"""Screen 4: Supplier Multi-Criteria Radar & Decision Tree Payoff (Sourcing Workbench)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from inventory_dss.suppliers.ahp import AHPEngine
from inventory_dss.suppliers.evaluator import SupplierEvaluator
from inventory_dss.suppliers.risk_trees import SupplyRiskDecisionTree
from inventory_dss.ui.state import get_state
from inventory_dss.ui.theme import ThemeMode, get_plotly_template, get_theme
from inventory_dss.ui.utils import load_synthetic_dataset


def render_suppliers_screen() -> None:
    """Render Supplier Multi-Criteria Radar & Sourcing Risk screen."""
    st.markdown("## 🏭 Многокритериальная оценка поставщиков и дерево решений")
    st.caption("АРМ Снабженца: радар надежности, многокритериальный выбор (TOPSIS / AHP) и анализ рисков сбоев (EMV)")

    data = load_synthetic_dataset()
    suppliers = data["suppliers"]

    # Tabs for structured sourcing workflow
    tab_mcda, tab_risk, tab_contracts = st.tabs([
        "🕸️ Радар надежности и рейтинг TOPSIS/AHP",
        "🌳 Дерево решений: Single vs Dual Sourcing",
        "📑 Условия контрактов и аудит надежности",
    ])

    with tab_mcda:
        # 1. Method & Weighting Controls
        c1, _ = st.columns([1, 1])
        with c1:
            method = st.selectbox(
                "Метод многокритериальной оценки",
                [
                    "TOPSIS (AHP веса)",
                    "Shannon Entropy (Объективные веса)",
                    "Hybrid (AHP + Entropy)",
                    "WSM (Линейная свертка)",
                ],
                index=0,
                key="sup_method_select",
            )
            method_code = (
                "TOPSIS"
                if "AHP" in method
                else (
                    "ENTROPY_TOPSIS"
                    if "Entropy" in method
                    else ("HYBRID" if "Hybrid" in method else "WSM")
                )
            )

        with st.expander("⚖️ Экспертная калибровка весов критериев (AHP / МАИ Саати)", expanded=False):
            w_col1, w_col2 = st.columns(2)
            with w_col1:
                pri_price = st.slider("Приоритет: Закупочная цена / наценка", 1, 9, 4, key="ahp_pri_price")
                pri_otif = st.slider("Приоритет: Надежность доставки (OTIF)", 1, 9, 5, key="ahp_pri_otif")
                pri_lead = st.slider("Приоритет: Скорость поставки (Lead Time)", 1, 9, 3, key="ahp_pri_lead")
            with w_col2:
                pri_std = st.slider("Приоритет: Стабильность сроков (Std LT)", 1, 9, 3, key="ahp_pri_std")
                pri_defect = st.slider("Приоритет: Низкий уровень брака", 1, 9, 4, key="ahp_pri_defect")
                pri_moq = st.slider("Приоритет: Минимальный квант (MOQ)", 1, 9, 2, key="ahp_pri_moq")

            # Build pairwise comparison matrix from user priorities
            # Canonical order: [price, lead_time, lead_time_std, defect_rate, moq, otif]
            priorities = np.array([pri_price, pri_lead, pri_std, pri_defect, pri_moq, pri_otif], dtype=float)
            n_crit = len(priorities)
            pw_mat = np.ones((n_crit, n_crit), dtype=float)
            for i in range(n_crit):
                for j in range(n_crit):
                    pw_mat[i, j] = priorities[i] / priorities[j]

            computed_weights, lambda_max, cr = AHPEngine.compute_weights(pw_mat)

            if cr < 0.10:
                st.success(f"✅ Экспертные суждения Саати согласованы: CR = {cr:.3f} < 0.10 (λ_max = {lambda_max:.2f})")
            else:
                st.warning(f"⚠️ Несогласованность суждений: CR = {cr:.3f} >= 0.10. Рекомендуется калибровка.")

        evaluator = SupplierEvaluator()
        criteria_keys = ["price", "lead_time", "lead_time_std", "defect_rate", "moq", "otif"]
        custom_w = dict(zip(criteria_keys, computed_weights)) if "AHP" in method else None
        scores = evaluator.evaluate_suppliers(suppliers, method=method_code, weights=custom_w)

        # 2. Multi-Criteria Radar Chart
        st.markdown("### 🕸️ Радар характеристик поставщиков (Нормированные критерии [0, 1])")
        categories = [
            "OTIF Надежность",
            "Качество (1 - Брак)",
            "Скорость доставки",
            "Стабильность сроков",
            "Ценовая доступность",
            "Доступный MOQ",
        ]

        max_lt = max(s.mean_lead_time_days for s in suppliers)
        max_std = max(s.std_lead_time_days for s in suppliers)
        max_markup = max(s.price_markup_factor for s in suppliers)
        max_moq = max(s.min_order_quantity for s in suppliers)

        fig_radar = go.Figure()
        for s in suppliers:
            # Normalize so that 1.0 is best for all
            r_vals = [
                s.on_time_delivery_rate,
                1.0 - s.defect_rate,
                1.0 - (s.mean_lead_time_days / max_lt),
                1.0 - (s.std_lead_time_days / (max_std or 1.0)),
                1.0 - ((s.price_markup_factor - 0.7) / (max_markup - 0.7)),
                1.0 - (s.min_order_quantity / max_moq),
            ]
            # Close radar loop
            r_vals.append(r_vals[0])
            fig_radar.add_trace(
                go.Scatterpolar(
                    r=r_vals,
                    theta=categories + [categories[0]],
                    fill="toself",
                    name=f"{s.name} ({s.supplier_id})",
                )
            )

        theme_mode_str = get_state("dss_theme_mode", "dark")
        theme_mode = ThemeMode.DARK if theme_mode_str == "dark" else ThemeMode.LIGHT
        theme = get_theme(theme_mode)

        fig_radar.update_layout(
            template=get_plotly_template(theme_mode),
            polar={
                "radialaxis": {
                    "visible": True,
                    "range": [0, 1],
                    "gridcolor": theme.borders.default,
                    "linecolor": theme.borders.default,
                },
                "angularaxis": {
                    "gridcolor": theme.borders.default,
                    "linecolor": theme.borders.default,
                },
            },
            showlegend=True,
            height=450,
            margin={"t": 30, "b": 30, "l": 30, "r": 30},
        )
        st.plotly_chart(fig_radar, width="stretch")

        # 3. Leaderboard
        st.markdown("### 🏅 Итоговый рейтинг поставщиков (Близость к идеалу)")
        sup_records = []
        for s in suppliers:
            score = scores.get(s.supplier_id, 0.0)
            profile_str = (
                s.profile_type.value
                if hasattr(s.profile_type, "value")
                else str(s.profile_type or "STANDARD")
            )
            sup_records.append({
                "Код": s.supplier_id,
                "Поставщик": s.name,
                "Профиль": profile_str,
                "Срок (дней)": f"{s.mean_lead_time_days:.1f} ± {s.std_lead_time_days:.1f}",
                "OTIF (%)": f"{s.on_time_delivery_rate * 100:.1f}%",
                "Брак (%)": f"{s.defect_rate * 100:.2f}%",
                "Наценка": f"{s.price_markup_factor:.2f}x",
                "MOQ": s.min_order_quantity,
                "Балл TOPSIS": round(score, 4),
            })
        sup_df = pd.DataFrame(sup_records).sort_values(by="Балл TOPSIS", ascending=False)
        st.dataframe(sup_df, width="stretch", hide_index=True)

    with tab_risk:
        # 4. Supply Disruption Decision Tree
        st.markdown("### 🌳 Дерево решений: Single Sourcing vs Dual Sourcing")
        st.caption("Оценка ожидаемой монетарной ценности (EMV) при риске сбоев цепочки поставок")

        t1, t2 = st.columns(2)
        with t1:
            p_disrupt = st.slider(
                "Вероятность срыва одиночного поставщика (p_disrupt)",
                0.01,
                0.25,
                0.08,
                0.01,
                key="p_disrupt_slider",
            )
        with t2:
            penalty_cost = st.slider(
                "Убыток при срыве поставок (₽)",
                50000,
                500000,
                250000,
                25000,
                key="penalty_cost_slider",
            )

        tree = SupplyRiskDecisionTree(
            cost_normal_single=100000.0,
            cost_disrupt_single=float(penalty_cost),
            p_disrupt_single=float(p_disrupt),
            cost_normal_dual=115000.0,
            cost_disrupt_dual=float(penalty_cost) * 0.7,
            p_disrupt_dual=0.01,
        )
        tree_res = tree.evaluate_emv()

        c_s, c_d, c_rec = st.columns(3)
        with c_s:
            st.metric("Ожидаемые затраты (Single)", f"{tree_res['emv_single']:,.0f} ₽")
        with c_d:
            st.metric("Ожидаемые затраты (Dual)", f"{tree_res['emv_dual']:,.0f} ₽")
        with c_rec:
            pref = (
                "Одиночный источник (Single)"
                if tree_res["preferred_strategy"] == "SINGLE_SOURCING"
                else "Дуальный источник (Dual)"
            )
            st.metric(
                "Рекомендованная стратегия",
                pref,
                delta=f"Выгода: {tree_res['cost_difference']:,.0f} ₽",
            )

        # Sensitivity Curve for EMV vs p_disrupt
        p_range = [i * 0.01 for i in range(1, 26)]
        emv_single_curve = [
            (1.0 - p) * 100000.0 + p * float(penalty_cost) for p in p_range
        ]
        emv_dual_curve = [
            0.99 * 115000.0 + 0.01 * (float(penalty_cost) * 0.7) for _ in p_range
        ]

        try:
            p_star = tree.find_breakeven_probability()
        except (ValueError, ZeroDivisionError):
            p_star = 0.0

        fig_emv = go.Figure()
        fig_emv.add_trace(
            go.Scatter(
                x=[p * 100 for p in p_range],
                y=emv_single_curve,
                mode="lines",
                name="Single Sourcing EMV",
                line={"color": theme.status.critical.solid, "width": 2.5},
            )
        )
        fig_emv.add_trace(
            go.Scatter(
                x=[p * 100 for p in p_range],
                y=emv_dual_curve,
                mode="lines",
                name="Dual Sourcing EMV",
                line={"color": theme.status.optimal.solid, "width": 2.5, "dash": "dash"},
            )
        )
        if 0.01 <= p_star <= 0.25:
            fig_emv.add_vline(
                x=p_star * 100,
                line_dash="dot",
                line_color=theme.accent.primary,
                annotation_text=f"Точка безразличия p* = {p_star * 100:.1f}%",
            )
        fig_emv.update_layout(
            template=get_plotly_template(theme_mode),
            title="Чувствительность стратегии к риску сбоя (EMV Sensitivity Analysis)",
            xaxis_title="Вероятность сбоя поставщика p_disrupt (%)",
            yaxis_title="Ожидаемые совокупные издержки (₽)",
            height=320,
            margin={"t": 40, "b": 20, "l": 20, "r": 20},
        )
        st.plotly_chart(fig_emv, width="stretch")

        st.markdown("#### 🎲 Анализ решений в условиях полной неопределенности (Non-Probabilistic Criteria)")
        st.caption("Критерии выбора стратегии, когда точные вероятности сбоев неизвестны (Вальд, Сэвидж, Гурвиц, Лаплас)")

        unc_res = tree.evaluate_uncertainty_criteria(hurwicz_alpha=0.5)
        strat_ru = {
            "Single_Sourcing": "Single Sourcing (Один поставщик)",
            "Dual_Sourcing": "Dual Sourcing (Два поставщика)",
        }

        unc_rows = [
            {
                "Критерий": "Вальд (Maximin / Пессимизм)",
                "Логика принятия решений": "Минимизация максимального возможного ущерба в наихудшем сценарии",
                "Выбор СППР": strat_ru.get(unc_res["wald"]["preferred"], unc_res["wald"]["preferred"]),
            },
            {
                "Критерий": "Сэвидж (Minimax Regret)",
                "Логика принятия решений": "Минимизация максимального упущенного выигрыша (сожаления о решении)",
                "Выбор СППР": strat_ru.get(unc_res["savage"]["preferred"], unc_res["savage"]["preferred"]),
            },
            {
                "Критерий": "Гурвиц (Оптимизм-пессимизм, α=0.5)",
                "Логика принятия решений": "Баланс между наилучшим и наихудшим исходом с весом оптимизма",
                "Выбор СППР": strat_ru.get(unc_res["hurwicz"]["preferred"], unc_res["hurwicz"]["preferred"]),
            },
            {
                "Критерий": "Лаплас (Равновероятность)",
                "Логика принятия решений": "Предположение о равной вероятности нормальной работы и срыва",
                "Выбор СППР": strat_ru.get(unc_res["laplace"]["preferred"], unc_res["laplace"]["preferred"]),
            },
        ]
        st.dataframe(pd.DataFrame(unc_rows), width="stretch", hide_index=True)

    with tab_contracts:
        st.markdown("### 📑 Паспорт контрагентов и параметры надежности")
        c_cols = st.columns(len(suppliers))
        for idx, s in enumerate(suppliers):
            with c_cols[idx]:
                st.markdown(
                    f"""<div class="dss-action-card">
                        <div class="dss-action-header">
                            <span style="color: var(--text-primary); font-weight: 800;">{s.supplier_id}</span>
                            <span class="dss-action-stat">OTIF: {s.on_time_delivery_rate * 100:.0f}%</span>
                        </div>
                        <div class="dss-action-title">{s.name}</div>
                        <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">
                            • Срок поставки: <b>{s.mean_lead_time_days:.0f} ± {s.std_lead_time_days:.1f} дн.</b><br>
                            • Дефектность: <b>{s.defect_rate * 100:.2f}%</b><br>
                            • Минимальный квант (MOQ): <b>{s.min_order_quantity} шт.</b><br>
                            • Коэф. цены: <b>{s.price_markup_factor:.2f}x</b>
                        </div>
                    </div>""",
                    unsafe_allow_html=True,
                )
