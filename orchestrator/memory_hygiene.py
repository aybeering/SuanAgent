"""Read-only outcome memory hygiene report."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from orchestrator.outcome_memory import read_outcome_memory, scoped_outcome_memory
from orchestrator.schema_validation import (
    load_schema,
    validate_json_file,
    validate_json_payload,
)


SCHEMA_VERSION = "memory_hygiene_v1"
SCHEMA_PATH = Path("schemas/memory_hygiene.schema.json")


def build_memory_hygiene(
    *,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    failed_patch_threshold: int = 2,
    failed_direction_threshold: int = 3,
    created_at_from: str = "",
    recent_record_limit: int = 0,
    exclude_run_id: str = "",
) -> dict[str, Any]:
    """Return a deterministic hygiene report for append-only outcome memory."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    all_records = [
        record
        for record in read_outcome_memory(experiments_dir)
        if record.get("kind", "proposal_outcome") == "proposal_outcome"
    ]
    scoped_records = [
        record
        for record in scoped_outcome_memory(
            experiments_dir=experiments_dir,
            exclude_run_id=exclude_run_id,
            created_at_from=created_at_from,
            recent_record_limit=recent_record_limit,
        )
        if record.get("kind", "proposal_outcome") == "proposal_outcome"
    ]
    pre_recent_records = [
        record
        for record in all_records
        if str(record.get("run_id", "")) != exclude_run_id
        and (
            not created_at_from
            or str(record.get("created_at", "")) >= created_at_from
        )
    ]
    ignored_by_created_at = [
        record
        for record in all_records
        if created_at_from and str(record.get("created_at", "")) < created_at_from
    ]
    ignored_by_excluded_run = [
        record
        for record in all_records
        if exclude_run_id and str(record.get("run_id", "")) == exclude_run_id
    ]
    ignored_by_recent_limit = max(len(pre_recent_records) - len(scoped_records), 0)

    patch_rows = aggregate_patch_rows(
        total_records=all_records,
        scoped_records=scoped_records,
        threshold=failed_patch_threshold,
    )
    direction_rows = aggregate_direction_rows(
        total_records=all_records,
        scoped_records=scoped_records,
        threshold=failed_direction_threshold,
    )
    active_failures = [
        record for record in scoped_records if record.get("accepted") is False
    ]
    active_accepts = [
        record for record in scoped_records if record.get("accepted") is True
    ]
    overblocked_patch_rows = [
        row
        for row in patch_rows
        if row["would_reject"] and row["active_failed_count"] == row["total_failed_count"]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "repo_root": str(repo_root),
        "experiments_dir": str(experiments_dir),
        "memory_path": str(experiments_dir / "memory.jsonl"),
        "scope": {
            "created_at_from": created_at_from,
            "recent_record_limit": recent_record_limit,
            "exclude_run_id": exclude_run_id,
            "uses_full_history": not created_at_from and recent_record_limit <= 0,
        },
        "thresholds": {
            "failed_patch_threshold": failed_patch_threshold,
            "failed_direction_threshold": failed_direction_threshold,
        },
        "totals": {
            "total_record_count": len(all_records),
            "active_record_count": len(scoped_records),
            "active_failed_count": len(active_failures),
            "active_accepted_count": len(active_accepts),
            "ignored_by_created_at_count": len(ignored_by_created_at),
            "ignored_by_recent_limit_count": ignored_by_recent_limit,
            "ignored_by_excluded_run_count": len(ignored_by_excluded_run),
            "patch_block_count": sum(1 for row in patch_rows if row["would_reject"]),
            "direction_block_count": sum(
                1 for row in direction_rows if row["would_reject"]
            ),
            "overblocked_patch_count": len(overblocked_patch_rows),
        },
        "top_blocked_patches": patch_rows[:20],
        "top_blocked_directions": direction_rows[:20],
        "recommendations": recommendations(
            patch_rows=patch_rows,
            direction_rows=direction_rows,
            created_at_from=created_at_from,
            recent_record_limit=recent_record_limit,
        ),
        "policy": {
            "inspection_only": True,
            "reads_outcome_memory_only": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_apply_patches": True,
            "does_not_route_agents": True,
            "does_not_change_acceptance": True,
            "does_not_delete_memory": True,
        },
    }


def write_memory_hygiene(
    *,
    output_path: Path,
    markdown_path: Path | None = None,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    failed_patch_threshold: int = 2,
    failed_direction_threshold: int = 3,
    created_at_from: str = "",
    recent_record_limit: int = 0,
    exclude_run_id: str = "",
) -> dict[str, Any]:
    """Write memory hygiene JSON and optional markdown artifacts."""
    payload = build_memory_hygiene(
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        failed_patch_threshold=failed_patch_threshold,
        failed_direction_threshold=failed_direction_threshold,
        created_at_from=created_at_from,
        recent_record_limit=recent_record_limit,
        exclude_run_id=exclude_run_id,
    )
    errors = validate_memory_hygiene_payload(
        payload,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        failed_patch_threshold=failed_patch_threshold,
        failed_direction_threshold=failed_direction_threshold,
        created_at_from=created_at_from,
        recent_record_limit=recent_record_limit,
        exclude_run_id=exclude_run_id,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(f"memory hygiene failed schema validation: {errors}")
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if markdown_path is not None:
        markdown_path.write_text(render_memory_hygiene_markdown(payload), encoding="utf-8")
    return payload


def aggregate_patch_rows(
    *,
    total_records: list[dict[str, Any]],
    scoped_records: list[dict[str, Any]],
    threshold: int,
) -> list[dict[str, Any]]:
    """Return patch-level memory hygiene rows."""
    return aggregate_key_rows(
        key_field="patch_sha256",
        label_field="patch_sha256",
        total_records=total_records,
        scoped_records=scoped_records,
        threshold=threshold,
    )


def aggregate_direction_rows(
    *,
    total_records: list[dict[str, Any]],
    scoped_records: list[dict[str, Any]],
    threshold: int,
) -> list[dict[str, Any]]:
    """Return direction-level memory hygiene rows."""
    return aggregate_key_rows(
        key_field="direction_tag",
        label_field="direction_tag",
        total_records=total_records,
        scoped_records=scoped_records,
        threshold=threshold,
    )


def aggregate_key_rows(
    *,
    key_field: str,
    label_field: str,
    total_records: list[dict[str, Any]],
    scoped_records: list[dict[str, Any]],
    threshold: int,
) -> list[dict[str, Any]]:
    """Aggregate active and total memory counts for one key."""
    keys = sorted(
        {
            str(record.get(key_field, ""))
            for record in total_records + scoped_records
            if str(record.get(key_field, ""))
        }
    )
    rows: list[dict[str, Any]] = []
    for key in keys:
        total_for_key = [record for record in total_records if record.get(key_field) == key]
        active_for_key = [
            record for record in scoped_records if record.get(key_field) == key
        ]
        total_failed = [
            record for record in total_for_key if record.get("accepted") is False
        ]
        active_failed = [
            record for record in active_for_key if record.get("accepted") is False
        ]
        if not total_for_key and not active_for_key:
            continue
        direction_counts = Counter(
            str(record.get("direction_tag", ""))
            for record in active_for_key
            if str(record.get("direction_tag", ""))
        )
        agent_counts = Counter(
            str(record.get("agent_name", ""))
            for record in active_for_key
            if str(record.get("agent_name", ""))
        )
        rows.append(
            {
                "key": key,
                label_field: key,
                "short_key": key[:12],
                "active_record_count": len(active_for_key),
                "total_record_count": len(total_for_key),
                "active_failed_count": len(active_failed),
                "total_failed_count": len(total_failed),
                "active_accepted_count": sum(
                    1 for record in active_for_key if record.get("accepted") is True
                ),
                "would_reject": bool(threshold > 0 and len(active_failed) >= threshold),
                "threshold": threshold,
                "last_created_at": max(
                    [str(record.get("created_at", "")) for record in active_for_key]
                    or [""]
                ),
                "run_ids": sorted(
                    {
                        str(record.get("run_id", ""))
                        for record in active_for_key
                        if str(record.get("run_id", ""))
                    }
                ),
                "top_direction": top_counter_key(direction_counts),
                "top_agent": top_counter_key(agent_counts),
            }
        )
    rows.sort(
        key=lambda row: (
            not bool(row["would_reject"]),
            -int(row["active_failed_count"]),
            str(row["key"]),
        )
    )
    return rows


def recommendations(
    *,
    patch_rows: list[dict[str, Any]],
    direction_rows: list[dict[str, Any]],
    created_at_from: str,
    recent_record_limit: int,
) -> list[dict[str, str]]:
    """Return deterministic operator-facing hygiene suggestions."""
    rows: list[dict[str, str]] = []
    if not created_at_from and recent_record_limit <= 0:
        rows.append(
            {
                "code": "consider_memory_scope",
                "message": (
                    "memory filter currently uses full history; consider "
                    "created_at_from or recent_record_limit for generation scope"
                ),
            }
        )
    if sum(1 for row in patch_rows if row["would_reject"]) >= 3:
        rows.append(
            {
                "code": "many_patch_blocks",
                "message": "multiple patch families are blocked by active memory",
            }
        )
    if sum(1 for row in direction_rows if row["would_reject"]) >= 1:
        rows.append(
            {
                "code": "direction_block_active",
                "message": "one or more proposal directions are blocked by memory",
            }
        )
    if not rows:
        rows.append({"code": "memory_scope_ok", "message": "memory scope has no hygiene warnings"})
    return rows


def render_memory_hygiene_markdown(payload: dict[str, Any]) -> str:
    """Render a compact markdown summary."""
    totals = dict(payload.get("totals", {}))
    scope = dict(payload.get("scope", {}))
    lines = [
        "# Memory Hygiene",
        "",
        f"- Active records: `{totals.get('active_record_count', 0)}`",
        f"- Total records: `{totals.get('total_record_count', 0)}`",
        f"- Patch blocks: `{totals.get('patch_block_count', 0)}`",
        f"- Direction blocks: `{totals.get('direction_block_count', 0)}`",
        f"- Created-at scope: `{scope.get('created_at_from', '') or 'full history'}`",
        f"- Recent record limit: `{scope.get('recent_record_limit', 0)}`",
        "",
        "## Recommendations",
        "",
    ]
    for row in list_of_dicts(payload.get("recommendations", [])):
        lines.append(f"- `{row.get('code', '')}`: {row.get('message', '')}")
    lines.extend(["", "## Top Blocked Patches", ""])
    lines.extend(render_rows_table(payload.get("top_blocked_patches", [])))
    lines.extend(["", "## Top Blocked Directions", ""])
    lines.extend(render_rows_table(payload.get("top_blocked_directions", [])))
    lines.extend(
        [
            "",
            "This artifact is inspection-only and never deletes memory or changes acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def render_rows_table(value: object) -> list[str]:
    """Return a markdown table for memory hygiene rows."""
    lines = [
        "| Key | Active failed | Total failed | Threshold | Would reject | Last seen |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ]
    rows = list_of_dicts(value)
    if not rows:
        lines.append("| none | 0 | 0 | 0 | false | - |")
        return lines
    for row in rows[:10]:
        lines.append(
            "| "
            f"{row.get('short_key', '') or row.get('key', '')} | "
            f"{row.get('active_failed_count', 0)} | "
            f"{row.get('total_failed_count', 0)} | "
            f"{row.get('threshold', 0)} | "
            f"{str(bool(row.get('would_reject', False))).lower()} | "
            f"{row.get('last_created_at', '') or '-'} |"
        )
    return lines


def validate_memory_hygiene_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved memory hygiene report."""
    return validate_json_file(
        payload_path=payload_path,
        schema_path=repo_root / SCHEMA_PATH,
    )


def validate_memory_hygiene_payload(
    payload: dict[str, Any],
    *,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    failed_patch_threshold: int = 2,
    failed_direction_threshold: int = 3,
    created_at_from: str = "",
    recent_record_limit: int = 0,
    exclude_run_id: str = "",
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an in-memory memory hygiene payload."""
    repo_root = repo_root.resolve()
    normalized = dict(payload)
    normalized.pop("from_artifact", None)
    schema = load_schema(repo_root / SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=normalized,
            schema=schema,
            schema_dir=(repo_root / SCHEMA_PATH).parent,
        )
    )
    errors.extend(validate_memory_hygiene_consistency(normalized))
    if require_current_evidence:
        expected = build_memory_hygiene(
            experiments_dir=experiments_dir,
            repo_root=repo_root,
            failed_patch_threshold=failed_patch_threshold,
            failed_direction_threshold=failed_direction_threshold,
            created_at_from=created_at_from,
            recent_record_limit=recent_record_limit,
            exclude_run_id=exclude_run_id,
        )
        if normalized != expected:
            errors.append("memory_hygiene current evidence mismatch")
    return tuple(errors)


def validate_memory_hygiene_consistency(payload: dict[str, Any]) -> tuple[str, ...]:
    """Return stable internal consistency errors for a saved hygiene report."""
    errors: list[str] = []
    scope = object_value(payload.get("scope", {}))
    thresholds = object_value(payload.get("thresholds", {}))
    totals = object_value(payload.get("totals", {}))
    patch_rows = list_of_dicts(payload.get("top_blocked_patches", []))
    direction_rows = list_of_dicts(payload.get("top_blocked_directions", []))
    if bool(scope.get("uses_full_history", False)) != (
        not str(scope.get("created_at_from", ""))
        and int(scope.get("recent_record_limit", 0) or 0) <= 0
    ):
        errors.append("memory_hygiene consistency mismatch: uses_full_history")
    if int(totals.get("active_record_count", 0) or 0) != (
        int(totals.get("active_failed_count", 0) or 0)
        + int(totals.get("active_accepted_count", 0) or 0)
    ):
        errors.append("memory_hygiene consistency mismatch: active totals")
    for field in (
        "active_record_count",
        "active_failed_count",
        "active_accepted_count",
        "ignored_by_created_at_count",
        "ignored_by_recent_limit_count",
        "ignored_by_excluded_run_count",
        "patch_block_count",
        "direction_block_count",
        "overblocked_patch_count",
    ):
        if int(totals.get(field, 0) or 0) < 0:
            errors.append(f"memory_hygiene consistency mismatch: negative {field}")
    validate_hygiene_rows_consistency(
        rows=patch_rows,
        label_field="patch_sha256",
        threshold=int(thresholds.get("failed_patch_threshold", 0) or 0),
        artifact_label="patch",
        errors=errors,
    )
    validate_hygiene_rows_consistency(
        rows=direction_rows,
        label_field="direction_tag",
        threshold=int(thresholds.get("failed_direction_threshold", 0) or 0),
        artifact_label="direction",
        errors=errors,
    )
    visible_patch_blocks = sum(1 for row in patch_rows if bool(row.get("would_reject")))
    visible_direction_blocks = sum(
        1 for row in direction_rows if bool(row.get("would_reject"))
    )
    visible_overblocked = sum(
        1
        for row in patch_rows
        if bool(row.get("would_reject"))
        and int(row.get("active_failed_count", 0) or 0)
        == int(row.get("total_failed_count", 0) or 0)
    )
    if int(totals.get("patch_block_count", 0) or 0) < visible_patch_blocks:
        errors.append("memory_hygiene consistency mismatch: patch_block_count")
    if int(totals.get("direction_block_count", 0) or 0) < visible_direction_blocks:
        errors.append("memory_hygiene consistency mismatch: direction_block_count")
    if int(totals.get("overblocked_patch_count", 0) or 0) < visible_overblocked:
        errors.append("memory_hygiene consistency mismatch: overblocked_patch_count")
    expected_recommendations = recommendations(
        patch_rows=patch_rows,
        direction_rows=direction_rows,
        created_at_from=str(scope.get("created_at_from", "")),
        recent_record_limit=int(scope.get("recent_record_limit", 0) or 0),
    )
    if list_of_dicts(payload.get("recommendations", [])) != expected_recommendations:
        errors.append("memory_hygiene consistency mismatch: recommendations")
    return tuple(errors)


def validate_hygiene_rows_consistency(
    *,
    rows: list[dict[str, Any]],
    label_field: str,
    threshold: int,
    artifact_label: str,
    errors: list[str],
) -> None:
    """Append consistency errors for saved patch or direction hygiene rows."""
    for index, row in enumerate(rows, start=1):
        key = str(row.get("key", ""))
        if str(row.get(label_field, "")) != key:
            errors.append(
                f"memory_hygiene consistency mismatch: {artifact_label} row label {index}"
            )
        if str(row.get("short_key", "")) != key[:12]:
            errors.append(
                f"memory_hygiene consistency mismatch: {artifact_label} short_key {index}"
            )
        active_records = int(row.get("active_record_count", 0) or 0)
        total_records = int(row.get("total_record_count", 0) or 0)
        active_failed = int(row.get("active_failed_count", 0) or 0)
        total_failed = int(row.get("total_failed_count", 0) or 0)
        active_accepted = int(row.get("active_accepted_count", 0) or 0)
        if active_failed + active_accepted > active_records:
            errors.append(
                f"memory_hygiene consistency mismatch: {artifact_label} active counts {index}"
            )
        if active_records > total_records or total_failed > total_records:
            errors.append(
                f"memory_hygiene consistency mismatch: {artifact_label} total counts {index}"
            )
        if int(row.get("threshold", 0) or 0) != threshold:
            errors.append(
                f"memory_hygiene consistency mismatch: {artifact_label} threshold {index}"
            )
        if bool(row.get("would_reject", False)) != bool(
            threshold > 0 and active_failed >= threshold
        ):
            errors.append(
                f"memory_hygiene consistency mismatch: {artifact_label} would_reject {index}"
            )
        if label_field == "direction_tag" and active_records > 0 and str(
            row.get("top_direction", "")
        ) != key:
            errors.append(
                f"memory_hygiene consistency mismatch: {artifact_label} top_direction {index}"
            )


def top_counter_key(counter: Counter[str]) -> str:
    """Return the most frequent key with deterministic tie-breaks."""
    if not counter:
        return ""
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def list_of_dicts(value: object) -> list[dict[str, Any]]:
    """Return dictionary rows from a list-like value."""
    if not isinstance(value, list | tuple):
        return []
    return [row for row in value if isinstance(row, dict)]


def object_value(value: object) -> dict[str, Any]:
    """Return a dictionary value or an empty object."""
    return value if isinstance(value, dict) else {}


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root."""
    return path if path.is_absolute() else repo_root / path


def main() -> None:
    """CLI entrypoint for memory hygiene reports."""
    parser = argparse.ArgumentParser(description="Inspect outcome memory hygiene.")
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--failed-patch-threshold", type=int, default=2)
    parser.add_argument("--failed-direction-threshold", type=int, default=3)
    parser.add_argument("--created-at-from", default="")
    parser.add_argument("--recent-record-limit", type=int, default=0)
    parser.add_argument("--exclude-run-id", default="")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()

    if args.output is not None:
        payload = write_memory_hygiene(
            output_path=args.output,
            markdown_path=args.markdown_output,
            experiments_dir=args.experiments_dir,
            repo_root=args.repo_root,
            failed_patch_threshold=args.failed_patch_threshold,
            failed_direction_threshold=args.failed_direction_threshold,
            created_at_from=args.created_at_from,
            recent_record_limit=args.recent_record_limit,
            exclude_run_id=args.exclude_run_id,
        )
    else:
        payload = build_memory_hygiene(
            experiments_dir=args.experiments_dir,
            repo_root=args.repo_root,
            failed_patch_threshold=args.failed_patch_threshold,
            failed_direction_threshold=args.failed_direction_threshold,
            created_at_from=args.created_at_from,
            recent_record_limit=args.recent_record_limit,
            exclude_run_id=args.exclude_run_id,
        )
        errors = validate_memory_hygiene_payload(
            payload,
            experiments_dir=args.experiments_dir,
            repo_root=args.repo_root,
            failed_patch_threshold=args.failed_patch_threshold,
            failed_direction_threshold=args.failed_direction_threshold,
            created_at_from=args.created_at_from,
            recent_record_limit=args.recent_record_limit,
            exclude_run_id=args.exclude_run_id,
            require_current_evidence=True,
        )
        if errors:
            raise ValueError(f"memory hygiene failed schema validation: {errors}")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
