"""Read-only config lineage report from saved config artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.config_application_executor import (
    DEFAULT_CONFIG_PATH,
    file_sha256,
    load_json_object,
    object_field,
    relative_path,
    resolve_path,
    string_list,
)
from orchestrator.schema_validation import (
    load_schema,
    validate_json_file,
    validate_json_payload,
)


CONFIG_LINEAGE_SCHEMA_VERSION = "config_lineage_v1"
SCHEMA_PATH = Path("schemas/config_lineage.schema.json")


STAGE_FILES = (
    ("config_change_candidate", "config_change_candidate.json"),
    ("operator_config_review", "operator_config_review.json"),
    ("config_application_dry_run", "config_application_dry_run.json"),
    ("config_application_receipt", "config_application_receipt.json"),
    ("config_application_rollback_preview", "config_application_rollback_preview.json"),
    ("config_application_restore_receipt", "config_application_restore_receipt.json"),
)


def write_config_lineage(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown config lineage artifacts."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    run_dir = experiments_dir / run_id
    config_path = resolve_path(config_path, repo_root)
    payload = build_config_lineage(
        run_id=run_id,
        run_dir=run_dir,
        repo_root=repo_root,
        config_path=config_path,
    )
    errors = validate_config_lineage_payload(
        payload,
        run_id=run_id,
        run_dir=run_dir,
        repo_root=repo_root,
        config_path=config_path,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError("config lineage failed schema validation: " + "; ".join(errors))
    json_path = run_dir / "config_lineage.json"
    md_path = run_dir / "config_lineage.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_config_lineage_markdown(payload), encoding="utf-8")
    return json_path, md_path, payload


def build_config_lineage(
    *,
    run_id: str,
    run_dir: Path,
    repo_root: Path,
    config_path: Path,
) -> dict[str, object]:
    """Build a deterministic lineage report for one run's config artifacts."""
    artifacts = {
        stage_name: run_dir / filename for stage_name, filename in STAGE_FILES
    }
    payloads = {
        stage_name: load_json_object(path) for stage_name, path in artifacts.items()
    }
    stages = [
        stage_row(
            stage_name=stage_name,
            path=artifacts[stage_name],
            payload=payloads[stage_name],
            repo_root=repo_root,
        )
        for stage_name, _ in STAGE_FILES
    ]
    checks = lineage_checks(
        run_id=run_id,
        current_config_path=config_path,
        artifacts=artifacts,
        payloads=payloads,
    )
    return {
        "schema_version": CONFIG_LINEAGE_SCHEMA_VERSION,
        "run_id": run_id,
        "run_dir": relative_path(run_dir, repo_root),
        "status": lineage_status(payloads),
        "ok": bool(checks["ok"]),
        "current_config": {
            "path": relative_path(config_path, repo_root),
            "exists": config_path.exists(),
            "sha256": file_sha256(config_path),
        },
        "stages": stages,
        "checks": checks,
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
        },
    }


def stage_row(
    *,
    stage_name: str,
    path: Path,
    payload: dict[str, Any],
    repo_root: Path,
) -> dict[str, object]:
    """Return one compact lineage stage row."""
    return {
        "stage_name": stage_name,
        "artifact_path": relative_path(path, repo_root),
        "exists": path.exists(),
        "sha256": file_sha256(path),
        "schema_version": str(payload.get("schema_version", "")),
        "status": stage_status(stage_name=stage_name, payload=payload),
        "action_succeeded": stage_action_succeeded(
            stage_name=stage_name,
            payload=payload,
        ),
        "config_before_sha256": str(payload.get("config_before_sha256", "")),
        "config_after_sha256": str(payload.get("config_after_sha256", "")),
        "blockers": stage_blockers(stage_name=stage_name, payload=payload),
        "source_links": stage_source_links(stage_name=stage_name, payload=payload),
    }


def stage_status(*, stage_name: str, payload: dict[str, Any]) -> str:
    """Return a stable status string for a stage."""
    if not payload:
        return "missing"
    if stage_name == "operator_config_review":
        intent = object_field(payload, "operator_intent")
        return str(intent.get("decision_requested", "not_recorded"))
    return str(payload.get("status", "present"))


def stage_action_succeeded(*, stage_name: str, payload: dict[str, Any]) -> bool:
    """Return true when a stage completed a write/action."""
    if stage_name == "config_application_receipt":
        return payload.get("applied") is True
    if stage_name == "config_application_restore_receipt":
        return payload.get("restored") is True
    return False


def stage_blockers(*, stage_name: str, payload: dict[str, Any]) -> list[str]:
    """Return blockers from stage-specific gate fields."""
    if not payload:
        return ["artifact_missing"]
    if stage_name == "config_application_dry_run":
        return string_list(object_field(payload, "application_gate").get("application_blockers", []))
    if stage_name == "config_application_receipt":
        return string_list(object_field(payload, "evidence_checks").get("blockers", []))
    if stage_name == "config_application_rollback_preview":
        return string_list(object_field(payload, "rollback_gate").get("blockers", []))
    if stage_name == "config_application_restore_receipt":
        return string_list(object_field(payload, "restore_gate").get("blockers", []))
    return []


def stage_source_links(*, stage_name: str, payload: dict[str, Any]) -> list[dict[str, object]]:
    """Return source artifact links recorded by one stage."""
    links: list[dict[str, object]] = []
    if not payload:
        return links
    if stage_name == "config_application_dry_run":
        add_nested_file_link(
            links,
            source_name="operator_config_review",
            container=object_field(payload, "source_operator_review"),
        )
        add_nested_file_link(
            links,
            source_name="config",
            container=object_field(payload, "source_config"),
        )
    for key, source_name in (
        ("source_dry_run_path", "config_application_dry_run"),
        ("source_operator_review_path", "operator_config_review"),
        ("source_receipt_path", "config_application_receipt"),
        ("source_preview_path", "config_application_rollback_preview"),
    ):
        if key in payload:
            links.append(
                {
                    "source_name": source_name,
                    "path": str(payload.get(key, "")),
                    "sha256": str(payload.get(key.replace("_path", "_sha256"), "")),
                }
            )
    return links


def add_nested_file_link(
    links: list[dict[str, object]],
    *,
    source_name: str,
    container: dict[str, Any],
) -> None:
    """Append a source link from an object containing a file record."""
    file_record = object_field(container, "file")
    if not file_record:
        return
    links.append(
        {
            "source_name": source_name,
            "path": str(file_record.get("path", "")),
            "sha256": str(file_record.get("sha256", "")),
        }
    )


def lineage_checks(
    *,
    run_id: str,
    current_config_path: Path,
    artifacts: dict[str, Path],
    payloads: dict[str, dict[str, Any]],
) -> dict[str, object]:
    """Return deterministic config lineage consistency checks."""
    errors: list[str] = []
    for stage_name, payload in payloads.items():
        if payload and str(payload.get("run_id", run_id)) != run_id:
            errors.append(f"{stage_name}_run_id_mismatch")
    errors.extend(source_digest_errors(artifacts=artifacts, payloads=payloads))
    current_config_sha = file_sha256(current_config_path)
    current_matches_latest = current_config_matches_latest(
        current_config_sha=current_config_sha,
        payloads=payloads,
    )
    if not current_matches_latest:
        errors.append("current_config_not_explained_by_latest_stage")
    return {
        "ok": not errors,
        "errors": errors,
        "stage_count": len(STAGE_FILES),
        "existing_stage_count": sum(1 for path in artifacts.values() if path.exists()),
        "applied": payloads["config_application_receipt"].get("applied") is True,
        "restored": (
            payloads["config_application_restore_receipt"].get("restored") is True
        ),
        "current_config_matches_latest_stage": current_matches_latest,
        "current_config_sha256": current_config_sha,
    }


def source_digest_errors(
    *,
    artifacts: dict[str, Path],
    payloads: dict[str, dict[str, Any]],
) -> list[str]:
    """Return cross-artifact digest mismatch errors."""
    errors: list[str] = []
    dry_run = payloads["config_application_dry_run"]
    receipt = payloads["config_application_receipt"]
    preview = payloads["config_application_rollback_preview"]
    restore = payloads["config_application_restore_receipt"]
    if receipt:
        if str(receipt.get("source_dry_run_sha256", "")) != file_sha256(
            artifacts["config_application_dry_run"]
        ):
            errors.append("receipt_dry_run_digest_mismatch")
        if str(receipt.get("source_operator_review_sha256", "")) != file_sha256(
            artifacts["operator_config_review"]
        ):
            errors.append("receipt_operator_review_digest_mismatch")
    if preview and str(preview.get("source_receipt_sha256", "")) != file_sha256(
        artifacts["config_application_receipt"]
    ):
        errors.append("preview_receipt_digest_mismatch")
    if restore:
        if str(restore.get("source_preview_sha256", "")) != file_sha256(
            artifacts["config_application_rollback_preview"]
        ):
            errors.append("restore_preview_digest_mismatch")
        if str(restore.get("source_receipt_sha256", "")) != file_sha256(
            artifacts["config_application_receipt"]
        ):
            errors.append("restore_receipt_digest_mismatch")
    if dry_run:
        config_file = object_field(object_field(dry_run, "source_config"), "file")
        if not config_file:
            errors.append("dry_run_config_source_missing")
    return errors


def current_config_matches_latest(
    *,
    current_config_sha: str,
    payloads: dict[str, dict[str, Any]],
) -> bool:
    """Return true when current config digest matches the latest config action."""
    restore = payloads["config_application_restore_receipt"]
    receipt = payloads["config_application_receipt"]
    dry_run = payloads["config_application_dry_run"]
    if restore and restore.get("restored") is True:
        return current_config_sha == str(restore.get("config_after_sha256", ""))
    if receipt and receipt.get("applied") is True:
        return current_config_sha == str(receipt.get("config_after_sha256", ""))
    if dry_run:
        config_file = object_field(object_field(dry_run, "source_config"), "file")
        return current_config_sha == str(config_file.get("sha256", ""))
    return True


def lineage_status(payloads: dict[str, dict[str, Any]]) -> str:
    """Return the top-level lineage status."""
    if payloads["config_application_restore_receipt"].get("restored") is True:
        return "restored"
    if payloads["config_application_receipt"].get("applied") is True:
        return "applied"
    if payloads["config_application_restore_receipt"] or payloads["config_application_receipt"]:
        return "blocked"
    return "partial"


def render_config_lineage_markdown(payload: dict[str, object]) -> str:
    """Render config lineage as markdown."""
    checks = object_field(payload, "checks")
    lines = [
        "# Config Lineage",
        "",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Existing stages: `{checks.get('existing_stage_count', 0)}`",
        f"- Current config matches latest stage: `{checks.get('current_config_matches_latest_stage', False)}`",
        "",
        "## Stages",
        "",
        "| Stage | Exists | Status | SHA-256 |",
        "| --- | --- | --- | --- |",
    ]
    for row_raw in payload.get("stages", []):
        row = row_raw if isinstance(row_raw, dict) else {}
        lines.append(
            "| "
            f"{row.get('stage_name', '')} | "
            f"{row.get('exists', False)} | "
            f"{row.get('status', '')} | "
            f"`{row.get('sha256', '')}` |"
        )
    lines.extend(["", "## Errors", ""])
    errors = string_list(checks.get("errors", []))
    lines.extend([f"- `{error}`" for error in errors] or ["- none"])
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This lineage is read-only and does not write config, delete memory, execute agents, run backtests, route candidates, apply patches, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_config_lineage_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved config lineage report."""
    return tuple(
        validate_json_file(
            payload_path=payload_path,
            schema_path=repo_root / SCHEMA_PATH,
        )
    )


def validate_config_lineage_payload(
    payload: dict[str, object],
    *,
    run_id: str,
    run_dir: Path,
    repo_root: Path,
    config_path: Path,
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an in-memory config lineage payload."""
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
        validate_config_lineage_consistency(
            normalized,
            run_id=run_id,
            run_dir=run_dir,
            repo_root=repo_root,
        )
    )
    if require_current_evidence:
        expected = build_config_lineage(
            run_id=run_id,
            run_dir=run_dir,
            repo_root=repo_root,
            config_path=config_path,
        )
        if normalized != expected:
            errors.append("config_lineage current evidence mismatch")
    return tuple(errors)


def validate_config_lineage_consistency(
    payload: dict[str, object],
    *,
    run_id: str,
    run_dir: Path,
    repo_root: Path,
) -> tuple[str, ...]:
    """Return stable internal consistency errors for config lineage."""
    errors: list[str] = []
    if str(payload.get("run_id", "")) != run_id:
        errors.append("config_lineage run_id mismatch")
    if str(payload.get("run_dir", "")) != relative_path(run_dir, repo_root):
        errors.append("config_lineage run_dir mismatch")
    stages = [
        row for row in payload.get("stages", []) if isinstance(row, dict)
    ]
    checks = object_field(payload, "checks")
    expected_stage_names = [stage_name for stage_name, _ in STAGE_FILES]
    stage_names = [str(row.get("stage_name", "")) for row in stages]
    if stage_names != expected_stage_names:
        errors.append("config_lineage stage order mismatch")
    expected_paths = [
        relative_path(run_dir / filename, repo_root) for _, filename in STAGE_FILES
    ]
    if [str(row.get("artifact_path", "")) for row in stages] != expected_paths:
        errors.append("config_lineage stage path mismatch")
    existing_count = sum(1 for row in stages if row.get("exists") is True)
    if int(checks.get("stage_count", -1) or 0) != len(STAGE_FILES):
        errors.append("config_lineage stage count mismatch")
    if int(checks.get("existing_stage_count", -1) or 0) != existing_count:
        errors.append("config_lineage existing stage count mismatch")
    receipt_stage = stage_by_name(stages, "config_application_receipt")
    restore_stage = stage_by_name(stages, "config_application_restore_receipt")
    applied = bool(receipt_stage.get("action_succeeded", False))
    restored = bool(restore_stage.get("action_succeeded", False))
    if bool(checks.get("applied", False)) != applied:
        errors.append("config_lineage applied mismatch")
    if bool(checks.get("restored", False)) != restored:
        errors.append("config_lineage restored mismatch")
    if bool(payload.get("ok", False)) != bool(checks.get("ok", False)):
        errors.append("config_lineage ok mismatch")
    if bool(checks.get("ok", False)) != (not string_list(checks.get("errors", []))):
        errors.append("config_lineage check ok mismatch")
    current_config = object_field(payload, "current_config")
    if str(checks.get("current_config_sha256", "")) != str(
        current_config.get("sha256", "")
    ):
        errors.append("config_lineage current config sha mismatch")
    expected_status = status_from_stage_rows(stages)
    if str(payload.get("status", "")) != expected_status:
        errors.append("config_lineage status mismatch")
    return tuple(errors)


def stage_by_name(
    stages: list[dict[str, object]],
    stage_name: str,
) -> dict[str, object]:
    """Return a stage row by name or an empty object."""
    for row in stages:
        if row.get("stage_name") == stage_name:
            return row
    return {}


def status_from_stage_rows(stages: list[dict[str, object]]) -> str:
    """Return lineage status derived from compact stage rows."""
    restore = stage_by_name(stages, "config_application_restore_receipt")
    receipt = stage_by_name(stages, "config_application_receipt")
    if restore.get("action_succeeded") is True:
        return "restored"
    if receipt.get("action_succeeded") is True:
        return "applied"
    if restore.get("exists") is True or receipt.get("exists") is True:
        return "blocked"
    return "partial"


def main() -> None:
    """CLI entrypoint for config lineage reports."""
    parser = argparse.ArgumentParser(description="Write a read-only config lineage report.")
    parser.add_argument("run_id")
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args()
    _, _, payload = write_config_lineage(
        run_id=args.run_id,
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
        config_path=args.config,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
