#!/usr/bin/env python3
"""
Niche and location filter for leads.

Rules:
- Must be in Rosario, Santa Fe, Argentina.
- Must belong to the amoblamientos / muebles / carpintería niche.
- Must NOT have an excellent modern website (those are excluded).
- Businesses with only social media profiles are valid targets.
"""

from colorama import Fore, init

from config import config

init(autoreset=True)

_SOCIAL_DOMAINS = frozenset([
    "instagram.com", "facebook.com", "fb.com", "twitter.com", "x.com",
    "linkedin.com", "youtube.com", "tiktok.com", "pinterest.com",
    "wa.me", "whatsapp.com", "linktr.ee", "bio.link",
])

_ROSARIO_SYNONYMS = frozenset([
    "rosario", "rosario centro", "rosario sur", "rosario norte",
    "baigorria", "funes", "granadero baigorria",
])

_FURNITURE_CATS_LOWER = frozenset(c.lower() for c in config.FURNITURE_CATEGORIES)
_FURNITURE_KW_LOWER = [k.lower() for k in config.FURNITURE_KEYWORDS]


def _is_rosario(lead: dict) -> bool:
    city = (lead.get("city") or lead.get("ciudad") or "").lower().strip()
    state = (lead.get("state") or lead.get("provincia") or "").lower().strip()
    country = (lead.get("countryCode") or lead.get("pais") or "AR").upper()

    if country not in ("AR", ""):
        return False

    if city and any(syn in city for syn in _ROSARIO_SYNONYMS):
        return True

    # Some records have city = "" but state = "Santa Fe"; keep those with niche match
    if state and "santa fe" in state and not city:
        return True

    return False


def _is_furniture_niche(lead: dict) -> bool:
    cat_name = (lead.get("categoryName") or lead.get("categoria") or "").lower()
    cats = [c.lower() for c in (lead.get("categories") or [])]
    title = (lead.get("title") or lead.get("nombre") or "").lower()

    if cat_name in _FURNITURE_CATS_LOWER:
        return True

    if any(c in _FURNITURE_CATS_LOWER for c in cats):
        return True

    if any(kw in title for kw in _FURNITURE_KW_LOWER):
        return True

    if any(kw in cat_name for kw in _FURNITURE_KW_LOWER):
        return True

    return False


def _is_social_only(website: str) -> bool:
    if not website:
        return False
    ws = website.lower()
    return any(d in ws for d in _SOCIAL_DOMAINS)


def _has_real_website(website: str) -> bool:
    if not website:
        return False
    if _is_social_only(website):
        return False
    # Maps / Google links are not real websites
    if "google.com/maps" in website or "maps.google" in website:
        return False
    return True


def filter_leads(leads: list[dict]) -> tuple[list[dict], dict]:
    """
    Filter leads to only furniture businesses in Rosario without excellent websites.

    Returns (filtered_leads, stats_dict).
    Each accepted lead gets a 'filter_reason' key describing why it was kept.
    """
    accepted = []
    stats = {
        "total": len(leads),
        "wrong_location": 0,
        "wrong_niche": 0,
        "has_real_website": 0,
        "permanently_closed": 0,
        "accepted": 0,
    }

    for lead in leads:
        if lead.get("permanentlyClosed"):
            stats["permanently_closed"] += 1
            continue

        if not _is_rosario(lead):
            stats["wrong_location"] += 1
            continue

        if not _is_furniture_niche(lead):
            stats["wrong_niche"] += 1
            continue

        website = lead.get("website") or lead.get("url", "")
        # Google Maps URLs stored in the `url` field are not real websites
        if "google.com/maps" in website:
            website = ""

        if _has_real_website(website):
            stats["has_real_website"] += 1
            continue

        if not website:
            lead["filter_reason"] = "sin_website"
        else:
            lead["filter_reason"] = "solo_redes_sociales"

        accepted.append(lead)
        stats["accepted"] += 1

    return accepted, stats


def print_filter_report(stats: dict) -> None:
    print(f"\n{'='*60}")
    print("🔍 FILTRO DE NICHO Y UBICACIÓN")
    print(f"{'='*60}")
    print(f"   Total analizados:      {stats['total']}")
    print(f"   Fuera de Rosario:      {stats['wrong_location']}")
    print(f"   Fuera del nicho:       {stats['wrong_niche']}")
    print(f"   Tienen web real:       {stats['has_real_website']}")
    print(f"   Cerrados permanente:   {stats['permanently_closed']}")
    print(f"   {Fore.GREEN}✅ Leads válidos:        {stats['accepted']}")
    print(f"{'='*60}")
