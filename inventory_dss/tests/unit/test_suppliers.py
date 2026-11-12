"""Unit tests for supplier MCDA evaluation: AHP, Entropy, TOPSIS, and Risk Decision Trees."""

from __future__ import annotations

import math

import numpy as np
import pytest

from inventory_dss.models.domain import Supplier, SupplierProfileType
from inventory_dss.suppliers.ahp import DEFAULT_PAIRWISE_MATRIX, AHPEngine
from inventory_dss.suppliers.entropy import EntropyWeightEngine
from inventory_dss.suppliers.evaluator import SupplierEvaluator
from inventory_dss.suppliers.risk_trees import SupplyRiskDecisionTree
from inventory_dss.suppliers.topsis import TOPSISSolver


@pytest.fixture
def test_suppliers() -> list[Supplier]:
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


class TestAHPEngine:
    """Tests for Saaty Analytic Hierarchy Process criteria weighting and consistency."""

    def test_default_matrix_consistency_ratio_under_threshold(self):
        weights, lambda_max, cr = AHPEngine.compute_weights(DEFAULT_PAIRWISE_MATRIX)
        assert len(weights) == 6
        assert math.isclose(float(np.sum(weights)), 1.0, rel_tol=1e-5)
        assert np.all(weights > 0.0)
        assert lambda_max >= 6.0
        # Mandatory Saaty standard: CR must be strictly under 0.10
        assert cr < 0.10, f"Consistency ratio {cr:.4f} exceeds 0.10"
        assert cr < 0.02, f"Expected highly consistent matrix (got CR={cr:.4f})"

    def test_validate_consistency_method(self):
        assert AHPEngine.validate_consistency(DEFAULT_PAIRWISE_MATRIX, threshold=0.10) is True

        # Highly inconsistent matrix
        inconsistent = np.array([
            [1.0, 9.0, 1 / 9.0],
            [1 / 9.0, 1.0, 9.0],
            [9.0, 1 / 9.0, 1.0],
        ])
        assert AHPEngine.validate_consistency(inconsistent, threshold=0.10) is False

    def test_single_criterion_boundary(self):
        single_m = np.array([[1.0]])
        w, l_max, cr = AHPEngine.compute_weights(single_m)
        assert list(w) == [1.0]
        assert l_max == 1.0
        assert cr == 0.0

    def test_geometric_mean_approximation_alignment(self):
        eig_w, _, _ = AHPEngine.compute_weights(DEFAULT_PAIRWISE_MATRIX)
        geom_w = AHPEngine.compute_geometric_mean_weights(DEFAULT_PAIRWISE_MATRIX)
        # Geometric mean approximation must closely track principal eigenvector (< 0.02 delta)
        np.testing.assert_allclose(eig_w, geom_w, atol=0.02)


class TestEntropyWeightEngine:
    """Tests for objective Shannon Entropy Weight Method."""

    def test_entropy_weights_properties(self, test_suppliers: list[Supplier]):
        X, _, _ = SupplierEvaluator._extract_decision_matrix(test_suppliers)
        w = EntropyWeightEngine.compute_entropy_weights(X)

        assert len(w) == X.shape[1]
        assert math.isclose(float(np.sum(w)), 1.0, rel_tol=1e-5)
        assert np.all(w >= 0.0)

    def test_uniform_criteria_yields_uniform_weights(self):
        # All suppliers have identical metrics
        uniform_X = np.ones((5, 4)) * 10.0
        w = EntropyWeightEngine.compute_entropy_weights(uniform_X)
        expected = np.full(4, 0.25)
        np.testing.assert_allclose(w, expected, atol=1e-5)

    def test_high_dispersion_criterion_receives_higher_weight(self):
        # Column 0 has high variance across suppliers; Column 1 is almost constant
        X = np.array([
            [1.0, 10.0],
            [10.0, 10.1],
            [100.0, 10.0],
            [1000.0, 9.9],
        ])
        w = EntropyWeightEngine.compute_entropy_weights(X)
        assert w[0] > w[1], "Criterion with higher dispersion must receive higher entropy weight"


class TestTOPSISSolver:
    """Tests for TOPSIS vector normalization, ideal distances, and ranking."""

    def test_closeness_bounded_in_unit_interval(self):
        X = np.array([
            [10.0, 2.0],
            [20.0, 4.0],
            [15.0, 3.0],
        ])
        w = np.array([0.5, 0.5])
        is_benefit = [False, True]  # min, max

        closeness = TOPSISSolver.solve(X, w, is_benefit)
        assert len(closeness) == 3
        for c in closeness:
            assert 0.0 <= c <= 1.0

    def test_dominance_monotonicity(self):
        # Alternative 0 strictly dominates Alternative 1 across both criteria (cost lower, benefit higher)
        X = np.array([
            [5.0, 100.0],  # Superior: lower cost (5 vs 20), higher benefit (100 vs 50)
            [20.0, 50.0],  # Inferior
        ])
        w = np.array([0.5, 0.5])
        is_benefit = [False, True]

        scores = TOPSISSolver.solve(X, w, is_benefit)
        assert scores[0] > scores[1], "Dominant alternative must have strictly higher TOPSIS score"

    def test_single_alternative_boundary(self):
        X = np.array([[10.0, 5.0]])
        w = np.array([0.5, 0.5])
        is_benefit = [False, True]

        scores = TOPSISSolver.solve(X, w, is_benefit)
        assert scores[0] == 1.0


class TestSupplyRiskDecisionTree:
    """Tests for supply disruption modeling and decision criteria under uncertainty."""

    @pytest.fixture
    def tree(self) -> SupplyRiskDecisionTree:
        return SupplyRiskDecisionTree()

    def test_emv_baseline_calculation(self, tree: SupplyRiskDecisionTree):
        # S1: (1-0.08)*100k + 0.08*250k = 92000 + 20000 = 112000
        # S1+S2: (1-0.01)*115k + 0.01*180k = 113850 + 1800 = 115650
        res = tree.evaluate_emv()
        assert res["emv_single"] == 112000.0
        assert res["emv_dual"] == 115650.0
        assert res["preferred_strategy"] == "SINGLE_SOURCING"
        assert res["cost_difference"] == 3650.0

    def test_catastrophic_disruption_reverses_decision(self, tree: SupplyRiskDecisionTree):
        # If disruption cost climbs to 400k for single sourcing:
        # EMV single = 0.92*100k + 0.08*400k = 92k + 32k = 124k > 115.65k
        res = tree.evaluate_emv(cost_disrupt_single=400000.0)
        assert res["emv_single"] == 124000.0
        assert res["preferred_strategy"] == "DUAL_SOURCING"

    def test_breakeven_disruption_probability(self, tree: SupplyRiskDecisionTree):
        p_star = tree.find_breakeven_probability()
        # At p_star, EMV(single) must equal EMV(dual)
        res = tree.evaluate_emv(p_disrupt_single=p_star)
        assert math.isclose(res["emv_single"], res["emv_dual"], rel_tol=1e-4)

    def test_uncertainty_criteria_evaluations(self, tree: SupplyRiskDecisionTree):
        crit = tree.evaluate_uncertainty_criteria(hurwicz_alpha=0.6)
        # Wald minimax cost prefers Dual Sourcing because worst-case 180k < 250k
        assert crit["wald"]["preferred"] == "Dual_Sourcing"
        # Optimistic minimin cost prefers Single Sourcing because best-case 100k < 115k
        assert crit["optimistic"]["preferred"] == "Single_Sourcing"
        # Savage minimax regret
        assert "savage" in crit
        assert crit["savage"]["scores"]["Dual_Sourcing"] <= 30000.0


class TestSupplierEvaluatorFacade:
    """Tests for the high-level SupplierEvaluator facade."""

    def test_evaluate_suppliers_topsis_ranking(self, test_suppliers: list[Supplier]):
        evaluator = SupplierEvaluator()
        scores = evaluator.evaluate_suppliers(test_suppliers, method="TOPSIS")

        assert len(scores) == 5
        for supp_id, score in scores.items():
            assert 0.0 <= score <= 1.0, f"Score for {supp_id} out of bounds: {score}"

        # Reliable premium and local express suppliers must outperform volatile budget supplier
        assert scores["SUP-PREMIUM"] > scores["SUP-BUDGET"]
        assert scores["SUP-LOCAL"] > scores["SUP-BUDGET"]

    def test_evaluate_suppliers_entropy_and_wsm_methods(self, test_suppliers: list[Supplier]):
        evaluator = SupplierEvaluator()

        scores_entropy = evaluator.evaluate_suppliers(test_suppliers, method="ENTROPY_TOPSIS")
        assert len(scores_entropy) == 5
        for s in scores_entropy.values():
            assert 0.0 <= s <= 1.0

        scores_wsm = evaluator.evaluate_suppliers(test_suppliers, method="WSM")
        assert len(scores_wsm) == 5
        for s in scores_wsm.values():
            assert 0.0 <= s <= 1.0

        scores_hybrid = evaluator.evaluate_suppliers(test_suppliers, method="HYBRID")
        assert len(scores_hybrid) == 5

    def test_rank_suppliers_output_structure(self, test_suppliers: list[Supplier]):
        evaluator = SupplierEvaluator()
        ranked = evaluator.rank_suppliers(test_suppliers, method="TOPSIS")

        assert len(ranked) == 5
        assert ranked[0]["rank"] == 1
        assert ranked[-1]["rank"] == 5
        # Verify monotonically descending scores
        for i in range(len(ranked) - 1):
            assert ranked[i]["score"] >= ranked[i + 1]["score"]

    def test_edge_case_empty_and_single_supplier(self, test_suppliers: list[Supplier]):
        evaluator = SupplierEvaluator()
        assert evaluator.evaluate_suppliers([]) == {}

        single = test_suppliers[:1]
        res = evaluator.evaluate_suppliers(single)
        assert res == {"SUP-PREMIUM": 1.0}
