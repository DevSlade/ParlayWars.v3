"""
OSWS — Scraper API
FastAPI service exposing scraped h2hggl.com eBasketball data on port 8001.

Usage:
    python -m osws.scraper_api
    uvicorn osws.scraper_api:app --port 8001
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional

# Allow running as: python -m osws.scraper_api from repo root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Run the OSWS pipeline on startup to populate the database."""
    import asyncio
    from osws.h2h_pipeline import run_pipeline
    loop = asyncio.get_event_loop()
    count = await loop.run_in_executor(None, run_pipeline, False)
    log.info("OSWS startup: %d players loaded.", count)
    yield


app = FastAPI(
    title="OSWS — Open Source Web Scraper",
    description="Scrapes h2hggl.com eBasketball data and exposes it as REST endpoints.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok", "service": "OSWS"}


@app.get("/players")
async def get_players() -> List[Dict[str, Any]]:
    """Return all scraped players."""
    from osws.h2h_database import get_all_players
    return get_all_players()


@app.get("/players/{name}")
async def get_player(name: str) -> Dict[str, Any]:
    """Return a single player by name."""
    from osws.h2h_database import get_all_players
    players = get_all_players()
    for p in players:
        if p.get("name", "").upper() == name.upper():
            return p
    raise HTTPException(status_code=404, detail=f"Player '{name}' not found")


@app.get("/matches/live")
async def get_live_matches() -> List[Dict[str, Any]]:
    """Return live matches from OSWS DB."""
    from osws.h2h_database import get_matches
    return get_matches(status="live")


@app.get("/matches/scheduled")
async def get_scheduled_matches() -> List[Dict[str, Any]]:
    """Return scheduled matches from OSWS DB."""
    from osws.h2h_database import get_matches
    return get_matches(status="scheduled")


@app.post("/refresh")
async def refresh_data(force: bool = Query(default=False)) -> Dict[str, Any]:
    """Trigger a fresh data fetch from HudStats API."""
    import asyncio
    from osws.h2h_pipeline import run_pipeline
    loop = asyncio.get_event_loop()
    count = await loop.run_in_executor(None, run_pipeline, force)
    return {"status": "ok", "players": count}


if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("OSWS_PORT", "8001"))
    uvicorn.run("osws.scraper_api:app", host="0.0.0.0", port=port, reload=False)
