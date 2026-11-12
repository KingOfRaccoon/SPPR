"""Multi-item warehouse storage capacity optimization with KKT Lagrangian multipliers."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from inventory_dss.models.domain import SKU, Warehouse


@dataclass(frozen=True)
class CapacityOptimizationResult:
    """Outcome of multi-item warehouse capacity constrained optimization."""

    allocated_quantities: dict[str, float]
    total_volume_m3: float
    total_weight_kg: float
    volume_utilization: float
    weight_utilization: float
    is_constrained: bool
    lambda_volume: float
    mu_weight: float


def check_warehouse_capacity(
    quantities: dict[str, float],
    skus: dict[str, SKU],
    warehouse: Warehouse,
) -> tuple[bool, float, float]:
    """Check if proposed quantities satisfy warehouse volume and weight limits.

    Returns:
        (is_admissible, total_volume_m3, total_weight_kg)
    """
    total_vol = 0.0
    total_wt = 0.0
    for sku_id, qty in quantities.items():
        if sku_id in skus and qty > 0:
            sku = skus[sku_id]
            total_vol += qty * sku.unit_volume_m3
            total_wt += qty * sku.unit_weight_kg

    v_max = warehouse.total_volume_capacity_m3
    w_max = warehouse.total_weight_capacity_kg
    is_admissible = (total_vol <= v_max + 1e-4) and (total_wt <= w_max + 1e-4)
    return is_admissible, round(total_vol, 4), round(total_wt, 2)


def scale_single_item_to_capacity(
    raw_qty: float,
    unit_volume_m3: float,
    unit_weight_kg: float,
    available_volume_m3: float,
    available_weight_kg: float,
) -> float:
    """Scale a single order down to admissible warehouse capacity limits."""
    max_by_vol = (
        available_volume_m3 / unit_volume_m3
        if unit_volume_m3 > 0.0
        else raw_qty
    )
    max_by_wt = (
        available_weight_kg / unit_weight_kg
        if unit_weight_kg > 0.0
        else raw_qty
    )
    admissible = min(raw_qty, max_by_vol, max_by_wt)
    return max(0.0, admissible)


class CapacityOptimizer:
    """Solves multi-item inventory order allocation under warehouse storage limits.

    Formulation:
        min sum( D_i * K_i / Q_i + H_i * Q_i / 2 )
        s.t.
            sum( Q_i * v_i ) <= V_max    (multiplier lambda >= 0)
            sum( Q_i * w_i ) <= W_max    (multiplier mu >= 0)
            Q_i >= MOQ_i
    """

    def __init__(self, warehouse: Warehouse) -> None:
        self.warehouse = warehouse

    def optimize_allocation(
        self,
        unconstrained_eoqs: dict[str, float],
        skus: dict[str, SKU],
        annual_demands: dict[str, float],
        order_costs: dict[str, float],
        holding_costs: dict[str, float],
        moqs: dict[str, int] | None = None,
    ) -> CapacityOptimizationResult:
        """Find optimal order quantities Q* respecting warehouse envelope."""
        sku_ids = [sid for sid in unconstrained_eoqs if sid in skus]
        if not sku_ids:
            return CapacityOptimizationResult(
                allocated_quantities={},
                total_volume_m3=0.0,
                total_weight_kg=0.0,
                volume_utilization=0.0,
                weight_utilization=0.0,
                is_constrained=False,
                lambda_volume=0.0,
                mu_weight=0.0,
            )

        v_max = self.warehouse.total_volume_capacity_m3
        w_max = self.warehouse.total_weight_capacity_kg

        # Check if unconstrained EOQ already satisfies capacity
        is_ok, tot_v, tot_w = check_warehouse_capacity(unconstrained_eoqs, skus, self.warehouse)
        if is_ok:
            return CapacityOptimizationResult(
                allocated_quantities={sid: round(unconstrained_eoqs[sid], 2) for sid in sku_ids},
                total_volume_m3=tot_v,
                total_weight_kg=tot_w,
                volume_utilization=round(tot_v / v_max, 4),
                weight_utilization=round(tot_w / w_max, 4),
                is_constrained=False,
                lambda_volume=0.0,
                mu_weight=0.0,
            )

        # Capacity violated: Solve constrained non-linear program
        n = len(sku_ids)
        d_vec = np.array([max(1.0, annual_demands.get(sid, 100.0)) for sid in sku_ids])
        k_vec = np.array([max(1.0, order_costs.get(sid, self.warehouse.fixed_order_cost)) for sid in sku_ids])
        h_vec = np.array([max(1e-4, holding_costs.get(sid, 10.0)) for sid in sku_ids])
        v_vec = np.array([skus[sid].unit_volume_m3 for sid in sku_ids])
        w_vec = np.array([skus[sid].unit_weight_kg for sid in sku_ids])
        moq_vec = np.array([moqs.get(sid, 1) if moqs else 1 for sid in sku_ids], dtype=float)

        def objective(q: np.ndarray) -> float:
            return float(np.sum((d_vec * k_vec) / q + 0.5 * h_vec * q))

        def grad_objective(q: np.ndarray) -> np.ndarray:
            return -(d_vec * k_vec) / (q ** 2) + 0.5 * h_vec

        constraints = [
            {"type": "ineq", "fun": lambda q: v_max - np.sum(q * v_vec), "jac": lambda q: -v_vec},
            {"type": "ineq", "fun": lambda q: w_max - np.sum(q * w_vec), "jac": lambda q: -w_vec},
        ]

        bounds = [(max(1.0, float(moq_vec[i])), None) for i in range(n)]

        # Initial scaled guess
        q0_raw = np.array([unconstrained_eoqs[sid] for sid in sku_ids])
        scale_v = v_max / max(1e-6, np.sum(q0_raw * v_vec))
        scale_w = w_max / max(1e-6, np.sum(q0_raw * w_vec))
        scale = min(scale_v, scale_w, 1.0)
        q0 = np.maximum(moq_vec, q0_raw * scale)

        opt_res = minimize(
            objective,
            q0,
            jac=grad_objective,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 100, "ftol": 1e-5},
        )

        q_opt = opt_res.x if opt_res.success else q0

        # Extract Lagrange multipliers if available
        # Modern SciPy (1.14+) exposes SLSQP multipliers in opt_res.multipliers (ndarray),
        # whereas legacy versions or alternative bindings may use opt_res.v or dict keys.
        lambda_v = 0.0
        mu_w = 0.0
        mults = getattr(opt_res, "multipliers", None)
        if mults is None:
            mults = getattr(opt_res, "v", None)
        if mults is None and isinstance(opt_res, dict):
            mults = opt_res.get("multipliers")
            if mults is None:
                mults = opt_res.get("v")

        if mults is not None and len(mults) >= 2:
            try:
                v0 = float(mults[0])
                v1 = float(mults[1])
                lambda_v = max(0.0, v0) if math.isfinite(v0) else 0.0
                mu_w = max(0.0, v1) if math.isfinite(v1) else 0.0
            except (ValueError, TypeError, IndexError):
                pass
        elif mults is not None and len(mults) == 1:
            try:
                v0 = float(mults[0])
                lambda_v = max(0.0, v0) if math.isfinite(v0) else 0.0
            except (ValueError, TypeError, IndexError):
                pass

        allocated: dict[str, float] = {}
        pack_sizes: dict[str, int] = {}
        min_quantities: dict[str, float] = {}
        floor_quantities: dict[str, float] = {}

        for i, sid in enumerate(sku_ids):
            pack = max(1, skus[sid].pack_size)
            moq = max(1, moqs.get(sid, 1) if moqs else 1)
            min_q = max(float(pack), float(math.ceil(moq / pack) * pack))
            q_raw = float(q_opt[i])
            ceil_q = max(min_q, float(math.ceil(q_raw / pack) * pack))
            floor_q = max(min_q, float(math.floor(q_raw / pack) * pack))

            allocated[sid] = ceil_q
            pack_sizes[sid] = pack
            min_quantities[sid] = min_q
            floor_quantities[sid] = floor_q

        def current_vol_wt() -> tuple[float, float]:
            vol = sum(allocated[s] * skus[s].unit_volume_m3 for s in sku_ids)
            wt = sum(allocated[s] * skus[s].unit_weight_kg for s in sku_ids)
            return vol, wt

        def tc_item(sid: str, q: float) -> float:
            d = max(1.0, annual_demands.get(sid, 100.0))
            k = max(1.0, order_costs.get(sid, self.warehouse.fixed_order_cost))
            h = max(1e-4, holding_costs.get(sid, 10.0))
            return (d * k) / q + 0.5 * h * q

        eps = 1e-4
        vol, wt = current_vol_wt()

        # Phase 1: Greedily reduce items from ceil down to floor
        # Phase 2: If still overflowing, reduce further down to min_q (MOQ)
        for phase in (1, 2):
            while (vol > v_max + eps) or (wt > w_max + eps):
                candidates = []
                vol_viol = max(0.0, vol - v_max)
                wt_viol = max(0.0, wt - w_max)

                for sid in sku_ids:
                    pack = pack_sizes[sid]
                    lower_bound = floor_quantities[sid] if phase == 1 else min_quantities[sid]
                    if allocated[sid] - pack < lower_bound:
                        continue

                    delta_v = pack * skus[sid].unit_volume_m3
                    delta_w = pack * skus[sid].unit_weight_kg

                    relief = 0.0
                    if vol_viol > eps and v_max > 0:
                        relief += (vol_viol / v_max) * (delta_v / v_max)
                    if wt_viol > eps and w_max > 0:
                        relief += (wt_viol / w_max) * (delta_w / w_max)

                    if relief <= 0.0:
                        continue

                    cur_q = allocated[sid]
                    next_q = cur_q - pack
                    delta_tc = tc_item(sid, next_q) - tc_item(sid, cur_q)

                    # Minimize cost increase per unit of relief
                    score = (delta_tc / relief) if delta_tc > 0 else (-1e9 + delta_tc)
                    candidates.append((score, sid))

                if not candidates:
                    break

                candidates.sort(key=lambda x: x[0])
                best_sid = candidates[0][1]
                allocated[best_sid] -= pack_sizes[best_sid]
                vol, wt = current_vol_wt()

        # Emergency fallback if warehouse envelope physically cannot fit MOQ
        if (vol > v_max + eps) or (wt > w_max + eps):
            scale_emergency = min(
                (v_max / vol) if (v_max > 0 and vol > v_max) else 1.0,
                (w_max / wt) if (w_max > 0 and wt > w_max) else 1.0,
            )
            for sid in sku_ids:
                pack = pack_sizes[sid]
                raw_scaled = allocated[sid] * scale_emergency
                allocated[sid] = max(0.0, float(math.floor(raw_scaled / pack) * pack))

        tot_v_final = float(np.sum([allocated[sid] * skus[sid].unit_volume_m3 for sid in sku_ids]))
        tot_w_final = float(np.sum([allocated[sid] * skus[sid].unit_weight_kg for sid in sku_ids]))

        return CapacityOptimizationResult(
            allocated_quantities={sid: round(allocated[sid], 2) for sid in sku_ids},
            total_volume_m3=round(tot_v_final, 4),
            total_weight_kg=round(tot_w_final, 2),
            volume_utilization=round(tot_v_final / v_max, 4),
            weight_utilization=round(tot_w_final / w_max, 4),
            is_constrained=True,
            lambda_volume=round(lambda_v, 6),
            mu_weight=round(mu_w, 6),
        )
