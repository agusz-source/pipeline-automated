#!/usr/bin/env python3
"""
Main orchestrator — LeadGen Amoblamientos Rosario

Pipeline stages:
  1. --scrape           Run Apify to fetch raw Google Maps data → dataset.json
  2. --discover         Read dataset.json and show summary (no changes)
  3. --send             Filter, dedup, score, then send WhatsApp outreach
  4. --generate-webs    Generate websites for interested leads
  5. --deploy           Deploy websites to Vercel
  6. --send-links       Send live URLs to interested leads via WhatsApp
  7. --full             Run steps 1–6 end-to-end
  8. --status           Show pipeline status from estado.csv
  9. --migrate          Migrate existing estado.csv to add new columns
"""

import asyncio
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from colorama import Fore, Style, init

from config import config
from modules.claude_builder import ClaudeBuilder
from modules.deduplication import filter_new_leads, load_existing_ids
from modules.deploy import Deployer
from modules.niche_filter import filter_leads, print_filter_report
from modules.outreach import OutreachBot
from modules.scraper import run_scraper
from modules.scoring import score_and_annotate
from modules.send_links import SendLinks

init(autoreset=True)

# ── CSV schema ────────────────────────────────────────────────────────────────

CSV_FIELDNAMES = [
    "lead_id",
    "nombre",
    "telefono",
    "categoria",
    "direccion",
    "puntaje",
    "resenas",
    "score",
    "filter_reason",
    "enviado",
    "fecha_envio",
    "estado_respuesta",
    "fecha_respuesta",
    "project_path",
    "live_url",
    "enviado_links",
    "fecha_envio_links",
    "fecha_entrega",
    "fecha_renovacion_web",
    "fecha_renovacion_hosting",
    "fecha_renovacion_mantenimiento",
    "notas",
]


class LeadGenAgency:
    def __init__(self):
        config.ensure_directories()
        self.builder = ClaudeBuilder()
        self.deployer = Deployer()
        self.sender = SendLinks()

    # ── Step 0: Scrape ────────────────────────────────────────────────────────

    def cmd_scrape(self) -> list[dict]:
        """Run Apify scraper and save results to dataset.json."""
        return run_scraper()

    # ── Step 1: Discover ──────────────────────────────────────────────────────

    def cmd_discover(self, dataset_file: str) -> list[dict]:
        """Read dataset.json and show a summary (no saves)."""
        df = Path(dataset_file)
        print(f"\n{Fore.CYAN}📂 Leyendo dataset: {df}")

        if not df.exists():
            print(f"{Fore.RED}❌ Archivo no encontrado: {df}")
            return []

        with open(df, "r", encoding="utf-8") as f:
            data = json.load(f)

        leads = data if isinstance(data, list) else [data]
        con_tel = sum(1 for l in leads if l.get("phone") or l.get("telefono"))
        con_web = sum(1 for l in leads if l.get("website") and "google.com/maps" not in l.get("website", ""))

        print(f"\n{'='*50}")
        print("📊 RESUMEN DEL DATASET")
        print(f"{'='*50}")
        print(f"   Total de registros:  {len(leads)}")
        print(f"   Con teléfono:        {con_tel}")
        print(f"   Con website real:    {con_web}")

        # Run filter preview
        filtered, stats = filter_leads(leads)
        print_filter_report(stats)

        return leads

    # ── Step 2: Send outreach ─────────────────────────────────────────────────

    def cmd_send(self, dataset_file: str, status_file: str) -> int:
        """Filter, dedup, score leads, then send WhatsApp outreach."""
        df = Path(dataset_file)
        if not df.exists():
            print(f"{Fore.RED}❌ Dataset no encontrado: {df}")
            return 0

        with open(df, "r", encoding="utf-8") as f:
            raw = json.load(f)
        leads = raw if isinstance(raw, list) else [raw]

        # 1. Niche + location filter
        filtered, stats = filter_leads(leads)
        print_filter_report(stats)

        if not filtered:
            print(f"{Fore.YELLOW}⚠️  Sin leads después del filtro. Abortando envíos.")
            return 0

        # 2. Score
        scored = score_and_annotate(filtered)
        below_threshold = [l for l in scored if l.get("score", 0) < config.SCORE_MIN_TO_CONTACT]
        scored = [l for l in scored if l.get("score", 0) >= config.SCORE_MIN_TO_CONTACT]

        if below_threshold:
            print(f"{Fore.YELLOW}   ℹ️  {len(below_threshold)} leads descartados por puntaje bajo (<{config.SCORE_MIN_TO_CONTACT})")

        # 3. Deduplication
        sf = Path(status_file)
        existing_ids = load_existing_ids(sf)
        new_leads, duplicates = filter_new_leads(scored, existing_ids)

        print(f"\n{'='*50}")
        print("📊 DEDUPLICACIÓN")
        print(f"{'='*50}")
        print(f"   Leads filtrados:     {len(scored)}")
        print(f"   Ya en estado.csv:    {len(duplicates)}")
        print(f"{Fore.GREEN}   Nuevos para enviar: {len(new_leads)}")

        if not new_leads:
            print(f"\n{Fore.YELLOW}✅ No hay leads nuevos para enviar.")
            return 0

        # 4. Build dataset for outreach (convert to outreach format)
        outreach_dataset = _leads_to_outreach_format(new_leads)

        # Save temporary dataset for OutreachBot
        tmp_dataset = config.DATA_DIR / "_filtered_leads.json"
        with open(tmp_dataset, "w", encoding="utf-8") as f:
            json.dump(outreach_dataset, f, ensure_ascii=False, indent=2)

        # 5. Send
        count = asyncio.run(OutreachBot().run(str(tmp_dataset), status_file, new_leads))

        tmp_dataset.unlink(missing_ok=True)
        return count

    # ── Step 3: Generate websites ─────────────────────────────────────────────

    def cmd_generate_webs(self, status_file: str) -> list[str] | None:
        return self.builder.generar_para_interesados(status_file)

    # ── Step 4: Deploy ────────────────────────────────────────────────────────

    def cmd_deploy(self, status_file: str, session_paths: list[str] | None = None):
        self.deployer.desplegar_interesados(status_file, session_paths=session_paths)

    # ── Step 5: Send links ────────────────────────────────────────────────────

    def cmd_send_links(self, status_file: str):
        self.sender.enviar_links(status_file)

    # ── Full pipeline ─────────────────────────────────────────────────────────

    def cmd_full(self, dataset_file: str, status_file: str):
        """Scrape → Filter → Dedup → Send → Generate → Deploy → Links."""
        print(f"\n{Fore.CYAN}{'='*60}")
        print("🚀 PIPELINE COMPLETO")
        print(f"{'='*60}")

        self.cmd_scrape()
        self.cmd_discover(dataset_file)

        enviados = self.cmd_send(dataset_file, status_file)
        if not enviados:
            print(f"\n{Fore.YELLOW}❌ Sin envíos. Abortando pipeline.")
            return

        session_paths = self.cmd_generate_webs(status_file)
        self.cmd_deploy(status_file, session_paths=session_paths)
        self.cmd_send_links(status_file)

    # ── Status ────────────────────────────────────────────────────────────────

    def cmd_status(self, status_file: str):
        sf = Path(status_file)
        if not sf.exists():
            print(f"{Fore.RED}❌ {status_file} no encontrado")
            return

        with open(sf, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        total = len(rows)
        enviados = sum(1 for r in rows if r.get("enviado", "").upper() == "SI")
        respondieron = sum(1 for r in rows if r.get("estado_respuesta", "") not in ("", "neutral"))
        interesados = sum(1 for r in rows if r.get("estado_respuesta", "") in ("interest", "positive_intent", "price_request"))
        rechazados = sum(1 for r in rows if r.get("estado_respuesta", "") == "rejection")
        con_web = sum(1 for r in rows if r.get("project_path"))
        con_link = sum(1 for r in rows if r.get("live_url"))
        links_ok = sum(1 for r in rows if r.get("enviado_links", "").upper() == "SI")

        print(f"\n{'='*55}")
        print("📊 ESTADO DEL PIPELINE")
        print(f"{'='*55}")
        print(f"   Total en CRM:             {total}")
        print(f"   Mensajes enviados:         {enviados}")
        print(f"   Respondieron:              {respondieron}")
        print(f"   Interesados:               {Fore.GREEN}{interesados}{Style.RESET_ALL}")
        print(f"   Rechazaron:                {Fore.RED}{rechazados}{Style.RESET_ALL}")
        print(f"   Websites generados:        {con_web}")
        print(f"   Sitios live:               {con_link}")
        print(f"   Links enviados:            {links_ok}")
        print(f"{'='*55}")

        # Renewal alerts
        hoy = datetime.now().date()
        renovaciones_proximas = []
        for r in rows:
            for campo in ("fecha_renovacion_web", "fecha_renovacion_hosting", "fecha_renovacion_mantenimiento"):
                fecha_str = r.get(campo, "")
                if not fecha_str:
                    continue
                try:
                    fecha = datetime.strptime(fecha_str[:10], "%Y-%m-%d").date()
                    dias = (fecha - hoy).days
                    if 0 <= dias <= 60:
                        renovaciones_proximas.append((dias, r["nombre"], campo, fecha_str[:10]))
                except ValueError:
                    pass

        if renovaciones_proximas:
            renovaciones_proximas.sort()
            print(f"\n{Fore.AMBER if hasattr(Fore, 'AMBER') else Fore.YELLOW}⚠️  RENOVACIONES PRÓXIMAS (60 días)")
            print(f"{'='*55}")
            for dias, nombre, campo, fecha in renovaciones_proximas:
                alerta = "🔴" if dias <= 7 else ("🟡" if dias <= 30 else "🟢")
                tipo = campo.replace("fecha_renovacion_", "").replace("_", " ")
                print(f"   {alerta} {nombre[:35]:35s} {tipo:12s} {fecha} ({dias}d)")

    # ── Schema migration ──────────────────────────────────────────────────────

    def cmd_migrate(self, status_file: str):
        """Add new columns to existing estado.csv without losing any data."""
        sf = Path(status_file)
        if not sf.exists():
            print(f"{Fore.RED}❌ {status_file} no encontrado")
            return

        with open(sf, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            existing_fields = reader.fieldnames or []
            rows = list(reader)

        missing = [f for f in CSV_FIELDNAMES if f not in existing_fields]
        if not missing:
            print(f"{Fore.GREEN}✅ estado.csv ya tiene todos los campos — sin cambios")
            return

        for row in rows:
            for col in missing:
                row.setdefault(col, "")

        with open(sf, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        print(f"{Fore.GREEN}✅ Migración completada: {len(missing)} columnas añadidas")
        print(f"   Nuevas columnas: {', '.join(missing)}")
        print(f"   Filas migradas:  {len(rows)}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _leads_to_outreach_format(leads: list[dict]) -> list[dict]:
    """Convert internal lead format to OutreachBot expected format."""
    result = []
    for l in leads:
        phone = l.get("phone") or l.get("telefono", "")
        website = l.get("website", "")
        if "google.com/maps" in website:
            website = ""
        result.append(
            {
                "title": l.get("title") or l.get("nombre", ""),
                "phone": phone,
                "website": website,
                "categoryName": l.get("categoryName") or l.get("categoria", ""),
                "address": l.get("street") or l.get("direccion", "Rosario"),
                "rating": l.get("totalScore") or l.get("puntaje", 4.5),
                "reviewCount": l.get("reviewsCount") or l.get("resenas", 0),
                "lead_id": l.get("lead_id", ""),
                "score": l.get("score", 0),
                "filter_reason": l.get("filter_reason", ""),
            }
        )
    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="LeadGen Amoblamientos Rosario — Pipeline de outreach"
    )
    parser.add_argument("--scrape", action="store_true", help="Ejecutar Apify scraper")
    parser.add_argument("--discover", metavar="DATASET", help="Leer y analizar dataset")
    parser.add_argument("--send", nargs=2, metavar=("DATASET", "STATUS"), help="Enviar outreach")
    parser.add_argument("--generate-webs", metavar="STATUS", help="Generar websites")
    parser.add_argument("--deploy", metavar="STATUS", help="Desplegar a Vercel")
    parser.add_argument("--send-links", metavar="STATUS", help="Enviar links a clientes")
    parser.add_argument("--full", nargs=2, metavar=("DATASET", "STATUS"), help="Pipeline completo")
    parser.add_argument("--status", metavar="STATUS", help="Ver estado del pipeline")
    parser.add_argument("--migrate", metavar="STATUS", help="Migrar estado.csv a nuevo schema")

    args = parser.parse_args()
    agency = LeadGenAgency()

    if args.scrape:
        agency.cmd_scrape()
    elif args.discover:
        agency.cmd_discover(args.discover)
    elif args.send:
        agency.cmd_send(args.send[0], args.send[1])
    elif args.generate_webs:
        agency.cmd_generate_webs(args.generate_webs)
    elif args.deploy:
        agency.cmd_deploy(args.deploy)
    elif args.send_links:
        agency.cmd_send_links(args.send_links)
    elif args.full:
        agency.cmd_full(args.full[0], args.full[1])
    elif args.status:
        agency.cmd_status(args.status)
    elif args.migrate:
        agency.cmd_migrate(args.migrate)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
