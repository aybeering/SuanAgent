"""Deterministic acceptance policy for V0 strategy patches."""

from __future__ import annotations

from orchestrator.failure_taxonomy import (
    attach_failure_metadata,
    normalize_reason_codes,
    reason_code,
)


DEFAULT_RULES = {
    "min_trade_count": 20,
    "min_ev_improvement": 0.01,
    "max_drawdown_worsening": 0.01,
    "max_slippage_worsening": 0.005,
}

DEFAULT_HOLDOUT_RULES = {
    "enabled": False,
    "min_trade_count": 1,
    "min_ev_delta": -0.01,
    "max_drawdown_worsening": 0.02,
    "max_slippage_worsening": 0.005,
}


def evaluate_policy(
    before: dict[str, float | int],
    after: dict[str, float | int],
    rules: dict[str, float | int] | None = None,
) -> dict[str, object]:
    """Return a deterministic accept/reject decision for candidate metrics."""
    active_rules = DEFAULT_RULES | (rules or {})
    reasons: list[str] = []
    reason_codes: list[dict[str, str]] = []

    if after["trade_count"] < active_rules["min_trade_count"]:
        message = (
            "trade_count "
            f"{after['trade_count']} < {active_rules['min_trade_count']}"
        )
        reasons.append(message)
        reason_codes.append(
            reason_code(
                stage="policy_gate",
                code="policy_trade_count_low",
                message=message,
            )
        )

    ev_improvement = float(after["ev"]) - float(before["ev"])
    if ev_improvement < active_rules["min_ev_improvement"]:
        message = (
            "ev improvement "
            f"{ev_improvement:.6f} < {active_rules['min_ev_improvement']}"
        )
        reasons.append(message)
        reason_codes.append(
            reason_code(
                stage="policy_gate",
                code="policy_ev_improvement_low",
                message=message,
            )
        )

    drawdown_worsening = float(after["max_drawdown"]) - float(before["max_drawdown"])
    if drawdown_worsening > active_rules["max_drawdown_worsening"]:
        message = (
            "max_drawdown worsening "
            f"{drawdown_worsening:.6f} > {active_rules['max_drawdown_worsening']}"
        )
        reasons.append(message)
        reason_codes.append(
            reason_code(
                stage="policy_gate",
                code="policy_drawdown_worsened",
                message=message,
            )
        )

    slippage_worsening = float(after["avg_slippage"]) - float(before["avg_slippage"])
    if slippage_worsening > active_rules["max_slippage_worsening"]:
        message = (
            "avg_slippage worsening "
            f"{slippage_worsening:.6f} > {active_rules['max_slippage_worsening']}"
        )
        reasons.append(message)
        reason_codes.append(
            reason_code(
                stage="policy_gate",
                code="policy_slippage_worsened",
                message=message,
            )
        )

    return attach_failure_metadata({
        "accepted": not reasons,
        "reasons": reasons,
        "before": before,
        "after": after,
    }, reason_codes)


def apply_holdout_gate(
    decision: dict[str, object],
    *,
    before: dict[str, float | int],
    after: dict[str, float | int],
    rules: dict[str, float | int | bool] | None = None,
) -> dict[str, object]:
    """Attach optional holdout checks to a validation policy decision."""
    holdout_decision = evaluate_holdout_policy(before=before, after=after, rules=rules)
    decision["holdout_policy"] = holdout_decision
    if holdout_decision["enabled"] and not holdout_decision["accepted"]:
        decision["accepted"] = False
        decision["reasons"] = [
            *decision_reasons(decision),
            *holdout_decision["reasons"],  # type: ignore[list-item]
        ]
        decision["reason_codes"] = [
            *decision_reason_codes(decision),
            *decision_reason_codes(holdout_decision),
        ]
        attach_failure_metadata(
            decision,
            decision_reason_codes(decision),
        )
    return decision


def evaluate_holdout_policy(
    *,
    before: dict[str, float | int],
    after: dict[str, float | int],
    rules: dict[str, float | int | bool] | None = None,
) -> dict[str, object]:
    """Return deterministic holdout risk checks for candidate metrics."""
    active_rules = DEFAULT_HOLDOUT_RULES | (rules or {})
    enabled = bool(active_rules["enabled"])
    reasons: list[str] = []
    reason_codes: list[dict[str, str]] = []

    if enabled and after["trade_count"] < active_rules["min_trade_count"]:
        message = (
            "holdout trade_count "
            f"{after['trade_count']} < {active_rules['min_trade_count']}"
        )
        reasons.append(message)
        reason_codes.append(
            reason_code(
                stage="holdout_gate",
                code="holdout_trade_count_low",
                message=message,
            )
        )

    ev_delta = float(after["ev"]) - float(before["ev"])
    if enabled and ev_delta < active_rules["min_ev_delta"]:
        message = (
            "holdout ev delta "
            f"{ev_delta:.6f} < {active_rules['min_ev_delta']}"
        )
        reasons.append(message)
        reason_codes.append(
            reason_code(
                stage="holdout_gate",
                code="holdout_ev_delta_low",
                message=message,
            )
        )

    drawdown_worsening = float(after["max_drawdown"]) - float(before["max_drawdown"])
    if enabled and drawdown_worsening > active_rules["max_drawdown_worsening"]:
        message = (
            "holdout max_drawdown worsening "
            f"{drawdown_worsening:.6f} > {active_rules['max_drawdown_worsening']}"
        )
        reasons.append(message)
        reason_codes.append(
            reason_code(
                stage="holdout_gate",
                code="holdout_drawdown_worsened",
                message=message,
            )
        )

    slippage_worsening = float(after["avg_slippage"]) - float(before["avg_slippage"])
    if enabled and slippage_worsening > active_rules["max_slippage_worsening"]:
        message = (
            "holdout avg_slippage worsening "
            f"{slippage_worsening:.6f} > {active_rules['max_slippage_worsening']}"
        )
        reasons.append(message)
        reason_codes.append(
            reason_code(
                stage="holdout_gate",
                code="holdout_slippage_worsened",
                message=message,
            )
        )

    return attach_failure_metadata({
        "enabled": enabled,
        "accepted": not reasons,
        "reasons": reasons,
        "before": before,
        "after": after,
        "rules": active_rules,
    }, reason_codes)


def decision_reasons(decision: dict[str, object]) -> list[str]:
    """Return decision reasons as strings."""
    reasons = decision.get("reasons", [])
    if not isinstance(reasons, list):
        return []
    return [str(reason) for reason in reasons]


def decision_reason_codes(decision: dict[str, object]) -> list[dict[str, str]]:
    """Return decision reason-code rows."""
    return normalize_reason_codes(decision.get("reason_codes", []))
