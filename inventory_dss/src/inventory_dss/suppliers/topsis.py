"""Technique for Order Preference by Similarity to Ideal Solution (TOPSIS).

Implements multi-criteria ranking:
1. Vector normalization of the decision matrix
2. Weighting by criteria importance
3. Determination of Positive Ideal (PIS) and Negative Ideal (NIS) solutions
4. Euclidean distance computation to PIS and NIS
5. Relative closeness score C_i in [0.0, 1.0] and ranking
"""

from __future__ import annotations

import numpy as np


class TOPSISSolver:
    """TOPSIS multi-criteria decision solver."""

    @staticmethod
    def solve(
        decision_matrix: np.ndarray,
        weights: np.ndarray,
        is_benefit: list[bool] | np.ndarray,
    ) -> np.ndarray:
        """Compute TOPSIS relative closeness coefficient C_i for each alternative.

        Args:
            decision_matrix: Matrix of shape (m, n) for m alternatives and n criteria.
            weights: Array of shape (n,) with non-negative criteria weights summing to 1.
            is_benefit: Boolean flags of length n (True if criterion is to be maximized, False if minimized).

        Returns:
            Array of shape (m,) containing closeness scores C_i in [0.0, 1.0].
        """
        detailed = TOPSISSolver.solve_detailed(decision_matrix, weights, is_benefit)
        return detailed["closeness"]

    @staticmethod
    def solve_detailed(
        decision_matrix: np.ndarray,
        weights: np.ndarray,
        is_benefit: list[bool] | np.ndarray,
    ) -> dict[str, np.ndarray]:
        """Compute full TOPSIS analytical step-by-step matrices and metrics.

        Returns:
            Dictionary containing:
                - 'normalized_matrix': R (m x n)
                - 'weighted_matrix': V (m x n)
                - 'pis': Positive Ideal Solution (n,)
                - 'nis': Negative Ideal Solution (n,)
                - 'd_pos': Euclidean distance to PIS (m,)
                - 'd_neg': Euclidean distance to NIS (m,)
                - 'closeness': Relative closeness C_i (m,)
                - 'ranks': Ordinal ranks 1..m (1 = highest closeness)
        """
        X = np.asarray(decision_matrix, dtype=float)
        w = np.asarray(weights, dtype=float)
        benefits = np.asarray(is_benefit, dtype=bool)

        m, n = X.shape
        if m == 0 or n == 0:
            raise ValueError("Decision matrix cannot be empty")
        if len(w) != n:
            raise ValueError(f"Weights length {len(w)} must match criteria count {n}")
        if len(benefits) != n:
            raise ValueError(f"Benefit flags length {len(benefits)} must match criteria count {n}")

        # Normalize weights to sum to 1.0 if not already normalized
        sum_w = float(np.sum(w))
        if sum_w > 0 and not np.isclose(sum_w, 1.0):
            w = w / sum_w

        if m == 1:
            # Single alternative is trivially optimal
            return {
                "normalized_matrix": np.ones((1, n)),
                "weighted_matrix": np.ones((1, n)) * w,
                "pis": np.ones(n) * w,
                "nis": np.ones(n) * w,
                "d_pos": np.array([0.0]),
                "d_neg": np.array([0.0]),
                "closeness": np.array([1.0]),
                "ranks": np.array([1]),
            }

        # 1. Vector Normalization: r_ij = x_ij / sqrt(sum_k x_kj^2)
        col_norms = np.sqrt(np.sum(X**2, axis=0, keepdims=True))
        col_norms = np.where(col_norms == 0, 1e-12, col_norms)
        R = X / col_norms

        # 2. Weighted Normalized Decision Matrix: v_ij = w_j * r_ij
        V = R * w

        # 3. Positive and Negative Ideal Solutions
        pis = np.zeros(n, dtype=float)
        nis = np.zeros(n, dtype=float)
        for j in range(n):
            if benefits[j]:
                pis[j] = float(np.max(V[:, j]))
                nis[j] = float(np.min(V[:, j]))
            else:
                pis[j] = float(np.min(V[:, j]))
                nis[j] = float(np.max(V[:, j]))

        # 4. Euclidean Distances to PIS and NIS
        d_pos = np.sqrt(np.sum((V - pis) ** 2, axis=1))
        d_neg = np.sqrt(np.sum((V - nis) ** 2, axis=1))

        # 5. Relative Closeness Coefficient: C_i = d_neg / (d_pos + d_neg)
        denom = d_pos + d_neg
        denom_safe = np.where(denom == 0, 1e-12, denom)
        closeness = d_neg / denom_safe
        closeness = np.clip(closeness, 0.0, 1.0)

        # 6. Ordinal ranks: rank 1 is highest closeness
        # argsort descending
        order = np.argsort(-closeness)
        ranks = np.empty_like(order)
        ranks[order] = np.arange(1, m + 1)

        return {
            "normalized_matrix": R,
            "weighted_matrix": V,
            "pis": pis,
            "nis": nis,
            "d_pos": d_pos,
            "d_neg": d_neg,
            "closeness": closeness,
            "ranks": ranks,
        }
