"""Guarded execution receipt for approved read-only operator action commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from orchestrator.operator_action_approval import (
    OPERATOR_ACTION_APPROVAL_SCHEMA_VERSION,
)
from orchestrator.schema_validation import validate_json_file


OPERATOR_ACTION_EXECUTION_RECEIPT_SCHEMA_VERSION = (
    "operator_action_execution_receipt_v1"
)
SCHEMA_PATH = Path("schemas/operator_action_execution_receipt.schema.json")
DEFAULT_TIMEOUT_SECONDS = 20
ALLOWED_EXPERIMENTS_SUBCOMMANDS = {
    "action-approval",
    "action-plan",
    "candidates",
    "quality-trace",
    "review",
    "show",
}


def execute_operator_action_with_approval(
    *,
    run_id: str,
    approval_path: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """Execute one approved read-only action command and write a receipt."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    approval_path = resolve_path(approval_path, repo_root)
    run_dir = experiments_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    approval = load_json_object(approval_path)
    checks = execution_evidence_checks(
        run_id=run_id,
        approval_path=approval_path,
        approval=approval,
        repo_root=repo_root,
    )
    command = str(object_field(approval, "selected_command").get("command", ""))
    git_before = git_status_record(repo_root)
    execution = blocked_execution_record(
        command=command,
        timeout_seconds=timeout_seconds,
        blockers=string_list(checks.get("blockers", [])),
    )
    git_after = git_before
    if checks["ok"]:
        execution = run_approved_command(
            command=command,
            repo_root=repo_root,
            timeout_seconds=timeout_seconds,
        )
        git_after = git_status_record(repo_root)
    mutation_guard = mutation_guard_record(before=git_before, after=git_after)
    status = receipt_status(
        checks_ok=bool(checks.get("ok", False)),
        execution=execution,
        mutation_guard=mutation_guard,
    )
    payload = build_receipt_payload(
        run_id=run_id,
        run_dir=run_dir,
        repo_root=repo_root,
        approval_path=approval_path,
        approval=approval,
        checks=checks,
        execution=execution,
        mutation_guard=mutation_guard,
        status=status,
    )
    write_receipt(run_dir=run_dir, payload=payload, repo_root=repo_root)
    return payload


def execution_evidence_checks(
    *,
    run_id: str,
    approval_path: Path,
    approval: dict[str, Any],
    repo_root: Path,
) -> dict[str, object]:
    """Return deterministic blockers for guarded operator action execution."""
    blockers: list[str] = []
    approval_errors = (
        validate_json_file(
            payload_path=approval_path,
            schema_path=repo_root / "schemas/operator_action_approval.schema.json",
        )
        if approval_path.exists() and approval_path.is_file()
        else ("missing_approval_file",)
    )
    if approval_errors:
        blockers.append("approval_schema_invalid")
    if approval.get("schema_version") != OPERATOR_ACTION_APPROVAL_SCHEMA_VERSION:
        blockers.append("approval_schema_version_invalid")
    if approval.get("ok") is not True:
        blockers.append("approval_not_ok")
    if approval.get("status") != "approval_recorded":
        blockers.append("approval_not_recorded")
    if str(approval.get("run_id", "")) != run_id:
        blockers.append("approval_run_id_mismatch")

    intent = object_field(approval, "operator_intent")
    if intent.get("approval_recorded") is not True:
        blockers.append("operator_approval_not_recorded")
    if intent.get("explicit_approval") is not True:
        blockers.append("explicit_approval_missing")
    if intent.get("confirmation_phrase_matches") is not True:
        blockers.append("confirmation_phrase_mismatch")

    command = object_field(approval, "selected_command")
    command_text = str(command.get("command", ""))
    command_sha = str(command.get("command_sha256", ""))
    if not command_text:
        blockers.append("selected_command_missing")
    if command_sha != sha256_text(command_text):
        blockers.append("selected_command_digest_mismatch")
    if command.get("command_sha256_matches") is not True:
        blockers.append("approval_command_digest_mismatch")
    if command.get("executed_by_approval") is not False:
        blockers.append("approval_already_executed_command")
    if command.get("requires_explicit_operator_invocation") is not True:
        blockers.append("command_missing_explicit_invocation_flag")
    if command.get("writes_repository") is True:
        blockers.append("command_writes_repository")
    if command.get("promotes_champion") is True:
        blockers.append("command_promotes_champion")
    if command.get("runs_backtests") is True:
        blockers.append("command_runs_backtests")

    argv = parse_command(command_text)
    if not argv:
        blockers.append("command_parse_failed")
    elif not command_is_allowlisted(argv):
        blockers.append("command_not_allowlisted")

    source = object_field(approval, "source_action_plan")
    source_file = object_field(source, "file")
    plan_path = resolve_path(Path(str(source_file.get("path", ""))), repo_root)
    if str(source_file.get("sha256", "")) != file_sha256(plan_path):
        blockers.append("source_action_plan_digest_mismatch")
    if plan_path.name != "operator_action_plan.json":
        blockers.append("source_action_plan_path_invalid")

    return {
        "ok": not blockers,
        "blockers": unique_strings(blockers),
        "approval_schema_errors": list(approval_errors),
        "selected_command_sha256": command_sha,
        "computed_command_sha256": sha256_text(command_text),
        "source_action_plan_path": str(plan_path),
        "source_action_plan_sha256": file_sha256(plan_path),
        "allowed_experiments_subcommands": sorted(ALLOWED_EXPERIMENTS_SUBCOMMANDS),
    }


def command_is_allowlisted(argv: list[str]) -> bool:
    """Return whether argv is one of the narrow read-only inspection commands."""
    if len(argv) >= 3 and argv[0] == "python" and argv[1] == "-m":
        module = argv[2]
        if module == "orchestrator.artifact_validator":
            return True
        if module == "orchestrator.experiments" and len(argv) >= 4:
            return argv[3] in ALLOWED_EXPERIMENTS_SUBCOMMANDS
    return False


def run_approved_command(
    *,
    command: str,
    repo_root: Path,
    timeout_seconds: int,
) -> dict[str, object]:
    """Run the approved command without a shell and return output hashes."""
    argv = parse_command(command)
    started = time.monotonic()
    try:
        result = subprocess.run(
            argv,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout = normalize_process_text(exc.stdout)
        stderr = normalize_process_text(exc.stderr)
        return {
            "executed": True,
            "status": "timeout",
            "returncode": None,
            "duration_ms": duration_ms,
            "timeout_seconds": timeout_seconds,
            "command": command,
            "argv": argv,
            "stdout": output_record(stdout),
            "stderr": output_record(stderr),
        }
    duration_ms = int((time.monotonic() - started) * 1000)
    status = "completed" if result.returncode == 0 else "command_failed"
    return {
        "executed": True,
        "status": status,
        "returncode": result.returncode,
        "duration_ms": duration_ms,
        "timeout_seconds": timeout_seconds,
        "command": command,
        "argv": argv,
        "stdout": output_record(result.stdout),
        "stderr": output_record(result.stderr),
    }


def blocked_execution_record(
    *,
    command: str,
    timeout_seconds: int,
    blockers: list[str],
) -> dict[str, object]:
    """Return an execution record for blocked commands."""
    return {
        "executed": False,
        "status": "blocked",
        "returncode": None,
        "duration_ms": 0,
        "timeout_seconds": timeout_seconds,
        "command": command,
        "argv": parse_command(command),
        "stdout": output_record(""),
        "stderr": output_record("; ".join(blockers)),
    }


def receipt_status(
    *,
    checks_ok: bool,
    execution: dict[str, object],
    mutation_guard: dict[str, object],
) -> str:
    """Return compact receipt status."""
    if not checks_ok:
        return "blocked"
    if execution.get("status") == "timeout":
        return "timeout"
    if execution.get("status") == "command_failed":
        return "command_failed"
    if mutation_guard.get("ok") is not True:
        return "workspace_violation"
    return "completed"


def build_receipt_payload(
    *,
    run_id: str,
    run_dir: Path,
    repo_root: Path,
    approval_path: Path,
    approval: dict[str, Any],
    checks: dict[str, object],
    execution: dict[str, object],
    mutation_guard: dict[str, object],
    status: str,
) -> dict[str, object]:
    """Build the saved operator action execution receipt payload."""
    return {
        "schema_version": OPERATOR_ACTION_EXECUTION_RECEIPT_SCHEMA_VERSION,
        "run_id": run_id,
        "run_dir": relative_path(run_dir, repo_root),
        "status": status,
        "ok": status == "completed",
        "executed": bool(execution.get("executed", False)),
        "source_approval": {
            "artifact_name": "operator_action_approval",
            "file": file_record(approval_path, repo_root),
            "approval_status": str(approval.get("status", "")),
            "approval_recorded": bool(
                object_field(approval, "operator_intent").get(
                    "approval_recorded",
                    False,
                )
            ),
        },
        "selected_action": object_field(approval, "selected_action"),
        "selected_command": object_field(approval, "selected_command"),
        "evidence_checks": {
            "ok": bool(checks.get("ok", False)),
            "blockers": string_list(checks.get("blockers", [])),
            "approval_schema_errors": string_list(
                checks.get("approval_schema_errors", [])
            ),
            "selected_command_sha256": str(
                checks.get("selected_command_sha256", "")
            ),
            "computed_command_sha256": str(
                checks.get("computed_command_sha256", "")
            ),
            "source_action_plan_path": str(
                checks.get("source_action_plan_path", "")
            ),
            "source_action_plan_sha256": str(
                checks.get("source_action_plan_sha256", "")
            ),
            "allowed_experiments_subcommands": string_list(
                checks.get("allowed_experiments_subcommands", [])
            ),
        },
        "command_execution": execution,
        "mutation_guard": mutation_guard,
        "policy": {
            "requires_operator_action_approval": True,
            "requires_approval_recorded": True,
            "requires_command_digest_match": True,
            "requires_source_action_plan_digest_match": True,
            "executes_only_allowlisted_read_only_commands": True,
            "blocks_repository_writing_commands": True,
            "blocks_champion_promotion_commands": True,
            "blocks_backtest_commands": True,
            "records_stdout_stderr_hashes": True,
            "checks_tracked_workspace_mutation": True,
            "does_not_execute_agents": True,
            "does_not_write_config": True,
            "does_not_promote_champion": True,
            "does_not_apply_patches": True,
            "does_not_route_agents": True,
            "does_not_change_acceptance": True,
        },
    }


def write_receipt(
    *,
    run_dir: Path,
    payload: dict[str, object],
    repo_root: Path,
) -> tuple[Path, Path]:
    """Write machine-readable and markdown operator action execution receipts."""
    json_path = run_dir / "operator_action_execution_receipt.json"
    md_path = run_dir / "operator_action_execution_receipt.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_receipt_markdown(payload), encoding="utf-8")
    errors = validate_operator_action_execution_receipt_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(
            "operator action execution receipt failed schema validation: "
            + "; ".join(errors)
        )
    return json_path, md_path


def render_receipt_markdown(payload: dict[str, object]) -> str:
    """Render an operator action execution receipt as markdown."""
    checks = object_field(payload, "evidence_checks")
    execution = object_field(payload, "command_execution")
    command = object_field(payload, "selected_command")
    mutation = object_field(payload, "mutation_guard")
    lines = [
        "# Operator Action Execution Receipt",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- Executed: `{payload.get('executed', False)}`",
        f"- Evidence OK: `{checks.get('ok', False)}`",
        f"- Command label: `{command.get('label', '')}`",
        f"- Return code: `{execution.get('returncode', None)}`",
        f"- Workspace unchanged: `{mutation.get('tracked_status_unchanged', False)}`",
        "",
        "## Command",
        "",
        "```bash",
        str(command.get("command", "")),
        "```",
        "",
        "## Output Hashes",
        "",
        f"- stdout SHA-256: `{object_field(execution, 'stdout').get('sha256', '')}`",
        f"- stderr SHA-256: `{object_field(execution, 'stderr').get('sha256', '')}`",
        "",
        "## Blockers",
        "",
    ]
    blockers = string_list(checks.get("blockers", []))
    lines.extend([f"- `{blocker}`" for blocker in blockers] or ["- none"])
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This receipt executes only approval-backed, allowlisted read-only inspection commands.",
            "- It blocks commands that write the repository, promote champions, run backtests, execute agents, apply patches, route agents, or change acceptance.",
            "- It records stdout/stderr hashes and checks tracked workspace mutation before writing this receipt.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_operator_action_execution_receipt_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved operator action execution receipt."""
    return tuple(
        validate_json_file(
            payload_path=payload_path,
            schema_path=repo_root / SCHEMA_PATH,
        )
    )


def mutation_guard_record(
    *,
    before: dict[str, object],
    after: dict[str, object],
) -> dict[str, object]:
    """Return tracked workspace mutation check results."""
    before_status = string_list(before.get("status_lines", []))
    after_status = string_list(after.get("status_lines", []))
    unchanged = before.get("available") is True and before_status == after_status
    return {
        "available": bool(before.get("available", False) and after.get("available", False)),
        "tracked_status_before": before_status,
        "tracked_status_after": after_status,
        "tracked_status_unchanged": unchanged,
        "ok": unchanged,
    }


def git_status_record(repo_root: Path) -> dict[str, object]:
    """Return compact git status evidence."""
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {
            "available": False,
            "status_lines": [],
            "returncode": result.returncode,
            "stderr_sha256": sha256_text(result.stderr),
        }
    return {
        "available": True,
        "status_lines": [
            line for line in result.stdout.splitlines() if not ignored_status_line(line)
        ],
        "returncode": result.returncode,
        "stderr_sha256": sha256_text(result.stderr),
    }


def ignored_status_line(line: str) -> bool:
    """Return whether a git status line is irrelevant to tracked mutation guard."""
    return line.strip().startswith("?? experiments/")


def output_record(value: str) -> dict[str, object]:
    """Return deterministic output metadata with a short inspectable excerpt."""
    return {
        "sha256": sha256_text(value),
        "byte_count": len(value.encode("utf-8")),
        "line_count": len(value.splitlines()),
        "excerpt": value[:2000],
    }


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


def sha256_text(value: str) -> str:
    """Return SHA-256 for text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_command(command: str) -> list[str]:
    """Parse a command string without enabling shell features."""
    try:
        return shlex.split(command)
    except ValueError:
        return []


def normalize_process_text(value: object) -> str:
    """Return subprocess output as text."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


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
    """CLI entrypoint for guarded operator action execution."""
    parser = argparse.ArgumentParser(
        description="Execute one approved read-only operator action command."
    )
    parser.add_argument("run_id")
    parser.add_argument("--approval-path", type=Path, required=True)
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args()
    payload = execute_operator_action_with_approval(
        run_id=args.run_id,
        approval_path=args.approval_path,
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
