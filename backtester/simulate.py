"""Deterministic CSV backtester for V0 strategies."""

from __future__ import annotations

import csv
import importlib
import math
import sys
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
    clear_strategy_cache(strategy_module)
    module = importlib.import_module(strategy_module)
    if not hasattr(module, "generate_orders"):
        raise AttributeError(f"{strategy_module} must define generate_orders(snapshot)")
    return module


def clear_strategy_cache(strategy_module: str) -> None:
    """Clear module and bytecode caches before loading a strategy file."""
    sys.modules.pop(strategy_module, None)
    if strategy_module.startswith("strategies."):
        module_name = strategy_module.rsplit(".", maxsplit=1)[-1]
        for pyc_path in Path("strategies/__pycache__").glob(f"{module_name}*.pyc"):
            pyc_path.unlink(missing_ok=True)
    importlib.invalidate_caches()


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
        orders = validate_strategy_orders(snapshot, strategy.generate_orders(snapshot))
        order_count += len(orders)
        for order in orders:
            trade = maybe_fill_order(snapshot, order)
            if trade is not None:
                trades.append(trade)

    return trades, calculate_metrics(trades, order_count)


def validate_strategy_orders(
    snapshot: MarketSnapshot,
    orders: object,
) -> list[StrategyOrder]:
    """Validate strategy output before simulation accepts it."""
    if not isinstance(orders, list):
        raise TypeError("generate_orders(snapshot) must return a list")

    validated: list[StrategyOrder] = []
    for order in orders:
        if not isinstance(order, StrategyOrder):
            raise TypeError("strategy orders must be StrategyOrder instances")
        if order.market_id != snapshot.market_id:
            raise ValueError("strategy order market_id must match the snapshot")
        if order.side != "YES":
            raise ValueError("V0.5 only supports YES orders")
        if not math.isfinite(order.limit_price) or not 0.0 < order.limit_price < 1.0:
            raise ValueError("strategy order limit_price must be between 0 and 1")
        if not math.isfinite(order.stake) or order.stake <= 0.0:
            raise ValueError("strategy order stake must be positive")
        validated.append(order)
    return validated


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
