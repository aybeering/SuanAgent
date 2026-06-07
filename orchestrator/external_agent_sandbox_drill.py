"""Run-level sandbox drill report for future external agent execution."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from orchestrator.schema_validation import validate_json_file


EXTERNAL_AGENT_SANDBOX_DRILL_SCHEMA_VERSION = "external_agent_sandbox_drill_v1"
SCHEMA_PATH = Path("schemas/external_agent_sandbox_drill.schema.json")
WORKSPACE_ADAPTERS = {"codex_cli", "codex_dry_run", "codex_cli_dry_run", "file_protocol"}


def build_external_agent_sandbox_drill(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Return a deterministic dry-run report for external agent slots."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    slots: list[dict[str, Any]] = []
    for round_dir in round_dirs(run_dir):
        slots.extend(
            round_sandbox_rows(
                round_dir=round_dir,
                repo_root=repo_root,
            )
        )
    status_counts = Counter(str(slot["sandbox_status"]) for slot in slots)
    return {
        "schema_version": EXTERNAL_AGENT_SANDBOX_DRILL_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "ok": status_counts.get("blocked", 0) == 0,
        "source_artifacts": {
            "rounds": [
                str(path / "agent_execution_plan.json") for path in round_dirs(run_dir)
            ],
        },
        "totals": {
            "slot_count": len(slots),
            "external_slot_count": sum(1 for slot in slots if slot["external_slot"]),
            "dry_run_only_count": sum(1 for slot in slots if slot["dry_run_only"]),
            "subprocess_executed_count": sum(
                1 for slot in slots if slot["subprocess_executed"]
            ),
            "blocked_count": status_counts.get("blocked", 0),
        },
        "status_counts": dict(sorted(status_counts.items())),
        "slots": slots,
        "policy": {
            "sandbox_drill_only": True,
            "does_not_execute_agents": True,
            "does_not_apply_patches": True,
            "does_not_select_candidate": True,
            "does_not_change_acceptance": True,
            "deterministic_code_keeps_acceptance_authority": True,
        },
    }


def write_external_agent_sandbox_drill(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    """Write JSON and markdown sandbox-drill reports for one run."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_external_agent_sandbox_drill(
        run_dir=run_dir,
        repo_root=repo_root,
    )
    destination = output_path or run_dir / "external_agent_sandbox_drill.json"
    write_json(destination, payload)
    markdown_destination = markdown_path or run_dir / "external_agent_sandbox_drill.md"
    markdown_destination.write_text(
        external_agent_sandbox_drill_markdown(payload),
        encoding="utf-8",
    )
    return payload


def validate_external_agent_sandbox_drill_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
    schema_path: Path | None = None,
    require_current_evidence: bool = True,
) -> tuple[str, ...]:
    """Validate a saved sandbox-drill report against schema and evidence."""
    repo_root = repo_root.resolve()
    schema_errors = tuple(
        validate_json_file(
            payload_path=payload_path,
            schema_path=schema_path or repo_root / SCHEMA_PATH,
        )
    )
    if schema_errors or not require_current_evidence:
        return schema_errors
    payload = load_json_object(payload_path)
    run_dir_value = str(payload.get("run_dir", ""))
    if not run_dir_value:
        return schema_errors + ("external_agent_sandbox_drill run_dir required",)
    expected = build_external_agent_sandbox_drill(
        run_dir=resolve_path(Path(run_dir_value), repo_root),
        repo_root=repo_root,
    )
    if payload != expected:
        return schema_errors + (
            "external_agent_sandbox_drill current evidence mismatch",
        )
    return schema_errors


def round_sandbox_rows(*, round_dir: Path, repo_root: Path) -> list[dict[str, Any]]:
    """Return sandbox rows for external slots in one round."""
    plan = load_json_object(round_dir / "agent_execution_plan.json")
    executor_report = load_json_object(round_dir / "agent_executor_report.json")
    executor_attempts = rows_by_id(executor_report.get("attempts", []))
    rows: list[dict[str, Any]] = []
    for planned in object_rows(plan.get("attempts", [])):
        if not is_external_slot(planned):
            continue
        attempt_id = str(planned.get("attempt_id", ""))
        rows.append(
            sandbox_slot_row(
                round_dir=round_dir,
                repo_root=repo_root,
                planned=planned,
                executor_attempt=executor_attempts.get(attempt_id, {}),
            )
        )
    return rows


def sandbox_slot_row(
    *,
    round_dir: Path,
    repo_root: Path,
    planned: dict[str, Any],
    executor_attempt: dict[str, Any],
) -> dict[str, Any]:
    """Return one external-slot sandbox drill row."""
    attempt_id = str(planned.get("attempt_id", ""))
    runner = object_value(planned.get("runner", {}))
    workspace = object_value(planned.get("workspace", {}))
    input_contract = object_value(planned.get("input_contract", {}))
    output_contract = object_value(planned.get("output_contract", {}))
    planned_artifacts = object_value(planned.get("planned_artifacts", {}))
    proposal = proposal_payload(
        round_dir=round_dir,
        repo_root=repo_root,
        planned_artifacts=planned_artifacts,
        executor_attempt=executor_attempt,
    )
    workspace_manifest_path = first_existing_path(
        repo_root,
        [
            str(planned_artifacts.get("workspace_manifest", "")),
            str(round_dir / "workspace_manifests" / f"{attempt_id}.json"),
            str(round_dir / "agent_attempts" / attempt_id / "workspace_manifest.json"),
            str(round_dir / "workspace_manifest.json"),
        ],
    )
    workspace_manifest = (
        load_json_object(workspace_manifest_path) if workspace_manifest_path else {}
    )
    execution_path = first_existing_path(
        repo_root,
        [
            str(planned_artifacts.get("agent_execution", "")),
            str(round_dir / "agent_executions" / f"{attempt_id}.json"),
            str(round_dir / "agent_attempts" / attempt_id / "agent_execution.json"),
            str(round_dir / "agent_execution.json"),
        ],
    )
    execution = load_json_object(execution_path) if execution_path else {}
    command, command_source = command_for_slot(
        proposal=proposal,
        execution=execution,
    )
    execution_enabled = bool(runner.get("execution_enabled", False))
    dry_run_only = not execution_enabled
    execution_status = str(execution.get("status", ""))
    mutation_guard = object_value(execution.get("mutation_guard", {}))
    subprocess_executed = bool(execution.get("execution_enabled", False)) and (
        execution_status != "disabled"
    )
    requirements = {
        "workspace_required": bool(workspace.get("workspace_required", False)),
        "workspace_manifest_present": bool(workspace_manifest_path),
        "command_declared": bool(command),
        "round_agent_input_present": path_exists(
            repo_root,
            str(input_contract.get("round_agent_input", "")),
        ),
        "attempt_agent_input_present": path_exists(
            repo_root,
            str(input_contract.get("attempt_agent_input", "")),
        ),
        "input_bundle_present": path_exists(
            repo_root,
            str(input_contract.get("input_bundle_dir", "")),
        ),
        "execution_audit_required": execution_enabled,
        "execution_audit_present": bool(execution_path),
        "mutation_guard_declared": bool(
            workspace_manifest.get("mutation_policy", {})
        ),
        "mutation_guard_passed": (
            True if not execution else bool(mutation_guard.get("passed", False))
        ),
    }
    blockers = sandbox_blockers(
        execution_status=execution_status,
        requirements=requirements,
    )
    return {
        "slot_id": f"{round_dir.name}:{attempt_id}",
        "run_id": round_dir.parent.name,
        "round_id": round_dir.name,
        "attempt_id": attempt_id,
        "attempt_index": int(planned.get("attempt_index", 0)),
        "queue_role": str(planned.get("queue_role", "")),
        "profile_name": str(planned.get("profile_name", "")),
        "agent_role": str(planned.get("agent_role", "")),
        "adapter_name": str(planned.get("adapter_name", "")),
        "runner_name": str(runner.get("runner_name", "")),
        "external_slot": True,
        "execution_enabled": execution_enabled,
        "dry_run_only": dry_run_only,
        "subprocess_executed": subprocess_executed,
        "sandbox_status": "blocked" if blockers else "ready",
        "sandbox_ok": not blockers,
        "blocking_issues": blockers,
        "requirements": requirements,
        "command": {
            "source": command_source,
            "argv": command,
            "argc": len(command),
            "argv_sha256": sha256_json_list(command),
        },
        "workspace": {
            "expected_workspace_path": str(workspace.get("expected_workspace_path", "")),
            "manifest_path": str(workspace_manifest_path) if workspace_manifest_path else "",
            "manifest_sha256": sha256_file(workspace_manifest_path),
            "manifest_workspace_path": str(workspace_manifest.get("workspace_path", "")),
            "allowed_mutation_paths": string_list(
                object_value(workspace_manifest.get("mutation_policy", {})).get(
                    "allowed_paths",
                    [],
                )
            ),
        },
        "execution_audit": {
            "path": str(execution_path) if execution_path else "",
            "artifact_sha256": sha256_file(execution_path),
            "status": execution_status,
            "returncode": execution.get("returncode", None),
            "mutation_guard_passed": requirements["mutation_guard_passed"],
        },
        "io_paths": {
            "round_agent_input": resolve_text(
                repo_root,
                str(input_contract.get("round_agent_input", "")),
            ),
            "round_agent_input_sha256": sha256_file(
                existing_path(repo_root, str(input_contract.get("round_agent_input", "")))
            ),
            "attempt_agent_input": resolve_text(
                repo_root,
                str(input_contract.get("attempt_agent_input", "")),
            ),
            "attempt_agent_input_sha256": sha256_file(
                existing_path(repo_root, str(input_contract.get("attempt_agent_input", "")))
            ),
            "input_bundle": resolve_text(
                repo_root,
                str(input_contract.get("input_bundle_dir", "")),
            ),
            "input_bundle_sha256": sha256_tree(
                existing_path(repo_root, str(input_contract.get("input_bundle_dir", "")))
            ),
            "round_output_files": [
                resolve_text(repo_root, str(path))
                for path in string_list(output_contract.get("round_output_files", []))
            ],
            "round_output_file_records": [
                file_record(existing_path(repo_root, str(path)), repo_root, str(path))
                for path in string_list(output_contract.get("round_output_files", []))
            ],
        },
    }


def is_external_slot(planned: dict[str, Any]) -> bool:
    """Return whether a planned slot crosses an external/workspace boundary."""
    runner = object_value(planned.get("runner", {}))
    workspace = object_value(planned.get("workspace", {}))
    output_contract = object_value(planned.get("output_contract", {}))
    adapter_name = str(planned.get("adapter_name", ""))
    return (
        adapter_name in WORKSPACE_ADAPTERS
        or bool(workspace.get("workspace_required", False))
        or str(runner.get("isolation", "")) == "workspace"
        or bool(output_contract.get("file_contract_required", False))
        or bool(output_contract.get("stdout_patch_allowed", False))
    )


def sandbox_blockers(
    *,
    execution_status: str,
    requirements: dict[str, bool],
) -> list[str]:
    """Return stable blocker codes for one external slot."""
    blockers: list[str] = []
    required_true = (
        ("workspace_manifest_present", "workspace_manifest_missing"),
        ("command_declared", "command_missing"),
        ("round_agent_input_present", "round_agent_input_missing"),
        ("input_bundle_present", "input_bundle_missing"),
        ("mutation_guard_declared", "mutation_guard_missing"),
        ("mutation_guard_passed", "mutation_guard_failed"),
    )
    for key, code in required_true:
        if not requirements.get(key, False):
            blockers.append(code)
    if requirements.get("execution_audit_required", False):
        if not requirements.get("execution_audit_present", False):
            blockers.append("execution_audit_missing")
        elif execution_status not in {"completed", "disabled"}:
            blockers.append(f"execution_audit_{execution_status or 'unknown'}")
    return blockers


def command_for_slot(
    *,
    proposal: dict[str, Any],
    execution: dict[str, Any],
) -> tuple[list[str], str]:
    """Return the best available command and its source artifact."""
    execution_command = string_list(execution.get("command", []))
    if execution_command:
        return execution_command, "agent_execution"
    proposal_command = string_list(proposal.get("command", []))
    if proposal_command:
        return proposal_command, "proposal"
    return [], "missing"


def proposal_payload(
    *,
    round_dir: Path,
    repo_root: Path,
    planned_artifacts: dict[str, Any],
    executor_attempt: dict[str, Any],
) -> dict[str, Any]:
    """Return proposal metadata from executor report or attempt proposal."""
    proposal = object_value(executor_attempt.get("proposal", {}))
    if proposal:
        return proposal
    proposal_path = existing_path(repo_root, str(planned_artifacts.get("proposal", "")))
    if proposal_path is None:
        attempt_dir = existing_path(repo_root, str(planned_artifacts.get("attempt_dir", "")))
        proposal_path = attempt_dir / "proposal.json" if attempt_dir else None
    if proposal_path is None or not proposal_path.exists():
        return {}
    return load_json_object(proposal_path)


def round_dirs(run_dir: Path) -> list[Path]:
    """Return sorted round directories for one iteration run."""
    return [path for path in sorted(run_dir.glob("round_*")) if path.is_dir()]


def rows_by_id(value: object) -> dict[str, dict[str, Any]]:
    """Return object rows keyed by attempt id."""
    return {
        str(row.get("attempt_id", "")): row
        for row in object_rows(value)
        if str(row.get("attempt_id", ""))
    }


def object_rows(value: object) -> list[dict[str, Any]]:
    """Return JSON object rows from a list value."""
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def object_value(value: object) -> dict[str, Any]:
    """Return a JSON object or an empty object."""
    return value if isinstance(value, dict) else {}


def string_list(value: object) -> list[str]:
    """Return a deterministic list of strings."""
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list | tuple):
        return [str(item) for item in value if str(item)]
    return []


def sha256_json_list(values: list[str]) -> str:
    """Return a stable SHA-256 digest for a JSON string list."""
    if not values:
        return ""
    encoded = json.dumps(values, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def sha256_file(path: Path | None) -> str:
    """Return a stable SHA-256 digest for a file, or empty text when absent."""
    if path is None or not path.exists() or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_tree(path: Path | None) -> str:
    """Return a stable SHA-256 digest for a directory tree."""
    if path is None or not path.exists() or not path.is_dir():
        return ""
    digest = hashlib.sha256()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = child.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(child.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def file_record(path: Path | None, repo_root: Path, original: str) -> dict[str, Any]:
    """Return a deterministic file record for an optional path."""
    resolved = path
    if resolved is None and original:
        resolved = resolve_path(Path(original), repo_root)
    return {
        "path": str(resolved) if resolved else "",
        "exists": bool(resolved and resolved.exists() and resolved.is_file()),
        "sha256": sha256_file(resolved),
    }


def first_existing_path(repo_root: Path, values: list[str]) -> Path | None:
    """Return the first existing path from path text values."""
    for value in values:
        path = existing_path(repo_root, value)
        if path is not None:
            return path
    return None


def existing_path(repo_root: Path, value: str) -> Path | None:
    """Return a resolved path only when it exists."""
    if not value:
        return None
    path = resolve_path(Path(value), repo_root)
    return path if path.exists() else None


def path_exists(repo_root: Path, value: str) -> bool:
    """Return whether a path value exists."""
    return existing_path(repo_root, value) is not None


def resolve_text(repo_root: Path, value: str) -> str:
    """Return resolved path text for a possibly relative path."""
    if not value:
        return ""
    return str(resolve_path(Path(value), repo_root))


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root."""
    return path if path.is_absolute() else repo_root / path


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object, returning an empty object for missing or invalid files."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: object) -> None:
    """Write deterministic JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def external_agent_sandbox_drill_markdown(payload: dict[str, Any]) -> str:
    """Return a compact markdown sandbox drill report."""
    lines = [
        "# External Agent Sandbox Drill",
        "",
        f"- Schema: `{payload['schema_version']}`",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        f"- External slots: `{payload.get('totals', {}).get('external_slot_count', 0)}`",
        f"- Blocked: `{payload.get('totals', {}).get('blocked_count', 0)}`",
        "",
        "| Round | Attempt | Profile | Adapter | Runner | Status | Command | Command SHA-256 | Workspace SHA-256 | Execution SHA-256 | Input Bundle SHA-256 | Output Files | Output SHA-256 | Issues |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for slot in object_rows(payload.get("slots", [])):
        command = object_value(slot.get("command", {}))
        workspace = object_value(slot.get("workspace", {}))
        execution_audit = object_value(slot.get("execution_audit", {}))
        io_paths = object_value(slot.get("io_paths", {}))
        issues = slot.get("blocking_issues", [])
        lines.append(
            "| "
            + " | ".join(
                [
                    str(slot.get("round_id", "")),
                    str(slot.get("attempt_id", "")),
                    str(slot.get("profile_name", "")),
                    str(slot.get("adapter_name", "")),
                    str(slot.get("runner_name", "")),
                    str(slot.get("sandbox_status", "")),
                    str(command.get("source", "")),
                    str(command.get("argv_sha256", "")) or "none",
                    str(workspace.get("manifest_sha256", "")) or "none",
                    str(execution_audit.get("artifact_sha256", "")) or "none",
                    str(io_paths.get("input_bundle_sha256", "")) or "none",
                    output_record_status(io_paths.get("round_output_file_records", [])),
                    output_record_hashes(io_paths.get("round_output_file_records", [])),
                    ", ".join(str(item) for item in issues)
                    if isinstance(issues, list)
                    else "",
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def output_record_status(records: object) -> str:
    """Return compact output file presence text for markdown."""
    rows = object_rows(records)
    if not rows:
        return "none"
    values = []
    for record in rows:
        path = Path(str(record.get("path", "")))
        label = path.name if path.name else "output"
        status = "present" if record.get("exists", False) else "missing"
        values.append(f"{label}:{status}")
    return ", ".join(values)


def output_record_hashes(records: object) -> str:
    """Return compact output file hashes for markdown."""
    rows = object_rows(records)
    if not rows:
        return "none"
    values = [str(record.get("sha256", "")) or "missing" for record in rows]
    return ", ".join(values)


def main() -> None:
    """CLI entrypoint for external agent sandbox drill reports."""
    args = parse_args()
    payload = write_external_agent_sandbox_drill(
        run_dir=args.run_dir,
        repo_root=args.repo_root,
        output_path=args.output,
        markdown_path=args.markdown,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not bool(payload["ok"]):
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Inspect sandbox evidence for external agent slots.",
    )
    parser.add_argument("run_dir", type=Path, help="Path to experiments/<run_id>.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root used to resolve artifact paths.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for external_agent_sandbox_drill.json.",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=None,
        help="Optional path for external_agent_sandbox_drill.md.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
