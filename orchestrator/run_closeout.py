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
    config_lineage = load_json_object(run_dir / "config_lineage.json")
    quality_trace = load_json_object(run_dir / "candidate_quality_trace.json")
    challenger = load_json_object(run_dir / "candidate_challenger_report.json")
    promotion = load_json_object(run_dir / "champion_promotion_dry_run.json")
    approval = load_json_object(run_dir / "champion_promotion_approval.json")
    candidates = load_json_list(run_dir / "candidate_leaderboard.json")
    selected_candidates = [
        compact_candidate(row)
        for row in candidates
        if isinstance(row, dict) and bool(row.get("selected", False))
    ]
    top_candidates = [compact_candidate(row) for row in candidates[:5]]
    artifact_history = object_field(manifest, "artifact_health_history")
    research_focus = object_field(research_brief, "recommended_experiment_focus")
    research_watchlist = object_field(research_brief, "watchlist_summary")
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
            "candidate_quality_trace_present": bool(quality_trace),
            "candidate_quality_selectable_count": int(
                object_field(quality_trace, "summary").get("selectable_count", 0) or 0
            ),
            "candidate_quality_top_failure_code": str(
                object_field(quality_trace, "summary").get("top_failure_code", "")
            ),
            "research_brief_present": bool(research_brief),
            "research_brief_artifact_ok": bool(research_brief.get("artifact_ok", False)),
            "research_watchlist_status": str(
                research_watchlist.get("status", "unknown")
            ),
            "research_watchlist_alert_count": int(
                research_watchlist.get("alert_count", 0) or 0
            ),
            "research_primary_focus": str(
                research_focus.get("primary_focus", "unknown")
            ),
            "config_lineage_present": bool(config_lineage),
            "config_lineage_status": str(config_lineage.get("status", "unknown")),
            "config_lineage_ok": bool(config_lineage.get("ok", False)),
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
        "operator_dashboard": operator_dashboard(
            manifest=manifest,
            scope_health=scope_health,
            research_brief=research_brief,
            config_lineage=config_lineage,
            quality_trace=quality_trace,
            challenger=challenger,
            promotion=promotion,
            approval=approval,
            selected_candidates=selected_candidates,
            closeout_ok=closeout_ok,
            closeout_status=closeout_status,
        ),
        "recommended_next_actions": recommended_next_actions(
            closeout_ok=closeout_ok,
            manifest=manifest,
            scope_health=scope_health,
            research_focus=research_focus,
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
            run_dir / "candidate_quality_trace.json",
            label="candidate_quality_trace",
            required=True,
        ),
        artifact_row(run_dir / "config_lineage.json", label="config_lineage", required=True),
        artifact_row(
            run_dir / "candidate_challenger_report.json",
            label="candidate_challenger_report",
            required=True,
        ),
        artifact_row(
            run_dir / "champion_promotion_dry_run.json",
            label="champion_promotion_dry_run",
            required=True,
        ),
        artifact_row(
            run_dir / "champion_promotion_approval.json",
            label="champion_promotion_approval",
            required=True,
        ),
        artifact_row(
            experiments_dir / "run_artifact_health_history.jsonl",
            label="run_artifact_health_history",
            required=True,
        ),
    ]
    return rows


def operator_dashboard(
    *,
    manifest: dict[str, Any],
    scope_health: dict[str, Any],
    research_brief: dict[str, Any],
    config_lineage: dict[str, Any],
    quality_trace: dict[str, Any],
    challenger: dict[str, Any],
    promotion: dict[str, Any],
    approval: dict[str, Any],
    selected_candidates: list[dict[str, object]],
    closeout_ok: bool,
    closeout_status: str,
) -> dict[str, object]:
    """Return a compact operator-facing dashboard from saved artifacts."""
    config_checks = object_field(config_lineage, "checks")
    quality_summary = object_field(quality_trace, "summary")
    quality_source = object_field(quality_trace, "source")
    promotion_decision = object_field(promotion, "dry_run_decision")
    approval_intent = object_field(approval, "operator_intent")
    watchlist = object_field(research_brief, "watchlist_summary")
    return {
        "schema_version": "operator_dashboard_v1",
        "status_summary": {
            "run_status": str(manifest.get("status", "unknown")),
            "closeout_status": closeout_status,
            "completed_rounds": int(manifest.get("completed_rounds", 0) or 0),
            "accepted": manifest.get("status") == "accepted",
            "accepted_round": manifest.get("accepted_round"),
            "stop_reason": manifest.get("stop_reason"),
            "selected_candidate_count": len(selected_candidates),
        },
        "gates": [
            dashboard_gate(
                gate_name="artifact_health",
                ok=closeout_ok,
                status=closeout_status,
                artifact_path="run_closeout.json",
                details=(
                    "Run closeout is ready for operator review."
                    if closeout_ok
                    else "Run closeout needs artifact or scope attention."
                ),
            ),
            dashboard_gate(
                gate_name="scope_health",
                ok=bool(scope_health.get("ok", False)),
                status=str(scope_health.get("status", "unknown")),
                artifact_path="experiment_scope_health.json",
                details="Experiment scope health is read-only.",
            ),
            dashboard_gate(
                gate_name="config_lineage",
                ok=bool(config_lineage.get("ok", False)),
                status=str(config_lineage.get("status", "missing")),
                artifact_path="config_lineage.json",
                details="Config lineage reads saved config evidence only.",
            ),
            dashboard_gate(
                gate_name="candidate_quality_trace",
                ok=bool(quality_trace),
                status="present" if quality_trace else "missing",
                artifact_path="candidate_quality_trace.json",
                details="Candidate scoring and rejection trace is inspection-only.",
            ),
            dashboard_gate(
                gate_name="champion_review",
                ok=bool(challenger.get("ok", False)),
                status=str(challenger.get("status", "missing")),
                artifact_path="candidate_challenger_report.json",
                details="Champion comparison is inspection-only.",
            ),
            dashboard_gate(
                gate_name="promotion_review",
                ok=bool(promotion.get("ok", False)) and bool(approval.get("ok", False)),
                status=str(approval.get("status", "missing")),
                artifact_path="champion_promotion_approval.json",
                details="Promotion still requires an explicit operator command.",
            ),
        ],
        "config_review": {
            "lineage_status": str(config_lineage.get("status", "missing")),
            "lineage_ok": bool(config_lineage.get("ok", False)),
            "existing_stage_count": int(config_checks.get("existing_stage_count", 0) or 0),
            "current_config_matches_latest_stage": bool(
                config_checks.get("current_config_matches_latest_stage", False)
            ),
            "applied": bool(config_checks.get("applied", False)),
            "restored": bool(config_checks.get("restored", False)),
        },
        "champion_review": {
            "challenger_status": str(challenger.get("status", "missing")),
            "promotion_status": str(promotion.get("status", "missing")),
            "approval_status": str(approval.get("status", "missing")),
            "would_promote": bool(promotion_decision.get("would_promote", False)),
            "approval_recorded": bool(approval_intent.get("approval_recorded", False)),
        },
        "candidate_quality_review": {
            "trace_present": bool(quality_trace),
            "candidate_count": int(quality_summary.get("candidate_count", 0) or 0),
            "selectable_count": int(quality_summary.get("selectable_count", 0) or 0),
            "selected_count": int(quality_summary.get("selected_count", 0) or 0),
            "selected_directions": string_list(
                quality_summary.get("selected_directions", [])
            ),
            "top_failure_code": str(quality_summary.get("top_failure_code", "")),
            "top_quality_component": str(
                quality_summary.get("top_quality_component", "")
            ),
            "source_path": str(quality_source.get("path", "")),
        },
        "watchlist": {
            "status": str(watchlist.get("status", "unknown")),
            "alert_count": int(watchlist.get("alert_count", 0) or 0),
        },
        "operator_action_items": operator_action_items(
            manifest=manifest,
            config_lineage=config_lineage,
            promotion=promotion,
            approval=approval,
            closeout_ok=closeout_ok,
        ),
        "authority": {
            "final_acceptance_authority": "deterministic_code",
            "agent_language_can_accept": False,
            "config_changes_require_guarded_command": True,
            "champion_promotion_requires_explicit_command": True,
        },
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_write_config": True,
            "does_not_promote_champion": True,
            "does_not_apply_patches": True,
            "does_not_route_agents": True,
            "does_not_change_acceptance": True,
        },
    }


def dashboard_gate(
    *,
    gate_name: str,
    ok: bool,
    status: str,
    artifact_path: str,
    details: str,
) -> dict[str, object]:
    """Return one operator dashboard gate row."""
    return {
        "gate_name": gate_name,
        "ok": ok,
        "status": status,
        "artifact_path": artifact_path,
        "details": details,
    }


def operator_action_items(
    *,
    manifest: dict[str, Any],
    config_lineage: dict[str, Any],
    promotion: dict[str, Any],
    approval: dict[str, Any],
    closeout_ok: bool,
) -> list[str]:
    """Return stable operator-facing action items."""
    actions: list[str] = []
    if not closeout_ok:
        actions.append("Review artifact health before starting another run.")
    if not config_lineage or not bool(config_lineage.get("ok", False)):
        actions.append("Regenerate or inspect config_lineage.json before config changes.")
    if promotion and object_field(promotion, "dry_run_decision").get("would_promote") is True:
        if not object_field(approval, "operator_intent").get("approval_recorded", False):
            actions.append("Review champion promotion approval before promoting.")
    if manifest.get("status") == "stopped_repeated_proposal":
        actions.append("Use a different deterministic modifier profile next.")
    if not actions:
        actions.append("Review selected candidates and research brief before the next run.")
    return actions


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
    research_focus: dict[str, Any],
    selected_candidates: list[dict[str, object]],
) -> list[str]:
    """Return deterministic next-step hints for operator review."""
    if not closeout_ok:
        return ["Inspect run_closeout.json and experiment_scope_health.json before reuse."]
    primary_focus = str(research_focus.get("primary_focus", ""))
    avoid = string_list(research_focus.get("avoid_directions", []))
    suggested = string_list(research_focus.get("suggested_directions", []))
    if primary_focus == "repair_artifact_pipeline":
        return ["Fix artifact health before starting another iteration."]
    if primary_focus == "switch_modifier_direction":
        avoid_text = ", ".join(avoid) if avoid else "the repeated direction"
        suggested_text = ", ".join(suggested) if suggested else "a different profile"
        return [
            "Start the next deterministic iteration with "
            f"{suggested_text}; avoid {avoid_text}."
        ]
    if primary_focus == "close_champion_ev_gap":
        suggested_text = ", ".join(suggested) if suggested else "a fresh direction"
        return [
            "Prioritize a candidate direction that can close the champion EV gap; "
            f"next deterministic probe: {suggested_text}."
        ]
    if primary_focus == "analyze_rejection_reasons":
        return ["Review selected candidate rejection reasons before reusing the same modifier."]
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
        f"- Research watchlist: `{summary.get('research_watchlist_status', 'unknown')}` "
        f"({summary.get('research_watchlist_alert_count', 0)} alert(s))",
        f"- Research focus: `{summary.get('research_primary_focus', 'unknown')}`",
        f"- Config lineage: `{summary.get('config_lineage_status', 'unknown')}` "
        f"(ok: `{summary.get('config_lineage_ok', False)}`)",
        "",
        "## Operator Dashboard",
        "",
    ]
    dashboard = object_field(payload, "operator_dashboard")
    config_review = object_field(dashboard, "config_review")
    champion_review = object_field(dashboard, "champion_review")
    watchlist = object_field(dashboard, "watchlist")
    quality_review = object_field(dashboard, "candidate_quality_review")
    lines.extend(
        [
            f"- Config lineage: `{config_review.get('lineage_status', 'unknown')}` "
            f"({config_review.get('existing_stage_count', 0)} stage(s))",
            "- Config matches latest stage: "
            f"`{config_review.get('current_config_matches_latest_stage', False)}`",
            f"- Champion challenger: `{champion_review.get('challenger_status', 'unknown')}`",
            f"- Candidate quality trace: `{quality_review.get('top_failure_code', '')}` "
            f"({quality_review.get('selectable_count', 0)} selectable)",
            f"- Promotion approval: `{champion_review.get('approval_status', 'unknown')}`",
            f"- Watchlist: `{watchlist.get('status', 'unknown')}` "
            f"({watchlist.get('alert_count', 0)} alert(s))",
            "",
            "| Gate | OK | Status | Artifact |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in list_of_dicts(dashboard.get("gates", [])):
        lines.append(
            "| "
            f"{row.get('gate_name', '')} | "
            f"{row.get('ok', False)} | "
            f"{row.get('status', '')} | "
            f"`{row.get('artifact_path', '')}` |"
        )
    lines.extend(["", "## Operator Action Items", ""])
    lines.extend(
        f"- {action}"
        for action in string_list(dashboard.get("operator_action_items", []))
    )
    lines.extend(["", "## Next Actions", ""])
    lines.extend(
        f"- {action}"
        for action in string_list(payload.get("recommended_next_actions", []))
    )
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
    schema_errors = tuple(
        validate_json_file(
            payload_path=payload_path,
            schema_path=repo_root / SCHEMA_PATH,
        )
    )
    if schema_errors:
        return schema_errors
    payload = load_json_object(payload_path)
    expected = build_run_closeout(
        run_dir=run_closeout_run_dir(
            payload=payload,
            payload_path=payload_path,
            repo_root=repo_root,
        ),
        experiments_dir=run_closeout_experiments_dir(
            payload=payload,
            payload_path=payload_path,
            repo_root=repo_root,
        ),
        repo_root=repo_root,
    )
    if payload != expected:
        return ("run_closeout current evidence mismatch",)
    return ()


def run_closeout_run_dir(
    *,
    payload: dict[str, Any],
    payload_path: Path,
    repo_root: Path,
) -> Path:
    """Return the run directory recorded by a closeout payload."""
    raw_path = str(payload.get("run_dir", ""))
    return resolve_path(Path(raw_path), repo_root) if raw_path else payload_path.parent


def run_closeout_experiments_dir(
    *,
    payload: dict[str, Any],
    payload_path: Path,
    repo_root: Path,
) -> Path:
    """Return the experiments directory recorded by a closeout payload."""
    raw_path = str(payload.get("experiments_dir", ""))
    if raw_path:
        return resolve_path(Path(raw_path), repo_root)
    return payload_path.parent.parent


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
