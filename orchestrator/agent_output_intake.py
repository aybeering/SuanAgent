"""Validate raw strategy-agent output before the loop can apply it."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from orchestrator.failure_taxonomy import (
    agent_validation_reason_codes,
    attach_failure_metadata,
    primary_failure,
)
from orchestrator.git_manager import GitError, check_patch
from orchestrator.patch_parser import (
    PatchParseError,
    extract_json_object,
    extract_unified_diff,
)
from orchestrator.proposal import (
    PROPOSAL_PROTOCOL_VERSION,
    StrategyProposal,
    build_proposal_semantic_report,
    sha256_text,
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
    proposal_intent_summary = dict_or_empty(
        agent_input.get("proposal_intent_summary", {})
    )
    normalized_proposal = proposal_with_patch_hash(proposal)
    semantic_checks = build_proposal_semantic_report(
        proposal=normalized_proposal,
        expected_target_file=expected_target,
        expected_round_index=expected_round_index,
    )
    contract_errors = tuple(str(error) for error in semantic_checks["errors"])
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
    reason_codes = agent_validation_reason_codes(
        contract_errors=contract_errors,
        git_apply_error=git_apply_error,
    )
    intake_diagnosis = build_agent_intake_diagnosis(
        reason_codes=reason_codes,
        errors=errors,
        git_apply_status=git_apply_status,
    )

    report: dict[str, object] = attach_failure_metadata({
        "schema_version": AGENT_VALIDATION_SCHEMA_VERSION,
        "ok": not errors,
        "errors": errors,
        "warnings": [],
        "agent_input_path": str(agent_input_path),
        "agent_output_path": str(agent_output_path or ""),
        "proposal_intent_summary": proposal_intent_summary,
        "expected_target_file": str(expected_target),
        "expected_round_index": expected_round_index,
        "proposal_protocol_version": normalized_proposal.protocol_version,
        "proposal_applicable": normalized_proposal.applicable,
        "proposal_target_file": normalized_proposal.target_file,
        "proposal_direction_tag": normalized_proposal.direction_tag,
        "proposal_patch_sha256": normalized_proposal.patch_sha256,
        "semantic_checks": semantic_checks,
        "intake_diagnosis": intake_diagnosis,
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
    }, reason_codes)
    report["consistency_checks"] = agent_validation_consistency_checks(
        report=report,
        agent_input=agent_input,
        agent_output_path=agent_output_path,
        proposal=normalized_proposal,
    )
    write_optional_json(output_path, report)
    return report


def agent_validation_consistency_checks(
    *,
    report: dict[str, object],
    agent_input: dict[str, Any],
    agent_output_path: Path | None,
    proposal: StrategyProposal,
) -> dict[str, object]:
    """Return deterministic self-checks for the validation report."""
    proposal_payload = dict_or_empty(report.get("proposal", {}))
    checks_payload = dict_or_empty(report.get("checks", {}))
    semantic_payload = dict_or_empty(report.get("semantic_checks", {}))
    diagnosis_payload = dict_or_empty(report.get("intake_diagnosis", {}))
    errors = string_list(report.get("errors", []))
    semantic_errors = string_list(semantic_payload.get("errors", []))
    reason_codes = reason_code_rows(report.get("reason_codes", []))
    raw_output = read_text_or_empty(agent_output_path)
    patch_sha256 = str(report.get("proposal_patch_sha256", ""))
    patch_diff = str(proposal_payload.get("patch_diff", ""))
    checks = {
        "ok_matches_errors": bool(report.get("ok", False)) == (not errors),
        "failure_code_matches_ok": (
            (
                bool(report.get("ok", False))
                and str(report.get("failure_code", "")) == "none"
            )
            or (
                not bool(report.get("ok", False))
                and str(report.get("failure_code", "")) != "none"
            )
        ),
        "proposal_intent_matches_agent_input": (
            report.get("proposal_intent_summary", {})
            == agent_input.get("proposal_intent_summary", {})
        ),
        "expected_round_matches_agent_input": (
            int(report.get("expected_round_index", -1))
            == int(agent_input.get("round_index", -2))
        ),
        "expected_target_matches_agent_input": (
            str(report.get("expected_target_file", ""))
            == str(agent_input.get("target_file", ""))
        ),
        "proposal_round_matches_expected": (
            int(proposal_payload.get("round_index", -1))
            == int(report.get("expected_round_index", -2))
        ),
        "proposal_target_matches_expected": (
            str(proposal_payload.get("target_file", ""))
            == str(report.get("expected_target_file", ""))
        ),
        "proposal_protocol_matches_top_level": (
            str(proposal_payload.get("protocol_version", ""))
            == str(report.get("proposal_protocol_version", ""))
        ),
        "proposal_applicable_matches_top_level": (
            bool(proposal_payload.get("applicable", False))
            == bool(report.get("proposal_applicable", False))
        ),
        "proposal_direction_matches_top_level": (
            str(proposal_payload.get("direction_tag", ""))
            == str(report.get("proposal_direction_tag", ""))
        ),
        "proposal_patch_hash_matches_top_level": (
            str(proposal_payload.get("patch_sha256", "")) == patch_sha256
        ),
        "patch_hash_matches_patch_diff": (
            (not patch_diff and not patch_sha256)
            or sha256_text(patch_diff) == patch_sha256
        ),
        "raw_output_matches_proposal": (
            not raw_output
            or raw_output.rstrip("\n")
            == str(proposal_payload.get("raw_response", "")).rstrip("\n")
        ),
        "contract_check_matches_errors": (
            bool(checks_payload.get("contract_valid", False))
            == (not bool(contract_error_rows(errors)))
        ),
        "semantic_check_matches_contract_valid": (
            bool(semantic_payload.get("ok", False))
            == bool(checks_payload.get("contract_valid", False))
        ),
        "semantic_errors_match_report_contract_errors": (
            semantic_errors == contract_error_rows(errors)
        ),
        "intake_diagnosis_matches_failure_metadata": (
            str(diagnosis_payload.get("primary_stage", ""))
            == str(report.get("failure_stage", ""))
            and str(diagnosis_payload.get("primary_code", ""))
            == str(report.get("failure_code", ""))
            and str(diagnosis_payload.get("primary_message", ""))
            == str(report.get("failure_message", ""))
        ),
        "intake_diagnosis_codes_match_reason_codes": (
            string_list(diagnosis_payload.get("blocking_codes", []))
            == [row["code"] for row in reason_codes]
        ),
        "git_apply_error_matches_errors": (
            not str(checks_payload.get("git_apply_error", ""))
            or any(error.startswith("git apply check failed:") for error in errors)
        ),
        "strategy_only_matches_contract_errors": (
            bool(checks_payload.get("strategy_only_patch", False))
            == (
                not any(
                    "patch_diff target validation failed" in error for error in errors
                )
            )
        ),
    }
    blocking_reasons = [
        f"agent_validation_consistency:{name}"
        for name, passed in checks.items()
        if not passed
    ]
    return {
        "agent_output_path": str(agent_output_path or ""),
        "proposal_patch_sha256": patch_sha256,
        "checks": checks,
        "blocking_reasons": blocking_reasons,
    }


def build_agent_intake_diagnosis(
    *,
    reason_codes: list[dict[str, str]],
    errors: list[str],
    git_apply_status: str,
) -> dict[str, object]:
    """Return a compact stable diagnosis for raw agent-output intake."""
    failure = primary_failure(reason_codes)
    blocking_codes = [
        str(row.get("code", ""))
        for row in reason_codes
        if str(row.get("code", "")) and str(row.get("code", "")) != "none"
    ]
    retryable_codes = {
        "patch_check_failed",
    }
    return {
        "schema_version": "agent_intake_diagnosis_v1",
        "status": "passed" if not errors else "blocked",
        "primary_stage": failure["stage"],
        "primary_code": failure["code"],
        "primary_message": failure["message"],
        "blocking_codes": blocking_codes,
        "blocking_count": len(blocking_codes),
        "retryable": any(code in retryable_codes for code in blocking_codes),
        "git_apply_status": git_apply_status,
    }


def proposal_from_raw_agent_output(
    *,
    raw_output: str,
    agent_input: dict[str, Any],
    agent_name: str = DEFAULT_INTAKE_AGENT_NAME,
    prompt: str = "",
    command: tuple[str, ...] = (),
    workspace_path: str = "",
    default_summary: str = "",
    default_risk_notes: str = "",
    default_direction_tag: str = "",
    default_hypotheses: tuple[str, ...] = (),
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
            summary=string_value(metadata.get("summary", "")) or default_summary,
            risk_notes=(
                string_value(metadata.get("risk_notes", "")) or default_risk_notes
            ),
            expected_metric_change=string_mapping(
                metadata.get("expected_metric_change", {})
            ),
            raw_response=raw_output,
            patch_diff=patch_diff,
            applicable=applicable,
            protocol_version=string_value(
                metadata.get("protocol_version", PROPOSAL_PROTOCOL_VERSION)
            ),
            direction_tag=(
                string_value(metadata.get("direction_tag", "")) or default_direction_tag
            ),
            hypotheses=(
                string_tuple(metadata.get("hypotheses", ())) or default_hypotheses
            ),
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


def dict_or_empty(value: object) -> dict[str, object]:
    """Return a JSON object value or an empty object."""
    return value if isinstance(value, dict) else {}


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


def string_list(value: object) -> list[str]:
    """Return list items as strings."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def reason_code_rows(value: object) -> list[dict[str, str]]:
    """Return valid reason-code rows from a JSON-like value."""
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append({
            "stage": str(item.get("stage", "")),
            "code": str(item.get("code", "")),
            "message": str(item.get("message", "")),
        })
    return rows


def read_text_or_empty(path: Path | None) -> str:
    """Return file text when a path is present and readable."""
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def contract_error_rows(errors: list[str]) -> list[str]:
    """Return validation errors that came from proposal contract checks."""
    return [
        error
        for error in errors
        if not error.startswith("git apply check failed:")
    ]


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
