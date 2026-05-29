#!/usr/bin/env python3
# modules/whatsapp.py - Envío de WhatsApp con anti-baneo

import time
import json
from datetime import datetime, time as dt_time
from twilio.rest import Client
from colorama import Fore
from config import config

class WhatsAppSender:
    def __init__(self):
        self.client = None
        if all([config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN]):
            self.client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
        
        self.enviados_hoy = self._cargar_envios_hoy()
        self.ultimo_envio = None
    
    def _cargar_envios_hoy(self):
        try:
            with open(config.ENVIADOS_FILE, 'r') as f:
                data = json.load(f)
                hoy = datetime.now().date().isoformat()
                return data.get(hoy, {}).get("count", 0)
        except:
            return 0
    
    def _guardar_envios_hoy(self):
        with open(config.ENVIADOS_FILE, 'r') as f:
            data = json.load(f)
        
        hoy = datetime.now().date().isoformat()
        data[hoy] = {
            "count": self.enviados_hoy,
            "ultimo_envio": self.ultimo_envio.isoformat() if self.ultimo_envio else None
        }
        
        with open(config.ENVIADOS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _puede_enviar(self):
        if self.enviados_hoy >= config.MAX_MENSAJES_POR_DIA:
            return False, f"Límite diario: {config.MAX_MENSAJES_POR_DIA}"
        
        hoy = datetime.now().weekday()
        if hoy not in config.DIAS_SEMANA:
            return False, "Solo Lunes a Viernes"
        
        ahora = datetime.now()
        if ahora.hour < config.HORARIO_INICIO or ahora.hour >= config.HORARIO_FIN:
            return False, f"Horario {config.HORARIO_INICIO}:00-{config.HORARIO_FIN}:00"
        
        if self.ultimo_envio:
            segundos = (ahora - self.ultimo_envio).total_seconds()
            if segundos < config.INTERVALO_SEGUNDOS:
                espera = config.INTERVALO_SEGUNDOS - segundos
                return False, f"Esperar {espera:.0f} segundos"
        
        return True, ""
    
    def _esperar_intervalo(self):
        if self.ultimo_envio:
            ahora = datetime.now()
            segundos = (ahora - self.ultimo_envio).total_seconds()
            if segundos < config.INTERVALO_SEGUNDOS:
                espera = config.INTERVALO_SEGUNDOS - segundos
                print(f"{Fore.CYAN}⏰ Esperando {espera:.0f} segundos...")
                time.sleep(espera)
    
    def enviar(self, telefono, mensaje, nombre):
        puede, razon = self._puede_enviar()
        if not puede:
            print(f"{Fore.YELLOW}⚠️ {razon}")
            return False
        
        self._esperar_intervalo()
        
        telefono_limpio = ''.join(filter(str.isdigit, telefono))
        if not telefono_limpio.startswith('549'):
            telefono_limpio = '549' + telefono_limpio
        
        try:
            if self.client:
                msg = self.client.messages.create(
                    body=mensaje,
                    from_=f'whatsapp:{config.TWILIO_WHATSAPP_NUMBER}',
                    to=f'whatsapp:+{telefono_limpio}'
                )
                print(f"{Fore.GREEN}✅ Enviado a {nombre}")
                
                with open(config.LOGS_DIR / "leadgen.log", "a") as f:
                    f.write(f"{datetime.now()} | ENVIADO | {telefono} | {nombre}\n")
                
                self.enviados_hoy += 1
                self.ultimo_envio = datetime.now()
                self._guardar_envios_hoy()
                
                # Agregar a blacklist
                with open(config.BLACKLIST_FILE, 'r') as f:
                    blacklist = json.load(f)
                if "telefonos" not in blacklist:
                    blacklist["telefonos"] = []
                if telefono not in blacklist["telefonos"]:
                    blacklist["telefonos"].append(telefono)
                with open(config.BLACKLIST_FILE, 'w') as f:
                    json.dump(blacklist, f, indent=2)
                
                return True
            else:
                print(f"{Fore.YELLOW}🔸 SIMULACIÓN: {nombre}")
                return True
        except Exception as e:
            print(f"{Fore.RED}❌ Error: {e}")
            return False
    
    def enviar_cola(self):
        with open(config.QUEUE_FILE, 'r') as f:
            data = json.load(f)
            queue = data.get("queue", [])
        
        if not queue:
            print(f"{Fore.YELLOW}No hay mensajes en cola")
            return
        
        print(f"{Fore.YELLOW}📋 {len(queue)} mensajes pendientes")
        resp = input(f"{Fore.CYAN}¿Enviar todos? (si/no): ")
        
        if resp.lower() != 'si':
            print(f"{Fore.YELLOW}Envío cancelado")
            return
        
        for i, item in enumerate(queue):
            lead = item["lead"]
            mensaje = item["mensaje"]
            telefono = lead.get("telefono", "")
            
            if not telefono:
                print(f"{Fore.YELLOW}⚠️ {lead['nombre']} no tiene teléfono")
                continue
            
            self.enviar(telefono, mensaje, lead["nombre"])
            
            if i < len(queue) - 1:
                print(f"{Fore.CYAN}⏰ Esperando {config.INTERVALO_SEGUNDOS} segundos...")
                time.sleep(config.INTERVALO_SEGUNDOS)
        
        with open(config.QUEUE_FILE, 'w') as f:
            json.dump({"queue": []}, f)
        
        print(f"{Fore.GREEN}✅ Envío completado")
