"""Round-level readiness report for future agent roles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


AGENT_ROLE_READINESS_SCHEMA_VERSION = "agent_role_readiness_v1"


def write_agent_role_readiness(
    *,
    output_path: Path,
    markdown_path: Path,
    repo_root: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    round_dir: Path,
    agent_role_contracts_path: Path,
) -> Path:
    """Write a deterministic readiness audit for configured agent roles."""
    payload = agent_role_readiness_payload(
        repo_root=repo_root,
        run_id=run_id,
        round_id=round_id,
        round_index=round_index,
        round_dir=round_dir,
        agent_role_contracts_path=agent_role_contracts_path,
    )
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(agent_role_readiness_markdown(payload), encoding="utf-8")
    return output_path


def agent_role_readiness_payload(
    *,
    repo_root: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    round_dir: Path,
    agent_role_contracts_path: Path,
) -> dict[str, object]:
    """Return the JSON payload for the role readiness audit."""
    contracts = load_json_object(agent_role_contracts_path)
    roles = [
        role_readiness(
            role=role,
            repo_root=repo_root,
            round_dir=round_dir,
        )
        for role in contracts.get("roles", [])
        if isinstance(role, dict)
    ]
    return {
        "schema_version": AGENT_ROLE_READINESS_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "round_index": round_index,
        "round_dir": relative_path(round_dir, repo_root),
        "agent_role_contracts": relative_path(agent_role_contracts_path, repo_root),
        "roles": roles,
        "readiness_summary": readiness_summary(roles),
        "policy": {
            "only_strategy_modifier_executes_in_v0_5": True,
            "deterministic_gates_keep_acceptance_authority": True,
            "readiness_report_can_change_acceptance": False,
            "readiness_report_can_change_routing": False,
        },
    }


def role_readiness(
    *,
    role: dict[str, Any],
    repo_root: Path,
    round_dir: Path,
) -> dict[str, object]:
    """Return one role's deterministic readiness row."""
    role_name = str(role.get("role_name", ""))
    enabled = bool(role.get("enabled", False))
    implemented = bool(role.get("implemented", False))
    execution_mode = str(role.get("execution_mode", ""))
    executable_now = (
        role_name == "strategy_modifier"
        and enabled
        and implemented
        and execution_mode == "active"
    )
    consumed = artifact_records(
        artifact_paths=consumed_artifact_paths(role_name, role, round_dir),
        repo_root=repo_root,
    )
    produced = artifact_records(
        artifact_paths=produced_artifact_paths(role_name, role, round_dir),
        repo_root=repo_root,
    )
    return {
        "role_name": role_name,
        "stage": str(role.get("stage", "")),
        "enabled": enabled,
        "execution_mode": execution_mode,
        "implemented": implemented,
        "required": bool(role.get("required", False)),
        "declared_decision_authority": str(role.get("decision_authority", "")),
        "executable_now": executable_now,
        "activation_blockers": activation_blockers(
            role_name=role_name,
            enabled=enabled,
            implemented=implemented,
            execution_mode=execution_mode,
        ),
        "consumed_artifacts": consumed,
        "produced_artifacts": produced,
        "integrity_checks": {
            "consumed_artifacts_exist": all(
                bool(artifact["exists"]) for artifact in consumed
            ),
            "produced_artifacts_exist": all(
                bool(artifact["exists"]) for artifact in produced
            ),
        },
        "authority": {
            "can_change_acceptance": False,
            "can_change_routing": False,
            "can_veto": False,
        },
    }


def activation_blockers(
    *,
    role_name: str,
    enabled: bool,
    implemented: bool,
    execution_mode: str,
) -> list[str]:
    """Return deterministic blockers for roles that cannot execute yet."""
    if role_name == "strategy_modifier" and enabled and implemented and execution_mode == "active":
        return []
    blockers: list[str] = []
    if not enabled:
        blockers.append("role_disabled")
    if not implemented:
        blockers.append("role_not_implemented")
    if execution_mode == "stub_contract":
        blockers.append("stub_contract_not_executable")
    elif execution_mode != "active":
        blockers.append("execution_mode_not_active")
    if role_name != "strategy_modifier":
        blockers.append("v0_5_executes_strategy_modifier_only")
    return blockers


def consumed_artifact_paths(
    role_name: str,
    role: dict[str, Any],
    round_dir: Path,
) -> dict[str, Path]:
    """Return the files a role is expected to consume in this round."""
    known: dict[str, dict[str, Path]] = {
        "strategy_modifier": {
            "agent_input": round_dir / "agent_input.json",
            "agent_context": round_dir / "agent_context.json",
            "proposal_intent": round_dir / "proposal_intent.json",
            "agent_role_contracts": round_dir / "agent_role_contracts.json",
            "analysis_notes": round_dir / "analysis_notes.json",
            "visual_review": round_dir / "visual_review.json",
            "target_strategy": Path("strategies/current_strategy.py"),
        },
        "analysis": {
            "agent_role_contracts": round_dir / "agent_role_contracts.json",
            "proposal_intent": round_dir / "proposal_intent.json",
            "train_metrics_before": round_dir / "train_metrics_before.json",
            "validation_metrics_before": round_dir / "metrics_before.json",
            "holdout_metrics_before": round_dir / "holdout_metrics_before.json",
            "train_report_before": round_dir / "train_report_before.md",
            "validation_report_before": round_dir / "report_before.md",
            "holdout_report_before": round_dir / "holdout_report_before.md",
        },
        "visual_review": {
            "analysis_notes": round_dir / "analysis_notes.json",
            "visual_artifacts_manifest": round_dir / "visual_artifacts_manifest.json",
            "chart_html": round_dir / "chart.html",
            "trade_timeline_html": round_dir / "trade_timeline.html",
            "train_trades_before": round_dir / "train_trades_before.csv",
            "validation_trades_before": round_dir / "trades_before.csv",
            "holdout_trades_before": round_dir / "holdout_trades_before.csv",
        },
        "overfit_validator": {
            "agent_role_contracts": round_dir / "agent_role_contracts.json",
            "analysis_notes": round_dir / "analysis_notes.json",
            "proposal": round_dir / "proposal.json",
            "decision": round_dir / "decision.json",
            "train_metrics_before": round_dir / "train_metrics_before.json",
            "train_metrics_after": round_dir / "train_metrics_after.json",
            "validation_metrics_before": round_dir / "metrics_before.json",
            "validation_metrics_after": round_dir / "metrics_after.json",
            "holdout_metrics_before": round_dir / "holdout_metrics_before.json",
            "holdout_metrics_after": round_dir / "holdout_metrics_after.json",
        },
    }
    if role_name in known:
        return known[role_name]
    return inferred_artifact_paths(role.get("consumes", []), round_dir)


def produced_artifact_paths(
    role_name: str,
    role: dict[str, Any],
    round_dir: Path,
) -> dict[str, Path]:
    """Return the files a role is expected to produce in this round."""
    known: dict[str, dict[str, Path]] = {
        "strategy_modifier": {
            "proposal": round_dir / "proposal.json",
            "patch": round_dir / "patch.diff",
            "raw_agent_output": round_dir / "raw_agent_output.txt",
            "agent_output": round_dir / "agent_output.json",
            "agent_validation": round_dir / "agent_validation.json",
        },
        "analysis": {
            "analysis_notes_json": round_dir / "analysis_notes.json",
            "analysis_notes_markdown": round_dir / "analysis_notes.md",
        },
        "visual_review": {
            "visual_review_json": round_dir / "visual_review.json",
            "visual_review_markdown": round_dir / "visual_review.md",
        },
        "overfit_validator": {
            "overfit_validation_json": round_dir / "overfit_validation.json",
            "overfit_validation_markdown": round_dir / "overfit_validation.md",
        },
    }
    if role_name in known:
        return known[role_name]
    return inferred_artifact_paths(role.get("produces", []), round_dir)


def inferred_artifact_paths(value: object, round_dir: Path) -> dict[str, Path]:
    """Return best-effort artifact paths for custom roles."""
    if not isinstance(value, list | tuple):
        return {}
    paths: dict[str, Path] = {}
    for item in value:
        filename = str(item)
        if not filename:
            continue
        paths[filename] = round_dir / filename
    return paths


def artifact_records(
    *,
    artifact_paths: dict[str, Path],
    repo_root: Path,
) -> list[dict[str, object]]:
    """Return stable artifact records with existence and schema metadata."""
    records: list[dict[str, object]] = []
    for name, path in sorted(artifact_paths.items()):
        resolved = resolve_path(path, repo_root)
        records.append(
            {
                "name": name,
                "path": relative_path(resolved, repo_root),
                "exists": resolved.exists() and resolved.is_file(),
                "schema_version": schema_version(resolved),
            }
        )
    return records


def readiness_summary(roles: list[dict[str, object]]) -> dict[str, object]:
    """Return compact readiness counts and role sets."""
    return {
        "role_count": len(roles),
        "executable_roles": [
            str(role["role_name"])
            for role in roles
            if bool(role.get("executable_now", False))
        ],
        "implemented_roles": [
            str(role["role_name"])
            for role in roles
            if bool(role.get("implemented", False))
        ],
        "stub_roles": [
            str(role["role_name"])
            for role in roles
            if str(role.get("execution_mode", "")) == "stub_contract"
        ],
        "blocked_roles": [
            str(role["role_name"])
            for role in roles
            if not bool(role.get("executable_now", False))
        ],
        "all_produced_artifacts_present": all(
            bool(role.get("integrity_checks", {}).get("produced_artifacts_exist", False))
            for role in roles
            if isinstance(role.get("integrity_checks", {}), dict)
        ),
        "stub_roles_have_no_execution_authority": all(
            not any(bool(value) for value in authority_values(role))
            for role in roles
            if str(role.get("execution_mode", "")) == "stub_contract"
        ),
    }


def authority_values(role: dict[str, object]) -> list[object]:
    """Return the authority boolean values for one role."""
    authority = role.get("authority", {})
    if not isinstance(authority, dict):
        return [True]
    return [
        authority.get("can_change_acceptance", True),
        authority.get("can_change_routing", True),
        authority.get("can_veto", True),
    ]


def agent_role_readiness_markdown(payload: dict[str, object]) -> str:
    """Return a human-readable render of the readiness audit."""
    role_lines = []
    for role in payload.get("roles", []):
        if not isinstance(role, dict):
            continue
        blockers = role.get("activation_blockers", [])
        blocker_text = ", ".join(str(item) for item in blockers) if blockers else "none"
        role_lines.append(
            "| {role} | {mode} | {implemented} | {executable} | {blockers} |".format(
                role=role.get("role_name", ""),
                mode=role.get("execution_mode", ""),
                implemented=role.get("implemented", False),
                executable=role.get("executable_now", False),
                blockers=blocker_text,
            )
        )
    return "\n".join(
        [
            "# Agent Role Readiness",
            "",
            f"Run: {payload['run_id']}",
            f"Round: {payload['round_id']}",
            "",
            "| Role | Mode | Implemented | Executable now | Blockers |",
            "| --- | --- | --- | --- | --- |",
            *role_lines,
            "",
            "Final acceptance remains controlled by deterministic gates.",
            "",
        ]
    )


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk, returning an empty dict on parse failure."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def schema_version(path: Path) -> str:
    """Return a JSON artifact schema version when available."""
    if path.suffix != ".json":
        return ""
    payload = load_json_object(path)
    return str(payload.get("schema_version", ""))


def resolve_path(path: Path, root: Path) -> Path:
    """Resolve path relative to the repository root when needed."""
    return path if path.is_absolute() else root / path


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
