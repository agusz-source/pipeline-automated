#!/usr/bin/env python3
# modules/send_links.py - Envío de links por WhatsApp (solo a interesados)

import csv
import json
import random
import asyncio
from pathlib import Path
from datetime import datetime
from colorama import Fore
from whatsplay import Client
from whatsplay.auth import LocalProfileAuth
from config import config

INTERESADOS_FILE = config.DATA_DIR / "interesados.json"


class SendLinks:
    def __init__(self):
        self.data_dir = Path.home() / "whatsapp_session"

    def enviar_links(self, status_file):
        """Lee interesados.json y CSV, envía links por WhatsApp"""
        asyncio.run(self._enviar_links_async(status_file))

    async def _enviar_links_async(self, status_file):
        if not INTERESADOS_FILE.exists():
            print(f"{Fore.RED}❌ No se encontró {INTERESADOS_FILE}")
            print(f"   Primero ejecutá --generate-webs para registrar los interesados")
            return

        if not Path(status_file).exists():
            print(f"{Fore.RED}❌ Archivo no encontrado: {status_file}")
            return

        with open(INTERESADOS_FILE, 'r', encoding='utf-8') as f:
            interesados = json.load(f)

        telefonos_interesados = {i['telefono'] for i in interesados}

        with open(status_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = reader.fieldnames

        pendientes = [
            r for r in rows
            if r['telefono'] in telefonos_interesados
            and r.get('live_url')
            and r.get('enviado_links', '').upper() != 'SI'
        ]

        if not pendientes:
            print(f"{Fore.YELLOW}⚠️  No hay links pendientes para enviar")
            return

        print(f"\n{'='*60}")
        print(f"📤 ENVIANDO LINKS — {len(pendientes)} pendientes")
        print(f"{'='*60}")

        auth = LocalProfileAuth(self.data_dir)
        client = Client(auth=auth, headless=False)

        @client.event("on_auth")
        async def on_auth():
            print("\n📸 ESCANEA EL CÓDIGO QR EN LA VENTANA QUE SE ABRIÓ")
            print("   (Solo la primera vez, después se guarda la sesión)")

        @client.event("on_logged_in")
        async def on_logged_in():
            enviados = 0

            for i, row in enumerate(pendientes):
                nombre = row['nombre']
                telefono = row['telefono']
                url = row['live_url']

                numero = telefono.replace("+", "").replace(" ", "").replace("-", "")
                if not numero.startswith("54"):
                    numero = "54" + numero

                mensaje = f"¡Hola! Te paso el link del sitio web, miralo y decime que te parece: {url}"

                print(f"\n{'─'*50}")
                print(f"📤 [{i+1}/{len(pendientes)}] {nombre}")
                print(f"   🔗 URL: {url}")
                print(f"   📝 {mensaje[:70]}...")

                try:
                    await client.send_message(numero, mensaje, open_via_url=True)
                    await asyncio.sleep(2)

                    row['enviado_links'] = 'SI'
                    row['fecha_envio_links'] = datetime.now().isoformat()
                    enviados += 1
                    print(f"   ✅ LINK ENVIADO")

                    with open(status_file, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(rows)

                    if i < len(pendientes) - 1:
                        pausa = 15 + random.uniform(-3, 3)
                        print(f"   ⏰ Esperando {pausa:.1f}s...")
                        await asyncio.sleep(max(10, pausa))

                except Exception as e:
                    print(f"   ❌ ERROR: {str(e)[:100]}")
                    await asyncio.sleep(5)

            print(f"\n{'='*60}")
            print(f"{Fore.GREEN}✅ Links enviados: {enviados}")
            print(f"{'='*60}")
            await client.stop()

        await client.start()
