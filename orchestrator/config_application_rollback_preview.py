"""Read-only rollback preview for applied config changes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.config_application_executor import (
    CONFIG_APPLICATION_RECEIPT_SCHEMA_VERSION,
    DEFAULT_CONFIG_PATH,
    file_sha256,
    list_of_objects,
    load_json_object,
    object_field,
    relative_path,
    resolve_path,
    string_list,
    unique_strings,
)
from orchestrator.schema_validation import (
    load_schema,
    validate_json_file,
    validate_json_payload,
)


CONFIG_APPLICATION_ROLLBACK_PREVIEW_SCHEMA_VERSION = (
    "config_application_rollback_preview_v1"
)
SCHEMA_PATH = Path("schemas/config_application_rollback_preview.schema.json")


def write_config_application_rollback_preview(
    *,
    run_id: str,
    receipt_path: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> tuple[Path, Path, dict[str, object]]:
    """Write a read-only rollback preview from a config application receipt."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    receipt_path = resolve_path(receipt_path, repo_root)
    config_path = resolve_path(config_path, repo_root)
    run_dir = experiments_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = build_config_application_rollback_preview(
        run_id=run_id,
        run_dir=run_dir,
        repo_root=repo_root,
        receipt_path=receipt_path,
        config_path=config_path,
    )
    errors = validate_config_application_rollback_preview_payload(
        payload,
        run_id=run_id,
        run_dir=run_dir,
        repo_root=repo_root,
        receipt_path=receipt_path,
        config_path=config_path,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "config application rollback preview failed schema validation: "
            + "; ".join(errors)
        )
    json_path = run_dir / "config_application_rollback_preview.json"
    md_path = run_dir / "config_application_rollback_preview.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_rollback_preview_markdown(payload), encoding="utf-8")
    return json_path, md_path, payload


def build_config_application_rollback_preview(
    *,
    run_id: str,
    run_dir: Path,
    repo_root: Path,
    receipt_path: Path,
    config_path: Path,
) -> dict[str, object]:
    """Build a deterministic preview for manually restoring config values."""
    receipt = load_json_object(receipt_path)
    config_payload = load_json_object(config_path)
    receipt_schema_errors = (
        validate_json_file(
            payload_path=receipt_path,
            schema_path=repo_root / "schemas/config_application_receipt.schema.json",
        )
        if receipt_path.exists() and receipt_path.is_file()
        else ("missing_config_application_receipt_file",)
    )
    receipt_applied = receipt.get("applied") is True
    applied_changes = list_of_objects(receipt.get("applied_changes", []))
    rollback_plan = build_rollback_plan(
        config_payload=config_payload,
        applied_changes=applied_changes,
        receipt_applied=receipt_applied,
    )
    blockers = rollback_preview_blockers(
        run_id=run_id,
        receipt=receipt,
        receipt_schema_errors=tuple(receipt_schema_errors),
        receipt_path=receipt_path,
        config_path=config_path,
        rollback_plan=rollback_plan,
    )
    eligible = not blockers
    status = rollback_preview_status(
        receipt_applied=receipt_applied,
        eligible=eligible,
    )
    affected_paths = [str(row.get("config_path", "")) for row in rollback_plan]
    return {
        "schema_version": CONFIG_APPLICATION_ROLLBACK_PREVIEW_SCHEMA_VERSION,
        "run_id": run_id,
        "run_dir": relative_path(run_dir, repo_root),
        "status": status,
        "ok": True,
        "source_receipt_path": relative_path(receipt_path, repo_root),
        "source_receipt_sha256": file_sha256(receipt_path),
        "source_receipt_schema_errors": list(receipt_schema_errors),
        "source_receipt_status": str(receipt.get("status", "")),
        "source_receipt_applied": receipt_applied,
        "config_path": relative_path(config_path, repo_root),
        "current_config_sha256": file_sha256(config_path),
        "receipt_config_after_sha256": str(receipt.get("config_after_sha256", "")),
        "rollback_gate": {
            "eligible_for_manual_restore": eligible,
            "blockers": blockers,
            "matching_applied_config_digest": (
                file_sha256(config_path)
                == str(receipt.get("config_after_sha256", ""))
            ),
            "applied_change_count": len(applied_changes),
            "restorable_change_count": sum(
                1 for row in rollback_plan if row.get("can_restore") is True
            ),
        },
        "rollback_plan": rollback_plan,
        "next_run_impact": {
            "affected_config_paths": affected_paths,
            "impact_rows": build_impact_rows(rollback_plan),
            "summary": impact_summary(rollback_plan),
        },
        "policy": {
            "requires_config_application_receipt": True,
            "read_only": True,
            "does_not_write_config": True,
            "does_not_delete_memory": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_route_candidates": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
        },
    }


def build_rollback_plan(
    *,
    config_payload: dict[str, Any],
    applied_changes: list[dict[str, object]],
    receipt_applied: bool,
) -> list[dict[str, object]]:
    """Return per-field restore rows without modifying config."""
    rows: list[dict[str, object]] = []
    for change in applied_changes:
        path = str(change.get("config_path", ""))
        current_value = value_at_path(config_payload, path)
        expected_applied_value = change.get("new_value")
        restore_value = change.get("previous_value")
        restore_path_exists = bool(change.get("previous_path_exists", True))
        current_matches = values_equal(current_value, expected_applied_value)
        rows.append(
            {
                "candidate_id": str(change.get("candidate_id", "")),
                "config_path": path,
                "current_value": current_value,
                "expected_applied_value": expected_applied_value,
                "restore_value": restore_value,
                "restore_path_exists": restore_path_exists,
                "current_matches_expected_applied": current_matches,
                "can_restore": bool(receipt_applied and current_matches),
                "source_artifact": str(
                    change.get("source_artifact", "config_application_receipt.json")
                ),
            }
        )
    return rows


def rollback_preview_blockers(
    *,
    run_id: str,
    receipt: dict[str, Any],
    receipt_schema_errors: tuple[str, ...],
    receipt_path: Path,
    config_path: Path,
    rollback_plan: list[dict[str, object]],
) -> list[str]:
    """Return stable blockers for a manual config restore preview."""
    blockers: list[str] = []
    if receipt_schema_errors:
        blockers.append("receipt_schema_invalid")
    if receipt.get("schema_version") != CONFIG_APPLICATION_RECEIPT_SCHEMA_VERSION:
        blockers.append("receipt_schema_version_invalid")
    if str(receipt.get("run_id", "")) != run_id:
        blockers.append("receipt_run_id_mismatch")
    if receipt.get("applied") is not True:
        blockers.append("receipt_not_applied")
    if not rollback_plan:
        blockers.append("no_applied_changes")
    if not receipt_path.exists() or not receipt_path.is_file():
        blockers.append("receipt_missing")
    if not config_path.exists() or not config_path.is_file():
        blockers.append("config_missing")
    elif file_sha256(config_path) != str(receipt.get("config_after_sha256", "")):
        blockers.append("config_digest_mismatch")
    if any(
        row.get("current_matches_expected_applied") is not True
        for row in rollback_plan
    ):
        blockers.append("rollback_plan_current_value_mismatch")
    return unique_strings(blockers)


def rollback_preview_status(*, receipt_applied: bool, eligible: bool) -> str:
    """Return the top-level rollback preview status."""
    if not receipt_applied:
        return "no_applied_config_change"
    return "rollback_ready" if eligible else "rollback_blocked"


def build_impact_rows(
    rollback_plan: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return deterministic descriptions of likely next-run config effects."""
    rows: list[dict[str, object]] = []
    for row in rollback_plan:
        path = str(row.get("config_path", ""))
        rows.append(
            {
                "config_path": path,
                "current_value": row.get("current_value"),
                "restore_value": row.get("restore_value"),
                "likely_runtime_effect": likely_runtime_effect(path),
            }
        )
    return rows


def impact_summary(rollback_plan: list[dict[str, object]]) -> str:
    """Return a compact next-run impact summary."""
    if not rollback_plan:
        return "No applied config changes are available to inspect."
    paths = ", ".join(str(row.get("config_path", "")) for row in rollback_plan)
    return f"Next runs would continue using the applied config values for: {paths}."


def likely_runtime_effect(config_path: str) -> str:
    """Return a deterministic human-readable effect for known config paths."""
    known_effects = {
        "agents": (
            "Changes which strategy modifier profiles future iteration runs can select."
        ),
        "memory_filter.recent_record_limit": (
            "Changes how many recent outcome-memory rows candidate filtering reads."
        ),
        "memory_filter.failed_patch_threshold": (
            "Changes when repeated failed patch hashes are filtered."
        ),
        "memory_filter.failed_direction_threshold": (
            "Changes when repeated failed direction tags are filtered."
        ),
    }
    return known_effects.get(
        config_path,
        "Affects future runs only through the configured orchestrator setting.",
    )


def render_rollback_preview_markdown(payload: dict[str, object]) -> str:
    """Render a config rollback preview as markdown."""
    gate = object_field(payload, "rollback_gate")
    lines = [
        "# Config Application Rollback Preview",
        "",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- Source receipt: `{payload.get('source_receipt_path', '')}`",
        f"- Eligible for manual restore: `{gate.get('eligible_for_manual_restore', False)}`",
        f"- Current config SHA-256: `{payload.get('current_config_sha256', '')}`",
        "",
        "## Rollback Plan",
        "",
    ]
    rows = list_of_objects(payload.get("rollback_plan", []))
    if not rows:
        lines.append("No applied config changes are available for restore preview.")
    else:
        lines.extend(
            [
                "| Config Path | Current | Restore To | Can Restore |",
                "| --- | --- | --- | --- |",
            ]
        )
        for row in rows:
            lines.append(
                "| "
                f"{row.get('config_path', '')} | "
                f"{json.dumps(row.get('current_value', ''), sort_keys=True)} | "
                f"{json.dumps(row.get('restore_value', ''), sort_keys=True)} | "
                f"{row.get('can_restore', False)} |"
            )
    lines.extend(["", "## Blockers", ""])
    blockers = string_list(gate.get("blockers", []))
    lines.extend([f"- `{blocker}`" for blocker in blockers] or ["- none"])
    lines.extend(["", "## Next Run Impact", ""])
    impact = object_field(payload, "next_run_impact")
    lines.append(str(impact.get("summary", "")))
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This preview is read-only and does not write config, delete memory, execute agents, run backtests, route candidates, apply patches, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_config_application_rollback_preview_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved config application rollback preview."""
    return tuple(
        validate_json_file(
            payload_path=payload_path,
            schema_path=repo_root / SCHEMA_PATH,
        )
    )


def validate_config_application_rollback_preview_payload(
    payload: dict[str, object],
    *,
    run_id: str,
    run_dir: Path,
    repo_root: Path,
    receipt_path: Path,
    config_path: Path,
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an in-memory config application rollback preview payload."""
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
        validate_config_application_rollback_preview_consistency(
            normalized,
            run_id=run_id,
            run_dir=run_dir,
            repo_root=repo_root,
        )
    )
    if require_current_evidence:
        expected = build_config_application_rollback_preview(
            run_id=run_id,
            run_dir=run_dir,
            repo_root=repo_root,
            receipt_path=receipt_path,
            config_path=config_path,
        )
        if normalized != expected:
            errors.append(
                "config_application_rollback_preview current evidence mismatch"
            )
    return tuple(errors)


def validate_config_application_rollback_preview_consistency(
    payload: dict[str, object],
    *,
    run_id: str,
    run_dir: Path,
    repo_root: Path,
) -> tuple[str, ...]:
    """Return stable internal consistency errors for rollback previews."""
    errors: list[str] = []
    if str(payload.get("run_id", "")) != run_id:
        errors.append("config_application_rollback_preview run_id mismatch")
    if str(payload.get("run_dir", "")) != relative_path(run_dir, repo_root):
        errors.append("config_application_rollback_preview run_dir mismatch")
    gate = object_field(payload, "rollback_gate")
    plan = list_of_objects(payload.get("rollback_plan", []))
    blockers = string_list(gate.get("blockers", []))
    receipt_applied = bool(payload.get("source_receipt_applied", False))
    eligible = not blockers
    if bool(gate.get("eligible_for_manual_restore", False)) != eligible:
        errors.append("config_application_rollback_preview eligible mismatch")
    if bool(gate.get("matching_applied_config_digest", False)) != (
        str(payload.get("current_config_sha256", ""))
        == str(payload.get("receipt_config_after_sha256", ""))
    ):
        errors.append("config_application_rollback_preview digest match mismatch")
    if int(gate.get("applied_change_count", -1) or 0) != len(plan):
        errors.append("config_application_rollback_preview applied count mismatch")
    restorable_count = sum(1 for row in plan if row.get("can_restore") is True)
    if int(gate.get("restorable_change_count", -1) or 0) != restorable_count:
        errors.append("config_application_rollback_preview restorable count mismatch")
    expected_status = rollback_preview_status(
        receipt_applied=receipt_applied,
        eligible=eligible,
    )
    if str(payload.get("status", "")) != expected_status:
        errors.append("config_application_rollback_preview status mismatch")
    for row in plan:
        current_matches = values_equal(
            row.get("current_value"),
            row.get("expected_applied_value"),
        )
        if bool(row.get("current_matches_expected_applied", False)) != current_matches:
            errors.append("config_application_rollback_preview row match mismatch")
        if "restore_path_exists" in row and not isinstance(
            row.get("restore_path_exists"),
            bool,
        ):
            errors.append("config_application_rollback_preview restore path invalid")
        if bool(row.get("can_restore", False)) != bool(
            receipt_applied and current_matches
        ):
            errors.append("config_application_rollback_preview row restore mismatch")
    expected_impact = {
        "affected_config_paths": [str(row.get("config_path", "")) for row in plan],
        "impact_rows": build_impact_rows(plan),
        "summary": impact_summary(plan),
    }
    if object_field(payload, "next_run_impact") != expected_impact:
        errors.append("config_application_rollback_preview impact mismatch")
    return tuple(errors)


def value_at_path(payload: dict[str, Any], dotted_path: str) -> object:
    """Return a nested JSON value for a dotted config path."""
    cursor: object = payload
    for part in [part for part in dotted_path.split(".") if part]:
        if not isinstance(cursor, dict) or part not in cursor:
            return None
        cursor = cursor[part]
    return cursor


def values_equal(left: object, right: object) -> bool:
    """Compare JSON-like values deterministically."""
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def main() -> None:
    """CLI entrypoint for config application rollback preview."""
    parser = argparse.ArgumentParser(
        description="Write a read-only config application rollback preview."
    )
    parser.add_argument("run_id")
    parser.add_argument("--receipt-path", type=Path, required=True)
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args()
    _, _, payload = write_config_application_rollback_preview(
        run_id=args.run_id,
        receipt_path=args.receipt_path,
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
        config_path=args.config,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
