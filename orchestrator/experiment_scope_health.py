"""Unified read-only health summary for one experiment time scope."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.memory_diagnostics import build_memory_diagnostics
from orchestrator.run_artifact_health import (
    DEFAULT_HISTORY_FILENAME,
    build_run_artifact_health,
    build_run_artifact_health_history,
    resolve_path,
    string_list,
)
from orchestrator.schema_validation import validate_json_file


SCHEMA_VERSION = "experiment_scope_health_v1"
SCHEMA_PATH = Path("schemas/experiment_scope_health.schema.json")


def build_experiment_scope_health(
    *,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    history_path: Path | None = None,
    limit: int = 20,
    created_at_from: str = "",
) -> dict[str, Any]:
    """Return a compact read-only health page for the selected experiment scope."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    active_history_path = (
        resolve_path(history_path, repo_root)
        if history_path is not None
        else experiments_dir / DEFAULT_HISTORY_FILENAME
    )
    run_health = build_run_artifact_health(
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        limit=limit,
        all_runs=True,
        created_at_from=created_at_from,
    )
    health_history = build_run_artifact_health_history(
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        history_path=active_history_path,
        limit=limit,
        created_at_from=created_at_from,
    )
    memory_diagnostics = build_memory_diagnostics(
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        history_path=active_history_path,
        limit=limit,
        created_at_from=created_at_from,
    )

    run_totals = dict(run_health.get("totals", {}))
    history_totals = dict(health_history.get("totals", {}))
    memory_totals = dict(memory_diagnostics.get("totals", {}))
    summary = {
        "scoped_run_count": int(run_totals.get("run_count", 0) or 0),
        "artifact_failed_run_count": int(run_totals.get("failed_count", 0) or 0),
        "artifact_error_count": int(run_totals.get("error_count", 0) or 0),
        "artifact_warning_count": int(run_totals.get("warning_count", 0) or 0),
        "history_record_count": int(history_totals.get("record_count", 0) or 0),
        "history_failed_run_observation_count": int(
            history_totals.get("failed_run_observation_count", 0) or 0
        ),
        "history_artifact_failure_count": int(
            history_totals.get("artifact_failure_count", 0) or 0
        ),
        "memory_outcome_record_count": int(
            memory_totals.get("outcome_record_count", 0) or 0
        ),
        "memory_failed_health_run_count": int(
            memory_totals.get("failed_health_run_count", 0) or 0
        ),
        "memory_matched_failed_health_run_count": int(
            memory_totals.get("matched_failed_health_run_count", 0) or 0
        ),
        "read_error_count": int(history_totals.get("read_error_count", 0) or 0)
        + int(memory_totals.get("read_error_count", 0) or 0),
    }
    component_status = {
        "run_artifact_health_ok": bool(run_health.get("ok", False)),
        "run_artifact_health_history_ok": bool(health_history.get("ok", False)),
        "memory_diagnostics_ok": bool(memory_diagnostics.get("ok", False)),
        "history_scope_clean": summary["history_failed_run_observation_count"] == 0,
        "memory_scope_clean": summary["memory_failed_health_run_count"] == 0,
    }
    ok = all(component_status.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "repo_root": str(repo_root),
        "experiments_dir": str(experiments_dir),
        "history_path": str(active_history_path),
        "scope": {
            "created_at_from": created_at_from,
            "run_selection": "all_indexed_runs_in_scope",
        },
        "ok": ok,
        "status": "healthy" if ok else "unhealthy",
        "summary": summary,
        "component_status": component_status,
        "components": {
            "run_artifact_health": compact_run_artifact_health(run_health),
            "run_artifact_health_history": compact_run_artifact_health_history(
                health_history
            ),
            "memory_diagnostics": compact_memory_diagnostics(memory_diagnostics),
        },
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "reads_outcome_memory_only": True,
            "reads_artifact_health_history_only": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
            "does_not_route_agents": True,
            "strict_mode_required_for_nonzero_exit": True,
        },
    }


def compact_run_artifact_health(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the current artifact health fields needed for scope triage."""
    runs = [row for row in payload.get("runs", []) if isinstance(row, dict)]
    return {
        "schema_version": str(payload.get("schema_version", "")),
        "ok": bool(payload.get("ok", False)),
        "selection": payload.get("selection", {}),
        "totals": payload.get("totals", {}),
        "failed_run_ids": [
            str(row.get("run_id", "")) for row in runs if not bool(row.get("ok", False))
        ],
    }


def compact_run_artifact_health_history(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the artifact-health history fields needed for scope triage."""
    run_failures = [
        row for row in payload.get("run_failures", []) if isinstance(row, dict)
    ]
    return {
        "schema_version": str(payload.get("schema_version", "")),
        "ok": bool(payload.get("ok", False)),
        "scope": payload.get("scope", {}),
        "totals": payload.get("totals", {}),
        "failed_run_ids": [str(row.get("run_id", "")) for row in run_failures],
        "artifact_failure_names": [
            str(row.get("artifact_name", ""))
            for row in payload.get("artifact_failures", [])
            if isinstance(row, dict)
        ],
        "read_errors": string_list(payload.get("read_errors", [])),
    }


def compact_memory_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the memory diagnostics fields needed for scope triage."""
    return {
        "schema_version": str(payload.get("schema_version", "")),
        "ok": bool(payload.get("ok", False)),
        "scope": payload.get("scope", {}),
        "totals": payload.get("totals", {}),
        "matched_failed_run_ids": string_list(
            payload.get("matched_failed_run_ids", [])
        ),
        "unmatched_failed_health_run_ids": string_list(
            payload.get("unmatched_failed_health_run_ids", [])
        ),
        "read_errors": string_list(payload.get("read_errors", [])),
    }


def write_experiment_scope_health(
    *,
    output_path: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    history_path: Path | None = None,
    limit: int = 20,
    created_at_from: str = "",
) -> dict[str, Any]:
    """Write and validate a unified experiment scope health report."""
    payload = build_experiment_scope_health(
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        history_path=history_path,
        limit=limit,
        created_at_from=created_at_from,
    )
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    errors = validate_experiment_scope_health_file(
        payload_path=output_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(f"experiment scope health failed schema validation: {errors}")
    return payload


def render_experiment_scope_health_markdown(payload: dict[str, Any]) -> str:
    """Render an experiment scope health payload as terminal markdown."""
    def compact_list(values: list[str], *, max_items: int = 10) -> str:
        if not values:
            return "`none`"
        shown = values[:max_items]
        text = ", ".join(f"`{value}`" for value in shown)
        remaining = len(values) - len(shown)
        if remaining > 0:
            text += f", ... +{remaining} more"
        return text

    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    component_status = payload.get("component_status", {})
    if not isinstance(component_status, dict):
        component_status = {}
    scope = payload.get("scope", {})
    if not isinstance(scope, dict):
        scope = {}
    components = payload.get("components", {})
    if not isinstance(components, dict):
        components = {}

    run_health = components.get("run_artifact_health", {})
    if not isinstance(run_health, dict):
        run_health = {}
    history = components.get("run_artifact_health_history", {})
    if not isinstance(history, dict):
        history = {}
    memory = components.get("memory_diagnostics", {})
    if not isinstance(memory, dict):
        memory = {}

    lines = [
        "# Experiment Scope Health",
        "",
        f"- Status: `{payload.get('status', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Created at from: `{scope.get('created_at_from', '')}`",
        f"- Experiments dir: `{payload.get('experiments_dir', '')}`",
        f"- History path: `{payload.get('history_path', '')}`",
        "",
        "## Summary",
        "",
        f"- Scoped runs: `{summary.get('scoped_run_count', 0)}`",
        f"- Artifact failed runs: `{summary.get('artifact_failed_run_count', 0)}`",
        f"- Artifact errors: `{summary.get('artifact_error_count', 0)}`",
        f"- Artifact warnings: `{summary.get('artifact_warning_count', 0)}`",
        f"- History records: `{summary.get('history_record_count', 0)}`",
        "- History failed run observations: "
        f"`{summary.get('history_failed_run_observation_count', 0)}`",
        f"- Memory outcome records: `{summary.get('memory_outcome_record_count', 0)}`",
        "- Memory failed health runs: "
        f"`{summary.get('memory_failed_health_run_count', 0)}`",
        f"- Read errors: `{summary.get('read_error_count', 0)}`",
        "",
        "## Component Status",
        "",
    ]
    for key in (
        "run_artifact_health_ok",
        "run_artifact_health_history_ok",
        "memory_diagnostics_ok",
        "history_scope_clean",
        "memory_scope_clean",
    ):
        lines.append(f"- {key}: `{component_status.get(key, False)}`")

    lines.extend(["", "## Failed Runs", ""])
    failed_run_ids = string_list(run_health.get("failed_run_ids", []))
    history_failed_run_ids = string_list(history.get("failed_run_ids", []))
    memory_failed_run_ids = string_list(
        memory.get("unmatched_failed_health_run_ids", [])
    )
    lines.append(
        "- Current artifact health: "
        + compact_list(failed_run_ids)
    )
    lines.append(
        "- Artifact-health history: "
        + compact_list(history_failed_run_ids)
    )
    lines.append(
        "- Memory diagnostics unmatched: "
        + compact_list(memory_failed_run_ids)
    )

    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This view is read-only and does not execute agents, run backtests, route agents, apply patches, or change acceptance.",
            "- Use `--strict` when a nonzero exit is required for unhealthy scopes.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_experiment_scope_health_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved experiment scope health report."""
    return validate_json_file(
        payload_path=payload_path,
        schema_path=repo_root / SCHEMA_PATH,
    )


def main() -> None:
    """CLI entrypoint for unified experiment scope health."""
    parser = argparse.ArgumentParser(
        description="Inspect artifact health, health history, and memory for one scope.",
    )
    parser.add_argument(
        "--experiments-dir",
        type=Path,
        default=Path("experiments"),
        help="Directory containing experiment artifacts.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root for schema and relative path resolution.",
    )
    parser.add_argument("--history-path", type=Path)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--created-at-from",
        default="",
        help="Only inspect indexed runs and memory records from this UTC timestamp.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render the scope health report as markdown.",
    )
    args = parser.parse_args()

    if args.output is not None:
        payload = write_experiment_scope_health(
            output_path=args.output,
            experiments_dir=args.experiments_dir,
            repo_root=args.repo_root,
            history_path=args.history_path,
            limit=args.limit,
            created_at_from=args.created_at_from,
        )
    else:
        payload = build_experiment_scope_health(
            experiments_dir=args.experiments_dir,
            repo_root=args.repo_root,
            history_path=args.history_path,
            limit=args.limit,
            created_at_from=args.created_at_from,
        )
    if args.markdown:
        print(render_experiment_scope_health_markdown(payload), end="")
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    if args.strict and not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
