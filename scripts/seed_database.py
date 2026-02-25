"""
ParlayWars v3 — Seed Database Script
Date: 2026-02-25

Parses data/seed/players_seed.tsv and populates the SQLite database
with all 166 players. Also initialises their ELO ratings based on
win rate (higher win rate → higher starting ELO).
Also computes PWR ratings.
"""
from __future__ import annotations

import sys
import os

# Allow running from repo root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import init_db_sync, upsert_player_sync
from core.logger import setup_logging, get_logger
from engines.elo import DEFAULT_ELO
from engines.ratings import compute_pwr
from sports.ebasketball.parser import parse_seed_file

log = get_logger(__name__)


def _elo_from_win_pct(win_pct: float, rank: int) -> float:
    """
    Estimate a starting ELO from overall win percentage and rank.
    Range: 1200 (19% WR) to 1900 (73% WR).
    """
    # Linear interpolation: WR 50% → 1500, WR 73% → 1800, WR 19% → 1200
    elo = DEFAULT_ELO + (win_pct - 50.0) * 10.0
    # Rank boost for top players
    if rank <= 10:
        elo += 50.0
    elif rank <= 25:
        elo += 25.0
    return round(max(1100.0, min(2000.0, elo)), 1)


def seed_all() -> int:
    """
    Run the full seed: parse TSV → compute ELO + PWR → upsert all players.
    Returns the number of players seeded.
    """
    setup_logging()
    init_db_sync()

    players = parse_seed_file()
    if not players:
        log.error("No players parsed — seed TSV missing or empty.")
        return 0

    for player in players:
        # Compute starting ELO from win rate + rank
        player["elo"] = _elo_from_win_pct(
            float(player.get("win_pct") or 50.0),
            int(player.get("rank") or 83),
        )
        # Compute PWR composite rating
        player["pwr_rating"] = compute_pwr(player)
        upsert_player_sync(player)

    log.info("Seeded %d players into the database.", len(players))
    return len(players)


if __name__ == "__main__":
    count = seed_all()
    print(f"✅ Seeded {count} players.")
