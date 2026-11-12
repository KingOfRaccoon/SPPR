"""Configuration constants and defaults for Inventory DSS."""

from pathlib import Path

# ---------------------------------------------------------------------------
# Path Configuration
# ---------------------------------------------------------------------------
PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
SYNTHETIC_DATA_DIR = DATA_DIR / "synthetic"
OUTPUTS_DATA_DIR = DATA_DIR / "outputs"
DOCS_DIR = PROJECT_ROOT / "docs"

# ---------------------------------------------------------------------------
# Determinism and Reproducibility
# ---------------------------------------------------------------------------
RANDOM_SEED: int = 42

# ---------------------------------------------------------------------------
# Warehouse Capacity & Cost Defaults
# ---------------------------------------------------------------------------
DEFAULT_WAREHOUSE_ID: str = "WH-CENTRAL-01"
DEFAULT_WAREHOUSE_NAME: str = "Центральный распределительный склад"
DEFAULT_WAREHOUSE_VOLUME_M3: float = 1000.0
DEFAULT_WAREHOUSE_WEIGHT_KG: float = 50000.0
DEFAULT_FIXED_ORDER_COST_RUB: float = 3500.0
DEFAULT_ANNUAL_CAPITAL_RATE: float = 0.18
DEFAULT_HOLDING_COST_RATE: float = 0.22

# ---------------------------------------------------------------------------
# Service Level Standards & Normal Quantiles
# ---------------------------------------------------------------------------
DEFAULT_SERVICE_LEVEL: float = 0.95
DEFAULT_Z_SCORE: float = 1.6448536269514722

SERVICE_LEVEL_QUANTILES: dict[float, float] = {
    0.90: 1.2815515655446004,
    0.95: 1.6448536269514722,
    0.975: 1.959963984540054,
    0.98: 2.0537489106318225,
    0.99: 2.3263478740408408,
    0.995: 2.5758293035489004,
    0.999: 3.090232306167813,
}

# ---------------------------------------------------------------------------
# ABC / XYZ Segmentation Thresholds
# ---------------------------------------------------------------------------
ABC_A_CUMULATIVE_SHARE: float = 0.80
ABC_B_CUMULATIVE_SHARE: float = 0.95

XYZ_X_CV_THRESHOLD: float = 0.15
XYZ_Y_CV_THRESHOLD: float = 0.35

# ---------------------------------------------------------------------------
# Forecasting & Data Generator Defaults
# ---------------------------------------------------------------------------
TOTAL_SKU_COUNT: int = 25
TOTAL_SUPPLIER_COUNT: int = 5
DEMAND_HISTORY_DAYS: int = 730
DEFAULT_FORECAST_HORIZON_DAYS: int = 30
DEFAULT_HOLDOUT_DAYS: int = 60
DEFAULT_CONFIDENCE_LEVEL: float = 0.95
