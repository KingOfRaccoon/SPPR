"""Production UI Components for Inventory DSS (Milestone 2).

This module provides production-grade, typed visual components conforming to
the 3-Tier Design System tokens and WCAG 2.2 AA accessibility standards:
- 1. KPI Metric Card (`render_kpi_card`, `kpi_card_html`):
     Title, large tabular-nums value, directional delta indicators, and
     warehouse capacity micro-gauges / progress bars.
- 2. Status Badges & Chips (`render_status_badge`, `status_badge_html`):
     Pill badges for CRITICAL (with pulse dot animation), REORDER_NEEDED,
     OPTIMAL, EXCESS with accessible contrast and size variants.
- 3. Data Table Styling (`render_data_table`, `data_table_html`, `format_table_styler`):
     Tabular numerals right-aligned, status chips in cells, sticky headers,
     hover states, and pandas Styler integration.
- 4. Explainable AI Reasoning Card (`render_reasoning_card`, `reasoning_card_html`):
     Epistemic trust tier indicators (ALGORITHMIC, HEURISTIC, EXPLORATORY),
     decision factors breakdown, recommendation rationale, and confidence bounds.
- 5. What-If Interactive Controls (`render_what_if_controls`, `WhatIfScenarioState`):
     Card container wrapping scenario sliders and quick-stress presets.
- 6. Plotly Theming Helpers (`apply_plotly_theme`, `create_themed_figure`, `create_confidence_fan_chart`):
     Enforces `get_plotly_template(theme_mode)`, transparent backgrounds,
     subtle gridlines, and DSS colorways.
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]

try:
    import streamlit as st
except ImportError:
    st = None  # type: ignore[assignment]

try:
    import plotly.graph_objects as go
except ImportError:
    go = None  # type: ignore[assignment]

from inventory_dss.ui.theme import (
    EpistemicTrustTier,
    InventoryStatus,
    ThemeMode,
    get_plotly_template,
    get_theme,
)

# ---------------------------------------------------------------------------
# Component Scoped CSS Stylesheet
# ---------------------------------------------------------------------------

DSS_COMPONENTS_CSS = """
/* ==========================================================================
   DSS Milestone 2 Component Styles
   ========================================================================== */

/* 1. Micro-Gauge / Progress Indicator */
.dss-kpi-gauge {
    margin-top: 8px;
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.dss-gauge-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.75rem;
    color: var(--text-secondary);
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
}

.dss-gauge-track {
    width: 100%;
    height: 6px;
    background-color: var(--surface-layer-2);
    border-radius: 9999px;
    overflow: hidden;
    position: relative;
}

.dss-gauge-bar {
    height: 100%;
    border-radius: 9999px;
    transition: width 0.3s ease, background-color 0.3s ease;
}

.dss-gauge-optimal { background-color: #10B981; }
.dss-gauge-warning { background-color: #F59E0B; }
.dss-gauge-critical { background-color: #EF4444; }

/* 2. KPI Metric Delta Indicators */
.dss-kpi-delta {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 0.8125rem;
    font-weight: 500;
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    margin-top: 2px;
}

.dss-delta-positive { color: #10B981; }
.dss-delta-negative { color: #EF4444; }
.dss-delta-neutral { color: var(--text-secondary); }

.dss-kpi-caption {
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 2px;
}

/* 3. Badge Sizes */
.dss-badge-sm {
    padding: 2px 6px;
    font-size: 0.6875rem;
    gap: 4px;
}
.dss-badge-sm .dss-dot {
    width: 4px;
    height: 4px;
}
.dss-badge-md {
    padding: 3px 10px;
    font-size: 0.75rem;
    gap: 6px;
}
.dss-badge-lg {
    padding: 5px 14px;
    font-size: 0.875rem;
    gap: 8px;
}
.dss-badge-lg .dss-dot {
    width: 8px;
    height: 8px;
}

/* 4. Enhanced Data Table */
.dss-table-container {
    width: 100%;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    background-color: var(--surface-layer-1);
    box-shadow: var(--elevation-xs);
    overflow: hidden;
    margin: 8px 0;
}

.dss-table-scroll {
    width: 100%;
    overflow-x: auto;
    overflow-y: auto;
    max-height: 540px;
}

.dss-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8125rem;
    font-family: var(--font-sans);
    color: var(--text-primary);
    text-align: left;
}

.dss-th {
    background-color: var(--surface-layer-2);
    color: var(--text-secondary);
    font-weight: 600;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border-subtle);
    position: sticky;
    top: 0;
    z-index: 2;
    white-space: nowrap;
}

.dss-th-right { text-align: right; }
.dss-th-center { text-align: center; }
.dss-th-left { text-align: left; }

.dss-tr {
    border-bottom: 1px solid var(--border-subtle);
    transition: background-color 0.1s ease;
}

.dss-tr:last-child {
    border-bottom: none;
}

.dss-tr:hover {
    background-color: var(--surface-layer-2);
}

.dss-td {
    padding: 10px 14px;
    vertical-align: middle;
}

.dss-td-right { text-align: right; }
.dss-td-center { text-align: center; }
.dss-td-left { text-align: left; }

.dss-td-num {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum" 1, "zero" 1;
    text-align: right;
}

/* 5. Explainable AI Reasoning Card Sub-Elements */
.dss-reasoning-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    flex-wrap: wrap;
}

.dss-reasoning-title-group {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.dss-reasoning-sku {
    font-size: 0.75rem;
    font-family: var(--font-mono);
    color: var(--text-secondary);
    font-weight: 500;
}

.dss-reasoning-title {
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0;
}

.dss-reasoning-badges {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
}

.dss-trust-pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    line-height: 1.2;
}

.dss-trust-pill-algorithmic {
    background-color: rgba(16, 185, 129, 0.12);
    color: #10B981;
    border: 1px solid rgba(16, 185, 129, 0.3);
}

.dss-trust-pill-heuristic {
    background-color: rgba(99, 102, 241, 0.12);
    color: #818CF8;
    border: 1px solid rgba(99, 102, 241, 0.3);
}

.dss-trust-pill-exploratory {
    background-color: rgba(245, 158, 11, 0.12);
    color: #FBBF24;
    border: 1px solid rgba(245, 158, 11, 0.3);
}

.dss-urgency-pill {
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.6875rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.dss-urgency-high, .dss-urgency-critical {
    background-color: rgba(239, 68, 68, 0.15);
    color: #F87171;
}

.dss-urgency-normal, .dss-urgency-medium {
    background-color: var(--surface-layer-2);
    color: var(--text-secondary);
}

.dss-reasoning-action-box {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 8px;
    background-color: var(--surface-layer-2);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    padding: 10px 14px;
}

.dss-action-metric {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.dss-action-label {
    font-size: 0.75rem;
    color: var(--text-secondary);
}

.dss-action-value {
    font-size: 0.9375rem;
    font-weight: 600;
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    color: var(--text-primary);
}

.dss-factors-section {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.dss-factors-title {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.dss-factors-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}

.dss-factor-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background-color: var(--surface-layer-2);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    padding: 4px 8px;
    font-size: 0.75rem;
}

.dss-impact-positive { border-color: rgba(16, 185, 129, 0.4); }
.dss-impact-negative { border-color: rgba(239, 68, 68, 0.4); }

.dss-factor-impact-icon { font-weight: bold; }
.dss-impact-positive .dss-factor-impact-icon { color: #10B981; }
.dss-impact-negative .dss-factor-impact-icon { color: #EF4444; }

.dss-factor-name { color: var(--text-secondary); }
.dss-factor-value { font-weight: 600; font-family: var(--font-mono); color: var(--text-primary); }

.dss-factor-weight {
    font-size: 0.6875rem;
    color: var(--text-muted);
    background-color: rgba(255, 255, 255, 0.05);
    padding: 1px 4px;
    border-radius: 2px;
}

.dss-rationale-box {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    background-color: rgba(79, 70, 229, 0.05);
    border-left: 2px solid var(--brand-primary);
    padding: 8px 12px;
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}

.dss-rationale-quote-icon { font-size: 1.1rem; line-height: 1; }

.dss-rationale-text {
    margin: 0;
    font-size: 0.8125rem;
    line-height: 1.45;
    color: var(--text-primary);
}

.dss-reasoning-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.75rem;
    color: var(--text-secondary);
    border-top: 1px solid var(--border-subtle);
    padding-top: 8px;
    font-family: var(--font-mono);
}

/* 6. What-If Controls Container */
.dss-what-if-card {
    background-color: var(--surface-layer-1);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 16px;
    box-shadow: var(--elevation-sm);
    margin-bottom: 16px;
}

.dss-what-if-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}

.dss-what-if-title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 6px;
}

/* 7. 9-Cell ABC/XYZ Matrix Grid */
.dss-matrix-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin: 12px 0 18px 0;
}

.dss-matrix-card {
    background-color: var(--surface-layer-1);
    border: 2px solid var(--border-default);
    border-radius: var(--radius-sm);
    padding: 12px 14px;
    box-shadow: 3px 3px 0px rgba(0, 0, 0, 0.45);
    display: flex;
    flex-direction: column;
    gap: 6px;
    transition: transform 0.12s ease, box-shadow 0.12s ease, border-color 0.12s ease;
}

.dss-matrix-card:hover {
    transform: translate(-1px, -1px);
    box-shadow: 4px 4px 0px rgba(0, 0, 0, 0.6);
    border-color: var(--border-strong);
}

.dss-matrix-card.selected {
    border-color: var(--brand-primary);
    box-shadow: 4px 4px 0px var(--brand-primary);
}

.dss-matrix-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.dss-matrix-code {
    font-size: 1.15rem;
    font-weight: 800;
    font-family: var(--font-mono);
    letter-spacing: 0.05em;
    color: var(--text-primary);
}

.dss-matrix-badge {
    font-size: 0.6875rem;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 2px;
    border: 1px solid var(--border-subtle);
    background-color: var(--surface-layer-2);
    font-family: var(--font-sans);
    text-transform: uppercase;
}

.dss-matrix-count {
    font-size: 1.25rem;
    font-weight: 700;
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    color: var(--text-primary);
}

.dss-matrix-stat {
    font-size: 0.75rem;
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    color: var(--text-secondary);
}

.dss-matrix-theme-optimal {
    border-left: 4px solid #10B981 !important;
}
.dss-matrix-theme-reorder {
    border-left: 4px solid #F59E0B !important;
}
.dss-matrix-theme-critical {
    border-left: 4px solid #EF4444 !important;
}
.dss-matrix-theme-excess {
    border-left: 4px solid #8B5CF6 !important;
}
.dss-matrix-theme-neutral {
    border-left: 4px solid var(--border-strong) !important;
}
"""


def inject_components_css() -> str:
    """Idempotently inject component-scoped CSS rules into active Streamlit DOM."""
    if st is not None and hasattr(st, "markdown"):
        st.markdown(f"<style>{DSS_COMPONENTS_CSS}</style>", unsafe_allow_html=True)
    return DSS_COMPONENTS_CSS


# ---------------------------------------------------------------------------
# 1. KPI Metric Card
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KpiMetricData:
    """Data container for KPI metric cards with tabular values, deltas, and micro-gauges."""
    title: str
    value: str | int | float
    delta: str | None = None
    delta_color: Literal["normal", "inverse", "off"] = "normal"
    delta_direction: Literal["up", "down", "neutral"] | None = None
    unit: str | None = None
    caption: str | None = None
    # Micro-gauge capacity parameters
    gauge_value: float | None = None
    gauge_max: float | None = None
    gauge_unit: str | None = None
    gauge_label: str | None = None
    help_text: str | None = None


def kpi_card_html(metric: KpiMetricData, theme_mode: ThemeMode | str = ThemeMode.DARK) -> str:
    """Generate pure HTML markup for a KPI metric card conforming to DSS tokens."""
    title_escaped = html.escape(str(metric.title))

    # Format value
    if isinstance(metric.value, float):
        val_str = f"{metric.value:,.2f}"
    elif isinstance(metric.value, int):
        val_str = f"{metric.value:,d}"
    else:
        val_str = str(metric.value)
    val_escaped = html.escape(val_str)

    unit_html = (
        f' <span style="font-size:0.55em;color:var(--text-secondary);font-weight:normal;">'
        f'{html.escape(metric.unit)}</span>'
        if metric.unit
        else ""
    )

    # Delta formatting
    delta_html = ""
    if metric.delta:
        delta_str = str(metric.delta)
        direction = metric.delta_direction
        if direction is None:
            if delta_str.startswith("+"):
                direction = "up"
            elif delta_str.startswith("-"):
                direction = "down"
            else:
                direction = "neutral"

        if direction == "up":
            arrow = "&#9650; "
        elif direction == "down":
            arrow = "&#9660; "
        else:
            arrow = "&mdash; "

        # Color class calculation
        if metric.delta_color == "off":
            delta_class = "dss-delta-neutral"
        elif metric.delta_color == "inverse":
            delta_class = "dss-delta-negative" if direction == "up" else "dss-delta-positive"
        else:  # normal
            delta_class = "dss-delta-positive" if direction == "up" else "dss-delta-negative"

        delta_html = (
            f'<div class="dss-kpi-delta {delta_class}">'
            f'<span>{arrow}</span><span>{html.escape(delta_str)}</span>'
            f'</div>'
        )

    # Caption
    caption_html = (
        f'<div class="dss-kpi-caption">{html.escape(metric.caption)}</div>'
        if metric.caption
        else ""
    )

    # Micro-gauge capacity bar
    gauge_html = ""
    if metric.gauge_value is not None and metric.gauge_max is not None and metric.gauge_max > 0:
        pct = (metric.gauge_value / metric.gauge_max) * 100.0
        pct_clamped = min(100.0, max(0.0, pct))
        unit_lbl = f" {html.escape(metric.gauge_unit)}" if metric.gauge_unit else ""
        header_lbl = html.escape(metric.gauge_label) if metric.gauge_label else "Емкость"

        if pct < 80.0:
            bar_color_class = "dss-gauge-optimal"
        elif pct < 95.0:
            bar_color_class = "dss-gauge-warning"
        else:
            bar_color_class = "dss-gauge-critical"

        gauge_html = f"""
        <div class="dss-kpi-gauge">
            <div class="dss-gauge-header">
                <span>{header_lbl}</span>
                <span>{pct:.1f}% ({metric.gauge_value:,.1f}/{metric.gauge_max:,.1f}{unit_lbl})</span>
            </div>
            <div class="dss-gauge-track">
                <div class="dss-gauge-bar {bar_color_class}" style="width: {pct_clamped:.1f}%;"></div>
            </div>
        </div>
        """

    return f"""
    <div class="dss-kpi-card" role="region" aria-label="{title_escaped}">
        <div class="dss-kpi-title">{title_escaped}</div>
        <div class="dss-kpi-value">{val_escaped}{unit_html}</div>
        {delta_html}
        {caption_html}
        {gauge_html}
    </div>
    """.strip()


def render_kpi_card(
    metric: KpiMetricData,
    theme_mode: ThemeMode | str = ThemeMode.DARK,
) -> None:
    """Render a KPI metric card into Streamlit DOM."""
    markup = kpi_card_html(metric, theme_mode=theme_mode)
    if st is not None and hasattr(st, "markdown"):
        st.markdown(markup, unsafe_allow_html=True)


def render_kpi_grid(
    metrics: Sequence[KpiMetricData],
    columns: int = 4,
    theme_mode: ThemeMode | str = ThemeMode.DARK,
) -> None:
    """Render a responsive grid of KPI metric cards into Streamlit layout columns."""
    if not metrics:
        return
    cols = st.columns(columns) if (st is not None and hasattr(st, "columns")) else []
    for i, m in enumerate(metrics):
        if cols:
            with cols[i % columns]:
                render_kpi_card(m, theme_mode=theme_mode)
        else:
            render_kpi_card(m, theme_mode=theme_mode)


# ---------------------------------------------------------------------------
# 2. Status Badges & Chips
# ---------------------------------------------------------------------------

DSS_STATUS_LABELS: dict[str, str] = {
    "CRITICAL": "ДЕФИЦИТ",
    "REORDER_NEEDED": "К ЗАКАЗУ",
    "OPTIMAL": "НОРМА",
    "EXCESS": "ИЗБЫТОК",
}


@dataclass(frozen=True)
class StatusBadgeData:
    """Configuration for status pills and chips."""
    status: InventoryStatus | str
    label: str | None = None
    pulse: bool | None = None
    size: Literal["sm", "md", "lg"] = "md"
    count: int | None = None


def status_badge_html(
    status: InventoryStatus | str,
    label: str | None = None,
    pulse: bool | None = None,
    size: Literal["sm", "md", "lg"] = "md",
    count: int | None = None,
) -> str:
    """Generate pure HTML for a DSS status badge/chip with dot and accessible contrast."""
    raw_status = status.value if isinstance(status, InventoryStatus) else str(status)
    normalized = raw_status.upper().strip()

    status_key_map = {
        "CRITICAL": "critical",
        "REORDER_NEEDED": "reorder",
        "REORDER": "reorder",
        "OPTIMAL": "optimal",
        "NORMAL": "optimal",
        "EXCESS": "excess",
        "OVERSTOCK": "excess",
    }
    status_suffix = status_key_map.get(normalized, "optimal")

    # Determine default label
    if label is None:
        display_label = DSS_STATUS_LABELS.get(normalized, normalized)
    else:
        display_label = label

    # Pulse animation: default True for CRITICAL, False for others
    if pulse is None:
        is_pulse = status_suffix == "critical"
    else:
        is_pulse = bool(pulse)

    pulse_class = " dss-dot-critical" if (is_pulse and status_suffix == "critical") else ""
    count_html = (
        f' <span style="opacity:0.8;font-size:0.9em;">({count})</span>'
        if count is not None
        else ""
    )

    return (
        f'<span class="dss-badge dss-badge-{status_suffix} dss-badge-{size}" role="status">'
        f'<span class="dss-dot dss-dot-{status_suffix}{pulse_class}"></span>'
        f'<span class="dss-badge-label">{html.escape(display_label)}</span>'
        f"{count_html}"
        f"</span>"
    )


def render_status_badge(
    status: InventoryStatus | str,
    label: str | None = None,
    pulse: bool | None = None,
    size: Literal["sm", "md", "lg"] = "md",
    count: int | None = None,
) -> None:
    """Render a status badge directly into Streamlit DOM."""
    markup = status_badge_html(status=status, label=label, pulse=pulse, size=size, count=count)
    if st is not None and hasattr(st, "markdown"):
        st.markdown(markup, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 3. Data Table Styling
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ColumnConfig:
    """Formatting metadata for table columns."""
    key: str
    label: str | None = None
    align: Literal["left", "center", "right"] = "left"
    is_numeric: bool = False
    format_spec: str | None = None  # e.g. "{:,.2f} ₽" or "{:.1f}%"
    is_status: bool = False


def data_table_html(
    df: Any,
    columns: Sequence[ColumnConfig] | None = None,
    status_column: str | None = "status",
    max_height_px: int = 520,
) -> str:
    """Render a DataFrame as a high-density, accessible HTML table with tabular numbers and status chips."""
    if df is None or (hasattr(df, "empty") and df.empty):
        return (
            '<div class="dss-table-container" style="padding: 24px; text-align: center;'
            ' color: var(--text-muted);">Нет данных для отображения</div>'
        )

    # Derive column configs if not provided
    if columns is None:
        col_configs: list[ColumnConfig] = []
        for col_name in df.columns:
            str_col = str(col_name)
            is_stat = (status_column is not None) and (str_col.lower() == status_column.lower())
            is_num = False
            align: Literal["left", "center", "right"] = "left"

            if pd is not None and str_col in df.columns:
                is_num = pd.api.types.is_numeric_dtype(df[str_col])
                if is_num:
                    align = "right"

            col_configs.append(
                ColumnConfig(
                    key=str_col,
                    label=str_col,
                    align=align,
                    is_numeric=is_num,
                    is_status=is_stat,
                )
            )
    else:
        col_configs = list(columns)

    # Build header HTML
    th_items = []
    for cfg in col_configs:
        align_class = f"dss-th-{cfg.align}"
        lbl = html.escape(cfg.label or cfg.key)
        th_items.append(f'<th class="dss-th {align_class}">{lbl}</th>')
    thead_html = f"<tr>{''.join(th_items)}</tr>"

    # Build rows HTML
    tr_items = []
    records = df.to_dict(orient="records") if hasattr(df, "to_dict") else []
    for row in records:
        td_items = []
        for cfg in col_configs:
            raw_val = row.get(cfg.key, "")
            align_class = f"dss-td-{cfg.align}"
            num_class = " dss-td-num" if cfg.is_numeric else ""

            if cfg.is_status and raw_val:
                cell_content = status_badge_html(str(raw_val), size="sm")
            elif cfg.is_numeric and isinstance(raw_val, (int, float)):
                if cfg.format_spec:
                    cell_content = html.escape(cfg.format_spec.format(raw_val))
                elif isinstance(raw_val, float):
                    cell_content = html.escape(f"{raw_val:,.2f}")
                else:
                    cell_content = html.escape(f"{raw_val:,d}")
            else:
                cell_content = html.escape(str(raw_val) if raw_val is not None else "")

            td_items.append(f'<td class="dss-td {align_class}{num_class}">{cell_content}</td>')
        tr_items.append(f'<tr class="dss-tr">{"".join(td_items)}</tr>')

    tbody_html = "".join(tr_items)
    scroll_style = f"max-height: {max_height_px}px;" if max_height_px else ""

    return f"""
    <div class="dss-table-container">
        <div class="dss-table-scroll" style="{scroll_style}">
            <table class="dss-table">
                <thead>{thead_html}</thead>
                <tbody>{tbody_html}</tbody>
            </table>
        </div>
    </div>
    """.strip()


def render_data_table(
    df: Any,
    columns: Sequence[ColumnConfig] | None = None,
    status_column: str | None = "status",
    max_height_px: int = 520,
) -> None:
    """Render the high-density styled data table into Streamlit DOM."""
    markup = data_table_html(
        df=df,
        columns=columns,
        status_column=status_column,
        max_height_px=max_height_px,
    )
    if st is not None and hasattr(st, "markdown"):
        st.markdown(markup, unsafe_allow_html=True)


def format_table_styler(
    df: Any,
    status_column: str = "status",
    numeric_formats: dict[str, str] | None = None,
    theme_mode: ThemeMode | str = ThemeMode.DARK,
) -> Any:
    """Enhance a pandas DataFrame via Styler for direct display via `st.dataframe`."""
    if df is None or not hasattr(df, "style"):
        return df

    theme = get_theme(theme_mode)
    styler = df.style

    # Right align & tabular numerals on numeric columns
    if pd is not None:
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if numeric_cols:
            styler = styler.set_properties(
                subset=numeric_cols,
                **{
                    "text-align": "right",
                    "font-variant-numeric": "tabular-nums",
                    "font-family": theme.typography.font_mono,
                },
            )

    # Format specified columns
    if numeric_formats:
        for col, fmt in numeric_formats.items():
            if col in df.columns:
                styler = styler.format({col: fmt})

    # Status column soft background coloring
    if status_column in df.columns:
        status_bg_map = {
            "CRITICAL": f"background-color: {theme.status_critical.bg}; color: {theme.status_critical.fg}; font-weight: 600;",
            "REORDER_NEEDED": f"background-color: {theme.status_reorder.bg}; color: {theme.status_reorder.fg}; font-weight: 600;",
            "OPTIMAL": f"background-color: {theme.status_optimal.bg}; color: {theme.status_optimal.fg}; font-weight: 600;",
            "EXCESS": f"background-color: {theme.status_excess.bg}; color: {theme.status_excess.fg}; font-weight: 600;",
        }

        def _apply_status_color(val: Any) -> str:
            if not isinstance(val, str):
                return ""
            return status_bg_map.get(val.upper().strip(), "")

        styler = styler.map(_apply_status_color, subset=[status_column])

    return styler


# ---------------------------------------------------------------------------
# 4. Explainable AI Reasoning Card
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DecisionFactor:
    """Individual algorithmic or heuristic driver influencing the recommendation."""
    name: str
    value: str | float | int
    impact: Literal["positive", "negative", "neutral"] = "neutral"
    weight: float | None = None
    description: str | None = None


@dataclass(frozen=True)
class ReasoningCardData:
    """Comprehensive explainability dataset supporting executive decision transparency."""
    sku_id: str
    sku_name: str
    trust_tier: EpistemicTrustTier | str
    recommendation_title: str
    recommended_quantity: float | int
    selected_supplier: str
    estimated_cost_rub: float
    rationale: str
    factors: list[DecisionFactor] = field(default_factory=list)
    confidence_interval: tuple[float, float] | None = None
    confidence_level: float = 0.95
    urgency: str = "NORMAL"
    stockout_risk_reduction: str | None = None


def reasoning_card_html(
    data: ReasoningCardData,
    theme_mode: ThemeMode | str = ThemeMode.DARK,
) -> str:
    """Generate pure HTML markup for an Explainable AI recommendation card."""
    raw_tier = data.trust_tier.value if isinstance(data.trust_tier, EpistemicTrustTier) else str(data.trust_tier)
    tier_upper = raw_tier.upper().strip()

    tier_classes = {
        "ALGORITHMIC": ("dss-trust-algorithmic", "dss-trust-pill-algorithmic", "🛡️ Доказано (KKT / EOQ)"),
        "HEURISTIC": ("dss-trust-heuristic", "dss-trust-pill-heuristic", "⚖️ Эвристика (TOPSIS / HW)"),
        "EXPLORATORY": ("dss-trust-exploratory", "dss-trust-pill-exploratory", "🧪 Симуляция (What-If / LLM)"),
    }
    tier_card_class, tier_pill_class, default_tier_lbl = tier_classes.get(
        tier_upper, ("dss-trust-heuristic", "dss-trust-pill-heuristic", tier_upper)
    )

    # Urgency class
    urgency_upper = data.urgency.upper()
    urgency_class = (
        "dss-urgency-high"
        if urgency_upper in ("CRITICAL", "HIGH", "EMERGENCY")
        else "dss-urgency-normal"
    )

    # Decision factors chips
    factors_html_list = []
    for f in data.factors:
        impact_icon = "+" if f.impact == "positive" else ("-" if f.impact == "negative" else "&bull;")
        weight_html = (
            f'<span class="dss-factor-weight">{f.weight * 100:.0f}%</span>'
            if f.weight is not None
            else ""
        )
        f_val_str = f"{f.value:,.1f}" if isinstance(f.value, float) else str(f.value)
        factors_html_list.append(
            f'<div class="dss-factor-chip dss-impact-{f.impact}">'
            f'<span class="dss-factor-impact-icon">{impact_icon}</span>'
            f'<span class="dss-factor-name">{html.escape(f.name)}:</span>'
            f'<span class="dss-factor-value">{html.escape(f_val_str)}</span>'
            f'{weight_html}'
            f'</div>'
        )
    factors_grid_html = "".join(factors_html_list)

    factors_section = (
        f"""
        <div class="dss-factors-section">
            <div class="dss-factors-title">Ключевые факторы решения (MCDA / Optimization Drivers):</div>
            <div class="dss-factors-grid">{factors_grid_html}</div>
        </div>
        """
        if factors_html_list
        else ""
    )

    # Confidence interval & footer
    ci_html = ""
    if data.confidence_interval:
        low, high = data.confidence_interval
        ci_html = (
            f'<span>Доверительный интервал ({data.confidence_level * 100:.0f}%): '
            f'<strong>[{low:,.0f}; {high:,.0f}] ед.</strong></span>'
        )

    risk_reduction_html = (
        f'<span>Снижение риска дефицита: <strong>{html.escape(data.stockout_risk_reduction)}</strong></span>'
        if data.stockout_risk_reduction
        else ""
    )

    footer_section = (
        f"""
        <div class="dss-reasoning-footer">
            {ci_html}
            {risk_reduction_html}
        </div>
        """
        if (ci_html or risk_reduction_html)
        else ""
    )

    # Format numeric quantities
    qty_str = (
        f"{data.recommended_quantity:,.0f}"
        if isinstance(data.recommended_quantity, (int, float))
        else str(data.recommended_quantity)
    )

    return f"""
    <div class="dss-reasoning-card {tier_card_class}" role="article">
        <div class="dss-reasoning-header">
            <div class="dss-reasoning-title-group">
                <span class="dss-reasoning-sku">{html.escape(data.sku_id)} &bull; {html.escape(data.sku_name)}</span>
                <h4 class="dss-reasoning-title">{html.escape(data.recommendation_title)}</h4>
            </div>
            <div class="dss-reasoning-badges">
                <span class="dss-trust-pill {tier_pill_class}">{html.escape(default_tier_lbl)}</span>
                <span class="dss-urgency-pill {urgency_class}">{html.escape(data.urgency)}</span>
            </div>
        </div>

        <div class="dss-reasoning-action-box">
            <div class="dss-action-metric">
                <span class="dss-action-label">К заказу:</span>
                <span class="dss-action-value">{html.escape(qty_str)} шт</span>
            </div>
            <div class="dss-action-metric">
                <span class="dss-action-label">Поставщик:</span>
                <span class="dss-action-value">{html.escape(data.selected_supplier)}</span>
            </div>
            <div class="dss-action-metric">
                <span class="dss-action-label">Сумма заказа:</span>
                <span class="dss-action-value">{data.estimated_cost_rub:,.0f} ₽</span>
            </div>
        </div>

        {factors_section}

        <div class="dss-rationale-box">
            <span class="dss-rationale-quote-icon">💡</span>
            <p class="dss-rationale-text">{html.escape(data.rationale)}</p>
        </div>

        {footer_section}
    </div>
    """.strip()


def render_reasoning_card(
    data: ReasoningCardData,
    theme_mode: ThemeMode | str = ThemeMode.DARK,
) -> None:
    """Render the Explainable AI reasoning card into Streamlit DOM."""
    markup = reasoning_card_html(data, theme_mode=theme_mode)
    if st is not None and hasattr(st, "markdown"):
        st.markdown(markup, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 5. What-If Interactive Controls
# ---------------------------------------------------------------------------

@dataclass
class WhatIfScenarioState:
    """Active parameter state resulting from What-If modeling controls."""
    service_level: float = 0.95
    volume_limit_m3: float = 1200.0
    weight_limit_kg: float = 50000.0
    lead_time_shock_days: float = 0.0
    active_preset: str = "custom"


def render_what_if_controls(
    default_service_level: float = 0.95,
    default_volume_m3: float = 1200.0,
    default_weight_kg: float = 50000.0,
    default_lead_shock: float = 0.0,
    key_prefix: str = "wb",
) -> WhatIfScenarioState:
    """Render interactive What-If scenario sliders and stress toggles inside a DSS card container."""
    if st is None:
        return WhatIfScenarioState(
            service_level=default_service_level,
            volume_limit_m3=default_volume_m3,
            weight_limit_kg=default_weight_kg,
            lead_time_shock_days=default_lead_shock,
        )

    inject_components_css()

    with st.container():
        st.markdown(
            """
            <div class="dss-what-if-header">
                <div class="dss-what-if-title">
                    <span>⚙️</span> Параметры What-If моделирования (Стресс-тестирование цепи поставок)
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 4 Sliders with exact keys matching existing test suites
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            service_level = st.slider(
                "Уровень сервиса (α)",
                min_value=0.90,
                max_value=0.999,
                value=float(default_service_level),
                step=0.005,
                key=f"{key_prefix}_service_level",
                help="Вероятность непрерывного удовлетворения спроса без дефицита",
            )
        with c2:
            vol_limit = st.slider(
                "Лимит объема склада (м³)",
                min_value=500.0,
                max_value=2500.0,
                value=float(default_volume_m3),
                step=50.0,
                key=f"{key_prefix}_vol_limit",
                help="Предельная полезная кубатура складского комплекса",
            )
        with c3:
            wt_limit = st.slider(
                "Лимит веса склада (кг)",
                min_value=20000.0,
                max_value=120000.0,
                value=float(default_weight_kg),
                step=5000.0,
                key=f"{key_prefix}_wt_limit",
                help="Максимальная несущая способность стеллажных секций",
            )
        with c4:
            lead_shock = st.slider(
                "Шок задержки поставок (дней)",
                min_value=0.0,
                max_value=14.0,
                value=float(default_lead_shock),
                step=1.0,
                key=f"{key_prefix}_lead_shock",
                help="Искусственный сдвиг сроков выполнения заказов поставщиками",
            )

    return WhatIfScenarioState(
        service_level=float(service_level),
        volume_limit_m3=float(vol_limit),
        weight_limit_kg=float(wt_limit),
        lead_time_shock_days=float(lead_shock),
    )


# ---------------------------------------------------------------------------
# 6. Plotly Theming Helpers
# ---------------------------------------------------------------------------

def apply_plotly_theme(
    fig: Any,
    theme_mode: ThemeMode | str = ThemeMode.DARK,
    title: str | None = None,
    height: int | None = None,
    show_legend: bool = True,
) -> Any:
    """Apply unified DSS tokens, transparent background, margins, and typography to any Plotly Figure."""
    if fig is None or go is None:
        return fig

    theme = get_theme(theme_mode)
    template = get_plotly_template(theme.mode)

    fig.update_layout(template=template)
    layout_updates: dict[str, Any] = {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "margin": {"l": 40, "r": 20, "t": 40 if title else 20, "b": 40},
        "showlegend": show_legend,
    }
    if title:
        layout_updates["title"] = {
            "text": title,
            "font": {
                "family": theme.typography.font_sans,
                "color": theme.text.primary,
                "size": 15,
            },
        }
    if height:
        layout_updates["height"] = height

    fig.update_layout(**layout_updates)
    return fig


def create_themed_figure(
    data: Any = None,
    layout: Any = None,
    theme_mode: ThemeMode | str = ThemeMode.DARK,
    title: str | None = None,
    height: int | None = None,
) -> Any:
    """Create a new Plotly Figure pre-configured with DSS theme tokens."""
    if go is None:
        raise ImportError("Plotly is required to construct a themed figure.")

    fig = go.Figure(data=data, layout=layout)
    return apply_plotly_theme(fig, theme_mode=theme_mode, title=title, height=height)


def create_confidence_fan_chart(
    x: Sequence[Any],
    y_history: Sequence[float | int],
    y_forecast: Sequence[float | int],
    y_lower: Sequence[float | int],
    y_upper: Sequence[float | int],
    x_forecast: Sequence[Any] | None = None,
    title: str = "Прогноз спроса с доверительным интервалом",
    theme_mode: ThemeMode | str = ThemeMode.DARK,
    height: int = 380,
) -> Any:
    """Construct an executive fan chart with alpha confidence bands and transparent theme styling."""
    if go is None:
        raise ImportError("Plotly is required to construct confidence fan charts.")

    theme = get_theme(theme_mode)
    fig = go.Figure()

    # Historical demand trace
    fig.add_trace(
        go.Scatter(
            x=list(x),
            y=list(y_history),
            mode="lines",
            name="История спроса",
            line={"color": theme.text.secondary, "width": 1.8},
        )
    )

    fc_x = list(x_forecast) if x_forecast is not None else list(x)[-len(y_forecast):]

    # Upper bound (invisible fill baseline)
    fig.add_trace(
        go.Scatter(
            x=fc_x,
            y=list(y_upper),
            mode="lines",
            name="Верхняя граница (95% ДИ)",
            line={"width": 0},
            showlegend=False,
            hoverinfo="skip",
        )
    )

    # Lower bound + fill to upper
    fig.add_trace(
        go.Scatter(
            x=fc_x,
            y=list(y_lower),
            mode="lines",
            name="95% Доверительный интервал",
            line={"width": 0},
            fill="tonexty",
            fillcolor=theme.components.chart.confidence_band_fill,
            hoverinfo="skip",
        )
    )

    # Forecast mean line
    fig.add_trace(
        go.Scatter(
            x=fc_x,
            y=list(y_forecast),
            mode="lines+markers",
            name="Прогноз спроса",
            line={"color": theme.brand_primary, "width": 2.5, "dash": "dash"},
            marker={"size": 5, "color": theme.brand_primary},
        )
    )

    return apply_plotly_theme(fig, theme_mode=theme_mode, title=title, height=height)


def render_themed_plotly_chart(
    fig: Any,
    theme_mode: ThemeMode | str = ThemeMode.DARK,
    use_container_width: bool = True,
    key: str | None = None,
) -> None:
    """Render a themed Plotly figure into Streamlit with responsive configuration."""
    if fig is None or st is None:
        return
    apply_plotly_theme(fig, theme_mode=theme_mode)
    config = {
        "displayModeBar": "hover",
        "displaylogo": False,
        "responsive": True,
        "modeBarButtonsToRemove": ["lasso2d", "select2d"],
    }
    st.plotly_chart(
        fig,
        use_container_width=use_container_width,
        config=config,
        key=key,
    )


# ---------------------------------------------------------------------------
# 7. Global Top Dispatch Ticker Bar (Industrial Neo-Brutalism)
# ---------------------------------------------------------------------------


def dispatch_bar_html(
    warehouse_id: str = "WH-CENTRAL-01",
    volume_used_pct: float = 78.4,
    weight_used_pct: float = 62.1,
    critical_skus: int = 2,
    reorder_skus: int = 6,
    service_level: float = 0.95,
) -> str:
    """Generate industrial neo-brutalist dispatch status bar HTML."""
    vol_cls = "dss-alert" if volume_used_pct >= 90.0 else "dss-ok"
    wt_cls = "dss-alert" if weight_used_pct >= 90.0 else "dss-ok"
    crit_cls = "dss-alert" if critical_skus > 0 else "dss-ok"

    return f"""<div class="dss-dispatch-bar">
    <div class="dss-dispatch-item">
        <span class="dss-dispatch-lbl">КОНТУР:</span>
        <span class="dss-dispatch-val">{html.escape(warehouse_id)}</span>
    </div>
    <div class="dss-dispatch-item">
        <span class="dss-dispatch-lbl">ОБЪЕМ V:</span>
        <span class="dss-dispatch-val {vol_cls}">{volume_used_pct:.1f}%</span>
    </div>
    <div class="dss-dispatch-item">
        <span class="dss-dispatch-lbl">НАГРУЗКА W:</span>
        <span class="dss-dispatch-val {wt_cls}">{weight_used_pct:.1f}%</span>
    </div>
    <div class="dss-dispatch-item">
        <span class="dss-dispatch-lbl">ДЕФИЦИТ:</span>
        <span class="dss-dispatch-val {crit_cls}">[ {critical_skus} CRITICAL ]</span>
    </div>
    <div class="dss-dispatch-item">
        <span class="dss-dispatch-lbl">К ЗАКАЗУ:</span>
        <span class="dss-dispatch-val">{reorder_skus} SKU</span>
    </div>
    <div class="dss-dispatch-item">
        <span class="dss-dispatch-lbl">СЕРВИС α:</span>
        <span class="dss-dispatch-val">{service_level * 100:.1f}%</span>
    </div>
    <div class="dss-dispatch-item">
        <span class="dss-dispatch-lbl">РЕЖИМ:</span>
        <span class="dss-dispatch-val dss-ok">● ОНЛАЙН-КОНТРОЛЬ</span>
    </div>
</div>"""


def render_dispatch_bar(
    warehouse_id: str = "WH-CENTRAL-01",
    volume_used_pct: float = 78.4,
    weight_used_pct: float = 62.1,
    critical_skus: int = 2,
    reorder_skus: int = 6,
    service_level: float = 0.95,
) -> None:
    """Render the global neo-brutalist dispatch ticker bar in Streamlit."""
    if st is None:
        return
    bar_code = dispatch_bar_html(
        warehouse_id=warehouse_id,
        volume_used_pct=volume_used_pct,
        weight_used_pct=weight_used_pct,
        critical_skus=critical_skus,
        reorder_skus=reorder_skus,
        service_level=service_level,
    )
    st.markdown(bar_code, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 8. 9-Cell ABC/XYZ Matrix Grid
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MatrixCellData:
    """Data container for an ABC/XYZ matrix quadrant cell."""

    code: str  # e.g., "AX", "AY", "AZ", "BX", "BY", "BZ", "CX", "CY", "CZ"
    count: int
    valuation_rub: float
    capital_share_pct: float
    label: str
    status_theme: Literal["optimal", "reorder", "critical", "excess", "neutral"] = "neutral"


def matrix_grid_html(
    cells: Sequence[MatrixCellData],
    selected_code: str | None = None,
    theme_mode: ThemeMode | str = ThemeMode.DARK,
) -> str:
    """Generate industrial neo-brutalist 3x3 ABC/XYZ matrix grid HTML."""
    cards_html = []
    for c in cells:
        theme_cls = f"dss-matrix-theme-{c.status_theme}"
        sel_cls = " selected" if selected_code and selected_code.upper() == c.code.upper() else ""
        escaped_code = html.escape(c.code)
        escaped_label = html.escape(c.label)
        val_str = f"{c.valuation_rub:,.0f} ₽".replace(",", " ")
        cards_html.append(
            f"""    <div class="dss-matrix-card {theme_cls}{sel_cls}">
        <div class="dss-matrix-header">
            <span class="dss-matrix-code">{escaped_code}</span>
            <span class="dss-matrix-badge">{escaped_label}</span>
        </div>
        <div class="dss-matrix-count">{c.count} SKU</div>
        <div class="dss-matrix-stat">
            Капитал: <b>{val_str}</b> ({c.capital_share_pct:.1f}%)
        </div>
    </div>"""
        )

    return f"""<div class="dss-matrix-grid">
{"\n".join(cards_html)}
</div>"""


def render_matrix_grid(
    cells: Sequence[MatrixCellData],
    selected_code: str | None = None,
    theme_mode: ThemeMode | str = ThemeMode.DARK,
) -> None:
    """Render 9-cell ABC/XYZ matrix component in Streamlit."""
    if st is None:
        return
    inject_components_css()
    st.markdown(matrix_grid_html(cells, selected_code=selected_code, theme_mode=theme_mode), unsafe_allow_html=True)


__all__ = [
    "DSS_COMPONENTS_CSS",
    "DSS_STATUS_LABELS",
    "ColumnConfig",
    "DecisionFactor",
    "KpiMetricData",
    "MatrixCellData",
    "ReasoningCardData",
    "StatusBadgeData",
    "WhatIfScenarioState",
    "apply_plotly_theme",
    "create_confidence_fan_chart",
    "create_themed_figure",
    "data_table_html",
    "dispatch_bar_html",
    "format_table_styler",
    "inject_components_css",
    "kpi_card_html",
    "matrix_grid_html",
    "reasoning_card_html",
    "render_data_table",
    "render_dispatch_bar",
    "render_kpi_card",
    "render_kpi_grid",
    "render_matrix_grid",
    "render_reasoning_card",
    "render_status_badge",
    "render_themed_plotly_chart",
    "render_what_if_controls",
    "status_badge_html",
]
