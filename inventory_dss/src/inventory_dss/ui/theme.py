"""Production Theme Engine and 3-Tier Design System Tokens for Inventory DSS.

This module provides a production-grade 3-tier design system implementation:
- 1. Primitive Tokens: Zinc and Slate neutral scales (50-950), Crimson, Amber,
     Emerald, Sky, Purple, and Electric Indigo semantic scales, typography tokens
     (Inter sans-serif, JetBrains Mono monospace with tabular numerals), concentric
     radii mathematics (R_outer = R_inner + padding), 4px/8px baseline grid, and
     elevation shadow tokens.
- 2. Semantic Tokens: Layer-0 canvas, Layer-1 card, Layer-2 popover/hover surfaces,
     text and border contrast hierarchies, domain inventory status tokens
     (CRITICAL with pulse, REORDER_NEEDED, OPTIMAL, EXCESS), and epistemic trust
     tiers (ALGORITHMIC, HEURISTIC, EXPLORATORY).
- 3. Component Tokens: Tokens for KPI cards, data tables, status badges, reasoning
     cards, what-if controls, and chart containers.
- 4. Theme Engine: Dark and Light modes, CSS generation, and seamless Streamlit DOM
     injection via `inject_custom_css()`.
- 5. Accessibility Engine: Exact relative luminance and contrast ratio calculation
     per WCAG 2.2 specifications, with automated validation helpers (`verify_wcag_aa`).
- 6. Plotly Theming: High-contrast, transparent `go.layout.Template` generator
     synchronized with theme tokens.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

try:
    import streamlit as st
except ImportError:
    st = None  # Allow standalone imports in non-Streamlit environments or test suites

try:
    import plotly.graph_objects as go
except ImportError:
    go = None  # Allow headless environments without plotly if optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ThemeMode(str, Enum):
    """Supported color themes for Inventory DSS."""
    LIGHT = "light"
    DARK = "dark"


class InventoryStatus(str, Enum):
    """Core domain inventory health statuses."""
    CRITICAL = "CRITICAL"            # Stockout active or imminent (< SS or = 0)
    REORDER_NEEDED = "REORDER_NEEDED"  # Stock <= ROP, replenishment required
    OPTIMAL = "OPTIMAL"              # Buffer normal (ROP < Stock <= MaxNorm)
    EXCESS = "EXCESS"                # Overstock, capital freeze risk (> MaxNorm)


class EpistemicTrustTier(str, Enum):
    """Explainable AI / DSS decision confidence and validation tiers."""
    ALGORITHMIC = "ALGORITHMIC"    # Mathematical proof (KKT optimization, analytical EOQ)
    HEURISTIC = "HEURISTIC"        # Statistical/MCDA fit (TOPSIS, AHP, Holt-Winters, ARIMA)
    EXPLORATORY = "EXPLORATORY"    # Speculative / Simulation (What-If slider shock, LLM notes)


# ---------------------------------------------------------------------------
# 1. Primitive Tokens
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ColorScale:
    """11-step chromatic or neutral color ramp (50 to 950)."""
    c50: str
    c100: str
    c200: str
    c300: str
    c400: str
    c500: str
    c600: str
    c700: str
    c800: str
    c900: str
    c950: str


# Neutral Palettes
ZINC_PALETTE = ColorScale(
    c50="#FAFAFA", c100="#F4F4F5", c200="#E4E4E7", c300="#D4D4D8",
    c400="#A1A1AA", c500="#71717A", c600="#52525B", c700="#3F3F46",
    c800="#27272A", c900="#18181B", c950="#09090B"
)

SLATE_PALETTE = ColorScale(
    c50="#F8FAFC", c100="#F1F5F9", c200="#E2E8F0", c300="#CBD5E1",
    c400="#94A3B8", c500="#64748B", c600="#475569", c700="#334155",
    c800="#1E293B", c900="#0F172A", c950="#020617"
)

# Semantic Primitives
CRIMSON_PALETTE = ColorScale(
    c50="#FEF2F2", c100="#FEE2E2", c200="#FECACA", c300="#FCA5A5",
    c400="#F87171", c500="#EF4444", c600="#DC2626", c700="#B91C1C",
    c800="#991B1B", c900="#7F1D1D", c950="#450A0A"
)

AMBER_PALETTE = ColorScale(
    c50="#FFFBEB", c100="#FEF3C7", c200="#FDE68A", c300="#FCD34D",
    c400="#FBBF24", c500="#F59E0B", c600="#D97706", c700="#B45309",
    c800="#92400E", c900="#78350F", c950="#451A03"
)

EMERALD_PALETTE = ColorScale(
    c50="#ECFDF5", c100="#D1FAE5", c200="#A7F3D0", c300="#6EE7B7",
    c400="#34D399", c500="#10B981", c600="#059669", c700="#047857",
    c800="#065F46", c900="#064E3B", c950="#022C22"
)

SKY_PALETTE = ColorScale(
    c50="#F0F9FF", c100="#E0F2FE", c200="#BAE6FD", c300="#7DD3FC",
    c400="#38BDF8", c500="#0EA5E9", c600="#0284C7", c700="#0369A1",
    c800="#075985", c900="#0C4A6E", c950="#082F49"
)

PURPLE_PALETTE = ColorScale(
    c50="#FAF5FF", c100="#F3E8FF", c200="#E9D5FF", c300="#D8B4FE",
    c400="#C084FC", c500="#A855F7", c600="#9333EA", c700="#7E22CE",
    c800="#6B21A8", c900="#581C87", c950="#3B0764"
)

INDIGO_PALETTE = ColorScale(
    c50="#EEF2FF", c100="#E0E7FF", c200="#C7D2FE", c300="#A5B4FC",
    c400="#818CF8", c500="#6366F1", c600="#4F46E5", c700="#4338CA",
    c800="#3730A3", c900="#312E81", c950="#1E1B4B"
)


@dataclass(frozen=True)
class TypographyTokens:
    """Font families, scale, line-heights, weights, and tabular figures."""
    font_sans: str = (
        "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
    )
    font_mono: str = (
        "'JetBrains Mono', 'SF Mono', Consolas, 'Liberation Mono', Menlo, monospace"
    )
    font_tabular_settings: str = '"tnum" 1, "zero" 1'

    # Font sizes
    size_xs: str = "0.75rem"      # 12px
    size_sm: str = "0.875rem"     # 14px
    size_base: str = "1.0rem"     # 16px
    size_lg: str = "1.125rem"     # 18px
    size_xl: str = "1.25rem"      # 20px
    size_2xl: str = "1.5rem"      # 24px
    size_3xl: str = "1.875rem"    # 30px
    size_4xl: str = "2.25rem"     # 36px

    # Line heights
    leading_tight: str = "1.25"
    leading_normal: str = "1.5"
    leading_relaxed: str = "1.625"

    # Font weights
    weight_normal: int = 400
    weight_medium: int = 500
    weight_semibold: int = 600
    weight_bold: int = 700


@dataclass(frozen=True)
class RadiiTokens:
    """Concentric radii scale and mathematical derivation helper methods."""
    r_none: str = "0px"
    r_xs: str = "2px"
    r_sm: str = "4px"
    r_md: str = "8px"
    r_lg: str = "12px"
    r_xl: str = "16px"
    r_2xl: str = "24px"
    r_full: str = "9999px"

    @staticmethod
    def calculate_concentric_radius(outer_radius_px: float, padding_px: float) -> float:
        """Concentric radii mathematics: R_outer = R_inner + padding => R_inner = max(0, R_outer - padding).

        Prevents optical corner distortion when nesting containers.
        """
        return max(0.0, outer_radius_px - padding_px)

    @staticmethod
    def calculate_inner_radius(outer_radius_px: float, padding_px: float) -> float:
        """Alias for calculate_concentric_radius."""
        return max(0.0, outer_radius_px - padding_px)

    @staticmethod
    def calculate_outer_radius(inner_radius_px: float, padding_px: float) -> float:
        """Calculate outer container radius: R_outer = R_inner + padding."""
        return max(0.0, inner_radius_px + padding_px)


@dataclass(frozen=True)
class SpacingTokens:
    """4px/8px baseline grid system."""
    space_0: str = "0px"
    space_1: str = "4px"
    space_2: str = "8px"
    space_3: str = "12px"
    space_4: str = "16px"
    space_5: str = "20px"
    space_6: str = "24px"
    space_8: str = "32px"
    space_10: str = "40px"
    space_12: str = "48px"
    space_16: str = "64px"


@dataclass(frozen=True)
class ShadowTokens:
    """Elevation shadows and ambient status glow rings."""
    elevation_none: str
    elevation_xs: str
    elevation_sm: str
    elevation_md: str
    elevation_lg: str
    elevation_xl: str
    glow_brand: str
    glow_critical: str
    glow_optimal: str


@dataclass(frozen=True)
class PrimitiveTokens:
    """Container for all primitive design tokens."""
    zinc: ColorScale = ZINC_PALETTE
    slate: ColorScale = SLATE_PALETTE
    crimson: ColorScale = CRIMSON_PALETTE
    amber: ColorScale = AMBER_PALETTE
    emerald: ColorScale = EMERALD_PALETTE
    sky: ColorScale = SKY_PALETTE
    purple: ColorScale = PURPLE_PALETTE
    indigo: ColorScale = INDIGO_PALETTE
    typography: TypographyTokens = field(default_factory=TypographyTokens)
    radii: RadiiTokens = field(default_factory=RadiiTokens)
    spacing: SpacingTokens = field(default_factory=SpacingTokens)


# ---------------------------------------------------------------------------
# 2. Semantic Tokens
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SurfaceTokens:
    """Layered surface elevation hierarchy."""
    layer_0: str      # Main Canvas / App Background
    layer_1: str      # Cards, Sidebars, Main Panels
    layer_2: str      # Nested Cards, Dropdowns, Table Row Hovers, Modals
    layer_accent: str # Subtle contextual accent tint


@dataclass(frozen=True)
class TextTokens:
    """Text contrast and semantic hierarchy."""
    primary: str
    secondary: str
    muted: str
    inverse: str
    accent: str


@dataclass(frozen=True)
class BorderTokens:
    """Border contrast and interactive focus hierarchy."""
    subtle: str       # Decorative inner dividers
    default: str      # Standard card borders
    strong: str       # Interactive inputs / table outer borders (meets WCAG 1.4.11)
    focus: str        # Active focus ring / keyboard navigation


@dataclass(frozen=True)
class StatusColorTokens:
    """Composite color tokens for inventory health states."""
    fg: str
    bg: str
    border: str
    solid: str
    pulse: str

    @property
    def fill(self) -> str:
        return self.solid


@dataclass(frozen=True)
class TrustTierColorTokens:
    """Explainable AI / DSS decision transparency badges."""
    fg: str
    bg: str
    border: str
    badge_label: str


@dataclass(frozen=True)
class SemanticTokens:
    """Container for all semantic design tokens."""
    surfaces: SurfaceTokens
    text: TextTokens
    borders: BorderTokens
    brand_primary: str
    brand_hover: str
    brand_active: str
    status_critical: StatusColorTokens
    status_reorder: StatusColorTokens
    status_optimal: StatusColorTokens
    status_excess: StatusColorTokens
    trust_algorithmic: TrustTierColorTokens
    trust_heuristic: TrustTierColorTokens
    trust_exploratory: TrustTierColorTokens


# ---------------------------------------------------------------------------
# 3. Component Tokens
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KpiCardTokens:
    bg: str
    border: str
    radius: str
    padding: str
    shadow: str
    title_color: str
    value_color: str
    delta_up: str
    delta_down: str
    progress_track: str
    progress_bar: str


@dataclass(frozen=True)
class DataTableTokens:
    bg: str
    header_bg: str
    header_text: str
    row_hover_bg: str
    row_border: str
    cell_padding: str
    num_font_settings: str


@dataclass(frozen=True)
class BadgeTokens:
    radius: str
    padding: str
    font_size: str
    font_weight: int
    dot_size: str


@dataclass(frozen=True)
class ReasoningCardTokens:
    bg: str
    border_left_width: str
    radius: str
    padding: str
    title_color: str
    text_color: str


@dataclass(frozen=True)
class ControlTokens:
    track_bg: str
    thumb_color: str
    active_accent: str
    border_focus: str


@dataclass(frozen=True)
class ChartTokens:
    bg: str
    grid_color: str
    text_color: str
    border_color: str
    confidence_band_fill: str


@dataclass(frozen=True)
class ComponentTokens:
    """Container for all component-level design tokens."""
    kpi_card: KpiCardTokens
    data_table: DataTableTokens
    badge: BadgeTokens
    reasoning_card: ReasoningCardTokens
    controls: ControlTokens
    chart: ChartTokens


# ---------------------------------------------------------------------------
# Complete DSS Theme Container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DSSTheme:
    """Unified container for all 3 token tiers."""
    mode: ThemeMode
    surfaces: SurfaceTokens
    text: TextTokens
    borders: BorderTokens
    brand_primary: str
    brand_hover: str
    brand_active: str
    status_critical: StatusColorTokens
    status_reorder: StatusColorTokens
    status_optimal: StatusColorTokens
    status_excess: StatusColorTokens
    trust_algorithmic: TrustTierColorTokens
    trust_heuristic: TrustTierColorTokens
    trust_exploratory: TrustTierColorTokens
    shadows: ShadowTokens
    typography: TypographyTokens = field(default_factory=TypographyTokens)
    radii: RadiiTokens = field(default_factory=RadiiTokens)
    spacing: SpacingTokens = field(default_factory=SpacingTokens)

    @property
    def accent(self) -> Any:
        class AccentHelper:
            primary = self.brand_primary
            hover = self.brand_hover
            active = self.brand_active
        return AccentHelper()

    @property
    def status(self) -> Any:
        class StatusHelper:
            critical = self.status_critical
            reorder_needed = self.status_reorder
            reorder = self.status_reorder
            optimal = self.status_optimal
            excess = self.status_excess
        return StatusHelper()

    @property
    def charts(self) -> Any:
        class ChartHelper:
            def __init__(self) -> None:
                self.categorical_sequence = [
                    "#6366F1", "#10B981", "#F59E0B", "#EF4444", "#0EA5E9", "#8B5CF6", "#64748B", "#EC4899"
                ]
        return ChartHelper()

    @property
    def primitives(self) -> PrimitiveTokens:
        """Primitive tokens bundle."""
        return PrimitiveTokens(
            zinc=ZINC_PALETTE,
            slate=SLATE_PALETTE,
            crimson=CRIMSON_PALETTE,
            amber=AMBER_PALETTE,
            emerald=EMERALD_PALETTE,
            sky=SKY_PALETTE,
            purple=PURPLE_PALETTE,
            indigo=INDIGO_PALETTE,
            typography=self.typography,
            radii=self.radii,
            spacing=self.spacing,
        )

    @property
    def semantics(self) -> SemanticTokens:
        """Semantic tokens bundle."""
        return SemanticTokens(
            surfaces=self.surfaces,
            text=self.text,
            borders=self.borders,
            brand_primary=self.brand_primary,
            brand_hover=self.brand_hover,
            brand_active=self.brand_active,
            status_critical=self.status_critical,
            status_reorder=self.status_reorder,
            status_optimal=self.status_optimal,
            status_excess=self.status_excess,
            trust_algorithmic=self.trust_algorithmic,
            trust_heuristic=self.trust_heuristic,
            trust_exploratory=self.trust_exploratory,
        )

    @property
    def components(self) -> ComponentTokens:
        """Component tokens bundle."""
        return ComponentTokens(
            kpi_card=self.kpi_card,
            data_table=self.data_table,
            badge=self.badge,
            reasoning_card=self.reasoning_card,
            controls=self.controls,
            chart=self.chart,
        )

    @property
    def kpi_card(self) -> KpiCardTokens:
        return KpiCardTokens(
            bg=self.surfaces.layer_1,
            border=self.borders.subtle,
            radius=self.radii.r_lg,
            padding=self.spacing.space_4,
            shadow=self.shadows.elevation_sm,
            title_color=self.text.secondary,
            value_color=self.text.primary,
            delta_up=self.status_optimal.fg,
            delta_down=self.status_critical.fg,
            progress_track=self.surfaces.layer_2,
            progress_bar=self.brand_primary,
        )

    @property
    def data_table(self) -> DataTableTokens:
        return DataTableTokens(
            bg=self.surfaces.layer_1,
            header_bg=self.surfaces.layer_2,
            header_text=self.text.secondary,
            row_hover_bg=self.surfaces.layer_2,
            row_border=self.borders.subtle,
            cell_padding="8px 12px",
            num_font_settings=self.typography.font_tabular_settings,
        )

    @property
    def badge(self) -> BadgeTokens:
        return BadgeTokens(
            radius=self.radii.r_full,
            padding="3px 10px",
            font_size=self.typography.size_xs,
            font_weight=self.typography.weight_semibold,
            dot_size="6px",
        )

    @property
    def reasoning_card(self) -> ReasoningCardTokens:
        return ReasoningCardTokens(
            bg=self.surfaces.layer_1,
            border_left_width="4px",
            radius=self.radii.r_md,
            padding=self.spacing.space_4,
            title_color=self.text.primary,
            text_color=self.text.secondary,
        )

    @property
    def controls(self) -> ControlTokens:
        return ControlTokens(
            track_bg=self.surfaces.layer_2,
            thumb_color=self.brand_primary,
            active_accent=self.brand_primary,
            border_focus=self.borders.focus,
        )

    @property
    def chart(self) -> ChartTokens:
        return ChartTokens(
            bg="rgba(0,0,0,0)",
            grid_color=self.borders.subtle,
            text_color=self.text.secondary,
            border_color=self.borders.subtle,
            confidence_band_fill=(
                "rgba(16, 185, 129, 0.18)"
                if self.mode == ThemeMode.DARK
                else "rgba(5, 150, 105, 0.12)"
            ),
        )


# Alias for backward and architectural compatibility
Theme = DSSTheme


# ---------------------------------------------------------------------------
# Theme Builders
# ---------------------------------------------------------------------------

def get_dark_theme() -> DSSTheme:
    """Build production-grade Dark Mode theme (Zinc/Slate foundation)."""
    return DSSTheme(
        mode=ThemeMode.DARK,
        surfaces=SurfaceTokens(
            layer_0="#09090B",       # Zinc 950 deep canvas
            layer_1="#18181B",       # Zinc 900 card background
            layer_2="#27272A",       # Zinc 800 hovered rows / nested cards
            layer_accent="#1E1B4B",   # Indigo 950 subtle wash
        ),
        text=TextTokens(
            primary="#F4F4F5",       # Zinc 100 (CR 16.12:1 on Zinc 900, AA PASS)
            secondary="#A1A1AA",     # Zinc 400 (CR 6.91:1 on Zinc 900, AA PASS)
            muted="#9CA3AF",         # Gray 400 (CR 6.98:1 on Zinc 900, AA PASS)
            inverse="#09090B",       # Zinc 950
            accent="#818CF8",        # Indigo 400 (CR 5.94:1 on Zinc 900, AA PASS)
        ),
        borders=BorderTokens(
            subtle="#27272A",        # Zinc 800 (clean subtle dividers)
            default="#3F3F46",       # Zinc 700 (card frames)
            strong="#71717A",        # Zinc 500 (CR 3.67:1 on Zinc 900, WCAG 1.4.11 PASS)
            focus="#818CF8",         # Indigo 400 (CR 5.94:1 on Zinc 900, high visibility)
        ),
        brand_primary="#4F46E5",     # Indigo 600 (CR 6.29:1 with White text, AA PASS)
        brand_hover="#6366F1",       # Indigo 500
        brand_active="#4338CA",      # Indigo 700
        status_critical=StatusColorTokens(
            fg="#F87171",            # Red 400 (CR 6.40:1 on Zinc 900, AA PASS)
            bg="#450A0A",            # Red 950 dark container
            border="#7F1D1D",        # Red 900
            solid="#EF4444",         # Red 500
            pulse="rgba(239, 68, 68, 0.4)",
        ),
        status_reorder=StatusColorTokens(
            fg="#FBBF24",            # Amber 400 (CR 10.61:1 on Zinc 900, AA PASS)
            bg="#451A03",            # Amber 950
            border="#78350F",        # Amber 900
            solid="#F59E0B",         # Amber 500
            pulse="rgba(245, 158, 11, 0.4)",
        ),
        status_optimal=StatusColorTokens(
            fg="#34D399",            # Emerald 400 (CR 9.22:1 on Zinc 900, AA PASS)
            bg="#022C22",            # Emerald 950
            border="#064E3B",        # Emerald 900
            solid="#10B981",         # Emerald 500
            pulse="rgba(16, 185, 129, 0.4)",
        ),
        status_excess=StatusColorTokens(
            fg="#C084FC",            # Purple 400 (CR 6.70:1 on Zinc 900, AA PASS)
            bg="#3B0764",            # Purple 950
            border="#581C87",        # Purple 900
            solid="#A855F7",         # Purple 500
            pulse="rgba(168, 85, 247, 0.4)",
        ),
        trust_algorithmic=TrustTierColorTokens(
            fg="#34D399",
            bg="rgba(16, 185, 129, 0.15)",
            border="#059669",
            badge_label="🛡️ Математически доказано (KKT / EOQ)",
        ),
        trust_heuristic=TrustTierColorTokens(
            fg="#818CF8",
            bg="rgba(99, 102, 241, 0.15)",
            border="#4F46E5",
            badge_label="⚖️ Статистическая эвристика (TOPSIS / HW)",
        ),
        trust_exploratory=TrustTierColorTokens(
            fg="#FBBF24",
            bg="rgba(245, 158, 11, 0.15)",
            border="#D97706",
            badge_label="🧪 Сценарная симуляция (What-If / LLM)",
        ),
        shadows=ShadowTokens(
            elevation_none="none",
            elevation_xs="0 1px 2px 0 rgba(0, 0, 0, 0.3)",
            elevation_sm="0 1px 3px 0 rgba(0, 0, 0, 0.4), 0 1px 2px -1px rgba(0, 0, 0, 0.3)",
            elevation_md="0 4px 6px -1px rgba(0, 0, 0, 0.4), 0 2px 4px -2px rgba(0, 0, 0, 0.3)",
            elevation_lg="0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -4px rgba(0, 0, 0, 0.3)",
            elevation_xl="0 20px 25px -5px rgba(0, 0, 0, 0.4), 0 8px 10px -6px rgba(0, 0, 0, 0.3)",
            glow_brand="0 0 0 1px rgba(99, 102, 241, 0.4), 0 0 12px rgba(99, 102, 241, 0.25)",
            glow_critical="0 0 0 1px rgba(239, 68, 68, 0.4), 0 0 12px rgba(239, 68, 68, 0.25)",
            glow_optimal="0 0 0 1px rgba(16, 185, 129, 0.4), 0 0 12px rgba(16, 185, 129, 0.25)",
        ),
    )


def get_light_theme() -> DSSTheme:
    """Build production-grade Light Mode theme (Slate/Zinc foundation)."""
    return DSSTheme(
        mode=ThemeMode.LIGHT,
        surfaces=SurfaceTokens(
            layer_0="#F8FAFC",       # Slate 50 canvas
            layer_1="#FFFFFF",       # Pure white cards
            layer_2="#F1F5F9",       # Slate 100 table hover / nested
            layer_accent="#EEF2FF",   # Indigo 50 wash
        ),
        text=TextTokens(
            primary="#0F172A",       # Slate 900 (CR 17.85:1 on White, AA PASS)
            secondary="#475569",     # Slate 600 (CR 7.58:1 on White, AA PASS)
            muted="#64748B",         # Slate 500 (CR 4.76:1 on White, AA PASS)
            inverse="#FFFFFF",
            accent="#4338CA",        # Indigo 700 (CR 7.90:1 on White, AA PASS)
        ),
        borders=BorderTokens(
            subtle="#E2E8F0",        # Slate 200 (clean subtle dividers)
            default="#CBD5E1",       # Slate 300 (card frames)
            strong="#64748B",        # Slate 500 (CR 4.76:1 on White, WCAG 1.4.11 PASS)
            focus="#4F46E5",         # Indigo 600 (CR 6.29:1 on White, high visibility)
        ),
        brand_primary="#4F46E5",     # Indigo 600 (CR 6.29:1 with White text, AA PASS)
        brand_hover="#4338CA",       # Indigo 700
        brand_active="#3730A3",      # Indigo 800
        status_critical=StatusColorTokens(
            fg="#B91C1C",            # Red 700 (CR 6.47:1 on White, AA PASS)
            bg="#FEF2F2",            # Red 50
            border="#FCA5A5",        # Red 300
            solid="#DC2626",         # Red 600
            pulse="rgba(220, 38, 38, 0.3)",
        ),
        status_reorder=StatusColorTokens(
            fg="#B45309",            # Amber 700 (CR 5.02:1 on White, AA PASS)
            bg="#FFFBEB",            # Amber 50
            border="#FCD34D",        # Amber 300
            solid="#D97706",         # Amber 600
            pulse="rgba(217, 119, 6, 0.3)",
        ),
        status_optimal=StatusColorTokens(
            fg="#047857",            # Emerald 700 (CR 5.48:1 on White, AA PASS)
            bg="#ECFDF5",            # Emerald 50
            border="#6EE7B7",        # Emerald 300
            solid="#059669",         # Emerald 600
            pulse="rgba(5, 150, 105, 0.3)",
        ),
        status_excess=StatusColorTokens(
            fg="#7E22CE",            # Purple 700 (CR 6.98:1 on White, AA PASS)
            bg="#FAF5FF",            # Purple 50
            border="#D8B4FE",        # Purple 300
            solid="#9333EA",         # Purple 600
            pulse="rgba(147, 51, 234, 0.3)",
        ),
        trust_algorithmic=TrustTierColorTokens(
            fg="#047857",
            bg="#ECFDF5",
            border="#6EE7B7",
            badge_label="🛡️ Математически доказано (KKT / EOQ)",
        ),
        trust_heuristic=TrustTierColorTokens(
            fg="#4338CA",
            bg="#EEF2FF",
            border="#A5B4FC",
            badge_label="⚖️ Статистическая эвристика (TOPSIS / HW)",
        ),
        trust_exploratory=TrustTierColorTokens(
            fg="#B45309",
            bg="#FFFBEB",
            border="#FCD34D",
            badge_label="🧪 Сценарная симуляция (What-If / LLM)",
        ),
        shadows=ShadowTokens(
            elevation_none="none",
            elevation_xs="0 1px 2px 0 rgba(15, 23, 42, 0.05)",
            elevation_sm="0 1px 3px 0 rgba(15, 23, 42, 0.08), 0 1px 2px -1px rgba(15, 23, 42, 0.06)",
            elevation_md="0 4px 6px -1px rgba(15, 23, 42, 0.08), 0 2px 4px -2px rgba(15, 23, 42, 0.06)",
            elevation_lg="0 10px 15px -3px rgba(15, 23, 42, 0.08), 0 4px 6px -4px rgba(15, 23, 42, 0.06)",
            elevation_xl="0 20px 25px -5px rgba(15, 23, 42, 0.08), 0 8px 10px -6px rgba(15, 23, 42, 0.06)",
            glow_brand="0 0 0 1px rgba(79, 70, 229, 0.3), 0 0 12px rgba(79, 70, 229, 0.15)",
            glow_critical="0 0 0 1px rgba(220, 38, 38, 0.3), 0 0 12px rgba(220, 38, 38, 0.15)",
            glow_optimal="0 0 0 1px rgba(5, 150, 105, 0.3), 0 0 12px rgba(5, 150, 105, 0.15)",
        ),
    )


def get_theme(mode: ThemeMode | str = ThemeMode.DARK) -> DSSTheme:
    """Return DSSTheme for given mode (case-insensitive string or enum)."""
    if isinstance(mode, ThemeMode):
        if mode == ThemeMode.LIGHT:
            return get_light_theme()
        elif mode == ThemeMode.DARK:
            return get_dark_theme()
        raise ValueError(f"Invalid theme mode: {mode}")

    raw_str = str(mode).strip().lower()
    if "." in raw_str:
        raw_str = raw_str.split(".")[-1]
    if raw_str in ("light", "theme_light", "light_theme"):
        return get_light_theme()
    elif raw_str in ("dark", "theme_dark", "dark_theme"):
        return get_dark_theme()
    raise ValueError(f"Invalid theme mode: {mode}")


# ---------------------------------------------------------------------------
# WCAG 2.2 AA Contrast Verification Functions
# ---------------------------------------------------------------------------

def srgb_to_linear(channel: int) -> float:
    """Convert sRGB 8-bit integer channel (0-255) to linear color space."""
    c = channel / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_rgb(hex_code: str) -> tuple[int, int, int]:
    """Parse #RGB or #RRGGBB hex string to 3-tuple integer RGB."""
    if not isinstance(hex_code, str):
        raise TypeError(f"Invalid hex code type: {type(hex_code)}")
    h = hex_code.strip().lstrip("#")
    if len(h) == 3:
        h = "".join([c * 2 for c in h])
    elif len(h) != 6:
        raise ValueError(f"Invalid hex code length: {hex_code}")
    if not all(c in "0123456789abcdefABCDEF" for c in h):
        raise ValueError(f"Invalid hex characters: {hex_code}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def calculate_relative_luminance(hex_code: str) -> float:
    """Calculate WCAG 2.2 relative luminance L = 0.2126*R + 0.7152*G + 0.0722*B."""
    r, g, b = hex_to_rgb(hex_code)
    r_lin = srgb_to_linear(r)
    g_lin = srgb_to_linear(g)
    b_lin = srgb_to_linear(b)
    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def calculate_contrast_ratio(hex1: str, hex2: str) -> float:
    """Calculate WCAG contrast ratio (L1 + 0.05) / (L2 + 0.05)."""
    l1 = calculate_relative_luminance(hex1)
    l2 = calculate_relative_luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def verify_wcag_compliance(hex_fg: str, hex_bg: str, target_ratio: float = 4.5) -> tuple[float, bool]:
    """Check whether contrast ratio meets target threshold (e.g. 4.5 for text, 3.0 for UI)."""
    ratio = calculate_contrast_ratio(hex_fg, hex_bg)
    return round(ratio, 2), ratio >= target_ratio


def verify_wcag_aa(hex_fg: str, hex_bg: str, is_large_or_ui: bool = False) -> bool:
    """Check whether the contrast between hex_fg and hex_bg satisfies WCAG 2.2 AA.

    Normal text requires at least 4.5:1 contrast ratio.
    Large text (>=18pt or >=14pt bold) and non-text UI components require at least 3.0:1.
    """
    ratio = calculate_contrast_ratio(hex_fg, hex_bg)
    threshold = 3.0 if is_large_or_ui else 4.5
    return ratio >= threshold


def verify_theme_wcag(theme: DSSTheme) -> dict[str, tuple[float, bool]]:
    """Audit all key text and UI contrast pairings in theme against WCAG 2.2 AA.

    Target: >= 4.5:1 for regular text, >= 3.0:1 for graphical UI elements.
    """
    s1 = theme.surfaces.layer_1
    s0 = theme.surfaces.layer_0

    pairs: list[tuple[str, str, str, float]] = [
        ("Text Primary on Card (Layer 1)", theme.text.primary, s1, 4.5),
        ("Text Primary on Canvas (Layer 0)", theme.text.primary, s0, 4.5),
        ("Text Secondary on Card", theme.text.secondary, s1, 4.5),
        ("Text Muted on Card", theme.text.muted, s1, 4.5),
        ("Brand Button White Text", "#FFFFFF", theme.brand_primary, 4.5),
        ("Critical Status FG on Card", theme.status_critical.fg, s1, 4.5),
        ("Critical Status FG on Status BG", theme.status_critical.fg, theme.status_critical.bg, 4.5),
        ("Reorder Status FG on Card", theme.status_reorder.fg, s1, 4.5),
        ("Reorder Status FG on Status BG", theme.status_reorder.fg, theme.status_reorder.bg, 4.5),
        ("Optimal Status FG on Card", theme.status_optimal.fg, s1, 4.5),
        ("Optimal Status FG on Status BG", theme.status_optimal.fg, theme.status_optimal.bg, 4.5),
        ("Excess Status FG on Card", theme.status_excess.fg, s1, 4.5),
        ("Excess Status FG on Status BG", theme.status_excess.fg, theme.status_excess.bg, 4.5),
        ("Active Border on Card (UI 1.4.11)", theme.borders.strong, s1, 3.0),
    ]

    report: dict[str, tuple[float, bool]] = {}
    for label, fg, bg, threshold in pairs:
        cr = calculate_contrast_ratio(fg, bg)
        report[label] = (round(cr, 2), cr >= threshold)
    return report


# ---------------------------------------------------------------------------
# CSS Injection Engine for Streamlit
# ---------------------------------------------------------------------------

def generate_theme_css(theme: DSSTheme) -> str:
    """Generate comprehensive CSS rules and custom properties for the theme."""
    s = theme.surfaces
    t = theme.text
    b = theme.borders
    r = theme.radii
    sp = theme.spacing
    sh = theme.shadows
    ty = theme.typography

    return f"""
/* ==========================================================================
   INVENTORY DSS DESIGN SYSTEM TOKENS & OVERRIDES ({theme.mode.value.upper()} MODE)
   ========================================================================== */

:root {{
    /* 1. Primitive & Semantic Surfaces */
    --surface-layer-0: {s.layer_0};
    --surface-layer-1: {s.layer_1};
    --surface-layer-2: {s.layer_2};
    --surface-accent: {s.layer_accent};

    /* 2. Text Tokens */
    --text-primary: {t.primary};
    --text-secondary: {t.secondary};
    --text-muted: {t.muted};
    --text-inverse: {t.inverse};
    --text-accent: {t.accent};

    /* 3. Border Tokens */
    --border-subtle: {b.subtle};
    --border-default: {b.default};
    --border-strong: {b.strong};
    --border-focus: {b.focus};

    /* 4. Brand Accent */
    --brand-primary: {theme.brand_primary};
    --brand-hover: {theme.brand_hover};
    --brand-active: {theme.brand_active};

    /* 5. Inventory DSS Domain Status Tokens */
    --status-critical-fg: {theme.status_critical.fg};
    --status-critical-bg: {theme.status_critical.bg};
    --status-critical-border: {theme.status_critical.border};
    --status-critical-solid: {theme.status_critical.solid};
    --status-critical-pulse: {theme.status_critical.pulse};

    --status-reorder-fg: {theme.status_reorder.fg};
    --status-reorder-bg: {theme.status_reorder.bg};
    --status-reorder-border: {theme.status_reorder.border};
    --status-reorder-solid: {theme.status_reorder.solid};
    --status-reorder-pulse: {theme.status_reorder.pulse};

    --status-optimal-fg: {theme.status_optimal.fg};
    --status-optimal-bg: {theme.status_optimal.bg};
    --status-optimal-border: {theme.status_optimal.border};
    --status-optimal-solid: {theme.status_optimal.solid};
    --status-optimal-pulse: {theme.status_optimal.pulse};

    --status-excess-fg: {theme.status_excess.fg};
    --status-excess-bg: {theme.status_excess.bg};
    --status-excess-border: {theme.status_excess.border};
    --status-excess-solid: {theme.status_excess.solid};
    --status-excess-pulse: {theme.status_excess.pulse};

    /* 6. Typography */
    --font-sans: {ty.font_sans};
    --font-mono: {ty.font_mono};
    --font-tabular: {ty.font_tabular_settings};
    --font-tabular-settings: {ty.font_tabular_settings};

    /* 7. Concentric Radii */
    --radius-none: {r.r_none};
    --radius-xs: {r.r_xs};
    --radius-sm: {r.r_sm};
    --radius-md: {r.r_md};
    --radius-lg: {r.r_lg};
    --radius-xl: {r.r_xl};
    --radius-2xl: {r.r_2xl};
    --radius-full: {r.r_full};

    /* 8. Elevation Shadows */
    --elevation-none: {sh.elevation_none};
    --elevation-xs: {sh.elevation_xs};
    --elevation-sm: {sh.elevation_sm};
    --elevation-md: {sh.elevation_md};
    --elevation-lg: {sh.elevation_lg};
    --elevation-xl: {sh.elevation_xl};
    --glow-brand: {sh.glow_brand};
    --glow-critical: {sh.glow_critical};
    --glow-optimal: {sh.glow_optimal};
}}

/* Global Resets & Typography (Clean Enterprise Glassmorphism) */
.stApp {{
    background-color: var(--surface-layer-0) !important;
    background-image: 
        radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.08) 0px, transparent 50%),
        radial-gradient(at 100% 0%, rgba(56, 189, 248, 0.08) 0px, transparent 50%),
        radial-gradient(at 50% 100%, rgba(241, 245, 249, 0.85) 0px, transparent 60%) !important;
    background-attachment: fixed !important;
    color: var(--text-primary) !important;
    font-family: var(--font-sans) !important;
}}

/* Tabular Numerals Enforcement */
.tabular-nums, [data-testid="stMetricValue"], .dss-mono, .stDataFrame, .dss-number {{
    font-variant-numeric: tabular-nums !important;
    font-feature-settings: "tnum" 1, "zero" 1 !important;
}}

/* Sidebar Customization - Frosted Glass Panel */
[data-testid="stSidebar"] {{
    background: rgba(255, 255, 255, 0.72) !important;
    backdrop-filter: blur(20px) saturate(190%) !important;
    -webkit-backdrop-filter: blur(20px) saturate(190%) !important;
    border-right: 1px solid rgba(226, 232, 240, 0.85) !important;
    box-shadow: 4px 0 24px rgba(15, 23, 42, 0.02) !important;
}}

/* Native Metric Card Customization - Floating Glass Tile */
[data-testid="stMetric"] {{
    background: rgba(255, 255, 255, 0.8) !important;
    backdrop-filter: blur(16px) saturate(180%) !important;
    -webkit-backdrop-filter: blur(16px) saturate(180%) !important;
    border: 1px solid rgba(255, 255, 255, 0.95) !important;
    border-radius: var(--radius-xl) !important;
    padding: 1.25rem 1.5rem !important;
    box-shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.05), 0 2px 6px -1px rgba(15, 23, 42, 0.02), inset 0 1px 0 rgba(255, 255, 255, 1) !important;
    transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.2s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.2s ease !important;
}}

[data-testid="stMetric"]:hover {{
    transform: translateY(-2px) !important;
    box-shadow: 0 12px 32px -4px rgba(15, 23, 42, 0.08), 0 4px 12px -2px rgba(15, 23, 42, 0.03), inset 0 1px 0 rgba(255, 255, 255, 1) !important;
    border-color: rgba(99, 102, 241, 0.3) !important;
}}

[data-testid="stMetricLabel"] p {{
    color: var(--text-secondary) !important;
    font-size: {ty.size_xs} !important;
    font-weight: 600 !important;
    font-family: var(--font-sans) !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
}}

[data-testid="stMetricValue"] div {{
    color: var(--text-primary) !important;
    font-family: var(--font-sans) !important;
    font-variant-numeric: tabular-nums !important;
    font-size: 1.85rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.03em !important;
}}

/* Buttons - Stripe & Vercel Tactile Micro-Interactions */
button[kind="primary"] {{
    background: linear-gradient(180deg, #1E293B 0%, #0F172A 100%) !important;
    color: #FFFFFF !important;
    border-radius: 10px !important;
    border: 1px solid rgba(255, 255, 255, 0.18) !important;
    font-family: var(--font-sans) !important;
    font-weight: 600 !important;
    text-transform: none !important;
    letter-spacing: normal !important;
    box-shadow: 0 2px 4px rgba(15, 23, 42, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.25) !important;
    transition: transform 0.12s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.12s ease, background 0.15s ease !important;
}}

button[kind="primary"]:hover {{
    background: linear-gradient(180deg, #0F172A 0%, #020617 100%) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 16px rgba(15, 23, 42, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.35) !important;
}}

button[kind="primary"]:active {{
    transform: scale(0.98) !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.1) !important;
}}

button[kind="secondary"] {{
    background: rgba(255, 255, 255, 0.85) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    color: var(--text-primary) !important;
    border: 1px solid rgba(203, 213, 225, 0.8) !important;
    border-radius: 10px !important;
    font-family: var(--font-sans) !important;
    font-weight: 500 !important;
    text-transform: none !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), inset 0 1px 0 #FFFFFF !important;
    transition: transform 0.12s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.12s ease, background 0.15s ease !important;
}}

button[kind="secondary"]:hover {{
    background: #FFFFFF !important;
    border-color: #94A3B8 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06) !important;
}}

button[kind="secondary"]:active {{
    transform: scale(0.98) !important;
}}

/* Data Tables - Frosted Glass Container */
.stDataFrame {{
    border-radius: var(--radius-xl) !important;
    border: 1px solid rgba(226, 232, 240, 0.9) !important;
    background: rgba(255, 255, 255, 0.85) !important;
    backdrop-filter: blur(16px) !important;
    -webkit-backdrop-filter: blur(16px) !important;
    box-shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.04), inset 0 1px 0 #FFFFFF !important;
    overflow: hidden !important;
}}

/* Expanders - Glass Panels */
div[data-testid="stExpander"] {{
    border: 1px solid rgba(226, 232, 240, 0.9) !important;
    border-radius: var(--radius-xl) !important;
    background: rgba(255, 255, 255, 0.8) !important;
    backdrop-filter: blur(16px) saturate(180%) !important;
    -webkit-backdrop-filter: blur(16px) saturate(180%) !important;
    box-shadow: 0 4px 16px -2px rgba(15, 23, 42, 0.03), inset 0 1px 0 #FFFFFF !important;
}}

/* Alerts & Banners */
div[data-testid="stAlert"] {{
    border: 1px solid rgba(226, 232, 240, 0.9) !important;
    border-radius: var(--radius-xl) !important;
    background: rgba(255, 255, 255, 0.85) !important;
    backdrop-filter: blur(16px) !important;
    box-shadow: 0 4px 16px -2px rgba(15, 23, 42, 0.04), inset 0 1px 0 #FFFFFF !important;
    font-family: var(--font-sans) !important;
}}

/* Form Controls & Selectboxes */
div[data-baseweb="select"] > div, .stTextInput > div > div, div[data-baseweb="input"] > div {{
    background: rgba(255, 255, 255, 0.9) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(203, 213, 225, 0.85) !important;
    border-radius: 10px !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), inset 0 1px 0 #FFFFFF !important;
}}

/* Tabs */
button[data-baseweb="tab"] {{
    border-radius: 8px !important;
    padding: 8px 16px !important;
    font-weight: 500 !important;
    color: var(--text-secondary) !important;
    transition: all 0.15s ease !important;
}}
button[data-baseweb="tab"][aria-selected="true"] {{
    background: rgba(255, 255, 255, 0.95) !important;
    backdrop-filter: blur(12px) !important;
    color: var(--text-primary) !important;
    font-weight: 600 !important;
    box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06), inset 0 1px 0 #FFFFFF !important;
    border: 1px solid rgba(226, 232, 240, 0.9) !important;
}}

/* ==========================================================================
   DSS Custom Component CSS Classes (Clean Enterprise Glassmorphism)
   ========================================================================== */

.dss-kpi-card {{
    background: rgba(255, 255, 255, 0.8);
    backdrop-filter: blur(16px) saturate(180%);
    -webkit-backdrop-filter: blur(16px) saturate(180%);
    border: 1px solid rgba(255, 255, 255, 0.95);
    border-radius: var(--radius-xl);
    padding: {sp.space_4};
    box-shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.05), inset 0 1px 0 #FFFFFF;
    display: flex;
    flex-direction: column;
    gap: {sp.space_2};
    transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.2s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.2s ease;
}}

.dss-kpi-card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 12px 32px -4px rgba(15, 23, 42, 0.08), inset 0 1px 0 #FFFFFF;
    border-color: rgba(99, 102, 241, 0.3);
}}

.dss-kpi-title {{
    color: var(--text-secondary);
    font-size: {ty.size_xs};
    font-weight: 600;
    font-family: var(--font-sans);
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}

.dss-kpi-value {{
    color: var(--text-primary);
    font-family: var(--font-sans);
    font-variant-numeric: tabular-nums;
    font-size: {ty.size_3xl};
    font-weight: 700;
    letter-spacing: -0.03em;
}}

.dss-badge {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: var(--radius-full);
    font-size: {ty.size_xs};
    font-weight: 600;
    font-family: var(--font-sans);
    text-transform: none;
    letter-spacing: normal;
    line-height: 1.3;
    border-width: 1px;
    border-style: solid;
    backdrop-filter: blur(8px);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6);
}}

.dss-badge-critical {{
    color: var(--status-critical-fg);
    background-color: var(--status-critical-bg);
    border-color: var(--status-critical-border);
}}

.dss-badge-reorder {{
    color: var(--status-reorder-fg);
    background-color: var(--status-reorder-bg);
    border-color: var(--status-reorder-border);
}}

.dss-badge-optimal {{
    color: var(--status-optimal-fg);
    background-color: var(--status-optimal-bg);
    border-color: var(--status-optimal-border);
}}

.dss-badge-excess {{
    color: var(--status-excess-fg);
    background-color: var(--status-excess-bg);
    border-color: var(--status-excess-border);
}}

.dss-dot {{
    width: 6px;
    height: 6px;
    border-radius: var(--radius-full);
    display: inline-block;
}}

.dss-dot-critical {{
    background-color: var(--status-critical-solid);
    animation: dss-pulse 1.8s infinite ease-in-out;
}}

.dss-dot-reorder {{ background-color: var(--status-reorder-solid); }}
.dss-dot-optimal {{ background-color: var(--status-optimal-solid); }}
.dss-dot-excess {{ background-color: var(--status-excess-solid); }}

@keyframes dss-pulse {{
    0% {{
        transform: scale(0.9);
        box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7);
    }}
    70% {{
        transform: scale(1.15);
        box-shadow: 0 0 0 5px rgba(239, 68, 68, 0);
    }}
    100% {{
        transform: scale(0.9);
        box-shadow: 0 0 0 0 rgba(239, 68, 68, 0);
    }}
}}

.dss-reasoning-card {{
    background-color: var(--surface-layer-1);
    border: 1px solid var(--border-default);
    border-left: 4px solid var(--border-focus);
    border-radius: var(--radius-md);
    padding: {sp.space_4};
    box-shadow: var(--elevation-sm);
    display: flex;
    flex-direction: column;
    gap: {sp.space_2};
}}

.dss-trust-algorithmic {{
    border-left-color: #10B981 !important;
}}
.dss-trust-heuristic {{
    border-left-color: #4F46E5 !important;
}}
.dss-trust-exploratory {{
    border-left-color: #F59E0B !important;
}}

/* Clean SCM Data Table */
.dss-table-container {{
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    background-color: var(--surface-layer-1);
    box-shadow: var(--elevation-sm);
    overflow: hidden;
}}

.dss-th {{
    background-color: var(--surface-layer-2);
    border-bottom: 1px solid var(--border-default);
    border-right: 1px solid var(--border-subtle);
    font-family: var(--font-sans);
    font-size: {ty.size_xs};
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 10px 14px;
    color: var(--text-secondary);
}}

.dss-td {{
    border-bottom: 1px solid var(--border-subtle);
    border-right: 1px solid var(--border-subtle);
    font-family: var(--font-mono);
    font-size: {ty.size_sm};
    padding: 8px 14px;
    color: var(--text-primary);
}}

.dss-tr:hover {{
    background-color: var(--surface-layer-2);
}}

/* Capacity Micro-Gauge */
.dss-kpi-gauge {{
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-top: 6px;
}}

.dss-gauge-header {{
    display: flex;
    justify-content: space-between;
    font-family: var(--font-mono);
    font-size: {ty.size_xs};
    font-weight: 600;
    color: var(--text-secondary);
}}

.dss-gauge-track {{
    height: 8px;
    background-color: var(--surface-layer-2);
    border-radius: var(--radius-full);
    overflow: hidden;
}}

.dss-gauge-bar {{
    height: 100%;
    border-radius: var(--radius-full);
    transition: width 0.3s ease;
}}

.dss-gauge-optimal {{ background-color: #10B981; }}
.dss-gauge-warning {{ background-color: #F59E0B; }}
.dss-gauge-critical {{
    background: repeating-linear-gradient(
        -45deg,
        #EF4444,
        #EF4444 8px,
        #DC2626 8px,
        #DC2626 16px
    ) !important;
}}

/* Refined SCM Global Dispatch Status Bar (Floating Glass HUD) */
.dss-dispatch-bar {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 12px 20px;
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(20px) saturate(190%);
    -webkit-backdrop-filter: blur(20px) saturate(190%);
    border: 1px solid rgba(226, 232, 240, 0.9);
    border-radius: var(--radius-xl);
    box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.05), inset 0 1px 0 #FFFFFF;
    margin-bottom: 24px;
    font-family: var(--font-mono);
    font-size: 0.8125rem;
}}
.dss-dispatch-item {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
}}
.dss-dispatch-lbl {{
    color: var(--text-secondary);
    font-weight: 600;
    font-family: var(--font-sans);
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}
.dss-dispatch-val {{
    color: var(--text-primary);
    font-weight: 700;
    font-variant-numeric: tabular-nums;
}}
.dss-dispatch-val.dss-alert {{
    color: #B91C1C;
    background-color: rgba(254, 226, 226, 0.85);
    padding: 3px 10px;
    border-radius: var(--radius-full);
    border: 1px solid rgba(252, 165, 165, 0.9);
    font-weight: 600;
    font-size: 0.75rem;
}}
.dss-dispatch-val.dss-ok {{
    color: #047857;
    background-color: rgba(209, 250, 229, 0.85);
    padding: 3px 10px;
    border-radius: var(--radius-full);
    border: 1px solid rgba(110, 231, 183, 0.9);
    font-weight: 600;
    font-size: 0.75rem;
}}

/* Action Triage Cards (Stripe Glassmorphism Cards) */
.dss-action-card {{
    background: rgba(255, 255, 255, 0.8);
    backdrop-filter: blur(16px) saturate(180%);
    -webkit-backdrop-filter: blur(16px) saturate(180%);
    border: 1px solid rgba(255, 255, 255, 0.95);
    border-radius: var(--radius-xl);
    padding: 18px 20px;
    box-shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.05), inset 0 1px 0 #FFFFFF;
    display: flex;
    flex-direction: column;
    gap: 10px;
    transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.2s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.2s ease;
}}
.dss-action-card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 12px 30px -4px rgba(15, 23, 42, 0.08), inset 0 1px 0 #FFFFFF;
    border-color: rgba(99, 102, 241, 0.3);
}}
.dss-action-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.75rem;
}}
.dss-action-title {{
    color: var(--text-primary);
    font-weight: 600;
    font-size: 0.9375rem;
}}
.dss-action-stat {{
    font-family: var(--font-mono);
    font-size: 0.8125rem;
    color: var(--text-secondary);
}}

/* 9-Cell ABC/XYZ Matrix Grid (Translucent Glass Cells) */
.dss-matrix-grid {{
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin: 12px 0 18px 0;
}}

.dss-matrix-card {{
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(16px) saturate(180%);
    -webkit-backdrop-filter: blur(16px) saturate(180%);
    border: 1px solid rgba(226, 232, 240, 0.9);
    border-radius: var(--radius-lg);
    padding: 14px 16px;
    box-shadow: 0 4px 16px -2px rgba(15, 23, 42, 0.04), inset 0 1px 0 #FFFFFF;
    display: flex;
    flex-direction: column;
    gap: 6px;
    transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.2s ease, border-color 0.2s ease;
}}

.dss-matrix-card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 10px 25px -4px rgba(15, 23, 42, 0.08), inset 0 1px 0 #FFFFFF;
    border-color: rgba(99, 102, 241, 0.35);
}}

.dss-matrix-card.selected {{
    border-color: var(--brand-primary);
    box-shadow: 0 0 0 2px var(--brand-primary), 0 8px 24px rgba(79, 70, 229, 0.15);
}}

.dss-matrix-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
}}

.dss-matrix-code {{
    font-size: 1.15rem;
    font-weight: 800;
    font-family: var(--font-mono);
    letter-spacing: 0.05em;
    color: var(--text-primary);
}}

.dss-matrix-badge {{
    font-size: 0.6875rem;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 2px;
    border: 1px solid var(--border-subtle);
    background-color: var(--surface-layer-2);
    font-family: var(--font-sans);
    text-transform: uppercase;
}}

.dss-matrix-count {{
    font-size: 1.25rem;
    font-weight: 700;
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    color: var(--text-primary);
}}

.dss-matrix-stat {{
    font-size: 0.75rem;
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    color: var(--text-secondary);
}}

.dss-matrix-theme-optimal {{
    border-left: 4px solid #10B981 !important;
}}
.dss-matrix-theme-reorder {{
    border-left: 4px solid #F59E0B !important;
}}
.dss-matrix-theme-critical {{
    border-left: 4px solid #EF4444 !important;
}}
.dss-matrix-theme-excess {{
    border-left: 4px solid #8B5CF6 !important;
}}
.dss-matrix-theme-neutral {{
    border-left: 4px solid var(--border-strong) !important;
}}
"""


# Alias for compatibility with survey prototypes
generate_css = generate_theme_css


def inject_custom_css(theme: DSSTheme | ThemeMode | str = ThemeMode.DARK) -> str:
    """Inject DSS CSS stylesheet into active Streamlit DOM and return the CSS string.

    Handles DSSTheme instance, ThemeMode enum, or string ('dark'/'light').
    """
    if isinstance(theme, DSSTheme):
        dss_theme = theme
    else:
        dss_theme = get_theme(theme)

    css_code = generate_theme_css(dss_theme)
    if st is not None and hasattr(st, "markdown"):
        st.markdown(f"<style>{css_code}</style>", unsafe_allow_html=True)
    return css_code


def get_streamlit_config_toml(mode: ThemeMode | str = ThemeMode.DARK) -> str:
    """Generate exact contents for .streamlit/config.toml."""
    theme = get_theme(mode)
    return f"""[theme]
base = "{theme.mode.value}"
primaryColor = "#4F46E5"
backgroundColor = "{theme.surfaces.layer_0}"
secondaryBackgroundColor = "{theme.surfaces.layer_1}"
textColor = "{theme.text.primary}"
font = "sans serif"
"""


# Alias for compatibility
generate_streamlit_config_toml = get_streamlit_config_toml


# ---------------------------------------------------------------------------
# Plotly Visualization Theming
# ---------------------------------------------------------------------------

DSS_STATUS_COLORS: dict[str, str] = {
    "CRITICAL": "#EF4444",
    "REORDER_NEEDED": "#F59E0B",
    "OPTIMAL": "#10B981",
    "EXCESS": "#0EA5E9",
}

DSS_PLOTLY_COLORWAY: list[str] = [
    "#6366F1",  # Brand Indigo Accent
    "#10B981",  # Emerald (Optimal/Fulfillment)
    "#F59E0B",  # Amber (Warning/Reorder)
    "#EF4444",  # Crimson (Critical/Disruption)
    "#0EA5E9",  # Sky (Info/Excess)
    "#8B5CF6",  # Purple (Analytics/Heuristics)
    "#14B8A6",  # Teal (Logistics/Transport)
    "#F43F5E",  # Rose (Emergency/Stockout)
]


def get_plotly_template(mode: ThemeMode | str = ThemeMode.DARK) -> Any:
    """Build and return a unified Plotly Layout Template conforming to DSS design tokens."""
    if go is None:
        raise ImportError("Plotly is required to construct a Plotly Layout Template.")

    theme = get_theme(mode)
    is_dark = theme.mode == ThemeMode.DARK

    grid_color = "rgba(255, 255, 255, 0.08)" if is_dark else "rgba(0, 0, 0, 0.08)"
    zeroline_color = "rgba(255, 255, 255, 0.16)" if is_dark else "rgba(0, 0, 0, 0.16)"

    axis_config = {
        "gridcolor": grid_color,
        "zerolinecolor": zeroline_color,
        "linecolor": theme.borders.default,
        "tickfont": {
            "color": theme.text.secondary,
            "size": 11,
            "family": theme.typography.font_sans,
        },
        "title": {
            "font": {
                "color": theme.text.primary,
                "size": 12,
                "family": theme.typography.font_sans,
            }
        },
    }

    template = go.layout.Template(
        layout=go.Layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            colorway=DSS_PLOTLY_COLORWAY,
            font={
                "family": theme.typography.font_sans,
                "color": theme.text.primary,
                "size": 12,
            },
            title={
                "font": {
                    "family": theme.typography.font_sans,
                    "color": theme.text.primary,
                    "size": 16,
                }
            },
            xaxis=axis_config,
            yaxis=axis_config,
            hoverlabel={
                "bgcolor": theme.surfaces.layer_2,
                "bordercolor": theme.borders.default,
                "font": {
                    "family": theme.typography.font_sans,
                    "color": theme.text.primary,
                    "size": 12,
                },
            },
            legend={
                "font": {
                    "family": theme.typography.font_sans,
                    "color": theme.text.secondary,
                    "size": 11,
                }
            },
        )
    )
    return template


__all__ = [
    "AMBER_PALETTE",
    "CRIMSON_PALETTE",
    "DSS_PLOTLY_COLORWAY",
    "DSS_STATUS_COLORS",
    "EMERALD_PALETTE",
    "INDIGO_PALETTE",
    "PURPLE_PALETTE",
    "SKY_PALETTE",
    "SLATE_PALETTE",
    "ZINC_PALETTE",
    "BadgeTokens",
    "BorderTokens",
    "ChartTokens",
    "ColorScale",
    "ComponentTokens",
    "ControlTokens",
    "DSSTheme",
    "DataTableTokens",
    "EpistemicTrustTier",
    "InventoryStatus",
    "KpiCardTokens",
    "PrimitiveTokens",
    "RadiiTokens",
    "ReasoningCardTokens",
    "SemanticTokens",
    "ShadowTokens",
    "SpacingTokens",
    "StatusColorTokens",
    "SurfaceTokens",
    "TextTokens",
    "Theme",
    "ThemeMode",
    "TrustTierColorTokens",
    "TypographyTokens",
    "calculate_contrast_ratio",
    "calculate_relative_luminance",
    "generate_css",
    "generate_streamlit_config_toml",
    "generate_theme_css",
    "get_dark_theme",
    "get_light_theme",
    "get_plotly_template",
    "get_streamlit_config_toml",
    "get_theme",
    "hex_to_rgb",
    "inject_custom_css",
    "srgb_to_linear",
    "verify_theme_wcag",
    "verify_wcag_aa",
    "verify_wcag_compliance",
]
