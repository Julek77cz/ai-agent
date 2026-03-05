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
from pathlib import Path

# Configuration
PROJECT_DIR = Path(__file__).parent.resolve()
VENV_DIR = PROJECT_DIR / ".venv"
OLLAMA_URL = "http://localhost:11434"
MODELS = [
    "nomic-embed-text",
    "jobautomation/OpenEuroLLM-Czech:latest",
    "qwen2.5:3b-instruct"
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
    log_info("[1/6] Checking Python installation...")
    
    if not check_python():
        log_error("Python 3.10+ required!")
        print(f"  Current: {sys.version}")
        print("\nPlease install Python 3.10 or higher from https://python.org/")
        return 1
    
    log_success(f"Python {sys.version_info.major}.{sys.version_info.minor} found")
    
    # Determine Python command
    python_cmd = "python" if sys.platform == "win32" else "python3"
    
    # ─── Step 2: Create Virtual Environment ───────────────────────────
    log_info("[2/6] Setting up virtual environment...")
    
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
    log_info("[3/6] Installing Python dependencies...")
    install_dependencies(venv_python)
    
    # ─── Step 4: Check/Install Ollama ─────────────────────────────────
    log_info("[4/6] Checking Ollama...")
    
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
    
    # ─── Step 5: Pull Required Models ─────────────────────────────────
    log_info("[5/6] Downloading LLM models...")
    print()
    log_warn("  Model sizes (approximate):")
    print("  - nomic-embed-text:       ~274 MB")
    print("  - OpenEuroLLM-Czech:      ~4-5 GB")
    print("  - qwen2.5:3b-instruct:    ~2 GB")
    print("  Total: ~7 GB")
    print()
    log_warn("  This will take a while depending on your internet speed...")
    print()
    
    for model in MODELS:
        if not pull_model(model):
            log_error(f"Failed to pull model: {model}")
            return 1
        print()
    
    # ─── Step 6: Create Data Directories ───────────────────────────────
    log_info("[6/6] Creating data directories...")
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
