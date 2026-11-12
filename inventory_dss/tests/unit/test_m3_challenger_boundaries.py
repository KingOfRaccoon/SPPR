"""Milestone 3 Empirical Challenger Boundary & Invariants Verification Suite.

Authored by challenger_m3_2 (teamwork_challenger: Boundary & Mathematical Invariants Verifier).
Stress-tests boundary conditions, degeneracies, mathematical invariants,
and DSS Passport Sections 4 & 6 numerical consistency.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from inventory_dss.forecasting.baseline import (
    CrostonForecaster,
    ExponentialSmoothingForecaster,
)
from inventory_dss.forecasting.metrics import (
    calculate_forecast_metrics,
    calculate_mae,
    calculate_mape,
    calculate_rmse,
    calculate_wape,
)
from inventory_dss.forecasting.model import DemandForecaster
from inventory_dss.models.domain import SKU, DiscountTier, Supplier, Warehouse
from inventory_dss.optimization.capacity import (
    CapacityOptimizer,
    scale_single_item_to_capacity,
)
from inventory_dss.optimization.engine import InventoryOptimizer
from inventory_dss.optimization.eoq import (
    calculate_classical_eoq,
    calculate_eoq_with_discounts,
)
from inventory_dss.optimization.stochastic import (
    calculate_rop,
    calculate_safety_stock,
    calculate_stochastic_total_cost,
    get_service_level_z,
)

# =============================================================================
# 1. FORECASTING DEGENERACIES & BOUNDARY BEHAVIOR
# =============================================================================

class TestForecastingDegeneracies:
    """Empirical verification of demand forecaster on degenerate series."""

    def test_constant_series_variance_zero(self):
        """Constant series must yield exactly zero variance and collapsed uncertainty bounds."""
        forecaster = DemandForecaster()
        constant_series = np.full(100, 30.0)
        res = forecaster.fit_predict(constant_series, horizon_days=20, holdout_days=20)

        assert res.std_daily_demand == 0.0, "Standard deviation on constant series must be exactly 0.0"
        assert res.mean_daily_demand == 30.0, "Mean forecast must match constant demand"
        assert all(p == 30.0 for p in res.point_forecast)
        assert res.lower_bound_95 == res.point_forecast == res.upper_bound_95, (
            "Uncertainty corridor must collapse to point forecast when variance is zero"
        )

    def test_step_function_adaptation(self):
        """Step function regime shift must adapt and maintain non-negative forecasts."""
        forecaster = DemandForecaster()
        step_series = np.concatenate([np.full(50, 10.0), np.full(50, 50.0)])
        res = forecaster.fit_predict(step_series, horizon_days=14, holdout_days=20)

        assert all(p >= 0.0 for p in res.point_forecast), "Forecast cannot be negative"
        assert all(0.0 <= l <= p <= u for l, p, u in zip(res.lower_bound_95, res.point_forecast, res.upper_bound_95))
        assert np.mean(res.point_forecast) > 30.0

    def test_impulse_shock_numerical_stability(self):
        """Severe impulse shock (+1500% spike) must not produce NaNs, infinities, or crash."""
        forecaster = DemandForecaster()
        impulse_series = np.full(100, 20.0)
        impulse_series[80] = 300.0
        res = forecaster.fit_predict(impulse_series, horizon_days=14, holdout_days=20)

        assert not np.isnan(res.point_forecast).any(), "Forecast cannot contain NaN"
        assert not np.isinf(res.point_forecast).any(), "Forecast cannot contain Inf"
        assert all(0.0 <= l <= p <= u for l, p, u in zip(res.lower_bound_95, res.point_forecast, res.upper_bound_95))

    def test_purely_seasonal_synthetic_series(self):
        """Purely periodic series (sine wave, period=7) must be recognized with low error."""
        forecaster = DemandForecaster()
        seasonal = 20.0 + 10.0 * np.sin(2.0 * np.pi * np.arange(140) / 7.0)
        res = forecaster.fit_predict(seasonal, horizon_days=14, holdout_days=28)

        assert res.metrics["WAPE"] < 0.15, f"WAPE on pure seasonal series should be < 15%, got {res.metrics['WAPE']}"
        assert all(0.0 <= l <= p <= u for l, p, u in zip(res.lower_bound_95, res.point_forecast, res.upper_bound_95))

    def test_croston_vs_ses_intermittent_demand(self):
        """Croston must maintain constant rate separating intervals and demand size, unlike decaying SES."""
        intermittent = np.zeros(100)
        intermittent[10] = 10.0
        intermittent[20] = 12.0
        intermittent[30] = 8.0
        intermittent[40] = 10.0
        intermittent[50] = 10.0

        croston = CrostonForecaster(alpha=0.1).fit(intermittent)
        ses = ExponentialSmoothingForecaster(alpha=0.2).fit(intermittent)
        p_croston = croston.predict(10)
        p_ses = ses.predict(10)

        assert p_croston[0] > 0.0, "Croston rate must be positive"
        assert math.isclose(p_croston[0], 1.0, abs_tol=0.3), f"Croston rate expected ~1.0, got {p_croston[0]}"
        assert p_ses[0] < p_croston[0], "Standard SES level should decay below Croston rate after quiet periods"
        assert not np.isnan(p_croston).any()
        assert not np.isnan(p_ses).any()

    def test_prediction_interval_monotonicity_and_ordering(self):
        """Uncertainty corridor width must be non-decreasing with horizon and non-negative."""
        forecaster = DemandForecaster()
        rng = np.random.default_rng(101)
        series = 50.0 + rng.normal(0, 5, size=80)
        res = forecaster.fit_predict(series, horizon_days=30, holdout_days=20)

        corridor_widths = [u - l for l, u in zip(res.lower_bound_95, res.upper_bound_95)]
        assert corridor_widths[-1] >= corridor_widths[0], (
            f"Corridor width at horizon end ({corridor_widths[-1]}) must be >= start ({corridor_widths[0]})"
        )
        for l, p, u in zip(res.lower_bound_95, res.point_forecast, res.upper_bound_95):
            assert 0.0 <= l <= p <= u, f"Ordering violation: 0 <= {l} <= {p} <= {u}"

    def test_empirical_prediction_interval_coverage_rate(self):
        """Empirical coverage on stationary Gaussian process should cover actuals."""
        np.random.seed(42)
        noise = np.random.normal(0, 3.0, 200)
        series = np.maximum(0.0, 25.0 + noise)

        forecaster = DemandForecaster()
        res = forecaster.fit_predict(series[:150], horizon_days=50, holdout_days=30)
        actuals = series[150:200]
        covered = sum(l <= a <= u for l, a, u in zip(res.lower_bound_95, actuals, res.upper_bound_95))
        coverage_rate = covered / len(actuals)
        assert coverage_rate >= 0.85, f"Coverage rate should be >= 85%, got {coverage_rate*100:.1f}%"

    def test_metric_edge_cases(self):
        """Verify error metrics under zero actuals, near-zero forecasts, and empty inputs."""
        assert calculate_mae([], []) == 0.0
        assert calculate_rmse([], []) == 0.0
        assert calculate_mape([], []) == 0.0
        assert calculate_wape([], []) == 0.0

        m_zeros = calculate_forecast_metrics([0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
        assert m_zeros["MAE"] == 0.0
        assert m_zeros["RMSE"] == 0.0
        assert m_zeros["MAPE"] == 0.0
        assert m_zeros["WAPE"] == 0.0

        m_zero_act = calculate_forecast_metrics([0.0, 0.0], [5.0, 5.0])
        assert m_zero_act["MAE"] == 5.0
        assert m_zero_act["RMSE"] == 5.0
        assert m_zero_act["WAPE"] == 1.0

        m_near_zero = calculate_forecast_metrics([10.0, 10.0], [1e-9, 1e-9])
        assert math.isclose(m_near_zero["MAE"], 10.0, abs_tol=1e-4)
        assert math.isclose(m_near_zero["WAPE"], 1.0, abs_tol=1e-4)

    def test_dataframe_with_string_dates_parsing(self):
        """CHALLENGE / BUG CHECK: DataFrame loaded from CSV has string 'date' column."""
        forecaster = DemandForecaster()
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"] * 10,
            "sku_id": ["SKU-TEST"] * 40,
            "quantity": [10.0, 15.0, 20.0, 25.0] * 10,
        })
        res = forecaster.fit_predict(df, horizon_days=7, holdout_days=10)
        assert res.sku_id == "SKU-TEST"


# =============================================================================
# 2. OPTIMIZATION BOUNDARIES & MATHEMATICAL INVARIANTS
# =============================================================================

class TestOptimizationBoundariesAndInvariants:
    """Empirical verification of optimization models, cost functions, and capacity bounds."""

    def test_zero_holding_cost_limit(self):
        """Zero holding cost limit in classical EOQ."""
        eoq = calculate_classical_eoq(annual_demand=1000.0, order_cost=50.0, holding_cost_per_unit=0.0)
        assert eoq == 0.0, "EOQ should return 0.0 when holding cost is 0 to avoid division by zero"

    def test_zero_ordering_cost_limit(self):
        """Zero ordering cost limit in classical EOQ and discounts."""
        eoq = calculate_classical_eoq(annual_demand=1000.0, order_cost=0.0, holding_cost_per_unit=2.0)
        assert eoq == 0.0, "EOQ should return 0.0 when ordering cost is 0"

        res_disc = calculate_eoq_with_discounts(
            annual_demand=1000.0, base_unit_price=10.0, holding_rate=0.2, order_cost=0.0, min_order_quantity=1
        )
        assert res_disc.optimal_quantity >= 1.0, "Discounts EOQ with K=0 falls back to MOQ"

    def test_lead_time_variance_sensitivity_and_monotonicity(self):
        """Safety Stock must strictly monotonically increase with supplier lead-time variance sigma_L."""
        mu_d = 25.0
        sigma_d = 4.0
        mu_l = 7.0
        sigma_l_candidates = [0.0, 0.5, 1.0, 2.0, 4.0, 8.0]
        ss_list = []

        for sl in sigma_l_candidates:
            ss = calculate_safety_stock(
                mean_demand=mu_d, std_demand=sigma_d, mean_lead_time=mu_l, std_lead_time=sl, service_level=0.95
            )
            ss_list.append(ss)

        for i in range(len(ss_list) - 1):
            assert ss_list[i + 1] > ss_list[i], (
                f"Monotonicity violation: sigma_L={sigma_l_candidates[i+1]} gave SS={ss_list[i+1]}, "
                f"expected > {ss_list[i]} for sigma_L={sigma_l_candidates[i]}"
            )

        z = get_service_level_z(0.95)
        var_exact = mu_l * (sigma_d ** 2) + (mu_d ** 2) * (2.0 ** 2)
        expected_ss = round(z * math.sqrt(var_exact), 2)
        assert ss_list[3] == expected_ss

    def test_quantity_discount_boundary_jump_condition(self):
        """Batch size jumps to discount breakpoint ONLY when total cost is strictly lower."""
        profitable_tiers = [DiscountTier(min_quantity=200, discount_percentage=0.20)]
        res_a = calculate_eoq_with_discounts(
            annual_demand=1000.0, base_unit_price=100.0, holding_rate=0.20, order_cost=50.0,
            discount_tiers=profitable_tiers
        )
        assert res_a.optimal_quantity == 200.0
        assert res_a.applied_tier_min_quantity == 200

        unprofitable_tiers = [DiscountTier(min_quantity=10000, discount_percentage=0.001)]
        res_b = calculate_eoq_with_discounts(
            annual_demand=1000.0, base_unit_price=100.0, holding_rate=0.20, order_cost=50.0,
            discount_tiers=unprofitable_tiers
        )
        assert res_b.optimal_quantity == 71.0
        assert res_b.applied_tier_min_quantity == 0

    def test_warehouse_capacity_slack_shadow_prices_zero(self):
        """When warehouse has excess capacity, shadow prices lambda and mu must be exactly 0.0."""
        wh = Warehouse(
            warehouse_id="WH-HUGE",
            name="Huge",
            total_volume_capacity_m3=10000.0,
            total_weight_capacity_kg=1000000.0,
        )
        optimizer = CapacityOptimizer(wh)
        skus = {
            "SKU-A": SKU(sku_id="SKU-A", name="A", category="Electronics", unit_price=10.0, unit_volume_m3=0.1, unit_weight_kg=1.0),
        }
        res = optimizer.optimize_allocation(
            unconstrained_eoqs={"SKU-A": 50.0},
            skus=skus,
            annual_demands={"SKU-A": 500.0},
            order_costs={"SKU-A": 50.0},
            holding_costs={"SKU-A": 2.0},
        )
        assert not res.is_constrained
        assert res.lambda_volume == 0.0
        assert res.mu_weight == 0.0

    def test_warehouse_capacity_binding_shadow_price_positive(self):
        """CHALLENGE / BUG CHECK: When warehouse capacity binds, shadow price lambda/mu must be > 0.0."""
        wh = Warehouse(
            warehouse_id="WH-TIGHT",
            name="Tight",
            total_volume_capacity_m3=5.0,
            total_weight_capacity_kg=100.0,
        )
        optimizer = CapacityOptimizer(wh)
        skus = {
            "SKU-A": SKU(sku_id="SKU-A", name="A", category="Raw Materials", unit_price=10.0, unit_volume_m3=0.5, unit_weight_kg=20.0),
        }
        res = optimizer.optimize_allocation(
            unconstrained_eoqs={"SKU-A": 100.0},
            skus=skus,
            annual_demands={"SKU-A": 1000.0},
            order_costs={"SKU-A": 50.0},
            holding_costs={"SKU-A": 2.0},
        )
        assert res.is_constrained
        shadow_price_positive = (res.lambda_volume > 0.0 or res.mu_weight > 0.0)
        assert shadow_price_positive, (
            f"Binding warehouse capacity shadow price must be > 0.0, "
            f"got lambda_volume={res.lambda_volume}, mu_weight={res.mu_weight}"
        )

    def test_warehouse_capacity_never_exceeded_post_allocation(self):
        """CHALLENGE / BUG CHECK: Allocated batch quantities must NEVER exceed warehouse V_max or W_max."""
        wh = Warehouse(
            warehouse_id="WH-TIGHT-2",
            name="Tight 2",
            total_volume_capacity_m3=2.0,
            total_weight_capacity_kg=20.0,
        )
        optimizer = CapacityOptimizer(wh)
        skus = {
            "SKU-1": SKU(sku_id="SKU-1", name="Item 1", category="Electronics", unit_price=100.0, unit_volume_m3=0.1, unit_weight_kg=1.0, pack_size=1),
            "SKU-2": SKU(sku_id="SKU-2", name="Item 2", category="Spare Parts", unit_price=200.0, unit_volume_m3=0.2, unit_weight_kg=2.0, pack_size=1),
        }
        res = optimizer.optimize_allocation(
            unconstrained_eoqs={"SKU-1": 50.0, "SKU-2": 40.0},
            skus=skus,
            annual_demands={"SKU-1": 1000.0, "SKU-2": 500.0},
            order_costs={"SKU-1": 50.0, "SKU-2": 50.0},
            holding_costs={"SKU-1": 20.0, "SKU-2": 40.0},
        )
        assert res.is_constrained
        assert res.total_volume_m3 <= wh.total_volume_capacity_m3 + 1e-4, (
            f"Volume capacity exceeded! {res.total_volume_m3} > {wh.total_volume_capacity_m3}"
        )
        assert res.total_weight_kg <= wh.total_weight_capacity_kg + 1e-4, (
            f"Weight capacity exceeded! {res.total_weight_kg} > {wh.total_weight_capacity_kg}"
        )

    def test_numerical_stability_negative_and_zero_inputs(self):
        """Verify no division by zero or negative order quantities on degenerate inputs."""
        assert calculate_safety_stock(-10, -5, -2, -1) == 0.0
        assert calculate_rop(-10, -5, -5) == 0.0
        assert scale_single_item_to_capacity(-10, 0, 0, 0, 0) == 0.0
        tco = calculate_stochastic_total_cost(0, -10, 0, 0, 0, 0)
        assert all(v >= 0.0 for v in tco.values())


# =============================================================================
# 3. PASSPORT DSS SECTIONS 4 & 6 NUMERICAL CONSISTENCY
# =============================================================================

class TestPassportDSSNumericalConsistency:
    """Validate numerical alignment between docs/PASSPORT_DSS.md and live models."""

    @pytest.fixture
    def synthetic_data(self):
        base_dir = Path(__file__).resolve().parent.parent.parent
        data_dir = base_dir / "data" / "synthetic"
        if not (data_dir / "skus.csv").exists():
            pytest.skip("Synthetic data not found")

        skus_df = pd.read_csv(data_dir / "skus.csv")
        suppliers_df = pd.read_csv(data_dir / "suppliers.csv")
        demand_df = pd.read_csv(data_dir / "demand_history.csv")
        demand_df["date"] = pd.to_datetime(demand_df["date"]).dt.date
        with open(data_dir / "warehouse.json") as f:
            wh_dict = json.load(f)

        return {
            "skus": {r["sku_id"]: SKU(**r) for _, r in skus_df.iterrows()},
            "suppliers": {r["supplier_id"]: Supplier(**r) for _, r in suppliers_df.iterrows()},
            "demand": demand_df,
            "warehouse": Warehouse(**wh_dict),
        }

    def test_passport_section_6_forecasting_metrics_consistency(self, synthetic_data):
        """Check SKU-ELEC-001 metrics reported in Section 6.3 Table 1 against live model."""
        forecaster = DemandForecaster()
        demand_df = synthetic_data["demand"]
        elec_df = demand_df[demand_df["sku_id"] == "SKU-ELEC-001"]
        fc = forecaster.fit_predict(elec_df, horizon_days=30, holdout_days=60)

        assert fc.model_name == "RidgeRegression"
        assert math.isclose(fc.mean_daily_demand, 14.75, abs_tol=0.1)
        assert math.isclose(fc.std_daily_demand, 3.96, abs_tol=0.1)
        assert math.isclose(fc.metrics["MAE"], 1.17, abs_tol=0.05)
        assert math.isclose(fc.metrics["RMSE"], 1.44, abs_tol=0.05)
        assert math.isclose(fc.metrics["WAPE"], 0.0808, abs_tol=0.01)

    def test_passport_section_4_optimization_policy_consistency(self, synthetic_data):
        """Check SKU-ELEC-001 policy in Section 4.3 Table 1 against live optimizer."""
        forecaster = DemandForecaster()
        optimizer = InventoryOptimizer()
        demand_df = synthetic_data["demand"]
        skus = synthetic_data["skus"]
        suppliers = synthetic_data["suppliers"]
        warehouse = synthetic_data["warehouse"]

        elec_df = demand_df[demand_df["sku_id"] == "SKU-ELEC-001"]
        fc = forecaster.fit_predict(elec_df, horizon_days=30, holdout_days=60)
        sup = suppliers["SUP-PREMIUM"]
        plan = optimizer.calculate_policy(skus["SKU-ELEC-001"], fc, sup, warehouse, service_level=0.95)

        assert math.isclose(plan.eoq, 111.0, abs_tol=1.0)
        assert math.isclose(plan.safety_stock, 17.8, abs_tol=0.5)
        assert math.isclose(plan.reorder_point, 76.8, abs_tol=0.5)
        assert math.isclose(plan.expected_annual_holding_cost, 258051.0, rel_tol=0.01)
        assert math.isclose(plan.expected_annual_ordering_cost, 193956.0, rel_tol=0.01)
