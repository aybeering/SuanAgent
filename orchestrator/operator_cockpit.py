"""Read-only operator cockpit across run, config, action, and champion state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.operator_action_audit import (
    file_record,
    load_json_object,
    object_field,
    resolve_path,
    schema_errors,
)
from orchestrator.operator_action_dashboard import build_operator_action_dashboard
from orchestrator.operator_command_boundaries import classify_operator_command
from orchestrator.operator_unlock_checklist import (
    build_codex_unlock_checklist,
    build_operator_unlock_checklist,
)
from orchestrator.codex_cli_intake_readiness import (
    build_codex_cli_intake_readiness,
    validate_codex_cli_intake_readiness,
)
from orchestrator.codex_cli_execution_preflight import (
    codex_cli_execution_preflight_status,
)
from orchestrator.operator_action_plan import sha256_text
from orchestrator.schema_validation import validate_json_file, validate_json_payload


OPERATOR_COCKPIT_SCHEMA_VERSION = "operator_cockpit_v1"
SCHEMA_PATH = Path("schemas/operator_cockpit.schema.json")


def write_operator_cockpit(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown operator cockpit artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    payload = build_operator_cockpit(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    errors = validate_operator_cockpit_payload(
        payload,
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "operator cockpit failed schema validation: " + "; ".join(errors)
        )
    json_path = run_dir / "operator_cockpit.json"
    md_path = run_dir / "operator_cockpit.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_operator_cockpit_markdown(payload), encoding="utf-8")
    errors = validate_operator_cockpit_file(payload_path=json_path, repo_root=repo_root)
    if errors:
        raise ValueError(
            "operator cockpit failed schema validation: " + "; ".join(errors)
        )
    return json_path, md_path, payload


def annotate_snapshot_freshness(
    payload: dict[str, object],
    *,
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Attach transient source-hash freshness metadata to a cockpit payload."""
    payload["snapshot_freshness"] = cockpit_snapshot_freshness(
        payload=payload,
        repo_root=repo_root,
    )
    return payload


def cockpit_snapshot_freshness(
    *,
    payload: dict[str, object],
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return read-only freshness checks for a saved cockpit source snapshot."""
    repo_root = repo_root.resolve()
    sources = object_field(payload, "source_artifacts")
    rows: list[dict[str, object]] = []
    for source_key in sorted(sources):
        source = sources.get(source_key, {})
        if not isinstance(source, dict):
            rows.append(
                {
                    "artifact_name": source_key,
                    "path": "",
                    "status": "invalid_record",
                    "recorded_exists": False,
                    "current_exists": False,
                    "recorded_sha256": "",
                    "current_sha256": "",
                }
            )
            continue
        source_file = source.get("file", {})
        if not isinstance(source_file, dict):
            rows.append(
                {
                    "artifact_name": source_key,
                    "path": "",
                    "status": "invalid_record",
                    "recorded_exists": False,
                    "current_exists": False,
                    "recorded_sha256": "",
                    "current_sha256": "",
                }
            )
            continue
        path_text = str(source_file.get("path", ""))
        recorded_exists = bool(source_file.get("exists", False))
        recorded_sha = str(source_file.get("sha256", ""))
        artifact_path = resolve_path(Path(path_text), repo_root) if path_text else Path()
        current_file = file_record(artifact_path, repo_root) if path_text else {}
        current_exists = bool(current_file.get("exists", False))
        current_sha = str(current_file.get("sha256", ""))
        if not path_text:
            status = "missing_path"
        elif recorded_exists != current_exists:
            status = "stale"
        elif recorded_sha != current_sha:
            status = "stale"
        else:
            status = "fresh"
        rows.append(
            {
                "artifact_name": source_key,
                "path": str(current_file.get("path", path_text)),
                "status": status,
                "recorded_exists": recorded_exists,
                "current_exists": current_exists,
                "recorded_sha256": recorded_sha,
                "current_sha256": current_sha,
            }
        )
    stale_rows = [row for row in rows if row.get("status") != "fresh"]
    recommended_command = (
        "python -m orchestrator.experiments refresh-operator-views "
        f"{str(payload.get('run_id', ''))}"
    )
    return {
        "schema_version": "operator_cockpit_snapshot_freshness_v1",
        "ok": not stale_rows,
        "status": "fresh" if not stale_rows else "stale_sources",
        "source_count": len(rows),
        "fresh_count": len(rows) - len(stale_rows),
        "stale_count": len(stale_rows),
        "stale_sources": [str(row.get("artifact_name", "")) for row in stale_rows],
        "rows": rows,
        "recommended_command": recommended_command,
        "recommended_command_sha256": sha256_text(recommended_command),
        "policy": {
            "inspection_only": True,
            "does_not_write_artifacts": True,
            "does_not_execute_commands": True,
            "does_not_change_acceptance": True,
        },
    }


def build_operator_cockpit(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return a compact read-only operator cockpit for a completed run."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    run_id = run_dir.name

    manifest = load_json_object(run_dir / "manifest.json")
    diagnosis = load_json_object(run_dir / "diagnosis.json")
    closeout = load_json_object(run_dir / "run_closeout.json")
    config_lineage = load_json_object(run_dir / "config_lineage.json")
    quality_trace = load_json_object(run_dir / "candidate_quality_trace.json")
    challenger = load_json_object(run_dir / "candidate_challenger_report.json")
    promotion = load_json_object(run_dir / "champion_promotion_dry_run.json")
    approval = load_json_object(run_dir / "champion_promotion_approval.json")
    receipt = load_json_object(run_dir / "champion_promotion_receipt.json")
    codex_preflight = load_json_object(run_dir / "codex_cli_execution_preflight.json")
    codex_unlock_runbook = load_json_object(run_dir / "codex_cli_unlock_runbook.json")
    codex_readiness_diff = load_json_object(
        run_dir / "codex_cli_execution_readiness_diff.json"
    )
    codex_intake_readiness = build_codex_cli_intake_readiness(
        run_dir=run_dir,
        repo_root=repo_root,
    )
    codex_unlock_checklist = load_or_build_unlock_checklist(
        run_dir=run_dir,
        repo_root=repo_root,
        codex_preflight=codex_preflight,
    )
    action_dashboard = load_or_build_action_dashboard(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    action_failure_reasons = cockpit_action_failure_reasons(action_dashboard)
    scope_health = load_json_object(run_dir / "experiment_scope_health.json")
    summary = cockpit_summary(
        closeout=closeout,
        config_lineage=config_lineage,
        quality_trace=quality_trace,
        challenger=challenger,
        promotion=promotion,
        approval=approval,
        receipt=receipt,
        codex_preflight=codex_preflight,
        codex_unlock_runbook=codex_unlock_runbook,
        codex_readiness_diff=codex_readiness_diff,
        codex_intake_readiness=codex_intake_readiness,
        action_dashboard=action_dashboard,
        scope_health=scope_health,
        manifest=manifest,
        diagnosis=diagnosis,
    )
    panels = cockpit_panels(
        run_dir=run_dir,
        diagnosis=diagnosis,
        closeout=closeout,
        config_lineage=config_lineage,
        quality_trace=quality_trace,
        challenger=challenger,
        promotion=promotion,
        approval=approval,
        receipt=receipt,
        codex_preflight=codex_preflight,
        codex_unlock_runbook=codex_unlock_runbook,
        codex_readiness_diff=codex_readiness_diff,
        codex_intake_readiness=codex_intake_readiness,
        action_dashboard=action_dashboard,
        scope_health=scope_health,
    )
    blockers = cockpit_blockers(
        config_lineage=config_lineage,
        action_dashboard=action_dashboard,
        codex_preflight=codex_preflight,
        codex_readiness_diff=codex_readiness_diff,
        codex_intake_readiness=codex_intake_readiness,
        promotion=promotion,
        approval=approval,
        scope_health=scope_health,
    )
    status = cockpit_status(summary=summary, blockers=blockers)
    commands = recommended_commands(
        run_id=run_id,
        run_dir=run_dir,
        repo_root=repo_root,
        summary=summary,
        status=status,
    )
    review_priority = cockpit_review_priority(
        status=status,
        summary=summary,
        blockers=blockers,
        panels=panels,
        commands=commands,
    )
    operator_digest = cockpit_operator_digest(
        status=status,
        summary=summary,
        blockers=blockers,
        review_priority=review_priority,
    )
    return {
        "schema_version": OPERATOR_COCKPIT_SCHEMA_VERSION,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "status": status,
        "ok": status not in {"needs_repair", "missing_closeout"},
        "primary_focus": primary_focus(status=status, summary=summary),
        "operator_digest": operator_digest,
        "source_artifacts": source_artifacts(run_dir=run_dir, repo_root=repo_root),
        "summary": summary,
        "panels": panels,
        "action_failure_reasons": action_failure_reasons,
        "blockers": blockers,
        "codex_intake_readiness": codex_intake_readiness,
        "codex_unlock_checklist": codex_unlock_checklist,
        "review_priority": review_priority,
        "recommended_commands": commands,
        "authority": {
            "final_acceptance_authority": "deterministic_policy_gate",
            "cockpit_can_record_approval": False,
            "cockpit_can_execute_commands": False,
            "cockpit_can_write_config": False,
            "cockpit_can_promote_champion": False,
            "cockpit_can_change_acceptance": False,
        },
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "does_not_record_approval": True,
            "does_not_execute_commands": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_write_config": True,
            "does_not_promote_champion": True,
            "does_not_apply_patches": True,
            "does_not_route_agents": True,
            "does_not_change_acceptance": True,
        },
    }


def load_or_build_action_dashboard(
    *,
    run_dir: Path,
    experiments_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    """Load saved action dashboard or derive the same read-only view."""
    path = run_dir / "operator_action_dashboard.json"
    if path.exists():
        return load_json_object(path)
    return build_operator_action_dashboard(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )


def load_or_build_unlock_checklist(
    *,
    run_dir: Path,
    repo_root: Path,
    codex_preflight: dict[str, Any],
) -> dict[str, Any]:
    """Load saved operator unlock checklist or derive the embedded checklist."""
    path = run_dir / "operator_unlock_checklist.json"
    if path.exists():
        payload = load_json_object(path)
        return {
            "status": str(payload.get("status", "missing_preflight")),
            "ready": bool(payload.get("ready", False)),
            "item_count": int(payload.get("item_count", 0) or 0),
            "passed_count": int(payload.get("passed_count", 0) or 0),
            "failed_count": int(payload.get("failed_count", 0) or 0),
            "next_step": str(payload.get("next_step", "")),
            "items": list_of_dicts(payload.get("items", [])),
            "authority": object_field(payload, "authority"),
        }
    if codex_preflight:
        return build_codex_unlock_checklist(codex_preflight=codex_preflight)
    payload = build_operator_unlock_checklist(run_dir=run_dir, repo_root=repo_root)
    return {
        "status": str(payload.get("status", "missing_preflight")),
        "ready": bool(payload.get("ready", False)),
        "item_count": int(payload.get("item_count", 0) or 0),
        "passed_count": int(payload.get("passed_count", 0) or 0),
        "failed_count": int(payload.get("failed_count", 0) or 0),
        "next_step": str(payload.get("next_step", "")),
        "items": list_of_dicts(payload.get("items", [])),
        "authority": object_field(payload, "authority"),
    }


def cockpit_summary(
    *,
    closeout: dict[str, Any],
    config_lineage: dict[str, Any],
    quality_trace: dict[str, Any],
    challenger: dict[str, Any],
    promotion: dict[str, Any],
    approval: dict[str, Any],
    receipt: dict[str, Any],
    codex_preflight: dict[str, Any],
    codex_unlock_runbook: dict[str, Any],
    codex_readiness_diff: dict[str, Any],
    codex_intake_readiness: dict[str, Any],
    action_dashboard: dict[str, Any],
    scope_health: dict[str, Any],
    manifest: dict[str, Any],
    diagnosis: dict[str, Any],
) -> dict[str, object]:
    """Return compact cockpit summary fields."""
    closeout_summary = object_field(closeout, "summary")
    outcome = cockpit_run_outcome_summary(manifest=manifest, diagnosis=diagnosis)
    action_summary = object_field(action_dashboard, "summary")
    action_readiness = object_field(action_dashboard, "execution_readiness")
    action_closure = object_field(action_dashboard, "path_closure")
    quality_summary = object_field(quality_trace, "summary")
    codex_summary = object_field(codex_preflight, "summary")
    diff_summary = object_field(codex_readiness_diff, "summary")
    codex_blockers = string_rows(codex_preflight.get("blocking_errors", []))
    return {
        "run_status": str(closeout.get("status", "unknown")),
        "run_outcome_category": str(outcome.get("category", "")),
        "run_outcome_primary_code": str(outcome.get("primary_code", "")),
        "run_outcome_primary_stage": str(outcome.get("primary_stage", "")),
        "artifact_health_ok": bool(
            closeout.get("ok", False)
            or closeout_summary.get("artifact_health_history_ok", False)
        ),
        "scope_health_ok": bool(scope_health.get("ok", False)),
        "config_lineage_status": str(config_lineage.get("status", "missing")),
        "config_lineage_ok": bool(config_lineage.get("ok", False)),
        "action_status": str(action_dashboard.get("status", "missing")),
        "action_current_step": str(action_dashboard.get("current_step", "")),
        "action_execution_readiness_status": str(
            action_readiness.get("status", "")
        ),
        "action_execution_ready": bool(action_readiness.get("ready", False)),
        "action_execution_next_command_boundary": str(
            action_readiness.get("next_command_boundary", "")
        ),
        "action_execution_missing_artifact_count": int(
            action_readiness.get("missing_artifact_count", 0) or 0
        ),
        "action_path_closure_status": str(action_closure.get("status", "")),
        "action_path_closed": bool(action_closure.get("closed", False)),
        "action_path_completed_step_count": int(
            action_closure.get("completed_step_count", 0) or 0
        ),
        "action_path_required_step_count": int(
            action_closure.get("required_step_count", 0) or 0
        ),
        "action_safe_command_count": int(
            action_summary.get("safe_command_count", 0) or 0
        ),
        "action_failure_reason_count": int(
            action_summary.get("failure_reason_count", 0) or 0
        ),
        "action_first_failure_stage": str(
            action_summary.get("first_failure_stage", "none")
        ),
        "candidate_quality_status": "present" if quality_trace else "missing",
        "candidate_quality_candidate_count": int(
            quality_summary.get("candidate_count", 0) or 0
        ),
        "candidate_quality_selectable_count": int(
            quality_summary.get("selectable_count", 0) or 0
        ),
        "candidate_quality_selected_count": int(
            quality_summary.get("selected_count", 0) or 0
        ),
        "candidate_quality_top_failure_code": str(
            quality_summary.get("top_failure_code", "")
        ),
        "challenger_status": str(challenger.get("status", "missing")),
        "promotion_status": str(promotion.get("status", "missing")),
        "promotion_would_promote": bool(
            object_field(promotion, "dry_run_decision").get("would_promote", False)
        ),
        "promotion_approval_status": str(approval.get("status", "missing")),
        "promotion_approval_recorded": bool(
            object_field(approval, "operator_intent").get("approval_recorded", False)
        ),
        "promotion_receipt_status": str(receipt.get("status", "missing")),
        "promotion_receipt_promoted": bool(receipt.get("promoted", False)),
        "codex_preflight_status": codex_preflight_status(
            preflight=codex_preflight,
            blockers=codex_blockers,
        ),
        "codex_preflight_ok": bool(codex_preflight.get("ok", False)),
        "codex_real_execute_profile_count": int(
            codex_summary.get("real_codex_execute_profile_count", 0) or 0
        ),
        "codex_operator_unlock_ready_count": int(
            codex_summary.get("operator_unlock_ready_count", 0) or 0
        ),
        "codex_preflight_blocker_count": len(codex_blockers),
        "codex_unlock_runbook_status": str(
            codex_unlock_runbook.get("status", "missing")
        ),
        "codex_unlock_runbook_ready": bool(
            codex_unlock_runbook.get("ready", False)
        ),
        "codex_unlock_runbook_blocked_step_count": int(
            object_field(codex_unlock_runbook, "summary").get(
                "blocked_step_count",
                0,
            )
            or 0
        ),
        "codex_readiness_diff_status": str(
            codex_readiness_diff.get("status", "missing")
        ),
        "codex_readiness_diff_ready": bool(
            codex_readiness_diff.get("ready", False)
        ),
        "codex_readiness_diff_matched_count": int(
            diff_summary.get("matched_count", 0) or 0
        ),
        "codex_readiness_diff_drift_count": int(
            diff_summary.get("drift_count", 0) or 0
        ),
        "codex_readiness_diff_missing_count": int(
            diff_summary.get("missing_comparison_count", 0) or 0
        ),
        "codex_intake_readiness_status": str(
            codex_intake_readiness.get("status", "not_available")
        ),
        "codex_intake_ready": bool(codex_intake_readiness.get("ready", False)),
        "codex_intake_blocker_count": int(
            codex_intake_readiness.get("blocking_reason_count", 0) or 0
        ),
    }


def cockpit_status(*, summary: dict[str, object], blockers: list[str]) -> str:
    """Return a stable cockpit status."""
    if summary.get("run_status") == "unknown":
        return "missing_closeout"
    if blockers:
        return "needs_operator_review"
    if summary.get("action_status") in {"pending_approval", "ready_for_execution"}:
        return "action_pending"
    if summary.get("promotion_would_promote") is True and not summary.get(
        "promotion_approval_recorded"
    ):
        return "promotion_pending_approval"
    return "ready_for_review"


def primary_focus(*, status: str, summary: dict[str, object]) -> str:
    """Return one human-facing focus string."""
    if status == "action_pending":
        return str(summary.get("action_current_step", "review_action_dashboard"))
    if status == "promotion_pending_approval":
        return "review_champion_promotion"
    if status == "needs_operator_review":
        return "inspect_blockers"
    if status == "missing_closeout":
        return "write_run_closeout"
    return "review_research_outcome"


def cockpit_operator_digest(
    *,
    status: str,
    summary: dict[str, object],
    blockers: list[str],
    review_priority: dict[str, object],
) -> dict[str, object]:
    """Return the first-screen cockpit digest derived from saved evidence."""
    blocker_count = len(blockers)
    first_blocker = blockers[0] if blockers else ""
    priority = str(review_priority.get("priority", ""))
    outcome = str(summary.get("run_outcome_category", ""))
    outcome_code = str(summary.get("run_outcome_primary_code", ""))
    target_title = str(review_priority.get("target_panel_title", ""))
    if blocker_count:
        headline = f"Inspect {target_title or 'blockers'} before continuing."
    elif priority == "action_required":
        headline = (
            f"Complete {target_title or 'the operator action'} before continuing."
        )
    elif outcome and outcome != "accepted":
        headline = f"Review deterministic run outcome {outcome_code or outcome}."
    else:
        headline = "Run is ready for operator review."
    return {
        "schema_version": "operator_digest_v1",
        "headline": headline,
        "status": status,
        "ok": status not in {"needs_repair", "missing_closeout"},
        "primary_focus": primary_focus(status=status, summary=summary),
        "run_outcome_category": outcome,
        "run_outcome_primary_code": outcome_code,
        "blocker_count": blocker_count,
        "first_blocker": first_blocker,
        "config_lineage_status": str(summary.get("config_lineage_status", "")),
        "action_status": str(summary.get("action_status", "")),
        "action_current_step": str(summary.get("action_current_step", "")),
        "action_execution_readiness_status": str(
            summary.get("action_execution_readiness_status", "")
        ),
        "action_execution_ready": bool(
            summary.get("action_execution_ready", False)
        ),
        "action_execution_next_command_boundary": str(
            summary.get("action_execution_next_command_boundary", "")
        ),
        "action_execution_missing_artifact_count": int(
            summary.get("action_execution_missing_artifact_count", 0) or 0
        ),
        "action_path_closure_status": str(
            summary.get("action_path_closure_status", "")
        ),
        "action_path_closed": bool(summary.get("action_path_closed", False)),
        "action_path_completed_step_count": int(
            summary.get("action_path_completed_step_count", 0) or 0
        ),
        "action_path_required_step_count": int(
            summary.get("action_path_required_step_count", 0) or 0
        ),
        "candidate_quality_top_failure_code": str(
            summary.get("candidate_quality_top_failure_code", "")
        ),
        "codex_preflight_status": str(summary.get("codex_preflight_status", "")),
        "codex_unlock_runbook_status": str(
            summary.get("codex_unlock_runbook_status", "")
        ),
        "codex_readiness_diff_status": str(
            summary.get("codex_readiness_diff_status", "")
        ),
        "codex_intake_readiness_status": str(
            summary.get("codex_intake_readiness_status", "")
        ),
        "codex_intake_ready": bool(summary.get("codex_intake_ready", False)),
        "promotion_status": str(summary.get("promotion_status", "")),
        "priority": priority,
        "primary_reason": str(review_priority.get("primary_reason", "")),
        "target_panel_id": str(review_priority.get("target_panel_id", "")),
        "target_panel_title": target_title,
        "target_panel_status": str(review_priority.get("target_panel_status", "")),
        "next_step": str(review_priority.get("next_step", "")),
        "recommended_command_label": str(
            review_priority.get("recommended_command_label", "")
        ),
        "recommended_command": str(review_priority.get("recommended_command", "")),
        "recommended_command_sha256": str(
            review_priority.get("recommended_command_sha256", "")
        ),
        "recommended_command_boundary": object_field(
            review_priority,
            "recommended_command_boundary",
        ),
        "policy": {
            "inspection_only": True,
            "command_is_hint_only": True,
            "does_not_execute_commands": True,
            "does_not_change_acceptance": True,
        },
    }


def cockpit_panels(
    *,
    run_dir: Path,
    diagnosis: dict[str, Any],
    closeout: dict[str, Any],
    config_lineage: dict[str, Any],
    quality_trace: dict[str, Any],
    challenger: dict[str, Any],
    promotion: dict[str, Any],
    approval: dict[str, Any],
    receipt: dict[str, Any],
    codex_preflight: dict[str, Any],
    codex_unlock_runbook: dict[str, Any],
    codex_readiness_diff: dict[str, Any],
    codex_intake_readiness: dict[str, Any],
    action_dashboard: dict[str, Any],
    scope_health: dict[str, Any],
) -> list[dict[str, object]]:
    """Return the cockpit panel rows."""
    preflight_blockers = string_rows(codex_preflight.get("blocking_errors", []))
    return [
        panel(
            panel_id="run_review",
            title="Run Review",
            status=str(closeout.get("closeout_status", "missing")),
            ok=bool(closeout.get("ok", False)),
            artifact_path=run_dir / "run_closeout.json",
            next_step="review run closeout dashboard",
        ),
        panel(
            panel_id="run_outcome",
            title="Run Outcome",
            status=str(
                object_field(diagnosis, "run_outcome_summary").get(
                    "category",
                    "missing",
                )
            ),
            ok=bool(
                object_field(diagnosis, "run_outcome_summary").get(
                    "artifact_ok",
                    False,
                )
            ),
            artifact_path=run_dir / "diagnosis.json",
            next_step="review deterministic outcome category and primary code",
        ),
        panel(
            panel_id="config_lineage",
            title="Config Lineage",
            status=str(config_lineage.get("status", "missing")),
            ok=bool(config_lineage.get("ok", False)),
            artifact_path=run_dir / "config_lineage.json",
            next_step="inspect config lineage before changing config",
        ),
        panel(
            panel_id="operator_action",
            title="Operator Action",
            status=str(action_dashboard.get("status", "missing")),
            ok=bool(action_dashboard.get("ok", False)),
            artifact_path=run_dir / "operator_action_dashboard.json",
            next_step=str(action_dashboard.get("current_step", "review action dashboard")),
        ),
        panel(
            panel_id="codex_cli_unlock",
            title="Codex CLI Unlock",
            status=codex_preflight_status(
                preflight=codex_preflight,
                blockers=preflight_blockers,
            ),
            ok=bool(codex_preflight.get("ok", False)),
            artifact_path=run_dir / "codex_cli_execution_preflight.json",
            next_step=codex_preflight_next_step(
                preflight=codex_preflight,
                blockers=preflight_blockers,
            ),
        ),
        panel(
            panel_id="codex_cli_unlock_runbook",
            title="Codex CLI Unlock Runbook",
            status=str(codex_unlock_runbook.get("status", "missing")),
            ok=bool(codex_unlock_runbook.get("ready", False))
            or str(codex_unlock_runbook.get("status", "")) == "needs_artifacts",
            artifact_path=run_dir / "codex_cli_unlock_runbook.json",
            next_step=codex_unlock_runbook_next_step(codex_unlock_runbook),
        ),
        panel(
            panel_id="codex_cli_readiness_diff",
            title="Codex CLI Readiness Diff",
            status=str(codex_readiness_diff.get("status", "missing")),
            ok=bool(codex_readiness_diff.get("ready", False)),
            artifact_path=run_dir / "codex_cli_execution_readiness_diff.json",
            next_step=codex_readiness_diff_next_step(codex_readiness_diff),
        ),
        panel(
            panel_id="codex_cli_intake",
            title="Codex CLI Intake Binding",
            status=str(codex_intake_readiness.get("status", "not_available")),
            ok=bool(codex_intake_readiness.get("ready", False))
            or str(codex_intake_readiness.get("status", "")) == "not_available",
            artifact_path=run_dir / "codex_cli_execution_readiness_diff.json",
            next_step=str(
                codex_intake_readiness.get(
                    "next_step",
                    "review Codex CLI intake binding evidence",
                )
            ),
        ),
        panel(
            panel_id="candidate_quality",
            title="Candidate Quality",
            status="present" if quality_trace else "missing",
            ok=bool(quality_trace),
            artifact_path=run_dir / "candidate_quality_trace.json",
            next_step="inspect candidate scores, selectable count, and rejection reasons",
        ),
        panel(
            panel_id="champion_review",
            title="Champion Review",
            status=str(challenger.get("status", "missing")),
            ok=bool(challenger.get("ok", False)),
            artifact_path=run_dir / "candidate_challenger_report.json",
            next_step="review candidate challenger gap",
        ),
        panel(
            panel_id="promotion",
            title="Promotion",
            status=str(promotion.get("status", "missing")),
            ok=bool(promotion.get("ok", False)),
            artifact_path=run_dir / "champion_promotion_dry_run.json",
            next_step="record promotion approval only if dry run recommends it",
        ),
        panel(
            panel_id="promotion_approval",
            title="Promotion Approval",
            status=str(approval.get("status", "missing")),
            ok=bool(object_field(approval, "operator_intent").get("approval_recorded", False)),
            artifact_path=run_dir / "champion_promotion_approval.json",
            next_step="approval does not promote automatically",
        ),
        panel(
            panel_id="promotion_receipt",
            title="Promotion Receipt",
            status=str(receipt.get("status", "missing")),
            ok=bool(receipt.get("promoted", False)),
            artifact_path=run_dir / "champion_promotion_receipt.json",
            next_step="refresh champion lineage after a successful receipt",
        ),
        panel(
            panel_id="scope_health",
            title="Scope Health",
            status="ok" if scope_health.get("ok") is True else "needs_review",
            ok=bool(scope_health.get("ok", False)),
            artifact_path=run_dir / "experiment_scope_health.json",
            next_step="inspect artifact health failures before reuse",
        ),
    ]


def panel(
    *,
    panel_id: str,
    title: str,
    status: str,
    ok: bool,
    artifact_path: Path,
    next_step: str,
) -> dict[str, object]:
    """Return one cockpit panel row."""
    return {
        "panel_id": panel_id,
        "title": title,
        "status": status,
        "ok": ok,
        "artifact_path": artifact_path.as_posix(),
        "artifact_exists": artifact_path.exists(),
        "next_step": next_step,
    }


def cockpit_blockers(
    *,
    config_lineage: dict[str, Any],
    action_dashboard: dict[str, Any],
    codex_preflight: dict[str, Any],
    codex_readiness_diff: dict[str, Any],
    codex_intake_readiness: dict[str, Any],
    promotion: dict[str, Any],
    approval: dict[str, Any],
    scope_health: dict[str, Any],
) -> list[str]:
    """Return compact blocker codes from the cockpit source artifacts."""
    blockers: list[str] = []
    if config_lineage and config_lineage.get("ok") is not True:
        blockers.append("config_lineage_not_ok")
    blockers.extend(
        f"operator_action:{reason.get('code', '')}"
        for reason in cockpit_action_failure_reasons(action_dashboard)
        if reason.get("code")
    )
    blockers.extend(string_rows(action_dashboard.get("blockers", [])))
    blockers.extend(
        f"codex_cli_preflight:{blocker}"
        for blocker in string_rows(codex_preflight.get("blocking_errors", []))
    )
    codex_summary = object_field(codex_preflight, "summary")
    real_codex_profile_count = int(
        codex_summary.get("real_codex_execute_profile_count", 0) or 0
    )
    if (
        real_codex_profile_count > 0
        and codex_readiness_diff
        and codex_readiness_diff.get("ready") is not True
    ):
        blockers.extend(
            f"codex_cli_readiness_diff:{blocker}"
            for blocker in string_rows(
                codex_readiness_diff.get("blocking_reasons", [])
            )
        )
    if codex_intake_readiness.get("status") == "blocked":
        blockers.extend(
            f"codex_cli_intake:{blocker}"
            for blocker in string_rows(
                codex_intake_readiness.get("blocking_reasons", [])
            )
        )
    blockers.extend(
        string_rows(object_field(promotion, "promotion_gate").get("blockers", []))
    )
    approval_blockers = promotion_approval_blockers(
        promotion=promotion,
        approval=approval,
    )
    blockers.extend(approval_blockers)
    if scope_health and scope_health.get("ok") is not True:
        blockers.append("scope_health_not_ok")
    return unique_strings(blockers)


def promotion_approval_blockers(
    *,
    promotion: dict[str, Any],
    approval: dict[str, Any],
) -> list[str]:
    """Return promotion approval blockers, keeping expected review work actionable."""
    blockers = string_rows(
        object_field(approval, "approval_gate").get("approval_blockers", [])
    )
    would_promote = bool(
        object_field(promotion, "dry_run_decision").get("would_promote", False)
    )
    approval_recorded = bool(
        object_field(approval, "operator_intent").get("approval_recorded", False)
    )
    if would_promote and not approval_recorded:
        return [
            blocker
            for blocker in blockers
            if blocker != "operator_approval_not_recorded"
        ]
    return blockers


def cockpit_review_priority(
    *,
    status: str,
    summary: dict[str, object],
    blockers: list[str],
    panels: list[dict[str, object]],
    commands: list[dict[str, object]],
) -> dict[str, object]:
    """Return the first operator review target without changing authority."""
    primary_blocker = blockers[0] if blockers else ""
    outcome_category = str(summary.get("run_outcome_category", ""))
    outcome_code = str(summary.get("run_outcome_primary_code", ""))
    quality_failure = str(summary.get("candidate_quality_top_failure_code", ""))
    if primary_blocker:
        priority = "critical"
        primary_reason = "blocker_present"
        reason_codes = [f"blocker:{primary_blocker}"]
        target_panel_id = panel_for_blocker(primary_blocker)
    elif status == "missing_closeout":
        priority = "critical"
        primary_reason = "missing_closeout"
        reason_codes = ["missing_closeout"]
        target_panel_id = "run_review"
    elif status == "action_pending":
        priority = "action_required"
        primary_reason = "operator_action_pending"
        reason_codes = ["operator_action_pending"]
        target_panel_id = "operator_action"
    elif status == "promotion_pending_approval":
        priority = "action_required"
        primary_reason = "promotion_pending_approval"
        reason_codes = ["promotion_pending_approval"]
        target_panel_id = "promotion_approval"
    elif outcome_category and outcome_category != "accepted" and quality_failure:
        priority = "review"
        primary_reason = f"candidate_quality:{quality_failure}"
        reason_codes = [f"candidate_quality:{quality_failure}"]
        if outcome_code:
            reason_codes.append(f"outcome_code:{outcome_code}")
        target_panel_id = "candidate_quality"
    elif outcome_category and outcome_category != "accepted":
        priority = "review"
        primary_reason = f"run_outcome:{outcome_category}"
        reason_codes = [f"outcome:{outcome_category}"]
        if outcome_code:
            reason_codes.append(f"outcome_code:{outcome_code}")
        target_panel_id = "run_outcome"
    else:
        priority = "clean"
        primary_reason = "ready_for_review"
        reason_codes = ["ready_for_review"]
        target_panel_id = "run_review"

    target_panel = panel_by_id(panels, target_panel_id)
    command = command_for_panel(commands=commands, panel_id=target_panel_id)
    return {
        "schema_version": "operator_review_priority_v1",
        "priority": priority,
        "primary_reason": primary_reason,
        "reason_codes": reason_codes,
        "target_panel_id": target_panel_id,
        "target_panel_title": str(target_panel.get("title", "")),
        "target_panel_status": str(target_panel.get("status", "")),
        "target_artifact_path": str(target_panel.get("artifact_path", "")),
        "target_artifact_exists": bool(target_panel.get("artifact_exists", False)),
        "next_step": str(target_panel.get("next_step", "")),
        "recommended_command_label": str(command.get("label", "")),
        "recommended_command": str(command.get("command", "")),
        "recommended_command_sha256": str(command.get("command_sha256", "")),
        "recommended_command_writes_artifact": str(
            command.get("writes_artifact", "")
        ),
        "recommended_command_reason": str(command.get("reason", "")),
        "recommended_command_boundary": object_field(command, "boundary"),
        "policy": {
            "inspection_only": True,
            "does_not_execute_commands": True,
            "does_not_change_acceptance": True,
        },
    }


def panel_for_blocker(blocker: str) -> str:
    """Map a blocker code to the cockpit panel that should be inspected first."""
    if blocker.startswith("operator_action:"):
        return "operator_action"
    if blocker.startswith("codex_cli_preflight:"):
        return "codex_cli_unlock"
    if blocker.startswith("codex_cli_readiness_diff:"):
        return "codex_cli_readiness_diff"
    if blocker.startswith("codex_cli_intake:"):
        return "codex_cli_intake"
    if blocker == "config_lineage_not_ok":
        return "config_lineage"
    if blocker == "scope_health_not_ok":
        return "scope_health"
    if "approval" in blocker:
        return "promotion_approval"
    if "promotion" in blocker:
        return "promotion"
    return "run_review"


def panel_by_id(
    panels: list[dict[str, object]],
    panel_id: str,
) -> dict[str, object]:
    """Return a cockpit panel by id, or a stable empty panel row."""
    for row in panels:
        if str(row.get("panel_id", "")) == panel_id:
            return row
    return {
        "panel_id": panel_id,
        "title": "",
        "status": "missing",
        "artifact_path": "",
        "artifact_exists": False,
        "next_step": "",
    }


def command_for_panel(
    *,
    commands: list[dict[str, object]],
    panel_id: str,
) -> dict[str, object]:
    """Return the most relevant saved command hint for a cockpit panel."""
    labels_by_panel = {
        "run_outcome": "review_run_diagnosis",
        "config_lineage": "review_config_lineage",
        "operator_action": "review_action_dashboard",
        "codex_cli_unlock": "review_codex_cli_preflight",
        "codex_cli_unlock_runbook": "review_codex_cli_unlock_runbook",
        "codex_cli_readiness_diff": "review_codex_cli_readiness_diff",
        "codex_cli_intake": "review_codex_cli_readiness_diff",
        "candidate_quality": "review_quality_trace",
        "champion_review": "review_challenger_report",
        "promotion": "review_promotion_dry_run",
        "promotion_approval": "review_promotion_approval",
        "scope_health": "review_scope_health",
    }
    wanted = labels_by_panel.get(panel_id, "review_cockpit")
    for command in commands:
        if str(command.get("label", "")) == wanted:
            return command
    return commands[0] if commands else {}


def cockpit_action_failure_reasons(
    action_dashboard: dict[str, Any],
) -> list[dict[str, object]]:
    """Return action-chain failure reasons surfaced by the action dashboard."""
    rows: list[dict[str, object]] = []
    for reason in list_of_dicts(action_dashboard.get("failure_reasons", [])):
        rows.append(
            {
                "stage": str(reason.get("stage", "")),
                "code": str(reason.get("code", "")),
                "severity": str(reason.get("severity", "")),
                "detail": str(reason.get("detail", "")),
            }
        )
    return rows


def cockpit_run_outcome_summary(
    *,
    manifest: dict[str, Any],
    diagnosis: dict[str, Any],
) -> dict[str, Any]:
    """Return the saved run outcome summary from diagnosis or manifest."""
    diagnosis_outcome = object_field(diagnosis, "run_outcome_summary")
    if diagnosis_outcome:
        return diagnosis_outcome
    return object_field(manifest, "run_outcome_summary")


def source_artifacts(*, run_dir: Path, repo_root: Path) -> dict[str, object]:
    """Return cockpit source artifact records."""
    specs = {
        "run_closeout": (
            run_dir / "run_closeout.json",
            "schemas/run_closeout.schema.json",
        ),
        "config_lineage": (
            run_dir / "config_lineage.json",
            "schemas/config_lineage.schema.json",
        ),
        "operator_action_dashboard": (
            run_dir / "operator_action_dashboard.json",
            "schemas/operator_action_dashboard.schema.json",
        ),
        "codex_cli_execution_preflight": (
            run_dir / "codex_cli_execution_preflight.json",
            "schemas/codex_cli_execution_preflight.schema.json",
        ),
        "codex_cli_execution_readiness_diff": (
            run_dir / "codex_cli_execution_readiness_diff.json",
            "schemas/codex_cli_execution_readiness_diff.schema.json",
        ),
        "codex_cli_unlock_runbook": (
            run_dir / "codex_cli_unlock_runbook.json",
            "schemas/codex_cli_unlock_runbook.schema.json",
        ),
        "operator_unlock_checklist": (
            run_dir / "operator_unlock_checklist.json",
            "schemas/operator_unlock_checklist.schema.json",
        ),
        "candidate_quality_trace": (
            run_dir / "candidate_quality_trace.json",
            "schemas/candidate_quality_trace.schema.json",
        ),
        "candidate_challenger_report": (
            run_dir / "candidate_challenger_report.json",
            "schemas/candidate_challenger_report.schema.json",
        ),
        "champion_promotion_dry_run": (
            run_dir / "champion_promotion_dry_run.json",
            "schemas/champion_promotion_dry_run.schema.json",
        ),
        "champion_promotion_approval": (
            run_dir / "champion_promotion_approval.json",
            "schemas/champion_promotion_approval.schema.json",
        ),
        "champion_promotion_receipt": (
            run_dir / "champion_promotion_receipt.json",
            "schemas/champion_promotion_receipt.schema.json",
        ),
        "experiment_scope_health": (
            run_dir / "experiment_scope_health.json",
            "schemas/experiment_scope_health.schema.json",
        ),
    }
    return {
        name: source_artifact(
            path=path,
            schema_path=repo_root / schema_path,
            artifact_name=name,
            repo_root=repo_root,
        )
        for name, (path, schema_path) in specs.items()
    }


def source_artifact(
    *,
    path: Path,
    schema_path: Path,
    artifact_name: str,
    repo_root: Path,
) -> dict[str, object]:
    """Return one source artifact row."""
    return {
        "artifact_name": artifact_name,
        "file": file_record(path, repo_root),
        "schema_errors": list(schema_errors(path=path, schema_path=schema_path)),
    }


def recommended_commands(
    *,
    run_id: str,
    run_dir: Path,
    repo_root: Path,
    summary: dict[str, object],
    status: str,
) -> list[dict[str, object]]:
    """Return read-only command hints for the next operator step."""
    commands = [
        command_hint(
            label="review_cockpit",
            command=f"python -m orchestrator.experiments cockpit {run_id} --markdown",
            reason="Review this read-only cockpit.",
            writes_artifact="",
        ),
        command_hint(
            label="review_run_dashboard",
            command=f"python -m orchestrator.experiments review {run_id} --markdown",
            reason="Inspect the saved run closeout dashboard.",
            writes_artifact="",
        ),
        command_hint(
            label="review_run_diagnosis",
            command=f"python -m orchestrator.experiments diagnose {run_id}",
            reason="Inspect deterministic run outcome and artifact diagnosis.",
            writes_artifact="",
        ),
        command_hint(
            label="review_config_lineage",
            command=f"python -m orchestrator.experiments config-lineage {run_id}",
            reason="Inspect config candidate, review, dry-run, and receipt lineage.",
            writes_artifact="config_lineage.json",
        ),
        command_hint(
            label="review_action_dashboard",
            command=f"python -m orchestrator.experiments action-dashboard {run_id} --markdown",
            reason="Inspect operator action state and guarded next commands.",
            writes_artifact="",
        ),
        command_hint(
            label="review_codex_cli_preflight",
            command=(
                "python -m orchestrator.codex_cli_execution_preflight "
                f"{relative_path(run_dir, repo_root)}"
            ),
            reason="Inspect startup blockers before any real Codex CLI execution.",
            writes_artifact="codex_cli_execution_preflight.json",
        ),
        command_hint(
            label="review_codex_cli_unlock_runbook",
            command=(
                "python -m orchestrator.experiments "
                f"unlock-runbook {run_id} --markdown"
            ),
            reason="Inspect the ordered Codex CLI unlock evidence guide.",
            writes_artifact="",
        ),
        command_hint(
            label="review_codex_cli_readiness_diff",
            command=(
                "python -m orchestrator.experiments "
                f"execution-readiness-diff {run_id} --markdown"
            ),
            reason="Inspect current-vs-reviewed Codex CLI execution evidence.",
            writes_artifact="",
        ),
        command_hint(
            label="review_quality_trace",
            command=f"python -m orchestrator.experiments quality-trace {run_id}",
            reason="Inspect candidate scores, selectable counts, and rejection reasons.",
            writes_artifact="candidate_quality_trace.json",
        ),
        command_hint(
            label="review_challenger_report",
            command=(
                "python -m orchestrator.candidate_challenger_report "
                f"{relative_path(run_dir, repo_root)}"
            ),
            reason="Inspect whether this run beats the current champion.",
            writes_artifact="candidate_challenger_report.json",
        ),
        command_hint(
            label="review_promotion_dry_run",
            command=(
                "python -m orchestrator.champion_promotion_dry_run "
                f"{relative_path(run_dir, repo_root)}"
            ),
            reason="Preview champion promotion eligibility without promoting.",
            writes_artifact="champion_promotion_dry_run.json",
        ),
        command_hint(
            label="review_scope_health",
            command="python -m orchestrator.experiments scope-health --limit 20",
            reason="Inspect experiment-scope artifact and memory health.",
            writes_artifact="",
        ),
    ]
    if not (run_dir / "operator_action_dashboard.json").exists():
        commands.append(
            command_hint(
                label="write_action_dashboard",
                command=(
                    "python -m orchestrator.operator_action_dashboard "
                    f"{relative_path(run_dir, repo_root)}"
                ),
                reason="Persist the read-only action dashboard.",
                writes_artifact="operator_action_dashboard.json",
            )
        )
    if status == "action_pending":
        commands.append(
            command_hint(
                label="continue_operator_action",
                command=f"python -m orchestrator.experiments action-dashboard {run_id} --markdown",
                reason=str(summary.get("action_current_step", "Continue operator action review.")),
                writes_artifact="",
            )
        )
    if status == "promotion_pending_approval":
        commands.append(
            command_hint(
                label="review_promotion_approval",
                command=(
                    "python -m orchestrator.champion_promotion_approval "
                    f"{relative_path(run_dir, repo_root)}"
                ),
                reason="Preview the explicit promotion approval artifact.",
                writes_artifact="champion_promotion_approval.json",
            )
        )
    return commands


def command_hint(
    *,
    label: str,
    command: str,
    reason: str,
    writes_artifact: str,
) -> dict[str, object]:
    """Return one command hint row."""
    return {
        "label": label,
        "command": command,
        "command_sha256": sha256_text(command),
        "reason": reason,
        "writes_artifact": writes_artifact,
        "boundary": classify_operator_command(
            label=label,
            writes_artifact=writes_artifact,
        ),
    }


def codex_preflight_status(
    *,
    preflight: dict[str, Any],
    blockers: list[str],
) -> str:
    """Return a compact Codex CLI startup preflight status."""
    return codex_cli_execution_preflight_status(
        payload=preflight,
        blocking_errors=blockers,
    )


def codex_preflight_next_step(
    *,
    preflight: dict[str, Any],
    blockers: list[str],
) -> str:
    """Return the next operator-facing step for Codex CLI startup preflight."""
    if not preflight:
        return "run iteration preflight before reviewing Codex CLI unlock"
    if blockers:
        return "inspect Codex CLI preflight blockers before real execution"
    summary = object_field(preflight, "summary")
    if int(summary.get("real_codex_execute_profile_count", 0) or 0) == 0:
        return "keep real Codex execution disabled unless explicitly reviewed"
    ready_count = int(summary.get("operator_unlock_ready_count", 0) or 0)
    real_count = int(summary.get("real_codex_execute_profile_count", 0) or 0)
    if ready_count != real_count:
        return "complete operator unlock evidence before real execution review"
    return "review operator unlock evidence before any real Codex execution"


def codex_readiness_diff_next_step(payload: dict[str, Any]) -> str:
    """Return the next operator-facing step for the Codex CLI readiness diff."""
    if not payload:
        return "write Codex CLI execution readiness diff before real execution review"
    status = str(payload.get("status", "missing"))
    if status == "ready":
        return "review startup preflight authority before real execution"
    if status == "drift_detected":
        return "regenerate reviewed Codex CLI evidence before real execution"
    if status == "missing_evidence":
        return "generate missing Codex CLI readiness artifacts before review"
    return "inspect Codex CLI readiness blockers before real execution"


def codex_unlock_runbook_next_step(payload: dict[str, Any]) -> str:
    """Return the next operator-facing step for the Codex CLI unlock runbook."""
    if not payload:
        return "write Codex CLI unlock runbook before real execution review"
    status = str(payload.get("status", "missing"))
    if status == "ready":
        return "review readiness diff before any real Codex execution"
    if status == "blocked":
        return "inspect blocked Codex CLI unlock runbook steps"
    if status == "needs_artifacts":
        return "generate missing Codex CLI unlock evidence artifacts"
    return "inspect Codex CLI unlock runbook"


def render_operator_cockpit_markdown(payload: dict[str, object]) -> str:
    """Render an operator cockpit as markdown."""
    summary = object_field(payload, "summary")
    digest = object_field(payload, "operator_digest")
    priority = object_field(payload, "review_priority")
    lines = [
        "# Operator Cockpit",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Primary focus: `{payload.get('primary_focus', '')}`",
        f"- Run status: `{summary.get('run_status', '')}`",
        f"- Run outcome: `{summary.get('run_outcome_category', '')}` "
        f"(`{summary.get('run_outcome_primary_code', '')}`)",
        f"- Config lineage: `{summary.get('config_lineage_status', '')}`",
        f"- Action: `{summary.get('action_status', '')}`",
        f"- Action execution readiness: "
        f"`{summary.get('action_execution_readiness_status', '')}`",
        f"- Action execution ready: `{summary.get('action_execution_ready', False)}`",
        f"- Action path closure: "
        f"`{summary.get('action_path_closure_status', '')}`",
        f"- Action path closed: `{summary.get('action_path_closed', False)}`",
        f"- Candidate quality: `{summary.get('candidate_quality_status', '')}` "
        f"(`{summary.get('candidate_quality_top_failure_code', '')}`)",
        f"- Codex CLI preflight: `{summary.get('codex_preflight_status', '')}`",
        f"- Codex CLI unlock runbook: `{summary.get('codex_unlock_runbook_status', '')}`",
        f"- Codex CLI readiness diff: `{summary.get('codex_readiness_diff_status', '')}`",
        f"- Codex CLI intake binding: `{summary.get('codex_intake_readiness_status', '')}`",
        f"- Codex CLI intake ready: `{summary.get('codex_intake_ready', False)}`",
        f"- Promotion: `{summary.get('promotion_status', '')}`",
        f"- Promotion approval recorded: "
        f"`{summary.get('promotion_approval_recorded', False)}`",
        f"- Promotion receipt: `{summary.get('promotion_receipt_status', '')}`",
        f"- Promotion receipt promoted: "
        f"`{summary.get('promotion_receipt_promoted', False)}`",
        "",
        "## Operator Digest",
        "",
        f"- Headline: {digest.get('headline', '')}",
        f"- Priority: `{digest.get('priority', '')}`",
        f"- Target panel: `{digest.get('target_panel_title', '')}` "
        f"(`{digest.get('target_panel_status', '')}`)",
        f"- Blockers: `{digest.get('blocker_count', 0)}`",
        f"- First blocker: `{digest.get('first_blocker', '')}`",
        f"- Next step: {digest.get('next_step', '')}",
        f"- Next command: `{digest.get('recommended_command_label', '')}`",
        f"- Command boundary: "
        f"`{object_field(digest, 'recommended_command_boundary').get('boundary_type', '')}`",
        f"- Command SHA-256: `{digest.get('recommended_command_sha256', '')}`",
        f"- Command hint: `{digest.get('recommended_command', '')}`",
        "",
        "## Review Priority",
        "",
        f"- Priority: `{priority.get('priority', '')}`",
        f"- Primary reason: `{priority.get('primary_reason', '')}`",
        f"- Target panel: `{priority.get('target_panel_title', '')}` "
        f"(`{priority.get('target_panel_status', '')}`)",
        f"- Target artifact: `{priority.get('target_artifact_path', '')}`",
        f"- Next step: {priority.get('next_step', '')}",
        f"- Recommended command: `{priority.get('recommended_command', '')}`",
        f"- Recommended command SHA-256: "
        f"`{priority.get('recommended_command_sha256', '')}`",
        f"- Recommended command boundary: "
        f"`{object_field(priority, 'recommended_command_boundary').get('boundary_type', '')}`",
        "",
        "## Panels",
        "",
        "| Panel | Status | OK | Next Step |",
        "| --- | --- | --- | --- |",
    ]
    for row in list_of_dicts(payload.get("panels", [])):
        lines.append(
            "| "
            f"{row.get('title', '')} | "
            f"`{row.get('status', '')}` | "
            f"`{row.get('ok', False)}` | "
            f"{row.get('next_step', '')} |"
        )
    freshness = object_field(payload, "snapshot_freshness")
    if freshness:
        lines.extend(
            [
                "",
                "## Snapshot Freshness",
                "",
                f"- Status: `{freshness.get('status', '')}`",
                f"- OK: `{freshness.get('ok', False)}`",
                f"- Stale sources: `{freshness.get('stale_count', 0)}`",
                f"- Refresh command: `{freshness.get('recommended_command', '')}`",
                "- Refresh command SHA-256: "
                f"`{freshness.get('recommended_command_sha256', '')}`",
                "",
            ]
        )
        stale_sources = string_rows(freshness.get("stale_sources", []))
        lines.extend([f"- `{source}`" for source in stale_sources] or ["- none"])
    lines.extend(["", "## Blockers", ""])
    blockers = string_rows(payload.get("blockers", []))
    lines.extend([f"- `{blocker}`" for blocker in blockers] or ["- none"])
    lines.extend(["", "## Action Failure Reasons", ""])
    action_reasons = list_of_dicts(payload.get("action_failure_reasons", []))
    lines.extend(
        [
            (
                f"- `{reason.get('stage', '')}` / `{reason.get('code', '')}`: "
                f"{reason.get('detail', '')}"
            )
            for reason in action_reasons
        ]
        or ["- none"]
    )
    lines.extend(["", "## Recommended Commands", ""])
    for command in list_of_dicts(payload.get("recommended_commands", [])):
        boundary = object_field(command, "boundary")
        lines.append(
            f"- `{command.get('label', '')}` "
            f"(`{boundary.get('boundary_type', '')}`): "
            f"`{command.get('command', '')}` "
            f"[sha256 `{str(command.get('command_sha256', ''))[:12]}`]"
        )
    checklist = object_field(payload, "codex_unlock_checklist")
    lines.extend(
        [
            "",
            "## Codex Unlock Checklist",
            "",
            f"- Status: `{checklist.get('status', '')}`",
            f"- Ready: `{checklist.get('ready', False)}`",
            f"- Failed items: `{checklist.get('failed_count', 0)}`",
            f"- Next step: {checklist.get('next_step', '')}",
            "",
            "| Check | Status | Evidence | Next Step |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in list_of_dicts(checklist.get("items", [])):
        lines.append(
            "| "
            f"{item.get('label', '')} | "
            f"`{item.get('status', '')}` | "
            f"{item.get('evidence', '')} | "
            f"{item.get('next_step', '')} |"
        )
    if not list_of_dicts(checklist.get("items", [])):
        lines.append("| none | `not_applicable` | no real Codex profile requires unlock | |")
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This cockpit is read-only and does not record approvals or execute commands.",
            "- It does not execute agents, run backtests, write config, promote champions, apply patches, route agents, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_operator_cockpit_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved operator cockpit artifact."""
    schema_errors = tuple(
        validate_json_file(payload_path=payload_path, schema_path=repo_root / SCHEMA_PATH)
    )
    if schema_errors:
        return schema_errors
    return schema_errors + validate_operator_cockpit_consistency(
        load_json_object(payload_path)
    )


def validate_operator_cockpit_payload(
    payload: dict[str, object],
    *,
    run_dir: Path | None = None,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an in-memory operator cockpit payload."""
    repo_root = repo_root.resolve()
    comparable_payload = strip_terminal_metadata(payload)
    schema = load_json_object(repo_root / SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=comparable_payload,
            schema=schema,
            schema_dir=(repo_root / SCHEMA_PATH).parent,
        )
    )
    errors.extend(validate_operator_cockpit_consistency(comparable_payload))
    if require_current_evidence:
        if run_dir is None:
            errors.append("operator_cockpit run_dir required")
        else:
            resolved_run_dir = resolve_path(run_dir, repo_root)
            resolved_experiments_dir = resolve_path(experiments_dir, repo_root)
            expected = build_operator_cockpit(
                run_dir=resolved_run_dir,
                experiments_dir=resolved_experiments_dir,
                repo_root=repo_root,
            )
            errors.extend(
                validate_operator_cockpit_source_artifacts(
                    comparable_payload,
                    expected=expected,
                )
            )
            errors.extend(
                validate_operator_cockpit_snapshot_freshness(
                    payload,
                    comparable_payload=comparable_payload,
                    repo_root=repo_root,
                )
            )
            if comparable_payload != expected:
                errors.append("operator_cockpit current evidence mismatch")
    return tuple(errors)


def strip_terminal_metadata(payload: dict[str, object]) -> dict[str, object]:
    """Return payload without terminal-only annotation fields."""
    stripped = dict(payload)
    stripped.pop("from_artifact", None)
    stripped.pop("snapshot_freshness", None)
    return stripped


def validate_operator_cockpit_consistency(
    payload: dict[str, object],
) -> tuple[str, ...]:
    """Validate derived operator cockpit fields against the saved payload."""
    errors: list[str] = []
    summary = object_field(payload, "summary")
    status = str(payload.get("status", ""))
    blockers = string_rows(payload.get("blockers", []))
    panels = list_of_dicts(payload.get("panels", []))
    commands = list_of_dicts(payload.get("recommended_commands", []))
    action_failure_reasons = list_of_dicts(payload.get("action_failure_reasons", []))
    unlock_checklist = object_field(payload, "codex_unlock_checklist")
    intake_readiness = object_field(payload, "codex_intake_readiness")
    review_priority = object_field(payload, "review_priority")
    operator_digest = object_field(payload, "operator_digest")

    if bool(payload.get("ok", False)) != (
        status not in {"needs_repair", "missing_closeout"}
    ):
        errors.append("operator_cockpit ok status mismatch")
    if str(payload.get("primary_focus", "")) != primary_focus(
        status=status,
        summary=summary,
    ):
        errors.append("operator_cockpit primary_focus mismatch")
    if status != cockpit_status(summary=summary, blockers=blockers):
        errors.append("operator_cockpit status summary mismatch")
    expected_digest = cockpit_operator_digest(
        status=status,
        summary=summary,
        blockers=blockers,
        review_priority=review_priority,
    )
    if operator_digest != expected_digest:
        errors.append("operator_cockpit operator_digest mismatch")

    expected_failure_count = len(action_failure_reasons)
    if int(summary.get("action_failure_reason_count", 0) or 0) != expected_failure_count:
        errors.append(
            "operator_cockpit summary action_failure_reason_count mismatch"
        )
    expected_first_failure_stage = (
        str(action_failure_reasons[0].get("stage", ""))
        if action_failure_reasons
        else "none"
    )
    if (
        str(summary.get("action_first_failure_stage", "none"))
        != expected_first_failure_stage
    ):
        errors.append(
            "operator_cockpit summary action_first_failure_stage mismatch"
        )
    for reason in action_failure_reasons:
        reason_code = str(reason.get("code", ""))
        if reason_code and f"operator_action:{reason_code}" not in blockers:
            errors.append("operator_cockpit action failure blocker missing")
            break

    if len(blockers) > 0 and status != "needs_operator_review":
        errors.append("operator_cockpit blockers status mismatch")
    if status == "action_pending" and summary.get("action_status") not in {
        "pending_approval",
        "ready_for_execution",
    }:
        errors.append("operator_cockpit action_pending summary mismatch")
    if (
        status == "promotion_pending_approval"
        and summary.get("promotion_would_promote") is not True
    ):
        errors.append("operator_cockpit promotion_pending summary mismatch")

    checklist_items = list_of_dicts(unlock_checklist.get("items", []))
    checklist_passed_items = [
        row for row in checklist_items if str(row.get("status", "")) == "passed"
    ]
    checklist_failed_items = [
        row for row in checklist_items if str(row.get("status", "")) == "failed"
    ]
    if int(unlock_checklist.get("item_count", 0) or 0) != len(checklist_items):
        errors.append("operator_cockpit codex unlock item_count mismatch")
    if int(unlock_checklist.get("passed_count", 0) or 0) != len(
        checklist_passed_items
    ):
        errors.append("operator_cockpit codex unlock passed_count mismatch")
    if int(unlock_checklist.get("failed_count", 0) or 0) != len(
        checklist_failed_items
    ):
        errors.append("operator_cockpit codex unlock failed_count mismatch")
    if bool(unlock_checklist.get("ready", False)) and checklist_failed_items:
        errors.append("operator_cockpit codex unlock ready mismatch")
    if not intake_readiness:
        errors.append("operator_cockpit intake readiness missing")
    else:
        errors.extend(validate_codex_cli_intake_readiness(intake_readiness))
        if str(summary.get("codex_intake_readiness_status", "")) != str(
            intake_readiness.get("status", "")
        ):
            errors.append("operator_cockpit summary intake status mismatch")
        if bool(summary.get("codex_intake_ready", False)) != bool(
            intake_readiness.get("ready", False)
        ):
            errors.append("operator_cockpit summary intake ready mismatch")
        if int(summary.get("codex_intake_blocker_count", -1)) != int(
            intake_readiness.get("blocking_reason_count", 0) or 0
        ):
            errors.append("operator_cockpit summary intake blocker mismatch")

    errors.extend(
        validate_operator_cockpit_review_priority_consistency(
            payload=payload,
            panels=panels,
            commands=commands,
        )
    )
    return tuple(errors)


def validate_operator_cockpit_source_artifacts(
    payload: dict[str, object],
    *,
    expected: dict[str, object],
) -> tuple[str, ...]:
    """Validate cockpit source artifact records match current evidence."""
    errors: list[str] = []
    source_payload = object_field(payload, "source_artifacts")
    expected_sources = object_field(expected, "source_artifacts")
    for source_name, expected_record in expected_sources.items():
        if source_payload.get(source_name) != expected_record:
            errors.append(
                f"operator_cockpit source_artifacts {source_name} mismatch"
            )
    return tuple(errors)


def validate_operator_cockpit_snapshot_freshness(
    payload: dict[str, object],
    *,
    comparable_payload: dict[str, object],
    repo_root: Path,
) -> tuple[str, ...]:
    """Validate transient snapshot freshness matches current source files."""
    if "snapshot_freshness" not in payload:
        return ()
    errors: list[str] = []
    freshness = object_field(payload, "snapshot_freshness")
    expected = cockpit_snapshot_freshness(
        payload=comparable_payload,
        repo_root=repo_root,
    )
    for field_name in (
        "schema_version",
        "ok",
        "status",
        "source_count",
        "fresh_count",
        "stale_count",
        "stale_sources",
        "rows",
        "recommended_command",
        "recommended_command_sha256",
        "policy",
    ):
        if freshness.get(field_name) != expected.get(field_name):
            errors.append(
                f"operator_cockpit snapshot_freshness {field_name} mismatch"
            )
    return tuple(errors)


def validate_operator_cockpit_review_priority_consistency(
    *,
    payload: dict[str, object],
    panels: list[dict[str, Any]],
    commands: list[dict[str, Any]],
) -> tuple[str, ...]:
    """Validate cockpit review priority references saved panel and command rows."""
    errors: list[str] = []
    priority = object_field(payload, "review_priority")
    target_panel_id = str(priority.get("target_panel_id", ""))
    target_panel = next(
        (row for row in panels if str(row.get("panel_id", "")) == target_panel_id),
        None,
    )
    if target_panel is None:
        errors.append("operator_cockpit review_priority target panel missing")
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
            if str(priority.get(priority_key, "")) != str(target_panel.get(panel_key, "")):
                errors.append(error)
        if bool(priority.get("target_artifact_exists", False)) != bool(
            target_panel.get("artifact_exists", False)
        ):
            errors.append(
                "operator_cockpit review_priority target artifact exists mismatch"
            )

    command_label = str(priority.get("recommended_command_label", ""))
    if str(priority.get("recommended_command_sha256", "")) != sha256_text(
        str(priority.get("recommended_command", ""))
    ):
        errors.append("operator_cockpit review_priority command sha256 mismatch")
    command = next(
        (row for row in commands if str(row.get("label", "")) == command_label),
        None,
    )
    if command is None:
        errors.append("operator_cockpit review_priority command label missing")
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
            (
                "recommended_command_sha256",
                "command_sha256",
                "operator_cockpit review_priority command sha256 mismatch",
            ),
        ):
            if str(priority.get(priority_key, "")) != str(command.get(command_key, "")):
                errors.append(error)
        if object_field(priority, "recommended_command_boundary") != object_field(
            command,
            "boundary",
        ):
            errors.append(
                "operator_cockpit review_priority command boundary mismatch"
            )

    for command in commands:
        label = str(command.get("label", ""))
        writes_artifact = str(command.get("writes_artifact", ""))
        expected_boundary = classify_operator_command(
            label=label,
            writes_artifact=writes_artifact,
        )
        if object_field(command, "boundary") != expected_boundary:
            errors.append("operator_cockpit command boundary mismatch")
            break
        if str(command.get("command_sha256", "")) != sha256_text(
            str(command.get("command", ""))
        ):
            errors.append("operator_cockpit command sha256 mismatch")
            break

    return tuple(errors)


def list_of_dicts(value: object) -> list[dict[str, Any]]:
    """Return object rows from a possible list."""
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def string_rows(value: object) -> list[str]:
    """Return string rows from a possible list."""
    return [str(row) for row in value] if isinstance(value, list) else []


def unique_strings(values: list[str]) -> list[str]:
    """Return values in stable first-seen order."""
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        if value and value not in seen:
            rows.append(value)
            seen.add(value)
    return rows


def relative_path(path: Path, repo_root: Path) -> str:
    """Return a stable repository-relative path when possible."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def main() -> None:
    """CLI entrypoint for operator cockpit generation."""
    parser = argparse.ArgumentParser(
        description="Write a read-only operator cockpit for one iteration run."
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    _, _, payload = write_operator_cockpit(
        run_dir=args.run_dir,
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
