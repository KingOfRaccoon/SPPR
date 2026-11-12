"""Comprehensive 5-Tier Unit Test Suite for Inventory DSS Design System.

Verifies:
- Tier 1: Primitive, Semantic, and Component token integrity, types, and hierarchy.
- Tier 2: WCAG 2.2 AA Contrast calculation mathematics ($L_1+0.05 / L_2+0.05$) and
          compliance assertions (>= 4.5:1 text, >= 3.0:1 UI) for Dark & Light modes.
- Tier 3: Concentric radii mathematical proof ($R_{outer} = R_{inner} + padding$).
- Tier 4: Theme Engine (ThemeMode, get_theme, generate_css, inject_custom_css, config.toml).
- Tier 5: Plotly visualization theming (get_plotly_template layout, transparency, colorways).
- Adversarial Robustness: Invalid inputs, extreme contrasts, boundary paddings.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import plotly.graph_objects as go
import pytest

from inventory_dss.ui.theme import (
    AMBER_PALETTE,
    CRIMSON_PALETTE,
    EMERALD_PALETTE,
    INDIGO_PALETTE,
    PURPLE_PALETTE,
    SKY_PALETTE,
    SLATE_PALETTE,
    ZINC_PALETTE,
    BadgeTokens,
    BorderTokens,
    ChartTokens,
    ColorScale,
    ControlTokens,
    DataTableTokens,
    DSSTheme,
    EpistemicTrustTier,
    InventoryStatus,
    KpiCardTokens,
    RadiiTokens,
    ReasoningCardTokens,
    ShadowTokens,
    SpacingTokens,
    StatusColorTokens,
    SurfaceTokens,
    TextTokens,
    ThemeMode,
    TrustTierColorTokens,
    TypographyTokens,
    calculate_contrast_ratio,
    calculate_relative_luminance,
    generate_css,
    get_dark_theme,
    get_light_theme,
    get_plotly_template,
    get_streamlit_config_toml,
    get_theme,
    hex_to_rgb,
    inject_custom_css,
    srgb_to_linear,
    verify_theme_wcag,
)

HEX_COLOR_REGEX = re.compile(r"^#[0-9a-fA-F]{6}$")


# ==============================================================================
# Tier 1: Primitive, Semantic, and Component Token Integrity
# ==============================================================================

class TestTier1PrimitiveTokens:
    """Validate core visual primitive tokens, scales, and types."""

    def test_theme_mode_enum_members(self) -> None:
        """ThemeMode must define LIGHT and DARK with string values."""
        assert ThemeMode.LIGHT.value == "light"
        assert ThemeMode.DARK.value == "dark"
        assert len(ThemeMode) == 2

    def test_inventory_status_enum_members(self) -> None:
        """InventoryStatus must contain all 4 domain states."""
        assert InventoryStatus.CRITICAL.value == "CRITICAL"
        assert InventoryStatus.REORDER_NEEDED.value == "REORDER_NEEDED"
        assert InventoryStatus.OPTIMAL.value == "OPTIMAL"
        assert InventoryStatus.EXCESS.value == "EXCESS"
        assert len(InventoryStatus) == 4

    def test_epistemic_trust_tier_enum_members(self) -> None:
        """EpistemicTrustTier must define 3 AI/DSS transparency levels."""
        assert EpistemicTrustTier.ALGORITHMIC.value == "ALGORITHMIC"
        assert EpistemicTrustTier.HEURISTIC.value == "HEURISTIC"
        assert EpistemicTrustTier.EXPLORATORY.value == "EXPLORATORY"
        assert len(EpistemicTrustTier) == 3

    @pytest.mark.parametrize(
        ("palette_name", "palette"),
        [
            ("zinc", ZINC_PALETTE),
            ("slate", SLATE_PALETTE),
            ("crimson", CRIMSON_PALETTE),
            ("amber", AMBER_PALETTE),
            ("emerald", EMERALD_PALETTE),
            ("sky", SKY_PALETTE),
            ("purple", PURPLE_PALETTE),
            ("indigo", INDIGO_PALETTE),
        ],
    )
    def test_color_scales_11_steps_and_valid_hex(
        self, palette_name: str, palette: ColorScale
    ) -> None:
        """All primitive palettes must expose all 11 steps with valid 6-char hex codes."""
        steps = [
            "c50", "c100", "c200", "c300", "c400", "c500",
            "c600", "c700", "c800", "c900", "c950",
        ]
        for step in steps:
            val = getattr(palette, step)
            assert isinstance(val, str), f"{palette_name}.{step} is not string"
            assert HEX_COLOR_REGEX.match(val), (
                f"{palette_name}.{step}='{val}' does not match #RRGGBB format"
            )

    @pytest.mark.parametrize(
        "palette",
        [
            ZINC_PALETTE,
            SLATE_PALETTE,
            CRIMSON_PALETTE,
            AMBER_PALETTE,
            EMERALD_PALETTE,
            SKY_PALETTE,
            PURPLE_PALETTE,
            INDIGO_PALETTE,
        ],
    )
    def test_palette_luminance_ordering(self, palette: ColorScale) -> None:
        """Higher scale steps (c50) must have strictly higher luminance than lower (c950)."""
        lum_50 = calculate_relative_luminance(palette.c50)
        lum_500 = calculate_relative_luminance(palette.c500)
        lum_950 = calculate_relative_luminance(palette.c950)
        assert lum_50 > lum_500 > lum_950, "Palette lightness inverted or non-monotonic"

    def test_typography_tokens_properties(self) -> None:
        """Typography must specify Inter, JetBrains Mono, and tabular-nums settings."""
        typo = TypographyTokens()
        assert "Inter" in typo.font_sans
        assert "JetBrains Mono" in typo.font_mono
        assert "tnum" in typo.font_tabular_settings
        assert "zero" in typo.font_tabular_settings

        # Font weights
        assert typo.weight_normal == 400
        assert typo.weight_medium == 500
        assert typo.weight_semibold == 600
        assert typo.weight_bold == 700

    def test_typography_scale_strictly_monotonic(self) -> None:
        """Font sizes from xs to 4xl must be strictly increasing in rem/px value."""
        typo = TypographyTokens()
        scale_props = [
            typo.size_xs,
            typo.size_sm,
            typo.size_base,
            typo.size_lg,
            typo.size_xl,
            typo.size_2xl,
            typo.size_3xl,
            typo.size_4xl,
        ]
        values: list[float] = []
        for prop in scale_props:
            val = float(prop.replace("rem", "").replace("px", ""))
            values.append(val)

        for i in range(len(values) - 1):
            assert values[i] < values[i + 1], f"Typography step {i} not smaller than {i + 1}"

    def test_spacing_grid_adheres_to_baseline(self) -> None:
        """Spacing tokens must follow 4px/8px incremental grid."""
        sp = SpacingTokens()
        expected = {
            "space_0": "0px",
            "space_1": "4px",
            "space_2": "8px",
            "space_3": "12px",
            "space_4": "16px",
            "space_5": "20px",
            "space_6": "24px",
            "space_8": "32px",
            "space_10": "40px",
            "space_12": "48px",
            "space_16": "64px",
        }
        for prop, val in expected.items():
            assert getattr(sp, prop) == val

    def test_shadow_tokens_elevation_hierarchy(self) -> None:
        """Shadow tokens must include standard elevations and ambient glows."""
        dark = get_dark_theme()
        sh = dark.shadows
        assert isinstance(sh, ShadowTokens)
        assert sh.elevation_none == "none"
        assert "rgba" in sh.elevation_sm
        assert "rgba" in sh.elevation_md
        assert "rgba" in sh.elevation_lg
        assert "rgba" in sh.glow_brand
        assert "rgba" in sh.glow_critical
        assert "rgba" in sh.glow_optimal


class TestTier1SemanticAndComponentTokens:
    """Validate Semantic layer mappings and Component-level composite tokens."""

    @pytest.mark.parametrize("mode", [ThemeMode.DARK, ThemeMode.LIGHT])
    def test_semantic_surfaces_structure(self, mode: ThemeMode) -> None:
        """Surfaces must provide layer_0, layer_1, layer_2, and layer_accent."""
        theme = get_theme(mode)
        surfaces: SurfaceTokens = theme.surfaces
        assert HEX_COLOR_REGEX.match(surfaces.layer_0)
        assert HEX_COLOR_REGEX.match(surfaces.layer_1)
        assert HEX_COLOR_REGEX.match(surfaces.layer_2)
        assert HEX_COLOR_REGEX.match(surfaces.layer_accent)

    @pytest.mark.parametrize("mode", [ThemeMode.DARK, ThemeMode.LIGHT])
    def test_semantic_text_structure(self, mode: ThemeMode) -> None:
        """Text tokens must specify primary, secondary, muted, inverse, and accent."""
        theme = get_theme(mode)
        text: TextTokens = theme.text
        assert HEX_COLOR_REGEX.match(text.primary)
        assert HEX_COLOR_REGEX.match(text.secondary)
        assert HEX_COLOR_REGEX.match(text.muted)
        assert HEX_COLOR_REGEX.match(text.inverse)
        assert HEX_COLOR_REGEX.match(text.accent)

    @pytest.mark.parametrize("mode", [ThemeMode.DARK, ThemeMode.LIGHT])
    def test_semantic_borders_structure(self, mode: ThemeMode) -> None:
        """Border tokens must specify subtle, default, strong, and focus."""
        theme = get_theme(mode)
        b: BorderTokens = theme.borders
        assert HEX_COLOR_REGEX.match(b.subtle)
        assert HEX_COLOR_REGEX.match(b.default)
        assert HEX_COLOR_REGEX.match(b.strong)
        assert HEX_COLOR_REGEX.match(b.focus)

    @pytest.mark.parametrize("mode", [ThemeMode.DARK, ThemeMode.LIGHT])
    def test_domain_status_composite_tokens(self, mode: ThemeMode) -> None:
        """All 4 inventory statuses must have fg, bg, border, solid, and pulse."""
        theme = get_theme(mode)
        statuses = [
            theme.status_critical,
            theme.status_reorder,
            theme.status_optimal,
            theme.status_excess,
        ]
        for st in statuses:
            assert isinstance(st, StatusColorTokens)
            assert HEX_COLOR_REGEX.match(st.fg)
            assert HEX_COLOR_REGEX.match(st.bg)
            assert HEX_COLOR_REGEX.match(st.border)
            assert HEX_COLOR_REGEX.match(st.solid)
            assert "rgba" in st.pulse or "#" in st.pulse

    @pytest.mark.parametrize("mode", [ThemeMode.DARK, ThemeMode.LIGHT])
    def test_epistemic_trust_tier_composite_tokens(self, mode: ThemeMode) -> None:
        """All 3 trust tiers must have fg, bg, border, and human-readable badge labels."""
        theme = get_theme(mode)
        tiers = [
            theme.trust_algorithmic,
            theme.trust_heuristic,
            theme.trust_exploratory,
        ]
        for tr in tiers:
            assert isinstance(tr, TrustTierColorTokens)
            assert HEX_COLOR_REGEX.match(tr.fg)
            assert len(tr.badge_label) > 0
            assert tr.border.startswith("#")

    @pytest.mark.parametrize("mode", [ThemeMode.DARK, ThemeMode.LIGHT])
    def test_kpi_card_component_tokens(self, mode: ThemeMode) -> None:
        """KPI Card tokens must assemble surface, border, radius, and delta indicators."""
        theme = get_theme(mode)
        card: KpiCardTokens = theme.kpi_card
        assert card.bg == theme.surfaces.layer_1
        assert card.border == theme.borders.subtle
        assert card.radius == theme.radii.r_lg
        assert card.title_color == theme.text.secondary
        assert card.value_color == theme.text.primary
        assert card.delta_up == theme.status_optimal.fg
        assert card.delta_down == theme.status_critical.fg

    @pytest.mark.parametrize("mode", [ThemeMode.DARK, ThemeMode.LIGHT])
    def test_data_table_component_tokens(self, mode: ThemeMode) -> None:
        """Data table tokens must enforce tabular numerals and distinct header background."""
        theme = get_theme(mode)
        table: DataTableTokens = theme.data_table
        assert table.header_bg == theme.surfaces.layer_2
        assert table.header_text == theme.text.secondary
        assert table.row_hover_bg == theme.surfaces.layer_2
        assert "tnum" in table.num_font_settings

    @pytest.mark.parametrize("mode", [ThemeMode.DARK, ThemeMode.LIGHT])
    def test_badge_and_chips_tokens(self, mode: ThemeMode) -> None:
        """Status badge tokens must define full pill radius and compact font styling."""
        theme = get_theme(mode)
        badge: BadgeTokens = theme.badge
        assert badge.radius == theme.radii.r_full
        assert badge.dot_size == "6px"
        assert badge.font_weight == theme.typography.weight_semibold

    @pytest.mark.parametrize("mode", [ThemeMode.DARK, ThemeMode.LIGHT])
    def test_reasoning_card_component_tokens(self, mode: ThemeMode) -> None:
        """Reasoning card tokens must define 4px left accent border and concentric radius."""
        theme = get_theme(mode)
        rc: ReasoningCardTokens = theme.reasoning_card
        assert rc.bg == theme.surfaces.layer_1
        assert rc.border_left_width == "4px"
        assert rc.radius == theme.radii.r_md

    @pytest.mark.parametrize("mode", [ThemeMode.DARK, ThemeMode.LIGHT])
    def test_controls_component_tokens(self, mode: ThemeMode) -> None:
        """What-if controls tokens must define track, thumb, and active focus colors."""
        theme = get_theme(mode)
        ctrl: ControlTokens = theme.controls
        assert ctrl.track_bg == theme.surfaces.layer_2
        assert ctrl.thumb_color == theme.brand_primary
        assert ctrl.border_focus == theme.borders.focus

    @pytest.mark.parametrize("mode", [ThemeMode.DARK, ThemeMode.LIGHT])
    def test_chart_component_tokens(self, mode: ThemeMode) -> None:
        """Chart tokens must define transparent background and subtle grid color."""
        theme = get_theme(mode)
        chart: ChartTokens = theme.chart
        assert chart.bg in ("rgba(0,0,0,0)", "transparent")
        assert chart.grid_color == theme.borders.subtle
        assert "rgba" in chart.confidence_band_fill


# ==============================================================================
# Tier 2: WCAG 2.2 AA Contrast Calculation Mathematics & Assertions
# ==============================================================================

class TestTier2WCAGContrastMathematics:
    """Rigorous verification of WCAG 2.2 Relative Luminance and Contrast Ratio math."""

    def test_srgb_to_linear_extremes_and_threshold(self) -> None:
        """Test channel linearization piecewise threshold at 0.04045."""
        assert srgb_to_linear(0) == pytest.approx(0.0, abs=1e-6)
        assert srgb_to_linear(255) == pytest.approx(1.0, abs=1e-6)

        # Value below piecewise threshold (10 / 255 = 0.039215 < 0.04045)
        lin_10 = srgb_to_linear(10)
        assert lin_10 == pytest.approx((10 / 255.0) / 12.92, rel=1e-4)

        # Value above piecewise threshold (128 / 255 = 0.50196 > 0.04045)
        lin_128 = srgb_to_linear(128)
        assert lin_128 == pytest.approx(((128 / 255.0 + 0.055) / 1.055) ** 2.4, rel=1e-4)

    def test_hex_to_rgb_parsing(self) -> None:
        """Test 6-digit, 3-digit shorthand, and prefix handling."""
        assert hex_to_rgb("#FFFFFF") == (255, 255, 255)
        assert hex_to_rgb("#000000") == (0, 0, 0)
        assert hex_to_rgb("#4F46E5") == (79, 70, 229)
        # Shorthand 3-digit hex
        assert hex_to_rgb("#FFF") == (255, 255, 255)
        assert hex_to_rgb("#000") == (0, 0, 0)
        # Without leading hash
        assert hex_to_rgb("FAFAFA") == (250, 250, 250)

    def test_calculate_relative_luminance_standards(self) -> None:
        """Test relative luminance coefficients: L = 0.2126*R + 0.7152*G + 0.0722*B."""
        assert calculate_relative_luminance("#FFFFFF") == pytest.approx(1.0, abs=1e-3)
        assert calculate_relative_luminance("#000000") == pytest.approx(0.0, abs=1e-3)
        assert calculate_relative_luminance("#FF0000") == pytest.approx(0.2126, abs=1e-3)
        assert calculate_relative_luminance("#00FF00") == pytest.approx(0.7152, abs=1e-3)
        assert calculate_relative_luminance("#0000FF") == pytest.approx(0.0722, abs=1e-3)

    def test_calculate_contrast_ratio_properties(self) -> None:
        """Test symmetry, maximum (21:1), and minimum (1:1) contrast limits."""
        # Max contrast (white vs black)
        assert calculate_contrast_ratio("#FFFFFF", "#000000") == pytest.approx(21.0, abs=1e-2)
        # Min contrast (same color)
        assert calculate_contrast_ratio("#4F46E5", "#4F46E5") == pytest.approx(1.0, abs=1e-2)
        # Symmetry property
        cr_ab = calculate_contrast_ratio("#09090B", "#F4F4F5")
        cr_ba = calculate_contrast_ratio("#F4F4F5", "#09090B")
        assert cr_ab == pytest.approx(cr_ba, abs=1e-4)

    def test_dark_theme_wcag_text_compliance(self) -> None:
        """Dark theme: all text on card (layer_1) and canvas (layer_0) must be >= 4.5:1."""
        dark = get_dark_theme()
        card_bg = dark.surfaces.layer_1
        canvas_bg = dark.surfaces.layer_0

        cr_prim_card = calculate_contrast_ratio(dark.text.primary, card_bg)
        assert cr_prim_card >= 4.5, f"Dark primary on card failed: {cr_prim_card:.2f}:1"

        cr_prim_canvas = calculate_contrast_ratio(dark.text.primary, canvas_bg)
        assert cr_prim_canvas >= 4.5, f"Dark primary on canvas failed: {cr_prim_canvas:.2f}:1"

        cr_sec_card = calculate_contrast_ratio(dark.text.secondary, card_bg)
        assert cr_sec_card >= 4.5, f"Dark secondary on card failed: {cr_sec_card:.2f}:1"

        cr_muted_card = calculate_contrast_ratio(dark.text.muted, card_bg)
        assert cr_muted_card >= 4.5, f"Dark muted on card failed: {cr_muted_card:.2f}:1"

        # Brand button: white text on brand primary
        cr_btn = calculate_contrast_ratio("#FFFFFF", dark.brand_primary)
        assert cr_btn >= 4.5, f"Dark brand button text failed: {cr_btn:.2f}:1"

    def test_dark_theme_wcag_status_contrast(self) -> None:
        """Dark theme: all status foregrounds must meet >= 4.5:1 on card and on status bg."""
        dark = get_dark_theme()
        card_bg = dark.surfaces.layer_1
        statuses = [
            ("CRITICAL", dark.status_critical),
            ("REORDER_NEEDED", dark.status_reorder),
            ("OPTIMAL", dark.status_optimal),
            ("EXCESS", dark.status_excess),
        ]
        for name, st in statuses:
            cr_on_card = calculate_contrast_ratio(st.fg, card_bg)
            assert cr_on_card >= 4.5, f"Dark status {name} on card failed: {cr_on_card:.2f}:1"

            cr_on_bg = calculate_contrast_ratio(st.fg, st.bg)
            assert cr_on_bg >= 4.5, f"Dark status {name} on status bg failed: {cr_on_bg:.2f}:1"

    def test_dark_theme_wcag_ui_border_contrast(self) -> None:
        """Dark theme: strong interactive border must meet WCAG 1.4.11 >= 3.0:1 on card."""
        dark = get_dark_theme()
        cr = calculate_contrast_ratio(dark.borders.strong, dark.surfaces.layer_1)
        assert cr >= 3.0, f"Dark strong border failed non-text UI contrast: {cr:.2f}:1"

    def test_light_theme_wcag_text_compliance(self) -> None:
        """Light theme: all text on card (layer_1) and canvas (layer_0) must be >= 4.5:1."""
        light = get_light_theme()
        card_bg = light.surfaces.layer_1
        canvas_bg = light.surfaces.layer_0

        cr_prim_card = calculate_contrast_ratio(light.text.primary, card_bg)
        assert cr_prim_card >= 4.5, f"Light primary on card failed: {cr_prim_card:.2f}:1"

        cr_prim_canvas = calculate_contrast_ratio(light.text.primary, canvas_bg)
        assert cr_prim_canvas >= 4.5, f"Light primary on canvas failed: {cr_prim_canvas:.2f}:1"

        cr_sec_card = calculate_contrast_ratio(light.text.secondary, card_bg)
        assert cr_sec_card >= 4.5, f"Light secondary on card failed: {cr_sec_card:.2f}:1"

        cr_muted_card = calculate_contrast_ratio(light.text.muted, card_bg)
        assert cr_muted_card >= 4.5, f"Light muted on card failed: {cr_muted_card:.2f}:1"

        # Brand button: white text on brand primary
        cr_btn = calculate_contrast_ratio("#FFFFFF", light.brand_primary)
        assert cr_btn >= 4.5, f"Light brand button text failed: {cr_btn:.2f}:1"

    def test_light_theme_wcag_status_contrast(self) -> None:
        """Light theme: all status foregrounds must meet >= 4.5:1 on card and on status bg."""
        light = get_light_theme()
        card_bg = light.surfaces.layer_1
        statuses = [
            ("CRITICAL", light.status_critical),
            ("REORDER_NEEDED", light.status_reorder),
            ("OPTIMAL", light.status_optimal),
            ("EXCESS", light.status_excess),
        ]
        for name, st in statuses:
            cr_on_card = calculate_contrast_ratio(st.fg, card_bg)
            assert cr_on_card >= 4.5, f"Light status {name} on card failed: {cr_on_card:.2f}:1"

            cr_on_bg = calculate_contrast_ratio(st.fg, st.bg)
            assert cr_on_bg >= 4.5, f"Light status {name} on status bg failed: {cr_on_bg:.2f}:1"

    def test_light_theme_wcag_ui_border_contrast(self) -> None:
        """Light theme: strong interactive border must meet WCAG 1.4.11 >= 3.0:1 on card."""
        light = get_light_theme()
        cr = calculate_contrast_ratio(light.borders.strong, light.surfaces.layer_1)
        assert cr >= 3.0, f"Light strong border failed non-text UI contrast: {cr:.2f}:1"

    @pytest.mark.parametrize("mode", [ThemeMode.DARK, ThemeMode.LIGHT])
    def test_verify_theme_wcag_full_audit(self, mode: ThemeMode) -> None:
        """verify_theme_wcag() must return 100% passing results for both themes."""
        theme = get_theme(mode)
        report = verify_theme_wcag(theme)
        assert isinstance(report, dict)
        assert len(report) >= 12, "Audit must cover all standard pairings"
        for label, (cr, passed) in report.items():
            assert passed is True, f"Theme {mode.value} pairing '{label}' failed WCAG: {cr}:1"


# ==============================================================================
# Tier 3: Concentric Radii Mathematical Proof
# ==============================================================================

class TestTier3ConcentricRadii:
    """Verify concentric radii mathematics: R_outer = R_inner + padding."""

    def test_concentric_radii_formula_derivation(self) -> None:
        """R_inner = max(0, R_outer - padding) must yield exact concentric curves."""
        calc_fn = getattr(RadiiTokens, "calculate_concentric_radius", None) or getattr(
            RadiiTokens, "calculate_inner_radius", None
        )
        assert calc_fn is not None, "RadiiTokens missing concentric radius calculation method"

        # Standard card: R_outer = 16px, padding = 12px -> R_inner = 4px
        assert calc_fn(16.0, 12.0) == pytest.approx(4.0, abs=1e-4)

        # Standard KPI card: R_outer = 12px, padding = 8px -> R_inner = 4px
        assert calc_fn(12.0, 8.0) == pytest.approx(4.0, abs=1e-4)

        # Exact match: R_outer = 8px, padding = 8px -> R_inner = 0px
        assert calc_fn(8.0, 8.0) == pytest.approx(0.0, abs=1e-4)

        # Zero padding: R_outer = 12px, padding = 0px -> R_inner = 12px
        assert calc_fn(12.0, 0.0) == pytest.approx(12.0, abs=1e-4)

    def test_concentric_radii_non_negative_clamp(self) -> None:
        """Padding exceeding outer radius must never produce negative border-radius."""
        calc_fn = getattr(RadiiTokens, "calculate_concentric_radius", None) or getattr(
            RadiiTokens, "calculate_inner_radius", None
        )
        assert calc_fn is not None
        assert calc_fn(6.0, 10.0) == 0.0
        assert calc_fn(0.0, 16.0) == 0.0
        assert calc_fn(4.0, 50.0) == 0.0

    def test_radii_scale_tokens_values(self) -> None:
        """Validate standard scale from none (0px) to full (9999px)."""
        r = RadiiTokens()
        assert r.r_none == "0px"
        assert r.r_xs == "2px"
        assert r.r_sm == "4px"
        assert r.r_md == "8px"
        assert r.r_lg == "12px"
        assert r.r_xl == "16px"
        assert r.r_2xl == "24px"
        assert r.r_full == "9999px"


# ==============================================================================
# Tier 4: Theme Engine & CSS Structure
# ==============================================================================

class TestTier4ThemeEngineAndCSS:
    """Verify theme factory, mode resolution, CSS injection, and config generation."""

    def test_get_theme_dark_and_light(self) -> None:
        """get_theme must return correct DSSTheme instance for enum modes."""
        dark = get_theme(ThemeMode.DARK)
        assert isinstance(dark, DSSTheme)
        assert dark.mode == ThemeMode.DARK
        assert dark.surfaces.layer_0 == "#09090B"

        light = get_theme(ThemeMode.LIGHT)
        assert isinstance(light, DSSTheme)
        assert light.mode == ThemeMode.LIGHT
        assert light.surfaces.layer_0 == "#F8FAFC"

    def test_get_theme_case_insensitivity(self) -> None:
        """get_theme must accept string arguments case-insensitively."""
        assert get_theme("dark").mode == ThemeMode.DARK
        assert get_theme("DARK").mode == ThemeMode.DARK
        assert get_theme("Dark").mode == ThemeMode.DARK

        assert get_theme("light").mode == ThemeMode.LIGHT
        assert get_theme("LIGHT").mode == ThemeMode.LIGHT
        assert get_theme("Light").mode == ThemeMode.LIGHT

    def test_get_theme_invalid_mode_raises_error(self) -> None:
        """Invalid theme mode string must raise ValueError."""
        with pytest.raises(ValueError):
            get_theme("cyberpunk_neon")

    def test_generate_css_contains_root_custom_properties(self) -> None:
        """Generated stylesheet must define complete CSS custom properties in :root."""
        dark = get_dark_theme()
        css = generate_css(dark)

        assert ":root {" in css
        # Check surfaces
        assert f"--surface-layer-0: {dark.surfaces.layer_0};" in css
        assert f"--surface-layer-1: {dark.surfaces.layer_1};" in css
        assert f"--surface-layer-2: {dark.surfaces.layer_2};" in css

        # Check typography & brand
        assert "--font-sans:" in css
        assert "--font-mono:" in css
        assert f"--brand-primary: {dark.brand_primary};" in css

        # Check status tokens
        assert f"--status-critical-fg: {dark.status_critical.fg};" in css
        assert f"--status-reorder-fg: {dark.status_reorder.fg};" in css
        assert f"--status-optimal-fg: {dark.status_optimal.fg};" in css
        assert f"--status-excess-fg: {dark.status_excess.fg};" in css

        # Check radii & elevations
        assert "--radius-lg:" in css
        assert "--radius-full:" in css
        assert "--elevation-sm:" in css

    def test_generate_css_contains_streamlit_native_overrides(self) -> None:
        """Generated stylesheet must target key Streamlit DOM selectors."""
        light = get_light_theme()
        css = generate_css(light)

        assert ".stApp" in css
        assert '[data-testid="stSidebar"]' in css
        assert '[data-testid="stMetric"]' in css
        assert '[data-testid="stMetricLabel"]' in css
        assert '[data-testid="stMetricValue"]' in css
        assert 'button[kind="primary"]' in css
        assert ".stDataFrame" in css

    def test_generate_css_contains_dss_custom_component_classes(self) -> None:
        """Generated stylesheet must provide styling for DSS custom UI classes."""
        dark = get_dark_theme()
        css = generate_css(dark)

        assert ".dss-kpi-card" in css
        assert ".dss-badge" in css
        assert ".dss-badge-critical" in css
        assert ".dss-badge-reorder" in css
        assert ".dss-badge-optimal" in css
        assert ".dss-badge-excess" in css
        assert ".dss-reasoning-card" in css

    def test_generate_css_enforces_tabular_nums(self) -> None:
        """Tabular numeral features must be globally enforced for numbers & metrics."""
        dark = get_dark_theme()
        css = generate_css(dark)
        assert "tabular-nums" in css
        assert '"tnum" 1' in css

    def test_inject_custom_css_execution(self) -> None:
        """inject_custom_css must inject <style> block into Streamlit without error."""
        mock_st = MagicMock()
        with patch("inventory_dss.ui.theme.st", mock_st):
            inject_custom_css(ThemeMode.DARK)
            mock_st.markdown.assert_called_once()
            args, kwargs = mock_st.markdown.call_args
            assert "<style>" in args[0]
            assert "</style>" in args[0]
            assert kwargs.get("unsafe_allow_html") is True

    def test_get_streamlit_config_toml_dark(self) -> None:
        """Generated .streamlit/config.toml for dark mode must match Zinc/Slate tokens."""
        toml_content = get_streamlit_config_toml(ThemeMode.DARK)
        assert '[theme]' in toml_content
        assert 'base = "dark"' in toml_content
        assert 'primaryColor = "#4F46E5"' in toml_content
        assert 'backgroundColor = "#09090B"' in toml_content
        assert 'secondaryBackgroundColor = "#18181B"' in toml_content
        assert 'textColor = "#F4F4F5"' in toml_content

    def test_get_streamlit_config_toml_light(self) -> None:
        """Generated .streamlit/config.toml for light mode must match Slate/Zinc tokens."""
        toml_content = get_streamlit_config_toml(ThemeMode.LIGHT)
        assert '[theme]' in toml_content
        assert 'base = "light"' in toml_content
        assert 'primaryColor = "#4F46E5"' in toml_content
        assert 'backgroundColor = "#F8FAFC"' in toml_content
        assert 'secondaryBackgroundColor = "#FFFFFF"' in toml_content
        assert 'textColor = "#0F172A"' in toml_content

    def test_actual_streamlit_config_file_on_disk_sync(self) -> None:
        """Verify .streamlit/config.toml on disk strictly matches get_streamlit_config_toml(ThemeMode.DARK)."""
        config_path = Path(__file__).resolve().parents[2] / ".streamlit" / "config.toml"
        assert config_path.exists(), ".streamlit/config.toml must exist on disk"
        disk_content = config_path.read_text(encoding="utf-8").strip()
        expected_content = get_streamlit_config_toml(ThemeMode.DARK).strip()
        assert disk_content == expected_content, (
            f".streamlit/config.toml on disk does not match get_streamlit_config_toml(ThemeMode.DARK).\n"
            f"Disk:\n{disk_content}\nExpected:\n{expected_content}"
        )


# ==============================================================================
# Tier 5: Plotly Visualization Theming
# ==============================================================================

class TestTier5PlotlyVisualizationTheming:
    """Verify Plotly layout template, background transparency, colorways, and fonts."""

    @pytest.mark.parametrize("mode", [ThemeMode.DARK, ThemeMode.LIGHT, "dark", "light"])
    def test_plotly_template_type(self, mode: Any) -> None:
        """get_plotly_template must return a valid go.layout.Template object."""
        tmpl = get_plotly_template(mode)
        assert isinstance(tmpl, go.layout.Template)
        assert hasattr(tmpl, "layout")

    @pytest.mark.parametrize("mode", [ThemeMode.DARK, ThemeMode.LIGHT])
    def test_plotly_template_transparent_background(self, mode: ThemeMode) -> None:
        """Plotly charts must use transparent paper and plot backgrounds to blend in."""
        tmpl = get_plotly_template(mode)
        layout = tmpl.layout
        assert layout.paper_bgcolor in ("rgba(0,0,0,0)", "transparent")
        assert layout.plot_bgcolor in ("rgba(0,0,0,0)", "transparent")

    def test_plotly_template_typography_alignment(self) -> None:
        """Plotly chart typography must align with design system Inter sans-serif."""
        tmpl_dark = get_plotly_template(ThemeMode.DARK)
        assert "Inter" in tmpl_dark.layout.font.family
        assert tmpl_dark.layout.font.color == "#F4F4F5"

        tmpl_light = get_plotly_template(ThemeMode.LIGHT)
        assert "Inter" in tmpl_light.layout.font.family
        assert tmpl_light.layout.font.color in ("#0F172A", "#18181B")

    @pytest.mark.parametrize("mode", [ThemeMode.DARK, ThemeMode.LIGHT])
    def test_plotly_template_grid_and_axes(self, mode: ThemeMode) -> None:
        """X and Y axes must define subtle gridlines, zero lines, and tick fonts."""
        tmpl = get_plotly_template(mode)
        xaxis = tmpl.layout.xaxis
        yaxis = tmpl.layout.yaxis

        assert xaxis.gridcolor is not None
        assert yaxis.gridcolor is not None
        assert xaxis.tickfont.size == 11
        assert yaxis.tickfont.size == 11

    @pytest.mark.parametrize("mode", [ThemeMode.DARK, ThemeMode.LIGHT])
    def test_plotly_template_hoverlabel_card_style(self, mode: ThemeMode) -> None:
        """Plotly hover tooltip must look like elevated layer-2 card."""
        tmpl = get_plotly_template(mode)
        hover = tmpl.layout.hoverlabel

        assert hover.bgcolor is not None
        assert hover.bordercolor is not None
        assert hover.font.size == 12
        assert "Inter" in hover.font.family

    @pytest.mark.parametrize("mode", [ThemeMode.DARK, ThemeMode.LIGHT])
    def test_plotly_template_semantic_colorway(self, mode: ThemeMode) -> None:
        """Colorway sequence must include brand accent, emerald, amber, and crimson."""
        tmpl = get_plotly_template(mode)
        colorway = tmpl.layout.colorway

        assert isinstance(colorway, (list, tuple))
        assert len(colorway) >= 6, "Plotly colorway must contain at least 6 categorical colors"

        # Check key semantic hues exist in sequence
        colorway_upper = [c.upper() for c in colorway]
        assert any(c in colorway_upper for c in ("#6366F1", "#4F46E5")), "Brand indigo missing"
        assert any(c in colorway_upper for c in ("#10B981", "#059669")), "Emerald missing"
        assert any(c in colorway_upper for c in ("#F59E0B", "#D97706")), "Amber missing"
        assert any(c in colorway_upper for c in ("#EF4444", "#DC2626")), "Crimson missing"

    def test_plotly_figure_rendering_with_template(self) -> None:
        """Ensure a live Plotly figure instantiates and serializes cleanly with template."""
        tmpl = get_plotly_template(ThemeMode.DARK)
        fig = go.Figure(
            data=[
                go.Scatter(x=[1, 2, 3], y=[10, 20, 30], name="Historical Demand"),
                go.Scatter(x=[3, 4, 5], y=[30, 42, 55], name="Forecast"),
            ],
            layout=go.Layout(template=tmpl, title="SKU Inventory Trajectory"),
        )
        data_dict = fig.to_dict()
        assert "layout" in data_dict
        template_layout = data_dict["layout"]["template"]["layout"]
        assert template_layout["paper_bgcolor"] in ("rgba(0,0,0,0)", "transparent")
        assert fig.layout.template.layout.paper_bgcolor in ("rgba(0,0,0,0)", "transparent")
        assert len(data_dict["data"]) == 2


# ==============================================================================
# Adversarial Verification & Boundary Robustness
# ==============================================================================

class TestAdversarialThemeRobustness:
    """Adversarial edge cases, malformed inputs, and extreme boundary checks."""

    @pytest.mark.parametrize(
        "invalid_hex",
        [
            "#GGGGGG",
            "#12",
            "#12345",
            "#1234567",
            "not-a-color",
            "",
            "#ZZZ",
        ],
    )
    def test_hex_to_rgb_invalid_inputs_raise_error(self, invalid_hex: str) -> None:
        """Malformed hex strings must fail cleanly with ValueError."""
        with pytest.raises(ValueError):
            hex_to_rgb(invalid_hex)

    def test_contrast_identical_colors_is_exact_unity(self) -> None:
        """Zero difference in color must produce exactly 1.0 contrast ratio."""
        for hex_code in ["#000000", "#FFFFFF", "#18181B", "#4F46E5"]:
            assert calculate_contrast_ratio(hex_code, hex_code) == pytest.approx(1.0, abs=1e-5)

    def test_concentric_radii_extreme_padding_boundary(self) -> None:
        """Extreme padding values (e.g. 1000px) must safely clamp to 0.0px."""
        calc_fn = getattr(RadiiTokens, "calculate_concentric_radius", None) or getattr(
            RadiiTokens, "calculate_inner_radius", None
        )
        assert calc_fn is not None
        assert calc_fn(12.0, 10000.0) == 0.0

    def test_css_no_unrendered_template_placeholders(self) -> None:
        """Generated CSS must not leak unrendered template strings or NaN values."""
        for mode in [ThemeMode.DARK, ThemeMode.LIGHT]:
            css = generate_css(get_theme(mode))
            assert "{" in css and "}" in css
            assert "None" not in css
            assert "NaN" not in css
            assert "undefined" not in css
