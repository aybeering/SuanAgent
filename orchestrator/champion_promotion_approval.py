"""Deterministic read-only champion promotion operator approval artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.champion_promotion_dry_run import (
    CHAMPION_PROMOTION_DRY_RUN_SCHEMA_VERSION,
)
from orchestrator.schema_validation import (
    load_schema,
    validate_json_file,
    validate_json_payload,
)


CHAMPION_PROMOTION_APPROVAL_SCHEMA_VERSION = "champion_promotion_approval_v1"
SCHEMA_PATH = Path("schemas/champion_promotion_approval.schema.json")
DEFAULT_OPERATOR_ID = "unassigned"
REQUIRED_CONFIRMATION_PHRASE = "APPROVE CHAMPION PROMOTION"


def write_champion_promotion_approval(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
    operator_id: str = DEFAULT_OPERATOR_ID,
    confirmation_phrase: str = "",
    explicit_approval: bool = False,
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown champion promotion approval artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_champion_promotion_approval(
        run_dir=run_dir,
        repo_root=repo_root,
        operator_id=operator_id,
        confirmation_phrase=confirmation_phrase,
        explicit_approval=explicit_approval,
    )
    json_path = run_dir / "champion_promotion_approval.json"
    md_path = run_dir / "champion_promotion_approval.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_champion_promotion_approval_markdown(payload), encoding="utf-8")
    errors = validate_champion_promotion_approval_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(f"champion promotion approval failed schema validation: {errors}")
    return json_path, md_path, payload


def build_champion_promotion_approval(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
    operator_id: str = DEFAULT_OPERATOR_ID,
    confirmation_phrase: str = "",
    explicit_approval: bool = False,
) -> dict[str, object]:
    """Return a deterministic promotion approval placeholder from saved dry-run evidence."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    dry_run_path = run_dir / "champion_promotion_dry_run.json"
    dry_run = load_json_object(dry_run_path)
    run_id = str(dry_run.get("run_id", run_dir.name))
    decision = object_field(dry_run, "dry_run_decision")
    dry_policy = object_field(dry_run, "policy")
    reviewed_command = str(decision.get("promotion_command", ""))
    command_digest = sha256_text(reviewed_command) if reviewed_command else ""
    evidence_files = approval_evidence_files(
        run_dir=run_dir,
        dry_run_path=dry_run_path,
        dry_run=dry_run,
    )
    phrase_hash = sha256_text(confirmation_phrase) if confirmation_phrase else ""
    required_phrase_hash = sha256_text(REQUIRED_CONFIRMATION_PHRASE)
    phrase_matches = confirmation_phrase == REQUIRED_CONFIRMATION_PHRASE
    dry_run_recommended = bool(decision.get("would_promote", False))
    eligible_for_approval = bool(
        dry_run
        and dry_run.get("schema_version") == CHAMPION_PROMOTION_DRY_RUN_SCHEMA_VERSION
        and dry_run.get("ok") is True
        and dry_run_recommended
        and reviewed_command
    )
    approval_recorded = bool(explicit_approval and phrase_matches and eligible_for_approval)
    blockers = approval_blockers(
        dry_run=dry_run,
        dry_run_recommended=dry_run_recommended,
        reviewed_command=reviewed_command,
        explicit_approval=explicit_approval,
        phrase_matches=phrase_matches,
        eligible_for_approval=eligible_for_approval,
    )
    payload: dict[str, object] = {
        "schema_version": CHAMPION_PROMOTION_APPROVAL_SCHEMA_VERSION,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "status": approval_status(
            dry_run=dry_run,
            eligible_for_approval=eligible_for_approval,
            approval_recorded=approval_recorded,
            explicit_approval=explicit_approval,
        ),
        "ok": bool(dry_run),
        "operator_intent": {
            "approval_recorded": approval_recorded,
            "explicit_approval": bool(explicit_approval),
            "operator_id": str(operator_id),
            "required_confirmation_phrase_hash": required_phrase_hash,
            "provided_confirmation_phrase_hash": phrase_hash,
            "confirmation_phrase_matches": phrase_matches,
        },
        "reviewed_command": {
            "command": reviewed_command,
            "command_sha256": command_digest,
            "promotion_authority": str(
                dry_policy.get(
                    "promotion_authority",
                    "python -m orchestrator.experiments promote-approved",
                )
            ),
            "source_dry_run_path": str(dry_run_path),
            "source_dry_run_sha256": file_sha256(dry_run_path),
        },
        "dry_run_summary": {
            "schema_version": str(dry_run.get("schema_version", "")),
            "status": str(dry_run.get("status", "")),
            "ok": bool(dry_run.get("ok", False)),
            "would_promote": dry_run_recommended,
            "blocking_reasons": string_list(decision.get("blocking_reasons", [])),
        },
        "approval_gate": {
            "eligible_for_approval": eligible_for_approval,
            "approval_blockers": blockers,
            "requires_operator_review": True,
            "requires_matching_confirmation_phrase": True,
            "requires_dry_run_recommendation": True,
            "requires_nonempty_reviewed_command": True,
        },
        "evidence_files": evidence_files,
        "recommended_next_actions": recommended_next_actions(
            eligible_for_approval=eligible_for_approval,
            approval_recorded=approval_recorded,
            blockers=blockers,
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
            "does_not_execute_promote_command": True,
            "does_not_change_acceptance": True,
            "approval_does_not_promote": True,
            "promotion_still_requires_explicit_command": True,
        },
    }
    return payload


def approval_blockers(
    *,
    dry_run: dict[str, Any],
    dry_run_recommended: bool,
    reviewed_command: str,
    explicit_approval: bool,
    phrase_matches: bool,
    eligible_for_approval: bool,
) -> list[str]:
    """Return deterministic approval blockers."""
    blockers: list[str] = []
    if not dry_run:
        blockers.append("missing_champion_promotion_dry_run")
    if dry_run.get("schema_version") != CHAMPION_PROMOTION_DRY_RUN_SCHEMA_VERSION:
        blockers.append("dry_run_schema_invalid")
    if dry_run.get("ok") is not True:
        blockers.append("dry_run_not_ok")
    if not dry_run_recommended:
        blockers.append("dry_run_does_not_recommend_promotion")
    if not reviewed_command:
        blockers.append("reviewed_command_empty")
    if explicit_approval and not phrase_matches:
        blockers.append("confirmation_phrase_mismatch")
    if not explicit_approval:
        blockers.append("operator_approval_not_recorded")
    if not eligible_for_approval:
        blockers.append("not_eligible_for_approval")
    return unique_strings(blockers)


def approval_status(
    *,
    dry_run: dict[str, Any],
    eligible_for_approval: bool,
    approval_recorded: bool,
    explicit_approval: bool,
) -> str:
    """Return compact approval artifact status."""
    if not dry_run:
        return "needs_dry_run"
    if approval_recorded:
        return "approval_recorded"
    if eligible_for_approval and not explicit_approval:
        return "ready_for_operator_review"
    if eligible_for_approval and explicit_approval:
        return "approval_blocked"
    return "approval_blocked"


def approval_evidence_files(
    *,
    run_dir: Path,
    dry_run_path: Path,
    dry_run: dict[str, Any],
) -> list[dict[str, object]]:
    """Return file records that bind approval evidence to saved artifacts."""
    paths = [
        dry_run_path,
        run_dir / "manifest.json",
        run_dir / "diagnosis.json",
        run_dir / "candidate_challenger_report.json",
        run_dir / "champion_comparison.json",
    ]
    decision = object_field(dry_run, "dry_run_decision")
    for value in decision.get("evidence_paths", []):
        if isinstance(value, str) and value:
            paths.append(Path(value))
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen or not path.exists():
            continue
        seen.add(key)
        records.append(file_record(path))
    return records


def recommended_next_actions(
    *,
    eligible_for_approval: bool,
    approval_recorded: bool,
    blockers: list[str],
) -> list[str]:
    """Return compact next actions for operator review."""
    if approval_recorded:
        return ["Run the reviewed promote command only after final operator review."]
    if eligible_for_approval:
        return ["Record explicit operator approval with the required confirmation phrase."]
    if "dry_run_does_not_recommend_promotion" in blockers:
        return ["Keep iterating until the dry-run recommends champion promotion."]
    return ["Resolve approval blockers before considering champion promotion."]


def render_champion_promotion_approval_markdown(payload: dict[str, object]) -> str:
    """Render approval payload as markdown."""
    intent = object_field(payload, "operator_intent")
    command = object_field(payload, "reviewed_command")
    gate = object_field(payload, "approval_gate")
    dry_run = object_field(payload, "dry_run_summary")
    lines = [
        "# Champion Promotion Approval",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Dry-run status: `{dry_run.get('status', '')}`",
        f"- Dry-run would promote: `{dry_run.get('would_promote', False)}`",
        f"- Eligible for approval: `{gate.get('eligible_for_approval', False)}`",
        f"- Approval recorded: `{intent.get('approval_recorded', False)}`",
        f"- Operator id: `{intent.get('operator_id', '')}`",
        "",
        "## Reviewed Command",
        "",
    ]
    reviewed_command = str(command.get("command", ""))
    lines.append(f"`{reviewed_command}`" if reviewed_command else "No command is approved.")
    lines.extend(
        [
            f"- Command SHA-256: `{command.get('command_sha256', '')}`",
            f"- Source dry-run SHA-256: `{command.get('source_dry_run_sha256', '')}`",
            "",
            "## Approval Blockers",
            "",
        ]
    )
    blockers = string_list(gate.get("approval_blockers", []))
    lines.extend([f"- `{blocker}`" for blocker in blockers] or ["- none"])
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This artifact is inspection-only and reads saved artifacts only.",
            "- It does not execute the promote command, write champion registry files, append champion history, execute agents, run backtests, apply patches, route agents, or change acceptance.",
            "- Promotion still requires an explicit deterministic promote command.",
        ]
    )
    return "\n".join(lines) + "\n"


def validate_champion_promotion_approval_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved champion promotion approval artifact."""
    schema_errors = validate_json_file(
        payload_path=payload_path,
        schema_path=repo_root / SCHEMA_PATH,
    )
    if schema_errors:
        return schema_errors
    return validate_champion_promotion_approval_consistency(
        load_json_object(payload_path)
    )


def validate_champion_promotion_approval_payload(
    payload: dict[str, object],
    *,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate an in-memory champion promotion approval payload."""
    schema = load_schema(repo_root / SCHEMA_PATH)
    schema_errors = validate_json_payload(
        payload=payload,
        schema=schema,
        schema_dir=(repo_root / SCHEMA_PATH).parent,
    )
    if schema_errors:
        return schema_errors
    return validate_champion_promotion_approval_consistency(payload)


def validate_champion_promotion_approval_consistency(
    payload: dict[str, object],
) -> tuple[str, ...]:
    """Validate derived champion promotion approval fields."""
    errors: list[str] = []
    intent = object_field(payload, "operator_intent")
    command = object_field(payload, "reviewed_command")
    dry_summary = object_field(payload, "dry_run_summary")
    gate = object_field(payload, "approval_gate")
    source_dry_run_path = Path(str(command.get("source_dry_run_path", "")))
    source_dry_run = load_json_object(source_dry_run_path)
    source_decision = object_field(source_dry_run, "dry_run_decision")
    reviewed_command = str(command.get("command", ""))
    command_digest = sha256_text(reviewed_command) if reviewed_command else ""
    dry_run_recommended = bool(dry_summary.get("would_promote", False))
    eligible_for_approval = bool(
        source_dry_run
        and source_dry_run.get("schema_version") == CHAMPION_PROMOTION_DRY_RUN_SCHEMA_VERSION
        and source_dry_run.get("ok") is True
        and dry_run_recommended
        and reviewed_command
    )
    approval_recorded = bool(
        intent.get("explicit_approval", False)
        and intent.get("confirmation_phrase_matches", False)
        and eligible_for_approval
    )
    blockers = approval_blockers(
        dry_run=source_dry_run,
        dry_run_recommended=dry_run_recommended,
        reviewed_command=reviewed_command,
        explicit_approval=bool(intent.get("explicit_approval", False)),
        phrase_matches=bool(intent.get("confirmation_phrase_matches", False)),
        eligible_for_approval=eligible_for_approval,
    )
    expected_status = approval_status(
        dry_run=source_dry_run,
        eligible_for_approval=eligible_for_approval,
        approval_recorded=approval_recorded,
        explicit_approval=bool(intent.get("explicit_approval", False)),
    )

    if bool(payload.get("ok", False)) != bool(source_dry_run):
        errors.append("champion_promotion_approval ok mismatch")
    if str(payload.get("run_id", "")) != str(source_dry_run.get("run_id", "")):
        errors.append("champion_promotion_approval run id mismatch")
    if str(payload.get("status", "")) != expected_status:
        errors.append("champion_promotion_approval status mismatch")
    if intent.get("required_confirmation_phrase_hash") != sha256_text(
        REQUIRED_CONFIRMATION_PHRASE
    ):
        errors.append("champion_promotion_approval required phrase hash mismatch")
    if bool(intent.get("approval_recorded", False)) != approval_recorded:
        errors.append("champion_promotion_approval recorded mismatch")
    if command.get("command_sha256") != command_digest:
        errors.append("champion_promotion_approval command digest mismatch")
    if command.get("source_dry_run_sha256") != file_sha256(source_dry_run_path):
        errors.append("champion_promotion_approval dry-run digest mismatch")
    if str(dry_summary.get("schema_version", "")) != str(
        source_dry_run.get("schema_version", "")
    ):
        errors.append("champion_promotion_approval dry-run schema mismatch")
    if str(dry_summary.get("status", "")) != str(source_dry_run.get("status", "")):
        errors.append("champion_promotion_approval dry-run status mismatch")
    if bool(dry_summary.get("ok", False)) != bool(source_dry_run.get("ok", False)):
        errors.append("champion_promotion_approval dry-run ok mismatch")
    if dry_run_recommended != bool(source_decision.get("would_promote", False)):
        errors.append("champion_promotion_approval dry-run recommendation mismatch")
    if string_list(dry_summary.get("blocking_reasons", [])) != string_list(
        source_decision.get("blocking_reasons", [])
    ):
        errors.append("champion_promotion_approval dry-run blockers mismatch")
    if bool(gate.get("eligible_for_approval", False)) != eligible_for_approval:
        errors.append("champion_promotion_approval eligibility mismatch")
    if string_list(gate.get("approval_blockers", [])) != blockers:
        errors.append("champion_promotion_approval blockers mismatch")
    for key in (
        "requires_operator_review",
        "requires_matching_confirmation_phrase",
        "requires_dry_run_recommendation",
        "requires_nonempty_reviewed_command",
    ):
        if gate.get(key) is not True:
            errors.append(f"champion_promotion_approval gate false: {key}")
    expected_actions = recommended_next_actions(
        eligible_for_approval=eligible_for_approval,
        approval_recorded=approval_recorded,
        blockers=blockers,
    )
    if string_list(payload.get("recommended_next_actions", [])) != expected_actions:
        errors.append("champion_promotion_approval next actions mismatch")
    errors.extend(validate_evidence_file_records(payload))
    errors.extend(validate_champion_promotion_approval_policy(payload))
    return tuple(errors)


def validate_evidence_file_records(payload: dict[str, object]) -> tuple[str, ...]:
    """Validate saved evidence file records.

    The source dry-run is a guarded approval dependency and must still match
    exactly. Other evidence files are review-time snapshots; some, such as the
    run manifest, can be updated by later closeout steps in the same iteration.
    """
    errors: list[str] = []
    seen: set[str] = set()
    records = payload.get("evidence_files", [])
    source_dry_run_path = str(
        object_field(payload, "reviewed_command").get("source_dry_run_path", "")
    )
    if not isinstance(records, list):
        return ("champion_promotion_approval evidence files invalid",)
    for row in records:
        if not isinstance(row, dict):
            errors.append("champion_promotion_approval evidence file invalid")
            continue
        path_text = str(row.get("path", ""))
        path = Path(path_text)
        if path_text in seen:
            errors.append("champion_promotion_approval duplicate evidence path")
        seen.add(path_text)
        if path_text == source_dry_run_path:
            if bool(row.get("exists", False)) != path.exists():
                errors.append("champion_promotion_approval evidence exists mismatch")
            if row.get("sha256") != file_sha256(path):
                errors.append("champion_promotion_approval evidence digest mismatch")
            expected_size = path.stat().st_size if path.exists() else 0
            if row.get("byte_count") != expected_size:
                errors.append("champion_promotion_approval evidence size mismatch")
            continue
        if row.get("exists") is True:
            if not row.get("sha256"):
                errors.append("champion_promotion_approval evidence digest empty")
            if int(row.get("byte_count", 0)) <= 0:
                errors.append("champion_promotion_approval evidence size empty")
        elif row.get("sha256") or row.get("byte_count") != 0:
            errors.append("champion_promotion_approval missing evidence not empty")
    return tuple(errors)


def validate_champion_promotion_approval_policy(
    payload: dict[str, object],
) -> tuple[str, ...]:
    """Validate approval policy flags preserve non-promoting behavior."""
    errors: list[str] = []
    policy = object_field(payload, "policy")
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_write_champion_registry",
        "does_not_append_champion_history",
        "does_not_execute_promote_command",
        "does_not_change_acceptance",
        "approval_does_not_promote",
        "promotion_still_requires_explicit_command",
    ):
        if policy.get(key) is not True:
            errors.append(f"champion_promotion_approval policy false: {key}")
    return tuple(errors)


def file_record(path: Path) -> dict[str, object]:
    """Return a deterministic file record."""
    return {
        "path": str(path),
        "exists": path.exists(),
        "sha256": file_sha256(path),
        "byte_count": path.stat().st_size if path.exists() else 0,
    }


def file_sha256(path: Path) -> str:
    """Return SHA-256 for a file or an empty string when missing."""
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    """Return SHA-256 for text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root."""
    return path if path.is_absolute() else repo_root / path


def main() -> None:
    """CLI entrypoint for champion promotion approval artifacts."""
    parser = argparse.ArgumentParser(description="Write a champion promotion approval artifact.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--operator-id", default=DEFAULT_OPERATOR_ID)
    parser.add_argument("--confirmation-phrase", default="")
    parser.add_argument("--approve", action="store_true")
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Print the champion promotion approval artifact as markdown.",
    )
    args = parser.parse_args()
    _, _, payload = write_champion_promotion_approval(
        run_dir=args.run_dir,
        repo_root=args.repo_root,
        operator_id=args.operator_id,
        confirmation_phrase=args.confirmation_phrase,
        explicit_approval=args.approve,
    )
    if args.markdown:
        print(render_champion_promotion_approval_markdown(payload), end="")
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
