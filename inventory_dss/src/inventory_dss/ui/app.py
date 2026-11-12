"""Main Streamlit Application Entrypoint for Inventory DSS."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from inventory_dss.ui.components import render_dispatch_bar
from inventory_dss.ui.state import get_state, init_session_state, set_state
from inventory_dss.ui.theme import ThemeMode, inject_custom_css
from inventory_dss.ui.utils import calculate_dss_recommendations, load_synthetic_dataset
from inventory_dss.ui.views.forecasting import render_forecasting_screen
from inventory_dss.ui.views.inventory import render_inventory_screen
from inventory_dss.ui.views.overview import render_overview_screen
from inventory_dss.ui.views.recommendations import render_recommendations_screen
from inventory_dss.ui.views.showcase import render_showcase_screen
from inventory_dss.ui.views.suppliers import render_suppliers_screen


def main() -> None:
    """Streamlit application root runner."""
    # 1. Page Configuration (must be called first)
    st.set_page_config(
        page_title="СППР Управления Запасами",
        page_icon="📦",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # 2. Initialize Session State & Inject DSS Theme CSS
    init_session_state()
    theme_mode_val = get_state("dss_theme_mode", "light")
    theme_mode = ThemeMode.LIGHT if theme_mode_val == "light" else ThemeMode.DARK
    inject_custom_css(theme_mode)

    # 3. Sidebar Navigation & Theme Selector
    st.sidebar.title("📦 СППР Запасы")
    st.sidebar.caption("Система Поддержки Принятия Решений")

    with st.sidebar:
        selected_theme = st.selectbox(
            "Тема интерфейса",
            options=["Светлая (Stripe / Vercel Glass)", "Темная (Zinc Dark)"],
            index=0 if theme_mode == ThemeMode.LIGHT else 1,
            key="dss_theme_select",
        )
        new_mode = "light" if "Светлая" in selected_theme else "dark"
        if new_mode != theme_mode_val:
            set_state("dss_theme_mode", new_mode)
            st.rerun()

    screens = [
        "📊 Обзор и ключевые KPI",
        "📦 Состояние запасов (ABC/XYZ)",
        "📈 Прогнозирование спроса",
        "🏭 Оценка поставщиков",
        "🎯 Рекомендации и What-If",
        "🎨 Дизайн-система (Showcase)",
    ]

    current_nav = get_state("nav_screen", screens[0])
    nav_index = screens.index(current_nav) if current_nav in screens else 0

    selected_screen = st.sidebar.radio(
        "Навигация",
        screens,
        index=nav_index,
        key="nav_screen",
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        """
        **Контур принятия решений:**
        - Товарных позиций: `25 SKU`
        - Поставщиков: `5 контрагентов`
        - Горизонт истории: `730 дней`
        - Склад: `WH-CENTRAL-01`
        """
    )

    # 4. Global Top Dispatch Status Bar (Industrial Neo-Brutalism)
    dataset = load_synthetic_dataset()
    wh = dataset["warehouse"]
    states_df = dataset["state_df"]
    skus_df = dataset["skus_df"]
    merged = pd.merge(states_df, skus_df, on="sku_id")
    vol_util_pct = (merged["on_hand"] * merged["unit_volume_m3"]).sum() / wh.total_volume_capacity_m3 * 100
    wt_util_pct = (merged["on_hand"] * merged["unit_weight_kg"]).sum() / wh.total_weight_capacity_kg * 100
    active_sl = float(get_state("service_level", 0.95))
    recs = calculate_dss_recommendations(
        service_level=active_sl,
        volume_limit=wh.total_volume_capacity_m3,
        weight_limit=wh.total_weight_capacity_kg,
    )
    crit_count = sum(1 for r in recs if r.status == "CRITICAL")
    reorder_count = sum(1 for r in recs if r.status == "REORDER_NEEDED")

    render_dispatch_bar(
        warehouse_id="WH-CENTRAL-01",
        volume_used_pct=vol_util_pct,
        weight_used_pct=wt_util_pct,
        critical_skus=crit_count,
        reorder_skus=reorder_count,
        service_level=active_sl,
    )

    # 5. Screen Routing
    if selected_screen == "📊 Обзор и ключевые KPI":
        render_overview_screen()
    elif selected_screen == "📦 Состояние запасов (ABC/XYZ)":
        render_inventory_screen()
    elif selected_screen == "📈 Прогнозирование спроса":
        render_forecasting_screen()
    elif selected_screen == "🏭 Оценка поставщиков":
        render_suppliers_screen()
    elif selected_screen == "🎯 Рекомендации и What-If":
        render_recommendations_screen()
    elif selected_screen == "🎨 Дизайн-система (Showcase)":
        render_showcase_screen()


if __name__ == "__main__":
    main()
