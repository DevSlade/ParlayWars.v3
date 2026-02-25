"""
ParlayWars v3 — SURGE Engine (Momentum/Streak Detector)
Date: 2026-02-25

Uses LightGBM with EWMA-smoothed features.
Heavy weight on recent form — designed to capture the "hot hand" effect.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import lightgbm as lgb
    _LGBM_AVAILABLE = True
except ImportError:
    _LGBM_AVAILABLE = False

from core.database import get_h2h_sync
from core.logger import get_logger
from engines.base import BaseEngine
from engines.elo import expected_score
from engines.explainer import explain_prediction
from engines.features import FEATURE_NAMES, build_training_data, compute_features

log = get_logger(__name__)


def _ewma_win_rate(form: List[str], span: int) -> float:
    """
    Compute EWMA-smoothed win rate over the form list.

    Args:
        form: List of 'W'/'L' strings, most recent first.
        span: EWMA span parameter.

    Returns:
        EWMA-smoothed win rate in [0, 1].
    """
    if not form:
        return 0.5
    values = [1.0 if r == "W" else 0.0 for r in reversed(form)]  # oldest first
    series = pd.Series(values)
    ewma = series.ewm(span=span, adjust=True).mean()
    return float(ewma.iloc[-1])


def _surge_features(player: Dict[str, Any]) -> List[float]:
    """
    Compute SURGE-specific momentum features for a single player.
    Returns 8 additional features on top of the base 35.
    """
    form = player.get("form") or []
    return [
        _ewma_win_rate(form, span=3),   # very short-term
        _ewma_win_rate(form, span=5),   # short-term
        _ewma_win_rate(form, span=10),  # medium-term (all available)
        _ewma_win_rate(form, span=20),  # hypothetical long-term (flat for <10 games)
        float(len(form)),               # form history length
        float(player.get("total_games") or 1),
        float(player.get("win_pct") or 50.0) / 100.0,
        float(player.get("recent_win_pct") or 50.0) / 100.0,
    ]


class SurgeEngine(BaseEngine):
    """SURGE — LightGBM momentum-based prediction engine."""

    def __init__(self) -> None:
        if _LGBM_AVAILABLE:
            self._model = lgb.LGBMClassifier(
                n_estimators=300,
                learning_rate=0.05,
                max_depth=6,
                num_leaves=31,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=42,
                n_jobs=-1,
                verbose=-1,
            )
        else:
            # Fallback to sklearn GradientBoosting
            from sklearn.ensemble import GradientBoostingClassifier
            self._model = GradientBoostingClassifier(
                n_estimators=200,
                learning_rate=0.05,
                max_depth=4,
                random_state=42,
            )
        self._trained = False
        self._players: Dict[str, Dict[str, Any]] = {}
        self._importances: Optional[np.ndarray] = None

    @property
    def name(self) -> str:
        return "SURGE"

    def load_players(self, players: List[Dict[str, Any]]) -> None:
        self._players = {p["name"]: p for p in players}

    def _build_surge_X(self, players: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Extend base feature matrix with SURGE-specific momentum features.
        Returns (X_surge, y) where X_surge has 35 + 16 = 51 features.
        """
        import itertools
        from engines.elo import expected_score as elo_exp

        X_rows = []
        y_labels = []
        player_map = {p["name"]: p for p in players}
        names = list(player_map.keys())

        for name_a, name_b in itertools.combinations(names, 2):
            pa = player_map[name_a]
            pb = player_map[name_b]

            base_feat = compute_features(pa, pb)
            surge_a = _surge_features(pa)
            surge_b = _surge_features(pb)
            # Deltas between surge features
            surge_delta = [a - b for a, b in zip(surge_a, surge_b)]

            feat = np.concatenate([base_feat, surge_delta]).astype(np.float32)
            X_rows.append(feat)

            p_elo = elo_exp(float(pa.get("elo") or 1500), float(pb.get("elo") or 1500))
            wr_a = float(pa.get("win_pct") or 50) / 100.0
            wr_b = float(pb.get("win_pct") or 50) / 100.0
            p_wr = wr_a / (wr_a + wr_b + 1e-9)
            prob_a = 0.6 * p_elo + 0.4 * p_wr
            y_labels.append(1.0 if prob_a > 0.5 else 0.0)

            # Reverse pair
            feat_rev = np.concatenate([
                compute_features(pb, pa),
                [b - a for a, b in zip(surge_a, surge_b)],
            ]).astype(np.float32)
            X_rows.append(feat_rev)
            y_labels.append(1.0 - (1.0 if prob_a > 0.5 else 0.0))

        return np.array(X_rows, dtype=np.float32), np.array(y_labels, dtype=np.float32)

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        if len(X) < 10:
            log.warning("SURGE: too few samples. Skipping.")
            return
        self._model.fit(X, y)
        self._trained = True
        if hasattr(self._model, "feature_importances_"):
            self._importances = self._model.feature_importances_
        log.info("SURGE trained on %d samples.", len(X))

    def train_on_players(self, players: List[Dict[str, Any]]) -> None:
        self.load_players(players)
        X, y = self._build_surge_X(players)
        self.train(X, y)

    def _get_player(self, name: str) -> Dict[str, Any]:
        return self._players.get(name, {"name": name, "elo": 1500.0, "win_pct": 50.0})

    def predict(self, player_a: str, player_b: str) -> Tuple[float, float]:
        pa = self._get_player(player_a)
        pb = self._get_player(player_b)
        h2h = get_h2h_sync(player_a, player_b)
        base_feat = compute_features(pa, pb, h2h)
        surge_a = _surge_features(pa)
        surge_b = _surge_features(pb)
        surge_delta = [a - b for a, b in zip(surge_a, surge_b)]
        feat = np.concatenate([base_feat, surge_delta]).reshape(1, -1).astype(np.float32)

        if self._trained:
            probs = self._model.predict_proba(feat)[0]
            prob_a = float(np.clip(probs[1], 0.01, 0.99))
        else:
            elo_a = float(pa.get("elo") or 1500)
            elo_b = float(pb.get("elo") or 1500)
            prob_a = expected_score(elo_a, elo_b)

        return prob_a, 1.0 - prob_a

    def explain(self, player_a: str, player_b: str) -> str:
        pa = self._get_player(player_a)
        pb = self._get_player(player_b)
        h2h = get_h2h_sync(player_a, player_b)
        feat = compute_features(pa, pb, h2h)
        importances = (
            self._importances[:len(FEATURE_NAMES)].tolist()
            if self._importances is not None
            else [1.0 / len(FEATURE_NAMES)] * len(FEATURE_NAMES)
        )
        ewma3_a = _ewma_win_rate(pa.get("form") or [], 3)
        ewma3_b = _ewma_win_rate(pb.get("form") or [], 3)
        momentum = player_a if ewma3_a > ewma3_b else player_b
        base = explain_prediction(player_a, player_b, feat.tolist(), importances)
        return f"[SURGE momentum] {momentum} has stronger short-term momentum. {base}"

    def get_tree_data(self) -> Dict[str, Any]:
        if not self._trained:
            return {"engine": "SURGE", "trained": False, "nodes": []}

        top_features = []
        if self._importances is not None:
            all_names = FEATURE_NAMES + [f"surge_{i}" for i in range(8)]
            for fname, imp in sorted(
                zip(all_names, self._importances), key=lambda x: x[1], reverse=True
            )[:10]:
                top_features.append({"feature": fname, "importance": float(imp)})

        return {
            "engine": "SURGE",
            "trained": True,
            "model_type": "LightGBM" if _LGBM_AVAILABLE else "GradientBoosting",
            "top_features": top_features,
            "nodes": [],  # LightGBM tree dump is too large; use top features only
        }


# Module-level singleton
surge_engine = SurgeEngine()
