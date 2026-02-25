"""
ParlayWars v3 — Seed TSV Parser
Date: 2026-02-25

Reads data/seed/players_seed.tsv and returns a list of player dicts
ready to be inserted into the database.
"""
from __future__ import annotations

import csv
import os
from typing import Any, Dict, List, Optional

from core.config import cfg
from core.logger import get_logger
from sports.ebasketball.metrics import compute_all_metrics

log = get_logger(__name__)

DEFAULT_TSV_PATH = "data/seed/players_seed.tsv"


def parse_seed_file(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Parse the 166-player seed TSV file.

    Columns: rank, name, win_pct, recent_win_pct, total_games, wins, losses,
             form_1 through form_10

    Returns:
        List of player dicts ready for the database.
    """
    tsv_path = path or cfg.get("seed", "tsv_path", default=DEFAULT_TSV_PATH)
    if not os.path.exists(tsv_path):
        log.error("Seed file not found at %s", tsv_path)
        return []

    players: List[Dict[str, Any]] = []

    with open(tsv_path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            try:
                # Parse form columns
                form = []
                for i in range(1, 11):
                    val = row.get(f"form_{i}", "").strip().upper()
                    if val in ("W", "L"):
                        form.append(val)

                total_games = int(row.get("total_games") or 0)
                wins = int(row.get("wins") or 0)
                losses = int(row.get("losses") or total_games - wins)
                win_pct = float(row.get("win_pct") or 50.0)
                recent_win_pct = float(row.get("recent_win_pct") or win_pct)

                player: Dict[str, Any] = {
                    "name": str(row.get("name") or "UNKNOWN").strip().upper(),
                    "sport": "ebasketball",
                    "rank": int(row.get("rank") or 999),
                    "elo": 1500.0,          # Will be computed later
                    "pwr_rating": 50.0,     # Will be computed later
                    "win_pct": win_pct,
                    "recent_win_pct": recent_win_pct,
                    "total_games": total_games,
                    "wins": wins,
                    "losses": losses,
                    "form": form,
                    # Advanced stats — seeded with league-average values
                    "avg_points": 45.0 + (win_pct - 50.0) * 0.3,
                    "avg_fg_pct": 0.42 + (win_pct - 50.0) * 0.001,
                    "avg_reb": 8.0,
                    "avg_ast": 5.0,
                    "avg_stl": 1.5,
                    "avg_blk": 0.5,
                    "avg_tov": max(1.0, 4.0 - (win_pct - 50.0) * 0.02),
                }

                # Compute novel metrics
                metrics = compute_all_metrics(player)
                player.update(metrics)

                players.append(player)

            except (ValueError, KeyError) as exc:
                log.warning("Skipping malformed seed row %s: %s", row.get("name"), exc)

    log.info("Parsed %d players from seed file %s.", len(players), tsv_path)
    return players
