"""Supplier Evaluator Facade.

Unifies TOPSIS, Analytic Hierarchy Process (AHP), Shannon Entropy Weighting,
and Weighted Sum Model (WSM) under a clean domain facade.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from inventory_dss.models.domain import Supplier
from inventory_dss.suppliers.ahp import DEFAULT_CRITERIA, AHPEngine
from inventory_dss.suppliers.entropy import EntropyWeightEngine
from inventory_dss.suppliers.topsis import TOPSISSolver

CRITERIA_BENEFICIAL_FLAGS: dict[str, bool] = {
    "price": False,          # cost -> minimize
    "lead_time": False,      # cost -> minimize
    "lead_time_std": False,  # cost -> minimize
    "defect_rate": False,    # cost -> minimize
    "moq": False,            # cost -> minimize
    "otif": True,            # benefit -> maximize
}


class SupplierEvaluator:
    """Facade for multi-criteria evaluation and ranking of candidate suppliers."""

    def __init__(self, hybrid_balance_factor: float = 0.5) -> None:
        """Initialize evaluator with hybrid AHP-Entropy balancing coefficient."""
        self.hybrid_balance_factor = hybrid_balance_factor

    @staticmethod
    def _extract_decision_matrix(
        suppliers: list[Supplier],
        criteria: list[str] | None = None,
    ) -> tuple[np.ndarray, list[str], list[bool]]:
        """Extract a numeric 2D numpy matrix and metadata from Supplier models."""
        if criteria is None:
            criteria = list(DEFAULT_CRITERIA)

        rows: list[list[float]] = []
        for s in suppliers:
            row: list[float] = []
            for c in criteria:
                if c == "price":
                    row.append(float(s.price_markup_factor))
                elif c == "lead_time":
                    row.append(float(s.mean_lead_time_days))
                elif c == "lead_time_std":
                    row.append(float(s.std_lead_time_days))
                elif c == "defect_rate":
                    row.append(float(s.defect_rate))
                elif c == "moq":
                    row.append(float(s.min_order_quantity))
                elif c == "otif":
                    row.append(float(s.on_time_delivery_rate))
                else:
                    raise ValueError(f"Unknown criterion: {c}")
            rows.append(row)

        X = np.array(rows, dtype=float)
        benefits = [CRITERIA_BENEFICIAL_FLAGS.get(c, False) for c in criteria]
        return X, criteria, benefits

    def evaluate_suppliers(
        self,
        suppliers: list[Supplier],
        weights: dict[str, float] | None = None,
        method: Literal["TOPSIS", "AHP", "WSM", "ENTROPY_TOPSIS", "HYBRID"] = "TOPSIS",
    ) -> dict[str, float]:
        """Compute relative closeness or performance scores for candidate suppliers.

        Args:
            suppliers: List of candidate Supplier domain entities.
            weights: Optional custom criteria weights mapping. If None, derived from method.
            method: Multi-criteria decision analysis methodology:
                - "TOPSIS": Vector-normalized TOPSIS using AHP or provided weights
                - "AHP": TOPSIS with Saaty's analytic hierarchy process weights
                - "ENTROPY_TOPSIS": TOPSIS with objective Shannon entropy weights
                - "HYBRID": TOPSIS with balanced AHP & Entropy weights
                - "WSM": Linear min-max Weighted Sum Model

        Returns:
            Dictionary mapping supplier_id -> score in [0.0, 1.0].
        """
        if not suppliers:
            return {}
        if len(suppliers) == 1:
            return {suppliers[0].supplier_id: 1.0}

        X, criteria, is_benefit = self._extract_decision_matrix(suppliers)
        n = len(criteria)

        # Determine weight vector
        if weights is not None:
            w_arr = np.array([weights.get(c, 1.0 / n) for c in criteria], dtype=float)
            if np.sum(w_arr) > 0:
                w_arr = w_arr / np.sum(w_arr)
            else:
                w_arr = np.full(n, 1.0 / n)
        elif method in ("TOPSIS", "AHP"):
            ahp_weights = AHPEngine.get_default_weights()
            w_arr = np.array([ahp_weights.get(c, 1.0 / n) for c in criteria], dtype=float)
        elif method == "ENTROPY_TOPSIS":
            w_arr = EntropyWeightEngine.compute_entropy_weights(X)
        elif method == "HYBRID":
            ahp_w = np.array([AHPEngine.get_default_weights().get(c, 1.0 / n) for c in criteria])
            ent_w = EntropyWeightEngine.compute_entropy_weights(X)
            alpha = self.hybrid_balance_factor
            w_arr = alpha * ahp_w + (1.0 - alpha) * ent_w
            w_arr = w_arr / np.sum(w_arr)
        elif method == "WSM":
            ahp_weights = AHPEngine.get_default_weights()
            w_arr = np.array([ahp_weights.get(c, 1.0 / n) for c in criteria], dtype=float)
        else:
            w_arr = np.full(n, 1.0 / n)

        # Solve according to chosen method
        if method == "WSM":
            # Linear min-max normalization
            R_wsm = np.zeros_like(X)
            for j in range(n):
                col = X[:, j]
                c_min, c_max = float(np.min(col)), float(np.max(col))
                span = c_max - c_min
                if span <= 1e-12:
                    R_wsm[:, j] = 1.0
                elif is_benefit[j]:
                    R_wsm[:, j] = (col - c_min) / span
                else:
                    R_wsm[:, j] = (c_max - col) / span
            scores = np.dot(R_wsm, w_arr)
            # Clip to [0.0, 1.0]
            scores = np.clip(scores, 0.0, 1.0)
        else:
            # TOPSIS
            scores = TOPSISSolver.solve(X, w_arr, is_benefit)

        return {
            supplier.supplier_id: float(scores[i])
            for i, supplier in enumerate(suppliers)
        }

    def rank_suppliers(
        self,
        suppliers: list[Supplier],
        weights: dict[str, float] | None = None,
        method: Literal["TOPSIS", "AHP", "WSM", "ENTROPY_TOPSIS", "HYBRID"] = "TOPSIS",
    ) -> list[dict]:
        """Rank suppliers and return sorted list with ranks and metadata."""
        scores_map = self.evaluate_suppliers(suppliers, weights=weights, method=method)
        sorted_items = sorted(scores_map.items(), key=lambda item: item[1], reverse=True)

        supp_lookup = {s.supplier_id: s for s in suppliers}
        ranked_list: list[dict] = []
        for rank, (supp_id, score) in enumerate(sorted_items, start=1):
            s = supp_lookup[supp_id]
            ranked_list.append({
                "rank": rank,
                "supplier_id": supp_id,
                "name": s.name,
                "score": round(score, 4),
                "mean_lead_time_days": s.mean_lead_time_days,
                "std_lead_time_days": s.std_lead_time_days,
                "on_time_delivery_rate": s.on_time_delivery_rate,
                "defect_rate": s.defect_rate,
                "min_order_quantity": s.min_order_quantity,
                "price_markup_factor": s.price_markup_factor,
            })
        return ranked_list
