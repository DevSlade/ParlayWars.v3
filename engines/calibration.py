"""
ParlayWars v3 — Self-Improving AI Calibration
Date: 2026-02-25

Auto-calibration loop, Platt scaling, engine degradation detection, shadow mode.

Glossary:
  Brier Score  — mean squared error of probability predictions (lower = better).
  Platt Scaling — logistic regression post-processing to calibrate raw scores.
  Shadow Mode  — run a challenger model in parallel; promote if it beats current.
  CLV          — Closing Line Value (see engines/edge.py).
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Tuple

log = logging.getLogger(__name__)


def brier_score(predictions: List[Tuple[float, int]]) -> float:
    """
    Compute the Brier Score for a set of probability predictions.

    Brier Score = mean((predicted_prob - outcome)^2)

    Lower is better.  A perfect calibration scores 0.0; random guessing ≈ 0.25.

    Args:
        predictions: List of (predicted_prob_for_winner, outcome) tuples.
                     predicted_prob_for_winner: probability assigned to the
                     eventual winner (0–1).
                     outcome: 1 if the predicted winner actually won, 0 if not.

    Returns:
        Brier score as a float.  Returns 0.0 for empty input.
    """
    if not predictions:
        return 0.0
    total = sum((prob - outcome) ** 2 for prob, outcome in predictions)
    return round(total / len(predictions), 6)


def _logit(p: float) -> float:
    """Return log-odds of p, clamped to avoid overflow."""
    p = max(1e-7, min(1 - 1e-7, p))
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


def _log_loss(a: float, b: float, logits: List[float], outcomes: List[int]) -> float:
    """Binary cross-entropy loss for Platt scaling parameters (a, b)."""
    total = 0.0
    for logit_val, y in zip(logits, outcomes):
        p = _sigmoid(a * logit_val + b)
        p = max(1e-12, min(1 - 1e-12, p))
        total -= y * math.log(p) + (1 - y) * math.log(1 - p)
    return total / max(len(logits), 1)


def platt_scale(
    probabilities: List[float],
    outcomes: List[int],
) -> Tuple[float, float]:
    """
    Fit Platt scaling parameters (a, b) to calibrate raw probability outputs.

    Platt scaling fits a logistic regression over the log-odds (logit) of the
    raw probabilities to correct systematic over- or under-confidence.

    calibrated_p = 1 / (1 + exp(-(a * logit(p) + b)))

    Uses scipy.optimize.minimize with BFGS.  Falls back to a simple additive
    shift (a=1, b computed from mean error) if scipy is unavailable.

    Args:
        probabilities: Raw model probability outputs (0–1).
        outcomes:      1 if correct prediction, 0 otherwise. Same length.

    Returns:
        (a, b) — Platt scaling coefficients.
    """
    if len(probabilities) != len(outcomes) or not probabilities:
        return (1.0, 0.0)

    logits = [_logit(p) for p in probabilities]

    try:
        from scipy.optimize import minimize  # type: ignore

        def objective(params: List[float]) -> float:
            return _log_loss(params[0], params[1], logits, outcomes)

        result = minimize(
            objective,
            x0=[1.0, 0.0],
            method="BFGS",
            options={"maxiter": 200, "gtol": 1e-5},
        )
        a, b = float(result.x[0]), float(result.x[1])
        return (round(a, 6), round(b, 6))

    except ImportError:
        log.warning("scipy not available; using simple Platt scaling fallback.")
        # Fallback: keep slope a=1, shift b to minimise mean calibration error
        errors = []
        for logit_val, y in zip(logits, outcomes):
            p = _sigmoid(logit_val)
            errors.append(y - p)
        b = sum(errors) / len(errors) if errors else 0.0
        return (1.0, round(b, 6))

    except Exception as exc:
        log.error("Platt scaling optimisation failed: %s", exc)
        return (1.0, 0.0)


def apply_platt_scale(prob: float, a: float, b: float) -> float:
    """
    Apply pre-fitted Platt scaling parameters to a raw probability.

    calibrated_p = 1 / (1 + exp(-(a * logit(p) + b)))

    Args:
        prob: Raw model probability (0–1).
        a:    Platt scale coefficient (slope).
        b:    Platt scale coefficient (intercept / shift).

    Returns:
        Calibrated probability clamped to (0, 1).
    """
    logit_p = _logit(prob)
    calibrated = _sigmoid(a * logit_p + b)
    return round(max(0.0, min(1.0, calibrated)), 6)


def calibration_status(brier: float, prev_brier: float) -> str:
    """
    Classify the calibration health of a model engine.

    Rules:
      GOOD         — brier < 0.25 and not degrading (brier ≤ prev_brier + small tolerance)
      DRIFTING     — brier is increasing vs previous measurement
      NEEDS_RETRAIN — brier > 0.28 (performance has deteriorated significantly)

    Args:
        brier:      Current Brier score.
        prev_brier: Previous Brier score (from last calibration run).

    Returns:
        Status string: 'GOOD', 'DRIFTING', or 'NEEDS_RETRAIN'.
    """
    if brier > 0.28:
        return "NEEDS_RETRAIN"
    if brier > prev_brier + 0.005:  # more than 0.5pp increase → drifting
        return "DRIFTING"
    return "GOOD"


def rolling_accuracy(
    predictions: List[Tuple[float, int]],
    window: int = 50,
) -> float:
    """
    Compute accuracy over the most recent `window` predictions.

    A prediction is considered correct when:
      - prob > 0.5 AND outcome == 1  (predicted winner was the actual winner)
      - prob < 0.5 AND outcome == 0  (correctly faded the team)
      - prob == 0.5 is treated as a miss

    Args:
        predictions: Full list of (predicted_prob, outcome) tuples.
        window:      Number of most recent predictions to evaluate.

    Returns:
        Accuracy as a fraction (0–1).  Returns 0.0 for empty input.
    """
    if not predictions:
        return 0.0
    recent = predictions[-window:]
    if not recent:
        return 0.0
    correct = sum(
        1 for prob, outcome in recent
        if (prob > 0.5 and outcome == 1) or (prob < 0.5 and outcome == 0)
    )
    return round(correct / len(recent), 4)


def is_degraded(rolling_acc: float, threshold: float = 0.50) -> bool:
    """
    Return True if rolling accuracy has fallen below the acceptable threshold.

    A degraded engine should be retrained before placing further high-stakes bets.

    Args:
        rolling_acc: Rolling accuracy fraction (0–1).
        threshold:   Minimum acceptable accuracy (default 50%).

    Returns:
        True if the engine is performing below threshold.
    """
    return rolling_acc < threshold


def shadow_compare(
    shadow_preds: List[Tuple[float, int]],
    current_preds: List[Tuple[float, int]],
) -> bool:
    """
    Compare a shadow (challenger) model against the current live model.

    Promotes the shadow model when its Brier score is lower over the same
    set of validation samples.

    Args:
        shadow_preds:  Predictions from the shadow/challenger model.
        current_preds: Predictions from the current live model.

    Returns:
        True if shadow should be promoted (shadow brier < current brier).
    """
    if not shadow_preds or not current_preds:
        return False
    shadow_brier = brier_score(shadow_preds)
    current_brier = brier_score(current_preds)
    return shadow_brier < current_brier


def anomaly_flags(
    player: Dict[str, Any],
    opponent: Dict[str, Any],
    match_history: List[Dict[str, Any]],
) -> List[str]:
    """
    Return a list of risk/anomaly flags for a player going into a match.

    Flags generated:
      RUST_RISK              — hours_since_last_game > 48 (layoff effect)
      FATIGUE_RISK           — games_today >= 5 (too many games)
      UNKNOWN_H2H            — no historical matches against this opponent
      REGRESSION_CANDIDATE   — recent win% >> career win% (may regress to mean)
      BOUNCE_BACK_CANDIDATE  — recent win% << career win% (due for reversal)
      NEW_PLAYER             — fewer than 50 career games (insufficient data)
      FADE_RISK              — current win streak >= 5 (due for regression)

    Args:
        player:        Dict with player stats (same schema as DB players table).
        opponent:      Dict with opponent stats (for context; not used directly).
        match_history: List of historical matches between these two players.

    Returns:
        List of flag strings (may be empty if no anomalies found).
    """
    flags: List[str] = []

    # RUST_RISK: hasn't played in a while
    last_ts = player.get("last_match_timestamp")
    if last_ts is not None:
        try:
            hours_since = float(last_ts)  # stored as hours-since-last-game float
            if hours_since > 48:
                flags.append("RUST_RISK")
        except (TypeError, ValueError):
            pass

    # FATIGUE_RISK: playing too many games today
    if int(player.get("games_today", 0)) >= 5:
        flags.append("FATIGUE_RISK")

    # UNKNOWN_H2H: no match history
    if len(match_history) == 0:
        flags.append("UNKNOWN_H2H")

    # REGRESSION / BOUNCE-BACK based on recent vs career win%
    career_wp = float(player.get("win_pct", 50))
    recent_wp = float(player.get("recent_win_pct", career_wp))
    gap = recent_wp - career_wp
    if gap > 10.0:
        flags.append("REGRESSION_CANDIDATE")
    elif gap < -10.0:
        flags.append("BOUNCE_BACK_CANDIDATE")

    # NEW_PLAYER: too few games to trust the stats
    if int(player.get("total_games", 999)) < 50:
        flags.append("NEW_PLAYER")

    # FADE_RISK: on a long win streak (≥5 consecutive wins)
    form = player.get("form", [])
    if isinstance(form, list) and len(form) >= 5:
        streak = 0
        for result in form:
            if str(result).upper() in ("W", "1"):
                streak += 1
            else:
                break
        if streak >= 5:
            flags.append("FADE_RISK")

    return flags


def confidence_adjustment(base_confidence: float, flags: List[str]) -> float:
    """
    Reduce base model confidence based on detected anomaly flags.

    Reductions applied:
      RUST_RISK              — −0.05
      FATIGUE_RISK           — −0.08
      UNKNOWN_H2H            — −0.03
      NEW_PLAYER             — −0.05
      FADE_RISK              — −0.04
      REGRESSION_CANDIDATE   — −0.03
      (BOUNCE_BACK_CANDIDATE has no penalty — it is a favourable signal)

    Minimum confidence floor: 0.50 (never drop below coin-flip level).

    Args:
        base_confidence: Raw model confidence (0–1).
        flags:           List of flag strings from anomaly_flags().

    Returns:
        Adjusted confidence clamped to [0.50, 1.00].
    """
    penalties: Dict[str, float] = {
        "RUST_RISK": 0.05,
        "FATIGUE_RISK": 0.08,
        "UNKNOWN_H2H": 0.03,
        "NEW_PLAYER": 0.05,
        "FADE_RISK": 0.04,
        "REGRESSION_CANDIDATE": 0.03,
    }
    adjusted = base_confidence
    for flag in flags:
        adjusted -= penalties.get(flag, 0.0)
    return round(max(0.50, adjusted), 4)
