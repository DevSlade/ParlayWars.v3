"""
ParlayWars v3 — SQLite Database Layer
Date: 2026-02-25

All database interactions go through this module.
Uses aiosqlite for async access from FastAPI, and sqlite3 for sync scripts.
"""
import json
import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional, Tuple

import aiosqlite

from core.config import cfg
from core.logger import get_logger

log = get_logger(__name__)

DB_PATH: str = cfg.get("database", "path", default="data/db/parlayWars.db")

# DDL for all 9 tables
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    sport TEXT DEFAULT 'ebasketball',
    rank INTEGER,
    elo REAL DEFAULT 1500.0,
    pwr_rating REAL DEFAULT 50.0,
    win_pct REAL, recent_win_pct REAL,
    total_games INTEGER, wins INTEGER, losses INTEGER,
    form TEXT,
    avg_points REAL, avg_fg_pct REAL, avg_reb REAL, avg_ast REAL,
    avg_stl REAL, avg_blk REAL, avg_tov REAL,
    clutch_index REAL, consistency_score REAL, upset_resistance REAL,
    fade_factor REAL, oqr REAL, form_velocity REAL, bounce_back_rate REAL,
    last_updated TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport TEXT DEFAULT 'ebasketball',
    player_a TEXT NOT NULL, player_b TEXT NOT NULL,
    winner TEXT, score_a INTEGER, score_b INTEGER,
    quarter_scores TEXT,
    match_date TEXT, source TEXT, api_match_id TEXT UNIQUE,
    status TEXT DEFAULT 'scheduled',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS h2h_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_a TEXT NOT NULL, player_b TEXT NOT NULL,
    a_wins INTEGER DEFAULT 0, b_wins INTEGER DEFAULT 0,
    total INTEGER DEFAULT 0, avg_margin REAL DEFAULT 0,
    last_played TEXT,
    UNIQUE(player_a, player_b)
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER, engine_name TEXT NOT NULL,
    player_a TEXT, player_b TEXT,
    predicted_winner TEXT, prob_a REAL, prob_b REAL,
    confidence REAL, tier TEXT,
    explanation TEXT, tree_data TEXT,
    is_pre_match INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER, bet_type TEXT DEFAULT 'straight',
    stake REAL, odds_american INTEGER, odds_decimal REAL,
    predicted_winner TEXT, actual_winner TEXT,
    profit_loss REAL, engine_used TEXT, confidence REAL, tier TEXT,
    parlay_id INTEGER,
    status TEXT DEFAULT 'pending',
    placed_at TEXT DEFAULT (datetime('now')),
    settled_at TEXT
);

CREATE TABLE IF NOT EXISTS bankroll_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    balance REAL, action TEXT, bet_id INTEGER, amount REAL
);

CREATE TABLE IF NOT EXISTS engine_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER, engine_name TEXT,
    vote TEXT, probability REAL, is_pre_match INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS model_training_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engine_name TEXT, accuracy REAL,
    features_used TEXT, hyperparams TEXT,
    samples_count INTEGER,
    trained_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS player_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_name TEXT, snapshot_date TEXT,
    elo REAL, pwr_rating REAL, win_pct REAL, recent_win_pct REAL,
    created_at TEXT DEFAULT (datetime('now'))
);
"""


def _ensure_db_dir() -> None:
    """Create the DB directory if it does not exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


# ── Synchronous helpers (for scripts / startup) ──────────────────────────────

@contextmanager
def get_sync_conn() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for a synchronous SQLite connection."""
    _ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db_sync() -> None:
    """Create all tables if they do not exist (synchronous — use at startup)."""
    _ensure_db_dir()
    with get_sync_conn() as conn:
        conn.executescript(SCHEMA_SQL)
    log.info("Database initialised at %s", DB_PATH)


# ── Async helpers (for FastAPI) ───────────────────────────────────────────────

@asynccontextmanager
async def get_async_conn() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async context manager for an aiosqlite connection."""
    _ensure_db_dir()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL;")
        yield conn
        await conn.commit()


async def init_db_async() -> None:
    """Create all tables if they do not exist (async — use in FastAPI lifespan)."""
    _ensure_db_dir()
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.executescript(SCHEMA_SQL)
        await conn.commit()
    log.info("Database initialised (async) at %s", DB_PATH)


# ── Player helpers ────────────────────────────────────────────────────────────

def upsert_player_sync(player: Dict[str, Any]) -> None:
    """Insert or update a player record (sync)."""
    with get_sync_conn() as conn:
        form_json = json.dumps(player.get("form") or [])
        conn.execute(
            """INSERT INTO players
               (name, sport, rank, elo, pwr_rating, win_pct, recent_win_pct,
                total_games, wins, losses, form,
                avg_points, avg_fg_pct, avg_reb, avg_ast, avg_stl, avg_blk, avg_tov,
                clutch_index, consistency_score, upset_resistance,
                fade_factor, oqr, form_velocity, bounce_back_rate, last_updated)
               VALUES
               (:name, :sport, :rank, :elo, :pwr_rating, :win_pct, :recent_win_pct,
                :total_games, :wins, :losses, :form,
                :avg_points, :avg_fg_pct, :avg_reb, :avg_ast, :avg_stl, :avg_blk, :avg_tov,
                :clutch_index, :consistency_score, :upset_resistance,
                :fade_factor, :oqr, :form_velocity, :bounce_back_rate, :last_updated)
               ON CONFLICT(name) DO UPDATE SET
                 sport=excluded.sport, rank=excluded.rank, elo=excluded.elo,
                 pwr_rating=excluded.pwr_rating, win_pct=excluded.win_pct,
                 recent_win_pct=excluded.recent_win_pct, total_games=excluded.total_games,
                 wins=excluded.wins, losses=excluded.losses, form=excluded.form,
                 avg_points=excluded.avg_points, avg_fg_pct=excluded.avg_fg_pct,
                 avg_reb=excluded.avg_reb, avg_ast=excluded.avg_ast,
                 avg_stl=excluded.avg_stl, avg_blk=excluded.avg_blk, avg_tov=excluded.avg_tov,
                 clutch_index=excluded.clutch_index, consistency_score=excluded.consistency_score,
                 upset_resistance=excluded.upset_resistance, fade_factor=excluded.fade_factor,
                 oqr=excluded.oqr, form_velocity=excluded.form_velocity,
                 bounce_back_rate=excluded.bounce_back_rate, last_updated=excluded.last_updated
            """,
            {
                "name": player.get("name"),
                "sport": player.get("sport", "ebasketball"),
                "rank": player.get("rank"),
                "elo": player.get("elo", 1500.0),
                "pwr_rating": player.get("pwr_rating", 50.0),
                "win_pct": player.get("win_pct"),
                "recent_win_pct": player.get("recent_win_pct"),
                "total_games": player.get("total_games"),
                "wins": player.get("wins"),
                "losses": player.get("losses"),
                "form": form_json,
                "avg_points": player.get("avg_points"),
                "avg_fg_pct": player.get("avg_fg_pct"),
                "avg_reb": player.get("avg_reb"),
                "avg_ast": player.get("avg_ast"),
                "avg_stl": player.get("avg_stl"),
                "avg_blk": player.get("avg_blk"),
                "avg_tov": player.get("avg_tov"),
                "clutch_index": player.get("clutch_index"),
                "consistency_score": player.get("consistency_score"),
                "upset_resistance": player.get("upset_resistance"),
                "fade_factor": player.get("fade_factor"),
                "oqr": player.get("oqr"),
                "form_velocity": player.get("form_velocity"),
                "bounce_back_rate": player.get("bounce_back_rate"),
                "last_updated": player.get("last_updated", datetime.now(tz=timezone.utc).isoformat()),
            },
        )


def get_player_count_sync() -> int:
    """Return the number of players in the database (sync)."""
    with get_sync_conn() as conn:
        row = conn.execute("SELECT COUNT(*) FROM players").fetchone()
    return row[0] if row else 0


def get_match_count_sync() -> int:
    """Return the number of matches in the database (sync)."""
    with get_sync_conn() as conn:
        row = conn.execute("SELECT COUNT(*) FROM matches").fetchone()
    return row[0] if row else 0


def get_all_players_sync() -> List[Dict[str, Any]]:
    """Return all players as list of dicts (sync)."""
    with get_sync_conn() as conn:
        rows = conn.execute("SELECT * FROM players ORDER BY rank NULLS LAST, elo DESC").fetchall()
    result = []
    for row in rows:
        d = dict(row)
        if d.get("form"):
            try:
                d["form"] = json.loads(d["form"])
            except Exception:
                d["form"] = []
        result.append(d)
    return result


def get_player_sync(name: str) -> Optional[Dict[str, Any]]:
    """Return a single player dict by name (sync)."""
    with get_sync_conn() as conn:
        row = conn.execute("SELECT * FROM players WHERE name=?", (name,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    if d.get("form"):
        try:
            d["form"] = json.loads(d["form"])
        except Exception:
            d["form"] = []
    return d


async def get_all_players_async() -> List[Dict[str, Any]]:
    """Return all players as list of dicts (async)."""
    async with get_async_conn() as conn:
        cursor = await conn.execute("SELECT * FROM players ORDER BY rank NULLS LAST, elo DESC")
        rows = await cursor.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        if d.get("form"):
            try:
                d["form"] = json.loads(d["form"])
            except Exception:
                d["form"] = []
        result.append(d)
    return result


async def get_player_async(name: str) -> Optional[Dict[str, Any]]:
    """Return a single player dict by name (async)."""
    async with get_async_conn() as conn:
        cursor = await conn.execute("SELECT * FROM players WHERE name=?", (name,))
        row = await cursor.fetchone()
    if row is None:
        return None
    d = dict(row)
    if d.get("form"):
        try:
            d["form"] = json.loads(d["form"])
        except Exception:
            d["form"] = []
    return d


# ── Match helpers ─────────────────────────────────────────────────────────────

def upsert_match_sync(match: Dict[str, Any]) -> int:
    """Insert or update a match; returns the match id."""
    with get_sync_conn() as conn:
        qs_json = json.dumps(match.get("quarter_scores") or {})
        cur = conn.execute(
            """INSERT INTO matches
               (sport, player_a, player_b, winner, score_a, score_b,
                quarter_scores, match_date, source, api_match_id, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(api_match_id) DO UPDATE SET
                 winner=excluded.winner, score_a=excluded.score_a, score_b=excluded.score_b,
                 quarter_scores=excluded.quarter_scores, status=excluded.status
            """,
            (
                match.get("sport", "ebasketball"),
                match.get("player_a"), match.get("player_b"),
                match.get("winner"), match.get("score_a"), match.get("score_b"),
                qs_json, match.get("match_date"),
                match.get("source"), match.get("api_match_id"), match.get("status", "scheduled"),
            ),
        )
        return cur.lastrowid or 0


async def get_matches_async(status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Return matches, optionally filtered by status."""
    async with get_async_conn() as conn:
        if status:
            cursor = await conn.execute(
                "SELECT * FROM matches WHERE status=? ORDER BY match_date DESC LIMIT ?",
                (status, limit),
            )
        else:
            cursor = await conn.execute(
                "SELECT * FROM matches ORDER BY match_date DESC LIMIT ?", (limit,)
            )
        rows = await cursor.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        if d.get("quarter_scores"):
            try:
                d["quarter_scores"] = json.loads(d["quarter_scores"])
            except Exception:
                d["quarter_scores"] = {}
        result.append(d)
    return result


# ── H2H helpers ───────────────────────────────────────────────────────────────

def upsert_h2h_sync(player_a: str, player_b: str, winner: str, margin: float = 0.0) -> None:
    """Update H2H record after a completed match (sync)."""
    # Normalise key order (alphabetical)
    a, b = sorted([player_a, player_b])
    with get_sync_conn() as conn:
        conn.execute(
            """INSERT INTO h2h_records (player_a, player_b, a_wins, b_wins, total, avg_margin, last_played)
               VALUES (?, ?, 0, 0, 0, 0, ?)
               ON CONFLICT(player_a, player_b) DO NOTHING""",
            (a, b, datetime.now(tz=timezone.utc).isoformat()),
        )
        if winner == a:
            conn.execute(
                """UPDATE h2h_records SET a_wins=a_wins+1, total=total+1,
                   avg_margin=(avg_margin*total + ?)/(total+1), last_played=?
                   WHERE player_a=? AND player_b=?""",
                (margin, datetime.now(tz=timezone.utc).isoformat(), a, b),
            )
        else:
            conn.execute(
                """UPDATE h2h_records SET b_wins=b_wins+1, total=total+1,
                   avg_margin=(avg_margin*total + ?)/(total+1), last_played=?
                   WHERE player_a=? AND player_b=?""",
                (margin, datetime.now(tz=timezone.utc).isoformat(), a, b),
            )


def get_h2h_sync(player_a: str, player_b: str) -> Optional[Dict[str, Any]]:
    """Return H2H record between two players (normalised key order)."""
    a, b = sorted([player_a, player_b])
    with get_sync_conn() as conn:
        row = conn.execute(
            "SELECT * FROM h2h_records WHERE player_a=? AND player_b=?", (a, b)
        ).fetchone()
    return dict(row) if row else None


async def get_h2h_async(player_a: str, player_b: str) -> Optional[Dict[str, Any]]:
    """Async H2H lookup."""
    a, b = sorted([player_a, player_b])
    async with get_async_conn() as conn:
        cursor = await conn.execute(
            "SELECT * FROM h2h_records WHERE player_a=? AND player_b=?", (a, b)
        )
        row = await cursor.fetchone()
    return dict(row) if row else None


# ── Prediction helpers ────────────────────────────────────────────────────────

async def save_prediction_async(pred: Dict[str, Any]) -> int:
    """Insert a prediction and return its id."""
    async with get_async_conn() as conn:
        cursor = await conn.execute(
            """INSERT INTO predictions
               (match_id, engine_name, player_a, player_b,
                predicted_winner, prob_a, prob_b, confidence, tier,
                explanation, tree_data, is_pre_match)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pred.get("match_id"), pred.get("engine_name"),
                pred.get("player_a"), pred.get("player_b"),
                pred.get("predicted_winner"), pred.get("prob_a"), pred.get("prob_b"),
                pred.get("confidence"), pred.get("tier", "LOW"),
                pred.get("explanation"),
                json.dumps(pred.get("tree_data") or {}),
                int(pred.get("is_pre_match", True)),
            ),
        )
        return cursor.lastrowid or 0


async def get_predictions_async(limit: int = 50) -> List[Dict[str, Any]]:
    """Return recent predictions."""
    async with get_async_conn() as conn:
        cursor = await conn.execute(
            "SELECT * FROM predictions ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        if d.get("tree_data"):
            try:
                d["tree_data"] = json.loads(d["tree_data"])
            except Exception:
                d["tree_data"] = {}
        result.append(d)
    return result


# ── Bet helpers ───────────────────────────────────────────────────────────────

async def save_bet_async(bet: Dict[str, Any]) -> int:
    """Insert a paper bet and return its id."""
    async with get_async_conn() as conn:
        cursor = await conn.execute(
            """INSERT INTO bets
               (match_id, bet_type, stake, odds_american, odds_decimal,
                predicted_winner, engine_used, confidence, tier, parlay_id, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                bet.get("match_id"), bet.get("bet_type", "straight"),
                bet.get("stake"), bet.get("odds_american"), bet.get("odds_decimal"),
                bet.get("predicted_winner"), bet.get("engine_used"),
                bet.get("confidence"), bet.get("tier", "LOW"),
                bet.get("parlay_id"), bet.get("status", "pending"),
            ),
        )
        return cursor.lastrowid or 0


async def settle_bet_async(bet_id: int, actual_winner: str, profit_loss: float) -> None:
    """Update a bet after the match result is known."""
    from datetime import datetime, timezone
    status = "won" if profit_loss > 0 else "lost"
    async with get_async_conn() as conn:
        await conn.execute(
            """UPDATE bets SET actual_winner=?, profit_loss=?, status=?, settled_at=?
               WHERE id=?""",
            (actual_winner, profit_loss, status,
             datetime.now(tz=timezone.utc).isoformat(), bet_id),
        )


async def get_bets_async(status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Return bets, optionally filtered by status."""
    async with get_async_conn() as conn:
        if status:
            cursor = await conn.execute(
                "SELECT * FROM bets WHERE status=? ORDER BY placed_at DESC LIMIT ?",
                (status, limit),
            )
        else:
            cursor = await conn.execute(
                "SELECT * FROM bets ORDER BY placed_at DESC LIMIT ?", (limit,)
            )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# ── Bankroll helpers ──────────────────────────────────────────────────────────

async def log_bankroll_async(balance: float, action: str, amount: float, bet_id: Optional[int] = None) -> None:
    """Append a bankroll entry."""
    async with get_async_conn() as conn:
        await conn.execute(
            "INSERT INTO bankroll_log (balance, action, bet_id, amount) VALUES (?, ?, ?, ?)",
            (balance, action, bet_id, amount),
        )


async def get_bankroll_history_async(limit: int = 200) -> List[Dict[str, Any]]:
    """Return bankroll log entries."""
    async with get_async_conn() as conn:
        cursor = await conn.execute(
            "SELECT * FROM bankroll_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# ── Snapshot helpers ──────────────────────────────────────────────────────────

def save_snapshot_sync(player_name: str, elo: float, pwr: float, win_pct: Optional[float], recent_win_pct: Optional[float]) -> None:
    """Save daily player snapshot (sync)."""
    today = datetime.now(tz=timezone.utc).date().isoformat()
    with get_sync_conn() as conn:
        conn.execute(
            """INSERT INTO player_snapshots (player_name, snapshot_date, elo, pwr_rating, win_pct, recent_win_pct)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (player_name, today, elo, pwr, win_pct, recent_win_pct),
        )


# ── Training log helpers ──────────────────────────────────────────────────────

def log_training_sync(engine_name: str, accuracy: float, features: List[str], hyperparams: Dict, samples: int) -> None:
    """Record a model training run (sync)."""
    with get_sync_conn() as conn:
        conn.execute(
            """INSERT INTO model_training_log (engine_name, accuracy, features_used, hyperparams, samples_count)
               VALUES (?, ?, ?, ?, ?)""",
            (engine_name, accuracy, json.dumps(features), json.dumps(hyperparams), samples),
        )


# ── Auto-initialise on import ─────────────────────────────────────────────────
# Ensure tables exist whenever this module is loaded (sync, lightweight).
try:
    init_db_sync()
except Exception as _db_init_err:  # pragma: no cover
    log.warning("Auto DB init failed: %s", _db_init_err)
