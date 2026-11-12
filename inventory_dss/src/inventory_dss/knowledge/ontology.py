"""Domain ontology for the Inventory Decision Support System (СППР Управления Запасами).

Provides formal concept definitions, taxonomy hierarchies, semantic relationships,
and domain axioms for inventory management, supplier relations, and warehouse logistics.
"""

from dataclasses import dataclass, field
from enum import Enum


class ConceptType(str, Enum):
    CLASS = "CLASS"
    RELATION = "RELATION"
    AXIOM = "AXIOM"
    INDIVIDUAL = "INDIVIDUAL"


@dataclass
class OntologyClass:
    """A semantic class or concept in the domain ontology."""
    id: str
    name: str
    description: str
    parent_id: str | None = None
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class OntologyRelation:
    """A directed semantic relationship between two ontology concepts."""
    id: str
    name: str
    source_class_id: str
    target_class_id: str
    inverse_name: str | None = None
    description: str = ""


@dataclass
class OntologyAxiom:
    """A domain rule, invariant, or constraint assertion."""
    id: str
    name: str
    formal_expression: str
    description: str
    severity: str = "ERROR"  # ERROR, WARNING


class DomainOntology:
    """In-memory domain ontology graph supporting taxonomy traversal and consistency checks."""

    def __init__(self, name: str = "InventoryDSSOntology"):
        self.name = name
        self.classes: dict[str, OntologyClass] = {}
        self.relations: dict[str, OntologyRelation] = {}
        self.axioms: dict[str, OntologyAxiom] = {}

    def add_class(self, ontology_class: OntologyClass) -> None:
        if ontology_class.id in self.classes:
            raise ValueError(f"Class with ID '{ontology_class.id}' already registered")
        self.classes[ontology_class.id] = ontology_class

    def add_relation(self, relation: OntologyRelation) -> None:
        if relation.id in self.relations:
            raise ValueError(f"Relation with ID '{relation.id}' already registered")
        self.relations[relation.id] = relation

    def add_axiom(self, axiom: OntologyAxiom) -> None:
        if axiom.id in self.axioms:
            raise ValueError(f"Axiom with ID '{axiom.id}' already registered")
        self.axioms[axiom.id] = axiom

    def get_class(self, class_id: str) -> OntologyClass | None:
        return self.classes.get(class_id)

    def get_subclasses(self, class_id: str, recursive: bool = True) -> list[OntologyClass]:
        """Return all direct or indirect subclasses of a given class."""
        direct = [c for c in self.classes.values() if c.parent_id == class_id]
        if not recursive:
            return direct
        result = list(direct)
        for child in direct:
            result.extend(self.get_subclasses(child.id, recursive=True))
        return result

    def get_superclasses(self, class_id: str) -> list[OntologyClass]:
        """Return path of ancestors from immediate parent up to the root."""
        ancestors: list[OntologyClass] = []
        curr = self.classes.get(class_id)
        visited: set[str] = set()
        while curr and curr.parent_id:
            if curr.parent_id in visited:
                break  # Cycle detected, prevent infinite loop
            visited.add(curr.parent_id)
            parent = self.classes.get(curr.parent_id)
            if parent:
                ancestors.append(parent)
                curr = parent
            else:
                break
        return ancestors

    def is_subclass_of(self, sub_class_id: str, super_class_id: str) -> bool:
        """Check if sub_class_id is a subclass of super_class_id."""
        if sub_class_id == super_class_id:
            return True
        superclasses = self.get_superclasses(sub_class_id)
        return any(sc.id == super_class_id for sc in superclasses)

    def get_relations_from(self, class_id: str) -> list[OntologyRelation]:
        """Find all relations originating from class_id or its superclasses."""
        applicable_classes = {class_id} | {sc.id for sc in self.get_superclasses(class_id)}
        return [r for r in self.relations.values() if r.source_class_id in applicable_classes]

    def get_relations_to(self, class_id: str) -> list[OntologyRelation]:
        """Find all relations targeting class_id or its superclasses."""
        applicable_classes = {class_id} | {sc.id for sc in self.get_superclasses(class_id)}
        return [r for r in self.relations.values() if r.target_class_id in applicable_classes]

    def validate_consistency(self) -> list[str]:
        """Validate structural consistency of the ontology graph."""
        errors: list[str] = []

        # 1. Check parent references
        for c in self.classes.values():
            if c.parent_id and c.parent_id not in self.classes:
                errors.append(f"Class '{c.id}' references undefined parent '{c.parent_id}'")

        # 2. Check circular inheritance
        for c in self.classes.values():
            visited: set[str] = set()
            curr = c
            while curr and curr.parent_id:
                if curr.id in visited:
                    errors.append(f"Circular inheritance detected involving class '{curr.id}'")
                    break
                visited.add(curr.id)
                curr = self.classes.get(curr.parent_id)

        # 3. Check relation endpoints
        for r in self.relations.values():
            if r.source_class_id not in self.classes:
                errors.append(f"Relation '{r.id}' has undefined source class '{r.source_class_id}'")
            if r.target_class_id not in self.classes:
                errors.append(f"Relation '{r.id}' has undefined target class '{r.target_class_id}'")

        return errors


def build_inventory_ontology() -> DomainOntology:
    """Construct and return the canonical domain ontology for Inventory DSS."""
    ontology = DomainOntology("InventoryManagementOntology")

    # -----------------------------------------------------------------------
    # Classes & Taxonomy
    # -----------------------------------------------------------------------
    # Root
    ontology.add_class(OntologyClass(
        id="DomainEntity",
        name="Сущность предметной области",
        description="Базовый класс всех понятий предметной области управления запасами"
    ))

    # Inventory Items
    ontology.add_class(OntologyClass(
        id="InventoryItem",
        name="Товарно-материальный запас (SKU)",
        description="Номенклатурная единица хранения и закупки",
        parent_id="DomainEntity",
        properties={
            "sku_id": "str",
            "unit_price": "float",
            "unit_volume_m3": "float",
            "unit_weight_kg": "float",
            "pack_size": "int",
        }
    ))
    ontology.add_class(OntologyClass(
        id="HighValueItem",
        name="Позиция категории A (Высокая ценность)",
        description="80% доли совокупного товарооборота (ABC-анализ)",
        parent_id="InventoryItem"
    ))
    ontology.add_class(OntologyClass(
        id="MediumValueItem",
        name="Позиция категории B (Средняя ценность)",
        description="15% доли совокупного товарооборота (ABC-анализ)",
        parent_id="InventoryItem"
    ))
    ontology.add_class(OntologyClass(
        id="LowValueItem",
        name="Позиция категории C (Низкая ценность)",
        description="5% доли совокупного товарооборота (ABC-анализ)",
        parent_id="InventoryItem"
    ))
    ontology.add_class(OntologyClass(
        id="IntermittentDemandItem",
        name="Позиция с прерывистым спросом (Класс Z)",
        description="Товар с высокой долей нулевого спроса и редкими случайными пиками",
        parent_id="InventoryItem"
    ))

    # Actors & Supply Chain Nodes
    ontology.add_class(OntologyClass(
        id="SupplyChainActor",
        name="Субъект цепи поставок",
        description="Участник процесса управления или поставок",
        parent_id="DomainEntity"
    ))
    ontology.add_class(OntologyClass(
        id="Supplier",
        name="Поставщик",
        description="Контрагент, осуществляющий поставку номенклатурных позиций",
        parent_id="SupplyChainActor",
        properties={
            "mean_lead_time_days": "float",
            "std_lead_time_days": "float",
            "on_time_delivery_rate": "float",
            "defect_rate": "float",
            "moq": "int",
        }
    ))
    ontology.add_class(OntologyClass(
        id="ReliableSupplier",
        name="Надежный поставщик (Tier 1)",
        description="Поставщик с высоким OTIF (>= 95%) и низкой долей брака (<= 1%)",
        parent_id="Supplier"
    ))
    ontology.add_class(OntologyClass(
        id="ExpressSupplier",
        name="Резервный экспресс-поставщик",
        description="Локальный поставщик с минимальным сроком поставки для покрытия дефицита",
        parent_id="Supplier"
    ))
    ontology.add_class(OntologyClass(
        id="DecisionMaker",
        name="Лицо, принимающее решения (ЛПР)",
        description="Ответственный руководитель, утверждающий планы закупок",
        parent_id="SupplyChainActor"
    ))

    # Logistics Facilities
    ontology.add_class(OntologyClass(
        id="LogisticsFacility",
        name="Логистический объект",
        description="Складской комплекс или распределительный центр",
        parent_id="DomainEntity"
    ))
    ontology.add_class(OntologyClass(
        id="Warehouse",
        name="Склад",
        description="Центральный распределительный склад с ограничениями емкости",
        parent_id="LogisticsFacility",
        properties={
            "max_volume_m3": "float",
            "max_weight_kg": "float",
            "fixed_order_cost": "float",
        }
    ))

    # Inventory State & Decision Artifacts
    ontology.add_class(OntologyClass(
        id="DecisionArtifact",
        name="Артефакт принятия решений",
        description="Вычисляемые срезы состояния и рекомендации СППР",
        parent_id="DomainEntity"
    ))
    ontology.add_class(OntologyClass(
        id="InventoryState",
        name="Состояние запаса позиции",
        description="Текущий статус обеспеченности склада по номенклатуре",
        parent_id="DecisionArtifact",
        properties={
            "effective_inventory": "float",
            "safety_stock": "float",
            "reorder_point": "float",
        }
    ))
    ontology.add_class(OntologyClass(
        id="CriticalDeficitState",
        name="Состояние критического дефицита",
        description="Эффективный запас ниже или равен уровню страхового запаса (I_eff <= SS)",
        parent_id="InventoryState"
    ))
    ontology.add_class(OntologyClass(
        id="ReorderNeededState",
        name="Состояние планового пополнения",
        description="Эффективный запас в диапазоне (SS, ROP]",
        parent_id="InventoryState"
    ))
    ontology.add_class(OntologyClass(
        id="OptimalStockState",
        name="Оптимальное состояние запаса",
        description="Эффективный запас в нормативном диапазоне (ROP, S_max]",
        parent_id="InventoryState"
    ))
    ontology.add_class(OntologyClass(
        id="ExcessStockState",
        name="Состояние затоваривания (Излишек)",
        description="Эффективный запас превышает максимальный норматив S_max",
        parent_id="InventoryState"
    ))
    ontology.add_class(OntologyClass(
        id="ReplenishmentRecommendation",
        name="Рекомендация по пополнению",
        description="Сформированное СППР предложение по заказу с указанием объема и поставщика",
        parent_id="DecisionArtifact"
    ))
    ontology.add_class(OntologyClass(
        id="PurchaseOrder",
        name="Заказ на закупку",
        description="Утвержденный заказ контрагенту",
        parent_id="DecisionArtifact"
    ))

    # -----------------------------------------------------------------------
    # Relations
    # -----------------------------------------------------------------------
    ontology.add_relation(OntologyRelation(
        id="REL_SUPPLIED_BY",
        name="SUPPLIED_BY",
        source_class_id="InventoryItem",
        target_class_id="Supplier",
        inverse_name="SUPPLIES",
        description="Связывает номенклатурную позицию с авторизованным поставщиком"
    ))
    ontology.add_relation(OntologyRelation(
        id="REL_STORED_IN",
        name="STORED_IN",
        source_class_id="InventoryItem",
        target_class_id="Warehouse",
        inverse_name="STORES",
        description="Указывает склад хранения номенклатурной позиции"
    ))
    ontology.add_relation(OntologyRelation(
        id="REL_HAS_STATE",
        name="HAS_STATE",
        source_class_id="InventoryItem",
        target_class_id="InventoryState",
        inverse_name="STATE_OF",
        description="Связывает SKU с его текущим расчетным состоянием запасов"
    ))
    ontology.add_relation(OntologyRelation(
        id="REL_TRIGGERS_RECOMMENDATION",
        name="TRIGGERS_RECOMMENDATION",
        source_class_id="InventoryState",
        target_class_id="ReplenishmentRecommendation",
        inverse_name="TRIGGERED_BY",
        description="Состояние дефицита или точки заказа инициирует рекомендацию по пополнению"
    ))
    ontology.add_relation(OntologyRelation(
        id="REL_CONSTRAINED_BY",
        name="CONSTRAINED_BY",
        source_class_id="ReplenishmentRecommendation",
        target_class_id="Warehouse",
        inverse_name="CONSTRAINS",
        description="Рекомендуемый объем закупки ограничивается физической емкостью склада"
    ))
    ontology.add_relation(OntologyRelation(
        id="REL_REVIEWED_BY",
        name="REVIEWED_BY",
        source_class_id="ReplenishmentRecommendation",
        target_class_id="DecisionMaker",
        inverse_name="REVIEWS",
        description="Рекомендация передается на утверждение ЛПР"
    ))

    # -----------------------------------------------------------------------
    # Axioms
    # -----------------------------------------------------------------------
    ontology.add_axiom(OntologyAxiom(
        id="AX_EFFECTIVE_INVENTORY",
        name="Аксиома эффективного остатка",
        formal_expression="I_eff == on_hand + on_order - allocated - backorders",
        description="Эффективный остаток учитывает физический остаток, заказы в пути и обязательства"
    ))
    ontology.add_axiom(OntologyAxiom(
        id="AX_WAREHOUSE_VOLUME_LIMIT",
        name="Аксиома предельного объема склада",
        formal_expression="sum(quantity_i * unit_volume_m3_i) <= max_volume_m3",
        description="Суммарный объем размещенных позиций не должен превышать полезный объем склада"
    ))
    ontology.add_axiom(OntologyAxiom(
        id="AX_WAREHOUSE_WEIGHT_LIMIT",
        name="Аксиома предельной массы склада",
        formal_expression="sum(quantity_i * unit_weight_kg_i) <= max_weight_kg",
        description="Суммарная масса размещенных позиций не должна превышать допустимую нагрузку на стеллажи"
    ))
    ontology.add_axiom(OntologyAxiom(
        id="AX_CRITICAL_ORDER_MANDATORY",
        name="Аксиома обязательности заказа при дефиците",
        formal_expression="I_eff <= safety_stock => order_needed == True and urgency == 'HIGH'",
        description="При падении эффективного остатка до или ниже уровня страхового запаса заказ обязателен"
    ))

    return ontology
