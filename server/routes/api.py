"""
ParlayWars v3 — REST API Routes
Date: 2026-02-25

Endpoints:
  GET  /api/players            — All players with stats
  GET  /api/players/{name}     — Single player profile
  GET  /api/matches            — Recent/live/upcoming matches
  GET  /api/predictions        — Recent predictions
  POST /api/predict            — Request prediction for two players
  GET  /api/h2h/{a}/{b}        — H2H comparison
  GET  /api/engines            — Engine status and tree data
  GET  /api/stats              — Platform statistics
  GET  /api/sim                — Simulation summary
  PUT  /api/config             — Update configuration
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from core.config import cfg
from core.database import (
    get_all_players_async,
    get_bets_async,
    get_h2h_async,
    get_matches_async,
    get_player_async,
    get_predictions_async,
    get_bankroll_history_async,
    save_prediction_async,
)
from core.logger import get_logger
from core.models import ConfigUpdate, PredictionRequest
from sim.bankroll import bankroll_manager
from sim.tracker import tracker

log = get_logger(__name__)
router = APIRouter()


@router.get("/players")
async def get_players(
    search: Optional[str] = Query(None),
    limit: int = Query(200, le=500),
) -> List[Dict[str, Any]]:
    """Return all players, optionally filtered by name search."""
    players = await get_all_players_async()
    if search:
        s = search.upper()
        players = [p for p in players if s in p.get("name", "").upper()]
    return players[:limit]


@router.get("/players/{name}")
async def get_player(name: str) -> Dict[str, Any]:
    """Return a single player's full profile."""
    player = await get_player_async(name.upper())
    if not player:
        raise HTTPException(status_code=404, detail=f"Player '{name}' not found")
    return player


@router.get("/matches")
async def get_matches(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
) -> List[Dict[str, Any]]:
    """Return matches, optionally filtered by status (live/scheduled/completed)."""
    return await get_matches_async(status=status, limit=limit)


@router.get("/predictions")
async def get_predictions(limit: int = Query(50, le=200)) -> List[Dict[str, Any]]:
    """Return recent predictions from all engines."""
    return await get_predictions_async(limit=limit)


@router.post("/predict")
async def predict_match(req: PredictionRequest) -> Dict[str, Any]:
    """
    Generate predictions from all 4 engines for a player_a vs player_b matchup.
    Returns aggregated result with individual engine votes.
    """
    from engines.titan import titan_engine
    from engines.phantom import phantom_engine
    from engines.surge import surge_engine
    from engines.oracle import oracle_engine

    results: List[Dict[str, Any]] = []
    loop = asyncio.get_event_loop()

    for engine in [titan_engine, phantom_engine, surge_engine, oracle_engine]:
        try:
            prob_a, prob_b = await loop.run_in_executor(
                None, engine.predict, req.player_a, req.player_b
            )
            confidence = max(prob_a, prob_b)
            tier = engine.confidence_tier(confidence)
            explanation = await loop.run_in_executor(None, engine.explain, req.player_a, req.player_b)
            tree_data = await loop.run_in_executor(None, engine.get_tree_data)
            predicted_winner = req.player_a if prob_a >= 0.5 else req.player_b

            pred = {
                "engine_name": engine.name,
                "player_a": req.player_a,
                "player_b": req.player_b,
                "predicted_winner": predicted_winner,
                "prob_a": round(prob_a, 4),
                "prob_b": round(prob_b, 4),
                "confidence": round(confidence, 4),
                "tier": tier,
                "explanation": explanation,
                "tree_data": tree_data,
                "match_id": req.match_id,
            }
            # Save to DB
            pred["id"] = await save_prediction_async(pred)
            results.append(pred)
        except Exception as exc:
            log.warning("Engine %s failed for %s vs %s: %s", engine.name, req.player_a, req.player_b, exc)
            results.append({
                "engine_name": engine.name,
                "error": str(exc),
                "player_a": req.player_a,
                "player_b": req.player_b,
                "prob_a": 0.5,
                "prob_b": 0.5,
                "confidence": 0.5,
                "tier": "LOW",
                "predicted_winner": req.player_a,
            })

    return {
        "player_a": req.player_a,
        "player_b": req.player_b,
        "match_id": req.match_id,
        "engines": results,
        "consensus": _compute_consensus(results, req.player_a),
    }


def _compute_consensus(results: List[Dict], player_a: str) -> Dict[str, Any]:
    """Compute the weighted consensus across all engines."""
    weights = {"TITAN": 0.40, "PHANTOM": 0.25, "SURGE": 0.35, "ORACLE": 0.0}
    total_w = 0.0
    weighted_prob_a = 0.0
    for r in results:
        w = weights.get(r.get("engine_name", ""), 0.25)
        weighted_prob_a += w * float(r.get("prob_a", 0.5))
        total_w += w
    if total_w > 0:
        weighted_prob_a /= total_w
    winner = player_a if weighted_prob_a >= 0.5 else "player_b"
    confidence = max(weighted_prob_a, 1.0 - weighted_prob_a)
    return {
        "predicted_winner": winner,
        "prob_a": round(weighted_prob_a, 4),
        "confidence": round(confidence, 4),
        "tier": "HIGH" if confidence >= 0.65 else ("MEDIUM" if confidence >= 0.55 else "LOW"),
    }


@router.get("/h2h/{player_a}/{player_b}")
async def get_h2h(player_a: str, player_b: str) -> Dict[str, Any]:
    """Return H2H record + full predictions for two players."""
    h2h = await get_h2h_async(player_a.upper(), player_b.upper())
    pa = await get_player_async(player_a.upper())
    pb = await get_player_async(player_b.upper())
    if not pa:
        raise HTTPException(status_code=404, detail=f"Player '{player_a}' not found")
    if not pb:
        raise HTTPException(status_code=404, detail=f"Player '{player_b}' not found")
    return {
        "player_a": pa,
        "player_b": pb,
        "h2h": h2h or {"player_a": player_a, "player_b": player_b, "a_wins": 0, "b_wins": 0, "total": 0},
    }


@router.get("/engines")
async def get_engines() -> List[Dict[str, Any]]:
    """Return status and tree data for all 4 engines."""
    from engines.titan import titan_engine
    from engines.phantom import phantom_engine
    from engines.surge import surge_engine
    from engines.oracle import oracle_engine

    engines_info = []
    for engine in [titan_engine, phantom_engine, surge_engine, oracle_engine]:
        loop = asyncio.get_event_loop()
        tree_data = await loop.run_in_executor(None, engine.get_tree_data)
        engines_info.append({
            "name": engine.name,
            "trained": tree_data.get("trained", False),
            "tree_data": tree_data,
        })
    return engines_info


@router.get("/stats")
async def get_stats() -> Dict[str, Any]:
    """Return platform-level statistics."""
    from core.database import get_async_conn
    async with get_async_conn() as conn:
        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM players")
        row = await cursor.fetchone()
        player_count = row["cnt"] if row else 0

        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM matches")
        row = await cursor.fetchone()
        match_count = row["cnt"] if row else 0

        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM predictions")
        row = await cursor.fetchone()
        pred_count = row["cnt"] if row else 0

        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM bets WHERE status='pending'")
        row = await cursor.fetchone()
        pending_bets = row["cnt"] if row else 0

    return {
        "players": player_count,
        "matches": match_count,
        "predictions": pred_count,
        "pending_bets": pending_bets,
        "bankroll": round(bankroll_manager.balance, 2),
        "starting_bankroll": bankroll_manager.starting_balance,
        "roi_pct": bankroll_manager.roi(),
    }


@router.get("/sim")
async def get_sim_summary() -> Dict[str, Any]:
    """Return paper-trading simulation summary."""
    bets = await get_bets_async(limit=500)
    history = await get_bankroll_history_async(limit=200)
    summary = tracker.summary(bankroll_manager.starting_balance)
    return {
        "bankroll": round(bankroll_manager.balance, 2),
        "starting_bankroll": bankroll_manager.starting_balance,
        "summary": summary,
        "engine_breakdown": tracker.engine_breakdown(),
        "pl_by_day": tracker.pl_by_day(),
        "bankroll_chart": tracker.bankroll_chart_data() or [
            {"ts": h["timestamp"], "balance": h["balance"]} for h in history
        ],
        "recent_bets": bets[:20],
        "parlay_history": [b for b in bets if b.get("bet_type") == "parlay"][:10],
    }


@router.put("/config")
async def update_config(update: ConfigUpdate) -> Dict[str, Any]:
    """Update configuration settings and persist to config.yaml."""
    cfg.save(update.data)
    return {"status": "saved", "data": cfg.data}


@router.get("/config")
async def get_config() -> Dict[str, Any]:
    """Return current configuration."""
    return cfg.data
