"""
ParlayWars v3 — HudStats API Response Parser
Date: 2026-02-25

Parses the raw JSON payload from the HudStats /participant/nba endpoint
and returns a list of player dicts ready to be inserted into the database.

There is NO static seed file.  ALL player data originates from live API calls.
"""
from __future__ import annotations

from typing import Any, Dict, List

from core.logger import get_logger
from sports.ebasketball.metrics import compute_all_metrics

log = get_logger(__name__)


def _parse_form(form_raw: Any) -> List[str]:
    """
    Normalise the form/last_results field from the API into a list of 'W'/'L'
    strings (most-recent first, up to 10 entries).
    """
    if not form_raw:
        return []
    results: List[str] = []
    for r in form_raw[:10]:
        if isinstance(r, str):
            results.append("W" if r.upper() in ("W", "WIN", "1") else "L")
        elif isinstance(r, (int, float)):
            results.append("W" if int(r) == 1 else "L")
    return results


def parse_hudstats_player(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map a single player dict from the HudStats API response to our internal
    schema.  Falls back to sensible defaults for any missing fields.

    Args:
        raw: One element from the 'participants' (or root list) of the
             /participant/nba API response.

    Returns:
        Player dict ready for ``upsert_player_sync`` / ``upsert_player_async``.
    """
    name = str(
        raw.get("nickname") or raw.get("name") or raw.get("username") or "UNKNOWN"
    ).strip().upper()

    total = int(raw.get("games") or raw.get("total_games") or raw.get("matchesPlayed") or 0)
    wins = int(raw.get("wins") or raw.get("winCount") or 0)
    losses = max(0, total - wins)

    # win_pct may come back as 0-100 float or 0-1 fraction — normalise to 0-100
    raw_wr = raw.get("win_rate") or raw.get("winRate") or raw.get("win_pct")
    if raw_wr is not None:
        win_pct = float(raw_wr)
        if win_pct <= 1.0:          # fraction → percentage
            win_pct = win_pct * 100.0
    else:
        win_pct = round(wins / total * 100.0, 1) if total > 0 else 50.0

    raw_rwr = (
        raw.get("recent_win_rate")
        or raw.get("recentWinRate")
        or raw.get("last10_win_pct")
    )
    if raw_rwr is not None:
        recent_win_pct = float(raw_rwr)
        if recent_win_pct <= 1.0:
            recent_win_pct = recent_win_pct * 100.0
    else:
        recent_win_pct = win_pct

    form = _parse_form(raw.get("form") or raw.get("lastResults") or raw.get("last_results"))

    # Rank (position on the HudStats leaderboard if provided)
    rank = int(raw.get("rank") or raw.get("position") or 999)

    # Advanced stats — use API values where present, else estimate from win rate
    avg_points = float(
        raw.get("avg_points") or raw.get("avgPoints") or raw.get("avg_score")
        or (45.0 + (win_pct - 50.0) * 0.3)
    )
    avg_fg_pct = float(
        raw.get("fg_pct") or raw.get("fgPct") or raw.get("field_goal_pct")
        or (0.42 + (win_pct - 50.0) * 0.001)
    )
    avg_reb = float(raw.get("avg_reb") or raw.get("avgReb") or 8.0)
    avg_ast = float(raw.get("avg_ast") or raw.get("avgAst") or 5.0)
    avg_stl = float(raw.get("avg_stl") or raw.get("avgStl") or 1.5)
    avg_blk = float(raw.get("avg_blk") or raw.get("avgBlk") or 0.5)
    avg_tov = float(
        raw.get("avg_tov") or raw.get("avgTov")
        or max(1.0, 4.0 - (win_pct - 50.0) * 0.02)
    )

    player: Dict[str, Any] = {
        "name": name,
        "sport": "ebasketball",
        "rank": rank,
        "elo": 1500.0,          # Computed by bootstrap_players after parsing
        "pwr_rating": 50.0,     # Computed by bootstrap_players after parsing
        "win_pct": round(win_pct, 1),
        "recent_win_pct": round(recent_win_pct, 1),
        "total_games": total,
        "wins": wins,
        "losses": losses,
        "form": form,
        "avg_points": round(avg_points, 2),
        "avg_fg_pct": round(min(1.0, avg_fg_pct), 4),
        "avg_reb": round(avg_reb, 2),
        "avg_ast": round(avg_ast, 2),
        "avg_stl": round(avg_stl, 2),
        "avg_blk": round(avg_blk, 2),
        "avg_tov": round(avg_tov, 2),
    }

    # Compute novel metrics (clutch_index, form_velocity, etc.)
    player.update(compute_all_metrics(player))
    return player


def parse_hudstats_response(data: Any) -> List[Dict[str, Any]]:
    """
    Parse the full API response from ``GET /participant/nba``.

    The endpoint may return:
      - A list of player objects directly
      - A dict with a 'participants', 'data', or 'players' key containing the list

    Args:
        data: Parsed JSON from the HudStats API (dict or list).

    Returns:
        List of player dicts ready for the database.
    """
    if data is None:
        log.warning("parse_hudstats_response: received None data")
        return []

    if isinstance(data, dict):
        players_raw = (
            data.get("participants")
            or data.get("data")
            or data.get("players")
            or []
        )
    elif isinstance(data, list):
        players_raw = data
    else:
        log.warning("parse_hudstats_response: unexpected data type %s", type(data))
        return []

    players: List[Dict[str, Any]] = []
    for raw in players_raw:
        if not isinstance(raw, dict):
            continue
        try:
            players.append(parse_hudstats_player(raw))
        except Exception as exc:  # pragma: no cover
            log.warning("Skipping malformed HudStats player record: %s", exc)

    log.info("Parsed %d players from HudStats API response.", len(players))
    return players
