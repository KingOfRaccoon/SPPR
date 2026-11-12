"""Comprehensive unit tests for Replenishment Recommendation Engine.

Covers stock classification state machine, order sizing with MOQ and pack multiples,
supplier multi-criteria and emergency routing, capacity constraint enforcement,
and batch/health summary contracts.
"""

from __future__ import annotations

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
from inventory_dss.recommendations.engine import (
    RecommendationEngine,
)


@pytest.fixture
def base_sku() -> SKU:
    return SKU(
        sku_id="SKU-UNIT-001",
        name="Precision Industrial Sensor",
        category="Electronics",
        unit_price=1200.0,
        holding_cost_annual_rate=0.20,
        unit_volume_m3=0.005,
        unit_weight_kg=0.8,
        pack_size=6,
        abc_class="A",
        xyz_class="X",
    )


@pytest.fixture
def fast_supplier() -> Supplier:
    return Supplier(
        supplier_id="SUP-FAST",
        name="Express Local Partner",
        mean_lead_time_days=2.0,
        std_lead_time_days=0.2,
        on_time_delivery_rate=0.99,
        defect_rate=0.005,
        min_order_quantity=10,
        price_markup_factor=1.10,
        order_processing_cost=2500.0,
    )


@pytest.fixture
def primary_supplier() -> Supplier:
    return Supplier(
        supplier_id="SUP-PRIMARY",
        name="Global Prime Distributor",
        mean_lead_time_days=5.0,
        std_lead_time_days=0.8,
        on_time_delivery_rate=0.97,
        defect_rate=0.01,
        min_order_quantity=20,
        price_markup_factor=1.00,
        order_processing_cost=3500.0,
    )


@pytest.fixture
def test_warehouse() -> Warehouse:
    return Warehouse(
        warehouse_id="WH-TEST-01",
        name="Test Logistics Warehouse",
        total_volume_capacity_m3=500.0,
        total_weight_capacity_kg=25000.0,
        fixed_order_cost=3500.0,
        annual_capital_rate=0.18,
        target_service_level=0.95,
    )


class TestStockHealthClassification:
    """Tests for 4-tier state machine classification logic."""

    def test_exact_safety_stock_boundary_triggers_critical(self):
        engine = RecommendationEngine()
        status, urgency, order_needed, doi = engine.classify_stock(
            effective_stock=25.0,
            safety_stock=25.0,
            reorder_point=60.0,
            eoq=50.0,
            mean_daily_demand=10.0,
        )
        assert status == "CRITICAL"
        assert urgency == "HIGH"
        assert order_needed is True
        assert doi == 2.5

    def test_below_safety_stock_triggers_critical(self):
        engine = RecommendationEngine()
        status, urgency, order_needed, _ = engine.classify_stock(
            effective_stock=10.0,
            safety_stock=25.0,
            reorder_point=60.0,
            eoq=50.0,
            mean_daily_demand=10.0,
        )
        assert status == "CRITICAL"
        assert urgency == "HIGH"
        assert order_needed is True

    def test_low_days_of_inventory_triggers_critical_even_above_safety_stock(self):
        engine = RecommendationEngine(critical_doi_threshold=3.0)
        # SS = 15, stock = 20, but daily demand = 10 -> DOI = 2.0 days < 3.0
        status, urgency, order_needed, doi = engine.classify_stock(
            effective_stock=20.0,
            safety_stock=15.0,
            reorder_point=60.0,
            eoq=50.0,
            mean_daily_demand=10.0,
        )
        assert status == "CRITICAL"
        assert urgency == "HIGH"
        assert order_needed is True
        assert doi == 2.0

    def test_reorder_zone_classification(self):
        engine = RecommendationEngine()
        # SS = 20, ROP = 60, stock = 45, DOI = 4.5 >= 3.0
        status, urgency, order_needed, doi = engine.classify_stock(
            effective_stock=45.0,
            safety_stock=20.0,
            reorder_point=60.0,
            eoq=50.0,
            mean_daily_demand=10.0,
        )
        assert status == "REORDER_NEEDED"
        assert urgency == "MEDIUM"
        assert order_needed is True
        assert doi == 4.5

    def test_exact_reorder_point_boundary(self):
        engine = RecommendationEngine()
        status, urgency, order_needed, _ = engine.classify_stock(
            effective_stock=60.0,
            safety_stock=20.0,
            reorder_point=60.0,
            eoq=50.0,
            mean_daily_demand=10.0,
        )
        assert status == "REORDER_NEEDED"
        assert urgency == "MEDIUM"
        assert order_needed is True

    def test_optimal_stock_zone(self):
        engine = RecommendationEngine()
        # ROP = 60, stock = 100, max_stock = 60 + 2*50 = 160
        status, urgency, order_needed, doi = engine.classify_stock(
            effective_stock=100.0,
            safety_stock=20.0,
            reorder_point=60.0,
            eoq=50.0,
            mean_daily_demand=10.0,
        )
        assert status == "OPTIMAL"
        assert urgency == "NONE"
        assert order_needed is False
        assert doi == 10.0

    def test_excess_stock_by_max_stock_multiplier(self):
        engine = RecommendationEngine(excess_multiplier=2.0)
        # ROP = 60, EOQ = 50, max = 160, stock = 180
        status, urgency, order_needed, _ = engine.classify_stock(
            effective_stock=180.0,
            safety_stock=20.0,
            reorder_point=60.0,
            eoq=50.0,
            mean_daily_demand=10.0,
        )
        assert status == "EXCESS"
        assert urgency == "LOW"
        assert order_needed is False

    def test_excess_stock_by_doi_threshold(self):
        engine = RecommendationEngine(excess_doi_threshold=90.0)
        # Mean demand = 1.0, stock = 100 -> DOI = 100 > 90
        status, urgency, order_needed, doi = engine.classify_stock(
            effective_stock=100.0,
            safety_stock=10.0,
            reorder_point=30.0,
            eoq=200.0,
            mean_daily_demand=1.0,
        )
        assert status == "EXCESS"
        assert urgency == "LOW"
        assert order_needed is False
        assert doi == 100.0

    def test_negative_effective_stock_deep_backorders(self):
        engine = RecommendationEngine()
        status, urgency, order_needed, doi = engine.classify_stock(
            effective_stock=-30.0,
            safety_stock=20.0,
            reorder_point=60.0,
            eoq=50.0,
            mean_daily_demand=10.0,
        )
        assert status == "CRITICAL"
        assert urgency == "HIGH"
        assert order_needed is True
        assert doi < 0

    def test_zero_demand_sku_handling(self):
        engine = RecommendationEngine()
        _status, _urgency, order_needed, doi = engine.classify_stock(
            effective_stock=50.0,
            safety_stock=10.0,
            reorder_point=20.0,
            eoq=30.0,
            mean_daily_demand=0.0,
        )
        # When demand is 0 and stock > 0, stock is not critical or reorder
        assert doi == float("inf")
        assert not order_needed


class TestOrderSizingFormulas:
    """Tests for order sizing formulas, supplier MOQ, and pack multiples."""

    def test_target_stock_raw_sizing(self):
        engine = RecommendationEngine()
        # ROP = 60, EOQ = 40, Target = 100, Stock = 40 -> Raw = 60, pack = 1, MOQ = 1
        qty = engine.size_order(
            effective_stock=40.0,
            reorder_point=60.0,
            eoq=40.0,
            pack_size=1,
            moq=1,
        )
        assert qty == 60.0

    def test_supplier_moq_enforcement(self):
        engine = RecommendationEngine()
        # Raw requirement 25, but MOQ is 50 -> must order 50
        qty = engine.size_order(
            effective_stock=55.0,
            reorder_point=60.0,
            eoq=20.0,
            pack_size=1,
            moq=50,
        )
        assert qty == 50.0

    def test_pack_size_rounding_up(self):
        engine = RecommendationEngine()
        # Target raw = 45, pack size = 12 -> ceil(45/12)*12 = 48
        qty = engine.size_order(
            effective_stock=35.0,
            reorder_point=50.0,
            eoq=30.0,
            pack_size=12,
            moq=1,
        )
        assert qty == 48.0
        assert qty % 12 == 0

    def test_asymmetric_moq_and_pack_size_interaction(self):
        engine = RecommendationEngine()
        # Raw = 35, MOQ = 50, Pack = 24 -> max(35, 50)=50 -> ceil(50/24)*24 = 72
        qty = engine.size_order(
            effective_stock=10.0,
            reorder_point=25.0,
            eoq=35.0,
            pack_size=24,
            moq=50,
        )
        assert qty == 72.0
        assert qty >= 50
        assert qty % 24 == 0

    def test_deep_backorders_covered_by_sizing(self):
        engine = RecommendationEngine()
        # I_eff = -40, ROP = 60, EOQ = 50 -> Target = 110, Deficit = 110 - (-40) = 150
        qty = engine.size_order(
            effective_stock=-40.0,
            reorder_point=60.0,
            eoq=50.0,
            pack_size=10,
            moq=1,
        )
        assert qty >= 150.0


class TestSupplierAllocationAndEmergencySourcing:
    """Tests for supplier selection: TOPSIS for normal, express for critical."""

    def test_reorder_needed_routes_to_best_topsis(self, primary_supplier, fast_supplier):
        engine = RecommendationEngine()
        suppliers = {primary_supplier.supplier_id: primary_supplier, fast_supplier.supplier_id: fast_supplier}
        scores = {primary_supplier.supplier_id: 0.95, fast_supplier.supplier_id: 0.80}

        sel_sup, is_emergency = engine.select_supplier("REORDER_NEEDED", suppliers, scores)
        assert sel_sup.supplier_id == primary_supplier.supplier_id
        assert is_emergency is False

    def test_critical_state_routes_to_fastest_supplier(self, primary_supplier, fast_supplier):
        engine = RecommendationEngine()
        suppliers = {primary_supplier.supplier_id: primary_supplier, fast_supplier.supplier_id: fast_supplier}
        scores = {primary_supplier.supplier_id: 0.95, fast_supplier.supplier_id: 0.80}

        # Fast supplier has 2 days mean lead time vs 5 days for primary
        sel_sup, is_emergency = engine.select_supplier("CRITICAL", suppliers, scores)
        assert sel_sup.supplier_id == fast_supplier.supplier_id
        assert is_emergency is True

    def test_single_supplier_catalog_safe_fallback(self, primary_supplier):
        engine = RecommendationEngine()
        suppliers = {primary_supplier.supplier_id: primary_supplier}
        scores = {primary_supplier.supplier_id: 1.0}

        sel_sup, is_emergency = engine.select_supplier("CRITICAL", suppliers, scores)
        assert sel_sup.supplier_id == primary_supplier.supplier_id
        assert is_emergency is False

    def test_empty_suppliers_raises_error(self):
        engine = RecommendationEngine()
        with pytest.raises(ValueError, match="No suppliers available"):
            engine.select_supplier("CRITICAL", {}, {})


class TestRecommendationBatchAndSummaryContracts:
    """Tests for RecommendationBatch and StockHealthSummary data models."""

    def test_health_summary_computation(self, base_sku):
        engine = RecommendationEngine()
        recs = [
            Recommendation(
                sku_id=base_sku.sku_id,
                status="CRITICAL",
                current_effective_stock=10.0,
                reorder_point=50.0,
                safety_stock=20.0,
                order_needed=True,
                recommended_order_quantity=60.0,
                selected_supplier_id="SUP-FAST",
                selected_supplier_name="Fast",
                urgency="HIGH",
                rationale="Critical deficit",
                estimated_purchase_cost_rub=72000.0,
            ),
            Recommendation(
                sku_id="SKU-2",
                status="OPTIMAL",
                current_effective_stock=80.0,
                reorder_point=50.0,
                safety_stock=20.0,
                order_needed=False,
                recommended_order_quantity=0.0,
                selected_supplier_id="SUP-PRI",
                selected_supplier_name="Primary",
                urgency="NONE",
                rationale="Optimal",
            ),
        ]
        summary = engine.get_stock_health_summary(recs, {base_sku.sku_id: base_sku})
        assert summary.total_skus == 2
        assert summary.critical_skus == [base_sku.sku_id]
        assert summary.optimal_skus == ["SKU-2"]
        assert summary.critical_percentage == 50.0
        assert summary.optimal_percentage == 50.0
        assert 0.0 <= summary.health_score <= 100.0

    def test_batch_analytics_generation(
        self, base_sku, primary_supplier, fast_supplier, test_warehouse
    ):
        engine = RecommendationEngine()
        state = InventoryState(
            sku_id=base_sku.sku_id,
            on_hand=15.0,
            on_order=0.0,
        )
        forecast = ForecastResult(
            sku_id=base_sku.sku_id,
            forecast_horizon_days=30,
            point_forecast=[10.0] * 30,
            lower_bound_95=[5.0] * 30,
            upper_bound_95=[15.0] * 30,
            mean_daily_demand=10.0,
            std_daily_demand=2.0,
        )
        policy = OptimizationPlan(
            sku_id=base_sku.sku_id,
            eoq=50.0,
            safety_stock=25.0,
            reorder_point=65.0,
            expected_annual_holding_cost=500.0,
            expected_annual_ordering_cost=500.0,
            expected_total_cost=1000.0,
        )
        batch = engine.generate_batch(
            inventory_states=[state],
            skus={base_sku.sku_id: base_sku},
            forecasts={base_sku.sku_id: forecast},
            policies={base_sku.sku_id: policy},
            suppliers={primary_supplier.supplier_id: primary_supplier, fast_supplier.supplier_id: fast_supplier},
            warehouse=test_warehouse,
        )
        assert batch.total_skus_evaluated == 1
        assert batch.orders_needed_count == 1
        assert batch.total_recommended_units > 0
        assert batch.volume_utilization >= 0.0
        assert batch.batch_id.startswith("BATCH-")


class TestWarehouseCapacityContention:
    """Tests for warehouse capacity limitation and priority-aware trimming."""

    def test_orders_within_capacity_untrimmed(
        self, base_sku, primary_supplier, test_warehouse
    ):
        engine = RecommendationEngine()
        state = InventoryState(
            sku_id=base_sku.sku_id,
            on_hand=30.0,
            on_order=0.0,
        )
        forecast = ForecastResult(
            sku_id=base_sku.sku_id,
            forecast_horizon_days=30,
            point_forecast=[10.0] * 30,
            lower_bound_95=[5.0] * 30,
            upper_bound_95=[15.0] * 30,
            mean_daily_demand=10.0,
            std_daily_demand=2.0,
        )
        policy = OptimizationPlan(
            sku_id=base_sku.sku_id,
            eoq=50.0,
            safety_stock=20.0,
            reorder_point=60.0,
            expected_annual_holding_cost=500.0,
            expected_annual_ordering_cost=500.0,
            expected_total_cost=1000.0,
        )
        recs = engine.generate_recommendations(
            inventory_states=[state],
            skus={base_sku.sku_id: base_sku},
            forecasts={base_sku.sku_id: forecast},
            policies={base_sku.sku_id: policy},
            suppliers={primary_supplier.supplier_id: primary_supplier},
            warehouse=test_warehouse,
            enforce_capacity=True,
        )
        assert len(recs) == 1
        assert recs[0].order_needed is True
        assert recs[0].recommended_order_quantity >= 50.0
        assert "Capacity trimmed" not in (recs[0].rationale or "")

    def test_decision_rationale_model(self):
        from inventory_dss.recommendations.models import DecisionRationale

        rationale = DecisionRationale(
            status="CRITICAL",
            urgency="HIGH",
            order_needed=True,
            stock_diagnostic="Stockout imminent",
            supplier_selection_reason="Fastest express supplier selected",
            full_text="Status CRITICAL: stock below safety threshold",
        )
        assert rationale.status == "CRITICAL"
        assert rationale.urgency == "HIGH"
        assert rationale.order_needed is True
