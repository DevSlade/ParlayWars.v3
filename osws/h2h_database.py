"""
OSWS — SQLite Database for scraped h2hggl.com data.
Stores player snapshots and match data fetched by h2h_pipeline.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional

OSWS_DB_PATH = os.environ.get("OSWS_DB_PATH", "data/db/osws.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS osws_players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    rank INTEGER,
    win_pct REAL,
    recent_win_pct REAL,
    total_games INTEGER,
    wins INTEGER,
    losses INTEGER,
    form TEXT,
    raw_json TEXT,
    fetched_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS osws_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_match_id TEXT UNIQUE,
    player_a TEXT,
    player_b TEXT,
    status TEXT DEFAULT 'scheduled',
    score_a INTEGER,
    score_b INTEGER,
    winner TEXT,
    match_date TEXT,
    raw_json TEXT,
    fetched_at TEXT DEFAULT (datetime('now'))
);
"""


def _ensure_dir() -> None:
    os.makedirs(os.path.dirname(OSWS_DB_PATH), exist_ok=True)


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    _ensure_dir()
    conn = sqlite3.connect(OSWS_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    _ensure_dir()
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def upsert_player(player: Dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO osws_players
               (name, rank, win_pct, recent_win_pct, total_games, wins, losses, form, raw_json, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                 rank=excluded.rank, win_pct=excluded.win_pct,
                 recent_win_pct=excluded.recent_win_pct, total_games=excluded.total_games,
                 wins=excluded.wins, losses=excluded.losses, form=excluded.form,
                 raw_json=excluded.raw_json, fetched_at=excluded.fetched_at
            """,
            (
                player.get("name"),
                player.get("rank"),
                player.get("win_pct"),
                player.get("recent_win_pct"),
                player.get("total_games"),
                player.get("wins"),
                player.get("losses"),
                json.dumps(player.get("form") or []),
                json.dumps(player),
                datetime.now(tz=timezone.utc).isoformat(),
            ),
        )


def get_all_players() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM osws_players ORDER BY rank NULLS LAST"
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        try:
            d["form"] = json.loads(d.get("form") or "[]")
        except Exception:
            d["form"] = []
        try:
            raw = json.loads(d.get("raw_json") or "{}")
            d.update({k: v for k, v in raw.items() if k not in d or d[k] is None})
        except Exception:
            pass
        result.append(d)
    return result


def upsert_match(match: Dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO osws_matches
               (api_match_id, player_a, player_b, status, score_a, score_b, winner, match_date, raw_json, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(api_match_id) DO UPDATE SET
                 status=excluded.status, score_a=excluded.score_a, score_b=excluded.score_b,
                 winner=excluded.winner, raw_json=excluded.raw_json, fetched_at=excluded.fetched_at
            """,
            (
                match.get("api_match_id") or "",
                match.get("player_a"),
                match.get("player_b"),
                match.get("status", "scheduled"),
                match.get("score_a"),
                match.get("score_b"),
                match.get("winner"),
                match.get("match_date"),
                json.dumps(match),
                datetime.now(tz=timezone.utc).isoformat(),
            ),
        )


def get_matches(status: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM osws_matches WHERE status=? ORDER BY match_date DESC LIMIT 50",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM osws_matches ORDER BY match_date DESC LIMIT 50"
            ).fetchall()
    return [dict(row) for row in rows]
