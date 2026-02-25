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

    print(f"""
╔═══════════════════════════════════════════════════════╗
║          ParlayWars v3 — Starting Up                  ║
║  2K eBasketball AI Prediction & Paper Trading         ║
╠═══════════════════════════════════════════════════════╣
║  URL:  http://{host}:{port:<38} ║
║  Date: 2026-02-25                                     ║
╠═══════════════════════════════════════════════════════╣
║  Cloudflare Tunnel (remote access):                   ║
║  cloudflared tunnel --url http://localhost:{port:<6}  ║
╚═══════════════════════════════════════════════════════╝
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
