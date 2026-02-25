"""
ParlayWars v3 — The Odds API + Optional BetsAPI Client
Date: 2026-02-25

The Odds API key: b824c5f93dc1f906c306702b7eb1f6fc
BetsAPI is optional ($10/mo) and disabled by default.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from core.cache import cache
from core.config import cfg
from core.logger import get_logger

log = get_logger(__name__)

ODDS_BASE_URL = "https://api.the-odds-api.com/v4"
BETSAPI_BASE_URL = "https://api.b365api.com"
TIMEOUT = 10.0


def _implied_prob(american_odds: int) -> float:
    """Convert American odds to implied probability."""
    if american_odds > 0:
        return 100.0 / (american_odds + 100.0)
    else:
        return abs(american_odds) / (abs(american_odds) + 100.0)


class OddsAPIClient:
    """Client for The Odds API (https://the-odds-api.com)."""

    def __init__(self) -> None:
        self._key = cfg.get("apis", "odds_api", "key", default="")
        self._enabled = cfg.get("apis", "odds_api", "enabled", default=True)
        self._client = httpx.AsyncClient(
            base_url=ODDS_BASE_URL,
            timeout=TIMEOUT,
            follow_redirects=True,
        )

    async def _get(self, path: str, params: Optional[Dict] = None) -> Optional[Any]:
        if not self._enabled or not self._key:
            return None
        cache_key = f"odds:{path}:{str(params)}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            p = params or {}
            p["apiKey"] = self._key
            resp = await self._client.get(path, params=p)
            resp.raise_for_status()
            data = resp.json()
            cache.set(cache_key, data, ttl=600)
            return data
        except Exception as exc:
            log.warning("Odds API error for %s: %s", path, exc)
        return None

    async def get_sports(self) -> List[Dict[str, Any]]:
        """Return all available sport keys."""
        data = await self._get("/sports")
        return data if isinstance(data, list) else []

    async def get_ebasketball_odds(self) -> List[Dict[str, Any]]:
        """
        Return odds for eBasketball matches.
        Searches for sport keys containing 'esports' or 'basketball'.
        """
        sports = await self.get_sports()
        esports_keys = [
            s["key"] for s in sports
            if "esport" in s.get("key", "").lower() or "ebasketball" in s.get("key", "").lower()
        ]
        results = []
        for sport_key in esports_keys[:3]:  # Limit to avoid burning API quota
            data = await self._get(f"/sports/{sport_key}/odds", params={"regions": "us", "markets": "h2h"})
            if isinstance(data, list):
                results.extend(data)
        return results

    async def get_implied_prob(self, player_a: str, player_b: str) -> Optional[float]:
        """
        Return the implied probability that player_a wins, derived from bookie odds.
        Returns None if no odds are available.
        """
        odds_list = await self.get_ebasketball_odds()
        for match in odds_list:
            home = str(match.get("home_team") or "").upper()
            away = str(match.get("away_team") or "").upper()
            if player_a.upper() in home or player_b.upper() in home:
                bookmakers = match.get("bookmakers") or []
                for bm in bookmakers:
                    markets = bm.get("markets") or []
                    for mkt in markets:
                        if mkt.get("key") == "h2h":
                            outcomes = mkt.get("outcomes") or []
                            for out in outcomes:
                                if player_a.upper() in str(out.get("name") or "").upper():
                                    price = float(out.get("price") or 0)
                                    if price != 0:
                                        return _implied_prob(int(price))
        return None

    async def close(self) -> None:
        await self._client.aclose()


class BetsAPIClient:
    """Optional BetsAPI client (disabled by default — requires $10/mo subscription)."""

    def __init__(self) -> None:
        self._token = cfg.get("apis", "betsapi", "token", default="")
        self._enabled = cfg.get("apis", "betsapi", "enabled", default=False)
        self._sport_id = cfg.get("apis", "betsapi", "sport_id", default=151)
        self._league_id = cfg.get("apis", "betsapi", "league_id", default=25067)
        self._client = httpx.AsyncClient(
            base_url=BETSAPI_BASE_URL,
            timeout=TIMEOUT,
        )

    async def get_live_events(self) -> List[Dict[str, Any]]:
        """Return live eBasketball events from BetsAPI."""
        if not self._enabled or not self._token:
            return []
        try:
            resp = await self._client.get(
                "/v2/bet365/inplay",
                params={"token": self._token, "sport_id": self._sport_id},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("results") or []
        except Exception as exc:
            log.warning("BetsAPI error: %s", exc)
        return []

    async def close(self) -> None:
        await self._client.aclose()


# Module-level singletons
odds_client = OddsAPIClient()
betsapi_client = BetsAPIClient()
