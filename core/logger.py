"""
ParlayWars v3 — Structured Logger with Ring Buffer
Date: 2026-02-25

Provides:
  - Standard Python logging to console + file
  - In-memory ring buffer of recent log entries (for the Web Console tab)
  - get_ring_buffer() to fetch recent lines as JSON-serialisable list
"""
import logging
import os
import sys
from collections import deque
from datetime import datetime, timezone
from typing import List, Dict, Deque

from core.config import cfg


# ── Ring buffer shared across the whole process ──────────────────────────────
_ring_buffer: Deque[Dict] = deque(maxlen=cfg.get("logging", "ring_buffer_size", default=500))


class _RingBufferHandler(logging.Handler):
    """Appends every log record to the in-memory ring buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        entry = {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "msg": self.format(record),
        }
        _ring_buffer.append(entry)


def get_ring_buffer() -> List[Dict]:
    """Return a snapshot of the current ring-buffer contents."""
    return list(_ring_buffer)


def setup_logging() -> None:
    """Configure root logger: console + optional file + ring buffer handler."""
    level_name: str = cfg.get("logging", "level", default="INFO")
    level = getattr(logging, level_name.upper(), logging.INFO)

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    # Remove any existing handlers to avoid duplicates on reload
    root.handlers.clear()

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    ch.setLevel(level)
    root.addHandler(ch)

    # File handler (optional — skip if path cannot be created)
    log_file: str = cfg.get("logging", "file", default="data/parlayWars.log")
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        fh.setLevel(level)
        root.addHandler(fh)
    except Exception:
        pass  # Non-fatal — continue without file logging

    # Ring-buffer handler
    rbh = _RingBufferHandler()
    rbh.setFormatter(fmt)
    rbh.setLevel(level)
    root.addHandler(rbh)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (call setup_logging() once at app start)."""
    return logging.getLogger(name)
