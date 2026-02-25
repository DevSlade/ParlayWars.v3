"""
ParlayWars v3 — Database Bootstrap (Live API)
Date: 2026-02-25

Fetches ALL player data live from the HudStats API and populates the
SQLite database.  There is NO static seed file — the API is the data source.

Usage:
    python scripts/seed_database.py              # Bootstrap / refresh from API
    python scripts/seed_database.py --force      # Force re-upsert even if DB is populated
"""
from __future__ import annotations

import asyncio
import sys
import os

# Allow running from repo root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import init_db_sync, upsert_player_sync
from core.logger import setup_logging, get_logger
from engines.elo import DEFAULT_ELO
from engines.ratings import compute_pwr

log = get_logger(__name__)


def _elo_from_win_pct(win_pct: float, rank: int) -> float:
    """
    Estimate a starting ELO from overall win percentage and rank.
    Range: ~1100 (≤19% WR) to ~2000 (≥73% WR).
    """
    elo = DEFAULT_ELO + (win_pct - 50.0) * 10.0
    # Small rank bonus for proven top players
    if rank <= 10:
        elo += 50.0
    elif rank <= 25:
        elo += 25.0
    return round(max(1100.0, min(2000.0, elo)), 1)


async def _fetch_players() -> list:
    """Fetch all players from the HudStats API and return parsed player dicts."""
    from sports.ebasketball.api_hudstats import HudStatsClient

    client = HudStatsClient()
    try:
        players = await client.get_all_players()
    finally:
        await client.close()
    return players


def bootstrap_from_api(force: bool = False) -> int:
    """
    Bootstrap the player database from the live HudStats API.

    Steps:
      1. Call ``GET /participant/nba`` via HudStatsClient
      2. Parse the response with ``parse_hudstats_response``
      3. Compute starting ELO and PWR ratings
      4. Upsert all players into SQLite

    Args:
        force: If True, upsert all players even if the database is already
               populated (useful for a full refresh).

    Returns:
        Number of players written to the database.
    """
    setup_logging()
    init_db_sync()

    from core.database import get_all_players_sync

    if not force:
        existing = get_all_players_sync()
        if existing:
            log.info(
                "Database already has %d players — skipping bootstrap "
                "(use --force to refresh).",
                len(existing),
            )
            return len(existing)

    log.info("Fetching players from HudStats API...")
    players = asyncio.run(_fetch_players())

    if not players:
        log.error(
            "HudStats API returned no players. "
            "Check connectivity and try again later."
        )
        return 0

    log.info("Received %d players from API. Computing ELO + PWR...", len(players))
    for i, player in enumerate(players):
        # If the API didn't supply a rank, use list position
        if not player.get("rank") or player["rank"] == 999:
            player["rank"] = i + 1

        player["elo"] = _elo_from_win_pct(
            float(player.get("win_pct") or 50.0),
            int(player.get("rank") or 83),
        )
        player["pwr_rating"] = compute_pwr(player)
        upsert_player_sync(player)

    log.info("Bootstrapped %d players from HudStats API.", len(players))
    return len(players)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Bootstrap player DB from HudStats API")
    ap.add_argument("--force", action="store_true", help="Re-upsert even if DB is populated")
    args = ap.parse_args()

    count = bootstrap_from_api(force=args.force)
    print(f"✅ Bootstrapped {count} players from HudStats API.")
