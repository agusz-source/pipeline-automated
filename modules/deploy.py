#!/usr/bin/env python3
# modules/deploy.py - Despliegue a GitHub y Netlify

import subprocess
import csv
from pathlib import Path
from colorama import Fore
from config import config


class Deployer:
    def __init__(self):
        self.github_user = config.GITHUB_USERNAME if hasattr(config, 'GITHUB_USERNAME') else ""
    
    def deploy_a_github(self, project_path, nombre):
        """Sube el proyecto a GitHub"""
        repo_name = f"leadgen-{nombre.lower().replace(' ', '-')}"
        repo_name = ''.join(c for c in repo_name if c.isalnum() or c == '-')
        
        print(f"{Fore.CYAN}📤 Subiendo a GitHub: {repo_name}")
        
        commands = [
            ["git", "init"],
            ["git", "add", "."],
            ["git", "commit", "-m", "Initial commit - LeadGen Rosario"],
            ["gh", "repo", "create", repo_name, "--public", "--source=.", "--push", "--yes"],
        ]

        try:
            result = None
            for cmd in commands:
                result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_path)
                if result.returncode != 0:
                    break
            if result and result.returncode == 0 and self.github_user:
                url = f"https://github.com/{self.github_user}/{repo_name}"
                print(f"{Fore.GREEN}✅ Repositorio: {url}")
                return url
            else:
                print(f"{Fore.YELLOW}⚠️ No se pudo subir a GitHub (gh no configurado)")
                return ""
        except Exception as e:
            print(f"{Fore.RED}❌ Error: {e}")
            return ""
    
    def deploy_a_netlify(self, project_path, nombre):
        """Despliega a Netlify"""
        print(f"{Fore.CYAN}🚀 Desplegando a Netlify...")
        
        try:
            result = subprocess.run(
                ["netlify", "deploy", "--prod", "--dir=."],
                capture_output=True,
                text=True,
                cwd=project_path
            )
            
            output = result.stdout
            url = ""
            for line in output.split('\n'):
                if 'Website URL:' in line or ('.netlify.app' in line and 'https://' in line):
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
    
    def desplegar_interesados(self, status_file):
        """Lee el CSV y despliega los websites generados"""
        if not Path(status_file).exists():
            print(f"{Fore.RED}❌ Archivo no encontrado: {status_file}")
            return
        
        # Leer CSV
        with open(status_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        actualizados = 0
        for row in rows:
            if row.get('project_path') and not row.get('live_url'):
                project_path = Path(row['project_path'])
                nombre = row['nombre']
                
                if project_path.exists():
                    repo_url = self.deploy_a_github(project_path, nombre)
                    live_url = self.deploy_a_netlify(project_path, nombre)
                    
                    row['live_url'] = live_url
                    actualizados += 1
        
        # Guardar CSV actualizado
        if actualizados > 0:
            with open(status_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=reader.fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        
        print(f"{Fore.GREEN}✅ Despliegue completado: {actualizados} sitios")