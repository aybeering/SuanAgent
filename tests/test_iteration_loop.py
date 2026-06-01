from __future__ import annotations

import json
import shutil
import stat
import subprocess
import sys
import difflib
from dataclasses import replace
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
from orchestrator.agent_context import build_agent_context, build_agent_context_payload
from orchestrator.config import ProjectConfig, load_project_config
from orchestrator.git_manager import apply_patch, ensure_git_repo, rollback_strategy
from orchestrator.iteration_loop import run_iteration_loop
from orchestrator.outcome_memory import (
    append_outcome_memory,
    direction_filter_rejection_reason,
    direction_prior,
    read_outcome_memory,
)
from orchestrator.run_loop import run_pipeline
from orchestrator.preflight import run_preflight
from orchestrator.experiments import (
    candidate_leaderboard,
    experiment_leaderboard,
    list_experiments,
    show_experiment,
    summarize_experiments,
)
from orchestrator.patch_parser import (
    PatchParseError,
    changed_paths_from_diff,
    extract_json_object,
    extract_unified_diff,
    validate_patch_targets,
)
from orchestrator.proposal import StrategyProposal, validate_proposal_contract
from orchestrator.workspace_manager import (
    create_isolated_workspace,
    workspace_mutation_errors,
    workspace_snapshot,
)


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
    assert config.memory_failed_patch_threshold == 2
    assert config.memory_failed_direction_threshold == 3
    assert config.memory_fallback_modifier == "adaptive_stub"
    assert config.memory_fallback_modifiers == (
        "adaptive_stub",
        "conservative_stub",
    )
    assert config.stop_after_no_improvement_rounds == 3
    assert config.min_probe_ev_delta == 0.0
    assert config.min_validation_ev_delta == 0.0
    assert config.explore_after_no_improvement_rounds == 2
    assert config.explore_low_sample_threshold == 1
    assert config.explore_bonus == 12
    assert config.datasets["train"] == "data/train/sample_markets.csv"
    assert config.datasets["validation"] == "data/validation/sample_markets.csv"
    assert config.datasets["holdout"] == "data/holdout/sample_markets.csv"
    assert config.policy["min_ev_improvement"] == 0.01
    assert config.holdout_policy["enabled"] is True
    assert config.holdout_policy["min_ev_delta"] == -0.01
    assert config.stop_on_repeated_proposal is True


def test_example_configs_load_modifier_modes() -> None:
    dry_run = load_project_config(Path.cwd(), Path("config/codex_dry_run.json"))
    guarded = load_project_config(Path.cwd(), Path("config/codex_cli_guarded.json"))
    adaptive = load_project_config(Path.cwd(), Path("config/adaptive_stub.json"))

    assert dry_run.strategy_modifier == "codex_cli_dry_run"
    assert guarded.strategy_modifier == "codex_cli"
    assert adaptive.strategy_modifier == "adaptive_stub"
    assert adaptive.max_rounds == 2
    assert guarded.modifier_settings["execute"] is False


def test_preflight_passes_default_config() -> None:
    result = run_preflight(repo_root=Path.cwd(), config_path=Path("config/default.json"))

    assert result.ok is True
    assert result.errors == []


def test_preflight_passes_adaptive_stub_config() -> None:
    result = run_preflight(
        repo_root=Path.cwd(),
        config_path=Path("config/adaptive_stub.json"),
    )

    assert result.ok is True
    assert result.errors == []


def test_preflight_rejects_missing_dataset(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    (repo / "data/train/sample_markets.csv").unlink()

    result = run_preflight(repo_root=repo, config_path=repo / "config/default.json")

    assert result.ok is False
    assert any("dataset path does not exist" in error for error in result.errors)


def test_preflight_rejects_enabled_missing_codex(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config_path = repo / "config/missing_codex.json"
    config = json.loads((repo / "config/codex_cli_guarded.json").read_text())
    config["codex_cli"]["execute"] = True
    config["codex_cli"]["executable"] = "definitely-not-a-real-codex-command"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_preflight(repo_root=repo, config_path=config_path)

    assert result.ok is False
    assert any("executable not found" in error for error in result.errors)


def test_preflight_rejects_negative_memory_filter_threshold(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config_path = repo / "config/negative_memory_filter.json"
    config = json.loads((repo / "config/default.json").read_text())
    config["memory_filter"]["failed_patch_threshold"] = -1
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_preflight(repo_root=repo, config_path=config_path)

    assert result.ok is False
    assert any("memory_filter.failed_patch_threshold" in error for error in result.errors)


def test_preflight_rejects_negative_direction_filter_threshold(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config_path = repo / "config/negative_direction_filter.json"
    config = json.loads((repo / "config/default.json").read_text())
    config["memory_filter"]["failed_direction_threshold"] = -1
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_preflight(repo_root=repo, config_path=config_path)

    assert result.ok is False
    assert any(
        "memory_filter.failed_direction_threshold" in error
        for error in result.errors
    )


def test_preflight_rejects_negative_no_improvement_threshold(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config_path = repo / "config/negative_exploration.json"
    config = json.loads((repo / "config/default.json").read_text())
    config["exploration"]["stop_after_no_improvement_rounds"] = -1
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_preflight(repo_root=repo, config_path=config_path)

    assert result.ok is False
    assert any(
        "exploration.stop_after_no_improvement_rounds" in error
        for error in result.errors
    )


def test_preflight_rejects_negative_exploration_bonus(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config_path = repo / "config/negative_exploration_bonus.json"
    config = json.loads((repo / "config/default.json").read_text())
    config["exploration"]["explore_bonus"] = -1
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_preflight(repo_root=repo, config_path=config_path)

    assert result.ok is False
    assert any("exploration.explore_bonus" in error for error in result.errors)


def test_preflight_rejects_unknown_memory_fallback_modifier(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config_path = repo / "config/bad_memory_fallback.json"
    config = json.loads((repo / "config/default.json").read_text())
    config["memory_filter"]["fallback_modifiers"] = ["missing_modifier"]
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_preflight(repo_root=repo, config_path=config_path)

    assert result.ok is False
    assert any("memory_filter.fallback_modifiers" in error for error in result.errors)


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
    assert proposal.direction_tag == "lower_min_edge"
    assert validate_proposal_contract(
        proposal=proposal,
        expected_target_file=Path("strategies/current_strategy.py"),
        expected_round_index=1,
    ) == ()
    assert proposal.hypotheses
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
        "probe_data.csv",
        "probe_metrics_before.json",
        "probe_report_before.md",
        "probe_trades_before.csv",
        "agent_context.md",
        "agent_context.json",
        "proposal_attempts.json",
        "proposal.json",
        "agent_response.txt",
        "patch.diff",
        "metrics_after.json",
        "report_after.md",
        "trades_after.csv",
        "decision.json",
    ):
        assert (round_dir / filename).exists()
    assert (run_dir / "candidate_leaderboard.json").exists()

    decision = json.loads((round_dir / "decision.json").read_text(encoding="utf-8"))
    attempts = json.loads(
        (round_dir / "proposal_attempts.json").read_text(encoding="utf-8")
    )
    leaderboard = json.loads(
        (run_dir / "candidate_leaderboard.json").read_text(encoding="utf-8")
    )
    selected_attempt = next(attempt for attempt in attempts if attempt["selected"])
    assert decision["accepted"] is False
    assert selected_attempt["candidate_score"] > 0
    assert selected_attempt["direction_tag"] == "lower_min_edge"
    assert selected_attempt["validation_status"] == "evaluated"
    assert isinstance(selected_attempt["validation_ev_delta"], float)
    assert selected_attempt["probe_metrics_before"]
    assert selected_attempt["probe_metrics_after"]
    assert selected_attempt["probe_artifacts"]["metrics"]
    assert (round_dir / selected_attempt["probe_artifacts"]["metrics"]).exists()
    assert leaderboard[0]["selected"] is True
    assert leaderboard[0]["direction_tag"] == "lower_min_edge"
    assert leaderboard[0]["validation_status"] == "evaluated"
    assert leaderboard[0]["round_id"] == "round_001"
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )
    assert (repo / "experiments/index.jsonl").exists()
    summary_text = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "Experiment Summary" in summary_text
    assert "round_001" in summary_text
    assert "strategy_modifier_stub" in summary_text
    assert "ev improvement" in summary_text
    context_text = (round_dir / "agent_context.md").read_text(encoding="utf-8")
    context_payload = json.loads(
        (round_dir / "agent_context.json").read_text(encoding="utf-8")
    )
    assert "No prior rounds in this run." in context_text
    assert context_payload["schema_version"] == "agent_context_v1"
    assert context_payload["current_round_id"] == "round_001"
    assert context_payload["target_file"] == "strategies/current_strategy.py"
    assert context_payload["prior_rounds"] == []


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
    summary_text = (
        repo / "experiments/accept-smoke/summary.md"
    ).read_text(encoding="utf-8")
    assert "- Status: `accepted`" in summary_text
    assert "- Accepted round: `round_001`" in summary_text
    assert NEW_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )


def test_iteration_loop_holdout_gate_rejects_relaxed_validation_acceptance(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    config = replace(
        load_project_config(repo),
        holdout_policy={
            "enabled": True,
            "min_trade_count": 1,
            "min_ev_delta": 0.02,
            "max_drawdown_worsening": 0.02,
            "max_slippage_worsening": 0.005,
        },
    )

    manifest = run_iteration_loop(
        run_id="holdout-gate-reject",
        max_rounds=1,
        repo_root=repo,
        config=config,
        policy_rules={
            "min_trade_count": 20,
            "min_ev_improvement": -1.0,
            "max_drawdown_worsening": 0.01,
            "max_slippage_worsening": 0.005,
        },
    )

    round_dir = repo / "experiments/holdout-gate-reject/round_001"
    decision = json.loads((round_dir / "decision.json").read_text(encoding="utf-8"))
    saved_manifest = json.loads(
        (repo / "experiments/holdout-gate-reject/manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["status"] == "stopped_max_rounds"
    assert manifest["rounds"][0]["accepted"] is False  # type: ignore[index]
    assert decision["accepted"] is False
    assert decision["reasons"][0].startswith("holdout ev delta ")
    assert decision["reasons"][0].endswith(" < 0.02")
    assert decision["holdout_policy"]["enabled"] is True
    assert saved_manifest["holdout_policy"]["min_ev_delta"] == 0.02
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )


def test_iteration_loop_runs_at_most_five_rounds(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    no_fallback = replace(
        load_project_config(repo),
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
        stop_after_no_improvement_rounds=0,
    )

    manifest = run_iteration_loop(
        run_id="max-rounds",
        max_rounds=5,
        repo_root=repo,
        config=no_fallback,
        stop_on_repeated_proposal=False,
    )

    assert manifest["status"] == "stopped_max_rounds"
    assert manifest["completed_rounds"] == 5
    saved_manifest = json.loads(
        (repo / "experiments/max-rounds/manifest.json").read_text(encoding="utf-8")
    )
    assert saved_manifest["completed_rounds"] == 5
    round_001 = json.loads(
        (repo / "experiments/max-rounds/round_001/proposal.json").read_text(
            encoding="utf-8"
        )
    )
    round_002 = json.loads(
        (repo / "experiments/max-rounds/round_002/proposal.json").read_text(
            encoding="utf-8"
        )
    )
    assert round_001["patch_sha256"]
    assert round_001["is_repeat_patch"] is False
    assert round_001["quality_checks"]["has_hypotheses"] is True
    assert round_002["is_repeat_patch"] is True
    assert round_002["repeat_of_round"] == "round_001"


def test_iteration_loop_stops_on_repeated_proposal_by_default(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    no_fallback = replace(
        load_project_config(repo),
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
        stop_after_no_improvement_rounds=0,
    )

    manifest = run_iteration_loop(
        run_id="repeat-stop",
        max_rounds=5,
        repo_root=repo,
        config=no_fallback,
    )

    assert manifest["status"] == "stopped_repeated_proposal"
    assert manifest["completed_rounds"] == 2
    assert manifest["stop_reason"] == "round_002 repeated patch from round_001"
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )

    run_dir = repo / "experiments/repeat-stop"
    saved_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    proposal = json.loads(
        (run_dir / "round_002/proposal.json").read_text(encoding="utf-8")
    )
    summary_text = (run_dir / "summary.md").read_text(encoding="utf-8")

    assert saved_manifest["status"] == "stopped_repeated_proposal"
    assert saved_manifest["stop_reason"] == "round_002 repeated patch from round_001"
    assert proposal["is_repeat_patch"] is True
    context_text = (run_dir / "round_002/agent_context.md").read_text(
        encoding="utf-8"
    )
    assert "round_001" in context_text
    assert "ev improvement" in context_text
    assert proposal["patch_sha256"][:12] in context_text
    assert "yes (round_001)" in summary_text
    assert "- Stop reason: `round_002 repeated patch from round_001`" in summary_text


def test_iteration_loop_stops_after_no_improvement_window(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config = replace(
        load_project_config(repo),
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
        stop_after_no_improvement_rounds=2,
        min_probe_ev_delta=1.0,
        min_validation_ev_delta=1.0,
    )

    manifest = run_iteration_loop(
        run_id="no-improvement-stop",
        max_rounds=5,
        repo_root=repo,
        config=config,
        stop_on_repeated_proposal=False,
    )

    assert manifest["status"] == "stopped_no_improvement"
    assert manifest["completed_rounds"] == 2
    assert "no probe or validation EV improvement" in str(manifest["stop_reason"])
    saved_manifest = json.loads(
        (repo / "experiments/no-improvement-stop/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert saved_manifest["exploration_policy"]["stop_after_no_improvement_rounds"] == 2
    assert saved_manifest["status"] == "stopped_no_improvement"


def test_iteration_loop_rejects_known_failed_patch_from_memory(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config = replace(
        load_project_config(repo),
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
        stop_after_no_improvement_rounds=0,
    )

    run_iteration_loop(
        run_id="memory-fail-1",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )
    run_iteration_loop(
        run_id="memory-fail-2",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )
    manifest = run_iteration_loop(
        run_id="memory-filtered",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    run_dir = repo / "experiments/memory-filtered"
    round_dir = run_dir / "round_001"
    decision = json.loads((round_dir / "decision.json").read_text(encoding="utf-8"))
    metrics_before = json.loads(
        (round_dir / "metrics_before.json").read_text(encoding="utf-8")
    )
    metrics_after = json.loads(
        (round_dir / "metrics_after.json").read_text(encoding="utf-8")
    )
    summary_text = (run_dir / "summary.md").read_text(encoding="utf-8")
    memory = read_outcome_memory(repo / "experiments")

    assert manifest["status"] == "stopped_max_rounds"
    assert manifest["rounds"][0]["proposal_memory_rejected"] is True  # type: ignore[index]
    assert decision["accepted"] is False
    assert decision["reasons"][0].startswith("memory filter rejected patch")
    assert metrics_before == metrics_after
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )
    assert "memory filter rejected patch" in summary_text
    assert memory[-1]["run_id"] == "memory-filtered"
    assert memory[-1]["validation_ev_delta"] == 0.0
    assert memory[-1]["direction_tag"] == "lower_min_edge"


def test_iteration_loop_uses_fallback_after_memory_rejected_primary(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    no_fallback = replace(
        load_project_config(repo),
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
    )

    run_iteration_loop(
        run_id="fallback-source-1",
        max_rounds=1,
        repo_root=repo,
        config=no_fallback,
    )
    run_iteration_loop(
        run_id="fallback-source-2",
        max_rounds=1,
        repo_root=repo,
        config=no_fallback,
    )
    manifest = run_iteration_loop(
        run_id="fallback-target",
        max_rounds=1,
        repo_root=repo,
    )

    run_dir = repo / "experiments/fallback-target"
    round_dir = run_dir / "round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    attempts = json.loads(
        (round_dir / "proposal_attempts.json").read_text(encoding="utf-8")
    )
    decision = json.loads((round_dir / "decision.json").read_text(encoding="utf-8"))
    summary_text = (run_dir / "summary.md").read_text(encoding="utf-8")

    assert manifest["rounds"][0]["primary_proposal_memory_rejected"] is True  # type: ignore[index]
    assert manifest["rounds"][0]["proposal_fallback_used"] is True  # type: ignore[index]
    assert manifest["rounds"][0]["proposal_memory_rejected"] is False  # type: ignore[index]
    assert attempts[0]["role"] == "primary"
    assert attempts[0]["memory_filter_rejected"] is True
    assert attempts[1]["role"] == "fallback_01"
    assert attempts[1]["memory_filter_rejected"] is False
    assert attempts[1]["selected"] is True
    assert attempts[1]["candidate_score"] > 0
    assert attempts[1]["score_reasons"]
    assert proposal["agent_name"] == "strategy_modifier_adaptive_stub"
    assert proposal["direction_tag"] == "reduce_stake"
    assert "STAKE = 8.0" in proposal["patch_diff"]
    assert not decision["reasons"][0].startswith("memory filter rejected patch")
    assert "selected fallback_01 with score" in summary_text


def test_iteration_loop_tries_next_candidate_after_fallback_memory_rejection(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    default = load_project_config(repo)
    no_fallback = replace(
        default,
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
    )
    adaptive_without_fallback = replace(
        default,
        strategy_modifier="adaptive_stub",
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
    )

    run_iteration_loop(
        run_id="candidate-min-edge-1",
        max_rounds=1,
        repo_root=repo,
        config=no_fallback,
    )
    run_iteration_loop(
        run_id="candidate-min-edge-2",
        max_rounds=1,
        repo_root=repo,
        config=no_fallback,
    )
    run_iteration_loop(
        run_id="candidate-stake-1",
        max_rounds=1,
        repo_root=repo,
        config=adaptive_without_fallback,
    )
    run_iteration_loop(
        run_id="candidate-stake-2",
        max_rounds=1,
        repo_root=repo,
        config=adaptive_without_fallback,
    )
    manifest = run_iteration_loop(
        run_id="candidate-target",
        max_rounds=1,
        repo_root=repo,
        config=default,
    )

    round_dir = repo / "experiments/candidate-target/round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    attempts = json.loads(
        (round_dir / "proposal_attempts.json").read_text(encoding="utf-8")
    )

    assert manifest["rounds"][0]["proposal_fallback_used"] is True  # type: ignore[index]
    assert manifest["rounds"][0]["proposal_memory_rejected"] is False  # type: ignore[index]
    assert [attempt["role"] for attempt in attempts] == [
        "primary",
        "fallback_01",
        "fallback_02",
    ]
    assert [attempt["status"] for attempt in attempts] == [
        "memory_rejected",
        "memory_rejected",
        "selectable",
    ]
    assert attempts[2]["selected"] is True
    assert attempts[2]["candidate_score"] > attempts[0]["candidate_score"]
    assert proposal["agent_name"] == "strategy_modifier_conservative_stub"
    assert proposal["direction_tag"] == "raise_min_edge"
    assert "MIN_EDGE = 0.06" in proposal["patch_diff"]


def test_direction_memory_filter_rejects_failed_direction(tmp_path: Path) -> None:
    experiments_dir = tmp_path / "experiments"
    for index in range(3):
        append_outcome_memory(
            experiments_dir=experiments_dir,
            record={
                "kind": "proposal_outcome",
                "run_id": f"direction-source-{index}",
                "round_id": "round_001",
                "direction_tag": "lower_min_edge",
                "accepted": False,
                "patch_sha256": f"different-patch-{index}",
            },
        )

    reason = direction_filter_rejection_reason(
        experiments_dir=experiments_dir,
        direction_tag="lower_min_edge",
        threshold=3,
        exclude_run_id="direction-target",
    )

    assert reason.startswith("memory filter rejected direction lower_min_edge")


def test_direction_prior_scores_historical_outcomes(tmp_path: Path) -> None:
    experiments_dir = tmp_path / "experiments"
    append_outcome_memory(
        experiments_dir=experiments_dir,
        record={
            "kind": "proposal_outcome",
            "run_id": "prior-success-1",
            "round_id": "round_001",
            "direction_tag": "raise_min_edge",
            "accepted": True,
            "validation_ev_delta": 0.02,
        },
    )
    append_outcome_memory(
        experiments_dir=experiments_dir,
        record={
            "kind": "proposal_outcome",
            "run_id": "prior-success-2",
            "round_id": "round_001",
            "direction_tag": "raise_min_edge",
            "accepted": False,
            "validation_ev_delta": 0.0,
        },
    )

    prior = direction_prior(
        experiments_dir=experiments_dir,
        direction_tag="raise_min_edge",
        exclude_run_id="new-run",
    )

    assert prior["sample_count"] == 2
    assert prior["accepted_count"] == 1
    assert prior["failed_count"] == 1
    assert prior["accept_rate"] == 0.5
    assert prior["avg_validation_ev_delta"] == 0.01
    assert prior["score_delta"] > 0


def test_iteration_loop_uses_direction_prior_to_rank_candidates(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    config = replace(
        load_project_config(repo),
        memory_failed_patch_threshold=0,
        memory_failed_direction_threshold=99,
        memory_fallback_modifier="conservative_stub",
        memory_fallback_modifiers=("conservative_stub",),
        stop_after_no_improvement_rounds=0,
    )
    for index in range(2):
        append_outcome_memory(
            experiments_dir=repo / "experiments",
            record={
                "kind": "proposal_outcome",
                "run_id": f"lower-prior-fail-{index}",
                "round_id": "round_001",
                "direction_tag": "lower_min_edge",
                "accepted": False,
                "patch_sha256": f"lower-different-{index}",
                "validation_ev_delta": 0.0,
            },
        )
    for index in range(5):
        append_outcome_memory(
            experiments_dir=repo / "experiments",
            record={
                "kind": "proposal_outcome",
                "run_id": f"raise-prior-success-{index}",
                "round_id": "round_001",
                "direction_tag": "raise_min_edge",
                "accepted": True,
                "patch_sha256": f"raise-different-{index}",
                "validation_ev_delta": 0.02,
            },
        )

    manifest = run_iteration_loop(
        run_id="direction-prior-rank",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    round_dir = repo / "experiments/direction-prior-rank/round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    attempts = json.loads(
        (round_dir / "proposal_attempts.json").read_text(encoding="utf-8")
    )

    assert manifest["rounds"][0]["proposal_fallback_used"] is True  # type: ignore[index]
    assert proposal["direction_tag"] == "raise_min_edge"
    assert attempts[0]["direction_prior"]["score_delta"] < 0
    assert attempts[1]["direction_prior"]["score_delta"] > 0
    assert attempts[1]["selected"] is True
    assert any(
        "direction prior" in reason
        for reason in attempts[1]["score_reasons"]
    )


def test_iteration_loop_explores_low_sample_direction_after_stalls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    config = replace(
        load_project_config(repo),
        strategy_modifier="exploit_test_primary",
        memory_failed_patch_threshold=0,
        memory_failed_direction_threshold=99,
        memory_fallback_modifier="explore_test_fallback",
        memory_fallback_modifiers=("explore_test_fallback",),
        stop_after_no_improvement_rounds=0,
        explore_after_no_improvement_rounds=2,
        explore_low_sample_threshold=1,
        explore_bonus=20,
    )

    class ExploitPrimary:
        def propose_strategy_change(self, **kwargs) -> StrategyProposal:
            return build_test_replacement_proposal(
                target_file=kwargs["target_file"],
                repo_root=kwargs["repo_root"],
                round_index=kwargs["round_index"],
                old_text="MIN_EDGE = 0.05",
                new_text="MIN_EDGE = 0.04",
                agent_name="exploit_primary",
                direction_tag="lower_min_edge",
                expected_metric_change={
                    "trade_count": "increase",
                    "ev": "uncertain",
                },
                risk_notes="May increase lower-quality trades.",
            )

    class ExploreFallback:
        def propose_strategy_change(self, **kwargs) -> StrategyProposal:
            return build_test_replacement_proposal(
                target_file=kwargs["target_file"],
                repo_root=kwargs["repo_root"],
                round_index=kwargs["round_index"],
                old_text="STAKE = 10.0",
                new_text="STAKE = 8.0",
                agent_name="explore_fallback",
                direction_tag="reduce_stake",
                expected_metric_change={"trade_count": "decrease"},
                risk_notes="May increase uncertainty while exploring sizing.",
            )

    def modifier_factory(name: str, _settings: dict[str, object]) -> object:
        if name == "exploit_test_primary":
            return ExploitPrimary()
        if name == "explore_test_fallback":
            return ExploreFallback()
        raise AssertionError(f"unexpected modifier name: {name}")

    monkeypatch.setattr(
        "orchestrator.iteration_loop.get_strategy_modifier",
        modifier_factory,
    )

    manifest = run_iteration_loop(
        run_id="explore-after-stall",
        max_rounds=3,
        repo_root=repo,
        config=config,
        stop_on_repeated_proposal=False,
    )

    run_dir = repo / "experiments/explore-after-stall"
    attempts_3 = json.loads(
        (run_dir / "round_003/proposal_attempts.json").read_text(encoding="utf-8")
    )
    selected = next(attempt for attempt in attempts_3 if attempt["selected"])
    context_3 = (run_dir / "round_003/agent_context.md").read_text(encoding="utf-8")
    summary_text = (run_dir / "summary.md").read_text(encoding="utf-8")

    assert manifest["completed_rounds"] == 3
    assert manifest["rounds"][2]["proposal_selected_role"] == "fallback_01"  # type: ignore[index]
    assert attempts_3[0]["direction_tag"] == "lower_min_edge"
    assert attempts_3[0]["exploration_bonus"]["active"] is False
    assert selected["direction_tag"] == "reduce_stake"
    assert selected["exploration_bonus"]["active"] is True
    assert selected["exploration_bonus"]["score_delta"] == 20
    assert any("exploration bonus" in reason for reason in selected["score_reasons"])
    assert "Explore" in summary_text
    assert "Explore" in context_3


def test_proposal_contract_rejects_invalid_patch_target() -> None:
    proposal = StrategyProposal(
        agent_name="bad_agent",
        round_index=1,
        target_file="strategies/current_strategy.py",
        summary="Touches the wrong file.",
        risk_notes="Invalid proposal for contract test.",
        expected_metric_change={"ev": "uncertain"},
        raw_response="bad patch",
        patch_diff=(
            "--- a/backtester/simulate.py\n"
            "+++ b/backtester/simulate.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        ),
        applicable=True,
        direction_tag="bad_direction",
        hypotheses=("This should fail contract validation.",),
    )

    errors = validate_proposal_contract(
        proposal=proposal,
        expected_target_file=Path("strategies/current_strategy.py"),
        expected_round_index=1,
    )

    assert any("disallowed files" in error for error in errors)


def test_iteration_loop_rejects_contract_invalid_proposal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    config = replace(
        load_project_config(repo),
        strategy_modifier="invalid_contract_test",
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
        stop_after_no_improvement_rounds=0,
    )

    class BadModifier:
        def propose_strategy_change(self, **kwargs) -> StrategyProposal:
            target_file = kwargs["target_file"]
            repo_root = kwargs["repo_root"]
            return StrategyProposal(
                agent_name="bad_contract_agent",
                round_index=kwargs["round_index"],
                target_file=str(target_file.relative_to(repo_root)),
                summary="Return a patch for a disallowed file.",
                risk_notes="The contract validator should reject this before apply.",
                expected_metric_change={"ev": "uncertain"},
                raw_response="bad contract response",
                patch_diff=(
                    "--- a/backtester/simulate.py\n"
                    "+++ b/backtester/simulate.py\n"
                    "@@ -1 +1 @@\n"
                    "-old\n"
                    "+new\n"
                ),
                applicable=True,
                direction_tag="bad_direction",
                hypotheses=("Only strategy patches are allowed.",),
            )

    monkeypatch.setattr(
        "orchestrator.iteration_loop.get_strategy_modifier",
        lambda _name, _settings: BadModifier(),
    )

    manifest = run_iteration_loop(
        run_id="contract-invalid",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    round_dir = repo / "experiments/contract-invalid/round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    attempts = json.loads(
        (round_dir / "proposal_attempts.json").read_text(encoding="utf-8")
    )
    decision = json.loads((round_dir / "decision.json").read_text(encoding="utf-8"))

    assert manifest["rounds"][0]["proposal_contract_valid"] is False  # type: ignore[index]
    assert proposal["applicable"] is False
    assert proposal["contract_errors"]
    assert attempts[0]["status"] == "contract_invalid"
    assert attempts[0]["contract_errors"] == proposal["contract_errors"]
    assert decision["reasons"][0].startswith("proposal contract invalid")
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )


def test_iteration_loop_rejects_failed_direction_from_memory(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config = replace(
        load_project_config(repo),
        memory_failed_patch_threshold=0,
        memory_failed_direction_threshold=3,
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
        stop_after_no_improvement_rounds=0,
    )
    for index in range(3):
        append_outcome_memory(
            experiments_dir=repo / "experiments",
            record={
                "kind": "proposal_outcome",
                "run_id": f"direction-source-{index}",
                "round_id": "round_001",
                "agent_name": "external_test_agent",
                "direction_tag": "lower_min_edge",
                "accepted": False,
                "patch_sha256": f"different-patch-{index}",
            },
        )

    manifest = run_iteration_loop(
        run_id="direction-filtered",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    round_dir = repo / "experiments/direction-filtered/round_001"
    decision = json.loads((round_dir / "decision.json").read_text(encoding="utf-8"))
    attempts = json.loads(
        (round_dir / "proposal_attempts.json").read_text(encoding="utf-8")
    )

    assert manifest["rounds"][0]["proposal_direction_memory_rejected"] is True  # type: ignore[index]
    assert attempts[0]["direction_memory_filter_rejected"] is True
    assert attempts[0]["patch_memory_filter_rejected"] is False
    assert attempts[0]["status"] == "memory_rejected"
    assert decision["reasons"][0].startswith(
        "memory filter rejected direction lower_min_edge"
    )
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )


def test_iteration_loop_initializes_git_when_missing(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    assert not (repo / ".git").exists()

    run_iteration_loop(run_id="git-init", max_rounds=1, repo_root=repo)

    assert (repo / ".git").exists()


def test_run_pipeline_accepts_config_path_and_run_id(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    summary = run_pipeline(
        run_id="single-cli-style",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )

    assert summary["run_id"] == "single-cli-style"
    assert (repo / "experiments/single-cli-style/decision.json").exists()
    assert (repo / "experiments/single-cli-style/summary.md").exists()


def test_iteration_loop_accepts_dry_run_config_path(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)

    manifest = run_iteration_loop(
        run_id="dry-config",
        repo_root=repo,
        config_path=repo / "config/codex_dry_run.json",
    )

    proposal = json.loads(
        (
            repo / "experiments/dry-config/round_001/proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["completed_rounds"] == 1
    assert proposal["agent_name"] == "codex_cli_dry_run"


def test_adaptive_stub_changes_patch_direction_after_context_failure(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)

    manifest = run_iteration_loop(
        run_id="adaptive-history",
        repo_root=repo,
        config_path=repo / "config/adaptive_stub.json",
    )

    run_dir = repo / "experiments/adaptive-history"
    proposal_1 = json.loads(
        (run_dir / "round_001/proposal.json").read_text(encoding="utf-8")
    )
    proposal_2 = json.loads(
        (run_dir / "round_002/proposal.json").read_text(encoding="utf-8")
    )
    context_2 = (run_dir / "round_002/agent_context.md").read_text(encoding="utf-8")
    summary_text = (run_dir / "summary.md").read_text(encoding="utf-8")

    assert manifest["status"] == "stopped_max_rounds"
    assert manifest["completed_rounds"] == 2
    assert proposal_1["agent_name"] == "strategy_modifier_adaptive_stub"
    assert proposal_2["agent_name"] == "strategy_modifier_adaptive_stub"
    assert "MIN_EDGE = 0.04" in proposal_1["patch_diff"]
    assert "STAKE = 8.0" in proposal_2["patch_diff"]
    assert proposal_1["patch_sha256"] != proposal_2["patch_sha256"]
    assert proposal_2["is_repeat_patch"] is False
    assert "round_001" in context_2
    assert proposal_1["patch_sha256"][:12] in context_2
    assert "Replace `STAKE = 10.0` with `STAKE = 8.0`" in summary_text
    memory = read_outcome_memory(repo / "experiments")
    assert len(memory) == 2
    assert memory[0]["run_id"] == "adaptive-history"
    assert memory[0]["round_id"] == "round_001"
    assert memory[0]["patch_sha256"] == proposal_1["patch_sha256"]
    assert memory[1]["round_id"] == "round_002"
    assert memory[1]["validation_ev_delta"] == 0.0
    strategy_text = (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )
    assert OLD_THRESHOLD in strategy_text
    assert "STAKE = 10.0" in strategy_text


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
        holdout_policy=default.holdout_policy,
        strategy_path=default.strategy_path,
        strategy_modifier="codex_dry_run",
        modifier_settings={
            "executable": "codex",
            "model": "dry-run-model",
            "sandbox": "workspace-write",
        },
        stub_old_threshold=default.stub_old_threshold,
        stub_new_threshold=default.stub_new_threshold,
        stop_on_repeated_proposal=default.stop_on_repeated_proposal,
        memory_failed_patch_threshold=default.memory_failed_patch_threshold,
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
    assert proposal["hypotheses"]
    assert proposal["quality_checks"]["has_patch"] is False
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
    assert "Return either a unified diff patch or a JSON object" in proposal["prompt"]
    assert "Prior proposal context:" in proposal["prompt"]
    assert "agent_context.json" in proposal["prompt"]
    assert "No prior rounds in this run." in proposal["prompt"]
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
        holdout_policy=default.holdout_policy,
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
        stop_on_repeated_proposal=default.stop_on_repeated_proposal,
        memory_failed_patch_threshold=default.memory_failed_patch_threshold,
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


def test_iteration_loop_codex_cli_executes_structured_json_fixture(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    fake_codex = write_fake_command(
        tmp_path,
        "fake_codex_structured.py",
        """#!/usr/bin/env python3
import difflib
import json
import pathlib
import sys
prompt = sys.stdin.read()
target = pathlib.Path('strategies/current_strategy.py')
before = target.read_text(encoding='utf-8')
after = before.replace('MIN_EDGE = 0.05', 'MIN_EDGE = 0.04', 1)
patch = ''.join(difflib.unified_diff(
    before.splitlines(keepends=True),
    after.splitlines(keepends=True),
    fromfile='a/strategies/current_strategy.py',
    tofile='b/strategies/current_strategy.py',
))
print(json.dumps({
    "summary": "Lower MIN_EDGE through structured JSON.",
    "risk_notes": "May increase trade count and slippage.",
    "direction_tag": "lower_min_edge",
    "expected_metric_change": {
        "trade_count": "increase",
        "ev": "uncertain"
    },
    "hypotheses": [
        "Structured proposal metadata should survive subprocess parsing."
    ],
    "patch_diff": patch
}))
""",
    )
    default = load_project_config(repo)
    config = replace(
        default,
        strategy_modifier="codex_cli",
        modifier_settings={
            "executable": str(fake_codex),
            "model": "structured-test",
            "sandbox": "workspace-write",
            "workspace_root": "workspaces",
            "execute": True,
            "timeout_seconds": 5,
        },
        memory_failed_patch_threshold=0,
        memory_failed_direction_threshold=99,
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
        stop_after_no_improvement_rounds=0,
    )

    manifest = run_iteration_loop(
        run_id="codex-structured-fixture",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    round_dir = repo / "experiments/codex-structured-fixture/round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    attempts = json.loads(
        (round_dir / "proposal_attempts.json").read_text(encoding="utf-8")
    )
    assert manifest["completed_rounds"] == 1
    assert proposal["agent_name"] == "codex_cli"
    assert proposal["summary"] == "Lower MIN_EDGE through structured JSON."
    assert proposal["direction_tag"] == "lower_min_edge"
    assert proposal["expected_metric_change"]["trade_count"] == "increase"
    assert proposal["hypotheses"] == [
        "Structured proposal metadata should survive subprocess parsing."
    ]
    assert "MIN_EDGE = 0.04" in proposal["patch_diff"]
    assert proposal["contract_errors"] == []
    assert attempts[0]["status"] == "selectable"
    assert attempts[0]["selected"] is True
    assert "agent_context.json" in proposal["prompt"]
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )


def test_iteration_loop_rejects_codex_cli_workspace_mutation(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    fake_codex = write_fake_command(
        tmp_path,
        "fake_codex_mutates_workspace.py",
        """#!/usr/bin/env python3
import difflib
import json
import pathlib
import sys
sys.stdin.read()
pathlib.Path('README.md').write_text('unexpected mutation\\n', encoding='utf-8')
target = pathlib.Path('strategies/current_strategy.py')
before = target.read_text(encoding='utf-8')
after = before.replace('MIN_EDGE = 0.05', 'MIN_EDGE = 0.04', 1)
patch = ''.join(difflib.unified_diff(
    before.splitlines(keepends=True),
    after.splitlines(keepends=True),
    fromfile='a/strategies/current_strategy.py',
    tofile='b/strategies/current_strategy.py',
))
print(json.dumps({
    "summary": "Return a clean strategy patch after mutating README.",
    "risk_notes": "Mutation guard should reject this.",
    "direction_tag": "lower_min_edge",
    "expected_metric_change": {"trade_count": "increase"},
    "hypotheses": ["Workspace mutation guard should catch side effects."],
    "patch_diff": patch
}))
""",
    )
    default = load_project_config(repo)
    config = replace(
        default,
        strategy_modifier="codex_cli",
        modifier_settings={
            "executable": str(fake_codex),
            "model": "mutation-test",
            "sandbox": "workspace-write",
            "workspace_root": "workspaces",
            "execute": True,
            "timeout_seconds": 5,
        },
        memory_failed_patch_threshold=0,
        memory_failed_direction_threshold=99,
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
        stop_after_no_improvement_rounds=0,
    )

    run_iteration_loop(
        run_id="codex-mutation-guard",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    round_dir = repo / "experiments/codex-mutation-guard/round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    attempts = json.loads(
        (round_dir / "proposal_attempts.json").read_text(encoding="utf-8")
    )
    decision = json.loads((round_dir / "decision.json").read_text(encoding="utf-8"))

    assert proposal["applicable"] is False
    assert proposal["contract_errors"] == [
        "workspace modified disallowed file: README.md"
    ]
    assert proposal["rejection_reason"].startswith("proposal contract invalid")
    assert attempts[0]["status"] == "contract_invalid"
    assert decision["reasons"][0].startswith("proposal contract invalid")
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )


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
        context_text="# Agent Context\n- prior failure\n",
    )
    command = build_codex_command(
        executable="codex",
        model="gpt-test",
        sandbox="workspace-write",
        target_file="strategies/current_strategy.py",
    )

    assert "Round: 3" in prompt
    assert "Only modify: strategies/current_strategy.py" in prompt
    assert "prior failure" in prompt
    assert "JSON object" in prompt
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


def test_agent_context_summarizes_prior_failed_rounds(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    no_fallback = replace(
        load_project_config(repo),
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
    )
    run_iteration_loop(
        run_id="context-history",
        max_rounds=2,
        repo_root=repo,
        config=no_fallback,
        stop_on_repeated_proposal=False,
    )

    context_text = build_agent_context(
        run_dir=repo / "experiments/context-history",
        current_round_id="round_003",
    )
    context_payload = build_agent_context_payload(
        run_dir=repo / "experiments/context-history",
        current_round_id="round_003",
    )

    assert "round_001" in context_text
    assert "round_002" in context_text
    assert "Failed Patch Hashes" in context_text
    assert "Candidate Search Trace" in context_text
    assert "strategy_modifier_stub" in context_text
    assert "Probe EV Delta" in context_text
    assert "ev improvement" in context_text
    assert "yes (round_001)" in context_text
    assert context_payload["schema_version"] == "agent_context_v1"
    assert len(context_payload["prior_rounds"]) == 2
    assert context_payload["failed_patch_hashes"]
    assert context_payload["candidate_search_trace"]


def test_agent_context_includes_global_outcome_memory(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_iteration_loop(
        run_id="memory-source",
        max_rounds=1,
        repo_root=repo,
    )
    run_iteration_loop(
        run_id="memory-reader",
        max_rounds=1,
        repo_root=repo,
        config_path=repo / "config/codex_dry_run.json",
    )

    context_text = (
        repo / "experiments/memory-reader/round_001/agent_context.md"
    ).read_text(encoding="utf-8")
    context_payload = json.loads(
        (
            repo / "experiments/memory-reader/round_001/agent_context.json"
        ).read_text(encoding="utf-8")
    )

    assert "Global Outcome Memory" in context_text
    assert "memory-source" in context_text
    assert "strategy_modifier_stub" in context_text
    assert "ev improvement" in context_text
    assert context_payload["global_outcome_memory"][0]["run_id"] == "memory-source"


def test_iteration_loop_cli_arguments_work(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.iteration_loop",
            "--config",
            "config/codex_dry_run.json",
            "--run-id",
            "cli-dry",
            "--max-rounds",
            "1",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Run id: cli-dry" in result.stdout
    assert (repo / "experiments/cli-dry/manifest.json").exists()


def test_run_loop_cli_arguments_work(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.run_loop",
            "--config",
            "config/default.json",
            "--run-id",
            "cli-single",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Run directory:" in result.stdout
    assert (repo / "experiments/cli-single/decision.json").exists()


def test_experiment_list_and_show_helpers(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_pipeline(
        run_id="single-show",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )
    run_iteration_loop(
        run_id="iteration-show",
        max_rounds=1,
        repo_root=repo,
        config_path=repo / "config/codex_dry_run.json",
    )

    records = list_experiments(experiments_dir=repo / "experiments", limit=2)
    single = show_experiment(run_id="single-show", experiments_dir=repo / "experiments")
    iteration = show_experiment(
        run_id="iteration-show",
        experiments_dir=repo / "experiments",
    )

    assert [record["run_id"] for record in records] == ["single-show", "iteration-show"]
    assert single["kind"] == "single_run"
    assert single["summary_path"].endswith("experiments/single-show/summary.md")
    assert single["decision"]["accepted"] is False  # type: ignore[index]
    assert iteration["kind"] == "iteration_loop"
    assert iteration["summary_path"].endswith("experiments/iteration-show/summary.md")
    assert iteration["manifest"]["completed_rounds"] == 1  # type: ignore[index]


def test_experiment_summary_and_leaderboard_helpers(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_pipeline(
        run_id="single-rank",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )
    run_iteration_loop(
        run_id="iteration-rank",
        max_rounds=1,
        repo_root=repo,
        config_path=repo / "config/default.json",
    )

    summary = summarize_experiments(experiments_dir=repo / "experiments")
    leaderboard = experiment_leaderboard(experiments_dir=repo / "experiments", limit=2)

    assert summary["total_runs"] == 2
    assert summary["by_kind"] == {"single_run": 1, "iteration_loop": 1}
    assert len(leaderboard) == 2
    assert all("ev_delta" in row for row in leaderboard)


def test_experiments_cli_list_and_show_work(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_pipeline(
        run_id="cli-list-show",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )

    list_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.experiments",
            "--experiments-dir",
            "experiments",
            "list",
            "--limit",
            "1",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    show_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.experiments",
            "--experiments-dir",
            "experiments",
            "show",
            "cli-list-show",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert list_result.returncode == 0, list_result.stderr
    assert show_result.returncode == 0, show_result.stderr
    assert json.loads(list_result.stdout)[0]["run_id"] == "cli-list-show"
    assert json.loads(show_result.stdout)["kind"] == "single_run"


def test_experiments_cli_summary_and_leaderboard_work(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_pipeline(
        run_id="cli-summary",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )

    summary_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.experiments",
            "--experiments-dir",
            "experiments",
            "summary",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    leaderboard_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.experiments",
            "--experiments-dir",
            "experiments",
            "leaderboard",
            "--limit",
            "1",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert summary_result.returncode == 0, summary_result.stderr
    assert leaderboard_result.returncode == 0, leaderboard_result.stderr
    assert json.loads(summary_result.stdout)["total_runs"] == 1
    assert json.loads(leaderboard_result.stdout)[0]["run_id"] == "cli-summary"


def test_experiments_cli_memory_work(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_iteration_loop(
        run_id="cli-memory",
        max_rounds=1,
        repo_root=repo,
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.experiments",
            "--experiments-dir",
            "experiments",
            "memory",
            "--limit",
            "1",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload[0]["run_id"] == "cli-memory"
    assert payload[0]["kind"] == "proposal_outcome"


def test_experiments_candidate_leaderboard_helpers_and_cli_work(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_iteration_loop(
        run_id="cli-candidates",
        max_rounds=1,
        repo_root=repo,
    )

    rows = candidate_leaderboard(
        run_id="cli-candidates",
        experiments_dir=repo / "experiments",
        limit=2,
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.experiments",
            "--experiments-dir",
            "experiments",
            "candidates",
            "cli-candidates",
            "--limit",
            "1",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert rows
    assert rows[0]["run_id"] == "cli-candidates"
    assert rows[0]["selected"] is True
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["run_id"] == "cli-candidates"
    assert "probe_ev_delta" in payload[0]


def test_summary_markdown_is_written_for_single_and_iteration_runs(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_pipeline(
        run_id="summary-single",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )
    run_iteration_loop(
        run_id="summary-iteration",
        max_rounds=1,
        repo_root=repo,
        config_path=repo / "config/default.json",
    )

    single_summary = (
        repo / "experiments/summary-single/summary.md"
    ).read_text(encoding="utf-8")
    iteration_summary = (
        repo / "experiments/summary-iteration/summary.md"
    ).read_text(encoding="utf-8")

    assert "| Metric | Before | After | Delta |" in single_summary
    assert "- Kind: `single_run`" in single_summary
    assert "| Round | Accepted | Proposal |" in iteration_summary
    assert "Best Validation Delta" in iteration_summary
    assert "Proposal Quality" in iteration_summary
    assert "Candidate Leaderboard" in iteration_summary
    assert "Expected Change" in iteration_summary
    assert "Probe EV" in iteration_summary
    assert "strategy_modifier_stub" in iteration_summary


def test_preflight_cli_arguments_work(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.preflight",
            "--config",
            "config/default.json",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True


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


def test_workspace_snapshot_mutation_guard_allows_only_strategy_file(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "strategies").mkdir(parents=True)
    (workspace / "backtester").mkdir()
    strategy = workspace / "strategies/current_strategy.py"
    strategy.write_text("MIN_EDGE = 0.05\n", encoding="utf-8")
    readme = workspace / "README.md"
    readme.write_text("baseline\n", encoding="utf-8")
    deleted = workspace / "backtester/deleted.py"
    deleted.write_text("x = 1\n", encoding="utf-8")

    before = workspace_snapshot(workspace)

    strategy.write_text("MIN_EDGE = 0.04\n", encoding="utf-8")
    readme.write_text("unexpected\n", encoding="utf-8")
    deleted.unlink()
    (workspace / "notes.txt").write_text("side effect\n", encoding="utf-8")
    (workspace / "__pycache__").mkdir()
    (workspace / "__pycache__/ignored.pyc").write_bytes(b"ignored")

    assert workspace_mutation_errors(
        before=before,
        after=workspace_snapshot(workspace),
        allowed_paths={"strategies/current_strategy.py"},
    ) == (
        "workspace modified disallowed file: README.md",
        "workspace deleted disallowed file: backtester/deleted.py",
        "workspace added disallowed file: notes.txt",
    )


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


def test_patch_parser_extracts_fenced_json_object() -> None:
    raw_output = """
Use this structured proposal:

```json
{
  "summary": "Lower threshold.",
  "direction_tag": "lower_min_edge"
}
```
"""

    payload = extract_json_object(raw_output)

    assert payload["summary"] == "Lower threshold."
    assert payload["direction_tag"] == "lower_min_edge"


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


def test_codex_structured_json_output_is_converted_to_proposal(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    report_path = repo / "experiments/run-json/round_001/train_report_before.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# Report\n", encoding="utf-8")
    workspace = repo / "workspaces/run-json/round_001/strategy_workspace"
    raw_output = """```json
{
  "summary": "Lower MIN_EDGE to test more trades.",
  "risk_notes": "May increase trade count and slippage.",
  "direction_tag": "lower_min_edge",
  "expected_metric_change": {
    "trade_count": "increase",
    "ev": "uncertain"
  },
  "hypotheses": [
    "More candidate trades may improve opportunity capture."
  ],
  "patch_diff": "--- a/strategies/current_strategy.py\\n+++ b/strategies/current_strategy.py\\n@@ -9,7 +9,7 @@\\n-MIN_EDGE = 0.05\\n+MIN_EDGE = 0.04\\n"
}
```"""

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
    assert proposal.summary == "Lower MIN_EDGE to test more trades."
    assert proposal.direction_tag == "lower_min_edge"
    assert proposal.expected_metric_change["trade_count"] == "increase"
    assert proposal.hypotheses == (
        "More candidate trades may improve opportunity capture.",
    )
    assert "MIN_EDGE = 0.04" in proposal.patch_diff


def write_fake_command(tmp_path: Path, filename: str, content: str) -> Path:
    """Write an executable fake command for subprocess adapter tests."""
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def build_test_replacement_proposal(
    *,
    target_file: Path,
    repo_root: Path,
    round_index: int,
    old_text: str,
    new_text: str,
    agent_name: str,
    direction_tag: str,
    expected_metric_change: dict[str, str],
    risk_notes: str,
) -> StrategyProposal:
    """Build a test proposal that replaces one exact text snippet."""
    target_text = target_file.read_text(encoding="utf-8")
    target_relative = target_file.relative_to(repo_root)
    updated_text = target_text.replace(old_text, new_text, 1)
    patch_diff = "".join(
        difflib.unified_diff(
            target_text.splitlines(keepends=True),
            updated_text.splitlines(keepends=True),
            fromfile=f"a/{target_relative}",
            tofile=f"b/{target_relative}",
        )
    )
    return StrategyProposal(
        agent_name=agent_name,
        round_index=round_index,
        target_file=str(target_relative),
        summary=f"Replace `{old_text}` with `{new_text}`.",
        risk_notes=risk_notes,
        expected_metric_change=expected_metric_change,
        raw_response=f"{agent_name} response",
        patch_diff=patch_diff,
        applicable=True,
        direction_tag=direction_tag,
        hypotheses=("Exercise deterministic candidate selection.",),
    )


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
