"""Run-level research brief artifacts for iteration experiments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.run_diagnosis import diagnose_run


RESEARCH_BRIEF_SCHEMA_VERSION = "research_brief_v1"


def write_research_brief(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> tuple[Path, Path]:
    """Write machine-readable and markdown research briefs for one run."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    payload = build_research_brief(
        run_id=run_id,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    run_dir = experiments_dir / run_id
    json_path = run_dir / "research_brief.json"
    md_path = run_dir / "research_brief.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_research_brief_markdown(payload), encoding="utf-8")
    return json_path, md_path


def build_research_brief(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return a compact research brief payload for one run."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    run_dir = experiments_dir / run_id
    diagnosis = diagnose_run(
        run_id=run_id,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    manifest = load_json_object(run_dir / "manifest.json")
    leaderboard = load_json_list(run_dir / "candidate_leaderboard.json")
    champion_comparison = compact_champion_comparison(
        load_json_object(run_dir / "champion_comparison.json"),
    )
    selected_candidates = list_of_dicts(diagnosis.get("selected_candidates", []))
    top_candidates = compact_candidates(leaderboard[:5])
    payload: dict[str, object] = {
        "schema_version": RESEARCH_BRIEF_SCHEMA_VERSION,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "kind": diagnosis.get("kind", "unknown"),
        "status": diagnosis.get("status", "unknown"),
        "artifact_ok": bool(diagnosis.get("artifact_ok", False)),
        "artifact_error_count": len(list(diagnosis.get("artifact_errors", []))),
        "completed_rounds": int(diagnosis.get("completed_rounds", 0)),
        "accepted_round": diagnosis.get("accepted_round"),
        "stop_reason": diagnosis.get("stop_reason"),
        "final_strategy_commit": diagnosis.get("final_strategy_commit"),
        "summary": diagnosis.get("summary", ""),
        "best_round": diagnosis.get("best_round"),
        "selected_candidates": compact_candidates(selected_candidates),
        "top_candidates": top_candidates,
        "champion_comparison": champion_comparison,
        "candidate_selection": manifest.get("candidate_selection", {})
        if isinstance(manifest, dict)
        else {},
        "observations": [],
        "next_questions": [],
    }
    payload["observations"] = research_observations(payload)
    payload["next_questions"] = research_next_questions(payload)
    return payload


def compact_candidates(rows: list[dict[str, Any]]) -> list[dict[str, object]]:
    """Return compact candidate rows for research briefs."""
    compact: list[dict[str, object]] = []
    for row in rows:
        compact.append(
            {
                "round_id": row.get("round_id", ""),
                "role": row.get("role", ""),
                "agent_name": row.get("agent_name", ""),
                "direction_tag": row.get("direction_tag", ""),
                "selected": bool(row.get("selected", False)),
                "status": row.get("status", ""),
                "candidate_score": row.get("candidate_score", 0),
                "quality_breakdown": row.get("quality_breakdown", {}),
                "probe_ev_delta": row.get("probe_ev_delta", 0.0),
                "validation_ev_delta": row.get("validation_ev_delta"),
                "holdout_ev_delta": row.get("holdout_ev_delta"),
                "champion_gap": row.get("champion_gap", {}),
                "selection_reason": row.get("selection_reason", ""),
            }
        )
    return compact


def compact_champion_comparison(payload: dict[str, Any]) -> dict[str, object]:
    """Return compact champion comparison metadata."""
    if not payload:
        return {
            "exists": False,
        }
    comparison = payload.get("comparison", {})
    comparison_payload = comparison if isinstance(comparison, dict) else {}
    metric_deltas = comparison_payload.get("metric_deltas", {})
    metric_payload = metric_deltas if isinstance(metric_deltas, dict) else {}
    return {
        "exists": True,
        "champion_run_id": payload.get("champion_run_id", ""),
        "winner": comparison_payload.get("winner", ""),
        "recommendation": comparison_payload.get("recommendation", ""),
        "validation_ev_delta": metric_payload.get("validation_ev_delta", 0.0),
        "summary": comparison_payload.get("summary", ""),
        "reasons": comparison_payload.get("reasons", []),
    }


def research_observations(payload: dict[str, object]) -> list[str]:
    """Return deterministic research observations from a brief payload."""
    observations: list[str] = []
    if not payload.get("artifact_ok", False):
        observations.append("Artifact validation failed; inspect artifact_errors first.")
    status = str(payload.get("status", "unknown"))
    if status == "accepted":
        observations.append("The run produced an accepted strategy candidate.")
    elif status.startswith("stopped"):
        observations.append(f"The run stopped without acceptance: {status}.")
    if payload.get("accepted_round"):
        observations.append(f"Accepted round: {payload['accepted_round']}.")

    champion = dict_payload(payload.get("champion_comparison", {}))
    if champion.get("exists"):
        recommendation = str(champion.get("recommendation", ""))
        observations.append(f"Champion comparison recommendation: {recommendation}.")
        observations.append(
            "Champion EV delta difference: "
            f"{float(champion.get('validation_ev_delta', 0.0)):.6f}."
        )
    else:
        observations.append("No champion comparison was available for this run.")

    top_candidates = list_of_dicts(payload.get("top_candidates", []))
    if top_candidates:
        top = top_candidates[0]
        observations.append(
            "Top candidate "
            f"{top.get('round_id', '')}/{top.get('role', '')} scored "
            f"{top.get('candidate_score', 0)} with status {top.get('status', '')}."
        )
    return observations


def research_next_questions(payload: dict[str, object]) -> list[str]:
    """Return deterministic next research questions."""
    questions: list[str] = []
    champion = dict_payload(payload.get("champion_comparison", {}))
    if champion.get("exists") and champion.get("recommendation") != "promote_candidate":
        questions.append("Which proposal direction can close the champion EV gap?")
    if not payload.get("accepted_round"):
        questions.append("Which rejection reason appears most often among selected candidates?")
    if not payload.get("artifact_ok", False):
        questions.append("Which missing or invalid artifact blocked reliable interpretation?")
    if not questions:
        questions.append("Should the accepted strategy be promoted after an explicit compare?")
    return questions


def render_research_brief_markdown(payload: dict[str, object]) -> str:
    """Render a research brief payload as markdown."""
    lines = [
        "# Research Brief",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- Artifact health: `{str(bool(payload.get('artifact_ok', False))).lower()}`",
        f"- Completed rounds: `{payload.get('completed_rounds', 0)}`",
        f"- Accepted round: `{payload.get('accepted_round') or 'none'}`",
        f"- Stop reason: `{payload.get('stop_reason') or 'none'}`",
        "",
        "## Summary",
        "",
        str(payload.get("summary", "")) or "No summary available.",
        "",
        "## Observations",
        "",
    ]
    lines.extend(f"- {observation}" for observation in payload.get("observations", []))

    champion = dict_payload(payload.get("champion_comparison", {}))
    lines.extend(["", "## Champion Comparison", ""])
    if not champion.get("exists"):
        lines.append("No champion comparison available.")
    else:
        lines.extend(
            [
                f"- Champion run: `{champion.get('champion_run_id', '')}`",
                f"- Winner: `{champion.get('winner', '')}`",
                f"- Recommendation: `{champion.get('recommendation', '')}`",
                f"- EV delta difference: `{float(champion.get('validation_ev_delta', 0.0)):.6f}`",
                f"- Summary: {champion.get('summary', '')}",
            ]
        )

    lines.extend(["", "## Top Candidates", ""])
    candidates = list_of_dicts(payload.get("top_candidates", []))
    if not candidates:
        lines.append("No candidate rows available.")
    else:
        lines.extend(
            [
                "| Round | Role | Direction | Selected | Score | Probe EV | Validation EV | Holdout EV | Champion Gap | Status |",
                "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for row in candidates:
            lines.append(candidate_row(row))

    lines.extend(["", "## Next Questions", ""])
    lines.extend(f"- {question}" for question in payload.get("next_questions", []))
    return "\n".join(lines).rstrip() + "\n"


def candidate_row(row: dict[str, object]) -> str:
    """Return one markdown candidate row."""
    champion_gap = dict_payload(row.get("champion_gap", {}))
    champion_gap_text = "none"
    if champion_gap.get("active"):
        champion_gap_text = (
            f"{int(champion_gap.get('score_delta', 0))} "
            f"gap={float(champion_gap.get('gap', 0.0)):.6f}"
        )
    validation = row.get("validation_ev_delta")
    validation_text = "none" if validation is None else f"{float(validation):.6f}"
    holdout = row.get("holdout_ev_delta")
    holdout_text = "none" if holdout is None else f"{float(holdout):.6f}"
    return (
        f"| {row.get('round_id', '')} "
        f"| {row.get('role', '')} "
        f"| {row.get('direction_tag', '') or 'none'} "
        f"| `{str(bool(row.get('selected', False))).lower()}` "
        f"| {row.get('candidate_score', 0)} "
        f"| {float(row.get('probe_ev_delta', 0.0)):.6f} "
        f"| {validation_text} "
        f"| {holdout_text} "
        f"| {champion_gap_text} "
        f"| {row.get('status', '')} |"
    )


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object if present."""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def load_json_list(path: Path) -> list[dict[str, Any]]:
    """Load a list of JSON objects if present."""
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def list_of_dicts(value: object) -> list[dict[str, Any]]:
    """Return dict items from a list-like value."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def dict_payload(value: object) -> dict[str, Any]:
    """Return a dict payload or an empty mapping."""
    return value if isinstance(value, dict) else {}


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to repo root."""
    return path if path.is_absolute() else repo_root / path
