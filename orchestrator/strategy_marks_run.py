"""CLI and runner for the isolated dead-strategy marks workspace."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from backtester.schema import StrategyOrder, Trade
from backtester.simulate import (
    load_snapshots,
    maybe_fill_order,
    validate_strategy_orders,
)
from orchestrator.config import load_project_config
from orchestrator.schema_validation import validate_json_file, validate_json_payload
from orchestrator.strategy_marks_workspace import (
    ALLOWED_OUTPUT_PATHS,
    INPUT_MARKET_CSV,
    INPUT_RUN_REQUEST,
    assert_workspace_mutations_allowed,
    create_strategy_marks_workspace,
    file_sha256,
    load_workspace_manifest,
    strategy_marks_workspace_path,
    verify_input_digests,
    write_json,
)
from orchestrator.workspace_manager import workspace_snapshot
from reports.generate_marks_view import generate_marks_view


MARK_POINTS_SCHEMA_VERSION = "strategy_mark_points_v1"
RUN_RECEIPT_SCHEMA_VERSION = "strategy_marks_run_receipt_v1"
MARK_SOURCE = "dead_strategy"

MARK_POINTS_JSON = "output/mark_points.json"
MARK_POINTS_CSV = "output/mark_points.csv"
MARKS_VIEW_HTML = "output/marks_view.html"
RUN_RECEIPT_JSON = "output/run_receipt.json"

MARK_CSV_FIELDS = (
    "mark_id",
    "timestamp",
    "market_id",
    "side",
    "action",
    "price",
    "kind",
    "stake",
    "quantity",
    "reason",
    "source",
)


def main(argv: list[str] | None = None) -> int:
    """Run the dead-strategy marks workspace from the repository root."""
    parser = argparse.ArgumentParser(
        description="Create and run an isolated dead-strategy marks workspace.",
    )
    parser.add_argument("--run-id", default="strategy-marks-demo")
    parser.add_argument("--workspace-id", default="")
    parser.add_argument(
        "--split",
        choices=("train", "validation", "holdout"),
        default="validation",
    )
    parser.add_argument("--config", default="config/default.json")
    parser.add_argument(
        "--workspace-root",
        default="workspaces",
        help="Root directory for isolated workspaces.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    config = load_project_config(repo_root=repo_root, config_path=Path(args.config))
    market_csv = config.dataset_path(repo_root, args.split)
    workspace_id = args.workspace_id or f"{args.split}-dead"
    workspace_root = Path(args.workspace_root)
    if not workspace_root.is_absolute():
        workspace_root = repo_root / workspace_root

    result = run_strategy_marks(
        repo_root=repo_root,
        workspace_root=workspace_root,
        run_id=args.run_id,
        workspace_id=workspace_id,
        split=args.split,
        market_csv_source=market_csv,
    )
    print(json.dumps(result["receipt"], indent=2, sort_keys=True))
    return 0 if result["receipt"]["status"] == "accepted" else 1


def run_strategy_marks(
    *,
    repo_root: Path,
    workspace_root: Path,
    run_id: str,
    workspace_id: str,
    split: str,
    market_csv_source: Path,
    strategy_module: str = "strategies/current_strategy.py",
) -> dict[str, Any]:
    """Create a workspace, export mark points, render HTML, and write a receipt."""
    workspace_path = create_strategy_marks_workspace(
        repo_root=repo_root,
        workspace_root=workspace_root,
        run_id=run_id,
        workspace_id=workspace_id,
        split=split,
        market_csv_source=market_csv_source,
        strategy_module=strategy_module,
    )
    before_snapshot = workspace_snapshot(workspace_path)
    manifest = load_workspace_manifest(workspace_path)
    input_ok, input_errors = verify_input_digests(
        workspace_path=workspace_path,
        expected=manifest["input_digests"],
    )

    marks: list[dict[str, Any]] = []
    mark_payload: dict[str, Any] = {}
    failure_reason = ""
    try:
        if not input_ok:
            raise RuntimeError("; ".join(input_errors))
        validate_workspace_inputs(repo_root=repo_root, workspace_path=workspace_path)
        run_request = json.loads(
            (workspace_path / INPUT_RUN_REQUEST).read_text(encoding="utf-8")
        )
        strategy_rel = str(run_request["strategy_module"])
        strategy_path = workspace_path / strategy_rel
        strategy = load_strategy_from_path(strategy_path)
        snapshots = load_snapshots(workspace_path / INPUT_MARKET_CSV)
        marks = collect_mark_points(strategy=strategy, snapshots=snapshots)
        mark_payload = build_mark_points_payload(
            run_id=run_id,
            workspace_id=workspace_id,
            split=split,
            input_digest=combined_input_digest(manifest["input_digests"]),
            strategy_sha256=file_sha256(strategy_path),
            marks=marks,
        )
        schema_errors = validate_json_payload(
            payload=mark_payload,
            schema=load_schema(
                repo_root / "schemas/strategy_mark_points.schema.json"
            ),
            schema_dir=repo_root / "schemas",
        )
        if schema_errors:
            raise RuntimeError("; ".join(schema_errors))

        write_json(workspace_path / MARK_POINTS_JSON, mark_payload)
        write_mark_points_csv(workspace_path / MARK_POINTS_CSV, marks)
        generate_marks_view(
            output_path=workspace_path / MARKS_VIEW_HTML,
            run_id=run_id,
            workspace_id=workspace_id,
            split=split,
            market_csv_path=workspace_path / INPUT_MARKET_CSV,
            mark_points=mark_payload,
        )
    except Exception as exc:  # noqa: BLE001 - receipt must capture runner failures
        failure_reason = str(exc)

    mutation_errors = assert_workspace_mutations_allowed(
        workspace_path=workspace_path,
        before_snapshot=before_snapshot,
    )
    status = "accepted"
    if failure_reason or mutation_errors or not input_ok:
        status = "rejected"
        if not failure_reason and mutation_errors:
            failure_reason = "; ".join(mutation_errors)
        elif not failure_reason and not input_ok:
            failure_reason = "; ".join(input_errors)

    receipt = build_run_receipt(
        run_id=run_id,
        workspace_id=workspace_id,
        workspace_path=workspace_path,
        status=status,
        input_digest_ok=input_ok,
        mutation_errors=mutation_errors,
        mark_count=len(marks),
        failure_reason=failure_reason,
    )
    write_json(workspace_path / RUN_RECEIPT_JSON, receipt)
    validate_receipt = validate_json_file(
        payload_path=workspace_path / RUN_RECEIPT_JSON,
        schema_path=repo_root / "schemas/strategy_marks_run_receipt.schema.json",
    )
    if validate_receipt:
        receipt["status"] = "rejected"
        receipt["failure_reason"] = "; ".join(validate_receipt)
        write_json(workspace_path / RUN_RECEIPT_JSON, receipt)

    return {
        "workspace_path": workspace_path,
        "receipt": receipt,
        "mark_points": mark_payload,
        "allowed_output_paths": list(ALLOWED_OUTPUT_PATHS),
    }


def validate_workspace_inputs(*, repo_root: Path, workspace_path: Path) -> None:
    """Validate packed input contracts before running the dead strategy."""
    request_errors = validate_json_file(
        payload_path=workspace_path / INPUT_RUN_REQUEST,
        schema_path=repo_root / "schemas/strategy_marks_run_request.schema.json",
    )
    if request_errors:
        raise RuntimeError("; ".join(request_errors))
    manifest_errors = validate_json_file(
        payload_path=workspace_path / "workspace_manifest.json",
        schema_path=repo_root
        / "schemas/strategy_marks_workspace_manifest.schema.json",
    )
    if manifest_errors:
        raise RuntimeError("; ".join(manifest_errors))


def load_strategy_from_path(strategy_path: Path) -> ModuleType:
    """Load a strategy module from an isolated workspace file path."""
    if not strategy_path.exists():
        raise FileNotFoundError(f"Missing strategy module: {strategy_path}")
    module_name = f"strategy_marks_{strategy_path.stem}_{file_sha256(strategy_path)[:12]}"
    spec = importlib.util.spec_from_file_location(module_name, strategy_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load strategy from {strategy_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "generate_orders"):
        raise AttributeError(f"{strategy_path} must define generate_orders(snapshot)")
    return module


def collect_mark_points(
    *,
    strategy: ModuleType,
    snapshots: list[Any],
) -> list[dict[str, Any]]:
    """Collect deterministic signal and fill marks from one dead strategy run."""
    marks: list[dict[str, Any]] = []
    for snap_index, snapshot in enumerate(snapshots):
        orders = validate_strategy_orders(snapshot, strategy.generate_orders(snapshot))
        for order_index, order in enumerate(orders):
            signal_id = f"signal-{snap_index:05d}-{order_index:03d}"
            marks.append(mark_from_order(order=order, snapshot=snapshot, mark_id=signal_id))
            trade = maybe_fill_order(snapshot, order)
            if trade is not None:
                fill_id = f"fill-{snap_index:05d}-{order_index:03d}"
                marks.append(mark_from_trade(trade=trade, mark_id=fill_id))
    return marks


def mark_from_order(
    *,
    order: StrategyOrder,
    snapshot: Any,
    mark_id: str,
) -> dict[str, Any]:
    """Map one strategy order to a signal mark point."""
    action = "enter" if order.side == "YES" else "exit"
    return {
        "mark_id": mark_id,
        "timestamp": snapshot.timestamp,
        "market_id": order.market_id,
        "side": order.side,
        "action": action,
        "price": round(float(order.limit_price), 6),
        "kind": "signal",
        "stake": round(float(order.stake), 6),
        "quantity": 0.0,
        "reason": order.reason,
        "source": MARK_SOURCE,
    }


def mark_from_trade(*, trade: Trade, mark_id: str) -> dict[str, Any]:
    """Map one filled trade to a fill mark point."""
    action = "buy" if trade.side == "YES" else "sell"
    return {
        "mark_id": mark_id,
        "timestamp": trade.timestamp,
        "market_id": trade.market_id,
        "side": trade.side,
        "action": action,
        "price": round(float(trade.fill_price), 6),
        "kind": "fill",
        "stake": round(float(trade.stake), 6),
        "quantity": round(float(trade.quantity), 6),
        "reason": trade.reason,
        "source": MARK_SOURCE,
    }


def build_mark_points_payload(
    *,
    run_id: str,
    workspace_id: str,
    split: str,
    input_digest: str,
    strategy_sha256: str,
    marks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the authoritative mark-points contract payload."""
    return {
        "schema_version": MARK_POINTS_SCHEMA_VERSION,
        "run_id": run_id,
        "workspace_id": workspace_id,
        "split": split,
        "source": MARK_SOURCE,
        "input_digest": input_digest,
        "strategy_sha256": strategy_sha256,
        "mark_count": len(marks),
        "marks": marks,
    }


def write_mark_points_csv(path: Path, marks: list[dict[str, Any]]) -> Path:
    """Write a flat CSV mirror of mark points."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(MARK_CSV_FIELDS))
        writer.writeheader()
        for mark in marks:
            writer.writerow({field: mark.get(field, "") for field in MARK_CSV_FIELDS})
    return path


def build_run_receipt(
    *,
    run_id: str,
    workspace_id: str,
    workspace_path: Path,
    status: str,
    input_digest_ok: bool,
    mutation_errors: tuple[str, ...],
    mark_count: int,
    failure_reason: str,
) -> dict[str, Any]:
    """Build the run receipt after output writes."""
    receipt: dict[str, Any] = {
        "schema_version": RUN_RECEIPT_SCHEMA_VERSION,
        "run_id": run_id,
        "workspace_id": workspace_id,
        "status": status,
        "workspace_path": str(workspace_path.resolve()),
        "input_digest_ok": input_digest_ok,
        "mutation_errors": list(mutation_errors),
        "artifact_sha256": {
            "mark_points_json": optional_file_sha256(workspace_path / MARK_POINTS_JSON),
            "mark_points_csv": optional_file_sha256(workspace_path / MARK_POINTS_CSV),
            "marks_view_html": optional_file_sha256(workspace_path / MARKS_VIEW_HTML),
        },
        "mark_count": mark_count,
    }
    if failure_reason:
        receipt["failure_reason"] = failure_reason
    return receipt


def optional_file_sha256(path: Path) -> str:
    """Return a file digest or empty string when missing."""
    if not path.exists():
        return ""
    return file_sha256(path)


def combined_input_digest(input_digests: dict[str, str]) -> str:
    """Return one stable digest over the packed input digest map."""
    payload = json.dumps(input_digests, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_schema(path: Path) -> dict[str, Any]:
    """Load a local JSON schema document."""
    return json.loads(path.read_text(encoding="utf-8"))


# Re-export for tests that patch workspace creation paths.
resolve_workspace_path = strategy_marks_workspace_path


if __name__ == "__main__":
    raise SystemExit(main())
