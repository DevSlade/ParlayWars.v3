"""
ParlayWars v3 — OSWS Bridge Client
Date: 2026-02-25

HTTP client that talks to the OSWS scraper service (default: http://localhost:8001).
Used as a drop-in replacement for the broken HudStats live/schedule endpoints.
Player data is still fetched directly from HudStats /participant/nba (which works).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from core.cache import cache
from core.config import cfg
from core.logger import get_logger

log = get_logger(__name__)

_OSWS_BASE = cfg.get("apis", "osws", "base_url", default="http://localhost:8001")
TIMEOUT = 5.0


class OSWSClient:
    """
    Async HTTP client for the OSWS scraper service.
    Falls back gracefully if OSWS is not running.
    """

    def __init__(self, base_url: str = _OSWS_BASE) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=TIMEOUT,
            follow_redirects=True,
        )

    async def _get(self, path: str) -> Optional[Any]:
        """GET request with cache; returns None on failure."""
        cache_key = f"osws:{path}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            resp = await self._client.get(path)
            resp.raise_for_status()
            data = resp.json()
            cache.set(cache_key, data, ttl=60)
            return data
        except Exception as exc:
            log.debug("OSWS request failed for %s: %s", path, exc)
        return None

    async def is_available(self) -> bool:
        """Check if the OSWS service is reachable."""
        try:
            resp = await self._client.get("/health", timeout=2.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def get_all_players(self) -> List[Dict[str, Any]]:
        """Return all players from OSWS."""
        data = await self._get("/players")
        if isinstance(data, list):
            return data
        return []

    async def get_live_matches(self) -> List[Dict[str, Any]]:
        """Return live matches from OSWS."""
        data = await self._get("/matches/live")
        if isinstance(data, list):
            return [self._map_match(m, "live") for m in data]
        return []

    async def get_scheduled_matches(self) -> List[Dict[str, Any]]:
        """Return scheduled matches from OSWS."""
        data = await self._get("/matches/scheduled")
        if isinstance(data, list):
            return [self._map_match(m, "scheduled") for m in data]
        return []

    def _map_match(self, raw: Dict[str, Any], default_status: str = "scheduled") -> Dict[str, Any]:
        """Normalise an OSWS match record to our internal match schema."""
        return {
            "sport": "ebasketball",
            "player_a": str(raw.get("player_a") or "P1").upper(),
            "player_b": str(raw.get("player_b") or "P2").upper(),
            "winner": raw.get("winner"),
            "score_a": raw.get("score_a"),
            "score_b": raw.get("score_b"),
            "match_date": raw.get("match_date"),
            "source": "osws",
            "api_match_id": f"osws_{raw.get('api_match_id') or raw.get('id') or ''}",
            "status": raw.get("status") or default_status,
        }

    async def close(self) -> None:
        await self._client.aclose()


# Module-level singleton
osws_client = OSWSClient()
