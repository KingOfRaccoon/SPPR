"""Unit tests for Pydantic v2 domain models and data validation."""

from datetime import date

import pytest
from pydantic import ValidationError

from inventory_dss.models.domain import (
    SKU,
    DemandRecord,
    DiscountTier,
    ForecastResult,
    InventoryState,
    OptimizationPlan,
    PurchaseOrder,
    Recommendation,
    Supplier,
    SupplierProfileType,
    Warehouse,
)


class TestSKUModel:
    """Tests for SKU domain entity validation and attributes."""

    def test_valid_sku_creation(self):
        sku = SKU(
            sku_id="SKU-TEST-001",
            name="Контроллер тестовый",
            category="Electronics",
            unit_price=15000.0,
            holding_cost_annual_rate=0.20,
            unit_volume_m3=0.005,
            unit_weight_kg=1.2,
            pack_size=2,
            abc_class="A",
            xyz_class="X",
        )
        assert sku.sku_id == "SKU-TEST-001"
        assert sku.category == "Electronics"
        assert sku.unit_price == 15000.0
        assert sku.pack_size == 2
        assert sku.abc_class == "A"
        assert sku.xyz_class == "X"

    def test_invalid_price_raises_validation_error(self):
        with pytest.raises(ValidationError):
            SKU(
                sku_id="SKU-TEST-002",
                name="Невалидный товар",
                category="Spare Parts",
                unit_price=-100.0,  # Negative price is forbidden
                unit_volume_m3=0.01,
                unit_weight_kg=1.0,
            )

    def test_zero_volume_raises_validation_error(self):
        with pytest.raises(ValidationError):
            SKU(
                sku_id="SKU-TEST-003",
                name="Нулевой объем",
                category="Raw Materials",
                unit_price=500.0,
                unit_volume_m3=0.0,  # Must be strictly positive
                unit_weight_kg=1.0,
            )

    def test_invalid_category_raises_validation_error(self):
        with pytest.raises(ValidationError):
            SKU(
                sku_id="SKU-TEST-004",
                name="Неизвестная категория",
                category="UnknownCategory",  # Not in allowed literals
                unit_price=500.0,
                unit_volume_m3=0.01,
                unit_weight_kg=1.0,
            )

    def test_invalid_pack_size_raises_validation_error(self):
        with pytest.raises(ValidationError):
            SKU(
                sku_id="SKU-TEST-005",
                name="Нулевая упаковка",
                category="Consumables",
                unit_price=100.0,
                unit_volume_m3=0.001,
                unit_weight_kg=0.1,
                pack_size=0,  # Must be >= 1
            )


class TestSupplierModel:
    """Tests for Supplier domain entity and reliability metrics."""

    def test_valid_supplier_creation(self):
        sup = Supplier(
            supplier_id="SUP-TEST-01",
            name="Тестовый поставщик",
            mean_lead_time_days=5.0,
            std_lead_time_days=1.0,
            on_time_delivery_rate=0.95,
            defect_rate=0.01,
            min_order_quantity=20,
            price_markup_factor=1.05,
            profile_type=SupplierProfileType.PREMIUM_RELIABLE,
        )
        assert sup.supplier_id == "SUP-TEST-01"
        assert sup.mean_lead_time_days == 5.0
        assert sup.on_time_delivery_rate == 0.95
        assert sup.min_order_quantity == 20

    def test_invalid_otif_rate_raises_error(self):
        with pytest.raises(ValidationError):
            Supplier(
                supplier_id="SUP-TEST-02",
                name="Сверхнадежный поставщик",
                mean_lead_time_days=3.0,
                std_lead_time_days=0.5,
                on_time_delivery_rate=1.5,  # Must be in [0, 1]
                defect_rate=0.02,
                min_order_quantity=10,
            )

    def test_invalid_negative_defect_rate_raises_error(self):
        with pytest.raises(ValidationError):
            Supplier(
                supplier_id="SUP-TEST-03",
                name="Отрицательный брак",
                mean_lead_time_days=4.0,
                std_lead_time_days=1.0,
                on_time_delivery_rate=0.90,
                defect_rate=-0.05,  # Forbidden
                min_order_quantity=10,
            )

    def test_discount_tiers_inclusion(self):
        tier1 = DiscountTier(min_quantity=50, discount_percentage=0.05)
        tier2 = DiscountTier(min_quantity=100, discount_percentage=0.10)
        sup = Supplier(
            supplier_id="SUP-TEST-04",
            name="Оптовый поставщик",
            mean_lead_time_days=10.0,
            std_lead_time_days=2.0,
            on_time_delivery_rate=0.88,
            defect_rate=0.02,
            min_order_quantity=50,
            discount_tiers=[tier1, tier2],
        )
        assert len(sup.discount_tiers) == 2
        assert sup.discount_tiers[1].discount_percentage == 0.10


class TestWarehouseModel:
    """Tests for Warehouse specifications and constraints."""

    def test_valid_warehouse_creation(self):
        wh = Warehouse(
            warehouse_id="WH-01",
            name="Основной склад",
            total_volume_capacity_m3=800.0,
            total_weight_capacity_kg=40000.0,
            fixed_order_cost=3000.0,
            target_service_level=0.95,
        )
        assert wh.total_volume_capacity_m3 == 800.0
        assert wh.target_service_level == 0.95

    def test_invalid_volume_raises_error(self):
        with pytest.raises(ValidationError):
            Warehouse(
                warehouse_id="WH-02",
                name="Отрицательный склад",
                total_volume_capacity_m3=-50.0,
                total_weight_capacity_kg=10000.0,
            )


class TestDemandRecordModel:
    """Tests for DemandRecord temporal entries."""

    def test_valid_demand_record(self):
        rec = DemandRecord(
            date=date(2025, 6, 15),
            sku_id="SKU-ELEC-001",
            quantity=24.5,
            is_promotional=True,
            is_weekend=False,
        )
        assert rec.quantity == 24.5
        assert rec.is_promotional is True

    def test_negative_demand_quantity_raises_error(self):
        with pytest.raises(ValidationError):
            DemandRecord(
                date=date(2025, 6, 15),
                sku_id="SKU-ELEC-001",
                quantity=-5.0,  # Negative demand is physically impossible
            )


class TestInventoryStateModel:
    """Tests for InventoryState snapshot and effective inventory computation."""

    def test_effective_inventory_standard_calculation(self):
        state = InventoryState(
            sku_id="SKU-ELEC-001",
            on_hand=100.0,
            on_order=50.0,
            allocated=20.0,
            backorders=10.0,
        )
        # Formula: on_hand + on_order - allocated - backorders = 100 + 50 - 20 - 10 = 120.0
        assert state.effective_inventory == 120.0

    def test_effective_inventory_with_zero_commitments(self):
        state = InventoryState(
            sku_id="SKU-ELEC-001",
            on_hand=75.0,
            on_order=0.0,
            allocated=0.0,
            backorders=0.0,
        )
        assert state.effective_inventory == 75.0

    def test_effective_inventory_negative_under_backorders(self):
        state = InventoryState(
            sku_id="SKU-PART-001",
            on_hand=10.0,
            on_order=0.0,
            allocated=5.0,
            backorders=20.0,
        )
        # 10 + 0 - 5 - 20 = -15.0
        assert state.effective_inventory == -15.0

    def test_computed_field_serialization(self):
        state = InventoryState(
            sku_id="SKU-RAW-001",
            on_hand=50.0,
            on_order=25.0,
            allocated=10.0,
            backorders=5.0,
        )
        dump = state.model_dump()
        assert "effective_inventory" in dump
        assert dump["effective_inventory"] == 60.0

    def test_negative_physical_on_hand_raises_error(self):
        with pytest.raises(ValidationError):
            InventoryState(
                sku_id="SKU-CNS-001",
                on_hand=-5.0,  # Physical stock cannot be negative
            )


class TestForecastAndOptimizationModels:
    """Tests for ForecastResult and OptimizationPlan schemas."""

    def test_valid_forecast_result(self):
        res = ForecastResult(
            sku_id="SKU-ELEC-001",
            forecast_horizon_days=30,
            point_forecast=[10.0] * 30,
            lower_bound_95=[7.0] * 30,
            upper_bound_95=[13.0] * 30,
            mean_daily_demand=10.0,
            std_daily_demand=2.1,
            metrics={"MAE": 1.45, "RMSE": 2.05, "WAPE": 0.145},
            model_name="HoltWinters",
        )
        assert res.forecast_horizon_days == 30
        assert len(res.point_forecast) == 30
        assert res.metrics["WAPE"] == 0.145

    def test_valid_optimization_plan(self):
        plan = OptimizationPlan(
            sku_id="SKU-ELEC-001",
            eoq=64.0,
            safety_stock=27.0,
            reorder_point=87.0,
            expected_annual_holding_cost=15200.0,
            expected_annual_ordering_cost=14800.0,
            expected_total_cost=30000.0,
        )
        assert plan.eoq == 64.0
        assert plan.reorder_point == 87.0
        assert plan.expected_total_cost == 30000.0


class TestRecommendationAndPurchaseOrderModels:
    """Tests for Recommendation and PurchaseOrder contracts."""

    def test_valid_recommendation_creation(self):
        rec = Recommendation(
            sku_id="SKU-ELEC-002",
            status="CRITICAL",
            current_effective_stock=15.0,
            reorder_point=65.0,
            safety_stock=35.0,
            order_needed=True,
            recommended_order_quantity=80.0,
            selected_supplier_id="SUP-PREMIUM",
            selected_supplier_name="ТехноСнаб Премиум",
            urgency="HIGH",
            rationale="Критический дефицит: остаток ниже страхового запаса",
            estimated_purchase_cost_rub=2720000.0,
            warehouse_volume_required_m3=2.0,
            warehouse_weight_required_kg=520.0,
        )
        assert rec.status == "CRITICAL"
        assert rec.urgency == "HIGH"
        assert rec.order_needed is True
        assert rec.recommended_order_quantity == 80.0

    def test_valid_purchase_order(self):
        order = PurchaseOrder(
            order_id="PO-2025-001",
            sku_id="SKU-ELEC-002",
            supplier_id="SUP-PREMIUM",
            quantity=80.0,
            unit_price=34000.0,
            total_cost=2720000.0,
            order_date=date(2025, 10, 1),
            expected_delivery_date=date(2025, 10, 5),
            status="APPROVED",
        )
        assert order.status == "APPROVED"
        assert order.total_cost == 2720000.0

    def test_invalid_zero_quantity_purchase_order_raises_error(self):
        with pytest.raises(ValidationError):
            PurchaseOrder(
                order_id="PO-2025-002",
                sku_id="SKU-ELEC-002",
                supplier_id="SUP-PREMIUM",
                quantity=0.0,  # Must be strictly positive
                unit_price=34000.0,
                total_cost=0.0,
                order_date=date(2025, 10, 1),
                expected_delivery_date=date(2025, 10, 5),
            )
