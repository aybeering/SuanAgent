"""Inspect experiment history and artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from orchestrator.experiment_index import read_experiment_index, recent_experiments
from orchestrator.outcome_memory import recent_outcomes


def list_experiments(
    *,
    experiments_dir: Path = Path("experiments"),
    limit: int = 10,
) -> list[dict[str, object]]:
    """Return recent experiment records."""
    return recent_experiments(experiments_dir=experiments_dir, limit=limit)


def show_experiment(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return a compact summary for a run directory."""
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")

    manifest_path = run_dir / "manifest.json"
    decision_path = run_dir / "decision.json"
    if manifest_path.exists():
        manifest = load_json(manifest_path)
        return {
            "kind": "iteration_loop",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "summary_path": str(run_dir / "summary.md"),
            "manifest": manifest,
        }
    if decision_path.exists():
        decision = load_json(decision_path)
        return {
            "kind": "single_run",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "summary_path": str(run_dir / "summary.md"),
            "decision": decision,
        }
    raise FileNotFoundError(f"No manifest.json or decision.json for run: {run_id}")


def summarize_experiments(
    *,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return aggregate counts for local experiment history."""
    records = read_experiment_index(experiments_dir)
    by_kind: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for record in records:
        kind = str(record.get("kind", "unknown"))
        status = str(record.get("status", "unknown"))
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1

    leaderboard = experiment_leaderboard(experiments_dir=experiments_dir, limit=1)
    return {
        "total_runs": len(records),
        "by_kind": by_kind,
        "by_status": by_status,
        "best_run": leaderboard[0] if leaderboard else None,
    }


def experiment_leaderboard(
    *,
    experiments_dir: Path = Path("experiments"),
    limit: int = 10,
) -> list[dict[str, object]]:
    """Rank experiments by validation EV improvement."""
    rows = [
        experiment_score(record=record, experiments_dir=experiments_dir)
        for record in read_experiment_index(experiments_dir)
    ]
    rows.sort(
        key=lambda row: (
            float(row.get("ev_delta", 0.0)),
            str(row.get("created_at", "")),
        ),
        reverse=True,
    )
    return rows[: max(limit, 0)]


def experiment_score(
    *,
    record: dict[str, object],
    experiments_dir: Path,
) -> dict[str, object]:
    """Build one leaderboard row from index and artifact data."""
    kind = str(record.get("kind", "unknown"))
    if kind == "single_run":
        ev_before = float(record.get("ev_before", 0.0))
        ev_after = float(record.get("ev_after", 0.0))
        return {
            "run_id": record.get("run_id"),
            "kind": kind,
            "status": record.get("status"),
            "created_at": record.get("created_at"),
            "ev_before": ev_before,
            "ev_after": ev_after,
            "ev_delta": round(ev_after - ev_before, 6),
            "trade_count_before": record.get("trade_count_before"),
            "trade_count_after": record.get("trade_count_after"),
        }

    if kind == "iteration_loop":
        run_id = str(record.get("run_id", ""))
        manifest_path = experiments_dir / run_id / "manifest.json"
        best_round: dict[str, object] | None = None
        best_delta = 0.0
        if manifest_path.exists():
            manifest = load_json(manifest_path)
            for round_payload in manifest.get("rounds", []):
                if not isinstance(round_payload, dict):
                    continue
                before = float(round_payload.get("validation_ev_before", 0.0))
                after = float(round_payload.get("validation_ev_after", 0.0))
                delta = round(after - before, 6)
                if best_round is None or delta > best_delta:
                    best_round = round_payload
                    best_delta = delta
        return {
            "run_id": record.get("run_id"),
            "kind": kind,
            "status": record.get("status"),
            "created_at": record.get("created_at"),
            "completed_rounds": record.get("completed_rounds"),
            "accepted_round": record.get("accepted_round"),
            "ev_delta": best_delta,
            "best_round": best_round.get("round_id") if best_round else None,
        }

    return {
        "run_id": record.get("run_id"),
        "kind": kind,
        "status": record.get("status"),
        "created_at": record.get("created_at"),
        "ev_delta": 0.0,
    }


def load_json(path: Path) -> dict[str, object]:
    """Load a JSON object from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    """CLI entrypoint for experiment inspection."""
    parser = argparse.ArgumentParser(description="Inspect SuanAgent experiments.")
    parser.add_argument(
        "--experiments-dir",
        type=Path,
        default=Path("experiments"),
        help="Directory containing experiment artifacts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List recent experiments.")
    list_parser.add_argument("--limit", type=int, default=10)

    show_parser = subparsers.add_parser("show", help="Show one experiment.")
    show_parser.add_argument("run_id")

    leaderboard_parser = subparsers.add_parser(
        "leaderboard",
        help="Rank experiments by validation EV improvement.",
    )
    leaderboard_parser.add_argument("--limit", type=int, default=10)

    memory_parser = subparsers.add_parser(
        "memory",
        help="List recent proposal outcome memory records.",
    )
    memory_parser.add_argument("--limit", type=int, default=10)

    subparsers.add_parser("summary", help="Summarize experiment history.")

    args = parser.parse_args()
    if args.command == "list":
        payload = list_experiments(
            experiments_dir=args.experiments_dir,
            limit=args.limit,
        )
    elif args.command == "show":
        payload = show_experiment(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
    elif args.command == "leaderboard":
        payload = experiment_leaderboard(
            experiments_dir=args.experiments_dir,
            limit=args.limit,
        )
    elif args.command == "memory":
        payload = recent_outcomes(
            experiments_dir=args.experiments_dir,
            limit=args.limit,
        )
    else:
        payload = summarize_experiments(experiments_dir=args.experiments_dir)
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
