"""
ParlayWars v3 — WebSocket Routes
Date: 2026-02-25

WebSocket endpoints:
  /ws/dashboard  — Live dashboard updates (matches, predictions, bankroll)
  /ws/console    — Real-time log stream from in-memory ring buffer
"""
from __future__ import annotations

import asyncio
import json
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.logger import get_logger, get_ring_buffer

log = get_logger(__name__)
router = APIRouter()

# Connected WebSocket clients
_dashboard_clients: Set[WebSocket] = set()
_console_clients: Set[WebSocket] = set()


async def broadcast_dashboard(data: dict) -> None:
    """Broadcast a message to all connected dashboard clients."""
    dead = set()
    for ws in _dashboard_clients:
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    _dashboard_clients -= dead


@router.websocket("/dashboard")
async def dashboard_ws(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time dashboard updates.
    Pushes live match data, prediction updates, and bankroll changes
    every 5 seconds.
    """
    await websocket.accept()
    _dashboard_clients.add(websocket)
    log.info("Dashboard WebSocket connected (total: %d)", len(_dashboard_clients))

    try:
        while True:
            try:
                # Gather current state
                from core.database import get_matches_async, get_predictions_async
                from sim.bankroll import bankroll_manager
                from sim.tracker import tracker

                live = await get_matches_async(status="live", limit=10)
                upcoming = await get_matches_async(status="scheduled", limit=10)
                predictions = await get_predictions_async(limit=20)

                payload = {
                    "type": "dashboard_update",
                    "live_matches": live,
                    "upcoming_matches": upcoming,
                    "recent_predictions": predictions,
                    "bankroll": round(bankroll_manager.balance, 2),
                    "summary": tracker.summary(bankroll_manager.starting_balance),
                }
                await websocket.send_json(payload)
            except WebSocketDisconnect:
                break
            except Exception as exc:
                log.warning("Dashboard WS send error: %s", exc)
                break

            # Wait 5 seconds between updates
            await asyncio.sleep(5)

    except WebSocketDisconnect:
        log.info("Dashboard WebSocket disconnected.")
    finally:
        _dashboard_clients.discard(websocket)


@router.websocket("/console")
async def console_ws(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for the web console log stream.
    Sends the current ring-buffer contents on connect, then
    streams new entries every 2 seconds.
    """
    await websocket.accept()
    _console_clients.add(websocket)
    log.info("Console WebSocket connected.")

    # Send existing ring-buffer contents
    try:
        initial_logs = get_ring_buffer()
        await websocket.send_json({"type": "log_init", "entries": initial_logs})
    except Exception:
        pass

    last_count = len(get_ring_buffer())

    try:
        while True:
            await asyncio.sleep(2)
            try:
                current_logs = get_ring_buffer()
                new_entries = current_logs[last_count:]
                last_count = len(current_logs)
                if new_entries:
                    await websocket.send_json({"type": "log_append", "entries": new_entries})
            except WebSocketDisconnect:
                break
            except Exception as exc:
                log.warning("Console WS send error: %s", exc)
                break

    except WebSocketDisconnect:
        log.info("Console WebSocket disconnected.")
    finally:
        _console_clients.discard(websocket)
