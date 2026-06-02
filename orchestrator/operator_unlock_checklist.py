"""Read-only operator checklist for real Codex CLI unlock evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.operator_action_audit import (
    file_record,
    load_json_object,
    object_field,
    resolve_path,
    schema_errors,
)
from orchestrator.schema_validation import validate_json_file


OPERATOR_UNLOCK_CHECKLIST_SCHEMA_VERSION = "operator_unlock_checklist_v1"
SCHEMA_PATH = Path("schemas/operator_unlock_checklist.schema.json")


def write_operator_unlock_checklist(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown operator unlock checklist artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_operator_unlock_checklist(run_dir=run_dir, repo_root=repo_root)
    json_path = run_dir / "operator_unlock_checklist.json"
    md_path = run_dir / "operator_unlock_checklist.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_operator_unlock_checklist_markdown(payload), encoding="utf-8")
    errors = validate_operator_unlock_checklist_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(
            "operator unlock checklist failed schema validation: " + "; ".join(errors)
        )
    return json_path, md_path, payload


def build_operator_unlock_checklist(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return a read-only unlock checklist for one iteration run."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    codex_preflight_path = run_dir / "codex_cli_execution_preflight.json"
    codex_preflight = load_json_object(codex_preflight_path)
    checklist = build_codex_unlock_checklist(codex_preflight=codex_preflight)
    return {
        "schema_version": OPERATOR_UNLOCK_CHECKLIST_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "status": str(checklist.get("status", "missing_preflight")),
        "ready": bool(checklist.get("ready", False)),
        "item_count": int(checklist.get("item_count", 0) or 0),
        "passed_count": int(checklist.get("passed_count", 0) or 0),
        "failed_count": int(checklist.get("failed_count", 0) or 0),
        "next_step": str(checklist.get("next_step", "")),
        "source_artifacts": {
            "codex_cli_execution_preflight": source_artifact(
                path=codex_preflight_path,
                schema_path=repo_root / "schemas/codex_cli_execution_preflight.schema.json",
                artifact_name="codex_cli_execution_preflight",
                repo_root=repo_root,
            ),
        },
        "items": list_of_dicts(checklist.get("items", [])),
        "authority": object_field(checklist, "authority"),
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "does_not_record_unlock_approval": True,
            "does_not_execute_codex_cli": True,
            "does_not_execute_agents": True,
            "does_not_create_workspace": True,
            "does_not_apply_patches": True,
            "does_not_route_agents": True,
            "does_not_change_acceptance": True,
        },
    }


def source_artifact(
    *,
    path: Path,
    schema_path: Path,
    artifact_name: str,
    repo_root: Path,
) -> dict[str, object]:
    """Return one source artifact row."""
    return {
        "artifact_name": artifact_name,
        "file": file_record(path, repo_root),
        "schema_errors": list(schema_errors(path=path, schema_path=schema_path)),
    }


def build_codex_unlock_checklist(
    *,
    codex_preflight: dict[str, Any],
) -> dict[str, object]:
    """Return a grouped, read-only checklist for real Codex CLI unlock evidence."""
    if not codex_preflight:
        return checklist_payload(
            status="missing_preflight",
            ready=False,
            next_step="run codex_cli_execution_preflight before reviewing unlock evidence",
            items=[],
        )
    profiles = list_of_dicts(codex_preflight.get("profiles", []))
    real_profiles = [
        profile
        for profile in profiles
        if bool(profile.get("requires_operator_unlock", False))
    ]
    summary = object_field(codex_preflight, "summary")
    if not real_profiles:
        canary_count = int(summary.get("canary_exempt_count", 0) or 0)
        status = "canary_exempt" if canary_count else "not_requested"
        next_step = (
            "checked-in canary execution is exempt from real Codex unlock"
            if canary_count
            else "keep real Codex execution disabled unless explicitly reviewed"
        )
        return checklist_payload(
            status=status,
            ready=canary_count > 0,
            next_step=next_step,
            items=[],
        )

    items = [
        item
        for profile in real_profiles
        for item in checklist_items_for_profile(profile=profile)
    ]
    failed_count = sum(1 for item in items if item["status"] == "failed")
    blockers = string_rows(codex_preflight.get("blocking_errors", []))
    ready = bool(codex_preflight.get("ok", False)) and failed_count == 0 and not blockers
    return checklist_payload(
        status="ready" if ready else "blocked",
        ready=ready,
        next_step=(
            "review operator unlock request before any real Codex execution"
            if ready
            else "complete failed unlock evidence items before enabling real Codex execution"
        ),
        items=items,
    )


def checklist_items_for_profile(*, profile: dict[str, Any]) -> list[dict[str, object]]:
    """Return grouped unlock checklist items for one real Codex profile."""
    profile_name = str(profile.get("profile_name", ""))
    checks = object_field(profile, "checks")
    groups = [
        (
            "operator_unlock_request",
            "Canonical operator unlock request",
            [
                "operator_unlock_request_path_declared",
                "operator_unlock_request_exists",
                "operator_unlock_request_path_is_run_artifact",
                "operator_unlock_request_path_is_canonical_run_artifact",
                "operator_unlock_request_contract_valid",
                "operator_unlock_request_schema_version_matches",
                "operator_unlock_request_ok",
                "operator_unlock_request_ready",
            ],
            "write the canonical codex_cli_operator_unlock_request.json artifact",
        ),
        (
            "operator_intent",
            "Explicit operator intent",
            [
                "operator_request_scope_matches",
                "operator_request_explicitly_requested",
                "operator_request_requested_by_present",
                "operator_request_confirmation_phrase_matches",
                "operator_request_required_confirmation_hash_matches",
                "operator_request_provided_confirmation_hash_matches",
            ],
            "record explicit operator intent with the required confirmation phrase",
        ),
        (
            "source_evidence",
            "Readiness evidence binding",
            [
                "operator_request_source_pipeline_hash_matches",
                "operator_request_source_pipeline_path_matches_record",
                "operator_request_source_pipeline_path_is_canonical_run_artifact",
                "operator_request_source_dry_run_hash_matches",
                "operator_request_source_dry_run_path_matches_record",
                "operator_request_source_dry_run_path_is_canonical_run_artifact",
                "operator_request_source_dry_run_plan_present",
                "operator_request_source_dry_run_plan_matches_review",
            ],
            "regenerate readiness pipeline, dry run, and operator request together",
        ),
        (
            "execution_identity",
            "Reviewed execution identity",
            [
                "operator_request_run_id_matches",
                "operator_request_run_dir_matches_run",
                "operator_request_agent_name_matches",
                "operator_request_profile_name_matches",
                "operator_request_round_id_matches",
                "operator_request_attempt_id_matches",
            ],
            "bind the operator request to this run, profile, round, and attempt",
        ),
        (
            "command_review",
            "Reviewed command digest",
            [
                "operator_request_command_matches_profile",
                "operator_request_command_sha256_matches_profile",
            ],
            "review the exact Codex command and command digest",
        ),
        (
            "workspace_boundary",
            "Reviewed workspace boundary",
            [
                "operator_request_workspace_prefix_matches_run",
                "operator_request_workspace_path_matches_expected",
            ],
            "bind the request to the exact reviewed isolated workspace path",
        ),
        (
            "mutation_boundary",
            "Strategy-only mutation boundary",
            [
                "operator_request_targets_current_strategy",
                "operator_request_allows_strategy_only",
            ],
            "restrict allowed mutation paths to strategies/current_strategy.py",
        ),
        (
            "non_executing_request",
            "Operator request remains non-executing",
            ["operator_request_does_not_execute_by_itself"],
            "ensure approval artifacts do not execute Codex by themselves",
        ),
    ]
    return [
        checklist_item(
            profile_name=profile_name,
            group_id=group_id,
            label=label,
            check_keys=check_keys,
            checks=checks,
            next_step=next_step,
        )
        for group_id, label, check_keys, next_step in groups
    ]


def checklist_item(
    *,
    profile_name: str,
    group_id: str,
    label: str,
    check_keys: list[str],
    checks: dict[str, Any],
    next_step: str,
) -> dict[str, object]:
    """Return one grouped checklist item."""
    failed_keys = [key for key in check_keys if not bool(checks.get(key, False))]
    return {
        "check_id": f"{profile_name}:{group_id}" if profile_name else group_id,
        "profile_name": profile_name,
        "label": label,
        "status": "failed" if failed_keys else "passed",
        "required": True,
        "passed_check_count": len(check_keys) - len(failed_keys),
        "total_check_count": len(check_keys),
        "failed_checks": failed_keys,
        "evidence": (
            f"{len(check_keys) - len(failed_keys)}/{len(check_keys)} checks passed"
        ),
        "next_step": "" if not failed_keys else next_step,
    }


def checklist_payload(
    *,
    status: str,
    ready: bool,
    next_step: str,
    items: list[dict[str, object]],
) -> dict[str, object]:
    """Return a stable Codex unlock checklist payload."""
    passed_count = sum(1 for item in items if item["status"] == "passed")
    failed_count = sum(1 for item in items if item["status"] == "failed")
    return {
        "status": status,
        "ready": ready,
        "item_count": len(items),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "next_step": next_step,
        "items": items,
        "authority": {
            "checklist_can_unlock_codex": False,
            "checklist_can_execute_codex": False,
            "checklist_can_create_workspace": False,
            "checklist_can_apply_patches": False,
            "checklist_can_change_acceptance": False,
        },
    }


def render_operator_unlock_checklist_markdown(payload: dict[str, object]) -> str:
    """Render operator unlock checklist as markdown."""
    lines = [
        "# Operator Unlock Checklist",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- Ready: `{payload.get('ready', False)}`",
        f"- Failed items: `{payload.get('failed_count', 0)}`",
        f"- Next step: {payload.get('next_step', '')}",
        "",
        "| Check | Status | Evidence | Next Step |",
        "| --- | --- | --- | --- |",
    ]
    items = list_of_dicts(payload.get("items", []))
    if not items:
        lines.append("| none | `not_applicable` | no real Codex profile requires unlock | |")
    for item in items:
        lines.append(
            "| "
            f"{item.get('label', '')} | "
            f"`{item.get('status', '')}` | "
            f"{item.get('evidence', '')} | "
            f"{item.get('next_step', '')} |"
        )
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This checklist is read-only and does not record unlock approval or execute Codex.",
            "- It does not execute agents, create workspaces, apply patches, route agents, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_operator_unlock_checklist_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved operator unlock checklist artifact."""
    return tuple(
        validate_json_file(
            payload_path=payload_path,
            schema_path=repo_root / SCHEMA_PATH,
        )
    )


def list_of_dicts(value: object) -> list[dict[str, Any]]:
    """Return object rows from a possible list."""
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def string_rows(value: object) -> list[str]:
    """Return string rows from a possible list."""
    return [str(row) for row in value] if isinstance(value, list) else []


def main() -> None:
    """CLI entrypoint for operator unlock checklist generation."""
    parser = argparse.ArgumentParser(
        description="Write a read-only operator unlock checklist for one iteration run."
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    _, _, payload = write_operator_unlock_checklist(
        run_dir=args.run_dir,
        repo_root=args.repo_root,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
