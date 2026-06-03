"""Deterministic run-outcome summaries for iteration artifacts."""

from __future__ import annotations

from typing import Any


RUN_OUTCOME_SUMMARY_SCHEMA_VERSION = "run_outcome_summary_v1"


def build_run_outcome_summary(
    *,
    manifest: dict[str, object],
    artifact_ok: bool | None = None,
    artifact_error_count: int = 0,
) -> dict[str, object]:
    """Return a stable read-only outcome summary for one iteration run."""
    rounds = [
        row
        for row in manifest.get("rounds", [])
        if isinstance(row, dict) and isinstance(row.get("round_id"), str)
    ]
    round_rows = [round_outcome(row) for row in rounds]
    primary = primary_outcome(
        manifest=manifest,
        rounds=round_rows,
        artifact_ok=artifact_ok,
        artifact_error_count=artifact_error_count,
    )
    return {
        "schema_version": RUN_OUTCOME_SUMMARY_SCHEMA_VERSION,
        "status": str(manifest.get("status", "unknown")),
        "accepted": str(manifest.get("status", "")) == "accepted",
        "category": primary["category"],
        "primary_stage": primary["stage"],
        "primary_code": primary["code"],
        "primary_message": primary["message"],
        "stop_reason": str(manifest.get("stop_reason", "") or ""),
        "completed_rounds": int(manifest.get("completed_rounds", len(round_rows)) or 0),
        "accepted_round": manifest.get("accepted_round"),
        "final_strategy_commit": manifest.get("final_strategy_commit"),
        "artifact_ok": artifact_ok,
        "artifact_error_count": artifact_error_count,
        "category_counts": count_key(round_rows, "category"),
        "stage_counts": count_key(round_rows, "failure_stage"),
        "code_counts": count_key(round_rows, "failure_code", skip_none=True),
        "rounds": round_rows,
    }


def primary_outcome(
    *,
    manifest: dict[str, object],
    rounds: list[dict[str, object]],
    artifact_ok: bool | None,
    artifact_error_count: int,
) -> dict[str, str]:
    """Choose the run-level primary outcome from deterministic evidence."""
    if artifact_ok is False:
        return {
            "category": "artifact_invalid",
            "stage": "artifact_validation",
            "code": "artifact_validation_failed",
            "message": f"{artifact_error_count} artifact validation errors",
        }
    status = str(manifest.get("status", "unknown"))
    if status == "accepted":
        accepted_round = str(manifest.get("accepted_round", "") or "")
        return {
            "category": "accepted",
            "stage": "acceptance",
            "code": "accepted",
            "message": f"accepted round {accepted_round}" if accepted_round else "accepted",
        }
    if status == "failed":
        return {
            "category": "run_failed",
            "stage": "runtime",
            "code": "run_failed",
            "message": str(manifest.get("error", "") or "iteration loop failed"),
        }

    intake = object_value(manifest.get("agent_intake_summary", {}))
    if int(intake.get("blocked_round_count", 0) or 0) > 0:
        return {
            "category": "agent_intake_blocked",
            "stage": str(intake.get("primary_stage", "agent_intake")),
            "code": str(intake.get("primary_code", "agent_intake_blocked")),
            "message": str(intake.get("primary_message", "")),
        }
    if status == "stopped_repeated_proposal":
        return {
            "category": "repeated_proposal",
            "stage": "proposal",
            "code": "repeated_proposal",
            "message": str(manifest.get("stop_reason", "") or "repeated proposal"),
        }
    if status == "stopped_no_improvement":
        return {
            "category": "no_improvement",
            "stage": "improvement",
            "code": "no_improvement",
            "message": str(manifest.get("stop_reason", "") or "no improvement"),
        }

    latest_failure = latest_non_accepted_round(rounds)
    if latest_failure:
        category = str(latest_failure.get("category", "round_rejected"))
        return {
            "category": category,
            "stage": str(latest_failure.get("failure_stage", "none")),
            "code": str(latest_failure.get("failure_code", "none")),
            "message": str(latest_failure.get("failure_message", "")),
        }
    if status == "stopped_max_rounds":
        return {
            "category": "max_rounds",
            "stage": "iteration",
            "code": "max_rounds_reached",
            "message": str(manifest.get("stop_reason", "") or "max rounds reached"),
        }
    return {
        "category": "unknown",
        "stage": "unknown",
        "code": "unknown",
        "message": "",
    }


def round_outcome(round_payload: dict[str, Any]) -> dict[str, object]:
    """Return a compact outcome row for one manifest round."""
    accepted = bool(round_payload.get("accepted", False))
    failure_stage = str(round_payload.get("failure_stage", "none"))
    failure_code = str(round_payload.get("failure_code", "none"))
    failure_message = str(round_payload.get("failure_message", ""))
    return {
        "round_id": str(round_payload.get("round_id", "")),
        "accepted": accepted,
        "category": round_category(
            accepted=accepted,
            failure_stage=failure_stage,
            failure_code=failure_code,
        ),
        "failure_stage": failure_stage,
        "failure_code": failure_code,
        "failure_message": failure_message,
        "reason_codes": round_payload.get("reason_codes", []),
        "proposal_is_repeat": bool(round_payload.get("proposal_is_repeat", False)),
        "agent_intake_primary_code": object_value(
            round_payload.get("agent_intake_diagnosis", {})
        ).get("primary_code", "none"),
    }


def round_category(
    *,
    accepted: bool,
    failure_stage: str,
    failure_code: str,
) -> str:
    """Classify a round failure into a stable operator-facing category."""
    if accepted:
        return "accepted"
    if failure_stage == "holdout_gate" or failure_code.startswith("holdout_"):
        return "holdout_veto"
    if failure_stage == "policy_gate" or failure_code.startswith("policy_"):
        return "policy_reject"
    if failure_stage in {"agent_validation", "contract", "proposal", "workspace"}:
        return "agent_intake_blocked"
    if failure_code and failure_code != "none":
        return "round_rejected"
    return "round_rejected"


def latest_non_accepted_round(rounds: list[dict[str, object]]) -> dict[str, object]:
    """Return the latest rejected round outcome row."""
    for row in reversed(rounds):
        if not bool(row.get("accepted", False)):
            return row
    return {}


def count_key(
    rows: list[dict[str, object]],
    key: str,
    *,
    skip_none: bool = False,
) -> dict[str, int]:
    """Count stable string values by key."""
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, ""))
        if not value:
            continue
        if skip_none and value == "none":
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


def object_value(value: object) -> dict[str, Any]:
    """Return a dict value or an empty dict."""
    return value if isinstance(value, dict) else {}
