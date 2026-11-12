"""Unit tests for Milestone 2 UI Components Reference Implementation."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from inventory_dss.ui.components import (
    DecisionFactor,
    KpiMetricData,
    MatrixCellData,
    ReasoningCardData,
    WhatIfScenarioState,
    apply_plotly_theme,
    create_confidence_fan_chart,
    data_table_html,
    dispatch_bar_html,
    format_table_styler,
    kpi_card_html,
    matrix_grid_html,
    reasoning_card_html,
    render_dispatch_bar,
    render_matrix_grid,
    render_what_if_controls,
    status_badge_html,
)
from inventory_dss.ui.theme import EpistemicTrustTier, InventoryStatus, ThemeMode

# ==============================================================================
# 1. KPI Metric Card Tests
# ==============================================================================

class TestKpiMetricCard:
    """Test suite for KPI metric card rendering and micro-gauges."""

    def test_kpi_card_basic_rendering(self) -> None:
        """Card should contain title, formatted value, and proper CSS class."""
        metric = KpiMetricData(title="Стоимость запасов", value=45200000.0, unit="млн ₽")
        html_out = kpi_card_html(metric)

        assert "dss-kpi-card" in html_out
        assert "dss-kpi-title" in html_out
        assert "Стоимость запасов" in html_out
        assert "dss-kpi-value" in html_out
        assert "45,200,000.00" in html_out
        assert "млн ₽" in html_out

    def test_kpi_card_delta_indicators(self) -> None:
        """Delta indicator should render appropriate arrows and color classes."""
        # Normal positive (increase is good)
        m_pos = KpiMetricData(title="Уровень сервиса", value="98.5%", delta="+2.1%", delta_color="normal")
        out_pos = kpi_card_html(m_pos)
        assert "dss-delta-positive" in out_pos
        assert "&#9650;" in out_pos
        assert "+2.1%" in out_pos

        # Normal negative (decrease is bad)
        m_neg = KpiMetricData(title="Уровень сервиса", value="88.0%", delta="-5.2%", delta_color="normal")
        out_neg = kpi_card_html(m_neg)
        assert "dss-delta-negative" in out_neg
        assert "&#9660;" in out_neg

        # Inverted positive (increase is bad, e.g. stockouts)
        m_inv_up = KpiMetricData(title="Дефицит", value=5, delta="+3 SKU", delta_color="inverse")
        out_inv_up = kpi_card_html(m_inv_up)
        assert "dss-delta-negative" in out_inv_up  # Inverted: up is negative

        # Neutral delta
        m_neutral = KpiMetricData(title="Норма", value=100, delta="Норматив", delta_color="off")
        out_neutral = kpi_card_html(m_neutral)
        assert "dss-delta-neutral" in out_neutral
        assert "&mdash;" in out_neutral

    def test_kpi_card_micro_gauge_thresholds(self) -> None:
        """Micro-gauge bar should respond to capacity utilization thresholds."""
        # Optimal (< 80%)
        m_opt = KpiMetricData(
            title="Объем склада",
            value="750 м³",
            gauge_value=750.0,
            gauge_max=1500.0,
            gauge_unit="м³",
        )
        out_opt = kpi_card_html(m_opt)
        assert "dss-kpi-gauge" in out_opt
        assert "dss-gauge-optimal" in out_opt
        assert "50.0%" in out_opt
        assert "width: 50.0%;" in out_opt

        # Warning (80% - 95%)
        m_warn = KpiMetricData(
            title="Объем склада",
            value="1350 м³",
            gauge_value=1350.0,
            gauge_max=1500.0,
        )
        out_warn = kpi_card_html(m_warn)
        assert "dss-gauge-warning" in out_warn
        assert "90.0%" in out_warn

        # Critical (>= 95%)
        m_crit = KpiMetricData(
            title="Объем склада",
            value="1470 м³",
            gauge_value=1470.0,
            gauge_max=1500.0,
        )
        out_crit = kpi_card_html(m_crit)
        assert "dss-gauge-critical" in out_crit
        assert "98.0%" in out_crit

    def test_kpi_card_gauge_clamp_overflow(self) -> None:
        """Gauge fill width must clamp to 100% on overflow to avoid layout breaking."""
        m_over = KpiMetricData(
            title="Складской перегруз",
            value="1600 м³",
            gauge_value=1650.0,
            gauge_max=1500.0,
        )
        out_over = kpi_card_html(m_over)
        assert "width: 100.0%;" in out_over
        assert "110.0%" in out_over  # Text shows true percentage
        assert "dss-gauge-critical" in out_over


# ==============================================================================
# 2. Status Badges & Chips Tests
# ==============================================================================

class TestStatusBadges:
    """Test suite for standardized domain status pills and chips."""

    def test_all_four_domain_statuses(self) -> None:
        """All 4 domain statuses must render with appropriate CSS classes."""
        # Critical with pulse
        crit = status_badge_html(InventoryStatus.CRITICAL)
        assert "dss-badge-critical" in crit
        assert "dss-dot-critical" in crit
        assert "ДЕФИЦИТ" in crit

        # Reorder needed
        reorder = status_badge_html(InventoryStatus.REORDER_NEEDED)
        assert "dss-badge-reorder" in reorder
        assert "dss-dot-reorder" in reorder
        assert "К ЗАКАЗУ" in reorder

        # Optimal
        optimal = status_badge_html(InventoryStatus.OPTIMAL)
        assert "dss-badge-optimal" in optimal
        assert "dss-dot-optimal" in optimal
        assert "НОРМА" in optimal

        # Excess
        excess = status_badge_html(InventoryStatus.EXCESS)
        assert "dss-badge-excess" in excess
        assert "dss-dot-excess" in excess
        assert "ИЗБЫТОК" in excess

    def test_status_badge_string_input_case_insensitive(self) -> None:
        """String inputs should be normalized regardless of case."""
        assert "dss-badge-critical" in status_badge_html("critical")
        assert "dss-badge-reorder" in status_badge_html("Reorder_Needed")
        assert "dss-badge-optimal" in status_badge_html("optimal")
        assert "dss-badge-excess" in status_badge_html("excess")

    def test_status_badge_custom_label_and_count(self) -> None:
        """Custom labels and count badges should be supported."""
        out = status_badge_html(InventoryStatus.CRITICAL, label="Внимание: стокаут", count=7, size="lg")
        assert "Внимание: стокаут" in out
        assert "(7)" in out
        assert "dss-badge-lg" in out


# ==============================================================================
# 3. Data Table Tests
# ==============================================================================

class TestDataTable:
    """Test suite for enhanced data table presentation."""

    def test_data_table_html_structure(self) -> None:
        """Table should render sticky header, right-aligned numbers, and status chips."""
        df = pd.DataFrame([
            {"sku_id": "SKU-001", "name": "Подшипник", "stock": 120, "cost": 45000.5, "status": "OPTIMAL"},
            {"sku_id": "SKU-002", "name": "Ремень ГРМ", "stock": 0, "cost": 0.0, "status": "CRITICAL"},
        ])
        out = data_table_html(df)

        assert "dss-table-container" in out
        assert "dss-table" in out
        assert "dss-th" in out
        assert "dss-td-num" in out  # Numeric columns
        assert "dss-badge-optimal" in out  # Status chip in row 1
        assert "dss-badge-critical" in out  # Status chip in row 2

    def test_data_table_html_escaping_security(self) -> None:
        """Malicious string contents in dataframe must be escaped to prevent XSS."""
        df = pd.DataFrame([
            {"sku_id": "<script>alert(1)</script>", "status": "OPTIMAL"}
        ])
        out = data_table_html(df)
        assert "<script>" not in out
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out

    def test_data_table_empty_fallback(self) -> None:
        """Empty dataframe should render friendly empty placeholder."""
        df = pd.DataFrame()
        out = data_table_html(df)
        assert "Нет данных для отображения" in out

    def test_format_table_styler(self) -> None:
        """Pandas Styler should successfully generate with tabular font settings."""
        df = pd.DataFrame([
            {"sku_id": "SKU-001", "stock": 100, "status": "OPTIMAL"},
            {"sku_id": "SKU-002", "stock": 5, "status": "CRITICAL"},
        ])
        styler = format_table_styler(df, status_column="status")
        assert styler is not None
        rendered_html = styler.to_html()
        assert "tabular-nums" in rendered_html


# ==============================================================================
# 4. Explainable AI Reasoning Card Tests
# ==============================================================================

class TestReasoningCard:
    """Test suite for Explainable AI recommendation cards."""

    def test_reasoning_card_algorithmic_tier(self) -> None:
        """Algorithmic tier card should render emerald left border and proof pill."""
        data = ReasoningCardData(
            sku_id="SKU-001",
            sku_name="Моторное масло 5W-40",
            trust_tier=EpistemicTrustTier.ALGORITHMIC,
            recommendation_title="Пополнение запаса по модели KKT-оптимизации",
            recommended_quantity=350,
            selected_supplier="SUP-PREMIUM",
            estimated_cost_rub=280000.0,
            rationale="Заказ сформирован на основе точного решения условий KKT с учетом вместимости склада.",
            factors=[
                DecisionFactor(name="Дефицит до SS", value=-120, impact="negative", weight=0.4),
                DecisionFactor(name="Рейтинг поставщика", value=0.92, impact="positive", weight=0.35),
            ],
            confidence_interval=(310.0, 390.0),
            confidence_level=0.95,
            urgency="HIGH",
        )
        out = reasoning_card_html(data)

        assert "dss-reasoning-card" in out
        assert "dss-trust-algorithmic" in out
        assert "dss-trust-pill-algorithmic" in out
        assert "SKU-001" in out
        assert "350 шт" in out
        assert "280,000 ₽" in out
        assert "SUP-PREMIUM" in out
        assert "dss-impact-negative" in out
        assert "dss-impact-positive" in out
        assert "[310; 390] ед." in out

    def test_reasoning_card_heuristic_and_exploratory_tiers(self) -> None:
        """Heuristic and Exploratory tiers should map to their respective CSS classes."""
        d_heur = ReasoningCardData(
            sku_id="SKU-002",
            sku_name="Свеча зажигания",
            trust_tier="HEURISTIC",
            recommendation_title="Статистический заказ",
            recommended_quantity=100,
            selected_supplier="SUP-BASE",
            estimated_cost_rub=15000.0,
            rationale="Прогноз Holt-Winters.",
        )
        assert "dss-trust-heuristic" in reasoning_card_html(d_heur)

        d_expl = ReasoningCardData(
            sku_id="SKU-003",
            sku_name="Фильтр масляный",
            trust_tier="EXPLORATORY",
            recommendation_title="Сценарный заказ",
            recommended_quantity=50,
            selected_supplier="SUP-BASE",
            estimated_cost_rub=7500.0,
            rationale="Стресс-моделирование What-If.",
        )
        assert "dss-trust-exploratory" in reasoning_card_html(d_expl)


# ==============================================================================
# 5. What-If Controls Tests
# ==============================================================================

class TestWhatIfControls:
    """Test suite for What-If scenario controls container and state."""

    def test_what_if_scenario_state_defaults(self) -> None:
        """Default scenario state should conform to DSS normative parameters."""
        state = WhatIfScenarioState()
        assert state.service_level == 0.95
        assert state.volume_limit_m3 == 1200.0
        assert state.weight_limit_kg == 50000.0
        assert state.lead_time_shock_days == 0.0

    def test_render_what_if_controls_headless_fallback(self) -> None:
        """When streamlit is headless/unrendered, function returns clean state container."""
        state = render_what_if_controls(
            default_service_level=0.98,
            default_volume_m3=1400.0,
            default_weight_kg=60000.0,
            default_lead_shock=5.0,
        )
        assert state.service_level == 0.98
        assert state.volume_limit_m3 == 1400.0
        assert state.weight_limit_kg == 60000.0
        assert state.lead_time_shock_days == 5.0


# ==============================================================================
# 6. Plotly Theming Helper Tests
# ==============================================================================

class TestPlotlyTheming:
    """Test suite for Plotly figure theming and confidence fan chart generation."""

    def test_apply_plotly_theme(self) -> None:
        """Figure should receive transparent background, layout template, and margins."""
        fig = go.Figure(data=[go.Scatter(x=[1, 2, 3], y=[10, 20, 30])])
        themed = apply_plotly_theme(fig, theme_mode=ThemeMode.DARK, title="Тестовый график", height=400)

        assert themed.layout.paper_bgcolor == "rgba(0,0,0,0)"
        assert themed.layout.plot_bgcolor == "rgba(0,0,0,0)"
        assert themed.layout.title.text == "Тестовый график"
        assert themed.layout.height == 400

    def test_create_confidence_fan_chart(self) -> None:
        """Fan chart should contain history, upper bound, lower filled bound, and forecast."""
        dates = [f"2026-01-{i:02d}" for i in range(1, 11)]
        hist = [100, 110, 105, 115, 120]
        fc_dates = dates[5:]
        fc = [125, 130, 135, 140, 145]
        lower = [110, 112, 115, 118, 120]
        upper = [140, 148, 155, 162, 170]

        fig = create_confidence_fan_chart(
            x=dates[:5],
            y_history=hist,
            y_forecast=fc,
            y_lower=lower,
            y_upper=upper,
            x_forecast=fc_dates,
            title="Прогноз спроса",
            theme_mode=ThemeMode.DARK,
        )

        assert len(fig.data) == 4
        # Trace names
        trace_names = [t.name for t in fig.data]
        assert "История спроса" in trace_names
        assert "95% Доверительный интервал" in trace_names
        assert "Прогноз спроса" in trace_names
        # Lower bound fills to upper
        assert fig.data[2].fill == "tonexty"


# ==============================================================================
# 7. Global Dispatch Bar Tests
# ==============================================================================


class TestDispatchBar:
    """Test suite for neo-brutalist dispatch status ticker."""

    def test_dispatch_bar_html_structure(self) -> None:
        """Dispatch bar HTML must render items, tabular numbers, and alert styles."""
        bar_html = dispatch_bar_html(
            warehouse_id="WH-CENTRAL-01",
            volume_used_pct=92.5,
            weight_used_pct=65.0,
            critical_skus=3,
            reorder_skus=7,
            service_level=0.98,
        )
        assert "dss-dispatch-bar" in bar_html
        assert "WH-CENTRAL-01" in bar_html
        assert "92.5%" in bar_html
        assert "65.0%" in bar_html
        assert "[ 3 CRITICAL ]" in bar_html
        assert "7 SKU" in bar_html
        assert "98.0%" in bar_html
        assert "dss-alert" in bar_html
        assert "● ОНЛАЙН-КОНТРОЛЬ" in bar_html

    def test_dispatch_bar_nominal_status(self) -> None:
        """When metrics are below warning thresholds, alert class is not triggered on capacity."""
        bar_html = dispatch_bar_html(
            volume_used_pct=70.0,
            weight_used_pct=50.0,
            critical_skus=0,
        )
        assert "dss-dispatch-bar" in bar_html
        assert "[ 0 CRITICAL ]" in bar_html

    def test_render_dispatch_bar_safe_execution(self) -> None:
        """Calling render_dispatch_bar should execute without exceptions."""
        render_dispatch_bar()


# ==============================================================================
# 8. 9-Cell ABC/XYZ Matrix Tests
# ==============================================================================


class TestMatrixGrid:
    """Test suite for industrial 9-cell ABC/XYZ matrix presentation."""

    def test_matrix_grid_html_structure(self) -> None:
        """Matrix grid should render 9 cells with codes, counts, and capital stats."""
        cells = [
            MatrixCellData(code="AX", count=5, valuation_rub=1500000.0, capital_share_pct=45.2, label="Ключевой", status_theme="optimal"),
            MatrixCellData(code="AY", count=3, valuation_rub=800000.0, capital_share_pct=24.1, label="Буферный", status_theme="reorder"),
            MatrixCellData(code="AZ", count=2, valuation_rub=250000.0, capital_share_pct=7.5, label="Рисковый", status_theme="critical"),
        ]
        out = matrix_grid_html(cells, selected_code="AX")
        assert "dss-matrix-grid" in out
        assert "dss-matrix-card" in out
        assert "AX" in out
        assert "5 SKU" in out
        assert "1 500 000 ₽" in out
        assert "45.2%" in out
        assert "selected" in out
        assert "dss-matrix-theme-optimal" in out
        assert "dss-matrix-theme-reorder" in out
        assert "dss-matrix-theme-critical" in out

    def test_render_matrix_grid_execution(self) -> None:
        """Calling render_matrix_grid should execute safely."""
        cells = [
            MatrixCellData(code="AX", count=1, valuation_rub=100.0, capital_share_pct=10.0, label="Test"),
        ]
        render_matrix_grid(cells)

    def test_matrix_grid_html_empty_cells(self) -> None:
        """Matrix grid should render cleanly even with an empty cell sequence."""
        out = matrix_grid_html([], selected_code=None)
        assert '<div class="dss-matrix-grid">' in out
        assert "</div>" in out

    def test_matrix_grid_html_html_escaping(self) -> None:
        """Label and code strings must be safely HTML escaped."""
        cells = [
            MatrixCellData(
                code="A<X>",
                count=2,
                valuation_rub=1000.0,
                capital_share_pct=5.0,
                label="<Danger> & Warning",
            ),
        ]
        out = matrix_grid_html(cells)
        assert "<Danger>" not in out
        assert "&lt;Danger&gt; &amp; Warning" in out
        assert "A&lt;X&gt;" in out

