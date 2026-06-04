"""Read-only operator runbook for guarded config review and application."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.operator_action_audit import file_record, resolve_path
from orchestrator.operator_config_review import REQUIRED_APPROVAL_PHRASE
from orchestrator.schema_validation import (
    load_schema,
    validate_json_file,
    validate_json_payload,
)


CONFIG_OPERATOR_RUNBOOK_SCHEMA_VERSION = "config_operator_runbook_v1"
SCHEMA_PATH = Path("schemas/config_operator_runbook.schema.json")

STEP_SPECS = (
    {
        "step_id": "step_001_config_candidates",
        "artifact_id": "config_change_candidate",
        "filename": "config_change_candidate.json",
        "label": "Inspect config change candidates",
        "purpose": "review advisory config candidates before recording operator intent",
        "command_label": "inspect_config_candidates",
    },
    {
        "step_id": "step_002_operator_review",
        "artifact_id": "operator_config_review",
        "filename": "operator_config_review.json",
        "label": "Record operator config review",
        "purpose": "record explicit approve or reject intent for selected candidates",
        "command_label": "record_operator_approval",
    },
    {
        "step_id": "step_003_application_dry_run",
        "artifact_id": "config_application_dry_run",
        "filename": "config_application_dry_run.json",
        "label": "Preview config application",
        "purpose": "verify approved candidates still match current config before apply",
        "command_label": "write_config_application_dry_run",
    },
    {
        "step_id": "step_004_apply_approved_config",
        "artifact_id": "config_application_receipt",
        "filename": "config_application_receipt.json",
        "label": "Apply approved config",
        "purpose": "apply config only from ready dry-run evidence and matching digests",
        "command_label": "apply_config_approved",
    },
    {
        "step_id": "step_005_rollback_preview",
        "artifact_id": "config_application_rollback_preview",
        "filename": "config_application_rollback_preview.json",
        "label": "Preview config rollback",
        "purpose": "preview restore rows and next-run impact from an applied receipt",
        "command_label": "write_config_rollback_preview",
    },
    {
        "step_id": "step_006_restore_approved_config",
        "artifact_id": "config_application_restore_receipt",
        "filename": "config_application_restore_receipt.json",
        "label": "Restore approved config",
        "purpose": "restore config only from ready rollback-preview evidence",
        "command_label": "restore_config_approved",
    },
    {
        "step_id": "step_007_config_lineage",
        "artifact_id": "config_lineage",
        "filename": "config_lineage.json",
        "label": "Inspect config lineage",
        "purpose": "inspect the digest-checked config candidate/review/apply/restore chain",
        "command_label": "inspect_config_lineage",
    },
)


def write_config_operator_runbook(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown config operator runbook artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_config_operator_runbook(run_dir=run_dir, repo_root=repo_root)
    errors = validate_config_operator_runbook_payload(
        payload,
        run_dir=run_dir,
        repo_root=repo_root,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "config operator runbook failed schema validation: " + "; ".join(errors)
        )
    json_path = run_dir / "config_operator_runbook.json"
    md_path = run_dir / "config_operator_runbook.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_config_operator_runbook_markdown(payload), encoding="utf-8")
    errors = validate_config_operator_runbook_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(
            "config operator runbook failed schema validation: " + "; ".join(errors)
        )
    return json_path, md_path, payload


def build_config_operator_runbook(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return a deterministic read-only runbook for guarded config operations."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    steps = [
        runbook_step(spec=spec, run_dir=run_dir, repo_root=repo_root)
        for spec in STEP_SPECS
    ]
    summary = runbook_summary(steps=steps)
    return {
        "schema_version": CONFIG_OPERATOR_RUNBOOK_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": relative_path(run_dir, repo_root),
        "status": runbook_status(summary),
        "ready": str(summary.get("workflow_phase", "")) in {"applied", "restored"},
        "summary": summary,
        "steps": steps,
        "operator_commands": operator_commands(steps),
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "runbook_only": True,
            "does_not_execute_commands": True,
            "does_not_record_operator_review": True,
            "does_not_write_config": True,
            "does_not_delete_memory": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_route_candidates": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
            "commands_require_explicit_operator_invocation": True,
        },
    }


def runbook_step(
    *,
    spec: dict[str, str],
    run_dir: Path,
    repo_root: Path,
) -> dict[str, object]:
    """Return one config operator runbook step."""
    payload_path = run_dir / spec["filename"]
    payload = load_json_object(payload_path)
    exists = payload_path.exists()
    status = step_status(artifact_id=spec["artifact_id"], payload=payload, exists=exists)
    command = command_for_step(
        command_label=spec["command_label"],
        run_dir=run_dir,
        repo_root=repo_root,
    )
    return {
        "step_id": spec["step_id"],
        "artifact_id": spec["artifact_id"],
        "label": spec["label"],
        "purpose": spec["purpose"],
        "status": status,
        "ready": status == "ready",
        "artifact": {
            "artifact_id": spec["artifact_id"],
            "json_file": file_record(payload_path, repo_root),
            "markdown_file": file_record(
                payload_path.with_suffix(".md"),
                repo_root,
            ),
            "status": artifact_status(artifact_id=spec["artifact_id"], payload=payload),
        },
        "blocking_reasons": blocking_reasons(
            artifact_id=spec["artifact_id"],
            payload=payload,
            exists=exists,
        ),
        "command": command,
        "authority": {
            "step_can_execute_command": False,
            "step_can_record_review": False,
            "step_can_write_config": False,
            "step_can_execute_agents": False,
            "step_can_run_backtests": False,
            "step_can_change_acceptance": False,
        },
    }


def step_status(
    *,
    artifact_id: str,
    payload: dict[str, Any],
    exists: bool,
) -> str:
    """Return one step status from saved artifact evidence."""
    if not exists:
        return "missing"
    if artifact_id == "config_change_candidate":
        summary = dict_field(payload, "summary")
        if int(summary.get("candidate_count", 0) or 0) <= 0:
            return "not_applicable"
        return "ready"
    if artifact_id == "operator_config_review":
        intent = dict_field(payload, "operator_intent")
        if intent.get("review_recorded") is True and intent.get("decision_requested") == "approve":
            return "ready"
        return "blocked"
    if artifact_id == "config_application_dry_run":
        return "ready" if payload.get("status") == "ready_for_manual_application" else "blocked"
    if artifact_id == "config_application_receipt":
        return "ready" if payload.get("applied") is True else "blocked"
    if artifact_id == "config_application_rollback_preview":
        return "ready" if payload.get("status") == "rollback_ready" else "blocked"
    if artifact_id == "config_application_restore_receipt":
        return "ready" if payload.get("restored") is True else "blocked"
    if artifact_id == "config_lineage":
        return "ready" if payload.get("ok") is True else "blocked"
    return "blocked"


def artifact_status(*, artifact_id: str, payload: dict[str, Any]) -> str:
    """Return the status field used by one source artifact."""
    if not payload:
        return ""
    if artifact_id == "config_change_candidate":
        return str(dict_field(payload, "summary").get("status", ""))
    return str(payload.get("status", ""))


def blocking_reasons(
    *,
    artifact_id: str,
    payload: dict[str, Any],
    exists: bool,
) -> list[str]:
    """Return compact blocking reasons for one step."""
    if not exists:
        return [f"{artifact_id}_missing"]
    if artifact_id == "config_change_candidate":
        if int(dict_field(payload, "summary").get("candidate_count", 0) or 0) <= 0:
            return ["no_config_candidates"]
        return []
    if artifact_id == "operator_config_review":
        return string_rows(dict_field(payload, "review_gate").get("review_blockers", []))
    if artifact_id == "config_application_dry_run":
        return string_rows(
            dict_field(payload, "application_gate").get("application_blockers", [])
        )
    if artifact_id == "config_application_receipt":
        return string_rows(dict_field(payload, "evidence_checks").get("blockers", []))
    if artifact_id == "config_application_rollback_preview":
        return string_rows(dict_field(payload, "rollback_gate").get("blockers", []))
    if artifact_id == "config_application_restore_receipt":
        return string_rows(dict_field(payload, "restore_gate").get("blockers", []))
    if artifact_id == "config_lineage" and payload.get("ok") is not True:
        return ["config_lineage_not_ok"]
    return []


def command_for_step(
    *,
    command_label: str,
    run_dir: Path,
    repo_root: Path,
) -> dict[str, object]:
    """Return an explicit operator command hint for one step."""
    run_arg = relative_path(run_dir, repo_root)
    run_id = run_dir.name
    commands = {
        "inspect_config_candidates": (
            f"python -m orchestrator.experiments config-change-candidate {run_id}"
        ),
        "record_operator_approval": (
            "python -m orchestrator.operator_config_review "
            f"{run_arg} --decision approve --operator-id <operator> "
            f'--confirmation-phrase "{REQUIRED_APPROVAL_PHRASE}" '
            "--candidate-id <candidate_id>"
        ),
        "write_config_application_dry_run": (
            f"python -m orchestrator.config_application_dry_run {run_arg} "
            "--config config/default.json"
        ),
        "apply_config_approved": (
            f"python -m orchestrator.experiments apply-config-approved {run_id} "
            f"--dry-run-path {run_arg}/config_application_dry_run.json"
        ),
        "write_config_rollback_preview": (
            f"python -m orchestrator.config_application_rollback_preview {run_id} "
            f"--receipt-path {run_arg}/config_application_receipt.json"
        ),
        "restore_config_approved": (
            f"python -m orchestrator.experiments restore-config-approved {run_id} "
            f"--preview-path {run_arg}/config_application_rollback_preview.json"
        ),
        "inspect_config_lineage": (
            f"python -m orchestrator.experiments config-lineage {run_id}"
        ),
    }
    artifact_ids = {
        "inspect_config_candidates": "config_change_candidate",
        "record_operator_approval": "operator_config_review",
        "write_config_application_dry_run": "config_application_dry_run",
        "apply_config_approved": "config_application_receipt",
        "write_config_rollback_preview": "config_application_rollback_preview",
        "restore_config_approved": "config_application_restore_receipt",
        "inspect_config_lineage": "config_lineage",
    }
    writes_config = command_label in {"apply_config_approved", "restore_config_approved"}
    return {
        "label": command_label,
        "artifact_id": artifact_ids.get(command_label, ""),
        "command": commands.get(command_label, ""),
        "writes_artifacts": True,
        "writes_config_if_invoked": writes_config,
        "requires_explicit_operator_invocation": True,
        "runbook_executes_command": False,
    }


def runbook_summary(*, steps: list[dict[str, object]]) -> dict[str, object]:
    """Return summary counts and next operator step."""
    ready_steps = step_ids_with_status(steps, "ready")
    missing_steps = step_ids_with_status(steps, "missing")
    blocked_steps = step_ids_with_status(steps, "blocked")
    not_applicable_steps = step_ids_with_status(steps, "not_applicable")
    phase = workflow_phase(steps)
    next_command = next_command_label(steps=steps, phase=phase)
    return {
        "step_count": len(steps),
        "ready_step_count": len(ready_steps),
        "missing_step_count": len(missing_steps),
        "blocked_step_count": len(blocked_steps),
        "not_applicable_step_count": len(not_applicable_steps),
        "operator_command_count": len(operator_commands(steps)),
        "workflow_phase": phase,
        "next_step_id": first_incomplete_step_id(steps),
        "next_command_label": next_command,
        "ready_steps": ready_steps,
        "missing_steps": missing_steps,
        "blocked_steps": blocked_steps,
        "not_applicable_steps": not_applicable_steps,
    }


def workflow_phase(steps: list[dict[str, object]]) -> str:
    """Return a compact current phase for the config workflow."""
    by_artifact = {str(step.get("artifact_id", "")): step for step in steps}
    if by_artifact.get("config_application_restore_receipt", {}).get("ready") is True:
        return "restored"
    if by_artifact.get("config_application_receipt", {}).get("ready") is True:
        return "applied"
    if by_artifact.get("config_application_dry_run", {}).get("ready") is True:
        return "ready_for_apply"
    if by_artifact.get("operator_config_review", {}).get("ready") is True:
        return "approved"
    candidate = by_artifact.get("config_change_candidate", {})
    if candidate.get("status") == "not_applicable":
        return "no_config_candidates"
    if candidate.get("ready") is True:
        return "needs_operator_review"
    return "needs_config_candidates"


def runbook_status(summary: dict[str, object]) -> str:
    """Return top-level runbook status."""
    phase = str(summary.get("workflow_phase", ""))
    if phase in {"restored", "applied"}:
        return phase
    if phase == "no_config_candidates":
        return "not_applicable"
    return "needs_operator_action"


def next_command_label(*, steps: list[dict[str, object]], phase: str) -> str:
    """Return the next command label an operator would invoke manually."""
    command_by_artifact = {
        str(step.get("artifact_id", "")): dict_field(step, "command")
        for step in steps
    }
    phase_to_artifact = {
        "needs_config_candidates": "config_change_candidate",
        "needs_operator_review": "operator_config_review",
        "approved": "config_application_dry_run",
        "ready_for_apply": "config_application_receipt",
        "applied": "config_application_rollback_preview",
    }
    artifact_id = phase_to_artifact.get(phase, "")
    return str(command_by_artifact.get(artifact_id, {}).get("label", ""))


def step_ids_with_status(steps: list[dict[str, object]], status: str) -> list[str]:
    """Return step ids with one status."""
    return [
        str(step.get("step_id", ""))
        for step in steps
        if str(step.get("status", "")) == status
    ]


def first_incomplete_step_id(steps: list[dict[str, object]]) -> str:
    """Return the first missing or blocked step id."""
    for step in steps:
        if str(step.get("status", "")) in {"missing", "blocked"}:
            return str(step.get("step_id", ""))
    return ""


def operator_commands(steps: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return command rows from all steps."""
    rows: list[dict[str, object]] = []
    for step in steps:
        command = step.get("command", {})
        if isinstance(command, dict):
            rows.append(command)
    return rows


def render_config_operator_runbook_markdown(payload: dict[str, object]) -> str:
    """Render a config operator runbook as markdown."""
    summary = dict_field(payload, "summary")
    steps = list_of_dicts(payload.get("steps", []))
    commands = list_of_dicts(payload.get("operator_commands", []))
    lines = [
        "# Config Operator Runbook",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- Workflow phase: `{summary.get('workflow_phase', '')}`",
        f"- Next command: `{summary.get('next_command_label', '')}`",
        "",
        "| Step | Status | Artifact | Command |",
        "| --- | --- | --- | --- |",
    ]
    for step in steps:
        artifact = dict_field(step, "artifact")
        json_file = dict_field(artifact, "json_file")
        command = dict_field(step, "command")
        lines.append(
            "| "
            f"{step.get('label', '')} | "
            f"`{step.get('status', '')}` | "
            f"`{artifact.get('artifact_id', '')}` exists=`{json_file.get('exists', False)}` | "
            f"`{command.get('label', '')}` |"
        )
    lines.extend(["", "## Command Hints", ""])
    for command in commands:
        marker = " writes config if invoked" if command.get("writes_config_if_invoked") else ""
        lines.append(
            f"- `{command.get('label', '')}`{marker}: `{command.get('command', '')}`"
        )
    if not commands:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This runbook is read-only and does not execute commands.",
            "- Approval, apply, and restore still require explicit operator invocation.",
            "- It does not write config, execute agents, run backtests, route candidates, apply patches, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_config_operator_runbook_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved config operator runbook artifact."""
    schema_errors = tuple(
        validate_json_file(
            payload_path=payload_path,
            schema_path=repo_root / SCHEMA_PATH,
        )
    )
    if schema_errors:
        return schema_errors
    return schema_errors + validate_config_operator_runbook_consistency(
        load_json_object(payload_path)
    )


def validate_config_operator_runbook_payload(
    payload: dict[str, object],
    *,
    run_dir: Path | None = None,
    repo_root: Path = Path("."),
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an in-memory config operator runbook payload."""
    repo_root = repo_root.resolve()
    comparable_payload = strip_terminal_metadata(payload)
    schema = load_schema(repo_root / SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=comparable_payload,
            schema=schema,
            schema_dir=(repo_root / SCHEMA_PATH).parent,
        )
    )
    errors.extend(validate_config_operator_runbook_consistency(comparable_payload))
    if require_current_evidence:
        if run_dir is None:
            errors.append("config_operator_runbook run_dir required")
        else:
            expected = build_config_operator_runbook(
                run_dir=resolve_path(run_dir, repo_root),
                repo_root=repo_root,
            )
            if comparable_payload != expected:
                errors.append("config_operator_runbook current evidence mismatch")
    return tuple(errors)


def strip_terminal_metadata(payload: dict[str, object]) -> dict[str, object]:
    """Return payload without terminal-only annotation fields."""
    stripped = dict(payload)
    stripped.pop("from_artifact", None)
    return stripped


def validate_config_operator_runbook_consistency(
    payload: dict[str, object],
) -> tuple[str, ...]:
    """Validate derived config operator runbook fields."""
    errors: list[str] = []
    steps = list_of_dicts(payload.get("steps", []))
    summary = dict_field(payload, "summary")
    commands = list_of_dicts(payload.get("operator_commands", []))
    expected_artifacts = [spec["artifact_id"] for spec in STEP_SPECS]
    expected_steps = [spec["step_id"] for spec in STEP_SPECS]
    if [str(step.get("artifact_id", "")) for step in steps] != expected_artifacts:
        errors.append("config_operator_runbook step order mismatch")
    if [str(step.get("step_id", "")) for step in steps] != expected_steps:
        errors.append("config_operator_runbook step ids mismatch")

    ready_steps = step_ids_with_status(steps, "ready")
    missing_steps = step_ids_with_status(steps, "missing")
    blocked_steps = step_ids_with_status(steps, "blocked")
    not_applicable_steps = step_ids_with_status(steps, "not_applicable")
    if int(summary.get("step_count", -1)) != len(steps):
        errors.append("config_operator_runbook step count mismatch")
    if int(summary.get("ready_step_count", -1)) != len(ready_steps):
        errors.append("config_operator_runbook ready count mismatch")
    if int(summary.get("missing_step_count", -1)) != len(missing_steps):
        errors.append("config_operator_runbook missing count mismatch")
    if int(summary.get("blocked_step_count", -1)) != len(blocked_steps):
        errors.append("config_operator_runbook blocked count mismatch")
    if int(summary.get("not_applicable_step_count", -1)) != len(not_applicable_steps):
        errors.append("config_operator_runbook not applicable count mismatch")
    if int(summary.get("operator_command_count", -1)) != len(commands):
        errors.append("config_operator_runbook command count mismatch")
    expected_phase = workflow_phase(steps)
    if str(summary.get("workflow_phase", "")) != expected_phase:
        errors.append("config_operator_runbook workflow phase mismatch")
    if str(summary.get("next_step_id", "")) != first_incomplete_step_id(steps):
        errors.append("config_operator_runbook next step mismatch")
    if str(summary.get("next_command_label", "")) != next_command_label(
        steps=steps,
        phase=expected_phase,
    ):
        errors.append("config_operator_runbook next command mismatch")
    for key, expected in (
        ("ready_steps", ready_steps),
        ("missing_steps", missing_steps),
        ("blocked_steps", blocked_steps),
        ("not_applicable_steps", not_applicable_steps),
    ):
        if string_rows(summary.get(key, [])) != expected:
            errors.append(f"config_operator_runbook {key} mismatch")
    if str(payload.get("status", "")) != runbook_status(summary):
        errors.append("config_operator_runbook status mismatch")
    if bool(payload.get("ready", False)) != (
        str(summary.get("workflow_phase", "")) in {"applied", "restored"}
    ):
        errors.append("config_operator_runbook ready mismatch")
    errors.extend(validate_steps(steps=steps))
    errors.extend(validate_commands(payload=payload, steps=steps))
    errors.extend(validate_policy(payload=payload))
    return tuple(errors)


def validate_steps(*, steps: list[dict[str, Any]]) -> tuple[str, ...]:
    """Validate each runbook step."""
    errors: list[str] = []
    for step in steps:
        status = str(step.get("status", ""))
        ready = bool(step.get("ready", False))
        if status == "ready" and not ready:
            errors.append("config_operator_runbook ready step false")
        if status in {"missing", "blocked", "not_applicable"} and ready:
            errors.append("config_operator_runbook inactive step ready true")
        artifact = dict_field(step, "artifact")
        if str(artifact.get("artifact_id", "")) != str(step.get("artifact_id", "")):
            errors.append("config_operator_runbook step artifact mismatch")
        if str(dict_field(step, "command").get("artifact_id", "")) != str(
            step.get("artifact_id", "")
        ):
            errors.append("config_operator_runbook step command artifact mismatch")
        authority = dict_field(step, "authority")
        for key in (
            "step_can_execute_command",
            "step_can_record_review",
            "step_can_write_config",
            "step_can_execute_agents",
            "step_can_run_backtests",
            "step_can_change_acceptance",
        ):
            if bool(authority.get(key, True)):
                errors.append(f"config_operator_runbook authority true: {key}")
    return tuple(errors)


def validate_commands(
    *,
    payload: dict[str, object],
    steps: list[dict[str, Any]],
) -> tuple[str, ...]:
    """Validate command hints stay bounded and match steps."""
    errors: list[str] = []
    commands = list_of_dicts(payload.get("operator_commands", []))
    step_commands = [dict_field(step, "command") for step in steps]
    if commands != step_commands:
        errors.append("config_operator_runbook operator commands mismatch")
    expected = command_artifacts()
    unsafe_tokens = ("&&", "||", "|", "`", "$(", "\n", ";")
    for command in commands:
        label = str(command.get("label", ""))
        if expected.get(label, "") != str(command.get("artifact_id", "")):
            errors.append("config_operator_runbook command artifact mismatch")
        if bool(command.get("runbook_executes_command", True)):
            errors.append("config_operator_runbook command executes by itself")
        if not bool(command.get("requires_explicit_operator_invocation", False)):
            errors.append("config_operator_runbook command lacks explicit gate")
        command_text = str(command.get("command", ""))
        if any(token in command_text for token in unsafe_tokens):
            errors.append("config_operator_runbook command unsafe token")
    return tuple(errors)


def validate_policy(payload: dict[str, object]) -> tuple[str, ...]:
    """Validate runbook policy flags preserve read-only authority."""
    errors: list[str] = []
    policy = dict_field(payload, "policy")
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "runbook_only",
        "does_not_execute_commands",
        "does_not_record_operator_review",
        "does_not_write_config",
        "does_not_delete_memory",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_route_candidates",
        "does_not_apply_patches",
        "does_not_change_acceptance",
        "commands_require_explicit_operator_invocation",
    ):
        if not bool(policy.get(key, False)):
            errors.append(f"config_operator_runbook policy false: {key}")
    return tuple(errors)


def command_artifacts() -> dict[str, str]:
    """Return expected command-label to artifact-id bindings."""
    return {
        "inspect_config_candidates": "config_change_candidate",
        "record_operator_approval": "operator_config_review",
        "write_config_application_dry_run": "config_application_dry_run",
        "apply_config_approved": "config_application_receipt",
        "write_config_rollback_preview": "config_application_rollback_preview",
        "restore_config_approved": "config_application_restore_receipt",
        "inspect_config_lineage": "config_lineage",
    }


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object or return an empty object."""
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def dict_field(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a nested dictionary field or an empty dictionary."""
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def list_of_dicts(value: object) -> list[dict[str, Any]]:
    """Return dictionaries from a JSON list value."""
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def string_rows(value: object) -> list[str]:
    """Return strings from a JSON list value."""
    if not isinstance(value, list):
        return []
    return [str(row) for row in value]


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> None:
    """CLI entrypoint for config operator runbook generation."""
    parser = argparse.ArgumentParser(
        description="Write a read-only config operator runbook for one iteration run."
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    _, _, payload = write_config_operator_runbook(
        run_dir=args.run_dir,
        repo_root=args.repo_root,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
