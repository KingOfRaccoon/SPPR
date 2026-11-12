"""Screen 2: Inventory Health & Interactive ABC/XYZ Matrix (Specialist Workbench)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from inventory_dss.ui.components import MatrixCellData, render_matrix_grid
from inventory_dss.ui.state import get_state
from inventory_dss.ui.theme import ThemeMode, get_plotly_template, get_theme
from inventory_dss.ui.utils import load_synthetic_dataset


def render_inventory_screen() -> None:
    """Render Inventory Health & ABC/XYZ Matrix screen."""
    st.markdown("## 📦 Состояние запасов и матрица ABC/XYZ")
    st.caption("АРМ Аналитика запасов: 9-секторная сегментация номенклатуры, вариативность спроса и дифференцированные политики")

    data = load_synthetic_dataset()
    skus_df = data["skus_df"]
    states_df = data["state_df"]
    demand_df = data["demand_df"]

    # Compute CV for each SKU from demand
    cv_records = []
    for sku_id, group in demand_df.groupby("sku_id"):
        mean_d = float(group["quantity"].mean())
        std_d = float(group["quantity"].std())
        cv = (std_d / mean_d) if mean_d > 0 else 0.0
        cv_records.append({"sku_id": sku_id, "mean_demand": mean_d, "demand_cv": round(cv, 3)})
    cv_df = pd.DataFrame(cv_records)

    # Merge full picture
    merged = pd.merge(skus_df, states_df, on="sku_id")
    merged = pd.merge(merged, cv_df, on="sku_id")
    merged["valuation"] = merged["on_hand"] * merged["unit_price"]

    # Calculate cumulative revenue share for Y-axis
    merged = merged.sort_values(by="valuation", ascending=False)
    total_val = merged["valuation"].sum()
    merged["cum_revenue_share"] = (merged["valuation"].cumsum() / total_val * 100).round(1)

    # 1. Global Filters Bar (Accessible across tabs)
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        cat_choices = ["Все"] + sorted(merged["category"].unique().tolist())
        sel_cat = st.selectbox("Категория", cat_choices, key="inv_cat_filter")
    with f2:
        abc_choices = ["Все", "A", "B", "C"]
        sel_abc = st.selectbox("Класс ABC", abc_choices, key="inv_abc_filter")
    with f3:
        xyz_choices = ["Все", "X", "Y", "Z"]
        sel_xyz = st.selectbox("Класс XYZ", xyz_choices, key="inv_xyz_filter")
    with f4:
        status_choices = ["Все", "CRITICAL", "REORDER_NEEDED", "OPTIMAL", "EXCESS"]
        sel_status = st.selectbox("Статус запаса", status_choices, key="inv_status_filter")

    # Filter dataframe
    filtered = merged.copy()
    if sel_cat != "Все":
        filtered = filtered[filtered["category"] == sel_cat]
    if sel_abc != "Все":
        filtered = filtered[filtered["abc_class"] == sel_abc]
    if sel_xyz != "Все":
        filtered = filtered[filtered["xyz_class"] == sel_xyz]
    if sel_status != "Все":
        filtered = filtered[filtered["status"] == sel_status]

    theme_mode_str = get_state("dss_theme_mode", "dark")
    theme_mode = ThemeMode.DARK if theme_mode_str == "dark" else ThemeMode.LIGHT
    theme = get_theme(theme_mode)

    # Sub-tabs for structured analytical workflow
    tab_matrix, tab_table, tab_strategies = st.tabs([
        "🎯 Матрица ABC/XYZ (9 квадрантов)",
        "📋 Реестр номенклатурных позиций",
        "💡 Рекомендуемые политики управления",
    ])

    with tab_matrix:
        st.markdown("### 🎯 Матричная сегментация ABC/XYZ (9 квадрантов)")
        st.caption("Матрица дифференцированных политик управления: ценность выручки (A/B/C) vs вариативность спроса (X/Y/Z)")

        # Build 9 matrix cells
        quadrant_meta = {
            "AX": ("🌟 КЛЮЧЕВОЙ (JIT)", "optimal"),
            "AY": ("⚡ ВЫСОКИЙ (Буфер)", "optimal"),
            "AZ": ("⚠️ РИСКОВЫЙ (MTO)", "critical"),
            "BX": ("⚙️ БАЗОВЫЙ (EOQ)", "reorder"),
            "BY": ("📦 РЕГУЛЯРНЫЙ", "reorder"),
            "BZ": ("🎲 СПОРАДИЧЕСКИЙ", "excess"),
            "CX": ("🔩 ВТОРОСТЕПЕННЫЙ", "neutral"),
            "CY": ("📉 НЕАКТИВНЫЙ", "neutral"),
            "CZ": ("🛑 НЕЛИКВИД", "excess"),
        }
        matrix_cells = []
        total_working_cap = merged["valuation"].sum() or 1.0
        for a in ["A", "B", "C"]:
            for x in ["X", "Y", "Z"]:
                code = f"{a}{x}"
                cell_df = merged[(merged["abc_class"] == a) & (merged["xyz_class"] == x)]
                c_cnt = len(cell_df)
                c_val = float(cell_df["valuation"].sum())
                c_pct = (c_val / total_working_cap) * 100
                lbl, thm = quadrant_meta[code]
                matrix_cells.append(
                    MatrixCellData(
                        code=code,
                        count=c_cnt,
                        valuation_rub=c_val,
                        capital_share_pct=c_pct,
                        label=lbl,
                        status_theme=thm,  # type: ignore[arg-type]
                    )
                )

        # Active quadrant highlight if single filter applied
        active_code = None
        if sel_abc != "Все" and sel_xyz != "Все":
            active_code = f"{sel_abc}{sel_xyz}"

        render_matrix_grid(matrix_cells, selected_code=active_code, theme_mode=theme_mode)

        st.markdown("#### 🧭 2D Диаграмма рассеяния номенклатуры")
        st.caption("Ось X: коэффициент вариации спроса (CV). Ось Y: кумулятивная доля капитала (%). Размер круга: стоимость остатка (₽)")

        status_colors = {
            "CRITICAL": theme.status.critical.fill,
            "REORDER_NEEDED": theme.status.reorder_needed.fill,
            "OPTIMAL": theme.status.optimal.fill,
            "EXCESS": theme.status.excess.fill,
        }

        fig = px.scatter(
            filtered,
            x="demand_cv",
            y="cum_revenue_share",
            size="valuation",
            color="status",
            color_discrete_map=status_colors,
            hover_name="name",
            hover_data={
                "sku_id": True,
                "category": True,
                "abc_class": True,
                "xyz_class": True,
                "on_hand": ":.1f",
                "effective_inventory": ":.1f",
                "reorder_point": ":.1f",
                "valuation": ":,.0f",
                "demand_cv": ":.2f",
                "cum_revenue_share": ":.1f%",
            },
            labels={
                "demand_cv": "Коэффициент вариации спроса (CV = σ / μ)",
                "cum_revenue_share": "Кумулятивная доля стоимости (%)",
                "status": "Статус запаса",
            },
            title="Карта позиций: Размер круга = Стоимость в запасах (₽)",
        )

        # Add quadrant separator lines
        fig.add_vline(x=0.15, line_dash="dash", line_color=theme.borders.default, annotation_text="X / Y (CV=0.15)")
        fig.add_vline(x=0.35, line_dash="dash", line_color=theme.borders.default, annotation_text="Y / Z (CV=0.35)")
        fig.add_hline(y=80.0, line_dash="dash", line_color=theme.borders.default, annotation_text="Класс A (80%)")
        fig.add_hline(y=95.0, line_dash="dash", line_color=theme.borders.default, annotation_text="Класс B (95%)")

        fig.update_layout(
            template=get_plotly_template(theme_mode),
            height=480,
            margin={"t": 50, "b": 30, "l": 30, "r": 30},
        )
        st.plotly_chart(fig, width="stretch")

    with tab_table:
        st.markdown("### 📋 Детализированный реестр номенклатуры")

        display_cols = [
            "sku_id",
            "name",
            "category",
            "abc_class",
            "xyz_class",
            "on_hand",
            "effective_inventory",
            "safety_stock",
            "reorder_point",
            "status",
            "valuation",
        ]
        renamed_cols = {
            "sku_id": "Артикул",
            "name": "Наименование",
            "category": "Категория",
            "abc_class": "ABC",
            "xyz_class": "XYZ",
            "on_hand": "В наличии",
            "effective_inventory": "Эфф. запас",
            "safety_stock": "SS",
            "reorder_point": "ROP",
            "status": "Статус",
            "valuation": "Стоимость (₽)",
        }

        table_data = filtered[display_cols].rename(columns=renamed_cols)
        if filtered.empty:
            st.info("ℹ️ По выбранным фильтрам записи не найдены. Сбросьте или измените параметры фильтрации.")
        st.dataframe(table_data, width="stretch", hide_index=True)

        # Download button
        csv_bytes = table_data.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Скачать реестр в CSV",
            data=csv_bytes,
            file_name="inventory_health_abc_xyz.csv",
            mime="text/csv",
        )

    with tab_strategies:
        st.markdown("### 💡 Матрица дифференцированных стратегий управления")
        c_ax, c_by, c_cz = st.columns(3)
        with c_ax:
            st.markdown(
                """<div class="dss-action-card">
                    <div class="dss-action-title">💎 Квадрант AX / AY (Фокус)</div>
                    <div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 4px;">
                        • Высокая стоимость, стабильный спрос.<br>
                        • Стратегия: <b>Just-In-Time, частые поставки малыми партиями</b>.<br>
                        • Жесткий ежедневный контроль ROP.<br>
                        • Минимизация страхового запаса.
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )
        with c_by:
            st.markdown(
                """<div class="dss-action-card">
                    <div class="dss-action-title">⚖️ Квадрант BX / BY (Базовый)</div>
                    <div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 4px;">
                        • Средняя стоимость, умеренная вариация.<br>
                        • Стратегия: <b>Периодический пересмотр (R, S)</b>.<br>
                        • Оптимизация размера партии по EOQ.<br>
                        • Балансировка под складские кванты.
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )
        with c_cz:
            st.markdown(
                """<div class="dss-action-card">
                    <div class="dss-action-title">⚠️ Квадрант AZ / BZ / CZ (Риск)</div>
                    <div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 4px;">
                        • Высокая нестабильность и нерегулярность.<br>
                        • Стратегия: <b>Под заказ (Make-to-Order)</b> или повышенный буфер.<br>
                        • Подавление эффекта хлыста (Bullwhip).<br>
                        • Анализ на выбытие неликвидов.
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )
