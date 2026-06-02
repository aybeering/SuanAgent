"""Guarded config application from approved dry-run evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.config_application_dry_run import (
    CONFIG_APPLICATION_DRY_RUN_SCHEMA_VERSION,
)
from orchestrator.operator_config_review import OPERATOR_CONFIG_REVIEW_SCHEMA_VERSION
from orchestrator.schema_validation import validate_json_file


CONFIG_APPLICATION_RECEIPT_SCHEMA_VERSION = "config_application_receipt_v1"
SCHEMA_PATH = Path("schemas/config_application_receipt.schema.json")
DEFAULT_CONFIG_PATH = Path("config/default.json")


def apply_config_with_approval(
    *,
    run_id: str,
    dry_run_path: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> dict[str, object]:
    """Apply approved config changes only when saved dry-run evidence still matches."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    dry_run_path = resolve_path(dry_run_path, repo_root)
    config_path = resolve_path(config_path, repo_root)
    run_dir = experiments_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    dry_run = load_json_object(dry_run_path)
    checks = config_application_evidence_checks(
        run_id=run_id,
        dry_run_path=dry_run_path,
        dry_run=dry_run,
        repo_root=repo_root,
        config_path=config_path,
    )
    config_before = load_json_object(config_path)
    applied = False
    applied_changes: list[dict[str, object]] = []
    if checks["ok"]:
        config_after = apply_ready_changes(
            config_payload=config_before,
            planned_changes=list_of_objects(dry_run.get("planned_changes", [])),
        )
        applied_changes = applied_change_rows(
            planned_changes=list_of_objects(dry_run.get("planned_changes", [])),
        )
        config_path.write_text(
            json.dumps(config_after, indent=2) + "\n",
            encoding="utf-8",
        )
        applied = True

    receipt = build_receipt_payload(
        run_id=run_id,
        run_dir=run_dir,
        repo_root=repo_root,
        config_path=config_path,
        dry_run_path=dry_run_path,
        dry_run=dry_run,
        checks=checks,
        applied=applied,
        applied_changes=applied_changes,
    )
    write_receipt(run_dir=run_dir, payload=receipt, repo_root=repo_root)
    return receipt


def config_application_evidence_checks(
    *,
    run_id: str,
    dry_run_path: Path,
    dry_run: dict[str, Any],
    repo_root: Path,
    config_path: Path,
) -> dict[str, Any]:
    """Return deterministic blockers for guarded config application."""
    blockers: list[str] = []
    dry_run_schema_errors = (
        validate_json_file(
            payload_path=dry_run_path,
            schema_path=repo_root / "schemas/config_application_dry_run.schema.json",
        )
        if dry_run_path.exists() and dry_run_path.is_file()
        else ("missing_dry_run_file",)
    )
    if dry_run_schema_errors:
        blockers.append("dry_run_schema_invalid")
    if dry_run.get("schema_version") != CONFIG_APPLICATION_DRY_RUN_SCHEMA_VERSION:
        blockers.append("dry_run_schema_version_invalid")
    if str(dry_run.get("run_id", "")) != run_id:
        blockers.append("dry_run_run_id_mismatch")
    if dry_run.get("status") != "ready_for_manual_application":
        blockers.append("dry_run_not_ready")

    gate = object_field(dry_run, "application_gate")
    if gate.get("eligible_for_manual_application") is not True:
        blockers.append("application_gate_not_eligible")
    if string_list(gate.get("application_blockers", [])):
        blockers.append("application_gate_has_blockers")

    planned_changes = list_of_objects(dry_run.get("planned_changes", []))
    ready_changes = [
        change for change in planned_changes if change.get("ready_for_manual_edit") is True
    ]
    if not ready_changes:
        blockers.append("no_ready_changes")
    if any(change.get("applied") is not False for change in planned_changes):
        blockers.append("dry_run_change_already_applied")
    if any(
        change.get("requires_manual_config_edit") is not True
        for change in planned_changes
    ):
        blockers.append("dry_run_change_missing_manual_flag")

    config_source = object_field(dry_run, "source_config")
    config_file = object_field(config_source, "file")
    if str(config_file.get("path", "")) != relative_path(config_path, repo_root):
        blockers.append("config_path_mismatch")
    recorded_config_sha = str(config_file.get("sha256", ""))
    if not config_path.exists() or not config_path.is_file():
        blockers.append("config_missing")
    elif recorded_config_sha != file_sha256(config_path):
        blockers.append("config_digest_mismatch")

    review_source = object_field(dry_run, "source_operator_review")
    review_file = object_field(review_source, "file")
    review_path = resolve_path(Path(str(review_file.get("path", ""))), repo_root)
    review = load_json_object(review_path)
    review_schema_errors = (
        validate_json_file(
            payload_path=review_path,
            schema_path=repo_root / "schemas/operator_config_review.schema.json",
        )
        if review_path.exists() and review_path.is_file()
        else ("missing_operator_review_file",)
    )
    if review_schema_errors:
        blockers.append("operator_review_schema_invalid")
    if review.get("schema_version") != OPERATOR_CONFIG_REVIEW_SCHEMA_VERSION:
        blockers.append("operator_review_schema_version_invalid")
    if str(review.get("run_id", "")) != run_id:
        blockers.append("operator_review_run_id_mismatch")
    if str(review_file.get("sha256", "")) != file_sha256(review_path):
        blockers.append("operator_review_digest_mismatch")
    intent = object_field(review, "operator_intent")
    if intent.get("review_recorded") is not True:
        blockers.append("operator_review_not_recorded")
    if intent.get("decision_requested") != "approve":
        blockers.append("operator_review_not_approved")
    if intent.get("confirmation_phrase_matches") is not True:
        blockers.append("operator_review_confirmation_mismatch")

    return {
        "ok": not blockers,
        "blockers": unique_strings(blockers),
        "dry_run_schema_errors": list(dry_run_schema_errors),
        "operator_review_schema_errors": list(review_schema_errors),
        "config_before_sha256": file_sha256(config_path),
        "source_config_sha256": recorded_config_sha,
        "source_operator_review_path": str(review_path),
        "source_operator_review_sha256": file_sha256(review_path),
        "ready_change_count": len(ready_changes),
    }


def apply_ready_changes(
    *,
    config_payload: dict[str, Any],
    planned_changes: list[dict[str, object]],
) -> dict[str, Any]:
    """Return a config payload with ready changes applied."""
    updated = json.loads(json.dumps(config_payload))
    for change in planned_changes:
        if change.get("ready_for_manual_edit") is True:
            set_value_at_path(
                updated,
                str(change.get("config_path", "")),
                change.get("proposed_value"),
            )
    return updated


def applied_change_rows(
    *,
    planned_changes: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return receipt rows for applied changes."""
    rows: list[dict[str, object]] = []
    for change in planned_changes:
        if change.get("ready_for_manual_edit") is not True:
            continue
        rows.append(
            {
                "candidate_id": str(change.get("candidate_id", "")),
                "config_path": str(change.get("config_path", "")),
                "previous_value": change.get("current_config_value"),
                "new_value": change.get("proposed_value"),
                "source_artifact": "config_application_dry_run.json",
            }
        )
    return rows


def build_receipt_payload(
    *,
    run_id: str,
    run_dir: Path,
    repo_root: Path,
    config_path: Path,
    dry_run_path: Path,
    dry_run: dict[str, Any],
    checks: dict[str, Any],
    applied: bool,
    applied_changes: list[dict[str, object]],
) -> dict[str, object]:
    """Build the saved config application receipt."""
    status = "applied" if applied else "blocked"
    return {
        "schema_version": CONFIG_APPLICATION_RECEIPT_SCHEMA_VERSION,
        "run_id": run_id,
        "run_dir": relative_path(run_dir, repo_root),
        "status": status,
        "ok": True,
        "applied": applied,
        "config_path": relative_path(config_path, repo_root),
        "config_before_sha256": str(checks.get("config_before_sha256", "")),
        "config_after_sha256": file_sha256(config_path),
        "source_dry_run_path": relative_path(dry_run_path, repo_root),
        "source_dry_run_sha256": file_sha256(dry_run_path),
        "source_operator_review_path": relative_path(
            Path(str(checks.get("source_operator_review_path", ""))),
            repo_root,
        ),
        "source_operator_review_sha256": str(
            checks.get("source_operator_review_sha256", "")
        ),
        "dry_run_status": str(dry_run.get("status", "")),
        "evidence_checks": {
            "ok": bool(checks.get("ok", False)),
            "blockers": string_list(checks.get("blockers", [])),
            "dry_run_schema_errors": string_list(
                checks.get("dry_run_schema_errors", [])
            ),
            "operator_review_schema_errors": string_list(
                checks.get("operator_review_schema_errors", [])
            ),
            "source_config_sha256": str(checks.get("source_config_sha256", "")),
            "ready_change_count": int(checks.get("ready_change_count", 0) or 0),
        },
        "applied_changes": applied_changes,
        "policy": {
            "requires_config_application_dry_run": True,
            "requires_dry_run_ready": True,
            "requires_source_dry_run_digest_match": True,
            "requires_operator_review_digest_match": True,
            "requires_current_config_digest_match": True,
            "writes_only_config": True,
            "does_not_delete_memory": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_route_candidates": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
        },
    }


def write_receipt(
    *,
    run_dir: Path,
    payload: dict[str, object],
    repo_root: Path,
) -> tuple[Path, Path]:
    """Write machine-readable and markdown config application receipts."""
    json_path = run_dir / "config_application_receipt.json"
    md_path = run_dir / "config_application_receipt.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_receipt_markdown(payload), encoding="utf-8")
    errors = validate_config_application_receipt_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(f"config application receipt failed schema validation: {errors}")
    return json_path, md_path


def render_receipt_markdown(payload: dict[str, object]) -> str:
    """Render a config application receipt as markdown."""
    checks = object_field(payload, "evidence_checks")
    lines = [
        "# Config Application Receipt",
        "",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- Applied: `{payload.get('applied', False)}`",
        f"- Config path: `{payload.get('config_path', '')}`",
        f"- Evidence OK: `{checks.get('ok', False)}`",
        f"- Source dry-run SHA-256: `{payload.get('source_dry_run_sha256', '')}`",
        f"- Operator review SHA-256: `{payload.get('source_operator_review_sha256', '')}`",
        "",
        "## Applied Changes",
        "",
    ]
    changes = list_of_objects(payload.get("applied_changes", []))
    if not changes:
        lines.append("No config changes were applied.")
    else:
        lines.extend(
            [
                "| Candidate | Config Path | Previous | New |",
                "| --- | --- | --- | --- |",
            ]
        )
        for change in changes:
            lines.append(
                "| "
                f"{change.get('candidate_id', '')} | "
                f"{change.get('config_path', '')} | "
                f"{json.dumps(change.get('previous_value', ''), sort_keys=True)} | "
                f"{json.dumps(change.get('new_value', ''), sort_keys=True)} |"
            )
    lines.extend(["", "## Blockers", ""])
    blockers = string_list(checks.get("blockers", []))
    lines.extend([f"- `{blocker}`" for blocker in blockers] or ["- none"])
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This command requires a ready config application dry-run, matching dry-run digest, matching operator review digest, and unchanged current config digest.",
            "- It writes only the configured config file and does not execute agents, run backtests, route candidates, apply patches, or change iteration acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_config_application_receipt_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved config application receipt."""
    return tuple(
        validate_json_file(
            payload_path=payload_path,
            schema_path=repo_root / SCHEMA_PATH,
        )
    )


def set_value_at_path(payload: dict[str, Any], dotted_path: str, value: object) -> None:
    """Set a nested JSON value for a dotted config path."""
    parts = [part for part in dotted_path.split(".") if part]
    if not parts:
        raise ValueError("empty config path")
    cursor: dict[str, Any] = payload
    for part in parts[:-1]:
        child = cursor.get(part)
        if not isinstance(child, dict):
            child = {}
            cursor[part] = child
        cursor = child
    cursor[parts[-1]] = value


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object or return an empty object."""
    if not path.exists() or not path.is_file() or not str(path):
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def object_field(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a nested object field."""
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def list_of_objects(value: object) -> list[dict[str, object]]:
    """Return JSON object rows from a list-like value."""
    if not isinstance(value, list | tuple):
        return []
    return [row for row in value if isinstance(row, dict)]


def string_list(value: object) -> list[str]:
    """Return string rows from a list-like value."""
    if isinstance(value, str):
        return [value] if value else []
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
    """Resolve a possibly relative path from the repository root."""
    return path if path.is_absolute() else repo_root / path


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def file_sha256(path: Path) -> str:
    """Return SHA-256 for a file or an empty string when missing."""
    if not path.exists() or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """CLI entrypoint for guarded config application."""
    parser = argparse.ArgumentParser(description="Apply config from approved dry-run evidence.")
    parser.add_argument("run_id")
    parser.add_argument("--dry-run-path", type=Path, required=True)
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args()
    payload = apply_config_with_approval(
        run_id=args.run_id,
        dry_run_path=args.dry_run_path,
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
        config_path=args.config,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload.get("applied", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
