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
    APIFY_ACTOR_ID = os.getenv("APIFY_ACTOR_ID", "compass/crawler-google-places")

    # ── GitHub ────────────────────────────────────────────────
    GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")

    # ── WhatsApp bridge ───────────────────────────────────────
    WA_BRIDGE_PORT = int(os.getenv("WA_BRIDGE_PORT", "3001"))
    WA_EVENTS_PORT = int(os.getenv("WA_EVENTS_PORT", "3002"))

    # ── Business scope ────────────────────────────────────────
    TARGET_CITY = "Rosario"
    TARGET_PROVINCE = "Santa Fe"
    TARGET_COUNTRY = "AR"

    FURNITURE_CATEGORIES = {
        "tienda de muebles",
        "fábrica de muebles",
        "carpintería",
        "carpintero",
        "tienda de muebles de cocina",
        "tienda de muebles de pino",
        "interiorista",
        "tienda de mobiliario de oficina",
        "tienda de mobiliario para dormitorios",
        "tienda de artículos para el hogar",
        "herrero",
        "establecimiento de venta de madera",
        "tapicería",
        "mueblería",
    }

    FURNITURE_KEYWORDS = [
        "mueble", "amoblamiento", "carpinter", "placard", "vestidor",
        "cocina", "interior", "mobiliario", "madera", "sillón", "tapizado",
        "ebanista", "herrería", "mueblería", "muebleria", "closet",
        "dormitorio", "living", "estanterías", "ropero",
    ]

    # Scraping search queries (one per Apify run)
    APIFY_SEARCH_QUERIES = [
        "amoblamientos Rosario Santa Fe",
        "muebles a medida Rosario",
        "carpintería Rosario",
        "cocinas a medida Rosario",
        "placares vestidores Rosario",
        "mueblería Rosario Santa Fe",
    ]

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
