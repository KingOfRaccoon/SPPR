"""Main demand forecasting engine with model selection and uncertainty quantification."""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from inventory_dss.forecasting.advanced import (
    AutoARIMAForecaster,
    HoltWintersForecaster,
    RidgeRegressionForecaster,
)
from inventory_dss.forecasting.baseline import (
    CrostonForecaster,
    ExponentialSmoothingForecaster,
    SimpleMovingAverageForecaster,
)
from inventory_dss.forecasting.metrics import calculate_forecast_metrics
from inventory_dss.models.domain import DemandRecord, ForecastResult

Z_95_DEFAULT = 1.6448536269514722  # 95% quantile (one-sided) or standard DSS interval quantile


class DemandForecaster:
    """Production-grade demand forecasting engine.

    Fits candidate models on temporal train split, evaluates on hold-out validation set,
    selects best-performing model, refits on full history, and quantifies 95% uncertainty intervals.
    """

    def _parse_history(
        self,
        history: list[DemandRecord] | pd.DataFrame | list[dict[str, Any]] | np.ndarray,
    ) -> tuple[str, np.ndarray, list[date] | None]:
        """Normalize history into sku_id, 1D quantities array, and dates list."""
        if history is None or (hasattr(history, "__len__") and len(history) == 0):
            raise ValueError("History cannot be empty")

        if isinstance(history, pd.DataFrame):
            if history.empty:
                raise ValueError("History cannot be empty")
            sku_id = str(history["sku_id"].iloc[0]) if "sku_id" in history.columns else "SKU-UNKNOWN"
            qty_col = "quantity" if "quantity" in history.columns else ("demand" if "demand" in history.columns else None)
            if qty_col is None:
                raise ValueError("DataFrame must contain 'quantity' or 'demand' column")
            quantities = history[qty_col].to_numpy(dtype=float)
            dates = None
            if "date" in history.columns:
                try:
                    dates = pd.to_datetime(history["date"]).dt.date.tolist()
                except (ValueError, TypeError, AttributeError):
                    dates = None
            return sku_id, quantities, dates

        if isinstance(history, np.ndarray):
            if len(history) == 0:
                raise ValueError("History cannot be empty")
            return "SKU-UNKNOWN", history.astype(float).flatten(), None

        # Sequence of items
        first_item = history[0]
        if isinstance(first_item, DemandRecord):
            sku_id = first_item.sku_id
            quantities = np.array([r.quantity for r in history], dtype=float)
            dates = [r.date for r in history]
            return sku_id, quantities, dates

        if isinstance(first_item, dict):
            sku_id = str(first_item.get("sku_id", "SKU-UNKNOWN"))
            qty_key = "quantity" if "quantity" in first_item else "demand"
            quantities = np.array([item[qty_key] for item in history], dtype=float)
            dates = None
            raw_dates = [item["date"] for item in history if "date" in item]
            if len(raw_dates) == len(history):
                try:
                    dates = pd.to_datetime(pd.Series(raw_dates)).dt.date.tolist()
                except (ValueError, TypeError, AttributeError):
                    dates = None
            return sku_id, quantities, dates

        # Numeric list
        quantities = np.asarray(history, dtype=float)
        return "SKU-UNKNOWN", quantities, None

    def fit_predict(
        self,
        history: list[DemandRecord] | pd.DataFrame | list[dict[str, Any]] | np.ndarray,
        horizon_days: int = 30,
        holdout_days: int = 60,
    ) -> ForecastResult:
        """Fit demand models, evaluate on hold-out, and generate forecast with 95% bounds."""
        sku_id, quantities, dates = self._parse_history(history)
        n = len(quantities)

        # 1. Edge Case: Complete zero demand
        if np.all(quantities == 0.0):
            zeros = [0.0] * horizon_days
            return ForecastResult(
                sku_id=sku_id,
                forecast_horizon_days=horizon_days,
                point_forecast=zeros,
                lower_bound_95=zeros,
                upper_bound_95=zeros,
                mean_daily_demand=0.0,
                std_daily_demand=0.0,
                metrics={"MAE": 0.0, "RMSE": 0.0, "MAPE": 0.0, "WAPE": 0.0},
                model_name="ZeroDemand",
            )

        # 2. Temporal Hold-Out Split
        # Require at least 7 training samples
        if n < holdout_days + 7:
            # Fall back to shorter holdout or in-sample evaluation
            val_len = max(1, min(holdout_days, n // 3)) if n >= 6 else 0
            if val_len > 0:
                train = quantities[:-val_len]
                val = quantities[-val_len:]
                train_dates = dates[:-val_len] if dates else None
            else:
                train = quantities
                val = quantities
                train_dates = dates
        else:
            train = quantities[:-holdout_days]
            val = quantities[-holdout_days:]
            train_dates = dates[:-holdout_days] if dates else None

        val_len = len(val)

        # 3. Candidate Models
        candidates: dict[str, Any] = {}

        # Intermittent demand detection (Croston)
        zero_fraction = float(np.mean(train == 0.0))
        if zero_fraction >= 0.5:
            candidates["Croston"] = CrostonForecaster(alpha=0.1)

        # Holt-Winters Additive
        if len(train) >= 14:
            candidates["HoltWinters"] = HoltWintersForecaster(
                trend="add", seasonal="add", seasonal_periods=7
            )

        # Ridge Regression with lags and calendar features
        candidates["RidgeRegression"] = RidgeRegressionForecaster(
            lags=(1, 2, 7, 14), alpha=1.0
        )

        # Simple Moving Average baseline
        candidates["MovingAverage"] = SimpleMovingAverageForecaster(window=7)

        # Single Exponential Smoothing
        candidates["ExponentialSmoothing"] = ExponentialSmoothingForecaster(alpha=0.2)

        # Auto-ARIMA / SARIMAX if sufficient data
        if len(train) >= 28:
            candidates["SARIMAX"] = AutoARIMAForecaster(seasonal_periods=7)

        # 4. Model Selection via Hold-out Validation
        best_name = "MovingAverage"
        best_wape = float("inf")
        best_rmse = float("inf")
        holdout_metrics: dict[str, float] = {}

        for name, model in candidates.items():
            try:
                if isinstance(model, RidgeRegressionForecaster):
                    model.fit(train, dates=train_dates)
                else:
                    model.fit(train)

                val_preds = model.predict(val_len)
                metrics = calculate_forecast_metrics(val, val_preds)

                # Ranking criterion: primary WAPE, secondary RMSE
                wape = metrics["WAPE"]
                rmse = metrics["RMSE"]
                if wape < best_wape or (math.isclose(wape, best_wape, abs_tol=1e-5) and rmse < best_rmse):
                    best_wape = wape
                    best_rmse = rmse
                    best_name = name
                    holdout_metrics = metrics
            except (ValueError, TypeError, RuntimeError, IndexError, AttributeError, np.linalg.LinAlgError):
                continue

        # If holdout_metrics empty for any reason, compute with fallback mean
        if not holdout_metrics:
            train_mean = float(np.mean(train))
            val_preds = np.repeat(train_mean, val_len)
            holdout_metrics = calculate_forecast_metrics(val, val_preds)

        # 5. Refit Best Model on Full History
        best_model = candidates.get(best_name)
        if best_model is None:
            best_model = SimpleMovingAverageForecaster(window=7)

        if isinstance(best_model, RidgeRegressionForecaster):
            best_model.fit(quantities, dates=dates)
        else:
            best_model.fit(quantities)

        raw_preds = best_model.predict(horizon_days)
        point_forecast = [round(max(0.0, float(p)), 2) for p in raw_preds]

        # 6. Uncertainty Quantification
        # Compute demand standard deviation sigma_D
        # If demand is perfectly deterministic (variance == 0), sigma_D = 0
        if len(quantities) > 1:
            sample_std = float(np.std(quantities, ddof=1))
        else:
            sample_std = float(np.std(quantities))

        # Uncertainty spread: if constant series, variance is zero
        std_daily_demand = round(sample_std, 4)
        mean_daily_demand = round(float(np.mean(point_forecast)), 4)


        lower_bound = []
        upper_bound = []
        z_95 = Z_95_DEFAULT

        # Uncertainty envelope expands with horizon step h
        for h in range(1, horizon_days + 1):
            pred = point_forecast[h - 1]
            if std_daily_demand == 0.0:
                pred_std = 0.0
            else:
                # Compound dispersion over forecast horizon
                pred_std = std_daily_demand * math.sqrt(1.0 + 0.05 * h)

            l_val = round(max(0.0, pred - z_95 * pred_std), 2)
            u_val = round(pred + z_95 * pred_std, 2)
            # Ensure 0 <= lower <= pred <= upper invariant
            l_val = min(l_val, pred)
            u_val = max(u_val, pred)

            lower_bound.append(l_val)
            upper_bound.append(u_val)

        return ForecastResult(
            sku_id=sku_id,
            forecast_horizon_days=horizon_days,
            point_forecast=point_forecast,
            lower_bound_95=lower_bound,
            upper_bound_95=upper_bound,
            mean_daily_demand=mean_daily_demand,
            std_daily_demand=std_daily_demand,
            metrics=holdout_metrics,
            model_name=best_name,
        )
