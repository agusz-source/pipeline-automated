#!/usr/bin/env python3
# modules/deploy.py - Despliegue a GitHub y Netlify

import subprocess
import json
from pathlib import Path
from colorama import Fore
from config import config

class Deployer:
    def __init__(self):
        self.github_user = config.GITHUB_USERNAME
    
    def deploy_a_github(self, project_path, nombre):
        repo_name = f"leadgen-{nombre.lower().replace(' ', '-')}"
        repo_name = ''.join(c for c in repo_name if c.isalnum() or c == '-')
        
        print(f"{Fore.CYAN}📤 Subiendo a GitHub: {repo_name}")
        
        commands = f"""
        cd {project_path}
        git init
        git add .
        git commit -m "Initial commit - LeadGen Rosario"
        gh repo create {repo_name} --public --source=. --push --yes
        """
        
        try:
            result = subprocess.run(commands, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                url = f"https://github.com/{self.github_user}/{repo_name}"
                print(f"{Fore.GREEN}✅ Repositorio: {url}")
                return url
            else:
                print(f"{Fore.RED}❌ Error: {result.stderr}")
                return ""
        except Exception as e:
            print(f"{Fore.RED}❌ Error: {e}")
            return ""
    
    def deploy_a_netlify(self, project_path, nombre):
        print(f"{Fore.CYAN}🚀 Desplegando a Netlify...")
        
        try:
            result = subprocess.run(
                f"cd {project_path} && netlify deploy --prod --dir=.",
                shell=True,
                capture_output=True,
                text=True
            )
            
            output = result.stdout
            url = ""
            for line in output.split('\n'):
                if 'Website URL:' in line or 'https://' in line and '.netlify.app' in line:
                    parts = line.split()
                    for part in parts:
                        if 'netlify.app' in part:
                            url = part.strip()
                            break
            
            if not url:
                url = f"https://{nombre.lower().replace(' ', '-')}.netlify.app"
            
            print(f"{Fore.GREEN}✅ URL: {url}")
            return url
        except Exception as e:
            print(f"{Fore.RED}❌ Error: {e}")
            return ""
    
    def desplegar_interesados(self):
        with open(config.INTERESADOS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            interesados = data.get("interesados", [])
        
        for inter in interesados:
            lead = inter.get("lead_data")
            project_path = inter.get("project_path")
            
            if lead and project_path and not inter.get("live_url"):
                repo_url = self.deploy_a_github(project_path, lead["nombre"])
                live_url = self.deploy_a_netlify(project_path, lead["nombre"])
                inter["repo_url"] = repo_url
                inter["live_url"] = live_url
        
        with open(config.INTERESADOS_FILE, 'w', encoding='utf-8') as f:
            json.dump({"interesados": interesados}, f, indent=2, ensure_ascii=False)
        
        print(f"{Fore.GREEN}✅ Despliegue completado")
    
    def enviar_links(self, whatsapp_sender):
        with open(config.INTERESADOS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            interesados = data.get("interesados", [])
        
        for inter in interesados:
            lead = inter.get("lead_data")
            url = inter.get("live_url")
            telefono = inter.get("telefono")
            
            if url and telefono:
                mensaje = f"¡Listo! Tu web está online: {url}"
                whatsapp_sender.enviar(telefono, mensaje, lead.get("nombre", "cliente"))
                if inter != interesados[-1]:
                    time.sleep(config.INTERVALO_SEGUNDOS)

import time
