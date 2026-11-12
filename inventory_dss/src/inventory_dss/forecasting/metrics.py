"""Evaluation metrics for time-series demand forecasting."""

from __future__ import annotations

import numpy as np


def calculate_mae(y_true: np.ndarray | list[float], y_pred: np.ndarray | list[float]) -> float:
    """Mean Absolute Error (MAE): (1/n) * sum(|y - y_hat|)."""
    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_pred, dtype=float)
    if len(yt) == 0:
        return 0.0
    return float(np.mean(np.abs(yt - yp)))


def calculate_rmse(y_true: np.ndarray | list[float], y_pred: np.ndarray | list[float]) -> float:
    """Root Mean Squared Error (RMSE): sqrt((1/n) * sum((y - y_hat)^2))."""
    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_pred, dtype=float)
    if len(yt) == 0:
        return 0.0
    return float(np.sqrt(np.mean((yt - yp) ** 2)))


def calculate_mape(
    y_true: np.ndarray | list[float],
    y_pred: np.ndarray | list[float],
    epsilon: float = 1e-5,
) -> float:
    """Mean Absolute Percentage Error (MAPE) in [0, 1] or percentage scale.

    Robust to zero denominators using epsilon or non-zero subset.
    """
    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_pred, dtype=float)
    if len(yt) == 0:
        return 0.0
    if np.all(yt == 0.0) and np.all(yp == 0.0):
        return 0.0
    # Use non-zero actuals when present, otherwise regularized denominator
    non_zero = yt > epsilon
    if np.any(non_zero):
        return float(np.mean(np.abs((yt[non_zero] - yp[non_zero]) / yt[non_zero])))
    denom = np.maximum(yt, epsilon)
    return float(np.mean(np.abs((yt - yp) / denom)))


def calculate_wape(y_true: np.ndarray | list[float], y_pred: np.ndarray | list[float]) -> float:
    """Weighted Absolute Percentage Error (WAPE): sum(|y - y_hat|) / sum(y).

    Robust for intermittent or low-volume demand series.
    """
    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_pred, dtype=float)
    if len(yt) == 0:
        return 0.0
    total_actual = float(np.sum(yt))
    total_abs_error = float(np.sum(np.abs(yt - yp)))
    if total_actual == 0.0:
        return 0.0 if total_abs_error == 0.0 else 1.0
    return float(total_abs_error / total_actual)


def calculate_forecast_metrics(
    y_true: np.ndarray | list[float],
    y_pred: np.ndarray | list[float],
) -> dict[str, float]:
    """Calculate all standard forecast accuracy metrics (MAE, RMSE, MAPE, WAPE)."""
    mae = calculate_mae(y_true, y_pred)
    rmse = calculate_rmse(y_true, y_pred)
    mape = calculate_mape(y_true, y_pred)
    wape = calculate_wape(y_true, y_pred)

    # Ensure Jensen's inequality RMSE >= MAE numerically holds despite precision jitter
    rmse = max(rmse, mae)

    return {
        "MAE": round(mae, 4),
        "RMSE": round(rmse, 4),
        "MAPE": round(mape, 4),
        "WAPE": round(wape, 4),
    }
