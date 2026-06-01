from __future__ import annotations

import json
from pathlib import Path

from backtester.metrics import METRIC_KEYS
from backtester.simulate import DEFAULT_DATA_PATH, run_backtest
from orchestrator.policy_gate import evaluate_policy
from orchestrator.run_loop import run_pipeline
from reports.generate_report import generate_report


def test_backtester_can_run_on_sample_data() -> None:
    trades, metrics = run_backtest("strategies.baseline_strategy", DEFAULT_DATA_PATH)

    assert trades
    assert set(METRIC_KEYS).issubset(metrics)
    assert metrics["trade_count"] == len(trades)


def test_report_generation(tmp_path: Path) -> None:
    _, metrics = run_backtest("strategies.baseline_strategy", DEFAULT_DATA_PATH)
    report_path = tmp_path / "report.md"

    generate_report(
        strategy_name="strategies.baseline_strategy",
        metrics=metrics,
        trade_count=int(metrics["trade_count"]),
        output_path=report_path,
    )

    assert report_path.exists()
    assert "V0 Backtest Report" in report_path.read_text(encoding="utf-8")


def test_policy_gate_returns_valid_decision() -> None:
    before = {
        "ev": 0.01,
        "total_pnl": 1.0,
        "max_drawdown": 0.03,
        "trade_count": 20,
        "fill_rate": 1.0,
        "avg_slippage": 0.002,
    }
    after = {
        "ev": 0.03,
        "total_pnl": 3.0,
        "max_drawdown": 0.035,
        "trade_count": 21,
        "fill_rate": 1.0,
        "avg_slippage": 0.003,
    }

    decision = evaluate_policy(before, after)

    assert decision["accepted"] is True
    assert decision["reasons"] == []
    assert decision["before"] == before
    assert decision["after"] == after


def test_full_v0_run_loop_completes(tmp_path: Path) -> None:
    summary = run_pipeline(run_id="smoke", experiments_dir=tmp_path)
    run_dir = tmp_path / "smoke"

    assert summary["run_dir"] == str(run_dir)
    for filename in (
        "metrics_before.json",
        "metrics_after.json",
        "report_before.md",
        "report_after.md",
        "decision.json",
        "patch.diff",
        "trades_before.csv",
        "trades_after.csv",
    ):
        assert (run_dir / filename).exists()

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    assert isinstance(decision["accepted"], bool)
    assert isinstance(decision["reasons"], list)
