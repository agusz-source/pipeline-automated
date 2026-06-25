#!/usr/bin/env python3
"""
Lead scoring system — 0 to 100.

Higher score = higher priority to contact.

Factors:
  - Web presence quality   (0-40 pts)
  - Niche match strength   (0-20 pts)
  - Social proof           (0-20 pts)
  - Business maturity      (0-20 pts)
"""

from config import config

_STRONG_CATS = frozenset([
    "fábrica de muebles",
    "tienda de muebles",
    "tienda de muebles de cocina",
    "tienda de mobiliario para dormitorios",
    "interiorista",
])

_MEDIUM_CATS = frozenset([
    "carpintería",
    "carpintero",
    "tienda de muebles de pino",
    "tienda de mobiliario de oficina",
    "herrero",
    "tienda de artículos para el hogar",
    "establecimiento de venta de madera",
])

_PREMIUM_KEYWORDS = [
    "medida", "design", "studio", "estudio", "premium", "exclusive",
    "vestidor", "placard", "closet", "amoblamiento", "interior",
]

_SOCIAL_DOMAINS = ("instagram.com", "facebook.com", "tiktok.com")


def score_lead(lead: dict) -> int:
    """Compute a score from 0 to 100 for a given lead."""
    points = 0

    # ── Web presence (0-40) ──────────────────────────────────
    website = (lead.get("website") or lead.get("url", "")).lower()
    if "google.com/maps" in website:
        website = ""

    filter_reason = lead.get("filter_reason", "")

    if not website:
        # No web presence at all — highest opportunity
        points += 40
    elif any(d in website for d in _SOCIAL_DOMAINS):
        # Social media only — good opportunity
        points += 28
    elif filter_reason == "solo_redes_sociales":
        points += 25
    else:
        # Has some web presence but not filtered as excellent
        points += 10

    # ── Niche match (0-20) ───────────────────────────────────
    cat = (lead.get("categoryName") or lead.get("categoria") or "").lower()
    cats = [c.lower() for c in (lead.get("categories") or [])]
    title = (lead.get("title") or lead.get("nombre") or "").lower()

    if cat in _STRONG_CATS or any(c in _STRONG_CATS for c in cats):
        points += 20
    elif cat in _MEDIUM_CATS or any(c in _MEDIUM_CATS for c in cats):
        points += 14
    else:
        # Keyword-matched niche
        points += 8

    # Bonus for premium positioning signals in business name
    if any(kw in title for kw in _PREMIUM_KEYWORDS):
        points += 5

    # ── Social proof — reviews (0-15) ────────────────────────
    reviews = lead.get("reviewsCount") or lead.get("resenas") or 0
    try:
        reviews = int(reviews)
    except (ValueError, TypeError):
        reviews = 0

    if reviews >= 100:
        points += 15
    elif reviews >= 50:
        points += 10
    elif reviews >= 20:
        points += 7
    elif reviews >= 5:
        points += 4
    else:
        points += 1

    # ── Rating quality (0-10) ────────────────────────────────
    rating = lead.get("totalScore") or lead.get("puntaje") or 0
    try:
        rating = float(rating)
    except (ValueError, TypeError):
        rating = 0

    if rating >= 4.7:
        points += 10
    elif rating >= 4.3:
        points += 7
    elif rating >= 3.8:
        points += 4
    elif rating > 0:
        points += 2

    # ── Phone availability (0-5) — no phone = very hard to contact
    phone = lead.get("phone") or lead.get("telefono") or ""
    if phone and len(phone.strip()) >= 8:
        points += 5

    return min(100, points)


def score_and_annotate(leads: list[dict]) -> list[dict]:
    """Add 'score' field to each lead and sort by score descending."""
    for lead in leads:
        lead["score"] = score_lead(lead)
    return sorted(leads, key=lambda x: -x["score"])
