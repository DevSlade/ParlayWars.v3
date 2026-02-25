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


# ── Edge / Bookie-Beating ─────────────────────────────────────────────────────

@router.get("/edge/opportunities")
async def get_edge_opportunities() -> List[Dict[str, Any]]:
    """
    Return all upcoming matches with positive EV, sorted by Kelly edge score.

    For each match computes: edge_pct, ev, kelly_edge, no_vig_fair_prob,
    vig_pct, and tier flags using engines/edge.py.
    """
    from engines.edge import (
        no_vig_prob, vig as compute_vig,
        expected_value, edge_pct as compute_edge_pct,
        kelly_edge_score,
    )
    from sim.odds_estimator import estimate_odds

    try:
        upcoming = await get_matches_async(status="upcoming")
    except Exception:
        upcoming = []

    results: List[Dict[str, Any]] = []
    for match in upcoming[:50]:
        player_a = match.get("player_a", "")
        player_b = match.get("player_b", "")
        if not player_a or not player_b:
            continue
        try:
            # Get model probability from latest prediction for this match
            preds = await get_predictions_async(limit=500)
            match_preds = [
                p for p in preds
                if p.get("match_id") == match.get("id") and p.get("engine_name") == "ORACLE"
            ]
            if match_preds:
                prob_a = float(match_preds[0].get("prob_a") or 0.5)
                confidence = float(match_preds[0].get("confidence") or 0.5)
                tier = match_preds[0].get("tier", "LEAN")
            else:
                prob_a = 0.5
                confidence = 0.5
                tier = "LEAN"

            # Estimate bookie odds from model probability
            _, dec_a, _, dec_b = estimate_odds(prob_a)
            fair_a, fair_b = no_vig_prob(dec_a, dec_b)
            vig_val = compute_vig(dec_a, dec_b)
            our_edge = compute_edge_pct(prob_a, fair_a)
            ev = expected_value(prob_a, dec_a, stake=10.0)
            k_edge = kelly_edge_score(prob_a, dec_a)

            if ev <= 0:
                continue  # only positive-EV opportunities

            results.append({
                "match_id": match.get("id"),
                "player_a": player_a,
                "player_b": player_b,
                "prob_a": round(prob_a, 4),
                "fair_prob_a": round(fair_a, 4),
                "fair_prob_b": round(fair_b, 4),
                "edge_pct": round(our_edge * 100.0, 2),
                "ev_at_10": round(ev, 2),
                "kelly_edge": round(k_edge, 4),
                "vig_pct": round(vig_val * 100.0, 2),
                "confidence": confidence,
                "tier": tier,
                "decimal_a": round(dec_a, 3),
                "decimal_b": round(dec_b, 3),
                "scheduled_at": match.get("scheduled_at") or match.get("match_time"),
            })
        except Exception as exc:
            log.warning("Edge calc failed for match %s: %s", match.get("id"), exc)

    results.sort(key=lambda x: -x["kelly_edge"])
    return results


@router.get("/edge/clv")
async def get_clv_stats() -> Dict[str, Any]:
    """
    CLV tracking: percentage of bets that beat the closing line, average CLV.

    Reads settled bets with opening_odds_decimal and closing_odds_decimal fields.
    """
    from engines.edge import clv_result

    try:
        bets = await get_bets_async(status="won") + await get_bets_async(status="lost")
    except Exception:
        bets = []

    clv_values: List[float] = []
    beat_count = 0
    for bet in bets:
        opening = bet.get("opening_odds_decimal") or bet.get("odds_decimal")
        closing = bet.get("closing_odds_decimal")
        if not opening or not closing:
            continue
        try:
            our_implied = 1.0 / float(opening)
            clv = clv_result(our_implied, float(closing))
            clv_values.append(clv)
            if clv > 0:
                beat_count += 1
        except Exception:
            continue

    n = len(clv_values)
    return {
        "clv_rate": round(beat_count / n, 4) if n > 0 else 0.0,
        "avg_clv": round(sum(clv_values) / n, 4) if n > 0 else 0.0,
        "total_bets_with_clv": n,
    }


@router.get("/edge/odds-history/{match_id}")
async def get_odds_history(match_id: int) -> List[Dict[str, Any]]:
    """
    Return the full odds movement timeline for a match from cache.

    Returns an empty list if no odds history is stored.
    """
    from core.cache import cache
    history = cache.get(f"odds_history:{match_id}")
    if not history or not isinstance(history, list):
        return []
    return history


# ── Console Command Processor ─────────────────────────────────────────────────

@router.post("/console/command")
async def run_console_command(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a console command string and return a formatted result.

    Supported commands:
      predict A vs B  — run all engines for player A vs B
      status          — overall system status
      bankroll        — current bankroll summary
      retrain [eng]   — retrain all or a specific engine
      accuracy        — overall engine accuracy
      upcoming        — next 10 upcoming matches
      player NAME     — player profile
      h2h A B         — H2H head-to-head stats
      bets [today]    — recent bet log
      edge            — top edge opportunities
      calibration     — model calibration status
      pause sim       — pause auto-betting
      resume sim      — resume auto-betting
      config set K V  — update a config key
      export          — export all data
    """
    cmd = str(payload.get("command", "")).strip().lower()
    if not cmd:
        return {"output": "No command provided. Type 'help' for a list.", "color": "yellow"}

    try:
        # ── predict A vs B ────────────────────────────────────────────
        if cmd.startswith("predict ") and " vs " in cmd:
            parts = cmd[len("predict "):].split(" vs ", 1)
            pa, pb = parts[0].strip().upper(), parts[1].strip().upper()
            from engines.titan import titan_engine
            from engines.phantom import phantom_engine
            from engines.surge import surge_engine
            from engines.oracle import oracle_engine
            lines = [f"🤖 Predicting: {pa} vs {pb}", "─" * 40]
            for engine in [titan_engine, phantom_engine, surge_engine, oracle_engine]:
                try:
                    prob_a, prob_b = engine.predict(pa, pb)
                    conf = max(prob_a, prob_b)
                    tier = engine.confidence_tier(conf)
                    winner = pa if prob_a >= prob_b else pb
                    lines.append(
                        f"  {engine.name:<8} → {winner:<12}  {prob_a*100:.1f}% / {prob_b*100:.1f}%  [{tier}]"
                    )
                except Exception as e:
                    lines.append(f"  {engine.name:<8} → ERROR: {e}")
            return {"output": "\n".join(lines), "color": "white"}

        # ── status ────────────────────────────────────────────────────
        if cmd == "status":
            from sim.bankroll import bankroll_manager
            from sim.tracker import tracker
            s = tracker.summary(bankroll_manager.starting_balance)
            lines = [
                "✅ ParlayWars v3 — ONLINE",
                f"   Bankroll:    ${bankroll_manager.balance:.2f}",
                f"   ROI:         {s['roi_pct']:.2f}%",
                f"   Win Rate:    {s['win_rate']*100:.1f}%",
                f"   Total Bets:  {s['total_bets']}",
                f"   Streak:      {s['current_streak']}",
                f"   Recovery:    {'YES ⚠️' if bankroll_manager.is_in_recovery_mode() else 'No'}",
            ]
            return {"output": "\n".join(lines), "color": "green"}

        # ── bankroll ──────────────────────────────────────────────────
        if cmd == "bankroll":
            from sim.bankroll import bankroll_manager
            from sim.tracker import tracker
            proj = tracker.compound_growth_projection(
                bankroll_manager.starting_balance,
                bankroll_manager.balance,
                days_elapsed=30,
            )
            lines = [
                f"💰 Bankroll: ${bankroll_manager.balance:.2f}",
                f"   Starting:      ${bankroll_manager.starting_balance:.2f}",
                f"   ROI:           {bankroll_manager.roi():.2f}%",
                f"   Daily ROI est: {proj['daily_roi_pct']:.3f}%",
                f"   30d Projection: ${proj['projection_30d']:.2f}",
                f"   90d Projection: ${proj['projection_90d']:.2f}",
                f"   CAGR est:       {proj['cagr_pct']:.1f}%",
            ]
            return {"output": "\n".join(lines), "color": "green"}

        # ── retrain ───────────────────────────────────────────────────
        if cmd.startswith("retrain"):
            target = cmd[len("retrain"):].strip()
            from core.database import get_all_players_async
            players = await get_all_players_async()
            from engines.titan import titan_engine
            from engines.phantom import phantom_engine
            from engines.surge import surge_engine
            import asyncio as _asyncio
            loop = _asyncio.get_event_loop()
            engines_to_train = []
            if not target or target == "all":
                engines_to_train = [titan_engine, phantom_engine, surge_engine]
            elif target == "titan":
                engines_to_train = [titan_engine]
            elif target == "phantom":
                engines_to_train = [phantom_engine]
            elif target == "surge":
                engines_to_train = [surge_engine]
            trained = []
            for eng in engines_to_train:
                await loop.run_in_executor(None, eng.train_on_players, players)
                trained.append(eng.name)
            return {
                "output": f"✅ Retrained: {', '.join(trained)} on {len(players)} players.",
                "color": "green",
            }

        # ── accuracy ──────────────────────────────────────────────────
        if cmd == "accuracy":
            from sim.tracker import tracker
            tiers = tracker.accuracy_by_tier()
            breakdown = tracker.engine_breakdown()
            lines = ["📊 Accuracy by Tier:"]
            for tier, d in tiers.items():
                lines.append(f"  {tier:<8} {d['hit_rate']}%  ({d['wins']}/{d['bets']} bets)")
            lines.append("📊 Engine Breakdown:")
            for eng, d in breakdown.items():
                lines.append(f"  {eng:<8} WR={d['win_rate']*100:.1f}%  P/L=${d['pl']:.2f}")
            return {"output": "\n".join(lines), "color": "white"}

        # ── upcoming ──────────────────────────────────────────────────
        if cmd == "upcoming":
            matches = await get_matches_async(status="upcoming")
            lines = ["📅 Upcoming Matches (next 10):"]
            for m in matches[:10]:
                lines.append(
                    f"  {m.get('player_a','?'):>12} vs {m.get('player_b','?'):<12}  "
                    f"{(m.get('scheduled_at') or m.get('match_time') or '?')[:16]}"
                )
            if not matches:
                lines.append("  No upcoming matches found.")
            return {"output": "\n".join(lines), "color": "white"}

        # ── player NAME ───────────────────────────────────────────────
        if cmd.startswith("player "):
            name = cmd[len("player "):].strip().upper()
            player = await get_player_async(name)
            if not player:
                return {"output": f"Player '{name}' not found.", "color": "red"}
            lines = [
                f"👤 {player['name']}",
                f"   ELO:    {player.get('elo', 1500):.0f}",
                f"   PWR:    {player.get('pwr_rating', 50):.1f}",
                f"   Win%:   {player.get('win_pct', 50):.1f}%",
                f"   Recent: {player.get('recent_win_pct', 50):.1f}%",
                f"   Games:  {player.get('total_games', 0)}",
                f"   Form:   {''.join(player.get('form', [])[:10])}",
            ]
            return {"output": "\n".join(lines), "color": "white"}

        # ── h2h A B ───────────────────────────────────────────────────
        if cmd.startswith("h2h "):
            parts = cmd[4:].strip().split()
            if len(parts) >= 2:
                pa, pb = parts[0].upper(), parts[1].upper()
                h2h = await get_h2h_async(pa, pb)
                rec = h2h.get("h2h", {}) if h2h else {}
                lines = [
                    f"⚔️  {pa} vs {pb}",
                    f"   H2H Record: {rec.get('a_wins',0)}-{rec.get('b_wins',0)} ({rec.get('total',0)} games)",
                    f"   Avg Margin: {rec.get('avg_margin',0):.1f} pts",
                ]
                return {"output": "\n".join(lines), "color": "white"}

        # ── bets ──────────────────────────────────────────────────────
        if cmd.startswith("bets"):
            bets = await get_bets_async(limit=10)
            lines = ["📋 Recent Bets:"]
            for b in bets:
                pl = b.get("profit_loss")
                pl_str = f"${pl:+.2f}" if pl is not None else "pending"
                lines.append(
                    f"  {b.get('placed_at','?')[:16]}  {b.get('predicted_winner','?'):<12}"
                    f"  ${b.get('stake',0):.2f}  {b.get('status','?'):<8}  {pl_str}"
                )
            if not bets:
                lines.append("  No bets found.")
            return {"output": "\n".join(lines), "color": "white"}

        # ── edge ──────────────────────────────────────────────────────
        if cmd == "edge":
            opps = await get_edge_opportunities()
            lines = [f"💡 Top Edge Opportunities ({len(opps)} total):"]
            for opp in opps[:5]:
                lines.append(
                    f"  {opp['player_a']:>12} vs {opp['player_b']:<12}  "
                    f"edge={opp['edge_pct']:.1f}%  EV=${opp['ev_at_10']:.2f}  [{opp['tier']}]"
                )
            if not opps:
                lines.append("  No positive-EV opportunities right now.")
            return {"output": "\n".join(lines), "color": "green"}

        # ── calibration ───────────────────────────────────────────────
        if cmd == "calibration":
            cal = await get_calibration_status()
            lines = ["🔬 Calibration Status:"]
            for eng_name, eng_data in cal.get("engines", {}).items():
                lines.append(
                    f"  {eng_name:<8} brier={eng_data.get('brier',0):.4f}  "
                    f"acc={eng_data.get('rolling_acc',0)*100:.1f}%  {eng_data.get('status','?')}"
                )
            return {"output": "\n".join(lines), "color": "white"}

        # ── pause sim ────────────────────────────────────────────────
        if cmd == "pause sim":
            from sim.bankroll import bankroll_manager
            bankroll_manager._betting_paused = True
            return {"output": "⏸️  Auto-betting PAUSED.", "color": "yellow"}

        # ── resume sim ───────────────────────────────────────────────
        if cmd == "resume sim":
            from sim.bankroll import bankroll_manager
            bankroll_manager._betting_paused = False
            return {"output": "▶️  Auto-betting RESUMED.", "color": "green"}

        # ── config set K V ───────────────────────────────────────────
        if cmd.startswith("config set "):
            parts = cmd[len("config set "):].strip().split(None, 1)
            if len(parts) == 2:
                key, value = parts
                cfg.set(key, value)
                return {"output": f"✅ Config updated: {key} = {value}", "color": "green"}
            return {"output": "Usage: config set <key> <value>", "color": "yellow"}

        # ── export ────────────────────────────────────────────────────
        if cmd == "export":
            try:
                from scripts.export_data import export_all
                export_all()
                return {"output": "✅ Data exported to data/exports/", "color": "green"}
            except Exception as e:
                return {"output": f"Export failed: {e}", "color": "red"}

        # ── unknown command ───────────────────────────────────────────
        return {
            "output": (
                f"Unknown command: '{cmd}'\n"
                "Available: predict A vs B, status, bankroll, retrain, accuracy, "
                "upcoming, player NAME, h2h A B, bets, edge, calibration, "
                "pause sim, resume sim, config set K V, export"
            ),
            "color": "yellow",
        }

    except Exception as exc:
        log.error("Console command failed '%s': %s", cmd, exc)
        return {"output": f"❌ Error: {exc}", "color": "red"}


# ── Calibration Status ────────────────────────────────────────────────────────

@router.get("/calibration")
async def get_calibration_status() -> Dict[str, Any]:
    """
    Return current model calibration status for all engines.

    Computes Brier score, rolling accuracy, and calibration status
    (GOOD / DRIFTING / NEEDS_RETRAIN) for each engine using settled predictions.
    """
    from engines.calibration import (
        brier_score as compute_brier,
        rolling_accuracy,
        calibration_status,
        is_degraded,
    )
    from core.database import get_async_conn

    engine_results: Dict[str, Any] = {}

    try:
        async with get_async_conn() as conn:
            cursor = await conn.execute(
                """
                SELECT p.engine_name, p.prob_a, p.predicted_winner,
                       m.winner AS actual_winner
                FROM predictions p
                JOIN matches m ON p.match_id = m.id
                WHERE m.status = 'completed' AND m.winner IS NOT NULL
                ORDER BY p.id DESC
                LIMIT 500
                """,
            )
            rows = await cursor.fetchall()

        # Group predictions by engine
        engine_preds: Dict[str, list] = {}
        for row in rows:
            eng = (row["engine_name"] if hasattr(row, "__getitem__") else row[0]) or "UNKNOWN"
            try:
                prob_a = float(row["prob_a"] if hasattr(row, "__getitem__") else row[1] or 0.5)
                predicted = (row["predicted_winner"] if hasattr(row, "__getitem__") else row[2]) or ""
                actual = (row["actual_winner"] if hasattr(row, "__getitem__") else row[3]) or ""
            except Exception:
                continue
            outcome = 1 if predicted == actual else 0
            confidence = max(prob_a, 1.0 - prob_a)
            if eng not in engine_preds:
                engine_preds[eng] = []
            engine_preds[eng].append((confidence, outcome))

        for eng, preds in engine_preds.items():
            if not preds:
                continue
            b_score = compute_brier(preds)
            r_acc = rolling_accuracy(preds, window=50)
            status = calibration_status(b_score, 0.25)
            engine_results[eng] = {
                "brier": round(b_score, 4),
                "rolling_acc": round(r_acc, 4),
                "status": status,
                "degraded": is_degraded(r_acc),
                "sample_size": len(preds),
            }

    except Exception as exc:
        log.error("Calibration status query failed: %s", exc)

    overall = "GOOD"
    if any(v.get("status") == "NEEDS_RETRAIN" for v in engine_results.values()):
        overall = "NEEDS_RETRAIN"
    elif any(v.get("status") == "DRIFTING" for v in engine_results.values()):
        overall = "DRIFTING"

    return {
        "engines": engine_results,
        "overall_status": overall,
        "engines_checked": len(engine_results),
    }
