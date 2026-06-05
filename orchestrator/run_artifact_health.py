"""Batch-validate saved experiment run artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from orchestrator.artifact_validator import validate_run_artifacts
from orchestrator.experiment_index import read_experiment_index
from orchestrator.schema_validation import validate_json_file


SCHEMA_VERSION = "run_artifact_health_v1"
SCHEMA_PATH = Path("schemas/run_artifact_health.schema.json")
HISTORY_SCHEMA_VERSION = "run_artifact_health_history_v1"
HISTORY_RECORD_SCHEMA_VERSION = "run_artifact_health_history_record_v1"
HISTORY_SCHEMA_PATH = Path("schemas/run_artifact_health_history.schema.json")
DEFAULT_HISTORY_FILENAME = "run_artifact_health_history.jsonl"


def build_run_artifact_health(
    *,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    limit: int = 10,
    all_runs: bool = False,
    run_ids: list[str] | None = None,
    created_at_from: str = "",
) -> dict[str, Any]:
    """Return a deterministic health report for saved experiment artifacts."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    selected_run_ids = select_run_ids(
        experiments_dir=experiments_dir,
        limit=limit,
        all_runs=all_runs,
        run_ids=run_ids,
        created_at_from=created_at_from,
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
            "filters": {
                "created_at_from": created_at_from,
                "applied_to_explicit_run_ids": False,
            },
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
    created_at_from: str = "",
) -> list[str]:
    """Return stable run ids for batch validation."""
    if run_ids:
        return list(dict.fromkeys(run_ids))

    records = read_experiment_index(experiments_dir)
    if created_at_from:
        records = [
            record
            for record in records
            if str(record.get("created_at", "")) >= created_at_from
        ]
    indexed_ids = [
        str(record.get("run_id", ""))
        for record in records
        if isinstance(record.get("run_id"), str) and record.get("run_id")
    ]
    if not indexed_ids and not created_at_from:
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


def compact_markdown_list(values: list[str], *, max_items: int = 5) -> str:
    """Return a bounded inline markdown list."""
    if not values:
        return "`none`"
    shown = values[:max_items]
    text = ", ".join(f"`{value}`" for value in shown)
    extra_count = len(values) - len(shown)
    if extra_count > 0:
        text += f", ... +{extra_count} more"
    return text


def render_run_artifact_health_history_markdown(payload: dict[str, Any]) -> str:
    """Render artifact-health history as compact terminal markdown."""
    scope = payload.get("scope", {})
    if not isinstance(scope, dict):
        scope = {}
    totals = payload.get("totals", {})
    if not isinstance(totals, dict):
        totals = {}
    run_failures = payload.get("run_failures", [])
    if not isinstance(run_failures, list):
        run_failures = []
    artifact_failures = payload.get("artifact_failures", [])
    if not isinstance(artifact_failures, list):
        artifact_failures = []
    recent_records = payload.get("recent_records", [])
    if not isinstance(recent_records, list):
        recent_records = []

    lines = [
        "# Run Artifact Health History",
        "",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Created at from: `{scope.get('created_at_from', '')}`",
        f"- Experiments dir: `{payload.get('experiments_dir', '')}`",
        f"- History path: `{payload.get('history_path', '')}`",
        "",
        "## Totals",
        "",
        f"- Records: `{totals.get('record_count', 0)}`",
        f"- Records with failures: `{totals.get('records_with_failures', 0)}`",
        (
            "- Failed run observations: "
            f"`{totals.get('failed_run_observation_count', 0)}`"
        ),
        f"- Artifact failures: `{totals.get('artifact_failure_count', 0)}`",
        f"- Read errors: `{totals.get('read_error_count', 0)}`",
        "",
        "## Top Failing Runs",
        "",
    ]

    if not run_failures:
        lines.append("- none")
    for row in run_failures[:10]:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"- `{row.get('run_id', '')}`: failures "
            f"`{row.get('failure_count', 0)}`, errors "
            f"`{row.get('total_error_count', 0)}`"
        )

    lines.extend(["", "## Top Artifact Failures", ""])
    if not artifact_failures:
        lines.append("- none")
    for row in artifact_failures[:10]:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"- `{row.get('artifact_name', '')}`: failures "
            f"`{row.get('failure_count', 0)}`, runs "
            + compact_markdown_list(string_list(row.get("run_ids", [])))
        )

    lines.extend(["", "## Recent Records", ""])
    if not recent_records:
        lines.append("- none")
    for row in recent_records[:5]:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"- `{row.get('recorded_at', '')}`: ok `{row.get('ok', False)}`, "
            f"runs `{row.get('run_count', 0)}`, failed "
            f"`{row.get('failed_count', 0)}`, failed ids "
            + compact_markdown_list(string_list(row.get("failed_run_ids", [])))
        )

    lines.extend(
        [
            "",
            "## Policy",
            "",
            (
                "- This view is read-only and does not execute agents, run "
                "backtests, apply patches, or change acceptance."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def write_run_artifact_health(
    *,
    output_path: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    limit: int = 10,
    all_runs: bool = False,
    run_ids: list[str] | None = None,
    created_at_from: str = "",
) -> dict[str, Any]:
    """Write a batch run artifact health report."""
    payload = build_run_artifact_health(
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        limit=limit,
        all_runs=all_runs,
        run_ids=run_ids,
        created_at_from=created_at_from,
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


def append_run_artifact_health_history(
    *,
    payload: dict[str, Any],
    history_path: Path,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    """Append one compact artifact-health history record."""
    history_path.parent.mkdir(parents=True, exist_ok=True)
    record = history_record_from_health(
        payload=payload,
        recorded_at=recorded_at or utc_timestamp(),
    )
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def history_record_from_health(
    *,
    payload: dict[str, Any],
    recorded_at: str,
) -> dict[str, Any]:
    """Return a compact JSONL record from a health payload."""
    runs = [row for row in payload.get("runs", []) if isinstance(row, dict)]
    failed_runs = [
        {
            "run_id": str(row.get("run_id", "")),
            "kind": str(row.get("kind", "unknown")),
            "error_count": int(row.get("error_count", 0) or 0),
            "warning_count": int(row.get("warning_count", 0) or 0),
            "errors": string_list(row.get("errors", [])),
        }
        for row in runs
        if not bool(row.get("ok", False))
    ]
    return {
        "schema_version": HISTORY_RECORD_SCHEMA_VERSION,
        "recorded_at": recorded_at,
        "health_schema_version": str(payload.get("schema_version", "")),
        "ok": bool(payload.get("ok", False)),
        "selection": payload.get("selection", {}),
        "totals": payload.get("totals", {}),
        "failed_runs": failed_runs,
    }


def build_run_artifact_health_history(
    *,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    history_path: Path | None = None,
    limit: int = 10,
    created_at_from: str = "",
) -> dict[str, Any]:
    """Return aggregate trends from artifact-health history records."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    active_history_path = (
        resolve_path(history_path, repo_root)
        if history_path is not None
        else experiments_dir / DEFAULT_HISTORY_FILENAME
    )
    records, read_errors = read_history_records(active_history_path)
    created_at_by_run = index_created_at_by_run(experiments_dir)
    artifact_counts: dict[str, dict[str, Any]] = {}
    run_counts: dict[str, dict[str, Any]] = {}
    recent_records = records[-max(limit, 0) :]
    scoped_failed_runs_by_record = [
        scoped_failed_runs_from_record(
            record=record,
            created_at_by_run=created_at_by_run,
            created_at_from=created_at_from,
        )
        for record in records
    ]

    for scoped_failed_runs in scoped_failed_runs_by_record:
        for failed_run in scoped_failed_runs:
            run_id = str(failed_run.get("run_id", ""))
            run_entry = run_counts.setdefault(
                run_id,
                {
                    "run_id": run_id,
                    "kind": str(failed_run.get("kind", "unknown")),
                    "failure_count": 0,
                    "total_error_count": 0,
                    "latest_errors": [],
                },
            )
            run_entry["failure_count"] += 1
            run_entry["total_error_count"] += int(failed_run.get("error_count", 0) or 0)
            run_entry["latest_errors"] = string_list(failed_run.get("errors", []))

            for error in string_list(failed_run.get("errors", [])):
                artifact_name = artifact_name_from_error(error)
                artifact_entry = artifact_counts.setdefault(
                    artifact_name,
                    {
                        "artifact_name": artifact_name,
                        "failure_count": 0,
                        "run_ids": [],
                    },
                )
                artifact_entry["failure_count"] += 1
                if run_id and run_id not in artifact_entry["run_ids"]:
                    artifact_entry["run_ids"].append(run_id)

    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "repo_root": str(repo_root),
        "experiments_dir": str(experiments_dir),
        "history_path": str(active_history_path),
        "scope": {
            "created_at_from": created_at_from,
            "failed_runs_without_index_created_at_excluded": bool(created_at_from),
        },
        "ok": not read_errors,
        "record_count": len(records),
        "read_errors": read_errors,
        "totals": {
            "record_count": len(records),
            "records_with_failures": sum(
                1 for scoped_failed_runs in scoped_failed_runs_by_record if scoped_failed_runs
            ),
            "failed_run_observation_count": sum(
                len(scoped_failed_runs)
                for scoped_failed_runs in scoped_failed_runs_by_record
            ),
            "artifact_failure_count": sum(
                int(row["failure_count"]) for row in artifact_counts.values()
            ),
            "read_error_count": len(read_errors),
        },
        "run_failures": sorted_rows(run_counts.values(), key_name="run_id"),
        "artifact_failures": sorted_rows(
            artifact_counts.values(),
            key_name="artifact_name",
        ),
        "recent_records": [
            history_record_summary(
                record,
                created_at_by_run=created_at_by_run,
                created_at_from=created_at_from,
            )
            for record in recent_records
        ],
        "policy": {
            "inspection_only": True,
            "reads_history_only": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
        },
    }


def read_history_records(history_path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Read JSONL history records and return records plus read errors."""
    if not history_path.exists():
        return [], []
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    with history_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{history_path}:{line_number}: invalid JSONL: {exc}")
                continue
            if not isinstance(payload, dict):
                errors.append(f"{history_path}:{line_number}: record must be an object")
                continue
            records.append(payload)
    return records, errors


def failed_runs_from_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Return failed run rows from one history record."""
    rows = record.get("failed_runs", [])
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def scoped_failed_runs_from_record(
    *,
    record: dict[str, Any],
    created_at_by_run: dict[str, str],
    created_at_from: str,
) -> list[dict[str, Any]]:
    """Return failed run rows inside the requested indexed time scope."""
    failed_runs = failed_runs_from_record(record)
    if not created_at_from:
        return failed_runs
    return [
        row
        for row in failed_runs
        if created_at_by_run.get(str(row.get("run_id", "")), "") >= created_at_from
    ]


def scoped_run_ids(
    *,
    run_ids: list[str],
    created_at_by_run: dict[str, str],
    created_at_from: str,
) -> list[str]:
    """Return selected run ids inside the requested indexed time scope."""
    if not created_at_from:
        return run_ids
    return [
        run_id
        for run_id in run_ids
        if created_at_by_run.get(run_id, "") >= created_at_from
    ]


def index_created_at_by_run(experiments_dir: Path) -> dict[str, str]:
    """Return indexed created_at timestamps by run id."""
    return {
        str(record.get("run_id", "")): str(record.get("created_at", ""))
        for record in read_experiment_index(experiments_dir)
        if record.get("run_id")
    }


def history_record_summary(
    record: dict[str, Any],
    *,
    created_at_by_run: dict[str, str] | None = None,
    created_at_from: str = "",
) -> dict[str, Any]:
    """Return a compact summary for one history record."""
    active_created_at_by_run = created_at_by_run or {}
    failed_runs = scoped_failed_runs_from_record(
        record=record,
        created_at_by_run=active_created_at_by_run,
        created_at_from=created_at_from,
    )
    totals = record.get("totals", {})
    totals_data = totals if isinstance(totals, dict) else {}
    selection = record.get("selection", {})
    selection_data = selection if isinstance(selection, dict) else {}
    selected_run_ids = scoped_run_ids(
        run_ids=string_list(selection_data.get("selected_run_ids", [])),
        created_at_by_run=active_created_at_by_run,
        created_at_from=created_at_from,
    )
    return {
        "recorded_at": str(record.get("recorded_at", "")),
        "ok": not failed_runs and not bool(record.get("read_error", False)),
        "run_count": (
            len(selected_run_ids)
            if created_at_from
            else int(totals_data.get("run_count", 0) or 0)
        ),
        "failed_count": (
            len(failed_runs)
            if created_at_from
            else int(totals_data.get("failed_count", 0) or 0)
        ),
        "error_count": (
            sum(int(row.get("error_count", 0) or 0) for row in failed_runs)
            if created_at_from
            else int(totals_data.get("error_count", 0) or 0)
        ),
        "selected_run_ids": selected_run_ids,
        "failed_run_ids": [str(row.get("run_id", "")) for row in failed_runs],
    }


def artifact_name_from_error(error: str) -> str:
    """Extract a likely artifact filename from an error string."""
    suffixes = (".json", ".jsonl", ".md", ".csv", ".html", ".diff")
    for raw_token in error.replace(":", " ").split():
        token = raw_token.strip(" ,.;()[]{}'\"")
        if token.endswith(suffixes):
            return Path(token).name
    return "unknown"


def sorted_rows(rows: Any, *, key_name: str) -> list[dict[str, Any]]:
    """Return rows sorted by failure count descending, then stable key."""
    result = [dict(row) for row in rows]
    result.sort(
        key=lambda row: (
            -int(row.get("failure_count", 0) or 0),
            str(row.get(key_name, "")),
        )
    )
    return result


def utc_timestamp() -> str:
    """Return a stable UTC timestamp string."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def validate_run_artifact_health_history_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved run artifact health history summary."""
    return validate_json_file(
        payload_path=payload_path,
        schema_path=repo_root / HISTORY_SCHEMA_PATH,
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
    parser.add_argument(
        "--created-at-from",
        default="",
        help="Only select indexed runs created at or after this UTC timestamp.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--record-history", action="store_true")
    parser.add_argument("--history-summary", action="store_true")
    parser.add_argument("--history-path", type=Path)
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render history summaries as markdown.",
    )
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    history_path = args.history_path or args.experiments_dir / DEFAULT_HISTORY_FILENAME
    if args.history_summary:
        payload = build_run_artifact_health_history(
            experiments_dir=args.experiments_dir,
            repo_root=args.repo_root,
            history_path=history_path,
            limit=args.limit,
            created_at_from=args.created_at_from,
        )
    elif args.output is not None:
        payload = write_run_artifact_health(
            output_path=args.output,
            experiments_dir=args.experiments_dir,
            repo_root=args.repo_root,
            limit=args.limit,
            all_runs=args.all_runs,
            run_ids=args.run_ids,
            created_at_from=args.created_at_from,
        )
    else:
        payload = build_run_artifact_health(
            experiments_dir=args.experiments_dir,
            repo_root=args.repo_root,
            limit=args.limit,
            all_runs=args.all_runs,
            run_ids=args.run_ids,
            created_at_from=args.created_at_from,
        )
    if args.markdown and args.history_summary:
        print(render_run_artifact_health_history_markdown(payload), end="")
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    if args.record_history and not args.history_summary:
        append_run_artifact_health_history(
            payload=payload,
            history_path=resolve_path(history_path, args.repo_root.resolve()),
        )
    if args.strict and not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
