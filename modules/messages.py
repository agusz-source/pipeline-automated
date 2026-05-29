#!/usr/bin/env python3
# modules/messages.py - Generador de mensajes

import random
import json
from datetime import datetime
from colorama import Fore
from config import config

class MessageGenerator:
    
    TEMPLATES = [
    "Hola buenas! Soy Agustin y hago páginas web. Encontré su negocio en Google Maps y me llamó la atención la cantidad de reseñas buenas que tienen. Se que va a sonar raro, pero terminé armando una web desde cero inspirada en el negocio. Te la puedo mostrar?",

    "Buenas! Me llamo Agustin, soy desarrollador web. Vi su negocio mientras buscaba locales de Rosario y se nota que le ponen ganas al negocio. Se que va a sonar medio de la nada jajaj, pero les hice una web personalizada. Te interesaría verla?",

    "Hola! Cómo va? Soy Agustin. Encontré su negocio en internet y me gustó mucho cómo hablan los clientes de ustedes. Se que va a sonar raro, pero me inspiró a hacerles una web moderna basada en el local. Te la puedo pasar?",

    "Buenas! Soy Agustin y hago sitios web para negocios locales. Vi su perfil y se nota que hay bastante laburo detrás del lugar. Se que va a sonar medio random, pero les armé una web desde cero inspirada en eso. Te molestaría verla?",

    "Hola buenas! Me apareció su negocio en Maps y me sorprendió lo bien valorado que está. Me dedico al desarrollo web y, se que va a sonar raro, pero hice una web inspirada específicamente en la identidad del negocio. Te la puedo mostrar?",

    "Buenas! Soy Agustin. Encontré su local buscando negocios de la zona y me gustó mucho la imagen que transmite el lugar. Se que va a sonar raro viniendo de alguien que no conocen, pero hice una web basada en eso. Te interesaría verla?",

    "Hola! Soy Agustin, desarrollador web. Vi su negocio online y hay algo en la estética del negocio que destaca bastante. Se que va a sonar medio raro jajaj, pero me dieron ganas de hacerles una web personalizada. Te la puedo mostrar?",

    "Buenas! Cómo estás? Me llamo Agustin y hago webs para negocios. Encontré su perfil y se nota que tienen una clientela bastante fiel. Se que va a sonar raro, pero preparé una web pensando específicamente en el estilo del lugar. Te interesaría verla?",

    "Hola buenas! Soy Agustin. Vi su negocio en Google Maps y me llamó la atención lo prolijo que se ve todo. Se que va a sonar medio random, pero armé una web bastante distinta a las típicas inspirada en ustedes. Te la puedo mostrar?",

    "Buenas! Soy Agustin y trabajo haciendo páginas web. Encontré su negocio buscando locales de Rosario y se siente un negocio con identidad propia. Se que va a sonar raro, pero me dieron ganas de hacerles una web personalizada desde cero. Te molestaría hecharle un vistazo?"
]
    
    def generar_para_leads(self):
        with open(config.LEADS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            leads = data.get("leads", [])
        
        queue = []
        for lead in leads[:config.MAX_MENSAJES_POR_DIA]:
            mensaje = random.choice(self.TEMPLATES)
            queue.append({
                "lead": lead,
                "mensaje": mensaje,
                "created_at": datetime.now().isoformat()
            })
        
        with open(config.QUEUE_FILE, 'w', encoding='utf-8') as f:
            json.dump({"queue": queue}, f, indent=2, ensure_ascii=False)
        
        print(f"{Fore.GREEN}✅ {len(queue)} mensajes generados")
        return queue
