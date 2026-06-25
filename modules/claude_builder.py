#!/usr/bin/env python3
"""
Website generator — Claude Code agent writes files directly into each project folder.
Flow: Python creates folder → invokes claude --permission-mode bypassPermissions → Claude writes files to disk.
"""

import csv
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from colorama import Fore, init

from config import config

init(autoreset=True)

INTERESADOS_FILE = config.INTERESADOS_FILE
DATASET_FILE = config.DATASET_FILE

_DESIGN_ARCHETYPES = [
    {
        "name": "brutal_workshop",
        "palette_hint": "near-white #F0ECE3, raw black #0D0D0D, construction orange #FF5500, mid-grey #888888",
        "type_hint": "Space Grotesk 900 for headings, IBM Plex Mono for labels/metadata",
        "structure_hint": "Brutalist grid: sections bordered by 2px black lines, oversized section numbers (01, 02…) as typographic anchors in top-left of each block, zero decorative softness",
        "hero_hint": "Giant heading flush-left at clamp(3rem,8vw,7rem), a 2px horizontal rule below it, then address in Mono and a sharp CTA. No gradient, no rounded corners, no shadows.",
        "layout_twist": "Each section has a large typographic counter (01 SERVICIOS, 02 PROCESO…) in the top-left in Space Grotesk 900 at 15vw opacity-10 — decorative but structural. Service cards are full-width bordered rows, not a card grid.",
        "visual_trick": "CSS hatching texture via repeating-linear-gradient(45deg, #0D0D0D 1px, transparent 1px) at very low opacity for subtle depth. Section dividers are 2px solid black lines, nothing else.",
        "copy_tone": "Direct, zero-fluff Argentine workshop energy. Short declarative sentences. No softening adjectives.",
    },
    {
        "name": "editorial_magazine",
        "palette_hint": "warm off-white #FAF8F3, charcoal #1C1C1A, muted gold #C9A84C, light stone #E8E2D9",
        "type_hint": "Playfair Display italic 700 for display headings, Lato 300/400 for body — classic editorial contrast",
        "structure_hint": "Irregular CSS grid columns (7fr 5fr), pull-quotes as visual anchors, full-bleed typographic interludes between content sections",
        "hero_hint": "Large italic Playfair headline spanning 70% width, overlined eyebrow in uppercase tracked 0.2em, a 1px gold horizontal rule, then a short punchy subheadline in Lato 300.",
        "layout_twist": "Alternating text-left/text-right sections using CSS grid with named areas. One section rotates a decorative background word 90deg (like 'MADERA' or 'TALLER') as a typographic watermark. An SVG ruler illustration acts as the portfolio/process divider.",
        "visual_trick": "SVG horizontal rule with measured tick marks like a woodworking ruler — rendered inline between sections as a visual metaphor.",
        "copy_tone": "Thoughtful, craft-forward. Talks about the work as if it matters because it does.",
    },
    {
        "name": "anti_polish_raw",
        "palette_hint": "paper white #FAFAF8, pencil grey #4A4A4A, marker black #1A1A1A, kraft brown #C4A77D, red-ink accent #D63A2F",
        "type_hint": "Amatic SC for headings (hand-drawn feel), Cabin for body — indie craft personality",
        "structure_hint": "Cards with slight CSS rotations via nth-child (rotate(-1.5deg), rotate(1deg), rotate(-0.5deg)), ruled-line backgrounds on testimonial sections, stamp-like section badges",
        "hero_hint": "Title in Amatic SC at clamp(3rem,7vw,6rem), underlined with a thick 4px red-ink border-bottom, short punchy subheadline in Cabin, CTA styled like a rubber stamp (border: 2px solid, uppercase, tracked).",
        "layout_twist": "Service cards each rotated slightly with nth-child CSS — they look pinned to a corkboard. Testimonials styled as sticky notes (slightly yellow background, rotate, box-shadow). Process steps are handwritten-style numbered circles with a dashed connecting line.",
        "visual_trick": "CSS ::before pseudo-elements simulate washi tape in the top corners of each card — a thin colored strip rotated 45deg. No images needed.",
        "copy_tone": "Casual, warm, human. Like a neighbour recommending their own carpenter with genuine enthusiasm.",
    },
    {
        "name": "showroom_dark",
        "palette_hint": "near-black #0A0A08, off-white #F2F0EB, warm gold #C9973A, dark mid-grey #2A2A27",
        "type_hint": "Cormorant Garamond 300 for large display headings, Inter 400 for body — luxury contrast",
        "structure_hint": "Dark luxury: minimal text density, very generous vertical padding (min 8rem per section), text centered on dark backgrounds, single accent color used sparingly",
        "hero_hint": "Full-viewport-height section, centered headline in Cormorant at clamp(2.5rem,5vw,5rem) weight 300, one-line subtitle in Inter 400, gold-bordered CTA with transparent background (border: 1px solid gold, color: gold).",
        "layout_twist": "Horizontal CSS scroll-snap showcase for services/portfolio — users swipe through cards, no JS pagination library. A counter section with huge Cormorant numbers (01, 02…) next to short stat labels. Gold 1px ::before/::after lines flanking section headings as decoration.",
        "visual_trick": "Thin 1px gold lines as CSS pseudo-element decorators flanking h2 headings: content: ''; display: block; width: 40px; height: 1px; background: gold; — centered above or beside heading.",
        "copy_tone": "Understated confidence. Never boastful. The work speaks; the copy just introduces it.",
    },
    {
        "name": "nature_craft",
        "palette_hint": "terracotta #C67B5C, sand beige #D4C4A8, warm clay #B5651D, soft cream #F5F0E1, olive #6B7B3C",
        "type_hint": "Fraunces (variable, optical size) for headings, Source Sans 3 for body — organic editorial warmth",
        "structure_hint": "Earthy and organic: sections alternate between cream and sand backgrounds, CSS grain overlay at 8% opacity on hero, border-radius used organically (blob shapes on decorative elements, not on cards)",
        "hero_hint": "Organic layout: heading in Fraunces italic at clamp(2.5rem,5vw,4.5rem) in warm clay on cream, a small olive-colored leaf SVG ornament (draw it inline), then address and CTA. Background is cream, not a photo.",
        "layout_twist": "Process steps shown as a winding path: each step has a left or right border (alternating), connected by a vertical dashed line — like a hand-drawn map route, not numbered boxes in a grid. Testimonials in earthy-colored asymmetric quote blocks.",
        "visual_trick": "An inline SVG wood-grain decoration (a few parallel wavy lines) used as section divider. CSS grain overlay on the hero: background-image: url(\"data:image/svg+xml,...\") for noise texture.",
        "copy_tone": "Warm, process-proud, sustainable in spirit. Talks about materials and craft with genuine care — not performative.",
    },
    {
        "name": "split_grid_industrial",
        "palette_hint": "concrete #B0A99F, warm black #1A1714, amber #E8A020, raw white #F7F5F2",
        "type_hint": "Barlow Condensed 700-900 for headings, Barlow 400 for body — industrial utility type",
        "structure_hint": "Asymmetric CSS grid throughout: hero is 60/40 split, services in a staggered pattern (full-width → two columns → full-width), amber accent bars as section separators",
        "hero_hint": "Split screen: left 60% has headline in Barlow Condensed at clamp(3rem,7vw,6rem) weight 800, address and CTA below. Right 40% has a CSS geometric composition — interlocking rectangles in concrete/amber referencing furniture joints or wood joinery. Pure CSS, no images.",
        "layout_twist": "Services: first card full-width, next two side-by-side, last card full-width again — staggered rhythm breaks the boring grid. CSS clip-path diagonal cuts (polygon(0 0, 100% 0, 100% 88%, 0 100%)) on section transitions instead of straight horizontal borders.",
        "visual_trick": "Amber accent bars — a 4px solid amber horizontal line — used as visual separator and section introduction. CSS clip-path diagonal transitions between sections.",
        "copy_tone": "Workshop-honest. Talks about craft like a builder explaining their process to a client — practical, confident, no marketing veneer.",
    },
    {
        "name": "boutique_warm",
        "palette_hint": "cream #F8F3EE, sand #E8DDD0, terracotta accent #C0705A, deep forest green #2D4A3E",
        "type_hint": "DM Serif Display italic for headings, DM Sans 400/500 for body — boutique warmth",
        "structure_hint": "Warm residential feel: curved section dividers (a div with border-radius 50% acting as a wave), overlapping cards via negative margins on desktop, green accent used only on CTAs and highlights",
        "hero_hint": "Full narrative: eyebrow in DM Sans small-caps, large DM Serif italic headline across 2-3 lines, a short personal-voice subtitle, then two CTAs side by side — WhatsApp (terracotta fill) and 'Ver nuestros trabajos' (outlined).",
        "layout_twist": "Testimonials use an offset layout: odd items float-left with left padding, even items float-right with right padding, and they overlap slightly — not a grid, not a carousel. A section with a large decorative DM Serif Display italic quote in the background at low opacity.",
        "visual_trick": "Section background alternates cream/sand with a curved divider div between them (height: 80px, border-radius: 0 0 50% 50% / 0 0 100% 100%, background from previous section color). Creates a soft wavy visual rhythm.",
        "copy_tone": "Personal, boutique warmth. Talks to you like the owner would in the showroom — knowledgeable, relaxed, proud of their work.",
    },
    {
        "name": "retro_print",
        "palette_hint": "aged paper #F2ECD8, deep ink #1A1208, rust red #B33A1E, olive stamp #4A5C2B",
        "type_hint": "Libre Baskerville for headings, Space Mono for labels/metadata/prices — letterpress printing echo",
        "structure_hint": "Letterpress grid: content in constrained columns (max 720px centered), large typographic ornaments (asterisms, section dividers from Unicode), stamp-like badges, ruled lines as dividers",
        "hero_hint": "Large Libre Baskerville headline with a CSS double-border box around it (outline + border, gap via padding), subtitle in Space Mono uppercase tracked 0.1em, aged-paper background (#F2ECD8), rust-red accent on key words.",
        "layout_twist": "Service items styled as receipt/invoice line items — Space Mono, dotted border-bottom, a 'price on request' label in olive. One large decorative typographic seal (CSS-drawn circle with text on path using SVG textPath) in the trust section. Process steps look like a numbered list from a 1970s instruction manual.",
        "visual_trick": "CSS noise grain on hero: a pseudo-element with repeating-conic-gradient or SVG feTurbulence filter for that aged-print texture. Rust-red rubber-stamp style badges (border: 2px solid rust, rotate(-5deg), uppercase) on section headings.",
        "copy_tone": "Honest, slightly humorous, old-school craft pride. Aware of their own history. No Instagram-speak.",
    },
]


def _pick_archetype(lead: dict, idx: int = 0) -> dict:
    """Pick a design archetype based on business name hash for consistency."""
    name = lead.get("nombre", lead.get("title", ""))
    h = sum(ord(c) for c in name) % len(_DESIGN_ARCHETYPES)
    return _DESIGN_ARCHETYPES[h]


def _build_agent_prompt(lead: dict, archetype: dict) -> str:
    """Build prompt for Claude Code agent — instructs it to write website files to disk."""
    nombre = lead.get("nombre") or lead.get("title", "Amoblamientos")
    telefono = lead.get("telefono") or lead.get("phone", "")
    direccion = lead.get("direccion") or lead.get("street", "Rosario")
    ciudad = lead.get("ciudad") or lead.get("city", "Rosario")
    categoria = lead.get("categoryName") or lead.get("categoria", "muebles a medida")
    categoria_title = categoria.title()
    resenas = lead.get("resenas") or lead.get("reviewsCount", 0)
    puntaje = lead.get("puntaje") or lead.get("totalScore", "")

    phone_digits = re.sub(r"[^\d]", "", telefono)
    if not phone_digits.startswith("54"):
        phone_digits = "54" + phone_digits
    wa_link = f"https://wa.me/{phone_digits}?text=Hola%2C%20quer%C3%ADa%20consultar%20sobre%20sus%20muebles"

    reviews_note = ""
    if resenas and int(resenas) > 0:
        reviews_note = (
            f"  Google rating: {puntaje} stars ({resenas} reviews)"
            if puntaje
            else f"  {resenas} Google reviews"
        )

    return f"""You are a web development agent. Your task: build a production website for a real Argentine furniture workshop. Not a template. Not a UI kit screenshot. A real site the owner would be proud to show their clients.

TASK — use your Write tool to create exactly three files in the current directory:
  1. styles.css  — complete stylesheet, CSS custom properties, no Tailwind
  2. script.js   — minimal vanilla JS only (mobile nav toggle, smooth scroll)
  3. index.html  — complete HTML referencing ./styles.css and ./script.js

Write directly to disk. Do not print code in the terminal. Do not explain what you are doing.

───────────────────────────────────────────────
BUSINESS
  Name:     {nombre}
  Category: {categoria}
  Address:  {direccion}, {ciudad}, Argentina
  Phone:    {telefono}
  WA link:  {wa_link}
{reviews_note}
───────────────────────────────────────────────
DESIGN ARCHETYPE — {archetype["name"].upper().replace("_", " ")}

  Palette:      {archetype["palette_hint"]}
  Typography:   {archetype["type_hint"]}
  Structure:    {archetype["structure_hint"]}
  Hero:         {archetype["hero_hint"]}
  Layout twist: {archetype["layout_twist"]}
  Visual trick: {archetype["visual_trick"]}
  Copy tone:    {archetype["copy_tone"]}

Implement every line of the archetype literally. These are not mood-board suggestions.
───────────────────────────────────────────────
THE SLOP TEST — run this before writing each section:

  1. "Could this section appear unchanged on a dental clinic?" → Yes = rewrite it around furniture.
  2. "Are 3+ consecutive sections just [icon] [heading] [paragraph]?" → Yes = break the pattern.
  3. "Is my hero a headline + subtitle + button on a gradient or stock-photo placeholder?" → Yes = follow archetype hero instead.
  4. "Do I use calidad, compromiso, excelencia, pasión, or innovación anywhere?" → Delete every instance.
  5. "Do my testimonials sound like a brand wrote them?" → Replace with specific Argentine-register moments.
───────────────────────────────────────────────
REQUIRED SECTIONS — 8 minimum, in this order:

  NAV         Logo ({nombre}), phone number visible on desktop, WhatsApp CTA button
  HERO        Follow archetype hero instructions exactly — do not invent a different layout
  SERVICIOS   4 services specific to "{categoria}" — name each with a real description, not just "Diseño a medida"
  PROCESO     3-5 steps with furniture-specific language (measurement visit → material selection → workshop build → install)
  PORTFOLIO   CSS-only visual showcase — use geometric shapes, color blocks, or CSS art; no <img> to external URLs
  TESTIMONIOS 3 testimonials — real Argentine voices, specific problems, specific solutions
                BAD:  "Muy buena atención, los recomiendo ampliamente."
                GOOD: "Tenia una cocina en L con una columna de gas en el medio y tres presupuestistas me dijeron que era imposible. Me lo resolvieron en la primera visita y quedó perfecto."
  TRUST       3 differentiators specific to this business — not generic promises applicable to any company
  CONTACTO    Address, phone, WhatsApp CTA prominent, neighborhood reference if useful
  FOOTER      Year, city, business name — minimal
───────────────────────────────────────────────
COPY RULES:
  - All text in Argentine Spanish, informal vos register (not forced, just natural)
  - Zero invented statistics — no "15 años de experiencia", "500 clientes" unless data above provides them
  - No em-dashes, no ellipses, no excessive exclamation marks
  - No emoji anywhere in the HTML
  - Testimonial names: use common Argentine first names (Mariana, Diego, Florencia, Sebastián)
───────────────────────────────────────────────
TYPOGRAPHY:
  - @import the archetype fonts from Google Fonts at top of styles.css
  - --ff-display and --ff-body as CSS custom properties
  - h1 uses display font; h2/h3 can mix; labels/metadata use body or mono
  - Line-height: 1.1-1.25 headings, 1.6-1.75 body
  - Body text max-width: 65ch per line
───────────────────────────────────────────────
CSS & LAYOUT:
  - CSS custom properties for ALL colors, fonts, spacing scale
  - Mobile-first; breakpoints at 768px and 1100px minimum
  - Implement archetype layout_twist and visual_trick literally — these are CSS techniques, not vibes
  - Varied vertical rhythm: sections are NOT all the same padding
  - z-index scale: 10 content, 20 sticky nav, 50 floating button, 999 overlay
───────────────────────────────────────────────
ACCESSIBILITY & INTERACTION:
  - cursor: pointer on ALL clickable/hoverable elements — cards, buttons, links, nav items
  - Hover transitions: 150-250ms ease on color and opacity (not width or height)
  - Visible focus rings: outline: 2px solid <accent>; outline-offset: 2px on :focus-visible
  - All SVGs and meaningful visuals: aria-label or role="img" + aria-label
  - @media (prefers-reduced-motion: reduce) block that disables all transition and animation
───────────────────────────────────────────────
WHATSAPP:
  - Floating button: position fixed, bottom: 1.5rem, right: 1.5rem, 56×56px, z-index 50, background #25D366
  - SVG WhatsApp icon inside (draw the path inline, no external source)
  - aria-label="Escribinos por WhatsApp"
  - Minimum 2 inline WhatsApp CTAs within body sections
  - Exact link everywhere: {wa_link}
───────────────────────────────────────────────
TECHNICAL CONSTRAINTS:
  - No inline <style> or <script> blocks in index.html
  - No external JS libraries (no jQuery, no GSAP, no Alpine)
  - No <img> tags pointing to http/https external URLs
  - <html lang="es">
  - <title>{nombre} | {categoria_title} en {ciudad}</title>
  - <meta name="description" content="..."> with real local SEO value (mention city, category, address)
  - <meta name="viewport" content="width=device-width, initial-scale=1">

Write styles.css first, then script.js, then index.html.
"""


def _run_claude_agent(project_path: Path, prompt: str, timeout: int = 1200) -> bool:
    """
    Invoke Claude Code as autonomous agent inside project_path.
    Returns True if index.html exists after the run.
    """
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

    print(f"{Fore.CYAN}   Ejecutando Claude Code en: {project_path.name}/")
    try:
        subprocess.run(
            ["claude", "--permission-mode", "bypassPermissions", prompt],
            cwd=str(project_path),
            env=env,
            timeout=timeout,
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
        nombre = lead.get("nombre") or lead.get("title", "Amoblamientos")
        print(f"{Fore.MAGENTA}Generando web para: {nombre}")

        archetype = _pick_archetype(lead)
        print(f"   Arquetipo: {archetype['name']}")

        prompt = _build_agent_prompt(lead, archetype)

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
