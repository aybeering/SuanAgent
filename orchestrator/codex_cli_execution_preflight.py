"""Gate real Codex CLI execution before an iteration loop can start."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from agents.codex_dry_run_adapter import build_codex_command
from orchestrator.agent_activation_preflight import effective_agent_profiles
from orchestrator.codex_cli_dry_invocation_guard import (
    file_record,
    load_json_object,
    object_value,
    relative_path,
    resolve_path,
    string_list,
    write_json,
)
from orchestrator.codex_cli_operator_unlock_request import (
    CODEX_CLI_OPERATOR_UNLOCK_REQUEST_SCHEMA_VERSION,
    REQUIRED_OPERATOR_CONFIRMATION_PHRASE,
)
from orchestrator.config import ProjectConfig, load_project_config
from orchestrator.schema_validation import validate_json_file


CODEX_CLI_EXECUTION_PREFLIGHT_SCHEMA_VERSION = "codex_cli_execution_preflight_v1"
CANARY_EXECUTABLE = "agents/codex_cli_canary.py"
TARGET_FILE = "strategies/current_strategy.py"
REQUEST_SCOPE = "real_codex_cli_execution_review"


def build_codex_cli_execution_preflight(
    *,
    run_dir: Path,
    config: ProjectConfig,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Return a startup gate report for real Codex CLI execution."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    profiles = effective_agent_profiles(config)
    profile_rows = [
        profile_execution_row(
            profile=profile,
            repo_root=repo_root,
            run_dir=run_dir,
            run_id=run_dir.name,
        )
        for profile in profiles
    ]
    blocking_errors = [
        error
        for row in profile_rows
        for error in string_list(row.get("blocking_errors", []))
    ]
    real_execute_profiles = [
        str(row.get("profile_name", ""))
        for row in profile_rows
        if bool(row.get("requires_operator_unlock", False))
    ]
    return {
        "schema_version": CODEX_CLI_EXECUTION_PREFLIGHT_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "ok": not blocking_errors,
        "blocking_errors": blocking_errors,
        "profiles": profile_rows,
        "summary": {
            "profile_count": len(profile_rows),
            "real_codex_execute_profile_count": len(real_execute_profiles),
            "real_codex_execute_profiles": real_execute_profiles,
            "operator_unlock_ready_count": sum(
                1
                for row in profile_rows
                if bool(row.get("operator_unlock_ready", False))
            ),
            "canary_exempt_count": sum(
                1 for row in profile_rows if bool(row.get("canary_exempt", False))
            ),
        },
        "policy": {
            "startup_gate_only": True,
            "read_only": True,
            "blocks_real_codex_without_operator_unlock": True,
            "allows_checked_in_canary_fixture": True,
            "does_not_execute_codex_cli": True,
            "does_not_create_workspace": True,
            "does_not_send_strategy_prompt": True,
            "does_not_modify_config": True,
            "does_not_select_candidate": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
            "deterministic_code_keeps_acceptance_authority": True,
        },
    }


def write_codex_cli_execution_preflight(
    *,
    output_path: Path,
    markdown_path: Path,
    run_dir: Path,
    config: ProjectConfig,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Write JSON and markdown startup gate artifacts."""
    repo_root = repo_root.resolve()
    payload = build_codex_cli_execution_preflight(
        run_dir=run_dir,
        config=config,
        repo_root=repo_root,
    )
    write_json(output_path, payload)
    markdown_path.write_text(
        codex_cli_execution_preflight_markdown(payload),
        encoding="utf-8",
    )
    return payload


def profile_execution_row(
    *,
    profile: dict[str, object],
    repo_root: Path,
    run_dir: Path,
    run_id: str,
) -> dict[str, Any]:
    """Return preflight status for one agent profile."""
    profile_name = str(profile.get("name", ""))
    adapter_name = str(profile.get("adapter", ""))
    enabled = bool(profile.get("enabled", True))
    settings = object_value(profile.get("settings", {}))
    executable = str(settings.get("executable", "codex"))
    execute = bool(settings.get("execute", False))
    canary_exempt = (
        enabled
        and adapter_name == "codex_cli"
        and execute
        and executable == CANARY_EXECUTABLE
    )
    requires_operator_unlock = (
        enabled and adapter_name == "codex_cli" and execute and not canary_exempt
    )
    request_path_text = str(settings.get("operator_unlock_request_path", ""))
    request_path = (
        resolve_path(Path(request_path_text), repo_root)
        if request_path_text
        else None
    )
    request = load_json_object(request_path) if request_path is not None else {}
    operator_intent = object_value(request.get("request", {}))
    planned = object_value(request.get("planned_execution_review", {}))
    source_pipeline = object_value(request.get("source_pipeline", {}))
    source_dry_run = object_value(request.get("source_real_execution_dry_run", {}))
    source_pipeline_file = object_value(source_pipeline.get("file", {}))
    source_dry_run_file = object_value(source_dry_run.get("file", {}))
    allowed_mutation_paths = string_list(planned.get("allowed_mutation_paths", []))
    expected_command = build_codex_command(
        executable=executable,
        model=str(settings.get("model", "default")),
        sandbox=str(settings.get("sandbox", "workspace-write")),
        target_file=TARGET_FILE,
    )
    planned_command = string_list(planned.get("command", []))
    expected_command_sha256 = stable_digest(expected_command)
    planned_workspace_path = str(planned.get("workspace_path", ""))
    workspace_root = str(settings.get("workspace_root", "workspaces"))
    expected_workspace_prefix = workspace_prefix(
        workspace_root=workspace_root,
        run_id=run_id,
    )
    expected_confirmation_hash = sha256_text(REQUIRED_OPERATOR_CONFIRMATION_PHRASE)
    checks = {
        "profile_enabled": enabled,
        "adapter_is_codex_cli": adapter_name == "codex_cli",
        "execute_true": execute,
        "canary_exempt": canary_exempt,
        "operator_unlock_request_path_declared": bool(request_path_text),
        "operator_unlock_request_exists": bool(
            request_path is not None and request_path.exists() and request_path.is_file()
        ),
        "operator_unlock_request_contract_valid": operator_request_contract_valid(
            request_path=request_path,
            repo_root=repo_root,
        ),
        "operator_unlock_request_schema_version_matches": str(
            request.get("schema_version", "")
        )
        == CODEX_CLI_OPERATOR_UNLOCK_REQUEST_SCHEMA_VERSION,
        "operator_unlock_request_ok": bool(request.get("ok", False)),
        "operator_unlock_request_ready": bool(
            request.get("operator_request_ready", False)
        ),
        "operator_request_run_id_matches": str(request.get("run_id", "")) == run_id,
        "operator_request_run_dir_matches_run": recorded_run_dir_matches(
            declared_run_dir=str(request.get("run_dir", "")),
            expected_run_dir=run_dir,
            repo_root=repo_root,
        ),
        "operator_request_scope_matches": str(
            operator_intent.get("request_scope", "")
        )
        == REQUEST_SCOPE,
        "operator_request_explicitly_requested": bool(
            operator_intent.get("requested", False)
        ),
        "operator_request_requested_by_present": bool(
            str(operator_intent.get("requested_by", "")).strip()
        ),
        "operator_request_confirmation_phrase_matches": bool(
            operator_intent.get("confirmation_phrase_matches", False)
        ),
        "operator_request_required_confirmation_hash_matches": str(
            operator_intent.get("required_confirmation_phrase_sha256", "")
        )
        == expected_confirmation_hash,
        "operator_request_provided_confirmation_hash_matches": str(
            operator_intent.get("provided_confirmation_phrase_sha256", "")
        )
        == expected_confirmation_hash,
        "operator_request_source_pipeline_hash_matches": recorded_file_matches(
            record=source_pipeline_file,
            repo_root=repo_root,
        ),
        "operator_request_source_pipeline_path_matches_record": recorded_path_matches(
            declared_path=str(source_pipeline.get("path", "")),
            record=source_pipeline_file,
            repo_root=repo_root,
        ),
        "operator_request_source_dry_run_hash_matches": recorded_file_matches(
            record=source_dry_run_file,
            repo_root=repo_root,
        ),
        "operator_request_source_dry_run_path_matches_record": recorded_path_matches(
            declared_path=str(source_dry_run.get("path", "")),
            record=source_dry_run_file,
            repo_root=repo_root,
        ),
        "operator_request_command_matches_profile": planned_command == expected_command,
        "operator_request_command_sha256_matches_profile": str(
            planned.get("command_sha256", "")
        )
        == expected_command_sha256,
        "operator_request_workspace_prefix_matches_run": (
            bool(expected_workspace_prefix)
            and planned_workspace_path.startswith(expected_workspace_prefix)
        ),
        "operator_request_targets_current_strategy": str(
            planned.get("target_file", "")
        )
        == TARGET_FILE,
        "operator_request_allows_strategy_only": allowed_mutation_paths == [TARGET_FILE],
        "operator_request_does_not_execute_by_itself": not bool(
            planned.get("execution_enabled_by_this_artifact", True)
        ),
    }
    blockers = (
        operator_unlock_blockers(checks)
        if requires_operator_unlock
        else []
    )
    return {
        "profile_name": profile_name,
        "adapter_name": adapter_name,
        "enabled": enabled,
        "execute": execute,
        "executable": executable,
        "requires_operator_unlock": requires_operator_unlock,
        "canary_exempt": canary_exempt,
        "operator_unlock_ready": requires_operator_unlock and not blockers,
        "blocking_errors": [
            f"profile {profile_name}: {blocker}" for blocker in blockers
        ],
        "checks": checks,
        "operator_unlock_request": (
            file_record(request_path, repo_root)
            if request_path is not None
            else {
                "exists": False,
                "path": "",
                "bytes": 0,
                "sha256": "",
            }
        ),
        "expected_execution": {
            "target_file": TARGET_FILE,
            "workspace_root": workspace_root,
            "workspace_prefix": expected_workspace_prefix,
            "command": expected_command,
            "command_sha256": expected_command_sha256,
        },
    }


def operator_unlock_blockers(checks: dict[str, bool]) -> list[str]:
    """Return blocker codes for real Codex execution unlock evidence."""
    blockers: list[str] = []
    for key, code in (
        ("operator_unlock_request_path_declared", "operator_unlock_request_path_missing"),
        ("operator_unlock_request_exists", "operator_unlock_request_missing"),
        (
            "operator_unlock_request_contract_valid",
            "operator_unlock_request_contract_invalid",
        ),
        (
            "operator_unlock_request_schema_version_matches",
            "operator_unlock_request_schema_version_mismatch",
        ),
        ("operator_unlock_request_ok", "operator_unlock_request_not_ok"),
        ("operator_unlock_request_ready", "operator_unlock_request_not_ready"),
        ("operator_request_run_id_matches", "operator_request_run_id_mismatch"),
        (
            "operator_request_run_dir_matches_run",
            "operator_request_run_dir_mismatch",
        ),
        ("operator_request_scope_matches", "operator_request_scope_mismatch"),
        (
            "operator_request_explicitly_requested",
            "operator_request_not_explicitly_requested",
        ),
        ("operator_request_requested_by_present", "operator_request_requested_by_missing"),
        (
            "operator_request_confirmation_phrase_matches",
            "operator_request_confirmation_phrase_mismatch",
        ),
        (
            "operator_request_required_confirmation_hash_matches",
            "operator_request_required_confirmation_hash_mismatch",
        ),
        (
            "operator_request_provided_confirmation_hash_matches",
            "operator_request_provided_confirmation_hash_mismatch",
        ),
        (
            "operator_request_source_pipeline_hash_matches",
            "operator_request_source_pipeline_hash_mismatch",
        ),
        (
            "operator_request_source_pipeline_path_matches_record",
            "operator_request_source_pipeline_path_mismatch",
        ),
        (
            "operator_request_source_dry_run_hash_matches",
            "operator_request_source_dry_run_hash_mismatch",
        ),
        (
            "operator_request_source_dry_run_path_matches_record",
            "operator_request_source_dry_run_path_mismatch",
        ),
        (
            "operator_request_command_matches_profile",
            "operator_request_command_mismatch",
        ),
        (
            "operator_request_command_sha256_matches_profile",
            "operator_request_command_sha256_mismatch",
        ),
        (
            "operator_request_workspace_prefix_matches_run",
            "operator_request_workspace_prefix_mismatch",
        ),
        (
            "operator_request_targets_current_strategy",
            "operator_request_target_not_current_strategy",
        ),
        (
            "operator_request_allows_strategy_only",
            "operator_request_mutation_paths_not_strategy_only",
        ),
        (
            "operator_request_does_not_execute_by_itself",
            "operator_request_executes_by_itself",
        ),
    ):
        if not checks.get(key, False):
            blockers.append(code)
    return blockers


def stable_digest(payload: object) -> str:
    """Return a stable digest for one JSON-compatible payload."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def sha256_text(text: str) -> str:
    """Return the SHA-256 hex digest for one UTF-8 text value."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def workspace_prefix(*, workspace_root: str, run_id: str) -> str:
    """Return the required run-scoped workspace prefix for real execution."""
    root = workspace_root.rstrip("/")
    return f"{root}/{run_id}/" if root and run_id else ""


def recorded_file_matches(*, record: dict[str, Any], repo_root: Path) -> bool:
    """Return whether a recorded file hash still matches the current file."""
    if not bool(record.get("exists", False)):
        return False
    path_text = str(record.get("path", ""))
    expected_sha256 = str(record.get("sha256", ""))
    if not path_text or not expected_sha256:
        return False
    path = resolve_path(Path(path_text), repo_root)
    if not path.exists() or not path.is_file():
        return False
    return str(file_record(path, repo_root).get("sha256", "")) == expected_sha256


def recorded_path_matches(
    *,
    declared_path: str,
    record: dict[str, Any],
    repo_root: Path,
) -> bool:
    """Return whether a declared artifact path matches its file record path."""
    if not declared_path:
        return False
    recorded_path = str(record.get("path", ""))
    if not recorded_path:
        return False
    normalized = relative_path(resolve_path(Path(declared_path), repo_root), repo_root)
    return normalized == recorded_path


def recorded_run_dir_matches(
    *,
    declared_run_dir: str,
    expected_run_dir: Path,
    repo_root: Path,
) -> bool:
    """Return whether a request run_dir points at the current run directory."""
    if not declared_run_dir:
        return False
    return (
        resolve_path(Path(declared_run_dir), repo_root).resolve()
        == expected_run_dir.resolve()
    )


def operator_request_contract_valid(
    *,
    request_path: Path | None,
    repo_root: Path,
) -> bool:
    """Return whether an operator request matches its local JSON contract."""
    if request_path is None or not request_path.exists() or not request_path.is_file():
        return False
    schema_path = repo_root / "schemas/codex_cli_operator_unlock_request.schema.json"
    if not schema_path.exists() or not schema_path.is_file():
        return False
    return validate_json_file(payload_path=request_path, schema_path=schema_path) == ()


def codex_cli_execution_preflight_markdown(payload: dict[str, Any]) -> str:
    """Return compact markdown for the startup execution gate."""
    lines = [
        "# Codex CLI Execution Preflight",
        "",
        f"- Schema: `{payload.get('schema_version', '')}`",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        "",
        "## Profiles",
    ]
    for profile in payload.get("profiles", []):
        if not isinstance(profile, dict):
            continue
        lines.append(
            f"- `{profile.get('profile_name', '')}` adapter=`{profile.get('adapter_name', '')}` "
            f"execute=`{profile.get('execute', False)}` "
            f"requires_unlock=`{profile.get('requires_operator_unlock', False)}`"
        )
    blockers = string_list(payload.get("blocking_errors", []))
    lines.extend(["", "## Blocking Errors"])
    lines.extend(f"- {reason}" for reason in blockers)
    if not blockers:
        lines.append("- none")
    lines.extend(
        [
            "",
            "This startup gate is read-only. It blocks real Codex CLI execution unless a ready operator unlock request is already recorded.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    """CLI entrypoint for Codex CLI execution preflight."""
    args = parse_args()
    repo_root = args.repo_root.resolve()
    config = load_project_config(repo_root, args.config)
    run_dir = resolve_path(args.run_dir, repo_root)
    payload = write_codex_cli_execution_preflight(
        output_path=args.output or run_dir / "codex_cli_execution_preflight.json",
        markdown_path=args.markdown_output
        or run_dir / "codex_cli_execution_preflight.md",
        run_dir=run_dir,
        config=config,
        repo_root=repo_root,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for Codex CLI execution preflight."""
    parser = argparse.ArgumentParser(
        description="Gate real Codex CLI execution before iteration starts.",
    )
    parser.add_argument("run_dir", type=Path, help="Path to the iteration run dir.")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to the project config.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root used to resolve paths.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_execution_preflight.json.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_execution_preflight.md.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
