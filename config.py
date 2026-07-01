import os
from pathlib import Path
from dotenv import load_dotenv

# ROOT always resolves to the actual repo directory regardless of folder name
ROOT = Path(__file__).parent.resolve()

load_dotenv(ROOT / ".env")


class Config:
    BASE_DIR = ROOT
    DATA_DIR = ROOT / "data"
    LOGS_DIR = ROOT / "logs"
    TEMPLATES_DIR = ROOT / "templates"
    WEBSITES_DIR = ROOT / "websites"

    # ── Data files ────────────────────────────────────────────
    DATASET_FILE = ROOT / "dataset.json"
    STATUS_FILE = DATA_DIR / "estado.csv"
    INTERESADOS_FILE = DATA_DIR / "interesados.json"
    CONVERSACIONES_FILE = DATA_DIR / "conversaciones.json"
    FINANZAS_FILE = DATA_DIR / "finanzas.json"
    BLACKLIST_FILE = DATA_DIR / "blacklist.json"
    SIN_TELEFONO_FILE = DATA_DIR / "sin_telefono.json"
    ENVIADOS_FILE = DATA_DIR / "enviados.json"
    QUEUE_FILE = DATA_DIR / "queue.json"
    LEADS_FILE = DATA_DIR / "leads.json"

    # ── Anthropic ─────────────────────────────────────────────
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

    # ── Apify ─────────────────────────────────────────────────
    APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")
    APIFY_TOKEN_2 = os.getenv("APIFY_TOKEN_2", "")
    APIFY_ACTOR_ID = os.getenv("APIFY_ACTOR_ID", "compass/crawler-google-places")

    # ── GitHub ────────────────────────────────────────────────
    GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")

    # ── WhatsApp bridge ───────────────────────────────────────
    WA_BRIDGE_PORT = int(os.getenv("WA_BRIDGE_PORT", "3001"))
    WA_EVENTS_PORT = int(os.getenv("WA_EVENTS_PORT", "3002"))
    # URL del bridge — cambiar a https://tu-app.fly.dev para bridge remoto
    WA_BRIDGE_URL  = os.getenv("WA_BRIDGE_URL", f"http://localhost:{os.getenv('WA_BRIDGE_PORT', '3001')}")
    WA_RESPONSES_FILE = ROOT / "data" / "wa_responses.json"
    BRIDGE_SECRET  = os.getenv("BRIDGE_SECRET", "")

    # ── ntfy.sh push notifications ────────────────────────────
    NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")          # ej: binario-crm-agus
    NTFY_URL   = os.getenv("NTFY_URL", "https://ntfy.sh")

    # ── Instagram / Meta (Social Media Agent) ─────────────────
    INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    INSTAGRAM_BUSINESS_ID  = os.getenv("INSTAGRAM_BUSINESS_ID", "")
    META_APP_ID            = os.getenv("META_APP_ID", "")
    META_APP_SECRET        = os.getenv("META_APP_SECRET", "")

    # ── Pexels (stock images, free API) ───────────────────────
    PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

    # ── Business scope ────────────────────────────────────────
    TARGET_CITY = "Rosario"
    TARGET_PROVINCE = "Santa Fe"
    TARGET_COUNTRY = "AR"

    # ── Niches — add new entries here to expand scraping + filtering ──
    NICHES: dict = {
        "amoblamientos": {
            "categories": {
                "tienda de muebles", "fábrica de muebles", "carpintería", "carpintero",
                "tienda de muebles de cocina", "tienda de muebles de pino",
                "interiorista", "tienda de mobiliario de oficina",
                "tienda de mobiliario para dormitorios",
                "tienda de artículos para el hogar", "herrero",
                "establecimiento de venta de madera", "tapicería", "mueblería",
            },
            "keywords": [
                "mueble", "amoblamiento", "carpinter", "placard", "vestidor",
                "cocina", "interior", "mobiliario", "madera", "sillón", "tapizado",
                "ebanista", "herrería", "mueblería", "muebleria", "closet",
                "dormitorio", "living", "estanterías", "ropero",
            ],
            "queries": [
                "amoblamientos Rosario Santa Fe",
                "muebles a medida Rosario",
                "carpintería Rosario",
                "cocinas a medida Rosario",
                "placares vestidores Rosario",
                "mueblería Rosario Santa Fe",
            ],
        },
        "estetica": {
            "categories": {
                "salón de belleza", "peluquería", "peluquero", "estética",
                "spa", "manicura", "pedicura", "centro de estética",
                "centro de belleza", "salón de uñas", "depilación",
                "maquillaje", "lash studio", "nail studio",
                "instituto de belleza", "salón de manicure",
            },
            "keywords": [
                "estética", "estetica", "peluquer", "belleza", "nail", "manicur",
                "pedicur", "depilacion", "spa", "lash", "cejas", "maquillaje",
                "bronceado", "masaje", "keratina", "coloracion", "tintura",
            ],
            "queries": [
                "estéticas Rosario Santa Fe",
                "peluquerías Rosario",
                "salones de belleza Rosario",
                "nail studio Rosario",
                "institutos de belleza Rosario",
            ],
        },
        "gimnasio": {
            "categories": {
                "gimnasio", "centro deportivo", "fitness", "crossfit",
                "pilates", "yoga", "artes marciales", "boxeo",
                "entrenamiento personal", "funcional",
            },
            "keywords": [
                "gimnasio", "gym", "fitness", "crossfit", "pilates", "yoga",
                "boxeo", "funcional", "entrenamiento", "musculacion",
            ],
            "queries": [
                "gimnasios Rosario Santa Fe",
                "crossfit Rosario",
                "pilates Rosario",
                "yoga Rosario",
                "entrenamiento personal Rosario",
            ],
        },
        "cerrajeria": {
            "categories": {
                "cerrajería", "cerrajero", "duplicado de llaves",
                "servicio de cerrajería", "cerrajería del automóvil",
            },
            "keywords": [
                "cerrajer", "llave", "duplicado", "cerradura", "candado", "copia de llave",
            ],
            "queries": [
                "cerrajerías Rosario",
                "cerrajeros Rosario Santa Fe",
                "duplicado de llaves Rosario",
            ],
        },
    }

    # All queries derived from all niches
    APIFY_SEARCH_QUERIES = [q for niche in NICHES.values() for q in niche["queries"]]

    # ── Lead scoring ──────────────────────────────────────────
    SCORE_MIN_TO_CONTACT = 40

    # ── Outreach ──────────────────────────────────────────────
    MAX_MENSAJES_POR_DIA = 50
    INTERVALO_SEGUNDOS = 15
    HORARIO_INICIO = 9
    HORARIO_FIN = 20
    DIAS_SEMANA = [0, 1, 2, 3, 4]  # Mon-Fri

    # ── OSM fallback ──────────────────────────────────────────
    LATITUD = -32.9468
    LONGITUD = -60.6393
    RADIO_BUSQUEDA = 10000  # meters
    CATEGORIAS = [
        "carpintería",
        "muebles a medida",
        "amoblamientos",
    ]

    @classmethod
    def ensure_directories(cls):
        for d in [cls.DATA_DIR, cls.LOGS_DIR, cls.TEMPLATES_DIR, cls.WEBSITES_DIR]:
            d.mkdir(exist_ok=True)

    @classmethod
    def data_file(cls, name: str) -> Path:
        return cls.DATA_DIR / name


config = Config()
