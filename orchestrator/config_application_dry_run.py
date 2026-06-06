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
    effective_repo_root = infer_repo_root_from_payload_path(payload_path, repo_root)
    errors = list(
        validate_json_file(
            payload_path=payload_path,
            schema_path=effective_repo_root / SCHEMA_PATH,
        )
    )
    if payload_path.exists():
        payload = load_json_object(payload_path)
        errors.extend(
            validate_config_application_dry_run_payload(
                payload,
                run_dir=payload_path.parent,
                repo_root=effective_repo_root,
                experiments_dir=payload_path.parent.parent,
                config_path=config_path_from_payload(
                    payload,
                    repo_root=effective_repo_root,
                ),
            )
        )
        current_errors = validate_config_application_dry_run_current_evidence(
            payload,
            run_dir=payload_path.parent,
            repo_root=effective_repo_root,
            experiments_dir=payload_path.parent.parent,
            config_path=config_path_from_payload(
                payload,
                repo_root=effective_repo_root,
            ),
        )
        errors.extend(current_errors)
        if current_errors:
            errors.append("config_application_dry_run current evidence mismatch")
    return tuple(errors)


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
        errors.extend(
            validate_config_application_dry_run_current_evidence(
                normalized,
                run_dir=run_dir,
                repo_root=repo_root,
                experiments_dir=experiments_dir,
                config_path=config_path,
            )
        )
        expected = build_config_application_dry_run(
            run_dir=run_dir,
            repo_root=repo_root,
            experiments_dir=experiments_dir,
            config_path=config_path,
        )
        if normalized != expected:
            errors.append("config_application_dry_run current evidence mismatch")
    return tuple(errors)


def validate_config_application_dry_run_current_evidence(
    payload: dict[str, object],
    *,
    run_dir: Path,
    repo_root: Path,
    experiments_dir: Path | None = None,
    config_path: Path | None = None,
) -> tuple[str, ...]:
    """Validate dry-run fields against current review and config evidence."""
    errors: list[str] = []
    expected = build_config_application_dry_run(
        run_dir=run_dir,
        repo_root=repo_root,
        experiments_dir=experiments_dir,
        config_path=config_path,
    )
    append_field_mismatches(
        errors,
        prefix="config_application_dry_run",
        payload=payload,
        expected=expected,
        field_names=("run_id", "run_dir", "status", "ok"),
    )
    append_field_mismatches(
        errors,
        prefix="config_application_dry_run source_operator_review",
        payload=object_value(payload.get("source_operator_review", {})),
        expected=object_value(expected.get("source_operator_review", {})),
        field_names=("artifact_name", "from_artifact", "file"),
    )
    append_field_mismatches(
        errors,
        prefix="config_application_dry_run source_config",
        payload=object_value(payload.get("source_config", {})),
        expected=object_value(expected.get("source_config", {})),
        field_names=("artifact_name", "file"),
    )
    append_field_mismatches(
        errors,
        prefix="config_application_dry_run operator_intent",
        payload=object_value(payload.get("operator_intent", {})),
        expected=object_value(expected.get("operator_intent", {})),
        field_names=tuple(object_value(expected.get("operator_intent", {}))),
    )
    append_field_mismatches(
        errors,
        prefix="config_application_dry_run application_gate",
        payload=object_value(payload.get("application_gate", {})),
        expected=object_value(expected.get("application_gate", {})),
        field_names=tuple(object_value(expected.get("application_gate", {}))),
    )
    rows = list_of_objects(payload.get("planned_changes", []))
    expected_rows = list_of_objects(expected.get("planned_changes", []))
    if len(rows) != len(expected_rows):
        errors.append("config_application_dry_run planned_changes count mismatch")
    for index, row in enumerate(rows):
        expected_row = expected_rows[index] if index < len(expected_rows) else {}
        append_field_mismatches(
            errors,
            prefix=f"config_application_dry_run planned_changes {index}",
            payload=row,
            expected=expected_row,
            field_names=tuple(expected_row),
        )
    if payload.get("recommended_next_actions") != expected.get(
        "recommended_next_actions"
    ):
        errors.append("config_application_dry_run next actions mismatch")
    append_field_mismatches(
        errors,
        prefix="config_application_dry_run policy",
        payload=object_value(payload.get("policy", {})),
        expected=object_value(expected.get("policy", {})),
        field_names=tuple(object_value(expected.get("policy", {}))),
    )
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
    source_review = object_value(payload.get("source_operator_review", {}))
    source_review_file = object_value(source_review.get("file", {}))
    review_path = resolve_repo_path(
        Path(str(source_review_file.get("path", ""))),
        repo_root,
    )
    source_config = object_value(payload.get("source_config", {}))
    source_config_file = object_value(source_config.get("file", {}))
    config_path = resolve_repo_path(
        Path(str(source_config_file.get("path", ""))),
        repo_root,
    )
    review_payload = load_json_object(review_path)
    if source_review.get("artifact_name") != "operator_config_review":
        errors.append("config_application_dry_run source review artifact mismatch")
    if str(source_review_file.get("sha256", "")) != file_sha256(review_path):
        errors.append("config_application_dry_run source review digest mismatch")
    if source_config.get("artifact_name") != "config":
        errors.append("config_application_dry_run source config artifact mismatch")
    if str(source_config_file.get("sha256", "")) != file_sha256(config_path):
        errors.append("config_application_dry_run source config digest mismatch")
    intent = object_value(payload.get("operator_intent", {}))
    gate = object_value(payload.get("application_gate", {}))
    rows = list_of_objects(payload.get("planned_changes", []))
    review_recorded = bool(intent.get("review_recorded", False))
    decision_requested = str(intent.get("decision_requested", ""))
    review_intent = object_value(review_payload.get("operator_intent", {}))
    expected_intent = {
        "review_recorded": bool(review_intent.get("review_recorded", False)),
        "decision_requested": str(review_intent.get("decision_requested", "")),
        "operator_id": str(review_intent.get("operator_id", "")),
        "target_candidate_ids": string_list(
            review_intent.get("target_candidate_ids", [])
        ),
        "confirmation_phrase_matches": bool(
            review_intent.get("confirmation_phrase_matches", False)
        ),
    }
    append_field_mismatches(
        errors,
        prefix="config_application_dry_run operator_intent",
        payload=intent,
        expected=expected_intent,
        field_names=tuple(expected_intent),
    )
    expected_blockers = expected_application_blockers(
        review_payload=review_payload,
        rows=rows,
        payload_ok=bool(payload.get("ok", False)),
        review_recorded=review_recorded,
        decision_requested=decision_requested,
    )
    expected_eligible = bool(not expected_blockers and rows)
    if bool(gate.get("eligible_for_manual_application", False)) != expected_eligible:
        errors.append("config_application_dry_run eligible mismatch")
    expected_approved = sum(
        1 for row in rows if row.get("review_decision") == "approved"
    )
    expected_ready = sum(1 for row in rows if row.get("ready_for_manual_edit"))
    expected_gate = {
        "eligible_for_manual_application": expected_eligible,
        "application_blockers": expected_blockers,
        "approved_change_count": expected_approved,
        "ready_change_count": expected_ready,
        "requires_operator_review_artifact": True,
        "requires_approved_operator_review": True,
        "requires_config_value_match": True,
        "config_changes_must_be_manual": True,
    }
    append_field_mismatches(
        errors,
        prefix="config_application_dry_run application_gate",
        payload=gate,
        expected=expected_gate,
        field_names=tuple(expected_gate),
    )
    if string_list(gate.get("application_blockers", [])) != expected_blockers:
        errors.append("config_application_dry_run blockers mismatch")
    if int(gate.get("approved_change_count", -1) or 0) != expected_approved:
        errors.append("config_application_dry_run approved count mismatch")
    if int(gate.get("ready_change_count", -1) or 0) != expected_ready:
        errors.append("config_application_dry_run ready count mismatch")
    for row_index, row in enumerate(rows):
        selected = str(row.get("review_decision", "")) == "approved" and bool(
            row.get("selected_for_application", False)
        )
        value_matches = row.get("current_config_value") == row.get(
            "reviewed_current_value"
        )
        would_change = row.get("current_config_value") != row.get("proposed_value")
        ready = bool(selected and value_matches)
        expected_row = {
            "value_matches_review": value_matches,
            "would_change_config": would_change,
            "ready_for_manual_edit": ready,
            "applied": False,
            "requires_manual_config_edit": True,
            "source_artifact": "operator_config_review.json",
        }
        append_field_mismatches(
            errors,
            prefix=f"config_application_dry_run planned_changes {row_index}",
            payload=row,
            expected=expected_row,
            field_names=tuple(expected_row),
        )
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
        blockers=expected_blockers,
    )
    if str(payload.get("status", "")) != expected_status:
        errors.append("config_application_dry_run status mismatch")
    expected_actions = recommended_next_actions(
        eligible=expected_eligible,
        blockers=expected_blockers,
        planned_changes=rows,
    )
    if payload.get("recommended_next_actions") != expected_actions:
        errors.append("config_application_dry_run next actions mismatch")
    if review_recorded and decision_requested == "approve" and expected_approved == 0:
        errors.append("config_application_dry_run approval count missing")
    policy = object_value(payload.get("policy", {}))
    expected_policy = {
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
    }
    append_field_mismatches(
        errors,
        prefix="config_application_dry_run policy",
        payload=policy,
        expected=expected_policy,
        field_names=tuple(expected_policy),
    )
    if policy != expected_policy:
        errors.append("config_application_dry_run policy mismatch")
    return tuple(errors)


def expected_application_blockers(
    *,
    review_payload: dict[str, object],
    rows: list[dict[str, object]],
    payload_ok: bool,
    review_recorded: bool,
    decision_requested: str,
) -> list[str]:
    """Return expected dry-run blockers from the saved review and planned rows."""
    blockers: list[str] = []
    if not review_payload:
        blockers.append("missing_operator_config_review")
    if (
        review_payload
        and review_payload.get("schema_version") != OPERATOR_CONFIG_REVIEW_SCHEMA_VERSION
    ):
        blockers.append("operator_config_review_schema_invalid")
    if not payload_ok:
        blockers.append("missing_or_invalid_config")
    if not rows:
        blockers.append("no_reviewed_changes")
    if not review_recorded:
        blockers.append("operator_review_not_recorded")
    if decision_requested != "approve":
        blockers.append("operator_review_not_approved")
    approved_changes = [
        row for row in rows if row.get("review_decision") == "approved"
    ]
    if not approved_changes:
        blockers.append("no_approved_changes")
    if any(
        not bool(row.get("value_matches_review", False))
        for row in approved_changes
    ):
        blockers.append("current_config_value_mismatch")
    if any(
        not bool(row.get("would_change_config", False))
        for row in approved_changes
    ):
        blockers.append("approved_change_already_present")
    return unique_strings(blockers)


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


def append_field_mismatches(
    errors: list[str],
    *,
    prefix: str,
    payload: dict[str, object],
    expected: dict[str, object],
    field_names: tuple[str, ...],
) -> None:
    """Append field-specific mismatch messages for comparable objects."""
    for field_name in field_names:
        if payload.get(field_name) != expected.get(field_name):
            errors.append(f"{prefix} {field_name} mismatch")


def unique_strings(values: list[str]) -> list[str]:
    """Return unique strings in first-seen order."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def resolve_repo_path(path: Path, repo_root: Path) -> Path:
    """Return an absolute path resolved relative to repo root."""
    return path if path.is_absolute() else repo_root / path


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


def file_sha256(path: Path) -> str:
    """Return SHA-256 for one file, or empty string when unavailable."""
    if not path.exists() or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def infer_repo_root_from_payload_path(payload_path: Path, repo_root: Path) -> Path:
    """Infer repo root for experiment artifacts when caller passes another cwd."""
    resolved_payload = payload_path.resolve()
    resolved_repo = repo_root.resolve()
    try:
        resolved_payload.relative_to(resolved_repo)
        return resolved_repo
    except ValueError:
        pass
    run_dir = resolved_payload.parent
    experiments_dir = run_dir.parent
    if experiments_dir.name == "experiments":
        return experiments_dir.parent
    return resolved_repo


def config_path_from_payload(payload: dict[str, object], *, repo_root: Path) -> Path:
    """Return the config path recorded by a dry-run payload."""
    source_config = object_value(payload.get("source_config", {}))
    source_file = object_value(source_config.get("file", {}))
    recorded_path = str(source_file.get("path", ""))
    if not recorded_path:
        return repo_root / DEFAULT_CONFIG_PATH
    return resolve_repo_path(Path(recorded_path), repo_root)


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
