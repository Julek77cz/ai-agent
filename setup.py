#!/usr/bin/env python3
"""
JARVIS V19 - Cross-Platform Python Installer
Run: python setup.py

Supports: Windows, Linux, macOS
"""
import sys
import os
import subprocess
import shutil
import urllib.request
import json
import platform
from pathlib import Path

# Configuration
PROJECT_DIR = Path(__file__).parent.resolve()
VENV_DIR = PROJECT_DIR / ".venv"
OLLAMA_URL = "http://localhost:11434"

# Always include these models
BASE_MODELS = [
    "nomic-embed-text",
    "jobautomation/OpenEuroLLM-Czech:latest"
]

# Colors (ANSI)
class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"

def log_info(msg):
    print(f"{Colors.CYAN}{msg}{Colors.RESET}")

def log_success(msg):
    print(f"{Colors.GREEN}✓ {msg}{Colors.RESET}")

def log_warn(msg):
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.RESET}")

def log_error(msg):
    print(f"{Colors.RED}✗ {msg}{Colors.RESET}")

def detect_hardware():
    """Detect GPU VRAM and system RAM."""
    hardware_info = {
        "vram_gb": 0,
        "ram_gb": 0,
        "cpu_name": "Unknown CPU",
        "gpu_name": "No GPU detected"
    }

    # Detect VRAM using nvidia-smi
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            vram_mb = int(result.stdout.strip().split()[0])
            hardware_info["vram_gb"] = vram_mb // 1024

            # Try to get GPU name
            try:
                name_result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if name_result.returncode == 0:
                    hardware_info["gpu_name"] = name_result.stdout.strip()
            except:
                pass
    except:
        pass

    # Detect RAM
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["wmic", "OS", "get", "TotalVisibleMemorySize", "/value"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        if key.strip() == 'TotalVisibleMemorySize':
                            ram_kb = int(value.strip())
                            hardware_info["ram_gb"] = ram_kb // (1024 * 1024)
                            break
        else:
            result = subprocess.run(
                ["free", "-m"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if line.startswith('Mem:'):
                        parts = line.split()
                        if len(parts) >= 2:
                            hardware_info["ram_gb"] = int(parts[1]) // 1024
                            break
    except:
        pass

    return hardware_info

def recommend_models(vram_gb):
    """Get model recommendations based on VRAM."""
    if vram_gb < 4:
        return [
            ("qwen2.5:3b-instruct", "Lightweight, fast (best for low VRAM)"),
        ]
    elif vram_gb < 6:
        return [
            ("qwen2.5:7b-instruct", "Good balance"),
            ("llama3.1:8b-instruct-q4_K_M", "Better quality (quantized)"),
        ]
    elif vram_gb < 9:
        return [
            ("llama3.1:8b-instruct-q4_K_M", "RECOMMENDED - Best for 8GB VRAM"),
            ("llama3.1:8b-instruct-q5_K_M", "Higher quality, slower"),
            ("qwen2.5:7b-instruct", "Faster alternative"),
            ("gemma2:9b-instruct-q4_K_M", "Good for reasoning"),
        ]
    else:
        return [
            ("llama3.1:8b-instruct-q5_K_M", "Fast and capable"),
            ("llama3.1:8b-instruct", "Best quality 8B"),
            ("mistral-nemo:12b-instruct-q4_K_M", "Higher quality 12B"),
            ("llama3.1:70b-instruct-q4_K_M", "Best quality (slow, requires 8GB+)"),
        ]

def select_model(hardware_info):
    """Interactive model selection."""
    print()
    log_info("=" * 70)
    log_info("Hardware Detection Results:")
    log_info("=" * 70)
    print(f"  GPU:  {hardware_info['gpu_name']}")
    if hardware_info['vram_gb'] > 0:
        print(f"  VRAM: {hardware_info['vram_gb']} GB")
    else:
        print(f"  VRAM: Not detected (or no NVIDIA GPU)")
    if hardware_info['ram_gb'] > 0:
        print(f"  RAM:  {hardware_info['ram_gb']} GB")
    print()
    log_info("=" * 70)
    log_info("Recommended models for your system:")
    log_info("=" * 70)
    print()

    # Get recommendations
    recommendations = recommend_models(hardware_info['vram_gb'])

    # Display options
    for i, (model, desc) in enumerate(recommendations, 1):
        print(f"  [{i}] {model}")
        print(f"      {desc}")
        print()

    print(f"  [{len(recommendations) + 1}] Custom - Enter your own model name")
    print()

    # Get user selection
    while True:
        try:
            choice = input(f"Select [{1}-{len(recommendations) + 1}]: ").strip()
            choice_num = int(choice)

            if 1 <= choice_num <= len(recommendations):
                selected_model = recommendations[choice_num - 1][0]
                log_success(f"Selected: {selected_model}")
                return selected_model
            elif choice_num == len(recommendations) + 1:
                while True:
                    custom_model = input("Enter model name (e.g., llama3.1:8b-instruct): ").strip()
                    if custom_model:
                        log_success(f"Selected: {custom_model}")
                        return custom_model
                    log_error("Please enter a model name")
            else:
                log_error(f"Please enter a number between 1 and {len(recommendations) + 1}")
        except ValueError:
            log_error("Please enter a valid number")
        except KeyboardInterrupt:
            log_error("\nSetup cancelled")
            sys.exit(1)

def update_user_config(model):
    """Update user_config.py with selected model."""
    config_path = PROJECT_DIR / "jarvis_config" / "user_config.py"

    config_content = f'''"""
User Configuration Override for JARVIS

This file was auto-generated by the setup script based on your
detected hardware and selected model preferences.

You can also edit this file manually to change model settings.
"""

def apply_user_config():
    """Apply user-selected model configuration."""
    import jarvis_config as _cfg

    # Override with user-selected models
    _cfg.MODELS["planner"] = "{model}"
    _cfg.MODELS["verifier"] = "{model}"
    _cfg.MODELS["reasoner"] = "{model}"

    # Note: MODELS["czech_gateway"] should remain as jobautomation/OpenEuroLLM-Czech:latest
'''

    try:
        with open(config_path, 'w') as f:
            f.write(config_content)
        log_success(f"Configuration updated: {config_path}")
        return True
    except Exception as e:
        log_error(f"Failed to update configuration: {e}")
        return False

def run_cmd(cmd, check=True, capture=True, shell=False):
    """Run a command and return result."""
    try:
        if isinstance(cmd, str):
            if shell:
                result = subprocess.run(cmd, shell=True, capture_output=capture, text=True)
            else:
                result = subprocess.run(cmd.split(), capture_output=capture, text=True)
        else:
            result = subprocess.run(cmd, capture_output=capture, text=True)

        if check and result.returncode != 0:
            if result.stderr:
                log_error(f"Command failed: {result.stderr.strip()}")
            return False, result
        return True, result
    except FileNotFoundError:
        return False, None
    except Exception as e:
        return False, None

def is_ollama_running():
    """Check if Ollama is running."""
    try:
        import requests
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        return resp.status_code == 200
    except:
        return False

def install_ollama():
    """Install Ollama based on OS."""
    system = sys.platform
    
    log_warn("Ollama is not installed. Installing...")
    
    if system == "win32":
        log_info("For Windows:")
        log_info("  1. Download: https://ollama.com/download/windows")
        log_info("  2. Run OllamaSetup.exe")
        log_info("  3. Restart this script")
        log_info("\nOr use winget: winget install Ollama.Ollama")
        return False
    
    elif system == "darwin":
        # macOS
        if shutil.which("brew"):
            log_info("Installing Ollama via Homebrew...")
            run_cmd(["brew", "install", "ollama"], check=False)
            run_cmd(["brew", "services", "start", "ollama"], check=False)
            return True
        else:
            log_info("For macOS:")
            log_info("  1. Download: https://ollama.com/download/mac")
            log_info("  2. Install the .app")
            return False
    
    else:
        # Linux
        if shutil.which("curl"):
            log_info("Installing Ollama via official script...")
            script = """
            curl -fsSL https://ollama.com/install.sh | sh
            """
            success, _ = run_cmd("curl -fsSL https://ollama.com/install.sh | sh", shell=True, check=False)
            if success:
                # Try to start ollama
                run_cmd(["ollama", "serve"], check=False)
                return True
            return False
        else:
            log_error("curl is required to install Ollama")
            return False

def wait_for_ollama(timeout=60):
    """Wait for Ollama to become available."""
    log_info("Waiting for Ollama service...")
    import time
    start = time.time()
    while time.time() - start < timeout:
        if is_ollama_running():
            return True
        time.sleep(2)
    return False

def pull_model(model):
    """Pull an Ollama model."""
    log_info(f"Downloading model: {model}")
    log_info("  (This may take several minutes...)")
    
    success, result = run_cmd(["ollama", "pull", model], check=False)
    if success:
        log_success(f"Model installed: {model}")
        return True
    else:
        log_error(f"Failed to install: {model}")
        return False

def create_data_dirs():
    """Create JARVIS data directories."""
    log_info("Creating JARVIS data directories...")
    
    dirs = [
        "jarvis_data/memory",
        "jarvis_data/orchestrator", 
        "jarvis_data/chromadb",
        "jarvis_data/knowledge_graph",
        "jarvis_data/wal",
        "jarvis_data/procedural"
    ]
    
    for d in dirs:
        (PROJECT_DIR / d).mkdir(parents=True, exist_ok=True)
    
    log_success("Directories created")

def check_python():
    """Check Python version."""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 10:
        return True
    return False

def install_dependencies(python_cmd):
    """Install Python dependencies."""
    log_info("Installing Python dependencies...")
    
    # Upgrade pip
    run_cmd([python_cmd, "-m", "pip", "install", "--upgrade", "pip"], check=False)
    
    # Install requirements
    req_file = PROJECT_DIR / "requirements.txt"
    run_cmd([python_cmd, "-m", "pip", "install", "-r", str(req_file)], check=False)
    
    log_success("Dependencies installed")

def test_jarvis(python_cmd):
    """Test JARVIS installation."""
    log_info("Testing JARVIS...")
    
    success, _ = run_cmd([python_cmd, str(PROJECT_DIR / "jarvis_v19.py"), "--help"], check=False)
    if success:
        log_success("JARVIS is ready!")
        return True
    return False

def print_banner():
    """Print installation banner."""
    print(f"""
{Colors.CYAN}╔═══════════════════════════════════════════════════════════════╗
║          🤖 JARVIS V19 - Universal Setup Installer            ║
║                 Cross-Platform Python Edition                  ║
╚═══════════════════════════════════════════════════════════════╝{Colors.RESET}
""")

def main():
    print_banner()

    # ─── Step 1: Check Python ─────────────────────────────────────────
    log_info("[1/7] Checking Python installation...")

    if not check_python():
        log_error("Python 3.10+ required!")
        print(f"  Current: {sys.version}")
        print("\nPlease install Python 3.10 or higher from https://python.org/")
        return 1

    log_success(f"Python {sys.version_info.major}.{sys.version_info.minor} found")

    # Determine Python command
    python_cmd = "python" if sys.platform == "win32" else "python3"

    # ─── Step 2: Create Virtual Environment ───────────────────────────
    log_info("[2/7] Setting up virtual environment...")

    if VENV_DIR.exists():
        log_info("Virtual environment already exists")
    else:
        run_cmd([python_cmd, "-m", "venv", str(VENV_DIR)], check=False)
        log_success("Virtual environment created")

    # Determine venv Python
    if sys.platform == "win32":
        venv_python = str(VENV_DIR / "Scripts" / "python.exe")
    else:
        venv_python = str(VENV_DIR / "bin" / "python")

    # ─── Step 3: Install Dependencies ─────────────────────────────────
    log_info("[3/7] Installing Python dependencies...")
    install_dependencies(venv_python)

    # ─── Step 4: Check/Install Ollama ─────────────────────────────────
    log_info("[4/7] Checking Ollama...")

    if not is_ollama_running():
        if not shutil.which("ollama"):
            if not install_ollama():
                log_error("Could not install Ollama automatically")
                log_info("Please install Ollama manually and re-run this script")
                return 1
        else:
            log_warn("Ollama installed but not running. Starting...")
            subprocess.Popen(["ollama", "serve"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
            if not wait_for_ollama():
                log_error("Ollama failed to start")
                return 1

    log_success("Ollama is running")

    # ─── Step 5: Detect Hardware and Select Model ─────────────────────
    log_info("[5/7] Detecting hardware and selecting model...")

    hardware_info = detect_hardware()
    selected_model = select_model(hardware_info)

    # ─── Step 6: Pull Required Models ─────────────────────────────────
    log_info("[6/7] Downloading LLM models...")
    print()
    log_warn("  Model sizes (approximate):")
    print("  - nomic-embed-text:       ~274 MB")
    print("  - OpenEuroLLM-Czech:      ~4-5 GB")
    print(f"  - {selected_model}:      ~2-10 GB (varies by model)")
    print()
    log_warn("  This will take a while depending on your internet speed...")
    print()

    # Pull base models
    for model in BASE_MODELS:
        if not pull_model(model):
            log_error(f"Failed to pull model: {model}")
            return 1
        print()

    # Pull selected model
    if not pull_model(selected_model):
        log_error(f"Failed to pull model: {selected_model}")
        return 1
    print()

    # Update user configuration
    if not update_user_config(selected_model):
        log_warn("Failed to update configuration. You may need to edit jarvis_config/user_config.py manually")

    # ─── Step 7: Create Data Directories ───────────────────────────────
    log_info("[7/7] Creating data directories...")
    create_data_dirs()

    # ─── Test JARVIS ───────────────────────────────────────────────────
    print()
    test_jarvis(venv_python)

    # ─── Final: Summary ────────────────────────────────────────────────
    print()
    log_success("════════════════════════════════════════════════════════════")
    log_success("  🎉 INSTALLATION COMPLETE!")
    log_success("════════════════════════════════════════════════════════════")
    print()
    print("  Configuration:")
    print(f"  - Selected model: {selected_model}")
    print(f"  - Czech gateway:  OpenEuroLLM-Czech:latest")
    print()
    print("  Next steps:")
    if sys.platform == "win32":
        print("  1. Run: run.bat")
    else:
        print("  1. Run: ./run.sh")
    print(f"  2. Or:  {venv_python} jarvis_v19.py")
    print()
    print("  First run will initialize the vector database...")
    print()

    return 0

if __name__ == "__main__":
    sys.exit(main())
