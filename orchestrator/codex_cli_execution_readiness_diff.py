"""Read-only drift audit for real Codex CLI execution readiness evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agents.codex_dry_run_adapter import build_codex_command
from orchestrator.codex_cli_dry_invocation_guard import (
    file_record,
    load_json_object,
    object_value,
    relative_path,
    resolve_path,
    string_list,
    write_json,
)
from orchestrator.codex_cli_execution_preflight import (
    EXPECTED_AGENT_NAME,
    EXPECTED_ATTEMPT_ID,
    EXPECTED_PROFILE_NAME,
    EXPECTED_ROUND_ID,
    TARGET_FILE,
    real_execution_workspace_path,
    stable_digest,
    workspace_prefix,
)
from orchestrator.schema_validation import validate_json_file


CODEX_CLI_EXECUTION_READINESS_DIFF_SCHEMA_VERSION = (
    "codex_cli_execution_readiness_diff_v1"
)
SCHEMA_PATH = Path("schemas/codex_cli_execution_readiness_diff.schema.json")


def write_codex_cli_execution_readiness_diff(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
    config_path: Path = Path("config/codex_cli_enable_candidate.json"),
    config_payload: dict[str, Any] | None = None,
) -> tuple[Path, Path, dict[str, object]]:
    """Write JSON and markdown read-only execution readiness diff artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_codex_cli_execution_readiness_diff(
        run_dir=run_dir,
        repo_root=repo_root,
        config_path=config_path,
        config_payload=config_payload,
    )
    json_path = run_dir / "codex_cli_execution_readiness_diff.json"
    md_path = run_dir / "codex_cli_execution_readiness_diff.md"
    write_json(json_path, payload)
    md_path.write_text(
        render_codex_cli_execution_readiness_diff_markdown(payload),
        encoding="utf-8",
    )
    errors = validate_codex_cli_execution_readiness_diff_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(
            "Codex CLI execution readiness diff failed schema validation: "
            + "; ".join(errors)
        )
    return json_path, md_path, payload


def build_codex_cli_execution_readiness_diff(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
    config_path: Path = Path("config/codex_cli_enable_candidate.json"),
    config_payload: dict[str, Any] | None = None,
) -> dict[str, object]:
    """Return a deterministic read-only drift audit for real Codex execution."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    config_path = resolve_path(config_path, repo_root)
    config = config_payload if config_payload is not None else load_json_object(config_path)
    preflight = load_json_object(run_dir / "codex_cli_execution_preflight.json")
    candidate = load_json_object(run_dir / "codex_cli_execution_candidate.json")
    dry_run = load_json_object(run_dir / "codex_cli_real_execution_dry_run.json")
    operator_request = load_json_object(
        run_dir / "codex_cli_operator_unlock_request.json"
    )
    current_expected = current_expected_execution(
        config=config,
        config_path=config_path,
        run_dir=run_dir,
        repo_root=repo_root,
        config_object_provided=config_payload is not None,
    )
    reviewed = object_value(operator_request.get("planned_execution_review", {}))
    dry_plan = object_value(dry_run.get("planned_execution", {}))
    candidate_plan = object_value(candidate.get("execution_plan", {}))
    preflight_expected = selected_preflight_expected_execution(preflight)
    comparisons = readiness_comparisons(
        current=current_expected,
        reviewed=reviewed,
        dry_plan=dry_plan,
        candidate_plan=candidate_plan,
        preflight_expected=preflight_expected,
        operator_request=operator_request,
        run_dir=run_dir,
        repo_root=repo_root,
    )
    source_artifacts = source_artifact_records(
        run_dir=run_dir,
        repo_root=repo_root,
        config_path=config_path,
    )
    summary = readiness_diff_summary(
        comparisons=comparisons,
        source_artifacts=source_artifacts,
        preflight=preflight,
        operator_request=operator_request,
    )
    status = readiness_diff_status(summary)
    return {
        "schema_version": CODEX_CLI_EXECUTION_READINESS_DIFF_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "status": status,
        "ready": status == "ready",
        "summary": summary,
        "source_artifacts": source_artifacts,
        "current_expected_execution": current_expected,
        "reviewed_execution": reviewed_execution_record(reviewed),
        "candidate_execution": compact_execution_plan(candidate_plan),
        "dry_run_execution": compact_execution_plan(dry_plan),
        "preflight_expected_execution": compact_execution_plan(preflight_expected),
        "comparisons": comparisons,
        "blocking_reasons": blocking_reasons(summary=summary, comparisons=comparisons),
        "policy": {
            "inspection_only": True,
            "read_only": True,
            "diff_only": True,
            "does_not_execute_commands": True,
            "does_not_execute_codex_cli": True,
            "does_not_record_operator_approval": True,
            "does_not_create_workspace": True,
            "does_not_send_strategy_prompt": True,
            "does_not_modify_config": True,
            "does_not_apply_patches": True,
            "does_not_route_agents": True,
            "does_not_change_acceptance": True,
            "startup_preflight_keeps_execution_authority": True,
        },
    }


def current_expected_execution(
    *,
    config: dict[str, Any],
    config_path: Path,
    run_dir: Path,
    repo_root: Path,
    config_object_provided: bool = False,
) -> dict[str, object]:
    """Return the current execution boundary derived from config."""
    codex_cli = object_value(config.get("codex_cli", {}))
    executable = str(codex_cli.get("executable", "codex"))
    model = str(codex_cli.get("model", "default"))
    sandbox = str(codex_cli.get("sandbox", "workspace-write"))
    workspace_root = str(codex_cli.get("workspace_root", "workspaces"))
    command = build_codex_command(
        executable=executable,
        model=model,
        sandbox=sandbox,
        target_file=TARGET_FILE,
    )
    workspace_path = real_execution_workspace_path(
        workspace_root=workspace_root,
        run_id=run_dir.name,
    )
    return {
        "source_config": file_record(config_path, repo_root),
        "config_object_provided": config_object_provided,
        "agent_name": EXPECTED_AGENT_NAME,
        "profile_name": EXPECTED_PROFILE_NAME,
        "round_id": EXPECTED_ROUND_ID,
        "attempt_id": EXPECTED_ATTEMPT_ID,
        "target_file": TARGET_FILE,
        "allowed_mutation_paths": [TARGET_FILE],
        "workspace_root": workspace_root,
        "workspace_prefix": workspace_prefix(
            workspace_root=workspace_root,
            run_id=run_dir.name,
        ),
        "workspace_path": workspace_path,
        "command": command,
        "command_sha256": stable_digest(command),
        "execute": bool(codex_cli.get("execute", False)),
        "sandbox": sandbox,
        "timeout_seconds": int_value(codex_cli.get("timeout_seconds", 0)),
    }


def selected_preflight_expected_execution(preflight: dict[str, Any]) -> dict[str, Any]:
    """Return the first real-Codex profile expected execution from preflight."""
    for profile in list_value(preflight.get("profiles", [])):
        if bool(profile.get("requires_operator_unlock", False)):
            return object_value(profile.get("expected_execution", {}))
    return {}


def source_artifact_records(
    *,
    run_dir: Path,
    repo_root: Path,
    config_path: Path,
) -> dict[str, object]:
    """Return source artifacts used by the readiness diff."""
    artifacts = {
        "candidate_config": config_path,
        "codex_cli_execution_preflight": run_dir
        / "codex_cli_execution_preflight.json",
        "codex_cli_readiness_pipeline": run_dir / "codex_cli_readiness_pipeline.json",
        "codex_cli_execution_candidate": run_dir
        / "codex_cli_execution_candidate.json",
        "codex_cli_real_execution_dry_run": run_dir
        / "codex_cli_real_execution_dry_run.json",
        "codex_cli_operator_unlock_request": run_dir
        / "codex_cli_operator_unlock_request.json",
        "codex_cli_unlock_runbook": run_dir / "codex_cli_unlock_runbook.json",
    }
    required = {
        "candidate_config",
        "codex_cli_execution_preflight",
        "codex_cli_execution_candidate",
        "codex_cli_real_execution_dry_run",
        "codex_cli_operator_unlock_request",
    }
    return {
        artifact_id: {
            "artifact_id": artifact_id,
            "required_for_ready_diff": artifact_id in required,
            "file": file_record(path, repo_root),
        }
        for artifact_id, path in artifacts.items()
    }


def readiness_comparisons(
    *,
    current: dict[str, object],
    reviewed: dict[str, Any],
    dry_plan: dict[str, Any],
    candidate_plan: dict[str, Any],
    preflight_expected: dict[str, Any],
    operator_request: dict[str, Any],
    run_dir: Path,
    repo_root: Path,
) -> list[dict[str, object]]:
    """Return stable comparison rows for reviewed versus current execution state."""
    rows = [
        comparison_row(
            comparison_id="current_command_matches_review",
            label="Current config command matches operator-reviewed command",
            left_name="current_config",
            right_name="operator_request",
            left=current.get("command", []),
            right=reviewed.get("command", []),
        ),
        comparison_row(
            comparison_id="current_command_digest_matches_review",
            label="Current config command digest matches operator review",
            left_name="current_config",
            right_name="operator_request",
            left=current.get("command_sha256", ""),
            right=reviewed.get("command_sha256", ""),
        ),
        comparison_row(
            comparison_id="current_workspace_matches_review",
            label="Current workspace path matches operator review",
            left_name="current_config",
            right_name="operator_request",
            left=current.get("workspace_path", ""),
            right=reviewed.get("workspace_path", ""),
        ),
        comparison_row(
            comparison_id="current_target_matches_review",
            label="Current target file matches operator review",
            left_name="current_config",
            right_name="operator_request",
            left=current.get("target_file", ""),
            right=reviewed.get("target_file", ""),
        ),
        comparison_row(
            comparison_id="current_allowed_mutations_match_review",
            label="Current allowed mutation paths match operator review",
            left_name="current_config",
            right_name="operator_request",
            left=current.get("allowed_mutation_paths", []),
            right=reviewed.get("allowed_mutation_paths", []),
        ),
        comparison_row(
            comparison_id="current_execution_identity_matches_review",
            label="Current execution identity matches operator review",
            left_name="current_config",
            right_name="operator_request",
            left=execution_identity(current),
            right=execution_identity(reviewed),
        ),
        comparison_row(
            comparison_id="preflight_expected_matches_current",
            label="Startup preflight expected execution matches current config",
            left_name="codex_cli_execution_preflight",
            right_name="current_config",
            left=execution_boundary(preflight_expected),
            right=execution_boundary(current),
        ),
        comparison_row(
            comparison_id="candidate_plan_matches_dry_run_plan",
            label="Execution candidate plan matches real-execution dry-run plan",
            left_name="codex_cli_execution_candidate",
            right_name="codex_cli_real_execution_dry_run",
            left=execution_boundary(candidate_plan),
            right=execution_boundary(dry_plan),
        ),
        comparison_row(
            comparison_id="dry_run_plan_matches_operator_review",
            label="Real-execution dry-run plan matches operator review",
            left_name="codex_cli_real_execution_dry_run",
            right_name="operator_request",
            left=execution_boundary(dry_plan),
            right=execution_boundary(reviewed),
        ),
    ]
    rows.extend(
        source_hash_comparisons(
            operator_request=operator_request,
            run_dir=run_dir,
            repo_root=repo_root,
        )
    )
    return rows


def source_hash_comparisons(
    *,
    operator_request: dict[str, Any],
    run_dir: Path,
    repo_root: Path,
) -> list[dict[str, object]]:
    """Return comparisons for operator-reviewed source evidence hashes."""
    sources = (
        (
            "operator_request_pipeline_hash_matches_current",
            "Operator-reviewed readiness pipeline hash matches current file",
            "source_pipeline",
            run_dir / "codex_cli_readiness_pipeline.json",
        ),
        (
            "operator_request_dry_run_hash_matches_current",
            "Operator-reviewed dry-run hash matches current file",
            "source_real_execution_dry_run",
            run_dir / "codex_cli_real_execution_dry_run.json",
        ),
    )
    rows: list[dict[str, object]] = []
    for comparison_id, label, source_key, expected_path in sources:
        source = object_value(operator_request.get(source_key, {}))
        source_file = object_value(source.get("file", {}))
        current_file = file_record(expected_path, repo_root)
        reviewed_record = (
            {
                "path": source_file.get("path", ""),
                "sha256": source_file.get("sha256", ""),
            }
            if source_file.get("sha256", "")
            else {}
        )
        current_record = (
            {
                "path": relative_path(expected_path, repo_root),
                "sha256": current_file.get("sha256", ""),
            }
            if current_file.get("exists") is True
            else {}
        )
        rows.append(
            comparison_row(
                comparison_id=comparison_id,
                label=label,
                left_name=source_key,
                right_name="current_file",
                left=reviewed_record,
                right=current_record,
            )
        )
    return rows


def comparison_row(
    *,
    comparison_id: str,
    label: str,
    left_name: str,
    right_name: str,
    left: object,
    right: object,
) -> dict[str, object]:
    """Return one deterministic comparison row."""
    left_missing = value_missing(left)
    right_missing = value_missing(right)
    status = (
        "missing"
        if left_missing or right_missing
        else "matched"
        if left == right
        else "drift"
    )
    return {
        "comparison_id": comparison_id,
        "label": label,
        "status": status,
        "left_name": left_name,
        "right_name": right_name,
        "left_sha256": value_digest(left),
        "right_sha256": value_digest(right),
        "left_value": compact_value(left),
        "right_value": compact_value(right),
        "missing_sides": [
            name
            for name, missing in (
                (left_name, left_missing),
                (right_name, right_missing),
            )
            if missing
        ],
    }


def readiness_diff_summary(
    *,
    comparisons: list[dict[str, object]],
    source_artifacts: dict[str, object],
    preflight: dict[str, Any],
    operator_request: dict[str, Any],
) -> dict[str, object]:
    """Return compact diff summary counts."""
    comparison_statuses = [str(row.get("status", "")) for row in comparisons]
    missing_artifacts = [
        artifact_id
        for artifact_id, artifact in source_artifacts.items()
        if isinstance(artifact, dict)
        and bool(artifact.get("required_for_ready_diff", False))
        and not bool(object_value(artifact.get("file", {})).get("exists", False))
    ]
    drift_ids = [
        str(row.get("comparison_id", ""))
        for row in comparisons
        if row.get("status") == "drift"
    ]
    missing_comparison_ids = [
        str(row.get("comparison_id", ""))
        for row in comparisons
        if row.get("status") == "missing"
    ]
    return {
        "comparison_count": len(comparisons),
        "matched_count": comparison_statuses.count("matched"),
        "drift_count": comparison_statuses.count("drift"),
        "missing_comparison_count": comparison_statuses.count("missing"),
        "missing_artifact_count": len(missing_artifacts),
        "missing_artifacts": missing_artifacts,
        "drift_comparisons": drift_ids,
        "missing_comparisons": missing_comparison_ids,
        "preflight_ok": bool(preflight.get("ok", False)),
        "operator_request_ready": bool(
            operator_request.get("operator_request_ready", False)
        ),
    }


def readiness_diff_status(summary: dict[str, object]) -> str:
    """Return top-level status for the execution readiness diff."""
    if int(summary.get("missing_artifact_count", 0)) or int(
        summary.get("missing_comparison_count", 0)
    ):
        return "missing_evidence"
    if int(summary.get("drift_count", 0)):
        return "drift_detected"
    if bool(summary.get("preflight_ok", False)) and bool(
        summary.get("operator_request_ready", False)
    ):
        return "ready"
    return "blocked"


def blocking_reasons(
    *,
    summary: dict[str, object],
    comparisons: list[dict[str, object]],
) -> list[str]:
    """Return stable blocking reason codes for the diff report."""
    reasons: list[str] = []
    reasons.extend(
        f"missing_artifact:{artifact_id}"
        for artifact_id in string_list(summary.get("missing_artifacts", []))
    )
    for comparison in comparisons:
        status = str(comparison.get("status", ""))
        if status in {"missing", "drift"}:
            reasons.append(
                f"{status}:{str(comparison.get('comparison_id', 'unknown'))}"
            )
    if (
        not reasons
        and not bool(summary.get("preflight_ok", False))
    ):
        reasons.append("preflight_not_ok")
    if (
        not reasons
        and not bool(summary.get("operator_request_ready", False))
    ):
        reasons.append("operator_request_not_ready")
    return reasons


def compact_execution_plan(plan: dict[str, Any]) -> dict[str, object]:
    """Return the execution plan fields relevant to drift detection."""
    return {
        "agent_name": str(plan.get("agent_name", "")),
        "profile_name": str(plan.get("profile_name", "")),
        "round_id": str(plan.get("round_id", "")),
        "attempt_id": str(plan.get("attempt_id", "")),
        "target_file": str(plan.get("target_file", "")),
        "allowed_mutation_paths": string_list(plan.get("allowed_mutation_paths", [])),
        "workspace_path": str(plan.get("workspace_path", "")),
        "command": string_list(plan.get("command", [])),
    }


def reviewed_execution_record(reviewed: dict[str, Any]) -> dict[str, object]:
    """Return compact operator-reviewed execution details."""
    record = compact_execution_plan(reviewed)
    record["command_sha256"] = str(reviewed.get("command_sha256", ""))
    record["execution_enabled_by_this_artifact"] = bool(
        reviewed.get("execution_enabled_by_this_artifact", False)
    )
    return record


def execution_identity(plan: dict[str, Any] | dict[str, object]) -> dict[str, str]:
    """Return identity fields from an execution plan-like object."""
    return {
        "agent_name": str(plan.get("agent_name", "")),
        "profile_name": str(plan.get("profile_name", "")),
        "round_id": str(plan.get("round_id", "")),
        "attempt_id": str(plan.get("attempt_id", "")),
    }


def execution_boundary(plan: dict[str, Any] | dict[str, object]) -> dict[str, object]:
    """Return boundary fields from an execution plan-like object."""
    return {
        **execution_identity(plan),
        "target_file": str(plan.get("target_file", "")),
        "allowed_mutation_paths": string_list(plan.get("allowed_mutation_paths", [])),
        "workspace_path": str(plan.get("workspace_path", "")),
        "command": string_list(plan.get("command", [])),
    }


def compact_value(value: object) -> object:
    """Return JSON-safe comparison values."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [compact_value(row) for row in value]
    if isinstance(value, dict):
        return {str(key): compact_value(row) for key, row in sorted(value.items())}
    return str(value)


def value_missing(value: object) -> bool:
    """Return whether a comparison value is effectively absent."""
    if value is None:
        return True
    if value == "":
        return True
    if value == []:
        return True
    if value == {}:
        return True
    if isinstance(value, list):
        return all(value_missing(row) for row in value)
    if isinstance(value, dict):
        return all(value_missing(row) for row in value.values())
    return False


def value_digest(value: object) -> str:
    """Return a deterministic digest for one comparison value."""
    if value_missing(value):
        return ""
    return stable_digest(compact_value(value))


def list_value(value: object) -> list[dict[str, Any]]:
    """Return a list of dictionaries from arbitrary input."""
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def int_value(value: object) -> int:
    """Return an integer value or zero."""
    return value if isinstance(value, int) else 0


def render_codex_cli_execution_readiness_diff_markdown(
    payload: dict[str, object],
) -> str:
    """Render the execution readiness diff as markdown."""
    summary = object_value(payload.get("summary", {}))
    comparisons = [
        row for row in payload.get("comparisons", []) if isinstance(row, dict)
    ]
    lines = [
        "# Codex CLI Execution Readiness Diff",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- Ready: `{payload.get('ready', False)}`",
        f"- Matched: `{summary.get('matched_count', 0)}`",
        f"- Drift: `{summary.get('drift_count', 0)}`",
        f"- Missing: `{summary.get('missing_comparison_count', 0)}`",
        "",
        "| Comparison | Status | Left | Right |",
        "| --- | --- | --- | --- |",
    ]
    for comparison in comparisons:
        lines.append(
            "| "
            f"{comparison.get('label', '')} | "
            f"`{comparison.get('status', '')}` | "
            f"`{comparison.get('left_name', '')}` | "
            f"`{comparison.get('right_name', '')}` |"
        )
    blockers = string_list(payload.get("blocking_reasons", []))
    lines.extend(["", "## Blocking Reasons", ""])
    lines.extend(f"- {reason}" for reason in blockers)
    if not blockers:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This report is read-only and does not execute commands or Codex.",
            "- Startup preflight remains the authority for blocking real Codex execution.",
            "- It does not create workspaces, apply patches, route agents, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_codex_cli_execution_readiness_diff_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved Codex CLI execution readiness diff artifact."""
    return tuple(
        validate_json_file(
            payload_path=payload_path,
            schema_path=repo_root / SCHEMA_PATH,
        )
    )


def main() -> None:
    """CLI entrypoint for Codex CLI execution readiness diff generation."""
    parser = argparse.ArgumentParser(
        description="Write a read-only Codex CLI execution readiness drift audit."
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/codex_cli_enable_candidate.json"),
    )
    args = parser.parse_args()
    _, _, payload = write_codex_cli_execution_readiness_diff(
        run_dir=args.run_dir,
        repo_root=args.repo_root,
        config_path=args.config,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
