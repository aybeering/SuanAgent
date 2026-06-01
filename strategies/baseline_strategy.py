"""Baseline V0 strategy.

The strategy buys YES when the fixed dataset's estimated fair value is at least
five cents above the current YES price and visible liquidity can cover the
stake. It is intentionally simple so strategy changes can be audited.
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
