"""
OSM scraper — queries Overpass API for businesses in Rosario, AR.
Returns records in the same format as the Apify scraper so they pass
through filter_leads and stage_discover without changes.
"""

import re
import time
import requests
from config import config

OVERPASS_URL = "https://overpass.kumi.systems/api/interpreter"

# OSM tag → list of Overpass tag filters
_OSM_NICHES = {
    "amoblamientos": [
        '["shop"="furniture"]',
        '["shop"="kitchen"]',
        '["craft"="cabinet_maker"]',
        '["shop"="interior_decoration"]',
    ],
    "estetica": [
        '["shop"="beauty"]',
        '["shop"="hairdresser"]',
        '["shop"="nail_salon"]',
        '["amenity"="beauty_salon"]',
    ],
    "gimnasio": [
        '["leisure"="fitness_centre"]',
        '["leisure"="sports_centre"]',
        '["sport"="yoga"]',
        '["sport"="crossfit"]',
    ],
    "cerrajeria": [
        '["shop"="locksmith"]',
    ],
}

_SOCIAL_DOMAINS = frozenset([
    "instagram.com", "facebook.com", "fb.com", "twitter.com", "x.com",
    "linktr.ee", "wa.me", "whatsapp.com",
])


def _normalize_phone(raw: str) -> str:
    """Normalize Argentine phone to international format (no +)."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0"):
        digits = digits[1:]
    if digits.startswith("15") and len(digits) == 12:
        digits = digits[:2] + digits[4:]
    if len(digits) == 10:
        digits = "54" + digits
    if len(digits) == 11 and not digits.startswith("54"):
        digits = "54" + digits
    if not (11 <= len(digits) <= 15):
        return ""
    return "+" + digits


def _has_real_website(url: str) -> bool:
    if not url:
        return False
    return not any(d in url.lower() for d in _SOCIAL_DOMAINS)


def _query_overpass(tag_filter: str, lat: float, lon: float, radius: int) -> list[dict]:
    """Run a single Overpass query and return raw elements."""
    query = f"""
[out:json][timeout:90];
(
  node{tag_filter}(around:{radius},{lat},{lon});
  way{tag_filter}(around:{radius},{lat},{lon});
  relation{tag_filter}(around:{radius},{lat},{lon});
);
out center tags;
"""
    try:
        r = requests.post(
            OVERPASS_URL,
            data={"data": query},
            timeout=(10, 90),
            headers={"Accept-Charset": "utf-8"},
        )
        if r.status_code != 200:
            return []
        return r.json().get("elements", [])
    except Exception:
        return []


def scrape_osm(niches: list[str] | None = None, max_per_niche: int = 40) -> list[dict]:
    """
    Scrape Overpass/OSM for businesses in Rosario.
    Returns records in the same format as the Apify scraper.
    """
    lat = config.LATITUD
    lon = config.LONGITUD
    radius = getattr(config, "RADIO_BUSQUEDA", 12000)

    if niches is None:
        niches = list(_OSM_NICHES.keys())

    results: list[dict] = []
    seen_names: set[str] = set()

    for niche in niches:
        tag_filters = _OSM_NICHES.get(niche, [])
        if not tag_filters:
            continue

        niche_results: list[dict] = []
        for tag_filter in tag_filters:
            if len(niche_results) >= max_per_niche:
                break
            elements = _query_overpass(tag_filter, lat, lon, radius)
            for el in elements:
                if len(niche_results) >= max_per_niche:
                    break
                tags = el.get("tags", {})
                name = tags.get("name", "").strip()
                if not name or name in seen_names:
                    continue

                phone_raw = tags.get("phone") or tags.get("contact:phone") or tags.get("mobile") or ""
                phone = _normalize_phone(phone_raw)

                website = tags.get("website") or tags.get("contact:website") or tags.get("url") or ""

                street = tags.get("addr:street", "")
                housenumber = tags.get("addr:housenumber", "")
                direccion = (street + " " + housenumber).strip() or "Rosario"

                rec = {
                    "title": name,
                    "nombre": name,
                    "categoryName": niche,
                    "categoria": niche,
                    "categories": [niche],
                    "phone": phone,
                    "telefono": phone,
                    "street": direccion,
                    "direccion": direccion,
                    "city": "Rosario",
                    "ciudad": "Rosario",
                    "state": "Santa Fe",
                    "countryCode": "AR",
                    "website": website if not _has_real_website(website) else website,
                    "totalScore": tags.get("stars"),
                    "reviewsCount": 0,
                    "permanentlyClosed": False,
                    "source": "OSM",
                }
                # Filter: if they have a real website, mark it so filter_leads can exclude them
                # (OSM leads without website are our targets)
                seen_names.add(name)
                niche_results.append(rec)

            time.sleep(1.5)

        results.extend(niche_results)

    return results
