"""Record an operator request for future Codex CLI execution review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.codex_cli_dry_invocation_guard import (
    file_record,
    load_json_object,
    object_value,
    resolve_path,
    sha256_text,
    string_list,
    write_json,
)


CODEX_CLI_OPERATOR_UNLOCK_REQUEST_SCHEMA_VERSION = (
    "codex_cli_operator_unlock_request_v1"
)
REQUIRED_OPERATOR_CONFIRMATION_PHRASE = (
    "I request operator review for real Codex CLI execution"
)
TARGET_FILE = "strategies/current_strategy.py"


def build_codex_cli_operator_unlock_request(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
    requested: bool = False,
    requested_by: str = "",
    confirmation_phrase: str = "",
    request_scope: str = "real_codex_cli_execution_review",
    pipeline_path: Path | None = None,
    dry_run_path: Path | None = None,
) -> dict[str, Any]:
    """Return a read-only operator request for future real Codex CLI execution."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    pipeline_path = resolve_path(
        pipeline_path or run_dir / "codex_cli_readiness_pipeline.json",
        repo_root,
    )
    dry_run_path = resolve_path(
        dry_run_path or run_dir / "codex_cli_real_execution_dry_run.json",
        repo_root,
    )
    ensure_canonical_operator_unlock_source_paths(
        pipeline_path=pipeline_path,
        dry_run_path=dry_run_path,
        run_dir=run_dir,
        repo_root=repo_root,
    )
    pipeline = load_json_object(pipeline_path)
    dry_run = load_json_object(dry_run_path)
    planned_execution = object_value(dry_run.get("planned_execution", {}))
    allowed_mutation_paths = string_list(
        planned_execution.get("allowed_mutation_paths", [])
    )
    command = string_list(planned_execution.get("command", []))
    checks = {
        "readiness_pipeline_exists": pipeline_path.exists() and pipeline_path.is_file(),
        "readiness_pipeline_path_is_canonical_run_artifact": path_is_canonical_artifact(
            path=pipeline_path,
            expected_path=run_dir / "codex_cli_readiness_pipeline.json",
        ),
        "readiness_pipeline_ok": bool(pipeline.get("ok", False)),
        "readiness_pipeline_completed": bool(
            pipeline.get("pipeline_completed", False)
        ),
        "readiness_pipeline_final_ready": bool(pipeline.get("final_ready", False)),
        "readiness_pipeline_hash_present": bool(
            file_record(pipeline_path, repo_root).get("sha256", "")
        ),
        "real_execution_dry_run_exists": dry_run_path.exists() and dry_run_path.is_file(),
        "real_execution_dry_run_path_is_canonical_run_artifact": (
            path_is_canonical_artifact(
                path=dry_run_path,
                expected_path=run_dir / "codex_cli_real_execution_dry_run.json",
            )
        ),
        "real_execution_dry_run_ok": bool(dry_run.get("ok", False)),
        "real_execution_dry_run_ready": bool(
            dry_run.get("real_execution_dry_run_ready", False)
        ),
        "execution_plan_present": bool(planned_execution),
        "command_present": bool(command),
        "target_file_is_current_strategy": str(
            planned_execution.get("target_file", "")
        )
        == TARGET_FILE,
        "allowed_mutation_paths_strategy_only": allowed_mutation_paths == [TARGET_FILE],
        "explicit_operator_request": bool(requested),
        "requested_by_present": bool(requested_by.strip()),
        "confirmation_phrase_matches": (
            confirmation_phrase == REQUIRED_OPERATOR_CONFIRMATION_PHRASE
        ),
        "request_does_not_execute_codex_cli": True,
        "request_does_not_create_workspace": True,
        "request_does_not_send_strategy_prompt": True,
        "request_does_not_apply_patches": True,
        "request_does_not_change_acceptance": True,
    }
    blocking_reasons = request_blockers(checks)
    ready = not blocking_reasons
    return {
        "schema_version": CODEX_CLI_OPERATOR_UNLOCK_REQUEST_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "ok": True,
        "operator_request_ready": ready,
        "blocking_reasons": blocking_reasons,
        "checks": checks,
        "request": {
            "requested": bool(requested),
            "requested_by": requested_by.strip(),
            "request_scope": request_scope,
            "required_confirmation_phrase_sha256": sha256_text(
                REQUIRED_OPERATOR_CONFIRMATION_PHRASE
            ),
            "provided_confirmation_phrase_sha256": sha256_text(confirmation_phrase),
            "confirmation_phrase_matches": checks["confirmation_phrase_matches"],
        },
        "source_pipeline": {
            "path": relative_path(pipeline_path, repo_root),
            "final_ready": bool(pipeline.get("final_ready", False)),
            "readiness_status": str(pipeline.get("readiness_status", "")),
            "blocking_reasons": string_list(pipeline.get("blocking_reasons", [])),
            "file": file_record(pipeline_path, repo_root),
        },
        "source_real_execution_dry_run": {
            "path": relative_path(dry_run_path, repo_root),
            "real_execution_dry_run_ready": bool(
                dry_run.get("real_execution_dry_run_ready", False)
            ),
            "blocking_reasons": string_list(dry_run.get("blocking_reasons", [])),
            "file": file_record(dry_run_path, repo_root),
        },
        "planned_execution_review": {
            "agent_name": str(planned_execution.get("agent_name", "")),
            "profile_name": str(planned_execution.get("profile_name", "")),
            "round_id": str(planned_execution.get("round_id", "")),
            "attempt_id": str(planned_execution.get("attempt_id", "")),
            "target_file": str(planned_execution.get("target_file", "")),
            "allowed_mutation_paths": allowed_mutation_paths,
            "workspace_path": str(planned_execution.get("workspace_path", "")),
            "command": command,
            "command_sha256": stable_digest(command),
            "execution_enabled_by_this_artifact": False,
        },
        "policy": {
            "operator_request_only": True,
            "read_only": True,
            "requires_readiness_pipeline": True,
            "requires_pipeline_final_ready": True,
            "requires_real_execution_dry_run_ready": True,
            "requires_explicit_operator_request": True,
            "requires_exact_confirmation_phrase": True,
            "does_not_execute_codex_cli": True,
            "does_not_create_workspace": True,
            "does_not_send_strategy_prompt": True,
            "does_not_modify_config": True,
            "does_not_select_candidate": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
            "allows_only_strategy_file_mutation": True,
            "deterministic_code_keeps_acceptance_authority": True,
        },
    }


def write_codex_cli_operator_unlock_request(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
    requested: bool = False,
    requested_by: str = "",
    confirmation_phrase: str = "",
    request_scope: str = "real_codex_cli_execution_review",
    pipeline_path: Path | None = None,
    dry_run_path: Path | None = None,
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    """Write JSON and markdown operator request artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    destination = output_path or run_dir / "codex_cli_operator_unlock_request.json"
    markdown_destination = markdown_path or (
        run_dir / "codex_cli_operator_unlock_request.md"
    )
    ensure_canonical_operator_unlock_request_paths(
        output_path=destination,
        markdown_path=markdown_destination,
        run_dir=run_dir,
        repo_root=repo_root,
    )
    payload = build_codex_cli_operator_unlock_request(
        run_dir=run_dir,
        repo_root=repo_root,
        requested=requested,
        requested_by=requested_by,
        confirmation_phrase=confirmation_phrase,
        request_scope=request_scope,
        pipeline_path=pipeline_path,
        dry_run_path=dry_run_path,
    )
    write_json(destination, payload)
    markdown_destination.write_text(
        codex_cli_operator_unlock_request_markdown(payload),
        encoding="utf-8",
    )
    return payload


def ensure_canonical_operator_unlock_request_paths(
    *,
    output_path: Path,
    markdown_path: Path,
    run_dir: Path,
    repo_root: Path,
) -> None:
    """Require operator request artifacts to be written to canonical run paths."""
    output_path = resolve_path(output_path, repo_root)
    markdown_path = resolve_path(markdown_path, repo_root)
    expected_output_path = run_dir / "codex_cli_operator_unlock_request.json"
    expected_markdown_path = run_dir / "codex_cli_operator_unlock_request.md"
    if output_path.resolve() != expected_output_path.resolve():
        raise ValueError(
            "operator unlock request JSON must be written to "
            f"{expected_output_path}"
        )
    if markdown_path.resolve() != expected_markdown_path.resolve():
        raise ValueError(
            "operator unlock request markdown must be written to "
            f"{expected_markdown_path}"
        )


def ensure_canonical_operator_unlock_source_paths(
    *,
    pipeline_path: Path,
    dry_run_path: Path,
    run_dir: Path,
    repo_root: Path,
) -> None:
    """Require operator request source evidence to come from canonical run paths."""
    pipeline_path = resolve_path(pipeline_path, repo_root)
    dry_run_path = resolve_path(dry_run_path, repo_root)
    expected_pipeline_path = run_dir / "codex_cli_readiness_pipeline.json"
    expected_dry_run_path = run_dir / "codex_cli_real_execution_dry_run.json"
    if pipeline_path.resolve() != expected_pipeline_path.resolve():
        raise ValueError(
            "operator unlock request pipeline source must be "
            f"{expected_pipeline_path}"
        )
    if dry_run_path.resolve() != expected_dry_run_path.resolve():
        raise ValueError(
            "operator unlock request dry-run source must be "
            f"{expected_dry_run_path}"
        )


def path_is_canonical_artifact(*, path: Path, expected_path: Path) -> bool:
    """Return whether a path resolves to the expected artifact path."""
    return path.resolve() == expected_path.resolve()


def request_blockers(checks: dict[str, bool]) -> list[str]:
    """Return stable blocker codes for an operator unlock request."""
    blockers: list[str] = []
    for key, code in (
        ("readiness_pipeline_exists", "readiness_pipeline_missing"),
        (
            "readiness_pipeline_path_is_canonical_run_artifact",
            "readiness_pipeline_path_not_canonical_run_artifact",
        ),
        ("readiness_pipeline_ok", "readiness_pipeline_not_ok"),
        ("readiness_pipeline_completed", "readiness_pipeline_incomplete"),
        ("readiness_pipeline_final_ready", "readiness_pipeline_not_final_ready"),
        ("readiness_pipeline_hash_present", "readiness_pipeline_hash_missing"),
        ("real_execution_dry_run_exists", "real_execution_dry_run_missing"),
        (
            "real_execution_dry_run_path_is_canonical_run_artifact",
            "real_execution_dry_run_path_not_canonical_run_artifact",
        ),
        ("real_execution_dry_run_ok", "real_execution_dry_run_not_ok"),
        ("real_execution_dry_run_ready", "real_execution_dry_run_not_ready"),
        ("execution_plan_present", "execution_plan_missing"),
        ("command_present", "command_missing"),
        ("target_file_is_current_strategy", "target_file_not_current_strategy"),
        (
            "allowed_mutation_paths_strategy_only",
            "allowed_mutation_paths_not_strategy_only",
        ),
        ("explicit_operator_request", "explicit_operator_request_missing"),
        ("requested_by_present", "requested_by_missing"),
        ("confirmation_phrase_matches", "confirmation_phrase_mismatch"),
        ("request_does_not_execute_codex_cli", "request_executed_codex_cli"),
        ("request_does_not_create_workspace", "request_created_workspace"),
        ("request_does_not_send_strategy_prompt", "request_sent_strategy_prompt"),
        ("request_does_not_apply_patches", "request_applied_patch"),
        ("request_does_not_change_acceptance", "request_changed_acceptance"),
    ):
        if not checks.get(key, False):
            blockers.append(code)
    return blockers


def stable_digest(payload: object) -> str:
    """Return a stable digest for one JSON-compatible payload."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256_text(encoded)


def codex_cli_operator_unlock_request_markdown(payload: dict[str, Any]) -> str:
    """Return compact markdown for the operator unlock request."""
    blockers = string_list(payload.get("blocking_reasons", []))
    request = object_value(payload.get("request", {}))
    planned = object_value(payload.get("planned_execution_review", {}))
    lines = [
        "# Codex CLI Operator Unlock Request",
        "",
        f"- Schema: `{payload.get('schema_version', '')}`",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Operator request ready: `{payload.get('operator_request_ready', False)}`",
        f"- Requested by: `{request.get('requested_by', '')}`",
        f"- Target: `{planned.get('target_file', '')}`",
        f"- Workspace: `{planned.get('workspace_path', '')}`",
        "",
        "## Blocking Reasons",
    ]
    lines.extend(f"- {reason}" for reason in blockers)
    if not blockers:
        lines.append("- none")
    lines.extend(
        [
            "",
            "This artifact records operator intent only. It does not execute Codex CLI, create workspaces, apply patches, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> None:
    """CLI entrypoint for operator unlock requests."""
    args = parse_args()
    try:
        payload = write_codex_cli_operator_unlock_request(
            run_dir=args.run_dir,
            repo_root=args.repo_root,
            requested=args.requested,
            requested_by=args.requested_by,
            confirmation_phrase=args.confirmation_phrase,
            request_scope=args.request_scope,
            pipeline_path=args.pipeline,
            dry_run_path=args.dry_run,
            output_path=args.output,
            markdown_path=args.markdown_output,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for operator unlock requests."""
    parser = argparse.ArgumentParser(
        description="Record a read-only operator request for Codex CLI execution review.",
    )
    parser.add_argument("run_dir", type=Path, help="Path to a guarded run directory.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root used to resolve paths.",
    )
    parser.add_argument(
        "--requested",
        action="store_true",
        help="Record an explicit operator request.",
    )
    parser.add_argument(
        "--requested-by",
        default="",
        help="Stable operator identifier for the request.",
    )
    parser.add_argument(
        "--confirmation-phrase",
        default="",
        help="Exact confirmation phrase required for the request.",
    )
    parser.add_argument(
        "--request-scope",
        default="real_codex_cli_execution_review",
        help="Stable request scope recorded in the artifact.",
    )
    parser.add_argument(
        "--pipeline",
        type=Path,
        default=None,
        help=(
            "Optional explicit path; must equal "
            "<run_dir>/codex_cli_readiness_pipeline.json."
        ),
    )
    parser.add_argument(
        "--dry-run",
        type=Path,
        default=None,
        help=(
            "Optional explicit path; must equal "
            "<run_dir>/codex_cli_real_execution_dry_run.json."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Optional explicit path; must equal "
            "<run_dir>/codex_cli_operator_unlock_request.json."
        ),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help=(
            "Optional explicit path; must equal "
            "<run_dir>/codex_cli_operator_unlock_request.md."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
