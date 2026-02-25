"""
ParlayWars v3 — Performance Tracker
Date: 2026-02-25

Tracks:
  - Total P/L
  - ROI%
  - Win rate
  - Current streak
  - Max drawdown
  - Bankroll over time (for charting)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.logger import get_logger

log = get_logger(__name__)


class PerformanceTracker:
    """Tracks paper-trading performance statistics."""

    def __init__(self) -> None:
        self._bets: List[Dict[str, Any]] = []
        self._bankroll_history: List[Tuple[str, float]] = []  # (timestamp, balance)

    def record_bet(
        self,
        bet_id: int,
        stake: float,
        profit_loss: float,
        won: bool,
        timestamp: str,
        engine: str,
        confidence: float,
    ) -> None:
        """Record a settled bet."""
        self._bets.append({
            "bet_id": bet_id,
            "stake": stake,
            "profit_loss": profit_loss,
            "won": won,
            "timestamp": timestamp,
            "engine": engine,
            "confidence": confidence,
        })

    def record_balance(self, timestamp: str, balance: float) -> None:
        """Record a bankroll data point for the chart."""
        self._bankroll_history.append((timestamp, balance))

    def total_pl(self) -> float:
        """Sum of all P/L."""
        return round(sum(b["profit_loss"] for b in self._bets), 2)

    def win_rate(self) -> float:
        """Fraction of bets won."""
        if not self._bets:
            return 0.0
        wins = sum(1 for b in self._bets if b["won"])
        return round(wins / len(self._bets), 4)

    def current_streak(self) -> int:
        """
        Current win/loss streak.
        Positive = win streak length. Negative = loss streak length.
        """
        if not self._bets:
            return 0
        streak_type = self._bets[-1]["won"]
        count = 0
        for b in reversed(self._bets):
            if b["won"] == streak_type:
                count += 1
            else:
                break
        return count if streak_type else -count

    def max_drawdown(self) -> float:
        """
        Maximum drawdown: largest peak-to-trough drop in bankroll.
        Returns as an absolute dollar amount (positive number).
        """
        if not self._bankroll_history:
            return 0.0
        balances = [b for _, b in self._bankroll_history]
        peak = balances[0]
        max_dd = 0.0
        for b in balances:
            if b > peak:
                peak = b
            dd = peak - b
            if dd > max_dd:
                max_dd = dd
        return round(max_dd, 2)

    def roi(self, starting_bankroll: float) -> float:
        """ROI% relative to starting bankroll."""
        if starting_bankroll == 0:
            return 0.0
        return round(self.total_pl() / starting_bankroll * 100.0, 2)

    def summary(self, starting_bankroll: float = 1000.0) -> Dict[str, Any]:
        """Return a full performance summary dict."""
        return {
            "total_bets": len(self._bets),
            "total_pl": self.total_pl(),
            "win_rate": self.win_rate(),
            "current_streak": self.current_streak(),
            "max_drawdown": self.max_drawdown(),
            "roi_pct": self.roi(starting_bankroll),
        }

    def bankroll_chart_data(self) -> List[Dict[str, Any]]:
        """Return bankroll history as a list of {ts, balance} dicts for charting."""
        return [{"ts": ts, "balance": b} for ts, b in self._bankroll_history]

    def pl_by_day(self) -> Dict[str, float]:
        """Return P/L grouped by date (YYYY-MM-DD)."""
        daily: Dict[str, float] = {}
        for bet in self._bets:
            date = str(bet["timestamp"])[:10]
            daily[date] = daily.get(date, 0.0) + bet["profit_loss"]
        return {k: round(v, 2) for k, v in sorted(daily.items())}

    def drawdown_chart_data(self) -> List[Dict[str, Any]]:
        """
        Return bankroll history annotated with drawdown values for chart shading.
        Each point: {ts, balance, peak, drawdown, drawdown_pct}
        """
        if not self._bankroll_history:
            return []
        result = []
        peak = self._bankroll_history[0][1]
        for ts, balance in self._bankroll_history:
            if balance > peak:
                peak = balance
            dd = round(peak - balance, 2)
            dd_pct = round(dd / peak * 100.0, 2) if peak > 0 else 0.0
            result.append({"ts": ts, "balance": balance, "peak": round(peak, 2),
                            "drawdown": dd, "drawdown_pct": dd_pct})
        return result

    def best_streak(self) -> int:
        """Longest win streak (positive number) in history."""
        if not self._bets:
            return 0
        best = cur = 0
        for b in self._bets:
            if b["won"]:
                cur += 1
                best = max(best, cur)
            else:
                cur = 0
        return best

    def worst_streak(self) -> int:
        """Longest loss streak (returned as a negative number) in history."""
        if not self._bets:
            return 0
        worst = cur = 0
        for b in self._bets:
            if not b["won"]:
                cur += 1
                worst = max(worst, cur)
            else:
                cur = 0
        return -worst

    def accuracy_by_tier(self) -> Dict[str, Dict[str, Any]]:
        """
        Win rate per confidence tier (LOCK / STRONG / LEAN / SKIP).
        Requires that bets have a 'tier' key set when recorded.
        """
        tiers: Dict[str, Dict] = {}
        for bet in self._bets:
            tier = bet.get("tier", "SKIP")
            if tier not in tiers:
                tiers[tier] = {"bets": 0, "wins": 0}
            tiers[tier]["bets"] += 1
            if bet.get("won"):
                tiers[tier]["wins"] += 1
        result = {}
        for tier, data in tiers.items():
            n = data["bets"]
            result[tier] = {
                "bets": n,
                "wins": data["wins"],
                "hit_rate": round(data["wins"] / n * 100.0, 1) if n > 0 else 0.0,
            }
        return result
        """P/L and win rate broken down by engine."""
        engines: Dict[str, Dict] = {}
        for bet in self._bets:
            eng = bet.get("engine", "UNKNOWN")
            if eng not in engines:
                engines[eng] = {"bets": 0, "wins": 0, "pl": 0.0}
            engines[eng]["bets"] += 1
            engines[eng]["pl"] += bet["profit_loss"]
            if bet["won"]:
                engines[eng]["wins"] += 1
        result = {}
        for eng, data in engines.items():
            n = data["bets"]
            result[eng] = {
                "bets": n,
                "wins": data["wins"],
                "win_rate": round(data["wins"] / n, 4) if n > 0 else 0.0,
                "pl": round(data["pl"], 2),
            }
        return result


# Module-level singleton
tracker = PerformanceTracker()
