"""Shared pytest fixtures for Inventory DSS test suite."""

from datetime import date, timedelta

import pytest

from inventory_dss.knowledge.ontology import DomainOntology, build_inventory_ontology
from inventory_dss.knowledge.rules import RuleEngine, WorkingMemory, build_inventory_rule_engine
from inventory_dss.models.domain import (
    SKU,
    ABCClass,
    DemandRecord,
    InventoryState,
    ProductCategory,
    StockStatus,
    Supplier,
    SupplierProfileType,
    Warehouse,
    XYZClass,
)


@pytest.fixture
def sample_skus() -> list[SKU]:
    return [
        SKU(
            sku_id="SKU-ELEC-001",
            name="Промышленный контроллер STM32",
            category=ProductCategory.ELECTRONICS.value,
            unit_price=18500.0,
            holding_cost_annual_rate=0.20,
            unit_volume_m3=0.004,
            unit_weight_kg=0.8,
            pack_size=1,
            abc_class=ABCClass.A.value,
            xyz_class=XYZClass.X.value,
            unit_cost=16000.0,
            stockout_penalty_per_unit=5000.0,
        ),
        SKU(
            sku_id="SKU-PART-001",
            name="Ротор насоса высокого давления",
            category=ProductCategory.SPARE_PARTS.value,
            unit_price=28000.0,
            holding_cost_annual_rate=0.22,
            unit_volume_m3=0.030,
            unit_weight_kg=14.0,
            pack_size=1,
            abc_class=ABCClass.B.value,
            xyz_class=XYZClass.Z.value,
            unit_cost=24000.0,
            stockout_penalty_per_unit=12000.0,
        ),
        SKU(
            sku_id="SKU-RAW-001",
            name="Лист стальной х/к 2.0 мм",
            category=ProductCategory.RAW_MATERIALS.value,
            unit_price=85000.0,
            holding_cost_annual_rate=0.18,
            unit_volume_m3=0.350,
            unit_weight_kg=450.0,
            pack_size=1,
            abc_class=ABCClass.A.value,
            xyz_class=XYZClass.X.value,
            unit_cost=78000.0,
            stockout_penalty_per_unit=25000.0,
        ),
        SKU(
            sku_id="SKU-CNS-001",
            name="Стретч-пленка машинная 23мкм",
            category=ProductCategory.CONSUMABLES.value,
            unit_price=1450.0,
            holding_cost_annual_rate=0.25,
            unit_volume_m3=0.015,
            unit_weight_kg=16.0,
            pack_size=6,
            abc_class=ABCClass.C.value,
            xyz_class=XYZClass.X.value,
            unit_cost=1200.0,
            stockout_penalty_per_unit=400.0,
        ),
    ]


@pytest.fixture
def sample_suppliers() -> list[Supplier]:
    return [
        Supplier(
            supplier_id="SUP-PREMIUM",
            name="ТехноСнаб Премиум",
            mean_lead_time_days=4.0,
            std_lead_time_days=0.5,
            on_time_delivery_rate=0.985,
            defect_rate=0.003,
            min_order_quantity=10,
            price_markup_factor=1.10,
            order_processing_cost=4000.0,
            profile_type=SupplierProfileType.PREMIUM_RELIABLE,
        ),
        Supplier(
            supplier_id="SUP-BUDGET",
            name="ГлобалТрейд Дискаунт",
            mean_lead_time_days=14.0,
            std_lead_time_days=4.0,
            on_time_delivery_rate=0.75,
            defect_rate=0.035,
            min_order_quantity=50,
            price_markup_factor=0.85,
            order_processing_cost=3000.0,
            profile_type=SupplierProfileType.BUDGET_VOLATILE,
        ),
        Supplier(
            supplier_id="SUP-LOCAL",
            name="Северо-Запад Экспресс",
            mean_lead_time_days=2.0,
            std_lead_time_days=0.3,
            on_time_delivery_rate=0.96,
            defect_rate=0.008,
            min_order_quantity=1,
            price_markup_factor=1.05,
            order_processing_cost=2500.0,
            profile_type=SupplierProfileType.LOCAL_EXPRESS,
        ),
    ]


@pytest.fixture
def sample_warehouse() -> Warehouse:
    return Warehouse(
        warehouse_id="WH-CENTRAL-01",
        name="Центральный распределительный склад",
        total_volume_capacity_m3=1000.0,
        total_weight_capacity_kg=50000.0,
        fixed_order_cost=3500.0,
        annual_capital_rate=0.18,
        target_service_level=0.95,
    )


@pytest.fixture
def sample_demand_records() -> list[DemandRecord]:
    base_date = date(2025, 1, 1)
    records = []
    quantities = [12.0, 15.0, 10.0, 18.0, 22.0, 5.0, 4.0, 14.0, 16.0, 13.0]
    for i, qty in enumerate(quantities):
        rec_date = base_date + timedelta(days=i)
        records.append(
            DemandRecord(
                date=rec_date,
                sku_id="SKU-ELEC-001",
                quantity=qty,
                is_weekend=(rec_date.weekday() >= 5),
            )
        )
    return records


@pytest.fixture
def sample_inventory_states() -> dict[str, InventoryState]:
    return {
        "critical": InventoryState(
            sku_id="SKU-ELEC-001",
            on_hand=25.0,
            on_order=10.0,
            allocated=5.0,
            backorders=0.0,
            safety_stock=40.0,
            reorder_point=80.0,
            max_stock=200.0,
            status=StockStatus.CRITICAL,
        ),
        "reorder": InventoryState(
            sku_id="SKU-PART-001",
            on_hand=50.0,
            on_order=0.0,
            allocated=5.0,
            backorders=0.0,
            safety_stock=20.0,
            reorder_point=60.0,
            max_stock=150.0,
            status=StockStatus.REORDER_NEEDED,
        ),
        "optimal": InventoryState(
            sku_id="SKU-RAW-001",
            on_hand=120.0,
            on_order=0.0,
            allocated=10.0,
            backorders=0.0,
            safety_stock=30.0,
            reorder_point=90.0,
            max_stock=250.0,
            status=StockStatus.OPTIMAL,
        ),
        "excess": InventoryState(
            sku_id="SKU-CNS-001",
            on_hand=600.0,
            on_order=100.0,
            allocated=20.0,
            backorders=0.0,
            safety_stock=50.0,
            reorder_point=150.0,
            max_stock=400.0,
            status=StockStatus.EXCESS,
        ),
    }


@pytest.fixture
def sample_ontology() -> DomainOntology:
    return build_inventory_ontology()


@pytest.fixture
def sample_rule_engine() -> RuleEngine:
    return build_inventory_rule_engine()


@pytest.fixture
def working_memory() -> WorkingMemory:
    return WorkingMemory()
