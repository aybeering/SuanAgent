"""Deterministic candidate-agent execution queue."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agents.modifier_adapter import StrategyModifier
from orchestrator.agent_attempts import attempt_trace_id
from orchestrator.proposal import StrategyProposal


@dataclass(frozen=True)
class AgentCandidate:
    """One modifier candidate scheduled for a strategy-improvement attempt."""

    role: str
    attempt_index: int
    attempt_id: str
    modifier_name: str
    modifier: StrategyModifier


@dataclass(frozen=True)
class AgentCandidateResult:
    """Structured result from one candidate-agent execution."""

    role: str
    attempt_index: int
    attempt_id: str
    modifier_name: str
    proposal: StrategyProposal


def build_agent_queue(
    *,
    primary_modifier: StrategyModifier,
    fallback_modifiers: tuple[StrategyModifier, ...],
) -> tuple[AgentCandidate, ...]:
    """Return a stable primary-plus-fallback execution queue."""
    modifiers = [("primary", primary_modifier)]
    modifiers.extend(
        (f"fallback_{index:02d}", fallback_modifier)
        for index, fallback_modifier in enumerate(fallback_modifiers, start=1)
    )
    return tuple(
        AgentCandidate(
            role=role,
            attempt_index=index,
            attempt_id=attempt_trace_id(index=index, role=role),
            modifier_name=modifier_name(modifier),
            modifier=modifier,
        )
        for index, (role, modifier) in enumerate(modifiers, start=1)
    )


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
                proposal=proposal,
            )
        )
    return tuple(results)


def modifier_name(modifier: StrategyModifier) -> str:
    """Return stable modifier name metadata for agent I/O fixtures."""
    return str(getattr(modifier, "agent_name", modifier.__class__.__name__))
