"""
ParlayWars v3 — Abstract Base Engine
Date: 2026-02-25
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple


class BaseEngine(ABC):
    """
    Abstract interface that all prediction engines must implement.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short engine name (e.g. 'TITAN')."""

    @abstractmethod
    def train(self, X: Any, y: Any) -> None:
        """Train the model on feature matrix X and labels y."""

    @abstractmethod
    def predict(self, player_a: str, player_b: str) -> Tuple[float, float]:
        """
        Return (prob_a, prob_b): probabilities that player_a / player_b wins.
        Both values are in [0, 1] and sum to 1.0.
        """

    @abstractmethod
    def explain(self, player_a: str, player_b: str) -> str:
        """Return a plain-English explanation of the prediction."""

    @abstractmethod
    def get_tree_data(self) -> Dict[str, Any]:
        """Return a JSON-serialisable dict describing the model's tree structure for D3.js."""

    def confidence_tier(self, prob: float) -> str:
        """Classify a probability into a confidence tier."""
        if prob >= 0.65:
            return "HIGH"
        if prob >= 0.55:
            return "MEDIUM"
        return "LOW"
