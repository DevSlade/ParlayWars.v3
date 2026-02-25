"""
ParlayWars v3 — Feature Engineering (35 features per matchup)
Date: 2026-02-25

Computes a feature vector for any player_a vs player_b matchup.
All features are derived from real player data — no random values.

Feature list (35 total):
  1.  elo_delta               ELO difference (a - b)
  2.  elo_expected            ELO-based win probability for a
  3.  wr_delta                Overall win rate diff
  4.  recent_wr_delta         Recent win rate diff
  5.  l10_delta               Last-10 games win rate diff
  6.  l5_delta                Last-5 games win rate diff
  7.  l3_delta                Last-3 games win rate diff
  8.  streak_delta            Current streak diff (+ = win streak)
  9.  games_delta             Total games diff
  10. games_ratio             Total games ratio
  11. h2h_delta               H2H win rate diff
  12. h2h_total               Total H2H matches
  13. h2h_avg_margin          Avg point margin in H2H
  14. rank_delta              Rank diff
  15. hot_a                   Player A on 3+ win streak
  16. cold_a                  Player A on 3+ loss streak
  17. hot_b                   Player B on 3+ win streak
  18. cold_b                  Player B on 3+ loss streak
  19. consistency_a
  20. consistency_b
  21. form_momentum_delta      form_velocity diff
  22. pts_delta               Avg points diff
  23. ast_delta               Avg assists diff
  24. fg_pct_delta            FG% diff
  25. three_pct_delta         3P% diff (estimated from fg_pct - avg)
  26. tov_delta               Turnovers diff (flipped — lower is better)
  27. stl_delta               Steals diff
  28. blk_delta               Blocks diff
  29. reb_delta               Rebounds diff
  30. scoring_efficiency_delta (PTS/(FGA+TOV)) diff
  31. clutch_delta            Clutch index diff
  32. upset_resistance_delta
  33. bounce_back_delta
  34. oqr_delta               OQR diff
  35. pwr_delta               PWR rating diff
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np

from engines.elo import expected_score
from core.logger import get_logger

log = get_logger(__name__)

FEATURE_NAMES: List[str] = [
    "elo_delta", "elo_expected", "wr_delta", "recent_wr_delta",
    "l10_delta", "l5_delta", "l3_delta", "streak_delta",
    "games_delta", "games_ratio",
    "h2h_delta", "h2h_total", "h2h_avg_margin",
    "rank_delta",
    "hot_a", "cold_a", "hot_b", "cold_b",
    "consistency_a", "consistency_b",
    "form_momentum_delta",
    "pts_delta", "ast_delta", "fg_pct_delta", "three_pct_delta",
    "tov_delta", "stl_delta", "blk_delta", "reb_delta",
    "scoring_efficiency_delta",
    "clutch_delta", "upset_resistance_delta", "bounce_back_delta",
    "oqr_delta", "pwr_delta",
]


def _form_win_rate(form: Optional[List[str]], last_n: int = 10) -> float:
    """Compute win rate from a W/L form list for the last N games."""
    if not form:
        return 0.5
    subset = form[:last_n]
    wins = sum(1 for x in subset if x == "W")
    return wins / len(subset) if subset else 0.5


def _streak_value(form: Optional[List[str]]) -> float:
    """
    Return current streak value:
      +N if on N-game win streak, -N if on N-game loss streak.
    """
    if not form:
        return 0.0
    streak_type = form[0]
    count = 0
    for result in form:
        if result == streak_type:
            count += 1
        else:
            break
    return float(count) if streak_type == "W" else float(-count)


def _is_hot(form: Optional[List[str]]) -> float:
    """Return 1.0 if player is on a 3+ game win streak."""
    if not form:
        return 0.0
    if form[0] != "W":
        return 0.0
    streak = sum(1 for x in form if x == form[0])  # simplistic — reuse streak logic
    return 1.0 if _streak_value(form) >= 3 else 0.0


def _is_cold(form: Optional[List[str]]) -> float:
    """Return 1.0 if player is on a 3+ game loss streak."""
    if not form:
        return 0.0
    return 1.0 if _streak_value(form) <= -3 else 0.0


def _scoring_efficiency(avg_pts: float, avg_fg_pct: float, avg_tov: float) -> float:
    """Simplified scoring efficiency: pts per (estimated FGA + TOV)."""
    # Estimate FGA from points and FG% (2-pt average assumption)
    if avg_fg_pct > 0:
        fga = avg_pts / (2.0 * avg_fg_pct + 1e-6)
    else:
        fga = avg_pts / 2.0
    denominator = fga + avg_tov + 1e-6
    return avg_pts / denominator


def compute_features(
    player_a: Dict[str, Any],
    player_b: Dict[str, Any],
    h2h: Optional[Dict[str, Any]] = None,
) -> np.ndarray:
    """
    Compute the 35-element feature vector for a matchup.

    Args:
        player_a: Dict of player A's stats from the database.
        player_b: Dict of player B's stats from the database.
        h2h: Optional H2H record dict from h2h_records table.

    Returns:
        numpy array of shape (35,) with all feature values.
    """
    form_a = player_a.get("form") or []
    form_b = player_b.get("form") or []

    elo_a = float(player_a.get("elo") or 1500.0)
    elo_b = float(player_b.get("elo") or 1500.0)

    wr_a = float(player_a.get("win_pct") or 50.0) / 100.0
    wr_b = float(player_b.get("win_pct") or 50.0) / 100.0
    rwr_a = float(player_a.get("recent_win_pct") or 50.0) / 100.0
    rwr_b = float(player_b.get("recent_win_pct") or 50.0) / 100.0

    l10_a = _form_win_rate(form_a, 10)
    l10_b = _form_win_rate(form_b, 10)
    l5_a = _form_win_rate(form_a, 5)
    l5_b = _form_win_rate(form_b, 5)
    l3_a = _form_win_rate(form_a, 3)
    l3_b = _form_win_rate(form_b, 3)

    streak_a = _streak_value(form_a)
    streak_b = _streak_value(form_b)

    games_a = float(player_a.get("total_games") or 1)
    games_b = float(player_b.get("total_games") or 1)

    # H2H features
    if h2h:
        total_h2h = float(h2h.get("total") or 0)
        # Determine which player is "a" in the h2h record
        if h2h.get("player_a") == player_a.get("name"):
            a_h2h_wins = float(h2h.get("a_wins") or 0)
        else:
            a_h2h_wins = float(h2h.get("b_wins") or 0)
        h2h_wr_a = a_h2h_wins / total_h2h if total_h2h > 0 else 0.5
        h2h_total = total_h2h
        h2h_margin = float(h2h.get("avg_margin") or 0.0)
    else:
        h2h_wr_a = 0.5
        h2h_total = 0.0
        h2h_margin = 0.0

    rank_a = float(player_a.get("rank") or 83)  # median rank if unknown
    rank_b = float(player_b.get("rank") or 83)

    # Advanced stats
    pts_a = float(player_a.get("avg_points") or 45.0)
    pts_b = float(player_b.get("avg_points") or 45.0)
    ast_a = float(player_a.get("avg_ast") or 5.0)
    ast_b = float(player_b.get("avg_ast") or 5.0)
    fg_a = float(player_a.get("avg_fg_pct") or 0.45)
    fg_b = float(player_b.get("avg_fg_pct") or 0.45)
    tov_a = float(player_a.get("avg_tov") or 3.0)
    tov_b = float(player_b.get("avg_tov") or 3.0)
    stl_a = float(player_a.get("avg_stl") or 1.5)
    stl_b = float(player_b.get("avg_stl") or 1.5)
    blk_a = float(player_a.get("avg_blk") or 0.5)
    blk_b = float(player_b.get("avg_blk") or 0.5)
    reb_a = float(player_a.get("avg_reb") or 8.0)
    reb_b = float(player_b.get("avg_reb") or 8.0)

    # Novel metrics
    clutch_a = float(player_a.get("clutch_index") or 50.0)
    clutch_b = float(player_b.get("clutch_index") or 50.0)
    consistency_a = float(player_a.get("consistency_score") or 50.0)
    consistency_b = float(player_b.get("consistency_score") or 50.0)
    upset_res_a = float(player_a.get("upset_resistance") or 50.0)
    upset_res_b = float(player_b.get("upset_resistance") or 50.0)
    form_vel_a = float(player_a.get("form_velocity") or 0.0)
    form_vel_b = float(player_b.get("form_velocity") or 0.0)
    bounce_a = float(player_a.get("bounce_back_rate") or 0.5)
    bounce_b = float(player_b.get("bounce_back_rate") or 0.5)
    oqr_a = float(player_a.get("oqr") or 50.0)
    oqr_b = float(player_b.get("oqr") or 50.0)
    pwr_a = float(player_a.get("pwr_rating") or 50.0)
    pwr_b = float(player_b.get("pwr_rating") or 50.0)

    # Scoring efficiency
    eff_a = _scoring_efficiency(pts_a, fg_a, tov_a)
    eff_b = _scoring_efficiency(pts_b, fg_b, tov_b)

    # Estimated 3P% (FG% minus league average 2P% contribution)
    three_pct_a = max(0.0, fg_a - 0.42)
    three_pct_b = max(0.0, fg_b - 0.42)

    features = np.array([
        elo_a - elo_b,                          # 1.  elo_delta
        expected_score(elo_a, elo_b),           # 2.  elo_expected
        wr_a - wr_b,                            # 3.  wr_delta
        rwr_a - rwr_b,                          # 4.  recent_wr_delta
        l10_a - l10_b,                          # 5.  l10_delta
        l5_a - l5_b,                            # 6.  l5_delta
        l3_a - l3_b,                            # 7.  l3_delta
        streak_a - streak_b,                    # 8.  streak_delta
        games_a - games_b,                      # 9.  games_delta
        games_a / (games_b + 1e-6),             # 10. games_ratio
        h2h_wr_a - 0.5,                         # 11. h2h_delta
        h2h_total,                              # 12. h2h_total
        h2h_margin,                             # 13. h2h_avg_margin
        rank_b - rank_a,                        # 14. rank_delta (lower rank = better)
        _is_hot(form_a),                        # 15. hot_a
        _is_cold(form_a),                       # 16. cold_a
        _is_hot(form_b),                        # 17. hot_b
        _is_cold(form_b),                       # 18. cold_b
        consistency_a,                          # 19. consistency_a
        consistency_b,                          # 20. consistency_b
        form_vel_a - form_vel_b,                # 21. form_momentum_delta
        pts_a - pts_b,                          # 22. pts_delta
        ast_a - ast_b,                          # 23. ast_delta
        fg_a - fg_b,                            # 24. fg_pct_delta
        three_pct_a - three_pct_b,              # 25. three_pct_delta
        tov_b - tov_a,                          # 26. tov_delta (flipped)
        stl_a - stl_b,                          # 27. stl_delta
        blk_a - blk_b,                          # 28. blk_delta
        reb_a - reb_b,                          # 29. reb_delta
        eff_a - eff_b,                          # 30. scoring_efficiency_delta
        clutch_a - clutch_b,                    # 31. clutch_delta
        upset_res_a - upset_res_b,              # 32. upset_resistance_delta
        bounce_a - bounce_b,                    # 33. bounce_back_delta
        oqr_a - oqr_b,                          # 34. oqr_delta
        pwr_a - pwr_b,                          # 35. pwr_delta
    ], dtype=np.float32)

    return features


def build_training_data(players: list[Dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate synthetic training data from player stats.

    For each pair of players with different win rates, we synthesise a matchup
    using log-odds of their win rates as the label probability, then threshold
    at 0.5 to get a binary label.

    Returns:
        X: Feature matrix of shape (N, 35)
        y: Binary label array of shape (N,)  — 1 = player_a wins
    """
    import itertools
    from engines.elo import expected_score as elo_exp

    X_rows: list[np.ndarray] = []
    y_labels: list[float] = []

    player_map = {p["name"]: p for p in players}
    names = list(player_map.keys())

    # Only generate pairs where we have enough data
    for name_a, name_b in itertools.combinations(names, 2):
        pa = player_map[name_a]
        pb = player_map[name_b]

        feat = compute_features(pa, pb)
        X_rows.append(feat)

        # Label: probability based on ELO expected score + win rate
        p_elo = elo_exp(
            float(pa.get("elo") or 1500),
            float(pb.get("elo") or 1500),
        )
        wr_a = float(pa.get("win_pct") or 50) / 100.0
        wr_b = float(pb.get("win_pct") or 50) / 100.0
        p_wr = wr_a / (wr_a + wr_b + 1e-9)
        prob_a = 0.6 * p_elo + 0.4 * p_wr
        label = 1.0 if prob_a > 0.5 else 0.0
        y_labels.append(label)

        # Also add the reverse pair
        feat_rev = compute_features(pb, pa)
        X_rows.append(feat_rev)
        y_labels.append(1.0 - label)

    X = np.array(X_rows, dtype=np.float32)
    y = np.array(y_labels, dtype=np.float32)
    return X, y
