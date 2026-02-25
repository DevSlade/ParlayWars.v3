"""
ParlayWars v3 — Auto Bettor
Date: 2026-02-25

Reads engine predictions and places paper bets automatically.
Called by the APScheduler on each polling cycle.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import (
    get_bets_async,
    get_matches_async,
    log_bankroll_async,
    save_bet_async,
    settle_bet_async,
)
from core.logger import get_logger
from sim.bankroll import bankroll_manager
from sim.odds_estimator import estimate_odds, prob_to_decimal
from sim.parlay import parlay_builder
from sim.tracker import tracker

log = get_logger(__name__)


class AutoBettor:
    """
    Automatically places paper bets on upcoming matches
    based on engine predictions.
    """

    async def place_bet(
        self,
        match_id: int,
        player_a: str,
        player_b: str,
        prob_a: float,
        engine_name: str,
        confidence: float,
        tier: str,
        bookie_prob: Optional[float] = None,
    ) -> Optional[int]:
        """
        Evaluate a prediction and place a paper bet if it meets criteria.

        Returns the bet_id if placed, None otherwise.
        """
        if not bankroll_manager.should_bet(confidence):
            return None

        # Determine which player we're betting on
        if prob_a >= 0.5:
            predicted_winner = player_a
            win_prob = prob_a
        else:
            predicted_winner = player_b
            win_prob = 1.0 - prob_a

        # Estimate odds from model probability
        american_a, decimal_a, american_b, decimal_b = estimate_odds(prob_a)
        if predicted_winner == player_a:
            american_odds = american_a
            decimal_odds = decimal_a
        else:
            american_odds = american_b
            decimal_odds = decimal_b

        # Compute Kelly stake
        stake = bankroll_manager.kelly_stake(win_prob, decimal_odds)
        if stake <= 0:
            return None

        # Ensure we have enough bankroll
        if stake > bankroll_manager.balance:
            log.warning("Insufficient bankroll ($%.2f) for stake $%.2f", bankroll_manager.balance, stake)
            stake = bankroll_manager.balance * 0.05  # Emergency: bet 5%

        # Insert bet into database
        bet_id = await save_bet_async({
            "match_id": match_id,
            "bet_type": "straight",
            "stake": stake,
            "odds_american": american_odds,
            "odds_decimal": decimal_odds,
            "predicted_winner": predicted_winner,
            "engine_used": engine_name,
            "confidence": confidence,
            "tier": tier,
            "status": "pending",
        })

        # Log bankroll change (stake is reserved but not deducted until settlement)
        await log_bankroll_async(
            balance=bankroll_manager.balance,
            action=f"bet_placed:{engine_name}",
            amount=-stake,
            bet_id=bet_id,
        )

        log.info(
            "Bet placed: %s → %s | stake=$%.2f | odds=%s | engine=%s | confidence=%.1%%",
            player_a, predicted_winner, stake,
            american_odds, engine_name, confidence * 100,
        )
        return bet_id

    async def settle_match(self, match_id: int, actual_winner: str) -> None:
        """
        Settle all pending bets for a completed match.
        Updates bankroll and tracker.
        """
        bets = await get_bets_async(status="pending")
        for bet in bets:
            if bet.get("match_id") != match_id:
                continue

            stake = float(bet.get("stake") or 0)
            decimal_odds = float(bet.get("odds_decimal") or 2.0)
            predicted_winner = bet.get("predicted_winner") or ""
            won = predicted_winner == actual_winner

            if won:
                profit_loss = bankroll_manager.apply_win(stake, decimal_odds)
            else:
                profit_loss = bankroll_manager.apply_loss(stake)

            await settle_bet_async(bet["id"], actual_winner, profit_loss)
            await log_bankroll_async(
                balance=bankroll_manager.balance,
                action="bet_settled_win" if won else "bet_settled_loss",
                amount=profit_loss,
                bet_id=bet["id"],
            )

            tracker.record_bet(
                bet_id=bet["id"],
                stake=stake,
                profit_loss=profit_loss,
                won=won,
                timestamp=datetime.now(tz=timezone.utc).isoformat(),
                engine=bet.get("engine_used") or "UNKNOWN",
                confidence=float(bet.get("confidence") or 0.5),
            )
            tracker.record_balance(
                datetime.now(tz=timezone.utc).isoformat(),
                bankroll_manager.balance,
            )
            log.info(
                "Bet settled: id=%d | %s | P/L=$%.2f | bankroll=$%.2f",
                bet["id"], "WON" if won else "LOST",
                profit_loss, bankroll_manager.balance,
            )


# Module-level singleton
auto_bettor = AutoBettor()
