"""Inventory optimization module for Inventory DSS."""

from inventory_dss.optimization.capacity import (
    CapacityOptimizationResult,
    CapacityOptimizer,
    check_warehouse_capacity,
    scale_single_item_to_capacity,
)
from inventory_dss.optimization.engine import InventoryOptimizer, OptimizationPlan
from inventory_dss.optimization.eoq import (
    EOQResult,
    calculate_classical_eoq,
    calculate_eoq_with_discounts,
    calculate_total_inventory_cost,
)
from inventory_dss.optimization.stochastic import (
    SERVICE_LEVEL_QUANTILES,
    calculate_lead_time_demand_variance,
    calculate_rop,
    calculate_safety_stock,
    calculate_stochastic_total_cost,
    get_service_level_z,
)

__all__ = [
    "SERVICE_LEVEL_QUANTILES",
    "CapacityOptimizationResult",
    "CapacityOptimizer",
    "EOQResult",
    "InventoryOptimizer",
    "OptimizationPlan",
    "calculate_classical_eoq",
    "calculate_eoq_with_discounts",
    "calculate_lead_time_demand_variance",
    "calculate_rop",
    "calculate_safety_stock",
    "calculate_stochastic_total_cost",
    "calculate_total_inventory_cost",
    "check_warehouse_capacity",
    "get_service_level_z",
    "scale_single_item_to_capacity",
]
