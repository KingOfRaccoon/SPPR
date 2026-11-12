"""Command-line interface (CLI) for Inventory Decision Support System (СППР).

Provides subcommands:
- generate-data: Generate synthetic supply chain dataset (SKUs, demand, suppliers, warehouse).
- recommend: Run replenishment recommendation pipeline and display tabular decisions.
- evaluate-suppliers: Run multi-criteria supplier evaluation (TOPSIS, AHP, Entropy, Hybrid).
- serve: Launch the Streamlit interactive BI dashboard.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from inventory_dss.config import (
    DEFAULT_SERVICE_LEVEL,
    PACKAGE_ROOT,
    SYNTHETIC_DATA_DIR,
)
from inventory_dss.data.generator import SyntheticDataGenerator
from inventory_dss.forecasting.model import DemandForecaster
from inventory_dss.models.domain import (
    SKU,
    DemandRecord,
    InventoryState,
    Supplier,
    Warehouse,
)
from inventory_dss.optimization.engine import InventoryOptimizer
from inventory_dss.recommendations.engine import RecommendationEngine
from inventory_dss.suppliers.evaluator import SupplierEvaluator

APP_PATH = PACKAGE_ROOT / "ui" / "app.py"


def _load_or_generate_dataset(data_dir: Path) -> dict[str, list | Warehouse]:
    """Load dataset from directory or automatically generate if missing."""
    skus_path = data_dir / "skus.csv"
    suppliers_path = data_dir / "suppliers.csv"
    demand_path = data_dir / "demand_history.csv"
    warehouse_path = data_dir / "warehouse.json"
    state_path = data_dir / "inventory_state.csv"

    if not (skus_path.exists() and suppliers_path.exists() and demand_path.exists()):
        gen = SyntheticDataGenerator()
        gen.save_to_disk(output_dir=data_dir)

    # 1. Load SKUs
    skus: list[SKU] = []
    with open(skus_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            skus.append(
                SKU(
                    sku_id=row["sku_id"],
                    name=row["name"],
                    category=row["category"],
                    unit_price=float(row["unit_price"]),
                    unit_cost=float(row["unit_cost"]) if row.get("unit_cost") else None,
                    holding_cost_annual_rate=float(row["holding_cost_annual_rate"]),
                    unit_volume_m3=float(row["unit_volume_m3"]),
                    unit_weight_kg=float(row["unit_weight_kg"]),
                    pack_size=int(row["pack_size"]),
                    abc_class=row.get("abc_class") or None,
                    xyz_class=row.get("xyz_class") or None,
                    stockout_penalty_per_unit=(
                        float(row["stockout_penalty_per_unit"])
                        if row.get("stockout_penalty_per_unit")
                        else None
                    ),
                )
            )

    # 2. Load Suppliers
    suppliers: list[Supplier] = []
    with open(suppliers_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            suppliers.append(
                Supplier(
                    supplier_id=row["supplier_id"],
                    name=row["name"],
                    mean_lead_time_days=float(row["mean_lead_time_days"]),
                    std_lead_time_days=float(row["std_lead_time_days"]),
                    on_time_delivery_rate=float(row["on_time_delivery_rate"]),
                    defect_rate=float(row["defect_rate"]),
                    min_order_quantity=int(row["min_order_quantity"]),
                    price_markup_factor=float(row.get("price_markup_factor", 1.0)),
                    order_processing_cost=float(row.get("order_processing_cost", 3500.0)),
                    profile_type=row.get("profile_type") or None,
                )
            )

    # 3. Load Warehouse
    with open(warehouse_path, encoding="utf-8") as f:
        wh_data = json.load(f)
    warehouse = Warehouse(**wh_data)

    # 4. Load Demand History
    demand_records: list[DemandRecord] = []
    with open(demand_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            demand_records.append(
                DemandRecord(
                    date=row["date"],
                    sku_id=row["sku_id"],
                    quantity=float(row["quantity"]),
                    is_promotional=row.get("is_promotional", "False").lower() in ("true", "1"),
                    is_weekend=row.get("is_weekend", "False").lower() in ("true", "1"),
                    stockout_flag=row.get("stockout_flag", "False").lower() in ("true", "1"),
                )
            )

    # 5. Load Inventory State
    states: list[InventoryState] = []
    if state_path.exists():
        with open(state_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                states.append(
                    InventoryState(
                        sku_id=row["sku_id"],
                        on_hand=float(row["on_hand"]),
                        on_order=float(row["on_order"]),
                        allocated=float(row.get("allocated", 0.0)),
                        backorders=float(row.get("backorders", 0.0)),
                        safety_stock=float(row["safety_stock"]) if row.get("safety_stock") else 0.0,
                        reorder_point=(
                            float(row["reorder_point"]) if row.get("reorder_point") else 0.0
                        ),
                        max_stock=float(row["max_stock"]) if row.get("max_stock") else 0.0,
                    )
                )

    return {
        "skus": skus,
        "suppliers": suppliers,
        "warehouse": warehouse,
        "demand": demand_records,
        "states": states,
    }


def handle_generate_data(args: argparse.Namespace) -> int:
    """Generate synthetic supply chain dataset."""
    output_dir = Path(args.output_dir)
    print(f"Generating synthetic dataset (seed={args.seed}, days={args.days})...")
    gen = SyntheticDataGenerator(seed=args.seed)
    files = gen.save_to_disk(output_dir=output_dir, days=args.days)

    print(f"\n✓ Dataset generated successfully in {output_dir.resolve()}:")
    for name, path in files.items():
        print(f"  - {name:15}: {path.name}")
    print("\nCatalog Summary: 25 SKUs across 4 categories, 5 supplier archetypes, 730 days history.")
    return 0


def handle_evaluate_suppliers(args: argparse.Namespace) -> int:
    """Evaluate and rank suppliers using MCDA."""
    data_dir = Path(args.data_dir)
    data = _load_or_generate_dataset(data_dir)
    suppliers: list[Supplier] = data["suppliers"]  # type: ignore[assignment]

    evaluator = SupplierEvaluator()
    ranked = evaluator.rank_suppliers(suppliers, method=args.method)

    print(f"\nSupplier Evaluation Ranking (Method: {args.method})")
    print("=" * 95)
    header = (
        f"{'Rank':4} | {'Supplier ID':12} | {'Name':24} | {'Score':7} | "
        f"{'Lead (d)':8} | {'OTIF (%)':8} | {'Defect (%)':10} | {'MOQ':5}"
    )
    print(header)
    print("-" * 95)

    for item in ranked:
        print(
            f"{item['rank']:4} | {item['supplier_id']:12} | {item['name']:24} | {item['score']:7.4f} | "
            f"{item['mean_lead_time_days']:8.1f} | {item['on_time_delivery_rate'] * 100:8.1f} | "
            f"{item['defect_rate'] * 100:10.2f} | {item['min_order_quantity']:5}"
        )
    print("=" * 95)
    return 0


def handle_recommend(args: argparse.Namespace) -> int:
    """Run DSS replenishment recommendation pipeline and display results."""
    data_dir = Path(args.data_dir)
    data = _load_or_generate_dataset(data_dir)

    skus: list[SKU] = data["skus"]  # type: ignore[assignment]
    suppliers: list[Supplier] = data["suppliers"]  # type: ignore[assignment]
    warehouse: Warehouse = data["warehouse"]  # type: ignore[assignment]
    demand: list[DemandRecord] = data["demand"]  # type: ignore[assignment]
    states: list[InventoryState] = data["states"]  # type: ignore[assignment]

    skus_dict = {s.sku_id: s for s in skus}
    suppliers_dict = {s.supplier_id: s for s in suppliers}

    print("Running DSS Analytical Pipeline...")
    # 1. Forecasting
    forecaster = DemandForecaster()
    forecasts = {}
    for sku in skus:
        sku_records = [d for d in demand if d.sku_id == sku.sku_id]
        if sku_records:
            forecasts[sku.sku_id] = forecaster.fit_predict(
                sku_records, horizon_days=args.horizon, holdout_days=30
            )

    # 2. Supplier MCDA
    evaluator = SupplierEvaluator()
    supplier_scores = evaluator.evaluate_suppliers(suppliers, method="HYBRID")

    # 3. Optimization
    optimizer = InventoryOptimizer()
    policies = optimizer.calculate_multi_item_policies(
        skus=skus_dict,
        forecasts=forecasts,
        suppliers=suppliers_dict,
        warehouse=warehouse,
        service_level=args.service_level,
        enforce_capacity=True,
    )

    # 4. Recommendations
    rec_engine = RecommendationEngine()
    batch = rec_engine.generate_batch(
        inventory_states=states,
        skus=skus_dict,
        forecasts=forecasts,
        policies=policies,
        suppliers=suppliers_dict,
        warehouse=warehouse,
        supplier_scores=supplier_scores,
        enforce_capacity=True,
    )

    print(f"\nDSS Replenishment Recommendations (Batch ID: {batch.batch_id})")
    print(f"Service Level: {args.service_level * 100:.1f}% | Horizon: {args.horizon} days")
    print("=" * 115)
    header = (
        f"{'SKU ID':13} | {'Status':14} | {'On-Hand':8} | {'ROP':8} | {'Safety':8} | "
        f"{'Recom Qty':9} | {'Supplier':18} | {'Cost (RUB)':12} | {'Urgency':7}"
    )
    print(header)
    print("-" * 115)

    for r in batch.recommendations:
        status_disp = r.status.value if hasattr(r.status, "value") else str(r.status)
        urgency_disp = r.urgency.value if hasattr(r.urgency, "value") else str(r.urgency)
        cost_disp = f"{r.estimated_purchase_cost_rub:,.2f}" if r.estimated_purchase_cost_rub else "0.00"
        print(
            f"{r.sku_id:13} | {status_disp:14} | {r.current_effective_stock:8.1f} | "
            f"{r.reorder_point:8.1f} | {r.safety_stock:8.1f} | {r.recommended_order_quantity:9.1f} | "
            f"{r.selected_supplier_name[:18]:18} | {cost_disp:>12} | {urgency_disp:7}"
        )
    print("=" * 115)

    print("\nPortfolio Executive Summary:")
    print(f"  • Total SKUs Evaluated     : {batch.total_skus_evaluated}")
    print(f"  • Purchase Orders Needed   : {batch.orders_needed_count}")
    print(f"  • Total Units to Order     : {batch.total_recommended_units:,.1f}")
    print(f"  • Total Estimated Spend    : {batch.total_purchase_cost_rub:,.2f} RUB")
    print(
        f"  • Warehouse Volume Usage   : {batch.total_volume_m3:.2f} / "
        f"{batch.warehouse_volume_capacity_m3:.1f} m³ ({batch.volume_utilization * 100:.1f}%)"
    )
    print(
        f"  • Warehouse Weight Usage   : {batch.total_weight_kg:.1f} / "
        f"{batch.warehouse_weight_capacity_kg:.1f} kg ({batch.weight_utilization * 100:.1f}%)"
    )
    print(
        f"  • Capacity Constrained     : {'YES (Trimmed to fit)' if batch.is_capacity_constrained else 'NO (Within limits)'}"
    )
    return 0


def handle_serve(args: argparse.Namespace) -> int:
    """Launch Streamlit BI dashboard."""
    if not APP_PATH.exists():
        print(f"Error: UI application script not found at {APP_PATH}", file=sys.stderr)
        return 1

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(APP_PATH),
        "--server.port",
        str(args.port),
        "--server.address",
        str(args.host),
    ]
    print(f"Starting Streamlit BI Dashboard on http://{args.host}:{args.port}...")
    try:
        proc = subprocess.run(cmd, check=False)
        return proc.returncode
    except KeyboardInterrupt:
        print("\nStreamlit server stopped by user.")
        return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="inventory-dss",
        description="Decision Support System (СППР) for Inventory Management and Procurement Optimization",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 1. generate-data
    p_gen = subparsers.add_parser("generate-data", help="Generate synthetic supply chain dataset")
    p_gen.add_argument(
        "--output-dir",
        default=str(SYNTHETIC_DATA_DIR),
        help=f"Directory to save generated CSV/JSON files (default: {SYNTHETIC_DATA_DIR})",
    )
    p_gen.add_argument(
        "--days",
        type=int,
        default=730,
        help="Number of days of demand history to generate (default: 730)",
    )
    p_gen.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic generation (default: 42)",
    )

    # 2. evaluate-suppliers
    p_sup = subparsers.add_parser("evaluate-suppliers", help="Evaluate and rank suppliers via MCDA")
    p_sup.add_argument(
        "--data-dir",
        default=str(SYNTHETIC_DATA_DIR),
        help="Directory containing suppliers.csv",
    )
    p_sup.add_argument(
        "--method",
        choices=["TOPSIS", "AHP", "ENTROPY", "HYBRID"],
        default="HYBRID",
        help="MCDA weighting/ranking methodology (default: HYBRID)",
    )

    # 3. recommend
    p_rec = subparsers.add_parser(
        "recommend",
        help="Run inventory optimization and generate replenishment recommendations",
    )
    p_rec.add_argument(
        "--data-dir",
        default=str(SYNTHETIC_DATA_DIR),
        help="Directory containing synthetic or production dataset",
    )
    p_rec.add_argument(
        "--service-level",
        type=float,
        default=DEFAULT_SERVICE_LEVEL,
        help="Target cycle service level fraction [0.50, 0.999] (default: 0.95)",
    )
    p_rec.add_argument(
        "--horizon",
        type=int,
        default=30,
        help="Forecasting horizon in days (default: 30)",
    )

    # 4. serve
    p_srv = subparsers.add_parser("serve", help="Launch interactive Streamlit BI dashboard")
    p_srv.add_argument(
        "--port",
        type=int,
        default=8501,
        help="Port to bind Streamlit server (default: 8501)",
    )
    p_srv.add_argument(
        "--host",
        default="0.0.0.0",
        help="Address to bind Streamlit server (default: 0.0.0.0)",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Main CLI entry point."""
    if argv is None:
        argv = sys.argv[1:]

    parser = build_parser()

    if not argv or argv == ["--help"] or argv == ["-h"]:
        parser.print_help()
        return 0

    args = parser.parse_args(argv)

    if args.command == "generate-data":
        return handle_generate_data(args)
    if args.command == "evaluate-suppliers":
        return handle_evaluate_suppliers(args)
    if args.command == "recommend":
        return handle_recommend(args)
    if args.command == "serve":
        return handle_serve(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
