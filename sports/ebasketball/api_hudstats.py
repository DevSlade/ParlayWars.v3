"""
ParlayWars v3 — HudStats API Client
Date: 2026-02-25

HudStats is the FREE backend for h2hggl.com.
Base: https://api-h2h.hudstats.com/v1
No API key required. Uses Referer + Origin headers.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import httpx

from core.cache import cache
from core.logger import get_logger

log = get_logger(__name__)

BASE_URL = "https://api-h2h.hudstats.com/v1"
HEADERS = {
    "Referer": "https://h2hggl.com/",
    "Origin": "https://h2hggl.com",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; ParlayWarsBot/3.0)",
}
TIMEOUT = 10.0  # seconds


class HudStatsClient:
    """
    Async HTTP client for the HudStats API.
    All responses are cached to avoid hammering the free endpoint.
    """

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers=HEADERS,
            timeout=TIMEOUT,
            follow_redirects=True,
        )

    async def _get(self, path: str, params: Optional[Dict] = None) -> Optional[Any]:
        """
        Perform a GET request. Returns parsed JSON or None on failure.
        Uses cache to avoid redundant requests.
        """
        cache_key = f"hudstats:{path}:{str(params)}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            resp = await self._client.get(path, params=params or {})
            resp.raise_for_status()
            data = resp.json()
            cache.set(cache_key, data, ttl=300)
            return data
        except httpx.HTTPStatusError as exc:
            log.warning("HudStats HTTP error %s for %s: %s", exc.response.status_code, path, exc)
        except Exception as exc:
            log.warning("HudStats request failed for %s: %s", path, exc)
        return None

    async def get_all_players(self) -> List[Dict[str, Any]]:
        """
        Fetch all player stats from the /participant/nba endpoint and parse
        them via ``sports.ebasketball.parser.parse_hudstats_response``.

        Returns a list of player dicts ready for the database.
        This is the sole source of truth for player data — no static files.
        """
        from sports.ebasketball.parser import parse_hudstats_response  # avoid circular import
        data = await self._get("/participant/nba")
        return parse_hudstats_response(data)

    async def get_live_matches(self) -> List[Dict[str, Any]]:
        """Fetch currently live matches."""
        data = await self._get("/matches/live")
        if data is None:
            return []
        matches_raw = data.get("matches") or data.get("data") or (data if isinstance(data, list) else [])
        return [self._map_match(m, "live") for m in matches_raw if isinstance(m, dict)]

    async def get_scheduled_matches(self) -> List[Dict[str, Any]]:
        """Fetch upcoming scheduled matches."""
        data = await self._get("/schedule")
        if data is None:
            # Try alternate endpoint
            data = await self._get("/matches/upcoming")
        if data is None:
            return []
        matches_raw = data.get("matches") or data.get("schedule") or (data if isinstance(data, list) else [])
        return [self._map_match(m, "scheduled") for m in matches_raw if isinstance(m, dict)]

    async def get_h2h(self, player_a: str, player_b: str) -> Optional[Dict[str, Any]]:
        """Fetch H2H data for two players."""
        # Try various endpoint patterns
        data = await self._get(f"/h2h/{player_a.lower()}/{player_b.lower()}")
        if data is None:
            data = await self._get("/h2h", params={"player1": player_a, "player2": player_b})
        if data is None:
            return None
        h2h = data.get("h2h") or data if isinstance(data, dict) else None
        if h2h is None:
            return None
        return {
            "player_a": player_a,
            "player_b": player_b,
            "a_wins": int(h2h.get("player1_wins") or h2h.get("a_wins") or 0),
            "b_wins": int(h2h.get("player2_wins") or h2h.get("b_wins") or 0),
            "total": int(h2h.get("total") or 0),
            "avg_margin": float(h2h.get("avg_margin") or 0.0),
        }

    def _map_match(self, raw: Dict[str, Any], default_status: str = "scheduled") -> Dict[str, Any]:
        """Normalise a HudStats match record to our match schema."""
        players = raw.get("players") or raw.get("participants") or []
        player_a = player_b = "UNKNOWN"
        score_a = score_b = None
        if len(players) >= 2:
            player_a = str(players[0].get("nickname") or players[0].get("name") or "P1").upper()
            player_b = str(players[1].get("nickname") or players[1].get("name") or "P2").upper()
            score_a = players[0].get("score")
            score_b = players[1].get("score")

        status_raw = str(raw.get("status") or default_status).lower()
        if "live" in status_raw or "ongoing" in status_raw:
            status = "live"
        elif "finish" in status_raw or "complet" in status_raw or "done" in status_raw:
            status = "completed"
        else:
            status = "scheduled"

        winner = raw.get("winner") or raw.get("winner_name")
        if winner:
            winner = str(winner).upper()

        return {
            "sport": "ebasketball",
            "player_a": player_a,
            "player_b": player_b,
            "winner": winner,
            "score_a": int(score_a) if score_a is not None else None,
            "score_b": int(score_b) if score_b is not None else None,
            "match_date": raw.get("start_time") or raw.get("date") or raw.get("scheduled_at"),
            "source": "hudstats",
            "api_match_id": str(raw.get("id") or raw.get("match_id") or ""),
            "status": status,
        }

    async def close(self) -> None:
        await self._client.aclose()


# Module-level singleton
hudstats_client = HudStatsClient()
