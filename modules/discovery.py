#!/usr/bin/env python3
# modules/discovery.py - Lee JSON de Apify directamente

import json
import re
from datetime import datetime
from colorama import Fore
from config import config

class LeadDiscovery:
    def scan_all(self) -> list:
        # Buscar el JSON de Apify en data/
        import glob
        archivos = glob.glob("data/dataset_instagram*.json")
        
        if not archivos:
            print(f"{Fore.RED}❌ No encontré ningún JSON de Apify en data/")
            print(f"{Fore.YELLOW}💡 Copiá tu JSON a data/dataset_instagram_xxxx.json")
            return []
        
        json_path = archivos[0]
        print(f"{Fore.CYAN}📂 Leyendo: {json_path}")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        leads = []
        for item in data:
            nombre = item.get("title", "Sin nombre")
            nombre = nombre.split(" on Instagram")[0].split("•")[0].strip()
            
            telefono_raw = item.get("phone_number", "")
            telefono = re.sub(r'[^\d]', '', telefono_raw)
            if len(telefono) == 11 and telefono.startswith('54'):
                telefono = '549' + telefono[2:]
            
            descripcion = item.get("description", "")
            keyword = item.get("keyword", "negocio")
            
            lead = {
                "nombre": nombre[:50],
                "categoria": keyword,
                "direccion": "Rosario",
                "descripcion": descripcion[:500],
                "puntaje": 4.5,
                "resenas": 30,
                "telefono": telefono,
                "website": item.get("url", ""),
                "source": "Instagram"
            }
            
            if telefono and len(telefono) >= 10:
                leads.append(lead)
                print(f"{Fore.GREEN}✓ {nombre} - {telefono}")
        
        # Guardar en el formato que espera el sistema
        with open(config.LEADS_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "leads": leads,
                "total": len(leads),
                "fecha": datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        
        print(f"{Fore.GREEN}✅ Total leads: {len(leads)}")
        return leads
