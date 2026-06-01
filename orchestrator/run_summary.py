"""Human-readable experiment summary writers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


METRIC_KEYS = (
    "ev",
    "total_pnl",
    "max_drawdown",
    "trade_count",
    "fill_rate",
    "avg_slippage",
)


def write_single_run_summary(
    *,
    run_dir: Path,
    run_id: str,
    decision: dict[str, object],
    metrics_before: dict[str, float | int],
    metrics_after: dict[str, float | int],
) -> Path:
    """Write a markdown summary for a single deterministic evaluation run."""
    accepted = bool(decision.get("accepted", False))
    reasons = decision.get("reasons", [])
    lines = [
        "# Experiment Summary",
        "",
        f"- Run id: `{run_id}`",
        "- Kind: `single_run`",
        f"- Status: `{'accepted' if accepted else 'rejected'}`",
        "",
        "## Validation Metrics",
        "",
        metric_table(metrics_before, metrics_after),
        "",
        "## Decision",
        "",
        f"- Accepted: `{str(accepted).lower()}`",
    ]
    if isinstance(reasons, list) and reasons:
        lines.append("- Reasons:")
        lines.extend(f"  - {escape_text(str(reason))}" for reason in reasons)
    else:
        lines.append("- Reasons: none")

    return write_summary(run_dir / "summary.md", lines)


def write_iteration_summary(
    *,
    run_dir: Path,
    manifest: dict[str, object],
) -> Path:
    """Write a markdown summary for a multi-round iteration run."""
    rounds = [
        round_payload
        for round_payload in manifest.get("rounds", [])
        if isinstance(round_payload, dict)
    ]
    best_round = best_validation_round(rounds)
    lines = [
        "# Experiment Summary",
        "",
        f"- Run id: `{display_value(manifest.get('run_id'))}`",
        "- Kind: `iteration_loop`",
        f"- Status: `{display_value(manifest.get('status'))}`",
        f"- Completed rounds: `{display_value(manifest.get('completed_rounds'))}`",
        f"- Accepted round: `{display_value(manifest.get('accepted_round'))}`",
        f"- Stop reason: `{display_value(manifest.get('stop_reason'))}`",
        f"- Final strategy commit: `{display_value(manifest.get('final_strategy_commit'))}`",
    ]

    datasets = manifest.get("datasets")
    if isinstance(datasets, dict):
        lines.extend(["", "## Datasets", ""])
        for split in ("train", "validation", "holdout"):
            if split in datasets:
                lines.append(f"- {split}: `{datasets[split]}`")

    lines.extend(["", "## Best Validation Delta", ""])
    if best_round is None:
        lines.append("No completed rounds.")
    else:
        before = float(best_round.get("validation_ev_before", 0.0))
        after = float(best_round.get("validation_ev_after", 0.0))
        lines.append(
            f"- {best_round.get('round_id')}: `{format_number(after - before)}` "
            f"({format_number(before)} -> {format_number(after)})"
        )

    lines.extend(["", "## Rounds", ""])
    if not rounds:
        lines.append("No rounds were completed.")
    else:
        lines.extend(
            [
                "| Round | Accepted | Proposal | Train EV | Validation EV | "
                "Holdout EV | Trades | Reasons |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for round_payload in rounds:
            lines.append(round_table_row(run_dir, round_payload))

        lines.extend(["", "## Proposal Quality", ""])
        lines.extend(
            [
                "| Round | Direction | Repeat | Memory Filter | Fallback | Score | Probe EV | Patch SHA | Hypotheses | Expected Change | Risk |",
                "| --- | --- | --- | --- | --- | ---: | ---: | --- | --- | --- | --- |",
            ]
        )
        for round_payload in rounds:
            lines.append(proposal_quality_row(run_dir, round_payload))

        candidate_rows = load_optional_json_list(run_dir / "candidate_leaderboard.json")
        if candidate_rows:
            lines.extend(["", "## Candidate Leaderboard", ""])
            lines.extend(
                [
                    "| Round | Role | Agent | Direction | Selected | Score | Probe EV | Validation EV | Status |",
                    "| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |",
                ]
            )
            for row in candidate_rows[:10]:
                lines.append(candidate_leaderboard_row(row))

    return write_summary(run_dir / "summary.md", lines)


def metric_table(
    before: dict[str, float | int],
    after: dict[str, float | int],
) -> str:
    """Build a markdown table comparing before and after metrics."""
    lines = [
        "| Metric | Before | After | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for key in METRIC_KEYS:
        before_value = before.get(key, 0)
        after_value = after.get(key, 0)
        delta = float(after_value) - float(before_value)
        lines.append(
            "| "
            f"{key} | {format_number(before_value)} | {format_number(after_value)} | "
            f"{format_number(delta)} |"
        )
    return "\n".join(lines)


def round_table_row(run_dir: Path, round_payload: dict[str, object]) -> str:
    """Build one markdown table row for an iteration round."""
    round_id = str(round_payload.get("round_id", ""))
    proposal = load_optional_json(run_dir / round_id / "proposal.json")
    decision = load_optional_json(run_dir / round_id / "decision.json")
    proposal_summary = str(proposal.get("summary", "")) if proposal else ""
    agent_name = str(proposal.get("agent_name", "")) if proposal else ""
    accepted = str(bool(round_payload.get("accepted", False))).lower()
    reasons = decision.get("reasons") if decision else round_payload.get("reasons", [])
    reason_text = (
        "; ".join(str(reason) for reason in reasons)
        if isinstance(reasons, list)
        else ""
    )

    return (
        f"| {escape_cell(round_id)} "
        f"| `{accepted}` "
        f"| {escape_cell(agent_label(agent_name, proposal_summary))} "
        f"| {delta_cell(round_payload, 'train_ev_before', 'train_ev_after')} "
        f"| {delta_cell(round_payload, 'validation_ev_before', 'validation_ev_after')} "
        f"| {delta_cell(round_payload, 'holdout_ev_before', 'holdout_ev_after')} "
        f"| {round_payload.get('before_trade_count', 0)} -> "
        f"{round_payload.get('after_trade_count', 0)} "
        f"| {escape_cell(reason_text or 'none')} |"
    )


def proposal_quality_row(run_dir: Path, round_payload: dict[str, object]) -> str:
    """Build one markdown row describing proposal quality metadata."""
    round_id = str(round_payload.get("round_id", ""))
    proposal = load_optional_json(run_dir / round_id / "proposal.json")
    selected_attempt_payload = selected_attempt(
        load_optional_json_list(run_dir / round_id / "proposal_attempts.json")
    )
    repeat_of_round = str(proposal.get("repeat_of_round", "")) if proposal else ""
    repeat_label = f"yes ({repeat_of_round})" if repeat_of_round else "no"
    patch_sha = str(proposal.get("patch_sha256", "")) if proposal else ""
    hypotheses = proposal.get("hypotheses", []) if proposal else []
    expected = proposal.get("expected_metric_change", {}) if proposal else {}
    risk_notes = str(proposal.get("risk_notes", "")) if proposal else ""
    direction_tag = str(proposal.get("direction_tag", "")) if proposal else ""
    memory_reason = str(round_payload.get("proposal_memory_filter_reason", ""))
    fallback_reason = str(round_payload.get("proposal_fallback_reason", ""))
    fallback_label = "yes" if round_payload.get("proposal_fallback_used") else "no"
    if fallback_reason:
        fallback_label = f"yes: {fallback_reason}"
    score = round_payload.get("proposal_candidate_score", "none")
    probe_ev = selected_attempt_payload.get("probe_ev_delta", "none")

    return (
        f"| {escape_cell(round_id)} "
        f"| {escape_cell(direction_tag or 'none')} "
        f"| {escape_cell(repeat_label)} "
        f"| {escape_cell(memory_reason or 'none')} "
        f"| {escape_cell(fallback_label)} "
        f"| {escape_cell(str(score))} "
        f"| {escape_cell(str(probe_ev))} "
        f"| `{patch_sha[:12] if patch_sha else 'none'}` "
        f"| {escape_cell(list_text(hypotheses))} "
        f"| {escape_cell(mapping_text(expected))} "
        f"| {escape_cell(risk_notes or 'none')} |"
    )


def candidate_leaderboard_row(row: dict[str, Any]) -> str:
    """Build one markdown row for the candidate leaderboard."""
    validation_ev = row.get("validation_ev_delta")
    validation_text = "none" if validation_ev is None else str(validation_ev)
    return (
        f"| {escape_cell(str(row.get('round_id', '')))} "
        f"| {escape_cell(str(row.get('role', '')))} "
        f"| {escape_cell(str(row.get('agent_name', '')))} "
        f"| {escape_cell(str(row.get('direction_tag', '')) or 'none')} "
        f"| `{str(bool(row.get('selected', False))).lower()}` "
        f"| {escape_cell(str(row.get('candidate_score', 0)))} "
        f"| {escape_cell(str(row.get('probe_ev_delta', 0.0)))} "
        f"| {escape_cell(validation_text)} "
        f"| {escape_cell(str(row.get('status', '')))} |"
    )


def best_validation_round(rounds: list[dict[str, object]]) -> dict[str, object] | None:
    """Return the round with the largest validation EV improvement."""
    if not rounds:
        return None
    return max(
        rounds,
        key=lambda round_payload: float(round_payload.get("validation_ev_after", 0.0))
        - float(round_payload.get("validation_ev_before", 0.0)),
    )


def delta_cell(payload: dict[str, object], before_key: str, after_key: str) -> str:
    """Format a before/after metric pair with its delta."""
    before = float(payload.get(before_key, 0.0))
    after = float(payload.get(after_key, 0.0))
    delta = format_number(after - before)
    return f"{format_number(before)} -> {format_number(after)} ({delta})"


def agent_label(agent_name: str, proposal_summary: str) -> str:
    """Combine agent name and proposal summary for compact display."""
    if agent_name and proposal_summary:
        return f"{agent_name}: {proposal_summary}"
    return agent_name or proposal_summary or "unknown"


def load_optional_json(path: Path) -> dict[str, Any]:
    """Load JSON if it exists; otherwise return an empty mapping."""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def load_optional_json_list(path: Path) -> list[dict[str, Any]]:
    """Load a JSON list of objects if it exists."""
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def selected_attempt(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the selected proposal attempt payload, if present."""
    for attempt in attempts:
        if attempt.get("selected") is True:
            return attempt
    return {}


def list_text(value: object) -> str:
    """Format a list-like proposal field for compact markdown display."""
    if isinstance(value, list | tuple):
        return "; ".join(str(item) for item in value) or "none"
    return str(value) if value else "none"


def mapping_text(value: object) -> str:
    """Format a mapping-like proposal field for compact markdown display."""
    if not isinstance(value, dict) or not value:
        return "none"
    return "; ".join(f"{key}: {value[key]}" for key in sorted(value))


def write_summary(path: Path, lines: list[str]) -> Path:
    """Write markdown lines to a summary path."""
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def format_number(value: object) -> str:
    """Format numeric values compactly and deterministically."""
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.6f}"


def display_value(value: object) -> str:
    """Format optional manifest values for markdown."""
    if value is None:
        return "none"
    return str(value)


def escape_cell(value: str) -> str:
    """Escape markdown table cell content."""
    return escape_text(value).replace("|", "\\|")


def escape_text(value: str) -> str:
    """Flatten text for markdown summary display."""
    return " ".join(value.split())
