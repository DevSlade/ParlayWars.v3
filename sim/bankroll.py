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

        # ── Stop-loss / take-profit controls ────────────────────────
        self._daily_stop_loss_pct: float = float(sim_cfg.get("daily_stop_loss_pct", 0.10))
        self._weekly_stop_loss_pct: float = float(sim_cfg.get("weekly_stop_loss_pct", 0.20))
        self._take_profit_pct: float = float(sim_cfg.get("take_profit_pct", 0.15))
        self._recovery_threshold: float = float(sim_cfg.get("recovery_threshold", 0.60))
        self._resume_threshold: float = float(sim_cfg.get("resume_threshold", 0.80))
        self._daily_start_balance: float = self._balance
        self._weekly_start_balance: float = self._balance
        self._recovery_mode: bool = False
        self._betting_paused: bool = False

        log.info("Bankroll initialised: $%.2f (Kelly fraction: %.2f)", self._balance, self._kelly_fraction)

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def starting_balance(self) -> float:
        return self._starting_balance

    def kelly_stake(self, prob: float, decimal_odds: float, confidence: float = 0.0) -> float:
        """
        Compute the Kelly-optimal bet size for this wager.

        In recovery mode uses a flat 2% stake and only allows LOCK-tier bets
        (confidence >= 0.75).

        Args:
            prob:          Model win probability.
            decimal_odds:  Decimal format odds offered by bookie/estimator.
            confidence:    Model confidence (0–1); used for recovery mode gate.

        Returns:
            Recommended stake in dollars (may be 0 if no edge).
        """
        # Recovery mode: flat 2% of balance, LOCK picks only
        if self._recovery_mode:
            if confidence < 0.75:
                return 0.0
            return round(self._balance * 0.02, 2)

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
        """Return True if confidence meets the minimum threshold and betting is not paused."""
        if self._betting_paused:
            return False
        return confidence >= self._min_confidence

    def check_risk_controls(self) -> str:
        """
        Evaluate stop-loss and take-profit conditions and adjust bet sizing.

        Checks (in priority order):
          1. Daily drawdown > daily_stop_loss_pct → pause betting entirely.
          2. Weekly drawdown > weekly_stop_loss_pct → halve Kelly fraction.
          3. Daily gain > take_profit_pct → reduce Kelly fraction by 25%.
          4. Balance < starting * recovery_threshold → activate recovery mode.
          5. In recovery and balance > starting * resume_threshold → deactivate.

        Returns:
            Status string: 'DAILY_STOP_LOSS', 'WEEKLY_STOP_LOSS', 'TAKE_PROFIT',
            'RECOVERY_ACTIVATED', 'RECOVERY_RESUMED', or 'OK'.
        """
        if self._daily_start_balance > 0:
            daily_drawdown = (self._daily_start_balance - self._balance) / self._daily_start_balance
            if daily_drawdown > self._daily_stop_loss_pct:
                self._betting_paused = True
                log.warning("Daily stop-loss triggered (drawdown=%.1f%%)", daily_drawdown * 100)
                return "DAILY_STOP_LOSS"

            daily_gain = (self._balance - self._daily_start_balance) / self._daily_start_balance
            if daily_gain > self._take_profit_pct:
                self._kelly_fraction *= 0.75
                log.info("Take-profit triggered — Kelly fraction reduced to %.3f", self._kelly_fraction)
                return "TAKE_PROFIT"

        if self._weekly_start_balance > 0:
            weekly_drawdown = (self._weekly_start_balance - self._balance) / self._weekly_start_balance
            if weekly_drawdown > self._weekly_stop_loss_pct:
                self._kelly_fraction *= 0.5
                log.warning("Weekly stop-loss triggered — Kelly fraction halved to %.3f", self._kelly_fraction)
                return "WEEKLY_STOP_LOSS"

        if self._starting_balance > 0:
            balance_ratio = self._balance / self._starting_balance
            if not self._recovery_mode and balance_ratio < self._recovery_threshold:
                self._recovery_mode = True
                log.warning("Recovery mode activated (balance=$%.2f)", self._balance)
                return "RECOVERY_ACTIVATED"
            if self._recovery_mode and balance_ratio >= self._resume_threshold:
                self._recovery_mode = False
                log.info("Recovery mode deactivated (balance=$%.2f)", self._balance)
                return "RECOVERY_RESUMED"

        return "OK"

    def is_in_recovery_mode(self) -> bool:
        """Return True if the bankroll is in recovery mode (flat betting, LOCKs only)."""
        return self._recovery_mode

    def reset_daily_stats(self) -> None:
        """Reset the daily tracking baseline (call at midnight UTC)."""
        self._daily_start_balance = self._balance
        self._betting_paused = False
        log.info("Daily stats reset — new start balance: $%.2f", self._balance)

    def reset_weekly_stats(self) -> None:
        """Reset the weekly tracking baseline (call on Monday UTC)."""
        self._weekly_start_balance = self._balance
        log.info("Weekly stats reset — new start balance: $%.2f", self._balance)

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
