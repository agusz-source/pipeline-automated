#!/usr/bin/env python3
# main.py - Orquestador principal con pipeline completo

import sys
import asyncio
import argparse
import csv
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from config import config
from modules.claude_builder import ClaudeBuilder
from modules.deploy import Deployer
from modules.outreach import OutreachBot
from modules.send_links import SendLinks


class LeadGenAgency:
    def __init__(self):
        config.ensure_directories()
        self.builder = ClaudeBuilder()
        self.deployer = Deployer()
        self.sender = SendLinks()
    
    def cmd_discover(self, dataset_file):
        """Paso 1: Lee dataset.json y muestra resumen (no guarda nada)"""
        print(f"\n📂 Leyendo dataset: {dataset_file}")
        
        if not Path(dataset_file).exists():
            print(f"❌ Archivo no encontrado: {dataset_file}")
            return
        
        with open(dataset_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Asegurar que es una lista
        leads = data if isinstance(data, list) else [data]
        
        print(f"\n{'='*50}")
        print(f"📊 RESUMEN DEL DATASET")
        print(f"{'='*50}")
        print(f"   Total de negocios: {len(leads)}")
        
        # Contar cuántos tienen teléfono
        con_telefono = sum(1 for l in leads if l.get('phone'))
        print(f"   Con teléfono: {con_telefono}")
        
        # Contar cuántos tienen website propio (aproximado)
        con_web = sum(1 for l in leads if l.get('website'))
        print(f"   Con website: {con_web}")
        
        print(f"\n✅ Discovery completado (no se guardó nada)")
        return leads
    
    def cmd_send(self, dataset_file, status_file):
        """Paso 2: Envía mensajes de outreach y genera CSV"""
        print(f"\n📤 Ejecutando outreach...")
        print(f"   Dataset: {dataset_file}")
        print(f"   Estado: {status_file}")

        count = asyncio.run(OutreachBot().run(dataset_file, status_file))

        if count > 0:
            print(f"\n✅ Envíos completados: {count}. Estado guardado en {status_file}")
        else:
            print(f"\n⚠️ No se enviaron mensajes")

        return count
    
    def cmd_generate_webs(self, status_file):
        """Paso 3: Genera websites para los que tienen enviado=SI"""
        self.builder.generar_para_interesados(status_file)
    
    def cmd_deploy(self, status_file):
        """Paso 4: Despliega los websites generados"""
        self.deployer.desplegar_interesados(status_file)
    
    def cmd_send_links(self, status_file):
        """Paso 5: Envía los links a los interesados"""
        self.sender.enviar_links(status_file)
    
    def cmd_full(self, dataset_file, status_file):
        """Pipeline completo: discover → send → generate-webs → deploy → send-links"""
        self.cmd_discover(dataset_file)
        enviados = self.cmd_send(dataset_file, status_file)
        if not enviados:
            print("\n❌ No se enviaron mensajes. Abortando pipeline.")
            return
        self.cmd_generate_webs(status_file)
        self.cmd_deploy(status_file)
        self.cmd_send_links(status_file)
    
    def cmd_status(self, status_file):
        """Muestra el estado actual desde el CSV"""
        if not Path(status_file).exists():
            print(f"❌ Archivo de estado no encontrado: {status_file}")
            return
        
        with open(status_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        total = len(rows)
        enviados = sum(1 for r in rows if r.get('enviado', '').upper() == 'SI')
        con_web = sum(1 for r in rows if r.get('live_url'))
        links_enviados = sum(1 for r in rows if r.get('enviado_links', '').upper() == 'SI')
        
        print(f"\n{'='*50}")
        print(f"📊 ESTADO DEL PIPELINE")
        print(f"{'='*50}")
        print(f"   Total seleccionados: {total}")
        print(f"   Mensajes enviados: {enviados}")
        print(f"   Websites generados: {con_web}")
        print(f"   Links enviados: {links_enviados}")
        print(f"{'='*50}")


def main():
    parser = argparse.ArgumentParser(description='LeadGen Rosario - Pipeline de outreach')
    
    parser.add_argument('--discover', metavar='DATASET', help='Lee el dataset (ej: dataset.json)')
    parser.add_argument('--send', nargs=2, metavar=('DATASET', 'STATUS'), help='Envía mensajes y genera CSV')
    parser.add_argument('--generate-webs', metavar='STATUS', help='Genera websites desde CSV')
    parser.add_argument('--deploy', metavar='STATUS', help='Despliega websites')
    parser.add_argument('--send-links', metavar='STATUS', help='Envía links por WhatsApp')
    parser.add_argument('--full', nargs=2, metavar=('DATASET', 'STATUS'), help='Pipeline completo')
    parser.add_argument('--status', metavar='STATUS', help='Muestra estado del pipeline')
    
    args = parser.parse_args()
    agency = LeadGenAgency()
    
    if args.discover:
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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()