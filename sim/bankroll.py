"""
ParlayWars v3 — Bankroll Management
Date: 2026-02-25

Implements Kelly Criterion (default: quarter-Kelly) and flat-bet sizing.

Kelly formula:
    f = (p * (decimal_odds - 1) - (1 - p)) / (decimal_odds - 1)
    stake = kelly_fraction * f * bankroll

Where:
    p            = model probability of winning
    decimal_odds = decimal format odds offered
    kelly_fraction = 0.25 (quarter-Kelly default)
"""
from __future__ import annotations
import math
from typing import Optional

from core.config import cfg
from core.logger import get_logger

log = get_logger(__name__)


class BankrollManager:
    """
    Manages the paper-trading bankroll and bet sizing.
    """

    def __init__(self, starting_balance: Optional[float] = None) -> None:
        sim_cfg = cfg.get("simulation", default={})
        self._balance: float = float(starting_balance or sim_cfg.get("starting_bankroll", 1000.0))
        self._kelly_fraction: float = float(sim_cfg.get("kelly_fraction", 0.25))
        self._flat_bet: float = float(sim_cfg.get("flat_bet_amount", 10.0))
        self._min_confidence: float = float(sim_cfg.get("min_confidence", 0.52))
        self._starting_balance: float = self._balance
        log.info("Bankroll initialised: $%.2f (Kelly fraction: %.2f)", self._balance, self._kelly_fraction)

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def starting_balance(self) -> float:
        return self._starting_balance

    def kelly_stake(self, prob: float, decimal_odds: float) -> float:
        """
        Compute the Kelly-optimal bet size for this wager.

        Args:
            prob: Model win probability.
            decimal_odds: Decimal format odds offered by bookie/estimator.

        Returns:
            Recommended stake in dollars (may be 0 if no edge).
        """
        b = decimal_odds - 1.0          # net profit per unit if win
        q = 1.0 - prob                  # probability of losing
        if b <= 0:
            return 0.0
        kelly_fraction_full = (prob * b - q) / (b + 1e-9)
        if kelly_fraction_full <= 0:
            return 0.0   # No edge — don't bet
        stake = self._kelly_fraction * kelly_fraction_full * self._balance
        # Cap at 20% of bankroll per bet
        stake = min(stake, 0.20 * self._balance)
        # Floor at flat bet minimum
        stake = max(stake, self._flat_bet)
        return round(stake, 2)

    def flat_stake(self) -> float:
        """Return the flat-bet amount."""
        return self._flat_bet

    def should_bet(self, confidence: float) -> bool:
        """Return True if confidence meets the minimum threshold to place a bet."""
        return confidence >= self._min_confidence

    def apply_win(self, stake: float, decimal_odds: float) -> float:
        """
        Apply a winning bet result to the bankroll.

        Returns the profit.
        """
        profit = stake * (decimal_odds - 1.0)
        self._balance += profit
        return round(profit, 2)

    def apply_loss(self, stake: float) -> float:
        """
        Apply a losing bet result to the bankroll.

        Returns the loss (negative).
        """
        self._balance -= stake
        return -round(stake, 2)

    def set_balance(self, balance: float) -> None:
        """Directly set the bankroll balance (e.g. loaded from DB)."""
        self._balance = balance

    def roi(self) -> float:
        """Return the return-on-investment percentage."""
        total_wagered = self._starting_balance
        return round((self._balance - self._starting_balance) / total_wagered * 100.0, 2)


# Module-level singleton
bankroll_manager = BankrollManager()
