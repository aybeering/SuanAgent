"""Read-only audit chain for operator action plan, approval, and execution."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.operator_action_approval import OPERATOR_ACTION_APPROVAL_SCHEMA_VERSION
from orchestrator.operator_action_executor import (
    OPERATOR_ACTION_EXECUTION_RECEIPT_SCHEMA_VERSION,
)
from orchestrator.operator_action_plan import (
    OPERATOR_ACTION_PLAN_SCHEMA_VERSION,
    build_operator_action_plan,
)
from orchestrator.schema_validation import (
    load_schema,
    validate_json_file,
    validate_json_payload,
)


OPERATOR_ACTION_AUDIT_SCHEMA_VERSION = "operator_action_audit_v1"
SCHEMA_PATH = Path("schemas/operator_action_audit.schema.json")


def write_operator_action_audit(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown operator action audit artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    payload = build_operator_action_audit(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    errors = validate_operator_action_audit_payload(
        payload,
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "operator action audit failed schema validation: " + "; ".join(errors)
        )
    json_path = run_dir / "operator_action_audit.json"
    md_path = run_dir / "operator_action_audit.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_operator_action_audit_markdown(payload), encoding="utf-8")
    errors = validate_operator_action_audit_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(
            "operator action audit failed schema validation: " + "; ".join(errors)
        )
    return json_path, md_path, payload


def build_operator_action_audit(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return a deterministic audit chain for operator action artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    plan_path = run_dir / "operator_action_plan.json"
    approval_path = run_dir / "operator_action_approval.json"
    execution_path = run_dir / "operator_action_execution_receipt.json"

    if plan_path.exists():
        plan = load_json_object(plan_path)
        plan_from_artifact = True
    else:
        plan = build_operator_action_plan(
            run_dir=run_dir,
            experiments_dir=experiments_dir,
            repo_root=repo_root,
        )
        plan_from_artifact = False
    approval = load_json_object(approval_path)
    execution = load_json_object(execution_path)
    checks = chain_checks(
        plan=plan,
        plan_path=plan_path,
        approval=approval,
        approval_path=approval_path,
        execution=execution,
        execution_path=execution_path,
        repo_root=repo_root,
    )
    status = audit_status(
        plan=plan,
        approval=approval,
        execution=execution,
        checks=checks,
    )
    payload: dict[str, object] = {
        "schema_version": OPERATOR_ACTION_AUDIT_SCHEMA_VERSION,
        "run_id": str(plan.get("run_id", run_dir.name)),
        "run_dir": str(run_dir),
        "status": status,
        "ok": bool(checks.get("ok", False)),
        "source_artifacts": {
            "action_plan": {
                "artifact_name": "operator_action_plan",
                "from_artifact": plan_from_artifact,
                "file": file_record(plan_path, repo_root),
                "schema_errors": string_list(checks.get("plan_schema_errors", [])),
            },
            "action_approval": {
                "artifact_name": "operator_action_approval",
                "from_artifact": approval_path.exists(),
                "file": file_record(approval_path, repo_root),
                "schema_errors": string_list(
                    checks.get("approval_schema_errors", [])
                ),
            },
            "execution_receipt": {
                "artifact_name": "operator_action_execution_receipt",
                "from_artifact": execution_path.exists(),
                "file": file_record(execution_path, repo_root),
                "schema_errors": string_list(
                    checks.get("execution_schema_errors", [])
                ),
            },
        },
        "summary": audit_summary(
            plan=plan,
            approval=approval,
            execution=execution,
            checks=checks,
        ),
        "selected_action": selected_action_record(plan=plan, approval=approval),
        "selected_command": selected_command_record(plan=plan, approval=approval),
        "approval_record": approval_record(approval),
        "execution_record": execution_record(execution),
        "chain_checks": checks,
        "recommended_next_actions": recommended_next_actions(status=status),
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
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


def chain_checks(
    *,
    plan: dict[str, Any],
    plan_path: Path,
    approval: dict[str, Any],
    approval_path: Path,
    execution: dict[str, Any],
    execution_path: Path,
    repo_root: Path,
) -> dict[str, object]:
    """Return digest and consistency checks across the action artifacts."""
    consistency_errors: list[str] = []
    plan_errors = schema_errors(
        path=plan_path,
        schema_path=repo_root / "schemas/operator_action_plan.schema.json",
    )
    approval_errors = schema_errors(
        path=approval_path,
        schema_path=repo_root / "schemas/operator_action_approval.schema.json",
    )
    execution_errors = schema_errors(
        path=execution_path,
        schema_path=repo_root
        / "schemas/operator_action_execution_receipt.schema.json",
    )
    if not plan:
        consistency_errors.append("action_plan_missing")
    if plan and plan.get("schema_version") != OPERATOR_ACTION_PLAN_SCHEMA_VERSION:
        consistency_errors.append("action_plan_schema_version_invalid")

    selected_action = selected_action_from_approval(approval)
    selected_command = selected_command_from_approval(approval)
    plan_action = find_action(plan=plan, action_id=str(selected_action.get("action_id", "")))
    plan_command = find_command(
        action=plan_action,
        command_label=str(selected_command.get("label", "")),
    )
    if approval:
        if approval.get("schema_version") != OPERATOR_ACTION_APPROVAL_SCHEMA_VERSION:
            consistency_errors.append("approval_schema_version_invalid")
        source_plan_file = object_field(object_field(approval, "source_action_plan"), "file")
        if str(source_plan_file.get("sha256", "")) != file_sha256(plan_path):
            consistency_errors.append("approval_source_plan_digest_mismatch")
        if not plan_action:
            consistency_errors.append("approval_action_not_in_plan")
        if not plan_command:
            consistency_errors.append("approval_command_not_in_plan")
        elif selected_command.get("command_sha256") != plan_command.get("command_sha256"):
            consistency_errors.append("approval_command_digest_not_in_plan")

    execution_command = object_field(execution, "selected_command")
    if execution:
        if (
            execution.get("schema_version")
            != OPERATOR_ACTION_EXECUTION_RECEIPT_SCHEMA_VERSION
        ):
            consistency_errors.append("execution_schema_version_invalid")
        source_approval_file = object_field(
            object_field(execution, "source_approval"),
            "file",
        )
        if str(source_approval_file.get("sha256", "")) != file_sha256(approval_path):
            consistency_errors.append("execution_source_approval_digest_mismatch")
        if not approval:
            consistency_errors.append("execution_without_approval")
        elif execution_command.get("command_sha256") != selected_command.get(
            "command_sha256"
        ):
            consistency_errors.append("execution_command_digest_mismatch")

    return {
        "ok": not plan_errors
        and not approval_errors
        and not execution_errors
        and not consistency_errors,
        "plan_schema_errors": list(plan_errors),
        "approval_schema_errors": list(approval_errors),
        "execution_schema_errors": list(execution_errors),
        "consistency_errors": unique_strings(consistency_errors),
        "failure_reasons": chain_failure_reasons(
            plan_schema_errors=list(plan_errors),
            approval_schema_errors=list(approval_errors),
            execution_schema_errors=list(execution_errors),
            consistency_errors=unique_strings(consistency_errors),
        ),
        "plan_sha256": file_sha256(plan_path),
        "approval_sha256": file_sha256(approval_path),
        "execution_sha256": file_sha256(execution_path),
        "approval_source_plan_sha256": str(
            object_field(object_field(approval, "source_action_plan"), "file").get(
                "sha256",
                "",
            )
        ),
        "execution_source_approval_sha256": str(
            object_field(object_field(execution, "source_approval"), "file").get(
                "sha256",
                "",
            )
        ),
    }


def audit_status(
    *,
    plan: dict[str, Any],
    approval: dict[str, Any],
    execution: dict[str, Any],
    checks: dict[str, object],
) -> str:
    """Return compact action audit status."""
    if not plan:
        return "missing_action_plan"
    if list_of_dicts(checks.get("failure_reasons", [])):
        return "chain_inconsistent"
    if not approval:
        return "pending_approval"
    if approval.get("status") != "approval_recorded":
        return "approval_blocked"
    if not execution:
        return "ready_for_execution"
    execution_status = str(execution.get("status", ""))
    if execution_status == "completed":
        return "execution_completed"
    if execution_status == "blocked":
        return "execution_blocked"
    return "execution_failed"


def audit_summary(
    *,
    plan: dict[str, Any],
    approval: dict[str, Any],
    execution: dict[str, Any],
    checks: dict[str, object],
) -> dict[str, object]:
    """Return compact operator action audit summary."""
    plan_summary = object_field(plan, "summary")
    return {
        "action_count": int(plan_summary.get("action_count", 0) or 0),
        "command_candidate_count": int(
            plan_summary.get("command_candidate_count", 0) or 0
        ),
        "approval_present": bool(approval),
        "approval_status": str(approval.get("status", "")),
        "approval_recorded": bool(
            object_field(approval, "operator_intent").get("approval_recorded", False)
        ),
        "execution_present": bool(execution),
        "execution_status": str(execution.get("status", "")),
        "execution_completed": execution.get("status") == "completed",
        "chain_ok": bool(checks.get("ok", False)),
        "consistency_error_count": len(
            string_list(checks.get("consistency_errors", []))
        ),
        "failure_reason_count": len(list_of_dicts(checks.get("failure_reasons", []))),
        "first_failure_stage": first_failure_stage(checks),
    }


def chain_failure_reasons(
    *,
    plan_schema_errors: list[str],
    approval_schema_errors: list[str],
    execution_schema_errors: list[str],
    consistency_errors: list[str],
) -> list[dict[str, object]]:
    """Return stable failure taxonomy rows for action audit chain breaks."""
    reasons: list[dict[str, object]] = []
    for error in plan_schema_errors:
        reasons.append(
            failure_reason(
                stage="action_plan",
                code="action_plan_schema_error",
                detail=error,
            )
        )
    for error in approval_schema_errors:
        reasons.append(
            failure_reason(
                stage="action_approval",
                code="action_approval_schema_error",
                detail=error,
            )
        )
    for error in execution_schema_errors:
        reasons.append(
            failure_reason(
                stage="execution_receipt",
                code="execution_receipt_schema_error",
                detail=error,
            )
        )
    for error in consistency_errors:
        reasons.append(
            failure_reason(
                stage=consistency_error_stage(error),
                code=error,
                detail=error,
            )
        )
    return reasons


def failure_reason(*, stage: str, code: str, detail: str) -> dict[str, object]:
    """Return one stable failure reason row."""
    return {
        "stage": stage,
        "code": code,
        "severity": "error",
        "detail": detail,
    }


def consistency_error_stage(code: str) -> str:
    """Return the artifact stage responsible for a consistency error code."""
    if code.startswith("action_plan"):
        return "action_plan"
    if code.startswith("approval"):
        return "action_approval"
    if code.startswith("execution"):
        return "execution_receipt"
    return "chain"


def first_failure_stage(checks: dict[str, object]) -> str:
    """Return the first failure stage for compact dashboard summaries."""
    reasons = list_of_dicts(checks.get("failure_reasons", []))
    if not reasons:
        return "none"
    return str(reasons[0].get("stage", "chain"))


def selected_action_record(
    *,
    plan: dict[str, Any],
    approval: dict[str, Any],
) -> dict[str, object]:
    """Return selected action details from approval and plan context."""
    selected = selected_action_from_approval(approval)
    action = find_action(plan=plan, action_id=str(selected.get("action_id", "")))
    return {
        "action_id": str(selected.get("action_id", "")),
        "action_type": str(selected.get("action_type", "")),
        "status": str(selected.get("status", "")),
        "source_text": str(selected.get("source_text", "")),
        "exists_in_plan": bool(action),
    }


def selected_command_record(
    *,
    plan: dict[str, Any],
    approval: dict[str, Any],
) -> dict[str, object]:
    """Return selected command details from approval and plan context."""
    selected_action = selected_action_from_approval(approval)
    selected_command = selected_command_from_approval(approval)
    plan_action = find_action(plan=plan, action_id=str(selected_action.get("action_id", "")))
    plan_command = find_command(
        action=plan_action,
        command_label=str(selected_command.get("label", "")),
    )
    return {
        "label": str(selected_command.get("label", "")),
        "command": str(selected_command.get("command", "")),
        "command_sha256": str(selected_command.get("command_sha256", "")),
        "expected_artifact": str(selected_command.get("expected_artifact", "")),
        "writes_repository": bool(selected_command.get("writes_repository", False)),
        "promotes_champion": bool(selected_command.get("promotes_champion", False)),
        "runs_backtests": bool(selected_command.get("runs_backtests", False)),
        "exists_in_plan": bool(plan_command),
        "digest_matches_plan": bool(
            plan_command
            and selected_command.get("command_sha256")
            == plan_command.get("command_sha256")
        ),
    }


def approval_record(approval: dict[str, Any]) -> dict[str, object]:
    """Return compact approval state."""
    intent = object_field(approval, "operator_intent")
    return {
        "present": bool(approval),
        "status": str(approval.get("status", "")),
        "approval_recorded": bool(intent.get("approval_recorded", False)),
        "operator_id": str(intent.get("operator_id", "")),
        "target_action_id": str(intent.get("target_action_id", "")),
        "target_command_label": str(intent.get("target_command_label", "")),
        "confirmation_phrase_matches": bool(
            intent.get("confirmation_phrase_matches", False)
        ),
    }


def execution_record(execution: dict[str, Any]) -> dict[str, object]:
    """Return compact execution receipt state."""
    command_execution = object_field(execution, "command_execution")
    mutation_guard = object_field(execution, "mutation_guard")
    return {
        "present": bool(execution),
        "status": str(execution.get("status", "")),
        "ok": bool(execution.get("ok", False)),
        "executed": bool(execution.get("executed", False)),
        "returncode": command_execution.get("returncode"),
        "stdout_sha256": str(object_field(command_execution, "stdout").get("sha256", "")),
        "stderr_sha256": str(object_field(command_execution, "stderr").get("sha256", "")),
        "tracked_status_unchanged": bool(
            mutation_guard.get("tracked_status_unchanged", False)
        ),
    }


def recommended_next_actions(*, status: str) -> list[str]:
    """Return next actions based on the audit status."""
    if status == "pending_approval":
        return ["Record operator approval for one action-plan command candidate."]
    if status == "ready_for_execution":
        return ["Execute the approved read-only command through the guarded executor."]
    if status == "execution_completed":
        return ["Review the execution receipt output hashes and next dashboard action."]
    if status == "execution_blocked":
        return ["Choose a read-only allowlisted command or inspect the blockers."]
    if status == "chain_inconsistent":
        return ["Regenerate the action plan, approval, or execution receipt chain."]
    return ["Inspect operator action artifacts before taking another action."]


def render_operator_action_audit_markdown(payload: dict[str, object]) -> str:
    """Render an operator action audit payload as markdown."""
    summary = object_field(payload, "summary")
    action = object_field(payload, "selected_action")
    command = object_field(payload, "selected_command")
    approval = object_field(payload, "approval_record")
    execution = object_field(payload, "execution_record")
    checks = object_field(payload, "chain_checks")
    lines = [
        "# Operator Action Audit",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Actions: `{summary.get('action_count', 0)}`",
        f"- Command candidates: `{summary.get('command_candidate_count', 0)}`",
        f"- Approval present: `{approval.get('present', False)}`",
        f"- Execution present: `{execution.get('present', False)}`",
        "",
        "## Selected Command",
        "",
        f"- Action id: `{action.get('action_id', '')}`",
        f"- Command label: `{command.get('label', '')}`",
        f"- Command SHA-256: `{command.get('command_sha256', '')}`",
        f"- Exists in plan: `{command.get('exists_in_plan', False)}`",
        f"- Digest matches plan: `{command.get('digest_matches_plan', False)}`",
        "",
        "## Execution",
        "",
        f"- Approval status: `{approval.get('status', '')}`",
        f"- Execution status: `{execution.get('status', '')}`",
        f"- Executed: `{execution.get('executed', False)}`",
        f"- Return code: `{execution.get('returncode', None)}`",
        f"- Workspace unchanged: `{execution.get('tracked_status_unchanged', False)}`",
        "",
        "## Consistency Errors",
        "",
    ]
    errors = string_list(checks.get("consistency_errors", []))
    lines.extend([f"- `{error}`" for error in errors] or ["- none"])
    lines.extend(
        [
            "",
            "## Failure Reasons",
            "",
        ]
    )
    reasons = list_of_dicts(checks.get("failure_reasons", []))
    lines.extend(
        [
            (
                f"- `{reason.get('stage', '')}` / `{reason.get('code', '')}`: "
                f"{reason.get('detail', '')}"
            )
            for reason in reasons
        ]
        or ["- none"]
    )
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This artifact is read-only and only audits saved action artifacts.",
            "- It does not execute commands, execute agents, run backtests, write config, promote champions, apply patches, route agents, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_operator_action_audit_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved operator action audit artifact."""
    errors = list(
        validate_json_file(
            payload_path=payload_path,
            schema_path=repo_root / SCHEMA_PATH,
        )
    )
    if payload_path.exists():
        errors.extend(
            validate_operator_action_audit_consistency(
                load_json_object(payload_path),
                run_dir=payload_path.parent,
                experiments_dir=payload_path.parent.parent,
                repo_root=repo_root,
            )
        )
    return tuple(errors)


def validate_operator_action_audit_payload(
    payload: dict[str, object],
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an in-memory operator action audit payload."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    comparable_payload = strip_terminal_metadata(payload)
    schema = load_schema(repo_root / SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=comparable_payload,
            schema=schema,
            schema_dir=(repo_root / SCHEMA_PATH).parent,
        )
    )
    errors.extend(
        validate_operator_action_audit_consistency(
            comparable_payload,
            run_dir=run_dir,
            experiments_dir=experiments_dir,
            repo_root=repo_root,
        )
    )
    if require_current_evidence:
        expected = build_operator_action_audit(
            run_dir=run_dir,
            experiments_dir=experiments_dir,
            repo_root=repo_root,
        )
        if comparable_payload != expected:
            errors.append("operator_action_audit current evidence mismatch")
    return tuple(errors)


def validate_operator_action_audit_consistency(
    payload: dict[str, object],
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate audit source hashes, summaries, status, and policy fields."""
    errors: list[str] = []
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    plan_path = run_dir / "operator_action_plan.json"
    approval_path = run_dir / "operator_action_approval.json"
    execution_path = run_dir / "operator_action_execution_receipt.json"

    if str(payload.get("run_id", "")) != run_dir.name:
        errors.append("operator_action_audit run_id mismatch")
    if str(payload.get("run_dir", "")) != str(run_dir):
        errors.append("operator_action_audit run_dir mismatch")

    source_artifacts = object_field(payload, "source_artifacts")
    expected_sources = {
        "action_plan": ("operator_action_plan", plan_path),
        "action_approval": ("operator_action_approval", approval_path),
        "execution_receipt": ("operator_action_execution_receipt", execution_path),
    }
    for key, (artifact_name, source_path) in expected_sources.items():
        source = object_field(source_artifacts, key)
        source_file = object_field(source, "file")
        if source.get("artifact_name") != artifact_name:
            errors.append(f"operator_action_audit {key} source artifact mismatch")
        if source_file != file_record(source_path, repo_root):
            errors.append(f"operator_action_audit {key} source file mismatch")

    expected = build_operator_action_audit(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    expected_fields = [
        "status",
        "ok",
        "source_artifacts",
        "summary",
        "selected_action",
        "selected_command",
        "approval_record",
        "execution_record",
        "chain_checks",
        "recommended_next_actions",
        "policy",
    ]
    for field in expected_fields:
        if payload.get(field) != expected.get(field):
            errors.append(f"operator_action_audit {field} mismatch")
    return tuple(errors)


def strip_terminal_metadata(payload: dict[str, object]) -> dict[str, object]:
    """Return payload without CLI-only annotation fields."""
    stripped = dict(payload)
    stripped.pop("from_artifact", None)
    return stripped


def selected_action_from_approval(approval: dict[str, Any]) -> dict[str, Any]:
    """Return selected action from approval payload."""
    return object_field(approval, "selected_action")


def selected_command_from_approval(approval: dict[str, Any]) -> dict[str, Any]:
    """Return selected command from approval payload."""
    return object_field(approval, "selected_command")


def find_action(*, plan: dict[str, Any], action_id: str) -> dict[str, Any]:
    """Return an action row from an action plan."""
    for row in list_of_dicts(plan.get("actions", [])):
        if str(row.get("action_id", "")) == action_id:
            return row
    return {}


def find_command(*, action: dict[str, Any], command_label: str) -> dict[str, Any]:
    """Return a command row from an action."""
    for row in list_of_dicts(action.get("command_candidates", [])):
        if str(row.get("label", "")) == command_label:
            return row
    return {}


def schema_errors(*, path: Path, schema_path: Path) -> tuple[str, ...]:
    """Return schema errors for an optional artifact."""
    if not path.exists():
        return ()
    return tuple(validate_json_file(payload_path=path, schema_path=schema_path))


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
    """Load one JSON object or return an empty object."""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def object_field(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a nested object field."""
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def list_of_dicts(value: object) -> list[dict[str, Any]]:
    """Return object rows from a possible list."""
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def string_list(value: object) -> list[str]:
    """Return string rows from a possible list."""
    return [str(item) for item in value] if isinstance(value, list) else []


def unique_strings(values: list[str]) -> list[str]:
    """Return values in stable first-seen order."""
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root."""
    return path if path.is_absolute() else repo_root / path


def relative_path(path: Path, repo_root: Path) -> str:
    """Return a stable repository-relative path when possible."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(resolved)


def main() -> None:
    """CLI entrypoint for operator action audit generation."""
    parser = argparse.ArgumentParser(
        description="Write a read-only operator action artifact audit."
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    _, _, payload = write_operator_action_audit(
        run_dir=args.run_dir,
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
