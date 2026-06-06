"""Read-only operator review artifact for config change candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.config_change_candidate import (
    CONFIG_CHANGE_CANDIDATE_SCHEMA_VERSION,
    build_config_change_candidate,
)
from orchestrator.schema_validation import (
    load_schema,
    validate_json_file,
    validate_json_payload,
)


OPERATOR_CONFIG_REVIEW_SCHEMA_VERSION = "operator_config_review_v1"
SCHEMA_PATH = Path("schemas/operator_config_review.schema.json")
DEFAULT_OPERATOR_ID = "unassigned"
REQUIRED_APPROVAL_PHRASE = "APPROVE CONFIG CHANGE CANDIDATE"


def write_operator_config_review(
    *,
    run_dir: Path,
    repo_root: Path,
    experiments_dir: Path | None = None,
    operator_id: str = DEFAULT_OPERATOR_ID,
    decision: str = "none",
    confirmation_phrase: str = "",
    candidate_ids: tuple[str, ...] = (),
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown operator config review artifacts."""
    payload = build_operator_config_review(
        run_dir=run_dir,
        repo_root=repo_root,
        experiments_dir=experiments_dir,
        operator_id=operator_id,
        decision=decision,
        confirmation_phrase=confirmation_phrase,
        candidate_ids=candidate_ids,
    )
    errors = validate_operator_config_review_payload(
        payload,
        run_dir=run_dir,
        repo_root=repo_root,
        experiments_dir=experiments_dir,
        operator_id=operator_id,
        decision=decision,
        confirmation_phrase=confirmation_phrase,
        candidate_ids=candidate_ids,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "operator config review failed schema validation: " + "; ".join(errors)
        )
    json_path = run_dir / "operator_config_review.json"
    md_path = run_dir / "operator_config_review.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_operator_config_review_markdown(payload), encoding="utf-8")
    return json_path, md_path, payload


def build_operator_config_review(
    *,
    run_dir: Path,
    repo_root: Path,
    experiments_dir: Path | None = None,
    operator_id: str = DEFAULT_OPERATOR_ID,
    decision: str = "none",
    confirmation_phrase: str = "",
    candidate_ids: tuple[str, ...] = (),
) -> dict[str, object]:
    """Return deterministic operator review status for config change candidates."""
    repo_root = repo_root.resolve()
    run_dir = run_dir.resolve()
    normalized_decision = normalize_decision(decision)
    candidate_path = run_dir / "config_change_candidate.json"
    if candidate_path.exists():
        candidate_payload = load_json_object(candidate_path)
        source_from_artifact = True
    else:
        candidate_payload = build_config_change_candidate(
            run_dir=run_dir,
            repo_root=repo_root,
            experiments_dir=experiments_dir,
        )
        source_from_artifact = False
    changes = list_of_objects(candidate_payload.get("changes", []))
    target_ids = selected_candidate_ids(
        changes=changes,
        requested_ids=candidate_ids,
    )
    phrase_hash = sha256_text(confirmation_phrase) if confirmation_phrase else ""
    required_phrase_hash = sha256_text(REQUIRED_APPROVAL_PHRASE)
    phrase_matches = confirmation_phrase == REQUIRED_APPROVAL_PHRASE
    candidate_artifact_ok = bool(
        candidate_payload
        and candidate_payload.get("schema_version")
        == CONFIG_CHANGE_CANDIDATE_SCHEMA_VERSION
    )
    eligible_for_review = bool(candidate_artifact_ok and changes and target_ids)
    review_recorded = bool(
        (normalized_decision == "reject" and eligible_for_review)
        or (
            normalized_decision == "approve"
            and eligible_for_review
            and phrase_matches
        )
    )
    blockers = review_blockers(
        candidate_payload=candidate_payload,
        changes=changes,
        target_ids=target_ids,
        requested_ids=candidate_ids,
        decision=normalized_decision,
        phrase_matches=phrase_matches,
        eligible_for_review=eligible_for_review,
    )
    reviewed_changes = reviewed_change_rows(
        changes=changes,
        target_ids=target_ids,
        decision=normalized_decision,
        review_recorded=review_recorded,
    )
    payload: dict[str, object] = {
        "schema_version": OPERATOR_CONFIG_REVIEW_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": relative_path(run_dir, repo_root),
        "status": review_status(
            candidate_payload=candidate_payload,
            changes=changes,
            decision=normalized_decision,
            review_recorded=review_recorded,
            eligible_for_review=eligible_for_review,
        ),
        "ok": bool(candidate_payload),
        "source": {
            "artifact_name": "config_change_candidate",
            "from_artifact": source_from_artifact,
            "file": file_record(candidate_path, repo_root),
        },
        "candidate_summary": {
            "schema_version": str(candidate_payload.get("schema_version", "")),
            "status": str(
                object_value(candidate_payload.get("summary", {})).get("status", "")
            ),
            "candidate_count": len(changes),
            "config_paths": sorted(
                str(change.get("config_path", ""))
                for change in changes
                if str(change.get("config_path", ""))
            ),
        },
        "operator_intent": {
            "review_recorded": review_recorded,
            "decision_requested": normalized_decision,
            "operator_id": str(operator_id),
            "target_candidate_ids": list(target_ids),
            "required_approval_phrase_hash": required_phrase_hash,
            "provided_confirmation_phrase_hash": phrase_hash,
            "confirmation_phrase_matches": phrase_matches,
        },
        "review_gate": {
            "eligible_for_review": eligible_for_review,
            "review_blockers": blockers,
            "requires_operator_review": bool(changes),
            "requires_matching_confirmation_phrase_for_approval": True,
            "config_changes_must_be_manual": True,
        },
        "reviewed_changes": reviewed_changes,
        "recommended_next_actions": recommended_next_actions(
            changes=changes,
            decision=normalized_decision,
            review_recorded=review_recorded,
            blockers=blockers,
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
            "review_does_not_apply_config": True,
            "config_changes_still_require_manual_edit": True,
        },
    }
    return payload


def normalize_decision(decision: str) -> str:
    """Return a supported review decision."""
    value = decision.strip().lower()
    return value if value in {"none", "approve", "reject"} else "none"


def selected_candidate_ids(
    *,
    changes: list[dict[str, object]],
    requested_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """Return requested candidate ids or all known candidate ids."""
    known = tuple(
        str(change.get("candidate_id", ""))
        for change in changes
        if str(change.get("candidate_id", ""))
    )
    if not requested_ids:
        return known
    known_set = set(known)
    return tuple(candidate_id for candidate_id in requested_ids if candidate_id in known_set)


def review_blockers(
    *,
    candidate_payload: dict[str, object],
    changes: list[dict[str, object]],
    target_ids: tuple[str, ...],
    requested_ids: tuple[str, ...],
    decision: str,
    phrase_matches: bool,
    eligible_for_review: bool,
) -> list[str]:
    """Return deterministic operator review blockers."""
    blockers: list[str] = []
    if not candidate_payload:
        blockers.append("missing_config_change_candidate")
    if candidate_payload.get("schema_version") != CONFIG_CHANGE_CANDIDATE_SCHEMA_VERSION:
        blockers.append("config_change_candidate_schema_invalid")
    if not changes:
        blockers.append("no_candidate_changes")
    if requested_ids and not target_ids:
        blockers.append("requested_candidate_ids_not_found")
    if decision == "none":
        blockers.append("operator_review_not_recorded")
    if decision == "approve" and not phrase_matches:
        blockers.append("confirmation_phrase_mismatch")
    if not eligible_for_review:
        blockers.append("not_eligible_for_review")
    return unique_strings(blockers)


def review_status(
    *,
    candidate_payload: dict[str, object],
    changes: list[dict[str, object]],
    decision: str,
    review_recorded: bool,
    eligible_for_review: bool,
) -> str:
    """Return compact operator review status."""
    if not candidate_payload:
        return "needs_config_candidate"
    if not changes:
        return "no_candidate_changes"
    if review_recorded:
        return "review_recorded"
    if eligible_for_review and decision == "none":
        return "ready_for_operator_review"
    return "review_blocked"


def reviewed_change_rows(
    *,
    changes: list[dict[str, object]],
    target_ids: tuple[str, ...],
    decision: str,
    review_recorded: bool,
) -> list[dict[str, object]]:
    """Return compact reviewed change rows."""
    target_set = set(target_ids)
    rows: list[dict[str, object]] = []
    for change in changes:
        candidate_id = str(change.get("candidate_id", ""))
        selected = candidate_id in target_set
        row_decision = "pending"
        if selected and review_recorded and decision == "approve":
            row_decision = "approved"
        elif selected and review_recorded and decision == "reject":
            row_decision = "rejected"
        rows.append(
            {
                "candidate_id": candidate_id,
                "config_path": str(change.get("config_path", "")),
                "current_value": change.get("current_value"),
                "proposed_value": change.get("proposed_value"),
                "selected_for_review": selected,
                "review_decision": row_decision,
                "applied": False,
                "requires_manual_config_edit": True,
                "source_artifact": "config_change_candidate.json",
            }
        )
    return rows


def recommended_next_actions(
    *,
    changes: list[dict[str, object]],
    decision: str,
    review_recorded: bool,
    blockers: list[str],
) -> list[str]:
    """Return deterministic next actions for operator review."""
    if not changes:
        return ["No config changes are recommended for this run."]
    if review_recorded and decision == "approve":
        return ["Manually edit config only after reviewing this approval record."]
    if review_recorded and decision == "reject":
        return ["Keep the current config and continue iteration."]
    if "confirmation_phrase_mismatch" in blockers:
        return ["Use the required confirmation phrase to record approval."]
    return ["Review config_change_candidate.json and record approve or reject intent."]


def render_operator_config_review_markdown(payload: dict[str, object]) -> str:
    """Render operator config review as markdown."""
    intent = object_value(payload.get("operator_intent", {}))
    gate = object_value(payload.get("review_gate", {}))
    summary = object_value(payload.get("candidate_summary", {}))
    lines = [
        "# Operator Config Review",
        "",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Candidate count: `{summary.get('candidate_count', 0)}`",
        f"- Decision requested: `{intent.get('decision_requested', '')}`",
        f"- Review recorded: `{intent.get('review_recorded', False)}`",
        f"- Operator id: `{intent.get('operator_id', '')}`",
        f"- Eligible for review: `{gate.get('eligible_for_review', False)}`",
        "",
        "## Reviewed Changes",
        "",
    ]
    rows = list_of_objects(payload.get("reviewed_changes", []))
    if not rows:
        lines.append("No config changes are available for review.")
    else:
        lines.extend(
            [
                "| Candidate | Config Path | Current | Proposed | Decision |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for row in rows:
            lines.append(
                "| "
                f"{row.get('candidate_id', '')} | "
                f"{row.get('config_path', '')} | "
                f"{json.dumps(row.get('current_value', ''), sort_keys=True)} | "
                f"{json.dumps(row.get('proposed_value', ''), sort_keys=True)} | "
                f"{row.get('review_decision', '')} |"
            )
    lines.extend(
        [
            "",
            "## Review Blockers",
            "",
        ]
    )
    blockers = string_list(gate.get("review_blockers", []))
    lines.extend([f"- `{blocker}`" for blocker in blockers] or ["- none"])
    lines.extend(
        [
            "",
            "This artifact records operator intent only. It does not write config, execute agents, run backtests, route candidates, apply patches, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_operator_config_review_file(
    *,
    payload_path: Path,
    repo_root: Path,
) -> tuple[str, ...]:
    """Validate a saved operator config review report."""
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
            validate_operator_config_review_payload(
                payload,
                run_dir=payload_path.parent,
                repo_root=effective_repo_root,
                experiments_dir=payload_path.parent.parent,
            )
        )
        current_errors = validate_operator_config_review_current_evidence(
            payload,
            run_dir=payload_path.parent,
            repo_root=effective_repo_root,
            experiments_dir=payload_path.parent.parent,
            operator_id=None,
            decision=None,
            confirmation_phrase=None,
            candidate_ids=None,
        )
        errors.extend(current_errors)
        if current_errors:
            errors.append("operator_config_review current evidence mismatch")
    return tuple(errors)


def validate_operator_config_review_payload(
    payload: dict[str, object],
    *,
    run_dir: Path,
    repo_root: Path,
    experiments_dir: Path | None = None,
    operator_id: str = DEFAULT_OPERATOR_ID,
    decision: str = "none",
    confirmation_phrase: str = "",
    candidate_ids: tuple[str, ...] = (),
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an in-memory operator config review payload."""
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
        validate_operator_config_review_consistency(
            normalized,
            run_dir=run_dir,
            repo_root=repo_root,
        )
    )
    if require_current_evidence:
        current_errors = validate_operator_config_review_current_evidence(
            normalized,
            run_dir=run_dir,
            repo_root=repo_root,
            experiments_dir=experiments_dir,
            operator_id=operator_id,
            decision=decision,
            confirmation_phrase=confirmation_phrase,
            candidate_ids=candidate_ids,
        )
        errors.extend(current_errors)
        expected = build_operator_config_review(
            run_dir=run_dir,
            repo_root=repo_root,
            experiments_dir=experiments_dir,
            operator_id=operator_id,
            decision=decision,
            confirmation_phrase=confirmation_phrase,
            candidate_ids=candidate_ids,
        )
        if normalized != expected:
            errors.append("operator_config_review current evidence mismatch")
    return tuple(errors)


def validate_operator_config_review_current_evidence(
    payload: dict[str, object],
    *,
    run_dir: Path,
    repo_root: Path,
    experiments_dir: Path | None = None,
    operator_id: str | None = DEFAULT_OPERATOR_ID,
    decision: str | None = "none",
    confirmation_phrase: str | None = "",
    candidate_ids: tuple[str, ...] | None = (),
) -> tuple[str, ...]:
    """Validate review fields against current candidate artifact evidence."""
    errors: list[str] = []
    intent = object_value(payload.get("operator_intent", {}))
    effective_operator_id = (
        str(intent.get("operator_id", DEFAULT_OPERATOR_ID))
        if operator_id is None
        else operator_id
    )
    effective_decision = (
        str(intent.get("decision_requested", "none")) if decision is None else decision
    )
    effective_candidate_ids = (
        tuple(string_list(intent.get("target_candidate_ids", [])))
        if candidate_ids is None
        else candidate_ids
    )
    phrase_is_exact = confirmation_phrase is not None
    if confirmation_phrase is None:
        effective_confirmation_phrase = (
            REQUIRED_APPROVAL_PHRASE
            if bool(intent.get("confirmation_phrase_matches", False))
            else ""
        )
    else:
        effective_confirmation_phrase = confirmation_phrase
    expected = build_operator_config_review(
        run_dir=run_dir,
        repo_root=repo_root,
        experiments_dir=experiments_dir,
        operator_id=effective_operator_id,
        decision=effective_decision,
        confirmation_phrase=effective_confirmation_phrase,
        candidate_ids=effective_candidate_ids,
    )
    append_field_mismatches(
        errors,
        prefix="operator_config_review",
        payload=payload,
        expected=expected,
        field_names=("run_id", "run_dir", "status", "ok"),
    )
    append_field_mismatches(
        errors,
        prefix="operator_config_review source",
        payload=object_value(payload.get("source", {})),
        expected=object_value(expected.get("source", {})),
        field_names=("artifact_name", "from_artifact", "file"),
    )
    append_field_mismatches(
        errors,
        prefix="operator_config_review candidate_summary",
        payload=object_value(payload.get("candidate_summary", {})),
        expected=object_value(expected.get("candidate_summary", {})),
        field_names=tuple(object_value(expected.get("candidate_summary", {}))),
    )
    intent_fields = tuple(object_value(expected.get("operator_intent", {})))
    if not phrase_is_exact:
        intent_fields = tuple(
            field_name
            for field_name in intent_fields
            if field_name != "provided_confirmation_phrase_hash"
        )
    append_field_mismatches(
        errors,
        prefix="operator_config_review operator_intent",
        payload=intent,
        expected=object_value(expected.get("operator_intent", {})),
        field_names=intent_fields,
    )
    append_field_mismatches(
        errors,
        prefix="operator_config_review review_gate",
        payload=object_value(payload.get("review_gate", {})),
        expected=object_value(expected.get("review_gate", {})),
        field_names=tuple(object_value(expected.get("review_gate", {}))),
    )
    rows = list_of_objects(payload.get("reviewed_changes", []))
    expected_rows = list_of_objects(expected.get("reviewed_changes", []))
    if len(rows) != len(expected_rows):
        errors.append("operator_config_review reviewed_changes count mismatch")
    for index, row in enumerate(rows):
        expected_row = expected_rows[index] if index < len(expected_rows) else {}
        candidate_id = str(row.get("candidate_id", index))
        append_field_mismatches(
            errors,
            prefix=f"operator_config_review reviewed_changes {candidate_id}",
            payload=row,
            expected=expected_row,
            field_names=tuple(expected_row),
        )
    if payload.get("recommended_next_actions") != expected.get(
        "recommended_next_actions"
    ):
        errors.append("operator_config_review next actions mismatch")
    append_field_mismatches(
        errors,
        prefix="operator_config_review policy",
        payload=object_value(payload.get("policy", {})),
        expected=object_value(expected.get("policy", {})),
        field_names=tuple(object_value(expected.get("policy", {}))),
    )
    return tuple(errors)


def validate_operator_config_review_consistency(
    payload: dict[str, object],
    *,
    run_dir: Path,
    repo_root: Path,
) -> tuple[str, ...]:
    """Return stable internal consistency errors for operator config review."""
    errors: list[str] = []
    if str(payload.get("run_id", "")) != run_dir.name:
        errors.append("operator_config_review run_id mismatch")
    if str(payload.get("run_dir", "")) != relative_path(run_dir, repo_root):
        errors.append("operator_config_review run_dir mismatch")
    summary = object_value(payload.get("candidate_summary", {}))
    intent = object_value(payload.get("operator_intent", {}))
    gate = object_value(payload.get("review_gate", {}))
    rows = list_of_objects(payload.get("reviewed_changes", []))
    target_ids = tuple(string_list(intent.get("target_candidate_ids", [])))
    decision = str(intent.get("decision_requested", "none"))
    review_recorded = bool(intent.get("review_recorded", False))
    selected_ids = tuple(
        str(row.get("candidate_id", ""))
        for row in rows
        if bool(row.get("selected_for_review", False))
    )
    if target_ids != selected_ids:
        errors.append("operator_config_review selected ids mismatch")
    expected_summary = {
        "schema_version": str(summary.get("schema_version", "")),
        "status": str(summary.get("status", "")),
        "candidate_count": len(rows),
        "config_paths": sorted(
            str(row.get("config_path", ""))
            for row in rows
            if str(row.get("config_path", ""))
        ),
    }
    append_field_mismatches(
        errors,
        prefix="operator_config_review candidate_summary",
        payload=summary,
        expected=expected_summary,
        field_names=("schema_version", "status", "candidate_count", "config_paths"),
    )
    if summary != expected_summary:
        errors.append("operator_config_review candidate_summary mismatch")
    phrase_matches = bool(intent.get("confirmation_phrase_matches", False))
    eligible = bool(
        summary.get("schema_version") == CONFIG_CHANGE_CANDIDATE_SCHEMA_VERSION
        and rows
        and target_ids
    )
    required_phrase_hash = sha256_text(REQUIRED_APPROVAL_PHRASE)
    provided_phrase_hash = str(intent.get("provided_confirmation_phrase_hash", ""))
    expected_review_recorded = bool(
        (decision == "reject" and eligible)
        or (decision == "approve" and eligible and phrase_matches)
    )
    expected_intent = {
        "review_recorded": expected_review_recorded,
        "decision_requested": decision,
        "target_candidate_ids": list(target_ids),
        "required_approval_phrase_hash": required_phrase_hash,
        "provided_confirmation_phrase_hash": provided_phrase_hash,
        "confirmation_phrase_matches": bool(
            provided_phrase_hash == required_phrase_hash and bool(provided_phrase_hash)
        ),
    }
    append_field_mismatches(
        errors,
        prefix="operator_config_review operator_intent",
        payload=intent,
        expected=expected_intent,
        field_names=tuple(expected_intent),
    )
    expected_blockers = review_blockers(
        candidate_payload={"schema_version": summary.get("schema_version", "")}
        if bool(payload.get("ok", False))
        else {},
        changes=rows,
        target_ids=target_ids,
        requested_ids=target_ids,
        decision=decision,
        phrase_matches=phrase_matches,
        eligible_for_review=eligible,
    )
    expected_gate = {
        "eligible_for_review": eligible,
        "review_blockers": expected_blockers,
        "requires_operator_review": bool(rows),
        "requires_matching_confirmation_phrase_for_approval": True,
        "config_changes_must_be_manual": True,
    }
    append_field_mismatches(
        errors,
        prefix="operator_config_review review_gate",
        payload=gate,
        expected=expected_gate,
        field_names=tuple(expected_gate),
    )
    if bool(gate.get("eligible_for_review", False)) != eligible:
        errors.append("operator_config_review eligible_for_review mismatch")
    if string_list(gate.get("review_blockers", [])) != expected_blockers:
        errors.append("operator_config_review review_blockers mismatch")
    if bool(gate.get("requires_operator_review", False)) != bool(rows):
        errors.append("operator_config_review requires_operator_review mismatch")
    if str(intent.get("required_approval_phrase_hash", "")) != required_phrase_hash:
        errors.append("operator_config_review approval phrase hash mismatch")
    if decision == "approve" and phrase_matches and not review_recorded and eligible:
        errors.append("operator_config_review approval should be recorded")
    if review_recorded and decision not in {"approve", "reject"}:
        errors.append("operator_config_review invalid recorded decision")
    expected_status = review_status(
        candidate_payload={"schema_version": summary.get("schema_version", "")}
        if bool(payload.get("ok", False))
        else {},
        changes=rows,
        decision=decision,
        review_recorded=review_recorded,
        eligible_for_review=eligible,
    )
    if str(payload.get("status", "")) != expected_status:
        errors.append("operator_config_review status mismatch")
    for row in rows:
        candidate_id = str(row.get("candidate_id", ""))
        selected = candidate_id in set(target_ids)
        expected_decision = "pending"
        if selected and review_recorded and decision == "approve":
            expected_decision = "approved"
        elif selected and review_recorded and decision == "reject":
            expected_decision = "rejected"
        expected_row = {
            "selected_for_review": selected,
            "review_decision": expected_decision,
            "applied": False,
            "requires_manual_config_edit": True,
            "source_artifact": "config_change_candidate.json",
        }
        append_field_mismatches(
            errors,
            prefix=f"operator_config_review reviewed_changes {candidate_id}",
            payload=row,
            expected=expected_row,
            field_names=tuple(expected_row),
        )
        if bool(row.get("selected_for_review", False)) != selected:
            errors.append("operator_config_review row selection mismatch")
        if str(row.get("review_decision", "")) != expected_decision:
            errors.append("operator_config_review reviewed row decision mismatch")
        if bool(row.get("applied", True)):
            errors.append("operator_config_review applied flag must be false")
        if not bool(row.get("requires_manual_config_edit", False)):
            errors.append("operator_config_review requires manual edit false")
    expected_actions = recommended_next_actions(
        changes=rows,
        decision=decision,
        review_recorded=review_recorded,
        blockers=string_list(gate.get("review_blockers", [])),
    )
    if payload.get("recommended_next_actions") != expected_actions:
        errors.append("operator_config_review next actions mismatch")
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
        "review_does_not_apply_config": True,
        "config_changes_still_require_manual_edit": True,
    }
    append_field_mismatches(
        errors,
        prefix="operator_config_review policy",
        payload=policy,
        expected=expected_policy,
        field_names=tuple(expected_policy),
    )
    if policy != expected_policy:
        errors.append("operator_config_review policy mismatch")
    return tuple(errors)


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


def sha256_text(value: str) -> str:
    """Return SHA-256 for text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def main() -> None:
    """CLI entrypoint for operator config review reports."""
    parser = argparse.ArgumentParser(description="Write an operator config review report.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--decision",
        choices=("none", "approve", "reject"),
        default="none",
    )
    parser.add_argument("--operator-id", default=DEFAULT_OPERATOR_ID)
    parser.add_argument("--confirmation-phrase", default="")
    parser.add_argument("--candidate-id", action="append", default=[])
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--experiments-dir", type=Path)
    args = parser.parse_args()
    _, _, payload = write_operator_config_review(
        run_dir=args.run_dir,
        repo_root=args.repo_root,
        experiments_dir=args.experiments_dir,
        operator_id=args.operator_id,
        decision=args.decision,
        confirmation_phrase=args.confirmation_phrase,
        candidate_ids=tuple(args.candidate_id),
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
