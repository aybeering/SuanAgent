"""Build deterministic context for strategy modification agents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.experiment_index import read_experiment_index
from orchestrator.outcome_memory import read_outcome_memory


AGENT_CONTEXT_SCHEMA_VERSION = "agent_context_v1"
TARGET_FILE = "strategies/current_strategy.py"
POLICY_NOTES = (
    "Acceptance is decided only by deterministic policy gate results.",
    "Avoid repeating failed patch hashes unless there is a new justification.",
)


def write_agent_context(
    *,
    run_dir: Path,
    current_round_id: str,
    output_path: Path,
    memory_path: Path | None = None,
) -> Path:
    """Write markdown and JSON context for the next strategy proposal."""
    payload = build_agent_context_payload(
        run_dir=run_dir,
        current_round_id=current_round_id,
        memory_path=memory_path,
    )
    output_path.write_text(build_agent_context_markdown(payload), encoding="utf-8")
    output_path.with_suffix(".json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def build_agent_context_payload(
    *,
    run_dir: Path,
    current_round_id: str,
    memory_path: Path | None = None,
) -> dict[str, object]:
    """Return a structured context payload from prior round artifacts."""
    prior_rounds = prior_round_summaries(
        run_dir=run_dir,
        current_round_id=current_round_id,
    )
    failed_hashes = [
        str(payload["patch_sha256"])
        for payload in prior_rounds
        if payload["patch_sha256"] and not payload["accepted"]
    ]
    return {
        "schema_version": AGENT_CONTEXT_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "current_round_id": current_round_id,
        "target_file": TARGET_FILE,
        "policy_notes": list(POLICY_NOTES),
        "champion": champion_context(run_dir=run_dir),
        "previous_champion_comparison": previous_champion_comparison(
            run_dir=run_dir,
        ),
        "prior_rounds": prior_rounds,
        "failed_patch_hashes": sorted(set(failed_hashes)),
        "candidate_search_trace": candidate_search_rows(
            run_dir=run_dir,
            current_round_id=current_round_id,
        ),
        "global_outcome_memory": recent_memory_records(
            memory_path=memory_path,
            run_dir=run_dir,
        ),
        "recent_research_briefs": recent_research_briefs(run_dir=run_dir),
    }


def build_agent_context(
    *,
    run_dir: Path,
    current_round_id: str,
    memory_path: Path | None = None,
) -> str:
    """Return a markdown context summary from prior round artifacts."""
    return build_agent_context_markdown(
        build_agent_context_payload(
            run_dir=run_dir,
            current_round_id=current_round_id,
            memory_path=memory_path,
        )
    )


def build_agent_context_markdown(payload: dict[str, object]) -> str:
    """Render a structured agent context payload as markdown."""
    prior_rounds = list_of_dicts(payload.get("prior_rounds", []))
    memory_records = list_of_dicts(payload.get("global_outcome_memory", []))
    candidate_rows = list_of_dicts(payload.get("candidate_search_trace", []))
    research_briefs = list_of_dicts(payload.get("recent_research_briefs", []))
    champion = dict_payload(payload.get("champion", {}))
    champion_comparison = dict_payload(
        payload.get("previous_champion_comparison", {}),
    )
    policy_notes = [
        str(note) for note in payload.get("policy_notes", []) if str(note)
    ]
    lines = [
        "# Agent Context",
        "",
        f"- Schema: `{payload.get('schema_version', AGENT_CONTEXT_SCHEMA_VERSION)}`",
        f"- Current round: `{payload.get('current_round_id', '')}`",
        f"- Target file: `{payload.get('target_file', TARGET_FILE)}`",
        "- Structured JSON: `agent_context.json`",
    ]
    lines.extend(f"- {note}" for note in policy_notes)
    lines.extend([
        "",
        "## Prior Rounds",
        "",
    ])
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

    lines.extend(["", "## Current Champion", ""])
    if not champion.get("exists", False):
        lines.append("No champion registry found.")
    else:
        lines.extend(
            [
                f"- Champion run: `{champion.get('champion_run_id', '')}`",
                f"- Source status: `{champion.get('source_status', '')}`",
                f"- Source best round: `{champion.get('source_best_round') or 'none'}`",
                f"- Validation EV delta: {format_number(float(champion.get('validation_ev_delta', 0.0)))}",
                f"- Strategy modifier: `{champion.get('strategy_modifier', '')}`",
                f"- Strategy commit: `{short_hash(str(champion.get('strategy_commit', '')) or '')}`",
                f"- Promotion summary: {escape_cell(str(champion.get('comparison_summary', '')))}",
            ]
        )

    lines.extend(["", "## Previous Champion Comparison", ""])
    if not champion_comparison.get("exists", False):
        lines.append("No champion comparison for this run yet.")
    else:
        lines.extend(
            [
                f"- Champion run: `{champion_comparison.get('champion_run_id', '')}`",
                f"- Winner: `{champion_comparison.get('winner', '')}`",
                f"- Recommendation: `{champion_comparison.get('recommendation', '')}`",
                f"- EV delta vs champion: {format_number(float(champion_comparison.get('validation_ev_delta', 0.0)))}",
                f"- Summary: {escape_cell(str(champion_comparison.get('summary', '')))}",
            ]
        )

    lines.extend(["", "## Failed Patch Hashes", ""])
    failed_hashes = [str(value) for value in payload.get("failed_patch_hashes", [])]
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
                "Validation EV Delta | Direction | Prior | Explore | Champion Gap | Status | Summary |",
                "| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- |",
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

    lines.extend(["", "## Recent Research Briefs", ""])
    if not research_briefs:
        lines.append("No prior research briefs yet.")
    else:
        lines.extend(
            [
                "| Run | Status | Rounds | Accepted | Top Direction | Recommendation | Next Questions |",
                "| --- | --- | ---: | --- | --- | --- | --- |",
            ]
        )
        for payload in research_briefs:
            lines.append(research_brief_row(payload))

    return "\n".join(lines).rstrip() + "\n"


def list_of_dicts(value: object) -> list[dict[str, object]]:
    """Return only dict items from a list-like payload field."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def dict_payload(value: object) -> dict[str, object]:
    """Return a dict payload, or an empty mapping."""
    return value if isinstance(value, dict) else {}


def champion_context(*, run_dir: Path) -> dict[str, object]:
    """Return compact current champion context for modifier agents."""
    path = run_dir.parent / "champion.json"
    if not path.exists():
        return {
            "exists": False,
            "path": str(path),
        }
    payload = load_json(path)
    return {
        "exists": True,
        "path": str(path),
        "champion_run_id": payload.get("champion_run_id", ""),
        "promoted_from_run_id": payload.get("promoted_from_run_id", ""),
        "source_kind": payload.get("source_kind", ""),
        "source_status": payload.get("source_status", ""),
        "source_best_round": payload.get("source_best_round"),
        "strategy_commit": payload.get("strategy_commit", ""),
        "strategy_modifier": payload.get("strategy_modifier", ""),
        "validation_ev_delta": payload.get("validation_ev_delta", 0.0),
        "trade_count_delta": payload.get("trade_count_delta", 0),
        "dataset_sha256": payload.get("dataset_sha256", {}),
        "comparison_summary": payload.get("comparison_summary", ""),
        "promotion_reasons": payload.get("promotion_reasons", []),
    }


def previous_champion_comparison(*, run_dir: Path) -> dict[str, object]:
    """Return compact champion comparison context for the active run."""
    path = run_dir / "champion_comparison.json"
    if not path.exists():
        return {
            "exists": False,
            "path": str(path),
        }
    payload = load_json(path)
    comparison = dict_payload(payload.get("comparison", {}))
    metric_deltas = dict_payload(comparison.get("metric_deltas", {}))
    return {
        "exists": True,
        "path": str(path),
        "champion_run_id": payload.get("champion_run_id", ""),
        "winner": comparison.get("winner", ""),
        "recommendation": comparison.get("recommendation", ""),
        "reasons": comparison.get("reasons", []),
        "validation_ev_delta": metric_deltas.get("validation_ev_delta", 0.0),
        "summary": comparison.get("summary", ""),
    }


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
        f"| {escape_cell(exploration_bonus_label(payload.get('exploration_bonus', {})))} "
        f"| {escape_cell(champion_gap_label(payload.get('champion_gap', {})))} "
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


def recent_research_briefs(
    *,
    run_dir: Path,
    limit: int = 3,
) -> list[dict[str, object]]:
    """Return compact research briefs from recent completed runs."""
    if limit <= 0:
        return []
    experiments_dir = run_dir.parent
    active_run_id = run_dir.name
    run_ids = recent_index_run_ids(experiments_dir=experiments_dir)
    if not run_ids:
        run_ids = [
            path.name
            for path in sorted(experiments_dir.iterdir())
            if path.is_dir() and path.name != active_run_id
        ]

    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for run_id in reversed(run_ids):
        if run_id == active_run_id or run_id in seen:
            continue
        seen.add(run_id)
        path = experiments_dir / run_id / "research_brief.json"
        if not path.exists():
            continue
        payload = load_json(path)
        rows.append(compact_research_brief(payload, path=path))
        if len(rows) >= limit:
            break
    return rows


def recent_index_run_ids(*, experiments_dir: Path) -> list[str]:
    """Return run ids from the append-only experiment index."""
    records = read_experiment_index(experiments_dir)
    return [
        str(record.get("run_id", ""))
        for record in records
        if str(record.get("kind", "")) == "iteration_loop" and record.get("run_id")
    ]


def compact_research_brief(
    payload: dict[str, Any],
    *,
    path: Path,
) -> dict[str, object]:
    """Return the small research-brief shape exposed to modifier agents."""
    champion = dict_payload(payload.get("champion_comparison", {}))
    top_candidates = list_of_dicts(payload.get("top_candidates", []))
    selected_candidates = list_of_dicts(payload.get("selected_candidates", []))
    top_candidate = top_candidates[0] if top_candidates else {}
    selected_candidate = selected_candidates[0] if selected_candidates else {}
    return {
        "path": str(path),
        "run_id": payload.get("run_id", ""),
        "status": payload.get("status", ""),
        "completed_rounds": payload.get("completed_rounds", 0),
        "accepted_round": payload.get("accepted_round"),
        "stop_reason": payload.get("stop_reason"),
        "summary": payload.get("summary", ""),
        "top_direction_tag": top_candidate.get("direction_tag", ""),
        "top_candidate_status": top_candidate.get("status", ""),
        "top_candidate_score": top_candidate.get("candidate_score", 0),
        "selected_direction_tag": selected_candidate.get("direction_tag", ""),
        "champion_recommendation": champion.get("recommendation", ""),
        "observations": payload.get("observations", []),
        "next_questions": payload.get("next_questions", []),
    }


def research_brief_row(payload: dict[str, object]) -> str:
    """Format one recent research brief as a markdown table row."""
    next_questions = payload.get("next_questions", [])
    questions = (
        "; ".join(str(question) for question in next_questions)
        if isinstance(next_questions, list)
        else ""
    )
    accepted_round = str(payload.get("accepted_round") or "none")
    direction = (
        str(payload.get("top_direction_tag", ""))
        or str(payload.get("selected_direction_tag", ""))
        or "none"
    )
    recommendation = str(payload.get("champion_recommendation", "")) or "none"
    return (
        f"| {escape_cell(str(payload.get('run_id', '')))} "
        f"| {escape_cell(str(payload.get('status', '')))} "
        f"| {int(payload.get('completed_rounds', 0))} "
        f"| {escape_cell(accepted_round)} "
        f"| {escape_cell(direction)} "
        f"| {escape_cell(recommendation)} "
        f"| {escape_cell(questions or 'none')} |"
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


def exploration_bonus_label(value: object) -> str:
    """Return compact exploration-bonus text for agent context."""
    if not isinstance(value, dict) or not value.get("active"):
        return "none"
    score_delta = int(value.get("score_delta", 0))
    sign = "+" if score_delta > 0 else ""
    return f"{sign}{score_delta}"


def champion_gap_label(value: object) -> str:
    """Return compact champion-gap text for agent context."""
    if not isinstance(value, dict) or not value.get("active"):
        return "none"
    score_delta = int(value.get("score_delta", 0))
    sign = "+" if score_delta > 0 else ""
    return (
        f"{sign}{score_delta} "
        f"(gap={float(value.get('gap', 0.0)):.6f}, "
        f"champion={value.get('champion_run_id', '')})"
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


def short_hash(value: str) -> str:
    """Return a compact hash label."""
    return value[:12] if value else "none"


def escape_cell(value: str) -> str:
    """Escape markdown table cell content."""
    return " ".join(value.split()).replace("|", "\\|")
