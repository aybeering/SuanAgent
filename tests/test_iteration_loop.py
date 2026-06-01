from __future__ import annotations

import json
import shutil
import stat
from pathlib import Path

from agents.codex_cli_adapter import CodexCliModifier
from agents.codex_dry_run_adapter import (
    build_codex_command,
    build_codex_prompt,
    proposal_from_codex_output,
    workspace_ids_from_report,
)
from agents.strategy_modifier_stub import NEW_THRESHOLD, OLD_THRESHOLD, propose_strategy_change
from backtester.schema import MarketSnapshot, StrategyOrder
from backtester.simulate import validate_strategy_orders
from orchestrator.config import ProjectConfig, load_project_config
from orchestrator.git_manager import apply_patch, ensure_git_repo, rollback_strategy
from orchestrator.iteration_loop import run_iteration_loop
from orchestrator.patch_parser import (
    PatchParseError,
    changed_paths_from_diff,
    extract_unified_diff,
    validate_patch_targets,
)
from orchestrator.workspace_manager import create_isolated_workspace


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
        "docs",
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
    assert config.strategy_modifier == "fixed_patch_stub"
    assert config.datasets["train"] == "data/train/sample_markets.csv"
    assert config.datasets["validation"] == "data/validation/sample_markets.csv"
    assert config.datasets["holdout"] == "data/holdout/sample_markets.csv"
    assert config.policy["min_ev_improvement"] == 0.01


def test_strategy_interface_document_covers_agent_boundaries() -> None:
    contract = Path("docs/strategy_interface.md").read_text(encoding="utf-8")

    assert "generate_orders(snapshot: MarketSnapshot)" in contract
    assert "list[StrategyOrder]" in contract
    assert "Invalid outputs fail before simulation" in contract
    assert "network calls" in contract


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


def test_codex_dry_run_adapter_records_non_applicable_proposal(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    default = load_project_config(repo)
    config = ProjectConfig(
        baseline_strategy_module=default.baseline_strategy_module,
        current_strategy_module=default.current_strategy_module,
        experiments_dir=default.experiments_dir,
        max_rounds=1,
        datasets=default.datasets,
        policy=default.policy,
        strategy_path=default.strategy_path,
        strategy_modifier="codex_dry_run",
        modifier_settings={
            "executable": "codex",
            "model": "dry-run-model",
            "sandbox": "workspace-write",
        },
        stub_old_threshold=default.stub_old_threshold,
        stub_new_threshold=default.stub_new_threshold,
    )

    manifest = run_iteration_loop(
        run_id="dry-run",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    round_dir = repo / "experiments/dry-run/round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    decision = json.loads((round_dir / "decision.json").read_text(encoding="utf-8"))

    assert manifest["status"] == "stopped_max_rounds"
    assert proposal["agent_name"] == "codex_cli_dry_run"
    assert proposal["applicable"] is False
    assert "dry-run" in proposal["raw_response"]
    assert proposal["command"][:6] == [
        "codex",
        "exec",
        "--model",
        "dry-run-model",
        "--sandbox",
        "workspace-write",
    ]
    assert "Only modify: strategies/current_strategy.py" in proposal["prompt"]
    assert "Return a unified diff patch only." in proposal["prompt"]
    assert "workspaces/dry-run/round_001/strategy_workspace" in proposal["workspace_path"]
    assert (
        repo
        / "workspaces/dry-run/round_001/strategy_workspace/strategies/current_strategy.py"
    ).exists()
    assert decision["accepted"] is False
    assert "does not emit patches" in decision["reasons"][0]
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )


def test_codex_cli_adapter_disabled_does_not_execute(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    default = load_project_config(repo)
    config = ProjectConfig(
        baseline_strategy_module=default.baseline_strategy_module,
        current_strategy_module=default.current_strategy_module,
        experiments_dir=default.experiments_dir,
        max_rounds=1,
        datasets=default.datasets,
        policy=default.policy,
        strategy_path=default.strategy_path,
        strategy_modifier="codex_cli",
        modifier_settings={
            "executable": "missing-codex-for-disabled-test",
            "model": "dry-run-model",
            "sandbox": "workspace-write",
            "execute": False,
        },
        stub_old_threshold=default.stub_old_threshold,
        stub_new_threshold=default.stub_new_threshold,
    )

    run_iteration_loop(run_id="codex-disabled", max_rounds=1, repo_root=repo, config=config)

    round_dir = repo / "experiments/codex-disabled/round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    assert proposal["agent_name"] == "codex_cli"
    assert proposal["applicable"] is False
    assert proposal["rejection_reason"] == "Codex CLI execution disabled."
    assert proposal["command"][0] == "missing-codex-for-disabled-test"


def test_codex_cli_adapter_execute_success_parses_patch(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    report_path = repo / "experiments/run-1/round_001/train_report_before.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# Report\n", encoding="utf-8")
    fake_codex = write_fake_command(
        tmp_path,
        "fake_codex_success.py",
        """#!/usr/bin/env python3
import sys
sys.stdin.read()
print('--- a/strategies/current_strategy.py')
print('+++ b/strategies/current_strategy.py')
print('@@ -9,7 +9,7 @@')
print('-MIN_EDGE = 0.05')
print('+MIN_EDGE = 0.04')
""",
    )
    adapter = CodexCliModifier(
        executable=str(fake_codex),
        model="test",
        sandbox="workspace-write",
        execute=True,
        timeout_seconds=5,
    )

    proposal = adapter.propose_strategy_change(
        report_path=report_path,
        target_file=repo / "strategies/current_strategy.py",
        round_index=1,
        repo_root=repo,
        old_threshold=OLD_THRESHOLD,
        new_threshold=NEW_THRESHOLD,
    )

    assert proposal.applicable is True
    assert proposal.agent_name == "codex_cli"
    assert "MIN_EDGE = 0.04" in proposal.patch_diff
    assert proposal.command[0] == str(fake_codex)


def test_codex_cli_adapter_execute_failure_is_rejected(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    report_path = repo / "experiments/run-2/round_001/train_report_before.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# Report\n", encoding="utf-8")
    fake_codex = write_fake_command(
        tmp_path,
        "fake_codex_failure.py",
        """#!/usr/bin/env python3
import sys
print('bad things', file=sys.stderr)
raise SystemExit(7)
""",
    )
    adapter = CodexCliModifier(
        executable=str(fake_codex),
        model="test",
        sandbox="workspace-write",
        execute=True,
        timeout_seconds=5,
    )

    proposal = adapter.propose_strategy_change(
        report_path=report_path,
        target_file=repo / "strategies/current_strategy.py",
        round_index=1,
        repo_root=repo,
        old_threshold=OLD_THRESHOLD,
        new_threshold=NEW_THRESHOLD,
    )

    assert proposal.applicable is False
    assert proposal.rejection_reason == "Codex CLI exited with 7."
    assert "bad things" in proposal.raw_response


def test_codex_prompt_and_command_builders_are_deterministic() -> None:
    prompt = build_codex_prompt(
        report_text="# Report\nmetric: value\n",
        target_file="strategies/current_strategy.py",
        round_index=3,
    )
    command = build_codex_command(
        executable="codex",
        model="gpt-test",
        sandbox="workspace-write",
        target_file="strategies/current_strategy.py",
    )

    assert "Round: 3" in prompt
    assert "Only modify: strategies/current_strategy.py" in prompt
    assert command == [
        "codex",
        "exec",
        "--model",
        "gpt-test",
        "--sandbox",
        "workspace-write",
        "--",
        "Modify only strategies/current_strategy.py and return a patch.",
    ]


def test_workspace_ids_are_derived_from_report_path() -> None:
    run_id, round_id = workspace_ids_from_report(
        Path("experiments/example-run/round_003/train_report_before.md")
    )

    assert run_id == "example-run"
    assert round_id == "round_003"


def test_create_isolated_workspace_copies_minimal_project(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)

    workspace = create_isolated_workspace(
        repo_root=repo,
        workspace_root=repo / "workspaces",
        run_id="run-1",
        round_id="round_001",
    )

    assert (workspace / "strategies/current_strategy.py").exists()
    assert (workspace / "backtester/simulate.py").exists()
    assert (workspace / "docs/strategy_interface.md").exists()
    assert not (workspace / ".git").exists()


def test_patch_parser_extracts_and_validates_strategy_diff() -> None:
    raw_output = """
Here is the patch:

```diff
--- a/strategies/current_strategy.py
+++ b/strategies/current_strategy.py
@@ -1 +1 @@
-MIN_EDGE = 0.05
+MIN_EDGE = 0.04
```
"""

    patch = extract_unified_diff(raw_output)

    assert changed_paths_from_diff(patch) == {"strategies/current_strategy.py"}
    validate_patch_targets(patch, Path("strategies/current_strategy.py"))


def test_patch_parser_rejects_disallowed_paths() -> None:
    patch = """--- a/backtester/simulate.py
+++ b/backtester/simulate.py
@@ -1 +1 @@
-old
+new
"""

    try:
        validate_patch_targets(patch, Path("strategies/current_strategy.py"))
    except PatchParseError as exc:
        assert "disallowed" in str(exc)
    else:
        raise AssertionError("expected non-strategy patch to be rejected")


def test_codex_output_is_converted_to_applicable_proposal(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    report_path = repo / "experiments/run-1/round_001/train_report_before.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# Report\n", encoding="utf-8")
    workspace = repo / "workspaces/run-1/round_001/strategy_workspace"
    raw_output = """--- a/strategies/current_strategy.py
+++ b/strategies/current_strategy.py
@@ -9,7 +9,7 @@
-MIN_EDGE = 0.05
+MIN_EDGE = 0.04
"""

    proposal = proposal_from_codex_output(
        raw_output=raw_output,
        report_path=report_path,
        target_file=repo / "strategies/current_strategy.py",
        round_index=1,
        repo_root=repo,
        prompt="prompt",
        command=["codex", "exec"],
        workspace_path=workspace,
    )

    assert proposal.applicable is True
    assert proposal.agent_name == "codex_cli"
    assert proposal.patch_diff.startswith("--- a/strategies/current_strategy.py")
    assert proposal.workspace_path == str(workspace)


def write_fake_command(tmp_path: Path, filename: str, content: str) -> Path:
    """Write an executable fake command for subprocess adapter tests."""
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


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
