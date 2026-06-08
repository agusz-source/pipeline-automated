#!/usr/bin/env python3
# modules/send_links.py - Envío de links por WhatsApp

import csv
import asyncio
from pathlib import Path
from datetime import datetime
from colorama import Fore
from whatsplay import Client
from whatsplay.auth import LocalProfileAuth
from config import config


class SendLinks:
    def __init__(self):
        self.data_dir = Path.home() / "whatsapp_session"
    
    async def enviar_mensaje(self, client, telefono, url, nombre):
        """Envía el link por WhatsApp"""
        numero = telefono.replace("+", "").replace(" ", "").replace("-", "")
        if not numero.startswith("54"):
            numero = "54" + numero
        
        mensaje = f"¡Hola! Te paso el link del sitio web, miralo y decime que te parece: {url}"
        
        await client.send_message(numero, mensaje)
        await asyncio.sleep(2)
    
    def enviar_links(self, status_file):
        """Lee el CSV y envía links a los que tienen live_url y no recibieron link"""
        asyncio.run(self._enviar_links_async(status_file))
    
    async def _enviar_links_async(self, status_file):
        if not Path(status_file).exists():
            print(f"{Fore.RED}❌ Archivo no encontrado: {status_file}")
            return
        
        # Leer CSV
        with open(status_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = reader.fieldnames
        
        # Filtrar los que necesitan link
        pendientes = [r for r in rows if r.get('live_url') and not r.get('enviado_links')]
        
        if not pendientes:
            print(f"{Fore.YELLOW}⚠️ No hay links pendientes para enviar")
            return
        
        print(f"\n📤 Enviando {len(pendientes)} links...")
        
        # Inicializar WhatsApp
        auth = LocalProfileAuth(self.data_dir)
        client = Client(auth=auth, headless=False)
        
        @client.event("on_auth")
        async def on_auth():
            print("\n📸 ESCANEA EL CÓDIGO QR EN LA VENTANA QUE SE ABRIÓ")
        
        await client.start()
        
        enviados = 0
        for i, row in enumerate(pendientes):
            nombre = row['nombre']
            telefono = row['telefono']
            url = row['live_url']
            
            print(f"\n{'─'*50}")
            print(f"📤 [{i+1}/{len(pendientes)}] {nombre}")
            print(f"   🔗 URL: {url}")
            
            try:
                await self.enviar_mensaje(client, telefono, url, nombre)
                row['enviado_links'] = 'SI'
                row['fecha_envio_links'] = datetime.now().isoformat()
                enviados += 1
                print(f"   ✅ LINK ENVIADO")
                
                # Pequeña pausa entre envíos
                if i < len(pendientes) - 1:
                    await asyncio.sleep(5)
                
            except Exception as e:
                print(f"   ❌ ERROR: {str(e)[:100]}")
        
        # Guardar CSV actualizado
        if enviados > 0:
            with open(status_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        
        print(f"\n{Fore.GREEN}✅ Links enviados: {enviados}")
        await client.close()
