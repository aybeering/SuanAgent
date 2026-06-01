"""Aggregate candidate outcomes for future multi-agent routing."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


AGENT_RESULT_STATS_SCHEMA_VERSION = "agent_result_stats_v1"


def write_agent_result_stats(run_dir: Path) -> Path:
    """Write aggregate agent/direction/patch-family stats for one run."""
    payload = build_agent_result_stats(run_dir=run_dir)
    output_path = run_dir / "agent_result_stats.json"
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def build_agent_result_stats(run_dir: Path) -> dict[str, object]:
    """Build aggregate stats from a run-local candidate leaderboard."""
    candidates = load_candidate_rows(run_dir / "candidate_leaderboard.json")
    return {
        "schema_version": AGENT_RESULT_STATS_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "source_path": str(run_dir / "candidate_leaderboard.json"),
        "generated_at": utc_timestamp(),
        "totals": totals(candidates),
        "agents": aggregate_rows(candidates, key_field="agent_name"),
        "directions": aggregate_rows(candidates, key_field="direction_tag"),
        "patch_families": aggregate_patch_families(candidates),
        "routing_hints": routing_hints(candidates),
    }


def load_candidate_rows(path: Path) -> list[dict[str, object]]:
    """Load candidate leaderboard rows from disk."""
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


def totals(rows: list[dict[str, object]]) -> dict[str, object]:
    """Return run-level candidate totals."""
    accepted_count = sum(1 for row in rows if bool(row.get("validation_accepted", False)))
    selected_count = sum(1 for row in rows if bool(row.get("selected", False)))
    selectable_count = sum(1 for row in rows if row.get("status") == "selectable")
    return {
        "attempt_count": len(rows),
        "selected_count": selected_count,
        "selectable_count": selectable_count,
        "accepted_count": accepted_count,
        "rejected_count": len(rows) - accepted_count,
    }


def aggregate_rows(
    rows: list[dict[str, object]],
    *,
    key_field: str,
) -> list[dict[str, object]]:
    """Aggregate candidate rows by one stable key."""
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        key = str(row.get(key_field, "") or "unknown")
        grouped[key].append(row)
    payload = [
        aggregate_group(key=key, rows=group_rows, key_field=key_field)
        for key, group_rows in grouped.items()
    ]
    payload.sort(key=aggregate_sort_key)
    return payload


def aggregate_patch_families(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Aggregate candidate rows by patch hash family."""
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        patch_sha = str(row.get("patch_sha256", ""))
        family = patch_sha[:12] if patch_sha else "no_patch"
        grouped[family].append(row)
    payload = [
        {
            **aggregate_group(key=key, rows=group_rows, key_field="patch_family"),
            "patch_sha256": str(group_rows[0].get("patch_sha256", "")),
            "direction_tags": sorted(
                {
                    str(row.get("direction_tag", ""))
                    for row in group_rows
                    if str(row.get("direction_tag", ""))
                }
            ),
        }
        for key, group_rows in grouped.items()
    ]
    payload.sort(key=aggregate_sort_key)
    return payload


def aggregate_group(
    *,
    key: str,
    rows: list[dict[str, object]],
    key_field: str,
) -> dict[str, object]:
    """Return one aggregate row for a group of candidates."""
    accepted_count = sum(1 for row in rows if bool(row.get("validation_accepted", False)))
    selected_count = sum(1 for row in rows if bool(row.get("selected", False)))
    selectable_count = sum(1 for row in rows if row.get("status") == "selectable")
    failure_counts = failure_counter(rows)
    return {
        "key": key,
        "key_field": key_field,
        "attempt_count": len(rows),
        "selected_count": selected_count,
        "selectable_count": selectable_count,
        "accepted_count": accepted_count,
        "rejected_count": len(rows) - accepted_count,
        "acceptance_rate": ratio(accepted_count, len(rows)),
        "selection_rate": ratio(selected_count, len(rows)),
        "failure_counts": dict(sorted(failure_counts.items())),
        "top_failure_code": top_counter_key(failure_counts),
        "avg_candidate_score": average_number(rows, "candidate_score"),
        "avg_probe_ev_delta": average_number(rows, "probe_ev_delta"),
        "avg_validation_ev_delta": average_optional_number(rows, "validation_ev_delta"),
        "routing_action": routing_action(rows),
    }


def routing_hints(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return deterministic routing hints for agent and direction groups."""
    hints: list[dict[str, object]] = []
    for key_field in ("agent_name", "direction_tag"):
        for row in aggregate_rows(rows, key_field=key_field):
            action = str(row["routing_action"])
            if action == "neutral":
                continue
            hints.append(
                {
                    "target_type": key_field,
                    "target": row["key"],
                    "action": action,
                    "reason": routing_reason(row),
                    "top_failure_code": row["top_failure_code"],
                    "attempt_count": row["attempt_count"],
                    "accepted_count": row["accepted_count"],
                }
            )
    hints.sort(
        key=lambda row: (
            str(row["action"]),
            -int(row["attempt_count"]),
            str(row["target_type"]),
            str(row["target"]),
        )
    )
    return hints


def routing_action(rows: list[dict[str, object]]) -> str:
    """Return a conservative routing action from aggregate outcomes."""
    if not rows:
        return "neutral"
    accepted_count = sum(1 for row in rows if bool(row.get("validation_accepted", False)))
    if accepted_count:
        return "prefer"
    failure_counts = failure_counter(rows)
    top_code = top_counter_key(failure_counts)
    if len(rows) >= 2 and top_code in {
        "contract_invalid",
        "patch_check_failed",
        "patch_memory_rejected",
        "policy_ev_improvement_low",
    }:
        return "downweight"
    return "neutral"


def routing_reason(row: dict[str, object]) -> str:
    """Return a short routing explanation for one aggregate row."""
    action = str(row.get("routing_action", "neutral"))
    key = str(row.get("key", "unknown"))
    attempts = int(row.get("attempt_count", 0))
    accepted = int(row.get("accepted_count", 0))
    top_failure = str(row.get("top_failure_code", "none"))
    if action == "prefer":
        return f"{key} has {accepted}/{attempts} accepted candidates"
    if action == "downweight":
        return f"{key} has {attempts} attempts with top failure {top_failure}"
    return f"{key} has no strong routing signal"


def failure_counter(rows: list[dict[str, object]]) -> Counter[str]:
    """Count non-empty failure codes for candidate rows."""
    counter: Counter[str] = Counter()
    for row in rows:
        code = str(row.get("failure_code", "") or "none")
        if code != "none":
            counter[code] += 1
    return counter


def top_counter_key(counter: Counter[str]) -> str:
    """Return the most common counter key, with lexical tie-break."""
    if not counter:
        return "none"
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def average_number(rows: list[dict[str, object]], field: str) -> float:
    """Average numeric values, treating missing values as zero."""
    if not rows:
        return 0.0
    values = [float(row.get(field, 0.0) or 0.0) for row in rows]
    return round(sum(values) / len(values), 6)


def average_optional_number(rows: list[dict[str, object]], field: str) -> float:
    """Average numeric values, skipping null and missing values."""
    values = [
        float(row[field])
        for row in rows
        if isinstance(row.get(field), int | float)
    ]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 6)


def ratio(numerator: int, denominator: int) -> float:
    """Return a rounded ratio with zero protection."""
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def aggregate_sort_key(row: dict[str, object]) -> tuple[object, ...]:
    """Sort useful aggregate rows first."""
    return (
        -int(row.get("accepted_count", 0)),
        -int(row.get("selected_count", 0)),
        -int(row.get("attempt_count", 0)),
        str(row.get("key", "")),
    )


def utc_timestamp() -> str:
    """Return a deterministic-format UTC timestamp."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
