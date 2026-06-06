import asyncio
import json
import random
import re
from pathlib import Path
from datetime import datetime
from whatsplay import Client
from whatsplay.auth import LocalProfileAuth

# ===== CONFIGURACIÓN =====
LINKS_FILE = "dataset_crawler-google-places_2026-06-04_21-04-24-158.json"
DATA_DIR = Path.home() / "whatsapp_session"

# 20 PLANTILLAS
PLANTILLAS = [
    "¡Hola! 👋 Vi tu negocio de {categoria}. ¿Te interesaría recibir info sobre proveedores de insumos?",
    "✨ Hola! Tenemos promociones en insumos para {categoria} este mes. ¿Te interesa saber más?",
    "📱 ¡Buen día! Trabajamos con {categoria}. ¿Te interesaría conocer nuestros precios?",
    "🎯 Hola, tenemos materiales de primera para {categoria}. ¿Te parece si te cuento?",
    "💬 ¡Hola! ¿Cómo va la producción? Queríamos ofrecerte nuestros servicios.",
    "🪑 Buenos días. Somos proveedores de insumos para {categoria}. ¿Te interesaría una cotización?",
    "🌟 Promoción especial: 15% off en primera compra. ¿Te interesa?",
    "📞 ¡Hola! Tenemos insumos de calidad para tus proyectos de {categoria}.",
    "⚡ Hola, tenemos novedades en maderas y herrajes. ¿Te cuento en 1 minuto?",
    "✅ ¡Buenas! Queríamos ofrecerte nuestro catálogo de insumos.",
    "🎁 Hola, para {categoria} tenemos un kit de muestra gratis. ¿Te interesaría?",
    "📋 ¡Buen día! Estamos armando una lista de proveedores. ¿Te sumás?",
    "🏆 Trabajamos con los mejores {categoria}. ¿Te gustaría conocer por qué?",
    "💎 Para clientes del rubro tenemos precios especiales. ¿Te interesa?",
    "🆓 ¡Buenas! Probá nuestros insumos sin compromiso. ¿Te animas?",
    "📢 ¡Novedad! Llegaron nuevos herrajes. ¿Querés que te muestre?",
    "🎯 Oferta por tiempo limitado. ¿Te interesaría aprovecharla?",
    "🤝 Valoramos el trabajo de los {categoria}. ¿Podemos ayudarte?",
    "⭐ Los mejores {categoria} trabajan con nosotros. ¿Te gustaría saber por qué?",
    "🔥 ¡Buen día! Promo de lanzamiento. ¿Te interesaría saber más?"
]

TIEMPO_ENTRE_MENSAJES = 15  # segundos
# =========================

# Lista de dominios de redes sociales
REDES_SOCIALES = [
    'instagram.com', 'facebook.com', 'fb.com', 'twitter.com', 'x.com',
    'linkedin.com', 'youtube.com', 'tiktok.com', 'pinterest.com',
    'tumblr.com', 'snapchat.com', 'reddit.com'
]

def es_red_social(website: str) -> bool:
    if not website:
        return False
    website_lower = website.lower()
    return any(red in website_lower for red in REDES_SOCIALES)

def es_link_whatsapp(website: str) -> bool:
    if not website:
        return False
    website_lower = website.lower()
    return 'wa.me' in website_lower or 'whatsapp.com' in website_lower

def limpiar_telefono(telefono: str) -> str:
    """Convierte +54 341 550-7912 a 5493415507912"""
    if not telefono or not telefono.strip():
        return None
    solo_numeros = re.sub(r'[^\d]', '', telefono)
    if not solo_numeros:
        return None
    # Formato Argentina
    if solo_numeros.startswith('54'):
        return solo_numeros
    if len(solo_numeros) == 10:
        return '54' + solo_numeros
    if len(solo_numeros) == 11 and solo_numeros.startswith('9'):
        return '54' + solo_numeros
    return solo_numeros

def extraer_link_whatsapp(negocio: dict) -> tuple:
    """
    Lógica DEFINITIVA por cada negocio:

    PRIMERO: ¿Este negocio tiene el apartado "website"?
       SI → Evaluar su contenido
       NO → Ir a verificar teléfono

    DENTRO DE WEBSITE (si existe):
       ¿Es link directo de WhatsApp (wa.me o whatsapp.com)?
          SI → ENVIAR usando ESE link
          NO ↓
       ¿Es red social (Instagram, Facebook, etc.)?
          SI → ENVIAR con TELÉFONO (si existe)
          NO (sitio web propio) → NO ENVIAR

    SI NO EXISTE WEBSITE:
       ¿Tiene teléfono?
          SI → ENVIAR transformando a wa.me/54XXX
          NO → NO ENVIAR
    """
    nombre = negocio.get('title', 'Desconocido')
    telefono = negocio.get('phone', '')
    
    # Verificar si existe el apartado "website" en ESTE negocio
    tiene_website = 'website' in negocio and negocio['website'] is not None and str(negocio['website']).strip() != ''
    website = negocio.get('website', '') if tiene_website else ''
    
    # CASO 1: Este negocio TIENE website
    if tiene_website:
        # 1a: Link directo de WhatsApp
        if es_link_whatsapp(website):
            print(f"   ✅ {nombre}: website es link WhatsApp -> ENVIAR con ese link")
            return (website, "whatsapp_link")
        
        # 1b: Es red social
        elif es_red_social(website):
            if telefono and telefono.strip():
                telefono_limpio = limpiar_telefono(telefono)
                if telefono_limpio:
                    link = f"https://wa.me/{telefono_limpio}"
                    print(f"   ✅ {nombre}: website es red social + tiene teléfono -> ENVIAR con teléfono")
                    return (link, "telefono_por_red_social")
                else:
                    print(f"   ❌ {nombre}: website es red social pero teléfono inválido -> NO ENVIAR")
                    return (None, "red_social_telefono_invalido")
            else:
                print(f"   ❌ {nombre}: website es red social pero NO tiene teléfono -> NO ENVIAR")
                return (None, "red_social_sin_telefono")
        
        # 1c: Sitio web propio
        else:
            print(f"   ❌ {nombre}: tiene sitio web propio ({website}) -> NO ENVIAR")
            return (None, "sitio_propio")
    
    # CASO 2: Este negocio NO tiene website
    else:
        if telefono and telefono.strip():
            telefono_limpio = limpiar_telefono(telefono)
            if telefono_limpio:
                link = f"https://wa.me/{telefono_limpio}"
                print(f"   ✅ {nombre}: no tiene website + tiene teléfono -> ENVIAR")
                return (link, "telefono")
            else:
                print(f"   ❌ {nombre}: teléfono inválido -> NO ENVIAR")
                return (None, "telefono_invalido")
        else:
            print(f"   ❌ {nombre}: no tiene website ni teléfono -> NO ENVIAR")
            return (None, "sin_contacto")

async def cargar_negocios():
    """Carga el JSON y filtra negocios contactables"""
    try:
        with open(LINKS_FILE, 'r', encoding='utf-8') as f:
            datos = json.load(f)
        
        # Asegurar que es una lista
        negocios = datos if isinstance(datos, list) else [datos]
        
        print("\n" + "="*60)
        print("📋 ANALIZANDO CADA NEGOCIO INDIVIDUALMENTE...")
        print("="*60)
        
        negocios_procesados = []
        for negocio in negocios:
            link, motivo = extraer_link_whatsapp(negocio)
            
            if link:
                negocio['whatsapp_link'] = link
                negocio['motivo_contacto'] = motivo
                negocio['enviado'] = negocio.get('enviado', False)
                negocios_procesados.append(negocio)
        
        pendientes = [n for n in negocios_procesados if not n.get('enviado', False)]
        return pendientes, negocios_procesados
    
    except FileNotFoundError:
        print(f"❌ No se encuentra el archivo: {LINKS_FILE}")
        print(f"📁 Asegurate de que el archivo esté en la misma carpeta que este script")
        return [], []
    except json.JSONDecodeError as e:
        print(f"❌ Error en el formato JSON: {e}")
        return [], []

def guardar_progreso(negocios):
    """Guarda el estado después de cada envío"""
    with open(LINKS_FILE, 'w', encoding='utf-8') as f:
        for n in negocios:
            n.pop('whatsapp_link', None)
            n.pop('motivo_contacto', None)
        json.dump(negocios, f, indent=2, ensure_ascii=False)

async def enviar_mensaje(client, link, mensaje):
    """Envía un mensaje usando el link de WhatsApp"""
    numero = link.replace("https://wa.me/", "").split("?")[0]
    await client.send_message(numero, mensaje)
    await asyncio.sleep(random.uniform(2, 4))

async def main():
    print("="*60)
    print("🤖 BOT WHATSAPP - VERSIÓN DEFINITIVA")
    print("="*60)
    
    pendientes, todos = await cargar_negocios()
    
    print("\n" + "="*60)
    print("📊 RESUMEN DE ANÁLISIS")
    print("="*60)
    print(f"   📋 Negocios totales en archivo: {len(todos)}")
    print(f"   📤 Pendientes de enviar: {len(pendientes)}")
    print(f"   📝 Plantillas disponibles: {len(PLANTILLAS)}")
    
    if not pendientes:
        print("\n✅ No hay negocios pendientes para enviar")
        return
    
    print(f"   ⏱️  Tiempo estimado: {len(pendientes) * TIEMPO_ENTRE_MENSAJES / 60:.1f} minutos")
    
    # Inicializar WhatsApp
    auth = LocalProfileAuth(DATA_DIR)
    client = Client(auth=auth, headless=False)
    
    @client.event("on_auth")
    async def on_auth():
        print("\n📸 ESCANEA EL CÓDIGO QR EN LA VENTANA QUE SE ABRIÓ")
        print("   (Solo la primera vez, después se guarda la sesión)")
    
    await client.start()
    
    # Preparar plantillas
    plantillas_disponibles = PLANTILLAS.copy()
    random.shuffle(plantillas_disponibles)
    
    enviados = 0
    
    print("\n🚀 INICIANDO ENVÍOS...\n")
    
    for i, negocio in enumerate(pendientes):
        nombre = negocio.get('title', 'Cliente')
        link = negocio.get('whatsapp_link')
        motivo = negocio.get('motivo_contacto', 'desconocido')
        categoria = negocio.get('categoryName', 'carpintería/muebles')
        
        # Seleccionar plantilla (rotar sin repetir)
        if not plantillas_disponibles:
            plantillas_disponibles = PLANTILLAS.copy()
            random.shuffle(plantillas_disponibles)
        
        plantilla = plantillas_disponibles.pop(0)
        mensaje = plantilla.replace("{categoria}", categoria if categoria else "carpintería")
        
        print(f"\n{'─'*50}")
        print(f"📤 [{i+1}/{len(pendientes)}] {nombre}")
        print(f"   🔗 Contacto vía: {motivo}")
        print(f"   📝 Mensaje: {mensaje[:60]}...")
        
        try:
            await enviar_mensaje(client, link, mensaje)
            
            # Marcar como enviado
            negocio['enviado'] = True
            negocio['fecha_envio'] = datetime.now().isoformat()
            negocio['plantilla_usada'] = plantilla[:80]
            guardar_progreso(todos)
            
            enviados += 1
            print(f"   ✅ ENVIADO correctamente")
            
            # Pausa entre mensajes (15 segundos)
            if i < len(pendientes) - 1:
                pausa = TIEMPO_ENTRE_MENSAJES + random.uniform(-3, 3)
                print(f"   ⏰ Esperando {pausa:.1f} segundos antes del próximo...")
                await asyncio.sleep(max(10, pausa))
            
        except Exception as e:
            print(f"   ❌ ERROR: {str(e)[:100]}")
            await asyncio.sleep(5)
    
    print("\n" + "="*60)
    print("📊 RESUMEN FINAL")
    print("="*60)
    print(f"   ✅ Enviados hoy: {enviados}")
    print(f"   📋 Total contactables: {len(todos)}")
    print(f"   ⏳ Restantes: {len(pendientes) - enviados}")
    print("="*60)
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())