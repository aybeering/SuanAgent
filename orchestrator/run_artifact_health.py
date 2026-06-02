"""Batch-validate saved experiment run artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.artifact_validator import validate_run_artifacts
from orchestrator.experiment_index import read_experiment_index
from orchestrator.schema_validation import validate_json_file


SCHEMA_VERSION = "run_artifact_health_v1"
SCHEMA_PATH = Path("schemas/run_artifact_health.schema.json")


def build_run_artifact_health(
    *,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    limit: int = 10,
    all_runs: bool = False,
    run_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return a deterministic health report for saved experiment artifacts."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    selected_run_ids = select_run_ids(
        experiments_dir=experiments_dir,
        limit=limit,
        all_runs=all_runs,
        run_ids=run_ids,
    )
    reports = [
        validate_run_artifacts(
            run_id=run_id,
            experiments_dir=experiments_dir,
            repo_root=repo_root,
        )
        for run_id in selected_run_ids
    ]
    rows = [health_row(report) for report in reports]
    totals = health_totals(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "repo_root": str(repo_root),
        "experiments_dir": str(experiments_dir),
        "ok": totals["failed_count"] == 0,
        "selection": {
            "mode": selection_mode(run_ids=run_ids, all_runs=all_runs),
            "limit": max(limit, 0),
            "requested_run_ids": list(run_ids or []),
            "selected_run_ids": selected_run_ids,
        },
        "totals": totals,
        "runs": rows,
        "policy": {
            "inspection_only": True,
            "validates_saved_artifacts_only": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
            "strict_mode_required_for_nonzero_exit": True,
        },
    }


def select_run_ids(
    *,
    experiments_dir: Path,
    limit: int,
    all_runs: bool,
    run_ids: list[str] | None,
) -> list[str]:
    """Return stable run ids for batch validation."""
    if run_ids:
        return list(dict.fromkeys(run_ids))

    records = read_experiment_index(experiments_dir)
    indexed_ids = [
        str(record.get("run_id", ""))
        for record in records
        if isinstance(record.get("run_id"), str) and record.get("run_id")
    ]
    if not indexed_ids:
        indexed_ids = directory_run_ids(experiments_dir)

    if all_runs:
        return indexed_ids
    return indexed_ids[-max(limit, 0) :]


def directory_run_ids(experiments_dir: Path) -> list[str]:
    """Return run directory names when the experiment index is absent."""
    if not experiments_dir.exists():
        return []
    return sorted(
        path.name
        for path in experiments_dir.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )


def selection_mode(*, run_ids: list[str] | None, all_runs: bool) -> str:
    """Return a compact selection mode label."""
    if run_ids:
        return "explicit"
    if all_runs:
        return "all"
    return "recent"


def health_row(report: dict[str, object]) -> dict[str, Any]:
    """Return one compact row from a single-run validation report."""
    errors = string_list(report.get("errors", []))
    warnings = string_list(report.get("warnings", []))
    checked_files = string_list(report.get("checked_files", []))
    return {
        "run_id": str(report.get("run_id", "")),
        "run_dir": str(report.get("run_dir", "")),
        "kind": str(report.get("kind", "unknown")),
        "ok": bool(report.get("ok", False)),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "checked_file_count": len(checked_files),
        "rounds_checked": int(report.get("rounds_checked", 0) or 0),
        "errors": errors,
        "warnings": warnings,
    }


def health_totals(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Return aggregate run artifact health counts."""
    return {
        "run_count": len(rows),
        "ok_count": sum(1 for row in rows if row["ok"]),
        "failed_count": sum(1 for row in rows if not row["ok"]),
        "error_count": sum(int(row["error_count"]) for row in rows),
        "warning_count": sum(int(row["warning_count"]) for row in rows),
        "checked_file_count": sum(int(row["checked_file_count"]) for row in rows),
        "rounds_checked": sum(int(row["rounds_checked"]) for row in rows),
    }


def string_list(value: object) -> list[str]:
    """Return a list of strings from a report field."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def write_run_artifact_health(
    *,
    output_path: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    limit: int = 10,
    all_runs: bool = False,
    run_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Write a batch run artifact health report."""
    payload = build_run_artifact_health(
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        limit=limit,
        all_runs=all_runs,
        run_ids=run_ids,
    )
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    errors = validate_run_artifact_health_file(
        payload_path=output_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(f"run artifact health failed schema validation: {errors}")
    return payload


def validate_run_artifact_health_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved run artifact health report."""
    return validate_json_file(
        payload_path=payload_path,
        schema_path=repo_root / SCHEMA_PATH,
    )


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve paths relative to the repository root."""
    return path if path.is_absolute() else repo_root / path


def main() -> None:
    """CLI entrypoint for batch artifact validation."""
    parser = argparse.ArgumentParser(
        description="Batch-validate SuanAgent experiment run artifacts.",
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
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--all", action="store_true", dest="all_runs")
    parser.add_argument("--run-id", action="append", dest="run_ids", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    if args.output is not None:
        payload = write_run_artifact_health(
            output_path=args.output,
            experiments_dir=args.experiments_dir,
            repo_root=args.repo_root,
            limit=args.limit,
            all_runs=args.all_runs,
            run_ids=args.run_ids,
        )
    else:
        payload = build_run_artifact_health(
            experiments_dir=args.experiments_dir,
            repo_root=args.repo_root,
            limit=args.limit,
            all_runs=args.all_runs,
            run_ids=args.run_ids,
        )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.strict and not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
