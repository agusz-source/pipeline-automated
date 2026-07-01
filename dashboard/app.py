#!/usr/bin/env python3
"""
Binario Websites — Production Dashboard
Flask-SocketIO backend with SQLite via SQLAlchemy.
"""

import json
import logging
import sys
import threading
import traceback

# Suppress harmless "Bad file descriptor" noise from eventlet WSGI on socket close
logging.getLogger("eventlet.wsgi.server").setLevel(logging.CRITICAL)
import uuid
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from functools import wraps

from flask import Flask, abort, jsonify, render_template, request
from flask_socketio import SocketIO, emit

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

# ── App setup ─────────────────────────────────────────────────

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["SECRET_KEY"] = "binario-2024-secret"
app.config["JSON_SORT_KEYS"] = False

socketio = SocketIO(
    app,
    async_mode="eventlet",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
)

# ── Database & workers ────────────────────────────────────────

from database import (
    Session, Lead, PipelineJob, ErrorLog, ClaudeGeneration,
    Template, AppConfig, Finanza, STAGE_CHOICES, STAGE_LABELS,
    init_db, migrate_from_csv,
)
from workers import (
    job_manager,
    stage_discover, stage_send, stage_generate_webs,
    stage_deploy, stage_send_links, stage_scrape, stage_followup,
    stage_social_post, FOLLOWUP_MESSAGES,
)

job_manager.init_socketio(socketio)


# ── Helpers ───────────────────────────────────────────────────

def ok(data: dict | None = None) -> tuple:
    return jsonify({"ok": True, **(data or {})}), 200


def err(msg: str, code: int = 400) -> tuple:
    return jsonify({"ok": False, "error": msg}), code


def get_json_body():
    body = request.get_json(silent=True)
    if body is None:
        abort(400, "JSON body required")
    return body


def _advance_monthly(d: date, today: date) -> date:
    while d <= today:
        year = d.year + (d.month // 12)
        month = (d.month % 12) + 1
        last = monthrange(year, month)[1]
        d = d.replace(year=year, month=month, day=min(d.day, last))
    return d


def _renewals(leads) -> dict:
    today = date.today()
    windows = {"7d": [], "30d": [], "60d": []}
    CAMPOS = {
        "fecha_renovacion_web":           ("Web", False),
        "fecha_renovacion_hosting":       ("Hosting", False),
        "fecha_renovacion_mantenimiento": ("Mantenimiento", True),
    }
    for lead in leads:
        for campo, (label, mensual) in CAMPOS.items():
            val = getattr(lead, campo, None)
            if not val:
                continue
            if isinstance(val, str):
                try:
                    val = date.fromisoformat(val[:10])
                except ValueError:
                    continue
            if mensual and val <= today:
                val = _advance_monthly(val, today)
            dias = (val - today).days
            item = {
                "nombre": lead.nombre,
                "telefono": lead.telefono,
                "tipo": label,
                "fecha": val.isoformat(),
                "dias": dias,
                "vencido": dias < 0,
            }
            if dias <= 7:
                windows["7d"].append(item)
            elif dias <= 30:
                windows["30d"].append(item)
            elif dias <= 60:
                windows["60d"].append(item)
    for k in windows:
        windows[k].sort(key=lambda x: x["dias"])
    return windows


def _stats(leads) -> dict:
    total      = len(leads)
    enviados   = sum(1 for l in leads if l.enviado)
    respondieron = sum(1 for l in leads if l.estado_respuesta and l.estado_respuesta != "neutral")
    interesados  = sum(1 for l in leads if l.estado_respuesta in
                       ("interest", "positive_intent", "price_request", "follow_up"))
    rechazados   = sum(1 for l in leads if l.estado_respuesta == "rejection")
    con_web   = sum(1 for l in leads if l.project_path)
    con_link  = sum(1 for l in leads if l.live_url)
    links_env = sum(1 for l in leads if l.enviado_links)
    clientes  = sum(1 for l in leads if l.fecha_entrega)

    def pct(a, b):
        return round(a / b * 100, 1) if b else 0

    return {
        "total": total,
        "enviados": enviados,
        "respondieron": respondieron,
        "interesados": interesados,
        "rechazados": rechazados,
        "con_web": con_web,
        "con_link": con_link,
        "links_enviados": links_env,
        "clientes": clientes,
        "tasa_envio": pct(enviados, total),
        "tasa_respuesta": pct(respondieron, enviados),
        "tasa_interes": pct(interesados, respondieron),
        "tasa_web": pct(con_web, interesados),
        "tasa_deploy": pct(con_link, con_web),
    }


def _kategorias(leads) -> list:
    cats: dict[str, dict] = defaultdict(lambda: {"total": 0, "enviados": 0, "interesados": 0, "link": 0})
    for l in leads:
        cat = l.categoria or "General"
        cats[cat]["total"] += 1
        if l.enviado:
            cats[cat]["enviados"] += 1
        if l.estado_respuesta in ("interest", "positive_intent", "price_request"):
            cats[cat]["interesados"] += 1
        if l.live_url:
            cats[cat]["link"] += 1
    return sorted([
        {
            "nombre": cat,
            "total": d["total"],
            "enviados": d["enviados"],
            "interesados": d["interesados"],
            "convertidos": d["link"],
            "tasa_envio": round(d["enviados"] / d["total"] * 100, 1) if d["total"] else 0,
            "tasa_interes": round(d["interesados"] / d["enviados"] * 100, 1) if d["enviados"] else 0,
        }
        for cat, d in cats.items()
    ], key=lambda x: -x["total"])[:12]


# ── Main Routes ───────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── Dashboard API ─────────────────────────────────────────────

@app.route("/api/dashboard/summary")
def api_dashboard_summary():
    session = Session()
    try:
        leads  = session.query(Lead).all()
        pagos  = session.query(Finanza).all()
        today  = date.today()
        now    = datetime.utcnow()

        stats = _stats(leads)

        # MRR — paid/partial this month, separated by currency
        def _in_month(p, yr, mo, moneda):
            return (p.estado in ("pagado", "parcial") and p.monto and p.fecha
                    and p.fecha.year == yr and p.fecha.month == mo and p.moneda == moneda)
        lm = (today.replace(day=1) - timedelta(days=1))
        mrr_ars      = sum(p.monto for p in pagos if _in_month(p, today.year, today.month, "ARS"))
        mrr_usd      = sum(p.monto for p in pagos if _in_month(p, today.year, today.month, "USD"))
        mrr_prev_ars = sum(p.monto for p in pagos if _in_month(p, lm.year, lm.month, "ARS"))
        mrr_prev_usd = sum(p.monto for p in pagos if _in_month(p, lm.year, lm.month, "USD"))
        mrr      = mrr_ars
        mrr_prev = mrr_prev_ars

        # Clients
        clients = [l for l in leads if l.fecha_entrega]
        new_this_month = [l for l in clients if l.fecha_entrega and l.fecha_entrega.year == today.year and l.fecha_entrega.month == today.month]

        # Follow-ups: sent, no response, older than 3 days
        cutoff = now - timedelta(days=3)
        fu_leads = [l for l in leads if l.enviado and not l.estado_respuesta and l.fecha_envio and l.fecha_envio < cutoff]

        # Renewals
        all_renewals = _renewals(clients)
        ren_7d    = all_renewals["7d"]
        ren_overdue = [r for w in all_renewals.values() for r in w if r["vencido"]]

        # Tasks (generated from live data)
        tasks = []
        waiting = [l for l in leads if l.stage == "waiting"]
        for l in waiting[:3]:
            tasks.append({"type": "waiting", "title": f"Responder a {l.nombre}", "sub": "Respondio tu mensaje — requiere atencion", "priority": "high", "lead_id": l.id})
        for r in ren_7d[:2]:
            label = "Vencida" if r["vencido"] else f"Vence en {r['dias']}d"
            tasks.append({"type": "renewal", "title": f"Renovar {r['tipo']} — {r['nombre']}", "sub": label, "priority": "high" if r["vencido"] or r["dias"] <= 2 else "medium"})
        for l in fu_leads[:3]:
            days_ago = int((now - l.fecha_envio).total_seconds() / 86400) if l.fecha_envio else 0
            tasks.append({"type": "followup", "title": f"Seguimiento: {l.nombre}", "sub": f"Sin respuesta hace {days_ago} dias", "priority": "medium"})
        ready = [l for l in leads if l.stage == "ready_deploy"]
        for l in ready[:2]:
            tasks.append({"type": "deploy", "title": f"Publicar sitio de {l.nombre}", "sub": "Listo para deploy", "priority": "medium"})
        prio = {"high": 0, "medium": 1, "low": 2}
        tasks.sort(key=lambda t: prio.get(t["priority"], 2))

        # Activity feed (synthetic from lead timestamps)
        events = []
        for l in sorted(leads, key=lambda x: x.updated_at or datetime.min, reverse=True)[:30]:
            if l.live_url and l.stage in ("deployed", "link_sent", "completed") and l.updated_at and (now - l.updated_at).total_seconds() < 14 * 86400:
                events.append({"type": "deployed", "label": "Sitio publicado", "client": l.nombre, "time": l.updated_at.isoformat(), "color": "accent"})
            if l.fecha_respuesta and (now - l.fecha_respuesta).total_seconds() < 7 * 86400:
                events.append({"type": "reply", "label": "Respondio por WhatsApp", "client": l.nombre, "time": l.fecha_respuesta.isoformat(), "color": "green"})
            if l.fecha_envio and (now - l.fecha_envio).total_seconds() < 7 * 86400:
                events.append({"type": "sent", "label": "Mensaje enviado", "client": l.nombre, "time": l.fecha_envio.isoformat(), "color": "blue"})
            if l.created_at and (now - l.created_at).total_seconds() < 3 * 86400:
                events.append({"type": "created", "label": "Lead importado", "client": l.nombre, "time": l.created_at.isoformat(), "color": "amber"})
        events.sort(key=lambda e: e["time"], reverse=True)
        events = events[:14]

        # Insights
        insights = []
        if fu_leads:
            insights.append({"type": "warning", "text": f"{len(fu_leads)} leads sin seguimiento hace mas de 3 dias."})
        if ren_7d:
            insights.append({"type": "urgent", "text": f"{len(ren_7d)} renovaciones vencen en los proximos 7 dias."})
        cats = _kategorias(leads)
        if cats:
            best = max(cats, key=lambda c: c["tasa_interes"])
            if best["tasa_interes"] > 0:
                insights.append({"type": "positive", "text": f"'{best['nombre']}' convierte al {best['tasa_interes']}% — tu mejor categoria."})
        if ready:
            insights.append({"type": "action", "text": f"{len(ready)} sitios generados esperan ser publicados."})
        if waiting:
            insights.append({"type": "action", "text": f"{len(waiting)} leads respondieron y esperan tu respuesta."})
        discovered_n = sum(1 for l in leads if l.stage == "discovered")
        if discovered_n:
            insights.append({"type": "info", "text": f"{discovered_n} leads nuevos listos para contactar."})

        # Funnel with conversion % and drop highlighting
        funnel = [
            {"label": "Leads totales",     "value": stats["total"]},
            {"label": "Enviados",          "value": stats["enviados"]},
            {"label": "Respondieron",      "value": stats["respondieron"]},
            {"label": "Interesados",       "value": stats["interesados"]},
            {"label": "Demo generada",     "value": stats["con_web"]},
            {"label": "Sitio live",        "value": stats["con_link"]},
            {"label": "Clientes",          "value": stats["clientes"]},
        ]
        for i, step in enumerate(funnel):
            if i == 0:
                step["pct"] = 100.0
                step["drop"] = 0.0
            else:
                prev = funnel[i - 1]["value"] or 1
                step["pct"] = round(step["value"] / prev * 100, 1)
                step["drop"] = round(100 - step["pct"], 1)
        if len(funnel) > 1:
            bi = max(range(1, len(funnel)), key=lambda i: funnel[i]["drop"])
            funnel[bi]["biggest_drop"] = True

        # Stage cards
        stage_cards = [{"key": s, "label": STAGE_LABELS[s], "count": sum(1 for l in leads if l.stage == s)} for s in STAGE_CHOICES]
        total_n = len(leads) or 1
        for c in stage_cards:
            c["pct"] = round(c["count"] / total_n * 100, 1)

        # Enriched category table
        pago_map: dict = defaultdict(float)
        phone_to_cat = {l.telefono: (l.categoria or "General") for l in leads}
        for p in pagos:
            if p.estado == "pagado" and p.monto and p.moneda == "ARS":
                cat = phone_to_cat.get(p.telefono, "General")
                pago_map[cat] += p.monto
        # Add respondieron per category
        resp_map: dict = defaultdict(int)
        for l in leads:
            if l.estado_respuesta and l.estado_respuesta != "neutral":
                resp_map[l.categoria or "General"] += 1
        cats_enriched = []
        for c in cats:
            c["respondieron"] = resp_map.get(c["nombre"], 0)
            c["revenue"] = pago_map.get(c["nombre"], 0)
            cats_enriched.append(c)

        return jsonify({
            "mrr": mrr, "mrr_prev": mrr_prev, "mrr_delta": mrr - mrr_prev,
            "mrr_ars": mrr_ars, "mrr_usd": mrr_usd,
            "mrr_prev_ars": mrr_prev_ars, "mrr_prev_usd": mrr_prev_usd,
            "clients_count": len(clients), "clients_new": len(new_this_month),
            "follow_ups_count": len(fu_leads),
            "renewals_soon": len(ren_7d), "renewals_overdue": len(ren_overdue),
            "tasks": tasks[:8], "activity": events, "insights": insights[:6],
            "funnel": funnel, "stage_cards": stage_cards, "categorias": cats_enriched,
            "stats": stats,
            "renewal_count": sum(len(v) for v in all_renewals.values()),
        })
    finally:
        session.close()


@app.route("/api/dashboard")
def api_dashboard():
    session = Session()
    try:
        leads = session.query(Lead).all()
        renewals = _renewals(leads)
        return jsonify({
            "stats": _stats(leads),
            "categorias": _kategorias(leads),
            "renewals": renewals,
            "renewal_count": sum(len(v) for v in renewals.values()),
            "stages": {s: sum(1 for l in leads if l.stage == s) for s in STAGE_CHOICES},
            "lastUpdated": datetime.utcnow().isoformat(),
        })
    finally:
        session.close()


# ── Leads API ─────────────────────────────────────────────────

@app.route("/api/leads")
def api_leads():
    session = Session()
    try:
        q = session.query(Lead)

        stage = request.args.get("stage")
        if stage:
            q = q.filter(Lead.stage == stage)

        search = request.args.get("q", "").strip()
        if search:
            like = f"%{search}%"
            q = q.filter(
                Lead.nombre.ilike(like) |
                Lead.telefono.ilike(like) |
                Lead.categoria.ilike(like)
            )

        sort_by = request.args.get("sort", "created_at")
        sort_dir = request.args.get("dir", "desc")
        col_map = {
            "nombre": Lead.nombre, "score": Lead.score,
            "created_at": Lead.created_at, "stage": Lead.stage,
            "categoria": Lead.categoria,
        }
        col = col_map.get(sort_by, Lead.created_at)
        q = q.order_by(col.desc() if sort_dir == "desc" else col.asc())

        page = max(1, int(request.args.get("page", 1)))
        per_page = min(200, int(request.args.get("per_page", 50)))
        total = q.count()
        leads = q.offset((page - 1) * per_page).limit(per_page).all()

        return jsonify({
            "leads": [l.to_dict() for l in leads],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        })
    finally:
        session.close()


@app.route("/api/leads/kanban")
def api_leads_kanban():
    session = Session()
    try:
        leads = session.query(Lead).order_by(Lead.updated_at.desc()).all()
        board = {s: [] for s in STAGE_CHOICES}
        for l in leads:
            stage = l.stage if l.stage in board else "discovered"
            board[stage].append({
                "id": l.id,
                "lead_id": l.lead_id,
                "nombre": l.nombre,
                "telefono": l.telefono,
                "categoria": l.categoria,
                "score": l.score,
                "live_url": l.live_url,
                "estado_respuesta": l.estado_respuesta,
                "stage": l.stage,
                "prioridad": l.prioridad,
                "updated_at": l.updated_at.isoformat() if l.updated_at else None,
            })
        return jsonify({
            "board": board,
            "labels": STAGE_LABELS,
            "counts": {s: len(v) for s, v in board.items()},
        })
    finally:
        session.close()


@app.route("/api/leads/<int:lead_id>", methods=["GET"])
def get_lead(lead_id: int):
    session = Session()
    try:
        lead = session.query(Lead).filter_by(id=lead_id).first()
        if not lead:
            return err("Lead not found", 404)
        d = lead.to_dict()

        # Attach conversation from conversaciones.json if exists
        conv_file = ROOT / "data" / "conversaciones.json"
        if conv_file.exists() and lead.telefono:
            try:
                convs = json.loads(conv_file.read_text())
                digits = "".join(c for c in lead.telefono if c.isdigit())
                if not digits.startswith("54"):
                    digits = "54" + digits
                d["conversacion"] = convs.get(digits, [])
            except Exception:
                d["conversacion"] = []
        return jsonify(d)
    finally:
        session.close()


@app.route("/api/leads/<int:lead_id>", methods=["PUT"])
def update_lead(lead_id: int):
    body = get_json_body()
    session = Session()
    try:
        lead = session.query(Lead).filter_by(id=lead_id).first()
        if not lead:
            return err("Lead not found", 404)

        UPDATABLE = [
            "stage", "notas", "prioridad", "etiquetas", "responsable",
            "estado_respuesta", "fecha_respuesta", "enviado", "fecha_envio",
            "project_path", "live_url", "enviado_links", "fecha_envio_links",
            "fecha_entrega", "fecha_renovacion_web", "fecha_renovacion_hosting",
            "fecha_renovacion_mantenimiento", "nombre", "telefono", "categoria",
            "direccion",
        ]
        for key in UPDATABLE:
            if key not in body:
                continue
            val = body[key]
            if key == "etiquetas" and isinstance(val, list):
                val = json.dumps(val)
            if key in ("fecha_entrega", "fecha_renovacion_web", "fecha_renovacion_hosting",
                       "fecha_renovacion_mantenimiento") and val:
                try:
                    val = date.fromisoformat(str(val)[:10])
                except ValueError:
                    val = None
            if key in ("fecha_respuesta", "fecha_envio", "fecha_envio_links") and val:
                try:
                    val = datetime.fromisoformat(str(val)[:19])
                except ValueError:
                    val = None
            setattr(lead, key, val)

        lead.updated_at = datetime.utcnow()
        session.commit()
        d = lead.to_dict()
        socketio.emit("lead_update", {"lead": d})
        return ok({"lead": d})
    except Exception as e:
        session.rollback()
        return err(str(e))
    finally:
        session.close()


@app.route("/api/leads/<int:lead_id>/stage", methods=["PUT"])
def update_lead_stage(lead_id: int):
    body = get_json_body()
    new_stage = body.get("stage", "")
    if new_stage not in STAGE_CHOICES:
        return err(f"Invalid stage: {new_stage}")

    session = Session()
    try:
        lead = session.query(Lead).filter_by(id=lead_id).first()
        if not lead:
            return err("Lead not found", 404)

        lead.stage = new_stage
        lead.updated_at = datetime.utcnow()

        # Auto-update related fields
        if new_stage == "sent" and not lead.enviado:
            lead.enviado = True
            lead.fecha_envio = datetime.utcnow()
        elif new_stage == "waiting":
            if not lead.estado_respuesta:
                lead.estado_respuesta = "interest"
                lead.fecha_respuesta = datetime.utcnow()
        elif new_stage == "completed" and not lead.fecha_entrega:
            lead.fecha_entrega = date.today()

        session.commit()
        d = lead.to_dict()
        socketio.emit("lead_update", {"lead": d})
        return ok({"lead": d})
    except Exception as e:
        session.rollback()
        return err(str(e))
    finally:
        session.close()


@app.route("/api/leads", methods=["POST"])
def create_lead():
    body = get_json_body()
    if not body.get("nombre") or not body.get("telefono"):
        return err("nombre y telefono son requeridos")

    session = Session()
    try:
        existing = session.query(Lead).filter_by(telefono=body["telefono"]).first()
        if existing:
            return err("Teléfono ya existe"), 409

        lead = Lead(
            lead_id        = str(uuid.uuid4()),
            nombre         = body["nombre"],
            telefono       = body["telefono"],
            categoria      = body.get("categoria", ""),
            direccion      = body.get("direccion", ""),
            ciudad         = body.get("ciudad", "Rosario"),
            score          = int(body.get("score", 0)),
            notas          = body.get("notas", ""),
            stage          = body.get("stage", "discovered"),
            prioridad      = int(body.get("prioridad", 3)),
            live_url       = body.get("live_url") or None,
            fecha_entrega  = body.get("fecha_entrega") or None,
        )
        session.add(lead)
        session.commit()
        return ok({"lead": lead.to_dict()}), 201
    except Exception as e:
        session.rollback()
        return err(str(e))
    finally:
        session.close()


@app.route("/api/leads/<int:lead_id>", methods=["DELETE"])
def delete_lead(lead_id: int):
    session = Session()
    try:
        lead = session.query(Lead).filter_by(id=lead_id).first()
        if not lead:
            return err("Lead not found", 404)
        session.delete(lead)
        session.commit()
        socketio.emit("lead_deleted", {"lead_id": lead_id})
        return ok()
    except Exception as e:
        session.rollback()
        return err(str(e))
    finally:
        session.close()


# ── Pipeline API ──────────────────────────────────────────────

@app.route("/api/pipeline/jobs")
def api_pipeline_jobs():
    return jsonify({"jobs": job_manager.get_all_jobs()})


@app.route("/api/pipeline/jobs/<job_id>")
def api_pipeline_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        return err("Job not found", 404)
    return jsonify({"job": job})


@app.route("/api/pipeline/start/<stage>", methods=["POST"])
def api_pipeline_start(stage: str):
    body = request.get_json(silent=True) or {}

    # Check for already-running job for this stage
    active = job_manager.get_active_job_for_stage(stage)
    if active:
        return err(f"Stage '{stage}' already running as job {active['job_id']}", 409)

    STAGES = {
        "scrape":         lambda jid: stage_scrape(jid, body.get("queries"), body.get("account", "both")),
        "discover":       lambda jid: stage_discover(jid, body.get("dataset_file")),
        "send":           lambda jid: stage_send(jid, body.get("limit")),
        "generate_webs":  lambda jid: stage_generate_webs(jid, body.get("lead_ids")),
        "deploy":         lambda jid: stage_deploy(jid, body.get("lead_ids")),
        "send_links":     lambda jid: stage_send_links(jid, body.get("lead_ids")),
        "followup":       lambda jid: stage_followup(jid, body.get("lead_ids", []), body.get("message_index", 0)),
        "social_post":    lambda jid: stage_social_post(jid, body.get("lead_ids", []), body.get("post_type", "servicio")),
    }

    if stage not in STAGES:
        return err(f"Unknown stage: {stage}. Valid: {list(STAGES)}")

    job_id = job_manager.create_and_start(stage, STAGES[stage])
    return ok({"job_id": job_id, "stage": stage})


@app.route("/api/pipeline/stop/<job_id>", methods=["POST"])
def api_pipeline_stop(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        return err("Job not found", 404)
    job_manager.stop(job_id)
    return ok()


@app.route("/api/pipeline/pause/<job_id>", methods=["POST"])
def api_pipeline_pause(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        return err("Job not found", 404)
    job_manager.pause(job_id)
    return ok()


@app.route("/api/pipeline/resume/<job_id>", methods=["POST"])
def api_pipeline_resume(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        return err("Job not found", 404)
    job_manager.resume(job_id)
    return ok()


@app.route("/api/pipeline/stages")
def api_pipeline_stages():
    session = Session()
    try:
        counts = {s: session.query(Lead).filter(Lead.stage == s).count() for s in STAGE_CHOICES}
        jobs = job_manager.get_all_jobs()
        active = {}
        for j in jobs:
            if j["status"] in ("running", "paused"):
                active[j["stage"]] = j

        return jsonify({
            "stages": [
                {
                    "key": s,
                    "label": STAGE_LABELS[s],
                    "count": counts[s],
                    "active_job": active.get(s),
                }
                for s in STAGE_CHOICES
            ]
        })
    finally:
        session.close()


# ── Analytics API ─────────────────────────────────────────────

@app.route("/api/analytics")
def api_analytics():
    session = Session()
    try:
        leads = session.query(Lead).all()
        stats = _stats(leads)

        # Funnel
        funnel = [
            {"label": "Total leads",      "value": stats["total"]},
            {"label": "Mensajes enviados","value": stats["enviados"]},
            {"label": "Respondieron",     "value": stats["respondieron"]},
            {"label": "Interesados",      "value": stats["interesados"]},
            {"label": "Webs generadas",   "value": stats["con_web"]},
            {"label": "Sitios live",      "value": stats["con_link"]},
            {"label": "Links enviados",   "value": stats["links_enviados"]},
            {"label": "Clientes",         "value": stats["clientes"]},
        ]

        # Timeline (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        timeline_leads = [
            l for l in leads
            if l.created_at and l.created_at >= thirty_days_ago
        ]
        daily: dict[str, int] = defaultdict(int)
        for l in timeline_leads:
            day = l.created_at.strftime("%Y-%m-%d")
            daily[day] += 1
        today = date.today()
        timeline = [
            {"date": (today - timedelta(days=i)).isoformat(), "count": 0}
            for i in range(29, -1, -1)
        ]
        for item in timeline:
            item["count"] = daily.get(item["date"], 0)

        # Stage distribution
        stage_dist = [
            {"stage": s, "label": STAGE_LABELS[s], "count": sum(1 for l in leads if l.stage == s)}
            for s in STAGE_CHOICES
        ]

        # Category breakdown
        categorias = _kategorias(leads)

        # Response distribution
        responses = defaultdict(int)
        for l in leads:
            if l.estado_respuesta:
                responses[l.estado_respuesta] += 1

        # Average time between stages (simplified)
        avg_send_duration = None
        sent_leads = [l for l in leads if l.enviado and l.fecha_envio and l.created_at]
        if sent_leads:
            deltas = [(l.fecha_envio - l.created_at).total_seconds() / 3600 for l in sent_leads]
            avg_send_duration = round(sum(deltas) / len(deltas), 1)

        return jsonify({
            "stats": stats,
            "funnel": funnel,
            "timeline": timeline,
            "stage_distribution": stage_dist,
            "categorias": categorias,
            "responses": dict(responses),
            "avg_hours_to_send": avg_send_duration,
        })
    finally:
        session.close()


# ── Dólar API ─────────────────────────────────────────────────

_dolar_cache: dict = {"data": None, "ts": None}

@app.route("/api/dolar")
def api_dolar():
    import urllib.request as _urlreq
    import json as _json
    now = datetime.utcnow()
    if _dolar_cache["data"] and _dolar_cache["ts"] and (now - _dolar_cache["ts"]).total_seconds() < 1800:
        return jsonify(_dolar_cache["data"])
    try:
        req = _urlreq.Request(
            "https://dolarapi.com/v1/dolares/oficial",
            headers={"User-Agent": "BinarioCRM/1.0"},
        )
        with _urlreq.urlopen(req, timeout=5) as r:
            raw = _json.loads(r.read())
        mid = round((raw["compra"] + raw["venta"]) / 2, 2)
        data = {
            "compra": raw["compra"],
            "venta": raw["venta"],
            "mid": mid,
            "updated_at": raw.get("fechaActualizacion", ""),
        }
        _dolar_cache["data"] = data
        _dolar_cache["ts"] = now
        return jsonify(data)
    except Exception as exc:
        if _dolar_cache["data"]:
            return jsonify({**_dolar_cache["data"], "stale": True})
        return jsonify({"error": str(exc), "mid": None}), 503


# ── Finanzas API ──────────────────────────────────────────────

@app.route("/api/finanzas")
def api_finanzas():
    session = Session()
    try:
        pagos = session.query(Finanza).order_by(Finanza.created_at.desc()).all()
        pagados    = [p for p in pagos if p.estado in ("pagado", "parcial")]
        pendientes = [p for p in pagos if p.estado == "pendiente"]
        total_ars = sum(p.monto for p in pagados if p.moneda == "ARS" and p.monto)
        total_usd = sum(p.monto for p in pagados if p.moneda == "USD" and p.monto)
        pend_ars  = sum(p.monto for p in pendientes if p.moneda == "ARS" and p.monto)
        pend_usd  = sum(p.monto for p in pendientes if p.moneda == "USD" and p.monto)
        return jsonify({
            "pagos": [p.to_dict() for p in pagos],
            "stats": {
                "total_clientes": len(pagos),
                "clientes_pagados": len(pagados),
                "clientes_pendientes": len(pendientes),
                "total_ars": total_ars,
                "total_usd": total_usd,
                "pendiente_ars": pend_ars,
                "pendiente_usd": pend_usd,
                "promedio_ars": round(total_ars / len(pagados)) if pagados else 0,
            },
        })
    finally:
        session.close()


@app.route("/api/finanzas/pago", methods=["POST"])
def create_pago():
    body = get_json_body()
    session = Session()
    try:
        fecha = None
        if body.get("fecha"):
            try:
                fecha = date.fromisoformat(str(body["fecha"])[:10])
            except ValueError:
                fecha = date.today()

        # Link to lead if possible
        lead_id = None
        tel = body.get("telefono", "")
        if tel:
            lead = session.query(Lead).filter_by(telefono=tel).first()
            if lead:
                lead_id = lead.id

        # Update or create (force_create bypasses upsert — used for monthly payment registration)
        force_create = body.get("force_create", False)
        existing = None
        if tel and not force_create:
            existing = session.query(Finanza).filter_by(telefono=tel).first()

        if existing:
            existing.nombre  = body.get("nombre", existing.nombre)
            existing.monto   = float(body.get("monto", existing.monto or 0))
            existing.moneda  = body.get("moneda", existing.moneda)
            existing.estado  = body.get("estado", existing.estado)
            existing.fecha   = fecha or existing.fecha
            existing.servicio = body.get("servicio", existing.servicio)
            existing.notas   = body.get("notas", existing.notas)
            pago = existing
        else:
            pago = Finanza(
                lead_id  = lead_id,
                nombre   = body.get("nombre", ""),
                telefono = tel,
                monto    = float(body.get("monto", 0)),
                moneda   = body.get("moneda", "ARS"),
                estado   = body.get("estado", "pendiente"),
                fecha    = fecha or date.today(),
                servicio = body.get("servicio", "Sitio web"),
                notas    = body.get("notas", ""),
            )
            session.add(pago)

        session.commit()
        return ok({"pago": pago.to_dict()})
    except Exception as e:
        session.rollback()
        return err(str(e))
    finally:
        session.close()


@app.route("/api/finanzas/pago/<int:pago_id>", methods=["PUT"])
def update_pago(pago_id: int):
    body = get_json_body()
    session = Session()
    try:
        pago = session.query(Finanza).filter_by(id=pago_id).first()
        if not pago:
            return err("Pago no encontrado", 404)
        if "monto" in body:
            pago.monto = float(body["monto"])
        if "moneda" in body:
            pago.moneda = body["moneda"]
        if "estado" in body:
            pago.estado = body["estado"]
        if "notas" in body:
            pago.notas = body["notas"]
        if body.get("fecha"):
            try:
                pago.fecha = date.fromisoformat(str(body["fecha"])[:10])
            except ValueError:
                pass
        session.commit()
        return ok({"pago": pago.to_dict()})
    except Exception as e:
        session.rollback()
        return err(str(e))
    finally:
        session.close()


@app.route("/api/finanzas/pago/<int:pago_id>", methods=["DELETE"])
def delete_pago(pago_id: int):
    session = Session()
    try:
        pago = session.query(Finanza).filter_by(id=pago_id).first()
        if not pago:
            return err("Not found", 404)
        session.delete(pago)
        session.commit()
        return ok()
    except Exception as e:
        session.rollback()
        return err(str(e))
    finally:
        session.close()


# ── Templates API ─────────────────────────────────────────────

@app.route("/api/templates")
def api_templates():
    session = Session()
    try:
        tipo = request.args.get("tipo")
        q = session.query(Template)
        if tipo:
            q = q.filter(Template.tipo == tipo)
        templates = q.order_by(Template.id).all()
        return jsonify({"templates": [t.to_dict() for t in templates]})
    finally:
        session.close()


@app.route("/api/templates", methods=["POST"])
def create_template():
    body = get_json_body()
    session = Session()
    try:
        t = Template(
            nombre   = body.get("nombre", ""),
            contenido = body.get("contenido", ""),
            tipo     = body.get("tipo", "outreach"),
            activo   = body.get("activo", True),
        )
        session.add(t)
        session.commit()
        return ok({"template": t.to_dict()}), 201
    except Exception as e:
        session.rollback()
        return err(str(e))
    finally:
        session.close()


@app.route("/api/templates/<int:tid>", methods=["PUT"])
def update_template(tid: int):
    body = get_json_body()
    session = Session()
    try:
        t = session.query(Template).filter_by(id=tid).first()
        if not t:
            return err("Not found", 404)
        for key in ("nombre", "contenido", "tipo", "activo"):
            if key in body:
                setattr(t, key, body[key])
        t.updated_at = datetime.utcnow()
        session.commit()
        return ok({"template": t.to_dict()})
    except Exception as e:
        session.rollback()
        return err(str(e))
    finally:
        session.close()


@app.route("/api/templates/<int:tid>", methods=["DELETE"])
def delete_template(tid: int):
    session = Session()
    try:
        t = session.query(Template).filter_by(id=tid).first()
        if not t:
            return err("Not found", 404)
        session.delete(t)
        session.commit()
        return ok()
    except Exception as e:
        session.rollback()
        return err(str(e))
    finally:
        session.close()


# ── Niches API ────────────────────────────────────────────────

@app.route("/api/niches")
def api_niches():
    from config import config
    niches = {}
    for key, val in config.NICHES.items():
        niches[key] = {
            "label": key.replace("_", " ").capitalize(),
            "queries": val.get("queries", []),
        }
    return jsonify({"niches": niches})


# ── Config API ────────────────────────────────────────────────

@app.route("/api/config")
def api_config():
    session = Session()
    try:
        rows = session.query(AppConfig).all()
        return jsonify({"config": {r.key: r.value for r in rows}})
    finally:
        session.close()


@app.route("/api/config", methods=["PUT"])
def update_config():
    body = get_json_body()
    session = Session()
    try:
        for key, val in body.items():
            row = session.query(AppConfig).filter_by(key=key).first()
            if row:
                row.value = str(val)
            else:
                session.add(AppConfig(key=key, value=str(val)))
        session.commit()
        return ok()
    except Exception as e:
        session.rollback()
        return err(str(e))
    finally:
        session.close()


# ── Errors API ────────────────────────────────────────────────

@app.route("/api/errors")
def api_errors():
    session = Session()
    try:
        errors = (
            session.query(ErrorLog)
            .order_by(ErrorLog.created_at.desc())
            .limit(200)
            .all()
        )
        return jsonify({"errors": [e.to_dict() for e in errors]})
    finally:
        session.close()


# ── Websites API ──────────────────────────────────────────────

@app.route("/api/websites")
def api_websites():
    from config import config
    session = Session()
    try:
        leads = (
            session.query(Lead)
            .filter(Lead.project_path != None)
            .order_by(Lead.updated_at.desc())
            .all()
        )
        sites = []
        for l in leads:
            p = Path(l.project_path)
            has_index = (p / "index.html").exists() if p.exists() else False
            sites.append({
                "lead_id": l.id,
                "nombre": l.nombre,
                "project_path": l.project_path,
                "live_url": l.live_url,
                "has_index": has_index,
                "stage": l.stage,
                "website_version": l.website_version,
                "website_duration": l.website_duration,
                "updated_at": l.updated_at.isoformat() if l.updated_at else None,
            })
        return jsonify({"websites": sites})
    finally:
        session.close()


@app.route("/api/websites/<int:lead_id>/regenerate", methods=["POST"])
def regenerate_website(lead_id: int):
    body = request.get_json(silent=True) or {}
    active = job_manager.get_active_job_for_stage("generate_webs")
    if active:
        return err("Ya hay una generación en curso", 409)

    job_id = job_manager.create_and_start(
        "generate_webs",
        lambda jid: stage_generate_webs(jid, [lead_id]),
    )
    return ok({"job_id": job_id})


# ── Clientes API ──────────────────────────────────────────────

@app.route("/api/clientes")
def api_clientes():
    session = Session()
    try:
        clientes = (
            session.query(Lead)
            .filter(Lead.fecha_entrega != None)
            .order_by(Lead.fecha_entrega.desc())
            .all()
        )
        return jsonify({"clientes": [l.to_dict() for l in clientes]})
    finally:
        session.close()


@app.route("/api/generate-webs/candidates")
def api_generate_webs_candidates():
    """Returns all contacted leads for the web generation selection modal."""
    session = Session()
    try:
        candidates = (
            session.query(Lead)
            .order_by(Lead.fecha_envio.desc(), Lead.created_at.desc())
            .all()
        )
        return jsonify({
            "candidates": [l.to_dict() for l in candidates],
            "total": len(candidates),
        })
    finally:
        session.close()


@app.route("/api/social/test")
def api_social_test():
    """Test Social Media Agent connections."""
    try:
        from modules.social_agent import test_connections
        results = test_connections()
        return ok({"results": {k: {"status": s, "msg": m} for k, (s, m) in results.items()}})
    except Exception as e:
        return err(str(e))


@app.route("/api/social/generate", methods=["POST"])
def api_social_generate():
    """Generate a post preview without publishing."""
    body = get_json_body()
    lead_id = body.get("lead_id")
    post_type = body.get("post_type", "servicio")
    session = Session()
    try:
        lead = session.query(Lead).filter_by(id=lead_id).first() if lead_id else None
        client = lead.to_dict() if lead else {
            "nombre": body.get("nombre", "Demo Negocio"),
            "categoria": body.get("categoria", "negocio"),
            "ciudad": "Rosario",
        }
    finally:
        session.close()
    try:
        from modules.social_agent import generate_post_content, get_image_url, _niche_key
        content = generate_post_content(client, post_type)
        niche = _niche_key(client.get("categoria", ""))
        image_url = get_image_url(content.get("image_query", "business"), niche)
        return ok({"content": content, "image_url": image_url})
    except Exception as e:
        return err(str(e))


@app.route("/api/followup/candidates")
def api_followup_candidates():
    """Returns all contacted leads for followup selection."""
    session = Session()
    try:
        candidates = (
            session.query(Lead)
            .filter(Lead.enviado == True)
            .order_by(Lead.fecha_envio.desc())
            .all()
        )
        return jsonify({
            "candidates": [l.to_dict() for l in candidates],
            "total": len(candidates),
            "messages": FOLLOWUP_MESSAGES,
        })
    finally:
        session.close()


@app.route("/api/send-links/candidates")
def api_send_links_candidates():
    """Returns all leads with a live URL that haven't had their link sent yet."""
    session = Session()
    try:
        candidates = (
            session.query(Lead)
            .filter(Lead.enviado == True, Lead.live_url != None)
            .order_by(Lead.updated_at.desc())
            .all()
        )
        return jsonify({
            "candidates": [l.to_dict() for l in candidates],
            "total": len(candidates),
        })
    finally:
        session.close()


# ── File editor API ────────────────────────────────────────────

@app.route("/api/files/read", methods=["POST"])
def api_file_read():
    body = get_json_body()
    path = body.get("path", "")
    if not path:
        return err("path required")
    try:
        p = Path(path)
        if not p.exists():
            return err("File not found", 404)
        if not p.is_file():
            return err("Not a file", 400)
        content = p.read_text(encoding="utf-8", errors="replace")
        return ok({"content": content, "path": str(p), "size": p.stat().st_size})
    except Exception as e:
        return err(str(e))


@app.route("/api/files/write", methods=["POST"])
def api_file_write():
    body = get_json_body()
    path = body.get("path", "")
    content = body.get("content", "")
    if not path:
        return err("path required")
    try:
        p = Path(path)
        p.write_text(content, encoding="utf-8")
        return ok({"path": str(p), "size": p.stat().st_size})
    except Exception as e:
        return err(str(e))


# ── Migration & utilities ─────────────────────────────────────

@app.route("/api/migrate", methods=["POST"])
def api_migrate():
    from config import config
    csv_path = config.STATUS_FILE
    try:
        n = migrate_from_csv(csv_path)
        return ok({"imported": n, "message": f"{n} leads importados desde estado.csv"})
    except Exception as e:
        return err(str(e))


@app.route("/api/renewals")
def api_renewals():
    session = Session()
    try:
        leads = session.query(Lead).filter(Lead.fecha_entrega != None).all()
        return jsonify(_renewals(leads))
    finally:
        session.close()


@app.route("/api/dataset/status")
def api_dataset_status():
    from config import config
    ds = config.DATASET_FILE
    if not ds.exists():
        return jsonify({"exists": False})
    stat = ds.stat()
    try:
        import json as _json
        with open(ds) as f:
            data = _json.load(f)
        count = len(data) if isinstance(data, list) else 1
    except Exception:
        count = 0
    return jsonify({
        "exists": True,
        "path": str(ds),
        "size_kb": round(stat.st_size / 1024, 1),
        "count": count,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    })


# ── WhatsApp Inbound ──────────────────────────────────────────

_NTFY_ICONS = {
    "positive_intent": "🔥",
    "interest":        "👀",
    "price_request":   "💰",
    "info_request":    "❓",
    "follow_up":       "🔄",
    "rejection":       "❌",
    "neutral":         "💬",
}

_NTFY_PRIORITY = {
    "positive_intent": "urgent",
    "interest":        "high",
    "price_request":   "high",
    "info_request":    "default",
    "follow_up":       "default",
    "rejection":       "low",
    "neutral":         "min",
}


def _ntfy(title: str, body: str, category: str = "neutral"):
    from config import config
    import requests as _req
    topic = config.NTFY_TOPIC
    if not topic:
        return
    def _send():
        try:
            _req.post(
                f"{config.NTFY_URL}/{topic}",
                data=body.encode("utf-8"),
                headers={
                    "Title":    title,
                    "Priority": _NTFY_PRIORITY.get(category, "default"),
                    "Tags":     "whatsapp," + category,
                },
                timeout=5,
            )
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()


@app.route("/wa-event", methods=["POST"])
def wa_event():
    """Receive events from the Node.js WhatsApp bridge."""
    event = request.get_json(force=True, silent=True) or {}
    if event.get("type") != "message":
        return jsonify({"status": "ack", "type": event.get("type")})

    phone = event.get("phone", "")
    text  = event.get("message", "")
    if not phone:
        return jsonify({"status": "ignored", "reason": "no_phone"})

    from modules.classifier import classify
    result = classify(text)

    _PRIO = {
        "": 0, "neutral": 1, "info_request": 2, "follow_up": 2,
        "price_request": 3, "interest": 4, "positive_intent": 5, "rejection": 6,
    }

    def _norm(p: str) -> str:
        digits = "".join(c for c in (p or "") if c.isdigit())
        return digits if digits.startswith("54") else "54" + digits

    norm_in = _norm(phone)
    session = Session()
    try:
        lead = next(
            (l for l in session.query(Lead).filter(Lead.enviado == True).all()
             if _norm(l.telefono or "") == norm_in),
            None,
        )
        if lead is None:
            return jsonify({"status": "stored", "linked": False, "category": result.category})

        current = lead.estado_respuesta or ""
        if _PRIO.get(result.category, 0) >= _PRIO.get(current, 0):
            lead.estado_respuesta = result.category
            lead.fecha_respuesta = datetime.utcnow()
            if result.category in ("interest", "positive_intent", "price_request", "follow_up"):
                if lead.stage == "sent":
                    lead.stage = "waiting"
            session.commit()
            socketio.emit("lead_update", {"lead": lead.to_dict()})

            icon = _NTFY_ICONS.get(result.category, "💬")
            nombre = lead.nombre or phone
            _ntfy(
                title=f"{icon} {nombre} contestó",
                body=text[:200] if text else "(sin texto)",
                category=result.category,
            )

        return jsonify({"status": "processed", "category": result.category, "confidence": result.confidence})
    except Exception as exc:
        session.rollback()
        return jsonify({"status": "error", "error": str(exc)}), 500
    finally:
        session.close()


# ── WhatsApp Response Sync ────────────────────────────────────

def _sync_responses_from_bridge() -> dict:
    """
    Pull WhatsApp responses persisted by the bridge (wa_responses.json)
    and update leads in SQLite. Safe to call even when bridge is offline.
    Works in two modes:
      - Bridge running: GET /responses?since=<last_sync> via HTTP
      - Bridge offline: read wa_responses.json directly
    Returns {"synced": N, "total": M}
    """
    import requests as _req
    from config import config
    from modules.classifier import classify

    _PRIO = {
        "": 0, "neutral": 1, "info_request": 2, "follow_up": 2,
        "price_request": 3, "interest": 4, "positive_intent": 5, "rejection": 6,
    }

    # Retrieve last sync timestamp from DB config
    session = Session()
    try:
        cfg_row = session.query(AppConfig).filter_by(key="wa_last_sync").first()
        last_sync = cfg_row.value if cfg_row else "1970-01-01T00:00:00Z"
    finally:
        session.close()

    # Try HTTP first, fall back to reading the file directly
    _headers = {"X-Bridge-Secret": config.BRIDGE_SECRET} if config.BRIDGE_SECRET else {}
    responses = []
    try:
        r = _req.get(
            f"{config.WA_BRIDGE_URL}/responses",
            params={"since": last_sync},
            headers=_headers,
            timeout=4,
        )
        responses = r.json().get("responses", [])
    except Exception:
        # Bridge offline — read file directly
        rf = config.WA_RESPONSES_FILE
        if rf.exists():
            try:
                with open(rf, encoding="utf-8") as f:
                    all_resp = json.load(f)
                responses = [r for r in all_resp if r.get("timestamp", "") > last_sync]
            except Exception:
                pass

    if not responses:
        return {"synced": 0, "total": 0}

    session = Session()
    updated = 0
    try:
        all_sent = session.query(Lead).filter(Lead.enviado == True).all()

        for event in responses:
            phone = event.get("phone", "")
            text  = event.get("message", "")
            ts    = event.get("timestamp", "")
            if not phone:
                continue

            result = classify(text)

            # Match by last 8 digits (strips country + area codes)
            suffix = "".join(c for c in phone if c.isdigit())[-8:]
            lead = next(
                (l for l in all_sent
                 if "".join(c for c in (l.telefono or "") if c.isdigit()).endswith(suffix)),
                None,
            )
            if not lead:
                continue

            current = lead.estado_respuesta or ""
            if _PRIO.get(result.category, 0) >= _PRIO.get(current, 0):
                lead.estado_respuesta = result.category
                lead.fecha_respuesta  = ts
                if result.category in ("interest", "positive_intent", "price_request", "follow_up"):
                    if lead.stage == "sent":
                        lead.stage = "waiting"
                updated += 1

        session.commit()

        # Emit socket updates for changed leads
        for lead in all_sent:
            if lead.estado_respuesta:
                socketio.emit("lead_update", {"lead": lead.to_dict()})

        # Persist last sync time
        session2 = Session()
        try:
            cfg = session2.query(AppConfig).filter_by(key="wa_last_sync").first()
            if not cfg:
                cfg = AppConfig(key="wa_last_sync", value="")
                session2.add(cfg)
            cfg.value = datetime.utcnow().isoformat() + "Z"
            session2.commit()
        finally:
            session2.close()

    except Exception:
        session.rollback()
    finally:
        session.close()

    return {"synced": updated, "total": len(responses)}


@app.route("/api/sync-responses", methods=["POST"])
def api_sync_responses():
    """Sync WhatsApp responses from bridge — call on demand or at startup."""
    try:
        result = _sync_responses_from_bridge()
        return ok(result)
    except Exception as e:
        return err(str(e))


# ── SocketIO Events ───────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    emit("connected", {"status": "ok", "time": datetime.utcnow().isoformat()})
    jobs = job_manager.get_all_jobs()
    emit("jobs_state", {"jobs": jobs})


@socketio.on("subscribe_job")
def on_subscribe_job(data):
    job_id = data.get("job_id")
    job = job_manager.get_job(job_id)
    if job:
        emit("job_update", {"job": job})


# ── Bootstrap ─────────────────────────────────────────────────

def _bootstrap():
    from config import config
    config.ensure_directories()
    init_db()

    # Auto-migrate CSV if DB is empty and CSV exists
    session = Session()
    try:
        count = session.query(Lead).count()
    finally:
        session.close()

    if count == 0 and config.STATUS_FILE.exists():
        try:
            n = migrate_from_csv(config.STATUS_FILE)
            if n:
                print(f"✅ Auto-migrated {n} leads from estado.csv")
        except Exception as e:
            print(f"⚠️  Auto-migrate failed: {e}")

    # Sync WhatsApp responses received while the CRM was offline
    def _deferred_sync():
        import time as _t
        _t.sleep(3)  # wait for SocketIO to be ready
        try:
            result = _sync_responses_from_bridge()
            if result["total"] > 0:
                print(f"📱 WA sync: {result['synced']} respuestas nuevas de {result['total']} totales")
        except Exception as exc:
            print(f"⚠️  WA sync failed: {exc}")

    threading.Thread(target=_deferred_sync, daemon=True).start()


_bootstrap()


if __name__ == "__main__":
    socketio.run(app, debug=False, host="0.0.0.0", port=5000, use_reloader=False)
