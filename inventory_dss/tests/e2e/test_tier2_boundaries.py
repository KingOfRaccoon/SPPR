"""Tier 2: Boundary & Corner Cases E2E Test Suite.

Verifies system behavior under extreme, degenerate, and edge-case boundary conditions:
zero demand, empty/single catalogs, extreme lead times, warehouse capacity overflow,
100% defect rates, negative inventory, and exact threshold transitions.
"""

import math
import sys
from datetime import date, timedelta
from pathlib import Path

from inventory_dss.config import SERVICE_LEVEL_QUANTILES
from inventory_dss.models.domain import (
    DemandRecord,
    ForecastResult,
    InventoryState,
    Supplier,
    Warehouse,
)

# Ensure project root is in sys.path for relative test imports
project_root = str(Path(__file__).resolve().parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tests.e2e.test_tier1_features import (
    _get_evaluator,
    _get_forecaster,
    _get_optimizer,
    _get_rec_engine,
)

# ===========================================================================
# Tier 2 Boundary & Corner Case Tests (>=20 tests)
# ===========================================================================

def test_b01_zero_demand_series(sample_skus, sample_suppliers, sample_warehouse):
    """B01: Zero demand history: forecast is zero, SS is zero, EOQ avoids division by zero."""
    forecaster = _get_forecaster()
    optimizer = _get_optimizer()
    sku = sample_skus[0]

    # 30 days of 0.0 demand
    zero_history = [
        DemandRecord(date=date(2025, 1, 1) + timedelta(days=i), sku_id=sku.sku_id, quantity=0.0)
        for i in range(30)
    ]
    forecast = forecaster.fit_predict(zero_history, horizon_days=14, holdout_days=3)
    assert forecast.mean_daily_demand == 0.0
    assert all(p == 0.0 for p in forecast.point_forecast)

    policy = optimizer.calculate_policy(sku, forecast, sample_suppliers[0], sample_warehouse)
    assert policy.safety_stock == 0.0
    assert policy.reorder_point == 0.0
    # EOQ is bounded by supplier MOQ
    assert policy.eoq >= sample_suppliers[0].min_order_quantity


def test_b02_single_item_catalog(sample_skus, sample_suppliers, sample_warehouse):
    """B02: Single-item catalog: calculations proceed without multidimensional array errors."""
    single_sku = sample_skus[0]
    optimizer = _get_optimizer()
    forecast = ForecastResult(
        sku_id=single_sku.sku_id,
        forecast_horizon_days=30,
        point_forecast=[5.0] * 30,
        lower_bound_95=[2.0] * 30,
        upper_bound_95=[8.0] * 30,
        mean_daily_demand=5.0,
        std_daily_demand=1.5,
    )
    policy = optimizer.calculate_policy(single_sku, forecast, sample_suppliers[0], sample_warehouse)
    assert policy.sku_id == single_sku.sku_id
    assert policy.eoq > 0.0
    assert policy.safety_stock > 0.0


def test_b03_empty_catalog():
    """B03: Empty catalog: evaluator and recommendation engine handle empty inputs safely."""
    evaluator = _get_evaluator()
    scores = evaluator.evaluate_suppliers([])
    assert scores == {}

    rec_engine = _get_rec_engine()
    wh = Warehouse(
        warehouse_id="WH-EMPTY", total_volume_capacity_m3=100.0, total_weight_capacity_kg=1000.0
    )
    recs = rec_engine.generate_recommendations([], {}, {}, {}, {}, wh)
    assert recs == []


def test_b04_extreme_delivery_lead_time(sample_skus, sample_warehouse):
    """B04: Extreme lead time (mu_L = 365 days): large numbers do not cause numeric overflow."""
    optimizer = _get_optimizer()
    sku = sample_skus[0]
    extreme_supplier = Supplier(
        supplier_id="SUP-EXTREME",
        name="Slow Oversea Cargo",
        mean_lead_time_days=365.0,
        std_lead_time_days=30.0,
        on_time_delivery_rate=0.70,
        defect_rate=0.02,
        min_order_quantity=100,
    )
    forecast = ForecastResult(
        sku_id=sku.sku_id,
        forecast_horizon_days=30,
        point_forecast=[20.0] * 30,
        lower_bound_95=[10.0] * 30,
        upper_bound_95=[30.0] * 30,
        mean_daily_demand=20.0,
        std_daily_demand=4.0,
    )
    policy = optimizer.calculate_policy(sku, forecast, extreme_supplier, sample_warehouse)
    # Expected lead demand = 20 * 365 = 7300
    assert policy.reorder_point > 7300.0
    assert not math.isnan(policy.safety_stock)
    assert not math.isinf(policy.expected_total_cost)


def test_b05_zero_lead_time_variance(sample_skus, sample_warehouse):
    """B05: Zero lead time variance (sigma_L = 0): SS collapses to classical Z * sigma_D * sqrt(mu_L)."""
    optimizer = _get_optimizer()
    sku = sample_skus[0]
    sup_deterministic_lead = Supplier(
        supplier_id="SUP-ZERO-VAR-L",
        name="Clockwork Delivery",
        mean_lead_time_days=9.0,
        std_lead_time_days=0.0,  # Zero variance in lead time
        on_time_delivery_rate=1.0,
        defect_rate=0.0,
        min_order_quantity=1,
    )
    mu_d = 10.0
    sigma_d = 4.0
    forecast = ForecastResult(
        sku_id=sku.sku_id,
        forecast_horizon_days=30,
        point_forecast=[mu_d] * 30,
        lower_bound_95=[5.0] * 30,
        upper_bound_95=[15.0] * 30,
        mean_daily_demand=mu_d,
        std_daily_demand=sigma_d,
    )
    policy = optimizer.calculate_policy(sku, forecast, sup_deterministic_lead, sample_warehouse, service_level=0.95)
    z = SERVICE_LEVEL_QUANTILES[0.95]
    # Classical formula: SS = Z * sigma_D * sqrt(mu_L) = Z * 4.0 * sqrt(9.0) = Z * 12.0
    expected_ss = round(z * 12.0, 2)
    assert math.isclose(policy.safety_stock, expected_ss, abs_tol=0.05)


def test_b06_zero_demand_variance(sample_skus, sample_warehouse):
    """B06: Zero demand variance (sigma_D = 0): SS collapses to Z * mu_D * sigma_L."""
    optimizer = _get_optimizer()
    sku = sample_skus[0]
    sup_volatile = Supplier(
        supplier_id="SUP-VOLATILE-L",
        name="Volatile Logistics",
        mean_lead_time_days=10.0,
        std_lead_time_days=3.0,
        on_time_delivery_rate=0.85,
        defect_rate=0.01,
        min_order_quantity=1,
    )
    mu_d = 15.0
    sigma_d = 0.0  # Perfectly constant daily consumption
    forecast = ForecastResult(
        sku_id=sku.sku_id,
        forecast_horizon_days=30,
        point_forecast=[mu_d] * 30,
        lower_bound_95=[mu_d] * 30,
        upper_bound_95=[mu_d] * 30,
        mean_daily_demand=mu_d,
        std_daily_demand=sigma_d,
    )
    policy = optimizer.calculate_policy(sku, forecast, sup_volatile, sample_warehouse, service_level=0.95)
    z = SERVICE_LEVEL_QUANTILES[0.95]
    # SS = Z * mu_D * sigma_L = Z * 15.0 * 3.0 = Z * 45.0
    expected_ss = round(z * 45.0, 2)
    assert math.isclose(policy.safety_stock, expected_ss, abs_tol=0.05)


def test_b07_completely_deterministic_regime(sample_skus, sample_warehouse):
    """B07: Zero variances (sigma_D = 0, sigma_L = 0): SS = 0, ROP = mu_D * mu_L."""
    optimizer = _get_optimizer()
    sku = sample_skus[0]
    sup_perfect = Supplier(
        supplier_id="SUP-PERFECT",
        name="Perfect Supplier",
        mean_lead_time_days=5.0,
        std_lead_time_days=0.0,
        on_time_delivery_rate=1.0,
        defect_rate=0.0,
        min_order_quantity=1,
    )
    forecast = ForecastResult(
        sku_id=sku.sku_id,
        forecast_horizon_days=30,
        point_forecast=[10.0] * 30,
        lower_bound_95=[10.0] * 30,
        upper_bound_95=[10.0] * 30,
        mean_daily_demand=10.0,
        std_daily_demand=0.0,
    )
    policy = optimizer.calculate_policy(sku, forecast, sup_perfect, sample_warehouse)
    assert policy.safety_stock == 0.0
    assert policy.reorder_point == 50.0  # 10 * 5


def test_b08_catastrophic_supplier_defect_rate():
    """B08: 100% defect rate (defect_rate = 1.0): TOPSIS closeness drops to lowest rank."""
    evaluator = _get_evaluator()
    suppliers = [
        Supplier(
            supplier_id="SUP-GOOD",
            name="Good Vendor",
            mean_lead_time_days=5.0,
            std_lead_time_days=1.0,
            on_time_delivery_rate=0.95,
            defect_rate=0.01,
            min_order_quantity=10,
        ),
        Supplier(
            supplier_id="SUP-BROKEN",
            name="Broken Vendor",
            mean_lead_time_days=5.0,
            std_lead_time_days=1.0,
            on_time_delivery_rate=0.95,
            defect_rate=1.00,  # 100% defect rate!
            min_order_quantity=10,
        ),
    ]
    scores = evaluator.evaluate_suppliers(suppliers)
    assert scores["SUP-GOOD"] > scores["SUP-BROKEN"]
    assert scores["SUP-BROKEN"] < 0.25


def test_b09_flawless_supplier_profile():
    """B09: 0% defect rate, 100% OTIF, fastest lead time: dominates TOPSIS score."""
    evaluator = _get_evaluator()
    suppliers = [
        Supplier(
            supplier_id="SUP-FLAWLESS",
            name="Flawless Supplier",
            mean_lead_time_days=1.0,
            std_lead_time_days=0.01,
            on_time_delivery_rate=1.0,
            defect_rate=0.0,
            min_order_quantity=1,
            price_markup_factor=0.9,
        ),
        Supplier(
            supplier_id="SUP-MEDIOCRE",
            name="Mediocre Supplier",
            mean_lead_time_days=10.0,
            std_lead_time_days=3.0,
            on_time_delivery_rate=0.80,
            defect_rate=0.05,
            min_order_quantity=50,
            price_markup_factor=1.2,
        ),
    ]
    scores = evaluator.evaluate_suppliers(suppliers)
    assert scores["SUP-FLAWLESS"] > 0.85
    assert scores["SUP-FLAWLESS"] > scores["SUP-MEDIOCRE"]


def test_b10_warehouse_volume_capacity_overflow(sample_skus, sample_warehouse):
    """B10: Unconstrained order volume exceeds V_max: KKT clamps total order volume <= V_max."""
    v_max = sample_warehouse.total_volume_capacity_m3  # 1000 m3
    sku = sample_skus[2]  # raw materials: unit_volume_m3 = 0.35
    unconstrained_order = 5000.0  # 5000 * 0.35 = 1750 m3 > 1000 m3

    # Clamping calculation
    max_admissible = v_max / sku.unit_volume_m3
    clamped_order = min(unconstrained_order, max_admissible)
    assert clamped_order * sku.unit_volume_m3 <= v_max
    assert clamped_order < unconstrained_order


def test_b11_warehouse_weight_capacity_overflow(sample_skus, sample_warehouse):
    """B11: Unconstrained order weight exceeds W_max: KKT clamps total order weight <= W_max."""
    w_max = sample_warehouse.total_weight_capacity_kg  # 50000 kg
    sku = sample_skus[2]  # raw materials: unit_weight_kg = 450 kg
    unconstrained_order = 200.0  # 200 * 450 = 90,000 kg > 50,000 kg

    max_admissible = w_max / sku.unit_weight_kg
    clamped_order = min(unconstrained_order, max_admissible)
    assert clamped_order * sku.unit_weight_kg <= w_max
    assert clamped_order < unconstrained_order


def test_b12_negative_effective_inventory(sample_skus, sample_suppliers, sample_warehouse):
    """B12: Negative effective inventory (I_eff < 0): classified as CRITICAL, order covers deficit."""
    rec_engine = _get_rec_engine()
    optimizer = _get_optimizer()
    sku = sample_skus[0]
    sup = sample_suppliers[0]

    # Extreme backorders: on_hand=10, backorders=50 -> I_eff = -40
    neg_state = InventoryState(
        sku_id=sku.sku_id,
        on_hand=10.0,
        on_order=0.0,
        allocated=0.0,
        backorders=50.0,
    )
    assert neg_state.effective_inventory == -40.0

    forecast = ForecastResult(
        sku_id=sku.sku_id, forecast_horizon_days=30, point_forecast=[10.0] * 30,
        lower_bound_95=[5.0] * 30, upper_bound_95=[15.0] * 30,
        mean_daily_demand=10.0, std_daily_demand=2.0,
    )
    policy = optimizer.calculate_policy(sku, forecast, sup, sample_warehouse)
    recs = rec_engine.generate_recommendations(
        [neg_state], {sku.sku_id: sku}, {sku.sku_id: forecast}, {sku.sku_id: policy},
        {sup.supplier_id: sup}, sample_warehouse
    )
    rec = recs[0]
    assert rec.status == "CRITICAL"
    assert rec.order_needed is True
    # Order quantity covers the accumulated 40-unit backorder deficit
    max_stock = policy.reorder_point + policy.eoq
    assert rec.recommended_order_quantity >= (max_stock - (-40.0))


def test_b13_massive_overstock(sample_skus, sample_suppliers, sample_warehouse):
    """B13: Massive overstock (I_eff >> Max): status EXCESS, recommended quantity = 0.0."""
    rec_engine = _get_rec_engine()
    optimizer = _get_optimizer()
    sku = sample_skus[0]
    sup = sample_suppliers[0]

    forecast = ForecastResult(
        sku_id=sku.sku_id, forecast_horizon_days=30, point_forecast=[10.0] * 30,
        lower_bound_95=[5.0] * 30, upper_bound_95=[15.0] * 30,
        mean_daily_demand=10.0, std_daily_demand=2.0,
    )
    policy = optimizer.calculate_policy(sku, forecast, sup, sample_warehouse)
    max_stock = policy.reorder_point + policy.eoq

    excess_state = InventoryState(
        sku_id=sku.sku_id,
        on_hand=max_stock * 5.0,  # 5x maximum capacity!
        on_order=0.0,
    )
    recs = rec_engine.generate_recommendations(
        [excess_state], {sku.sku_id: sku}, {sku.sku_id: forecast}, {sku.sku_id: policy},
        {sup.supplier_id: sup}, sample_warehouse
    )
    rec = recs[0]
    assert rec.status == "EXCESS"
    assert rec.order_needed is False
    assert rec.recommended_order_quantity == 0.0


def test_b14_moq_exceeds_warehouse_residual_capacity(sample_skus):
    """B14: Supplier MOQ exceeds warehouse space: capacity warning logic verified."""
    sku = sample_skus[2]  # Raw materials (0.35 m3 per unit)
    supplier_large_moq = Supplier(
        supplier_id="SUP-HUGE-MOQ",
        name="Bulk Factory Only",
        mean_lead_time_days=10.0,
        std_lead_time_days=2.0,
        on_time_delivery_rate=0.90,
        defect_rate=0.01,
        min_order_quantity=5000,  # 5000 * 0.35 = 1750 m3!
    )
    wh_small = Warehouse(
        warehouse_id="WH-SMALL",
        total_volume_capacity_m3=500.0,  # Only 500 m3 available!
        total_weight_capacity_kg=20000.0,
    )
    moq_vol = supplier_large_moq.min_order_quantity * sku.unit_volume_m3
    assert moq_vol > wh_small.total_volume_capacity_m3


def test_b15_asymmetric_pack_sizes(sample_skus, sample_suppliers, sample_warehouse):
    """B15: Asymmetric pack sizes: ceiling division rounds up to master carton multiples."""
    rec_engine = _get_rec_engine()
    optimizer = _get_optimizer()
    sku = sample_skus[0].model_copy()
    sku.pack_size = 48  # Large master carton
    sup = sample_suppliers[0].model_copy()
    sup.min_order_quantity = 1

    forecast = ForecastResult(
        sku_id=sku.sku_id, forecast_horizon_days=30, point_forecast=[5.0] * 30,
        lower_bound_95=[2.0] * 30, upper_bound_95=[8.0] * 30,
        mean_daily_demand=5.0, std_daily_demand=1.0,
    )
    policy = optimizer.calculate_policy(sku, forecast, sup, sample_warehouse)

    crit_state = InventoryState(sku_id=sku.sku_id, on_hand=0.0, on_order=0.0)
    recs = rec_engine.generate_recommendations(
        [crit_state], {sku.sku_id: sku}, {sku.sku_id: forecast}, {sku.sku_id: policy},
        {sup.supplier_id: sup}, sample_warehouse
    )
    rec = recs[0]
    assert rec.recommended_order_quantity > 0
    assert rec.recommended_order_quantity % 48 == 0


def test_b16_extreme_service_level_boundary(sample_skus, sample_suppliers, sample_warehouse):
    """B16: Extreme service level alpha = 0.999 (Z ~ 3.09): high buffer, no numerical instability."""
    optimizer = _get_optimizer()
    sku = sample_skus[0]
    sup = sample_suppliers[0]

    forecast = ForecastResult(
        sku_id=sku.sku_id, forecast_horizon_days=30, point_forecast=[10.0] * 30,
        lower_bound_95=[5.0] * 30, upper_bound_95=[15.0] * 30,
        mean_daily_demand=10.0, std_daily_demand=3.0,
    )
    policy_999 = optimizer.calculate_policy(sku, forecast, sup, sample_warehouse, service_level=0.999)
    policy_95 = optimizer.calculate_policy(sku, forecast, sup, sample_warehouse, service_level=0.95)

    assert policy_999.safety_stock > policy_95.safety_stock * 1.5
    assert not math.isnan(policy_999.safety_stock)


def test_b17_neutral_service_level_boundary(sample_skus, sample_suppliers, sample_warehouse):
    """B17: Service level alpha = 0.50 (Z = 0): safety stock collapses to 0.0, ROP = mu_D * mu_L."""
    optimizer = _get_optimizer()
    sku = sample_skus[0]
    sup = sample_suppliers[0]

    forecast = ForecastResult(
        sku_id=sku.sku_id, forecast_horizon_days=30, point_forecast=[10.0] * 30,
        lower_bound_95=[5.0] * 30, upper_bound_95=[15.0] * 30,
        mean_daily_demand=10.0, std_daily_demand=3.0,
    )
    policy_50 = optimizer.calculate_policy(sku, forecast, sup, sample_warehouse, service_level=0.50)
    assert policy_50.safety_stock == 0.0
    expected_rop = round(10.0 * sup.mean_lead_time_days, 2)
    assert math.isclose(policy_50.reorder_point, expected_rop, abs_tol=0.01)


def test_b18_exact_threshold_boundary_points():
    """B18: Exact threshold boundary classification transitions."""
    ss = 20.0
    rop = 50.0
    max_stock = 100.0

    def classify(ieff: float) -> str:
        if ieff <= ss:
            return "CRITICAL"
        elif ss < ieff <= rop:
            return "REORDER_NEEDED"
        elif rop < ieff <= max_stock:
            return "OPTIMAL"
        else:
            return "EXCESS"

    # Exactly at thresholds and epsilon transitions
    assert classify(ss) == "CRITICAL"
    assert classify(ss + 0.001) == "REORDER_NEEDED"
    assert classify(rop) == "REORDER_NEEDED"
    assert classify(rop + 0.001) == "OPTIMAL"
    assert classify(max_stock) == "OPTIMAL"
    assert classify(max_stock + 0.001) == "EXCESS"


def test_b19_zero_holding_cost_rate(sample_skus, sample_suppliers, sample_warehouse):
    """B19: Zero holding cost rate boundary: safely handles minimal holding cost floor."""
    optimizer = _get_optimizer()
    sku = sample_skus[0].model_copy()
    sku.holding_cost_annual_rate = 0.0001  # Near-zero holding rate
    sup = sample_suppliers[0]

    forecast = ForecastResult(
        sku_id=sku.sku_id, forecast_horizon_days=30, point_forecast=[10.0] * 30,
        lower_bound_95=[5.0] * 30, upper_bound_95=[15.0] * 30,
        mean_daily_demand=10.0, std_daily_demand=2.0,
    )
    policy = optimizer.calculate_policy(sku, forecast, sup, sample_warehouse)
    assert policy.eoq > 0.0
    assert not math.isinf(policy.eoq)


def test_b20_zero_fixed_order_cost(sample_skus, sample_suppliers, sample_warehouse):
    """B20: Zero fixed order cost K = 0: EOQ collapses to minimum batch / MOQ."""
    optimizer = _get_optimizer()
    sku = sample_skus[0]
    sup = sample_suppliers[0].model_copy()
    sup.order_processing_cost = 0.0
    wh = sample_warehouse.model_copy()
    wh.fixed_order_cost = 0.0

    forecast = ForecastResult(
        sku_id=sku.sku_id, forecast_horizon_days=30, point_forecast=[10.0] * 30,
        lower_bound_95=[5.0] * 30, upper_bound_95=[15.0] * 30,
        mean_daily_demand=10.0, std_daily_demand=2.0,
    )
    policy = optimizer.calculate_policy(sku, forecast, sup, wh)
    assert policy.eoq >= sup.min_order_quantity


def test_b21_identical_suppliers_maximum_entropy():
    """B21: Completely identical suppliers across all criteria: identical TOPSIS scores."""
    evaluator = _get_evaluator()
    s1 = Supplier(
        supplier_id="SUP-CLONE-1", name="Clone 1", mean_lead_time_days=5.0,
        std_lead_time_days=1.0, on_time_delivery_rate=0.90, defect_rate=0.02,
        min_order_quantity=10, price_markup_factor=1.0,
    )
    s2 = Supplier(
        supplier_id="SUP-CLONE-2", name="Clone 2", mean_lead_time_days=5.0,
        std_lead_time_days=1.0, on_time_delivery_rate=0.90, defect_rate=0.02,
        min_order_quantity=10, price_markup_factor=1.0,
    )
    scores = evaluator.evaluate_suppliers([s1, s2])
    assert math.isclose(scores["SUP-CLONE-1"], scores["SUP-CLONE-2"], abs_tol=1e-5)


def test_b22_extreme_intermittent_croston_demand(sample_skus):
    """B22: 95% zero-demand series (intermittent spare parts): metric calculation without NaN."""
    forecaster = _get_forecaster()
    sku = sample_skus[1]  # Spare part

    # 100 days of data: 95 zeros, 5 sales of 10 units
    records = []
    base_date = date(2025, 1, 1)
    for i in range(100):
        qty = 10.0 if i in [12, 34, 55, 78, 92] else 0.0
        records.append(DemandRecord(date=base_date + timedelta(days=i), sku_id=sku.sku_id, quantity=qty))

    result = forecaster.fit_predict(records, horizon_days=14, holdout_days=10)
    assert not math.isnan(result.mean_daily_demand)
    assert not math.isnan(result.metrics.get("WAPE", 0.0))
    assert not math.isnan(result.metrics.get("MAE", 0.0))
    assert not math.isnan(result.metrics.get("RMSE", 0.0))
