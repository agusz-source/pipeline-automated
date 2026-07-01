#!/usr/bin/env python3
"""
Website generator — Claude Code agent writes files directly into each project folder.
Flow: Python creates folder → invokes claude --permission-mode bypassPermissions → Claude writes files to disk.
"""

import csv
import hashlib
import io
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

import requests
from colorama import Fore, init

from config import config

init(autoreset=True)

INTERESADOS_FILE = config.INTERESADOS_FILE
DATASET_FILE = config.DATASET_FILE

_NICHE_VIBE: list[tuple[list[str], str]] = [
    (
        ["mueble", "carpinter", "amoblamiento", "placard", "cocina", "madera", "tapiz", "herrer"],
        "Industrial-craft: zinc-950 (#1a1714) base, off-white (#f5f3ef) text, warm amber (#c97820) as sole accent. "
        "Barlow Condensed 800 for headings, Barlow 400 body. Hero: 60/40 split — headline left, CSS geometric "
        "composition of interlocking rectangles right (pure CSS, no img). Service rows full-width bordered, not card grid.",
    ),
    (
        ["estética", "estetica", "belleza", "nail", "manicur", "pedicur", "lash", "spa", "bronceado", "masaje"],
        "Quiet editorial luxury: warm off-white (#f9f6f2) base, single rose accent (#c0788a). "
        "DM Serif Display italic for headings, DM Sans 400 body. Hero: asymmetric — headline large italic left, "
        "address + CTA right, no gradient. Sections alternate off-white / pale sand, curved divider between them.",
    ),
    (
        ["peluquer", "keratina", "coloracion", "tintura"],
        "Bold typographic confidence: near-black (#1a1714) base, off-white text, electric teal (#1dada8) accent. "
        "Bebas Neue or Barlow Condensed 900 for headings. Hero: full-bleed dark, headline at clamp(4rem,10vw,8rem) "
        "flush left, zero decoration. Testimonials in high-contrast inverted cards.",
    ),
    (
        ["gimnasio", "gym", "fitness", "crossfit", "funcional", "entrenamiento", "musculacion", "boxeo"],
        "High-energy industrial: zinc-950 (#111110) base, off-white text, electric lime (#c8e120) as sole accent. "
        "Barlow Condensed 900 for headings at oversized scale, Barlow 400 body. Hero: full-bleed dark with "
        "headline crushing full width, CTA in lime-on-black. Service rows as stark full-width blocks, "
        "no cards. Testimonials inverted with bold first-name callout.",
    ),
    (
        ["pilates", "yoga"],
        "Calm editorial: warm linen (#f5f0e8) base, charcoal (#2a2826) text, sage green (#7a9e7e) accent. "
        "Cormorant Garamond 300 italic for display headings, DM Sans 400 body. Hero: asymmetric — "
        "large italic headline left, minimal address + CTA right, no gradient. Generous whitespace, "
        "sections alternate linen/warm white with thin sage dividers.",
    ),
    (
        ["cerrajer", "llave", "duplicado", "cerradura"],
        "Utility confidence: concrete (#b0a99f) and zinc-950, amber (#e8a020) accent on CTAs only. "
        "Barlow Condensed 700 headings, Barlow 400 body. Hero: split — left headline + address, right CSS "
        "geometric lock/key shape in amber/concrete. No decoration beyond function.",
    ),
]

_DEFAULT_VIBE = (
    "Editorial craft: off-white (#f5f3ef) base, zinc-950 text, one strong accent derived from the business "
    "personality. Outfit 700 or Cabinet Grotesk 700 for headings, system-sans body. Varied section rhythm, "
    "no two consecutive sections with the same layout family."
)

_NICHE_COLORS: list[tuple[list[str], list[str]]] = [
    (
        ["estética", "estetica", "belleza", "nail", "manicur", "pedicur", "lash", "spa", "bronceado", "masaje"],
        ["#c0788a", "#f9f6f2", "#8b4a5c", "#1a1714"],
        # rose accent, warm cream base, deep rose contrast, near-black text
    ),
    (
        ["peluquer", "keratina", "coloracion", "tintura"],
        ["#1dada8", "#1a1714", "#e8f4f3", "#c8523a"],
        # electric teal, near-black, light teal tint, warm red contrast
    ),
    (
        ["gimnasio", "gym", "fitness", "crossfit", "funcional", "entrenamiento", "musculacion", "boxeo"],
        ["#c8e120", "#111110", "#f0f5d0", "#e8340a"],
        # electric lime, near-black, lime tint, aggressive red contrast
    ),
    (
        ["pilates", "yoga"],
        ["#7a9e7e", "#f5f0e8", "#3d5c40", "#c4a882"],
        # sage green, warm linen, deep forest, sand contrast
    ),
    (
        ["mueble", "carpinter", "amoblamiento", "placard", "cocina", "madera", "tapiz", "herrer"],
        ["#c97820", "#1a1714", "#f5f3ef", "#6b4c1e"],
        # warm amber, near-black, off-white, deep wood contrast
    ),
    (
        ["cerrajer", "llave", "duplicado", "cerradura"],
        ["#e8a020", "#1a1714", "#b0a99f", "#2a2420"],
        # amber, near-black, concrete, dark contrast
    ),
    (
        ["restaurant", "restau", "comida", "pizza", "sushi", "burger", "cafe", "panaderia", "heladeria"],
        ["#d4500a", "#1a1714", "#fdf6ec", "#8b2a0a"],
        # warm orange-red, near-black, warm cream, deep red contrast
    ),
    (
        ["medic", "odontolog", "dentist", "clinic", "salud", "psicolog", "nutricion", "farmac"],
        ["#2a7fbd", "#f4f8fc", "#1a3a5c", "#4ab3c8"],
        # trust blue, clean white-blue base, deep navy, cyan contrast
    ),
    (
        ["abogad", "estudio juridico", "contad", "inmobiliari"],
        ["#1a3a5c", "#f5f3ef", "#c4a050", "#2d5a8c"],
        # deep navy, off-white, gold accent, mid blue contrast
    ),
    (
        ["electrodom", "tecnic", "reparacion", "plomero", "electric", "pintor", "albañil", "construc"],
        ["#e85010", "#1a1714", "#f5f3ef", "#a83808"],
        # strong orange-red, near-black, off-white, deep red contrast
    ),
]

_DEFAULT_COLORS = ["#2a5a8c", "#f5f3ef", "#1a1714", "#c4a050"]
# versatile navy + off-white + near-black + gold — works for any unmatched category


def _category_colors(lead: dict) -> list[str]:
    text = " ".join([
        (lead.get("categoryName") or lead.get("categoria") or ""),
        (lead.get("nombre") or lead.get("title") or ""),
    ]).lower()
    for keywords, colors in _NICHE_COLORS:
        if any(k in text for k in keywords):
            return colors
    return _DEFAULT_COLORS


_LAYOUT_PERSONALITIES = [
    """\
LAYOUT: Editorial Asymmetry
- Hero: 65/35 horizontal split — massive italic headline left, stacked address + CTA right. Dark background.
- Servicios: horizontal overflow row of tall narrow cards (overflow-x: auto, snap-type: x mandatory)
- Proceso: diagonal staircase — each step indented more than the last, large numeral, small text
- Portfolio: CSS masonry using columns property (3 col desktop), varied heights
- Testimonios: single large pull-quote per row, full width, 4rem italic, name in small caps below
- Contacto: two columns — left: large phone number at 4rem; right: address + WA CTA""",

    """\
LAYOUT: Bold Bento Grid
- Hero: CSS grid 12-col — headline spans cols 1-8, accent color block fills cols 9-12, full viewport height
- Servicios: 2×2 grid desktop, each cell dark background with single service word at 3rem + description on hover
- Proceso: horizontal timeline — circles connected by a line, text alternates above/below
- Portfolio: overlapping cards with explicit z-index layering, slight rotation (2-4deg) on alternates
- Testimonios: 3-col card grid, each card has huge opening-quote mark (7rem) as decoration
- Contacto: centered narrow column (max 520px), minimal, large WA button full width""",

    """\
LAYOUT: Magazine Flow
- Hero: full-bleed solid color (use darkest palette color), headline at clamp(4rem,10vw,9rem), subtext in uppercase tracking-wide
- Servicios: alternating full-width rows — odd rows: text left 40% / visual block right 60%; even rows: reversed
- Proceso: vertical steps with left border accent line, step title at 2rem, description indented
- Portfolio: 3 unequal columns (45% / 30% / 25%), color blocks in brand palette, no border-radius
- Testimonios: horizontal scrolling strip — each testimonial 320px wide, dark bg, white text
- Contacto: split page — left half dark with white contact info; right half light with WA CTA""",

    """\
LAYOUT: High Contrast Blocks
- Hero: alternating stripe background (2 horizontal bands), headline breaks across both bands
- Servicios: full-width alternating sections per service — each one different bg color from palette
- Proceso: large bold numbers (10rem, low opacity) behind step text, steps full bleed
- Portfolio: rectangular color blocks in a CSS grid collage — no text, pure visual
- Testimonios: blockquote format, 3rem italic, left border 4px accent color, name flush right
- Contacto: dark section, address in monospace-style font, WA button accent color full width""",

    """\
LAYOUT: Typographic Brutalism
- Hero: oversized headline clamp(6rem,16vw,13rem) flush left, zero decoration, one-word accent color highlight
- Servicios: numbered list — 01, 02, 03... at 5rem low opacity behind service names, no cards
- Proceso: inline paragraph format — steps written as running text with bold action words
- Portfolio: CSS grid of solid color squares/rectangles, sizes vary (1×1, 2×1, 1×2), brand palette only
- Testimonios: single testimonial at a time, huge quotation mark background, italic serif at 2.5rem
- Contacto: raw layout — phone at 4rem, address small, WA link styled as underline-only text""",
]


def _layout_personality(lead: dict) -> str:
    nombre = (lead.get("nombre") or lead.get("title") or "x")
    idx = int(hashlib.md5(nombre.encode()).hexdigest(), 16) % len(_LAYOUT_PERSONALITIES)
    return _LAYOUT_PERSONALITIES[idx]


def _design_vibe(lead: dict) -> str:
    text = " ".join([
        (lead.get("categoryName") or lead.get("categoria") or ""),
        (lead.get("nombre") or lead.get("title") or ""),
    ]).lower()
    for keywords, vibe in _NICHE_VIBE:
        if any(k in text for k in keywords):
            return vibe
    return _DEFAULT_VIBE


def _is_business_logo(image_path: Path) -> bool:
    """Uses Claude Haiku CLI to check if the image is a business logo (not a personal photo)."""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    try:
        r = subprocess.run(
            [
                "claude",
                "--model", "claude-haiku-4-5-20251001",
                "--permission-mode", "bypassPermissions",
                "--print",
                f"Read the image file at {image_path}. Is this a business logo or brand image (not a face or personal photo)? Reply only YES or NO.",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            stdin=subprocess.DEVNULL,
            env=env,
        )
        return r.stdout.strip().upper().startswith("Y")
    except Exception:
        return False


def _fetch_brand_assets(phone: str, project_path: Path) -> dict:
    """
    Fetches WhatsApp profile picture, verifies it's a business logo via Claude Haiku,
    and extracts dominant colors. Returns dict with logo_path (str|None) and colors (list of hex).
    """
    try:
        from colorthief import ColorThief
    except ImportError:
        return {"logo_path": None, "colors": []}

    bridge_url = config.WA_BRIDGE_URL
    digits = re.sub(r"[^\d]", "", phone)

    try:
        r = requests.get(
            f"{bridge_url}/profile-pic",
            params={"phone": digits},
            timeout=8,
        )
        if r.status_code != 200:
            return {"logo_path": None, "colors": []}
        pic_url = r.json().get("url")
        if not pic_url:
            return {"logo_path": None, "colors": []}
    except Exception:
        return {"logo_path": None, "colors": []}

    try:
        img_data = requests.get(pic_url, timeout=10).content
        tmp_path = project_path / "logo.jpg"
        tmp_path.write_bytes(img_data)

        if not _is_business_logo(tmp_path):
            tmp_path.unlink(missing_ok=True)
            return {"logo_path": None, "colors": []}

        ct = ColorThief(io.BytesIO(img_data))
        palette = ct.get_palette(color_count=3, quality=1)
        colors = [f"#{rv:02x}{gv:02x}{bv:02x}" for rv, gv, bv in palette]
        return {"logo_path": str(tmp_path), "colors": colors}
    except Exception:
        return {"logo_path": None, "colors": []}


def _build_agent_prompt(lead: dict, brand: dict | None = None) -> str:
    nombre = lead.get("nombre") or lead.get("title", "Negocio")
    telefono = lead.get("telefono") or lead.get("phone", "")
    direccion = lead.get("direccion") or lead.get("street", "Rosario")
    ciudad = lead.get("ciudad") or lead.get("city", "Rosario")
    categoria = lead.get("categoryName") or lead.get("categoria", "servicio")
    resenas = lead.get("resenas") or lead.get("reviewsCount", 0)
    puntaje = lead.get("puntaje") or lead.get("totalScore", "")

    phone_digits = re.sub(r"[^\d]", "", telefono)
    if not phone_digits.startswith("54"):
        phone_digits = "54" + phone_digits
    wa_link = f"https://wa.me/{phone_digits}?text=Hola%2C%20quer%C3%ADa%20hacer%20una%20consulta"

    reviews_line = ""
    if resenas and int(resenas) > 0:
        reviews_line = f"  Reviews: {puntaje} estrellas ({resenas} resenas Google)\n" if puntaje else f"  Reviews: {resenas} en Google\n"

    vibe   = _design_vibe(lead)
    layout = _layout_personality(lead)
    brand  = brand or {}

    if brand.get("logo_path"):
        logo_line = (
            f"  Logo file: ./logo.jpg — place as <img> in the NAV. "
            f"If the logo has a white/light background, apply CSS `mix-blend-mode: multiply` so it blends cleanly.\n"
        )
    else:
        logo_line = "  No logo available — use business name as text in NAV.\n"

    if brand.get("colors"):
        hex_list = ", ".join(brand["colors"])
        color_instruction = (
            f"  Logo colors detected: {hex_list}.\n"
            f"  Build the palette from these but don't use them alone — add a near-black and a near-white "
            f"for legibility. Contrast can be subtle or obvious; let it breathe naturally.\n"
        )
    else:
        niche_colors = _category_colors(lead)
        hex_list = ", ".join(niche_colors)
        color_instruction = (
            f"  Curated palette for this business type: {hex_list}.\n"
            f"  First = primary accent, second = base/bg, third = headings, fourth = CTA contrast. "
            f"Mix light and dark tones; contrast can be subtle or obvious.\n"
        )

    return f"""You are a web development agent. Write a real production website for {nombre}, a {categoria} in {ciudad}, Argentina.

Use your Write tool to create exactly three files in the current directory:
  styles.css  — complete stylesheet, CSS custom properties, no Tailwind, no Bootstrap
  script.js   — mobile nav toggle + smooth scroll + IntersectionObserver scroll-reveal
  index.html  — full HTML referencing ./styles.css and ./script.js

Do not print code to the terminal. Do not explain. Just write the files.

BUSINESS
  Name:     {nombre}
  Type:     {categoria}
  Address:  {direccion}, {ciudad}, Argentina
  Phone:    {telefono}
  WA link:  {wa_link}
{reviews_line}
BRAND
{logo_line}{color_instruction}
LAYOUT PERSONALITY — follow this structure literally, section by section:
{layout}

DESIGN DIRECTION (typography + mood)
{vibe}
Fonts: pick one from Geist, Outfit, Cabinet Grotesk, Satoshi, Barlow Condensed, DM Serif Display, Bebas Neue. No Inter. No Roboto. Import via @import in styles.css (Google Fonts CDN).

STOCK IMAGES (royalty-free — Unsplash, no copyright, no watermark):
Place 3-4 <img> tags using real Unsplash photo IDs you know from training that match "{categoria}".
URL format: https://images.unsplash.com/photo-PHOTO_ID?w=1200&q=80&auto=format&fit=crop
- Hero: one large image (1200x800 or wider) that sets the mood of the business
- Portfolio/gallery section: 3 real photos replacing any "CSS color block" instruction
- One ambient/lifestyle photo inside Servicios or Proceso
All images: descriptive alt text in Spanish, loading="lazy" on everything below the fold,
width + height attributes set (prevents layout shift). Use object-fit: cover on containers.

TASTE RULES — apply every one:
- Hero headline: font-size clamp(3rem, 7vw, 6.5rem), flush-left per layout, max 2 lines, max 8 words.
- Hero container: min-height: 100dvh. Never height: 100vh (breaks mobile Safari).
- Hero top padding max 5rem. The CTA must be visible without scrolling at 1280px.
- Shadows: always tint to the background hue. On dark bg: 0 4px 24px rgba(0,0,0,.35). On light bg: 0 4px 24px rgba(26,23,20,.10). Never pure black box-shadow.
- Buttons — tactile press: :active {{ transform: scale(0.98) translateY(1px); transition: transform 80ms; }}
- Pick ONE corner-radius rule and use it everywhere: either all-sharp (border-radius: 0), all-soft (12px), or all-pill (999px for interactive only). Never mix systems.
- One accent color for the whole page. No section uses a different accent.
- No em-dash (—) anywhere in copy. Use commas, periods, or colons instead.
- Eyebrow micro-labels (small uppercase tracking): max 1 per 3 sections. Hero counts as 1. No section-number eyebrows.
- Scroll-reveal in script.js: IntersectionObserver with threshold 0.15; add class .visible when element enters view. In styles.css: .reveal {{ opacity: 0; transform: translateY(20px); transition: opacity .55s ease, transform .55s ease; }} .reveal.visible {{ opacity: 1; transform: none; }} @media (prefers-reduced-motion: reduce) {{ .reveal, .reveal.visible {{ opacity: 1; transform: none; transition: none; }} }}
- Apply .reveal to section headings, service cards, process steps, testimonials.

HARD BLOCKLIST:
- No status dots, section-number counters (01, 02...)
- No purple/blue mesh gradients or glassmorphism
- No 3 consecutive sections with the same layout family
- No div-based fake product screenshots
- No "calidad", "compromiso", "excelencia", "pasion", "innovacion" in copy
- No 3-equal-column card grids
- No generic testimonial names ("Cliente satisfecho") — use real Argentine names
- No placeholder.com or via.placeholder.com images
- No invented stats or fake-precise numbers

REQUIRED SECTIONS (8 minimum, in the order from LAYOUT PERSONALITY):
  NAV        — logo or business name, phone on desktop, WhatsApp CTA. Max height 72px.
  HERO       — follow layout personality exactly. Real Unsplash image. min-height: 100dvh.
  SERVICIOS  — 4 real services specific to "{categoria}"
  PROCESO    — 3-5 steps in niche-specific language, one photo alongside
  PORTFOLIO  — 3 real Unsplash photos (override any "CSS color blocks" instruction here)
  TESTIMONIOS — 3 testimonials, Argentine register, real names, max 3 lines each
  CONTACTO   — address, phone, prominent WhatsApp CTA, one ambient Unsplash bg image
  FOOTER     — year, city, business name; minimal

COPY: Argentine Spanish, informal vos. No emojis in HTML. No em-dashes. Max 8-word headlines, max 25-word subtext. No filler verbs (elevar, revolucionar, innovar).

CSS:
  - All colors/fonts/spacing as CSS custom properties in :root
  - Mobile-first, breakpoints 768px and 1100px
  - cursor: pointer on all interactive elements
  - Hover transitions: 150-250ms ease on color/opacity only (not transform)
  - :active on buttons: transform: scale(0.98) translateY(1px)
  - :focus-visible rings: 2px solid var(--color-accent), offset 2px
  - @media (prefers-reduced-motion: reduce): disable all transitions and reveal animations
  - No inline <style> or <script> in index.html

HTML:
  - First tag inside <head>: <meta charset="UTF-8"> — mandatory, español needs it
  - <html lang="es">
  - Proper <title> and <meta name="description"> with city + category
  - All Spanish text: proper characters ñ, á, é, í, ó, ú, ü, ¿, ¡

WHATSAPP:
  - Floating button: fixed bottom-right, 56x56px, z-index 50, background #25D366
  - SVG icon inline (no external src), aria-label="Escribinos por WhatsApp"
  - At least 2 inline CTAs in body sections + the floating button
  - Link everywhere: {wa_link}

Write styles.css first, then script.js, then index.html.
"""


def _run_claude_agent(project_path: Path, prompt: str, timeout: int = 1200) -> bool:
    """
    Invoke Claude Code as autonomous agent inside project_path.
    Returns True if index.html exists after the run.
    """
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    log_file = project_path / "claude.log"

    print(f"{Fore.CYAN}   Ejecutando Claude Code en: {project_path.name}/")
    try:
        with open(log_file, "w") as log:
            subprocess.run(
                ["claude", "--permission-mode", "bypassPermissions", prompt],
                cwd=str(project_path),
                env=env,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
            )
    except subprocess.TimeoutExpired:
        print(f"{Fore.YELLOW}   Timeout despues de {timeout}s")
    except FileNotFoundError:
        print(f"{Fore.RED}   Error: 'claude' CLI no encontrado en PATH")
    except Exception as e:
        print(f"{Fore.YELLOW}   Error inesperado: {e}")

    return (project_path / "index.html").exists()


def _build_fallback_html(lead: dict) -> str:
    """Fallback single-file HTML when the agent fails to produce index.html."""
    nombre = lead.get("nombre") or lead.get("title", "Amoblamientos")
    telefono = lead.get("telefono") or lead.get("phone", "")
    direccion = lead.get("direccion") or lead.get("street", "Rosario")
    ciudad = lead.get("ciudad") or lead.get("city", "Rosario")
    categoria = lead.get("categoryName") or lead.get("categoria", "muebles a medida")

    phone_digits = re.sub(r"[^\d]", "", telefono)
    if not phone_digits.startswith("54"):
        phone_digits = "54" + phone_digits
    wa_link = f"https://wa.me/{phone_digits}?text=Hola%2C%20quer%C3%ADa%20consultar%20sobre%20sus%20muebles"

    safe_nombre = nombre.replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    safe_dir = direccion.replace('"', "&quot;")
    year = datetime.now().year

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="{safe_nombre} — {categoria} en {ciudad}. {safe_dir}.">
  <title>{safe_nombre} | {categoria.title()} — {ciudad}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --cream: #f5f0e8; --dark: #1a1a16; --mid: #3d3d35;
      --accent: #8b5e3c; --light-accent: #c8a882; --border: #d4c5b0;
      --ff-head: 'Playfair Display', Georgia, serif;
      --ff-body: 'Inter', sans-serif;
    }}
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html {{ scroll-behavior: smooth; }}
    body {{ font-family: var(--ff-body); background: var(--cream); color: var(--dark); line-height: 1.6; }}
    .nav {{ position: sticky; top: 0; z-index: 100; background: rgba(245,240,232,0.95); backdrop-filter: blur(8px); border-bottom: 1px solid var(--border); padding: 0 2rem; }}
    .nav__inner {{ max-width: 1100px; margin: 0 auto; height: 64px; display: flex; align-items: center; justify-content: space-between; }}
    .nav__logo {{ font-family: var(--ff-head); font-size: 1.2rem; color: var(--dark); text-decoration: none; }}
    .nav__wa {{ display: flex; align-items: center; gap: .5rem; background: #25d366; color: #fff; padding: .5rem 1.25rem; border-radius: 2rem; text-decoration: none; font-size: .875rem; font-weight: 600; }}
    .hero {{ min-height: 80vh; display: flex; align-items: center; padding: 6rem 2rem 4rem; }}
    .hero__inner {{ max-width: 1100px; margin: 0 auto; }}
    .hero__eyebrow {{ font-size: .8rem; font-weight: 600; letter-spacing: .15em; text-transform: uppercase; color: var(--accent); margin-bottom: 1rem; }}
    .hero__title {{ font-family: var(--ff-head); font-size: clamp(2rem, 5vw, 3.5rem); line-height: 1.1; margin-bottom: 1.5rem; }}
    .hero__title em {{ color: var(--accent); font-style: italic; }}
    .hero__sub {{ color: var(--mid); font-size: 1rem; max-width: 40ch; margin-bottom: 2rem; }}
    .btn {{ display: inline-flex; align-items: center; gap: .5rem; padding: .875rem 2rem; text-decoration: none; font-size: .9rem; font-weight: 600; transition: all .2s; }}
    .btn--primary {{ background: var(--dark); color: var(--cream); }}
    .btn--primary:hover {{ background: var(--accent); }}
    .contact-section {{ padding: 6rem 2rem; background: var(--dark); color: var(--cream); text-align: center; }}
    .btn--wa {{ display: inline-flex; align-items: center; gap: .75rem; background: #25d366; color: #fff; padding: 1.2rem 2.5rem; text-decoration: none; font-size: 1rem; font-weight: 700; margin-top: 2rem; }}
    footer {{ padding: 2rem; text-align: center; background: #111110; color: rgba(245,240,232,.3); font-size: .8rem; }}
    .wa-float {{ position: fixed; bottom: 1.5rem; right: 1.5rem; z-index: 999; width: 56px; height: 56px; border-radius: 50%; background: #25d366; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 16px rgba(37,211,102,.4); text-decoration: none; }}
  </style>
</head>
<body>
<nav class="nav">
  <div class="nav__inner">
    <a href="#" class="nav__logo">{safe_nombre}</a>
    <a href="{wa_link}" class="nav__wa" target="_blank" rel="noopener">WhatsApp</a>
  </div>
</nav>
<header class="hero">
  <div class="hero__inner">
    <p class="hero__eyebrow">{ciudad} &middot; {safe_dir}</p>
    <h1 class="hero__title">Muebles hechos<br>para <em>tu espacio</em></h1>
    <p class="hero__sub">En {safe_nombre} fabricamos a medida porque los espacios no siempre son estandar.</p>
    <a href="{wa_link}" class="btn btn--primary" target="_blank" rel="noopener">Pedir presupuesto</a>
  </div>
</header>
<section class="contact-section">
  <p style="color:rgba(245,240,232,.6);margin-bottom:.5rem">{safe_dir}, {ciudad}</p>
  <p style="color:rgba(245,240,232,.6)">{telefono}</p>
  <a href="{wa_link}" class="btn--wa" target="_blank" rel="noopener">Escribinos por WhatsApp</a>
</section>
<footer><p>&copy; {year} {safe_nombre}. {ciudad}, Argentina.</p></footer>
<a href="{wa_link}" class="wa-float" target="_blank" rel="noopener" aria-label="WhatsApp">
  <svg width="28" height="28" viewBox="0 0 24 24" fill="white"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
</a>
</body>
</html>"""


class ClaudeBuilder:
    def __init__(self):
        self.websites_dir = config.WEBSITES_DIR
        self.websites_dir.mkdir(exist_ok=True)
        self._dataset_index = self._load_dataset_index()

    def _load_dataset_index(self) -> dict:
        ds = DATASET_FILE if DATASET_FILE.exists() else config.DATA_DIR / "dataset.json"
        if not ds.exists():
            return {}
        with open(ds, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {entry.get("phone", ""): entry for entry in data if entry.get("phone")}
        return {}

    def preguntar_interesados(self, status_file: str) -> list[dict]:
        """Show sent leads and ask which ones responded with interest."""
        sf = Path(status_file)
        if not sf.exists():
            print(f"{Fore.RED}Archivo no encontrado: {status_file}")
            return []

        with open(sf, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        con_fecha = [
            r for r in rows
            if r.get("enviado", "").upper() == "SI" and r.get("fecha_envio", "").strip()
        ]

        if not con_fecha:
            print(f"{Fore.YELLOW}Sin leads enviados con fecha registrada")
            return []

        ultima_fecha = max(r["fecha_envio"][:10] for r in con_fecha)
        contactados = [r for r in con_fecha if r["fecha_envio"][:10] == ultima_fecha]

        print(f"{Fore.CYAN}   Sesion: {ultima_fecha} — {len(contactados)} leads enviados")
        print(f"\n{'='*60}")
        print("LEADS CONTACTADOS — cuales estan interesados?")
        print(f"{'='*60}")
        for i, lead in enumerate(contactados, 1):
            resp = lead.get("estado_respuesta", "")
            resp_label = f" [{resp}]" if resp else ""
            score = lead.get("score", "")
            score_label = f" score:{score}" if score else ""
            print(f"  [{i:2}]  {lead['nombre']:40s}  {lead['telefono']}{resp_label}{score_label}")
        print(f"{'='*60}")
        print("  Indices separados por coma (ej: 1, 3).  Enter = ninguno")

        entrada = input("\n  Interesados: ").strip()
        if not entrada:
            print(f"{Fore.YELLOW}Sin seleccion")
            return []

        interesados = []
        for token in entrada.split(","):
            token = token.strip()
            if not token.isdigit():
                continue
            idx = int(token) - 1
            if not (0 <= idx < len(contactados)):
                print(f"{Fore.YELLOW}  Indice {token} invalido")
                continue
            row = contactados[idx]
            telefono = row["telefono"]
            dataset_entry = self._dataset_index.get(telefono, {})
            interesados.append(
                {
                    "nombre": row["nombre"],
                    "telefono": telefono,
                    "direccion": dataset_entry.get("street") or row.get("direccion", "Rosario"),
                    "ciudad": dataset_entry.get("city") or row.get("ciudad", "Rosario"),
                    "puntaje": dataset_entry.get("totalScore") or row.get("puntaje", ""),
                    "resenas": dataset_entry.get("reviewsCount") or row.get("resenas", 0),
                    "categoryName": dataset_entry.get("categoryName") or row.get("categoria", ""),
                    "categories": dataset_entry.get("categories", []),
                    "score": row.get("score", ""),
                }
            )

        if interesados:
            config.DATA_DIR.mkdir(exist_ok=True)
            with open(INTERESADOS_FILE, "w", encoding="utf-8") as f:
                json.dump(interesados, f, ensure_ascii=False, indent=2)
            print(f"\n{Fore.GREEN}{len(interesados)} interesado(s) guardados")

        return interesados

    def generar_web(self, lead: dict, project_path: Path) -> bool:
        """
        Generate website for a single lead.
        Invokes Claude Code as agent inside project_path; falls back to static HTML on failure.
        Returns True on success.
        """
        nombre = lead.get("nombre") or lead.get("title", "Negocio")
        telefono = lead.get("telefono") or lead.get("phone", "")
        print(f"{Fore.MAGENTA}Generando web para: {nombre}")

        brand = _fetch_brand_assets(telefono, project_path)
        if brand.get("logo_path"):
            print(f"{Fore.CYAN}   Logo extraído de WhatsApp")
        if brand.get("colors"):
            print(f"{Fore.CYAN}   Colores de marca: {', '.join(brand['colors'])}")

        prompt = _build_agent_prompt(lead, brand)

        if _run_claude_agent(project_path, prompt):
            print(f"{Fore.GREEN}   Generada en {project_path}")
            return True

        print(f"{Fore.YELLOW}   index.html no encontrado — usando fallback")
        fallback = _build_fallback_html(lead)
        (project_path / "index.html").write_text(fallback, encoding="utf-8")
        print(f"{Fore.YELLOW}   Fallback escrito en {project_path}")
        return True

    def generar_para_interesados(self, status_file: str) -> list[str] | None:
        """Prompt for interested leads, generate websites, update CSV."""
        interesados = self.preguntar_interesados(status_file)
        if not interesados:
            return None

        sf = Path(status_file)
        with open(sf, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = list(reader.fieldnames or [])

        rows_by_phone = {r["telefono"]: r for r in rows}
        session_paths = []

        for lead in interesados:
            nombre = lead["nombre"]
            telefono = lead["telefono"]

            folder = re.sub(r"[^a-z0-9_]", "", nombre.lower().replace(" ", "_"))[:50]
            project_path = self.websites_dir / folder
            project_path.mkdir(exist_ok=True)

            if self.generar_web(lead, project_path):
                if telefono in rows_by_phone:
                    rows_by_phone[telefono]["project_path"] = str(project_path)
                session_paths.append(str(project_path))

        if session_paths:
            with open(sf, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print(f"\n{Fore.GREEN}Websites generados: {len(session_paths)}")

        return session_paths
