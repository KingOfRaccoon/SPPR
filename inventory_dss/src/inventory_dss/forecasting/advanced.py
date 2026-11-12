"""Advanced forecasting models: Holt-Winters, Ridge Regression with lags, and Auto-ARIMA/SARIMAX."""

from __future__ import annotations

import warnings
from datetime import date, timedelta
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import ExponentialSmoothing

# Handled statistical convergence and numerical errors
_MODEL_ERRORS = (ValueError, TypeError, RuntimeError, IndexError, AttributeError, np.linalg.LinAlgError)


class HoltWintersForecaster:
    """Holt-Winters Triple Exponential Smoothing (Additive and Multiplicative)."""

    def __init__(
        self,
        trend: Literal["add", "mul"] | None = "add",
        seasonal: Literal["add", "mul"] | None = "add",
        seasonal_periods: int = 7,
    ) -> None:
        self.trend = trend
        self.seasonal = seasonal
        self.seasonal_periods = seasonal_periods
        self.model = None
        self.fitted_model = None
        self.fitted_values: np.ndarray | None = None
        self.residuals: np.ndarray | None = None
        self._fallback_mean: float = 0.0

    def fit(self, series: np.ndarray | list[float]) -> HoltWintersForecaster:
        """Fit Holt-Winters model on time series data."""
        y = np.asarray(series, dtype=float)
        n = len(y)
        self._fallback_mean = float(np.mean(y)) if n > 0 else 0.0

        if n < max(14, 2 * self.seasonal_periods):
            # Fall back gracefully on short series
            self.fitted_values = np.repeat(self._fallback_mean, n)
            self.residuals = y - self.fitted_values
            return self

        # If multiplicative mode is requested but data contains zeros or negatives, switch to additive
        eff_trend = self.trend
        eff_seasonal = self.seasonal
        if (eff_trend == "mul" or eff_seasonal == "mul") and np.any(y <= 0):
            eff_trend = "add" if eff_trend else None
            eff_seasonal = "add" if eff_seasonal else None

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                hw = ExponentialSmoothing(
                    y,
                    trend=eff_trend,
                    seasonal=eff_seasonal,
                    seasonal_periods=self.seasonal_periods,
                    initialization_method="estimated",
                )
                self.fitted_model = hw.fit(optimized=True)
                fitted = np.maximum(0.0, np.asarray(self.fitted_model.fittedvalues, dtype=float))
                self.fitted_values = fitted
                self.residuals = y - fitted
        except _MODEL_ERRORS:
            self.fitted_model = None
            self.fitted_values = np.repeat(self._fallback_mean, n)
            self.residuals = y - self.fitted_values

        return self

    def predict(self, horizon_days: int) -> np.ndarray:
        """Forecast horizon_days ahead."""
        if horizon_days <= 0:
            return np.array([])
        if self.fitted_model is not None:
            try:
                preds = self.fitted_model.forecast(horizon_days)
                return np.maximum(0.0, np.asarray(preds, dtype=float))
            except _MODEL_ERRORS:
                return np.repeat(max(0.0, self._fallback_mean), horizon_days)
        return np.repeat(max(0.0, self._fallback_mean), horizon_days)


class RidgeRegressionForecaster:
    """Feature-based regularized linear regression with lag, rolling and calendar features."""

    def __init__(
        self,
        lags: tuple[int, ...] = (1, 2, 7, 14, 21),
        alpha: float = 1.0,
    ) -> None:
        self.lags = lags
        self.alpha = alpha
        self.model = Ridge(alpha=alpha)
        self.history_: np.ndarray | None = None
        self.fitted_values: np.ndarray | None = None
        self.residuals: np.ndarray | None = None
        self.dates_: list[date] | None = None
        self._fallback_mean: float = 0.0

    def _extract_features(
        self,
        history: np.ndarray,
        idx: int,
        ref_date: date | None = None,
    ) -> list[float]:
        """Extract lag, rolling and calendar features for time step idx."""
        feats = []
        # Lag features
        for lag in self.lags:
            if idx - lag >= 0:
                feats.append(float(history[idx - lag]))
            else:
                feats.append(float(history[0]))

        # Rolling statistics
        w7 = history[max(0, idx - 7) : idx] if idx > 0 else np.array([history[0]])
        feats.append(float(np.mean(w7)))
        feats.append(float(np.std(w7)))

        # Calendar features if date provided
        if ref_date is not None and not isinstance(ref_date, date):
            try:
                ref_date = pd.to_datetime(ref_date).date()
            except (ValueError, TypeError, AttributeError):
                ref_date = None

        if ref_date is not None:
            dow = ref_date.weekday()
            feats.append(1.0 if dow in (5, 6) else 0.0)
            feats.append(np.sin(2 * np.pi * dow / 7.0))
            feats.append(np.cos(2 * np.pi * dow / 7.0))
            feats.append(float(ref_date.day) / 31.0)
            feats.append(float(ref_date.month) / 12.0)
        else:
            dow = idx % 7
            feats.append(1.0 if dow in (5, 6) else 0.0)
            feats.append(np.sin(2 * np.pi * dow / 7.0))
            feats.append(np.cos(2 * np.pi * dow / 7.0))
            feats.append(0.5)
            feats.append(0.5)

        return feats

    def fit(
        self,
        series: np.ndarray | list[float],
        dates: list[date] | None = None,
    ) -> RidgeRegressionForecaster:
        """Fit Ridge Regression on feature matrix."""
        y = np.asarray(series, dtype=float)
        n = len(y)
        self.history_ = y.copy()
        parsed_dates = None
        if dates is not None and len(dates) > 0:
            try:
                parsed_dates = pd.to_datetime(pd.Series(dates)).dt.date.tolist()
            except (ValueError, TypeError, AttributeError):
                parsed_dates = None
        self.dates_ = parsed_dates
        self._fallback_mean = float(np.mean(y)) if n > 0 else 0.0

        max_lag = max(self.lags) if self.lags else 1
        if n <= max_lag + 2:
            self.fitted_values = np.repeat(self._fallback_mean, n)
            self.residuals = y - self.fitted_values
            return self

        X_rows = []
        y_targets = []
        for t in range(max_lag, n):
            cur_date = dates[t] if dates is not None and t < len(dates) else None
            X_rows.append(self._extract_features(y, t, cur_date))
            y_targets.append(y[t])

        X = np.array(X_rows, dtype=float)
        Y = np.array(y_targets, dtype=float)

        self.model.fit(X, Y)

        # Compute fitted values
        fitted_tail = np.maximum(0.0, self.model.predict(X))
        fitted = np.concatenate([np.repeat(self._fallback_mean, max_lag), fitted_tail])
        self.fitted_values = fitted
        self.residuals = y - fitted
        return self

    def predict(self, horizon_days: int) -> np.ndarray:
        """Recursive multi-step forecast."""
        if horizon_days <= 0:
            return np.array([])
        if self.history_ is None or len(self.history_) == 0:
            return np.repeat(0.0, horizon_days)

        sim_history = list(self.history_)
        n_orig = len(sim_history)
        predictions = []

        last_date = self.dates_[-1] if self.dates_ else date(2025, 1, 1)
        if not isinstance(last_date, date):
            try:
                last_date = pd.to_datetime(last_date).date()
            except (ValueError, TypeError, AttributeError):
                last_date = date(2025, 1, 1)

        for h in range(1, horizon_days + 1):
            cur_date = last_date + timedelta(days=h)
            cur_idx = n_orig + h - 1
            cur_feats = self._extract_features(np.array(sim_history, dtype=float), cur_idx, cur_date)
            try:
                pred = float(self.model.predict([cur_feats])[0])
                pred = max(0.0, pred)
            except _MODEL_ERRORS:
                pred = max(0.0, self._fallback_mean)

            predictions.append(pred)
            sim_history.append(pred)

        return np.array(predictions, dtype=float)


class AutoARIMAForecaster:
    """Parsimonious, fast Auto-ARIMA / SARIMAX candidate selector."""

    def __init__(self, seasonal_periods: int = 7) -> None:
        self.seasonal_periods = seasonal_periods
        self.fitted_model = None
        self.fitted_values: np.ndarray | None = None
        self.residuals: np.ndarray | None = None
        self._fallback_mean: float = 0.0

    def fit(self, series: np.ndarray | list[float]) -> AutoARIMAForecaster:
        """Fit best ARIMA/SARIMAX model over candidate orders minimizing AIC."""
        y = np.asarray(series, dtype=float)
        n = len(y)
        self._fallback_mean = float(np.mean(y)) if n > 0 else 0.0

        if n < 14:
            self.fitted_values = np.repeat(self._fallback_mean, n)
            self.residuals = y - self.fitted_values
            return self

        candidate_orders = [(1, 0, 0), (1, 1, 0), (1, 0, 1)]
        best_aic = float("inf")
        best_res = None

        for order in candidate_orders:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    mod = ARIMA(y, order=order)
                    res = mod.fit()
                    if res.aic < best_aic:
                        best_aic = res.aic
                        best_res = res
            except _MODEL_ERRORS:
                continue

        if best_res is not None:
            self.fitted_model = best_res
            fitted = np.maximum(0.0, np.asarray(best_res.fittedvalues, dtype=float))
            self.fitted_values = fitted
            self.residuals = y - fitted
        else:
            self.fitted_values = np.repeat(self._fallback_mean, n)
            self.residuals = y - self.fitted_values

        return self

    def predict(self, horizon_days: int) -> np.ndarray:
        """Forecast horizon_days ahead with ARIMA."""
        if horizon_days <= 0:
            return np.array([])
        if self.fitted_model is not None:
            try:
                preds = self.fitted_model.forecast(steps=horizon_days)
                return np.maximum(0.0, np.asarray(preds, dtype=float))
            except _MODEL_ERRORS:
                return np.repeat(max(0.0, self._fallback_mean), horizon_days)
        return np.repeat(max(0.0, self._fallback_mean), horizon_days)
