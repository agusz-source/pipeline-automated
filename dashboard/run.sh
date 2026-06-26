#!/bin/bash
# Binario Dashboard — Production launcher
# Usage: ./run.sh [port]

PORT="${1:-5000}"
DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$DIR/../venv/bin/python"

export PYTHONPATH="$DIR/.."

echo "Starting Binario Dashboard on port $PORT..."
exec "$VENV" "$DIR/app.py"
