"""
ParlayWars v3 — Bookie-Beating Edge System
Date: 2026-02-25

Metrics that find where bookie implied probability is WRONG:
  - Expected Value (EV): EV = (our_prob × profit) - ((1-our_prob) × stake)
  - Edge %: edge = our_probability - bookie_implied_probability (no-vig)
  - Closing Line Value (CLV): did we beat the closing line?
  - No-Vig Fair Odds: strip vig from bookie lines
  - Vig Calculator: vig = (1/dec_a + 1/dec_b) - 1
  - Kelly Edge Score: (prob * decimal_odds - 1) / (decimal_odds - 1)
  - Steam Move Detector: >5% implied prob shift in <30 min
  - Reverse Line Movement: line moves against public side
  - Market Efficiency: max_implied - min_implied across books
  - ROI by confidence tier (from historical bets)
"""
from __future__ import annotations

from typing import Dict, List, Tuple


def no_vig_prob(decimal_a: float, decimal_b: float) -> Tuple[float, float]:
    """
    Strip the vig from two-sided decimal odds and return fair probabilities.

    The raw implied probabilities (1/decimal) sum to more than 1.0 because of
    the bookmaker margin.  We normalise them so they sum exactly to 1.0.

    Args:
        decimal_a: Decimal odds for side A (e.g. 1.85).
        decimal_b: Decimal odds for side B (e.g. 1.95).

    Returns:
        (fair_prob_a, fair_prob_b) — normalised, vig-free probabilities.
    """
    if decimal_a <= 0 or decimal_b <= 0:
        return (0.5, 0.5)
    implied_a = 1.0 / decimal_a
    implied_b = 1.0 / decimal_b
    total = implied_a + implied_b
    if total <= 0:
        return (0.5, 0.5)
    return (round(implied_a / total, 6), round(implied_b / total, 6))


def vig(decimal_a: float, decimal_b: float) -> float:
    """
    Calculate the bookmaker's vig (margin) for a two-sided market.

    vig = (1/decimal_a + 1/decimal_b) - 1

    A value of 0.05 means the book takes ~5% of every dollar wagered.

    Args:
        decimal_a: Decimal odds for side A.
        decimal_b: Decimal odds for side B.

    Returns:
        Vig as a fraction (e.g. 0.045 ≈ 4.5% margin).
    """
    if decimal_a <= 0 or decimal_b <= 0:
        return 0.0
    return round(1.0 / decimal_a + 1.0 / decimal_b - 1.0, 6)


def expected_value(our_prob: float, decimal_odds: float, stake: float = 1.0) -> float:
    """
    Compute the Expected Value of a bet in dollars.

    EV = (our_prob × (decimal_odds - 1) × stake) - ((1 - our_prob) × stake)

    A positive EV means we have a mathematical edge over the book.

    Args:
        our_prob:      Our estimated probability of winning (0–1).
        decimal_odds:  Decimal odds offered by the bookmaker.
        stake:         Dollar amount wagered (default 1.0).

    Returns:
        Expected profit/loss in dollars.
    """
    if decimal_odds <= 1.0:
        return -stake
    profit_if_win = (decimal_odds - 1.0) * stake
    loss_if_lose = stake
    return round(our_prob * profit_if_win - (1.0 - our_prob) * loss_if_lose, 4)


def edge_pct(our_prob: float, fair_prob: float) -> float:
    """
    Compute our edge over the no-vig fair probability as a fraction.

    edge = our_prob - fair_prob

    Positive means we believe the true probability is higher than the
    market's no-vig estimate — a +EV opportunity.

    Args:
        our_prob:   Our model's estimated win probability.
        fair_prob:  The no-vig implied probability from the bookie line.

    Returns:
        Edge as a fraction (e.g. 0.06 = 6% edge).
    """
    return round(our_prob - fair_prob, 6)


def kelly_edge_score(our_prob: float, decimal_odds: float) -> float:
    """
    Compute the Kelly Edge Score — a normalised measure of edge size.

    Formula: (p * d - 1) / (d - 1), floored at 0 (no negative bets).

    This tells us *how much* of the full Kelly fraction we should use.

    Args:
        our_prob:      Our estimated win probability.
        decimal_odds:  Decimal odds offered.

    Returns:
        Kelly edge score ≥ 0.  Returns 0 if there is no edge.
    """
    d = decimal_odds
    if d <= 1.0:
        return 0.0
    numerator = our_prob * d - 1.0
    denominator = d - 1.0
    if denominator <= 0:
        return 0.0
    score = numerator / denominator
    return round(max(0.0, score), 6)


def is_low_vig(decimal_a: float, decimal_b: float, threshold: float = 0.04) -> bool:
    """
    Return True if the bookmaker's vig is below the given threshold.

    Low-vig markets are more efficient and fairer to the bettor.

    Args:
        decimal_a:  Decimal odds for side A.
        decimal_b:  Decimal odds for side B.
        threshold:  Maximum vig to qualify as "low" (default 4%).

    Returns:
        True if vig < threshold.
    """
    return vig(decimal_a, decimal_b) < threshold


def market_efficiency_score(
    all_decimal_a: List[float],
    all_decimal_b: List[float],
) -> float:
    """
    Measure how spread the implied probabilities are across multiple books.

    A lower score (closer to 0) means all books agree → efficient market.
    A higher score means there is disagreement → potential soft lines.

    Computed as: max(implied_a across books) - min(implied_a across books).

    Args:
        all_decimal_a: Decimal odds for side A from each book.
        all_decimal_b: Decimal odds for side B from each book.

    Returns:
        Spread between highest and lowest implied probability for side A.
        Returns 0.0 if fewer than 2 books are provided.
    """
    if len(all_decimal_a) < 2:
        return 0.0
    implied_a_values = []
    for dec_a, dec_b in zip(all_decimal_a, all_decimal_b):
        if dec_a > 0 and dec_b > 0:
            fair_a, _ = no_vig_prob(dec_a, dec_b)
            implied_a_values.append(fair_a)
    if len(implied_a_values) < 2:
        return 0.0
    return round(max(implied_a_values) - min(implied_a_values), 6)


def detect_steam_move(
    old_implied: float,
    new_implied: float,
    minutes_elapsed: float,
) -> bool:
    """
    Detect a steam move — a sharp, rapid shift in implied probability.

    Criteria: more than 5% absolute change in implied probability in under 30 min.
    Steam moves indicate sharp bettor action that the market is reacting to.

    Args:
        old_implied:      Previous implied probability (0–1).
        new_implied:      Current implied probability (0–1).
        minutes_elapsed:  Time elapsed between observations in minutes.

    Returns:
        True if this qualifies as a steam move.
    """
    if minutes_elapsed <= 0 or minutes_elapsed >= 30:
        return False
    return abs(new_implied - old_implied) > 0.05


def clv_result(our_prob: float, closing_decimal_odds: float) -> float:
    """
    Calculate Closing Line Value (CLV).

    CLV measures whether we got better odds than the closing line.
    Positive CLV = we beat the closing line (good process).
    Negative CLV = we got worse odds than closing (potential leak).

    Formula: our_prob - (1 / closing_decimal_odds)

    Args:
        our_prob:               Our model's win probability when bet was placed.
        closing_decimal_odds:   Decimal odds at market close.

    Returns:
        CLV as a fraction.  Positive = beat closing line.
    """
    if closing_decimal_odds <= 0:
        return 0.0
    closing_implied = 1.0 / closing_decimal_odds
    return round(our_prob - closing_implied, 6)


def grade_bet(won: bool, ev: float, confidence: float) -> str:
    """
    Grade a settled bet based on outcome, EV, and confidence.

    Grading rubric:
      A+  Won AND ev > 0.05 AND confidence > 0.70 — elite execution
      A   Won (regardless of EV) — good result
      B   Lost but ev > 0 — correct process, bad luck
      C   Lost and ev <= 0 — bad process
      F   Lost AND confidence >= 0.75 — LOCK lost (worst outcome)

    Note: F is checked before C because a LOCK loss is worse than C.

    Args:
        won:        True if the bet won.
        ev:         Expected value of the bet at placement time.
        confidence: Model confidence at placement time (0–1).

    Returns:
        Grade string: 'A+', 'A', 'B', 'C', or 'F'.
    """
    if won and ev > 0.05 and confidence > 0.70:
        return "A+"
    if won:
        return "A"
    # Bet was lost from here on
    if confidence >= 0.75:
        return "F"  # LOCK loss — highest priority bad grade
    if ev > 0:
        return "B"  # Good process, bad luck
    return "C"      # Bad process


def edge_based_unit_size(
    edge_pct_val: float,
    consensus_count: int,
    total_engines: int = 4,
) -> float:
    """
    Determine bet size as a unit multiplier based on edge % and engine consensus.

    Edge tiers:
      3–5%   → 0.5 units  (marginal edge)
      5–8%   → 1.0 units  (solid edge)
      8–12%  → 1.5 units  (strong edge)
      12%+   → 2.0 units  (elite edge)
      <3%    → 0.0 units  (skip — not enough edge)

    Consensus scaling:
      4/4 engines agree → ×1.00
      3/4 engines agree → ×0.75
      ≤2/4 engines agree → 0 (skip regardless of edge)

    Args:
        edge_pct_val:     Edge as a fraction (e.g. 0.06 = 6% edge).
        consensus_count:  Number of engines that agree on the pick.
        total_engines:    Total number of engines (default 4).

    Returns:
        Unit multiplier (0.0 means skip the bet).
    """
    # Base unit from edge tier
    edge_as_pct = edge_pct_val * 100.0  # convert fraction to percent
    if edge_as_pct < 3.0:
        return 0.0
    elif edge_as_pct < 5.0:
        base_units = 0.5
    elif edge_as_pct < 8.0:
        base_units = 1.0
    elif edge_as_pct < 12.0:
        base_units = 1.5
    else:
        base_units = 2.0

    # Consensus scaling
    if total_engines <= 0:
        return 0.0
    ratio = consensus_count / total_engines
    if consensus_count >= total_engines:  # 4/4
        consensus_multiplier = 1.0
    elif consensus_count == total_engines - 1:  # 3/4
        consensus_multiplier = 0.75
    else:  # 2/4 or worse → skip
        return 0.0

    return round(base_units * consensus_multiplier, 4)


def roi_by_edge_bucket(bets: List[Dict]) -> Dict[str, Dict]:
    """
    Group historical bets by edge % bucket and compute ROI metrics per bucket.

    Edge buckets:
      "3-5":  3–5% edge
      "5-8":  5–8% edge
      "8-12": 8–12% edge
      "12+":  12%+ edge

    For each bucket returns:
      - win_rate:   fraction of bets won
      - roi:        total profit_loss / total stake (fraction)
      - count:      number of bets in bucket

    Args:
        bets: List of bet dicts, each with keys:
              - edge_pct (float, 0–1 fraction)
              - won (bool)
              - stake (float)
              - profit_loss (float)

    Returns:
        Dict keyed by bucket name.  Missing buckets are omitted.
    """
    buckets: Dict[str, Dict] = {
        "3-5":  {"wins": 0, "count": 0, "total_stake": 0.0, "total_pl": 0.0},
        "5-8":  {"wins": 0, "count": 0, "total_stake": 0.0, "total_pl": 0.0},
        "8-12": {"wins": 0, "count": 0, "total_stake": 0.0, "total_pl": 0.0},
        "12+":  {"wins": 0, "count": 0, "total_stake": 0.0, "total_pl": 0.0},
    }

    for bet in bets:
        ep = float(bet.get("edge_pct", 0)) * 100.0  # fraction → percent
        if ep < 3.0:
            continue
        elif ep < 5.0:
            key = "3-5"
        elif ep < 8.0:
            key = "5-8"
        elif ep < 12.0:
            key = "8-12"
        else:
            key = "12+"

        buckets[key]["count"] += 1
        buckets[key]["total_stake"] += float(bet.get("stake", 0))
        buckets[key]["total_pl"] += float(bet.get("profit_loss", 0))
        if bet.get("won"):
            buckets[key]["wins"] += 1

    result: Dict[str, Dict] = {}
    for key, data in buckets.items():
        n = data["count"]
        if n == 0:
            continue
        stake = data["total_stake"]
        result[key] = {
            "win_rate": round(data["wins"] / n, 4),
            "roi": round(data["total_pl"] / stake, 4) if stake > 0 else 0.0,
            "count": n,
        }
    return result
