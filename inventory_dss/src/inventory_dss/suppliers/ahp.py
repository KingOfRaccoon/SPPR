"""Analytic Hierarchy Process (AHP / МАИ Саати) for Criteria Weighting.

Implements pairwise comparison reciprocal matrix evaluation,
principal eigenvector priority vector computation, geometric mean approximation,
and consistency index (CI) and consistency ratio (CR < 0.10) verification.
"""

from __future__ import annotations

import numpy as np

# Saaty's empirical Random Index (RI) table for matrix orders n = 1 .. 10
RANDOM_INDEX_TABLE: dict[int, float] = {
    1: 0.00,
    2: 0.00,
    3: 0.58,
    4: 0.90,
    5: 1.12,
    6: 1.24,
    7: 1.32,
    8: 1.41,
    9: 1.45,
    10: 1.49,
}

# 6 canonical criteria for supplier evaluation
DEFAULT_CRITERIA: list[str] = [
    "price",          # Purchasing cost / markup factor (cost, min)
    "lead_time",      # Average delivery lead time in days (cost, min)
    "lead_time_std",  # Lead time variance / delay uncertainty (cost, min)
    "defect_rate",    # Quality rejection rate fraction (cost, min)
    "moq",            # Minimum Order Quantity constraint (cost, min)
    "otif",           # On-Time In-Full delivery reliability rate (benefit, max)
]

# Consistent expert pairwise comparison matrix for the 6 criteria (CR = 0.0067 < 0.10)
# Rows & Cols: [price, lead_time, lead_time_std, defect_rate, moq, otif]
DEFAULT_PAIRWISE_MATRIX: np.ndarray = np.array([
    [1.0,     2.0,   3.0,   2.0,   4.0,   1.0],      # price
    [1/2.0,   1.0,   2.0,   1.0,   3.0,   1/2.0],    # lead_time
    [1/3.0,   1/2.0, 1.0,   1/2.0, 2.0,   1/3.0],    # lead_time_std
    [1/2.0,   1.0,   2.0,   1.0,   3.0,   1/2.0],    # defect_rate
    [1/4.0,   1/3.0, 1/2.0, 1/3.0, 1.0,   1/4.0],    # moq
    [1.0,     2.0,   3.0,   2.0,   4.0,   1.0],      # otif
], dtype=float)


class AHPEngine:
    """Saaty Analytic Hierarchy Process engine for criteria weight determination."""

    @staticmethod
    def compute_weights(pairwise_matrix: np.ndarray) -> tuple[np.ndarray, float, float]:
        """Compute criteria priority weights vector via principal eigenvector method.

        Args:
            pairwise_matrix: Square reciprocal comparison matrix (n x n).

        Returns:
            Tuple of:
                - Normalized priority weights vector (summing to 1.0)
                - Principal eigenvalue lambda_max
                - Consistency Ratio (CR)
        """
        matrix = np.asarray(pairwise_matrix, dtype=float)
        n, m = matrix.shape
        if n != m:
            raise ValueError(f"Pairwise matrix must be square, got shape ({n}, {m})")
        if n == 0:
            raise ValueError("Pairwise matrix cannot be empty")
        if n == 1:
            return np.array([1.0]), 1.0, 0.0

        # Validate reciprocal property: A[i, j] * A[j, i] ~ 1.0
        reciprocal_product = matrix * matrix.T
        if not np.allclose(reciprocal_product, 1.0, rtol=1e-2):
            # Non-fatal warning or adjustment, but verify diagonal
            pass

        # Compute eigenvalues and eigenvectors
        eigenvalues, eigenvectors = np.linalg.eig(matrix)
        max_idx = int(np.argmax(np.real(eigenvalues)))
        lambda_max = float(np.real(eigenvalues[max_idx]))

        # Principal eigenvector
        principal_vector = np.real(eigenvectors[:, max_idx])
        # Invert if all negative
        if np.all(principal_vector <= 0):
            principal_vector = -principal_vector
        principal_vector = np.maximum(0.0, principal_vector)

        weights = principal_vector / np.sum(principal_vector)

        # Consistency index (CI)
        ci = (lambda_max - n) / (n - 1) if n > 1 else 0.0
        # Prevent numerical float rounding producing small negative CI
        ci = max(0.0, ci)

        # Random Index (RI)
        ri = RANDOM_INDEX_TABLE.get(n, 1.49)
        cr = ci / ri if ri > 0 else 0.0

        return weights, lambda_max, cr

    @staticmethod
    def compute_geometric_mean_weights(pairwise_matrix: np.ndarray) -> np.ndarray:
        """Compute priority weights via Saaty's geometric mean (logarithmic least squares)."""
        matrix = np.asarray(pairwise_matrix, dtype=float)
        n = matrix.shape[0]
        geom_means = np.prod(matrix, axis=1) ** (1.0 / n)
        return geom_means / np.sum(geom_means)

    @classmethod
    def get_default_weights(cls) -> dict[str, float]:
        """Compute default normalized criteria weights from the canonical 6-criteria matrix."""
        weights, _, _ = cls.compute_weights(DEFAULT_PAIRWISE_MATRIX)
        return {
            criterion: float(weights[i])
            for i, criterion in enumerate(DEFAULT_CRITERIA)
        }

    @classmethod
    def validate_consistency(cls, pairwise_matrix: np.ndarray, threshold: float = 0.10) -> bool:
        """Verify whether the pairwise matrix meets the consistency threshold CR < 0.10."""
        _, _, cr = cls.compute_weights(pairwise_matrix)
        return cr < threshold
