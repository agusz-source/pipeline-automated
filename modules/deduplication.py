#!/usr/bin/env python3
"""
SHA256-based lead deduplication.

Every lead gets a deterministic lead_id derived from:
  SHA256(normalized_name + "|" + normalized_address + "|" + normalized_phone)

Normalization: lowercase, strip accents, remove non-alphanumeric, trim.
"""

import csv
import hashlib
import re
import unicodedata
from pathlib import Path


def _normalize(text: str) -> str:
    """Lowercase, remove accents, keep only alphanum + spaces, collapse whitespace."""
    if not text:
        return ""
    text = str(text).lower().strip()
    # Remove accents
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # Keep only alphanumeric and spaces
    text = re.sub(r"[^a-z0-9\s]", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compute_lead_id(name: str, address: str, phone: str) -> str | None:
    """
    Compute a stable SHA256 lead ID from business identity fields.
    Returns None if all three fields are empty (cannot identify lead).
    """
    n = _normalize(name)
    a = _normalize(address)
    p = _normalize(phone)

    if not n and not a and not p:
        return None

    raw = f"{n}|{a}|{p}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_existing_ids(status_file: Path) -> set[str]:
    """Read all lead_ids already present in estado.csv."""
    if not status_file.exists():
        return set()

    existing = set()
    with open(status_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "lead_id" not in (reader.fieldnames or []):
            return set()
        for row in reader:
            lid = row.get("lead_id", "").strip()
            if lid:
                existing.add(lid)
    return existing


def filter_new_leads(
    leads: list[dict],
    existing_ids: set[str],
) -> tuple[list[dict], list[dict]]:
    """
    Attach lead_id to each lead, then split into new vs duplicate.

    Returns (new_leads, duplicates).
    Leads that can't produce a lead_id are discarded (not returned in either list).
    """
    new_leads = []
    duplicates = []
    seen_in_batch: set[str] = set()

    for lead in leads:
        name = lead.get("title") or lead.get("nombre", "")
        address = (
            lead.get("street")
            or lead.get("direccion")
            or lead.get("address")
            or ""
        )
        phone = lead.get("phone") or lead.get("telefono", "")

        lid = compute_lead_id(name, address, phone)
        if not lid:
            continue  # discard unidentifiable leads

        lead["lead_id"] = lid

        if lid in existing_ids or lid in seen_in_batch:
            duplicates.append(lead)
        else:
            seen_in_batch.add(lid)
            new_leads.append(lead)

    return new_leads, duplicates
