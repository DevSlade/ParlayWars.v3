"""
ParlayWars v3 — ORACLE Engine (Meta-Ensemble / Stacking MLP)
Date: 2026-02-25

ORACLE is the final stacking layer:
  Input: [TITAN prob, PHANTOM prob, SURGE prob, bookie implied prob,
          engine disagreement score, average confidence]
  Architecture: Linear(6→32) → ReLU → Dropout(0.2) → Linear(32→16)
                → ReLU → Dropout(0.2) → Linear(16→1) → Sigmoid

Trained on how accurately each sub-engine has historically performed.
Falls back to weighted average of sub-engine probabilities if not trained.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False

from core.config import cfg
from core.logger import get_logger
from engines.base import BaseEngine
from engines.elo import expected_score

log = get_logger(__name__)


class _OracleMLP(nn.Module if _TORCH_AVAILABLE else object):
    """Stacking MLP for combining sub-engine predictions."""

    def __init__(self, hidden_size: int = 32) -> None:
        if not _TORCH_AVAILABLE:
            return
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(6, hidden_size),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_size, 16),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        return self.net(x)


class OracleEngine(BaseEngine):
    """ORACLE — Meta-ensemble stacking engine using a PyTorch MLP."""

    def __init__(self) -> None:
        hidden_size = cfg.get("engines", "oracle", "hidden_size", default=32)
        if _TORCH_AVAILABLE:
            self._mlp = _OracleMLP(hidden_size=hidden_size)
            self._optimizer = optim.Adam(self._mlp.parameters(), lr=1e-3)
            self._criterion = nn.BCELoss()
        self._trained = False
        self._players: Dict[str, Dict[str, Any]] = {}
        self._sub_engines: List[BaseEngine] = []
        self._engine_weights: Dict[str, float] = {
            "TITAN": 0.40,
            "PHANTOM": 0.25,
            "SURGE": 0.35,
        }

    @property
    def name(self) -> str:
        return "ORACLE"

    def set_sub_engines(self, engines: List[BaseEngine]) -> None:
        """Register the sub-engines that ORACLE stacks on top of."""
        self._sub_engines = engines

    def load_players(self, players: List[Dict[str, Any]]) -> None:
        self._players = {p["name"]: p for p in players}

    def _make_meta_features(
        self,
        titan_p: float,
        phantom_p: float,
        surge_p: float,
        bookie_p: float = 0.5,
    ) -> List[float]:
        """
        Construct the 6-element meta-feature vector:
          [titan_p, phantom_p, surge_p, bookie_p, disagreement, avg_confidence]
        """
        probs = [titan_p, phantom_p, surge_p]
        avg_conf = float(np.mean(probs))
        disagreement = float(np.std(probs))
        return [titan_p, phantom_p, surge_p, bookie_p, disagreement, avg_conf]

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        """
        Train the MLP on meta-feature matrix X (N×6) and binary labels y.
        Falls back to weight-averaging if PyTorch not available.
        """
        if not _TORCH_AVAILABLE or len(X) < 10:
            log.warning("ORACLE MLP training skipped (torch=%s, samples=%d).", _TORCH_AVAILABLE, len(X))
            return

        self._mlp.train()
        X_t = torch.tensor(X, dtype=torch.float32)
        y_t = torch.tensor(y, dtype=torch.float32).unsqueeze(1)

        for epoch in range(200):
            self._optimizer.zero_grad()
            preds = self._mlp(X_t)
            loss = self._criterion(preds, y_t)
            loss.backward()
            self._optimizer.step()
            if epoch % 50 == 0:
                log.debug("ORACLE epoch %d loss=%.4f", epoch, loss.item())

        self._trained = True
        log.info("ORACLE MLP trained for 200 epochs.")

    def train_on_sub_engine_history(
        self,
        predictions_history: List[Dict[str, Any]],
    ) -> None:
        """
        Train from historical prediction records.
        Each record should have: titan_p, phantom_p, surge_p, actual_winner, player_a.
        """
        if len(predictions_history) < 10:
            log.warning("ORACLE: insufficient history (%d records). Using weight avg.", len(predictions_history))
            return

        X_rows = []
        y_labels = []
        for rec in predictions_history:
            titan_p = float(rec.get("titan_p", 0.5))
            phantom_p = float(rec.get("phantom_p", 0.5))
            surge_p = float(rec.get("surge_p", 0.5))
            bookie_p = float(rec.get("bookie_p", 0.5))
            actual_winner = rec.get("actual_winner", "")
            player_a = rec.get("player_a", "")
            label = 1.0 if actual_winner == player_a else 0.0
            meta = self._make_meta_features(titan_p, phantom_p, surge_p, bookie_p)
            X_rows.append(meta)
            y_labels.append(label)

        X = np.array(X_rows, dtype=np.float32)
        y = np.array(y_labels, dtype=np.float32)
        self.train(X, y)

    def predict(self, player_a: str, player_b: str) -> Tuple[float, float]:
        """
        Get meta-prediction by stacking sub-engine outputs through the MLP.
        Falls back to weighted average if MLP not trained.
        """
        titan_p = phantom_p = surge_p = 0.5
        for eng in self._sub_engines:
            p_a, _ = eng.predict(player_a, player_b)
            if eng.name == "TITAN":
                titan_p = p_a
            elif eng.name == "PHANTOM":
                phantom_p = p_a
            elif eng.name == "SURGE":
                surge_p = p_a

        if self._trained and _TORCH_AVAILABLE:
            meta = self._make_meta_features(titan_p, phantom_p, surge_p)
            self._mlp.eval()
            with torch.no_grad():
                x_t = torch.tensor([meta], dtype=torch.float32)
                prob_a = float(self._mlp(x_t)[0][0])
        else:
            # Weighted fallback average
            w = self._engine_weights
            prob_a = (
                w.get("TITAN", 0.4) * titan_p
                + w.get("PHANTOM", 0.25) * phantom_p
                + w.get("SURGE", 0.35) * surge_p
            ) / sum(w.values())

        prob_a = float(np.clip(prob_a, 0.01, 0.99))
        return prob_a, 1.0 - prob_a

    def explain(self, player_a: str, player_b: str) -> str:
        titan_p = phantom_p = surge_p = 0.5
        for eng in self._sub_engines:
            p_a, _ = eng.predict(player_a, player_b)
            if eng.name == "TITAN":
                titan_p = p_a
            elif eng.name == "PHANTOM":
                phantom_p = p_a
            elif eng.name == "SURGE":
                surge_p = p_a

        prob_a, _ = self.predict(player_a, player_b)
        winner = player_a if prob_a >= 0.5 else player_b
        return (
            f"[ORACLE meta-ensemble] TITAN={titan_p:.1%}, PHANTOM={phantom_p:.1%}, "
            f"SURGE={surge_p:.1%} → consensus picks {winner} with "
            f"{max(prob_a, 1-prob_a):.1%} confidence."
        )

    def get_tree_data(self) -> Dict[str, Any]:
        """Return MLP architecture and current engine weights as tree data."""
        if not self._trained:
            return {
                "engine": "ORACLE",
                "trained": False,
                "architecture": "Linear(6→32)→ReLU→Dropout→Linear(32→16)→ReLU→Dropout→Linear(16→1)→Sigmoid",
                "engine_weights": self._engine_weights,
            }
        return {
            "engine": "ORACLE",
            "trained": True,
            "architecture": "Linear(6→32)→ReLU→Dropout→Linear(32→16)→ReLU→Dropout→Linear(16→1)→Sigmoid",
            "engine_weights": self._engine_weights,
            "nodes": [
                {"id": "input", "feature": "Sub-engine probabilities", "shape": "6"},
                {"id": "hidden1", "feature": "Hidden layer 1", "shape": "32"},
                {"id": "hidden2", "feature": "Hidden layer 2", "shape": "16"},
                {"id": "output", "feature": "Win probability", "shape": "1"},
            ],
        }


# Module-level singleton
oracle_engine = OracleEngine()
