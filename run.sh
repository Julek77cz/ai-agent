#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
#  JARVIS V19 - Launcher (run after installation)
#  Usage: ./run.sh [arguments]
# ═══════════════════════════════════════════════════════════════════════

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Activate virtual environment if exists
if [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
    source "$PROJECT_DIR/.venv/bin/activate"
fi

# Check for Ollama
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "[WARNING] Ollama is not running!"
    echo "Starting Ollama service..."
    nohup ollama serve > /dev/null 2>&1 &
    sleep 3
fi

# Run JARVIS
python jarvis_v19.py "$@"
