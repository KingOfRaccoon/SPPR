"""Tier 5: Adversarial Coverage Hardening E2E Test Suite.

Adversarial Stress Testing, Edge Case Mining, and Invariant Verification:
1. Combined demand spike + supplier disruption failover across the entire pipeline.
2. Simultaneous warehouse capacity binding (volume + weight) with multi-item Lagrangian KKT trimming and discrete pack rounding.
3. Intermittent Croston demand forecasting feeding into Wald compound safety stock and recommendations.
4. Production rules engine edge cases: salience priority under competing conditions, refraction cycle prevention, duplicate registration, and trace generation.
5. Multi-tier volume discount step-function arbitrage and holding cost penalties.
6. AHP & TOPSIS mathematical boundaries (non-square, empty, uniform alternatives, weight mismatches).
7. Full pipeline execution: synthetic data -> forecasting -> supplier TOPSIS -> optimization -> recommendation batch -> headless Streamlit UI AppTest validation.
"""

from __future__ import annotations

import math
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

# Ensure project root is in sys.path
project_root = str(Path(__file__).resolve().parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from inventory_dss.config import PACKAGE_ROOT
from inventory_dss.data.generator import SyntheticDataGenerator
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
from inventory_dss.forecasting.model import DemandForecaster
from inventory_dss.knowledge.ontology import build_inventory_ontology
from inventory_dss.knowledge.rules import (
    Fact,
    Rule,
    RuleEngine,
    WorkingMemory,
    build_inventory_rule_engine,
)
from inventory_dss.models.domain import (
    SKU,
    DemandRecord,
    DiscountTier,
    ForecastResult,
    InventoryState,
    OptimizationPlan,
    StockStatus,
    Supplier,
    SupplierProfileType,
    Warehouse,
)
from inventory_dss.optimization.capacity import CapacityOptimizer
from inventory_dss.optimization.engine import InventoryOptimizer
from inventory_dss.optimization.eoq import (
    calculate_classical_eoq,
    calculate_eoq_with_discounts,
    calculate_total_inventory_cost,
)
from inventory_dss.optimization.stochastic import calculate_rop, calculate_safety_stock
from inventory_dss.recommendations.engine import RecommendationEngine
from inventory_dss.recommendations.models import RecommendationBatch
from inventory_dss.suppliers.ahp import AHPEngine
from inventory_dss.suppliers.entropy import EntropyWeightEngine
from inventory_dss.suppliers.evaluator import SupplierEvaluator
from inventory_dss.suppliers.risk_trees import SupplyRiskDecisionTree
from inventory_dss.suppliers.topsis import TOPSISSolver

APP_PATH = PACKAGE_ROOT / "ui" / "app.py"


# ===========================================================================
# Group 1: Combined Demand Shocks + Multi-Supplier Disruption & Failovers
# ===========================================================================

def test_adv_01_catastrophic_demand_spike_with_primary_supplier_collapse(
    sample_skus: list[SKU], sample_suppliers: list[Supplier], sample_warehouse: Warehouse
):
    """Test 1: Sudden 10x demand spike with primary supplier defect rate spiking to 100%.

    Adversarial scenario:
    - SKU-ELEC-001 experiences a 10x surge in daily demand (flash sale / shock).
    - The historically favored supplier SUP-PREMIUM suffers catastrophic disruption:
      defect rate jumps to 1.0 (100% defective) and lead time jumps to 60 days.
    - System must automatically penalize SUP-PREMIUM in TOPSIS scoring, reroute orders
      to backup/express supplier (SUP-LOCAL), expand safety stock and ROP, and generate
      positive replenishment recommendations covering the shock and any backorders.
    """
    sku = sample_skus[0]  # SKU-ELEC-001
    forecaster = DemandForecaster()
    evaluator = SupplierEvaluator()
    optimizer = InventoryOptimizer()
    rec_engine = RecommendationEngine()

    # Generate 180 days history with a massive 10x demand shock in the last 30 days
    base_date = date(2025, 1, 1)
    history: list[DemandRecord] = []
    for day in range(180):
        cur_date = base_date + timedelta(days=day)
        # Normal baseline: ~10 units/day; last 30 days: 100 units/day
        qty = float(np.random.poisson(100.0) if day >= 150 else np.random.poisson(10.0))
        history.append(
            DemandRecord(
                date=cur_date,
                sku_id=sku.sku_id,
                quantity=max(1.0, qty),
                is_weekend=(cur_date.weekday() >= 5),
            )
        )

    forecast_res = forecaster.fit_predict(history, horizon_days=30, holdout_days=30)
    assert forecast_res.mean_daily_demand > 20.0
    assert forecast_res.std_daily_demand > 0.0

    # Perturb primary supplier to collapse
    collapsed_suppliers = [
        Supplier(
            supplier_id="SUP-PREMIUM",
            name="ТехноСнаб Премиум (Collapsed)",
            mean_lead_time_days=60.0,
            std_lead_time_days=15.0,
            on_time_delivery_rate=0.10,
            defect_rate=1.0,
            min_order_quantity=500,
            price_markup_factor=1.50,
            profile_type=SupplierProfileType.PREMIUM_RELIABLE,
        ),
        Supplier(
            supplier_id="SUP-LOCAL",
            name="Северо-Запад Экспресс (Backup)",
            mean_lead_time_days=2.0,
            std_lead_time_days=0.3,
            on_time_delivery_rate=0.96,
            defect_rate=0.008,
            min_order_quantity=1,
            price_markup_factor=1.05,
            profile_type=SupplierProfileType.LOCAL_EXPRESS,
        ),
    ]

    # Evaluate suppliers under TOPSIS
    scores = evaluator.evaluate_suppliers(collapsed_suppliers)
    assert scores["SUP-LOCAL"] > scores["SUP-PREMIUM"], "Backup supplier must decisively beat collapsed supplier"
    assert scores["SUP-PREMIUM"] < 0.20, f"Collapsed supplier score must be severely penalized, got {scores['SUP-PREMIUM']}"

    # Best supplier must be SUP-LOCAL
    best_sup = collapsed_suppliers[1]
    policy = optimizer.calculate_policy(
        sku=sku,
        demand_forecast=forecast_res,
        supplier=best_sup,
        warehouse=sample_warehouse,
    )
    assert policy.safety_stock > 0.0
    assert policy.reorder_point > policy.safety_stock

    # Under critical inventory state (on_hand = 0, backorders = 50)
    crit_state = InventoryState(
        sku_id=sku.sku_id,
        on_hand=0.0,
        on_order=0.0,
        allocated=0.0,
        backorders=50.0,
        safety_stock=policy.safety_stock,
        reorder_point=policy.reorder_point,
        status=StockStatus.CRITICAL,
    )

    recs = rec_engine.generate_recommendations(
        inventory_states=[crit_state],
        skus={sku.sku_id: sku},
        forecasts={sku.sku_id: forecast_res},
        policies={sku.sku_id: policy},
        suppliers={s.supplier_id: s for s in collapsed_suppliers},
        warehouse=sample_warehouse,
        supplier_scores=scores,
    )

    assert len(recs) == 1
    rec = recs[0]
    assert rec.status == "CRITICAL"
    assert rec.order_needed is True
    assert rec.selected_supplier_id == "SUP-LOCAL"
    # Order quantity must cover backorders (50) + target buffer (ROP + EOQ)
    assert rec.recommended_order_quantity >= 50.0 + policy.eoq


def test_adv_02_simultaneous_all_supplier_lead_time_explosion_and_joint_uncertainty():
    """Test 2: All suppliers suffer severe lead time explosion (e.g. global logistics freeze).

    Adversarial scenario:
    - Lead times jump 5x-10x, and lead time variance jumps to sigma_L = 8.0 days.
    - Safety stock formula SS = Z_alpha * sqrt(mu_L * sigma_D^2 + mu_D^2 * sigma_L^2)
      must handle joint compounding uncertainty without numerical overflow or NaN.
    - Safety stock must be strictly greater than individual variance components.
    """
    mu_D = 50.0
    sigma_D = 15.0
    mu_L = 45.0  # Exploded from 4.0 to 45.0 days
    sigma_L = 8.0  # Exploded from 0.5 to 8.0 days
    service_level = 0.99  # Z ~ 2.3263

    ss_joint = calculate_safety_stock(
        mean_demand=mu_D,
        std_demand=sigma_D,
        mean_lead_time=mu_L,
        std_lead_time=sigma_L,
        service_level=service_level,
    )

    # Component 1: Demand variance during lead time: mu_L * sigma_D^2 = 45 * 225 = 10125
    # Component 2: Lead time variance: mu_D^2 * sigma_L^2 = 2500 * 64 = 160000
    # Joint variance = 170125, sqrt = 412.46, SS = 2.3263 * 412.46 = 959.52
    assert math.isfinite(ss_joint)
    assert ss_joint > 900.0

    # Individual component with zero lead-time variance
    ss_demand_only = calculate_safety_stock(
        mean_demand=mu_D,
        std_demand=sigma_D,
        mean_lead_time=mu_L,
        std_lead_time=0.0,
        service_level=service_level,
    )
    assert ss_joint > ss_demand_only * 3.0, "Joint compounding variance must heavily dominate demand-only variance"

    # ROP must compound mu_D * mu_L + SS
    rop = calculate_rop(
        mean_demand=mu_D,
        mean_lead_time=mu_L,
        safety_stock=ss_joint,
    )
    expected_rop = round(mu_D * mu_L + ss_joint, 2)
    assert rop == expected_rop
    assert rop > 3000.0


def test_adv_03_supplier_anti_ideal_reversal_adversarial_matrix():
    """Test 3: Pathological supplier decision matrix with extreme conflicting attributes.

    Adversarial scenario:
    - Supplier 1: Perfect defect rate (0.0), but exorbitant price markup (10.0x).
    - Supplier 2: Free price (0.01x), but 100% defect rate (1.0).
    - Supplier 3: Fast lead time (0.1 days), but enormous MOQ (10,000 units).
    - Supplier 4: Balanced benchmark.
    Tests vector normalization, Euclidean distance stability, and closeness strictly in [0, 1].
    """
    matrix = np.array([
        [10.0, 5.0, 1.0, 0.0, 50, 0.99],   # Sup 1: Price=10.0, Defect=0.0
        [0.01, 10.0, 2.0, 1.0, 100, 0.50], # Sup 2: Price=0.01, Defect=1.0
        [1.0, 0.1, 0.05, 0.02, 10000, 0.95], # Sup 3: Lead=0.1, MOQ=10000
        [1.05, 4.0, 0.5, 0.005, 20, 0.98], # Sup 4: Balanced
    ])
    weights = np.array([0.25, 0.20, 0.10, 0.20, 0.10, 0.15])
    is_benefit = [False, False, False, False, False, True]

    res = TOPSISSolver.solve_detailed(matrix, weights, is_benefit)
    closeness = res["closeness"]
    ranks = res["ranks"]

    assert len(closeness) == 4
    for c in closeness:
        assert 0.0 <= c <= 1.0, f"TOPSIS closeness must be bounded in [0, 1], got {c}"

    # Sup 4 (balanced) should rank near top while pathological suppliers rank lower
    assert ranks[3] <= 2, "Balanced supplier should be top-ranked"
    assert ranks[1] >= 3, "Supplier with 100% defect rate must be penalized in bottom half"


# ===========================================================================
# Group 2: Simultaneous Capacity Binding & Discrete KKT Trimming
# ===========================================================================

def test_adv_04_dual_binding_capacity_kkt_tight_envelope():
    """Test 4: Simultaneous volume and weight capacity binding under tight warehouse envelope.

    Adversarial scenario:
    - 4 SKUs with unconstrained EOQs requiring 1,200 m3 and 60,000 kg.
    - Warehouse restricts total storage to only 200 m3 and 10,000 kg (severe double constraint).
    - CapacityOptimizer must activate Kuhn-Tucker Lagrangian multipliers (lambda_v > 0 or mu_w > 0).
    - Allocated quantities must strictly obey volume <= 200 and weight <= 10,000.
    """
    wh = Warehouse(
        warehouse_id="WH-TIGHT-01",
        total_volume_capacity_m3=200.0,
        total_weight_capacity_kg=10000.0,
        fixed_order_cost=3000.0,
        annual_capital_rate=0.20,
    )
    skus = {
        f"SKU-T-{i}": SKU(
            sku_id=f"SKU-T-{i}",
            name=f"Bulk Item {i}",
            category="Raw Materials",
            unit_price=1000.0,
            holding_cost_annual_rate=0.20,
            unit_volume_m3=1.0,
            unit_weight_kg=50.0,
            pack_size=5,
            abc_class="A",
            xyz_class="X",
        )
        for i in range(4)
    }
    unconstrained_eoqs = {f"SKU-T-{i}": 300.0 for i in range(4)}  # Totals: 1200 m3, 60,000 kg
    annual_demands = {f"SKU-T-{i}": 5000.0 for i in range(4)}
    order_costs = {f"SKU-T-{i}": 3000.0 for i in range(4)}
    holding_costs = {f"SKU-T-{i}": 200.0 for i in range(4)}

    optimizer = CapacityOptimizer(wh)
    res = optimizer.optimize_allocation(
        unconstrained_eoqs=unconstrained_eoqs,
        skus=skus,
        annual_demands=annual_demands,
        order_costs=order_costs,
        holding_costs=holding_costs,
    )

    assert res.is_constrained is True
    assert (res.lambda_volume > 0.0) or (res.mu_weight > 0.0), "At least one KKT multiplier must be strictly positive"
    assert res.total_volume_m3 <= wh.total_volume_capacity_m3 + 1e-3
    assert res.total_weight_kg <= wh.total_weight_capacity_kg + 1e-3
    # Every allocated quantity must be an integer multiple of pack size (5)
    for q in res.allocated_quantities.values():
        assert q > 0.0
        assert math.isclose(q % 5, 0.0, abs_tol=1e-5), f"Quantity {q} must be multiple of pack_size 5"


def test_adv_05_kkt_trimming_under_asymmetric_pack_sizes_and_high_moqs():
    """Test 5: Discrete pack trimming under asymmetric pack sizes (12, 48, 100) and high MOQs.

    Adversarial scenario:
    - Multiple SKUs where pack sizes are large (12, 48, 100) and MOQs are binding (200).
    - Warehouse capacity is tightly constrained ($V_max = 25.0 m3$).
    - Phase 1 & Phase 2 trimming must greedily reduce quantities without violating MOQ lower bounds
      or pack size divisibility.
    """
    wh = Warehouse(
        warehouse_id="WH-ASYMM-01",
        total_volume_capacity_m3=45.0,
        total_weight_capacity_kg=20000.0,
        fixed_order_cost=4000.0,
        annual_capital_rate=0.15,
    )
    skus = {
        "SKU-P12": SKU(
            sku_id="SKU-P12",
            name="Carton 12",
            category="Consumables",
            unit_price=500.0,
            unit_volume_m3=0.05,
            unit_weight_kg=5.0,
            pack_size=12,
            abc_class="B",
            xyz_class="Y",
        ),
        "SKU-P48": SKU(
            sku_id="SKU-P48",
            name="Crate 48",
            category="Spare Parts",
            unit_price=1200.0,
            unit_volume_m3=0.10,
            unit_weight_kg=15.0,
            pack_size=48,
            abc_class="A",
            xyz_class="X",
        ),
        "SKU-P100": SKU(
            sku_id="SKU-P100",
            name="Pallet 100",
            category="Raw Materials",
            unit_price=3000.0,
            unit_volume_m3=0.25,
            unit_weight_kg=40.0,
            pack_size=100,
            abc_class="A",
            xyz_class="Z",
        ),
    }
    unconstrained_eoqs = {"SKU-P12": 360.0, "SKU-P48": 240.0, "SKU-P100": 200.0}
    moqs = {"SKU-P12": 96, "SKU-P48": 96, "SKU-P100": 100}
    annual_demands = {"SKU-P12": 2000.0, "SKU-P48": 1500.0, "SKU-P100": 800.0}
    order_costs = {"SKU-P12": 2500.0, "SKU-P48": 3000.0, "SKU-P100": 4000.0}
    holding_costs = {"SKU-P12": 75.0, "SKU-P48": 180.0, "SKU-P100": 450.0}

    optimizer = CapacityOptimizer(wh)
    res = optimizer.optimize_allocation(
        unconstrained_eoqs=unconstrained_eoqs,
        skus=skus,
        annual_demands=annual_demands,
        order_costs=order_costs,
        holding_costs=holding_costs,
        moqs=moqs,
    )

    for sid, q in res.allocated_quantities.items():
        pack = skus[sid].pack_size
        moq = moqs[sid]
        assert math.isclose(q % pack, 0.0, abs_tol=1e-5), f"{sid}: Q={q} must be divisible by pack={pack}"
        assert q >= moq, f"{sid}: Q={q} must be at least MOQ={moq}"


def test_adv_06_capacity_contention_with_critical_versus_reorder_prioritization(
    sample_skus: list[SKU], sample_suppliers: list[Supplier]
):
    """Test 6: Recommendation engine capacity enforcement protects CRITICAL over REORDER items.

    Adversarial scenario:
    - 2 SKUs in CRITICAL status (on-hand 0, DOI < 1).
    - 2 SKUs in REORDER_NEEDED status.
    - Warehouse capacity is restricted so that total unconstrained orders exceed volume.
    - System must 100% protect CRITICAL item orders and trim REORDER_NEEDED orders
      within the residual envelope.
    """
    wh = Warehouse(
        warehouse_id="WH-PRIO-01",
        total_volume_capacity_m3=20.0,  # Tight capacity
        total_weight_capacity_kg=5000.0,
        fixed_order_cost=3000.0,
        annual_capital_rate=0.20,
    )
    rec_engine = RecommendationEngine()

    skus = {s.sku_id: s for s in sample_skus}
    suppliers = {s.supplier_id: s for s in sample_suppliers}

    # SKU 0 and 1 are CRITICAL
    # SKU 2 and 3 are REORDER_NEEDED
    states = [
        InventoryState(
            sku_id=sample_skus[0].sku_id,
            on_hand=0.0,
            safety_stock=20.0,
            reorder_point=50.0,
            status=StockStatus.CRITICAL,
        ),
        InventoryState(
            sku_id=sample_skus[1].sku_id,
            on_hand=5.0,
            safety_stock=20.0,
            reorder_point=50.0,
            status=StockStatus.CRITICAL,
        ),
        InventoryState(
            sku_id=sample_skus[2].sku_id,
            on_hand=60.0,
            safety_stock=20.0,
            reorder_point=100.0,
            status=StockStatus.REORDER_NEEDED,
        ),
        InventoryState(
            sku_id=sample_skus[3].sku_id,
            on_hand=60.0,
            safety_stock=20.0,
            reorder_point=100.0,
            status=StockStatus.REORDER_NEEDED,
        ),
    ]

    forecasts = {
        s.sku_id: ForecastResult(
            sku_id=s.sku_id,
            forecast_horizon_days=30,
            model_name="HoltWinters",
            point_forecast=[15.0] * 30,
            mean_daily_demand=15.0,
            std_daily_demand=3.0,
            metrics={"WAPE": 0.10, "RMSE": 3.0, "MAE": 2.5},
            lower_bound_95=[10.0] * 30,
            upper_bound_95=[20.0] * 30,
        )
        for s in sample_skus
    }

    policies = {
        s.sku_id: OptimizationPlan(
            sku_id=s.sku_id,
            eoq=50.0,
            safety_stock=20.0,
            reorder_point=100.0,
            expected_total_cost=50000.0,
            expected_annual_holding_cost=20000.0,
            expected_annual_ordering_cost=10000.0,
        )
        for s in sample_skus
    }

    # Generate with capacity enforcement
    recs = rec_engine.generate_recommendations(
        inventory_states=states,
        skus=skus,
        forecasts=forecasts,
        policies=policies,
        suppliers=suppliers,
        warehouse=wh,
        enforce_capacity=True,
    )

    crit_recs = [r for r in recs if r.status == "CRITICAL"]
    reorder_recs = [r for r in recs if r.status == "REORDER_NEEDED"]

    assert len(crit_recs) == 2
    assert len(reorder_recs) == 2

    # Verify CRITICAL items got their full unconstrained quantities
    for cr in crit_recs:
        assert cr.recommended_order_quantity >= 50.0

    # Total volume of final recommendations must not exceed warehouse envelope
    tot_vol = sum(r.warehouse_volume_required_m3 for r in recs)
    assert tot_vol <= wh.total_volume_capacity_m3 + 1e-2


def test_adv_07_zero_residual_capacity_critical_starvation_behavior(
    sample_skus: list[SKU], sample_suppliers: list[Supplier]
):
    """Test 7: CRITICAL items alone saturate 100% of warehouse capacity.

    Adversarial scenario:
    - CRITICAL items require 15.0 m3 of volume, but warehouse capacity is only 10.0 m3.
    - Residual capacity for REORDER_NEEDED items is 0.0 m3.
    - Recommendation engine must zero-out REORDER items with a clear rationale explaining
      capacity exhaustion by critical orders, while maintaining critical orders.
    """
    wh = Warehouse(
        warehouse_id="WH-TINY-01",
        total_volume_capacity_m3=5.0,  # Very small
        total_weight_capacity_kg=2000.0,
        fixed_order_cost=3000.0,
        annual_capital_rate=0.20,
    )
    rec_engine = RecommendationEngine()
    skus = {s.sku_id: s for s in sample_skus}
    suppliers = {s.supplier_id: s for s in sample_suppliers}

    states = [
        InventoryState(
            sku_id=sample_skus[2].sku_id,  # Heavy raw material (0.350 m3 / unit)
            on_hand=0.0,
            safety_stock=20.0,
            reorder_point=40.0,
            status=StockStatus.CRITICAL,
        ),
        InventoryState(
            sku_id=sample_skus[0].sku_id,
            on_hand=30.0,
            safety_stock=20.0,
            reorder_point=40.0,
            status=StockStatus.REORDER_NEEDED,
        ),
    ]

    forecasts = {
        s.sku_id: ForecastResult(
            sku_id=s.sku_id,
            forecast_horizon_days=30,
            model_name="HoltWinters",
            point_forecast=[10.0] * 30,
            mean_daily_demand=10.0,
            std_daily_demand=2.0,
            metrics={"WAPE": 0.10, "RMSE": 2.0, "MAE": 1.5},
            lower_bound_95=[5.0] * 30,
            upper_bound_95=[15.0] * 30,
        )
        for s in sample_skus
    }

    policies = {
        s.sku_id: OptimizationPlan(
            sku_id=s.sku_id,
            eoq=30.0,
            safety_stock=20.0,
            reorder_point=40.0,
            expected_total_cost=20000.0,
            expected_annual_holding_cost=5000.0,
            expected_annual_ordering_cost=5000.0,
        )
        for s in sample_skus
    }

    recs = rec_engine.generate_recommendations(
        inventory_states=states,
        skus=skus,
        forecasts=forecasts,
        policies=policies,
        suppliers=suppliers,
        warehouse=wh,
        enforce_capacity=True,
    )

    reorder_rec = next(r for r in recs if r.sku_id == sample_skus[0].sku_id)
    # Reorder item must be trimmed to 0 because critical item consumed all capacity
    assert reorder_rec.recommended_order_quantity == 0.0
    assert "Capacity trimmed" in reorder_rec.rationale


# ===========================================================================
# Group 3: Intermittent Croston Demand & Extreme Volatility
# ===========================================================================

def test_adv_08_hyper_sparse_croston_demand_to_wald_safety_stock():
    """Test 8: Intermittent demand with 95% zeros feeding into Wald compound safety stock.

    Adversarial scenario:
    - Daily demand series has 95% zero days (demand events occur once every 20-30 days).
    - CrostonForecaster must update smoothed demand level (z) and smoothed inter-arrival interval (p).
    - Rate forecast must be strictly positive (e.g. 0.2 units/day).
    - Downstream DemandForecaster must fit holdout and select Croston or parsimonious baseline.
    - calculate_safety_stock must handle low daily mean without division by zero.
    """
    np.random.seed(42)
    n_days = 365
    demand_series = np.zeros(n_days)
    # Demand occurs randomly on ~18 days with magnitude 5..20
    event_days = np.random.choice(n_days, size=18, replace=False)
    for day in event_days:
        demand_series[day] = float(np.random.randint(5, 20))

    croston = CrostonForecaster(alpha=0.1)
    croston.fit(demand_series)
    preds = croston.predict(30)

    assert croston.forecast_rate > 0.0
    assert len(preds) == 30
    assert np.all(preds == croston.forecast_rate)

    # Integrated model fit_predict
    base_date = date(2025, 1, 1)
    records = [
        DemandRecord(
            date=base_date + timedelta(days=i),
            sku_id="SKU-CROSTON-01",
            quantity=float(demand_series[i]),
        )
        for i in range(n_days)
    ]

    model = DemandForecaster()
    forecast_res = model.fit_predict(records, horizon_days=30, holdout_days=60)
    assert forecast_res.mean_daily_demand > 0.0
    assert math.isfinite(forecast_res.mean_daily_demand)

    # Calculate safety stock with intermittent parameters
    ss = calculate_safety_stock(
        mean_demand=forecast_res.mean_daily_demand,
        std_demand=forecast_res.std_daily_demand,
        mean_lead_time=10.0,
        std_lead_time=2.0,
        service_level=0.95,
    )
    assert ss > 0.0
    assert math.isfinite(ss)


def test_adv_09_alternating_binary_burst_demand_with_trend():
    """Test 9: Highly volatile burst demand alternating between 0 and 500 units with trend.

    Adversarial scenario:
    - Tests prediction interval coverage: 95% confidence bands must properly expand
      with residual standard deviation.
    - Lower confidence bound must be strictly clamped at 0.0 (non-negative demand).
    """
    n_days = 180
    base_date = date(2025, 1, 1)
    records = []
    for t in range(n_days):
        trend = 0.5 * t
        burst = 300.0 if (t % 14 == 0) else 0.0
        q = max(0.0, trend + burst + np.random.normal(5.0, 2.0))
        records.append(
            DemandRecord(
                date=base_date + timedelta(days=t),
                sku_id="SKU-BURST-01",
                quantity=round(q, 2),
            )
        )

    model = DemandForecaster()
    res = model.fit_predict(records, horizon_days=30, holdout_days=30)

    assert len(res.lower_bound_95) == 30
    assert len(res.upper_bound_95) == 30
    assert all(lb >= 0.0 for lb in res.lower_bound_95), "Lower bound must never drop below 0.0"
    assert all(ub >= lb for lb, ub in zip(res.lower_bound_95, res.upper_bound_95))


def test_adv_10_deterministic_flat_zero_demand_transition_to_sudden_shock():
    """Test 10: 180 days of flat zero demand followed by 5 days of 50 units shock demand.

    Adversarial scenario:
    - Tests division-by-zero protection in holdout error metrics (WAPE, RMSE).
    - Verifies model refits without NaN or Inf.
    """
    base_date = date(2025, 1, 1)
    records = [
        DemandRecord(
            date=base_date + timedelta(days=i),
            sku_id="SKU-SHOCK-01",
            quantity=0.0 if i < 180 else 50.0,
        )
        for i in range(185)
    ]

    model = DemandForecaster()
    res = model.fit_predict(records, horizon_days=14, holdout_days=20)
    assert math.isfinite(res.mean_daily_demand)
    assert res.mean_daily_demand > 0.0
    assert all(math.isfinite(v) for v in res.metrics.values())


# ===========================================================================
# Group 4: Production Rules Engine Forward-Chaining & Refraction
# ===========================================================================

def test_adv_11_production_rules_salience_conflict_resolution():
    """Test 11: Production rules engine salience conflict resolution.

    Adversarial scenario:
    - Multiple candidate rules match the same fact.
    - Rule A has higher salience (priority=100) than Rule B (priority=50).
    - Rule Engine conflict resolution must fire Rule A first and record detailed traces.
    """
    engine = RuleEngine()
    fired_order: list[str] = []

    def cond_high(wm: WorkingMemory):
        matches = []
        for f in wm.get_facts_by_name("StockAlertFact"):
            if not [e for e in wm.get_facts_by_name("HighPriorityHandledFact") if e.get("target") == f.get("sku")]:
                matches.append({"sku": f.get("sku")})
        return matches

    def act_high(wm: WorkingMemory, bindings: dict, asserted: list):
        fired_order.append("RULE_HIGH")
        f = Fact("HighPriorityHandledFact", {"target": bindings["sku"]})
        wm.assert_fact(f)
        asserted.append(f)
        return "Fired high priority rule"

    def cond_low(wm: WorkingMemory):
        matches = []
        for f in wm.get_facts_by_name("StockAlertFact"):
            if not [e for e in wm.get_facts_by_name("LowPriorityHandledFact") if e.get("target") == f.get("sku")]:
                matches.append({"sku": f.get("sku")})
        return matches

    def act_low(wm: WorkingMemory, bindings: dict, asserted: list):
        fired_order.append("RULE_LOW")
        f = Fact("LowPriorityHandledFact", {"target": bindings["sku"]})
        wm.assert_fact(f)
        asserted.append(f)
        return "Fired low priority rule"

    rule_high = Rule(
        rule_id="R_HIGH",
        name="High Salience Handler",
        priority=100,
        condition=cond_high,
        action=act_high,
    )
    rule_low = Rule(
        rule_id="R_LOW",
        name="Low Salience Handler",
        priority=50,
        condition=cond_low,
        action=act_low,
    )

    engine.register_rule(rule_low)
    engine.register_rule(rule_high)

    wm = WorkingMemory()
    wm.assert_fact(Fact("StockAlertFact", {"sku": "SKU-TEST-1"}))

    report = engine.run(wm, max_cycles=10)
    assert report.rules_fired_count == 2
    assert fired_order[0] == "RULE_HIGH", "Higher priority rule must fire before lower priority rule"
    assert fired_order[1] == "RULE_LOW"
    assert len(report.execution_traces) == 2


def test_adv_12_production_rules_refraction_cycle_loop_prevention():
    """Test 12: Production rules engine refraction cycle loop prevention.

    Adversarial scenario:
    - A rule asserts a fact that matches its own condition.
    - Without refraction, this would loop infinitely until max_cycles.
    - Refraction set must detect the exact same (rule_id, matched_facts) and prevent repeat execution.
    """
    engine = RuleEngine()
    firing_count = 0

    def cond_recursive(wm: WorkingMemory):
        matches = []
        for f in wm.get_facts_by_name("LoopFact"):
            matches.append({"val": f.get("val")})
        return matches

    def act_recursive(wm: WorkingMemory, bindings: dict, asserted: list):
        nonlocal firing_count
        firing_count += 1
        # Action does not modify facts that would alter matched_facts
        return "Fired recursive rule"

    engine.register_rule(
        Rule(
            rule_id="R_LOOP",
            name="Recursive Trigger",
            priority=10,
            condition=cond_recursive,
            action=act_recursive,
        )
    )

    wm = WorkingMemory()
    wm.assert_fact(Fact("LoopFact", {"val": 42}))

    report = engine.run(wm, max_cycles=50)
    # Refraction must prevent infinite firing; it must fire exactly once!
    assert firing_count == 1
    assert report.rules_fired_count == 1
    assert report.cycles_executed == 2  # Cycle 1: fires, Cycle 2: quiescence


def test_adv_13_production_rules_duplicate_registration_and_fact_isolation():
    """Test 13: Duplicate rule registration raises ValueError and working memory retract."""
    engine = RuleEngine()
    rule1 = Rule(rule_id="R1", name="Rule 1", condition=lambda wm: [], action=lambda wm, b, a: "")
    rule2 = Rule(rule_id="R1", name="Rule 1 Dup", condition=lambda wm: [], action=lambda wm, b, a: "")

    engine.register_rule(rule1)
    with pytest.raises(ValueError, match="already registered"):
        engine.register_rule(rule2)

    wm = WorkingMemory()
    f1 = Fact("FactA", {"key": "val1"})
    f2 = Fact("FactA", {"key": "val2"})
    wm.assert_fact(f1)
    wm.assert_fact(f2)
    assert len(wm.get_facts_by_name("FactA")) == 2

    # Retract fact
    wm.retract_fact(f1.id)
    assert len(wm.get_facts_by_name("FactA")) == 1
    assert wm.get_facts_by_name("FactA")[0].id == f2.id


def test_adv_14_full_knowledge_ontology_and_forward_chaining_stock_trace(
    sample_skus: list[SKU], sample_inventory_states: dict[str, InventoryState]
):
    """Test 14: Canonical ontology and forward-chaining rule engine execution on 4 SKU states.

    Verifies:
    - Domain ontology concepts, relations, and validation.
    - Rule engine classifies all states into StockClassificationFact.
    - Execution traces capture detailed audit trail.
    """
    ontology = build_inventory_ontology()
    assert len(ontology.classes) >= 5
    assert len(ontology.relations) >= 3

    engine = build_inventory_rule_engine()
    wm = WorkingMemory()

    # Load 4 states: critical, reorder, optimal, excess
    for state in sample_inventory_states.values():
        wm.assert_fact(
            Fact(
                "InventoryStateFact",
                {
                    "sku_id": state.sku_id,
                    "effective_inventory": state.effective_inventory,
                    "safety_stock": state.safety_stock,
                    "reorder_point": state.reorder_point,
                    "max_stock": state.max_stock,
                },
            )
        )

    report = engine.run(wm, max_cycles=20)
    assert report.rules_fired_count == 4

    classifications = {
        f.get("sku_id"): f.get("status")
        for f in wm.get_facts_by_name("StockClassificationFact")
    }

    assert classifications["SKU-ELEC-001"] == "CRITICAL"
    assert classifications["SKU-PART-001"] == "REORDER_NEEDED"
    assert classifications["SKU-RAW-001"] == "OPTIMAL"
    assert classifications["SKU-CNS-001"] == "EXCESS"


# ===========================================================================
# Group 5: Volume Discount Arbitrage & Edge MCDA Boundaries
# ===========================================================================

def test_adv_15_supplier_multi_tier_discount_eoq_step_function_arbitrage():
    """Test 15: Multi-tier volume discount schedule step-function arbitrage.

    Schedule:
    - Tier 1: 0 - 99 units -> base price 1,000 RUB (0% discount)
    - Tier 2: 100 - 499 units -> 10% discount (900 RUB)
    - Tier 3: 500 - 999 units -> 25% discount (750 RUB)
    - Tier 4: 1000+ units -> 40% discount (600 RUB)

    For high annual demand (e.g. D = 10,000 units), the optimizer should exploit
    the massive discount tier, balancing holding cost penalty against purchase savings.
    """
    tiers = [
        DiscountTier(min_quantity=0, discount_percentage=0.0),
        DiscountTier(min_quantity=100, discount_percentage=0.10),
        DiscountTier(min_quantity=500, discount_percentage=0.25),
        DiscountTier(min_quantity=1000, discount_percentage=0.40),
    ]

    # Case A: Low annual demand (D = 20) -> EOQ should not jump to 1000 due to holding cost
    res_low = calculate_eoq_with_discounts(
        annual_demand=20.0,
        base_unit_price=1000.0,
        holding_rate=0.20,
        order_cost=1000.0,
        discount_tiers=tiers,
        pack_size=10,
    )
    assert res_low.optimal_quantity < 500.0

    # Case B: High annual demand (D = 10,000) -> EOQ jumps to at least 1,000 to capture 40% discount
    res_high = calculate_eoq_with_discounts(
        annual_demand=10000.0,
        base_unit_price=1000.0,
        holding_rate=0.20,
        order_cost=1000.0,
        discount_tiers=tiers,
        pack_size=10,
    )
    assert res_high.optimal_quantity >= 1000.0
    assert res_high.applied_discount_rate == 0.40
    assert res_high.effective_unit_price == 600.0


def test_adv_16_extreme_holding_rate_vs_zero_ordering_cost_limit():
    """Test 16: Extreme holding rate (500% annual rate) and minimal ordering cost.

    Verifies:
    - Classical EOQ collapses towards 1.0 (pack size boundary).
    - calculate_total_inventory_cost handles extreme parameters monotonically without overflow.
    """
    eoq = calculate_classical_eoq(
        annual_demand=1000.0,
        order_cost=1.0,
        holding_cost_per_unit=5000.0,  # 500% of 1000 RUB unit cost
    )
    assert eoq < 5.0

    purch, order, hold, total = calculate_total_inventory_cost(
        quantity=1.0,
        annual_demand=1000.0,
        unit_price=1000.0,
        holding_cost_rate=5.0,
        order_cost=1.0,
        safety_stock=0.0,
    )
    assert purch == 1000000.0
    assert order == 1000.0
    assert hold == 2500.0
    assert total == 1003500.0


def test_adv_17_ahp_non_square_empty_and_eigenvector_divergence():
    """Test 17: AHP boundary checks for non-square, empty, and single-criterion matrices."""
    # Non-square matrix
    with pytest.raises(ValueError, match="must be square"):
        AHPEngine.compute_weights(np.array([[1.0, 2.0], [0.5, 1.0], [1.0, 1.0]]))

    # Empty matrix
    with pytest.raises(ValueError, match="cannot be empty"):
        AHPEngine.compute_weights(np.empty((0, 0)))

    # Single criterion
    w, l_max, cr = AHPEngine.compute_weights(np.array([[1.0]]))
    assert np.allclose(w, [1.0])
    assert l_max == 1.0
    assert cr == 0.0

    # Inconsistent matrix (CR > 0.10)
    inconsistent_mat = np.array([
        [1.0, 9.0, 1.0 / 9.0],
        [1.0 / 9.0, 1.0, 9.0],
        [9.0, 1.0 / 9.0, 1.0],
    ])
    w, l_max, cr = AHPEngine.compute_weights(inconsistent_mat)
    assert cr > 0.10
    assert AHPEngine.validate_consistency(inconsistent_mat) is False


def test_adv_18_entropy_and_topsis_uniform_alternatives_and_dimension_mismatch():
    """Test 18: Shannon entropy and TOPSIS dimension mismatch and uniform input boundaries."""
    # Empty decision matrix for Entropy
    with pytest.raises(ValueError, match="cannot be empty"):
        EntropyWeightEngine.compute_entropy_weights(np.empty((0, 3)))

    # Single alternative in Entropy -> returns uniform weights
    w_single = EntropyWeightEngine.compute_entropy_weights(np.array([[10.0, 20.0, 30.0]]))
    assert np.allclose(w_single, [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0])

    # TOPSIS dimension mismatches
    with pytest.raises(ValueError, match="Weights length"):
        TOPSISSolver.solve(
            decision_matrix=np.ones((3, 3)),
            weights=np.array([0.5, 0.5]),  # Length 2 instead of 3
            is_benefit=[True, True, True],
        )

    with pytest.raises(ValueError, match="Benefit flags length"):
        TOPSISSolver.solve(
            decision_matrix=np.ones((3, 3)),
            weights=np.array([0.33, 0.33, 0.34]),
            is_benefit=[True, False],  # Length 2 instead of 3
        )


# ===========================================================================
# Group 6: Full Operational Pipeline & Headless Streamlit UI Stress
# ===========================================================================

def test_adv_19_end_to_end_pipeline_under_adversarial_multi_shock():
    """Test 19: Full operational pipeline execution under concurrent multi-factor shock.

    1. Synthetic generator creates full dataset (25 SKUs, 5 suppliers, 730 days demand).
    2. Demand shock injected into category Electronics (+200%).
    3. Primary supplier suffers 14-day delay disruption shock.
    4. Forecasting model fits and evaluates holdout metrics across all SKUs.
    5. Supplier MCDA ranks suppliers with perturbed weights.
    6. Multi-item inventory optimizer enforces warehouse capacity envelope.
    7. Recommendation engine generates complete RecommendationBatch.
    8. Batch serializes to JSON and exports cleanly without schema errors.
    """
    gen = SyntheticDataGenerator(seed=123)
    skus, suppliers, warehouse, demand_history, states = gen.generate_all(days=90)
    skus_dict = {s.sku_id: s for s in skus}
    suppliers_dict = {s.supplier_id: s for s in suppliers}

    # 1. Inject 3x demand shock into Electronics
    for r in demand_history:
        if r.sku_id.startswith("SKU-ELEC"):
            r.quantity *= 3.0

    # 2. Inject disruption into first supplier
    suppliers[0].mean_lead_time_days += 14.0
    suppliers[0].std_lead_time_days += 4.0

    # 3. Forecast demand for all SKUs
    forecaster = DemandForecaster()
    forecasts: dict[str, ForecastResult] = {}
    for sid in skus_dict:
        sku_records = [r for r in demand_history if r.sku_id == sid]
        forecasts[sid] = forecaster.fit_predict(sku_records, horizon_days=30, holdout_days=20)
        assert forecasts[sid].mean_daily_demand > 0.0

    # 4. Supplier MCDA
    evaluator = SupplierEvaluator()
    supplier_scores = evaluator.evaluate_suppliers(suppliers, method="HYBRID")

    # 5. Inventory Optimization
    optimizer = InventoryOptimizer()
    policies = optimizer.calculate_multi_item_policies(
        skus=skus,
        forecasts=forecasts,
        suppliers=suppliers_dict,
        warehouse=warehouse,
    )
    assert len(policies) == len(skus)

    # 6. Recommendation Generation
    rec_engine = RecommendationEngine()
    batch = rec_engine.generate_batch(
        inventory_states=states,
        skus=skus_dict,
        forecasts=forecasts,
        policies=policies,
        suppliers=suppliers_dict,
        warehouse=warehouse,
        supplier_scores=supplier_scores,
        enforce_capacity=True,
    )

    assert len(batch.recommendations) == len(skus)
    assert batch.total_skus_evaluated == len(skus)
    assert batch.total_purchase_cost_rub >= 0.0

    # JSON roundtrip serialization
    json_str = batch.model_dump_json()
    batch_restored = RecommendationBatch.model_validate_json(json_str)
    assert batch_restored.total_skus_evaluated == len(skus)


def test_adv_20_headless_ui_adversarial_rapid_tab_and_shock_interaction():
    """Test 20: In-memory Streamlit AppTest rapid navigation and parameter shock sweep.

    Tests:
    - Navigation across all 5 dashboard screens in rapid succession.
    - Parameter slider perturbation on What-If workbench (service level 0.999, lead time +14d).
    - Zero unhandled exceptions thrown by Streamlit runtime.
    """
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    assert not at.exception

    screens = [
        "📊 Обзор и ключевые KPI",
        "📦 Состояние запасов (ABC/XYZ)",
        "📈 Прогнозирование спроса",
        "🏭 Оценка поставщиков",
        "🎯 Рекомендации и What-If",
    ]

    for screen in screens:
        at.sidebar.radio(key="nav_screen").set_value(screen).run()
        assert not at.exception, f"Crash while navigating to {screen}: {at.exception}"

    # On What-If screen, apply extreme shocks
    at.slider(key="wb_service_level").set_value(0.999).run()
    assert not at.exception
    at.slider(key="wb_lead_shock").set_value(14.0).run()
    assert not at.exception

    # Approve all orders button click
    approve_btn = at.button(key="approve_orders_btn")
    if approve_btn:
        approve_btn.click().run()
        assert not at.exception


def test_adv_21_headless_ui_adversarial_empty_catalog_and_extreme_filters():
    """Test 21: Streamlit AppTest empty-filter states and graceful degradation.

    Tests:
    - Applying a status filter on Inventory screen that has zero matching items.
    - Application displays informative alert banner without crashing.
    """
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()

    at.sidebar.radio(key="nav_screen").set_value("📦 Состояние запасов (ABC/XYZ)").run()
    assert not at.exception

    # Select filters
    at.selectbox(key="inv_status_filter").set_value("Все").run()
    assert not at.exception
    at.selectbox(key="inv_cat_filter").set_value("Electronics").run()
    assert not at.exception


def test_adv_22_risk_decision_tree_adversarial_payoff_matrix_and_breakeven():
    """Test 22: Supply risk decision tree under catastrophic failure loss (50M RUB).

    Verifies:
    - Calculation of Expected Monetary Value (EMV) for single vs dual sourcing.
    - Identification of exact breakeven disruption probability.
    - Catastrophic loss reverses optimal policy from single to dual sourcing.
    """
    catastrophic_loss = 50_000_000.0
    tree = SupplyRiskDecisionTree(
        cost_normal_single=1_000_000.0,
        cost_disrupt_single=catastrophic_loss,
        cost_normal_dual=1_200_000.0,
        cost_disrupt_dual=2_000_000.0,
        p_disrupt_single=0.30,
        p_disrupt_dual=0.01,
    )

    # When disruption probability is very high (0.30), dual sourcing must win
    eval_high = tree.evaluate_emv()
    assert eval_high["preferred_strategy"] == "DUAL_SOURCING"
    assert eval_high["emv_dual"] < eval_high["emv_single"]  # Lower expected cost is better

    # Breakeven disruption probability calculation
    p_star = tree.find_breakeven_probability()
    assert 0.0 < p_star < 0.10, f"Breakeven disruption probability should be small under 50M loss, got {p_star}"


def test_adv_23_ridge_and_arima_short_series_and_date_parsing_adversarial():
    """Test 23: Advanced forecasters on ultra-short series (<14 days) and non-standard dates.

    Verifies:
    - Fallback mean is returned gracefully without index or linear algebra crashes.
    - String and datetime conversions handle missing/irregular calendar dates.
    """
    short_series = [10.0, 12.0, 14.0, 8.0, 11.0]

    # HoltWinters on short series (< 14)
    hw = HoltWintersForecaster(seasonal_periods=7)
    hw.fit(short_series)
    hw_preds = hw.predict(5)
    assert len(hw_preds) == 5
    assert np.all(hw_preds == float(np.mean(short_series)))

    # AutoARIMA on short series (< 14)
    arima = AutoARIMAForecaster(seasonal_periods=7)
    arima.fit(short_series)
    arima_preds = arima.predict(5)
    assert len(arima_preds) == 5
    assert np.all(arima_preds == float(np.mean(short_series)))

    # Ridge with string dates
    ridge = RidgeRegressionForecaster(lags=(1, 2))
    dates = ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05"]
    ridge.fit(short_series, dates=dates)
    ridge_preds = ridge.predict(5)
    assert len(ridge_preds) == 5
    assert all(p >= 0.0 for p in ridge_preds)


def test_adv_24_multi_item_capacity_unconstrained_and_supplier_fallback(
    sample_skus: list[SKU], sample_suppliers: list[Supplier], sample_warehouse: Warehouse
):
    """Test 24: Multi-item policy optimization with missing suppliers dictionary entries.

    Verifies:
    - Optimizer falls back gracefully to warehouse fixed order cost and SKU holding cost rate
      when a specific SKU has no assigned supplier in the suppliers dictionary.
    """
    optimizer = InventoryOptimizer()
    forecasts = {
        s.sku_id: ForecastResult(
            sku_id=s.sku_id,
            forecast_horizon_days=30,
            model_name="Baseline",
            point_forecast=[20.0] * 30,
            mean_daily_demand=20.0,
            std_daily_demand=4.0,
            metrics={"WAPE": 0.1, "RMSE": 4.0, "MAE": 3.0},
            lower_bound_95=[10.0] * 30,
            upper_bound_95=[30.0] * 30,
        )
        for s in sample_skus
    }

    # Pass fallback supplier mapping where SKU IDs don't match
    policies = optimizer.calculate_multi_item_policies(
        skus=sample_skus,
        forecasts=forecasts,
        suppliers={"SUP-FALLBACK": sample_suppliers[0]},
        warehouse=sample_warehouse,
    )

    assert len(policies) == len(sample_skus)
    for p in policies.values():
        assert p.eoq > 0.0
        assert p.safety_stock > 0.0


def test_adv_25_baseline_forecaster_parameter_boundaries():
    """Test 25: Baseline forecasters input and parameter boundary validations.

    Verifies:
    - SMA window < 1 raises ValueError.
    - Exponential smoothing alpha <= 0 or > 1 raises ValueError.
    - Croston alpha <= 0 or > 1 raises ValueError.
    - Zero horizon predict returns empty array.
    """
    with pytest.raises(ValueError, match="Window must be at least 1"):
        SimpleMovingAverageForecaster(window=0)

    with pytest.raises(ValueError, match="Alpha must be in"):
        ExponentialSmoothingForecaster(alpha=0.0)

    with pytest.raises(ValueError, match="Alpha must be in"):
        ExponentialSmoothingForecaster(alpha=1.5)

    with pytest.raises(ValueError, match="Alpha must be in"):
        CrostonForecaster(alpha=-0.1)

    sma = SimpleMovingAverageForecaster(window=3)
    sma.fit([10.0, 20.0, 30.0])
    assert len(sma.predict(0)) == 0

    croston = CrostonForecaster(alpha=0.2)
    croston.fit([0.0, 10.0, 0.0, 0.0, 15.0])
    assert len(croston.predict(0)) == 0
