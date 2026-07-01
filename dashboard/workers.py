#!/usr/bin/env python3
"""
Background job manager for pipeline execution.
Each pipeline stage runs in a daemon thread.
Progress and logs are emitted via SocketIO.
"""

import asyncio
import json
import re
import subprocess
import sys
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

try:
    import eventlet
    _sleep = eventlet.sleep
except ImportError:
    import time
    _sleep = time.sleep

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))


class LogCapture:
    """Redirect a module's print output into our log stream."""
    def __init__(self, callback: Callable[[str, str], None]):
        self._cb = callback
        self._buf = ""

    def write(self, text: str):
        self._buf += text
        if "\n" in self._buf:
            lines = self._buf.split("\n")
            for line in lines[:-1]:
                clean = _strip_ansi(line)
                if clean.strip():
                    self._cb(clean.strip(), "info")
            self._buf = lines[-1]

    def flush(self):
        if self._buf.strip():
            self._cb(_strip_ansi(self._buf.strip()), "info")
            self._buf = ""


_ANSI = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _strip_ansi(s: str) -> str:
    return _ANSI.sub("", s)


class JobManager:
    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._stop_events: dict[str, threading.Event] = {}
        self._pause_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._socketio = None

    def init_socketio(self, sio):
        self._socketio = sio

    # ── Emit helpers ──────────────────────────────────────────

    def _emit(self, event: str, data: dict):
        if self._socketio:
            self._socketio.emit(event, data)

    def _emit_job(self, job_id: str):
        job = self.get_job(job_id)
        if job:
            self._emit("job_update", {"job": job})

    # ── Job lifecycle ─────────────────────────────────────────

    def create_and_start(self, stage: str, target: Callable, params: dict | None = None) -> str:
        job_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat() + "Z"
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "stage": stage,
                "status": "running",
                "progress": 0,
                "total_items": 0,
                "processed_items": 0,
                "started_at": now,
                "completed_at": None,
                "error": None,
                "logs": [],
                "params": params or {},
            }
            self._stop_events[job_id] = threading.Event()
            self._pause_events[job_id] = threading.Event()

        self._emit_job(job_id)

        if self._socketio:
            # eventlet/gevent: start_background_task emits dentro del event loop
            t = self._socketio.start_background_task(self._run, job_id, target)
        else:
            t = threading.Thread(
                target=self._run,
                args=(job_id, target),
                daemon=True,
                name=f"job-{stage}-{job_id[:8]}",
            )
            t.start()
        with self._lock:
            self._threads[job_id] = t
        return job_id

    def _run(self, job_id: str, target: Callable):
        try:
            target(job_id)
            with self._lock:
                job = self._jobs.get(job_id, {})
                if job.get("status") not in ("cancelled", "failed"):
                    job["status"] = "completed"
                    job["progress"] = 100
                    job["completed_at"] = datetime.utcnow().isoformat()
        except Exception as exc:
            tb = traceback.format_exc()
            with self._lock:
                job = self._jobs.get(job_id, {})
                job["status"] = "failed"
                job["error"] = str(exc)
                job["completed_at"] = datetime.utcnow().isoformat()
            self.log(job_id, f"❌ {exc}", "error")
            self.log(job_id, tb, "error")
        finally:
            self._emit_job(job_id)

    def stop(self, job_id: str):
        with self._lock:
            if job_id not in self._jobs:
                return
            self._stop_events[job_id].set()
            self._pause_events[job_id].clear()
            self._jobs[job_id]["status"] = "cancelled"
            self._jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()
        self._emit_job(job_id)

    def pause(self, job_id: str):
        with self._lock:
            if job_id not in self._jobs:
                return
            self._pause_events[job_id].set()
            self._jobs[job_id]["status"] = "paused"
        self._emit_job(job_id)

    def resume(self, job_id: str):
        with self._lock:
            if job_id not in self._jobs:
                return
            self._pause_events[job_id].clear()
            self._jobs[job_id]["status"] = "running"
        self._emit_job(job_id)

    # ── Checkpoint helpers (called from stage functions) ──────

    def is_stopped(self, job_id: str) -> bool:
        return self._stop_events.get(job_id, threading.Event()).is_set()

    def check_pause(self, job_id: str) -> bool:
        """Block while paused. Returns False if job was cancelled."""
        pause = self._pause_events.get(job_id, threading.Event())
        while pause.is_set():
            if self.is_stopped(job_id):
                return False
            threading.Event().wait(0.3)
        return not self.is_stopped(job_id)

    # ── Progress/log helpers (called from stage functions) ────

    def log(self, job_id: str, message: str, level: str = "info"):
        entry = {"ts": datetime.utcnow().isoformat() + "Z", "msg": message, "level": level}
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job["logs"].append(entry)
        self._emit("job_log", {"job_id": job_id, "entry": entry})
        _sleep(0)

    def set_progress(self, job_id: str, processed: int, total: int):
        pct = int(processed / total * 100) if total > 0 else 0
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job["progress"] = pct
                job["processed_items"] = processed
                job["total_items"] = total
        self._emit("job_progress", {
            "job_id": job_id, "progress": pct,
            "processed": processed, "total": total,
        })
        _sleep(0)  # cede el event loop para que eventlet flush el emit

    def get_job(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def get_all_jobs(self) -> list[dict]:
        with self._lock:
            return [dict(j) for j in self._jobs.values()]

    def get_active_job_for_stage(self, stage: str) -> dict | None:
        with self._lock:
            for j in self._jobs.values():
                if j["stage"] == stage and j["status"] in ("running", "paused"):
                    return dict(j)
        return None

    def make_log_capture(self, job_id: str) -> LogCapture:
        return LogCapture(lambda msg, lvl: self.log(job_id, msg, lvl))


# ── Singleton ─────────────────────────────────────────────────

job_manager = JobManager()


# ── Pipeline Stage Functions ──────────────────────────────────

def stage_discover(job_id: str, dataset_file: str | None = None):
    from config import config
    from modules.niche_filter import filter_leads, print_filter_report
    from database import Session, Lead
    import json as _json

    jm = job_manager
    ds_path = Path(dataset_file) if dataset_file else config.DATASET_FILE

    jm.log(job_id, f"📂 Leyendo dataset: {ds_path}")

    if not ds_path.exists():
        raise FileNotFoundError(f"Dataset no encontrado: {ds_path}")

    with open(ds_path, encoding="utf-8") as f:
        raw = _json.load(f)
    leads = raw if isinstance(raw, list) else [raw]

    total = len(leads)
    jm.log(job_id, f"📊 {total} registros en dataset")
    jm.set_progress(job_id, 0, total * 2)  # fase 1: filtrar, fase 2: importar

    # Fase 1: filtrar con progreso incremental
    filtered, stats = filter_leads(leads)
    jm.set_progress(job_id, total, total * 2)

    jm.log(job_id, f"✅ Filtrados: {len(filtered)} leads válidos de {stats.get('total', 0)} analizados")
    jm.log(job_id, f"   Aceptados:     {stats.get('accepted', len(filtered))}")
    jm.log(job_id, f"   Fuera Rosario: {stats.get('wrong_location', 0)}")
    jm.log(job_id, f"   Fuera nicho:   {stats.get('wrong_niche', 0)}")
    jm.log(job_id, f"   Tienen web:    {stats.get('has_real_website', 0)}")

    # Fase 2: importar a DB
    session = Session()
    try:
        import uuid as _uuid
        nuevos = 0
        for i, lead in enumerate(filtered):
            if not jm.check_pause(job_id):
                jm.log(job_id, "⛔ Job cancelado", "warning")
                break

            jm.set_progress(job_id, total + i + 1, total * 2)

            telefono = (lead.get("phone") or lead.get("telefono", "")).strip()
            if not telefono:
                website = lead.get("website") or ""
                import re as _re2
                wa_match = _re2.search(r"wa\.me/(\d+)", website)
                if wa_match:
                    telefono = wa_match.group(1)
            if not telefono:
                continue

            existing = session.query(Lead).filter_by(telefono=telefono).first()
            if existing:
                continue

            nombre = lead.get("title") or lead.get("nombre", "")
            session.add(Lead(
                lead_id   = str(_uuid.uuid4()),
                nombre    = nombre,
                telefono  = telefono,
                categoria = lead.get("categoryName") or lead.get("categoria", ""),
                direccion = lead.get("street") or lead.get("direccion", ""),
                ciudad    = lead.get("city") or "Rosario",
                puntaje   = float(lead["totalScore"]) if lead.get("totalScore") else None,
                resenas   = int(lead["reviewsCount"]) if lead.get("reviewsCount") else 0,
                stage     = "discovered",
            ))
            nuevos += 1
        session.commit()
        jm.log(job_id, f"✅ {nuevos} nuevos leads importados a la base de datos")
    finally:
        session.close()


def stage_send(job_id: str, limit: int | None = None):
    import random
    import time as _time
    import requests as _req
    from config import config
    from modules.outreach import PLANTILLAS, limpiar_telefono
    from database import Session, Lead

    jm = job_manager
    bridge_url = config.WA_BRIDGE_URL
    _headers = {"X-Bridge-Secret": config.BRIDGE_SECRET} if config.BRIDGE_SECRET else {}

    try:
        health = _req.get(f"{bridge_url}/health", timeout=5).json()
        if health.get("status") != "ready":
            jm.log(job_id, "❌ El bridge de WhatsApp no está listo. Iniciá el bridge primero.", "error")
            return
    except Exception as e:
        jm.log(job_id, f"❌ No se pudo conectar al bridge WhatsApp ({bridge_url}): {e}", "error")
        return

    session = Session()
    try:
        pending = session.query(Lead).filter(Lead.stage == "pending_send").all()
        if not pending:
            pending = session.query(Lead).filter(
                Lead.enviado == False,
                Lead.stage == "discovered",
            ).all()
        if limit:
            pending = pending[:limit]
        leads_data = [(l.id, l.nombre, l.telefono, l.categoria) for l in pending]
        session.close()
        session = None
    except Exception:
        session.close()
        raise

    total = len(leads_data)
    jm.log(job_id, f"📋 {total} leads para enviar")
    jm.set_progress(job_id, 0, total)

    if total == 0:
        jm.log(job_id, "⚠️ Sin leads pendientes de envío", "warning")
        return

    plantillas = PLANTILLAS.copy()
    random.shuffle(plantillas)
    enviados = 0
    stop_event = jm._stop_events.get(job_id, threading.Event())

    for i, (lead_id, nombre, telefono, _cat) in enumerate(leads_data):
        if stop_event.is_set():
            jm.log(job_id, "⛔ Envíos cancelados", "warning")
            break

        while jm._pause_events.get(job_id, threading.Event()).is_set():
            if stop_event.is_set():
                break
            _time.sleep(0.5)

        if not plantillas:
            plantillas = PLANTILLAS.copy()
            random.shuffle(plantillas)

        plantilla = plantillas.pop(0)
        numero = limpiar_telefono(telefono)
        if not numero:
            jm.log(job_id, f"   ⚠️ [{i+1}/{total}] {nombre} — teléfono inválido", "warning")
            continue
        if not numero.startswith("54"):
            numero = "54" + numero

        jm.log(job_id, f"📤 [{i+1}/{total}] {nombre}")
        try:
            resp = _req.post(
                f"{bridge_url}/send",
                json={"phone": numero, "message": plantilla},
                headers=_headers,
                timeout=30,
            )
            resp.raise_for_status()
            _update_lead_sent(lead_id, telefono, plantilla)
            enviados += 1
            jm.log(job_id, "   ✅ Enviado")
            jm.set_progress(job_id, i + 1, total)

            if i < total - 1:
                pausa = 15 + random.uniform(-3, 3)
                jm.log(job_id, f"   ⏰ Pausa {pausa:.1f}s")
                _time.sleep(max(10, pausa))
        except Exception as e:
            jm.log(job_id, f"   ❌ {e}", "error")
            _time.sleep(5)

    jm.log(job_id, f"✅ Enviados: {enviados}/{total}")


def _update_lead_sent(lead_id: str | None, telefono: str, mensaje: str):
    from database import Session, Lead
    session = Session()
    try:
        lead = session.query(Lead).filter(
            (Lead.lead_id == lead_id) if lead_id else (Lead.telefono == telefono)
        ).first()
        if lead:
            lead.enviado = True
            lead.fecha_envio = datetime.utcnow()
            lead.stage = "sent"
            lead.mensaje_enviado = mensaje
            session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def stage_generate_webs(job_id: str, lead_ids: list[int] | None = None):
    import concurrent.futures
    import time
    from config import config
    from modules.claude_builder import _build_agent_prompt, _run_claude_agent, _build_fallback_html, _fetch_brand_assets
    from database import Session, Lead
    import re as _re

    MAX_WORKERS = 2  # max Claude processes en paralelo

    jm = job_manager
    session = Session()
    try:
        if lead_ids:
            leads = session.query(Lead).filter(Lead.id.in_(lead_ids)).all()
        else:
            leads = session.query(Lead).filter(
                Lead.stage.in_(["sent", "waiting", "ready_deploy"]),
                Lead.project_path == None,
            ).all()
        leads_data = [l.to_dict() for l in leads]
        session.close()
        session = None
    except Exception:
        session.close()
        raise

    total = len(leads_data)
    jm.log(job_id, f"🎨 {total} sitios para generar (max {MAX_WORKERS} en paralelo)")
    jm.set_progress(job_id, 0, total)

    if total == 0:
        jm.log(job_id, "⚠️ Sin leads interesados con proyecto pendiente", "warning")
        return

    websites_dir = config.WEBSITES_DIR
    websites_dir.mkdir(exist_ok=True)

    completed = 0
    counter_lock = threading.Lock()

    def process_one(lead):
        nombre = lead["nombre"] or "negocio"
        folder = _re.sub(r"[^a-z0-9_]", "", nombre.lower().replace(" ", "_"))[:50]
        project_path = websites_dir / folder
        project_path.mkdir(exist_ok=True)

        jm.log(job_id, f"🖥️  Generando: {nombre}")
        brand = _fetch_brand_assets(lead.get("telefono") or lead.get("phone", ""), project_path)
        if brand.get("logo_path"):
            jm.log(job_id, f"   🖼️  Logo extraído de WhatsApp")
        if brand.get("colors"):
            jm.log(job_id, f"   🎨 Colores: {', '.join(brand['colors'])}")
        prompt = _build_agent_prompt(lead, brand)
        t0 = time.time()

        success = _run_claude_agent(project_path, prompt)
        duration = time.time() - t0

        if not success:
            jm.log(job_id, f"   ⚠️ {nombre}: fallback HTML", "warning")
            fallback = _build_fallback_html(lead)
            (project_path / "index.html").write_text(fallback, encoding="utf-8")

        _update_lead_project(lead["id"], str(project_path), duration, success)
        jm.log(job_id, f"   ✅ {nombre} ({duration:.1f}s)")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_one, lead): lead for lead in leads_data}
        for future in concurrent.futures.as_completed(futures):
            if jm.is_stopped(job_id):
                jm.log(job_id, "⛔ Generación cancelada", "warning")
                break
            try:
                future.result()
            except Exception as exc:
                lead = futures[future]
                jm.log(job_id, f"   ❌ {lead.get('nombre','?')}: {exc}", "error")
            with counter_lock:
                completed += 1
            jm.set_progress(job_id, completed, total)

    jm.log(job_id, f"✅ Generación completada: {completed}/{total} sitios")


def _update_lead_project(lead_id: int, project_path: str, duration: float, success: bool):
    from database import Session, Lead
    session = Session()
    try:
        lead = session.query(Lead).filter_by(id=lead_id).first()
        if lead:
            lead.project_path = project_path
            lead.website_duration = duration
            lead.stage = "ready_deploy" if success else "error"
            lead.website_version = (lead.website_version or 0) + 1
            session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def stage_deploy(job_id: str, lead_ids: list[int] | None = None):
    from modules.deploy import Deployer
    from database import Session, Lead
    import time

    jm = job_manager
    deployer = Deployer()

    session = Session()
    try:
        if lead_ids:
            leads = session.query(Lead).filter(Lead.id.in_(lead_ids)).all()
        else:
            leads = session.query(Lead).filter(
                Lead.stage == "ready_deploy",
                Lead.project_path != None,
                Lead.live_url == None,
            ).all()
        leads_data = [(l.id, l.nombre, l.project_path) for l in leads]
        session.close()
        session = None
    except Exception:
        session.close()
        raise

    total = len(leads_data)
    jm.log(job_id, f"🚀 {total} sitios para desplegar")
    jm.set_progress(job_id, 0, total)

    if total == 0:
        jm.log(job_id, "⚠️ Sin sitios pendientes de deploy", "warning")
        return

    for i, (lead_id, nombre, project_path) in enumerate(leads_data):
        if not jm.check_pause(job_id):
            jm.log(job_id, "⛔ Deploy cancelado", "warning")
            break

        jm.log(job_id, f"🌐 [{i+1}/{total}] Desplegando: {nombre}")
        ppath = Path(project_path)

        if not ppath.exists():
            jm.log(job_id, f"   ⚠️ Carpeta no existe: {project_path}", "warning")
            continue

        # Stream Vercel output
        import subprocess
        import re as _re
        project_name = _re.sub(r"[^a-z0-9-]", "", nombre.lower().replace(" ", "-"))[:52]

        try:
            proc = subprocess.Popen(
                ["vercel", "--prod", "--yes", f"--name={project_name}"],
                cwd=str(ppath),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            output_lines = []
            for line in proc.stdout:
                clean = _strip_ansi(line.rstrip())
                if clean:
                    jm.log(job_id, f"   {clean}")
                    output_lines.append(clean)
            proc.wait()

            full_output = "\n".join(output_lines)
            # Prefer the production alias URL (no hash in subdomain).
            # vercel --prod prints "Preview: hash-url" first, then "Production: alias-url".
            prod_match = _re.search(r"Production:\s+(https://\S+)", full_output, _re.IGNORECASE)
            if prod_match:
                url = prod_match.group(1).rstrip(".")
            else:
                all_urls = _re.findall(r"https://\S+\.vercel\.app", full_output)
                clean_urls = [u for u in all_urls if not _re.search(r"-[a-z0-9]{9,}-", u)]
                url = clean_urls[-1] if clean_urls else (all_urls[-1] if all_urls else "")

            if url:
                _update_lead_deploy(lead_id, url, full_output)
                jm.log(job_id, f"   ✅ Live: {url}")
                try:
                    from modules.deploy import Deployer as _Deployer
                    _Deployer()._desactivar_proteccion(ppath)
                except Exception as _e:
                    jm.log(job_id, f"   ⚠️ No se pudo desactivar protección: {_e}", "warning")
            else:
                jm.log(job_id, "   ⚠️ Deploy OK pero no se encontró URL", "warning")

        except FileNotFoundError:
            jm.log(job_id, "   ❌ 'vercel' no instalado. Ejecutá: npm i -g vercel", "error")
        except Exception as e:
            jm.log(job_id, f"   ❌ {e}", "error")

        jm.set_progress(job_id, i + 1, total)


def _update_lead_deploy(lead_id: int, url: str, logs: str):
    from database import Session, Lead
    session = Session()
    try:
        lead = session.query(Lead).filter_by(id=lead_id).first()
        if lead:
            lead.live_url = url
            lead.stage = "deployed"
            lead.deploy_logs = logs[:5000]
            session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def stage_send_links(job_id: str, lead_ids: list[int] | None = None):
    import random
    import time as _time
    import requests as _req
    from config import config
    from modules.outreach import limpiar_telefono
    from database import Session, Lead

    jm = job_manager
    bridge_url = config.WA_BRIDGE_URL
    _headers = {"X-Bridge-Secret": config.BRIDGE_SECRET} if config.BRIDGE_SECRET else {}

    try:
        health = _req.get(f"{bridge_url}/health", timeout=5).json()
        if health.get("status") != "ready":
            jm.log(job_id, "❌ El bridge de WhatsApp no está listo. Iniciá el bridge primero.", "error")
            return
    except Exception as e:
        jm.log(job_id, f"❌ No se pudo conectar al bridge WhatsApp ({bridge_url}): {e}", "error")
        return

    session = Session()
    try:
        if lead_ids:
            leads = session.query(Lead).filter(Lead.id.in_(lead_ids)).all()
        else:
            leads = session.query(Lead).filter(
                Lead.live_url != None,
                Lead.enviado_links == False,
            ).all()
        leads_data = [(l.id, l.nombre, l.telefono, l.live_url) for l in leads]
        session.close()
        session = None
    except Exception:
        session.close()
        raise

    total = len(leads_data)
    jm.log(job_id, f"📤 {total} links para enviar")
    jm.set_progress(job_id, 0, total)

    if total == 0:
        jm.log(job_id, "⚠️ Sin links pendientes de envío", "warning")
        return

    stop_event = jm._stop_events.get(job_id, threading.Event())
    enviados = 0

    for i, (lead_id, nombre, telefono, url) in enumerate(leads_data):
        if stop_event.is_set():
            jm.log(job_id, "⛔ Envíos cancelados", "warning")
            break

        while jm._pause_events.get(job_id, threading.Event()).is_set():
            if stop_event.is_set():
                break
            _time.sleep(0.5)

        numero = limpiar_telefono(telefono)
        if not numero:
            jm.log(job_id, f"   ⚠️ [{i+1}/{total}] {nombre} — teléfono inválido", "warning")
            continue
        if not numero.startswith("54"):
            numero = "54" + numero

        mensaje = f"Hola! Te paso el link del sitio web que te armé, miralo y decime que te parece: {url}"
        jm.log(job_id, f"📤 [{i+1}/{total}] {nombre}")
        try:
            resp = _req.post(
                f"{bridge_url}/send",
                json={"phone": numero, "message": mensaje},
                headers=_headers,
                timeout=30,
            )
            resp.raise_for_status()
            _update_lead_link_sent(lead_id)
            enviados += 1
            jm.log(job_id, "   ✅ Link enviado")
            jm.set_progress(job_id, i + 1, total)

            if i < total - 1:
                pausa = 15 + random.uniform(-3, 3)
                jm.log(job_id, f"   ⏰ Pausa {pausa:.1f}s")
                _time.sleep(max(10, pausa))
        except Exception as e:
            jm.log(job_id, f"   ❌ {e}", "error")
            _time.sleep(5)

    jm.log(job_id, f"✅ Links enviados: {enviados}/{total}")


def _update_lead_link_sent(lead_id: int):
    from database import Session, Lead
    session = Session()
    try:
        lead = session.query(Lead).filter_by(id=lead_id).first()
        if lead:
            lead.enviado_links = True
            lead.fecha_envio_links = datetime.utcnow()
            lead.stage = "link_sent"
            session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def stage_social_post(job_id: str, lead_ids: list[int], post_type: str = "servicio"):
    """Generate and publish Instagram posts for the given clients."""
    from modules.social_agent import publish_post, generate_post_content, get_image_url, _niche_key
    from database import Session, Lead

    jm = job_manager

    session = Session()
    try:
        leads = session.query(Lead).filter(Lead.id.in_(lead_ids)).all()
        leads_data = [l.to_dict() for l in leads]
        session.close()
        session = None
    except Exception:
        session.close()
        raise

    total = len(leads_data)
    jm.log(job_id, f"📱 {total} clientes para postear — tipo: {post_type}")
    jm.set_progress(job_id, 0, total)

    if total == 0:
        jm.log(job_id, "⚠️ Sin clientes seleccionados", "warning")
        return

    ok_count = 0
    for i, client in enumerate(leads_data):
        if not jm.check_pause(job_id):
            jm.log(job_id, "⛔ Cancelado", "warning")
            break

        nombre = client.get("nombre", "?")
        jm.log(job_id, f"📝 [{i+1}/{total}] Generando contenido: {nombre}")
        try:
            result = publish_post(client, post_type)
            ok_count += 1
            jm.log(job_id, f"   ✅ Publicado — media_id: {result['media_id']}")
        except Exception as e:
            jm.log(job_id, f"   ❌ {nombre}: {e}", "error")

        jm.set_progress(job_id, i + 1, total)
        if i < total - 1:
            _sleep(3)  # brief rate-limit pause between posts

    jm.log(job_id, f"✅ Posts publicados: {ok_count}/{total}")


FOLLOWUP_MESSAGES = [
    "Hola, pudieron ver el mensaje?",
    "Hola, pudieron ver la pagina web?",
    "Hola, buenas tardes, pudieron decidirse? Si les gusto la pagina web la podemos publicar ya esta semana.",
]


def stage_followup(job_id: str, lead_ids: list[int], message_index: int):
    import random
    import time as _time
    import requests as _req
    from config import config
    from modules.outreach import limpiar_telefono
    from database import Session, Lead

    jm = job_manager
    bridge_url = config.WA_BRIDGE_URL
    _headers = {"X-Bridge-Secret": config.BRIDGE_SECRET} if config.BRIDGE_SECRET else {}

    if message_index < 0 or message_index >= len(FOLLOWUP_MESSAGES):
        jm.log(job_id, f"❌ message_index {message_index} inválido (0-{len(FOLLOWUP_MESSAGES)-1})", "error")
        return

    mensaje = FOLLOWUP_MESSAGES[message_index]
    followup_stage = message_index + 1  # 1-indexed tag

    try:
        health = _req.get(f"{bridge_url}/health", timeout=5).json()
        if health.get("status") != "ready":
            jm.log(job_id, "❌ El bridge de WhatsApp no está listo. Iniciá el bridge primero.", "error")
            return
    except Exception as e:
        jm.log(job_id, f"❌ No se pudo conectar al bridge WhatsApp ({bridge_url}): {e}", "error")
        return

    session = Session()
    try:
        leads = session.query(Lead).filter(Lead.id.in_(lead_ids)).all()
        leads_data = [(l.id, l.nombre, l.telefono) for l in leads]
        session.close()
        session = None
    except Exception:
        session.close()
        raise

    total = len(leads_data)
    jm.log(job_id, f"📤 Seguimiento #{followup_stage} — {total} leads")
    jm.log(job_id, f"   Mensaje: \"{mensaje}\"")
    jm.set_progress(job_id, 0, total)

    if total == 0:
        jm.log(job_id, "⚠️ Sin leads seleccionados", "warning")
        return

    stop_event = jm._stop_events.get(job_id, threading.Event())
    enviados = 0

    for i, (lead_id, nombre, telefono) in enumerate(leads_data):
        if stop_event.is_set():
            jm.log(job_id, "⛔ Seguimientos cancelados", "warning")
            break

        while jm._pause_events.get(job_id, threading.Event()).is_set():
            if stop_event.is_set():
                break
            _time.sleep(0.5)

        numero = limpiar_telefono(telefono)
        if not numero:
            jm.log(job_id, f"   ⚠️ [{i+1}/{total}] {nombre} — teléfono inválido", "warning")
            continue
        if not numero.startswith("54"):
            numero = "54" + numero

        jm.log(job_id, f"📤 [{i+1}/{total}] {nombre}")
        try:
            resp = _req.post(
                f"{bridge_url}/send",
                json={"phone": numero, "message": mensaje},
                headers=_headers,
                timeout=30,
            )
            resp.raise_for_status()
            _update_lead_followup(lead_id, followup_stage)
            enviados += 1
            jm.log(job_id, "   ✅ Enviado")
            jm.set_progress(job_id, i + 1, total)

            if i < total - 1:
                pausa = 15 + random.uniform(-3, 3)
                jm.log(job_id, f"   ⏰ Pausa {pausa:.1f}s")
                _time.sleep(max(10, pausa))
        except Exception as e:
            jm.log(job_id, f"   ❌ {e}", "error")
            _time.sleep(5)

    jm.log(job_id, f"✅ Seguimientos enviados: {enviados}/{total}")


def _update_lead_followup(lead_id: int, followup_stage: int):
    from database import Session, Lead
    session = Session()
    try:
        lead = session.query(Lead).filter_by(id=lead_id).first()
        if lead:
            lead.followup_stage = followup_stage
            lead.followup_sent_at = datetime.utcnow()
            session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def stage_scrape(job_id: str, queries: list[str] | None = None, account: str = "both"):
    import json as _json
    import time as _time
    import requests as _requests
    from config import config

    jm = job_manager
    ACTOR_ID = config.APIFY_ACTOR_ID.replace("/", "~")
    API_BASE = "https://api.apify.com/v2"
    RESULTS_PER_QUERY = 50

    # Build token pool filtered by requested account
    full_pool = [t for t in [config.APIFY_TOKEN, config.APIFY_TOKEN_2] if t]
    if not full_pool:
        jm.log(job_id, "APIFY_TOKEN no configurado en .env", "error")
        return

    if account == "1":
        token_pool = full_pool[:1]
    elif account == "2":
        token_pool = full_pool[1:2] if len(full_pool) >= 2 else full_pool
    else:
        token_pool = full_pool

    if not token_pool:
        jm.log(job_id, f"Cuenta {account} no disponible — verificar APIFY_TOKEN_2 en .env", "error")
        return

    exhausted: set[str] = set()  # tokens that hit 402

    def _get_token(idx: int) -> str | None:
        available = [t for t in token_pool if t not in exhausted]
        if not available:
            return None
        return available[idx % len(available)]

    if not queries:
        queries = config.APIFY_SEARCH_QUERIES
    total_q = len(queries)

    if account == "both":
        cuentas = f"{len(token_pool)} cuenta(s)"
    else:
        cuentas = f"cuenta {account}"
    jm.log(job_id, f"Iniciando scraper — {total_q} queries, {cuentas}, Rosario")
    jm.set_progress(job_id, 0, total_q)

    # Load existing dataset to merge
    ds_path = config.DATASET_FILE
    existing: list[dict] = []
    seen_phones: set[str] = set()
    if ds_path.exists():
        try:
            with open(ds_path, encoding="utf-8") as f:
                existing = _json.load(f)
            seen_phones = {r.get("phone", "") for r in existing if r.get("phone")}
            jm.log(job_id, f"   Ya en dataset: {len(existing)} registros")
        except Exception:
            existing = []

    all_new: list[dict] = []

    for i, query in enumerate(queries):
        if not jm.check_pause(job_id):
            jm.log(job_id, "Scraping cancelado", "warning")
            break

        token = _get_token(i)
        if not token:
            jm.log(job_id, "Cuota agotada en todas las cuentas Apify", "error")
            break

        cuenta_num = full_pool.index(token) + 1
        jm.log(job_id, f"[{i+1}/{total_q}] (cuenta {cuenta_num}) {query}")

        actor_input = {
            "searchStringsArray": [query],
            "language": "es",
            "maxCrawledPlacesPerSearch": RESULTS_PER_QUERY,
            "countryCode": "ar",
            "includeHistogram": False,
            "includeOpeningHours": False,
            "includePeopleAlsoSearch": False,
            "exportPlaceUrls": False,
            "additionalInfo": False,
        }

        try:
            run_resp = _requests.post(
                f"{API_BASE}/acts/{ACTOR_ID}/runs",
                json=actor_input,
                params={"token": token},
                timeout=30,
            )
            if run_resp.status_code == 402:
                jm.log(job_id, f"   Cuenta {cuenta_num} sin creditos — cambiando a otra cuenta", "warning")
                exhausted.add(token)
                # Retry this same query with next available token
                token = _get_token(i)
                if not token:
                    jm.log(job_id, "Cuota agotada en todas las cuentas Apify", "error")
                    break
                cuenta_num = full_pool.index(token) + 1
                jm.log(job_id, f"   Reintentando con cuenta {cuenta_num}")
                run_resp = _requests.post(
                    f"{API_BASE}/acts/{ACTOR_ID}/runs",
                    json=actor_input,
                    params={"token": token},
                    timeout=30,
                )
                if run_resp.status_code == 402:
                    exhausted.add(token)
                    jm.log(job_id, "Cuota agotada en todas las cuentas Apify", "error")
                    break

            if run_resp.status_code not in (200, 201):
                jm.log(job_id, f"   HTTP {run_resp.status_code}: {run_resp.text[:120]}", "warning")
                jm.set_progress(job_id, i + 1, total_q)
                continue

            run_id = run_resp.json()["data"]["id"]
            dataset_id = run_resp.json()["data"]["defaultDatasetId"]
            jm.log(job_id, f"   Run {run_id[:8]}... aguardando")

            # Poll until SUCCEEDED
            deadline = _time.time() + 300
            status = "RUNNING"
            while _time.time() < deadline:
                _time.sleep(6)
                if not jm.check_pause(job_id):
                    break
                try:
                    st = _requests.get(
                        f"{API_BASE}/actor-runs/{run_id}",
                        params={"token": token},
                        timeout=15,
                    ).json()
                    status = st["data"]["status"]
                    if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                        break
                except Exception:
                    pass

            if status != "SUCCEEDED":
                jm.log(job_id, f"   Run {status}", "warning")
                jm.set_progress(job_id, i + 1, total_q)
                continue

            # Fetch results
            items = _requests.get(
                f"{API_BASE}/datasets/{dataset_id}/items",
                params={"token": token, "format": "json"},
                timeout=60,
            ).json()

            added_here = 0
            for item in items:
                rec = {
                    "title": item.get("title", ""),
                    "totalScore": item.get("totalScore"),
                    "reviewsCount": item.get("reviewsCount", 0),
                    "street": item.get("street", ""),
                    "city": item.get("city", ""),
                    "state": item.get("state", ""),
                    "countryCode": item.get("countryCode", ""),
                    "phone": item.get("phone", ""),
                    "website": item.get("website", ""),
                    "categories": item.get("categories", []),
                    "categoryName": item.get("categoryName", ""),
                    "url": item.get("url", ""),
                    "permanentlyClosed": item.get("permanentlyClosed", False),
                }
                phone = rec.get("phone", "")
                if phone and phone in seen_phones:
                    continue
                if phone:
                    seen_phones.add(phone)
                all_new.append(rec)
                added_here += 1

            jm.log(job_id, f"   {added_here} nuevos resultados")

        except _requests.Timeout:
            jm.log(job_id, f"   Timeout — query: {query}", "warning")
        except Exception as e:
            jm.log(job_id, f"   Error: {e}", "error")

        jm.set_progress(job_id, i + 1, total_q)

    # Merge and save
    merged = existing + all_new
    try:
        ds_path.parent.mkdir(exist_ok=True)
        with open(ds_path, "w", encoding="utf-8") as f:
            _json.dump(merged, f, ensure_ascii=False, indent=2)
        jm.log(job_id, f"Scraping completado: +{len(all_new)} nuevos ({len(merged)} total)")
        jm.log(job_id, f"   Guardado en: {ds_path}")
    except Exception as e:
        jm.log(job_id, f"Error guardando dataset: {e}", "error")
