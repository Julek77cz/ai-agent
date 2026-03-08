# JARVIS V19 - Installation Guide

## Quick Start (Double-Click)

### Windows
1. Double-click `scripts/setup.bat`
2. Wait for installation to complete (~10-15 minutes for first-time setup)
3. Double-click `scripts/run.bat` to start JARVIS

### Linux/Mac
```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
./scripts/run.sh
```

---

## Requirements

### Python
- **Version**: 3.10 or higher
- **Windows**: Download from https://www.python.org/downloads/
- **Linux**: `sudo apt install python3 python3-pip` (Debian/Ubuntu)
- **macOS**: `brew install python3`

### Ollama (Local LLM Runtime)
- **Windows**: Download from https://ollama.com/download/windows
- **Linux**: Auto-installed by setup script
- **macOS**: `brew install ollama` or download from https://ollama.com/download/mac
- **RAM**: Minimum 8GB (16GB recommended)
- **Storage**: ~7GB for models

---

## Installation Steps

### Step 1: Run Setup
- **Windows**: Double-click `scripts/setup.bat`
- **Linux/Mac**: `./scripts/setup.sh`

The setup will:
1. ✅ Check Python version
2. ✅ Create virtual environment (`.venv/`)
3. ✅ Install Python dependencies
4. ✅ Check/install Ollama runtime
5. ✅ Download required LLM models (~7GB)
6. ✅ Create data directories

### Step 2: Run JARVIS
- **Windows**: Double-click `scripts/run.bat`
- **Linux/Mac**: `./scripts/run.sh`

Or manually:
```bash
# Activate virtual environment
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate    # Windows

# Run JARVIS
python jarvis_v19.py
```

---

## First Run

On first run, JARVIS will:
1. Initialize vector database (ChromaDB)
2. Create knowledge graph structure
3. Test LLM connectivity
4. Ready to use!

---

## Troubleshooting

### "Python not found"
- Install Python 3.10+ from https://python.org
- On Windows: Check "Add Python to PATH" during installation

### "Ollama not running"
- Windows: Start "Ollama" from Start Menu or run `ollama serve`
- Linux/Mac: Run `ollama serve` in terminal

### "Model not found"
- Re-run setup: `./scripts/setup.sh` or `scripts/setup.bat`
- Or manually: `ollama pull <model-name>`

### Port 11434 already in use
- Another application is using Ollama's port
- Check: `curl http://localhost:11434/api/tags`

### Out of memory
- Models require ~8GB RAM
- Close other applications
- Use smaller models (see below)

---

## Custom Models

Edit `jarvis_config/__init__.py` to change models:

```python
MODELS = {
    "czech_gateway": "your-model:tag",
    "planner": "your-planner:tag",
    "verifier": "your-verifier:tag",
    "reasoner": "your-reasoner:tag",
}
```

Then re-download:
```bash
ollama pull your-model:tag
```

---

## File Structure

```
jarvis_v19/
├── scripts/
│   ├── setup.bat          # Windows installer
│   ├── setup.sh           # Linux/Mac installer
│   ├── setup.py           # Cross-platform Python installer
│   ├── run.bat            # Windows launcher
│   └── run.sh             # Linux/Mac launcher
├── requirements.txt      # Python dependencies
├── jarvis_v19.py          # Main entry point
├── .venv/                 # Virtual environment (created by setup)
└── jarvis_data/           # Runtime data (created by JARVIS)
    ├── memory/
    ├── chromadb/
    ├── knowledge_graph/
    ├── wal/
    └── procedural/
```

---

## Uninstall

```bash
# Remove virtual environment
rm -rf .venv          # Linux/Mac
rmdir /s /q .venv     # Windows

# Remove models (optional)
ollama rm nomic-embed-text
ollama rm jobautomation/OpenEuroLLM-Czech:latest
ollama rm qwen2.5:3b-instruct

# Remove data (optional)
rm -rf jarvis_data
```

---

## Support

- Ollama docs: https://github.com/ollama/ollama
- JARVIS issues: https://github.com/your-repo/jarvis-v19
