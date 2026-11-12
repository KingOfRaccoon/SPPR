"""Production rules engine with forward-chaining inference for Inventory DSS.

Implements working memory, pattern matching, conflict resolution (salience,
specificity, refraction), and explainable execution traces for stock
classification, supplier reliability rating, and ordering heuristics.
"""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Fact:
    """Working memory fact with a type name, attributes payload, and unique ID."""
    name: str
    payload: dict[str, Any]
    id: str | None = None
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.id is None:
            # Deterministic unique ID generation based on type and payload keys
            content_sig = "_".join(f"{k}={self.payload[k]}" for k in sorted(self.payload.keys()))
            self.id = f"{self.name}::{content_sig}"

    def get(self, key: str, default: Any = None) -> Any:
        return self.payload.get(key, default)


class WorkingMemory:
    """In-memory fact base supporting retrieval, assertion, and modification."""

    def __init__(self):
        self._facts: dict[str, Fact] = {}

    def assert_fact(self, fact: Fact) -> str:
        """Add a fact to working memory. If an identical fact exists, overwrite it."""
        self._facts[fact.id] = fact
        return fact.id

    def retract_fact(self, fact_id: str) -> bool:
        """Remove a fact by its ID."""
        return self._facts.pop(fact_id, None) is not None

    def get_fact(self, fact_id: str) -> Fact | None:
        return self._facts.get(fact_id)

    def get_facts_by_name(self, name: str) -> list[Fact]:
        return [f for f in self._facts.values() if f.name == name]

    def all_facts(self) -> list[Fact]:
        return list(self._facts.values())

    def clear(self) -> None:
        self._facts.clear()


@dataclass
class RuleActivation:
    """A match of a rule with specific facts from working memory."""
    rule: "Rule"
    matched_facts: tuple[str, ...]
    bindings: dict[str, Any]

    @property
    def activation_key(self) -> tuple[str, tuple[str, ...]]:
        """Used for refraction (preventing firing the same rule on the same facts)."""
        return (self.rule.id, tuple(sorted(self.matched_facts)))


@dataclass
class RuleTraceEntry:
    """Audit log entry capturing a fired rule and its reasoning for Explainable AI (XAI)."""
    cycle: int
    rule_id: str
    rule_name: str
    matched_facts: list[str]
    rationale: str
    asserted_facts: list[str]


@dataclass
class RuleExecutionReport:
    """Summary of the forward chaining inference execution."""
    cycles_executed: int
    rules_fired_count: int
    execution_traces: list[RuleTraceEntry]
    final_facts: list[Fact]


class Rule:
    """Production rule representing IF (conditions) THEN (actions) with priority."""

    def __init__(
        self,
        rule_id: str,
        name: str,
        priority: int = 10,
        condition: Callable[[WorkingMemory], list[dict[str, Any]]] | None = None,
        action: Callable[[WorkingMemory, dict[str, Any], list[Fact]], str] | None = None,
        description: str = "",
        category: str = "GENERAL",
    ):
        self.id = rule_id
        self.name = name
        self.priority = priority  # Salience: higher priority rules fire earlier
        self.condition = condition or (lambda wm: [])
        self.action = action or (lambda wm, bindings, asserted: "")
        self.description = description
        self.category = category

    def evaluate(self, wm: WorkingMemory) -> list[RuleActivation]:
        """Evaluate conditions against working memory, returning candidate activations."""
        bindings_list = self.condition(wm)
        activations = []
        for b in bindings_list:
            matched_fact_ids = tuple(b.get("_matched_fact_ids", []))
            activations.append(RuleActivation(rule=self, matched_facts=matched_fact_ids, bindings=b))
        return activations


class RuleEngine:
    """Forward-chaining production rules engine with conflict resolution."""

    def __init__(self):
        self.rules: dict[str, Rule] = {}

    def register_rule(self, rule: Rule) -> None:
        if rule.id in self.rules:
            raise ValueError(f"Rule with ID '{rule.id}' is already registered")
        self.rules[rule.id] = rule

    def run(self, wm: WorkingMemory, max_cycles: int = 50) -> RuleExecutionReport:
        """Run forward-chaining cycle until quiescence (fixpoint) or max_cycles."""
        traces: list[RuleTraceEntry] = []
        refraction_set: set[tuple[str, tuple[str, ...]]] = set()
        cycle = 0

        while cycle < max_cycles:
            cycle += 1
            # 1. Match phase: find all activations
            candidate_activations: list[RuleActivation] = []
            for rule in self.rules.values():
                rule_matches = rule.evaluate(wm)
                for act in rule_matches:
                    if act.activation_key not in refraction_set:
                        candidate_activations.append(act)

            if not candidate_activations:
                # Quiescence reached: no more rules can fire
                break

            # 2. Conflict Resolution phase:
            # Sort by:
            # - Priority / Salience (descending)
            # - Specificity (number of matched facts, descending)
            candidate_activations.sort(
                key=lambda a: (a.rule.priority, len(a.matched_facts)),
                reverse=True
            )

            # Select winning activation
            chosen_activation = candidate_activations[0]
            refraction_set.add(chosen_activation.activation_key)

            # 3. Act phase: fire chosen rule
            asserted_in_step: list[Fact] = []
            rationale = chosen_activation.rule.action(
                wm, chosen_activation.bindings, asserted_in_step
            )

            # Record in execution trace
            trace_entry = RuleTraceEntry(
                cycle=cycle,
                rule_id=chosen_activation.rule.id,
                rule_name=chosen_activation.rule.name,
                matched_facts=list(chosen_activation.matched_facts),
                rationale=rationale,
                asserted_facts=[f.id for f in asserted_in_step],
            )
            traces.append(trace_entry)

        return RuleExecutionReport(
            cycles_executed=cycle,
            rules_fired_count=len(traces),
            execution_traces=traces,
            final_facts=wm.all_facts(),
        )


# ===========================================================================
# Standard Domain Rules for Inventory DSS
# ===========================================================================

def build_inventory_rule_engine() -> RuleEngine:
    """Build and configure the canonical rule engine for inventory decision support."""
    engine = RuleEngine()

    # -----------------------------------------------------------------------
    # Rule 1: CRITICAL Stock Diagnosis (I_eff <= SS)
    # -----------------------------------------------------------------------
    def cond_stock_critical(wm: WorkingMemory) -> list[dict[str, Any]]:
        matches = []
        for fact in wm.get_facts_by_name("InventoryStateFact"):
            effective_inv = float(fact.get("effective_inventory", 0.0))
            safety_stock = float(fact.get("safety_stock", 0.0))
            # Fire only if not already classified
            sku_id = fact.get("sku_id")
            existing = [
                f for f in wm.get_facts_by_name("StockClassificationFact")
                if f.get("sku_id") == sku_id
            ]
            if not existing and effective_inv <= safety_stock:
                matches.append({
                    "sku_id": sku_id,
                    "effective_inventory": effective_inv,
                    "safety_stock": safety_stock,
                    "reorder_point": float(fact.get("reorder_point", safety_stock)),
                    "_matched_fact_ids": [fact.id],
                })
        return matches

    def act_stock_critical(wm: WorkingMemory, bindings: dict[str, Any], asserted: list[Fact]) -> str:
        sku = bindings["sku_id"]
        eff = bindings["effective_inventory"]
        ss = bindings["safety_stock"]
        deficit = ss - eff

        classification = Fact(
            name="StockClassificationFact",
            payload={
                "sku_id": sku,
                "status": "CRITICAL",
                "urgency": "HIGH",
                "order_needed": True,
                "deficit_units": max(0.0, deficit),
            }
        )
        alert = Fact(
            name="AlertFact",
            payload={
                "level": "CRITICAL",
                "sku_id": sku,
                "message": f"Опасность дефицита: эффективный остаток {eff} ниже/равен страховому запасу {ss}.",
            }
        )
        wm.assert_fact(classification)
        wm.assert_fact(alert)
        asserted.extend([classification, alert])
        return f"Позиция {sku}: обнаружен критический дефицит (I_eff={eff} <= SS={ss}). Срочность: HIGH."

    engine.register_rule(Rule(
        rule_id="RULE_STOCK_CRITICAL",
        name="Диагностика критического дефицита запаса",
        priority=100,  # Highest priority
        condition=cond_stock_critical,
        action=act_stock_critical,
        description="При I_eff <= SS присваивает статус CRITICAL и генерирует тревожное оповещение.",
        category="STOCK_CLASSIFICATION",
    ))

    # -----------------------------------------------------------------------
    # Rule 2: REORDER_NEEDED Diagnosis (SS < I_eff <= ROP)
    # -----------------------------------------------------------------------
    def cond_stock_reorder(wm: WorkingMemory) -> list[dict[str, Any]]:
        matches = []
        for fact in wm.get_facts_by_name("InventoryStateFact"):
            sku_id = fact.get("sku_id")
            effective_inv = float(fact.get("effective_inventory", 0.0))
            safety_stock = float(fact.get("safety_stock", 0.0))
            reorder_point = float(fact.get("reorder_point", 0.0))
            existing = [
                f for f in wm.get_facts_by_name("StockClassificationFact")
                if f.get("sku_id") == sku_id
            ]
            if not existing and safety_stock < effective_inv <= reorder_point:
                matches.append({
                    "sku_id": sku_id,
                    "effective_inventory": effective_inv,
                    "safety_stock": safety_stock,
                    "reorder_point": reorder_point,
                    "_matched_fact_ids": [fact.id],
                })
        return matches

    def act_stock_reorder(wm: WorkingMemory, bindings: dict[str, Any], asserted: list[Fact]) -> str:
        sku = bindings["sku_id"]
        eff = bindings["effective_inventory"]
        rop = bindings["reorder_point"]

        classification = Fact(
            name="StockClassificationFact",
            payload={
                "sku_id": sku,
                "status": "REORDER_NEEDED",
                "urgency": "MEDIUM",
                "order_needed": True,
            }
        )
        wm.assert_fact(classification)
        asserted.append(classification)
        return f"Позиция {sku}: достигнута точка заказа (I_eff={eff} <= ROP={rop}). Срочность: MEDIUM."

    engine.register_rule(Rule(
        rule_id="RULE_STOCK_REORDER_NEEDED",
        name="Диагностика необходимости планового пополнения",
        priority=80,
        condition=cond_stock_reorder,
        action=act_stock_reorder,
        description="При SS < I_eff <= ROP присваивает статус REORDER_NEEDED.",
        category="STOCK_CLASSIFICATION",
    ))

    # -----------------------------------------------------------------------
    # Rule 3: OPTIMAL Stock Diagnosis (ROP < I_eff <= Max_Stock)
    # -----------------------------------------------------------------------
    def cond_stock_optimal(wm: WorkingMemory) -> list[dict[str, Any]]:
        matches = []
        for fact in wm.get_facts_by_name("InventoryStateFact"):
            sku_id = fact.get("sku_id")
            effective_inv = float(fact.get("effective_inventory", 0.0))
            reorder_point = float(fact.get("reorder_point", 0.0))
            max_stock = float(fact.get("max_stock", reorder_point * 3.0))
            existing = [
                f for f in wm.get_facts_by_name("StockClassificationFact")
                if f.get("sku_id") == sku_id
            ]
            if not existing and reorder_point < effective_inv <= max_stock:
                matches.append({
                    "sku_id": sku_id,
                    "effective_inventory": effective_inv,
                    "reorder_point": reorder_point,
                    "max_stock": max_stock,
                    "_matched_fact_ids": [fact.id],
                })
        return matches

    def act_stock_optimal(wm: WorkingMemory, bindings: dict[str, Any], asserted: list[Fact]) -> str:
        sku = bindings["sku_id"]
        eff = bindings["effective_inventory"]
        classification = Fact(
            name="StockClassificationFact",
            payload={
                "sku_id": sku,
                "status": "OPTIMAL",
                "urgency": "NONE",
                "order_needed": False,
            }
        )
        wm.assert_fact(classification)
        asserted.append(classification)
        return f"Позиция {sku}: уровень запаса оптимален (I_eff={eff}). Дозаказ не требуется."

    engine.register_rule(Rule(
        rule_id="RULE_STOCK_OPTIMAL",
        name="Диагностика оптимального уровня запаса",
        priority=50,
        condition=cond_stock_optimal,
        action=act_stock_optimal,
        description="При ROP < I_eff <= Max_Stock фиксирует состояние OPTIMAL.",
        category="STOCK_CLASSIFICATION",
    ))

    # -----------------------------------------------------------------------
    # Rule 4: EXCESS Stock Diagnosis (I_eff > Max_Stock)
    # -----------------------------------------------------------------------
    def cond_stock_excess(wm: WorkingMemory) -> list[dict[str, Any]]:
        matches = []
        for fact in wm.get_facts_by_name("InventoryStateFact"):
            sku_id = fact.get("sku_id")
            effective_inv = float(fact.get("effective_inventory", 0.0))
            reorder_point = float(fact.get("reorder_point", 0.0))
            max_stock = float(fact.get("max_stock", reorder_point * 3.0))
            existing = [
                f for f in wm.get_facts_by_name("StockClassificationFact")
                if f.get("sku_id") == sku_id
            ]
            if not existing and effective_inv > max_stock:
                matches.append({
                    "sku_id": sku_id,
                    "effective_inventory": effective_inv,
                    "max_stock": max_stock,
                    "_matched_fact_ids": [fact.id],
                })
        return matches

    def act_stock_excess(wm: WorkingMemory, bindings: dict[str, Any], asserted: list[Fact]) -> str:
        sku = bindings["sku_id"]
        eff = bindings["effective_inventory"]
        max_s = bindings["max_stock"]

        classification = Fact(
            name="StockClassificationFact",
            payload={
                "sku_id": sku,
                "status": "EXCESS",
                "urgency": "LOW",
                "order_needed": False,
                "overstock_units": eff - max_s,
            }
        )
        alert = Fact(
            name="AlertFact",
            payload={
                "level": "WARNING",
                "sku_id": sku,
                "message": f"Затоваривание склада: остаток {eff} превышает нормативный максимум {max_s}.",
            }
        )
        wm.assert_fact(classification)
        wm.assert_fact(alert)
        asserted.extend([classification, alert])
        return f"Позиция {sku}: обнаружен избыток запасов (I_eff={eff} > Max={max_s}). Заказы заблокированы."

    engine.register_rule(Rule(
        rule_id="RULE_STOCK_EXCESS",
        name="Диагностика затоваривания (излишка) склада",
        priority=50,
        condition=cond_stock_excess,
        action=act_stock_excess,
        description="При I_eff > Max_Stock присваивает статус EXCESS и блокирует заказы.",
        category="STOCK_CLASSIFICATION",
    ))

    # -----------------------------------------------------------------------
    # Rule 5: Supplier Reliability Tier 1 (OTIF >= 0.95 and Defect <= 0.01)
    # -----------------------------------------------------------------------
    def cond_supplier_tier1(wm: WorkingMemory) -> list[dict[str, Any]]:
        matches = []
        for fact in wm.get_facts_by_name("SupplierFact"):
            supplier_id = fact.get("supplier_id")
            otif = float(fact.get("on_time_delivery_rate", 0.0))
            defect = float(fact.get("defect_rate", 1.0))
            existing = [
                f for f in wm.get_facts_by_name("SupplierRatingFact")
                if f.get("supplier_id") == supplier_id
            ]
            if not existing and otif >= 0.95 and defect <= 0.01:
                matches.append({
                    "supplier_id": supplier_id,
                    "supplier_name": fact.get("name", supplier_id),
                    "otif": otif,
                    "defect": defect,
                    "_matched_fact_ids": [fact.id],
                })
        return matches

    def act_supplier_tier1(wm: WorkingMemory, bindings: dict[str, Any], asserted: list[Fact]) -> str:
        sup_id = bindings["supplier_id"]
        rating = Fact(
            name="SupplierRatingFact",
            payload={
                "supplier_id": sup_id,
                "tier": "TIER_1_PREFERRED",
                "reliability_rating": "HIGH",
                "recommendation": "PRIMARY_SOURCE",
            }
        )
        wm.assert_fact(rating)
        asserted.append(rating)
        return f"Поставщик {sup_id}: квалифицирован как TIER_1_PREFERRED (OTIF >= 95%, брак <= 1%)."

    engine.register_rule(Rule(
        rule_id="RULE_SUPPLIER_TIER1",
        name="Классификация надежного поставщика (Tier 1 Preferred)",
        priority=70,
        condition=cond_supplier_tier1,
        action=act_supplier_tier1,
        description="Квалифицирует контрагента как надежного при высоких показателях качества и сроков.",
        category="SUPPLIER_RATING",
    ))

    # -----------------------------------------------------------------------
    # Rule 6: Supplier Reliability Tier 3 (OTIF < 0.85 or Defect > 0.03)
    # -----------------------------------------------------------------------
    def cond_supplier_tier3(wm: WorkingMemory) -> list[dict[str, Any]]:
        matches = []
        for fact in wm.get_facts_by_name("SupplierFact"):
            supplier_id = fact.get("supplier_id")
            otif = float(fact.get("on_time_delivery_rate", 0.0))
            defect = float(fact.get("defect_rate", 0.0))
            existing = [
                f for f in wm.get_facts_by_name("SupplierRatingFact")
                if f.get("supplier_id") == supplier_id
            ]
            if not existing and (otif < 0.85 or defect > 0.03):
                matches.append({
                    "supplier_id": supplier_id,
                    "otif": otif,
                    "defect": defect,
                    "_matched_fact_ids": [fact.id],
                })
        return matches

    def act_supplier_tier3(wm: WorkingMemory, bindings: dict[str, Any], asserted: list[Fact]) -> str:
        sup_id = bindings["supplier_id"]
        rating = Fact(
            name="SupplierRatingFact",
            payload={
                "supplier_id": sup_id,
                "tier": "TIER_3_HIGH_RISK",
                "reliability_rating": "LOW",
                "recommendation": "AVOID_OR_DUAL_SOURCE",
            }
        )
        alert = Fact(
            name="AlertFact",
            payload={
                "level": "WARNING",
                "supplier_id": sup_id,
                "message": f"Поставщик {sup_id} имеет высокий риск срывов (OTIF={bindings['otif']*100:.1f}%, брак={bindings['defect']*100:.1f}%).",
            }
        )
        wm.assert_fact(rating)
        wm.assert_fact(alert)
        asserted.extend([rating, alert])
        return f"Поставщик {sup_id}: квалифицирован как TIER_3_HIGH_RISK из-за низкой дисциплины поставок."

    engine.register_rule(Rule(
        rule_id="RULE_SUPPLIER_TIER3",
        name="Классификация ненадежного поставщика (Tier 3 High Risk)",
        priority=70,
        condition=cond_supplier_tier3,
        action=act_supplier_tier3,
        description="Выявляет контрагентов с повышенным риском задержек и брака.",
        category="SUPPLIER_RATING",
    ))

    # -----------------------------------------------------------------------
    # Rule 7: Emergency Sourcing Heuristic (CRITICAL stock & slow primary supplier)
    # -----------------------------------------------------------------------
    def cond_emergency_sourcing(wm: WorkingMemory) -> list[dict[str, Any]]:
        matches = []
        # Find critical classifications
        for class_fact in wm.get_facts_by_name("StockClassificationFact"):
            if class_fact.get("status") == "CRITICAL":
                sku_id = class_fact.get("sku_id")
                # Check if emergency override already exists
                existing = [
                    f for f in wm.get_facts_by_name("EmergencySourcingFact")
                    if f.get("sku_id") == sku_id
                ]
                if existing:
                    continue

                # Look for assigned primary supplier
                primary_sup_fact = None
                for sup in wm.get_facts_by_name("SupplierFact"):
                    if sup.get("is_primary_for") == sku_id:
                        primary_sup_fact = sup
                        break

                # If primary lead time > 7 days, look for an express supplier
                if primary_sup_fact and float(primary_sup_fact.get("mean_lead_time_days", 0.0)) > 7.0:
                    for express_sup in wm.get_facts_by_name("SupplierFact"):
                        if (
                            express_sup.get("profile_type") == "LOCAL_EXPRESS"
                            or float(express_sup.get("mean_lead_time_days", 99.0)) <= 3.0
                        ):
                            matches.append({
                                "sku_id": sku_id,
                                "primary_supplier_id": primary_sup_fact.get("supplier_id"),
                                "primary_lead_time": float(primary_sup_fact.get("mean_lead_time_days")),
                                "express_supplier_id": express_sup.get("supplier_id"),
                                "express_lead_time": float(express_sup.get("mean_lead_time_days")),
                                "_matched_fact_ids": [class_fact.id, primary_sup_fact.id, express_sup.id],
                            })
                            break
        return matches

    def act_emergency_sourcing(wm: WorkingMemory, bindings: dict[str, Any], asserted: list[Fact]) -> str:
        sku = bindings["sku_id"]
        express_id = bindings["express_supplier_id"]
        prim_lt = bindings["primary_lead_time"]
        exp_lt = bindings["express_lead_time"]

        emergency_fact = Fact(
            name="EmergencySourcingFact",
            payload={
                "sku_id": sku,
                "recommended_supplier_id": express_id,
                "reason": (
                    f"Критический дефицит! Срок основного поставщика ({prim_lt} дн.) грозит остановкой. "
                    f"Переключение на экспресс-поставщика {express_id} ({exp_lt} дн.)."
                ),
            }
        )
        wm.assert_fact(emergency_fact)
        asserted.append(emergency_fact)
        return f"Позиция {sku}: активирована аварийная процедура закупки у экспресс-поставщика {express_id}."

    engine.register_rule(Rule(
        rule_id="RULE_EMERGENCY_SOURCING",
        name="Эвристика экстренной закупки у экспресс-поставщика",
        priority=90,  # High priority override
        condition=cond_emergency_sourcing,
        action=act_emergency_sourcing,
        description="Переключает заказ на резервного локального поставщика при критическом дефиците.",
        category="ORDERING_HEURISTICS",
    ))

    # -----------------------------------------------------------------------
    # Rule 8: Lot Sizing & Pack Multiplicity Alignment
    # -----------------------------------------------------------------------
    def cond_lot_sizing(wm: WorkingMemory) -> list[dict[str, Any]]:
        matches = []
        for prop_fact in wm.get_facts_by_name("RawOrderProposalFact"):
            sku_id = prop_fact.get("sku_id")
            existing = [
                f for f in wm.get_facts_by_name("AlignedOrderFact")
                if f.get("sku_id") == sku_id
            ]
            if not existing:
                matches.append({
                    "sku_id": sku_id,
                    "raw_quantity": float(prop_fact.get("quantity", 0.0)),
                    "pack_size": int(prop_fact.get("pack_size", 1)),
                    "moq": int(prop_fact.get("moq", 1)),
                    "_matched_fact_ids": [prop_fact.id],
                })
        return matches

    def act_lot_sizing(wm: WorkingMemory, bindings: dict[str, Any], asserted: list[Fact]) -> str:
        sku = bindings["sku_id"]
        raw_q = bindings["raw_quantity"]
        pack = max(1, bindings["pack_size"])
        moq = max(1, bindings["moq"])

        # Order must be at least MOQ and aligned to pack_size multiple
        target_q = max(raw_q, float(moq))
        aligned_q = math.ceil(target_q / pack) * pack

        aligned_fact = Fact(
            name="AlignedOrderFact",
            payload={
                "sku_id": sku,
                "aligned_quantity": float(aligned_q),
                "raw_quantity": raw_q,
                "pack_size": pack,
                "moq": moq,
            }
        )
        wm.assert_fact(aligned_fact)
        asserted.append(aligned_fact)
        return f"Позиция {sku}: объем партии скорректирован с {raw_q} до {aligned_q} (MOQ={moq}, упаковка={pack})."

    engine.register_rule(Rule(
        rule_id="RULE_LOT_SIZING_ALIGNMENT",
        name="Выравнивание партии заказа по MOQ и кратности упаковок",
        priority=60,
        condition=cond_lot_sizing,
        action=act_lot_sizing,
        description="Округляет сырой расчетный объем партии вверх до кратности упаковок и порога MOQ.",
        category="ORDERING_HEURISTICS",
    ))

    return engine
