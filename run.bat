@echo off
chcp 65001 >nul
setlocal

:: ═══════════════════════════════════════════════════════════════════════
::  JARVIS Universal Launcher - Version Switcher
::  Supports V19 and V20
:: ═══════════════════════════════════════════════════════════════════════

:: DETEKCE VERZE (změňte zde pro přepínání)
set "JARVIS_VERSION=20"

:: PŘEČTUJTE ZDE PRO PŘEPÍNÍ VERZE
:: 20 = JARVIS V20 (nejnovější, SOTA)
:: 19 = JARVIS V19 (historická, pro zpětnou kompatibilitu)

if "%JARVIS_VERSION%"=="20" (
    set "JARVIS_DIR=jarvis_v20"
    set "PYTHON_FILE=jarvis_v20.py"
    set "TITLE=JARVIS V20 - State-of-the-Art AI Agent"
) else (
    set "JARVIS_DIR=jarvis_v19"
    set "PYTHON_FILE=jarvis_v19.py"
    set "TITLE=JARVIS V19 - AI Assistant"
)

:: Banner
echo.
echo ╔═══════════════════════════════════════════════════╗
echo ║                                                               ║
echo ║         %TITLE%         ║
echo ║                                                               ║
echo ╚═════════════════════════════════════════════════════╝
echo.

set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
cd /d "%PROJECT_DIR%"

:: 1. Auto-update
echo [*] Kontroluji aktualizace z GitHubu...
git pull
if %errorlevel% neq 0 (
    echo [!] Problem se stazenim, pokracuji s lokalni verzi.
)
echo.

:: 2. Kontrola Pythonu
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python neni nainstalovan!
    pause
    exit /b 1
)

:: 3. Vyber verze (promenna JARVIS_VERSION)
if "%JARVIS_VERSION%"=="20" (
    echo [*] JARVIS V20 aktivovana - nejnovější verze
    set "REQUIREMENTS=requirements_v20.txt"
) else (
    echo [*] JARVIS V19 aktivovana - historicka verze
    set "REQUIREMENTS=requirements_v19.txt"
)

:: 4. Kontrola venv
if exist "%PROJECT_DIR%\.venv\Scripts\activate.bat" (
    echo [*] Aktivuji virtualni prostredi...
    call "%PROJECT_DIR%\.venv\Scripts\activate.bat"
    
    echo [*] Kontroluji zavislosti...
    python -m pip install -r %REQUIREMENTS% -q
) else (
    echo [!] Virtualni prostredi nalezeno!
    pause
    exit /b 1
)
echo.

:: 5. Kontrola Ollamy
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Ollama neběží!
    echo [*] Startuji Ollamu na pozadi...
    start "" ollama serve
    timeout /t 5 /nobreak >nul
) else (
    echo [OK] Ollama je pripravena.
)

echo.
echo [*] Startuji %JARVIS_VERSION%...
echo ═════════════════════════════════════════════════════
echo.

python start.py %*

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] JARVIS %JARVIS_VERSION% selhal s kodem %errorlevel%
    echo.
    echo 💡 Možné řešení:
    echo    - Zkontrolujte, zda běží Ollama: ollama serve
    echo    - Zkontrolujte modely: ollama list
    echo    - Přepněte verzi (změňte JARVIS_VERSION=19 v run.bat)
    echo    - Zapněte debug mód: python start.py --debug
    echo.
    pause
    exit /b %errorlevel%
)

pause
