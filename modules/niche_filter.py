#!/usr/bin/env python3
"""
Niche and location filter for leads.

Rules:
- Must be in Rosario, Santa Fe, Argentina.
- Must belong to any configured niche in config.NICHES.
- Must NOT have a real standalone website (social-only or no website = valid target).
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

# Build combined sets from all configured niches
_ALL_CATS_LOWER = frozenset(
    c.lower()
    for niche in config.NICHES.values()
    for c in niche.get("categories", set())
)

_ALL_KWS_LOWER = list({
    kw.lower()
    for niche in config.NICHES.values()
    for kw in niche.get("keywords", [])
})


def _is_rosario(lead: dict) -> bool:
    city = (lead.get("city") or lead.get("ciudad") or "").lower().strip()
    state = (lead.get("state") or lead.get("provincia") or "").lower().strip()
    country = (lead.get("countryCode") or lead.get("pais") or "AR").upper()

    if country not in ("AR", ""):
        return False

    if city and any(syn in city for syn in _ROSARIO_SYNONYMS):
        return True

    # Records with empty city but state = Santa Fe are kept if niche matches
    if state and "santa fe" in state and not city:
        return True

    return False


def _is_target_niche(lead: dict) -> bool:
    cat_name = (lead.get("categoryName") or lead.get("categoria") or "").lower()
    cats = [c.lower() for c in (lead.get("categories") or [])]
    title = (lead.get("title") or lead.get("nombre") or "").lower()

    if cat_name in _ALL_CATS_LOWER:
        return True
    if any(c in _ALL_CATS_LOWER for c in cats):
        return True
    if any(kw in title for kw in _ALL_KWS_LOWER):
        return True
    if any(kw in cat_name for kw in _ALL_KWS_LOWER):
        return True

    return False


def _is_social_only(website: str) -> bool:
    if not website:
        return False
    return any(d in website.lower() for d in _SOCIAL_DOMAINS)


def _has_real_website(website: str) -> bool:
    if not website:
        return False
    if _is_social_only(website):
        return False
    if "google.com/maps" in website or "maps.google" in website:
        return False
    return True


def filter_leads(leads: list[dict]) -> tuple[list[dict], dict]:
    """
    Filter leads to target-niche businesses in Rosario without real websites.
    Returns (filtered_leads, stats_dict).
    Each accepted lead gets a 'filter_reason' key.
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

        if not _is_target_niche(lead):
            stats["wrong_niche"] += 1
            continue

        website = lead.get("website") or lead.get("url", "")
        if "google.com/maps" in website:
            website = ""

        if _has_real_website(website):
            stats["has_real_website"] += 1
            continue

        lead["filter_reason"] = "sin_website" if not website else "solo_redes_sociales"
        accepted.append(lead)
        stats["accepted"] += 1

    return accepted, stats


def print_filter_report(stats: dict) -> None:
    print(f"\n{'='*60}")
    print("FILTRO DE NICHO Y UBICACION")
    print(f"{'='*60}")
    print(f"   Total analizados:      {stats['total']}")
    print(f"   Fuera de Rosario:      {stats['wrong_location']}")
    print(f"   Fuera del nicho:       {stats['wrong_niche']}")
    print(f"   Tienen web real:       {stats['has_real_website']}")
    print(f"   Cerrados permanente:   {stats['permanently_closed']}")
    print(f"   {Fore.GREEN}Leads validos:         {stats['accepted']}")
    print(f"{'='*60}")
