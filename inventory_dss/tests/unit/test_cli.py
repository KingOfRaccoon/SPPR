"""Unit tests for Inventory DSS command-line interface (CLI)."""

from __future__ import annotations

import argparse
from pathlib import Path

from inventory_dss.cli import build_parser, main


def test_cli_parser_build():
    """Verify CLI parser builds with all subcommands."""
    parser = build_parser()
    subparsers_actions = [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    assert len(subparsers_actions) == 1
    subcommands = set(subparsers_actions[0].choices.keys())
    assert subcommands == {"generate-data", "evaluate-suppliers", "recommend", "serve"}


def test_cli_help_returns_zero(capsys):
    """Running CLI with --help returns exit code 0 and prints usage."""
    code = main(["--help"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Decision Support System" in captured.out
    assert "generate-data" in captured.out
    assert "recommend" in captured.out


def test_cli_no_args_returns_zero(capsys):
    """Running CLI with no arguments prints usage and returns 0."""
    code = main([])
    assert code == 0
    captured = capsys.readouterr()
    assert "Decision Support System" in captured.out


def test_cli_generate_data_subcommand(tmp_path: Path, capsys):
    """Running generate-data subcommand outputs files to specified directory."""
    code = main(["generate-data", "--days", "30", "--output-dir", str(tmp_path)])
    assert code == 0
    captured = capsys.readouterr()
    assert "Dataset generated successfully" in captured.out

    assert (tmp_path / "skus.csv").exists()
    assert (tmp_path / "suppliers.csv").exists()
    assert (tmp_path / "demand_history.csv").exists()
    assert (tmp_path / "warehouse.json").exists()
    assert (tmp_path / "inventory_state.csv").exists()


def test_cli_evaluate_suppliers_subcommand(tmp_path: Path, capsys):
    """Running evaluate-suppliers subcommand outputs ranking table."""
    main(["generate-data", "--days", "30", "--output-dir", str(tmp_path)])
    code = main(["evaluate-suppliers", "--data-dir", str(tmp_path), "--method", "TOPSIS"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Supplier Evaluation Ranking" in captured.out
    assert "SUP-PREMIUM" in captured.out or "SUP-LOCAL" in captured.out


def test_cli_recommend_subcommand(tmp_path: Path, capsys):
    """Running recommend subcommand outputs recommendation table and executive summary."""
    main(["generate-data", "--days", "60", "--output-dir", str(tmp_path)])
    code = main(["recommend", "--data-dir", str(tmp_path), "--horizon", "14", "--service-level", "0.95"])
    assert code == 0
    captured = capsys.readouterr()
    assert "DSS Replenishment Recommendations" in captured.out
    assert "Portfolio Executive Summary" in captured.out
    assert "Total SKUs Evaluated" in captured.out
