"""Headless integration test suite for Streamlit Decision Support System dashboard.

Uses streamlit.testing.v1.AppTest to execute the application in-memory
without requiring a web browser or display server.
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from inventory_dss.config import PACKAGE_ROOT

APP_PATH = PACKAGE_ROOT / "ui" / "app.py"


@pytest.fixture
def app_runner() -> AppTest:
    """Initialize an AppTest instance pointing to app.py."""
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    return at


class TestStreamlitUIHeadless:
    """Suite of headless UI integration tests covering all 5 screens and interactions."""

    def test_ui_initialization_and_layout(self, app_runner: AppTest):
        """Verify cold start, zero unhandled exceptions, and presence of navigation."""
        at = app_runner
        assert not at.exception, f"App threw unexpected exception: {at.exception}"
        assert len(at.sidebar.radio) > 0, "Sidebar navigation radio missing"
        assert at.sidebar.radio[0].value == "📊 Обзор и ключевые KPI"

    def test_screen_overview_kpis_and_gauges(self, app_runner: AppTest):
        """Verify Screen 1 (Executive Overview) renders macro metrics and gauges."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("📊 Обзор и ключевые KPI").run()
        assert not at.exception

        # Check macro metrics presence
        metric_labels = [m.label for m in at.metric]
        assert "Стоимость запасов" in metric_labels
        assert "Уровень сервиса (α)" in metric_labels
        assert "Дефицит (CRITICAL)" in metric_labels

        # Check Plotly charts (gauges + category bars + donut)
        assert len(at.get("plotly_chart")) >= 2, "Expected at least 2 Plotly charts on Overview screen"

    def test_screen_inventory_health_and_abc_xyz(self, app_runner: AppTest):
        """Verify Screen 2 (Inventory Health) filters and ABC/XYZ scatter plot."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("📦 Состояние запасов (ABC/XYZ)").run()
        assert not at.exception

        # Check filter selectors
        select_labels = [s.label for s in at.selectbox]
        assert "Категория" in select_labels
        assert "Класс ABC" in select_labels
        assert "Статус запаса" in select_labels

        # Check scatter matrix chart and data table
        assert len(at.get("plotly_chart")) >= 1
        assert len(at.dataframe) >= 1

    def test_screen_demand_forecasting_and_bands(self, app_runner: AppTest):
        """Verify Screen 3 (Demand Forecasting) SKU selector, horizon slider, and fan chart."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("📈 Прогнозирование спроса").run()
        assert not at.exception

        # Check forecast horizon slider
        assert len(at.slider) >= 1
        at.slider(key="forecast_h_slider").set_value(45).run()
        assert not at.exception

        # Check fan chart rendered
        assert len(at.get("plotly_chart")) >= 1

    def test_screen_suppliers_radar_and_mcda(self, app_runner: AppTest):
        """Verify Screen 4 (Supplier Radar) multi-criteria radar chart and decision tree."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("🏭 Оценка поставщиков").run()
        assert not at.exception

        # Verify radar chart rendered
        assert len(at.get("plotly_chart")) >= 1

        # Check suppliers leaderboard dataframe
        assert len(at.dataframe) >= 1

        # Check disruption sliders
        assert len(at.slider) >= 2

    def test_screen_replenishment_workbench_what_if_and_approval(self, app_runner: AppTest):
        """Verify Screen 5 (Replenishment Workbench) what-if sliders and order approval button."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("🎯 Рекомендации и What-If").run()
        assert not at.exception

        # 1. Adjust What-If Service Level Slider to 0.98
        at.slider(key="wb_service_level").set_value(0.98).run()
        assert not at.exception

        # 2. Check recommendation table
        assert len(at.dataframe) >= 1

        # 3. Click order approval button
        approve_btn = at.button(key="approve_orders_btn")
        approve_btn.click().run()
        assert not at.exception

        # Check success message appears
        assert len(at.success) >= 1
        assert "Успешно утверждено заказов" in at.success[0].value

    def test_capacity_stress_and_lead_time_shock(self, app_runner: AppTest):
        """Verify applying lead-time shock and capacity constraints does not crash UI."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("🎯 Рекомендации и What-If").run()

        # Apply 7-day shock
        at.slider(key="wb_lead_shock").set_value(7.0).run()
        assert not at.exception

        # Verify table still populates with emergency or critical statuses
        assert len(at.dataframe) >= 1

    def test_screen_design_system_showcase(self, app_runner: AppTest):
        """Verify Design System Showcase screen renders without exceptions and displays components."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("🎨 Дизайн-система (Showcase)").run()
        assert not at.exception
        # Verify Plotly charts on showcase screen (fan chart, gauges)
        assert len(at.get("plotly_chart")) >= 3
        # Verify WCAG compliance dataframe presence
        assert len(at.dataframe) >= 1
