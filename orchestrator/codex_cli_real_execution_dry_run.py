"""Dry-run the final real Codex CLI execution boundary without executing it."""

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
    string_list,
    write_json,
)
from orchestrator.codex_cli_execution_candidate import TARGET_FILE


CODEX_CLI_REAL_EXECUTION_DRY_RUN_SCHEMA_VERSION = (
    "codex_cli_real_execution_dry_run_v1"
)


def build_codex_cli_real_execution_dry_run(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
    candidate_path: Path | None = None,
) -> dict[str, Any]:
    """Return a read-only final dry-run audit for the real Codex execution path."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    candidate_path = resolve_path(
        candidate_path or run_dir / "codex_cli_execution_candidate.json",
        repo_root,
    )
    candidate = load_json_object(candidate_path)
    execution_plan = object_value(candidate.get("execution_plan", {}))
    command = string_list(execution_plan.get("command", []))
    allowed_mutation_paths = string_list(
        execution_plan.get("allowed_mutation_paths", [])
    )
    workspace_path = resolve_path(
        Path(str(execution_plan.get("workspace_path", ""))),
        repo_root,
    )
    checks = {
        "candidate_exists": candidate_path.exists() and candidate_path.is_file(),
        "candidate_ok": bool(candidate.get("ok", False)),
        "candidate_ready": bool(candidate.get("execution_candidate_ready", False)),
        "candidate_file_hash_present": bool(
            file_record(candidate_path, repo_root).get("sha256", "")
        ),
        "source_snapshot_recorded": bool(
            object_value(candidate.get("source_snapshot", {})).get("snapshot_digest", "")
        ),
        "execution_plan_present": bool(execution_plan),
        "command_present": bool(command),
        "command_targets_strategy_only": command_targets_only_strategy(command),
        "workspace_path_declared": bool(str(execution_plan.get("workspace_path", ""))),
        "workspace_not_created": not workspace_path.exists(),
        "allowed_mutation_paths_strategy_only": allowed_mutation_paths == [TARGET_FILE],
        "candidate_does_not_execute_by_itself": not bool(
            execution_plan.get("execution_enabled_by_this_artifact", True)
        ),
        "dry_run_does_not_execute_codex_cli": True,
        "dry_run_does_not_create_workspace": True,
        "dry_run_does_not_send_strategy_prompt": True,
        "dry_run_does_not_apply_patches": True,
        "dry_run_does_not_change_acceptance": True,
    }
    blocking_reasons = dry_run_blockers(checks)
    ready = not blocking_reasons
    return {
        "schema_version": CODEX_CLI_REAL_EXECUTION_DRY_RUN_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "ok": True,
        "real_execution_dry_run_ready": ready,
        "blocking_reasons": blocking_reasons,
        "checks": checks,
        "source_candidate": {
            "path": str(candidate_path.relative_to(repo_root))
            if candidate_path.is_relative_to(repo_root)
            else str(candidate_path),
            "execution_candidate_ready": bool(
                candidate.get("execution_candidate_ready", False)
            ),
            "blocking_reasons": string_list(candidate.get("blocking_reasons", [])),
            "file": file_record(candidate_path, repo_root),
        },
        "planned_execution": {
            "agent_name": str(execution_plan.get("agent_name", "")),
            "profile_name": str(execution_plan.get("profile_name", "")),
            "round_id": str(execution_plan.get("round_id", "")),
            "attempt_id": str(execution_plan.get("attempt_id", "")),
            "target_file": str(execution_plan.get("target_file", "")),
            "allowed_mutation_paths": allowed_mutation_paths,
            "workspace_path": str(execution_plan.get("workspace_path", "")),
            "command": command,
            "timeout_seconds": int_value(execution_plan.get("timeout_seconds", 0)),
        },
        "dry_run_result": {
            "execution_performed": False,
            "subprocess_invoked": False,
            "workspace_created": False,
            "patch_applied": False,
            "acceptance_changed": False,
            "would_execute_if_unlocked_and_operator_confirms": ready,
        },
        "policy": {
            "dry_run_only": True,
            "read_only": True,
            "requires_execution_candidate": True,
            "requires_candidate_ready": True,
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


def write_codex_cli_real_execution_dry_run(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
    candidate_path: Path | None = None,
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    """Write JSON and markdown real-execution dry-run artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_codex_cli_real_execution_dry_run(
        run_dir=run_dir,
        repo_root=repo_root,
        candidate_path=candidate_path,
    )
    destination = output_path or run_dir / "codex_cli_real_execution_dry_run.json"
    write_json(destination, payload)
    markdown_destination = markdown_path or (
        run_dir / "codex_cli_real_execution_dry_run.md"
    )
    markdown_destination.write_text(
        codex_cli_real_execution_dry_run_markdown(payload),
        encoding="utf-8",
    )
    return payload


def command_targets_only_strategy(command: list[str]) -> bool:
    """Return whether the planned command references the strategy target only."""
    command_text = " ".join(str(part) for part in command)
    return (
        TARGET_FILE in command_text
        and "data/" not in command_text
        and "backtester/" not in command_text
        and "orchestrator/policy_gate.py" not in command_text
    )


def dry_run_blockers(checks: dict[str, bool]) -> list[str]:
    """Return stable blockers for the final real-execution dry run."""
    blockers: list[str] = []
    for key, code in (
        ("candidate_exists", "execution_candidate_missing"),
        ("candidate_ok", "execution_candidate_not_ok"),
        ("candidate_ready", "execution_candidate_not_ready"),
        ("candidate_file_hash_present", "execution_candidate_hash_missing"),
        ("source_snapshot_recorded", "source_snapshot_not_recorded"),
        ("execution_plan_present", "execution_plan_missing"),
        ("command_present", "command_missing"),
        ("command_targets_strategy_only", "command_not_strategy_only"),
        ("workspace_path_declared", "workspace_path_missing"),
        ("workspace_not_created", "workspace_already_exists"),
        (
            "allowed_mutation_paths_strategy_only",
            "allowed_mutation_paths_not_strategy_only",
        ),
        ("candidate_does_not_execute_by_itself", "candidate_executes_by_itself"),
        ("dry_run_does_not_execute_codex_cli", "dry_run_executed_codex_cli"),
        ("dry_run_does_not_create_workspace", "dry_run_created_workspace"),
        ("dry_run_does_not_send_strategy_prompt", "dry_run_sent_strategy_prompt"),
        ("dry_run_does_not_apply_patches", "dry_run_applied_patch"),
        ("dry_run_does_not_change_acceptance", "dry_run_changed_acceptance"),
    ):
        if not checks.get(key, False):
            blockers.append(code)
    return blockers


def codex_cli_real_execution_dry_run_markdown(payload: dict[str, Any]) -> str:
    """Return compact markdown for the final real-execution dry run."""
    blockers = string_list(payload.get("blocking_reasons", []))
    planned = object_value(payload.get("planned_execution", {}))
    lines = [
        "# Codex CLI Real Execution Dry Run",
        "",
        f"- Schema: `{payload.get('schema_version', '')}`",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Dry run ready: `{payload.get('real_execution_dry_run_ready', False)}`",
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
            "This final dry run records the real execution boundary without invoking Codex CLI or creating a workspace.",
            "",
        ]
    )
    return "\n".join(lines)


def int_value(value: object) -> int:
    """Return an integer value or zero."""
    return value if isinstance(value, int) else 0


def main() -> None:
    """CLI entrypoint for final real-execution dry runs."""
    args = parse_args()
    payload = write_codex_cli_real_execution_dry_run(
        run_dir=args.run_dir,
        repo_root=args.repo_root,
        candidate_path=args.candidate,
        output_path=args.output,
        markdown_path=args.markdown_output,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for final real-execution dry runs."""
    parser = argparse.ArgumentParser(
        description="Dry-run the final real Codex CLI execution boundary.",
    )
    parser.add_argument("run_dir", type=Path, help="Path to a guarded run directory.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root used to resolve paths.",
    )
    parser.add_argument(
        "--candidate",
        type=Path,
        default=None,
        help="Optional path to codex_cli_execution_candidate.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_real_execution_dry_run.json.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_real_execution_dry_run.md.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
