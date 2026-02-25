"""
ParlayWars v3 — REST API Routes
Date: 2026-02-25

Endpoints:
  GET  /api/players                 — All players with stats
  GET  /api/players/{name}          — Single player profile
  GET  /api/matches                 — Recent/live/upcoming matches
  GET  /api/predictions             — Recent predictions
  POST /api/predict                 — Request prediction for two players
  GET  /api/h2h/{a}/{b}             — H2H comparison
  GET  /api/engines                 — Engine status and tree data
  GET  /api/engines/accuracy        — Per-engine accuracy + tier breakdown
  GET  /api/stats                   — Platform statistics
  GET  /api/stats/regression        — Regression / bounce-back candidates
  GET  /api/sim                     — Simulation summary (with drawdown data)
  GET  /api/bets/{id}/postmortem    — Post-game "What Happened?" analysis
  GET  /api/freshness               — Last API sync timestamps
  PUT  /api/config                  — Update configuration
  GET  /api/config                  — Read configuration
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
    # Build drawdown-annotated chart data; fall back to DB history if tracker is empty
    drawdown_data = tracker.drawdown_chart_data() or [
        {"ts": h["timestamp"], "balance": h["balance"], "peak": h["balance"],
         "drawdown": 0, "drawdown_pct": 0}
        for h in history
    ]
    return {
        "bankroll": round(bankroll_manager.balance, 2),
        "starting_bankroll": bankroll_manager.starting_balance,
        "summary": summary,
        "best_streak": tracker.best_streak(),
        "worst_streak": tracker.worst_streak(),
        "engine_breakdown": tracker.engine_breakdown(),
        "pl_by_day": tracker.pl_by_day(),
        "bankroll_chart": drawdown_data,
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


# ── Engine accuracy tracker ───────────────────────────────────────────────────

@router.get("/engines/accuracy")
async def get_engine_accuracy() -> Dict[str, Any]:
    """
    Return per-engine prediction accuracy vs settled bet outcomes.
    Also breaks down by confidence tier (LOCK/STRONG/LEAN/SKIP).
    """
    from core.database import get_async_conn
    async with get_async_conn() as conn:
        # For each engine, join predictions to settled bets
        cursor = await conn.execute(
            """
            SELECT p.engine_name,
                   p.tier,
                   p.predicted_winner,
                   b.actual_winner,
                   CASE WHEN p.predicted_winner = b.actual_winner THEN 1 ELSE 0 END AS correct
            FROM predictions p
            JOIN bets b ON b.match_id = p.match_id AND b.engine_used = p.engine_name
            WHERE b.status IN ('won','lost')
            """
        )
        rows = await cursor.fetchall()

    by_engine: Dict[str, Dict] = {}
    by_tier: Dict[str, Dict] = {}
    for row in rows:
        eng = row["engine_name"]
        tier = row["tier"] or "SKIP"
        correct = bool(row["correct"])

        if eng not in by_engine:
            by_engine[eng] = {"correct": 0, "total": 0}
        by_engine[eng]["total"] += 1
        if correct:
            by_engine[eng]["correct"] += 1

        tier_key = f"{eng}:{tier}"
        if tier_key not in by_tier:
            by_tier[tier_key] = {"engine": eng, "tier": tier, "correct": 0, "total": 0}
        by_tier[tier_key]["total"] += 1
        if correct:
            by_tier[tier_key]["correct"] += 1

    engine_acc = {
        eng: {
            "total": d["total"],
            "accuracy": round(d["correct"] / d["total"] * 100, 1) if d["total"] > 0 else 0.0,
        }
        for eng, d in by_engine.items()
    }
    tier_acc = [
        {
            "engine": d["engine"], "tier": d["tier"],
            "total": d["total"],
            "accuracy": round(d["correct"] / d["total"] * 100, 1) if d["total"] > 0 else 0.0,
        }
        for d in by_tier.values()
    ]
    return {
        "by_engine": engine_acc,
        "by_tier": sorted(tier_acc, key=lambda x: (x["engine"], x["tier"])),
        "sim_accuracy_by_tier": tracker.accuracy_by_tier(),
        "best_streak": tracker.best_streak(),
        "worst_streak": tracker.worst_streak(),
        "current_streak": tracker.current_streak(),
    }


# ── Regression / bounce-back detection ───────────────────────────────────────

@router.get("/stats/regression")
async def get_regression_candidates() -> Dict[str, Any]:
    """
    Return players flagged as REGRESSION CANDIDATES (recent WR >> career WR)
    or BOUNCE-BACK CANDIDATES (recent WR << career WR).
    Threshold: 10 percentage-point gap.
    """
    players = await get_all_players_async()
    regression = []
    bounce_back = []
    for p in players:
        career = float(p.get("win_pct") or 50.0)
        recent = float(p.get("recent_win_pct") or career)
        gap = recent - career
        if gap >= 10.0:
            regression.append({
                "name": p["name"], "career_wr": career,
                "recent_wr": recent, "gap": round(gap, 1),
            })
        elif gap <= -10.0:
            bounce_back.append({
                "name": p["name"], "career_wr": career,
                "recent_wr": recent, "gap": round(gap, 1),
            })
    # Sort by absolute gap descending
    regression.sort(key=lambda x: -x["gap"])
    bounce_back.sort(key=lambda x: x["gap"])
    return {"regression_candidates": regression, "bounce_back_candidates": bounce_back}


# ── Postmortem — "What Happened?" on a losing bet ────────────────────────────

@router.get("/bets/{bet_id}/postmortem")
async def get_bet_postmortem(bet_id: int) -> Dict[str, Any]:
    """
    For a settled bet, return full post-game analysis:
    - What each engine predicted
    - What actually happened
    - Which engine was correct / dissenting
    - Score of the match (if available)
    """
    from core.database import get_async_conn
    async with get_async_conn() as conn:
        # Fetch the bet
        cursor = await conn.execute("SELECT * FROM bets WHERE id=?", (bet_id,))
        bet = await cursor.fetchone()
        if not bet:
            raise HTTPException(status_code=404, detail="Bet not found")
        bet = dict(bet)

        match_id = bet.get("match_id")
        match: Optional[Dict] = None
        engine_preds: List[Dict] = []

        if match_id:
            cursor = await conn.execute("SELECT * FROM matches WHERE id=?", (match_id,))
            m = await cursor.fetchone()
            if m:
                match = dict(m)

            cursor = await conn.execute(
                "SELECT * FROM predictions WHERE match_id=?", (match_id,)
            )
            preds_rows = await cursor.fetchall()
            engine_preds = [dict(r) for r in preds_rows]

    dissenting = [
        p["engine_name"] for p in engine_preds
        if p.get("predicted_winner") == bet.get("actual_winner")
        and p.get("engine_name") != bet.get("engine_used")
    ]

    return {
        "bet": bet,
        "match": match,
        "engine_predictions": engine_preds,
        "correct_engines": [
            p["engine_name"] for p in engine_preds
            if p.get("predicted_winner") == bet.get("actual_winner")
        ],
        "dissenting_engines": dissenting,
        "summary": (
            f"{bet.get('engine_used','?')} predicted {bet.get('predicted_winner','?')} "
            f"but {bet.get('actual_winner','?')} won. "
            + (f"Dissenting engine(s) were correct: {', '.join(dissenting)}." if dissenting else "No engine predicted correctly.")
        ),
    }


# ── Data freshness ────────────────────────────────────────────────────────────

@router.get("/freshness")
async def get_data_freshness() -> Dict[str, Any]:
    """Return last successful API sync timestamps."""
    from core.cache import cache
    last_hudstats  = cache.get("_last_sync:hudstats") or None
    last_esb       = cache.get("_last_sync:esportsbattle") or None
    return {
        "hudstats":      last_hudstats,
        "esportsbattle": last_esb,
    }
