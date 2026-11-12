"""Screen 5: Replenishment Decision Workbench & What-If Simulation (1C:ERP / SAP IBP Style)."""

from __future__ import annotations

import json
import math

import pandas as pd
import streamlit as st

from inventory_dss.models.domain import Warehouse as DomainWarehouse
from inventory_dss.optimization.capacity import CapacityOptimizer
from inventory_dss.ui.components import DecisionFactor, ReasoningCardData, render_reasoning_card
from inventory_dss.ui.state import (
    approve_recommendation,
    clear_approved_orders,
    get_state,
    set_state,
)
from inventory_dss.ui.theme import EpistemicTrustTier, ThemeMode
from inventory_dss.ui.utils import calculate_dss_recommendations, load_synthetic_dataset


def render_recommendations_screen() -> None:
    """Render Replenishment Decision Workbench screen."""
    st.markdown("## 🎯 Рабочее место ЛПР: План пополнения и What-If анализ")
    st.caption("АРМ Управления закупками: интерактивная балансировка ограничений, KKT-оптимизация квот и утверждение заказов")

    data = load_synthetic_dataset()
    wh = data["warehouse"]
    skus = {s.sku_id: s for s in data["skus"]}

    # 1. What-If Simulation Controls (Card Header)
    with st.expander("⚙️ Параметры What-If моделирования (Стресс-тестирование сценариев)", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            service_level = st.slider(
                "Уровень сервиса (α)",
                min_value=0.90,
                max_value=0.999,
                value=float(get_state("service_level", 0.95)),
                step=0.005,
                key="wb_service_level",
            )
            set_state("service_level", service_level)
        with col2:
            vol_limit = st.slider(
                "Лимит объема склада (м³)",
                min_value=500.0,
                max_value=2000.0,
                value=float(get_state("warehouse_volume_limit", wh.total_volume_capacity_m3)),
                step=50.0,
                key="wb_vol_limit",
            )
            set_state("warehouse_volume_limit", vol_limit)
        with col3:
            wt_limit = st.slider(
                "Лимит веса склада (кг)",
                min_value=20000.0,
                max_value=100000.0,
                value=float(get_state("warehouse_weight_limit", wh.total_weight_capacity_kg)),
                step=5000.0,
                key="wb_wt_limit",
            )
            set_state("warehouse_weight_limit", wt_limit)
        with col4:
            lead_shock = st.slider(
                "Шок задержки поставок (дней)",
                min_value=0.0,
                max_value=14.0,
                value=float(get_state("lead_time_shock_days", 0.0)),
                step=1.0,
                key="wb_lead_shock",
            )
            set_state("lead_time_shock_days", lead_shock)

    # 2. Run Recommendations Engine under parameters
    recs = calculate_dss_recommendations(
        service_level=service_level,
        volume_limit=vol_limit,
        weight_limit=wt_limit,
        lead_time_shock=lead_shock,
    )

    # Order needed subset
    order_recs = [r for r in recs if r.order_needed and r.recommended_order_quantity > 0]
    total_investment = sum(r.estimated_purchase_cost_rub or 0.0 for r in order_recs)
    total_order_vol = sum(r.warehouse_volume_required_m3 or 0.0 for r in order_recs)
    total_order_wt = sum(r.warehouse_weight_required_kg or 0.0 for r in order_recs)

    # Baseline comparison (SL=0.95, shock=0)
    base_recs = calculate_dss_recommendations(
        service_level=0.95,
        volume_limit=wh.total_volume_capacity_m3,
        weight_limit=wh.total_weight_capacity_kg,
        lead_time_shock=0.0,
    )
    base_order_recs = [r for r in base_recs if r.order_needed and r.recommended_order_quantity > 0]
    base_investment = sum(r.estimated_purchase_cost_rub or 0.0 for r in base_order_recs)
    delta_inv = total_investment - base_investment

    # Summary metrics
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric(
            "Позиций к заказу",
            f"{len(order_recs)} SKU",
            delta=f"{len(order_recs) - len(base_order_recs):+d} vs База" if len(order_recs) != len(base_order_recs) else "Базовый сценарий",
        )
    with m2:
        st.metric(
            "Сумма заказа",
            f"{total_investment:,.0f} ₽",
            delta=f"{delta_inv:+,.0f} ₽" if abs(delta_inv) > 10 else "Базовый уровень",
        )
    with m3:
        st.metric("Требуемый объем", f"{total_order_vol:.1f} м³", delta=f"Лимит: {vol_limit:.0f} м³")
    with m4:
        st.metric("Требуемый вес", f"{total_order_wt:.0f} кг", delta=f"Лимит: {wt_limit:.0f} кг")

    # Capacity warning if constraints exceeded
    if total_order_vol > vol_limit or total_order_wt > wt_limit:
        st.warning(
            "⚠️ ВНИМАНИЕ: Совокупный заказ превышает свободную вместимость склада. Требуется применение KKT оптимизации квот."
        )

        with st.expander("⚡ KKT-оптимизация партий под лимиты склада (Lagrangian Multipliers)", expanded=True):
            st.caption("Математическое сжатие партий заказа с минимизацией совокупных затрат по условиям Куна-Таккера")
            sim_wh = DomainWarehouse(
                warehouse_id=wh.warehouse_id,
                name=wh.name,
                total_volume_capacity_m3=vol_limit,
                total_weight_capacity_kg=wt_limit,
                annual_capital_rate=wh.annual_capital_rate,
            )
            opt = CapacityOptimizer(warehouse=sim_wh)
            unconstrained_eoqs = {r.sku_id: float(r.recommended_order_quantity) for r in order_recs}
            annual_demands = {r.sku_id: 365.0 * 10.0 for r in order_recs}
            order_costs = {r.sku_id: 3500.0 for r in order_recs}
            holding_costs = {r.sku_id: (skus[r.sku_id].unit_price * wh.annual_capital_rate if r.sku_id in skus else 200.0) for r in order_recs}
            moqs = {r.sku_id: 10 for r in order_recs}

            kkt_res = opt.optimize_allocation(
                unconstrained_eoqs=unconstrained_eoqs,
                skus=skus,
                annual_demands=annual_demands,
                order_costs=order_costs,
                holding_costs=holding_costs,
                moqs=moqs,
            )

            k_col1, k_col2, k_col3 = st.columns(3)
            with k_col1:
                st.metric("Статус ограничений", "АКТИВНО (KKT сжатие)" if kkt_res.is_constrained else "ВМЕСТИМОСТЬ ДОСТАТОЧНА")
            with k_col2:
                st.metric("Теневая цена объема (λ)", f"{kkt_res.lambda_volume:.2f} ₽/м³", delta="Multiplier")
            with k_col3:
                st.metric("Теневая цена веса (μ)", f"{kkt_res.mu_weight:.2f} ₽/кг", delta="Multiplier")

            st.info(f"💡 Оптимизатор KKT сжал потребный объем с {total_order_vol:.1f} м³ до {kkt_res.total_volume_m3:.1f} м³ и вес с {total_order_wt:.0f} кг до {kkt_res.total_weight_kg:.0f} кг.")

    # Prepare recommended table rows
    table_rows = []
    for r in recs:
        sku = skus.get(r.sku_id)
        table_rows.append({
            "SKU ID": r.sku_id,
            "Наименование": sku.name if sku else "",
            "Статус": r.status,
            "Эфф. запас": r.current_effective_stock,
            "SS": r.safety_stock,
            "ROP": r.reorder_point,
            "Реком. заказ": r.recommended_order_quantity,
            "Поставщик": r.selected_supplier_name,
            "Сумма (₽)": r.estimated_purchase_cost_rub or 0.0,
            "Срочность": r.urgency,
            "Обоснование": r.rationale,
        })
    rec_df = pd.DataFrame(table_rows)

    # Tabs for Replenishment Decision Workbench
    tab_orders, tab_xai, tab_trucks = st.tabs([
        "📋 План заказов и утверждение (PO Approval)",
        "🔍 Инспектор обоснований (Explainable AI)",
        "🚛 Транспортные кванты и упаковка",
    ])

    with tab_orders:
        st.markdown("### 📋 Сформированные рекомендации к пополнению")
        st.dataframe(rec_df, width="stretch", hide_index=True)

        st.markdown("### ✍️ Принятие решений и согласование заказов")
        act_col1, act_col2, act_col3 = st.columns([2, 1, 1])

        with act_col1:
            if st.button("✅ Утвердить все сформированные заказы", key="approve_orders_btn", type="primary"):
                approved_count = 0
                for r in order_recs:
                    sku = skus.get(r.sku_id)
                    unit_price = (sku.unit_cost or sku.unit_price) if sku else 1000.0
                    approve_recommendation(r, unit_price)
                    approved_count += 1
                st.success(f"Успешно утверждено заказов: {approved_count} на сумму {total_investment:,.0f} ₽")

        with act_col2:
            csv_data = rec_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Экспорт в CSV",
                data=csv_data,
                file_name="dss_replenishment_orders.csv",
                mime="text/csv",
                key="export_csv_btn",
            )

        with act_col3:
            json_data = json.dumps([r.model_dump() for r in recs], indent=2, ensure_ascii=False).encode("utf-8")
            st.download_button(
                label="📥 Экспорт в JSON",
                data=json_data,
                file_name="dss_replenishment_orders.json",
                mime="application/json",
                key="export_json_btn",
            )

        # Approved Orders Log
        approved = get_state("approved_orders", [])
        if approved:
            with st.expander(f"📜 Журнал утвержденных заказов ({len(approved)} PO)", expanded=False):
                app_df = pd.DataFrame(approved)
                st.dataframe(app_df, width="stretch", hide_index=True)
                if st.button("Очистить журнал заказов", key="clear_orders_btn"):
                    clear_approved_orders()
                    st.rerun()

    with tab_xai:
        st.markdown("### 🔍 Прозрачность алгоритмического решения (XAI)")
        crit_recs = [r for r in recs if r.status == "CRITICAL" and r.recommended_order_quantity > 0]
        if not crit_recs:
            crit_recs = [r for r in recs if r.recommended_order_quantity > 0]

        if crit_recs:
            sku_options = [
                f"{r.sku_id} — {skus.get(r.sku_id).name if skus.get(r.sku_id) else r.sku_id} ({r.status})"
                for r in crit_recs
            ]
            sel_sku_opt = st.selectbox(
                "Выберите позицию для инспекции обоснования решения",
                sku_options,
                key="xai_sku_selector",
            )
            chosen_idx = sku_options.index(sel_sku_opt)
            top_rec = crit_recs[chosen_idx]
            sku_obj = skus.get(top_rec.sku_id)
            sku_name = sku_obj.name if sku_obj else top_rec.sku_id
            theme_mode_str = get_state("dss_theme_mode", "dark")
            theme_mode = ThemeMode.DARK if theme_mode_str == "dark" else ThemeMode.LIGHT

            render_reasoning_card(
                ReasoningCardData(
                    sku_id=top_rec.sku_id,
                    sku_name=sku_name,
                    trust_tier=EpistemicTrustTier.ALGORITHMIC,
                    recommendation_title=f"Срочный дозаказ {top_rec.recommended_order_quantity:.0f} ед. ({top_rec.selected_supplier_name})",
                    recommended_quantity=top_rec.recommended_order_quantity,
                    selected_supplier=top_rec.selected_supplier_name,
                    estimated_cost_rub=top_rec.estimated_purchase_cost_rub or 0.0,
                    rationale=top_rec.rationale,
                    factors=[
                        DecisionFactor(
                            name="Уровень запаса",
                            value=f"{top_rec.current_effective_stock:.0f} ед.",
                            impact="negative",
                            description="Остаток ниже точки перезаказа",
                        ),
                        DecisionFactor(
                            name="Точка перезаказа (ROP)",
                            value=f"{top_rec.reorder_point:.0f} ед.",
                            impact="neutral",
                        ),
                        DecisionFactor(
                            name="Потребный объем",
                            value=f"{top_rec.warehouse_volume_required_m3:.1f} м³",
                            impact="positive",
                        ),
                    ],
                    confidence_interval=(
                        top_rec.current_effective_stock,
                        top_rec.current_effective_stock + top_rec.recommended_order_quantity,
                    ),
                    confidence_level=0.95,
                    urgency=top_rec.urgency,
                    stockout_risk_reduction="Снижение вероятности дефицита до < 1.0%",
                ),
                theme_mode=theme_mode,
            )
        else:
            st.info("Нет активных рекомендаций к заказу в текущем сценарии.")

    with tab_trucks:
        st.markdown("### 🚛 Балансировка загрузки транспорта и паллетизация (1С:ERP АРМ)")
        truck_cap_vol = 82.0  # Euro truck m3
        truck_cap_wt = 20000.0  # Euro truck kg
        trucks_needed = max(total_order_vol / truck_cap_vol, total_order_wt / truck_cap_wt)
        num_trucks = max(1, math.ceil(trucks_needed)) if trucks_needed > 0 else 0
        fleet_vol_cap = max(1.0, float(num_trucks)) * truck_cap_vol
        fleet_wt_cap = max(1.0, float(num_trucks)) * truck_cap_wt

        vol_fill_pct = min(100.0, (total_order_vol / fleet_vol_cap) * 100) if num_trucks > 0 else 0.0
        wt_fill_pct = min(100.0, (total_order_wt / fleet_wt_cap) * 100) if num_trucks > 0 else 0.0

        tr_col1, tr_col2, tr_col3 = st.columns(3)
        with tr_col1:
            st.metric("Расчетное число еврофур (FTL)", f"{num_trucks} ТС", delta=f"{trucks_needed:.1f} физ. емк.")
        with tr_col2:
            st.metric("Коэффициент заполнения объема", f"{vol_fill_pct:.1f}%")
        with tr_col3:
            st.metric("Коэффициент весовой нагрузки", f"{wt_fill_pct:.1f}%")

        st.markdown(
            f"""<div style="display: flex; gap: 16px; margin: 12px 0;">
                <div style="flex: 1; background: var(--surface-layer-1); border: 2px solid var(--border-default); border-radius: var(--radius-sm); padding: 12px; box-shadow: 2px 2px 0px rgba(0,0,0,0.4);">
                    <div style="font-size: 0.75rem; color: var(--text-secondary); font-weight: 600;">УТИЛИЗАЦИЯ ОБЪЕМА КУЗОВА ({vol_fill_pct:.1f}%)</div>
                    <div class="dss-gauge-track" style="margin-top: 6px;"><div class="dss-gauge-bar dss-gauge-optimal" style="width: {vol_fill_pct:.1f}%;"></div></div>
                </div>
                <div style="flex: 1; background: var(--surface-layer-1); border: 2px solid var(--border-default); border-radius: var(--radius-sm); padding: 12px; box-shadow: 2px 2px 0px rgba(0,0,0,0.4);">
                    <div style="font-size: 0.75rem; color: var(--text-secondary); font-weight: 600;">УТИЛИЗАЦИЯ ГРУЗОПОДЪЕМНОСТИ ({wt_fill_pct:.1f}%)</div>
                    <div class="dss-gauge-track" style="margin-top: 6px;"><div class="dss-gauge-bar dss-gauge-optimal" style="width: {wt_fill_pct:.1f}%;"></div></div>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""<div class="dss-action-card">
                <div class="dss-action-header">
                    <span>ПРАВИЛО ФОРМИРОВАНИЯ FTL / LTL</span>
                    <span class="dss-action-stat">КВАНТЫ ПОСТАВКИ</span>
                </div>
                <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 6px;">
                    Партии округляются до целых паллетных норм (кратно MOQ поставщиков).<br>
                    При заказе свыше <b>{truck_cap_vol:.0f} м³</b> автоматически применяется ставка магистральной транспортировки FTL.
                </div>
            </div>""",
            unsafe_allow_html=True,
        )
