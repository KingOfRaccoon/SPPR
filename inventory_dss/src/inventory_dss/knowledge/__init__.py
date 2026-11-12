"""Knowledge base package for Inventory Decision Support System."""

from inventory_dss.knowledge.ontology import (
    ConceptType,
    DomainOntology,
    OntologyAxiom,
    OntologyClass,
    OntologyRelation,
    build_inventory_ontology,
)
from inventory_dss.knowledge.rules import (
    Fact,
    Rule,
    RuleActivation,
    RuleEngine,
    RuleExecutionReport,
    RuleTraceEntry,
    WorkingMemory,
    build_inventory_rule_engine,
)

__all__ = [
    "ConceptType",
    "DomainOntology",
    "Fact",
    "OntologyAxiom",
    "OntologyClass",
    "OntologyRelation",
    "Rule",
    "RuleActivation",
    "RuleEngine",
    "RuleExecutionReport",
    "RuleTraceEntry",
    "WorkingMemory",
    "build_inventory_ontology",
    "build_inventory_rule_engine",
]
