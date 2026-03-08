#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
#  JARVIS Universal Launcher - Version Switcher
#  Supports V19 and V20
#  Usage: ./run.sh [arguments]
# ═══════════════════════════════════════════════════════════════════════

# DETEKCE VERZE (zmente zde pro prepinani)
export JARVIS_VERSION=${JARVIS_VERSION:-20}

# PRECTETE ZDE PRO PREPINANI VERZE
# 20 = JARVIS V20 (nejnovější, SOTA)
# 19 = JARVIS V19 (historicka, pro zpetnou kompatibilitu)

if [ "$JARVIS_VERSION" = "20" ]; then
    JARVIS_DIR="jarvis_v20"
    PYTHON_FILE="jarvis_v20.py"
    TITLE="JARVIS V20 - State-of-the-Art AI Agent"
else
    JARVIS_DIR="jarvis_v19"
    PYTHON_FILE="jarvis_v19.py"
    TITLE="JARVIS V19 - AI Assistant"
fi

# Banner
echo ""
echo "╔═══════════════════════════════════════════════════╗"
echo "║                                                               ║"
echo "║         $TITLE         ║"
echo "║                                                               ║"
echo "╚═════════════════════════════════════════════════════════╝"
echo ""

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# 1. Auto-update
echo "[*] Kontroluji aktualizace z GitHubu..."
git pull || echo "[!] Problem se stazenim, pokracuji s lokalni verzi."
echo ""

# 2. Kontrola Pythonu
if ! command -v python &>/dev/null; then
    echo "[ERROR] Python neni nainstalovan!"
    exit 1
fi

# 3. Vyber verze (promenna JARVIS_VERSION)
if [ "$JARVIS_VERSION" = "20" ]; then
    echo "[*] JARVIS V20 aktivovana - nejnovější verze"
    REQUIREMENTS="requirements_v20.txt"
else
    echo "[*] JARVIS V19 aktivovana - historicka verze"
    REQUIREMENTS="requirements_v19.txt"
fi

# 4. Aktivace venv
if [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
    echo "[*] Aktivuji virtualni prostredi..."
    source "$PROJECT_DIR/.venv/bin/activate"
    
    echo "[*] Kontroluji zavislosti..."
    python -m pip install -r $REQUIREMENTS -q
else
    echo "[!] Virtualni prostredi nalezeno!"
    exit 1
fi
echo ""

# 5. Kontrola Ollamy
if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "[WARNING] Ollama neběží!"
    echo "[*] Startuji Ollamu na pozadi..."
    nohup ollama serve >/dev/null 2>&1 &
    sleep 5
else
    echo "[OK] Ollama je pripravena."
fi

echo ""
echo "[*] Startuji $JARVIS_VERSION..."
echo "══════════════════════════════════════════════════════════"
echo ""

python start.py "$@"

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "[ERROR] JARVIS $JARVIS_VERSION selhal s kodem $EXIT_CODE"
    echo ""
    echo "💡 Možné řešení:"
    echo "   - Zkontrolujte, zda běží Ollama: ollama serve"
    echo "   - Zkontrolujte modely: ollama list"
    echo "   - Přepněte verzi (export JARVIS_VERSION=19)"
    echo "   - Zapněte debug mód: python start.py --debug"
    echo ""
fi

exit $EXIT_CODE
