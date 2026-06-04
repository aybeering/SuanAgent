"""Read-only recommendation for outcome memory scope settings."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.memory_hygiene import build_memory_hygiene
from orchestrator.schema_validation import (
    load_schema,
    validate_json_file,
    validate_json_payload,
)


MEMORY_SCOPE_RECOMMENDATION_SCHEMA_VERSION = "memory_scope_recommendation_v1"
SCHEMA_PATH = Path("schemas/memory_scope_recommendation.schema.json")
DEFAULT_RECENT_RECORD_LIMIT = 100
HIGH_MEMORY_PRESSURE_RECORDS = 100
VERY_HIGH_MEMORY_PRESSURE_RECORDS = 250


def write_memory_scope_recommendation(
    *,
    run_dir: Path,
    repo_root: Path,
    experiments_dir: Path | None = None,
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown memory scope recommendation artifacts."""
    payload = build_memory_scope_recommendation(
        run_dir=run_dir,
        repo_root=repo_root,
        experiments_dir=experiments_dir,
    )
    errors = validate_memory_scope_recommendation_payload(
        payload,
        run_dir=run_dir,
        repo_root=repo_root,
        experiments_dir=experiments_dir,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "memory scope recommendation failed schema validation: "
            + "; ".join(errors)
        )
    json_path = run_dir / "memory_scope_recommendation.json"
    md_path = run_dir / "memory_scope_recommendation.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(
        render_memory_scope_recommendation_markdown(payload),
        encoding="utf-8",
    )
    return json_path, md_path, payload


def build_memory_scope_recommendation(
    *,
    run_dir: Path,
    repo_root: Path,
    experiments_dir: Path | None = None,
) -> dict[str, object]:
    """Return a deterministic recommendation from saved memory hygiene data."""
    repo_root = repo_root.resolve()
    run_dir = run_dir.resolve()
    active_experiments_dir = (
        experiments_dir.resolve()
        if experiments_dir is not None
        else run_dir.parent.resolve()
    )
    hygiene_path = run_dir / "memory_hygiene.json"
    if hygiene_path.exists():
        hygiene = load_json_object(hygiene_path)
        from_artifact = True
    else:
        manifest = load_json_object(run_dir / "manifest.json")
        memory_policy = object_value(manifest.get("memory_filter_policy", {}))
        hygiene = build_memory_hygiene(
            experiments_dir=active_experiments_dir,
            repo_root=repo_root,
            failed_patch_threshold=int(memory_policy.get("failed_patch_threshold", 2)),
            failed_direction_threshold=int(
                memory_policy.get("failed_direction_threshold", 3)
            ),
            created_at_from=str(memory_policy.get("created_at_from", "")),
            recent_record_limit=int(memory_policy.get("recent_record_limit", 0) or 0),
            exclude_run_id=run_dir.name,
        )
        from_artifact = False
    scope = object_value(hygiene.get("scope", {}))
    totals = object_value(hygiene.get("totals", {}))
    recommendation = recommendation_payload(scope=scope, totals=totals)
    return {
        "schema_version": MEMORY_SCOPE_RECOMMENDATION_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": relative_path(run_dir, repo_root),
        "source": file_record(hygiene_path, repo_root),
        "source_from_artifact": from_artifact,
        "current_scope": {
            "created_at_from": str(scope.get("created_at_from", "")),
            "recent_record_limit": int(scope.get("recent_record_limit", 0) or 0),
            "uses_full_history": bool(scope.get("uses_full_history", False)),
        },
        "observed_totals": {
            "total_record_count": int(totals.get("total_record_count", 0) or 0),
            "active_record_count": int(totals.get("active_record_count", 0) or 0),
            "active_failed_count": int(totals.get("active_failed_count", 0) or 0),
            "patch_block_count": int(totals.get("patch_block_count", 0) or 0),
            "direction_block_count": int(totals.get("direction_block_count", 0) or 0),
            "overblocked_patch_count": int(totals.get("overblocked_patch_count", 0) or 0),
        },
        "candidate_scopes": candidate_scope_rows(scope=scope, totals=totals),
        "recommendation": recommendation,
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "does_not_write_config": True,
            "does_not_delete_memory": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_route_candidates": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
        },
    }


def recommendation_payload(
    *,
    scope: dict[str, object],
    totals: dict[str, object],
) -> dict[str, object]:
    """Return the deterministic memory scope recommendation."""
    active_count = int(totals.get("active_record_count", 0) or 0)
    patch_blocks = int(totals.get("patch_block_count", 0) or 0)
    direction_blocks = int(totals.get("direction_block_count", 0) or 0)
    overblocked = int(totals.get("overblocked_patch_count", 0) or 0)
    recent_limit = int(scope.get("recent_record_limit", 0) or 0)
    created_at_from = str(scope.get("created_at_from", ""))
    uses_full_history = bool(scope.get("uses_full_history", False))
    reason_codes: list[str] = []
    if active_count >= VERY_HIGH_MEMORY_PRESSURE_RECORDS:
        reason_codes.append("very_large_active_memory")
    elif active_count >= HIGH_MEMORY_PRESSURE_RECORDS:
        reason_codes.append("large_active_memory")
    if patch_blocks:
        reason_codes.append("patch_block_active")
    if direction_blocks:
        reason_codes.append("direction_block_active")
    if overblocked:
        reason_codes.append("overblocked_patch_groups")

    should_limit = (
        uses_full_history
        and active_count >= HIGH_MEMORY_PRESSURE_RECORDS
        and bool(patch_blocks or direction_blocks or overblocked)
    )
    if should_limit:
        recommended_limit = DEFAULT_RECENT_RECORD_LIMIT
        return {
            "action": "set_recent_record_limit",
            "recommended_created_at_from": "",
            "recommended_recent_record_limit": recommended_limit,
            "reason_codes": reason_codes,
            "confidence": "medium" if active_count < VERY_HIGH_MEMORY_PRESSURE_RECORDS else "high",
            "would_change_current_config": recent_limit != recommended_limit
            or bool(created_at_from),
            "message": (
                "Outcome memory is using full history and active blocks are present; "
                "consider scoping future runs to the most recent records."
            ),
        }
    if created_at_from or recent_limit > 0:
        return {
            "action": "keep_current_scope",
            "recommended_created_at_from": created_at_from,
            "recommended_recent_record_limit": recent_limit,
            "reason_codes": reason_codes or ["scope_already_configured"],
            "confidence": "medium",
            "would_change_current_config": False,
            "message": "Outcome memory is already scoped; keep the current scope for now.",
        }
    return {
        "action": "keep_full_history",
        "recommended_created_at_from": "",
        "recommended_recent_record_limit": 0,
        "reason_codes": reason_codes or ["low_memory_pressure"],
        "confidence": "high",
        "would_change_current_config": False,
        "message": "Outcome memory pressure is low; full-history behavior is still acceptable.",
    }


def candidate_scope_rows(
    *,
    scope: dict[str, object],
    totals: dict[str, object],
) -> list[dict[str, object]]:
    """Return deterministic candidate scope rows for human review."""
    active_count = int(totals.get("active_record_count", 0) or 0)
    current_limit = int(scope.get("recent_record_limit", 0) or 0)
    current_created_at = str(scope.get("created_at_from", ""))
    rows = [
        {
            "label": "current",
            "created_at_from": current_created_at,
            "recent_record_limit": current_limit,
            "estimated_active_record_count": active_count,
            "note": "Current configured memory scope.",
        },
        {
            "label": "full_history",
            "created_at_from": "",
            "recent_record_limit": 0,
            "estimated_active_record_count": active_count,
            "note": "Default behavior; preserves every outcome memory record.",
        },
    ]
    for limit in (50, DEFAULT_RECENT_RECORD_LIMIT, 250):
        rows.append(
            {
                "label": f"recent_{limit}",
                "created_at_from": "",
                "recent_record_limit": limit,
                "estimated_active_record_count": min(active_count, limit),
                "note": "Candidate recent-record scope; advisory only.",
            }
        )
    unique: dict[tuple[str, int], dict[str, object]] = {}
    for row in rows:
        key = (str(row["created_at_from"]), int(row["recent_record_limit"]))
        unique.setdefault(key, row)
    return list(unique.values())


def render_memory_scope_recommendation_markdown(payload: dict[str, object]) -> str:
    """Render memory scope recommendation as markdown."""
    current = object_value(payload.get("current_scope", {}))
    observed = object_value(payload.get("observed_totals", {}))
    recommendation = object_value(payload.get("recommendation", {}))
    lines = [
        "# Memory Scope Recommendation",
        "",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Action: `{recommendation.get('action', '')}`",
        f"- Confidence: `{recommendation.get('confidence', '')}`",
        f"- Recommended recent limit: `{recommendation.get('recommended_recent_record_limit', 0)}`",
        f"- Recommended created_at_from: `{recommendation.get('recommended_created_at_from', '') or 'none'}`",
        f"- Would change config: `{recommendation.get('would_change_current_config', False)}`",
        f"- Active records: `{observed.get('active_record_count', 0)}`",
        f"- Patch blocks: `{observed.get('patch_block_count', 0)}`",
        f"- Direction blocks: `{observed.get('direction_block_count', 0)}`",
        f"- Current full history: `{current.get('uses_full_history', False)}`",
        "",
        "## Reason Codes",
        "",
    ]
    reasons = string_list(recommendation.get("reason_codes", []))
    if reasons:
        lines.extend(f"- `{reason}`" for reason in reasons)
    else:
        lines.append("- `none`")
    lines.extend(
        [
            "",
            "## Candidate Scopes",
            "",
            "| Label | Created At From | Recent Limit | Estimated Active Records |",
            "| --- | --- | ---: | ---: |",
        ]
    )
    for row in list_of_objects(payload.get("candidate_scopes", [])):
        lines.append(
            "| "
            f"{row.get('label', '')} | "
            f"{row.get('created_at_from', '') or '-'} | "
            f"{row.get('recent_record_limit', 0)} | "
            f"{row.get('estimated_active_record_count', 0)} |"
        )
    lines.extend(
        [
            "",
            "This artifact is advisory only and does not write config, delete memory, route candidates, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_memory_scope_recommendation_file(
    *,
    payload_path: Path,
    repo_root: Path,
) -> tuple[str, ...]:
    """Validate a saved memory scope recommendation report."""
    schema_path = repo_root / SCHEMA_PATH
    return tuple(validate_json_file(payload_path=payload_path, schema_path=schema_path))


def validate_memory_scope_recommendation_payload(
    payload: dict[str, object],
    *,
    run_dir: Path,
    repo_root: Path,
    experiments_dir: Path | None = None,
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an in-memory memory scope recommendation payload."""
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
    errors.extend(validate_memory_scope_recommendation_consistency(normalized))
    if require_current_evidence:
        expected = build_memory_scope_recommendation(
            run_dir=run_dir,
            repo_root=repo_root,
            experiments_dir=experiments_dir,
        )
        if normalized != expected:
            errors.append("memory_scope_recommendation current evidence mismatch")
    return tuple(errors)


def validate_memory_scope_recommendation_consistency(
    payload: dict[str, object],
) -> tuple[str, ...]:
    """Return stable internal consistency errors for a scope recommendation."""
    errors: list[str] = []
    current_scope = object_value(payload.get("current_scope", {}))
    observed = object_value(payload.get("observed_totals", {}))
    recommendation = object_value(payload.get("recommendation", {}))
    candidate_scopes = list_of_objects(payload.get("candidate_scopes", []))
    expected_recommendation = recommendation_payload(
        scope=current_scope,
        totals=observed,
    )
    if recommendation != expected_recommendation:
        errors.append("memory_scope_recommendation recommendation mismatch")
    expected_candidates = candidate_scope_rows(
        scope=current_scope,
        totals=observed,
    )
    if candidate_scopes != expected_candidates:
        errors.append("memory_scope_recommendation candidate scopes mismatch")
    for field in (
        "total_record_count",
        "active_record_count",
        "active_failed_count",
        "patch_block_count",
        "direction_block_count",
        "overblocked_patch_count",
    ):
        if int(observed.get(field, 0) or 0) < 0:
            errors.append(f"memory_scope_recommendation negative {field}")
    for row in candidate_scopes:
        if int(row.get("estimated_active_record_count", 0) or 0) < 0:
            errors.append("memory_scope_recommendation negative candidate estimate")
    return tuple(errors)


def load_json_object(path: Path) -> dict[str, object]:
    """Load a JSON object, returning an empty object if unavailable."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def object_value(value: object) -> dict[str, object]:
    """Return a JSON object value or an empty object."""
    return value if isinstance(value, dict) else {}


def list_of_objects(value: object) -> list[dict[str, object]]:
    """Return JSON object rows from a list-like value."""
    if not isinstance(value, list | tuple):
        return []
    return [row for row in value if isinstance(row, dict)]


def string_list(value: object) -> list[str]:
    """Return a deterministic string list."""
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list | tuple):
        return [str(item) for item in value if str(item)]
    return []


def file_record(path: Path, repo_root: Path) -> dict[str, object]:
    """Return deterministic metadata for one source file."""
    if not path.exists():
        return {
            "exists": False,
            "path": relative_path(path, repo_root),
            "bytes": 0,
            "sha256": "",
        }
    data = path.read_bytes()
    return {
        "exists": True,
        "path": relative_path(path, repo_root),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> None:
    """CLI entrypoint for memory scope recommendations."""
    parser = argparse.ArgumentParser(description="Write a memory scope recommendation.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--experiments-dir", type=Path)
    args = parser.parse_args()
    _, _, payload = write_memory_scope_recommendation(
        run_dir=args.run_dir,
        repo_root=args.repo_root,
        experiments_dir=args.experiments_dir,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
