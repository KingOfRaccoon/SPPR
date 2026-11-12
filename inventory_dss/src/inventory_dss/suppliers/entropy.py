"""Objective Shannon Entropy Weighting for Multi-Criteria Supplier Metrics.

Measures the information utility and dispersion of each criterion across alternatives:
criteria with high variability across suppliers provide more discriminating power
and thus receive higher objective weights.
"""

from __future__ import annotations

import numpy as np


class EntropyWeightEngine:
    """Calculates objective weights via the Shannon Entropy Weight Method (EWM)."""

    @staticmethod
    def compute_entropy_weights(decision_matrix: np.ndarray) -> np.ndarray:
        """Compute objective Shannon entropy weights for an m x n decision matrix.

        Args:
            decision_matrix: Matrix of m alternatives x n criteria. Must be non-negative.

        Returns:
            Normalized weight vector w of shape (n,) such that sum(w) == 1.0 and w_j >= 0.
        """
        X = np.asarray(decision_matrix, dtype=float)
        m, n = X.shape

        if m == 0 or n == 0:
            raise ValueError("Decision matrix cannot be empty")
        if m == 1:
            # Single alternative: uniform distribution
            return np.full(n, 1.0 / n)

        # 1. Normalization to probability distribution P_ij = x_ij / sum_i(x_ij)
        col_sums = np.sum(X, axis=0, keepdims=True)
        # Avoid division by zero
        safe_col_sums = np.where(col_sums == 0, 1.0, col_sums)
        P = X / safe_col_sums

        # 2. Shannon Entropy: E_j = -k * sum_i(p_ij * ln(p_ij)) where k = 1 / ln(m)
        # Handle p_ij == 0: convention 0 * ln(0) = 0
        P_safe = np.where(P > 0, P, 1.0)
        P_log = np.where(P > 0, np.log(P_safe), 0.0)
        k = 1.0 / np.log(m)
        E = -k * np.sum(P * P_log, axis=0)
        # Clip to [0.0, 1.0] due to precision limits
        E = np.clip(E, 0.0, 1.0)

        # 3. Degree of divergence d_j = 1 - E_j
        d = 1.0 - E

        # 4. Objective weights w_j = d_j / sum(d_k)
        total_divergence = float(np.sum(d))
        if total_divergence <= 1e-12:
            # If all criteria are identical across alternatives, assign uniform weights
            return np.full(n, 1.0 / n)

        weights = d / total_divergence
        return weights

    @classmethod
    def compute_entropy_and_divergence(
        cls, decision_matrix: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Compute entropy values E_j, divergence degrees d_j, and weights w_j.

        Returns:
            Tuple of (E, d, weights) vectors.
        """
        X = np.asarray(decision_matrix, dtype=float)
        m, n = X.shape
        if m <= 1 or n == 0:
            return np.ones(n), np.zeros(n), np.full(n, 1.0 / n)

        col_sums = np.sum(X, axis=0, keepdims=True)
        safe_col_sums = np.where(col_sums == 0, 1.0, col_sums)
        P = X / safe_col_sums

        P_safe = np.where(P > 0, P, 1.0)
        P_log = np.where(P > 0, np.log(P_safe), 0.0)
        k = 1.0 / np.log(m)
        E = np.clip(-k * np.sum(P * P_log, axis=0), 0.0, 1.0)
        d = 1.0 - E

        total_d = float(np.sum(d))
        weights = d / total_d if total_d > 1e-12 else np.full(n, 1.0 / n)
        return E, d, weights
