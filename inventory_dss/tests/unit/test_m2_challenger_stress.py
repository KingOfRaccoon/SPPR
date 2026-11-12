"""Milestone 2 Empirical Challenger Stress-Testing Suite.

Authored by challenger_m2_2 (teamwork_challenger).
Validates mathematical boundary conditions, empirical distributions,
and Pydantic v2 schema adherence for M2 MCDA algorithms and synthetic data generator.
"""

from __future__ import annotations

import csv
import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from inventory_dss.data.generator import SyntheticDataGenerator
from inventory_dss.models.domain import (
    SKU,
    DemandRecord,
    InventoryState,
    StockStatus,
    Supplier,
    SupplierProfileType,
    Warehouse,
)
from inventory_dss.suppliers.ahp import (
    DEFAULT_PAIRWISE_MATRIX,
    RANDOM_INDEX_TABLE,
    AHPEngine,
)
from inventory_dss.suppliers.entropy import EntropyWeightEngine
from inventory_dss.suppliers.evaluator import SupplierEvaluator
from inventory_dss.suppliers.risk_trees import SupplyRiskDecisionTree
from inventory_dss.suppliers.topsis import TOPSISSolver

# =============================================================================
# 1. AHP MATHEMATICAL BOUNDARY & EMPIRICAL DISTRIBUTION TESTS
# =============================================================================

class TestAHPMathematicalBoundaries:
    """Rigorous mathematical tests for Saaty Analytic Hierarchy Process."""

    @pytest.mark.parametrize("n", [3, 4, 5, 6, 7, 8])
    def test_perfectly_consistent_matrices_yield_zero_ci(self, n: int):
        """A perfectly consistent reciprocal matrix A[i, j] = w_i / w_j must have lambda_max = n and CR = 0.0."""
        rng = np.random.default_rng(100 + n)
        w_true = rng.uniform(0.1, 1.0, size=n)
        w_true /= np.sum(w_true)

        A_consistent = np.outer(w_true, 1.0 / w_true)
        weights, lambda_max, cr = AHPEngine.compute_weights(A_consistent)

        np.testing.assert_allclose(weights, w_true, atol=1e-5)
        assert math.isclose(lambda_max, n, abs_tol=1e-5)
        assert cr == 0.0 or math.isclose(cr, 0.0, abs_tol=1e-5)

    def test_saaty_random_index_table_matches_literature(self):
        """Verify empirical Random Index (RI) table against Saaty (1980) canonical values."""
        canonical_ri = {
            1: 0.00, 2: 0.00, 3: 0.58, 4: 0.90, 5: 1.12,
            6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49,
        }
        for n, expected_ri in canonical_ri.items():
            assert RANDOM_INDEX_TABLE.get(n) == expected_ri

    @pytest.mark.parametrize("n", [3, 4, 5, 6])
    def test_random_reciprocal_matrices_average_cr_near_one(self, n: int):
        """Simulate random reciprocal matrices on Saaty 1-9 scale; mean CR must approximate 1.0 (validating RI)."""
        saaty_scale = np.array([
            1/9, 1/8, 1/7, 1/6, 1/5, 1/4, 1/3, 1/2,
            1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0,
        ])
        rng = np.random.default_rng(42 + n)
        crs = []
        for _ in range(200):
            A = np.ones((n, n), dtype=float)
            for i in range(n):
                for j in range(i + 1, n):
                    val = rng.choice(saaty_scale)
                    A[i, j] = val
                    A[j, i] = 1.0 / val
            _, _, cr = AHPEngine.compute_weights(A)
            crs.append(cr)

        mean_cr = float(np.mean(crs))
        # The mean consistency ratio of uniformly random reciprocal matrices is approximately 1.0 (+/- 25%)
        assert 0.75 <= mean_cr <= 1.25, f"Empirical CR mean {mean_cr:.4f} diverged for n={n}"

    def test_pairwise_matrix_strict_reciprocity_invariant(self):
        """Verify default 6x6 expert matrix satisfies A[i, j] * A[j, i] == 1.0."""
        recip_product = DEFAULT_PAIRWISE_MATRIX * DEFAULT_PAIRWISE_MATRIX.T
        np.testing.assert_allclose(recip_product, 1.0, atol=1e-7)

    def test_matrix_order_boundaries_one_and_two(self):
        """Matrix orders n=1 and n=2 must be mathematically consistent with CR=0.0."""
        # Order 1
        w1, l1, cr1 = AHPEngine.compute_weights(np.array([[1.0]]))
        assert list(w1) == [1.0]
        assert l1 == 1.0
        assert cr1 == 0.0

        # Order 2
        w2, l2, cr2 = AHPEngine.compute_weights(np.array([[1.0, 4.0], [0.25, 1.0]]))
        assert math.isclose(w2[0], 0.8, abs_tol=1e-4)
        assert math.isclose(w2[1], 0.2, abs_tol=1e-4)
        assert math.isclose(l2, 2.0, abs_tol=1e-4)
        assert cr2 == 0.0


# =============================================================================
# 2. SHANNON ENTROPY WEIGHTING MATHEMATICAL BOUNDARY TESTS
# =============================================================================

class TestEntropyWeightBoundaries:
    """Tests for objective Shannon Entropy dispersion and edge cases."""

    def test_column_with_identical_values_has_maximum_entropy_and_zero_weight(self):
        """A criterion with zero variance across alternatives provides zero discriminating power (d_j=0, w_j=0)."""
        X = np.array([
            [10.0, 100.0],
            [20.0, 100.0],
            [30.0, 100.0],
            [40.0, 100.0],
        ])
        E, d, w = EntropyWeightEngine.compute_entropy_and_divergence(X)
        assert math.isclose(E[1], 1.0, abs_tol=1e-5), f"Entropy {E[1]} must be 1.0"
        assert math.isclose(d[1], 0.0, abs_tol=1e-5), f"Divergence {d[1]} must be 0.0"
        assert math.isclose(w[1], 0.0, abs_tol=1e-5), f"Weight {w[1]} must be 0.0"
        assert math.isclose(w[0], 1.0, abs_tol=1e-5), f"Weight {w[0]} must be 1.0"

    def test_all_columns_identical_yields_uniform_weights(self):
        """When all criteria are constant across alternatives, weights fall back to uniform 1/n."""
        X = np.ones((5, 3)) * 25.0
        w = EntropyWeightEngine.compute_entropy_weights(X)
        np.testing.assert_allclose(w, np.full(3, 1.0 / 3.0), atol=1e-5)

    def test_near_zero_entries_numerical_safety(self):
        """Zero and near-zero values (1e-15) must not produce NaN or Inf."""
        X = np.array([
            [0.0, 10.0],
            [1e-15, 20.0],
            [50.0, 30.0],
        ])
        w = EntropyWeightEngine.compute_entropy_weights(X)
        assert not np.isnan(w).any()
        assert not np.isinf(w).any()
        assert math.isclose(float(np.sum(w)), 1.0, abs_tol=1e-5)

    def test_higher_dispersion_yields_higher_entropy_weight(self):
        """A criterion with higher relative variance must receive strictly higher objective weight."""
        X = np.array([
            [1.0, 50.0],
            [5.0, 50.1],
            [20.0, 49.9],
            [100.0, 50.0],
        ])
        w = EntropyWeightEngine.compute_entropy_weights(X)
        assert w[0] > w[1] * 5.0, "Column 0 high variance must heavily dominate Column 1 flat metric"


# =============================================================================
# 3. TOPSIS MATHEMATICAL BOUNDARY & SYMMETRY TESTS
# =============================================================================

class TestTOPSISMathematicalBoundaries:
    """Tests for TOPSIS boundary conditions, symmetry, and ideal distance invariants."""

    def test_single_alternative_boundary(self):
        """Single alternative is trivially optimal and receives closeness == 1.0."""
        X = np.array([[12.0, 4.5, 0.95]])
        w = np.array([0.3, 0.3, 0.4])
        b = [False, False, True]
        scores = TOPSISSolver.solve(X, w, b)
        assert len(scores) == 1
        assert scores[0] == 1.0

    def test_identical_alternatives_equal_scores(self):
        """Completely identical alternatives across all criteria must receive equal scores (tied)."""
        X = np.array([
            [10.0, 20.0],
            [10.0, 20.0],
            [10.0, 20.0],
        ])
        w = np.array([0.5, 0.5])
        b = [False, True]
        det = TOPSISSolver.solve_detailed(X, w, b)
        scores = det["closeness"]
        assert len(scores) == 3
        # All identical alternatives must receive the exact same score
        assert scores[0] == scores[1] == scores[2]
        # In TOPSIS with denom_safe=1e-12, scores evaluate to 0.0; check bounded in [0.0, 1.0]
        assert all(0.0 <= s <= 1.0 for s in scores)

    def test_inverse_ranking_when_cost_vs_benefit_flips(self):
        """Flipping benefit flags strictly inverts relative closeness scores and rankings."""
        X = np.array([
            [10.0, 100.0],  # Alt A: Low cost (10 vs 50), High benefit (100 vs 20)
            [50.0, 20.0],   # Alt B: High cost, Low benefit
        ])
        w = np.array([0.5, 0.5])

        # Direction 1: [Cost, Benefit] -> A dominates B
        scores_ab = TOPSISSolver.solve(X, w, [False, True])
        assert scores_ab[0] > scores_ab[1]
        assert scores_ab[0] == 1.0 and scores_ab[1] == 0.0

        # Direction 2: [Benefit, Cost] -> B dominates A
        scores_ba = TOPSISSolver.solve(X, w, [True, False])
        assert scores_ba[1] > scores_ba[0]
        assert scores_ba[1] == 1.0 and scores_ba[0] == 0.0

        # Exact symmetry
        assert math.isclose(scores_ab[0], scores_ba[1], abs_tol=1e-5)
        assert math.isclose(scores_ab[1], scores_ba[0], abs_tol=1e-5)

    def test_extreme_ideal_and_anti_ideal_alternatives(self):
        """Alternative matching ideal on all criteria gets 1.0; alternative matching anti-ideal gets 0.0."""
        X = np.array([
            [1.0, 100.0],  # Ideal
            [100.0, 1.0],  # Anti-ideal
        ])
        w = np.array([0.5, 0.5])
        scores = TOPSISSolver.solve(X, w, [False, True])
        assert scores[0] == 1.0
        assert scores[1] == 0.0


# =============================================================================
# 4. SYNTHETIC DATA PYDANTIC V2 ROUND-TRIP VALIDATION
# =============================================================================

class TestSyntheticDataPydanticRoundTrip:
    """Validates that persisted synthetic data files load cleanly into Pydantic models."""

    @pytest.fixture
    def data_dir(self) -> Path:
        p = Path(__file__).resolve().parents[2] / "data" / "synthetic"
        assert p.exists(), f"Synthetic data directory {p} does not exist"
        return p

    def test_skus_csv_pydantic_validation(self, data_dir: Path):
        skus_file = data_dir / "skus.csv"
        assert skus_file.exists()

        loaded_skus: list[SKU] = []
        with open(skus_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sku = SKU(
                    sku_id=row["sku_id"],
                    name=row["name"],
                    category=row["category"],
                    unit_price=float(row["unit_price"]),
                    unit_cost=float(row["unit_cost"]) if row["unit_cost"] else None,
                    holding_cost_annual_rate=float(row["holding_cost_annual_rate"]),
                    unit_volume_m3=float(row["unit_volume_m3"]),
                    unit_weight_kg=float(row["unit_weight_kg"]),
                    pack_size=int(row["pack_size"]),
                    abc_class=row["abc_class"] if row["abc_class"] else None,
                    xyz_class=row["xyz_class"] if row["xyz_class"] else None,
                    stockout_penalty_per_unit=float(row["stockout_penalty_per_unit"]) if row["stockout_penalty_per_unit"] else None,
                )
                loaded_skus.append(sku)

        assert len(loaded_skus) == 25
        for s in loaded_skus:
            assert s.unit_price > 0.0
            assert s.unit_volume_m3 > 0.0
            assert s.unit_weight_kg > 0.0
            assert s.pack_size >= 1
            assert s.abc_class in ("A", "B", "C")
            assert s.xyz_class in ("X", "Y", "Z")

    def test_suppliers_csv_pydantic_validation(self, data_dir: Path):
        supp_file = data_dir / "suppliers.csv"
        assert supp_file.exists()

        loaded_supps: list[Supplier] = []
        with open(supp_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                supp = Supplier(
                    supplier_id=row["supplier_id"],
                    name=row["name"],
                    mean_lead_time_days=float(row["mean_lead_time_days"]),
                    std_lead_time_days=float(row["std_lead_time_days"]),
                    on_time_delivery_rate=float(row["on_time_delivery_rate"]),
                    defect_rate=float(row["defect_rate"]),
                    min_order_quantity=int(row["min_order_quantity"]),
                    price_markup_factor=float(row["price_markup_factor"]),
                    order_processing_cost=float(row["order_processing_cost"]),
                    profile_type=SupplierProfileType(row["profile_type"]) if row["profile_type"] else None,
                )
                loaded_supps.append(supp)

        assert len(loaded_supps) == 5
        for s in loaded_supps:
            assert s.mean_lead_time_days > 0.0
            assert 0.0 <= s.on_time_delivery_rate <= 1.0
            assert 0.0 <= s.defect_rate <= 1.0
            assert s.min_order_quantity >= 1

    def test_demand_history_csv_pydantic_validation(self, data_dir: Path):
        demand_file = data_dir / "demand_history.csv"
        assert demand_file.exists()

        record_count = 0
        with open(demand_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rec = DemandRecord(
                    date=date.fromisoformat(row["date"]),
                    sku_id=row["sku_id"],
                    quantity=float(row["quantity"]),
                    is_promotional=row["is_promotional"].lower() in ("true", "1"),
                    is_weekend=row["is_weekend"].lower() in ("true", "1"),
                    stockout_flag=row["stockout_flag"].lower() in ("true", "1"),
                )
                assert rec.quantity >= 0.0
                record_count += 1

        assert record_count == 25 * 730

    def test_warehouse_json_pydantic_validation(self, data_dir: Path):
        wh_file = data_dir / "warehouse.json"
        assert wh_file.exists()

        with open(wh_file, encoding="utf-8") as f:
            data = json.load(f)
        wh = Warehouse.model_validate(data)
        assert wh.warehouse_id == "WH-CENTRAL-01"
        assert wh.total_volume_capacity_m3 == 1000.0
        assert wh.total_weight_capacity_kg == 50000.0
        assert 0.50 <= wh.target_service_level < 1.0

    def test_inventory_state_csv_pydantic_validation_and_effective_stock(self, data_dir: Path):
        state_file = data_dir / "inventory_state.csv"
        assert state_file.exists()

        loaded_states: list[InventoryState] = []
        with open(state_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                st = InventoryState(
                    sku_id=row["sku_id"],
                    on_hand=float(row["on_hand"]),
                    on_order=float(row["on_order"]),
                    allocated=float(row["allocated"]),
                    backorders=float(row["backorders"]),
                    safety_stock=float(row["safety_stock"]) if row["safety_stock"] else None,
                    reorder_point=float(row["reorder_point"]) if row["reorder_point"] else None,
                    max_stock=float(row["max_stock"]) if row["max_stock"] else None,
                    status=StockStatus(row["status"]) if row["status"] else None,
                )
                # Confirm computed property aligns with stored CSV column
                csv_eff = float(row["effective_inventory"])
                assert math.isclose(st.effective_inventory, csv_eff, abs_tol=1e-3)
                loaded_states.append(st)

        assert len(loaded_states) == 25

    def test_generator_programmatic_invariants(self):
        """Verify SyntheticDataGenerator API directly generates self-consistent datasets."""
        gen = SyntheticDataGenerator(seed=42)
        skus, supps, wh, demand, states = gen.generate_all(days=365)
        assert len(skus) == 25
        assert len(supps) == 5
        assert wh.total_volume_capacity_m3 > 0
        assert len(demand) == 25 * 365
        assert len(states) == 25


# =============================================================================
# 5. SUPPLIER EVALUATOR FACADE & RISK DECISION TREE STRESS TESTS
# =============================================================================

class TestEvaluatorAndRiskTreeIntegrity:
    """Tests confirming SupplierEvaluator facade and SupplyRiskDecisionTree."""

    def test_evaluator_methods_monotonicity(self):
        gen = SyntheticDataGenerator(seed=42)
        suppliers = gen.generate_suppliers()
        evaluator = SupplierEvaluator()

        for method in ["TOPSIS", "AHP", "ENTROPY_TOPSIS", "HYBRID", "WSM"]:
            scores = evaluator.evaluate_suppliers(suppliers, method=method)
            assert len(scores) == 5
            for supp_id, score in scores.items():
                assert 0.0 <= score <= 1.0, f"Method {method} produced out of bound score {score} for {supp_id}"
            # Across all methods, Premium Reliable must outperform Budget Volatile
            assert scores["SUP-PREMIUM"] > scores["SUP-BUDGET"]

    def test_decision_tree_breakeven_and_emv(self):
        tree = SupplyRiskDecisionTree()
        res = tree.evaluate_emv()
        assert res["emv_single"] == 112000.0
        assert res["emv_dual"] == 115650.0
        assert res["preferred_strategy"] == "SINGLE_SOURCING"

        p_star = tree.find_breakeven_probability()
        assert math.isclose(p_star, 0.104333, abs_tol=1e-4)
        # At p_star, single EMV matches dual EMV
        emv_at_star = tree.evaluate_emv(p_disrupt_single=p_star)
        assert math.isclose(emv_at_star["emv_single"], emv_at_star["emv_dual"], rel_tol=1e-4)
