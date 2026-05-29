# modules/osm_discovery.py - OpenStreetMap Lead Discovery (WHATSAPP ONLY PRO)

import requests
import json
import time
from datetime import datetime
from colorama import Fore
from config import config


class OSMDiscovery:
    def __init__(self):
        self.endpoints = [
           # "https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"
        ]

        self.lat = config.LATITUD
        self.lon = config.LONGITUD

        self.max_total = 20

    def search_places(self, categoria: str, max_por_cat: int) -> list:

        osm_map = {
            "cerrajeria cerrajero": '["shop"="locksmith"]',
            "cafe cafeteria": '["amenity"="cafe"]',
            "restaurante": '["amenity"="restaurant"]',
            "salon belleza estetica": '["shop"="beauty"]'
        }

        tag = osm_map.get(categoria)
        if not tag:
            return []

        query = f"""
        [out:json][timeout:120];
        (
          node{tag}(around:{config.RADIO_BUSQUEDA},{self.lat},{self.lon});
          way{tag}(around:{config.RADIO_BUSQUEDA},{self.lat},{self.lon});
        );
        out center;
        """

        print(f"{Fore.CYAN}🔍 Buscando en OSM: {categoria}")

        for endpoint in self.endpoints:
            try:
                response = requests.post(
                    endpoint,
                    data=query,
                    timeout=(5, 120),
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )

                if response.status_code != 200:
                    continue

                try:
                    data = response.json()
                except:
                    continue

                resultados = []
                seen = set()

                for element in data.get("elements", []):
                    tags = element.get("tags", {})

                    nombre = tags.get("name")
                    if not nombre or nombre in seen:
                        continue
                    seen.add(nombre)

                    # 📞 SOLO WHATSAPP (móvil real)
                    raw_phone = tags.get("phone") or tags.get("contact:phone")
                    if not raw_phone:
                        continue

                    phone = self._extract_mobile_whatsapp(raw_phone)

                    # ❌ si no es móvil válido → descartar
                    if not phone:
                        continue

                    # dirección
                    direccion = tags.get("addr:street", "")
                    if tags.get("addr:housenumber"):
                        direccion += " " + tags.get("addr:housenumber")
                    if not direccion:
                        direccion = "Rosario"

                    negocio = {
                        "nombre": nombre,
                        "categoria": categoria,
                        "direccion": direccion,
                        "telefono": phone,
                        "whatsapp": f"https://wa.me/{phone}",
                        "website": tags.get("website", ""),
                        "source": "OSM"
                    }

                    resultados.append(negocio)
                    print(f"{Fore.GREEN}  ✓ {nombre} (WhatsApp OK)")

                    if len(resultados) >= max_por_cat:
                        break

                if resultados:
                    return resultados

            except Exception as e:
                print(f"{Fore.YELLOW}  → Error {endpoint}: {e}")
                continue

            finally:
                time.sleep(1.5)

        return []

    def _extract_mobile_whatsapp(self, raw: str) -> str:
        """
        Detecta si es número móvil (WhatsApp) válido.
        ❌ descarta fijos
        ✔ devuelve solo móviles en formato wa.me
        """

        if not raw:
            return ""

        digits = ''.join(filter(str.isdigit, raw))

        # Argentina normalización básica
        if digits.startswith("0"):
            digits = digits[1:]

        if digits.startswith("15"):
            digits = digits[2:]

        # caso móvil argentino típico
        # 10 dígitos + prefijo móvil
        if len(digits) == 10:
            digits = "54" + digits

        # validar mínimo razonable internacional
        if len(digits) < 11 or len(digits) > 15:
            return ""

        # ❌ filtro de teléfonos fijos argentinos comunes
        # (muy aproximado pero útil)
        local_prefixes_fijos = ["341", "342", "343", "351", "362", "370", "381", "387"]
        if len(digits) == 12:  # 54 + 10 digits
            local_area = digits[2:5]
            if local_area in local_prefixes_fijos:
                return ""

        return digits

    def scan_all(self) -> list:
        """20 leads TOTAL SOLO con WhatsApp válido"""

        todos = []
        seen = set()

        categorias = config.CATEGORIAS
        n = len(categorias)

        base = self.max_total // n
        resto = self.max_total % n

        for i, cat in enumerate(categorias):

            if len(todos) >= self.max_total:
                break

            max_por_cat = base + (1 if i < resto else 0)

            resultados = self.search_places(cat, max_por_cat)

            for r in resultados:
                if r["nombre"] in seen:
                    continue

                seen.add(r["nombre"])
                todos.append(r)

                if len(todos) >= self.max_total:
                    break

            time.sleep(1)

        # guardar
        with open(config.LEADS_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "leads": todos,
                "total": len(todos),
                "fecha": datetime.now().isoformat(),
                "source": "OSM_WHATSAPP_ONLY"
            }, f, indent=2, ensure_ascii=False)

        print(f"{Fore.GREEN}✅ WhatsApp leads finales: {len(todos)}")

        return todos
