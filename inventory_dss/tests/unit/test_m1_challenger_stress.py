"""Empirical stress-testing and boundary verification suite for Milestone 1.

Authored by challenger_m1_2 (empirical challenger).
Verifies:
1. Pydantic domain models boundary conditions and negative input rejection:
   - SKU: pack_size (0, negative, non-integer), unit_volume_m3 <= 0, unit_weight_kg <= 0, NaN values.
   - Supplier: defect_rate outside [0, 1], on_time_delivery_rate outside [0, 1], lead times, MOQ <= 0.
   - Warehouse: total_volume_capacity_m3 <= 0, total_weight_capacity_kg <= 0, target_service_level limits.
   - InventoryState: effective inventory under extreme commitments and deep backorders.
2. Knowledge engine production rules:
   - Salience / priority ordering and conflict resolution.
   - Specificity conflict resolution.
   - Refraction guarantee and max_cycles termination protection.
   - Working memory state integrity, fact deduplication, and high-load stress (2,000 facts).
   - Domain rule cascade across all 8 canonical inventory rules.
   - Exact interval partitioning of stock status across 14 boundary probe points.
"""

import pytest
from pydantic import ValidationError

from inventory_dss.knowledge.rules import (
    Fact,
    Rule,
    RuleEngine,
    WorkingMemory,
    build_inventory_rule_engine,
)
from inventory_dss.models.domain import (
    SKU,
    InventoryState,
    Supplier,
    Warehouse,
)

# ===========================================================================
# 1. Domain Models Boundary & Stress Tests
# ===========================================================================

class TestSKUModelBoundaryAndAdversarial:
    """Adversarial and boundary test cases for SKU domain entity."""

    @pytest.mark.parametrize("invalid_pack_size", [0, -1, -10, -999])
    def test_pack_size_zero_or_negative_raises_error(self, invalid_pack_size):
        with pytest.raises(ValidationError) as exc_info:
            SKU(
                sku_id="SKU-ADV-001",
                name="Test Adversarial",
                category="Electronics",
                unit_price=100.0,
                unit_volume_m3=0.01,
                unit_weight_kg=1.0,
                pack_size=invalid_pack_size,
            )
        assert "pack_size" in str(exc_info.value)

    @pytest.mark.parametrize("invalid_volume", [0.0, -0.0001, -1.0, -100.0])
    def test_unit_volume_zero_or_negative_raises_error(self, invalid_volume):
        with pytest.raises(ValidationError) as exc_info:
            SKU(
                sku_id="SKU-ADV-002",
                name="Zero Volume SKU",
                category="Spare Parts",
                unit_price=50.0,
                unit_volume_m3=invalid_volume,
                unit_weight_kg=1.0,
            )
        assert "unit_volume_m3" in str(exc_info.value)

    @pytest.mark.parametrize("invalid_weight", [0.0, -0.0001, -5.0, -500.0])
    def test_unit_weight_zero_or_negative_raises_error(self, invalid_weight):
        with pytest.raises(ValidationError) as exc_info:
            SKU(
                sku_id="SKU-ADV-003",
                name="Zero Weight SKU",
                category="Raw Materials",
                unit_price=200.0,
                unit_volume_m3=0.05,
                unit_weight_kg=invalid_weight,
            )
        assert "unit_weight_kg" in str(exc_info.value)

    @pytest.mark.parametrize("invalid_price", [0.0, -0.01, -1000.0])
    def test_unit_price_zero_or_negative_raises_error(self, invalid_price):
        with pytest.raises(ValidationError) as exc_info:
            SKU(
                sku_id="SKU-ADV-004",
                name="Negative Price SKU",
                category="Consumables",
                unit_price=invalid_price,
                unit_volume_m3=0.01,
                unit_weight_kg=0.5,
            )
        assert "unit_price" in str(exc_info.value)

    @pytest.mark.parametrize("invalid_holding_rate", [-0.01, 0.0, 0.005, 1.01, 2.5])
    def test_holding_cost_annual_rate_bounds(self, invalid_holding_rate):
        with pytest.raises(ValidationError) as exc_info:
            SKU(
                sku_id="SKU-ADV-005",
                name="Invalid Holding Rate",
                category="Electronics",
                unit_price=100.0,
                holding_cost_annual_rate=invalid_holding_rate,
                unit_volume_m3=0.01,
                unit_weight_kg=1.0,
            )
        assert "holding_cost_annual_rate" in str(exc_info.value)

    def test_nan_values_rejected(self):
        with pytest.raises(ValidationError):
            SKU(
                sku_id="SKU-ADV-006",
                name="NaN SKU",
                category="Electronics",
                unit_price=float("nan"),
                unit_volume_m3=0.01,
                unit_weight_kg=1.0,
            )

    def test_valid_extreme_boundaries(self):
        sku = SKU(
            sku_id="SKU-EXTREME-001",
            name="Microscopic SKU",
            category="Consumables",
            unit_price=0.01,
            holding_cost_annual_rate=0.01,
            unit_volume_m3=1e-6,
            unit_weight_kg=1e-6,
            pack_size=1,
        )
        assert sku.unit_volume_m3 == 1e-6
        assert sku.unit_weight_kg == 1e-6
        assert sku.pack_size == 1


class TestSupplierModelBoundaryAndAdversarial:
    """Adversarial and boundary test cases for Supplier domain entity."""

    @pytest.mark.parametrize("invalid_defect_rate", [-0.5, -0.0001, 1.0001, 1.5, 10.0])
    def test_defect_rate_out_of_bounds_raises_error(self, invalid_defect_rate):
        with pytest.raises(ValidationError) as exc_info:
            Supplier(
                supplier_id="SUP-ERR-01",
                name="Erroneous Defect Supplier",
                mean_lead_time_days=7.0,
                std_lead_time_days=1.0,
                on_time_delivery_rate=0.95,
                defect_rate=invalid_defect_rate,
                min_order_quantity=10,
            )
        assert "defect_rate" in str(exc_info.value)

    @pytest.mark.parametrize("invalid_otif_rate", [-0.5, -0.0001, 1.0001, 1.1, 5.0])
    def test_otif_rate_out_of_bounds_raises_error(self, invalid_otif_rate):
        with pytest.raises(ValidationError) as exc_info:
            Supplier(
                supplier_id="SUP-ERR-02",
                name="Erroneous OTIF Supplier",
                mean_lead_time_days=7.0,
                std_lead_time_days=1.0,
                on_time_delivery_rate=invalid_otif_rate,
                defect_rate=0.02,
                min_order_quantity=10,
            )
        assert "on_time_delivery_rate" in str(exc_info.value)

    @pytest.mark.parametrize("rate_boundary", [0.0, 1.0])
    def test_exact_rate_boundaries_accepted(self, rate_boundary):
        sup = Supplier(
            supplier_id=f"SUP-BOUND-{rate_boundary}",
            name=f"Boundary Supplier {rate_boundary}",
            mean_lead_time_days=5.0,
            std_lead_time_days=0.0,
            on_time_delivery_rate=rate_boundary,
            defect_rate=rate_boundary,
            min_order_quantity=1,
        )
        assert sup.on_time_delivery_rate == rate_boundary
        assert sup.defect_rate == rate_boundary

    @pytest.mark.parametrize("invalid_lead_time", [0.0, -0.01, -10.0])
    def test_mean_lead_time_zero_or_negative_raises_error(self, invalid_lead_time):
        with pytest.raises(ValidationError) as exc_info:
            Supplier(
                supplier_id="SUP-ERR-03",
                name="Instant Supplier",
                mean_lead_time_days=invalid_lead_time,
                std_lead_time_days=1.0,
                on_time_delivery_rate=0.90,
                defect_rate=0.01,
                min_order_quantity=10,
            )
        assert "mean_lead_time_days" in str(exc_info.value)

    @pytest.mark.parametrize("invalid_moq", [0, -1, -50])
    def test_moq_zero_or_negative_raises_error(self, invalid_moq):
        with pytest.raises(ValidationError) as exc_info:
            Supplier(
                supplier_id="SUP-ERR-04",
                name="Negative MOQ Supplier",
                mean_lead_time_days=5.0,
                std_lead_time_days=1.0,
                on_time_delivery_rate=0.90,
                defect_rate=0.01,
                min_order_quantity=invalid_moq,
            )
        assert "min_order_quantity" in str(exc_info.value)


class TestWarehouseModelBoundaryAndAdversarial:
    """Adversarial and boundary test cases for Warehouse domain entity."""

    @pytest.mark.parametrize("invalid_vol", [0.0, -0.001, -100.0])
    def test_warehouse_volume_zero_or_negative_raises_error(self, invalid_vol):
        with pytest.raises(ValidationError) as exc_info:
            Warehouse(
                warehouse_id="WH-ERR-01",
                name="Zero Volume WH",
                total_volume_capacity_m3=invalid_vol,
                total_weight_capacity_kg=10000.0,
            )
        assert "total_volume_capacity_m3" in str(exc_info.value)

    @pytest.mark.parametrize("invalid_weight", [0.0, -0.001, -500.0])
    def test_warehouse_weight_zero_or_negative_raises_error(self, invalid_weight):
        with pytest.raises(ValidationError) as exc_info:
            Warehouse(
                warehouse_id="WH-ERR-02",
                name="Zero Weight WH",
                total_volume_capacity_m3=500.0,
                total_weight_capacity_kg=invalid_weight,
            )
        assert "total_weight_capacity_kg" in str(exc_info.value)

    @pytest.mark.parametrize("invalid_service_level", [0.49, 0.0, -0.1, 1.0, 1.05])
    def test_target_service_level_bounds_enforced(self, invalid_service_level):
        with pytest.raises(ValidationError) as exc_info:
            Warehouse(
                warehouse_id="WH-ERR-03",
                name="Invalid SL WH",
                total_volume_capacity_m3=500.0,
                total_weight_capacity_kg=20000.0,
                target_service_level=invalid_service_level,
            )
        assert "target_service_level" in str(exc_info.value)

    @pytest.mark.parametrize("valid_service_level", [0.50, 0.95, 0.999])
    def test_valid_service_level_boundaries(self, valid_service_level):
        wh = Warehouse(
            warehouse_id=f"WH-SL-{valid_service_level}",
            total_volume_capacity_m3=500.0,
            total_weight_capacity_kg=20000.0,
            target_service_level=valid_service_level,
        )
        assert wh.target_service_level == valid_service_level


class TestInventoryStateModelStress:
    """Stress tests for InventoryState effective inventory calculation."""

    def test_extreme_negative_effective_inventory(self):
        state = InventoryState(
            sku_id="SKU-BACKORDER",
            on_hand=0.0,
            on_order=0.0,
            allocated=250.0,
            backorders=750.0,
        )
        assert state.effective_inventory == -1000.0

    def test_fractional_precision_rounding(self):
        state = InventoryState(
            sku_id="SKU-FRAC",
            on_hand=100.123456,
            on_order=50.654321,
            allocated=10.111111,
            backorders=5.222222,
        )
        # 100.123456 + 50.654321 - 10.111111 - 5.222222 = 135.444444 -> rounded to 4 decimals = 135.4444
        assert state.effective_inventory == 135.4444


# ===========================================================================
# 2. Knowledge Engine Salience, Ordering & Working Memory Stress Tests
# ===========================================================================

class TestRuleEnginePriorityAndSalienceStress:
    """Empirical verification of salience, specificity, and execution ordering."""

    def test_strict_descending_priority_execution(self):
        engine = RuleEngine()
        fire_log = []

        # Register 5 competing rules with distinct priorities
        priorities = [10, 50, 100, 200, 500]
        for p in priorities:
            r = Rule(
                rule_id=f"RULE_P_{p}",
                name=f"Rule with priority {p}",
                priority=p,
                condition=lambda wm, p=p: [{
                    "_matched_fact_ids": [f.id],
                    "priority": p,
                } for f in wm.get_facts_by_name("TestTrigger")],
                action=lambda wm, b, a: fire_log.append(b["priority"]) or f"Fired {b['priority']}",
            )
            engine.register_rule(r)

        wm = WorkingMemory()
        wm.assert_fact(Fact(name="TestTrigger", payload={"trigger": True}))

        report = engine.run(wm)
        assert report.rules_fired_count == 5
        # Must fire strictly from highest (500) to lowest (10)
        assert fire_log == [500, 200, 100, 50, 10]

    def test_specificity_tie_breaking_for_equal_priorities(self):
        engine = RuleEngine()
        fire_log = []

        # Two rules with identical priority=80
        r_single = Rule(
            rule_id="RULE_SPEC_1",
            name="Matches 1 fact",
            priority=80,
            condition=lambda wm: [{
                "_matched_fact_ids": [f1.id],
                "type": "SINGLE",
            } for f1 in wm.get_facts_by_name("FactA")],
            action=lambda wm, b, a: fire_log.append("SINGLE") or "Single",
        )
        r_double = Rule(
            rule_id="RULE_SPEC_2",
            name="Matches 2 facts",
            priority=80,
            condition=lambda wm: [{
                "_matched_fact_ids": [f1.id, f2.id],
                "type": "DOUBLE",
            } for f1 in wm.get_facts_by_name("FactA") for f2 in wm.get_facts_by_name("FactB")],
            action=lambda wm, b, a: fire_log.append("DOUBLE") or "Double",
        )

        engine.register_rule(r_single)
        engine.register_rule(r_double)

        wm = WorkingMemory()
        wm.assert_fact(Fact(name="FactA", payload={"a": 1}))
        wm.assert_fact(Fact(name="FactB", payload={"b": 2}))

        report = engine.run(wm)
        assert report.rules_fired_count == 2
        # Double-fact rule must fire first due to higher specificity
        assert fire_log == ["DOUBLE", "SINGLE"]

    def test_refraction_prevents_re_firing_on_same_facts(self):
        engine = RuleEngine()
        fire_counter = [0]

        r = Rule(
            rule_id="RULE_REFRACT",
            name="Refraction Test Rule",
            priority=50,
            condition=lambda wm: [{
                "_matched_fact_ids": [f.id],
            } for f in wm.get_facts_by_name("StaticFact")],
            action=lambda wm, b, a: (fire_counter.__setitem__(0, fire_counter[0] + 1), "Fired")[1],
        )
        engine.register_rule(r)

        wm = WorkingMemory()
        wm.assert_fact(Fact(name="StaticFact", payload={"state": "constant"}))

        report = engine.run(wm, max_cycles=10)
        # Even with max_cycles=10, the rule must fire EXACTLY ONCE due to refraction
        assert fire_counter[0] == 1
        assert report.rules_fired_count == 1
        assert report.cycles_executed == 2  # Cycle 1 fires, Cycle 2 quiescence

    def test_max_cycles_safeguard_against_divergent_chaining(self):
        engine = RuleEngine()

        def action_gen(wm, b, a):
            new_fact = Fact(name="SeqFact", payload={"seq": b["seq"] + 1})
            wm.assert_fact(new_fact)
            a.append(new_fact)
            return f"Generated seq {b['seq'] + 1}"

        # Rule that generates a new unique fact every cycle
        r_generator = Rule(
            rule_id="RULE_DIVERGENT",
            name="Generates infinite facts",
            priority=10,
            condition=lambda wm: [{
                "_matched_fact_ids": [f.id],
                "seq": f.get("seq", 0),
            } for f in wm.get_facts_by_name("SeqFact")],
            action=action_gen,
        )
        engine.register_rule(r_generator)

        wm = WorkingMemory()
        wm.assert_fact(Fact(name="SeqFact", payload={"seq": 0}))

        report = engine.run(wm, max_cycles=8)
        assert report.cycles_executed == 8
        assert report.rules_fired_count == 8

    def test_full_canonical_rule_cascade_and_salience_order(self):
        """Validates all 8 canonical domain rules executing in their exact prioritized order."""
        wm = WorkingMemory()
        engine = build_inventory_rule_engine()

        # 1. Critical inventory state
        wm.assert_fact(Fact(name="InventoryStateFact", payload={
            "sku_id": "SKU-CRIT",
            "effective_inventory": 10.0,
            "safety_stock": 25.0,
            "reorder_point": 60.0,
            "max_stock": 150.0,
        }))
        # 2. Reorder needed inventory state
        wm.assert_fact(Fact(name="InventoryStateFact", payload={
            "sku_id": "SKU-REORDER",
            "effective_inventory": 40.0,
            "safety_stock": 25.0,
            "reorder_point": 60.0,
            "max_stock": 150.0,
        }))
        # 3. Optimal inventory state
        wm.assert_fact(Fact(name="InventoryStateFact", payload={
            "sku_id": "SKU-OPTIMAL",
            "effective_inventory": 90.0,
            "safety_stock": 25.0,
            "reorder_point": 60.0,
            "max_stock": 150.0,
        }))
        # 4. Excess inventory state
        wm.assert_fact(Fact(name="InventoryStateFact", payload={
            "sku_id": "SKU-EXCESS",
            "effective_inventory": 200.0,
            "safety_stock": 25.0,
            "reorder_point": 60.0,
            "max_stock": 150.0,
        }))
        # 5. Slow primary supplier for SKU-CRIT
        wm.assert_fact(Fact(name="SupplierFact", payload={
            "supplier_id": "SUP-SLOW",
            "is_primary_for": "SKU-CRIT",
            "mean_lead_time_days": 14.0,
            "on_time_delivery_rate": 0.80,
            "defect_rate": 0.04,
        }))
        # 6. Fast backup local express supplier
        wm.assert_fact(Fact(name="SupplierFact", payload={
            "supplier_id": "SUP-EXPRESS",
            "profile_type": "LOCAL_EXPRESS",
            "mean_lead_time_days": 2.0,
            "on_time_delivery_rate": 0.98,
            "defect_rate": 0.005,
        }))
        # 7. Unaligned raw order proposal
        wm.assert_fact(Fact(name="RawOrderProposalFact", payload={
            "sku_id": "SKU-REORDER",
            "quantity": 35.0,
            "pack_size": 12,
            "moq": 40,
        }))

        report = engine.run(wm)
        assert report.rules_fired_count == 8

        # Extract fired rule IDs in chronological sequence
        fired_sequence = [t.rule_id for t in report.execution_traces]
        expected_sequence = [
            "RULE_STOCK_CRITICAL",         # Priority 100
            "RULE_EMERGENCY_SOURCING",     # Priority 90 (chained from CRITICAL)
            "RULE_STOCK_REORDER_NEEDED",   # Priority 80
            "RULE_SUPPLIER_TIER1",         # Priority 70
            "RULE_SUPPLIER_TIER3",         # Priority 70
            "RULE_LOT_SIZING_ALIGNMENT",   # Priority 60
            "RULE_STOCK_OPTIMAL",          # Priority 50
            "RULE_STOCK_EXCESS",           # Priority 50
        ]
        assert fired_sequence == expected_sequence

    @pytest.mark.parametrize(
        ("effective_inv", "expected_status"),
        [
            (-100.0, "CRITICAL"),
            (0.0, "CRITICAL"),
            (19.999, "CRITICAL"),
            (20.0, "CRITICAL"),            # Exact boundary: I_eff == SS
            (20.001, "REORDER_NEEDED"),    # Just above SS
            (35.0, "REORDER_NEEDED"),
            (49.999, "REORDER_NEEDED"),
            (50.0, "REORDER_NEEDED"),      # Exact boundary: I_eff == ROP
            (50.001, "OPTIMAL"),           # Just above ROP
            (75.0, "OPTIMAL"),
            (99.999, "OPTIMAL"),
            (100.0, "OPTIMAL"),            # Exact boundary: I_eff == Max_Stock
            (100.001, "EXCESS"),           # Just above Max_Stock
            (500.0, "EXCESS"),
        ],
    )
    def test_stock_status_strict_interval_partitioning(self, effective_inv, expected_status):
        """Verifies mathematical non-overlapping partitioning of stock classification."""
        engine = build_inventory_rule_engine()
        wm = WorkingMemory()
        wm.assert_fact(Fact(
            name="InventoryStateFact",
            payload={
                "sku_id": "SKU-PROBE",
                "effective_inventory": effective_inv,
                "safety_stock": 20.0,
                "reorder_point": 50.0,
                "max_stock": 100.0,
            }
        ))
        engine.run(wm)
        classifications = wm.get_facts_by_name("StockClassificationFact")
        assert len(classifications) == 1
        assert classifications[0].get("status") == expected_status


class TestWorkingMemoryStateIntegrity:
    """Stress tests for WorkingMemory operations and high-volume performance."""

    def test_fact_deduplication_and_payload_update(self):
        wm = WorkingMemory()
        f1 = Fact(name="FactA", payload={"v": 1}, id="STATIC-ID")
        f2 = Fact(name="FactA", payload={"v": 99}, id="STATIC-ID")
        wm.assert_fact(f1)
        wm.assert_fact(f2)
        assert len(wm.all_facts()) == 1
        assert wm.get_fact("STATIC-ID").get("v") == 99

    def test_retract_fact_lifecycle(self):
        wm = WorkingMemory()
        f = Fact(name="FactB", payload={"x": 42}, id="RETRACT-ID")
        wm.assert_fact(f)
        assert wm.retract_fact("RETRACT-ID") is True
        assert wm.retract_fact("RETRACT-ID") is False
        assert wm.get_fact("RETRACT-ID") is None

    def test_high_volume_assertion_and_query_integrity(self):
        wm = WorkingMemory()
        total_facts = 2000
        for i in range(total_facts):
            wm.assert_fact(Fact(
                name=f"Category_{i % 10}",
                payload={"index": i, "value": i * 1.5},
            ))
        assert len(wm.all_facts()) == total_facts
        for cat_idx in range(10):
            facts_in_cat = wm.get_facts_by_name(f"Category_{cat_idx}")
            assert len(facts_in_cat) == 200

        wm.clear()
        assert len(wm.all_facts()) == 0
