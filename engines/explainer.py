"""
ParlayWars v3 — Natural Language Explanation Generator
Date: 2026-02-25

Converts top feature importances into plain English sentences.
"""
from __future__ import annotations
from typing import Dict, List, Any

from engines.features import FEATURE_NAMES

# Templates for each feature
_TEMPLATES: Dict[str, tuple[str, str]] = {
    "elo_delta":               ("{a} has a higher ELO rating by {val:.0f} points, indicating stronger historical performance.",
                                "{b} has a higher ELO rating by {val:.0f} points, indicating stronger historical performance."),
    "elo_expected":            ("{a}'s ELO win probability is {val:.1%}.",
                                "{a}'s ELO win probability is only {val:.1%}."),
    "wr_delta":                ("{a}'s overall win rate is {val:.1%} higher than {b}'s.",
                                "{b}'s overall win rate is {val:.1%} higher than {a}'s."),
    "recent_wr_delta":         ("{a} has been winning {val:.1%} more in recent matches.",
                                "{b} has been winning {val:.1%} more recently."),
    "l10_delta":               ("{a} won {val:.0%} more of the last 10 games.",
                                "{b} won {val:.0%} more of the last 10 games."),
    "l5_delta":                ("{a} is on a hot streak — {val:.0%} better over last 5.",
                                "{b} is on a hot streak — {val:.0%} better over last 5."),
    "l3_delta":                ("{a} dominated the last 3 games.",
                                "{b} dominated the last 3 games."),
    "streak_delta":            ("{a} is riding a {val:.0f}-game win streak.",
                                "{b} is riding a {val:.0f}-game win streak."),
    "h2h_delta":               ("{a} has a {val:.1%} H2H advantage over {b}.",
                                "{b} has a {val:.1%} H2H advantage over {a}."),
    "h2h_total":               ("These players have met {val:.0f} times before.",
                                "These players have met {val:.0f} times before."),
    "rank_delta":              ("{a} is ranked {val:.0f} spots higher than {b}.",
                                "{b} is ranked {val:.0f} spots higher than {a}."),
    "hot_a":                   ("{a} is currently on a 3+ game win streak (hot hand).",
                                ""),
    "cold_b":                  ("{b} is on a losing streak, which hurts their chances.",
                                ""),
    "clutch_delta":            ("{a} has a higher clutch index — better in tight situations.",
                                "{b} has a higher clutch index — better in tight situations."),
    "form_momentum_delta":     ("{a}'s momentum is trending upward.",
                                "{b}'s momentum is trending upward."),
    "pwr_delta":               ("{a}'s PWR composite rating is {val:.1f} points higher.",
                                "{b}'s PWR composite rating is {val:.1f} points higher."),
}


def explain_prediction(
    player_a: str,
    player_b: str,
    feature_values: List[float],
    feature_importances: List[float],
    top_n: int = 5,
) -> str:
    """
    Generate a natural-language explanation for a prediction.

    Args:
        player_a: Name of player A.
        player_b: Name of player B.
        feature_values: The 35-element feature vector.
        feature_importances: Per-feature importance scores from the model.
        top_n: Number of top features to include in the explanation.

    Returns:
        A multi-sentence English string.
    """
    if len(feature_importances) != len(FEATURE_NAMES):
        return f"Prediction favours {player_a} based on overall statistics."

    # Sort features by importance descending
    ranked = sorted(
        zip(FEATURE_NAMES, feature_values, feature_importances),
        key=lambda x: x[2],
        reverse=True,
    )[:top_n]

    sentences: List[str] = []
    for feat_name, val, imp in ranked:
        tpl_pair = _TEMPLATES.get(feat_name)
        if tpl_pair is None:
            # Generic template
            if val > 0:
                sentences.append(f"{player_a} leads on {feat_name.replace('_', ' ')} (Δ={val:.2f}).")
            elif val < 0:
                sentences.append(f"{player_b} leads on {feat_name.replace('_', ' ')} (Δ={abs(val):.2f}).")
            continue

        pos_tpl, neg_tpl = tpl_pair
        if val >= 0 and pos_tpl:
            sentences.append(pos_tpl.format(a=player_a, b=player_b, val=abs(val)))
        elif val < 0 and neg_tpl:
            sentences.append(neg_tpl.format(a=player_a, b=player_b, val=abs(val)))

    return " ".join(sentences) or f"{player_a} is the predicted winner based on overall statistics."
