"""
ParlayWars v3 — Dynamic ELO Rating System
Date: 2026-02-25

Chess-style ELO with adaptive K-factor:
  - K=40  for new players  (< 30 games)
  - K=28  for normal players
  - K=20  for veterans     (> 2000 games)
  - K boosted ×1.5 after inactivity (> 14 days since last game)
"""
from __future__ import annotations
import math
from datetime import datetime, timezone
from typing import Dict, Optional

from core.logger import get_logger

log = get_logger(__name__)

# Starting ELO for all new players
DEFAULT_ELO: float = 1500.0


def expected_score(rating_a: float, rating_b: float) -> float:
    """
    Standard ELO expected score for player A vs player B.
    Returns the probability that A wins (0-1).
    """
    return 1.0 / (1.0 + math.pow(10.0, (rating_b - rating_a) / 400.0))


def k_factor(total_games: int, days_inactive: int = 0) -> float:
    """
    Determine the K-factor based on player experience and inactivity.

    Args:
        total_games: Total career matches played.
        days_inactive: Days since the player's last recorded match.

    Returns:
        K-factor as a float.
    """
    if total_games < 30:
        k = 40.0   # New player — high volatility
    elif total_games > 2000:
        k = 20.0   # Veteran — stable rating
    else:
        k = 28.0   # Normal player

    # Inactivity boost — rating is more volatile after a break
    if days_inactive > 14:
        k *= 1.5

    return k


def update_elos(
    elo_a: float,
    elo_b: float,
    winner: str,
    player_a: str,
    player_b: str,
    games_a: int = 100,
    games_b: int = 100,
    days_inactive_a: int = 0,
    days_inactive_b: int = 0,
) -> tuple[float, float]:
    """
    Update ELO ratings after a match result.

    Args:
        elo_a: Current ELO of player A.
        elo_b: Current ELO of player B.
        winner: Name of the winning player.
        player_a: Name of player A.
        player_b: Name of player B.
        games_a: Total games played by player A.
        games_b: Total games played by player B.
        days_inactive_a: Days since player A last played.
        days_inactive_b: Days since player B last played.

    Returns:
        (new_elo_a, new_elo_b)
    """
    ea = expected_score(elo_a, elo_b)
    eb = 1.0 - ea

    sa = 1.0 if winner == player_a else 0.0
    sb = 1.0 - sa

    ka = k_factor(games_a, days_inactive_a)
    kb = k_factor(games_b, days_inactive_b)

    new_a = elo_a + ka * (sa - ea)
    new_b = elo_b + kb * (sb - eb)

    log.debug(
        "ELO update: %s %.1f→%.1f | %s %.1f→%.1f",
        player_a, elo_a, new_a,
        player_b, elo_b, new_b,
    )
    return new_a, new_b


class EloTracker:
    """
    Tracks ELO ratings for a pool of players in memory.
    Synchronises back to the database via core.database helpers.
    """

    def __init__(self) -> None:
        self._ratings: Dict[str, float] = {}
        self._games: Dict[str, int] = {}
        self._last_played: Dict[str, Optional[datetime]] = {}

    def load_player(self, name: str, elo: float, total_games: int, last_played: Optional[str] = None) -> None:
        """Register a player's current ELO and game count."""
        self._ratings[name] = elo
        self._games[name] = total_games
        if last_played:
            try:
                self._last_played[name] = datetime.fromisoformat(last_played)
            except ValueError:
                self._last_played[name] = None
        else:
            self._last_played[name] = None

    def get_elo(self, name: str) -> float:
        """Return current ELO (default 1500 for unknown players)."""
        return self._ratings.get(name, DEFAULT_ELO)

    def get_expected(self, player_a: str, player_b: str) -> float:
        """Return ELO expected score (win probability) for player A."""
        return expected_score(self.get_elo(player_a), self.get_elo(player_b))

    def record_result(self, player_a: str, player_b: str, winner: str) -> tuple[float, float]:
        """Update ELO ratings after a match and return (new_elo_a, new_elo_b)."""
        now = datetime.now(tz=timezone.utc)

        def days_since(name: str) -> int:
            last = self._last_played.get(name)
            if last is None:
                return 0
            diff = now - last if last.tzinfo else now - last.replace(tzinfo=timezone.utc)
            return max(0, diff.days)

        new_a, new_b = update_elos(
            elo_a=self.get_elo(player_a),
            elo_b=self.get_elo(player_b),
            winner=winner,
            player_a=player_a,
            player_b=player_b,
            games_a=self._games.get(player_a, 100),
            games_b=self._games.get(player_b, 100),
            days_inactive_a=days_since(player_a),
            days_inactive_b=days_since(player_b),
        )

        self._ratings[player_a] = new_a
        self._ratings[player_b] = new_b
        self._last_played[player_a] = now
        self._last_played[player_b] = now
        self._games[player_a] = self._games.get(player_a, 0) + 1
        self._games[player_b] = self._games.get(player_b, 0) + 1

        return new_a, new_b

    def all_ratings(self) -> Dict[str, float]:
        """Return a copy of all current ELO ratings."""
        return dict(self._ratings)


# Module-level singleton ELO tracker
elo_tracker = EloTracker()
