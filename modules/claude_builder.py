#!/usr/bin/env python3
# modules/claude_builder.py - Generación de webs con Claude Code

import subprocess
import json
import shutil
from pathlib import Path
from datetime import datetime
from colorama import Fore
from config import config

class ClaudeBuilder:
    def __init__(self):
        self.websites_dir = config.WEBSITES_DIR
        self.websites_dir.mkdir(exist_ok=True)
    
    def generar_web(self, lead):
        nombre = lead.get("nombre", "negocio")
        categoria = lead.get("categoria", "")
        telefono = lead.get("telefono", "")
        direccion = lead.get("direccion", "Rosario")
        puntaje = lead.get("puntaje", 4.5)
        resenas = lead.get("resenas", 50)
        
        folder_name = nombre.lower().replace(' ', '_').replace('á', 'a').replace('é', 'e')
        folder_name = ''.join(c for c in folder_name if c.isalnum() or c == '_')
        project_path = self.websites_dir / folder_name
        project_path.mkdir(exist_ok=True)
        
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


El objetivo es que el sitio se sienta:
- humano
- específico
- real
- artesanal
- local
- creíble
- con identidad propia
- emocionalmente auténtico
- visualmente distintivo

━━━━━━━━━━━━━━━━━━━━━━
PROHIBIDO ABSOLUTO
━━━━━━━━━━━━━━━━━━━━━━

NO usar:
- layouts genéricos
- estructura repetitiva
- bloques clonados
- SaaS aesthetic
- startup aesthetic
- diseño tipo Framer template
- diseño tipo Webflow template
- diseño tipo Linear/Vercel
- glassmorphism exagerado
- glow effects innecesarios
- gradientes cliché violeta/azul
- copy corporativo vacío
- frases aspiracionales genéricas
- buzzwords
- “innovative solutions”
- “elevate your business”
- “digital transformation”
- “cutting-edge”
- “premium solutions”
- “next-generation”
- “modern experiences”
- “we take your business to the next level”

NO usar:
- testimonios falsos obvios
- estadísticas inventadas
- “+500 clientes”
- “98% satisfaction”
- fake counters
- FAQs irreales
- preguntas SEO artificiales
- texto demasiado perfecto
- copy excesivamente limpio
- lenguaje corporativo

NO usar:
- fotos stock irreales
- personas mirando laptops sonriendo
- coworkings falsos
- oficinas minimalistas fake
- imágenes americanizadas
- imágenes sin contexto local

NO usar:
- reveal animations en todo
- fade-up repetido
- stagger animations idénticas
- motion excesivo
- microinteracciones innecesarias
- hover effects genéricos
- animaciones infantiles

NO usar:
- React
- frameworks innecesarios
- bundles enormes
- SPA innecesaria
- JavaScript pesado

━━━━━━━━━━━━━━━━━━━━━━
OBLIGATORIO
━━━━━━━━━━━━━━━━━━━━━━

El sitio DEBE sentirse:
- específico al negocio
- diseñado a mano
- pensado por una persona real
- imperfectamente humano
- visualmente único
- auténtico
- local
- contextual

El diseño debe:
- romper simetrías cuando tenga sentido
- evitar spacing ultra perfecto
- evitar grids repetitivos
- evitar cards clonadas
- variar ritmos visuales
- tener jerarquía real
- tener tensión visual natural
- sentirse diseñado y no ensamblado

━━━━━━━━━━━━━━━━━━━━━━
COPYWRITING
━━━━━━━━━━━━━━━━━━━━━━

El texto debe:
- sonar humano
- sonar local
- sonar específico
- evitar marketing genérico
- evitar lenguaje corporativo
- mencionar detalles reales
- mencionar situaciones concretas
- mencionar comportamiento real de clientes
- sentirse escrito por alguien que conoce el rubro

Usar:
- frases naturales
- observaciones concretas
- detalles humanos
- personalidad
- tono auténtico

NO usar:
- slogans vacíos
- frases universales
- relleno SEO
- copy intercambiable entre rubros

━━━━━━━━━━━━━━━━━━━━━━
DISEÑO
━━━━━━━━━━━━━━━━━━━━━━

La dirección artística debe:
- ser coherente con el negocio
- tener personalidad visual propia
- evitar parecer una startup tecnológica
- evitar look “AI generated”
- evitar exceso de perfección

Usar:
- composiciones interesantes
- contraste visual inteligente
- ritmo visual variable
- layouts menos predecibles
- espacios con intención
- elementos visuales con propósito

━━━━━━━━━━━━━━━━━━━━━━
IMÁGENES
━━━━━━━━━━━━━━━━━━━━━━

Priorizar:
- imágenes realistas
- estética local
- fotos creíbles
- elementos específicos del rubro

Evitar:
- stock evidente
- estética corporativa internacional
- imágenes genéricas

━━━━━━━━━━━━━━━━━━━━━━
ANIMACIONES
━━━━━━━━━━━━━━━━━━━━━━

Las animaciones deben:
- ser mínimas
- sentirse naturales
- tener propósito
- mejorar UX
- no llamar demasiado la atención

Evitar:
- scroll reveal repetitivo
- motion excesivo
- animaciones genéricas de templates

━━━━━━━━━━━━━━━━━━━━━━
ESTRUCTURA
━━━━━━━━━━━━━━━━━━━━━━

NO usar automáticamente:
Hero → Features → Testimonials → FAQ → CTA

La estructura debe surgir del negocio y del contenido real.

━━━━━━━━━━━━━━━━━━━━━━
RESULTADO FINAL
━━━━━━━━━━━━━━━━━━━━━━

El sitio debe parecer:
- diseñado por una persona talentosa
- hecho específicamente para ese negocio
- visualmente moderno pero no genérico
- emocionalmente auténtico
- diferente a una landing típica de IA

Debe evitar completamente la sensación de:
- template
- startup clonada
- SaaS genérico
- diseño automático
- sitio “sin alma”

La prioridad NO es verse futurista.
La prioridad es verse humano, distintivo y real.
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
                self._guardar_metadata(project_path, lead)
                return str(project_path)
            else:
                return self._usar_plantilla(lead, project_path)
        except:
            return self._usar_plantilla(lead, project_path)
    
    def _usar_plantilla(self, lead, project_path):
        categoria = lead.get("categoria", "")
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
            
            html = html.replace("{nombre}", lead["nombre"])
            html = html.replace("{telefono}", lead.get("telefono", ""))
            html = html.replace("{direccion}", lead.get("direccion", "Rosario"))
            html = html.replace("{puntaje}", str(lead.get("puntaje", 4.5)))
            html = html.replace("{resenas}", str(lead.get("resenas", 50)))
            html = html.replace("{year}", str(datetime.now().year))
            
            with open(project_path / "index.html", 'w', encoding='utf-8') as f:
                f.write(html)
            
            print(f"{Fore.YELLOW}📄 Usando plantilla {template_name}")
        else:
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
        
        self._guardar_metadata(project_path, lead)
        return str(project_path)
    
    def _guardar_metadata(self, path, lead):
        with open(path / "metadata.json", 'w', encoding='utf-8') as f:
            json.dump({
                "negocio": lead["nombre"],
                "categoria": lead["categoria"],
                "telefono": lead["telefono"],
                "fecha": datetime.now().isoformat()
            }, f, indent=2)

    def generar_para_interesados(self):
        with open(config.INTERESADOS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            interesados = data.get("interesados", [])
        
        for inter in interesados:
            lead = inter.get("lead_data")
            if lead and not inter.get("project_path"):
                path = self.generar_web(lead)
                inter["project_path"] = path
        
        with open(config.INTERESADOS_FILE, 'w', encoding='utf-8') as f:
            json.dump({"interesados": interesados}, f, indent=2, ensure_ascii=False)
        
        print(f"{Fore.GREEN}✅ Websites generados")
