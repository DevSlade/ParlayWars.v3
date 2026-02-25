"""
ParlayWars v3 — eBasketball Sport Adapter
Date: 2026-02-25

Implements BaseSportAdapter for the 2K eBasketball game mode.
Aggregates data from HudStats (primary) and ESportsBattle (secondary).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.logger import get_logger
from sports.base import BaseSportAdapter
from sports.ebasketball.api_esportsbattle import esportsbattle_client
from sports.ebasketball.api_hudstats import hudstats_client
from sports.ebasketball.api_odds import odds_client
from sports.ebasketball.metrics import compute_all_metrics

log = get_logger(__name__)

# NBA team strength map for 2K team assignment advantage feature
TEAM_STRENGTH: Dict[str, int] = {
    "Boston Celtics": 85, "Milwaukee Bucks": 84, "Oklahoma City Thunder": 84,
    "Denver Nuggets": 83, "Phoenix Suns": 82, "Minnesota Timberwolves": 81,
    "New York Knicks": 81, "Philadelphia 76ers": 81, "Los Angeles Lakers": 80,
    "Dallas Mavericks": 80, "Golden State Warriors": 80, "Cleveland Cavaliers": 80,
    "Miami Heat": 78, "Sacramento Kings": 78, "Indiana Pacers": 77,
    "Los Angeles Clippers": 77, "New Orleans Pelicans": 77, "Orlando Magic": 77,
    "Memphis Grizzlies": 76, "Chicago Bulls": 76, "Atlanta Hawks": 76,
    "Houston Rockets": 76, "Toronto Raptors": 75, "Brooklyn Nets": 74,
    "San Antonio Spurs": 74, "Utah Jazz": 73, "Portland Trail Blazers": 73,
    "Charlotte Hornets": 72, "Washington Wizards": 71, "Detroit Pistons": 71,
}


class EBasketballAdapter(BaseSportAdapter):
    """
    eBasketball data adapter.
    Tries HudStats first, falls back to ESportsBattle, then cached data.
    """

    async def get_live(self) -> List[Dict[str, Any]]:
        """Return live matches from HudStats + ESportsBattle, deduplicated."""
        try:
            hudstats_live = await hudstats_client.get_live_matches()
        except Exception as exc:
            log.warning("HudStats live fetch failed: %s", exc)
            hudstats_live = []
        try:
            esb_live = await esportsbattle_client.get_live_matches()
        except Exception as exc:
            log.warning("ESportsBattle live fetch failed: %s", exc)
            esb_live = []

        # Deduplicate by player pair
        seen = set()
        matches: List[Dict[str, Any]] = []
        for m in hudstats_live + esb_live:
            key = tuple(sorted([m.get("player_a", ""), m.get("player_b", "")]))
            if key not in seen:
                seen.add(key)
                matches.append(m)
        return matches

    async def get_upcoming(self) -> List[Dict[str, Any]]:
        """Return upcoming scheduled matches."""
        try:
            matches = await hudstats_client.get_scheduled_matches()
            if matches:
                return matches
        except Exception as exc:
            log.warning("HudStats schedule fetch failed: %s", exc)

        try:
            return await esportsbattle_client.get_matches(status="scheduled")
        except Exception as exc:
            log.warning("ESportsBattle schedule fetch failed: %s", exc)
        return []

    async def get_player_stats(self, name: str) -> Optional[Dict[str, Any]]:
        """Return live stats for a single player by name."""
        all_players = await self.get_all_players()
        for p in all_players:
            if p.get("name", "").upper() == name.upper():
                return p
        return None

    async def get_all_players(self) -> List[Dict[str, Any]]:
        """Return all players with computed metrics."""
        try:
            players = await hudstats_client.get_all_players()
            if players:
                # Compute novel metrics for API-fetched players
                for p in players:
                    metrics = compute_all_metrics(p)
                    p.update(metrics)
                return players
        except Exception as exc:
            log.warning("HudStats all-players fetch failed: %s", exc)
        return []

    async def get_h2h(self, player_a: str, player_b: str) -> Optional[Dict[str, Any]]:
        """Return H2H data from HudStats."""
        try:
            return await hudstats_client.get_h2h(player_a, player_b)
        except Exception as exc:
            log.warning("H2H fetch failed: %s", exc)
        return None

    async def get_odds(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Return bookie odds for a match (stub — uses The Odds API)."""
        try:
            # Odds API doesn't easily map to our match IDs,
            # so return the full list and let callers filter
            all_odds = await odds_client.get_ebasketball_odds()
            for o in all_odds:
                if str(o.get("id") or "") == match_id:
                    return o
        except Exception as exc:
            log.warning("Odds fetch failed: %s", exc)
        return None


# Module-level singleton
ebasketball_adapter = EBasketballAdapter()
