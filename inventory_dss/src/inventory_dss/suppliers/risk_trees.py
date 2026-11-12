"""Decision Tree Modeling for Supply Disruption and Sourcing Risk Analysis.

Models operational and supply chain risks:
- Lead time delay and delivery disruption probabilities
- Expected Monetary Value (EMV) payoff for Single Sourcing vs. Dual Sourcing
- Breakeven disruption probability threshold analysis
- Classical decision criteria under uncertainty (Wald, Savage, Hurwicz, Laplace)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class SourcingScenario:
    """A distinct environmental state or operational disruption event."""
    name: str
    probability: float
    cost: float  # Total cost in currency (purchasing + penalty + holding)


@dataclass
class SourcingStrategyResult:
    """Outcome metrics for a sourcing decision branch."""
    strategy_name: str
    scenarios: list[SourcingScenario]
    expected_cost: float
    min_cost: float
    max_cost: float
    max_regret: float = 0.0


class SupplyRiskDecisionTree:
    """Decision tree analyzer for evaluating sourcing strategies under disruption risks."""

    def __init__(
        self,
        cost_normal_single: float = 100000.0,
        cost_disrupt_single: float = 250000.0,
        p_disrupt_single: float = 0.08,
        cost_normal_dual: float = 115000.0,
        cost_disrupt_dual: float = 180000.0,
        p_disrupt_dual: float = 0.01,
    ) -> None:
        self.cost_normal_single = cost_normal_single
        self.cost_disrupt_single = cost_disrupt_single
        self.p_disrupt_single = p_disrupt_single

        self.cost_normal_dual = cost_normal_dual
        self.cost_disrupt_dual = cost_disrupt_dual
        self.p_disrupt_dual = p_disrupt_dual

    def evaluate_emv(
        self,
        cost_normal_single: float | None = None,
        cost_disrupt_single: float | None = None,
        p_disrupt_single: float | None = None,
        cost_normal_dual: float | None = None,
        cost_disrupt_dual: float | None = None,
        p_disrupt_dual: float | None = None,
    ) -> dict[str, Any]:
        """Compute Expected Monetary Value (EMV / Expected Cost) for both strategies."""
        c_norm_s = cost_normal_single if cost_normal_single is not None else self.cost_normal_single
        c_dis_s = cost_disrupt_single if cost_disrupt_single is not None else self.cost_disrupt_single
        p_s = p_disrupt_single if p_disrupt_single is not None else self.p_disrupt_single

        c_norm_d = cost_normal_dual if cost_normal_dual is not None else self.cost_normal_dual
        c_dis_d = cost_disrupt_dual if cost_disrupt_dual is not None else self.cost_disrupt_dual
        p_d = p_disrupt_dual if p_disrupt_dual is not None else self.p_disrupt_dual

        emv_single = (1.0 - p_s) * c_norm_s + p_s * c_dis_s
        emv_dual = (1.0 - p_d) * c_norm_d + p_d * c_dis_d

        preferred = "SINGLE_SOURCING" if emv_single < emv_dual else "DUAL_SOURCING"
        cost_difference = abs(emv_dual - emv_single)

        return {
            "emv_single": round(emv_single, 2),
            "emv_dual": round(emv_dual, 2),
            "preferred_strategy": preferred,
            "cost_difference": round(cost_difference, 2),
            "single_breakdown": {
                "normal": {"p": round(1.0 - p_s, 4), "cost": c_norm_s},
                "disrupted": {"p": round(p_s, 4), "cost": c_dis_s},
            },
            "dual_breakdown": {
                "normal": {"p": round(1.0 - p_d, 4), "cost": c_norm_d},
                "disrupted": {"p": round(p_d, 4), "cost": c_dis_d},
            },
        }

    def find_breakeven_probability(
        self,
        cost_normal_single: float | None = None,
        cost_disrupt_single: float | None = None,
        cost_normal_dual: float | None = None,
        cost_disrupt_dual: float | None = None,
        p_disrupt_dual: float | None = None,
    ) -> float:
        """Find the single-sourcing disruption probability p* where EMV(Single) == EMV(Dual).

        EMV_single(p) = (1 - p)*C_norm_s + p*C_dis_s = C_norm_s + p*(C_dis_s - C_norm_s)
        p* = (EMV_dual - C_norm_s) / (C_dis_s - C_norm_s)
        """
        c_norm_s = cost_normal_single if cost_normal_single is not None else self.cost_normal_single
        c_dis_s = cost_disrupt_single if cost_disrupt_single is not None else self.cost_disrupt_single

        c_norm_d = cost_normal_dual if cost_normal_dual is not None else self.cost_normal_dual
        c_dis_d = cost_disrupt_dual if cost_disrupt_dual is not None else self.cost_disrupt_dual
        p_d = p_disrupt_dual if p_disrupt_dual is not None else self.p_disrupt_dual

        emv_dual = (1.0 - p_d) * c_norm_d + p_d * c_dis_d
        delta = c_dis_s - c_norm_s
        if delta <= 0:
            raise ValueError("Disruption cost must exceed normal cost for single sourcing")

        p_star = (emv_dual - c_norm_s) / delta
        return float(np.clip(p_star, 0.0, 1.0))

    def evaluate_uncertainty_criteria(
        self,
        hurwicz_alpha: float = 0.5,
    ) -> dict[str, Any]:
        """Compute decision selection under complete uncertainty (without known probabilities).

        Evaluates:
        - Wald Minimax Cost (Pessimistic / Min of Maximum costs)
        - Optimistic / Min of Minimum costs
        - Savage Minimax Regret (Opportunity loss minimization)
        - Hurwicz criterion (Weighted combination of best and worst outcomes)
        - Laplace criterion (Equal probability assumption)
        """
        # Cost matrix: Strategy x Scenario
        cost_matrix = {
            "Single_Sourcing": {
                "Normal": self.cost_normal_single,
                "Disrupted": self.cost_disrupt_single,
            },
            "Dual_Sourcing": {
                "Normal": self.cost_normal_dual,
                "Disrupted": self.cost_disrupt_dual,
            },
        }

        # 1. Wald criterion (Minimax Cost for cost minimization: min over strategies of max cost)
        max_costs = {strat: max(scens.values()) for strat, scens in cost_matrix.items()}
        wald_choice = min(max_costs, key=max_costs.get)

        # 2. Best case (Minimin: min of min costs)
        min_costs = {strat: min(scens.values()) for strat, scens in cost_matrix.items()}
        optimistic_choice = min(min_costs, key=min_costs.get)

        # 3. Savage Minimax Regret
        # For each scenario, find best (min) cost across all strategies
        scenarios = ["Normal", "Disrupted"]
        min_per_scenario = {
            scen: min(cost_matrix[strat][scen] for strat in cost_matrix)
            for scen in scenarios
        }

        regret_matrix: dict[str, dict[str, float]] = {strat: {} for strat in cost_matrix}
        max_regrets: dict[str, float] = {}
        for strat in cost_matrix:
            for scen in scenarios:
                regret_matrix[strat][scen] = cost_matrix[strat][scen] - min_per_scenario[scen]
            max_regrets[strat] = max(regret_matrix[strat].values())

        savage_choice = min(max_regrets, key=max_regrets.get)

        # 4. Hurwicz Criterion for costs: H = alpha * min_cost + (1 - alpha) * max_cost
        hurwicz_values = {
            strat: hurwicz_alpha * min_costs[strat] + (1.0 - hurwicz_alpha) * max_costs[strat]
            for strat in cost_matrix
        }
        hurwicz_choice = min(hurwicz_values, key=hurwicz_values.get)

        # 5. Laplace Criterion: Equal probability across states
        laplace_values = {
            strat: sum(cost_matrix[strat].values()) / len(scenarios)
            for strat in cost_matrix
        }
        laplace_choice = min(laplace_values, key=laplace_values.get)

        return {
            "cost_matrix": cost_matrix,
            "regret_matrix": regret_matrix,
            "wald": {"scores": max_costs, "preferred": wald_choice},
            "optimistic": {"scores": min_costs, "preferred": optimistic_choice},
            "savage": {"scores": max_regrets, "preferred": savage_choice},
            "hurwicz": {"scores": hurwicz_values, "alpha": hurwicz_alpha, "preferred": hurwicz_choice},
            "laplace": {"scores": laplace_values, "preferred": laplace_choice},
        }
