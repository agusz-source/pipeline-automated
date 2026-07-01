#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Binario Websites — Setup interactivo
#  Configura todas las dependencias y claves API del pipeline.
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# ── Colores ───────────────────────────────────────────────────
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; C='\033[0;36m'
B='\033[1;34m'; W='\033[1;37m'; DIM='\033[2m'; RESET='\033[0m'

ok()    { echo -e "  ${G}✅  $*${RESET}"; }
warn()  { echo -e "  ${Y}⚠️   $*${RESET}"; }
fail()  { echo -e "  ${R}❌  $*${RESET}"; }
info()  { echo -e "  ${C}→   $*${RESET}"; }
step()  { echo -e "\n${B}── $* ${DIM}─────────────────────────────────────────${RESET}"; }
title() { echo -e "\n${W}$*${RESET}"; }
hint()  { echo -e "     ${DIM}$*${RESET}"; }

ERRORS=0
err_inc() { ERRORS=$((ERRORS+1)); }

clear
echo -e "${C}"
echo "  ╔═══════════════════════════════════════════════════╗"
echo "  ║   🌐  Binario Websites — Setup                    ║"
echo "  ║   Pipeline de outreach + webs + social media      ║"
echo "  ╚═══════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  Directorio: ${C}$PROJECT_DIR${RESET}"
echo ""

# ──────────────────────────────────────────────────────────────
# 1. Python
# ──────────────────────────────────────────────────────────────
step "Python 3.10+"
PYTHON=python3
if ! command -v "$PYTHON" &>/dev/null; then
    fail "python3 no encontrado. Instalá Python 3.10+ desde python.org"
    err_inc
else
    PY_VER=$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
    PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
        fail "Python $PY_VER detectado — se requiere 3.10+"
        err_inc
    else
        ok "Python $PY_VER"
    fi
fi

# ──────────────────────────────────────────────────────────────
# 2. Entorno virtual
# ──────────────────────────────────────────────────────────────
step "Entorno virtual (venv)"
VENV_PY="$PROJECT_DIR/venv/bin/python"
VENV_PIP="$PROJECT_DIR/venv/bin/pip"

if [ -d "$PROJECT_DIR/venv" ]; then
    ok "venv ya existe"
else
    info "Creando venv..."
    "$PYTHON" -m venv "$PROJECT_DIR/venv"
    ok "venv creado"
fi

if [ ! -f "$VENV_PY" ]; then
    fail "Ejecutable Python no encontrado en venv — recreando"
    rm -rf "$PROJECT_DIR/venv"
    "$PYTHON" -m venv "$PROJECT_DIR/venv"
fi

info "Actualizando pip..."
"$VENV_PIP" install --upgrade pip --quiet

info "Instalando dependencias Python..."
"$VENV_PIP" install -r "$PROJECT_DIR/requirements.txt" --quiet
ok "requirements.txt instalado"

# ──────────────────────────────────────────────────────────────
# 3. Node.js
# ──────────────────────────────────────────────────────────────
step "Node.js + WhatsApp Bridge"
if ! command -v node &>/dev/null; then
    fail "node no encontrado — instalá Node.js 18+ desde nodejs.org"
    err_inc
else
    NODE_VER=$(node -e "process.stdout.write(process.version)")
    NODE_MAJOR=$(echo "$NODE_VER" | tr -d 'v' | cut -d. -f1)
    if [ "$NODE_MAJOR" -lt 18 ]; then
        warn "Node $NODE_VER — se recomienda 18+"
    else
        ok "Node $NODE_VER"
    fi

    if [ -d "$PROJECT_DIR/whatsapp_bridge" ]; then
        info "Instalando dependencias Node (whatsapp_bridge/)..."
        (cd "$PROJECT_DIR/whatsapp_bridge" && npm install --silent 2>&1)
        ok "npm install completado"
    else
        warn "whatsapp_bridge/ no encontrado — saltando"
    fi
fi

# ──────────────────────────────────────────────────────────────
# 4. Vercel CLI
# ──────────────────────────────────────────────────────────────
step "Vercel CLI (deploy de sitios)"
if command -v vercel &>/dev/null; then
    ok "vercel CLI $(vercel --version 2>/dev/null || echo '')"
else
    info "Instalando Vercel CLI..."
    if npm install -g vercel --silent 2>/dev/null; then
        ok "vercel CLI instalado"
    else
        warn "No se pudo instalar vercel CLI — deploy manual requerido"
    fi
fi

# ──────────────────────────────────────────────────────────────
# 5. Directorios
# ──────────────────────────────────────────────────────────────
step "Directorios y archivos base"
for dir in data logs websites templates; do
    mkdir -p "$PROJECT_DIR/$dir"
    ok "$dir/"
done

_init_json() {
    [ ! -f "$1" ] && echo "$2" > "$1" && ok "Creado: $(basename "$1")" || ok "Existe: $(basename "$1")"
}
_init_json "$PROJECT_DIR/data/conversaciones.json" '{}'
_init_json "$PROJECT_DIR/data/blacklist.json" '[]'

# ──────────────────────────────────────────────────────────────
# 6. Variables de entorno — CONFIGURACIÓN INTERACTIVA
# ──────────────────────────────────────────────────────────────
step "Variables de entorno (.env)"

ENV_FILE="$PROJECT_DIR/.env"

# Read current value for a key (empty string if not set)
_get() {
    grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || echo ""
}

# Write/update a key in .env
_set() {
    local key="$1" val="$2"
    if grep -qE "^${key}=" "$ENV_FILE" 2>/dev/null; then
        # Replace in-place (compatible with Linux and macOS)
        local escaped
        escaped=$(printf '%s\n' "$val" | sed 's/[[\.*^$()+?{|]/\\&/g')
        sed -i "s|^${key}=.*|${key}=${escaped}|" "$ENV_FILE"
    else
        echo "${key}=${val}" >> "$ENV_FILE"
    fi
}

# Create .env if it doesn't exist
if [ ! -f "$ENV_FILE" ]; then
    touch "$ENV_FILE"
    info ".env creado"
fi

# Masked display of a value
_mask() {
    local v="$1"
    if [ -z "$v" ]; then echo "(vacío)"; return; fi
    local len=${#v}
    if [ "$len" -le 8 ]; then echo "***"; return; fi
    echo "${v:0:4}...${v: -4}"
}

# Interactive prompt for a key
# Usage: _ask_key KEY "Descripcion" "https://link"
_ask_key() {
    local key="$1" desc="$2" link="$3"
    local current
    current=$(_get "$key")
    local masked
    masked=$(_mask "$current")

    echo ""
    echo -e "  ${W}${key}${RESET}"
    echo -e "  ${DIM}${desc}${RESET}"
    [ -n "$link" ] && echo -e "  ${DIM}Obtener: ${C}${link}${RESET}"
    echo -e "  Actual: ${DIM}${masked}${RESET}"

    if [ -n "$current" ]; then
        printf "  ¿Cambiar? (y/N): "
        read -r change
        [ "$change" != "y" ] && [ "$change" != "Y" ] && return
    fi

    printf "  Nuevo valor: "
    read -r new_val
    if [ -n "$new_val" ]; then
        _set "$key" "$new_val"
        ok "$key actualizado"
    else
        warn "$key no modificado (entrada vacía)"
    fi
}

echo ""
echo -e "${W}  Configurá cada clave API a continuación."
echo -e "  Presioná Enter para mantener el valor actual.${RESET}"

# ── Anthropic ─────────────────────────────────────────────────
title "  [Anthropic — REQUERIDO]"
hint "Necesitás una cuenta en anthropic.com y una API key activa."
hint "Sin esta clave, la generación de webs y el social agent NO funcionan."
_ask_key "ANTHROPIC_API_KEY" \
    "API key de Anthropic — usada para generar sitios web y contenido social" \
    "https://console.anthropic.com/settings/keys"

# ── Apify ─────────────────────────────────────────────────────
title "  [Apify — para scraping de Google Maps]"
hint "Cuenta gratuita disponible. Necesitás el actor 'compass/crawler-google-places'."
hint "Sin esto no podés descubrir nuevos leads, pero el resto del pipeline funciona."
_ask_key "APIFY_TOKEN" \
    "Token principal de Apify (scraping Google Maps)" \
    "https://console.apify.com/account/integrations"
_ask_key "APIFY_TOKEN_2" \
    "Segunda cuenta Apify opcional (mayor cuota de scraping)" \
    "https://console.apify.com/account/integrations"
_ask_key "APIFY_ACTOR_ID" \
    "ID del actor de Apify (default: compass/crawler-google-places)" \
    ""
[ -z "$(_get APIFY_ACTOR_ID)" ] && _set "APIFY_ACTOR_ID" "compass/crawler-google-places"

# ── WhatsApp Bridge ───────────────────────────────────────────
title "  [WhatsApp Bridge]"
hint "El bridge corre localmente. Solo cambiá si lo moviste a un servidor remoto."
_ask_key "WA_BRIDGE_URL" \
    "URL del bridge de WhatsApp (local o Fly.io/Railway)" \
    ""
[ -z "$(_get WA_BRIDGE_URL)" ] && _set "WA_BRIDGE_URL" "http://localhost:3001"

_ask_key "BRIDGE_SECRET" \
    "Clave secreta compartida entre el CRM y el bridge" \
    ""
if [ -z "$(_get BRIDGE_SECRET)" ]; then
    _set "BRIDGE_SECRET" "$(openssl rand -hex 20 2>/dev/null || head -c 20 /dev/urandom | xxd -p)"
    ok "BRIDGE_SECRET generado automáticamente"
fi

_ask_key "WA_BRIDGE_PORT" \
    "Puerto del bridge (default: 3001)" \
    ""
[ -z "$(_get WA_BRIDGE_PORT)" ] && _set "WA_BRIDGE_PORT" "3001"

# ── Instagram / Meta ──────────────────────────────────────────
title "  [Instagram / Meta — para Social Media Agent]"
hint "Necesitás: cuenta Instagram Business/Creator + Facebook App gratis."
hint ""
hint "Pasos para obtener el token:"
hint "  1. Ir a developers.facebook.com → Crear App (tipo: Business)"
hint "  2. Agregar producto 'Instagram Graph API'"
hint "  3. En Graph API Explorer: seleccionar tu app"
hint "  4. Generar token con permisos: instagram_content_publish,"
hint "     instagram_basic, pages_show_list, pages_read_engagement"
hint "  5. Hacer clic en 'Generate Access Token' → copiar"
hint "  6. Extender a token de larga duracion:"
hint "     curl -X GET 'https://graph.facebook.com/v21.0/oauth/access_token"
hint "       ?grant_type=fb_exchange_token"
hint "       &client_id=TU_APP_ID"
hint "       &client_secret=TU_APP_SECRET"
hint "       &fb_exchange_token=TU_TOKEN_CORTO'"
hint ""
hint "  Para obtener INSTAGRAM_BUSINESS_ID:"
hint "    curl 'https://graph.facebook.com/v21.0/me/accounts?access_token=TU_TOKEN'"
hint "    → copiá el id del page, luego:"
hint "    curl 'https://graph.facebook.com/v21.0/PAGE_ID?fields=instagram_business_account&access_token=TU_TOKEN'"
echo ""

_ask_key "META_APP_ID" \
    "ID de tu Facebook App (developers.facebook.com → tu app → App ID)" \
    "https://developers.facebook.com"
_ask_key "META_APP_SECRET" \
    "Secret de tu Facebook App (Settings → Basic → App Secret)" \
    "https://developers.facebook.com"
_ask_key "INSTAGRAM_ACCESS_TOKEN" \
    "Token de acceso larga duracion de Instagram Graph API (60 dias, auto-renovable)" \
    "https://developers.facebook.com/tools/explorer/"
_ask_key "INSTAGRAM_BUSINESS_ID" \
    "ID numerico de tu cuenta Instagram Business/Creator" \
    ""

# ── Pexels ────────────────────────────────────────────────────
title "  [Pexels — imágenes stock gratuitas]"
hint "API completamente gratuita. Se usa para buscar fotos por categoria."
hint "Sin esta clave se usa Picsum (fotos aleatorias) como fallback."
_ask_key "PEXELS_API_KEY" \
    "API key de Pexels (gratis, sin limites para uso normal)" \
    "https://www.pexels.com/api/"

# ── GitHub ────────────────────────────────────────────────────
title "  [GitHub — para deploy con Vercel]"
_ask_key "GITHUB_USERNAME" \
    "Tu usuario de GitHub (para que Vercel pueda importar el repo)" \
    "https://github.com"

# ── ntfy ─────────────────────────────────────────────────────
title "  [ntfy — notificaciones push al celular (opcional)]"
hint "Instalá la app 'ntfy' en tu celular y suscribite al topic que uses."
hint "Recibís notificaciones cuando alguien responde tu WhatsApp."
_ask_key "NTFY_TOPIC" \
    "Topic de ntfy.sh (ej: binario-crm-miusuario) — dejá vacío para deshabilitar" \
    "https://ntfy.sh"

# ──────────────────────────────────────────────────────────────
# 7. Validación del .env final
# ──────────────────────────────────────────────────────────────
step "Validando .env"

_check_key() {
    local key="$1" required="$2"
    local val
    val=$(_get "$key")
    if [ -n "$val" ]; then
        ok "$key"
    elif [ "$required" = "required" ]; then
        fail "$key — REQUERIDO pero no configurado"
        err_inc
    else
        warn "$key — no configurado (funcionalidad limitada)"
    fi
}

_check_key "ANTHROPIC_API_KEY"    required
_check_key "APIFY_TOKEN"          optional
_check_key "WA_BRIDGE_URL"        required
_check_key "BRIDGE_SECRET"        required
_check_key "INSTAGRAM_ACCESS_TOKEN" optional
_check_key "INSTAGRAM_BUSINESS_ID"  optional
_check_key "PEXELS_API_KEY"         optional

# ──────────────────────────────────────────────────────────────
# 8. Inicializar base de datos SQLite
# ──────────────────────────────────────────────────────────────
step "Base de datos SQLite"
if [ -f "$VENV_PY" ]; then
    "$VENV_PY" - << 'PYEOF'
import sys
sys.path.insert(0, 'dashboard')
sys.path.insert(0, '.')
try:
    from database import init_db
    init_db()
    print("  \033[0;32m✅  database OK (data/pipeline.db)\033[0m")
except Exception as e:
    print(f"  \033[0;31m❌  {e}\033[0m")
PYEOF
fi

# ──────────────────────────────────────────────────────────────
# 9. Tests de conexión
# ──────────────────────────────────────────────────────────────
step "Tests de conexión"

ANTHROPIC_KEY=$(_get "ANTHROPIC_API_KEY")
if [ -n "$ANTHROPIC_KEY" ] && [ -f "$VENV_PY" ]; then
    info "Testeando Anthropic..."
    "$VENV_PY" - << PYEOF 2>/dev/null
import sys
sys.path.insert(0, '.')
import anthropic, os
from dotenv import load_dotenv
load_dotenv('.env')
try:
    c = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    c.messages.create(model='claude-haiku-4-5-20251001', max_tokens=5,
                      messages=[{'role':'user','content':'hi'}])
    print("  \033[0;32m✅  Anthropic Claude Haiku OK\033[0m")
except Exception as e:
    print(f"  \033[0;31m❌  Anthropic: {e}\033[0m")
PYEOF
fi

PEXELS_KEY=$(_get "PEXELS_API_KEY")
if [ -n "$PEXELS_KEY" ] && [ -f "$VENV_PY" ]; then
    info "Testeando Pexels..."
    "$VENV_PY" - << PYEOF 2>/dev/null
import requests, os
from dotenv import load_dotenv
load_dotenv('.env')
try:
    r = requests.get('https://api.pexels.com/v1/search',
        headers={'Authorization': os.getenv('PEXELS_API_KEY','')},
        params={'query':'business','per_page':1}, timeout=5)
    r.raise_for_status()
    print("  \033[0;32m✅  Pexels API OK\033[0m")
except Exception as e:
    print(f"  \033[0;31m❌  Pexels: {e}\033[0m")
PYEOF
fi

IG_TOKEN=$(_get "INSTAGRAM_ACCESS_TOKEN")
IG_ID=$(_get "INSTAGRAM_BUSINESS_ID")
if [ -n "$IG_TOKEN" ] && [ -n "$IG_ID" ] && [ -f "$VENV_PY" ]; then
    info "Testeando Instagram API..."
    "$VENV_PY" - << PYEOF 2>/dev/null
import requests, os
from dotenv import load_dotenv
load_dotenv('.env')
token = os.getenv('INSTAGRAM_ACCESS_TOKEN','')
ig_id = os.getenv('INSTAGRAM_BUSINESS_ID','')
try:
    r = requests.get(f'https://graph.facebook.com/v21.0/{ig_id}',
        params={'fields':'id,username,name','access_token':token}, timeout=5)
    r.raise_for_status()
    d = r.json()
    print(f"  \033[0;32m✅  Instagram: @{d.get('username',d.get('id','?'))}\033[0m")
except Exception as e:
    print(f"  \033[0;31m❌  Instagram: {e}\033[0m")
PYEOF
fi

# ──────────────────────────────────────────────────────────────
# 10. Resumen
# ──────────────────────────────────────────────────────────────
echo ""
echo -e "${B}── Resumen ──────────────────────────────────────────────${RESET}"
echo ""

if [ "$ERRORS" -eq 0 ]; then
    echo -e "  ${G}✅  Setup completado sin errores${RESET}"
else
    echo -e "  ${Y}⚠️   Setup completado con $ERRORS advertencia(s)${RESET}"
    echo -e "  ${DIM}Revisá los mensajes ❌ de arriba antes de usar el pipeline${RESET}"
fi

echo ""
echo -e "  ${W}Comandos principales:${RESET}"
echo ""
echo -e "  ${C}# Activar entorno virtual${RESET}"
echo -e "  source venv/bin/activate"
echo ""
echo -e "  ${C}# Iniciar dashboard (CRM + Pipeline)${RESET}"
echo -e "  bash run.sh"
echo ""
echo -e "  ${C}# Iniciar WhatsApp bridge${RESET}"
echo -e "  node whatsapp_bridge/index.js"
echo ""
echo -e "  ${C}# Testear Social Media Agent${RESET}"
echo -e "  venv/bin/python modules/social_agent.py --test"
echo ""
echo -e "  ${C}# Generar un post de prueba (sin publicar)${RESET}"
echo -e "  venv/bin/python modules/social_agent.py --generate --nombre 'Tu Negocio' --categoria 'estetica' --tipo servicio"
echo ""
echo -e "  ${C}# Publicar en Instagram${RESET}"
echo -e "  venv/bin/python modules/social_agent.py --publish --nombre 'Tu Negocio' --categoria 'estetica'"
echo ""

# ── Token refresh reminder ─────────────────────────────────────
if [ -n "$IG_TOKEN" ]; then
    echo -e "  ${Y}⚠️   Recordatorio: el token de Instagram dura ~60 dias."
    echo -e "       Renovalo desde Meta for Developers antes de que expire.${RESET}"
    echo ""
fi

echo -e "  ${DIM}Documentacion: README.md${RESET}"
echo ""
