"""Validate raw strategy-agent output before the loop can apply it."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from orchestrator.git_manager import GitError, check_patch
from orchestrator.patch_parser import (
    PatchParseError,
    extract_json_object,
    extract_unified_diff,
)
from orchestrator.proposal import (
    PROPOSAL_PROTOCOL_VERSION,
    StrategyProposal,
    sha256_text,
    validate_proposal_contract,
)


AGENT_VALIDATION_SCHEMA_VERSION = "agent_validation_v1"
DEFAULT_INTAKE_AGENT_NAME = "agent_output_intake"


def verify_agent_output(
    *,
    agent_input_path: Path,
    agent_output_path: Path,
    repo_root: Path = Path("."),
    output_path: Path | None = None,
    proposal_output_path: Path | None = None,
    agent_name: str = DEFAULT_INTAKE_AGENT_NAME,
    check_git_apply: bool = True,
) -> dict[str, object]:
    """Validate a raw agent output file against the strategy proposal contract."""
    agent_input = load_json_object(agent_input_path)
    raw_output = agent_output_path.read_text(encoding="utf-8")
    proposal = proposal_from_raw_agent_output(
        raw_output=raw_output,
        agent_input=agent_input,
        agent_name=agent_name,
        prompt=str(agent_input_path),
    )
    report = validate_agent_proposal(
        agent_input_path=agent_input_path,
        proposal=proposal,
        repo_root=repo_root,
        agent_output_path=agent_output_path,
        check_git_apply=check_git_apply,
    )
    write_optional_json(output_path, report)
    write_optional_json(proposal_output_path, report["proposal"])
    return report


def validate_agent_proposal(
    *,
    agent_input_path: Path,
    proposal: StrategyProposal,
    repo_root: Path = Path("."),
    agent_output_path: Path | None = None,
    output_path: Path | None = None,
    check_git_apply: bool = True,
) -> dict[str, object]:
    """Validate an already parsed strategy proposal and optionally write a report."""
    agent_input = load_json_object(agent_input_path)
    expected_target = Path(str(agent_input["target_file"]))
    expected_round_index = int(agent_input["round_index"])
    normalized_proposal = proposal_with_patch_hash(proposal)
    contract_errors = validate_proposal_contract(
        proposal=normalized_proposal,
        expected_target_file=expected_target,
        expected_round_index=expected_round_index,
    )
    git_apply_status = "skipped"
    git_apply_error = ""
    if normalized_proposal.applicable and not contract_errors and check_git_apply:
        try:
            check_patch(repo_root.resolve(), normalized_proposal.patch_diff)
            git_apply_status = "passed"
        except GitError as exc:
            git_apply_status = "failed"
            git_apply_error = str(exc)
    elif normalized_proposal.applicable and contract_errors:
        git_apply_status = "skipped_contract_invalid"
    elif normalized_proposal.applicable and not check_git_apply:
        git_apply_status = "skipped_disabled"

    errors = list(contract_errors)
    if git_apply_error:
        errors.append(f"git apply check failed: {git_apply_error}")

    report: dict[str, object] = {
        "schema_version": AGENT_VALIDATION_SCHEMA_VERSION,
        "ok": not errors,
        "errors": errors,
        "warnings": [],
        "agent_input_path": str(agent_input_path),
        "agent_output_path": str(agent_output_path or ""),
        "expected_target_file": str(expected_target),
        "expected_round_index": expected_round_index,
        "proposal_protocol_version": normalized_proposal.protocol_version,
        "proposal_applicable": normalized_proposal.applicable,
        "proposal_target_file": normalized_proposal.target_file,
        "proposal_direction_tag": normalized_proposal.direction_tag,
        "proposal_patch_sha256": normalized_proposal.patch_sha256,
        "checks": {
            "contract_valid": not contract_errors,
            "git_apply_check": git_apply_status,
            "git_apply_error": git_apply_error,
            "strategy_only_patch": not any(
                "patch_diff target validation failed" in error
                for error in contract_errors
            ),
        },
        "proposal": normalized_proposal.to_dict(),
    }
    write_optional_json(output_path, report)
    return report


def proposal_from_raw_agent_output(
    *,
    raw_output: str,
    agent_input: dict[str, Any],
    agent_name: str = DEFAULT_INTAKE_AGENT_NAME,
    prompt: str = "",
    command: tuple[str, ...] = (),
    workspace_path: str = "",
) -> StrategyProposal:
    """Convert raw agent output text into a standard strategy proposal."""
    expected_target = str(agent_input["target_file"])
    expected_round_index = int(agent_input["round_index"])
    metadata = proposal_metadata_from_raw_output(raw_output)
    parse_error = ""
    patch_diff = string_value(metadata.get("patch_diff", ""))
    if patch_diff and not patch_diff.endswith("\n"):
        patch_diff += "\n"
    if not patch_diff:
        try:
            patch_diff = extract_unified_diff(raw_output)
        except PatchParseError as exc:
            parse_error = str(exc)
            patch_diff = ""

    applicable = bool(patch_diff.strip())
    rejection_reason = string_value(metadata.get("rejection_reason", ""))
    if not applicable:
        rejection_reason = rejection_reason or parse_error or "agent output did not include a patch"

    return proposal_with_patch_hash(
        StrategyProposal(
            agent_name=string_value(metadata.get("agent_name", "")) or agent_name,
            round_index=int(metadata.get("round_index", expected_round_index)),
            target_file=string_value(metadata.get("target_file", "")) or expected_target,
            summary=string_value(metadata.get("summary", "")),
            risk_notes=string_value(metadata.get("risk_notes", "")),
            expected_metric_change=string_mapping(
                metadata.get("expected_metric_change", {})
            ),
            raw_response=raw_output,
            patch_diff=patch_diff,
            applicable=applicable,
            protocol_version=string_value(
                metadata.get("protocol_version", PROPOSAL_PROTOCOL_VERSION)
            ),
            direction_tag=string_value(metadata.get("direction_tag", "")),
            hypotheses=string_tuple(metadata.get("hypotheses", ())),
            rejection_reason=rejection_reason,
            prompt=prompt,
            command=command,
            workspace_path=workspace_path,
        )
    )


def proposal_metadata_from_raw_output(raw_output: str) -> dict[str, object]:
    """Return proposal metadata from JSON output, or an empty mapping for plain diffs."""
    try:
        payload = extract_json_object(raw_output)
    except PatchParseError:
        return {}
    if isinstance(payload.get("selected_proposal"), dict):
        return payload["selected_proposal"]  # type: ignore[return-value]
    if isinstance(payload.get("proposal"), dict):
        return payload["proposal"]  # type: ignore[return-value]
    return payload


def proposal_with_patch_hash(proposal: StrategyProposal) -> StrategyProposal:
    """Attach a patch hash when the proposal has a patch and no hash yet."""
    if proposal.patch_sha256 or not proposal.patch_diff:
        return proposal
    return replace(proposal, patch_sha256=sha256_text(proposal.patch_diff))


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def write_optional_json(path: Path | None, payload: object) -> None:
    """Write deterministic JSON when a path is supplied."""
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def string_value(value: object) -> str:
    """Return a string value for JSON metadata."""
    return value if isinstance(value, str) else ""


def string_mapping(value: object) -> dict[str, str]:
    """Return a string-to-string mapping from JSON metadata."""
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def string_tuple(value: object) -> tuple[str, ...]:
    """Return non-empty string items as a tuple."""
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def main() -> None:
    """CLI entrypoint for validating raw strategy-agent output."""
    args = parse_args()
    report = verify_agent_output(
        agent_input_path=args.agent_input,
        agent_output_path=args.agent_output,
        repo_root=args.repo_root,
        output_path=args.output,
        proposal_output_path=args.proposal_output,
        agent_name=args.agent_name,
        check_git_apply=not args.skip_git_apply_check,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for agent output validation."""
    parser = argparse.ArgumentParser(
        description="Validate raw agent output before applying a strategy patch.",
    )
    parser.add_argument("agent_input", type=Path, help="Path to agent_input.json.")
    parser.add_argument("agent_output", type=Path, help="Path to raw agent output.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root used for git apply checks.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write agent_validation.json.",
    )
    parser.add_argument(
        "--proposal-output",
        type=Path,
        default=None,
        help="Optional path to write the normalized proposal JSON.",
    )
    parser.add_argument(
        "--agent-name",
        default=DEFAULT_INTAKE_AGENT_NAME,
        help="Agent name to use when raw output omits one.",
    )
    parser.add_argument(
        "--skip-git-apply-check",
        action="store_true",
        help="Validate contract shape without running git apply --check.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
