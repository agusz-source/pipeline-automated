import os
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class Config:
    # API Keys (solo las que usás)
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID', '')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', '')
    TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER', '')
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
    GITHUB_USERNAME = os.getenv('GITHUB_USERNAME', '')
    
    # Búsqueda
    CIUDAD = "Rosario"
    LATITUD = -32.9468
    LONGITUD = -60.6393
    RADIO_BUSQUEDA = 30000
    MIN_PUNTAJE = 4.3
    MIN_RESENAS = 30
    
    CATEGORIAS = [
        "cerrajeria cerrajero",
        "cafe cafeteria",
        "gimnasio fitness", 
        "restaurante",
        "salon belleza estetica"
    ]
    
    # WhatsApp Anti-Baneo
    MAX_MENSAJES_POR_DIA = 40
    INTERVALO_SEGUNDOS = 240  # 4 minutos
    HORARIO_INICIO = 10
    HORARIO_FIN = 20
    DIAS_SEMANA = [0, 1, 2, 3, 4]
    
    # Directorios
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR / "data"
    LOGS_DIR = BASE_DIR / "logs"
    TEMPLATES_DIR = BASE_DIR / "templates"
    WEBSITES_DIR = BASE_DIR / "websites"
    
    # Archivos
    LEADS_FILE = DATA_DIR / "leads.json"
    BLACKLIST_FILE = DATA_DIR / "blacklist.json"
    SIN_TELEFONO_FILE = DATA_DIR / "sin_telefono.json"
    QUEUE_FILE = DATA_DIR / "queue.json"
    ENVIADOS_FILE = DATA_DIR / "enviados.json"
    INTERESADOS_FILE = DATA_DIR / "interesados.json"
    
    # OSM (gratis)
    USAR_OSM = True
    OSM_TIMEOUT = 240   
    OSM_MAX_RADIUS = 30000
    
    OSM_CATEGORIES = {
        "cerrajeria cerrajero": {"shop": "locksmith"},
        "cafe cafeteria": {"amenity": "cafe"},
        "restaurante": {"amenity": "restaurant"},
        "salon belleza estetica": {"shop": "beauty"}
    }
    
    @classmethod
    def ensure_directories(cls):
        for dir_path in [cls.DATA_DIR, cls.LOGS_DIR, cls.TEMPLATES_DIR, cls.WEBSITES_DIR]:
            dir_path.mkdir(exist_ok=True)
        
        for file_path in [cls.LEADS_FILE, cls.BLACKLIST_FILE, cls.SIN_TELEFONO_FILE, 
                          cls.QUEUE_FILE, cls.ENVIADOS_FILE, cls.INTERESADOS_FILE]:
            if not file_path.exists():
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump({}, f, indent=2)

config = Config()	
