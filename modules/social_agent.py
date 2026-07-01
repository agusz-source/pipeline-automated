#!/usr/bin/env python3
"""
Social Media Agent — generates and publishes Instagram posts.
Uses: Claude Haiku (copy), Pexels free API (images), Instagram Graph API (posting).
Zero additional paid services required.
"""
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

INSTAGRAM_GRAPH = "https://graph.facebook.com/v21.0"
PEXELS_API      = "https://api.pexels.com/v1"

# ── Post types ────────────────────────────────────────────────

POST_TYPES = {
    "servicio":    "destacando el servicio principal o producto estrella del negocio",
    "motivacional":"un mensaje motivacional o inspirador relacionado al rubro",
    "tip":         "un consejo util o dato interesante para los clientes",
    "promo":       "una promocion o descuento atractivo para atraer clientes nuevos",
    "comunidad":   "invitando a la comunidad local a conocer el negocio o dejar una resena",
}

# ── Stock image search keywords per niche ─────────────────────

_NICHE_QUERIES = {
    "estetica":      ["beauty salon modern interior", "nail art studio professional", "spa relaxation candles"],
    "amoblamientos": ["modern furniture showroom", "custom wood furniture workshop", "interior design living room"],
    "gimnasio":      ["modern gym workout equipment", "fitness training session", "crossfit box interior"],
    "cerrajeria":    ["locksmith professional tools", "keys security hardware", "door lock installation"],
    "default":       ["professional small business", "local entrepreneur working", "modern office workspace"],
}


def _niche_key(categoria: str) -> str:
    cat = (categoria or "").lower()
    if any(x in cat for x in ["estetic", "peluq", "belleza", "nail", "spa", "manicur"]):
        return "estetica"
    if any(x in cat for x in ["muebl", "amoblam", "carpint", "madera", "placard"]):
        return "amoblamientos"
    if any(x in cat for x in ["gimnas", "gym", "fitness", "crossfit", "pilates", "yoga", "boxeo"]):
        return "gimnasio"
    if any(x in cat for x in ["cerraj", "llave", "duplicado"]):
        return "cerrajeria"
    return "default"


# ── Content generation ────────────────────────────────────────

def generate_post_content(client: dict, post_type: str = "servicio") -> dict:
    """
    Generate Instagram caption + hashtags using Claude Haiku.
    Returns: {caption, hashtags, image_query, full_caption, post_type}
    """
    from config import config
    import anthropic

    nombre    = client.get("nombre", "el negocio")
    categoria = client.get("categoria", "negocio local")
    ciudad    = client.get("ciudad", "Rosario")
    tipo_desc = POST_TYPES.get(post_type, POST_TYPES["servicio"])

    prompt = f"""Sos un community manager experto en redes sociales para pequeños negocios argentinos.
Generá un post de Instagram para este negocio:

Negocio: {nombre}
Rubro: {categoria}
Ciudad: {ciudad}
Tipo de post: {tipo_desc}

Respondé SOLO con un JSON válido, sin texto adicional:
{{
  "caption": "Texto del post en español argentino, máximo 180 caracteres, natural y auténtico. Máximo 2 emojis.",
  "hashtags": ["hashtag1sin#", "hashtag2sin#"],
  "image_query": "3-4 word English query for a stock photo that fits this post"
}}

Incluí 12-15 hashtags: mezcla español e inglés, locales (Rosario) y del rubro."""

    ac = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = ac.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:])
        if raw.endswith("```"):
            raw = raw[:-3]

    data = json.loads(raw.strip())
    tags = " ".join(f"#{h.strip('#').replace(' ', '_')}" for h in data.get("hashtags", []))
    data["full_caption"] = f"{data['caption']}\n.\n.\n.\n{tags}"
    data["post_type"] = post_type
    return data


# ── Image fetching ────────────────────────────────────────────

def get_image_url(query: str, fallback_niche: str = "default") -> str:
    """
    Get a relevant photo URL.
    Priority: Pexels API (free key required) → Picsum (no key, random).
    """
    from config import config
    key = config.PEXELS_API_KEY

    if key:
        for q in [query, _NICHE_QUERIES.get(fallback_niche, ["business"])[0]]:
            try:
                r = requests.get(
                    f"{PEXELS_API}/search",
                    headers={"Authorization": key},
                    params={"query": q, "per_page": 5, "orientation": "square"},
                    timeout=10,
                )
                r.raise_for_status()
                photos = r.json().get("photos", [])
                if photos:
                    return photos[0]["src"]["large"]
            except Exception:
                continue

    # Picsum fallback — deterministic seed from query so same query = same image
    seed = abs(hash(query)) % 9999
    return f"https://picsum.photos/seed/{seed}/1080/1080"


# ── Instagram publishing ──────────────────────────────────────

def _ig_create_container(token: str, ig_user_id: str, image_url: str, caption: str) -> str:
    """Step 1: Create media container. Returns container_id."""
    r = requests.post(
        f"{INSTAGRAM_GRAPH}/{ig_user_id}/media",
        data={"image_url": image_url, "caption": caption, "access_token": token},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def _ig_wait_container(token: str, container_id: str, max_wait: int = 90) -> bool:
    """Poll until container is FINISHED processing."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        r = requests.get(
            f"{INSTAGRAM_GRAPH}/{container_id}",
            params={"fields": "status_code", "access_token": token},
            timeout=10,
        )
        status = r.json().get("status_code", "")
        if status == "FINISHED":
            return True
        if status == "ERROR":
            return False
        time.sleep(4)
    return False


def _ig_publish_container(token: str, ig_user_id: str, container_id: str) -> str:
    """Step 2: Publish the container. Returns media_id."""
    r = requests.post(
        f"{INSTAGRAM_GRAPH}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def publish_post(client: dict, post_type: str = "servicio") -> dict:
    """
    Full flow: generate content → fetch image → publish to Instagram.
    Returns result dict with media_id, caption, image_url.
    """
    from config import config

    token      = config.INSTAGRAM_ACCESS_TOKEN
    ig_user_id = config.INSTAGRAM_BUSINESS_ID

    if not token or not ig_user_id:
        raise ValueError("Configurá INSTAGRAM_ACCESS_TOKEN e INSTAGRAM_BUSINESS_ID en .env")

    content   = generate_post_content(client, post_type)
    niche     = _niche_key(client.get("categoria", ""))
    image_url = get_image_url(content.get("image_query", "business"), niche)

    container_id = _ig_create_container(token, ig_user_id, image_url, content["full_caption"])

    if not _ig_wait_container(token, container_id):
        raise RuntimeError(f"Container {container_id} no procesó — revisá la URL de imagen")

    media_id = _ig_publish_container(token, ig_user_id, container_id)

    return {
        "media_id":    media_id,
        "caption":     content["caption"],
        "hashtags":    content.get("hashtags", []),
        "image_url":   image_url,
        "full_caption": content["full_caption"],
        "post_type":   post_type,
        "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ── Connection tests ─────────────────────────────────────────

def test_connections() -> dict:
    from config import config
    results = {}

    # Anthropic
    try:
        import anthropic
        ac = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        ac.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=5,
            messages=[{"role": "user", "content": "hi"}]
        )
        results["anthropic"] = ("ok", "Claude Haiku respondio")
    except Exception as e:
        results["anthropic"] = ("error", str(e)[:80])

    # Pexels
    if config.PEXELS_API_KEY:
        try:
            r = requests.get(
                f"{PEXELS_API}/search",
                headers={"Authorization": config.PEXELS_API_KEY},
                params={"query": "business", "per_page": 1},
                timeout=5,
            )
            r.raise_for_status()
            results["pexels"] = ("ok", "API key valida")
        except Exception as e:
            results["pexels"] = ("error", str(e)[:80])
    else:
        results["pexels"] = ("warn", "Sin clave — usando Picsum (sin busqueda por categoria)")

    # Instagram
    if config.INSTAGRAM_ACCESS_TOKEN and config.INSTAGRAM_BUSINESS_ID:
        try:
            r = requests.get(
                f"{INSTAGRAM_GRAPH}/{config.INSTAGRAM_BUSINESS_ID}",
                params={"fields": "id,username,name", "access_token": config.INSTAGRAM_ACCESS_TOKEN},
                timeout=5,
            )
            r.raise_for_status()
            d = r.json()
            results["instagram"] = ("ok", f"@{d.get('username', d.get('id', '?'))}")
        except Exception as e:
            results["instagram"] = ("error", str(e)[:80])
    else:
        results["instagram"] = ("warn", "Sin configurar — solo generacion de contenido disponible")

    return results


# ── CLI ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Social Media Agent — Binario Websites")
    p.add_argument("--test",     action="store_true", help="Testear conexiones")
    p.add_argument("--generate", action="store_true", help="Generar contenido (sin publicar)")
    p.add_argument("--publish",  action="store_true", help="Generar y publicar en Instagram")
    p.add_argument("--nombre",    default="Mi Negocio")
    p.add_argument("--categoria", default="estetica")
    p.add_argument("--tipo",      default="servicio", choices=list(POST_TYPES.keys()))
    args = p.parse_args()

    GREEN = "\033[92m"; YELLOW = "\033[93m"; RED = "\033[91m"; RESET = "\033[0m"

    if args.test:
        print("\nTestando conexiones del Social Agent...\n")
        for svc, (status, msg) in test_connections().items():
            icon = GREEN + "✅" if status == "ok" else (YELLOW + "⚠️ " if status == "warn" else RED + "❌")
            print(f"  {icon}{RESET}  {svc:<14} {msg}")
        print()

    elif args.generate or args.publish:
        client = {"nombre": args.nombre, "categoria": args.categoria, "ciudad": "Rosario"}
        print(f"\nGenerando post: {args.nombre} ({args.categoria}) — tipo: {args.tipo}\n")

        content = generate_post_content(client, args.tipo)
        niche   = _niche_key(args.categoria)
        img_url = get_image_url(content.get("image_query", "business"), niche)

        print(f"  Caption:   {content['caption']}")
        print(f"  Tags:      {len(content.get('hashtags', []))} hashtags")
        print(f"  Imagen:    {img_url}")
        print(f"\n--- Full caption ---\n{content['full_caption']}\n")

        if args.publish:
            print("Publicando en Instagram...")
            result = publish_post(client, args.tipo)
            print(f"{GREEN}✅ Publicado — media_id: {result['media_id']}{RESET}")
    else:
        p.print_help()
