"""Validate experiment artifacts and agent contract files."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.schema_validation import validate_json_file


SINGLE_RUN_REQUIRED_FILES = (
    "metrics_before.json",
    "metrics_after.json",
    "report_before.md",
    "report_after.md",
    "summary.md",
    "decision.json",
    "patch.diff",
    "trades_before.csv",
    "trades_after.csv",
)

ITERATION_RUN_REQUIRED_FILES = (
    "manifest.json",
    "summary.md",
    "candidate_leaderboard.json",
    "codex_cli_execution_preflight.json",
    "codex_cli_execution_preflight.md",
    "agent_activation_preflight.json",
    "agent_activation_preflight.md",
)

ROUND_REQUIRED_FILES = (
    "train_metrics_before.json",
    "train_report_before.md",
    "train_trades_before.csv",
    "metrics_before.json",
    "report_before.md",
    "trades_before.csv",
    "holdout_metrics_before.json",
    "holdout_report_before.md",
    "holdout_trades_before.csv",
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
    "visual_artifacts_manifest.json",
    "chart.html",
    "trade_timeline.html",
    "visual_review.json",
    "visual_review.md",
    "agent_execution_plan.json",
    "agent_execution_plan.md",
    "agent_input.json",
    "agent_bundle_manifest.json",
    "agent_output.json",
    "agent_validation.json",
    "agent_output_quarantine.json",
    "agent_output_quarantine.md",
    "agent_executor_report.json",
    "agent_routing_policy.json",
    "agent_attempts_manifest.json",
    "agent_selection_report.json",
    "proposal_attempts.json",
    "proposal.json",
    "raw_agent_output.txt",
    "agent_response.txt",
    "patch.diff",
    "train_metrics_after.json",
    "train_report_after.md",
    "train_trades_after.csv",
    "metrics_after.json",
    "report_after.md",
    "trades_after.csv",
    "holdout_metrics_after.json",
    "holdout_report_after.md",
    "holdout_trades_after.csv",
    "decision.json",
    "overfit_validation.json",
    "overfit_validation.md",
    "agent_role_readiness.json",
    "agent_role_readiness.md",
)


def validate_run_artifacts(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return a deterministic validation report for one experiment run."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    run_dir = experiments_dir / run_id
    report: dict[str, object] = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "kind": "unknown",
        "ok": False,
        "errors": [],
        "warnings": [],
        "checked_files": [],
        "rounds_checked": 0,
    }

    if not run_dir.exists():
        add_error(report, f"run directory does not exist: {run_dir}")
        return report

    if (run_dir / "manifest.json").exists():
        report["kind"] = "iteration_loop"
        validate_iteration_run(run_dir=run_dir, repo_root=repo_root, report=report)
    elif (run_dir / "decision.json").exists():
        report["kind"] = "single_run"
        validate_required_files(
            base_dir=run_dir,
            filenames=SINGLE_RUN_REQUIRED_FILES,
            report=report,
        )
        validate_json_object(path=run_dir / "decision.json", report=report)
    elif (run_dir / "codex_cli_operator_unlock_request.json").exists():
        report["kind"] = "codex_cli_operator_unlock_request"
    elif (run_dir / "codex_cli_readiness_pipeline.json").exists():
        report["kind"] = "codex_cli_readiness_pipeline"
    elif (run_dir / "codex_cli_readiness_summary.json").exists():
        report["kind"] = "codex_cli_readiness_summary"
    elif (run_dir / "codex_cli_real_execution_dry_run.json").exists():
        report["kind"] = "codex_cli_real_execution_dry_run"
    elif (run_dir / "codex_cli_execution_candidate.json").exists():
        report["kind"] = "codex_cli_execution_candidate"
    elif (run_dir / "codex_cli_execution_unlock_snapshot.json").exists():
        report["kind"] = "codex_cli_execution_unlock_snapshot"
    elif (run_dir / "codex_cli_execution_unlock_gate.json").exists():
        report["kind"] = "codex_cli_execution_unlock_gate"
    elif (run_dir / "codex_cli_real_preflight.json").exists():
        report["kind"] = "codex_cli_real_preflight"
    elif (run_dir / "codex_cli_dry_invocation_guard.json").exists():
        report["kind"] = "codex_cli_dry_invocation_guard"
    else:
        add_error(report, "run has neither manifest.json nor decision.json")

    validate_optional_diagnosis(run_dir=run_dir, report=report)
    validate_optional_metadata(run_dir=run_dir, repo_root=repo_root, report=report)
    validate_optional_champion_comparison(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_champion_registry(
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_champion_lineage(
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_research_brief(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_experiment_scope_health(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_candidate_challenger_report(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_champion_promotion_dry_run(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_champion_promotion_approval(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_champion_promotion_receipt(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_run_closeout(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_agent_slot_health(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_agent_slot_readiness_gate(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_external_agent_sandbox_drill(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_codex_cli_replay_gate(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_codex_cli_execution_preflight(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_codex_cli_enablement_gate(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_codex_cli_manual_approval(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_codex_cli_canary_gate(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_codex_cli_real_preflight(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_codex_cli_dry_invocation_guard(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_codex_cli_execution_unlock_gate(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_codex_cli_execution_unlock_snapshot(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_codex_cli_execution_candidate(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_codex_cli_real_execution_dry_run(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_codex_cli_readiness_summary(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_codex_cli_readiness_pipeline(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_codex_cli_operator_unlock_request(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    report["ok"] = not report["errors"]
    return report


def validate_iteration_run(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate an iteration-loop run directory."""
    validate_required_files(
        base_dir=run_dir,
        filenames=ITERATION_RUN_REQUIRED_FILES,
        report=report,
    )
    manifest = load_json_object(run_dir / "manifest.json", report)
    if manifest is None:
        return

    candidate_rows = validate_json_list(
        path=run_dir / "candidate_leaderboard.json",
        report=report,
    )
    validate_candidate_leaderboard_quality(
        rows=candidate_rows,
        report=report,
    )
    validate_contract_file(
        payload_path=run_dir / "agent_activation_preflight.json",
        schema_path=repo_root / "schemas/agent_activation_preflight.schema.json",
        report=report,
    )
    validate_agent_activation_preflight(
        path=run_dir / "agent_activation_preflight.json",
        report=report,
    )
    validate_optional_agent_result_stats(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    round_ids = round_ids_from_manifest(manifest)
    if not round_ids:
        add_error(report, "manifest.rounds is empty or invalid")
        return

    for round_id in round_ids:
        round_dir = run_dir / round_id
        validate_round_dir(round_dir=round_dir, repo_root=repo_root, report=report)
    report["rounds_checked"] = len(round_ids)


def validate_candidate_leaderboard_quality(
    *,
    rows: list[Any] | None,
    report: dict[str, object],
) -> None:
    """Validate candidate leaderboard quality metadata when rows are present."""
    if rows is None:
        return
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            add_error(report, f"candidate_leaderboard row {index} is not an object")
            continue
        quality = row.get("quality_breakdown", {})
        if not isinstance(quality, dict):
            add_error(report, f"candidate_leaderboard row {index} quality invalid")
            continue
        if quality.get("schema_version") != "candidate_quality_v1":
            add_error(report, f"candidate_leaderboard row {index} quality schema invalid")
        if quality.get("total_score") != row.get("candidate_score"):
            add_error(report, f"candidate_leaderboard row {index} quality score mismatch")
        components = quality.get("components", [])
        if not isinstance(components, list):
            add_error(report, f"candidate_leaderboard row {index} quality components invalid")
        signals = quality.get("signals", {})
        if not isinstance(signals, dict):
            add_error(report, f"candidate_leaderboard row {index} quality signals invalid")
            continue
        if row.get("selected") is True:
            for key in ("validation_ev_delta", "holdout_ev_delta"):
                if row.get(key) is None:
                    add_error(
                        report,
                        f"candidate_leaderboard selected row {index} missing {key}",
                    )
                if signals.get(key) != row.get(key):
                    add_error(
                        report,
                        f"candidate_leaderboard selected row {index} signal mismatch: {key}",
                    )


def validate_round_dir(
    *,
    round_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate one iteration round directory."""
    if not round_dir.exists():
        add_error(report, f"round directory does not exist: {round_dir}")
        return

    validate_required_files(
        base_dir=round_dir,
        filenames=ROUND_REQUIRED_FILES,
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "proposal_intent.json",
        schema_path=repo_root / "schemas/proposal_intent.schema.json",
        report=report,
    )
    validate_proposal_intent_trace(
        path=round_dir / "proposal_intent.json",
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_input.json",
        schema_path=repo_root / "schemas/agent_input.schema.json",
        report=report,
    )
    validate_agent_input_search_space(
        path=round_dir / "agent_input.json",
        repo_root=repo_root,
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_output_quarantine.json",
        schema_path=repo_root / "schemas/agent_output_quarantine.schema.json",
        report=report,
    )
    validate_agent_output_quarantine(
        path=round_dir / "agent_output_quarantine.json",
        repo_root=repo_root,
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_role_contracts.json",
        schema_path=repo_root / "schemas/agent_role_contracts.schema.json",
        report=report,
    )
    role_names = validate_agent_role_contracts(
        path=round_dir / "agent_role_contracts.json",
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "analysis_notes.json",
        schema_path=repo_root / "schemas/analysis_notes.schema.json",
        report=report,
    )
    validate_analysis_notes(
        path=round_dir / "analysis_notes.json",
        repo_root=repo_root,
        role_names=role_names,
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "visual_artifacts_manifest.json",
        schema_path=repo_root / "schemas/visual_artifacts_manifest.schema.json",
        report=report,
    )
    validate_visual_artifacts_manifest(
        path=round_dir / "visual_artifacts_manifest.json",
        repo_root=repo_root,
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "visual_review.json",
        schema_path=repo_root / "schemas/visual_review.schema.json",
        report=report,
    )
    validate_chart_html(path=round_dir / "chart.html", report=report)
    validate_trade_timeline_html(
        path=round_dir / "trade_timeline.html",
        report=report,
    )
    validate_visual_review(
        path=round_dir / "visual_review.json",
        repo_root=repo_root,
        role_names=role_names,
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_bundle_manifest.json",
        schema_path=repo_root / "schemas/agent_bundle.schema.json",
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_execution_plan.json",
        schema_path=repo_root / "schemas/agent_execution_plan.schema.json",
        report=report,
    )
    validate_agent_execution_plan(
        path=round_dir / "agent_execution_plan.json",
        repo_root=repo_root,
        role_names=role_names,
        report=report,
    )
    validate_agent_bundle_manifest(
        path=round_dir / "agent_bundle_manifest.json",
        repo_root=repo_root,
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_output.json",
        schema_path=repo_root / "schemas/agent_output.schema.json",
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_validation.json",
        schema_path=repo_root / "schemas/agent_validation.schema.json",
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_executor_report.json",
        schema_path=repo_root / "schemas/agent_executor.schema.json",
        report=report,
    )
    validate_agent_executor_report(
        path=round_dir / "agent_executor_report.json",
        repo_root=repo_root,
        role_names=role_names,
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_routing_policy.json",
        schema_path=repo_root / "schemas/agent_routing_policy.schema.json",
        report=report,
    )
    validate_agent_routing_policy(
        path=round_dir / "agent_routing_policy.json",
        repo_root=repo_root,
        role_names=role_names,
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_attempts_manifest.json",
        schema_path=repo_root / "schemas/agent_attempts.schema.json",
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_selection_report.json",
        schema_path=repo_root / "schemas/agent_selection.schema.json",
        report=report,
    )
    validate_agent_attempts_manifest(
        path=round_dir / "agent_attempts_manifest.json",
        repo_root=repo_root,
        report=report,
    )
    validate_agent_selection_report(
        path=round_dir / "agent_selection_report.json",
        repo_root=repo_root,
        report=report,
    )
    round_replay_path = round_dir / "round_replay.json"
    if round_replay_path.exists():
        checked_files(report).append(str(round_replay_path))
        validate_contract_file(
            payload_path=round_replay_path,
            schema_path=repo_root / "schemas/round_replay.schema.json",
            report=report,
        )
        validate_round_replay(
            path=round_replay_path,
            repo_root=repo_root,
            report=report,
        )
    round_replay_markdown_path = round_dir / "round_replay.md"
    if round_replay_markdown_path.exists():
        checked_files(report).append(str(round_replay_markdown_path))
    golden_replay_path = round_dir / "agent_golden_replay.json"
    if golden_replay_path.exists():
        checked_files(report).append(str(golden_replay_path))
        validate_contract_file(
            payload_path=golden_replay_path,
            schema_path=repo_root / "schemas/agent_golden_replay.schema.json",
            report=report,
        )
        validate_agent_golden_replay(
            path=golden_replay_path,
            repo_root=repo_root,
            report=report,
        )
    golden_replay_markdown_path = round_dir / "agent_golden_replay.md"
    if golden_replay_markdown_path.exists():
        checked_files(report).append(str(golden_replay_markdown_path))
    codex_fixture_path = round_dir / "codex_cli_contract_fixture.json"
    if codex_fixture_path.exists():
        checked_files(report).append(str(codex_fixture_path))
        validate_contract_file(
            payload_path=codex_fixture_path,
            schema_path=repo_root / "schemas/codex_cli_contract_fixture.schema.json",
            report=report,
        )
        validate_codex_cli_contract_fixture(
            path=codex_fixture_path,
            repo_root=repo_root,
            report=report,
        )
    codex_fixture_markdown_path = round_dir / "codex_cli_contract_fixture.md"
    if codex_fixture_markdown_path.exists():
        checked_files(report).append(str(codex_fixture_markdown_path))

    proposal = load_json_object(round_dir / "proposal.json", report)
    if proposal and proposal.get("agent_name") in {"file_protocol_agent", "codex_cli"}:
        validate_required_files(
            base_dir=round_dir,
            filenames=("agent_execution.json",),
            report=report,
        )
        validate_contract_file(
            payload_path=round_dir / "agent_execution.json",
            schema_path=repo_root / "schemas/agent_execution.schema.json",
            report=report,
        )
        validate_agent_execution(
            path=round_dir / "agent_execution.json",
            run_dir=round_dir.parent,
            repo_root=repo_root,
            report=report,
        )
    elif (round_dir / "agent_execution.json").exists():
        add_warning(report, f"unexpected agent_execution.json in {round_dir}")
        validate_contract_file(
            payload_path=round_dir / "agent_execution.json",
            schema_path=repo_root / "schemas/agent_execution.schema.json",
            report=report,
        )
        validate_agent_execution(
            path=round_dir / "agent_execution.json",
            run_dir=round_dir.parent,
            repo_root=repo_root,
            report=report,
        )
    for execution_path in sorted((round_dir / "agent_executions").glob("*.json")):
        checked_files(report).append(str(execution_path))
        validate_contract_file(
            payload_path=execution_path,
            schema_path=repo_root / "schemas/agent_execution.schema.json",
            report=report,
        )
        validate_agent_execution(
            path=execution_path,
            run_dir=round_dir.parent,
            repo_root=repo_root,
            report=report,
        )

    validate_json_object(path=round_dir / "decision.json", report=report)
    validate_contract_file(
        payload_path=round_dir / "overfit_validation.json",
        schema_path=repo_root / "schemas/overfit_validation.schema.json",
        report=report,
    )
    validate_overfit_validation(
        path=round_dir / "overfit_validation.json",
        repo_root=repo_root,
        role_names=role_names,
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_role_readiness.json",
        schema_path=repo_root / "schemas/agent_role_readiness.schema.json",
        report=report,
    )
    validate_agent_role_readiness(
        path=round_dir / "agent_role_readiness.json",
        repo_root=repo_root,
        role_names=role_names,
        report=report,
    )
    proposal_attempts = validate_json_list(
        path=round_dir / "proposal_attempts.json",
        report=report,
    )
    validate_attempt_agent_roles(
        payload_name="proposal_attempts.json",
        attempts=proposal_attempts,
        role_names=role_names,
        report=report,
    )
    validate_optional_workspace_manifest(
        round_dir=round_dir,
        repo_root=repo_root,
        proposal=proposal,
        report=report,
    )


def validate_agent_execution(
    *,
    path: Path,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate one saved external agent execution audit."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    command = payload.get("command", [])
    if not isinstance(command, list):
        add_error(report, f"agent_execution command invalid: {path}")
        return
    expected_command_sha256 = stable_json_digest(command)
    if payload.get("command_sha256") != expected_command_sha256:
        add_error(report, f"agent_execution command sha256 mismatch: {path}")
    if str(payload.get("runner_name", "")) != "codex_cli_guarded_adapter":
        return
    if str(payload.get("adapter_name", "")) != "codex_cli":
        add_error(report, f"codex_cli agent_execution adapter invalid: {path}")
    preflight_path = run_dir / "codex_cli_execution_preflight.json"
    preflight = load_json_object(preflight_path, report)
    if not isinstance(preflight, dict):
        add_error(report, f"codex_cli agent_execution preflight missing: {path}")
        return
    profiles = preflight.get("profiles", [])
    if not isinstance(profiles, list):
        add_error(report, f"codex_cli execution preflight profiles invalid: {path}")
        return
    profile_name = str(payload.get("profile_name", ""))
    matching_profiles = [
        profile
        for profile in profiles
        if isinstance(profile, dict)
        and str(profile.get("profile_name", "")) == profile_name
        and str(profile.get("adapter_name", "")) == "codex_cli"
    ]
    if not matching_profiles:
        add_error(report, f"codex_cli agent_execution preflight profile missing: {path}")
        return
    expected_execution = matching_profiles[0].get("expected_execution", {})
    if not isinstance(expected_execution, dict):
        add_error(report, f"codex_cli preflight expected execution invalid: {path}")
        return
    expected_command = expected_execution.get("command", [])
    if command != expected_command:
        add_error(report, f"codex_cli agent_execution command not preflight-bound: {path}")
    if payload.get("command_sha256") != expected_execution.get("command_sha256"):
        add_error(
            report,
            f"codex_cli agent_execution command sha256 not preflight-bound: {path}",
        )


def validate_agent_input_search_space(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate saved agent input strategy-search-space authority policy."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    validate_agent_input_proposal_intent_summary(
        payload=payload,
        path=path,
        repo_root=repo_root,
        report=report,
    )
    search_space = payload.get("strategy_search_space", {})
    if not isinstance(search_space, dict):
        add_error(report, f"agent_input.json strategy_search_space invalid: {path}")
        return
    directions = search_space.get("directions", [])
    if not isinstance(directions, list) or not directions:
        add_error(report, f"agent_input.json strategy_search_space directions empty: {path}")
    direction_tags = {
        str(direction.get("direction_tag", ""))
        for direction in directions
        if isinstance(direction, dict)
        and str(direction.get("direction_tag", ""))
    }
    validate_agent_input_profile_directions(
        payload=payload,
        direction_tags=direction_tags,
        path=path,
        report=report,
    )
    policy = search_space.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, f"agent_input.json strategy_search_space policy invalid: {path}")
        return
    for key in (
        "advisory_only",
        "does_not_route_agents",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            add_error(report, f"agent_input.json strategy_search_space policy false: {key}")


def validate_agent_input_proposal_intent_summary(
    *,
    payload: dict[str, object],
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate compact proposal-intent summary exposed in agent input."""
    summary = payload.get("proposal_intent_summary", {})
    if not validate_proposal_intent_summary_contract(
        summary=summary,
        artifact_name="agent_input.json",
        report=report,
    ):
        return
    recommended = str(summary.get("recommended_direction", ""))
    candidate_order = string_values(summary.get("candidate_order", []))
    artifacts = payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return
    intent_path_text = str(artifacts.get("proposal_intent_json", ""))
    if not intent_path_text:
        return
    intent_path = resolve_path(Path(intent_path_text), repo_root)
    intent = load_json_object(intent_path, report)
    if intent is None:
        return
    trace = intent.get("direction_decision_trace", {})
    if not isinstance(trace, dict):
        return
    if str(intent.get("recommended_direction", "")) != recommended:
        add_error(report, f"agent_input.json proposal intent recommendation drift: {path}")
    if str(trace.get("selection_reason_code", "")) != str(
        summary.get("selection_reason_code", "")
    ):
        add_error(report, f"agent_input.json proposal intent reason drift: {path}")
    if string_values(trace.get("candidate_order", [])) != candidate_order:
        add_error(report, f"agent_input.json proposal intent order drift: {path}")


def validate_proposal_intent_summary_contract(
    *,
    summary: object,
    artifact_name: str,
    report: dict[str, object],
) -> bool:
    """Validate compact proposal-intent summary shape and authority policy."""
    if not isinstance(summary, dict):
        add_error(report, f"{artifact_name} proposal_intent_summary invalid")
        return False
    if summary.get("schema_version") != "proposal_intent_summary_v1":
        add_error(report, f"{artifact_name} proposal_intent_summary schema mismatch")
    recommended = str(summary.get("recommended_direction", ""))
    selected = str(summary.get("selected_direction", ""))
    if recommended != selected:
        add_error(report, f"{artifact_name} proposal intent summary direction mismatch")
    candidate_order = string_values(summary.get("candidate_order", []))
    candidate_rows = summary.get("candidate_rows", [])
    if not isinstance(candidate_rows, list):
        add_error(report, f"{artifact_name} proposal intent candidate rows invalid")
        candidate_rows = []
    row_directions: list[str] = []
    selected_rows = 0
    for index, row in enumerate(candidate_rows, start=1):
        if not isinstance(row, dict):
            add_error(report, f"{artifact_name} proposal intent candidate row invalid")
            continue
        row_directions.append(str(row.get("direction_tag", "")))
        if row.get("rank") != index:
            add_error(report, f"{artifact_name} proposal intent candidate rank mismatch")
        if bool(row.get("selected", False)):
            selected_rows += 1
            if str(row.get("direction_tag", "")) != selected:
                add_error(report, f"{artifact_name} proposal intent selected row mismatch")
    if row_directions != candidate_order:
        add_error(report, f"{artifact_name} proposal intent candidate order mismatch")
    if selected in row_directions and selected_rows != 1:
        add_error(report, f"{artifact_name} proposal intent selected row count invalid")
    policy = summary.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, f"{artifact_name} proposal intent summary policy invalid")
    else:
        for key in ("advisory_only", "does_not_route_agents", "does_not_change_acceptance"):
            if policy.get(key) is not True:
                add_error(report, f"{artifact_name} proposal intent summary policy false: {key}")
    return True


def validate_proposal_intent_trace(*, path: Path, report: dict[str, object]) -> None:
    """Validate planner direction-decision trace authority and consistency."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    trace = payload.get("direction_decision_trace", {})
    if not isinstance(trace, dict):
        add_error(report, f"proposal_intent.json direction_decision_trace invalid: {path}")
        return
    if trace.get("schema_version") != "direction_decision_trace_v1":
        add_error(report, "proposal_intent.json direction_decision_trace schema mismatch")
    recommended = str(payload.get("recommended_direction", ""))
    if str(trace.get("selected_direction", "")) != recommended:
        add_error(report, "proposal_intent.json direction trace selected direction mismatch")
    candidate_order = trace.get("candidate_order", [])
    candidate_rows = trace.get("candidate_rows", [])
    if not isinstance(candidate_order, list) or not isinstance(candidate_rows, list):
        add_error(report, "proposal_intent.json direction trace candidates invalid")
        return
    row_directions: list[str] = []
    selected_rows = 0
    for index, row in enumerate(candidate_rows, start=1):
        if not isinstance(row, dict):
            add_error(report, f"proposal_intent.json direction trace row invalid: {index}")
            continue
        row_directions.append(str(row.get("direction_tag", "")))
        if row.get("rank") != index:
            add_error(report, f"proposal_intent.json direction trace rank mismatch: {index}")
        selected = bool(row.get("selected", False))
        if selected:
            selected_rows += 1
            if str(row.get("direction_tag", "")) != recommended:
                add_error(report, "proposal_intent.json direction trace selected row mismatch")
    if row_directions != [str(direction) for direction in candidate_order]:
        add_error(report, "proposal_intent.json direction trace order mismatch")
    if recommended in row_directions and selected_rows != 1:
        add_error(report, "proposal_intent.json direction trace selected row count invalid")
    policy = trace.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "proposal_intent.json direction trace policy invalid")
        return
    for key in ("advisory_only", "does_not_route_agents", "does_not_change_acceptance"):
        if policy.get(key) is not True:
            add_error(report, f"proposal_intent.json direction trace policy false: {key}")


def validate_agent_input_profile_directions(
    *,
    payload: dict[str, object],
    direction_tags: set[str],
    path: Path,
    report: dict[str, object],
) -> None:
    """Validate profile direction capabilities exposed to agents."""
    profiles = payload.get("agent_profiles", [])
    if not isinstance(profiles, list):
        add_error(report, f"agent_input.json agent_profiles invalid: {path}")
        return
    for index, profile in enumerate(profiles, start=1):
        if not isinstance(profile, dict):
            add_error(report, f"agent_input.json agent_profiles[{index}] invalid: {path}")
            continue
        supported = profile.get("supported_directions", [])
        if not isinstance(supported, list) or not supported:
            add_error(
                report,
                f"agent_input.json agent_profiles[{index}].supported_directions empty: {path}",
            )
            continue
        normalized = [str(direction) for direction in supported if str(direction)]
        if "*" in normalized:
            if normalized != ["*"]:
                add_error(
                    report,
                    "agent_input.json supported_directions wildcard must stand alone: "
                    f"{path}",
                )
            continue
        for direction in normalized:
            if direction not in direction_tags:
                add_error(
                    report,
                    "agent_input.json supported_directions unknown direction "
                    f"{direction}: {path}",
                )


def validate_optional_workspace_manifest(
    *,
    round_dir: Path,
    repo_root: Path,
    proposal: dict[str, Any] | None,
    report: dict[str, object],
) -> None:
    """Validate workspace_manifest.json for workspace-backed agent rounds."""
    path = round_dir / "workspace_manifest.json"
    has_workspace = bool(proposal and proposal.get("workspace_path"))
    if not path.exists():
        if has_workspace:
            add_error(report, f"missing required workspace manifest: {path}")
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/workspace_manifest.schema.json",
        report=report,
    )


def validate_agent_bundle_manifest(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate bundle dirs and listed files exist."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    for key in ("input_bundle_dir", "output_bundle_dir"):
        bundle_dir = resolve_path(Path(str(payload.get(key, ""))), repo_root)
        if not bundle_dir.exists() or not bundle_dir.is_dir():
            add_error(report, f"{key} does not exist: {bundle_dir}")
    for key in ("input_files", "output_files"):
        rows = payload.get(key, [])
        if not isinstance(rows, list) or not rows:
            add_error(report, f"agent_bundle_manifest.json {key} is empty or invalid")
            continue
        for row in rows:
            if not isinstance(row, dict):
                add_error(report, f"agent_bundle_manifest.json {key} contains non-object")
                continue
            file_path = resolve_path(Path(str(row.get("path", ""))), repo_root)
            if not file_path.exists() or not file_path.is_file():
                add_error(report, f"bundle file does not exist: {file_path}")


def validate_agent_output_quarantine(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate the pre-apply quarantine report for one selected output."""
    del repo_root
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    release_to_apply = bool(payload.get("release_to_apply", False))
    status = str(payload.get("quarantine_status", ""))
    blockers = payload.get("blocking_reasons", [])
    if not isinstance(blockers, list):
        add_error(report, f"agent_output_quarantine blocking_reasons invalid: {path}")
        return
    if release_to_apply and blockers:
        add_error(report, f"agent_output_quarantine released with blockers: {path}")
    if release_to_apply and status != "released":
        add_error(report, f"agent_output_quarantine release/status mismatch: {path}")
    if not release_to_apply and status == "released":
        add_error(report, f"agent_output_quarantine status released but blocked: {path}")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, f"agent_output_quarantine policy invalid: {path}")
        return
    for key in (
        "quarantine_before_git_apply",
        "does_not_execute_agents",
        "does_not_apply_patch",
        "release_requires_agent_validation_ok",
        "release_requires_applicable_patch",
        "release_requires_git_apply_check_passed",
        "deterministic_policy_gate_keeps_acceptance_authority",
    ):
        if not bool(policy.get(key, False)):
            add_error(report, f"agent_output_quarantine policy false: {key}")


def validate_agent_activation_preflight(
    *,
    path: Path,
    report: dict[str, object],
) -> None:
    """Validate run-level agent activation preflight boundaries."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if not bool(payload.get("ok", False)):
        add_error(report, "agent_activation_preflight.json must be ok")
    blocking_errors = payload.get("blocking_errors", [])
    if not isinstance(blocking_errors, list):
        add_error(report, "agent_activation_preflight.json blocking_errors invalid")
    elif blocking_errors:
        add_error(report, "agent_activation_preflight.json has blocking errors")
    roles = payload.get("roles", [])
    if not isinstance(roles, list) or not roles:
        add_error(report, "agent_activation_preflight.json roles is empty or invalid")
    else:
        executable_roles = [
            str(role.get("role_name", ""))
            for role in roles
            if isinstance(role, dict)
            and bool(role.get("can_execute_in_v0_5", False))
        ]
        if executable_roles != ["strategy_modifier"]:
            add_error(
                report,
                "agent_activation_preflight.json only strategy_modifier may execute",
            )
    profiles = payload.get("profiles", [])
    if not isinstance(profiles, list) or not profiles:
        add_error(report, "agent_activation_preflight.json profiles is empty or invalid")
    else:
        enabled_primary_count = 0
        for profile in profiles:
            if not isinstance(profile, dict):
                add_error(report, "agent_activation_preflight.json profile non-object")
                continue
            enabled = bool(profile.get("enabled", False))
            if enabled and profile.get("queue_role") == "primary":
                enabled_primary_count += 1
            if enabled and profile.get("agent_role") != "strategy_modifier":
                add_error(
                    report,
                    "agent_activation_preflight.json enabled non-strategy profile: "
                    f"{profile.get('profile_name', '')}",
                )
            if enabled and profile.get("activation_status") != "ready":
                add_error(
                    report,
                    "agent_activation_preflight.json enabled profile is not ready: "
                    f"{profile.get('profile_name', '')}",
                )
        if enabled_primary_count != 1:
            add_error(
                report,
                "agent_activation_preflight.json must have one enabled primary",
            )
    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        add_error(report, "agent_activation_preflight.json summary is invalid")
    else:
        if summary.get("blocked_enabled_profiles") not in ([], None):
            add_error(
                report,
                "agent_activation_preflight.json blocked enabled profiles present",
            )
        if summary.get("enabled_primary_count") != 1:
            add_error(
                report,
                "agent_activation_preflight.json enabled primary count mismatch",
            )
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "agent_activation_preflight.json policy is invalid")
    else:
        if not bool(policy.get("only_strategy_modifier_executes_in_v0_5", False)):
            add_error(
                report,
                "agent_activation_preflight.json must preserve strategy-only execution",
            )
        if bool(policy.get("activation_preflight_can_change_acceptance", True)):
            add_error(
                report,
                "agent_activation_preflight.json must not change acceptance",
            )
        if bool(policy.get("activation_preflight_can_change_routing", True)):
            add_error(
                report,
                "agent_activation_preflight.json must not change routing",
            )


def validate_agent_execution_plan(
    *,
    path: Path,
    repo_root: Path,
    role_names: set[str],
    report: dict[str, object],
) -> None:
    """Validate the pre-execution queue plan for one round."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    attempts = payload.get("attempts", [])
    if not isinstance(attempts, list) or not attempts:
        add_error(report, "agent_execution_plan.json attempts is empty or invalid")
        return
    if payload.get("queue_count") != len(attempts):
        add_error(report, "agent_execution_plan.json queue_count mismatch")
    plan_summary = payload.get("proposal_intent_summary", {})
    validate_proposal_intent_summary_contract(
        summary=plan_summary,
        artifact_name="agent_execution_plan.json",
        report=report,
    )
    attempt_ids: set[str] = set()
    primary_count = 0
    for attempt in attempts:
        if not isinstance(attempt, dict):
            add_error(report, "agent_execution_plan.json attempt is non-object")
            continue
        attempt_id = str(attempt.get("attempt_id", ""))
        if attempt_id in attempt_ids:
            add_error(
                report,
                f"agent_execution_plan.json duplicate attempt_id: {attempt_id}",
            )
        attempt_ids.add(attempt_id)
        if str(attempt.get("queue_role", "")) == "primary":
            primary_count += 1
        agent_role = str(attempt.get("agent_role", ""))
        if role_names and agent_role not in role_names:
            add_error(
                report,
                f"agent_execution_plan.json unknown agent_role: {agent_role}",
            )
        if agent_role != "strategy_modifier":
            add_error(
                report,
                "agent_execution_plan.json only strategy_modifier may be planned: "
                f"{agent_role}",
            )
        validate_execution_plan_direction_capability(
            attempt=attempt,
            report=report,
        )
        validate_execution_plan_input_contract(
            attempt=attempt,
            plan_summary=plan_summary,
            repo_root=repo_root,
            report=report,
        )
        validate_execution_plan_workspace(attempt=attempt, report=report)
        validate_execution_plan_output(attempt=attempt, report=report)
    if primary_count != 1:
        add_error(report, "agent_execution_plan.json must contain one primary attempt")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "agent_execution_plan.json policy is invalid")
    else:
        for key in (
            "plan_only",
            "does_not_execute_agents",
            "does_not_select_candidate",
            "acceptance_still_requires_policy_gate",
            "only_strategy_modifier_profiles_may_execute",
        ):
            if not bool(policy.get(key, False)):
                add_error(report, f"agent_execution_plan.json policy false: {key}")


def validate_execution_plan_direction_capability(
    *,
    attempt: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate planned direction capability metadata."""
    capability = attempt.get("direction_capability", {})
    if not isinstance(capability, dict):
        add_error(report, "agent_execution_plan.json direction_capability is invalid")
        return
    if capability.get("schema_version") != "direction_capability_v1":
        add_error(report, "agent_execution_plan.json direction_capability schema mismatch")
    supported = capability.get("supported_directions", [])
    if not isinstance(supported, list) or not supported:
        add_error(report, "agent_execution_plan.json supported_directions is empty")
    if capability.get("wildcard") is True and supported != ["*"]:
        add_error(report, "agent_execution_plan.json wildcard capability must be ['*']")


def validate_execution_plan_input_contract(
    *,
    attempt: dict[str, object],
    plan_summary: object,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate planned agent input paths that should exist by validation time."""
    input_contract = attempt.get("input_contract", {})
    if not isinstance(input_contract, dict):
        add_error(report, "agent_execution_plan.json input_contract invalid")
        return
    attempt_summary = input_contract.get("proposal_intent_summary", {})
    if attempt_summary != plan_summary:
        add_error(report, "agent_execution_plan.json input summary not plan-bound")
    validate_proposal_intent_summary_contract(
        summary=attempt_summary,
        artifact_name="agent_execution_plan.json input_contract",
        report=report,
    )
    for key in ("round_agent_input", "input_bundle_dir"):
        contract_path = resolve_path(Path(str(input_contract.get(key, ""))), repo_root)
        if not contract_path.exists():
            add_error(
                report,
                f"agent_execution_plan.json input contract path missing: {key}",
            )
    round_input_path = resolve_path(
        Path(str(input_contract.get("round_agent_input", ""))),
        repo_root,
    )
    round_input = load_json_object(round_input_path, report)
    if round_input is not None:
        round_summary = round_input.get("proposal_intent_summary", {})
        if round_summary != plan_summary:
            add_error(
                report,
                "agent_execution_plan.json input summary drift from agent_input",
            )


def validate_execution_plan_workspace(
    *,
    attempt: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate planned workspace contract metadata."""
    workspace = attempt.get("workspace", {})
    if not isinstance(workspace, dict):
        add_error(report, "agent_execution_plan.json workspace invalid")
        return
    workspace_required = bool(workspace.get("workspace_required", False))
    if workspace_required:
        if str(workspace.get("isolation", "")) != "workspace":
            add_error(report, "agent_execution_plan.json workspace isolation invalid")
        if not str(workspace.get("expected_workspace_path", "")):
            add_error(report, "agent_execution_plan.json workspace path missing")
        if not bool(workspace.get("mutation_guard_required", False)):
            add_error(report, "agent_execution_plan.json mutation guard required")
        allowed_paths = workspace.get("allowed_mutation_paths", [])
        if not isinstance(allowed_paths, list) or not allowed_paths:
            add_error(report, "agent_execution_plan.json allowed mutations missing")


def validate_execution_plan_output(
    *,
    attempt: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate planned output contract metadata."""
    output = attempt.get("output_contract", {})
    if not isinstance(output, dict):
        add_error(report, "agent_execution_plan.json output_contract invalid")
        return
    allowed_files = output.get("allowed_output_files", [])
    if not isinstance(allowed_files, list):
        add_error(report, "agent_execution_plan.json allowed_output_files invalid")
        return
    for filename in allowed_files:
        text = str(filename)
        if "/" in text or "\\" in text or text in {"", ".", ".."}:
            add_error(
                report,
                f"agent_execution_plan.json allowed output must be basename: {text}",
            )
    if bool(output.get("file_contract_required", False)) and not allowed_files:
        add_error(
            report,
            "agent_execution_plan.json file contract requires allowed output files",
        )


def validate_agent_role_contracts(
    *,
    path: Path,
    report: dict[str, object],
) -> set[str]:
    """Validate role uniqueness and active role references."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return set()
    roles = payload.get("roles", [])
    if not isinstance(roles, list) or not roles:
        add_error(report, "agent_role_contracts.json roles is empty or invalid")
        return set()
    role_names: set[str] = set()
    for role in roles:
        if not isinstance(role, dict):
            add_error(report, "agent_role_contracts.json roles contains non-object")
            continue
        role_name = str(role.get("role_name", ""))
        if not role_name:
            add_error(report, "agent_role_contracts.json role_name is empty")
        if role_name in role_names:
            add_error(report, f"agent_role_contracts.json duplicate role: {role_name}")
        role_names.add(role_name)
    active_roles = payload.get("active_roles", [])
    if not isinstance(active_roles, list) or not active_roles:
        add_error(report, "agent_role_contracts.json active_roles is empty or invalid")
        return set()
    for active_role in active_roles:
        if str(active_role) not in role_names:
            add_error(
                report,
                f"agent_role_contracts.json active role is missing: {active_role}",
            )
    return role_names


def validate_attempt_agent_roles(
    *,
    payload_name: str,
    attempts: list[Any] | None,
    role_names: set[str],
    report: dict[str, object],
) -> None:
    """Validate that attempt rows reference known agent roles."""
    if attempts is None or not role_names:
        return
    for index, attempt in enumerate(attempts, start=1):
        if not isinstance(attempt, dict):
            continue
        agent_role = str(attempt.get("agent_role", ""))
        if not agent_role:
            add_error(report, f"{payload_name} attempt {index} missing agent_role")
        elif agent_role not in role_names:
            add_error(
                report,
                f"{payload_name} attempt {index} unknown agent_role: {agent_role}",
            )


def validate_analysis_notes(
    *,
    path: Path,
    repo_root: Path,
    role_names: set[str],
    report: dict[str, object],
) -> None:
    """Validate the read-only analysis role stub artifact."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    agent_role = str(payload.get("agent_role", ""))
    if agent_role != "analysis":
        add_error(report, f"analysis_notes.json agent_role must be analysis: {agent_role}")
    if role_names and agent_role not in role_names:
        add_error(report, f"analysis_notes.json unknown agent_role: {agent_role}")
    recommendation = payload.get("recommendation", {})
    if not isinstance(recommendation, dict):
        add_error(report, "analysis_notes.json recommendation is invalid")
    elif bool(recommendation.get("can_change_acceptance", True)):
        add_error(report, "analysis_notes.json must not change acceptance")
    for group_key in ("consumed_artifacts", "produced_artifacts"):
        artifacts = payload.get(group_key, {})
        if not isinstance(artifacts, dict):
            add_error(report, f"analysis_notes.json {group_key} is invalid")
            continue
        for artifact_key, artifact_value in artifacts.items():
            artifact_path = resolve_path(Path(str(artifact_value)), repo_root)
            if not artifact_path.exists() or not artifact_path.is_file():
                add_error(
                    report,
                    "analysis_notes.json artifact does not exist: "
                    f"{artifact_key}={artifact_path}",
                )


def validate_overfit_validation(
    *,
    path: Path,
    repo_root: Path,
    role_names: set[str],
    report: dict[str, object],
) -> None:
    """Validate the deterministic overfit-validator stub artifact."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    agent_role = str(payload.get("agent_role", ""))
    if agent_role != "overfit_validator":
        add_error(
            report,
            f"overfit_validation.json agent_role must be overfit_validator: {agent_role}",
        )
    if role_names and agent_role not in role_names:
        add_error(report, f"overfit_validation.json unknown agent_role: {agent_role}")
    recommendation = payload.get("recommendation", {})
    if not isinstance(recommendation, dict):
        add_error(report, "overfit_validation.json recommendation is invalid")
    else:
        if bool(recommendation.get("can_veto", True)):
            add_error(report, "overfit_validation.json must not veto in V0.5")
        if bool(recommendation.get("can_change_acceptance", True)):
            add_error(report, "overfit_validation.json must not change acceptance")
    checks = payload.get("checks", {})
    if isinstance(checks, dict) and bool(checks.get("deterministic_gate_active", True)):
        add_error(report, "overfit_validation.json deterministic gate must be inactive")
    for group_key in ("consumed_artifacts", "produced_artifacts"):
        artifacts = payload.get(group_key, {})
        if not isinstance(artifacts, dict):
            add_error(report, f"overfit_validation.json {group_key} is invalid")
            continue
        for artifact_key, artifact_value in artifacts.items():
            artifact_path = resolve_path(Path(str(artifact_value)), repo_root)
            if not artifact_path.exists() or not artifact_path.is_file():
                add_error(
                    report,
                    "overfit_validation.json artifact does not exist: "
                    f"{artifact_key}={artifact_path}",
                )


def validate_agent_role_readiness(
    *,
    path: Path,
    repo_root: Path,
    role_names: set[str],
    report: dict[str, object],
) -> None:
    """Validate the round-level readiness report for future agent roles."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    roles = payload.get("roles", [])
    if not isinstance(roles, list) or not roles:
        add_error(report, "agent_role_readiness.json roles is empty or invalid")
        return
    seen_roles: set[str] = set()
    executable_roles: list[str] = []
    for role in roles:
        if not isinstance(role, dict):
            add_error(report, "agent_role_readiness.json role is non-object")
            continue
        role_name = str(role.get("role_name", ""))
        if not role_name:
            add_error(report, "agent_role_readiness.json role_name is empty")
        elif role_name in seen_roles:
            add_error(
                report,
                f"agent_role_readiness.json duplicate role: {role_name}",
            )
        seen_roles.add(role_name)
        if role_names and role_name not in role_names:
            add_error(
                report,
                f"agent_role_readiness.json unknown role: {role_name}",
            )
        executable_now = bool(role.get("executable_now", False))
        if executable_now:
            executable_roles.append(role_name)
        if role_name != "strategy_modifier" and executable_now:
            add_error(
                report,
                "agent_role_readiness.json non-strategy role cannot execute in V0.5: "
                f"{role_name}",
            )
        if str(role.get("execution_mode", "")) == "stub_contract" and executable_now:
            add_error(
                report,
                "agent_role_readiness.json stub role cannot be executable: "
                f"{role_name}",
            )
        authority = role.get("authority", {})
        if not isinstance(authority, dict):
            add_error(report, "agent_role_readiness.json role authority is invalid")
        else:
            if bool(authority.get("can_change_acceptance", True)):
                add_error(
                    report,
                    "agent_role_readiness.json role must not change acceptance: "
                    f"{role_name}",
                )
            if bool(authority.get("can_change_routing", True)):
                add_error(
                    report,
                    "agent_role_readiness.json role must not change routing: "
                    f"{role_name}",
                )
            if bool(authority.get("can_veto", True)):
                add_error(
                    report,
                    f"agent_role_readiness.json role must not veto in V0.5: {role_name}",
                )
        validate_readiness_artifact_records(
            role_name=role_name,
            group_key="consumed_artifacts",
            artifacts=role.get("consumed_artifacts", []),
            repo_root=repo_root,
            report=report,
        )
        validate_readiness_artifact_records(
            role_name=role_name,
            group_key="produced_artifacts",
            artifacts=role.get("produced_artifacts", []),
            repo_root=repo_root,
            report=report,
        )
    summary = payload.get("readiness_summary", {})
    if not isinstance(summary, dict):
        add_error(report, "agent_role_readiness.json readiness_summary is invalid")
    else:
        if summary.get("role_count") != len(roles):
            add_error(report, "agent_role_readiness.json role_count mismatch")
        if summary.get("executable_roles") != executable_roles:
            add_error(report, "agent_role_readiness.json executable_roles mismatch")
        if executable_roles != ["strategy_modifier"]:
            add_error(
                report,
                "agent_role_readiness.json only strategy_modifier should execute",
            )
        if not bool(summary.get("all_produced_artifacts_present", False)):
            add_error(
                report,
                "agent_role_readiness.json produced artifacts must be present",
            )
        if not bool(summary.get("stub_roles_have_no_execution_authority", False)):
            add_error(
                report,
                "agent_role_readiness.json stub roles must have no execution authority",
            )
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "agent_role_readiness.json policy is invalid")
    else:
        if not bool(policy.get("only_strategy_modifier_executes_in_v0_5", False)):
            add_error(
                report,
                "agent_role_readiness.json must preserve strategy-only execution",
            )
        if not bool(
            policy.get("deterministic_gates_keep_acceptance_authority", False)
        ):
            add_error(
                report,
                "agent_role_readiness.json must preserve deterministic gates",
            )
        if bool(policy.get("readiness_report_can_change_acceptance", True)):
            add_error(
                report,
                "agent_role_readiness.json report must not change acceptance",
            )
        if bool(policy.get("readiness_report_can_change_routing", True)):
            add_error(
                report,
                "agent_role_readiness.json report must not change routing",
            )


def validate_readiness_artifact_records(
    *,
    role_name: str,
    group_key: str,
    artifacts: object,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate readiness artifact path records."""
    if not isinstance(artifacts, list) or not artifacts:
        add_error(
            report,
            f"agent_role_readiness.json {role_name} {group_key} is empty or invalid",
        )
        return
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            add_error(
                report,
                f"agent_role_readiness.json {role_name} {group_key} contains non-object",
            )
            continue
        artifact_path = resolve_path(Path(str(artifact.get("path", ""))), repo_root)
        exists = bool(artifact.get("exists", False))
        if not exists:
            add_error(
                report,
                "agent_role_readiness.json artifact marked missing: "
                f"{role_name}.{group_key}.{artifact.get('name', '')}",
            )
        if not artifact_path.exists() or not artifact_path.is_file():
            add_error(
                report,
                "agent_role_readiness.json artifact does not exist: "
                f"{artifact_path}",
            )


def validate_visual_review(
    *,
    path: Path,
    repo_root: Path,
    role_names: set[str],
    report: dict[str, object],
) -> None:
    """Validate the read-only visual-review role stub artifact."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    agent_role = str(payload.get("agent_role", ""))
    if agent_role != "visual_review":
        add_error(
            report,
            f"visual_review.json agent_role must be visual_review: {agent_role}",
        )
    if role_names and agent_role not in role_names:
        add_error(report, f"visual_review.json unknown agent_role: {agent_role}")
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        add_error(report, "visual_review.json checks is invalid")
    else:
        if not bool(checks.get("chart_rendering_enabled", False)):
            add_error(report, "visual_review.json chart rendering must be enabled")
        if bool(checks.get("visual_agent_enabled", True)):
            add_error(report, "visual_review.json visual agent must be disabled")
        if not bool(checks.get("chart_file_present", False)):
            add_error(report, "visual_review.json chart file must be present")
        if not bool(checks.get("timeline_file_present", False)):
            add_error(report, "visual_review.json timeline file must be present")
        if bool(checks.get("can_change_acceptance", True)):
            add_error(report, "visual_review.json must not change acceptance")
        if bool(checks.get("can_change_routing", True)):
            add_error(report, "visual_review.json must not change routing")
    recommendation = payload.get("recommendation", {})
    if not isinstance(recommendation, dict):
        add_error(report, "visual_review.json recommendation is invalid")
    else:
        if bool(recommendation.get("can_change_acceptance", True)):
            add_error(report, "visual_review.json must not change acceptance")
        if bool(recommendation.get("can_change_routing", True)):
            add_error(report, "visual_review.json must not change routing")
    for group_key in ("consumed_artifacts", "produced_artifacts"):
        artifacts = payload.get(group_key, {})
        if not isinstance(artifacts, dict):
            add_error(report, f"visual_review.json {group_key} is invalid")
            continue
        for artifact_key, artifact_value in artifacts.items():
            artifact_path = resolve_path(Path(str(artifact_value)), repo_root)
            if not artifact_path.exists() or not artifact_path.is_file():
                add_error(
                    report,
                    "visual_review.json artifact does not exist: "
                    f"{artifact_key}={artifact_path}",
                )
    chart_artifacts = payload.get("chart_artifacts", {})
    if not isinstance(chart_artifacts, dict):
        add_error(report, "visual_review.json chart_artifacts is invalid")
        return
    if bool(chart_artifacts.get("external_dependencies", True)):
        add_error(report, "visual_review.json chart must not use external dependencies")
    chart_path = resolve_path(Path(str(chart_artifacts.get("chart_html", ""))), repo_root)
    if not chart_path.exists() or not chart_path.is_file():
        add_error(report, f"visual_review.json chart_html does not exist: {chart_path}")
    timeline_artifacts = payload.get("timeline_artifacts", {})
    if not isinstance(timeline_artifacts, dict):
        add_error(report, "visual_review.json timeline_artifacts is invalid")
        return
    if bool(timeline_artifacts.get("external_dependencies", True)):
        add_error(
            report,
            "visual_review.json timeline must not use external dependencies",
        )
    timeline_path = resolve_path(
        Path(str(timeline_artifacts.get("trade_timeline_html", ""))),
        repo_root,
    )
    if not timeline_path.exists() or not timeline_path.is_file():
        add_error(
            report,
            f"visual_review.json trade_timeline_html does not exist: {timeline_path}",
        )
    validate_visual_review_summary(payload=payload, report=report)


def validate_visual_review_summary(
    *,
    payload: dict[str, Any],
    report: dict[str, object],
) -> None:
    """Validate the manifest-derived summary in visual_review.json."""
    summary = payload.get("visual_artifacts_summary", {})
    if not isinstance(summary, dict):
        add_error(report, "visual_review.json visual_artifacts_summary is invalid")
        return
    artifacts = summary.get("artifacts", [])
    if not isinstance(artifacts, list):
        add_error(report, "visual_review.json visual_artifacts_summary artifacts invalid")
        return
    artifact_count = summary.get("artifact_count", None)
    if isinstance(artifact_count, int) and artifact_count != len(artifacts):
        add_error(report, "visual_review.json visual artifact count mismatch")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            add_error(report, "visual_review.json visual artifact summary is non-object")
            continue
        if bool(artifact.get("external_dependencies", True)):
            add_error(
                report,
                "visual_review.json visual artifact summary must not use external dependencies",
            )
        if int_value(artifact.get("source_file_count", 0)) <= 0:
            add_error(
                report,
                "visual_review.json visual artifact summary must include source files",
            )
        if not str(artifact.get("sha256_prefix", "")):
            add_error(
                report,
                "visual_review.json visual artifact summary missing sha256 prefix",
            )
    policy = summary.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "visual_review.json visual summary policy is invalid")
        return
    if bool(policy.get("external_network_assets_allowed", True)):
        add_error(report, "visual_review.json visual summary must not allow external assets")
    if bool(policy.get("visual_agent_can_change_acceptance", True)):
        add_error(report, "visual_review.json visual summary must not change acceptance")
    if bool(policy.get("visual_agent_can_change_routing", True)):
        add_error(report, "visual_review.json visual summary must not change routing")


def validate_visual_artifacts_manifest(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate the manifest that indexes visual input artifacts."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if bool(payload.get("visual_agent_enabled", True)):
        add_error(report, "visual_artifacts_manifest.json visual agent must be disabled")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "visual_artifacts_manifest.json policy is invalid")
    else:
        if bool(policy.get("external_network_assets_allowed", True)):
            add_error(
                report,
                "visual_artifacts_manifest.json must not allow external assets",
            )
        if bool(policy.get("visual_agent_can_change_acceptance", True)):
            add_error(
                report,
                "visual_artifacts_manifest.json must not change acceptance",
            )
        if bool(policy.get("visual_agent_can_change_routing", True)):
            add_error(
                report,
                "visual_artifacts_manifest.json must not change routing",
            )
    artifacts = payload.get("artifacts", [])
    if not isinstance(artifacts, list) or not artifacts:
        add_error(report, "visual_artifacts_manifest.json artifacts is empty or invalid")
        return
    artifact_ids: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            add_error(report, "visual_artifacts_manifest.json artifact is non-object")
            continue
        artifact_id = str(artifact.get("artifact_id", ""))
        if artifact_id in artifact_ids:
            add_error(
                report,
                f"visual_artifacts_manifest.json duplicate artifact_id: {artifact_id}",
            )
        artifact_ids.add(artifact_id)
        if bool(artifact.get("external_dependencies", True)):
            add_error(
                report,
                f"visual_artifacts_manifest.json artifact uses external dependencies: {artifact_id}",
            )
        artifact_path = resolve_path(Path(str(artifact.get("path", ""))), repo_root)
        if not artifact_path.exists() or not artifact_path.is_file():
            add_error(
                report,
                f"visual_artifacts_manifest.json artifact does not exist: {artifact_path}",
            )
            continue
        expected_bytes = artifact.get("bytes", None)
        if isinstance(expected_bytes, int) and expected_bytes != artifact_path.stat().st_size:
            add_error(
                report,
                f"visual_artifacts_manifest.json byte count mismatch: {artifact_path}",
            )
        expected_sha = str(artifact.get("sha256", ""))
        if expected_sha and expected_sha != file_sha256(artifact_path):
            add_error(
                report,
                f"visual_artifacts_manifest.json sha256 mismatch: {artifact_path}",
            )
        marker = str(artifact.get("schema_marker", ""))
        text = artifact_path.read_text(encoding="utf-8")
        if marker and marker not in text:
            add_error(
                report,
                f"visual_artifacts_manifest.json schema marker missing in artifact: {artifact_path}",
            )
        source_files = artifact.get("source_files", [])
        if not isinstance(source_files, list) or not source_files:
            add_error(
                report,
                f"visual_artifacts_manifest.json artifact has no source files: {artifact_id}",
            )
            continue
        for source in source_files:
            source_path = resolve_path(Path(str(source)), repo_root)
            if not source_path.exists() or not source_path.is_file():
                add_error(
                    report,
                    "visual_artifacts_manifest.json source file does not exist: "
                    f"{source_path}",
                )


def validate_chart_html(*, path: Path, report: dict[str, object]) -> None:
    """Validate the deterministic static chart artifact."""
    if not path.exists():
        return
    checked_files(report).append(str(path))
    text = path.read_text(encoding="utf-8")
    if 'name="suan-chart-schema" content="round_chart_v1"' not in text:
        add_error(report, f"chart.html missing round_chart_v1 schema marker: {path}")
    if "<svg" not in text or "</svg>" not in text:
        add_error(report, f"chart.html missing inline SVG chart: {path}")
    if "http://" in text or "https://" in text:
        add_error(report, f"chart.html must not reference external network assets: {path}")


def validate_trade_timeline_html(*, path: Path, report: dict[str, object]) -> None:
    """Validate the deterministic static trade timeline artifact."""
    if not path.exists():
        return
    checked_files(report).append(str(path))
    text = path.read_text(encoding="utf-8")
    if 'name="suan-timeline-schema" content="trade_timeline_v1"' not in text:
        add_error(
            report,
            f"trade_timeline.html missing trade_timeline_v1 schema marker: {path}",
        )
    if "<table>" not in text or "</table>" not in text:
        add_error(report, f"trade_timeline.html missing trade table: {path}")
    if "http://" in text or "https://" in text:
        add_error(
            report,
            f"trade_timeline.html must not reference external network assets: {path}",
        )


def file_sha256(path: Path) -> str:
    """Return a SHA-256 digest for a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_json_digest(payload: object) -> str:
    """Return a stable digest for one JSON-compatible payload."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def int_value(value: object) -> int:
    """Return an integer value or zero."""
    return value if isinstance(value, int) else 0


def dict_value(value: object) -> dict[str, Any]:
    """Return a dict value or an empty dict."""
    return value if isinstance(value, dict) else {}


def string_values(value: object) -> list[str]:
    """Return a stable list of string values from a JSON value."""
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, list | tuple):
        return []
    return [str(item) for item in value if str(item)]


def load_recorded_json_object(
    *,
    record: dict[str, Any],
    repo_root: Path,
    report: dict[str, object],
    label: str,
) -> dict[str, Any] | None:
    """Load a JSON artifact from a recorded file path."""
    path_text = str(record.get("path", ""))
    if not path_text:
        add_error(report, f"{label} recorded path missing")
        return None
    return load_json_object(resolve_path(Path(path_text), repo_root), report)


def path_inside_base(*, path: Path, base: Path) -> bool:
    """Return whether a path resolves inside a base directory."""
    try:
        path.resolve().relative_to(base.resolve())
    except ValueError:
        return False
    return True


def source_plan_matches_operator_review(
    *,
    source_plan: dict[str, Any],
    reviewed_plan: dict[str, Any],
) -> bool:
    """Return whether an operator review matches its source dry-run plan."""
    if not source_plan or not reviewed_plan:
        return False
    for key in (
        "agent_name",
        "profile_name",
        "round_id",
        "attempt_id",
        "target_file",
        "workspace_path",
    ):
        if str(source_plan.get(key, "")) != str(reviewed_plan.get(key, "")):
            return False
    return (
        string_values(source_plan.get("allowed_mutation_paths", []))
        == string_values(reviewed_plan.get("allowed_mutation_paths", []))
        and string_values(source_plan.get("command", []))
        == string_values(reviewed_plan.get("command", []))
    )


def validate_agent_attempts_manifest(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate per-attempt trace dirs and listed files exist."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    attempts_dir = resolve_path(Path(str(payload.get("attempts_dir", ""))), repo_root)
    if not attempts_dir.exists() or not attempts_dir.is_dir():
        add_error(report, f"attempts_dir does not exist: {attempts_dir}")
    rows = payload.get("attempts", [])
    if not isinstance(rows, list) or not rows:
        add_error(report, "agent_attempts_manifest.json attempts is empty or invalid")
        return
    for row in rows:
        if not isinstance(row, dict):
            add_error(report, "agent_attempts_manifest.json attempts contains non-object")
            continue
        attempt_dir = resolve_path(Path(str(row.get("attempt_dir", ""))), repo_root)
        if not attempt_dir.exists() or not attempt_dir.is_dir():
            add_error(report, f"attempt_dir does not exist: {attempt_dir}")
        else:
            attempt_input = attempt_dir / "agent_input.json"
            if attempt_input.exists():
                checked_files(report).append(str(attempt_input))
                validate_contract_file(
                    payload_path=attempt_input,
                    schema_path=repo_root / "schemas/agent_input.schema.json",
                    report=report,
                )
                validate_agent_input_search_space(
                    path=attempt_input,
                    repo_root=repo_root,
                    report=report,
                )
            else:
                add_error(report, f"attempt agent_input.json does not exist: {attempt_input}")
            attempt_output = attempt_dir / "attempt_output.json"
            if attempt_output.exists():
                checked_files(report).append(str(attempt_output))
                validate_contract_file(
                    payload_path=attempt_output,
                    schema_path=repo_root / "schemas/attempt_output.schema.json",
                    report=report,
                )
                validate_attempt_output_artifacts(
                    path=attempt_output,
                    repo_root=repo_root,
                    report=report,
                )
            else:
                add_error(report, f"attempt_output.json does not exist: {attempt_output}")
            replay_path = attempt_dir / "attempt_replay.json"
            if replay_path.exists():
                checked_files(report).append(str(replay_path))
                validate_contract_file(
                    payload_path=replay_path,
                    schema_path=repo_root / "schemas/attempt_replay.schema.json",
                    report=report,
                )
        file_rows = row.get("files", [])
        if not isinstance(file_rows, list) or not file_rows:
            add_error(report, f"attempt has no file records: {row.get('attempt_id', '')}")
            continue
        for file_row in file_rows:
            if not isinstance(file_row, dict):
                add_error(report, "attempt file record is non-object")
                continue
            file_path = resolve_path(Path(str(file_row.get("path", ""))), repo_root)
            if not file_path.exists() or not file_path.is_file():
                add_error(report, f"attempt file does not exist: {file_path}")


def validate_round_replay(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate a round-level replay report points at saved attempt replays."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    attempts = payload.get("attempts", [])
    if not isinstance(attempts, list) or not attempts:
        add_error(report, "round_replay.json attempts is empty or invalid")
        return
    if payload.get("replayed_attempt_count") != len(attempts):
        add_error(report, "round_replay.json replayed_attempt_count mismatch")
    if payload.get("planned_attempt_count") != payload.get("manifest_attempt_count"):
        add_error(report, "round_replay.json plan and manifest counts differ")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "round_replay.json policy invalid")
    else:
        for key in (
            "does_not_execute_agents",
            "does_not_select_candidate",
            "does_not_apply_final_patch",
            "reuses_attempt_replay_contract",
        ):
            if not bool(policy.get(key, False)):
                add_error(report, f"round_replay.json policy false: {key}")
    for row in attempts:
        if not isinstance(row, dict):
            add_error(report, "round_replay.json attempt is non-object")
            continue
        if not bool(row.get("manifest_present", False)):
            add_error(
                report,
                f"round_replay.json attempt missing manifest row: {row.get('attempt_id', '')}",
            )
        if not bool(row.get("plan_matches_manifest", False)):
            add_error(
                report,
                f"round_replay.json plan mismatch: {row.get('attempt_id', '')}",
            )
        replay_path = resolve_path(Path(str(row.get("replay_path", ""))), repo_root)
        if not replay_path.exists() or not replay_path.is_file():
            add_error(report, f"round_replay replay_path does not exist: {replay_path}")
            continue
        checked_files(report).append(str(replay_path))
        validate_contract_file(
            payload_path=replay_path,
            schema_path=repo_root / "schemas/attempt_replay.schema.json",
            report=report,
        )


def validate_agent_golden_replay(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate a golden replay report points at replayed protocol fixtures."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        add_error(report, f"agent_golden_replay checks invalid: {path}")
        return
    if bool(payload.get("ok", False)):
        for key in (
            "attempt_present",
            "replayed_output_validation_ok",
            "patch_sha_matches_saved_proposal",
            "direction_tag_matches_saved_proposal",
        ):
            if not bool(checks.get(key, False)):
                add_error(report, f"agent_golden_replay check false: {key}")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, f"agent_golden_replay policy invalid: {path}")
        return
    for key in (
        "does_not_execute_external_agents",
        "does_not_select_candidate",
        "does_not_apply_final_patch",
        "does_not_change_acceptance",
        "replays_saved_agent_input_contract",
        "requires_replayed_output_validation",
        "requires_patch_hash_match",
    ):
        if not bool(policy.get(key, False)):
            add_error(report, f"agent_golden_replay policy false: {key}")
    artifacts = payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        add_error(report, f"agent_golden_replay artifacts invalid: {path}")
        return
    for key in (
        "attempt_input",
        "saved_raw_output",
        "saved_proposal",
        "golden_output",
        "golden_validation",
        "golden_proposal",
    ):
        record = artifacts.get(key, {})
        if not isinstance(record, dict):
            add_error(report, f"agent_golden_replay artifact invalid: {key}")
            continue
        if bool(payload.get("ok", False)) and not bool(record.get("exists", False)):
            add_error(report, f"agent_golden_replay artifact missing: {key}")
            continue
        artifact_path = resolve_path(Path(str(record.get("path", ""))), repo_root)
        if bool(record.get("exists", False)):
            if not artifact_path.exists() or not artifact_path.is_file():
                add_error(
                    report,
                    f"agent_golden_replay artifact does not exist: {artifact_path}",
                )
                continue
            checked_files(report).append(str(artifact_path))
            if key == "golden_validation":
                validate_contract_file(
                    payload_path=artifact_path,
                    schema_path=repo_root / "schemas/agent_validation.schema.json",
                    report=report,
                )


def validate_codex_cli_contract_fixture(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate a guarded Codex CLI stdin/stdout contract fixture."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        add_error(report, f"codex_cli_contract_fixture checks invalid: {path}")
        return
    if bool(payload.get("ok", False)):
        for key in (
            "attempt_present",
            "adapter_is_codex_cli",
            "runner_is_guarded_codex_cli",
            "stdin_prompt_sha_matches_audit",
            "fixture_stdout_validation_ok",
            "fixture_patch_present",
            "does_not_execute_codex",
        ):
            if not bool(checks.get(key, False)):
                add_error(report, f"codex_cli_contract_fixture check false: {key}")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, f"codex_cli_contract_fixture policy invalid: {path}")
        return
    for key in (
        "does_not_execute_codex_cli",
        "does_not_select_candidate",
        "does_not_apply_final_patch",
        "does_not_change_acceptance",
        "freezes_stdin_stdout_contract",
        "requires_guarded_codex_runner",
        "requires_prompt_hash_match",
        "requires_fixture_stdout_validation",
    ):
        if not bool(policy.get(key, False)):
            add_error(report, f"codex_cli_contract_fixture policy false: {key}")
    contract = payload.get("contract", {})
    if not isinstance(contract, dict):
        add_error(report, f"codex_cli_contract_fixture contract invalid: {path}")
        return
    if bool(payload.get("ok", False)):
        if not str(contract.get("prompt_sha256", "")):
            add_error(report, "codex_cli_contract_fixture prompt hash missing")
        if contract.get("prompt_sha256") != contract.get("audit_stdin_sha256"):
            add_error(report, "codex_cli_contract_fixture prompt hash mismatch")
        if not str(contract.get("fixture_patch_sha256", "")):
            add_error(report, "codex_cli_contract_fixture patch hash missing")
    artifacts = payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        add_error(report, f"codex_cli_contract_fixture artifacts invalid: {path}")
        return
    for key in (
        "attempt_input",
        "saved_proposal",
        "agent_execution",
        "fixture_stdout",
        "fixture_validation",
        "fixture_proposal",
    ):
        record = artifacts.get(key, {})
        if not isinstance(record, dict):
            add_error(report, f"codex_cli_contract_fixture artifact invalid: {key}")
            continue
        if bool(payload.get("ok", False)) and not bool(record.get("exists", False)):
            add_error(report, f"codex_cli_contract_fixture artifact missing: {key}")
            continue
        artifact_path = resolve_path(Path(str(record.get("path", ""))), repo_root)
        if bool(record.get("exists", False)):
            if not artifact_path.exists() or not artifact_path.is_file():
                add_error(
                    report,
                    f"codex_cli_contract_fixture artifact does not exist: {artifact_path}",
                )
                continue
            checked_files(report).append(str(artifact_path))
            if key == "agent_execution":
                validate_contract_file(
                    payload_path=artifact_path,
                    schema_path=repo_root / "schemas/agent_execution.schema.json",
                    report=report,
                )
            if key == "fixture_validation":
                validate_contract_file(
                    payload_path=artifact_path,
                    schema_path=repo_root / "schemas/agent_validation.schema.json",
                    report=report,
                )


def validate_attempt_output_artifacts(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate attempt_output.json points at existing audit files."""
    payload = load_json_object(path, report)
    if payload is None:
        return
    artifacts = payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        add_error(report, f"attempt_output.json artifacts is invalid: {path}")
        return
    required = (
        "attempt",
        "agent_input",
        "proposal",
        "raw_agent_output",
        "patch",
        "selection",
        "round_agent_input",
        "round_agent_output",
        "round_agent_validation",
    )
    optional = ("workspace_manifest", "agent_execution")
    for key in required:
        artifact_path = resolve_path(Path(str(artifacts.get(key, ""))), repo_root)
        if not artifact_path.exists() or not artifact_path.is_file():
            add_error(report, f"attempt_output artifact does not exist: {key}={artifact_path}")
    for key in optional:
        value = str(artifacts.get(key, ""))
        if not value:
            continue
        artifact_path = resolve_path(Path(value), repo_root)
        if not artifact_path.exists() or not artifact_path.is_file():
            add_error(report, f"attempt_output artifact does not exist: {key}={artifact_path}")
            continue
        checked_files(report).append(str(artifact_path))
        if key == "workspace_manifest":
            validate_contract_file(
                payload_path=artifact_path,
                schema_path=repo_root / "schemas/workspace_manifest.schema.json",
                report=report,
            )
        if key == "agent_execution":
            validate_contract_file(
                payload_path=artifact_path,
                schema_path=repo_root / "schemas/agent_execution.schema.json",
                report=report,
            )


def validate_agent_executor_report(
    *,
    path: Path,
    repo_root: Path,
    role_names: set[str],
    report: dict[str, object],
) -> None:
    """Validate executor rows point at existing attempt/runtime artifacts."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    rows = payload.get("attempts", [])
    if not isinstance(rows, list) or not rows:
        add_error(report, "agent_executor_report.json attempts is empty or invalid")
        return
    selected_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            add_error(report, "agent_executor_report.json attempts contains non-object")
            continue
        if bool(row.get("selected", False)):
            selected_rows += 1
        agent_role = str(row.get("agent_role", ""))
        if not agent_role:
            add_error(report, "agent_executor_report.json attempt missing agent_role")
        elif role_names and agent_role not in role_names:
            add_error(
                report,
                f"agent_executor_report.json unknown agent_role: {agent_role}",
            )
        validate_direction_capability_row(
            row=row,
            artifact_name="agent_executor_report.json",
            report=report,
        )
        validate_direction_intent_alignment_row(
            row=row,
            artifact_name="agent_executor_report.json",
            report=report,
        )
        artifacts = row.get("artifacts", {})
        if not isinstance(artifacts, dict):
            add_error(report, "agent_executor_report.json artifacts is non-object")
            continue
        for key in ("attempt_dir", "workspace_manifest", "agent_execution"):
            value = str(artifacts.get(key, ""))
            if not value:
                continue
            artifact_path = resolve_path(Path(value), repo_root)
            if key == "attempt_dir":
                if not artifact_path.exists() or not artifact_path.is_dir():
                    add_error(
                        report,
                        f"executor attempt_dir does not exist: {artifact_path}",
                    )
            elif not artifact_path.exists() or not artifact_path.is_file():
                add_error(report, f"executor artifact does not exist: {artifact_path}")
    if selected_rows != 1:
        add_error(
            report,
            f"agent_executor_report.json must have exactly one selected row, got {selected_rows}",
        )


def validate_agent_routing_policy(
    *,
    path: Path,
    repo_root: Path,
    role_names: set[str],
    report: dict[str, object],
) -> None:
    """Validate routing policy rows and referenced attempt artifacts."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    rows = payload.get("candidates", [])
    if not isinstance(rows, list) or not rows:
        add_error(report, "agent_routing_policy.json candidates is empty or invalid")
        return
    selected_rows = 0
    selected_agent_role = str(payload.get("selected_agent_role", ""))
    for row in rows:
        if not isinstance(row, dict):
            add_error(report, "agent_routing_policy.json candidates contains non-object")
            continue
        if bool(row.get("selected", False)):
            selected_rows += 1
            if selected_agent_role != str(row.get("agent_role", "")):
                add_error(
                    report,
                    "agent_routing_policy.json selected_agent_role does not match selected row",
                )
        agent_role = str(row.get("agent_role", ""))
        if not agent_role:
            add_error(report, "agent_routing_policy.json candidate missing agent_role")
        elif role_names and agent_role not in role_names:
            add_error(
                report,
                f"agent_routing_policy.json unknown agent_role: {agent_role}",
            )
        validate_direction_capability_row(
            row=row,
            artifact_name="agent_routing_policy.json",
            report=report,
        )
        validate_direction_intent_alignment_row(
            row=row,
            artifact_name="agent_routing_policy.json",
            report=report,
        )
        artifacts = row.get("artifacts", {})
        if not isinstance(artifacts, dict):
            add_error(report, "agent_routing_policy.json artifacts is non-object")
            continue
        attempt_dir = resolve_path(
            Path(str(artifacts.get("attempt_dir", ""))),
            repo_root,
        )
        if not attempt_dir.exists() or not attempt_dir.is_dir():
            add_error(report, f"routing attempt_dir does not exist: {attempt_dir}")
        for key in ("attempt_output", "agent_input", "selection", "proposal"):
            artifact_path = resolve_path(Path(str(artifacts.get(key, ""))), repo_root)
            if not artifact_path.exists() or not artifact_path.is_file():
                add_error(
                    report,
                    f"routing artifact does not exist: {key}={artifact_path}",
                )
    if selected_rows != 1:
        add_error(
            report,
            f"agent_routing_policy.json must have exactly one selected row, got {selected_rows}",
        )
    selected_attempt_id = str(payload.get("selected_attempt_id", ""))
    if selected_attempt_id and not any(
        isinstance(row, dict)
        and bool(row.get("selected", False))
        and str(row.get("attempt_id", "")) == selected_attempt_id
        for row in rows
    ):
        add_error(
            report,
            "agent_routing_policy.json selected_attempt_id does not match selected row",
        )


def validate_agent_selection_report(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate selection report rows point at real attempt dirs."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    rows = payload.get("attempts", [])
    if not isinstance(rows, list) or not rows:
        add_error(report, "agent_selection_report.json attempts is empty or invalid")
        return
    selected_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            add_error(report, "agent_selection_report.json attempts contains non-object")
            continue
        if bool(row.get("selected", False)):
            selected_rows += 1
        validate_direction_capability_row(
            row=row,
            artifact_name="agent_selection_report.json",
            report=report,
        )
        validate_direction_intent_alignment_row(
            row=row,
            artifact_name="agent_selection_report.json",
            report=report,
        )
        attempt_dir = resolve_path(Path(str(row.get("attempt_dir", ""))), repo_root)
        if not attempt_dir.exists() or not attempt_dir.is_dir():
            add_error(report, f"selection attempt_dir does not exist: {attempt_dir}")
        selection_file = attempt_dir / "selection.json"
        if not selection_file.exists():
            add_error(report, f"missing per-attempt selection file: {selection_file}")
    if selected_rows != 1:
        add_error(
            report,
            f"agent_selection_report.json must have exactly one selected row, got {selected_rows}",
        )


def validate_direction_capability_row(
    *,
    row: dict[str, object],
    artifact_name: str,
    report: dict[str, object],
) -> None:
    """Validate direction-capability audit metadata for one candidate row."""
    supported = row.get("supported_directions", [])
    if not isinstance(supported, list) or not supported:
        add_error(report, f"{artifact_name} missing supported_directions")
    capability = row.get("direction_capability", {})
    if not isinstance(capability, dict):
        add_error(report, f"{artifact_name} direction_capability must be object")
        return
    if capability.get("schema_version") != "direction_capability_v1":
        add_error(report, f"{artifact_name} direction_capability schema mismatch")
    status = str(row.get("status", ""))
    capability_ok = bool(capability.get("ok", False))
    reason = str(capability.get("reason", ""))
    if status == "direction_not_supported" and capability_ok:
        add_error(
            report,
            f"{artifact_name} direction_not_supported row has ok capability",
        )
    if status == "direction_not_supported" and not reason:
        add_error(
            report,
            f"{artifact_name} direction_not_supported row missing reason",
        )
    if status == "selectable" and not capability_ok:
        add_error(report, f"{artifact_name} selectable row has failed capability")


def validate_direction_intent_alignment_row(
    *,
    row: dict[str, object],
    artifact_name: str,
    report: dict[str, object],
) -> None:
    """Validate audit-only planner/profile/proposal direction alignment."""
    alignment = row.get("direction_intent_alignment", {})
    if not isinstance(alignment, dict):
        add_error(report, f"{artifact_name} direction_intent_alignment must be object")
        return
    if alignment.get("schema_version") != "direction_intent_alignment_v1":
        add_error(report, f"{artifact_name} direction_intent_alignment schema mismatch")
    policy = alignment.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, f"{artifact_name} direction_intent_alignment policy invalid")
    else:
        for key in (
            "audit_only",
            "does_not_route_candidates",
            "does_not_change_acceptance",
            "acceptance_still_requires_policy_gate",
        ):
            if policy.get(key) is not True:
                add_error(
                    report,
                    f"{artifact_name} direction_intent_alignment policy false: {key}",
                )
    proposal_direction = str(row.get("direction_tag", ""))
    if str(alignment.get("proposal_direction_tag", "")) != proposal_direction:
        add_error(
            report,
            f"{artifact_name} direction_intent_alignment proposal direction mismatch",
        )
    recommended = str(alignment.get("recommended_direction", ""))
    matches = bool(alignment.get("proposal_matches_recommended_direction", False))
    deviates = bool(alignment.get("proposal_deviates_from_recommended", False))
    if recommended and proposal_direction == recommended and not matches:
        add_error(report, f"{artifact_name} alignment should mark recommendation match")
    if recommended and proposal_direction != recommended and matches:
        add_error(report, f"{artifact_name} alignment incorrectly marks match")
    if matches and deviates:
        add_error(report, f"{artifact_name} alignment cannot both match and deviate")


def validate_required_files(
    *,
    base_dir: Path,
    filenames: tuple[str, ...],
    report: dict[str, object],
) -> None:
    """Check required files exist and record present files."""
    for filename in filenames:
        path = base_dir / filename
        if not path.exists():
            add_error(report, f"missing required artifact: {path}")
            continue
        checked_files(report).append(str(path))


def validate_optional_diagnosis(
    *,
    run_dir: Path,
    report: dict[str, object],
) -> None:
    """Validate diagnosis.json when a run has one."""
    path = run_dir / "diagnosis.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_json_object(path=path, report=report)


def validate_optional_metadata(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate run_metadata.json when a run has one."""
    path = run_dir / "run_metadata.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/run_metadata.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, f"run_metadata.json run_id does not match report: {path}")


def validate_optional_experiment_scope_health(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate experiment_scope_health.json when a run has one."""
    path = run_dir / "experiment_scope_health.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/experiment_scope_health.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if not bool(payload.get("ok", False)):
        add_error(report, f"experiment_scope_health.json ok false: {path}")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "experiment_scope_health.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_apply_patches",
        "does_not_change_acceptance",
        "does_not_route_agents",
    ):
        if policy.get(key) is not True:
            add_error(report, f"experiment_scope_health.json policy false: {key}")


def validate_optional_run_closeout(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate run_closeout.json/md when a run has one."""
    path = run_dir / "run_closeout.json"
    md_path = run_dir / "run_closeout.md"
    if not path.exists() and not md_path.exists():
        return
    if not path.exists():
        add_error(report, f"missing run closeout JSON artifact: {path}")
        return
    if not md_path.exists():
        add_error(report, f"missing run closeout markdown artifact: {md_path}")
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/run_closeout.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, f"run_closeout.json run_id does not match report: {path}")
    if not bool(payload.get("ok", False)):
        add_error(report, f"run_closeout.json ok false: {path}")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "run_closeout.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_apply_patches",
        "does_not_change_acceptance",
        "does_not_route_agents",
    ):
        if policy.get(key) is not True:
            add_error(report, f"run_closeout.json policy false: {key}")


def validate_optional_candidate_challenger_report(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate candidate_challenger_report.json/md when a run has one."""
    path = run_dir / "candidate_challenger_report.json"
    md_path = run_dir / "candidate_challenger_report.md"
    if not path.exists() and not md_path.exists():
        return
    if not path.exists():
        add_error(report, f"missing candidate challenger JSON artifact: {path}")
        return
    if not md_path.exists():
        add_error(report, f"missing candidate challenger markdown artifact: {md_path}")
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/candidate_challenger_report.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"candidate_challenger_report.json run_id does not match report: {path}",
        )
    if not bool(payload.get("ok", False)):
        add_error(report, f"candidate_challenger_report.json ok false: {path}")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "candidate_challenger_report.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_promote_champion",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            add_error(report, f"candidate_challenger_report.json policy false: {key}")


def validate_optional_champion_promotion_dry_run(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate champion_promotion_dry_run.json/md when a run has one."""
    path = run_dir / "champion_promotion_dry_run.json"
    md_path = run_dir / "champion_promotion_dry_run.md"
    if not path.exists() and not md_path.exists():
        return
    if not path.exists():
        add_error(report, f"missing champion promotion dry-run JSON artifact: {path}")
        return
    if not md_path.exists():
        add_error(report, f"missing champion promotion dry-run markdown artifact: {md_path}")
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/champion_promotion_dry_run.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"champion_promotion_dry_run.json run_id does not match report: {path}",
        )
    if not bool(payload.get("ok", False)):
        add_error(report, f"champion_promotion_dry_run.json ok false: {path}")
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        add_error(report, "champion_promotion_dry_run.json checks invalid")
        return
    if checks.get("would_write_champion_registry") is not False:
        add_error(report, "champion_promotion_dry_run.json would write champion")
    if checks.get("would_append_champion_history") is not False:
        add_error(report, "champion_promotion_dry_run.json would append history")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "champion_promotion_dry_run.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_write_champion_registry",
        "does_not_append_champion_history",
        "does_not_change_acceptance",
        "requires_explicit_promote_command",
    ):
        if policy.get(key) is not True:
            add_error(report, f"champion_promotion_dry_run.json policy false: {key}")


def validate_optional_champion_promotion_approval(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate champion_promotion_approval.json/md when a run has one."""
    path = run_dir / "champion_promotion_approval.json"
    md_path = run_dir / "champion_promotion_approval.md"
    if not path.exists() and not md_path.exists():
        return
    if not path.exists():
        add_error(report, f"missing champion promotion approval JSON artifact: {path}")
        return
    if not md_path.exists():
        add_error(report, f"missing champion promotion approval markdown artifact: {md_path}")
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/champion_promotion_approval.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"champion_promotion_approval.json run_id does not match report: {path}",
        )
    if not bool(payload.get("ok", False)):
        add_error(report, f"champion_promotion_approval.json ok false: {path}")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "champion_promotion_approval.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_write_champion_registry",
        "does_not_append_champion_history",
        "does_not_execute_promote_command",
        "does_not_change_acceptance",
        "approval_does_not_promote",
        "promotion_still_requires_explicit_command",
    ):
        if policy.get(key) is not True:
            add_error(report, f"champion_promotion_approval.json policy false: {key}")


def validate_optional_champion_promotion_receipt(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate champion_promotion_receipt.json when a run has one."""
    path = run_dir / "champion_promotion_receipt.json"
    md_path = run_dir / "champion_promotion_receipt.md"
    if not path.exists():
        if md_path.exists():
            add_error(report, "champion_promotion_receipt.md exists without JSON")
        return
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    else:
        add_error(report, "champion_promotion_receipt.json missing markdown pair")
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/champion_promotion_receipt.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("candidate_run_id") != report.get("run_id"):
        add_error(
            report,
            f"champion_promotion_receipt.json run_id does not match report: {path}",
        )
    if not bool(payload.get("ok", False)):
        add_error(report, f"champion_promotion_receipt.json ok false: {path}")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "champion_promotion_receipt.json policy invalid")
        return
    for key in (
        "requires_approval_artifact",
        "requires_approval_recorded",
        "requires_command_digest_match",
        "requires_source_dry_run_digest_match",
        "requires_current_champion_match",
        "requires_current_comparison_recommendation",
        "writes_only_champion_registry_and_history",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            add_error(report, f"champion_promotion_receipt.json policy false: {key}")


def validate_optional_champion_comparison(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate champion_comparison.json when a run has one."""
    path = run_dir / "champion_comparison.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/champion_comparison.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"champion_comparison.json run_id does not match report: {path}",
        )


def validate_optional_champion_registry(
    *,
    experiments_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate the shared champion registry when it exists."""
    path = experiments_dir / "champion.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/champion.schema.json",
        report=report,
    )


def validate_optional_champion_lineage(
    *,
    experiments_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate the shared champion lineage report when it exists."""
    path = experiments_dir / "champion_lineage.json"
    md_path = experiments_dir / "champion_lineage.md"
    if not path.exists():
        if md_path.exists():
            add_error(report, "champion_lineage.md exists without JSON")
        return
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    else:
        add_error(report, "champion_lineage.json missing markdown pair")
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/champion_lineage.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if not bool(payload.get("ok", False)):
        add_error(report, f"champion_lineage.json ok false: {path}")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "champion_lineage.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_change_acceptance",
        "does_not_write_champion_registry",
        "does_not_append_champion_history",
        "does_not_promote_champion",
    ):
        if policy.get(key) is not True:
            add_error(report, f"champion_lineage.json policy false: {key}")


def validate_optional_agent_slot_health(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate agent_slot_health.json when a run has one."""
    path = run_dir / "agent_slot_health.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/agent_slot_health.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, f"agent_slot_health.json run_id does not match report: {path}")
    slots = payload.get("slots", [])
    if not isinstance(slots, list) or not slots:
        add_error(report, "agent_slot_health.json slots is empty or invalid")
        return
    totals = payload.get("totals", {})
    if isinstance(totals, dict) and totals.get("slot_count") != len(slots):
        add_error(report, "agent_slot_health.json slot_count mismatch")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "agent_slot_health.json policy invalid")
    else:
        for key in (
            "inspection_only",
            "does_not_execute_agents",
            "does_not_select_candidate",
            "does_not_change_acceptance",
        ):
            if not bool(policy.get(key, False)):
                add_error(report, f"agent_slot_health.json policy false: {key}")
    markdown_path = run_dir / "agent_slot_health.md"
    if markdown_path.exists():
        checked_files(report).append(str(markdown_path))


def validate_optional_agent_slot_readiness_gate(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate agent_slot_readiness_gate.json when a run has one."""
    path = run_dir / "agent_slot_readiness_gate.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/agent_slot_readiness_gate.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"agent_slot_readiness_gate.json run_id does not match report: {path}",
        )
    slots = payload.get("slots", [])
    if not isinstance(slots, list) or not slots:
        add_error(report, "agent_slot_readiness_gate.json slots is empty or invalid")
        return
    totals = payload.get("totals", {})
    if isinstance(totals, dict) and totals.get("slot_count") != len(slots):
        add_error(report, "agent_slot_readiness_gate.json slot_count mismatch")
    blocked_count = sum(
        1
        for slot in slots
        if isinstance(slot, dict) and slot.get("readiness_status") == "blocked"
    )
    if isinstance(totals, dict) and totals.get("blocked_count") != blocked_count:
        add_error(report, "agent_slot_readiness_gate.json blocked_count mismatch")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "agent_slot_readiness_gate.json policy invalid")
    else:
        for key in (
            "readiness_gate_only",
            "does_not_execute_agents",
            "does_not_select_candidate",
            "does_not_change_acceptance",
            "deterministic_code_keeps_acceptance_authority",
        ):
            if not bool(policy.get(key, False)):
                add_error(
                    report,
                    f"agent_slot_readiness_gate.json policy false: {key}",
                )
    markdown_path = run_dir / "agent_slot_readiness_gate.md"
    if markdown_path.exists():
        checked_files(report).append(str(markdown_path))


def validate_optional_external_agent_sandbox_drill(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate external_agent_sandbox_drill.json when a run has one."""
    path = run_dir / "external_agent_sandbox_drill.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/external_agent_sandbox_drill.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"external_agent_sandbox_drill.json run_id does not match report: {path}",
        )
    slots = payload.get("slots", [])
    if not isinstance(slots, list):
        add_error(report, "external_agent_sandbox_drill.json slots is invalid")
        return
    totals = payload.get("totals", {})
    if isinstance(totals, dict) and totals.get("slot_count") != len(slots):
        add_error(report, "external_agent_sandbox_drill.json slot_count mismatch")
    blocked_count = sum(
        1
        for slot in slots
        if isinstance(slot, dict) and slot.get("sandbox_status") == "blocked"
    )
    if isinstance(totals, dict) and totals.get("blocked_count") != blocked_count:
        add_error(report, "external_agent_sandbox_drill.json blocked_count mismatch")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "external_agent_sandbox_drill.json policy invalid")
    else:
        for key in (
            "sandbox_drill_only",
            "does_not_execute_agents",
            "does_not_apply_patches",
            "does_not_select_candidate",
            "does_not_change_acceptance",
            "deterministic_code_keeps_acceptance_authority",
        ):
            if not bool(policy.get(key, False)):
                add_error(
                    report,
                    f"external_agent_sandbox_drill.json policy false: {key}",
                )
    markdown_path = run_dir / "external_agent_sandbox_drill.md"
    if markdown_path.exists():
        checked_files(report).append(str(markdown_path))


def validate_optional_codex_cli_replay_gate(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate codex_cli_replay_gate.json when a run has one."""
    path = run_dir / "codex_cli_replay_gate.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/codex_cli_replay_gate.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"codex_cli_replay_gate.json run_id does not match report: {path}",
        )
    slots = payload.get("slots", [])
    if not isinstance(slots, list) or not slots:
        add_error(report, "codex_cli_replay_gate.json slots is empty or invalid")
        return
    totals = payload.get("totals", {})
    if isinstance(totals, dict) and totals.get("slot_count") != len(slots):
        add_error(report, "codex_cli_replay_gate.json slot_count mismatch")
    blocked_count = sum(
        1
        for slot in slots
        if isinstance(slot, dict) and slot.get("gate_status") == "blocked"
    )
    if isinstance(totals, dict) and totals.get("blocked_count") != blocked_count:
        add_error(report, "codex_cli_replay_gate.json blocked_count mismatch")
    if bool(payload.get("ok", False)) != (blocked_count == 0):
        add_error(report, "codex_cli_replay_gate.json ok/status mismatch")
    if bool(payload.get("ready_to_enable_codex_cli", False)) != bool(
        payload.get("ok", False)
    ):
        add_error(report, "codex_cli_replay_gate.json ready/ok mismatch")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "codex_cli_replay_gate.json policy invalid")
    else:
        for key in (
            "gate_only",
            "does_not_execute_codex_cli",
            "does_not_select_candidate",
            "does_not_apply_patches",
            "does_not_change_acceptance",
            "requires_guarded_execution_audit",
            "requires_contract_fixture",
            "requires_quarantine",
            "requires_round_replay",
            "deterministic_code_keeps_acceptance_authority",
        ):
            if not bool(policy.get(key, False)):
                add_error(report, f"codex_cli_replay_gate.json policy false: {key}")
    for slot in slots:
        if not isinstance(slot, dict):
            add_error(report, "codex_cli_replay_gate.json slot is non-object")
            continue
        if slot.get("adapter_name") != "codex_cli":
            add_error(
                report,
                f"codex_cli_replay_gate.json non-codex slot: {slot.get('slot_id', '')}",
            )
        blockers = slot.get("blocking_issues", [])
        if not isinstance(blockers, list):
            add_error(report, "codex_cli_replay_gate.json blocking_issues invalid")
            continue
        if bool(slot.get("ready_to_enable", False)) and blockers:
            add_error(
                report,
                f"codex_cli_replay_gate.json ready slot has blockers: {slot.get('slot_id', '')}",
            )
        if bool(slot.get("ready_to_enable", False)) != (
            slot.get("gate_status") == "ready"
        ):
            add_error(
                report,
                f"codex_cli_replay_gate.json slot ready/status mismatch: {slot.get('slot_id', '')}",
            )
        artifacts = slot.get("artifacts", {})
        if not isinstance(artifacts, dict):
            add_error(report, "codex_cli_replay_gate.json artifacts invalid")
            continue
        for key in (
            "agent_execution",
            "codex_cli_contract_fixture",
            "agent_output_quarantine",
            "round_replay",
        ):
            artifact_path = resolve_path(Path(str(artifacts.get(key, ""))), repo_root)
            if bool(slot.get("ready_to_enable", False)):
                if not artifact_path.exists() or not artifact_path.is_file():
                    add_error(
                        report,
                        f"codex_cli_replay_gate artifact does not exist: {key}={artifact_path}",
                    )
                    continue
                checked_files(report).append(str(artifact_path))
    markdown_path = run_dir / "codex_cli_replay_gate.md"
    if markdown_path.exists():
        checked_files(report).append(str(markdown_path))


def validate_optional_codex_cli_execution_preflight(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate codex_cli_execution_preflight.json when a run has one."""
    path = run_dir / "codex_cli_execution_preflight.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/codex_cli_execution_preflight.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"codex_cli_execution_preflight.json run_id does not match report: {path}",
        )
    blockers = payload.get("blocking_errors", [])
    if not isinstance(blockers, list):
        add_error(report, "codex_cli_execution_preflight.json blockers invalid")
        return
    ok = bool(payload.get("ok", False))
    if ok and blockers:
        add_error(report, "codex_cli_execution_preflight.json ok with blockers")
    if not ok and not blockers:
        add_error(report, "codex_cli_execution_preflight.json blocked without blockers")
    profiles = payload.get("profiles", [])
    if not isinstance(profiles, list) or not profiles:
        add_error(report, "codex_cli_execution_preflight.json profiles empty or invalid")
    else:
        ready_count = 0
        real_execute_count = 0
        canary_exempt_count = 0
        for profile in profiles:
            if not isinstance(profile, dict):
                add_error(report, "codex_cli_execution_preflight profile invalid")
                continue
            requires_unlock = bool(profile.get("requires_operator_unlock", False))
            operator_ready = bool(profile.get("operator_unlock_ready", False))
            canary_exempt = bool(profile.get("canary_exempt", False))
            if requires_unlock:
                real_execute_count += 1
                request_record = profile.get("operator_unlock_request", {})
                if isinstance(request_record, dict):
                    validate_recorded_file_hash(
                        record=request_record,
                        repo_root=repo_root,
                        report=report,
                        label=(
                            "codex_cli_execution_preflight operator request "
                            f"{profile.get('profile_name', '')}"
                        ),
                    )
                    request_path = resolve_path(
                        Path(str(request_record.get("path", ""))),
                        repo_root,
                    )
                    if not path_inside_base(path=request_path, base=run_dir):
                        add_error(
                            report,
                            "codex_cli_execution_preflight operator request "
                            "outside run directory",
                        )
                    canonical_path = run_dir / "codex_cli_operator_unlock_request.json"
                    if request_path.resolve() != canonical_path.resolve():
                        add_error(
                            report,
                            "codex_cli_execution_preflight operator request "
                            "not canonical run artifact",
                        )
                else:
                    add_error(
                        report,
                        "codex_cli_execution_preflight operator request invalid",
                    )
                if operator_ready:
                    ready_count += 1
            elif operator_ready:
                add_error(
                    report,
                    "codex_cli_execution_preflight non-real profile marked ready",
                )
            if canary_exempt:
                canary_exempt_count += 1
                if str(profile.get("executable", "")) != "agents/codex_cli_canary.py":
                    add_error(
                        report,
                        "codex_cli_execution_preflight canary executable invalid",
                    )
            checks = profile.get("checks", {})
            if not isinstance(checks, dict):
                add_error(report, "codex_cli_execution_preflight checks invalid")
            elif requires_unlock and operator_ready:
                for key in (
                    "operator_unlock_request_contract_valid",
                    "operator_unlock_request_schema_version_matches",
                    "operator_unlock_request_path_is_run_artifact",
                    "operator_unlock_request_path_is_canonical_run_artifact",
                    "operator_request_run_id_matches",
                    "operator_request_run_dir_matches_run",
                    "operator_request_scope_matches",
                    "operator_request_explicitly_requested",
                    "operator_request_requested_by_present",
                    "operator_request_confirmation_phrase_matches",
                    "operator_request_required_confirmation_hash_matches",
                    "operator_request_provided_confirmation_hash_matches",
                    "operator_request_source_pipeline_hash_matches",
                    "operator_request_source_pipeline_path_matches_record",
                    "operator_request_source_pipeline_path_is_canonical_run_artifact",
                    "operator_request_source_dry_run_hash_matches",
                    "operator_request_source_dry_run_path_matches_record",
                    "operator_request_source_dry_run_path_is_canonical_run_artifact",
                    "operator_request_source_dry_run_plan_present",
                    "operator_request_source_dry_run_plan_matches_review",
                    "operator_request_agent_name_matches",
                    "operator_request_profile_name_matches",
                    "operator_request_round_id_matches",
                    "operator_request_attempt_id_matches",
                    "operator_request_command_matches_profile",
                    "operator_request_command_sha256_matches_profile",
                    "operator_request_workspace_prefix_matches_run",
                    "operator_request_workspace_path_matches_expected",
                    "operator_request_targets_current_strategy",
                    "operator_request_allows_strategy_only",
                    "operator_request_does_not_execute_by_itself",
                ):
                    if not bool(checks.get(key, False)):
                        add_error(
                            report,
                            "codex_cli_execution_preflight ready with false "
                            f"check: {key}",
                        )
            expected = profile.get("expected_execution", {})
            if not isinstance(expected, dict):
                add_error(report, "codex_cli_execution_preflight expected execution invalid")
            else:
                expected_command = expected.get("command", [])
                expected_target = str(expected.get("target_file", ""))
                if expected_target != "strategies/current_strategy.py":
                    add_error(
                        report,
                        "codex_cli_execution_preflight expected target invalid",
                    )
                if not str(expected.get("workspace_root", "")).strip():
                    add_error(
                        report,
                        "codex_cli_execution_preflight expected workspace root missing",
                    )
                if not str(expected.get("workspace_prefix", "")).strip():
                    add_error(
                        report,
                        "codex_cli_execution_preflight expected workspace prefix missing",
                    )
                if not str(expected.get("workspace_path", "")).strip():
                    add_error(
                        report,
                        "codex_cli_execution_preflight expected workspace path missing",
                    )
                if not isinstance(expected_command, list):
                    add_error(
                        report,
                        "codex_cli_execution_preflight expected command invalid",
                    )
                else:
                    expected_command_text = " ".join(
                        str(part) for part in expected_command
                    )
                    if "strategies/current_strategy.py" not in expected_command_text:
                        add_error(
                            report,
                            "codex_cli_execution_preflight expected command "
                            "missing target file",
                        )
                    if expected.get("command_sha256") != stable_json_digest(
                        expected_command
                    ):
                        add_error(
                            report,
                            "codex_cli_execution_preflight expected command "
                            "sha256 mismatch",
                        )
        summary = payload.get("summary", {})
        if isinstance(summary, dict):
            if summary.get("real_codex_execute_profile_count") != real_execute_count:
                add_error(
                    report,
                    "codex_cli_execution_preflight real execute count mismatch",
                )
            if summary.get("operator_unlock_ready_count") != ready_count:
                add_error(
                    report,
                    "codex_cli_execution_preflight operator ready count mismatch",
                )
            if summary.get("canary_exempt_count") != canary_exempt_count:
                add_error(
                    report,
                    "codex_cli_execution_preflight canary exempt count mismatch",
                )
        else:
            add_error(report, "codex_cli_execution_preflight summary invalid")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "codex_cli_execution_preflight policy invalid")
    else:
        for key in (
            "startup_gate_only",
            "read_only",
            "blocks_real_codex_without_operator_unlock",
            "allows_checked_in_canary_fixture",
            "does_not_execute_codex_cli",
            "does_not_create_workspace",
            "does_not_send_strategy_prompt",
            "does_not_modify_config",
            "does_not_select_candidate",
            "does_not_apply_patches",
            "does_not_change_acceptance",
            "deterministic_code_keeps_acceptance_authority",
        ):
            if not bool(policy.get(key, False)):
                add_error(
                    report,
                    f"codex_cli_execution_preflight policy false: {key}",
                )
    markdown_path = run_dir / "codex_cli_execution_preflight.md"
    if markdown_path.exists():
        checked_files(report).append(str(markdown_path))


def validate_optional_codex_cli_enablement_gate(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate codex_cli_enablement_gate.json when a run has one."""
    path = run_dir / "codex_cli_enablement_gate.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/codex_cli_enablement_gate.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"codex_cli_enablement_gate.json run_id does not match report: {path}",
        )
    blockers = payload.get("blocking_reasons", [])
    if not isinstance(blockers, list):
        add_error(report, "codex_cli_enablement_gate.json blocking_reasons invalid")
        return
    permitted = bool(payload.get("permitted_to_enable", False))
    if bool(payload.get("ok", False)) != permitted:
        add_error(report, "codex_cli_enablement_gate.json ok/permitted mismatch")
    if permitted and blockers:
        add_error(report, "codex_cli_enablement_gate.json permitted with blockers")
    if not permitted and not blockers:
        add_error(report, "codex_cli_enablement_gate.json blocked without reason")
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        add_error(report, "codex_cli_enablement_gate.json checks invalid")
    elif permitted:
        for key, value in checks.items():
            if not bool(value):
                add_error(report, f"codex_cli_enablement_gate.json check false: {key}")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "codex_cli_enablement_gate.json policy invalid")
    else:
        for key in (
            "gate_only",
            "does_not_execute_codex_cli",
            "does_not_modify_config",
            "does_not_select_candidate",
            "does_not_apply_patches",
            "does_not_change_acceptance",
            "requires_replay_gate_ready",
            "requires_manual_confirmation",
            "deterministic_code_keeps_acceptance_authority",
        ):
            if not bool(policy.get(key, False)):
                add_error(
                    report,
                    f"codex_cli_enablement_gate.json policy false: {key}",
                )
    artifacts = payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        add_error(report, "codex_cli_enablement_gate.json artifacts invalid")
    else:
        for key in ("codex_cli_replay_gate", "candidate_config"):
            record = artifacts.get(key, {})
            if not isinstance(record, dict):
                add_error(
                    report,
                    f"codex_cli_enablement_gate artifact invalid: {key}",
                )
                continue
            artifact_path = resolve_path(Path(str(record.get("path", ""))), repo_root)
            if permitted and not artifact_path.exists():
                add_error(
                    report,
                    f"codex_cli_enablement_gate artifact missing: {key}={artifact_path}",
                )
            elif artifact_path.exists():
                checked_files(report).append(str(artifact_path))
    markdown_path = run_dir / "codex_cli_enablement_gate.md"
    if markdown_path.exists():
        checked_files(report).append(str(markdown_path))


def validate_optional_codex_cli_manual_approval(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate codex_cli_manual_approval.json when a run has one."""
    path = run_dir / "codex_cli_manual_approval.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/codex_cli_manual_approval.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"codex_cli_manual_approval.json run_id does not match report: {path}",
        )
    blockers = payload.get("blocking_reasons", [])
    if not isinstance(blockers, list):
        add_error(report, "codex_cli_manual_approval.json blocking_reasons invalid")
        return
    granted = bool(payload.get("manual_approval_granted", False))
    if bool(payload.get("ok", False)) != granted:
        add_error(report, "codex_cli_manual_approval.json ok/granted mismatch")
    if bool(payload.get("ready_for_controlled_codex_cli_execution", False)) != granted:
        add_error(report, "codex_cli_manual_approval.json ready/granted mismatch")
    if granted and blockers:
        add_error(report, "codex_cli_manual_approval.json granted with blockers")
    if not granted and not blockers:
        add_error(report, "codex_cli_manual_approval.json blocked without reason")
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        add_error(report, "codex_cli_manual_approval.json checks invalid")
    elif granted:
        for key, value in checks.items():
            if not bool(value):
                add_error(report, f"codex_cli_manual_approval.json check false: {key}")
    approval = payload.get("approval", {})
    if not isinstance(approval, dict):
        add_error(report, "codex_cli_manual_approval.json approval invalid")
    elif granted:
        if not bool(approval.get("approved", False)):
            add_error(report, "codex_cli_manual_approval.json approved false")
        if not str(approval.get("approved_by", "")).strip():
            add_error(report, "codex_cli_manual_approval.json approved_by missing")
        if not bool(approval.get("confirmation_phrase_matches", False)):
            add_error(
                report,
                "codex_cli_manual_approval.json confirmation phrase mismatch",
            )
    enablement_gate = payload.get("enablement_gate", {})
    if not isinstance(enablement_gate, dict):
        add_error(report, "codex_cli_manual_approval.json enablement_gate invalid")
    elif granted:
        if not bool(enablement_gate.get("ok", False)):
            add_error(report, "codex_cli_manual_approval.json enablement gate not ok")
        if not bool(enablement_gate.get("permitted_to_enable", False)):
            add_error(
                report,
                "codex_cli_manual_approval.json enablement gate not permitted",
            )
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "codex_cli_manual_approval.json policy invalid")
    else:
        for key in (
            "approval_only",
            "does_not_execute_codex_cli",
            "does_not_modify_config",
            "does_not_select_candidate",
            "does_not_apply_patches",
            "does_not_change_acceptance",
            "requires_enablement_gate",
            "requires_explicit_approval_flag",
            "requires_exact_confirmation_phrase",
            "deterministic_code_keeps_acceptance_authority",
        ):
            if not bool(policy.get(key, False)):
                add_error(
                    report,
                    f"codex_cli_manual_approval.json policy false: {key}",
                )
    artifacts = payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        add_error(report, "codex_cli_manual_approval.json artifacts invalid")
    else:
        for key in ("codex_cli_enablement_gate", "candidate_config"):
            record = artifacts.get(key, {})
            if not isinstance(record, dict):
                add_error(
                    report,
                    f"codex_cli_manual_approval artifact invalid: {key}",
                )
                continue
            artifact_path = resolve_path(Path(str(record.get("path", ""))), repo_root)
            if granted and not artifact_path.exists():
                add_error(
                    report,
                    f"codex_cli_manual_approval artifact missing: {key}={artifact_path}",
                )
            elif artifact_path.exists():
                checked_files(report).append(str(artifact_path))
    markdown_path = run_dir / "codex_cli_manual_approval.md"
    if markdown_path.exists():
        checked_files(report).append(str(markdown_path))


def validate_optional_codex_cli_canary_gate(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate codex_cli_canary_gate.json when a run has one."""
    path = run_dir / "codex_cli_canary_gate.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/codex_cli_canary_gate.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"codex_cli_canary_gate.json run_id does not match report: {path}",
        )
    blockers = payload.get("blocking_reasons", [])
    if not isinstance(blockers, list):
        add_error(report, "codex_cli_canary_gate.json blocking_reasons invalid")
        return
    ready = bool(payload.get("controlled_execution_ready", False))
    if bool(payload.get("ok", False)) != ready:
        add_error(report, "codex_cli_canary_gate.json ok/ready mismatch")
    if ready and blockers:
        add_error(report, "codex_cli_canary_gate.json ready with blockers")
    if not ready and not blockers:
        add_error(report, "codex_cli_canary_gate.json blocked without reason")
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        add_error(report, "codex_cli_canary_gate.json checks invalid")
    elif ready:
        for key, value in checks.items():
            if not bool(value):
                add_error(report, f"codex_cli_canary_gate.json check false: {key}")
    totals = payload.get("totals", {})
    slots = payload.get("slots", [])
    if not isinstance(totals, dict):
        add_error(report, "codex_cli_canary_gate.json totals invalid")
    if not isinstance(slots, list) or not slots:
        add_error(report, "codex_cli_canary_gate.json slots empty or invalid")
        slots = []
    if isinstance(totals, dict):
        if totals.get("round_count") != len(slots):
            add_error(report, "codex_cli_canary_gate.json round_count mismatch")
        ready_count = sum(
            1 for slot in slots if isinstance(slot, dict) and slot.get("ready") is True
        )
        if totals.get("ready_count") != ready_count:
            add_error(report, "codex_cli_canary_gate.json ready_count mismatch")
        if totals.get("blocked_count") != len(slots) - ready_count:
            add_error(report, "codex_cli_canary_gate.json blocked_count mismatch")
    for slot in slots:
        if not isinstance(slot, dict):
            add_error(report, "codex_cli_canary_gate.json slot is non-object")
            continue
        slot_ready = bool(slot.get("ready", False))
        slot_blockers = slot.get("blocking_issues", [])
        if not isinstance(slot_blockers, list):
            add_error(report, "codex_cli_canary_gate.json slot blockers invalid")
            continue
        if slot_ready and slot_blockers:
            add_error(
                report,
                f"codex_cli_canary_gate.json ready slot has blockers: {slot.get('slot_id', '')}",
            )
        if slot_ready != (slot.get("gate_status") == "ready"):
            add_error(
                report,
                f"codex_cli_canary_gate.json slot ready/status mismatch: {slot.get('slot_id', '')}",
            )
        requirements = slot.get("requirements", {})
        if not isinstance(requirements, dict):
            add_error(report, "codex_cli_canary_gate.json requirements invalid")
        elif slot_ready:
            for key, value in requirements.items():
                if not bool(value):
                    add_error(
                        report,
                        f"codex_cli_canary_gate.json requirement false: {key}",
                    )
        artifacts = slot.get("artifacts", {})
        if isinstance(artifacts, dict):
            for key, value in artifacts.items():
                artifact_path = resolve_path(Path(str(value)), repo_root)
                if slot_ready and not artifact_path.exists():
                    add_error(
                        report,
                        f"codex_cli_canary_gate artifact missing: {key}={artifact_path}",
                    )
                elif artifact_path.exists():
                    checked_files(report).append(str(artifact_path))
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "codex_cli_canary_gate.json policy invalid")
    else:
        for key in (
            "gate_only",
            "executes_only_checked_in_canary",
            "does_not_execute_real_codex_cli",
            "does_not_modify_config",
            "does_not_select_candidate",
            "does_not_apply_patches",
            "does_not_change_acceptance",
            "requires_guarded_execution_audit",
            "requires_quarantine_release",
            "requires_deterministic_reject_and_rollback",
            "deterministic_code_keeps_acceptance_authority",
        ):
            if not bool(policy.get(key, False)):
                add_error(report, f"codex_cli_canary_gate.json policy false: {key}")
    artifacts = payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        add_error(report, "codex_cli_canary_gate.json artifacts invalid")
    else:
        for key, record in artifacts.items():
            if not isinstance(record, dict):
                add_error(report, f"codex_cli_canary_gate artifact invalid: {key}")
                continue
            artifact_path = resolve_path(Path(str(record.get("path", ""))), repo_root)
            if ready and not artifact_path.exists():
                add_error(
                    report,
                    f"codex_cli_canary_gate artifact missing: {key}={artifact_path}",
                )
            elif artifact_path.exists():
                checked_files(report).append(str(artifact_path))
    markdown_path = run_dir / "codex_cli_canary_gate.md"
    if markdown_path.exists():
        checked_files(report).append(str(markdown_path))


def validate_optional_codex_cli_real_preflight(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate codex_cli_real_preflight.json when a run has one."""
    path = run_dir / "codex_cli_real_preflight.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/codex_cli_real_preflight.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"codex_cli_real_preflight.json run_id does not match report: {path}",
        )
    blockers = payload.get("blocking_reasons", [])
    if not isinstance(blockers, list):
        add_error(report, "codex_cli_real_preflight.json blocking_reasons invalid")
        return
    ready = bool(payload.get("real_codex_cli_ready", False))
    if ready and blockers:
        add_error(report, "codex_cli_real_preflight.json ready with blockers")
    if not ready and not blockers:
        add_error(report, "codex_cli_real_preflight.json blocked without reason")
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        add_error(report, "codex_cli_real_preflight.json checks invalid")
    else:
        if not bool(checks.get("does_not_execute_strategy_modification", False)):
            add_error(
                report,
                "codex_cli_real_preflight.json executed strategy modification",
            )
        if ready:
            for key, value in checks.items():
                if not bool(value):
                    add_error(
                        report,
                        f"codex_cli_real_preflight.json check false: {key}",
                    )
    if bool(payload.get("ok", False)) is not True:
        add_error(report, "codex_cli_real_preflight.json ok false")
    executable = payload.get("executable", {})
    if not isinstance(executable, dict):
        add_error(report, "codex_cli_real_preflight.json executable invalid")
    version_probe = payload.get("version_probe", {})
    if not isinstance(version_probe, dict):
        add_error(report, "codex_cli_real_preflight.json version_probe invalid")
    else:
        status = str(version_probe.get("status", ""))
        if status not in {"missing", "completed", "failed", "timeout"}:
            add_error(
                report,
                f"codex_cli_real_preflight.json invalid version status: {status}",
            )
        command = version_probe.get("command", [])
        if ready:
            if not isinstance(command, list) or "--version" not in command:
                add_error(
                    report,
                    "codex_cli_real_preflight.json ready without version command",
                )
            if version_probe.get("returncode") != 0:
                add_error(
                    report,
                    "codex_cli_real_preflight.json ready with nonzero version probe",
                )
        if isinstance(command, list) and any(
            "current_strategy.py" in str(part) for part in command
        ):
            add_error(
                report,
                "codex_cli_real_preflight.json version command targets strategy",
            )
    command_template = payload.get("command_template", [])
    if not isinstance(command_template, list):
        add_error(report, "codex_cli_real_preflight.json command_template invalid")
    elif "exec" not in command_template or "--sandbox" not in command_template:
        add_error(report, "codex_cli_real_preflight.json command_template incomplete")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "codex_cli_real_preflight.json policy invalid")
    else:
        for key in (
            "preflight_only",
            "does_not_execute_strategy_modification",
            "does_not_send_strategy_prompt",
            "does_not_create_agent_workspace",
            "does_not_modify_config",
            "does_not_select_candidate",
            "does_not_apply_patches",
            "does_not_change_acceptance",
            "version_probe_only",
            "deterministic_code_keeps_acceptance_authority",
        ):
            if not bool(policy.get(key, False)):
                add_error(report, f"codex_cli_real_preflight.json policy false: {key}")
    artifacts = payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        add_error(report, "codex_cli_real_preflight.json artifacts invalid")
    else:
        for key, record in artifacts.items():
            if not isinstance(record, dict):
                add_error(report, f"codex_cli_real_preflight artifact invalid: {key}")
                continue
            artifact_path = resolve_path(Path(str(record.get("path", ""))), repo_root)
            if artifact_path.exists():
                checked_files(report).append(str(artifact_path))
    markdown_path = run_dir / "codex_cli_real_preflight.md"
    if markdown_path.exists():
        checked_files(report).append(str(markdown_path))


def validate_optional_codex_cli_dry_invocation_guard(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate codex_cli_dry_invocation_guard.json when a run has one."""
    path = run_dir / "codex_cli_dry_invocation_guard.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/codex_cli_dry_invocation_guard.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"codex_cli_dry_invocation_guard.json run_id does not match report: {path}",
        )
    blockers = payload.get("blocking_reasons", [])
    if not isinstance(blockers, list):
        add_error(report, "codex_cli_dry_invocation_guard.json blocking_reasons invalid")
        return
    ready = bool(payload.get("dry_invocation_ready", False))
    execution_requested = bool(payload.get("execution_requested", False))
    if ready and blockers:
        add_error(report, "codex_cli_dry_invocation_guard.json ready with blockers")
    if not ready and execution_requested and not blockers:
        add_error(report, "codex_cli_dry_invocation_guard.json blocked without reason")
    if bool(payload.get("ok", False)) is not True:
        add_error(report, "codex_cli_dry_invocation_guard.json ok false")
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        add_error(report, "codex_cli_dry_invocation_guard.json checks invalid")
    else:
        for key in (
            "prompt_is_harmless",
            "command_is_harmless",
            "does_not_apply_patches",
            "does_not_change_acceptance",
        ):
            if not bool(checks.get(key, False)):
                add_error(
                    report,
                    f"codex_cli_dry_invocation_guard.json safety check false: {key}",
                )
        if ready:
            for key, value in checks.items():
                if not bool(value):
                    add_error(
                        report,
                        f"codex_cli_dry_invocation_guard.json check false: {key}",
                    )
    dry_invocation = payload.get("dry_invocation", {})
    if not isinstance(dry_invocation, dict):
        add_error(report, "codex_cli_dry_invocation_guard.json dry_invocation invalid")
    else:
        command = dry_invocation.get("command", [])
        if not isinstance(command, list):
            add_error(report, "codex_cli_dry_invocation_guard.json command invalid")
        else:
            command_text = " ".join(str(part) for part in command)
            for forbidden in ("current_strategy.py", "strategies/", "patch"):
                if forbidden in command_text:
                    add_error(
                        report,
                        f"codex_cli_dry_invocation_guard.json command contains {forbidden}",
                    )
            if "SUANAGENT_DRY_INVOCATION_OK" not in command_text:
                add_error(
                    report,
                    "codex_cli_dry_invocation_guard.json command missing expected text",
                )
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "codex_cli_dry_invocation_guard.json policy invalid")
    else:
        for key in (
            "guard_only",
            "harmless_prompt_only",
            "does_not_reference_strategy_file",
            "does_not_apply_patches",
            "does_not_select_candidate",
            "does_not_change_acceptance",
            "requires_empty_mutation_allowlist",
            "requires_workspace_mutation_guard",
            "deterministic_code_keeps_acceptance_authority",
        ):
            if not bool(policy.get(key, False)):
                add_error(
                    report,
                    f"codex_cli_dry_invocation_guard.json policy false: {key}",
                )
    artifacts = payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        add_error(report, "codex_cli_dry_invocation_guard.json artifacts invalid")
    else:
        execution_record = artifacts.get("execution_audit", {})
        execution_path: Path | None = None
        if isinstance(execution_record, dict):
            execution_path = resolve_path(
                Path(str(execution_record.get("path", ""))),
                repo_root,
            )
            if execution_path.exists():
                checked_files(report).append(str(execution_path))
                validate_contract_file(
                    payload_path=execution_path,
                    schema_path=repo_root / "schemas/agent_execution.schema.json",
                    report=report,
                )
                execution = validate_json_object(path=execution_path, report=report)
                if execution is not None:
                    if execution.get("runner_name") != "codex_cli_guarded_adapter":
                        add_error(
                            report,
                            "codex_cli_dry_invocation execution runner invalid",
                        )
                    if execution.get("adapter_name") != "codex_cli_dry_invocation":
                        add_error(
                            report,
                            "codex_cli_dry_invocation execution adapter invalid",
                        )
                    if execution.get("allowed_mutation_paths") != []:
                        add_error(
                            report,
                            "codex_cli_dry_invocation allowed mutation paths not empty",
                        )
                    mutation_guard = execution.get("mutation_guard", {})
                    if not isinstance(mutation_guard, dict) or not bool(
                        mutation_guard.get("passed", False)
                    ):
                        add_error(
                            report,
                            "codex_cli_dry_invocation mutation guard failed",
                        )
            elif ready:
                add_error(
                    report,
                    f"codex_cli_dry_invocation execution missing: {execution_path}",
                )
        for key, record in artifacts.items():
            if key == "workspace":
                if isinstance(record, dict) and bool(record.get("exists", False)):
                    workspace_path = resolve_path(Path(str(record.get("path", ""))), repo_root)
                    if not workspace_path.exists() and ready:
                        add_error(
                            report,
                            f"codex_cli_dry_invocation workspace missing: {workspace_path}",
                        )
                continue
            if not isinstance(record, dict):
                add_error(
                    report,
                    f"codex_cli_dry_invocation artifact invalid: {key}",
                )
                continue
            artifact_path = resolve_path(Path(str(record.get("path", ""))), repo_root)
            if artifact_path.exists():
                checked_files(report).append(str(artifact_path))
            elif ready:
                add_error(
                    report,
                    f"codex_cli_dry_invocation artifact missing: {key}={artifact_path}",
                )
    markdown_path = run_dir / "codex_cli_dry_invocation_guard.md"
    if markdown_path.exists():
        checked_files(report).append(str(markdown_path))


def validate_optional_codex_cli_execution_unlock_gate(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate codex_cli_execution_unlock_gate.json when a run has one."""
    path = run_dir / "codex_cli_execution_unlock_gate.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/codex_cli_execution_unlock_gate.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"codex_cli_execution_unlock_gate.json run_id does not match report: {path}",
        )
    if bool(payload.get("ok", False)) is not True:
        add_error(report, "codex_cli_execution_unlock_gate.json ok false")
    blockers = payload.get("blocking_reasons", [])
    if not isinstance(blockers, list):
        add_error(
            report,
            "codex_cli_execution_unlock_gate.json blocking_reasons invalid",
        )
        return
    unlocked = bool(payload.get("real_codex_execution_unlocked", False))
    if unlocked and blockers:
        add_error(report, "codex_cli_execution_unlock_gate.json unlocked with blockers")
    if not unlocked and not blockers:
        add_error(report, "codex_cli_execution_unlock_gate.json locked without reason")
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        add_error(report, "codex_cli_execution_unlock_gate.json checks invalid")
    else:
        for key in (
            "does_not_execute_codex_cli",
            "does_not_apply_patches",
            "does_not_change_acceptance",
            "deterministic_code_keeps_acceptance_authority",
        ):
            if not bool(checks.get(key, False)):
                add_error(
                    report,
                    f"codex_cli_execution_unlock_gate.json safety check false: {key}",
                )
        if unlocked:
            for key, value in checks.items():
                if not bool(value):
                    add_error(
                        report,
                        f"codex_cli_execution_unlock_gate.json check false: {key}",
                    )
    gate_status = payload.get("gate_status", {})
    if not isinstance(gate_status, dict):
        add_error(report, "codex_cli_execution_unlock_gate.json gate_status invalid")
    else:
        for key in (
            "codex_cli_replay_gate",
            "codex_cli_enablement_gate",
            "codex_cli_manual_approval",
            "codex_cli_canary_gate",
            "codex_cli_real_preflight",
            "codex_cli_dry_invocation_guard",
        ):
            status = gate_status.get(key, {})
            if not isinstance(status, dict):
                add_error(
                    report,
                    f"codex_cli_execution_unlock_gate.json gate_status invalid: {key}",
                )
                continue
            if unlocked and not bool(status.get("ready", False)):
                add_error(
                    report,
                    f"codex_cli_execution_unlock_gate.json gate_status not ready: {key}",
                )
    config_binding = payload.get("config_binding", {})
    if not isinstance(config_binding, dict):
        add_error(report, "codex_cli_execution_unlock_gate.json config_binding invalid")
    else:
        expected_sha256 = str(config_binding.get("expected_config_sha256", ""))
        gates = config_binding.get("gates", {})
        missing = config_binding.get("missing_gate_names", [])
        mismatched = config_binding.get("mismatched_gate_names", [])
        all_matched = bool(config_binding.get("all_matched", False))
        if not expected_sha256:
            add_error(
                report,
                "codex_cli_execution_unlock_gate.json expected config sha256 missing",
            )
        if not isinstance(gates, dict):
            add_error(
                report,
                "codex_cli_execution_unlock_gate.json binding gates invalid",
            )
        else:
            for key in (
                "codex_cli_enablement_gate",
                "codex_cli_manual_approval",
                "codex_cli_real_preflight",
                "codex_cli_dry_invocation_guard",
            ):
                binding = gates.get(key, {})
                if not isinstance(binding, dict):
                    add_error(
                        report,
                        f"codex_cli_execution_unlock_gate.json binding invalid: {key}",
                    )
                    continue
                if unlocked and not bool(binding.get("matches_expected", False)):
                    add_error(
                        report,
                        f"codex_cli_execution_unlock_gate.json binding mismatch: {key}",
                    )
        if not isinstance(missing, list):
            add_error(
                report,
                "codex_cli_execution_unlock_gate.json binding missing invalid",
            )
        if not isinstance(mismatched, list):
            add_error(
                report,
                "codex_cli_execution_unlock_gate.json binding mismatched invalid",
            )
        if unlocked and not all_matched:
            add_error(
                report,
                "codex_cli_execution_unlock_gate.json unlocked with config mismatch",
            )
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "codex_cli_execution_unlock_gate.json policy invalid")
    else:
        for key in (
            "unlock_gate_only",
            "read_only",
            "does_not_execute_codex_cli",
            "does_not_send_strategy_prompt",
            "does_not_modify_config",
            "does_not_select_candidate",
            "does_not_apply_patches",
            "does_not_change_acceptance",
            "requires_replay_gate",
            "requires_enablement_gate",
            "requires_manual_approval",
            "requires_controlled_canary",
            "requires_real_preflight",
            "requires_successful_dry_invocation",
            "requires_candidate_config_hash_binding",
            "deterministic_code_keeps_acceptance_authority",
        ):
            if not bool(policy.get(key, False)):
                add_error(
                    report,
                    f"codex_cli_execution_unlock_gate.json policy false: {key}",
                )
    artifacts = payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        add_error(report, "codex_cli_execution_unlock_gate.json artifacts invalid")
    else:
        for key, record in artifacts.items():
            if not isinstance(record, dict):
                add_error(
                    report,
                    f"codex_cli_execution_unlock_gate artifact invalid: {key}",
                )
                continue
            artifact_path = resolve_path(Path(str(record.get("path", ""))), repo_root)
            if artifact_path.exists():
                checked_files(report).append(str(artifact_path))
            elif unlocked:
                add_error(
                    report,
                    f"codex_cli_execution_unlock_gate artifact missing: {key}={artifact_path}",
                )
    markdown_path = run_dir / "codex_cli_execution_unlock_gate.md"
    if markdown_path.exists():
        checked_files(report).append(str(markdown_path))


def validate_optional_codex_cli_execution_unlock_snapshot(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate codex_cli_execution_unlock_snapshot.json when a run has one."""
    path = run_dir / "codex_cli_execution_unlock_snapshot.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/codex_cli_execution_unlock_snapshot.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"codex_cli_execution_unlock_snapshot.json run_id does not match report: {path}",
        )
    if bool(payload.get("ok", False)) is not True:
        add_error(report, "codex_cli_execution_unlock_snapshot.json ok false")
    source_gate = payload.get("source_gate", {})
    if not isinstance(source_gate, dict):
        add_error(report, "codex_cli_execution_unlock_snapshot.json source_gate invalid")
    else:
        validate_recorded_file_hash(
            record=source_gate,
            repo_root=repo_root,
            report=report,
            label="codex_cli_execution_unlock_snapshot source_gate",
        )
        validate_declared_record_path(
            declared_path=str(payload.get("source_gate_path", "")),
            record=source_gate,
            repo_root=repo_root,
            report=report,
            label="codex_cli_execution_unlock_snapshot source_gate",
        )
        if not artifact_path_matches_file(
            path_text=str(payload.get("source_gate_path", "")),
            expected_path=run_dir / "codex_cli_execution_unlock_gate.json",
            repo_root=repo_root,
        ):
            add_error(
                report,
                "codex_cli_execution_unlock_snapshot source_gate "
                "not canonical run artifact",
            )
    expected_digest = snapshot_digest_from_payload(payload)
    if str(payload.get("snapshot_digest", "")) != expected_digest:
        add_error(report, "codex_cli_execution_unlock_snapshot.json digest mismatch")
    evidence = payload.get("evidence_artifacts", {})
    if not isinstance(evidence, dict):
        add_error(report, "codex_cli_execution_unlock_snapshot.json evidence invalid")
    else:
        for key, record in evidence.items():
            if not isinstance(record, dict):
                add_error(
                    report,
                    f"codex_cli_execution_unlock_snapshot evidence invalid: {key}",
                )
                continue
            validate_recorded_file_hash(
                record=record,
                repo_root=repo_root,
                report=report,
                label=f"codex_cli_execution_unlock_snapshot evidence {key}",
                allow_missing_when_recorded_missing=True,
            )
    config_binding = payload.get("config_binding", {})
    if not isinstance(config_binding, dict):
        add_error(
            report,
            "codex_cli_execution_unlock_snapshot.json config_binding invalid",
        )
    elif not str(config_binding.get("expected_config_sha256", "")):
        add_error(
            report,
            "codex_cli_execution_unlock_snapshot.json expected config sha256 missing",
        )
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "codex_cli_execution_unlock_snapshot.json policy invalid")
    else:
        for key in (
            "snapshot_only",
            "read_only",
            "does_not_execute_codex_cli",
            "does_not_send_strategy_prompt",
            "does_not_modify_config",
            "does_not_select_candidate",
            "does_not_apply_patches",
            "does_not_change_acceptance",
            "freezes_unlock_gate_sha256",
            "freezes_evidence_artifact_sha256",
            "deterministic_code_keeps_acceptance_authority",
        ):
            if not bool(policy.get(key, False)):
                add_error(
                    report,
                    f"codex_cli_execution_unlock_snapshot.json policy false: {key}",
                )
    markdown_path = run_dir / "codex_cli_execution_unlock_snapshot.md"
    if markdown_path.exists():
        checked_files(report).append(str(markdown_path))


def validate_optional_codex_cli_execution_candidate(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate codex_cli_execution_candidate.json when a run has one."""
    path = run_dir / "codex_cli_execution_candidate.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/codex_cli_execution_candidate.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"codex_cli_execution_candidate.json run_id does not match report: {path}",
        )
    if bool(payload.get("ok", False)) is not True:
        add_error(report, "codex_cli_execution_candidate.json ok false")
    blockers = payload.get("blocking_reasons", [])
    if not isinstance(blockers, list):
        add_error(report, "codex_cli_execution_candidate.json blockers invalid")
        return
    ready = bool(payload.get("execution_candidate_ready", False))
    if ready and blockers:
        add_error(report, "codex_cli_execution_candidate.json ready with blockers")
    if not ready and not blockers:
        add_error(report, "codex_cli_execution_candidate.json blocked without reason")
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        add_error(report, "codex_cli_execution_candidate.json checks invalid")
    else:
        for key in (
            "does_not_execute_codex_cli",
            "does_not_create_workspace",
            "does_not_apply_patches",
            "does_not_change_acceptance",
        ):
            if not bool(checks.get(key, False)):
                add_error(
                    report,
                    f"codex_cli_execution_candidate.json safety check false: {key}",
                )
        if ready:
            for key, value in checks.items():
                if not bool(value):
                    add_error(
                        report,
                        f"codex_cli_execution_candidate.json check false: {key}",
                    )
    source_snapshot = payload.get("source_snapshot", {})
    if not isinstance(source_snapshot, dict):
        add_error(report, "codex_cli_execution_candidate.json source_snapshot invalid")
    else:
        validate_source_artifact_provenance(
            source=source_snapshot,
            expected_path=run_dir / "codex_cli_execution_unlock_snapshot.json",
            repo_root=repo_root,
            report=report,
            label="codex_cli_execution_candidate source_snapshot",
            invalid_file_error="codex_cli_execution_candidate snapshot file invalid",
            not_canonical_error=(
                "codex_cli_execution_candidate source_snapshot "
                "not canonical run artifact"
            ),
        )
    candidate_config = payload.get("candidate_config", {})
    if isinstance(candidate_config, dict):
        validate_recorded_file_hash(
            record=candidate_config,
            repo_root=repo_root,
            report=report,
            label="codex_cli_execution_candidate candidate_config",
        )
    else:
        add_error(report, "codex_cli_execution_candidate candidate_config invalid")
    execution_plan = payload.get("execution_plan", {})
    if not isinstance(execution_plan, dict):
        add_error(report, "codex_cli_execution_candidate.json execution_plan invalid")
    else:
        allowed = execution_plan.get("allowed_mutation_paths", [])
        if allowed != ["strategies/current_strategy.py"]:
            add_error(
                report,
                "codex_cli_execution_candidate.json allowed mutation paths invalid",
            )
        if bool(execution_plan.get("execution_enabled_by_this_artifact", True)):
            add_error(report, "codex_cli_execution_candidate.json executes by itself")
        command = execution_plan.get("command", [])
        if not isinstance(command, list):
            add_error(report, "codex_cli_execution_candidate.json command invalid")
        else:
            command_text = " ".join(str(part) for part in command)
            if "strategies/current_strategy.py" not in command_text:
                add_error(
                    report,
                    "codex_cli_execution_candidate.json command missing target file",
                )
            for forbidden in ("data/", "backtester/", "orchestrator/policy_gate.py"):
                if forbidden in command_text:
                    add_error(
                        report,
                        f"codex_cli_execution_candidate.json command contains {forbidden}",
                    )
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "codex_cli_execution_candidate.json policy invalid")
    else:
        for key in (
            "candidate_only",
            "read_only",
            "requires_unlock_snapshot",
            "requires_snapshot_unlocked",
            "requires_candidate_config_hash_match",
            "does_not_execute_codex_cli",
            "does_not_create_workspace",
            "does_not_send_strategy_prompt",
            "does_not_modify_config",
            "does_not_select_candidate",
            "does_not_apply_patches",
            "does_not_change_acceptance",
            "allows_only_strategy_file_mutation",
            "deterministic_code_keeps_acceptance_authority",
        ):
            if not bool(policy.get(key, False)):
                add_error(
                    report,
                    f"codex_cli_execution_candidate.json policy false: {key}",
                )
    markdown_path = run_dir / "codex_cli_execution_candidate.md"
    if markdown_path.exists():
        checked_files(report).append(str(markdown_path))


def validate_optional_codex_cli_real_execution_dry_run(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate codex_cli_real_execution_dry_run.json when a run has one."""
    path = run_dir / "codex_cli_real_execution_dry_run.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/codex_cli_real_execution_dry_run.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"codex_cli_real_execution_dry_run.json run_id does not match report: {path}",
        )
    if bool(payload.get("ok", False)) is not True:
        add_error(report, "codex_cli_real_execution_dry_run.json ok false")
    blockers = payload.get("blocking_reasons", [])
    if not isinstance(blockers, list):
        add_error(report, "codex_cli_real_execution_dry_run.json blockers invalid")
        return
    ready = bool(payload.get("real_execution_dry_run_ready", False))
    if ready and blockers:
        add_error(report, "codex_cli_real_execution_dry_run.json ready with blockers")
    if not ready and not blockers:
        add_error(
            report,
            "codex_cli_real_execution_dry_run.json blocked without reason",
        )
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        add_error(report, "codex_cli_real_execution_dry_run.json checks invalid")
    else:
        for key in (
            "dry_run_does_not_execute_codex_cli",
            "dry_run_does_not_create_workspace",
            "dry_run_does_not_send_strategy_prompt",
            "dry_run_does_not_apply_patches",
            "dry_run_does_not_change_acceptance",
        ):
            if not bool(checks.get(key, False)):
                add_error(
                    report,
                    f"codex_cli_real_execution_dry_run.json safety check false: {key}",
                )
        if ready:
            for key, value in checks.items():
                if not bool(value):
                    add_error(
                        report,
                        f"codex_cli_real_execution_dry_run.json check false: {key}",
                    )
    source_candidate = payload.get("source_candidate", {})
    if not isinstance(source_candidate, dict):
        add_error(
            report,
            "codex_cli_real_execution_dry_run.json source_candidate invalid",
        )
    else:
        validate_source_artifact_provenance(
            source=source_candidate,
            expected_path=run_dir / "codex_cli_execution_candidate.json",
            repo_root=repo_root,
            report=report,
            label="codex_cli_real_execution_dry_run source_candidate",
            invalid_file_error=(
                "codex_cli_real_execution_dry_run candidate file invalid"
            ),
            not_canonical_error=(
                "codex_cli_real_execution_dry_run source_candidate "
                "not canonical run artifact"
            ),
        )
    planned = payload.get("planned_execution", {})
    if not isinstance(planned, dict):
        add_error(report, "codex_cli_real_execution_dry_run.json planned invalid")
    else:
        if planned.get("allowed_mutation_paths", []) != [
            "strategies/current_strategy.py"
        ]:
            add_error(
                report,
                "codex_cli_real_execution_dry_run.json mutation paths invalid",
            )
        command = planned.get("command", [])
        if not isinstance(command, list):
            add_error(report, "codex_cli_real_execution_dry_run.json command invalid")
        else:
            command_text = " ".join(str(part) for part in command)
            if "strategies/current_strategy.py" not in command_text:
                add_error(
                    report,
                    "codex_cli_real_execution_dry_run.json command missing target file",
                )
            for forbidden in ("data/", "backtester/", "orchestrator/policy_gate.py"):
                if forbidden in command_text:
                    add_error(
                        report,
                        f"codex_cli_real_execution_dry_run.json command contains {forbidden}",
                    )
        workspace_path = resolve_path(
            Path(str(planned.get("workspace_path", ""))),
            repo_root,
        )
        if workspace_path.exists():
            add_error(
                report,
                f"codex_cli_real_execution_dry_run workspace exists: {workspace_path}",
            )
    dry_result = payload.get("dry_run_result", {})
    if not isinstance(dry_result, dict):
        add_error(report, "codex_cli_real_execution_dry_run.json result invalid")
    else:
        for key in (
            "execution_performed",
            "subprocess_invoked",
            "workspace_created",
            "patch_applied",
            "acceptance_changed",
        ):
            if bool(dry_result.get(key, True)):
                add_error(
                    report,
                    f"codex_cli_real_execution_dry_run.json result true: {key}",
                )
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "codex_cli_real_execution_dry_run.json policy invalid")
    else:
        for key in (
            "dry_run_only",
            "read_only",
            "requires_execution_candidate",
            "requires_candidate_ready",
            "does_not_execute_codex_cli",
            "does_not_create_workspace",
            "does_not_send_strategy_prompt",
            "does_not_modify_config",
            "does_not_select_candidate",
            "does_not_apply_patches",
            "does_not_change_acceptance",
            "allows_only_strategy_file_mutation",
            "deterministic_code_keeps_acceptance_authority",
        ):
            if not bool(policy.get(key, False)):
                add_error(
                    report,
                    f"codex_cli_real_execution_dry_run.json policy false: {key}",
                )
    markdown_path = run_dir / "codex_cli_real_execution_dry_run.md"
    if markdown_path.exists():
        checked_files(report).append(str(markdown_path))


def validate_optional_codex_cli_readiness_summary(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate codex_cli_readiness_summary.json when a run has one."""
    path = run_dir / "codex_cli_readiness_summary.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/codex_cli_readiness_summary.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"codex_cli_readiness_summary.json run_id does not match report: {path}",
        )
    if bool(payload.get("ok", False)) is not True:
        add_error(report, "codex_cli_readiness_summary.json ok false")
    stages = payload.get("stages", [])
    if not isinstance(stages, list) or len(stages) != 10:
        add_error(report, "codex_cli_readiness_summary.json stages invalid")
    else:
        for stage in stages:
            if not isinstance(stage, dict):
                add_error(report, "codex_cli_readiness_summary.json stage invalid")
                continue
            artifact = stage.get("artifact", {})
            if not isinstance(artifact, dict):
                add_error(
                    report,
                    f"codex_cli_readiness_summary artifact invalid: {stage.get('stage', '')}",
                )
                continue
            artifact_path = resolve_path(Path(str(artifact.get("path", ""))), repo_root)
            if artifact_path.exists():
                checked_files(report).append(str(artifact_path))
            elif bool(artifact.get("exists", False)):
                add_error(
                    report,
                    f"codex_cli_readiness_summary artifact missing: {artifact_path}",
                )
    final_ready = bool(payload.get("final_ready", False))
    readiness_status = str(payload.get("readiness_status", ""))
    if final_ready and readiness_status != "ready_for_operator_review":
        add_error(report, "codex_cli_readiness_summary.json ready/status mismatch")
    if not final_ready and readiness_status != "blocked":
        add_error(report, "codex_cli_readiness_summary.json blocked/status mismatch")
    blockers = payload.get("aggregate_blocking_reasons", [])
    if not isinstance(blockers, list):
        add_error(report, "codex_cli_readiness_summary.json blockers invalid")
    elif not final_ready and not blockers:
        add_error(report, "codex_cli_readiness_summary.json blocked without blockers")
    if isinstance(stages, list) and stages:
        final_stage = stages[-1]
        if (
            isinstance(final_stage, dict)
            and bool(final_stage.get("ready", False)) != final_ready
        ):
            add_error(report, "codex_cli_readiness_summary.json final stage mismatch")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "codex_cli_readiness_summary.json policy invalid")
    else:
        for key in (
            "summary_only",
            "read_only",
            "does_not_execute_codex_cli",
            "does_not_create_workspace",
            "does_not_send_strategy_prompt",
            "does_not_modify_config",
            "does_not_select_candidate",
            "does_not_apply_patches",
            "does_not_change_acceptance",
            "deterministic_code_keeps_acceptance_authority",
        ):
            if not bool(policy.get(key, False)):
                add_error(
                    report,
                    f"codex_cli_readiness_summary.json policy false: {key}",
                )
    markdown_path = run_dir / "codex_cli_readiness_summary.md"
    if markdown_path.exists():
        checked_files(report).append(str(markdown_path))


def validate_optional_codex_cli_readiness_pipeline(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate codex_cli_readiness_pipeline.json when a run has one."""
    path = run_dir / "codex_cli_readiness_pipeline.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/codex_cli_readiness_pipeline.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"codex_cli_readiness_pipeline.json run_id does not match report: {path}",
        )
    if bool(payload.get("ok", False)) is not True:
        add_error(report, "codex_cli_readiness_pipeline.json ok false")
    if bool(payload.get("pipeline_completed", False)) is not True:
        add_error(report, "codex_cli_readiness_pipeline.json pipeline incomplete")
    steps = payload.get("steps", [])
    if not isinstance(steps, list) or len(steps) != 9:
        add_error(report, "codex_cli_readiness_pipeline.json steps invalid")
    else:
        for step in steps:
            if not isinstance(step, dict):
                add_error(report, "codex_cli_readiness_pipeline.json step invalid")
                continue
            artifacts = step.get("artifacts", {})
            if not isinstance(artifacts, dict):
                add_error(
                    report,
                    f"codex_cli_readiness_pipeline step artifacts invalid: {step.get('step', '')}",
                )
                continue
            for key in ("json", "markdown"):
                record = artifacts.get(key, {})
                if not isinstance(record, dict):
                    add_error(
                        report,
                        f"codex_cli_readiness_pipeline step artifact invalid: {key}",
                    )
                    continue
                validate_recorded_file_hash(
                    record=record,
                    repo_root=repo_root,
                    report=report,
                    label=f"codex_cli_readiness_pipeline step {step.get('step', '')}.{key}",
                )
    generated = payload.get("generated_artifacts", {})
    if not isinstance(generated, dict) or not generated:
        add_error(report, "codex_cli_readiness_pipeline.json generated artifacts invalid")
    else:
        for key, record in generated.items():
            if not isinstance(record, dict):
                add_error(
                    report,
                    f"codex_cli_readiness_pipeline generated artifact invalid: {key}",
                )
                continue
            validate_recorded_file_hash(
                record=record,
                repo_root=repo_root,
                report=report,
                label=f"codex_cli_readiness_pipeline generated {key}",
            )
    final_ready = bool(payload.get("final_ready", False))
    readiness_status = str(payload.get("readiness_status", ""))
    if final_ready and readiness_status != "ready_for_operator_review":
        add_error(report, "codex_cli_readiness_pipeline.json ready/status mismatch")
    if not final_ready and readiness_status != "blocked":
        add_error(report, "codex_cli_readiness_pipeline.json blocked/status mismatch")
    blockers = payload.get("blocking_reasons", [])
    if not isinstance(blockers, list):
        add_error(report, "codex_cli_readiness_pipeline.json blockers invalid")
    elif final_ready and blockers:
        add_error(report, "codex_cli_readiness_pipeline.json ready with blockers")
    elif not final_ready and not blockers:
        add_error(report, "codex_cli_readiness_pipeline.json blocked without blockers")
    final_summary = payload.get("final_summary", {})
    if not isinstance(final_summary, dict):
        add_error(report, "codex_cli_readiness_pipeline.json final_summary invalid")
    else:
        if bool(final_summary.get("final_ready", False)) != final_ready:
            add_error(report, "codex_cli_readiness_pipeline.json final summary mismatch")
        summary_record = final_summary.get("file", {})
        if isinstance(summary_record, dict):
            validate_recorded_file_hash(
                record=summary_record,
                repo_root=repo_root,
                report=report,
                label="codex_cli_readiness_pipeline final_summary",
            )
        else:
            add_error(report, "codex_cli_readiness_pipeline.json final summary file invalid")
    options = payload.get("options", {})
    if not isinstance(options, dict):
        add_error(report, "codex_cli_readiness_pipeline.json options invalid")
    elif bool(options.get("execute_dry_invocation", True)):
        dry_guard = load_json_object(run_dir / "codex_cli_dry_invocation_guard.json", report)
        if dry_guard and not bool(dry_guard.get("execution_requested", False)):
            add_error(
                report,
                "codex_cli_readiness_pipeline.json execute option/dry guard mismatch",
            )
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "codex_cli_readiness_pipeline.json policy invalid")
    else:
        for key in (
            "pipeline_only",
            "read_only",
            "does_not_execute_real_codex_strategy_modification",
            "does_not_create_real_execution_workspace",
            "does_not_send_strategy_prompt",
            "does_not_modify_config",
            "does_not_select_candidate",
            "does_not_apply_patches",
            "does_not_change_acceptance",
            "requires_existing_replay_gate",
            "requires_existing_canary_gate",
            "deterministic_code_keeps_acceptance_authority",
        ):
            if not bool(policy.get(key, False)):
                add_error(
                    report,
                    f"codex_cli_readiness_pipeline.json policy false: {key}",
                )
    markdown_path = run_dir / "codex_cli_readiness_pipeline.md"
    if markdown_path.exists():
        checked_files(report).append(str(markdown_path))


def validate_optional_codex_cli_operator_unlock_request(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate codex_cli_operator_unlock_request.json when a run has one."""
    path = run_dir / "codex_cli_operator_unlock_request.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/codex_cli_operator_unlock_request.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            "codex_cli_operator_unlock_request.json run_id does not match report: "
            f"{path}",
        )
    if not artifact_path_matches_run_dir(
        path_text=str(payload.get("run_dir", "")),
        run_dir=run_dir,
        repo_root=repo_root,
    ):
        add_error(
            report,
            "codex_cli_operator_unlock_request.json run_dir does not match report",
        )
    if bool(payload.get("ok", False)) is not True:
        add_error(report, "codex_cli_operator_unlock_request.json ok false")
    blockers = payload.get("blocking_reasons", [])
    if not isinstance(blockers, list):
        add_error(report, "codex_cli_operator_unlock_request.json blockers invalid")
        return
    ready = bool(payload.get("operator_request_ready", False))
    if ready and blockers:
        add_error(report, "codex_cli_operator_unlock_request.json ready with blockers")
    if not ready and not blockers:
        add_error(
            report,
            "codex_cli_operator_unlock_request.json blocked without blockers",
        )
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        add_error(report, "codex_cli_operator_unlock_request.json checks invalid")
    else:
        for key in (
            "request_does_not_execute_codex_cli",
            "request_does_not_create_workspace",
            "request_does_not_send_strategy_prompt",
            "request_does_not_apply_patches",
            "request_does_not_change_acceptance",
        ):
            if not bool(checks.get(key, False)):
                add_error(
                    report,
                    f"codex_cli_operator_unlock_request.json safety check false: {key}",
                )
        for key in (
            "readiness_pipeline_path_is_canonical_run_artifact",
            "real_execution_dry_run_path_is_canonical_run_artifact",
        ):
            if not bool(checks.get(key, False)):
                add_error(
                    report,
                    "codex_cli_operator_unlock_request.json canonical source "
                    f"check false: {key}",
                )
        if ready:
            for key, value in checks.items():
                if not bool(value):
                    add_error(
                        report,
                        f"codex_cli_operator_unlock_request.json check false: {key}",
                    )
    request = payload.get("request", {})
    if not isinstance(request, dict):
        add_error(report, "codex_cli_operator_unlock_request.json request invalid")
    elif ready:
        if not bool(request.get("requested", False)):
            add_error(report, "codex_cli_operator_unlock_request.json requested false")
        if not str(request.get("requested_by", "")).strip():
            add_error(report, "codex_cli_operator_unlock_request.json requested_by missing")
        if not bool(request.get("confirmation_phrase_matches", False)):
            add_error(
                report,
                "codex_cli_operator_unlock_request.json confirmation phrase mismatch",
            )
    source_pipeline = payload.get("source_pipeline", {})
    if isinstance(source_pipeline, dict):
        validate_source_artifact_provenance(
            source=source_pipeline,
            expected_path=run_dir / "codex_cli_readiness_pipeline.json",
            repo_root=repo_root,
            report=report,
            label="codex_cli_operator_unlock_request source_pipeline",
            invalid_file_error=(
                "codex_cli_operator_unlock_request.json "
                "source pipeline file invalid"
            ),
            not_canonical_error=(
                "codex_cli_operator_unlock_request source_pipeline "
                "not canonical run artifact"
            ),
        )
        if ready and not bool(source_pipeline.get("final_ready", False)):
            add_error(
                report,
                "codex_cli_operator_unlock_request.json source pipeline not ready",
            )
    else:
        add_error(report, "codex_cli_operator_unlock_request.json source_pipeline invalid")
    source_dry_run = payload.get("source_real_execution_dry_run", {})
    source_dry_run_plan: dict[str, Any] = {}
    if isinstance(source_dry_run, dict):
        dry_run_record = validate_source_artifact_provenance(
            source=source_dry_run,
            expected_path=run_dir / "codex_cli_real_execution_dry_run.json",
            repo_root=repo_root,
            report=report,
            label="codex_cli_operator_unlock_request source_dry_run",
            invalid_file_error=(
                "codex_cli_operator_unlock_request.json "
                "source dry-run file invalid"
            ),
            not_canonical_error=(
                "codex_cli_operator_unlock_request source_dry_run "
                "not canonical run artifact"
            ),
        )
        if isinstance(dry_run_record, dict):
            dry_run_payload = load_recorded_json_object(
                record=dry_run_record,
                repo_root=repo_root,
                report=report,
                label="codex_cli_operator_unlock_request source_dry_run",
            )
            if isinstance(dry_run_payload, dict):
                source_dry_run_plan = dict_value(
                    dry_run_payload.get("planned_execution", {})
                )
        if ready and not bool(
            source_dry_run.get("real_execution_dry_run_ready", False)
        ):
            add_error(
                report,
                "codex_cli_operator_unlock_request.json source dry-run not ready",
            )
    else:
        add_error(
            report,
            "codex_cli_operator_unlock_request.json source_real_execution_dry_run invalid",
        )
    planned = payload.get("planned_execution_review", {})
    if not isinstance(planned, dict):
        add_error(
            report,
            "codex_cli_operator_unlock_request.json planned execution invalid",
        )
    else:
        expected_identity = {
            "agent_name": "codex_cli",
            "profile_name": "real_codex_execution",
            "round_id": "codex_cli_real_execution",
            "attempt_id": "attempt_001_real_execution",
        }
        for key, expected in expected_identity.items():
            if str(planned.get(key, "")) != expected:
                add_error(
                    report,
                    "codex_cli_operator_unlock_request.json planned "
                    f"{key} mismatch",
                )
        if not source_dry_run_plan:
            add_error(
                report,
                "codex_cli_operator_unlock_request.json source dry-run plan missing",
            )
        elif not source_plan_matches_operator_review(
            source_plan=source_dry_run_plan,
            reviewed_plan=planned,
        ):
            add_error(
                report,
                "codex_cli_operator_unlock_request.json source dry-run plan mismatch",
            )
        expected_workspace_suffix = (
            f"{run_dir.name}/codex_cli_real_execution/real_codex_execution/"
            "attempt_001_real_execution/strategy_workspace"
        )
        if not str(planned.get("workspace_path", "")).endswith(
            expected_workspace_suffix
        ):
            add_error(
                report,
                "codex_cli_operator_unlock_request.json planned workspace_path mismatch",
            )
        if planned.get("allowed_mutation_paths", []) != [
            "strategies/current_strategy.py"
        ]:
            add_error(
                report,
                "codex_cli_operator_unlock_request.json mutation paths invalid",
            )
        if bool(planned.get("execution_enabled_by_this_artifact", True)):
            add_error(
                report,
                "codex_cli_operator_unlock_request.json executes by itself",
            )
        command = planned.get("command", [])
        if not isinstance(command, list):
            add_error(
                report,
                "codex_cli_operator_unlock_request.json command invalid",
            )
        else:
            command_text = " ".join(str(part) for part in command)
            if planned.get("command_sha256") != stable_json_digest(command):
                add_error(
                    report,
                    "codex_cli_operator_unlock_request.json command sha256 mismatch",
                )
            if "strategies/current_strategy.py" not in command_text:
                add_error(
                    report,
                    "codex_cli_operator_unlock_request.json command missing target file",
                )
            for forbidden in ("data/", "backtester/", "orchestrator/policy_gate.py"):
                if forbidden in command_text:
                    add_error(
                        report,
                        "codex_cli_operator_unlock_request.json command contains "
                        f"{forbidden}",
                    )
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "codex_cli_operator_unlock_request.json policy invalid")
    else:
        for key in (
            "operator_request_only",
            "read_only",
            "requires_readiness_pipeline",
            "requires_pipeline_final_ready",
            "requires_real_execution_dry_run_ready",
            "requires_explicit_operator_request",
            "requires_exact_confirmation_phrase",
            "does_not_execute_codex_cli",
            "does_not_create_workspace",
            "does_not_send_strategy_prompt",
            "does_not_modify_config",
            "does_not_select_candidate",
            "does_not_apply_patches",
            "does_not_change_acceptance",
            "allows_only_strategy_file_mutation",
            "deterministic_code_keeps_acceptance_authority",
        ):
            if not bool(policy.get(key, False)):
                add_error(
                    report,
                    f"codex_cli_operator_unlock_request.json policy false: {key}",
                )
    markdown_path = run_dir / "codex_cli_operator_unlock_request.md"
    if markdown_path.exists():
        checked_files(report).append(str(markdown_path))


def snapshot_digest_from_payload(payload: dict[str, object]) -> str:
    """Return the expected digest for a codex_cli_execution_unlock_snapshot payload."""
    core = {
        "source_gate": payload.get("source_gate", {}),
        "real_codex_execution_unlocked": bool(
            payload.get("real_codex_execution_unlocked", False)
        ),
        "blocking_reasons": payload.get("blocking_reasons", []),
        "checks": payload.get("checks", {}),
        "gate_status": payload.get("gate_status", {}),
        "config_binding": payload.get("config_binding", {}),
        "evidence_artifacts": payload.get("evidence_artifacts", {}),
    }
    encoded = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_recorded_file_hash(
    *,
    record: dict[str, object],
    repo_root: Path,
    report: dict[str, object],
    label: str,
    allow_missing_when_recorded_missing: bool = False,
) -> None:
    """Validate one recorded file hash against the current filesystem."""
    exists = bool(record.get("exists", False))
    artifact_path = resolve_path(Path(str(record.get("path", ""))), repo_root)
    if artifact_path.exists():
        checked_files(report).append(str(artifact_path))
    if not exists and allow_missing_when_recorded_missing:
        if artifact_path.exists():
            add_error(
                report,
                f"{label} recorded missing but now exists: {artifact_path}",
            )
        return
    if exists and not artifact_path.exists():
        add_error(report, f"{label} missing: {artifact_path}")
        return
    if not exists:
        add_error(report, f"{label} recorded missing")
        return
    expected_sha256 = str(record.get("sha256", ""))
    actual_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    if expected_sha256 != actual_sha256:
        add_error(report, f"{label} sha256 mismatch")


def validate_declared_record_path(
    *,
    declared_path: str,
    record: dict[str, object],
    repo_root: Path,
    report: dict[str, object],
    label: str,
) -> None:
    """Validate that an artifact path field matches its file record path."""
    recorded_path = str(record.get("path", ""))
    if not declared_path or not recorded_path:
        add_error(report, f"{label} path binding missing")
        return
    normalized_path = normalize_repo_path(declared_path, repo_root)
    if normalized_path != recorded_path:
        add_error(report, f"{label} path mismatch")


def validate_source_artifact_provenance(
    *,
    source: dict[str, object],
    expected_path: Path,
    repo_root: Path,
    report: dict[str, object],
    label: str,
    invalid_file_error: str,
    not_canonical_error: str,
) -> dict[str, object] | None:
    """Validate hash, declared path, and canonical path for one source artifact."""
    record = source.get("file", {})
    if not isinstance(record, dict):
        add_error(report, invalid_file_error)
        return None
    validate_recorded_file_hash(
        record=record,
        repo_root=repo_root,
        report=report,
        label=label,
    )
    validate_declared_record_path(
        declared_path=str(source.get("path", "")),
        record=record,
        repo_root=repo_root,
        report=report,
        label=label,
    )
    if not artifact_path_matches_file(
        path_text=str(source.get("path", "")),
        expected_path=expected_path,
        repo_root=repo_root,
    ):
        add_error(report, not_canonical_error)
    return record


def validate_optional_research_brief(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate research_brief.json/md when a run has one."""
    path = run_dir / "research_brief.json"
    md_path = run_dir / "research_brief.md"
    if not path.exists() and not md_path.exists():
        return
    if not path.exists():
        add_error(report, f"missing research brief JSON artifact: {path}")
        return
    if not md_path.exists():
        add_error(report, f"missing research brief markdown artifact: {md_path}")
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/research_brief.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, f"research_brief.json run_id does not match report: {path}")
    search_space = payload.get("strategy_search_space", {})
    if not isinstance(search_space, dict):
        add_error(report, "research_brief.json strategy_search_space invalid")
    else:
        policy = search_space.get("policy", {})
        if not isinstance(policy, dict):
            add_error(report, "research_brief.json strategy_search_space policy invalid")
        else:
            for key in (
                "advisory_only",
                "does_not_route_agents",
                "does_not_change_acceptance",
            ):
                if policy.get(key) is not True:
                    add_error(
                        report,
                        f"research_brief.json strategy_search_space policy false: {key}",
                    )
    watchlist = payload.get("watchlist_summary", {})
    if not isinstance(watchlist, dict):
        add_error(report, "research_brief.json watchlist_summary invalid")
    else:
        policy = watchlist.get("policy", {})
        if not isinstance(policy, dict):
            add_error(report, "research_brief.json watchlist policy invalid")
        else:
            for key in (
                "inspection_only",
                "reads_saved_artifacts_only",
                "does_not_execute_agents",
                "does_not_run_backtests",
                "does_not_apply_patches",
                "does_not_change_acceptance",
            ):
                if policy.get(key) is not True:
                    add_error(report, f"research_brief.json watchlist policy false: {key}")
    focus = payload.get("recommended_experiment_focus", {})
    if not isinstance(focus, dict):
        add_error(report, "research_brief.json recommended_experiment_focus invalid")
    else:
        policy = focus.get("policy", {})
        if not isinstance(policy, dict):
            add_error(report, "research_brief.json focus policy invalid")
        else:
            for key in (
                "advisory_only",
                "does_not_route_agents",
                "does_not_change_acceptance",
            ):
                if policy.get(key) is not True:
                    add_error(report, f"research_brief.json focus policy false: {key}")


def validate_optional_agent_result_stats(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate agent_result_stats.json when a run has one."""
    path = run_dir / "agent_result_stats.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/agent_result_stats.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, f"agent_result_stats.json run_id does not match report: {path}")


def validate_contract_file(
    *,
    payload_path: Path,
    schema_path: Path,
    report: dict[str, object],
) -> None:
    """Validate a JSON artifact against a schema."""
    if not payload_path.exists():
        return
    if not schema_path.exists():
        add_error(report, f"schema file does not exist: {schema_path}")
        return
    try:
        errors = validate_json_file(payload_path=payload_path, schema_path=schema_path)
    except Exception as exc:
        add_error(report, f"could not validate {payload_path}: {exc}")
        return
    for error in errors:
        add_error(report, f"{payload_path}: {error}")


def validate_json_object(*, path: Path, report: dict[str, object]) -> dict[str, Any] | None:
    """Load a JSON object artifact."""
    payload = load_json_object(path, report)
    return payload


def validate_json_list(*, path: Path, report: dict[str, object]) -> list[Any] | None:
    """Load a JSON list artifact."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        add_error(report, f"could not read JSON artifact {path}: {exc}")
        return None
    if not isinstance(payload, list):
        add_error(report, f"JSON artifact must be a list: {path}")
        return None
    return payload


def load_json_object(path: Path, report: dict[str, object]) -> dict[str, Any] | None:
    """Load a JSON object artifact."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        add_error(report, f"could not read JSON artifact {path}: {exc}")
        return None
    if not isinstance(payload, dict):
        add_error(report, f"JSON artifact must be an object: {path}")
        return None
    return payload


def round_ids_from_manifest(manifest: dict[str, Any]) -> list[str]:
    """Return round ids from an iteration manifest."""
    raw_rounds = manifest.get("rounds", [])
    if not isinstance(raw_rounds, list):
        return []
    round_ids: list[str] = []
    for row in raw_rounds:
        if isinstance(row, dict) and isinstance(row.get("round_id"), str):
            round_ids.append(str(row["round_id"]))
    return round_ids


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve paths relative to the repository root."""
    return path if path.is_absolute() else repo_root / path


def normalize_repo_path(path_text: str, repo_root: Path) -> str:
    """Return a stable repository-relative path when possible."""
    path = resolve_path(Path(path_text), repo_root)
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def artifact_path_matches_run_dir(
    *,
    path_text: str,
    run_dir: Path,
    repo_root: Path,
) -> bool:
    """Return whether a run_dir artifact path points at the current run."""
    if not path_text:
        return False
    return resolve_path(Path(path_text), repo_root).resolve() == run_dir.resolve()


def artifact_path_matches_file(
    *,
    path_text: str,
    expected_path: Path,
    repo_root: Path,
) -> bool:
    """Return whether an artifact path points at one expected file."""
    if not path_text:
        return False
    return resolve_path(Path(path_text), repo_root).resolve() == expected_path.resolve()


def checked_files(report: dict[str, object]) -> list[str]:
    """Return the mutable checked_files list from a report."""
    return report["checked_files"]  # type: ignore[return-value]


def add_error(report: dict[str, object], message: str) -> None:
    """Append an error to a validation report."""
    errors = report["errors"]  # type: ignore[assignment]
    errors.append(message)


def add_warning(report: dict[str, object], message: str) -> None:
    """Append a warning to a validation report."""
    warnings = report["warnings"]  # type: ignore[assignment]
    warnings.append(message)


def main() -> None:
    """CLI entrypoint for artifact validation."""
    parser = argparse.ArgumentParser(description="Validate SuanAgent run artifacts.")
    parser.add_argument("run_id", help="Experiment run id under experiments/.")
    parser.add_argument(
        "--experiments-dir",
        type=Path,
        default=Path("experiments"),
        help="Directory containing experiment artifacts.",
    )
    args = parser.parse_args()

    payload = validate_run_artifacts(
        run_id=args.run_id,
        experiments_dir=args.experiments_dir,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
