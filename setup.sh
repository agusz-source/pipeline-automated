#!/usr/bin/env bash
# ── LeadGen Amoblamientos Rosario — Setup ──────────────────────────────────────
# Installs all dependencies, initialises data directories, and runs health checks.
# Works regardless of the folder name the repo lives in.

set -e
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
RESET='\033[0m'

ok()   { echo -e "  ${GREEN}✅ $*${RESET}"; }
warn() { echo -e "  ${YELLOW}⚠️  $*${RESET}"; }
fail() { echo -e "  ${RED}❌ $*${RESET}"; }
info() { echo -e "  ${CYAN}→  $*${RESET}"; }

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════╗"
echo -e "║  LeadGen Amoblamientos Rosario — Setup           ║"
echo -e "╚══════════════════════════════════════════════════╝${RESET}"
echo -e "  Directorio: $PROJECT_DIR"
echo ""

ERRORS=0

# ── 1. Python 3.10+ ───────────────────────────────────────────────────────────
echo "── Python ──────────────────────────────────────────────"
PYTHON=python3
if ! command -v "$PYTHON" &>/dev/null; then
    fail "python3 no encontrado — instalá Python 3.10+"
    ERRORS=$((ERRORS+1))
else
    PY_VERSION=$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
        fail "Python $PY_VERSION detectado — se requiere 3.10+"
        ERRORS=$((ERRORS+1))
    else
        ok "Python $PY_VERSION"
    fi
fi

# ── 2. Virtual environment ─────────────────────────────────────────────────────
echo ""
echo "── Entorno virtual (venv) ──────────────────────────────"
if [ -d "$PROJECT_DIR/venv" ]; then
    ok "venv ya existe"
else
    info "Creando venv..."
    "$PYTHON" -m venv "$PROJECT_DIR/venv"
    ok "venv creado"
fi

VENV_PY="$PROJECT_DIR/venv/bin/python"
VENV_PIP="$PROJECT_DIR/venv/bin/pip"

if [ ! -f "$VENV_PY" ]; then
    fail "No se encontró el ejecutable de Python en venv"
    ERRORS=$((ERRORS+1))
else
    info "Actualizando pip..."
    "$VENV_PIP" install --upgrade pip --quiet
    ok "pip actualizado"

    if [ -f "$PROJECT_DIR/requirements.txt" ]; then
        info "Instalando dependencias Python..."
        "$VENV_PIP" install -r "$PROJECT_DIR/requirements.txt" --quiet
        ok "requirements.txt instalado"
    else
        warn "requirements.txt no encontrado — saltando"
    fi
fi

# ── 3. Node.js ─────────────────────────────────────────────────────────────────
echo ""
echo "── Node.js ─────────────────────────────────────────────"
if ! command -v node &>/dev/null; then
    fail "node no encontrado — instalá Node.js 18+ desde https://nodejs.org"
    ERRORS=$((ERRORS+1))
else
    NODE_VERSION=$(node -e "process.stdout.write(process.version)")
    NODE_MAJOR=$(echo "$NODE_VERSION" | tr -d 'v' | cut -d. -f1)
    if [ "$NODE_MAJOR" -lt 18 ]; then
        warn "Node $NODE_VERSION — se recomienda 18+; el bridge puede fallar"
    else
        ok "Node $NODE_VERSION"
    fi

    WA_BRIDGE="$PROJECT_DIR/whatsapp_bridge"
    if [ -d "$WA_BRIDGE" ]; then
        info "Instalando dependencias Node (whatsapp_bridge/)..."
        (cd "$WA_BRIDGE" && npm install --silent 2>&1)
        ok "npm install completado"
    else
        warn "whatsapp_bridge/ no encontrado — saltando npm install"
    fi
fi

# ── 4. Apify CLI ───────────────────────────────────────────────────────────────
echo ""
echo "── Apify CLI ───────────────────────────────────────────"
if command -v apify &>/dev/null; then
    APIFY_VERSION=$(apify --version 2>/dev/null || echo "desconocida")
    ok "apify CLI $APIFY_VERSION"
else
    info "Instalando Apify CLI..."
    if npm install -g apify-cli --silent 2>/dev/null; then
        ok "apify CLI instalado"
    else
        warn "No se pudo instalar apify CLI — el scraper usará la API REST"
    fi
fi

# ── 5. Playwright (para whatsplay) ────────────────────────────────────────────
echo ""
echo "── Playwright ──────────────────────────────────────────"
if "$VENV_PY" -c "import playwright" 2>/dev/null; then
    info "Instalando navegadores Playwright..."
    "$VENV_PY" -m playwright install chromium --quiet 2>/dev/null && ok "Playwright chromium listo" || warn "playwright install falló — outreach puede no funcionar"
else
    warn "playwright no instalado en venv — saltando"
fi

# ── 6. Directorios y archivos base ────────────────────────────────────────────
echo ""
echo "── Directorios ─────────────────────────────────────────"
for dir in data logs websites templates; do
    if [ ! -d "$PROJECT_DIR/$dir" ]; then
        mkdir -p "$PROJECT_DIR/$dir"
        ok "Creado: $dir/"
    else
        ok "OK: $dir/"
    fi
done

# JSON files that must exist (non-destructive)
init_json() {
    local path="$1"
    local content="$2"
    if [ ! -f "$path" ]; then
        echo "$content" > "$path"
        ok "Inicializado: $(basename $path)"
    else
        ok "Existe: $(basename $path)"
    fi
}

init_json "$PROJECT_DIR/data/finanzas.json"       '{"pagos":[],"config":{"precio_sugerido":50000,"moneda_default":"ARS"}}'
init_json "$PROJECT_DIR/data/conversaciones.json" '{}'
init_json "$PROJECT_DIR/data/blacklist.json"       '[]'
init_json "$PROJECT_DIR/data/interesados.json"    '[]'

# estado.csv — append-only, never overwrite if exists
if [ ! -f "$PROJECT_DIR/data/estado.csv" ]; then
    echo "lead_id,nombre,telefono,categoria,direccion,puntaje,resenas,score,filter_reason,enviado,fecha_envio,estado_respuesta,fecha_respuesta,project_path,live_url,enviado_links,fecha_envio_links,fecha_entrega,fecha_renovacion_web,fecha_renovacion_hosting,fecha_renovacion_mantenimiento,notas" \
        > "$PROJECT_DIR/data/estado.csv"
    ok "Creado: estado.csv (vacío)"
else
    ok "Existe: estado.csv — NO se sobreescribe"
fi

# ── 7. .env ────────────────────────────────────────────────────────────────────
echo ""
echo "── Variables de entorno ────────────────────────────────"
if [ ! -f "$PROJECT_DIR/.env" ]; then
    if [ -f "$PROJECT_DIR/.env.example" ]; then
        cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
        warn ".env creado desde .env.example — editá tus claves antes de usar"
    else
        warn ".env no encontrado — creando plantilla mínima..."
        cat > "$PROJECT_DIR/.env" << 'DOTENV'
ANTHROPIC_API_KEY=
APIFY_TOKEN=
APIFY_ACTOR_ID=compass/google-maps-scraper
GITHUB_USERNAME=
WA_BRIDGE_PORT=3001
WA_EVENTS_PORT=3002
DOTENV
        warn ".env creado — completá ANTHROPIC_API_KEY y APIFY_TOKEN"
    fi
else
    ok ".env existe"
fi

# Validate required keys
MISSING_KEYS=()
check_env_key() {
    local key="$1"
    local val
    val=$(grep -E "^${key}=" "$PROJECT_DIR/.env" 2>/dev/null | cut -d= -f2-)
    if [ -z "$val" ]; then
        MISSING_KEYS+=("$key")
    fi
}

check_env_key "ANTHROPIC_API_KEY"
check_env_key "APIFY_TOKEN"

if [ ${#MISSING_KEYS[@]} -gt 0 ]; then
    warn "Claves vacías en .env: ${MISSING_KEYS[*]}"
    warn "Editá .env antes de usar el pipeline"
fi

# ── 8. Migrar estado.csv si tiene columnas faltantes ─────────────────────────
echo ""
echo "── Migración de schema ─────────────────────────────────"
if [ -f "$PROJECT_DIR/data/estado.csv" ] && [ -f "$VENV_PY" ]; then
    "$VENV_PY" - << 'PYEOF'
import csv, sys
from pathlib import Path

FIELDNAMES = [
    "lead_id","nombre","telefono","categoria","direccion","puntaje","resenas",
    "score","filter_reason","enviado","fecha_envio","estado_respuesta",
    "fecha_respuesta","project_path","live_url","enviado_links","fecha_envio_links",
    "fecha_entrega","fecha_renovacion_web","fecha_renovacion_hosting",
    "fecha_renovacion_mantenimiento","notas",
]

sf = Path("data/estado.csv")
with open(sf, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    existing = reader.fieldnames or []
    rows = list(reader)

missing = [c for c in FIELDNAMES if c not in existing]
if not missing:
    print("  schema OK — no se requieren cambios")
    sys.exit(0)

for row in rows:
    for col in missing:
        row.setdefault(col, "")

with open(sf, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

print(f"  {len(missing)} columnas añadidas: {', '.join(missing)}")
print(f"  {len(rows)} filas migradas")
PYEOF
    ok "estado.csv OK"
fi

# ── 9. Verificar imports Python ───────────────────────────────────────────────
echo ""
echo "── Health checks ───────────────────────────────────────"
if [ -f "$VENV_PY" ]; then
    "$VENV_PY" - << 'PYEOF' 2>&1
import importlib, sys
mods = ["flask", "anthropic", "requests", "dotenv", "colorama"]
all_ok = True
for m in mods:
    try:
        importlib.import_module(m)
        print(f"  \033[0;32m✅ {m}\033[0m")
    except ImportError:
        print(f"  \033[0;31m❌ {m} — no instalado\033[0m")
        all_ok = False
sys.exit(0 if all_ok else 1)
PYEOF
    IMPORT_STATUS=$?
    if [ "$IMPORT_STATUS" -ne 0 ]; then
        warn "Algunos módulos Python no están instalados — revisá requirements.txt"
        ERRORS=$((ERRORS+1))
    fi
fi

# ── 10. Node bridge syntax check ──────────────────────────────────────────────
if [ -f "$PROJECT_DIR/whatsapp_bridge/index.js" ]; then
    if node --check "$PROJECT_DIR/whatsapp_bridge/index.js" 2>/dev/null; then
        ok "whatsapp_bridge/index.js — sintaxis OK"
    else
        warn "whatsapp_bridge/index.js — error de sintaxis"
        ERRORS=$((ERRORS+1))
    fi
fi

# ── 11. Path integrity check ──────────────────────────────────────────────────
if [ -f "$PROJECT_DIR/data/estado.csv" ] && [ -f "$VENV_PY" ]; then
    BROKEN=$("$VENV_PY" - << 'PYEOF'
import csv
from pathlib import Path
sf = Path("data/estado.csv")
count = 0
with open(sf, "r", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        pp = row.get("project_path","")
        if pp and not Path(pp).exists():
            count += 1
print(count)
PYEOF
)
    if [ "$BROKEN" -gt 0 ]; then
        warn "$BROKEN project_path roto(s) en estado.csv — sitios movidos o no generados"
    else
        ok "project_path integridad OK"
    fi
fi

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "── Resumen ─────────────────────────────────────────────"
if [ "$ERRORS" -eq 0 ]; then
    echo -e "${GREEN}✅ Setup completado sin errores${RESET}"
    echo ""
    echo -e "  Activar entorno:  ${CYAN}source venv/bin/activate${RESET}"
    echo -e "  Ver pipeline:     ${CYAN}python3 main.py --status data/estado.csv${RESET}"
    echo -e "  Dashboard:        ${CYAN}python3 -m flask --app dashboard/app.py run${RESET}"
    echo -e "  WA Bridge:        ${CYAN}node whatsapp_bridge/index.js${RESET}"
    echo -e "  Opciones run.sh:  ${CYAN}bash run.sh${RESET}"
else
    echo -e "${YELLOW}⚠️  Setup completado con $ERRORS advertencia(s)${RESET}"
    echo -e "  Revisá los mensajes ${RED}❌${RESET} de arriba antes de usar el pipeline."
fi
echo ""
