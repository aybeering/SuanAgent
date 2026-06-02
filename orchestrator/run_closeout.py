"""Deterministic run closeout report for completed iteration runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.schema_validation import validate_json_file


RUN_CLOSEOUT_SCHEMA_VERSION = "run_closeout_v1"
SCHEMA_PATH = Path("schemas/run_closeout.schema.json")


def write_run_closeout(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown run closeout artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    payload = build_run_closeout(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    json_path = run_dir / "run_closeout.json"
    md_path = run_dir / "run_closeout.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_run_closeout_markdown(payload), encoding="utf-8")
    errors = validate_run_closeout_file(payload_path=json_path, repo_root=repo_root)
    if errors:
        raise ValueError(f"run closeout failed schema validation: {errors}")
    return json_path, md_path, payload


def build_run_closeout(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return a deterministic closeout payload from saved run artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    manifest = load_json_object(run_dir / "manifest.json")
    scope_health = load_json_object(run_dir / "experiment_scope_health.json")
    research_brief = load_json_object(run_dir / "research_brief.json")
    candidates = load_json_list(run_dir / "candidate_leaderboard.json")
    selected_candidates = [
        compact_candidate(row)
        for row in candidates
        if isinstance(row, dict) and bool(row.get("selected", False))
    ]
    top_candidates = [compact_candidate(row) for row in candidates[:5]]
    artifact_history = object_field(manifest, "artifact_health_history")
    run_id = str(manifest.get("run_id", run_dir.name))
    closeout_ok = closeout_checks_pass(
        manifest=manifest,
        scope_health=scope_health,
        artifact_history=artifact_history,
    )
    closeout_status = "ready_for_review" if closeout_ok else "needs_attention"
    payload: dict[str, object] = {
        "schema_version": RUN_CLOSEOUT_SCHEMA_VERSION,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "experiments_dir": str(experiments_dir),
        "status": str(manifest.get("status", "unknown")),
        "closeout_status": closeout_status,
        "ok": closeout_ok,
        "summary": {
            "completed_rounds": int(manifest.get("completed_rounds", 0) or 0),
            "accepted_round": manifest.get("accepted_round"),
            "stop_reason": manifest.get("stop_reason"),
            "final_strategy_commit": manifest.get("final_strategy_commit"),
            "scope_health_ok": bool(scope_health.get("ok", False)),
            "scope_health_status": str(scope_health.get("status", "unknown")),
            "artifact_health_history_recorded": bool(
                artifact_history.get("recorded", False)
            ),
            "artifact_health_history_ok": bool(artifact_history.get("ok", False)),
            "candidate_count": len(candidates),
            "selected_candidate_count": len(selected_candidates),
            "research_brief_present": bool(research_brief),
            "research_brief_artifact_ok": bool(research_brief.get("artifact_ok", False)),
        },
        "artifacts": artifact_rows(run_dir=run_dir, experiments_dir=experiments_dir),
        "selected_candidates": selected_candidates,
        "top_candidates": top_candidates,
        "decision_record": {
            "accepted": manifest.get("status") == "accepted",
            "accepted_round": manifest.get("accepted_round"),
            "acceptance_source": "deterministic_policy_and_holdout_gates",
            "final_acceptance_authority": "deterministic_code",
            "agent_language_can_accept": False,
        },
        "recommended_next_actions": recommended_next_actions(
            closeout_ok=closeout_ok,
            manifest=manifest,
            scope_health=scope_health,
            selected_candidates=selected_candidates,
        ),
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
            "does_not_route_agents": True,
        },
    }
    return payload


def closeout_checks_pass(
    *,
    manifest: dict[str, Any],
    scope_health: dict[str, Any],
    artifact_history: dict[str, Any],
) -> bool:
    """Return whether the saved run is ready for operator review."""
    return (
        bool(manifest)
        and bool(scope_health.get("ok", False))
        and bool(artifact_history.get("recorded", False))
        and bool(artifact_history.get("ok", False))
        and bool(manifest.get("final_strategy_commit"))
    )


def artifact_rows(*, run_dir: Path, experiments_dir: Path) -> list[dict[str, object]]:
    """Return closeout source artifact rows."""
    rows = [
        artifact_row(run_dir / "manifest.json", label="manifest", required=True),
        artifact_row(run_dir / "summary.md", label="summary", required=True),
        artifact_row(
            run_dir / "experiment_scope_health.json",
            label="experiment_scope_health",
            required=True,
        ),
        artifact_row(run_dir / "research_brief.json", label="research_brief", required=False),
        artifact_row(
            run_dir / "candidate_leaderboard.json",
            label="candidate_leaderboard",
            required=True,
        ),
        artifact_row(
            run_dir / "candidate_challenger_report.json",
            label="candidate_challenger_report",
            required=True,
        ),
        artifact_row(
            experiments_dir / "run_artifact_health_history.jsonl",
            label="run_artifact_health_history",
            required=True,
        ),
    ]
    return rows


def artifact_row(path: Path, *, label: str, required: bool) -> dict[str, object]:
    """Return one artifact presence row."""
    return {
        "label": label,
        "path": str(path),
        "required": required,
        "present": path.exists(),
    }


def compact_candidate(row: dict[str, Any]) -> dict[str, object]:
    """Return a compact closeout candidate row."""
    return {
        "round_id": row.get("round_id", ""),
        "role": row.get("role", ""),
        "profile_name": row.get("profile_name", ""),
        "agent_name": row.get("agent_name", ""),
        "direction_tag": row.get("direction_tag", ""),
        "selected": bool(row.get("selected", False)),
        "status": row.get("status", ""),
        "candidate_score": row.get("candidate_score", 0),
        "quality_breakdown": row.get("quality_breakdown", {}),
        "probe_ev_delta": row.get("probe_ev_delta", 0.0),
        "validation_ev_delta": row.get("validation_ev_delta"),
        "holdout_ev_delta": row.get("holdout_ev_delta"),
        "selection_reason": row.get("selection_reason", ""),
    }


def recommended_next_actions(
    *,
    closeout_ok: bool,
    manifest: dict[str, Any],
    scope_health: dict[str, Any],
    selected_candidates: list[dict[str, object]],
) -> list[str]:
    """Return deterministic next-step hints for operator review."""
    if not closeout_ok:
        return ["Inspect run_closeout.json and experiment_scope_health.json before reuse."]
    status = str(manifest.get("status", "unknown"))
    if status == "accepted":
        return ["Review accepted strategy commit before promoting or reusing it."]
    if status == "stopped_repeated_proposal":
        return ["Try a different deterministic modifier direction or profile."]
    if selected_candidates:
        return ["Inspect selected candidate reasons and tune deterministic modifier search."]
    if not bool(scope_health.get("ok", False)):
        return ["Resolve artifact health issues before starting another iteration."]
    return ["Review research_brief.json for the next deterministic experiment direction."]


def render_run_closeout_markdown(payload: dict[str, object]) -> str:
    """Render closeout payload as markdown."""
    summary = object_field(payload, "summary")
    lines = [
        "# Run Closeout",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- Closeout status: `{payload.get('closeout_status', '')}`",
        f"- OK: `{str(payload.get('ok', False)).lower()}`",
        "",
        "## Summary",
        "",
        f"- Completed rounds: `{summary.get('completed_rounds', 0)}`",
        f"- Accepted round: `{summary.get('accepted_round')}`",
        f"- Stop reason: `{summary.get('stop_reason')}`",
        f"- Scope health: `{summary.get('scope_health_status')}`",
        f"- Artifact history recorded: `{summary.get('artifact_health_history_recorded')}`",
        f"- Candidate count: `{summary.get('candidate_count', 0)}`",
        f"- Selected candidates: `{summary.get('selected_candidate_count', 0)}`",
        "",
        "## Next Actions",
        "",
    ]
    lines.extend(f"- {action}" for action in string_list(payload.get("recommended_next_actions", [])))
    lines.extend(["", "## Selected Candidates", ""])
    selected = list_of_dicts(payload.get("selected_candidates", []))
    if not selected:
        lines.append("No selected candidates.")
    else:
        lines.extend(
            [
                "| Round | Profile | Direction | Status | Quality | Score | Probe EV | Validation EV | Holdout EV |",
                "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in selected:
            lines.append(
                "| "
                f"{row.get('round_id', '')} | "
                f"{row.get('profile_name', '')} | "
                f"{row.get('direction_tag', '')} | "
                f"{row.get('status', '')} | "
                f"{quality_breakdown_label(row.get('quality_breakdown', {}))} | "
                f"{row.get('candidate_score', 0)} | "
                f"{row.get('probe_ev_delta', 0.0)} | "
                f"{row.get('validation_ev_delta', '')} | "
                f"{row.get('holdout_ev_delta', '')} |"
            )
    return "\n".join(lines) + "\n"


def quality_breakdown_label(value: object) -> str:
    """Return compact quality component text."""
    if not isinstance(value, dict):
        return "none"
    components = value.get("components", [])
    if not isinstance(components, list):
        return "none"
    named = [
        component
        for component in components
        if isinstance(component, dict) and int(component.get("score_delta", 0)) != 0
    ]
    if not named:
        return "none"
    return "; ".join(
        f"{component.get('name', '')}={int(component.get('score_delta', 0))}"
        for component in named[:3]
    )


def validate_run_closeout_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved run closeout report."""
    return validate_json_file(
        payload_path=payload_path,
        schema_path=repo_root / SCHEMA_PATH,
    )


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object or return an empty object."""
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
    """CLI entrypoint for run closeout generation."""
    parser = argparse.ArgumentParser(description="Write a deterministic run closeout report.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    _, _, payload = write_run_closeout(
        run_dir=args.run_dir,
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
