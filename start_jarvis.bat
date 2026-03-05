@echo off
chcp 65001 >nul
setlocal

:: ═══════════════════════════════════════════════════════════════════════
::  JARVIS V19 - Ultimate Auto-Updating Launcher
:: ═══════════════════════════════════════════════════════════════════════

set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
cd /d "%PROJECT_DIR%"

echo.
echo ╔═══════════════════════════════════════════════════════════════════════╗
echo ║                                                                       ║
echo ║             🤖 JARVIS V19 - AI Assistant Launcher                     ║
echo ║                                                                       ║
echo ╚═══════════════════════════════════════════════════════════════════════╝
echo.

:: 1. Auto-Update z GitHubu
echo [*] Kontroluji aktualizace z GitHubu...
git pull
if %errorlevel% neq 0 (
    echo [!] Problem se stazenim aktualizaci. Pokracuji s lokalni verzi.
)
echo.

:: 2. Kontrola Pythonu
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python neni nainstalovany nebo neni v PATH!
    pause
    exit /b 1
)

:: 3. Aktivace venv a knihoven
if exist "%PROJECT_DIR%\.venv\Scripts\activate.bat" (
    echo [*] Aktivuji virtualni prostredi...
    call "%PROJECT_DIR%\.venv\Scripts\activate.bat"
    
    echo [*] Kontroluji zavislosti...
    python -m pip install -r requirements.txt -q
) else (
    echo [!] Virtualni prostredi nenalezeno! Zkus spustit setup.bat.
    pause
    exit /b 1
)
echo.

:: 4. Kontrola Ollamy
echo [*] Kontroluji Ollamu...
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Ollama nebezi! Startuji sluzbu na pozadi...
    start "" ollama serve
    timeout /t 5 /nobreak >nul
) else (
    echo [OK] Ollama je pripravena.
)

echo.
echo [*] Startuji Mozek...
echo ═══════════════════════════════════════════════════════════════════════
echo.

:: 5. Spusteni
python jarvis_v19.py %*

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] JARVIS spadl s chybovym kodem %errorlevel%
    pause
)
