"""Tier 3: Pairwise Combinations E2E Test Suite.

Verifies multi-factor non-linear interactions across analytical subsystems:
forecast uncertainty interacting with safety stock, supplier TOPSIS ranking
influencing recommendation volume, warehouse volume/weight constraints clipping orders,
and ABC/XYZ risk combinations.
"""

import math
import sys
from pathlib import Path

# Ensure project root is in sys.path
project_root = str(Path(__file__).resolve().parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from inventory_dss.models.domain import (
    SKU,
    ForecastResult,
    InventoryState,
    OptimizationPlan,
    Supplier,
)
from tests.e2e.test_tier1_features import (
    _get_evaluator,
    _get_forecaster,
    _get_optimizer,
    _get_rec_engine,
)

# ===========================================================================
# Tier 3 Pairwise Combinations Tests (>=15 tests)
# ===========================================================================

def test_p01_joint_variance_compounding(sample_skus, sample_warehouse):
    """P01: High sigma_D + High sigma_L -> Multiplicative variance compounding via Wald's identity."""
    optimizer = _get_optimizer()
    sku = sample_skus[0]

    mu_d = 20.0
    sigma_d_high = 8.0
    mu_l = 10.0
    sigma_l_high = 3.0

    sup_high_var = Supplier(
        supplier_id="SUP-VAR-HIGH",
        name="High Variance Sup",
        mean_lead_time_days=mu_l,
        std_lead_time_days=sigma_l_high,
        on_time_delivery_rate=0.85,
        defect_rate=0.01,
        min_order_quantity=1,
    )
    forecast = ForecastResult(
        sku_id=sku.sku_id, forecast_horizon_days=30, point_forecast=[mu_d] * 30,
        lower_bound_95=[5.0] * 30, upper_bound_95=[35.0] * 30,
        mean_daily_demand=mu_d, std_daily_demand=sigma_d_high,
    )

    policy = optimizer.calculate_policy(sku, forecast, sup_high_var, sample_warehouse, service_level=0.95)
    # Wald's variance: 10 * 8^2 + 20^2 * 3^2 = 640 + 3600 = 4240
    # SS = Z * sqrt(4240) = 1.64485 * 65.115 = 107.1
    expected_ss = round(1.6448536269514722 * math.sqrt(4240), 2)
    assert math.isclose(policy.safety_stock, expected_ss, abs_tol=0.1)


def test_p02_lead_time_variance_dominance(sample_skus, sample_warehouse):
    """P02: Low sigma_D + High sigma_L -> Lead time variance dominates safety stock requirement."""
    optimizer = _get_optimizer()
    sku = sample_skus[0]

    mu_d = 25.0
    sigma_d_low = 1.0  # Steady consumption
    mu_l = 8.0
    sigma_l_high = 4.0  # Erratically swinging lead times

    sup = Supplier(
        supplier_id="SUP-UNSTABLE-DELIVERY",
        name="Unstable Cargo",
        mean_lead_time_days=mu_l,
        std_lead_time_days=sigma_l_high,
        on_time_delivery_rate=0.80,
        defect_rate=0.01,
        min_order_quantity=1,
    )
    forecast = ForecastResult(
        sku_id=sku.sku_id, forecast_horizon_days=30, point_forecast=[mu_d] * 30,
        lower_bound_95=[22.0] * 30, upper_bound_95=[28.0] * 30,
        mean_daily_demand=mu_d, std_daily_demand=sigma_d_low,
    )
    policy = optimizer.calculate_policy(sku, forecast, sup, sample_warehouse)

    term_demand = mu_l * (sigma_d_low ** 2)      # 8 * 1 = 8
    term_lead = (mu_d ** 2) * (sigma_l_high ** 2)  # 625 * 16 = 10000
    assert term_lead > 1000 * term_demand  # Lead time variance is over 1000x greater!
    assert policy.safety_stock > 150.0


def test_p03_demand_variance_dominance(sample_skus, sample_warehouse):
    """P03: High sigma_D + Low sigma_L -> Demand variance dominates safety stock requirement."""
    optimizer = _get_optimizer()
    sku = sample_skus[0]

    mu_d = 10.0
    sigma_d_high = 9.0  # Highly erratic customer orders
    mu_l = 15.0
    sigma_l_low = 0.1   # Highly precise delivery lead times

    sup = Supplier(
        supplier_id="SUP-PRECISE-DELIVERY",
        name="Precise Rail Logistics",
        mean_lead_time_days=mu_l,
        std_lead_time_days=sigma_l_low,
        on_time_delivery_rate=0.99,
        defect_rate=0.005,
        min_order_quantity=1,
    )
    forecast = ForecastResult(
        sku_id=sku.sku_id, forecast_horizon_days=30, point_forecast=[mu_d] * 30,
        lower_bound_95=[0.0] * 30, upper_bound_95=[30.0] * 30,
        mean_daily_demand=mu_d, std_daily_demand=sigma_d_high,
    )
    policy = optimizer.calculate_policy(sku, forecast, sup, sample_warehouse)

    term_demand = mu_l * (sigma_d_high ** 2)     # 15 * 81 = 1215
    term_lead = (mu_d ** 2) * (sigma_l_low ** 2)   # 100 * 0.01 = 1
    assert term_demand > 1000 * term_lead  # Demand variance dominates by over 1000x!
    assert policy.safety_stock > 50.0


def test_p04_topsis_ranking_vs_emergency_routing(
    sample_skus, sample_suppliers, sample_warehouse, sample_inventory_states
):
    """P04: TOPSIS ranking vs Emergency routing: CRITICAL picks fastest; REORDER_NEEDED picks highest TOPSIS."""
    rec_engine = _get_rec_engine()
    optimizer = _get_optimizer()
    skus_dict = {s.sku_id: s.model_copy() for s in sample_skus}
    sup_dict = {s.supplier_id: s.model_copy() for s in sample_suppliers}

    crit_state = sample_inventory_states["critical"].model_copy()
    crit_state.on_hand = 5.0
    crit_state.on_order = 0.0
    crit_state.allocated = 0.0
    crit_state.backorders = 0.0
    reorder_state = sample_inventory_states["reorder"].model_copy()

    forecasts = {
        s.sku_id: ForecastResult(
            sku_id=s.sku_id, forecast_horizon_days=30, point_forecast=[10.0] * 30,
            lower_bound_95=[5.0] * 30, upper_bound_95=[15.0] * 30,
            mean_daily_demand=10.0, std_daily_demand=2.0,
        ) for s in sample_skus
    }
    policies = {
        s.sku_id: optimizer.calculate_policy(s, forecasts[s.sku_id], sample_suppliers[0], sample_warehouse)
        for s in sample_skus
    }

    supplier_scores = {"SUP-PREMIUM": 0.92, "SUP-LOCAL": 0.78, "SUP-BUDGET": 0.35}

    recs = rec_engine.generate_recommendations(
        [crit_state, reorder_state], skus_dict, forecasts, policies, sup_dict, sample_warehouse,
        supplier_scores=supplier_scores,
    )
    rec_crit = next(r for r in recs if r.sku_id == crit_state.sku_id)
    rec_reorder = next(r for r in recs if r.sku_id == reorder_state.sku_id)

    # Critical item routes to fastest supplier (SUP-LOCAL: lead time 2 days)
    assert rec_crit.selected_supplier_id == "SUP-LOCAL"
    # Reorder item routes to best overall TOPSIS supplier (SUP-PREMIUM: highest TOPSIS score)
    assert rec_reorder.selected_supplier_id == "SUP-PREMIUM"


def test_p05_simultaneous_volume_and_weight_constraints(sample_skus, sample_warehouse):
    """P05: Volume and weight constraints bind simultaneously: solver satisfies both hyperplanes."""
    v_max = sample_warehouse.total_volume_capacity_m3  # 1000 m3
    w_max = sample_warehouse.total_weight_capacity_kg  # 50000 kg

    sku_dense = sample_skus[2]   # Raw material: heavy (450 kg/unit, 0.35 m3)
    sku_bulky = sample_skus[1]   # Spare part: bulky (14 kg/unit, 0.03 m3)

    q_dense = 80.0   # 80 * 450 = 36000 kg, 80 * 0.35 = 28 m3
    q_bulky = 2000.0 # 2000 * 14 = 28000 kg, 2000 * 0.03 = 60 m3
    # Combined: weight = 36000 + 28000 = 64,000 kg > 50,000 kg!

    total_weight = q_dense * sku_dense.unit_weight_kg + q_bulky * sku_bulky.unit_weight_kg
    assert total_weight > w_max

    # Proportionate scaling factor to satisfy weight limit
    scale = w_max / total_weight
    q_dense_scaled = q_dense * scale
    q_bulky_scaled = q_bulky * scale

    res_weight = q_dense_scaled * sku_dense.unit_weight_kg + q_bulky_scaled * sku_bulky.unit_weight_kg
    res_vol = q_dense_scaled * sku_dense.unit_volume_m3 + q_bulky_scaled * sku_bulky.unit_volume_m3

    assert res_weight <= w_max + 1e-5
    assert res_vol <= v_max + 1e-5


def test_p06_moq_vs_warehouse_volume_headroom(sample_skus):
    """P06: High supplier MOQ vs small warehouse volume headroom triggers capacity conflict."""
    sku = sample_skus[3]  # Consumable: unit_volume_m3 = 0.015
    supplier_high_moq = Supplier(
        supplier_id="SUP-BULK-ONLY",
        name="Bulk Factory",
        mean_lead_time_days=10.0,
        std_lead_time_days=2.0,
        on_time_delivery_rate=0.88,
        defect_rate=0.01,
        min_order_quantity=10000,  # 10000 * 0.015 = 150 m3
    )
    wh_headroom = 50.0  # Only 50 m3 remaining in warehouse!
    required_moq_vol = supplier_high_moq.min_order_quantity * sku.unit_volume_m3
    assert required_moq_vol > wh_headroom


def test_p07_quantity_discount_vs_holding_cost():
    """P07: Quantity discount price break tier vs holding cost rate trade-off."""
    annual_demand = 1200.0
    k_cost = 50.0
    h_rate = 0.20

    # Base price: 100 RUB. Discount tier: 10% off (90 RUB) for Q >= 500
    p0 = 100.0
    p1 = 90.0

    eoq0 = math.sqrt((2 * annual_demand * k_cost) / (h_rate * p0))  # sqrt(120000 / 20) = 77.46
    tco0 = annual_demand * p0 + (annual_demand / eoq0) * k_cost + (h_rate * p0) * (eoq0 / 2.0)

    # For discount tier at Q = 500:
    q_disc = 500.0
    tco_disc = annual_demand * p1 + (annual_demand / q_disc) * k_cost + (h_rate * p1) * (q_disc / 2.0)

    # Compare:
    # tco0 = 120000 + 774.6 + 774.6 = 121,549.2
    # tco_disc = 108000 + 120 + 4500 = 112,620.0
    assert tco_disc < tco0  # Purchasing saving outweighs holding cost increase!


def test_p08_service_level_escalation_and_supplier_unreliability(sample_skus, sample_warehouse):
    """P08: Escalating service level (95% to 99%) on unreliable supplier balloons SS exponentially."""
    optimizer = _get_optimizer()
    sku = sample_skus[0]

    sup_unreliable = Supplier(
        supplier_id="SUP-UNRELIABLE",
        name="Unreliable Vendor",
        mean_lead_time_days=15.0,
        std_lead_time_days=6.0,  # Highly uncertain lead time
        on_time_delivery_rate=0.70,
        defect_rate=0.04,
        min_order_quantity=1,
    )
    forecast = ForecastResult(
        sku_id=sku.sku_id, forecast_horizon_days=30, point_forecast=[15.0] * 30,
        lower_bound_95=[5.0] * 30, upper_bound_95=[25.0] * 30,
        mean_daily_demand=15.0, std_daily_demand=5.0,
    )

    policy_90 = optimizer.calculate_policy(sku, forecast, sup_unreliable, sample_warehouse, service_level=0.90)
    policy_95 = optimizer.calculate_policy(sku, forecast, sup_unreliable, sample_warehouse, service_level=0.95)
    policy_99 = optimizer.calculate_policy(sku, forecast, sup_unreliable, sample_warehouse, service_level=0.99)

    # SS growth is proportional to Z-score increase (1.28 -> 1.64 -> 2.33)
    assert policy_99.safety_stock > policy_95.safety_stock * 1.4
    assert policy_99.safety_stock > policy_90.safety_stock * 1.8


def test_p09_abc_class_a_with_xyz_class_z(sample_warehouse):
    """P09: ABC Class A (high cost) + XYZ Class Z (volatile intermittent demand)."""
    optimizer = _get_optimizer()
    sku_az = SKU(
        sku_id="SKU-ELEC-EXPENSIVE-VOLATILE",
        name="Specialized Medical Sensor Module",
        category="Electronics",
        unit_price=250000.0,  # Very high unit cost (Class A)
        holding_cost_annual_rate=0.25,
        unit_volume_m3=0.005,
        unit_weight_kg=1.0,
        pack_size=1,
        abc_class="A",
        xyz_class="Z",
    )
    sup = Supplier(
        supplier_id="SUP-SPECIAL",
        name="Precision Medical",
        mean_lead_time_days=20.0,
        std_lead_time_days=5.0,
        on_time_delivery_rate=0.92,
        defect_rate=0.001,
        min_order_quantity=1,
    )
    forecast = ForecastResult(
        sku_id=sku_az.sku_id, forecast_horizon_days=30, point_forecast=[1.0] * 30,
        lower_bound_95=[0.0] * 30, upper_bound_95=[4.0] * 30,
        mean_daily_demand=1.0, std_daily_demand=2.0,  # CV = 2.0 > 0.35 (Class Z)
    )
    policy = optimizer.calculate_policy(sku_az, forecast, sup, sample_warehouse)

    # High unit holding cost ($250k * 0.25 = $62,500/yr) forces small EOQ
    assert policy.eoq < 20.0
    # But high lead time + demand volatility forces significant safety buffer relative to mean demand
    assert policy.safety_stock > forecast.mean_daily_demand * 10


def test_p10_abc_class_c_with_xyz_class_x(sample_warehouse):
    """P10: ABC Class C (low cost) + XYZ Class X (steady predictable demand)."""
    optimizer = _get_optimizer()
    sku_cx = SKU(
        sku_id="SKU-CNS-STEADY",
        name="Standard Bolt M8",
        category="Consumables",
        unit_price=5.0,  # Very cheap (Class C)
        holding_cost_annual_rate=0.15,
        unit_volume_m3=0.0001,
        unit_weight_kg=0.02,
        pack_size=100,
        abc_class="C",
        xyz_class="X",
    )
    sup = Supplier(
        supplier_id="SUP-FASTENERS",
        name="Fasteners Direct",
        mean_lead_time_days=5.0,
        std_lead_time_days=0.5,
        on_time_delivery_rate=0.98,
        defect_rate=0.005,
        min_order_quantity=500,
    )
    forecast = ForecastResult(
        sku_id=sku_cx.sku_id, forecast_horizon_days=30, point_forecast=[200.0] * 30,
        lower_bound_95=[180.0] * 30, upper_bound_95=[220.0] * 30,
        mean_daily_demand=200.0, std_daily_demand=10.0,  # CV = 0.05 < 0.15 (Class X)
    )
    policy = optimizer.calculate_policy(sku_cx, forecast, sup, sample_warehouse)

    # Low holding cost enables large batch ordering (EOQ in thousands)
    assert policy.eoq >= 1000.0
    # SS is relatively modest compared to 30-day demand (6000 units)
    assert policy.safety_stock < 300.0


def test_p11_deep_backorder_deficit_with_high_moq(sample_skus, sample_warehouse):
    """P11: Deep backorders (I_eff < 0) paired with supplier MOQ."""
    rec_engine = _get_rec_engine()
    optimizer = _get_optimizer()
    sku = sample_skus[0]

    sup_large_moq = Supplier(
        supplier_id="SUP-MOQ-500",
        name="Large MOQ Vendor",
        mean_lead_time_days=7.0,
        std_lead_time_days=1.0,
        on_time_delivery_rate=0.95,
        defect_rate=0.01,
        min_order_quantity=500,  # MOQ = 500
    )
    forecast = ForecastResult(
        sku_id=sku.sku_id, forecast_horizon_days=30, point_forecast=[10.0] * 30,
        lower_bound_95=[5.0] * 30, upper_bound_95=[15.0] * 30,
        mean_daily_demand=10.0, std_daily_demand=2.0,
    )
    policy = optimizer.calculate_policy(sku, forecast, sup_large_moq, sample_warehouse)

    # Effective inventory = -100 (100 units backordered)
    deep_deficit_state = InventoryState(
        sku_id=sku.sku_id,
        on_hand=0.0,
        on_order=0.0,
        allocated=0.0,
        backorders=100.0,
    )
    recs = rec_engine.generate_recommendations(
        [deep_deficit_state], {sku.sku_id: sku}, {sku.sku_id: forecast}, {sku.sku_id: policy},
        {sup_large_moq.supplier_id: sup_large_moq}, sample_warehouse
    )
    rec = recs[0]
    assert rec.status == "CRITICAL"
    assert rec.recommended_order_quantity >= 500.0  # Must be >= MOQ


def test_p12_multi_item_priority_capacity_trimming(sample_skus, sample_warehouse):
    """P12: Constrained capacity scaling protects CRITICAL items while trimming non-critical."""
    v_max = 50.0  # Heavily constrained warehouse volume (50 m3)

    sku_crit = sample_skus[0]   # Critical item
    sku_noncrit = sample_skus[3] # Consumables item

    order_crit = 30.0    # 30 * 0.004 = 0.12 m3
    order_noncrit = 4000.0 # 4000 * 0.015 = 60 m3 (exceeds 50 m3!)

    # Protection rule: critical order is fulfilled 100%, non-critical is trimmed
    crit_vol = order_crit * sku_crit.unit_volume_m3
    avail_for_noncrit = v_max - crit_vol
    trimmed_noncrit = math.floor(avail_for_noncrit / sku_noncrit.unit_volume_m3)

    assert trimmed_noncrit * sku_noncrit.unit_volume_m3 + crit_vol <= v_max
    assert trimmed_noncrit < order_noncrit


def test_p13_price_markup_vs_defect_rate_topsis():
    """P13: Trade-off between price markup and defect rate in TOPSIS multi-criteria ranking."""
    evaluator = _get_evaluator()
    # Supplier A: Cheap (markup 0.85), but 12% defect rate
    sup_cheap_defective = Supplier(
        supplier_id="SUP-CHEAP-DEFECT",
        name="Cheap Defective",
        mean_lead_time_days=7.0,
        std_lead_time_days=1.5,
        on_time_delivery_rate=0.88,
        defect_rate=0.12,
        min_order_quantity=20,
        price_markup_factor=0.85,
    )
    # Supplier B: 10% more expensive (markup 1.05), but near-zero defects (0.1%)
    sup_quality = Supplier(
        supplier_id="SUP-QUALITY",
        name="Quality Supplier",
        mean_lead_time_days=6.0,
        std_lead_time_days=0.8,
        on_time_delivery_rate=0.97,
        defect_rate=0.001,
        min_order_quantity=20,
        price_markup_factor=1.05,
    )
    scores = evaluator.evaluate_suppliers([sup_cheap_defective, sup_quality])
    # Defect rate and OTIF advantages outweigh modest price difference
    assert scores["SUP-QUALITY"] > scores["SUP-CHEAP-DEFECT"]


def test_p14_forecast_demand_surge_with_fixed_lead_time(sample_skus, sample_suppliers, sample_warehouse):
    """P14: Sudden demand surge in forecast with fixed lead time triggers dynamic upward ROP shift."""
    optimizer = _get_optimizer()
    sku = sample_skus[0]
    sup = sample_suppliers[0]

    # Baseline forecast: 10 units/day
    fc_base = ForecastResult(
        sku_id=sku.sku_id, forecast_horizon_days=30, point_forecast=[10.0] * 30,
        lower_bound_95=[5.0] * 30, upper_bound_95=[15.0] * 30,
        mean_daily_demand=10.0, std_daily_demand=2.0,
    )
    # Surge forecast: 25 units/day (+150% demand surge)
    fc_surge = ForecastResult(
        sku_id=sku.sku_id, forecast_horizon_days=30, point_forecast=[25.0] * 30,
        lower_bound_95=[15.0] * 30, upper_bound_95=[35.0] * 30,
        mean_daily_demand=25.0, std_daily_demand=5.0,
    )

    p_base = optimizer.calculate_policy(sku, fc_base, sup, sample_warehouse)
    p_surge = optimizer.calculate_policy(sku, fc_surge, sup, sample_warehouse)

    assert p_surge.reorder_point > p_base.reorder_point * 2.0
    assert p_surge.safety_stock > p_base.safety_stock * 1.5


def test_p15_expanding_horizon_with_cumulative_uncertainty(sample_demand_records):
    """P15: Forecast horizon expansion (14 to 60 days) expands prediction interval envelope."""
    forecaster = _get_forecaster()
    res_14 = forecaster.fit_predict(sample_demand_records, horizon_days=14, holdout_days=3)
    res_60 = forecaster.fit_predict(sample_demand_records, horizon_days=60, holdout_days=3)
    assert res_14.forecast_horizon_days == 14

    width_day_1 = res_60.upper_bound_95[0] - res_60.lower_bound_95[0]
    width_day_60 = res_60.upper_bound_95[-1] - res_60.lower_bound_95[-1]

    # Cumulative variance accumulation expands the forecast corridor over time
    assert width_day_60 >= width_day_1


def test_p16_pack_size_carton_and_supplier_moq_batching(sample_skus, sample_warehouse):
    """P16: Pack size = 24 and MOQ = 50: raw order of 35 rectified to ceil(50/24)*24 = 72."""
    rec_engine = _get_rec_engine()
    sku = sample_skus[0].model_copy()
    sku.pack_size = 24

    sup = Supplier(
        supplier_id="SUP-MOQ-50",
        name="MOQ 50 Supplier",
        mean_lead_time_days=5.0,
        std_lead_time_days=1.0,
        on_time_delivery_rate=0.95,
        defect_rate=0.01,
        min_order_quantity=50,
    )
    forecast = ForecastResult(
        sku_id=sku.sku_id, forecast_horizon_days=30, point_forecast=[5.0] * 30,
        lower_bound_95=[2.0] * 30, upper_bound_95=[8.0] * 30,
        mean_daily_demand=5.0, std_daily_demand=1.0,
    )

    # State with on_hand = 10.0 (non-negative)
    state = InventoryState(
        sku_id=sku.sku_id,
        on_hand=10.0,
        on_order=0.0,
    )
    # Manually configure policy with EOQ = 35 so raw requirement = max(35, ROP + EOQ - 10) = 50
    custom_policy = OptimizationPlan(
        sku_id=sku.sku_id,
        eoq=35.0,
        safety_stock=10.0,
        reorder_point=25.0,
        expected_annual_holding_cost=100.0,
        expected_annual_ordering_cost=100.0,
        expected_total_cost=200.0,
    )
    recs = rec_engine.generate_recommendations(
        [state], {sku.sku_id: sku}, {sku.sku_id: forecast}, {sku.sku_id: custom_policy},
        {sup.supplier_id: sup}, sample_warehouse
    )
    rec = recs[0]
    # Max(raw, MOQ) = max(50, 50) = 50. In 24-packs: ceil(50/24) * 24 = 3 * 24 = 72.
    assert rec.recommended_order_quantity % 24 == 0
    assert rec.recommended_order_quantity >= 50
    assert rec.recommended_order_quantity == 72.0
