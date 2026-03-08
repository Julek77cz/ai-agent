#!/bin/bash
# JARVIS V20 - State-of-the-Art AI Agent Launcher
# ══════════════════════════════════════════════════════════
#  🤖 JARVIS V20 - STATE-OF-THE-ART AI AGENT
# ══════════════════════════════════════════════════════════

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                                                               ║"
echo "║         🤖 JARVIS V20 - STATE-OF-THE-ART AI AGENT         ║"
echo "║                                                               ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# 1. Auto-update
echo "[*] Kontroluji aktualizace z GitHubu..."
git pull || echo "[!] Problem se stazením, pokračuji s lokální verzí."
echo ""

# 2. Kontrola Pythonu
if ! command -v python &>/dev/null; then
    echo "[ERROR] Python není nainstalován!"
    exit 1
fi

# 3. Aktivace venv
if [ -f ".venv/bin/activate" ]; then
    echo "[*] Aktivuji virtualni prostredi..."
    source ".venv/bin/activate"

    echo "[*] Kontroluji zavislosti..."
    python -m pip install -r requirements.txt -q
else
    echo "[!] Virtuální prostředí nenalezeno!"
    exit 1
fi
echo ""

# 4. Kontrola Ollamy
if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    echo "[WARNING] Ollama neběží!"
    echo "[*] Startuji Ollamu na pozadi..."
    ollama serve &
    sleep 5
else
    echo "[OK] Ollama je připravena."
fi

echo ""
echo "[*] Startuji JARVIS V20 State-of-the-Art..."
echo "════════════════════════════════════════════════════════════════"
echo ""

python jarvis_v20.py "$@"

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "[ERROR] JARVIS V20 selhal s kódem $EXIT_CODE"
    echo ""
    echo "💡 Možné řešení:"
    echo "   - Zkontrolujte, zda běží Ollama: ollama serve"
    echo "   - Zkontrolujte modely: ollama list"
    echo "   - Zapněte debug mód: python jarvis_v20.py --debug"
    echo ""
fi

exit $EXIT_CODE
