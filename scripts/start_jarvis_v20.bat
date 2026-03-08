@echo off
chcp 65001 >nul
setlocal

:: JARVIS V20 - State-of-the-Art AI Agent Launcher
:: ══════════════════════════════════════════════════════════
::  🤖 JARVIS V20 - STATE-OF-THE-ART AI AGENT
:: ══════════════════════════════════════════════════════════

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo.
echo ╔═══════════════════════════════════════════════════════════╗
echo ║                                                               ║
echo ║         🤖 JARVIS V20 - STATE-OF-THE-ART AI AGENT         ║
echo ║                                                               ║
echo ╚═══════════════════════════════════════════════════════════╝
echo.

:: 1. Auto-update
echo [*] Kontroluji aktualizace z GitHubu...
git pull
if %errorlevel% neq 0 (
    echo [!] Problem se stazením, pokračuji s lokální verzí.
)
echo.

:: 2. Kontrola Pythonu
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python není nainstalován!
    pause
    exit /b 1
)

:: 3. Kontrola venv
if exist ".venv\Scripts\activate.bat" (
    echo [*] Aktivuji virtualni prostredi...
    call ".venv\Scripts\activate.bat"

    echo [*] Kontroluji zavislosti...
    python -m pip install -r requirements.txt -q
) else (
    echo [!] Virtuální prostředí nenalezeno!
    pause
    exit /b 1
)
echo.

:: 4. Kontrola Ollamy
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Ollama neběží!
    echo [*] Startuji Ollamu na pozadi...
    start "" ollama serve
    timeout /t 5 /nobreak >nul
) else (
    echo [OK] Ollama je připravena.
)

echo.
echo [*] Startuji JARVIS V20 State-of-the-Art...
echo ═════════════════════════════════════════════════════════════
echo.

python jarvis_v20.py %*

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] JARVIS V20 selhal s kódem %errorlevel%
    echo.
    echo 💡 Možné řešení:
    echo   - Zkontrolujte, zda běží Ollama: ollama serve
    echo   - Zkontrolujte modely: ollama list
    echo   - Zapněte debug mód: python jarvis_v20.py --debug
    echo.
    pause
    exit /b %errorlevel%
)

pause
