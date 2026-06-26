#!/usr/bin/env python3
"""
Binario Websites — Production Dashboard
Flask-SocketIO backend with SQLite via SQLAlchemy.
"""

import json
import sys
import traceback
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
app.config["SECRET_KEY"] = "binario-2024-secret"
app.config["JSON_SORT_KEYS"] = False

socketio = SocketIO(
    app,
    async_mode="eventlet",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
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
    stage_deploy, stage_send_links, stage_scrape,
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
            lead_id   = str(uuid.uuid4()),
            nombre    = body["nombre"],
            telefono  = body["telefono"],
            categoria = body.get("categoria", ""),
            direccion = body.get("direccion", ""),
            ciudad    = body.get("ciudad", "Rosario"),
            score     = int(body.get("score", 0)),
            notas     = body.get("notas", ""),
            stage     = body.get("stage", "discovered"),
            prioridad = int(body.get("prioridad", 3)),
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
        "scrape":         lambda jid: stage_scrape(jid),
        "discover":       lambda jid: stage_discover(jid, body.get("dataset_file")),
        "send":           lambda jid: stage_send(jid, body.get("limit")),
        "generate_webs":  lambda jid: stage_generate_webs(jid, body.get("lead_ids")),
        "deploy":         lambda jid: stage_deploy(jid, body.get("lead_ids")),
        "send_links":     lambda jid: stage_send_links(jid, body.get("lead_ids")),
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


# ── Finanzas API ──────────────────────────────────────────────

@app.route("/api/finanzas")
def api_finanzas():
    session = Session()
    try:
        pagos = session.query(Finanza).order_by(Finanza.created_at.desc()).all()
        pagados   = [p for p in pagos if p.estado == "pagado"]
        pendientes = [p for p in pagos if p.estado in ("pendiente", "parcial")]
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

        # Update or create
        existing = None
        if tel:
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


_bootstrap()


if __name__ == "__main__":
    socketio.run(app, debug=False, host="0.0.0.0", port=5000, use_reloader=False)
