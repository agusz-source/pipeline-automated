#!/bin/bash
set -e

cd ~/leadgen_rosario

echo "🚀 Instalando LeadGen Rosario..."

# Dependencias del sistema
sudo pacman -S python python-pip nodejs npm git --noconfirm

# GitHub CLI
if ! command -v gh &> /dev/null; then
    yay -S github-cli --noconfirm
fi

# Netlify CLI
if ! command -v netlify &> /dev/null; then
   npm install -g netlify-cli
fi

# Entorno virtual
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Crear directorios
mkdir -p data logs templates websites

echo ""
echo "✅ Instalación completa"
echo ""
echo "Próximos pasos:"
echo "1. Completar .env con tus API keys"
echo "2. gh auth login"
echo "3. netlify login"
echo "4. export ANTHROPIC_API_KEY='tu_key'"
echo "5. ./run.sh"
