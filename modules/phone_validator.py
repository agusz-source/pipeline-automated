#!/usr/bin/env python3
"""
Argentine phone number normalizer for WhatsApp.

Target format: digits-only E.164 without + sign, mobile 9 indicator.
  Mobile Rosario:  5493415XXXXXXX  (13 digits)
  Landline:        54341XXXXXXXX   (12 digits)

Handles the most common Google Maps Argentina formats:
  +54 341 5XX-XXXX  →  5493415XXXXXXX
  0341 5XXXXXX      →  5493415XXXXXX
  341 15-XXXXXX     →  549341XXXXXX
  5XXXXXX           →  549341XXXXXXX  (local-only, default area)
"""

import re

COUNTRY = "54"
DEFAULT_AREA = "341"  # Rosario — override via normalizar_telefono(area=...)


def normalizar_telefono(raw: str, area: str = DEFAULT_AREA) -> str | None:
    """
    Normalize an Argentine phone to WhatsApp-compatible digit string.
    Returns e.g. '5493415551234' or None if unrecognizable.
    """
    if not raw:
        return None

    digits = re.sub(r"[^\d]", "", str(raw))
    if not digits:
        return None

    # Already full WA format: 549 + area + number
    if digits.startswith("549") and 12 <= len(digits) <= 14:
        return digits

    # International without mobile 9: 54 + number
    if digits.startswith("54") and 11 <= len(digits) <= 13:
        after = digits[2:]
        if after.startswith("9"):
            return digits  # already 549...
        return "549" + after

    # Strip 0054 prefix
    if digits.startswith("0054"):
        digits = digits[4:]
        return normalizar_telefono(digits, area)

    # Strip national trunk 0
    if digits.startswith("0"):
        digits = digits[1:]

    # Local mobile with 15 prefix only (no area code): 15XXXXXXX
    if digits.startswith("15") and 7 <= len(digits) <= 9:
        return COUNTRY + "9" + area + digits[2:]

    # Area code (3 digits) + 15 + local: e.g. 34115XXXXXXX (12 digits)
    if len(digits) == 12 and digits[3:5] == "15":
        return COUNTRY + "9" + digits[:3] + digits[5:]

    # 10 digits: area (2-3 digits) + local — most common case from Google Maps
    if len(digits) == 10:
        return COUNTRY + "9" + digits

    # 9 digits: 2-digit area + 7-digit local (e.g. CABA 11 + 7 digits)
    if len(digits) == 9:
        return COUNTRY + "9" + digits

    # 11 digits starting with 9: mobile indicator but no country code
    if len(digits) == 11 and digits.startswith("9"):
        return COUNTRY + digits

    # 7-8 digits: local-only, prepend default area
    if 7 <= len(digits) <= 8:
        return COUNTRY + "9" + area + digits

    return None


def es_valido(raw: str) -> bool:
    norm = normalizar_telefono(raw)
    return norm is not None and 11 <= len(norm) <= 14
