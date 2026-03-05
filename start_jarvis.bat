@echo off
chcp 65001 >nul
setlocal

:: ═══════════════════════════════════════════════════════════════════════
::  JARVIS V19 - Windows Launcher
::  Double-click or run from terminal to start JARVIS
:: ═══════════════════════════════════════════════════════════════════════

set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
cd /d "%PROJECT_DIR%"

echo.
echo ╔═══════════════════════════════════════════════════════════════════════╗
echo ║                                                                       ║
echo ║           🤖 JARVIS V19 - AI Assistant Launcher                       ║
echo ║                                                                       ║
echo ╚═══════════════════════════════════════════════════════════════════════╝
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.8+ and try again.
    pause
    exit /b 1
)

:: Activate virtual environment if exists
if exist "%PROJECT_DIR%\.venv\Scripts\activate.bat" (
    echo [*] Activating virtual environment...
    call "%PROJECT_DIR%\.venv\Scripts\activate.bat"
) else (
    echo [!] Virtual environment not found, using system Python
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

echo.
echo [*] Starting JARVIS...
echo.

:: Run JARVIS
python jarvis_v19.py %*

:: Pause if there was an error
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] JARVIS exited with error code %errorlevel%
    pause
)
