"""Stable JSON I/O fixtures for strategy modifier agents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
) -> dict[str, object]:
    """Return the deterministic input contract for modifier agents."""
    return {
        "schema_version": AGENT_INPUT_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "round_index": round_index,
        "target_file": relative_path(target_file, repo_root),
        "round_dir": relative_path(round_dir, repo_root),
        "artifacts": {
            "agent_context_markdown": relative_path(context_path, repo_root),
            "agent_context_json": relative_path(context_path.with_suffix(".json"), repo_root),
            "train_report_before": relative_path(train_report_path, repo_root),
            "validation_report_before": relative_path(validation_report_path, repo_root),
            "holdout_report_before": relative_path(holdout_report_path, repo_root),
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
        "modifiers": {
            "primary": primary_modifier,
            "fallbacks": list(fallback_modifiers),
        },
        "output_contract": {
            "schema_version": AGENT_OUTPUT_SCHEMA_VERSION,
            "proposal_protocol_version": "proposal_v1",
            "expected_output_path": relative_path(round_dir / "agent_output.json", repo_root),
            "required_artifacts": [
                "proposal.json",
                "proposal_attempts.json",
                "agent_response.txt",
                "patch.diff",
            ],
        },
    }


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
    return {
        "schema_version": AGENT_OUTPUT_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "round_index": round_index,
        "selected_role": selected_role,
        "selection_reason": str(selected_attempt.get("selection_reason", "")),
        "selected_proposal": proposal.to_dict(),
        "attempt_count": len(proposal_attempts),
        "attempts": compact_attempts(proposal_attempts),
        "artifacts": {
            "agent_input": relative_path(round_dir / "agent_input.json", repo_root),
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
                "agent_name": attempt.get("agent_name", ""),
                "direction_tag": attempt.get("direction_tag", ""),
                "status": attempt.get("status", ""),
                "selected": bool(attempt.get("selected", False)),
                "candidate_score": attempt.get("candidate_score", 0),
                "patch_sha256": attempt.get("patch_sha256", ""),
                "selection_reason": attempt.get("selection_reason", ""),
            }
        )
    return rows


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write deterministic JSON."""
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
