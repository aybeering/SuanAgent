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
from orchestrator.candidate_quality_trace import build_candidate_quality_trace
from orchestrator.config_change_candidate import build_config_change_candidate
from orchestrator.experiment_index import read_experiment_index, recent_experiments
from orchestrator.external_agent_sandbox_drill import (
    build_external_agent_sandbox_drill,
)
from orchestrator.experiment_scope_health import build_experiment_scope_health
from orchestrator.config_application_dry_run import build_config_application_dry_run
from orchestrator.memory_diagnostics import build_memory_diagnostics
from orchestrator.memory_hygiene import build_memory_hygiene
from orchestrator.memory_scope_recommendation import build_memory_scope_recommendation
from orchestrator.operator_action_approval import (
    build_operator_action_approval,
    render_operator_action_approval_markdown,
)
from orchestrator.operator_action_audit import (
    build_operator_action_audit,
    render_operator_action_audit_markdown,
)
from orchestrator.operator_action_dashboard import (
    build_operator_action_dashboard,
    render_operator_action_dashboard_markdown,
    write_operator_action_dashboard,
)
from orchestrator.operator_cockpit import (
    annotate_snapshot_freshness,
    build_operator_cockpit,
    render_operator_cockpit_markdown,
    write_operator_cockpit,
)
from orchestrator.operator_unlock_checklist import (
    build_operator_unlock_checklist,
    render_operator_unlock_checklist_markdown,
    write_operator_unlock_checklist,
)
from orchestrator.codex_cli_unlock_runbook import (
    build_codex_cli_unlock_runbook,
    render_codex_cli_unlock_runbook_markdown,
)
from orchestrator.codex_cli_execution_readiness_diff import (
    build_codex_cli_execution_readiness_diff,
    render_codex_cli_execution_readiness_diff_markdown,
    write_codex_cli_execution_readiness_diff,
)
from orchestrator.codex_cli_execution_preflight import (
    write_codex_cli_execution_preflight,
)
from orchestrator.config import load_project_config
from orchestrator.operator_action_executor import (
    render_receipt_markdown as render_operator_action_execution_markdown,
)
from orchestrator.operator_action_plan import (
    build_operator_action_plan,
    render_operator_action_plan_markdown,
)
from orchestrator.operator_config_review import build_operator_config_review
from orchestrator.outcome_memory import recent_outcomes
from orchestrator.run_artifact_health import (
    DEFAULT_HISTORY_FILENAME,
    build_run_artifact_health,
    build_run_artifact_health_history,
)
from orchestrator.run_closeout import build_run_closeout
from orchestrator.run_diagnosis import diagnose_run


CHAMPION_SCHEMA_VERSION = "champion_v1"
SUMMARY_DASHBOARD_SCHEMA_VERSION = "experiment_summary_dashboard_v1"
SUMMARY_DASHBOARD_RECENT_LIMIT = 5


def list_experiments(
    *,
    experiments_dir: Path = Path("experiments"),
    limit: int = 10,
) -> list[dict[str, object]]:
    """Return recent experiment records."""
    return recent_experiments(experiments_dir=experiments_dir, limit=limit)


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
            "manifest": manifest,
        }
    if decision_path.exists():
        decision = load_json(decision_path)
        return {
            "kind": "single_run",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "summary_path": str(run_dir / "summary.md"),
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
    return {
        "total_runs": len(records),
        "by_kind": by_kind,
        "by_status": by_status,
        "best_run": best_run,
        "dashboard": experiment_summary_dashboard(
            records=records,
            experiments_dir=experiments_dir,
            best_run=best_run,
        ),
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
    latest_run = compact_record_row(records[-1]) if records else None
    latest_accepted = latest_record_with_status(records, status="accepted")
    latest_rejected = latest_record_with_status(records, status="rejected")
    champion_gap = champion_gap_summary(
        experiments_dir=experiments_dir,
        best_run=best_run,
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
        "champion_gap": champion_gap,
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


def compact_diagnosis_row(diagnosis: dict[str, object]) -> dict[str, object]:
    """Return one compact dashboard row from a diagnosis payload."""
    best_round = dict_payload(diagnosis.get("best_round", {}))
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
        f"- Watchlist: `{watchlist.get('status', 'clean')}` "
        f"({watchlist.get('alert_count', 0)} alert(s))",
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
            "## Recent Runs",
            "",
            "| Run | Kind | Status | EV Delta | Failure |",
            "| --- | --- | --- | ---: | --- |",
        ]
    )
    if not recent_runs:
        lines.append("| none |  |  |  |  |")
    else:
        for row in recent_runs:
            lines.append(
                "| "
                f"`{markdown_cell(row.get('run_id', ''))}` | "
                f"{markdown_cell(row.get('kind', ''))} | "
                f"{markdown_cell(row.get('status', ''))} | "
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
    return rows[: max(limit, 0)]


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
    return rows[: max(limit, 0)]


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
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_agent_result_stats(run_dir=run_dir)
    payload["from_artifact"] = False
    payload["round_replays"] = round_replay_summary(run_dir=run_dir)
    return payload


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
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_candidate_quality_trace(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
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
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_memory_scope_recommendation(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        experiments_dir=experiments_dir,
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
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_config_change_candidate(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        experiments_dir=experiments_dir,
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
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_operator_config_review(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        experiments_dir=experiments_dir,
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
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    from orchestrator.config_application_rollback_preview import (
        build_config_application_rollback_preview,
    )

    payload = build_config_application_rollback_preview(
        run_id=run_id,
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        receipt_path=receipt_path or run_dir / "config_application_receipt.json",
        config_path=config_path,
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
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    from orchestrator.config_lineage import build_config_lineage

    payload = build_config_lineage(
        run_id=run_id,
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        config_path=config_path,
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
    return {
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


def render_operator_run_review_markdown(payload: dict[str, object]) -> str:
    """Render an operator run review payload as compact markdown."""
    dashboard = dict_payload(payload.get("dashboard", {}))
    status_summary = dict_payload(dashboard.get("status_summary", {}))
    config_review = dict_payload(dashboard.get("config_review", {}))
    champion_review = dict_payload(dashboard.get("champion_review", {}))
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


def operator_action_plan_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return the saved or derived operator action plan for one run."""
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    plan_path = run_dir / "operator_action_plan.json"
    if plan_path.exists():
        payload = load_json(plan_path)
        payload["from_artifact"] = True
        return payload
    if not (run_dir / "run_closeout.json").exists():
        raise FileNotFoundError(f"Run closeout not found for run: {run_id}")
    payload = build_operator_action_plan(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
    )
    payload["from_artifact"] = False
    return payload


def operator_action_approval_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    action_id: str = "",
    command_label: str = "",
) -> dict[str, object]:
    """Return the saved or derived operator action approval for one run."""
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    approval_path = run_dir / "operator_action_approval.json"
    if approval_path.exists() and not action_id and not command_label:
        payload = load_json(approval_path)
        payload["from_artifact"] = True
        return payload
    payload = build_operator_action_approval(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
        action_id=action_id,
        command_label=command_label,
    )
    payload["from_artifact"] = False
    return payload


def operator_action_execution_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return the saved operator action execution receipt for one run."""
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    receipt_path = run_dir / "operator_action_execution_receipt.json"
    if not receipt_path.exists():
        raise FileNotFoundError(
            f"Operator action execution receipt not found: {receipt_path}"
        )
    payload = load_json(receipt_path)
    payload["from_artifact"] = True
    return payload


def operator_action_audit_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return the saved or derived operator action audit for one run."""
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    audit_path = run_dir / "operator_action_audit.json"
    if audit_path.exists():
        payload = load_json(audit_path)
        payload["from_artifact"] = True
        return payload
    payload = build_operator_action_audit(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
    )
    payload["from_artifact"] = False
    return payload


def operator_action_dashboard_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return the saved or derived operator action dashboard for one run."""
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    dashboard_path = run_dir / "operator_action_dashboard.json"
    if dashboard_path.exists():
        payload = load_json(dashboard_path)
        payload["from_artifact"] = True
        return payload
    payload = build_operator_action_dashboard(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=experiments_dir.parent,
    )
    payload["from_artifact"] = False
    return payload


def operator_cockpit_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return the saved or derived operator cockpit for one run."""
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    cockpit_path = run_dir / "operator_cockpit.json"
    if cockpit_path.exists():
        payload = load_json(cockpit_path)
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
    payload["from_artifact"] = False
    return annotate_snapshot_freshness(
        payload,
        repo_root=experiments_dir.parent,
    )


def refresh_operator_views(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    config_path: Path | None = None,
) -> dict[str, object]:
    """Refresh source-hash-bound operator views in deterministic order."""
    experiments_dir = experiments_dir.resolve()
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
    operator_summary = operator_view_refresh_summary(cockpit)
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
    return {
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
        "cockpit_snapshot_freshness": cockpit.get("snapshot_freshness", {}),
        "policy": policy,
        "policy_summary": operator_view_refresh_policy_summary(policy),
    }


def operator_view_refresh_summary(cockpit: dict[str, object]) -> dict[str, object]:
    """Return the next operator-facing checkpoint after refreshing views."""
    commands = list_payload(cockpit.get("recommended_commands", []))
    next_command = commands[0] if commands else {}
    blockers = string_payload(cockpit.get("blockers", []))
    return {
        "cockpit_status": str(cockpit.get("status", "")),
        "cockpit_ok": bool(cockpit.get("ok", False)),
        "primary_focus": str(cockpit.get("primary_focus", "")),
        "blocker_count": len(blockers),
        "primary_blocker": blockers[0] if blockers else "",
        "blocker_preview": blockers[:5],
        "next_command_label": str(next_command.get("label", "")),
        "next_command": str(next_command.get("command", "")),
        "next_command_reason": str(next_command.get("reason", "")),
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


def render_operator_view_refresh_markdown(payload: dict[str, object]) -> str:
    """Render the operator-view refresh receipt as a compact markdown summary."""
    config_record = dict_payload(payload.get("config_record", {}))
    pre_freshness = dict_payload(payload.get("pre_refresh_snapshot_freshness", {}))
    freshness = dict_payload(payload.get("cockpit_snapshot_freshness", {}))
    operator_summary = dict_payload(payload.get("operator_summary", {}))
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
        f"- Cockpit status: `{operator_summary.get('cockpit_status', '')}`",
        f"- Primary focus: `{operator_summary.get('primary_focus', '')}`",
        f"- Blockers: `{operator_summary.get('blocker_count', 0)}`",
        f"- Primary blocker: `{operator_summary.get('primary_blocker', '')}`",
        f"- Next command: `{operator_summary.get('next_command_label', '')}`",
        f"- Next command text: `{operator_summary.get('next_command', '')}`",
        f"- Next command reason: {operator_summary.get('next_command_reason', '')}",
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
    blocker_preview = operator_summary.get("blocker_preview", [])
    lines.extend(["", "## Current Blockers", ""])
    for blocker in blocker_preview if isinstance(blocker_preview, list) else []:
        lines.append(f"- `{blocker}`")
    if not blocker_preview:
        lines.append("- none")
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
        payload["from_artifact"] = True
        return payload
    payload = build_operator_unlock_checklist(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
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
        payload["from_artifact"] = True
        return payload
    payload = build_codex_cli_unlock_runbook(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
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
        payload["from_artifact"] = True
        return payload
    payload = build_codex_cli_execution_readiness_diff(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
        config_path=config_path,
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
    if not path.exists():
        return {
            "exists": False,
            "schema_version": CHAMPION_SCHEMA_VERSION,
            "champion_path": str(path),
            "lineage_summary": lineage,
        }
    payload = load_json(path)
    return {
        "exists": True,
        "champion_path": str(path),
        "champion": payload,
        "lineage_summary": lineage,
    }


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
    cockpit_parser.add_argument("run_id")
    cockpit_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the operator cockpit as markdown.",
    )

    refresh_views_parser = subparsers.add_parser(
        "refresh-operator-views",
        help="Refresh source-hash-bound read-only operator views in safe order.",
    )
    refresh_views_parser.add_argument("run_id")
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
    action_plan_parser.add_argument("run_id")
    action_plan_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the operator action plan as markdown.",
    )

    action_approval_parser = subparsers.add_parser(
        "action-approval",
        help="Show read-only operator approval status for one action candidate.",
    )
    action_approval_parser.add_argument("run_id")
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
    action_execution_parser.add_argument("run_id")
    action_execution_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the operator action execution receipt as markdown.",
    )

    action_audit_parser = subparsers.add_parser(
        "action-audit",
        help="Show the read-only operator action artifact audit.",
    )
    action_audit_parser.add_argument("run_id")
    action_audit_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the operator action audit as markdown.",
    )

    action_dashboard_parser = subparsers.add_parser(
        "action-dashboard",
        help="Show the read-only operator action dashboard.",
    )
    action_dashboard_parser.add_argument("run_id")
    action_dashboard_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the operator action dashboard as markdown.",
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
            run_id=args.run_id,
        )
        if args.markdown:
            print(render_operator_cockpit_markdown(payload), end="")
            return
    elif args.command == "refresh-operator-views":
        payload = refresh_operator_views(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
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
            run_id=args.run_id,
        )
        if args.markdown:
            print(render_operator_action_plan_markdown(payload), end="")
            return
    elif args.command == "action-approval":
        payload = operator_action_approval_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
            action_id=args.action_id,
            command_label=args.command_label,
        )
        if args.markdown:
            print(render_operator_action_approval_markdown(payload), end="")
            return
    elif args.command == "action-execution":
        payload = operator_action_execution_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
        if args.markdown:
            print(render_operator_action_execution_markdown(payload), end="")
            return
    elif args.command == "action-audit":
        payload = operator_action_audit_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
        if args.markdown:
            print(render_operator_action_audit_markdown(payload), end="")
            return
    elif args.command == "action-dashboard":
        payload = operator_action_dashboard_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
        if args.markdown:
            print(render_operator_action_dashboard_markdown(payload), end="")
            return
    elif args.command == "leaderboard":
        payload = experiment_leaderboard(
            experiments_dir=args.experiments_dir,
            limit=args.limit,
        )
    elif args.command == "memory":
        payload = recent_outcomes(
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
