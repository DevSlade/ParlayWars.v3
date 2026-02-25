"""
ParlayWars v3 — FastAPI Application Factory
Date: 2026-02-25

Sets up:
  - CORS middleware
  - Lifespan events (startup: DB init, engine training, scheduler start)
  - Static file mount for the SPA
  - Route registration
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import cfg
from core.database import init_db_async, get_all_players_async
from core.logger import get_logger, setup_logging
from core.scheduler import create_scheduler

log = get_logger(__name__)
_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan: startup → yield → shutdown."""
    global _scheduler

    # 1. Setup logging
    setup_logging()
    log.info("ParlayWars v3 starting up...")

    # 2. Initialise database
    await init_db_async()

    # 3. Seed database from TSV if players table is empty
    await _seed_if_needed()

    # 4. Train engines on seed data
    await _train_engines()

    # 5. Start background scheduler
    _scheduler = create_scheduler()
    _scheduler.start()
    log.info("Background scheduler started.")

    yield  # ← Server runs here

    # Shutdown
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    log.info("ParlayWars v3 shut down.")


async def _seed_if_needed() -> None:
    """Seed the players table from TSV if it's empty."""
    try:
        players = await get_all_players_async()
        if len(players) == 0:
            log.info("Players table empty — seeding from TSV...")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _run_seed)
            log.info("Seed complete.")
        else:
            log.info("Players table has %d players — skipping seed.", len(players))
    except Exception as exc:
        log.error("Seed failed: %s", exc)


def _run_seed() -> None:
    """Synchronous seed function (run in executor)."""
    from scripts.seed_database import seed_all
    seed_all()


async def _train_engines() -> None:
    """Train all engines on current player data."""
    try:
        players = await get_all_players_async()
        if not players:
            log.warning("No players in DB — engines will use ELO fallback.")
            return

        log.info("Training engines on %d players...", len(players))
        from engines.titan import titan_engine
        from engines.phantom import phantom_engine
        from engines.surge import surge_engine
        from engines.oracle import oracle_engine

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, titan_engine.train_on_players, players)
        await loop.run_in_executor(None, phantom_engine.train_on_players, players)
        await loop.run_in_executor(None, surge_engine.train_on_players, players)

        # Set sub-engines for ORACLE and train with weighted average (no history yet)
        oracle_engine.set_sub_engines([titan_engine, phantom_engine, surge_engine])
        log.info("All engines trained and ready.")
    except Exception as exc:
        log.error("Engine training at startup failed: %s", exc)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="ParlayWars v3",
        description="2K eBasketball AI Prediction & Paper Trading Platform",
        version="3.0.0",
        lifespan=lifespan,
    )

    # CORS — allow all origins for local dev / Cloudflare Tunnel
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes
    from server.routes.api import router as api_router
    from server.routes.ws import router as ws_router
    from server.routes.exports import router as exports_router

    app.include_router(api_router, prefix="/api")
    app.include_router(ws_router, prefix="/ws")
    app.include_router(exports_router, prefix="/export")

    # Serve SPA static files
    static_path = Path(__file__).parent / "static"
    if static_path.exists():
        app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")
    else:
        log.warning("Static directory not found at %s", static_path)

    return app
