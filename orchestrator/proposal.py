"""Proposal schema for strategy modification agents."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StrategyProposal:
    """Structured output from a strategy modification agent."""

    agent_name: str
    round_index: int
    target_file: str
    summary: str
    risk_notes: str
    expected_metric_change: dict[str, str]
    raw_response: str
    patch_diff: str
    applicable: bool
    rejection_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly proposal payload."""
        return asdict(self)
