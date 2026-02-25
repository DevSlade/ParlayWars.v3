"""
ParlayWars v3 — eBasketball Novel Metrics
Date: 2026-02-25

Computes 7 novel metrics for each player:
  1. clutch_index       — Performance in close/important games (estimated from form + win rate)
  2. consistency_score  — How consistent win rate is (low variance = high score)
  3. upset_resistance   — How well higher-ranked players hold off upsets
  4. fade_factor        — Tendency to decline in performance over a series
  5. oqr               — Opponent Quality Rating (average rank of opponents beat)
  6. form_velocity      — Recent trend direction: rising (+1) or falling (-1)
  7. bounce_back_rate   — How often the player wins after a loss
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


def _form_list(form: Optional[List[str]]) -> List[float]:
    """Convert W/L form list to 1.0/0.0 list."""
    return [1.0 if r == "W" else 0.0 for r in (form or [])]


def clutch_index(player: Dict[str, Any]) -> float:
    """
    Clutch index: combination of recent win rate and form consistency.
    Players who win consistently under pressure score higher.
    Formula: 50 * (recent_win_rate / overall_win_rate) clamped to [0, 100]
    """
    win_pct = float(player.get("win_pct") or 50.0) / 100.0
    recent_pct = float(player.get("recent_win_pct") or win_pct * 100) / 100.0
    if win_pct <= 0:
        return 50.0
    ratio = recent_pct / (win_pct + 1e-9)
    # Scale: ratio of 1.0 → 50, 1.5 → 75, 2.0 → 100, 0.5 → 25
    score = 50.0 * ratio
    return round(max(0.0, min(100.0, score)), 2)


def consistency_score(player: Dict[str, Any]) -> float:
    """
    Consistency: how predictable (stable) a player's results are.
    Low variance in form = high consistency.
    Uses standard deviation of the form binary values scaled to 0-100.
    """
    form_vals = _form_list(player.get("form"))
    if len(form_vals) < 2:
        return 50.0
    n = len(form_vals)
    mean = sum(form_vals) / n
    variance = sum((x - mean) ** 2 for x in form_vals) / n
    std = math.sqrt(variance)
    # Max possible std for binary is 0.5 (alternating W/L)
    # Consistency: 1 - (std / 0.5) → high consistency = low std
    consistency = (1.0 - std / 0.5) * 100.0
    return round(max(0.0, min(100.0, consistency)), 2)


def upset_resistance(player: Dict[str, Any]) -> float:
    """
    Upset resistance: for higher-ranked players, how rarely they lose to underdogs.
    Approximation based on rank and win rate:
    Higher rank (lower rank number) players who maintain high win rates = high upset resistance.
    """
    rank = int(player.get("rank") or 83)  # default to median
    win_pct = float(player.get("win_pct") or 50.0)
    # Top-25 players are expected to have high win rates;
    # penalise if they underperform their rank expectations
    expected_wp = max(50.0, 80.0 - (rank - 1) * 0.2)
    ratio = win_pct / (expected_wp + 1e-9)
    score = ratio * 50.0
    return round(max(0.0, min(100.0, score)), 2)


def fade_factor(player: Dict[str, Any]) -> float:
    """
    Fade factor: how much a player's performance has declined recently.
    Positive fade = declining. Negative fade = improving.
    Computed as: recent_win_pct - overall_win_pct (scaled to 0-100)
    A score near 50 = neutral. > 50 = improving. < 50 = fading.
    """
    win_pct = float(player.get("win_pct") or 50.0)
    recent_pct = float(player.get("recent_win_pct") or win_pct)
    diff = recent_pct - win_pct   # positive = improving, negative = fading
    # Normalise: diff of ±20 maps to ±50 (100 = max improving, 0 = max fading)
    score = 50.0 + diff * 2.5
    return round(max(0.0, min(100.0, score)), 2)


def opponent_quality_rating(player: Dict[str, Any]) -> float:
    """
    OQR: Opponent Quality Rating.
    Higher-ranked (lower rank number) players face tougher opponents on average.
    We estimate OQR from rank: rank 1 opponent pool ≈ 85/100, rank 166 ≈ 40/100.
    """
    rank = int(player.get("rank") or 83)
    # Linear mapping: rank 1 → 85, rank 166 → 40
    oqr = 85.0 - (rank - 1) * (85.0 - 40.0) / 165.0
    return round(max(0.0, min(100.0, oqr)), 2)


def form_velocity(player: Dict[str, Any]) -> float:
    """
    Form velocity: trend direction of recent performance.
    Returns value in [-1, +1]:
      +1 = strongly rising (recent games better than earlier)
      -1 = strongly falling
      0  = neutral
    Uses first half vs second half of form window.
    """
    form_vals = _form_list(player.get("form"))
    if len(form_vals) < 4:
        return 0.0
    mid = len(form_vals) // 2
    # Recent half (first in list = most recent)
    recent_half = form_vals[:mid]
    older_half = form_vals[mid:]
    recent_wr = sum(recent_half) / len(recent_half)
    older_wr = sum(older_half) / len(older_half)
    velocity = recent_wr - older_wr   # in [-1, +1]
    return round(max(-1.0, min(1.0, velocity)), 3)


def bounce_back_rate(player: Dict[str, Any]) -> float:
    """
    Bounce-back rate: probability of winning after a loss.
    Counts occurrences of 'L→W' patterns in the form list.
    Returns value in [0, 1].
    """
    form_vals = _form_list(player.get("form"))
    if len(form_vals) < 2:
        return 0.5  # default
    losses_followed_by_result = 0
    bounced_back = 0
    for i in range(len(form_vals) - 1):
        if form_vals[i] == 0.0:  # was a loss
            losses_followed_by_result += 1
            if form_vals[i + 1] == 1.0:  # next result was a win
                bounced_back += 1
    if losses_followed_by_result == 0:
        return 0.5
    return round(bounced_back / losses_followed_by_result, 3)


def compute_all_metrics(player: Dict[str, Any]) -> Dict[str, float]:
    """
    Compute all 7 novel metrics for a player and return as a dict.
    """
    return {
        "clutch_index": clutch_index(player),
        "consistency_score": consistency_score(player),
        "upset_resistance": upset_resistance(player),
        "fade_factor": fade_factor(player),
        "oqr": opponent_quality_rating(player),
        "form_velocity": form_velocity(player),
        "bounce_back_rate": bounce_back_rate(player),
    }
