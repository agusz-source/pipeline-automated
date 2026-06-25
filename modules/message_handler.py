#!/usr/bin/env python3
"""
Python-side WhatsApp message handler.

Runs a Flask server on WA_EVENTS_PORT (default 3002).
Receives events from the Node.js bridge and:
  - Classifies incoming messages
  - Updates estado.csv with response status
  - Stores conversation history in conversaciones.json
  - Logs all activity

Usage:
    python3 -m modules.message_handler
    # or from run.sh option 10 / setup.sh background
"""

import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from threading import Lock

from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config
from modules.classifier import classify

app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [handler] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.LOGS_DIR / "message_handler.log"),
    ],
)
log = logging.getLogger(__name__)

_csv_lock = Lock()
_conv_lock = Lock()

STATUS_FILE = config.STATUS_FILE
CONVERSACIONES_FILE = config.CONVERSACIONES_FILE


def _load_estado() -> tuple[list[dict], list[str]]:
    if not STATUS_FILE.exists():
        return [], []
    with open(STATUS_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


def _save_estado(rows: list[dict], fieldnames: list[str]) -> None:
    with open(STATUS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _load_conversaciones() -> dict:
    if not CONVERSACIONES_FILE.exists():
        return {}
    try:
        with open(CONVERSACIONES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def _save_conversaciones(convs: dict) -> None:
    CONVERSACIONES_FILE.parent.mkdir(exist_ok=True)
    with open(CONVERSACIONES_FILE, "w", encoding="utf-8") as f:
        json.dump(convs, f, ensure_ascii=False, indent=2)


def _normalize_phone(phone: str) -> str:
    """Strip non-digits, ensure starts with 54."""
    digits = "".join(c for c in phone if c.isdigit())
    if not digits.startswith("54"):
        digits = "54" + digits
    return digits


def _find_row_by_phone(rows: list[dict], phone: str) -> dict | None:
    """Match a phone against the telefono column (flexible normalization)."""
    norm_incoming = _normalize_phone(phone)
    for row in rows:
        stored = _normalize_phone(row.get("telefono", ""))
        if stored == norm_incoming:
            return row
    return None


def handle_message(event: dict) -> dict:
    """
    Process a message event from the Node bridge.
    Returns a dict with action taken.
    """
    phone = event.get("phone", "")
    text = event.get("message", "")
    timestamp = event.get("timestamp", datetime.now().isoformat())

    if not phone:
        return {"status": "ignored", "reason": "no_phone"}

    # Classify
    result = classify(text)
    log.info(
        f"Message from {phone}: '{text[:60]}' → {result.category} ({result.confidence:.0%})"
    )

    # Store in conversation history
    with _conv_lock:
        convs = _load_conversaciones()
        norm_phone = _normalize_phone(phone)
        if norm_phone not in convs:
            convs[norm_phone] = []
        convs[norm_phone].append(
            {
                "timestamp": timestamp,
                "direction": "in",
                "text": text,
                "category": result.category,
                "confidence": result.confidence,
                "signals": result.signals,
            }
        )
        _save_conversaciones(convs)

    # Update CRM
    with _csv_lock:
        rows, fieldnames = _load_estado()

        # Ensure new columns exist in fieldnames
        for col in ("estado_respuesta", "fecha_respuesta"):
            if col not in fieldnames:
                fieldnames.append(col)
                for r in rows:
                    r.setdefault(col, "")

        row = _find_row_by_phone(rows, phone)
        if row is None:
            log.warning(f"Phone {phone} not found in estado.csv — message stored but not linked")
            return {
                "status": "stored",
                "category": result.category,
                "linked_to_lead": False,
            }

        # Only update if the new status is more specific
        current_status = row.get("estado_respuesta", "")
        _priority = {
            "": 0,
            "neutral": 1,
            "info_request": 2,
            "follow_up": 2,
            "price_request": 3,
            "interest": 4,
            "positive_intent": 5,
            "rejection": 6,
        }
        if _priority.get(result.category, 0) >= _priority.get(current_status, 0):
            row["estado_respuesta"] = result.category
            row["fecha_respuesta"] = timestamp

        _save_estado(rows, fieldnames)

    return {
        "status": "processed",
        "category": result.category,
        "confidence": result.confidence,
        "linked_to_lead": True,
    }


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


@app.route("/wa-event", methods=["POST"])
def wa_event():
    """Receive events from Node.js bridge."""
    event = request.get_json(force=True, silent=True) or {}
    event_type = event.get("type", "")

    if event_type == "message":
        result = handle_message(event)
        return jsonify(result)

    elif event_type == "ready":
        log.info("WhatsApp bridge reported READY")
        return jsonify({"status": "ack"})

    elif event_type == "disconnected":
        log.warning(f"WhatsApp bridge disconnected: {event.get('reason')}")
        return jsonify({"status": "ack"})

    elif event_type == "reaction":
        log.info(f"Reaction from {event.get('phone')}: {event.get('reaction')}")
        return jsonify({"status": "ack"})

    return jsonify({"status": "ignored", "type": event_type})


@app.route("/conversations/<phone>")
def get_conversation(phone):
    """Return conversation history for a phone number."""
    convs = _load_conversaciones()
    norm = _normalize_phone(phone)
    return jsonify(convs.get(norm, []))


@app.route("/conversations")
def list_conversations():
    """Return summary of all conversations."""
    convs = _load_conversaciones()
    summary = {
        phone: {
            "message_count": len(msgs),
            "last_message": msgs[-1]["timestamp"] if msgs else None,
            "last_category": msgs[-1]["category"] if msgs else None,
        }
        for phone, msgs in convs.items()
    }
    return jsonify(summary)


if __name__ == "__main__":
    config.ensure_directories()
    port = config.WA_EVENTS_PORT
    log.info(f"Message handler starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
