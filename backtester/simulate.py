"""Deterministic CSV backtester for V0 strategies."""

from __future__ import annotations

import csv
import importlib
from pathlib import Path
from types import ModuleType

from backtester.metrics import calculate_metrics
from backtester.schema import MarketSnapshot, StrategyOrder, Trade


DEFAULT_DATA_PATH = Path("data/validation/sample_markets.csv")


def load_snapshots(data_path: Path = DEFAULT_DATA_PATH) -> list[MarketSnapshot]:
    """Load fixed validation snapshots from CSV."""
    with data_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [
            MarketSnapshot(
                timestamp=str(row["timestamp"]),
                market_id=str(row["market_id"]),
                yes_price=float(row["yes_price"]),
                fair_value=float(row["fair_value"]),
                outcome=int(row["outcome"]),
                liquidity=float(row["liquidity"]),
                next_yes_price=float(row["next_yes_price"]),
            )
            for row in reader
        ]


def load_strategy(strategy_module: str) -> ModuleType:
    """Import a strategy module by dotted path."""
    module = importlib.import_module(strategy_module)
    if not hasattr(module, "generate_orders"):
        raise AttributeError(f"{strategy_module} must define generate_orders(snapshot)")
    return module


def run_backtest(
    strategy_module: str,
    data_path: Path = DEFAULT_DATA_PATH,
) -> tuple[list[Trade], dict[str, float | int]]:
    """Run a strategy over fixed data and return trades plus metrics."""
    strategy = load_strategy(strategy_module)
    snapshots = load_snapshots(data_path)
    trades: list[Trade] = []
    order_count = 0

    for snapshot in snapshots:
        orders = strategy.generate_orders(snapshot)
        order_count += len(orders)
        for order in orders:
            trade = maybe_fill_order(snapshot, order)
            if trade is not None:
                trades.append(trade)

    return trades, calculate_metrics(trades, order_count)


def maybe_fill_order(snapshot: MarketSnapshot, order: StrategyOrder) -> Trade | None:
    """Fill an order deterministically when liquidity and limit constraints pass."""
    if order.side != "YES":
        raise ValueError("V0 only supports YES orders")
    if snapshot.liquidity < order.stake:
        return None

    slippage = deterministic_slippage(snapshot)
    fill_price = round(min(0.99, snapshot.yes_price + slippage), 6)
    if fill_price > order.limit_price + 0.01:
        return None

    quantity = order.stake / fill_price
    pnl = (snapshot.outcome - fill_price) * quantity
    return Trade(
        timestamp=snapshot.timestamp,
        market_id=order.market_id,
        side=order.side,
        requested_price=round(order.limit_price, 6),
        fill_price=fill_price,
        stake=round(order.stake, 6),
        quantity=round(quantity, 6),
        outcome=snapshot.outcome,
        pnl=round(pnl, 6),
        slippage=round(fill_price - order.limit_price, 6),
        reason=order.reason,
    )


def deterministic_slippage(snapshot: MarketSnapshot) -> float:
    """Return a small deterministic price impact from visible liquidity."""
    liquidity_component = min(0.004, 1.0 / max(snapshot.liquidity, 1.0))
    movement_component = max(0.0, snapshot.next_yes_price - snapshot.yes_price) * 0.05
    return round(0.001 + liquidity_component + movement_component, 6)
