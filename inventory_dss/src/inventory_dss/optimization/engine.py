"""High-level inventory optimization engine orchestrating stochastic policies and batch sizing."""

from __future__ import annotations

import math

from inventory_dss.models.domain import (
    SKU,
    ForecastResult,
    OptimizationPlan,
    Supplier,
    Warehouse,
)
from inventory_dss.optimization.capacity import CapacityOptimizer
from inventory_dss.optimization.eoq import (
    calculate_classical_eoq,
    calculate_eoq_with_discounts,
)
from inventory_dss.optimization.stochastic import (
    calculate_rop,
    calculate_safety_stock,
)


class InventoryOptimizer:
    """Decision Support System optimization engine.

    Computes stochastic safety stock (joint demand & lead-time variance via Wald's identity),
    dynamic reorder point (ROP), optimal batch sizing (EOQ with discounts and pack batching),
    and warehouse capacity constrained policies.
    """

    def calculate_policy(
        self,
        sku: SKU,
        demand_forecast: ForecastResult,
        supplier: Supplier,
        warehouse: Warehouse,
        service_level: float = 0.95,
    ) -> OptimizationPlan:
        """Calculate single-SKU optimal replenishment policy under uncertainty."""
        mu_d = max(0.0, float(demand_forecast.mean_daily_demand))
        sigma_d = max(0.0, float(demand_forecast.std_daily_demand))
        mu_l = max(0.1, float(supplier.mean_lead_time_days))
        sigma_l = max(0.0, float(supplier.std_lead_time_days))

        # 1. Joint Uncertainty Safety Stock (Wald's Identity)
        safety_stock = calculate_safety_stock(
            mean_demand=mu_d,
            std_demand=sigma_d,
            mean_lead_time=mu_l,
            std_lead_time=sigma_l,
            service_level=service_level,
        )

        # 2. Dynamic Reorder Point
        reorder_point = calculate_rop(
            mean_demand=mu_d,
            mean_lead_time=mu_l,
            safety_stock=safety_stock,
        )

        # 3. Cost Parameters
        annual_demand = mu_d * 365.0
        unit_cost = sku.unit_cost or sku.unit_price
        effective_price = unit_cost * supplier.price_markup_factor
        holding_rate = sku.holding_cost_annual_rate or warehouse.annual_capital_rate
        h = max(1e-4, holding_rate * effective_price)
        k = max(1.0, supplier.order_processing_cost or warehouse.fixed_order_cost)
        pack = max(1, sku.pack_size)
        moq = max(1, supplier.min_order_quantity)

        # 4. Economic Order Quantity (EOQ)
        if supplier.discount_tiers:
            eoq_res = calculate_eoq_with_discounts(
                annual_demand=annual_demand,
                base_unit_price=effective_price,
                holding_rate=holding_rate,
                order_cost=k,
                discount_tiers=supplier.discount_tiers,
                min_order_quantity=moq,
                pack_size=pack,
                safety_stock=safety_stock,
            )
            eoq = eoq_res.optimal_quantity
            expected_annual_holding = eoq_res.holding_cost
            expected_annual_ordering = eoq_res.ordering_cost
            expected_total_cost = eoq_res.total_cost
        else:
            if annual_demand > 0.0:
                raw_eoq = calculate_classical_eoq(annual_demand, k, h)
            else:
                raw_eoq = 0.0

            # MOQ and pack size rounding
            eoq = max(float(moq), math.ceil(raw_eoq / pack) * pack)
            expected_annual_holding = h * (eoq / 2.0 + safety_stock)
            expected_annual_ordering = (annual_demand / max(1.0, eoq)) * k if annual_demand > 0.0 else 0.0
            expected_total_cost = round(
                expected_annual_holding + expected_annual_ordering + annual_demand * effective_price,
                2,
            )

        return OptimizationPlan(
            sku_id=sku.sku_id,
            eoq=round(eoq, 2),
            safety_stock=safety_stock,
            reorder_point=reorder_point,
            expected_annual_holding_cost=round(expected_annual_holding, 2),
            expected_annual_ordering_cost=round(expected_annual_ordering, 2),
            expected_total_cost=expected_total_cost,
        )

    def calculate_multi_item_policies(
        self,
        skus: list[SKU] | dict[str, SKU],
        forecasts: dict[str, ForecastResult],
        suppliers: dict[str, Supplier],
        warehouse: Warehouse,
        service_level: float = 0.95,
        enforce_capacity: bool = True,
    ) -> dict[str, OptimizationPlan]:
        """Compute coordinated policies for multiple items, optionally enforcing warehouse limits."""
        skus_list = list(skus.values()) if isinstance(skus, dict) else list(skus)
        unconstrained_policies: dict[str, OptimizationPlan] = {}
        for sku in skus_list:
            fc = forecasts.get(sku.sku_id)
            if fc is None:
                continue
            sup = suppliers.get(sku.sku_id)
            if sup is None and suppliers:
                sup = next(iter(suppliers.values()))
            if sup is None:
                sup = Supplier(
                    supplier_id="SUP-DEFAULT",
                    name="Default Supplier",
                    mean_lead_time_days=7.0,
                    std_lead_time_days=1.5,
                    on_time_delivery_rate=0.95,
                    defect_rate=0.01,
                    min_order_quantity=1,
                    order_processing_cost=warehouse.fixed_order_cost,
                )
            policy = self.calculate_policy(sku, fc, sup, warehouse, service_level)
            unconstrained_policies[sku.sku_id] = policy

        if not enforce_capacity or not unconstrained_policies:
            return unconstrained_policies

        # Check total capacity
        skus_dict = {s.sku_id: s for s in skus_list}
        unconstrained_eoqs = {sid: p.eoq for sid, p in unconstrained_policies.items()}
        annual_demands = {sid: forecasts[sid].mean_daily_demand * 365.0 for sid in unconstrained_eoqs}
        order_costs: dict[str, float] = {}
        holding_costs: dict[str, float] = {}
        moqs: dict[str, int] = {}

        for sid in unconstrained_eoqs:
            sku = skus_dict[sid]
            sup = suppliers.get(sid) or (next(iter(suppliers.values())) if suppliers else None)
            if sup is not None:
                moqs[sid] = max(1, sup.min_order_quantity)
                order_costs[sid] = max(1.0, sup.order_processing_cost or warehouse.fixed_order_cost)
                unit_cost = sku.unit_cost or sku.unit_price
                eff_price = unit_cost * sup.price_markup_factor
                holding_rate = sku.holding_cost_annual_rate or warehouse.annual_capital_rate
                holding_costs[sid] = max(1e-4, holding_rate * eff_price)
            else:
                moqs[sid] = 1
                order_costs[sid] = max(1.0, warehouse.fixed_order_cost)
                holding_rate = sku.holding_cost_annual_rate or warehouse.annual_capital_rate
                holding_costs[sid] = max(1e-4, holding_rate * (sku.unit_cost or sku.unit_price))

        cap_optimizer = CapacityOptimizer(warehouse)
        cap_result = cap_optimizer.optimize_allocation(
            unconstrained_eoqs=unconstrained_eoqs,
            skus=skus_dict,
            annual_demands=annual_demands,
            order_costs=order_costs,
            holding_costs=holding_costs,
            moqs=moqs,
        )

        if not cap_result.is_constrained:
            return unconstrained_policies

        # Rebuild policies with scaled EOQ respecting supplier contract MOQ
        constrained_policies: dict[str, OptimizationPlan] = {}
        for sid, p in unconstrained_policies.items():
            allocated_q = cap_result.allocated_quantities.get(sid, p.eoq)
            min_moq = moqs.get(sid, 1)
            new_eoq = max(float(min_moq), float(allocated_q))
            sku = skus_dict[sid]
            sup = suppliers.get(sid) or (next(iter(suppliers.values())) if suppliers else None)
            if sup is not None:
                unit_cost = sku.unit_cost or sku.unit_price
                eff_price = unit_cost * sup.price_markup_factor
                holding_rate = sku.holding_cost_annual_rate or warehouse.annual_capital_rate
                h = max(1e-4, holding_rate * eff_price)
                k = max(1.0, sup.order_processing_cost or warehouse.fixed_order_cost)
            else:
                eff_price = sku.unit_cost or sku.unit_price
                holding_rate = sku.holding_cost_annual_rate or warehouse.annual_capital_rate
                h = max(1e-4, holding_rate * eff_price)
                k = max(1.0, warehouse.fixed_order_cost)

            d_ann = annual_demands[sid]
            hold_c = h * (new_eoq / 2.0 + p.safety_stock)
            order_c = (d_ann / max(1.0, new_eoq)) * k if d_ann > 0 else 0.0
            tot_c = round(hold_c + order_c + d_ann * eff_price, 2)

            constrained_policies[sid] = OptimizationPlan(
                sku_id=sid,
                eoq=new_eoq,
                safety_stock=p.safety_stock,
                reorder_point=p.reorder_point,
                expected_annual_holding_cost=round(hold_c, 2),
                expected_annual_ordering_cost=round(order_c, 2),
                expected_total_cost=tot_c,
            )

        return constrained_policies

    # Backward-compatible alias
    optimize_multi_item_policies = calculate_multi_item_policies
