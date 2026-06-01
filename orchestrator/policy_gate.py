"""Deterministic acceptance policy for V0 strategy patches."""

from __future__ import annotations


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

    if after["trade_count"] < active_rules["min_trade_count"]:
        reasons.append(
            "trade_count "
            f"{after['trade_count']} < {active_rules['min_trade_count']}"
        )

    ev_improvement = float(after["ev"]) - float(before["ev"])
    if ev_improvement < active_rules["min_ev_improvement"]:
        reasons.append(
            "ev improvement "
            f"{ev_improvement:.6f} < {active_rules['min_ev_improvement']}"
        )

    drawdown_worsening = float(after["max_drawdown"]) - float(before["max_drawdown"])
    if drawdown_worsening > active_rules["max_drawdown_worsening"]:
        reasons.append(
            "max_drawdown worsening "
            f"{drawdown_worsening:.6f} > {active_rules['max_drawdown_worsening']}"
        )

    slippage_worsening = float(after["avg_slippage"]) - float(before["avg_slippage"])
    if slippage_worsening > active_rules["max_slippage_worsening"]:
        reasons.append(
            "avg_slippage worsening "
            f"{slippage_worsening:.6f} > {active_rules['max_slippage_worsening']}"
        )

    return {
        "accepted": not reasons,
        "reasons": reasons,
        "before": before,
        "after": after,
    }


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

    if enabled and after["trade_count"] < active_rules["min_trade_count"]:
        reasons.append(
            "holdout trade_count "
            f"{after['trade_count']} < {active_rules['min_trade_count']}"
        )

    ev_delta = float(after["ev"]) - float(before["ev"])
    if enabled and ev_delta < active_rules["min_ev_delta"]:
        reasons.append(
            "holdout ev delta "
            f"{ev_delta:.6f} < {active_rules['min_ev_delta']}"
        )

    drawdown_worsening = float(after["max_drawdown"]) - float(before["max_drawdown"])
    if enabled and drawdown_worsening > active_rules["max_drawdown_worsening"]:
        reasons.append(
            "holdout max_drawdown worsening "
            f"{drawdown_worsening:.6f} > {active_rules['max_drawdown_worsening']}"
        )

    slippage_worsening = float(after["avg_slippage"]) - float(before["avg_slippage"])
    if enabled and slippage_worsening > active_rules["max_slippage_worsening"]:
        reasons.append(
            "holdout avg_slippage worsening "
            f"{slippage_worsening:.6f} > {active_rules['max_slippage_worsening']}"
        )

    return {
        "enabled": enabled,
        "accepted": not reasons,
        "reasons": reasons,
        "before": before,
        "after": after,
        "rules": active_rules,
    }


def decision_reasons(decision: dict[str, object]) -> list[str]:
    """Return decision reasons as strings."""
    reasons = decision.get("reasons", [])
    if not isinstance(reasons, list):
        return []
    return [str(reason) for reason in reasons]
