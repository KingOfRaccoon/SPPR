"""Stochastic inventory modeling under joint demand and lead-time uncertainty (Wald's identity)."""

from __future__ import annotations

import math

from scipy.stats import norm

# Standard analytical quantiles for cycle service level (CSL)
SERVICE_LEVEL_QUANTILES: dict[float, float] = {
    0.90: 1.2815515655446004,
    0.95: 1.6448536269514722,
    0.98: 2.0537489106318225,
    0.99: 2.3263478740408408,
}


def get_service_level_z(service_level: float) -> float:
    """Retrieve standard normal quantile Z_alpha for the target service level.

    Args:
        service_level: Target cycle service level fraction (e.g. 0.95 for 95%).
    """
    if service_level in SERVICE_LEVEL_QUANTILES:
        return SERVICE_LEVEL_QUANTILES[service_level]
    if math.isclose(service_level, 0.50, abs_tol=1e-5):
        return 0.0
    if not (0.0 < service_level < 1.0):
        raise ValueError(f"Service level must be strictly in (0.0, 1.0), got {service_level}")
    return float(norm.ppf(service_level))


def calculate_lead_time_demand_variance(
    mean_demand: float,
    std_demand: float,
    mean_lead_time: float,
    std_lead_time: float,
) -> float:
    """Calculate compound lead-time demand variance via Wald's Identity.

    Var(D_L) = mu_L * sigma_D^2 + mu_D^2 * sigma_L^2
    """
    mu_d = max(0.0, float(mean_demand))
    sigma_d = max(0.0, float(std_demand))
    mu_l = max(0.0, float(mean_lead_time))
    sigma_l = max(0.0, float(std_lead_time))

    var_demand_term = mu_l * (sigma_d ** 2)
    var_lead_term = (mu_d ** 2) * (sigma_l ** 2)
    return max(0.0, var_demand_term + var_lead_term)


def calculate_safety_stock(
    mean_demand: float,
    std_demand: float,
    mean_lead_time: float,
    std_lead_time: float,
    service_level: float = 0.95,
) -> float:
    """Calculate analytical Safety Stock (SS) protecting against joint uncertainty.

    SS = Z_alpha * sqrt(mu_L * sigma_D^2 + mu_D^2 * sigma_L^2)
    """
    z = get_service_level_z(service_level)
    if z <= 0.0:
        return 0.0

    var_dl = calculate_lead_time_demand_variance(
        mean_demand=mean_demand,
        std_demand=std_demand,
        mean_lead_time=mean_lead_time,
        std_lead_time=std_lead_time,
    )
    if var_dl <= 0.0:
        return 0.0

    std_dl = math.sqrt(var_dl)
    return round(z * std_dl, 2)


def calculate_rop(
    mean_demand: float,
    mean_lead_time: float,
    safety_stock: float,
) -> float:
    """Calculate dynamic Reorder Point (ROP).

    ROP = mu_D * mu_L + SS
    """
    mu_d = max(0.0, float(mean_demand))
    mu_l = max(0.0, float(mean_lead_time))
    ss = max(0.0, float(safety_stock))
    return round(mu_d * mu_l + ss, 2)


def calculate_stochastic_total_cost(
    annual_demand: float,
    order_quantity: float,
    unit_price: float,
    holding_cost_rate: float,
    order_cost: float,
    safety_stock: float,
    stockout_penalty_per_unit: float = 0.0,
    expected_units_short_per_cycle: float = 0.0,
) -> dict[str, float]:
    """Calculate complete Total Cost of Ownership (TCO) breakdown under uncertainty.

    TC = C_purchasing + C_ordering + C_holding + C_stockout
    """
    q = max(1.0, float(order_quantity))
    d = max(0.0, float(annual_demand))
    h = max(1e-6, float(holding_cost_rate * unit_price))
    k = max(0.0, float(order_cost))
    ss = max(0.0, float(safety_stock))

    purchasing_cost = d * unit_price
    ordering_cost = (d / q) * k if d > 0.0 else 0.0
    holding_cost = h * (q / 2.0 + ss)
    stockout_cost = (d / q) * stockout_penalty_per_unit * expected_units_short_per_cycle if d > 0.0 else 0.0
    total_cost = purchasing_cost + ordering_cost + holding_cost + stockout_cost

    return {
        "purchasing_cost": round(purchasing_cost, 2),
        "ordering_cost": round(ordering_cost, 2),
        "holding_cost": round(holding_cost, 2),
        "stockout_cost": round(stockout_cost, 2),
        "total_cost": round(total_cost, 2),
    }
