"""Inspect experiment history and artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from orchestrator.agent_result_stats import build_agent_result_stats
from orchestrator.agent_slot_readiness_gate import build_agent_slot_readiness_gate
from orchestrator.agent_slot_health import build_agent_slot_health
from orchestrator.artifact_validator_coverage import build_artifact_validator_coverage
from orchestrator.candidate_quality_trace import (
    build_candidate_quality_trace,
    validate_candidate_quality_trace_payload,
)
from orchestrator.config_change_candidate import (
    build_config_change_candidate,
    validate_config_change_candidate_payload,
)
from orchestrator.experiment_index import read_experiment_index, recent_experiments
from orchestrator.external_agent_sandbox_drill import (
    build_external_agent_sandbox_drill,
)
from orchestrator.experiment_scope_health import build_experiment_scope_health
from orchestrator.config_application_dry_run import (
    build_config_application_dry_run,
    validate_config_application_dry_run_payload,
)
from orchestrator.config_operator_runbook import (
    build_config_operator_runbook,
    render_config_operator_runbook_markdown,
    validate_config_operator_runbook_payload,
)
from orchestrator.memory_diagnostics import (
    build_memory_diagnostics,
    validate_memory_diagnostics_payload,
)
from orchestrator.memory_hygiene import (
    build_memory_hygiene,
    validate_memory_hygiene_payload,
)
from orchestrator.memory_scope_recommendation import (
    build_memory_scope_recommendation,
    validate_memory_scope_recommendation_payload,
)
from orchestrator.modifier_profile_recommendation import (
    build_modifier_profile_recommendation,
    render_modifier_profile_recommendation_markdown,
    validate_modifier_profile_recommendation_payload,
)
from orchestrator.operator_action_approval import (
    build_operator_action_approval,
    render_operator_action_approval_markdown,
    validate_operator_action_approval_payload,
)
from orchestrator.operator_action_audit import (
    build_operator_action_audit,
    render_operator_action_audit_markdown,
    validate_operator_action_audit_payload,
)
from orchestrator.operator_action_dashboard import (
    build_operator_action_dashboard,
    render_operator_action_dashboard_markdown,
    validate_operator_action_dashboard_payload,
    write_operator_action_dashboard,
)
from orchestrator.operator_action_guide import (
    build_operator_action_guide,
    render_operator_action_guide_markdown,
    validate_operator_action_guide_payload,
)
from orchestrator.operator_cockpit import (
    annotate_snapshot_freshness,
    build_operator_cockpit,
    render_operator_cockpit_markdown,
    validate_operator_cockpit_payload,
    write_operator_cockpit,
)
from orchestrator.operator_home import (
    build_operator_home,
    render_operator_home_markdown,
    validate_operator_home_payload,
)
from orchestrator.operator_unlock_checklist import (
    build_operator_unlock_checklist,
    render_operator_unlock_checklist_markdown,
    validate_operator_unlock_checklist_payload,
    write_operator_unlock_checklist,
)
from orchestrator.codex_cli_unlock_runbook import (
    build_codex_cli_unlock_runbook,
    render_codex_cli_unlock_runbook_markdown,
    validate_codex_cli_unlock_runbook_payload,
    write_codex_cli_unlock_runbook,
)
from orchestrator.codex_cli_execution_readiness_diff import (
    build_codex_cli_execution_readiness_diff,
    render_codex_cli_execution_readiness_diff_markdown,
    validate_codex_cli_execution_readiness_diff_payload,
    write_codex_cli_execution_readiness_diff,
)
from orchestrator.codex_cli_execution_preflight import (
    write_codex_cli_execution_preflight,
)
from orchestrator.config import load_project_config
from orchestrator.operator_action_executor import (
    render_receipt_markdown as render_operator_action_execution_markdown,
    validate_operator_action_execution_receipt_payload,
)
from orchestrator.operator_action_plan import (
    build_operator_action_plan,
    render_operator_action_plan_markdown,
    validate_operator_action_plan_payload,
)
from orchestrator.operator_config_review import (
    build_operator_config_review,
    validate_operator_config_review_payload,
)
from orchestrator.outcome_memory import read_outcome_memory, recent_outcomes
from orchestrator.run_artifact_health import (
    DEFAULT_HISTORY_FILENAME,
    build_run_artifact_health,
    build_run_artifact_health_history,
)
from orchestrator.run_closeout import build_run_closeout
from orchestrator.run_diagnosis import diagnose_run
from orchestrator.schema_validation import load_schema, validate_json_payload


CHAMPION_SCHEMA_VERSION = "champion_v1"
CHAMPION_STATUS_SCHEMA_VERSION = "champion_status_v1"
SUMMARY_DASHBOARD_SCHEMA_VERSION = "experiment_summary_dashboard_v1"
SUMMARY_DASHBOARD_RECENT_LIMIT = 5
OPERATOR_VIEW_REFRESH_SCHEMA_PATH = Path("schemas/operator_view_refresh.schema.json")
CHAMPION_STATUS_SCHEMA_PATH = Path("schemas/champion_status.schema.json")
CANDIDATE_LEADERBOARD_SCHEMA_PATH = Path(
    "schemas/candidate_leaderboard.schema.json"
)
AGENT_RESULT_STATS_SCHEMA_PATH = Path("schemas/agent_result_stats.schema.json")
PROPOSAL_OUTCOME_MEMORY_SCHEMA_PATH = Path(
    "schemas/proposal_outcome_memory.schema.json"
)
EXPERIMENT_LEADERBOARD_SCHEMA_PATH = Path("schemas/experiment_leaderboard.schema.json")
EXPERIMENT_SUMMARY_DASHBOARD_SCHEMA_PATH = Path(
    "schemas/experiment_summary_dashboard.schema.json"
)
OPERATOR_RUN_REVIEW_SCHEMA_PATH = Path("schemas/operator_run_review.schema.json")


def list_experiments(
    *,
    experiments_dir: Path = Path("experiments"),
    limit: int = 10,
) -> list[dict[str, object]]:
    """Return recent experiment records."""
    return [
        {
            **record,
            "operator_home": experiment_list_operator_home_hint(
                record=record,
                experiments_dir=experiments_dir,
            ),
        }
        for record in recent_experiments(experiments_dir=experiments_dir, limit=limit)
    ]


def latest_iteration_run_id(
    *,
    experiments_dir: Path = Path("experiments"),
) -> str:
    """Return the latest indexed iteration-loop run id."""
    for record in reversed(read_experiment_index(experiments_dir)):
        run_id = str(record.get("run_id", ""))
        if str(record.get("kind", "")) != "iteration_loop" or not run_id:
            continue
        if (experiments_dir / run_id / "manifest.json").exists():
            return run_id
    raise FileNotFoundError("No indexed iteration-loop run found.")


def show_experiment(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return a compact summary for a run directory."""
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")

    manifest_path = run_dir / "manifest.json"
    decision_path = run_dir / "decision.json"
    if manifest_path.exists():
        manifest = load_json(manifest_path)
        return {
            "kind": "iteration_loop",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "summary_path": str(run_dir / "summary.md"),
            "candidate_leaderboard_path": str(run_dir / "candidate_leaderboard.json"),
            "operator_home": experiment_list_operator_home_hint(
                record={"kind": "iteration_loop", "run_id": run_id},
                experiments_dir=experiments_dir,
            ),
            "manifest": manifest,
        }
    if decision_path.exists():
        decision = load_json(decision_path)
        return {
            "kind": "single_run",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "summary_path": str(run_dir / "summary.md"),
            "operator_home": experiment_list_operator_home_hint(
                record={"kind": "single_run", "run_id": run_id},
                experiments_dir=experiments_dir,
            ),
            "decision": decision,
        }
    raise FileNotFoundError(f"No manifest.json or decision.json for run: {run_id}")


def summarize_experiments(
    *,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return aggregate counts for local experiment history."""
    records = read_experiment_index(experiments_dir)
    by_kind: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for record in records:
        kind = str(record.get("kind", "unknown"))
        status = str(record.get("status", "unknown"))
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1

    leaderboard = experiment_leaderboard(experiments_dir=experiments_dir, limit=1)
    best_run = leaderboard[0] if leaderboard else None
    dashboard = experiment_summary_dashboard(
        records=records,
        experiments_dir=experiments_dir,
        best_run=best_run,
    )
    errors = validate_experiment_summary_dashboard_payload(
        dashboard,
        repo_root=experiments_dir.parent,
    )
    if errors:
        raise ValueError(
            "experiment summary dashboard failed schema validation: "
            + "; ".join(errors)
        )
    return {
        "total_runs": len(records),
        "by_kind": by_kind,
        "by_status": by_status,
        "best_run": best_run,
        "dashboard": dashboard,
        "champion_lineage": champion_lineage_summary(
            experiments_dir=experiments_dir,
        ),
    }


def experiment_summary_dashboard(
    *,
    records: list[dict[str, object]],
    experiments_dir: Path,
    best_run: dict[str, object] | None,
    recent_limit: int = SUMMARY_DASHBOARD_RECENT_LIMIT,
) -> dict[str, object]:
    """Return a compact read-only dashboard for experiment status."""
    recent_records = records[-max(recent_limit, 0):] if recent_limit > 0 else []
    recent_diagnoses = [
        diagnose_record(record=record, experiments_dir=experiments_dir)
        for record in recent_records
    ]
    recent_rows = [compact_diagnosis_row(diagnosis) for diagnosis in recent_diagnoses]
    failure_codes = recent_failure_code_counts(recent_diagnoses)
    outcome_categories = recent_outcome_category_counts(recent_diagnoses)
    latest_run = compact_record_row(records[-1]) if records else None
    latest_accepted = latest_record_with_status(records, status="accepted")
    latest_rejected = latest_record_with_status(records, status="rejected")
    champion_gap = champion_gap_summary(
        experiments_dir=experiments_dir,
        best_run=best_run,
    )
    operator_home_entry = experiment_operator_home_entry(
        latest_run=latest_run,
        experiments_dir=experiments_dir,
    )
    return {
        "schema_version": SUMMARY_DASHBOARD_SCHEMA_VERSION,
        "total_runs": len(records),
        "recent_limit": recent_limit,
        "latest_run": latest_run,
        "latest_accepted_run": latest_accepted,
        "latest_rejected_run": latest_rejected,
        "recent_runs": recent_rows,
        "recent_failure_codes": dict(sorted(failure_codes.items())),
        "top_recent_failure_code": top_counter_key(failure_codes),
        "recent_outcome_categories": dict(sorted(outcome_categories.items())),
        "top_recent_outcome_category": top_counter_key(outcome_categories),
        "champion_gap": champion_gap,
        "operator_home_entry": operator_home_entry,
        "watchlist": dashboard_watchlist(
            recent_runs=recent_rows,
            latest_run=latest_run,
            latest_accepted=latest_accepted,
            champion_gap=champion_gap,
            failure_codes=failure_codes,
        ),
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_apply_patches": True,
            "does_not_promote_champion": True,
            "does_not_change_acceptance": True,
        },
    }


def validate_experiment_summary_dashboard_payload(
    payload: dict[str, object],
    *,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate an in-memory experiment summary dashboard payload."""
    schema = load_schema(repo_root / EXPERIMENT_SUMMARY_DASHBOARD_SCHEMA_PATH)
    errors = list(validate_json_payload(payload=payload, schema=schema))
    errors.extend(validate_experiment_summary_dashboard_consistency(payload))
    return tuple(errors)


def validate_experiment_summary_dashboard_consistency(
    payload: dict[str, object],
) -> tuple[str, ...]:
    """Validate derived dashboard counters and copied summary fields."""
    errors: list[str] = []
    recent_runs = list_payload(payload.get("recent_runs", []))
    recent_limit = int_value(payload.get("recent_limit", 0))
    total_runs = int_value(payload.get("total_runs", 0))
    if len(recent_runs) > max(recent_limit, 0):
        errors.append("experiment_summary_dashboard recent_runs exceeds recent_limit")
    if len(recent_runs) > total_runs:
        errors.append("experiment_summary_dashboard recent_runs exceeds total_runs")
    latest_run = dict_or_none_payload(payload.get("latest_run"))
    if total_runs == 0:
        if latest_run is not None or recent_runs:
            errors.append("experiment_summary_dashboard empty history mismatch")
    elif latest_run is None:
        errors.append("experiment_summary_dashboard latest_run missing")
    elif recent_runs and not same_run_identity(latest_run, recent_runs[-1]):
        errors.append("experiment_summary_dashboard latest_run mismatch")
    for row in recent_runs:
        if str(row.get("status", "")) == "accepted" and row.get("accepted") is not True:
            errors.append("experiment_summary_dashboard accepted row mismatch")
        if int_value(row.get("completed_rounds", -1)) < 0:
            errors.append("experiment_summary_dashboard completed_rounds negative")

    failure_counts = Counter(
        str(row.get("failure_code", ""))
        for row in recent_runs
        if str(row.get("failure_code", "")) not in {"", "none"}
    )
    if dict(sorted(failure_counts.items())) != int_mapping_payload(
        payload.get("recent_failure_codes", {})
    ):
        errors.append("experiment_summary_dashboard recent_failure_codes mismatch")
    if str(payload.get("top_recent_failure_code", "")) != top_counter_key(
        failure_counts,
    ):
        errors.append("experiment_summary_dashboard top_recent_failure_code mismatch")

    outcome_counts = Counter(
        str(row.get("outcome_category", ""))
        for row in recent_runs
        if str(row.get("outcome_category", ""))
    )
    if dict(sorted(outcome_counts.items())) != int_mapping_payload(
        payload.get("recent_outcome_categories", {})
    ):
        errors.append("experiment_summary_dashboard recent_outcome_categories mismatch")
    if str(payload.get("top_recent_outcome_category", "")) != top_counter_key(
        outcome_counts,
    ):
        errors.append(
            "experiment_summary_dashboard top_recent_outcome_category mismatch"
        )

    latest_accepted = dict_or_none_payload(payload.get("latest_accepted_run"))
    if latest_accepted is not None and latest_accepted.get("status") != "accepted":
        errors.append("experiment_summary_dashboard latest_accepted_run status mismatch")
    latest_rejected = dict_or_none_payload(payload.get("latest_rejected_run"))
    if latest_rejected is not None and latest_rejected.get("status") != "rejected":
        errors.append("experiment_summary_dashboard latest_rejected_run status mismatch")
    if latest_run is not None and latest_run.get("status") == "accepted":
        if latest_accepted is None or not same_run_identity(latest_accepted, latest_run):
            errors.append("experiment_summary_dashboard latest_accepted_run mismatch")
    if latest_run is not None and latest_run.get("status") == "rejected":
        if latest_rejected is None or not same_run_identity(latest_rejected, latest_run):
            errors.append("experiment_summary_dashboard latest_rejected_run mismatch")

    operator_home = dict_payload(payload.get("operator_home_entry", {}))
    errors.extend(
        validate_experiment_operator_home_entry(
            operator_home=operator_home,
            latest_run=latest_run,
            total_runs=total_runs,
        )
    )

    champion_gap = dict_payload(payload.get("champion_gap", {}))
    errors.extend(validate_champion_gap_summary(champion_gap))

    watchlist = dict_payload(payload.get("watchlist", {}))
    alerts = list_payload(watchlist.get("alerts", []))
    expected_severity_counts = severity_counts(alerts)
    if int_value(watchlist.get("alert_count", -1)) != len(alerts):
        errors.append("experiment_summary_dashboard watchlist alert_count mismatch")
    if dict_payload(watchlist.get("severity_counts", {})) != expected_severity_counts:
        errors.append(
            "experiment_summary_dashboard watchlist severity_counts mismatch"
        )
    if str(watchlist.get("status", "")) != watchlist_status(alerts):
        errors.append("experiment_summary_dashboard watchlist status mismatch")
    for alert in alerts:
        if str(alert.get("severity", "")) not in {"critical", "warning", "info"}:
            errors.append("experiment_summary_dashboard watchlist severity invalid")
        if not str(alert.get("code", "")):
            errors.append("experiment_summary_dashboard watchlist alert code missing")
    policy = dict_payload(payload.get("policy", {}))
    watchlist_policy = dict_payload(watchlist.get("policy", {}))
    for key, value in policy.items():
        if value is not True:
            errors.append(f"experiment_summary_dashboard policy false: {key}")
    for key, value in watchlist_policy.items():
        if value is not True:
            errors.append(f"experiment_summary_dashboard watchlist policy false: {key}")
    for key in (
        "inspection_only",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_apply_patches",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True or watchlist_policy.get(key) is not True:
            errors.append(f"experiment_summary_dashboard policy binding false: {key}")
    return tuple(errors)


def validate_experiment_operator_home_entry(
    *,
    operator_home: dict[str, object],
    latest_run: dict[str, object] | None,
    total_runs: int,
) -> tuple[str, ...]:
    """Validate the dashboard's latest-run operator-home navigation entry."""
    errors: list[str] = []
    available = bool(operator_home.get("available", False))
    run_id = str(operator_home.get("run_id", ""))
    run_kind = str(operator_home.get("run_kind", ""))
    command = str(operator_home.get("command", ""))
    next_command_status = str(operator_home.get("next_command_status", ""))
    next_command_blocked = bool(operator_home.get("next_command_blocked", False))
    next_command_blocker_count = int_value(
        operator_home.get("next_command_blocker_count", -1)
    )
    next_command_text = str(operator_home.get("next_command", ""))
    next_command_boundary = str(operator_home.get("next_command_boundary", ""))
    expected_command = (
        f"python -m orchestrator.experiments home {run_id} --markdown"
        if run_id
        else ""
    )
    if total_runs == 0:
        if available or run_id or command:
            errors.append("experiment_summary_dashboard operator_home empty mismatch")
    elif latest_run is None:
        errors.append("experiment_summary_dashboard operator_home latest missing")
    else:
        if run_id != str(latest_run.get("run_id", "")):
            errors.append("experiment_summary_dashboard operator_home run mismatch")
        if run_kind != str(latest_run.get("kind", "")):
            errors.append("experiment_summary_dashboard operator_home kind mismatch")
        if str(latest_run.get("kind", "")) == "iteration_loop":
            if not available:
                errors.append("experiment_summary_dashboard operator_home unavailable")
            if command != expected_command:
                errors.append(
                    "experiment_summary_dashboard operator_home command mismatch"
                )
            if not next_command_status or next_command_status == "unavailable":
                errors.append(
                    "experiment_summary_dashboard operator_home next command unavailable"
                )
            if not next_command_text:
                errors.append(
                    "experiment_summary_dashboard operator_home next command missing"
                )
            if not next_command_boundary:
                errors.append(
                    "experiment_summary_dashboard operator_home next boundary missing"
                )
        else:
            if available or command:
                errors.append(
                    "experiment_summary_dashboard operator_home non-iteration mismatch"
                )
            if next_command_status != "unavailable" or next_command_blocked:
                errors.append(
                    "experiment_summary_dashboard operator_home non-iteration next command"
                )
            if next_command_text or next_command_boundary:
                errors.append(
                    "experiment_summary_dashboard operator_home non-iteration next command"
                )
            if next_command_blocker_count != 0:
                errors.append(
                    "experiment_summary_dashboard operator_home non-iteration next command"
                )
    if available:
        if str(operator_home.get("command_label", "")) != "review_operator_home":
            errors.append("experiment_summary_dashboard operator_home label mismatch")
        if str(operator_home.get("command_boundary", "")) != "read_only_inspection":
            errors.append("experiment_summary_dashboard operator_home boundary mismatch")
        if bool(operator_home.get("command_is_hint_only", False)) is not True:
            errors.append("experiment_summary_dashboard operator_home hint mismatch")
        if bool(operator_home.get("terminal_only", False)) is not True:
            errors.append("experiment_summary_dashboard operator_home terminal mismatch")
        if bool(operator_home.get("artifact_created", True)) is not False:
            errors.append("experiment_summary_dashboard operator_home artifact mismatch")
        if next_command_blocked and next_command_blocker_count < 1:
            errors.append(
                "experiment_summary_dashboard operator_home blocker count mismatch"
            )
        if not next_command_blocked and next_command_blocker_count != 0:
            errors.append(
                "experiment_summary_dashboard operator_home blocker count mismatch"
            )
    return tuple(errors)


def same_run_identity(left: dict[str, object], right: dict[str, object]) -> bool:
    """Return whether two compact rows identify the same indexed run."""
    return all(
        str(left.get(key, "")) == str(right.get(key, ""))
        for key in ("run_id", "kind")
    )


def validate_champion_gap_summary(champion_gap: dict[str, object]) -> tuple[str, ...]:
    """Validate champion-gap fields are internally consistent."""
    errors: list[str] = []
    active = bool(champion_gap.get("active", False))
    status = str(champion_gap.get("status", ""))
    champion_run_id = str(champion_gap.get("champion_run_id", ""))
    comparison_run_id = str(champion_gap.get("comparison_run_id", ""))
    gap = optional_float_value(champion_gap.get("gap_to_champion"))
    champion_ev = optional_float_value(champion_gap.get("champion_validation_ev_delta"))
    comparison_ev = optional_float_value(
        champion_gap.get("comparison_validation_ev_delta")
    )
    if status == "no_champion":
        if active or champion_run_id or gap is not None:
            errors.append("experiment_summary_dashboard champion_gap no_champion mismatch")
    elif status == "no_comparison_run":
        if active or not champion_run_id or comparison_run_id or gap is not None:
            errors.append(
                "experiment_summary_dashboard champion_gap no_comparison_run mismatch"
            )
    else:
        if not active or not champion_run_id or not comparison_run_id or gap is None:
            errors.append("experiment_summary_dashboard champion_gap active mismatch")
        if champion_ev is not None and comparison_ev is not None and gap is not None:
            expected_gap = round(comparison_ev - champion_ev, 6)
            if round(gap, 6) != expected_gap:
                errors.append("experiment_summary_dashboard champion_gap delta mismatch")
        if status == "best_run_is_champion" and comparison_run_id != champion_run_id:
            errors.append(
                "experiment_summary_dashboard champion_gap champion identity mismatch"
            )
        if status == "best_run_beats_champion" and (gap is None or gap <= 0):
            errors.append("experiment_summary_dashboard champion_gap beats mismatch")
        if status == "best_run_trails_champion" and (gap is None or gap >= 0):
            errors.append("experiment_summary_dashboard champion_gap trails mismatch")
        if status == "best_run_ties_champion" and (gap is None or gap != 0):
            errors.append("experiment_summary_dashboard champion_gap ties mismatch")
    return tuple(errors)


def int_value(value: object, default: int = -1) -> int:
    """Return an int for validation without raising on malformed payloads."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def float_value(value: object, default: float = 0.0) -> float:
    """Return a float for validation without raising on malformed payloads."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def int_mapping_payload(value: object) -> dict[str, int]:
    """Return a stable string-to-int mapping for validator comparisons."""
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, row_value in value.items():
        result[str(key)] = int_value(row_value)
    return dict(sorted(result.items()))


def dict_or_none_payload(value: object) -> dict[str, object] | None:
    """Return an object payload or None for optional object fields."""
    if value is None:
        return None
    return value if isinstance(value, dict) else {}


def diagnose_record(
    *,
    record: dict[str, object],
    experiments_dir: Path,
) -> dict[str, object]:
    """Return diagnosis for one index record, with stable fallback fields."""
    run_id = str(record.get("run_id", ""))
    if not run_id:
        return {
            "run_id": "",
            "kind": str(record.get("kind", "unknown")),
            "status": "missing_run_id",
            "artifact_ok": False,
            "summary": "Index record is missing run_id.",
            "failure_code": "missing_run_id",
            "failure_stage": "index",
        }
    try:
        diagnosis = diagnose_run(
            run_id=run_id,
            experiments_dir=experiments_dir,
            repo_root=experiments_dir.parent,
        )
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        return {
            "run_id": run_id,
            "kind": str(record.get("kind", "unknown")),
            "status": "diagnosis_failed",
            "artifact_ok": False,
            "summary": str(exc),
            "failure_code": "diagnosis_failed",
            "failure_stage": "inspection",
        }
    return diagnosis


def latest_record_with_status(
    records: list[dict[str, object]],
    *,
    status: str,
) -> dict[str, object] | None:
    """Return the latest compact index row with the requested status."""
    for record in reversed(records):
        if str(record.get("status", "")) == status:
            return compact_record_row(record)
    return None


def compact_record_row(record: dict[str, object]) -> dict[str, object]:
    """Return stable fields from one experiment index record."""
    return {
        "run_id": str(record.get("run_id", "")),
        "kind": str(record.get("kind", "unknown")),
        "status": str(record.get("status", "unknown")),
        "created_at": str(record.get("created_at", "")),
    }


def experiment_list_operator_home_hint(
    *,
    record: dict[str, object],
    experiments_dir: Path,
) -> dict[str, object]:
    """Return a compact operator-home hint for one experiment-list row."""
    run_id = str(record.get("run_id", ""))
    kind = str(record.get("kind", ""))
    base = {
        "available": False,
        "reason": "not_iteration_run",
        "status": "unavailable",
        "command_label": "",
        "command": "",
        "command_boundary": "",
        "terminal_only": True,
        "artifact_created": False,
        "command_is_hint_only": True,
        "next_command_label": "",
        "next_command": "",
        "next_command_status": "unavailable",
        "next_command_blocked": False,
        "next_command_blocker_count": 0,
        "next_command_operator_hint": "",
        "next_command_boundary": "",
        "next_command_writes_artifact": "",
        "next_command_requires_explicit_operator_invocation": False,
        "next_command_requires_operator_approval": False,
        "next_command_records_operator_approval": False,
        "next_command_uses_guarded_executor": False,
        "next_command_is_hint_only": True,
    }
    if kind != "iteration_loop" or not run_id:
        return base

    manifest_home = load_manifest_operator_home(
        experiments_dir=experiments_dir,
        run_id=run_id,
    )
    command = f"python -m orchestrator.experiments home {run_id} --markdown"
    return {
        **base,
        "available": True,
        "reason": "iteration_run",
        "status": str(manifest_home.get("status", "unknown")),
        "command_label": "review_operator_home",
        "command": command,
        "command_boundary": "read_only_inspection",
        "next_command_label": str(manifest_home.get("next_command_label", "")),
        "next_command": str(manifest_home.get("next_command", "")),
        "next_command_status": str(
            manifest_home.get("next_command_status", "unknown")
        ),
        "next_command_blocked": bool(
            manifest_home.get("next_command_blocked", False)
        ),
        "next_command_blocker_count": int(
            manifest_home.get("next_command_blocker_count", 0) or 0
        ),
        "next_command_operator_hint": str(
            manifest_home.get("next_command_operator_hint", "")
        ),
        "next_command_boundary": str(manifest_home.get("next_command_boundary", "")),
        "next_command_writes_artifact": str(
            manifest_home.get("next_command_writes_artifact", "")
        ),
        "next_command_requires_explicit_operator_invocation": bool(
            manifest_home.get("next_command_requires_explicit_operator_invocation", False)
        ),
        "next_command_requires_operator_approval": bool(
            manifest_home.get("next_command_requires_operator_approval", False)
        ),
        "next_command_records_operator_approval": bool(
            manifest_home.get("next_command_records_operator_approval", False)
        ),
        "next_command_uses_guarded_executor": bool(
            manifest_home.get("next_command_uses_guarded_executor", False)
        ),
        "next_command_is_hint_only": bool(
            manifest_home.get("next_command_is_hint_only", True)
        ),
    }


def experiment_operator_home_entry(
    *,
    latest_run: dict[str, object] | None,
    experiments_dir: Path,
) -> dict[str, object]:
    """Return the latest-run operator home command for the summary dashboard."""
    base = {
        "schema_version": "experiment_operator_home_entry_v1",
        "available": False,
        "reason": "no_runs",
        "run_id": "",
        "run_kind": "",
        "status": "unavailable",
        "primary_focus": "",
        "action_step": "",
        "codex_unlock_runbook_status": "",
        "codex_intake_readiness_status": "",
        "next_command_label": "",
        "next_command": "",
        "next_command_status": "unavailable",
        "next_command_blocked": False,
        "next_command_blocker_count": 0,
        "next_command_operator_hint": "",
        "next_command_boundary": "",
        "next_command_writes_artifact": "",
        "next_command_requires_explicit_operator_invocation": False,
        "next_command_requires_operator_approval": False,
        "next_command_records_operator_approval": False,
        "next_command_uses_guarded_executor": False,
        "next_command_is_hint_only": True,
        "command_label": "",
        "command": "",
        "command_boundary": "",
        "terminal_only": True,
        "artifact_created": False,
        "command_is_hint_only": True,
        "source": "none",
    }
    if latest_run is None:
        return base
    run_id = str(latest_run.get("run_id", ""))
    run_kind = str(latest_run.get("kind", ""))
    base.update(
        {
            "reason": "latest_run_not_iteration",
            "run_id": run_id,
            "run_kind": run_kind,
            "source": "latest_run",
        }
    )
    if run_kind != "iteration_loop" or not run_id:
        return base

    manifest_home = load_manifest_operator_home(
        experiments_dir=experiments_dir,
        run_id=run_id,
    )
    command = f"python -m orchestrator.experiments home {run_id} --markdown"
    base.update(
        {
            "available": True,
            "reason": "latest_iteration_run",
            "status": str(manifest_home.get("status", "unknown")),
            "primary_focus": str(manifest_home.get("primary_focus", "")),
            "action_step": str(manifest_home.get("action_step", "")),
            "codex_unlock_runbook_status": str(
                manifest_home.get("codex_unlock_runbook_status", "")
            ),
            "codex_intake_readiness_status": str(
                manifest_home.get("codex_intake_readiness_status", "")
            ),
            "next_command_label": str(manifest_home.get("next_command_label", "")),
            "next_command": str(manifest_home.get("next_command", "")),
            "next_command_status": str(
                manifest_home.get("next_command_status", "unknown")
            ),
            "next_command_blocked": bool(
                manifest_home.get("next_command_blocked", False)
            ),
            "next_command_blocker_count": int(
                manifest_home.get("next_command_blocker_count", 0) or 0
            ),
            "next_command_operator_hint": str(
                manifest_home.get("next_command_operator_hint", "")
            ),
            "next_command_boundary": str(
                manifest_home.get("next_command_boundary", "")
            ),
            "next_command_writes_artifact": str(
                manifest_home.get("next_command_writes_artifact", "")
            ),
            "next_command_requires_explicit_operator_invocation": bool(
                manifest_home.get(
                    "next_command_requires_explicit_operator_invocation", False
                )
            ),
            "next_command_requires_operator_approval": bool(
                manifest_home.get("next_command_requires_operator_approval", False)
            ),
            "next_command_records_operator_approval": bool(
                manifest_home.get("next_command_records_operator_approval", False)
            ),
            "next_command_uses_guarded_executor": bool(
                manifest_home.get("next_command_uses_guarded_executor", False)
            ),
            "next_command_is_hint_only": bool(
                manifest_home.get("next_command_is_hint_only", True)
            ),
            "command_label": "review_operator_home",
            "command": command,
            "command_boundary": "read_only_inspection",
            "source": (
                "latest_run_manifest_operator_home"
                if manifest_home
                else "derived_latest_iteration_run"
            ),
        }
    )
    return base


def load_manifest_operator_home(
    *,
    experiments_dir: Path,
    run_id: str,
) -> dict[str, object]:
    """Load the saved operator_home manifest row when present."""
    manifest_path = experiments_dir / run_id / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        manifest = load_json(manifest_path)
    except (json.JSONDecodeError, OSError):
        return {}
    operator_home = manifest.get("operator_home", {})
    return operator_home if isinstance(operator_home, dict) else {}


def compact_diagnosis_row(diagnosis: dict[str, object]) -> dict[str, object]:
    """Return one compact dashboard row from a diagnosis payload."""
    best_round = dict_payload(diagnosis.get("best_round", {}))
    outcome = dict_payload(diagnosis.get("run_outcome_summary", {}))
    selected_candidates = list_payload(diagnosis.get("selected_candidates", []))
    selected = selected_candidates[0] if selected_candidates else {}
    return {
        "run_id": str(diagnosis.get("run_id", "")),
        "kind": str(diagnosis.get("kind", "unknown")),
        "status": str(diagnosis.get("status", "unknown")),
        "artifact_ok": bool(diagnosis.get("artifact_ok", False)),
        "accepted": bool(diagnosis.get("accepted", False))
        or str(diagnosis.get("status", "")) == "accepted",
        "validation_ev_delta": dashboard_ev_delta(diagnosis, best_round),
        "best_round": str(best_round.get("round_id", "")),
        "accepted_round": diagnosis.get("accepted_round"),
        "completed_rounds": int(diagnosis.get("completed_rounds", 0) or 0),
        "stop_reason": str(diagnosis.get("stop_reason", "")),
        "failure_code": diagnosis_failure_code(diagnosis),
        "failure_stage": diagnosis_failure_stage(diagnosis),
        "outcome_category": str(outcome.get("category", "")),
        "outcome_primary_code": str(outcome.get("primary_code", "")),
        "outcome_primary_stage": str(outcome.get("primary_stage", "")),
        "selected_direction_tag": str(selected.get("direction_tag", "")),
        "summary": str(diagnosis.get("summary", "")),
    }


def dashboard_ev_delta(
    diagnosis: dict[str, object],
    best_round: dict[str, object],
) -> float:
    """Return the most comparable validation EV delta for a diagnosis."""
    if best_round:
        return round(float(best_round.get("validation_ev_delta", 0.0)), 6)
    return round(float(diagnosis.get("validation_ev_delta", 0.0)), 6)


def diagnosis_failure_code(diagnosis: dict[str, object]) -> str:
    """Return the first stable failure code for a diagnosis."""
    code = str(diagnosis.get("failure_code", ""))
    if code:
        return code
    rounds = list_payload(diagnosis.get("rounds", []))
    for row in reversed(rounds):
        row_code = str(row.get("failure_code", ""))
        if row_code and row_code != "none":
            return row_code
    return "none"


def diagnosis_failure_stage(diagnosis: dict[str, object]) -> str:
    """Return the first stable failure stage for a diagnosis."""
    stage = str(diagnosis.get("failure_stage", ""))
    if stage:
        return stage
    rounds = list_payload(diagnosis.get("rounds", []))
    for row in reversed(rounds):
        row_stage = str(row.get("failure_stage", ""))
        if row_stage and row_stage != "none":
            return row_stage
    return "none"


def recent_failure_code_counts(
    diagnoses: list[dict[str, object]],
) -> Counter[str]:
    """Count non-success failure codes among recent diagnoses."""
    counts: Counter[str] = Counter()
    for diagnosis in diagnoses:
        code = diagnosis_failure_code(diagnosis)
        if code and code != "none":
            counts[code] += 1
    return counts


def recent_outcome_category_counts(
    diagnoses: list[dict[str, object]],
) -> Counter[str]:
    """Count run-outcome categories among recent diagnoses."""
    counts: Counter[str] = Counter()
    for diagnosis in diagnoses:
        outcome = dict_payload(diagnosis.get("run_outcome_summary", {}))
        category = str(outcome.get("category", ""))
        if category:
            counts[category] += 1
    return counts


def champion_gap_summary(
    *,
    experiments_dir: Path,
    best_run: dict[str, object] | None,
) -> dict[str, object]:
    """Compare the current best indexed run against the champion registry."""
    champion_file = champion_path(experiments_dir)
    if not champion_file.exists():
        return {
            "active": False,
            "status": "no_champion",
            "champion_run_id": "",
            "comparison_run_id": str(best_run.get("run_id", "")) if best_run else "",
            "gap_to_champion": None,
        }
    champion = load_json(champion_file)
    champion_run_id = str(champion.get("champion_run_id", ""))
    champion_ev_delta = float(champion.get("validation_ev_delta", 0.0) or 0.0)
    if not best_run:
        return {
            "active": False,
            "status": "no_comparison_run",
            "champion_run_id": champion_run_id,
            "comparison_run_id": "",
            "champion_validation_ev_delta": round(champion_ev_delta, 6),
            "comparison_validation_ev_delta": None,
            "gap_to_champion": None,
        }
    comparison_run_id = str(best_run.get("run_id", ""))
    comparison_ev_delta = float(best_run.get("ev_delta", 0.0) or 0.0)
    gap = round(comparison_ev_delta - champion_ev_delta, 6)
    if comparison_run_id == champion_run_id:
        status = "best_run_is_champion"
    elif gap > 0:
        status = "best_run_beats_champion"
    elif gap < 0:
        status = "best_run_trails_champion"
    else:
        status = "best_run_ties_champion"
    return {
        "active": True,
        "status": status,
        "champion_run_id": champion_run_id,
        "comparison_run_id": comparison_run_id,
        "champion_validation_ev_delta": round(champion_ev_delta, 6),
        "comparison_validation_ev_delta": round(comparison_ev_delta, 6),
        "gap_to_champion": gap,
    }


def top_counter_key(counter: Counter[str]) -> str:
    """Return the highest-count key with stable tie-breaking."""
    if not counter:
        return "none"
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def dashboard_watchlist(
    *,
    recent_runs: list[dict[str, object]],
    latest_run: dict[str, object] | None,
    latest_accepted: dict[str, object] | None,
    champion_gap: dict[str, object],
    failure_codes: Counter[str],
) -> dict[str, object]:
    """Return deterministic operator-facing dashboard alerts."""
    alerts: list[dict[str, object]] = []
    if latest_run is None:
        alerts.append(
            watch_alert(
                severity="info",
                code="no_runs_indexed",
                title="No experiment runs indexed",
                detail="Run a single or iteration loop to populate experiment history.",
            )
        )
    elif str(latest_run.get("status", "")) == "stopped_repeated_proposal":
        alerts.append(
            watch_alert(
                severity="warning",
                code="latest_run_repeated_proposal",
                title="Latest run stopped on a repeated proposal",
                detail="The active modifier is repeating a previously failed patch.",
                run_id=str(latest_run.get("run_id", "")),
            )
        )
    if latest_accepted is None and latest_run is not None:
        alerts.append(
            watch_alert(
                severity="info",
                code="no_accepted_run_indexed",
                title="No accepted run indexed yet",
                detail="The current experiment history has not recorded an accepted run.",
            )
        )
    repeated_failures = int(failure_codes.get("patch_memory_rejected", 0))
    if repeated_failures:
        alerts.append(
            watch_alert(
                severity="warning",
                code="recent_patch_memory_rejections",
                title="Recent runs hit proposal memory rejection",
                detail=f"{repeated_failures} recent run(s) rejected a repeated patch.",
            )
        )
    artifact_failed = [
        row for row in recent_runs if not bool(row.get("artifact_ok", False))
    ]
    for row in artifact_failed[:3]:
        alerts.append(
            watch_alert(
                severity="critical",
                code="recent_artifact_health_failed",
                title="Recent run has invalid artifacts",
                detail=str(row.get("summary", "")),
                run_id=str(row.get("run_id", "")),
            )
        )
    gap = optional_float_value(champion_gap.get("gap_to_champion"))
    if bool(champion_gap.get("active", False)) and gap is not None and gap < 0:
        alerts.append(
            watch_alert(
                severity="warning",
                code="best_run_trails_champion",
                title="Best indexed run trails the champion",
                detail=(
                    f"Best run {champion_gap.get('comparison_run_id', '')} "
                    f"trails champion {champion_gap.get('champion_run_id', '')} "
                    f"by {abs(gap):.6f} validation EV delta."
                ),
                run_id=str(champion_gap.get("comparison_run_id", "")),
            )
        )
    return {
        "schema_version": "experiment_watchlist_v1",
        "status": watchlist_status(alerts),
        "alert_count": len(alerts),
        "severity_counts": severity_counts(alerts),
        "alerts": alerts,
        "policy": {
            "inspection_only": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
        },
    }


def watch_alert(
    *,
    severity: str,
    code: str,
    title: str,
    detail: str,
    run_id: str = "",
) -> dict[str, object]:
    """Return one stable watchlist alert row."""
    return {
        "severity": severity,
        "code": code,
        "title": title,
        "detail": detail,
        "run_id": run_id,
    }


def watchlist_status(alerts: list[dict[str, object]]) -> str:
    """Return compact watchlist status from alert severities."""
    severities = {str(alert.get("severity", "")) for alert in alerts}
    if "critical" in severities:
        return "critical"
    if "warning" in severities:
        return "attention"
    if alerts:
        return "informational"
    return "clean"


def severity_counts(alerts: list[dict[str, object]]) -> dict[str, int]:
    """Return stable alert severity counts."""
    counts = Counter(str(alert.get("severity", "unknown")) for alert in alerts)
    return {key: int(counts.get(key, 0)) for key in ("critical", "warning", "info")}


def optional_float_value(value: object) -> float | None:
    """Return an optional float from a JSON-like value."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def render_experiment_summary_markdown(payload: dict[str, object]) -> str:
    """Render the experiment summary dashboard as compact markdown."""
    dashboard = dict_payload(payload.get("dashboard", {}))
    watchlist = dict_payload(dashboard.get("watchlist", {}))
    lineage = dict_payload(payload.get("champion_lineage", {}))
    by_kind = dict_payload(payload.get("by_kind", {}))
    by_status = dict_payload(payload.get("by_status", {}))
    best_run = dict_payload(payload.get("best_run", {}))
    champion_gap = dict_payload(dashboard.get("champion_gap", {}))
    latest_run = dict_payload(dashboard.get("latest_run", {}))
    latest_accepted = dict_payload(dashboard.get("latest_accepted_run", {}))
    latest_rejected = dict_payload(dashboard.get("latest_rejected_run", {}))
    recent_runs = list_payload(dashboard.get("recent_runs", []))
    failure_counts = dict_payload(dashboard.get("recent_failure_codes", {}))
    outcome_counts = dict_payload(dashboard.get("recent_outcome_categories", {}))
    operator_home = dict_payload(dashboard.get("operator_home_entry", {}))
    lines = [
        "# Experiment Summary",
        "",
        f"- Total runs: `{payload.get('total_runs', 0)}`",
        f"- Latest run: `{latest_run.get('run_id', 'none') or 'none'}` "
        f"({latest_run.get('status', 'unknown') or 'unknown'})",
        f"- Latest accepted: `{latest_accepted.get('run_id', 'none') or 'none'}`",
        f"- Latest rejected: `{latest_rejected.get('run_id', 'none') or 'none'}`",
        f"- Best run: `{best_run.get('run_id', 'none') or 'none'}` "
        f"({number_text(best_run.get('ev_delta'))} validation EV delta)",
        f"- Champion: `{lineage.get('current_champion_run_id', '') or 'none'}`",
        f"- Champion gap: `{champion_gap.get('status', 'unknown')}` "
        f"({number_text(champion_gap.get('gap_to_champion'))})",
        f"- Top recent failure: `{dashboard.get('top_recent_failure_code', 'none')}`",
        f"- Top recent outcome: `{dashboard.get('top_recent_outcome_category', 'none')}`",
        f"- Watchlist: `{watchlist.get('status', 'clean')}` "
        f"({watchlist.get('alert_count', 0)} alert(s))",
        f"- Operator home: `{operator_home.get('status', 'unavailable')}` "
        f"({operator_home.get('reason', 'unknown')})",
        "- Operator home command: "
        f"`{operator_home.get('command', '') or 'unavailable'}`",
        "- Operator home next command: "
        f"`{operator_home.get('next_command_label', '') or 'unavailable'}`",
        "- Operator home next command text: "
        f"`{operator_home.get('next_command', '') or 'unavailable'}`",
        "- Operator home next command status: "
        f"`{operator_home.get('next_command_status', 'unavailable')}`",
        "- Operator home next command boundary: "
        f"`{operator_home.get('next_command_boundary', '') or 'unavailable'}`",
        "- Operator home next command blocked: "
        f"`{operator_home.get('next_command_blocked', False)}` "
        f"({operator_home.get('next_command_blocker_count', 0)} blocker(s))",
        "- Operator home next command hint: "
        f"{operator_home.get('next_command_operator_hint', '') or 'none'}",
        "- Operator home next command writes: "
        f"`{operator_home.get('next_command_writes_artifact', '') or 'none'}`",
        "- Operator home next command requires explicit invocation: "
        f"`{operator_home.get('next_command_requires_explicit_operator_invocation', False)}`",
        "- Operator home next command requires approval: "
        f"`{operator_home.get('next_command_requires_operator_approval', False)}`",
        "- Operator home next command records approval: "
        f"`{operator_home.get('next_command_records_operator_approval', False)}`",
        "- Operator home next command uses guarded executor: "
        f"`{operator_home.get('next_command_uses_guarded_executor', False)}`",
        "- Operator home next command hint-only: "
        f"`{operator_home.get('next_command_is_hint_only', False)}`",
        "",
        "## Watchlist",
        "",
        "| Severity | Code | Run | Detail |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(watchlist_markdown_rows(watchlist))
    lines.extend(
        [
            "",
            "## Counts",
            "",
            "| Kind | Count |",
            "| --- | ---: |",
        ]
    )
    lines.extend(counter_markdown_rows(by_kind))
    lines.extend(
        [
            "",
            "| Status | Count |",
            "| --- | ---: |",
        ]
    )
    lines.extend(counter_markdown_rows(by_status))
    lines.extend(
        [
            "",
            "## Recent Failure Codes",
            "",
            "| Failure Code | Count |",
            "| --- | ---: |",
        ]
    )
    lines.extend(counter_markdown_rows(failure_counts))
    lines.extend(
        [
            "",
            "## Recent Outcome Categories",
            "",
            "| Outcome Category | Count |",
            "| --- | ---: |",
        ]
    )
    lines.extend(counter_markdown_rows(outcome_counts))
    lines.extend(
        [
            "",
            "## Recent Runs",
            "",
            "| Run | Kind | Status | Outcome | EV Delta | Failure |",
            "| --- | --- | --- | --- | ---: | --- |",
        ]
    )
    if not recent_runs:
        lines.append("| none |  |  |  |  |  |")
    else:
        for row in recent_runs:
            lines.append(
                "| "
                f"`{markdown_cell(row.get('run_id', ''))}` | "
                f"{markdown_cell(row.get('kind', ''))} | "
                f"{markdown_cell(row.get('status', ''))} | "
                f"`{markdown_cell(row.get('outcome_category', ''))}` | "
                f"{number_text(row.get('validation_ev_delta'))} | "
                f"`{markdown_cell(row.get('failure_code', 'none'))}` |"
            )
    lines.extend(
        [
            "",
            "## Champion Lineage",
            "",
            f"- OK: `{lineage.get('ok', False)}`",
            f"- History events: `{lineage.get('event_count', 0)}`",
            f"- Approved receipts: `{lineage.get('approved_receipt_count', 0)}`",
            f"- Legacy direct promotions: `{lineage.get('legacy_direct_count', 0)}`",
            f"- Latest promotion source: `{lineage.get('latest_promotion_source', '') or 'none'}`",
            "",
            "## Policy",
            "",
            "- Inspection only: `True`",
            "- Executes agents: `False`",
            "- Runs backtests: `False`",
            "- Applies patches: `False`",
            "- Changes acceptance: `False`",
        ]
    )
    return "\n".join(lines) + "\n"


def watchlist_markdown_rows(watchlist: dict[str, object]) -> list[str]:
    """Return markdown rows for dashboard watchlist alerts."""
    alerts = list_payload(watchlist.get("alerts", []))
    if not alerts:
        return ["| clean | none |  | No watchlist alerts. |"]
    rows: list[str] = []
    for alert in alerts:
        rows.append(
            "| "
            f"`{markdown_cell(alert.get('severity', ''))}` | "
            f"`{markdown_cell(alert.get('code', ''))}` | "
            f"`{markdown_cell(alert.get('run_id', ''))}` | "
            f"{markdown_cell(alert.get('detail', ''))} |"
        )
    return rows


def counter_markdown_rows(payload: dict[str, object]) -> list[str]:
    """Return stable markdown rows for a string-to-count payload."""
    if not payload:
        return ["| none | 0 |"]
    return [
        f"| `{markdown_cell(key)}` | {int(value)} |"
        for key, value in sorted(payload.items())
    ]


def number_text(value: object) -> str:
    """Return compact markdown text for optional numeric values."""
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return markdown_cell(value)


def markdown_cell(value: object) -> str:
    """Escape markdown table cell text."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def experiment_leaderboard(
    *,
    experiments_dir: Path = Path("experiments"),
    limit: int = 10,
) -> list[dict[str, object]]:
    """Rank experiments by validation EV improvement."""
    rows = [
        experiment_score(record=record, experiments_dir=experiments_dir)
        for record in read_experiment_index(experiments_dir)
    ]
    rows.sort(
        key=lambda row: (
            float(row.get("ev_delta", 0.0)),
            str(row.get("created_at", "")),
        ),
        reverse=True,
    )
    payload = rows[: max(limit, 0)]
    errors = validate_experiment_leaderboard_payload(
        payload,
        repo_root=experiments_dir.parent,
        limit=limit,
    )
    if errors:
        raise ValueError(
            "experiment leaderboard failed schema validation: " + "; ".join(errors)
        )
    return payload


def validate_experiment_leaderboard_payload(
    payload: list[dict[str, object]],
    *,
    repo_root: Path,
    limit: int,
) -> tuple[str, ...]:
    """Validate the terminal-only experiment leaderboard output."""
    schema = load_schema(repo_root / EXPERIMENT_LEADERBOARD_SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=payload,
            schema=schema,
            schema_dir=(repo_root / EXPERIMENT_LEADERBOARD_SCHEMA_PATH).parent,
        )
    )
    errors.extend(validate_experiment_leaderboard_consistency(payload, limit=limit))
    return tuple(errors)


def validate_experiment_leaderboard_consistency(
    payload: list[dict[str, object]],
    *,
    limit: int,
) -> tuple[str, ...]:
    """Validate leaderboard ordering, kind-specific fields, and bounded output."""
    errors: list[str] = []
    if len(payload) > max(limit, 0):
        errors.append("experiment_leaderboard limit exceeded")
    previous_key: tuple[float, str] | None = None
    seen_run_ids: set[str] = set()
    for row in payload:
        run_id = str(row.get("run_id", ""))
        kind = str(row.get("kind", ""))
        current_key = (
            float_value(row.get("ev_delta"), 0.0),
            str(row.get("created_at", "")),
        )
        if previous_key is not None and current_key > previous_key:
            errors.append("experiment_leaderboard sort order mismatch")
        previous_key = current_key
        if not run_id:
            errors.append("experiment_leaderboard run_id missing")
        elif run_id in seen_run_ids:
            errors.append("experiment_leaderboard duplicate run_id")
        seen_run_ids.add(run_id)
        if kind == "single_run":
            ev_before = optional_float_value(row.get("ev_before"))
            ev_after = optional_float_value(row.get("ev_after"))
            ev_delta = optional_float_value(row.get("ev_delta"))
            if ev_before is None or ev_after is None:
                errors.append("experiment_leaderboard single_run ev fields missing")
            elif ev_delta is not None and round(ev_after - ev_before, 6) != round(
                ev_delta,
                6,
            ):
                errors.append("experiment_leaderboard single_run ev_delta mismatch")
        elif kind == "iteration_loop":
            if int_value(row.get("completed_rounds", 0), 0) < 0:
                errors.append("experiment_leaderboard completed_rounds negative")
            best_round = row.get("best_round")
            if best_round is not None and not str(best_round):
                errors.append("experiment_leaderboard best_round empty")
    return tuple(errors)


def candidate_leaderboard(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    limit: int = 20,
) -> list[dict[str, object]]:
    """Return ranked candidate attempts for an iteration run."""
    run_dir = experiments_dir / run_id
    path = run_dir / "candidate_leaderboard.json"
    if not path.exists():
        raise FileNotFoundError(f"Candidate leaderboard not found for run: {run_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Candidate leaderboard is not a list: {path}")
    rows = [row for row in payload if isinstance(row, dict)]
    limited_rows = rows[: max(limit, 0)]
    errors = validate_candidate_leaderboard_payload(
        limited_rows,
        repo_root=experiments_dir.parent,
        run_id=run_id,
        limit=limit,
    )
    if errors:
        raise ValueError(
            "candidate leaderboard failed schema validation: " + "; ".join(errors)
        )
    return limited_rows


def validate_candidate_leaderboard_payload(
    payload: list[dict[str, object]],
    *,
    repo_root: Path,
    run_id: str,
    limit: int,
) -> tuple[str, ...]:
    """Validate the terminal-only candidate leaderboard output."""
    schema = load_schema(repo_root / CANDIDATE_LEADERBOARD_SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=payload,
            schema=schema,
            schema_dir=(repo_root / CANDIDATE_LEADERBOARD_SCHEMA_PATH).parent,
        )
    )
    errors.extend(
        validate_candidate_leaderboard_consistency(
            payload,
            run_id=run_id,
            limit=limit,
        )
    )
    return tuple(errors)


def validate_candidate_leaderboard_consistency(
    payload: list[dict[str, object]],
    *,
    run_id: str,
    limit: int,
) -> tuple[str, ...]:
    """Validate candidate leaderboard bounds, ordering, and selected-row signals."""
    errors: list[str] = []
    if len(payload) > max(limit, 0):
        errors.append("candidate_leaderboard limit exceeded")
    previous_key: tuple[object, ...] | None = None
    seen_attempts: set[tuple[str, str]] = set()
    for row in payload:
        row_run_id = str(row.get("run_id", ""))
        round_id = str(row.get("round_id", ""))
        attempt_id = str(row.get("attempt_id", ""))
        if row_run_id != run_id:
            errors.append("candidate_leaderboard run_id mismatch")
        if not round_id:
            errors.append("candidate_leaderboard round_id missing")
        if not attempt_id:
            errors.append("candidate_leaderboard attempt_id missing")
        attempt_key = (round_id, attempt_id)
        if attempt_id and attempt_key in seen_attempts:
            errors.append("candidate_leaderboard duplicate attempt")
        seen_attempts.add(attempt_key)
        if int_value(row.get("attempt_index", 0), 0) < 1:
            errors.append("candidate_leaderboard attempt_index invalid")
        current_key = candidate_leaderboard_validation_sort_key(row)
        if previous_key is not None and current_key > previous_key:
            errors.append("candidate_leaderboard sort order mismatch")
        previous_key = current_key
        quality = row.get("quality_breakdown", {})
        if not isinstance(quality, dict):
            errors.append("candidate_leaderboard quality_breakdown invalid")
        else:
            if quality.get("schema_version") != "candidate_quality_v1":
                errors.append("candidate_leaderboard quality schema invalid")
            total_score = optional_float_value(quality.get("total_score"))
            candidate_score = optional_float_value(row.get("candidate_score"))
            if total_score is not None and candidate_score is not None:
                if round(total_score, 6) != round(candidate_score, 6):
                    errors.append("candidate_leaderboard score mismatch")
            signals = quality.get("signals", {})
            if row.get("selected") is True:
                validation_ev = row.get("validation_ev_delta")
                holdout_ev = row.get("holdout_ev_delta")
                if validation_ev is None:
                    errors.append("candidate_leaderboard selected validation missing")
                if holdout_ev is None:
                    errors.append("candidate_leaderboard selected holdout missing")
                if isinstance(signals, dict):
                    if signals.get("validation_ev_delta") != validation_ev:
                        errors.append(
                            "candidate_leaderboard selected validation signal mismatch"
                        )
                    if signals.get("holdout_ev_delta") != holdout_ev:
                        errors.append(
                            "candidate_leaderboard selected holdout signal mismatch"
                        )
    return tuple(errors)


def candidate_leaderboard_validation_sort_key(
    row: dict[str, object],
) -> tuple[object, ...]:
    """Return the expected descending sort key for candidate leaderboard rows."""
    validation_ev_delta = row.get("validation_ev_delta")
    validation_value = (
        float(validation_ev_delta)
        if isinstance(validation_ev_delta, int | float)
        else float("-inf")
    )
    return (
        bool(row.get("selected", False)),
        validation_value,
        float_value(row.get("probe_ev_delta"), 0.0),
        int_value(row.get("candidate_score", 0), 0),
        str(row.get("round_id", "")),
        -int_value(row.get("attempt_index", 0), 0),
    )


def agent_result_stats(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return agent/direction/patch-family aggregate stats for one run."""
    run_dir = experiments_dir / run_id
    path = run_dir / "agent_result_stats.json"
    if path.exists():
        payload = load_json(path)
        payload["from_artifact"] = True
        payload["round_replays"] = round_replay_summary(run_dir=run_dir)
        errors = validate_agent_result_stats_payload(
            payload,
            repo_root=experiments_dir.parent,
            run_id=run_id,
            run_dir=run_dir,
        )
        if errors:
            raise ValueError(
                "agent result stats failed schema validation: " + "; ".join(errors)
            )
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_agent_result_stats(run_dir=run_dir)
    payload["from_artifact"] = False
    payload["round_replays"] = round_replay_summary(run_dir=run_dir)
    errors = validate_agent_result_stats_payload(
        payload,
        repo_root=experiments_dir.parent,
        run_id=run_id,
        run_dir=run_dir,
    )
    if errors:
        raise ValueError(
            "agent result stats failed schema validation: " + "; ".join(errors)
        )
    return payload


def validate_agent_result_stats_payload(
    payload: dict[str, object],
    *,
    repo_root: Path,
    run_id: str,
    run_dir: Path,
) -> tuple[str, ...]:
    """Validate the terminal-only agent result stats output."""
    schema = load_schema(repo_root / AGENT_RESULT_STATS_SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=payload,
            schema=schema,
            schema_dir=(repo_root / AGENT_RESULT_STATS_SCHEMA_PATH).parent,
        )
    )
    errors.extend(
        validate_agent_result_stats_consistency(
            payload,
            repo_root=repo_root,
            run_id=run_id,
            run_dir=run_dir,
        )
    )
    return tuple(errors)


def validate_agent_result_stats_consistency(
    payload: dict[str, object],
    *,
    repo_root: Path,
    run_id: str,
    run_dir: Path,
) -> tuple[str, ...]:
    """Validate stats output against the saved candidate leaderboard and replays."""
    errors: list[str] = []
    if payload.get("run_id") != run_id:
        errors.append("agent_result_stats run_id mismatch")
    expected = build_agent_result_stats(run_dir=run_dir)
    for key in (
        "schema_version",
        "totals",
        "agents",
        "directions",
        "patch_families",
        "routing_hints",
    ):
        if payload.get(key) != expected.get(key):
            errors.append(f"agent_result_stats {key} mismatch")
    if resolve_report_path(payload.get("source_path"), repo_root) != resolve_report_path(
        expected.get("source_path"),
        repo_root,
    ):
        errors.append("agent_result_stats source_path mismatch")
    expected_round_replays = round_replay_summary(run_dir=run_dir)
    if normalize_report_paths(payload.get("round_replays"), repo_root) != (
        normalize_report_paths(expected_round_replays, repo_root)
    ):
        errors.append("agent_result_stats round_replays mismatch")
    from_artifact = payload.get("from_artifact")
    if from_artifact is not None and not isinstance(from_artifact, bool):
        errors.append("agent_result_stats from_artifact invalid")
    return tuple(errors)


def resolve_report_path(value: object, repo_root: Path) -> str:
    """Return an absolute comparable path for repo-local report fields."""
    raw = str(value or "")
    if not raw:
        return ""
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    return str(path.resolve())


def normalize_report_paths(value: object, repo_root: Path) -> object:
    """Normalize nested report path fields for stable consistency checks."""
    if isinstance(value, dict):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if key in {"path", "markdown_path", "replay_path"}:
                normalized[key] = resolve_report_path(item, repo_root)
            else:
                normalized[key] = normalize_report_paths(item, repo_root)
        return normalized
    if isinstance(value, list):
        return [normalize_report_paths(item, repo_root) for item in value]
    return value


def proposal_memory(
    *,
    experiments_dir: Path = Path("experiments"),
    limit: int = 10,
) -> list[dict[str, object]]:
    """Return validated recent proposal outcome memory records."""
    payload = recent_outcomes(experiments_dir=experiments_dir, limit=limit)
    errors = validate_proposal_memory_payload(
        payload,
        repo_root=experiments_dir.parent,
        experiments_dir=experiments_dir,
        limit=limit,
    )
    if errors:
        raise ValueError(
            "proposal memory failed schema validation: " + "; ".join(errors)
        )
    return payload


def validate_proposal_memory_payload(
    payload: list[dict[str, object]],
    *,
    repo_root: Path,
    experiments_dir: Path,
    limit: int,
) -> tuple[str, ...]:
    """Validate the terminal-only proposal outcome memory output."""
    schema = load_schema(repo_root / PROPOSAL_OUTCOME_MEMORY_SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=payload,
            schema=schema,
            schema_dir=(repo_root / PROPOSAL_OUTCOME_MEMORY_SCHEMA_PATH).parent,
        )
    )
    errors.extend(
        validate_proposal_memory_consistency(
            payload,
            experiments_dir=experiments_dir,
            limit=limit,
        )
    )
    return tuple(errors)


def validate_proposal_memory_consistency(
    payload: list[dict[str, object]],
    *,
    experiments_dir: Path,
    limit: int,
) -> tuple[str, ...]:
    """Validate recent memory bounds and identity fields."""
    errors: list[str] = []
    bounded_limit = max(limit, 0)
    if len(payload) > bounded_limit:
        errors.append("proposal_memory limit exceeded")
    expected = read_outcome_memory(experiments_dir)[-bounded_limit:] if bounded_limit else []
    if payload != expected:
        errors.append("proposal_memory recent window mismatch")
    for row in payload:
        created_at = str(row.get("created_at", ""))
        if not created_at:
            errors.append("proposal_memory created_at missing")
        if str(row.get("kind", "")) != "proposal_outcome":
            errors.append("proposal_memory kind mismatch")
        for key in ("run_id", "round_id"):
            if not str(row.get(key, "")):
                errors.append(f"proposal_memory {key} missing")
        if not isinstance(row.get("accepted"), bool):
            errors.append("proposal_memory accepted invalid")
        if "validation_ev_delta" in row and optional_float_value(
            row.get("validation_ev_delta")
        ) is None:
            errors.append("proposal_memory validation_ev_delta invalid")
    return tuple(errors)


def candidate_quality_trace(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return candidate quality trace for one iteration run."""
    run_dir = experiments_dir / run_id
    path = run_dir / "candidate_quality_trace.json"
    if path.exists():
        payload = load_json(path)
        errors = validate_candidate_quality_trace_payload(
            payload,
            run_dir=run_dir,
            repo_root=experiments_dir.parent,
            require_current_evidence=True,
        )
        if errors:
            raise ValueError(
                "candidate quality trace failed schema validation: "
                + "; ".join(errors)
            )
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_candidate_quality_trace(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
    )
    errors = validate_candidate_quality_trace_payload(
        payload,
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "candidate quality trace failed schema validation: " + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def modifier_profile_recommendation(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    config_path: Path = Path("config/default.json"),
) -> dict[str, object]:
    """Return modifier profile recommendation for one iteration run."""
    run_dir = experiments_dir / run_id
    path = run_dir / "modifier_profile_recommendation.json"
    repo_root = experiments_dir.parent
    if path.exists():
        payload = load_json(path)
        errors = validate_modifier_profile_recommendation_payload(
            payload,
            run_dir=run_dir,
            repo_root=repo_root,
            config_path=config_path,
            require_current_evidence=True,
        )
        if errors:
            raise ValueError(
                "modifier profile recommendation failed schema validation: "
                + "; ".join(errors)
            )
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_modifier_profile_recommendation(
        run_dir=run_dir,
        repo_root=repo_root,
        config_path=config_path,
    )
    errors = validate_modifier_profile_recommendation_payload(
        payload,
        run_dir=run_dir,
        repo_root=repo_root,
        config_path=config_path,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "modifier profile recommendation failed schema validation: "
            + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def memory_hygiene_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return memory hygiene for one iteration run."""
    run_dir = experiments_dir / run_id
    path = run_dir / "memory_hygiene.json"
    if path.exists():
        payload = load_json(path)
        errors = validate_memory_hygiene_payload(
            payload,
            experiments_dir=experiments_dir,
            repo_root=experiments_dir.parent,
        )
        if errors:
            raise ValueError(
                "memory hygiene failed schema validation: " + "; ".join(errors)
            )
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    manifest = load_json(run_dir / "manifest.json") if (run_dir / "manifest.json").exists() else {}
    memory_policy = (
        manifest.get("memory_filter_policy", {})
        if isinstance(manifest.get("memory_filter_policy", {}), dict)
        else {}
    )
    payload = build_memory_hygiene(
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
        failed_patch_threshold=int(memory_policy.get("failed_patch_threshold", 2)),
        failed_direction_threshold=int(
            memory_policy.get("failed_direction_threshold", 3)
        ),
        created_at_from=str(memory_policy.get("created_at_from", "")),
        recent_record_limit=int(memory_policy.get("recent_record_limit", 0) or 0),
        exclude_run_id=run_id,
    )
    errors = validate_memory_hygiene_payload(
        payload,
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
        failed_patch_threshold=int(memory_policy.get("failed_patch_threshold", 2)),
        failed_direction_threshold=int(
            memory_policy.get("failed_direction_threshold", 3)
        ),
        created_at_from=str(memory_policy.get("created_at_from", "")),
        recent_record_limit=int(memory_policy.get("recent_record_limit", 0) or 0),
        exclude_run_id=run_id,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "memory hygiene failed schema validation: " + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def memory_scope_recommendation_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return memory scope recommendation for one iteration run."""
    run_dir = experiments_dir / run_id
    path = run_dir / "memory_scope_recommendation.json"
    if path.exists():
        payload = load_json(path)
        errors = validate_memory_scope_recommendation_payload(
            payload,
            run_dir=run_dir,
            repo_root=experiments_dir.parent,
            experiments_dir=experiments_dir,
        )
        if errors:
            raise ValueError(
                "memory scope recommendation failed schema validation: "
                + "; ".join(errors)
            )
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_memory_scope_recommendation(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        experiments_dir=experiments_dir,
    )
    errors = validate_memory_scope_recommendation_payload(
        payload,
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        experiments_dir=experiments_dir,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "memory scope recommendation failed schema validation: "
            + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def config_change_candidate_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return config change candidates for one iteration run."""
    run_dir = experiments_dir / run_id
    path = run_dir / "config_change_candidate.json"
    if path.exists():
        payload = load_json(path)
        errors = validate_config_change_candidate_payload(
            payload,
            run_dir=run_dir,
            repo_root=experiments_dir.parent,
            experiments_dir=experiments_dir,
        )
        if errors:
            raise ValueError(
                "config change candidate failed schema validation: "
                + "; ".join(errors)
            )
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_config_change_candidate(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        experiments_dir=experiments_dir,
    )
    errors = validate_config_change_candidate_payload(
        payload,
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        experiments_dir=experiments_dir,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "config change candidate failed schema validation: " + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def operator_config_review_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return operator config review for one iteration run."""
    run_dir = experiments_dir / run_id
    path = run_dir / "operator_config_review.json"
    if path.exists():
        payload = load_json(path)
        errors = validate_operator_config_review_payload(
            payload,
            run_dir=run_dir,
            repo_root=experiments_dir.parent,
            experiments_dir=experiments_dir,
        )
        if errors:
            raise ValueError(
                "operator config review failed schema validation: "
                + "; ".join(errors)
            )
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_operator_config_review(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        experiments_dir=experiments_dir,
    )
    errors = validate_operator_config_review_payload(
        payload,
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        experiments_dir=experiments_dir,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "operator config review failed schema validation: " + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def config_application_dry_run_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    config_path: Path = Path("config/default.json"),
) -> dict[str, object]:
    """Return config application dry run for one iteration run."""
    run_dir = experiments_dir / run_id
    path = run_dir / "config_application_dry_run.json"
    if path.exists():
        payload = load_json(path)
        errors = validate_config_application_dry_run_payload(
            payload,
            run_dir=run_dir,
            repo_root=experiments_dir.parent,
            experiments_dir=experiments_dir,
            config_path=config_path,
        )
        if errors:
            raise ValueError(
                "config application dry run failed schema validation: "
                + "; ".join(errors)
            )
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_config_application_dry_run(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        experiments_dir=experiments_dir,
        config_path=config_path,
    )
    errors = validate_config_application_dry_run_payload(
        payload,
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        experiments_dir=experiments_dir,
        config_path=config_path,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "config application dry run failed schema validation: "
            + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def config_operator_runbook_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return config operator runbook for one iteration run."""
    run_dir = experiments_dir / run_id
    path = run_dir / "config_operator_runbook.json"
    if path.exists():
        payload = load_json(path)
        errors = validate_config_operator_runbook_payload(
            payload,
            run_dir=run_dir,
            repo_root=experiments_dir.parent,
        )
        if errors:
            raise ValueError(
                "config operator runbook failed schema validation: "
                + "; ".join(errors)
            )
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_config_operator_runbook(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
    )
    errors = validate_config_operator_runbook_payload(
        payload,
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "config operator runbook failed schema validation: " + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def config_application_rollback_preview_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    receipt_path: Path | None = None,
    config_path: Path = Path("config/default.json"),
) -> dict[str, object]:
    """Return config application rollback preview for one iteration run."""
    run_dir = experiments_dir / run_id
    path = run_dir / "config_application_rollback_preview.json"
    if path.exists() and receipt_path is None:
        payload = load_json(path)
        from orchestrator.config_application_rollback_preview import (
            validate_config_application_rollback_preview_payload,
        )

        errors = validate_config_application_rollback_preview_payload(
            payload,
            run_id=run_id,
            run_dir=run_dir,
            repo_root=experiments_dir.parent,
            receipt_path=run_dir / "config_application_receipt.json",
            config_path=config_path,
        )
        if errors:
            raise ValueError(
                "config application rollback preview failed schema validation: "
                + "; ".join(errors)
            )
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    from orchestrator.config_application_rollback_preview import (
        build_config_application_rollback_preview,
        validate_config_application_rollback_preview_payload,
    )

    resolved_receipt_path = receipt_path or run_dir / "config_application_receipt.json"
    payload = build_config_application_rollback_preview(
        run_id=run_id,
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        receipt_path=resolved_receipt_path,
        config_path=config_path,
    )
    errors = validate_config_application_rollback_preview_payload(
        payload,
        run_id=run_id,
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        receipt_path=resolved_receipt_path,
        config_path=config_path,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "config application rollback preview failed schema validation: "
            + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def config_lineage_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    config_path: Path = Path("config/default.json"),
) -> dict[str, object]:
    """Return config lineage for one iteration run."""
    run_dir = experiments_dir / run_id
    path = run_dir / "config_lineage.json"
    if path.exists():
        payload = load_json(path)
        from orchestrator.config_lineage import validate_config_lineage_payload

        errors = validate_config_lineage_payload(
            payload,
            run_id=run_id,
            run_dir=run_dir,
            repo_root=experiments_dir.parent,
            config_path=config_path,
        )
        if errors:
            raise ValueError(
                "config lineage failed schema validation: " + "; ".join(errors)
            )
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    from orchestrator.config_lineage import (
        build_config_lineage,
        validate_config_lineage_payload,
    )

    payload = build_config_lineage(
        run_id=run_id,
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        config_path=config_path,
    )
    errors = validate_config_lineage_payload(
        payload,
        run_id=run_id,
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        config_path=config_path,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "config lineage failed schema validation: " + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def operator_run_review(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return the operator dashboard for one iteration run."""
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    closeout_path = run_dir / "run_closeout.json"
    if closeout_path.exists():
        closeout = load_json(closeout_path)
        from_artifact = True
    else:
        if not (run_dir / "manifest.json").exists():
            raise FileNotFoundError(f"Iteration manifest not found for run: {run_id}")
        closeout = build_run_closeout(
            run_dir=run_dir,
            experiments_dir=experiments_dir,
            repo_root=experiments_dir.parent,
        )
        from_artifact = False
    dashboard = dict_payload(closeout.get("operator_dashboard", {}))
    summary = dict_payload(closeout.get("summary", {}))
    payload = {
        "schema_version": "operator_run_review_v1",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "from_artifact": from_artifact,
        "closeout_path": str(closeout_path),
        "closeout_markdown_path": str(run_dir / "run_closeout.md"),
        "run_status": str(closeout.get("status", "unknown")),
        "closeout_status": str(closeout.get("closeout_status", "unknown")),
        "closeout_ok": bool(closeout.get("ok", False)),
        "summary": {
            "completed_rounds": int(summary.get("completed_rounds", 0) or 0),
            "accepted_round": summary.get("accepted_round"),
            "stop_reason": summary.get("stop_reason"),
            "config_lineage_status": str(
                summary.get("config_lineage_status", "unknown")
            ),
            "research_primary_focus": str(
                summary.get("research_primary_focus", "unknown")
            ),
        },
        "dashboard": dashboard,
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_write_config": True,
            "does_not_promote_champion": True,
            "does_not_apply_patches": True,
            "does_not_route_agents": True,
            "does_not_change_acceptance": True,
        },
    }
    errors = validate_operator_run_review_payload(
        payload,
        repo_root=experiments_dir.parent,
    )
    if errors:
        raise ValueError(
            "operator run review failed schema validation: " + "; ".join(errors)
        )
    return payload


def render_operator_run_review_markdown(payload: dict[str, object]) -> str:
    """Render an operator run review payload as compact markdown."""
    dashboard = dict_payload(payload.get("dashboard", {}))
    status_summary = dict_payload(dashboard.get("status_summary", {}))
    config_review = dict_payload(dashboard.get("config_review", {}))
    champion_review = dict_payload(dashboard.get("champion_review", {}))
    quality_review = dict_payload(dashboard.get("candidate_quality_review", {}))
    watchlist = dict_payload(dashboard.get("watchlist", {}))
    lines = [
        "# Operator Run Review",
        "",
        f"- Run id: `{markdown_cell(payload.get('run_id', ''))}`",
        f"- Run status: `{markdown_cell(payload.get('run_status', 'unknown'))}`",
        f"- Closeout status: `{markdown_cell(payload.get('closeout_status', 'unknown'))}`",
        f"- Closeout OK: `{payload.get('closeout_ok', False)}`",
        f"- Completed rounds: `{status_summary.get('completed_rounds', 0)}`",
        f"- Stop reason: `{markdown_cell(status_summary.get('stop_reason', ''))}`",
        "",
        "## Config",
        "",
        f"- Lineage status: `{markdown_cell(config_review.get('lineage_status', 'unknown'))}`",
        f"- Existing stages: `{config_review.get('existing_stage_count', 0)}`",
        "- Current config matches latest stage: "
        f"`{config_review.get('current_config_matches_latest_stage', False)}`",
        "",
        "## Champion",
        "",
        f"- Challenger status: `{markdown_cell(champion_review.get('challenger_status', 'unknown'))}`",
        f"- Promotion approval: `{markdown_cell(champion_review.get('approval_status', 'unknown'))}`",
        f"- Would promote: `{champion_review.get('would_promote', False)}`",
        "",
        "## Candidate Quality",
        "",
        f"- Trace present: `{quality_review.get('trace_present', False)}`",
        f"- Candidates: `{quality_review.get('candidate_count', 0)}`",
        f"- Selectable: `{quality_review.get('selectable_count', 0)}`",
        f"- Top failure: `{markdown_cell(quality_review.get('top_failure_code', ''))}`",
        f"- Source: `{markdown_cell(quality_review.get('source_path', ''))}`",
        "",
        "## Watchlist",
        "",
        f"- Status: `{markdown_cell(watchlist.get('status', 'unknown'))}`",
        f"- Alerts: `{watchlist.get('alert_count', 0)}`",
        "",
        "## Gates",
        "",
        "| Gate | OK | Status | Artifact |",
        "| --- | --- | --- | --- |",
    ]
    for row in list_payload(dashboard.get("gates", [])):
        lines.append(
            "| "
            f"{markdown_cell(row.get('gate_name', ''))} | "
            f"{row.get('ok', False)} | "
            f"{markdown_cell(row.get('status', ''))} | "
            f"`{markdown_cell(row.get('artifact_path', ''))}` |"
        )
    lines.extend(["", "## Action Items", ""])
    raw_action_items = dashboard.get("operator_action_items", [])
    action_items = (
        [str(item) for item in raw_action_items]
        if isinstance(raw_action_items, list)
        else []
    )
    lines.extend([f"- {markdown_cell(item)}" for item in action_items] or ["- none"])
    lines.extend(
        [
            "",
            "## Authority",
            "",
            "- Final acceptance authority: `deterministic_code`",
            "- Executes agents: `False`",
            "- Writes config: `False`",
            "- Promotes champion: `False`",
            "",
        ]
    )
    return "\n".join(lines)


def validate_operator_run_review_payload(
    payload: dict[str, object],
    *,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate an in-memory operator run review payload."""
    schema = load_schema(repo_root / OPERATOR_RUN_REVIEW_SCHEMA_PATH)
    errors = list(validate_json_payload(payload=payload, schema=schema))
    errors.extend(validate_operator_run_review_consistency(payload))
    return tuple(errors)


def validate_operator_run_review_consistency(
    payload: dict[str, object],
) -> tuple[str, ...]:
    """Validate copied run-review summaries match the embedded dashboard."""
    errors: list[str] = []
    dashboard = dict_payload(payload.get("dashboard", {}))
    status_summary = dict_payload(dashboard.get("status_summary", {}))
    summary = dict_payload(payload.get("summary", {}))
    config_review = dict_payload(dashboard.get("config_review", {}))

    def scalar_equal(left: object, right: object) -> bool:
        if left is None or right is None:
            return left is right
        return str(left) == str(right)

    summary_pairs = (
        (
            "run_status",
            payload.get("run_status", ""),
            status_summary.get("run_status", ""),
        ),
        (
            "closeout_status",
            payload.get("closeout_status", ""),
            status_summary.get("closeout_status", ""),
        ),
        (
            "completed_rounds",
            summary.get("completed_rounds", 0),
            status_summary.get("completed_rounds", 0),
        ),
        (
            "accepted_round",
            summary.get("accepted_round"),
            status_summary.get("accepted_round"),
        ),
        (
            "stop_reason",
            summary.get("stop_reason"),
            status_summary.get("stop_reason"),
        ),
        (
            "config_lineage_status",
            summary.get("config_lineage_status", ""),
            config_review.get("lineage_status", ""),
        ),
    )
    for key, left, right in summary_pairs:
        if not scalar_equal(left, right):
            errors.append(f"operator_run_review summary {key} mismatch")
    errors.extend(validate_operator_run_review_dashboard(payload=payload))
    return tuple(errors)


def validate_operator_run_review_dashboard(
    *,
    payload: dict[str, object],
) -> tuple[str, ...]:
    """Validate embedded operator dashboard fields remain read-only and bound."""
    errors: list[str] = []
    dashboard = dict_payload(payload.get("dashboard", {}))
    status_summary = dict_payload(dashboard.get("status_summary", {}))
    config_review = dict_payload(dashboard.get("config_review", {}))
    champion_review = dict_payload(dashboard.get("champion_review", {}))
    quality_review = dict_payload(dashboard.get("candidate_quality_review", {}))
    watchlist = dict_payload(dashboard.get("watchlist", {}))
    gates = list_payload(dashboard.get("gates", []))
    gates_by_name = {str(row.get("gate_name", "")): row for row in gates}

    expected_gate_order = [
        "artifact_health",
        "scope_health",
        "config_lineage",
        "candidate_quality_trace",
        "champion_review",
        "promotion_review",
    ]
    if [str(row.get("gate_name", "")) for row in gates] != expected_gate_order:
        errors.append("operator_run_review dashboard gate order mismatch")
    for row in gates:
        if not str(row.get("artifact_path", "")):
            errors.append("operator_run_review dashboard gate artifact missing")
        if not str(row.get("details", "")):
            errors.append("operator_run_review dashboard gate details missing")

    artifact_gate = gates_by_name.get("artifact_health", {})
    if bool(artifact_gate.get("ok", False)) != bool(payload.get("closeout_ok", False)):
        errors.append("operator_run_review dashboard artifact gate ok mismatch")
    if str(artifact_gate.get("status", "")) != str(
        payload.get("closeout_status", "")
    ):
        errors.append("operator_run_review dashboard artifact gate status mismatch")

    config_gate = gates_by_name.get("config_lineage", {})
    if bool(config_gate.get("ok", False)) != bool(
        config_review.get("lineage_ok", False)
    ):
        errors.append("operator_run_review dashboard config gate ok mismatch")
    if str(config_gate.get("status", "")) != str(
        config_review.get("lineage_status", "")
    ):
        errors.append("operator_run_review dashboard config gate status mismatch")

    champion_gate = gates_by_name.get("champion_review", {})
    if str(champion_gate.get("status", "")) != str(
        champion_review.get("challenger_status", "")
    ):
        errors.append("operator_run_review dashboard champion gate status mismatch")

    quality_gate = gates_by_name.get("candidate_quality_trace", {})
    if bool(quality_gate.get("ok", False)) != bool(
        quality_review.get("trace_present", False)
    ):
        errors.append("operator_run_review dashboard quality gate ok mismatch")
    if str(quality_gate.get("status", "")) != (
        "present" if quality_review.get("trace_present") is True else "missing"
    ):
        errors.append("operator_run_review dashboard quality gate status mismatch")

    promotion_gate = gates_by_name.get("promotion_review", {})
    if str(promotion_gate.get("status", "")) != str(
        champion_review.get("approval_status", "")
    ):
        errors.append("operator_run_review dashboard promotion gate status mismatch")

    if int_value(status_summary.get("selected_candidate_count", -1)) < 0:
        errors.append("operator_run_review dashboard selected count negative")
    if int_value(quality_review.get("candidate_count", -1)) < 0:
        errors.append("operator_run_review dashboard quality candidate count negative")
    if int_value(quality_review.get("selectable_count", -1)) < 0:
        errors.append("operator_run_review dashboard quality selectable count negative")
    if int_value(watchlist.get("alert_count", -1)) < 0:
        errors.append("operator_run_review dashboard watchlist alert count negative")
    if status_summary.get("accepted") is True and str(
        status_summary.get("run_status", "")
    ) != "accepted":
        errors.append("operator_run_review dashboard accepted status mismatch")
    if status_summary.get("accepted") is False and str(
        status_summary.get("run_status", "")
    ) == "accepted":
        errors.append("operator_run_review dashboard rejected status mismatch")

    policy = dict_payload(payload.get("policy", {}))
    dashboard_policy = dict_payload(dashboard.get("policy", {}))
    if policy != dashboard_policy:
        errors.append("operator_run_review dashboard policy mismatch")
    for key, value in policy.items():
        if value is not True:
            errors.append(f"operator_run_review policy false: {key}")

    authority = dict_payload(dashboard.get("authority", {}))
    expected_authority = {
        "final_acceptance_authority": "deterministic_code",
        "agent_language_can_accept": False,
        "config_changes_require_guarded_command": True,
        "champion_promotion_requires_explicit_command": True,
    }
    if authority != expected_authority:
        errors.append("operator_run_review dashboard authority mismatch")
    return tuple(errors)


def operator_action_plan_report(
    *,
    run_id: str | None = None,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return the saved or derived operator action plan for one run."""
    run_id = run_id or latest_iteration_run_id(experiments_dir=experiments_dir)
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    plan_path = run_dir / "operator_action_plan.json"
    if plan_path.exists():
        payload = load_json(plan_path)
        errors = validate_operator_action_plan_payload(
            payload,
            run_dir=run_dir,
            experiments_dir=experiments_dir,
            repo_root=experiments_dir.parent,
        )
        if errors:
            raise ValueError(
                "operator action plan failed schema validation: "
                + "; ".join(errors)
            )
        payload["from_artifact"] = True
        return payload
    if not (run_dir / "run_closeout.json").exists():
        raise FileNotFoundError(f"Run closeout not found for run: {run_id}")
    payload = build_operator_action_plan(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
    )
    errors = validate_operator_action_plan_payload(
        payload,
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "operator action plan failed schema validation: " + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def operator_action_approval_report(
    *,
    run_id: str | None = None,
    experiments_dir: Path = Path("experiments"),
    action_id: str = "",
    command_label: str = "",
) -> dict[str, object]:
    """Return the saved or derived operator action approval for one run."""
    run_id = run_id or latest_iteration_run_id(experiments_dir=experiments_dir)
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    approval_path = run_dir / "operator_action_approval.json"
    if approval_path.exists() and not action_id and not command_label:
        payload = load_json(approval_path)
        errors = validate_operator_action_approval_payload(
            payload,
            run_dir=run_dir,
            repo_root=experiments_dir.parent,
            experiments_dir=experiments_dir,
        )
        if errors:
            raise ValueError(
                "operator action approval failed schema validation: "
                + "; ".join(errors)
            )
        payload["from_artifact"] = True
        return payload
    payload = build_operator_action_approval(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
        action_id=action_id,
        command_label=command_label,
    )
    errors = validate_operator_action_approval_payload(
        payload,
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        experiments_dir=experiments_dir,
        action_id=action_id,
        command_label=command_label,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "operator action approval failed schema validation: "
            + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def operator_action_execution_report(
    *,
    run_id: str | None = None,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return the saved operator action execution receipt for one run."""
    run_id = run_id or latest_iteration_run_id(experiments_dir=experiments_dir)
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    receipt_path = run_dir / "operator_action_execution_receipt.json"
    if not receipt_path.exists():
        raise FileNotFoundError(
            f"Operator action execution receipt not found: {receipt_path}"
        )
    payload = load_json(receipt_path)
    errors = validate_operator_action_execution_receipt_payload(
        payload,
        run_id=run_id,
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
    )
    if errors:
        raise ValueError(
            "operator action execution receipt failed schema validation: "
            + "; ".join(errors)
        )
    payload["from_artifact"] = True
    return payload


def operator_action_audit_report(
    *,
    run_id: str | None = None,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return the saved or derived operator action audit for one run."""
    run_id = run_id or latest_iteration_run_id(experiments_dir=experiments_dir)
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    audit_path = run_dir / "operator_action_audit.json"
    if audit_path.exists():
        payload = load_json(audit_path)
        errors = validate_operator_action_audit_payload(
            payload,
            run_dir=run_dir,
            experiments_dir=experiments_dir,
            repo_root=experiments_dir.parent,
        )
        if errors:
            raise ValueError(
                "operator action audit failed schema validation: "
                + "; ".join(errors)
            )
        payload["from_artifact"] = True
        return payload
    payload = build_operator_action_audit(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
    )
    errors = validate_operator_action_audit_payload(
        payload,
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "operator action audit failed schema validation: " + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def operator_action_dashboard_report(
    *,
    run_id: str | None = None,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return the saved or derived operator action dashboard for one run."""
    run_id = run_id or latest_iteration_run_id(experiments_dir=experiments_dir)
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    dashboard_path = run_dir / "operator_action_dashboard.json"
    if dashboard_path.exists():
        payload = load_json(dashboard_path)
        errors = validate_operator_action_dashboard_payload(
            payload,
            run_dir=run_dir,
            experiments_dir=experiments_dir,
            repo_root=experiments_dir.parent,
        )
        if errors:
            raise ValueError(
                "operator action dashboard failed schema validation: "
                + "; ".join(errors)
            )
        payload["from_artifact"] = True
        return payload
    payload = build_operator_action_dashboard(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
    )
    errors = validate_operator_action_dashboard_payload(
        payload,
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "operator action dashboard failed schema validation: "
            + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def operator_action_guide_report(
    *,
    run_id: str | None = None,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return the terminal-only operator action guide for one run."""
    run_id = run_id or latest_iteration_run_id(experiments_dir=experiments_dir)
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_operator_action_guide(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
    )
    errors = validate_operator_action_guide_payload(
        payload,
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "operator action guide failed schema validation: " + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def operator_cockpit_report(
    *,
    run_id: str | None = None,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return the saved or derived operator cockpit for one run."""
    run_id = run_id or latest_iteration_run_id(experiments_dir=experiments_dir)
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    cockpit_path = run_dir / "operator_cockpit.json"
    if cockpit_path.exists():
        payload = load_json(cockpit_path)
        errors = validate_operator_cockpit_payload(
            payload,
            run_dir=run_dir,
            experiments_dir=experiments_dir,
            repo_root=experiments_dir.parent,
        )
        if errors:
            raise ValueError(
                "operator cockpit failed schema validation: " + "; ".join(errors)
            )
        payload["from_artifact"] = True
        return annotate_snapshot_freshness(
            payload,
            repo_root=experiments_dir.parent,
        )
    payload = build_operator_cockpit(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
    )
    errors = validate_operator_cockpit_payload(
        payload,
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "operator cockpit failed schema validation: " + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return annotate_snapshot_freshness(
        payload,
        repo_root=experiments_dir.parent,
    )


def operator_home_report(
    *,
    run_id: str | None = None,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return the terminal-only operator home for one run."""
    run_id = run_id or latest_iteration_run_id(experiments_dir=experiments_dir)
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_operator_home(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
    )
    errors = validate_operator_home_payload(
        payload,
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "operator home failed schema validation: " + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def refresh_operator_views(
    *,
    run_id: str | None = None,
    experiments_dir: Path = Path("experiments"),
    config_path: Path | None = None,
) -> dict[str, object]:
    """Refresh source-hash-bound operator views in deterministic order."""
    experiments_dir = experiments_dir.resolve()
    run_id = run_id or latest_iteration_run_id(experiments_dir=experiments_dir)
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    repo_root = experiments_dir.parent
    active_config_path, config_source = refresh_config_path(
        config_path=config_path,
        run_dir=run_dir,
        repo_root=repo_root,
    )
    active_config = load_project_config(repo_root, active_config_path)
    config_record = refresh_config_record(
        active_config_path,
        repo_root=repo_root,
        source=config_source,
        metadata_path=run_dir / "run_metadata.json",
    )
    pre_refresh_cockpit = operator_cockpit_report(
        run_id=run_id,
        experiments_dir=experiments_dir,
    )
    pre_refresh_freshness = dict_payload(
        pre_refresh_cockpit.get("snapshot_freshness", {})
    )
    pre_refresh_blockers = string_payload(pre_refresh_cockpit.get("blockers", []))
    refreshed: list[dict[str, object]] = []
    for artifact_name, writer in (
        (
            "operator_action_dashboard",
            lambda: write_operator_action_dashboard(
                run_dir=run_dir,
                experiments_dir=experiments_dir,
                repo_root=repo_root,
            ),
        ),
        (
            "codex_cli_execution_preflight",
            lambda: (
                run_dir / "codex_cli_execution_preflight.json",
                run_dir / "codex_cli_execution_preflight.md",
                write_codex_cli_execution_preflight(
                    output_path=run_dir / "codex_cli_execution_preflight.json",
                    markdown_path=run_dir / "codex_cli_execution_preflight.md",
                    run_dir=run_dir,
                    config=active_config,
                    repo_root=repo_root,
                ),
            ),
        ),
        (
            "operator_unlock_checklist",
            lambda: write_operator_unlock_checklist(
                run_dir=run_dir,
                repo_root=repo_root,
            ),
        ),
        (
            "codex_cli_unlock_runbook",
            lambda: write_codex_cli_unlock_runbook(
                run_dir=run_dir,
                repo_root=repo_root,
            ),
        ),
        (
            "codex_cli_execution_readiness_diff",
            lambda: write_codex_cli_execution_readiness_diff(
                run_dir=run_dir,
                repo_root=repo_root,
                config_path=active_config_path,
            ),
        ),
        (
            "operator_cockpit",
            lambda: write_operator_cockpit(
                run_dir=run_dir,
                experiments_dir=experiments_dir,
                repo_root=repo_root,
            ),
        ),
    ):
        json_path, md_path, payload = writer()
        refreshed.append(
            {
                "artifact_name": artifact_name,
                "json_path": str(json_path),
                "markdown_path": str(md_path),
                "json_file": refresh_file_record(json_path, repo_root=repo_root),
                "markdown_file": refresh_file_record(md_path, repo_root=repo_root),
                "schema_version": str(payload.get("schema_version", "")),
            }
        )
    cockpit = operator_cockpit_report(
        run_id=run_id,
        experiments_dir=experiments_dir,
    )
    home = build_operator_home(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    operator_summary = operator_view_refresh_summary(cockpit)
    home_summary = operator_view_refresh_home_summary(
        home=home,
        run_id=run_id,
    )
    blocker_delta = operator_view_refresh_blocker_delta(
        before=pre_refresh_blockers,
        after=string_payload(cockpit.get("blockers", [])),
    )
    post_refresh_freshness = dict_payload(cockpit.get("snapshot_freshness", {}))
    policy = {
        "writes_existing_read_only_operator_artifacts": True,
        "does_not_record_approval": True,
        "does_not_execute_commands": True,
        "does_not_execute_codex_cli": True,
        "does_not_execute_agents": True,
        "does_not_run_backtests": True,
        "does_not_write_config": True,
        "does_not_promote_champion": True,
        "does_not_apply_patches": True,
        "does_not_route_agents": True,
        "does_not_change_acceptance": True,
    }
    policy_summary = operator_view_refresh_policy_summary(policy)
    refresh_effect = operator_view_refresh_effect(
        pre_refresh_freshness=pre_refresh_freshness,
        post_refresh_freshness=post_refresh_freshness,
        blocker_delta=blocker_delta,
        policy_summary=policy_summary,
        operator_summary=operator_summary,
    )
    review_summary = operator_view_refresh_review_summary(
        refresh_effect=refresh_effect,
        operator_summary=operator_summary,
        post_refresh_freshness=post_refresh_freshness,
        policy_summary=policy_summary,
    )
    payload = {
        "schema_version": "operator_view_refresh_v1",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "config_path": str(active_config_path),
        "config_source": config_source,
        "config_path_exists": bool(config_record["exists"]),
        "config_sha256": str(config_record["sha256"]),
        "config_record": config_record,
        "pre_refresh_snapshot_freshness": pre_refresh_freshness,
        "refreshed_count": len(refreshed),
        "refreshed_artifacts": refreshed,
        "operator_summary": operator_summary,
        "home_summary": home_summary,
        "blocker_delta": blocker_delta,
        "refresh_effect": refresh_effect,
        "review_summary": review_summary,
        "cockpit_snapshot_freshness": post_refresh_freshness,
        "policy": policy,
        "policy_summary": policy_summary,
    }
    errors = validate_operator_view_refresh_payload(payload, repo_root=repo_root)
    if errors:
        raise ValueError(
            "operator view refresh failed schema validation: " + "; ".join(errors)
        )
    return payload


def operator_view_refresh_summary(cockpit: dict[str, object]) -> dict[str, object]:
    """Return the next operator-facing checkpoint after refreshing views."""
    next_command = operator_view_refresh_next_command(cockpit)
    blockers = string_payload(cockpit.get("blockers", []))
    digest = dict_payload(cockpit.get("operator_digest", {}))
    digest_boundary = dict_payload(digest.get("recommended_command_boundary", {}))
    next_command_boundary = dict_payload(next_command.get("boundary", {}))
    cockpit_summary = dict_payload(cockpit.get("summary", {}))
    return {
        "cockpit_status": str(cockpit.get("status", "")),
        "cockpit_ok": bool(cockpit.get("ok", False)),
        "primary_focus": str(cockpit.get("primary_focus", "")),
        "action_execution_readiness_status": str(
            cockpit_summary.get("action_execution_readiness_status", "")
        ),
        "action_execution_ready": bool(
            cockpit_summary.get("action_execution_ready", False)
        ),
        "action_execution_next_command_boundary": str(
            cockpit_summary.get("action_execution_next_command_boundary", "")
        ),
        "action_execution_missing_artifact_count": int(
            cockpit_summary.get("action_execution_missing_artifact_count", 0) or 0
        ),
        "action_path_closure_status": str(
            cockpit_summary.get("action_path_closure_status", "")
        ),
        "action_path_closed": bool(cockpit_summary.get("action_path_closed", False)),
        "action_path_completed_step_count": int(
            cockpit_summary.get("action_path_completed_step_count", 0) or 0
        ),
        "action_path_required_step_count": int(
            cockpit_summary.get("action_path_required_step_count", 0) or 0
        ),
        "operator_digest_headline": str(digest.get("headline", "")),
        "operator_digest_priority": str(digest.get("priority", "")),
        "operator_digest_primary_reason": str(digest.get("primary_reason", "")),
        "operator_digest_target_panel_id": str(digest.get("target_panel_id", "")),
        "operator_digest_target_panel_title": str(
            digest.get("target_panel_title", "")
        ),
        "operator_digest_target_panel_status": str(
            digest.get("target_panel_status", "")
        ),
        "operator_digest_next_step": str(digest.get("next_step", "")),
        "operator_digest_recommended_command_boundary": str(
            digest_boundary.get("boundary_type", "")
        ),
        "blocker_count": len(blockers),
        "primary_blocker": blockers[0] if blockers else "",
        "blocker_preview": blockers[:5],
        "next_command_source": str(next_command.get("source", "")),
        "next_command_label": str(next_command.get("label", "")),
        "next_command": str(next_command.get("command", "")),
        "next_command_reason": str(next_command.get("reason", "")),
        "next_command_boundary": str(next_command_boundary.get("boundary_type", "")),
    }


def operator_view_refresh_home_summary(
    *,
    home: dict[str, object],
    run_id: str,
) -> dict[str, object]:
    """Return the terminal-home navigation summary after refreshing views."""
    action_home = dict_payload(home.get("action_home", {}))
    codex_home = dict_payload(home.get("codex_home", {}))
    next_command = dict_payload(home.get("next_command", {}))
    next_boundary = dict_payload(next_command.get("boundary", {}))
    return {
        "schema_version": "operator_view_refresh_home_summary_v1",
        "status": str(home.get("status", "")),
        "ok": bool(home.get("ok", False)),
        "headline": str(home.get("headline", "")),
        "primary_focus": str(home.get("primary_focus", "")),
        "action_step": str(action_home.get("active_step_id", "")),
        "action_guide_status": str(action_home.get("guide_status", "")),
        "codex_preflight_status": str(codex_home.get("preflight_status", "")),
        "codex_unlock_runbook_status": str(
            codex_home.get("unlock_runbook_status", "")
        ),
        "codex_unlock_runbook_ready": bool(
            codex_home.get("unlock_runbook_ready", False)
        ),
        "codex_unlock_runbook_blocked_step_count": int(
            codex_home.get("unlock_runbook_blocked_step_count", 0) or 0
        ),
        "codex_unlock_runbook_command_label": str(
            codex_home.get("runbook_command_label", "")
        ),
        "codex_unlock_runbook_command": str(codex_home.get("runbook_command", "")),
        "codex_readiness_diff_status": str(
            codex_home.get("readiness_diff_status", "")
        ),
        "codex_intake_readiness_status": str(
            codex_home.get("intake_readiness_status", "")
        ),
        "codex_intake_ready": bool(codex_home.get("intake_ready", False)),
        "codex_intake_blocker_count": int(
            codex_home.get("intake_blocker_count", 0) or 0
        ),
        "next_command_label": str(next_command.get("label", "")),
        "next_command": str(next_command.get("command", "")),
        "next_command_status": str(action_home.get("next_command_status", "")),
        "next_command_blocked": bool(action_home.get("next_command_blocked", False)),
        "next_command_blocker_count": int(
            action_home.get("next_command_blocker_count", 0) or 0
        ),
        "next_command_operator_hint": str(
            action_home.get("next_command_operator_hint", "")
        ),
        "next_command_boundary": str(next_boundary.get("boundary_type", "")),
        "next_command_writes_artifact": str(
            next_command.get("writes_artifact", "")
        ),
        "next_command_requires_explicit_operator_invocation": bool(
            next_command.get("requires_explicit_operator_invocation", False)
        ),
        "next_command_requires_operator_approval": bool(
            next_command.get("requires_operator_approval", False)
        ),
        "next_command_records_operator_approval": bool(
            next_command.get("records_operator_approval", False)
        ),
        "next_command_uses_guarded_executor": bool(
            next_command.get("uses_guarded_executor", False)
        ),
        "next_command_is_hint_only": bool(
            next_command.get("command_is_hint_only", False)
        ),
        "home_command_label": "review_operator_home",
        "home_command": (
            f"python -m orchestrator.experiments home {run_id} --markdown"
        ),
        "home_command_boundary": "read_only_inspection",
        "home_command_is_hint_only": True,
    }


def operator_view_refresh_next_command(
    cockpit: dict[str, object],
) -> dict[str, object]:
    """Return the cockpit digest command, falling back to priority and hints."""
    digest = dict_payload(cockpit.get("operator_digest", {}))
    digest_label = str(digest.get("recommended_command_label", ""))
    digest_command = str(digest.get("recommended_command", ""))
    digest_reason = str(digest.get("next_step", "")) or str(
        digest.get("headline", "")
    )
    if digest_label and digest_command:
        return {
            "source": "operator_digest",
            "label": digest_label,
            "command": digest_command,
            "writes_artifact": "",
            "reason": digest_reason,
            "boundary": dict_payload(digest.get("recommended_command_boundary", {})),
        }

    priority = dict_payload(cockpit.get("review_priority", {}))
    priority_label = str(priority.get("recommended_command_label", ""))
    priority_command = str(priority.get("recommended_command", ""))
    priority_reason = str(priority.get("recommended_command_reason", ""))
    priority_writes = str(priority.get("recommended_command_writes_artifact", ""))
    if priority_label and priority_command:
        return {
            "source": "review_priority",
            "label": priority_label,
            "command": priority_command,
            "writes_artifact": priority_writes,
            "reason": priority_reason,
            "boundary": dict_payload(
                priority.get("recommended_command_boundary", {})
            ),
        }

    commands = list_payload(cockpit.get("recommended_commands", []))
    if commands:
        command = dict(commands[0])
        command["source"] = "recommended_commands_fallback"
        return command
    return {"source": "none"}


def operator_view_refresh_blocker_delta(
    *,
    before: list[str],
    after: list[str],
) -> dict[str, object]:
    """Return blocker changes caused by refreshing operator views."""
    before_set = set(before)
    after_set = set(after)
    added = [blocker for blocker in after if blocker not in before_set]
    removed = [blocker for blocker in before if blocker not in after_set]
    persisted = [blocker for blocker in after if blocker in before_set]
    return {
        "schema_version": "operator_view_refresh_blocker_delta_v1",
        "changed": bool(added or removed),
        "before_count": len(before),
        "after_count": len(after),
        "added_count": len(added),
        "removed_count": len(removed),
        "persisted_count": len(persisted),
        "added_blockers": added,
        "removed_blockers": removed,
        "persisted_blocker_preview": persisted[:5],
    }


def operator_view_refresh_effect(
    *,
    pre_refresh_freshness: dict[str, object],
    post_refresh_freshness: dict[str, object],
    blocker_delta: dict[str, object],
    policy_summary: dict[str, object],
    operator_summary: dict[str, object],
) -> dict[str, object]:
    """Return a compact operator-facing summary of refresh impact."""
    pre_stale_count = int(pre_refresh_freshness.get("stale_count", 0) or 0)
    post_stale_count = int(post_refresh_freshness.get("stale_count", 0) or 0)
    post_blocker_count = int(operator_summary.get("blocker_count", 0) or 0)
    stale_sources_fixed = pre_stale_count > 0 and post_stale_count == 0
    blockers_changed = bool(blocker_delta.get("changed", False))
    safety_policy_ok = bool(policy_summary.get("ok", False))
    freshness_ok = bool(post_refresh_freshness.get("ok", False))
    cockpit_ok = bool(operator_summary.get("cockpit_ok", False))
    operator_review_required = bool(
        not safety_policy_ok or not freshness_ok or not cockpit_ok or post_blocker_count
    )
    if not safety_policy_ok:
        status = "safety_policy_attention"
        summary = "Refresh completed, but the safety policy summary needs review."
    elif not freshness_ok or post_stale_count:
        status = "refresh_incomplete"
        summary = "Refresh completed, but some cockpit sources are still stale."
    elif stale_sources_fixed and blockers_changed:
        status = "stale_sources_fixed_blockers_changed"
        summary = "Refresh fixed stale sources and changed the blocker set."
    elif stale_sources_fixed:
        status = "stale_sources_fixed"
        summary = "Refresh fixed stale cockpit sources."
    elif blockers_changed:
        status = "blockers_changed"
        summary = "Refresh changed the blocker set."
    else:
        status = "refreshed_no_changes"
        summary = "Refresh completed with no stale-source or blocker changes."
    return {
        "schema_version": "operator_view_refresh_effect_v1",
        "status": status,
        "summary": summary,
        "stale_sources_fixed": stale_sources_fixed,
        "pre_stale_count": pre_stale_count,
        "post_stale_count": post_stale_count,
        "post_blocker_count": post_blocker_count,
        "blockers_changed": blockers_changed,
        "safety_policy_ok": safety_policy_ok,
        "operator_review_required": operator_review_required,
    }


def operator_view_refresh_review_summary(
    *,
    refresh_effect: dict[str, object],
    operator_summary: dict[str, object],
    post_refresh_freshness: dict[str, object],
    policy_summary: dict[str, object],
) -> dict[str, object]:
    """Return deterministic reason codes for post-refresh operator review."""
    reason_codes: list[str] = []
    post_stale_count = int(post_refresh_freshness.get("stale_count", 0) or 0)
    post_blocker_count = int(refresh_effect.get("post_blocker_count", 0) or 0)
    if not bool(policy_summary.get("ok", False)):
        reason_codes.append("safety_policy_attention")
    if not bool(post_refresh_freshness.get("ok", False)) or post_stale_count:
        reason_codes.append("stale_sources_remaining")
    if not bool(operator_summary.get("cockpit_ok", False)):
        reason_codes.append("cockpit_not_ok")
    if post_blocker_count:
        reason_codes.append("blockers_present")
    required = bool(reason_codes)
    return {
        "schema_version": "operator_view_refresh_review_summary_v1",
        "required": required,
        "primary_reason": reason_codes[0] if reason_codes else "",
        "reason_count": len(reason_codes),
        "reason_codes": reason_codes,
        "primary_blocker": str(operator_summary.get("primary_blocker", "")),
        "post_blocker_count": post_blocker_count,
        "next_command_source": str(operator_summary.get("next_command_source", "")),
        "next_command_label": str(operator_summary.get("next_command_label", "")),
        "next_command": str(operator_summary.get("next_command", "")),
        "next_command_reason": str(operator_summary.get("next_command_reason", "")),
        "next_command_boundary": str(
            operator_summary.get("next_command_boundary", "")
        ),
    }


def operator_view_refresh_policy_summary(
    policy: dict[str, bool],
) -> dict[str, object]:
    """Return a compact safety-policy summary for a refresh receipt."""
    false_keys = [key for key in sorted(policy) if policy.get(key) is not True]
    return {
        "ok": not false_keys,
        "true_count": len(policy) - len(false_keys),
        "false_count": len(false_keys),
        "false_keys": false_keys,
    }


def validate_operator_view_refresh_payload(
    payload: dict[str, object],
    *,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate an in-memory operator view refresh receipt payload."""
    schema = load_schema(repo_root / OPERATOR_VIEW_REFRESH_SCHEMA_PATH)
    errors = list(validate_json_payload(payload=payload, schema=schema))
    errors.extend(validate_operator_view_refresh_consistency(payload))
    return tuple(errors)


def validate_operator_view_refresh_consistency(
    payload: dict[str, object],
) -> tuple[str, ...]:
    """Validate derived refresh summaries remain internally consistent."""
    def int_value(value: object, default: int = -1) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    errors: list[str] = []
    refreshed_artifacts = list_payload(payload.get("refreshed_artifacts", []))
    if int_value(payload.get("refreshed_count", -1)) != len(refreshed_artifacts):
        errors.append("operator_view_refresh refreshed_count mismatch")
    expected_artifact_order = [
        "operator_action_dashboard",
        "codex_cli_execution_preflight",
        "operator_unlock_checklist",
        "codex_cli_unlock_runbook",
        "codex_cli_execution_readiness_diff",
        "operator_cockpit",
    ]
    artifact_order = [str(row.get("artifact_name", "")) for row in refreshed_artifacts]
    if artifact_order != expected_artifact_order:
        errors.append("operator_view_refresh refreshed artifact order mismatch")
    for row in refreshed_artifacts:
        artifact_name = str(row.get("artifact_name", ""))
        json_file = dict_payload(row.get("json_file", {}))
        markdown_file = dict_payload(row.get("markdown_file", {}))
        if str(row.get("json_path", "")) != str(json_file.get("path", "")):
            errors.append(
                f"operator_view_refresh refreshed json path mismatch: {artifact_name}"
            )
        if str(row.get("markdown_path", "")) != str(markdown_file.get("path", "")):
            errors.append(
                "operator_view_refresh refreshed markdown path mismatch: "
                f"{artifact_name}"
            )

    operator_summary = dict_payload(payload.get("operator_summary", {}))
    home_summary = dict_payload(payload.get("home_summary", {}))
    blocker_delta = dict_payload(payload.get("blocker_delta", {}))
    if int_value(operator_summary.get("blocker_count", -1)) != int_value(
        blocker_delta.get("after_count", -2)
    ):
        errors.append("operator_view_refresh operator_summary blocker_count mismatch")
    blocker_preview = string_payload(operator_summary.get("blocker_preview", []))
    primary_blocker = str(operator_summary.get("primary_blocker", ""))
    if int_value(operator_summary.get("blocker_count", -1)) == 0:
        if primary_blocker or blocker_preview:
            errors.append("operator_view_refresh operator_summary blocker mismatch")
    elif not blocker_preview or primary_blocker != blocker_preview[0]:
        errors.append("operator_view_refresh operator_summary primary_blocker mismatch")
    if str(operator_summary.get("next_command_source", "")) == "operator_digest":
        digest_next_step = str(operator_summary.get("operator_digest_next_step", ""))
        digest_boundary = str(
            operator_summary.get("operator_digest_recommended_command_boundary", "")
        )
        if not str(operator_summary.get("operator_digest_headline", "")):
            errors.append("operator_view_refresh operator_summary digest missing")
        if (
            digest_next_step
            and str(operator_summary.get("next_command_reason", ""))
            != digest_next_step
        ):
            errors.append(
                "operator_view_refresh operator_summary digest reason mismatch"
            )
        if digest_boundary and (
            str(operator_summary.get("next_command_boundary", ""))
            != digest_boundary
        ):
            errors.append(
                "operator_view_refresh operator_summary digest boundary mismatch"
            )
    run_id = str(payload.get("run_id", ""))
    expected_home_command = (
        f"python -m orchestrator.experiments home {run_id} --markdown"
    )
    if str(home_summary.get("schema_version", "")) != (
        "operator_view_refresh_home_summary_v1"
    ):
        errors.append("operator_view_refresh home_summary schema_version mismatch")
    if str(home_summary.get("primary_focus", "")) != str(
        operator_summary.get("primary_focus", "")
    ):
        errors.append("operator_view_refresh home_summary primary_focus mismatch")
    if str(home_summary.get("home_command_label", "")) != "review_operator_home":
        errors.append("operator_view_refresh home_summary command label mismatch")
    if str(home_summary.get("home_command", "")) != expected_home_command:
        errors.append("operator_view_refresh home_summary command mismatch")
    if str(home_summary.get("home_command_boundary", "")) != "read_only_inspection":
        errors.append("operator_view_refresh home_summary boundary mismatch")
    if bool(home_summary.get("home_command_is_hint_only", False)) is not True:
        errors.append("operator_view_refresh home_summary hint-only mismatch")
    if int_value(home_summary.get("next_command_blocker_count", -1)) < 0:
        errors.append("operator_view_refresh home_summary blocker count mismatch")
    if str(home_summary.get("next_command_label", "")):
        if not str(home_summary.get("next_command", "")):
            errors.append("operator_view_refresh home_summary next command missing")
        if not str(home_summary.get("next_command_boundary", "")):
            errors.append("operator_view_refresh home_summary next boundary missing")
    if bool(home_summary.get("next_command_blocked", False)) and (
        int_value(home_summary.get("next_command_blocker_count", 0)) < 1
        and str(home_summary.get("next_command_status", "")) != "unavailable"
    ):
        errors.append("operator_view_refresh home_summary blocked-state mismatch")
    if int_value(home_summary.get("codex_unlock_runbook_blocked_step_count", -1)) < 0:
        errors.append("operator_view_refresh home_summary runbook blocker mismatch")

    added_blockers = string_payload(blocker_delta.get("added_blockers", []))
    removed_blockers = string_payload(blocker_delta.get("removed_blockers", []))
    if int_value(blocker_delta.get("added_count", -1)) != len(added_blockers):
        errors.append("operator_view_refresh blocker_delta added_count mismatch")
    if int_value(blocker_delta.get("removed_count", -1)) != len(removed_blockers):
        errors.append("operator_view_refresh blocker_delta removed_count mismatch")
    persisted_count = int_value(blocker_delta.get("persisted_count", -1))
    if int_value(blocker_delta.get("before_count", -1)) != (
        persisted_count + len(removed_blockers)
    ):
        errors.append("operator_view_refresh blocker_delta before_count mismatch")
    if int_value(blocker_delta.get("after_count", -1)) != (
        persisted_count + len(added_blockers)
    ):
        errors.append("operator_view_refresh blocker_delta after_count mismatch")
    if bool(blocker_delta.get("changed", False)) != bool(
        added_blockers or removed_blockers
    ):
        errors.append("operator_view_refresh blocker_delta changed mismatch")

    policy = dict_payload(payload.get("policy", {}))
    policy_summary = dict_payload(payload.get("policy_summary", {}))
    expected_policy_summary = operator_view_refresh_policy_summary(
        {str(key): value is True for key, value in policy.items()}
    )
    if policy_summary != expected_policy_summary:
        errors.append("operator_view_refresh policy_summary mismatch")

    refresh_effect = dict_payload(payload.get("refresh_effect", {}))
    expected_refresh_effect = operator_view_refresh_effect(
        pre_refresh_freshness=dict_payload(
            payload.get("pre_refresh_snapshot_freshness", {})
        ),
        post_refresh_freshness=dict_payload(
            payload.get("cockpit_snapshot_freshness", {})
        ),
        blocker_delta=blocker_delta,
        policy_summary=policy_summary,
        operator_summary=operator_summary,
    )
    if refresh_effect != expected_refresh_effect:
        errors.append("operator_view_refresh refresh_effect mismatch")

    review_summary = dict_payload(payload.get("review_summary", {}))
    expected_review_summary = operator_view_refresh_review_summary(
        refresh_effect=refresh_effect,
        operator_summary=operator_summary,
        post_refresh_freshness=dict_payload(
            payload.get("cockpit_snapshot_freshness", {})
        ),
        policy_summary=policy_summary,
    )
    if review_summary != expected_review_summary:
        errors.append("operator_view_refresh review_summary mismatch")

    for key in (
        "next_command_source",
        "next_command_label",
        "next_command",
        "next_command_reason",
        "next_command_boundary",
    ):
        if str(operator_summary.get(key, "")) != str(review_summary.get(key, "")):
            errors.append(f"operator_view_refresh review_summary {key} mismatch")

    reason_codes = string_payload(review_summary.get("reason_codes", []))
    reason_count = int_value(review_summary.get("reason_count", -1))
    if reason_count != len(reason_codes):
        errors.append("operator_view_refresh review_summary reason_count mismatch")
    primary_reason = str(review_summary.get("primary_reason", ""))
    expected_primary_reason = reason_codes[0] if reason_codes else ""
    if primary_reason != expected_primary_reason:
        errors.append("operator_view_refresh review_summary primary_reason mismatch")

    refresh_effect = dict_payload(payload.get("refresh_effect", {}))
    effect_blocker_count = int_value(refresh_effect.get("post_blocker_count", -1))
    review_blocker_count = int_value(review_summary.get("post_blocker_count", -1))
    if effect_blocker_count != review_blocker_count:
        errors.append(
            "operator_view_refresh review_summary post_blocker_count mismatch"
        )
    return tuple(errors)


def render_operator_view_refresh_markdown(payload: dict[str, object]) -> str:
    """Render the operator-view refresh receipt as a compact markdown summary."""
    config_record = dict_payload(payload.get("config_record", {}))
    pre_freshness = dict_payload(payload.get("pre_refresh_snapshot_freshness", {}))
    freshness = dict_payload(payload.get("cockpit_snapshot_freshness", {}))
    operator_summary = dict_payload(payload.get("operator_summary", {}))
    home_summary = dict_payload(payload.get("home_summary", {}))
    blocker_delta = dict_payload(payload.get("blocker_delta", {}))
    refresh_effect = dict_payload(payload.get("refresh_effect", {}))
    review_summary = dict_payload(payload.get("review_summary", {}))
    policy = dict_payload(payload.get("policy", {}))
    policy_summary = dict_payload(payload.get("policy_summary", {}))
    lines = [
        "# Operator View Refresh",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Refreshed artifacts: `{payload.get('refreshed_count', 0)}`",
        f"- Config source: `{payload.get('config_source', '')}`",
        f"- Config path: `{config_record.get('relative_path', payload.get('config_path', ''))}`",
        f"- Config exists: `{payload.get('config_path_exists', False)}`",
        f"- Config sha256: `{str(payload.get('config_sha256', ''))[:12]}`",
        f"- Pre-refresh freshness: `{pre_freshness.get('status', '')}`",
        f"- Pre-refresh stale sources: `{pre_freshness.get('stale_count', 0)}`",
        f"- Cockpit freshness: `{freshness.get('status', '')}`",
        f"- Freshness ok: `{freshness.get('ok', False)}`",
        f"- Refresh effect: `{refresh_effect.get('status', '')}`",
        f"- Refresh effect summary: {refresh_effect.get('summary', '')}",
        f"- Review required: `{review_summary.get('required', False)}`",
        f"- Review primary reason: `{review_summary.get('primary_reason', '')}`",
        f"- Cockpit status: `{operator_summary.get('cockpit_status', '')}`",
        f"- Primary focus: `{operator_summary.get('primary_focus', '')}`",
        "- Action execution readiness: "
        f"`{operator_summary.get('action_execution_readiness_status', '')}`",
        f"- Action execution ready: "
        f"`{operator_summary.get('action_execution_ready', False)}`",
        "- Action execution missing artifacts: "
        f"`{operator_summary.get('action_execution_missing_artifact_count', 0)}`",
        "- Action path closure: "
        f"`{operator_summary.get('action_path_closure_status', '')}`",
        f"- Action path closed: "
        f"`{operator_summary.get('action_path_closed', False)}`",
        "- Action path steps: "
        f"`{operator_summary.get('action_path_completed_step_count', 0)}` / "
        f"`{operator_summary.get('action_path_required_step_count', 0)}`",
        f"- Operator digest: {operator_summary.get('operator_digest_headline', '')}",
        f"- Digest priority: `{operator_summary.get('operator_digest_priority', '')}`",
        "- Digest target panel: "
        f"`{operator_summary.get('operator_digest_target_panel_title', '')}` "
        f"(`{operator_summary.get('operator_digest_target_panel_status', '')}`)",
        f"- Digest next step: {operator_summary.get('operator_digest_next_step', '')}",
        "- Digest command boundary: "
        f"`{operator_summary.get('operator_digest_recommended_command_boundary', '')}`",
        f"- Blockers: `{operator_summary.get('blocker_count', 0)}`",
        f"- Blocker delta changed: `{blocker_delta.get('changed', False)}`",
        f"- Blockers added: `{blocker_delta.get('added_count', 0)}`",
        f"- Blockers removed: `{blocker_delta.get('removed_count', 0)}`",
        f"- Primary blocker: `{operator_summary.get('primary_blocker', '')}`",
        f"- Next command source: `{operator_summary.get('next_command_source', '')}`",
        f"- Next command: `{operator_summary.get('next_command_label', '')}`",
        f"- Next command text: `{operator_summary.get('next_command', '')}`",
        f"- Next command boundary: `{operator_summary.get('next_command_boundary', '')}`",
        f"- Next command reason: {operator_summary.get('next_command_reason', '')}",
        f"- Home status: `{home_summary.get('status', '')}`",
        f"- Home command: `{home_summary.get('home_command_label', '')}`",
        f"- Home command text: `{home_summary.get('home_command', '')}`",
        f"- Home Codex unlock runbook: `{home_summary.get('codex_unlock_runbook_status', '')}`",
        f"- Home Codex intake: `{home_summary.get('codex_intake_readiness_status', '')}`",
        f"- Safety policy OK: `{policy_summary.get('ok', False)}`",
        f"- Safety policy false keys: `{policy_summary.get('false_count', 0)}`",
        "",
        "## Refreshed Artifacts",
        "",
        "| Artifact | JSON | JSON SHA | Markdown | Markdown SHA |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in list_payload(payload.get("refreshed_artifacts", [])):
        json_file = dict_payload(row.get("json_file", {}))
        markdown_file = dict_payload(row.get("markdown_file", {}))
        lines.append(
            "| "
            f"{row.get('artifact_name', '')} | "
            f"`{json_file.get('relative_path', row.get('json_path', ''))}` | "
            f"`{str(json_file.get('sha256', ''))[:12]}` | "
            f"`{markdown_file.get('relative_path', row.get('markdown_path', ''))}` | "
            f"`{str(markdown_file.get('sha256', ''))[:12]}` |"
        )
    if not list_payload(payload.get("refreshed_artifacts", [])):
        lines.append("| none |  |  |  |  |")
    pre_stale_sources = pre_freshness.get("stale_sources", [])
    lines.extend(["", "## Before Refresh", ""])
    lines.append(f"- Status: `{pre_freshness.get('status', '')}`")
    lines.append(f"- Stale sources: `{pre_freshness.get('stale_count', 0)}`")
    for source in pre_stale_sources if isinstance(pre_stale_sources, list) else []:
        lines.append(f"- `{source}`")
    if not pre_stale_sources:
        lines.append("- none")
    lines.extend(["", "## Refresh Effect", ""])
    lines.append(f"- Status: `{refresh_effect.get('status', '')}`")
    lines.append(f"- Summary: {refresh_effect.get('summary', '')}")
    lines.append(
        f"- Stale sources fixed: `{refresh_effect.get('stale_sources_fixed', False)}`",
    )
    lines.append(
        f"- Blockers changed: `{refresh_effect.get('blockers_changed', False)}`",
    )
    lines.append(
        f"- Safety policy ok: `{refresh_effect.get('safety_policy_ok', False)}`",
    )
    lines.append(
        f"- Operator review required: `{refresh_effect.get('operator_review_required', False)}`",
    )
    lines.append(
        f"- Post-refresh blockers: `{refresh_effect.get('post_blocker_count', 0)}`",
    )
    lines.extend(["", "## Review Summary", ""])
    lines.append(f"- Required: `{review_summary.get('required', False)}`")
    lines.append(f"- Primary reason: `{review_summary.get('primary_reason', '')}`")
    lines.append(f"- Reason count: `{review_summary.get('reason_count', 0)}`")
    reason_codes = review_summary.get("reason_codes", [])
    lines.append("- Reasons:")
    for reason in reason_codes if isinstance(reason_codes, list) else []:
        lines.append(f"  - `{reason}`")
    if not reason_codes:
        lines.append("  - none")
    lines.append(f"- Primary blocker: `{review_summary.get('primary_blocker', '')}`")
    lines.append(
        f"- Next command source: `{review_summary.get('next_command_source', '')}`",
    )
    lines.append(f"- Next command: `{review_summary.get('next_command_label', '')}`")
    lines.append(f"- Next command text: `{review_summary.get('next_command', '')}`")
    lines.append(
        f"- Next command boundary: `{review_summary.get('next_command_boundary', '')}`"
    )
    lines.extend(["", "## Operator Home", ""])
    lines.append(f"- Status: `{home_summary.get('status', '')}`")
    lines.append(f"- OK: `{home_summary.get('ok', False)}`")
    lines.append(f"- Headline: {home_summary.get('headline', '')}")
    lines.append(f"- Primary focus: `{home_summary.get('primary_focus', '')}`")
    lines.append(f"- Action step: `{home_summary.get('action_step', '')}`")
    lines.append(f"- Next command: `{home_summary.get('next_command_label', '')}`")
    lines.append(f"- Next command text: `{home_summary.get('next_command', '')}`")
    lines.append(
        f"- Next command boundary: `{home_summary.get('next_command_boundary', '')}`"
    )
    lines.append(
        f"- Next command status: `{home_summary.get('next_command_status', '')}`"
    )
    lines.append(
        f"- Next command blocked: `{home_summary.get('next_command_blocked', False)}`"
    )
    lines.append(
        "- Next command blockers: "
        f"`{home_summary.get('next_command_blocker_count', 0)}`"
    )
    lines.append(
        "- Next command operator hint: "
        f"{home_summary.get('next_command_operator_hint', '')}"
    )
    lines.append(
        "- Next command writes: "
        f"`{home_summary.get('next_command_writes_artifact', '')}`"
    )
    lines.append(
        "- Next command requires explicit invocation: "
        f"`{home_summary.get('next_command_requires_explicit_operator_invocation', False)}`"
    )
    lines.append(
        "- Next command requires approval: "
        f"`{home_summary.get('next_command_requires_operator_approval', False)}`"
    )
    lines.append(
        "- Next command records approval: "
        f"`{home_summary.get('next_command_records_operator_approval', False)}`"
    )
    lines.append(
        "- Next command uses guarded executor: "
        f"`{home_summary.get('next_command_uses_guarded_executor', False)}`"
    )
    lines.append(
        "- Next command hint-only: "
        f"`{home_summary.get('next_command_is_hint_only', False)}`"
    )
    lines.append(
        f"- Codex unlock runbook: `{home_summary.get('codex_unlock_runbook_status', '')}`"
    )
    lines.append(
        f"- Codex unlock runbook ready: `{home_summary.get('codex_unlock_runbook_ready', False)}`"
    )
    lines.append(
        "- Codex unlock runbook blocked steps: "
        f"`{home_summary.get('codex_unlock_runbook_blocked_step_count', 0)}`"
    )
    lines.append(
        "- Codex unlock runbook command: "
        f"`{home_summary.get('codex_unlock_runbook_command_label', '')}`"
    )
    lines.append(
        f"- Codex readiness diff: `{home_summary.get('codex_readiness_diff_status', '')}`"
    )
    lines.append(
        f"- Codex intake: `{home_summary.get('codex_intake_readiness_status', '')}`"
    )
    lines.append(
        f"- Codex intake ready: `{home_summary.get('codex_intake_ready', False)}`"
    )
    lines.append(
        f"- Home command: `{home_summary.get('home_command_label', '')}`"
    )
    lines.append(f"- Home command text: `{home_summary.get('home_command', '')}`")
    lines.append(
        f"- Home command boundary: `{home_summary.get('home_command_boundary', '')}`"
    )
    blocker_preview = operator_summary.get("blocker_preview", [])
    lines.extend(["", "## Current Blockers", ""])
    for blocker in blocker_preview if isinstance(blocker_preview, list) else []:
        lines.append(f"- `{blocker}`")
    if not blocker_preview:
        lines.append("- none")
    lines.extend(["", "## Blocker Delta", ""])
    lines.append(f"- Before: `{blocker_delta.get('before_count', 0)}`")
    lines.append(f"- After: `{blocker_delta.get('after_count', 0)}`")
    lines.append(f"- Changed: `{blocker_delta.get('changed', False)}`")
    added_blockers = blocker_delta.get("added_blockers", [])
    removed_blockers = blocker_delta.get("removed_blockers", [])
    lines.append(f"- Added: `{blocker_delta.get('added_count', 0)}`")
    for blocker in added_blockers if isinstance(added_blockers, list) else []:
        lines.append(f"  - `{blocker}`")
    lines.append(f"- Removed: `{blocker_delta.get('removed_count', 0)}`")
    for blocker in removed_blockers if isinstance(removed_blockers, list) else []:
        lines.append(f"  - `{blocker}`")
    stale_sources = freshness.get("stale_sources", [])
    lines.extend(["", "## Snapshot Freshness", ""])
    lines.append(f"- Stale sources: `{freshness.get('stale_count', 0)}`")
    lines.append(
        f"- Refresh command: `{freshness.get('recommended_command', '')}`",
    )
    for source in stale_sources if isinstance(stale_sources, list) else []:
        lines.append(f"- `{source}`")
    if not stale_sources:
        lines.append("- none")
    lines.extend(["", "## Safety Policy", ""])
    false_keys = policy_summary.get("false_keys", [])
    if false_keys:
        lines.append("### False Keys")
        for key in false_keys if isinstance(false_keys, list) else []:
            lines.append(f"- `{key}`")
        lines.append("")
    for key in sorted(policy):
        lines.append(f"- `{key}`: `{policy.get(key)}`")
    return "\n".join(lines) + "\n"


def inferred_run_config_path(*, run_dir: Path, repo_root: Path) -> Path:
    """Return the config path recorded for a run, falling back to default."""
    return refresh_config_path(
        config_path=None,
        run_dir=run_dir,
        repo_root=repo_root,
    )[0]


def refresh_config_path(
    *,
    config_path: Path | None,
    run_dir: Path,
    repo_root: Path,
) -> tuple[Path, str]:
    """Return the effective refresh config path and provenance source."""
    if config_path is not None:
        active_path = (
            config_path if config_path.is_absolute() else repo_root / config_path
        )
        return active_path, "explicit_override"
    metadata_path = run_dir / "run_metadata.json"
    if metadata_path.exists():
        metadata = load_json(metadata_path)
        path_text = str(metadata.get("config_path", ""))
        if path_text:
            path = Path(path_text)
            active_path = path if path.is_absolute() else repo_root / path
            return active_path, "run_metadata"
    return repo_root / "config/default.json", "default_fallback"


def refresh_config_record(
    path: Path,
    *,
    repo_root: Path,
    source: str,
    metadata_path: Path,
) -> dict[str, object]:
    """Return the config file record used by the refresh command."""
    exists = path.exists()
    data = path.read_bytes() if exists and path.is_file() else b""
    return {
        "source": source,
        "path": str(path),
        "relative_path": repo_relative_path(path, repo_root),
        "exists": exists,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest() if data else "",
        "metadata_path": str(metadata_path),
        "metadata_relative_path": repo_relative_path(metadata_path, repo_root),
        "metadata_exists": metadata_path.exists(),
    }


def refresh_file_record(path: Path, *, repo_root: Path) -> dict[str, object]:
    """Return a compact file record for a refreshed output artifact."""
    exists = path.exists()
    data = path.read_bytes() if exists and path.is_file() else b""
    return {
        "path": str(path),
        "relative_path": repo_relative_path(path, repo_root),
        "exists": exists,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest() if data else "",
    }


def repo_relative_path(path: Path, repo_root: Path) -> str:
    """Return a repository-relative path when possible."""
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def operator_unlock_checklist_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return the saved or derived operator unlock checklist for one run."""
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    checklist_path = run_dir / "operator_unlock_checklist.json"
    if checklist_path.exists():
        payload = load_json(checklist_path)
        errors = validate_operator_unlock_checklist_payload(
            payload,
            run_dir=run_dir,
            repo_root=experiments_dir.parent,
        )
        if errors:
            raise ValueError(
                "operator unlock checklist failed schema validation: "
                + "; ".join(errors)
            )
        payload["from_artifact"] = True
        return payload
    payload = build_operator_unlock_checklist(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
    )
    errors = validate_operator_unlock_checklist_payload(
        payload,
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "operator unlock checklist failed schema validation: "
            + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def codex_cli_unlock_runbook_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return the saved or derived Codex CLI unlock runbook for one run."""
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    runbook_path = run_dir / "codex_cli_unlock_runbook.json"
    if runbook_path.exists():
        payload = load_json(runbook_path)
        errors = validate_codex_cli_unlock_runbook_payload(
            payload,
            run_dir=run_dir,
            repo_root=experiments_dir.parent,
        )
        if errors:
            raise ValueError(
                "Codex CLI unlock runbook failed schema validation: "
                + "; ".join(errors)
            )
        payload["from_artifact"] = True
        return payload
    payload = build_codex_cli_unlock_runbook(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
    )
    errors = validate_codex_cli_unlock_runbook_payload(
        payload,
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "Codex CLI unlock runbook failed schema validation: "
            + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def codex_cli_execution_readiness_diff_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    config_path: Path = Path("config/codex_cli_enable_candidate.json"),
) -> dict[str, object]:
    """Return the saved or derived Codex CLI execution readiness diff."""
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    diff_path = run_dir / "codex_cli_execution_readiness_diff.json"
    if diff_path.exists():
        payload = load_json(diff_path)
        errors = validate_codex_cli_execution_readiness_diff_payload(
            payload,
            run_dir=run_dir,
            repo_root=experiments_dir.parent,
            config_path=config_path,
        )
        if errors:
            raise ValueError(
                "Codex CLI execution readiness diff failed schema validation: "
                + "; ".join(errors)
            )
        payload["from_artifact"] = True
        return payload
    payload = build_codex_cli_execution_readiness_diff(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        config_path=config_path,
    )
    errors = validate_codex_cli_execution_readiness_diff_payload(
        payload,
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        config_path=config_path,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "Codex CLI execution readiness diff failed schema validation: "
            + "; ".join(errors)
        )
    payload["from_artifact"] = False
    return payload


def agent_slot_health_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return agent slot health, loading a saved report when present."""
    run_dir = experiments_dir / run_id
    path = run_dir / "agent_slot_health.json"
    if path.exists():
        payload = load_json(path)
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_agent_slot_health(run_dir=run_dir, repo_root=experiments_dir.parent)
    payload["from_artifact"] = False
    return payload


def agent_slot_readiness_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return agent slot readiness, loading a saved report when present."""
    run_dir = experiments_dir / run_id
    path = run_dir / "agent_slot_readiness_gate.json"
    if path.exists():
        payload = load_json(path)
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_agent_slot_readiness_gate(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
    )
    payload["from_artifact"] = False
    return payload


def external_agent_sandbox_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return external agent sandbox drill details for one run."""
    run_dir = experiments_dir / run_id
    path = run_dir / "external_agent_sandbox_drill.json"
    if path.exists():
        payload = load_json(path)
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_external_agent_sandbox_drill(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
    )
    payload["from_artifact"] = False
    return payload


def round_replay_summary(*, run_dir: Path) -> dict[str, object]:
    """Return compact round replay status for experiment inspection."""
    round_dirs = [
        path
        for path in sorted(run_dir.glob("round_*"))
        if path.is_dir()
    ]
    rounds = [round_replay_row(round_dir=round_dir) for round_dir in round_dirs]
    replayed_count = sum(1 for row in rounds if bool(row["exists"]))
    ok_count = sum(1 for row in rounds if bool(row["ok"]))
    return {
        "round_count": len(rounds),
        "replayed_round_count": replayed_count,
        "missing_round_count": len(rounds) - replayed_count,
        "ok_count": ok_count,
        "failure_count": replayed_count - ok_count,
        "rounds": rounds,
    }


def round_replay_row(*, round_dir: Path) -> dict[str, object]:
    """Return one compact round replay inspection row."""
    path = round_dir / "round_replay.json"
    markdown_path = round_dir / "round_replay.md"
    if not path.exists():
        return {
            "round_id": round_dir.name,
            "exists": False,
            "ok": False,
            "failure_code": "missing_round_replay",
            "failure_stage": "replay",
            "path": str(path),
            "markdown_path": str(markdown_path),
            "planned_attempt_count": 0,
            "manifest_attempt_count": 0,
            "replayed_attempt_count": 0,
            "selected_attempt_id": "",
            "attempts": [],
        }
    payload = load_json(path)
    attempts = payload.get("attempts", [])
    return {
        "round_id": str(payload.get("round_id", round_dir.name)),
        "exists": True,
        "ok": bool(payload.get("ok", False)),
        "failure_code": str(payload.get("failure_code", "")),
        "failure_stage": str(payload.get("failure_stage", "")),
        "path": str(path),
        "markdown_path": str(markdown_path),
        "planned_attempt_count": int(payload.get("planned_attempt_count", 0)),
        "manifest_attempt_count": int(payload.get("manifest_attempt_count", 0)),
        "replayed_attempt_count": int(payload.get("replayed_attempt_count", 0)),
        "selected_attempt_id": str(payload.get("selected_attempt_id", "")),
        "attempts": compact_round_replay_attempts(attempts),
    }


def compact_round_replay_attempts(attempts: object) -> list[dict[str, object]]:
    """Return compact attempt rows from a round replay payload."""
    if not isinstance(attempts, list):
        return []
    rows: list[dict[str, object]] = []
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        rows.append(
            {
                "attempt_id": str(attempt.get("attempt_id", "")),
                "profile_name": str(attempt.get("profile_name", "")),
                "adapter_name": str(attempt.get("adapter_name", "")),
                "runner_name": str(attempt.get("runner_name", "")),
                "selected": bool(attempt.get("selected", False)),
                "ok": bool(attempt.get("ok", False)),
                "failure_code": str(attempt.get("failure_code", "")),
                "plan_matches_manifest": bool(
                    attempt.get("plan_matches_manifest", False)
                ),
                "replay_path": str(attempt.get("replay_path", "")),
            }
        )
    return rows


def compare_experiments(
    *,
    base_run_id: str,
    candidate_run_id: str,
    experiments_dir: Path = Path("experiments"),
    min_ev_delta: float = 0.0,
) -> dict[str, object]:
    """Compare two runs and return a deterministic promotion recommendation."""
    base = diagnose_run(run_id=base_run_id, experiments_dir=experiments_dir)
    candidate = diagnose_run(run_id=candidate_run_id, experiments_dir=experiments_dir)
    base_perf = comparable_performance(base)
    candidate_perf = comparable_performance(candidate)
    dataset_comparison = compare_dataset_hashes(base, candidate)
    ev_delta = round(
        float(candidate_perf["validation_ev_delta"])
        - float(base_perf["validation_ev_delta"]),
        6,
    )
    trade_count_delta = int(candidate_perf["trade_count_delta"]) - int(
        base_perf["trade_count_delta"]
    )
    winner = comparison_winner(ev_delta=ev_delta, min_ev_delta=min_ev_delta)
    recommendation, reasons = comparison_recommendation(
        winner=winner,
        ev_delta=ev_delta,
        min_ev_delta=min_ev_delta,
        base_perf=base_perf,
        candidate_perf=candidate_perf,
        dataset_comparison=dataset_comparison,
    )
    return {
        "base_run_id": base_run_id,
        "candidate_run_id": candidate_run_id,
        "base": base_perf,
        "candidate": candidate_perf,
        "metric_deltas": {
            "validation_ev_delta": ev_delta,
            "trade_count_delta": trade_count_delta,
        },
        "dataset_comparison": dataset_comparison,
        "winner": winner,
        "recommendation": recommendation,
        "reasons": reasons,
        "min_ev_delta": min_ev_delta,
        "summary": comparison_summary(
            base_run_id=base_run_id,
            candidate_run_id=candidate_run_id,
            winner=winner,
            recommendation=recommendation,
            ev_delta=ev_delta,
        ),
    }


def show_champion(
    *,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return the current champion registry, or an empty status."""
    path = champion_path(experiments_dir)
    lineage = champion_lineage_summary(experiments_dir=experiments_dir)
    policy = {
        "inspection_only": True,
        "reads_saved_artifacts_only": True,
        "does_not_write_champion": True,
        "does_not_promote_champion": True,
        "does_not_change_acceptance": True,
    }
    if not path.exists():
        payload = {
            "schema_version": CHAMPION_STATUS_SCHEMA_VERSION,
            "exists": False,
            "champion_path": str(path),
            "lineage_summary": lineage,
            "policy": policy,
        }
    else:
        champion = load_json(path)
        payload = {
            "schema_version": CHAMPION_STATUS_SCHEMA_VERSION,
            "exists": True,
            "champion_path": str(path),
            "champion": champion,
            "lineage_summary": lineage,
            "policy": policy,
        }
    errors = validate_champion_status_payload(
        payload,
        repo_root=experiments_dir.parent,
    )
    if errors:
        raise ValueError("champion status failed schema validation: " + "; ".join(errors))
    return payload


def validate_champion_status_payload(
    payload: dict[str, object],
    *,
    repo_root: Path,
) -> tuple[str, ...]:
    """Validate the terminal-only champion status payload."""
    schema = load_schema(repo_root / CHAMPION_STATUS_SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=payload,
            schema=schema,
            schema_dir=(repo_root / CHAMPION_STATUS_SCHEMA_PATH).parent,
        )
    )
    errors.extend(validate_champion_status_consistency(payload))
    return tuple(errors)


def validate_champion_status_consistency(
    payload: dict[str, object],
) -> tuple[str, ...]:
    """Validate champion status fields are internally consistent and read-only."""
    errors: list[str] = []
    exists = bool(payload.get("exists", False))
    champion = dict_or_none_payload(payload.get("champion"))
    lineage = dict_payload(payload.get("lineage_summary", {}))
    policy = dict_payload(payload.get("policy", {}))
    lineage_policy = dict_payload(lineage.get("policy", {}))
    if str(payload.get("schema_version", "")) != CHAMPION_STATUS_SCHEMA_VERSION:
        errors.append("champion_status schema_version mismatch")
    for key, value in policy.items():
        if value is not True:
            errors.append(f"champion_status policy false: {key}")
    for key, value in lineage_policy.items():
        if value is not True:
            errors.append(f"champion_status lineage policy false: {key}")
    if exists:
        if champion is None:
            errors.append("champion_status champion missing")
        else:
            champion_run_id = str(champion.get("champion_run_id", ""))
            if champion.get("schema_version") != CHAMPION_SCHEMA_VERSION:
                errors.append("champion_status champion schema_version mismatch")
            if not champion_run_id:
                errors.append("champion_status champion_run_id missing")
            if lineage.get("current_champion_exists") is not True:
                errors.append("champion_status lineage existence mismatch")
            if str(lineage.get("current_champion_run_id", "")) != champion_run_id:
                errors.append("champion_status lineage current champion mismatch")
            if int_value(lineage.get("event_count", 0), 0) > 0:
                if str(lineage.get("latest_champion_run_id", "")) != champion_run_id:
                    errors.append("champion_status lineage latest champion mismatch")
                latest_ev = optional_float_value(
                    lineage.get("latest_validation_ev_delta")
                )
                champion_ev = optional_float_value(champion.get("validation_ev_delta"))
                if (
                    latest_ev is not None
                    and champion_ev is not None
                    and round(latest_ev, 6) != round(champion_ev, 6)
                ):
                    errors.append("champion_status lineage validation ev mismatch")
    else:
        if champion is not None:
            errors.append("champion_status empty champion mismatch")
        if lineage.get("current_champion_exists") is not False:
            errors.append("champion_status empty lineage existence mismatch")
        if str(lineage.get("current_champion_run_id", "")):
            errors.append("champion_status empty lineage champion mismatch")
    if int_value(lineage.get("event_count", 0), 0) < 0:
        errors.append("champion_status lineage event_count negative")
    if int_value(lineage.get("parse_error_count", 0), 0) < 0:
        errors.append("champion_status lineage parse_error_count negative")
    if int_value(lineage.get("approved_receipt_count", 0), 0) < 0:
        errors.append("champion_status lineage approved_receipt_count negative")
    if int_value(lineage.get("legacy_direct_count", 0), 0) < 0:
        errors.append("champion_status lineage legacy_direct_count negative")
    counted_events = int_value(lineage.get("approved_receipt_count", 0), 0) + int_value(
        lineage.get("legacy_direct_count", 0),
        0,
    )
    if counted_events > int_value(lineage.get("event_count", 0), 0):
        errors.append("champion_status lineage event count mismatch")
    return tuple(errors)


def champion_lineage_summary(
    *,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return a compact read-only champion lineage summary."""
    from orchestrator.champion_lineage import build_champion_lineage

    payload = build_champion_lineage(
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
    )
    current = dict_payload(payload.get("current_champion", {}))
    history = dict_payload(payload.get("history", {}))
    checks = dict_payload(payload.get("checks", {}))
    lineage = list_payload(payload.get("lineage", []))
    latest = lineage[-1] if lineage else {}
    approved_receipt_count = sum(
        1
        for row in lineage
        if str(row.get("promotion_source", "")) == "approved_receipt"
    )
    legacy_direct_count = sum(
        1
        for row in lineage
        if str(row.get("promotion_source", "")) == "legacy_direct"
    )
    resolved_experiments_dir = Path(
        str(payload.get("experiments_dir", experiments_dir))
    )
    json_path = resolved_experiments_dir / "champion_lineage.json"
    markdown_path = resolved_experiments_dir / "champion_lineage.md"
    return {
        "schema_version": "champion_lineage_summary_v1",
        "ok": bool(payload.get("ok", False)),
        "current_champion_exists": bool(current.get("exists", False)),
        "current_champion_run_id": str(current.get("champion_run_id", "")),
        "last_history_champion_run_id": str(
            checks.get("last_history_champion_run_id", "")
        ),
        "current_champion_matches_last_history": bool(
            checks.get("current_champion_matches_last_history", False)
        ),
        "event_count": int(history.get("event_count", 0)),
        "parse_error_count": int(history.get("parse_error_count", 0)),
        "approved_receipt_count": approved_receipt_count,
        "legacy_direct_count": legacy_direct_count,
        "latest_promotion_source": str(latest.get("promotion_source", "")),
        "latest_champion_run_id": str(latest.get("champion_run_id", "")),
        "latest_promoted_from_run_id": str(latest.get("promoted_from_run_id", "")),
        "latest_validation_ev_delta": latest.get("validation_ev_delta"),
        "history_path": str(
            history.get("path", champion_history_path(resolved_experiments_dir))
        ),
        "lineage_artifact_path": str(json_path),
        "lineage_markdown_path": str(markdown_path),
        "lineage_artifact_exists": json_path.exists(),
        "lineage_markdown_exists": markdown_path.exists(),
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "does_not_write_lineage_artifact": True,
            "does_not_promote_champion": True,
            "does_not_change_acceptance": True,
        },
    }


def promote_champion(
    *,
    base_run_id: str,
    candidate_run_id: str,
    experiments_dir: Path = Path("experiments"),
    min_ev_delta: float = 0.0,
) -> dict[str, object]:
    """Legacy direct promotion helper; operator CLI should use promote-approved."""
    comparison = compare_experiments(
        base_run_id=base_run_id,
        candidate_run_id=candidate_run_id,
        experiments_dir=experiments_dir,
        min_ev_delta=min_ev_delta,
    )
    if comparison["recommendation"] != "promote_candidate":
        return {
            "promoted": False,
            "champion_path": str(champion_path(experiments_dir)),
            "history_path": str(champion_history_path(experiments_dir)),
            "comparison": comparison,
            "reason": "comparison did not recommend promotion",
            "current_champion": show_champion(experiments_dir=experiments_dir),
        }

    candidate = diagnose_run(
        run_id=candidate_run_id,
        experiments_dir=experiments_dir,
    )
    payload = champion_payload(
        base_run_id=base_run_id,
        candidate_run_id=candidate_run_id,
        experiments_dir=experiments_dir,
        comparison=comparison,
        candidate_diagnosis=candidate,
    )
    path = champion_path(experiments_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    history_path = append_champion_history(
        experiments_dir=experiments_dir,
        payload=payload,
    )
    return {
        "promoted": True,
        "champion_path": str(path),
        "history_path": str(history_path),
        "champion": payload,
        "comparison": comparison,
    }


def write_champion_comparison(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    min_ev_delta: float = 0.0,
) -> Path | None:
    """Write a run-local comparison against the current champion when available."""
    champion = show_champion(experiments_dir=experiments_dir)
    if not champion.get("exists", False):
        return None
    champion_payload_raw = champion.get("champion", {})
    champion_payload_data = (
        champion_payload_raw if isinstance(champion_payload_raw, dict) else {}
    )
    champion_run_id = str(champion_payload_data.get("champion_run_id", ""))
    if not champion_run_id or champion_run_id == run_id:
        return None

    comparison = compare_experiments(
        base_run_id=champion_run_id,
        candidate_run_id=run_id,
        experiments_dir=experiments_dir,
        min_ev_delta=min_ev_delta,
    )
    payload = {
        "schema_version": "champion_comparison_v1",
        "run_id": run_id,
        "champion_run_id": champion_run_id,
        "created_at": utc_timestamp(),
        "comparison": comparison,
    }
    output_path = experiments_dir / run_id / "champion_comparison.json"
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def champion_payload(
    *,
    base_run_id: str,
    candidate_run_id: str,
    experiments_dir: Path,
    comparison: dict[str, object],
    candidate_diagnosis: dict[str, object],
) -> dict[str, object]:
    """Build the champion registry payload."""
    metadata_payload = candidate_diagnosis.get("metadata", {})
    metadata = metadata_payload if isinstance(metadata_payload, dict) else {}
    candidate_payload = comparison.get("candidate", {})
    candidate = candidate_payload if isinstance(candidate_payload, dict) else {}
    return {
        "schema_version": CHAMPION_SCHEMA_VERSION,
        "champion_run_id": candidate_run_id,
        "promoted_from_run_id": base_run_id,
        "promoted_at": utc_timestamp(),
        "experiments_dir": str(experiments_dir),
        "source_kind": candidate.get("kind", "unknown"),
        "source_status": candidate.get("status", "unknown"),
        "source_best_round": candidate.get("best_round"),
        "strategy_commit": champion_strategy_commit(candidate_diagnosis, metadata),
        "strategy_modifier": str(metadata.get("strategy_modifier", "")),
        "dataset_sha256": metadata.get("dataset_sha256", {}),
        "validation_ev_delta": candidate.get("validation_ev_delta", 0.0),
        "trade_count_delta": candidate.get("trade_count_delta", 0),
        "comparison_summary": comparison["summary"],
        "promotion_reasons": comparison["reasons"],
        "comparison": comparison,
    }


def champion_strategy_commit(
    diagnosis: dict[str, object],
    metadata: dict[str, object],
) -> str:
    """Return the best available commit for the champion strategy."""
    final_commit = diagnosis.get("final_strategy_commit")
    if isinstance(final_commit, str) and final_commit:
        return final_commit
    commit = metadata.get("git_commit")
    return str(commit) if commit else ""


def append_champion_history(
    *,
    experiments_dir: Path,
    payload: dict[str, object],
) -> Path:
    """Append one champion promotion event to history."""
    path = champion_history_path(experiments_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return path


def champion_path(experiments_dir: Path) -> Path:
    """Return the current champion registry path."""
    return experiments_dir / "champion.json"


def champion_history_path(experiments_dir: Path) -> Path:
    """Return the champion promotion history path."""
    return experiments_dir / "champion_history.jsonl"


def utc_timestamp() -> str:
    """Return a deterministic-format UTC timestamp."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def comparable_performance(diagnosis: dict[str, object]) -> dict[str, object]:
    """Return the comparable performance row for one diagnosis payload."""
    kind = str(diagnosis.get("kind", "unknown"))
    status = str(diagnosis.get("status", "unknown"))
    if kind == "iteration_loop":
        best_round = diagnosis.get("best_round")
        best = best_round if isinstance(best_round, dict) else {}
        return {
            "run_id": diagnosis.get("run_id", ""),
            "kind": kind,
            "status": status,
            "accepted": status == "accepted",
            "artifact_ok": bool(diagnosis.get("artifact_ok", False)),
            "validation_ev_delta": float(best.get("validation_ev_delta", 0.0)),
            "trade_count_delta": int(best.get("trade_count_delta", 0)),
            "best_round": best.get("round_id"),
            "summary": diagnosis.get("summary", ""),
        }
    return {
        "run_id": diagnosis.get("run_id", ""),
        "kind": kind,
        "status": status,
        "accepted": bool(diagnosis.get("accepted", False)),
        "artifact_ok": bool(diagnosis.get("artifact_ok", False)),
        "validation_ev_delta": float(diagnosis.get("validation_ev_delta", 0.0)),
        "trade_count_delta": int(diagnosis.get("trade_count_delta", 0)),
        "best_round": None,
        "summary": diagnosis.get("summary", ""),
    }


def compare_dataset_hashes(
    base: dict[str, object],
    candidate: dict[str, object],
) -> dict[str, object]:
    """Compare compact dataset hashes from two diagnosis payloads."""
    base_hashes = dataset_hashes_from_diagnosis(base)
    candidate_hashes = dataset_hashes_from_diagnosis(candidate)
    compared_splits = sorted(set(base_hashes) | set(candidate_hashes))
    missing_fingerprints = []
    if not base_hashes:
        missing_fingerprints.append("base")
    if not candidate_hashes:
        missing_fingerprints.append("candidate")
    mismatched = [
        split
        for split in compared_splits
        if base_hashes.get(split, "") != candidate_hashes.get(split, "")
    ]
    return {
        "match": not missing_fingerprints and not mismatched,
        "compared_splits": compared_splits,
        "mismatched_splits": mismatched,
        "missing_fingerprints": missing_fingerprints,
        "base_sha256": base_hashes,
        "candidate_sha256": candidate_hashes,
    }


def dataset_hashes_from_diagnosis(diagnosis: dict[str, object]) -> dict[str, str]:
    """Return dataset hashes from a diagnosis payload."""
    metadata_payload = diagnosis.get("metadata", {})
    metadata = metadata_payload if isinstance(metadata_payload, dict) else {}
    hashes_payload = metadata.get("dataset_sha256", {})
    if not isinstance(hashes_payload, dict):
        return {}
    return {str(key): str(value) for key, value in hashes_payload.items()}


def comparison_winner(*, ev_delta: float, min_ev_delta: float) -> str:
    """Return the metric winner label."""
    if ev_delta > min_ev_delta:
        return "candidate"
    if ev_delta < -min_ev_delta:
        return "base"
    return "tie"


def comparison_recommendation(
    *,
    winner: str,
    ev_delta: float,
    min_ev_delta: float,
    base_perf: dict[str, object],
    candidate_perf: dict[str, object],
    dataset_comparison: dict[str, object],
) -> tuple[str, list[str]]:
    """Return a deterministic baseline-promotion recommendation."""
    reasons: list[str] = []
    if not bool(base_perf.get("artifact_ok", False)):
        reasons.append("base artifacts are invalid")
    if not bool(candidate_perf.get("artifact_ok", False)):
        reasons.append("candidate artifacts are invalid")
        return "keep_base", reasons
    missing = dataset_comparison.get("missing_fingerprints", [])
    if missing:
        reasons.append(f"dataset fingerprints missing for {', '.join(missing)}")
        return "inconclusive_missing_dataset_fingerprints", reasons
    if not bool(dataset_comparison.get("match", False)):
        reasons.append("dataset fingerprints differ")
        return "inconclusive_dataset_mismatch", reasons
    if winner == "candidate":
        reasons.append(
            f"candidate validation EV delta beats base by {ev_delta:.6f}"
        )
        if bool(candidate_perf.get("accepted", False)):
            return "promote_candidate", reasons
        reasons.append("candidate run was not accepted by its policy gate")
        return "review_candidate_not_accepted", reasons
    if winner == "base":
        reasons.append(
            f"candidate validation EV delta trails base by {abs(ev_delta):.6f}"
        )
        return "keep_base", reasons
    reasons.append(
        f"validation EV delta difference is within threshold {min_ev_delta:.6f}"
    )
    return "keep_base", reasons


def comparison_summary(
    *,
    base_run_id: str,
    candidate_run_id: str,
    winner: str,
    recommendation: str,
    ev_delta: float,
) -> str:
    """Return a one-line comparison summary."""
    return (
        f"Compared {candidate_run_id} against {base_run_id}: winner={winner}; "
        f"recommendation={recommendation}; validation EV delta difference "
        f"{ev_delta:.6f}."
    )


def experiment_score(
    *,
    record: dict[str, object],
    experiments_dir: Path,
) -> dict[str, object]:
    """Build one leaderboard row from index and artifact data."""
    kind = str(record.get("kind", "unknown"))
    if kind == "single_run":
        ev_before = float(record.get("ev_before", 0.0))
        ev_after = float(record.get("ev_after", 0.0))
        return {
            "run_id": record.get("run_id"),
            "kind": kind,
            "status": record.get("status"),
            "created_at": record.get("created_at"),
            "ev_before": ev_before,
            "ev_after": ev_after,
            "ev_delta": round(ev_after - ev_before, 6),
            "trade_count_before": record.get("trade_count_before"),
            "trade_count_after": record.get("trade_count_after"),
        }

    if kind == "iteration_loop":
        run_id = str(record.get("run_id", ""))
        manifest_path = experiments_dir / run_id / "manifest.json"
        best_round: dict[str, object] | None = None
        best_delta = 0.0
        if manifest_path.exists():
            manifest = load_json(manifest_path)
            for round_payload in manifest.get("rounds", []):
                if not isinstance(round_payload, dict):
                    continue
                before = float(round_payload.get("validation_ev_before", 0.0))
                after = float(round_payload.get("validation_ev_after", 0.0))
                delta = round(after - before, 6)
                if best_round is None or delta > best_delta:
                    best_round = round_payload
                    best_delta = delta
        return {
            "run_id": record.get("run_id"),
            "kind": kind,
            "status": record.get("status"),
            "created_at": record.get("created_at"),
            "completed_rounds": record.get("completed_rounds"),
            "accepted_round": record.get("accepted_round"),
            "ev_delta": best_delta,
            "best_round": best_round.get("round_id") if best_round else None,
        }

    return {
        "run_id": record.get("run_id"),
        "kind": kind,
        "status": record.get("status"),
        "created_at": record.get("created_at"),
        "ev_delta": 0.0,
    }


def dict_payload(value: object) -> dict[str, object]:
    """Return a dict payload, or an empty dict for malformed values."""
    return value if isinstance(value, dict) else {}


def list_payload(value: object) -> list[dict[str, object]]:
    """Return object rows from a list payload."""
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def string_payload(value: object) -> list[str]:
    """Return string rows from a list payload."""
    if not isinstance(value, list):
        return []
    return [str(row) for row in value]


def load_json(path: Path) -> dict[str, object]:
    """Load a JSON object from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    """CLI entrypoint for experiment inspection."""
    parser = argparse.ArgumentParser(description="Inspect SuanAgent experiments.")
    parser.add_argument(
        "--experiments-dir",
        type=Path,
        default=Path("experiments"),
        help="Directory containing experiment artifacts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List recent experiments.")
    list_parser.add_argument("--limit", type=int, default=10)

    show_parser = subparsers.add_parser("show", help="Show one experiment.")
    show_parser.add_argument("run_id")

    review_parser = subparsers.add_parser(
        "review",
        help="Show the operator dashboard for one iteration run.",
    )
    review_parser.add_argument("run_id")
    review_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the operator dashboard as markdown.",
    )

    cockpit_parser = subparsers.add_parser(
        "cockpit",
        help="Show the read-only operator cockpit for one iteration run.",
    )
    cockpit_parser.add_argument(
        "run_id",
        nargs="?",
        help="Iteration run id. Defaults to the latest indexed iteration run.",
    )
    cockpit_parser.add_argument(
        "--latest",
        action="store_true",
        help="Show the latest indexed iteration run even if a run id is provided.",
    )
    cockpit_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the operator cockpit as markdown.",
    )

    home_parser = subparsers.add_parser(
        "home",
        help="Show the terminal-only operator home for one iteration run.",
    )
    home_parser.add_argument(
        "run_id",
        nargs="?",
        help="Iteration run id. Defaults to the latest indexed iteration run.",
    )
    home_parser.add_argument(
        "--latest",
        action="store_true",
        help="Show the latest indexed iteration run even if a run id is provided.",
    )
    home_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the operator home as markdown.",
    )

    refresh_views_parser = subparsers.add_parser(
        "refresh-operator-views",
        help="Refresh source-hash-bound read-only operator views in safe order.",
    )
    refresh_views_parser.add_argument(
        "run_id",
        nargs="?",
        help="Iteration run id. Defaults to the latest indexed iteration run.",
    )
    refresh_views_parser.add_argument(
        "--latest",
        action="store_true",
        help="Show the latest indexed iteration run even if a run id is provided.",
    )
    refresh_views_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Config path used for the Codex CLI execution readiness diff.",
    )
    refresh_views_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the refresh receipt as a concise operator summary.",
    )

    unlock_checklist_parser = subparsers.add_parser(
        "unlock-checklist",
        help="Show the read-only operator unlock checklist for one iteration run.",
    )
    unlock_checklist_parser.add_argument("run_id")
    unlock_checklist_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the operator unlock checklist as markdown.",
    )

    unlock_runbook_parser = subparsers.add_parser(
        "unlock-runbook",
        help="Show the read-only Codex CLI unlock runbook for one iteration run.",
    )
    unlock_runbook_parser.add_argument("run_id")
    unlock_runbook_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the Codex CLI unlock runbook as markdown.",
    )

    execution_diff_parser = subparsers.add_parser(
        "execution-readiness-diff",
        help="Show the read-only Codex CLI execution readiness drift audit.",
    )
    execution_diff_parser.add_argument("run_id")
    execution_diff_parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/codex_cli_enable_candidate.json"),
        help="Candidate config used to compute the current execution boundary.",
    )
    execution_diff_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the Codex CLI execution readiness diff as markdown.",
    )

    action_plan_parser = subparsers.add_parser(
        "action-plan",
        help="Show read-only operator action candidates for one iteration run.",
    )
    action_plan_parser.add_argument("run_id", nargs="?")
    action_plan_parser.add_argument(
        "--latest",
        action="store_true",
        help="Resolve the latest indexed iteration-loop run.",
    )
    action_plan_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the operator action plan as markdown.",
    )

    action_approval_parser = subparsers.add_parser(
        "action-approval",
        help="Show read-only operator approval status for one action candidate.",
    )
    action_approval_parser.add_argument("run_id", nargs="?")
    action_approval_parser.add_argument(
        "--latest",
        action="store_true",
        help="Resolve the latest indexed iteration-loop run.",
    )
    action_approval_parser.add_argument("--action-id", default="")
    action_approval_parser.add_argument("--command-label", default="")
    action_approval_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the operator action approval as markdown.",
    )

    action_execution_parser = subparsers.add_parser(
        "action-execution",
        help="Show a saved operator action execution receipt.",
    )
    action_execution_parser.add_argument("run_id", nargs="?")
    action_execution_parser.add_argument(
        "--latest",
        action="store_true",
        help="Resolve the latest indexed iteration-loop run.",
    )
    action_execution_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the operator action execution receipt as markdown.",
    )

    action_audit_parser = subparsers.add_parser(
        "action-audit",
        help="Show the read-only operator action artifact audit.",
    )
    action_audit_parser.add_argument("run_id", nargs="?")
    action_audit_parser.add_argument(
        "--latest",
        action="store_true",
        help="Resolve the latest indexed iteration-loop run.",
    )
    action_audit_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the operator action audit as markdown.",
    )

    action_dashboard_parser = subparsers.add_parser(
        "action-dashboard",
        help="Show the read-only operator action dashboard.",
    )
    action_dashboard_parser.add_argument("run_id", nargs="?")
    action_dashboard_parser.add_argument(
        "--latest",
        action="store_true",
        help="Resolve the latest indexed iteration-loop run.",
    )
    action_dashboard_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the operator action dashboard as markdown.",
    )

    action_guide_parser = subparsers.add_parser(
        "action-guide",
        help="Show the terminal-only operator action path guide.",
    )
    action_guide_parser.add_argument("run_id", nargs="?")
    action_guide_parser.add_argument(
        "--latest",
        action="store_true",
        help="Resolve the latest indexed iteration-loop run.",
    )
    action_guide_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the operator action guide as markdown.",
    )

    leaderboard_parser = subparsers.add_parser(
        "leaderboard",
        help="Rank experiments by validation EV improvement.",
    )
    leaderboard_parser.add_argument("--limit", type=int, default=10)

    memory_parser = subparsers.add_parser(
        "memory",
        help="List recent proposal outcome memory records.",
    )
    memory_parser.add_argument("--limit", type=int, default=10)

    candidates_parser = subparsers.add_parser(
        "candidates",
        help="Show candidate leaderboard for one iteration run.",
    )
    candidates_parser.add_argument("run_id")
    candidates_parser.add_argument("--limit", type=int, default=20)

    agents_parser = subparsers.add_parser(
        "agents",
        help="Show aggregate agent, direction, and patch-family result stats.",
    )
    agents_parser.add_argument("run_id")

    quality_trace_parser = subparsers.add_parser(
        "quality-trace",
        help="Show candidate quality trace for one iteration run.",
    )
    quality_trace_parser.add_argument("run_id")

    profile_recommendation_parser = subparsers.add_parser(
        "profile-recommendation",
        help="Show the read-only next modifier profile recommendation.",
    )
    profile_recommendation_parser.add_argument("run_id")
    profile_recommendation_parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/default.json"),
        help="Config used to resolve modifier profile capabilities.",
    )
    profile_recommendation_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the profile recommendation as markdown.",
    )

    slots_parser = subparsers.add_parser(
        "slots",
        help="Show agent slot health across one iteration run.",
    )
    slots_parser.add_argument("run_id")

    readiness_parser = subparsers.add_parser(
        "readiness",
        help="Show the external-agent slot readiness gate for one iteration run.",
    )
    readiness_parser.add_argument("run_id")

    sandbox_parser = subparsers.add_parser(
        "sandbox",
        help="Show external-agent sandbox drill details for one iteration run.",
    )
    sandbox_parser.add_argument("run_id")

    subparsers.add_parser(
        "coverage",
        help="Report schema, validator, docs, and replay coverage.",
    )

    subparsers.add_parser("champion", help="Show the current champion registry.")
    subparsers.add_parser("lineage", help="Write and show champion lineage.")

    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare two runs and recommend whether to promote the candidate.",
    )
    compare_parser.add_argument("base_run_id")
    compare_parser.add_argument("candidate_run_id")
    compare_parser.add_argument("--min-ev-delta", type=float, default=0.0)

    promote_parser = subparsers.add_parser(
        "promote",
        description=(
            "Legacy direct promotion for deterministic tests; prefer "
            "promote-approved for operator use."
        ),
        help=(
            "Legacy direct promotion for deterministic tests; prefer "
            "promote-approved for operator use."
        ),
    )
    promote_parser.add_argument("base_run_id")
    promote_parser.add_argument("candidate_run_id")
    promote_parser.add_argument("--min-ev-delta", type=float, default=0.0)

    promote_approved_parser = subparsers.add_parser(
        "promote-approved",
        help="Promote a candidate only from recorded approval evidence.",
    )
    promote_approved_parser.add_argument("candidate_run_id")
    promote_approved_parser.add_argument("--approval-path", type=Path, required=True)
    promote_approved_parser.add_argument("--min-ev-delta", type=float, default=0.0)

    apply_config_parser = subparsers.add_parser(
        "apply-config-approved",
        help="Apply config only from approved config dry-run evidence.",
    )
    apply_config_parser.add_argument("run_id")
    apply_config_parser.add_argument("--dry-run-path", type=Path, required=True)
    apply_config_parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/default.json"),
    )

    restore_config_parser = subparsers.add_parser(
        "restore-config-approved",
        help="Restore config only from ready rollback-preview evidence.",
    )
    restore_config_parser.add_argument("run_id")
    restore_config_parser.add_argument("--preview-path", type=Path, required=True)
    restore_config_parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/default.json"),
    )

    diagnose_parser = subparsers.add_parser(
        "diagnose",
        help="Diagnose one run with artifact health and round outcomes.",
    )
    diagnose_parser.add_argument("run_id")

    validate_parser = subparsers.add_parser(
        "validate",
        help="Batch-validate saved experiment run artifacts.",
    )
    validate_parser.add_argument("--limit", type=int, default=10)
    validate_parser.add_argument("--all", action="store_true", dest="all_runs")
    validate_parser.add_argument("--run-id", action="append", dest="run_ids", default=[])
    validate_parser.add_argument("--created-at-from", default="")
    validate_parser.add_argument("--strict", action="store_true")

    health_history_parser = subparsers.add_parser(
        "health-history",
        help="Summarize saved run artifact health history.",
    )
    health_history_parser.add_argument("--limit", type=int, default=10)
    health_history_parser.add_argument("--history-path", type=Path)
    health_history_parser.add_argument("--created-at-from", default="")

    memory_diagnostics_parser = subparsers.add_parser(
        "memory-diagnostics",
        help="Inspect proposal memory against artifact health history.",
    )
    memory_diagnostics_parser.add_argument("--limit", type=int, default=20)
    memory_diagnostics_parser.add_argument("--history-path", type=Path)
    memory_diagnostics_parser.add_argument("--created-at-from", default="")

    memory_hygiene_parser = subparsers.add_parser(
        "memory-hygiene",
        help="Show outcome memory hygiene for one iteration run.",
    )
    memory_hygiene_parser.add_argument("run_id")

    memory_scope_parser = subparsers.add_parser(
        "memory-scope-recommendation",
        help="Show outcome memory scope recommendation for one iteration run.",
    )
    memory_scope_parser.add_argument("run_id")

    config_change_parser = subparsers.add_parser(
        "config-change-candidate",
        help="Show advisory config change candidates for one iteration run.",
    )
    config_change_parser.add_argument("run_id")

    operator_config_parser = subparsers.add_parser(
        "operator-config-review",
        help="Show operator config review for one iteration run.",
    )
    operator_config_parser.add_argument("run_id")

    config_application_parser = subparsers.add_parser(
        "config-application-dry-run",
        help="Show config application dry run for one iteration run.",
    )
    config_application_parser.add_argument("run_id")
    config_application_parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/default.json"),
    )

    config_runbook_parser = subparsers.add_parser(
        "config-runbook",
        help="Show read-only config operator runbook for one iteration run.",
    )
    config_runbook_parser.add_argument("run_id")
    config_runbook_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the config operator runbook as markdown.",
    )

    config_rollback_parser = subparsers.add_parser(
        "config-application-rollback-preview",
        help="Show read-only config rollback preview for one iteration run.",
    )
    config_rollback_parser.add_argument("run_id")
    config_rollback_parser.add_argument("--receipt-path", type=Path)
    config_rollback_parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/default.json"),
    )

    config_lineage_parser = subparsers.add_parser(
        "config-lineage",
        help="Show read-only config lineage for one iteration run.",
    )
    config_lineage_parser.add_argument("run_id")
    config_lineage_parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/default.json"),
    )

    scope_health_parser = subparsers.add_parser(
        "scope-health",
        help="Summarize artifact, history, and memory health for one scope.",
    )
    scope_health_parser.add_argument("--limit", type=int, default=20)
    scope_health_parser.add_argument("--history-path", type=Path)
    scope_health_parser.add_argument("--created-at-from", default="")
    scope_health_parser.add_argument("--strict", action="store_true")

    summary_parser = subparsers.add_parser(
        "summary",
        help="Summarize experiment history.",
    )
    summary_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the summary dashboard as markdown.",
    )

    args = parser.parse_args()
    if args.command == "list":
        payload = list_experiments(
            experiments_dir=args.experiments_dir,
            limit=args.limit,
        )
    elif args.command == "show":
        payload = show_experiment(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
    elif args.command == "review":
        payload = operator_run_review(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
        if args.markdown:
            print(render_operator_run_review_markdown(payload), end="")
            return
    elif args.command == "cockpit":
        payload = operator_cockpit_report(
            experiments_dir=args.experiments_dir,
            run_id=None if args.latest else args.run_id,
        )
        if args.markdown:
            print(render_operator_cockpit_markdown(payload), end="")
            return
    elif args.command == "home":
        payload = operator_home_report(
            experiments_dir=args.experiments_dir,
            run_id=None if args.latest else args.run_id,
        )
        if args.markdown:
            print(render_operator_home_markdown(payload), end="")
            return
    elif args.command == "refresh-operator-views":
        payload = refresh_operator_views(
            experiments_dir=args.experiments_dir,
            run_id=None if args.latest else args.run_id,
            config_path=args.config,
        )
        if args.markdown:
            print(render_operator_view_refresh_markdown(payload), end="")
            return
    elif args.command == "unlock-checklist":
        payload = operator_unlock_checklist_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
        if args.markdown:
            print(render_operator_unlock_checklist_markdown(payload), end="")
            return
    elif args.command == "unlock-runbook":
        payload = codex_cli_unlock_runbook_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
        if args.markdown:
            print(render_codex_cli_unlock_runbook_markdown(payload), end="")
            return
    elif args.command == "execution-readiness-diff":
        payload = codex_cli_execution_readiness_diff_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
            config_path=args.config,
        )
        if args.markdown:
            print(render_codex_cli_execution_readiness_diff_markdown(payload), end="")
            return
    elif args.command == "action-plan":
        payload = operator_action_plan_report(
            experiments_dir=args.experiments_dir,
            run_id=None if args.latest else args.run_id,
        )
        if args.markdown:
            print(render_operator_action_plan_markdown(payload), end="")
            return
    elif args.command == "action-approval":
        payload = operator_action_approval_report(
            experiments_dir=args.experiments_dir,
            run_id=None if args.latest else args.run_id,
            action_id=args.action_id,
            command_label=args.command_label,
        )
        if args.markdown:
            print(render_operator_action_approval_markdown(payload), end="")
            return
    elif args.command == "action-execution":
        payload = operator_action_execution_report(
            experiments_dir=args.experiments_dir,
            run_id=None if args.latest else args.run_id,
        )
        if args.markdown:
            print(render_operator_action_execution_markdown(payload), end="")
            return
    elif args.command == "action-audit":
        payload = operator_action_audit_report(
            experiments_dir=args.experiments_dir,
            run_id=None if args.latest else args.run_id,
        )
        if args.markdown:
            print(render_operator_action_audit_markdown(payload), end="")
            return
    elif args.command == "action-dashboard":
        payload = operator_action_dashboard_report(
            experiments_dir=args.experiments_dir,
            run_id=None if args.latest else args.run_id,
        )
        if args.markdown:
            print(render_operator_action_dashboard_markdown(payload), end="")
            return
    elif args.command == "action-guide":
        payload = operator_action_guide_report(
            experiments_dir=args.experiments_dir,
            run_id=None if args.latest else args.run_id,
        )
        if args.markdown:
            print(render_operator_action_guide_markdown(payload), end="")
            return
    elif args.command == "leaderboard":
        payload = experiment_leaderboard(
            experiments_dir=args.experiments_dir,
            limit=args.limit,
        )
    elif args.command == "memory":
        payload = proposal_memory(
            experiments_dir=args.experiments_dir,
            limit=args.limit,
        )
    elif args.command == "candidates":
        payload = candidate_leaderboard(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
            limit=args.limit,
        )
    elif args.command == "agents":
        payload = agent_result_stats(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
    elif args.command == "quality-trace":
        payload = candidate_quality_trace(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
    elif args.command == "profile-recommendation":
        payload = modifier_profile_recommendation(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
            config_path=args.config,
        )
        if args.markdown:
            print(render_modifier_profile_recommendation_markdown(payload), end="")
            return
    elif args.command == "slots":
        payload = agent_slot_health_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
    elif args.command == "readiness":
        payload = agent_slot_readiness_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
    elif args.command == "sandbox":
        payload = external_agent_sandbox_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
    elif args.command == "coverage":
        payload = build_artifact_validator_coverage(repo_root=args.experiments_dir.parent)
    elif args.command == "champion":
        payload = show_champion(experiments_dir=args.experiments_dir)
    elif args.command == "lineage":
        from orchestrator.champion_lineage import write_champion_lineage

        _, _, payload = write_champion_lineage(
            experiments_dir=args.experiments_dir,
            repo_root=args.experiments_dir.parent,
        )
    elif args.command == "compare":
        payload = compare_experiments(
            experiments_dir=args.experiments_dir,
            base_run_id=args.base_run_id,
            candidate_run_id=args.candidate_run_id,
            min_ev_delta=args.min_ev_delta,
        )
    elif args.command == "promote":
        payload = promote_champion(
            experiments_dir=args.experiments_dir,
            base_run_id=args.base_run_id,
            candidate_run_id=args.candidate_run_id,
            min_ev_delta=args.min_ev_delta,
        )
    elif args.command == "promote-approved":
        from orchestrator.champion_promotion_executor import (
            promote_champion_with_approval,
        )

        payload = promote_champion_with_approval(
            experiments_dir=args.experiments_dir,
            repo_root=args.experiments_dir.parent,
            candidate_run_id=args.candidate_run_id,
            approval_path=args.approval_path,
            min_ev_delta=args.min_ev_delta,
        )
    elif args.command == "apply-config-approved":
        from orchestrator.config_application_executor import (
            apply_config_with_approval,
        )

        payload = apply_config_with_approval(
            experiments_dir=args.experiments_dir,
            repo_root=args.experiments_dir.parent,
            run_id=args.run_id,
            dry_run_path=args.dry_run_path,
            config_path=args.config,
        )
    elif args.command == "restore-config-approved":
        from orchestrator.config_application_restore_executor import (
            restore_config_with_preview,
        )

        payload = restore_config_with_preview(
            experiments_dir=args.experiments_dir,
            repo_root=args.experiments_dir.parent,
            run_id=args.run_id,
            preview_path=args.preview_path,
            config_path=args.config,
        )
    elif args.command == "diagnose":
        payload = diagnose_run(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
    elif args.command == "validate":
        payload = build_run_artifact_health(
            experiments_dir=args.experiments_dir,
            repo_root=args.experiments_dir.parent,
            limit=args.limit,
            all_runs=args.all_runs,
            run_ids=args.run_ids,
            created_at_from=args.created_at_from,
        )
    elif args.command == "health-history":
        payload = build_run_artifact_health_history(
            experiments_dir=args.experiments_dir,
            repo_root=args.experiments_dir.parent,
            history_path=args.history_path
            or args.experiments_dir / DEFAULT_HISTORY_FILENAME,
            limit=args.limit,
            created_at_from=args.created_at_from,
        )
    elif args.command == "memory-diagnostics":
        payload = build_memory_diagnostics(
            experiments_dir=args.experiments_dir,
            repo_root=args.experiments_dir.parent,
            history_path=args.history_path
            or args.experiments_dir / DEFAULT_HISTORY_FILENAME,
            limit=args.limit,
            created_at_from=args.created_at_from,
        )
        errors = validate_memory_diagnostics_payload(
            payload,
            experiments_dir=args.experiments_dir,
            repo_root=args.experiments_dir.parent,
            history_path=args.history_path
            or args.experiments_dir / DEFAULT_HISTORY_FILENAME,
            limit=args.limit,
            created_at_from=args.created_at_from,
        )
        if errors:
            raise ValueError(
                "memory diagnostics failed schema validation: " + "; ".join(errors)
            )
    elif args.command == "memory-hygiene":
        payload = memory_hygiene_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
    elif args.command == "memory-scope-recommendation":
        payload = memory_scope_recommendation_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
    elif args.command == "config-change-candidate":
        payload = config_change_candidate_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
    elif args.command == "operator-config-review":
        payload = operator_config_review_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
    elif args.command == "config-application-dry-run":
        payload = config_application_dry_run_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
            config_path=args.config,
        )
    elif args.command == "config-runbook":
        payload = config_operator_runbook_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
        if args.markdown:
            print(render_config_operator_runbook_markdown(payload), end="")
            return
    elif args.command == "config-application-rollback-preview":
        payload = config_application_rollback_preview_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
            receipt_path=args.receipt_path,
            config_path=args.config,
        )
    elif args.command == "config-lineage":
        payload = config_lineage_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
            config_path=args.config,
        )
    elif args.command == "scope-health":
        payload = build_experiment_scope_health(
            experiments_dir=args.experiments_dir,
            repo_root=args.experiments_dir.parent,
            history_path=args.history_path
            or args.experiments_dir / DEFAULT_HISTORY_FILENAME,
            limit=args.limit,
            created_at_from=args.created_at_from,
        )
    else:
        payload = summarize_experiments(experiments_dir=args.experiments_dir)
        if args.markdown:
            print(render_experiment_summary_markdown(payload), end="")
            return
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.command == "promote-approved" and not payload.get("promoted", False):
        raise SystemExit(1)
    if args.command == "apply-config-approved" and not payload.get("applied", False):
        raise SystemExit(1)
    if args.command == "restore-config-approved" and not payload.get(
        "restored",
        False,
    ):
        raise SystemExit(1)
    if args.command == "validate" and args.strict and not payload.get("ok", False):
        raise SystemExit(1)
    if args.command == "scope-health" and args.strict and not payload.get("ok", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
