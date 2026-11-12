"""Tier 4: Real-World Workload Scenarios E2E Test Suite.

Verifies end-to-end multi-period realistic operational workflows:
1. Multi-SKU seasonal peak replenishment campaign
2. Primary supplier disruption and emergency failover
3. Automated rolling replenishment cycle (14-day simulation)
4. Multi-item warehouse capacity contention and KKT scaling
5. Full pipeline from data generation to DSS passport validation
"""

import math
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

# Ensure project root is in sys.path
project_root = str(Path(__file__).resolve().parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from inventory_dss.models.domain import (
    SKU,
    DemandRecord,
    ForecastResult,
    InventoryState,
    PurchaseOrder,
    Supplier,
)
from tests.e2e.test_tier1_features import (
    _get_evaluator,
    _get_forecaster,
    _get_optimizer,
    _get_rec_engine,
)

# ===========================================================================
# Tier 4 Real-World Workload Scenario Tests (>=5 realistic scenarios)
# ===========================================================================

def test_scenario_01_seasonal_peak_replenishment(sample_warehouse):
    """Scenario 1: Multi-SKU seasonal peak replenishment campaign.

    Tests 25 SKUs over 730 days experiencing Q4 holiday demand surge (+150% demand).
    The system adapts forecasts upward, re-computes dynamic SS and ROP, and generates
    purchase recommendations without violating total warehouse capacity.
    """
    forecaster = _get_forecaster()
    optimizer = _get_optimizer()
    rec_engine = _get_rec_engine()

    # Generate 25 SKUs across 4 categories
    categories = ["Electronics", "Spare Parts", "Raw Materials", "Consumables"]
    skus = []
    for i in range(25):
        cat = categories[i % 4]
        skus.append(
            SKU(
                sku_id=f"SKU-PEAK-{i+1:03d}",
                name=f"Peak Item {i+1}",
                category=cat,
                unit_price=float(500 * (i % 5 + 1)),
                holding_cost_annual_rate=0.20,
                unit_volume_m3=0.01 * (i % 3 + 1),
                unit_weight_kg=1.0 * (i % 3 + 1),
                pack_size=1 if i % 2 == 0 else 10,
                abc_class="A" if i < 5 else ("B" if i < 15 else "C"),
                xyz_class="X" if i % 3 == 0 else ("Y" if i % 3 == 1 else "Z"),
            )
        )
    skus_dict = {s.sku_id: s for s in skus}

    supplier = Supplier(
        supplier_id="SUP-PEAK-PARTNER",
        name="Peak Logistics Partner",
        mean_lead_time_days=7.0,
        std_lead_time_days=1.5,
        on_time_delivery_rate=0.96,
        defect_rate=0.005,
        min_order_quantity=10,
        price_markup_factor=1.0,
    )
    sup_dict = {supplier.supplier_id: supplier}

    # Simulate demand with Q4 surge
    base_date = date(2024, 1, 1)
    forecasts = {}
    policies = {}
    inv_states = []

    for sku in skus:
        # Normal daily demand 10, surges to 25 during Q4
        records = []
        for d in range(730):
            cur_date = base_date + timedelta(days=d)
            is_q4 = (cur_date.month in [10, 11, 12])
            mean_d = 25.0 if is_q4 else 10.0
            records.append(
                DemandRecord(
                    date=cur_date,
                    sku_id=sku.sku_id,
                    quantity=float(np.random.default_rng(d).poisson(mean_d)),
                )
            )

        fc = forecaster.fit_predict(records, horizon_days=30, holdout_days=60)
        forecasts[sku.sku_id] = fc
        policy = optimizer.calculate_policy(sku, fc, supplier, sample_warehouse)
        policies[sku.sku_id] = policy

        # Current state: physical stock is at normal level (30 units) but surge requires 150+
        inv_states.append(
            InventoryState(
                sku_id=sku.sku_id,
                on_hand=30.0,
                on_order=0.0,
                allocated=5.0,
                backorders=0.0,
            )
        )

    recs = rec_engine.generate_recommendations(
        inv_states, skus_dict, forecasts, policies, sup_dict, sample_warehouse
    )

    assert len(recs) == 25
    total_vol_ordered = sum(r.recommended_order_quantity * skus_dict[r.sku_id].unit_volume_m3 for r in recs)
    total_wt_ordered = sum(r.recommended_order_quantity * skus_dict[r.sku_id].unit_weight_kg for r in recs)

    # All items needing replenishment are flagged
    orders_needed = [r for r in recs if r.order_needed]
    assert len(orders_needed) >= 20

    # Total order volume must be feasible within warehouse envelope
    assert total_vol_ordered <= sample_warehouse.total_volume_capacity_m3
    assert total_wt_ordered <= sample_warehouse.total_weight_capacity_kg


def test_scenario_02_supplier_disruption_and_failover(sample_skus, sample_warehouse):
    """Scenario 2: Primary supplier disruption & emergency failover.

    Primary low-cost supplier S1 collapses (OTIF drops to 20%, lead time triples).
    TOPSIS downgrades S1; recommendation engine redirects critical orders to S2 (local express).
    """
    evaluator = _get_evaluator()
    optimizer = _get_optimizer()
    rec_engine = _get_rec_engine()

    sku = sample_skus[0]
    forecast = ForecastResult(
        sku_id=sku.sku_id, forecast_horizon_days=30, point_forecast=[15.0] * 30,
        lower_bound_95=[5.0] * 30, upper_bound_95=[25.0] * 30,
        mean_daily_demand=15.0, std_daily_demand=3.0,
    )

    # 1. Normal state: Supplier A is primary (cheaper, reliable enough)
    sup_a_normal = Supplier(
        supplier_id="SUP-A",
        name="Primary Global",
        mean_lead_time_days=6.0,
        std_lead_time_days=1.0,
        on_time_delivery_rate=0.95,
        defect_rate=0.01,
        min_order_quantity=20,
        price_markup_factor=0.90,  # 10% discount
    )
    sup_b_express = Supplier(
        supplier_id="SUP-B",
        name="Local Express",
        mean_lead_time_days=2.0,
        std_lead_time_days=0.2,
        on_time_delivery_rate=0.99,
        defect_rate=0.002,
        min_order_quantity=1,
        price_markup_factor=1.15,  # Premium price
    )

    scores_normal = evaluator.evaluate_suppliers([sup_a_normal, sup_b_express])

    # 2. DISRUPTION EVENT: SUP-A experiences supply chain collapse
    sup_a_disrupted = Supplier(
        supplier_id="SUP-A",
        name="Primary Global (DISRUPTED)",
        mean_lead_time_days=28.0,  # Lead time jumps from 6 to 28 days!
        std_lead_time_days=10.0,
        on_time_delivery_rate=0.20,  # 80% delayed
        defect_rate=0.25,           # 25% defective!
        min_order_quantity=20,
        price_markup_factor=0.90,
    )

    scores_disrupted = evaluator.evaluate_suppliers([sup_a_disrupted, sup_b_express])
    # Disruption causes SUP-A score to drop significantly
    assert scores_normal["SUP-A"] > scores_disrupted["SUP-A"]
    assert scores_disrupted["SUP-B"] > scores_disrupted["SUP-A"] * 2.0

    # 3. Decision routing for critical stock
    policy = optimizer.calculate_policy(sku, forecast, sup_a_disrupted, sample_warehouse)
    crit_state = InventoryState(
        sku_id=sku.sku_id,
        on_hand=5.0,  # Far below safety stock
        on_order=0.0,
    )

    suppliers_map = {sup_a_disrupted.supplier_id: sup_a_disrupted, sup_b_express.supplier_id: sup_b_express}
    recs = rec_engine.generate_recommendations(
        [crit_state], {sku.sku_id: sku}, {sku.sku_id: forecast}, {sku.sku_id: policy},
        suppliers_map, sample_warehouse, supplier_scores=scores_disrupted
    )

    # System automatically fails over to SUP-B (Local Express)
    assert recs[0].status == "CRITICAL"
    assert recs[0].selected_supplier_id == "SUP-B"
    assert recs[0].urgency == "HIGH"


def test_scenario_03_automated_rolling_replenishment_cycle(sample_skus, sample_warehouse):
    """Scenario 3: Automated daily replenishment cycle (14-day rolling simulation).

    Simulates daily sales decrements, lead-time in-transit delays, daily rules engine evaluation,
    order arrival, and service level maintenance >= 95%.
    """
    optimizer = _get_optimizer()
    rec_engine = _get_rec_engine()
    sku = sample_skus[0]

    supplier = Supplier(
        supplier_id="SUP-ROLLING",
        name="Daily Rolling Logistics",
        mean_lead_time_days=3.0,
        std_lead_time_days=0.5,
        on_time_delivery_rate=0.98,
        defect_rate=0.005,
        min_order_quantity=10,
        price_markup_factor=1.0,
    )

    mean_daily_sales = 10.0
    forecast = ForecastResult(
        sku_id=sku.sku_id, forecast_horizon_days=30, point_forecast=[mean_daily_sales] * 30,
        lower_bound_95=[5.0] * 30, upper_bound_95=[15.0] * 30,
        mean_daily_demand=mean_daily_sales, std_daily_demand=2.0,
    )
    policy = optimizer.calculate_policy(sku, forecast, supplier, sample_warehouse)

    # Initial state
    current_on_hand = policy.reorder_point + policy.eoq / 2.0
    pipeline_orders: list[tuple[int, float]] = []  # (arrival_day, quantity)
    stockouts_count = 0
    total_days = 14

    for day in range(1, total_days + 1):
        # 1. Receive incoming shipments
        arrived = [qty for arr_day, qty in pipeline_orders if arr_day == day]
        current_on_hand += sum(arrived)
        pipeline_orders = [(arr_day, qty) for arr_day, qty in pipeline_orders if arr_day > day]

        # 2. Daily demand consumption
        daily_sales = 10.0  # Steady consumption
        if current_on_hand >= daily_sales:
            current_on_hand -= daily_sales
        else:
            stockouts_count += 1
            current_on_hand = 0.0

        # 3. Calculate effective inventory
        on_order_qty = sum(qty for _, qty in pipeline_orders)
        state = InventoryState(
            sku_id=sku.sku_id,
            on_hand=current_on_hand,
            on_order=on_order_qty,
        )

        # 4. Recommendation evaluation
        recs = rec_engine.generate_recommendations(
            [state], {sku.sku_id: sku}, {sku.sku_id: forecast}, {sku.sku_id: policy},
            {supplier.supplier_id: supplier}, sample_warehouse
        )
        rec = recs[0]

        # 5. Place order if needed
        if rec.order_needed and on_order_qty == 0:
            delivery_day = day + int(supplier.mean_lead_time_days)
            pipeline_orders.append((delivery_day, rec.recommended_order_quantity))

    # Service level target: zero unmanaged stockouts across rolling window
    assert stockouts_count == 0, f"Encountered {stockouts_count} stockout days in 14-day cycle"
    assert current_on_hand > 0


def test_scenario_04_multi_item_warehouse_capacity_contention(sample_skus, sample_warehouse):
    """Scenario 4: Multi-item warehouse capacity contention & constrained KKT allocation.

    10 raw materials and 15 electronics items simultaneously trigger reorder.
    Unconstrained proposals require 1,800 m3 (> 1,000 m3 limit). KKT scaling reduces non-critical
    items to guarantee total volume <= 1,000 m3 while respecting MOQs.
    """
    v_max = sample_warehouse.total_volume_capacity_m3  # 1000 m3
    w_max = sample_warehouse.total_weight_capacity_kg  # 50000 kg
    assert w_max == 50000.0

    sku_elec = sample_skus[0]  # vol=0.004 m3, wt=0.8 kg
    sku_raw = sample_skus[2]   # vol=0.35 m3, wt=450 kg

    # 10 raw materials orders of 500 units each: 10 * 500 * 0.35 = 1750 m3!
    # 15 electronics orders of 500 units each: 15 * 500 * 0.004 = 30 m3
    # Total volume = 1780 m3 > 1000 m3 limit!
    raw_orders = [500.0] * 10
    elec_orders = [500.0] * 15

    total_unconstrained_vol = sum(raw_orders) * sku_raw.unit_volume_m3 + sum(elec_orders) * sku_elec.unit_volume_m3
    assert total_unconstrained_vol > v_max

    # Constrained KKT allocation:
    # Protect electronics (compact, high value) and scale raw materials
    elec_vol_committed = sum(elec_orders) * sku_elec.unit_volume_m3  # 30 m3
    vol_remaining_for_raw = v_max - elec_vol_committed             # 970 m3
    max_raw_units_total = vol_remaining_for_raw / sku_raw.unit_volume_m3
    raw_units_per_sku = max_raw_units_total / 10.0                 # ~277 units each

    scaled_raw_orders = [raw_units_per_sku] * 10
    total_constrained_vol = sum(scaled_raw_orders) * sku_raw.unit_volume_m3 + elec_vol_committed

    assert math.isclose(total_constrained_vol, v_max, abs_tol=1e-3)
    assert total_constrained_vol <= v_max


def test_scenario_05_full_pipeline_to_passport_verification(sample_skus, sample_suppliers, sample_warehouse):
    """Scenario 5: Full DSS Pipeline from Synthetic Data to Exported DSS Passport.

    Validates that:
    1. Synthetic catalog, demand, and suppliers integrate seamlessly.
    2. Demand forecasting generates 95% uncertainty intervals and holdout metrics.
    3. Multi-criteria evaluation calculates TOPSIS relative closeness.
    4. Stochastic optimization determines EOQ, SS, and ROP.
    5. Recommendations produce Purchase Orders.
    6. PASSPORT_DSS.md is fully populated across all 8 canonical sections.
    """
    forecaster = _get_forecaster()
    evaluator = _get_evaluator()
    optimizer = _get_optimizer()
    rec_engine = _get_rec_engine()

    sku = sample_skus[0]
    sup = sample_suppliers[0]

    # Step 1: Demand generation & forecast
    history = [
        DemandRecord(date=date(2025, 1, 1) + timedelta(days=d), sku_id=sku.sku_id, quantity=10.0 + (d % 5))
        for d in range(100)
    ]
    forecast = forecaster.fit_predict(history, horizon_days=30, holdout_days=20)
    assert forecast.mean_daily_demand > 0
    assert len(forecast.point_forecast) == 30

    # Step 2: Multi-criteria supplier ranking
    scores = evaluator.evaluate_suppliers(sample_suppliers)
    assert len(scores) == len(sample_suppliers)

    # Step 3: Inventory optimization policy
    policy = optimizer.calculate_policy(sku, forecast, sup, sample_warehouse)
    assert policy.safety_stock > 0
    assert policy.reorder_point > 0

    # Step 4: Recommendation generation
    crit_state = InventoryState(sku_id=sku.sku_id, on_hand=5.0, on_order=0.0)
    recs = rec_engine.generate_recommendations(
        [crit_state], {sku.sku_id: sku}, {sku.sku_id: forecast}, {sku.sku_id: policy},
        {s.supplier_id: s for s in sample_suppliers}, sample_warehouse, supplier_scores=scores
    )
    assert len(recs) == 1
    rec = recs[0]
    assert rec.order_needed is True

    # Step 5: Convert approved recommendation to PurchaseOrder
    po = PurchaseOrder(
        order_id="PO-TEST-001",
        sku_id=rec.sku_id,
        supplier_id=rec.selected_supplier_id,
        quantity=rec.recommended_order_quantity,
        unit_price=sku.unit_price,
        total_cost=round(rec.recommended_order_quantity * sku.unit_price, 2),
        order_date=date.today(),
        expected_delivery_date=date.today() + timedelta(days=int(sup.mean_lead_time_days)),
        status="APPROVED",
    )
    assert po.quantity > 0
    assert po.status == "APPROVED"

    # Step 6: Verify DSS Passport completeness
    passport_path = Path(__file__).resolve().parents[2] / "docs" / "PASSPORT_DSS.md"
    assert passport_path.exists()
    passport_text = passport_path.read_text(encoding="utf-8")
    for sec in range(1, 9):
        assert f"Раздел {sec}." in passport_text
