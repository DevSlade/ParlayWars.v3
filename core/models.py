"""
ParlayWars v3 — Pydantic Data Models
Date: 2026-02-25

Defines all data shapes used throughout the system.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Player(BaseModel):
    """Full player profile with all stats and ratings."""
    id: Optional[int] = None
    name: str
    sport: str = "ebasketball"
    rank: Optional[int] = None
    elo: float = 1500.0
    pwr_rating: float = 50.0
    win_pct: Optional[float] = None
    recent_win_pct: Optional[float] = None
    total_games: Optional[int] = None
    wins: Optional[int] = None
    losses: Optional[int] = None
    form: Optional[List[str]] = None          # last-10 W/L list
    avg_points: Optional[float] = None
    avg_fg_pct: Optional[float] = None
    avg_reb: Optional[float] = None
    avg_ast: Optional[float] = None
    avg_stl: Optional[float] = None
    avg_blk: Optional[float] = None
    avg_tov: Optional[float] = None
    clutch_index: Optional[float] = None
    consistency_score: Optional[float] = None
    upset_resistance: Optional[float] = None
    fade_factor: Optional[float] = None
    oqr: Optional[float] = None
    form_velocity: Optional[float] = None
    bounce_back_rate: Optional[float] = None
    last_updated: Optional[str] = None
    created_at: Optional[str] = None


class Match(BaseModel):
    """A single recorded or live match."""
    id: Optional[int] = None
    sport: str = "ebasketball"
    player_a: str
    player_b: str
    winner: Optional[str] = None
    score_a: Optional[int] = None
    score_b: Optional[int] = None
    quarter_scores: Optional[Dict] = None
    match_date: Optional[str] = None
    source: Optional[str] = None
    api_match_id: Optional[str] = None
    created_at: Optional[str] = None
    status: Optional[str] = "scheduled"   # scheduled | live | completed


class H2HRecord(BaseModel):
    """Head-to-head record between two players."""
    id: Optional[int] = None
    player_a: str
    player_b: str
    a_wins: int = 0
    b_wins: int = 0
    total: int = 0
    avg_margin: float = 0.0
    last_played: Optional[str] = None


class EngineVote(BaseModel):
    """A single engine's prediction for a match."""
    id: Optional[int] = None
    match_id: Optional[int] = None
    engine_name: str
    vote: str                              # player name predicted to win
    probability: float                     # probability of vote winning (0-1)
    is_pre_match: bool = True
    created_at: Optional[str] = None


class Prediction(BaseModel):
    """Aggregated prediction across all engines for a match."""
    id: Optional[int] = None
    match_id: Optional[int] = None
    engine_name: str
    player_a: str
    player_b: str
    predicted_winner: str
    prob_a: float                          # probability player_a wins
    prob_b: float                          # probability player_b wins
    confidence: float                      # max(prob_a, prob_b)
    tier: str = "LOW"                      # HIGH / MEDIUM / LOW
    explanation: Optional[str] = None
    tree_data: Optional[Dict] = None       # JSON for D3.js
    is_pre_match: bool = True
    created_at: Optional[str] = None
    votes: Optional[List[EngineVote]] = None


class Bet(BaseModel):
    """A paper-trading bet."""
    id: Optional[int] = None
    match_id: Optional[int] = None
    bet_type: str = "straight"             # straight | parlay
    stake: float
    odds_american: int
    odds_decimal: float
    predicted_winner: str
    actual_winner: Optional[str] = None
    profit_loss: Optional[float] = None
    engine_used: str
    confidence: float
    tier: str = "LOW"
    parlay_id: Optional[int] = None
    status: str = "pending"               # pending | won | lost | void
    placed_at: Optional[str] = None
    settled_at: Optional[str] = None


class BankrollEntry(BaseModel):
    """A single bankroll snapshot entry."""
    id: Optional[int] = None
    timestamp: str
    balance: float
    action: str
    bet_id: Optional[int] = None
    amount: float


class ModelTrainingLog(BaseModel):
    """Record of an engine training run."""
    id: Optional[int] = None
    engine_name: str
    accuracy: float
    features_used: Optional[List[str]] = None
    hyperparams: Optional[Dict] = None
    samples_count: int
    trained_at: Optional[str] = None


class PlayerSnapshot(BaseModel):
    """Daily snapshot of a player's key ratings."""
    id: Optional[int] = None
    player_name: str
    snapshot_date: str
    elo: float
    pwr_rating: float
    win_pct: Optional[float] = None
    recent_win_pct: Optional[float] = None
    created_at: Optional[str] = None


class PredictionRequest(BaseModel):
    """API request for a prediction."""
    player_a: str
    player_b: str
    match_id: Optional[int] = None


class ConfigUpdate(BaseModel):
    """API request to update configuration."""
    data: Dict[str, Any]
