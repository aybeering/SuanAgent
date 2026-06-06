"""Preflight a real Codex CLI executable without strategy modification."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from orchestrator.schema_validation import validate_json_file


CODEX_CLI_REAL_PREFLIGHT_SCHEMA_VERSION = "codex_cli_real_preflight_v1"
PREFLIGHT_TIMEOUT_SECONDS = 10
SCHEMA_PATH = Path("schemas/codex_cli_real_preflight.schema.json")


def build_codex_cli_real_preflight(
    *,
    run_dir: Path,
    config_path: Path,
    repo_root: Path = Path("."),
    timeout_seconds: int = PREFLIGHT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Return a deterministic preflight report for a real Codex CLI executable."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    config_path = resolve_path(config_path, repo_root)
    config = load_json_object(config_path)
    codex_cli = object_value(config.get("codex_cli", {}))
    executable = str(codex_cli.get("executable", ""))
    resolved_executable = resolve_executable(executable, repo_root)
    version_probe = probe_codex_version(
        executable_path=resolved_executable,
        timeout_seconds=timeout_seconds,
    )
    command_template = codex_command_template(codex_cli)
    checks = {
        "config_exists": config_path.exists() and config_path.is_file(),
        "strategy_modifier_is_codex_cli": str(config.get("strategy_modifier", ""))
        == "codex_cli",
        "execute_true_candidate": bool(codex_cli.get("execute", False)),
        "executable_declared": bool(executable),
        "executable_found": bool(resolved_executable),
        "executable_not_checked_in_canary": executable != "agents/codex_cli_canary.py",
        "sandbox_workspace_write": str(codex_cli.get("sandbox", ""))
        == "workspace-write",
        "workspace_root_declared": bool(str(codex_cli.get("workspace_root", ""))),
        "timeout_positive": int_value(codex_cli.get("timeout_seconds", 0)) > 0,
        "version_probe_completed": version_probe["status"] == "completed",
        "version_probe_returncode_zero": version_probe["returncode"] == 0,
        "command_template_has_exec": "exec" in command_template,
        "command_template_has_sandbox": "--sandbox" in command_template,
        "does_not_execute_strategy_modification": True,
    }
    blocking_reasons = readiness_blockers(checks)
    ready = not blocking_reasons
    ok = checks["config_exists"] and checks["does_not_execute_strategy_modification"]
    return {
        "schema_version": CODEX_CLI_REAL_PREFLIGHT_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "config_path": relative_path(config_path, repo_root),
        "ok": ok,
        "real_codex_cli_ready": ready,
        "blocking_reasons": blocking_reasons,
        "checks": checks,
        "config": {
            "strategy_modifier": str(config.get("strategy_modifier", "")),
            "codex_cli": {
                "executable": executable,
                "model": str(codex_cli.get("model", "")),
                "sandbox": str(codex_cli.get("sandbox", "")),
                "workspace_root": str(codex_cli.get("workspace_root", "")),
                "execute": bool(codex_cli.get("execute", False)),
                "timeout_seconds": int_value(codex_cli.get("timeout_seconds", 0)),
            },
        },
        "executable": {
            "declared": executable,
            "resolved_path": str(resolved_executable) if resolved_executable else "",
            "found": bool(resolved_executable),
            "is_checked_in_canary": executable == "agents/codex_cli_canary.py",
        },
        "version_probe": version_probe,
        "command_template": command_template,
        "artifacts": {
            "candidate_config": file_record(config_path, repo_root),
        },
        "policy": {
            "preflight_only": True,
            "does_not_execute_strategy_modification": True,
            "does_not_send_strategy_prompt": True,
            "does_not_create_agent_workspace": True,
            "does_not_modify_config": True,
            "does_not_select_candidate": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
            "version_probe_only": True,
            "deterministic_code_keeps_acceptance_authority": True,
        },
    }


def write_codex_cli_real_preflight(
    *,
    run_dir: Path,
    config_path: Path,
    repo_root: Path = Path("."),
    timeout_seconds: int = PREFLIGHT_TIMEOUT_SECONDS,
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    """Write JSON and markdown Codex CLI real preflight artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_codex_cli_real_preflight(
        run_dir=run_dir,
        config_path=config_path,
        repo_root=repo_root,
        timeout_seconds=timeout_seconds,
    )
    destination = output_path or run_dir / "codex_cli_real_preflight.json"
    write_json(destination, payload)
    markdown_destination = markdown_path or run_dir / "codex_cli_real_preflight.md"
    markdown_destination.write_text(
        codex_cli_real_preflight_markdown(payload),
        encoding="utf-8",
    )
    return payload


def validate_codex_cli_real_preflight_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
    schema_path: Path | None = None,
    require_current_evidence: bool = True,
) -> tuple[str, ...]:
    """Validate a saved real preflight against schema and current evidence."""
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
    config_path_value = str(payload.get("config_path", ""))
    if not run_dir_value:
        return schema_errors + ("codex_cli_real_preflight run_dir required",)
    if not config_path_value:
        return schema_errors + ("codex_cli_real_preflight config_path required",)
    timeout_seconds = int_value(
        object_value(payload.get("version_probe", {})).get(
            "timeout_seconds",
            PREFLIGHT_TIMEOUT_SECONDS,
        )
    )
    expected = build_codex_cli_real_preflight(
        run_dir=resolve_path(Path(run_dir_value), repo_root),
        config_path=resolve_path(Path(config_path_value), repo_root),
        repo_root=repo_root,
        timeout_seconds=timeout_seconds or PREFLIGHT_TIMEOUT_SECONDS,
    )
    if payload != expected:
        return schema_errors + ("codex_cli_real_preflight current evidence mismatch",)
    return schema_errors


def probe_codex_version(
    *,
    executable_path: Path | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run a local version probe for Codex CLI when an executable exists."""
    if executable_path is None:
        return {
            "status": "missing",
            "command": [],
            "timeout_seconds": timeout_seconds,
            "returncode": None,
            "timed_out": False,
            "stdout": stream_summary(""),
            "stderr": stream_summary(""),
        }
    command = [str(executable_path), "--version"]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = text_or_empty(exc.stderr)
        timeout_message = f"codex cli version probe timed out after {timeout_seconds} seconds"
        return {
            "status": "timeout",
            "command": command,
            "timeout_seconds": timeout_seconds,
            "returncode": None,
            "timed_out": True,
            "stdout": stream_summary(text_or_empty(exc.stdout)),
            "stderr": stream_summary(
                "\n".join(part for part in (stderr, timeout_message) if part)
            ),
        }
    return {
        "status": "completed" if result.returncode == 0 else "failed",
        "command": command,
        "timeout_seconds": timeout_seconds,
        "returncode": result.returncode,
        "timed_out": False,
        "stdout": stream_summary(result.stdout),
        "stderr": stream_summary(result.stderr),
    }


def resolve_executable(executable: str, repo_root: Path) -> Path | None:
    """Return the local executable path when it can be found."""
    if not executable:
        return None
    candidate = Path(executable)
    if candidate.is_absolute():
        return candidate if candidate.exists() and candidate.is_file() else None
    if "/" in executable:
        path = repo_root / candidate
        return path if path.exists() and path.is_file() else None
    found = shutil.which(executable)
    return Path(found) if found else None


def codex_command_template(codex_cli: dict[str, Any]) -> list[str]:
    """Return the strategy-modification command shape without executing it."""
    executable = str(codex_cli.get("executable", "codex"))
    model = str(codex_cli.get("model", "default"))
    sandbox = str(codex_cli.get("sandbox", "workspace-write"))
    return [
        executable,
        "exec",
        "--model",
        model,
        "--sandbox",
        sandbox,
        "--",
        "Modify only strategies/current_strategy.py and return a patch.",
    ]


def readiness_blockers(checks: dict[str, bool]) -> list[str]:
    """Return stable blocker codes for real Codex CLI readiness."""
    blockers: list[str] = []
    for key, code in (
        ("config_exists", "config_missing"),
        ("strategy_modifier_is_codex_cli", "strategy_modifier_not_codex_cli"),
        ("execute_true_candidate", "execute_not_true_candidate"),
        ("executable_declared", "executable_missing_from_config"),
        ("executable_found", "codex_executable_not_found"),
        ("executable_not_checked_in_canary", "executable_is_checked_in_canary"),
        ("sandbox_workspace_write", "sandbox_not_workspace_write"),
        ("workspace_root_declared", "workspace_root_missing"),
        ("timeout_positive", "timeout_not_positive"),
        ("version_probe_completed", "version_probe_not_completed"),
        ("version_probe_returncode_zero", "version_probe_returncode_not_zero"),
        ("command_template_has_exec", "command_template_missing_exec"),
        ("command_template_has_sandbox", "command_template_missing_sandbox"),
    ):
        if not checks.get(key, False):
            blockers.append(code)
    return blockers


def codex_cli_real_preflight_markdown(payload: dict[str, Any]) -> str:
    """Return compact markdown for the real Codex CLI preflight."""
    blockers = string_list(payload.get("blocking_reasons", []))
    executable = object_value(payload.get("executable", {}))
    version_probe = object_value(payload.get("version_probe", {}))
    lines = [
        "# Codex CLI Real Preflight",
        "",
        f"- Schema: `{payload.get('schema_version', '')}`",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Report OK: `{payload.get('ok', False)}`",
        f"- Real Codex CLI ready: `{payload.get('real_codex_cli_ready', False)}`",
        f"- Executable: `{executable.get('declared', '')}`",
        f"- Resolved path: `{executable.get('resolved_path', '')}`",
        f"- Version probe: `{version_probe.get('status', '')}`",
        "",
        "## Blocking Reasons",
    ]
    lines.extend(f"- {reason}" for reason in blockers)
    if not blockers:
        lines.append("- none")
    lines.extend(
        [
            "",
            "This preflight only probes the local executable version; it does not send a strategy prompt or modify files.",
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


def stream_summary(text: str) -> dict[str, object]:
    """Return a compact deterministic summary for command output text."""
    return {
        "chars": len(text),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else "",
        "preview": text[:500],
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
    """CLI entrypoint for real Codex CLI preflight."""
    args = parse_args()
    payload = write_codex_cli_real_preflight(
        run_dir=args.run_dir,
        config_path=args.config,
        repo_root=args.repo_root,
        timeout_seconds=args.timeout_seconds,
        output_path=args.output,
        markdown_path=args.markdown_output,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for real Codex CLI preflight."""
    parser = argparse.ArgumentParser(
        description="Probe real Codex CLI availability without strategy modification.",
    )
    parser.add_argument("run_dir", type=Path, help="Path to an iteration run directory.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/codex_cli_enable_candidate.json"),
        help="Candidate config that declares a real Codex CLI executable.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root used to resolve paths.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=PREFLIGHT_TIMEOUT_SECONDS,
        help="Timeout for the local version probe.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_real_preflight.json.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_real_preflight.md.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
