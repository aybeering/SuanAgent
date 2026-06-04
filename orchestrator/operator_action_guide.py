"""Terminal-only guide for the operator action approval/execution path."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.operator_action_audit import object_field, resolve_path, string_list
from orchestrator.operator_action_dashboard import (
    build_operator_action_dashboard,
)
from orchestrator.schema_validation import (
    load_schema,
    validate_json_payload,
)


OPERATOR_ACTION_GUIDE_SCHEMA_VERSION = "operator_action_guide_v1"
SCHEMA_PATH = Path("schemas/operator_action_guide.schema.json")


def build_operator_action_guide(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return a deterministic terminal guide for the current action path."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    dashboard_path = run_dir / "operator_action_dashboard.json"
    dashboard = load_or_build_dashboard(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    readiness = object_field(dashboard, "execution_readiness")
    closure = object_field(dashboard, "path_closure")
    blockers = string_list(dashboard.get("blockers", []))
    guide_status = action_guide_status(
        dashboard=dashboard,
        readiness=readiness,
        closure=closure,
        blockers=blockers,
    )
    commands = list_of_dicts(dashboard.get("recommended_commands", []))
    next_command = select_guide_command(commands, guide_status)
    boundary = object_field(next_command, "boundary")
    payload: dict[str, object] = {
        "schema_version": OPERATOR_ACTION_GUIDE_SCHEMA_VERSION,
        "run_id": str(dashboard.get("run_id", run_dir.name)),
        "run_dir": str(run_dir),
        "status": guide_status,
        "ok": guide_status != "blocked",
        "current_step": str(dashboard.get("current_step", "")),
        "source_dashboard": {
            "artifact_name": "operator_action_dashboard",
            "from_artifact": dashboard_path.exists(),
            "file": file_record(dashboard_path, repo_root),
        },
        "action_state": action_state_summary(
            dashboard=dashboard,
            readiness=readiness,
            closure=closure,
            blockers=blockers,
        ),
        "next_command": guide_command(next_command),
        "guidance": guidance_summary(
            status=guide_status,
            dashboard=dashboard,
            next_command=next_command,
            boundary=boundary,
        ),
        "guided_path": guided_path_summary(
            dashboard=dashboard,
            commands=commands,
            status=guide_status,
            next_command=next_command,
        ),
        "command_sequence": command_sequence(commands),
        "blocker_preview": blockers[:5],
        "authority": {
            "guide_can_record_approval": False,
            "guide_can_execute_commands": False,
            "guide_can_change_repository": False,
            "approval_must_use_operator_action_approval": True,
            "execution_must_use_guarded_executor": True,
        },
        "policy": {
            "inspection_only": True,
            "reads_saved_or_derived_dashboard_only": True,
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
    return payload


def load_or_build_dashboard(
    *,
    run_dir: Path,
    experiments_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    """Load the saved dashboard when present, otherwise derive it."""
    dashboard_path = run_dir / "operator_action_dashboard.json"
    if dashboard_path.exists():
        payload = json.loads(dashboard_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    return build_operator_action_dashboard(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )


def action_guide_status(
    *,
    dashboard: dict[str, Any],
    readiness: dict[str, Any],
    closure: dict[str, Any],
    blockers: list[str],
) -> str:
    """Return compact guide status from dashboard state."""
    if blockers or dashboard.get("ok") is not True:
        return "blocked"
    if closure.get("closed") is True:
        return "path_closed"
    if readiness.get("ready") is True:
        return "ready_for_guarded_execution"
    dashboard_status = str(dashboard.get("status", ""))
    if dashboard_status == "pending_approval":
        return "awaiting_operator_approval"
    if dashboard_status == "ready_for_execution":
        return "ready_for_guarded_execution"
    return "review_required"


def action_state_summary(
    *,
    dashboard: dict[str, Any],
    readiness: dict[str, Any],
    closure: dict[str, Any],
    blockers: list[str],
) -> dict[str, object]:
    """Return compact action state for the guide."""
    return {
        "dashboard_status": str(dashboard.get("status", "")),
        "dashboard_ok": bool(dashboard.get("ok", False)),
        "readiness_status": str(readiness.get("status", "")),
        "readiness_ready": bool(readiness.get("ready", False)),
        "path_closure_status": str(closure.get("status", "")),
        "path_closed": bool(closure.get("closed", False)),
        "path_completed_step_count": int(
            closure.get("completed_step_count", 0) or 0
        ),
        "path_required_step_count": int(closure.get("required_step_count", 0) or 0),
        "blocker_count": len(blockers),
        "selected_command_label": str(closure.get("selected_command_label", "")),
    }


def select_guide_command(commands: list[dict[str, Any]], status: str) -> dict[str, Any]:
    """Return the dashboard command that best matches the guide status."""
    if not commands:
        return {}
    if status == "awaiting_operator_approval":
        for command in commands:
            boundary = object_field(command, "boundary")
            if (
                boundary.get("boundary_type") == "operator_approval_receipt"
                or boundary.get("records_operator_approval") is True
            ):
                return command
    if status == "ready_for_guarded_execution":
        for command in commands:
            boundary = object_field(command, "boundary")
            if boundary.get("uses_guarded_executor") is True:
                return command
    if status == "path_closed":
        for command in commands:
            boundary = object_field(command, "boundary")
            if boundary.get("boundary_type") == "read_only_inspection":
                return command
    return commands[0]


def guide_command(command: dict[str, Any]) -> dict[str, object]:
    """Return the next command hint used by the guide."""
    boundary = object_field(command, "boundary")
    return {
        "label": str(command.get("label", "")),
        "command": str(command.get("command", "")),
        "reason": str(command.get("reason", "")),
        "writes_artifact": str(command.get("writes_artifact", "")),
        "boundary": boundary,
        "command_is_hint_only": True,
        "requires_explicit_operator_invocation": bool(
            boundary.get("requires_explicit_operator_invocation", False)
        ),
        "requires_operator_approval": bool(
            boundary.get("requires_operator_approval", False)
        ),
        "records_operator_approval": bool(
            boundary.get("records_operator_approval", False)
        ),
        "uses_guarded_executor": bool(boundary.get("uses_guarded_executor", False)),
    }


def guidance_summary(
    *,
    status: str,
    dashboard: dict[str, Any],
    next_command: dict[str, Any],
    boundary: dict[str, Any],
) -> dict[str, object]:
    """Return human-facing action guide guidance fields."""
    label = str(next_command.get("label", ""))
    if status == "blocked":
        headline = "Inspect action blockers before continuing."
        instruction = "Repair the operator action chain or inspect blocker evidence."
    elif status == "path_closed":
        headline = "Operator action path is closed."
        instruction = "Review the execution receipt output hashes and dashboard summary."
    elif status == "ready_for_guarded_execution":
        headline = "Guarded execution is ready."
        instruction = "Invoke the guarded executor command explicitly when desired."
    elif status == "awaiting_operator_approval":
        headline = "Operator approval remains."
        instruction = "Record approval for one guarded read-only command candidate."
    else:
        headline = "Review the operator action dashboard."
        instruction = str(dashboard.get("primary_prompt", "Inspect action evidence."))
    return {
        "headline": headline,
        "instruction": instruction,
        "next_command_label": label,
        "next_command_boundary": str(boundary.get("boundary_type", "")),
        "can_invoke_guarded_executor_now": bool(
            status == "ready_for_guarded_execution"
            and boundary.get("uses_guarded_executor") is True
        ),
        "command_is_hint_only": True,
        "requires_manual_operator_step": status != "path_closed",
    }


def guided_path_summary(
    *,
    dashboard: dict[str, Any],
    commands: list[dict[str, Any]],
    status: str,
    next_command: dict[str, Any],
) -> dict[str, object]:
    """Return a deterministic checklist for the manual operator action path."""
    closure = object_field(dashboard, "path_closure")
    source_artifacts = object_field(dashboard, "source_artifacts")
    blockers = string_list(dashboard.get("blockers", []))
    active_step_id = active_guided_step_id(status)
    steps = guided_path_steps(
        commands=commands,
        closure=closure,
        source_artifacts=source_artifacts,
        active_step_id=active_step_id,
        blocked=bool(blockers or dashboard.get("ok") is not True),
    )
    return {
        "schema_version": "operator_action_guided_path_v1",
        "status": status,
        "current_step": str(dashboard.get("current_step", "")),
        "active_step_id": active_step_id,
        "next_command_label": str(next_command.get("label", "")),
        "step_count": len(steps),
        "completed_step_count": sum(1 for step in steps if step["complete"] is True),
        "steps": steps,
        "policy": {
            "commands_are_hints_only": True,
            "does_not_record_approval": True,
            "does_not_execute_commands": True,
            "does_not_change_acceptance": True,
        },
    }


def active_guided_step_id(status: str) -> str:
    """Return the active guided-path step id for one guide status."""
    return {
        "awaiting_operator_approval": "operator_approval",
        "ready_for_guarded_execution": "guarded_execution",
        "path_closed": "dashboard_review",
        "blocked": "blocker_review",
    }.get(status, "dashboard_review")


def guided_path_steps(
    *,
    commands: list[dict[str, Any]],
    closure: dict[str, Any],
    source_artifacts: dict[str, Any],
    active_step_id: str,
    blocked: bool,
) -> list[dict[str, object]]:
    """Return ordered guided-path rows from dashboard command hints."""
    audit_source = object_field(source_artifacts, "action_audit")
    approval_source = object_field(source_artifacts, "action_approval")
    execution_source = object_field(source_artifacts, "execution_receipt")
    steps = [
        guided_path_step(
            step_id="action_audit_refresh",
            label="Refresh action audit",
            command=find_command(commands, "write_action_audit"),
            artifact_name="operator_action_audit",
            artifact_path=artifact_path(audit_source),
            complete=bool(
                object_field(audit_source, "file").get("exists", False)
            ),
            active_step_id=active_step_id,
            blocked=blocked,
        ),
        guided_path_step(
            step_id="operator_approval",
            label="Record operator approval",
            command=find_command(commands, "record_operator_approval"),
            artifact_name="operator_action_approval",
            artifact_path=artifact_path(approval_source),
            complete=bool(closure.get("approval_recorded", False)),
            active_step_id=active_step_id,
            blocked=blocked,
        ),
        guided_path_step(
            step_id="guarded_execution",
            label="Run guarded read-only execution",
            command=find_command(commands, "execute_approved_command"),
            artifact_name="operator_action_execution_receipt",
            artifact_path=artifact_path(execution_source),
            complete=bool(closure.get("execution_completed", False)),
            active_step_id=active_step_id,
            blocked=blocked,
        ),
        guided_path_step(
            step_id="dashboard_review",
            label="Review refreshed dashboard",
            command=find_command_by_boundary(commands, "read_only_inspection"),
            artifact_name="operator_action_dashboard",
            artifact_path="operator_action_dashboard.json",
            complete=bool(closure.get("closed", False)),
            active_step_id=active_step_id,
            blocked=blocked,
        ),
    ]
    return steps


def guided_path_step(
    *,
    step_id: str,
    label: str,
    command: dict[str, Any],
    artifact_name: str,
    artifact_path: str,
    complete: bool,
    active_step_id: str,
    blocked: bool,
) -> dict[str, object]:
    """Return one guided-path checklist row."""
    boundary = object_field(command, "boundary")
    is_active = step_id == active_step_id and not complete and not blocked
    has_command = bool(command)
    if complete:
        status = "complete"
    elif blocked:
        status = "blocked"
    elif is_active:
        status = "active"
    elif has_command:
        status = "available"
    else:
        status = "waiting"
    return {
        "step_id": step_id,
        "label": label,
        "status": status,
        "complete": complete,
        "active": is_active,
        "artifact_name": artifact_name,
        "artifact_path": artifact_path,
        "command_label": str(command.get("label", "")),
        "command": str(command.get("command", "")),
        "boundary_type": str(boundary.get("boundary_type", "")),
        "command_is_hint_only": True,
    }


def find_command(commands: list[dict[str, Any]], label: str) -> dict[str, Any]:
    """Return a dashboard command by label."""
    for command in commands:
        if command.get("label") == label:
            return command
    return {}


def find_command_by_boundary(
    commands: list[dict[str, Any]], boundary_type: str
) -> dict[str, Any]:
    """Return the first dashboard command with the requested boundary type."""
    for command in commands:
        boundary = object_field(command, "boundary")
        if boundary.get("boundary_type") == boundary_type:
            return command
    return {}


def artifact_path(source: dict[str, Any]) -> str:
    """Return a source artifact path string from a dashboard source record."""
    return str(object_field(source, "file").get("path", ""))


def command_sequence(commands: list[dict[str, Any]]) -> list[dict[str, object]]:
    """Return compact ordered command labels and boundaries."""
    rows: list[dict[str, object]] = []
    for index, command in enumerate(commands, start=1):
        boundary = object_field(command, "boundary")
        rows.append(
            {
                "index": index,
                "label": str(command.get("label", "")),
                "boundary_type": str(boundary.get("boundary_type", "")),
                "writes_artifact": str(command.get("writes_artifact", "")),
            }
        )
    return rows


def render_operator_action_guide_markdown(payload: dict[str, object]) -> str:
    """Render the operator action guide as markdown."""
    state = object_field(payload, "action_state")
    command = object_field(payload, "next_command")
    boundary = object_field(command, "boundary")
    guidance = object_field(payload, "guidance")
    lines = [
        "# Operator Action Guide",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Current step: `{payload.get('current_step', '')}`",
        f"- Headline: {guidance.get('headline', '')}",
        f"- Instruction: {guidance.get('instruction', '')}",
        f"- Dashboard status: `{state.get('dashboard_status', '')}`",
        f"- Readiness: `{state.get('readiness_status', '')}`",
        f"- Path closure: `{state.get('path_closure_status', '')}`",
        f"- Path closed: `{state.get('path_closed', False)}`",
        f"- Path steps: `{state.get('path_completed_step_count', 0)}` / "
        f"`{state.get('path_required_step_count', 0)}`",
        f"- Blockers: `{state.get('blocker_count', 0)}`",
        "",
        "## Next Command",
        "",
        f"- Label: `{command.get('label', '')}`",
        f"- Boundary: `{boundary.get('boundary_type', '')}`",
        f"- Reason: {command.get('reason', '')}",
        f"- Hint only: `{command.get('command_is_hint_only', False)}`",
        "",
        "```bash",
        str(command.get("command", "")),
        "```",
        "",
        "## Guided Path",
        "",
    ]
    guided_path = object_field(payload, "guided_path")
    for step in list_of_dicts(guided_path.get("steps", [])):
        lines.append(
            f"- `{step.get('step_id', '')}` `{step.get('status', '')}` -> "
            f"`{step.get('command_label', '')}` (`{step.get('boundary_type', '')}`)"
        )
    lines.extend(
        [
            "",
            "## Command Sequence",
            "",
        ]
    )
    for row in list_of_dicts(payload.get("command_sequence", [])):
        lines.append(
            f"- `{row.get('index', 0)}` `{row.get('label', '')}` "
            f"(`{row.get('boundary_type', '')}`)"
        )
    lines.extend(["", "## Blockers", ""])
    blockers = string_list(payload.get("blocker_preview", []))
    lines.extend([f"- `{blocker}`" for blocker in blockers] or ["- none"])
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This guide is terminal-only and does not record approval or execute commands.",
            "- It does not execute agents, run backtests, write config, promote champions, apply patches, route agents, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_operator_action_guide_payload(
    payload: dict[str, object],
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an operator action guide payload."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    schema = load_schema(repo_root / SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=payload,
            schema=schema,
            schema_dir=(repo_root / SCHEMA_PATH).parent,
        )
    )
    errors.extend(
        validate_operator_action_guide_consistency(
            payload,
            run_dir=run_dir,
            experiments_dir=experiments_dir,
            repo_root=repo_root,
        )
    )
    if require_current_evidence:
        expected = build_operator_action_guide(
            run_dir=run_dir,
            experiments_dir=experiments_dir,
            repo_root=repo_root,
        )
        if "from_artifact" in payload:
            expected = {**expected, "from_artifact": payload.get("from_artifact")}
        if payload != expected:
            errors.append("operator_action_guide current evidence mismatch")
    return tuple(errors)


def validate_operator_action_guide_consistency(
    payload: dict[str, object],
    *,
    run_dir: Path,
    experiments_dir: Path,
    repo_root: Path,
) -> tuple[str, ...]:
    """Validate guide state, next command, authority, and policy fields."""
    errors: list[str] = []
    source = object_field(payload, "source_dashboard")
    source_file = object_field(source, "file")
    dashboard_path = resolve_path(Path(str(source_file.get("path", ""))), repo_root)
    dashboard = load_or_build_dashboard(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    readiness = object_field(dashboard, "execution_readiness")
    closure = object_field(dashboard, "path_closure")
    blockers = string_list(dashboard.get("blockers", []))
    expected_state = action_state_summary(
        dashboard=dashboard,
        readiness=readiness,
        closure=closure,
        blockers=blockers,
    )
    if object_field(payload, "action_state") != expected_state:
        errors.append("operator_action_guide action state mismatch")
    expected_status = action_guide_status(
        dashboard=dashboard,
        readiness=readiness,
        closure=closure,
        blockers=blockers,
    )
    if str(payload.get("status", "")) != expected_status:
        errors.append("operator_action_guide status mismatch")
    if bool(payload.get("ok", False)) != (expected_status != "blocked"):
        errors.append("operator_action_guide ok mismatch")
    commands = list_of_dicts(dashboard.get("recommended_commands", []))
    expected_raw_command = select_guide_command(commands, expected_status)
    expected_command = guide_command(expected_raw_command)
    if object_field(payload, "next_command") != expected_command:
        errors.append("operator_action_guide next command mismatch")
    if string_list(payload.get("blocker_preview", [])) != blockers[:5]:
        errors.append("operator_action_guide blocker preview mismatch")
    expected_sequence = command_sequence(commands)
    if list_of_dicts(payload.get("command_sequence", [])) != expected_sequence:
        errors.append("operator_action_guide command sequence mismatch")
    boundary = object_field(expected_command, "boundary")
    expected_guidance = guidance_summary(
        status=expected_status,
        dashboard=dashboard,
        next_command=expected_raw_command,
        boundary=boundary,
    )
    if object_field(payload, "guidance") != expected_guidance:
        errors.append("operator_action_guide guidance mismatch")
    expected_guided_path = guided_path_summary(
        dashboard=dashboard,
        commands=commands,
        status=expected_status,
        next_command=expected_raw_command,
    )
    if object_field(payload, "guided_path") != expected_guided_path:
        errors.append("operator_action_guide guided path mismatch")
    if str(source.get("artifact_name", "")) != "operator_action_dashboard":
        errors.append("operator_action_guide source artifact mismatch")
    if source_file.get("sha256") != file_sha256(dashboard_path):
        errors.append("operator_action_guide source digest mismatch")
    expected_authority = {
        "guide_can_record_approval": False,
        "guide_can_execute_commands": False,
        "guide_can_change_repository": False,
        "approval_must_use_operator_action_approval": True,
        "execution_must_use_guarded_executor": True,
    }
    if object_field(payload, "authority") != expected_authority:
        errors.append("operator_action_guide authority mismatch")
    expected_policy = {
        "inspection_only": True,
        "reads_saved_or_derived_dashboard_only": True,
        "does_not_record_approval": True,
        "does_not_execute_commands": True,
        "does_not_execute_agents": True,
        "does_not_run_backtests": True,
        "does_not_write_config": True,
        "does_not_promote_champion": True,
        "does_not_apply_patches": True,
        "does_not_route_agents": True,
        "does_not_change_acceptance": True,
    }
    if object_field(payload, "policy") != expected_policy:
        errors.append("operator_action_guide policy mismatch")
    return tuple(errors)


def file_record(path: Path, repo_root: Path) -> dict[str, object]:
    """Return a deterministic file record."""
    return {
        "path": relative_path(path, repo_root),
        "exists": path.exists(),
        "sha256": file_sha256(path),
        "byte_count": path.stat().st_size if path.exists() else 0,
    }


def file_sha256(path: Path) -> str:
    """Return SHA-256 for a file or an empty string when missing."""
    if not path.exists() or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object or return an empty dict."""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def list_of_dicts(value: object) -> list[dict[str, Any]]:
    """Return dict rows from a possible list."""
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def relative_path(path: Path, repo_root: Path) -> str:
    """Return repository-relative paths when possible."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def main() -> None:
    """CLI entrypoint for terminal-only operator action guidance."""
    parser = argparse.ArgumentParser(
        description="Show a read-only guide for the operator action path."
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    payload = build_operator_action_guide(
        run_dir=args.run_dir,
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
    )
    errors = validate_operator_action_guide_payload(
        payload,
        run_dir=args.run_dir,
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
        require_current_evidence=True,
    )
    if errors:
        raise SystemExit("; ".join(errors))
    if args.markdown:
        print(render_operator_action_guide_markdown(payload), end="")
        return
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
