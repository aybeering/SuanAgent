"""Build deterministic context for strategy modification agents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.outcome_memory import read_outcome_memory


def write_agent_context(
    *,
    run_dir: Path,
    current_round_id: str,
    output_path: Path,
    memory_path: Path | None = None,
) -> Path:
    """Write prior-round context for the next strategy proposal."""
    output_path.write_text(
        build_agent_context(
            run_dir=run_dir,
            current_round_id=current_round_id,
            memory_path=memory_path,
        ),
        encoding="utf-8",
    )
    return output_path


def build_agent_context(
    *,
    run_dir: Path,
    current_round_id: str,
    memory_path: Path | None = None,
) -> str:
    """Return a markdown context summary from prior round artifacts."""
    prior_rounds = prior_round_summaries(
        run_dir=run_dir,
        current_round_id=current_round_id,
    )
    memory_records = recent_memory_records(memory_path=memory_path, run_dir=run_dir)
    candidate_rows = candidate_search_rows(
        run_dir=run_dir,
        current_round_id=current_round_id,
    )
    lines = [
        "# Agent Context",
        "",
        f"- Current round: `{current_round_id}`",
        "- Target file: `strategies/current_strategy.py`",
        "- Acceptance is decided only by deterministic policy gate results.",
        "- Avoid repeating failed patch hashes unless there is a new justification.",
        "",
        "## Prior Rounds",
        "",
    ]
    if not prior_rounds:
        lines.append("No prior rounds in this run.")
    else:
        lines.extend(
            [
                "| Round | Accepted | Patch SHA | Repeat | Validation EV | "
                "Holdout EV | Direction | Reasons |",
                "| --- | --- | --- | --- | ---: | ---: | --- | --- |",
            ]
        )
        for payload in prior_rounds:
            lines.append(prior_round_row(payload))

    lines.extend(["", "## Failed Patch Hashes", ""])
    failed_hashes = [
        str(payload["patch_sha256"])
        for payload in prior_rounds
        if payload["patch_sha256"] and not payload["accepted"]
    ]
    if not failed_hashes:
        lines.append("None.")
    else:
        for patch_hash in sorted(set(failed_hashes)):
            lines.append(f"- `{patch_hash}`")

    lines.extend(["", "## Candidate Search Trace", ""])
    if not candidate_rows:
        lines.append("No candidate search trace yet.")
    else:
        lines.extend(
            [
                "| Round | Role | Agent | Selected | Score | Probe EV Delta | "
                "Validation EV Delta | Direction | Prior | Status | Summary |",
                "| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |",
            ]
        )
        for payload in candidate_rows:
            lines.append(candidate_search_row(payload))

    lines.extend(["", "## Global Outcome Memory", ""])
    if not memory_records:
        lines.append("No global outcome memory yet.")
    else:
        lines.extend(
            [
                "| Run | Round | Agent | Accepted | Patch SHA | Validation EV Delta | Direction | Reasons |",
                "| --- | --- | --- | --- | --- | ---: | --- | --- |",
            ]
        )
        for payload in memory_records:
            lines.append(memory_row(payload))

    return "\n".join(lines).rstrip() + "\n"


def candidate_search_rows(
    *,
    run_dir: Path,
    current_round_id: str,
    limit: int = 8,
) -> list[dict[str, object]]:
    """Return prior candidate leaderboard rows for the active run."""
    leaderboard_path = run_dir / "candidate_leaderboard.json"
    if not leaderboard_path.exists():
        return []
    payload = json.loads(leaderboard_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    rows = [
        row
        for row in payload
        if isinstance(row, dict) and str(row.get("round_id", "")) < current_round_id
    ]
    return rows[:limit]


def candidate_search_row(payload: dict[str, object]) -> str:
    """Format one candidate search trace row as markdown."""
    validation_ev = payload.get("validation_ev_delta")
    validation_text = (
        "none" if validation_ev is None else format_number(float(validation_ev))
    )
    return (
        f"| {escape_cell(str(payload.get('round_id', '')))} "
        f"| {escape_cell(str(payload.get('role', '')))} "
        f"| {escape_cell(str(payload.get('agent_name', '')))} "
        f"| `{str(bool(payload.get('selected', False))).lower()}` "
        f"| {int(payload.get('candidate_score', 0))} "
        f"| {format_number(float(payload.get('probe_ev_delta', 0.0)))} "
        f"| {validation_text} "
        f"| {escape_cell(str(payload.get('direction_tag', '')) or 'none')} "
        f"| {escape_cell(direction_prior_label(payload.get('direction_prior', {})))} "
        f"| {escape_cell(str(payload.get('status', '')))} "
        f"| {escape_cell(str(payload.get('summary', '')))} |"
    )


def prior_round_summaries(
    *,
    run_dir: Path,
    current_round_id: str,
) -> list[dict[str, object]]:
    """Collect deterministic summary rows from prior round artifacts."""
    summaries: list[dict[str, object]] = []
    for round_dir in sorted(run_dir.glob("round_*")):
        round_id = round_dir.name
        if round_id >= current_round_id:
            continue
        proposal = load_json(round_dir / "proposal.json")
        decision = load_json(round_dir / "decision.json")
        metrics_before = load_json(round_dir / "metrics_before.json")
        metrics_after = load_json(round_dir / "metrics_after.json")
        holdout_before = load_json(round_dir / "holdout_metrics_before.json")
        holdout_after = load_json(round_dir / "holdout_metrics_after.json")
        summaries.append(
            {
                "round_id": round_id,
                "accepted": bool(decision.get("accepted", False)),
                "reasons": decision.get("reasons", []),
                "patch_sha256": proposal.get("patch_sha256", ""),
                "direction_tag": proposal.get("direction_tag", ""),
                "is_repeat_patch": proposal.get("is_repeat_patch", False),
                "repeat_of_round": proposal.get("repeat_of_round", ""),
                "validation_ev_before": metrics_before.get("ev", 0.0),
                "validation_ev_after": metrics_after.get("ev", 0.0),
                "holdout_ev_before": holdout_before.get("ev", 0.0),
                "holdout_ev_after": holdout_after.get("ev", 0.0),
            }
        )
    return summaries


def prior_round_row(payload: dict[str, object]) -> str:
    """Format one prior round as a markdown table row."""
    patch_sha = str(payload.get("patch_sha256", ""))
    repeat_of_round = str(payload.get("repeat_of_round", ""))
    repeat_label = f"yes ({repeat_of_round})" if repeat_of_round else "no"
    reasons = payload.get("reasons", [])
    reason_text = (
        "; ".join(str(reason) for reason in reasons)
        if isinstance(reasons, list)
        else ""
    )
    return (
        f"| {escape_cell(str(payload['round_id']))} "
        f"| `{str(bool(payload['accepted'])).lower()}` "
        f"| `{patch_sha[:12] if patch_sha else 'none'}` "
        f"| {escape_cell(repeat_label)} "
        f"| {delta_cell(payload, 'validation_ev_before', 'validation_ev_after')} "
        f"| {delta_cell(payload, 'holdout_ev_before', 'holdout_ev_after')} "
        f"| {escape_cell(str(payload.get('direction_tag', '')) or 'none')} "
        f"| {escape_cell(reason_text or 'none')} |"
    )


def recent_memory_records(
    *,
    memory_path: Path | None,
    run_dir: Path,
    limit: int = 5,
) -> list[dict[str, object]]:
    """Return recent outcome memory rows, excluding the active run."""
    if memory_path is None:
        memory_path = run_dir.parent / "memory.jsonl"
    if not memory_path.exists():
        return []

    records = read_outcome_memory(memory_path.parent)
    active_run_id = run_dir.name
    filtered = [
        record
        for record in records
        if str(record.get("run_id", "")) != active_run_id
    ]
    return filtered[-limit:]


def memory_row(payload: dict[str, object]) -> str:
    """Format one outcome memory record as a markdown table row."""
    reasons = payload.get("reasons", [])
    reason_text = (
        "; ".join(str(reason) for reason in reasons)
        if isinstance(reasons, list)
        else ""
    )
    patch_sha = str(payload.get("patch_sha256", ""))
    return (
        f"| {escape_cell(str(payload.get('run_id', '')))} "
        f"| {escape_cell(str(payload.get('round_id', '')))} "
        f"| {escape_cell(str(payload.get('agent_name', '')))} "
        f"| `{str(bool(payload.get('accepted', False))).lower()}` "
        f"| `{patch_sha[:12] if patch_sha else 'none'}` "
        f"| {format_number(float(payload.get('validation_ev_delta', 0.0)))} "
        f"| {escape_cell(str(payload.get('direction_tag', '')) or 'none')} "
        f"| {escape_cell(reason_text or 'none')} |"
    )


def direction_prior_label(value: object) -> str:
    """Return compact direction-prior text for agent context."""
    if not isinstance(value, dict) or int(value.get("sample_count", 0)) <= 0:
        return "none"
    score_delta = int(value.get("score_delta", 0))
    sign = "+" if score_delta > 0 else ""
    return (
        f"{sign}{score_delta} "
        f"(n={int(value.get('sample_count', 0))}, "
        f"accept={float(value.get('accept_rate', 0.0)):.3f})"
    )


def delta_cell(payload: dict[str, object], before_key: str, after_key: str) -> str:
    """Format before/after values as a compact delta cell."""
    before = float(payload.get(before_key, 0.0))
    after = float(payload.get(after_key, 0.0))
    delta = format_number(after - before)
    return f"{format_number(before)} -> {format_number(after)} ({delta})"


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object if present, otherwise return an empty mapping."""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def format_number(value: float) -> str:
    """Format a numeric value deterministically."""
    return f"{value:.6f}"


def escape_cell(value: str) -> str:
    """Escape markdown table cell content."""
    return " ".join(value.split()).replace("|", "\\|")
