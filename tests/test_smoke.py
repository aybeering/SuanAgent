from __future__ import annotations

import json
import tomllib
from pathlib import Path

from backtester.metrics import METRIC_KEYS
from backtester.simulate import DEFAULT_DATA_PATH, run_backtest
from orchestrator.policy_gate import apply_holdout_gate, evaluate_policy
from orchestrator.run_loop import run_pipeline
from orchestrator.smoke_contract import (
    validate_smoke_contract,
    validate_smoke_contract_payload,
)
from reports.generate_report import generate_report


def test_project_metadata_matches_current_scope() -> None:
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]

    assert project["name"] == "suan-agent-v0-5"
    assert project["description"] == (
        "Deterministic V0.5 strategy self-iteration prototype"
    )


def test_required_smoke_commands_are_documented_and_ci_covered() -> None:
    payload = validate_smoke_contract(repo_root=Path("."))

    assert validate_smoke_contract_payload(payload, repo_root=Path(".")) == ()
    assert payload["ok"] is True
    assert payload["source"]["path"] == "TASK.md"  # type: ignore[index]
    assert payload["source"]["ok"] is True  # type: ignore[index]
    assert payload["source"]["commands"] == payload["required_doc_commands"]  # type: ignore[index]
    assert payload["summary"]["missing_count"] == 0  # type: ignore[index]
    assert payload["policy"]["inspection_only"] is True  # type: ignore[index]
    assert payload["policy"]["does_not_run_backtests"] is True  # type: ignore[index]


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
    assert decision["reason_codes"] == []
    assert decision["failure_code"] == "none"
    assert decision["before"] == before
    assert decision["after"] == after


def test_holdout_gate_can_override_validation_acceptance() -> None:
    validation_decision = {
        "accepted": True,
        "reasons": [],
        "before": {},
        "after": {},
    }
    before = {
        "ev": 0.20,
        "total_pnl": 2.0,
        "max_drawdown": 0.02,
        "trade_count": 10,
        "fill_rate": 1.0,
        "avg_slippage": 0.002,
    }
    after = {
        "ev": 0.18,
        "total_pnl": 1.8,
        "max_drawdown": 0.025,
        "trade_count": 10,
        "fill_rate": 1.0,
        "avg_slippage": 0.002,
    }

    decision = apply_holdout_gate(
        validation_decision,
        before=before,
        after=after,
        rules={
            "enabled": True,
            "min_trade_count": 1,
            "min_ev_delta": -0.01,
            "max_drawdown_worsening": 0.02,
            "max_slippage_worsening": 0.005,
        },
    )

    assert decision["accepted"] is False
    assert decision["reasons"] == ["holdout ev delta -0.020000 < -0.01"]
    assert decision["failure_stage"] == "holdout_gate"
    assert decision["failure_code"] == "holdout_ev_delta_low"
    assert decision["reason_codes"][0]["code"] == "holdout_ev_delta_low"
    assert decision["holdout_policy"]["accepted"] is False  # type: ignore[index]


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
