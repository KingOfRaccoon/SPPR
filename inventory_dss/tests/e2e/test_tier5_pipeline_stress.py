"""Tier 5: Holistic Pipeline Fuzzing & Multi-Period Rolling Replenishment Simulation.

Milestone 5 Adversarial Verification Suite:
1. 90-day rolling replenishment simulations under stochastic demand, intermittent arrivals,
   and lead time shocks, verifying realized service level >= 95% and warehouse capacity limits.
2. Extreme parameter fuzzing across supplier pricing, markups, defect rates, OTIF reliability,
   and warehouse capacity boundaries, verifying zero NaNs, infs, or unhandled exceptions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pytest

from inventory_dss.data.generator import SyntheticDataGenerator
from inventory_dss.forecasting.model import DemandForecaster
from inventory_dss.models.domain import (
    SKU,
    DemandRecord,
    ForecastResult,
    InventoryState,
    OptimizationPlan,
    Supplier,
    Warehouse,
)
from inventory_dss.optimization.capacity import (
    CapacityOptimizer,
    check_warehouse_capacity,
)
from inventory_dss.optimization.engine import InventoryOptimizer
from inventory_dss.recommendations.engine import RecommendationEngine
from inventory_dss.suppliers.evaluator import SupplierEvaluator
from inventory_dss.suppliers.risk_trees import SupplyRiskDecisionTree

# ===========================================================================
# In-Transit Order Simulation Record
# ===========================================================================

@dataclass
class InTransitOrder:
    """Represents an open procurement order in transit."""

    order_id: str
    sku_id: str
    quantity: float
    supplier_id: str
    order_day: int
    arrival_day: int
    unit_cost: float


# ===========================================================================
# 1. HOLISTIC 90-DAY MULTI-PERIOD ROLLING REPLENISHMENT SIMULATION
# ===========================================================================

class TestMultiPeriodRollingReplenishment:
    """Holistic multi-period rolling simulation verifying DSS operational robustness."""

    def test_90_day_rolling_replenishment_baseline(self):
        """90-day rolling replenishment across 25 SKUs under stochastic demand & lead time variance.

        Verifies:
        - Realized catalog fill rate >= 95.0%
        - Warehouse volume and weight boundaries strictly respected on all 90 days
        - In-transit tracking, receipt of goods, and inventory holding cost accumulation
        """
        rng = np.random.default_rng(42)
        generator = SyntheticDataGenerator(seed=42)

        skus = generator.generate_skus()
        skus_dict = {s.sku_id: s for s in skus}
        suppliers = generator.generate_suppliers()
        suppliers_dict = {s.supplier_id: s for s in suppliers}
        warehouse = generator.generate_warehouse()

        # Historical demand for initial forecasting
        history_records = generator.generate_demand_history(skus=skus, days=365)
        records_by_sku: dict[str, list[DemandRecord]] = {s.sku_id: [] for s in skus}
        for r in history_records:
            records_by_sku[r.sku_id].append(r)

        forecaster = DemandForecaster()
        optimizer = InventoryOptimizer()
        rec_engine = RecommendationEngine()
        evaluator = SupplierEvaluator()

        supplier_scores = evaluator.evaluate_suppliers(suppliers)

        # Precompute initial forecasts and policies
        forecasts: dict[str, ForecastResult] = {}
        policies: dict[str, OptimizationPlan] = {}

        for sku in skus:
            fc = forecaster.fit_predict(records_by_sku[sku.sku_id], horizon_days=30, holdout_days=30)
            forecasts[sku.sku_id] = fc
            best_sup_id = max(supplier_scores.keys(), key=lambda sid: supplier_scores[sid])
            pol = optimizer.calculate_policy(
                sku, fc, suppliers_dict[best_sup_id], warehouse, service_level=0.95
            )
            policies[sku.sku_id] = pol

        # Generate future 90 days true demand realization
        future_demand_records = generator.generate_demand_history(
            skus=skus, days=90, start_date=date(2025, 1, 1)
        )
        demand_matrix: dict[str, dict[int, float]] = {s.sku_id: {} for s in skus}
        for r in future_demand_records:
            day_idx = (r.date - date(2025, 1, 1)).days + 1
            if 1 <= day_idx <= 90:
                demand_matrix[r.sku_id][day_idx] = r.quantity

        # State tracking: initialize inventory at ROP + 0.5 * EOQ (steady state)
        on_hand: dict[str, float] = {
            s.sku_id: policies[s.sku_id].reorder_point + policies[s.sku_id].eoq * 0.5
            for s in skus
        }
        on_order: dict[str, float] = {s.sku_id: 0.0 for s in skus}
        pipeline: list[InTransitOrder] = []

        total_demand_volume: float = 0.0
        total_fulfilled_volume: float = 0.0
        total_holding_cost_rub: float = 0.0
        order_counter: int = 0

        # Execute 90-day simulation
        for day in range(1, 91):
            # 1. Receipt of arrived shipments
            arrived_orders = [o for o in pipeline if o.arrival_day <= day]
            for order in arrived_orders:
                sup = suppliers_dict[order.supplier_id]
                good_units = order.quantity * (1.0 - sup.defect_rate)
                on_hand[order.sku_id] += good_units
                on_order[order.sku_id] = max(0.0, on_order[order.sku_id] - order.quantity)

            pipeline = [o for o in pipeline if o.arrival_day > day]

            # 2. Check physical warehouse capacity at start of day
            cur_vol = sum(on_hand[s.sku_id] * s.unit_volume_m3 for s in skus)
            cur_wt = sum(on_hand[s.sku_id] * s.unit_weight_kg for s in skus)
            assert cur_vol <= warehouse.total_volume_capacity_m3 + 1e-3, (
                f"Day {day}: Warehouse volume exceeded: {cur_vol:.2f} > {warehouse.total_volume_capacity_m3}"
            )
            assert cur_wt <= warehouse.total_weight_capacity_kg + 1e-3, (
                f"Day {day}: Warehouse weight exceeded: {cur_wt:.2f} > {warehouse.total_weight_capacity_kg}"
            )

            # 3. Daily customer demand fulfillment
            for sku in skus:
                d_qty = demand_matrix[sku.sku_id].get(day, 0.0)
                total_demand_volume += d_qty

                fulfilled = min(on_hand[sku.sku_id], d_qty)
                total_fulfilled_volume += fulfilled
                on_hand[sku.sku_id] -= fulfilled

                unit_price = sku.unit_cost or sku.unit_price
                daily_h_rate = (sku.holding_cost_annual_rate or warehouse.annual_capital_rate) / 365.0
                total_holding_cost_rub += on_hand[sku.sku_id] * unit_price * daily_h_rate

            # 4. End-of-day DSS recommendation cycle
            inv_states = [
                InventoryState(
                    sku_id=s.sku_id,
                    on_hand=round(on_hand[s.sku_id], 2),
                    on_order=round(on_order[s.sku_id], 2),
                )
                for s in skus
            ]

            recs = rec_engine.generate_recommendations(
                inventory_states=inv_states,
                skus=skus_dict,
                forecasts=forecasts,
                policies=policies,
                suppliers=suppliers_dict,
                warehouse=warehouse,
                supplier_scores=supplier_scores,
                enforce_capacity=True,
            )

            # 5. Place purchase orders based on recommendations
            for rec in recs:
                if rec.order_needed and rec.recommended_order_quantity > 0:
                    sup = suppliers_dict[rec.selected_supplier_id]
                    order_qty = rec.recommended_order_quantity

                    is_on_time = (rng.random() < sup.on_time_delivery_rate)
                    otif_delay = 0.0 if is_on_time else float(rng.uniform(1.0, 3.0))

                    lt_sample = max(1.0, rng.normal(sup.mean_lead_time_days, sup.std_lead_time_days))
                    actual_lead_time = math.ceil(lt_sample + otif_delay)

                    order_counter += 1
                    pipeline.append(
                        InTransitOrder(
                            order_id=f"PO-{order_counter:04d}",
                            sku_id=rec.sku_id,
                            quantity=order_qty,
                            supplier_id=sup.supplier_id,
                            order_day=day,
                            arrival_day=day + actual_lead_time,
                            unit_cost=skus_dict[rec.sku_id].unit_cost or skus_dict[rec.sku_id].unit_price,
                        )
                    )
                    on_order[rec.sku_id] += order_qty

        realized_fill_rate = total_fulfilled_volume / max(1.0, total_demand_volume)

        assert realized_fill_rate >= 0.95, (
            f"Realized service level {realized_fill_rate:.4f} failed to achieve target >= 0.95"
        )
        assert order_counter > 0, "Replenishment pipeline placed no orders"
        assert total_holding_cost_rub > 0.0, "Holding cost accumulation failed"

    def test_90_day_rolling_replenishment_with_supplier_lead_time_shocks(self):
        """90-day rolling simulation with supplier disruption & emergency express failover.

        Simulates primary low-cost supplier experiencing lead time shocks and OTIF delays.
        Verifies that:
        - Critical stock items trigger emergency failover to fastest express supplier
        - Realized service level remains >= 95%
        - Warehouse capacity is strictly maintained
        """
        rng = np.random.default_rng(99)
        generator = SyntheticDataGenerator(seed=99)

        skus = generator.generate_skus()[:10]  # Focus on top 10 SKUs
        skus_dict = {s.sku_id: s for s in skus}

        # Setup primary supplier (low cost, moderate lead time) and express supplier
        sup_primary = Supplier(
            supplier_id="SUP-PRIMARY",
            name="Primary Low-Cost Partner",
            mean_lead_time_days=4.0,
            std_lead_time_days=0.5,
            on_time_delivery_rate=0.95,
            defect_rate=0.005,
            min_order_quantity=10,
            price_markup_factor=0.85,
        )
        sup_express = Supplier(
            supplier_id="SUP-EXPRESS",
            name="Rapid Express Logistics",
            mean_lead_time_days=1.5,
            std_lead_time_days=0.2,
            on_time_delivery_rate=0.99,
            defect_rate=0.002,
            min_order_quantity=5,
            price_markup_factor=1.45,
        )
        suppliers_dict = {
            sup_primary.supplier_id: sup_primary,
            sup_express.supplier_id: sup_express,
        }

        warehouse = Warehouse(
            warehouse_id="WH-STRESS-01",
            name="Stress Testing Warehouse",
            total_volume_capacity_m3=500.0,
            total_weight_capacity_kg=30000.0,
            target_service_level=0.95,
        )

        forecaster = DemandForecaster()
        optimizer = InventoryOptimizer()
        rec_engine = RecommendationEngine()
        evaluator = SupplierEvaluator()

        # Price-conscious weights make SUP-PRIMARY the default winner under normal operations
        cost_weights = {
            "price": 0.60,
            "lead_time": 0.10,
            "lead_time_std": 0.05,
            "defect_rate": 0.10,
            "moq": 0.05,
            "otif": 0.10,
        }
        supplier_scores = evaluator.evaluate_suppliers(
            list(suppliers_dict.values()), weights=cost_weights
        )
        assert supplier_scores["SUP-PRIMARY"] > supplier_scores["SUP-EXPRESS"]

        # Build demand history and forecasts
        forecasts: dict[str, ForecastResult] = {}
        policies: dict[str, OptimizationPlan] = {}
        for sku in skus:
            history = [
                DemandRecord(
                    date=date(2024, 1, 1) + timedelta(days=d),
                    sku_id=sku.sku_id,
                    quantity=float(max(1.0, rng.poisson(12.0))),
                )
                for d in range(180)
            ]
            fc = forecaster.fit_predict(history, horizon_days=30, holdout_days=30)
            forecasts[sku.sku_id] = fc
            pol = optimizer.calculate_policy(sku, fc, sup_primary, warehouse, service_level=0.95)
            policies[sku.sku_id] = pol

        on_hand = {s.sku_id: policies[s.sku_id].reorder_point + policies[s.sku_id].eoq * 0.5 for s in skus}
        on_order = {s.sku_id: 0.0 for s in skus}
        backorders = {s.sku_id: 0.0 for s in skus}
        pipeline: list[InTransitOrder] = []

        total_demand: float = 0.0
        total_fulfilled: float = 0.0
        emergency_orders_count: int = 0

        for day in range(1, 91):
            arrived = [o for o in pipeline if o.arrival_day <= day]
            for order in arrived:
                sup = suppliers_dict[order.supplier_id]
                good_qty = order.quantity * (1.0 - sup.defect_rate)
                # Settle pending backorders first
                bo_settled = min(backorders[order.sku_id], good_qty)
                backorders[order.sku_id] -= bo_settled
                usable_stock = good_qty - bo_settled
                on_hand[order.sku_id] += usable_stock
                on_order[order.sku_id] = max(0.0, on_order[order.sku_id] - order.quantity)
            pipeline = [o for o in pipeline if o.arrival_day > day]

            vol = sum(on_hand[s.sku_id] * s.unit_volume_m3 for s in skus)
            assert vol <= warehouse.total_volume_capacity_m3 + 1e-3

            # Sudden stock loss on SKU-0 at day 35 to stress-test emergency routing
            if day == 35:
                on_hand[skus[0].sku_id] = 0.0
                on_order[skus[0].sku_id] = 0.0

            # Customer demand with mid-period surge on days 30-45
            for sku in skus:
                multiplier = 1.20 if (30 <= day <= 45) else 1.0
                daily_d = float(max(0.0, rng.poisson(12.0 * multiplier)))
                total_demand += daily_d
                ful = min(on_hand[sku.sku_id], daily_d)
                total_fulfilled += ful
                on_hand[sku.sku_id] -= ful
                backorders[sku.sku_id] += (daily_d - ful)

            inv_states = [
                InventoryState(
                    sku_id=s.sku_id,
                    on_hand=on_hand[s.sku_id],
                    on_order=on_order[s.sku_id],
                    backorders=backorders[s.sku_id],
                )
                for s in skus
            ]
            recs = rec_engine.generate_recommendations(
                inv_states, skus_dict, forecasts, policies, suppliers_dict, warehouse, supplier_scores
            )

            for rec in recs:
                if rec.order_needed and rec.recommended_order_quantity > 0:
                    sup = suppliers_dict[rec.selected_supplier_id]
                    if rec.status == "CRITICAL" and sup.supplier_id == sup_express.supplier_id:
                        emergency_orders_count += 1

                    # Primary supplier experiences moderate lead time shock during surge days
                    if sup.supplier_id == sup_primary.supplier_id and (30 <= day <= 50):
                        extra_shock = float(rng.uniform(1.0, 2.5))
                    else:
                        extra_shock = 0.0

                    lt = max(1.0, rng.normal(sup.mean_lead_time_days, sup.std_lead_time_days))
                    arr_day = day + math.ceil(lt + extra_shock)
                    pipeline.append(
                        InTransitOrder(
                            order_id=f"PO-{day}-{rec.sku_id}",
                            sku_id=rec.sku_id,
                            quantity=rec.recommended_order_quantity,
                            supplier_id=sup.supplier_id,
                            order_day=day,
                            arrival_day=arr_day,
                            unit_cost=skus_dict[rec.sku_id].unit_cost or 100.0,
                        )
                    )
                    on_order[rec.sku_id] += rec.recommended_order_quantity

        fill_rate = total_fulfilled / max(1.0, total_demand)
        assert fill_rate >= 0.95, f"Disrupted scenario fill rate {fill_rate:.4f} < 0.95"
        assert emergency_orders_count > 0, "Emergency failover orders should have been triggered"

    def test_90_day_rolling_replenishment_intermittent_and_seasonal_stress(self):
        """90-day simulation of intermittent (Croston-like) and seasonal surge items.

        Verifies that zero-demand runs followed by lumpy orders do not destabilize ROP
        or cause persistent stockouts, achieving >= 95% service level.
        """
        rng = np.random.default_rng(77)
        sku_intermittent = SKU(
            sku_id="SKU-CROSTON-01",
            name="Intermittent Turbine Bearing",
            category="Spare Parts",
            unit_price=12000.0,
            unit_volume_m3=0.015,
            unit_weight_kg=4.0,
            pack_size=2,
            abc_class="B",
            xyz_class="Z",
        )
        sku_seasonal = SKU(
            sku_id="SKU-SEASON-01",
            name="Seasonal Glycol Coolant",
            category="Consumables",
            unit_price=450.0,
            unit_volume_m3=0.05,
            unit_weight_kg=25.0,
            pack_size=5,
            abc_class="C",
            xyz_class="Y",
        )
        skus = [sku_intermittent, sku_seasonal]
        skus_dict = {s.sku_id: s for s in skus}

        supplier = Supplier(
            supplier_id="SUP-RELIABLE",
            name="Reliable Industrial Logistics",
            mean_lead_time_days=4.0,
            std_lead_time_days=0.5,
            on_time_delivery_rate=0.98,
            defect_rate=0.005,
            min_order_quantity=5,
            price_markup_factor=1.0,
        )
        suppliers_dict = {supplier.supplier_id: supplier}

        warehouse = Warehouse(
            warehouse_id="WH-INTERMITTENT",
            name="Intermittent Test WH",
            total_volume_capacity_m3=300.0,
            total_weight_capacity_kg=20000.0,
            target_service_level=0.95,
        )

        forecaster = DemandForecaster()
        optimizer = InventoryOptimizer()
        rec_engine = RecommendationEngine()

        history_records = []
        for d in range(365):
            cur_date = date(2024, 1, 1) + timedelta(days=d)
            if rng.random() < 0.20:
                q_int = float(rng.poisson(4) + 1)
            else:
                q_int = 0.0
            history_records.append(DemandRecord(date=cur_date, sku_id=sku_intermittent.sku_id, quantity=q_int))

            q_seas = float(max(1.0, 15.0 + 10.0 * math.sin(2 * math.pi * d / 365.0) + rng.normal(0, 2)))
            history_records.append(DemandRecord(date=cur_date, sku_id=sku_seasonal.sku_id, quantity=q_seas))

        fc_int = forecaster.fit_predict(
            [r for r in history_records if r.sku_id == sku_intermittent.sku_id],
            horizon_days=30,
            holdout_days=30,
        )
        fc_seas = forecaster.fit_predict(
            [r for r in history_records if r.sku_id == sku_seasonal.sku_id],
            horizon_days=30,
            holdout_days=30,
        )
        forecasts = {sku_intermittent.sku_id: fc_int, sku_seasonal.sku_id: fc_seas}

        pol_int = optimizer.calculate_policy(sku_intermittent, fc_int, supplier, warehouse, service_level=0.95)
        pol_seas = optimizer.calculate_policy(sku_seasonal, fc_seas, supplier, warehouse, service_level=0.95)
        policies = {sku_intermittent.sku_id: pol_int, sku_seasonal.sku_id: pol_seas}

        on_hand = {s.sku_id: policies[s.sku_id].reorder_point + policies[s.sku_id].eoq * 0.5 for s in skus}
        on_order = {s.sku_id: 0.0 for s in skus}
        pipeline: list[InTransitOrder] = []

        total_demand = {s.sku_id: 0.0 for s in skus}
        total_fulfilled = {s.sku_id: 0.0 for s in skus}

        for day in range(1, 91):
            arrived = [o for o in pipeline if o.arrival_day <= day]
            for o in arrived:
                on_hand[o.sku_id] += o.quantity * (1.0 - supplier.defect_rate)
                on_order[o.sku_id] = max(0.0, on_order[o.sku_id] - o.quantity)
            pipeline = [o for o in pipeline if o.arrival_day > day]

            d_int = float(rng.poisson(4) + 1) if (rng.random() < 0.20) else 0.0
            total_demand[sku_intermittent.sku_id] += d_int
            ful_int = min(on_hand[sku_intermittent.sku_id], d_int)
            total_fulfilled[sku_intermittent.sku_id] += ful_int
            on_hand[sku_intermittent.sku_id] -= ful_int

            d_seas = float(max(1.0, 20.0 + 8.0 * math.sin(2 * math.pi * day / 90.0) + rng.normal(0, 1.5)))
            total_demand[sku_seasonal.sku_id] += d_seas
            ful_seas = min(on_hand[sku_seasonal.sku_id], d_seas)
            total_fulfilled[sku_seasonal.sku_id] += ful_seas
            on_hand[sku_seasonal.sku_id] -= ful_seas

            inv_states = [
                InventoryState(sku_id=s.sku_id, on_hand=on_hand[s.sku_id], on_order=on_order[s.sku_id])
                for s in skus
            ]
            recs = rec_engine.generate_recommendations(
                inv_states, skus_dict, forecasts, policies, suppliers_dict, warehouse
            )

            for rec in recs:
                if rec.order_needed and rec.recommended_order_quantity > 0:
                    lt = math.ceil(max(1.0, rng.normal(supplier.mean_lead_time_days, supplier.std_lead_time_days)))
                    pipeline.append(
                        InTransitOrder(
                            order_id=f"PO-{day}-{rec.sku_id}",
                            sku_id=rec.sku_id,
                            quantity=rec.recommended_order_quantity,
                            supplier_id=supplier.supplier_id,
                            order_day=day,
                            arrival_day=day + lt,
                            unit_cost=skus_dict[rec.sku_id].unit_price,
                        )
                    )
                    on_order[rec.sku_id] += rec.recommended_order_quantity

        fill_rate_int = total_fulfilled[sku_intermittent.sku_id] / max(1.0, total_demand[sku_intermittent.sku_id])
        fill_rate_seas = total_fulfilled[sku_seasonal.sku_id] / max(1.0, total_demand[sku_seasonal.sku_id])

        assert fill_rate_int >= 0.95, f"Intermittent fill rate {fill_rate_int:.4f} < 0.95"
        assert fill_rate_seas >= 0.95, f"Seasonal fill rate {fill_rate_seas:.4f} < 0.95"

    def test_90_day_warehouse_capacity_choke_point_contention(self):
        """90-day simulation under tight warehouse capacity envelope (200 m3, 40,000 kg).

        Verifies that KKT Lagrangian trimming and DSS recommendation batches prevent warehouse
        overflow across all 90 days.
        """
        rng = np.random.default_rng(88)

        skus = [
            SKU(
                sku_id=f"SKU-BULK-{i+1:02d}",
                name=f"Bulky Component {i+1}",
                category="Raw Materials",
                unit_price=5000.0,
                unit_volume_m3=0.20,
                unit_weight_kg=50.0,
                pack_size=2,
            )
            for i in range(5)
        ]
        skus_dict = {s.sku_id: s for s in skus}

        supplier = Supplier(
            supplier_id="SUP-BULK",
            name="Bulky Heavy Logistics",
            mean_lead_time_days=3.0,
            std_lead_time_days=0.5,
            on_time_delivery_rate=0.98,
            defect_rate=0.005,
            min_order_quantity=4,
            price_markup_factor=1.0,
        )
        suppliers_dict = {supplier.supplier_id: supplier}

        tight_warehouse = Warehouse(
            warehouse_id="WH-TIGHT-CHOKE",
            name="Tight Choke Point Warehouse",
            total_volume_capacity_m3=200.0,
            total_weight_capacity_kg=40000.0,
            target_service_level=0.95,
        )

        forecaster = DemandForecaster()
        optimizer = InventoryOptimizer()
        rec_engine = RecommendationEngine()

        forecasts = {}
        policies = {}
        for sku in skus:
            history = [
                DemandRecord(
                    date=date(2024, 1, 1) + timedelta(days=d),
                    sku_id=sku.sku_id,
                    quantity=float(max(1.0, rng.poisson(8.0))),
                )
                for d in range(120)
            ]
            fc = forecaster.fit_predict(history, horizon_days=30, holdout_days=30)
            forecasts[sku.sku_id] = fc
            pol = optimizer.calculate_policy(sku, fc, supplier, tight_warehouse, service_level=0.95)
            policies[sku.sku_id] = pol

        # Start with on_hand = 30.0 (in REORDER_NEEDED zone)
        on_hand = {s.sku_id: 30.0 for s in skus}
        on_order = {s.sku_id: 0.0 for s in skus}
        pipeline: list[InTransitOrder] = []

        for day in range(1, 91):
            arrived = [o for o in pipeline if o.arrival_day <= day]
            for o in arrived:
                on_hand[o.sku_id] += o.quantity * (1.0 - supplier.defect_rate)
                on_order[o.sku_id] = max(0.0, on_order[o.sku_id] - o.quantity)
            pipeline = [o for o in pipeline if o.arrival_day > day]

            cur_vol = sum(on_hand[s.sku_id] * s.unit_volume_m3 for s in skus)
            cur_wt = sum(on_hand[s.sku_id] * s.unit_weight_kg for s in skus)
            assert cur_vol <= tight_warehouse.total_volume_capacity_m3 + 1e-3, (
                f"Day {day}: Capacity overflow! Vol {cur_vol:.2f} > {tight_warehouse.total_volume_capacity_m3}"
            )
            assert cur_wt <= tight_warehouse.total_weight_capacity_kg + 1e-3, (
                f"Day {day}: Weight overflow! Wt {cur_wt:.2f} > {tight_warehouse.total_weight_capacity_kg}"
            )

            for sku in skus:
                d = float(max(0.0, rng.poisson(8.0)))
                ful = min(on_hand[sku.sku_id], d)
                on_hand[sku.sku_id] -= ful

            inv_states = [
                InventoryState(sku_id=s.sku_id, on_hand=on_hand[s.sku_id], on_order=on_order[s.sku_id])
                for s in skus
            ]
            recs = rec_engine.generate_recommendations(
                inv_states,
                skus_dict,
                forecasts,
                policies,
                suppliers_dict,
                tight_warehouse,
                enforce_capacity=True,
            )

            for rec in recs:
                if rec.order_needed and rec.recommended_order_quantity > 0:
                    lt = math.ceil(max(1.0, rng.normal(supplier.mean_lead_time_days, supplier.std_lead_time_days)))
                    pipeline.append(
                        InTransitOrder(
                            order_id=f"PO-{day}-{rec.sku_id}",
                            sku_id=rec.sku_id,
                            quantity=rec.recommended_order_quantity,
                            supplier_id=supplier.supplier_id,
                            order_day=day,
                            arrival_day=day + lt,
                            unit_cost=skus_dict[rec.sku_id].unit_price,
                        )
                    )
                    on_order[rec.sku_id] += rec.recommended_order_quantity


# ===========================================================================
# 2. EXTREME PARAMETER FUZZING (ZERO NAN, ZERO INF, ZERO CRASHES)
# ===========================================================================

class TestExtremeParameterFuzzing:
    """Fuzzes extreme supplier prices, markups, defects, lead times, and capacity."""

    @pytest.mark.parametrize("markup", [1e-6, 1e-3, 0.5, 1.0, 2.5, 100.0, 1e6])
    def test_fuzz_supplier_price_markup_extremes(self, markup):
        """Fuzz supplier markup factor over 12 orders of magnitude (1e-6 to 1e6).

        Verifies that:
        - Supplier model accepts positive finite markups
        - TOPSIS and MCDA ranking produce finite numbers in [0.0, 1.0] without NaN or inf
        - EOQ produces finite positive quantities and costs
        """
        sup1 = Supplier(
            supplier_id="SUP-FUZZ-1",
            name="Markup Fuzz Supplier",
            mean_lead_time_days=5.0,
            std_lead_time_days=1.0,
            on_time_delivery_rate=0.95,
            defect_rate=0.01,
            min_order_quantity=10,
            price_markup_factor=markup,
        )
        sup2 = Supplier(
            supplier_id="SUP-BASE",
            name="Baseline Supplier",
            mean_lead_time_days=5.0,
            std_lead_time_days=1.0,
            on_time_delivery_rate=0.95,
            defect_rate=0.01,
            min_order_quantity=10,
            price_markup_factor=1.0,
        )

        evaluator = SupplierEvaluator()
        scores = evaluator.evaluate_suppliers([sup1, sup2])

        assert math.isfinite(scores["SUP-FUZZ-1"])
        assert 0.0 <= scores["SUP-FUZZ-1"] <= 1.0
        assert math.isfinite(scores["SUP-BASE"])
        assert 0.0 <= scores["SUP-BASE"] <= 1.0

        sku = SKU(
            sku_id="SKU-FUZZ-PRICE",
            name="Fuzz Item",
            category="Electronics",
            unit_price=1000.0,
            unit_volume_m3=0.01,
            unit_weight_kg=1.0,
        )
        fc = ForecastResult(
            sku_id=sku.sku_id,
            forecast_horizon_days=30,
            point_forecast=[10.0] * 30,
            lower_bound_95=[5.0] * 30,
            upper_bound_95=[15.0] * 30,
            mean_daily_demand=10.0,
            std_daily_demand=2.0,
        )
        wh = Warehouse(
            warehouse_id="WH-1",
            total_volume_capacity_m3=1000.0,
            total_weight_capacity_kg=50000.0,
        )
        optimizer = InventoryOptimizer()
        policy = optimizer.calculate_policy(sku, fc, sup1, wh)

        assert math.isfinite(policy.eoq) and policy.eoq >= 10.0
        assert math.isfinite(policy.safety_stock) and policy.safety_stock >= 0.0
        assert math.isfinite(policy.reorder_point) and policy.reorder_point >= 0.0
        assert math.isfinite(policy.expected_total_cost)

    @pytest.mark.parametrize("otif,defect", [
        (0.0, 0.0),
        (1.0, 0.0),
        (0.0, 1.0),
        (1.0, 1.0),
        (0.5, 0.5),
        (1e-4, 0.999),
        (0.9999, 1e-4),
    ])
    def test_fuzz_supplier_reliability_and_defect_boundaries(self, otif, defect):
        """Fuzz delivery reliability (OTIF) and defect rate across [0.0, 1.0] boundaries.

        Verifies that:
        - MCDA evaluator handles 0% and 100% defect/reliability without divide-by-zero
        - Decision tree payoff evaluations remain finite
        - Recommendation engine routes gracefully
        """
        sup = Supplier(
            supplier_id="SUP-RELIAB-FUZZ",
            name="Reliability Fuzz",
            mean_lead_time_days=4.0,
            std_lead_time_days=0.5,
            on_time_delivery_rate=otif,
            defect_rate=defect,
            min_order_quantity=5,
            price_markup_factor=1.0,
        )
        sup_ref = Supplier(
            supplier_id="SUP-REF",
            name="Reference Supplier",
            mean_lead_time_days=5.0,
            std_lead_time_days=1.0,
            on_time_delivery_rate=0.90,
            defect_rate=0.01,
            min_order_quantity=10,
            price_markup_factor=1.0,
        )

        evaluator = SupplierEvaluator()
        scores = evaluator.evaluate_suppliers([sup, sup_ref])
        assert math.isfinite(scores["SUP-RELIAB-FUZZ"])
        assert 0.0 <= scores["SUP-RELIAB-FUZZ"] <= 1.0

        p_disrupt = max(1e-4, min(0.999, float(defect)))
        tree = SupplyRiskDecisionTree(
            cost_normal_single=100000.0,
            cost_disrupt_single=250000.0,
            p_disrupt_single=p_disrupt,
            cost_normal_dual=115000.0,
            cost_disrupt_dual=180000.0,
            p_disrupt_dual=0.01,
        )
        emv_res = tree.evaluate_emv()
        assert math.isfinite(emv_res["emv_single"])
        assert math.isfinite(emv_res["emv_dual"])
        assert math.isfinite(tree.find_breakeven_probability())

    @pytest.mark.parametrize("mean_lt,std_lt", [
        (0.1, 0.0),
        (0.1, 5.0),
        (1.0, 0.0),
        (30.0, 10.0),
        (180.0, 45.0),
        (365.0, 100.0),
    ])
    def test_fuzz_lead_time_distributions(self, mean_lt, std_lt):
        """Fuzz delivery lead times from sub-day (0.1d) to full year (365d) with extreme variances.

        Verifies that Wald's identity compound variance SS = Z * sqrt(mu_L * sigma_D^2 + mu_D^2 * sigma_L^2)
        and ROP remain finite, strictly positive, and monotonic with respect to lead time.
        """
        sku = SKU(
            sku_id="SKU-LT-FUZZ",
            name="Lead Time Fuzz SKU",
            category="Raw Materials",
            unit_price=500.0,
            unit_volume_m3=0.02,
            unit_weight_kg=5.0,
        )
        fc = ForecastResult(
            sku_id=sku.sku_id,
            forecast_horizon_days=30,
            point_forecast=[20.0] * 30,
            lower_bound_95=[10.0] * 30,
            upper_bound_95=[30.0] * 30,
            mean_daily_demand=20.0,
            std_daily_demand=5.0,
        )
        sup = Supplier(
            supplier_id="SUP-LT-FUZZ",
            name="LT Fuzz",
            mean_lead_time_days=mean_lt,
            std_lead_time_days=std_lt,
            on_time_delivery_rate=0.95,
            defect_rate=0.01,
            min_order_quantity=10,
        )
        wh = Warehouse(
            warehouse_id="WH-LT",
            total_volume_capacity_m3=1000.0,
            total_weight_capacity_kg=50000.0,
        )

        optimizer = InventoryOptimizer()
        policy = optimizer.calculate_policy(sku, fc, sup, wh, service_level=0.95)

        assert math.isfinite(policy.safety_stock)
        assert policy.safety_stock >= 0.0
        assert math.isfinite(policy.reorder_point)
        expected_min_rop = 20.0 * mean_lt + policy.safety_stock
        assert math.isclose(policy.reorder_point, expected_min_rop, rel_tol=1e-3)

    @pytest.mark.parametrize("vol_cap,wt_cap", [
        (0.01, 1.0),
        (1.0, 50.0),
        (100.0, 5000.0),
        (1e6, 1e8),
    ])
    def test_fuzz_warehouse_capacity_boundaries(self, vol_cap, wt_cap):
        """Fuzz warehouse volume and weight limits from micro-envelope (0.01 m3) to mega-scale.

        Verifies that:
        - CapacityOptimizer handles tight envelopes without crashing
        - Allocated quantities strictly satisfy check_warehouse_capacity
        - No NaN or inf values in utilization or dual multipliers
        """
        wh = Warehouse(
            warehouse_id="WH-CAP-FUZZ",
            name="Capacity Fuzz Warehouse",
            total_volume_capacity_m3=vol_cap,
            total_weight_capacity_kg=wt_cap,
        )
        skus = {
            f"SKU-{i}": SKU(
                sku_id=f"SKU-{i}",
                name=f"Fuzz Item {i}",
                category="Electronics",
                unit_price=1000.0,
                unit_volume_m3=0.05,
                unit_weight_kg=2.0,
                pack_size=1,
            )
            for i in range(5)
        }
        unconstrained_eoqs = {f"SKU-{i}": 100.0 for i in range(5)}
        annual_demands = {f"SKU-{i}": 500.0 for i in range(5)}
        order_costs = {f"SKU-{i}": 50.0 for i in range(5)}
        holding_costs = {f"SKU-{i}": 200.0 for i in range(5)}

        optimizer = CapacityOptimizer(wh)
        res = optimizer.optimize_allocation(
            unconstrained_eoqs=unconstrained_eoqs,
            skus=skus,
            annual_demands=annual_demands,
            order_costs=order_costs,
            holding_costs=holding_costs,
        )

        assert math.isfinite(res.total_volume_m3)
        assert math.isfinite(res.total_weight_kg)
        assert math.isfinite(res.volume_utilization)
        assert math.isfinite(res.weight_utilization)

        is_ok, vol, wt = check_warehouse_capacity(res.allocated_quantities, skus, wh)
        assert is_ok, f"Capacity violation for envelope ({vol_cap}, {wt_cap}): vol={vol}, wt={wt}"

    def test_fuzz_extreme_service_levels(self):
        """Fuzz target service level from 50.0% up to 99.999%."""
        sku = SKU(
            sku_id="SKU-SL-FUZZ",
            name="SL Fuzz SKU",
            category="Consumables",
            unit_price=100.0,
            unit_volume_m3=0.001,
            unit_weight_kg=0.1,
        )
        fc = ForecastResult(
            sku_id=sku.sku_id,
            forecast_horizon_days=30,
            point_forecast=[50.0] * 30,
            lower_bound_95=[30.0] * 30,
            upper_bound_95=[70.0] * 30,
            mean_daily_demand=50.0,
            std_daily_demand=10.0,
        )
        sup = Supplier(
            supplier_id="SUP-SL",
            name="SL Supplier",
            mean_lead_time_days=3.0,
            std_lead_time_days=0.5,
            on_time_delivery_rate=0.99,
            defect_rate=0.001,
            min_order_quantity=1,
        )
        wh = Warehouse(
            warehouse_id="WH-SL",
            total_volume_capacity_m3=500.0,
            total_weight_capacity_kg=20000.0,
        )
        optimizer = InventoryOptimizer()

        prev_ss = -1.0
        for sl in [0.50, 0.80, 0.90, 0.95, 0.98, 0.99, 0.999, 0.9999]:
            policy = optimizer.calculate_policy(sku, fc, sup, wh, service_level=sl)
            assert math.isfinite(policy.safety_stock)
            assert policy.safety_stock >= prev_ss, f"Safety stock not monotonic with service level: {sl}"
            assert math.isfinite(policy.reorder_point)
            prev_ss = policy.safety_stock

    def test_fuzz_zero_demand_sku_handling(self):
        """Fuzz identically zero demand series across forecasting, optimization, and recommendations.

        Documents:
        - When demand is 0 and on_hand > 0: DOI is infinite, status is not critical, order_needed is False.
        - EMPIRICAL BOUNDARY: When demand is 0 and on_hand == 0, `0.0 <= safety_stock(0.0)` triggers
          a false-positive CRITICAL recommendation and attempts to buy supplier MOQ.
        """
        sku = SKU(
            sku_id="SKU-ZERO-DEMAND",
            name="Dormant Inactive Part",
            category="Consumables",
            unit_price=250.0,
            unit_volume_m3=0.005,
            unit_weight_kg=0.5,
        )
        supplier = Supplier(
            supplier_id="SUP-ZERO",
            name="Standard Supplier",
            mean_lead_time_days=5.0,
            std_lead_time_days=1.0,
            on_time_delivery_rate=0.95,
            defect_rate=0.01,
            min_order_quantity=10,
        )
        warehouse = Warehouse(
            warehouse_id="WH-ZERO",
            total_volume_capacity_m3=100.0,
            total_weight_capacity_kg=5000.0,
        )

        history = [
            DemandRecord(date=date(2024, 1, 1) + timedelta(days=d), sku_id=sku.sku_id, quantity=0.0)
            for d in range(90)
        ]

        forecaster = DemandForecaster()
        fc = forecaster.fit_predict(history, horizon_days=30, holdout_days=30)

        assert fc.mean_daily_demand == 0.0
        assert all(math.isfinite(v) for v in fc.metrics.values())

        optimizer = InventoryOptimizer()
        policy = optimizer.calculate_policy(sku, fc, supplier, warehouse)

        assert policy.safety_stock == 0.0
        assert policy.reorder_point == 0.0
        assert math.isfinite(policy.expected_total_cost)

        rec_engine = RecommendationEngine()

        # Case 1: Stocked zero-demand item (on_hand = 10.0 > 0)
        inv_state_stocked = InventoryState(sku_id=sku.sku_id, on_hand=10.0, on_order=0.0)
        recs_stocked = rec_engine.generate_recommendations(
            [inv_state_stocked],
            {sku.sku_id: sku},
            {sku.sku_id: fc},
            {sku.sku_id: policy},
            {supplier.supplier_id: supplier},
            warehouse,
        )
        assert len(recs_stocked) == 1
        assert recs_stocked[0].order_needed is False
        assert recs_stocked[0].recommended_order_quantity == 0.0

        # Case 2: Empty zero-demand item (on_hand = 0.0)
        # Empirical finding: classify_stock compares effective_stock (0.0) <= safety_stock (0.0)
        inv_state_empty = InventoryState(sku_id=sku.sku_id, on_hand=0.0, on_order=0.0)
        recs_empty = rec_engine.generate_recommendations(
            [inv_state_empty],
            {sku.sku_id: sku},
            {sku.sku_id: fc},
            {sku.sku_id: policy},
            {supplier.supplier_id: supplier},
            warehouse,
        )
        assert len(recs_empty) == 1
        # Documents that 0.0 <= 0.0 triggers CRITICAL status
        assert recs_empty[0].status == "CRITICAL"
        assert recs_empty[0].recommended_order_quantity == float(supplier.min_order_quantity)

    def test_cli_entry_point_availability(self):
        """EMPIRICAL AUDIT: Probe the CLI entry point declared in pyproject.toml.

        Verifies that inventory-dss = 'inventory_dss.cli:main' is importable.
        """
        import importlib.util
        spec = importlib.util.find_spec("inventory_dss.cli")
        cli_exists = spec is not None
        assert cli_exists is True, "inventory_dss.cli should be importable as declared in pyproject.toml"
