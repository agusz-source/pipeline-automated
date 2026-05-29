#!/bin/bash
cd ~/leadgen_rosario
source venv/bin/activate

echo "🚀 LEADGEN ROSARIO"
echo "1) Pipeline completo"
echo "2) Leer datasets"
echo "3) Analizar leads"
echo "4) Generar mensajes"
echo "5) Enviar mensajes"
echo "6) Registrar respondedores"
echo "7) Generar websites (Claude Code)"
echo "8) Desplegar (GitHub + Netlify)"
echo "9) Enviar links a clientes"
echo "10) Ver estado"
echo "11) Salir"
echo ""
read -p "Opción: " opt

case $opt in
    1) python main.py --full ;;
    2) python main.py --discover ;;
    3) python main.py --analyze ;;
    4) python main.py --generate-msgs ;;
    5) python main.py --send ;;
    6) python main.py --responders ;;
    7) python main.py --generate-webs ;;
    8) python main.py --deploy ;;
    9) python main.py --send-links ;;
    10) python main.py --status ;;
    11) exit 0 ;;
    *) echo "Opción inválida" ;;
esac
