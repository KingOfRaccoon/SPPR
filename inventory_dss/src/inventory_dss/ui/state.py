"""Reactive session state management for Inventory DSS Streamlit dashboard."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import streamlit as st

from inventory_dss.config import (
    DEFAULT_SERVICE_LEVEL,
    DEFAULT_WAREHOUSE_VOLUME_M3,
    DEFAULT_WAREHOUSE_WEIGHT_KG,
)
from inventory_dss.models.domain import PurchaseOrder, Recommendation


def init_session_state() -> None:
    """Initialize default session state keys if not already present."""
    defaults: dict[str, Any] = {
        "nav_screen": "📊 Обзор и ключевые KPI",
        "service_level": float(DEFAULT_SERVICE_LEVEL),
        "warehouse_volume_limit": float(DEFAULT_WAREHOUSE_VOLUME_M3),
        "warehouse_weight_limit": float(DEFAULT_WAREHOUSE_WEIGHT_KG),
        "lead_time_shock_days": 0.0,
        "selected_sku_id": "SKU-ELEC-001",
        "approved_orders": [],  # List of PurchaseOrder dicts
        "supplier_method": "TOPSIS",
        "category_filter": [],
        "status_filter": [],
        "forecast_horizon": 30,
        "confidence_level": 0.95,
    }

    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def get_state(key: str, default: Any = None) -> Any:
    """Retrieve value from Streamlit session state with fallback."""
    return st.session_state.get(key, default)


def set_state(key: str, value: Any) -> None:
    """Assign value to Streamlit session state."""
    st.session_state[key] = value


def approve_recommendation(rec: Recommendation, unit_price: float) -> PurchaseOrder:
    """Create and approve a formalized PurchaseOrder from a Recommendation."""
    today = date.today()
    order_id = f"PO-{today.year}-{uuid.uuid4().hex[:6].upper()}"
    total_cost = round(rec.recommended_order_quantity * unit_price, 2)

    order = PurchaseOrder(
        order_id=order_id,
        sku_id=rec.sku_id,
        supplier_id=rec.selected_supplier_id,
        quantity=rec.recommended_order_quantity,
        unit_price=unit_price,
        total_cost=total_cost,
        order_date=today,
        expected_delivery_date=today,  # will be offset by supplier lead time
        status="APPROVED",
    )

    orders = list(st.session_state.get("approved_orders", []))
    orders.append(order.model_dump())
    st.session_state["approved_orders"] = orders
    return order


def clear_approved_orders() -> None:
    """Reset approved orders history."""
    st.session_state["approved_orders"] = []
