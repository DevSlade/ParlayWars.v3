#!/usr/bin/env bash
# ParlayWars v3 — Unified Startup Script
# Usage: bash start.sh [--no-osws] [--no-tunnel]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║           PARLAY WARS v3.0 — STARTING UP               ║"
echo "╚══════════════════════════════════════════════════════════╝"

# ── 1. Install dependencies ────────────────────────────────────────────────
echo "[1/4] Installing Python dependencies..."
pip install -r requirements.txt -q

# ── 2. Bootstrap database if empty ────────────────────────────────────────
echo "[2/4] Bootstrapping database..."
python main.py --bootstrap

# ── 3. Start OSWS scraper service (background) ────────────────────────────
START_OSWS=true
for arg in "$@"; do
  [[ "$arg" == "--no-osws" ]] && START_OSWS=false
done

if $START_OSWS; then
  echo "[3/4] Starting OSWS scraper service on port 8001..."
  python -m osws.scraper_api &
  OSWS_PID=$!
  echo "      OSWS PID: $OSWS_PID"
  sleep 2
else
  echo "[3/4] Skipping OSWS (--no-osws flag set)."
fi

# ── 4. Start ParlayWars server ────────────────────────────────────────────
echo "[4/4] Starting ParlayWars server..."
echo ""
echo "  Dashboard: http://localhost:8000"
echo "  API docs:  http://localhost:8000/docs"
if $START_OSWS; then
  echo "  OSWS API:  http://localhost:8001"
fi
echo ""

# Optional: Cloudflare tunnel
# Uncomment to expose publicly:
# cloudflared tunnel --url http://localhost:8000 &

python main.py
