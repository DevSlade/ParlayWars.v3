@echo off
REM ParlayWars v3 — Windows Startup Script
REM Usage: start.bat

echo ╔══════════════════════════════════════════════════════════╗
echo ║           PARLAY WARS v3.0 — STARTING UP               ║
echo ╚══════════════════════════════════════════════════════════╝

cd /d "%~dp0"

REM 1. Install dependencies
echo [1/4] Installing Python dependencies...
pip install -r requirements.txt -q

REM 2. Bootstrap database if empty
echo [2/4] Bootstrapping database...
python main.py --bootstrap

REM 3. Start OSWS scraper service (background)
echo [3/4] Starting OSWS scraper service on port 8001...
start /B python -m osws.scraper_api

REM Wait for OSWS to start
timeout /t 3 /nobreak > nul

REM 4. Start ParlayWars server
echo [4/4] Starting ParlayWars server...
echo.
echo   Dashboard: http://localhost:8000
echo   API docs:  http://localhost:8000/docs
echo   OSWS API:  http://localhost:8001
echo.

REM Optional: Cloudflare tunnel
REM Uncomment to expose publicly:
REM start /B cloudflared tunnel --url http://localhost:8000

python main.py
