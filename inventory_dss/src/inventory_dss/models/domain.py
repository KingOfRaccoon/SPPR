"""Pydantic v2 domain models and data contracts for Inventory DSS."""

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator


class ProductCategory(str, Enum):
    ELECTRONICS = "Electronics"
    SPARE_PARTS = "Spare Parts"
    RAW_MATERIALS = "Raw Materials"
    CONSUMABLES = "Consumables"


class ABCClass(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class XYZClass(str, Enum):
    X = "X"
    Y = "Y"
    Z = "Z"


class StockStatus(str, Enum):
    CRITICAL = "CRITICAL"
    REORDER_NEEDED = "REORDER_NEEDED"
    OPTIMAL = "OPTIMAL"
    EXCESS = "EXCESS"


class UrgencyLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class SupplierProfileType(str, Enum):
    PREMIUM_RELIABLE = "PREMIUM_RELIABLE"
    BUDGET_VOLATILE = "BUDGET_VOLATILE"
    LOCAL_EXPRESS = "LOCAL_EXPRESS"
    OVERSEAS_BULK = "OVERSEAS_BULK"
    BALANCED_STANDARD = "BALANCED_STANDARD"


class DiscountTier(BaseModel):
    min_quantity: int = Field(..., ge=0)
    discount_percentage: float = Field(..., ge=0.0, lt=1.0)


class SKU(BaseModel):
    """Stock Keeping Unit (номенклатурная позиция) master data."""
    sku_id: str = Field(..., description="Unique SKU code, e.g. SKU-ELEC-001")
    name: str = Field(..., description="Descriptive item name")
    category: Literal["Electronics", "Spare Parts", "Raw Materials", "Consumables"]
    unit_price: float = Field(..., gt=0.0, description="Base unit price/value in RUB")
    holding_cost_annual_rate: float = Field(default=0.20, ge=0.01, le=1.0, description="Holding rate per year")
    unit_volume_m3: float = Field(..., gt=0.0, description="Volume per unit in m3")
    unit_weight_kg: float = Field(..., gt=0.0, description="Weight per unit in kg")
    pack_size: int = Field(default=1, ge=1, description="Packaging lot multiple")
    abc_class: Literal["A", "B", "C"] | None = None
    xyz_class: Literal["X", "Y", "Z"] | None = None
    unit_cost: float | None = Field(default=None, description="Direct purchase cost if distinct from price")
    stockout_penalty_per_unit: float | None = Field(default=None, description="Stockout cost penalty per unit")

    @field_validator("unit_price", "unit_volume_m3", "unit_weight_kg")
    @classmethod
    def validate_positive(cls, value: float, info) -> float:
        if value <= 0:
            raise ValueError(f"{info.field_name} must be strictly positive (> 0)")
        return value


class Supplier(BaseModel):
    """Supplier profile with lead time, reliability, and cost parameters."""
    supplier_id: str = Field(..., description="Unique supplier identifier, e.g. SUP-01")
    name: str = Field(..., description="Company name")
    mean_lead_time_days: float = Field(..., gt=0.0, description="Average delivery lead time mu_L")
    std_lead_time_days: float = Field(..., ge=0.0, description="Lead time standard deviation sigma_L")
    on_time_delivery_rate: float = Field(..., ge=0.0, le=1.0, description="OTIF fulfillment rate fraction [0, 1]")
    defect_rate: float = Field(..., ge=0.0, le=1.0, description="Quality defect rate fraction [0, 1]")
    min_order_quantity: int = Field(..., ge=1, description="Minimum order quantity (MOQ)")
    price_markup_factor: float = Field(default=1.0, gt=0.0, description="Price multiplier relative to base price")
    order_processing_cost: float = Field(default=3500.0, ge=0.0, description="Fixed order placement cost S in RUB")
    profile_type: SupplierProfileType | None = None
    discount_tiers: list[DiscountTier] = Field(default_factory=list)

    @field_validator("on_time_delivery_rate", "defect_rate")
    @classmethod
    def validate_rate(cls, value: float, info) -> float:
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"{info.field_name} must be in [0.0, 1.0]")
        return value


class Warehouse(BaseModel):
    """Central warehouse capacity specifications and operational thresholds."""
    warehouse_id: str = Field(default="WH-CENTRAL-01")
    name: str = Field(default="Центральный распределительный склад")
    total_volume_capacity_m3: float = Field(..., gt=0.0, description="Total storage volume in m3")
    total_weight_capacity_kg: float = Field(..., gt=0.0, description="Total rack load capacity in kg")
    fixed_order_cost: float = Field(default=50.0, ge=0.0, description="Fixed order cost S in EOQ")
    annual_capital_rate: float = Field(default=0.18, ge=0.01, le=1.0, description="Cost of working capital")
    target_service_level: float = Field(default=0.95, ge=0.50, lt=1.0, description="Target cycle service level")


class DemandRecord(BaseModel):
    """Historical or recorded daily demand observation."""
    date: date
    sku_id: str
    quantity: float = Field(..., ge=0.0, description="Demand quantity observed")
    is_promotional: bool = False
    is_weekend: bool = False
    stockout_flag: bool = False

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Demand quantity cannot be negative")
        return value


class InventoryState(BaseModel):
    """Current stock snapshot for a single SKU including effective stock calculation."""
    sku_id: str
    on_hand: float = Field(..., ge=0.0, description="Physical stock currently in warehouse")
    on_order: float = Field(default=0.0, ge=0.0, description="Quantity in-transit / open purchase orders")
    allocated: float = Field(default=0.0, ge=0.0, description="Stock reserved for customer orders")
    backorders: float = Field(default=0.0, ge=0.0, description="Unfulfilled past customer orders")
    safety_stock: float | None = Field(default=None, ge=0.0)
    reorder_point: float | None = Field(default=None, ge=0.0)
    max_stock: float | None = Field(default=None, ge=0.0)
    status: StockStatus | None = None

    @computed_field
    @property
    def effective_inventory(self) -> float:
        """Effective (available) inventory: on_hand + on_order - allocated - backorders."""
        return round(self.on_hand + self.on_order - self.allocated - self.backorders, 4)


class ForecastResult(BaseModel):
    """Time-series demand forecast output with point predictions and uncertainty bounds."""
    sku_id: str
    forecast_horizon_days: int = Field(..., ge=1)
    point_forecast: list[float]
    lower_bound_95: list[float]
    upper_bound_95: list[float]
    mean_daily_demand: float = Field(..., ge=0.0)
    std_daily_demand: float = Field(..., ge=0.0)
    metrics: dict[str, float] = Field(default_factory=dict, description="MAE, RMSE, MAPE, WAPE")
    model_name: str | None = None


class OptimizationPlan(BaseModel):
    """Optimal inventory policy parameters derived from cost minimization."""
    sku_id: str
    eoq: float = Field(..., ge=0.0, description="Economic Order Quantity batch size")
    safety_stock: float = Field(..., ge=0.0, description="Calculated safety stock buffer SS")
    reorder_point: float = Field(..., ge=0.0, description="Calculated reorder point ROP")
    expected_annual_holding_cost: float = Field(..., ge=0.0)
    expected_annual_ordering_cost: float = Field(..., ge=0.0)
    expected_total_cost: float = Field(..., ge=0.0)


class Recommendation(BaseModel):
    """Actionable replenishment decision recommendation for the Decision Maker (ЛПР)."""
    sku_id: str
    status: Literal["CRITICAL", "REORDER_NEEDED", "OPTIMAL", "EXCESS"]
    current_effective_stock: float
    reorder_point: float
    safety_stock: float
    order_needed: bool
    recommended_order_quantity: float = Field(..., ge=0.0)
    selected_supplier_id: str
    selected_supplier_name: str
    urgency: Literal["HIGH", "MEDIUM", "LOW", "NONE"]
    rationale: str
    estimated_purchase_cost_rub: float | None = Field(default=None, ge=0.0)
    warehouse_volume_required_m3: float | None = Field(default=None, ge=0.0)
    warehouse_weight_required_kg: float | None = Field(default=None, ge=0.0)


class PurchaseOrder(BaseModel):
    """Formalized purchase order approved by the Decision Maker."""
    order_id: str
    sku_id: str
    supplier_id: str
    quantity: float = Field(..., gt=0.0)
    unit_price: float = Field(..., gt=0.0)
    total_cost: float = Field(..., gt=0.0)
    order_date: date
    expected_delivery_date: date
    status: Literal["DRAFT", "APPROVED", "REJECTED", "PLACED", "DELIVERED"] = "DRAFT"

    @field_validator("quantity", "unit_price", "total_cost")
    @classmethod
    def validate_positive_order_numbers(cls, value: float, info) -> float:
        if value <= 0:
            raise ValueError(f"{info.field_name} must be strictly positive")
        return value
