"""Unit tests for Domain Ontology and Forward-Chaining Production Rules Engine."""


from inventory_dss.knowledge.ontology import (
    DomainOntology,
    OntologyClass,
)
from inventory_dss.knowledge.rules import (
    Fact,
    RuleEngine,
    WorkingMemory,
)

# ===========================================================================
# 1. Tests for Domain Ontology
# ===========================================================================

class TestDomainOntology:
    """Verifies ontology concepts, taxonomy inheritance, relations, and axioms."""

    def test_canonical_ontology_structure(self, sample_ontology: DomainOntology):
        assert "InventoryItem" in sample_ontology.classes
        assert "Supplier" in sample_ontology.classes
        assert "Warehouse" in sample_ontology.classes
        assert "InventoryState" in sample_ontology.classes

        # Relations
        assert "REL_SUPPLIED_BY" in sample_ontology.relations
        assert "REL_STORED_IN" in sample_ontology.relations
        assert "REL_TRIGGERS_RECOMMENDATION" in sample_ontology.relations

        # Axioms
        assert "AX_EFFECTIVE_INVENTORY" in sample_ontology.axioms
        assert "AX_WAREHOUSE_VOLUME_LIMIT" in sample_ontology.axioms

    def test_taxonomy_hierarchy_and_subclasses(self, sample_ontology: DomainOntology):
        # HighValueItem is a subclass of InventoryItem and DomainEntity
        assert sample_ontology.is_subclass_of("HighValueItem", "InventoryItem")
        assert sample_ontology.is_subclass_of("HighValueItem", "DomainEntity")
        assert not sample_ontology.is_subclass_of("InventoryItem", "HighValueItem")

        # Check all subclasses of InventoryItem
        subclasses = sample_ontology.get_subclasses("InventoryItem", recursive=True)
        subclass_ids = {sc.id for sc in subclasses}
        assert "HighValueItem" in subclass_ids
        assert "MediumValueItem" in subclass_ids
        assert "LowValueItem" in subclass_ids
        assert "IntermittentDemandItem" in subclass_ids

    def test_superclasses_path(self, sample_ontology: DomainOntology):
        ancestors = sample_ontology.get_superclasses("ReliableSupplier")
        ancestor_ids = [sc.id for sc in ancestors]
        assert ancestor_ids == ["Supplier", "SupplyChainActor", "DomainEntity"]

    def test_relations_retrieval(self, sample_ontology: DomainOntology):
        item_relations = sample_ontology.get_relations_from("HighValueItem")
        rel_names = {r.name for r in item_relations}
        assert "SUPPLIED_BY" in rel_names
        assert "STORED_IN" in rel_names
        assert "HAS_STATE" in rel_names

    def test_canonical_ontology_consistency(self, sample_ontology: DomainOntology):
        errors = sample_ontology.validate_consistency()
        assert errors == [], f"Canonical ontology has consistency errors: {errors}"

    def test_ontology_consistency_validation_catches_broken_parent(self):
        broken_onto = DomainOntology("Broken")
        broken_onto.add_class(OntologyClass(
            id="Child",
            name="Child",
            description="Child",
            parent_id="NonExistentParent"
        ))
        errors = broken_onto.validate_consistency()
        assert len(errors) == 1
        assert "references undefined parent 'NonExistentParent'" in errors[0]

    def test_ontology_consistency_validation_catches_circular_inheritance(self):
        circular_onto = DomainOntology("Circular")
        circular_onto.add_class(OntologyClass(id="A", name="A", description="", parent_id="B"))
        circular_onto.add_class(OntologyClass(id="B", name="B", description="", parent_id="A"))
        errors = circular_onto.validate_consistency()
        assert any("Circular inheritance detected" in err for err in errors)


# ===========================================================================
# 2. Tests for Production Rules Engine & Working Memory
# ===========================================================================

class TestWorkingMemory:
    """Tests working memory operations: assertion, modification, query, retraction."""

    def test_assert_and_get_fact(self, working_memory: WorkingMemory):
        fact = Fact(name="TestFact", payload={"sku_id": "SKU-01", "level": 50})
        fact_id = working_memory.assert_fact(fact)
        assert fact_id == fact.id
        retrieved = working_memory.get_fact(fact_id)
        assert retrieved is not None
        assert retrieved.get("sku_id") == "SKU-01"
        assert retrieved.get("level") == 50

    def test_retract_fact(self, working_memory: WorkingMemory):
        fact = Fact(name="TemporaryFact", payload={"key": "val"})
        working_memory.assert_fact(fact)
        assert working_memory.get_fact(fact.id) is not None
        assert working_memory.retract_fact(fact.id) is True
        assert working_memory.get_fact(fact.id) is None


class TestStockClassificationRules:
    """Tests forward-chaining rules for diagnosing stock states."""

    def test_critical_deficit_rule_firing(
        self, sample_rule_engine: RuleEngine, working_memory: WorkingMemory
    ):
        # Assert inventory state where I_eff <= SS
        working_memory.assert_fact(Fact(
            name="InventoryStateFact",
            payload={
                "sku_id": "SKU-ELEC-001",
                "effective_inventory": 30.0,
                "safety_stock": 45.0,
                "reorder_point": 90.0,
                "max_stock": 250.0,
            }
        ))

        report = sample_rule_engine.run(working_memory)
        assert report.rules_fired_count >= 1

        # Check classification fact produced
        classifications = working_memory.get_facts_by_name("StockClassificationFact")
        assert len(classifications) == 1
        clf = classifications[0]
        assert clf.get("sku_id") == "SKU-ELEC-001"
        assert clf.get("status") == "CRITICAL"
        assert clf.get("urgency") == "HIGH"
        assert clf.get("order_needed") is True
        assert clf.get("deficit_units") == 15.0

        # Check critical alert
        alerts = working_memory.get_facts_by_name("AlertFact")
        assert any(a.get("level") == "CRITICAL" for a in alerts)

        # Check execution trace explanation
        traces = [t for t in report.execution_traces if t.rule_id == "RULE_STOCK_CRITICAL"]
        assert len(traces) == 1
        assert "обнаружен критический дефицит" in traces[0].rationale

    def test_reorder_needed_rule_firing(
        self, sample_rule_engine: RuleEngine, working_memory: WorkingMemory
    ):
        # Assert inventory state where SS < I_eff <= ROP
        working_memory.assert_fact(Fact(
            name="InventoryStateFact",
            payload={
                "sku_id": "SKU-PART-001",
                "effective_inventory": 55.0,
                "safety_stock": 30.0,
                "reorder_point": 70.0,
                "max_stock": 200.0,
            }
        ))

        report = sample_rule_engine.run(working_memory)
        assert report.rules_fired_count >= 1
        classifications = working_memory.get_facts_by_name("StockClassificationFact")
        assert len(classifications) == 1
        clf = classifications[0]
        assert clf.get("status") == "REORDER_NEEDED"
        assert clf.get("urgency") == "MEDIUM"
        assert clf.get("order_needed") is True

    def test_optimal_stock_rule_firing(
        self, sample_rule_engine: RuleEngine, working_memory: WorkingMemory
    ):
        # Assert inventory state where ROP < I_eff <= Max_Stock
        working_memory.assert_fact(Fact(
            name="InventoryStateFact",
            payload={
                "sku_id": "SKU-RAW-001",
                "effective_inventory": 120.0,
                "safety_stock": 40.0,
                "reorder_point": 90.0,
                "max_stock": 300.0,
            }
        ))

        report = sample_rule_engine.run(working_memory)
        assert report.rules_fired_count >= 1
        classifications = working_memory.get_facts_by_name("StockClassificationFact")
        assert len(classifications) == 1
        clf = classifications[0]
        assert clf.get("status") == "OPTIMAL"
        assert clf.get("urgency") == "NONE"
        assert clf.get("order_needed") is False

    def test_excess_stock_rule_firing(
        self, sample_rule_engine: RuleEngine, working_memory: WorkingMemory
    ):
        # Assert inventory state where I_eff > Max_Stock
        working_memory.assert_fact(Fact(
            name="InventoryStateFact",
            payload={
                "sku_id": "SKU-CNS-001",
                "effective_inventory": 550.0,
                "safety_stock": 50.0,
                "reorder_point": 150.0,
                "max_stock": 400.0,
            }
        ))

        report = sample_rule_engine.run(working_memory)
        assert report.rules_fired_count >= 1
        classifications = working_memory.get_facts_by_name("StockClassificationFact")
        assert len(classifications) == 1
        clf = classifications[0]
        assert clf.get("status") == "EXCESS"
        assert clf.get("urgency") == "LOW"
        assert clf.get("order_needed") is False
        assert clf.get("overstock_units") == 150.0

        # Warning alert should be raised
        alerts = working_memory.get_facts_by_name("AlertFact")
        assert any(a.get("level") == "WARNING" for a in alerts)


class TestSupplierRatingAndHeuristicsRules:
    """Tests supplier reliability classification and emergency order routing."""

    def test_supplier_tier1_preferred(
        self, sample_rule_engine: RuleEngine, working_memory: WorkingMemory
    ):
        working_memory.assert_fact(Fact(
            name="SupplierFact",
            payload={
                "supplier_id": "SUP-PREMIUM",
                "on_time_delivery_rate": 0.98,
                "defect_rate": 0.005,
            }
        ))
        sample_rule_engine.run(working_memory)
        ratings = working_memory.get_facts_by_name("SupplierRatingFact")
        assert len(ratings) == 1
        assert ratings[0].get("tier") == "TIER_1_PREFERRED"
        assert ratings[0].get("reliability_rating") == "HIGH"

    def test_supplier_tier3_high_risk(
        self, sample_rule_engine: RuleEngine, working_memory: WorkingMemory
    ):
        working_memory.assert_fact(Fact(
            name="SupplierFact",
            payload={
                "supplier_id": "SUP-VOLATILE",
                "on_time_delivery_rate": 0.72,
                "defect_rate": 0.045,
            }
        ))
        sample_rule_engine.run(working_memory)
        ratings = working_memory.get_facts_by_name("SupplierRatingFact")
        assert len(ratings) == 1
        assert ratings[0].get("tier") == "TIER_3_HIGH_RISK"
        assert ratings[0].get("reliability_rating") == "LOW"

    def test_emergency_sourcing_override(
        self, sample_rule_engine: RuleEngine, working_memory: WorkingMemory
    ):
        # 1. Assert Critical Stock for SKU-ELEC-002
        working_memory.assert_fact(Fact(
            name="InventoryStateFact",
            payload={
                "sku_id": "SKU-ELEC-002",
                "effective_inventory": 10.0,
                "safety_stock": 35.0,
                "reorder_point": 70.0,
                "max_stock": 200.0,
            }
        ))
        # 2. Assert slow primary supplier (lead time = 14 days)
        working_memory.assert_fact(Fact(
            name="SupplierFact",
            payload={
                "supplier_id": "SUP-OVERSEAS",
                "is_primary_for": "SKU-ELEC-002",
                "mean_lead_time_days": 14.0,
                "on_time_delivery_rate": 0.88,
                "defect_rate": 0.015,
            }
        ))
        # 3. Assert fast backup local express supplier (lead time = 2 days)
        working_memory.assert_fact(Fact(
            name="SupplierFact",
            payload={
                "supplier_id": "SUP-EXPRESS",
                "profile_type": "LOCAL_EXPRESS",
                "mean_lead_time_days": 2.0,
                "on_time_delivery_rate": 0.96,
                "defect_rate": 0.005,
            }
        ))

        # Run forward chaining:
        # Step 1: CRITICAL rule fires and asserts StockClassificationFact
        # Step 2: Emergency Sourcing rule detects CRITICAL + slow primary + available express
        report = sample_rule_engine.run(working_memory)
        assert report.rules_fired_count >= 1

        emergency_facts = working_memory.get_facts_by_name("EmergencySourcingFact")
        assert len(emergency_facts) == 1
        emf = emergency_facts[0]
        assert emf.get("sku_id") == "SKU-ELEC-002"
        assert emf.get("recommended_supplier_id") == "SUP-EXPRESS"
        assert "Критический дефицит" in emf.get("reason")

    def test_lot_sizing_and_moq_alignment(
        self, sample_rule_engine: RuleEngine, working_memory: WorkingMemory
    ):
        # Unconstrained calculated EOQ is 43 units, but MOQ=50 and pack_size=12
        working_memory.assert_fact(Fact(
            name="RawOrderProposalFact",
            payload={
                "sku_id": "SKU-CNS-001",
                "quantity": 43.0,
                "pack_size": 12,
                "moq": 50,
            }
        ))
        sample_rule_engine.run(working_memory)
        aligned_facts = working_memory.get_facts_by_name("AlignedOrderFact")
        assert len(aligned_facts) == 1
        # Target >= 50, next multiple of 12 is ceil(50/12)*12 = 5 * 12 = 60.0
        assert aligned_facts[0].get("aligned_quantity") == 60.0
