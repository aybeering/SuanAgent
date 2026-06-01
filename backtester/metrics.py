"""Deterministic V0 metrics.

Metric definitions:

- `total_pnl`: Sum of trade PnL where YES payoff is `outcome` and quantity is
  `stake / fill_price`.
- `ev`: Total PnL divided by total stake deployed.
- `max_drawdown`: Largest peak-to-trough drop in cumulative PnL, divided by
  total stake deployed.
- `trade_count`: Number of filled trades.
- `fill_rate`: Filled trades divided by orders emitted by the strategy.
- `avg_slippage`: Mean absolute difference between requested and fill price.
"""

from __future__ import annotations

from backtester.schema import Trade


METRIC_KEYS = (
    "ev",
    "total_pnl",
    "max_drawdown",
    "trade_count",
    "fill_rate",
    "avg_slippage",
)


def calculate_metrics(trades: list[Trade], order_count: int) -> dict[str, float | int]:
    """Calculate deterministic summary metrics for filled trades."""
    total_pnl = sum(trade.pnl for trade in trades)
    total_stake = sum(trade.stake for trade in trades)
    trade_count = len(trades)
    fill_rate = trade_count / order_count if order_count else 0.0
    avg_slippage = (
        sum(abs(trade.slippage) for trade in trades) / trade_count
        if trade_count
        else 0.0
    )

    peak = 0.0
    cumulative = 0.0
    max_drawdown_cash = 0.0
    for trade in trades:
        cumulative += trade.pnl
        peak = max(peak, cumulative)
        max_drawdown_cash = max(max_drawdown_cash, peak - cumulative)

    max_drawdown = max_drawdown_cash / total_stake if total_stake else 0.0
    ev = total_pnl / total_stake if total_stake else 0.0

    return {
        "ev": round(ev, 6),
        "total_pnl": round(total_pnl, 6),
        "max_drawdown": round(max_drawdown, 6),
        "trade_count": trade_count,
        "fill_rate": round(fill_rate, 6),
        "avg_slippage": round(avg_slippage, 6),
    }
