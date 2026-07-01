# Pipeline Automatizado — Binario Websites

Sistema automatizado de outreach por WhatsApp + generación de sitios web para negocios locales en Rosario, Argentina. Descubre negocios sin web, les manda un mensaje, genera el sitio, lo despliega y manda el link. Todo desde un dashboard web.

---

## Stack

| Capa | Tecnología |
|---|---|
| Dashboard | Flask + Flask-SocketIO + SQLAlchemy (SQLite) |
| WhatsApp bridge | Node.js + Baileys (headless, sin browser) |
| Generación de sitios | Claude (Anthropic API) |
| Despliegue | Vercel / GitHub |
| Scraping | Apify (Google Places) + OSM fallback |
| Imágenes stock | Pexels API (free) + Picsum fallback |
| Agente social | Claude Haiku + Instagram Graph API |

---

## Pipeline

```
[1] Scrape  →  [2] Filtro/Scoring  →  [3] Envío WA  →  [4] Genera Web  →  [5] Deploy  →  [6] Envía Link  →  [7] Seguimiento
```

Cada etapa se lanza desde el dashboard como un job en background. El estado de cada lead se guarda en SQLite.

---

## Setup

```bash
chmod +x setup.sh && ./setup.sh
```

El script hace todo de forma interactiva:
- Crea el virtualenv e instala dependencias Python
- Instala dependencias Node del bridge
- Crea directorios y archivos de datos
- Te pide las API keys una por una (con links e instrucciones)
- Valida la conexión con Anthropic, Pexels e Instagram
- Inicializa la base de datos SQLite

### Variables de entorno requeridas

| Variable | Descripción |
|---|---|
| `ANTHROPIC_API_KEY` | Para generación de sitios y agente social |
| `APIFY_TOKEN` | Scraping de Google Places |
| `WA_BRIDGE_URL` | URL del bridge de WhatsApp (default: `http://localhost:3001`) |
| `BRIDGE_SECRET` | Secret compartido entre dashboard y bridge |
| `GITHUB_USERNAME` | Para deploy de sitios |

### Variables opcionales

| Variable | Descripción |
|---|---|
| `INSTAGRAM_ACCESS_TOKEN` | Agente de redes sociales |
| `INSTAGRAM_BUSINESS_ID` | ID de cuenta de negocio de Meta |
| `PEXELS_API_KEY` | Imágenes stock de calidad (tiene fallback sin key) |
| `NTFY_TOPIC` | Push notifications via ntfy.sh |

---

## Correr el sistema

```bash
# 1. Levantar el bridge de WhatsApp
cd whatsapp_bridge && node index.js
# Escanear el QR con WhatsApp la primera vez

# 2. Levantar el dashboard
cd dashboard && ./run.sh

# Dashboard en: http://localhost:5000
```

---

## Estructura

```
pipeline-automated/
├── config.py                    # Config centralizada, carga .env
├── setup.sh                     # Setup interactivo completo
├── run.sh                       # Script de inicio rápido
├── requirements.txt
│
├── dashboard/
│   ├── app.py                   # Flask app + todas las rutas API
│   ├── database.py              # Modelos SQLAlchemy (Lead, Job)
│   ├── workers.py               # Jobs en background (scrape, send, generate, etc.)
│   ├── run.sh
│   ├── static/
│   │   ├── script.js            # Frontend SPA (vanilla JS)
│   │   └── style.css
│   └── templates/
│       └── index.html           # Layout del dashboard
│
├── modules/
│   ├── claude_builder.py        # Generación de sitios con Claude
│   ├── scraper.py               # Integración con Apify
│   ├── osm_discovery.py         # Fallback con OpenStreetMap
│   ├── niche_filter.py          # Filtrado y scoring de leads
│   ├── outreach.py              # Lógica de mensajes WA
│   ├── deploy.py                # Deploy a Vercel/GitHub
│   ├── send_links.py            # Envío de links generados
│   ├── social_agent.py          # Agente de Instagram (Haiku + Pexels)
│   └── phone_validator.py       # Validación de números
│
├── whatsapp_bridge/
│   ├── index.js                 # Bridge HTTP ↔ WhatsApp (Baileys)
│   ├── Dockerfile               # Para deploy en Fly.io
│   └── fly.toml
│
├── websites/                    # Sitios generados (uno por lead)
│   └── <nombre_negocio>/
│       ├── index.html
│       └── styles.css
│
└── data/
    ├── pipeline.db              # Base de datos SQLite
    └── wa_responses.json        # Respuestas de WhatsApp entrantes
```

---

## Secciones del Dashboard

| Sección | Descripción |
|---|---|
| Dashboard | Métricas clave: leads, enviados, sitios generados, conversión |
| Pipeline | Control de jobs: scrape, generate, send, deploy. Flujo visual del pipeline. |
| CRM | Tabla completa de leads con filtros, edición y scoring |
| Servicios | Gestión de servicios ofrecidos y precios |
| Seguimientos | Seleccioná leads contactados → elegí el mensaje (1, 2 o 3) → mandá → se marca el tag automáticamente |
| Websites | Vista de sitios generados con preview y links de deploy |
| Finanzas | Registro de ingresos y egresos |
| Clientes | Leads que cerraron como clientes |
| Configuración | Nichos activos, parámetros del pipeline |

---

## Agente de Redes Sociales

Genera y publica posts en Instagram sin intervención manual.

```bash
# Test de conexiones
python modules/social_agent.py --test

# Preview de contenido (sin publicar)
python modules/social_agent.py --generate --nombre "Mi Negocio" --categoria "estetica" --tipo servicio

# Publicar
python modules/social_agent.py --publish --nombre "Mi Negocio" --categoria "estetica" --tipo motivacional
```

Tipos de post: `servicio`, `motivacional`, `tip`, `promo`, `comunidad`.

Usa Claude Haiku para el copy, Pexels para imágenes stock, e Instagram Graph API para publicar. Todo gratuito salvo los tokens de Claude.

---

## WhatsApp Bridge en la nube (Fly.io)

Para no depender de tener la PC encendida:

```bash
cd whatsapp_bridge
fly launch
fly secrets set BRIDGE_SECRET=tu_secret
fly deploy
```

Actualizar en `.env`:
```
WA_BRIDGE_URL=https://tu-app.fly.dev
```

---

## Seguimientos

1. Ir a **Seguimientos** en el menú
2. Elegir el mensaje (Seg. 1, 2 o 3)
3. Seleccionar los leads
4. Presionar **Enviar seguimientos**
5. El sistema manda los mensajes por WhatsApp y marca cada lead con su tag en tiempo real

Los mensajes se editan en `dashboard/workers.py` → `FOLLOWUP_MESSAGES`.
