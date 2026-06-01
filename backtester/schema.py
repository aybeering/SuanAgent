"""Shared V0 data structures."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class MarketSnapshot:
    """One immutable row of validation market data."""

    timestamp: str
    market_id: str
    yes_price: float
    fair_value: float
    outcome: int
    liquidity: float
    next_yes_price: float


@dataclass(frozen=True)
class StrategyOrder:
    """A deterministic strategy order request."""

    market_id: str
    side: str
    limit_price: float
    stake: float
    reason: str


@dataclass(frozen=True)
class Trade:
    """A filled order used for metrics and audit output."""

    timestamp: str
    market_id: str
    side: str
    requested_price: float
    fill_price: float
    stake: float
    quantity: float
    outcome: int
    pnl: float
    slippage: float
    reason: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON/CSV friendly representation."""
        return asdict(self)
