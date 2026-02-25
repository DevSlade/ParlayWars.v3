"""
OSWS — h2h HTTP Client
Fetches player and match data from h2hggl.com and the backing HudStats API.
Falls back to embedded seed CSV when live scraping is unavailable.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import requests

# The h2hggl.com website is backed by the HudStats API for player data
HUDSTATS_BASE = "https://api-h2h.hudstats.com/v1"
H2H_SITE = "https://h2hggl.com/en/ebasketball/players"

HEADERS = {
    "Referer": "https://h2hggl.com/",
    "Origin": "https://h2hggl.com",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; OSWS/1.0; ParlayWarsBot/3.0)",
}
TIMEOUT = 15


def _get_json(url: str, params: Optional[Dict] = None) -> Optional[Any]:
    """Perform a GET request and return parsed JSON, or None on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, params=params or {}, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def fetch_players() -> List[Dict[str, Any]]:
    """
    Fetch all eBasketball player stats from the HudStats API.
    Returns a list of raw player dicts from the API.
    """
    data = _get_json(f"{HUDSTATS_BASE}/participant/nba")
    if data is None:
        return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return (
            data.get("participants")
            or data.get("data")
            or data.get("players")
            or []
        )
    return []


def fetch_live_matches() -> List[Dict[str, Any]]:
    """
    Attempt to fetch live matches. Returns empty list if endpoint is unavailable.
    The HudStats live endpoint is not publicly documented, so this is best-effort.
    """
    # Try several potential endpoint patterns
    for path in ("/matches/live", "/match/live", "/live"):
        data = _get_json(f"{HUDSTATS_BASE}{path}")
        if data is not None:
            raw = (
                data.get("matches")
                or data.get("data")
                or (data if isinstance(data, list) else [])
            )
            return [m for m in raw if isinstance(m, dict)]
    return []


def fetch_scheduled_matches() -> List[Dict[str, Any]]:
    """
    Attempt to fetch upcoming scheduled matches.
    Returns empty list if endpoint is unavailable.
    """
    for path in ("/schedule", "/matches/upcoming", "/matches?status=upcoming"):
        data = _get_json(f"{HUDSTATS_BASE}{path}")
        if data is not None:
            raw = (
                data.get("matches")
                or data.get("schedule")
                or data.get("data")
                or (data if isinstance(data, list) else [])
            )
            return [m for m in raw if isinstance(m, dict)]
    return []
