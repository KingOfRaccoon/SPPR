"""Milestone 1 Adversarial Empirical Stress Test Suite.

Probes domain models, effective inventory calculation, forward-chaining rule engine,
and ontology under extreme, boundary, adversarial, and high-volume workloads.
"""

import math
import time
from datetime import date

import pytest
from pydantic import ValidationError

from inventory_dss.knowledge.ontology import (
    DomainOntology,
    OntologyClass,
)
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
    InventoryState,
    PurchaseOrder,
    Supplier,
    Warehouse,
)

# ===========================================================================
# 1. DOMAIN MODEL ADVERSARIAL STRESS TESTS
# ===========================================================================

class TestDomainModelAdversarial:
    """Stress tests domain models with invalid, extreme, and malformed inputs."""

    @pytest.mark.parametrize("invalid_price", [
        -100.0, -0.0001, -1e9, 0.0, float("nan"), float("-inf")
    ])
    def test_sku_rejects_non_positive_and_nan_prices(self, invalid_price):
        """SKU price must be strictly positive and finite (> 0)."""
        with pytest.raises(ValidationError):
            SKU(
                sku_id="SKU-ADV-001",
                name="Adversarial Item",
                category="Electronics",
                unit_price=invalid_price,
                unit_volume_m3=0.01,
                unit_weight_kg=1.0,
            )

    def test_sku_infinite_price_behavior(self):
        """EMPIRICAL FINDING: float('inf') bypasses gt=0.0 without raising ValidationError.

        Documents that gt=0.0 allows +inf unless math.isfinite check is explicitly added.
        """
        sku = SKU(
            sku_id="SKU-INF-001",
            name="Infinite Price SKU",
            category="Electronics",
            unit_price=float("inf"),
            unit_volume_m3=0.01,
            unit_weight_kg=1.0,
        )
        assert math.isinf(sku.unit_price), "Currently permitted: unit_price=inf"

    @pytest.mark.parametrize("invalid_vol,invalid_wt", [
        (0.0, 1.0),
        (-0.01, 1.0),
        (-100.0, 1.0),
        (1.0, 0.0),
        (1.0, -0.01),
        (1.0, -100.0),
        (float("nan"), 1.0),
        (1.0, float("nan")),
        (float("-inf"), 1.0),
        (1.0, float("-inf")),
    ])
    def test_sku_rejects_zero_negative_nan_dimensions(self, invalid_vol, invalid_wt):
        """SKU physical dimensions (volume, weight) must be strictly positive."""
        with pytest.raises(ValidationError):
            SKU(
                sku_id="SKU-ADV-002",
                name="Dimension Anomaly Item",
                category="Spare Parts",
                unit_price=100.0,
                unit_volume_m3=invalid_vol,
                unit_weight_kg=invalid_wt,
            )

    def test_sku_infinite_dimensions_behavior(self):
        """EMPIRICAL FINDING: float('inf') for volume/weight bypasses gt=0.0."""
        sku = SKU(
            sku_id="SKU-INF-002",
            name="Infinite Volume SKU",
            category="Spare Parts",
            unit_price=100.0,
            unit_volume_m3=float("inf"),
            unit_weight_kg=float("inf"),
        )
        assert math.isinf(sku.unit_volume_m3)
        assert math.isinf(sku.unit_weight_kg)

    @pytest.mark.parametrize("invalid_category", [
        "", "electronics", "ELECTRONICS", "Furniture", "Chemicals", "123", None
    ])
    def test_sku_rejects_invalid_categories(self, invalid_category):
        """SKU category must strictly conform to allowed literal types."""
        with pytest.raises(ValidationError):
            SKU(
                sku_id="SKU-ADV-003",
                name="Category Anomaly",
                category=invalid_category,  # type: ignore
                unit_price=100.0,
                unit_volume_m3=0.01,
                unit_weight_kg=1.0,
            )

    @pytest.mark.parametrize("invalid_pack_size", [0, -1, -100, 1.5, "one"])
    def test_sku_rejects_invalid_pack_sizes(self, invalid_pack_size):
        """SKU pack size must be an integer >= 1."""
        with pytest.raises(ValidationError):
            SKU(
                sku_id="SKU-ADV-004",
                name="Pack Size Anomaly",
                category="Consumables",
                unit_price=50.0,
                unit_volume_m3=0.001,
                unit_weight_kg=0.1,
                pack_size=invalid_pack_size,  # type: ignore
            )

    @pytest.mark.parametrize("invalid_date", [
        "2025-02-30", "not-a-date", "2025/12/31", "15-06-2025", 123456789, None
    ])
    def test_demand_record_rejects_invalid_date_formats(self, invalid_date):
        """DemandRecord date must parse to a valid calendar date."""
        with pytest.raises(ValidationError):
            DemandRecord(
                date=invalid_date,  # type: ignore
                sku_id="SKU-ELEC-001",
                quantity=10.0,
            )

    @pytest.mark.parametrize("invalid_quantity", [-0.001, -1.0, -1000.0, float("-inf")])
    def test_demand_record_rejects_negative_quantities(self, invalid_quantity):
        """Demand quantity cannot be negative."""
        with pytest.raises(ValidationError):
            DemandRecord(
                date=date(2025, 6, 15),
                sku_id="SKU-ELEC-001",
                quantity=invalid_quantity,
            )

    @pytest.mark.parametrize("invalid_rate", [-0.01, 1.01, 2.5, -10.0, float("nan")])
    def test_supplier_rejects_out_of_bounds_reliability_rates(self, invalid_rate):
        """OTIF and defect rates must be strictly within [0.0, 1.0]."""
        with pytest.raises(ValidationError):
            Supplier(
                supplier_id="SUP-ADV-01",
                name="Out of bounds supplier",
                mean_lead_time_days=5.0,
                std_lead_time_days=1.0,
                on_time_delivery_rate=invalid_rate,
                defect_rate=0.01,
                min_order_quantity=10,
            )
        with pytest.raises(ValidationError):
            Supplier(
                supplier_id="SUP-ADV-02",
                name="Out of bounds supplier 2",
                mean_lead_time_days=5.0,
                std_lead_time_days=1.0,
                on_time_delivery_rate=0.95,
                defect_rate=invalid_rate,
                min_order_quantity=10,
            )

    @pytest.mark.parametrize("invalid_moq", [0, -1, -50])
    def test_supplier_rejects_non_positive_moq(self, invalid_moq):
        """Supplier MOQ must be >= 1."""
        with pytest.raises(ValidationError):
            Supplier(
                supplier_id="SUP-ADV-03",
                name="Zero MOQ supplier",
                mean_lead_time_days=5.0,
                std_lead_time_days=1.0,
                on_time_delivery_rate=0.95,
                defect_rate=0.01,
                min_order_quantity=invalid_moq,
            )

    @pytest.mark.parametrize("invalid_service_level", [0.0, 0.49, 1.0, 1.1, -0.5])
    def test_warehouse_rejects_invalid_service_levels(self, invalid_service_level):
        """Target cycle service level must be in [0.50, 1.0)."""
        with pytest.raises(ValidationError):
            Warehouse(
                warehouse_id="WH-ADV",
                name="Adversarial Warehouse",
                total_volume_capacity_m3=1000.0,
                total_weight_capacity_kg=50000.0,
                target_service_level=invalid_service_level,
            )

    def test_purchase_order_allows_delivery_before_order_date(self):
        """EMPIRICAL FINDING: PurchaseOrder does not check expected_delivery_date >= order_date."""
        po = PurchaseOrder(
            order_id="PO-ANOMALY-01",
            sku_id="SKU-01",
            supplier_id="SUP-01",
            quantity=100.0,
            unit_price=50.0,
            total_cost=5000.0,
            order_date=date(2025, 6, 15),
            expected_delivery_date=date(2025, 6, 10),
        )
        assert po.expected_delivery_date < po.order_date


# ===========================================================================
# 2. EFFECTIVE INVENTORY STRESS & ORACLE TESTS
# ===========================================================================

class TestEffectiveInventoryCalculation:
    """Stress tests effective inventory calculation under multi-unit allocations and backorders."""

    def test_effective_inventory_exact_oracle_formula(self):
        """Mathematical oracle: I_eff = on_hand + on_order - allocated - backorders."""
        test_cases = [
            # (on_hand, on_order, allocated, backorders, expected)
            (100.0, 50.0, 20.0, 10.0, 120.0),
            (0.0, 0.0, 0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0, 100.0, -100.0),            # Pure backorders
            (50.0, 0.0, 100.0, 0.0, -50.0),            # Allocation deficit
            (10.0, 20.0, 50.0, 40.0, -60.0),           # Negative stock under multi-unit allocations & backorders
            (1000.0, 500.0, 1200.0, 300.0, 0.0),       # Exact zero boundary
            (1e7, 5e6, 2e6, 1e6, 1.2e7),                # Large scale inventory numbers
            (10.3333, 5.2500, 3.1250, 1.4583, 11.0),    # Fractional / decimal precision
        ]
        for oh, oo, alloc, bo, expected in test_cases:
            state = InventoryState(
                sku_id="SKU-ORACLE",
                on_hand=oh,
                on_order=oo,
                allocated=alloc,
                backorders=bo,
            )
            calculated = state.effective_inventory
            assert math.isclose(calculated, expected, abs_tol=1e-4), (
                f"Mismatch for inputs ({oh}, {oo}, {alloc}, {bo}): "
                f"got {calculated}, expected {expected}"
            )

    def test_physical_on_hand_cannot_be_negative(self):
        """Physical on_hand is physically bounded below by 0 (backorders capture negative balances)."""
        with pytest.raises(ValidationError):
            InventoryState(
                sku_id="SKU-NEG",
                on_hand=-5.0,
                on_order=0.0,
                allocated=0.0,
                backorders=0.0,
            )

    def test_effective_inventory_randomized_invariants(self):
        """Fuzz testing: verify monotonicity and linear additive property across 500 random tuples."""
        import random
        rng = random.Random(42)
        for _ in range(500):
            oh = round(rng.uniform(0, 10000), 2)
            oo = round(rng.uniform(0, 5000), 2)
            alloc = round(rng.uniform(0, 8000), 2)
            bo = round(rng.uniform(0, 4000), 2)

            state = InventoryState(sku_id="SKU-FUZZ", on_hand=oh, on_order=oo, allocated=alloc, backorders=bo)
            expected = round(oh + oo - alloc - bo, 4)
            assert state.effective_inventory == expected

            # Invariant: increasing backorders strictly decreases or maintains effective inventory
            state_more_bo = InventoryState(sku_id="SKU-FUZZ", on_hand=oh, on_order=oo, allocated=alloc, backorders=bo + 10.0)
            assert state_more_bo.effective_inventory < state.effective_inventory

            # Invariant: increasing on_order strictly increases effective inventory
            state_more_oo = InventoryState(sku_id="SKU-FUZZ", on_hand=oh, on_order=oo + 15.0, allocated=alloc, backorders=bo)
            assert state_more_oo.effective_inventory > state.effective_inventory


# ===========================================================================
# 3. KNOWLEDGE BASE FORWARD CHAINING STRESS TESTS
# ===========================================================================

class TestKnowledgeBaseForwardChaining:
    """Stress tests the production rule engine for cycles, conflicts, multi-firings, and scaling."""

    def test_multi_rule_batch_firings(self):
        """Verify engine correctly fires rules across a batch of 40 heterogeneous SKUs."""
        engine = build_inventory_rule_engine()
        wm = WorkingMemory()

        for i in range(10):
            wm.assert_fact(Fact(
                name="InventoryStateFact",
                payload={"sku_id": f"SKU-CRIT-{i}", "effective_inventory": 10.0, "safety_stock": 25.0, "reorder_point": 60.0, "max_stock": 150.0}
            ))
            wm.assert_fact(Fact(
                name="InventoryStateFact",
                payload={"sku_id": f"SKU-REORD-{i}", "effective_inventory": 40.0, "safety_stock": 20.0, "reorder_point": 50.0, "max_stock": 150.0}
            ))
            wm.assert_fact(Fact(
                name="InventoryStateFact",
                payload={"sku_id": f"SKU-OPT-{i}", "effective_inventory": 90.0, "safety_stock": 20.0, "reorder_point": 50.0, "max_stock": 150.0}
            ))
            wm.assert_fact(Fact(
                name="InventoryStateFact",
                payload={"sku_id": f"SKU-EXC-{i}", "effective_inventory": 200.0, "safety_stock": 20.0, "reorder_point": 50.0, "max_stock": 150.0}
            ))

        report = engine.run(wm, max_cycles=100)

        classifications = wm.get_facts_by_name("StockClassificationFact")
        assert len(classifications) == 40
        assert report.rules_fired_count == 40

        crit_count = sum(1 for c in classifications if c.get("status") == "CRITICAL")
        reord_count = sum(1 for c in classifications if c.get("status") == "REORDER_NEEDED")
        opt_count = sum(1 for c in classifications if c.get("status") == "OPTIMAL")
        exc_count = sum(1 for c in classifications if c.get("status") == "EXCESS")

        assert crit_count == 10
        assert reord_count == 10
        assert opt_count == 10
        assert exc_count == 10

        alerts = wm.get_facts_by_name("AlertFact")
        crit_alerts = [a for a in alerts if a.get("level") == "CRITICAL"]
        assert len(crit_alerts) == 10

    def test_chained_multi_step_inference(self):
        """Verify sequential multi-rule inference chain: Stock Critical -> Emergency Sourcing -> Lot Sizing."""
        engine = build_inventory_rule_engine()
        wm = WorkingMemory()

        wm.assert_fact(Fact(
            name="InventoryStateFact",
            payload={"sku_id": "SKU-CHAIN-01", "effective_inventory": -5.0, "safety_stock": 30.0, "reorder_point": 70.0}
        ))
        wm.assert_fact(Fact(
            name="SupplierFact",
            payload={"supplier_id": "SUP-SLOW", "name": "Slow Overseas", "is_primary_for": "SKU-CHAIN-01", "mean_lead_time_days": 18.0}
        ))
        wm.assert_fact(Fact(
            name="SupplierFact",
            payload={"supplier_id": "SUP-EXPRESS", "name": "Local Express", "profile_type": "LOCAL_EXPRESS", "mean_lead_time_days": 1.5}
        ))
        wm.assert_fact(Fact(
            name="RawOrderProposalFact",
            payload={"sku_id": "SKU-CHAIN-01", "quantity": 42.0, "pack_size": 10, "moq": 50}
        ))

        report = engine.run(wm, max_cycles=20)

        fired_rules = [t.rule_id for t in report.execution_traces]
        assert "RULE_STOCK_CRITICAL" in fired_rules
        assert "RULE_EMERGENCY_SOURCING" in fired_rules
        assert "RULE_LOT_SIZING_ALIGNMENT" in fired_rules

        crit_idx = fired_rules.index("RULE_STOCK_CRITICAL")
        emerg_idx = fired_rules.index("RULE_EMERGENCY_SOURCING")
        lot_idx = fired_rules.index("RULE_LOT_SIZING_ALIGNMENT")
        assert crit_idx < emerg_idx < lot_idx

        aligned = wm.get_facts_by_name("AlignedOrderFact")[0]
        assert aligned.get("aligned_quantity") == 50.0

        emergency_fact = wm.get_facts_by_name("EmergencySourcingFact")[0]
        assert emergency_fact.get("recommended_supplier_id") == "SUP-EXPRESS"

    def test_cycle_prevention_and_refraction(self):
        """Adversarial stress test: create a circular dependency between two rules."""
        engine = RuleEngine()
        wm = WorkingMemory()

        def cond_ping(wm: WorkingMemory):
            matches = []
            for f in wm.get_facts_by_name("FactPing"):
                matches.append({"val": f.get("val"), "_matched_fact_ids": [f.id]})
            return matches

        def act_ping(wm: WorkingMemory, bindings, asserted):
            val = bindings["val"]
            pong = Fact(name="FactPong", payload={"val": val})
            wm.assert_fact(pong)
            asserted.append(pong)
            return f"Ping({val}) -> Pong({val})"

        def cond_pong(wm: WorkingMemory):
            matches = []
            for f in wm.get_facts_by_name("FactPong"):
                matches.append({"val": f.get("val"), "_matched_fact_ids": [f.id]})
            return matches

        def act_pong(wm: WorkingMemory, bindings, asserted):
            val = bindings["val"]
            ping = Fact(name="FactPing", payload={"val": val})
            wm.assert_fact(ping)
            asserted.append(ping)
            return f"Pong({val}) -> Ping({val})"

        engine.register_rule(Rule("RULE_PING", "Ping", priority=50, condition=cond_ping, action=act_ping))
        engine.register_rule(Rule("RULE_PONG", "Pong", priority=50, condition=cond_pong, action=act_pong))

        wm.assert_fact(Fact(name="FactPing", payload={"val": 1}))

        start = time.perf_counter()
        report = engine.run(wm, max_cycles=100)
        elapsed = time.perf_counter() - start

        assert report.rules_fired_count == 2
        assert elapsed < 0.1, "Refraction should immediately stop cycle"

    def test_adversarial_infinite_loop_safety_cap(self):
        """Construct an evolving cycle and verify max_cycles halts execution."""
        engine = RuleEngine()
        wm = WorkingMemory()

        def cond_ping(wm: WorkingMemory):
            matches = []
            for f in wm.get_facts_by_name("FactPing"):
                matches.append({"n": f.get("n"), "_matched_fact_ids": [f.id]})
            return matches

        def act_ping(wm: WorkingMemory, bindings, asserted):
            n = bindings["n"]
            pong = Fact(name="FactPong", payload={"n": n + 1})
            wm.assert_fact(pong)
            asserted.append(pong)
            return f"Ping({n}) -> Pong({n+1})"

        def cond_pong(wm: WorkingMemory):
            matches = []
            for f in wm.get_facts_by_name("FactPong"):
                matches.append({"n": f.get("n"), "_matched_fact_ids": [f.id]})
            return matches

        def act_pong(wm: WorkingMemory, bindings, asserted):
            n = bindings["n"]
            ping = Fact(name="FactPing", payload={"n": n + 1})
            wm.assert_fact(ping)
            asserted.append(ping)
            return f"Pong({n}) -> Ping({n+1})"

        engine.register_rule(Rule("RULE_EVOLVING_PING", "Evolving Ping", priority=50, condition=cond_ping, action=act_ping))
        engine.register_rule(Rule("RULE_EVOLVING_PONG", "Evolving Pong", priority=50, condition=cond_pong, action=act_pong))

        wm.assert_fact(Fact(name="FactPing", payload={"n": 0}))

        max_limit = 25
        start = time.perf_counter()
        report = engine.run(wm, max_cycles=max_limit)
        elapsed = time.perf_counter() - start

        assert report.cycles_executed == max_limit
        assert report.rules_fired_count == max_limit
        assert elapsed < 0.5, "Infinite loop guard must terminate promptly"

    def test_conflicting_rules_conflict_resolution(self):
        """Two rules matching the exact same fact with differing priorities."""
        engine = RuleEngine()
        wm = WorkingMemory()

        def cond_common(wm: WorkingMemory):
            matches = []
            for f in wm.get_facts_by_name("AmbiguousFact"):
                matches.append({"val": f.get("val"), "_matched_fact_ids": [f.id]})
            return matches

        def act_high(wm: WorkingMemory, bindings, asserted):
            fact = Fact(name="ResolvedFact", payload={"winner": "HIGH_PRIORITY"})
            wm.assert_fact(fact)
            asserted.append(fact)
            return "High priority won"

        def act_low(wm: WorkingMemory, bindings, asserted):
            fact = Fact(name="ResolvedFact", payload={"winner": "LOW_PRIORITY"})
            wm.assert_fact(fact)
            asserted.append(fact)
            return "Low priority won"

        engine.register_rule(Rule("RULE_HIGH", "High", priority=90, condition=cond_common, action=act_high))
        engine.register_rule(Rule("RULE_LOW", "Low", priority=20, condition=cond_common, action=act_low))

        wm.assert_fact(Fact(name="AmbiguousFact", payload={"val": 42}))

        report = engine.run(wm, max_cycles=10)
        assert report.rules_fired_count == 2
        assert report.execution_traces[0].rule_id == "RULE_HIGH"
        assert report.execution_traces[1].rule_id == "RULE_LOW"

    def test_default_max_cycles_truncates_large_batches_silently(self):
        """EMPIRICAL FINDING: batches > 50 facts are silently truncated under default max_cycles=50."""
        engine = build_inventory_rule_engine()
        wm = WorkingMemory()
        batch_size = 60

        for i in range(batch_size):
            wm.assert_fact(Fact(
                name="InventoryStateFact",
                payload={"sku_id": f"SKU-TRUNC-{i:04d}", "effective_inventory": 10.0, "safety_stock": 20.0, "reorder_point": 50.0, "max_stock": 100.0}
            ))

        report = engine.run(wm)
        classifications = wm.get_facts_by_name("StockClassificationFact")

        assert len(classifications) == 50
        assert report.cycles_executed == 50
        assert report.rules_fired_count == 50

    @pytest.mark.parametrize("batch_size", [10, 25, 50, 100])
    def test_working_memory_batch_scaling_profile(self, batch_size):
        """Empirically measure inference execution time under increasing batch sizes."""
        engine = build_inventory_rule_engine()
        wm = WorkingMemory()

        for i in range(batch_size):
            eff = 10.0 + (i % 150)
            ss = 30.0
            rop = 70.0
            max_s = 150.0
            wm.assert_fact(Fact(
                name="InventoryStateFact",
                payload={"sku_id": f"SKU-SCALE-{i:04d}", "effective_inventory": eff, "safety_stock": ss, "reorder_point": rop, "max_stock": max_s}
            ))

        start = time.perf_counter()
        report = engine.run(wm, max_cycles=batch_size + 20)
        elapsed = time.perf_counter() - start

        classifications = wm.get_facts_by_name("StockClassificationFact")
        assert len(classifications) == batch_size
        assert report.rules_fired_count == batch_size

        throughput = batch_size / elapsed if elapsed > 0 else float("inf")
        assert throughput > 300.0, f"Throughput too low: {throughput:.1f} facts/sec (elapsed={elapsed:.4f}s for {batch_size} facts)"


# ===========================================================================
# 4. ONTOLOGY REASONING & CONSISTENCY STRESS TESTS
# ===========================================================================

class TestOntologyReasoningAdversarial:
    """Stress tests taxonomy traversal, circular inheritance, and consistency validator."""

    def test_deep_taxonomy_hierarchy_traversal(self):
        """Construct a 50-level deep inheritance chain and traverse ancestors and descendants."""
        onto = DomainOntology("DeepOntology")
        onto.add_class(OntologyClass(id="Level_00", name="Root", description="Root level"))
        for i in range(1, 51):
            parent = f"Level_{i-1:02d}"
            child = f"Level_{i:02d}"
            onto.add_class(OntologyClass(id=child, name=f"Level {i}", description="Desc", parent_id=parent))

        errors = onto.validate_consistency()
        assert len(errors) == 0

        assert onto.is_subclass_of("Level_50", "Level_00") is True
        assert onto.is_subclass_of("Level_25", "Level_00") is True
        assert onto.is_subclass_of("Level_00", "Level_50") is False

        superclasses = onto.get_superclasses("Level_50")
        assert len(superclasses) == 50
        assert superclasses[-1].id == "Level_00"

        subclasses = onto.get_subclasses("Level_45")
        assert len(subclasses) == 5

    def test_circular_inheritance_detection_without_infinite_recursion(self):
        """Construct a cycle A -> B -> C -> A. Verify validate_consistency and get_superclasses survive."""
        onto = DomainOntology("CircularOntology")
        onto.add_class(OntologyClass(id="ClassA", name="A", description="A", parent_id="ClassC"))
        onto.add_class(OntologyClass(id="ClassB", name="B", description="B", parent_id="ClassA"))
        onto.add_class(OntologyClass(id="ClassC", name="C", description="C", parent_id="ClassB"))

        superclasses_a = onto.get_superclasses("ClassA")
        assert len(superclasses_a) <= 3

        errors = onto.validate_consistency()
        assert any("Circular inheritance detected" in e for e in errors)
