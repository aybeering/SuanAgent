"""Stable machine-readable failure taxonomy for agent attempts and gates."""

from __future__ import annotations

from typing import Any


NO_FAILURE_STAGE = "none"
NO_FAILURE_CODE = "none"


def reason_code(*, stage: str, code: str, message: str = "") -> dict[str, str]:
    """Return one stable reason-code record."""
    return {
        "stage": stage,
        "code": code,
        "message": message,
    }


def no_failure() -> dict[str, str]:
    """Return the stable no-failure sentinel."""
    return reason_code(stage=NO_FAILURE_STAGE, code=NO_FAILURE_CODE, message="")


def primary_failure(reason_codes: object) -> dict[str, str]:
    """Return the first real failure from a reason-code list."""
    if isinstance(reason_codes, list):
        for item in reason_codes:
            if not isinstance(item, dict):
                continue
            stage = str(item.get("stage", ""))
            code = str(item.get("code", ""))
            if stage and code and code != NO_FAILURE_CODE:
                return reason_code(
                    stage=stage,
                    code=code,
                    message=str(item.get("message", "")),
                )
    return no_failure()


def normalize_reason_codes(reason_codes: object) -> list[dict[str, str]]:
    """Return valid reason-code rows from an arbitrary payload value."""
    if not isinstance(reason_codes, list):
        return []
    rows: list[dict[str, str]] = []
    for item in reason_codes:
        if not isinstance(item, dict):
            continue
        stage = str(item.get("stage", ""))
        code = str(item.get("code", ""))
        if not stage or not code:
            continue
        rows.append(
            reason_code(
                stage=stage,
                code=code,
                message=str(item.get("message", "")),
            )
        )
    return rows


def attach_failure_metadata(
    payload: dict[str, Any],
    reason_codes: list[dict[str, str]],
) -> dict[str, Any]:
    """Attach reason codes plus first-failure metadata to a payload."""
    failure = primary_failure(reason_codes)
    payload["reason_codes"] = reason_codes
    payload["failure_stage"] = failure["stage"]
    payload["failure_code"] = failure["code"]
    payload["failure_message"] = failure["message"]
    return payload


def attempt_prefilter_reason_codes(
    *,
    status: str,
    contract_errors: object,
    memory_filter_reason: str,
    patch_memory_filter_reason: str,
    direction_filter_reason: str,
    patch_check_error: str,
    probe_error: str,
    duplicate_patch: bool,
    applicable: bool,
    direction_capability_reason: str = "",
) -> list[dict[str, str]]:
    """Classify cheap pre-validation candidate failures."""
    if isinstance(contract_errors, list | tuple) and contract_errors:
        return [
            reason_code(
                stage="contract",
                code="contract_invalid",
                message="; ".join(str(error) for error in contract_errors),
            )
        ]
    if direction_capability_reason or status == "direction_not_supported":
        return [
            reason_code(
                stage="selection",
                code="profile_direction_not_supported",
                message=direction_capability_reason
                or "proposal direction is not supported by this profile",
            )
        ]
    if patch_memory_filter_reason and direction_filter_reason:
        return [
            reason_code(
                stage="memory",
                code="outcome_memory_rejected",
                message=f"{patch_memory_filter_reason}; {direction_filter_reason}",
            )
        ]
    if patch_memory_filter_reason:
        return [
            reason_code(
                stage="memory",
                code="patch_memory_rejected",
                message=patch_memory_filter_reason,
            )
        ]
    if direction_filter_reason:
        return [
            reason_code(
                stage="memory",
                code="direction_memory_rejected",
                message=direction_filter_reason,
            )
        ]
    if memory_filter_reason:
        return [
            reason_code(
                stage="memory",
                code="outcome_memory_rejected",
                message=memory_filter_reason,
            )
        ]
    if not applicable or status == "not_applicable":
        return [
            reason_code(
                stage="proposal",
                code="proposal_not_applicable",
                message="proposal is marked non-applicable",
            )
        ]
    if duplicate_patch or status == "duplicate_candidate":
        return [
            reason_code(
                stage="selection",
                code="duplicate_candidate_patch",
                message="candidate patch hash duplicates an earlier candidate",
            )
        ]
    if patch_check_error:
        return [
            reason_code(
                stage="patch",
                code="patch_check_failed",
                message=patch_check_error,
            )
        ]
    if probe_error:
        return [
            reason_code(
                stage="probe",
                code="probe_failed",
                message=probe_error,
            )
        ]
    if status and status not in {"selectable", "accepted"}:
        return [
            reason_code(
                stage="selection",
                code=f"candidate_status_{status}",
                message=f"status={status}",
            )
        ]
    return []


def selection_skip_reason_codes(
    *,
    selected: bool,
    status: str,
    blocking_reasons: list[str],
    selected_index: int | None,
) -> list[dict[str, str]]:
    """Classify why an unselected row was skipped in selection artifacts."""
    if selected:
        return []
    if blocking_reasons:
        return [
            reason_code(
                stage="selection",
                code="candidate_blocked",
                message="; ".join(blocking_reasons),
            )
        ]
    if selected_index is None:
        return [
            reason_code(
                stage="selection",
                code="no_selected_attempt",
                message="no selected attempt",
            )
        ]
    if status == "selectable":
        return [
            reason_code(
                stage="selection",
                code="candidate_lower_rank",
                message="selectable but not highest ranked",
            )
        ]
    return [
        reason_code(
            stage="selection",
            code=f"candidate_status_{status or 'unknown'}",
            message=f"status={status or 'unknown'}",
        )
    ]


def agent_validation_reason_codes(
    *,
    contract_errors: tuple[str, ...],
    git_apply_error: str,
) -> list[dict[str, str]]:
    """Classify deterministic raw-agent validation failures."""
    reasons: list[dict[str, str]] = []
    if contract_errors:
        reasons.append(
            reason_code(
                stage="contract",
                code="contract_invalid",
                message="; ".join(contract_errors),
            )
        )
    if git_apply_error:
        reasons.append(
            reason_code(
                stage="patch",
                code="patch_check_failed",
                message=git_apply_error,
            )
        )
    return reasons


def apply_error_reason_code(apply_error: str) -> dict[str, str]:
    """Classify an apply-time error string into a stable code."""
    normalized = apply_error.lower()
    if normalized.startswith("agent output validation failed"):
        return reason_code(
            stage="contract",
            code="agent_validation_failed",
            message=apply_error,
        )
    if "memory filter rejected patch" in normalized:
        return reason_code(
            stage="memory",
            code="patch_memory_rejected",
            message=apply_error,
        )
    if "direction memory filter rejected" in normalized:
        return reason_code(
            stage="memory",
            code="direction_memory_rejected",
            message=apply_error,
        )
    if "proposal contract invalid" in normalized:
        return reason_code(
            stage="contract",
            code="contract_invalid",
            message=apply_error,
        )
    if "git apply" in normalized or "patch" in normalized:
        return reason_code(
            stage="patch",
            code="patch_apply_failed",
            message=apply_error,
        )
    if "not include a patch" in normalized or "does not emit patches" in normalized:
        return reason_code(
            stage="proposal",
            code="proposal_not_applicable",
            message=apply_error,
        )
    return reason_code(
        stage="application",
        code="application_failed",
        message=apply_error,
    )


def probe_reason_codes(*, ok: bool, error: str = "") -> list[dict[str, str]]:
    """Classify attempt replay probe failures."""
    if ok:
        return []
    return [
        reason_code(
            stage="probe",
            code="probe_failed",
            message=error or "probe failed",
        )
    ]
