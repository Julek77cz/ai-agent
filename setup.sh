#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
#  JARVIS V19 - Universal Setup Installer (Linux/Mac)
#  Run: chmod +x setup.sh && ./setup.sh
# ═══════════════════════════════════════════════════════════════════════

set -e

# ─── Configuration ─────────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
PYTHON_MIN="3.10"
OLLAMA_URL="http://localhost:11434"

# Always include these models
BASE_MODELS=("nomic-embed-text" "jobautomation/OpenEuroLLM-Czech:latest")
SELECTED_MODEL=""

# ─── Colors ────────────────────────────────────────────────────────────
RED='\033[91m'
GREEN='\033[92m'
YELLOW='\033[93m'
BLUE='\033[94m'
CYAN='\033[96m'
RESET='\033[0m'
BOLD='\033[1m'

# ─── Helper Functions ──────────────────────────────────────────────────
log_info() { echo -e "${CYAN}$1${RESET}"; }
log_success() { echo -e "${GREEN}✓ $1${RESET}"; }
log_warn() { echo -e "${YELLOW}⚠ $1${RESET}"; }
log_error() { echo -e "${RED}✗ $1${RESET}"; }

detect_hardware() {
    local vram_gb=0
    local ram_gb=0
    local gpu_name="No GPU detected"

    # Detect VRAM using nvidia-smi
    if command -v nvidia-smi &> /dev/null; then
        local vram_mb=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)
        if [ -n "$vram_mb" ]; then
            vram_gb=$((vram_mb / 1024))
            gpu_name=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
        fi
    fi

    # Detect RAM
    if command -v free &> /dev/null; then
        ram_mb=$(free -m | awk '/^Mem:/ {print $2}')
        ram_gb=$((ram_mb / 1024))
    fi

    echo "$vram_gb|$ram_gb|$gpu_name"
}

recommend_models() {
    local vram_gb=$1

    if [ "$vram_gb" -lt 4 ]; then
        echo "qwen2.5:3b-instruct|Lightweight, fast (best for low VRAM)"
    elif [ "$vram_gb" -lt 6 ]; then
        echo "qwen2.5:7b-instruct|Good balance"
        echo "llama3.1:8b-instruct-q4_K_M|Better quality (quantized)"
    elif [ "$vram_gb" -lt 9 ]; then
        echo "llama3.1:8b-instruct-q4_K_M|RECOMMENDED - Best for 8GB VRAM"
        echo "llama3.1:8b-instruct-q5_K_M|Higher quality, slower"
        echo "qwen2.5:7b-instruct|Faster alternative"
        echo "gemma2:9b-instruct-q4_K_M|Good for reasoning"
    else
        echo "llama3.1:8b-instruct-q5_K_M|Fast and capable"
        echo "llama3.1:8b-instruct|Best quality 8B"
        echo "mistral-nemo:12b-instruct-q4_K_M|Higher quality 12B"
        echo "llama3.1:70b-instruct-q4_K_M|Best quality (slow, requires 8GB+)"
    fi
}

select_model() {
    local hardware_info=$1
    local vram_gb=$(echo "$hardware_info" | cut -d'|' -f1)
    local ram_gb=$(echo "$hardware_info" | cut -d'|' -f2)
    local gpu_name=$(echo "$hardware_info" | cut -d'|' -f3)

    echo
    log_info "======================================================================"
    log_info "Hardware Detection Results:"
    log_info "======================================================================"
    echo "  GPU:  $gpu_name"
    if [ "$vram_gb" -gt 0 ]; then
        echo "  VRAM: $vram_gb GB"
    else
        echo "  VRAM: Not detected (or no NVIDIA GPU)"
    fi
    if [ "$ram_gb" -gt 0 ]; then
        echo "  RAM:  $ram_gb GB"
    fi
    echo
    log_info "======================================================================"
    log_info "Recommended models for your system:"
    log_info "======================================================================"
    echo

    local recommendations=($(recommend_models $vram_gb))
    local index=1

    for rec in "${recommendations[@]}"; do
        local model=$(echo "$rec" | cut -d'|' -f1)
        local desc=$(echo "$rec" | cut -d'|' -f2-)

        echo "  [$index] $model"
        echo "      $desc"
        echo

        # Store recommendation
        RECOMMENDATIONS[$index]=$model
        index=$((index + 1))
    done

    local custom_choice=$index
    echo "  [$custom_choice] Custom - Enter your own model name"
    echo

    # Get user selection
    while true; do
        read -p "Select [1-$custom_choice]: " choice

        # Check if input is a number
        if [[ "$choice" =~ ^[0-9]+$ ]]; then
            if [ "$choice" -ge 1 ] && [ "$choice" -le "$custom_choice" ]; then
                if [ "$choice" -eq "$custom_choice" ]; then
                    # Custom model
                    while true; do
                        read -p "Enter model name (e.g., llama3.1:8b-instruct): " custom_model
                        if [ -n "$custom_model" ]; then
                            SELECTED_MODEL="$custom_model"
                            log_success "Selected: $custom_model"
                            return 0
                        fi
                        log_error "Please enter a model name"
                    done
                else
                    # Pre-selected model
                    SELECTED_MODEL="${RECOMMENDATIONS[$choice]}"
                    log_success "Selected: $SELECTED_MODEL"
                    return 0
                fi
            else
                log_error "Please enter a number between 1 and $custom_choice"
            fi
        else
            log_error "Please enter a valid number"
        fi
    done
}

update_user_config() {
    local model=$1
    local config_file="$PROJECT_DIR/jarvis_config/user_config.py"

    cat > "$config_file" << EOF
"""
User Configuration Override for JARVIS

This file was auto-generated by the setup script based on your
detected hardware and selected model preferences.

You can also edit this file manually to change model settings.
"""

def apply_user_config():
    """Apply user-selected model configuration."""
    import jarvis_config as _cfg

    # Override with user-selected models
    _cfg.MODELS["planner"] = "$model"
    _cfg.MODELS["verifier"] = "$model"
    _cfg.MODELS["reasoner"] = "$model"

    # Note: MODELS["czech_gateway"] should remain as jobautomation/OpenEuroLLM-Czech:latest
EOF

    if [ $? -eq 0 ]; then
        log_success "Configuration updated: $config_file"
        return 0
    else
        log_error "Failed to update configuration"
        return 1
    fi
}

print_banner() {
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║          🤖 JARVIS V19 - Universal Setup Installer            ║"
    echo "║                 Linux/Mac Edition                             ║"
    echo "╚═══════════════════════════════════════════════════════════════╝${RESET}"
    echo
}

check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        return 1
    fi
    
    local version=$($PYTHON_CMD -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    local major=$(echo $version | cut -d. -f1)
    local minor=$(echo $version | cut -d. -f2)
    
    if [ "$major" -ge "$PYTHON_MIN" ]; then
        return 0
    fi
    return 1
}

get_python_version() {
    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
}

check_ollama_running() {
    curl -s "$OLLAMA_URL/api/tags" > /dev/null 2>&1
}

wait_for_ollama() {
    log_info "Checking Ollama service..."
    for i in {1..30}; do
        if curl -s "$OLLAMA_URL/api/tags" > /dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
}

install_ollama_linux() {
    echo
    log_warn "════════════════════════════════════════════════════════════"
    log_warn "  Ollama is NOT installed. Installing..."
    log_warn "════════════════════════════════════════════════════════════"
    echo
    
    if command -v curl &> /dev/null; then
        log_info "Installing Ollama via official script..."
        curl -fsSL https://ollama.com/install.sh | sh
        
        if [ $? -eq 0 ]; then
            log_success "Ollama installed"
            
            # Start Ollama in background
            log_info "Starting Ollama service..."
            if command -v systemctl &> /dev/null; then
                sudo systemctl start ollama 2>/dev/null || ollama serve &
            else
                nohup ollama serve > /dev/null 2>&1 &
            fi
            
            sleep 3
            wait_for_ollama
            return $?
        else
            log_error "Failed to install Ollama"
            return 1
        fi
    else
        log_error "curl is not installed. Please install curl first."
        echo "  Ubuntu/Debian: sudo apt install curl"
        echo "  Fedora: sudo dnf install curl"
        echo "  macOS: brew install curl"
        return 1
    fi
}

install_ollama_macos() {
    echo
    log_warn "════════════════════════════════════════════════════════════"
    log_warn "  Ollama is NOT installed."
    log_warn "════════════════════════════════════════════════════════════"
    echo
    
    if command -v brew &> /dev/null; then
        log_info "Installing Ollama via Homebrew..."
        brew install ollama
        log_success "Ollama installed via Homebrew"
        
        # Start Ollama
        log_info "Starting Ollama service..."
        brew services start ollama 2>/dev/null || ollama serve &
        sleep 3
        wait_for_ollama
        return $?
    else
        log_error "Homebrew not found. Please install Ollama manually:"
        echo "  1. Download: https://ollama.com/download/mac"
        echo "  2. Or install Homebrew: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        echo "  3. Then: brew install ollama"
        return 1
    fi
}

install_dependencies() {
    log_info "Installing Python dependencies..."
    
    # Upgrade pip
    $PYTHON_CMD -m pip install --upgrade pip -q
    
    # Install requirements
    $PYTHON_CMD -m pip install -r "$PROJECT_DIR/requirements.txt" -q
    
    if [ $? -eq 0 ]; then
        log_success "Dependencies installed"
    else
        log_error "Failed to install dependencies"
        return 1
    fi
}

pull_model() {
    local model="$1"
    log_info "Downloading model: $model"
    log_info "  (This may take several minutes depending on size and connection)"
    
    if ollama pull "$model" 2>&1; then
        log_success "Model installed: $model"
    else
        log_error "Failed to install model: $model"
        return 1
    fi
}

create_data_dirs() {
    log_info "Creating JARVIS data directories..."
    
    mkdir -p "$PROJECT_DIR/jarvis_data/memory"
    mkdir -p "$PROJECT_DIR/jarvis_data/orchestrator"
    mkdir -p "$PROJECT_DIR/jarvis_data/chromadb"
    mkdir -p "$PROJECT_DIR/jarvis_data/knowledge_graph"
    mkdir -p "$PROJECT_DIR/jarvis_data/wal"
    mkdir -p "$PROJECT_DIR/jarvis_data/procedural"
    
    log_success "Directories created"
}

test_jarvis() {
    log_info "Testing JARVIS installation..."
    
    if $PYTHON_CMD "$PROJECT_DIR/jarvis_v19.py" --help > /dev/null 2>&1; then
        log_success "JARVIS is ready!"
        return 0
    else
        log_error "JARVIS test failed"
        return 1
    fi
}

# ─── Main Installation Flow ───────────────────────────────────────────
main() {
    print_banner

    # ─── Step 1: Check Python ─────────────────────────────────────────
    log_info "[1/7] Checking Python installation..."

    if ! check_python; then
        log_error "Python 3.10+ not found!"
        echo
        echo "Please install Python 3.10 or higher:"
        echo "  Ubuntu/Debian: sudo apt install python3 python3-pip"
        echo "  Fedora: sudo dnf install python3 python3-pip"
        echo "  macOS: brew install python3"
        echo "  Windows: Download from https://www.python.org/downloads/"
        echo
        exit 1
    fi

    get_python_version
    log_success "Python $PYTHON_VERSION found"

    # ─── Step 2: Create Virtual Environment ───────────────────────────
    log_info "[2/7] Setting up virtual environment..."

    if [ -d "$VENV_DIR" ]; then
        log_info "Virtual environment already exists"
    else
        $PYTHON_CMD -m venv "$VENV_DIR"
        log_success "Virtual environment created"
    fi

    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    PYTHON_CMD="python"

    # ─── Step 3: Install Dependencies ─────────────────────────────────
    log_info "[3/7] Installing Python dependencies..."

    install_dependencies

    # ─── Step 4: Check/Install Ollama ─────────────────────────────────
    log_info "[4/7] Checking Ollama..."

    if ! check_ollama_running; then
        # Ollama not running - check if installed
        if ! command -v ollama &> /dev/null; then
            # Not installed - try to install
            if [[ "$OSTYPE" == "darwin"* ]]; then
                install_ollama_macos || exit 1
            else
                install_ollama_linux || exit 1
            fi
        else
            # Installed but not running - start it
            log_warn "Ollama is installed but not running. Starting service..."
            nohup ollama serve > /dev/null 2>&1 &
            sleep 3
            wait_for_ollama || {
                log_error "Ollama failed to start"
                exit 1
            }
        fi
    fi

    log_success "Ollama is running"

    # ─── Step 5: Detect Hardware and Select Model ─────────────────────
    log_info "[5/7] Detecting hardware and selecting model..."

    hardware_info=$(detect_hardware)
    select_model "$hardware_info"

    # ─── Step 6: Pull Required Models ─────────────────────────────────
    log_info "[6/7] Downloading LLM models..."
    echo
    echo -e "${YELLOW}  Model sizes (approximate):${RESET}"
    echo "  - nomic-embed-text:       ~274 MB"
    echo "  - OpenEuroLLM-Czech:      ~4-5 GB"
    echo "  - $SELECTED_MODEL:      ~2-10 GB (varies by model)"
    echo
    echo -e "${YELLOW}  This will take a while depending on your internet speed...${RESET}"
    echo

    # Pull base models
    for model in "${BASE_MODELS[@]}"; do
        pull_model "$model" || {
            log_error "Failed to pull model: $model"
            exit 1
        }
        echo
    done

    # Pull selected model
    pull_model "$SELECTED_MODEL" || {
        log_error "Failed to pull model: $SELECTED_MODEL"
        exit 1
    }
    echo

    # Update user configuration
    update_user_config "$SELECTED_MODEL" || {
        log_warn "Failed to update configuration. You may need to edit jarvis_config/user_config.py manually"
    }

    # ─── Step 7: Create Data Directories ───────────────────────────────
    log_info "[7/7] Creating data directories..."
    create_data_dirs

    # ─── Final: Summary ────────────────────────────────────────────────
    echo
    log_success "════════════════════════════════════════════════════════════"
    log_success "  🎉 INSTALLATION COMPLETE!"
    log_success "════════════════════════════════════════════════════════════"
    echo
    echo "  Configuration:"
    echo "  - Selected model: $SELECTED_MODEL"
    echo "  - Czech gateway:  OpenEuroLLM-Czech:latest"
    echo
    echo "  Next steps:"
    echo "  1. Run: ./run.sh"
    echo "  2. Or:  source .venv/bin/activate && python jarvis_v19.py"
    echo
    echo "  First run will initialize the vector database..."
    echo

    # Make run.sh executable
    chmod +x "$PROJECT_DIR/run.sh" 2>/dev/null || true

    exit 0
}

# Run main
main "$@"
