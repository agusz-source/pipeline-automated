#!/usr/bin/env python3
# modules/claude_builder.py - Generación de webs desde CSV

import subprocess
import json
import csv
from pathlib import Path
from datetime import datetime
from colorama import Fore
from config import config


class ClaudeBuilder:
    def __init__(self):
        self.websites_dir = config.WEBSITES_DIR
        self.websites_dir.mkdir(exist_ok=True)
    
    def generar_web(self, lead, project_path):
        """Genera un sitio web para un lead usando Claude o plantilla"""
        nombre = lead.get('nombre', 'negocio')
        categoria = lead.get('categoria', '')
        telefono = lead.get('telefono', '')
        direccion = lead.get('direccion', 'Rosario')
        puntaje = lead.get('puntaje', 4.5)
        resenas = lead.get('resenas', 50)
        
        print(f"{Fore.MAGENTA}🤖 Generando web para {nombre}...")
        
        prompt = f"""Creá un sitio web completo para {nombre}, un {categoria} en Rosario, Argentina.

DATOS REALES DEL NEGOCIO:
- Nombre: {nombre}
- Dirección: {direccion}
- Teléfono: {telefono}
- Calificación: {puntaje} estrellas
- Cantidad de reseñas: {resenas}

REQUERIMIENTOS:
1. HTML/CSS/JS (archivos separados)
2. Diseño moderno, responsive
3. Botón de WhatsApp con número {telefono}
4. Sección de 4 servicios típicos del rubro
5. Sección de testimonios (3 testimonios)
6. Mostrar puntaje y reseñas reales

GUARDAR EN: {project_path}
- index.html
- styles.css
- script.js

El sitio debe sentirse humano, específico, local, con identidad propia.
No usar templates genéricos, ni diseño SaaS/startup.
Crear los archivos directamente, no usar npm o build."""
        
        try:
            result = subprocess.run(
                ["claude", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                print(f"{Fore.GREEN}✅ Web generada en {project_path}")
                return True
            else:
                return self._usar_plantilla(lead, project_path)
        except:
            return self._usar_plantilla(lead, project_path)
    
    def _usar_plantilla(self, lead, project_path):
        """Fallback: usa plantilla HTML local"""
        categoria = lead.get('categoria', '')
        template_name = "barber"
        
        if "cafe" in categoria:
            template_name = "cafe"
        elif "gym" in categoria or "gimnasio" in categoria:
            template_name = "gym"
        elif "restaurant" in categoria or "restaurante" in categoria or "parrilla" in categoria:
            template_name = "restaurant"
        elif "salon" in categoria or "belleza" in categoria or "estetica" in categoria:
            template_name = "beauty"
        
        template_path = config.TEMPLATES_DIR / f"{template_name}.html"
        
        if template_path.exists():
            with open(template_path, 'r', encoding='utf-8') as f:
                html = f.read()
            
            html = html.replace("{nombre}", lead.get('nombre', ''))
            html = html.replace("{telefono}", lead.get('telefono', ''))
            html = html.replace("{direccion}", lead.get('direccion', 'Rosario'))
            html = html.replace("{puntaje}", str(lead.get('puntaje', 4.5)))
            html = html.replace("{resenas}", str(lead.get('resenas', 50)))
            html = html.replace("{year}", str(datetime.now().year))
            
            with open(project_path / "index.html", 'w', encoding='utf-8') as f:
                f.write(html)
            
            print(f"{Fore.YELLOW}📄 Usando plantilla {template_name}")
        else:
            # Plantilla mínima de emergencia
            html = f"""<!DOCTYPE html>
<html>
<head><title>{lead['nombre']}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {{ font-family: Arial; margin: 0; padding: 0; }}
.hero {{ background: #1a1a1a; color: white; text-align: center; padding: 50px; }}
.whatsapp-btn {{ background: #25d366; color: white; padding: 10px 20px; border-radius: 50px; text-decoration: none; }}
</style>
</head>
<body>
<div class="hero">
<h1>{lead['nombre']}</h1>
<p>{lead['direccion']}</p>
<a href="https://wa.me/{lead['telefono']}" class="whatsapp-btn">WhatsApp</a>
</div>
</body>
</html>"""
            with open(project_path / "index.html", 'w', encoding='utf-8') as f:
                f.write(html)
        
        return True
    
    def generar_para_interesados(self, status_file):
        """Lee el CSV y genera websites para los que tienen enviado=SI"""
        if not Path(status_file).exists():
            print(f"{Fore.RED}❌ Archivo no encontrado: {status_file}")
            return
        
        # Leer CSV
        with open(status_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        actualizados = 0
        for row in rows:
            if row.get('enviado', '').upper() == 'SI' and not row.get('project_path'):
                nombre = row['nombre']
                telefono = row['telefono']
                
                # Crear carpeta segura
                folder_name = nombre.lower().replace(' ', '_').replace('á', 'a').replace('é', 'e')
                folder_name = ''.join(c for c in folder_name if c.isalnum() or c == '_')
                project_path = self.websites_dir / folder_name
                project_path.mkdir(exist_ok=True)
                
                # Construir lead dict
                lead = {
                    'nombre': nombre,
                    'categoria': row.get('categoria', 'negocio'),
                    'telefono': telefono,
                    'direccion': row.get('direccion', 'Rosario'),
                    'puntaje': row.get('puntaje', 4.5),
                    'resenas': row.get('resenas', 30),
                }
                
                if self.generar_web(lead, project_path):
                    row['project_path'] = str(project_path)
                    actualizados += 1
        
        # Guardar CSV actualizado
        if actualizados > 0:
            with open(status_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=reader.fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        
        print(f"{Fore.GREEN}✅ Websites generados: {actualizados}")