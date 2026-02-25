"""
ParlayWars v3 — In-Memory + Disk Cache
Date: 2026-02-25

Two-tier cache:
  1. In-memory dict with TTL (fast, ephemeral)
  2. Disk JSON files (persists across restarts)

Usage:
    cache = Cache()
    cache.set("key", value, ttl=300)
    value = cache.get("key")   # None if expired or missing
"""
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from core.config import cfg
from core.logger import get_logger

log = get_logger(__name__)

_SENTINEL = object()  # used to distinguish missing vs None


class Cache:
    """Thread-safe (GIL-protected) in-memory + disk cache."""

    def __init__(
        self,
        default_ttl: int = 300,
        disk_path: Optional[str] = None,
    ) -> None:
        self._ttl = default_ttl
        self._store: dict[str, tuple[Any, float]] = {}  # key → (value, expiry_ts)
        self._disk_path = Path(disk_path or cfg.get("cache", "disk_path", default="data/cache"))
        self._disk_path.mkdir(parents=True, exist_ok=True)

    # ── Memory operations ─────────────────────────────────────────────────────

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value with a TTL (seconds). Also writes to disk."""
        expiry = time.monotonic() + (ttl if ttl is not None else self._ttl)
        self._store[key] = (value, expiry)
        self._write_disk(key, value, expiry)

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value; returns default if missing or expired. Falls back to disk."""
        entry = self._store.get(key, _SENTINEL)
        if entry is not _SENTINEL:
            value, expiry = entry  # type: ignore[misc]
            if time.monotonic() < expiry:
                return value
            # Expired — purge from memory
            del self._store[key]

        # Try disk fallback
        disk_val = self._read_disk(key)
        if disk_val is not None:
            return disk_val
        return default

    def delete(self, key: str) -> None:
        """Remove a key from memory and disk."""
        self._store.pop(key, None)
        disk_file = self._disk_path / f"{key}.json"
        if disk_file.exists():
            disk_file.unlink(missing_ok=True)

    def clear(self) -> None:
        """Clear all cached values from memory (does not touch disk)."""
        self._store.clear()

    # ── Disk operations ───────────────────────────────────────────────────────

    def _safe_key(self, key: str) -> str:
        """Convert a cache key to a filesystem-safe filename stem."""
        return key.replace("/", "_").replace(":", "_").replace(" ", "_")

    def _write_disk(self, key: str, value: Any, expiry: float) -> None:
        """Persist a cache entry to disk as JSON (best-effort)."""
        try:
            payload = {
                "expiry_abs": time.time() + max(0.0, expiry - time.monotonic()),
                "value": value,
            }
            path = self._disk_path / f"{self._safe_key(key)}.json"
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, default=str)
        except Exception as exc:
            log.debug("Cache disk write failed for key=%s: %s", key, exc)

    def _read_disk(self, key: str) -> Any:
        """Read from disk cache; returns None if missing or expired."""
        path = self._disk_path / f"{self._safe_key(key)}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if time.time() > payload.get("expiry_abs", 0):
                path.unlink(missing_ok=True)
                return None
            return payload.get("value")
        except Exception:
            return None


# Module-level singleton
cache = Cache(
    default_ttl=cfg.get("cache", "ttl_seconds", default=300),
    disk_path=cfg.get("cache", "disk_path", default="data/cache"),
)
