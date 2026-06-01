"""Stable JSON I/O fixtures for strategy modifier agents."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from orchestrator.agent_roles import compact_agent_roles as compact_agent_role_contracts
from orchestrator.proposal import StrategyProposal


AGENT_INPUT_SCHEMA_VERSION = "agent_io_input_v1"
AGENT_OUTPUT_SCHEMA_VERSION = "agent_io_output_v1"


def write_agent_input(
    *,
    output_path: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    repo_root: Path,
    round_dir: Path,
    target_file: Path,
    context_path: Path,
    intent_path: Path,
    train_report_path: Path,
    validation_report_path: Path,
    holdout_report_path: Path,
    train_metrics_before: dict[str, float | int],
    validation_metrics_before: dict[str, float | int],
    holdout_metrics_before: dict[str, float | int],
    policy_rules: dict[str, float | int] | None,
    holdout_policy_rules: dict[str, float | int | bool] | None,
    candidate_selection: dict[str, float | int],
    primary_modifier: str,
    fallback_modifiers: tuple[str, ...],
    agent_profiles: tuple[dict[str, object], ...] = (),
    agent_roles: tuple[dict[str, object], ...] = (),
) -> Path:
    """Write the deterministic input contract for modifier agents."""
    payload = build_agent_input_payload(
        run_id=run_id,
        round_id=round_id,
        round_index=round_index,
        repo_root=repo_root,
        round_dir=round_dir,
        target_file=target_file,
        context_path=context_path,
        intent_path=intent_path,
        train_report_path=train_report_path,
        validation_report_path=validation_report_path,
        holdout_report_path=holdout_report_path,
        train_metrics_before=train_metrics_before,
        validation_metrics_before=validation_metrics_before,
        holdout_metrics_before=holdout_metrics_before,
        policy_rules=policy_rules,
        holdout_policy_rules=holdout_policy_rules,
        candidate_selection=candidate_selection,
        primary_modifier=primary_modifier,
        fallback_modifiers=fallback_modifiers,
        agent_profiles=agent_profiles,
        agent_roles=agent_roles,
    )
    write_json(output_path, payload)
    return output_path


def build_agent_input_payload(
    *,
    run_id: str,
    round_id: str,
    round_index: int,
    repo_root: Path,
    round_dir: Path,
    target_file: Path,
    context_path: Path,
    intent_path: Path,
    train_report_path: Path,
    validation_report_path: Path,
    holdout_report_path: Path,
    train_metrics_before: dict[str, float | int],
    validation_metrics_before: dict[str, float | int],
    holdout_metrics_before: dict[str, float | int],
    policy_rules: dict[str, float | int] | None,
    holdout_policy_rules: dict[str, float | int | bool] | None,
    candidate_selection: dict[str, float | int],
    primary_modifier: str,
    fallback_modifiers: tuple[str, ...],
    agent_profiles: tuple[dict[str, object], ...] = (),
    agent_roles: tuple[dict[str, object], ...] = (),
) -> dict[str, object]:
    """Return the deterministic input contract for modifier agents."""
    return {
        "schema_version": AGENT_INPUT_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "round_index": round_index,
        "target_file": relative_path(target_file, repo_root),
        "target_file_content": target_file.read_text(encoding="utf-8"),
        "target_file_sha256": file_sha256(target_file),
        "round_dir": relative_path(round_dir, repo_root),
        "input_bundle_dir": relative_path(
            round_dir / "agent_input_bundle",
            repo_root,
        ),
        "output_bundle_dir": relative_path(
            round_dir / "agent_output_bundle",
            repo_root,
        ),
        "artifacts": {
            "agent_role_contracts": relative_path(
                round_dir / "agent_role_contracts.json",
                repo_root,
            ),
            "analysis_notes_json": relative_path(
                round_dir / "analysis_notes.json",
                repo_root,
            ),
            "analysis_notes_markdown": relative_path(
                round_dir / "analysis_notes.md",
                repo_root,
            ),
            "visual_review_json": relative_path(
                round_dir / "visual_review.json",
                repo_root,
            ),
            "visual_review_markdown": relative_path(
                round_dir / "visual_review.md",
                repo_root,
            ),
            "chart_html": relative_path(round_dir / "chart.html", repo_root),
            "trade_timeline_html": relative_path(
                round_dir / "trade_timeline.html",
                repo_root,
            ),
            "agent_context_markdown": relative_path(context_path, repo_root),
            "agent_context_json": relative_path(context_path.with_suffix(".json"), repo_root),
            "proposal_intent_json": relative_path(intent_path, repo_root),
            "proposal_intent_markdown": relative_path(intent_path.with_suffix(".md"), repo_root),
            "train_report_before": relative_path(train_report_path, repo_root),
            "validation_report_before": relative_path(validation_report_path, repo_root),
            "holdout_report_before": relative_path(holdout_report_path, repo_root),
            "champion_registry": optional_relative_path(
                round_dir.parent.parent / "champion.json",
                repo_root,
            ),
            "previous_champion_comparison": optional_relative_path(
                round_dir.parent / "champion_comparison.json",
                repo_root,
            ),
        },
        "metrics_before": {
            "train": train_metrics_before,
            "validation": validation_metrics_before,
            "holdout": holdout_metrics_before,
        },
        "policy": {
            "validation": policy_rules or {},
            "holdout": holdout_policy_rules or {},
        },
        "candidate_selection": candidate_selection,
        "agent_roles": compact_agent_role_contracts(agent_roles),
        "agent_profiles": compact_agent_profiles(agent_profiles),
        "active_agent": active_agent_template(),
        "modifiers": {
            "primary": primary_modifier,
            "fallbacks": list(fallback_modifiers),
        },
        "output_contract": {
            "schema_version": AGENT_OUTPUT_SCHEMA_VERSION,
            "proposal_protocol_version": "proposal_v1",
            "expected_output_path": relative_path(round_dir / "agent_output.json", repo_root),
            "expected_raw_output_path": relative_path(
                round_dir / "raw_agent_output.txt",
                repo_root,
            ),
            "allowed_output_paths": [
                relative_path(round_dir / "agent_output.json", repo_root),
                relative_path(round_dir / "raw_agent_output.txt", repo_root),
                relative_path(round_dir / "agent_output_bundle", repo_root),
            ],
            "workspace_output_path": "",
            "expected_command_output_filename": "",
            "required_artifacts": [
                "agent_bundle_manifest.json",
                "proposal.json",
                "proposal_attempts.json",
                "raw_agent_output.txt",
                "agent_response.txt",
                "patch.diff",
            ],
        },
    }


def compact_agent_profiles(
    agent_profiles: tuple[dict[str, object], ...],
) -> list[dict[str, object]]:
    """Return stable profile metadata safe for external agent input."""
    return [
        {
            "profile_name": str(profile.get("name", "")),
            "adapter_name": str(profile.get("adapter", "")),
            "role": str(profile.get("role", "")),
            "agent_role": str(profile.get("agent_role", "strategy_modifier")),
            "enabled": bool(profile.get("enabled", True)),
            "settings": dict_or_empty(profile.get("settings", {})),
            "runner": dict_or_empty(profile.get("runner", {})),
        }
        for profile in agent_profiles
    ]


def active_agent_template() -> dict[str, object]:
    """Return the round-level active-agent template."""
    return {
        "attempt_id": "",
        "role": "",
        "agent_role": "",
        "profile_name": "",
        "adapter_name": "",
        "agent_name": "",
        "output_filename": "",
    }


def dict_or_empty(value: object) -> dict[str, object]:
    """Return a string-keyed dict for JSON agent input metadata."""
    if not isinstance(value, dict):
        return {}
    return {str(key): entry for key, entry in value.items()}


def write_agent_output(
    *,
    output_path: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    repo_root: Path,
    round_dir: Path,
    proposal: StrategyProposal,
    proposal_attempts: list[dict[str, object]],
    selected_attempt: dict[str, object],
) -> Path:
    """Write the deterministic output contract from modifier selection."""
    payload = build_agent_output_payload(
        run_id=run_id,
        round_id=round_id,
        round_index=round_index,
        repo_root=repo_root,
        round_dir=round_dir,
        proposal=proposal,
        proposal_attempts=proposal_attempts,
        selected_attempt=selected_attempt,
    )
    write_json(output_path, payload)
    return output_path


def build_agent_output_payload(
    *,
    run_id: str,
    round_id: str,
    round_index: int,
    repo_root: Path,
    round_dir: Path,
    proposal: StrategyProposal,
    proposal_attempts: list[dict[str, object]],
    selected_attempt: dict[str, object],
) -> dict[str, object]:
    """Return the deterministic output contract from modifier selection."""
    selected_role = str(selected_attempt.get("role", ""))
    selected_agent_role = str(selected_attempt.get("agent_role", ""))
    return {
        "schema_version": AGENT_OUTPUT_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "round_index": round_index,
        "selected_role": selected_role,
        "selected_agent_role": selected_agent_role,
        "selection_reason": str(selected_attempt.get("selection_reason", "")),
        "selected_proposal": proposal.to_dict(),
        "attempt_count": len(proposal_attempts),
        "attempts": compact_attempts(proposal_attempts),
        "artifacts": {
            "agent_input": relative_path(round_dir / "agent_input.json", repo_root),
            "agent_bundle_manifest": relative_path(
                round_dir / "agent_bundle_manifest.json",
                repo_root,
            ),
            "raw_agent_output": relative_path(
                round_dir / "raw_agent_output.txt",
                repo_root,
            ),
            "proposal": relative_path(round_dir / "proposal.json", repo_root),
            "proposal_attempts": relative_path(
                round_dir / "proposal_attempts.json",
                repo_root,
            ),
            "agent_response": relative_path(round_dir / "agent_response.txt", repo_root),
            "patch": relative_path(round_dir / "patch.diff", repo_root),
        },
    }


def compact_attempts(attempts: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return compact, stable attempt metadata for agent output fixtures."""
    rows: list[dict[str, object]] = []
    for attempt in attempts:
        rows.append(
            {
                "role": attempt.get("role", ""),
                "agent_role": attempt.get("agent_role", ""),
                "profile_name": attempt.get("profile_name", ""),
                "adapter_name": attempt.get("adapter_name", ""),
                "runner": dict_or_empty(attempt.get("runner", {})),
                "runner_name": attempt.get("runner_name", ""),
                "agent_name": attempt.get("agent_name", ""),
                "direction_tag": attempt.get("direction_tag", ""),
                "status": attempt.get("status", ""),
                "selected": bool(attempt.get("selected", False)),
                "candidate_score": attempt.get("candidate_score", 0),
                "failure_stage": attempt.get("failure_stage", "none"),
                "failure_code": attempt.get("failure_code", "none"),
                "failure_message": attempt.get("failure_message", ""),
                "reason_codes": attempt.get("reason_codes", []),
                "patch_sha256": attempt.get("patch_sha256", ""),
                "selection_reason": attempt.get("selection_reason", ""),
                "champion_gap": attempt.get("champion_gap", {}),
                "routing_prior": attempt.get("routing_prior", {}),
            }
        )
    return rows


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def optional_relative_path(path: Path, root: Path) -> str:
    """Return a relative path only when the optional artifact exists."""
    return relative_path(path, root) if path.exists() else ""


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write deterministic JSON."""
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    """Return a file SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
