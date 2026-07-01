#!/usr/bin/env python3
"""
WhatsApp outreach sender.

Reads the filtered+deduped+scored lead list, sends messages, and
writes entries to estado.csv using the full schema.
"""

import asyncio
import csv
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path

from whatsplay import Client
from whatsplay.auth import LocalProfileAuth

from config import config

TIEMPO_ENTRE_MENSAJES = 15

PLANTILLAS = [
    "Hola! Vi tu negocio en internet. Capaz te parece raro el mensaje, pero estuve viendo lo que hacen y terminé haciendo una página web para mostrarles una idea. Si quieren verla, se las paso sin costo.",
    "Hola! Me encontré con tu negocio online y me gustó lo que hacen. Va a sonar raro pero por eso preparé una página web de ejemplo para que puedan verla cuando quieran y obvio sin cargo.",
    "Hola Buenas! Como va? Soy desarrollador web, vi tu negocio en internet y pensé que podía quedar muy bien con una página web, así que hice una para mostrarles. Si quieren se las muestro sin cargo.",
    "Hola! Estuve viendo tu negocio y me tomé un rato para hacer una página web basada en la información que encontré. Si les interesa, se las muestro.",
    "Buenas! Capaz es un mensaje inesperado, pero encontré tu negocio online y terminé haciendo una página web para que puedan ver cómo se vería. Les gustaría verla?",
    "Hola! Vi tu negocio en internet y me llamó la atención, por eso se me ocurrió hacer una página web de ejemplo y quería mostrársela.",
    "Buenas! Estaba en internet y me crucé con tu negocio. Me gustó lo que hacen y preparé una página web para que la puedan ver sin compromiso.",
    "Hola! Encontré tu negocio online y me gustó mucho, por eso pensé que una página web podría ayudar a mostrar mejor lo que hacen. Hice una muestra gratis. Si quieren la pueden ver sin compromiso.",
    "Buenas! Vi tu negocio en internet y decidí hacer una página web porque me gustó mucho, y siento que puede mostrar mejor su trabajo.",
    "Hola! Estuve viendo tu negocio y terminé armando una página web basada en lo que encontré online. Si quieren verla, se las comparto sin compromiso.",
    "Buenas! Vi tu negocio en internet y me pareció interesante. Por eso hice una página web de ejemplo para que puedan darle un vistazo.",
    "Hola! Capaz te parece raro, pero encontré tu negocio online y preparé una página web para mostrarles una idea sin compromiso. Si quieren se las mando.",
    "Hola Buenas! Estuve mirando tu negocio y pensé que podía verse muy bien en una página web, así que hice una para que la miren tranki.",
    "Hola! Todo bien? Vi su negocio en internet y veo potencial. Por eso me tomé un rato para crear una página web de ejemplo gratis. Si les interesa verla, se las paso obvio sin cargo.",
    "Buenas! Me encontré con tu negocio mientras estaba en internet y se que va a sonar medio raro pero les terminé haciendo una página web para mostrarles cómo podría verse.",
    "Hola! Como va? Vi su negocio y soy desarrollador web, se que va a sonar raro pero por eso les hice una pagina web de ejemplo gratis, como una muestra. Si quieren, la pueden ver sin cargo.",
    "Buenas! Encontré tu negocio online y preparé una página web de muestra. Si quieren verla, con gusto se las comparto y sin cargo obvio.",
    "Hola! Todo bien? Estuve viendo lo que hacen y capaz es medio inesperado pero les terminé armando una página web para mostrar una posible mejora en su presencia online. La pueden ver sin cargo.",
    "Hola Buenas! Vi su negocio en internet y va a sonar raro pero se me ocurrió hacer una página web basada en lo que encontré. Si quieren verla, está lista.",
    "Hola! Encontré tu negocio online y preparé una página web para mostrarles como se vería una. Si les interesa, se las puedo mandar sin cargo obvio.",
]

_SOCIAL_DOMAINS = frozenset([
    "instagram.com", "facebook.com", "fb.com", "twitter.com", "x.com",
    "linkedin.com", "youtube.com", "tiktok.com", "pinterest.com",
    "wa.me", "whatsapp.com", "linktr.ee",
])


def _es_red_social(website: str) -> bool:
    if not website:
        return False
    return any(d in website.lower() for d in _SOCIAL_DOMAINS)


def _es_link_whatsapp(website: str) -> bool:
    if not website:
        return False
    ws = website.lower()
    return "wa.me" in ws or "whatsapp.com" in ws


def limpiar_telefono(telefono: str) -> str | None:
    from modules.phone_validator import normalizar_telefono
    return normalizar_telefono(telefono)


def extraer_link_whatsapp(negocio: dict) -> tuple[str | None, str]:
    telefono = negocio.get("phone", "") or negocio.get("telefono", "")
    website = negocio.get("website", "") or ""
    if "google.com/maps" in website:
        website = ""

    tiene_website = bool(website.strip())

    if tiene_website:
        if _es_link_whatsapp(website):
            return website, "whatsapp_link"
        elif _es_red_social(website):
            clean = limpiar_telefono(telefono)
            if clean:
                return f"https://wa.me/{clean}", "telefono_por_red_social"
            return None, "red_social_sin_telefono"
        else:
            return None, "sitio_propio"
    else:
        clean = limpiar_telefono(telefono)
        if clean:
            return f"https://wa.me/{clean}", "telefono"
        return None, "sin_contacto"


# ── CSV helpers ───────────────────────────────────────────────────────────────

CSV_FIELDNAMES = [
    "lead_id", "nombre", "telefono", "categoria", "direccion", "puntaje", "resenas",
    "score", "filter_reason",
    "enviado", "fecha_envio",
    "estado_respuesta", "fecha_respuesta",
    "project_path", "live_url", "enviado_links", "fecha_envio_links",
    "fecha_entrega", "fecha_renovacion_web", "fecha_renovacion_hosting",
    "fecha_renovacion_mantenimiento", "notas",
]


def _cargar_csv_existente(status_file: str) -> dict[str, dict]:
    existentes: dict[str, dict] = {}
    sf = Path(status_file)
    if not sf.exists():
        return existentes
    with open(sf, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tel = row.get("telefono", "").strip()
            if tel:
                existentes[tel] = row
    return existentes


def _guardar_estado_csv(
    status_file: str,
    seleccionados: list[dict],
    enviados: dict[str, dict],
    csv_existente: dict[str, dict],
):
    phones_actuales = {s.get("phone", s.get("telefono", "")).strip() for s in seleccionados}

    with open(status_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()

        # Preserve old rows not in this batch
        for tel, row in csv_existente.items():
            if tel not in phones_actuales:
                writer.writerow({k: row.get(k, "") for k in CSV_FIELDNAMES})

        # Write current batch
        for s in seleccionados:
            phone = s.get("phone") or s.get("telefono", "")
            enviado_info = enviados.get(phone, {})
            viejo = csv_existente.get(phone.strip(), {})

            if viejo.get("enviado", "").strip().upper() == "SI":
                estado_final = "SI"
                fecha_final = viejo.get("fecha_envio", "")
            else:
                estado_final = "SI" if enviado_info.get("enviado") else "NO"
                fecha_final = enviado_info.get("fecha", "")

            writer.writerow(
                {
                    "lead_id": s.get("lead_id") or viejo.get("lead_id", ""),
                    "nombre": s.get("title") or s.get("nombre", ""),
                    "telefono": phone,
                    "categoria": s.get("categoryName") or s.get("categoria", ""),
                    "direccion": s.get("address") or s.get("direccion", "Rosario"),
                    "puntaje": s.get("rating") or s.get("puntaje", ""),
                    "resenas": s.get("reviewCount") or s.get("resenas", ""),
                    "score": s.get("score", ""),
                    "filter_reason": s.get("filter_reason", ""),
                    "enviado": estado_final,
                    "fecha_envio": fecha_final,
                    "estado_respuesta": viejo.get("estado_respuesta", ""),
                    "fecha_respuesta": viejo.get("fecha_respuesta", ""),
                    "project_path": viejo.get("project_path", ""),
                    "live_url": viejo.get("live_url", ""),
                    "enviado_links": viejo.get("enviado_links", ""),
                    "fecha_envio_links": viejo.get("fecha_envio_links", ""),
                    "fecha_entrega": viejo.get("fecha_entrega", ""),
                    "fecha_renovacion_web": viejo.get("fecha_renovacion_web", ""),
                    "fecha_renovacion_hosting": viejo.get("fecha_renovacion_hosting", ""),
                    "fecha_renovacion_mantenimiento": viejo.get("fecha_renovacion_mantenimiento", ""),
                    "notas": viejo.get("notas", ""),
                }
            )

    print(f"   💾 Estado guardado en: {status_file}")


# ── Bot ───────────────────────────────────────────────────────────────────────

class OutreachBot:
    DATA_DIR = Path.home() / "whatsapp_session"

    def cargar_negocios(self, dataset_file: str) -> list[dict]:
        try:
            with open(dataset_file, "r", encoding="utf-8") as f:
                datos = json.load(f)
            negocios = datos if isinstance(datos, list) else [datos]

            print("\n" + "=" * 60)
            print("📋 ANALIZANDO NEGOCIOS...")
            print("=" * 60)

            seleccionados = []
            for n in negocios:
                link, motivo = extraer_link_whatsapp(n)
                if link:
                    seleccionados.append({**n, "whatsapp_link": link, "motivo": motivo})
            return seleccionados
        except FileNotFoundError:
            print(f"❌ No se encuentra: {dataset_file}")
            return []
        except json.JSONDecodeError as e:
            print(f"❌ Error JSON: {e}")
            return []

    async def _enviar_mensaje(self, client, link: str, mensaje: str):
        numero = link.replace("https://wa.me/", "").split("?")[0]
        await client.send_message(numero, mensaje, open_via_url=True)
        await asyncio.sleep(random.uniform(2, 4))

    async def run(
        self,
        dataset_file: str,
        status_file: str,
        scored_leads: list[dict] | None = None,
    ) -> int:
        print("=" * 60)
        print("🤖 OUTREACH BOT")
        print("=" * 60)

        todos = self.cargar_negocios(dataset_file)
        csv_existente = _cargar_csv_existente(status_file)
        ya_enviados = {
            tel for tel, row in csv_existente.items()
            if row.get("enviado", "").strip().upper() == "SI"
        }

        seleccionados = [n for n in todos if n.get("phone", "").strip() not in ya_enviados]

        print(f"\n{'='*60}")
        print("📊 RESUMEN")
        print(f"{'='*60}")
        print(f"   Total en dataset:    {len(todos)}")
        print(f"   Ya enviados:         {len(todos) - len(seleccionados)}")
        print(f"   Nuevos:              {len(seleccionados)}")

        if not seleccionados:
            print("\n✅ Sin negocios nuevos para enviar")
            return 0

        print(f"   Tiempo estimado:     {len(seleccionados) * TIEMPO_ENTRE_MENSAJES / 60:.1f} min")

        plantillas_disponibles = PLANTILLAS.copy()
        random.shuffle(plantillas_disponibles)
        enviados: dict[str, dict] = {}
        enviados_count = 0

        auth = LocalProfileAuth(self.DATA_DIR)
        client = Client(auth=auth, headless=False)

        @client.event("on_auth")
        async def on_auth():
            print("\n📸 ESCANEA EL QR EN LA VENTANA QUE SE ABRIÓ")
            print("   (Solo la primera vez — la sesión se guarda)")

        @client.event("on_logged_in")
        async def on_logged_in():
            nonlocal enviados_count, plantillas_disponibles

            print("\n🚀 INICIANDO ENVÍOS...\n")

            for i, negocio in enumerate(seleccionados):
                nombre = negocio.get("title") or negocio.get("nombre", "Cliente")
                link = negocio.get("whatsapp_link")
                motivo = negocio.get("motivo", "")
                categoria = negocio.get("categoryName") or negocio.get("categoria", "")
                telefono = negocio.get("phone") or negocio.get("telefono", "")

                fila_csv = csv_existente.get(telefono.strip())
                if fila_csv and fila_csv.get("enviado", "").strip().upper() == "SI":
                    print(f"⏭️  [{i+1}/{len(seleccionados)}] SALTANDO {nombre} — ya enviado")
                    continue

                if not plantillas_disponibles:
                    plantillas_disponibles = PLANTILLAS.copy()
                    random.shuffle(plantillas_disponibles)

                plantilla = plantillas_disponibles.pop(0)
                mensaje = plantilla.replace("{categoria}", categoria or "carpintería")

                print(f"\n{'─'*50}")
                print(f"📤 [{i+1}/{len(seleccionados)}] {nombre}")
                print(f"   Vía: {motivo}")
                print(f"   Msg: {mensaje[:60]}...")

                try:
                    await self._enviar_mensaje(client, link, mensaje)
                    enviados[telefono] = {"enviado": True, "fecha": datetime.now().isoformat()}
                    enviados_count += 1
                    print("   ✅ ENVIADO")

                    _guardar_estado_csv(status_file, seleccionados, enviados, csv_existente)

                    if i < len(seleccionados) - 1:
                        pausa = TIEMPO_ENTRE_MENSAJES + random.uniform(-3, 3)
                        print(f"   ⏰ Pausa {pausa:.1f}s...")
                        await asyncio.sleep(max(10, pausa))

                except Exception as e:
                    print(f"   ❌ ERROR: {str(e)[:100]}")
                    await asyncio.sleep(5)

            print(f"\n{'='*60}")
            print(f"✅ Enviados: {enviados_count} / {len(seleccionados)}")
            print(f"{'='*60}")
            await client.stop()

        await client.start()
        return enviados_count


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python outreach.py <dataset_file> <status_file>")
        sys.exit(1)
    asyncio.run(OutreachBot().run(sys.argv[1], sys.argv[2]))
