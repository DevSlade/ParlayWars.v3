"""
ParlayWars v3 — Abstract Sport Adapter
Date: 2026-02-25
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseSportAdapter(ABC):
    """
    Abstract interface that every sport integration must implement.
    """

    @abstractmethod
    async def get_live(self) -> List[Dict[str, Any]]:
        """Return list of currently live matches."""

    @abstractmethod
    async def get_upcoming(self) -> List[Dict[str, Any]]:
        """Return list of upcoming scheduled matches."""

    @abstractmethod
    async def get_player_stats(self, name: str) -> Optional[Dict[str, Any]]:
        """Return stats dict for a single player, or None if not found."""

    @abstractmethod
    async def get_all_players(self) -> List[Dict[str, Any]]:
        """Return all known players with their stats."""

    @abstractmethod
    async def get_h2h(self, player_a: str, player_b: str) -> Optional[Dict[str, Any]]:
        """Return head-to-head record between two players, or None."""

    @abstractmethod
    async def get_odds(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Return bookie odds for a match, or None if unavailable."""
