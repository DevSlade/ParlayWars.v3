"""
ParlayWars v3 — Odds Estimator
Date: 2026-02-25

Converts model probabilities into estimated American and decimal odds.
This simulates what a sportsbook like FanDuel would set given the model's edge.
"""
from __future__ import annotations
import math
from typing import Tuple


def prob_to_american(prob: float) -> int:
    """
    Convert a win probability to American moneyline odds.

    Args:
        prob: Win probability in (0, 1).

    Returns:
        American odds as integer (e.g., -150, +130).

    Formula:
        If prob > 0.5:  odds = -round(prob / (1 - prob) * 100)
        If prob < 0.5:  odds = +round((1 - prob) / prob * 100)
        If prob == 0.5: odds = -100
    """
    prob = max(0.001, min(0.999, prob))
    if prob > 0.5:
        return -round(prob / (1.0 - prob) * 100)
    elif prob < 0.5:
        return round((1.0 - prob) / prob * 100)
    else:
        return -100


def prob_to_decimal(prob: float) -> float:
    """
    Convert a win probability to decimal odds.

    Args:
        prob: Win probability in (0, 1).

    Returns:
        Decimal odds (e.g., 1.67, 2.30).
    """
    prob = max(0.001, min(0.999, prob))
    return round(1.0 / prob, 4)


def american_to_decimal(american: int) -> float:
    """Convert American odds to decimal format."""
    if american > 0:
        return round(american / 100.0 + 1.0, 4)
    else:
        return round(100.0 / abs(american) + 1.0, 4)


def decimal_to_implied_prob(decimal_odds: float) -> float:
    """Convert decimal odds to implied probability."""
    if decimal_odds <= 1.0:
        return 0.99
    return round(1.0 / decimal_odds, 4)


def american_to_implied_prob(american: int) -> float:
    """Convert American odds to implied probability."""
    if american > 0:
        return round(100.0 / (american + 100.0), 4)
    else:
        return round(abs(american) / (abs(american) + 100.0), 4)


def estimate_odds(prob_a: float) -> Tuple[int, float, int, float]:
    """
    Given prob_a, estimate odds for both sides.

    Returns:
        (american_a, decimal_a, american_b, decimal_b)
    """
    prob_b = 1.0 - prob_a
    return (
        prob_to_american(prob_a),
        prob_to_decimal(prob_a),
        prob_to_american(prob_b),
        prob_to_decimal(prob_b),
    )


def edge(model_prob: float, bookie_prob: float) -> float:
    """
    Calculate the edge (%) of a bet.
    edge = model_prob - bookie_implied_prob
    Positive edge = value bet.
    """
    return round(model_prob - bookie_prob, 4)
