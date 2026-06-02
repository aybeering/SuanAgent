"""Prepare a read-only Codex CLI execution candidate after unlock evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agents.codex_dry_run_adapter import build_codex_command
from orchestrator.codex_cli_dry_invocation_guard import (
    file_record,
    int_value,
    load_json_object,
    object_value,
    relative_path,
    resolve_path,
    string_list,
    write_json,
)


CODEX_CLI_EXECUTION_CANDIDATE_SCHEMA_VERSION = "codex_cli_execution_candidate_v1"
TARGET_FILE = "strategies/current_strategy.py"
ROUND_ID = "codex_cli_real_execution"
ATTEMPT_ID = "attempt_001_real_execution"
PROFILE_NAME = "real_codex_execution"


def build_codex_cli_execution_candidate(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
    snapshot_path: Path | None = None,
) -> dict[str, Any]:
    """Return a read-only candidate plan for a future real Codex CLI execution."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    snapshot_path = resolve_path(
        snapshot_path or run_dir / "codex_cli_execution_unlock_snapshot.json",
        repo_root,
    )
    snapshot = load_json_object(snapshot_path)
    candidate_config_record = object_value(
        object_value(snapshot.get("evidence_artifacts", {})).get(
            "candidate_config",
            {},
        )
    )
    config_path = resolve_path(
        Path(str(candidate_config_record.get("path", ""))),
        repo_root,
    )
    config = load_json_object(config_path)
    codex_cli = object_value(config.get("codex_cli", {}))
    command = build_codex_command(
        executable=str(codex_cli.get("executable", "codex")),
        model=str(codex_cli.get("model", "default")),
        sandbox=str(codex_cli.get("sandbox", "workspace-write")),
        target_file=TARGET_FILE,
    )
    workspace_path = planned_workspace_path(
        repo_root=repo_root,
        workspace_root=str(codex_cli.get("workspace_root", "workspaces")),
        run_id=run_dir.name,
    )
    checks = {
        "snapshot_exists": snapshot_path.exists() and snapshot_path.is_file(),
        "snapshot_ok": bool(snapshot.get("ok", False)),
        "snapshot_digest_present": bool(str(snapshot.get("snapshot_digest", ""))),
        "snapshot_unlocked": bool(snapshot.get("real_codex_execution_unlocked", False)),
        "snapshot_source_gate_hash_present": bool(
            object_value(snapshot.get("source_gate", {})).get("sha256", "")
        ),
        "candidate_config_recorded": bool(candidate_config_record),
        "candidate_config_exists": config_path.exists() and config_path.is_file(),
        "candidate_config_sha256_matches_snapshot": str(
            candidate_config_record.get("sha256", "")
        )
        == str(file_record(config_path, repo_root).get("sha256", "")),
        "config_binding_all_matched": bool(
            object_value(snapshot.get("config_binding", {})).get("all_matched", False)
        ),
        "strategy_modifier_is_codex_cli": str(config.get("strategy_modifier", ""))
        == "codex_cli",
        "execute_true_candidate": bool(codex_cli.get("execute", False)),
        "sandbox_workspace_write": str(codex_cli.get("sandbox", ""))
        == "workspace-write",
        "workspace_root_declared": bool(str(codex_cli.get("workspace_root", ""))),
        "target_file_is_current_strategy": TARGET_FILE
        == str(config.get("strategy_path", TARGET_FILE)),
        "allowed_mutation_paths_strategy_only": [TARGET_FILE] == [TARGET_FILE],
        "command_targets_strategy_only": command_targets_only_strategy(command),
        "does_not_execute_codex_cli": True,
        "does_not_create_workspace": True,
        "does_not_apply_patches": True,
        "does_not_change_acceptance": True,
    }
    blocking_reasons = candidate_blockers(checks)
    ready = not blocking_reasons
    return {
        "schema_version": CODEX_CLI_EXECUTION_CANDIDATE_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "ok": True,
        "execution_candidate_ready": ready,
        "blocking_reasons": blocking_reasons,
        "checks": checks,
        "source_snapshot": {
            "path": relative_path(snapshot_path, repo_root),
            "snapshot_digest": str(snapshot.get("snapshot_digest", "")),
            "real_codex_execution_unlocked": bool(
                snapshot.get("real_codex_execution_unlocked", False)
            ),
            "blocking_reasons": string_list(snapshot.get("blocking_reasons", [])),
            "file": file_record(snapshot_path, repo_root),
        },
        "candidate_config": file_record(config_path, repo_root),
        "execution_plan": {
            "agent_name": "codex_cli",
            "profile_name": PROFILE_NAME,
            "round_id": ROUND_ID,
            "attempt_id": ATTEMPT_ID,
            "target_file": TARGET_FILE,
            "allowed_mutation_paths": [TARGET_FILE],
            "workspace_path": relative_path(workspace_path, repo_root),
            "command": command,
            "timeout_seconds": int_value(codex_cli.get("timeout_seconds", 0)),
            "execution_enabled_by_this_artifact": False,
            "codex_cli_execute_flag": bool(codex_cli.get("execute", False)),
        },
        "policy": {
            "candidate_only": True,
            "read_only": True,
            "requires_unlock_snapshot": True,
            "requires_snapshot_unlocked": True,
            "requires_candidate_config_hash_match": True,
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


def write_codex_cli_execution_candidate(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
    snapshot_path: Path | None = None,
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    """Write JSON and markdown Codex CLI execution candidate artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_codex_cli_execution_candidate(
        run_dir=run_dir,
        repo_root=repo_root,
        snapshot_path=snapshot_path,
    )
    destination = output_path or run_dir / "codex_cli_execution_candidate.json"
    write_json(destination, payload)
    markdown_destination = markdown_path or run_dir / "codex_cli_execution_candidate.md"
    markdown_destination.write_text(
        codex_cli_execution_candidate_markdown(payload),
        encoding="utf-8",
    )
    return payload


def planned_workspace_path(
    *,
    repo_root: Path,
    workspace_root: str,
    run_id: str,
) -> Path:
    """Return the future workspace path without creating it."""
    return (
        repo_root
        / workspace_root
        / run_id
        / ROUND_ID
        / PROFILE_NAME
        / ATTEMPT_ID
        / "strategy_workspace"
    )


def command_targets_only_strategy(command: list[str]) -> bool:
    """Return whether the planned command references the strategy target only."""
    command_text = " ".join(str(part) for part in command)
    return (
        TARGET_FILE in command_text
        and "data/" not in command_text
        and "backtester/" not in command_text
        and "orchestrator/policy_gate.py" not in command_text
    )


def candidate_blockers(checks: dict[str, bool]) -> list[str]:
    """Return stable blocker codes for a real Codex CLI execution candidate."""
    blockers: list[str] = []
    for key, code in (
        ("snapshot_exists", "unlock_snapshot_missing"),
        ("snapshot_ok", "unlock_snapshot_not_ok"),
        ("snapshot_digest_present", "unlock_snapshot_digest_missing"),
        ("snapshot_unlocked", "unlock_snapshot_not_unlocked"),
        ("snapshot_source_gate_hash_present", "unlock_snapshot_source_hash_missing"),
        ("candidate_config_recorded", "candidate_config_not_recorded"),
        ("candidate_config_exists", "candidate_config_missing"),
        (
            "candidate_config_sha256_matches_snapshot",
            "candidate_config_sha256_mismatch",
        ),
        ("config_binding_all_matched", "config_binding_not_matched"),
        ("strategy_modifier_is_codex_cli", "strategy_modifier_not_codex_cli"),
        ("execute_true_candidate", "execute_not_true_candidate"),
        ("sandbox_workspace_write", "sandbox_not_workspace_write"),
        ("workspace_root_declared", "workspace_root_missing"),
        ("target_file_is_current_strategy", "target_file_not_current_strategy"),
        (
            "allowed_mutation_paths_strategy_only",
            "allowed_mutation_paths_not_strategy_only",
        ),
        ("command_targets_strategy_only", "command_not_strategy_only"),
        ("does_not_execute_codex_cli", "candidate_executed_codex_cli"),
        ("does_not_create_workspace", "candidate_created_workspace"),
        ("does_not_apply_patches", "candidate_applied_patch"),
        ("does_not_change_acceptance", "candidate_changed_acceptance"),
    ):
        if not checks.get(key, False):
            blockers.append(code)
    return blockers


def codex_cli_execution_candidate_markdown(payload: dict[str, Any]) -> str:
    """Return compact markdown for a Codex CLI execution candidate."""
    blockers = string_list(payload.get("blocking_reasons", []))
    execution_plan = object_value(payload.get("execution_plan", {}))
    lines = [
        "# Codex CLI Execution Candidate",
        "",
        f"- Schema: `{payload.get('schema_version', '')}`",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Candidate ready: `{payload.get('execution_candidate_ready', False)}`",
        f"- Target: `{execution_plan.get('target_file', '')}`",
        f"- Workspace: `{execution_plan.get('workspace_path', '')}`",
        "",
        "## Blocking Reasons",
    ]
    lines.extend(f"- {reason}" for reason in blockers)
    if not blockers:
        lines.append("- none")
    lines.extend(
        [
            "",
            "This candidate freezes the future command and mutation boundary. It is read-only and does not execute Codex CLI.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    """CLI entrypoint for Codex CLI execution candidates."""
    args = parse_args()
    payload = write_codex_cli_execution_candidate(
        run_dir=args.run_dir,
        repo_root=args.repo_root,
        snapshot_path=args.snapshot,
        output_path=args.output,
        markdown_path=args.markdown_output,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for Codex CLI execution candidates."""
    parser = argparse.ArgumentParser(
        description="Prepare a read-only Codex CLI execution candidate.",
    )
    parser.add_argument("run_dir", type=Path, help="Path to a guarded run directory.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root used to resolve paths.",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=None,
        help="Optional path to codex_cli_execution_unlock_snapshot.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_execution_candidate.json.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_execution_candidate.md.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
