#!/usr/bin/env python3
"""
Rule-based WhatsApp response classifier.

Detects intent from message text using keyword sets.
Designed for Argentine Spanish informal register.

Categories:
  - rejection       → No interest, stop messaging
  - interest        → Positive, wants to know more
  - price_request   → Asking how much
  - info_request    → Asking for details/info
  - positive_intent → Ready to move forward
  - follow_up       → Asking when/how to see the website
  - neutral         → Unclear, needs context
"""

import re
from dataclasses import dataclass, field


@dataclass
class ClassificationResult:
    category: str
    confidence: float
    signals: list[str] = field(default_factory=list)
    raw_text: str = ""

    @property
    def label(self) -> str:
        return {
            "rejection": "Rechazo",
            "interest": "Interesado",
            "price_request": "Pidió precio",
            "info_request": "Pidió info",
            "positive_intent": "Intención positiva",
            "follow_up": "Follow-up",
            "neutral": "Neutral",
        }.get(self.category, self.category)


# ── Keyword sets (Argentine Spanish + common variations) ─────────────────────

_REJECTION = [
    r"\bno me interesa\b",
    r"\bno gracias\b",
    r"\bno, gracias\b",
    r"\bno necesito\b",
    r"\bno quiero\b",
    r"\bno estoy interesad",
    r"\bno busco\b",
    r"\bya teng[oa] web\b",
    r"\bya ten[ée]m[oa]s web\b",
    r"\bya cuento con\b",
    r"\bno estamos interesados\b",
    r"\bpor favor no\b",
    r"\bsaqu[eé]me de\b",
    r"\bno contestes m[aá]s\b",
    r"\bspam\b",
    r"\bno molest",
    r"\bdejen de\b",
    r"\bno, pas[ée]\b",
    r"\bpas[ée]\b",
]

_INTEREST = [
    r"\bme interesa\b",
    r"\bnos interesa\b",
    r"\binteresante\b",
    r"\bquiero ver\b",
    r"\bquer[eé]mos ver\b",
    r"\bman[dá]la?\b",
    r"\bman[dá]me\b",
    r"\bman[dá]nos\b",
    r"\bpas[áa]la?\b",
    r"\bpas[áa]me\b",
    r"\bpas[áa]nos\b",
    r"\bquiero ver[la]?\b",
    r"\bme gustar[íi]a ver\b",
    r"\bpodr[íi]as?\s+mostrar",
    r"\bmu[eé]str",
    r"\bcon gusto\b",
    r"\bbuena onda\b",
    r"\bme cop[óo]\b",
    r"\bc[óo]mo es\b",
    r"\bcomo es\b",
]

_PRICE_REQUEST = [
    r"\bcuanto\b",
    r"\bcu[áa]nto\b",
    r"\bcuanto cuesta\b",
    r"\bcuanto sale\b",
    r"\bqu[eé] precio\b",
    r"\bpreci[oa]\b",
    r"\bcosto\b",
    r"\bcostar[íi]a\b",
    r"\bval[eo]\b",
    r"\bcuanto cobr",
    r"\btarifa\b",
    r"\bcuanto cobras\b",
    r"\bpresto\b",
    r"\bpresupuesto\b",
]

_INFO_REQUEST = [
    r"\bcomo funcion",
    r"\bc[óo]mo funcion",
    r"\bque incluye\b",
    r"\bqu[eé] incluye\b",
    r"\bque ofrec[eé]s\b",
    r"\bque hac[eé]s\b",
    r"\bcomo es el proceso\b",
    r"\bque es esto\b",
    r"\bde qu[eé] se trata\b",
    r"\bexplicame\b",
    r"\bexplical?me\b",
    r"\bcont[áa]me\b",
    r"\bque tipo de web\b",
    r"\bqu[eé] tipo de\b",
    r"\bcomo quedar[íi]a\b",
    r"\bcomo seria\b",
    r"\bc[óo]mo ser[íi]a\b",
]

_POSITIVE_INTENT = [
    r"\bquiero contrat",
    r"\bquer[eé]mos contrat",
    r"\bcu[áa]ndo podem[oa]s\b",
    r"\bcu[áa]ndo empezamos\b",
    r"\bpodemos reunir\b",
    r"\bqu[eé] necesit[aá]s?\b",
    r"\bqu[eé] datos\b",
    r"\badelante\b",
    r"\bme copó\b",
    r"\bme gust[óo] la idea\b",
    r"\bme interesa que hagas\b",
    r"\bquiero que lo hagas\b",
    r"\bcu[áa]ndo arranc",
]

_FOLLOW_UP = [
    r"\bc[óo]mo puedo ver\b",
    r"\bdonde la veo\b",
    r"\btu[íi]\b",
    r"\blink\b",
    r"\burl\b",
    r"\bla web\b",
    r"\bel sitio\b",
    r"\bel link\b",
    r"\bpas[áa]me el link\b",
    r"\bdonde est[áa]\b",
    r"\bcomo entro\b",
    r"\bcomo la veo\b",
]


def _compile(patterns: list[str]):
    return [re.compile(p, re.IGNORECASE | re.UNICODE) for p in patterns]


_COMPILED = {
    "rejection": _compile(_REJECTION),
    "interest": _compile(_INTEREST),
    "price_request": _compile(_PRICE_REQUEST),
    "info_request": _compile(_INFO_REQUEST),
    "positive_intent": _compile(_POSITIVE_INTENT),
    "follow_up": _compile(_FOLLOW_UP),
}

# Priority order — first match wins (positive_intent before interest, etc.)
_PRIORITY = [
    "rejection",
    "positive_intent",
    "follow_up",
    "price_request",
    "interest",
    "info_request",
]


def classify(text: str) -> ClassificationResult:
    """
    Classify a WhatsApp message text.
    Returns ClassificationResult with category, confidence, and matched signals.
    """
    if not text or not text.strip():
        return ClassificationResult("neutral", 0.0, [], text)

    text_normalized = text.lower().strip()
    all_signals: dict[str, list[str]] = {cat: [] for cat in _COMPILED}

    for cat, patterns in _COMPILED.items():
        for pat in patterns:
            m = pat.search(text_normalized)
            if m:
                all_signals[cat].append(m.group(0))

    # Count hits per category
    hits = {cat: len(sigs) for cat, sigs in all_signals.items()}

    if not any(hits.values()):
        return ClassificationResult("neutral", 0.3, [], text)

    # Select by priority, then by hit count
    best_cat = None
    for cat in _PRIORITY:
        if hits[cat] > 0:
            best_cat = cat
            break

    if not best_cat:
        best_cat = max(hits, key=lambda c: hits[c])

    total_hits = sum(hits.values())
    confidence = min(0.95, 0.4 + (hits[best_cat] / max(total_hits, 1)) * 0.55)

    # Reduce confidence if rejection + interest signals coexist (ambiguous)
    if hits["rejection"] > 0 and hits["interest"] > 0:
        confidence *= 0.7

    return ClassificationResult(
        category=best_cat,
        confidence=round(confidence, 2),
        signals=all_signals[best_cat],
        raw_text=text,
    )
