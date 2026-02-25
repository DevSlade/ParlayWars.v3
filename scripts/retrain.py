"""
ParlayWars v3 — Force Retrain All Engines (CLI Script)
Date: 2026-02-25

Usage:
    python scripts/retrain.py

Loads all players from the database and retrains TITAN, PHANTOM, SURGE.
ORACLE is updated to use new sub-engine outputs.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import get_all_players_sync, init_db_sync
from core.logger import setup_logging, get_logger

log = get_logger(__name__)


def retrain_all() -> None:
    """Retrain all engines on current database player data."""
    setup_logging()
    init_db_sync()

    players = get_all_players_sync()
    if not players:
        log.error("No players in database. Run seed_database.py first.")
        sys.exit(1)

    log.info("Retraining all engines on %d players...", len(players))

    from engines.titan import titan_engine
    from engines.phantom import phantom_engine
    from engines.surge import surge_engine
    from engines.oracle import oracle_engine

    titan_engine.train_on_players(players)
    log.info("TITAN trained.")

    phantom_engine.train_on_players(players)
    log.info("PHANTOM trained.")

    surge_engine.train_on_players(players)
    log.info("SURGE trained.")

    oracle_engine.set_sub_engines([titan_engine, phantom_engine, surge_engine])
    log.info("ORACLE sub-engines set.")

    log.info("All engines retrained successfully.")


if __name__ == "__main__":
    retrain_all()
    print("✅ All engines retrained.")
