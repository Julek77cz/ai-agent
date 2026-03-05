@echo off
chcp 65001 >nul
setlocal

:: ═══════════════════════════════════════════════════════════════════════
::  JARVIS V19 - Launcher (run after installation)
::  Double-click or run from terminal
:: ═══════════════════════════════════════════════════════════════════════

set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
cd /d "%PROJECT_DIR%"

:: Activate virtual environment if exists
if exist "%PROJECT_DIR%\.venv\Scripts\activate.bat" (
    call "%PROJECT_DIR%\.venv\Scripts\activate.bat"
)

:: Check for Ollama
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [WARNING] Ollama is not running!
    echo Starting Ollama service...
    start "" ollama serve
    timeout /t 5 /nobreak >nul
)

:: Run JARVIS
python jarvis_v19.py %*
