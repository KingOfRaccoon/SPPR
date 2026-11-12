"""Economic Order Quantity (EOQ) models with quantity tier discounts and cost breakdowns."""

from __future__ import annotations

import math
from dataclasses import dataclass

from inventory_dss.models.domain import DiscountTier


@dataclass(frozen=True)
class EOQResult:
    """Detailed breakdown of EOQ calculation and expected annual logistics costs."""

    optimal_quantity: float
    raw_eoq: float
    purchasing_cost: float
    ordering_cost: float
    holding_cost: float
    total_cost: float
    effective_unit_price: float
    applied_discount_rate: float
    applied_tier_min_quantity: int


def calculate_classical_eoq(
    annual_demand: float,
    order_cost: float,
    holding_cost_per_unit: float,
) -> float:
    """Wilson Economic Order Quantity: Q* = sqrt(2*D*K / H)."""
    if annual_demand <= 0.0 or holding_cost_per_unit <= 0.0 or order_cost <= 0.0:
        return 0.0
    return math.sqrt((2.0 * annual_demand * order_cost) / holding_cost_per_unit)


def calculate_total_inventory_cost(
    quantity: float,
    annual_demand: float,
    unit_price: float,
    holding_cost_rate: float,
    order_cost: float,
    safety_stock: float = 0.0,
) -> tuple[float, float, float, float]:
    """Calculate annual purchasing, ordering, holding, and total cost.

    Returns:
        (purchasing_cost, ordering_cost, holding_cost, total_cost)
    """
    if quantity <= 0.0:
        purch = annual_demand * unit_price
        return purch, 0.0, 0.0, purch

    h = max(1e-6, holding_cost_rate * unit_price)
    purchasing_cost = annual_demand * unit_price
    ordering_cost = (annual_demand / quantity) * order_cost if annual_demand > 0.0 else 0.0
    holding_cost = h * (quantity / 2.0 + safety_stock)
    total_cost = purchasing_cost + ordering_cost + holding_cost
    return purchasing_cost, ordering_cost, holding_cost, total_cost


def calculate_eoq_with_discounts(
    annual_demand: float,
    base_unit_price: float,
    holding_rate: float,
    order_cost: float,
    discount_tiers: list[DiscountTier] | None = None,
    min_order_quantity: int = 1,
    pack_size: int = 1,
    safety_stock: float = 0.0,
) -> EOQResult:
    """Evaluate all-units quantity discount schedule and find cost-minimizing order size.

    Adjusts final batch size to supplier MOQ and pack size multiples.
    """
    moq = max(1, min_order_quantity)
    pack = max(1, pack_size)

    # Base tier (no discount)
    tiers = [DiscountTier(min_quantity=0, discount_percentage=0.0)]
    if discount_tiers:
        # Sort user tiers by min_quantity ascending
        sorted_tiers = sorted(discount_tiers, key=lambda t: t.min_quantity)
        for t in sorted_tiers:
            if t.min_quantity > 0:
                tiers.append(t)

    best_result: EOQResult | None = None
    min_total_cost = float("inf")

    # Evaluate candidate batch sizes for each tier
    for i, tier in enumerate(tiers):
        disc = tier.discount_percentage
        p_eff = base_unit_price * (1.0 - disc)
        h_eff = max(1e-6, holding_rate * p_eff)

        # Classical unconstrained EOQ for this tier price
        if annual_demand > 0.0 and h_eff > 0.0:
            raw_eoq = math.sqrt((2.0 * annual_demand * order_cost) / h_eff)
        else:
            raw_eoq = 0.0

        # Next tier cutoff if present
        next_cutoff = tiers[i + 1].min_quantity if i + 1 < len(tiers) else float("inf")

        # Candidate selection rule for all-units discounts:
        # 1. If EOQ_k is within [tier.min_quantity, next_cutoff), candidate is EOQ_k
        # 2. If EOQ_k < tier.min_quantity, candidate is price break point tier.min_quantity
        # 3. If EOQ_k >= next_cutoff, candidate is discarded (dominated by higher tier)
        if raw_eoq < tier.min_quantity:
            cand_qty = float(tier.min_quantity)
        elif raw_eoq < next_cutoff:
            cand_qty = raw_eoq
        else:
            cand_qty = float(next_cutoff)

        # Batching: apply supplier MOQ and pack size rounding up
        batched_qty = max(float(moq), math.ceil(cand_qty / pack) * pack)

        # Determine effective discount actually applicable to batched_qty
        actual_tier = tier
        for t in reversed(tiers):
            if batched_qty >= t.min_quantity:
                actual_tier = t
                break

        actual_p = base_unit_price * (1.0 - actual_tier.discount_percentage)
        purch_c, order_c, hold_c, total_c = calculate_total_inventory_cost(
            quantity=batched_qty,
            annual_demand=annual_demand,
            unit_price=actual_p,
            holding_cost_rate=holding_rate,
            order_cost=order_cost,
            safety_stock=safety_stock,
        )

        if total_c < min_total_cost:
            min_total_cost = total_c
            best_result = EOQResult(
                optimal_quantity=round(batched_qty, 2),
                raw_eoq=round(raw_eoq, 2),
                purchasing_cost=round(purch_c, 2),
                ordering_cost=round(order_c, 2),
                holding_cost=round(hold_c, 2),
                total_cost=round(total_c, 2),
                effective_unit_price=round(actual_p, 4),
                applied_discount_rate=actual_tier.discount_percentage,
                applied_tier_min_quantity=actual_tier.min_quantity,
            )

    if best_result is None:
        # Fallback to MOQ
        batched_qty = float(moq)
        purch_c, order_c, hold_c, total_c = calculate_total_inventory_cost(
            quantity=batched_qty,
            annual_demand=annual_demand,
            unit_price=base_unit_price,
            holding_cost_rate=holding_rate,
            order_cost=order_cost,
            safety_stock=safety_stock,
        )
        best_result = EOQResult(
            optimal_quantity=round(batched_qty, 2),
            raw_eoq=round(batched_qty, 2),
            purchasing_cost=round(purch_c, 2),
            ordering_cost=round(order_c, 2),
            holding_cost=round(hold_c, 2),
            total_cost=round(total_c, 2),
            effective_unit_price=round(base_unit_price, 4),
            applied_discount_rate=0.0,
            applied_tier_min_quantity=0,
        )

    return best_result
