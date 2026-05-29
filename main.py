#!/usr/bin/env python3
# main.py - Orquestador principal

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import config
from modules.discovery import LeadDiscovery
from modules.analyzer import DigitalAnalyzer
from modules.messages import MessageGenerator
from modules.whatsapp import WhatsAppSender
from modules.claude_builder import ClaudeBuilder
from modules.deploy import Deployer
from modules.analytics import Analytics

class LeadGenAgency:
    def __init__(self):
        config.ensure_directories()
        self.discovery = LeadDiscovery()
        self.analyzer = DigitalAnalyzer()
        self.messages = MessageGenerator()
        self.whatsapp = WhatsAppSender()
        self.builder = ClaudeBuilder()
        self.deployer = Deployer()
        self.analytics = Analytics()
    
    def cmd_discover(self):
        self.discovery.scan_all()
    
    def cmd_analyze(self):
        self.analyzer.analizar()
    
    def cmd_generate_msgs(self):
        self.messages.generar_para_leads()
    
    def cmd_send(self):
        self.whatsapp.enviar_cola()
    
    def cmd_responders(self):
        print("\n📝 Ingresá los números que respondieron con interés:")
        numeros = input("Números (separados por coma): ")
        
        interesados = []
        for num in numeros.split(","):
            num = num.strip()
            interesados.append({
                "telefono": num,
                "fecha": datetime.now().isoformat()
            })
        
        import json
        with open(config.INTERESADOS_FILE, 'w') as f:
            json.dump({"interesados": interesados}, f, indent=2)
        
        print(f"✅ {len(interesados)} interesados registrados")
    
    def cmd_generate_webs(self):
        # Cargar leads para obtener datos completos
        import json
        with open(config.LEADS_FILE, 'r') as f:
            leads_data = json.load(f)
            all_leads = leads_data.get("leads", [])
        
        with open(config.INTERESADOS_FILE, 'r') as f:
            interested_data = json.load(f)
            interesados = interested_data.get("interesados", [])
        
        for inter in interesados:
            telefono = inter.get("telefono")
            lead = next((l for l in all_leads if l.get("telefono") == telefono), None)
            if lead:
                inter["lead_data"] = lead
        
        with open(config.INTERESADOS_FILE, 'w') as f:
            json.dump({"interesados": interesados}, f, indent=2)
        
        self.builder.generar_para_interesados()
    
    def cmd_deploy(self):
        self.deployer.desplegar_interesados()
    
    def cmd_send_links(self):
        self.deployer.enviar_links(self.whatsapp)
    
    def cmd_status(self):
        self.analytics.mostrar_estado()
    
    def cmd_full(self):
        self.cmd_discover()
        self.cmd_analyze()
        self.cmd_generate_msgs()
        self.cmd_send()

from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description='LeadGen Rosario')
    parser.add_argument('--discover', action='store_true')
    parser.add_argument('--analyze', action='store_true')
    parser.add_argument('--generate-msgs', action='store_true')
    parser.add_argument('--send', action='store_true')
    parser.add_argument('--responders', action='store_true')
    parser.add_argument('--generate-webs', action='store_true')
    parser.add_argument('--deploy', action='store_true')
    parser.add_argument('--send-links', action='store_true')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--full', action='store_true')
    
    args = parser.parse_args()
    agency = LeadGenAgency()
    
    if args.full:
        agency.cmd_full()
    elif args.discover:
        agency.cmd_discover()
    elif args.analyze:
        agency.cmd_analyze()
    elif args.generate_msgs:
        agency.cmd_generate_msgs()
    elif args.send:
        agency.cmd_send()
    elif args.responders:
        agency.cmd_responders()
    elif args.generate_webs:
        agency.cmd_generate_webs()
    elif args.deploy:
        agency.cmd_deploy()
    elif args.send_links:
        agency.cmd_send_links()
    elif args.status:
        agency.cmd_status()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
