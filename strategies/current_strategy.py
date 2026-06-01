"""Current candidate strategy for V0.

Only this file should be changed by future strategy-improvement steps. It starts
as a copy of the baseline strategy so the initial V0 loop is deterministic.
"""

from __future__ import annotations

from backtester.schema import MarketSnapshot, StrategyOrder


MIN_EDGE = 0.05
STAKE = 10.0


def generate_orders(snapshot: MarketSnapshot) -> list[StrategyOrder]:
    """Return deterministic orders for one market snapshot."""
    edge = snapshot.fair_value - snapshot.yes_price
    if edge >= MIN_EDGE and snapshot.liquidity >= STAKE:
        return [
            StrategyOrder(
                market_id=snapshot.market_id,
                side="YES",
                limit_price=snapshot.yes_price,
                stake=STAKE,
                reason=f"edge={edge:.4f}",
            )
        ]
    return []
