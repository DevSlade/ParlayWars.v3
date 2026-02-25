"""
ParlayWars v3 — PHANTOM Engine (Underdog Hunter)
Date: 2026-02-25

Uses Logistic Regression + Random Forest with feature weights biased toward
upset indicators:
  - H2H anomalies (lower-ranked player beats higher-ranked historically)
  - Form reversals (declining favourite vs rising underdog)
  - Inconsistency of the favourite

Flags picks where model probability disagrees with bookie implied probability
by more than 8%.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from core.database import get_h2h_sync
from core.logger import get_logger
from engines.base import BaseEngine
from engines.elo import expected_score
from engines.explainer import explain_prediction
from engines.features import FEATURE_NAMES, build_training_data, compute_features

log = get_logger(__name__)

# Indices of upset-indicator features (higher weight for PHANTOM)
_UPSET_FEATURE_IDX = [
    FEATURE_NAMES.index("h2h_delta"),
    FEATURE_NAMES.index("l3_delta"),
    FEATURE_NAMES.index("l5_delta"),
    FEATURE_NAMES.index("streak_delta"),
    FEATURE_NAMES.index("form_momentum_delta"),
    FEATURE_NAMES.index("consistency_a"),
    FEATURE_NAMES.index("consistency_b"),
]


def _apply_upset_weights(X: np.ndarray) -> np.ndarray:
    """
    Amplify upset-indicator features by 2x to bias the model
    toward detecting underdog victories.
    """
    X_weighted = X.copy()
    for idx in _UPSET_FEATURE_IDX:
        X_weighted[:, idx] *= 2.0
    return X_weighted


class PhantomEngine(BaseEngine):
    """PHANTOM — Underdog Hunter engine combining LogReg and Random Forest."""

    def __init__(self) -> None:
        # Logistic Regression with L2 penalty
        lr = LogisticRegression(
            C=1.0,
            penalty="l2",
            max_iter=1000,
            random_state=42,
        )
        # Random Forest for non-linear upset patterns
        rf = RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1,
        )
        # Soft voting ensemble
        self._model = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", VotingClassifier(
                estimators=[("lr", lr), ("rf", rf)],
                voting="soft",
                weights=[1, 2],  # RF gets double weight
            )),
        ])
        self._trained = False
        self._players: Dict[str, Dict[str, Any]] = {}
        self._importances: Optional[np.ndarray] = None

    @property
    def name(self) -> str:
        return "PHANTOM"

    def load_players(self, players: List[Dict[str, Any]]) -> None:
        self._players = {p["name"]: p for p in players}

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        if len(X) < 10:
            log.warning("PHANTOM: too few samples. Skipping.")
            return
        X_w = _apply_upset_weights(X)
        self._model.fit(X_w, y)
        self._trained = True
        # Extract RF feature importances via the pipeline
        clf = self._model.named_steps["clf"]
        rf_est = dict(clf.named_estimators_).get("rf")
        if rf_est is not None:
            self._importances = rf_est.feature_importances_
        log.info("PHANTOM trained on %d samples.", len(X))

    def train_on_players(self, players: List[Dict[str, Any]]) -> None:
        self.load_players(players)
        X, y = build_training_data(players)
        self.train(X, y)

    def _get_player(self, name: str) -> Dict[str, Any]:
        return self._players.get(name, {"name": name, "elo": 1500.0, "win_pct": 50.0})

    def predict(self, player_a: str, player_b: str) -> Tuple[float, float]:
        pa = self._get_player(player_a)
        pb = self._get_player(player_b)
        h2h = get_h2h_sync(player_a, player_b)
        feat = compute_features(pa, pb, h2h)
        feat_w = _apply_upset_weights(feat.reshape(1, -1))

        if self._trained:
            probs = self._model.predict_proba(feat_w)[0]
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
            self._importances.tolist()
            if self._importances is not None
            else [1.0 / len(FEATURE_NAMES)] * len(FEATURE_NAMES)
        )
        base = explain_prediction(player_a, player_b, feat.tolist(), importances)
        return f"[PHANTOM upset scan] {base}"

    def get_tree_data(self) -> Dict[str, Any]:
        if not self._trained:
            return {"engine": "PHANTOM", "trained": False, "nodes": []}

        clf = self._model.named_steps["clf"]
        rf_est = dict(clf.named_estimators_).get("rf")
        nodes: List[Dict] = []
        if rf_est is not None:
            # Export first tree from the forest
            tree = rf_est.estimators_[0]
            t = tree.tree_
            for i in range(t.node_count):
                if t.feature[i] >= 0:
                    nodes.append({
                        "id": str(i),
                        "feature": FEATURE_NAMES[t.feature[i]] if t.feature[i] < len(FEATURE_NAMES) else f"f{t.feature[i]}",
                        "threshold": float(t.threshold[i]),
                        "left": str(t.children_left[i]),
                        "right": str(t.children_right[i]),
                        "samples": int(t.n_node_samples[i]),
                    })
                else:
                    nodes.append({
                        "id": str(i),
                        "feature": "Leaf",
                        "prob": float(t.value[i][0][1] / (t.value[i][0].sum() + 1e-9)),
                        "samples": int(t.n_node_samples[i]),
                    })

        top_features = []
        if self._importances is not None:
            for fname, imp in sorted(
                zip(FEATURE_NAMES, self._importances), key=lambda x: x[1], reverse=True
            )[:10]:
                top_features.append({"feature": fname, "importance": float(imp)})

        return {"engine": "PHANTOM", "trained": True, "nodes": nodes, "top_features": top_features}


# Module-level singleton
phantom_engine = PhantomEngine()
