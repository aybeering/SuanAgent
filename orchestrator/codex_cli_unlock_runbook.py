"""Read-only operator runbook for the real Codex CLI unlock chain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.codex_cli_dry_invocation_guard import load_json_object
from orchestrator.operator_action_audit import file_record, resolve_path
from orchestrator.operator_unlock_checklist import (
    artifact_navigation_record,
    build_operator_unlock_checklist,
    command_for_artifact,
    display_path,
    render_operator_unlock_checklist_markdown,
)
from orchestrator.schema_validation import (
    load_schema,
    validate_json_file,
    validate_json_payload,
)


CODEX_CLI_UNLOCK_RUNBOOK_SCHEMA_VERSION = "codex_cli_unlock_runbook_v1"
SCHEMA_PATH = Path("schemas/codex_cli_unlock_runbook.schema.json")

RUNBOOK_STEPS = (
    {
        "step_id": "step_001_execution_preflight",
        "artifact_id": "codex_cli_execution_preflight",
        "ready_field": "ok",
        "label": "Run startup execution preflight",
        "purpose": "record whether any real Codex profile requires operator unlock",
    },
    {
        "step_id": "step_002_readiness_pipeline",
        "artifact_id": "codex_cli_readiness_pipeline",
        "ready_field": "final_ready",
        "label": "Generate readiness pipeline evidence",
        "purpose": "aggregate read-only enablement, approval, preflight, canary, and dry-run evidence",
    },
    {
        "step_id": "step_003_execution_candidate",
        "artifact_id": "codex_cli_execution_candidate",
        "ready_field": "execution_candidate_ready",
        "label": "Freeze execution candidate",
        "purpose": "freeze the reviewed command, workspace path, and strategy-only mutation boundary",
    },
    {
        "step_id": "step_004_real_execution_dry_run",
        "artifact_id": "codex_cli_real_execution_dry_run",
        "ready_field": "real_execution_dry_run_ready",
        "label": "Dry-run the real execution boundary",
        "purpose": "verify the final real-execution boundary without executing Codex or creating workspaces",
    },
    {
        "step_id": "step_005_operator_unlock_request",
        "artifact_id": "codex_cli_operator_unlock_request",
        "ready_field": "operator_request_ready",
        "label": "Record operator unlock request",
        "purpose": "record explicit operator intent bound to the reviewed evidence and command digest",
    },
)


def write_codex_cli_unlock_runbook(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown Codex CLI unlock runbook artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_codex_cli_unlock_runbook(run_dir=run_dir, repo_root=repo_root)
    errors = validate_codex_cli_unlock_runbook_payload(
        payload,
        run_dir=run_dir,
        repo_root=repo_root,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "Codex CLI unlock runbook failed schema validation: " + "; ".join(errors)
        )
    json_path = run_dir / "codex_cli_unlock_runbook.json"
    md_path = run_dir / "codex_cli_unlock_runbook.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_codex_cli_unlock_runbook_markdown(payload), encoding="utf-8")
    errors = validate_codex_cli_unlock_runbook_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(
            "Codex CLI unlock runbook failed schema validation: " + "; ".join(errors)
        )
    return json_path, md_path, payload


def build_codex_cli_unlock_runbook(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return a deterministic read-only runbook for real Codex unlock review."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    checklist = build_operator_unlock_checklist(run_dir=run_dir, repo_root=repo_root)
    steps = [
        runbook_step(
            spec=spec,
            run_dir=run_dir,
            repo_root=repo_root,
        )
        for spec in RUNBOOK_STEPS
    ]
    summary = runbook_summary(steps=steps, checklist=checklist)
    return {
        "schema_version": CODEX_CLI_UNLOCK_RUNBOOK_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "status": runbook_status(summary=summary, checklist=checklist),
        "ready": bool(checklist.get("ready", False)) and summary["blocked_step_count"] == 0,
        "summary": summary,
        "source_checklist": {
            "artifact_name": "operator_unlock_checklist",
            "from_artifact": (run_dir / "operator_unlock_checklist.json").exists(),
            "file": file_record(run_dir / "operator_unlock_checklist.json", repo_root),
            "status": str(checklist.get("status", "")),
            "ready": bool(checklist.get("ready", False)),
            "failed_count": int(checklist.get("failed_count", 0) or 0),
            "markdown_preview": render_operator_unlock_checklist_markdown(checklist)
            .splitlines()[0],
        },
        "steps": steps,
        "operator_commands": operator_commands(steps),
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "runbook_only": True,
            "does_not_execute_commands": True,
            "does_not_execute_codex_cli": True,
            "does_not_record_operator_approval": True,
            "does_not_create_workspace": True,
            "does_not_send_strategy_prompt": True,
            "does_not_apply_patches": True,
            "does_not_route_agents": True,
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
    """Return one ordered operator runbook step."""
    artifact_id = spec["artifact_id"]
    artifact = artifact_navigation_record(
        artifact_id=artifact_id,
        run_dir=run_dir,
        repo_root=repo_root,
    )
    json_file = artifact.get("json_file", {})
    payload_path = run_dir / str(artifact_id_to_json_filename(artifact_id))
    payload = load_json_object(payload_path)
    ready_field = spec["ready_field"]
    ready = bool(payload.get(ready_field, False)) if payload else False
    exists = bool(json_file.get("exists", False)) if isinstance(json_file, dict) else False
    command = command_for_artifact(
        artifact_id=artifact_id,
        run_arg=display_path(run_dir, repo_root),
    )
    return {
        "step_id": spec["step_id"],
        "artifact_id": artifact_id,
        "label": spec["label"],
        "purpose": spec["purpose"],
        "status": step_status(exists=exists, ready=ready),
        "ready": ready,
        "required": True,
        "ready_field": ready_field,
        "artifact": artifact,
        "blocking_reasons": blocking_reasons_for_payload(payload),
        "command": {
            "label": str(artifact.get("write_command_label", "")),
            "command": command,
            "writes_artifacts": True,
            "executes_codex_cli": False,
            "requires_explicit_operator_invocation": True,
        },
        "authority": {
            "step_can_execute_command": False,
            "step_can_execute_codex_cli": False,
            "step_can_create_workspace": False,
            "step_can_apply_patches": False,
            "step_can_change_acceptance": False,
        },
    }


def artifact_id_to_json_filename(artifact_id: str) -> str:
    """Return the expected JSON filename for one unlock evidence artifact."""
    artifact_filenames = {
        "codex_cli_execution_preflight": "codex_cli_execution_preflight.json",
        "codex_cli_readiness_pipeline": "codex_cli_readiness_pipeline.json",
        "codex_cli_execution_candidate": "codex_cli_execution_candidate.json",
        "codex_cli_real_execution_dry_run": "codex_cli_real_execution_dry_run.json",
        "codex_cli_operator_unlock_request": "codex_cli_operator_unlock_request.json",
    }
    return artifact_filenames.get(artifact_id, "")


def step_status(*, exists: bool, ready: bool) -> str:
    """Return compact status for a runbook step."""
    if ready:
        return "ready"
    if exists:
        return "blocked"
    return "missing"


def blocking_reasons_for_payload(payload: dict[str, Any]) -> list[str]:
    """Return stable blocking reasons from a known Codex readiness artifact."""
    for key in (
        "blocking_reasons",
        "aggregate_blocking_reasons",
        "blocking_errors",
    ):
        if key not in payload:
            continue
        value = payload.get(key, [])
        if isinstance(value, list):
            return [str(row) for row in value]
    if payload and not bool(payload.get("ok", True)):
        return ["artifact_not_ok"]
    return []


def runbook_summary(
    *,
    steps: list[dict[str, object]],
    checklist: dict[str, object],
) -> dict[str, object]:
    """Return summary counts for the operator runbook."""
    missing_steps = [
        str(step.get("step_id", ""))
        for step in steps
        if step.get("status") == "missing"
    ]
    blocked_steps = [
        str(step.get("step_id", ""))
        for step in steps
        if step.get("status") == "blocked"
    ]
    ready_steps = [
        str(step.get("step_id", ""))
        for step in steps
        if step.get("status") == "ready"
    ]
    return {
        "step_count": len(steps),
        "ready_step_count": len(ready_steps),
        "missing_step_count": len(missing_steps),
        "blocked_step_count": len(blocked_steps),
        "operator_command_count": len(operator_commands(steps)),
        "checklist_status": str(checklist.get("status", "")),
        "checklist_ready": bool(checklist.get("ready", False)),
        "checklist_failed_count": int(checklist.get("failed_count", 0) or 0),
        "next_step_id": first_step_id(steps, statuses={"missing", "blocked"}),
        "ready_steps": ready_steps,
        "missing_steps": missing_steps,
        "blocked_steps": blocked_steps,
    }


def runbook_status(
    *,
    summary: dict[str, object],
    checklist: dict[str, object],
) -> str:
    """Return top-level runbook status."""
    if bool(checklist.get("ready", False)) and not summary.get("blocked_steps"):
        return "ready_for_operator_review"
    if int(summary.get("missing_step_count", 0) or 0):
        return "needs_artifacts"
    if int(summary.get("blocked_step_count", 0) or 0):
        return "blocked"
    return "not_requested"


def first_step_id(
    steps: list[dict[str, object]],
    *,
    statuses: set[str],
) -> str:
    """Return the first step id whose status is in the requested set."""
    for step in steps:
        if str(step.get("status", "")) in statuses:
            return str(step.get("step_id", ""))
    return ""


def operator_commands(steps: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return command rows from all runbook steps."""
    rows: list[dict[str, object]] = []
    for step in steps:
        command = step.get("command", {})
        if isinstance(command, dict):
            rows.append(command)
    return rows


def render_codex_cli_unlock_runbook_markdown(payload: dict[str, object]) -> str:
    """Render the Codex CLI unlock runbook as markdown."""
    summary = payload.get("summary", {})
    summary = summary if isinstance(summary, dict) else {}
    steps = [row for row in payload.get("steps", []) if isinstance(row, dict)]
    commands = [
        row for row in payload.get("operator_commands", []) if isinstance(row, dict)
    ]
    lines = [
        "# Codex CLI Unlock Runbook",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- Ready: `{payload.get('ready', False)}`",
        f"- Next step: `{summary.get('next_step_id', '')}`",
        "",
        "| Step | Status | Artifact | Command |",
        "| --- | --- | --- | --- |",
    ]
    for step in steps:
        artifact = step.get("artifact", {})
        artifact = artifact if isinstance(artifact, dict) else {}
        json_file = artifact.get("json_file", {})
        json_file = json_file if isinstance(json_file, dict) else {}
        command = step.get("command", {})
        command = command if isinstance(command, dict) else {}
        lines.append(
            "| "
            f"{step.get('label', '')} | "
            f"`{step.get('status', '')}` | "
            f"`{artifact.get('artifact_id', '')}` exists=`{json_file.get('exists', False)}` | "
            f"`{command.get('label', '')}` |"
        )
    lines.extend(["", "## Command Hints", ""])
    for command in commands:
        lines.append(
            f"- `{command.get('label', '')}`: `{command.get('command', '')}`"
        )
    if not commands:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This runbook is read-only and does not execute commands or Codex.",
            "- Every listed command requires explicit operator invocation.",
            "- It does not create workspaces, apply patches, route agents, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_codex_cli_unlock_runbook_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved Codex CLI unlock runbook artifact."""
    schema_errors = tuple(
        validate_json_file(
            payload_path=payload_path,
            schema_path=repo_root / SCHEMA_PATH,
        )
    )
    if schema_errors:
        return schema_errors
    return schema_errors + validate_codex_cli_unlock_runbook_consistency(
        load_json_object(payload_path)
    )


def validate_codex_cli_unlock_runbook_payload(
    payload: dict[str, object],
    *,
    run_dir: Path | None = None,
    repo_root: Path = Path("."),
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an in-memory Codex CLI unlock runbook payload."""
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
    errors.extend(validate_codex_cli_unlock_runbook_consistency(comparable_payload))
    if require_current_evidence:
        if run_dir is None:
            errors.append("codex_cli_unlock_runbook run_dir required")
        else:
            expected = build_codex_cli_unlock_runbook(
                run_dir=resolve_path(run_dir, repo_root),
                repo_root=repo_root,
            )
            if comparable_payload != expected:
                errors.append("codex_cli_unlock_runbook current evidence mismatch")
    return tuple(errors)


def strip_terminal_metadata(payload: dict[str, object]) -> dict[str, object]:
    """Return payload without terminal-only annotation fields."""
    stripped = dict(payload)
    stripped.pop("from_artifact", None)
    return stripped


def validate_codex_cli_unlock_runbook_consistency(
    payload: dict[str, object],
) -> tuple[str, ...]:
    """Validate derived Codex CLI unlock runbook fields against the payload."""
    errors: list[str] = []
    steps = list_of_dicts(payload.get("steps", []))
    summary = dict_field(payload, "summary")
    checklist = dict_field(payload, "source_checklist")
    commands = list_of_dicts(payload.get("operator_commands", []))

    expected_artifact_ids = [spec["artifact_id"] for spec in RUNBOOK_STEPS]
    expected_step_ids = [spec["step_id"] for spec in RUNBOOK_STEPS]
    artifact_ids = [str(step.get("artifact_id", "")) for step in steps]
    step_ids = [str(step.get("step_id", "")) for step in steps]
    if artifact_ids != expected_artifact_ids:
        errors.append("codex_cli_unlock_runbook step order mismatch")
    if step_ids != expected_step_ids:
        errors.append("codex_cli_unlock_runbook step ids mismatch")

    ready_steps = [
        str(step.get("step_id", ""))
        for step in steps
        if step.get("status") == "ready"
    ]
    missing_steps = [
        str(step.get("step_id", ""))
        for step in steps
        if step.get("status") == "missing"
    ]
    blocked_steps = [
        str(step.get("step_id", ""))
        for step in steps
        if step.get("status") == "blocked"
    ]
    if int(summary.get("step_count", -1)) != len(steps):
        errors.append("codex_cli_unlock_runbook step count mismatch")
    if int(summary.get("ready_step_count", -1)) != len(ready_steps):
        errors.append("codex_cli_unlock_runbook ready count mismatch")
    if int(summary.get("missing_step_count", -1)) != len(missing_steps):
        errors.append("codex_cli_unlock_runbook missing count mismatch")
    if int(summary.get("blocked_step_count", -1)) != len(blocked_steps):
        errors.append("codex_cli_unlock_runbook blocked count mismatch")
    if string_rows(summary.get("ready_steps", [])) != ready_steps:
        errors.append("codex_cli_unlock_runbook ready steps mismatch")
    if string_rows(summary.get("missing_steps", [])) != missing_steps:
        errors.append("codex_cli_unlock_runbook missing steps mismatch")
    if string_rows(summary.get("blocked_steps", [])) != blocked_steps:
        errors.append("codex_cli_unlock_runbook blocked steps mismatch")
    expected_next_step = first_step_id(steps, statuses={"missing", "blocked"})
    if str(summary.get("next_step_id", "")) != expected_next_step:
        errors.append("codex_cli_unlock_runbook next step mismatch")
    if int(summary.get("operator_command_count", -1)) != len(commands):
        errors.append("codex_cli_unlock_runbook command count mismatch")

    checklist_ready = bool(checklist.get("ready", False))
    expected_status = runbook_status(summary=summary, checklist=checklist)
    expected_ready = checklist_ready and len(blocked_steps) == 0
    if str(payload.get("status", "")) != expected_status:
        errors.append("codex_cli_unlock_runbook status mismatch")
    if bool(payload.get("ready", False)) != expected_ready:
        errors.append("codex_cli_unlock_runbook ready mismatch")
    if str(summary.get("checklist_status", "")) != str(checklist.get("status", "")):
        errors.append("codex_cli_unlock_runbook checklist status mismatch")
    if bool(summary.get("checklist_ready", False)) != checklist_ready:
        errors.append("codex_cli_unlock_runbook checklist ready mismatch")
    if int(summary.get("checklist_failed_count", -1)) != int(
        checklist.get("failed_count", 0) or 0
    ):
        errors.append("codex_cli_unlock_runbook checklist failed count mismatch")

    errors.extend(validate_runbook_steps(steps=steps))
    errors.extend(validate_runbook_commands(payload=payload, steps=steps))
    errors.extend(validate_runbook_policy(payload=payload))
    return tuple(errors)


def validate_runbook_steps(*, steps: list[dict[str, Any]]) -> tuple[str, ...]:
    """Validate each Codex CLI unlock runbook step."""
    errors: list[str] = []
    for step in steps:
        status = str(step.get("status", ""))
        ready = bool(step.get("ready", False))
        if status == "ready" and not ready:
            errors.append("codex_cli_unlock_runbook ready step false")
        if status in {"missing", "blocked"} and ready:
            errors.append("codex_cli_unlock_runbook blocked step ready true")
        artifact = dict_field(step, "artifact")
        if str(artifact.get("artifact_id", "")) != str(step.get("artifact_id", "")):
            errors.append("codex_cli_unlock_runbook step artifact mismatch")
        if str(artifact.get("write_command_label", "")) != str(
            dict_field(step, "command").get("label", "")
        ):
            errors.append("codex_cli_unlock_runbook step command label mismatch")
        authority = dict_field(step, "authority")
        for key in (
            "step_can_execute_command",
            "step_can_execute_codex_cli",
            "step_can_create_workspace",
            "step_can_apply_patches",
            "step_can_change_acceptance",
        ):
            if bool(authority.get(key, True)):
                errors.append(f"codex_cli_unlock_runbook authority true: {key}")
    return tuple(errors)


def validate_runbook_commands(
    *,
    payload: dict[str, object],
    steps: list[dict[str, Any]],
) -> tuple[str, ...]:
    """Validate operator command hints stay bounded and match ordered steps."""
    errors: list[str] = []
    commands = list_of_dicts(payload.get("operator_commands", []))
    step_commands = [dict_field(step, "command") for step in steps]
    if commands != step_commands:
        errors.append("codex_cli_unlock_runbook operator commands mismatch")

    expected_artifacts = command_artifacts()
    unsafe_tokens = ("&&", "||", "|", "`", "$(", "\n", ";")
    for index, command in enumerate(commands):
        label = str(command.get("label", ""))
        expected_artifact = expected_artifacts.get(label, "")
        if not expected_artifact:
            errors.append(f"codex_cli_unlock_runbook command unknown: {label}")
        elif (
            index < len(steps)
            and str(steps[index].get("artifact_id", "")) != expected_artifact
        ):
            errors.append("codex_cli_unlock_runbook command artifact mismatch")
        if bool(command.get("executes_codex_cli", True)):
            errors.append("codex_cli_unlock_runbook command executes Codex")
        if not bool(command.get("requires_explicit_operator_invocation", False)):
            errors.append("codex_cli_unlock_runbook command lacks explicit gate")
        if not bool(command.get("writes_artifacts", False)):
            errors.append("codex_cli_unlock_runbook command write flag mismatch")
        command_text = str(command.get("command", ""))
        if any(token in command_text for token in unsafe_tokens):
            errors.append("codex_cli_unlock_runbook command unsafe token")
    return tuple(errors)


def validate_runbook_policy(payload: dict[str, object]) -> tuple[str, ...]:
    """Validate runbook policy flags preserve read-only authority."""
    errors: list[str] = []
    policy = dict_field(payload, "policy")
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
            errors.append(f"codex_cli_unlock_runbook policy false: {key}")
    return tuple(errors)


def command_artifacts() -> dict[str, str]:
    """Return expected command-label to artifact-id bindings for the runbook."""
    return {
        "run_execution_preflight": "codex_cli_execution_preflight",
        "run_readiness_pipeline": "codex_cli_readiness_pipeline",
        "write_execution_candidate": "codex_cli_execution_candidate",
        "write_real_execution_dry_run": "codex_cli_real_execution_dry_run",
        "write_operator_unlock_request": "codex_cli_operator_unlock_request",
    }


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


def main() -> None:
    """CLI entrypoint for Codex CLI unlock runbook generation."""
    parser = argparse.ArgumentParser(
        description="Write a read-only Codex CLI unlock runbook for one iteration run."
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    _, _, payload = write_codex_cli_unlock_runbook(
        run_dir=args.run_dir,
        repo_root=args.repo_root,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
