"""
ParlayWars v3 — TITAN Engine (XGBoost)
Date: 2026-02-25

Modelled after Green Code's "I Trained AI to Predict Sports" YouTube series.
Uses XGBoost gradient boosting with:
  - 500 trees, learning_rate=0.05, max_depth=6
  - L1 regularisation (reg_alpha=0.1)
  - L2 regularisation (reg_lambda=1.0)
  - Dynamic ELO as the dominant feature
  - 35 engineered features per matchup
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import xgboost as xgb

from core.config import cfg
from core.database import get_h2h_sync
from core.logger import get_logger
from engines.base import BaseEngine
from engines.elo import expected_score
from engines.explainer import explain_prediction
from engines.features import FEATURE_NAMES, build_training_data, compute_features

log = get_logger(__name__)


class TitanEngine(BaseEngine):
    """
    TITAN — XGBoost-based primary prediction engine.

    Implements the Green Code YT approach:
    - Gradient boosting with sequential tree learning
    - L1/L2 regularisation to prevent overfitting
    - Feature importances exported for D3.js visualisation
    """

    def __init__(self) -> None:
        titan_cfg = cfg.get("engines", "titan", default={})
        self._model = xgb.XGBClassifier(
            n_estimators=int(titan_cfg.get("n_estimators", 500)),
            learning_rate=float(titan_cfg.get("learning_rate", 0.05)),
            max_depth=int(titan_cfg.get("max_depth", 6)),
            reg_alpha=float(titan_cfg.get("reg_alpha", 0.1)),
            reg_lambda=float(titan_cfg.get("reg_lambda", 1.0)),
            use_label_encoder=False,
            eval_metric="logloss",
            random_state=42,
            n_jobs=-1,
        )
        self._trained = False
        self._players: Dict[str, Dict[str, Any]] = {}
        self._importances: Optional[np.ndarray] = None

    @property
    def name(self) -> str:
        return "TITAN"

    def load_players(self, players: List[Dict[str, Any]]) -> None:
        """Load player data into engine memory."""
        self._players = {p["name"]: p for p in players}

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        """Fit XGBoost on the provided feature matrix and labels."""
        if len(X) < 10:
            log.warning("TITAN: insufficient training samples (%d). Skipping train.", len(X))
            return
        self._model.fit(
            X, y,
            eval_set=[(X, y)],
            verbose=False,
        )
        self._trained = True
        self._importances = self._model.feature_importances_
        log.info("TITAN trained on %d samples. Best logloss logged.", len(X))

    def train_on_players(self, players: List[Dict[str, Any]]) -> None:
        """Build training data from player pool and fit the model."""
        self.load_players(players)
        X, y = build_training_data(players)
        self.train(X, y)

    def _get_player(self, name: str) -> Dict[str, Any]:
        """Return player dict or a placeholder with default stats."""
        return self._players.get(name, {"name": name, "elo": 1500.0, "win_pct": 50.0})

    def predict(self, player_a: str, player_b: str) -> Tuple[float, float]:
        """
        Return (prob_a, prob_b) using the trained XGBoost model.
        Falls back to ELO-based probability if model not yet trained.
        """
        pa = self._get_player(player_a)
        pb = self._get_player(player_b)
        h2h = get_h2h_sync(player_a, player_b)
        feat = compute_features(pa, pb, h2h).reshape(1, -1)

        if self._trained:
            probs = self._model.predict_proba(feat)[0]
            # probs[1] = probability of class 1 (player_a wins)
            prob_a = float(np.clip(probs[1], 0.01, 0.99))
        else:
            # ELO fallback
            elo_a = float(pa.get("elo") or 1500)
            elo_b = float(pb.get("elo") or 1500)
            prob_a = expected_score(elo_a, elo_b)

        prob_b = 1.0 - prob_a
        return prob_a, prob_b

    def explain(self, player_a: str, player_b: str) -> str:
        """Natural-language explanation for the TITAN prediction."""
        pa = self._get_player(player_a)
        pb = self._get_player(player_b)
        h2h = get_h2h_sync(player_a, player_b)
        feat = compute_features(pa, pb, h2h)

        importances = (
            self._importances.tolist()
            if self._importances is not None
            else [1.0 / len(FEATURE_NAMES)] * len(FEATURE_NAMES)
        )
        return explain_prediction(player_a, player_b, feat.tolist(), importances)

    def get_tree_data(self) -> Dict[str, Any]:
        """Export XGBoost tree structure as JSON for D3.js visualisation."""
        if not self._trained:
            return {
                "engine": "TITAN",
                "trained": False,
                "note": "Model not yet trained",
                "nodes": [],
            }

        # Export the first tree's structure
        booster = self._model.get_booster()
        trees_df = booster.trees_to_dataframe()

        # Build a simplified node list for the first tree
        first_tree = trees_df[trees_df["Tree"] == 0].copy()
        nodes: List[Dict[str, Any]] = []
        for _, row in first_tree.iterrows():
            feature = row.get("Feature", "Leaf")
            feat_name = (
                FEATURE_NAMES[int(feature.replace("f", ""))]
                if isinstance(feature, str) and feature.startswith("f") and feature != "Leaf"
                else feature
            )
            node = {
                "id": str(row["ID"]),
                "feature": feat_name,
                "split": float(row["Split"]) if not str(row.get("Split", "")).lower() in ("nan", "none") else None,
                "gain": float(row.get("Gain", 0.0)),
                "cover": float(row.get("Cover", 0.0)),
                "yes": str(row.get("Yes", "")),
                "no": str(row.get("No", "")),
                "leaf": float(row["Gain"]) if row["Feature"] == "Leaf" else None,
            }
            nodes.append(node)

        # Top feature importances for display
        importances_list = []
        if self._importances is not None:
            for fname, imp in sorted(
                zip(FEATURE_NAMES, self._importances),
                key=lambda x: x[1],
                reverse=True,
            )[:10]:
                importances_list.append({"feature": fname, "importance": float(imp)})

        return {
            "engine": "TITAN",
            "trained": True,
            "n_estimators": self._model.n_estimators,
            "max_depth": self._model.max_depth,
            "nodes": nodes,
            "top_features": importances_list,
        }


# Module-level singleton
titan_engine = TitanEngine()
