"""Read-only operator action status dashboard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.operator_action_audit import (
    OPERATOR_ACTION_AUDIT_SCHEMA_VERSION,
    build_operator_action_audit,
    file_record,
    list_of_dicts,
    load_json_object,
    object_field,
    resolve_path,
    schema_errors,
    string_list,
)
from orchestrator.operator_command_boundaries import classify_operator_command
from orchestrator.operator_action_executor import command_is_allowlisted, parse_command
from orchestrator.operator_action_plan import build_operator_action_plan
from orchestrator.schema_validation import validate_json_file, validate_json_payload


OPERATOR_ACTION_DASHBOARD_SCHEMA_VERSION = "operator_action_dashboard_v1"
SCHEMA_PATH = Path("schemas/operator_action_dashboard.schema.json")
APPROVAL_CONFIRMATION_PHRASE = "APPROVE OPERATOR ACTION"


def write_operator_action_dashboard(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown operator action dashboard artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    payload = build_operator_action_dashboard(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    errors = validate_operator_action_dashboard_payload(
        payload,
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "operator action dashboard failed schema validation: "
            + "; ".join(errors)
        )
    json_path = run_dir / "operator_action_dashboard.json"
    md_path = run_dir / "operator_action_dashboard.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(
        render_operator_action_dashboard_markdown(payload),
        encoding="utf-8",
    )
    errors = validate_operator_action_dashboard_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(
            "operator action dashboard failed schema validation: "
            + "; ".join(errors)
        )
    return json_path, md_path, payload


def build_operator_action_dashboard(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return a compact read-only dashboard for operator action state."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    plan_path = run_dir / "operator_action_plan.json"
    approval_path = run_dir / "operator_action_approval.json"
    execution_path = run_dir / "operator_action_execution_receipt.json"
    audit_path = run_dir / "operator_action_audit.json"

    audit = build_operator_action_audit(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    audit_from_artifact = audit_path.exists()
    if plan_path.exists():
        plan = load_json_object(plan_path)
    else:
        plan = build_operator_action_plan(
            run_dir=run_dir,
            experiments_dir=experiments_dir,
            repo_root=repo_root,
        )
    approval = load_json_object(approval_path)
    execution = load_json_object(execution_path)
    status = dashboard_status(audit=audit)
    current_step = dashboard_current_step(status=status)
    failure_reasons = dashboard_failure_reasons(audit=audit)
    blockers = dashboard_blockers(audit=audit, approval=approval, execution=execution)
    actions = available_action_rows(plan=plan)
    timeline = dashboard_timeline(
        plan_path=plan_path,
        approval=approval,
        approval_path=approval_path,
        execution=execution,
        execution_path=execution_path,
        audit=audit,
        audit_path=audit_path,
    )
    commands = recommended_commands(
        status=status,
        actions=actions,
        run_id=str(audit.get("run_id", plan.get("run_id", run_dir.name))),
        run_dir=run_dir,
        approval_path=approval_path,
        repo_root=repo_root,
        audit_from_artifact=audit_from_artifact,
    )
    selected_command = object_field(audit, "selected_command")
    sources = {
        "action_plan": source_artifact(
            path=plan_path,
            artifact_name="operator_action_plan",
            schema_path=repo_root / "schemas/operator_action_plan.schema.json",
            repo_root=repo_root,
        ),
        "action_approval": source_artifact(
            path=approval_path,
            artifact_name="operator_action_approval",
            schema_path=repo_root / "schemas/operator_action_approval.schema.json",
            repo_root=repo_root,
        ),
        "execution_receipt": source_artifact(
            path=execution_path,
            artifact_name="operator_action_execution_receipt",
            schema_path=repo_root
            / "schemas/operator_action_execution_receipt.schema.json",
            repo_root=repo_root,
        ),
        "action_audit": source_artifact(
            path=audit_path,
            artifact_name="operator_action_audit",
            schema_path=repo_root / "schemas/operator_action_audit.schema.json",
            repo_root=repo_root,
            from_artifact=audit_from_artifact,
        ),
    }

    return {
        "schema_version": OPERATOR_ACTION_DASHBOARD_SCHEMA_VERSION,
        "run_id": str(audit.get("run_id", plan.get("run_id", run_dir.name))),
        "run_dir": str(run_dir),
        "status": status,
        "ok": status not in {"needs_chain_repair", "missing_action_plan"},
        "current_step": current_step,
        "primary_prompt": primary_prompt(status=status),
        "source_artifacts": sources,
        "summary": dashboard_summary(audit=audit, actions=actions, blockers=blockers),
        "timeline": timeline,
        "selected_action": object_field(audit, "selected_action"),
        "selected_command": selected_command,
        "available_actions": actions,
        "failure_reasons": failure_reasons,
        "blockers": blockers,
        "recommended_commands": commands,
        "execution_readiness": execution_readiness_summary(
            status=status,
            current_step=current_step,
            sources=sources,
            timeline=timeline,
            blockers=blockers,
            recommended_commands=commands,
            selected_command=selected_command,
        ),
        "path_closure": path_closure_summary(
            status=status,
            current_step=current_step,
            sources=sources,
            timeline=timeline,
            summary=dashboard_summary(audit=audit, actions=actions, blockers=blockers),
            blockers=blockers,
            selected_command=selected_command,
        ),
        "authority": {
            "approval_required_before_execution": True,
            "execution_must_use_guarded_executor": True,
            "final_acceptance_authority": "deterministic_policy_gate",
            "dashboard_can_execute_commands": False,
            "dashboard_can_approve_commands": False,
            "dashboard_can_change_repository": False,
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


def path_closure_summary(
    *,
    status: str,
    current_step: str,
    sources: dict[str, object],
    timeline: list[dict[str, object]],
    summary: dict[str, object],
    blockers: list[str],
    selected_command: dict[str, Any],
) -> dict[str, object]:
    """Return deterministic closure evidence for the operator action path."""
    steps = path_closure_steps(
        status=status,
        sources=sources,
        timeline=timeline,
    )
    completed_step_count = sum(1 for row in steps if row["complete"] is True)
    required_step_count = sum(1 for row in steps if row["required"] is True)
    closed = bool(
        status == "execution_completed"
        and not blockers
        and completed_step_count == required_step_count
        and summary.get("chain_ok") is True
        and summary.get("approval_recorded") is True
        and summary.get("execution_completed") is True
    )
    if blockers:
        closure_status = "blocked"
        reason = "operator action path has blockers"
    elif closed:
        closure_status = "closed"
        reason = "approval, guarded execution, audit, and dashboard evidence agree"
    elif status == "ready_for_execution":
        closure_status = "ready_for_guarded_execution"
        reason = "approval is recorded; guarded execution remains"
    elif status == "pending_approval":
        closure_status = "awaiting_operator_approval"
        reason = "operator approval remains before guarded execution"
    elif status == "missing_action_plan":
        closure_status = "missing_action_plan"
        reason = "action plan evidence is missing"
    elif status in {"needs_chain_repair", "chain_inconsistent"}:
        closure_status = "needs_chain_repair"
        reason = "saved action artifacts disagree"
    else:
        closure_status = "open"
        reason = "operator action path is not closed yet"
    return {
        "schema_version": "operator_action_path_closure_v1",
        "status": closure_status,
        "closed": closed,
        "reason": reason,
        "current_step": current_step,
        "completed_step_count": completed_step_count,
        "required_step_count": required_step_count,
        "approval_recorded": bool(summary.get("approval_recorded", False)),
        "execution_completed": bool(summary.get("execution_completed", False)),
        "audit_chain_ok": bool(summary.get("chain_ok", False)),
        "dashboard_consistency_checked": True,
        "selected_command_label": str(selected_command.get("label", "")),
        "selected_command_digest_matches_plan": bool(
            selected_command.get("digest_matches_plan", False)
        ),
        "blocker_count": len(blockers),
        "blockers": blockers[:5],
        "steps": steps,
        "policy": {
            "inspection_only": True,
            "does_not_execute_commands": True,
            "does_not_record_approval": True,
            "does_not_change_acceptance": True,
        },
    }


def path_closure_steps(
    *,
    status: str,
    sources: dict[str, object],
    timeline: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return stable step rows for path closure evidence."""
    timeline_by_step = {
        str(row.get("step", "")): row for row in timeline if isinstance(row, dict)
    }
    artifact_to_source_key = {
        "operator_action_plan": "action_plan",
        "operator_action_approval": "action_approval",
        "operator_action_execution_receipt": "execution_receipt",
        "operator_action_audit": "action_audit",
    }
    artifact_to_step = {
        "operator_action_plan": "action_plan",
        "operator_action_approval": "operator_approval",
        "operator_action_execution_receipt": "guarded_execution",
        "operator_action_audit": "action_audit",
    }
    required_by_artifact = {
        "operator_action_plan": True,
        "operator_action_approval": status
        in {
            "ready_for_execution",
            "execution_completed",
            "execution_blocked",
            "execution_failed",
        },
        "operator_action_execution_receipt": status == "execution_completed",
        "operator_action_audit": status != "missing_action_plan",
    }
    complete_statuses = {
        "operator_action_plan": {"complete", "derived"},
        "operator_action_approval": {"complete"},
        "operator_action_execution_receipt": {"complete"},
        "operator_action_audit": {"complete", "derived"},
    }
    rows: list[dict[str, object]] = []
    for artifact_name in (
        "operator_action_plan",
        "operator_action_approval",
        "operator_action_execution_receipt",
        "operator_action_audit",
    ):
        source = sources.get(artifact_to_source_key[artifact_name], {})
        if not isinstance(source, dict):
            source = {}
        file_info = object_field(source, "file")
        timeline_row = timeline_by_step.get(artifact_to_step[artifact_name], {})
        timeline_status = str(timeline_row.get("status", ""))
        required = bool(required_by_artifact.get(artifact_name, False))
        complete = bool(
            timeline_status in complete_statuses[artifact_name]
            and not string_list(source.get("schema_errors", []))
        )
        rows.append(
            {
                "artifact_name": artifact_name,
                "phase": artifact_to_step[artifact_name],
                "required": required,
                "complete": complete,
                "status": timeline_status,
                "path": str(file_info.get("path", "")),
                "schema_error_count": len(string_list(source.get("schema_errors", []))),
            }
        )
    rows.append(
        {
            "artifact_name": "operator_action_dashboard",
            "phase": "dashboard",
            "required": True,
            "complete": status == "execution_completed",
            "status": status,
            "path": "operator_action_dashboard.json",
            "schema_error_count": 0,
        }
    )
    return rows


def execution_readiness_summary(
    *,
    status: str,
    current_step: str,
    sources: dict[str, object],
    timeline: list[dict[str, object]],
    blockers: list[str],
    recommended_commands: list[dict[str, object]],
    selected_command: dict[str, Any],
) -> dict[str, object]:
    """Return deterministic pre-execution readiness for the operator action chain."""
    next_command = recommended_commands[0] if recommended_commands else {}
    next_boundary = object_field(next_command, "boundary")
    dependency_rows = execution_dependency_rows(
        sources=sources,
        timeline=timeline,
        status=status,
    )
    missing_artifacts = [
        str(row["artifact_name"])
        for row in dependency_rows
        if row["required"] is True and row["passed"] is not True
    ]
    if blockers:
        readiness_status = "blocked"
        ready = False
        reason = "action chain has blockers"
    elif status == "ready_for_execution":
        readiness_status = "ready_for_guarded_execution"
        ready = True
        reason = "approval is recorded and guarded execution can be invoked"
    elif status == "pending_approval":
        readiness_status = "needs_operator_approval"
        ready = False
        reason = "operator approval must be recorded first"
    elif status == "execution_completed":
        readiness_status = "execution_completed"
        ready = False
        reason = "execution receipt is already complete"
    elif status in {"execution_blocked", "execution_failed"}:
        readiness_status = status
        ready = False
        reason = "inspect execution receipt before retrying"
    elif status in {"needs_chain_repair", "chain_inconsistent"}:
        readiness_status = "needs_chain_repair"
        ready = False
        reason = "repair action chain evidence before execution"
    elif status == "missing_action_plan":
        readiness_status = "missing_action_plan"
        ready = False
        reason = "generate action plan before execution review"
    else:
        readiness_status = "review_required"
        ready = False
        reason = "review action dashboard before execution"

    return {
        "schema_version": "operator_action_execution_readiness_v1",
        "status": readiness_status,
        "ready": ready,
        "reason": reason,
        "current_step": current_step,
        "next_command_label": str(next_command.get("label", "")),
        "next_command_boundary": str(next_boundary.get("boundary_type", "")),
        "requires_operator_approval": bool(
            next_boundary.get("requires_operator_approval", False)
        ),
        "uses_guarded_executor": bool(
            next_boundary.get("uses_guarded_executor", False)
        ),
        "selected_command_label": str(selected_command.get("label", "")),
        "selected_command_digest_matches_plan": bool(
            selected_command.get("digest_matches_plan", False)
        ),
        "blocker_count": len(blockers),
        "blockers": blockers[:5],
        "missing_artifact_count": len(missing_artifacts),
        "missing_artifacts": missing_artifacts,
        "dependencies": dependency_rows,
        "policy": {
            "inspection_only": True,
            "does_not_execute_commands": True,
            "does_not_record_approval": True,
            "does_not_change_acceptance": True,
        },
    }


def execution_dependency_rows(
    *,
    sources: dict[str, object],
    timeline: list[dict[str, object]],
    status: str,
) -> list[dict[str, object]]:
    """Return dependency rows used by the action execution readiness summary."""
    timeline_by_step = {
        str(row.get("step", "")): row for row in timeline if isinstance(row, dict)
    }
    required_by_artifact = {
        "operator_action_plan": True,
        "operator_action_audit": status != "missing_action_plan",
        "operator_action_approval": status
        in {
            "ready_for_execution",
            "execution_completed",
            "execution_blocked",
            "execution_failed",
        },
        "operator_action_execution_receipt": status == "execution_completed",
    }
    timeline_step_by_artifact = {
        "operator_action_plan": "action_plan",
        "operator_action_audit": "action_audit",
        "operator_action_approval": "operator_approval",
        "operator_action_execution_receipt": "guarded_execution",
    }
    rows: list[dict[str, object]] = []
    for source_key in (
        "action_plan",
        "action_audit",
        "action_approval",
        "execution_receipt",
    ):
        source_record = sources.get(source_key, {})
        if not isinstance(source_record, dict):
            source_record = {}
        source = object_field(source_record, "file")
        artifact_name = str(source_record.get("artifact_name", ""))
        timeline_row = timeline_by_step.get(
            timeline_step_by_artifact.get(artifact_name, ""),
            {},
        )
        exists = bool(source.get("exists", False))
        required = bool(required_by_artifact.get(artifact_name, False))
        rows.append(
            {
                "artifact_name": artifact_name,
                "required": required,
                "exists": exists,
                "passed": (not required) or exists,
                "timeline_status": str(timeline_row.get("status", "")),
                "path": str(source.get("path", "")),
            }
        )
    return rows


def dashboard_status(*, audit: dict[str, Any]) -> str:
    """Return dashboard status derived from the audit chain."""
    audit_status = str(audit.get("status", ""))
    if not audit:
        return "missing_action_plan"
    if audit.get("ok") is not True:
        return "needs_chain_repair"
    return audit_status or "needs_chain_repair"


def dashboard_current_step(*, status: str) -> str:
    """Return the next operator step key."""
    return {
        "missing_action_plan": "regenerate_action_plan",
        "chain_inconsistent": "repair_action_chain",
        "needs_chain_repair": "repair_action_chain",
        "pending_approval": "record_operator_approval",
        "approval_blocked": "fix_operator_approval",
        "ready_for_execution": "execute_approved_command",
        "execution_completed": "review_execution_receipt",
        "execution_blocked": "inspect_execution_blockers",
        "execution_failed": "inspect_execution_failure",
    }.get(status, "inspect_action_chain")


def primary_prompt(*, status: str) -> str:
    """Return a compact operator-facing prompt."""
    prompts = {
        "pending_approval": "Choose one action-plan command and record approval.",
        "ready_for_execution": "Run the approved command through the guarded executor.",
        "execution_completed": "Review the execution output hashes and next action.",
        "approval_blocked": "Fix the approval blockers before execution.",
        "execution_blocked": "Inspect why the guarded executor blocked the command.",
        "execution_failed": "Inspect the failed execution receipt before retrying.",
        "needs_chain_repair": "Regenerate or repair inconsistent action artifacts.",
        "missing_action_plan": "Generate the action plan from run closeout first.",
    }
    return prompts.get(status, "Inspect the operator action artifact chain.")


def available_action_rows(*, plan: dict[str, Any]) -> list[dict[str, object]]:
    """Return compact action and command rows from an action plan."""
    rows: list[dict[str, object]] = []
    for action in list_of_dicts(plan.get("actions", [])):
        commands = [
            command_row(command)
            for command in list_of_dicts(action.get("command_candidates", []))
        ]
        rows.append(
            {
                "action_id": str(action.get("action_id", "")),
                "action_type": str(action.get("action_type", "")),
                "status": str(action.get("status", "")),
                "source_text": str(action.get("source_text", "")),
                "command_count": len(commands),
                "safe_command_count": sum(
                    1 for command in commands if command["guarded_read_only"] is True
                ),
                "commands": commands,
            }
        )
    return rows


def command_row(command: dict[str, Any]) -> dict[str, object]:
    """Return a compact command candidate row."""
    command_text = str(command.get("command", ""))
    writes_repository = bool(command.get("writes_repository", False))
    promotes_champion = bool(command.get("promotes_champion", False))
    runs_backtests = bool(command.get("runs_backtests", False))
    allowlisted = command_is_allowlisted(parse_command(command_text))
    return {
        "label": str(command.get("label", "")),
        "command": command_text,
        "command_sha256": str(command.get("command_sha256", "")),
        "expected_artifact": str(command.get("expected_artifact", "")),
        "writes_repository": writes_repository,
        "promotes_champion": promotes_champion,
        "runs_backtests": runs_backtests,
        "allowlisted_for_guarded_execution": allowlisted,
        "guarded_read_only": (
            allowlisted
            and not writes_repository
            and not promotes_champion
            and not runs_backtests
        ),
    }


def dashboard_blockers(
    *,
    audit: dict[str, Any],
    approval: dict[str, Any],
    execution: dict[str, Any],
) -> list[str]:
    """Return stable blocker codes from action artifacts."""
    blockers: list[str] = []
    checks = object_field(audit, "chain_checks")
    blockers.extend(
        str(reason.get("code", ""))
        for reason in dashboard_failure_reasons(audit=audit)
        if reason.get("code")
    )
    for key in (
        "plan_schema_errors",
        "approval_schema_errors",
        "execution_schema_errors",
        "consistency_errors",
    ):
        blockers.extend(string_list(checks.get(key, [])))
    blockers.extend(
        string_list(object_field(approval, "approval_gate").get("approval_blockers", []))
    )
    blockers.extend(string_list(object_field(execution, "evidence_checks").get("blockers", [])))
    return unique_preserving_order(blockers)


def dashboard_failure_reasons(*, audit: dict[str, Any]) -> list[dict[str, object]]:
    """Return compact failure reasons from the action audit."""
    rows: list[dict[str, object]] = []
    reasons = object_field(audit, "chain_checks").get("failure_reasons", [])
    for reason in list_of_dicts(reasons):
        rows.append(
            {
                "stage": str(reason.get("stage", "")),
                "code": str(reason.get("code", "")),
                "severity": str(reason.get("severity", "")),
                "detail": str(reason.get("detail", "")),
            }
        )
    return rows


def dashboard_summary(
    *,
    audit: dict[str, Any],
    actions: list[dict[str, object]],
    blockers: list[str],
) -> dict[str, object]:
    """Return compact dashboard summary values."""
    audit_summary = object_field(audit, "summary")
    return {
        "action_count": int(audit_summary.get("action_count", len(actions)) or 0),
        "command_candidate_count": int(
            audit_summary.get(
                "command_candidate_count",
                sum(int(action.get("command_count", 0) or 0) for action in actions),
            )
            or 0
        ),
        "safe_command_count": sum(
            int(action.get("safe_command_count", 0) or 0) for action in actions
        ),
        "approval_present": bool(audit_summary.get("approval_present", False)),
        "approval_recorded": bool(audit_summary.get("approval_recorded", False)),
        "execution_present": bool(audit_summary.get("execution_present", False)),
        "execution_completed": bool(audit_summary.get("execution_completed", False)),
        "chain_ok": bool(audit_summary.get("chain_ok", False)),
        "failure_reason_count": int(audit_summary.get("failure_reason_count", 0) or 0),
        "first_failure_stage": str(audit_summary.get("first_failure_stage", "none")),
        "blocker_count": len(blockers),
    }


def dashboard_timeline(
    *,
    plan_path: Path,
    approval: dict[str, Any],
    approval_path: Path,
    execution: dict[str, Any],
    execution_path: Path,
    audit: dict[str, Any],
    audit_path: Path,
) -> list[dict[str, object]]:
    """Return action chain timeline rows."""
    return [
        timeline_row(
            step="action_plan",
            label="Action plan",
            status="complete" if plan_path.exists() else "derived",
            artifact_path=plan_path,
        ),
        timeline_row(
            step="operator_approval",
            label="Operator approval",
            status=approval_status(approval=approval, path=approval_path),
            artifact_path=approval_path,
        ),
        timeline_row(
            step="guarded_execution",
            label="Guarded execution",
            status=execution_status(execution=execution, path=execution_path),
            artifact_path=execution_path,
        ),
        timeline_row(
            step="action_audit",
            label="Action audit",
            status=audit_status(audit=audit, path=audit_path),
            artifact_path=audit_path,
        ),
    ]


def timeline_row(
    *,
    step: str,
    label: str,
    status: str,
    artifact_path: Path,
) -> dict[str, object]:
    """Return one compact timeline row."""
    return {
        "step": step,
        "label": label,
        "status": status,
        "artifact_path": artifact_path.as_posix(),
        "artifact_exists": artifact_path.exists(),
    }


def approval_status(*, approval: dict[str, Any], path: Path) -> str:
    """Return compact approval status."""
    if not path.exists():
        return "missing"
    if approval.get("status") == "approval_recorded":
        return "complete"
    return "blocked"


def execution_status(*, execution: dict[str, Any], path: Path) -> str:
    """Return compact execution status."""
    if not path.exists():
        return "missing"
    if execution.get("status") == "completed":
        return "complete"
    return str(execution.get("status", "present"))


def audit_status(*, audit: dict[str, Any], path: Path) -> str:
    """Return compact audit status."""
    if path.exists():
        return "complete" if audit.get("ok") is True else "inconsistent"
    return "derived" if audit.get("schema_version") == OPERATOR_ACTION_AUDIT_SCHEMA_VERSION else "missing"


def recommended_commands(
    *,
    status: str,
    actions: list[dict[str, object]],
    run_id: str,
    run_dir: Path,
    approval_path: Path,
    repo_root: Path,
    audit_from_artifact: bool,
) -> list[dict[str, object]]:
    """Return deterministic next command hints without executing them."""
    commands: list[dict[str, object]] = []
    if not audit_from_artifact:
        commands.append(
            command_hint(
                label="write_action_audit",
                command=f"python -m orchestrator.operator_action_audit {relative_path(run_dir, repo_root)}",
                reason="Persist the digest-checked action audit artifact.",
                writes_artifact="operator_action_audit.json",
            )
        )
    if status == "pending_approval":
        action, command = first_guarded_command(actions)
        if action and command:
            commands.append(
                command_hint(
                    label="record_operator_approval",
                    command=(
                        "python -m orchestrator.operator_action_approval "
                        f"{relative_path(run_dir, repo_root)} "
                        f"--action-id {action.get('action_id', '')} "
                        f"--command-label {command.get('label', '')} "
                        "--approve --operator-id <operator> "
                        f"--confirmation-phrase \"{APPROVAL_CONFIRMATION_PHRASE}\""
                    ),
                    reason="Record explicit approval for one guarded read-only command.",
                    writes_artifact="operator_action_approval.json",
                )
            )
    if status == "ready_for_execution":
        commands.append(
            command_hint(
                label="execute_approved_command",
                command=(
                    "python -m orchestrator.operator_action_executor "
                    f"{run_id} --approval-path {relative_path(approval_path, repo_root)}"
                ),
                reason="Run the approved command through the guarded executor.",
                writes_artifact="operator_action_execution_receipt.json",
            )
        )
    if status == "execution_completed":
        commands.append(
            command_hint(
                label="review_execution_receipt",
                command=f"python -m orchestrator.experiments action-execution {run_id} --markdown",
                reason="Inspect saved execution output hashes and mutation evidence.",
                writes_artifact="",
            )
        )
    commands.append(
        command_hint(
            label="review_action_dashboard",
            command=f"python -m orchestrator.experiments action-dashboard {run_id} --markdown",
            reason="Review this read-only operator action dashboard.",
            writes_artifact="",
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
    """Return one command hint with an explicit operator boundary."""
    return {
        "label": label,
        "command": command,
        "reason": reason,
        "writes_artifact": writes_artifact,
        "boundary": classify_operator_command(
            label=label,
            writes_artifact=writes_artifact,
        ),
    }


def first_guarded_command(
    actions: list[dict[str, object]],
) -> tuple[dict[str, object], dict[str, object]]:
    """Return the first guarded read-only command candidate."""
    for action in actions:
        for command in list_of_dicts(action.get("commands", [])):
            if command.get("guarded_read_only") is True:
                return action, command
    return {}, {}


def source_artifact(
    *,
    path: Path,
    artifact_name: str,
    schema_path: Path,
    repo_root: Path,
    from_artifact: bool | None = None,
) -> dict[str, object]:
    """Return a source artifact record."""
    exists = path.exists()
    return {
        "artifact_name": artifact_name,
        "from_artifact": exists if from_artifact is None else from_artifact,
        "file": file_record(path, repo_root),
        "schema_errors": list(schema_errors(path=path, schema_path=schema_path)),
    }


def render_operator_action_dashboard_markdown(payload: dict[str, object]) -> str:
    """Render an operator action dashboard as markdown."""
    summary = object_field(payload, "summary")
    selected_command = object_field(payload, "selected_command")
    readiness = object_field(payload, "execution_readiness")
    closure = object_field(payload, "path_closure")
    lines = [
        "# Operator Action Dashboard",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- Current step: `{payload.get('current_step', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Prompt: {payload.get('primary_prompt', '')}",
        f"- Actions: `{summary.get('action_count', 0)}`",
        f"- Commands: `{summary.get('command_candidate_count', 0)}`",
        f"- Safe commands: `{summary.get('safe_command_count', 0)}`",
        f"- Chain OK: `{summary.get('chain_ok', False)}`",
        f"- Execution readiness: `{readiness.get('status', '')}`",
        f"- Ready for guarded execution: `{readiness.get('ready', False)}`",
        f"- Path closure: `{closure.get('status', '')}`",
        f"- Path closed: `{closure.get('closed', False)}`",
        "",
        "## Execution Readiness",
        "",
        f"- Status: `{readiness.get('status', '')}`",
        f"- Ready: `{readiness.get('ready', False)}`",
        f"- Reason: {readiness.get('reason', '')}",
        f"- Next command: `{readiness.get('next_command_label', '')}`",
        f"- Next command boundary: `{readiness.get('next_command_boundary', '')}`",
        f"- Missing artifacts: `{readiness.get('missing_artifact_count', 0)}`",
        f"- Blockers: `{readiness.get('blocker_count', 0)}`",
        "",
        "| Dependency | Required | Exists | Passed | Status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in list_of_dicts(readiness.get("dependencies", [])):
        lines.append(
            "| "
            f"{row.get('artifact_name', '')} | "
            f"`{row.get('required', False)}` | "
            f"`{row.get('exists', False)}` | "
            f"`{row.get('passed', False)}` | "
            f"`{row.get('timeline_status', '')}` |"
        )
    lines.extend(
        [
            "",
            "## Path Closure",
            "",
            f"- Status: `{closure.get('status', '')}`",
            f"- Closed: `{closure.get('closed', False)}`",
            f"- Reason: {closure.get('reason', '')}",
            f"- Completed steps: `{closure.get('completed_step_count', 0)}` / "
            f"`{closure.get('required_step_count', 0)}`",
            f"- Dashboard consistency checked: "
            f"`{closure.get('dashboard_consistency_checked', False)}`",
            "",
            "| Step | Required | Complete | Status | Schema errors |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in list_of_dicts(closure.get("steps", [])):
        lines.append(
            "| "
            f"{row.get('artifact_name', '')} | "
            f"`{row.get('required', False)}` | "
            f"`{row.get('complete', False)}` | "
            f"`{row.get('status', '')}` | "
            f"`{row.get('schema_error_count', 0)}` |"
        )
    lines.extend(
        [
            "",
        "## Timeline",
        "",
        "| Step | Status | Artifact |",
        "| --- | --- | --- |",
        ]
    )
    for row in list_of_dicts(payload.get("timeline", [])):
        lines.append(
            "| "
            f"{row.get('label', '')} | "
            f"`{row.get('status', '')}` | "
            f"`{row.get('artifact_path', '')}` |"
        )
    lines.extend(
        [
            "",
            "## Selected Command",
            "",
            f"- Label: `{selected_command.get('label', '')}`",
            f"- SHA-256: `{selected_command.get('command_sha256', '')}`",
            f"- Digest matches plan: `{selected_command.get('digest_matches_plan', False)}`",
            "",
            "## Blockers",
            "",
        ]
    )
    blockers = string_list(payload.get("blockers", []))
    lines.extend([f"- `{blocker}`" for blocker in blockers] or ["- none"])
    lines.extend(["", "## Failure Reasons", ""])
    failure_reasons = list_of_dicts(payload.get("failure_reasons", []))
    lines.extend(
        [
            (
                f"- `{reason.get('stage', '')}` / `{reason.get('code', '')}`: "
                f"{reason.get('detail', '')}"
            )
            for reason in failure_reasons
        ]
        or ["- none"]
    )
    lines.extend(["", "## Recommended Commands", ""])
    for command in list_of_dicts(payload.get("recommended_commands", [])):
        boundary = object_field(command, "boundary")
        lines.append(
            f"- `{command.get('label', '')}` "
            f"(`{boundary.get('boundary_type', '')}`): "
            f"`{command.get('command', '')}`"
        )
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This dashboard is read-only and does not record approval or execute commands.",
            "- It does not execute agents, run backtests, write config, promote champions, apply patches, route agents, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_operator_action_dashboard_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved operator action dashboard artifact."""
    errors = list(
        validate_json_file(
            payload_path=payload_path,
            schema_path=repo_root / SCHEMA_PATH,
        )
    )
    if payload_path.exists():
        errors.extend(
            validate_operator_action_dashboard_consistency(load_json_object(payload_path))
        )
    return tuple(errors)


def validate_operator_action_dashboard_payload(
    payload: dict[str, object],
    *,
    run_dir: Path | None = None,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an in-memory operator action dashboard payload."""
    repo_root = repo_root.resolve()
    comparable_payload = strip_terminal_metadata(payload)
    schema = load_json_object(repo_root / SCHEMA_PATH)
    errors = list(validate_json_payload(payload=comparable_payload, schema=schema))
    errors.extend(validate_operator_action_dashboard_consistency(comparable_payload))
    if require_current_evidence:
        if run_dir is None:
            errors.append("operator_action_dashboard run_dir required")
        else:
            resolved_run_dir = resolve_path(run_dir, repo_root)
            expected = build_operator_action_dashboard(
                run_dir=resolved_run_dir,
                experiments_dir=resolve_path(experiments_dir, repo_root),
                repo_root=repo_root,
            )
            if comparable_payload != expected:
                errors.append("operator_action_dashboard current evidence mismatch")
    return tuple(errors)


def validate_operator_action_dashboard_consistency(
    payload: dict[str, object],
) -> tuple[str, ...]:
    """Validate derived dashboard summaries remain internally consistent."""
    def int_value(value: object, default: int = -1) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    errors: list[str] = []
    status = str(payload.get("status", ""))
    summary = object_field(payload, "summary")
    actions = list_of_dicts(payload.get("available_actions", []))
    failure_reasons = list_of_dicts(payload.get("failure_reasons", []))
    blockers = string_list(payload.get("blockers", []))
    commands = list_of_dicts(payload.get("recommended_commands", []))
    sources = object_field(payload, "source_artifacts")
    timeline = list_of_dicts(payload.get("timeline", []))
    readiness = object_field(payload, "execution_readiness")
    closure = object_field(payload, "path_closure")
    selected_command = object_field(payload, "selected_command")

    if bool(payload.get("ok", False)) != (
        status not in {"needs_chain_repair", "missing_action_plan"}
    ):
        errors.append("operator_action_dashboard ok status mismatch")
    if str(payload.get("current_step", "")) != dashboard_current_step(status=status):
        errors.append("operator_action_dashboard current_step mismatch")
    if str(payload.get("primary_prompt", "")) != primary_prompt(status=status):
        errors.append("operator_action_dashboard primary_prompt mismatch")
    if int_value(summary.get("action_count", -1)) != len(actions):
        errors.append("operator_action_dashboard summary action_count mismatch")
    command_count = sum(
        int_value(action.get("command_count", 0), 0) for action in actions
    )
    if int_value(summary.get("command_candidate_count", -1)) != command_count:
        errors.append(
            "operator_action_dashboard summary command_candidate_count mismatch"
        )
    safe_command_count = sum(
        int_value(action.get("safe_command_count", 0), 0) for action in actions
    )
    if int_value(summary.get("safe_command_count", -1)) != safe_command_count:
        errors.append("operator_action_dashboard summary safe_command_count mismatch")
    if int_value(summary.get("failure_reason_count", -1)) != len(failure_reasons):
        errors.append(
            "operator_action_dashboard summary failure_reason_count mismatch"
        )
    first_stage = (
        str(failure_reasons[0].get("stage", "none")) if failure_reasons else "none"
    )
    if str(summary.get("first_failure_stage", "")) != first_stage:
        errors.append("operator_action_dashboard summary first_failure_stage mismatch")
    if int_value(summary.get("blocker_count", -1)) != len(blockers):
        errors.append("operator_action_dashboard summary blocker_count mismatch")
    for command in commands:
        label = str(command.get("label", ""))
        writes_artifact = str(command.get("writes_artifact", ""))
        expected_boundary = classify_operator_command(
            label=label,
            writes_artifact=writes_artifact,
        )
        if object_field(command, "boundary") != expected_boundary:
            errors.append("operator_action_dashboard command boundary mismatch")
            break
    expected_readiness = execution_readiness_summary(
        status=status,
        current_step=str(payload.get("current_step", "")),
        sources=sources,
        timeline=timeline,
        blockers=blockers,
        recommended_commands=commands,
        selected_command=selected_command,
    )
    if readiness != expected_readiness:
        errors.append("operator_action_dashboard execution_readiness mismatch")
    expected_closure = path_closure_summary(
        status=status,
        current_step=str(payload.get("current_step", "")),
        sources=sources,
        timeline=timeline,
        summary=summary,
        blockers=blockers,
        selected_command=selected_command,
    )
    if closure != expected_closure:
        errors.append("operator_action_dashboard path_closure mismatch")
    return tuple(errors)


def relative_path(path: Path, repo_root: Path) -> str:
    """Return a stable repository-relative path when possible."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def unique_preserving_order(values: list[str]) -> list[str]:
    """Return values in first-seen order without duplicates."""
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            rows.append(value)
    return rows


def strip_terminal_metadata(payload: dict[str, object]) -> dict[str, object]:
    """Return payload without CLI-only annotation fields."""
    stripped = dict(payload)
    stripped.pop("from_artifact", None)
    return stripped


def main() -> None:
    """CLI entrypoint for operator action dashboard generation."""
    parser = argparse.ArgumentParser(
        description="Write a read-only operator action status dashboard."
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    _, _, payload = write_operator_action_dashboard(
        run_dir=args.run_dir,
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
