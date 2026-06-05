"""Read-only diagnostics across proposal memory and artifact health history."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.experiment_index import read_experiment_index
from orchestrator.outcome_memory import read_outcome_memory
from orchestrator.run_artifact_health import (
    DEFAULT_HISTORY_FILENAME,
    artifact_name_from_error,
    failed_runs_from_record,
    read_history_records,
    resolve_path,
    string_list,
)
from orchestrator.schema_validation import (
    load_schema,
    validate_json_file,
    validate_json_payload,
)


SCHEMA_VERSION = "memory_diagnostics_v1"
SCHEMA_PATH = Path("schemas/memory_diagnostics.schema.json")


def build_memory_diagnostics(
    *,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    history_path: Path | None = None,
    limit: int = 20,
    created_at_from: str = "",
) -> dict[str, Any]:
    """Return deterministic read-only diagnostics for saved memory artifacts."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    active_history_path = (
        resolve_path(history_path, repo_root)
        if history_path is not None
        else experiments_dir / DEFAULT_HISTORY_FILENAME
    )
    outcome_records = [
        record
        for record in read_outcome_memory(experiments_dir)
        if record.get("kind", "proposal_outcome") == "proposal_outcome"
        and record_matches_created_at_filter(
            record=record,
            created_at_from=created_at_from,
        )
    ]
    history_records, health_read_errors = read_history_records(active_history_path)
    created_at_by_run = index_created_at_by_run(experiments_dir)
    health_by_run = {
        run_id: row
        for run_id, row in artifact_health_by_run(history_records).items()
        if run_matches_created_at_filter(
            run_id=run_id,
            created_at_by_run=created_at_by_run,
            created_at_from=created_at_from,
        )
    }
    outcome_run_ids = {
        str(record.get("run_id", ""))
        for record in outcome_records
        if str(record.get("run_id", ""))
    }
    failed_health_run_ids = sorted(
        run_id for run_id, row in health_by_run.items() if row["failure_count"] > 0
    )
    matched_failed_run_ids = [
        run_id for run_id in failed_health_run_ids if run_id in outcome_run_ids
    ]

    groups = {
        "by_agent": aggregate_groups(
            outcome_records=outcome_records,
            health_by_run=health_by_run,
            key_field="agent_name",
            missing_label="unknown_agent",
        ),
        "by_profile": aggregate_groups(
            outcome_records=outcome_records,
            health_by_run=health_by_run,
            key_field="profile_name",
            missing_label="unknown_profile",
        ),
        "by_direction": aggregate_groups(
            outcome_records=outcome_records,
            health_by_run=health_by_run,
            key_field="direction_tag",
            missing_label="unknown_direction",
        ),
        "by_patch": aggregate_groups(
            outcome_records=outcome_records,
            health_by_run=health_by_run,
            key_field="patch_sha256",
            missing_label="unknown_patch",
        ),
    }
    recent_links = recent_outcome_health_links(
        outcome_records=outcome_records,
        health_by_run=health_by_run,
        limit=limit,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "repo_root": str(repo_root),
        "experiments_dir": str(experiments_dir),
        "memory_path": str(experiments_dir / "memory.jsonl"),
        "health_history_path": str(active_history_path),
        "scope": {
            "created_at_from": created_at_from,
            "health_runs_without_index_created_at_excluded": bool(created_at_from),
        },
        "ok": not health_read_errors,
        "read_errors": health_read_errors,
        "totals": {
            "outcome_record_count": len(outcome_records),
            "health_history_record_count": len(history_records),
            "outcome_run_count": len(outcome_run_ids),
            "failed_health_run_count": len(failed_health_run_ids),
            "matched_failed_health_run_count": len(matched_failed_run_ids),
            "unmatched_failed_health_run_count": (
                len(failed_health_run_ids) - len(matched_failed_run_ids)
            ),
            "read_error_count": len(health_read_errors),
        },
        "matched_failed_run_ids": matched_failed_run_ids,
        "unmatched_failed_health_run_ids": [
            run_id for run_id in failed_health_run_ids if run_id not in outcome_run_ids
        ],
        "groups": groups,
        "recent_outcome_health_links": recent_links,
        "policy": {
            "inspection_only": True,
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


def artifact_health_by_run(
    history_records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return aggregate artifact health failures keyed by run id."""
    rows: dict[str, dict[str, Any]] = {}
    for record in history_records:
        for failed_run in failed_runs_from_record(record):
            run_id = str(failed_run.get("run_id", ""))
            if not run_id:
                continue
            row = rows.setdefault(
                run_id,
                {
                    "run_id": run_id,
                    "kind": str(failed_run.get("kind", "unknown")),
                    "failure_count": 0,
                    "total_error_count": 0,
                    "artifact_names": [],
                    "latest_errors": [],
                },
            )
            row["failure_count"] += 1
            row["total_error_count"] += int(failed_run.get("error_count", 0) or 0)
            errors = string_list(failed_run.get("errors", []))
            row["latest_errors"] = errors
            for error in errors:
                artifact_name = artifact_name_from_error(error)
                if artifact_name not in row["artifact_names"]:
                    row["artifact_names"].append(artifact_name)
    return rows


def index_created_at_by_run(experiments_dir: Path) -> dict[str, str]:
    """Return indexed created_at timestamps by run id."""
    return {
        str(record.get("run_id", "")): str(record.get("created_at", ""))
        for record in read_experiment_index(experiments_dir)
        if record.get("run_id")
    }


def record_matches_created_at_filter(
    *,
    record: dict[str, Any],
    created_at_from: str,
) -> bool:
    """Return whether a memory record is inside the requested time scope."""
    if not created_at_from:
        return True
    return str(record.get("created_at", "")) >= created_at_from


def run_matches_created_at_filter(
    *,
    run_id: str,
    created_at_by_run: dict[str, str],
    created_at_from: str,
) -> bool:
    """Return whether a run id is inside the requested indexed time scope."""
    if not created_at_from:
        return True
    return created_at_by_run.get(run_id, "") >= created_at_from


def aggregate_groups(
    *,
    outcome_records: list[dict[str, Any]],
    health_by_run: dict[str, dict[str, Any]],
    key_field: str,
    missing_label: str,
) -> list[dict[str, Any]]:
    """Aggregate outcome rows by one proposal metadata field."""
    groups: dict[str, dict[str, Any]] = {}
    for record in outcome_records:
        key = str(record.get(key_field, "") or missing_label)
        row = groups.setdefault(
            key,
            {
                "key": key,
                "record_count": 0,
                "accepted_count": 0,
                "rejected_count": 0,
                "applicable_count": 0,
                "repeat_patch_count": 0,
                "artifact_failed_run_observation_count": 0,
                "artifact_failed_run_ids": [],
                "artifact_failure_names": [],
                "avg_validation_ev_delta": 0.0,
                "_ev_delta_total": 0.0,
            },
        )
        row["record_count"] += 1
        if record.get("accepted") is True:
            row["accepted_count"] += 1
        else:
            row["rejected_count"] += 1
        if record.get("applicable") is True:
            row["applicable_count"] += 1
        if record.get("is_repeat_patch") is True:
            row["repeat_patch_count"] += 1
        row["_ev_delta_total"] += float(record.get("validation_ev_delta", 0.0) or 0.0)

        run_id = str(record.get("run_id", ""))
        health = health_by_run.get(run_id, {})
        if health:
            row["artifact_failed_run_observation_count"] += int(
                health.get("failure_count", 0) or 0
            )
            if run_id and run_id not in row["artifact_failed_run_ids"]:
                row["artifact_failed_run_ids"].append(run_id)
            for artifact_name in string_list(health.get("artifact_names", [])):
                if artifact_name not in row["artifact_failure_names"]:
                    row["artifact_failure_names"].append(artifact_name)

    rows: list[dict[str, Any]] = []
    for row in groups.values():
        record_count = int(row["record_count"])
        row["avg_validation_ev_delta"] = round(
            float(row.pop("_ev_delta_total")) / record_count if record_count else 0.0,
            6,
        )
        row["accept_rate"] = round(
            int(row["accepted_count"]) / record_count if record_count else 0.0,
            6,
        )
        row["artifact_failed_run_ids"] = sorted(row["artifact_failed_run_ids"])
        row["artifact_failure_names"] = sorted(row["artifact_failure_names"])
        rows.append(row)
    rows.sort(
        key=lambda row: (
            -int(row["artifact_failed_run_observation_count"]),
            -int(row["rejected_count"]),
            str(row["key"]),
        )
    )
    return rows


def recent_outcome_health_links(
    *,
    outcome_records: list[dict[str, Any]],
    health_by_run: dict[str, dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Return compact recent links between proposal outcomes and health failures."""
    links: list[dict[str, Any]] = []
    for record in outcome_records[-max(limit, 0) :]:
        run_id = str(record.get("run_id", ""))
        health = health_by_run.get(run_id, {})
        links.append(
            {
                "run_id": run_id,
                "round_id": str(record.get("round_id", "")),
                "agent_name": str(record.get("agent_name", "")),
                "profile_name": str(record.get("profile_name", "")),
                "direction_tag": str(record.get("direction_tag", "")),
                "patch_sha256": str(record.get("patch_sha256", "")),
                "accepted": bool(record.get("accepted", False)),
                "validation_ev_delta": float(
                    record.get("validation_ev_delta", 0.0) or 0.0
                ),
                "artifact_health_failed": bool(health),
                "artifact_failure_count": int(health.get("failure_count", 0) or 0),
                "artifact_error_count": int(health.get("total_error_count", 0) or 0),
                "artifact_failure_names": string_list(
                    health.get("artifact_names", []),
                ),
            }
        )
    return links


def write_memory_diagnostics(
    *,
    output_path: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    history_path: Path | None = None,
    limit: int = 20,
    created_at_from: str = "",
) -> dict[str, Any]:
    """Write a memory diagnostics report and validate its schema."""
    payload = build_memory_diagnostics(
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        history_path=history_path,
        limit=limit,
        created_at_from=created_at_from,
    )
    errors = validate_memory_diagnostics_payload(
        payload,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        history_path=history_path,
        limit=limit,
        created_at_from=created_at_from,
    )
    if errors:
        raise ValueError(f"memory diagnostics failed schema validation: {errors}")
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def render_memory_diagnostics_markdown(payload: dict[str, Any]) -> str:
    """Render memory diagnostics as compact terminal markdown."""
    def compact_list(values: list[str], *, max_items: int = 10) -> str:
        if not values:
            return "`none`"
        shown = values[:max_items]
        text = ", ".join(f"`{value}`" for value in shown)
        remaining = len(values) - len(shown)
        if remaining > 0:
            text += f", ... +{remaining} more"
        return text

    def top_rows(rows: object, *, max_items: int = 5) -> list[dict[str, Any]]:
        if not isinstance(rows, list):
            return []
        return [row for row in rows[:max_items] if isinstance(row, dict)]

    totals = payload.get("totals", {})
    if not isinstance(totals, dict):
        totals = {}
    scope = payload.get("scope", {})
    if not isinstance(scope, dict):
        scope = {}
    groups = payload.get("groups", {})
    if not isinstance(groups, dict):
        groups = {}
    recent_links = payload.get("recent_outcome_health_links", [])
    if not isinstance(recent_links, list):
        recent_links = []

    lines = [
        "# Memory Diagnostics",
        "",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Created at from: `{scope.get('created_at_from', '')}`",
        f"- Experiments dir: `{payload.get('experiments_dir', '')}`",
        f"- Memory path: `{payload.get('memory_path', '')}`",
        f"- Health history path: `{payload.get('health_history_path', '')}`",
        "",
        "## Totals",
        "",
        f"- Outcome records: `{totals.get('outcome_record_count', 0)}`",
        f"- Outcome runs: `{totals.get('outcome_run_count', 0)}`",
        "- Health history records: "
        f"`{totals.get('health_history_record_count', 0)}`",
        f"- Failed health runs: `{totals.get('failed_health_run_count', 0)}`",
        "- Matched failed health runs: "
        f"`{totals.get('matched_failed_health_run_count', 0)}`",
        "- Unmatched failed health runs: "
        f"`{totals.get('unmatched_failed_health_run_count', 0)}`",
        f"- Read errors: `{totals.get('read_error_count', 0)}`",
        "",
        "## Failed Health Runs",
        "",
        "- Matched to outcome memory: "
        + compact_list(string_list(payload.get("matched_failed_run_ids", []))),
        "- Unmatched in outcome memory: "
        + compact_list(
            string_list(payload.get("unmatched_failed_health_run_ids", []))
        ),
        "",
        "## Top Groups",
        "",
    ]
    for group_name, label in (
        ("by_direction", "Direction"),
        ("by_agent", "Agent"),
        ("by_profile", "Profile"),
        ("by_patch", "Patch"),
    ):
        lines.extend([f"### {label}", ""])
        rows = top_rows(groups.get(group_name, []))
        if not rows:
            lines.append("- none")
        for row in rows:
            lines.append(
                "- "
                f"`{row.get('key', '')}`: records `{row.get('record_count', 0)}`, "
                f"rejected `{row.get('rejected_count', 0)}`, "
                "failed observations "
                f"`{row.get('artifact_failed_run_observation_count', 0)}`"
            )
        lines.append("")

    lines.extend(["## Recent Links", ""])
    link_rows = [row for row in recent_links[:5] if isinstance(row, dict)]
    if not link_rows:
        lines.append("- none")
    for row in link_rows:
        lines.append(
            "- "
            f"`{row.get('run_id', '')}` "
            f"direction `{row.get('direction_tag', '')}` "
            f"accepted `{row.get('accepted', False)}` "
            f"health_failed `{row.get('artifact_health_failed', False)}` "
            f"errors `{row.get('artifact_error_count', 0)}`"
        )

    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This view is read-only and does not execute agents, run backtests, route agents, apply patches, delete memory, or change acceptance.",
            "- Use `--strict` when a nonzero exit is required for read errors.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_memory_diagnostics_payload(
    payload: dict[str, Any],
    *,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    history_path: Path | None = None,
    limit: int = 20,
    created_at_from: str = "",
) -> tuple[str, ...]:
    """Validate an in-memory memory diagnostics payload."""
    repo_root = repo_root.resolve()
    schema = load_schema(repo_root / SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=payload,
            schema=schema,
            schema_dir=(repo_root / SCHEMA_PATH).parent,
        )
    )
    errors.extend(
        validate_memory_diagnostics_consistency(
            payload,
            experiments_dir=experiments_dir,
            repo_root=repo_root,
            history_path=history_path,
            limit=limit,
            created_at_from=created_at_from,
        )
    )
    return tuple(errors)


def validate_memory_diagnostics_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved memory diagnostics report."""
    return validate_json_file(
        payload_path=payload_path,
        schema_path=repo_root / SCHEMA_PATH,
    )


def validate_memory_diagnostics_consistency(
    payload: dict[str, Any],
    *,
    experiments_dir: Path,
    repo_root: Path,
    history_path: Path | None,
    limit: int,
    created_at_from: str,
) -> tuple[str, ...]:
    """Validate that diagnostics output matches current source artifacts."""
    expected = build_memory_diagnostics(
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        history_path=history_path,
        limit=limit,
        created_at_from=created_at_from,
    )
    if payload != expected:
        return ("memory_diagnostics current evidence mismatch",)
    return ()


def main() -> None:
    """CLI entrypoint for memory diagnostics."""
    parser = argparse.ArgumentParser(
        description="Inspect proposal outcome memory against artifact health history.",
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
        help="Only inspect records created at or after this UTC timestamp.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render memory diagnostics as markdown.",
    )
    args = parser.parse_args()

    if args.output is not None:
        payload = write_memory_diagnostics(
            output_path=args.output,
            experiments_dir=args.experiments_dir,
            repo_root=args.repo_root,
            history_path=args.history_path,
            limit=args.limit,
            created_at_from=args.created_at_from,
        )
    else:
        payload = build_memory_diagnostics(
            experiments_dir=args.experiments_dir,
            repo_root=args.repo_root,
            history_path=args.history_path,
            limit=args.limit,
            created_at_from=args.created_at_from,
        )
        errors = validate_memory_diagnostics_payload(
            payload,
            experiments_dir=args.experiments_dir,
            repo_root=args.repo_root,
            history_path=args.history_path,
            limit=args.limit,
            created_at_from=args.created_at_from,
        )
        if errors:
            raise ValueError(f"memory diagnostics failed schema validation: {errors}")
    if args.markdown:
        print(render_memory_diagnostics_markdown(payload), end="")
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    if args.strict and not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
