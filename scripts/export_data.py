"""
ParlayWars v3 — CLI Data Export Script
Date: 2026-02-25

Usage:
    python scripts/export_data.py --format csv     # Export all as CSV
    python scripts/export_data.py --format json    # Export all as JSON (default)
    python scripts/export_data.py --table players  # Export only players

Exports go to data/exports/
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import (
    get_all_players_sync,
    get_sync_conn,
    init_db_sync,
)
from core.logger import setup_logging, get_logger

log = get_logger(__name__)
EXPORT_DIR = "data/exports"


def export_table(table: str, fmt: str) -> None:
    """Export a single table to CSV or JSON."""
    os.makedirs(EXPORT_DIR, exist_ok=True)

    with get_sync_conn() as conn:
        rows_raw = conn.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608

    rows = [dict(r) for r in rows_raw]
    out_path = os.path.join(EXPORT_DIR, f"{table}.{fmt}")

    if fmt == "csv":
        if rows:
            with open(out_path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
                writer.writeheader()
                for row in rows:
                    flat = {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in row.items()}
                    writer.writerow(flat)
    else:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=2, default=str)

    log.info("Exported %d rows from '%s' → %s", len(rows), table, out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="ParlayWars v3 Data Exporter")
    parser.add_argument("--format", choices=["csv", "json"], default="json")
    parser.add_argument("--table", default="all",
                        help="Table to export (players/matches/bets/predictions) or 'all'")
    args = parser.parse_args()

    setup_logging()
    init_db_sync()

    tables = (
        ["players", "matches", "bets", "predictions", "h2h_records", "bankroll_log"]
        if args.table == "all"
        else [args.table]
    )

    for tbl in tables:
        try:
            export_table(tbl, args.format)
        except Exception as exc:
            log.error("Failed to export table '%s': %s", tbl, exc)

    print(f"✅ Exported {len(tables)} table(s) to {EXPORT_DIR}/")


if __name__ == "__main__":
    main()
