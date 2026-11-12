"""Synthetic Data Generator for Inventory Decision Support System.

Generates 100% reproducible supply chain data:
- 25 SKUs across 4 categories (Electronics, Spare Parts, Raw Materials, Consumables)
- Strict ABC classification (~80/15/5 revenue share)
- XYZ demand variability categorization (smooth, seasonal/trend, intermittent)
- 730 days of daily demand series with trends, annual/weekly harmonics, promotions, and Croston noise
- 5 distinct supplier archetypes
- Central warehouse capacity parameters
- Baseline inventory snapshots
"""

from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from inventory_dss.config import (
    DEFAULT_ANNUAL_CAPITAL_RATE,
    DEFAULT_FIXED_ORDER_COST_RUB,
    DEFAULT_SERVICE_LEVEL,
    DEFAULT_WAREHOUSE_ID,
    DEFAULT_WAREHOUSE_NAME,
    DEFAULT_WAREHOUSE_VOLUME_M3,
    DEFAULT_WAREHOUSE_WEIGHT_KG,
    DEMAND_HISTORY_DAYS,
    RANDOM_SEED,
    SYNTHETIC_DATA_DIR,
)
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

# Definition of 25 baseline catalog items
CATALOG_SPECS: list[dict] = [
    # Electronics (6 items)
    {
        "sku_id": "SKU-ELEC-001",
        "name": "Промышленный контроллер STM32",
        "category": ProductCategory.ELECTRONICS.value,
        "unit_price": 18500.0,
        "unit_cost": 16000.0,
        "holding_cost_annual_rate": 0.20,
        "unit_volume_m3": 0.004,
        "unit_weight_kg": 0.8,
        "pack_size": 1,
        "stockout_penalty_per_unit": 5000.0,
        "target_abc": ABCClass.A.value,
        "target_xyz": XYZClass.X.value,
        "base_demand": 13.5,
        "trend_slope": 0.002,
        "seasonal_amp": 0.05,
        "is_intermittent": False,
    },
    {
        "sku_id": "SKU-ELEC-002",
        "name": "Модуль инвертора 5.5 кВт",
        "category": ProductCategory.ELECTRONICS.value,
        "unit_price": 34000.0,
        "unit_cost": 30000.0,
        "holding_cost_annual_rate": 0.20,
        "unit_volume_m3": 0.025,
        "unit_weight_kg": 6.5,
        "pack_size": 1,
        "stockout_penalty_per_unit": 10000.0,
        "target_abc": ABCClass.A.value,
        "target_xyz": XYZClass.Y.value,
        "base_demand": 8.0,
        "trend_slope": 0.003,
        "seasonal_amp": 0.20,
        "is_intermittent": False,
    },
    {
        "sku_id": "SKU-ELEC-003",
        "name": "Датчик давления 4-20мА",
        "category": ProductCategory.ELECTRONICS.value,
        "unit_price": 6200.0,
        "unit_cost": 5300.0,
        "holding_cost_annual_rate": 0.20,
        "unit_volume_m3": 0.002,
        "unit_weight_kg": 0.4,
        "pack_size": 5,
        "stockout_penalty_per_unit": 1800.0,
        "target_abc": ABCClass.B.value,
        "target_xyz": XYZClass.X.value,
        "base_demand": 7.0,
        "trend_slope": 0.001,
        "seasonal_amp": 0.05,
        "is_intermittent": False,
    },
    {
        "sku_id": "SKU-ELEC-004",
        "name": "Оптический энкодер 1024 имп",
        "category": ProductCategory.ELECTRONICS.value,
        "unit_price": 9800.0,
        "unit_cost": 8500.0,
        "holding_cost_annual_rate": 0.20,
        "unit_volume_m3": 0.003,
        "unit_weight_kg": 0.5,
        "pack_size": 2,
        "stockout_penalty_per_unit": 2800.0,
        "target_abc": ABCClass.B.value,
        "target_xyz": XYZClass.Y.value,
        "base_demand": 5.5,
        "trend_slope": 0.001,
        "seasonal_amp": 0.15,
        "is_intermittent": False,
    },
    {
        "sku_id": "SKU-ELEC-005",
        "name": "Блок питания 24В 10А DIN",
        "category": ProductCategory.ELECTRONICS.value,
        "unit_price": 4100.0,
        "unit_cost": 3500.0,
        "holding_cost_annual_rate": 0.20,
        "unit_volume_m3": 0.005,
        "unit_weight_kg": 1.1,
        "pack_size": 4,
        "stockout_penalty_per_unit": 1200.0,
        "target_abc": ABCClass.B.value,
        "target_xyz": XYZClass.X.value,
        "base_demand": 8.0,
        "trend_slope": 0.001,
        "seasonal_amp": 0.05,
        "is_intermittent": False,
    },
    {
        "sku_id": "SKU-ELEC-006",
        "name": "Сенсорная панель HMI 10\"",
        "category": ProductCategory.ELECTRONICS.value,
        "unit_price": 42000.0,
        "unit_cost": 37000.0,
        "holding_cost_annual_rate": 0.20,
        "unit_volume_m3": 0.015,
        "unit_weight_kg": 2.2,
        "pack_size": 1,
        "stockout_penalty_per_unit": 12000.0,
        "target_abc": ABCClass.A.value,
        "target_xyz": XYZClass.Y.value,
        "base_demand": 6.5,
        "trend_slope": 0.002,
        "seasonal_amp": 0.22,
        "is_intermittent": False,
    },
    # Spare Parts (7 items - sporadic / intermittent Croston patterns)
    {
        "sku_id": "SKU-PART-001",
        "name": "Ротор насоса высокого давления",
        "category": ProductCategory.SPARE_PARTS.value,
        "unit_price": 28000.0,
        "unit_cost": 24000.0,
        "holding_cost_annual_rate": 0.22,
        "unit_volume_m3": 0.030,
        "unit_weight_kg": 14.0,
        "pack_size": 1,
        "stockout_penalty_per_unit": 12000.0,
        "target_abc": ABCClass.B.value,
        "target_xyz": XYZClass.Z.value,
        "base_demand": 0.0,
        "trend_slope": 0.0,
        "seasonal_amp": 0.0,
        "is_intermittent": True,
        "intermittent_prob": 0.15,
        "intermittent_lambda": 2.0,
    },
    {
        "sku_id": "SKU-PART-002",
        "name": "Комплект уплотнений PTFE",
        "category": ProductCategory.SPARE_PARTS.value,
        "unit_price": 1850.0,
        "unit_cost": 1500.0,
        "holding_cost_annual_rate": 0.22,
        "unit_volume_m3": 0.001,
        "unit_weight_kg": 0.1,
        "pack_size": 10,
        "stockout_penalty_per_unit": 600.0,
        "target_abc": ABCClass.C.value,
        "target_xyz": XYZClass.Z.value,
        "base_demand": 0.0,
        "trend_slope": 0.0,
        "seasonal_amp": 0.0,
        "is_intermittent": True,
        "intermittent_prob": 0.14,
        "intermittent_lambda": 2.0,
    },
    {
        "sku_id": "SKU-PART-003",
        "name": "Подшипник шпиндельный прецизионный",
        "category": ProductCategory.SPARE_PARTS.value,
        "unit_price": 12400.0,
        "unit_cost": 10500.0,
        "holding_cost_annual_rate": 0.22,
        "unit_volume_m3": 0.003,
        "unit_weight_kg": 1.8,
        "pack_size": 2,
        "stockout_penalty_per_unit": 4000.0,
        "target_abc": ABCClass.B.value,
        "target_xyz": XYZClass.Z.value,
        "base_demand": 0.0,
        "trend_slope": 0.0,
        "seasonal_amp": 0.0,
        "is_intermittent": True,
        "intermittent_prob": 0.15,
        "intermittent_lambda": 2.2,
    },
    {
        "sku_id": "SKU-PART-004",
        "name": "Клапан электромагнитный DN25",
        "category": ProductCategory.SPARE_PARTS.value,
        "unit_price": 8900.0,
        "unit_cost": 7600.0,
        "holding_cost_annual_rate": 0.22,
        "unit_volume_m3": 0.006,
        "unit_weight_kg": 3.2,
        "pack_size": 1,
        "stockout_penalty_per_unit": 2600.0,
        "target_abc": ABCClass.B.value,
        "target_xyz": XYZClass.Y.value,
        "base_demand": 2.5,
        "trend_slope": 0.0,
        "seasonal_amp": 0.18,
        "is_intermittent": False,
    },
    {
        "sku_id": "SKU-PART-005",
        "name": "Шестерня коническая редуктора",
        "category": ProductCategory.SPARE_PARTS.value,
        "unit_price": 16500.0,
        "unit_cost": 14000.0,
        "holding_cost_annual_rate": 0.22,
        "unit_volume_m3": 0.012,
        "unit_weight_kg": 8.5,
        "pack_size": 1,
        "stockout_penalty_per_unit": 5500.0,
        "target_abc": ABCClass.B.value,
        "target_xyz": XYZClass.Z.value,
        "base_demand": 0.0,
        "trend_slope": 0.0,
        "seasonal_amp": 0.0,
        "is_intermittent": True,
        "intermittent_prob": 0.12,
        "intermittent_lambda": 1.8,
    },
    {
        "sku_id": "SKU-PART-006",
        "name": "Манжета армированная 50х72",
        "category": ProductCategory.SPARE_PARTS.value,
        "unit_price": 450.0,
        "unit_cost": 350.0,
        "holding_cost_annual_rate": 0.22,
        "unit_volume_m3": 0.0005,
        "unit_weight_kg": 0.05,
        "pack_size": 20,
        "stockout_penalty_per_unit": 150.0,
        "target_abc": ABCClass.C.value,
        "target_xyz": XYZClass.Z.value,
        "base_demand": 0.0,
        "trend_slope": 0.0,
        "seasonal_amp": 0.0,
        "is_intermittent": True,
        "intermittent_prob": 0.15,
        "intermittent_lambda": 3.0,
    },
    {
        "sku_id": "SKU-PART-007",
        "name": "Фильтроэлемент гидравлический",
        "category": ProductCategory.SPARE_PARTS.value,
        "unit_price": 3200.0,
        "unit_cost": 2700.0,
        "holding_cost_annual_rate": 0.22,
        "unit_volume_m3": 0.008,
        "unit_weight_kg": 1.4,
        "pack_size": 4,
        "stockout_penalty_per_unit": 1000.0,
        "target_abc": ABCClass.C.value,
        "target_xyz": XYZClass.Y.value,
        "base_demand": 2.2,
        "trend_slope": 0.0,
        "seasonal_amp": 0.20,
        "is_intermittent": False,
    },
    # Raw Materials (6 items - heavy / large volume)
    {
        "sku_id": "SKU-RAW-001",
        "name": "Лист стальной х/к 2.0 мм",
        "category": ProductCategory.RAW_MATERIALS.value,
        "unit_price": 85000.0,
        "unit_cost": 78000.0,
        "holding_cost_annual_rate": 0.18,
        "unit_volume_m3": 0.350,
        "unit_weight_kg": 450.0,
        "pack_size": 1,
        "stockout_penalty_per_unit": 25000.0,
        "target_abc": ABCClass.A.value,
        "target_xyz": XYZClass.X.value,
        "base_demand": 4.1,
        "trend_slope": 0.001,
        "seasonal_amp": 0.05,
        "is_intermittent": False,
    },
    {
        "sku_id": "SKU-RAW-002",
        "name": "Пруток медный d=30 мм",
        "category": ProductCategory.RAW_MATERIALS.value,
        "unit_price": 62000.0,
        "unit_cost": 55000.0,
        "holding_cost_annual_rate": 0.18,
        "unit_volume_m3": 0.080,
        "unit_weight_kg": 180.0,
        "pack_size": 1,
        "stockout_penalty_per_unit": 18000.0,
        "target_abc": ABCClass.A.value,
        "target_xyz": XYZClass.X.value,
        "base_demand": 4.8,
        "trend_slope": 0.001,
        "seasonal_amp": 0.05,
        "is_intermittent": False,
    },
    {
        "sku_id": "SKU-RAW-003",
        "name": "Гранулят полиамидный PA6",
        "category": ProductCategory.RAW_MATERIALS.value,
        "unit_price": 7800.0,
        "unit_cost": 6700.0,
        "holding_cost_annual_rate": 0.18,
        "unit_volume_m3": 0.045,
        "unit_weight_kg": 25.0,
        "pack_size": 10,
        "stockout_penalty_per_unit": 2300.0,
        "target_abc": ABCClass.B.value,
        "target_xyz": XYZClass.X.value,
        "base_demand": 5.0,
        "trend_slope": 0.0,
        "seasonal_amp": 0.05,
        "is_intermittent": False,
    },
    {
        "sku_id": "SKU-RAW-004",
        "name": "Профиль алюминиевый анодированный",
        "category": ProductCategory.RAW_MATERIALS.value,
        "unit_price": 14200.0,
        "unit_cost": 12200.0,
        "holding_cost_annual_rate": 0.18,
        "unit_volume_m3": 0.120,
        "unit_weight_kg": 45.0,
        "pack_size": 5,
        "stockout_penalty_per_unit": 4200.0,
        "target_abc": ABCClass.B.value,
        "target_xyz": XYZClass.Y.value,
        "base_demand": 3.0,
        "trend_slope": 0.0,
        "seasonal_amp": 0.20,
        "is_intermittent": False,
    },
    {
        "sku_id": "SKU-RAW-005",
        "name": "Труба нержавеющая 32х2",
        "category": ProductCategory.RAW_MATERIALS.value,
        "unit_price": 11500.0,
        "unit_cost": 9800.0,
        "holding_cost_annual_rate": 0.18,
        "unit_volume_m3": 0.060,
        "unit_weight_kg": 32.0,
        "pack_size": 5,
        "stockout_penalty_per_unit": 3400.0,
        "target_abc": ABCClass.B.value,
        "target_xyz": XYZClass.X.value,
        "base_demand": 3.8,
        "trend_slope": 0.0,
        "seasonal_amp": 0.05,
        "is_intermittent": False,
    },
    {
        "sku_id": "SKU-RAW-006",
        "name": "Смола эпоксидная двухкомпонентная",
        "category": ProductCategory.RAW_MATERIALS.value,
        "unit_price": 19000.0,
        "unit_cost": 16300.0,
        "holding_cost_annual_rate": 0.18,
        "unit_volume_m3": 0.040,
        "unit_weight_kg": 30.0,
        "pack_size": 2,
        "stockout_penalty_per_unit": 5600.0,
        "target_abc": ABCClass.B.value,
        "target_xyz": XYZClass.Y.value,
        "base_demand": 2.5,
        "trend_slope": 0.0,
        "seasonal_amp": 0.22,
        "is_intermittent": False,
    },
    # Consumables (6 items - high velocity, lower unit cost)
    {
        "sku_id": "SKU-CNS-001",
        "name": "Стретч-пленка машинная 23мкм",
        "category": ProductCategory.CONSUMABLES.value,
        "unit_price": 1450.0,
        "unit_cost": 1200.0,
        "holding_cost_annual_rate": 0.25,
        "unit_volume_m3": 0.015,
        "unit_weight_kg": 16.0,
        "pack_size": 6,
        "stockout_penalty_per_unit": 400.0,
        "target_abc": ABCClass.C.value,
        "target_xyz": XYZClass.X.value,
        "base_demand": 30.0,
        "trend_slope": 0.0,
        "seasonal_amp": 0.04,
        "is_intermittent": False,
    },
    {
        "sku_id": "SKU-CNS-002",
        "name": "Перчатки нитриловые защитные",
        "category": ProductCategory.CONSUMABLES.value,
        "unit_price": 380.0,
        "unit_cost": 310.0,
        "holding_cost_annual_rate": 0.25,
        "unit_volume_m3": 0.002,
        "unit_weight_kg": 0.3,
        "pack_size": 50,
        "stockout_penalty_per_unit": 120.0,
        "target_abc": ABCClass.C.value,
        "target_xyz": XYZClass.X.value,
        "base_demand": 55.0,
        "trend_slope": 0.0,
        "seasonal_amp": 0.04,
        "is_intermittent": False,
    },
    {
        "sku_id": "SKU-CNS-003",
        "name": "Лента клейкая упаковочная",
        "category": ProductCategory.CONSUMABLES.value,
        "unit_price": 120.0,
        "unit_cost": 95.0,
        "holding_cost_annual_rate": 0.25,
        "unit_volume_m3": 0.001,
        "unit_weight_kg": 0.2,
        "pack_size": 36,
        "stockout_penalty_per_unit": 40.0,
        "target_abc": ABCClass.C.value,
        "target_xyz": XYZClass.X.value,
        "base_demand": 95.0,
        "trend_slope": 0.0,
        "seasonal_amp": 0.03,
        "is_intermittent": False,
    },
    {
        "sku_id": "SKU-CNS-004",
        "name": "Смазка литиевая EP-2",
        "category": ProductCategory.CONSUMABLES.value,
        "unit_price": 550.0,
        "unit_cost": 450.0,
        "holding_cost_annual_rate": 0.25,
        "unit_volume_m3": 0.001,
        "unit_weight_kg": 0.4,
        "pack_size": 12,
        "stockout_penalty_per_unit": 170.0,
        "target_abc": ABCClass.C.value,
        "target_xyz": XYZClass.Y.value,
        "base_demand": 16.0,
        "trend_slope": 0.0,
        "seasonal_amp": 0.18,
        "is_intermittent": False,
    },
    {
        "sku_id": "SKU-CNS-005",
        "name": "Очиститель контактов аэрозоль",
        "category": ProductCategory.CONSUMABLES.value,
        "unit_price": 420.0,
        "unit_cost": 340.0,
        "holding_cost_annual_rate": 0.25,
        "unit_volume_m3": 0.001,
        "unit_weight_kg": 0.5,
        "pack_size": 12,
        "stockout_penalty_per_unit": 130.0,
        "target_abc": ABCClass.C.value,
        "target_xyz": XYZClass.Y.value,
        "base_demand": 14.0,
        "trend_slope": 0.0,
        "seasonal_amp": 0.18,
        "is_intermittent": False,
    },
    {
        "sku_id": "SKU-CNS-006",
        "name": "Поддон деревянный евро 1200х800",
        "category": ProductCategory.CONSUMABLES.value,
        "unit_price": 650.0,
        "unit_cost": 520.0,
        "holding_cost_annual_rate": 0.25,
        "unit_volume_m3": 0.144,
        "unit_weight_kg": 22.0,
        "pack_size": 15,
        "stockout_penalty_per_unit": 200.0,
        "target_abc": ABCClass.C.value,
        "target_xyz": XYZClass.Y.value,
        "base_demand": 12.0,
        "trend_slope": 0.0,
        "seasonal_amp": 0.16,
        "is_intermittent": False,
    },
]


class SyntheticDataGenerator:
    """Deterministic and reproducible synthetic data generator for Inventory DSS."""

    def __init__(self, seed: int = RANDOM_SEED) -> None:
        self.seed = seed
        self.rng = np.random.default_rng(seed)

    def generate_skus(self) -> list[SKU]:
        """Generate the catalog of 25 SKUs with domain parameters."""
        skus: list[SKU] = []
        for spec in CATALOG_SPECS:
            skus.append(
                SKU(
                    sku_id=spec["sku_id"],
                    name=spec["name"],
                    category=spec["category"],
                    unit_price=spec["unit_price"],
                    unit_cost=spec["unit_cost"],
                    holding_cost_annual_rate=spec["holding_cost_annual_rate"],
                    unit_volume_m3=spec["unit_volume_m3"],
                    unit_weight_kg=spec["unit_weight_kg"],
                    pack_size=spec["pack_size"],
                    abc_class=spec["target_abc"],
                    xyz_class=spec["target_xyz"],
                    stockout_penalty_per_unit=spec["stockout_penalty_per_unit"],
                )
            )
        return skus

    def generate_suppliers(self) -> list[Supplier]:
        """Generate 5 representative supplier archetypes."""
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
                on_time_delivery_rate=0.750,
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
                on_time_delivery_rate=0.960,
                defect_rate=0.008,
                min_order_quantity=1,
                price_markup_factor=1.05,
                order_processing_cost=2500.0,
                profile_type=SupplierProfileType.LOCAL_EXPRESS,
            ),
            Supplier(
                supplier_id="SUP-OVERSEAS",
                name="Восток Импорт Опт",
                mean_lead_time_days=35.0,
                std_lead_time_days=6.0,
                on_time_delivery_rate=0.820,
                defect_rate=0.020,
                min_order_quantity=200,
                price_markup_factor=0.75,
                order_processing_cost=8000.0,
                profile_type=SupplierProfileType.OVERSEAS_BULK,
            ),
            Supplier(
                supplier_id="SUP-STANDARD",
                name="Альянс Логистик",
                mean_lead_time_days=7.0,
                std_lead_time_days=1.2,
                on_time_delivery_rate=0.910,
                defect_rate=0.012,
                min_order_quantity=25,
                price_markup_factor=1.00,
                order_processing_cost=3500.0,
                profile_type=SupplierProfileType.BALANCED_STANDARD,
            ),
        ]

    def generate_warehouse(self) -> Warehouse:
        """Generate warehouse master parameters."""
        return Warehouse(
            warehouse_id=DEFAULT_WAREHOUSE_ID,
            name=DEFAULT_WAREHOUSE_NAME,
            total_volume_capacity_m3=DEFAULT_WAREHOUSE_VOLUME_M3,
            total_weight_capacity_kg=DEFAULT_WAREHOUSE_WEIGHT_KG,
            fixed_order_cost=DEFAULT_FIXED_ORDER_COST_RUB,
            annual_capital_rate=DEFAULT_ANNUAL_CAPITAL_RATE,
            target_service_level=DEFAULT_SERVICE_LEVEL,
        )

    def generate_demand_history(
        self,
        skus: list[SKU] | None = None,
        days: int = DEMAND_HISTORY_DAYS,
        start_date: date = date(2024, 1, 1),
    ) -> list[DemandRecord]:
        """Generate realistic daily demand series for each SKU over given horizon."""
        if skus is None:
            skus = self.generate_skus()

        spec_lookup = {s["sku_id"]: s for s in CATALOG_SPECS}
        all_records: list[DemandRecord] = []

        # Reset RNG with fixed seed offset for demand determinism
        demand_rng = np.random.default_rng(self.seed + 100)

        for sku in skus:
            spec = spec_lookup.get(sku.sku_id, {})
            base_d = spec.get("base_demand", 10.0)
            trend_s = spec.get("trend_slope", 0.0)
            amp_seas = spec.get("seasonal_amp", 0.05)
            is_intermittent = spec.get("is_intermittent", False)
            p_arr = spec.get("intermittent_prob", 0.15)
            lam = spec.get("intermittent_lambda", 2.0)

            for t in range(days):
                cur_date = start_date + timedelta(days=t)
                dow = cur_date.weekday()
                is_weekend = dow >= 5
                day_of_year = t % 365
                is_promo = (80 <= day_of_year <= 85) or (260 <= day_of_year <= 265)

                if is_intermittent:
                    # Croston zero-inflated demand
                    if demand_rng.random() < p_arr:
                        qty = float(demand_rng.poisson(lam) + 1)
                    else:
                        qty = 0.0
                else:
                    # Trend + Annual Seasonality + Weekend Dampening + Promo Spike + Gaussian Noise
                    trend = base_d + trend_s * t
                    seasonality = 1.0 + amp_seas * np.sin(2 * np.pi * t / 365.0)
                    weekend_factor = 0.60 if is_weekend else 1.15
                    promo_factor = 1.45 if is_promo else 1.0
                    noise = demand_rng.normal(0.0, max(0.5, base_d * 0.08))

                    raw_qty = (trend * seasonality * weekend_factor * promo_factor) + noise
                    qty = max(0.0, round(float(raw_qty), 1))

                all_records.append(
                    DemandRecord(
                        date=cur_date,
                        sku_id=sku.sku_id,
                        quantity=qty,
                        is_promotional=is_promo,
                        is_weekend=is_weekend,
                        stockout_flag=False,
                    )
                )

        return all_records

    def generate_inventory_states(
        self,
        skus: list[SKU] | None = None,
        demand_records: list[DemandRecord] | None = None,
    ) -> list[InventoryState]:
        """Generate realistic initial warehouse inventory state snapshots."""
        if skus is None:
            skus = self.generate_skus()
        if demand_records is None:
            demand_records = self.generate_demand_history(skus=skus)

        # Compute empirical mean daily demand per SKU over the last 90 days
        cutoff_date = max(r.date for r in demand_records) - timedelta(days=90)
        recent_demands: dict[str, list[float]] = {s.sku_id: [] for s in skus}
        for r in demand_records:
            if r.date >= cutoff_date:
                recent_demands[r.sku_id].append(r.quantity)

        mean_demand = {
            sku_id: float(np.mean(q_list)) if q_list else 5.0
            for sku_id, q_list in recent_demands.items()
        }

        states: list[InventoryState] = []

        # Distribute states across statuses: critical, reorder, optimal, excess
        status_assignments = [
            # First 2 items in critical or reorder state
            (StockStatus.CRITICAL, 0.5, 0.0),
            (StockStatus.REORDER_NEEDED, 1.2, 50.0),
            (StockStatus.OPTIMAL, 2.8, 0.0),
            (StockStatus.EXCESS, 5.5, 0.0),
        ]

        for i, sku in enumerate(skus):
            mu_d = max(0.5, mean_demand.get(sku.sku_id, 5.0))
            # Standard reference lead time ~ 7 days
            lead_time = 7.0
            lead_demand = mu_d * lead_time
            safety_stock = round(1.645 * np.sqrt(lead_time * (mu_d * 0.3) ** 2 + mu_d**2 * 1.44), 1)
            reorder_point = round(lead_demand + safety_stock, 1)
            eoq_est = round(max(float(sku.pack_size), np.sqrt(2 * mu_d * 365 * 3500 / (sku.unit_price * 0.20))), 1)
            max_stock = round(reorder_point + eoq_est, 1)

            status_type, _multiplier, in_transit = status_assignments[i % len(status_assignments)]

            if status_type == StockStatus.CRITICAL:
                on_hand = round(max(0.0, safety_stock * 0.6), 1)
                on_order = 0.0
                allocated = round(on_hand * 0.2, 1)
                backorders = 0.0
            elif status_type == StockStatus.REORDER_NEEDED:
                on_hand = round(safety_stock + (reorder_point - safety_stock) * 0.5, 1)
                on_order = in_transit
                allocated = 0.0
                backorders = 0.0
            elif status_type == StockStatus.OPTIMAL:
                on_hand = round(reorder_point + (max_stock - reorder_point) * 0.5, 1)
                on_order = 0.0
                allocated = round(on_hand * 0.05, 1)
                backorders = 0.0
            else:  # EXCESS
                on_hand = round(max_stock * 1.25, 1)
                on_order = 0.0
                allocated = 0.0
                backorders = 0.0

            states.append(
                InventoryState(
                    sku_id=sku.sku_id,
                    on_hand=on_hand,
                    on_order=on_order,
                    allocated=allocated,
                    backorders=backorders,
                    safety_stock=safety_stock,
                    reorder_point=reorder_point,
                    max_stock=max_stock,
                    status=status_type,
                )
            )

        return states

    def generate_all(
        self,
        days: int = DEMAND_HISTORY_DAYS,
        start_date: date = date(2024, 1, 1),
        output_dir: Path | str | None = None,
    ) -> tuple[list[SKU], list[Supplier], Warehouse, list[DemandRecord], list[InventoryState]]:
        """Generate complete self-consistent synthetic supply chain dataset."""
        skus = self.generate_skus()
        suppliers = self.generate_suppliers()
        warehouse = self.generate_warehouse()
        demand = self.generate_demand_history(skus=skus, days=days, start_date=start_date)
        states = self.generate_inventory_states(skus=skus, demand_records=demand)
        if output_dir is not None:
            self.save_to_disk(output_dir=output_dir, days=days)
        return skus, suppliers, warehouse, demand, states

    def save_to_disk(
        self,
        output_dir: Path | str | None = None,
        days: int = DEMAND_HISTORY_DAYS,
    ) -> dict[str, Path]:
        """Export generated synthetic data to CSV and JSON files."""
        if output_dir is None:
            output_path = Path(SYNTHETIC_DATA_DIR)
        else:
            output_path = Path(output_dir)

        output_path.mkdir(parents=True, exist_ok=True)

        skus, suppliers, warehouse, demand, states = self.generate_all(days=days)

        # 1. Export skus.csv
        skus_file = output_path / "skus.csv"
        with open(skus_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "sku_id",
                "name",
                "category",
                "unit_price",
                "unit_cost",
                "holding_cost_annual_rate",
                "unit_volume_m3",
                "unit_weight_kg",
                "pack_size",
                "abc_class",
                "xyz_class",
                "stockout_penalty_per_unit",
            ])
            for s in skus:
                writer.writerow([
                    s.sku_id,
                    s.name,
                    s.category,
                    s.unit_price,
                    s.unit_cost,
                    s.holding_cost_annual_rate,
                    s.unit_volume_m3,
                    s.unit_weight_kg,
                    s.pack_size,
                    s.abc_class,
                    s.xyz_class,
                    s.stockout_penalty_per_unit,
                ])

        # 2. Export suppliers.csv
        suppliers_file = output_path / "suppliers.csv"
        with open(suppliers_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "supplier_id",
                "name",
                "mean_lead_time_days",
                "std_lead_time_days",
                "on_time_delivery_rate",
                "defect_rate",
                "min_order_quantity",
                "price_markup_factor",
                "order_processing_cost",
                "profile_type",
            ])
            for supp in suppliers:
                writer.writerow([
                    supp.supplier_id,
                    supp.name,
                    supp.mean_lead_time_days,
                    supp.std_lead_time_days,
                    supp.on_time_delivery_rate,
                    supp.defect_rate,
                    supp.min_order_quantity,
                    supp.price_markup_factor,
                    supp.order_processing_cost,
                    supp.profile_type.value if supp.profile_type else "",
                ])

        # 3. Export demand_history.csv
        demand_file = output_path / "demand_history.csv"
        with open(demand_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "sku_id", "quantity", "is_promotional", "is_weekend", "stockout_flag"])
            for d in demand:
                writer.writerow([
                    d.date.isoformat(),
                    d.sku_id,
                    d.quantity,
                    d.is_promotional,
                    d.is_weekend,
                    d.stockout_flag,
                ])

        # 4. Export warehouse.json
        warehouse_file = output_path / "warehouse.json"
        with open(warehouse_file, "w", encoding="utf-8") as f:
            json.dump(warehouse.model_dump(), f, indent=2, ensure_ascii=False)

        # 5. Export inventory_state.csv
        state_file = output_path / "inventory_state.csv"
        with open(state_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "sku_id",
                "on_hand",
                "on_order",
                "allocated",
                "backorders",
                "effective_inventory",
                "safety_stock",
                "reorder_point",
                "max_stock",
                "status",
            ])
            for st in states:
                writer.writerow([
                    st.sku_id,
                    st.on_hand,
                    st.on_order,
                    st.allocated,
                    st.backorders,
                    st.effective_inventory,
                    st.safety_stock,
                    st.reorder_point,
                    st.max_stock,
                    st.status.value if st.status else "",
                ])

        return {
            "skus": skus_file,
            "suppliers": suppliers_file,
            "demand": demand_file,
            "warehouse": warehouse_file,
            "inventory_state": state_file,
        }
