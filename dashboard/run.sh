#!/bin/bash
# Binario Dashboard — Production launcher
# Usage: ./run.sh [port]

PORT="${1:-5000}"
DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$DIR/../venv/bin/python"
WATCHMEDO="$DIR/../venv/bin/watchmedo"
CLOUDFLARED=$(command -v cloudflared 2>/dev/null || echo "$HOME/.local/bin/cloudflared")

export PYTHONPATH="$DIR/.."

PIDS=()
trap 'kill "${PIDS[@]}" 2>/dev/null; exit' INT TERM

# Bridge WhatsApp
WA_BRIDGE_DIR="$DIR/../whatsapp_bridge"
if [ -f "$WA_BRIDGE_DIR/index.js" ]; then
    echo "Starting WhatsApp Bridge on port 3001..."
    node "$WA_BRIDGE_DIR/index.js" &
    PIDS+=($!)
else
    echo "⚠️  whatsapp_bridge/index.js no encontrado"
fi

# Cloudflare Tunnel
CF_LOG="/tmp/cloudflared-binario.log"
if [ -x "$CLOUDFLARED" ]; then
    echo "Starting Cloudflare Tunnel..."
    "$CLOUDFLARED" tunnel --url "http://localhost:$PORT" > "$CF_LOG" 2>&1 &
    PIDS+=($!)
    # Wait for URL, print it, and notify phone via ntfy.sh
    (
        # Load ntfy config from .env
        ENV_FILE="$DIR/../.env"
        NTFY_TOPIC=""
        NTFY_URL="https://ntfy.sh"
        if [ -f "$ENV_FILE" ]; then
            NTFY_TOPIC=$(grep -E '^NTFY_TOPIC=' "$ENV_FILE" | cut -d= -f2 | tr -d '[:space:]')
            _URL=$(grep -E '^NTFY_URL=' "$ENV_FILE" | cut -d= -f2 | tr -d '[:space:]')
            [ -n "$_URL" ] && NTFY_URL="$_URL"
        fi

        for i in $(seq 1 20); do
            sleep 1
            URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$CF_LOG" 2>/dev/null | head -1)
            if [ -n "$URL" ]; then
                echo ""
                echo "========================================="
                echo "  TUNNEL URL: $URL"
                echo "========================================="
                if [ -n "$NTFY_TOPIC" ]; then
                    curl -s -o /dev/null \
                        -d "$URL" \
                        -H "Title: Binario Dashboard activo" \
                        -H "Priority: high" \
                        -H "Tags: rocket,dashboard" \
                        -H "Click: $URL" \
                        -H "Actions: view, Abrir Dashboard, $URL" \
                        "$NTFY_URL/$NTFY_TOPIC" &
                fi
                break
            fi
        done
    ) &
    PIDS+=($!)
else
    echo "⚠️  cloudflared no encontrado — sin túnel"
fi

echo "Starting Binario Dashboard on port $PORT (auto-restart on .py changes)..."

export PYTHONWARNINGS="ignore::DeprecationWarning"

if [ -f "$WATCHMEDO" ]; then
    "$WATCHMEDO" auto-restart \
        --patterns="*.py" --recursive \
        --directory="$DIR/.." \
        -- "$VENV" -W ignore "$DIR/app.py"
else
    "$VENV" -W ignore "$DIR/app.py"
fi

kill "${PIDS[@]}" 2>/dev/null
