"""Proposal schema for strategy modification agents."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any


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
    direction_tag: str = ""
    hypotheses: tuple[str, ...] = ()
    patch_sha256: str = ""
    is_repeat_patch: bool = False
    repeat_of_round: str = ""
    quality_checks: dict[str, Any] | None = None
    rejection_reason: str = ""
    prompt: str = ""
    command: tuple[str, ...] = ()
    workspace_path: str = ""

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly proposal payload."""
        return asdict(self)


def annotate_proposal_quality(
    *,
    proposal: StrategyProposal,
    run_dir: Path,
    current_round_id: str,
) -> StrategyProposal:
    """Attach deterministic quality metadata to a proposal."""
    patch_sha256 = sha256_text(proposal.patch_diff) if proposal.patch_diff else ""
    repeat_of_round = find_repeat_patch_round(
        run_dir=run_dir,
        current_round_id=current_round_id,
        patch_sha256=patch_sha256,
    )
    quality_checks = {
        "has_patch": bool(proposal.patch_diff),
        "has_hypotheses": bool(proposal.hypotheses),
        "has_expected_metric_change": bool(proposal.expected_metric_change),
        "has_risk_notes": bool(proposal.risk_notes.strip()),
        "repeat_patch": bool(repeat_of_round),
    }
    return replace(
        proposal,
        patch_sha256=patch_sha256,
        is_repeat_patch=bool(repeat_of_round),
        repeat_of_round=repeat_of_round,
        quality_checks=quality_checks,
    )


def find_repeat_patch_round(
    *,
    run_dir: Path,
    current_round_id: str,
    patch_sha256: str,
) -> str:
    """Return the first prior round with the same patch hash, if any."""
    if not patch_sha256:
        return ""
    for proposal_path in sorted(run_dir.glob("round_*/proposal.json")):
        if proposal_path.parent.name >= current_round_id:
            continue
        try:
            payload = json.loads(proposal_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        if payload.get("patch_sha256") == patch_sha256:
            return proposal_path.parent.name
    return ""


def sha256_text(value: str) -> str:
    """Return the SHA-256 digest for text content."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
