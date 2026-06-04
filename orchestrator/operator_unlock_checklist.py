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
from orchestrator.codex_cli_intake_readiness import (
    build_codex_cli_intake_readiness,
    validate_codex_cli_intake_readiness,
)
from orchestrator.schema_validation import validate_json_file, validate_json_payload


OPERATOR_UNLOCK_CHECKLIST_SCHEMA_VERSION = "operator_unlock_checklist_v1"
SCHEMA_PATH = Path("schemas/operator_unlock_checklist.schema.json")
MANUAL_APPROVAL_PHRASE = "I approve this Codex CLI candidate for manual enablement"
OPERATOR_REQUEST_PHRASE = "I request operator review for real Codex CLI execution"

CHECK_TO_BLOCKER_CODE = {
    "operator_unlock_request_path_declared": "operator_unlock_request_path_missing",
    "operator_unlock_request_exists": "operator_unlock_request_missing",
    "operator_unlock_request_path_is_run_artifact": (
        "operator_unlock_request_path_not_run_artifact"
    ),
    "operator_unlock_request_path_is_canonical_run_artifact": (
        "operator_unlock_request_path_not_canonical_run_artifact"
    ),
    "operator_unlock_request_contract_valid": "operator_unlock_request_contract_invalid",
    "operator_unlock_request_schema_version_matches": (
        "operator_unlock_request_schema_version_mismatch"
    ),
    "operator_unlock_request_ok": "operator_unlock_request_not_ok",
    "operator_unlock_request_ready": "operator_unlock_request_not_ready",
    "operator_request_run_id_matches": "operator_request_run_id_mismatch",
    "operator_request_run_dir_matches_run": "operator_request_run_dir_mismatch",
    "operator_request_scope_matches": "operator_request_scope_mismatch",
    "operator_request_explicitly_requested": "operator_request_not_explicitly_requested",
    "operator_request_requested_by_present": "operator_request_requested_by_missing",
    "operator_request_confirmation_phrase_matches": (
        "operator_request_confirmation_phrase_mismatch"
    ),
    "operator_request_required_confirmation_hash_matches": (
        "operator_request_required_confirmation_hash_mismatch"
    ),
    "operator_request_provided_confirmation_hash_matches": (
        "operator_request_provided_confirmation_hash_mismatch"
    ),
    "operator_request_source_pipeline_hash_matches": (
        "operator_request_source_pipeline_hash_mismatch"
    ),
    "operator_request_source_pipeline_path_matches_record": (
        "operator_request_source_pipeline_path_mismatch"
    ),
    "operator_request_source_pipeline_path_is_canonical_run_artifact": (
        "operator_request_source_pipeline_path_not_canonical_run_artifact"
    ),
    "operator_request_source_dry_run_hash_matches": (
        "operator_request_source_dry_run_hash_mismatch"
    ),
    "operator_request_source_dry_run_path_matches_record": (
        "operator_request_source_dry_run_path_mismatch"
    ),
    "operator_request_source_dry_run_path_is_canonical_run_artifact": (
        "operator_request_source_dry_run_path_not_canonical_run_artifact"
    ),
    "operator_request_source_dry_run_plan_present": (
        "operator_request_source_dry_run_plan_missing"
    ),
    "operator_request_source_dry_run_plan_matches_review": (
        "operator_request_source_dry_run_plan_mismatch"
    ),
    "operator_request_agent_name_matches": "operator_request_agent_name_mismatch",
    "operator_request_profile_name_matches": "operator_request_profile_name_mismatch",
    "operator_request_round_id_matches": "operator_request_round_id_mismatch",
    "operator_request_attempt_id_matches": "operator_request_attempt_id_mismatch",
    "operator_request_command_matches_profile": "operator_request_command_mismatch",
    "operator_request_command_sha256_matches_profile": (
        "operator_request_command_sha256_mismatch"
    ),
    "operator_request_workspace_prefix_matches_run": (
        "operator_request_workspace_prefix_mismatch"
    ),
    "operator_request_workspace_path_matches_expected": (
        "operator_request_workspace_path_mismatch"
    ),
    "operator_request_targets_current_strategy": (
        "operator_request_target_not_current_strategy"
    ),
    "operator_request_allows_strategy_only": (
        "operator_request_mutation_paths_not_strategy_only"
    ),
    "operator_request_does_not_execute_by_itself": (
        "operator_request_executes_by_itself"
    ),
}

GROUP_ARTIFACTS = {
    "operator_unlock_request": ["codex_cli_operator_unlock_request"],
    "operator_intent": ["codex_cli_operator_unlock_request"],
    "source_evidence": [
        "codex_cli_readiness_pipeline",
        "codex_cli_real_execution_dry_run",
        "codex_cli_operator_unlock_request",
    ],
    "execution_identity": [
        "codex_cli_execution_candidate",
        "codex_cli_real_execution_dry_run",
        "codex_cli_operator_unlock_request",
    ],
    "command_review": [
        "codex_cli_execution_candidate",
        "codex_cli_real_execution_dry_run",
        "codex_cli_operator_unlock_request",
    ],
    "workspace_boundary": [
        "codex_cli_execution_candidate",
        "codex_cli_real_execution_dry_run",
        "codex_cli_operator_unlock_request",
    ],
    "mutation_boundary": [
        "codex_cli_execution_candidate",
        "codex_cli_real_execution_dry_run",
        "codex_cli_operator_unlock_request",
    ],
    "non_executing_request": ["codex_cli_operator_unlock_request"],
}


def write_operator_unlock_checklist(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown operator unlock checklist artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_operator_unlock_checklist(run_dir=run_dir, repo_root=repo_root)
    errors = validate_operator_unlock_checklist_payload(
        payload,
        run_dir=run_dir,
        repo_root=repo_root,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "operator unlock checklist failed schema validation: " + "; ".join(errors)
        )
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
    items = list_of_dicts(checklist.get("items", []))
    navigation = build_unlock_navigation(
        run_dir=run_dir,
        repo_root=repo_root,
        checklist=checklist,
        codex_preflight=codex_preflight,
        items=items,
    )
    intake_readiness = build_codex_cli_intake_readiness(
        run_dir=run_dir,
        repo_root=repo_root,
    )
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
        "navigation": navigation,
        "codex_intake_readiness": intake_readiness,
        "items": items,
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
    run_id = str(codex_preflight.get("run_id", ""))
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
        for item in checklist_items_for_profile(profile=profile, run_id=run_id)
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


def checklist_items_for_profile(
    *,
    profile: dict[str, Any],
    run_id: str = "",
) -> list[dict[str, object]]:
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
            profile=profile,
            run_id=run_id,
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
    profile: dict[str, Any],
    run_id: str,
    profile_name: str,
    group_id: str,
    label: str,
    check_keys: list[str],
    checks: dict[str, Any],
    next_step: str,
) -> dict[str, object]:
    """Return one grouped checklist item."""
    failed_keys = [key for key in check_keys if not bool(checks.get(key, False))]
    blocking_reason_codes = [
        blocker_code_for_check(key)
        for key in failed_keys
        if blocker_code_for_check(key)
    ]
    related_artifacts = artifact_ids_for_group(group_id)
    command_hints = command_hints_for_group(
        group_id=group_id,
        run_id=run_id,
    )
    return {
        "check_id": f"{profile_name}:{group_id}" if profile_name else group_id,
        "profile_name": profile_name,
        "group_id": group_id,
        "label": label,
        "status": "failed" if failed_keys else "passed",
        "required": True,
        "passed_check_count": len(check_keys) - len(failed_keys),
        "total_check_count": len(check_keys),
        "failed_checks": failed_keys,
        "blocking_reason_codes": blocking_reason_codes,
        "related_artifacts": related_artifacts,
        "command_hints": command_hints,
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


def build_unlock_navigation(
    *,
    run_dir: Path,
    repo_root: Path,
    checklist: dict[str, object],
    codex_preflight: dict[str, Any],
    items: list[dict[str, Any]],
) -> dict[str, object]:
    """Return read-only artifact and command navigation for unlock blockers."""
    failed_items = [item for item in items if item.get("status") == "failed"]
    missing_preflight = not codex_preflight
    blocking_items = [
        navigation_blocking_item(item=item, run_dir=run_dir, repo_root=repo_root)
        for item in failed_items
    ]
    if missing_preflight:
        blocking_items.insert(
            0,
            {
                "check_id": "codex_cli_execution_preflight",
                "profile_name": "",
                "label": "Codex CLI execution preflight",
                "status": "failed",
                "blocking_reason_codes": ["codex_cli_execution_preflight_missing"],
                "failed_checks": ["codex_cli_execution_preflight_exists"],
                "related_artifacts": [
                    artifact_navigation_record(
                        artifact_id="codex_cli_execution_preflight",
                        run_dir=run_dir,
                        repo_root=repo_root,
                    )
                ],
                "command_hints": command_hints_for_group(
                    group_id="codex_cli_execution_preflight",
                    run_id=run_dir.name,
                    run_arg=display_path(run_dir, repo_root),
                ),
                "next_step": (
                    "write codex_cli_execution_preflight.json before reviewing "
                    "real Codex unlock evidence"
                ),
            },
        )
    commands = unique_command_hints(
        [
            command
            for item in blocking_items
            for command in list_of_dicts(item.get("command_hints", []))
        ]
    )
    expected_artifacts = [
        artifact_navigation_record(
            artifact_id=artifact_id,
            run_dir=run_dir,
            repo_root=repo_root,
        )
        for artifact_id in (
            "codex_cli_readiness_pipeline",
            "codex_cli_execution_candidate",
            "codex_cli_real_execution_dry_run",
            "codex_cli_operator_unlock_request",
            "codex_cli_execution_preflight",
        )
    ]
    return {
        "schema_version": "operator_unlock_navigation_v1",
        "status": str(checklist.get("status", "missing_preflight")),
        "ready": bool(checklist.get("ready", False)),
        "blocking_count": len(blocking_items),
        "primary_blocker": (
            str(blocking_items[0].get("check_id", "")) if blocking_items else ""
        ),
        "expected_artifacts": expected_artifacts,
        "blocking_items": blocking_items,
        "commands": commands,
        "policy": {
            "navigation_only": True,
            "commands_are_hints_only": True,
            "requires_explicit_operator_invocation": True,
            "does_not_execute_commands": True,
            "does_not_execute_codex_cli": True,
            "does_not_create_workspace": True,
            "does_not_apply_patches": True,
            "does_not_route_agents": True,
            "does_not_change_acceptance": True,
        },
    }


def navigation_blocking_item(
    *,
    item: dict[str, Any],
    run_dir: Path,
    repo_root: Path,
) -> dict[str, object]:
    """Return one human-actionable blocker row from a failed checklist item."""
    related_artifact_ids = string_rows(item.get("related_artifacts", []))
    return {
        "check_id": str(item.get("check_id", "")),
        "profile_name": str(item.get("profile_name", "")),
        "label": str(item.get("label", "")),
        "status": str(item.get("status", "")),
        "blocking_reason_codes": string_rows(item.get("blocking_reason_codes", [])),
        "failed_checks": string_rows(item.get("failed_checks", [])),
        "related_artifacts": [
            artifact_navigation_record(
                artifact_id=artifact_id,
                run_dir=run_dir,
                repo_root=repo_root,
            )
            for artifact_id in related_artifact_ids
        ],
        "command_hints": command_hints_for_group(
            group_id=str(item.get("group_id", "")),
            run_id=run_dir.name,
            run_arg=display_path(run_dir, repo_root),
        ),
        "next_step": str(item.get("next_step", "")),
    }


def artifact_navigation_record(
    *,
    artifact_id: str,
    run_dir: Path,
    repo_root: Path,
) -> dict[str, object]:
    """Return file and command metadata for one expected unlock artifact."""
    spec = artifact_spec(artifact_id)
    json_path = run_dir / str(spec.get("json_filename", ""))
    markdown_filename = str(spec.get("markdown_filename", ""))
    markdown_path = run_dir / markdown_filename if markdown_filename else None
    return {
        "artifact_id": artifact_id,
        "label": str(spec.get("label", "")),
        "purpose": str(spec.get("purpose", "")),
        "required_for_real_codex_unlock": True,
        "json_path": display_path(json_path, repo_root),
        "json_file": file_record(json_path, repo_root),
        "markdown_path": (
            display_path(markdown_path, repo_root) if markdown_path is not None else ""
        ),
        "markdown_file": (
            file_record(markdown_path, repo_root)
            if markdown_path is not None
            else {"exists": False, "path": "", "sha256": "", "byte_count": 0}
        ),
        "write_command_label": str(spec.get("command_label", "")),
        "write_command": command_for_artifact(
            artifact_id=artifact_id,
            run_arg=display_path(run_dir, repo_root),
        ),
    }


def artifact_spec(artifact_id: str) -> dict[str, str]:
    """Return static metadata for one unlock evidence artifact."""
    specs = {
        "codex_cli_readiness_pipeline": {
            "label": "Codex CLI readiness pipeline",
            "json_filename": "codex_cli_readiness_pipeline.json",
            "markdown_filename": "codex_cli_readiness_pipeline.md",
            "purpose": "aggregate read-only readiness evidence before operator request",
            "command_label": "run_readiness_pipeline",
        },
        "codex_cli_execution_candidate": {
            "label": "Codex CLI execution candidate",
            "json_filename": "codex_cli_execution_candidate.json",
            "markdown_filename": "codex_cli_execution_candidate.md",
            "purpose": "freeze the reviewed command, workspace, and mutation boundary",
            "command_label": "write_execution_candidate",
        },
        "codex_cli_real_execution_dry_run": {
            "label": "Codex CLI real execution dry run",
            "json_filename": "codex_cli_real_execution_dry_run.json",
            "markdown_filename": "codex_cli_real_execution_dry_run.md",
            "purpose": "dry-run the final real-execution boundary without executing Codex",
            "command_label": "write_real_execution_dry_run",
        },
        "codex_cli_operator_unlock_request": {
            "label": "Codex CLI operator unlock request",
            "json_filename": "codex_cli_operator_unlock_request.json",
            "markdown_filename": "codex_cli_operator_unlock_request.md",
            "purpose": "record explicit operator intent for future real Codex review",
            "command_label": "write_operator_unlock_request",
        },
        "codex_cli_execution_preflight": {
            "label": "Codex CLI execution preflight",
            "json_filename": "codex_cli_execution_preflight.json",
            "markdown_filename": "codex_cli_execution_preflight.md",
            "purpose": "startup gate that blocks real Codex without ready request",
            "command_label": "run_execution_preflight",
        },
    }
    return specs.get(
        artifact_id,
        {
            "label": artifact_id,
            "json_filename": "",
            "markdown_filename": "",
            "purpose": "",
            "command_label": "",
        },
    )


def command_for_artifact(*, artifact_id: str, run_arg: str) -> str:
    """Return the explicit operator command that can write one artifact."""
    commands = {
        "codex_cli_readiness_pipeline": (
            "python -m orchestrator.codex_cli_readiness_pipeline "
            f"{run_arg} --config config/codex_cli_enable_candidate.json "
            "--canary-run-dir experiments/canary-demo --approved "
            f'--approved-by <operator> --confirmation-phrase "{MANUAL_APPROVAL_PHRASE}"'
        ),
        "codex_cli_execution_candidate": (
            f"python -m orchestrator.codex_cli_execution_candidate {run_arg}"
        ),
        "codex_cli_real_execution_dry_run": (
            f"python -m orchestrator.codex_cli_real_execution_dry_run {run_arg}"
        ),
        "codex_cli_operator_unlock_request": (
            "python -m orchestrator.codex_cli_operator_unlock_request "
            f"{run_arg} --requested --requested-by <operator> "
            f'--confirmation-phrase "{OPERATOR_REQUEST_PHRASE}"'
        ),
        "codex_cli_execution_preflight": (
            "python -m orchestrator.codex_cli_execution_preflight "
            f"{run_arg} --config config/codex_cli_enable_candidate.json"
        ),
    }
    return commands.get(artifact_id, "")


def command_hints_for_group(
    *,
    group_id: str,
    run_id: str,
    run_arg: str | None = None,
) -> list[dict[str, object]]:
    """Return explicit command hints for a failed unlock evidence group."""
    if run_arg is None:
        run_arg = f"experiments/{run_id}" if run_id else "experiments/<run_id>"
    artifact_ids = (
        ["codex_cli_execution_preflight"]
        if group_id == "codex_cli_execution_preflight"
        else artifact_ids_for_group(group_id)
    )
    return [
        {
            "label": str(artifact_spec(artifact_id).get("command_label", "")),
            "artifact_id": artifact_id,
            "command": command_for_artifact(
                artifact_id=artifact_id,
                run_arg=run_arg,
            ),
            "writes_artifacts": True,
            "executes_codex_cli": False,
            "requires_explicit_operator_invocation": True,
        }
        for artifact_id in artifact_ids
    ]


def unique_command_hints(commands: list[dict[str, Any]]) -> list[dict[str, object]]:
    """Deduplicate command hints while preserving first-seen order."""
    seen: set[str] = set()
    unique: list[dict[str, object]] = []
    for command in commands:
        label = str(command.get("label", ""))
        if label in seen:
            continue
        seen.add(label)
        unique.append(command)
    return unique


def artifact_ids_for_group(group_id: str) -> list[str]:
    """Return expected evidence artifact ids for one checklist group."""
    return list(GROUP_ARTIFACTS.get(group_id, []))


def blocker_code_for_check(check_key: str) -> str:
    """Return stable blocker code for one failed preflight check."""
    return CHECK_TO_BLOCKER_CODE.get(check_key, "")


def display_path(path: Path, repo_root: Path) -> str:
    """Return a stable repository-relative path when possible."""
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


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
    navigation = object_field(payload, "navigation")
    intake = object_field(payload, "codex_intake_readiness")
    blocking_items = list_of_dicts(navigation.get("blocking_items", []))
    expected_artifacts = list_of_dicts(navigation.get("expected_artifacts", []))
    commands = list_of_dicts(navigation.get("commands", []))
    lines.extend(
        [
            "",
            "## Codex Intake Readiness",
            "",
            f"- Status: `{intake.get('status', '')}`",
            f"- Ready: `{intake.get('ready', False)}`",
            f"- Source: `{intake.get('source', '')}`",
            f"- Bound slots: `{intake.get('bound_slot_count', 0)}/{intake.get('slot_count', 0)}`",
            f"- Blockers: `{intake.get('blocking_reason_count', 0)}`",
            f"- Next step: {intake.get('next_step', '')}",
        ]
    )
    lines.extend(
        [
            "",
            "## Blocking Navigation",
            "",
            f"- Blocking items: `{navigation.get('blocking_count', 0)}`",
            f"- Primary blocker: `{navigation.get('primary_blocker', '')}`",
            "",
            "| Blocker | Reasons | Related Artifacts | Next Step |",
            "| --- | --- | --- | --- |",
        ]
    )
    if not blocking_items:
        lines.append("| none | none | none | no unlock blocker is active |")
    for blocker in blocking_items:
        artifact_ids = [
            str(row.get("artifact_id", ""))
            for row in list_of_dicts(blocker.get("related_artifacts", []))
        ]
        lines.append(
            "| "
            f"{blocker.get('label', '')} | "
            f"{', '.join(string_rows(blocker.get('blocking_reason_codes', [])))} | "
            f"{', '.join(artifact_ids)} | "
            f"{blocker.get('next_step', '')} |"
        )
    lines.extend(
        [
            "",
            "## Evidence Artifacts",
            "",
            "| Artifact | Exists | Path | Command |",
            "| --- | --- | --- | --- |",
        ]
    )
    for artifact in expected_artifacts:
        json_file = object_field(artifact, "json_file")
        lines.append(
            "| "
            f"{artifact.get('artifact_id', '')} | "
            f"`{json_file.get('exists', False)}` | "
            f"`{artifact.get('json_path', '')}` | "
            f"`{artifact.get('write_command_label', '')}` |"
        )
    lines.extend(
        [
            "",
            "## Command Hints",
            "",
        ]
    )
    if not commands:
        lines.append("- none")
    for command in commands:
        lines.append(
            f"- `{command.get('label', '')}`: `{command.get('command', '')}`"
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
    schema_errors = tuple(
        validate_json_file(payload_path=payload_path, schema_path=repo_root / SCHEMA_PATH)
    )
    if schema_errors:
        return schema_errors
    return schema_errors + validate_operator_unlock_checklist_consistency(
        load_json_object(payload_path)
    )


def validate_operator_unlock_checklist_payload(
    payload: dict[str, object],
    *,
    run_dir: Path | None = None,
    repo_root: Path = Path("."),
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an in-memory operator unlock checklist payload."""
    repo_root = repo_root.resolve()
    comparable_payload = strip_terminal_metadata(payload)
    schema = load_json_object(repo_root / SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=comparable_payload,
            schema=schema,
            schema_dir=(repo_root / SCHEMA_PATH).parent,
        )
    )
    errors.extend(validate_operator_unlock_checklist_consistency(comparable_payload))
    if require_current_evidence:
        if run_dir is None:
            errors.append("operator_unlock_checklist run_dir required")
        else:
            expected = build_operator_unlock_checklist(
                run_dir=resolve_path(run_dir, repo_root),
                repo_root=repo_root,
            )
            if comparable_payload != expected:
                errors.append("operator_unlock_checklist current evidence mismatch")
    return tuple(errors)


def strip_terminal_metadata(payload: dict[str, object]) -> dict[str, object]:
    """Return payload without terminal-only annotation fields."""
    stripped = dict(payload)
    stripped.pop("from_artifact", None)
    return stripped


def validate_operator_unlock_checklist_consistency(
    payload: dict[str, object],
) -> tuple[str, ...]:
    """Validate derived operator unlock checklist fields against the payload."""
    errors: list[str] = []
    status = str(payload.get("status", ""))
    ready = bool(payload.get("ready", False))
    items = list_of_dicts(payload.get("items", []))
    passed_items = [item for item in items if item.get("status") == "passed"]
    failed_items = [item for item in items if item.get("status") == "failed"]

    if int(payload.get("item_count", -1)) != len(items):
        errors.append("operator_unlock_checklist item_count mismatch")
    if int(payload.get("passed_count", -1)) != len(passed_items):
        errors.append("operator_unlock_checklist passed_count mismatch")
    if int(payload.get("failed_count", -1)) != len(failed_items):
        errors.append("operator_unlock_checklist failed_count mismatch")
    if status == "ready" and ready is not True:
        errors.append("operator_unlock_checklist ready status mismatch")
    if status in {"missing_preflight", "not_requested", "blocked"} and ready:
        errors.append("operator_unlock_checklist blocked ready mismatch")
    if status == "canary_exempt" and ready is not True:
        errors.append("operator_unlock_checklist canary ready mismatch")

    for item in items:
        errors.extend(validate_unlock_item_consistency(item))
    errors.extend(
        validate_unlock_navigation_consistency(
            payload=payload,
            items=items,
        )
    )
    intake_readiness = object_field(payload, "codex_intake_readiness")
    if not intake_readiness:
        errors.append("operator_unlock_checklist intake readiness missing")
    else:
        errors.extend(validate_codex_cli_intake_readiness(intake_readiness))
    return tuple(errors)


def validate_unlock_item_consistency(item: dict[str, Any]) -> tuple[str, ...]:
    """Validate one grouped unlock checklist item."""
    errors: list[str] = []
    status = str(item.get("status", ""))
    failed_checks = string_rows(item.get("failed_checks", []))
    total_count = int(item.get("total_check_count", 0) or 0)
    passed_count = int(item.get("passed_check_count", 0) or 0)
    if passed_count + len(failed_checks) != total_count:
        errors.append("operator_unlock_checklist item check count mismatch")
    if status == "passed" and failed_checks:
        errors.append("operator_unlock_checklist passed item has failures")
    if status == "failed" and not failed_checks:
        errors.append("operator_unlock_checklist failed item lacks failures")
    expected_blockers = [
        blocker_code_for_check(check)
        for check in failed_checks
        if blocker_code_for_check(check)
    ]
    if string_rows(item.get("blocking_reason_codes", [])) != expected_blockers:
        errors.append("operator_unlock_checklist item blocker codes mismatch")
    expected_artifacts = artifact_ids_for_group(str(item.get("group_id", "")))
    if string_rows(item.get("related_artifacts", [])) != expected_artifacts:
        errors.append("operator_unlock_checklist item related artifacts mismatch")

    command_hints = list_of_dicts(item.get("command_hints", []))
    expected_hint_ids = expected_artifacts
    hint_ids = [str(command.get("artifact_id", "")) for command in command_hints]
    if hint_ids != expected_hint_ids:
        errors.append("operator_unlock_checklist item command hints mismatch")
    for command in command_hints:
        if command.get("executes_codex_cli") is not False:
            errors.append("operator_unlock_checklist item command executes codex")
        if command.get("requires_explicit_operator_invocation") is not True:
            errors.append("operator_unlock_checklist item command lacks explicit gate")
    return tuple(errors)


def validate_unlock_navigation_consistency(
    *,
    payload: dict[str, object],
    items: list[dict[str, Any]],
) -> tuple[str, ...]:
    """Validate unlock navigation rows summarize checklist blockers."""
    errors: list[str] = []
    navigation = object_field(payload, "navigation")
    blocking_items = list_of_dicts(navigation.get("blocking_items", []))
    failed_items = [item for item in items if item.get("status") == "failed"]
    expected_blocking_count = len(failed_items)
    if str(payload.get("status", "")) == "missing_preflight":
        expected_blocking_count += 1

    if str(navigation.get("status", "")) != str(payload.get("status", "")):
        errors.append("operator_unlock_checklist navigation status mismatch")
    if bool(navigation.get("ready", False)) != bool(payload.get("ready", False)):
        errors.append("operator_unlock_checklist navigation ready mismatch")
    if int(navigation.get("blocking_count", -1)) != expected_blocking_count:
        errors.append("operator_unlock_checklist blocking_count mismatch")

    expected_primary = (
        str(blocking_items[0].get("check_id", "")) if blocking_items else ""
    )
    if str(navigation.get("primary_blocker", "")) != expected_primary:
        errors.append("operator_unlock_checklist primary blocker mismatch")

    expected_artifact_ids = [
        "codex_cli_readiness_pipeline",
        "codex_cli_execution_candidate",
        "codex_cli_real_execution_dry_run",
        "codex_cli_operator_unlock_request",
        "codex_cli_execution_preflight",
    ]
    artifact_ids = [
        str(row.get("artifact_id", ""))
        for row in list_of_dicts(navigation.get("expected_artifacts", []))
    ]
    if artifact_ids != expected_artifact_ids:
        errors.append("operator_unlock_checklist expected artifacts mismatch")

    expected_blocker_ids = [str(item.get("check_id", "")) for item in failed_items]
    if str(payload.get("status", "")) == "missing_preflight":
        expected_blocker_ids = ["codex_cli_execution_preflight", *expected_blocker_ids]
    blocker_ids = [str(row.get("check_id", "")) for row in blocking_items]
    if blocker_ids != expected_blocker_ids:
        errors.append("operator_unlock_checklist blocking item ids mismatch")

    failed_by_id = {str(item.get("check_id", "")): item for item in failed_items}
    for row in blocking_items:
        check_id = str(row.get("check_id", ""))
        if check_id == "codex_cli_execution_preflight":
            continue
        source_item = failed_by_id.get(check_id)
        if source_item is None:
            errors.append("operator_unlock_checklist blocking item missing source")
            continue
        if string_rows(row.get("blocking_reason_codes", [])) != string_rows(
            source_item.get("blocking_reason_codes", [])
        ):
            errors.append("operator_unlock_checklist blocking reason mismatch")
        if string_rows(row.get("failed_checks", [])) != string_rows(
            source_item.get("failed_checks", [])
        ):
            errors.append("operator_unlock_checklist blocking failed checks mismatch")

    expected_command_labels = unique_command_labels(blocking_items)
    command_labels = [
        str(command.get("label", ""))
        for command in list_of_dicts(navigation.get("commands", []))
    ]
    if command_labels != expected_command_labels:
        errors.append("operator_unlock_checklist navigation commands mismatch")
    return tuple(errors)


def unique_command_labels(blocking_items: list[dict[str, Any]]) -> list[str]:
    """Return deduplicated command labels from blocking item command hints."""
    labels: list[str] = []
    seen: set[str] = set()
    for item in blocking_items:
        for command in list_of_dicts(item.get("command_hints", [])):
            label = str(command.get("label", ""))
            if label and label not in seen:
                labels.append(label)
                seen.add(label)
    return labels


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
