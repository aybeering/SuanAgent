"""Guarded config restore from rollback preview evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.config_application_executor import (
    DEFAULT_CONFIG_PATH,
    file_sha256,
    list_of_objects,
    load_json_object,
    object_field,
    relative_path,
    resolve_path,
    set_value_at_path,
    string_list,
    unique_strings,
)
from orchestrator.config_application_rollback_preview import (
    CONFIG_APPLICATION_ROLLBACK_PREVIEW_SCHEMA_VERSION,
)
from orchestrator.schema_validation import validate_json_file


CONFIG_APPLICATION_RESTORE_RECEIPT_SCHEMA_VERSION = (
    "config_application_restore_receipt_v1"
)
SCHEMA_PATH = Path("schemas/config_application_restore_receipt.schema.json")


def restore_config_with_preview(
    *,
    run_id: str,
    preview_path: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> dict[str, object]:
    """Restore config only when rollback preview evidence still matches."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    preview_path = resolve_path(preview_path, repo_root)
    config_path = resolve_path(config_path, repo_root)
    run_dir = experiments_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    preview = load_json_object(preview_path)
    checks = config_restore_evidence_checks(
        run_id=run_id,
        preview_path=preview_path,
        preview=preview,
        repo_root=repo_root,
        config_path=config_path,
    )
    restored = False
    restored_changes: list[dict[str, object]] = []
    if checks["ok"]:
        config_before = load_json_object(config_path)
        config_after = apply_restore_plan(
            config_payload=config_before,
            rollback_plan=list_of_objects(preview.get("rollback_plan", [])),
        )
        restored_changes = restored_change_rows(
            rollback_plan=list_of_objects(preview.get("rollback_plan", [])),
        )
        config_path.write_text(
            json.dumps(config_after, indent=2) + "\n",
            encoding="utf-8",
        )
        restored = True

    receipt = build_restore_receipt_payload(
        run_id=run_id,
        run_dir=run_dir,
        repo_root=repo_root,
        config_path=config_path,
        preview_path=preview_path,
        preview=preview,
        checks=checks,
        restored=restored,
        restored_changes=restored_changes,
    )
    write_restore_receipt(run_dir=run_dir, payload=receipt, repo_root=repo_root)
    return receipt


def config_restore_evidence_checks(
    *,
    run_id: str,
    preview_path: Path,
    preview: dict[str, Any],
    repo_root: Path,
    config_path: Path,
) -> dict[str, Any]:
    """Return deterministic blockers for guarded config restore."""
    blockers: list[str] = []
    preview_schema_errors = (
        validate_json_file(
            payload_path=preview_path,
            schema_path=repo_root
            / "schemas/config_application_rollback_preview.schema.json",
        )
        if preview_path.exists() and preview_path.is_file()
        else ("missing_config_application_rollback_preview_file",)
    )
    if preview_schema_errors:
        blockers.append("preview_schema_invalid")
    if (
        preview.get("schema_version")
        != CONFIG_APPLICATION_ROLLBACK_PREVIEW_SCHEMA_VERSION
    ):
        blockers.append("preview_schema_version_invalid")
    if str(preview.get("run_id", "")) != run_id:
        blockers.append("preview_run_id_mismatch")
    if preview.get("status") != "rollback_ready":
        blockers.append("preview_not_ready")
    if preview.get("source_receipt_applied") is not True:
        blockers.append("source_receipt_not_applied")

    gate = object_field(preview, "rollback_gate")
    if gate.get("eligible_for_manual_restore") is not True:
        blockers.append("rollback_gate_not_eligible")
    if string_list(gate.get("blockers", [])):
        blockers.append("rollback_gate_has_blockers")

    rollback_plan = list_of_objects(preview.get("rollback_plan", []))
    if not rollback_plan:
        blockers.append("no_restore_plan")
    if any(row.get("can_restore") is not True for row in rollback_plan):
        blockers.append("restore_plan_not_restorable")
    if any(
        row.get("current_matches_expected_applied") is not True
        for row in rollback_plan
    ):
        blockers.append("restore_plan_current_value_mismatch")

    receipt_path = resolve_path(
        Path(str(preview.get("source_receipt_path", ""))),
        repo_root,
    )
    if str(preview.get("source_receipt_sha256", "")) != file_sha256(receipt_path):
        blockers.append("source_receipt_digest_mismatch")
    if str(preview.get("config_path", "")) != relative_path(config_path, repo_root):
        blockers.append("config_path_mismatch")
    if not config_path.exists() or not config_path.is_file():
        blockers.append("config_missing")
    elif str(preview.get("current_config_sha256", "")) != file_sha256(config_path):
        blockers.append("config_digest_mismatch")
    if str(preview.get("receipt_config_after_sha256", "")) != file_sha256(config_path):
        blockers.append("config_not_at_applied_digest")

    return {
        "ok": not blockers,
        "blockers": unique_strings(blockers),
        "preview_schema_errors": list(preview_schema_errors),
        "config_before_sha256": file_sha256(config_path),
        "source_preview_sha256": file_sha256(preview_path),
        "source_receipt_path": str(receipt_path),
        "source_receipt_sha256": file_sha256(receipt_path),
        "restore_plan_count": len(rollback_plan),
        "restorable_change_count": sum(
            1 for row in rollback_plan if row.get("can_restore") is True
        ),
    }


def apply_restore_plan(
    *,
    config_payload: dict[str, Any],
    rollback_plan: list[dict[str, object]],
) -> dict[str, Any]:
    """Return a config payload with restore values applied."""
    updated = json.loads(json.dumps(config_payload))
    for row in rollback_plan:
        if row.get("can_restore") is True:
            config_path = str(row.get("config_path", ""))
            if row.get("restore_path_exists") is False:
                delete_value_at_path(updated, config_path)
            else:
                set_value_at_path(updated, config_path, row.get("restore_value"))
    return updated


def restored_change_rows(
    *,
    rollback_plan: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return receipt rows for restored config values."""
    rows: list[dict[str, object]] = []
    for row in rollback_plan:
        if row.get("can_restore") is not True:
            continue
        rows.append(
            {
                "candidate_id": str(row.get("candidate_id", "")),
                "config_path": str(row.get("config_path", "")),
                "previous_value": row.get("current_value"),
                "restored_value": row.get("restore_value"),
                "restored_path_exists": bool(row.get("restore_path_exists", True)),
                "source_artifact": "config_application_rollback_preview.json",
            }
        )
    return rows


def build_restore_receipt_payload(
    *,
    run_id: str,
    run_dir: Path,
    repo_root: Path,
    config_path: Path,
    preview_path: Path,
    preview: dict[str, Any],
    checks: dict[str, Any],
    restored: bool,
    restored_changes: list[dict[str, object]],
) -> dict[str, object]:
    """Build the saved config restore receipt."""
    return {
        "schema_version": CONFIG_APPLICATION_RESTORE_RECEIPT_SCHEMA_VERSION,
        "run_id": run_id,
        "run_dir": relative_path(run_dir, repo_root),
        "status": "restored" if restored else "blocked",
        "ok": True,
        "restored": restored,
        "config_path": relative_path(config_path, repo_root),
        "config_before_sha256": str(checks.get("config_before_sha256", "")),
        "config_after_sha256": file_sha256(config_path),
        "source_preview_path": relative_path(preview_path, repo_root),
        "source_preview_sha256": str(checks.get("source_preview_sha256", "")),
        "source_preview_status": str(preview.get("status", "")),
        "source_receipt_path": relative_path(
            Path(str(checks.get("source_receipt_path", ""))),
            repo_root,
        ),
        "source_receipt_sha256": str(checks.get("source_receipt_sha256", "")),
        "restore_gate": {
            "ok": bool(checks.get("ok", False)),
            "blockers": string_list(checks.get("blockers", [])),
            "preview_schema_errors": string_list(
                checks.get("preview_schema_errors", [])
            ),
            "restore_plan_count": int(checks.get("restore_plan_count", 0) or 0),
            "restorable_change_count": int(
                checks.get("restorable_change_count", 0) or 0
            ),
        },
        "restored_changes": restored_changes,
        "policy": {
            "requires_config_application_rollback_preview": True,
            "requires_preview_ready": True,
            "requires_preview_digest_match": True,
            "requires_source_receipt_digest_match": True,
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


def write_restore_receipt(
    *,
    run_dir: Path,
    payload: dict[str, object],
    repo_root: Path,
) -> tuple[Path, Path]:
    """Write machine-readable and markdown config restore receipts."""
    json_path = run_dir / "config_application_restore_receipt.json"
    md_path = run_dir / "config_application_restore_receipt.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_restore_receipt_markdown(payload), encoding="utf-8")
    errors = validate_config_application_restore_receipt_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(
            "config application restore receipt failed schema validation: "
            + "; ".join(errors)
        )
    return json_path, md_path


def delete_value_at_path(payload: dict[str, Any], dotted_path: str) -> None:
    """Delete a nested JSON value when it exists."""
    parts = [part for part in dotted_path.split(".") if part]
    if not parts:
        raise ValueError("empty config path")
    cursor: dict[str, Any] = payload
    for part in parts[:-1]:
        child = cursor.get(part)
        if not isinstance(child, dict):
            return
        cursor = child
    cursor.pop(parts[-1], None)


def render_restore_receipt_markdown(payload: dict[str, object]) -> str:
    """Render a config restore receipt as markdown."""
    gate = object_field(payload, "restore_gate")
    lines = [
        "# Config Application Restore Receipt",
        "",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- Restored: `{payload.get('restored', False)}`",
        f"- Config path: `{payload.get('config_path', '')}`",
        f"- Restore gate OK: `{gate.get('ok', False)}`",
        f"- Source preview: `{payload.get('source_preview_path', '')}`",
        "",
        "## Restored Changes",
        "",
    ]
    rows = list_of_objects(payload.get("restored_changes", []))
    if not rows:
        lines.append("No config changes were restored.")
    else:
        lines.extend(
            [
                "| Candidate | Config Path | Previous | Restored |",
                "| --- | --- | --- | --- |",
            ]
        )
        for row in rows:
            lines.append(
                "| "
                f"{row.get('candidate_id', '')} | "
                f"{row.get('config_path', '')} | "
                f"{json.dumps(row.get('previous_value', ''), sort_keys=True)} | "
                f"{json.dumps(row.get('restored_value', ''), sort_keys=True)} |"
            )
    lines.extend(["", "## Blockers", ""])
    blockers = string_list(gate.get("blockers", []))
    lines.extend([f"- `{blocker}`" for blocker in blockers] or ["- none"])
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This command requires a ready rollback preview, matching preview digest, matching source receipt digest, and unchanged current config digest.",
            "- It writes only the configured config file and does not execute agents, run backtests, route candidates, apply patches, or change iteration acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_config_application_restore_receipt_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved config application restore receipt."""
    return tuple(
        validate_json_file(
            payload_path=payload_path,
            schema_path=repo_root / SCHEMA_PATH,
        )
    )


def main() -> None:
    """CLI entrypoint for guarded config restore."""
    parser = argparse.ArgumentParser(
        description="Restore config from approved rollback preview evidence."
    )
    parser.add_argument("run_id")
    parser.add_argument("--preview-path", type=Path, required=True)
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args()
    payload = restore_config_with_preview(
        run_id=args.run_id,
        preview_path=args.preview_path,
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
        config_path=args.config,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload.get("restored", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
