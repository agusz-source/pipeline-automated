#!/bin/bash

# Dynamic path resolution — works regardless of folder name
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Activate virtual env if exists
if [ -f "$PROJECT_DIR/venv/bin/activate" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
fi

DATASET="$PROJECT_DIR/dataset.json"
STATUS="$PROJECT_DIR/data/estado.csv"

echo ""
echo "========================================"
echo "  LeadGen Amoblamientos — Rosario"
echo "========================================"
echo "  1) Scraping (Apify → dataset.json)"
echo "  2) Discovery (leer dataset)"
echo "  3) Enviar mensajes (outreach)"
echo "  4) Generar websites"
echo "  5) Desplegar (Vercel)"
echo "  6) Enviar links a clientes"
echo "  7) Pipeline completo"
echo "  8) Estado del pipeline"
echo "  9) Dashboard web"
echo " 10) Receptor de respuestas WhatsApp"
echo " 11) Migrar estado.csv (agregar columnas)"
echo "  0) Salir"
echo ""
read -p "Opción: " opt

case $opt in
    1) python3 "$PROJECT_DIR/main.py" --scrape ;;
    2) python3 "$PROJECT_DIR/main.py" --discover "$DATASET" ;;
    3) python3 "$PROJECT_DIR/main.py" --send "$DATASET" "$STATUS" ;;
    4) python3 "$PROJECT_DIR/main.py" --generate-webs "$STATUS" ;;
    5) python3 "$PROJECT_DIR/main.py" --deploy "$STATUS" ;;
    6) python3 "$PROJECT_DIR/main.py" --send-links "$STATUS" ;;
    7) python3 "$PROJECT_DIR/main.py" --full "$DATASET" "$STATUS" ;;
    8) python3 "$PROJECT_DIR/main.py" --status "$STATUS" ;;
    9) python3 "$PROJECT_DIR/dashboard/app.py" ;;
   10) cd "$PROJECT_DIR/whatsapp_bridge" && node index.js ;;
   11) python3 "$PROJECT_DIR/main.py" --migrate "$STATUS" ;;
    0) exit 0 ;;
    *) echo "Opción inválida" ;;
esac
