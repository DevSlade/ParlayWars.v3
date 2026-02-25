"""
ParlayWars v3 — APScheduler Background Tasks
Date: 2026-02-25

Scheduled jobs:
  1. Live poll (every 30s): fetch live matches, update scores, settle bets
  2. Schedule poll (every 120s): fetch upcoming matches, generate predictions
  3. Daily snapshot (3 AM UTC): save player ELO/PWR snapshots
  4. Auto retrain (after N match results): retrain all engines

All jobs are async-compatible via APScheduler's AsyncIOScheduler.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from core.config import cfg
from core.database import (
    get_all_players_async,
    get_matches_async,
    init_db_async,
    save_snapshot_sync,
    upsert_match_sync,
)
from core.logger import get_logger

log = get_logger(__name__)

_match_count_since_retrain = 0
_retrain_threshold = cfg.get("scheduler", "retrain_after_n_matches", default=20)


async def _poll_live_matches() -> None:
    """Fetch live matches from API, update DB, settle paper bets."""
    try:
        from sports.ebasketball.adapter import ebasketball_adapter
        from sim.bettor import auto_bettor

        live_matches = await ebasketball_adapter.get_live()
        for match in live_matches:
            match_id = upsert_match_sync(match)
            # If match is completed and has a winner, settle bets
            if match.get("status") == "completed" and match.get("winner"):
                await auto_bettor.settle_match(match_id, match["winner"])
                await _update_player_stats_after_match(match)
    except Exception as exc:
        log.error("Live poll failed: %s", exc)


async def _poll_schedule() -> None:
    """Fetch upcoming matches, generate and store predictions."""
    try:
        from sports.ebasketball.adapter import ebasketball_adapter
        from engines.titan import titan_engine
        from engines.phantom import phantom_engine
        from engines.surge import surge_engine
        from engines.oracle import oracle_engine
        from core.database import save_prediction_async
        from sim.bettor import auto_bettor
        from sim.odds_estimator import estimate_odds

        upcoming = await ebasketball_adapter.get_upcoming()
        for match in upcoming[:20]:  # Limit to 20 per cycle
            match_id = upsert_match_sync(match)
            player_a = match.get("player_a", "")
            player_b = match.get("player_b", "")
            if not player_a or not player_b:
                continue

            for engine in [titan_engine, phantom_engine, surge_engine, oracle_engine]:
                try:
                    prob_a, prob_b = engine.predict(player_a, player_b)
                    confidence = max(prob_a, prob_b)
                    tier = engine.confidence_tier(confidence)
                    explanation = engine.explain(player_a, player_b)
                    tree_data = engine.get_tree_data()
                    predicted_winner = player_a if prob_a >= 0.5 else player_b

                    pred_id = await save_prediction_async({
                        "match_id": match_id,
                        "engine_name": engine.name,
                        "player_a": player_a,
                        "player_b": player_b,
                        "predicted_winner": predicted_winner,
                        "prob_a": prob_a,
                        "prob_b": prob_b,
                        "confidence": confidence,
                        "tier": tier,
                        "explanation": explanation,
                        "tree_data": tree_data,
                        "is_pre_match": True,
                    })

                    # Place paper bet if oracle picks
                    if engine.name == "ORACLE":
                        await auto_bettor.place_bet(
                            match_id=match_id,
                            player_a=player_a,
                            player_b=player_b,
                            prob_a=prob_a,
                            engine_name=engine.name,
                            confidence=confidence,
                            tier=tier,
                        )
                except Exception as exc:
                    log.warning("Engine %s failed for %s vs %s: %s", engine.name, player_a, player_b, exc)

    except Exception as exc:
        log.error("Schedule poll failed: %s", exc)


async def _update_player_stats_after_match(match: Dict[str, Any]) -> None:
    """Update ELO, H2H, and PWR after a completed match."""
    global _match_count_since_retrain
    try:
        from engines.elo import elo_tracker
        from core.database import upsert_player_sync, get_player_sync, upsert_h2h_sync, get_h2h_sync

        player_a = match.get("player_a", "")
        player_b = match.get("player_b", "")
        winner = match.get("winner", "")
        if not all([player_a, player_b, winner]):
            return

        pa = get_player_sync(player_a) or {"name": player_a, "elo": 1500.0, "total_games": 0}
        pb = get_player_sync(player_b) or {"name": player_b, "elo": 1500.0, "total_games": 0}

        new_elo_a, new_elo_b = elo_tracker.record_result(player_a, player_b, winner)

        # Update form: prepend latest result
        def update_form(player: Dict, won: bool) -> List[str]:
            form = player.get("form") or []
            new_result = "W" if won else "L"
            return ([new_result] + form)[:10]

        wins_a = int(pa.get("wins") or 0) + (1 if winner == player_a else 0)
        wins_b = int(pb.get("wins") or 0) + (1 if winner == player_b else 0)
        total_a = int(pa.get("total_games") or 0) + 1
        total_b = int(pb.get("total_games") or 0) + 1

        pa_updated = {**pa, "elo": new_elo_a, "wins": wins_a, "total_games": total_a,
                      "losses": total_a - wins_a,
                      "win_pct": round(wins_a / total_a * 100, 1),
                      "form": update_form(pa, winner == player_a)}
        pb_updated = {**pb, "elo": new_elo_b, "wins": wins_b, "total_games": total_b,
                      "losses": total_b - wins_b,
                      "win_pct": round(wins_b / total_b * 100, 1),
                      "form": update_form(pb, winner == player_b)}

        # Recompute metrics
        from sports.ebasketball.metrics import compute_all_metrics
        from engines.ratings import compute_pwr
        for p_upd in [pa_updated, pb_updated]:
            metrics = compute_all_metrics(p_upd)
            p_upd.update(metrics)
            p_upd["pwr_rating"] = compute_pwr(p_upd)
            upsert_player_sync(p_upd)

        # Update H2H
        score_a = match.get("score_a") or 0
        score_b = match.get("score_b") or 0
        margin = abs(score_a - score_b)
        upsert_h2h_sync(player_a, player_b, winner, margin)

        _match_count_since_retrain += 1
        if _match_count_since_retrain >= _retrain_threshold:
            await _trigger_retrain()
            _match_count_since_retrain = 0

    except Exception as exc:
        log.error("Post-match update failed: %s", exc)


async def _trigger_retrain() -> None:
    """Retrain all engines with latest player data."""
    try:
        from engines.titan import titan_engine
        from engines.phantom import phantom_engine
        from engines.surge import surge_engine

        players = await get_all_players_async()
        if len(players) < 10:
            log.warning("Not enough players to retrain (%d).", len(players))
            return

        log.info("Retraining all engines on %d players...", len(players))
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, titan_engine.train_on_players, players)
        await loop.run_in_executor(None, phantom_engine.train_on_players, players)
        await loop.run_in_executor(None, surge_engine.train_on_players, players)
        log.info("All engines retrained successfully.")
    except Exception as exc:
        log.error("Engine retrain failed: %s", exc)


async def _daily_snapshot() -> None:
    """Save daily ELO/PWR snapshot for all players."""
    try:
        players = await get_all_players_async()
        for p in players:
            save_snapshot_sync(
                player_name=p["name"],
                elo=float(p.get("elo") or 1500.0),
                pwr=float(p.get("pwr_rating") or 50.0),
                win_pct=p.get("win_pct"),
                recent_win_pct=p.get("recent_win_pct"),
            )
        log.info("Daily snapshots saved for %d players.", len(players))
    except Exception as exc:
        log.error("Daily snapshot failed: %s", exc)


async def _run_calibration() -> None:
    """
    Daily calibration: compute Brier score per engine, detect degraded engines,
    and trigger retrain if performance has deteriorated significantly.
    """
    try:
        from engines.calibration import brier_score, calibration_status, rolling_accuracy, is_degraded
        from core.database import get_async_conn

        log.info("Running daily model calibration...")
        async with get_async_conn() as conn:
            # Fetch settled predictions with their actual outcomes
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
            eng = row["engine_name"] or "UNKNOWN"
            prob_a = float(row["prob_a"] or 0.5)
            predicted = row["predicted_winner"] or ""
            actual = row["actual_winner"] or ""
            # Outcome: 1 if prediction was correct, 0 if not
            outcome = 1 if predicted == actual else 0
            # Use the probability of the predicted side
            confidence = prob_a if predicted == (row.get("player_a") or predicted) else 1.0 - prob_a
            if eng not in engine_preds:
                engine_preds[eng] = []
            engine_preds[eng].append((confidence, outcome))

        degraded_engines = []
        for eng, preds in engine_preds.items():
            if not preds:
                continue
            b_score = brier_score(preds)
            r_acc = rolling_accuracy(preds, window=50)
            degraded = is_degraded(r_acc)
            status = calibration_status(b_score, 0.25)  # compare vs baseline 0.25
            log.info(
                "Calibration [%s]: brier=%.4f, rolling_acc=%.1f%%, status=%s, degraded=%s",
                eng, b_score, r_acc * 100, status, degraded,
            )
            if status == "NEEDS_RETRAIN" or degraded:
                degraded_engines.append(eng)

        if degraded_engines:
            log.warning("Degraded engines detected: %s — triggering retrain", degraded_engines)
            await _trigger_retrain()
        else:
            log.info("All engines within calibration thresholds.")

    except Exception as exc:
        log.error("Calibration job failed: %s", exc)


def create_scheduler() -> AsyncIOScheduler:
    """Create and return the configured APScheduler instance."""
    sched_cfg = cfg.get("scheduler", default={})
    live_interval = int(sched_cfg.get("live_poll_interval_seconds", 30))
    schedule_interval = int(sched_cfg.get("schedule_poll_interval_seconds", 120))
    snapshot_hour = int(sched_cfg.get("daily_snapshot_hour", 3))

    scheduler = AsyncIOScheduler(timezone="UTC")

    scheduler.add_job(
        _poll_live_matches,
        trigger=IntervalTrigger(seconds=live_interval),
        id="live_poll",
        name="Live Match Poll",
        max_instances=1,
        misfire_grace_time=10,
    )

    scheduler.add_job(
        _poll_schedule,
        trigger=IntervalTrigger(seconds=schedule_interval),
        id="schedule_poll",
        name="Schedule + Predictions Poll",
        max_instances=1,
        misfire_grace_time=30,
    )

    scheduler.add_job(
        _daily_snapshot,
        trigger=CronTrigger(hour=snapshot_hour, minute=0),
        id="daily_snapshot",
        name="Daily ELO/PWR Snapshot",
        max_instances=1,
    )

    scheduler.add_job(
        _run_calibration,
        trigger=CronTrigger(hour=4, minute=30),
        id="calibration",
        name="Model Auto-Calibration",
        max_instances=1,
    )

    log.info(
        "Scheduler configured: live=%ds, schedule=%ds, snapshot=%d:00 UTC",
        live_interval, schedule_interval, snapshot_hour,
    )
    return scheduler
