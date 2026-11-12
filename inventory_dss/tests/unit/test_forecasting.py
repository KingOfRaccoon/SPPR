"""Unit tests for time-series demand forecasting engines and error metrics."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

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
from inventory_dss.forecasting.metrics import (
    calculate_forecast_metrics,
    calculate_mae,
    calculate_mape,
    calculate_rmse,
    calculate_wape,
)
from inventory_dss.forecasting.model import DemandForecaster
from inventory_dss.models.domain import DemandRecord, ForecastResult


class TestForecastingMetrics:
    """Validate mathematical correctness and robustness of forecasting error metrics."""

    def test_mae_calculation_exact(self):
        y_true = [10.0, 20.0, 30.0]
        y_pred = [12.0, 18.0, 35.0]
        # abs diffs: [2, 2, 5] -> mean = 3.0
        assert math.isclose(calculate_mae(y_true, y_pred), 3.0)

    def test_rmse_calculation_exact(self):
        y_true = [10.0, 20.0, 30.0]
        y_pred = [10.0, 23.0, 26.0]
        # diffs: [0, 3, -4] -> squared: [0, 9, 16] -> mean = 25/3 -> sqrt(25/3) = 2.88675
        assert math.isclose(calculate_rmse(y_true, y_pred), math.sqrt(25.0 / 3.0))

    def test_rmse_ge_mae_jensens_inequality(self):
        rng = np.random.default_rng(123)
        y_true = rng.uniform(5, 50, size=50)
        y_pred = y_true + rng.normal(0, 5, size=50)
        mae = calculate_mae(y_true, y_pred)
        rmse = calculate_rmse(y_true, y_pred)
        assert rmse >= mae, "RMSE must be strictly >= MAE by Jensen's inequality"

    def test_mape_calculation_with_zeros(self):
        y_true = [0.0, 10.0, 20.0]
        y_pred = [0.0, 12.0, 18.0]
        # Non-zero actuals: 10 and 20 -> |10-12|/10 = 0.2, |20-18|/20 = 0.1 -> mean 0.15
        mape = calculate_mape(y_true, y_pred)
        assert math.isclose(mape, 0.15, abs_tol=1e-3)

    def test_wape_calculation_intermittent(self):
        y_true = [0.0, 0.0, 10.0, 0.0]
        y_pred = [1.0, 0.0, 8.0, 1.0]
        # abs diffs: 1 + 0 + 2 + 1 = 4.0; sum(y_true) = 10.0 -> WAPE = 0.4
        wape = calculate_wape(y_true, y_pred)
        assert math.isclose(wape, 0.4, abs_tol=1e-5)

    def test_empty_metrics_handling(self):
        assert calculate_mae([], []) == 0.0
        assert calculate_rmse([], []) == 0.0
        assert calculate_mape([], []) == 0.0
        assert calculate_wape([], []) == 0.0

    def test_calculate_forecast_metrics_dictionary_structure(self):
        y_true = [10.0, 20.0, 30.0, 40.0]
        y_pred = [11.0, 19.0, 31.0, 38.0]
        metrics = calculate_forecast_metrics(y_true, y_pred)
        assert "MAE" in metrics
        assert "RMSE" in metrics
        assert "MAPE" in metrics
        assert "WAPE" in metrics
        assert metrics["RMSE"] >= metrics["MAE"]


class TestBaselineForecasters:
    """Validate Simple Moving Average, Exponential Smoothing, and Croston methods."""

    def test_sma_window_averaging(self):
        series = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0]
        sma3 = SimpleMovingAverageForecaster(window=3).fit(series)
        # last 3 items: 18, 20, 22 -> mean = 20.0
        preds = sma3.predict(5)
        assert len(preds) == 5
        assert np.all(preds == 20.0)

    def test_sma_window_exceeds_length(self):
        series = [5.0, 15.0]
        sma7 = SimpleMovingAverageForecaster(window=7).fit(series)
        # mean of all items = 10.0
        preds = sma7.predict(3)
        assert np.all(preds == 10.0)

    def test_ses_exponential_weighting(self):
        series = [10.0, 10.0, 10.0, 20.0]
        ses = ExponentialSmoothingForecaster(alpha=0.5).fit(series)
        preds = ses.predict(4)
        assert len(preds) == 4
        # Level updates: l0=10, l1=10, l2=10, l3=0.5*20 + 0.5*10 = 15.0
        assert math.isclose(preds[0], 15.0, abs_tol=1e-4)

    def test_ses_invalid_alpha_raises_error(self):
        with pytest.raises(ValueError):
            ExponentialSmoothingForecaster(alpha=0.0)
        with pytest.raises(ValueError):
            ExponentialSmoothingForecaster(alpha=1.5)

    def test_croston_intermittent_separation(self):
        # Intermittent series: demand arrives every 2 days
        series = [0.0, 10.0, 0.0, 10.0, 0.0, 10.0]
        croston = CrostonForecaster(alpha=0.2).fit(series)
        preds = croston.predict(7)
        assert len(preds) == 7
        assert np.all(preds > 0.0)
        # Expected rate is around 10 / 2 = 5.0
        assert 3.0 <= preds[0] <= 7.0

    def test_croston_all_zeros(self):
        series = [0.0, 0.0, 0.0, 0.0]
        croston = CrostonForecaster(alpha=0.1).fit(series)
        preds = croston.predict(3)
        assert np.all(preds == 0.0)


class TestAdvancedForecasters:
    """Validate Holt-Winters, Ridge Regression with lags, and Auto-ARIMA."""

    def test_holt_winters_additive_trend_and_seasonality(self):
        # 56 days of daily data (8 weeks) with weekly seasonality and upward trend
        t = np.arange(56)
        trend = 0.5 * t
        seasonal = 5.0 * np.sin(2 * np.pi * t / 7.0)
        series = 20.0 + trend + seasonal

        hw = HoltWintersForecaster(trend="add", seasonal="add", seasonal_periods=7).fit(series)
        preds = hw.predict(7)
        assert len(preds) == 7
        assert np.all(preds > 0.0)
        # Forecast should continue upward trend above baseline mean
        assert np.mean(preds) > 20.0

    def test_holt_winters_multiplicative_fallback_on_zeros(self):
        # Multiplicative requested on series with zeros -> should gracefully adapt without crashing
        series = [0.0, 1.0, 5.0, 10.0, 0.0, 8.0, 12.0] * 3
        hw = HoltWintersForecaster(trend="mul", seasonal="mul", seasonal_periods=7).fit(series)
        preds = hw.predict(5)
        assert len(preds) == 5
        assert np.all(preds >= 0.0)

    def test_ridge_regression_recursive_multistep(self):
        # Daily series with autoregressive structure
        series = [10.0 + (i % 7) * 2.0 for i in range(40)]
        base_date = date(2025, 1, 1)
        dates = [base_date + timedelta(days=i) for i in range(40)]

        ridge = RidgeRegressionForecaster(lags=(1, 2, 7), alpha=1.0).fit(series, dates=dates)
        preds = ridge.predict(14)
        assert len(preds) == 14
        assert np.all(preds >= 0.0)
        assert not np.any(np.isnan(preds))

    def test_auto_arima_candidate_fitting(self):
        series = [15.0 + math.sin(i / 2.0) for i in range(35)]
        arima = AutoARIMAForecaster(seasonal_periods=7).fit(series)
        preds = arima.predict(7)
        assert len(preds) == 7
        assert np.all(preds >= 0.0)


class TestDemandForecasterEngine:
    """Validate full DemandForecaster pipeline, hold-out splitting, and uncertainty quantification."""

    def test_fit_predict_full_interface(self):
        forecaster = DemandForecaster()
        base_date = date(2025, 1, 1)
        history = [
            DemandRecord(date=base_date + timedelta(days=i), sku_id="SKU-TEST-01", quantity=10.0 + (i % 7))
            for i in range(60)
        ]

        result = forecaster.fit_predict(history, horizon_days=30, holdout_days=14)
        assert isinstance(result, ForecastResult)
        assert result.sku_id == "SKU-TEST-01"
        assert result.forecast_horizon_days == 30
        assert len(result.point_forecast) == 30
        assert len(result.lower_bound_95) == 30
        assert len(result.upper_bound_95) == 30
        assert result.mean_daily_demand > 0.0
        assert result.std_daily_demand > 0.0
        assert "MAE" in result.metrics
        assert "RMSE" in result.metrics
        assert "WAPE" in result.metrics
        assert result.metrics["RMSE"] >= result.metrics["MAE"]

    def test_zero_demand_bounds_collapse(self):
        forecaster = DemandForecaster()
        history = [
            DemandRecord(date=date(2025, 1, 1) + timedelta(days=i), sku_id="SKU-ZERO", quantity=0.0)
            for i in range(30)
        ]
        result = forecaster.fit_predict(history, horizon_days=10, holdout_days=5)
        assert result.mean_daily_demand == 0.0
        assert result.std_daily_demand == 0.0
        assert all(p == 0.0 for p in result.point_forecast)
        assert all(l == 0.0 for l in result.lower_bound_95)
        assert all(u == 0.0 for u in result.upper_bound_95)

    def test_uncertainty_interval_ordering_and_monotonicity(self):
        forecaster = DemandForecaster()
        history = [
            DemandRecord(date=date(2025, 1, 1) + timedelta(days=i), sku_id="SKU-VAR", quantity=20.0 + (i % 5) * 4.0)
            for i in range(50)
        ]
        result = forecaster.fit_predict(history, horizon_days=30, holdout_days=10)

        # Invariant 1: 0 <= Lower <= Point <= Upper
        for l, p, u in zip(result.lower_bound_95, result.point_forecast, result.upper_bound_95):
            assert 0.0 <= l <= p <= u, f"Bounds ordering violation: {l} <= {p} <= {u}"

        # Invariant 2: Prediction corridor widens or maintains width over time
        w_start = result.upper_bound_95[0] - result.lower_bound_95[0]
        w_end = result.upper_bound_95[-1] - result.lower_bound_95[-1]
        assert w_end >= w_start, f"Interval should expand: w_start={w_start}, w_end={w_end}"

    def test_dataframe_and_numeric_input_compatibility(self):
        forecaster = DemandForecaster()
        # DataFrame input
        df = pd.DataFrame({
            "date": [date(2025, 1, 1) + timedelta(days=i) for i in range(30)],
            "sku_id": ["SKU-DF"] * 30,
            "quantity": [15.0 + i * 0.1 for i in range(30)],
        })
        res_df = forecaster.fit_predict(df, horizon_days=7, holdout_days=5)
        assert res_df.sku_id == "SKU-DF"
        assert len(res_df.point_forecast) == 7

        # 1D numeric list input
        nums = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0]
        res_nums = forecaster.fit_predict(nums, horizon_days=5, holdout_days=2)
        assert res_nums.sku_id == "SKU-UNKNOWN"
        assert len(res_nums.point_forecast) == 5

    def test_empty_history_raises_value_error(self):
        forecaster = DemandForecaster()
        with pytest.raises(ValueError):
            forecaster.fit_predict([])
        with pytest.raises(ValueError):
            forecaster.fit_predict(pd.DataFrame())

    def test_constant_series_zero_variance(self):
        forecaster = DemandForecaster()
        history = [
            DemandRecord(date=date(2025, 1, 1) + timedelta(days=i), sku_id="SKU-CONST", quantity=25.0)
            for i in range(25)
        ]
        result = forecaster.fit_predict(history, horizon_days=10, holdout_days=5)
        assert result.mean_daily_demand == 25.0
        assert result.std_daily_demand == 0.0
        assert all(l == 25.0 for l in result.lower_bound_95)
        assert all(u == 25.0 for u in result.upper_bound_95)
