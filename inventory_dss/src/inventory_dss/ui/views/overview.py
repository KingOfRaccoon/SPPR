"""Screen 1: Executive KPI Overview & Operational Action Triage (Netstock / SAP IBP Style)."""

from __future__ import annotations

import html

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from inventory_dss.ui.components import KpiMetricData, render_kpi_grid
from inventory_dss.ui.state import get_state
from inventory_dss.ui.theme import ThemeMode, get_plotly_template, get_theme
from inventory_dss.ui.utils import (
    calculate_dss_recommendations,
    create_gauge_chart,
    load_synthetic_dataset,
)


def render_overview_screen() -> None:
    """Render Executive KPI Overview & Operational Action Triage screen."""
    st.markdown("## 📊 Руководящий обзор и Центр оперативного триажа")
    st.caption("Управление запасами по отклонениям (Management by Exception), Action Lists и складские спидометры")

    data = load_synthetic_dataset()
    skus_df = data["skus_df"]
    states_df = data["state_df"]
    demand_df = data["demand_df"]
    wh = data["warehouse"]

    # Calculate average daily demand per SKU
    daily_demands = demand_df.groupby("sku_id")["quantity"].mean().to_dict()

    # Merge on_hand and pricing
    merged = pd.merge(states_df, skus_df, on="sku_id")
    total_valuation = (merged["on_hand"] * merged["unit_price"]).sum()
    total_volume_util = (merged["on_hand"] * merged["unit_volume_m3"]).sum()
    total_weight_util = (merged["on_hand"] * merged["unit_weight_kg"]).sum()

    # Get current recommendations under active service level
    service_level = float(get_state("service_level", 0.95))
    recs = calculate_dss_recommendations(
        service_level=service_level,
        volume_limit=wh.total_volume_capacity_m3,
        weight_limit=wh.total_weight_capacity_kg,
    )
    critical_count = sum(1 for r in recs if r.status == "CRITICAL")
    reorder_count = sum(1 for r in recs if r.status == "REORDER_NEEDED")
    excess_count = sum(1 for r in recs if r.status == "EXCESS")
    optimal_count = sum(1 for r in recs if r.status == "OPTIMAL")
    holding_cost_annual = total_valuation * wh.annual_capital_rate

    theme_mode_str = get_state("dss_theme_mode", "dark")
    theme_mode = ThemeMode.DARK if theme_mode_str == "dark" else ThemeMode.LIGHT
    theme = get_theme(theme_mode)

    # Top Hero KPI Cockpit Cards (Industrial Neo-Brutalism)
    hero_metrics = [
        KpiMetricData(
            title="Капитал в запасах",
            value=f"{total_valuation / 1e6:.2f}",
            unit="млн ₽",
            delta="Норматив",
            caption=f"Остаток: {merged['on_hand'].sum():,.0f} ед.",
        ),
        KpiMetricData(
            title="Затраты хранения",
            value=f"{holding_cost_annual / 1e6:.2f}",
            unit="млн ₽/год",
            delta=f"{wh.annual_capital_rate * 100:.0f}% ставка",
            caption="TCO склада",
        ),
        KpiMetricData(
            title="Критический дефицит",
            value=critical_count,
            unit="SKU",
            delta=f"{critical_count} стокаутов" if critical_count > 0 else "В норме",
            delta_color="inverse" if critical_count > 0 else "normal",
            caption="Срочный заказ",
        ),
        KpiMetricData(
            title="Объем склада",
            value=f"{total_volume_util:.1f} м³",
            gauge_value=total_volume_util,
            gauge_max=wh.total_volume_capacity_m3,
            gauge_unit="м³",
            gauge_label="Загрузка",
            caption=f"Лимит: {wh.total_volume_capacity_m3:.0f} м³",
        ),
    ]
    render_kpi_grid(hero_metrics, columns=4, theme_mode=theme_mode)
    st.markdown("<div style='margin-bottom: 14px;'></div>", unsafe_allow_html=True)

    # Multi-tab layout: Netstock Action Lists vs Executive Macro KPIs vs Stress-Test
    tab_triage, tab_macro, tab_stress = st.tabs([
        "🚨 Центр оперативного триажа (Netstock Action Lists)",
        "📊 Макро-показатели и складские спидометры",
        "⚡ Стресс-тестирование портфеля (What-If)",
    ])

    # --------------------------------------------------------------------------
    # TAB 1: Netstock-style Action Inbox & Exception Management
    # --------------------------------------------------------------------------
    with tab_triage:
        st.markdown("### ⚡ Очередь критических действий и отклонений")
        st.caption("Принцип Management by Exception: не тратьте время на стабильные позиции — фокус на угрозах дефицита и избытка")

        tc1, tc2, tc3, tc4 = st.columns(4)
        with tc1:
            st.markdown(
                f"""<div class="dss-action-card">
                    <div class="dss-action-header">
                        <span style="color: var(--status-critical-fg); background: var(--status-critical-bg); border: 1px solid var(--status-critical-border); padding: 2px 6px;">[ ДЕФИЦИТ ]</span>
                        <span class="dss-action-stat">DOI &lt; L</span>
                    </div>
                    <div class="dss-action-title">Критический стокаут</div>
                    <div style="font-size: 1.4rem; font-weight: 800; color: var(--status-critical-fg);">{critical_count} SKU</div>
                    <div style="font-size: 0.75rem; color: var(--text-secondary);">Требуют немедленного заказа</div>
                </div>""",
                unsafe_allow_html=True,
            )
        with tc2:
            st.markdown(
                f"""<div class="dss-action-card">
                    <div class="dss-action-header">
                        <span style="color: var(--status-reorder-fg); background: var(--status-reorder-bg); border: 1px solid var(--status-reorder-border); padding: 2px 6px;">[ ПЕРЕЗАКАЗ ]</span>
                        <span class="dss-action-stat">ROP REACHED</span>
                    </div>
                    <div class="dss-action-title">Плановое пополнение</div>
                    <div style="font-size: 1.4rem; font-weight: 800; color: var(--status-reorder-fg);">{reorder_count} SKU</div>
                    <div style="font-size: 0.75rem; color: var(--text-secondary);">В пределах точки заказа</div>
                </div>""",
                unsafe_allow_html=True,
            )
        with tc3:
            st.markdown(
                f"""<div class="dss-action-card">
                    <div class="dss-action-header">
                        <span style="color: var(--status-excess-fg); background: var(--status-excess-bg); border: 1px solid var(--status-excess-border); padding: 2px 6px;">[ ИЗБЫТОК ]</span>
                        <span class="dss-action-stat">DOI &gt; 120 ДН.</span>
                    </div>
                    <div class="dss-action-title">Замороженный капитал</div>
                    <div style="font-size: 1.4rem; font-weight: 800; color: var(--status-excess-fg);">{excess_count} SKU</div>
                    <div style="font-size: 0.75rem; color: var(--text-secondary);">Кандидаты на уценку/акции</div>
                </div>""",
                unsafe_allow_html=True,
            )
        with tc4:
            st.markdown(
                f"""<div class="dss-action-card">
                    <div class="dss-action-header">
                        <span style="color: var(--status-optimal-fg); background: var(--status-optimal-bg); border: 1px solid var(--status-optimal-border); padding: 2px 6px;">[ НОРМА ]</span>
                        <span class="dss-action-stat">IN BALANCE</span>
                    </div>
                    <div class="dss-action-title">Оптимальный уровень</div>
                    <div style="font-size: 1.4rem; font-weight: 800; color: var(--status-optimal-fg);">{optimal_count} SKU</div>
                    <div style="font-size: 0.75rem; color: var(--text-secondary);">Вмешательство не требуется</div>
                </div>""",
                unsafe_allow_html=True,
            )

        st.markdown("#### 🚨 Неотложные сигналы закупщику (Top Action Cards)")
        actionable_recs = [r for r in recs if r.status in ("CRITICAL", "REORDER_NEEDED")]
        actionable_recs.sort(key=lambda x: (0 if x.status == "CRITICAL" else 1, -(x.estimated_purchase_cost_rub or 0.0)))

        sku_meta_map = {row["sku_id"]: row for _, row in skus_df.iterrows()}

        if actionable_recs:
            act_cols = st.columns(min(3, len(actionable_recs)))
            for idx, r in enumerate(actionable_recs[:3]):
                meta = sku_meta_map.get(r.sku_id, {})
                sku_name = meta.get("name", r.sku_id)
                mean_d = daily_demands.get(r.sku_id, 1.0)
                doi = (r.current_effective_stock / mean_d) if mean_d > 0 else 999.0
                urg_badge = "[ CRITICAL STOCKOUT ]" if r.status == "CRITICAL" else "[ REORDER NEEDED ]"
                badge_style = (
                    "color: var(--status-critical-fg); background: var(--status-critical-bg); border: 1.5px solid var(--status-critical-border);"
                    if r.status == "CRITICAL"
                    else "color: var(--status-reorder-fg); background: var(--status-reorder-bg); border: 1.5px solid var(--status-reorder-border);"
                )
                with act_cols[idx % 3]:
                    st.markdown(
                        f"""<div class="dss-action-card">
                            <div class="dss-action-header">
                                <span style="{badge_style} padding: 2px 6px;">{urg_badge}</span>
                                <span class="dss-action-stat">DOI: {doi:.1f} ДН.</span>
                            </div>
                            <div class="dss-action-title">{html.escape(r.sku_id)} — {html.escape(sku_name)}</div>
                            <div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 4px;">
                                Остаток: <b>{r.current_effective_stock:.0f} шт.</b> | ROP: <b>{r.reorder_point:.0f} шт.</b>
                            </div>
                            <div style="font-size: 0.8rem; margin-top: 6px; padding: 6px 8px; background: var(--surface-layer-2); border-left: 3px solid var(--border-default);">
                                Рекомендация: Заказ <b>{r.recommended_order_quantity:.0f} шт.</b> ({r.estimated_purchase_cost_rub or 0.0:,.0f} ₽)<br>
                                Поставщик: <b>{html.escape(r.selected_supplier_name or 'N/A')}</b>
                            </div>
                        </div>""",
                        unsafe_allow_html=True,
                    )
        else:
            st.info("✅ Все запасы в норме. Неотложных заказов не требуется.")

        st.markdown("#### 📋 Сводный реестр оперативного триажа (Priority Action Queue)")
        queue_rows = []
        for r in recs:
            meta = sku_meta_map.get(r.sku_id, {})
            mean_d = daily_demands.get(r.sku_id, 1.0)
            doi = (r.current_effective_stock / mean_d) if mean_d > 0 else 999.0
            queue_rows.append({
                "Артикул": r.sku_id,
                "Наименование": meta.get("name", ""),
                "Категория": meta.get("category", ""),
                "Статус": r.status,
                "Остаток (шт)": round(r.current_effective_stock, 1),
                "DOI (дней)": round(doi, 1),
                "ROP (шт)": round(r.reorder_point, 1),
                "Заказ (шт)": round(r.recommended_order_quantity, 0),
                "Сумма (₽)": round(r.estimated_purchase_cost_rub or 0.0, 0),
                "Поставщик": r.selected_supplier_name or "-",
                "Срочность": r.urgency,
            })
        if queue_rows:
            queue_df = pd.DataFrame(queue_rows)
            # Sort so CRITICAL is first, then REORDER_NEEDED
            status_rank = {"CRITICAL": 0, "REORDER_NEEDED": 1, "EXCESS": 2, "OPTIMAL": 3}
            queue_df["_rank"] = queue_df["Статус"].map(lambda s: status_rank.get(s, 9))
            queue_df = queue_df.sort_values(by=["_rank", "Сумма (₽)"], ascending=[True, False]).drop(columns=["_rank"])
            st.dataframe(queue_df, width="stretch", hide_index=True)
        else:
            st.info("ℹ️ Очередь оперативного триажа пуста. Все товарные позиции находятся в оптимальном состоянии.")

    # --------------------------------------------------------------------------
    # TAB 2: Executive Macro KPIs & Warehouse Capacity Gauges
    # --------------------------------------------------------------------------
    with tab_macro:
        # 1. Macro KPI Cards
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.metric(
                label="Стоимость запасов",
                value=f"{total_valuation / 1e6:.2f} млн ₽",
                delta="Норматив",
            )
        with c2:
            holding_cost_annual = total_valuation * wh.annual_capital_rate
            st.metric(
                label="Затраты хранения (год)",
                value=f"{holding_cost_annual / 1e6:.2f} млн ₽",
                delta=f"{wh.annual_capital_rate * 100:.0f}% ставка капитала",
            )
        with c3:
            st.metric(
                label="Уровень сервиса (α)",
                value=f"{service_level * 100:.1f}%",
                delta="Целевой",
            )
        with c4:
            st.metric(
                label="Дефицит (CRITICAL)",
                value=f"{critical_count} SKU",
                delta="Требуют внимания" if critical_count > 0 else "Нет риска",
                delta_color="inverse" if critical_count > 0 else "normal",
            )
        with c5:
            st.metric(
                label="К заказу (REORDER)",
                value=f"{reorder_count} SKU",
                delta=f"Избыток: {excess_count}",
            )

        st.markdown("---")

        # 2. Capacity Gauges
        st.markdown("### 🏬 Утилизация складских мощностей")
        g1, g2 = st.columns(2)
        with g1:
            fig_vol = create_gauge_chart(
                current=round(total_volume_util, 2),
                maximum=wh.total_volume_capacity_m3,
                title="Объем склада",
                unit="м³",
                theme_mode=theme_mode,
            )
            st.plotly_chart(fig_vol, width="stretch")
        with g2:
            fig_wt = create_gauge_chart(
                current=round(total_weight_util, 1),
                maximum=wh.total_weight_capacity_kg,
                title="Весовая нагрузка стеллажей",
                unit="кг",
                theme_mode=theme_mode,
            )
            st.plotly_chart(fig_wt, width="stretch")

        st.markdown("---")

        # 3. Structure Breakdown
        col_cat, col_cost = st.columns([3, 2])
        with col_cat:
            st.markdown("### 📦 Распределение стоимости по категориям")
            cat_agg = (
                merged.groupby("category", as_index=False)
                .agg(valuation=("on_hand", lambda x: (x * merged.loc[x.index, "unit_price"]).sum()))
            )
            fig_cat = px.bar(
                cat_agg,
                x="category",
                y="valuation",
                color="category",
                color_discrete_sequence=theme.charts.categorical_sequence,
                text_auto=".2s",
                title="Капитал в запасах по товарным группам (₽)",
                labels={"category": "Категория", "valuation": "Стоимость (₽)"},
            )
            fig_cat.update_layout(
                template=get_plotly_template(theme_mode),
                showlegend=False,
                height=320,
                margin={"t": 40, "b": 20, "l": 20, "r": 20},
            )
            st.plotly_chart(fig_cat, width="stretch")

        with col_cost:
            st.markdown("### 💰 Структура совокупных затрат (TCO)")
            costs_data = pd.DataFrame({
                "Компонент": ["Хранение (Holding)", "Заказ (Ordering)", "Риск дефицита (Stockout)"],
                "Сумма": [
                    holding_cost_annual,
                    3500 * (reorder_count + critical_count) * 12,
                    critical_count * 15000,
                ],
            })
            fig_donut = px.pie(
                costs_data,
                names="Компонент",
                values="Сумма",
                hole=0.5,
                title="Доли годовых логистических издержек",
                color_discrete_sequence=[
                    theme.status.optimal.solid,
                    theme.accent.primary,
                    theme.status.critical.solid,
                ],
            )
            fig_donut.update_layout(
                template=get_plotly_template(theme_mode),
                height=320,
                margin={"t": 40, "b": 20, "l": 20, "r": 20},
            )
            st.plotly_chart(fig_donut, width="stretch")

    # --------------------------------------------------------------------------
    # TAB 3: Portfolio Macro Stress-Testing & Shock Resilience
    # --------------------------------------------------------------------------
    with tab_stress:
        st.markdown("### ⚡ Стресс-тестирование портфеля запасов (Macro Stress-Testing)")
        st.caption("Оценка влияния общесистемных макро-шоков спроса и цепочек поставок на оборотный капитал")

        sc1, sc2 = st.columns(2)
        with sc1:
            macro_demand_shock = st.slider(
                "Шок общего роста спроса (+%)",
                min_value=0,
                max_value=50,
                value=15,
                step=5,
                key="ov_macro_demand_shock",
            )
        with sc2:
            macro_lead_shock = st.slider(
                "Общесистемная задержка поставок (дней)",
                min_value=0,
                max_value=14,
                value=3,
                step=1,
                key="ov_macro_lead_shock",
            )

        sim_recs = calculate_dss_recommendations(
            service_level=service_level,
            volume_limit=wh.total_volume_capacity_m3,
            weight_limit=wh.total_weight_capacity_kg,
            lead_time_shock=float(macro_lead_shock),
        )
        demand_factor = 1.0 + (float(macro_demand_shock) / 100.0)
        sim_critical = sum(1 for r in sim_recs if r.status == "CRITICAL")
        sim_investment = sum((r.estimated_purchase_cost_rub or 0.0) * demand_factor for r in sim_recs if r.order_needed)
        base_investment = sum(r.estimated_purchase_cost_rub or 0.0 for r in recs if r.order_needed)
        delta_inv = sim_investment - base_investment

        st_c1, st_c2, st_c3 = st.columns(3)
        with st_c1:
            st.metric(
                label="Прогноз дефицитных позиций",
                value=f"{sim_critical} SKU",
                delta=f"+{sim_critical - critical_count} к текущему" if sim_critical > critical_count else "Без роста",
                delta_color="inverse" if sim_critical > critical_count else "normal",
            )
        with st_c2:
            st.metric(
                label="Потребный бюджет дозакупки",
                value=f"{sim_investment / 1e6:.2f} млн ₽",
                delta=f"+{delta_inv / 1e6:.2f} млн ₽" if delta_inv > 0 else "0 млн ₽",
                delta_color="inverse" if delta_inv > 0 else "normal",
            )
        with st_c3:
            st.metric(
                label="Устойчивость цепи поставок",
                value="КРИТИЧЕСКАЯ" if sim_critical > 8 else ("ВЫСОКАЯ" if sim_critical <= 2 else "УМЕРЕННАЯ"),
                delta="Шок учтен" if macro_lead_shock > 0 else "Базовый режим",
            )

        sl_points = [0.90, 0.92, 0.95, 0.97, 0.99, 0.999]
        inv_points = []
        for sl_val in sl_points:
            temp_recs = calculate_dss_recommendations(
                service_level=sl_val,
                volume_limit=wh.total_volume_capacity_m3,
                weight_limit=wh.total_weight_capacity_kg,
                lead_time_shock=float(macro_lead_shock),
            )
            inv_points.append(sum(r.estimated_purchase_cost_rub or 0.0 for r in temp_recs if r.order_needed) / 1e6)

        fig_curve = go.Figure()
        fig_curve.add_trace(
            go.Scatter(
                x=[p * 100 for p in sl_points],
                y=inv_points,
                mode="lines+markers",
                name="Потребный капитал (млн ₽)",
                line={"color": theme.accent.primary, "width": 3},
                marker={"size": 7, "color": theme.status.critical.solid},
            )
        )
        fig_curve.update_layout(
            template=get_plotly_template(theme_mode),
            title="Кривая компромисса: Капитал в запасах vs Уровень клиентского сервиса (Trade-off Frontier)",
            xaxis_title="Целевой уровень сервиса (%)",
            yaxis_title="Объем заказа (млн ₽)",
            height=320,
            margin={"t": 40, "b": 20, "l": 20, "r": 20},
        )
        st.plotly_chart(fig_curve, width="stretch")
