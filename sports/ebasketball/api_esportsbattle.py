"""
ParlayWars v3 — ESportsBattle API Client
Date: 2026-02-25

Base: https://basketball.esportsbattle.com/api
No API key required.
Secondary source for tournament/match structure.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from core.cache import cache
from core.logger import get_logger

log = get_logger(__name__)

BASE_URL = "https://basketball.esportsbattle.com/api"
HEADERS = {
    "Referer": "https://basketball.esportsbattle.com/en/schedule",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; ParlayWarsBot/3.0)",
}
TIMEOUT = 10.0


class ESportsBattleClient:
    """Async HTTP client for ESportsBattle API."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers=HEADERS,
            timeout=TIMEOUT,
            follow_redirects=True,
        )

    async def _get(self, path: str, params: Optional[Dict] = None) -> Optional[Any]:
        """Cached GET request."""
        cache_key = f"esb:{path}:{str(params)}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            resp = await self._client.get(path, params=params or {})
            resp.raise_for_status()
            data = resp.json()
            cache.set(cache_key, data, ttl=120)
            return data
        except Exception as exc:
            log.warning("ESportsBattle request failed for %s: %s", path, exc)
        return None

    async def get_tournaments(self) -> List[Dict[str, Any]]:
        """Return list of active tournaments."""
        data = await self._get("/tournaments")
        if data is None:
            return []
        tournaments = data.get("data") or data.get("tournaments") or (data if isinstance(data, list) else [])
        return [t for t in tournaments if isinstance(t, dict)]

    async def get_matches(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return matches, optionally filtered by status (live, scheduled)."""
        params = {}
        if status:
            params["status"] = status
        data = await self._get("/matches", params=params)
        if data is None:
            return []
        matches_raw = data.get("data") or data.get("matches") or (data if isinstance(data, list) else [])
        return [self._map_match(m) for m in matches_raw if isinstance(m, dict)]

    async def get_live_matches(self) -> List[Dict[str, Any]]:
        """Convenience method for live matches."""
        data = await self._get("/matches", params={"status": "live"})
        if data is None:
            return []
        matches_raw = data.get("data") or data.get("matches") or (data if isinstance(data, list) else [])
        return [self._map_match(m) for m in matches_raw if isinstance(m, dict)]

    def _map_match(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalise an ESportsBattle match to our schema."""
        home = raw.get("home") or raw.get("home_team") or {}
        away = raw.get("away") or raw.get("away_team") or {}
        player_a = str(home.get("name") or home.get("nickname") or "HOME").upper()
        player_b = str(away.get("name") or away.get("nickname") or "AWAY").upper()

        score_a = home.get("score") or raw.get("home_score")
        score_b = away.get("score") or raw.get("away_score")

        status_raw = str(raw.get("status") or "scheduled").lower()
        if "live" in status_raw:
            status = "live"
        elif any(k in status_raw for k in ("finish", "complete", "done", "ended")):
            status = "completed"
        else:
            status = "scheduled"

        winner = None
        if status == "completed":
            if score_a is not None and score_b is not None:
                winner = player_a if int(score_a) > int(score_b) else player_b

        return {
            "sport": "ebasketball",
            "player_a": player_a,
            "player_b": player_b,
            "winner": winner,
            "score_a": int(score_a) if score_a is not None else None,
            "score_b": int(score_b) if score_b is not None else None,
            "match_date": raw.get("start_time") or raw.get("scheduled_at") or raw.get("date"),
            "source": "esportsbattle",
            "api_match_id": f"esb_{raw.get('id') or raw.get('match_id') or ''}",
            "status": status,
        }

    async def close(self) -> None:
        await self._client.aclose()


# Module-level singleton
esportsbattle_client = ESportsBattleClient()
