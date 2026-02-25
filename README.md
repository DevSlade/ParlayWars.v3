# ParlayWars v3 — 2K eBasketball AI Prediction & Paper Trading Platform
> **Date:** 2026-02-25 | **Version:** 3.0.0

A full-stack web platform for predicting 2K eBasketball match outcomes using multiple real machine learning engines and automatically paper-trading those predictions.

---

## Quick Start

```bash
pip install -r requirements.txt
python main.py           # start server on :8000
open http://localhost:8000
```

### Remote Access via Cloudflare Tunnel
```bash
cloudflared tunnel --url http://localhost:8000
```

---

## Remote Access via Cloudflare Tunnel

Access ParlayWars from any device (phone, tablet, another computer) without port forwarding.

### Option 1: Quick (no account needed)
```bash
# Install cloudflared
brew install cloudflare/cloudflare/cloudflared   # macOS
# or: curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared && chmod +x cloudflared

# Start tunnel (generates a random URL)
cloudflared tunnel --url http://localhost:8000
# Outputs: https://random-name.trycloudflare.com
```

### Option 2: Named tunnel (persistent URL)
```bash
cloudflared tunnel login
cloudflared tunnel create parlaywars
cloudflared tunnel route dns parlaywars yourdomain.com
cloudflared tunnel run parlaywars
```

### Running both server and tunnel together
```bash
# Terminal 1
python main.py

# Terminal 2
cloudflared tunnel --url http://localhost:8000
```

---

## AI Engines

| Engine | Model | Description |
|--------|-------|-------------|
| TITAN | XGBoost (500 trees) | Green Code YT approach — gradient boosting, L1/L2 regularisation |
| PHANTOM | LogReg + Random Forest | Underdog hunter — H2H anomalies + form reversals |
| SURGE | LightGBM + EWMA | Momentum detector — hot/cold streaks via EWMA features |
| ORACLE | PyTorch MLP | Meta-ensemble stacking TITAN/PHANTOM/SURGE |

All engines use real ML training on 35 engineered features. No mock outputs.

---

## Data Sources

| API | Key | Purpose |
|-----|-----|---------|
| HudStats (api-h2h.hudstats.com) | None (free) | PRIMARY — player stats, live/scheduled matches |
| ESportsBattle (basketball.esportsbattle.com) | None (free) | Secondary — tournament/match structure |
| The Odds API | b824c5f93dc1f906c306702b7eb1f6fc | Bookie odds |
| BetsAPI | Optional ($10/mo) | Extra match data (disabled by default) |

---

## Directory Structure

```
ParlayWars.v3/
├── main.py                    # Entry point
├── config.yaml                # All settings
├── requirements.txt
├── core/                      # DB, cache, logger, config, scheduler, models
├── engines/                   # TITAN, PHANTOM, SURGE, ORACLE, features, ELO
├── sports/ebasketball/        # HudStats, ESportsBattle, Odds API clients
├── sim/                       # Bankroll, bettor, parlay, tracker
└── server/                    # FastAPI app, REST API, WebSocket, SPA
```

---

## Scripts

```bash
python scripts/seed_database.py    # Seed DB from TSV
python scripts/retrain.py          # Force retrain all engines
python scripts/export_data.py      # Export all tables to data/exports/
```

---

## Database Schema (SQLite, 9 tables)

`players` | `matches` | `h2h_records` | `predictions` | `bets` | `bankroll_log` | `engine_votes` | `model_training_log` | `player_snapshots`

---

## Web UI Tabs

| Tab | Content |
|-----|---------|
| Dashboard | Live/upcoming matches, engine vote cards, bankroll chart, quick predict |
| Players | Searchable table, click for full profile |
| Predictions | All engine predictions with tier badges |
| H2H | Two-player comparison with engine predictions |
| Trees | D3.js interactive decision tree per engine |
| Simulator | Paper trading P/L chart, bet log, engine breakdown |
| Console | Live server log stream |
| Settings | Edit config.yaml in-browser |
| Export | Download data as CSV or JSON |
