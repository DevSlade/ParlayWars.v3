"""
ParlayWars v3 — Configuration Loader
Date: 2026-02-25

Loads config.yaml from disk with validation and default fallbacks.
"""
import os
from pathlib import Path
from typing import Any, Dict
import yaml


# Default configuration values (used when config.yaml is missing keys)
DEFAULTS: Dict[str, Any] = {
    "server": {"host": "0.0.0.0", "port": 8000, "reload": False, "log_level": "info"},
    "database": {"path": "data/db/parlayWars.db"},
    "cache": {"ttl_seconds": 300, "disk_path": "data/cache"},
    "logging": {"level": "INFO", "file": "data/parlayWars.log", "ring_buffer_size": 500},
    "apis": {
        "hudstats": {"base_url": "https://api-h2h.hudstats.com/v1", "enabled": True},
        "esportsbattle": {"base_url": "https://basketball.esportsbattle.com/api", "enabled": True},
        "odds_api": {"base_url": "https://api.the-odds-api.com/v4", "key": "b824c5f93dc1f906c306702b7eb1f6fc", "enabled": True},
        "betsapi": {"base_url": "https://api.b365api.com", "token": "", "sport_id": 151, "league_id": 25067, "enabled": False},
    },
    "scheduler": {"live_poll_interval_seconds": 30, "schedule_poll_interval_seconds": 120, "retrain_after_n_matches": 20, "daily_snapshot_hour": 3},
    "simulation": {"enabled": True, "starting_bankroll": 1000.0, "kelly_fraction": 0.25, "min_confidence": 0.52, "max_parlay_legs": 4, "min_edge_per_leg": 0.03, "flat_bet_amount": 10.0},
    "engines": {
        "titan": {"enabled": True, "n_estimators": 500, "learning_rate": 0.05, "max_depth": 6, "reg_alpha": 0.1, "reg_lambda": 1.0},
        "phantom": {"enabled": True},
        "surge": {"enabled": True},
        "oracle": {"enabled": True, "hidden_size": 32},
    },
    "seed": {"tsv_path": "data/seed/players_seed.tsv"},
}


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Recursively merge override dict into base dict, returning merged copy."""
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


class Config:
    """
    Singleton-style configuration object.
    Loads config.yaml at startup; falls back to DEFAULTS for missing keys.
    """

    def __init__(self, path: str = "config.yaml") -> None:
        self._path = Path(path)
        self._data: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """Load (or reload) configuration from YAML file."""
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
        else:
            raw = {}
        self._data = _deep_merge(DEFAULTS, raw)

    def save(self, updates: Dict[str, Any]) -> None:
        """Merge updates into current config and persist to disk."""
        self._data = _deep_merge(self._data, updates)
        with open(self._path, "w", encoding="utf-8") as fh:
            yaml.dump(self._data, fh, default_flow_style=False, allow_unicode=True)

    def get(self, *keys: str, default: Any = None) -> Any:
        """Retrieve a nested value by key path, e.g. cfg.get('server', 'port')."""
        node = self._data
        for k in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(k, default)
        return node

    @property
    def data(self) -> Dict[str, Any]:
        return self._data


# Module-level singleton — import and use directly
cfg = Config()
