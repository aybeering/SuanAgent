"""Read-only dry run for manually applying approved config candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.operator_config_review import (
    OPERATOR_CONFIG_REVIEW_SCHEMA_VERSION,
    build_operator_config_review,
)
from orchestrator.schema_validation import (
    load_schema,
    validate_json_file,
    validate_json_payload,
)


CONFIG_APPLICATION_DRY_RUN_SCHEMA_VERSION = "config_application_dry_run_v1"
SCHEMA_PATH = Path("schemas/config_application_dry_run.schema.json")
DEFAULT_CONFIG_PATH = Path("config/default.json")


def write_config_application_dry_run(
    *,
    run_dir: Path,
    repo_root: Path,
    experiments_dir: Path | None = None,
    config_path: Path | None = None,
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown config application dry-run artifacts."""
    payload = build_config_application_dry_run(
        run_dir=run_dir,
        repo_root=repo_root,
        experiments_dir=experiments_dir,
        config_path=config_path,
    )
    errors = validate_config_application_dry_run_payload(
        payload,
        run_dir=run_dir,
        repo_root=repo_root,
        experiments_dir=experiments_dir,
        config_path=config_path,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "config application dry run failed schema validation: "
            + "; ".join(errors)
        )
    json_path = run_dir / "config_application_dry_run.json"
    md_path = run_dir / "config_application_dry_run.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(
        render_config_application_dry_run_markdown(payload),
        encoding="utf-8",
    )
    return json_path, md_path, payload


def build_config_application_dry_run(
    *,
    run_dir: Path,
    repo_root: Path,
    experiments_dir: Path | None = None,
    config_path: Path | None = None,
) -> dict[str, object]:
    """Return a deterministic dry run for applying approved config changes."""
    repo_root = repo_root.resolve()
    run_dir = run_dir.resolve()
    resolved_config_path = resolve_config_path(
        repo_root=repo_root,
        config_path=config_path,
    )
    review_path = run_dir / "operator_config_review.json"
    if review_path.exists():
        review_payload = load_json_object(review_path)
        review_from_artifact = True
    else:
        review_payload = build_operator_config_review(
            run_dir=run_dir,
            repo_root=repo_root,
            experiments_dir=experiments_dir,
        )
        review_from_artifact = False
    config_payload = load_json_object(resolved_config_path)
    operator_intent = object_value(review_payload.get("operator_intent", {}))
    review_recorded = bool(operator_intent.get("review_recorded", False))
    decision_requested = str(operator_intent.get("decision_requested", ""))
    reviewed_changes = list_of_objects(review_payload.get("reviewed_changes", []))
    planned_changes = build_planned_changes(
        reviewed_changes=reviewed_changes,
        config_payload=config_payload,
    )
    blockers = application_blockers(
        review_payload=review_payload,
        reviewed_changes=reviewed_changes,
        planned_changes=planned_changes,
        config_payload=config_payload,
        review_recorded=review_recorded,
        decision_requested=decision_requested,
    )
    eligible = bool(not blockers and planned_changes)
    payload: dict[str, object] = {
        "schema_version": CONFIG_APPLICATION_DRY_RUN_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": relative_path(run_dir, repo_root),
        "status": application_status(
            review_payload=review_payload,
            reviewed_changes=reviewed_changes,
            planned_changes=planned_changes,
            blockers=blockers,
        ),
        "ok": bool(review_payload and config_payload),
        "source_operator_review": {
            "artifact_name": "operator_config_review",
            "from_artifact": review_from_artifact,
            "file": file_record(review_path, repo_root),
        },
        "source_config": {
            "artifact_name": "config",
            "file": file_record(resolved_config_path, repo_root),
        },
        "operator_intent": {
            "review_recorded": review_recorded,
            "decision_requested": decision_requested,
            "operator_id": str(operator_intent.get("operator_id", "")),
            "target_candidate_ids": string_list(
                operator_intent.get("target_candidate_ids", [])
            ),
            "confirmation_phrase_matches": bool(
                operator_intent.get("confirmation_phrase_matches", False)
            ),
        },
        "application_gate": {
            "eligible_for_manual_application": eligible,
            "application_blockers": blockers,
            "approved_change_count": sum(
                1
                for change in planned_changes
                if change.get("review_decision") == "approved"
            ),
            "ready_change_count": sum(
                1 for change in planned_changes if change.get("ready_for_manual_edit")
            ),
            "requires_operator_review_artifact": True,
            "requires_approved_operator_review": True,
            "requires_config_value_match": True,
            "config_changes_must_be_manual": True,
        },
        "planned_changes": planned_changes,
        "recommended_next_actions": recommended_next_actions(
            eligible=eligible,
            blockers=blockers,
            planned_changes=planned_changes,
        ),
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "does_not_write_config": True,
            "does_not_delete_memory": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_route_candidates": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
            "dry_run_only": True,
            "config_changes_still_require_manual_edit": True,
        },
    }
    return payload


def build_planned_changes(
    *,
    reviewed_changes: list[dict[str, object]],
    config_payload: dict[str, object],
) -> list[dict[str, object]]:
    """Return application rows for approved or reviewed config changes."""
    rows: list[dict[str, object]] = []
    for change in reviewed_changes:
        config_path = str(change.get("config_path", ""))
        current_path_exists = path_exists(config_payload, config_path)
        current_config_value = value_at_path(config_payload, config_path)
        reviewed_current_value = change.get("current_value")
        proposed_value = change.get("proposed_value")
        value_matches_review = current_config_value == reviewed_current_value
        selected = (
            str(change.get("review_decision", "")) == "approved"
            and bool(change.get("selected_for_review", False))
        )
        ready = bool(selected and value_matches_review)
        rows.append(
            {
                "candidate_id": str(change.get("candidate_id", "")),
                "config_path": config_path,
                "review_decision": str(change.get("review_decision", "")),
                "selected_for_application": selected,
                "current_config_value": current_config_value,
                "current_config_path_exists": current_path_exists,
                "reviewed_current_value": reviewed_current_value,
                "proposed_value": proposed_value,
                "value_matches_review": value_matches_review,
                "would_change_config": bool(current_config_value != proposed_value),
                "ready_for_manual_edit": ready,
                "applied": False,
                "requires_manual_config_edit": True,
                "source_artifact": "operator_config_review.json",
            }
        )
    return rows


def application_blockers(
    *,
    review_payload: dict[str, object],
    reviewed_changes: list[dict[str, object]],
    planned_changes: list[dict[str, object]],
    config_payload: dict[str, object],
    review_recorded: bool,
    decision_requested: str,
) -> list[str]:
    """Return deterministic blockers for manual config application."""
    blockers: list[str] = []
    if not review_payload:
        blockers.append("missing_operator_config_review")
    if (
        review_payload
        and review_payload.get("schema_version") != OPERATOR_CONFIG_REVIEW_SCHEMA_VERSION
    ):
        blockers.append("operator_config_review_schema_invalid")
    if not config_payload:
        blockers.append("missing_or_invalid_config")
    if not reviewed_changes:
        blockers.append("no_reviewed_changes")
    if not review_recorded:
        blockers.append("operator_review_not_recorded")
    if decision_requested != "approve":
        blockers.append("operator_review_not_approved")
    approved_changes = [
        change
        for change in planned_changes
        if change.get("review_decision") == "approved"
    ]
    if not approved_changes:
        blockers.append("no_approved_changes")
    if any(not bool(change.get("value_matches_review", False)) for change in approved_changes):
        blockers.append("current_config_value_mismatch")
    if any(not bool(change.get("would_change_config", False)) for change in approved_changes):
        blockers.append("approved_change_already_present")
    return unique_strings(blockers)


def application_status(
    *,
    review_payload: dict[str, object],
    reviewed_changes: list[dict[str, object]],
    planned_changes: list[dict[str, object]],
    blockers: list[str],
) -> str:
    """Return compact dry-run status."""
    if not review_payload:
        return "needs_operator_review"
    if not reviewed_changes:
        return "no_candidate_changes"
    if not blockers and planned_changes:
        return "ready_for_manual_application"
    if "no_approved_changes" in blockers or "operator_review_not_approved" in blockers:
        return "no_approved_changes"
    return "application_blocked"


def recommended_next_actions(
    *,
    eligible: bool,
    blockers: list[str],
    planned_changes: list[dict[str, object]],
) -> list[str]:
    """Return deterministic next actions for the dry run."""
    if eligible:
        return ["Manually edit config only after reviewing this dry-run report."]
    if not planned_changes:
        return ["No config application is available for this run."]
    if "operator_review_not_recorded" in blockers:
        return ["Record operator approval or rejection before applying config."]
    if "operator_review_not_approved" in blockers:
        return ["Keep config unchanged unless a future approval is recorded."]
    if "current_config_value_mismatch" in blockers:
        return ["Refresh the candidate because current config no longer matches review."]
    return ["Keep config unchanged and review the application blockers."]


def render_config_application_dry_run_markdown(payload: dict[str, object]) -> str:
    """Render config application dry run as markdown."""
    gate = object_value(payload.get("application_gate", {}))
    lines = [
        "# Config Application Dry Run",
        "",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Eligible for manual application: `{gate.get('eligible_for_manual_application', False)}`",
        f"- Approved changes: `{gate.get('approved_change_count', 0)}`",
        f"- Ready changes: `{gate.get('ready_change_count', 0)}`",
        "",
        "## Planned Changes",
        "",
    ]
    rows = list_of_objects(payload.get("planned_changes", []))
    if not rows:
        lines.append("No config changes are available for application dry run.")
    else:
        lines.extend(
            [
                "| Candidate | Config Path | Current | Proposed | Decision | Ready |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in rows:
            lines.append(
                "| "
                f"{row.get('candidate_id', '')} | "
                f"{row.get('config_path', '')} | "
                f"{json.dumps(row.get('current_config_value', ''), sort_keys=True)} | "
                f"{json.dumps(row.get('proposed_value', ''), sort_keys=True)} | "
                f"{row.get('review_decision', '')} | "
                f"{row.get('ready_for_manual_edit', False)} |"
            )
    lines.extend(["", "## Application Blockers", ""])
    blockers = string_list(gate.get("application_blockers", []))
    lines.extend([f"- `{blocker}`" for blocker in blockers] or ["- none"])
    lines.extend(
        [
            "",
            "This artifact is a dry run only. It does not write config, execute agents, run backtests, route candidates, apply patches, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_config_application_dry_run_file(
    *,
    payload_path: Path,
    repo_root: Path,
) -> tuple[str, ...]:
    """Validate a saved config application dry-run report."""
    return tuple(
        validate_json_file(
            payload_path=payload_path,
            schema_path=repo_root / SCHEMA_PATH,
        )
    )


def validate_config_application_dry_run_payload(
    payload: dict[str, object],
    *,
    run_dir: Path,
    repo_root: Path,
    experiments_dir: Path | None = None,
    config_path: Path | None = None,
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an in-memory config application dry-run payload."""
    repo_root = repo_root.resolve()
    run_dir = run_dir.resolve()
    normalized = dict(payload)
    normalized.pop("from_artifact", None)
    schema = load_schema(repo_root / SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=normalized,
            schema=schema,
            schema_dir=(repo_root / SCHEMA_PATH).parent,
        )
    )
    errors.extend(
        validate_config_application_dry_run_consistency(
            normalized,
            run_dir=run_dir,
            repo_root=repo_root,
        )
    )
    if require_current_evidence:
        expected = build_config_application_dry_run(
            run_dir=run_dir,
            repo_root=repo_root,
            experiments_dir=experiments_dir,
            config_path=config_path,
        )
        if normalized != expected:
            errors.append("config_application_dry_run current evidence mismatch")
    return tuple(errors)


def validate_config_application_dry_run_consistency(
    payload: dict[str, object],
    *,
    run_dir: Path,
    repo_root: Path,
) -> tuple[str, ...]:
    """Return stable internal consistency errors for config application dry runs."""
    errors: list[str] = []
    if str(payload.get("run_id", "")) != run_dir.name:
        errors.append("config_application_dry_run run_id mismatch")
    if str(payload.get("run_dir", "")) != relative_path(run_dir, repo_root):
        errors.append("config_application_dry_run run_dir mismatch")
    intent = object_value(payload.get("operator_intent", {}))
    gate = object_value(payload.get("application_gate", {}))
    rows = list_of_objects(payload.get("planned_changes", []))
    blockers = string_list(gate.get("application_blockers", []))
    review_recorded = bool(intent.get("review_recorded", False))
    decision_requested = str(intent.get("decision_requested", ""))
    expected_eligible = bool(not blockers and rows)
    if bool(gate.get("eligible_for_manual_application", False)) != expected_eligible:
        errors.append("config_application_dry_run eligible mismatch")
    expected_approved = sum(
        1 for row in rows if row.get("review_decision") == "approved"
    )
    expected_ready = sum(1 for row in rows if row.get("ready_for_manual_edit"))
    if int(gate.get("approved_change_count", -1) or 0) != expected_approved:
        errors.append("config_application_dry_run approved count mismatch")
    if int(gate.get("ready_change_count", -1) or 0) != expected_ready:
        errors.append("config_application_dry_run ready count mismatch")
    for row in rows:
        selected = str(row.get("review_decision", "")) == "approved" and bool(
            row.get("selected_for_application", False)
        )
        value_matches = row.get("current_config_value") == row.get(
            "reviewed_current_value"
        )
        would_change = row.get("current_config_value") != row.get("proposed_value")
        ready = bool(selected and value_matches)
        if bool(row.get("value_matches_review", False)) != value_matches:
            errors.append("config_application_dry_run value match mismatch")
        if "current_config_path_exists" in row and not isinstance(
            row.get("current_config_path_exists"),
            bool,
        ):
            errors.append("config_application_dry_run path exists invalid")
        if bool(row.get("would_change_config", False)) != would_change:
            errors.append("config_application_dry_run would change mismatch")
        if bool(row.get("ready_for_manual_edit", False)) != ready:
            errors.append("config_application_dry_run ready row mismatch")
        if bool(row.get("applied", True)):
            errors.append("config_application_dry_run applied flag must be false")
        if not bool(row.get("requires_manual_config_edit", False)):
            errors.append("config_application_dry_run requires manual edit false")
    expected_status = application_status(
        review_payload={"schema_version": OPERATOR_CONFIG_REVIEW_SCHEMA_VERSION}
        if bool(payload.get("ok", False))
        else {},
        reviewed_changes=rows,
        planned_changes=rows,
        blockers=blockers,
    )
    if str(payload.get("status", "")) != expected_status:
        errors.append("config_application_dry_run status mismatch")
    expected_actions = recommended_next_actions(
        eligible=expected_eligible,
        blockers=blockers,
        planned_changes=rows,
    )
    if payload.get("recommended_next_actions") != expected_actions:
        errors.append("config_application_dry_run next actions mismatch")
    if review_recorded and decision_requested == "approve" and expected_approved == 0:
        errors.append("config_application_dry_run approval count missing")
    return tuple(errors)


def resolve_config_path(*, repo_root: Path, config_path: Path | None) -> Path:
    """Return an absolute config path."""
    candidate = config_path or DEFAULT_CONFIG_PATH
    return candidate if candidate.is_absolute() else repo_root / candidate


def value_at_path(payload: dict[str, object], dotted_path: str) -> object:
    """Return a nested JSON value for a dotted config path."""
    value: object = payload
    for part in dotted_path.split("."):
        if not part:
            return None
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def path_exists(payload: dict[str, object], dotted_path: str) -> bool:
    """Return whether a dotted JSON path exists."""
    value: object = payload
    for part in dotted_path.split("."):
        if not part:
            return False
        if not isinstance(value, dict) or part not in value:
            return False
        value = value[part]
    return True


def load_json_object(path: Path) -> dict[str, object]:
    """Load a JSON object, returning an empty object if unavailable."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


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


def unique_strings(values: list[str]) -> list[str]:
    """Return unique strings in first-seen order."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


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


def main() -> None:
    """CLI entrypoint for config application dry-run reports."""
    parser = argparse.ArgumentParser(description="Write a config application dry run.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--experiments-dir", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args()
    _, _, payload = write_config_application_dry_run(
        run_dir=args.run_dir,
        repo_root=args.repo_root,
        experiments_dir=args.experiments_dir,
        config_path=args.config,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
