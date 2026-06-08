import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Solo lo necesario para directorios
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR / "data"
    LOGS_DIR = BASE_DIR / "logs"
    TEMPLATES_DIR = BASE_DIR / "templates"
    WEBSITES_DIR = BASE_DIR / "websites"
    
    # Opcional: GitHub username para deploy
    GITHUB_USERNAME = os.getenv('GITHUB_USERNAME', '')
    
    @classmethod
    def ensure_directories(cls):
        for dir_path in [cls.DATA_DIR, cls.LOGS_DIR, cls.TEMPLATES_DIR, cls.WEBSITES_DIR]:
            dir_path.mkdir(exist_ok=True)

config = Config()