"""Replenishment Recommendation Engine for Inventory Decision Support System.

Provides automated multi-item inventory status classification, order sizing with
packaging discretization and supplier MOQ, supplier multi-criteria allocation with
emergency expedited sourcing failover, and warehouse capacity constraint enforcement.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from inventory_dss.models.domain import (
    SKU,
    ForecastResult,
    InventoryState,
    OptimizationPlan,
    Recommendation,
    Supplier,
    Warehouse,
)
from inventory_dss.optimization.capacity import CapacityOptimizer, check_warehouse_capacity
from inventory_dss.recommendations.models import RecommendationBatch, StockHealthSummary
from inventory_dss.suppliers.evaluator import SupplierEvaluator


class RecommendationEngine:
    """Decision Support System engine for automated replenishment and supplier allocation."""

    def __init__(
        self,
        critical_doi_threshold: float = 3.0,
        excess_doi_threshold: float = 90.0,
        excess_multiplier: float = 2.0,
        emergency_lead_time_threshold_days: float = 7.0,
    ) -> None:
        self.critical_doi_threshold = critical_doi_threshold
        self.excess_doi_threshold = excess_doi_threshold
        self.excess_multiplier = excess_multiplier
        self.emergency_lead_time_threshold_days = emergency_lead_time_threshold_days
        self.supplier_evaluator = SupplierEvaluator()

    def classify_stock(
        self,
        effective_stock: float,
        safety_stock: float,
        reorder_point: float,
        eoq: float,
        mean_daily_demand: float,
    ) -> tuple[Literal["CRITICAL", "REORDER_NEEDED", "OPTIMAL", "EXCESS"], Literal["HIGH", "MEDIUM", "LOW", "NONE"], bool, float]:
        """Classify inventory state into CRITICAL, REORDER_NEEDED, OPTIMAL, or EXCESS.

        Returns:
            (status, urgency, order_needed, days_of_inventory)
        """
        # Guard for zero or dormant demand with positive stock
        if mean_daily_demand <= 0.0 and effective_stock > 0.0:
            return "OPTIMAL", "NONE", False, float("inf")

        doi = (
            effective_stock / mean_daily_demand
            if mean_daily_demand > 0.0
            else (float("inf") if effective_stock > 0 else 0.0)
        )

        max_stock = reorder_point + self.excess_multiplier * eoq

        # 1. CRITICAL: I_eff <= SS or (DOI < critical_doi_threshold with positive demand)
        if effective_stock <= safety_stock or (
            doi < self.critical_doi_threshold and mean_daily_demand > 0.0
        ):
            return "CRITICAL", "HIGH", True, doi

        # 2. REORDER_NEEDED: SS < I_eff <= ROP and DOI >= critical_doi_threshold
        if effective_stock <= reorder_point:
            return "REORDER_NEEDED", "MEDIUM", True, doi

        # 3. EXCESS: I_eff > max_stock or (DOI > excess_doi_threshold with positive demand)
        if effective_stock > max_stock or (
            doi > self.excess_doi_threshold and mean_daily_demand > 0.0
        ):
            return "EXCESS", "LOW", False, doi

        # 4. OPTIMAL: all remaining cases
        return "OPTIMAL", "NONE", False, doi

    def size_order(
        self,
        effective_stock: float,
        reorder_point: float,
        eoq: float,
        pack_size: int,
        moq: int,
    ) -> float:
        """Calculate order quantity respecting target buffer, supplier MOQ, and pack discretization."""
        target_stock = reorder_point + eoq
        raw_qty = max(eoq, target_stock - effective_stock)
        target_moq = max(raw_qty, float(max(1, moq)))
        pack = max(1, pack_size)
        return float(math.ceil(target_moq / pack) * pack)

    def select_supplier(
        self,
        status: str,
        suppliers: dict[str, Supplier],
        supplier_scores: dict[str, float],
    ) -> tuple[Supplier, bool]:
        """Select supplier: top TOPSIS score for normal orders, fastest express for critical stock."""
        if not suppliers:
            raise ValueError("No suppliers available for allocation")

        # Top ranked supplier by TOPSIS closeness
        best_supplier_id = max(supplier_scores.keys(), key=lambda sid: supplier_scores[sid])
        best_supplier = suppliers[best_supplier_id]

        if status == "CRITICAL" and len(suppliers) > 1:
            fastest_supplier = min(
                suppliers.values(),
                key=lambda s: s.mean_lead_time_days + 2.0 * s.std_lead_time_days,
            )
            # Switch to express supplier if faster than primary
            if fastest_supplier.supplier_id != best_supplier.supplier_id:
                return fastest_supplier, True
            return fastest_supplier, False

        return best_supplier, False

    def generate_recommendations(
        self,
        inventory_states: list[InventoryState],
        skus: dict[str, SKU],
        forecasts: dict[str, ForecastResult],
        policies: dict[str, OptimizationPlan],
        suppliers: dict[str, Supplier],
        warehouse: Warehouse,
        supplier_scores: dict[str, float] | None = None,
        enforce_capacity: bool = True,
    ) -> list[Recommendation]:
        """Generate replenishment recommendations conforming to DSS project contracts."""
        if not inventory_states or not suppliers:
            return []

        # 1. Supplier Evaluation
        if supplier_scores is None:
            supplier_scores = self.supplier_evaluator.evaluate_suppliers(list(suppliers.values()))

        raw_recommendations: list[Recommendation] = []
        unconstrained_quantities: dict[str, float] = {}

        # 2. Individual SKU Evaluation
        for state in inventory_states:
            sku = skus.get(state.sku_id)
            if sku is None:
                continue

            policy = policies.get(state.sku_id)
            forecast = forecasts.get(state.sku_id)

            ss = policy.safety_stock if policy else (state.safety_stock or 0.0)
            rop = policy.reorder_point if policy else (state.reorder_point or ss * 2.0)
            eoq = policy.eoq if policy else max(1.0, float(sku.pack_size))
            mean_demand = forecast.mean_daily_demand if forecast else 1.0

            ieff = state.effective_inventory
            status, urgency, order_needed, doi = self.classify_stock(
                effective_stock=ieff,
                safety_stock=ss,
                reorder_point=rop,
                eoq=eoq,
                mean_daily_demand=mean_demand,
            )

            sel_sup, is_emergency = self.select_supplier(status, suppliers, supplier_scores)

            if order_needed:
                rec_qty = self.size_order(
                    effective_stock=ieff,
                    reorder_point=rop,
                    eoq=eoq,
                    pack_size=sku.pack_size,
                    moq=sel_sup.min_order_quantity,
                )
                unconstrained_quantities[sku.sku_id] = rec_qty
                if is_emergency:
                    rationale = (
                        f"Status {status}: effective stock {ieff} below safety threshold {ss} (DOI={doi:.1f}d). "
                        f"Emergency sourcing activated: selected express supplier {sel_sup.name} "
                        f"(lead time {sel_sup.mean_lead_time_days}d) to avert stockout."
                    )
                else:
                    rationale = (
                        f"Status {status}: effective stock {ieff} at or below ROP {rop}. "
                        f"Selected primary supplier {sel_sup.name} (TOPSIS={supplier_scores.get(sel_sup.supplier_id, 0.0):.3f}, "
                        f"lead time {sel_sup.mean_lead_time_days}d, OTIF={sel_sup.on_time_delivery_rate * 100:.1f}%)."
                    )
            else:
                rec_qty = 0.0
                unconstrained_quantities[sku.sku_id] = 0.0
                max_s = rop + self.excess_multiplier * eoq
                if status == "EXCESS":
                    rationale = (
                        f"Status EXCESS: effective stock {ieff} exceeds maximum {max_s:.1f} (DOI={doi:.1f}d). "
                        f"Orders blocked."
                    )
                else:
                    rationale = (
                        f"Status OPTIMAL: effective stock {ieff} is adequate (ROP={rop}, DOI={doi:.1f}d). "
                        f"No order needed."
                    )

            unit_cost = sku.unit_cost or sku.unit_price
            eff_price = unit_cost * sel_sup.price_markup_factor

            raw_recommendations.append(
                Recommendation(
                    sku_id=sku.sku_id,
                    status=status,
                    current_effective_stock=round(ieff, 2),
                    reorder_point=round(rop, 2),
                    safety_stock=round(ss, 2),
                    order_needed=order_needed,
                    recommended_order_quantity=round(rec_qty, 2),
                    selected_supplier_id=sel_sup.supplier_id,
                    selected_supplier_name=sel_sup.name,
                    urgency=urgency,
                    rationale=rationale,
                    estimated_purchase_cost_rub=round(rec_qty * eff_price, 2),
                    warehouse_volume_required_m3=round(rec_qty * sku.unit_volume_m3, 4),
                    warehouse_weight_required_kg=round(rec_qty * sku.unit_weight_kg, 2),
                )
            )

        # 3. Warehouse Capacity Enforcement
        if not enforce_capacity:
            return raw_recommendations

        is_admissible, _tot_vol, _tot_wt = check_warehouse_capacity(
            unconstrained_quantities, skus, warehouse
        )
        if is_admissible:
            return raw_recommendations

        # Constrained scaling: protect CRITICAL items, trim REORDER_NEEDED items
        critical_vol = sum(
            r.recommended_order_quantity * skus[r.sku_id].unit_volume_m3
            for r in raw_recommendations
            if r.status == "CRITICAL"
        )
        critical_wt = sum(
            r.recommended_order_quantity * skus[r.sku_id].unit_weight_kg
            for r in raw_recommendations
            if r.status == "CRITICAL"
        )

        residual_v = max(0.0, warehouse.total_volume_capacity_m3 - critical_vol)
        residual_w = max(0.0, warehouse.total_weight_capacity_kg - critical_wt)

        reorder_items = [
            r for r in raw_recommendations if r.status == "REORDER_NEEDED" and r.order_needed
        ]

        if reorder_items and residual_v > 0.0 and residual_w > 0.0:
            wh_residual = Warehouse(
                warehouse_id=f"{warehouse.warehouse_id}-RESIDUAL",
                name="Residual Capacity Envelope",
                total_volume_capacity_m3=residual_v,
                total_weight_capacity_kg=residual_w,
                fixed_order_cost=warehouse.fixed_order_cost,
                annual_capital_rate=warehouse.annual_capital_rate,
            )
            reorder_eoqs = {r.sku_id: r.recommended_order_quantity for r in reorder_items}
            annual_demands = {
                r.sku_id: (forecasts[r.sku_id].mean_daily_demand * 365.0)
                if r.sku_id in forecasts
                else 1000.0
                for r in reorder_items
            }
            order_costs = {
                r.sku_id: getattr(
                    suppliers[r.selected_supplier_id],
                    "order_processing_cost",
                    warehouse.fixed_order_cost,
                )
                or warehouse.fixed_order_cost
                for r in reorder_items
            }
            holding_costs = {
                r.sku_id: (
                    skus[r.sku_id].holding_cost_annual_rate
                    * (skus[r.sku_id].unit_cost or skus[r.sku_id].unit_price)
                )
                for r in reorder_items
            }
            moqs = {
                r.sku_id: suppliers[r.selected_supplier_id].min_order_quantity
                for r in reorder_items
            }

            cap_optimizer = CapacityOptimizer(wh_residual)
            cap_res = cap_optimizer.optimize_allocation(
                unconstrained_eoqs=reorder_eoqs,
                skus={r.sku_id: skus[r.sku_id] for r in reorder_items},
                annual_demands=annual_demands,
                order_costs=order_costs,
                holding_costs=holding_costs,
                moqs=moqs,
            )
            trimmed_quantities = cap_res.allocated_quantities
        else:
            trimmed_quantities = {r.sku_id: 0.0 for r in reorder_items}

        final_recommendations: list[Recommendation] = []
        for r in raw_recommendations:
            if r.status == "REORDER_NEEDED" and r.sku_id in trimmed_quantities:
                new_q = trimmed_quantities[r.sku_id]
                sku = skus[r.sku_id]
                sel_sup = suppliers[r.selected_supplier_id]
                unit_cost = sku.unit_cost or sku.unit_price
                eff_price = unit_cost * sel_sup.price_markup_factor

                trimmed_r = Recommendation(
                    sku_id=r.sku_id,
                    status=r.status,
                    current_effective_stock=r.current_effective_stock,
                    reorder_point=r.reorder_point,
                    safety_stock=r.safety_stock,
                    order_needed=new_q > 0,
                    recommended_order_quantity=round(new_q, 2),
                    selected_supplier_id=r.selected_supplier_id,
                    selected_supplier_name=r.selected_supplier_name,
                    urgency=r.urgency,
                    rationale=(
                        r.rationale
                        + f" [Capacity trimmed from {r.recommended_order_quantity} to {new_q} to satisfy warehouse limits]"
                    ),
                    estimated_purchase_cost_rub=round(new_q * eff_price, 2),
                    warehouse_volume_required_m3=round(new_q * sku.unit_volume_m3, 4),
                    warehouse_weight_required_kg=round(new_q * sku.unit_weight_kg, 2),
                )
                final_recommendations.append(trimmed_r)
            else:
                final_recommendations.append(r)

        return final_recommendations

    def create_recommendation_batch(
        self,
        recommendations: list[Recommendation],
        warehouse: Warehouse,
    ) -> RecommendationBatch:
        """Create a structured RecommendationBatch report from recommendations and warehouse limits."""
        total_units = sum(r.recommended_order_quantity for r in recommendations)
        total_cost = sum(r.estimated_purchase_cost_rub or 0.0 for r in recommendations)
        total_vol = sum(r.warehouse_volume_required_m3 or 0.0 for r in recommendations)
        total_wt = sum(r.warehouse_weight_required_kg or 0.0 for r in recommendations)
        orders_needed = sum(1 for r in recommendations if r.order_needed)

        v_max = warehouse.total_volume_capacity_m3
        w_max = warehouse.total_weight_capacity_kg

        return RecommendationBatch(
            batch_id=f"BATCH-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6].upper()}",
            recommendations=recommendations,
            total_skus_evaluated=len(recommendations),
            orders_needed_count=orders_needed,
            total_recommended_units=round(total_units, 2),
            total_purchase_cost_rub=round(total_cost, 2),
            total_volume_m3=round(total_vol, 4),
            total_weight_kg=round(total_wt, 2),
            warehouse_volume_capacity_m3=v_max,
            warehouse_weight_capacity_kg=w_max,
            volume_utilization=round(total_vol / v_max, 4) if v_max > 0 else 0.0,
            weight_utilization=round(total_wt / w_max, 4) if w_max > 0 else 0.0,
            is_capacity_constrained=(total_vol > v_max or total_wt > w_max),
        )

    def generate_batch(
        self,
        inventory_states: list[InventoryState],
        skus: dict[str, SKU],
        forecasts: dict[str, ForecastResult],
        policies: dict[str, OptimizationPlan],
        suppliers: dict[str, Supplier],
        warehouse: Warehouse,
        supplier_scores: dict[str, float] | None = None,
        enforce_capacity: bool = True,
    ) -> RecommendationBatch:
        """Generate structured RecommendationBatch report with capacity analytics."""
        recs = self.generate_recommendations(
            inventory_states=inventory_states,
            skus=skus,
            forecasts=forecasts,
            policies=policies,
            suppliers=suppliers,
            warehouse=warehouse,
            supplier_scores=supplier_scores,
            enforce_capacity=enforce_capacity,
        )
        return self.create_recommendation_batch(recs, warehouse)

    def generate_health_summary(
        self,
        recommendations: list[Recommendation],
        skus: dict[str, SKU],
    ) -> StockHealthSummary:
        """Compute portfolio-wide stock health indicators for executive BI overview."""
        crit_skus = [r.sku_id for r in recommendations if r.status == "CRITICAL"]
        reorder_skus = [r.sku_id for r in recommendations if r.status == "REORDER_NEEDED"]
        optimal_skus = [r.sku_id for r in recommendations if r.status == "OPTIMAL"]
        excess_skus = [r.sku_id for r in recommendations if r.status == "EXCESS"]

        total_oh_val = 0.0
        total_excess_val = 0.0

        for r in recommendations:
            sku = skus.get(r.sku_id)
            if not sku:
                continue
            val_unit = sku.unit_cost or sku.unit_price
            if r.current_effective_stock > 0:
                total_oh_val += r.current_effective_stock * val_unit
            if r.status == "EXCESS":
                excess_units = max(0.0, r.current_effective_stock - r.reorder_point)
                total_excess_val += excess_units * val_unit

        return StockHealthSummary(
            total_skus=len(recommendations),
            critical_skus=crit_skus,
            reorder_skus=reorder_skus,
            optimal_skus=optimal_skus,
            excess_skus=excess_skus,
            total_on_hand_value_rub=round(total_oh_val, 2),
            total_excess_value_rub=round(total_excess_val, 2),
        )

    get_stock_health_summary = generate_health_summary
