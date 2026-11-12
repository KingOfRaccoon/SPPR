"""Time-series demand forecasting module for Inventory DSS."""

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
from inventory_dss.forecasting.model import DemandForecaster, ForecastResult

__all__ = [
    "AutoARIMAForecaster",
    "CrostonForecaster",
    "DemandForecaster",
    "ExponentialSmoothingForecaster",
    "ForecastResult",
    "HoltWintersForecaster",
    "RidgeRegressionForecaster",
    "SimpleMovingAverageForecaster",
    "calculate_forecast_metrics",
    "calculate_mae",
    "calculate_mape",
    "calculate_rmse",
    "calculate_wape",
]
