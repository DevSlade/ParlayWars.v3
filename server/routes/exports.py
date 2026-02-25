"""
ParlayWars v3 — Data Export Routes
Date: 2026-02-25

Export endpoints:
  GET /export/players?format=csv|json
  GET /export/matches?format=csv|json
  GET /export/bets?format=csv|json
  GET /export/predictions?format=csv|json
"""
from __future__ import annotations

import csv
import io
import json
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import Response, StreamingResponse

from core.database import (
    get_all_players_async,
    get_bets_async,
    get_matches_async,
    get_predictions_async,
)
from core.logger import get_logger

log = get_logger(__name__)
router = APIRouter()


def _to_csv(data: list, fieldnames: Optional[list] = None) -> str:
    """Convert a list of dicts to a CSV string."""
    if not data:
        return ""
    fields = fieldnames or list(data[0].keys())
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in data:
        # Flatten nested objects to strings for CSV
        flat = {}
        for k, v in row.items():
            flat[k] = json.dumps(v) if isinstance(v, (dict, list)) else v
        writer.writerow(flat)
    return output.getvalue()


def _make_response(data: list, fmt: str, filename: str) -> Response:
    """Return Response object in the requested format."""
    if fmt.lower() == "csv":
        content = _to_csv(data)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}.csv"},
        )
    else:
        content = json.dumps(data, default=str, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}.json"},
        )


@router.get("/players")
async def export_players(format: str = Query("json", regex="^(json|csv)$")) -> Response:
    """Export all player data."""
    data = await get_all_players_async()
    return _make_response(data, format, "players")


@router.get("/matches")
async def export_matches(
    format: str = Query("json", regex="^(json|csv)$"),
    limit: int = Query(500, le=5000),
) -> Response:
    """Export match history."""
    data = await get_matches_async(limit=limit)
    return _make_response(data, format, "matches")


@router.get("/bets")
async def export_bets(
    format: str = Query("json", regex="^(json|csv)$"),
    limit: int = Query(500, le=5000),
) -> Response:
    """Export paper-trading bet log."""
    data = await get_bets_async(limit=limit)
    return _make_response(data, format, "bets")


@router.get("/predictions")
async def export_predictions(
    format: str = Query("json", regex="^(json|csv)$"),
    limit: int = Query(500, le=5000),
) -> Response:
    """Export prediction history."""
    data = await get_predictions_async(limit=limit)
    return _make_response(data, format, "predictions")
