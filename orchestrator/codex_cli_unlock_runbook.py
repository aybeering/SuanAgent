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
from orchestrator.schema_validation import validate_json_file


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
    return tuple(
        validate_json_file(
            payload_path=payload_path,
            schema_path=repo_root / SCHEMA_PATH,
        )
    )


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
