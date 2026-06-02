"""Run the read-only Codex CLI readiness chain as one deterministic pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.codex_cli_dry_invocation_guard import (
    file_record,
    load_json_object,
    relative_path,
    resolve_path,
    string_list,
    write_codex_cli_dry_invocation_guard,
    write_json,
)
from orchestrator.codex_cli_enablement_gate import write_codex_cli_enablement_gate
from orchestrator.codex_cli_execution_candidate import (
    write_codex_cli_execution_candidate,
)
from orchestrator.codex_cli_execution_unlock_gate import (
    write_codex_cli_execution_unlock_gate,
)
from orchestrator.codex_cli_execution_unlock_snapshot import (
    write_codex_cli_execution_unlock_snapshot,
)
from orchestrator.codex_cli_manual_approval import (
    REQUIRED_CONFIRMATION_PHRASE,
    write_codex_cli_manual_approval,
)
from orchestrator.codex_cli_readiness_summary import (
    write_codex_cli_readiness_summary,
)
from orchestrator.codex_cli_real_execution_dry_run import (
    write_codex_cli_real_execution_dry_run,
)
from orchestrator.codex_cli_real_preflight import (
    PREFLIGHT_TIMEOUT_SECONDS,
    write_codex_cli_real_preflight,
)


CODEX_CLI_READINESS_PIPELINE_SCHEMA_VERSION = "codex_cli_readiness_pipeline_v1"

PIPELINE_STEPS = (
    (
        "codex_cli_enablement_gate",
        "codex_cli_enablement_gate.json",
        "codex_cli_enablement_gate.md",
        "permitted_to_enable",
    ),
    (
        "codex_cli_manual_approval",
        "codex_cli_manual_approval.json",
        "codex_cli_manual_approval.md",
        "ready_for_controlled_codex_cli_execution",
    ),
    (
        "codex_cli_real_preflight",
        "codex_cli_real_preflight.json",
        "codex_cli_real_preflight.md",
        "real_codex_cli_ready",
    ),
    (
        "codex_cli_dry_invocation_guard",
        "codex_cli_dry_invocation_guard.json",
        "codex_cli_dry_invocation_guard.md",
        "dry_invocation_ready",
    ),
    (
        "codex_cli_execution_unlock_gate",
        "codex_cli_execution_unlock_gate.json",
        "codex_cli_execution_unlock_gate.md",
        "real_codex_execution_unlocked",
    ),
    (
        "codex_cli_execution_unlock_snapshot",
        "codex_cli_execution_unlock_snapshot.json",
        "codex_cli_execution_unlock_snapshot.md",
        "real_codex_execution_unlocked",
    ),
    (
        "codex_cli_execution_candidate",
        "codex_cli_execution_candidate.json",
        "codex_cli_execution_candidate.md",
        "execution_candidate_ready",
    ),
    (
        "codex_cli_real_execution_dry_run",
        "codex_cli_real_execution_dry_run.json",
        "codex_cli_real_execution_dry_run.md",
        "real_execution_dry_run_ready",
    ),
    (
        "codex_cli_readiness_summary",
        "codex_cli_readiness_summary.json",
        "codex_cli_readiness_summary.md",
        "final_ready",
    ),
)


def build_codex_cli_readiness_pipeline(
    *,
    run_dir: Path,
    config_path: Path,
    repo_root: Path = Path("."),
    canary_run_dir: Path | None = None,
    approved: bool = False,
    approved_by: str = "pipeline",
    confirmation_phrase: str = "",
    preflight_timeout_seconds: int = PREFLIGHT_TIMEOUT_SECONDS,
    dry_invocation_timeout_seconds: int = 30,
    execute_dry_invocation: bool = False,
) -> dict[str, Any]:
    """Run the readiness writers in order and return a pipeline summary."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    run_dir.mkdir(parents=True, exist_ok=True)
    config_path = resolve_path(config_path, repo_root)
    canary_run_dir = (
        resolve_path(canary_run_dir, repo_root) if canary_run_dir is not None else run_dir
    )

    write_codex_cli_enablement_gate(
        run_dir=run_dir,
        config_path=config_path,
        repo_root=repo_root,
    )
    write_codex_cli_manual_approval(
        run_dir=run_dir,
        config_path=config_path,
        approved=approved,
        approved_by=approved_by,
        confirmation_phrase=confirmation_phrase,
        repo_root=repo_root,
    )
    write_codex_cli_real_preflight(
        run_dir=run_dir,
        config_path=config_path,
        repo_root=repo_root,
        timeout_seconds=preflight_timeout_seconds,
    )
    write_codex_cli_dry_invocation_guard(
        run_dir=run_dir,
        config_path=config_path,
        repo_root=repo_root,
        execute=execute_dry_invocation,
        timeout_seconds=dry_invocation_timeout_seconds,
    )
    write_codex_cli_execution_unlock_gate(
        run_dir=run_dir,
        config_path=config_path,
        repo_root=repo_root,
        canary_run_dir=canary_run_dir,
    )
    write_codex_cli_execution_unlock_snapshot(
        run_dir=run_dir,
        repo_root=repo_root,
    )
    write_codex_cli_execution_candidate(
        run_dir=run_dir,
        repo_root=repo_root,
    )
    write_codex_cli_real_execution_dry_run(
        run_dir=run_dir,
        repo_root=repo_root,
    )
    summary = write_codex_cli_readiness_summary(
        run_dir=run_dir,
        repo_root=repo_root,
    )

    steps = pipeline_step_summaries(run_dir=run_dir, repo_root=repo_root)
    generated_artifacts = generated_artifact_records(
        run_dir=run_dir,
        repo_root=repo_root,
    )
    final_ready = bool(summary.get("final_ready", False))
    return {
        "schema_version": CODEX_CLI_READINESS_PIPELINE_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "canary_run_dir": str(canary_run_dir),
        "config_path": relative_path(config_path, repo_root),
        "ok": True,
        "pipeline_completed": True,
        "final_ready": final_ready,
        "readiness_status": str(summary.get("readiness_status", "")),
        "blocking_reasons": string_list(
            summary.get("aggregate_blocking_reasons", [])
        ),
        "steps": steps,
        "generated_artifacts": generated_artifacts,
        "final_summary": {
            "path": relative_path(
                run_dir / "codex_cli_readiness_summary.json",
                repo_root,
            ),
            "final_ready": final_ready,
            "readiness_status": str(summary.get("readiness_status", "")),
            "missing_stages": string_list(summary.get("missing_stages", [])),
            "blocked_stages": string_list(summary.get("blocked_stages", [])),
            "file": file_record(run_dir / "codex_cli_readiness_summary.json", repo_root),
        },
        "options": {
            "approved": bool(approved),
            "approved_by": approved_by,
            "confirmation_phrase_matches_required": (
                confirmation_phrase == REQUIRED_CONFIRMATION_PHRASE
            ),
            "preflight_timeout_seconds": preflight_timeout_seconds,
            "dry_invocation_timeout_seconds": dry_invocation_timeout_seconds,
            "execute_dry_invocation": bool(execute_dry_invocation),
        },
        "policy": {
            "pipeline_only": True,
            "read_only": True,
            "does_not_execute_real_codex_strategy_modification": True,
            "does_not_create_real_execution_workspace": True,
            "does_not_send_strategy_prompt": True,
            "does_not_modify_config": True,
            "does_not_select_candidate": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
            "requires_existing_replay_gate": True,
            "requires_existing_canary_gate": True,
            "deterministic_code_keeps_acceptance_authority": True,
        },
    }


def write_codex_cli_readiness_pipeline(
    *,
    run_dir: Path,
    config_path: Path,
    repo_root: Path = Path("."),
    canary_run_dir: Path | None = None,
    approved: bool = False,
    approved_by: str = "pipeline",
    confirmation_phrase: str = "",
    preflight_timeout_seconds: int = PREFLIGHT_TIMEOUT_SECONDS,
    dry_invocation_timeout_seconds: int = 30,
    execute_dry_invocation: bool = False,
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    """Write JSON and markdown artifacts for the readiness pipeline."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_codex_cli_readiness_pipeline(
        run_dir=run_dir,
        config_path=config_path,
        repo_root=repo_root,
        canary_run_dir=canary_run_dir,
        approved=approved,
        approved_by=approved_by,
        confirmation_phrase=confirmation_phrase,
        preflight_timeout_seconds=preflight_timeout_seconds,
        dry_invocation_timeout_seconds=dry_invocation_timeout_seconds,
        execute_dry_invocation=execute_dry_invocation,
    )
    destination = output_path or run_dir / "codex_cli_readiness_pipeline.json"
    write_json(destination, payload)
    markdown_destination = markdown_path or run_dir / "codex_cli_readiness_pipeline.md"
    markdown_destination.write_text(
        codex_cli_readiness_pipeline_markdown(payload),
        encoding="utf-8",
    )
    return payload


def pipeline_step_summaries(*, run_dir: Path, repo_root: Path) -> list[dict[str, Any]]:
    """Return compact summaries for pipeline-generated steps."""
    steps: list[dict[str, Any]] = []
    for step_name, json_name, markdown_name, ready_key in PIPELINE_STEPS:
        json_path = run_dir / json_name
        payload = load_json_object(json_path)
        steps.append(
            {
                "step": step_name,
                "schema_version": str(payload.get("schema_version", "")),
                "ok": bool(payload.get("ok", False)),
                "ready_key": ready_key,
                "ready": bool(payload.get(ready_key, False)),
                "blocking_reasons": string_list(
                    payload.get(
                        "aggregate_blocking_reasons",
                        payload.get("blocking_reasons", []),
                    )
                ),
                "artifacts": {
                    "json": file_record(json_path, repo_root),
                    "markdown": file_record(run_dir / markdown_name, repo_root),
                },
            }
        )
    return steps


def generated_artifact_records(
    *,
    run_dir: Path,
    repo_root: Path,
) -> dict[str, dict[str, object]]:
    """Return records for all files produced by this pipeline."""
    records: dict[str, dict[str, object]] = {}
    for step_name, json_name, markdown_name, _ready_key in PIPELINE_STEPS:
        records[f"{step_name}.json"] = file_record(run_dir / json_name, repo_root)
        records[f"{step_name}.markdown"] = file_record(
            run_dir / markdown_name,
            repo_root,
        )
    for key, filename in (
        ("codex_cli_dry_invocation.prompt", "codex_cli_dry_invocation_prompt.txt"),
        (
            "codex_cli_dry_invocation.execution_audit",
            "codex_cli_dry_invocation_execution.json",
        ),
        (
            "codex_cli_dry_invocation.output",
            "codex_cli_dry_invocation_output.txt",
        ),
    ):
        path = run_dir / filename
        if path.exists():
            records[key] = file_record(path, repo_root)
    return records


def codex_cli_readiness_pipeline_markdown(payload: dict[str, Any]) -> str:
    """Return compact markdown for the readiness pipeline."""
    lines = [
        "# Codex CLI Readiness Pipeline",
        "",
        f"- Schema: `{payload.get('schema_version', '')}`",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Pipeline completed: `{payload.get('pipeline_completed', False)}`",
        f"- Status: `{payload.get('readiness_status', '')}`",
        f"- Final ready: `{payload.get('final_ready', False)}`",
        "",
        "## Steps",
    ]
    for step in payload.get("steps", []):
        if not isinstance(step, dict):
            continue
        lines.append(
            f"- `{step.get('step', '')}` ready=`{step.get('ready', False)}` "
            f"ok=`{step.get('ok', False)}`"
        )
    blockers = string_list(payload.get("blocking_reasons", []))
    lines.extend(["", "## Blocking Reasons"])
    lines.extend(f"- {reason}" for reason in blockers)
    if not blockers:
        lines.append("- none")
    lines.extend(
        [
            "",
            "This pipeline generates readiness evidence only. It does not execute Codex CLI strategy modification, apply patches, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    """CLI entrypoint for the read-only Codex CLI readiness pipeline."""
    args = parse_args()
    payload = write_codex_cli_readiness_pipeline(
        run_dir=args.run_dir,
        config_path=args.config,
        repo_root=args.repo_root,
        canary_run_dir=args.canary_run_dir,
        approved=args.approved,
        approved_by=args.approved_by,
        confirmation_phrase=args.confirmation_phrase,
        preflight_timeout_seconds=args.preflight_timeout_seconds,
        dry_invocation_timeout_seconds=args.dry_invocation_timeout_seconds,
        execute_dry_invocation=args.execute_dry_invocation,
        output_path=args.output,
        markdown_path=args.markdown_output,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for the readiness pipeline."""
    parser = argparse.ArgumentParser(
        description="Run the read-only Codex CLI readiness chain.",
    )
    parser.add_argument("run_dir", type=Path, help="Path to a guarded run directory.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/codex_cli_enable_candidate.json"),
        help="Path to the candidate execute=true config.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root used to resolve paths.",
    )
    parser.add_argument(
        "--canary-run-dir",
        type=Path,
        default=None,
        help="Run directory containing codex_cli_canary_gate.json.",
    )
    parser.add_argument(
        "--approved",
        action="store_true",
        help="Record explicit manual approval for this candidate.",
    )
    parser.add_argument(
        "--approved-by",
        default="pipeline",
        help="Stable approver name for the manual approval artifact.",
    )
    parser.add_argument(
        "--confirmation-phrase",
        default="",
        help="Exact confirmation phrase required by manual approval.",
    )
    parser.add_argument(
        "--preflight-timeout-seconds",
        type=int,
        default=PREFLIGHT_TIMEOUT_SECONDS,
        help="Timeout for the Codex CLI --version probe.",
    )
    parser.add_argument(
        "--dry-invocation-timeout-seconds",
        type=int,
        default=30,
        help="Timeout for the harmless dry invocation if enabled.",
    )
    parser.add_argument(
        "--execute-dry-invocation",
        action="store_true",
        help="Execute only the harmless dry-invocation guard.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_readiness_pipeline.json.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_readiness_pipeline.md.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
