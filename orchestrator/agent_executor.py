"""Deterministic candidate-agent execution queue."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.modifier_adapter import StrategyModifier
from orchestrator.agent_attempts import attempt_trace_id
from orchestrator.proposal import StrategyProposal


AGENT_EXECUTOR_SCHEMA_VERSION = "agent_executor_v1"


@dataclass(frozen=True)
class AgentCandidate:
    """One modifier candidate scheduled for a strategy-improvement attempt."""

    role: str
    attempt_index: int
    attempt_id: str
    modifier_name: str
    profile_name: str
    adapter_name: str
    modifier: StrategyModifier


@dataclass(frozen=True)
class AgentCandidateResult:
    """Structured result from one candidate-agent execution."""

    role: str
    attempt_index: int
    attempt_id: str
    modifier_name: str
    profile_name: str
    adapter_name: str
    proposal: StrategyProposal


def build_agent_queue(
    *,
    primary_modifier: StrategyModifier,
    fallback_modifiers: tuple[StrategyModifier, ...],
    executor_config: dict[str, object] | None = None,
    primary_profile: dict[str, object] | None = None,
    fallback_profiles: tuple[dict[str, object], ...] = (),
) -> tuple[AgentCandidate, ...]:
    """Return a stable primary-plus-fallback execution queue."""
    modifiers = [("primary", primary_modifier, primary_profile or {})]
    modifiers.extend(
        (
            f"fallback_{index:02d}",
            fallback_modifier,
            fallback_profiles[index - 1] if index <= len(fallback_profiles) else {},
        )
        for index, fallback_modifier in enumerate(fallback_modifiers, start=1)
    )
    queue = tuple(
        AgentCandidate(
            role=role,
            attempt_index=index,
            attempt_id=attempt_trace_id(index=index, role=role),
            modifier_name=modifier_name(modifier),
            profile_name=profile_name(profile, role),
            adapter_name=profile_adapter_name(profile, modifier),
            modifier=modifier,
        )
        for index, (role, modifier, profile) in enumerate(modifiers, start=1)
    )
    max_candidates = int((executor_config or {}).get("max_candidates", 0))
    return queue[:max_candidates] if max_candidates > 0 else queue


def execute_agent_queue(
    *,
    queue: tuple[AgentCandidate, ...],
    report_path: Path,
    target_file: Path,
    round_index: int,
    repo_root: Path,
    old_threshold: str,
    new_threshold: str,
    context_path: Path,
) -> tuple[AgentCandidateResult, ...]:
    """Execute candidate modifiers in queue order and return their proposals."""
    results: list[AgentCandidateResult] = []
    for candidate in queue:
        proposal = candidate.modifier.propose_strategy_change(
            report_path=report_path,
            target_file=target_file,
            round_index=round_index,
            repo_root=repo_root,
            old_threshold=old_threshold,
            new_threshold=new_threshold,
            context_path=context_path,
            attempt_id=candidate.attempt_id,
        )
        results.append(
            AgentCandidateResult(
                role=candidate.role,
                attempt_index=candidate.attempt_index,
                attempt_id=candidate.attempt_id,
                modifier_name=candidate.modifier_name,
                profile_name=candidate.profile_name,
                adapter_name=candidate.adapter_name,
                proposal=proposal,
            )
        )
    return tuple(results)


def write_agent_executor_report(
    *,
    output_path: Path,
    repo_root: Path,
    round_dir: Path,
    run_id: str,
    round_id: str,
    attempts: list[dict[str, object]],
    executor_config: dict[str, object],
) -> Path:
    """Write a deterministic report for agent queue execution and outcomes."""
    payload = agent_executor_report_payload(
        repo_root=repo_root,
        round_dir=round_dir,
        run_id=run_id,
        round_id=round_id,
        attempts=attempts,
        executor_config=executor_config,
    )
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def agent_executor_report_payload(
    *,
    repo_root: Path,
    round_dir: Path,
    run_id: str,
    round_id: str,
    attempts: list[dict[str, object]],
    executor_config: dict[str, object],
) -> dict[str, object]:
    """Return a JSON-friendly executor report payload."""
    selected_attempt_id = ""
    rows: list[dict[str, object]] = []
    for index, attempt in enumerate(attempts, start=1):
        if bool(attempt.get("selected", False)):
            selected_attempt_id = str(attempt.get("attempt_id", ""))
        rows.append(
            executor_attempt_row(
                attempt=attempt,
                attempt_index=index,
                repo_root=repo_root,
                round_dir=round_dir,
            )
        )
    return {
        "schema_version": AGENT_EXECUTOR_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "attempt_count": len(attempts),
        "selected_attempt_id": selected_attempt_id,
        "execution_policy": executor_policy_payload(executor_config),
        "attempts": rows,
    }


def executor_policy_payload(executor_config: dict[str, object]) -> dict[str, object]:
    """Return the normalized executor policy stored in audit artifacts."""
    return {
        "mode": str(executor_config.get("mode", "sequential")),
        "queue_order": ["primary", "fallbacks_by_config_order"],
        "attempt_id_source": "orchestrator.agent_attempts.attempt_trace_id",
        "acceptance": "deterministic policy gate after backtest",
        "max_candidates": int(executor_config.get("max_candidates", 0)),
        "per_agent_timeout_seconds": int(
            executor_config.get("per_agent_timeout_seconds", 120)
        ),
        "allow_disabled_adapters": bool(
            executor_config.get("allow_disabled_adapters", True)
        ),
    }


def executor_attempt_row(
    *,
    attempt: dict[str, object],
    attempt_index: int,
    repo_root: Path,
    round_dir: Path,
) -> dict[str, object]:
    """Return compact executor metadata for one attempt."""
    proposal = proposal_payload(attempt)
    attempt_id = str(attempt.get("attempt_id", ""))
    return {
        "attempt_id": attempt_id,
        "attempt_index": int(attempt.get("attempt_index", attempt_index)),
        "role": str(attempt.get("role", "")),
        "modifier_name": str(
            attempt.get("modifier_name", attempt.get("agent_name", ""))
        ),
        "profile_name": str(attempt.get("profile_name", "")),
        "adapter_name": str(attempt.get("adapter_name", "")),
        "agent_name": str(attempt.get("agent_name", "")),
        "direction_tag": str(attempt.get("direction_tag", "")),
        "status": str(attempt.get("status", "")),
        "selected": bool(attempt.get("selected", False)),
        "candidate_score": attempt.get("candidate_score", 0),
        "failure_stage": str(attempt.get("failure_stage", "none")),
        "failure_code": str(attempt.get("failure_code", "none")),
        "validation_status": str(attempt.get("validation_status", "")),
        "proposal": {
            "applicable": bool(proposal.get("applicable", False)),
            "patch_sha256": str(proposal.get("patch_sha256", "")),
            "workspace_path": str(proposal.get("workspace_path", "")),
            "command": list_or_empty(proposal.get("command", [])),
            "prompt_chars": len(str(proposal.get("prompt", ""))),
            "raw_response_chars": len(str(proposal.get("raw_response", ""))),
            "contract_errors": list_or_empty(proposal.get("contract_errors", [])),
        },
        "artifacts": {
            "attempt_dir": relative_path(
                round_dir / "agent_attempts" / attempt_id,
                repo_root,
            ) if attempt_id else "",
            "workspace_manifest": optional_relative_path(
                round_dir / "workspace_manifests" / f"{attempt_id}.json",
                repo_root,
            ) if attempt_id else "",
            "agent_execution": optional_relative_path(
                round_dir / "agent_executions" / f"{attempt_id}.json",
                repo_root,
            ) if attempt_id else "",
        },
    }


def proposal_payload(attempt: dict[str, object]) -> dict[str, Any]:
    """Return the proposal dict nested in an attempt record."""
    proposal = attempt.get("proposal", {})
    return proposal if isinstance(proposal, dict) else {}


def list_or_empty(value: object) -> list[object]:
    """Return JSON-list metadata without leaking tuple types."""
    return list(value) if isinstance(value, list | tuple) else []


def optional_relative_path(path: Path, root: Path) -> str:
    """Return a relative path only when an optional artifact exists."""
    return relative_path(path, root) if path.exists() else ""


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def modifier_name(modifier: StrategyModifier) -> str:
    """Return stable modifier name metadata for agent I/O fixtures."""
    return str(getattr(modifier, "agent_name", modifier.__class__.__name__))


def profile_name(profile: dict[str, object], role: str) -> str:
    """Return configured profile name, falling back to the queue role."""
    return str(profile.get("name", role))


def profile_adapter_name(profile: dict[str, object], modifier: StrategyModifier) -> str:
    """Return configured adapter name, falling back to modifier metadata."""
    return str(profile.get("adapter", modifier_name(modifier)))
