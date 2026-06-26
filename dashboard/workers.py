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
        now = datetime.utcnow().isoformat()
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

        thread = threading.Thread(
            target=self._run,
            args=(job_id, target),
            daemon=True,
            name=f"job-{stage}-{job_id[:8]}",
        )
        with self._lock:
            self._threads[job_id] = thread
        thread.start()
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
        entry = {"ts": datetime.utcnow().isoformat(), "msg": message, "level": level}
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job["logs"].append(entry)
        self._emit("job_log", {"job_id": job_id, "entry": entry})

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

    jm.log(job_id, f"📊 {len(leads)} registros en dataset")
    jm.set_progress(job_id, 0, len(leads))

    filtered, stats = filter_leads(leads)

    jm.log(job_id, f"✅ Filtrados: {len(filtered)} leads válidos")
    jm.log(job_id, f"   Con teléfono: {stats.get('con_telefono', 0)}")
    jm.log(job_id, f"   Pasan filtro: {stats.get('pasan', 0)}")
    jm.log(job_id, f"   Descartados:  {stats.get('descartados', 0)}")

    session = Session()
    try:
        import uuid as _uuid
        nuevos = 0
        for i, lead in enumerate(filtered):
            if not jm.check_pause(job_id):
                jm.log(job_id, "⛔ Job cancelado", "warning")
                break

            telefono = (lead.get("phone") or lead.get("telefono", "")).strip()
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
            jm.set_progress(job_id, i + 1, len(filtered))

        session.commit()
        jm.log(job_id, f"✅ {nuevos} nuevos leads importados a la base de datos")
    finally:
        session.close()


def stage_send(job_id: str, limit: int | None = None):
    from config import config
    from modules.outreach import OutreachBot, PLANTILLAS, limpiar_telefono, _es_red_social, _es_link_whatsapp
    from database import Session, Lead
    import json as _json
    import random
    import asyncio as _asyncio

    jm = job_manager
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

        total = len(pending)
        jm.log(job_id, f"📋 {total} leads para enviar")
        jm.set_progress(job_id, 0, total)

        if total == 0:
            jm.log(job_id, "⚠️ Sin leads pendientes de envío", "warning")
            return

        # Build outreach dataset
        outreach_data = []
        for lead in pending:
            phone = lead.telefono or ""
            website = ""
            link = None
            if _es_link_whatsapp(website):
                link = website
            elif not _es_red_social(website):
                clean = limpiar_telefono(phone)
                link = f"https://wa.me/{clean}" if clean else None
            else:
                clean = limpiar_telefono(phone)
                link = f"https://wa.me/{clean}" if clean else None

            if not link:
                clean = limpiar_telefono(phone)
                link = f"https://wa.me/{clean}" if clean else None

            if link:
                outreach_data.append({
                    "lead_id": lead.lead_id,
                    "title": lead.nombre,
                    "phone": lead.telefono,
                    "whatsapp_link": link,
                    "categoryName": lead.categoria,
                })
        session.close()
        session = None
    except Exception:
        session.close()
        raise

    if not outreach_data:
        jm.log(job_id, "⚠️ Sin leads con WhatsApp válido", "warning")
        return

    tmp_file = config.DATA_DIR / "_pending_send.json"
    with open(tmp_file, "w", encoding="utf-8") as f:
        _json.dump(outreach_data, f)

    jm.log(job_id, f"🚀 Iniciando envío de {len(outreach_data)} mensajes...")
    jm.log(job_id, "📱 Abriendo WhatsApp Web — escaneá el QR si es la primera vez")

    from whatsplay import Client
    from whatsplay.auth import LocalProfileAuth
    import random

    data_dir = Path.home() / "whatsapp_session"
    auth = LocalProfileAuth(data_dir)
    client = Client(auth=auth, headless=False)

    plantillas = PLANTILLAS.copy()
    random.shuffle(plantillas)
    enviados_count = 0
    stop_event = jm._stop_events.get(job_id, threading.Event())

    @client.event("on_auth")
    async def on_auth():
        jm.log(job_id, "📸 Escaneá el QR en la ventana del navegador")

    @client.event("on_logged_in")
    async def on_logged_in():
        nonlocal enviados_count, plantillas

        for i, item in enumerate(outreach_data):
            if stop_event.is_set():
                jm.log(job_id, "⛔ Envíos cancelados", "warning")
                break

            while jm._pause_events.get(job_id, threading.Event()).is_set():
                if stop_event.is_set():
                    break
                await _asyncio.sleep(0.5)

            if not plantillas:
                plantillas = PLANTILLAS.copy()
                random.shuffle(plantillas)

            plantilla = plantillas.pop(0)
            link = item["whatsapp_link"]
            nombre = item["title"]

            jm.log(job_id, f"📤 [{i+1}/{len(outreach_data)}] {nombre}")
            try:
                numero = link.replace("https://wa.me/", "").split("?")[0]
                await client.send_message(numero, plantilla, open_via_url=True)
                await _asyncio.sleep(2)

                # Update DB
                _update_lead_sent(item["lead_id"], item["phone"], plantilla)
                enviados_count += 1
                jm.log(job_id, f"   ✅ Enviado")
                jm.set_progress(job_id, i + 1, len(outreach_data))

                if i < len(outreach_data) - 1:
                    import random as r
                    pausa = 15 + r.uniform(-3, 3)
                    jm.log(job_id, f"   ⏰ Pausa {pausa:.1f}s...")
                    await _asyncio.sleep(max(10, pausa))

            except Exception as e:
                jm.log(job_id, f"   ❌ Error: {e}", "error")
                await _asyncio.sleep(5)

        jm.log(job_id, f"\n✅ Enviados: {enviados_count}/{len(outreach_data)}")
        await client.stop()

    _asyncio.run(client.start())
    tmp_file.unlink(missing_ok=True)


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
    from config import config
    from modules.claude_builder import ClaudeBuilder, _build_agent_prompt, _run_claude_agent, _build_fallback_html
    from database import Session, Lead, ClaudeGeneration
    import re as _re
    import time

    jm = job_manager
    session = Session()
    try:
        if lead_ids:
            leads = session.query(Lead).filter(Lead.id.in_(lead_ids)).all()
        else:
            leads = session.query(Lead).filter(
                Lead.stage.in_(["waiting", "ready_deploy"]),
                Lead.project_path == None,
            ).all()
        leads_data = [l.to_dict() for l in leads]
        session.close()
        session = None
    except Exception:
        session.close()
        raise

    total = len(leads_data)
    jm.log(job_id, f"🎨 {total} sitios para generar")
    jm.set_progress(job_id, 0, total)

    if total == 0:
        jm.log(job_id, "⚠️ Sin leads interesados con proyecto pendiente", "warning")
        return

    websites_dir = config.WEBSITES_DIR
    websites_dir.mkdir(exist_ok=True)

    for i, lead in enumerate(leads_data):
        if not jm.check_pause(job_id):
            jm.log(job_id, "⛔ Generación cancelada", "warning")
            break

        nombre = lead["nombre"] or "negocio"
        jm.log(job_id, f"🖥️  [{i+1}/{total}] Generando web para: {nombre}")

        folder = _re.sub(r"[^a-z0-9_]", "", nombre.lower().replace(" ", "_"))[:50]
        project_path = websites_dir / folder
        project_path.mkdir(exist_ok=True)

        prompt = _build_agent_prompt(lead)
        t0 = time.time()

        # Capture claude output in logs
        capture = jm.make_log_capture(job_id)
        old_stdout = sys.stdout
        sys.stdout = capture
        try:
            success = _run_claude_agent(project_path, prompt)
        finally:
            sys.stdout = old_stdout
            capture.flush()

        duration = time.time() - t0

        if not success:
            jm.log(job_id, f"   ⚠️ index.html no generado — usando fallback", "warning")
            fallback = _build_fallback_html(lead)
            (project_path / "index.html").write_text(fallback, encoding="utf-8")

        # Update DB
        _update_lead_project(lead["id"], str(project_path), duration, success)
        jm.log(job_id, f"   ✅ {project_path.name}/ ({duration:.1f}s)")
        jm.set_progress(job_id, i + 1, total)

    jm.log(job_id, f"✅ Generación completada: {total} sitios")


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
            url_match = _re.search(r"https://\S+\.vercel\.app", full_output)
            url = url_match.group(0) if url_match else ""

            if url:
                _update_lead_deploy(lead_id, url, full_output)
                jm.log(job_id, f"   ✅ Live: {url}")
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
    from database import Session, Lead
    import asyncio as _asyncio

    jm = job_manager
    session = Session()
    try:
        if lead_ids:
            leads = session.query(Lead).filter(Lead.id.in_(lead_ids)).all()
        else:
            leads = session.query(Lead).filter(
                Lead.stage == "deployed",
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

    from whatsplay import Client
    from whatsplay.auth import LocalProfileAuth
    import random

    data_dir = Path.home() / "whatsapp_session"
    auth = LocalProfileAuth(data_dir)
    client = Client(auth=auth, headless=False)

    stop_event = jm._stop_events.get(job_id, threading.Event())
    enviados = 0

    @client.event("on_auth")
    async def on_auth():
        jm.log(job_id, "📸 Escaneá el QR si es necesario")

    @client.event("on_logged_in")
    async def on_logged_in():
        nonlocal enviados

        for i, (lead_id, nombre, telefono, url) in enumerate(leads_data):
            if stop_event.is_set():
                jm.log(job_id, "⛔ Envío cancelado", "warning")
                break

            while jm._pause_events.get(job_id, threading.Event()).is_set():
                if stop_event.is_set():
                    break
                await _asyncio.sleep(0.5)

            numero = re.sub(r"[^\d]", "", telefono)
            if not numero.startswith("54"):
                numero = "54" + numero

            mensaje = f"¡Hola! Te paso el link del sitio web, miralo y decime que te parece: {url}"
            jm.log(job_id, f"📤 [{i+1}/{total}] {nombre} → {url}")

            try:
                await client.send_message(numero, mensaje, open_via_url=True)
                await _asyncio.sleep(2)
                _update_lead_link_sent(lead_id)
                enviados += 1
                jm.log(job_id, "   ✅ Link enviado")
                jm.set_progress(job_id, i + 1, total)

                if i < total - 1:
                    pausa = 15 + random.uniform(-3, 3)
                    jm.log(job_id, f"   ⏰ Pausa {pausa:.1f}s")
                    await _asyncio.sleep(max(10, pausa))
            except Exception as e:
                jm.log(job_id, f"   ❌ {e}", "error")
                await _asyncio.sleep(5)

        jm.log(job_id, f"✅ Links enviados: {enviados}/{total}")
        await client.stop()

    _asyncio.run(client.start())


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


def stage_scrape(job_id: str):
    from modules.scraper import run_scraper

    jm = job_manager
    capture = jm.make_log_capture(job_id)
    old_stdout = sys.stdout
    sys.stdout = capture
    try:
        jm.log(job_id, "🔍 Iniciando scraper Apify...")
        run_scraper()
        jm.log(job_id, "✅ Scraping completado")
    finally:
        sys.stdout = old_stdout
        capture.flush()
