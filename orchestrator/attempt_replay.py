"""Replay one saved candidate attempt without rerunning the full iteration loop."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

from orchestrator.agent_output_intake import validate_agent_proposal
from orchestrator.failure_taxonomy import (
    attach_failure_metadata,
    normalize_reason_codes,
    probe_reason_codes,
)
from orchestrator.git_manager import GitError, apply_patch, rollback_strategy
from orchestrator.proposal import StrategyProposal
from orchestrator.run_loop import run_and_write


ATTEMPT_REPLAY_SCHEMA_VERSION = "attempt_replay_v1"
DEFAULT_STRATEGY_MODULE = "strategies.current_strategy"


def replay_attempt(
    *,
    attempt_dir: Path,
    repo_root: Path = Path("."),
    output_path: Path | None = None,
    strategy_module: str = DEFAULT_STRATEGY_MODULE,
    run_probe: bool = True,
) -> dict[str, object]:
    """Replay contract validation and optional probe evaluation for one attempt."""
    repo_root = repo_root.resolve()
    attempt_dir = resolve_path(attempt_dir, repo_root)
    round_dir = infer_round_dir(attempt_dir)
    proposal = load_strategy_proposal(attempt_dir / "proposal.json")
    validation = validate_agent_proposal(
        agent_input_path=round_dir / "agent_input.json",
        agent_output_path=attempt_dir / "raw_agent_output.txt",
        proposal=proposal,
        repo_root=repo_root,
    )
    probe = replay_probe(
        proposal=proposal,
        repo_root=repo_root,
        round_dir=round_dir,
        attempt_dir=attempt_dir,
        strategy_module=strategy_module,
        enabled=run_probe and bool(validation["ok"]),
    )
    reason_codes = [
        *validation_reason_codes(validation),
        *probe_reason_codes(
            ok=bool(probe.get("ok", True)),
            error=str(probe.get("error", "")),
        ),
    ]
    report = attach_failure_metadata({
        "schema_version": ATTEMPT_REPLAY_SCHEMA_VERSION,
        "ok": bool(validation["ok"]) and bool(probe.get("ok", True)),
        "attempt_dir": str(attempt_dir),
        "round_dir": str(round_dir),
        "strategy_module": strategy_module,
        "validation": validation,
        "probe": probe,
    }, reason_codes)
    destination = output_path or attempt_dir / "attempt_replay.json"
    write_json(destination, report)
    return report


def replay_probe(
    *,
    proposal: StrategyProposal,
    repo_root: Path,
    round_dir: Path,
    attempt_dir: Path,
    strategy_module: str,
    enabled: bool,
) -> dict[str, object]:
    """Run one saved attempt against the round probe data when possible."""
    probe_data_path = round_dir / "probe_data.csv"
    if not enabled:
        return skipped_probe("disabled_or_validation_failed")
    if not proposal.applicable:
        return skipped_probe("proposal_not_applicable")
    if not probe_data_path.exists():
        return skipped_probe("probe_data_missing")

    metrics_path = attempt_dir / "attempt_replay_probe_metrics.json"
    trades_path = attempt_dir / "attempt_replay_probe_trades.csv"
    report_path = attempt_dir / "attempt_replay_probe_report.md"
    try:
        apply_patch(repo_root, proposal.patch_diff)
        clear_strategy_import(repo_root, strategy_module)
        _trades, metrics = run_and_write(
            strategy_name=strategy_module,
            data_path=probe_data_path,
            metrics_path=metrics_path,
            trades_path=trades_path,
            report_path=report_path,
        )
    except Exception as exc:
        return attach_failure_metadata(
            {"ran": True, "ok": False, "error": str(exc)},
            probe_reason_codes(ok=False, error=str(exc)),
        )
    finally:
        try:
            rollback_strategy(repo_root)
        except GitError:
            pass
        clear_strategy_import(repo_root, strategy_module)

    return attach_failure_metadata({
        "ran": True,
        "ok": True,
        "metrics": metrics,
        "artifacts": {
            "metrics": str(metrics_path),
            "trades": str(trades_path),
            "report": str(report_path),
        },
    }, [])


def skipped_probe(reason: str) -> dict[str, object]:
    """Return a non-failing skipped probe payload."""
    return attach_failure_metadata(
        {"ran": False, "ok": True, "reason": reason},
        [],
    )


def validation_reason_codes(validation: dict[str, object]) -> list[dict[str, str]]:
    """Return validation reason-code rows from a saved validation payload."""
    return normalize_reason_codes(validation.get("reason_codes", []))


def infer_round_dir(attempt_dir: Path) -> Path:
    """Return the round directory for an agent_attempts/attempt_xxx directory."""
    if attempt_dir.parent.name != "agent_attempts":
        raise ValueError(f"Attempt directory must be under agent_attempts/: {attempt_dir}")
    return attempt_dir.parent.parent


def load_strategy_proposal(path: Path) -> StrategyProposal:
    """Load a StrategyProposal from attempt proposal JSON."""
    payload = load_json_object(path)
    return StrategyProposal(**payload)  # type: ignore[arg-type]


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root when needed."""
    return path if path.is_absolute() else repo_root / path


def write_json(path: Path, payload: object) -> None:
    """Write deterministic JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def clear_strategy_import(repo_root: Path, strategy_module: str) -> None:
    """Force Python to reload the strategy module after patch/rollback."""
    sys.modules.pop(strategy_module, None)
    if strategy_module.startswith("strategies."):
        module_name = strategy_module.rsplit(".", maxsplit=1)[-1]
        for pyc_path in (repo_root / "strategies" / "__pycache__").glob(
            f"{module_name}*.pyc"
        ):
            pyc_path.unlink(missing_ok=True)
    importlib.invalidate_caches()


def main() -> None:
    """CLI entrypoint for attempt replay."""
    args = parse_args()
    report = replay_attempt(
        attempt_dir=args.attempt_dir,
        repo_root=args.repo_root,
        output_path=args.output,
        strategy_module=args.strategy_module,
        run_probe=not args.skip_probe,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for attempt replay."""
    parser = argparse.ArgumentParser(
        description="Replay one saved candidate attempt validation and probe check.",
    )
    parser.add_argument("attempt_dir", type=Path, help="Path to agent_attempts/attempt_xxx.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root used for patch checks and probe replay.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write attempt_replay.json.",
    )
    parser.add_argument(
        "--strategy-module",
        default=DEFAULT_STRATEGY_MODULE,
        help="Import path for the candidate strategy module.",
    )
    parser.add_argument(
        "--skip-probe",
        action="store_true",
        help="Only replay contract and patch validation.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
