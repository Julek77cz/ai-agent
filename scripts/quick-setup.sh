#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
#  Quick Setup - One-command installer for Linux/macOS
#  Run: curl -sSL https://raw.githubusercontent.com/your-repo/main/setup-quick.sh | bash
#  Or download and run: chmod +x quick-setup.sh && ./quick-setup.sh
# ═══════════════════════════════════════════════════════════════════════

set -e

RED='\033[91m'
GREEN='\033[92m'
YELLOW='\033[93m'
CYAN='\033[96m'
RESET='\033[0m'

log_info() { echo -e "${CYAN}$1${RESET}"; }
log_success() { echo -e "${GREEN}✓ $1${RESET}"; }
log_error() { echo -e "${RED}✗ $1${RESET}"; }

echo -e "${CYAN}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║            🤖 JARVIS V19 - Quick Setup Installer              ║"
echo "╚═══════════════════════════════════════════════════════════════╝${RESET}"
echo

# Check Python
if ! command -v python3 &> /dev/null; then
    log_error "Python 3 not found. Installing..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
    elif command -v brew &> /dev/null; then
        brew install python3
    else
        log_error "Please install Python 3.10+ manually"
        exit 1
    fi
fi

log_info "Python version: $(python3 --version)"

# Create venv
log_info "Creating virtual environment..."
python3 -m venv .venv

# Activate
source .venv/bin/activate

# Install deps
log_info "Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

log_success "Dependencies installed"

# Check Ollama
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    log_info "Installing Ollama..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &> /dev/null; then
            brew install ollama
            brew services start ollama
        else
            log_error "Install Ollama from https://ollama.com/download/mac"
            exit 1
        fi
    else
        curl -fsSL https://ollama.com/install.sh | sh
    fi
    sleep 5
fi

log_success "Ollama ready"

# Pull models
MODELS=("nomic-embed-text" "jobautomation/OpenEuroLLM-Czech:latest" "qwen2.5:3b-instruct")
for model in "${MODELS[@]}"; do
    log_info "Pulling $model..."
    ollama pull "$model"
done

# Create data dirs
mkdir -p jarvis_data/{memory,orchestrator,chromadb,knowledge_graph,wal,procedural}

log_success "Setup complete! Run: ./run.sh"
