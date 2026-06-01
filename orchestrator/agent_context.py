"""Build deterministic context for strategy modification agents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_agent_context(
    *,
    run_dir: Path,
    current_round_id: str,
    output_path: Path,
) -> Path:
    """Write prior-round context for the next strategy proposal."""
    output_path.write_text(
        build_agent_context(run_dir=run_dir, current_round_id=current_round_id),
        encoding="utf-8",
    )
    return output_path


def build_agent_context(*, run_dir: Path, current_round_id: str) -> str:
    """Return a markdown context summary from prior round artifacts."""
    prior_rounds = prior_round_summaries(
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
                "Holdout EV | Reasons |",
                "| --- | --- | --- | --- | ---: | ---: | --- |",
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

    return "\n".join(lines).rstrip() + "\n"


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
        f"| {escape_cell(reason_text or 'none')} |"
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
