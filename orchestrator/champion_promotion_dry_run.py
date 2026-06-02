"""Deterministic read-only champion promotion dry-run report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.experiments import compare_experiments, show_champion
from orchestrator.run_diagnosis import diagnose_run
from orchestrator.schema_validation import validate_json_file


CHAMPION_PROMOTION_DRY_RUN_SCHEMA_VERSION = "champion_promotion_dry_run_v1"
SCHEMA_PATH = Path("schemas/champion_promotion_dry_run.schema.json")


def write_champion_promotion_dry_run(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    min_ev_delta: float = 0.0,
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown champion promotion dry-run artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    payload = build_champion_promotion_dry_run(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        min_ev_delta=min_ev_delta,
    )
    json_path = run_dir / "champion_promotion_dry_run.json"
    md_path = run_dir / "champion_promotion_dry_run.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_champion_promotion_markdown(payload), encoding="utf-8")
    errors = validate_champion_promotion_dry_run_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(f"champion promotion dry-run failed schema validation: {errors}")
    return json_path, md_path, payload


def build_champion_promotion_dry_run(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    min_ev_delta: float = 0.0,
) -> dict[str, object]:
    """Return a deterministic read-only champion promotion dry-run payload."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    run_id = run_dir.name
    run_record = load_json_object(run_dir / "manifest.json") or load_json_object(
        run_dir / "decision.json"
    )
    diagnosis = diagnose_run(
        run_id=run_id,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    champion = compact_champion(show_champion(experiments_dir=experiments_dir))
    candidate = compact_candidate(diagnosis)
    comparison = dry_run_comparison(
        run_id=run_id,
        champion=champion,
        experiments_dir=experiments_dir,
        min_ev_delta=min_ev_delta,
    )
    blocking_reasons = promotion_blocking_reasons(
        champion=champion,
        candidate=candidate,
        comparison=comparison,
    )
    would_promote = (
        bool(comparison.get("exists", False))
        and comparison.get("recommendation") == "promote_candidate"
        and not blocking_reasons
    )
    status = dry_run_status(
        manifest_present=bool(run_record),
        champion=champion,
        comparison=comparison,
        would_promote=would_promote,
        blocking_reasons=blocking_reasons,
    )
    ok = bool(run_record and diagnosis)
    payload: dict[str, object] = {
        "schema_version": CHAMPION_PROMOTION_DRY_RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "experiments_dir": str(experiments_dir),
        "status": status,
        "ok": ok,
        "checks": {
            "manifest_present": bool(run_record),
            "diagnosis_present": bool(diagnosis),
            "champion_present": bool(champion.get("exists", False)),
            "candidate_is_current_champion": bool(
                champion.get("champion_run_id") == run_id
            ),
            "comparison_available": bool(comparison.get("exists", False)),
            "candidate_artifact_ok": bool(candidate.get("artifact_ok", False)),
            "candidate_accepted": bool(candidate.get("accepted", False)),
            "read_only": True,
            "would_write_champion_registry": False,
            "would_append_champion_history": False,
        },
        "champion": champion,
        "candidate": candidate,
        "comparison": comparison,
        "dry_run_decision": {
            "eligible": would_promote,
            "would_promote": would_promote,
            "blocking_reasons": blocking_reasons,
            "promotion_command": promotion_command(
                champion_run_id=str(champion.get("champion_run_id", "")),
                candidate_run_id=run_id,
                recommended=would_promote,
            ),
            "evidence_paths": evidence_paths(
                run_dir=run_dir,
                experiments_dir=experiments_dir,
                champion=champion,
            ),
        },
        "recommended_next_actions": recommended_next_actions(
            status=status,
            blocking_reasons=blocking_reasons,
            would_promote=would_promote,
        ),
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_apply_patches": True,
            "does_not_route_agents": True,
            "does_not_write_champion_registry": True,
            "does_not_append_champion_history": True,
            "does_not_change_acceptance": True,
            "requires_explicit_promote_command": True,
            "promotion_authority": "python -m orchestrator.experiments promote",
        },
    }
    return payload


def dry_run_comparison(
    *,
    run_id: str,
    champion: dict[str, object],
    experiments_dir: Path,
    min_ev_delta: float,
) -> dict[str, object]:
    """Return compact comparison metadata without writing champion artifacts."""
    champion_run_id = str(champion.get("champion_run_id", ""))
    if not champion.get("exists", False):
        return {
            "exists": False,
            "base_run_id": "",
            "candidate_run_id": run_id,
            "winner": "",
            "recommendation": "no_champion",
            "validation_ev_delta": None,
            "trade_count_delta": None,
            "dataset_match": None,
            "reasons": ["no current champion registry exists"],
            "summary": "No current champion registry exists.",
            "min_ev_delta": min_ev_delta,
        }
    if champion_run_id == run_id:
        return {
            "exists": False,
            "base_run_id": champion_run_id,
            "candidate_run_id": run_id,
            "winner": "current_champion",
            "recommendation": "already_champion",
            "validation_ev_delta": 0.0,
            "trade_count_delta": 0,
            "dataset_match": True,
            "reasons": ["candidate run is already the current champion"],
            "summary": "Candidate run is already the current champion.",
            "min_ev_delta": min_ev_delta,
        }
    comparison = compare_experiments(
        base_run_id=champion_run_id,
        candidate_run_id=run_id,
        experiments_dir=experiments_dir,
        min_ev_delta=min_ev_delta,
    )
    metric_deltas = object_field(comparison, "metric_deltas")
    dataset = object_field(comparison, "dataset_comparison")
    return {
        "exists": True,
        "base_run_id": champion_run_id,
        "candidate_run_id": run_id,
        "winner": str(comparison.get("winner", "")),
        "recommendation": str(comparison.get("recommendation", "")),
        "validation_ev_delta": optional_float(metric_deltas.get("validation_ev_delta")),
        "trade_count_delta": metric_deltas.get("trade_count_delta"),
        "dataset_match": dataset.get("match"),
        "reasons": string_list(comparison.get("reasons", [])),
        "summary": str(comparison.get("summary", "")),
        "min_ev_delta": min_ev_delta,
    }


def promotion_blocking_reasons(
    *,
    champion: dict[str, object],
    candidate: dict[str, object],
    comparison: dict[str, object],
) -> list[str]:
    """Return deterministic reasons that block promotion in this dry-run."""
    reasons: list[str] = []
    if not champion.get("exists", False):
        reasons.append("no_current_champion")
    if champion.get("champion_run_id") == candidate.get("run_id"):
        reasons.append("candidate_already_champion")
    if not bool(candidate.get("artifact_ok", False)):
        reasons.append("candidate_artifacts_not_ok")
    if not bool(candidate.get("accepted", False)):
        reasons.append("candidate_not_accepted")
    if comparison.get("recommendation") != "promote_candidate":
        reasons.append(f"comparison_recommendation_{comparison.get('recommendation', '')}")
    return unique_strings(reasons)


def dry_run_status(
    *,
    manifest_present: bool,
    champion: dict[str, object],
    comparison: dict[str, object],
    would_promote: bool,
    blocking_reasons: list[str],
) -> str:
    """Return compact dry-run status."""
    if not manifest_present:
        return "needs_artifacts"
    if would_promote:
        return "promotion_recommended"
    if not champion.get("exists", False):
        return "no_champion"
    if comparison.get("recommendation") == "already_champion":
        return "already_champion"
    if blocking_reasons:
        return "promotion_blocked"
    return "promotion_not_recommended"


def compact_champion(payload: dict[str, object]) -> dict[str, object]:
    """Return compact current champion registry context."""
    if not payload.get("exists", False):
        return {
            "exists": False,
            "path": str(payload.get("champion_path", "")),
            "champion_run_id": "",
            "validation_ev_delta": None,
            "trade_count_delta": None,
            "source_status": "",
            "strategy_commit": "",
        }
    champion = object_field(payload, "champion")
    return {
        "exists": True,
        "path": str(payload.get("champion_path", "")),
        "champion_run_id": str(champion.get("champion_run_id", "")),
        "validation_ev_delta": optional_float(champion.get("validation_ev_delta")),
        "trade_count_delta": champion.get("trade_count_delta"),
        "source_status": str(champion.get("source_status", "")),
        "strategy_commit": str(champion.get("strategy_commit", "")),
        "comparison_summary": str(champion.get("comparison_summary", "")),
    }


def compact_candidate(diagnosis: dict[str, object]) -> dict[str, object]:
    """Return compact candidate run context."""
    best_round = object_field(diagnosis, "best_round")
    return {
        "run_id": str(diagnosis.get("run_id", "")),
        "kind": str(diagnosis.get("kind", "")),
        "status": str(diagnosis.get("status", "")),
        "accepted": bool(diagnosis.get("status") == "accepted"),
        "artifact_ok": bool(diagnosis.get("artifact_ok", False)),
        "validation_ev_delta": optional_float(best_round.get("validation_ev_delta")),
        "trade_count_delta": best_round.get("trade_count_delta"),
        "best_round": best_round.get("round_id"),
        "final_strategy_commit": str(diagnosis.get("final_strategy_commit", "")),
    }


def promotion_command(
    *,
    champion_run_id: str,
    candidate_run_id: str,
    recommended: bool,
) -> str:
    """Return explicit command text only when the dry-run recommends promotion."""
    if not recommended or not champion_run_id:
        return ""
    return (
        "python -m orchestrator.experiments promote "
        f"{champion_run_id} {candidate_run_id}"
    )


def evidence_paths(
    *,
    run_dir: Path,
    experiments_dir: Path,
    champion: dict[str, object],
) -> list[str]:
    """Return saved artifacts used as evidence."""
    paths = [
        run_dir / "manifest.json",
        run_dir / "diagnosis.json",
        run_dir / "candidate_leaderboard.json",
        run_dir / "candidate_challenger_report.json",
        run_dir / "champion_comparison.json",
    ]
    champion_path = champion.get("path")
    if isinstance(champion_path, str) and champion_path:
        paths.append(Path(champion_path))
    else:
        paths.append(experiments_dir / "champion.json")
    return [str(path) for path in paths if path.exists()]


def recommended_next_actions(
    *,
    status: str,
    blocking_reasons: list[str],
    would_promote: bool,
) -> list[str]:
    """Return compact next actions for operator review."""
    if would_promote:
        return ["Review the dry-run evidence, then run the explicit promote command."]
    if status == "no_champion":
        return ["Create or promote an initial champion before promotion dry-runs can compare."]
    if "candidate_not_accepted" in blocking_reasons:
        return ["Keep iterating until the deterministic policy and holdout gates accept a run."]
    if "candidate_artifacts_not_ok" in blocking_reasons:
        return ["Fix artifact validation before considering promotion."]
    return ["Keep the current champion and continue candidate search."]


def render_champion_promotion_markdown(payload: dict[str, object]) -> str:
    """Render dry-run payload as markdown."""
    champion = object_field(payload, "champion")
    candidate = object_field(payload, "candidate")
    comparison = object_field(payload, "comparison")
    decision = object_field(payload, "dry_run_decision")
    lines = [
        "# Champion Promotion Dry Run",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Current champion: `{champion.get('champion_run_id', '') or 'none'}`",
        f"- Candidate accepted: `{candidate.get('accepted', False)}`",
        f"- Candidate artifact OK: `{candidate.get('artifact_ok', False)}`",
        f"- Would promote: `{decision.get('would_promote', False)}`",
        "",
        "## Comparison",
        "",
        f"- Recommendation: `{comparison.get('recommendation', '')}`",
        f"- Winner: `{comparison.get('winner', '')}`",
        f"- Validation EV delta gap: `{number_text(comparison.get('validation_ev_delta'))}`",
        f"- Dataset match: `{display_value(comparison.get('dataset_match'))}`",
        f"- Summary: {comparison.get('summary', '')}",
        "",
        "## Blocking Reasons",
        "",
    ]
    reasons = string_list(decision.get("blocking_reasons", []))
    lines.extend([f"- `{reason}`" for reason in reasons] or ["- none"])
    command = str(decision.get("promotion_command", ""))
    lines.extend(["", "## Promotion Command", ""])
    lines.append(f"`{command}`" if command else "No promote command is recommended.")
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This artifact is inspection-only and reads saved artifacts only.",
            "- It does not execute agents, run backtests, apply patches, route agents, write champion registry files, append champion history, or change acceptance.",
            "- Promotion still requires an explicit deterministic promote command.",
        ]
    )
    return "\n".join(lines) + "\n"


def validate_champion_promotion_dry_run_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved champion promotion dry-run report."""
    return validate_json_file(
        payload_path=payload_path,
        schema_path=repo_root / SCHEMA_PATH,
    )


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object or return an empty mapping."""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def object_field(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a nested object field."""
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def optional_float(value: object) -> float | None:
    """Return a float from a numeric value, otherwise None."""
    if isinstance(value, int | float):
        return float(value)
    return None


def string_list(value: object) -> list[str]:
    """Return string rows from a possible list."""
    return [str(item) for item in value] if isinstance(value, list) else []


def unique_strings(values: list[str]) -> list[str]:
    """Return stable unique strings."""
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def number_text(value: object) -> str:
    """Return compact number text for markdown."""
    if isinstance(value, int | float):
        return f"{float(value):.6f}"
    return "none"


def display_value(value: object) -> str:
    """Return compact markdown text for scalar values."""
    if value is None:
        return "none"
    return str(value)


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root."""
    return path if path.is_absolute() else repo_root / path


def main() -> None:
    """CLI entrypoint for champion promotion dry-runs."""
    parser = argparse.ArgumentParser(description="Write a champion promotion dry-run.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--min-ev-delta", type=float, default=0.0)
    args = parser.parse_args()
    _, _, payload = write_champion_promotion_dry_run(
        run_dir=args.run_dir,
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
        min_ev_delta=args.min_ev_delta,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
