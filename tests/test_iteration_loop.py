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
from agents.file_protocol_adapter import AGENT_EXECUTION_SCHEMA_VERSION
from agents.strategy_modifier_stub import NEW_THRESHOLD, OLD_THRESHOLD, propose_strategy_change
from backtester.schema import MarketSnapshot, StrategyOrder
from backtester.simulate import validate_strategy_orders
from orchestrator.agent_context import build_agent_context, build_agent_context_payload
from orchestrator.agent_executor import build_agent_queue, execute_agent_queue
from orchestrator.agent_io import (
    AGENT_INPUT_SCHEMA_VERSION,
    AGENT_OUTPUT_SCHEMA_VERSION,
)
from orchestrator.agent_roles import AGENT_ROLE_CONTRACTS_SCHEMA_VERSION
from orchestrator.agent_contract_runner import (
    AGENT_CONTRACT_RUNNER_NAME,
    run_agent_contract,
)
from orchestrator.agent_output_intake import (
    AGENT_VALIDATION_SCHEMA_VERSION,
    verify_agent_output,
)
from orchestrator.agent_replay import replay_agent_input, validate_replayed_proposal
from orchestrator.attempt_replay import replay_attempt
from orchestrator.artifact_validator import validate_run_artifacts
from orchestrator.config import (
    ProjectConfig,
    load_project_config,
    normalize_runner_capability,
)
from orchestrator.git_manager import apply_patch, ensure_git_repo, rollback_strategy
from orchestrator.iteration_loop import run_iteration_loop
from orchestrator.outcome_memory import (
    append_outcome_memory,
    direction_filter_rejection_reason,
    direction_prior,
    read_outcome_memory,
)
from orchestrator.run_loop import run_pipeline
from orchestrator.run_diagnosis import diagnose_run
from orchestrator.preflight import run_preflight
from orchestrator.schema_validation import validate_json_file, validate_json_payload
from orchestrator.experiments import (
    agent_result_stats,
    candidate_leaderboard,
    compare_experiments,
    experiment_leaderboard,
    list_experiments,
    promote_champion,
    show_experiment,
    show_champion,
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
    WORKSPACE_MANIFEST_SCHEMA_VERSION,
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
        "schemas",
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


def assert_matches_schema(payload_path: Path, schema_name: str) -> None:
    """Assert a JSON artifact matches one repository contract schema."""
    schema_path = Path.cwd() / "schemas" / f"{schema_name}.schema.json"
    assert validate_json_file(payload_path=payload_path, schema_path=schema_path) == ()


def test_agent_contract_runner_writes_disabled_audit(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    round_dir = tmp_path / "round"
    workspace.mkdir()
    round_dir.mkdir()
    agent_input = workspace / "agent_input.json"
    agent_input.write_text("{}", encoding="utf-8")
    workspace_output = workspace / "agent_output.json"
    round_output = round_dir / "agent_output.json"
    audit_path = round_dir / "agent_execution.json"

    result = run_agent_contract(
        output_path=audit_path,
        agent_name="demo_agent",
        profile_name="primary",
        adapter_name="file_protocol",
        command=["not-run"],
        cwd=workspace,
        workspace_path=workspace,
        agent_input_path=agent_input,
        workspace_output_path=workspace_output,
        round_output_path=round_output,
        timeout_seconds=5,
        execute=False,
        allowed_mutation_paths=("agent_output.json",),
        disabled_response="disabled by test",
    )

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert result.status == "disabled"
    assert result.raw_response == "disabled by test"
    assert audit["schema_version"] == AGENT_EXECUTION_SCHEMA_VERSION
    assert audit["runner_name"] == AGENT_CONTRACT_RUNNER_NAME
    assert audit["agent_name"] == "demo_agent"
    assert audit["status"] == "disabled"
    assert audit["execution_enabled"] is False
    assert audit["round_output_file"]["exists"] is False
    assert_matches_schema(audit_path, "agent_execution")


def test_agent_contract_runner_copies_allowed_output(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    round_dir = tmp_path / "round"
    workspace.mkdir()
    round_dir.mkdir()
    agent_input = workspace / "agent_input.json"
    agent_input.write_text("{}", encoding="utf-8")
    workspace_output = workspace / "agent_output.json"
    round_output = round_dir / "agent_output.json"
    audit_path = round_dir / "agent_execution.json"
    script = (
        "import pathlib, sys; "
        "pathlib.Path(sys.argv[1]).write_text('{\"ok\": true}\\n', encoding='utf-8')"
    )

    result = run_agent_contract(
        output_path=audit_path,
        agent_name="demo_agent",
        profile_name="primary",
        adapter_name="file_protocol",
        command=[sys.executable, "-c", script, str(workspace_output)],
        cwd=workspace,
        workspace_path=workspace,
        agent_input_path=agent_input,
        workspace_output_path=workspace_output,
        round_output_path=round_output,
        timeout_seconds=5,
        execute=True,
        allowed_mutation_paths=("agent_output.json",),
    )

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert result.status == "completed"
    assert result.mutation_errors == ()
    assert round_output.read_text(encoding="utf-8") == '{"ok": true}\n'
    assert audit["runner_name"] == AGENT_CONTRACT_RUNNER_NAME
    assert audit["status"] == "completed"
    assert audit["output_file"]["exists"] is True
    assert audit["round_output_file"]["exists"] is True
    assert audit["mutation_guard"]["passed"] is True
    assert_matches_schema(audit_path, "agent_execution")


def test_agent_contract_runner_rejects_workspace_side_effect(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    round_dir = tmp_path / "round"
    workspace.mkdir()
    round_dir.mkdir()
    agent_input = workspace / "agent_input.json"
    agent_input.write_text("{}", encoding="utf-8")
    workspace_output = workspace / "agent_output.json"
    round_output = round_dir / "agent_output.json"
    audit_path = round_dir / "agent_execution.json"
    protected_file = workspace / "protected.txt"
    script = (
        "import pathlib, sys; "
        "pathlib.Path(sys.argv[1]).write_text('{\"ok\": true}\\n', encoding='utf-8'); "
        "pathlib.Path(sys.argv[2]).write_text('side effect\\n', encoding='utf-8')"
    )

    result = run_agent_contract(
        output_path=audit_path,
        agent_name="demo_agent",
        profile_name="primary",
        adapter_name="file_protocol",
        command=[
            sys.executable,
            "-c",
            script,
            str(workspace_output),
            str(protected_file),
        ],
        cwd=workspace,
        workspace_path=workspace,
        agent_input_path=agent_input,
        workspace_output_path=workspace_output,
        round_output_path=round_output,
        timeout_seconds=5,
        execute=True,
        allowed_mutation_paths=("agent_output.json",),
    )

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert result.status == "workspace_violation"
    assert result.mutation_errors
    assert audit["status"] == "workspace_violation"
    assert audit["mutation_guard"]["passed"] is False
    assert any("protected.txt" in error for error in audit["mutation_errors"])
    assert_matches_schema(audit_path, "agent_execution")


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
    assert config.candidate_selection["base_selectable_score"] == 100
    assert config.candidate_selection["direction_prior_weight"] == 1.0
    assert config.candidate_selection["routing_prior_weight"] == 1.0
    assert config.candidate_selection["routing_prefer_bonus"] == 8
    assert config.candidate_selection["routing_downweight_penalty"] == 12
    assert config.candidate_selection["champion_gap_weight"] == 1.0
    assert config.candidate_selection["probe_ev_cap"] == 25
    assert config.candidate_selection["champion_gap_cap"] == 15
    assert config.executor["mode"] == "sequential"
    assert config.executor["max_candidates"] == 0
    assert config.executor["per_agent_timeout_seconds"] == 120
    assert config.executor["allow_disabled_adapters"] is True
    assert config.agent_profiles == ()
    assert [role["role_name"] for role in config.agent_roles] == [
        "strategy_modifier",
        "analysis",
        "visual_review",
        "overfit_validator",
    ]
    assert config.agent_roles[0]["execution_mode"] == "active"
    assert config.agent_roles[0]["implemented"] is True
    assert config.agent_roles[1]["execution_mode"] == "stub_contract"
    assert config.agent_roles[1]["implemented"] is False
    assert config.stop_on_repeated_proposal is True


def test_agent_executor_builds_stable_attempt_queue(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    report_path = repo / "report.md"
    context_path = repo / "context.md"
    report_path.write_text("report\n", encoding="utf-8")
    context_path.write_text("context\n", encoding="utf-8")

    class RecordingModifier:
        def __init__(self, agent_name: str) -> None:
            self.agent_name = agent_name
            self.calls: list[str] = []

        def propose_strategy_change(self, **kwargs) -> StrategyProposal:
            self.calls.append(str(kwargs["attempt_id"]))
            return StrategyProposal(
                agent_name=self.agent_name,
                round_index=int(kwargs["round_index"]),
                target_file=str(kwargs["target_file"].relative_to(kwargs["repo_root"])),
                summary=f"{self.agent_name} proposal",
                risk_notes="No real patch; executor test only.",
                expected_metric_change={},
                raw_response=f"response for {kwargs['attempt_id']}",
                patch_diff="",
                applicable=False,
                direction_tag="executor_test",
                hypotheses=("Executor should pass stable attempt ids.",),
                rejection_reason="executor test proposal is non-applicable",
            )

    primary = RecordingModifier("primary_agent")
    fallback = RecordingModifier("fallback_agent")

    queue = build_agent_queue(
        primary_modifier=primary,
        fallback_modifiers=(fallback,),
    )
    results = execute_agent_queue(
        queue=queue,
        report_path=report_path,
        target_file=repo / "strategies/current_strategy.py",
        round_index=1,
        repo_root=repo,
        old_threshold=OLD_THRESHOLD,
        new_threshold=NEW_THRESHOLD,
        context_path=context_path,
    )

    assert [candidate.role for candidate in queue] == ["primary", "fallback_01"]
    assert [candidate.attempt_id for candidate in queue] == [
        "attempt_001_primary",
        "attempt_002_fallback_01",
    ]
    assert [candidate.profile_name for candidate in queue] == [
        "primary",
        "fallback_01",
    ]
    assert [candidate.agent_role for candidate in queue] == [
        "strategy_modifier",
        "strategy_modifier",
    ]
    assert [candidate.adapter_name for candidate in queue] == [
        "primary_agent",
        "fallback_agent",
    ]
    assert [result.proposal.agent_name for result in results] == [
        "primary_agent",
        "fallback_agent",
    ]
    assert primary.calls == ["attempt_001_primary"]
    assert fallback.calls == ["attempt_002_fallback_01"]

    profiled_queue = build_agent_queue(
        primary_modifier=primary,
        fallback_modifiers=(fallback,),
        primary_profile={
            "name": "strategy_bot",
            "adapter": "fixed_patch_stub",
            "role": "primary",
            "agent_role": "strategy_modifier",
            "enabled": True,
            "settings": {},
        },
        fallback_profiles=(
            {
                "name": "risk_bot",
                "adapter": "adaptive_stub",
                "role": "fallback",
                "agent_role": "strategy_modifier",
                "enabled": True,
                "settings": {},
            },
        ),
    )
    assert [candidate.modifier_name for candidate in profiled_queue] == [
        "primary_agent",
        "fallback_agent",
    ]
    assert [candidate.profile_name for candidate in profiled_queue] == [
        "strategy_bot",
        "risk_bot",
    ]
    assert [candidate.adapter_name for candidate in profiled_queue] == [
        "fixed_patch_stub",
        "adaptive_stub",
    ]
    assert [candidate.agent_role for candidate in profiled_queue] == [
        "strategy_modifier",
        "strategy_modifier",
    ]

    capped_queue = build_agent_queue(
        primary_modifier=primary,
        fallback_modifiers=(fallback,),
        executor_config={"max_candidates": 1},
    )
    assert [candidate.attempt_id for candidate in capped_queue] == [
        "attempt_001_primary"
    ]


def test_example_configs_load_modifier_modes() -> None:
    dry_run = load_project_config(Path.cwd(), Path("config/codex_dry_run.json"))
    guarded = load_project_config(Path.cwd(), Path("config/codex_cli_guarded.json"))
    adaptive = load_project_config(Path.cwd(), Path("config/adaptive_stub.json"))
    file_protocol = load_project_config(
        Path.cwd(),
        Path("config/file_protocol_guarded.json"),
    )
    file_protocol_demo = load_project_config(
        Path.cwd(),
        Path("config/file_protocol_demo.json"),
    )

    assert dry_run.strategy_modifier == "codex_cli_dry_run"
    assert guarded.strategy_modifier == "codex_cli"
    assert adaptive.strategy_modifier == "adaptive_stub"
    assert file_protocol.strategy_modifier == "file_protocol"
    assert file_protocol_demo.strategy_modifier == "file_protocol"
    assert adaptive.max_rounds == 2
    assert guarded.modifier_settings["execute"] is False
    assert file_protocol.modifier_settings["execute"] is False
    assert file_protocol_demo.modifier_settings["execute"] is True
    assert file_protocol_demo.modifier_settings["args"] == [
        "-m",
        "agents.file_protocol_demo_agent",
    ]


def test_runner_capability_defaults_match_adapter_boundaries() -> None:
    assert normalize_runner_capability(
        adapter_name="fixed_patch_stub",
        settings={},
    )["runner_name"] == "in_process_modifier"
    assert normalize_runner_capability(
        adapter_name="file_protocol",
        settings={
            "execute": True,
            "timeout_seconds": 30,
            "output_filename": "agent_output.json",
        },
    ) == {
        "runner_name": "agent_contract_runner_v1",
        "isolation": "workspace",
        "execution_enabled": True,
        "timeout_seconds": 30,
        "workspace_root": "workspaces",
        "output_mode": "file_contract",
        "allowed_output_files": ["agent_output.json"],
    }
    assert normalize_runner_capability(
        adapter_name="codex_cli",
        settings={"execute": False, "timeout_seconds": 120},
    )["runner_name"] == "codex_cli_guarded_adapter"
    assert normalize_runner_capability(
        adapter_name="codex_dry_run",
        settings={},
    )["runner_name"] == "workspace_dry_run"


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


def test_preflight_passes_file_protocol_demo_config() -> None:
    result = run_preflight(
        repo_root=Path.cwd(),
        config_path=Path("config/file_protocol_demo.json"),
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


def test_preflight_rejects_enabled_missing_file_protocol_command(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    config_path = repo / "config/missing_file_protocol.json"
    config = json.loads((repo / "config/file_protocol_guarded.json").read_text())
    config["file_protocol"]["execute"] = True
    config["file_protocol"]["executable"] = "definitely-not-a-real-agent-command"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_preflight(repo_root=repo, config_path=config_path)

    assert result.ok is False
    assert any("file_protocol executable not found" in error for error in result.errors)


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


def test_preflight_rejects_negative_candidate_selection_cap(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config_path = repo / "config/negative_candidate_selection.json"
    config = json.loads((repo / "config/default.json").read_text())
    config["candidate_selection"]["probe_ev_cap"] = -1
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_preflight(repo_root=repo, config_path=config_path)

    assert result.ok is False
    assert any("candidate_selection.probe_ev_cap" in error for error in result.errors)


def test_preflight_rejects_negative_routing_prior_penalty(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config_path = repo / "config/negative_routing_prior.json"
    config = json.loads((repo / "config/default.json").read_text())
    config["candidate_selection"]["routing_downweight_penalty"] = -1
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_preflight(repo_root=repo, config_path=config_path)

    assert result.ok is False
    assert any(
        "candidate_selection.routing_downweight_penalty" in error
        for error in result.errors
    )


def test_preflight_rejects_invalid_executor_config(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config_path = repo / "config/bad_executor.json"
    config = json.loads((repo / "config/default.json").read_text())
    config["executor"]["mode"] = "parallel"
    config["executor"]["max_candidates"] = -1
    config["executor"]["per_agent_timeout_seconds"] = 0
    config["executor"]["allow_disabled_adapters"] = "yes"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_preflight(repo_root=repo, config_path=config_path)

    assert result.ok is False
    assert any("executor.mode" in error for error in result.errors)
    assert any("executor.max_candidates" in error for error in result.errors)
    assert any("executor.per_agent_timeout_seconds" in error for error in result.errors)
    assert any("executor.allow_disabled_adapters" in error for error in result.errors)


def test_explicit_agent_profiles_load_and_preflight(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config_path = repo / "config/agent_profiles.json"
    config = json.loads((repo / "config/default.json").read_text())
    config["agents"] = [
        {
            "name": "strategy_bot",
            "adapter": "fixed_patch_stub",
            "role": "primary",
            "agent_role": "strategy_modifier",
            "enabled": True,
            "settings": {},
        },
        {
            "name": "disabled_agent",
            "adapter": "conservative_stub",
            "role": "fallback",
            "agent_role": "analysis",
            "enabled": False,
            "settings": {},
        },
        {
            "name": "risk_agent",
            "adapter": "adaptive_stub",
            "role": "fallback",
            "agent_role": "strategy_modifier",
            "enabled": True,
            "settings": {},
        },
    ]
    config_path.write_text(json.dumps(config), encoding="utf-8")

    loaded = load_project_config(repo, config_path)
    result = run_preflight(repo_root=repo, config_path=config_path)

    assert result.ok is True
    assert [profile["name"] for profile in loaded.agent_profiles] == [
        "strategy_bot",
        "disabled_agent",
        "risk_agent",
    ]
    assert loaded.agent_profiles[0]["adapter"] == "fixed_patch_stub"
    assert loaded.agent_profiles[0]["agent_role"] == "strategy_modifier"
    assert loaded.agent_profiles[0]["runner"]["runner_name"] == "in_process_modifier"
    assert loaded.agent_profiles[0]["runner"]["isolation"] == "none"
    assert loaded.agent_profiles[1]["enabled"] is False
    assert loaded.agent_profiles[1]["agent_role"] == "analysis"
    assert loaded.agent_profiles[2]["role"] == "fallback"


def test_preflight_rejects_invalid_agent_profiles(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config_path = repo / "config/bad_agent_profiles.json"
    config = json.loads((repo / "config/default.json").read_text())
    config["agents"] = [
        {
            "name": "dup",
            "adapter": "fixed_patch_stub",
            "role": "primary",
            "enabled": True,
            "settings": {},
        },
        {
            "name": "dup",
            "adapter": "missing_modifier",
            "role": "fallback",
            "enabled": True,
            "settings": {},
        },
        {
            "name": "review_agent",
            "adapter": "adaptive_stub",
            "role": "reviewer",
            "enabled": True,
            "settings": {},
            "runner": {"runner_name": "missing_runner"},
        },
        {
            "name": "analysis_agent",
            "adapter": "adaptive_stub",
            "role": "fallback",
            "agent_role": "analysis",
            "enabled": True,
            "settings": {},
        },
    ]
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_preflight(repo_root=repo, config_path=config_path)

    assert result.ok is False
    assert any("name must be unique" in error for error in result.errors)
    assert any("adapter is unsupported" in error for error in result.errors)
    assert any("role must be primary or fallback" in error for error in result.errors)
    assert any("agent_role is not active" in error for error in result.errors)
    assert any("runner.runner_name is unsupported" in error for error in result.errors)


def test_preflight_rejects_invalid_agent_roles(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config_path = repo / "config/bad_agent_roles.json"
    config = json.loads((repo / "config/default.json").read_text())
    config["agent_roles"] = [
        {
            "role_name": "strategy_modifier",
            "stage": "proposal_generation",
            "enabled": True,
            "execution_mode": "active",
            "implemented": True,
            "decision_authority": "proposal_only",
        },
        {
            "role_name": "strategy_modifier",
            "stage": "mystery",
            "enabled": True,
            "execution_mode": "active",
            "implemented": False,
            "decision_authority": "natural_language_vote",
        },
    ]
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_preflight(repo_root=repo, config_path=config_path)

    assert result.ok is False
    assert any("role_name must be unique" in error for error in result.errors)
    assert any("stage is unsupported" in error for error in result.errors)
    assert any("decision_authority is unsupported" in error for error in result.errors)
    assert any("active role must be implemented" in error for error in result.errors)


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
        "proposal_intent.json",
        "proposal_intent.md",
        "agent_role_contracts.json",
        "analysis_notes.json",
        "analysis_notes.md",
        "agent_input.json",
        "agent_bundle_manifest.json",
        "agent_output.json",
        "agent_validation.json",
        "agent_executor_report.json",
        "agent_routing_policy.json",
        "agent_attempts_manifest.json",
        "agent_selection_report.json",
        "proposal_attempts.json",
        "proposal.json",
        "raw_agent_output.txt",
        "agent_response.txt",
        "patch.diff",
        "metrics_after.json",
        "report_after.md",
        "trades_after.csv",
        "decision.json",
        "overfit_validation.json",
        "overfit_validation.md",
    ):
        assert (round_dir / filename).exists()
    assert (run_dir / "candidate_leaderboard.json").exists()
    assert (run_dir / "agent_result_stats.json").exists()
    assert (run_dir / "research_brief.json").exists()
    assert (run_dir / "research_brief.md").exists()

    decision = json.loads((round_dir / "decision.json").read_text(encoding="utf-8"))
    overfit_validation = json.loads(
        (round_dir / "overfit_validation.json").read_text(encoding="utf-8")
    )
    brief = json.loads((run_dir / "research_brief.json").read_text(encoding="utf-8"))
    intent = json.loads((round_dir / "proposal_intent.json").read_text(encoding="utf-8"))
    role_contracts = json.loads(
        (round_dir / "agent_role_contracts.json").read_text(encoding="utf-8")
    )
    analysis_notes = json.loads(
        (round_dir / "analysis_notes.json").read_text(encoding="utf-8")
    )
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    agent_input = json.loads((round_dir / "agent_input.json").read_text(encoding="utf-8"))
    agent_bundle = json.loads(
        (round_dir / "agent_bundle_manifest.json").read_text(encoding="utf-8")
    )
    agent_attempts = json.loads(
        (round_dir / "agent_attempts_manifest.json").read_text(encoding="utf-8")
    )
    agent_selection = json.loads(
        (round_dir / "agent_selection_report.json").read_text(encoding="utf-8")
    )
    agent_output = json.loads(
        (round_dir / "agent_output.json").read_text(encoding="utf-8")
    )
    agent_validation = json.loads(
        (round_dir / "agent_validation.json").read_text(encoding="utf-8")
    )
    agent_executor = json.loads(
        (round_dir / "agent_executor_report.json").read_text(encoding="utf-8")
    )
    agent_routing = json.loads(
        (round_dir / "agent_routing_policy.json").read_text(encoding="utf-8")
    )
    attempts = json.loads(
        (round_dir / "proposal_attempts.json").read_text(encoding="utf-8")
    )
    leaderboard = json.loads(
        (run_dir / "candidate_leaderboard.json").read_text(encoding="utf-8")
    )
    agent_stats = json.loads(
        (run_dir / "agent_result_stats.json").read_text(encoding="utf-8")
    )
    selected_attempt = next(attempt for attempt in attempts if attempt["selected"])
    assert manifest["agent_profiles"][0]["name"] == "primary"
    assert manifest["agent_profiles"][0]["adapter"] == "fixed_patch_stub"
    assert manifest["agent_profiles"][0]["runner"]["runner_name"] == "in_process_modifier"
    assert [role["role_name"] for role in manifest["agent_roles"]] == [
        "strategy_modifier",
        "analysis",
        "visual_review",
        "overfit_validator",
    ]
    assert selected_attempt["profile_name"] == "primary"
    assert selected_attempt["adapter_name"] == "fixed_patch_stub"
    assert selected_attempt["agent_role"] == "strategy_modifier"
    assert selected_attempt["runner_name"] == "in_process_modifier"
    assert decision["accepted"] is False
    assert decision["failure_stage"] == "policy_gate"
    assert decision["failure_code"] == "policy_ev_improvement_low"
    assert decision["reason_codes"][0]["code"] == "policy_ev_improvement_low"
    assert overfit_validation["schema_version"] == "overfit_validation_v1"
    assert_matches_schema(round_dir / "overfit_validation.json", "overfit_validation")
    assert overfit_validation["agent_role"] == "overfit_validator"
    assert overfit_validation["execution_mode"] == "stub_contract"
    assert overfit_validation["implemented"] is False
    assert overfit_validation["recommendation"]["action"] == "keep_existing_decision"
    assert overfit_validation["recommendation"]["can_veto"] is False
    assert overfit_validation["recommendation"]["can_change_acceptance"] is False
    assert overfit_validation["checks"]["deterministic_gate_active"] is False
    assert overfit_validation["consumed_artifacts"]["decision"].endswith(
        "decision.json"
    )
    assert "validation" in overfit_validation["metric_deltas"]
    assert brief["schema_version"] == "research_brief_v1"
    assert brief["run_id"] == "reject-smoke"
    assert brief["status"] == "stopped_max_rounds"
    assert_matches_schema(run_dir / "research_brief.json", "research_brief")
    assert intent["schema_version"] == "proposal_intent_v1"
    assert intent["recommended_direction"] == "lower_min_edge"
    assert_matches_schema(round_dir / "proposal_intent.json", "proposal_intent")
    assert role_contracts["schema_version"] == AGENT_ROLE_CONTRACTS_SCHEMA_VERSION
    assert_matches_schema(round_dir / "agent_role_contracts.json", "agent_role_contracts")
    assert role_contracts["active_roles"] == ["strategy_modifier"]
    assert role_contracts["implemented_roles"] == ["strategy_modifier"]
    assert role_contracts["stub_roles"] == [
        "analysis",
        "visual_review",
        "overfit_validator",
    ]
    assert role_contracts["roles"][0]["role_name"] == "strategy_modifier"
    assert role_contracts["roles"][0]["execution_mode"] == "active"
    assert role_contracts["roles"][1]["role_name"] == "analysis"
    assert role_contracts["roles"][1]["implemented"] is False
    assert role_contracts["role_topology"][0]["from"] == "strategy_modifier"
    assert analysis_notes["schema_version"] == "analysis_notes_v1"
    assert_matches_schema(round_dir / "analysis_notes.json", "analysis_notes")
    assert analysis_notes["agent_role"] == "analysis"
    assert analysis_notes["execution_mode"] == "stub_contract"
    assert analysis_notes["implemented"] is False
    assert analysis_notes["metrics_before"]["validation"]["trade_count"] == 39
    assert analysis_notes["recommendation"]["action"] == "continue_to_strategy_modifier"
    assert analysis_notes["recommendation"]["can_change_acceptance"] is False
    assert analysis_notes["consumed_artifacts"]["agent_role_contracts"].endswith(
        "agent_role_contracts.json"
    )
    assert selected_attempt["candidate_score"] > 0
    assert agent_input["schema_version"] == AGENT_INPUT_SCHEMA_VERSION
    assert_matches_schema(round_dir / "agent_input.json", "agent_input")
    assert agent_input["target_file"] == "strategies/current_strategy.py"
    assert agent_input["artifacts"]["agent_context_json"].endswith("agent_context.json")
    assert agent_input["artifacts"]["agent_role_contracts"].endswith(
        "agent_role_contracts.json"
    )
    assert agent_input["artifacts"]["analysis_notes_json"].endswith(
        "analysis_notes.json"
    )
    assert agent_input["artifacts"]["analysis_notes_markdown"].endswith(
        "analysis_notes.md"
    )
    assert agent_input["artifacts"]["proposal_intent_json"].endswith(
        "proposal_intent.json"
    )
    assert agent_input["input_bundle_dir"].endswith("agent_input_bundle")
    assert agent_input["output_bundle_dir"].endswith("agent_output_bundle")
    assert agent_input["agent_roles"][0]["role_name"] == "strategy_modifier"
    assert agent_input["agent_roles"][0]["decision_authority"] == "proposal_only"
    assert agent_input["agent_roles"][1]["execution_mode"] == "stub_contract"
    assert agent_input["agent_profiles"][0]["profile_name"] == "primary"
    assert agent_input["agent_profiles"][0]["agent_role"] == "strategy_modifier"
    assert agent_input["agent_profiles"][0]["adapter_name"] == "fixed_patch_stub"
    assert agent_input["agent_profiles"][0]["runner"]["runner_name"] == (
        "in_process_modifier"
    )
    assert agent_input["agent_profiles"][1]["profile_name"] == "fallback_01"
    assert agent_input["active_agent"]["attempt_id"] == ""
    assert agent_input["active_agent"]["agent_role"] == ""
    assert agent_input["active_agent"]["profile_name"] == ""
    assert agent_input["metrics_before"]["validation"]["trade_count"] == 39
    assert agent_input["modifiers"]["primary"] == "strategy_modifier_stub"
    assert agent_input["output_contract"]["schema_version"] == AGENT_OUTPUT_SCHEMA_VERSION
    assert agent_input["output_contract"]["allowed_output_paths"]
    assert agent_input["output_contract"]["workspace_output_path"] == ""
    assert agent_input["output_contract"]["expected_raw_output_path"].endswith(
        "raw_agent_output.txt"
    )
    assert agent_bundle["schema_version"] == "agent_bundle_v1"
    assert_matches_schema(round_dir / "agent_bundle_manifest.json", "agent_bundle")
    assert agent_bundle["input_bundle_dir"].endswith("agent_input_bundle")
    assert agent_bundle["output_bundle_dir"].endswith("agent_output_bundle")
    assert any(
        row["name"] == "agent_role_contracts.json"
        for row in agent_bundle["input_files"]
    )
    assert any(
        row["name"] == "analysis_notes.json"
        for row in agent_bundle["input_files"]
    )
    assert any(
        row["name"] == "analysis_notes.md"
        for row in agent_bundle["input_files"]
    )
    assert any(row["name"] == "agent_input.json" for row in agent_bundle["input_files"])
    assert any(
        row["name"] == "raw_agent_output.txt"
        for row in agent_bundle["output_files"]
    )
    assert (round_dir / "agent_input_bundle/agent_input.json").exists()
    assert (round_dir / "agent_output_bundle/raw_agent_output.txt").exists()
    assert agent_attempts["schema_version"] == "agent_attempts_v1"
    assert_matches_schema(round_dir / "agent_attempts_manifest.json", "agent_attempts")
    assert agent_attempts["attempt_count"] == len(attempts)
    assert agent_attempts["selected_attempt_id"] == "attempt_001_primary"
    assert agent_attempts["attempts"][0]["selected"] is True
    assert agent_attempts["attempts"][0]["profile_name"] == "primary"
    assert agent_attempts["attempts"][0]["agent_role"] == "strategy_modifier"
    assert agent_attempts["attempts"][0]["adapter_name"] == "fixed_patch_stub"
    assert agent_attempts["attempts"][0]["runner_name"] == "in_process_modifier"
    assert agent_attempts["attempts"][0]["failure_code"] == "policy_ev_improvement_low"
    assert agent_attempts["attempts"][0]["files"]
    assert_matches_schema(round_dir / "agent_selection_report.json", "agent_selection")
    assert agent_selection["schema_version"] == "agent_selection_v1"
    assert agent_selection["selected_attempt_id"] == "attempt_001_primary"
    assert agent_selection["attempts"][0]["selected"] is True
    assert agent_selection["attempts"][0]["profile_name"] == "primary"
    assert agent_selection["attempts"][0]["agent_role"] == "strategy_modifier"
    assert agent_selection["attempts"][0]["adapter_name"] == "fixed_patch_stub"
    assert agent_selection["attempts"][0]["runner_name"] == "in_process_modifier"
    assert agent_selection["attempts"][0]["eligible"] is True
    assert agent_selection["attempts"][0]["rank"] == 1
    assert agent_selection["attempts"][0]["failure_stage"] == "policy_gate"
    assert agent_selection["attempts"][0]["failure_code"] == "policy_ev_improvement_low"
    assert agent_selection["attempts"][0]["score_reasons"]
    assert agent_selection["attempts"][0]["skip_reason"] == ""
    assert (
        round_dir / "agent_attempts/attempt_001_primary/selection.json"
    ).exists()
    assert (
        round_dir / "agent_attempts/attempt_001_primary/raw_agent_output.txt"
    ).exists()
    assert (round_dir / "agent_attempts/attempt_001_primary/proposal.json").exists()
    assert (round_dir / "agent_attempts/attempt_001_primary/patch.diff").exists()
    assert (
        round_dir / "agent_attempts/attempt_001_primary/attempt_output.json"
    ).exists()
    attempt_agent_input = json.loads(
        (
            round_dir / "agent_attempts/attempt_001_primary/agent_input.json"
        ).read_text(encoding="utf-8")
    )
    attempt_output = json.loads(
        (
            round_dir / "agent_attempts/attempt_001_primary/attempt_output.json"
        ).read_text(encoding="utf-8")
    )
    assert_matches_schema(
        round_dir / "agent_attempts/attempt_001_primary/agent_input.json",
        "agent_input",
    )
    assert_matches_schema(
        round_dir / "agent_attempts/attempt_001_primary/attempt_output.json",
        "attempt_output",
    )
    assert agent_attempts["attempts"][0]["agent_input"].endswith(
        "agent_attempts/attempt_001_primary/agent_input.json"
    )
    assert agent_attempts["attempts"][0]["attempt_output"].endswith(
        "agent_attempts/attempt_001_primary/attempt_output.json"
    )
    assert any(
        row["name"] == "agent_input.json"
        for row in agent_attempts["attempts"][0]["files"]
    )
    assert any(
        row["name"] == "attempt_output.json"
        for row in agent_attempts["attempts"][0]["files"]
    )
    assert attempt_agent_input["active_agent"]["attempt_id"] == "attempt_001_primary"
    assert attempt_agent_input["active_agent"]["agent_role"] == "strategy_modifier"
    assert attempt_agent_input["active_agent"]["profile_name"] == "primary"
    assert attempt_agent_input["active_agent"]["adapter_name"] == "fixed_patch_stub"
    assert attempt_agent_input["active_agent"]["agent_name"] == "strategy_modifier_stub"
    assert attempt_agent_input["output_contract"]["workspace_output_path"] == ""
    assert attempt_output["schema_version"] == "attempt_output_v1"
    assert attempt_output["attempt_id"] == "attempt_001_primary"
    assert attempt_output["agent_role"] == "strategy_modifier"
    assert attempt_output["profile_name"] == "primary"
    assert attempt_output["adapter_name"] == "fixed_patch_stub"
    assert attempt_output["runner_name"] == "in_process_modifier"
    assert attempt_output["runner"]["isolation"] == "none"
    assert attempt_output["selected"] is True
    assert attempt_output["proposal"]["patch_sha256"] == proposal["patch_sha256"]
    assert attempt_output["selection"]["skip_reason"] == ""
    assert attempt_output["failure_code"] == "policy_ev_improvement_low"
    assert attempt_output["artifacts"]["agent_input"].endswith(
        "agent_attempts/attempt_001_primary/agent_input.json"
    )
    assert attempt_output["artifacts"]["selection"].endswith(
        "agent_attempts/attempt_001_primary/selection.json"
    )
    assert agent_output["schema_version"] == AGENT_OUTPUT_SCHEMA_VERSION
    assert_matches_schema(round_dir / "agent_output.json", "agent_output")
    assert agent_output["selected_role"] == selected_attempt["role"]
    assert agent_output["selected_agent_role"] == "strategy_modifier"
    assert agent_output["selected_proposal"]["patch_sha256"] == proposal["patch_sha256"]
    assert agent_output["attempt_count"] == len(attempts)
    assert agent_output["attempts"][0]["profile_name"] == "primary"
    assert agent_output["attempts"][0]["agent_role"] == "strategy_modifier"
    assert agent_output["attempts"][0]["adapter_name"] == "fixed_patch_stub"
    assert agent_output["attempts"][0]["runner_name"] == "in_process_modifier"
    assert "routing_prior" in agent_output["attempts"][0]
    assert agent_output["artifacts"]["agent_input"].endswith("agent_input.json")
    assert agent_output["artifacts"]["agent_bundle_manifest"].endswith(
        "agent_bundle_manifest.json"
    )
    assert agent_output["artifacts"]["raw_agent_output"].endswith(
        "raw_agent_output.txt"
    )
    assert agent_validation["agent_output_path"].endswith("raw_agent_output.txt")
    assert agent_validation["schema_version"] == AGENT_VALIDATION_SCHEMA_VERSION
    assert_matches_schema(round_dir / "agent_validation.json", "agent_validation")
    assert agent_validation["ok"] is True
    assert agent_validation["failure_code"] == "none"
    assert agent_validation["reason_codes"] == []
    assert agent_validation["checks"]["contract_valid"] is True
    assert agent_validation["checks"]["git_apply_check"] == "passed"
    assert agent_validation["proposal_patch_sha256"] == proposal["patch_sha256"]
    assert agent_executor["schema_version"] == "agent_executor_v1"
    assert_matches_schema(round_dir / "agent_executor_report.json", "agent_executor")
    assert agent_executor["attempt_count"] == len(attempts)
    assert agent_executor["selected_attempt_id"] == "attempt_001_primary"
    assert agent_executor["execution_policy"]["mode"] == "sequential"
    assert agent_executor["execution_policy"]["max_candidates"] == 0
    assert agent_executor["execution_policy"]["per_agent_timeout_seconds"] == 120
    assert agent_routing["schema_version"] == "agent_routing_policy_v1"
    assert_matches_schema(
        round_dir / "agent_routing_policy.json",
        "agent_routing_policy",
    )
    assert agent_routing["selected_attempt_id"] == "attempt_001_primary"
    assert agent_routing["selected_profile_name"] == "primary"
    assert agent_routing["selected_agent_role"] == "strategy_modifier"
    assert agent_routing["selected_runner_name"] == "in_process_modifier"
    assert agent_routing["routing_policy"]["mode"] == (
        "deterministic_score_then_policy_gate"
    )
    assert (
        agent_routing["routing_policy"]["candidate_selection"]["routing_prefer_bonus"]
        == 8
    )
    assert agent_routing["candidates"][0]["selected"] is True
    assert agent_routing["candidates"][0]["agent_role"] == "strategy_modifier"
    assert agent_routing["candidates"][0]["selection_reason"] == selected_attempt[
        "selection_reason"
    ]
    assert agent_routing["candidates"][0]["artifacts"]["attempt_output"].endswith(
        "agent_attempts/attempt_001_primary/attempt_output.json"
    )
    assert agent_executor["execution_policy"]["allow_disabled_adapters"] is True
    assert agent_executor["attempts"][0]["modifier_name"] == "strategy_modifier_stub"
    assert agent_executor["attempts"][0]["profile_name"] == "primary"
    assert agent_executor["attempts"][0]["agent_role"] == "strategy_modifier"
    assert agent_executor["attempts"][0]["adapter_name"] == "fixed_patch_stub"
    assert agent_executor["attempts"][0]["proposal"]["applicable"] is True
    assert agent_executor["attempts"][0]["artifacts"]["attempt_dir"].endswith(
        "agent_attempts/attempt_001_primary"
    )
    assert selected_attempt["direction_tag"] == "lower_min_edge"
    assert selected_attempt["validation_status"] == "evaluated"
    assert selected_attempt["failure_code"] == "policy_ev_improvement_low"
    assert leaderboard[0]["failure_code"] == "policy_ev_improvement_low"
    assert agent_stats["schema_version"] == "agent_result_stats_v1"
    assert_matches_schema(run_dir / "agent_result_stats.json", "agent_result_stats")
    assert agent_stats["totals"]["attempt_count"] == len(leaderboard)
    assert agent_stats["agents"][0]["key"] == "strategy_modifier_stub"
    assert agent_stats["agents"][0]["top_failure_code"] == "policy_ev_improvement_low"
    assert agent_stats["directions"][0]["key"] == "lower_min_edge"
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


def test_iteration_loop_uses_explicit_agent_profiles(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config_path = repo / "config/agent_profiles.json"
    config = json.loads((repo / "config/default.json").read_text())
    config["agents"] = [
        {
            "name": "strategy_bot",
            "adapter": "fixed_patch_stub",
            "role": "primary",
            "agent_role": "strategy_modifier",
            "enabled": True,
            "settings": {},
        },
        {
            "name": "disabled_agent",
            "adapter": "conservative_stub",
            "role": "fallback",
            "agent_role": "analysis",
            "enabled": False,
            "settings": {},
        },
        {
            "name": "risk_agent",
            "adapter": "adaptive_stub",
            "role": "fallback",
            "agent_role": "strategy_modifier",
            "enabled": True,
            "settings": {},
        },
    ]
    config_path.write_text(json.dumps(config), encoding="utf-8")

    manifest = run_iteration_loop(
        run_id="agent-profiles",
        max_rounds=1,
        repo_root=repo,
        config_path=config_path,
    )

    round_dir = repo / "experiments/agent-profiles/round_001"
    attempts = json.loads(
        (round_dir / "proposal_attempts.json").read_text(encoding="utf-8")
    )
    agent_executor = json.loads(
        (round_dir / "agent_executor_report.json").read_text(encoding="utf-8")
    )
    agent_output = json.loads(
        (round_dir / "agent_output.json").read_text(encoding="utf-8")
    )
    agent_input = json.loads(
        (round_dir / "agent_input.json").read_text(encoding="utf-8")
    )
    role_contracts = json.loads(
        (round_dir / "agent_role_contracts.json").read_text(encoding="utf-8")
    )

    assert [profile["name"] for profile in manifest["agent_profiles"]] == [
        "strategy_bot",
        "disabled_agent",
        "risk_agent",
    ]
    assert manifest["agent_roles"][0]["role_name"] == "strategy_modifier"
    assert role_contracts["active_roles"] == ["strategy_modifier"]
    assert agent_input["agent_roles"][0]["role_name"] == "strategy_modifier"
    assert [profile["runner"]["runner_name"] for profile in manifest["agent_profiles"]] == [
        "in_process_modifier",
        "in_process_modifier",
        "in_process_modifier",
    ]
    assert [attempt["role"] for attempt in attempts] == ["primary", "fallback_01"]
    assert [attempt["profile_name"] for attempt in attempts] == [
        "strategy_bot",
        "risk_agent",
    ]
    assert [attempt["adapter_name"] for attempt in attempts] == [
        "fixed_patch_stub",
        "adaptive_stub",
    ]
    assert [attempt["agent_role"] for attempt in attempts] == [
        "strategy_modifier",
        "strategy_modifier",
    ]
    assert [attempt["profile_name"] for attempt in agent_executor["attempts"]] == [
        "strategy_bot",
        "risk_agent",
    ]
    assert [attempt["agent_role"] for attempt in agent_executor["attempts"]] == [
        "strategy_modifier",
        "strategy_modifier",
    ]
    assert [attempt["runner"]["runner_name"] for attempt in agent_executor["attempts"]] == [
        "in_process_modifier",
        "in_process_modifier",
    ]
    assert [attempt["profile_name"] for attempt in agent_output["attempts"]] == [
        "strategy_bot",
        "risk_agent",
    ]
    assert [attempt["agent_role"] for attempt in agent_output["attempts"]] == [
        "strategy_modifier",
        "strategy_modifier",
    ]
    assert [attempt["runner_name"] for attempt in agent_output["attempts"]] == [
        "in_process_modifier",
        "in_process_modifier",
    ]
    assert [profile["profile_name"] for profile in agent_input["agent_profiles"]] == [
        "strategy_bot",
        "disabled_agent",
        "risk_agent",
    ]
    assert agent_input["agent_profiles"][1]["enabled"] is False
    assert agent_input["agent_profiles"][1]["agent_role"] == "analysis"
    assert agent_input["agent_profiles"][1]["runner"]["runner_name"] == (
        "in_process_modifier"
    )


def test_iteration_loop_writes_research_brief(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)

    run_iteration_loop(
        run_id="research-brief",
        max_rounds=1,
        repo_root=repo,
    )
    run_dir = repo / "experiments/research-brief"
    round_dir = run_dir / "round_001"
    brief_path = run_dir / "research_brief.json"
    markdown_path = run_dir / "research_brief.md"
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    report = validate_run_artifacts(
        run_id="research-brief",
        experiments_dir=repo / "experiments",
        repo_root=repo,
    )

    assert brief["schema_version"] == "research_brief_v1"
    assert brief["run_id"] == "research-brief"
    assert brief["kind"] == "iteration_loop"
    assert brief["status"] == "stopped_max_rounds"
    assert brief["artifact_ok"] is True
    assert brief["artifact_error_count"] == 0
    assert brief["top_candidates"]
    assert brief["selected_candidates"]
    assert brief["next_questions"]
    assert "# Research Brief" in markdown
    assert "## Top Candidates" in markdown
    assert_matches_schema(brief_path, "research_brief")
    assert report["ok"] is True
    assert any(
        path.endswith("research_brief.json")
        for path in report["checked_files"]  # type: ignore[union-attr]
    )
    assert any(
        path.endswith("research_brief.md")
        for path in report["checked_files"]  # type: ignore[union-attr]
    )
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


def test_executor_max_candidates_caps_iteration_queue(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config = replace(
        load_project_config(repo),
        executor={
            "mode": "sequential",
            "max_candidates": 1,
            "per_agent_timeout_seconds": 120,
            "allow_disabled_adapters": True,
        },
    )

    manifest = run_iteration_loop(
        run_id="executor-caps-candidates",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    round_dir = repo / "experiments/executor-caps-candidates/round_001"
    attempts = json.loads(
        (round_dir / "proposal_attempts.json").read_text(encoding="utf-8")
    )
    executor = json.loads(
        (round_dir / "agent_executor_report.json").read_text(encoding="utf-8")
    )

    assert manifest["executor_policy"]["max_candidates"] == 1
    assert [attempt["role"] for attempt in attempts] == ["primary"]
    assert executor["attempt_count"] == 1
    assert executor["execution_policy"]["max_candidates"] == 1
    assert executor["attempts"][0]["attempt_id"] == "attempt_001_primary"


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
    assert manifest["candidate_selection"]["direction_prior_weight"] == 1.0
    assert attempts[1]["candidate_selection"]["direction_prior_weight"] == 1.0


def test_candidate_selection_can_disable_direction_prior_weight(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    base_config = load_project_config(repo)
    config = replace(
        base_config,
        memory_failed_patch_threshold=0,
        memory_failed_direction_threshold=99,
        memory_fallback_modifier="conservative_stub",
        memory_fallback_modifiers=("conservative_stub",),
        stop_after_no_improvement_rounds=0,
        candidate_selection={
            **base_config.candidate_selection,
            "direction_prior_weight": 0.0,
        },
    )
    for index in range(5):
        append_outcome_memory(
            experiments_dir=repo / "experiments",
            record={
                "kind": "proposal_outcome",
                "run_id": f"disabled-prior-success-{index}",
                "round_id": "round_001",
                "direction_tag": "raise_min_edge",
                "accepted": True,
                "patch_sha256": f"disabled-prior-raise-{index}",
                "validation_ev_delta": 0.02,
            },
        )

    manifest = run_iteration_loop(
        run_id="direction-prior-disabled",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    round_dir = repo / "experiments/direction-prior-disabled/round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    attempts = json.loads(
        (round_dir / "proposal_attempts.json").read_text(encoding="utf-8")
    )

    assert manifest["candidate_selection"]["direction_prior_weight"] == 0.0
    assert manifest["rounds"][0]["proposal_fallback_used"] is False  # type: ignore[index]
    assert proposal["direction_tag"] == "lower_min_edge"
    assert attempts[1]["direction_prior"]["score_delta"] > 0
    assert attempts[1]["candidate_selection"]["direction_prior_weight"] == 0.0
    assert all(
        "direction prior" not in reason
        for reason in attempts[1]["score_reasons"]
    )


def test_iteration_loop_uses_routing_prior_to_rank_candidates(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    stats_dir = repo / "experiments/routing-history"
    stats_dir.mkdir(parents=True)
    (stats_dir / "agent_result_stats.json").write_text(
        json.dumps(
            {
                "schema_version": "agent_result_stats_v1",
                "run_id": "routing-history",
                "source_path": "experiments/routing-history/candidate_leaderboard.json",
                "generated_at": "2026-06-02T00:00:00Z",
                "totals": {
                    "attempt_count": 2,
                    "selected_count": 2,
                    "selectable_count": 2,
                    "accepted_count": 0,
                    "rejected_count": 2,
                },
                "agents": [],
                "directions": [],
                "patch_families": [],
                "routing_hints": [
                    {
                        "target_type": "agent_name",
                        "target": "strategy_modifier_stub",
                        "action": "downweight",
                        "reason": "prior stub attempts failed",
                        "top_failure_code": "policy_ev_improvement_low",
                        "attempt_count": 2,
                        "accepted_count": 0,
                    },
                    {
                        "target_type": "direction_tag",
                        "target": "lower_min_edge",
                        "action": "downweight",
                        "reason": "prior lower_min_edge attempts failed",
                        "top_failure_code": "policy_ev_improvement_low",
                        "attempt_count": 2,
                        "accepted_count": 0,
                    },
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    config = replace(
        load_project_config(repo),
        memory_failed_patch_threshold=0,
        memory_failed_direction_threshold=99,
        memory_fallback_modifier="conservative_stub",
        memory_fallback_modifiers=("conservative_stub",),
        stop_after_no_improvement_rounds=0,
    )

    manifest = run_iteration_loop(
        run_id="routing-prior-rank",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    round_dir = repo / "experiments/routing-prior-rank/round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    attempts = json.loads(
        (round_dir / "proposal_attempts.json").read_text(encoding="utf-8")
    )

    assert manifest["rounds"][0]["proposal_fallback_used"] is True  # type: ignore[index]
    assert proposal["direction_tag"] == "raise_min_edge"
    assert attempts[0]["routing_prior"]["active"] is True
    assert attempts[0]["routing_prior"]["score_delta"] < 0
    assert attempts[1]["routing_prior"]["active"] is False
    assert attempts[1]["selected"] is True
    assert any("routing prior" in reason for reason in attempts[0]["score_reasons"])


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
    assert (repo / "experiments/single-cli-style/diagnosis.json").exists()
    metadata = json.loads(
        (repo / "experiments/single-cli-style/run_metadata.json").read_text(
            encoding="utf-8"
        )
    )
    report = validate_run_artifacts(
        run_id="single-cli-style",
        experiments_dir=repo / "experiments",
        repo_root=repo,
    )
    assert report["ok"] is True
    assert report["kind"] == "single_run"
    assert_matches_schema(
        repo / "experiments/single-cli-style/run_metadata.json",
        "run_metadata",
    )
    assert metadata["schema_version"] == "run_metadata_v1"
    assert metadata["kind"] == "single_run"
    assert metadata["config_snapshot"]["strategy_modifier"] == "fixed_patch_stub"
    assert metadata["resolved_datasets"]["validation"].endswith(
        "data/validation/sample_markets.csv"
    )
    validation_fingerprint = metadata["dataset_fingerprints"]["validation"]
    assert validation_fingerprint["exists"] is True
    assert validation_fingerprint["bytes"] > 0
    assert len(validation_fingerprint["sha256"]) == 64


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


def test_adaptive_stub_uses_recent_research_brief_without_memory(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    default = load_project_config(repo)
    fixed_without_fallback = replace(
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
        run_id="brief-signal-source",
        max_rounds=1,
        repo_root=repo,
        config=fixed_without_fallback,
    )
    (repo / "experiments/memory.jsonl").unlink()

    run_iteration_loop(
        run_id="brief-signal-target",
        max_rounds=1,
        repo_root=repo,
        config=adaptive_without_fallback,
    )
    round_dir = repo / "experiments/brief-signal-target/round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    context_payload = json.loads(
        (round_dir / "agent_context.json").read_text(encoding="utf-8")
    )
    intent = json.loads((round_dir / "proposal_intent.json").read_text(encoding="utf-8"))

    assert context_payload["global_outcome_memory"] == []
    assert context_payload["recent_research_briefs"][0]["run_id"] == "brief-signal-source"
    assert context_payload["recent_research_briefs"][0]["top_direction_tag"] == "lower_min_edge"
    assert intent["recommended_direction"] == "reduce_stake"
    assert intent["avoid_directions"] == ["lower_min_edge"]
    assert any("lower_min_edge appears" in item for item in intent["evidence"])
    assert_matches_schema(round_dir / "proposal_intent.json", "proposal_intent")
    assert proposal["direction_tag"] == "reduce_stake"
    assert "STAKE = 8.0" in proposal["patch_diff"]
    assert "recent research briefs flagged lower_min_edge" in proposal["summary"]


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
    workspace_manifest = json.loads(
        (round_dir / "workspace_manifest.json").read_text(encoding="utf-8")
    )

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
    assert "Proposal intent:" in proposal["prompt"]
    assert '"schema_version": "proposal_intent_v1"' in proposal["prompt"]
    assert '"recommended_direction": "lower_min_edge"' in proposal["prompt"]
    assert "No prior rounds in this run." in proposal["prompt"]
    assert (
        "workspaces/dry-run/round_001/primary/attempt_001_primary/strategy_workspace"
        in proposal["workspace_path"]
    )
    assert workspace_manifest["schema_version"] == WORKSPACE_MANIFEST_SCHEMA_VERSION
    assert_matches_schema(round_dir / "workspace_manifest.json", "workspace_manifest")
    assert workspace_manifest["attempt_id"] == "attempt_001_primary"
    assert workspace_manifest["profile_name"] == "primary"
    assert workspace_manifest["adapter_name"] == "codex_dry_run"
    assert workspace_manifest["profile_workspace_slug"] == "primary"
    assert workspace_manifest["agent_name"] == "codex_cli_dry_run"
    assert workspace_manifest["execution_enabled"] is False
    assert workspace_manifest["mutation_policy"]["allowed_paths"] == [
        "strategies/current_strategy.py"
    ]
    assert workspace_manifest["initial_snapshot"]["file_count"] > 0
    assert (
        repo
        / "workspaces/dry-run/round_001/primary/attempt_001_primary/strategy_workspace/strategies/current_strategy.py"
    ).exists()
    assert (
        round_dir / "workspace_manifests/attempt_001_primary.json"
    ).exists()
    assert (
        round_dir / "agent_attempts/attempt_001_primary/workspace_manifest.json"
    ).exists()
    assert decision["accepted"] is False
    assert "does not emit patches" in decision["reasons"][0]
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )


def test_workspace_backed_candidates_use_attempt_scoped_workspaces(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    default = load_project_config(repo)
    config = replace(
        default,
        strategy_modifier="codex_dry_run",
        modifier_settings={
            "executable": "codex",
            "model": "dry-run-model",
            "sandbox": "workspace-write",
        },
        memory_fallback_modifier="codex_dry_run",
        memory_fallback_modifiers=("codex_dry_run",),
    )

    manifest = run_iteration_loop(
        run_id="dry-run-fallback-workspaces",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    round_dir = repo / "experiments/dry-run-fallback-workspaces/round_001"
    attempts = json.loads(
        (round_dir / "proposal_attempts.json").read_text(encoding="utf-8")
    )
    workspace_manifest = json.loads(
        (round_dir / "workspace_manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["completed_rounds"] == 1
    assert [attempt["attempt_id"] for attempt in attempts] == [
        "attempt_001_primary",
        "attempt_002_fallback_01",
    ]
    assert attempts[1]["selected"] is True
    assert workspace_manifest["attempt_id"] == "attempt_002_fallback_01"
    assert (
        "workspaces/dry-run-fallback-workspaces/round_001/primary/attempt_001_primary/strategy_workspace"
        in attempts[0]["proposal"]["workspace_path"]
    )
    assert (
        "workspaces/dry-run-fallback-workspaces/round_001/fallback_01/attempt_002_fallback_01/strategy_workspace"
        in attempts[1]["proposal"]["workspace_path"]
    )
    assert (
        round_dir / "workspace_manifests/attempt_001_primary.json"
    ).exists()
    assert (
        round_dir / "workspace_manifests/attempt_002_fallback_01.json"
    ).exists()
    assert (
        round_dir / "agent_attempts/attempt_001_primary/workspace_manifest.json"
    ).exists()
    assert (
        round_dir / "agent_attempts/attempt_002_fallback_01/workspace_manifest.json"
    ).exists()


def test_file_protocol_adapter_executes_json_fixture(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    fake_agent = write_fake_command(
        tmp_path,
        "fake_file_protocol_agent.py",
        """#!/usr/bin/env python3
import difflib
import json
import pathlib
import sys
agent_input = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
output_path = pathlib.Path(sys.argv[2])
target = agent_input['target_file']
before = agent_input['target_file_content']
active_agent = agent_input['active_agent']
assert active_agent['attempt_id'] == 'attempt_001_primary'
assert active_agent['profile_name'] == 'primary'
assert active_agent['adapter_name'] == 'file_protocol'
assert active_agent['agent_role'] == 'strategy_modifier'
assert pathlib.Path(agent_input['artifacts']['agent_role_contracts']).exists()
assert agent_input['output_contract']['workspace_output_path'].endswith('fixture_agent_output.json')
assert pathlib.Path(agent_input['input_bundle_dir']).exists()
after = before.replace('MIN_EDGE = 0.05', 'MIN_EDGE = 0.04', 1)
patch = ''.join(difflib.unified_diff(
    before.splitlines(keepends=True),
    after.splitlines(keepends=True),
    fromfile=f'a/{target}',
    tofile=f'b/{target}',
))
output_path.write_text(json.dumps({
    "summary": "Lower MIN_EDGE through file protocol.",
    "risk_notes": "May increase trade count and slippage.",
    "direction_tag": "lower_min_edge",
    "expected_metric_change": {"trade_count": "increase", "ev": "uncertain"},
    "hypotheses": ["File protocol agent can emit a strategy-only patch."],
    "patch_diff": patch
}), encoding='utf-8')
""",
    )
    default = load_project_config(repo)
    config = replace(
        default,
        strategy_modifier="file_protocol",
        modifier_settings={
            "executable": str(fake_agent),
            "args": (),
            "execute": True,
            "timeout_seconds": 5,
            "output_filename": "fixture_agent_output.json",
        },
        memory_failed_patch_threshold=0,
        memory_failed_direction_threshold=99,
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
        stop_after_no_improvement_rounds=0,
    )

    manifest = run_iteration_loop(
        run_id="file-protocol-fixture",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    round_dir = repo / "experiments/file-protocol-fixture/round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    agent_input = json.loads((round_dir / "agent_input.json").read_text(encoding="utf-8"))
    agent_output = json.loads(
        (round_dir / "agent_output.json").read_text(encoding="utf-8")
    )
    agent_routing = json.loads(
        (round_dir / "agent_routing_policy.json").read_text(encoding="utf-8")
    )
    agent_execution = json.loads(
        (round_dir / "agent_execution.json").read_text(encoding="utf-8")
    )
    workspace_manifest = json.loads(
        (round_dir / "workspace_manifest.json").read_text(encoding="utf-8")
    )
    attempts = json.loads(
        (round_dir / "proposal_attempts.json").read_text(encoding="utf-8")
    )

    assert manifest["completed_rounds"] == 1
    assert manifest["agent_profiles"][0]["runner"]["runner_name"] == (
        AGENT_CONTRACT_RUNNER_NAME
    )
    assert manifest["agent_profiles"][0]["runner"]["isolation"] == "workspace"
    assert manifest["agent_profiles"][0]["runner"]["allowed_output_files"] == [
        "fixture_agent_output.json"
    ]
    assert_matches_schema(
        round_dir / "agent_routing_policy.json",
        "agent_routing_policy",
    )
    assert agent_routing["selected_runner_name"] == AGENT_CONTRACT_RUNNER_NAME
    assert agent_routing["selected_agent_role"] == "strategy_modifier"
    assert agent_routing["candidates"][0]["runner"]["output_mode"] == "file_contract"
    assert agent_routing["candidates"][0]["agent_role"] == "strategy_modifier"
    assert agent_routing["candidates"][0]["artifacts"]["attempt_output"].endswith(
        "agent_attempts/attempt_001_primary/attempt_output.json"
    )
    assert proposal["agent_name"] == "file_protocol_agent"
    assert proposal["summary"] == "Lower MIN_EDGE through file protocol."
    assert proposal["applicable"] is True
    assert proposal["contract_errors"] == []
    assert proposal["command"][0] == str(fake_agent)
    assert proposal["prompt"].endswith("agent_input.json")
    assert "MIN_EDGE = 0.04" in proposal["patch_diff"]
    assert (round_dir / "fixture_agent_output.json").exists()
    assert agent_execution["schema_version"] == AGENT_EXECUTION_SCHEMA_VERSION
    assert agent_execution["runner_name"] == AGENT_CONTRACT_RUNNER_NAME
    assert_matches_schema(round_dir / "agent_execution.json", "agent_execution")
    assert agent_execution["profile_name"] == "primary"
    assert agent_execution["adapter_name"] == "file_protocol"
    assert agent_execution["status"] == "completed"
    assert agent_execution["execution_enabled"] is True
    assert agent_execution["returncode"] == 0
    assert agent_execution["command"][0] == str(fake_agent)
    assert agent_execution["mutation_errors"] == []
    assert agent_execution["output_file"]["exists"] is True
    assert len(agent_execution["output_file"]["sha256"]) == 64
    assert (
        "file-protocol-fixture-file-protocol/round_001/primary/attempt_001_primary"
        in agent_execution["workspace_path"]
    )
    assert workspace_manifest["schema_version"] == WORKSPACE_MANIFEST_SCHEMA_VERSION
    assert_matches_schema(round_dir / "workspace_manifest.json", "workspace_manifest")
    assert workspace_manifest["attempt_id"] == "attempt_001_primary"
    assert workspace_manifest["profile_name"] == "primary"
    assert workspace_manifest["adapter_name"] == "file_protocol"
    assert workspace_manifest["profile_workspace_slug"] == "primary"
    assert workspace_manifest["agent_name"] == "file_protocol_agent"
    assert workspace_manifest["execution_enabled"] is True
    assert workspace_manifest["mutation_policy"]["allowed_paths"] == [
        "experiments/file-protocol-fixture/round_001/fixture_agent_output.json"
    ]
    assert workspace_manifest["initial_snapshot"]["file_count"] > 0
    assert agent_input["agent_profiles"][0]["runner"]["runner_name"] == (
        AGENT_CONTRACT_RUNNER_NAME
    )
    assert agent_input["agent_profiles"][0]["runner"]["output_mode"] == "file_contract"
    assert attempts[0]["runner_name"] == AGENT_CONTRACT_RUNNER_NAME
    assert attempts[0]["agent_role"] == "strategy_modifier"
    workspace_agent_input = json.loads(
        Path(agent_execution["agent_input_path"]).read_text(encoding="utf-8")
    )
    attempt_agent_input = json.loads(
        (
            round_dir / "agent_attempts/attempt_001_primary/agent_input.json"
        ).read_text(encoding="utf-8")
    )
    attempt_output = json.loads(
        (
            round_dir / "agent_attempts/attempt_001_primary/attempt_output.json"
        ).read_text(encoding="utf-8")
    )
    workspace_bundle_agent_input = json.loads(
        (
            Path(agent_execution["workspace_path"])
            / "experiments/file-protocol-fixture/round_001/agent_input_bundle/agent_input.json"
        ).read_text(encoding="utf-8")
    )
    assert agent_input["active_agent"]["attempt_id"] == ""
    assert workspace_agent_input["active_agent"]["attempt_id"] == "attempt_001_primary"
    assert workspace_agent_input["active_agent"]["agent_role"] == "strategy_modifier"
    assert workspace_agent_input["active_agent"]["profile_name"] == "primary"
    assert workspace_agent_input["active_agent"]["adapter_name"] == "file_protocol"
    assert workspace_agent_input["active_agent"]["agent_name"] == "file_protocol_agent"
    assert workspace_agent_input["active_agent"]["output_filename"] == (
        "fixture_agent_output.json"
    )
    assert workspace_agent_input["output_contract"]["workspace_output_path"].endswith(
        "fixture_agent_output.json"
    )
    assert (
        Path(agent_execution["workspace_path"])
        / "experiments/file-protocol-fixture/round_001/analysis_notes.json"
    ).exists()
    assert workspace_agent_input["artifacts"]["analysis_notes_json"].endswith(
        "analysis_notes.json"
    )
    assert workspace_bundle_agent_input["active_agent"] == workspace_agent_input[
        "active_agent"
    ]
    assert attempt_agent_input == workspace_agent_input
    assert_matches_schema(
        round_dir / "agent_attempts/attempt_001_primary/agent_input.json",
        "agent_input",
    )
    assert_matches_schema(
        round_dir / "agent_attempts/attempt_001_primary/attempt_output.json",
        "attempt_output",
    )
    assert (
        Path(agent_execution["workspace_path"])
        / "experiments/file-protocol-fixture/round_001/agent_input_bundle/agent_input.json"
    ).exists()
    assert (round_dir / "agent_executions/attempt_001_primary.json").exists()
    assert (
        round_dir / "agent_attempts/attempt_001_primary/agent_execution.json"
    ).exists()
    assert (
        round_dir / "agent_attempts/attempt_001_primary/workspace_manifest.json"
    ).exists()
    assert attempt_output["profile_name"] == "primary"
    assert attempt_output["agent_role"] == "strategy_modifier"
    assert attempt_output["adapter_name"] == "file_protocol"
    assert attempt_output["agent_name"] == "file_protocol_agent"
    assert attempt_output["runner_name"] == AGENT_CONTRACT_RUNNER_NAME
    assert attempt_output["runner"]["execution_enabled"] is True
    assert attempt_output["artifacts"]["agent_execution"].endswith(
        "agent_attempts/attempt_001_primary/agent_execution.json"
    )
    assert attempt_output["artifacts"]["workspace_manifest"].endswith(
        "agent_attempts/attempt_001_primary/workspace_manifest.json"
    )
    assert agent_input["target_file_content"].count("MIN_EDGE = 0.05") == 1
    assert agent_output["selected_proposal"]["patch_sha256"] == proposal["patch_sha256"]
    assert attempts[0]["selected"] is True
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )


def test_file_protocol_adapter_rejects_workspace_side_effect(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    original_readme = (repo / "README.md").read_text(encoding="utf-8")
    fake_agent = write_fake_command(
        tmp_path,
        "fake_file_protocol_mutates_workspace.py",
        """#!/usr/bin/env python3
import difflib
import json
import pathlib
import sys
agent_input = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
output_path = pathlib.Path(sys.argv[2])
pathlib.Path('README.md').write_text('workspace mutation\\n', encoding='utf-8')
target = agent_input['target_file']
before = agent_input['target_file_content']
after = before.replace('MIN_EDGE = 0.05', 'MIN_EDGE = 0.04', 1)
patch = ''.join(difflib.unified_diff(
    before.splitlines(keepends=True),
    after.splitlines(keepends=True),
    fromfile=f'a/{target}',
    tofile=f'b/{target}',
))
output_path.write_text(json.dumps({
    "summary": "Return a patch after mutating workspace README.",
    "risk_notes": "Mutation guard should reject this.",
    "direction_tag": "lower_min_edge",
    "expected_metric_change": {"trade_count": "increase"},
    "hypotheses": ["Workspace side effects should be rejected."],
    "patch_diff": patch
}), encoding='utf-8')
""",
    )
    default = load_project_config(repo)
    config = replace(
        default,
        strategy_modifier="file_protocol",
        modifier_settings={
            "executable": str(fake_agent),
            "args": (),
            "execute": True,
            "timeout_seconds": 5,
            "output_filename": "fixture_agent_output.json",
            "workspace_root": "workspaces",
        },
        memory_failed_patch_threshold=0,
        memory_failed_direction_threshold=99,
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
        stop_after_no_improvement_rounds=0,
    )

    run_iteration_loop(
        run_id="file-protocol-mutation-guard",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    round_dir = repo / "experiments/file-protocol-mutation-guard/round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    agent_execution = json.loads(
        (round_dir / "agent_execution.json").read_text(encoding="utf-8")
    )
    attempts = json.loads(
        (round_dir / "proposal_attempts.json").read_text(encoding="utf-8")
    )
    workspace_readme = (
        repo
        / "workspaces/file-protocol-mutation-guard-file-protocol/round_001/primary/attempt_001_primary/strategy_workspace/README.md"
    ).read_text(encoding="utf-8")

    assert proposal["applicable"] is False
    assert proposal["direction_tag"] == "file_protocol_source_violation"
    assert proposal["contract_errors"] == [
        "workspace modified disallowed file: README.md"
    ]
    assert agent_execution["status"] == "workspace_violation"
    assert agent_execution["profile_name"] == "primary"
    assert agent_execution["adapter_name"] == "file_protocol"
    assert agent_execution["mutation_errors"] == [
        "workspace modified disallowed file: README.md"
    ]
    assert agent_execution["output_file"]["exists"] is True
    assert len(agent_execution["output_file"]["sha256"]) == 64
    assert attempts[0]["status"] == "contract_invalid"
    assert workspace_readme == "workspace mutation\n"
    assert (repo / "README.md").read_text(encoding="utf-8") == original_readme
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )


def test_file_protocol_adapter_disabled_writes_execution_audit(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    default = load_project_config(repo)
    config = replace(
        default,
        strategy_modifier="file_protocol",
        modifier_settings={
            "executable": "definitely-not-run",
            "args": (),
            "execute": False,
            "timeout_seconds": 5,
            "output_filename": "disabled_agent_output.json",
            "workspace_root": "workspaces",
        },
        memory_failed_patch_threshold=0,
        memory_failed_direction_threshold=99,
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
        stop_after_no_improvement_rounds=0,
    )

    manifest = run_iteration_loop(
        run_id="file-protocol-disabled",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    round_dir = repo / "experiments/file-protocol-disabled/round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    agent_execution = json.loads(
        (round_dir / "agent_execution.json").read_text(encoding="utf-8")
    )

    assert manifest["completed_rounds"] == 1
    assert proposal["direction_tag"] == "file_protocol_disabled"
    assert agent_execution["schema_version"] == AGENT_EXECUTION_SCHEMA_VERSION
    assert agent_execution["status"] == "disabled"
    assert agent_execution["profile_name"] == "primary"
    assert agent_execution["adapter_name"] == "file_protocol"
    assert agent_execution["execution_enabled"] is False
    assert agent_execution["returncode"] is None
    assert agent_execution["command"][0] == "definitely-not-run"
    assert agent_execution["output_file"]["exists"] is False
    assert agent_execution["mutation_errors"] == []


def test_file_protocol_adapter_times_out_with_audit(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    fake_agent = write_fake_command(
        tmp_path,
        "fake_file_protocol_timeout.py",
        """#!/usr/bin/env python3
import time
time.sleep(2)
""",
    )
    default = load_project_config(repo)
    config = replace(
        default,
        strategy_modifier="file_protocol",
        modifier_settings={
            "executable": str(fake_agent),
            "args": (),
            "execute": True,
            "timeout_seconds": 1,
            "output_filename": "timeout_agent_output.json",
            "workspace_root": "workspaces",
        },
        memory_failed_patch_threshold=0,
        memory_failed_direction_threshold=99,
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
        stop_after_no_improvement_rounds=0,
    )

    run_iteration_loop(
        run_id="file-protocol-timeout",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    round_dir = repo / "experiments/file-protocol-timeout/round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    agent_execution = json.loads(
        (round_dir / "agent_execution.json").read_text(encoding="utf-8")
    )

    assert proposal["applicable"] is False
    assert proposal["direction_tag"] == "file_protocol_timeout"
    assert "timed out" in proposal["rejection_reason"]
    assert agent_execution["status"] == "timeout"
    assert agent_execution["profile_name"] == "primary"
    assert agent_execution["adapter_name"] == "file_protocol"
    assert agent_execution["returncode"] is None
    assert agent_execution["stderr"]["preview"].endswith("seconds")
    assert_matches_schema(round_dir / "agent_execution.json", "agent_execution")
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )


def test_file_protocol_adapter_rejects_unparseable_output(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    fake_agent = write_fake_command(
        tmp_path,
        "fake_file_protocol_bad_output.py",
        """#!/usr/bin/env python3
import pathlib
import sys
pathlib.Path(sys.argv[2]).write_text('not json and not a patch\\n', encoding='utf-8')
""",
    )
    default = load_project_config(repo)
    config = replace(
        default,
        strategy_modifier="file_protocol",
        modifier_settings={
            "executable": str(fake_agent),
            "args": (),
            "execute": True,
            "timeout_seconds": 5,
            "output_filename": "bad_agent_output.txt",
            "workspace_root": "workspaces",
        },
        memory_failed_patch_threshold=0,
        memory_failed_direction_threshold=99,
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
        stop_after_no_improvement_rounds=0,
    )

    run_iteration_loop(
        run_id="file-protocol-bad-output",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    round_dir = repo / "experiments/file-protocol-bad-output/round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    agent_execution = json.loads(
        (round_dir / "agent_execution.json").read_text(encoding="utf-8")
    )

    assert proposal["applicable"] is False
    assert proposal["direction_tag"] == "file_protocol_unknown"
    assert proposal["rejection_reason"] == "No unified diff found in agent output"
    assert agent_execution["status"] == "completed"
    assert agent_execution["profile_name"] == "primary"
    assert agent_execution["adapter_name"] == "file_protocol"
    assert agent_execution["output_file"]["exists"] is True
    assert_matches_schema(round_dir / "agent_execution.json", "agent_execution")
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )


def test_file_protocol_adapter_rejects_disallowed_patch_target(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    original_readme = (repo / "README.md").read_text(encoding="utf-8")
    fake_agent = write_fake_command(
        tmp_path,
        "fake_file_protocol_readme_patch.py",
        """#!/usr/bin/env python3
import json
import pathlib
import sys
patch = '''--- a/README.md
+++ b/README.md
@@ -1,1 +1,1 @@
-# Self Iterating Strategy Agent V0.5
+# Changed
'''
pathlib.Path(sys.argv[2]).write_text(json.dumps({
    "summary": "Try to edit README.",
    "risk_notes": "Should be rejected because target is not the strategy file.",
    "direction_tag": "touch_readme",
    "expected_metric_change": {},
    "hypotheses": ["Non-strategy patches must be rejected."],
    "patch_diff": patch
}), encoding='utf-8')
""",
    )
    default = load_project_config(repo)
    config = replace(
        default,
        strategy_modifier="file_protocol",
        modifier_settings={
            "executable": str(fake_agent),
            "args": (),
            "execute": True,
            "timeout_seconds": 5,
            "output_filename": "readme_patch_output.json",
            "workspace_root": "workspaces",
        },
        memory_failed_patch_threshold=0,
        memory_failed_direction_threshold=99,
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
        stop_after_no_improvement_rounds=0,
    )

    run_iteration_loop(
        run_id="file-protocol-disallowed-patch",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    round_dir = repo / "experiments/file-protocol-disallowed-patch/round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    agent_execution = json.loads(
        (round_dir / "agent_execution.json").read_text(encoding="utf-8")
    )

    assert proposal["applicable"] is False
    assert proposal["direction_tag"] == "touch_readme"
    assert proposal["rejection_reason"] == "Patch touches disallowed files: README.md"
    assert agent_execution["status"] == "completed"
    assert agent_execution["profile_name"] == "primary"
    assert agent_execution["adapter_name"] == "file_protocol"
    assert_matches_schema(round_dir / "agent_execution.json", "agent_execution")
    assert (repo / "README.md").read_text(encoding="utf-8") == original_readme
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )


def test_file_protocol_demo_agent_runs_from_config(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config = load_project_config(repo, repo / "config/file_protocol_demo.json")

    manifest = run_iteration_loop(
        run_id="file-protocol-demo",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    round_dir = repo / "experiments/file-protocol-demo/round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    agent_execution = json.loads(
        (round_dir / "agent_execution.json").read_text(encoding="utf-8")
    )
    agent_output = json.loads(
        (round_dir / "agent_output.json").read_text(encoding="utf-8")
    )
    workspace_manifest = json.loads(
        (round_dir / "workspace_manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["completed_rounds"] == 1
    assert proposal["agent_name"] == "file_protocol_agent"
    assert proposal["summary"] == "Demo file-protocol agent lowers MIN_EDGE."
    assert proposal["direction_tag"] == "file_protocol_demo_lower_min_edge"
    assert proposal["applicable"] is True
    assert "MIN_EDGE = 0.04" in proposal["patch_diff"]
    assert agent_execution["schema_version"] == AGENT_EXECUTION_SCHEMA_VERSION
    assert_matches_schema(round_dir / "agent_input.json", "agent_input")
    assert_matches_schema(round_dir / "agent_output.json", "agent_output")
    assert_matches_schema(round_dir / "agent_execution.json", "agent_execution")
    assert_matches_schema(round_dir / "workspace_manifest.json", "workspace_manifest")
    assert (round_dir / "raw_agent_output.txt").exists()
    assert agent_output["artifacts"]["raw_agent_output"].endswith(
        "raw_agent_output.txt"
    )
    assert agent_execution["status"] == "completed"
    assert agent_execution["profile_name"] == "primary"
    assert agent_execution["adapter_name"] == "file_protocol"
    assert agent_execution["command"][:3] == [
        "python",
        "-m",
        "agents.file_protocol_demo_agent",
    ]
    assert agent_execution["output_file"]["exists"] is True
    assert agent_output["selected_proposal"]["patch_sha256"] == proposal["patch_sha256"]
    assert workspace_manifest["mutation_policy"]["reject_unlisted_changes"] is True
    assert workspace_manifest["initial_snapshot"]["file_count"] > 0
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )


def test_file_protocol_demo_agent_follows_proposal_intent(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    default = load_project_config(repo)
    source_config = replace(
        default,
        memory_fallback_modifier="",
        memory_fallback_modifiers=(),
    )
    run_iteration_loop(
        run_id="file-protocol-intent-source",
        max_rounds=1,
        repo_root=repo,
        config=source_config,
    )
    (repo / "experiments/memory.jsonl").unlink()
    demo_config = load_project_config(repo, repo / "config/file_protocol_demo.json")

    run_iteration_loop(
        run_id="file-protocol-intent-target",
        max_rounds=1,
        repo_root=repo,
        config=demo_config,
    )

    round_dir = repo / "experiments/file-protocol-intent-target/round_001"
    proposal = json.loads((round_dir / "proposal.json").read_text(encoding="utf-8"))
    intent = json.loads((round_dir / "proposal_intent.json").read_text(encoding="utf-8"))

    assert intent["recommended_direction"] == "reduce_stake"
    assert proposal["direction_tag"] == "file_protocol_demo_reduce_stake"
    assert proposal["summary"] == (
        "Demo file-protocol agent follows proposal intent to reduce STAKE."
    )
    assert "STAKE = 8.0" in proposal["patch_diff"]
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )


def test_agent_replay_replays_demo_agent_from_agent_input(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config = load_project_config(repo, repo / "config/file_protocol_demo.json")
    run_iteration_loop(
        run_id="replay-source",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )
    round_dir = repo / "experiments/replay-source/round_001"
    output_path = round_dir / "replayed_agent_output.json"

    replayed = replay_agent_input(
        agent_input_path=round_dir / "agent_input.json",
        output_path=output_path,
    )
    command_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.agent_replay",
            str(round_dir / "agent_input.json"),
            "--output",
            str(round_dir / "replayed_agent_output_cli.json"),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    validate_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.agent_replay",
            str(round_dir / "agent_input.json"),
            "--validate",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    actual = json.loads((round_dir / "demo_agent_output.json").read_text(encoding="utf-8"))
    cli_payload = json.loads(command_result.stdout)
    validate_payload = json.loads(validate_result.stdout)
    validation = validate_replayed_proposal(
        agent_input_path=round_dir / "agent_input.json",
        proposal_payload=replayed,
    )
    intake_report = verify_agent_output(
        agent_input_path=round_dir / "agent_input.json",
        agent_output_path=output_path,
        repo_root=repo,
        output_path=round_dir / "replayed_agent_validation.json",
        proposal_output_path=round_dir / "replayed_agent_proposal.json",
        agent_name="file_protocol_demo_agent",
    )
    intake_cli_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.agent_output_intake",
            str(round_dir / "agent_input.json"),
            str(output_path),
            "--repo-root",
            str(repo),
            "--output",
            str(round_dir / "replayed_agent_validation_cli.json"),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert command_result.returncode == 0
    assert validate_result.returncode == 0
    assert intake_cli_result.returncode == 0
    assert replayed == actual
    assert json.loads(output_path.read_text(encoding="utf-8")) == actual
    assert cli_payload == actual
    assert validation["ok"] is True
    assert validation["errors"] == []
    assert intake_report["ok"] is True
    assert intake_report["checks"]["git_apply_check"] == "passed"  # type: ignore[index]
    assert_matches_schema(round_dir / "replayed_agent_validation.json", "agent_validation")
    assert json.loads(intake_cli_result.stdout)["ok"] is True
    assert validate_payload["proposal"] == actual
    assert validate_payload["validation"]["ok"] is True
    assert validate_payload["validation"]["target_file"] == "strategies/current_strategy.py"
    assert json.loads(
        (round_dir / "replayed_agent_output_cli.json").read_text(encoding="utf-8")
    ) == actual
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )


def test_attempt_replay_validates_and_probes_saved_attempt(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config = load_project_config(repo, repo / "config/file_protocol_demo.json")
    run_iteration_loop(
        run_id="attempt-replay-source",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )
    attempt_dir = (
        repo
        / "experiments/attempt-replay-source/round_001"
        / "agent_attempts/attempt_001_primary"
    )

    report = replay_attempt(attempt_dir=attempt_dir, repo_root=repo)
    command_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.attempt_replay",
            str(attempt_dir),
            "--repo-root",
            str(repo),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    cli_payload = json.loads(command_result.stdout)

    assert command_result.returncode == 0
    assert report["schema_version"] == "attempt_replay_v1"
    assert report["ok"] is True
    assert report["agent_input_path"].endswith(
        "agent_attempts/attempt_001_primary/agent_input.json"
    )
    assert report["failure_code"] == "none"
    assert report["reason_codes"] == []
    assert report["validation"]["ok"] is True  # type: ignore[index]
    assert report["validation"]["checks"]["git_apply_check"] == "passed"  # type: ignore[index]
    assert report["probe"]["ran"] is True  # type: ignore[index]
    assert report["probe"]["ok"] is True  # type: ignore[index]
    assert report["probe"]["failure_code"] == "none"  # type: ignore[index]
    assert cli_payload["ok"] is True
    assert (attempt_dir / "attempt_replay_probe_metrics.json").exists()
    assert (attempt_dir / "attempt_replay_probe_trades.csv").exists()
    assert (attempt_dir / "attempt_replay_probe_report.md").exists()
    assert_matches_schema(attempt_dir / "attempt_replay.json", "attempt_replay")
    assert OLD_THRESHOLD in (repo / "strategies/current_strategy.py").read_text(
        encoding="utf-8"
    )


def test_agent_output_intake_rejects_disallowed_patch(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_iteration_loop(
        run_id="intake-disallowed",
        max_rounds=1,
        repo_root=repo,
    )
    round_dir = repo / "experiments/intake-disallowed/round_001"
    bad_output_path = round_dir / "bad_agent_output.json"
    bad_output_path.write_text(
        json.dumps(
            {
                "summary": "Try to edit documentation instead of the strategy.",
                "risk_notes": "This must be rejected before git apply.",
                "direction_tag": "bad_docs_edit",
                "expected_metric_change": {"ev": "uncertain"},
                "hypotheses": ["Disallowed paths should fail intake validation."],
                "patch_diff": (
                    "--- a/README.md\n"
                    "+++ b/README.md\n"
                    "@@ -1,1 +1,1 @@\n"
                    "-# Self Iterating Strategy Agent V0.5\n"
                    "+# Bad Edit\n"
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    report = verify_agent_output(
        agent_input_path=round_dir / "agent_input.json",
        agent_output_path=bad_output_path,
        repo_root=repo,
        output_path=round_dir / "bad_agent_validation.json",
    )

    assert report["ok"] is False
    assert report["failure_code"] == "contract_invalid"
    assert report["reason_codes"][0]["code"] == "contract_invalid"
    assert report["checks"]["strategy_only_patch"] is False  # type: ignore[index]
    assert any("disallowed files" in error for error in report["errors"])  # type: ignore[union-attr]
    assert_matches_schema(round_dir / "bad_agent_validation.json", "agent_validation")


def test_artifact_validator_accepts_iteration_and_file_protocol_runs(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_iteration_loop(
        run_id="artifact-default",
        max_rounds=1,
        repo_root=repo,
    )
    demo_config = load_project_config(repo, repo / "config/file_protocol_demo.json")
    run_iteration_loop(
        run_id="artifact-file-protocol",
        max_rounds=1,
        repo_root=repo,
        config=demo_config,
    )
    replay_attempt(
        attempt_dir=(
            repo
            / "experiments/artifact-file-protocol/round_001"
            / "agent_attempts/attempt_001_primary"
        ),
        repo_root=repo,
    )

    default_report = validate_run_artifacts(
        run_id="artifact-default",
        experiments_dir=repo / "experiments",
        repo_root=repo,
    )
    file_protocol_report = validate_run_artifacts(
        run_id="artifact-file-protocol",
        experiments_dir=repo / "experiments",
        repo_root=repo,
    )

    assert default_report["ok"] is True
    assert default_report["kind"] == "iteration_loop"
    assert default_report["rounds_checked"] == 1
    assert any(
        path.endswith("diagnosis.json")
        for path in default_report["checked_files"]  # type: ignore[union-attr]
    )
    assert any(
        path.endswith("run_metadata.json")
        for path in default_report["checked_files"]  # type: ignore[union-attr]
    )
    assert file_protocol_report["ok"] is True
    assert any(
        path.endswith("agent_execution.json")
        for path in file_protocol_report["checked_files"]  # type: ignore[union-attr]
    )
    assert any(
        path.endswith("agent_bundle_manifest.json")
        for path in file_protocol_report["checked_files"]  # type: ignore[union-attr]
    )
    assert any(
        path.endswith("agent_role_contracts.json")
        for path in file_protocol_report["checked_files"]  # type: ignore[union-attr]
    )
    assert any(
        path.endswith("analysis_notes.json")
        for path in file_protocol_report["checked_files"]  # type: ignore[union-attr]
    )
    assert any(
        path.endswith("overfit_validation.json")
        for path in file_protocol_report["checked_files"]  # type: ignore[union-attr]
    )
    assert any(
        path.endswith("agent_attempts_manifest.json")
        for path in file_protocol_report["checked_files"]  # type: ignore[union-attr]
    )
    assert any(
        path.endswith("agent_selection_report.json")
        for path in file_protocol_report["checked_files"]  # type: ignore[union-attr]
    )
    assert any(
        path.endswith("agent_result_stats.json")
        for path in file_protocol_report["checked_files"]  # type: ignore[union-attr]
    )
    assert any(
        path.endswith("attempt_replay.json")
        for path in file_protocol_report["checked_files"]  # type: ignore[union-attr]
    )
    assert any(
        path.endswith("workspace_manifest.json")
        for path in file_protocol_report["checked_files"]  # type: ignore[union-attr]
    )


def test_artifact_validator_reports_missing_required_round_file(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_iteration_loop(
        run_id="artifact-missing",
        max_rounds=1,
        repo_root=repo,
    )
    missing_path = repo / "experiments/artifact-missing/round_001/agent_input.json"
    missing_path.unlink()

    report = validate_run_artifacts(
        run_id="artifact-missing",
        experiments_dir=repo / "experiments",
        repo_root=repo,
    )

    assert report["ok"] is False
    assert any(
        "missing required artifact" in error and "agent_input.json" in error
        for error in report["errors"]  # type: ignore[union-attr]
    )


def test_artifact_validator_reports_schema_errors(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    config = load_project_config(repo, repo / "config/file_protocol_demo.json")
    run_iteration_loop(
        run_id="artifact-schema-error",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )
    path = repo / "experiments/artifact-schema-error/round_001/agent_execution.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["status"] = "mystery"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    report = validate_run_artifacts(
        run_id="artifact-schema-error",
        experiments_dir=repo / "experiments",
        repo_root=repo,
    )

    assert report["ok"] is False
    assert any("expected one of" in error and "mystery" in error for error in report["errors"])  # type: ignore[union-attr]


def test_artifact_validator_reports_agent_role_mismatch(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_iteration_loop(
        run_id="artifact-role-mismatch",
        max_rounds=1,
        repo_root=repo,
    )
    path = repo / "experiments/artifact-role-mismatch/round_001/agent_routing_policy.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["selected_agent_role"] = "analysis"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    report = validate_run_artifacts(
        run_id="artifact-role-mismatch",
        experiments_dir=repo / "experiments",
        repo_root=repo,
    )

    assert report["ok"] is False
    assert any(
        "selected_agent_role does not match selected row" in error
        for error in report["errors"]  # type: ignore[union-attr]
    )


def test_artifact_validator_reports_analysis_acceptance_violation(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_iteration_loop(
        run_id="artifact-analysis-violation",
        max_rounds=1,
        repo_root=repo,
    )
    path = repo / "experiments/artifact-analysis-violation/round_001/analysis_notes.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["recommendation"]["can_change_acceptance"] = True
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    report = validate_run_artifacts(
        run_id="artifact-analysis-violation",
        experiments_dir=repo / "experiments",
        repo_root=repo,
    )

    assert report["ok"] is False
    assert any(
        "analysis_notes.json must not change acceptance" in error
        for error in report["errors"]  # type: ignore[union-attr]
    )


def test_artifact_validator_reports_overfit_veto_violation(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_iteration_loop(
        run_id="artifact-overfit-violation",
        max_rounds=1,
        repo_root=repo,
    )
    path = repo / "experiments/artifact-overfit-violation/round_001/overfit_validation.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["recommendation"]["can_veto"] = True
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    report = validate_run_artifacts(
        run_id="artifact-overfit-violation",
        experiments_dir=repo / "experiments",
        repo_root=repo,
    )

    assert report["ok"] is False
    assert any(
        "overfit_validation.json must not veto in V0.5" in error
        for error in report["errors"]  # type: ignore[union-attr]
    )


def test_artifact_validator_reports_metadata_run_id_mismatch(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_iteration_loop(
        run_id="artifact-metadata-error",
        max_rounds=1,
        repo_root=repo,
    )
    path = repo / "experiments/artifact-metadata-error/run_metadata.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["run_id"] = "wrong"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    report = validate_run_artifacts(
        run_id="artifact-metadata-error",
        experiments_dir=repo / "experiments",
        repo_root=repo,
    )

    assert report["ok"] is False
    assert any("run_id does not match" in error for error in report["errors"])  # type: ignore[union-attr]


def test_artifact_validator_reports_research_brief_run_id_mismatch(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_iteration_loop(
        run_id="artifact-brief-error",
        max_rounds=1,
        repo_root=repo,
    )
    path = repo / "experiments/artifact-brief-error/research_brief.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["run_id"] = "wrong"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    report = validate_run_artifacts(
        run_id="artifact-brief-error",
        experiments_dir=repo / "experiments",
        repo_root=repo,
    )

    assert report["ok"] is False
    assert any(
        "research_brief.json run_id does not match" in error
        for error in report["errors"]  # type: ignore[union-attr]
    )


def test_artifact_validator_reports_metadata_schema_errors(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_iteration_loop(
        run_id="artifact-metadata-schema-error",
        max_rounds=1,
        repo_root=repo,
    )
    path = repo / "experiments/artifact-metadata-schema-error/run_metadata.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["dataset_fingerprints"]["validation"] = []
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    report = validate_run_artifacts(
        run_id="artifact-metadata-schema-error",
        experiments_dir=repo / "experiments",
        repo_root=repo,
    )

    assert report["ok"] is False
    assert any(
        "dataset_fingerprints.validation" in error
        and "expected object" in error
        for error in report["errors"]  # type: ignore[union-attr]
    )


def test_artifact_validator_cli_exits_nonzero_for_invalid_run(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.artifact_validator",
            "does-not-exist",
            "--experiments-dir",
            str(repo / "experiments"),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "run directory does not exist" in result.stdout


def test_run_diagnosis_summarizes_single_run(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_pipeline(
        run_id="diagnose-single",
        experiments_dir=repo / "experiments",
        repo_root=repo,
    )

    diagnosis = diagnose_run(
        run_id="diagnose-single",
        experiments_dir=repo / "experiments",
        repo_root=repo,
    )

    assert diagnosis["kind"] == "single_run"
    assert diagnosis["artifact_ok"] is True
    assert diagnosis["status"] == "rejected"
    assert diagnosis["validation_ev_delta"] == 0.0
    assert "Single run rejected" in diagnosis["summary"]
    saved = json.loads(
        (repo / "experiments/diagnose-single/diagnosis.json").read_text(
            encoding="utf-8"
        )
    )
    assert saved["summary"] == diagnosis["summary"]


def test_run_diagnosis_summarizes_iteration_run(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    manifest = run_iteration_loop(
        run_id="diagnose-iteration",
        max_rounds=1,
        repo_root=repo,
    )

    diagnosis = diagnose_run(
        run_id="diagnose-iteration",
        experiments_dir=repo / "experiments",
        repo_root=repo,
    )

    assert diagnosis["kind"] == "iteration_loop"
    assert diagnosis["artifact_ok"] is True
    assert diagnosis["status"] == manifest["status"]
    assert diagnosis["completed_rounds"] == 1
    assert diagnosis["best_round"]["round_id"] == "round_001"  # type: ignore[index]
    assert diagnosis["rounds"][0]["direction_tag"] == "lower_min_edge"  # type: ignore[index]
    assert diagnosis["rounds"][0]["failure_code"] == "policy_ev_improvement_low"  # type: ignore[index]
    assert diagnosis["rounds"][0]["candidate_failure_code"] == "policy_ev_improvement_low"  # type: ignore[index]
    assert diagnosis["rounds"][0]["agent_validation_ok"] is True  # type: ignore[index]
    assert diagnosis["rounds"][0]["agent_bundle_present"] is True  # type: ignore[index]
    assert diagnosis["rounds"][0]["agent_bundle_input_file_count"] > 0  # type: ignore[index]
    assert diagnosis["rounds"][0]["agent_attempt_trace_present"] is True  # type: ignore[index]
    assert diagnosis["rounds"][0]["agent_attempt_count"] > 0  # type: ignore[index]
    assert diagnosis["rounds"][0]["agent_selection_present"] is True  # type: ignore[index]
    assert diagnosis["rounds"][0]["selection_rank_order"]  # type: ignore[index]
    assert "Iteration run" in diagnosis["summary"]
    saved = json.loads(
        (repo / "experiments/diagnose-iteration/diagnosis.json").read_text(
            encoding="utf-8"
        )
    )
    assert saved["best_round"]["round_id"] == "round_001"


def test_run_diagnosis_includes_file_protocol_execution_status(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    config = load_project_config(repo, repo / "config/file_protocol_demo.json")
    run_iteration_loop(
        run_id="diagnose-file-protocol",
        max_rounds=1,
        repo_root=repo,
        config=config,
    )

    diagnosis = diagnose_run(
        run_id="diagnose-file-protocol",
        experiments_dir=repo / "experiments",
        repo_root=repo,
    )

    round_diagnosis = diagnosis["rounds"][0]  # type: ignore[index]
    assert diagnosis["artifact_ok"] is True
    assert round_diagnosis["agent_name"] == "file_protocol_agent"
    assert round_diagnosis["file_protocol_status"] == "completed"
    assert round_diagnosis["selected_role"] == "primary"
    assert diagnosis["metadata"]["strategy_modifier"] == "file_protocol"  # type: ignore[index]
    assert len(diagnosis["metadata"]["dataset_sha256"]["validation"]) == 64  # type: ignore[index]
    assert diagnosis["selected_candidates"][0]["agent_name"] == "file_protocol_agent"  # type: ignore[index]


def test_experiments_diagnose_subcommand_outputs_json(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_iteration_loop(
        run_id="diagnose-cli",
        max_rounds=1,
        repo_root=repo,
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.experiments",
            "--experiments-dir",
            str(repo / "experiments"),
            "diagnose",
            "diagnose-cli",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["kind"] == "iteration_loop"
    assert payload["artifact_ok"] is True
    assert payload["rounds"][0]["round_id"] == "round_001"


def test_schema_validator_reports_missing_required_property() -> None:
    errors = validate_json_payload(
        payload={"schema_version": AGENT_INPUT_SCHEMA_VERSION},
        schema=json.loads(
            (Path.cwd() / "schemas/agent_input.schema.json").read_text(
                encoding="utf-8"
            )
        ),
    )

    assert "$: missing required property run_id" in errors


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
    agent_validation = json.loads(
        (round_dir / "agent_validation.json").read_text(encoding="utf-8")
    )
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
    assert agent_validation["ok"] is True
    assert agent_validation["proposal_direction_tag"] == "lower_min_edge"
    assert agent_validation["checks"]["git_apply_check"] == "passed"
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
    assert "Recent Research Briefs" in context_text
    assert "memory-source" in context_text
    assert "strategy_modifier_stub" in context_text
    assert "ev improvement" in context_text
    assert context_payload["global_outcome_memory"][0]["run_id"] == "memory-source"
    assert context_payload["recent_research_briefs"][0]["run_id"] == "memory-source"
    assert context_payload["recent_research_briefs"][0]["next_questions"]


def test_agent_context_limits_recent_research_briefs(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    for index in range(4):
        run_iteration_loop(
            run_id=f"brief-source-{index}",
            max_rounds=1,
            repo_root=repo,
        )

    context_payload = build_agent_context_payload(
        run_dir=repo / "experiments/brief-reader",
        current_round_id="round_001",
    )
    context_text = build_agent_context(
        run_dir=repo / "experiments/brief-reader",
        current_round_id="round_001",
    )
    brief_ids = [
        str(payload["run_id"])
        for payload in context_payload["recent_research_briefs"]  # type: ignore[index]
    ]

    assert brief_ids == ["brief-source-3", "brief-source-2", "brief-source-1"]
    assert "Recent Research Briefs" in context_text
    research_section = context_text.split("## Recent Research Briefs", 1)[1]
    assert "brief-source-3" in research_section
    assert "brief-source-0" not in research_section


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


def test_compare_experiments_recommends_accepted_metric_winner(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_pipeline(
        run_id="compare-base",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )
    run_pipeline(
        run_id="compare-candidate",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )
    metrics_path = repo / "experiments/compare-candidate/metrics_after.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["ev"] = round(float(metrics["ev"]) + 0.25, 6)
    metrics_path.write_text(
        json.dumps(metrics, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    decision_path = repo / "experiments/compare-candidate/decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["accepted"] = True
    decision["reasons"] = []
    decision_path.write_text(
        json.dumps(decision, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    comparison = compare_experiments(
        base_run_id="compare-base",
        candidate_run_id="compare-candidate",
        experiments_dir=repo / "experiments",
    )

    assert comparison["winner"] == "candidate"
    assert comparison["recommendation"] == "promote_candidate"
    assert comparison["dataset_comparison"]["match"] is True  # type: ignore[index]
    assert comparison["metric_deltas"]["validation_ev_delta"] == 0.25  # type: ignore[index]


def make_run_accepted_with_ev_lift(
    *,
    repo: Path,
    run_id: str,
    ev_lift: float,
) -> None:
    """Rewrite a test run into an accepted candidate with an EV lift."""
    metrics_path = repo / f"experiments/{run_id}/metrics_after.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["ev"] = round(float(metrics["ev"]) + ev_lift, 6)
    metrics_path.write_text(
        json.dumps(metrics, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    decision_path = repo / f"experiments/{run_id}/decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["accepted"] = True
    decision["reasons"] = []
    decision_path.write_text(
        json.dumps(decision, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def test_champion_registry_promotes_recommended_candidate(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_pipeline(
        run_id="champion-base",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )
    run_pipeline(
        run_id="champion-candidate",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )
    make_run_accepted_with_ev_lift(
        repo=repo,
        run_id="champion-candidate",
        ev_lift=0.3,
    )

    result = promote_champion(
        base_run_id="champion-base",
        candidate_run_id="champion-candidate",
        experiments_dir=repo / "experiments",
    )
    champion = show_champion(experiments_dir=repo / "experiments")

    assert result["promoted"] is True
    assert champion["exists"] is True
    assert result["champion"]["champion_run_id"] == "champion-candidate"  # type: ignore[index]
    assert result["champion"]["comparison"]["recommendation"] == "promote_candidate"  # type: ignore[index]
    assert (repo / "experiments/champion.json").exists()
    assert (repo / "experiments/champion_history.jsonl").exists()
    assert_matches_schema(repo / "experiments/champion.json", "champion")
    history = (repo / "experiments/champion_history.jsonl").read_text(
        encoding="utf-8"
    )
    assert "champion-candidate" in history


def test_champion_registry_refuses_non_promoted_candidate(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_pipeline(
        run_id="champion-refuse-base",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )
    run_pipeline(
        run_id="champion-refuse-candidate",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )

    result = promote_champion(
        base_run_id="champion-refuse-base",
        candidate_run_id="champion-refuse-candidate",
        experiments_dir=repo / "experiments",
    )
    champion = show_champion(experiments_dir=repo / "experiments")

    assert result["promoted"] is False
    assert result["comparison"]["recommendation"] == "keep_base"  # type: ignore[index]
    assert champion["exists"] is False
    assert not (repo / "experiments/champion.json").exists()


def test_iteration_loop_writes_champion_comparison_when_champion_exists(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_pipeline(
        run_id="auto-champion-base",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )
    run_pipeline(
        run_id="auto-champion-current",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )
    make_run_accepted_with_ev_lift(
        repo=repo,
        run_id="auto-champion-current",
        ev_lift=0.4,
    )
    promote_result = promote_champion(
        base_run_id="auto-champion-base",
        candidate_run_id="auto-champion-current",
        experiments_dir=repo / "experiments",
    )

    run_iteration_loop(
        run_id="auto-challenger",
        max_rounds=1,
        repo_root=repo,
    )
    comparison_path = repo / "experiments/auto-challenger/champion_comparison.json"
    brief_path = repo / "experiments/auto-challenger/research_brief.json"
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    markdown = (repo / "experiments/auto-challenger/research_brief.md").read_text(
        encoding="utf-8"
    )
    report = validate_run_artifacts(
        run_id="auto-challenger",
        experiments_dir=repo / "experiments",
        repo_root=repo,
    )

    assert promote_result["promoted"] is True
    assert comparison["schema_version"] == "champion_comparison_v1"
    assert comparison["run_id"] == "auto-challenger"
    assert comparison["champion_run_id"] == "auto-champion-current"
    assert comparison["comparison"]["base_run_id"] == "auto-champion-current"
    assert comparison["comparison"]["candidate_run_id"] == "auto-challenger"
    assert brief["champion_comparison"]["exists"] is True
    assert brief["champion_comparison"]["champion_run_id"] == "auto-champion-current"
    assert "## Champion Comparison" in markdown
    assert_matches_schema(comparison_path, "champion_comparison")
    assert_matches_schema(brief_path, "research_brief")
    assert report["ok"] is True
    assert any(
        path.endswith("champion_comparison.json")
        for path in report["checked_files"]  # type: ignore[union-attr]
    )


def test_agent_context_includes_current_champion_when_registry_exists(
    tmp_path: Path,
) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_pipeline(
        run_id="context-champion-base",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )
    run_pipeline(
        run_id="context-champion-current",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )
    make_run_accepted_with_ev_lift(
        repo=repo,
        run_id="context-champion-current",
        ev_lift=0.2,
    )
    promote_champion(
        base_run_id="context-champion-base",
        candidate_run_id="context-champion-current",
        experiments_dir=repo / "experiments",
    )

    run_iteration_loop(
        run_id="context-challenger",
        max_rounds=1,
        repo_root=repo,
    )
    round_dir = repo / "experiments/context-challenger/round_001"
    context_text = (round_dir / "agent_context.md").read_text(encoding="utf-8")
    context_payload = json.loads(
        (round_dir / "agent_context.json").read_text(encoding="utf-8")
    )
    agent_input = json.loads(
        (round_dir / "agent_input.json").read_text(encoding="utf-8")
    )
    attempts = json.loads(
        (round_dir / "proposal_attempts.json").read_text(encoding="utf-8")
    )
    leaderboard = json.loads(
        (
            repo / "experiments/context-challenger/candidate_leaderboard.json"
        ).read_text(encoding="utf-8")
    )

    assert "Current Champion" in context_text
    assert "context-champion-current" in context_text
    assert "Previous Champion Comparison" in context_text
    assert context_payload["champion"]["exists"] is True
    assert context_payload["champion"]["champion_run_id"] == "context-champion-current"
    assert context_payload["previous_champion_comparison"]["exists"] is False
    assert agent_input["artifacts"]["champion_registry"].endswith("champion.json")
    assert agent_input["artifacts"]["previous_champion_comparison"] == ""
    assert attempts[0]["champion_gap"]["active"] is True
    assert attempts[0]["champion_gap"]["champion_run_id"] == "context-champion-current"
    assert attempts[0]["champion_gap"]["score_delta"] < 0
    assert any("champion gap" in reason for reason in attempts[0]["score_reasons"])
    assert leaderboard[0]["champion_gap"]["active"] is True
    assert_matches_schema(round_dir / "agent_input.json", "agent_input")

    next_context_payload = build_agent_context_payload(
        run_dir=repo / "experiments/context-challenger",
        current_round_id="round_002",
    )
    assert next_context_payload["previous_champion_comparison"]["exists"] is True
    assert (
        next_context_payload["previous_champion_comparison"]["champion_run_id"]
        == "context-champion-current"
    )


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


def test_experiments_cli_compare_work(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_pipeline(
        run_id="cli-compare-base",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )
    run_pipeline(
        run_id="cli-compare-candidate",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.experiments",
            "--experiments-dir",
            "experiments",
            "compare",
            "cli-compare-base",
            "cli-compare-candidate",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert payload["base_run_id"] == "cli-compare-base"
    assert payload["candidate_run_id"] == "cli-compare-candidate"
    assert payload["winner"] == "tie"
    assert payload["recommendation"] == "keep_base"


def test_experiments_cli_champion_and_promote_work(tmp_path: Path) -> None:
    repo = copy_repo_fixture(tmp_path)
    run_pipeline(
        run_id="cli-champion-base",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )
    run_pipeline(
        run_id="cli-champion-candidate",
        experiments_dir=repo / "experiments",
        config_path=repo / "config/default.json",
        repo_root=repo,
    )
    make_run_accepted_with_ev_lift(
        repo=repo,
        run_id="cli-champion-candidate",
        ev_lift=0.2,
    )

    missing_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.experiments",
            "--experiments-dir",
            "experiments",
            "champion",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    promote_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.experiments",
            "--experiments-dir",
            "experiments",
            "promote",
            "cli-champion-base",
            "cli-champion-candidate",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    champion_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.experiments",
            "--experiments-dir",
            "experiments",
            "champion",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert missing_result.returncode == 0, missing_result.stderr
    assert promote_result.returncode == 0, promote_result.stderr
    assert champion_result.returncode == 0, champion_result.stderr
    assert json.loads(missing_result.stdout)["exists"] is False
    assert json.loads(promote_result.stdout)["promoted"] is True
    champion = json.loads(champion_result.stdout)
    assert champion["exists"] is True
    assert champion["champion"]["champion_run_id"] == "cli-champion-candidate"


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
        limit=20,
    )
    stats = agent_result_stats(
        run_id="cli-candidates",
        experiments_dir=repo / "experiments",
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
    stats_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.experiments",
            "--experiments-dir",
            "experiments",
            "agents",
            "cli-candidates",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert rows
    assert rows[0]["run_id"] == "cli-candidates"
    assert rows[0]["selected"] is True
    assert stats["from_artifact"] is True
    assert stats["totals"]["attempt_count"] == len(rows)
    assert stats["agents"][0]["top_failure_code"] == "policy_ev_improvement_low"
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["run_id"] == "cli-candidates"
    assert "probe_ev_delta" in payload[0]
    assert stats_result.returncode == 0, stats_result.stderr
    stats_payload = json.loads(stats_result.stdout)
    assert stats_payload["schema_version"] == "agent_result_stats_v1"
    assert stats_payload["agents"][0]["key"] == "strategy_modifier_stub"


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

    profiled_workspace = create_isolated_workspace(
        repo_root=repo,
        workspace_root=repo / "workspaces",
        run_id="run-2",
        round_id="round_001",
        attempt_id="attempt_001_primary",
        profile_name="Strategy Bot / Primary",
    )
    assert (
        repo
        / "workspaces/run-2/round_001/Strategy_Bot_Primary/attempt_001_primary/strategy_workspace"
    ) == profiled_workspace
    assert (profiled_workspace / "strategies/current_strategy.py").exists()


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
    assert proposal.summary == "Codex output produced a strategy patch."
    assert proposal.risk_notes == "Patch targets are checked before git apply."
    assert proposal.direction_tag == "codex_cli_unknown"
    assert proposal.patch_diff.startswith("--- a/strategies/current_strategy.py")
    assert proposal.workspace_path == str(workspace)
    assert validate_proposal_contract(
        proposal=proposal,
        expected_target_file=Path("strategies/current_strategy.py"),
        expected_round_index=1,
    ) == ()


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
