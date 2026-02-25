"""
ParlayWars v3 — PWR (ParlayWars Rating) Composite System
Date: 2026-02-25

PWR is a 0-100 composite score built from 7 novel metrics:
  1. Overall win rate (normalised)
  2. Recent win rate (last 10 games, weighted 2×)
  3. ELO rating (normalised to 0-100 scale)
  4. Clutch index
  5. Consistency score
  6. Form velocity (trend direction)
  7. Opponent quality rating (OQR)

PWR formula:
  PWR = 0.20 * wr_norm + 0.25 * recent_norm + 0.20 * elo_norm
       + 0.10 * clutch + 0.10 * consistency + 0.10 * form_vel + 0.05 * oqr
"""
from __future__ import annotations
from typing import Any, Dict, Optional

from core.logger import get_logger

log = get_logger(__name__)

# ELO normalisation range for the player pool
ELO_MIN = 1200.0
ELO_MAX = 1900.0


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp a value to [lo, hi]."""
    return max(lo, min(hi, value))


def compute_pwr(player: Dict[str, Any]) -> float:
    """
    Compute the PWR composite rating for a player.

    Args:
        player: Dict with keys matching the players table.

    Returns:
        PWR score in [0, 100].
    """
    # 1. Overall win rate component (0-100)
    wr = float(player.get("win_pct") or 50.0)
    wr_norm = _clamp(wr)

    # 2. Recent win rate (last 10, weighted more)
    recent_wr = float(player.get("recent_win_pct") or 50.0)
    recent_norm = _clamp(recent_wr)

    # 3. ELO normalised to 0-100
    elo = float(player.get("elo") or 1500.0)
    elo_norm = _clamp((elo - ELO_MIN) / (ELO_MAX - ELO_MIN) * 100.0)

    # 4. Clutch index (already 0-100)
    clutch = _clamp(float(player.get("clutch_index") or 50.0))

    # 5. Consistency score (already 0-100)
    consistency = _clamp(float(player.get("consistency_score") or 50.0))

    # 6. Form velocity (recent trend, -100 to +100 → normalised to 0-100)
    form_vel_raw = float(player.get("form_velocity") or 0.0)
    form_vel_norm = _clamp(50.0 + form_vel_raw * 50.0)

    # 7. OQR (already 0-100)
    oqr = _clamp(float(player.get("oqr") or 50.0))

    pwr = (
        0.20 * wr_norm
        + 0.25 * recent_norm
        + 0.20 * elo_norm
        + 0.10 * clutch
        + 0.10 * consistency
        + 0.10 * form_vel_norm
        + 0.05 * oqr
    )

    return round(_clamp(pwr), 2)
