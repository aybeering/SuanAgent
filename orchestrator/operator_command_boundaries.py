"""Shared operator command boundary classification helpers."""

from __future__ import annotations


def classify_operator_command(
    *,
    label: str,
    writes_artifact: str,
) -> dict[str, object]:
    """Return a deterministic authority boundary for an operator command hint."""
    if label == "record_operator_approval":
        boundary_type = "operator_approval_receipt"
    elif label == "execute_approved_command":
        boundary_type = "guarded_read_only_execution"
    elif writes_artifact:
        boundary_type = "read_only_artifact_refresh"
    else:
        boundary_type = "read_only_inspection"

    return {
        "boundary_type": boundary_type,
        "requires_explicit_operator_invocation": True,
        "requires_operator_approval": label == "execute_approved_command",
        "records_operator_approval": label == "record_operator_approval",
        "uses_guarded_executor": label == "execute_approved_command",
        "writes_artifact": bool(writes_artifact),
        "executes_agents": False,
        "runs_backtests": False,
        "applies_patches": False,
        "changes_acceptance": False,
    }
