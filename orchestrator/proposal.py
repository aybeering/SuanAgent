"""Proposal schema for strategy modification agents."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from orchestrator.patch_parser import PatchParseError, validate_patch_targets


PROPOSAL_PROTOCOL_VERSION = "proposal_v1"
KNOWN_METRIC_KEYS = {
    "avg_slippage",
    "ev",
    "fill_rate",
    "max_drawdown",
    "total_pnl",
    "trade_count",
}
DIRECTION_TAG_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


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
    protocol_version: str = PROPOSAL_PROTOCOL_VERSION
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
    contract_errors: tuple[str, ...] = ()

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


def validate_proposal_contract(
    *,
    proposal: StrategyProposal,
    expected_target_file: Path,
    expected_round_index: int,
) -> tuple[str, ...]:
    """Return deterministic schema/protocol errors for an agent proposal."""
    errors: list[str] = []
    expected_target = str(expected_target_file)

    if proposal.protocol_version != PROPOSAL_PROTOCOL_VERSION:
        errors.append(
            f"protocol_version must be {PROPOSAL_PROTOCOL_VERSION}, "
            f"got {proposal.protocol_version or 'empty'}"
        )
    if not proposal.agent_name.strip():
        errors.append("agent_name must be non-empty")
    if proposal.round_index != expected_round_index:
        errors.append(
            f"round_index must be {expected_round_index}, got {proposal.round_index}"
        )
    if proposal.target_file != expected_target:
        errors.append(f"target_file must be {expected_target}, got {proposal.target_file}")
    if Path(proposal.target_file).is_absolute() or ".." in Path(proposal.target_file).parts:
        errors.append("target_file must be a relative path inside the repository")
    if not proposal.summary.strip():
        errors.append("summary must be non-empty")
    if not proposal.risk_notes.strip():
        errors.append("risk_notes must be non-empty")
    if not proposal.raw_response.strip():
        errors.append("raw_response must be non-empty")
    if not proposal.direction_tag.strip():
        errors.append("direction_tag must be non-empty")
    elif DIRECTION_TAG_PATTERN.fullmatch(proposal.direction_tag) is None:
        errors.append(
            "direction_tag must match [a-z][a-z0-9_]{1,63}: "
            f"{proposal.direction_tag}"
        )

    errors.extend(validate_expected_metric_change(proposal.expected_metric_change))
    errors.extend(validate_hypotheses(proposal.hypotheses))
    errors.extend(validate_command(proposal.command))

    if proposal.applicable:
        if not proposal.patch_diff.strip():
            errors.append("applicable proposals must include patch_diff")
        else:
            try:
                validate_patch_targets(proposal.patch_diff, expected_target_file)
            except PatchParseError as exc:
                errors.append(f"patch_diff target validation failed: {exc}")
    elif not proposal.rejection_reason.strip():
        errors.append("non-applicable proposals must include rejection_reason")

    return tuple(errors)


def reject_invalid_proposal(
    *,
    proposal: StrategyProposal,
    contract_errors: tuple[str, ...],
) -> StrategyProposal:
    """Return a non-applicable proposal annotated with contract errors."""
    reason = "proposal contract invalid: " + "; ".join(contract_errors)
    rejection_reason = combined_rejection_reason(proposal.rejection_reason, reason)
    return replace(
        proposal,
        applicable=False,
        rejection_reason=rejection_reason,
        contract_errors=contract_errors,
    )


def enforce_proposal_contract(
    *,
    proposal: StrategyProposal,
    expected_target_file: Path,
    expected_round_index: int,
) -> StrategyProposal:
    """Validate and reject a proposal when it violates the protocol."""
    errors = validate_proposal_contract(
        proposal=proposal,
        expected_target_file=expected_target_file,
        expected_round_index=expected_round_index,
    )
    if not errors:
        return proposal
    return reject_invalid_proposal(proposal=proposal, contract_errors=errors)


def validate_expected_metric_change(value: object) -> list[str]:
    """Return protocol errors for expected_metric_change metadata."""
    if not isinstance(value, dict):
        return ["expected_metric_change must be a mapping"]
    errors: list[str] = []
    for key, metric_value in value.items():
        if not isinstance(key, str) or not key:
            errors.append("expected_metric_change keys must be non-empty strings")
            continue
        if key not in KNOWN_METRIC_KEYS:
            errors.append(f"expected_metric_change contains unknown metric: {key}")
        if not isinstance(metric_value, str) or not metric_value.strip():
            errors.append(
                f"expected_metric_change[{key}] must be a non-empty string"
            )
    return errors


def validate_hypotheses(value: object) -> list[str]:
    """Return protocol errors for proposal hypotheses."""
    if not isinstance(value, tuple | list):
        return ["hypotheses must be a tuple or list of strings"]
    errors: list[str] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"hypotheses[{index}] must be a non-empty string")
    return errors


def validate_command(value: object) -> list[str]:
    """Return protocol errors for optional command metadata."""
    if not isinstance(value, tuple | list):
        return ["command must be a tuple or list of strings"]
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str):
            return [f"command[{index}] must be a string"]
    return []


def combined_rejection_reason(*reasons: str) -> str:
    """Return one stable rejection reason from non-empty reason fragments."""
    return "; ".join(reason for reason in reasons if reason)


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
