# E2E Test Infrastructure: Inventory Decision Support System (СППР Управления Запасами)

## 1. Test Philosophy & Principles

- **Opaque-Box Requirement-Driven Verification**: All test suites are derived directly from the authoritative specifications in `ORIGINAL_REQUEST.md`, `specs/001-inventory-dss/spec.md`, and `PROJECT.md § Interface Contracts`. The tests verify domain contracts, mathematical invariant satisfaction, and observable behaviors without coupling to private internal implementation details.
- **Strict Anti-Facade Policy**: Zero mock facades, dummy assertions, or tests tailored to hardcoded responses. Every expected value is derived from first-principles analytical models:
  * Joint uncertainty safety stock via Wald's identity: $SS = Z_\alpha \sqrt{\mu_L \sigma_D^2 + \mu_D^2 \sigma_L^2}$.
  * Dynamic reorder point: $ROP = \mu_D \mu_L + SS$.
  * Classical Wilson economic order quantity: $EOQ = \sqrt{2 D K / H}$.
  * Effective inventory position: $I_{eff} = I_{on\_hand} + I_{in\_transit} - I_{allocated} - I_{backorders}$.
  * Multi-criteria TOPSIS with vector normalization and Euclidean distance to ideal/anti-ideal solutions.
  * Analytic Hierarchy Process (AHP) with consistency verification $CR < 0.10$.
  * Shannon Entropy weighting: $E_j = -\frac{1}{\ln m}\sum p_{ij} \ln p_{ij}, d_j = 1 - E_j$.
  * Karush-Kuhn-Tucker (KKT) multi-item warehouse capacity constrained optimization ($\sum Q_i v_i \le V_{max}$ and $\sum Q_i w_i \le W_{max}$).
  * 4-tier state machine inventory classification: `CRITICAL`, `REORDER_NEEDED`, `OPTIMAL`, `EXCESS`.
- **Progressive Testability & Decoupled Execution**: Tests interact cleanly with public domain models (`SKU`, `Supplier`, `Warehouse`, `DemandRecord`, `InventoryState`, `ForecastResult`, `OptimizationPlan`, `Recommendation`, `PurchaseOrder`). When modules are completed across milestones (M1 through M4), the test harness automatically executes against the production engines, while providing robust reference fallback pipelines for continuous end-to-end validation.

---

## 2. Feature Inventory & Test Coverage Matrix

| # | Feature | Scope | Tier 1 (Feature) | Tier 2 (Boundary) | Tier 3 (Pairwise) | Tier 4 (Scenario) |
|---|---------|-------|:----------------:|:-----------------:|:-----------------:|:-----------------:|
| F01 | Speckit Specification (`spec.md`) | M1 | ✓ | | | ✓ |
| F02 | DSS Passport Foundation & Structure | M1 | ✓ | | | ✓ |
| F03 | Knowledge Base & Decision Rules | M1 | ✓ | ✓ | ✓ | ✓ |
| F04 | Domain Schemas & Contracts | M1 | ✓ | ✓ | | ✓ |
| F05 | Synthetic SKU Catalog Generator | M2 | ✓ | ✓ | ✓ | ✓ |
| F06 | Multi-Year Demand Series Generator | M2 | ✓ | ✓ | ✓ | ✓ |
| F07 | Supplier Profiles & Catalog | M2 | ✓ | ✓ | ✓ | ✓ |
| F08 | Multi-Criteria Supplier Evaluation (TOPSIS) | M2 | ✓ | ✓ | ✓ | ✓ |
| F09 | Hybrid Criteria Weighting (AHP + Entropy) | M2 | ✓ | ✓ | | ✓ |
| F10 | Supplier Risk & Decision Tree Analysis | M2 | ✓ | ✓ | ✓ | ✓ |
| F11 | Time-Series Demand Forecasting | M3 | ✓ | ✓ | ✓ | ✓ |
| F12 | Uncertainty Quantification (95% CI) | M3 | ✓ | ✓ | ✓ | ✓ |
| F13 | Temporal Hold-Out Model Validation | M3 | ✓ | ✓ | | ✓ |
| F14 | Total Cost of Ownership (TCO) Model | M3 | ✓ | ✓ | ✓ | ✓ |
| F15 | Joint Uncertainty Safety Stock ($SS$) | M3 | ✓ | ✓ | ✓ | ✓ |
| F16 | Reorder Point ($ROP$) & EOQ | M3 | ✓ | ✓ | ✓ | ✓ |
| F17 | Warehouse Storage Capacity Constraints (KKT) | M3 | ✓ | ✓ | ✓ | ✓ |
| F18 | Inventory Status Classification (4-Tier) | M4 | ✓ | ✓ | ✓ | ✓ |
| F19 | Replenishment Order Recommendation ($Q_{rec}$) | M4 | ✓ | ✓ | ✓ | ✓ |
| F20 | Optimal Supplier Order Allocation | M4 | ✓ | ✓ | ✓ | ✓ |
| F21 | Interactive BI Dashboard (Streamlit) | M4 | ✓ | | | ✓ |
| F22 | What-If Parameter Simulation | M4 | ✓ | ✓ | ✓ | ✓ |
| F23 | Local DSS Passport Population | M4 | ✓ | | | ✓ |

---

## 3. Test Architecture & Directory Layout

```
inventory_dss/
├── TEST_INFRA.md                   # This document
├── TEST_READY.md                   # E2E Test Suite readiness declaration
└── tests/
    └── e2e/
        ├── __init__.py
        ├── test_tier1_features.py   # Tier 1: Feature Coverage (F01-F23, >=20 tests)
        ├── test_tier2_boundaries.py # Tier 2: Boundary & Corner Cases (>=20 tests)
        ├── test_tier3_pairwise.py   # Tier 3: Pairwise Combinations (>=15 tests)
        └── test_tier4_scenarios.py  # Tier 4: Real-World Workload Scenarios (>=5 scenarios)
```

---

## 4. Test Suite Tiers & Verification Scope

### Tier 1: Feature Coverage (`test_tier1_features.py`)
- **Target**: Comprehensive individual functional validation of features F01 through F23.
- **Minimum Tests**: $\ge 20$ independent test cases (authors provide 23+ tests covering every single feature).
- **Core Checks**:
  1. Specification completeness (user scenarios P1-P3, FR-001..FR-015, SC-001..SC-006).
  2. DSS Passport structural conformity to Google Docs template (8 canonical sections + 4-step methodological chain: Постановка -> Метод -> Результат -> Интерпретация).
  3. Domain models field validation, type checking, and `effective_inventory` computed property.
  4. Knowledge base forward-chaining rules and stock status classification.
  5. Synthetic data generation: 25 SKUs, ABC 80/15/5 distribution, XYZ segmentation, 730 days demand.
  6. MCDA TOPSIS closeness ranking, AHP consistency ratio $CR < 0.10$, Shannon entropy weights.
  7. Time-series forecasting point forecasts and 95% uncertainty confidence bands.
  8. Hold-out temporal validation and metrics (MAE, RMSE, MAPE, WAPE).
  9. Wald's identity joint safety stock $SS$ and dynamic $ROP$.
  10. Classical Wilson EOQ and all-units quantity discount tier optimization.
  11. KKT Lagrangian multi-item warehouse capacity constraint resolution.
  12. 4-tier recommendation state machine and order sizing with pack size ceiling and supplier MOQ.
  13. Urgency-aware supplier allocation (cost/TOPSIS for standard, lead-time speed for critical).
  14. What-if parameter sensitivity analysis across target service levels.

### Tier 2: Boundary & Corner Cases (`test_tier2_boundaries.py`)
- **Target**: Robustness under extreme, degenerate, and boundary operating conditions.
- **Minimum Tests**: $\ge 20$ tests.
- **Core Checks**:
  1. Zero demand history ($D_t = 0 \ \forall t$) -> Zero forecast, zero SS, graceful EOQ handling without division-by-zero.
  2. Single-SKU catalog vs empty catalog graceful handling.
  3. Extreme delivery lead times ($\mu_L = 365$ days) -> Large lead-time demand without integer or float overflow.
  4. Zero lead time variance ($\sigma_L = 0$) -> $SS$ collapses to classical $Z_\alpha \sigma_D \sqrt{\mu_L}$.
  5. Zero demand variance ($\sigma_D = 0$) -> $SS$ collapses to $Z_\alpha \mu_D \sigma_L$.
  6. Completely deterministic regime ($\sigma_D = 0, \sigma_L = 0$) -> $SS = 0, ROP = \mu_D \mu_L$.
  7. 100% supplier defect rate ($\delta = 1.0$) -> Minimum TOPSIS closeness, excluded from optimal procurement.
  8. Perfect supplier reliability (0% defect, 100% OTIF) -> Dominant closeness score approaching 1.0.
  9. Severe warehouse volume and weight overflow -> KKT multipliers clamp orders to fit available capacity.
  10. Negative effective inventory ($I_{eff} < 0$, severe backorders) -> Classified as CRITICAL, order covers backorders.
  11. Extreme overstock ($I_{eff} \gg Max$) -> Status EXCESS, order quantity zero, order flag False.
  12. Supplier MOQ exceeding remaining warehouse capacity -> System alerts and prevents unfeasible allocations.
  13. Asymmetric pack sizes (unit lot vs master carton 500) -> Ceiling rounding enforced.
  14. Extreme service levels ($\alpha = 0.999 \implies Z \approx 3.09$ vs $\alpha = 0.50 \implies Z = 0$).
  15. Exact classification boundaries ($I_{eff} = SS, I_{eff} = SS + \epsilon, I_{eff} = ROP, I_{eff} = Max$).
  16. Zero holding cost and zero fixed order cost boundary behaviors.
  17. Completely identical suppliers -> Maximum entropy, equal weights, identical closeness $C_i = 0.5$.
  18. Extreme intermittent demand (95% zeros, Croston-like) -> Numerical stability in WAPE and forecasts.

### Tier 3: Pairwise Combinations (`test_tier3_pairwise.py`)
- **Target**: Multi-factor non-linear interactions across analytical subsystems.
- **Minimum Tests**: $\ge 15$ tests.
- **Core Checks**:
  1. High forecast variance ($\sigma_D$) + High lead time variance ($\sigma_L$) -> Joint variance compounding in SS.
  2. Lead time variance dominance ($\sigma_L \gg \sigma_D$) vs Demand variance dominance ($\sigma_D \gg \sigma_L$).
  3. Supplier TOPSIS score interacting with urgency level: Standard selects top TOPSIS; CRITICAL selects fastest $\mu_L + 2\sigma_L$.
  4. Simultaneous binding of volume constraint ($V_{max}$) and weight constraint ($W_{max}$).
  5. Supplier MOQ interacting with warehouse volume ceiling under constrained scaling.
  6. Quantity discount tiers interacting with high holding cost rate.
  7. Service level escalation ($95\% \to 99\%$) interacting with supplier delivery unreliability.
  8. ABC Class A high-value items interacting with XYZ Class Z intermittent volatile demand.
  9. ABC Class C low-value items interacting with XYZ Class X steady demand.
  10. Deep negative stockout interacting with high MOQ suppliers.
  11. Multi-item capacity scaling protecting CRITICAL items while trimming REORDER_NEEDED items.
  12. Trade-off between supplier purchase price markup and defect rate penalty in TOPSIS ranking.
  13. Dynamic demand spike in forecast interacting with fixed delivery lead time on ROP.
  14. Forecast horizon expansion interacting with cumulative uncertainty envelope width.
  15. Combined pack size batching and supplier MOQ ceiling rectification.

### Tier 4: Real-World Workload Scenarios (`test_tier4_scenarios.py`)
- **Target**: Comprehensive, end-to-end multi-period realistic operational workflows.
- **Minimum Scenarios**: $\ge 5$ end-to-end scenarios.
- **Core Scenarios**:
  1. **Scenario S01: Multi-SKU Seasonal Peak Replenishment Campaign**:
     - 25 SKUs over 730 days experiencing Q4 holiday demand surge (+150% demand).
     - Forecasting engine detects trend and seasonal surge; SS and ROP adapt dynamically; procurement recommendations stay strictly within warehouse capacity limits.
  2. **Scenario S02: Primary Supplier Disruption & Emergency Failover**:
     - Primary low-cost supplier experiences operational collapse (OTIF drops to 10%, lead time triples).
     - MCDA re-evaluates ranking; production rules detect CRITICAL stockout risk and execute emergency failover to backup express supplier.
  3. **Scenario S03: Automated Rolling Replenishment Cycle (14-Day Simulation)**:
     - End-to-end simulation of daily inventory consumption, order placement, in-transit transit, and delivery arrival.
     - Cycle service level maintained $\ge 95\%$ with zero unmanaged stockouts.
  4. **Scenario S04: Multi-Item Warehouse Capacity Contention & Constrained KKT Allocation**:
     - Bulky raw materials and electronics simultaneously trigger reorder, demanding $1,800 \ m^3$ against a $1,000 \ m^3$ physical warehouse ceiling.
     - KKT Lagrangian solver scales orders optimally while safeguarding CRITICAL buffers.
  5. **Scenario S05: Full End-to-End Pipeline from Synthetic Data to Exported DSS Passport**:
     - Sequential execution of dataset generation, time-series forecasting, supplier MCDA, inventory optimization, recommendation generation, and DSS Passport content population verification.

---

## 5. Execution Commands & Verification Guide

### Running Full E2E Test Suite
```bash
uv run pytest tests/e2e/ -v
```

### Running Individual Tiers
```bash
# Tier 1: Feature Coverage (F01..F23)
uv run pytest tests/e2e/test_tier1_features.py -v

# Tier 2: Boundary & Corner Cases
uv run pytest tests/e2e/test_tier2_boundaries.py -v

# Tier 3: Pairwise Combinations
uv run pytest tests/e2e/test_tier3_pairwise.py -v

# Tier 4: Real-World Workload Scenarios
uv run pytest tests/e2e/test_tier4_scenarios.py -v
```

### Pass Criteria
- 100% of tests must pass (exit code 0).
- Zero assertion failures, zero uncaught exceptions, zero tracebacks.
- Numerical assertions must verify exact mathematical equality or tolerance within $\le 10^{-4}$.
