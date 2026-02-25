"""
ParlayWars v3 — Parlay Builder
Date: 2026-02-25

Builds multi-leg parlays from individual predictions.
Each leg must have min_edge >= min_edge_per_leg (default 3%).
Maximum legs: max_parlay_legs (default 4).

Parlay odds: product of decimal odds of all legs.
Parlay probability: product of individual win probabilities
  (adjusted for correlation via a correlation_factor).
"""
from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Tuple

from core.config import cfg
from core.logger import get_logger
from sim.odds_estimator import edge, prob_to_decimal

log = get_logger(__name__)

# Correlation adjustment factor: parlays are slightly correlated in eBasketball
# (same players feature in multiple games on the same day)
CORRELATION_FACTOR = 0.95  # conservative 5% correlation adjustment


class ParlayBuilder:
    """Constructs and validates parlays from individual bet legs."""

    def __init__(self) -> None:
        sim_cfg = cfg.get("simulation", default={})
        self._max_legs: int = int(sim_cfg.get("max_parlay_legs", 4))
        self._min_edge: float = float(sim_cfg.get("min_edge_per_leg", 0.03))

    def build_parlay(
        self,
        legs: List[Dict[str, Any]],
        bookie_probs: Optional[List[float]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Build a parlay from a list of legs.

        Args:
            legs: List of dicts, each with keys:
                  {player_a, player_b, predicted_winner, prob_a, match_id}
            bookie_probs: List of bookie implied probs for each leg (same order as legs).
                          If None, we assume 0.5 (no edge filter applied strictly).

        Returns:
            Parlay dict or None if legs don't meet criteria.
        """
        if not legs or len(legs) < 2:
            return None

        # Cap at max legs
        legs = legs[:self._max_legs]

        if bookie_probs is None:
            bookie_probs = [0.5] * len(legs)

        valid_legs = []
        for leg, bookie_p in zip(legs, bookie_probs):
            prob = float(leg.get("prob_a") if leg.get("predicted_winner") == leg.get("player_a") else 1 - leg.get("prob_a", 0.5))
            leg_edge = edge(prob, bookie_p)
            if leg_edge >= self._min_edge:
                valid_legs.append((leg, prob, leg_edge))

        if len(valid_legs) < 2:
            log.debug("Not enough valid parlay legs (need ≥2 with edge ≥%.1f%%)", self._min_edge * 100)
            return None

        # Compute combined parlay probability with correlation adjustment
        combined_prob = 1.0
        for _, prob, _ in valid_legs:
            combined_prob *= prob * CORRELATION_FACTOR
        # Normalise for over-adjustment
        combined_prob = min(combined_prob / (CORRELATION_FACTOR ** (len(valid_legs) - 1)), 0.99)

        # Compute combined decimal odds (product of individual decimal odds)
        combined_decimal = 1.0
        for _, prob, _ in valid_legs:
            combined_decimal *= prob_to_decimal(prob)

        return {
            "legs": [
                {
                    "match_id": l.get("match_id"),
                    "player_a": l.get("player_a"),
                    "player_b": l.get("player_b"),
                    "predicted_winner": l.get("predicted_winner"),
                    "prob": p,
                    "edge": e,
                    "decimal_odds": prob_to_decimal(p),
                }
                for l, p, e in valid_legs
            ],
            "combined_prob": round(combined_prob, 4),
            "combined_decimal_odds": round(combined_decimal, 4),
            "n_legs": len(valid_legs),
        }

    def validate_parlay(self, parlay: Dict[str, Any]) -> bool:
        """Return True if the parlay meets all quality thresholds."""
        if parlay.get("n_legs", 0) < 2:
            return False
        if parlay.get("combined_prob", 0) < 0.05:  # unreasonably low combined prob
            return False
        return True


# Module-level singleton
parlay_builder = ParlayBuilder()
