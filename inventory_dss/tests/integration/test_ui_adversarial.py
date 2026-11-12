"""Adversarial stress and boundary integration test suite for Streamlit DSS UI.

Executes headless verification using streamlit.testing.v1.AppTest across:
1. Rapid parameter perturbations and slider shocks.
2. Supply chain disruption (lead-time shock up to 14 days).
3. Extreme warehouse capacity restrictions and contention warnings.
4. Complete order approval lifecycle (approve, double approve, clear).
5. Exhaustive inventory filtering, including empty result-set boundaries.
6. Multi-model forecasting horizons and history window selections.
7. Supplier MCDA evaluation methods and decision-tree risk boundaries.
8. Cross-screen reactivity and state mutation persistence.
9. Export serialization and button integrity.
"""

from __future__ import annotations

import io
import json

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from inventory_dss.config import PACKAGE_ROOT
from inventory_dss.ui.utils import calculate_dss_recommendations

APP_PATH = PACKAGE_ROOT / "ui" / "app.py"
DEFAULT_TIMEOUT = 30


@pytest.fixture
def app_runner() -> AppTest:
    """Initialize a fresh headless AppTest runner with 30s timeout."""
    at = AppTest.from_file(str(APP_PATH), default_timeout=DEFAULT_TIMEOUT)
    at.run()
    return at


class TestHeadlessUIParameterPerturbation:
    """Stress tests rapid parameter variations and supply chain shocks."""

    def test_rapid_service_level_slider_sweep(self, app_runner: AppTest):
        """Stress rapid perturbation of service level slider (0.90 -> 0.999 -> 0.90)."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("🎯 Рекомендации и What-If").run()
        assert not at.exception

        sl_slider = at.slider(key="wb_service_level")
        levels = [0.90, 0.95, 0.98, 0.995, 0.999, 0.90]

        for sl in levels:
            sl_slider.set_value(sl).run()
            assert not at.exception, f"Crash when setting service level to {sl}"

            # Verify metrics update
            metrics = {m.label: m.value for m in at.metric}
            assert "Позиций к заказу" in metrics
            assert "Сумма заказа" in metrics

            # Recommendation table must remain populated
            assert len(at.dataframe) >= 1
            rec_df = at.dataframe[0].value
            assert len(rec_df) == 25

        # Check session state updated
        assert at.session_state["service_level"] == 0.90

    def test_supplier_lead_time_shock_sweep(self, app_runner: AppTest):
        """Stress lead-time shock up to 14 days and check critical item escalation."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("🎯 Рекомендации и What-If").run()

        # Step 1: Base lead time (0 shock)
        at.slider(key="wb_lead_shock").set_value(0.0).run()
        assert not at.exception
        base_df = at.dataframe[0].value
        base_critical = len(base_df[base_df["Статус"] == "CRITICAL"])

        # Step 2: Severe 14-day supply shock
        at.slider(key="wb_lead_shock").set_value(14.0).run()
        assert not at.exception
        shock_df = at.dataframe[0].value
        shock_critical = len(shock_df[shock_df["Статус"] == "CRITICAL"])

        # Under a 14-day delay shock, critical items must increase or remain high
        assert shock_critical >= base_critical
        assert shock_critical >= 7

        # Step 3: Check emergency supplier assignment
        critical_rows = shock_df[shock_df["Статус"] == "CRITICAL"]
        suppliers_assigned = critical_rows["Поставщик"].tolist()
        assert any("Экспресс" in s or "Северо-Запад" in s for s in suppliers_assigned)

        # Step 4: Reset back to 0 shock
        at.slider(key="wb_lead_shock").set_value(0.0).run()
        assert not at.exception

    def test_extreme_warehouse_capacity_clamp_and_warning(self, app_runner: AppTest):
        """Test minimum allowed warehouse capacity triggering warning banner."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("🎯 Рекомендации и What-If").run()

        # Clamp volume to 500 m3 and weight to 20,000 kg
        at.slider(key="wb_vol_limit").set_value(500.0)
        at.slider(key="wb_wt_limit").set_value(20000.0)
        # Apply 14d shock to balloon the order batch
        at.slider(key="wb_lead_shock").set_value(14.0)
        at.slider(key="wb_service_level").set_value(0.999)
        at.run()
        assert not at.exception

        # Capacity warning must be triggered
        assert len(at.warning) >= 1
        warning_text = at.warning[0].value
        assert "превышает свободную вместимость" in warning_text or "KKT" in warning_text


class TestHeadlessUIOrderApprovalLifecycle:
    """Stress tests order approval, repeat approval, and reset actions."""

    def test_order_approval_lifecycle_and_clearing(self, app_runner: AppTest):
        """Test full approval lifecycle: approve -> check state -> clear -> verify clean."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("🎯 Рекомендации и What-If").run()
        assert not at.exception

        # Initial state: 0 approved orders
        assert len(at.session_state["approved_orders"]) == 0

        # Approve orders
        at.button(key="approve_orders_btn").click().run()
        assert not at.exception
        assert len(at.success) >= 1
        assert "Успешно утверждено заказов" in at.success[0].value

        approved = at.session_state["approved_orders"]
        assert len(approved) >= 1
        first_order = approved[0]
        assert "order_id" in first_order
        assert first_order["status"] == "APPROVED"
        assert first_order["quantity"] > 0
        assert first_order["total_cost"] > 0

        # Check clear button presence and execution
        assert "clear_orders_btn" in [b.key for b in at.button]
        at.button(key="clear_orders_btn").click().run()
        assert not at.exception
        assert len(at.session_state["approved_orders"]) == 0

    def test_repeat_order_approvals_accumulation(self, app_runner: AppTest):
        """Test clicking approve multiple times accumulates orders with unique order IDs."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("🎯 Рекомендации и What-If").run()

        # Approve first time
        at.button(key="approve_orders_btn").click().run()
        assert not at.exception
        count_1 = len(at.session_state["approved_orders"])

        # Approve second time
        at.button(key="approve_orders_btn").click().run()
        assert not at.exception
        count_2 = len(at.session_state["approved_orders"])

        assert count_2 == count_1 * 2
        order_ids = [o["order_id"] for o in at.session_state["approved_orders"]]
        assert len(order_ids) == len(set(order_ids)), "Order IDs must be unique across approvals"


class TestHeadlessUIInventoryFilteringAndEdgeCases:
    """Stress tests inventory filters including empty set boundary conditions."""

    def test_empty_filter_result_handling(self, app_runner: AppTest):
        """Verify selecting contradictory filters resulting in 0 items does not crash UI."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("📦 Состояние запасов (ABC/XYZ)").run()
        assert not at.exception

        # Select combination known to yield 0 items
        at.selectbox(key="inv_cat_filter").select("Consumables")
        at.selectbox(key="inv_abc_filter").select("A")
        at.selectbox(key="inv_status_filter").select("CRITICAL")
        at.run()
        assert not at.exception

        # Dataframe should be empty but present
        assert len(at.dataframe) >= 1
        assert len(at.dataframe[0].value) == 0

        # Scatter chart must still be rendered without crashing
        assert len(at.get("plotly_chart")) >= 1

        # CSV download button must still exist
        assert len(at.download_button) >= 1

    def test_category_and_status_filter_permutations(self, app_runner: AppTest):
        """Verify cycling across all categories and status filters runs cleanly."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("📦 Состояние запасов (ABC/XYZ)").run()

        categories = ["Consumables", "Electronics", "Raw Materials", "Spare Parts", "Все"]
        statuses = ["CRITICAL", "REORDER_NEEDED", "OPTIMAL", "EXCESS", "Все"]

        for cat in categories:
            for st_val in statuses:
                at.selectbox(key="inv_cat_filter").select(cat)
                at.selectbox(key="inv_status_filter").select(st_val)
                at.run()
                assert not at.exception, f"Failed on filter combo cat={cat}, status={st_val}"


class TestHeadlessUIDemandForecastingAdversarial:
    """Stress tests forecasting screen controls, SKU cycling, and horizon bounds."""

    def test_forecasting_horizon_and_history_sweep(self, app_runner: AppTest):
        """Test boundary forecast horizons (7, 60 days) and all history views."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("📈 Прогнозирование спроса").run()
        assert not at.exception

        # Test minimum horizon
        at.slider(key="forecast_h_slider").set_value(7).run()
        assert not at.exception

        # Test maximum horizon
        at.slider(key="forecast_h_slider").set_value(60).run()
        assert not at.exception

        # Test all history windows
        windows = [
            "Последние 90 дней",
            "Последние 180 дней",
            "Последние 365 дней",
            "Все 730 дней",
        ]
        for w in windows:
            at.selectbox(key="forecast_hist_select").select(w).run()
            assert not at.exception

        # Check metrics and fan chart
        assert len(at.get("plotly_chart")) >= 1
        metric_labels = [m.label for m in at.metric]
        assert "Выбранная модель" in metric_labels
        assert "MAE (Абсолютная ошибка)" in metric_labels

    def test_forecasting_sku_selector_extremes(self, app_runner: AppTest):
        """Test selecting different SKUs across categories."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("📈 Прогнозирование спроса").run()

        sku_sb = at.selectbox(key="forecast_sku_select")
        options = sku_sb.options
        assert len(options) == 25

        # Select first SKU
        sku_sb.select_index(0).run()
        assert not at.exception

        # Select middle SKU
        sku_sb.select_index(12).run()
        assert not at.exception

        # Select last SKU
        sku_sb.select_index(len(options) - 1).run()
        assert not at.exception


class TestHeadlessUISupplierEvaluationAdversarial:
    """Stress tests supplier evaluation MCDA algorithms and risk simulation."""

    def test_all_mcda_evaluation_methods(self, app_runner: AppTest):
        """Verify all 4 MCDA methods compute rankings and render radar chart."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("🏭 Оценка поставщиков").run()
        assert not at.exception

        methods = [
            "TOPSIS (AHP веса)",
            "Shannon Entropy (Объективные веса)",
            "Hybrid (AHP + Entropy)",
            "WSM (Линейная свертка)",
        ]
        for m in methods:
            at.selectbox(key="sup_method_select").select(m).run()
            assert not at.exception, f"Failed on MCDA method {m}"
            assert len(at.dataframe) >= 1
            assert len(at.get("plotly_chart")) >= 1

    def test_supply_disruption_decision_tree_boundaries(self, app_runner: AppTest):
        """Test decision tree EMV calculation under minimum and maximum disruption parameters."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("🏭 Оценка поставщиков").run()

        # Min risk scenario
        at.slider(key="p_disrupt_slider").set_value(0.01)
        at.slider(key="penalty_cost_slider").set_value(50000)
        at.run()
        assert not at.exception

        # Max catastrophic risk scenario
        at.slider(key="p_disrupt_slider").set_value(0.25)
        at.slider(key="penalty_cost_slider").set_value(500000)
        at.run()
        assert not at.exception

        # Verify strategy metric is displayed
        metric_labels = [m.label for m in at.metric]
        assert "Рекомендованная стратегия" in metric_labels


class TestHeadlessUICrossScreenReactivity:
    """Stress tests session state synchronization across screen transitions."""

    def test_service_level_propagation_across_screens(self, app_runner: AppTest):
        """Verify updating service level in Screen 5 propagates to Screen 1 overview."""
        at = app_runner

        # 1. Start on Screen 1
        at.sidebar.radio(key="nav_screen").set_value("📊 Обзор и ключевые KPI").run()
        initial_sl_metric = next(m for m in at.metric if m.label == "Уровень сервиса (α)")
        assert initial_sl_metric.value == "95.0%"

        # 2. Mutate on Screen 5
        at.sidebar.radio(key="nav_screen").set_value("🎯 Рекомендации и What-If").run()
        at.slider(key="wb_service_level").set_value(0.99).run()

        # 3. Return to Screen 1
        at.sidebar.radio(key="nav_screen").set_value("📊 Обзор и ключевые KPI").run()
        updated_sl_metric = next(m for m in at.metric if m.label == "Уровень сервиса (α)")
        assert updated_sl_metric.value == "99.0%"

    def test_rapid_multiscreen_switching_stability(self, app_runner: AppTest):
        """Verify switching repeatedly across all screens executes without memory corruption."""
        at = app_runner
        screen_order = [
            "📊 Обзор и ключевые KPI",
            "📦 Состояние запасов (ABC/XYZ)",
            "📈 Прогнозирование спроса",
            "🏭 Оценка поставщиков",
            "🎯 Рекомендации и What-If",
            "📊 Обзор и ключевые KPI",
            "🎯 Рекомендации и What-If",
            "📦 Состояние запасов (ABC/XYZ)",
        ]

        for screen in screen_order:
            at.sidebar.radio(key="nav_screen").set_value(screen).run()
            assert not at.exception, f"Failed during rapid switch to {screen}"


class TestHeadlessUIExportButtonsAndSerialization:
    """Stress tests export buttons and data payload integrity."""

    def test_export_buttons_presence(self, app_runner: AppTest):
        """Verify CSV and JSON export buttons exist on Screen 5."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("🎯 Рекомендации и What-If").run()

        db_keys = [db.key for db in at.download_button]
        assert "export_csv_btn" in db_keys
        assert "export_json_btn" in db_keys

    def test_export_serialization_data_validity(self):
        """Directly verify that recommendation data serializes cleanly into CSV and JSON."""
        recs = calculate_dss_recommendations(
            service_level=0.95,
            volume_limit=1200.0,
            weight_limit=50000.0,
            lead_time_shock=0.0,
        )
        assert len(recs) == 25

        # Test JSON serialization
        json_payload = json.dumps([r.model_dump() for r in recs], ensure_ascii=False)
        reloaded_json = json.loads(json_payload)
        assert len(reloaded_json) == 25
        assert all(isinstance(item["sku_id"], str) for item in reloaded_json)

        # Test CSV export structure
        df = pd.DataFrame([r.model_dump() for r in recs])
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)
        reloaded_df = pd.read_csv(csv_buffer)
        assert len(reloaded_df) == 25
        assert "sku_id" in reloaded_df.columns
        assert "recommended_order_quantity" in reloaded_df.columns


class TestHeadlessUIEdgeCasesAndResilience:
    """Tests empty state robustness, non-probabilistic criteria, and logistics math."""

    def test_inventory_empty_filter_shows_info_message(self, app_runner: AppTest):
        """Selecting an impossible filter combination displays an info message rather than crashing."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("📦 Состояние запасов (ABC/XYZ)").run()
        assert not at.exception

        # Filter by category and an absent status
        at.selectbox(key="inv_cat_filter").set_value("Electronics").run()
        assert not at.exception
        at.selectbox(key="inv_status_filter").set_value("EXCESS").run()
        assert not at.exception

        # Check that empty notice is displayed if no rows matched
        df_len = len(at.dataframe[0].value) if at.dataframe else 0
        if df_len == 0:
            info_texts = [info.value for info in at.info]
            assert any("не найдены" in t for t in info_texts)

    def test_suppliers_uncertainty_criteria_rendered(self, app_runner: AppTest):
        """Screen 4 renders non-probabilistic criteria (Wald, Savage, Hurwicz, Laplace)."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("🏭 Оценка поставщиков").run()
        assert not at.exception

        # Dataframe for criteria must be present
        dfs = [df.value for df in at.dataframe]
        found_criteria_df = False
        for df in dfs:
            if "Критерий" in df.columns:
                found_criteria_df = True
                criteria_list = df["Критерий"].tolist()
                assert any("Вальд" in c for c in criteria_list)
                assert any("Сэвидж" in c for c in criteria_list)
                assert any("Гурвиц" in c for c in criteria_list)
                assert any("Лаплас" in c for c in criteria_list)
                break
        assert found_criteria_df, "Non-probabilistic uncertainty criteria table missing from Screen 4"

    def test_recommendations_truck_fleet_ceiling_metric(self, app_runner: AppTest):
        """Screen 5 computes truck logistics without crash and shows valid metrics."""
        at = app_runner
        at.sidebar.radio(key="nav_screen").set_value("🎯 Рекомендации и What-If").run()
        assert not at.exception

        metric_labels = [m.label for m in at.metric]
        assert "Расчетное число еврофур (FTL)" in metric_labels
        assert "Коэффициент заполнения объема" in metric_labels
        assert "Коэффициент весовой нагрузки" in metric_labels

    def test_overview_empty_recs_resilience(self):
        """Screen 1 handles empty recommendations gracefully without KeyError: 'Статус'."""
        from unittest.mock import patch
        with patch("inventory_dss.ui.views.overview.calculate_dss_recommendations", return_value=[]):
            at = AppTest.from_file(str(APP_PATH), default_timeout=DEFAULT_TIMEOUT)
            at.run()
            at.sidebar.radio(key="nav_screen").set_value("📊 Обзор и ключевые KPI").run()
            assert not at.exception
