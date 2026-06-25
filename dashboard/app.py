#!/usr/bin/env python3
"""
Dashboard Flask backend — LeadGen Amoblamientos Rosario

Serves the CRM dashboard with:
  - Lead management (estado.csv)
  - Finance tracking (finanzas.json)
  - Renewal alerts
  - Conversation history
  - Pipeline analytics
"""

import csv
import json
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path

from flask import Flask, jsonify, request, render_template, abort

# Dynamic root resolution — always works regardless of folder name
ROOT = Path(__file__).parent.parent.resolve()
DATA_DIR = ROOT / "data"

app = Flask(__name__, template_folder="templates", static_folder="static")

STATUS_FILE = DATA_DIR / "estado.csv"
FINANZAS_FILE = DATA_DIR / "finanzas.json"
CONVERSACIONES_FILE = DATA_DIR / "conversaciones.json"


# ── Data I/O ──────────────────────────────────────────────────────────────────

def cargar_datos() -> list[dict]:
    if not STATUS_FILE.exists():
        return []
    with open(STATUS_FILE, "r", encoding="utf-8") as f:
        return [dict(row) for row in csv.DictReader(f)]


def guardar_datos(datos: list[dict]):
    if not datos:
        return
    with open(STATUS_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(datos[0].keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(datos)


def cargar_finanzas() -> dict:
    if not FINANZAS_FILE.exists():
        return {"pagos": [], "config": {"precio_sugerido": 50000, "moneda_default": "ARS"}}
    with open(FINANZAS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_finanzas(data: dict):
    with open(FINANZAS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def cargar_conversaciones() -> dict:
    if not CONVERSACIONES_FILE.exists():
        return {}
    try:
        with open(CONVERSACIONES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


# ── Stats helpers ─────────────────────────────────────────────────────────────

def get_stats(datos: list[dict]) -> dict:
    total = len(datos)
    enviados = sum(1 for r in datos if r.get("enviado", "").upper() == "SI")
    respondieron = sum(1 for r in datos if r.get("estado_respuesta", "") not in ("", "neutral"))
    interesados = sum(
        1 for r in datos
        if r.get("estado_respuesta", "") in ("interest", "positive_intent", "price_request", "follow_up")
    )
    rechazados = sum(1 for r in datos if r.get("estado_respuesta", "") == "rejection")
    con_web = sum(1 for r in datos if r.get("project_path"))
    con_link = sum(1 for r in datos if r.get("live_url"))
    links_enviados = sum(1 for r in datos if r.get("enviado_links", "").upper() == "SI")
    clientes = sum(1 for r in datos if r.get("fecha_entrega"))

    return {
        "total": total,
        "enviados": enviados,
        "respondieron": respondieron,
        "interesados": interesados,
        "rechazados": rechazados,
        "con_web": con_web,
        "con_link": con_link,
        "links_enviados": links_enviados,
        "clientes": clientes,
        "tasa_envio": round(enviados / total * 100, 1) if total else 0,
        "tasa_respuesta": round(respondieron / enviados * 100, 1) if enviados else 0,
        "tasa_interes": round(interesados / respondieron * 100, 1) if respondieron else 0,
        "tasa_web": round(con_web / interesados * 100, 1) if interesados else 0,
        "tasa_deploy": round(con_link / con_web * 100, 1) if con_web else 0,
    }


def get_categorias(datos: list[dict]) -> list[dict]:
    cats: dict[str, dict] = defaultdict(lambda: {"total": 0, "enviados": 0, "interesados": 0, "con_link": 0})
    for r in datos:
        cat = r.get("categoria") or "General"
        cats[cat]["total"] += 1
        if r.get("enviado", "").upper() == "SI":
            cats[cat]["enviados"] += 1
        if r.get("estado_respuesta", "") in ("interest", "positive_intent", "price_request"):
            cats[cat]["interesados"] += 1
        if r.get("live_url"):
            cats[cat]["con_link"] += 1
    result = [
        {
            "nombre": cat,
            "total": d["total"],
            "enviados": d["enviados"],
            "interesados": d["interesados"],
            "convertidos": d["con_link"],
            "tasa_envio": round(d["enviados"] / d["total"] * 100, 1) if d["total"] else 0,
            "tasa_interes": round(d["interesados"] / d["enviados"] * 100, 1) if d["enviados"] else 0,
        }
        for cat, d in cats.items()
    ]
    return sorted(result, key=lambda x: -x["total"])[:8]


def _advance_monthly(fecha: date, hoy: date) -> date:
    """Return the next upcoming monthly occurrence of a given day-of-month."""
    import calendar
    while fecha <= hoy:
        year = fecha.year + (fecha.month // 12)
        month = (fecha.month % 12) + 1
        last_day = calendar.monthrange(year, month)[1]
        fecha = fecha.replace(year=year, month=month, day=min(fecha.day, last_day))
    return fecha


def get_renewals(datos: list[dict]) -> dict:
    """Return renewal alerts grouped by urgency window."""
    hoy = date.today()
    windows = {"7d": [], "30d": [], "60d": []}
    campos = {
        "fecha_renovacion_web": ("Web", False),
        "fecha_renovacion_hosting": ("Hosting", False),
        "fecha_renovacion_mantenimiento": ("Mantenimiento", True),  # True = monthly auto-advance
    }

    for r in datos:
        for campo, (label, mensual) in campos.items():
            fecha_str = r.get(campo, "")
            if not fecha_str:
                continue
            try:
                fecha = datetime.strptime(fecha_str[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            if mensual and fecha <= hoy:
                fecha = _advance_monthly(fecha, hoy)
            dias = (fecha - hoy).days
            item = {
                "nombre": r.get("nombre", ""),
                "telefono": r.get("telefono", ""),
                "tipo": label,
                "fecha": fecha.isoformat(),
                "dias": dias,
                "vencido": dias < 0,
            }
            if dias < 0 or dias <= 7:
                windows["7d"].append(item)
            elif dias <= 30:
                windows["30d"].append(item)
            elif dias <= 60:
                windows["60d"].append(item)

    for k in windows:
        windows[k].sort(key=lambda x: x["dias"])
    return windows


def get_stats_finanzas(finanzas: dict) -> dict:
    pagos = finanzas.get("pagos", [])
    pagados = [p for p in pagos if p.get("estado") == "pagado"]
    pendientes = [p for p in pagos if p.get("estado") in ("pendiente", "parcial")]
    total_ars = sum(p["monto"] for p in pagados if p.get("moneda") == "ARS")
    total_usd = sum(p["monto"] for p in pagados if p.get("moneda") == "USD")
    pendiente_ars = sum(p["monto"] for p in pendientes if p.get("moneda") == "ARS")
    pendiente_usd = sum(p["monto"] for p in pendientes if p.get("moneda") == "USD")
    return {
        "total_clientes": len(pagos),
        "clientes_pagados": len(pagados),
        "clientes_pendientes": len(pendientes),
        "total_ars": total_ars,
        "total_usd": total_usd,
        "pendiente_ars": pendiente_ars,
        "pendiente_usd": pendiente_usd,
        "promedio_ars": round(total_ars / len(pagados)) if pagados else 0,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/datos")
def api_datos():
    datos = cargar_datos()
    renewals = get_renewals(datos)
    total_alertas = sum(len(v) for v in renewals.values())
    return jsonify(
        {
            "stats": get_stats(datos),
            "categorias": get_categorias(datos),
            "leads": datos,
            "renewals": renewals,
            "renewal_count": total_alertas,
            "lastUpdated": datetime.now().isoformat(),
        }
    )


@app.route("/api/lead", methods=["PUT"])
def update_lead():
    body = request.get_json()
    telefono = body.get("telefono")
    if not telefono:
        return jsonify({"error": "telefono required"}), 400

    datos = cargar_datos()
    for row in datos:
        if row.get("telefono") == telefono:
            updatable = [
                "enviado", "fecha_envio", "project_path", "live_url",
                "enviado_links", "fecha_envio_links",
                "estado_respuesta", "fecha_respuesta",
                "fecha_entrega", "fecha_renovacion_web",
                "fecha_renovacion_hosting", "fecha_renovacion_mantenimiento",
                "notas",
            ]
            for key in updatable:
                if key in body:
                    row[key] = body[key]
            guardar_datos(datos)
            return jsonify({"ok": True})
    return jsonify({"error": "Lead not found"}), 404


@app.route("/api/lead/<path:telefono>", methods=["GET"])
def get_lead(telefono):
    datos = cargar_datos()
    lead = next((r for r in datos if r.get("telefono") == telefono), None)
    if not lead:
        return jsonify({"error": "not found"}), 404

    # Attach conversation history
    convs = cargar_conversaciones()
    digits = "".join(c for c in telefono if c.isdigit())
    if not digits.startswith("54"):
        digits = "54" + digits
    lead["conversacion"] = convs.get(digits, [])
    return jsonify(lead)


@app.route("/api/renewals")
def api_renewals():
    datos = cargar_datos()
    return jsonify(get_renewals(datos))


@app.route("/api/finanzas")
def api_finanzas():
    finanzas = cargar_finanzas()
    return jsonify(
        {
            "pagos": finanzas.get("pagos", []),
            "config": finanzas.get("config", {}),
            "stats": get_stats_finanzas(finanzas),
        }
    )


@app.route("/api/finanzas/pago", methods=["POST"])
def save_pago():
    body = request.get_json()
    finanzas = cargar_finanzas()
    pagos = finanzas.get("pagos", [])
    telefono = body.get("telefono", "")
    pago = {
        "nombre": body.get("nombre", ""),
        "telefono": telefono,
        "monto": float(body.get("monto", 0)),
        "moneda": body.get("moneda", "ARS"),
        "estado": body.get("estado", "pendiente"),
        "fecha": body.get("fecha") or datetime.now().strftime("%Y-%m-%d"),
        "servicio": body.get("servicio", "Sitio web"),
        "notas": body.get("notas", ""),
    }
    idx = next((i for i, p in enumerate(pagos) if p.get("telefono") == telefono and telefono), None)
    if idx is not None:
        pagos[idx] = pago
    else:
        pagos.append(pago)
    finanzas["pagos"] = pagos
    guardar_finanzas(finanzas)
    return jsonify({"ok": True, "pago": pago})


@app.route("/api/finanzas/pago/<path:telefono>", methods=["DELETE"])
def delete_pago(telefono):
    finanzas = cargar_finanzas()
    finanzas["pagos"] = [p for p in finanzas.get("pagos", []) if p.get("telefono") != telefono]
    guardar_finanzas(finanzas)
    return jsonify({"ok": True})


@app.route("/api/finanzas/config", methods=["PUT"])
def update_finanzas_config():
    body = request.get_json()
    finanzas = cargar_finanzas()
    finanzas["config"] = {**finanzas.get("config", {}), **body}
    guardar_finanzas(finanzas)
    return jsonify({"ok": True})


@app.route("/api/conversations/<path:telefono>")
def get_conversation(telefono):
    convs = cargar_conversaciones()
    digits = "".join(c for c in telefono if c.isdigit())
    if not digits.startswith("54"):
        digits = "54" + digits
    return jsonify(convs.get(digits, []))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
