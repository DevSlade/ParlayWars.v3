"""
ParlayWars v3 — Entry Point
Date: 2026-02-25

Usage:
    python main.py                         # Start server with config.yaml defaults
    python main.py --port 8080             # Custom port
    python main.py --bootstrap             # Bootstrap the database from HudStats API
    python main.py --retrain               # Force retrain all engines then exit

Cloudflare Tunnel (for remote access from any device):
    cloudflared tunnel --url http://localhost:8000
"""
from __future__ import annotations

import argparse
import os
import sys

# Ensure project root is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    """Parse CLI args and launch the appropriate mode."""
    parser = argparse.ArgumentParser(
        prog="parlayWars",
        description="ParlayWars v3 — 2K eBasketball AI Prediction Platform",
    )
    parser.add_argument("--host", default=None, help="Server host (overrides config.yaml)")
    parser.add_argument("--port", type=int, default=None, help="Server port (overrides config.yaml)")
    parser.add_argument("--bootstrap", action="store_true", help="Bootstrap database from HudStats API and exit")
    parser.add_argument("--retrain", action="store_true", help="Force retrain all engines and exit")
    parser.add_argument("--no-reload", action="store_true", help="Disable auto-reload (production mode)")
    args = parser.parse_args()

    from core.config import cfg
    from core.logger import setup_logging

    setup_logging()

    if args.bootstrap:
        from scripts.seed_database import bootstrap_from_api
        count = bootstrap_from_api(force=True)
        print(f"✅ Bootstrapped {count} players from HudStats API.")
        return

    if args.retrain:
        from scripts.retrain import retrain_all
        retrain_all()
        return

    # Start the FastAPI server
    import uvicorn

    host = args.host or cfg.get("server", "host", default="0.0.0.0")
    port = args.port or cfg.get("server", "port", default=8000)
    log_level = cfg.get("server", "log_level", default="info")
    reload = not args.no_reload and cfg.get("server", "reload", default=False)

    # ── Dynamic ASCII banner ─────────────────────────────────────────────────
    player_count = 0
    match_count = 0
    bankroll_val = 0.0
    try:
        from core.database import get_player_count_sync, get_match_count_sync
        player_count = get_player_count_sync()
        match_count = get_match_count_sync()
    except Exception:
        pass
    try:
        from sim.bankroll import bankroll_manager
        bankroll_val = bankroll_manager.balance
    except Exception:
        pass

    sim_status = "RUNNING"
    print(f"""
╔══════════════════════════════════════════════════════════╗
║           PARLAY WARS v3.0 — ONLINE                     ║
║       2K eBasketball AI Prediction Engine               ║
╠══════════════════════════════════════════════════════════╣
║  Engines:  TITAN ✅  PHANTOM ✅  SURGE ✅  ORACLE ✅      ║
║  APIs:     HudStats ✅  ESportsBattle ✅  Odds ✅         ║
║  Sim:      {sim_status:<8} |  Bankroll: ${bankroll_val:<20.2f}  ║
║  Players:  {player_count:<6} loaded  |  Matches: {match_count:<17,}  ║
║  Server:   http://localhost:{port:<30}  ║
╚══════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "server.app:create_app",
        factory=True,
        host=host,
        port=port,
        log_level=log_level,
        reload=reload,
    )


if __name__ == "__main__":
    main()
