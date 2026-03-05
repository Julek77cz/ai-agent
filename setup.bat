@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ═══════════════════════════════════════════════════════════════════════
::  JARVIS V19 - Universal Setup Installer (Windows)
::  Double-click to run - automatically installs Python deps & Ollama models
:: ═══════════════════════════════════════════════════════════════════════

setlocal

:: ─── Configuration ─────────────────────────────────────────────────────
set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
cd /d "%PROJECT_DIR%"

set "VENV_DIR=%PROJECT_DIR%\.venv"
set "PYTHON_MIN=3.10"
set "OLLAMA_URL=http://localhost:11434"
set "MODELS=nomic-embed-text jobautomation/OpenEuroLLM-Czech:latest qwen2.5:3b-instruct"

:: ─── Colors for Windows ───────────────────────────────────────────────
set "RESET=[0m"
set "RED=[91m"
set "GREEN=[92m"
set "YELLOW=[93m"
set "CYAN=[96m"
set "BLUE=[94m"

:: ─── Helper Functions ──────────────────────────────────────────────────
goto :main

:echo_color
setlocal
set "color=%~1"
set "text=%~2"
echo %color%%text%%RESET%
endlocal
goto :eof

:check_python
where python >nul 2>&1
if %errorlevel% equ 0 (
    python --version 2>nul | findstr /r "Python [3]\.[0-9]*" >nul
    if !errorlevel! equ 0 (
        set "PYTHON=python"
        exit /b 0
    )
)
where py >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON=py"
    exit /b 0
)
exit /b 1

:get_python_version
for /f "tokens=2" %%v in ('%PYTHON% --version 2^>^&1') do set "PYTHON_VERSION=%%v"
exit /b 0

:check_ollama_running
curl -s "%OLLAMA_URL%/api/tags" >nul 2>&1
exit /b %errorlevel%

:wait_for_ollama
echo.
call :echo_color %YELLOW% "  Checking Ollama service..."
set "OLLAMA_READY=0"
for /L %%i in (1,1,30) do (
    curl -s "%OLLAMA_URL%/api/tags" >nul 2>&1
    if !errorlevel! equ 0 (
        set "OLLAMA_READY=1"
        goto :eof
    )
    timeout /t 2 /nobreak >nul
)
exit /b %errorlevel%

:create_venv
if exist "%VENV_DIR%\Scripts\activate.bat" (
    call :echo_color %BLUE% "  Virtual environment already exists"
    exit /b 0
)
call :echo_color %CYAN% "  Creating virtual environment..."
%PYTHON% -m venv "%VENV_DIR%"
if !errorlevel! neq 0 (
    call :echo_color %RED% "  ERROR: Failed to create virtual environment"
    exit /b 1
)
exit /b 0

:activate_venv
set "PATH=%VENV_DIR%\Scripts;%PATH%"
exit /b 0

:install_dependencies
call :echo_color %CYAN% "  Installing Python dependencies..."
pip install --upgrade pip -q
if !errorlevel! neq 0 (
    call :echo_color %RED% "  ERROR: Failed to upgrade pip"
    exit /b 1
)
pip install -r "%PROJECT_DIR%\requirements.txt" -q
if !errorlevel! neq 0 (
    call :echo_color %RED% "  ERROR: Failed to install dependencies"
    exit /b 1
)
exit /b 0

:install_ollama_windows
echo.
call :echo_color %YELLOW% "════════════════════════════════════════════════════════════"
call :echo_color %YELLOW% "  Ollama is NOT installed. Downloading and installing..."
call :echo_color %YELLOW% "════════════════════════════════════════════════════════════"
echo.
echo  1. Download Ollama for Windows:
echo     https://ollama.com/download/windows
echo.
echo  2. Run the installer (OllamaSetup.exe)
echo.
echo  3. After installation, restart this script
echo.
echo  Alternative - using winget (if available):
echo   winget install Ollama.Ollama
echo.
call :echo_color %YELLOW% "  Press any key after installing Ollama..."
pause >nul
exit /b 1

:pull_model
setlocal
set "model=%~1"
call :echo_color %CYAN% "  Downloading model: %model% (this may take several minutes)..."
call :echo_color %CYAN% "  ════════════════════════════════════════════════════════════"
ollama pull %model%
if !errorlevel! equ 0 (
    call :echo_color %GREEN% "  ✓ Model installed: %model%"
) else (
    call :echo_color %RED% "  ✗ Failed to install: %model%"
    exit /b 1
)
endlocal
exit /b 0

:create_data_dirs
call :echo_color %CYAN% "  Creating JARVIS data directories..."
if not exist "%PROJECT_DIR%\jarvis_data" mkdir "%PROJECT_DIR%\jarvis_data"
if not exist "%PROJECT_DIR%\jarvis_data\memory" mkdir "%PROJECT_DIR%\jarvis_data\memory"
if not exist "%PROJECT_DIR%\jarvis_data\orchestrator" mkdir "%PROJECT_DIR%\jarvis_data\orchestrator"
if not exist "%PROJECT_DIR%\jarvis_data\chromadb" mkdir "%PROJECT_DIR%\jarvis_data\chromadb"
if not exist "%PROJECT_DIR%\jarvis_data\knowledge_graph" mkdir "%PROJECT_DIR%\jarvis_data\knowledge_graph"
if not exist "%PROJECT_DIR%\jarvis_data\wal" mkdir "%PROJECT_DIR%\jarvis_data\wal"
if not exist "%PROJECT_DIR%\jarvis_data\procedural" mkdir "%PROJECT_DIR%\jarvis_data\procedural"
exit /b 0

:test_jarvis
call :echo_color %CYAN% "  Testing JARVIS installation..."
python jarvis_v19.py --help >nul 2>&1
if !errorlevel! equ 0 (
    call :echo_color %GREEN% "  ✓ JARVIS is ready!"
    exit /b 0
) else (
    call :echo_color %RED% "  ✗ JARVIS test failed"
    exit /b 1
)
exit /b 0

:print_banner
echo.
echo %CYAN%╔═══════════════════════════════════════════════════════════════╗
echo %CYAN%║          🤖 JARVIS V19 - Universal Setup Installer            ║
echo %CYAN%║                 Windows Edition (Double-click)                ║
echo %CYAN%╚═══════════════════════════════════════════════════════════════╝%RESET%
echo.
exit /b 0

:main
call :print_banner

:: ─── Step 1: Check Python ───────────────────────────────────────────────
call :echo_color %CYAN% "[1/6] Checking Python installation..."
call :check_python
if !errorlevel! equ 1 (
    call :echo_color %RED% "ERROR: Python 3.10+ not found!"
    echo.
    echo Please install Python from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)
call :get_python_version
call :echo_color %GREEN% "  ✓ Python !PYTHON_VERSION! found"

:: ─── Step 2: Create Virtual Environment ─────────────────────────────────
call :echo_color %CYAN% "[2/6] Setting up virtual environment..."
call :create_venv
if !errorlevel! equ 1 (
    pause
    exit /b 1
)
call :activate_venv

:: ─── Step 3: Install Dependencies ──────────────────────────────────────
call :echo_color %CYAN% "[3/6] Installing Python dependencies..."
call :install_dependencies
if !errorlevel! equ 1 (
    pause
    exit /b 1
)
call :echo_color %GREEN% "  ✓ Dependencies installed"

:: ─── Step 4: Check/Install Ollama ───────────────────────────────────────
call :echo_color %CYAN% "[4/6] Checking Ollama..."
call :check_ollama_running
if !errorlevel! neq 0 (
    :: Ollama not running - check if installed
    ollama --version >nul 2>&1
    if !errorlevel! neq 0 (
        call :install_ollama_windows
    ) else (
        :: Ollama installed but not running - start it
        call :echo_color %YELLOW% "  Starting Ollama service..."
        start "" ollama serve
        call :wait_for_ollama
        if !OLLAMA_READY! equ 0 (
            call :echo_color %RED% "  ERROR: Ollama failed to start"
            pause
            exit /b 1
        )
    )
)
call :echo_color %GREEN% "  ✓ Ollama is running"

:: ─── Step 5: Pull Required Models ───────────────────────────────────────
call :echo_color %CYAN% "[5/6] Downloading LLM models..."
echo.
echo   Model sizes (approximate):
echo   - nomic-embed-text:       ~274 MB
echo   - OpenEuroLLM-Czech:      ~4-5 GB
echo   - qwen2.5:3b-instruct:    ~2 GB
echo   Total: ~7 GB
echo.
echo   This will take a while depending on your internet speed...
echo.
for %%m in (%MODELS%) do (
    call :pull_model "%%m"
    if !errorlevel! neq 0 (
        call :echo_color %RED% "  ERROR: Failed to pull model %%m"
        pause
        exit /b 1
    )
)

:: ─── Step 6: Create Data Directories ───────────────────────────────────
call :echo_color %CYAN% "[6/6] Creating data directories..."
call :create_data_dirs
call :echo_color %GREEN% "  ✓ Directories created"

:: ─── Final: Test and Summary ────────────────────────────────────────────
echo.
call :echo_color %GREEN% "════════════════════════════════════════════════════════════"
call :echo_color %GREEN% "  🎉 INSTALLATION COMPLETE!"
call :echo_color %GREEN% "════════════════════════════════════════════════════════════"
echo.
echo   Next steps:
echo   1. Run: run.bat   (or double-click run.bat)
echo   2. Or: python jarvis_v19.py
echo.
echo   First run will initialize the vector database...
echo.
pause
