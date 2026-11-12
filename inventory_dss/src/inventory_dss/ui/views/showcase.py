"""Screen 6: Production-Grade Design System Interactive Showcase (Milestone 3).

Demonstrates and verifies:
- 1. 3-Tier Design Token Architecture (Primitive, Semantic, Component).
- 2. Live KPI Metric Cards with tabular numerals and capacity micro-gauges.
- 3. Status Badges & Chips with animated pulse indicator (CRITICAL, REORDER_NEEDED, OPTIMAL, EXCESS).
- 4. High-Density Accessible Data Table with right-aligned tabular numerals and embedded badges.
- 5. Explainable AI Reasoning Cards for all 3 Epistemic Trust Tiers (ALGORITHMIC, HEURISTIC, EXPLORATORY).
- 6. What-If Interactive Controls Container.
- 7. Plotly Themed Visualizations (Confidence Fan Chart and Dual Warehouse Gauges).
- 8. Concentric Radii Geometry Verification ($R_{outer} = R_{inner} + padding$).
- 9. WCAG 2.2 AA Contrast Audit Matrix.
"""

from __future__ import annotations

import datetime

import pandas as pd
import streamlit as st

from inventory_dss.ui.components import (
    ColumnConfig,
    DecisionFactor,
    KpiMetricData,
    MatrixCellData,
    ReasoningCardData,
    create_confidence_fan_chart,
    render_data_table,
    render_kpi_grid,
    render_matrix_grid,
    render_reasoning_card,
    render_status_badge,
    render_what_if_controls,
)
from inventory_dss.ui.state import get_state, set_state
from inventory_dss.ui.theme import (
    AMBER_PALETTE,
    CRIMSON_PALETTE,
    EMERALD_PALETTE,
    INDIGO_PALETTE,
    SKY_PALETTE,
    SLATE_PALETTE,
    ZINC_PALETTE,
    EpistemicTrustTier,
    InventoryStatus,
    RadiiTokens,
    ThemeMode,
    calculate_contrast_ratio,
    get_theme,
)
from inventory_dss.ui.utils import create_gauge_chart


def render_showcase_screen() -> None:
    """Render interactive showcase validating tokens, components, and accessibility."""
    theme_mode_str = get_state("dss_theme_mode", "dark")
    active_mode = ThemeMode.DARK if theme_mode_str == "dark" else ThemeMode.LIGHT
    theme = get_theme(active_mode)

    st.markdown("## ⚙️ ПРОМЫШЛЕННЫЙ НЕОБРУТАЛИЗМ :: ПУЛЬТ СППР (INDUSTRIAL NEO-BRUTALISM)")
    st.caption(
        "Инженерная эстетика диспетчерского терминала: жесткие тени без размытия (0-Blur Hard Shadows), "
        "контуры 2-3px, тактильный механический отклик, сигнальная палитра безопасности и моноширинная точность."
    )

    # -----------------------------------------------------------------------
    # Section 0: Theme Mode Switcher Bar
    # -----------------------------------------------------------------------
    st.markdown("### 🌓 Активная тема оформления")
    col_mode1, col_mode2 = st.columns([2, 3])
    with col_mode1:
        selected_theme = st.radio(
            "Режим темы интерфейса",
            options=["Темная тема (Zinc Dark)", "Светлая тема (Slate Light)"],
            index=0 if active_mode == ThemeMode.DARK else 1,
            horizontal=True,
            key="showcase_theme_radio",
        )
        new_mode_str = "dark" if "Темная" in selected_theme else "light"
        if new_mode_str != theme_mode_str:
            set_state("dss_theme_mode", new_mode_str)
            st.rerun()

    with col_mode2:
        st.info(
            f"**Текущий профиль**: `{theme.mode.value.upper()}` | "
            f"**Canvas (Layer-0)**: `{theme.surfaces.layer_0}` | "
            f"**Card (Layer-1)**: `{theme.surfaces.layer_1}` | "
            f"**Border**: `{theme.borders.default}` | "
            f"**Primary Accent**: `{theme.accent.primary}`"
        )

    st.markdown("---")

    # -----------------------------------------------------------------------
    # Section 1: 3-Tier Design Tokens
    # -----------------------------------------------------------------------
    st.markdown("### 1. Архитектура дизайн-токенов (3-Tier Tokens)")
    t1, t2, t3 = st.tabs(["Primitive Tokens", "Semantic Tokens", "Component Tokens"])

    with t1:
        st.markdown("#### Примитивные цветовые шкалы (11 градаций [50..950])")
        palettes = [
            ("Zinc (Нейтраль Dark)", ZINC_PALETTE),
            ("Slate (Нейтраль Light)", SLATE_PALETTE),
            ("Indigo (Основной бренд-акцент)", INDIGO_PALETTE),
            ("Crimson (Критический статус)", CRIMSON_PALETTE),
            ("Amber (Предупреждение)", AMBER_PALETTE),
            ("Emerald (Успех / Норма)", EMERALD_PALETTE),
            ("Sky (Инфо / Избыток)", SKY_PALETTE),
        ]
        for name, pal in palettes:
            st.markdown(f"**{name}**")
            cols = st.columns(11)
            steps = ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"]
            for c, step in zip(cols, steps, strict=True):
                hex_val = getattr(pal, f"c{step}")
                c.markdown(
                    f'<div style="background:{hex_val};height:32px;border-radius:4px;border:1px solid rgba(128,128,128,0.2);"></div>'
                    f'<div style="font-size:0.65rem;text-align:center;font-family:monospace;margin-top:2px;">{step}<br>{hex_val}</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("#### Типографика и сетка отступов")
        c_typ1, c_typ2 = st.columns(2)
        with c_typ1:
            st.markdown(
                f"""
                - **Font Sans**: `{theme.typography.font_sans}`
                - **Font Mono (Tabular Nums)**: `{theme.typography.font_mono}`
                - **Scale**: `xs: 12px` | `sm: 14px` | `base: 16px` | `lg: 18px` | `xl: 20px` | `2xl: 24px` | `3xl: 30px`
                """
            )
        with c_typ2:
            st.markdown(
                """
                - **Базовая сетка**: `4px / 8px`
                - **Spacing Tokens**: `space-1 (4px)`, `space-2 (8px)`, `space-3 (12px)`, `space-4 (16px)`, `space-6 (24px)`, `space-8 (32px)`
                - **Concentric Scale**: `sm: 4px`, `md: 6px`, `lg: 8px`, `xl: 12px`, `2xl: 16px`, `full: 9999px`
                """
            )

    with t2:
        st.markdown("#### Семантические слои поверхностей и статусы")
        c_sem1, c_sem2 = st.columns(2)
        with c_sem1:
            st.markdown(
                f"""
                <div style="background:{theme.surfaces.layer_0};padding:16px;border-radius:8px;border:1px solid {theme.borders.default};">
                    <span style="color:{theme.text.secondary};font-size:0.8rem;">SURFACE LAYER-0 (Canvas)</span>
                    <div style="background:{theme.surfaces.layer_1};padding:14px;border-radius:6px;border:1px solid {theme.borders.default};margin-top:8px;">
                        <span style="color:{theme.text.primary};font-weight:600;">SURFACE LAYER-1 (Card)</span>
                        <div style="background:{theme.surfaces.layer_2};padding:10px;border-radius:4px;border:1px solid {theme.borders.subtle};margin-top:8px;">
                            <span style="color:{theme.text.secondary};font-size:0.75rem;">SURFACE LAYER-2 (Popover / Hover)</span>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c_sem2:
            st.markdown(
                f"""
                **Семантические статусы номенклатуры:**
                - <span style="color:{theme.status.critical.fill};font-weight:600;">● CRITICAL</span>: {theme.status.critical.fill} (bg: {theme.status.critical.bg})
                - <span style="color:{theme.status.reorder_needed.fill};font-weight:600;">● REORDER_NEEDED</span>: {theme.status.reorder_needed.fill} (bg: {theme.status.reorder_needed.bg})
                - <span style="color:{theme.status.optimal.fill};font-weight:600;">● OPTIMAL</span>: {theme.status.optimal.fill} (bg: {theme.status.optimal.bg})
                - <span style="color:{theme.status.excess.fill};font-weight:600;">● EXCESS</span>: {theme.status.excess.fill} (bg: {theme.status.excess.bg})
                """,
                unsafe_allow_html=True,
            )

    with t3:
        st.markdown("#### Токены компонентов СППР")
        st.json({
            "kpi_card": {
                "bg": theme.components.kpi_card.bg,
                "border": theme.components.kpi_card.border,
                "radius": theme.components.kpi_card.radius,
                "title_color": theme.components.kpi_card.title_color,
                "value_color": theme.components.kpi_card.value_color,
            },
            "data_table": {
                "header_bg": theme.components.data_table.header_bg,
                "row_border": theme.components.data_table.row_border,
                "row_hover_bg": theme.components.data_table.row_hover_bg,
            },
            "reasoning_card": {
                "bg": theme.components.reasoning_card.bg,
                "border_left_width": theme.components.reasoning_card.border_left_width,
                "radius": theme.components.reasoning_card.radius,
            },
            "chart": {
                "bg": theme.components.chart.bg,
                "grid_color": theme.components.chart.grid_color,
                "confidence_band_fill": theme.components.chart.confidence_band_fill,
            },
        })

    st.markdown("---")

    # -----------------------------------------------------------------------
    # Section 2: Key Components Showcase
    # -----------------------------------------------------------------------
    st.markdown("### 2. Спецификация ключевых компонентов СППР (Milestone 2)")

    # 2.1 KPI Metric Cards
    st.markdown("#### 2.1 Карточки ключевых показателей (KPI Metric Cards)")
    st.caption("Крупные табличные числа (tabular-nums), индикаторы дельты и шкалы заполненности склада")
    kpis = [
        KpiMetricData(
            title="ОЦЕНКА ЗАПАСОВ",
            value="42.85 млн ₽",
            delta="+3.2% vs план",
            delta_direction="up",
            delta_color="normal",
            caption="Норматив: 40.0 млн ₽",
            gauge_value=65.0,
            gauge_max=100.0,
            gauge_label="Загрузка бюджета",
        ),
        KpiMetricData(
            title="УРОВЕНЬ СЕРВИСА (α)",
            value="98.5%",
            delta="+1.5% выше цели",
            delta_direction="up",
            delta_color="normal",
            caption="Целевой уровень: 95.0%",
            gauge_value=98.5,
            gauge_max=100.0,
            gauge_label="Исполнение заказов",
        ),
        KpiMetricData(
            title="ДЕФИЦИТ (CRITICAL)",
            value="4 SKU",
            delta="+2 позиции",
            delta_direction="up",
            delta_color="inverse",
            caption="Требуют срочного заказа",
            gauge_value=92.0,
            gauge_max=100.0,
            gauge_label="Индекс риска",
        ),
        KpiMetricData(
            title="ОБЪЕМ СКЛАДА (WH-01)",
            value="1 180 м³",
            delta="98.3% лимита",
            delta_direction="neutral",
            delta_color="off",
            caption="Свободно: 20 м³",
            gauge_value=98.3,
            gauge_max=100.0,
            gauge_label="Емкость стеллажей",
        ),
    ]
    render_kpi_grid(kpis, columns=4, theme_mode=active_mode)

    st.write("")

    # 2.2 Status Badges & Chips
    st.markdown("#### 2.2 Статусные чипсы и бейджи (Status Badges & Chips)")
    st.caption("Стандартизированные статусы с пульсирующим индикатором для критических событий")
    b_col1, b_col2, b_col3, b_col4 = st.columns(4)
    with b_col1:
        st.markdown("**CRITICAL (Пульсация)**")
        render_status_badge(InventoryStatus.CRITICAL, label="ДЕФИЦИТ", pulse=True, count=4, size="lg")
        render_status_badge(InventoryStatus.CRITICAL, label="КРИТИЧНО", pulse=True, size="md")
        render_status_badge(InventoryStatus.CRITICAL, size="sm")
    with b_col2:
        st.markdown("**REORDER_NEEDED**")
        render_status_badge(InventoryStatus.REORDER_NEEDED, label="К ЗАКАЗУ", count=8, size="lg")
        render_status_badge(InventoryStatus.REORDER_NEEDED, label="ПЕРЕЗАКАЗ", size="md")
        render_status_badge(InventoryStatus.REORDER_NEEDED, size="sm")
    with b_col3:
        st.markdown("**OPTIMAL**")
        render_status_badge(InventoryStatus.OPTIMAL, label="НОРМА", count=11, size="lg")
        render_status_badge(InventoryStatus.OPTIMAL, label="ОПТИМАЛЬНО", size="md")
        render_status_badge(InventoryStatus.OPTIMAL, size="sm")
    with b_col4:
        st.markdown("**EXCESS**")
        render_status_badge(InventoryStatus.EXCESS, label="ИЗБЫТОК", count=2, size="lg")
        render_status_badge(InventoryStatus.EXCESS, label="ПРОФИЦИТ", size="md")
        render_status_badge(InventoryStatus.EXCESS, size="sm")

    st.write("")

    # 2.3 Explainable AI Reasoning Card
    st.markdown("#### 2.3 Карточка обоснования рекомендаций (Explainable AI Reasoning Card)")
    st.caption("3 уровня доверия (Trust Tiers), декомпозиция факторов решения и доверительные интервалы")

    tier_tab1, tier_tab2, tier_tab3 = st.tabs([
        "🛡️ Tier 1: ALGORITHMIC (KKT / EOQ)",
        "⚖️ Tier 2: HEURISTIC (TOPSIS / HW)",
        "🧪 Tier 3: EXPLORATORY (What-If / LLM)",
    ])

    with tier_tab1:
        render_reasoning_card(
            ReasoningCardData(
                sku_id="SKU-ELEC-001",
                sku_name="Промышленный контроллер PLC-400",
                trust_tier=EpistemicTrustTier.ALGORITHMIC,
                recommendation_title="Срочный заказ партии пополнения 350 ед.",
                recommended_quantity=350,
                selected_supplier="SUP-PREMIUM (ПАО ПромСнаб)",
                estimated_cost_rub=1_575_000.0,
                rationale=(
                    "Остаток (15 ед.) упал ниже страхового запаса (35 ед.). Оптимальная партия рассчитана по модели "
                    "EOQ с ограничениями ККТ по вместимости склада WH-01. Доказана глобальная субоптимальность без дефицита."
                ),
                factors=[
                    DecisionFactor(name="Дефицит остатка", value="15 < 35 ед.", impact="negative", weight=0.45),
                    DecisionFactor(name="Рейтинг поставщика", value="0.9412 TOPSIS", impact="positive", weight=0.30),
                    DecisionFactor(name="Лимит объема склада", value="32.5 / 1200 м³", impact="positive", weight=0.25),
                ],
                confidence_interval=(315.0, 385.0),
                confidence_level=0.95,
                urgency="CRITICAL",
                stockout_risk_reduction="Снижение вероятности дефицита с 42.0% до 0.8%",
            ),
            theme_mode=active_mode,
        )

    with tier_tab2:
        render_reasoning_card(
            ReasoningCardData(
                sku_id="SKU-MECH-012",
                sku_name="Гидравлический распределитель HD-2",
                trust_tier=EpistemicTrustTier.HEURISTIC,
                recommendation_title="Плановое пополнение 120 ед. по комбинированному рейтингу",
                recommended_quantity=120,
                selected_supplier="SUP-STANDARD (ООО ТехноПарк)",
                estimated_cost_rub=480_000.0,
                rationale=(
                    "Прогнозирование выполнено методом Holt-Winters с аддитивной сезонностью. "
                    "Выбор поставщика произведен многокритериальной сверткой TOPSIS с весами экспертных приоритетов AHP."
                ),
                factors=[
                    DecisionFactor(name="Сезонный тренд", value="+14% к пред. мес.", impact="positive", weight=0.40),
                    DecisionFactor(name="OTIF поставщика", value="94.5%", impact="positive", weight=0.35),
                    DecisionFactor(name="Срок поставки", value="7.2 ± 1.1 дн.", impact="neutral", weight=0.25),
                ],
                confidence_interval=(105.0, 135.0),
                confidence_level=0.90,
                urgency="NORMAL",
                stockout_risk_reduction="Поддержание уровня доступности α = 95.0%",
            ),
            theme_mode=active_mode,
        )

    with tier_tab3:
        render_reasoning_card(
            ReasoningCardData(
                sku_id="SKU-CHEM-005",
                sku_name="Синтетический полимер Poly-X",
                trust_tier=EpistemicTrustTier.EXPLORATORY,
                recommendation_title="Стресс-сценарий: буферный заказ 500 ед. при задержке поставок",
                recommended_quantity=500,
                selected_supplier="SUP-BUDGET (ЗАО ХимТрейд)",
                estimated_cost_rub=750_000.0,
                rationale=(
                    "Сценарий сгенерирован подсистемой What-If при искусственном шоке сроков логистики +7 дней. "
                    "Рекомендуется предварительное согласование условий с альтернативным контрагентом."
                ),
                factors=[
                    DecisionFactor(name="Шок сроков доставки", value="+7.0 дней", impact="negative", weight=0.50),
                    DecisionFactor(name="Буферный объем", value="45.0 м³", impact="neutral", weight=0.30),
                    DecisionFactor(name="Экономия на объеме", value="-8% скидка", impact="positive", weight=0.20),
                ],
                confidence_interval=(420.0, 580.0),
                confidence_level=0.80,
                urgency="HIGH",
                stockout_risk_reduction="Снижение экспозиции логистического риска на 65%",
            ),
            theme_mode=active_mode,
        )

    st.write("")

    # 2.4 Data Table Styling
    st.markdown("#### 2.4 Таблицы высокой плотности (Data Table Styling)")
    st.caption("Выравнивание чисел по правому краю, tabular-nums, липкие заголовки и встроенные бейджи")
    demo_df = pd.DataFrame([
        {
            "Артикул": "SKU-ELEC-001",
            "Наименование": "Контроллер PLC-400",
            "Остаток (ед.)": 15,
            "Точка ROP (ед.)": 45,
            "Стоимость (₽)": 1575000.0,
            "Статус": "CRITICAL",
        },
        {
            "Артикул": "SKU-MECH-012",
            "Наименование": "Распределитель HD-2",
            "Остаток (ед.)": 38,
            "Точка ROP (ед.)": 40,
            "Стоимость (₽)": 480000.0,
            "Статус": "REORDER_NEEDED",
        },
        {
            "Артикул": "SKU-PACK-003",
            "Наименование": "Гофрокороб T-24",
            "Остаток (ед.)": 1200,
            "Точка ROP (ед.)": 500,
            "Стоимость (₽)": 240000.0,
            "Статус": "OPTIMAL",
        },
        {
            "Артикул": "SKU-FAST-019",
            "Наименование": "Болт М8х30 ГОСТ",
            "Остаток (ед.)": 15400,
            "Точка ROP (ед.)": 3000,
            "Стоимость (₽)": 616000.0,
            "Статус": "EXCESS",
        },
    ])
    demo_cols = [
        ColumnConfig("Артикул", align="left"),
        ColumnConfig("Наименование", align="left"),
        ColumnConfig("Остаток (ед.)", align="right", is_numeric=True, format_spec="{:,.0f}"),
        ColumnConfig("Точка ROP (ед.)", align="right", is_numeric=True, format_spec="{:,.0f}"),
        ColumnConfig("Стоимость (₽)", align="right", is_numeric=True, format_spec="{:,.0f} ₽"),
        ColumnConfig("Статус", align="center", is_status=True),
    ]
    render_data_table(demo_df, columns=demo_cols, status_column="Статус")

    st.write("")

    # 2.5 What-If Controls Container
    st.markdown("#### 2.5 Контейнер интерактивного What-If моделирования")
    st.caption("Параметры стресс-тестирования в компактном семантическом блоке")
    render_what_if_controls(key_prefix="showcase_wb")

    st.write("")

    # 2.6 Themed Plotly Visualizations
    st.markdown("#### 2.6 Plotly графики с темой DSS (Fan Chart & Gauges)")
    c_g1, c_g2 = st.columns(2)
    with c_g1:
        st.markdown("**Индикатор склада (Объем)**")
        fig_g_vol = create_gauge_chart(1180.0, 1200.0, title="Объем склада WH-01", unit="м³", theme_mode=active_mode)
        st.plotly_chart(fig_g_vol, width="stretch")
    with c_g2:
        st.markdown("**Индикатор склада (Вес)**")
        fig_g_wt = create_gauge_chart(38500.0, 50000.0, title="Весовая нагрузка стеллажей", unit="кг", theme_mode=active_mode)
        st.plotly_chart(fig_g_wt, width="stretch")

    st.markdown("**Доверительный веер прогноза спроса (Fan Chart)**")
    sample_dates = [datetime.date.today() - datetime.timedelta(days=i) for i in range(30, 0, -1)]
    future_dates = [datetime.date.today() + datetime.timedelta(days=i) for i in range(1, 15)]
    history_demand = [100 + i * 1.5 + (i % 3) * 5 for i in range(30)]
    forecast_mean = [145 + i * 2 for i in range(14)]
    forecast_lower = [val - 15 - i * 0.8 for i, val in enumerate(forecast_mean)]
    forecast_upper = [val + 15 + i * 0.8 for i, val in enumerate(forecast_mean)]

    fig_fan = create_confidence_fan_chart(
        x=sample_dates,
        y_history=history_demand,
        x_forecast=future_dates,
        y_forecast=forecast_mean,
        y_lower=forecast_lower,
        y_upper=forecast_upper,
        theme_mode=active_mode,
        title="Смоделированный коридор спроса [L95; U95] на 14 дней",
    )
    st.plotly_chart(fig_fan, width="stretch")

    st.write("")

    # 2.7 9-Cell ABC/XYZ Classification Matrix Grid
    st.markdown("#### 2.7 Матрица сегментации запасов ABC/XYZ (Mission-Critical Grid)")
    st.caption("Тактильная сетка 3х3 с цветовым кодированием логистических стратегий, метриками капитала и SKU")
    showcase_matrix_cells = [
        MatrixCellData(code="AX", count=8, valuation_rub=18_450_000.0, capital_share_pct=43.1, label="JIT / Точно в срок", status_theme="optimal"),
        MatrixCellData(code="AY", count=4, valuation_rub=9_200_000.0, capital_share_pct=21.5, label="Регулярный ROP", status_theme="reorder"),
        MatrixCellData(code="AZ", count=2, valuation_rub=4_800_000.0, capital_share_pct=11.2, label="Страховой / VMI", status_theme="critical"),
        MatrixCellData(code="BX", count=6, valuation_rub=4_100_000.0, capital_share_pct=9.6, label="Периодический", status_theme="optimal"),
        MatrixCellData(code="BY", count=5, valuation_rub=3_050_000.0, capital_share_pct=7.1, label="Стандартный ROP", status_theme="neutral"),
        MatrixCellData(code="BZ", count=3, valuation_rub=1_600_000.0, capital_share_pct=3.7, label="Гибкий заказ", status_theme="reorder"),
        MatrixCellData(code="CX", count=12, valuation_rub=950_000.0, capital_share_pct=2.2, label="Партии EOQ", status_theme="neutral"),
        MatrixCellData(code="CY", count=7, valuation_rub=450_000.0, capital_share_pct=1.1, label="Упрощенный", status_theme="neutral"),
        MatrixCellData(code="CZ", count=5, valuation_rub=250_000.0, capital_share_pct=0.6, label="Под проект", status_theme="excess"),
    ]
    render_matrix_grid(showcase_matrix_cells, theme_mode=active_mode)

    st.markdown("---")

    # -----------------------------------------------------------------------
    # Section 3: Concentric Radii Geometry Verification
    # -----------------------------------------------------------------------
    st.markdown("### 3. Математическое обоснование концентрических радиусов")
    st.latex(r"R_{outer} = R_{inner} + P \quad \iff \quad R_{inner} = \max(0, R_{outer} - P)")
    st.markdown(
        """
        **Правило концентричности:** если вложенный элемент с внутренним радиусом скругления $R_{inner}$
        находится внутри внешнего контейнера с радиусом $R_{outer}$ при зазоре (padding) $P$,
        то центры кривизны их окружностей обязаны совпадать во избежание визуального оптического искажения («эффекта линзы»).
        """
    )
    r_cols = st.columns(3)
    examples = [
        (16, 8, "Card (Outer: 16px, Padding: 8px)"),
        (24, 12, "Modal / Sheet (Outer: 24px, Padding: 12px)"),
        (8, 4, "Nested Button (Outer: 8px, Padding: 4px)"),
    ]
    for col, (r_out, pad, title) in zip(r_cols, examples, strict=True):
        r_in = RadiiTokens.calculate_concentric_radius(r_out, pad)
        with col:
            st.markdown(
                f"""
                <div style="background:{theme.surfaces.layer_1};padding:{pad}px;border-radius:{r_out}px;border:1px solid {theme.borders.default};">
                    <div style="font-size:0.75rem;color:{theme.text.muted};margin-bottom:4px;">{title}</div>
                    <div style="background:{theme.surfaces.layer_2};padding:12px;border-radius:{r_in}px;border:1px solid {theme.borders.subtle};text-align:center;">
                        <span style="font-family:monospace;font-size:0.8rem;color:{theme.text.primary};">
                            R_outer = {r_out}px<br>
                            Padding = {pad}px<br>
                            <strong>R_inner = {r_in}px</strong>
                        </span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # -----------------------------------------------------------------------
    # Section 4: WCAG 2.2 AA Contrast Compliance Audit
    # -----------------------------------------------------------------------
    st.markdown("### 4. Матрица аудита доступности WCAG 2.2 AA")
    st.caption("Расчет относительной яркости $L = 0.2126 R + 0.7152 G + 0.0722 B$ и контраста $(L_1 + 0.05) / (L_2 + 0.05)$")

    pairs = [
        ("Основной текст на холсте (Canvas)", theme.text.primary, theme.surfaces.layer_0, 4.5),
        ("Вторичный текст на холсте", theme.text.secondary, theme.surfaces.layer_0, 4.5),
        ("Основной текст на карточке (Layer-1)", theme.text.primary, theme.surfaces.layer_1, 4.5),
        ("Вторичный текст на карточке", theme.text.secondary, theme.surfaces.layer_1, 4.5),
        ("Белый текст на бренд-кнопке (Indigo-600)", "#FFFFFF", theme.accent.primary, 4.5),
        ("Бордер карточки к фону (UI Component)", theme.borders.default, theme.surfaces.layer_0, 3.0),
        ("Критический статус текст к фону плашки", theme.status.critical.fill, theme.status.critical.bg, 4.5),
        ("Предупреждение текст к фону плашки", theme.status.reorder_needed.fill, theme.status.reorder_needed.bg, 4.5),
        ("Норма текст к фону плашки", theme.status.optimal.fill, theme.status.optimal.bg, 4.5),
        ("Избыток текст к фону плашки", theme.status.excess.fill, theme.status.excess.bg, 4.5),
    ]

    wcag_rows = []
    for desc, fg, bg, req in pairs:
        ratio = calculate_contrast_ratio(fg, bg)
        passed = ratio >= req
        wcag_rows.append({
            "Элемент / Пара цветов": desc,
            "Foreground": fg,
            "Background": bg,
            "Контраст": f"{ratio:.2f}:1",
            "Норматив WCAG": f">={req:.1f}:1",
            "Статус": "✅ PASS" if passed else "❌ FAIL",
        })

    wcag_df = pd.DataFrame(wcag_rows)
    st.dataframe(wcag_df, width="stretch", hide_index=True)
