"""Deterministic candidate-vs-champion challenger report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.schema_validation import validate_json_file


CANDIDATE_CHALLENGER_SCHEMA_VERSION = "candidate_challenger_report_v1"
SCHEMA_PATH = Path("schemas/candidate_challenger_report.schema.json")


def write_candidate_challenger_report(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown candidate challenger artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    payload = build_candidate_challenger_report(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    json_path = run_dir / "candidate_challenger_report.json"
    md_path = run_dir / "candidate_challenger_report.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_candidate_challenger_markdown(payload), encoding="utf-8")
    errors = validate_candidate_challenger_report_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(f"candidate challenger report failed schema validation: {errors}")
    return json_path, md_path, payload


def build_candidate_challenger_report(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return a deterministic candidate-vs-champion report from saved artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    manifest = load_json_object(run_dir / "manifest.json")
    leaderboard = load_json_list(run_dir / "candidate_leaderboard.json")
    champion = champion_context(experiments_dir)
    champion_comparison = load_json_object(run_dir / "champion_comparison.json")
    champion_validation_ev = champion.get("validation_ev_delta")
    candidates = [
        challenger_candidate_row(
            run_id=str(manifest.get("run_id", run_dir.name)),
            row=row,
            champion_validation_ev=champion_validation_ev,
        )
        for row in leaderboard
    ]
    candidates.sort(key=candidate_sort_key, reverse=True)
    selected_candidates = [row for row in candidates if row["selected"] is True]
    top_candidate = candidates[0] if candidates else {}
    checks = {
        "manifest_present": bool(manifest),
        "leaderboard_present": bool(leaderboard),
        "champion_present": bool(champion.get("exists", False)),
        "candidate_rows_present": bool(candidates),
        "selected_candidate_present": bool(selected_candidates),
        "read_only": True,
    }
    ok = bool(checks["manifest_present"] and checks["leaderboard_present"])
    payload: dict[str, object] = {
        "schema_version": CANDIDATE_CHALLENGER_SCHEMA_VERSION,
        "run_id": str(manifest.get("run_id", run_dir.name)),
        "run_dir": str(run_dir),
        "experiments_dir": str(experiments_dir),
        "status": challenger_status(
            ok=ok,
            champion_exists=bool(champion.get("exists", False)),
            candidates=candidates,
        ),
        "ok": ok,
        "checks": checks,
        "champion": champion,
        "champion_comparison": compact_champion_comparison(champion_comparison),
        "summary": {
            "candidate_count": len(candidates),
            "selected_candidate_count": len(selected_candidates),
            "top_candidate_status": top_candidate.get("comparison_status", "none"),
            "top_candidate_round": top_candidate.get("round_id", ""),
            "top_candidate_direction": top_candidate.get("direction_tag", ""),
            "top_candidate_validation_ev_delta": top_candidate.get(
                "validation_ev_delta",
                None,
            ),
            "top_candidate_holdout_ev_delta": top_candidate.get(
                "holdout_ev_delta",
                None,
            ),
            "champion_run_id": champion.get("champion_run_id", ""),
        },
        "selected_candidates": selected_candidates,
        "top_candidates": candidates[:10],
        "recommended_next_actions": recommended_next_actions(
            champion=champion,
            candidates=candidates,
            selected_candidates=selected_candidates,
        ),
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_apply_patches": True,
            "does_not_route_agents": True,
            "does_not_promote_champion": True,
            "does_not_change_acceptance": True,
            "final_acceptance_authority": "deterministic_policy_and_holdout_gates",
        },
    }
    return payload


def challenger_candidate_row(
    *,
    run_id: str,
    row: dict[str, Any],
    champion_validation_ev: object,
) -> dict[str, object]:
    """Return one candidate challenger comparison row."""
    validation_ev = optional_float(row.get("validation_ev_delta"))
    holdout_ev = optional_float(row.get("holdout_ev_delta"))
    probe_ev = float(row.get("probe_ev_delta", 0.0) or 0.0)
    champion_ev = optional_float(champion_validation_ev)
    validation_gap = (
        round(validation_ev - champion_ev, 6)
        if validation_ev is not None and champion_ev is not None
        else None
    )
    probe_validation_gap = (
        round(probe_ev - validation_ev, 6) if validation_ev is not None else None
    )
    validation_holdout_gap = (
        round(validation_ev - holdout_ev, 6)
        if validation_ev is not None and holdout_ev is not None
        else None
    )
    return {
        "run_id": run_id,
        "round_id": str(row.get("round_id", "")),
        "attempt_index": int(row.get("attempt_index", 0) or 0),
        "role": str(row.get("role", "")),
        "profile_name": str(row.get("profile_name", "")),
        "agent_name": str(row.get("agent_name", "")),
        "direction_tag": str(row.get("direction_tag", "")),
        "selected": bool(row.get("selected", False)),
        "status": str(row.get("status", "")),
        "candidate_score": int(row.get("candidate_score", 0) or 0),
        "quality_breakdown": object_field(row, "quality_breakdown"),
        "probe_ev_delta": probe_ev,
        "validation_ev_delta": validation_ev,
        "holdout_ev_delta": holdout_ev,
        "champion_validation_ev_delta": champion_ev,
        "validation_gap_vs_champion": validation_gap,
        "probe_validation_gap": probe_validation_gap,
        "validation_holdout_gap": validation_holdout_gap,
        "comparison_status": candidate_comparison_status(
            validation_gap=validation_gap,
            validation_ev=validation_ev,
            champion_ev=champion_ev,
        ),
        "stability_flags": stability_flags(
            validation_ev=validation_ev,
            holdout_ev=holdout_ev,
            probe_validation_gap=probe_validation_gap,
            validation_holdout_gap=validation_holdout_gap,
        ),
        "selection_reason": str(row.get("selection_reason", "")),
        "failure_code": str(row.get("failure_code", "")),
        "patch_sha256": str(row.get("patch_sha256", "")),
    }


def candidate_comparison_status(
    *,
    validation_gap: float | None,
    validation_ev: float | None,
    champion_ev: float | None,
) -> str:
    """Return a compact comparison label."""
    if champion_ev is None:
        return "no_champion"
    if validation_ev is None:
        return "not_evaluated"
    if validation_gap is None:
        return "inconclusive"
    if validation_gap > 0:
        return "beats_champion_validation"
    if validation_gap < 0:
        return "trails_champion_validation"
    return "ties_champion_validation"


def stability_flags(
    *,
    validation_ev: float | None,
    holdout_ev: float | None,
    probe_validation_gap: float | None,
    validation_holdout_gap: float | None,
) -> list[str]:
    """Return deterministic candidate stability flags."""
    flags: list[str] = []
    if validation_ev is None:
        flags.append("validation_missing")
    if holdout_ev is None:
        flags.append("holdout_missing")
    elif holdout_ev < 0:
        flags.append("holdout_negative")
    if probe_validation_gap is not None and probe_validation_gap > 0.01:
        flags.append("probe_overstates_validation")
    if validation_holdout_gap is not None and validation_holdout_gap > 0.01:
        flags.append("validation_overstates_holdout")
    if not flags:
        flags.append("stable_signals")
    return flags


def champion_context(experiments_dir: Path) -> dict[str, object]:
    """Return compact champion context."""
    path = experiments_dir / "champion.json"
    if not path.exists():
        return {
            "exists": False,
            "path": str(path),
            "champion_run_id": "",
            "validation_ev_delta": None,
            "trade_count_delta": None,
            "source_status": "",
        }
    payload = load_json_object(path)
    return {
        "exists": True,
        "path": str(path),
        "champion_run_id": str(payload.get("champion_run_id", "")),
        "validation_ev_delta": optional_float(payload.get("validation_ev_delta")),
        "trade_count_delta": payload.get("trade_count_delta"),
        "source_status": str(payload.get("source_status", "")),
        "source_best_round": payload.get("source_best_round"),
        "strategy_commit": str(payload.get("strategy_commit", "")),
        "comparison_summary": str(payload.get("comparison_summary", "")),
    }


def compact_champion_comparison(payload: dict[str, Any]) -> dict[str, object]:
    """Return compact run-level champion comparison context."""
    if not payload:
        return {"exists": False}
    comparison = object_field(payload, "comparison")
    metric_deltas = object_field(comparison, "metric_deltas")
    return {
        "exists": True,
        "champion_run_id": str(payload.get("champion_run_id", "")),
        "winner": str(comparison.get("winner", "")),
        "recommendation": str(comparison.get("recommendation", "")),
        "validation_ev_delta": optional_float(metric_deltas.get("validation_ev_delta")),
        "summary": str(comparison.get("summary", "")),
    }


def challenger_status(
    *,
    ok: bool,
    champion_exists: bool,
    candidates: list[dict[str, object]],
) -> str:
    """Return a run-level challenger report status."""
    if not ok:
        return "needs_artifacts"
    if not champion_exists:
        return "no_champion"
    if any(row["comparison_status"] == "beats_champion_validation" for row in candidates):
        return "candidate_beats_champion"
    return "champion_not_beaten"


def recommended_next_actions(
    *,
    champion: dict[str, object],
    candidates: list[dict[str, object]],
    selected_candidates: list[dict[str, object]],
) -> list[str]:
    """Return deterministic next-step hints for challenger inspection."""
    if not champion.get("exists", False):
        return ["Promote or create a champion run before relying on challenger gaps."]
    if not candidates:
        return ["Run an iteration with proposal attempts before challenger review."]
    if any(row["comparison_status"] == "beats_champion_validation" for row in candidates):
        return ["Review holdout flags before considering champion promotion."]
    if selected_candidates:
        return ["Use quality and stability flags to choose the next modifier direction."]
    return ["Inspect why no candidate was selected before running another iteration."]


def render_candidate_challenger_markdown(payload: dict[str, object]) -> str:
    """Render candidate challenger payload as markdown."""
    champion = object_field(payload, "champion")
    summary = object_field(payload, "summary")
    lines = [
        "# Candidate Challenger Report",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- OK: `{str(payload.get('ok', False)).lower()}`",
        f"- Champion: `{champion.get('champion_run_id', 'none') or 'none'}`",
        f"- Top candidate: `{summary.get('top_candidate_direction', '') or 'none'}`",
        "",
        "## Top Candidates",
        "",
    ]
    rows = list_of_dicts(payload.get("top_candidates", []))
    if not rows:
        lines.append("No candidate rows available.")
    else:
        lines.extend(
            [
                "| Round | Role | Direction | Selected | Status | Score | Probe EV | Validation EV | Holdout EV | Gap vs Champion | Flags |",
                "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for row in rows:
            lines.append(candidate_markdown_row(row))
    lines.extend(["", "## Next Actions", ""])
    lines.extend(
        f"- {action}" for action in string_list(payload.get("recommended_next_actions", []))
    )
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- Report is read-only.",
            "- It does not execute agents, run backtests, apply patches, route agents, promote champions, or change acceptance.",
        ]
    )
    return "\n".join(lines) + "\n"


def candidate_markdown_row(row: dict[str, Any]) -> str:
    """Return one markdown candidate row."""
    return (
        f"| {row.get('round_id', '')} "
        f"| {row.get('role', '')} "
        f"| {row.get('direction_tag', '') or 'none'} "
        f"| `{str(bool(row.get('selected', False))).lower()}` "
        f"| {row.get('comparison_status', '')} "
        f"| {row.get('candidate_score', 0)} "
        f"| {number_text(row.get('probe_ev_delta'))} "
        f"| {number_text(row.get('validation_ev_delta'))} "
        f"| {number_text(row.get('holdout_ev_delta'))} "
        f"| {number_text(row.get('validation_gap_vs_champion'))} "
        f"| {', '.join(string_list(row.get('stability_flags', [])))} |"
    )


def validate_candidate_challenger_report_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved candidate challenger report."""
    return validate_json_file(
        payload_path=payload_path,
        schema_path=repo_root / SCHEMA_PATH,
    )


def candidate_sort_key(row: dict[str, object]) -> tuple[object, ...]:
    """Sort selected and strong challenger candidates first."""
    validation_gap = row.get("validation_gap_vs_champion")
    validation_gap_value = (
        float(validation_gap) if isinstance(validation_gap, int | float) else float("-inf")
    )
    validation_ev = row.get("validation_ev_delta")
    validation_value = (
        float(validation_ev) if isinstance(validation_ev, int | float) else float("-inf")
    )
    holdout_ev = row.get("holdout_ev_delta")
    holdout_value = (
        float(holdout_ev) if isinstance(holdout_ev, int | float) else float("-inf")
    )
    return (
        bool(row.get("selected", False)),
        validation_gap_value,
        validation_value,
        holdout_value,
        int(row.get("candidate_score", 0)),
        -int(row.get("attempt_index", 0)),
    )


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object or return an empty mapping."""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def load_json_list(path: Path) -> list[dict[str, Any]]:
    """Load a JSON list of objects or return an empty list."""
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


def object_field(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a nested object field."""
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def optional_float(value: object) -> float | None:
    """Return a float from a numeric value, otherwise None."""
    if isinstance(value, int | float):
        return float(value)
    return None


def number_text(value: object) -> str:
    """Return compact number text for markdown tables."""
    if isinstance(value, int | float):
        return f"{float(value):.6f}"
    return "none"


def list_of_dicts(value: object) -> list[dict[str, Any]]:
    """Return object rows from a possible list."""
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def string_list(value: object) -> list[str]:
    """Return string rows from a possible list."""
    return [str(item) for item in value] if isinstance(value, list) else []


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root."""
    return path if path.is_absolute() else repo_root / path


def main() -> None:
    """CLI entrypoint for candidate challenger reports."""
    parser = argparse.ArgumentParser(description="Write a candidate challenger report.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    _, _, payload = write_candidate_challenger_report(
        run_dir=args.run_dir,
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
