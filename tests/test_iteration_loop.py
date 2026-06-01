from __future__ import annotations

import json
import shutil
from pathlib import Path

from agents.strategy_modifier_stub import NEW_THRESHOLD, OLD_THRESHOLD, propose_strategy_change
from backtester.schema import MarketSnapshot, StrategyOrder
from backtester.simulate import validate_strategy_orders
from orchestrator.config import load_project_config
from orchestrator.git_manager import apply_patch, ensure_git_repo, rollback_strategy
from orchestrator.iteration_loop import run_iteration_loop


def copy_repo_fixture(tmp_path: Path) -> Path:
    """Copy the small project into a temp repo for git mutation tests."""
    source = Path.cwd()
    repo = tmp_path / "repo"
    repo.mkdir()
    for directory in (
        "agents",
        "backtester",
        "config",
        "data",
        "orchestrator",
        "reports",
        "strategies",
    ):
        shutil.copytree(
            source / directory,
            repo / directory,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    for filename in ("AGENTS.md", "README.md", "TASK.md", "pyproject.toml", ".gitignore"):
        shutil.copy2(source / filename, repo / filename)
    (repo / "experiments").mkdir()
    (repo / "experiments" / ".gitkeep").write_text("", encoding="utf-8")
    return repo


def test_default_config_loads_dataset_splits() -> None:
    config = load_project_config(Path.cwd())

    assert config.max_rounds == 5
    assert config.datasets["train"] == "data/train/sample_markets.csv"
    assert config.datasets["validation"] == "data/validation/sample_markets.csv"
    assert config.datasets["holdout"] == "data/holdout/sample_markets.csv"
    assert config.policy["min_ev_improvement"] == 0.01


def test_stub_agent_generates_fixed_patch(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    report_path = tmp_path / "report.md"
    report_path.write_text("# Report\n", encoding="utf-8")

    proposal = propose_strategy_change(
        report_path=report_path,
        target_file=repo / "strategies/current_strategy.py",
        round_index=1,
        repo_root=repo,
    )

    assert proposal.applicable is True
    assert proposal.agent_name == "strategy_modifier_stub"
    assert proposal.expected_metric_change["trade_count"] == "increase"
    assert proposal.risk_notes
    assert "MIN_EDGE = 0.05" in proposal.patch_diff
    assert "MIN_EDGE = 0.04" in proposal.patch_diff


def test_patch_can_be_applied_and_rolled_back(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    ensure_git_repo(repo)
    report_path = tmp_path / "report.md"
    report_path.write_text("# Report\n", encoding="utf-8")
    proposal = propose_strategy_change(
        report_path=report_path,
        target_file=repo / "strategies/current_strategy.py",
        round_index=1,
        repo_root=repo,
    )

    apply_patch(repo, proposal.patch_diff)
    strategy_text = (repo / "strategies/current_strategy.py").read_text(encoding="utf-8")
    assert NEW_THRESHOLD in strategy_text

    rollback_strategy(repo)
    strategy_text = (repo / "strategies/current_strategy.py").read_text(encoding="utf-8")
    assert OLD_THRESHOLD in strategy_text


def test_iteration_loop_rejects_and_rolls_back_by_default(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)

    manifest = run_iteration_loop(run_id="reject-smoke", max_rounds=1, repo_root=repo)

    assert manifest["status"] == "stopped_max_rounds"
    run_dir = repo / "experiments/reject-smoke"
    round_dir = run_dir / "round_001"
    for filename in (
        "metrics_before.json",
        "report_before.md",
        "trades_before.csv",
        "train_metrics_before.json",
        "train_report_before.md",
        "train_trades_before.csv",
        "train_metrics_after.json",
        "train_report_after.md",
        "train_trades_after.csv",
        "holdout_metrics_before.json",
        "holdout_report_before.md",
        "holdout_trades_before.csv",
        "holdout_metrics_after.json",
        "holdout_report_after.md",
        "holdout_trades_after.csv",
        "proposal.json",
        "agent_response.txt",
        "patch.diff",
        "metrics_after.json",
        "report_after.md",
        "trades_after.csv",
        "decision.json",
    ):
        assert (round_dir / filename).exists()

    decision = json.loads((round_dir / "decision.json").read_text(encoding="utf-8"))
    assert decision["accepted"] is False
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )
    assert (repo / "experiments/index.jsonl").exists()


def test_iteration_loop_accepts_and_stops_with_relaxed_rules(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)

    manifest = run_iteration_loop(
        run_id="accept-smoke",
        max_rounds=5,
        repo_root=repo,
        policy_rules={
            "min_trade_count": 20,
            "min_ev_improvement": -1.0,
            "max_drawdown_worsening": 0.01,
            "max_slippage_worsening": 0.005,
        },
    )

    assert manifest["status"] == "accepted"
    assert manifest["completed_rounds"] == 1
    assert manifest["accepted_round"] == "round_001"
    assert NEW_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )


def test_iteration_loop_runs_at_most_five_rounds(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)

    manifest = run_iteration_loop(run_id="max-rounds", max_rounds=5, repo_root=repo)

    assert manifest["status"] == "stopped_max_rounds"
    assert manifest["completed_rounds"] == 5
    saved_manifest = json.loads(
        (repo / "experiments/max-rounds/manifest.json").read_text(encoding="utf-8")
    )
    assert saved_manifest["completed_rounds"] == 5


def test_iteration_loop_initializes_git_when_missing(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    assert not (repo / ".git").exists()

    run_iteration_loop(run_id="git-init", max_rounds=1, repo_root=repo)

    assert (repo / ".git").exists()


def test_strategy_order_validation_rejects_invalid_orders() -> None:
    snapshot = MarketSnapshot(
        timestamp="2026-01-01T00:00:00Z",
        market_id="m001",
        yes_price=0.42,
        fair_value=0.49,
        outcome=1,
        liquidity=120.0,
        next_yes_price=0.45,
    )

    valid = StrategyOrder(
        market_id="m001",
        side="YES",
        limit_price=0.42,
        stake=10.0,
        reason="valid",
    )
    assert validate_strategy_orders(snapshot, [valid]) == [valid]

    invalid = StrategyOrder(
        market_id="m002",
        side="YES",
        limit_price=0.42,
        stake=10.0,
        reason="wrong market",
    )
    try:
        validate_strategy_orders(snapshot, [invalid])
    except ValueError as exc:
        assert "market_id" in str(exc)
    else:
        raise AssertionError("expected invalid market_id to fail validation")
