"""Data loading pipelines, caching, and Plotly visualization builders."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from inventory_dss.config import SYNTHETIC_DATA_DIR
from inventory_dss.data.generator import SyntheticDataGenerator
from inventory_dss.forecasting.model import DemandForecaster
from inventory_dss.models.domain import (
    SKU,
    ForecastResult,
    InventoryState,
    OptimizationPlan,
    Recommendation,
    Supplier,
    Warehouse,
)
from inventory_dss.optimization.engine import InventoryOptimizer
from inventory_dss.recommendations.engine import RecommendationEngine
from inventory_dss.suppliers.evaluator import SupplierEvaluator
from inventory_dss.ui.theme import ThemeMode, get_plotly_template, get_theme


# ---------------------------------------------------------------------------
# Data Loading & Caching Pipeline
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_synthetic_dataset() -> dict[str, Any]:
    """Load or generate synthetic dataset from data/synthetic/."""
    SYNTHETIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    skus_path = SYNTHETIC_DATA_DIR / "skus.csv"
    suppliers_path = SYNTHETIC_DATA_DIR / "suppliers.csv"
    demand_path = SYNTHETIC_DATA_DIR / "demand_history.csv"
    warehouse_path = SYNTHETIC_DATA_DIR / "warehouse.json"
    state_path = SYNTHETIC_DATA_DIR / "inventory_state.csv"

    # If missing, automatically generate
    if not (skus_path.exists() and suppliers_path.exists() and demand_path.exists()):
        gen = SyntheticDataGenerator()
        gen.generate_all(output_dir=SYNTHETIC_DATA_DIR)

    # 1. Load SKUs
    skus_df = pd.read_csv(skus_path)
    skus: list[SKU] = [SKU(**row) for row in skus_df.to_dict(orient="records")]

    # 2. Load Suppliers
    sup_df = pd.read_csv(suppliers_path)
    suppliers: list[Supplier] = [Supplier(**row) for row in sup_df.to_dict(orient="records")]

    # 3. Load Warehouse
    with open(warehouse_path, encoding="utf-8") as f:
        wh_dict = json.load(f)
    warehouse = Warehouse(**wh_dict)

    # 4. Load Demand History
    demand_df = pd.read_csv(demand_path)

    # 5. Load Inventory State
    state_df = pd.read_csv(state_path)
    states: list[InventoryState] = [
        InventoryState(**row) for row in state_df.to_dict(orient="records")
    ]

    return {
        "skus": skus,
        "skus_df": skus_df,
        "suppliers": suppliers,
        "suppliers_df": sup_df,
        "warehouse": warehouse,
        "demand_df": demand_df,
        "states": states,
        "state_df": state_df,
    }


@st.cache_data(show_spinner=False)
def get_all_forecasts(horizon_days: int = 30) -> dict[str, ForecastResult]:
    """Fit forecasting models and return ForecastResult for all SKUs."""
    data = load_synthetic_dataset()
    demand_df = data["demand_df"]
    skus = data["skus"]
    forecaster = DemandForecaster()

    results: dict[str, ForecastResult] = {}
    for s in skus:
        sku_demand = demand_df[demand_df["sku_id"] == s.sku_id]
        if not sku_demand.empty:
            res = forecaster.fit_predict(sku_demand, horizon_days=horizon_days)
            results[s.sku_id] = res
    return results


@st.cache_data(show_spinner=False)
def calculate_dss_recommendations(
    service_level: float,
    volume_limit: float,
    weight_limit: float,
    lead_time_shock: float = 0.0,
) -> list[Recommendation]:
    """Run full recommendation logic under what-if parameters delegating to RecommendationEngine."""
    data = load_synthetic_dataset()
    skus = {s.sku_id: s for s in data["skus"]}
    suppliers = {sup.supplier_id: sup for sup in data["suppliers"]}
    wh = data["warehouse"]
    wh_override = Warehouse(
        warehouse_id=wh.warehouse_id,
        name=wh.name,
        total_volume_capacity_m3=volume_limit,
        total_weight_capacity_kg=weight_limit,
        fixed_order_cost=wh.fixed_order_cost,
        annual_capital_rate=wh.annual_capital_rate,
        target_service_level=service_level,
    )
    states_by_id = {st_item.sku_id: st_item for st_item in data["states"]}
    inventory_states = [
        states_by_id.get(sku_id, InventoryState(sku_id=sku_id, on_hand=0.0, on_order=0.0))
        for sku_id in skus
    ]
    forecasts = get_all_forecasts(horizon_days=30)

    # Multi-criteria supplier ranking (SUP-PREMIUM is primary planned partner, PASSPORT_DSS.md §7.2)
    evaluator = SupplierEvaluator()
    scores = evaluator.evaluate_suppliers(list(suppliers.values()), method="TOPSIS")
    primary_sup_id = "SUP-PREMIUM" if "SUP-PREMIUM" in suppliers else (max(scores, key=scores.get) if scores else "SUP-PREMIUM")
    primary_sup = suppliers[primary_sup_id]

    planned_scores = dict(scores)
    if primary_sup_id in planned_scores:
        planned_scores[primary_sup_id] = max(scores.values()) + 0.05

    # Adjust supplier for lead-time shock
    effective_sup = Supplier(
        supplier_id=primary_sup.supplier_id,
        name=primary_sup.name,
        mean_lead_time_days=primary_sup.mean_lead_time_days + lead_time_shock,
        std_lead_time_days=primary_sup.std_lead_time_days,
        on_time_delivery_rate=primary_sup.on_time_delivery_rate,
        defect_rate=primary_sup.defect_rate,
        min_order_quantity=primary_sup.min_order_quantity,
        price_markup_factor=primary_sup.price_markup_factor,
        order_processing_cost=primary_sup.order_processing_cost,
    )
    effective_suppliers = dict(suppliers)
    effective_suppliers[primary_sup_id] = effective_sup

    optimizer = InventoryOptimizer()
    policies: dict[str, OptimizationPlan] = {}
    for sku_id, sku in skus.items():
        fc = forecasts.get(sku_id)
        if not fc:
            continue
        policies[sku_id] = optimizer.calculate_policy(
            sku=sku,
            demand_forecast=fc,
            supplier=effective_sup,
            warehouse=wh_override,
            service_level=service_level,
        )

    engine = RecommendationEngine()
    return engine.generate_recommendations(
        inventory_states=inventory_states,
        skus=skus,
        forecasts=forecasts,
        policies=policies,
        suppliers=effective_suppliers,
        warehouse=wh_override,
        supplier_scores=planned_scores,
        enforce_capacity=True,
    )


# ---------------------------------------------------------------------------
# Plotly Chart Helpers
# ---------------------------------------------------------------------------
def create_gauge_chart(
    current: float,
    maximum: float,
    title: str,
    unit: str = "m³",
    theme_mode: ThemeMode | str = ThemeMode.DARK,
) -> go.Figure:
    """Create a standardized Plotly indicator gauge with DSS theme tokens."""
    theme = get_theme(theme_mode)
    pct = round((current / maximum) * 100, 1) if maximum > 0 else 0.0
    bar_color = (
        theme.status.optimal.fill
        if pct < 80
        else (theme.status.reorder_needed.fill if pct < 95 else theme.status.critical.fill)
    )
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=current,
            number={"suffix": f" {unit}", "font": {"size": 22, "color": theme.text.primary}},
            title={
                "text": f"<span style='color:{theme.text.primary};font-weight:600'>{title}</span><br><span style='font-size:0.8em;color:{theme.text.secondary}'>Использовано {pct}%</span>"
            },
            delta={"reference": maximum, "increasing": {"color": theme.status.critical.fill}},
            gauge={
                "axis": {"range": [0, maximum], "tickwidth": 1, "tickcolor": theme.borders.default},
                "bar": {"color": bar_color},
                "steps": [
                    {"range": [0, maximum * 0.8], "color": theme.status.optimal.bg},
                    {"range": [maximum * 0.8, maximum * 0.95], "color": theme.status.reorder_needed.bg},
                    {"range": [maximum * 0.95, maximum], "color": theme.status.critical.bg},
                ],
                "threshold": {
                    "line": {"color": theme.status.critical.solid, "width": 4},
                    "thickness": 0.75,
                    "value": maximum,
                },
            },
        )
    )
    fig.update_layout(
        template=get_plotly_template(theme_mode),
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
        height=240,
    )
    return fig
