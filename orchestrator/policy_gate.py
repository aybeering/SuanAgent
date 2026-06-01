"""Deterministic acceptance policy for V0 strategy patches."""

from __future__ import annotations


DEFAULT_RULES = {
    "min_trade_count": 20,
    "min_ev_improvement": 0.01,
    "max_drawdown_worsening": 0.01,
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
