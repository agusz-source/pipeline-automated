#!/usr/bin/env python3
# modules/outreach.py - Envío de mensajes con generación de CSV de estado
import asyncio
import json
import random
import re
import csv
import sys
from pathlib import Path
from datetime import datetime
from whatsplay import Client
from whatsplay.auth import LocalProfileAuth

TIEMPO_ENTRE_MENSAJES = 15

PLANTILLAS = [
    "Hola! Vi tu negocio en internet. Capaz te parece raro el mensaje, pero estuve viendo lo que hacen y terminé haciendo una página web para mostrarles una idea. Si quieren verla, se las paso.",
    "Hola! Me encontré con tu negocio online y me gustó lo que hacen. Por eso preparé una página web de ejemplo para que puedan verla cuando quieran.",
    "Buenas! Vi tu negocio en internet y pensé que podía quedar muy bien con una página web más moderna, así que hice una para mostrarles.",
    "Hola! Estuve viendo tu negocio y me tomé un rato para hacer una página web basada en la información que encontré. Si les interesa, se las muestro.",
    "Buenas! Capaz es un mensaje inesperado, pero encontré tu negocio online y terminé haciendo una página web para que puedan ver cómo se vería.",
    "Hola! Vi tu negocio en internet y me llamó la atención. Se me ocurrió hacer una página web de ejemplo y quería mostrársela.",
    "Buenas! Estuve navegando y llegué a tu negocio. Me gustó lo que hacen y preparé una página web para que la puedan ver sin compromiso.",
    "Hola! Encontré tu negocio online y pensé que una página web podría ayudar a mostrar mejor lo que hacen, así que hice una muestra.",
    "Buenas! Vi tu negocio en internet y decidí hacer una página web para mostrar una idea concreta en lugar de explicarla por mensaje.",
    "Hola! Estuve viendo tu negocio y terminé armando una página web basada en lo que encontré online. Si quieren verla, se las comparto.",
    "Buenas! Vi tu negocio en internet y me pareció interesante. Por eso hice una página web de ejemplo para que puedan darle un vistazo.",
    "Hola! Capaz te parece raro, pero encontré tu negocio online y preparé una página web para mostrarles una idea sin compromiso.",
    "Buenas! Estuve mirando tu negocio y pensé que podía verse muy bien en una página web, así que hice una para que la revisen.",
    "Hola! Vi tu negocio en internet y me tomé un rato para crear una página web de ejemplo. Si les interesa verla, se las paso.",
    "Buenas! Me encontré con tu negocio mientras navegaba y terminé haciendo una página web para mostrarles cómo podría verse online.",
    "Hola! Vi tu negocio y pensé que era más fácil mostrar una página web directamente que intentar explicarla por mensaje.",
    "Buenas! Encontré tu negocio online y preparé una página web de muestra. Si quieren verla, con gusto se las comparto.",
    "Hola! Estuve viendo lo que hacen y terminé armando una página web para mostrar una posible mejora en su presencia online.",
    "Buenas! Vi tu negocio en internet y se me ocurrió hacer una página web basada en lo que encontré. Si quieren verla, está lista.",
    "Hola! Encontré tu negocio online y preparé una página web para mostrarles una idea. Si les interesa, se las puedo enviar."
]

REDES_SOCIALES = [
    'instagram.com', 'facebook.com', 'fb.com', 'twitter.com', 'x.com',
    'linkedin.com', 'youtube.com', 'tiktok.com', 'pinterest.com',
    'tumblr.com', 'snapchat.com', 'reddit.com'
]


def es_red_social(website: str) -> bool:
    if not website:
        return False
    return any(red in website.lower() for red in REDES_SOCIALES)


def es_link_whatsapp(website: str) -> bool:
    if not website:
        return False
    website_lower = website.lower()
    return 'wa.me' in website_lower or 'whatsapp.com' in website_lower


def limpiar_telefono(telefono: str) -> str:
    if not telefono or not telefono.strip():
        return None
    solo_numeros = re.sub(r'[^\d]', '', telefono)
    if not solo_numeros:
        return None
    if solo_numeros.startswith('54'):
        return solo_numeros
    if len(solo_numeros) == 10:
        return '54' + solo_numeros
    if len(solo_numeros) == 11 and solo_numeros.startswith('9'):
        return '54' + solo_numeros
    return solo_numeros


def extraer_link_whatsapp(negocio: dict) -> tuple:
    telefono = negocio.get('phone', '')
    tiene_website = 'website' in negocio and negocio['website'] is not None and str(negocio['website']).strip() != ''
    website = negocio.get('website', '') if tiene_website else ''

    if tiene_website:
        if es_link_whatsapp(website):
            return (website, "whatsapp_link")
        elif es_red_social(website):
            if telefono and telefono.strip():
                telefono_limpio = limpiar_telefono(telefono)
                if telefono_limpio:
                    return (f"https://wa.me/{telefono_limpio}", "telefono_por_red_social")
                else:
                    return (None, "red_social_telefono_invalido")
            else:
                return (None, "red_social_sin_telefono")
        else:
            return (None, "sitio_propio")
    else:
        if telefono and telefono.strip():
            telefono_limpio = limpiar_telefono(telefono)
            if telefono_limpio:
                return (f"https://wa.me/{telefono_limpio}", "telefono")
            else:
                return (None, "telefono_invalido")
        else:
            return (None, "sin_contacto")


class OutreachBot:
    DATA_DIR = Path.home() / "whatsapp_session"

    def cargar_negocios(self, dataset_file):
        try:
            with open(dataset_file, 'r', encoding='utf-8') as f:
                datos = json.load(f)

            negocios = datos if isinstance(datos, list) else [datos]

            print("\n" + "="*60)
            print("📋 ANALIZANDO CADA NEGOCIO INDIVIDUALMENTE...")
            print("="*60)

            seleccionados = []
            for negocio in negocios:
                link, motivo = extraer_link_whatsapp(negocio)
                if link:
                    seleccionados.append({
                        'title': negocio.get('title', ''),
                        'phone': negocio.get('phone', ''),
                        'whatsapp_link': link,
                        'motivo': motivo,
                        'categoryName': negocio.get('categoryName', ''),
                        'address': (negocio.get('address') or negocio.get('formatted_address')
                                    or negocio.get('vicinity') or 'Rosario'),
                        'rating': negocio.get('rating') or negocio.get('score') or 4.5,
                        'reviewCount': (negocio.get('reviewCount') or negocio.get('userRatingsTotal')
                                        or negocio.get('reviews') or 30),
                    })

            return seleccionados

        except FileNotFoundError:
            print(f"❌ No se encuentra el archivo: {dataset_file}")
            return []
        except json.JSONDecodeError as e:
            print(f"❌ Error en el formato JSON: {e}")
            return []

    def guardar_estado_csv(self, status_file, seleccionados, enviados):
        with open(status_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'nombre', 'telefono', 'categoria', 'direccion', 'puntaje', 'resenas',
                'enviado', 'fecha_envio', 'project_path', 'live_url', 'enviado_links', 'fecha_envio_links'
            ])

            for s in seleccionados:
                enviado_info = enviados.get(s['phone'], {})
                writer.writerow([
                    s['title'],
                    s['phone'],
                    s['categoryName'],
                    s['address'],
                    s['rating'],
                    s['reviewCount'],
                    'SI' if enviado_info.get('enviado', False) else 'NO',
                    enviado_info.get('fecha', ''),
                    '',  # project_path
                    '',  # live_url
                    '',  # enviado_links
                    ''   # fecha_envio_links
                ])

        print(f"   💾 Estado guardado en: {status_file}")

    async def _enviar_mensaje(self, client, link, mensaje):
        numero = link.replace("https://wa.me/", "").split("?")[0]
        await client.send_message(numero, mensaje)
        await asyncio.sleep(random.uniform(2, 4))

    async def run(self, dataset_file, status_file) -> int:
        print("="*60)
        print("🤖 BOT WHATSAPP - VERSIÓN DEFINITIVA")
        print("="*60)

        seleccionados = self.cargar_negocios(dataset_file)

        print("\n" + "="*60)
        print("📊 RESUMEN DE ANÁLISIS")
        print("="*60)
        print(f"   📋 Negocios totales en archivo: {len(seleccionados)}")
        print(f"   📝 Plantillas disponibles: {len(PLANTILLAS)}")

        if not seleccionados:
            print("\n✅ No hay negocios para enviar")
            return 0

        print(f"   ⏱️  Tiempo estimado: {len(seleccionados) * TIEMPO_ENTRE_MENSAJES / 60:.1f} minutos")

        auth = LocalProfileAuth(self.DATA_DIR)
        client = Client(auth=auth, headless=False)

        @client.event("on_auth")
        async def on_auth():
            print("\n📸 ESCANEA EL CÓDIGO QR EN LA VENTANA QUE SE ABRIÓ")
            print("   (Solo la primera vez, después se guarda la sesión)")

        await client.start()

        plantillas_disponibles = PLANTILLAS.copy()
        random.shuffle(plantillas_disponibles)

        enviados = {}
        enviados_count = 0

        print("\n🚀 INICIANDO ENVÍOS...\n")

        for i, negocio in enumerate(seleccionados):
            nombre = negocio.get('title', 'Cliente')
            link = negocio.get('whatsapp_link')
            motivo = negocio.get('motivo', 'desconocido')
            categoria = negocio.get('categoryName', '')
            telefono = negocio.get('phone', '')

            if not plantillas_disponibles:
                plantillas_disponibles = PLANTILLAS.copy()
                random.shuffle(plantillas_disponibles)

            plantilla = plantillas_disponibles.pop(0)
            mensaje = plantilla.replace("{categoria}", categoria if categoria else "carpintería")

            print(f"\n{'─'*50}")
            print(f"📤 [{i+1}/{len(seleccionados)}] {nombre}")
            print(f"   🔗 Contacto vía: {motivo}")
            print(f"   📝 Mensaje: {mensaje[:60]}...")

            try:
                await self._enviar_mensaje(client, link, mensaje)

                enviados[telefono] = {
                    'enviado': True,
                    'fecha': datetime.now().isoformat()
                }
                enviados_count += 1
                print(f"   ✅ ENVIADO correctamente")

                self.guardar_estado_csv(status_file, seleccionados, enviados)

                if i < len(seleccionados) - 1:
                    pausa = TIEMPO_ENTRE_MENSAJES + random.uniform(-3, 3)
                    print(f"   ⏰ Esperando {pausa:.1f} segundos antes del próximo...")
                    await asyncio.sleep(max(10, pausa))

            except Exception as e:
                print(f"   ❌ ERROR: {str(e)[:100]}")
                await asyncio.sleep(5)

        print("\n" + "="*60)
        print("📊 RESUMEN FINAL")
        print("="*60)
        print(f"   ✅ Enviados hoy: {enviados_count}")
        print(f"   📋 Total seleccionados: {len(seleccionados)}")
        print(f"   💾 Estado guardado en: {status_file}")
        print("="*60)

        await client.close()
        return enviados_count


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python outreach.py <dataset_file> <status_file>")
        sys.exit(1)
    asyncio.run(OutreachBot().run(sys.argv[1], sys.argv[2]))
