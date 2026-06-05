"""Validate experiment artifacts and agent contract files."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
from pathlib import Path
from typing import Any

from orchestrator.codex_cli_intake_readiness import (
    validate_codex_cli_intake_readiness,
)
from orchestrator.operator_command_boundaries import classify_operator_command
from orchestrator.run_outcome import build_run_outcome_summary
from orchestrator.run_summary import (
    best_validation_round,
    candidate_leaderboard_row,
    format_number,
    proposal_quality_row,
    round_table_row,
)
from orchestrator.schema_validation import validate_json_file


TERMINAL_ONLY_SCHEMA_REFERENCES = (
    "schemas/operator_action_guide.schema.json",
    "schemas/operator_home.schema.json",
    "schemas/operator_next_command.schema.json",
)


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
    "candidate_quality_trace.json",
    "candidate_quality_trace.md",
    "modifier_profile_recommendation.json",
    "modifier_profile_recommendation.md",
    "memory_hygiene.json",
    "memory_hygiene.md",
    "memory_scope_recommendation.json",
    "memory_scope_recommendation.md",
    "config_change_candidate.json",
    "config_change_candidate.md",
    "operator_config_review.json",
    "operator_config_review.md",
    "config_application_dry_run.json",
    "config_application_dry_run.md",
    "config_lineage.json",
    "config_lineage.md",
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
    ignored_iteration_required_files: tuple[str, ...] = (),
    validate_diagnosis: bool = True,
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
        validate_iteration_run(
            run_dir=run_dir,
            repo_root=repo_root,
            report=report,
            ignored_required_files=ignored_iteration_required_files,
        )
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

    if validate_diagnosis:
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
    validate_optional_config_application_receipt(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_config_application_rollback_preview(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_config_application_restore_receipt(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_config_operator_runbook(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_config_lineage(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_run_closeout(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_operator_action_plan(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_operator_action_approval(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_operator_action_execution_receipt(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_operator_action_audit(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_operator_action_dashboard(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_operator_unlock_checklist(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_operator_cockpit(
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
    validate_optional_codex_cli_unlock_runbook(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_codex_cli_execution_readiness_diff(
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
    ignored_required_files: tuple[str, ...] = (),
) -> None:
    """Validate an iteration-loop run directory."""
    validate_required_files(
        base_dir=run_dir,
        filenames=ITERATION_RUN_REQUIRED_FILES,
        report=report,
        ignored_filenames=ignored_required_files,
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
    validate_candidate_quality_trace(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    if (
        "modifier_profile_recommendation.json" not in ignored_required_files
        or (run_dir / "modifier_profile_recommendation.json").exists()
    ):
        validate_modifier_profile_recommendation(
            run_dir=run_dir,
            repo_root=repo_root,
            report=report,
        )
    validate_memory_hygiene(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_memory_scope_recommendation(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_config_change_candidate(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_operator_config_review(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_config_application_dry_run(
        run_dir=run_dir,
        repo_root=repo_root,
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
    validate_manifest_agent_intake_summary(manifest=manifest, report=report)
    validate_manifest_run_outcome_summary(manifest=manifest, report=report)
    validate_iteration_summary_header(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_datasets(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_run_outcome(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_agent_intake(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_scope_health(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_artifact_health_history(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_config_application_dry_run(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_best_validation_delta(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_rounds(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_proposal_quality(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_candidate_leaderboard(
        run_dir=run_dir,
        report=report,
    )
    validate_iteration_summary_config_lineage(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_config_operator_runbook(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_candidate_challenger_report(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_champion_promotion_dry_run(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_champion_promotion_approval(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_run_closeout(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_operator_action_plan(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_operator_action_dashboard(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_operator_unlock_checklist(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_codex_cli_unlock_runbook(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_operator_cockpit(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_operator_home(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )
    validate_iteration_summary_operator_next_command(
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )

    for round_id in round_ids:
        round_dir = run_dir / round_id
        validate_round_dir(round_dir=round_dir, repo_root=repo_root, report=report)
    report["rounds_checked"] = len(round_ids)


def validate_manifest_run_outcome_summary(
    *,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate manifest-level run outcome summary consistency when present."""
    summary = manifest.get("run_outcome_summary")
    if not isinstance(summary, dict):
        return
    expected = build_run_outcome_summary(manifest=manifest)
    for key in (
        "status",
        "accepted",
        "category",
        "primary_stage",
        "primary_code",
        "primary_message",
        "completed_rounds",
        "accepted_round",
        "final_strategy_commit",
        "category_counts",
        "stage_counts",
        "code_counts",
    ):
        if summary.get(key) != expected.get(key):
            add_error(report, f"manifest.run_outcome_summary {key} mismatch")


def validate_manifest_agent_intake_summary(
    *,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate manifest-level agent-intake summary consistency when present."""
    summary = manifest.get("agent_intake_summary")
    if not isinstance(summary, dict):
        return
    expected = expected_agent_intake_summary(manifest.get("rounds", []))
    for key in (
        "round_count",
        "blocked_round_count",
        "passed_round_count",
        "retryable_round_count",
        "primary_stage",
        "primary_code",
        "top_blocking_code",
    ):
        if summary.get(key) != expected.get(key):
            add_error(report, f"manifest.agent_intake_summary {key} mismatch")
    if summary.get("code_counts") != expected.get("code_counts"):
        add_error(report, "manifest.agent_intake_summary code_counts mismatch")
    if summary.get("status_counts") != expected.get("status_counts"):
        add_error(report, "manifest.agent_intake_summary status_counts mismatch")


def validate_iteration_summary_header(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md top-level run fields mirror manifest.json."""
    summary_text = read_optional_text(run_dir / "summary.md")
    if not summary_text:
        add_error(report, "summary.md iteration header missing")
        return
    expected_lines: tuple[tuple[str, str], ...] = (
        ("title", "# Experiment Summary"),
        ("run_id", f"- Run id: `{markdown_display_value(manifest.get('run_id'))}`"),
        ("kind", "- Kind: `iteration_loop`"),
        ("status", f"- Status: `{markdown_display_value(manifest.get('status'))}`"),
        (
            "completed_rounds",
            "- Completed rounds: "
            f"`{markdown_display_value(manifest.get('completed_rounds'))}`",
        ),
        (
            "accepted_round",
            "- Accepted round: "
            f"`{markdown_display_value(manifest.get('accepted_round'))}`",
        ),
        (
            "stop_reason",
            "- Stop reason: "
            f"`{markdown_display_value(manifest.get('stop_reason'))}`",
        ),
        (
            "final_strategy_commit",
            "- Final strategy commit: "
            f"`{markdown_display_value(manifest.get('final_strategy_commit'))}`",
        ),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in summary_text:
            add_error(report, f"summary.md iteration header {field_name} mismatch")


def validate_iteration_summary_datasets(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md dataset rows mirror manifest.datasets."""
    datasets = manifest.get("datasets")
    if not isinstance(datasets, dict):
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Datasets",
    )
    if not section:
        add_error(report, "summary.md datasets section missing")
        return
    for split in ("train", "validation", "holdout"):
        if split not in datasets:
            continue
        expected_line = f"- {split}: `{markdown_display_value(datasets.get(split))}`"
        if expected_line not in section:
            add_error(report, f"summary.md datasets {split} mismatch")


def validate_iteration_summary_run_outcome(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md run-outcome section mirrors manifest.json."""
    outcome_summary = manifest.get("run_outcome_summary")
    if not isinstance(outcome_summary, dict):
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Run Outcome Summary",
    )
    if not section:
        add_error(report, "summary.md run_outcome_summary section missing")
        return
    expected_lines: tuple[tuple[str, str], ...] = (
        (
            "category",
            f"- Category: `{markdown_display_value(outcome_summary.get('category'))}`",
        ),
        (
            "primary_code",
            "- Primary code: "
            f"`{markdown_display_value(outcome_summary.get('primary_code'))}`",
        ),
        (
            "primary_stage",
            "- Primary stage: "
            f"`{markdown_display_value(outcome_summary.get('primary_stage'))}`",
        ),
        (
            "primary_message",
            "- Primary message: "
            f"{markdown_escape_text(markdown_display_value(outcome_summary.get('primary_message')))}",
        ),
        (
            "artifact_ok",
            "- Artifact OK: "
            f"`{markdown_display_value(outcome_summary.get('artifact_ok'))}`",
        ),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in section:
            add_error(report, f"summary.md run_outcome_summary {field_name} mismatch")


def validate_iteration_summary_agent_intake(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md agent-intake section mirrors manifest.json."""
    intake_summary = manifest.get("agent_intake_summary")
    if not isinstance(intake_summary, dict):
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Agent Intake Summary",
    )
    if not section:
        add_error(report, "summary.md agent_intake_summary section missing")
        return
    expected_lines: tuple[tuple[str, str], ...] = (
        (
            "blocked_round_count",
            "- Blocked rounds: "
            f"`{markdown_display_value(intake_summary.get('blocked_round_count'))}`",
        ),
        (
            "passed_round_count",
            "- Passed rounds: "
            f"`{markdown_display_value(intake_summary.get('passed_round_count'))}`",
        ),
        (
            "primary_code",
            "- Primary code: "
            f"`{markdown_display_value(intake_summary.get('primary_code'))}`",
        ),
        (
            "top_blocking_code",
            "- Top blocking code: "
            f"`{markdown_display_value(intake_summary.get('top_blocking_code'))}`",
        ),
        (
            "retryable_round_count",
            "- Retryable rounds: "
            f"`{markdown_display_value(intake_summary.get('retryable_round_count'))}`",
        ),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in section:
            add_error(report, f"summary.md agent_intake_summary {field_name} mismatch")


def validate_iteration_summary_scope_health(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md experiment-scope-health section mirrors manifest.json."""
    scope_health = manifest.get("experiment_scope_health")
    if not isinstance(scope_health, dict):
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Experiment Scope Health",
    )
    if not section:
        add_error(report, "summary.md experiment_scope_health section missing")
        return
    expected_lines: tuple[tuple[str, str], ...] = (
        ("status", f"- Status: `{markdown_display_value(scope_health.get('status'))}`"),
        ("ok", f"- OK: `{markdown_display_value(scope_health.get('ok'))}`"),
        (
            "created_at_from",
            "- Scope created_at_from: "
            f"`{markdown_display_value(scope_health.get('created_at_from'))}`",
        ),
        (
            "scoped_run_count",
            "- Scoped run count: "
            f"`{markdown_display_value(scope_health.get('scoped_run_count'))}`",
        ),
        ("path", f"- Artifact: `{markdown_display_value(scope_health.get('path'))}`"),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in section:
            add_error(report, f"summary.md experiment_scope_health {field_name} mismatch")


def validate_iteration_summary_artifact_health_history(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md artifact-health-history section mirrors manifest.json."""
    health_history = manifest.get("artifact_health_history")
    if not isinstance(health_history, dict):
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Artifact Health History",
    )
    if not section:
        add_error(report, "summary.md artifact_health_history section missing")
        return
    expected_lines: tuple[tuple[str, str], ...] = (
        (
            "recorded",
            f"- Recorded: `{markdown_display_value(health_history.get('recorded'))}`",
        ),
        ("ok", f"- OK: `{markdown_display_value(health_history.get('ok'))}`"),
        (
            "created_at_from",
            "- Scope created_at_from: "
            f"`{markdown_display_value(health_history.get('created_at_from'))}`",
        ),
        (
            "scoped_run_count",
            "- Scoped run count: "
            f"`{markdown_display_value(health_history.get('scoped_run_count'))}`",
        ),
        (
            "failed_run_count",
            "- Failed run count: "
            f"`{markdown_display_value(health_history.get('failed_run_count'))}`",
        ),
        ("path", f"- History: `{markdown_display_value(health_history.get('path'))}`"),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in section:
            add_error(
                report,
                f"summary.md artifact_health_history {field_name} mismatch",
            )


def validate_iteration_summary_config_application_dry_run(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md config-application dry-run section mirrors manifest."""
    dry_run = manifest.get("config_application_dry_run")
    if not isinstance(dry_run, dict):
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Config Application Dry Run",
    )
    if not section:
        add_error(report, "summary.md config_application_dry_run section missing")
        return
    expected_lines: tuple[tuple[str, str], ...] = (
        ("status", f"- Status: `{markdown_display_value(dry_run.get('status'))}`"),
        (
            "eligible_for_manual_application",
            "- Eligible for manual application: "
            f"`{markdown_display_value(dry_run.get('eligible_for_manual_application'))}`",
        ),
        ("path", f"- Artifact: `{markdown_display_value(dry_run.get('path'))}`"),
        (
            "markdown_path",
            "- Markdown: "
            f"`{markdown_display_value(dry_run.get('markdown_path'))}`",
        ),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in section:
            add_error(
                report,
                f"summary.md config_application_dry_run {field_name} mismatch",
            )


def validate_iteration_summary_best_validation_delta(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md best-validation delta mirrors manifest rounds."""
    rounds = [
        round_payload
        for round_payload in manifest.get("rounds", [])
        if isinstance(round_payload, dict)
    ]
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Best Validation Delta",
    )
    if not section:
        add_error(report, "summary.md best_validation_delta section missing")
        return
    best_round = best_validation_round(rounds)
    if best_round is None:
        expected_line = "No completed rounds."
    else:
        before = float(best_round.get("validation_ev_before", 0.0))
        after = float(best_round.get("validation_ev_after", 0.0))
        expected_line = (
            f"- {best_round.get('round_id')}: `{format_number(after - before)}` "
            f"({format_number(before)} -> {format_number(after)})"
        )
    if expected_line not in section:
        add_error(report, "summary.md best_validation_delta row mismatch")


def validate_iteration_summary_rounds(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md round table rows mirror manifest round records."""
    rounds = [
        round_payload
        for round_payload in manifest.get("rounds", [])
        if isinstance(round_payload, dict)
    ]
    if not rounds:
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Rounds",
    )
    if not section:
        add_error(report, "summary.md rounds section missing")
        return
    for round_payload in rounds:
        round_id = markdown_display_value(round_payload.get("round_id"))
        expected_line = round_table_row(run_dir, round_payload)
        if expected_line not in section:
            add_error(report, f"summary.md rounds {round_id} row mismatch")


def validate_iteration_summary_proposal_quality(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md proposal-quality rows mirror round proposal artifacts."""
    rounds = [
        round_payload
        for round_payload in manifest.get("rounds", [])
        if isinstance(round_payload, dict)
    ]
    if not rounds:
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Proposal Quality",
    )
    if not section:
        add_error(report, "summary.md proposal_quality section missing")
        return
    for round_payload in rounds:
        round_id = markdown_display_value(round_payload.get("round_id"))
        expected_line = proposal_quality_row(run_dir, round_payload)
        if expected_line not in section:
            add_error(report, f"summary.md proposal_quality {round_id} row mismatch")


def validate_iteration_summary_candidate_leaderboard(
    *,
    run_dir: Path,
    report: dict[str, object],
) -> None:
    """Validate summary.md candidate leaderboard rows mirror the JSON artifact."""
    candidate_rows = list_of_dicts(load_json_list(run_dir / "candidate_leaderboard.json"))
    if not candidate_rows:
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Candidate Leaderboard",
    )
    if not section:
        add_error(report, "summary.md candidate_leaderboard section missing")
        return
    for index, row in enumerate(candidate_rows[:10], start=1):
        expected_line = candidate_leaderboard_row(row)
        if expected_line not in section:
            add_error(report, f"summary.md candidate_leaderboard row_{index} mismatch")


def validate_iteration_summary_config_lineage(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md config-lineage section mirrors manifest."""
    lineage = manifest.get("config_lineage")
    if not isinstance(lineage, dict):
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Config Lineage",
    )
    if not section:
        add_error(report, "summary.md config_lineage section missing")
        return
    expected_lines: tuple[tuple[str, str], ...] = (
        ("status", f"- Status: `{markdown_display_value(lineage.get('status'))}`"),
        ("ok", f"- OK: `{markdown_display_value(lineage.get('ok'))}`"),
        (
            "existing_stage_count",
            "- Existing stages: "
            f"`{markdown_display_value(lineage.get('existing_stage_count'))}`",
        ),
        ("path", f"- Artifact: `{markdown_display_value(lineage.get('path'))}`"),
        (
            "markdown_path",
            "- Markdown: "
            f"`{markdown_display_value(lineage.get('markdown_path'))}`",
        ),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in section:
            add_error(report, f"summary.md config_lineage {field_name} mismatch")


def validate_iteration_summary_config_operator_runbook(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md config-operator-runbook section mirrors manifest."""
    runbook = manifest.get("config_operator_runbook")
    if not isinstance(runbook, dict):
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Config Operator Runbook",
    )
    if not section:
        add_error(report, "summary.md config_operator_runbook section missing")
        return
    expected_lines: tuple[tuple[str, str], ...] = (
        ("status", f"- Status: `{markdown_display_value(runbook.get('status'))}`"),
        ("ready", f"- Ready: `{markdown_display_value(runbook.get('ready'))}`"),
        (
            "workflow_phase",
            "- Workflow phase: "
            f"`{markdown_display_value(runbook.get('workflow_phase'))}`",
        ),
        (
            "next_command_label",
            "- Next command: "
            f"`{markdown_display_value(runbook.get('next_command_label'))}`",
        ),
        (
            "step_counts",
            "- Ready / blocked / missing steps: "
            f"`{markdown_display_value(runbook.get('ready_step_count'))}` / "
            f"`{markdown_display_value(runbook.get('blocked_step_count'))}` / "
            f"`{markdown_display_value(runbook.get('missing_step_count'))}`",
        ),
        ("path", f"- Artifact: `{markdown_display_value(runbook.get('path'))}`"),
        (
            "markdown_path",
            "- Markdown: "
            f"`{markdown_display_value(runbook.get('markdown_path'))}`",
        ),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in section:
            add_error(
                report,
                f"summary.md config_operator_runbook {field_name} mismatch",
            )


def validate_iteration_summary_candidate_challenger_report(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md candidate-challenger section mirrors manifest."""
    challenger = manifest.get("candidate_challenger_report")
    if not isinstance(challenger, dict):
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Candidate Challenger Report",
    )
    if not section:
        add_error(report, "summary.md candidate_challenger_report section missing")
        return
    expected_lines: tuple[tuple[str, str], ...] = (
        (
            "status",
            f"- Status: `{markdown_display_value(challenger.get('status'))}`",
        ),
        ("ok", f"- OK: `{markdown_display_value(challenger.get('ok'))}`"),
        (
            "path",
            f"- Artifact: `{markdown_display_value(challenger.get('path'))}`",
        ),
        (
            "markdown_path",
            "- Markdown: "
            f"`{markdown_display_value(challenger.get('markdown_path'))}`",
        ),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in section:
            add_error(
                report,
                f"summary.md candidate_challenger_report {field_name} mismatch",
            )


def validate_iteration_summary_champion_promotion_dry_run(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md champion-promotion dry-run section mirrors manifest."""
    promotion = manifest.get("champion_promotion_dry_run")
    if not isinstance(promotion, dict):
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Champion Promotion Dry Run",
    )
    if not section:
        add_error(report, "summary.md champion_promotion_dry_run section missing")
        return
    expected_lines: tuple[tuple[str, str], ...] = (
        ("status", f"- Status: `{markdown_display_value(promotion.get('status'))}`"),
        ("ok", f"- OK: `{markdown_display_value(promotion.get('ok'))}`"),
        (
            "would_promote",
            "- Would promote: "
            f"`{markdown_display_value(promotion.get('would_promote'))}`",
        ),
        ("path", f"- Artifact: `{markdown_display_value(promotion.get('path'))}`"),
        (
            "markdown_path",
            "- Markdown: "
            f"`{markdown_display_value(promotion.get('markdown_path'))}`",
        ),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in section:
            add_error(
                report,
                f"summary.md champion_promotion_dry_run {field_name} mismatch",
            )


def validate_iteration_summary_champion_promotion_approval(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md champion-promotion approval section mirrors manifest."""
    approval = manifest.get("champion_promotion_approval")
    if not isinstance(approval, dict):
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Champion Promotion Approval",
    )
    if not section:
        add_error(report, "summary.md champion_promotion_approval section missing")
        return
    expected_lines: tuple[tuple[str, str], ...] = (
        ("status", f"- Status: `{markdown_display_value(approval.get('status'))}`"),
        ("ok", f"- OK: `{markdown_display_value(approval.get('ok'))}`"),
        (
            "approval_recorded",
            "- Approval recorded: "
            f"`{markdown_display_value(approval.get('approval_recorded'))}`",
        ),
        ("path", f"- Artifact: `{markdown_display_value(approval.get('path'))}`"),
        (
            "markdown_path",
            "- Markdown: "
            f"`{markdown_display_value(approval.get('markdown_path'))}`",
        ),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in section:
            add_error(
                report,
                f"summary.md champion_promotion_approval {field_name} mismatch",
            )


def validate_iteration_summary_run_closeout(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md run-closeout section mirrors manifest."""
    closeout = manifest.get("run_closeout")
    if not isinstance(closeout, dict):
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Run Closeout",
    )
    if not section:
        add_error(report, "summary.md run_closeout section missing")
        return
    expected_lines: tuple[tuple[str, str], ...] = (
        ("status", f"- Status: `{markdown_display_value(closeout.get('status'))}`"),
        ("ok", f"- OK: `{markdown_display_value(closeout.get('ok'))}`"),
        ("path", f"- Artifact: `{markdown_display_value(closeout.get('path'))}`"),
        (
            "markdown_path",
            "- Markdown: "
            f"`{markdown_display_value(closeout.get('markdown_path'))}`",
        ),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in section:
            add_error(report, f"summary.md run_closeout {field_name} mismatch")


def validate_iteration_summary_operator_action_plan(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md operator-action-plan section mirrors manifest."""
    action_plan = manifest.get("operator_action_plan")
    if not isinstance(action_plan, dict):
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Operator Action Plan",
    )
    if not section:
        add_error(report, "summary.md operator_action_plan section missing")
        return
    expected_lines: tuple[tuple[str, str], ...] = (
        (
            "status",
            f"- Status: `{markdown_display_value(action_plan.get('status'))}`",
        ),
        ("ok", f"- OK: `{markdown_display_value(action_plan.get('ok'))}`"),
        (
            "action_count",
            "- Action count: "
            f"`{markdown_display_value(action_plan.get('action_count'))}`",
        ),
        (
            "path",
            f"- Artifact: `{markdown_display_value(action_plan.get('path'))}`",
        ),
        (
            "markdown_path",
            "- Markdown: "
            f"`{markdown_display_value(action_plan.get('markdown_path'))}`",
        ),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in section:
            add_error(
                report,
                f"summary.md operator_action_plan {field_name} mismatch",
            )


def validate_iteration_summary_operator_action_dashboard(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md operator-action-dashboard section mirrors manifest."""
    dashboard = manifest.get("operator_action_dashboard")
    if not isinstance(dashboard, dict):
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Operator Action Dashboard",
    )
    if not section:
        add_error(report, "summary.md operator_action_dashboard section missing")
        return
    expected_lines: tuple[tuple[str, str], ...] = (
        ("status", f"- Status: `{markdown_display_value(dashboard.get('status'))}`"),
        ("ok", f"- OK: `{markdown_display_value(dashboard.get('ok'))}`"),
        (
            "current_step",
            "- Current step: "
            f"`{markdown_display_value(dashboard.get('current_step'))}`",
        ),
        ("path", f"- Artifact: `{markdown_display_value(dashboard.get('path'))}`"),
        (
            "markdown_path",
            "- Markdown: "
            f"`{markdown_display_value(dashboard.get('markdown_path'))}`",
        ),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in section:
            add_error(
                report,
                f"summary.md operator_action_dashboard {field_name} mismatch",
            )


def validate_iteration_summary_operator_unlock_checklist(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md operator-unlock-checklist section mirrors manifest."""
    checklist = manifest.get("operator_unlock_checklist")
    if not isinstance(checklist, dict):
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Operator Unlock Checklist",
    )
    if not section:
        add_error(report, "summary.md operator_unlock_checklist section missing")
        return
    expected_lines: tuple[tuple[str, str], ...] = (
        ("status", f"- Status: `{markdown_display_value(checklist.get('status'))}`"),
        ("ready", f"- Ready: `{markdown_display_value(checklist.get('ready'))}`"),
        (
            "failed_count",
            "- Failed items: "
            f"`{markdown_display_value(checklist.get('failed_count'))}`",
        ),
        (
            "navigation_blocking_count",
            "- Blocking navigation items: "
            f"`{markdown_display_value(checklist.get('navigation_blocking_count'))}`",
        ),
        (
            "primary_blocker",
            "- Primary blocker: "
            f"`{markdown_display_value(checklist.get('primary_blocker'))}`",
        ),
        (
            "command_hint_count",
            "- Command hints: "
            f"`{markdown_display_value(checklist.get('command_hint_count'))}`",
        ),
        ("path", f"- Artifact: `{markdown_display_value(checklist.get('path'))}`"),
        (
            "markdown_path",
            "- Markdown: "
            f"`{markdown_display_value(checklist.get('markdown_path'))}`",
        ),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in section:
            add_error(
                report,
                f"summary.md operator_unlock_checklist {field_name} mismatch",
            )


def validate_iteration_summary_codex_cli_unlock_runbook(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md Codex CLI unlock-runbook section mirrors manifest."""
    runbook = manifest.get("codex_cli_unlock_runbook")
    if not isinstance(runbook, dict):
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Codex CLI Unlock Runbook",
    )
    if not section:
        add_error(report, "summary.md codex_cli_unlock_runbook section missing")
        return
    expected_lines: tuple[tuple[str, str], ...] = (
        ("status", f"- Status: `{markdown_display_value(runbook.get('status'))}`"),
        ("ready", f"- Ready: `{markdown_display_value(runbook.get('ready'))}`"),
        (
            "step_counts",
            "- Ready / blocked / missing steps: "
            f"`{markdown_display_value(runbook.get('ready_step_count'))}` / "
            f"`{markdown_display_value(runbook.get('blocked_step_count'))}` / "
            f"`{markdown_display_value(runbook.get('missing_step_count'))}`",
        ),
        (
            "codex_intake_readiness_status",
            "- Codex intake: "
            f"`{markdown_display_value(runbook.get('codex_intake_readiness_status'))}`",
        ),
        ("path", f"- Artifact: `{markdown_display_value(runbook.get('path'))}`"),
        (
            "markdown_path",
            "- Markdown: "
            f"`{markdown_display_value(runbook.get('markdown_path'))}`",
        ),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in section:
            add_error(
                report,
                f"summary.md codex_cli_unlock_runbook {field_name} mismatch",
            )


def validate_iteration_summary_operator_cockpit(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md operator-cockpit section mirrors manifest.json."""
    cockpit = manifest.get("operator_cockpit")
    if not isinstance(cockpit, dict):
        return
    section = markdown_section(
        read_optional_text(run_dir / "summary.md"),
        "## Operator Cockpit",
    )
    if not section:
        add_error(report, "summary.md operator_cockpit section missing")
        return
    expected_lines: tuple[tuple[str, str], ...] = (
        ("status", f"- Status: `{markdown_display_value(cockpit.get('status'))}`"),
        ("ok", f"- OK: `{markdown_display_value(cockpit.get('ok'))}`"),
        (
            "primary_focus",
            "- Primary focus: "
            f"`{markdown_display_value(cockpit.get('primary_focus'))}`",
        ),
        (
            "codex_unlock_status",
            "- Codex unlock: "
            f"`{markdown_display_value(cockpit.get('codex_unlock_status'))}`",
        ),
        (
            "codex_unlock_failed_count",
            "- Codex unlock failed items: "
            f"`{markdown_display_value(cockpit.get('codex_unlock_failed_count'))}`",
        ),
        ("path", f"- Artifact: `{markdown_display_value(cockpit.get('path'))}`"),
        (
            "markdown_path",
            "- Markdown: "
            f"`{markdown_display_value(cockpit.get('markdown_path'))}`",
        ),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in section:
            add_error(report, f"summary.md operator_cockpit {field_name} mismatch")


def validate_iteration_summary_operator_home(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md operator-home navigation mirrors the manifest row."""
    operator_home = manifest.get("operator_home")
    if not isinstance(operator_home, dict):
        return
    summary_path = run_dir / "summary.md"
    summary_text = read_optional_text(summary_path)
    if not summary_text:
        return
    if "## Operator Home" not in summary_text:
        add_error(report, "summary.md operator_home section missing")
        return

    expected_lines: tuple[tuple[str, str], ...] = (
        ("status", f"- Status: `{markdown_display_value(operator_home.get('status'))}`"),
        ("ok", f"- OK: `{markdown_display_value(operator_home.get('ok'))}`"),
        (
            "terminal_only",
            "- Terminal only: "
            f"`{markdown_display_value(operator_home.get('terminal_only'))}`",
        ),
        (
            "artifact_created",
            "- Artifact created: "
            f"`{markdown_display_value(operator_home.get('artifact_created'))}`",
        ),
        (
            "primary_focus",
            "- Primary focus: "
            f"`{markdown_display_value(operator_home.get('primary_focus'))}`",
        ),
        (
            "action_step",
            "- Action step: "
            f"`{markdown_display_value(operator_home.get('action_step'))}`",
        ),
        (
            "next_command_label",
            "- Next command: "
            f"`{markdown_display_value(operator_home.get('next_command_label'))}`",
        ),
        (
            "next_command",
            "- Next command text: "
            f"`{markdown_display_value(operator_home.get('next_command'))}`",
        ),
        (
            "next_command_boundary",
            "- Next command boundary: "
            f"`{markdown_display_value(operator_home.get('next_command_boundary'))}`",
        ),
        (
            "next_command_status",
            "- Next command status: "
            f"`{markdown_display_value(operator_home.get('next_command_status'))}`",
        ),
        (
            "next_command_blocked",
            "- Next command blocked: "
            f"`{markdown_display_value(operator_home.get('next_command_blocked'))}`",
        ),
        (
            "next_command_blocker_count",
            "- Next command blockers: "
            f"`{markdown_display_value(operator_home.get('next_command_blocker_count'))}`",
        ),
        (
            "next_command_operator_hint",
            "- Next command operator hint: "
            f"{markdown_display_value(operator_home.get('next_command_operator_hint'))}",
        ),
        (
            "next_command_writes_artifact",
            "- Next command writes: "
            f"`{markdown_display_value(operator_home.get('next_command_writes_artifact'))}`",
        ),
        (
            "next_command_requires_explicit_operator_invocation",
            "- Next command requires explicit invocation: "
            f"`{markdown_display_value(operator_home.get('next_command_requires_explicit_operator_invocation'))}`",
        ),
        (
            "next_command_requires_operator_approval",
            "- Next command requires approval: "
            f"`{markdown_display_value(operator_home.get('next_command_requires_operator_approval'))}`",
        ),
        (
            "next_command_records_operator_approval",
            "- Next command records approval: "
            f"`{markdown_display_value(operator_home.get('next_command_records_operator_approval'))}`",
        ),
        (
            "next_command_uses_guarded_executor",
            "- Next command uses guarded executor: "
            f"`{markdown_display_value(operator_home.get('next_command_uses_guarded_executor'))}`",
        ),
        (
            "next_command_is_hint_only",
            "- Next command hint-only: "
            f"`{markdown_display_value(operator_home.get('next_command_is_hint_only'))}`",
        ),
        (
            "codex_unlock_runbook_status",
            "- Codex unlock runbook: "
            f"`{markdown_display_value(operator_home.get('codex_unlock_runbook_status'))}`",
        ),
        (
            "codex_intake_readiness_status",
            "- Codex intake: "
            f"`{markdown_display_value(operator_home.get('codex_intake_readiness_status'))}`",
        ),
        (
            "command_label",
            "- Command: "
            f"`{markdown_display_value(operator_home.get('command_label'))}`",
        ),
        (
            "command_boundary",
            "- Command boundary: "
            f"`{markdown_display_value(operator_home.get('command_boundary'))}`",
        ),
        (
            "markdown_command",
            "- Command text: "
            f"`{markdown_display_value(operator_home.get('markdown_command'))}`",
        ),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in summary_text:
            add_error(report, f"summary.md operator_home {field_name} mismatch")


def validate_iteration_summary_operator_next_command(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate summary.md operator next-command selector mirrors operator_home."""
    operator_home = manifest.get("operator_home")
    if not isinstance(operator_home, dict):
        return
    summary_text = read_optional_text(run_dir / "summary.md")
    section = markdown_section(summary_text, "## Operator Next Command")
    if not section:
        add_error(report, "summary.md operator_next_command section missing")
        return
    expected_lines: tuple[tuple[str, str], ...] = (
        ("selection_source", "- Selection source: `operator_home.next_command`"),
        (
            "status",
            "- Status: "
            f"`{markdown_display_value(operator_home.get('next_command_status'))}`",
        ),
        (
            "blocked",
            "- Blocked: "
            f"`{markdown_display_value(operator_home.get('next_command_blocked'))}`",
        ),
        (
            "blocker_count",
            "- Blocker count: "
            f"`{markdown_display_value(operator_home.get('next_command_blocker_count'))}`",
        ),
        (
            "label",
            "- Label: "
            f"`{markdown_display_value(operator_home.get('next_command_label'))}`",
        ),
        (
            "command",
            "- Command: "
            f"`{markdown_display_value(operator_home.get('next_command'))}`",
        ),
        (
            "boundary",
            "- Boundary: "
            f"`{markdown_display_value(operator_home.get('next_command_boundary'))}`",
        ),
        (
            "writes_artifact",
            "- Writes artifact: "
            f"`{markdown_display_value(operator_home.get('next_command_writes_artifact'))}`",
        ),
        (
            "hint_only",
            "- Hint-only: "
            f"`{markdown_display_value(operator_home.get('next_command_is_hint_only'))}`",
        ),
        (
            "requires_explicit_invocation",
            "- Requires explicit invocation: "
            f"`{markdown_display_value(operator_home.get('next_command_requires_explicit_operator_invocation'))}`",
        ),
        (
            "requires_approval",
            "- Requires approval: "
            f"`{markdown_display_value(operator_home.get('next_command_requires_operator_approval'))}`",
        ),
        (
            "uses_guarded_executor",
            "- Uses guarded executor: "
            f"`{markdown_display_value(operator_home.get('next_command_uses_guarded_executor'))}`",
        ),
    )
    for field_name, expected_line in expected_lines:
        if expected_line not in section:
            add_error(
                report,
                f"summary.md operator_next_command {field_name} mismatch",
            )


def markdown_display_value(value: object) -> str:
    """Format optional manifest values like the markdown summary writer."""
    if value is None:
        return "none"
    return str(value)


def markdown_escape_text(value: str) -> str:
    """Flatten text like the markdown summary writer."""
    return " ".join(value.split())


def markdown_section(markdown: str, heading: str) -> str:
    """Return one markdown section body by heading."""
    start = markdown.find(heading)
    if start < 0:
        return ""
    body_start = start + len(heading)
    next_heading = markdown.find("\n## ", body_start)
    if next_heading < 0:
        return markdown[body_start:]
    return markdown[body_start:next_heading]


def expected_agent_intake_summary(rounds: object) -> dict[str, object]:
    """Return expected manifest-level agent-intake counters from round rows."""
    rows = rounds if isinstance(rounds, list) else []
    code_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    round_count = 0
    blocked_round_count = 0
    retryable_round_count = 0
    primary_stage = "none"
    primary_code = "none"
    for row in rows:
        if not isinstance(row, dict):
            continue
        diagnosis = row.get("agent_intake_diagnosis", {})
        diagnosis = diagnosis if isinstance(diagnosis, dict) else {}
        round_count += 1
        status = str(diagnosis.get("status", "unknown"))
        code = str(diagnosis.get("primary_code", "none"))
        status_counts[status] = status_counts.get(status, 0) + 1
        if code and code != "none":
            code_counts[code] = code_counts.get(code, 0) + 1
        if status == "blocked":
            blocked_round_count += 1
            if primary_code == "none":
                primary_code = code
                primary_stage = str(diagnosis.get("primary_stage", "none"))
        if bool(diagnosis.get("retryable", False)):
            retryable_round_count += 1
    return {
        "round_count": round_count,
        "blocked_round_count": blocked_round_count,
        "passed_round_count": int(status_counts.get("passed", 0)),
        "retryable_round_count": retryable_round_count,
        "primary_stage": primary_stage,
        "primary_code": primary_code,
        "top_blocking_code": top_count_key(code_counts),
        "code_counts": code_counts,
        "status_counts": status_counts,
    }


def top_count_key(counts: dict[str, int]) -> str:
    """Return the highest-count key using stable lexical tie-breaking."""
    if not counts:
        return "none"
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


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
        quality = validate_candidate_quality_row(
            row=row,
            artifact_name="candidate_leaderboard",
            row_label=str(index),
            report=report,
        )
        if quality is None:
            continue
        signals = quality.get("signals", {})
        if not isinstance(signals, dict):
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


def validate_candidate_quality_row(
    *,
    row: dict[str, object],
    artifact_name: str,
    row_label: str,
    report: dict[str, object],
) -> dict[str, object] | None:
    """Validate deterministic candidate score breakdown metadata."""
    quality = row.get("quality_breakdown", {})
    label = f"{artifact_name} row {row_label}"
    if not isinstance(quality, dict):
        add_error(report, f"{label} quality invalid")
        return None
    if quality.get("schema_version") != "candidate_quality_v1":
        add_error(report, f"{label} quality schema invalid")
    if quality.get("total_score") != row.get("candidate_score"):
        add_error(report, f"{label} quality score mismatch")
    components = quality.get("components", [])
    if not isinstance(components, list):
        add_error(report, f"{label} quality components invalid")
    signals = quality.get("signals", {})
    if not isinstance(signals, dict):
        add_error(report, f"{label} quality signals invalid")
    policy = quality.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, f"{label} quality policy invalid")
    return quality


def validate_candidate_quality_trace(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate run-level candidate quality trace artifact."""
    path = run_dir / "candidate_quality_trace.json"
    md_path = run_dir / "candidate_quality_trace.md"
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/candidate_quality_trace.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, f"candidate_quality_trace.json run_id does not match report: {path}")
    source = payload.get("source", {})
    if not isinstance(source, dict):
        add_error(report, "candidate_quality_trace.json source invalid")
    else:
        validate_recorded_file_hash(
            record=source,
            repo_root=repo_root,
            report=report,
            label="candidate_quality_trace source",
        )
        if not str(source.get("path", "")).endswith("candidate_leaderboard.json"):
            add_error(report, "candidate_quality_trace source is not candidate_leaderboard.json")
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list):
        add_error(report, "candidate_quality_trace.json candidates invalid")
        candidates = []
    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        add_error(report, "candidate_quality_trace.json summary invalid")
    elif int(summary.get("candidate_count", -1) or -1) != len(candidates):
        add_error(report, "candidate_quality_trace.json candidate_count mismatch")
    from orchestrator.candidate_quality_trace import (
        validate_candidate_quality_trace_consistency,
    )

    for error in validate_candidate_quality_trace_consistency(
        payload=payload,
        run_dir=run_dir,
        repo_root=repo_root,
    ):
        add_error(report, error)
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "candidate_quality_trace.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_route_candidates",
        "does_not_apply_patches",
        "does_not_change_acceptance",
        "proposal_attempts_remain_round_source_of_truth",
    ):
        if policy.get(key) is not True:
            add_error(report, f"candidate_quality_trace.json policy false: {key}")


def validate_modifier_profile_recommendation(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate run-level modifier profile recommendation artifact."""
    path = run_dir / "modifier_profile_recommendation.json"
    md_path = run_dir / "modifier_profile_recommendation.md"
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/modifier_profile_recommendation.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            "modifier_profile_recommendation.json run_id does not match report",
        )
    sources = payload.get("sources", {})
    if not isinstance(sources, dict):
        add_error(report, "modifier_profile_recommendation.json sources invalid")
        sources = {}
    config_source_path = repo_root / "config/default.json"
    for source_key, expected_name in (
        ("candidate_quality_trace", "candidate_quality_trace.json"),
        ("research_brief", "research_brief.json"),
        ("config", ".json"),
    ):
        source = sources.get(source_key, {})
        if not isinstance(source, dict):
            add_error(
                report,
                f"modifier_profile_recommendation source invalid: {source_key}",
            )
            continue
        validate_recorded_file_hash(
            record=source,
            repo_root=repo_root,
            report=report,
            label=f"modifier_profile_recommendation {source_key}",
        )
        source_path_text = str(source.get("path", ""))
        if source_key == "config" and source_path_text:
            config_source_path = resolve_path(Path(source_path_text), repo_root)
        if source.get("exists") is True and not source_path_text.endswith(expected_name):
            add_error(
                report,
                f"modifier_profile_recommendation source path invalid: {source_key}",
            )
    summary = payload.get("summary", {})
    recommendations = payload.get("recommendations", [])
    profiles = payload.get("available_profiles", [])
    if not isinstance(summary, dict):
        add_error(report, "modifier_profile_recommendation.json summary invalid")
        summary = {}
    if not isinstance(recommendations, list):
        add_error(
            report,
            "modifier_profile_recommendation.json recommendations invalid",
        )
        recommendations = []
    if not isinstance(profiles, list):
        add_error(
            report,
            "modifier_profile_recommendation.json available profiles invalid",
        )
        profiles = []
    if int(summary.get("recommendation_count", -1)) != len(recommendations):
        add_error(
            report,
            "modifier_profile_recommendation.json recommendation count mismatch",
        )
    if int(summary.get("available_profile_count", -1)) != len(profiles):
        add_error(
            report,
            "modifier_profile_recommendation.json profile count mismatch",
        )
    from orchestrator.modifier_profile_recommendation import (
        validate_modifier_profile_recommendation_consistency,
    )

    for error in validate_modifier_profile_recommendation_consistency(
        payload=payload,
        run_dir=run_dir,
        repo_root=repo_root,
        config_path=config_source_path,
    ):
        add_error(report, error)
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "modifier_profile_recommendation.json policy invalid")
        return
    for key in (
        "advisory_only",
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_write_config",
        "does_not_route_agents",
        "does_not_apply_patches",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            add_error(
                report,
                f"modifier_profile_recommendation.json policy false: {key}",
            )


def validate_memory_hygiene(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate run-level memory hygiene artifact."""
    path = run_dir / "memory_hygiene.json"
    md_path = run_dir / "memory_hygiene.md"
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/memory_hygiene.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    totals = payload.get("totals", {})
    if not isinstance(totals, dict):
        add_error(report, "memory_hygiene.json totals invalid")
    from orchestrator.memory_hygiene import validate_memory_hygiene_consistency

    for error in validate_memory_hygiene_consistency(payload):
        add_error(report, error)
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "memory_hygiene.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_outcome_memory_only",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_change_acceptance",
        "does_not_delete_memory",
    ):
        if policy.get(key) is not True:
            add_error(report, f"memory_hygiene.json policy false: {key}")


def validate_memory_scope_recommendation(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate run-level memory scope recommendation artifact."""
    path = run_dir / "memory_scope_recommendation.json"
    md_path = run_dir / "memory_scope_recommendation.md"
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/memory_scope_recommendation.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"memory_scope_recommendation.json run_id does not match report: {path}",
        )
    source = payload.get("source", {})
    if not isinstance(source, dict):
        add_error(report, "memory_scope_recommendation.json source invalid")
    else:
        validate_recorded_file_hash(
            record=source,
            repo_root=repo_root,
            report=report,
            label="memory_scope_recommendation source",
        )
        if not str(source.get("path", "")).endswith("memory_hygiene.json"):
            add_error(
                report,
                "memory_scope_recommendation source is not memory_hygiene.json",
            )
    recommendation = payload.get("recommendation", {})
    if not isinstance(recommendation, dict):
        add_error(report, "memory_scope_recommendation.json recommendation invalid")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "memory_scope_recommendation.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_write_config",
        "does_not_delete_memory",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_route_candidates",
        "does_not_apply_patches",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            add_error(report, f"memory_scope_recommendation.json policy false: {key}")


def validate_config_change_candidate(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate run-level config change candidate artifact."""
    path = run_dir / "config_change_candidate.json"
    md_path = run_dir / "config_change_candidate.md"
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/config_change_candidate.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"config_change_candidate.json run_id does not match report: {path}",
        )
    sources = payload.get("sources", [])
    if not isinstance(sources, list):
        add_error(report, "config_change_candidate.json sources invalid")
        sources = []
    for index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            add_error(report, f"config_change_candidate.json source {index} invalid")
            continue
        file_payload = source.get("file", {})
        if not isinstance(file_payload, dict):
            add_error(report, f"config_change_candidate.json source {index} file invalid")
            continue
        validate_recorded_file_hash(
            record=file_payload,
            repo_root=repo_root,
            report=report,
            label=f"config_change_candidate source {index}",
        )
        source_name = str(source.get("artifact_name", ""))
        source_path = str(file_payload.get("path", ""))
        expected_suffixes = {
            "memory_scope_recommendation": "memory_scope_recommendation.json",
            "modifier_profile_recommendation": "modifier_profile_recommendation.json",
            "config": ".json",
        }
        expected_suffix = expected_suffixes.get(source_name)
        if expected_suffix and not source_path.endswith(expected_suffix):
            add_error(
                report,
                f"config_change_candidate source path invalid: {source_name}",
            )
    changes = payload.get("changes", [])
    if not isinstance(changes, list):
        add_error(report, "config_change_candidate.json changes invalid")
        changes = []
    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        add_error(report, "config_change_candidate.json summary invalid")
    else:
        if int(summary.get("candidate_count", -1)) != len(changes):
            add_error(report, "config_change_candidate.json candidate_count mismatch")
    for index, change in enumerate(changes, start=1):
        if not isinstance(change, dict):
            add_error(report, f"config_change_candidate.json change {index} invalid")
            continue
        if change.get("applied") is not False:
            add_error(report, f"config_change_candidate.json change {index} applied")
        if change.get("requires_operator_review") is not True:
            add_error(
                report,
                f"config_change_candidate.json change {index} missing operator review",
            )
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "config_change_candidate.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_write_config",
        "does_not_delete_memory",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_route_candidates",
        "does_not_apply_patches",
        "does_not_change_acceptance",
        "operator_must_apply_changes_manually",
    ):
        if policy.get(key) is not True:
            add_error(report, f"config_change_candidate.json policy false: {key}")


def validate_operator_config_review(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate run-level operator config review artifact."""
    path = run_dir / "operator_config_review.json"
    md_path = run_dir / "operator_config_review.md"
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/operator_config_review.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"operator_config_review.json run_id does not match report: {path}",
        )
    source = payload.get("source", {})
    if not isinstance(source, dict):
        add_error(report, "operator_config_review.json source invalid")
    else:
        file_payload = source.get("file", {})
        if not isinstance(file_payload, dict):
            add_error(report, "operator_config_review.json source file invalid")
        else:
            validate_recorded_file_hash(
                record=file_payload,
                repo_root=repo_root,
                report=report,
                label="operator_config_review source",
            )
            if source.get("artifact_name") == "config_change_candidate" and not str(
                file_payload.get("path", "")
            ).endswith("config_change_candidate.json"):
                add_error(
                    report,
                    "operator_config_review source is not config_change_candidate.json",
                )
    reviewed_changes = payload.get("reviewed_changes", [])
    if not isinstance(reviewed_changes, list):
        add_error(report, "operator_config_review.json reviewed_changes invalid")
        reviewed_changes = []
    summary = payload.get("candidate_summary", {})
    if not isinstance(summary, dict):
        add_error(report, "operator_config_review.json candidate_summary invalid")
    else:
        if int(summary.get("candidate_count", -1)) != len(reviewed_changes):
            add_error(report, "operator_config_review.json candidate_count mismatch")
    for index, change in enumerate(reviewed_changes, start=1):
        if not isinstance(change, dict):
            add_error(report, f"operator_config_review.json change {index} invalid")
            continue
        if change.get("applied") is not False:
            add_error(report, f"operator_config_review.json change {index} applied")
        if change.get("requires_manual_config_edit") is not True:
            add_error(
                report,
                f"operator_config_review.json change {index} missing manual edit flag",
            )
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "operator_config_review.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_write_config",
        "does_not_delete_memory",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_route_candidates",
        "does_not_apply_patches",
        "does_not_change_acceptance",
        "review_does_not_apply_config",
        "config_changes_still_require_manual_edit",
    ):
        if policy.get(key) is not True:
            add_error(report, f"operator_config_review.json policy false: {key}")


def validate_config_application_dry_run(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate run-level config application dry-run artifact."""
    path = run_dir / "config_application_dry_run.json"
    md_path = run_dir / "config_application_dry_run.md"
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/config_application_dry_run.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"config_application_dry_run.json run_id does not match report: {path}",
        )
    review_source = payload.get("source_operator_review", {})
    if not isinstance(review_source, dict):
        add_error(report, "config_application_dry_run.json review source invalid")
    else:
        review_file = review_source.get("file", {})
        if not isinstance(review_file, dict):
            add_error(report, "config_application_dry_run.json review file invalid")
        else:
            validate_recorded_file_hash(
                record=review_file,
                repo_root=repo_root,
                report=report,
                label="config_application_dry_run review source",
            )
            if review_source.get("artifact_name") == "operator_config_review" and not str(
                review_file.get("path", "")
            ).endswith("operator_config_review.json"):
                add_error(
                    report,
                    "config_application_dry_run source is not operator_config_review.json",
                )
    config_source = payload.get("source_config", {})
    if not isinstance(config_source, dict):
        add_error(report, "config_application_dry_run.json config source invalid")
    else:
        config_file = config_source.get("file", {})
        if not isinstance(config_file, dict):
            add_error(report, "config_application_dry_run.json config file invalid")
        else:
            validate_recorded_file_hash(
                record=config_file,
                repo_root=repo_root,
                report=report,
                label="config_application_dry_run config source",
            )
            if config_source.get("artifact_name") == "config" and not str(
                config_file.get("path", "")
            ).endswith(".json"):
                add_error(
                    report,
                    "config_application_dry_run config source is not JSON",
                )
    planned_changes = payload.get("planned_changes", [])
    if not isinstance(planned_changes, list):
        add_error(report, "config_application_dry_run.json planned_changes invalid")
        planned_changes = []
    gate = payload.get("application_gate", {})
    if not isinstance(gate, dict):
        add_error(report, "config_application_dry_run.json gate invalid")
    else:
        approved_count = sum(
            1
            for change in planned_changes
            if isinstance(change, dict) and change.get("review_decision") == "approved"
        )
        ready_count = sum(
            1
            for change in planned_changes
            if isinstance(change, dict) and change.get("ready_for_manual_edit") is True
        )
        if int(gate.get("approved_change_count", -1)) != approved_count:
            add_error(
                report,
                "config_application_dry_run.json approved_change_count mismatch",
            )
        if int(gate.get("ready_change_count", -1)) != ready_count:
            add_error(
                report,
                "config_application_dry_run.json ready_change_count mismatch",
            )
        for key in (
            "requires_operator_review_artifact",
            "requires_approved_operator_review",
            "requires_config_value_match",
            "config_changes_must_be_manual",
        ):
            if gate.get(key) is not True:
                add_error(
                    report,
                    f"config_application_dry_run.json gate false: {key}",
                )
    for index, change in enumerate(planned_changes, start=1):
        if not isinstance(change, dict):
            add_error(report, f"config_application_dry_run.json change {index} invalid")
            continue
        if change.get("applied") is not False:
            add_error(report, f"config_application_dry_run.json change {index} applied")
        if change.get("requires_manual_config_edit") is not True:
            add_error(
                report,
                f"config_application_dry_run.json change {index} missing manual edit flag",
            )
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "config_application_dry_run.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_write_config",
        "does_not_delete_memory",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_route_candidates",
        "does_not_apply_patches",
        "does_not_change_acceptance",
        "dry_run_only",
        "config_changes_still_require_manual_edit",
    ):
        if policy.get(key) is not True:
            add_error(report, f"config_application_dry_run.json policy false: {key}")


def validate_round_candidate_quality_bindings(
    *,
    round_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate candidate metadata is identical across round artifacts."""
    reference_rows = list_of_dicts(load_json_list(round_dir / "proposal_attempts.json"))
    reference = candidate_quality_rows_by_attempt_id(
        rows=reference_rows,
        artifact_name="proposal_attempts.json",
        report=report,
    )
    if not reference:
        return

    source_rows_by_artifact: list[tuple[str, list[dict[str, object]]]] = [
        (
            "agent_executor_report.json",
            list_of_dicts(
                object_value(
                    load_json_object(round_dir / "agent_executor_report.json", report)
                ).get("attempts", [])
            ),
        ),
        (
            "agent_attempts_manifest.json",
            list_of_dicts(
                object_value(
                    load_json_object(round_dir / "agent_attempts_manifest.json", report)
                ).get("attempts", [])
            ),
        ),
        (
            "agent_selection_report.json",
            list_of_dicts(
                object_value(
                    load_json_object(round_dir / "agent_selection_report.json", report)
                ).get("attempts", [])
            ),
        ),
        (
            "agent_routing_policy.json",
            list_of_dicts(
                object_value(
                    load_json_object(round_dir / "agent_routing_policy.json", report)
                ).get("candidates", [])
            ),
        ),
        (
            "agent_output.json",
            list_of_dicts(
                object_value(
                    load_json_object(round_dir / "agent_output.json", report)
                ).get("attempts", [])
            ),
        ),
        (
            "candidate_leaderboard.json",
            leaderboard_rows_for_round(round_dir=round_dir),
        ),
        (
            "attempt_output.json",
            attempt_output_quality_rows(round_dir=round_dir, report=report),
        ),
    ]
    for artifact_name, rows in source_rows_by_artifact:
        validate_candidate_quality_source_binding(
            artifact_name=artifact_name,
            rows=rows,
            reference=reference,
            report=report,
        )
    validate_round_candidate_direction_bindings(
        round_dir=round_dir,
        reference_rows=reference_rows,
        report=report,
    )


def validate_round_candidate_direction_bindings(
    *,
    round_dir: Path,
    reference_rows: list[dict[str, object]],
    report: dict[str, object],
) -> None:
    """Validate candidate direction audit metadata against proposal attempts."""
    full_keys = (
        "direction_tag",
        "supported_directions",
        "direction_capability",
        "direction_intent_alignment",
    )
    reference = candidate_direction_rows_by_attempt_id(
        rows=reference_rows,
        artifact_name="proposal_attempts.json",
        keys=full_keys,
        report=report,
    )
    if not reference:
        return
    source_rows_by_artifact: list[
        tuple[str, list[dict[str, object]], tuple[str, ...]]
    ] = [
        (
            "agent_executor_report.json",
            list_of_dicts(
                object_value(
                    load_json_object(round_dir / "agent_executor_report.json", report)
                ).get("attempts", [])
            ),
            full_keys,
        ),
        (
            "agent_attempts_manifest.json",
            list_of_dicts(
                object_value(
                    load_json_object(round_dir / "agent_attempts_manifest.json", report)
                ).get("attempts", [])
            ),
            full_keys,
        ),
        (
            "agent_selection_report.json",
            list_of_dicts(
                object_value(
                    load_json_object(round_dir / "agent_selection_report.json", report)
                ).get("attempts", [])
            ),
            full_keys,
        ),
        (
            "agent_routing_policy.json",
            list_of_dicts(
                object_value(
                    load_json_object(round_dir / "agent_routing_policy.json", report)
                ).get("candidates", [])
            ),
            full_keys,
        ),
        (
            "attempt_output.json",
            attempt_output_direction_rows(round_dir=round_dir, report=report),
            full_keys,
        ),
        (
            "agent_output.json",
            list_of_dicts(
                object_value(
                    load_json_object(round_dir / "agent_output.json", report)
                ).get("attempts", [])
            ),
            ("direction_tag", "direction_intent_alignment"),
        ),
        (
            "candidate_leaderboard.json",
            leaderboard_rows_for_round(round_dir=round_dir),
            ("direction_tag",),
        ),
    ]
    for artifact_name, rows, keys in source_rows_by_artifact:
        validate_candidate_direction_source_binding(
            artifact_name=artifact_name,
            rows=rows,
            reference=reference,
            keys=keys,
            report=report,
        )


def candidate_quality_rows_by_attempt_id(
    *,
    rows: list[dict[str, object]],
    artifact_name: str,
    report: dict[str, object],
) -> dict[str, dict[str, object]]:
    """Return candidate quality signatures keyed by attempt id."""
    result: dict[str, dict[str, object]] = {}
    for row in rows:
        attempt_id = str(row.get("attempt_id", ""))
        if not attempt_id:
            add_error(report, f"{artifact_name} candidate quality row missing attempt_id")
            continue
        if attempt_id in result:
            add_error(
                report,
                f"{artifact_name} duplicate candidate quality row: {attempt_id}",
            )
            continue
        result[attempt_id] = candidate_quality_signature(row)
    return result


def validate_candidate_quality_source_binding(
    *,
    artifact_name: str,
    rows: list[dict[str, object]],
    reference: dict[str, dict[str, object]],
    report: dict[str, object],
) -> None:
    """Validate one artifact's candidate quality rows match proposal attempts."""
    observed = candidate_quality_rows_by_attempt_id(
        rows=rows,
        artifact_name=artifact_name,
        report=report,
    )
    if not observed:
        return
    for attempt_id in sorted(reference):
        if attempt_id not in observed:
            add_error(report, f"{artifact_name} missing quality row: {attempt_id}")
            continue
        if observed[attempt_id] != reference[attempt_id]:
            add_error(
                report,
                f"{artifact_name} quality binding mismatch: {attempt_id}",
            )
    for attempt_id in sorted(set(observed) - set(reference)):
        add_error(report, f"{artifact_name} unexpected quality row: {attempt_id}")


def candidate_quality_signature(row: dict[str, object]) -> dict[str, object]:
    """Return the quality fields that must remain stable across artifacts."""
    return {
        "candidate_score": row.get("candidate_score", 0),
        "score_reasons": list_value(row.get("score_reasons", [])),
        "quality_breakdown": object_value(row.get("quality_breakdown", {})),
    }


def candidate_direction_rows_by_attempt_id(
    *,
    rows: list[dict[str, object]],
    artifact_name: str,
    keys: tuple[str, ...],
    report: dict[str, object],
) -> dict[str, dict[str, object]]:
    """Return candidate direction signatures keyed by attempt id."""
    result: dict[str, dict[str, object]] = {}
    for row in rows:
        attempt_id = str(row.get("attempt_id", ""))
        if not attempt_id:
            add_error(report, f"{artifact_name} candidate direction row missing attempt_id")
            continue
        if attempt_id in result:
            add_error(
                report,
                f"{artifact_name} duplicate candidate direction row: {attempt_id}",
            )
            continue
        result[attempt_id] = candidate_direction_signature(row=row, keys=keys)
    return result


def validate_candidate_direction_source_binding(
    *,
    artifact_name: str,
    rows: list[dict[str, object]],
    reference: dict[str, dict[str, object]],
    keys: tuple[str, ...],
    report: dict[str, object],
) -> None:
    """Validate one artifact's candidate direction rows match proposal attempts."""
    observed = candidate_direction_rows_by_attempt_id(
        rows=rows,
        artifact_name=artifact_name,
        keys=keys,
        report=report,
    )
    if not observed:
        return
    for attempt_id in sorted(reference):
        if attempt_id not in observed:
            add_error(report, f"{artifact_name} missing direction row: {attempt_id}")
            continue
        expected = {
            key: value
            for key, value in reference[attempt_id].items()
            if key in keys
        }
        if observed[attempt_id] != expected:
            add_error(
                report,
                f"{artifact_name} direction binding mismatch: {attempt_id}",
            )
    for attempt_id in sorted(set(observed) - set(reference)):
        add_error(report, f"{artifact_name} unexpected direction row: {attempt_id}")


def candidate_direction_signature(
    *,
    row: dict[str, object],
    keys: tuple[str, ...],
) -> dict[str, object]:
    """Return direction fields that must remain stable across candidate artifacts."""
    signature: dict[str, object] = {}
    if "direction_tag" in keys:
        signature["direction_tag"] = str(row.get("direction_tag", ""))
    if "supported_directions" in keys:
        signature["supported_directions"] = normalized_direction_list(
            row.get("supported_directions", [])
        )
    if "direction_capability" in keys:
        signature["direction_capability"] = object_value(
            row.get("direction_capability", {})
        )
    if "direction_intent_alignment" in keys:
        signature["direction_intent_alignment"] = object_value(
            row.get("direction_intent_alignment", {})
        )
    return signature


def leaderboard_rows_for_round(*, round_dir: Path) -> list[dict[str, object]]:
    """Return candidate leaderboard rows for one round."""
    rows = list_of_dicts(load_json_list(round_dir.parent / "candidate_leaderboard.json"))
    return [row for row in rows if str(row.get("round_id", "")) == round_dir.name]


def attempt_output_quality_rows(
    *,
    round_dir: Path,
    report: dict[str, object],
) -> list[dict[str, object]]:
    """Return normalized quality rows from attempt_output.json files."""
    rows: list[dict[str, object]] = []
    for path in sorted((round_dir / "agent_attempts").glob("*/attempt_output.json")):
        payload = load_json_object(path, report)
        if payload is None:
            continue
        selection = object_value(payload.get("selection", {}))
        rows.append(
            {
                "attempt_id": str(payload.get("attempt_id", "")),
                "candidate_score": payload.get("candidate_score", 0),
                "score_reasons": list_value(selection.get("score_reasons", [])),
                "quality_breakdown": object_value(
                    selection.get("quality_breakdown", {})
                ),
            }
        )
    return rows


def attempt_output_direction_rows(
    *,
    round_dir: Path,
    report: dict[str, object],
) -> list[dict[str, object]]:
    """Return normalized direction rows from attempt_output.json files."""
    rows: list[dict[str, object]] = []
    for path in sorted((round_dir / "agent_attempts").glob("*/attempt_output.json")):
        payload = load_json_object(path, report)
        if payload is None:
            continue
        rows.append(
            {
                "attempt_id": str(payload.get("attempt_id", "")),
                "direction_tag": str(payload.get("direction_tag", "")),
                "supported_directions": normalized_direction_list(
                    payload.get("supported_directions", [])
                ),
                "direction_capability": object_value(
                    payload.get("direction_capability", {})
                ),
                "direction_intent_alignment": object_value(
                    payload.get("direction_intent_alignment", {})
                ),
            }
        )
    return rows


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
    validate_agent_output(
        path=round_dir / "agent_output.json",
        repo_root=repo_root,
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_validation.json",
        schema_path=repo_root / "schemas/agent_validation.schema.json",
        report=report,
    )
    validate_agent_validation(
        path=round_dir / "agent_validation.json",
        repo_root=repo_root,
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
    validate_round_candidate_quality_bindings(
        round_dir=round_dir,
        repo_root=repo_root,
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
    validate_agent_execution_intake_binding(
        path=path,
        payload=payload,
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
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


def validate_agent_execution_intake_binding(
    *,
    path: Path,
    payload: dict[str, Any],
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate execution audit binding to shared proposal intake artifacts."""
    binding = payload.get("intake_binding", {})
    if not isinstance(binding, dict):
        add_error(report, f"agent_execution intake_binding invalid: {path}")
        return
    bound = bool(binding.get("bound", False))
    status = str(binding.get("status", ""))
    if status == "bound" and not bound:
        add_error(report, f"agent_execution intake_binding status mismatch: {path}")
    if status != "bound" and bound:
        add_error(report, f"agent_execution intake_binding bound mismatch: {path}")
    if is_round_level_agent_execution(path=path, run_dir=run_dir) and not bound:
        add_error(report, f"agent_execution selected intake binding not bound: {path}")
    if not bound:
        return
    expected = expected_agent_execution_intake_binding(
        payload=payload,
        binding=binding,
        repo_root=repo_root,
        report=report,
    )
    if expected is None:
        add_error(report, f"agent_execution intake_binding source missing: {path}")
        return
    saved_checks = binding.get("checks", {})
    if not isinstance(saved_checks, dict):
        add_error(report, f"agent_execution intake_binding checks invalid: {path}")
        return
    expected_checks = expected["checks"]
    for key, expected_value in expected_checks.items():
        if bool(saved_checks.get(key, False)) != bool(expected_value):
            add_error(
                report,
                f"agent_execution intake_binding check drift: {key}: {path}",
            )
    if binding.get("proposal_patch_sha256") != expected["proposal_patch_sha256"]:
        add_error(report, f"agent_execution intake_binding patch hash drift: {path}")
    if bool(binding.get("agent_validation_ok", False)) != bool(
        expected["agent_validation_ok"]
    ):
        add_error(report, f"agent_execution intake_binding validation ok drift: {path}")
    expected_blockers = [
        f"intake_binding:{name}"
        for name, passed in expected_checks.items()
        if not passed
    ]
    blockers = binding.get("blocking_reasons", [])
    if not isinstance(blockers, list) or [str(item) for item in blockers] != expected_blockers:
        add_error(report, f"agent_execution intake_binding blockers drift: {path}")
    if not all(expected_checks.values()):
        add_error(report, f"agent_execution intake_binding expected checks failed: {path}")


def expected_agent_execution_intake_binding(
    *,
    payload: dict[str, Any],
    binding: dict[str, Any],
    repo_root: Path,
    report: dict[str, object],
) -> dict[str, object] | None:
    """Recompute execution-to-intake binding checks from saved artifacts."""
    validation_path = resolve_path(
        Path(str(binding.get("agent_validation_path", ""))),
        repo_root,
    )
    proposal_path = resolve_path(Path(str(binding.get("proposal_path", ""))), repo_root)
    raw_path = resolve_path(
        Path(str(binding.get("raw_agent_output_path", ""))),
        repo_root,
    )
    if not validation_path.exists() or not proposal_path.exists() or not raw_path.exists():
        return None
    validation = load_json_object(validation_path, report)
    proposal = load_json_object(proposal_path, report)
    if validation is None or proposal is None:
        return None
    raw_output = raw_path.read_text(encoding="utf-8")
    validation_proposal = object_value(validation.get("proposal", {}))
    command = list_value(payload.get("command", []))
    proposal_command = list_value(proposal.get("command", []))
    audit_raw_sha = str(object_value(payload.get("raw_response", {})).get("sha256", ""))
    audit_stdin_sha = str(object_value(payload.get("stdin", {})).get("sha256", ""))
    audit_stdin_chars = int(object_value(payload.get("stdin", {})).get("chars", 0) or 0)
    checks = {
        "agent_validation_present": validation_path.exists(),
        "proposal_present": proposal_path.exists(),
        "raw_agent_output_present": raw_path.exists(),
        "validation_embeds_proposal": bool(validation_proposal),
        "validation_proposal_matches_saved_proposal": validation_proposal == proposal,
        "audit_raw_response_matches_proposal": (
            audit_raw_sha == sha256_text(str(proposal.get("raw_response", "")))
        ),
        "raw_agent_output_matches_proposal": (
            raw_output.rstrip("\n") == str(proposal.get("raw_response", "")).rstrip("\n")
        ),
        "audit_command_matches_proposal": command == proposal_command,
        "audit_command_sha256_matches_proposal": (
            str(payload.get("command_sha256", "")) == stable_json_digest(proposal_command)
        ),
        "audit_stdin_matches_proposal_prompt": (
            audit_stdin_chars == 0
            or audit_stdin_sha == sha256_text(str(proposal.get("prompt", "")))
        ),
        "validation_patch_hash_matches_proposal": (
            str(validation.get("proposal_patch_sha256", ""))
            == str(proposal.get("patch_sha256", ""))
        ),
        "validation_target_matches_proposal": (
            str(validation.get("proposal_target_file", ""))
            == str(proposal.get("target_file", ""))
        ),
        "validation_applicable_matches_proposal": (
            bool(validation.get("proposal_applicable", False))
            == bool(proposal.get("applicable", False))
        ),
        "validation_agent_input_matches_audit": (
            str(validation.get("agent_input_path", ""))
            == str(payload.get("agent_input_path", ""))
            or str(proposal.get("prompt", "")) == str(payload.get("agent_input_path", ""))
        ),
        "validation_agent_output_matches_raw_path": (
            resolve_path(Path(str(validation.get("agent_output_path", ""))), repo_root)
            == raw_path
        ),
    }
    return {
        "checks": checks,
        "agent_validation_ok": bool(validation.get("ok", False)),
        "proposal_patch_sha256": str(proposal.get("patch_sha256", "")),
    }


def is_round_level_agent_execution(*, path: Path, run_dir: Path) -> bool:
    """Return whether an audit is the selected round-level execution artifact."""
    return path.name == "agent_execution.json" and path.parent.parent == run_dir


def list_value(value: object) -> list[object]:
    """Return a JSON list or an empty list."""
    return value if isinstance(value, list) else []


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


def validate_agent_output(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate selected agent output context bindings."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    validate_proposal_intent_summary_contract(
        summary=payload.get("proposal_intent_summary", {}),
        artifact_name="agent_output.json",
        report=report,
    )
    artifacts = payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        add_error(report, f"agent_output.json artifacts is invalid: {path}")
        return
    agent_input_path = resolve_path(
        Path(str(artifacts.get("agent_input", ""))),
        repo_root,
    )
    if not agent_input_path.exists() or not agent_input_path.is_file():
        add_error(
            report,
            f"agent_output agent_input artifact missing: {agent_input_path}",
        )
        return
    agent_input = load_json_object(agent_input_path, report)
    if agent_input is not None and agent_input.get(
        "proposal_intent_summary", {}
    ) != payload.get("proposal_intent_summary", {}):
        add_error(report, "agent_output proposal intent summary drift")
    attempts = payload.get("attempts", [])
    if not isinstance(attempts, list) or not attempts:
        add_error(report, "agent_output.json attempts is empty or invalid")
        return
    for index, row in enumerate(attempts, start=1):
        if not isinstance(row, dict):
            add_error(report, "agent_output.json attempts contains non-object")
            continue
        validate_candidate_quality_row(
            row=row,
            artifact_name="agent_output.json",
            row_label=str(index),
            report=report,
        )


def validate_agent_output_quarantine(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate the pre-apply quarantine report for one selected output."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    validate_proposal_intent_summary_contract(
        summary=payload.get("proposal_intent_summary", {}),
        artifact_name="agent_output_quarantine.json",
        report=report,
    )
    validate_quarantine_intent_summary_bindings(
        payload=payload,
        repo_root=repo_root,
        report=report,
    )
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
    validate_quarantine_consistency_checks(
        payload=payload,
        repo_root=repo_root,
        report=report,
    )
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


def validate_quarantine_consistency_checks(
    *,
    payload: dict[str, Any],
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate quarantine consistency checks and recorded artifact hashes."""
    consistency = payload.get("consistency_checks", {})
    if not isinstance(consistency, dict):
        add_error(report, "agent_output_quarantine consistency invalid")
        return
    blockers = consistency.get("blocking_reasons", [])
    if not isinstance(blockers, list):
        add_error(report, "agent_output_quarantine consistency blockers invalid")
    elif blockers:
        add_error(report, "agent_output_quarantine consistency failed")
    checks = consistency.get("checks", {})
    if not isinstance(checks, dict):
        add_error(report, "agent_output_quarantine consistency checks invalid")
    else:
        if any(not bool(passed) for passed in checks.values()):
            add_error(report, "agent_output_quarantine consistency check false")
        recomputed = recompute_quarantine_consistency_checks(
            payload=payload,
            repo_root=repo_root,
            report=report,
        )
        for key, expected in recomputed.items():
            if key in checks and bool(checks[key]) != expected:
                add_error(
                    report,
                    f"agent_output_quarantine consistency recompute mismatch: {key}",
                )
        if any(not passed for passed in recomputed.values()):
            add_error(report, "agent_output_quarantine consistency recomputed false")
    if consistency.get("expected_status") != payload.get("quarantine_status"):
        add_error(report, "agent_output_quarantine expected status mismatch")

    artifacts = payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return
    for artifact_key, record in artifacts.items():
        if not isinstance(record, dict):
            add_error(
                report,
                f"agent_output_quarantine artifact record invalid: {artifact_key}",
            )
            continue
        if record.get("exists") is True:
            validate_recorded_file_hash(
                record=record,
                repo_root=repo_root,
                report=report,
                label=f"agent_output_quarantine {artifact_key}",
            )


def recompute_quarantine_consistency_checks(
    *,
    payload: dict[str, Any],
    repo_root: Path,
    report: dict[str, object],
) -> dict[str, bool]:
    """Recompute quarantine consistency checks from source artifacts."""
    artifacts = object_value(payload.get("artifacts", {}))
    proposal = object_value(payload.get("proposal", {}))
    selected_attempt = object_value(payload.get("selected_attempt", {}))
    agent_validation = object_value(payload.get("agent_validation", {}))
    proposal_intent_summary = payload.get("proposal_intent_summary", {})
    agent_input = load_quarantine_source_payload(
        artifacts=artifacts,
        key="agent_input",
        repo_root=repo_root,
        report=report,
    )
    agent_output = load_quarantine_source_payload(
        artifacts=artifacts,
        key="agent_output",
        repo_root=repo_root,
        report=report,
    )
    validation = load_quarantine_source_payload(
        artifacts=artifacts,
        key="agent_validation",
        repo_root=repo_root,
        report=report,
    )
    proposal_file = load_quarantine_source_payload(
        artifacts=artifacts,
        key="proposal",
        repo_root=repo_root,
        report=report,
    )
    patch_record = object_value(artifacts.get("patch", {}))
    validation_record = object_value(artifacts.get("agent_validation", {}))
    patch_sha256 = str(proposal.get("patch_sha256", ""))
    release_to_apply = bool(payload.get("release_to_apply", False))
    proposal_applicable = bool(proposal.get("applicable", False))
    blocking_reasons = string_list(payload.get("blocking_reasons", []))
    expected_status = expected_quarantine_status(
        proposal_applicable=proposal_applicable,
        release_to_apply=release_to_apply,
    )
    return {
        "release_status_matches_blockers": (
            release_to_apply == (not blocking_reasons and proposal_applicable)
        ),
        "quarantine_status_matches_release": (
            str(payload.get("quarantine_status", "")) == expected_status
        ),
        "proposal_intent_matches_agent_input": (
            agent_input.get("proposal_intent_summary", {}) == proposal_intent_summary
        ),
        "proposal_intent_matches_agent_output": (
            agent_output.get("proposal_intent_summary", {}) == proposal_intent_summary
        ),
        "proposal_intent_matches_agent_validation": (
            validation.get("proposal_intent_summary", {}) == proposal_intent_summary
        ),
        "selected_attempt_matches_agent_output": any(
            str(row.get("attempt_id", "")) == str(selected_attempt.get("attempt_id", ""))
            and str(row.get("patch_sha256", "")) == patch_sha256
            for row in list_of_dicts(agent_output.get("attempts", []))
        ),
        "round_index_matches_agent_input": (
            int(agent_input.get("round_index", -1))
            == int(payload.get("round_index", -2))
        ),
        "proposal_hash_matches_agent_output": (
            nested_string(agent_output, ("selected_proposal", "patch_sha256"))
            == patch_sha256
        ),
        "proposal_hash_matches_agent_validation": (
            str(validation.get("proposal_patch_sha256", "")) == patch_sha256
        ),
        "proposal_hash_matches_proposal_file": (
            str(proposal_file.get("patch_sha256", "")) == patch_sha256
        ),
        "patch_artifact_hash_matches_proposal": (
            (
                not patch_sha256
                and (
                    not bool(patch_record.get("exists", False))
                    or int(patch_record.get("bytes", 0) or 0) == 0
                )
            )
            or str(patch_record.get("sha256", "")) == patch_sha256
        ),
        "agent_validation_path_matches_artifact": (
            str(agent_validation.get("path", ""))
            == str(validation_record.get("path", ""))
        ),
        "agent_validation_ok_matches_source": (
            bool(validation.get("ok", False)) == bool(agent_validation.get("ok", False))
        ),
        "contract_valid_matches_validation": (
            object_value(validation.get("checks", {})).get("contract_valid")
            == object_value(agent_validation.get("checks", {})).get("contract_valid")
        ),
        "git_apply_check_matches_validation": (
            object_value(validation.get("checks", {})).get("git_apply_check")
            == object_value(agent_validation.get("checks", {})).get("git_apply_check")
        ),
    }


def load_quarantine_source_payload(
    *,
    artifacts: dict[str, object],
    key: str,
    repo_root: Path,
    report: dict[str, object],
) -> dict[str, Any]:
    """Load a quarantine source artifact from its recorded file path."""
    record = object_value(artifacts.get(key, {}))
    source_path = resolve_path(Path(str(record.get("path", ""))), repo_root)
    if not source_path.exists() or not source_path.is_file():
        return {}
    return load_json_object(source_path, report) or {}


def expected_quarantine_status(
    *,
    proposal_applicable: bool,
    release_to_apply: bool,
) -> str:
    """Return expected quarantine status from persisted release fields."""
    if release_to_apply:
        return "released"
    if proposal_applicable:
        return "blocked"
    return "not_applicable"


def nested_string(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    """Return a nested string from a JSON object."""
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key, "")
    return current if isinstance(current, str) else ""


def validate_agent_validation(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate agent validation report context bindings."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    validate_proposal_intent_summary_contract(
        summary=payload.get("proposal_intent_summary", {}),
        artifact_name="agent_validation.json",
        report=report,
    )
    agent_input_path = resolve_path(
        Path(str(payload.get("agent_input_path", ""))),
        repo_root,
    )
    if not agent_input_path.exists() or not agent_input_path.is_file():
        add_error(
            report,
            f"agent_validation agent_input artifact missing: {agent_input_path}",
        )
        return
    agent_input = load_json_object(agent_input_path, report)
    if agent_input is not None and agent_input.get(
        "proposal_intent_summary", {}
    ) != payload.get("proposal_intent_summary", {}):
        add_error(report, "agent_validation proposal intent summary drift")
    if agent_input is not None:
        validate_agent_validation_consistency_checks(
            payload=payload,
            agent_input=agent_input,
            repo_root=repo_root,
            report=report,
        )


def validate_agent_validation_consistency_checks(
    *,
    payload: dict[str, Any],
    agent_input: dict[str, Any],
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate agent_validation consistency checks and recompute them."""
    consistency = payload.get("consistency_checks", {})
    if not isinstance(consistency, dict):
        add_error(report, "agent_validation consistency invalid")
        return
    blockers = consistency.get("blocking_reasons", [])
    if not isinstance(blockers, list):
        add_error(report, "agent_validation consistency blockers invalid")
    elif blockers:
        add_error(report, "agent_validation consistency failed")
    checks = consistency.get("checks", {})
    if not isinstance(checks, dict):
        add_error(report, "agent_validation consistency checks invalid")
        return
    if any(not bool(passed) for passed in checks.values()):
        add_error(report, "agent_validation consistency check false")
    recomputed = recompute_agent_validation_consistency_checks(
        payload=payload,
        agent_input=agent_input,
        repo_root=repo_root,
    )
    for key, expected in recomputed.items():
        if key in checks and bool(checks[key]) != expected:
            add_error(
                report,
                f"agent_validation consistency recompute mismatch: {key}",
            )
    if any(not passed for passed in recomputed.values()):
        add_error(report, "agent_validation consistency recomputed false")


def recompute_agent_validation_consistency_checks(
    *,
    payload: dict[str, Any],
    agent_input: dict[str, Any],
    repo_root: Path,
) -> dict[str, bool]:
    """Recompute agent_validation consistency checks from saved sources."""
    proposal = object_value(payload.get("proposal", {}))
    checks = object_value(payload.get("checks", {}))
    semantic_checks = object_value(payload.get("semantic_checks", {}))
    diagnosis = object_value(payload.get("intake_diagnosis", {}))
    errors = string_list(payload.get("errors", []))
    semantic_errors = string_list(semantic_checks.get("errors", []))
    reason_codes = reason_code_rows(payload.get("reason_codes", []))
    raw_output = read_optional_text(
        resolve_path(Path(str(payload.get("agent_output_path", ""))), repo_root)
    )
    patch_diff = str(proposal.get("patch_diff", ""))
    patch_sha256 = str(payload.get("proposal_patch_sha256", ""))
    return {
        "ok_matches_errors": bool(payload.get("ok", False)) == (not errors),
        "failure_code_matches_ok": (
            (
                bool(payload.get("ok", False))
                and str(payload.get("failure_code", "")) == "none"
            )
            or (
                not bool(payload.get("ok", False))
                and str(payload.get("failure_code", "")) != "none"
            )
        ),
        "proposal_intent_matches_agent_input": (
            payload.get("proposal_intent_summary", {})
            == agent_input.get("proposal_intent_summary", {})
        ),
        "expected_round_matches_agent_input": (
            int(payload.get("expected_round_index", -1))
            == int(agent_input.get("round_index", -2))
        ),
        "expected_target_matches_agent_input": (
            str(payload.get("expected_target_file", ""))
            == str(agent_input.get("target_file", ""))
        ),
        "proposal_round_matches_expected": (
            int(proposal.get("round_index", -1))
            == int(payload.get("expected_round_index", -2))
        ),
        "proposal_target_matches_expected": (
            str(proposal.get("target_file", ""))
            == str(payload.get("expected_target_file", ""))
        ),
        "proposal_protocol_matches_top_level": (
            str(proposal.get("protocol_version", ""))
            == str(payload.get("proposal_protocol_version", ""))
        ),
        "proposal_applicable_matches_top_level": (
            bool(proposal.get("applicable", False))
            == bool(payload.get("proposal_applicable", False))
        ),
        "proposal_direction_matches_top_level": (
            str(proposal.get("direction_tag", ""))
            == str(payload.get("proposal_direction_tag", ""))
        ),
        "proposal_patch_hash_matches_top_level": (
            str(proposal.get("patch_sha256", "")) == patch_sha256
        ),
        "patch_hash_matches_patch_diff": (
            (not patch_diff and not patch_sha256)
            or sha256_text(patch_diff) == patch_sha256
        ),
        "raw_output_matches_proposal": (
            not raw_output
            or raw_output.rstrip("\n")
            == str(proposal.get("raw_response", "")).rstrip("\n")
        ),
        "contract_check_matches_errors": (
            bool(checks.get("contract_valid", False))
            == (not bool(agent_validation_contract_errors(errors)))
        ),
        "semantic_check_matches_contract_valid": (
            bool(semantic_checks.get("ok", False))
            == bool(checks.get("contract_valid", False))
        ),
        "semantic_errors_match_report_contract_errors": (
            semantic_errors == agent_validation_contract_errors(errors)
        ),
        "intake_diagnosis_matches_failure_metadata": (
            str(diagnosis.get("primary_stage", ""))
            == str(payload.get("failure_stage", ""))
            and str(diagnosis.get("primary_code", ""))
            == str(payload.get("failure_code", ""))
            and str(diagnosis.get("primary_message", ""))
            == str(payload.get("failure_message", ""))
        ),
        "intake_diagnosis_codes_match_reason_codes": (
            string_list(diagnosis.get("blocking_codes", []))
            == [row["code"] for row in reason_codes]
        ),
        "git_apply_error_matches_errors": (
            not str(checks.get("git_apply_error", ""))
            or any(error.startswith("git apply check failed:") for error in errors)
        ),
        "strategy_only_matches_contract_errors": (
            bool(checks.get("strategy_only_patch", False))
            == (
                not any(
                    "patch_diff target validation failed" in error for error in errors
                )
            )
        ),
    }


def agent_validation_contract_errors(errors: list[str]) -> list[str]:
    """Return agent validation errors that came from proposal contract checks."""
    return [
        error
        for error in errors
        if not error.startswith("git apply check failed:")
    ]


def validate_quarantine_intent_summary_bindings(
    *,
    payload: dict[str, Any],
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate quarantine summary matches selected output and agent input."""
    artifacts = payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        add_error(report, "agent_output_quarantine artifacts invalid")
        return
    summary = payload.get("proposal_intent_summary", {})
    for artifact_key, error_text in (
        ("agent_output", "agent_output_quarantine proposal intent summary drift"),
        (
            "agent_input",
            "agent_output_quarantine proposal intent summary input drift",
        ),
    ):
        record = artifacts.get(artifact_key, {})
        if not isinstance(record, dict):
            add_error(
                report,
                f"agent_output_quarantine artifact record invalid: {artifact_key}",
            )
            continue
        artifact_path = resolve_path(Path(str(record.get("path", ""))), repo_root)
        if not artifact_path.exists() or not artifact_path.is_file():
            add_error(
                report,
                f"agent_output_quarantine artifact missing: {artifact_key}={artifact_path}",
            )
            continue
        artifact_payload = load_json_object(artifact_path, report)
        if artifact_payload is not None and artifact_payload.get(
            "proposal_intent_summary", {}
        ) != summary:
            add_error(report, error_text)


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


def sha256_text(value: str) -> str:
    """Return a SHA-256 digest for text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
        attempt_id = str(row.get("attempt_id", ""))
        validate_candidate_quality_row(
            row=row,
            artifact_name="agent_attempts_manifest.json",
            row_label=attempt_id,
            report=report,
        )
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
            "intake_binding_bound",
            "intake_binding_clean",
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
        "requires_intake_binding",
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
        if contract.get("intake_binding_status") != "bound":
            add_error(report, "codex_cli_contract_fixture intake binding not bound")
        if contract.get("intake_binding_blocking_reasons"):
            add_error(report, "codex_cli_contract_fixture intake binding blocked")
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
    validate_proposal_intent_summary_contract(
        summary=payload.get("proposal_intent_summary", {}),
        artifact_name="attempt_output.json",
        report=report,
    )
    selection = payload.get("selection", {})
    quality_breakdown = (
        selection.get("quality_breakdown", {}) if isinstance(selection, dict) else {}
    )
    validate_candidate_quality_row(
        row={
            "candidate_score": payload.get("candidate_score", 0),
            "quality_breakdown": quality_breakdown,
        },
        artifact_name="attempt_output.json",
        row_label=str(payload.get("attempt_id", "")),
        report=report,
    )
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
        if key == "agent_input" and artifact_path.exists() and artifact_path.is_file():
            agent_input = load_json_object(artifact_path, report)
            if agent_input is not None and agent_input.get(
                "proposal_intent_summary", {}
            ) != payload.get("proposal_intent_summary", {}):
                add_error(report, "attempt_output proposal intent summary drift")
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
        validate_candidate_quality_row(
            row=row,
            artifact_name="agent_executor_report.json",
            row_label=str(row.get("attempt_id", "")),
            report=report,
        )
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
        validate_candidate_quality_row(
            row=row,
            artifact_name="agent_routing_policy.json",
            row_label=str(row.get("attempt_id", "")),
            report=report,
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
        validate_candidate_quality_row(
            row=row,
            artifact_name="agent_selection_report.json",
            row_label=str(row.get("attempt_id", "")),
            report=report,
        )
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
    expected = recompute_direction_capability_from_row(row=row)
    capability_supported = normalized_direction_list(
        capability.get("supported_directions", [])
    )
    row_supported = normalized_direction_list(supported)
    if capability_supported != row_supported:
        add_error(
            report,
            f"{artifact_name} direction_capability supported_directions mismatch",
        )
    for key in (
        "wildcard",
        "supported_by_profile",
        "in_strategy_search_space",
        "ok",
    ):
        if capability.get(key) != expected[key]:
            add_error(
                report,
                f"{artifact_name} direction_capability recompute mismatch: {key}",
            )
    if reason != expected["reason"]:
        add_error(
            report,
            f"{artifact_name} direction_capability recompute mismatch: reason",
        )
    if str(row.get("direction_capability_reason", reason)) != reason:
        add_error(
            report,
            f"{artifact_name} direction_capability_reason does not match capability",
        )
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
    expected = recompute_direction_intent_alignment_from_row(row=row)
    alignment_supported = normalized_direction_list(
        alignment.get("supported_directions", [])
    )
    if alignment_supported != expected["supported_directions"]:
        add_error(
            report,
            f"{artifact_name} direction_intent_alignment supported_directions mismatch",
        )
    for key in (
        "profile_covers_recommended_direction",
        "proposal_matches_recommended_direction",
        "proposal_avoids_blocked_direction",
        "proposal_supported_by_profile",
        "proposal_deviates_from_recommended",
        "deviation_allowed",
        "reason",
    ):
        if alignment.get(key) != expected[key]:
            add_error(
                report,
                f"{artifact_name} direction_intent_alignment recompute mismatch: {key}",
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


def recompute_direction_capability_from_row(
    *,
    row: dict[str, object],
) -> dict[str, object]:
    """Recompute direction-capability fields from the saved candidate row."""
    capability = row.get("direction_capability", {})
    capability = capability if isinstance(capability, dict) else {}
    supported = normalized_direction_list(row.get("supported_directions", []))
    search_space = normalized_direction_list(
        capability.get("strategy_search_space_directions", [])
    )
    proposal_direction = str(row.get("direction_tag", ""))
    wildcard = "*" in supported
    supported_by_profile = bool(proposal_direction) and (
        wildcard or proposal_direction in supported
    )
    in_search_space = (
        proposal_direction in search_space if search_space else bool(proposal_direction)
    )
    ok = supported_by_profile and in_search_space
    reason = ""
    if not proposal_direction:
        reason = "proposal direction_tag is empty"
    elif not in_search_space:
        reason = (
            "proposal direction is outside configured strategy_search_space: "
            f"{proposal_direction}"
        )
    elif not supported_by_profile:
        supported_text = ", ".join(supported) or "none"
        reason = (
            "profile does not support proposal direction "
            f"{proposal_direction}; supported={supported_text}"
        )
    return {
        "supported_directions": supported,
        "wildcard": wildcard,
        "supported_by_profile": supported_by_profile,
        "in_strategy_search_space": in_search_space,
        "ok": ok,
        "reason": reason,
    }


def recompute_direction_intent_alignment_from_row(
    *,
    row: dict[str, object],
) -> dict[str, object]:
    """Recompute audit-only planner/profile/proposal direction alignment."""
    alignment = row.get("direction_intent_alignment", {})
    alignment = alignment if isinstance(alignment, dict) else {}
    capability = row.get("direction_capability", {})
    capability = capability if isinstance(capability, dict) else {}
    recommended_direction = str(alignment.get("recommended_direction", ""))
    proposal_direction = str(row.get("direction_tag", ""))
    supported_directions = normalized_direction_list(row.get("supported_directions", []))
    avoid_directions = string_list(alignment.get("avoid_directions", []))
    wildcard = "*" in supported_directions
    profile_covers_recommended = bool(recommended_direction) and (
        wildcard or recommended_direction in supported_directions
    )
    proposal_matches_recommended = (
        bool(recommended_direction) and proposal_direction == recommended_direction
    )
    proposal_avoids_blocked = proposal_direction not in avoid_directions
    proposal_supported = bool(capability.get("ok", False))
    deviation = bool(
        recommended_direction
        and proposal_direction
        and proposal_direction != recommended_direction
    )
    deviation_allowed = bool(
        deviation and proposal_supported and proposal_avoids_blocked
    )
    reason = recomputed_direction_intent_alignment_reason(
        recommended_direction=recommended_direction,
        proposal_direction=proposal_direction,
        proposal_supported=proposal_supported,
        proposal_matches_recommended=proposal_matches_recommended,
        proposal_avoids_blocked=proposal_avoids_blocked,
        profile_covers_recommended=profile_covers_recommended,
        deviation=deviation,
        deviation_allowed=deviation_allowed,
    )
    return {
        "supported_directions": supported_directions,
        "profile_covers_recommended_direction": profile_covers_recommended,
        "proposal_matches_recommended_direction": proposal_matches_recommended,
        "proposal_avoids_blocked_direction": proposal_avoids_blocked,
        "proposal_supported_by_profile": proposal_supported,
        "proposal_deviates_from_recommended": deviation,
        "deviation_allowed": deviation_allowed,
        "reason": reason,
    }


def recomputed_direction_intent_alignment_reason(
    *,
    recommended_direction: str,
    proposal_direction: str,
    proposal_supported: bool,
    proposal_matches_recommended: bool,
    proposal_avoids_blocked: bool,
    profile_covers_recommended: bool,
    deviation: bool,
    deviation_allowed: bool,
) -> str:
    """Return the expected direction-intent alignment reason text."""
    if not recommended_direction:
        return "proposal intent has no recommended direction"
    if not proposal_direction:
        return "proposal direction_tag is empty"
    if not proposal_supported:
        return "proposal direction is outside profile capability"
    if not proposal_avoids_blocked:
        return f"proposal uses avoided direction {proposal_direction}"
    if proposal_matches_recommended:
        return "proposal matches recommended direction"
    if deviation and deviation_allowed:
        if not profile_covers_recommended:
            return (
                "profile does not cover recommended direction "
                f"{recommended_direction}; proposal uses supported "
                f"non-recommended direction {proposal_direction}"
            )
        return (
            "proposal uses supported non-recommended direction "
            f"{proposal_direction}"
        )
    if not profile_covers_recommended:
        return f"profile does not cover recommended direction {recommended_direction}"
    return "proposal direction alignment is informational"


def normalized_direction_list(value: object) -> list[str]:
    """Return non-empty direction strings from a JSON list-like value."""
    return [direction for direction in string_list(value) if direction]


def validate_required_files(
    *,
    base_dir: Path,
    filenames: tuple[str, ...],
    report: dict[str, object],
    ignored_filenames: tuple[str, ...] = (),
) -> None:
    """Check required files exist and record present files."""
    for filename in filenames:
        path = base_dir / filename
        if not path.exists():
            if filename in ignored_filenames:
                continue
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
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    manifest = load_json_object(run_dir / "manifest.json", report)
    if manifest is not None:
        validate_iteration_diagnosis_summary(
            payload=payload,
            manifest=manifest,
            report=report,
        )
        validate_iteration_diagnosis_best_round(
            payload=payload,
            manifest=manifest,
            report=report,
        )
        validate_iteration_diagnosis_selected_candidates(
            payload=payload,
            run_dir=run_dir,
            report=report,
        )
    validate_diagnosis_operator_navigation(
        payload=payload,
        run_dir=run_dir,
        manifest=manifest,
        report=report,
    )


def validate_iteration_diagnosis_summary(
    *,
    payload: dict[str, object],
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate iteration diagnosis summary fields mirror manifest.json."""
    if str(payload.get("kind", "")) != "iteration_loop":
        add_error(report, "diagnosis.json kind mismatch")
    for field_name in (
        "status",
        "completed_rounds",
        "accepted_round",
        "stop_reason",
        "final_strategy_commit",
    ):
        if payload.get(field_name) != manifest.get(field_name):
            add_error(report, f"diagnosis.json {field_name} mismatch")
    if payload.get("agent_intake_summary") != manifest.get("agent_intake_summary"):
        add_error(report, "diagnosis.json agent_intake_summary mismatch")


def validate_iteration_diagnosis_best_round(
    *,
    payload: dict[str, object],
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate diagnosis best_round mirrors diagnosis rows and manifest deltas."""
    best_round = payload.get("best_round")
    if best_round is None:
        if list_of_dicts(manifest.get("rounds", [])):
            add_error(report, "diagnosis.json best_round missing")
        return
    if not isinstance(best_round, dict):
        add_error(report, "diagnosis.json best_round invalid")
        return

    diagnosis_rounds = list_of_dicts(payload.get("rounds", []))
    matching_round = next(
        (
            row
            for row in diagnosis_rounds
            if str(row.get("round_id", "")) == str(best_round.get("round_id", ""))
        ),
        None,
    )
    if matching_round is None or matching_round != best_round:
        add_error(report, "diagnosis.json best_round row mismatch")

    manifest_rounds = list_of_dicts(manifest.get("rounds", []))
    expected = best_validation_manifest_round(manifest_rounds)
    if expected is None:
        return
    expected_delta = metric_delta_from_round(
        expected,
        "validation_ev_before",
        "validation_ev_after",
    )
    if str(best_round.get("round_id", "")) != str(expected.get("round_id", "")):
        add_error(report, "diagnosis.json best_round round_id mismatch")
    if float_from_object(best_round.get("validation_ev_delta", 0.0)) != expected_delta:
        add_error(report, "diagnosis.json best_round validation_ev_delta mismatch")


def best_validation_manifest_round(
    rows: list[dict[str, object]],
) -> dict[str, object] | None:
    """Return the manifest round with the largest validation EV improvement."""
    if not rows:
        return None
    return max(
        rows,
        key=lambda row: metric_delta_from_round(
            row,
            "validation_ev_before",
            "validation_ev_after",
        ),
    )


def metric_delta_from_round(
    row: dict[str, object],
    before_key: str,
    after_key: str,
) -> float:
    """Return a numeric before/after delta from a manifest round row."""
    return float_from_object(row.get(after_key, 0.0)) - float_from_object(
        row.get(before_key, 0.0)
    )


def float_from_object(value: object) -> float:
    """Return a float for validator comparisons, defaulting invalid values to 0."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def validate_iteration_diagnosis_selected_candidates(
    *,
    payload: dict[str, object],
    run_dir: Path,
    report: dict[str, object],
) -> None:
    """Validate diagnosis selected candidates mirror candidate_leaderboard.json."""
    candidate_rows = list_of_dicts(load_json_list(run_dir / "candidate_leaderboard.json"))
    expected = [
        compact_diagnosis_selected_candidate(row)
        for row in candidate_rows
        if row.get("selected") is True
    ]
    if payload.get("selected_candidates") != expected:
        add_error(report, "diagnosis.json selected_candidates mismatch")


def compact_diagnosis_selected_candidate(row: dict[str, object]) -> dict[str, object]:
    """Return the compact selected-candidate shape saved in diagnosis.json."""
    return {
        "round_id": row.get("round_id", ""),
        "role": row.get("role", ""),
        "agent_name": row.get("agent_name", ""),
        "direction_tag": row.get("direction_tag", ""),
        "candidate_score": row.get("candidate_score", 0),
        "champion_gap": row.get("champion_gap", {}),
        "validation_ev_delta": row.get("validation_ev_delta"),
        "status": row.get("status", ""),
    }


def validate_diagnosis_operator_navigation(
    *,
    payload: dict[str, object],
    run_dir: Path,
    manifest: dict[str, object] | None,
    report: dict[str, object],
) -> None:
    """Validate diagnosis operator navigation when the block is present."""
    navigation = payload.get("operator_navigation")
    if navigation is None:
        return
    if not isinstance(navigation, dict):
        add_error(report, "diagnosis.json operator_navigation invalid")
        return
    if navigation.get("schema_version") != "run_diagnosis_operator_navigation_v1":
        add_error(report, "diagnosis.json operator_navigation schema invalid")
    run_id = str(report.get("run_id", ""))
    if str(navigation.get("run_id", "")) != run_id:
        add_error(report, "diagnosis.json operator_navigation run_id mismatch")
    policy = object_value(navigation.get("policy", {}))
    for key in (
        "inspection_only",
        "does_not_create_artifacts",
        "does_not_record_approval",
        "does_not_execute_commands",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_write_config",
        "does_not_promote_champion",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            add_error(report, f"diagnosis.json operator_navigation policy false: {key}")

    if manifest is not None:
        validate_iteration_diagnosis_operator_navigation(
            navigation=navigation,
            manifest=manifest,
            run_id=run_id,
            report=report,
        )
        return
    if (run_dir / "decision.json").exists():
        validate_unavailable_diagnosis_operator_navigation(
            navigation=navigation,
            run_kind="single_run",
            reason="not_iteration_run",
            report=report,
        )


def validate_iteration_diagnosis_operator_navigation(
    *,
    navigation: dict[str, object],
    manifest: dict[str, object],
    run_id: str,
    report: dict[str, object],
) -> None:
    """Validate iteration diagnosis navigation mirrors manifest.operator_home."""
    manifest_home = manifest.get("operator_home", {})
    if not isinstance(manifest_home, dict) or not str(manifest_home.get("command", "")):
        validate_unavailable_diagnosis_operator_navigation(
            navigation=navigation,
            run_kind="iteration_loop",
            reason="operator_home_unavailable",
            report=report,
        )
        return
    if navigation.get("available") is not True:
        add_error(report, "diagnosis.json operator_navigation unavailable")
    if str(navigation.get("reason", "")) != "iteration_run":
        add_error(report, "diagnosis.json operator_navigation reason mismatch")
    if str(navigation.get("run_kind", "")) != "iteration_loop":
        add_error(report, "diagnosis.json operator_navigation kind mismatch")

    home = object_value(navigation.get("home", {}))
    next_command = object_value(navigation.get("next_command", {}))
    expected_home_fields: tuple[tuple[str, str], ...] = (
        ("command_label", "command_label"),
        ("command", "command"),
        ("status", "status"),
        ("primary_focus", "primary_focus"),
        ("action_step", "action_step"),
        ("command_boundary", "command_boundary"),
    )
    if home.get("available") is not True:
        add_error(report, "diagnosis.json operator_navigation home unavailable")
    for nav_key, manifest_key in expected_home_fields:
        if str(home.get(nav_key, "")) != str(manifest_home.get(manifest_key, "")):
            add_error(
                report,
                f"diagnosis.json operator_navigation home {nav_key} mismatch",
            )
    for nav_key, manifest_key in (
        ("terminal_only", "terminal_only"),
        ("artifact_created", "artifact_created"),
        ("command_is_hint_only", "command_is_hint_only"),
    ):
        if bool(home.get(nav_key, False)) != bool(manifest_home.get(manifest_key, False)):
            add_error(
                report,
                f"diagnosis.json operator_navigation home {nav_key} mismatch",
            )

    expected_selector = (
        f"python -m orchestrator.experiments next-command {run_id} --markdown"
    )
    if next_command.get("available") is not bool(manifest_home.get("next_command", "")):
        add_error(report, "diagnosis.json operator_navigation next availability mismatch")
    if str(next_command.get("selection_source", "")) != "operator_home.next_command":
        add_error(report, "diagnosis.json operator_navigation next source mismatch")
    if str(next_command.get("selector_command_label", "")) != (
        "review_operator_next_command"
    ):
        add_error(report, "diagnosis.json operator_navigation selector label mismatch")
    if str(next_command.get("selector_command", "")) != expected_selector:
        add_error(report, "diagnosis.json operator_navigation selector command mismatch")
    if str(next_command.get("selector_boundary", "")) != "read_only_inspection":
        add_error(report, "diagnosis.json operator_navigation selector boundary mismatch")

    for nav_key, manifest_key in (
        ("selected_command_label", "next_command_label"),
        ("selected_command", "next_command"),
        ("status", "next_command_status"),
        ("operator_hint", "next_command_operator_hint"),
        ("boundary", "next_command_boundary"),
        ("writes_artifact", "next_command_writes_artifact"),
    ):
        if str(next_command.get(nav_key, "")) != str(manifest_home.get(manifest_key, "")):
            add_error(
                report,
                f"diagnosis.json operator_navigation next {nav_key} mismatch",
            )
    if bool(next_command.get("blocked", False)) != bool(
        manifest_home.get("next_command_blocked", False)
    ):
        add_error(report, "diagnosis.json operator_navigation next blocked mismatch")
    if int_value(next_command.get("blocker_count", 0)) != int_value(
        manifest_home.get("next_command_blocker_count", 0)
    ):
        add_error(
            report,
            "diagnosis.json operator_navigation next blocker_count mismatch",
        )
    for nav_key, manifest_key in (
        (
            "requires_explicit_operator_invocation",
            "next_command_requires_explicit_operator_invocation",
        ),
        ("requires_operator_approval", "next_command_requires_operator_approval"),
        ("records_operator_approval", "next_command_records_operator_approval"),
        ("uses_guarded_executor", "next_command_uses_guarded_executor"),
        ("command_is_hint_only", "next_command_is_hint_only"),
    ):
        if bool(next_command.get(nav_key, False)) != bool(
            manifest_home.get(manifest_key, False)
        ):
            add_error(
                report,
                f"diagnosis.json operator_navigation next {nav_key} mismatch",
            )


def validate_unavailable_diagnosis_operator_navigation(
    *,
    navigation: dict[str, object],
    run_kind: str,
    reason: str,
    report: dict[str, object],
) -> None:
    """Validate unavailable diagnosis navigation fields stay empty."""
    if navigation.get("available") is not False:
        add_error(report, "diagnosis.json operator_navigation availability mismatch")
    if str(navigation.get("reason", "")) != reason:
        add_error(report, "diagnosis.json operator_navigation reason mismatch")
    if str(navigation.get("run_kind", "")) != run_kind:
        add_error(report, "diagnosis.json operator_navigation kind mismatch")
    home = object_value(navigation.get("home", {}))
    next_command = object_value(navigation.get("next_command", {}))
    if home.get("available") is not False or str(home.get("command", "")):
        add_error(report, "diagnosis.json operator_navigation home unavailable mismatch")
    if str(home.get("status", "")) != "unavailable":
        add_error(report, "diagnosis.json operator_navigation home status mismatch")
    if next_command.get("available") is not False:
        add_error(report, "diagnosis.json operator_navigation next unavailable mismatch")
    if str(next_command.get("status", "")) != "unavailable":
        add_error(report, "diagnosis.json operator_navigation next status mismatch")
    if str(next_command.get("selected_command", "")):
        add_error(report, "diagnosis.json operator_navigation next command mismatch")
    if bool(next_command.get("blocked", False)) is not False:
        add_error(report, "diagnosis.json operator_navigation next blocked mismatch")
    if int_value(next_command.get("blocker_count", 0)) != 0:
        add_error(
            report,
            "diagnosis.json operator_navigation next blocker_count mismatch",
        )


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
    dashboard = payload.get("operator_dashboard", {})
    if not isinstance(dashboard, dict):
        add_error(report, "run_closeout.json operator_dashboard invalid")
        return
    dashboard_policy = dashboard.get("policy", {})
    if not isinstance(dashboard_policy, dict):
        add_error(report, "run_closeout.json operator_dashboard policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_write_config",
        "does_not_promote_champion",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_change_acceptance",
    ):
        if dashboard_policy.get(key) is not True:
            add_error(
                report,
                f"run_closeout.json operator_dashboard policy false: {key}",
            )


def validate_optional_operator_action_plan(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate operator_action_plan.json/md when a run has one."""
    path = run_dir / "operator_action_plan.json"
    md_path = run_dir / "operator_action_plan.md"
    if not path.exists() and not md_path.exists():
        return
    if not path.exists():
        add_error(report, f"missing operator action plan JSON artifact: {path}")
        return
    if not md_path.exists():
        add_error(report, f"missing operator action plan markdown artifact: {md_path}")
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/operator_action_plan.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, f"operator_action_plan.json run_id mismatch: {path}")
    source = payload.get("source_closeout", {})
    if not isinstance(source, dict):
        add_error(report, "operator_action_plan.json source_closeout invalid")
    else:
        source_file = source.get("file", {})
        if not isinstance(source_file, dict):
            add_error(report, "operator_action_plan.json source file invalid")
        else:
            validate_recorded_file_hash(
                record=source_file,
                repo_root=repo_root,
                report=report,
                label="operator_action_plan source closeout",
            )
            closeout_path = resolve_path(
                Path(str(source_file.get("path", ""))),
                repo_root,
            )
            if not closeout_path.name == "run_closeout.json":
                add_error(report, "operator_action_plan source is not run_closeout.json")
            if source_file.get("sha256") != file_sha256(closeout_path):
                add_error(report, "operator_action_plan source digest mismatch")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "operator_action_plan.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_execute_commands",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_write_config",
        "does_not_promote_champion",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_change_acceptance",
        "commands_require_explicit_operator_invocation",
    ):
        if policy.get(key) is not True:
            add_error(report, f"operator_action_plan.json policy false: {key}")
    actions = payload.get("actions", [])
    if not isinstance(actions, list):
        add_error(report, "operator_action_plan.json actions invalid")
        return
    for index, action in enumerate(actions, start=1):
        if not isinstance(action, dict):
            add_error(report, f"operator_action_plan.json action {index} invalid")
            continue
        authority = action.get("authority", {})
        if not isinstance(authority, dict):
            add_error(report, f"operator_action_plan.json action {index} authority invalid")
        else:
            for key in (
                "plan_can_execute",
                "plan_can_write_config",
                "plan_can_promote_champion",
            ):
                if authority.get(key) is not False:
                    add_error(
                        report,
                        f"operator_action_plan.json action {index} authority true: {key}",
                    )
        commands = action.get("command_candidates", [])
        if not isinstance(commands, list):
            add_error(report, f"operator_action_plan.json action {index} commands invalid")
            continue
        validate_operator_action_plan_command_candidates(
            action=action,
            action_index=index,
            report=report,
        )
        for command_index, command in enumerate(commands, start=1):
            if not isinstance(command, dict):
                add_error(
                    report,
                    f"operator_action_plan.json action {index} command {command_index} invalid",
                )
                continue
            if command.get("executed_by_plan") is not False:
                add_error(
                    report,
                    "operator_action_plan.json command executed_by_plan must be false",
                )
            if command.get("requires_explicit_operator_invocation") is not True:
                add_error(
                    report,
                    "operator_action_plan.json command missing explicit invocation flag",
                )
            if command.get("command_sha256") != sha256_text(str(command.get("command", ""))):
                add_error(
                    report,
                    "operator_action_plan.json command sha256 mismatch",
                )


def operator_action_plan_expected_artifacts() -> dict[str, str]:
    """Return expected action-plan command labels and artifact outputs."""
    return {
        "validate_run_artifacts": "run_artifact_health.json",
        "inspect_scope_health": "experiment_scope_health.json",
        "inspect_config_lineage": "config_lineage.json",
        "inspect_config_candidate": "config_change_candidate.json",
        "inspect_promotion_approval": "champion_promotion_approval.json",
        "promote_from_approval": "champion_promotion_receipt.json",
        "inspect_candidates": "candidate_leaderboard.json",
        "inspect_quality_trace": "candidate_quality_trace.json",
        "inspect_profile_recommendation": "modifier_profile_recommendation.json",
        "start_next_iteration": "manifest.json",
        "review_run_dashboard": "run_closeout.md",
        "inspect_research_brief": "research_brief.json",
    }


def validate_operator_action_plan_command_candidates(
    *,
    action: dict[str, object],
    action_index: int,
    report: dict[str, object],
) -> None:
    """Validate operator action plan command candidates stay bounded."""
    validate_recommended_command_hints(
        payload=action,
        report=report,
        artifact_label="operator_action_plan",
        allowed_writes=operator_action_plan_expected_artifacts(),
        unsafe_tokens=("&&", "||", "|", "`", "$(", "\n", ";"),
        commands_field="command_candidates",
        writes_field="expected_artifact",
        command_noun=f"action {action_index} command",
        allow_empty=True,
    )


def validate_optional_operator_action_approval(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate operator_action_approval.json/md when a run has one."""
    path = run_dir / "operator_action_approval.json"
    md_path = run_dir / "operator_action_approval.md"
    if not path.exists() and not md_path.exists():
        return
    if not path.exists():
        add_error(report, f"missing operator action approval JSON artifact: {path}")
        return
    if not md_path.exists():
        add_error(report, f"missing operator action approval markdown artifact: {md_path}")
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/operator_action_approval.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, f"operator_action_approval.json run_id mismatch: {path}")
    action_plan: dict[str, Any] = {}
    source = payload.get("source_action_plan", {})
    if not isinstance(source, dict):
        add_error(report, "operator_action_approval.json source_action_plan invalid")
    else:
        source_file = source.get("file", {})
        if not isinstance(source_file, dict):
            add_error(report, "operator_action_approval.json source file invalid")
        else:
            validate_recorded_file_hash(
                record=source_file,
                repo_root=repo_root,
                report=report,
                label="operator_action_approval source action plan",
            )
            plan_path = resolve_path(
                Path(str(source_file.get("path", ""))),
                repo_root,
            )
            if not plan_path.name == "operator_action_plan.json":
                add_error(
                    report,
                    "operator_action_approval source is not operator_action_plan.json",
                )
            if source_file.get("sha256") != file_sha256(plan_path):
                add_error(report, "operator_action_approval source digest mismatch")
            loaded_plan = load_json_object(plan_path, report)
            if loaded_plan is not None:
                action_plan = loaded_plan
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "operator_action_approval.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_execute_commands",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_write_config",
        "does_not_promote_champion",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_change_acceptance",
        "approval_does_not_execute_command",
        "command_still_requires_explicit_execution",
    ):
        if policy.get(key) is not True:
            add_error(report, f"operator_action_approval.json policy false: {key}")
    intent = payload.get("operator_intent", {})
    gate = payload.get("approval_gate", {})
    command = payload.get("selected_command", {})
    if not isinstance(intent, dict):
        add_error(report, "operator_action_approval.json operator_intent invalid")
        intent = {}
    if not isinstance(gate, dict):
        add_error(report, "operator_action_approval.json approval_gate invalid")
        gate = {}
    if not isinstance(command, dict):
        add_error(report, "operator_action_approval.json selected_command invalid")
        command = {}
    if command.get("executed_by_approval") is not False:
        add_error(report, "operator_action_approval.json command executed by approval")
    if command.get("command") and command.get("command_sha256_matches") is not True:
        add_error(report, "operator_action_approval.json command digest mismatch")
    validate_operator_action_approval_selection(
        action_plan=action_plan,
        intent=intent,
        selected_action=payload.get("selected_action", {}),
        selected_command=command,
        report=report,
    )
    approval_recorded = bool(intent.get("approval_recorded", False))
    if approval_recorded:
        if gate.get("eligible_for_approval") is not True:
            add_error(report, "operator_action_approval.json approval recorded ineligible")
        if gate.get("approval_blockers") not in ([], ()):
            add_error(report, "operator_action_approval.json approval recorded with blockers")
        if intent.get("explicit_approval") is not True:
            add_error(report, "operator_action_approval.json approval flag missing")
        if intent.get("confirmation_phrase_matches") is not True:
            add_error(report, "operator_action_approval.json confirmation mismatch")


def validate_operator_action_approval_selection(
    *,
    action_plan: dict[str, Any],
    intent: dict[str, object],
    selected_action: object,
    selected_command: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate approval selection still matches the saved action plan."""
    if not action_plan:
        return
    if not isinstance(selected_action, dict):
        add_error(report, "operator_action_approval selected_action invalid")
        selected_action = {}
    target_action_id = str(intent.get("target_action_id", ""))
    target_command_label = str(intent.get("target_command_label", ""))
    plan_action = find_operator_action_plan_action(
        action_plan=action_plan,
        action_id=target_action_id,
    )
    if not plan_action:
        add_error(report, "operator_action_approval selected action missing from plan")
        return
    plan_command = find_operator_action_plan_command(
        action=plan_action,
        command_label=target_command_label,
    )
    if not plan_command:
        add_error(report, "operator_action_approval selected command missing from plan")
        return
    for key in ("action_id", "action_type", "status", "source_text"):
        if str(selected_action.get(key, "")) != str(plan_action.get(key, "")):
            add_error(report, f"operator_action_approval selected action mismatch: {key}")
    for key in operator_command_binding_fields():
        if selected_command.get(key) != normalized_operator_command(plan_command).get(key):
            add_error(report, f"operator_action_approval selected command mismatch: {key}")


def find_operator_action_plan_action(
    *,
    action_plan: dict[str, Any],
    action_id: str,
) -> dict[str, object]:
    """Return one action-plan action by id."""
    for action in list_of_dicts(action_plan.get("actions", [])):
        if str(action.get("action_id", "")) == action_id:
            return action
    return {}


def find_operator_action_plan_command(
    *,
    action: dict[str, object],
    command_label: str,
) -> dict[str, object]:
    """Return one action-plan command by label."""
    for command in list_of_dicts(action.get("command_candidates", [])):
        if str(command.get("label", "")) == command_label:
            return command
    return {}


def operator_command_binding_fields() -> tuple[str, ...]:
    """Return command fields that must stay bound across operator artifacts."""
    return (
        "label",
        "command",
        "command_sha256",
        "expected_artifact",
        "writes_repository",
        "promotes_champion",
        "runs_backtests",
        "requires_explicit_operator_invocation",
    )


def normalized_operator_command(command: dict[str, object]) -> dict[str, object]:
    """Return a stable command subset for cross-artifact binding checks."""
    return {
        "label": str(command.get("label", "")),
        "command": str(command.get("command", "")),
        "command_sha256": str(command.get("command_sha256", "")),
        "expected_artifact": str(command.get("expected_artifact", "")),
        "writes_repository": bool(command.get("writes_repository", False)),
        "promotes_champion": bool(command.get("promotes_champion", False)),
        "runs_backtests": bool(command.get("runs_backtests", False)),
        "requires_explicit_operator_invocation": bool(
            command.get("requires_explicit_operator_invocation", False)
        ),
    }


def validate_optional_operator_action_execution_receipt(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate operator_action_execution_receipt.json/md when present."""
    path = run_dir / "operator_action_execution_receipt.json"
    md_path = run_dir / "operator_action_execution_receipt.md"
    if not path.exists() and not md_path.exists():
        return
    if not path.exists():
        add_error(report, f"missing operator action execution receipt JSON: {path}")
        return
    if not md_path.exists():
        add_error(report, f"missing operator action execution receipt markdown: {md_path}")
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root
        / "schemas/operator_action_execution_receipt.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, "operator_action_execution_receipt.json run_id mismatch")

    approval_payload: dict[str, Any] = {}
    source = payload.get("source_approval", {})
    if not isinstance(source, dict):
        add_error(report, "operator_action_execution_receipt.json source invalid")
        source = {}
    source_file = source.get("file", {})
    if not isinstance(source_file, dict):
        add_error(report, "operator_action_execution_receipt.json source file invalid")
        source_file = {}
    else:
        validate_recorded_file_hash(
            record=source_file,
            repo_root=repo_root,
            report=report,
            label="operator_action_execution source approval",
        )
        approval_path = resolve_path(Path(str(source_file.get("path", ""))), repo_root)
        if approval_path.name != "operator_action_approval.json":
            add_error(
                report,
                "operator_action_execution source is not operator_action_approval.json",
            )
        if source_file.get("sha256") != file_sha256(approval_path):
            add_error(report, "operator_action_execution source digest mismatch")
        loaded_approval = load_json_object(approval_path, report)
        if loaded_approval is not None:
            approval_payload = loaded_approval

    command = payload.get("selected_command", {})
    if not isinstance(command, dict):
        add_error(report, "operator_action_execution selected_command invalid")
        command = {}
    command_text = str(command.get("command", ""))
    command_sha256 = hashlib.sha256(command_text.encode("utf-8")).hexdigest()
    if command_text and str(command.get("command_sha256", "")) != command_sha256:
        add_error(report, "operator_action_execution selected command digest mismatch")
    if command.get("writes_repository") is True:
        add_error(report, "operator_action_execution command writes repository")
    if command.get("promotes_champion") is True:
        add_error(report, "operator_action_execution command promotes champion")
    if command.get("runs_backtests") is True and payload.get("executed") is True:
        add_error(report, "operator_action_execution executed backtest command")
    execution = payload.get("command_execution", {})
    if not isinstance(execution, dict):
        add_error(report, "operator_action_execution command_execution invalid")
        execution = {}
    validate_operator_action_execution_binding(
        receipt=payload,
        approval=approval_payload,
        source=source,
        selected_command=command,
        execution=execution,
        report=report,
    )

    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "operator_action_execution_receipt.json policy invalid")
        return
    for key in (
        "requires_operator_action_approval",
        "requires_approval_recorded",
        "requires_command_digest_match",
        "requires_source_action_plan_digest_match",
        "executes_only_allowlisted_read_only_commands",
        "blocks_repository_writing_commands",
        "blocks_champion_promotion_commands",
        "blocks_backtest_commands",
        "records_stdout_stderr_hashes",
        "checks_tracked_workspace_mutation",
        "does_not_execute_agents",
        "does_not_write_config",
        "does_not_promote_champion",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            add_error(
                report,
                f"operator_action_execution_receipt.json policy false: {key}",
            )

    mutation = payload.get("mutation_guard", {})
    if not isinstance(mutation, dict):
        add_error(report, "operator_action_execution mutation_guard invalid")
        mutation = {}
    if payload.get("status") == "completed":
        if payload.get("ok") is not True:
            add_error(report, "operator_action_execution completed but not ok")
        if payload.get("executed") is not True:
            add_error(report, "operator_action_execution completed but not executed")
        if execution.get("status") != "completed":
            add_error(report, "operator_action_execution status mismatch")
        if execution.get("returncode") != 0:
            add_error(report, "operator_action_execution returncode not zero")
        if mutation.get("ok") is not True:
            add_error(report, "operator_action_execution mutation guard failed")
        if mutation.get("tracked_status_unchanged") is not True:
            add_error(report, "operator_action_execution tracked status changed")
    if payload.get("status") == "blocked" and payload.get("executed") is not False:
        add_error(report, "operator_action_execution blocked but executed")


def validate_operator_action_execution_binding(
    *,
    receipt: dict[str, Any],
    approval: dict[str, Any],
    source: dict[str, object],
    selected_command: dict[str, object],
    execution: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate execution receipt fields bind to approval and execution evidence."""
    if approval:
        approval_source = approval.get("source_action_plan", {})
        if not isinstance(approval_source, dict):
            approval_source = {}
        approval_source_file = approval_source.get("file", {})
        if not isinstance(approval_source_file, dict):
            approval_source_file = {}
        evidence = receipt.get("evidence_checks", {})
        if not isinstance(evidence, dict):
            evidence = {}
        approval_action = approval.get("selected_action", {})
        receipt_action = receipt.get("selected_action", {})
        if not isinstance(approval_action, dict):
            approval_action = {}
        if not isinstance(receipt_action, dict):
            receipt_action = {}
        for key in ("action_id", "action_type", "status", "source_text"):
            if str(receipt_action.get(key, "")) != str(approval_action.get(key, "")):
                add_error(report, f"operator_action_execution selected action mismatch: {key}")
        approval_command = approval.get("selected_command", {})
        if not isinstance(approval_command, dict):
            approval_command = {}
        for key in operator_command_binding_fields():
            if normalized_operator_command(selected_command).get(key) != (
                normalized_operator_command(approval_command).get(key)
            ):
                add_error(
                    report,
                    f"operator_action_execution selected command mismatch: {key}",
                )
        source_approval_recorded = bool(source.get("approval_recorded", False))
        approval_recorded = bool(
            dict_field(approval, "operator_intent").get("approval_recorded", False)
        )
        if source_approval_recorded != approval_recorded:
            add_error(report, "operator_action_execution approval_recorded mismatch")
        if str(source.get("approval_status", "")) != str(approval.get("status", "")):
            add_error(report, "operator_action_execution approval status mismatch")
        if str(evidence.get("source_action_plan_path", "")) != str(
            approval_source_file.get("path", "")
        ):
            add_error(report, "operator_action_execution source action plan path mismatch")
        if str(evidence.get("source_action_plan_sha256", "")) != str(
            approval_source_file.get("sha256", "")
        ):
            add_error(report, "operator_action_execution source action plan sha mismatch")
    command_text = str(selected_command.get("command", ""))
    if str(execution.get("command", "")) != command_text:
        add_error(report, "operator_action_execution command_execution command mismatch")
    if execution.get("argv") != parse_shell_words(command_text):
        add_error(report, "operator_action_execution command_execution argv mismatch")
    evidence = receipt.get("evidence_checks", {})
    if not isinstance(evidence, dict):
        add_error(report, "operator_action_execution evidence_checks invalid")
        evidence = {}
    command_sha = sha256_text(command_text)
    if str(evidence.get("selected_command_sha256", "")) != str(
        selected_command.get("command_sha256", "")
    ):
        add_error(report, "operator_action_execution evidence selected sha mismatch")
    if str(evidence.get("computed_command_sha256", "")) != command_sha:
        add_error(report, "operator_action_execution evidence computed sha mismatch")


def dict_field(payload: dict[str, Any], key: str) -> dict[str, object]:
    """Return a dict field or an empty dict."""
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def parse_shell_words(command: str) -> list[str]:
    """Parse a command into argv without running a shell."""
    try:
        return shlex.split(command)
    except ValueError:
        return []


def validate_optional_operator_action_audit(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate operator_action_audit.json/md when present."""
    path = run_dir / "operator_action_audit.json"
    md_path = run_dir / "operator_action_audit.md"
    if not path.exists() and not md_path.exists():
        return
    if not path.exists():
        add_error(report, f"missing operator action audit JSON: {path}")
        return
    if not md_path.exists():
        add_error(report, f"missing operator action audit markdown: {md_path}")
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/operator_action_audit.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, "operator_action_audit.json run_id mismatch")
    sources = payload.get("source_artifacts", {})
    if not isinstance(sources, dict):
        add_error(report, "operator_action_audit.json source_artifacts invalid")
        sources = {}
    for source_key, expected_name in (
        ("action_plan", "operator_action_plan.json"),
        ("action_approval", "operator_action_approval.json"),
        ("execution_receipt", "operator_action_execution_receipt.json"),
    ):
        source = sources.get(source_key, {})
        if not isinstance(source, dict):
            add_error(report, f"operator_action_audit source invalid: {source_key}")
            continue
        source_file = source.get("file", {})
        if not isinstance(source_file, dict):
            add_error(report, f"operator_action_audit source file invalid: {source_key}")
            continue
        if source_file.get("exists") is True:
            validate_recorded_file_hash(
                record=source_file,
                repo_root=repo_root,
                report=report,
                label=f"operator_action_audit {source_key}",
            )
            source_path = resolve_path(Path(str(source_file.get("path", ""))), repo_root)
            if source_path.name != expected_name:
                add_error(
                    report,
                    f"operator_action_audit source path invalid: {source_key}",
                )
    checks = payload.get("chain_checks", {})
    if not isinstance(checks, dict):
        add_error(report, "operator_action_audit.json chain_checks invalid")
        checks = {}
    for key in (
        "plan_schema_errors",
        "approval_schema_errors",
        "execution_schema_errors",
        "consistency_errors",
    ):
        if checks.get(key) not in ([], ()):
            add_error(report, f"operator_action_audit.json {key} not empty")
    if payload.get("ok") is not True:
        add_error(report, "operator_action_audit.json ok false")
    if checks.get("ok") is not True:
        add_error(report, "operator_action_audit.json chain check failed")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "operator_action_audit.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_execute_commands",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_write_config",
        "does_not_promote_champion",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            add_error(report, f"operator_action_audit.json policy false: {key}")


def validate_optional_operator_action_dashboard(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate operator_action_dashboard.json/md when present."""
    path = run_dir / "operator_action_dashboard.json"
    md_path = run_dir / "operator_action_dashboard.md"
    if not path.exists() and not md_path.exists():
        return
    if not path.exists():
        add_error(report, f"missing operator action dashboard JSON: {path}")
        return
    if not md_path.exists():
        add_error(report, f"missing operator action dashboard markdown: {md_path}")
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/operator_action_dashboard.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, "operator_action_dashboard.json run_id mismatch")

    sources = payload.get("source_artifacts", {})
    if not isinstance(sources, dict):
        add_error(report, "operator_action_dashboard.json source_artifacts invalid")
        sources = {}
    for source_key, expected_name in (
        ("action_plan", "operator_action_plan.json"),
        ("action_approval", "operator_action_approval.json"),
        ("execution_receipt", "operator_action_execution_receipt.json"),
        ("action_audit", "operator_action_audit.json"),
    ):
        source = sources.get(source_key, {})
        if not isinstance(source, dict):
            add_error(report, f"operator_action_dashboard source invalid: {source_key}")
            continue
        source_file = source.get("file", {})
        if not isinstance(source_file, dict):
            add_error(
                report,
                f"operator_action_dashboard source file invalid: {source_key}",
            )
            continue
        if source_file.get("exists") is True:
            validate_recorded_file_hash(
                record=source_file,
                repo_root=repo_root,
                report=report,
                label=f"operator_action_dashboard {source_key}",
            )
            source_path = resolve_path(Path(str(source_file.get("path", ""))), repo_root)
            if source_path.name != expected_name:
                add_error(
                    report,
                    f"operator_action_dashboard source path invalid: {source_key}",
                )
    for row in list_of_dicts(payload.get("timeline", [])):
        artifact_path = resolve_path(Path(str(row.get("artifact_path", ""))), repo_root)
        if bool(row.get("artifact_exists", False)) != artifact_path.exists():
            add_error(
                report,
                "operator_action_dashboard timeline artifact existence mismatch",
            )

    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        add_error(report, "operator_action_dashboard.json summary invalid")
        summary = {}
    if payload.get("ok") is not True:
        add_error(report, "operator_action_dashboard.json ok false")
    if summary.get("chain_ok") is not True:
        add_error(report, "operator_action_dashboard.json chain not ok")
    if int(summary.get("blocker_count", 0) or 0) != len(
        string_list(payload.get("blockers", []))
    ):
        add_error(report, "operator_action_dashboard blocker count mismatch")
    validate_operator_action_dashboard_recommended_commands(
        payload=payload,
        report=report,
    )
    validate_operator_action_dashboard_execution_readiness(
        payload=payload,
        report=report,
    )
    validate_operator_action_dashboard_path_closure(
        payload=payload,
        report=report,
    )

    authority = payload.get("authority", {})
    if not isinstance(authority, dict):
        add_error(report, "operator_action_dashboard.json authority invalid")
        authority = {}
    for key in (
        "approval_required_before_execution",
        "execution_must_use_guarded_executor",
    ):
        if authority.get(key) is not True:
            add_error(report, f"operator_action_dashboard authority false: {key}")
    for key in (
        "dashboard_can_execute_commands",
        "dashboard_can_approve_commands",
        "dashboard_can_change_repository",
    ):
        if authority.get(key) is not False:
            add_error(report, f"operator_action_dashboard authority true: {key}")

    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "operator_action_dashboard.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_record_approval",
        "does_not_execute_commands",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_write_config",
        "does_not_promote_champion",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            add_error(report, f"operator_action_dashboard.json policy false: {key}")


def validate_operator_action_dashboard_recommended_commands(
    *,
    payload: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate action-dashboard command hints stay within known boundaries."""
    validate_recommended_command_hints(
        payload=payload,
        report=report,
        artifact_label="operator_action_dashboard",
        allowed_writes={
            "write_action_audit": "operator_action_audit.json",
            "record_operator_approval": "operator_action_approval.json",
            "execute_approved_command": "operator_action_execution_receipt.json",
            "review_execution_receipt": "",
            "review_action_dashboard": "",
        },
        unsafe_tokens=("&&", "||", "|", "`", "$(", "\n", ";"),
        current_step_field="current_step",
        current_step_error="operator_action_dashboard current step command missing",
        required_label_errors={
            "review_action_dashboard": (
                "operator_action_dashboard review command missing"
            ),
        },
    )


def validate_operator_action_dashboard_execution_readiness(
    *,
    payload: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate action-dashboard pre-execution readiness summary fields."""
    readiness = payload.get("execution_readiness", {})
    if not isinstance(readiness, dict):
        add_error(report, "operator_action_dashboard execution_readiness invalid")
        return
    status = str(payload.get("status", ""))
    readiness_status = str(readiness.get("status", ""))
    if status == "ready_for_execution":
        if readiness_status != "ready_for_guarded_execution":
            add_error(report, "operator_action_dashboard readiness status mismatch")
        if readiness.get("ready") is not True:
            add_error(report, "operator_action_dashboard readiness not ready")
    elif readiness.get("ready") is True:
        add_error(report, "operator_action_dashboard readiness ready mismatch")
    blockers = string_list(payload.get("blockers", []))
    if readiness.get("blocker_count") != len(blockers):
        add_error(report, "operator_action_dashboard readiness blocker mismatch")
    missing_artifacts = readiness.get("missing_artifacts", [])
    if not isinstance(missing_artifacts, list):
        add_error(report, "operator_action_dashboard readiness missing artifacts invalid")
        missing_artifacts = []
    if readiness.get("missing_artifact_count") != len(missing_artifacts):
        add_error(
            report,
            "operator_action_dashboard readiness missing artifact count mismatch",
        )
    commands = list_of_dicts(payload.get("recommended_commands", []))
    command = next(
        (
            row
            for row in commands
            if str(row.get("label", "")) == str(readiness.get("next_command_label", ""))
        ),
        None,
    )
    if command is None:
        add_error(report, "operator_action_dashboard readiness command missing")
    else:
        boundary = command.get("boundary", {})
        if not isinstance(boundary, dict):
            boundary = {}
        if str(readiness.get("next_command_boundary", "")) != str(
            boundary.get("boundary_type", "")
        ):
            add_error(report, "operator_action_dashboard readiness boundary mismatch")
    dependencies = readiness.get("dependencies", [])
    if not isinstance(dependencies, list):
        add_error(report, "operator_action_dashboard readiness dependencies invalid")
    policy = readiness.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "operator_action_dashboard readiness policy invalid")
        return
    for key in (
        "inspection_only",
        "does_not_execute_commands",
        "does_not_record_approval",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            add_error(
                report,
                f"operator_action_dashboard readiness policy false: {key}",
            )


def validate_operator_action_dashboard_path_closure(
    *,
    payload: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate action-dashboard end-to-end path closure evidence."""
    closure = payload.get("path_closure", {})
    if not isinstance(closure, dict):
        add_error(report, "operator_action_dashboard path_closure invalid")
        return
    status = str(payload.get("status", ""))
    blockers = string_list(payload.get("blockers", []))
    steps = list_of_dicts(closure.get("steps", []))
    completed_step_count = sum(1 for row in steps if row.get("complete") is True)
    required_step_count = sum(1 for row in steps if row.get("required") is True)
    if closure.get("completed_step_count") != completed_step_count:
        add_error(report, "operator_action_dashboard closure completed count mismatch")
    if closure.get("required_step_count") != required_step_count:
        add_error(report, "operator_action_dashboard closure required count mismatch")
    if closure.get("blocker_count") != len(blockers):
        add_error(report, "operator_action_dashboard closure blocker mismatch")
    if closure.get("closed") is True:
        if str(closure.get("status", "")) != "closed":
            add_error(report, "operator_action_dashboard closure status mismatch")
        if status != "execution_completed":
            add_error(report, "operator_action_dashboard closure closed too early")
        if blockers:
            add_error(report, "operator_action_dashboard closure closed with blockers")
        if closure.get("approval_recorded") is not True:
            add_error(report, "operator_action_dashboard closure approval mismatch")
        if closure.get("execution_completed") is not True:
            add_error(report, "operator_action_dashboard closure execution mismatch")
        if closure.get("audit_chain_ok") is not True:
            add_error(report, "operator_action_dashboard closure audit mismatch")
        if completed_step_count != required_step_count:
            add_error(report, "operator_action_dashboard closure step mismatch")
    elif str(closure.get("status", "")) == "closed":
        add_error(report, "operator_action_dashboard closure closed flag mismatch")
    if closure.get("dashboard_consistency_checked") is not True:
        add_error(report, "operator_action_dashboard closure consistency missing")
    expected_artifacts = {
        "operator_action_plan",
        "operator_action_approval",
        "operator_action_execution_receipt",
        "operator_action_audit",
        "operator_action_dashboard",
    }
    observed_artifacts = {str(row.get("artifact_name", "")) for row in steps}
    if observed_artifacts != expected_artifacts:
        add_error(report, "operator_action_dashboard closure steps mismatch")
    policy = closure.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "operator_action_dashboard closure policy invalid")
        return
    for key in (
        "inspection_only",
        "does_not_execute_commands",
        "does_not_record_approval",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            add_error(report, f"operator_action_dashboard closure policy false: {key}")


def validate_recommended_command_hints(
    *,
    payload: dict[str, object],
    report: dict[str, object],
    artifact_label: str,
    allowed_writes: dict[str, object],
    unsafe_tokens: tuple[str, ...],
    commands_field: str = "recommended_commands",
    writes_field: str = "writes_artifact",
    command_noun: str = "recommended command",
    allowed_artifact_ids: dict[str, str] | None = None,
    artifact_id_field: str = "artifact_id",
    allow_empty: bool = False,
    current_step_field: str | None = None,
    current_step_error: str = "",
    required_label_errors: dict[str, str] | None = None,
    first_label: str = "",
    first_label_error: str = "",
    first_command: str = "",
    first_command_error: str = "",
) -> None:
    """Validate operator-facing command hints against deterministic boundaries."""
    commands = payload.get(commands_field, [])
    if not isinstance(commands, list) or not commands:
        if allow_empty and isinstance(commands, list):
            return
        add_error(report, f"{artifact_label} {commands_field} invalid")
        return

    first = commands[0]
    if first_label and (
        not isinstance(first, dict) or first.get("label") != first_label
    ):
        add_error(report, first_label_error)

    labels: set[str] = set()
    for index, row in enumerate(commands):
        if not isinstance(row, dict):
            add_error(report, f"{artifact_label} {command_noun} {index} invalid")
            continue
        label = str(row.get("label", ""))
        labels.add(label)
        command = str(row.get("command", ""))
        writes_artifact = row.get(writes_field, "")
        if label not in allowed_writes:
            add_error(report, f"{artifact_label} {command_noun} unknown: {label}")
        elif writes_artifact != allowed_writes[label]:
            add_error(
                report,
                f"{artifact_label} {command_noun} writes mismatch: {label}",
            )
        if allowed_artifact_ids is not None:
            expected_artifact_id = allowed_artifact_ids.get(label)
            actual_artifact_id = str(row.get(artifact_id_field, ""))
            if expected_artifact_id is None:
                add_error(
                    report,
                    f"{artifact_label} {command_noun} artifact unknown: {label}",
                )
            elif actual_artifact_id != expected_artifact_id:
                add_error(
                    report,
                    f"{artifact_label} {command_noun} artifact mismatch: {label}",
                )
        if "boundary" in row:
            expected_boundary = classify_operator_command(
                label=label,
                writes_artifact=str(writes_artifact),
            )
            if row.get("boundary") != expected_boundary:
                add_error(
                    report,
                    f"{artifact_label} {command_noun} boundary mismatch: {label}",
                )
        if not command.startswith("python -m orchestrator."):
            add_error(
                report,
                f"{artifact_label} {command_noun} prefix invalid: {label}",
            )
        for token in unsafe_tokens:
            if token in command:
                add_error(
                    report,
                    f"{artifact_label} {command_noun} unsafe token: {label}",
                )
                break

    if current_step_field:
        current_step = str(payload.get(current_step_field, ""))
        if current_step and current_step not in labels:
            add_error(report, current_step_error)

    for required_label, error in (required_label_errors or {}).items():
        if required_label not in labels:
            add_error(report, error)

    if (
        first_command
        and isinstance(first, dict)
        and str(first.get("command", "")) != first_command
    ):
        add_error(report, first_command_error)


def validate_optional_operator_unlock_checklist(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate operator_unlock_checklist.json/md when present."""
    path = run_dir / "operator_unlock_checklist.json"
    md_path = run_dir / "operator_unlock_checklist.md"
    if not path.exists() and not md_path.exists():
        return
    if not path.exists():
        add_error(report, f"missing operator unlock checklist JSON: {path}")
        return
    if not md_path.exists():
        add_error(report, f"missing operator unlock checklist markdown: {md_path}")
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/operator_unlock_checklist.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, "operator_unlock_checklist.json run_id mismatch")

    sources = payload.get("source_artifacts", {})
    if not isinstance(sources, dict):
        add_error(report, "operator_unlock_checklist source_artifacts invalid")
        sources = {}
    source = sources.get("codex_cli_execution_preflight", {})
    if not isinstance(source, dict):
        add_error(report, "operator_unlock_checklist preflight source invalid")
    else:
        source_file = source.get("file", {})
        if not isinstance(source_file, dict):
            add_error(report, "operator_unlock_checklist preflight file invalid")
        elif source_file.get("exists") is True:
            validate_recorded_file_hash(
                record=source_file,
                repo_root=repo_root,
                report=report,
                label="operator_unlock_checklist codex_cli_execution_preflight",
            )
            source_path = resolve_path(Path(str(source_file.get("path", ""))), repo_root)
            if source_path.name != "codex_cli_execution_preflight.json":
                add_error(report, "operator_unlock_checklist source path invalid")

    validate_operator_cockpit_unlock_checklist(
        payload={"codex_unlock_checklist": payload},
        report=report,
    )
    validate_codex_intake_readiness_artifact(
        payload=payload,
        report=report,
        label="operator_unlock_checklist",
    )
    validate_operator_unlock_navigation(
        payload=payload,
        repo_root=repo_root,
        report=report,
    )
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "operator_unlock_checklist policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_record_unlock_approval",
        "does_not_execute_codex_cli",
        "does_not_execute_agents",
        "does_not_create_workspace",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            add_error(report, f"operator_unlock_checklist policy false: {key}")


def validate_operator_unlock_navigation(
    *,
    payload: dict[str, Any],
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate read-only navigation fields in operator_unlock_checklist.json."""
    navigation = payload.get("navigation", {})
    if not isinstance(navigation, dict):
        add_error(report, "operator_unlock_checklist navigation invalid")
        return
    if navigation.get("schema_version") != "operator_unlock_navigation_v1":
        add_error(report, "operator_unlock_checklist navigation schema invalid")
    blocking_items = navigation.get("blocking_items", [])
    if not isinstance(blocking_items, list):
        add_error(report, "operator_unlock_checklist blocking_items invalid")
        blocking_items = []
    if navigation.get("blocking_count") != len(blocking_items):
        add_error(report, "operator_unlock_checklist blocking_count mismatch")
    if blocking_items and not navigation.get("primary_blocker"):
        add_error(report, "operator_unlock_checklist primary blocker missing")
    expected_artifacts = navigation.get("expected_artifacts", [])
    if not isinstance(expected_artifacts, list):
        add_error(report, "operator_unlock_checklist expected_artifacts invalid")
        expected_artifacts = []
    artifact_ids = set()
    for artifact in expected_artifacts:
        if not isinstance(artifact, dict):
            add_error(report, "operator_unlock_checklist artifact row invalid")
            continue
        artifact_id = str(artifact.get("artifact_id", ""))
        artifact_ids.add(artifact_id)
        json_file = artifact.get("json_file", {})
        if not isinstance(json_file, dict):
            add_error(report, "operator_unlock_checklist artifact file invalid")
        elif json_file.get("exists") is True:
            validate_recorded_file_hash(
                record=json_file,
                repo_root=repo_root,
                report=report,
                label=f"operator_unlock_checklist artifact {artifact_id}",
            )
        if artifact.get("required_for_real_codex_unlock") is not True:
            add_error(report, "operator_unlock_checklist artifact not required")
    for artifact_id in (
        "codex_cli_readiness_pipeline",
        "codex_cli_execution_candidate",
        "codex_cli_real_execution_dry_run",
        "codex_cli_operator_unlock_request",
        "codex_cli_execution_preflight",
    ):
        if artifact_id not in artifact_ids:
            add_error(
                report,
                f"operator_unlock_checklist navigation missing artifact: {artifact_id}",
            )
    commands = navigation.get("commands", [])
    if not isinstance(commands, list):
        add_error(report, "operator_unlock_checklist commands invalid")
        commands = []
    else:
        validate_operator_unlock_navigation_command_hints(
            navigation=navigation,
            report=report,
        )
    for command in commands:
        if not isinstance(command, dict):
            add_error(report, "operator_unlock_checklist command invalid")
            continue
        if command.get("executes_codex_cli") is not False:
            add_error(report, "operator_unlock_checklist command executes codex")
        if command.get("requires_explicit_operator_invocation") is not True:
            add_error(report, "operator_unlock_checklist command lacks explicit gate")
    nav_policy = navigation.get("policy", {})
    if not isinstance(nav_policy, dict):
        add_error(report, "operator_unlock_checklist navigation policy invalid")
        return
    for key in (
        "navigation_only",
        "commands_are_hints_only",
        "requires_explicit_operator_invocation",
        "does_not_execute_commands",
        "does_not_execute_codex_cli",
        "does_not_create_workspace",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_change_acceptance",
    ):
        if nav_policy.get(key) is not True:
            add_error(report, f"operator_unlock_checklist navigation policy false: {key}")


def validate_operator_unlock_navigation_command_hints(
    *,
    navigation: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate operator unlock navigation command hints are bounded."""
    allowed_artifact_ids = {
        "run_readiness_pipeline": "codex_cli_readiness_pipeline",
        "write_execution_candidate": "codex_cli_execution_candidate",
        "write_real_execution_dry_run": "codex_cli_real_execution_dry_run",
        "write_operator_unlock_request": "codex_cli_operator_unlock_request",
        "run_execution_preflight": "codex_cli_execution_preflight",
    }
    validate_recommended_command_hints(
        payload=navigation,
        report=report,
        artifact_label="operator_unlock_checklist",
        allowed_writes={label: True for label in allowed_artifact_ids},
        unsafe_tokens=("&&", "||", "|", "`", "$(", "\n", ";"),
        commands_field="commands",
        writes_field="writes_artifacts",
        command_noun="command",
        allowed_artifact_ids=allowed_artifact_ids,
        allow_empty=True,
    )


def validate_optional_operator_cockpit(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate operator_cockpit.json/md when present."""
    path = run_dir / "operator_cockpit.json"
    md_path = run_dir / "operator_cockpit.md"
    if not path.exists() and not md_path.exists():
        return
    if not path.exists():
        add_error(report, f"missing operator cockpit JSON: {path}")
        return
    if not md_path.exists():
        add_error(report, f"missing operator cockpit markdown: {md_path}")
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/operator_cockpit.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, "operator_cockpit.json run_id mismatch")

    sources = payload.get("source_artifacts", {})
    if not isinstance(sources, dict):
        add_error(report, "operator_cockpit.json source_artifacts invalid")
        sources = {}
    for source_key, expected_name in (
        ("run_closeout", "run_closeout.json"),
        ("config_lineage", "config_lineage.json"),
        ("operator_action_dashboard", "operator_action_dashboard.json"),
        ("codex_cli_execution_preflight", "codex_cli_execution_preflight.json"),
        (
            "codex_cli_execution_readiness_diff",
            "codex_cli_execution_readiness_diff.json",
        ),
        ("codex_cli_unlock_runbook", "codex_cli_unlock_runbook.json"),
        ("operator_unlock_checklist", "operator_unlock_checklist.json"),
        ("candidate_challenger_report", "candidate_challenger_report.json"),
        ("champion_promotion_dry_run", "champion_promotion_dry_run.json"),
        ("champion_promotion_approval", "champion_promotion_approval.json"),
        ("experiment_scope_health", "experiment_scope_health.json"),
    ):
        source = sources.get(source_key, {})
        if not isinstance(source, dict):
            add_error(report, f"operator_cockpit source invalid: {source_key}")
            continue
        source_file = source.get("file", {})
        if not isinstance(source_file, dict):
            add_error(report, f"operator_cockpit source file invalid: {source_key}")
            continue
        if source_file.get("exists") is True:
            validate_recorded_file_hash(
                record=source_file,
                repo_root=repo_root,
                report=report,
                label=f"operator_cockpit {source_key}",
            )
            source_path = resolve_path(Path(str(source_file.get("path", ""))), repo_root)
            if source_path.name != expected_name:
                add_error(report, f"operator_cockpit source path invalid: {source_key}")

    for row in list_of_dicts(payload.get("panels", [])):
        artifact_path = resolve_path(Path(str(row.get("artifact_path", ""))), repo_root)
        if bool(row.get("artifact_exists", False)) != artifact_path.exists():
            add_error(report, "operator_cockpit panel artifact existence mismatch")
    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        add_error(report, "operator_cockpit.json summary invalid")
        summary = {}
    if payload.get("ok") is not True:
        add_error(report, "operator_cockpit.json ok false")
    if summary.get("artifact_health_ok") is not True:
        add_error(report, "operator_cockpit.json artifact health not ok")
    if summary.get("codex_preflight_ok") is not True:
        add_error(report, "operator_cockpit.json codex preflight not ok")
    if not isinstance(summary.get("codex_preflight_status", ""), str):
        add_error(report, "operator_cockpit.json codex preflight status invalid")
    if not isinstance(summary.get("codex_readiness_diff_status", ""), str):
        add_error(report, "operator_cockpit.json codex readiness diff status invalid")
    if not isinstance(summary.get("codex_readiness_diff_ready", False), bool):
        add_error(report, "operator_cockpit.json codex readiness diff ready invalid")
    validate_codex_intake_readiness_artifact(
        payload=payload,
        report=report,
        label="operator_cockpit",
        summary=summary,
    )
    validate_operator_cockpit_unlock_checklist(payload=payload, report=report)
    validate_operator_cockpit_recommended_commands(
        payload=payload,
        run_id=str(report.get("run_id", "")),
        report=report,
    )
    validate_operator_cockpit_review_priority(payload=payload, report=report)

    authority = payload.get("authority", {})
    if not isinstance(authority, dict):
        add_error(report, "operator_cockpit.json authority invalid")
        authority = {}
    for key in (
        "cockpit_can_record_approval",
        "cockpit_can_execute_commands",
        "cockpit_can_write_config",
        "cockpit_can_promote_champion",
        "cockpit_can_change_acceptance",
    ):
        if authority.get(key) is not False:
            add_error(report, f"operator_cockpit authority true: {key}")

    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "operator_cockpit.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_record_approval",
        "does_not_execute_commands",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_write_config",
        "does_not_promote_champion",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            add_error(report, f"operator_cockpit.json policy false: {key}")


def validate_operator_cockpit_recommended_commands(
    *,
    payload: dict[str, object],
    run_id: str,
    report: dict[str, object],
) -> None:
    """Validate cockpit command hints stay within known review boundaries."""
    expected_first = f"python -m orchestrator.experiments cockpit {run_id} --markdown"
    validate_recommended_command_hints(
        payload=payload,
        report=report,
        artifact_label="operator_cockpit",
        allowed_writes={
            "review_cockpit": "",
            "review_run_dashboard": "",
            "review_run_diagnosis": "",
            "review_config_lineage": "config_lineage.json",
            "review_action_dashboard": "",
            "review_codex_cli_preflight": "codex_cli_execution_preflight.json",
            "review_codex_cli_unlock_runbook": "",
            "review_codex_cli_readiness_diff": "",
            "review_quality_trace": "candidate_quality_trace.json",
            "review_challenger_report": "candidate_challenger_report.json",
            "review_promotion_dry_run": "champion_promotion_dry_run.json",
            "write_action_dashboard": "operator_action_dashboard.json",
            "continue_operator_action": "",
            "review_promotion_approval": "champion_promotion_approval.json",
            "review_scope_health": "",
        },
        unsafe_tokens=("&&", "||", "|", ">", "<", "`", "$(", "\n", ";"),
        first_label="review_cockpit",
        first_label_error="operator_cockpit first recommended command invalid",
        first_command=expected_first,
        first_command_error="operator_cockpit review_cockpit command mismatch",
    )


def validate_operator_cockpit_review_priority(
    *,
    payload: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate cockpit review priority points to saved panel and command rows."""
    priority = payload.get("review_priority", {})
    if not isinstance(priority, dict):
        add_error(report, "operator_cockpit review_priority invalid")
        return

    panels = list_of_dicts(payload.get("panels", []))
    commands = list_of_dicts(payload.get("recommended_commands", []))

    target_panel_id = str(priority.get("target_panel_id", ""))
    target_panel = next(
        (row for row in panels if str(row.get("panel_id", "")) == target_panel_id),
        None,
    )
    if target_panel is None:
        add_error(report, "operator_cockpit review_priority target panel missing")
    else:
        for priority_key, panel_key, error in (
            (
                "target_panel_title",
                "title",
                "operator_cockpit review_priority target panel title mismatch",
            ),
            (
                "target_panel_status",
                "status",
                "operator_cockpit review_priority target panel status mismatch",
            ),
            (
                "target_artifact_path",
                "artifact_path",
                "operator_cockpit review_priority target artifact path mismatch",
            ),
            (
                "next_step",
                "next_step",
                "operator_cockpit review_priority next step mismatch",
            ),
        ):
            priority_value = str(priority.get(priority_key, ""))
            panel_value = str(target_panel.get(panel_key, ""))
            if priority_value != panel_value:
                add_error(report, error)
        if bool(priority.get("target_artifact_exists", False)) != bool(
            target_panel.get("artifact_exists", False)
        ):
            add_error(
                report,
                "operator_cockpit review_priority target artifact exists mismatch",
            )

    command_label = str(priority.get("recommended_command_label", ""))
    command = next(
        (row for row in commands if str(row.get("label", "")) == command_label),
        None,
    )
    if command is None:
        add_error(report, "operator_cockpit review_priority command label missing")
    else:
        for priority_key, command_key, error in (
            (
                "recommended_command",
                "command",
                "operator_cockpit review_priority command mismatch",
            ),
            (
                "recommended_command_writes_artifact",
                "writes_artifact",
                "operator_cockpit review_priority command write target mismatch",
            ),
            (
                "recommended_command_reason",
                "reason",
                "operator_cockpit review_priority command reason mismatch",
            ),
        ):
            priority_value = str(priority.get(priority_key, ""))
            command_value = str(command.get(command_key, ""))
            if priority_value != command_value:
                add_error(report, error)
        priority_boundary = priority.get("recommended_command_boundary", {})
        command_boundary = command.get("boundary", {})
        if priority_boundary != command_boundary:
            add_error(
                report,
                "operator_cockpit review_priority command boundary mismatch",
            )

    reason_codes = priority.get("reason_codes", [])
    if not isinstance(reason_codes, list) or not reason_codes:
        add_error(report, "operator_cockpit review_priority reason codes invalid")

    policy = priority.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "operator_cockpit review_priority policy invalid")
        return
    for key in (
        "inspection_only",
        "does_not_execute_commands",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            add_error(report, f"operator_cockpit review_priority policy false: {key}")


def validate_operator_cockpit_unlock_checklist(
    *,
    payload: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate the Codex unlock checklist embedded in operator_cockpit.json."""
    checklist = payload.get("codex_unlock_checklist", {})
    if not isinstance(checklist, dict):
        add_error(report, "operator_cockpit codex unlock checklist invalid")
        return
    items = checklist.get("items", [])
    if not isinstance(items, list):
        add_error(report, "operator_cockpit codex unlock checklist items invalid")
        items = []
    item_rows = [item for item in items if isinstance(item, dict)]
    if len(item_rows) != len(items):
        add_error(report, "operator_cockpit codex unlock checklist item invalid")
    passed_count = sum(1 for item in item_rows if item.get("status") == "passed")
    failed_count = sum(1 for item in item_rows if item.get("status") == "failed")
    if checklist.get("item_count") != len(item_rows):
        add_error(report, "operator_cockpit codex unlock checklist count mismatch")
    if checklist.get("passed_count") != passed_count:
        add_error(report, "operator_cockpit codex unlock checklist passed mismatch")
    if checklist.get("failed_count") != failed_count:
        add_error(report, "operator_cockpit codex unlock checklist failed mismatch")
    if bool(checklist.get("ready", False)) and failed_count:
        add_error(report, "operator_cockpit codex unlock checklist ready with failures")
    for item in item_rows:
        failed_checks = item.get("failed_checks", [])
        if not isinstance(failed_checks, list):
            add_error(report, "operator_cockpit codex unlock failed checks invalid")
            failed_checks = []
        if item.get("status") == "passed" and failed_checks:
            add_error(report, "operator_cockpit codex unlock passed item has failures")
        if item.get("status") == "failed" and not failed_checks:
            add_error(report, "operator_cockpit codex unlock failed item lacks failures")
        if item.get("required") is not True:
            add_error(report, "operator_cockpit codex unlock item not required")
    authority = checklist.get("authority", {})
    if not isinstance(authority, dict):
        add_error(report, "operator_cockpit codex unlock authority invalid")
        return
    for key in (
        "checklist_can_unlock_codex",
        "checklist_can_execute_codex",
        "checklist_can_create_workspace",
        "checklist_can_apply_patches",
        "checklist_can_change_acceptance",
    ):
        if authority.get(key) is not False:
            add_error(report, f"operator_cockpit codex unlock authority true: {key}")


def validate_codex_intake_readiness_artifact(
    *,
    payload: dict[str, object],
    report: dict[str, object],
    label: str,
    summary: dict[str, object] | None = None,
) -> None:
    """Validate a shared Codex intake-readiness block embedded in an artifact."""
    intake = payload.get("codex_intake_readiness", {})
    if not isinstance(intake, dict):
        add_error(report, f"{label} codex intake readiness invalid")
        return
    for error in validate_codex_cli_intake_readiness(intake):
        add_error(report, f"{label} {error}")
    if summary is None:
        return
    status_key = (
        "codex_intake_readiness_status"
        if "codex_intake_readiness_status" in summary
        else "intake_readiness_status"
    )
    ready_key = (
        "codex_intake_ready"
        if "codex_intake_ready" in summary
        else "intake_readiness_ready"
    )
    blocker_key = (
        "codex_intake_blocker_count"
        if "codex_intake_blocker_count" in summary
        else "intake_readiness_blocker_count"
    )
    if str(summary.get(status_key, "")) != str(
        intake.get("status", "")
    ):
        add_error(report, f"{label} codex intake status summary mismatch")
    if bool(summary.get(ready_key, False)) != bool(
        intake.get("ready", False)
    ):
        add_error(report, f"{label} codex intake ready summary mismatch")
    if int(summary.get(blocker_key, -1)) != int(
        intake.get("blocking_reason_count", 0) or 0
    ):
        add_error(report, f"{label} codex intake blocker summary mismatch")


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
    from orchestrator.champion_promotion_dry_run import (
        validate_champion_promotion_dry_run_consistency,
    )

    for error in validate_champion_promotion_dry_run_consistency(payload):
        add_error(report, error)
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
    from orchestrator.champion_promotion_approval import (
        validate_champion_promotion_approval_consistency,
    )

    for error in validate_champion_promotion_approval_consistency(payload):
        add_error(report, error)
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
    from orchestrator.champion_promotion_executor import (
        validate_champion_promotion_receipt_consistency,
    )

    for error in validate_champion_promotion_receipt_consistency(
        payload,
        verify_source_digests=False,
    ):
        add_error(report, error)
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


def validate_optional_config_application_receipt(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate config_application_receipt.json when a run has one."""
    path = run_dir / "config_application_receipt.json"
    md_path = run_dir / "config_application_receipt.md"
    if not path.exists():
        if md_path.exists():
            add_error(report, "config_application_receipt.md exists without JSON")
        return
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    else:
        add_error(report, "config_application_receipt.json missing markdown pair")
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/config_application_receipt.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"config_application_receipt.json run_id does not match report: {path}",
        )
    if payload.get("status") == "applied" and payload.get("applied") is not True:
        add_error(report, "config_application_receipt.json applied status mismatch")
    if payload.get("status") == "blocked" and payload.get("applied") is not False:
        add_error(report, "config_application_receipt.json blocked status mismatch")
    dry_run_path = resolve_path(
        Path(str(payload.get("source_dry_run_path", ""))),
        repo_root,
    )
    if payload.get("source_dry_run_sha256") != file_sha256(dry_run_path):
        add_error(report, "config_application_receipt.json dry-run digest mismatch")
    review_path = resolve_path(
        Path(str(payload.get("source_operator_review_path", ""))),
        repo_root,
    )
    if payload.get("source_operator_review_sha256") != file_sha256(review_path):
        add_error(report, "config_application_receipt.json review digest mismatch")
    config_path = resolve_path(Path(str(payload.get("config_path", ""))), repo_root)
    if payload.get("config_after_sha256") != file_sha256(
        config_path,
    ) and not has_restored_config_application(
        run_dir=run_dir,
        receipt_path=path,
        repo_root=repo_root,
    ):
        add_error(report, "config_application_receipt.json config digest mismatch")
    checks = payload.get("evidence_checks", {})
    if not isinstance(checks, dict):
        add_error(report, "config_application_receipt.json evidence invalid")
    else:
        blockers = checks.get("blockers", [])
        if payload.get("applied") is True and blockers:
            add_error(report, "config_application_receipt.json applied with blockers")
        if payload.get("applied") is True and checks.get("ok") is not True:
            add_error(report, "config_application_receipt.json applied without evidence")
    applied_changes = payload.get("applied_changes", [])
    if not isinstance(applied_changes, list):
        add_error(report, "config_application_receipt.json applied_changes invalid")
    elif payload.get("applied") is True and not applied_changes:
        add_error(report, "config_application_receipt.json applied without changes")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "config_application_receipt.json policy invalid")
        return
    for key in (
        "requires_config_application_dry_run",
        "requires_dry_run_ready",
        "requires_source_dry_run_digest_match",
        "requires_operator_review_digest_match",
        "requires_current_config_digest_match",
        "writes_only_config",
        "does_not_delete_memory",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_route_candidates",
        "does_not_apply_patches",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            add_error(report, f"config_application_receipt.json policy false: {key}")


def validate_optional_config_application_rollback_preview(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate config_application_rollback_preview.json when present."""
    path = run_dir / "config_application_rollback_preview.json"
    md_path = run_dir / "config_application_rollback_preview.md"
    if not path.exists():
        if md_path.exists():
            add_error(
                report,
                "config_application_rollback_preview.md exists without JSON",
            )
        return
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    else:
        add_error(
            report,
            "config_application_rollback_preview.json missing markdown pair",
        )
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root
        / "schemas/config_application_rollback_preview.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            "config_application_rollback_preview.json run_id does not match report",
        )
    receipt_path = resolve_path(
        Path(str(payload.get("source_receipt_path", ""))),
        repo_root,
    )
    if payload.get("source_receipt_sha256") != file_sha256(receipt_path):
        add_error(
            report,
            "config_application_rollback_preview.json receipt digest mismatch",
        )
    config_path = resolve_path(Path(str(payload.get("config_path", ""))), repo_root)
    if payload.get("current_config_sha256") != file_sha256(
        config_path,
    ) and not has_config_restore_from_preview(
        run_dir=run_dir,
        preview_path=path,
        repo_root=repo_root,
    ):
        add_error(
            report,
            "config_application_rollback_preview.json config digest mismatch",
        )
    gate = payload.get("rollback_gate", {})
    if not isinstance(gate, dict):
        add_error(report, "config_application_rollback_preview.json gate invalid")
    else:
        eligible = gate.get("eligible_for_manual_restore") is True
        blockers = gate.get("blockers", [])
        status = payload.get("status")
        if status == "rollback_ready" and not eligible:
            add_error(
                report,
                "config_application_rollback_preview.json ready status mismatch",
            )
        if status == "rollback_ready" and blockers:
            add_error(
                report,
                "config_application_rollback_preview.json ready with blockers",
            )
        if status == "no_applied_config_change" and payload.get(
            "source_receipt_applied",
        ):
            add_error(
                report,
                "config_application_rollback_preview.json no-change status mismatch",
            )
    rollback_plan = payload.get("rollback_plan", [])
    if not isinstance(rollback_plan, list):
        add_error(report, "config_application_rollback_preview.json plan invalid")
    elif payload.get("status") == "rollback_ready" and not rollback_plan:
        add_error(report, "config_application_rollback_preview.json ready without plan")
    impact = payload.get("next_run_impact", {})
    if not isinstance(impact, dict):
        add_error(report, "config_application_rollback_preview.json impact invalid")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "config_application_rollback_preview.json policy invalid")
        return
    for key in (
        "requires_config_application_receipt",
        "read_only",
        "does_not_write_config",
        "does_not_delete_memory",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_route_candidates",
        "does_not_apply_patches",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            add_error(
                report,
                f"config_application_rollback_preview.json policy false: {key}",
            )


def validate_optional_config_application_restore_receipt(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate config_application_restore_receipt.json when present."""
    path = run_dir / "config_application_restore_receipt.json"
    md_path = run_dir / "config_application_restore_receipt.md"
    if not path.exists():
        if md_path.exists():
            add_error(
                report,
                "config_application_restore_receipt.md exists without JSON",
            )
        return
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    else:
        add_error(
            report,
            "config_application_restore_receipt.json missing markdown pair",
        )
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root
        / "schemas/config_application_restore_receipt.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            "config_application_restore_receipt.json run_id does not match report",
        )
    if payload.get("status") == "restored" and payload.get("restored") is not True:
        add_error(report, "config_application_restore_receipt.json status mismatch")
    if payload.get("status") == "blocked" and payload.get("restored") is not False:
        add_error(report, "config_application_restore_receipt.json blocked mismatch")
    preview_path = resolve_path(
        Path(str(payload.get("source_preview_path", ""))),
        repo_root,
    )
    if payload.get("source_preview_sha256") != file_sha256(preview_path):
        add_error(
            report,
            "config_application_restore_receipt.json preview digest mismatch",
        )
    receipt_path = resolve_path(
        Path(str(payload.get("source_receipt_path", ""))),
        repo_root,
    )
    if payload.get("source_receipt_sha256") != file_sha256(receipt_path):
        add_error(
            report,
            "config_application_restore_receipt.json receipt digest mismatch",
        )
    config_path = resolve_path(Path(str(payload.get("config_path", ""))), repo_root)
    if payload.get("config_after_sha256") != file_sha256(config_path):
        add_error(
            report,
            "config_application_restore_receipt.json config digest mismatch",
        )
    gate = payload.get("restore_gate", {})
    if not isinstance(gate, dict):
        add_error(report, "config_application_restore_receipt.json gate invalid")
    else:
        blockers = gate.get("blockers", [])
        if payload.get("restored") is True and blockers:
            add_error(report, "config_application_restore_receipt.json restored blocked")
        if payload.get("restored") is True and gate.get("ok") is not True:
            add_error(
                report,
                "config_application_restore_receipt.json restored without evidence",
            )
    restored_changes = payload.get("restored_changes", [])
    if not isinstance(restored_changes, list):
        add_error(report, "config_application_restore_receipt.json changes invalid")
    elif payload.get("restored") is True and not restored_changes:
        add_error(report, "config_application_restore_receipt.json restored no changes")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "config_application_restore_receipt.json policy invalid")
        return
    for key in (
        "requires_config_application_rollback_preview",
        "requires_preview_ready",
        "requires_preview_digest_match",
        "requires_source_receipt_digest_match",
        "requires_current_config_digest_match",
        "writes_only_config",
        "does_not_delete_memory",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_route_candidates",
        "does_not_apply_patches",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            add_error(
                report,
                f"config_application_restore_receipt.json policy false: {key}",
            )


def validate_optional_config_operator_runbook(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate config_operator_runbook.json when present."""
    path = run_dir / "config_operator_runbook.json"
    md_path = run_dir / "config_operator_runbook.md"
    if not path.exists():
        if md_path.exists():
            add_error(report, "config_operator_runbook.md exists without JSON")
        return
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    else:
        add_error(report, "config_operator_runbook.json missing markdown pair")
    # Coverage marker: schemas/config_operator_runbook.schema.json is checked
    # by validate_config_operator_runbook_file().
    from orchestrator.config_operator_runbook import (
        validate_config_operator_runbook_file,
    )

    for error in validate_config_operator_runbook_file(
        payload_path=path,
        repo_root=repo_root,
    ):
        add_error(report, error)
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, "config_operator_runbook.json run_id mismatch")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "config_operator_runbook.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "runbook_only",
        "does_not_execute_commands",
        "does_not_record_operator_review",
        "does_not_write_config",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_route_candidates",
        "does_not_apply_patches",
        "does_not_change_acceptance",
        "commands_require_explicit_operator_invocation",
    ):
        if policy.get(key) is not True:
            add_error(report, f"config_operator_runbook.json policy false: {key}")


def has_restored_config_application(
    *,
    run_dir: Path,
    receipt_path: Path,
    repo_root: Path,
) -> bool:
    """Return true when a restore receipt explains the current config drift."""
    restore_path = run_dir / "config_application_restore_receipt.json"
    if not restore_path.exists():
        return False
    payload = load_optional_json_object(restore_path)
    if payload.get("restored") is not True:
        return False
    source_receipt = resolve_path(
        Path(str(payload.get("source_receipt_path", ""))),
        repo_root,
    )
    return source_receipt.resolve() == receipt_path.resolve()


def has_config_restore_from_preview(
    *,
    run_dir: Path,
    preview_path: Path,
    repo_root: Path,
) -> bool:
    """Return true when a restore receipt explains preview config drift."""
    restore_path = run_dir / "config_application_restore_receipt.json"
    if not restore_path.exists():
        return False
    payload = load_optional_json_object(restore_path)
    if payload.get("restored") is not True:
        return False
    source_preview = resolve_path(
        Path(str(payload.get("source_preview_path", ""))),
        repo_root,
    )
    return source_preview.resolve() == preview_path.resolve()


def load_optional_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object for optional cross-artifact checks."""
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def validate_optional_config_lineage(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate config_lineage.json when present."""
    path = run_dir / "config_lineage.json"
    md_path = run_dir / "config_lineage.md"
    if not path.exists():
        if md_path.exists():
            add_error(report, "config_lineage.md exists without JSON")
        return
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    else:
        add_error(report, "config_lineage.json missing markdown pair")
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/config_lineage.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, "config_lineage.json run_id does not match report")
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        add_error(report, "config_lineage.json checks invalid")
    else:
        if payload.get("ok") != checks.get("ok"):
            add_error(report, "config_lineage.json ok mismatch")
        if checks.get("stage_count") != 6:
            add_error(report, "config_lineage.json stage_count mismatch")
        current_config = payload.get("current_config", {})
        current_config_path = repo_root / "config/default.json"
        if isinstance(current_config, dict):
            current_config_path = resolve_path(
                Path(str(current_config.get("path", ""))),
                repo_root,
            )
        if checks.get("current_config_sha256") != file_sha256(current_config_path):
            add_error(report, "config_lineage.json current config digest mismatch")
    stages = payload.get("stages", [])
    if not isinstance(stages, list):
        add_error(report, "config_lineage.json stages invalid")
    elif len(stages) != 6:
        add_error(report, "config_lineage.json stages length mismatch")
    else:
        for row in stages:
            if not isinstance(row, dict):
                add_error(report, "config_lineage.json stage row invalid")
                continue
            artifact_path = resolve_path(
                Path(str(row.get("artifact_path", ""))),
                repo_root,
            )
            if row.get("exists") is True:
                if not artifact_path.exists():
                    add_error(report, "config_lineage.json stage artifact missing")
                elif row.get("sha256") != file_sha256(artifact_path):
                    add_error(report, "config_lineage.json stage digest mismatch")
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "config_lineage.json policy invalid")
        return
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_write_config",
        "does_not_delete_memory",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_route_candidates",
        "does_not_apply_patches",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            add_error(report, f"config_lineage.json policy false: {key}")


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
            "requires_intake_binding",
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
            "requires_canary_intake_binding",
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
    consistency = payload.get("consistency_checks", {})
    if not isinstance(consistency, dict):
        add_error(report, "codex_cli_readiness_summary.json consistency invalid")
    else:
        consistency_blockers = consistency.get("blocking_reasons", [])
        if not isinstance(consistency_blockers, list):
            add_error(
                report,
                "codex_cli_readiness_summary.json consistency blockers invalid",
            )
        elif consistency_blockers:
            add_error(report, "codex_cli_readiness_summary.json consistency failed")
        checks = consistency.get("checks", {})
        if not isinstance(checks, dict):
            add_error(
                report,
                "codex_cli_readiness_summary.json consistency checks invalid",
            )
        elif any(not bool(passed) for passed in checks.values()):
            add_error(report, "codex_cli_readiness_summary.json consistency check false")
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


def validate_optional_codex_cli_unlock_runbook(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate codex_cli_unlock_runbook.json when a run has one."""
    path = run_dir / "codex_cli_unlock_runbook.json"
    if not path.exists():
        return
    md_path = run_dir / "codex_cli_unlock_runbook.md"
    checked_files(report).append(str(path))
    if not md_path.exists():
        add_error(report, f"missing Codex CLI unlock runbook markdown: {md_path}")
    else:
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/codex_cli_unlock_runbook.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, "codex_cli_unlock_runbook.json run_id mismatch")
    if not artifact_path_matches_run_dir(
        path_text=str(payload.get("run_dir", "")),
        run_dir=run_dir,
        repo_root=repo_root,
    ):
        add_error(report, "codex_cli_unlock_runbook.json run_dir mismatch")
    steps = payload.get("steps", [])
    if not isinstance(steps, list) or len(steps) != 5:
        add_error(report, "codex_cli_unlock_runbook.json steps invalid")
        steps = []
    expected_artifact_ids = [
        "codex_cli_execution_preflight",
        "codex_cli_readiness_pipeline",
        "codex_cli_execution_candidate",
        "codex_cli_real_execution_dry_run",
        "codex_cli_operator_unlock_request",
    ]
    observed_artifact_ids = [
        str(step.get("artifact_id", "")) for step in steps if isinstance(step, dict)
    ]
    if observed_artifact_ids != expected_artifact_ids:
        add_error(report, "codex_cli_unlock_runbook.json step order invalid")
    ready_count = 0
    missing_count = 0
    blocked_count = 0
    for step in steps:
        if not isinstance(step, dict):
            add_error(report, "codex_cli_unlock_runbook.json step row invalid")
            continue
        status = str(step.get("status", ""))
        ready = bool(step.get("ready", False))
        if status == "ready":
            ready_count += 1
            if not ready:
                add_error(report, "codex_cli_unlock_runbook.json ready step false")
        elif status == "missing":
            missing_count += 1
        elif status == "blocked":
            blocked_count += 1
        else:
            add_error(report, f"codex_cli_unlock_runbook.json step status invalid: {status}")
        artifact = step.get("artifact", {})
        if not isinstance(artifact, dict):
            add_error(report, "codex_cli_unlock_runbook.json step artifact invalid")
        else:
            json_file = artifact.get("json_file", {})
            if isinstance(json_file, dict) and json_file.get("exists") is True:
                validate_recorded_file_hash(
                    record=json_file,
                    repo_root=repo_root,
                    report=report,
                    label=(
                        "codex_cli_unlock_runbook "
                        f"{step.get('artifact_id', '')}"
                    ),
                )
        command = step.get("command", {})
        if not isinstance(command, dict):
            add_error(report, "codex_cli_unlock_runbook.json command invalid")
        else:
            if bool(command.get("executes_codex_cli", True)):
                add_error(report, "codex_cli_unlock_runbook.json command executes Codex")
            if not bool(command.get("requires_explicit_operator_invocation", False)):
                add_error(
                    report,
                    "codex_cli_unlock_runbook.json command lacks explicit operator gate",
                )
        authority = step.get("authority", {})
        if not isinstance(authority, dict):
            add_error(report, "codex_cli_unlock_runbook.json authority invalid")
        else:
            for key in (
                "step_can_execute_command",
                "step_can_execute_codex_cli",
                "step_can_create_workspace",
                "step_can_apply_patches",
                "step_can_change_acceptance",
            ):
                if bool(authority.get(key, True)):
                    add_error(
                        report,
                        f"codex_cli_unlock_runbook.json authority true: {key}",
                    )
    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        add_error(report, "codex_cli_unlock_runbook.json summary invalid")
    else:
        if int(summary.get("step_count", -1)) != len(steps):
            add_error(report, "codex_cli_unlock_runbook.json step count mismatch")
        if int(summary.get("ready_step_count", -1)) != ready_count:
            add_error(report, "codex_cli_unlock_runbook.json ready count mismatch")
        if int(summary.get("missing_step_count", -1)) != missing_count:
            add_error(report, "codex_cli_unlock_runbook.json missing count mismatch")
        if int(summary.get("blocked_step_count", -1)) != blocked_count:
            add_error(report, "codex_cli_unlock_runbook.json blocked count mismatch")
        validate_codex_intake_readiness_artifact(
            payload=payload,
            report=report,
            label="codex_cli_unlock_runbook.json",
            summary=summary,
        )
    source = payload.get("source_checklist", {})
    if not isinstance(source, dict):
        add_error(report, "codex_cli_unlock_runbook.json source checklist invalid")
    else:
        source_file = source.get("file", {})
        if isinstance(source_file, dict) and source_file.get("exists") is True:
            validate_recorded_file_hash(
                record=source_file,
                repo_root=repo_root,
                report=report,
                label="codex_cli_unlock_runbook source_checklist",
            )
    commands = payload.get("operator_commands", [])
    if not isinstance(commands, list):
        add_error(report, "codex_cli_unlock_runbook.json commands invalid")
    else:
        validate_codex_cli_unlock_runbook_operator_commands(
            payload=payload,
            report=report,
        )
        if len(commands) != len(steps):
            add_error(report, "codex_cli_unlock_runbook.json command count mismatch")
        for command in commands:
            if not isinstance(command, dict):
                add_error(report, "codex_cli_unlock_runbook.json command row invalid")
                continue
            if bool(command.get("executes_codex_cli", True)):
                add_error(
                    report,
                    "codex_cli_unlock_runbook.json operator command executes Codex",
                )
            if not bool(command.get("requires_explicit_operator_invocation", False)):
                add_error(
                    report,
                    "codex_cli_unlock_runbook.json operator command lacks explicit gate",
                )
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "codex_cli_unlock_runbook.json policy invalid")
    else:
        for key in (
            "inspection_only",
            "reads_saved_artifacts_only",
            "runbook_only",
            "does_not_execute_commands",
            "does_not_execute_codex_cli",
            "does_not_record_operator_approval",
            "does_not_create_workspace",
            "does_not_send_strategy_prompt",
            "does_not_apply_patches",
            "does_not_route_agents",
            "does_not_change_acceptance",
            "commands_require_explicit_operator_invocation",
        ):
            if not bool(policy.get(key, False)):
                add_error(
                    report,
                    f"codex_cli_unlock_runbook.json policy false: {key}",
                )


def codex_cli_unlock_runbook_command_artifacts() -> dict[str, str]:
    """Return expected command-label to artifact-id bindings for the runbook."""
    return {
        "run_execution_preflight": "codex_cli_execution_preflight",
        "run_readiness_pipeline": "codex_cli_readiness_pipeline",
        "write_execution_candidate": "codex_cli_execution_candidate",
        "write_real_execution_dry_run": "codex_cli_real_execution_dry_run",
        "write_operator_unlock_request": "codex_cli_operator_unlock_request",
    }


def validate_codex_cli_unlock_runbook_operator_commands(
    *,
    payload: dict[str, object],
    report: dict[str, object],
) -> None:
    """Validate Codex unlock runbook command hints are bounded."""
    allowed_artifact_ids = codex_cli_unlock_runbook_command_artifacts()
    validate_recommended_command_hints(
        payload=payload,
        report=report,
        artifact_label="codex_cli_unlock_runbook",
        allowed_writes={label: True for label in allowed_artifact_ids},
        unsafe_tokens=("&&", "||", "|", "`", "$(", "\n", ";"),
        commands_field="operator_commands",
        writes_field="writes_artifacts",
        command_noun="operator command",
    )
    for index, step in enumerate(list_of_dicts(payload.get("steps", []))):
        command = step.get("command", {})
        if not isinstance(command, dict):
            continue
        label = str(command.get("label", ""))
        expected_artifact_id = allowed_artifact_ids.get(label, "")
        if not expected_artifact_id:
            add_error(
                report,
                f"codex_cli_unlock_runbook.json step command unknown: {label}",
            )
        elif str(step.get("artifact_id", "")) != expected_artifact_id:
            add_error(
                report,
                "codex_cli_unlock_runbook.json step command artifact mismatch: "
                f"{index}",
            )


def validate_optional_codex_cli_execution_readiness_diff(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate codex_cli_execution_readiness_diff.json when present."""
    path = run_dir / "codex_cli_execution_readiness_diff.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    md_path = run_dir / "codex_cli_execution_readiness_diff.md"
    if md_path.exists():
        checked_files(report).append(str(md_path))
    else:
        add_error(report, "codex_cli_execution_readiness_diff.md missing")
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root
        / "schemas/codex_cli_execution_readiness_diff.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, "codex_cli_execution_readiness_diff.json run_id mismatch")
    if not artifact_path_matches_run_dir(
        path_text=str(payload.get("run_dir", "")),
        run_dir=run_dir,
        repo_root=repo_root,
    ):
        add_error(report, "codex_cli_execution_readiness_diff.json run_dir mismatch")
    status = str(payload.get("status", ""))
    ready = bool(payload.get("ready", False))
    if ready and status != "ready":
        add_error(report, "codex_cli_execution_readiness_diff.json ready/status mismatch")
    if status == "ready" and not ready:
        add_error(report, "codex_cli_execution_readiness_diff.json status ready false")
    if status not in {"missing_evidence", "drift_detected", "blocked", "ready"}:
        add_error(report, "codex_cli_execution_readiness_diff.json status invalid")
    sources = payload.get("source_artifacts", {})
    missing_artifacts: list[str] = []
    if not isinstance(sources, dict):
        add_error(report, "codex_cli_execution_readiness_diff.json sources invalid")
    else:
        for artifact_id, artifact in sources.items():
            if not isinstance(artifact, dict):
                add_error(
                    report,
                    "codex_cli_execution_readiness_diff.json source row invalid",
                )
                continue
            source_file = artifact.get("file", {})
            if not isinstance(source_file, dict):
                add_error(
                    report,
                    "codex_cli_execution_readiness_diff.json source file invalid",
                )
                continue
            if source_file.get("exists") is True:
                validate_recorded_file_hash(
                    record=source_file,
                    repo_root=repo_root,
                    report=report,
                    label=(
                        "codex_cli_execution_readiness_diff "
                        f"{artifact_id}"
                    ),
                )
            elif bool(artifact.get("required_for_ready_diff", False)):
                missing_artifacts.append(str(artifact_id))
    comparisons = payload.get("comparisons", [])
    matched_count = 0
    drift_count = 0
    missing_count = 0
    drift_ids: list[str] = []
    missing_ids: list[str] = []
    if not isinstance(comparisons, list):
        add_error(report, "codex_cli_execution_readiness_diff.json comparisons invalid")
        comparisons = []
    for comparison in comparisons:
        if not isinstance(comparison, dict):
            add_error(
                report,
                "codex_cli_execution_readiness_diff.json comparison row invalid",
            )
            continue
        row_status = str(comparison.get("status", ""))
        comparison_id = str(comparison.get("comparison_id", ""))
        if row_status == "matched":
            matched_count += 1
        elif row_status == "drift":
            drift_count += 1
            drift_ids.append(comparison_id)
        elif row_status == "missing":
            missing_count += 1
            missing_ids.append(comparison_id)
        else:
            add_error(
                report,
                "codex_cli_execution_readiness_diff.json comparison status invalid",
            )
        missing_sides = comparison.get("missing_sides", [])
        if row_status == "missing" and not missing_sides:
            add_error(
                report,
                "codex_cli_execution_readiness_diff.json missing row lacks side",
            )
        if row_status != "missing" and missing_sides:
            add_error(
                report,
                "codex_cli_execution_readiness_diff.json non-missing row has side",
            )
    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        add_error(report, "codex_cli_execution_readiness_diff.json summary invalid")
    else:
        if int(summary.get("comparison_count", -1)) != len(comparisons):
            add_error(
                report,
                "codex_cli_execution_readiness_diff.json comparison count mismatch",
            )
        if int(summary.get("matched_count", -1)) != matched_count:
            add_error(
                report,
                "codex_cli_execution_readiness_diff.json matched count mismatch",
            )
        if int(summary.get("drift_count", -1)) != drift_count:
            add_error(
                report,
                "codex_cli_execution_readiness_diff.json drift count mismatch",
            )
        if int(summary.get("missing_comparison_count", -1)) != missing_count:
            add_error(
                report,
                "codex_cli_execution_readiness_diff.json missing count mismatch",
            )
        if int(summary.get("missing_artifact_count", -1)) != len(missing_artifacts):
            add_error(
                report,
                "codex_cli_execution_readiness_diff.json missing artifact mismatch",
            )
        if sorted(string_list(summary.get("missing_artifacts", []))) != sorted(
            missing_artifacts
        ):
            add_error(
                report,
                "codex_cli_execution_readiness_diff.json missing artifact list mismatch",
            )
        if sorted(string_list(summary.get("drift_comparisons", []))) != sorted(
            drift_ids
        ):
            add_error(
                report,
                "codex_cli_execution_readiness_diff.json drift list mismatch",
            )
        if sorted(string_list(summary.get("missing_comparisons", []))) != sorted(
            missing_ids
        ):
            add_error(
                report,
                "codex_cli_execution_readiness_diff.json missing list mismatch",
            )
        validate_codex_intake_readiness_artifact(
            payload=payload,
            report=report,
            label="codex_cli_execution_readiness_diff.json",
            summary=summary,
        )
    blockers = payload.get("blocking_reasons", [])
    if not isinstance(blockers, list):
        add_error(report, "codex_cli_execution_readiness_diff.json blockers invalid")
    elif status == "ready" and blockers:
        add_error(report, "codex_cli_execution_readiness_diff.json ready with blockers")
    elif status != "ready" and not blockers:
        add_error(
            report,
            "codex_cli_execution_readiness_diff.json blocked without blockers",
        )
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        add_error(report, "codex_cli_execution_readiness_diff.json policy invalid")
    else:
        for key in (
            "inspection_only",
            "read_only",
            "diff_only",
            "does_not_execute_commands",
            "does_not_execute_codex_cli",
            "does_not_record_operator_approval",
            "does_not_create_workspace",
            "does_not_send_strategy_prompt",
            "does_not_modify_config",
            "does_not_apply_patches",
            "does_not_route_agents",
            "does_not_change_acceptance",
            "startup_preflight_keeps_execution_authority",
        ):
            if not bool(policy.get(key, False)):
                add_error(
                    report,
                    f"codex_cli_execution_readiness_diff.json policy false: {key}",
                )


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


def load_json_list(path: Path) -> list[Any]:
    """Load a JSON list artifact without mutating the validation report."""
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return payload if isinstance(payload, list) else []


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


def read_optional_text(path: Path) -> str:
    """Read optional UTF-8 text and return an empty string when absent."""
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError):
        return ""


def object_value(value: object) -> dict[str, object]:
    """Return a JSON object value or an empty object."""
    return value if isinstance(value, dict) else {}


def list_value(value: object) -> list[object]:
    """Return a JSON list value or an empty list."""
    return list(value) if isinstance(value, list | tuple) else []


def list_of_dicts(value: object) -> list[dict[str, object]]:
    """Return only object rows from a JSON list-like value."""
    if not isinstance(value, list | tuple):
        return []
    return [row for row in value if isinstance(row, dict)]


def string_list(value: object) -> list[str]:
    """Return string rows from a JSON list-like value."""
    if not isinstance(value, list | tuple):
        return []
    return [str(row) for row in value]


def reason_code_rows(value: object) -> list[dict[str, str]]:
    """Return valid reason-code rows from a JSON list-like value."""
    rows: list[dict[str, str]] = []
    if not isinstance(value, list | tuple):
        return rows
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append({
            "stage": str(item.get("stage", "")),
            "code": str(item.get("code", "")),
            "message": str(item.get("message", "")),
        })
    return rows


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
