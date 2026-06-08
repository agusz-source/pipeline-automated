#!/bin/bash

# Ruta fija al proyecto
PROJECT_DIR="/home/aguszz/pipeline-automated"
cd "$PROJECT_DIR"

# Activar virtual env si existe
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

DATASET="dataset.json"
STATUS="data/estado.csv"

echo "🚀 LEADGEN ROSARIO"
echo "1) Discovery (leer dataset)"
echo "2) Enviar mensajes (outreach)"
echo "3) Generar websites"
echo "4) Desplegar (GitHub + Netlify)"
echo "5) Enviar links a clientes"
echo "6) Pipeline completo"
echo "7) Ver estado"
echo "8) Salir"
echo ""
read -p "Opción: " opt

case $opt in
    1) python3 "$PROJECT_DIR/main.py" --discover "$DATASET" ;;
    2) python3 "$PROJECT_DIR/main.py" --send "$DATASET" "$STATUS" ;;
    3) python3 "$PROJECT_DIR/main.py" --generate-webs "$STATUS" ;;
    4) python3 "$PROJECT_DIR/main.py" --deploy "$STATUS" ;;
    5) python3 "$PROJECT_DIR/main.py" --send-links "$STATUS" ;;
    6) python3 "$PROJECT_DIR/main.py" --full "$DATASET" "$STATUS" ;;
    7) python3 "$PROJECT_DIR/main.py" --status "$STATUS" ;;
    8) exit 0 ;;
    *) echo "Opción inválida" ;;
esac