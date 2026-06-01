"""Run the full deterministic V0 strategy evaluation loop."""

from __future__ import annotations

import csv
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from backtester.schema import Trade
from backtester.simulate import run_backtest
from orchestrator.config import load_project_config
from orchestrator.experiment_index import append_experiment_index
from orchestrator.git_utils import strategy_diff
from orchestrator.policy_gate import evaluate_policy
from reports.generate_report import generate_report


def run_pipeline(
    *,
    run_id: str | None = None,
    experiments_dir: Path = Path("experiments"),
    data_path: Path | None = None,
) -> dict[str, object]:
    """Execute the V0 pipeline and write all experiment artifacts."""
    config = load_project_config()
    active_run_id = run_id or os.environ.get("SUAN_RUN_ID") or make_run_id()
    run_dir = experiments_dir / active_run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    active_data_path = data_path or Path(config.datasets["validation"])

    trades_before, metrics_before = run_and_write(
        strategy_name=config.baseline_strategy_module,
        data_path=active_data_path,
        metrics_path=run_dir / "metrics_before.json",
        trades_path=run_dir / "trades_before.csv",
        report_path=run_dir / "report_before.md",
    )

    trades_after, metrics_after = run_and_write(
        strategy_name=config.current_strategy_module,
        data_path=active_data_path,
        metrics_path=run_dir / "metrics_after.json",
        trades_path=run_dir / "trades_after.csv",
        report_path=run_dir / "report_after.md",
    )

    decision = evaluate_policy(metrics_before, metrics_after)
    write_json(run_dir / "decision.json", decision)
    (run_dir / "patch.diff").write_text(strategy_diff(), encoding="utf-8")
    append_experiment_index(
        experiments_dir=experiments_dir,
        record={
            "kind": "single_run",
            "run_id": active_run_id,
            "status": "accepted" if decision["accepted"] else "rejected",
            "accepted": decision["accepted"],
            "ev_before": metrics_before["ev"],
            "ev_after": metrics_after["ev"],
            "trade_count_before": metrics_before["trade_count"],
            "trade_count_after": metrics_after["trade_count"],
        },
    )

    return {
        "run_id": active_run_id,
        "run_dir": str(run_dir),
        "accepted": decision["accepted"],
        "reasons": decision["reasons"],
        "before_trade_count": len(trades_before),
        "after_trade_count": len(trades_after),
    }


def run_and_write(
    *,
    strategy_name: str,
    data_path: Path,
    metrics_path: Path,
    trades_path: Path,
    report_path: Path,
) -> tuple[list[Trade], dict[str, float | int]]:
    """Run one strategy and write its metrics, trades, and report."""
    trades, metrics = run_backtest(strategy_name, data_path)
    write_json(metrics_path, metrics)
    write_trades_csv(trades_path, trades)
    generate_report(
        strategy_name=strategy_name,
        metrics=metrics,
        trade_count=len(trades),
        output_path=report_path,
    )
    return trades, metrics


def write_json(path: Path, payload: object) -> None:
    """Write stable, human-readable JSON."""
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_trades_csv(path: Path, trades: list[Trade]) -> None:
    """Write filled trades to CSV, including a header for empty trade sets."""
    fieldnames = [
        "timestamp",
        "market_id",
        "side",
        "requested_price",
        "fill_price",
        "stake",
        "quantity",
        "outcome",
        "pnl",
        "slippage",
        "reason",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for trade in trades:
            writer.writerow(trade.to_dict())


def make_run_id() -> str:
    """Create a sortable run id."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def main() -> None:
    """CLI entrypoint for `python -m orchestrator.run_loop`."""
    summary = run_pipeline()
    print(f"Run directory: {summary['run_dir']}")
    print(f"Accepted: {summary['accepted']}")
    if summary["reasons"]:
        print("Reasons:")
        for reason in summary["reasons"]:
            print(f"- {reason}")
    print(
        "Trades before/after: "
        f"{summary['before_trade_count']}/{summary['after_trade_count']}"
    )


if __name__ == "__main__":
    main()
