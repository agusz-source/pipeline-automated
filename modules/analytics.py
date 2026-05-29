#!/usr/bin/env python3
# modules/analytics.py - Estadísticas y tracking

import json
import csv
from datetime import datetime
from colorama import Fore
from config import config

class Analytics:
    def mostrar_estado(self):
        print(f"{Fore.CYAN}\n{'='*50}")
        print(f"📊 ESTADO DEL SISTEMA")
        print(f"{'='*50}\n")
        
        with open(config.LEADS_FILE, 'r') as f:
            data = json.load(f)
            leads = data.get("leads", [])
            print(f"Leads descubiertos: {len(leads)}")
        
        with open(config.BLACKLIST_FILE, 'r') as f:
            data = json.load(f)
            blacklist = data.get("telefonos", [])
            print(f"Blacklist: {len(blacklist)} números")
        
        with open(config.SIN_TELEFONO_FILE, 'r') as f:
            data = json.load(f)
            sin_telefono = data.get("negocios", [])
            print(f"Sin teléfono: {len(sin_telefono)} negocios")
        
        with open(config.QUEUE_FILE, 'r') as f:
            data = json.load(f)
            queue = data.get("queue", [])
            print(f"Mensajes en cola: {len(queue)}")
        
        with open(config.INTERESADOS_FILE, 'r') as f:
            data = json.load(f)
            interesados = data.get("interesados", [])
            print(f"Interesados: {len(interesados)}")
        
        with open(config.ENVIADOS_FILE, 'r') as f:
            data = json.load(f)
            hoy = datetime.now().date().isoformat()
            enviados = data.get(hoy, {}).get("count", 0)
            print(f"Enviados hoy: {enviados}/{config.MAX_MENSAJES_POR_DIA}")
