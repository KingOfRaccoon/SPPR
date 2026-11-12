"""Unit tests for the synthetic data generator."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from inventory_dss.data.generator import SyntheticDataGenerator
from inventory_dss.models.domain import (
    DemandRecord,
    StockStatus,
)


class TestSyntheticDataGeneratorDeterminism:
    """Tests confirming 100% deterministic reproducibility under fixed random seed."""

    def test_seed_reproducibility(self):
        gen1 = SyntheticDataGenerator(seed=42)
        skus1, supps1, wh1, demand1, states1 = gen1.generate_all(days=365)

        gen2 = SyntheticDataGenerator(seed=42)
        skus2, supps2, wh2, demand2, states2 = gen2.generate_all(days=365)

        assert len(skus1) == len(skus2) == 25
        assert len(supps1) == len(supps2) == 5
        assert wh1.total_volume_capacity_m3 == wh2.total_volume_capacity_m3
        assert len(demand1) == len(demand2) == 25 * 365

        # Demand values must be bitwise identical
        q1 = np.array([d.quantity for d in demand1])
        q2 = np.array([d.quantity for d in demand2])
        np.testing.assert_array_equal(q1, q2)

        # Inventory states must be identical
        for s1, s2 in zip(states1, states2):
            assert s1.sku_id == s2.sku_id
            assert s1.on_hand == s2.on_hand
            assert s1.effective_inventory == s2.effective_inventory

    def test_different_seeds_diverge(self):
        gen1 = SyntheticDataGenerator(seed=42)
        demand1 = gen1.generate_demand_history(days=100)

        gen2 = SyntheticDataGenerator(seed=999)
        demand2 = gen2.generate_demand_history(days=100)

        q1 = np.array([d.quantity for d in demand1])
        q2 = np.array([d.quantity for d in demand2])
        assert not np.array_equal(q1, q2)


class TestSKUCatalogProperties:
    """Tests confirming SKU catalog contracts and ABC/XYZ partition."""

    @pytest.fixture
    def generator(self) -> SyntheticDataGenerator:
        return SyntheticDataGenerator(seed=42)

    def test_sku_catalog_size_and_categories(self, generator: SyntheticDataGenerator):
        skus = generator.generate_skus()
        assert len(skus) == 25

        categories = {s.category for s in skus}
        expected_categories = {"Electronics", "Spare Parts", "Raw Materials", "Consumables"}
        assert categories == expected_categories

        # Ensure each category has at least 4 items
        for cat in expected_categories:
            count = sum(1 for s in skus if s.category == cat)
            assert count >= 4, f"Category {cat} has only {count} items"

    def test_sku_physical_and_economic_invariants(self, generator: SyntheticDataGenerator):
        skus = generator.generate_skus()
        for sku in skus:
            assert sku.unit_price > 0.0, f"{sku.sku_id} non-positive unit_price"
            assert sku.unit_volume_m3 > 0.0, f"{sku.sku_id} non-positive unit_volume_m3"
            assert sku.unit_weight_kg > 0.0, f"{sku.sku_id} non-positive unit_weight_kg"
            assert sku.pack_size >= 1, f"{sku.sku_id} invalid pack_size"
            assert 0.01 <= sku.holding_cost_annual_rate <= 1.0
            assert sku.abc_class in ("A", "B", "C")
            assert sku.xyz_class in ("X", "Y", "Z")

    def test_abc_revenue_distribution_pareto_invariants(self, generator: SyntheticDataGenerator):
        """Verify strict ABC classification where A~80%, B~15%, C~5% of total annual revenue."""
        skus = generator.generate_skus()
        demand = generator.generate_demand_history(skus=skus, days=730)

        demand_by_sku: dict[str, float] = {s.sku_id: 0.0 for s in skus}
        for d in demand:
            demand_by_sku[d.sku_id] += d.quantity

        revenue_by_sku = {s.sku_id: demand_by_sku[s.sku_id] * s.unit_price for s in skus}
        total_revenue = sum(revenue_by_sku.values())
        assert total_revenue > 0

        revenue_by_class: dict[str, float] = {"A": 0.0, "B": 0.0, "C": 0.0}
        for s in skus:
            revenue_by_class[s.abc_class] += revenue_by_sku[s.sku_id]

        share_a = revenue_by_class["A"] / total_revenue
        share_b = revenue_by_class["B"] / total_revenue
        share_c = revenue_by_class["C"] / total_revenue

        # Verify A share is ~80% (acceptable window [0.70, 0.88])
        assert 0.70 <= share_a <= 0.88, f"ABC Class A share {share_a:.2%} outside expected range"
        # Verify B share is ~15% (acceptable window [0.10, 0.25])
        assert 0.10 <= share_b <= 0.25, f"ABC Class B share {share_b:.2%} outside expected range"
        # Verify C share is ~5% (acceptable window [0.01, 0.10])
        assert 0.01 <= share_c <= 0.10, f"ABC Class C share {share_c:.2%} outside expected range"

    def test_xyz_variability_ordering(self, generator: SyntheticDataGenerator):
        """Verify that Class X has lower demand variance/CV than Class Z."""
        skus = generator.generate_skus()
        demand = generator.generate_demand_history(skus=skus, days=365)

        series_by_sku: dict[str, list[float]] = {s.sku_id: [] for s in skus}
        for d in demand:
            series_by_sku[d.sku_id].append(d.quantity)

        cv_by_class: dict[str, list[float]] = {"X": [], "Y": [], "Z": []}
        for s in skus:
            vals = np.array(series_by_sku[s.sku_id])
            mean_v = float(np.mean(vals))
            std_v = float(np.std(vals))
            cv = std_v / mean_v if mean_v > 0 else 1.0
            cv_by_class[s.xyz_class].append(cv)

        avg_cv_x = float(np.mean(cv_by_class["X"]))
        avg_cv_z = float(np.mean(cv_by_class["Z"]))

        assert avg_cv_x < avg_cv_z, f"Class X CV ({avg_cv_x}) must be strictly lower than Class Z CV ({avg_cv_z})"


class TestDemandSeriesIntegrity:
    """Tests confirming demand timeseries continuity, seasonality, and non-negativity."""

    @pytest.fixture
    def demand_records(self) -> list[DemandRecord]:
        gen = SyntheticDataGenerator(seed=42)
        return gen.generate_demand_history(days=730)

    def test_demand_length_and_non_negativity(self, demand_records: list[DemandRecord]):
        assert len(demand_records) == 25 * 730
        for rec in demand_records:
            assert rec.quantity >= 0.0, f"Negative demand detected: {rec}"

    def test_date_sequence_continuity(self, demand_records: list[DemandRecord]):
        sku1_records = [r for r in demand_records if r.sku_id == "SKU-ELEC-001"]
        assert len(sku1_records) == 730
        dates = [r.date for r in sku1_records]
        assert dates[0] == date(2024, 1, 1)

        for i in range(1, len(dates)):
            expected_date = dates[0] + timedelta(days=i)
            assert dates[i] == expected_date, f"Date sequence broken at step {i}: {dates[i]} vs {expected_date}"

    def test_croston_intermittent_presence_of_zeros(self, demand_records: list[DemandRecord]):
        """Intermittent spare parts must contain zero-demand days (Croston regime)."""
        part_records = [r for r in demand_records if r.sku_id == "SKU-PART-001"]
        zero_days = sum(1 for r in part_records if r.quantity == 0.0)
        zero_ratio = zero_days / len(part_records)
        assert zero_ratio > 0.50, f"Expected >50% zero demand for sporadic SKU-PART-001, got {zero_ratio:.1%}"


class TestSuppliersAndWarehouseIntegrity:
    """Tests for supplier archetypes and warehouse parameters."""

    def test_supplier_profiles(self):
        gen = SyntheticDataGenerator(seed=42)
        suppliers = generator_suppliers = gen.generate_suppliers()
        assert len(generator_suppliers) == 5

        supp_dict = {s.supplier_id: s for s in suppliers}
        assert "SUP-PREMIUM" in supp_dict
        assert "SUP-BUDGET" in supp_dict
        assert "SUP-LOCAL" in supp_dict
        assert "SUP-OVERSEAS" in supp_dict
        assert "SUP-STANDARD" in supp_dict

        # Premium must be faster and more reliable than Overseas
        premium = supp_dict["SUP-PREMIUM"]
        overseas = supp_dict["SUP-OVERSEAS"]
        assert premium.mean_lead_time_days < overseas.mean_lead_time_days
        assert premium.on_time_delivery_rate > overseas.on_time_delivery_rate
        assert premium.defect_rate < overseas.defect_rate

    def test_warehouse_model_parameters(self):
        gen = SyntheticDataGenerator(seed=42)
        wh = gen.generate_warehouse()
        assert wh.total_volume_capacity_m3 == 1000.0
        assert wh.total_weight_capacity_kg == 50000.0
        assert wh.target_service_level == 0.95


class TestInventoryStatesAndPersistence:
    """Tests for initial inventory state snapshots and disk export."""

    def test_inventory_states_distribution(self):
        gen = SyntheticDataGenerator(seed=42)
        states = gen.generate_inventory_states()
        assert len(states) == 25

        statuses = {s.status for s in states}
        # All 4 taxonomy states must be represented across the 25 SKUs
        assert StockStatus.CRITICAL in statuses
        assert StockStatus.REORDER_NEEDED in statuses
        assert StockStatus.OPTIMAL in statuses
        assert StockStatus.EXCESS in statuses

        for s in states:
            expected = s.on_hand + s.on_order - s.allocated - s.backorders
            assert s.effective_inventory == pytest.approx(expected, abs=1e-4)

    def test_save_to_disk_and_file_conformance(self, tmp_path: Path):
        gen = SyntheticDataGenerator(seed=42)
        saved = gen.save_to_disk(output_dir=tmp_path, days=30)

        assert "skus" in saved and saved["skus"].exists()
        assert "suppliers" in saved and saved["suppliers"].exists()
        assert "demand" in saved and saved["demand"].exists()
        assert "warehouse" in saved and saved["warehouse"].exists()
        assert "inventory_state" in saved and saved["inventory_state"].exists()

        # Validate CSV parsability
        df_skus = pd.read_csv(saved["skus"])
        assert len(df_skus) == 25
        assert "sku_id" in df_skus.columns
        assert "unit_price" in df_skus.columns

        df_supp = pd.read_csv(saved["suppliers"])
        assert len(df_supp) == 5

        df_demand = pd.read_csv(saved["demand"])
        assert len(df_demand) == 25 * 30

        # Validate JSON parsability
        with open(saved["warehouse"], encoding="utf-8") as f:
            wh_data = json.load(f)
        assert wh_data["warehouse_id"] == "WH-CENTRAL-01"
