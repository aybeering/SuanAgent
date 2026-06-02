"""Summarize Codex CLI readiness artifacts into one read-only report."""

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


CODEX_CLI_READINESS_SUMMARY_SCHEMA_VERSION = "codex_cli_readiness_summary_v1"

STAGE_DEFINITIONS = (
    ("codex_cli_replay_gate", "codex_cli_replay_gate.json", "ready_to_enable_codex_cli"),
    ("codex_cli_enablement_gate", "codex_cli_enablement_gate.json", "permitted_to_enable"),
    (
        "codex_cli_manual_approval",
        "codex_cli_manual_approval.json",
        "ready_for_controlled_codex_cli_execution",
    ),
    ("codex_cli_canary_gate", "codex_cli_canary_gate.json", "controlled_execution_ready"),
    ("codex_cli_real_preflight", "codex_cli_real_preflight.json", "real_codex_cli_ready"),
    (
        "codex_cli_dry_invocation_guard",
        "codex_cli_dry_invocation_guard.json",
        "dry_invocation_ready",
    ),
    (
        "codex_cli_execution_unlock_gate",
        "codex_cli_execution_unlock_gate.json",
        "real_codex_execution_unlocked",
    ),
    (
        "codex_cli_execution_unlock_snapshot",
        "codex_cli_execution_unlock_snapshot.json",
        "real_codex_execution_unlocked",
    ),
    (
        "codex_cli_execution_candidate",
        "codex_cli_execution_candidate.json",
        "execution_candidate_ready",
    ),
    (
        "codex_cli_real_execution_dry_run",
        "codex_cli_real_execution_dry_run.json",
        "real_execution_dry_run_ready",
    ),
)


def build_codex_cli_readiness_summary(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Return a read-only summary for the Codex CLI readiness chain."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    artifact_overrides = stage_artifact_overrides(run_dir=run_dir, repo_root=repo_root)
    stages = [
        stage_summary(
            run_dir=run_dir,
            repo_root=repo_root,
            stage_name=stage_name,
            filename=filename,
            ready_key=ready_key,
            artifact_path=artifact_overrides.get(stage_name),
        )
        for stage_name, filename, ready_key in STAGE_DEFINITIONS
    ]
    missing = [stage["stage"] for stage in stages if not stage["artifact"]["exists"]]
    blocked = [
        stage["stage"]
        for stage in stages
        if stage["artifact"]["exists"] and not bool(stage["ready"])
    ]
    aggregate_blockers = aggregate_stage_blockers(stages)
    final_stage = stages[-1]
    final_ready = bool(final_stage["ready"])
    readiness_status = "ready_for_operator_review" if final_ready else "blocked"
    return {
        "schema_version": CODEX_CLI_READINESS_SUMMARY_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "ok": True,
        "readiness_status": readiness_status,
        "final_ready": final_ready,
        "missing_stages": missing,
        "blocked_stages": blocked,
        "aggregate_blocking_reasons": aggregate_blockers,
        "stages": stages,
        "policy": {
            "summary_only": True,
            "read_only": True,
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


def write_codex_cli_readiness_summary(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    """Write JSON and markdown Codex CLI readiness summary artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_codex_cli_readiness_summary(run_dir=run_dir, repo_root=repo_root)
    destination = output_path or run_dir / "codex_cli_readiness_summary.json"
    write_json(destination, payload)
    markdown_destination = markdown_path or run_dir / "codex_cli_readiness_summary.md"
    markdown_destination.write_text(
        codex_cli_readiness_summary_markdown(payload),
        encoding="utf-8",
    )
    return payload


def stage_summary(
    *,
    run_dir: Path,
    repo_root: Path,
    stage_name: str,
    filename: str,
    ready_key: str,
    artifact_path: Path | None = None,
) -> dict[str, Any]:
    """Return one stage summary."""
    path = artifact_path or run_dir / filename
    payload = load_json_object(path)
    artifact = file_record(path, repo_root)
    exists = bool(artifact["exists"])
    ready = exists and bool(payload.get(ready_key, False))
    blockers = string_list(payload.get("blocking_reasons", []))
    if not exists:
        blockers = [f"{stage_name}_missing"]
    return {
        "stage": stage_name,
        "schema_version": str(payload.get("schema_version", "")),
        "artifact": artifact,
        "ok": bool(payload.get("ok", False)) if exists else False,
        "ready_key": ready_key,
        "ready": ready,
        "blocking_reasons": blockers,
    }


def stage_artifact_overrides(*, run_dir: Path, repo_root: Path) -> dict[str, Path]:
    """Return stage artifact paths recorded by upstream gates."""
    unlock_gate = load_json_object(run_dir / "codex_cli_execution_unlock_gate.json")
    unlock_artifacts = object_value(unlock_gate.get("artifacts", {}))
    canary_record = object_value(unlock_artifacts.get("codex_cli_canary_gate", {}))
    canary_path = str(canary_record.get("path", ""))
    if not canary_path:
        return {}
    return {"codex_cli_canary_gate": resolve_path(Path(canary_path), repo_root)}


def aggregate_stage_blockers(stages: list[dict[str, Any]]) -> list[str]:
    """Return stable deduplicated blocking reason strings."""
    blockers: list[str] = []
    seen: set[str] = set()
    for stage in stages:
        stage_name = str(stage.get("stage", ""))
        for reason in string_list(stage.get("blocking_reasons", [])):
            item = f"{stage_name}:{reason}"
            if item not in seen:
                blockers.append(item)
                seen.add(item)
    return blockers


def codex_cli_readiness_summary_markdown(payload: dict[str, Any]) -> str:
    """Return compact markdown for Codex CLI readiness."""
    lines = [
        "# Codex CLI Readiness Summary",
        "",
        f"- Schema: `{payload.get('schema_version', '')}`",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('readiness_status', '')}`",
        f"- Final ready: `{payload.get('final_ready', False)}`",
        "",
        "## Stages",
    ]
    for stage in payload.get("stages", []):
        if not isinstance(stage, dict):
            continue
        lines.append(
            f"- `{stage.get('stage', '')}` ready=`{stage.get('ready', False)}` "
            f"ok=`{stage.get('ok', False)}`"
        )
    blockers = string_list(payload.get("aggregate_blocking_reasons", []))
    lines.extend(["", "## Blocking Reasons"])
    lines.extend(f"- {reason}" for reason in blockers)
    if not blockers:
        lines.append("- none")
    lines.extend(
        [
            "",
            "This report is read-only. It summarizes readiness evidence and does not execute Codex CLI.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    """CLI entrypoint for Codex CLI readiness summaries."""
    args = parse_args()
    payload = write_codex_cli_readiness_summary(
        run_dir=args.run_dir,
        repo_root=args.repo_root,
        output_path=args.output,
        markdown_path=args.markdown_output,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for Codex CLI readiness summaries."""
    parser = argparse.ArgumentParser(
        description="Summarize the Codex CLI readiness chain.",
    )
    parser.add_argument("run_dir", type=Path, help="Path to a guarded run directory.")
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
        help="Optional path for codex_cli_readiness_summary.json.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_readiness_summary.md.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
