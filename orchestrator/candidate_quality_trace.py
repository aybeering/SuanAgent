"""Read-only candidate quality trace for one iteration run."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from orchestrator.schema_validation import validate_json_file


CANDIDATE_QUALITY_TRACE_SCHEMA_VERSION = "candidate_quality_trace_v1"
SCHEMA_PATH = Path("schemas/candidate_quality_trace.schema.json")


def write_candidate_quality_trace(
    *,
    run_dir: Path,
    repo_root: Path,
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown candidate quality trace artifacts."""
    payload = build_candidate_quality_trace(run_dir=run_dir, repo_root=repo_root)
    json_path = run_dir / "candidate_quality_trace.json"
    md_path = run_dir / "candidate_quality_trace.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_candidate_quality_trace_markdown(payload), encoding="utf-8")
    errors = validate_candidate_quality_trace_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(f"candidate quality trace failed schema validation: {errors}")
    return json_path, md_path, payload


def build_candidate_quality_trace(
    *,
    run_dir: Path,
    repo_root: Path,
) -> dict[str, object]:
    """Return a deterministic candidate quality trace from saved leaderboard rows."""
    leaderboard_path = run_dir / "candidate_leaderboard.json"
    rows = load_json_list(leaderboard_path)
    candidates = [candidate_trace_row(row) for row in rows]
    candidates.sort(key=candidate_sort_key)
    rounds = round_trace_rows(candidates)
    return {
        "schema_version": CANDIDATE_QUALITY_TRACE_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": relative_path(run_dir, repo_root),
        "source": file_record(leaderboard_path, repo_root),
        "summary": summary_payload(candidates),
        "rounds": rounds,
        "candidates": candidates,
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_route_candidates": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
            "proposal_attempts_remain_round_source_of_truth": True,
        },
    }


def candidate_trace_row(row: dict[str, object]) -> dict[str, object]:
    """Return one compact quality trace row."""
    quality = object_value(row.get("quality_breakdown", {}))
    signals = object_value(quality.get("signals", {}))
    return {
        "run_id": str(row.get("run_id", "")),
        "round_id": str(row.get("round_id", "")),
        "attempt_id": str(row.get("attempt_id", "")),
        "attempt_index": int(row.get("attempt_index", 0) or 0),
        "role": str(row.get("role", "")),
        "profile_name": str(row.get("profile_name", "")),
        "adapter_name": str(row.get("adapter_name", "")),
        "runner_name": str(row.get("runner_name", "")),
        "agent_name": str(row.get("agent_name", "")),
        "direction_tag": str(row.get("direction_tag", "")),
        "selected": bool(row.get("selected", False)),
        "status": str(row.get("status", "")),
        "candidate_score": number_value(row.get("candidate_score", 0)),
        "score_reasons": string_list(row.get("score_reasons", [])),
        "quality_breakdown": quality,
        "score_components": score_components(quality),
        "signals": {
            "probe_ev_delta": number_value(row.get("probe_ev_delta", 0.0)),
            "probe_trade_count_delta": number_value(
                row.get("probe_trade_count_delta", 0.0)
            ),
            "validation_ev_delta": optional_number(row.get("validation_ev_delta")),
            "validation_trade_count_delta": optional_number(
                row.get("validation_trade_count_delta")
            ),
            "holdout_ev_delta": optional_number(row.get("holdout_ev_delta")),
            "holdout_trade_count_delta": optional_number(
                row.get("holdout_trade_count_delta")
            ),
            "quality_probe_ev_delta": optional_number(signals.get("probe_ev_delta")),
            "quality_validation_ev_delta": optional_number(
                signals.get("validation_ev_delta")
            ),
            "quality_holdout_ev_delta": optional_number(signals.get("holdout_ev_delta")),
        },
        "failure": {
            "stage": str(row.get("failure_stage", "")),
            "code": str(row.get("failure_code", "")),
            "message": str(row.get("failure_message", "")),
            "reason_codes": list_of_objects(row.get("reason_codes", [])),
        },
        "patch": {
            "sha256": str(row.get("patch_sha256", "")),
            "family": str(row.get("patch_sha256", ""))[:12],
            "target_file": str(row.get("target_file", "")),
        },
        "selection": {
            "reason": str(row.get("selection_reason", "")),
            "validation_status": str(row.get("validation_status", "")),
            "validation_accepted": bool(row.get("validation_accepted", False)),
        },
        "guards": {
            "contract_errors": string_list(row.get("contract_errors", [])),
            "memory_filter_reason": str(row.get("memory_filter_reason", "")),
            "patch_memory_filter_reason": str(
                row.get("patch_memory_filter_reason", "")
            ),
            "direction_filter_reason": str(row.get("direction_filter_reason", "")),
            "patch_check_error": str(row.get("patch_check_error", "")),
            "probe_error": str(row.get("probe_error", "")),
        },
    }


def score_components(quality: dict[str, object]) -> list[dict[str, object]]:
    """Return normalized score components from a quality breakdown."""
    components = quality.get("components", [])
    if not isinstance(components, list):
        return []
    rows: list[dict[str, object]] = []
    for component in components:
        if not isinstance(component, dict):
            continue
        rows.append(
            {
                "name": str(component.get("name", "")),
                "score_delta": number_value(component.get("score_delta", 0)),
                "reason": str(component.get("reason", "")),
            }
        )
    return rows


def round_trace_rows(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return per-round trace summaries."""
    grouped: dict[str, list[dict[str, object]]] = {}
    for candidate in candidates:
        grouped.setdefault(str(candidate.get("round_id", "")), []).append(candidate)
    rows: list[dict[str, object]] = []
    for round_id in sorted(grouped):
        round_candidates = grouped[round_id]
        selected = [row for row in round_candidates if bool(row.get("selected", False))]
        top = round_candidates[0] if round_candidates else {}
        selected_row = selected[0] if selected else {}
        rows.append(
            {
                "round_id": round_id,
                "candidate_count": len(round_candidates),
                "selected_attempt_id": str(selected_row.get("attempt_id", "")),
                "selected_direction_tag": str(selected_row.get("direction_tag", "")),
                "top_attempt_id": str(top.get("attempt_id", "")),
                "top_score": number_value(top.get("candidate_score", 0)),
                "top_failure_code": str(object_value(top.get("failure", {})).get("code", "")),
                "selected_validation_ev_delta": optional_number(
                    object_value(selected_row.get("signals", {})).get(
                        "validation_ev_delta"
                    )
                ),
                "selected_holdout_ev_delta": optional_number(
                    object_value(selected_row.get("signals", {})).get(
                        "holdout_ev_delta"
                    )
                ),
            }
        )
    return rows


def summary_payload(candidates: list[dict[str, object]]) -> dict[str, object]:
    """Return run-level quality trace summary."""
    selected = [row for row in candidates if bool(row.get("selected", False))]
    selectable = [row for row in candidates if str(row.get("status", "")) == "selectable"]
    accepted = [
        row
        for row in candidates
        if bool(object_value(row.get("selection", {})).get("validation_accepted", False))
    ]
    failures = Counter(
        str(object_value(row.get("failure", {})).get("code", ""))
        for row in candidates
        if str(object_value(row.get("failure", {})).get("code", ""))
    )
    components = Counter(
        str(component.get("name", ""))
        for row in candidates
        for component in list_of_objects(row.get("score_components", []))
        if str(component.get("name", ""))
    )
    return {
        "candidate_count": len(candidates),
        "round_count": len({str(row.get("round_id", "")) for row in candidates}),
        "selected_count": len(selected),
        "selectable_count": len(selectable),
        "accepted_count": len(accepted),
        "top_failure_code": top_counter_key(failures),
        "top_quality_component": top_counter_key(components),
        "selected_attempt_ids": [str(row.get("attempt_id", "")) for row in selected],
        "selected_directions": sorted(
            {str(row.get("direction_tag", "")) for row in selected if row.get("direction_tag")}
        ),
        "policy_note": "candidate quality trace is inspection-only",
    }


def render_candidate_quality_trace_markdown(payload: dict[str, object]) -> str:
    """Render candidate quality trace payload as markdown."""
    summary = object_value(payload.get("summary", {}))
    lines = [
        "# Candidate Quality Trace",
        "",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Candidates: `{summary.get('candidate_count', 0)}`",
        f"- Selected: `{summary.get('selected_count', 0)}`",
        f"- Accepted: `{summary.get('accepted_count', 0)}`",
        f"- Top failure: `{summary.get('top_failure_code', '') or 'none'}`",
        f"- Top quality component: `{summary.get('top_quality_component', '') or 'none'}`",
        "",
        "## Rounds",
        "",
        "| Round | Candidates | Selected | Direction | Score | Failure | Val EV | Holdout EV |",
        "| --- | ---: | --- | --- | ---: | --- | ---: | ---: |",
    ]
    for row in list_of_objects(payload.get("rounds", [])):
        lines.append(
            "| "
            f"{row.get('round_id', '')} | "
            f"{row.get('candidate_count', 0)} | "
            f"{row.get('selected_attempt_id', '') or '-'} | "
            f"{row.get('selected_direction_tag', '') or '-'} | "
            f"{row.get('top_score', 0)} | "
            f"{row.get('top_failure_code', '') or 'none'} | "
            f"{format_optional(row.get('selected_validation_ev_delta'))} | "
            f"{format_optional(row.get('selected_holdout_ev_delta'))} |"
        )
    lines.extend(
        [
            "",
            "This artifact reads saved candidate artifacts only and cannot change routing or acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_candidate_quality_trace_file(
    *,
    payload_path: Path,
    repo_root: Path,
) -> tuple[str, ...]:
    """Validate a saved candidate quality trace report."""
    schema_path = repo_root / SCHEMA_PATH
    return tuple(validate_json_file(payload_path=payload_path, schema_path=schema_path))


def validate_candidate_quality_trace_consistency(
    *,
    payload: dict[str, object],
    run_dir: Path,
    repo_root: Path,
) -> tuple[str, ...]:
    """Return consistency errors after recomputing the trace from leaderboard rows."""
    expected = build_candidate_quality_trace(run_dir=run_dir, repo_root=repo_root)
    errors: list[str] = []
    for key in (
        "schema_version",
        "run_id",
        "run_dir",
        "source",
        "summary",
        "rounds",
        "candidates",
        "policy",
    ):
        if payload.get(key) != expected.get(key):
            errors.append(f"candidate_quality_trace recompute mismatch: {key}")
    return tuple(errors)


def load_json_list(path: Path) -> list[dict[str, object]]:
    """Load a JSON list of objects."""
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


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


def number_value(value: object) -> int | float:
    """Return a JSON-safe numeric value."""
    return value if isinstance(value, int | float) and not isinstance(value, bool) else 0


def optional_number(value: object) -> int | float | None:
    """Return a JSON-safe optional numeric value."""
    return value if isinstance(value, int | float) and not isinstance(value, bool) else None


def top_counter_key(counter: Counter[str]) -> str:
    """Return the most frequent key with deterministic tie-breaks."""
    if not counter:
        return ""
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def format_optional(value: object) -> str:
    """Format optional numeric values for markdown."""
    return f"{float(value):.6f}" if isinstance(value, int | float) else "-"


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


def candidate_sort_key(row: dict[str, object]) -> tuple[object, ...]:
    """Sort candidates by round and attempt order for trace readability."""
    return (
        str(row.get("round_id", "")),
        int(row.get("attempt_index", 0) or 0),
        str(row.get("attempt_id", "")),
    )


def main() -> None:
    """CLI entrypoint for candidate quality traces."""
    parser = argparse.ArgumentParser(description="Write a candidate quality trace.")
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    _, _, payload = write_candidate_quality_trace(
        run_dir=args.run_dir,
        repo_root=Path(".").resolve(),
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
