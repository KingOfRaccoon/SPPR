"""Unit tests for inventory optimization: EOQ, discounts, stochastic SS, ROP, and capacity allocation."""

from __future__ import annotations

import math

import pytest

from inventory_dss.models.domain import (
    SKU,
    DiscountTier,
    ForecastResult,
    OptimizationPlan,
    Supplier,
    Warehouse,
)
from inventory_dss.optimization.capacity import (
    CapacityOptimizer,
    check_warehouse_capacity,
    scale_single_item_to_capacity,
)
from inventory_dss.optimization.engine import InventoryOptimizer
from inventory_dss.optimization.eoq import (
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


class TestClassicalAndDiscountEOQ:
    """Validate Wilson EOQ formula, convexity, quantity discounts, and cost breakdowns."""

    def test_classical_eoq_analytical_formula(self):
        # D = 10,000, K = 50, H = 4.0 -> Q* = sqrt(2 * 10000 * 50 / 4) = sqrt(250000) = 500.0
        eoq = calculate_classical_eoq(annual_demand=10000.0, order_cost=50.0, holding_cost_per_unit=4.0)
        assert math.isclose(eoq, 500.0)

    def test_zero_annual_demand_returns_zero(self):
        assert calculate_classical_eoq(annual_demand=0.0, order_cost=50.0, holding_cost_per_unit=5.0) == 0.0

    def test_convex_cost_curve_global_minimum(self):
        d = 7300.0
        k = 100.0
        h_rate = 0.20
        p = 50.0  # H = 10.0
        q_star = calculate_classical_eoq(d, k, h_rate * p)  # sqrt(2 * 7300 * 100 / 10) = sqrt(146000) ~ 382.099

        _, _, _, cost_star = calculate_total_inventory_cost(q_star, d, p, h_rate, k)
        _, _, _, cost_low = calculate_total_inventory_cost(q_star * 0.5, d, p, h_rate, k)
        _, _, _, cost_high = calculate_total_inventory_cost(q_star * 2.0, d, p, h_rate, k)

        assert cost_star < cost_low
        assert cost_star < cost_high

    def test_eoq_with_all_units_discounts_exploits_price_break(self):
        # Base price 100 RUB. Discount: >= 500 units -> 10% off (90 RUB)
        d = 2000.0
        k = 50.0
        h_rate = 0.20
        tiers = [DiscountTier(min_quantity=500, discount_percentage=0.10)]

        # Unconstrained EOQ at base price: sqrt(2 * 2000 * 50 / 20) = 100 units
        res = calculate_eoq_with_discounts(
            annual_demand=d,
            base_unit_price=100.0,
            holding_rate=h_rate,
            order_cost=k,
            discount_tiers=tiers,
            min_order_quantity=10,
            pack_size=1,
        )

        # Checking if 500 units is selected:
        # Cost at 100 units: 2000*100 + (2000/100)*50 + 20*(50) = 200000 + 1000 + 1000 = 202,000 RUB
        # Cost at 500 units: 2000*90 + (2000/500)*50 + 18*(250) = 180000 + 200 + 4500 = 184,700 RUB
        # Discount tier at 500 units gives substantial savings (184.7k vs 202k)
        assert res.optimal_quantity == 500.0
        assert res.applied_discount_rate == 0.10
        assert res.total_cost < 202000.0

    def test_moq_and_pack_size_batching(self):
        d = 1000.0
        k = 25.0
        p = 50.0
        # raw EOQ = sqrt(2 * 1000 * 25 / 10) = 70.71
        res = calculate_eoq_with_discounts(
            annual_demand=d,
            base_unit_price=p,
            holding_rate=0.20,
            order_cost=k,
            min_order_quantity=100,  # MOQ exceeds raw EOQ
            pack_size=12,            # Must be multiple of 12
        )
        # pack_qty = ceil(70.71 / 12) * 12 = 72; max(pack_qty, moq=100) = 100
        assert res.optimal_quantity == 100.0
        assert res.optimal_quantity >= 100


    def test_cost_breakdown_additivity(self):
        purch, order, hold, total = calculate_total_inventory_cost(
            quantity=200.0,
            annual_demand=5000.0,
            unit_price=40.0,
            holding_cost_rate=0.25,
            order_cost=80.0,
            safety_stock=30.0,
        )
        assert math.isclose(purch + order + hold, total, rel_tol=1e-5)


class TestStochasticSafetyStockAndROP:
    """Validate Wald's identity variance compounding, ROP, and service level sensitivity."""

    def test_walds_variance_joint_uncertainty(self):
        # mu_L = 4.0, sigma_D = 3.0, mu_D = 10.0, sigma_L = 2.0
        # Var(D_L) = 4 * (3^2) + (10^2) * (2^2) = 4 * 9 + 100 * 4 = 36 + 400 = 436.0
        var_dl = calculate_lead_time_demand_variance(
            mean_demand=10.0,
            std_demand=3.0,
            mean_lead_time=4.0,
            std_lead_time=2.0,
        )
        assert math.isclose(var_dl, 436.0)

    def test_safety_stock_monotonicity_in_service_level(self):
        # Higher CSL must strictly increase Safety Stock
        ss_90 = calculate_safety_stock(15.0, 4.0, 7.0, 1.5, service_level=0.90)
        ss_95 = calculate_safety_stock(15.0, 4.0, 7.0, 1.5, service_level=0.95)
        ss_98 = calculate_safety_stock(15.0, 4.0, 7.0, 1.5, service_level=0.98)
        ss_99 = calculate_safety_stock(15.0, 4.0, 7.0, 1.5, service_level=0.99)

        assert ss_90 < ss_95 < ss_98 < ss_99

    def test_lead_time_variance_dominance(self):
        # sigma_L high (5.0), sigma_D low (0.5), mu_D = 20.0, mu_L = 6.0
        var_dl = calculate_lead_time_demand_variance(20.0, 0.5, 6.0, 5.0)
        # Term D: 6 * 0.25 = 1.5; Term L: 400 * 25 = 10000.0
        assert var_dl > 10000.0
        ss = calculate_safety_stock(20.0, 0.5, 6.0, 5.0, service_level=0.95)
        assert ss > 150.0

    def test_demand_variance_dominance(self):
        # sigma_D high (8.0), sigma_L low (0.1), mu_D = 5.0, mu_L = 10.0
        var_dl = calculate_lead_time_demand_variance(5.0, 8.0, 10.0, 0.1)
        # Term D: 10 * 64 = 640; Term L: 25 * 0.01 = 0.25
        assert var_dl > 640.0
        ss = calculate_safety_stock(5.0, 8.0, 10.0, 0.1, service_level=0.95)
        assert ss > 35.0

    def test_deterministic_regime_zero_safety_stock(self):
        # Both variances zero -> SS collapses to 0.0
        ss = calculate_safety_stock(10.0, 0.0, 5.0, 0.0, service_level=0.95)
        assert ss == 0.0

    def test_rop_formula_correctness(self):
        # ROP = mu_D * mu_L + SS
        mu_d = 12.0
        mu_l = 5.0
        ss = 25.5
        rop = calculate_rop(mu_d, mu_l, ss)
        assert math.isclose(rop, 12.0 * 5.0 + 25.5)

    def test_stochastic_total_cost_components(self):
        cost_dict = calculate_stochastic_total_cost(
            annual_demand=3650.0,
            order_quantity=200.0,
            unit_price=100.0,
            holding_cost_rate=0.20,
            order_cost=50.0,
            safety_stock=40.0,
            stockout_penalty_per_unit=20.0,
            expected_units_short_per_cycle=1.5,
        )
        assert cost_dict["purchasing_cost"] == 365000.0
        assert cost_dict["holding_cost"] > 0
        assert cost_dict["stockout_cost"] > 0
        assert cost_dict["total_cost"] == round(
            cost_dict["purchasing_cost"]
            + cost_dict["ordering_cost"]
            + cost_dict["holding_cost"]
            + cost_dict["stockout_cost"],
            2,
        )

    def test_get_service_level_z_quantiles(self):
        assert math.isclose(get_service_level_z(0.95), SERVICE_LEVEL_QUANTILES[0.95])
        assert get_service_level_z(0.50) == 0.0
        with pytest.raises(ValueError):
            get_service_level_z(1.5)


class TestWarehouseCapacityOptimization:
    """Validate warehouse volume and weight bounds, admissibility, and KKT scaling."""

    def test_check_warehouse_capacity_helper(self):
        wh = Warehouse(warehouse_id="WH", total_volume_capacity_m3=100.0, total_weight_capacity_kg=1000.0)
        skus = {
            "S1": SKU(
                sku_id="S1", name="N1", category="Electronics", unit_price=10.0,
                unit_volume_m3=1.0, unit_weight_kg=10.0,
            )
        }
        ok, v, w = check_warehouse_capacity({"S1": 50.0}, skus, wh)
        assert ok
        assert v == 50.0
        assert w == 500.0

    def test_single_item_capacity_scaling(self):
        # Item: unit_vol = 0.5, unit_wt = 50. Max volume = 100, max weight = 4000
        # raw qty = 500 -> Vol cap = 100/0.5 = 200, Wt cap = 4000/50 = 80
        admissible = scale_single_item_to_capacity(
            raw_qty=500.0,
            unit_volume_m3=0.5,
            unit_weight_kg=50.0,
            available_volume_m3=100.0,
            available_weight_kg=4000.0,
        )
        assert admissible == 80.0


    def test_unconstrained_allocation_within_capacity(self):
        wh = Warehouse(
            warehouse_id="WH-TEST",
            total_volume_capacity_m3=1000.0,
            total_weight_capacity_kg=50000.0,
            fixed_order_cost=50.0,
        )
        skus = {
            "SKU-1": SKU(
                sku_id="SKU-1", name="Item 1", category="Electronics",
                unit_price=100.0, unit_volume_m3=0.01, unit_weight_kg=1.0,
            )
        }
        optimizer = CapacityOptimizer(wh)
        res = optimizer.optimize_allocation(
            unconstrained_eoqs={"SKU-1": 100.0},
            skus=skus,
            annual_demands={"SKU-1": 1000.0},
            order_costs={"SKU-1": 50.0},
            holding_costs={"SKU-1": 20.0},
        )
        assert not res.is_constrained
        assert res.allocated_quantities["SKU-1"] == 100.0

    def test_capacity_scaling_when_volume_exceeded(self):
        wh = Warehouse(
            warehouse_id="WH-TIGHT",
            total_volume_capacity_m3=10.0,  # Tight volume limit!
            total_weight_capacity_kg=50000.0,
            fixed_order_cost=50.0,
        )
        skus = {
            "SKU-BULK": SKU(
                sku_id="SKU-BULK", name="Bulk Material", category="Raw Materials",
                unit_price=200.0, unit_volume_m3=0.20, unit_weight_kg=10.0,
            )
        }
        optimizer = CapacityOptimizer(wh)
        # Unconstrained EOQ 200 units would require 200 * 0.20 = 40 m3 > 10 m3
        res = optimizer.optimize_allocation(
            unconstrained_eoqs={"SKU-BULK": 200.0},
            skus=skus,
            annual_demands={"SKU-BULK": 2000.0},
            order_costs={"SKU-BULK": 50.0},
            holding_costs={"SKU-BULK": 40.0},
        )
        assert res.is_constrained
        assert res.total_volume_m3 <= 10.0
        assert res.allocated_quantities["SKU-BULK"] <= 50.0


class TestInventoryOptimizerIntegration:
    """Validate high-level InventoryOptimizer facade integrating all domain models."""

    def test_calculate_policy_standard_pipeline(self):
        optimizer = InventoryOptimizer()
        sku = SKU(
            sku_id="SKU-INT-01",
            name="Int Item",
            category="Spare Parts",
            unit_price=500.0,
            holding_cost_annual_rate=0.20,
            unit_volume_m3=0.02,
            unit_weight_kg=2.5,
            pack_size=4,
        )
        sup = Supplier(
            supplier_id="SUP-INT-01",
            name="Int Sup",
            mean_lead_time_days=6.0,
            std_lead_time_days=1.2,
            on_time_delivery_rate=0.92,
            defect_rate=0.01,
            min_order_quantity=10,
            price_markup_factor=1.05,
        )
        wh = Warehouse(
            warehouse_id="WH-MAIN",
            total_volume_capacity_m3=500.0,
            total_weight_capacity_kg=20000.0,
            fixed_order_cost=40.0,
        )
        fc = ForecastResult(
            sku_id=sku.sku_id,
            forecast_horizon_days=30,
            point_forecast=[8.0] * 30,
            lower_bound_95=[4.0] * 30,
            upper_bound_95=[12.0] * 30,
            mean_daily_demand=8.0,
            std_daily_demand=2.0,
        )

        plan = optimizer.calculate_policy(sku, fc, sup, wh, service_level=0.95)
        assert isinstance(plan, OptimizationPlan)
        assert plan.sku_id == "SKU-INT-01"
        assert plan.eoq >= sup.min_order_quantity
        assert plan.eoq % sku.pack_size == 0
        assert plan.safety_stock > 0.0
        assert plan.reorder_point > plan.safety_stock
        assert plan.expected_total_cost > 0.0

    def test_multi_item_policies_coordination(self):
        optimizer = InventoryOptimizer()
        wh = Warehouse(
            warehouse_id="WH-MULTI",
            total_volume_capacity_m3=100.0,
            total_weight_capacity_kg=5000.0,
            fixed_order_cost=50.0,
        )
        skus = [
            SKU(sku_id="S1", name="N1", category="Electronics", unit_price=100.0, unit_volume_m3=0.05, unit_weight_kg=2.0),
            SKU(sku_id="S2", name="N2", category="Consumables", unit_price=50.0, unit_volume_m3=0.02, unit_weight_kg=1.0),
        ]
        sup = Supplier(
            supplier_id="SUP-1", name="Sup 1", mean_lead_time_days=5.0, std_lead_time_days=1.0,
            on_time_delivery_rate=0.95, defect_rate=0.01, min_order_quantity=5,
        )
        fcs = {
            "S1": ForecastResult(sku_id="S1", forecast_horizon_days=30, point_forecast=[10.0]*30, lower_bound_95=[5.0]*30, upper_bound_95=[15.0]*30, mean_daily_demand=10.0, std_daily_demand=2.0),
            "S2": ForecastResult(sku_id="S2", forecast_horizon_days=30, point_forecast=[20.0]*30, lower_bound_95=[10.0]*30, upper_bound_95=[30.0]*30, mean_daily_demand=20.0, std_daily_demand=3.0),
        }
        sups = {"S1": sup, "S2": sup}

        policies = optimizer.calculate_multi_item_policies(skus, fcs, sups, wh, service_level=0.95)
        assert "S1" in policies
        assert "S2" in policies
        assert policies["S1"].eoq > 0
        assert policies["S2"].eoq > 0
