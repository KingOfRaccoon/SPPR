"""Baseline forecasting models: Simple Moving Average and Exponential Smoothing."""

from __future__ import annotations

import numpy as np


class SimpleMovingAverageForecaster:
    """Simple Moving Average (SMA-k) baseline forecaster."""

    def __init__(self, window: int = 7) -> None:
        if window < 1:
            raise ValueError(f"Window must be at least 1, got {window}")
        self.window = window
        self.last_mean: float = 0.0
        self.fitted_values: np.ndarray | None = None
        self.residuals: np.ndarray | None = None

    def fit(self, series: np.ndarray | list[float]) -> SimpleMovingAverageForecaster:
        """Fit SMA on historical demand series."""
        y = np.asarray(series, dtype=float)
        n = len(y)
        if n == 0:
            self.last_mean = 0.0
            self.fitted_values = np.array([])
            self.residuals = np.array([])
            return self

        eff_window = min(self.window, n)
        self.last_mean = float(np.mean(y[-eff_window:]))

        # Compute in-sample 1-step ahead forecasts
        fitted = np.zeros(n)
        for t in range(n):
            if t == 0:
                fitted[t] = y[0]
            else:
                w = min(self.window, t)
                fitted[t] = float(np.mean(y[t - w : t]))

        self.fitted_values = fitted
        self.residuals = y - fitted
        return self

    def predict(self, horizon_days: int) -> np.ndarray:
        """Generate flat multi-step forecast for the given horizon."""
        if horizon_days <= 0:
            return np.array([])
        val = max(0.0, self.last_mean)
        return np.repeat(val, horizon_days)


class ExponentialSmoothingForecaster:
    """Single Exponential Smoothing (SES / EMA) baseline forecaster."""

    def __init__(self, alpha: float = 0.2) -> None:
        if not (0.0 < alpha <= 1.0):
            raise ValueError(f"Alpha must be in (0, 1], got {alpha}")
        self.alpha = alpha
        self.level: float = 0.0
        self.fitted_values: np.ndarray | None = None
        self.residuals: np.ndarray | None = None

    def fit(self, series: np.ndarray | list[float]) -> ExponentialSmoothingForecaster:
        """Fit Single Exponential Smoothing on historical demand series."""
        y = np.asarray(series, dtype=float)
        n = len(y)
        if n == 0:
            self.level = 0.0
            self.fitted_values = np.array([])
            self.residuals = np.array([])
            return self

        fitted = np.zeros(n)
        level = y[0]
        fitted[0] = level

        for t in range(1, n):
            level = self.alpha * y[t - 1] + (1.0 - self.alpha) * level
            fitted[t] = level

        # Final level after observing y[n-1]
        self.level = self.alpha * y[-1] + (1.0 - self.alpha) * level
        self.fitted_values = fitted
        self.residuals = y - fitted
        return self

    def predict(self, horizon_days: int) -> np.ndarray:
        """Generate flat forecast from the latest smoothed level."""
        if horizon_days <= 0:
            return np.array([])
        val = max(0.0, self.level)
        return np.repeat(val, horizon_days)


class CrostonForecaster:
    """Croston method for intermittent (zero-inflated) demand forecasting.

    Separates non-zero demand size and inter-demand arrival intervals.
    """

    def __init__(self, alpha: float = 0.1) -> None:
        if not (0.0 < alpha <= 1.0):
            raise ValueError(f"Alpha must be in (0, 1], got {alpha}")
        self.alpha = alpha
        self.forecast_rate: float = 0.0
        self.fitted_values: np.ndarray | None = None
        self.residuals: np.ndarray | None = None

    def fit(self, series: np.ndarray | list[float]) -> CrostonForecaster:
        """Fit Croston model on intermittent time series."""
        y = np.asarray(series, dtype=float)
        n = len(y)
        if n == 0:
            self.forecast_rate = 0.0
            self.fitted_values = np.array([])
            self.residuals = np.array([])
            return self

        non_zeros = np.where(y > 0)[0]
        if len(non_zeros) == 0:
            self.forecast_rate = 0.0
            self.fitted_values = np.zeros(n)
            self.residuals = y.copy()
            return self

        first_nz = non_zeros[0]
        z = y[first_nz]  # smoothed demand size
        p = float(first_nz + 1)  # smoothed inter-arrival interval
        q = 1  # periods since last non-zero

        fitted = np.full(n, z / max(1.0, p))

        for t in range(first_nz + 1, n):
            if y[t] > 0:
                z = self.alpha * y[t] + (1.0 - self.alpha) * z
                p = self.alpha * q + (1.0 - self.alpha) * p
                q = 1
            else:
                q += 1
            fitted[t] = z / max(1.0, p)

        self.forecast_rate = max(0.0, z / max(1.0, p))
        self.fitted_values = fitted
        self.residuals = y - fitted
        return self

    def predict(self, horizon_days: int) -> np.ndarray:
        """Generate constant forecast rate for the given horizon."""
        if horizon_days <= 0:
            return np.array([])
        return np.repeat(self.forecast_rate, horizon_days)
