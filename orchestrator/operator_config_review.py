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
from orchestrator.schema_validation import validate_json_file


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
    json_path = run_dir / "operator_config_review.json"
    md_path = run_dir / "operator_config_review.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_operator_config_review_markdown(payload), encoding="utf-8")
    errors = validate_operator_config_review_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(
            "operator config review failed schema validation: " + "; ".join(errors)
        )
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
    return tuple(
        validate_json_file(
            payload_path=payload_path,
            schema_path=repo_root / SCHEMA_PATH,
        )
    )


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


def sha256_text(value: str) -> str:
    """Return SHA-256 for text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


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
