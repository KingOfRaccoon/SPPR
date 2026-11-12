"""Milestone 4 Empirical Challenger Stress & Edge-Case Verification Suite.

Authored by challenger_m4_1 (teamwork_challenger: Critic & Specialist).
Empirically stress-tests the Replenishment Recommendation Engine against:
1. Zero demand, fractional demand, and extreme impulse spikes.
2. Deep negative effective inventory (severe stockouts and large customer backorders).
3. Extreme warehouse capacity contention (capacity starvation, asymmetric bottlenecks, micro capacity).
4. Supplier catalog anomalies (single supplier, identical suppliers, MOQ exceeding warehouse capacity).
5. Massive catalog fuzzing (150 random SKUs with varied pack sizes, weights, volumes, and states).
6. Missing/partial inputs and structural contract invariants.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from inventory_dss.models.domain import (
    SKU,
    ForecastResult,
    InventoryState,
    OptimizationPlan,
    Recommendation,
    Supplier,
    Warehouse,
)
from inventory_dss.recommendations.engine import RecommendationEngine
from inventory_dss.recommendations.models import (
    RecommendationBatch,
    StockHealthSummary,
)

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def base_catalog() -> tuple[dict[str, SKU], dict[str, Supplier], Warehouse]:
    """Standard baseline catalog with 3 SKUs, 2 suppliers, and 1 warehouse."""
    skus = {
        "SKU-A": SKU(
            sku_id="SKU-A",
            name="Critical Component A",
            category="Electronics",
            unit_price=1000.0,
            unit_cost=800.0,
            holding_cost_annual_rate=0.20,
            unit_volume_m3=0.01,
            unit_weight_kg=1.0,
            pack_size=10,
            abc_class="A",
            xyz_class="X",
        ),
        "SKU-B": SKU(
            sku_id="SKU-B",
            name="Standard Component B",
            category="Spare Parts",
            unit_price=500.0,
            unit_cost=400.0,
            holding_cost_annual_rate=0.15,
            unit_volume_m3=0.05,
            unit_weight_kg=5.0,
            pack_size=5,
            abc_class="B",
            xyz_class="Y",
        ),
        "SKU-C": SKU(
            sku_id="SKU-C",
            name="Bulky Raw Material C",
            category="Raw Materials",
            unit_price=200.0,
            unit_cost=150.0,
            holding_cost_annual_rate=0.10,
            unit_volume_m3=0.5,
            unit_weight_kg=50.0,
            pack_size=2,
            abc_class="C",
            xyz_class="Z",
        ),
    }

    suppliers = {
        "SUP-FAST": Supplier(
            supplier_id="SUP-FAST",
            name="Express Local Partner",
            mean_lead_time_days=2.0,
            std_lead_time_days=0.2,
            on_time_delivery_rate=0.99,
            defect_rate=0.005,
            min_order_quantity=10,
            price_markup_factor=1.15,
            order_processing_cost=2000.0,
        ),
        "SUP-PRIME": Supplier(
            supplier_id="SUP-PRIME",
            name="Global Prime Distributor",
            mean_lead_time_days=7.0,
            std_lead_time_days=1.0,
            on_time_delivery_rate=0.96,
            defect_rate=0.01,
            min_order_quantity=20,
            price_markup_factor=1.00,
            order_processing_cost=3000.0,
        ),
    }

    warehouse = Warehouse(
        warehouse_id="WH-CENTRAL",
        name="Central Distribution Hub",
        total_volume_capacity_m3=100.0,
        total_weight_capacity_kg=10000.0,
        fixed_order_cost=2500.0,
        annual_capital_rate=0.18,
        target_service_level=0.95,
    )

    return skus, suppliers, warehouse


# =============================================================================
# 1. EXTREME DEMAND REGIMES & STOCHASTIC EDGES
# =============================================================================

class TestExtremeDemandRegimes:
    """Stress tests covering zero demand, fractional slow-movers, and impulse demand shocks."""

    def test_zero_daily_demand_across_all_stock_tiers(self):
        engine = RecommendationEngine()

        # 1. High stock -> DOI should be infinity, status OPTIMAL or EXCESS, no order needed
        status_high, urgency_high, order_high, doi_high = engine.classify_stock(
            effective_stock=100.0,
            safety_stock=10.0,
            reorder_point=20.0,
            eoq=30.0,
            mean_daily_demand=0.0,
        )
        assert doi_high == float("inf")
        assert not order_high
        assert status_high in ("OPTIMAL", "EXCESS")
        assert urgency_high in ("NONE", "LOW")

        # 2. Zero stock and zero demand -> effective_stock <= safety_stock (0 <= 10)
        status_zero, urgency_zero, order_zero, doi_zero = engine.classify_stock(
            effective_stock=0.0,
            safety_stock=10.0,
            reorder_point=20.0,
            eoq=30.0,
            mean_daily_demand=0.0,
        )
        assert doi_zero == 0.0
        assert order_zero is True
        assert status_zero == "CRITICAL"
        assert urgency_zero == "HIGH"

        # 3. Negative stock with zero demand
        status_neg, urgency_neg, order_neg, doi_neg = engine.classify_stock(
            effective_stock=-5.0,
            safety_stock=10.0,
            reorder_point=20.0,
            eoq=30.0,
            mean_daily_demand=0.0,
        )
        assert doi_neg == 0.0
        assert order_neg is True
        assert status_neg == "CRITICAL"
        assert urgency_neg == "HIGH"

    def test_extreme_demand_spike_triggers_critical_and_bounds_order(self, base_catalog):
        """Massive surge (e.g. 10,000 units/day) must collapse DOI and trigger emergency sourcing."""
        skus, suppliers, warehouse = base_catalog
        engine = RecommendationEngine(critical_doi_threshold=3.0)

        # Normal stock (100 units), but demand spikes to 5,000 units/day -> DOI = 0.02 days
        status, urgency, order_needed, doi = engine.classify_stock(
            effective_stock=100.0,
            safety_stock=20.0,
            reorder_point=50.0,
            eoq=200.0,
            mean_daily_demand=5000.0,
        )
        assert status == "CRITICAL"
        assert urgency == "HIGH"
        assert order_needed is True
        assert math.isclose(doi, 0.02, abs_tol=1e-4)

        # Full recommendation run with demand spike
        state = InventoryState(sku_id="SKU-A", on_hand=100.0, on_order=0.0)
        forecast = ForecastResult(
            sku_id="SKU-A",
            forecast_horizon_days=30,
            point_forecast=[5000.0] * 30,
            lower_bound_95=[4500.0] * 30,
            upper_bound_95=[5500.0] * 30,
            mean_daily_demand=5000.0,
            std_daily_demand=250.0,
        )
        policy = OptimizationPlan(
            sku_id="SKU-A",
            eoq=5000.0,
            safety_stock=1000.0,
            reorder_point=11000.0,
            expected_annual_holding_cost=5000.0,
            expected_annual_ordering_cost=5000.0,
            expected_total_cost=10000.0,
        )

        recs = engine.generate_recommendations(
            inventory_states=[state],
            skus=skus,
            forecasts={"SKU-A": forecast},
            policies={"SKU-A": policy},
            suppliers=suppliers,
            warehouse=warehouse,
            enforce_capacity=False,
        )
        assert len(recs) == 1
        rec = recs[0]
        assert rec.status == "CRITICAL"
        assert rec.order_needed is True
        assert rec.selected_supplier_id == "SUP-FAST"  # Emergency routing
        assert rec.recommended_order_quantity >= 15900.0  # ROP + EOQ - stock = 11000 + 5000 - 100 = 15900
        assert rec.recommended_order_quantity % skus["SKU-A"].pack_size == 0

    def test_fractional_micro_demand_slow_moving_items(self):
        """Micro demand (e.g. 0.001 units/day, 1 unit every 3 years) must classify 1 unit as EXCESS."""
        engine = RecommendationEngine(excess_doi_threshold=90.0)

        status, urgency, order_needed, doi = engine.classify_stock(
            effective_stock=2.0,
            safety_stock=0.1,
            reorder_point=0.5,
            eoq=1.0,
            mean_daily_demand=0.001,
        )
        assert doi == 2000.0  # 2000 days > 90 days
        assert status == "EXCESS"
        assert urgency == "LOW"
        assert order_needed is False


# =============================================================================
# 2. DEEP NEGATIVE EFFECTIVE INVENTORY (BACKORDERS & STOCKOUTS)
# =============================================================================

class TestDeepNegativeEffectiveInventory:
    """Stress tests covering massive negative effective inventory (backorders)."""

    def test_massive_backorder_sizing_and_discretization(self):
        engine = RecommendationEngine()

        # Severe backorder of -50,000 units
        effective_stock = -50000.0
        rop = 1000.0
        eoq = 2500.0
        pack = 24
        moq = 100

        qty = engine.size_order(
            effective_stock=effective_stock,
            reorder_point=rop,
            eoq=eoq,
            pack_size=pack,
            moq=moq,
        )

        expected_min = rop + eoq - effective_stock  # 1000 + 2500 - (-50000) = 53500
        assert qty >= expected_min
        assert qty % pack == 0
        assert qty >= moq
        assert qty == float(math.ceil(53500 / 24) * 24)  # 53520

    def test_health_summary_non_negative_valuation_under_deep_backorders(self, base_catalog):
        """StockHealthSummary total_on_hand_value_rub must strictly remain >= 0 even with negative inventory."""
        skus, _, _ = base_catalog
        engine = RecommendationEngine()

        recs = [
            Recommendation(
                sku_id="SKU-A",
                status="CRITICAL",
                current_effective_stock=-15000.0,
                reorder_point=200.0,
                safety_stock=100.0,
                order_needed=True,
                recommended_order_quantity=20000.0,
                selected_supplier_id="SUP-FAST",
                selected_supplier_name="Express",
                urgency="HIGH",
                rationale="Severe negative backorders",
                estimated_purchase_cost_rub=16000000.0,
            ),
            Recommendation(
                sku_id="SKU-B",
                status="CRITICAL",
                current_effective_stock=-500.0,
                reorder_point=50.0,
                safety_stock=20.0,
                order_needed=True,
                recommended_order_quantity=1000.0,
                selected_supplier_id="SUP-FAST",
                selected_supplier_name="Express",
                urgency="HIGH",
                rationale="Deficit",
                estimated_purchase_cost_rub=400000.0,
            ),
        ]

        summary = engine.get_stock_health_summary(recs, skus)
        assert summary.total_skus == 2
        assert summary.critical_skus == ["SKU-A", "SKU-B"]
        assert summary.total_on_hand_value_rub >= 0.0
        assert summary.total_on_hand_value_rub == 0.0  # Since all effective stocks are <= 0
        assert summary.critical_percentage == 100.0
        assert summary.health_score <= 25.0


# =============================================================================
# 3. EXTREME WAREHOUSE CAPACITY CONTENTION & BOTTLENECK STRESS
# =============================================================================

class TestWarehouseCapacityContentionStress:
    """Stress tests on warehouse envelope exhaustion, asymmetric bounds, and micro capacity."""

    def test_extreme_capacity_starvation_protects_critical_items(self, base_catalog):
        """Warehouse capacity = 0.5 m3, 50 kg. Critical item requires 0.6 m3, Reorder items require 50 m3.

        Invariants:
        1. Critical item quantity must NOT be trimmed (business continuity protection).
        2. Reorder items must be trimmed down to fit residual space or dropped to 0.
        3. No unhandled exceptions or NaN values.
        """
        skus, suppliers, _ = base_catalog
        engine = RecommendationEngine()

        tiny_warehouse = Warehouse(
            warehouse_id="WH-TINY",
            name="Micro Container",
            total_volume_capacity_m3=0.5,
            total_weight_capacity_kg=50.0,
            fixed_order_cost=1000.0,
            annual_capital_rate=0.18,
            target_service_level=0.95,
        )

        # SKU-A is CRITICAL: effective stock = 0, ROP = 20, EOQ = 40 -> Order = 60 units
        # Vol = 60 * 0.01 = 0.6 m3, Wt = 60 * 1.0 = 60 kg (exceeds tiny warehouse on its own)
        # SKU-B is REORDER_NEEDED: effective stock = 15, demand = 2.0 -> DOI = 7.5d (>= 3.0d)
        states = [
            InventoryState(sku_id="SKU-A", on_hand=0.0, on_order=0.0),
            InventoryState(sku_id="SKU-B", on_hand=15.0, on_order=0.0),
        ]
        forecasts = {
            "SKU-A": ForecastResult(
                sku_id="SKU-A", forecast_horizon_days=14, point_forecast=[10.0]*14,
                lower_bound_95=[5.0]*14, upper_bound_95=[15.0]*14,
                mean_daily_demand=10.0, std_daily_demand=2.0
            ),
            "SKU-B": ForecastResult(
                sku_id="SKU-B", forecast_horizon_days=14, point_forecast=[2.0]*14,
                lower_bound_95=[1.0]*14, upper_bound_95=[3.0]*14,
                mean_daily_demand=2.0, std_daily_demand=0.5  # DOI = 15/2 = 7.5 > 3.0
            ),
        }
        policies = {
            "SKU-A": OptimizationPlan(
                sku_id="SKU-A", eoq=40.0, safety_stock=10.0, reorder_point=20.0,
                expected_annual_holding_cost=500.0, expected_annual_ordering_cost=500.0,
                expected_total_cost=1000.0
            ),
            "SKU-B": OptimizationPlan(
                sku_id="SKU-B", eoq=20.0, safety_stock=5.0, reorder_point=20.0,
                expected_annual_holding_cost=300.0, expected_annual_ordering_cost=300.0,
                expected_total_cost=600.0
            ),
        }

        recs = engine.generate_recommendations(
            inventory_states=states,
            skus=skus,
            forecasts=forecasts,
            policies=policies,
            suppliers=suppliers,
            warehouse=tiny_warehouse,
            enforce_capacity=True,
        )

        rec_a = next(r for r in recs if r.sku_id == "SKU-A")
        rec_b = next(r for r in recs if r.sku_id == "SKU-B")

        # Critical item SKU-A is protected at unconstrained requirement (60 units)
        assert rec_a.status == "CRITICAL"
        assert rec_a.order_needed is True
        assert rec_a.recommended_order_quantity == 60.0

        # Reorder item SKU-B: since critical volume (0.6) > capacity (0.5), residual capacity is 0
        # Reorder item must be trimmed to 0.0 units
        assert rec_b.status == "REORDER_NEEDED"
        assert rec_b.recommended_order_quantity == 0.0
        assert rec_b.order_needed is False
        assert "Capacity trimmed" in rec_b.rationale

    def test_asymmetric_bottleneck_stress(self, base_catalog):
        """Warehouse has ample volume (10,000 m3) but severe weight limit (10 kg)."""
        skus, suppliers, _ = base_catalog
        engine = RecommendationEngine()

        asymmetric_wh = Warehouse(
            warehouse_id="WH-ASYM",
            name="Asymmetric Warehouse",
            total_volume_capacity_m3=10000.0,
            total_weight_capacity_kg=10.0,  # Only 10 kg allowed!
            fixed_order_cost=1000.0,
            annual_capital_rate=0.18,
            target_service_level=0.95,
        )

        # SKU-B is REORDER_NEEDED: effective stock = 15.0, demand = 2.0 -> DOI = 7.5d >= 3.0d
        # Unit weight is 5.0 kg, unit volume is 0.05 m3.
        # Unconstrained order: 45 units (225 kg) -> severely violates weight limit.
        states = [InventoryState(sku_id="SKU-B", on_hand=15.0, on_order=0.0)]
        forecasts = {
            "SKU-B": ForecastResult(
                sku_id="SKU-B", forecast_horizon_days=14, point_forecast=[2.0]*14,
                lower_bound_95=[1.0]*14, upper_bound_95=[3.0]*14,
                mean_daily_demand=2.0, std_daily_demand=0.5
            ),
        }
        policies = {
            "SKU-B": OptimizationPlan(
                sku_id="SKU-B", eoq=40.0, safety_stock=5.0, reorder_point=20.0,
                expected_annual_holding_cost=300.0, expected_annual_ordering_cost=300.0,
                expected_total_cost=600.0
            ),
        }

        recs = engine.generate_recommendations(
            inventory_states=states,
            skus=skus,
            forecasts=forecasts,
            policies=policies,
            suppliers=suppliers,
            warehouse=asymmetric_wh,
            enforce_capacity=True,
        )

        rec_b = recs[0]
        # Weight required must not exceed 10.0 kg + epsilon
        assert rec_b.warehouse_weight_required_kg <= 10.0 + 1e-3
        assert rec_b.recommended_order_quantity * skus["SKU-B"].unit_weight_kg <= 10.0 + 1e-3

    def test_micro_capacity_warehouse_does_not_crash(self, base_catalog):
        """Micro capacity warehouse (0.0001 m3 and 0.001 kg) must not crash or raise zero division."""
        skus, suppliers, _ = base_catalog
        engine = RecommendationEngine()

        micro_wh = Warehouse(
            warehouse_id="WH-MICRO",
            name="Microscopic Space",
            total_volume_capacity_m3=1e-4,
            total_weight_capacity_kg=1e-3,
            fixed_order_cost=1000.0,
            annual_capital_rate=0.18,
            target_service_level=0.95,
        )

        states = [InventoryState(sku_id="SKU-B", on_hand=15.0, on_order=0.0)]
        forecasts = {
            "SKU-B": ForecastResult(
                sku_id="SKU-B", forecast_horizon_days=14, point_forecast=[2.0]*14,
                lower_bound_95=[1.0]*14, upper_bound_95=[3.0]*14,
                mean_daily_demand=2.0, std_daily_demand=0.5
            ),
        }
        policies = {
            "SKU-B": OptimizationPlan(
                sku_id="SKU-B", eoq=40.0, safety_stock=5.0, reorder_point=20.0,
                expected_annual_holding_cost=300.0, expected_annual_ordering_cost=300.0,
                expected_total_cost=600.0
            ),
        }

        batch = engine.generate_batch(
            inventory_states=states,
            skus=skus,
            forecasts=forecasts,
            policies=policies,
            suppliers=suppliers,
            warehouse=micro_wh,
            enforce_capacity=True,
        )
        assert isinstance(batch, RecommendationBatch)
        assert batch.orders_needed_count == 0  # Trimmed to 0
        assert batch.total_recommended_units == 0.0

    def test_order_quantity_monotonicity_under_capacity_constraint(self, base_catalog):
        """Enforcing warehouse capacity can only decrease or preserve order quantities, never increase them."""
        skus, suppliers, _ = base_catalog
        engine = RecommendationEngine()

        medium_wh = Warehouse(
            warehouse_id="WH-MED",
            name="Medium Warehouse",
            total_volume_capacity_m3=5.0,
            total_weight_capacity_kg=500.0,
            fixed_order_cost=1500.0,
            annual_capital_rate=0.18,
            target_service_level=0.95,
        )

        states = [
            InventoryState(sku_id="SKU-A", on_hand=0.0, on_order=0.0),
            InventoryState(sku_id="SKU-B", on_hand=15.0, on_order=0.0),
            InventoryState(sku_id="SKU-C", on_hand=5.0, on_order=0.0),
        ]
        forecasts = {
            "SKU-A": ForecastResult(
                sku_id="SKU-A", forecast_horizon_days=14, point_forecast=[10.0]*14,
                lower_bound_95=[5.0]*14, upper_bound_95=[15.0]*14,
                mean_daily_demand=10.0, std_daily_demand=2.0
            ),
            "SKU-B": ForecastResult(
                sku_id="SKU-B", forecast_horizon_days=14, point_forecast=[2.0]*14,
                lower_bound_95=[1.0]*14, upper_bound_95=[3.0]*14,
                mean_daily_demand=2.0, std_daily_demand=0.5
            ),
            "SKU-C": ForecastResult(
                sku_id="SKU-C", forecast_horizon_days=14, point_forecast=[1.0]*14,
                lower_bound_95=[0.5]*14, upper_bound_95=[1.5]*14,
                mean_daily_demand=1.0, std_daily_demand=0.2
            ),
        }
        policies = {
            "SKU-A": OptimizationPlan(sku_id="SKU-A", eoq=40.0, safety_stock=10.0, reorder_point=20.0, expected_annual_holding_cost=500.0, expected_annual_ordering_cost=500.0, expected_total_cost=1000.0),
            "SKU-B": OptimizationPlan(sku_id="SKU-B", eoq=30.0, safety_stock=5.0, reorder_point=20.0, expected_annual_holding_cost=300.0, expected_annual_ordering_cost=300.0, expected_total_cost=600.0),
            "SKU-C": OptimizationPlan(sku_id="SKU-C", eoq=20.0, safety_stock=2.0, reorder_point=10.0, expected_annual_holding_cost=200.0, expected_annual_ordering_cost=200.0, expected_total_cost=400.0),
        }

        recs_unconstrained = engine.generate_recommendations(
            inventory_states=states, skus=skus, forecasts=forecasts, policies=policies,
            suppliers=suppliers, warehouse=medium_wh, enforce_capacity=False,
        )
        recs_constrained = engine.generate_recommendations(
            inventory_states=states, skus=skus, forecasts=forecasts, policies=policies,
            suppliers=suppliers, warehouse=medium_wh, enforce_capacity=True,
        )

        unconstrained_map = {r.sku_id: r.recommended_order_quantity for r in recs_unconstrained}
        constrained_map = {r.sku_id: r.recommended_order_quantity for r in recs_constrained}

        for sid, unconstrained_qty in unconstrained_map.items():
            assert constrained_map[sid] <= unconstrained_qty + 1e-4


# =============================================================================
# 4. SUPPLIER CATALOG ANOMALIES & ALLOCATION STRESS
# =============================================================================

class TestSupplierCatalogAnomalies:
    """Stress tests covering degenerate supplier pools and MOQ mismatches."""

    def test_single_supplier_catalog_fallback_under_critical(self, base_catalog):
        """When only 1 supplier is available, emergency routing must safely fall back without crash."""
        _, suppliers, _ = base_catalog
        engine = RecommendationEngine()

        single_sup = {"SUP-SOLE": suppliers["SUP-PRIME"].model_copy(update={"supplier_id": "SUP-SOLE"})}
        scores = {"SUP-SOLE": 1.0}

        sup, is_emergency = engine.select_supplier("CRITICAL", single_sup, scores)
        assert sup.supplier_id == "SUP-SOLE"
        assert is_emergency is False

    def test_identical_suppliers_maximum_entropy(self):
        """Multiple identical suppliers must produce valid selection deterministically."""
        engine = RecommendationEngine()

        sup_clone1 = Supplier(
            supplier_id="SUP-C1",
            name="Clone 1",
            mean_lead_time_days=5.0,
            std_lead_time_days=0.5,
            on_time_delivery_rate=0.95,
            defect_rate=0.01,
            min_order_quantity=20,
            price_markup_factor=1.0,
            order_processing_cost=2500.0,
        )
        sup_clone2 = Supplier(
            supplier_id="SUP-C2",
            name="Clone 2",
            mean_lead_time_days=5.0,
            std_lead_time_days=0.5,
            on_time_delivery_rate=0.95,
            defect_rate=0.01,
            min_order_quantity=20,
            price_markup_factor=1.0,
            order_processing_cost=2500.0,
        )
        id_suppliers = {"SUP-C1": sup_clone1, "SUP-C2": sup_clone2}

        # Sizing and supplier selection under identical criteria
        scores = engine.supplier_evaluator.evaluate_suppliers(list(id_suppliers.values()))
        sel_sup, _ = engine.select_supplier("REORDER_NEEDED", id_suppliers, scores)
        assert sel_sup.supplier_id in id_suppliers

    def test_supplier_moq_exceeds_warehouse_envelope(self, base_catalog):
        """Supplier MOQ = 5,000 units (requires 250 m3) while warehouse capacity is 50 m3.

        Capacity optimizer must scale down to admissible limit or drop to 0 rather than exceeding envelope.
        """
        skus, _, _ = base_catalog
        engine = RecommendationEngine()

        giant_moq_supplier = Supplier(
            supplier_id="SUP-GIANT",
            name="Giant Bulk Importer",
            mean_lead_time_days=30.0,
            std_lead_time_days=3.0,
            on_time_delivery_rate=0.90,
            defect_rate=0.02,
            min_order_quantity=5000,  # 5,000 * 0.05 m3 = 250 m3
            price_markup_factor=0.80,
            order_processing_cost=10000.0,
        )
        suppliers = {"SUP-GIANT": giant_moq_supplier}

        tight_wh = Warehouse(
            warehouse_id="WH-TIGHT",
            name="Tight Warehouse",
            total_volume_capacity_m3=50.0,  # Only 50 m3!
            total_weight_capacity_kg=5000.0,
            fixed_order_cost=2000.0,
            annual_capital_rate=0.18,
            target_service_level=0.95,
        )

        # SKU-B is REORDER_NEEDED: stock = 15.0, demand = 2.0 -> DOI = 7.5d >= 3.0d
        state = InventoryState(sku_id="SKU-B", on_hand=15.0, on_order=0.0)
        forecast = ForecastResult(
            sku_id="SKU-B", forecast_horizon_days=30, point_forecast=[2.0]*30,
            lower_bound_95=[1.0]*30, upper_bound_95=[3.0]*30,
            mean_daily_demand=2.0, std_daily_demand=0.5
        )
        policy = OptimizationPlan(
            sku_id="SKU-B", eoq=100.0, safety_stock=10.0, reorder_point=25.0,
            expected_annual_holding_cost=500.0, expected_annual_ordering_cost=500.0,
            expected_total_cost=1000.0
        )

        recs = engine.generate_recommendations(
            inventory_states=[state],
            skus=skus,
            forecasts={"SKU-B": forecast},
            policies={"SKU-B": policy},
            suppliers=suppliers,
            warehouse=tight_wh,
            enforce_capacity=True,
        )
        rec = recs[0]
        # Must not exceed warehouse volume of 50.0 m3
        assert rec.warehouse_volume_required_m3 <= 50.0 + 1e-4


# =============================================================================
# 5. MASSIVE CATALOG FUZZING (150 RANDOM SKUS)
# =============================================================================

class TestMassiveCatalogFuzzing:
    """Randomized property-based fuzz test across 150 SKUs with extreme randomized attributes."""

    def test_random_fuzz_150_skus_systemic_invariants(self):
        """Generate 150 synthetic SKUs with wide parameter distributions and verify systemic invariants."""
        rng = np.random.default_rng(42)
        n_skus = 150

        pack_choices = [1, 2, 4, 6, 10, 12, 24, 50, 100]
        categories = ["Electronics", "Spare Parts", "Raw Materials", "Consumables"]
        abc_classes = ["A", "B", "C"]
        xyz_classes = ["X", "Y", "Z"]

        fuzz_skus: dict[str, SKU] = {}
        fuzz_states: list[InventoryState] = []
        fuzz_forecasts: dict[str, ForecastResult] = {}
        fuzz_policies: dict[str, OptimizationPlan] = {}

        for i in range(n_skus):
            sid = f"SKU-FUZZ-{i:03d}"
            price = float(rng.uniform(10.0, 25000.0))
            vol = float(rng.uniform(0.0005, 1.5))
            wt = float(rng.uniform(0.05, 80.0))
            pack = int(rng.choice(pack_choices))

            fuzz_skus[sid] = SKU(
                sku_id=sid,
                name=f"Fuzz Product {i}",
                category=str(rng.choice(categories)),
                unit_price=round(price, 2),
                unit_cost=round(price * 0.75, 2),
                holding_cost_annual_rate=round(float(rng.uniform(0.10, 0.35)), 2),
                unit_volume_m3=round(vol, 4),
                unit_weight_kg=round(wt, 2),
                pack_size=pack,
                abc_class=str(rng.choice(abc_classes)),
                xyz_class=str(rng.choice(xyz_classes)),
            )

            # Valid InventoryState domain model: on_hand >= 0, backorders >= 0
            # If on_hand = 0 and backorders = 200 -> effective_inventory = -200 (deep negative!)
            on_hand = float(rng.uniform(0.0, 5000.0))
            on_order = float(rng.uniform(0.0, 1000.0))
            backorders = float(rng.uniform(0.0, 1000.0)) if rng.random() < 0.25 else 0.0

            fuzz_states.append(
                InventoryState(
                    sku_id=sid,
                    on_hand=round(on_hand, 1),
                    on_order=round(on_order, 1),
                    backorders=round(backorders, 1),
                )
            )

            mean_d = float(rng.uniform(0.0, 200.0))
            fuzz_forecasts[sid] = ForecastResult(
                sku_id=sid,
                forecast_horizon_days=30,
                point_forecast=[round(mean_d, 2)] * 30,
                lower_bound_95=[round(max(0.0, mean_d * 0.8), 2)] * 30,
                upper_bound_95=[round(mean_d * 1.2, 2)] * 30,
                mean_daily_demand=round(mean_d, 2),
                std_daily_demand=round(mean_d * 0.2, 2),
            )

            ss = float(rng.uniform(10.0, 500.0))
            rop = ss + float(rng.uniform(20.0, 1000.0))
            eoq = float(rng.uniform(50.0, 2500.0))
            fuzz_policies[sid] = OptimizationPlan(
                sku_id=sid,
                eoq=round(eoq, 1),
                safety_stock=round(ss, 1),
                reorder_point=round(rop, 1),
                expected_annual_holding_cost=1000.0,
                expected_annual_ordering_cost=1000.0,
                expected_total_cost=2000.0,
            )

        # 4 Diverse Suppliers
        fuzz_suppliers = {
            "SUP-LOCAL": Supplier(
                supplier_id="SUP-LOCAL",
                name="Local Fast Partner",
                mean_lead_time_days=2.0,
                std_lead_time_days=0.3,
                on_time_delivery_rate=0.98,
                defect_rate=0.005,
                min_order_quantity=5,
                price_markup_factor=1.12,
                order_processing_cost=1500.0,
            ),
            "SUP-REGIONAL": Supplier(
                supplier_id="SUP-REGIONAL",
                name="Regional Standard",
                mean_lead_time_days=6.0,
                std_lead_time_days=0.8,
                on_time_delivery_rate=0.96,
                defect_rate=0.01,
                min_order_quantity=20,
                price_markup_factor=1.00,
                order_processing_cost=2500.0,
            ),
            "SUP-GLOBAL": Supplier(
                supplier_id="SUP-GLOBAL",
                name="Global Low-Cost",
                mean_lead_time_days=18.0,
                std_lead_time_days=2.5,
                on_time_delivery_rate=0.91,
                defect_rate=0.025,
                min_order_quantity=100,
                price_markup_factor=0.88,
                order_processing_cost=5000.0,
            ),
            "SUP-SPECIALTY": Supplier(
                supplier_id="SUP-SPECIALTY",
                name="Specialty Certified",
                mean_lead_time_days=10.0,
                std_lead_time_days=1.2,
                on_time_delivery_rate=0.99,
                defect_rate=0.001,
                min_order_quantity=10,
                price_markup_factor=1.20,
                order_processing_cost=3500.0,
            ),
        }

        fuzz_warehouse = Warehouse(
            warehouse_id="WH-FUZZ-MEGA",
            name="Mega Distribution Facility",
            total_volume_capacity_m3=500.0,
            total_weight_capacity_kg=50000.0,
            fixed_order_cost=3000.0,
            annual_capital_rate=0.18,
            target_service_level=0.95,
        )

        engine = RecommendationEngine()

        # Execute Batch Pipeline
        batch = engine.generate_batch(
            inventory_states=fuzz_states,
            skus=fuzz_skus,
            forecasts=fuzz_forecasts,
            policies=fuzz_policies,
            suppliers=fuzz_suppliers,
            warehouse=fuzz_warehouse,
            enforce_capacity=True,
        )

        assert isinstance(batch, RecommendationBatch)
        assert batch.total_skus_evaluated == n_skus
        assert len(batch.recommendations) == n_skus

        # Invariant 1: Order quantity non-negativity and consistency with order_needed flag
        for r in batch.recommendations:
            assert r.recommended_order_quantity >= 0.0
            if r.order_needed:
                assert r.recommended_order_quantity > 0.0
            else:
                assert r.recommended_order_quantity == 0.0

            assert r.status in ("CRITICAL", "REORDER_NEEDED", "OPTIMAL", "EXCESS")
            assert r.urgency in ("HIGH", "MEDIUM", "LOW", "NONE")
            assert r.selected_supplier_id in fuzz_suppliers

            # Estimated costs and space requirements must be non-negative
            assert (r.estimated_purchase_cost_rub or 0.0) >= 0.0
            assert (r.warehouse_volume_required_m3 or 0.0) >= 0.0
            assert (r.warehouse_weight_required_kg or 0.0) >= 0.0

        # Invariant 2: Health Summary Distribution
        summary = engine.get_stock_health_summary(batch.recommendations, fuzz_skus)
        assert isinstance(summary, StockHealthSummary)
        assert summary.total_skus == n_skus

        # Percentage sum check (100% within rounding)
        pct_sum = (
            summary.critical_percentage
            + summary.reorder_percentage
            + summary.optimal_percentage
            + summary.excess_percentage
        )
        assert math.isclose(pct_sum, 100.0, abs_tol=0.5)

        # Health score bounds
        assert 0.0 <= summary.health_score <= 100.0
        assert summary.total_on_hand_value_rub >= 0.0
        assert summary.total_excess_value_rub >= 0.0


# =============================================================================
# 6. MISSING / PARTIAL DATA & CONTRACT ROBUSTNESS
# =============================================================================

class TestMissingDataAndContractRobustness:
    """Stress tests on partial dictionaries, missing policies, and empty collections."""

    def test_missing_policies_and_forecasts_graceful_fallbacks(self, base_catalog):
        """When policies and forecasts maps are empty, engine must use heuristic fallbacks without crashing."""
        skus, suppliers, warehouse = base_catalog
        engine = RecommendationEngine()

        states = [
            InventoryState(
                sku_id="SKU-A",
                on_hand=5.0,
                on_order=0.0,
                safety_stock=15.0,
                reorder_point=40.0,
            )
        ]

        recs = engine.generate_recommendations(
            inventory_states=states,
            skus=skus,
            forecasts={},  # Empty forecasts
            policies={},   # Empty policies
            suppliers=suppliers,
            warehouse=warehouse,
            enforce_capacity=True,
        )
        assert len(recs) == 1
        rec = recs[0]
        assert rec.status == "CRITICAL"
        assert rec.order_needed is True
        assert rec.recommended_order_quantity > 0

    def test_unmatched_sku_in_inventory_states_skipped(self, base_catalog):
        """Inventory states containing unknown SKU IDs must be skipped cleanly."""
        skus, suppliers, warehouse = base_catalog
        engine = RecommendationEngine()

        states = [
            InventoryState(sku_id="SKU-UNKNOWN-999", on_hand=10.0, on_order=0.0),
            InventoryState(sku_id="SKU-A", on_hand=5.0, on_order=0.0),
        ]

        recs = engine.generate_recommendations(
            inventory_states=states,
            skus=skus,
            forecasts={},
            policies={},
            suppliers=suppliers,
            warehouse=warehouse,
        )
        assert len(recs) == 1
        assert recs[0].sku_id == "SKU-A"

    def test_empty_catalog_and_empty_suppliers_invariants(self, base_catalog):
        """Empty input collections must yield empty results without raising errors."""
        skus, suppliers, warehouse = base_catalog
        engine = RecommendationEngine()

        assert engine.generate_recommendations([], skus, {}, {}, suppliers, warehouse) == []
        assert engine.generate_recommendations([InventoryState(sku_id="SKU-A", on_hand=10)], skus, {}, {}, {}, warehouse) == []


# =============================================================================
# 7. STOCK HEALTH SUMMARY & XAI RATIONALE INVARIANTS
# =============================================================================

class TestStockHealthAndXAIRationaleInvariants:
    """Tests for edge condition scoring in StockHealthSummary and XAI DecisionRationale."""

    def test_health_summary_boundary_scores(self):
        """Verify health score mathematical bounds under all-critical, all-excess, and empty portfolios."""
        # 1. 100% Critical
        summary_crit = StockHealthSummary(
            total_skus=10,
            critical_skus=[f"SKU-{i}" for i in range(10)],
        )
        # Score = 100 - (100 * 0.8) = 20.0
        assert summary_crit.health_score == 20.0

        # 2. 100% Optimal
        summary_opt = StockHealthSummary(
            total_skus=10,
            optimal_skus=[f"SKU-{i}" for i in range(10)],
        )
        # Score = 100 - 0 = 100.0
        assert summary_opt.health_score == 100.0

        # 3. 100% Excess
        summary_excess = StockHealthSummary(
            total_skus=10,
            excess_skus=[f"SKU-{i}" for i in range(10)],
        )
        # Score = 100 - (100 * 0.4) = 60.0
        assert summary_excess.health_score == 60.0

        # 4. Empty Portfolio (0 SKUs)
        summary_empty = StockHealthSummary(total_skus=0)
        assert summary_empty.health_score == 100.0
        assert summary_empty.critical_percentage == 0.0

    def test_recommendation_rationale_xai_transparency(self, base_catalog):
        """Every generated recommendation must possess non-empty explainable AI rationale."""
        skus, suppliers, warehouse = base_catalog
        engine = RecommendationEngine()

        states = [
            InventoryState(sku_id="SKU-A", on_hand=0.0, on_order=0.0),      # CRITICAL
            InventoryState(sku_id="SKU-B", on_hand=15.0, on_order=0.0),     # REORDER_NEEDED
            InventoryState(sku_id="SKU-C", on_hand=50.0, on_order=0.0),     # OPTIMAL/EXCESS
        ]
        forecasts = {
            "SKU-A": ForecastResult(sku_id="SKU-A", forecast_horizon_days=14, point_forecast=[10.0]*14, lower_bound_95=[5.0]*14, upper_bound_95=[15.0]*14, mean_daily_demand=10.0, std_daily_demand=2.0),
            "SKU-B": ForecastResult(sku_id="SKU-B", forecast_horizon_days=14, point_forecast=[2.0]*14, lower_bound_95=[1.0]*14, upper_bound_95=[3.0]*14, mean_daily_demand=2.0, std_daily_demand=0.5),
            "SKU-C": ForecastResult(sku_id="SKU-C", forecast_horizon_days=14, point_forecast=[0.5]*14, lower_bound_95=[0.2]*14, upper_bound_95=[0.8]*14, mean_daily_demand=0.5, std_daily_demand=0.1),
        }
        policies = {
            "SKU-A": OptimizationPlan(sku_id="SKU-A", eoq=40.0, safety_stock=10.0, reorder_point=20.0, expected_annual_holding_cost=500.0, expected_annual_ordering_cost=500.0, expected_total_cost=1000.0),
            "SKU-B": OptimizationPlan(sku_id="SKU-B", eoq=30.0, safety_stock=5.0, reorder_point=20.0, expected_annual_holding_cost=300.0, expected_annual_ordering_cost=300.0, expected_total_cost=600.0),
            "SKU-C": OptimizationPlan(sku_id="SKU-C", eoq=10.0, safety_stock=2.0, reorder_point=5.0, expected_annual_holding_cost=100.0, expected_annual_ordering_cost=100.0, expected_total_cost=200.0),
        }

        recs = engine.generate_recommendations(
            inventory_states=states, skus=skus, forecasts=forecasts, policies=policies,
            suppliers=suppliers, warehouse=warehouse, enforce_capacity=True,
        )

        for r in recs:
            assert r.rationale is not None
            assert len(r.rationale.strip()) > 10
            assert f"Status {r.status}" in r.rationale
