# TEST_READY: Inventory DSS Production-Grade Design System

- **Milestone**: M0 (E2E & Unit Test Suite Creation)
- **Status**: COMPLETE & VERIFIED
- **Target Test File**: `tests/unit/test_theme.py`
- **Total Test Cases**: 94 automated test cases
- **Linter Status**: `uv run ruff check tests/unit/test_theme.py` -> 0 errors (PASS)
- **Target Implementation Module**: `src/inventory_dss/ui/theme.py` (Milestone M1)

---

## 1. Test Suite Architecture (5 Tiers + Adversarial Suite)

The test suite in `tests/unit/test_theme.py` provides comprehensive, deterministic verification of the complete 3-Tier Design System specification and contracts defined in `ORIGINAL_REQUEST.md` and `PROJECT.md`.

```
tests/unit/test_theme.py (94 Test Cases)
├── TestTier1PrimitiveTokens (23 tests)
│   ├── ThemeMode Enum (LIGHT, DARK)
│   ├── InventoryStatus Enum (CRITICAL, REORDER_NEEDED, OPTIMAL, EXCESS)
│   ├── EpistemicTrustTier Enum (ALGORITHMIC, HEURISTIC, EXPLORATORY)
│   ├── 8 Chromatic/Neutral Palettes (11 steps: c50 to c950, #RRGGBB format)
│   ├── Monotonic Palette Lightness / Luminance Ordering
│   ├── Typography Tokens (Inter Sans, JetBrains Mono, Tabular Numerals, 400-700 weights)
│   ├── Monotonic Type Scale (xs: 0.75rem -> 4xl: 2.25rem)
│   ├── 4px/8px Baseline Spacing Grid (space_0 to space_16)
│   └── Elevation Shadows & Status Glow Rings (elevation_none to xl, glow_brand/crit/opt)
├── TestTier1SemanticAndComponentTokens (18 tests)
│   ├── Layered Surface Elevations (layer_0 canvas, layer_1 cards, layer_2 popovers, layer_accent)
│   ├── Text Contrast Hierarchy (primary, secondary, muted, inverse, accent)
│   ├── Border Hierarchy (subtle, default, strong, focus)
│   ├── Domain Status Composite Tokens (fg, bg, border, solid, pulse)
│   ├── Epistemic Trust Tier Composite Tokens (fg, bg, border, badge labels)
│   └── Component Tokens (kpi_card, data_table, badge, reasoning_card, controls, chart)
├── TestTier2WCAGContrastMathematics (17 tests)
│   ├── Piecewise sRGB Channel Linearization Threshold (boundary at 0.04045)
│   ├── Hex to RGB Parsing (6-digit, 3-digit shorthand, without hash)
│   ├── WCAG 2.2 Relative Luminance Formula (L = 0.2126 R_lin + 0.7152 G_lin + 0.0722 B_lin)
│   ├── Contrast Ratio Properties (Symmetry, Max 21:1, Min 1:1)
│   ├── Dark Mode Text Pairings (CR >= 4.5:1 on card and canvas)
│   ├── Dark Mode Status Pairings (CR >= 4.5:1 on card and status bg)
│   ├── Dark Mode Active Border Contrast (CR >= 3.0:1 on card, WCAG 1.4.11)
│   ├── Light Mode Text Pairings (CR >= 4.5:1 on card and canvas)
│   ├── Light Mode Status Pairings (CR >= 4.5:1 on card and status bg)
│   ├── Light Mode Active Border Contrast (CR >= 3.0:1 on card, WCAG 1.4.11)
│   └── Full Theme Audit Verification Engine (`verify_theme_wcag`)
├── TestTier3ConcentricRadii (3 tests)
│   ├── Concentric Radii Mathematical Proof: R_inner = max(0, R_outer - padding)
│   ├── Strict Non-Negative Clamping (padding >= outer radius -> 0.0px)
│   └── Radii Scale Tokens (none 0px -> full 9999px)
├── TestTier4ThemeEngineAndCSS (11 tests)
│   ├── Theme Mode Getters (`get_theme(ThemeMode.DARK)`, `get_theme(ThemeMode.LIGHT)`)
│   ├── Case-Insensitive String Parsing ("dark", "DARK", "Light")
│   ├── Invalid Theme Mode Error Handling (raises ValueError)
│   ├── CSS Generation: `:root` CSS Custom Properties
│   ├── CSS Generation: Native Streamlit Overrides (.stApp, stSidebar, stMetric, button, stDataFrame)
│   ├── CSS Generation: DSS Component Utility Classes (.dss-kpi-card, .dss-badge, .dss-reasoning-card)
│   ├── Global Tabular Numeral Enforcement (`font-variant-numeric: tabular-nums`)
│   ├── Zero-Flicker Streamlit CSS Injection (`inject_custom_css`)
│   └── Streamlit Config TOML Generation (`get_streamlit_config_toml`)
├── TestTier5PlotlyVisualizationTheming (12 tests)
│   ├── Layout Template Object Generation (`get_plotly_template`)
│   ├── Transparent Canvas/Paper Blending (`paper_bgcolor`, `plot_bgcolor` = "rgba(0,0,0,0)")
│   ├── Typography Alignment (Inter Sans-Serif, Theme-Aware Font Colors)
│   ├── Subtle High-Contrast Gridlines and Coordinate Axes
│   ├── Elevated Card Tooltip Styling (`hoverlabel` background, border, font)
│   ├── 8-Color Semantic Sequence (`colorway` with Brand Indigo, Emerald, Amber, Crimson)
│   └── Live Plotly Figure Serialization with Applied Template
└── TestAdversarialThemeRobustness (10 tests)
    ├── Hex Input Edge Cases (#GGGGGG, #12, #12345, empty, etc. raise ValueError)
    ├── Zero Difference Color Contrast (Identical colors evaluate to exactly 1.0:1)
    ├── Extreme Padding Boundary Clamping (10000px padding safely returns 0.0px)
    └── CSS Output Sanitization (no unrendered template placeholders or NaN/undefined)
```

---

## 2. Key Interface Contracts & Implementation Guidance for Worker (Milestone M1)

When implementing `src/inventory_dss/ui/theme.py`, the worker must adhere to the following contracts and discovered nuances:

1. **Enum & String Normalization in `get_theme()`**:
   ```python
   def get_theme(mode: ThemeMode | str = ThemeMode.DARK) -> DSSTheme:
       if isinstance(mode, ThemeMode):
           normalized = mode
       else:
           normalized = ThemeMode(str(mode).strip().lower())
       if normalized == ThemeMode.LIGHT:
           return get_light_theme()
       return get_dark_theme()
   ```
   *Rationale*: In Python, calling `str(ThemeMode.DARK)` yields `"ThemeMode.DARK"`. Passing that through `.lower()` yields `"thememode.dark"`, which fails `ThemeMode(str)`. Checking `isinstance(mode, ThemeMode)` first guarantees flawless handling of both enums and strings.

2. **Strict Hex Validation in `hex_to_rgb()`**:
   ```python
   def hex_to_rgb(hex_code: str) -> tuple[int, int, int]:
       h = hex_code.strip().lstrip("#")
       if len(h) not in (3, 6) or not all(c in "0123456789abcdefABCDEF" for c in h):
           raise ValueError(f"Invalid hex color code: '{hex_code}'")
       if len(h) == 3:
           h = "".join([c * 2 for c in h])
       return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
   ```

3. **Plotly Layout Template (`get_plotly_template`)**:
   Must configure:
   - `paper_bgcolor="rgba(0,0,0,0)"`
   - `plot_bgcolor="rgba(0,0,0,0)"`
   - `font=dict(family="Inter, -apple-system, sans-serif", color=font_color)`
   - `colorway=["#6366F1", "#10B981", "#F59E0B", "#EF4444", "#0EA5E9", "#8B5CF6", "#14B8A6", "#F43F5E"]`
   - Styled `xaxis`, `yaxis`, and `hoverlabel`.

4. **Brand Primary Button Contrast**:
   - Primary button background must be `#4F46E5` (Indigo-600) rather than `#6366F1` (Indigo-500) to ensure white button text achieves a contrast ratio of **6.29:1** (exceeding WCAG 2.2 AA 4.5:1).

---

## 3. How to Run the Test Suite

Once `src/inventory_dss/ui/theme.py` is implemented:

```bash
# Run unit tests
cd inventory_dss
uv run pytest tests/unit/test_theme.py -v

# Run linter
uv run ruff check tests/unit/test_theme.py
```

*Pre-implementation Oracle Verification*: The test suite was pre-verified against the specification reference engine and achieved **94 passed in 0.18s** with zero regressions.
