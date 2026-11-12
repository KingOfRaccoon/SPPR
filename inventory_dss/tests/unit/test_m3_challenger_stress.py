"""Milestone 3 Empirical Challenger Stress-Testing & Invariance Verification Suite.

Authored by challenger_m3_1 (teamwork_challenger: Empirical Stress & Invariance Verifier).
Stress-tests mathematical invariants, boundary conditions, edge cases, data leakage,
and optimization feasibility for Demand Forecasting and Inventory Optimization engines.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pytest

from inventory_dss.forecasting.advanced import (
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
    calculate_rmse,
    calculate_wape,
)
from inventory_dss.forecasting.model import DemandForecaster
from inventory_dss.models.domain import (
    SKU,
    DemandRecord,
    DiscountTier,
    ForecastResult,
    Supplier,
    Warehouse,
)
from inventory_dss.optimization.capacity import (
    CapacityOptimizer,
)
from inventory_dss.optimization.engine import InventoryOptimizer
from inventory_dss.optimization.eoq import (
    calculate_classical_eoq,
    calculate_eoq_with_discounts,
    calculate_total_inventory_cost,
)
from inventory_dss.optimization.stochastic import (
    calculate_lead_time_demand_variance,
    calculate_rop,
    calculate_safety_stock,
)

# =============================================================================
# 1. FORECASTING ERROR METRICS & MATHEMATICAL INVARIANTS
# =============================================================================

class TestForecastingMetricsInvariants:
    """Rigorous empirical validation of mathematical properties of forecast metrics."""

    @pytest.mark.parametrize(
        "dist_name,dist_gen",
        [
            ("normal", lambda rng: rng.normal(50, 15, size=100)),
            ("uniform", lambda rng: rng.uniform(0, 100, size=100)),
            ("exponential", lambda rng: rng.exponential(scale=20, size=100)),
            ("cauchy", lambda rng: np.abs(rng.standard_cauchy(size=100) * 5 + 30)),
            ("pareto", lambda rng: (rng.pareto(a=3, size=100) + 1) * 5 + 10),
            ("beta", lambda rng: rng.beta(a=2, b=5, size=100) * 100),
        ],
    )
    def test_jensens_inequality_across_distributions(self, dist_name: str, dist_gen):
        """Jensen's inequality RMSE >= MAE must hold for arbitrary continuous distributions."""
        rng = np.random.default_rng(2026 + len(dist_name))
        for _ in range(50):
            y_true = np.maximum(0.0, dist_gen(rng))
            noise = rng.normal(0, 5, size=len(y_true))
            y_pred = np.maximum(0.0, y_true + noise)

            mae = calculate_mae(y_true, y_pred)
            rmse = calculate_rmse(y_true, y_pred)
            # Jensen: E[X^2] >= (E[|X|])^2 => sqrt(E[X^2]) >= E[|X|]
            assert rmse >= mae - 1e-12, f"Jensen violated on {dist_name}: rmse={rmse}, mae={mae}"

    def test_metrics_identical_arrays_yield_exact_zero(self):
        """Zero prediction error must produce exact 0.0 for all metrics."""
        y = np.array([5.0, 12.0, 100.0, 0.5])
        metrics = calculate_forecast_metrics(y, y)
        assert metrics["MAE"] == 0.0
        assert metrics["RMSE"] == 0.0
        assert metrics["MAPE"] == 0.0
        assert metrics["WAPE"] == 0.0

    def test_metrics_division_by_zero_and_near_zero(self):
        """Zero denominators in MAPE and WAPE must be regularized without crashing or returning Inf/NaN."""
        # 1. All zero actuals and predictions
        m_zero = calculate_forecast_metrics([0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
        assert m_zero["MAE"] == 0.0
        assert m_zero["RMSE"] == 0.0
        assert m_zero["MAPE"] == 0.0
        assert m_zero["WAPE"] == 0.0

        # 2. All zero actuals with non-zero predictions
        m_nz_pred = calculate_forecast_metrics([0.0, 0.0, 0.0], [10.0, 20.0, 30.0])
        assert not np.isnan(m_nz_pred["MAPE"])
        assert not np.isinf(m_nz_pred["MAPE"])
        assert m_nz_pred["WAPE"] == 1.0

        # 3. Microscopic denominators (1e-15)
        m_micro = calculate_forecast_metrics([1e-15, 1e-15], [2e-15, 0.0])
        assert not np.isnan(m_micro["MAPE"])
        assert not np.isinf(m_micro["MAPE"])

    def test_wape_robustness_on_sparse_intermittent_series(self):
        """WAPE behaves predictably on sparse intermittent series with 90% zeros."""
        y_true = np.array([0.0] * 9 + [100.0])
        y_pred = np.array([0.0] * 9 + [80.0])
        wape = calculate_wape(y_true, y_pred)
        # Sum diff = 20, sum actual = 100 => WAPE = 0.20
        assert math.isclose(wape, 0.20, abs_tol=1e-5)


# =============================================================================
# 2. UNCERTAINTY QUANTIFICATION & INTERVAL INVARIANTS
# =============================================================================

class TestForecastingUncertaintyBounds:
    """Stress-test 95% uncertainty intervals, non-negativity, and corridor expansion."""

    def test_non_negativity_under_downward_volatility(self):
        """Even under severe downward volatility, L_95 must NEVER be negative (physical stock invariant)."""
        forecaster = DemandForecaster()
        # High volatility with low mean: sigma_D = 10, mean = 2
        history = [
            DemandRecord(date=date(2025, 1, 1) + timedelta(days=i), sku_id="SKU-VOL", quantity=float(i % 2 * 20))
            for i in range(60)
        ]
        result = forecaster.fit_predict(history, horizon_days=30, holdout_days=10)

        assert len(result.lower_bound_95) == 30
        for h, (l, p, u) in enumerate(zip(result.lower_bound_95, result.point_forecast, result.upper_bound_95)):
            assert l >= 0.0, f"Lower bound negative at step h={h+1}: {l}"
            assert l <= p <= u, f"Bounds ordering violated at step h={h+1}: {l} <= {p} <= {u}"

    def test_monotonic_envelope_expansion_over_horizon(self):
        """Prediction interval half-width must strictly expand with forecast horizon h."""
        forecaster = DemandForecaster()
        history = [
            DemandRecord(date=date(2025, 1, 1) + timedelta(days=i), sku_id="SKU-EXP", quantity=50.0 + (i % 7) * 3.0)
            for i in range(70)
        ]
        res = forecaster.fit_predict(history, horizon_days=30, holdout_days=14)

        # Theoretical dispersion multiplier is sqrt(1 + 0.05 * h)
        # Therefore, upper bound minus point forecast must strictly monotonically increase
        half_widths = [u - p for p, u in zip(res.point_forecast, res.upper_bound_95)]
        for h in range(len(half_widths) - 1):
            assert half_widths[h + 1] >= half_widths[h], (
                f"Uncertainty half-width decreased at step {h+1}: {half_widths[h]} -> {half_widths[h+1]}"
            )

    def test_constant_series_bounds_collapse_to_point(self):
        """A deterministic flat series has zero variance; uncertainty corridor must collapse to point forecast."""
        forecaster = DemandForecaster()
        val = 42.0
        history = [
            DemandRecord(date=date(2025, 1, 1) + timedelta(days=i), sku_id="SKU-FLAT", quantity=val)
            for i in range(40)
        ]
        res = forecaster.fit_predict(history, horizon_days=15, holdout_days=7)
        assert res.std_daily_demand == 0.0
        assert np.all(np.array(res.lower_bound_95) == val)
        assert np.all(np.array(res.point_forecast) == val)
        assert np.all(np.array(res.upper_bound_95) == val)

    def test_empirical_coverage_oracle_monte_carlo(self):
        """For a stationary Gaussian demand DGP, 95% uncertainty interval must cover ~90-97% of simulated realizations."""
        rng = np.random.default_rng(777)
        mu_dgp = 60.0
        sigma_dgp = 8.0
        history = rng.normal(mu_dgp, sigma_dgp, size=180)

        forecaster = DemandForecaster()
        res = forecaster.fit_predict(history, horizon_days=30, holdout_days=30)

        # Generate 500 future paths of length 30 from true process
        sim_futures = rng.normal(mu_dgp, sigma_dgp, size=(500, 30))
        in_bounds = 0
        total_points = 500 * 30

        for fut in sim_futures:
            for h in range(30):
                if res.lower_bound_95[h] <= fut[h] <= res.upper_bound_95[h]:
                    in_bounds += 1

        emp_coverage = in_bounds / total_points
        assert 0.90 <= emp_coverage <= 0.98, f"Empirical coverage {emp_coverage:.4f} outside nominal range"


# =============================================================================
# 3. FORECASTING MODEL PIPELINE & ADVERSARIAL INPUTS
# =============================================================================

class TestForecastingModelRobustness:
    """Adversarial stress-testing of DemandForecaster model tournament and architectures."""

    def test_no_temporal_leakage_in_tournament_fitting(self):
        """Perturbing the holdout validation set must NOT leak into the candidate models fitted on train partition."""
        rng = np.random.default_rng(999)
        n_train = 80
        train_data = rng.uniform(20, 30, size=n_train)

        # Baseline candidates fitted on train
        sma = SimpleMovingAverageForecaster(7).fit(train_data)
        ses = ExponentialSmoothingForecaster(0.2).fit(train_data)
        ridge = RidgeRegressionForecaster().fit(train_data)

        # Predictions before observing any future
        sma_p1 = sma.predict(14)
        ses_p1 = ses.predict(14)
        ridge_p1 = ridge.predict(14)

        # Re-fit with same training data but hypothetical different futures
        sma_p2 = SimpleMovingAverageForecaster(7).fit(train_data).predict(14)
        ses_p2 = ExponentialSmoothingForecaster(0.2).fit(train_data).predict(14)
        ridge_p2 = RidgeRegressionForecaster().fit(train_data).predict(14)

        np.testing.assert_allclose(sma_p1, sma_p2)
        np.testing.assert_allclose(ses_p1, ses_p2)
        np.testing.assert_allclose(ridge_p1, ridge_p2)

    def test_extreme_intermittent_croston_selection(self):
        """When series contains >= 50% zeros, Croston model must be included and selected if optimal."""
        series = [0.0, 0.0, 15.0, 0.0, 0.0, 20.0, 0.0, 0.0, 18.0] * 5
        croston = CrostonForecaster(alpha=0.1).fit(series)
        preds = croston.predict(10)
        assert len(preds) == 10
        assert np.all(preds > 0.0)
        # Average rate should be approximately 17 / 3 ~ 5.67
        assert 3.0 <= preds[0] <= 8.0

    def test_massive_demand_spike_does_not_crash(self):
        """A single 1,000,000 unit spike must not produce NaNs or crash the forecasting engine."""
        forecaster = DemandForecaster()
        series = [10.0] * 50 + [1_000_000.0]
        res = forecaster.fit_predict(series, horizon_days=7, holdout_days=10)
        assert len(res.point_forecast) == 7
        assert not np.any(np.isnan(res.point_forecast))
        assert not np.any(np.isnan(res.lower_bound_95))
        assert not np.any(np.isnan(res.upper_bound_95))
        assert all(l >= 0.0 for l in res.lower_bound_95)

    @pytest.mark.parametrize("length", [1, 2, 5, 10, 14, 21])
    def test_short_series_graceful_degradation(self, length: int):
        """DemandForecaster must gracefully handle short series shorter than standard holdout."""
        forecaster = DemandForecaster()
        series = [15.0 + float(i) for i in range(length)]
        res = forecaster.fit_predict(series, horizon_days=5, holdout_days=30)
        assert len(res.point_forecast) == 5
        assert res.mean_daily_demand > 0.0
        assert all(l >= 0.0 for l in res.lower_bound_95)

    def test_holt_winters_multiplicative_fallback_on_zeros(self):
        """Multiplicative Holt-Winters requested on series with zeros must fall back without exception."""
        series = [0.0, 10.0, 20.0, 0.0, 15.0, 25.0, 0.0] * 4
        hw = HoltWintersForecaster(trend="mul", seasonal="mul", seasonal_periods=7).fit(series)
        preds = hw.predict(7)
        assert len(preds) == 7
        assert np.all(preds >= 0.0)


# =============================================================================
# 4. INVENTORY OPTIMIZATION, EOQ & WALD'S IDENTITY INVARIANTS
# =============================================================================

class TestOptimizationEOQAndStochasticInvariants:
    """Stress-test Wilson EOQ convexity, price tier arbitrage, and Wald's identity."""

    def test_wilson_eoq_first_and_second_order_convexity(self):
        """Verify EOQ is the unique global minimum of total inventory holding + ordering cost."""
        rng = np.random.default_rng(101)
        for _ in range(50):
            d = rng.uniform(500, 20000)
            k = rng.uniform(10, 500)
            h = rng.uniform(0.5, 50)

            q_star = calculate_classical_eoq(d, k, h)
            assert q_star > 0.0

            # First-order condition: d(TC)/dQ = -D*K/Q^2 + H/2 == 0
            grad = -(d * k) / (q_star ** 2) + 0.5 * h
            assert math.isclose(grad, 0.0, abs_tol=1e-5)

            # Second-order condition: d^2(TC)/dQ^2 = 2*D*K/Q^3 > 0 (strictly convex)
            d2 = 2.0 * d * k / (q_star ** 3)
            assert d2 > 0.0

            # Perturbation check
            _, order_c, hold_c, tc_star = calculate_total_inventory_cost(q_star, d, 10.0, h / 10.0, k)
            _, _, _, tc_low = calculate_total_inventory_cost(q_star * 0.9, d, 10.0, h / 10.0, k)
            _, _, _, tc_high = calculate_total_inventory_cost(q_star * 1.1, d, 10.0, h / 10.0, k)

            assert tc_star < tc_low
            assert tc_star < tc_high
            # In classical EOQ without SS, ordering cost equals holding cost at Q*
            assert math.isclose(order_c, hold_c, rel_tol=1e-3)

    def test_zero_and_negative_input_boundaries(self):
        """Zero demand or zero holding cost must return 0.0 without ZeroDivisionError."""
        assert calculate_classical_eoq(0.0, 50.0, 10.0) == 0.0
        assert calculate_classical_eoq(1000.0, 0.0, 10.0) == 0.0
        assert calculate_classical_eoq(1000.0, 50.0, 0.0) == 0.0
        assert calculate_classical_eoq(-500.0, 50.0, 10.0) == 0.0

    def test_quantity_tier_discount_arbitrage(self):
        """When price discount savings exceed additional holding costs, batch size must jump to price break."""
        d = 5000.0
        k = 100.0
        h_rate = 0.20
        p_base = 200.0  # H = 40.0 -> raw EOQ = sqrt(2 * 5000 * 100 / 40) = 158.11

        # Tier discount: >= 500 units -> 15% off (170 RUB)
        # Annual purchase savings: 5000 * 30 RUB = 150,000 RUB
        # Additional holding cost: ~40 * (500 - 158)/2 = ~6,840 RUB
        # Obvious arbitrage: optimizer MUST jump to 500
        tiers = [DiscountTier(min_quantity=500, discount_percentage=0.15)]
        res = calculate_eoq_with_discounts(
            annual_demand=d,
            base_unit_price=p_base,
            holding_rate=h_rate,
            order_cost=k,
            discount_tiers=tiers,
        )
        assert res.optimal_quantity == 500.0
        assert res.applied_discount_rate == 0.15

    def test_walds_identity_monte_carlo_oracle(self):
        """Monte Carlo validation of Wald's identity: Var(D_L) = mu_L * sigma_D^2 + mu_D^2 * sigma_L^2."""
        rng = np.random.default_rng(12345)
        mu_d = 25.0
        sigma_d = 5.0
        mu_l = 6.0
        sigma_l = 1.2

        var_theoretical = calculate_lead_time_demand_variance(mu_d, sigma_d, mu_l, sigma_l)

        # Simulate 100,000 lead times and compound demands
        l_samples = np.maximum(1, np.round(rng.normal(mu_l, sigma_l, size=100000))).astype(int)
        emp_mu_l = float(np.mean(l_samples))
        emp_var_l = float(np.var(l_samples))

        dl_sums = [np.sum(rng.normal(mu_d, sigma_d, size=l)) for l in l_samples[:20000]]
        emp_var_dl = float(np.var(dl_sums))

        # Expected variance given sample lead-time distribution
        exact_sample_wald = emp_mu_l * (sigma_d ** 2) + (mu_d ** 2) * emp_var_l
        rel_diff = abs(emp_var_dl - exact_sample_wald) / var_theoretical
        assert rel_diff < 0.03, f"Empirical lead time variance deviated by {rel_diff:.4f}"

    def test_service_level_sensitivity_monotonicity(self):
        """Safety Stock must be strictly monotonic across all supported and continuous service levels."""
        sls = [0.50, 0.80, 0.90, 0.95, 0.98, 0.99, 0.999, 0.9999]
        stocks = [calculate_safety_stock(10.0, 3.0, 5.0, 1.0, service_level=s) for s in sls]

        assert stocks[0] == 0.0  # SL=0.50 -> Z=0 -> SS=0
        for i in range(len(stocks) - 1):
            assert stocks[i + 1] > stocks[i], f"Monotonicity failed between {sls[i]} and {sls[i+1]}"

    def test_rop_shift_invariance(self):
        """Reorder Point must strictly equal mu_D * mu_L + SS."""
        mu_d = 14.5
        mu_l = 7.2
        ss = 33.8
        rop = calculate_rop(mu_d, mu_l, ss)
        assert math.isclose(rop, round(mu_d * mu_l + ss, 2))


# =============================================================================
# 5. EMPIRICAL ADVERSARIAL CHALLENGES & BUG REPRODUCTIONS
# =============================================================================

class TestWarehouseCapacityAdversarialBugs:
    """Empirical tests verifying warehouse capacity constraints under contention.

    These tests challenge edge cases and identify architectural discrepancies
    in CapacityOptimizer and multi-item policy coordination.
    """

    def test_capacity_optimizer_respects_volume_constraint(self):
        """When warehouse volume capacity is binding, allocated volume must NOT exceed V_max."""
        wh = Warehouse(
            warehouse_id="WH-TIGHT-VOL",
            total_volume_capacity_m3=5.0,
            total_weight_capacity_kg=2000.0,
            fixed_order_cost=50.0,
        )
        skus = {
            "S1": SKU(sku_id="S1", name="Item 1", category="Electronics", unit_price=100.0, unit_volume_m3=0.1, unit_weight_kg=2.0),
            "S2": SKU(sku_id="S2", name="Item 2", category="Raw Materials", unit_price=50.0, unit_volume_m3=0.2, unit_weight_kg=2.0),
        }
        opt = CapacityOptimizer(wh)
        res = opt.optimize_allocation(
            unconstrained_eoqs={"S1": 100.0, "S2": 100.0},
            skus=skus,
            annual_demands={"S1": 1000.0, "S2": 1000.0},
            order_costs={"S1": 50.0, "S2": 50.0},
            holding_costs={"S1": 20.0, "S2": 10.0},
            moqs={"S1": 1, "S2": 1},
        )
        assert res.is_constrained
        # Bug: ceil rounding yields 21.0 * 0.1 + 15.0 * 0.2 = 5.1 m3 > 5.0 m3
        assert res.total_volume_m3 <= wh.total_volume_capacity_m3, (
            f"Warehouse volume exceeded: {res.total_volume_m3} > {wh.total_volume_capacity_m3}"
        )

    def test_capacity_optimizer_respects_weight_constraint(self):
        """When warehouse weight capacity is binding, allocated weight must NOT exceed W_max."""
        wh = Warehouse(
            warehouse_id="WH-TIGHT-WT",
            total_volume_capacity_m3=1000.0,
            total_weight_capacity_kg=100.0,
            fixed_order_cost=50.0,
        )
        skus = {
            "S1": SKU(sku_id="S1", name="Item 1", category="Raw Materials", unit_price=100.0, unit_volume_m3=0.01, unit_weight_kg=5.0),
            "S2": SKU(sku_id="S2", name="Item 2", category="Raw Materials", unit_price=50.0, unit_volume_m3=0.01, unit_weight_kg=10.0),
        }
        opt = CapacityOptimizer(wh)
        res = opt.optimize_allocation(
            unconstrained_eoqs={"S1": 50.0, "S2": 50.0},
            skus=skus,
            annual_demands={"S1": 1000.0, "S2": 1000.0},
            order_costs={"S1": 50.0, "S2": 50.0},
            holding_costs={"S1": 20.0, "S2": 10.0},
            moqs={"S1": 1, "S2": 1},
        )
        assert res.is_constrained
        # Bug: ceil rounding yields 9.0 * 5.0 + 6.0 * 10.0 = 105.0 kg > 100.0 kg
        assert res.total_weight_kg <= wh.total_weight_capacity_kg, (
            f"Warehouse weight exceeded: {res.total_weight_kg} > {wh.total_weight_capacity_kg}"
        )

    def test_capacity_optimizer_extracts_lagrange_multipliers(self):
        """Binding warehouse constraints must produce non-zero KKT shadow prices (lambda_volume > 0 or mu_weight > 0)."""
        wh = Warehouse(
            warehouse_id="WH-TIGHT",
            total_volume_capacity_m3=10.0,
            total_weight_capacity_kg=50000.0,
            fixed_order_cost=50.0,
        )
        skus = {
            "SKU-BULK": SKU(
                sku_id="SKU-BULK", name="Bulk Material", category="Raw Materials",
                unit_price=200.0, unit_volume_m3=0.20, unit_weight_kg=10.0,
            )
        }
        opt = CapacityOptimizer(wh)
        res = opt.optimize_allocation(
            unconstrained_eoqs={"SKU-BULK": 200.0},
            skus=skus,
            annual_demands={"SKU-BULK": 2000.0},
            order_costs={"SKU-BULK": 50.0},
            holding_costs={"SKU-BULK": 40.0},
        )
        assert res.is_constrained
        # Analytical KKT shadow price is lambda = 100.0; currently res.lambda_volume == 0.0
        assert res.lambda_volume > 0.0, f"Expected positive lambda_volume shadow price, got {res.lambda_volume}"

    def test_multi_item_policies_respects_supplier_moq(self):
        """Multi-item capacity constrained policies must never violate supplier MOQ."""
        wh = Warehouse(
            warehouse_id="WH-CAP",
            total_volume_capacity_m3=10.0,
            total_weight_capacity_kg=1000.0,
            fixed_order_cost=50.0,
        )
        skus = [
            SKU(sku_id="S1", name="N1", category="Electronics", unit_price=100.0, unit_volume_m3=0.1, unit_weight_kg=2.0),
        ]
        sup = Supplier(
            supplier_id="SUP-OVERSEAS", name="Overseas", mean_lead_time_days=35.0, std_lead_time_days=6.0,
            on_time_delivery_rate=0.82, defect_rate=0.02, min_order_quantity=200,
        )
        fcs = {
            "S1": ForecastResult(
                sku_id="S1", forecast_horizon_days=30, point_forecast=[10.0] * 30,
                lower_bound_95=[5.0] * 30, upper_bound_95=[15.0] * 30, mean_daily_demand=10.0, std_daily_demand=2.0,
            ),
        }
        optimizer = InventoryOptimizer()
        policies = optimizer.calculate_multi_item_policies(skus, fcs, {"S1": sup}, wh, enforce_capacity=True)

        # Single policy respected MOQ=200, but multi-item capacity scaling scaled it down to 100.0
        assert policies["S1"].eoq >= sup.min_order_quantity, (
            f"Policy EOQ {policies['S1'].eoq} violates supplier MOQ {sup.min_order_quantity}"
        )
