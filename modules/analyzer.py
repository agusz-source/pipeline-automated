#!/usr/bin/env python3
# modules/analyzer.py - Análisis de presencia digital

import json
from colorama import Fore
from config import config

class DigitalAnalyzer:
    
    PLATAFORMAS_DEBILES = ["instagram", "facebook", "tiktok", "linktr", "whatsapp", "fb"]
    
    def analizar(self):
        with open(config.LEADS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            leads = data.get("leads", [])
        
        validos = []
        for lead in leads:
            telefono = lead.get("telefono", "")
            website = lead.get("website", "")
            
            if not telefono:
                print(f"{Fore.YELLOW}⚠️ Sin teléfono: {lead['nombre']}")
                self._guardar_sin_telefono(lead)
                continue
            
            if not website:
                lead["status"] = "HIGH_PRIORITY"
                validos.append(lead)
                print(f"{Fore.GREEN}✓ {lead['nombre']} - SIN WEB")
            elif any(p in website.lower() for p in self.PLATAFORMAS_DEBILES):
                lead["status"] = "VALID_LEAD"
                validos.append(lead)
                print(f"{Fore.GREEN}✓ {lead['nombre']} - SOLO REDES")
            else:
                print(f"{Fore.RED}✗ {lead['nombre']} - TIENE WEB REAL")
                self._guardar_en_blacklist(lead)
        
        with open(config.LEADS_FILE, 'w', encoding='utf-8') as f:
            json.dump({"leads": validos, "total": len(validos)}, f, indent=2, ensure_ascii=False)
        
        print(f"{Fore.GREEN}✅ Leads válidos: {len(validos)}")
        return validos
    
    def _guardar_sin_telefono(self, lead):
        with open(config.SIN_TELEFONO_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if "negocios" not in data:
            data["negocios"] = []
        
        nombres = [n.get("nombre") for n in data["negocios"]]
        if lead["nombre"] not in nombres:
            data["negocios"].append({
                "nombre": lead["nombre"],
                "categoria": lead["categoria"],
                "direccion": lead["direccion"],
                "fecha": datetime.now().isoformat()
            })
        
        with open(config.SIN_TELEFONO_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _guardar_en_blacklist(self, lead):
        with open(config.BLACKLIST_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if "telefonos" not in data:
            data["telefonos"] = []
        
        if lead["telefono"] and lead["telefono"] not in data["telefonos"]:
            data["telefonos"].append(lead["telefono"])
        
        with open(config.BLACKLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

from datetime import datetime
