"""Guard a harmless Codex CLI dry invocation before strategy execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from orchestrator.agent_contract_runner import (
    AgentCommandResult,
    AgentContractRunResult,
    CODEX_CLI_GUARDED_RUNNER_NAME,
    write_agent_execution,
)
from orchestrator.codex_cli_real_preflight import resolve_executable
from orchestrator.workspace_manager import (
    create_isolated_workspace,
    workspace_mutation_errors,
    workspace_snapshot,
)


CODEX_CLI_DRY_INVOCATION_GUARD_SCHEMA_VERSION = "codex_cli_dry_invocation_guard_v1"
DRY_INVOCATION_PROMPT = (
    "Return exactly SUANAGENT_DRY_INVOCATION_OK. "
    "Do not inspect files. Do not modify files."
)
DRY_INVOCATION_EXPECTED_TEXT = "SUANAGENT_DRY_INVOCATION_OK"
DRY_INVOCATION_ROUND_ID = "codex_cli_dry_invocation"
DRY_INVOCATION_ATTEMPT_ID = "attempt_001_dry_invocation"


def build_codex_cli_dry_invocation_guard(
    *,
    run_dir: Path,
    config_path: Path,
    repo_root: Path = Path("."),
    execute: bool = False,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Return a dry-invocation guard report and write its execution audit."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    run_dir.mkdir(parents=True, exist_ok=True)
    config_path = resolve_path(config_path, repo_root)
    config = load_json_object(config_path)
    codex_cli = object_value(config.get("codex_cli", {}))
    executable = str(codex_cli.get("executable", ""))
    resolved_executable = resolve_executable(executable, repo_root)
    command = dry_invocation_command(
        executable=str(resolved_executable or executable),
        model=str(codex_cli.get("model", "default")),
        sandbox=str(codex_cli.get("sandbox", "workspace-write")),
    )
    prompt_path = run_dir / "codex_cli_dry_invocation_prompt.txt"
    prompt_path.write_text(DRY_INVOCATION_PROMPT + "\n", encoding="utf-8")
    workspace_path = create_dry_invocation_workspace(
        repo_root=repo_root,
        codex_cli=codex_cli,
        run_id=run_dir.name,
    )
    audit_path = run_dir / "codex_cli_dry_invocation_execution.json"
    result_payload = run_or_skip_dry_invocation(
        audit_path=audit_path,
        command=command,
        prompt=DRY_INVOCATION_PROMPT,
        workspace_path=workspace_path,
        prompt_path=prompt_path,
        timeout_seconds=timeout_seconds,
        execute=execute,
    )
    execution = load_json_object(audit_path)
    stdout_preview = str(object_value(execution.get("stdout", {})).get("preview", ""))
    raw_preview = str(object_value(execution.get("raw_response", {})).get("preview", ""))
    output_text = stdout_preview + "\n" + raw_preview
    checks = {
        "config_exists": config_path.exists() and config_path.is_file(),
        "strategy_modifier_is_codex_cli": str(config.get("strategy_modifier", ""))
        == "codex_cli",
        "executable_declared": bool(executable),
        "executable_found": bool(resolved_executable),
        "execute_requested": bool(execute),
        "prompt_is_harmless": prompt_is_harmless(DRY_INVOCATION_PROMPT),
        "command_is_harmless": command_is_harmless(command),
        "sandbox_workspace_write": str(codex_cli.get("sandbox", ""))
        == "workspace-write",
        "workspace_created": workspace_path.exists(),
        "execution_audit_present": audit_path.exists(),
        "execution_completed": str(execution.get("status", "")) == "completed",
        "returncode_zero": execution.get("returncode") == 0,
        "stdout_contains_expected_text": DRY_INVOCATION_EXPECTED_TEXT in output_text,
        "mutation_guard_passed": bool(
            object_value(execution.get("mutation_guard", {})).get("passed", False)
        ),
        "no_allowed_mutation_paths": execution.get("allowed_mutation_paths", []) == [],
        "does_not_apply_patches": True,
        "does_not_change_acceptance": True,
    }
    blocking_reasons = dry_invocation_blockers(checks)
    if not execute and "execution_disabled" not in blocking_reasons:
        blocking_reasons.append("execution_disabled")
    ready = bool(execute) and not blocking_reasons
    return {
        "schema_version": CODEX_CLI_DRY_INVOCATION_GUARD_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "config_path": relative_path(config_path, repo_root),
        "ok": True,
        "dry_invocation_ready": ready,
        "execution_requested": bool(execute),
        "blocking_reasons": blocking_reasons,
        "checks": checks,
        "config": {
            "strategy_modifier": str(config.get("strategy_modifier", "")),
            "codex_cli": {
                "executable": executable,
                "resolved_executable": str(resolved_executable or ""),
                "model": str(codex_cli.get("model", "")),
                "sandbox": str(codex_cli.get("sandbox", "")),
                "workspace_root": str(codex_cli.get("workspace_root", "")),
                "execute": bool(codex_cli.get("execute", False)),
                "timeout_seconds": int_value(codex_cli.get("timeout_seconds", 0)),
            },
        },
        "dry_invocation": {
            "prompt_sha256": sha256_text(DRY_INVOCATION_PROMPT),
            "expected_text": DRY_INVOCATION_EXPECTED_TEXT,
            "command": command,
            "timeout_seconds": timeout_seconds,
            "result": result_payload,
        },
        "artifacts": {
            "candidate_config": file_record(config_path, repo_root),
            "prompt": file_record(prompt_path, repo_root),
            "execution_audit": file_record(audit_path, repo_root),
            "workspace": {
                "exists": workspace_path.exists(),
                "path": relative_path(workspace_path, repo_root),
            },
        },
        "policy": {
            "guard_only": True,
            "harmless_prompt_only": True,
            "does_not_reference_strategy_file": True,
            "does_not_apply_patches": True,
            "does_not_select_candidate": True,
            "does_not_change_acceptance": True,
            "requires_empty_mutation_allowlist": True,
            "requires_workspace_mutation_guard": True,
            "deterministic_code_keeps_acceptance_authority": True,
        },
    }


def write_codex_cli_dry_invocation_guard(
    *,
    run_dir: Path,
    config_path: Path,
    repo_root: Path = Path("."),
    execute: bool = False,
    timeout_seconds: int = 30,
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    """Write JSON and markdown dry-invocation guard artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_codex_cli_dry_invocation_guard(
        run_dir=run_dir,
        config_path=config_path,
        repo_root=repo_root,
        execute=execute,
        timeout_seconds=timeout_seconds,
    )
    destination = output_path or run_dir / "codex_cli_dry_invocation_guard.json"
    write_json(destination, payload)
    markdown_destination = markdown_path or run_dir / "codex_cli_dry_invocation_guard.md"
    markdown_destination.write_text(
        codex_cli_dry_invocation_guard_markdown(payload),
        encoding="utf-8",
    )
    return payload


def create_dry_invocation_workspace(
    *,
    repo_root: Path,
    codex_cli: dict[str, Any],
    run_id: str,
) -> Path:
    """Create an isolated workspace for the harmless dry invocation."""
    workspace_root = repo_root / str(codex_cli.get("workspace_root", "workspaces"))
    try:
        return create_isolated_workspace(
            repo_root=repo_root,
            workspace_root=workspace_root,
            run_id=run_id,
            round_id=DRY_INVOCATION_ROUND_ID,
            attempt_id=DRY_INVOCATION_ATTEMPT_ID,
            profile_name="real_codex_dry_invocation",
        )
    except FileExistsError:
        return (
            workspace_root
            / run_id
            / DRY_INVOCATION_ROUND_ID
            / "real_codex_dry_invocation"
            / DRY_INVOCATION_ATTEMPT_ID
            / "strategy_workspace"
        )


def run_or_skip_dry_invocation(
    *,
    audit_path: Path,
    command: list[str],
    prompt: str,
    workspace_path: Path,
    prompt_path: Path,
    timeout_seconds: int,
    execute: bool,
) -> dict[str, Any]:
    """Execute or record a skipped harmless dry invocation."""
    workspace_output_path = workspace_path / "codex_cli_dry_invocation_output.txt"
    round_output_path = audit_path.with_name("codex_cli_dry_invocation_output.txt")
    if not execute:
        write_dry_invocation_audit(
            audit_path=audit_path,
            command=command,
            prompt=prompt,
            workspace_path=workspace_path,
            prompt_path=prompt_path,
            workspace_output_path=workspace_output_path,
            round_output_path=round_output_path,
            timeout_seconds=timeout_seconds,
            execution_enabled=False,
            raw_response="codex cli dry invocation disabled",
            status="disabled",
        )
        return {"status": "disabled", "returncode": None, "timed_out": False}

    before = workspace_snapshot(workspace_path)
    result = run_command_with_stdin(
        command=command,
        prompt=prompt,
        cwd=workspace_path,
        timeout_seconds=timeout_seconds,
    )
    raw_response = result.stdout
    if result.stderr:
        raw_response = raw_response + "\n[stderr]\n" + result.stderr
    mutation_errors = workspace_mutation_errors(
        before=before,
        after=workspace_snapshot(workspace_path),
        allowed_paths=set(),
    )
    status = execution_status(result=result, mutation_errors=mutation_errors)
    write_dry_invocation_audit(
        audit_path=audit_path,
        command=command,
        prompt=prompt,
        workspace_path=workspace_path,
        prompt_path=prompt_path,
        workspace_output_path=workspace_output_path,
        round_output_path=round_output_path,
        timeout_seconds=timeout_seconds,
        execution_enabled=True,
        raw_response=raw_response,
        status=status,
        result=result,
        mutation_errors=mutation_errors,
    )
    return {
        "status": status,
        "returncode": result.returncode,
        "timed_out": result.timed_out,
    }


def write_dry_invocation_audit(
    *,
    audit_path: Path,
    command: list[str],
    prompt: str,
    workspace_path: Path,
    prompt_path: Path,
    workspace_output_path: Path,
    round_output_path: Path,
    timeout_seconds: int,
    execution_enabled: bool,
    raw_response: str,
    status: str,
    result: AgentCommandResult | None = None,
    mutation_errors: tuple[str, ...] = (),
) -> None:
    """Write a unified execution audit for the dry invocation."""
    write_agent_execution(
        output_path=audit_path,
        agent_name="codex_cli",
        profile_name="real_codex_dry_invocation",
        adapter_name="codex_cli_dry_invocation",
        runner_name=CODEX_CLI_GUARDED_RUNNER_NAME,
        stdin_text=prompt,
        contract_result=AgentContractRunResult(
            status=status,
            execution_enabled=execution_enabled,
            command=tuple(command),
            cwd=workspace_path,
            workspace_path=workspace_path,
            agent_input_path=prompt_path,
            workspace_output_path=workspace_output_path,
            round_output_path=round_output_path,
            timeout_seconds=timeout_seconds,
            raw_response=raw_response,
            mutation_errors=mutation_errors,
            allowed_mutation_paths=(),
            result=result,
        ),
    )


def run_command_with_stdin(
    *,
    command: list[str],
    prompt: str,
    cwd: Path,
    timeout_seconds: int,
) -> AgentCommandResult:
    """Run a command with prompt on stdin."""
    try:
        result = subprocess.run(
            command,
            input=prompt,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = text_or_empty(exc.stderr)
        timeout_message = f"codex cli dry invocation timed out after {timeout_seconds} seconds"
        return AgentCommandResult(
            returncode=None,
            stdout=text_or_empty(exc.stdout),
            stderr="\n".join(part for part in (stderr, timeout_message) if part),
            timed_out=True,
        )
    return AgentCommandResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def execution_status(
    *,
    result: AgentCommandResult,
    mutation_errors: tuple[str, ...],
) -> str:
    """Return normalized execution status."""
    if result.timed_out:
        return "timeout"
    if result.returncode != 0:
        return "command_failed"
    if mutation_errors:
        return "workspace_violation"
    return "completed"


def dry_invocation_command(*, executable: str, model: str, sandbox: str) -> list[str]:
    """Return a harmless Codex CLI dry invocation command."""
    return [
        executable,
        "exec",
        "--model",
        model,
        "--sandbox",
        sandbox,
        "--",
        DRY_INVOCATION_PROMPT,
    ]


def prompt_is_harmless(prompt: str) -> bool:
    """Return whether the prompt excludes strategy and file-modification language."""
    forbidden = ("current_strategy.py", "strategies/", "patch", "modify only")
    return bool(prompt) and not any(token in prompt for token in forbidden)


def command_is_harmless(command: list[str]) -> bool:
    """Return whether command args exclude strategy targets."""
    command_text = " ".join(command)
    return prompt_is_harmless(command_text)


def dry_invocation_blockers(checks: dict[str, bool]) -> list[str]:
    """Return stable blocker codes for dry invocation readiness."""
    blockers: list[str] = []
    for key, code in (
        ("config_exists", "config_missing"),
        ("strategy_modifier_is_codex_cli", "strategy_modifier_not_codex_cli"),
        ("executable_declared", "executable_missing_from_config"),
        ("executable_found", "codex_executable_not_found"),
        ("prompt_is_harmless", "prompt_not_harmless"),
        ("command_is_harmless", "command_not_harmless"),
        ("sandbox_workspace_write", "sandbox_not_workspace_write"),
        ("workspace_created", "workspace_missing"),
        ("execution_audit_present", "execution_audit_missing"),
        ("execution_completed", "execution_not_completed"),
        ("returncode_zero", "returncode_not_zero"),
        ("stdout_contains_expected_text", "expected_output_missing"),
        ("mutation_guard_passed", "mutation_guard_failed"),
        ("no_allowed_mutation_paths", "allowed_mutation_paths_not_empty"),
        ("does_not_apply_patches", "patch_application_not_disabled"),
        ("does_not_change_acceptance", "acceptance_change_not_disabled"),
    ):
        if not checks.get(key, False):
            blockers.append(code)
    return blockers


def codex_cli_dry_invocation_guard_markdown(payload: dict[str, Any]) -> str:
    """Return compact markdown for the dry-invocation guard."""
    blockers = string_list(payload.get("blocking_reasons", []))
    lines = [
        "# Codex CLI Dry Invocation Guard",
        "",
        f"- Schema: `{payload.get('schema_version', '')}`",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Execution requested: `{payload.get('execution_requested', False)}`",
        f"- Dry invocation ready: `{payload.get('dry_invocation_ready', False)}`",
        f"- Config: `{payload.get('config_path', '')}`",
        "",
        "## Blocking Reasons",
    ]
    lines.extend(f"- {reason}" for reason in blockers)
    if not blockers:
        lines.append("- none")
    lines.extend(
        [
            "",
            "This guard uses a harmless prompt and an empty mutation allowlist; it does not apply patches or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object, returning an empty object when missing."""
    if not path.exists() or not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def file_record(path: Path, repo_root: Path) -> dict[str, object]:
    """Return deterministic metadata for a file artifact."""
    if not path.exists() or not path.is_file():
        return {
            "exists": False,
            "path": relative_path(path, repo_root),
            "bytes": 0,
            "sha256": "",
        }
    data = path.read_bytes()
    return {
        "exists": True,
        "path": relative_path(path, repo_root),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def write_json(path: Path, payload: object) -> None:
    """Write deterministic JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def object_value(value: object) -> dict[str, Any]:
    """Return a dict value or an empty dict."""
    return value if isinstance(value, dict) else {}


def string_list(value: object) -> list[str]:
    """Return non-empty strings from a JSON value."""
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, list | tuple):
        return []
    return [str(item) for item in value if str(item)]


def int_value(value: object) -> int:
    """Return an integer value or zero."""
    return value if isinstance(value, int) else 0


def sha256_text(value: str) -> str:
    """Return the SHA-256 hash for text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def text_or_empty(value: str | bytes | None) -> str:
    """Return subprocess output as text."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root when needed."""
    return path if path.is_absolute() else repo_root / path


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> None:
    """CLI entrypoint for Codex CLI dry invocation guard."""
    args = parse_args()
    payload = write_codex_cli_dry_invocation_guard(
        run_dir=args.run_dir,
        config_path=args.config,
        repo_root=args.repo_root,
        execute=args.execute,
        timeout_seconds=args.timeout_seconds,
        output_path=args.output,
        markdown_path=args.markdown_output,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for Codex CLI dry invocation guard."""
    parser = argparse.ArgumentParser(
        description="Guard a harmless Codex CLI dry invocation.",
    )
    parser.add_argument("run_dir", type=Path, help="Path to a run directory.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/codex_cli_enable_candidate.json"),
        help="Candidate config that declares a Codex CLI executable.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root used to resolve paths.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually run the harmless dry invocation subprocess.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Timeout for the harmless dry invocation.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_dry_invocation_guard.json.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_dry_invocation_guard.md.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
