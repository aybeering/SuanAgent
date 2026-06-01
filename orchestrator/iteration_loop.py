"""Multi-round self-iteration loop skeleton."""

from __future__ import annotations

import importlib
import json
import os
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from agents.strategy_modifier_stub import propose_strategy_change
from backtester.simulate import DEFAULT_DATA_PATH
from orchestrator.git_manager import (
    STRATEGY_PATH,
    GitError,
    apply_patch,
    assert_strategy_clean,
    commit_strategy,
    current_commit,
    ensure_git_repo,
    rollback_strategy,
)
from orchestrator.policy_gate import evaluate_policy
from orchestrator.run_loop import CURRENT_STRATEGY, run_and_write, write_json


MAX_ROUNDS = 5


def run_iteration_loop(
    *,
    run_id: str | None = None,
    max_rounds: int = MAX_ROUNDS,
    repo_root: Path = Path("."),
    experiments_dir: Path | None = None,
    data_path: Path | None = None,
    policy_rules: dict[str, float | int] | None = None,
) -> dict[str, object]:
    """Run the V0.5 self-iteration skeleton until accepted or max rounds."""
    repo_root = repo_root.resolve()
    active_run_id = run_id or os.environ.get("SUAN_RUN_ID") or make_run_id()
    active_experiments_dir = (
        repo_root / "experiments" if experiments_dir is None else experiments_dir
    )
    active_data_path = repo_root / DEFAULT_DATA_PATH if data_path is None else data_path
    run_dir = active_experiments_dir / active_run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    manifest: dict[str, object] = {
        "run_id": active_run_id,
        "status": "failed",
        "max_rounds": max_rounds,
        "completed_rounds": 0,
        "accepted_round": None,
        "final_strategy_commit": None,
        "rounds": [],
    }

    try:
        ensure_git_repo(repo_root)
        assert_strategy_clean(repo_root)

        with repo_context(repo_root):
            for round_index in range(1, max_rounds + 1):
                round_id = f"round_{round_index:03d}"
                round_dir = run_dir / round_id
                round_dir.mkdir(parents=True, exist_ok=False)

                round_summary = run_round(
                    repo_root=repo_root,
                    run_id=active_run_id,
                    round_id=round_id,
                    round_index=round_index,
                    round_dir=round_dir,
                    data_path=active_data_path,
                    policy_rules=policy_rules,
                )
                manifest["completed_rounds"] = round_index
                manifest["rounds"].append(round_summary)  # type: ignore[union-attr]
                write_json(run_dir / "manifest.json", manifest)

                if round_summary["accepted"]:
                    manifest["status"] = "accepted"
                    manifest["accepted_round"] = round_id
                    manifest["final_strategy_commit"] = commit_strategy(
                        repo_root, run_id=active_run_id, round_id=round_id
                    )
                    write_json(run_dir / "manifest.json", manifest)
                    return manifest

                rollback_strategy(repo_root)
                clear_strategy_import(repo_root)

        manifest["status"] = "stopped_max_rounds"
        manifest["final_strategy_commit"] = current_commit(repo_root)
        write_json(run_dir / "manifest.json", manifest)
        return manifest
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        write_json(run_dir / "manifest.json", manifest)
        raise


def run_round(
    *,
    repo_root: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    round_dir: Path,
    data_path: Path,
    policy_rules: dict[str, float | int] | None,
) -> dict[str, object]:
    """Run one proposal/apply/evaluate round."""
    clear_strategy_import(repo_root)
    trades_before, metrics_before = run_and_write(
        strategy_name=CURRENT_STRATEGY,
        data_path=data_path,
        metrics_path=round_dir / "metrics_before.json",
        trades_path=round_dir / "trades_before.csv",
        report_path=round_dir / "report_before.md",
    )

    proposal = propose_strategy_change(
        report_path=round_dir / "report_before.md",
        target_file=repo_root / STRATEGY_PATH,
        round_index=round_index,
        repo_root=repo_root,
    )
    write_json(round_dir / "proposal.json", proposal.to_dict())
    (round_dir / "agent_response.txt").write_text(
        proposal.raw_response + "\n", encoding="utf-8"
    )
    (round_dir / "patch.diff").write_text(proposal.patch_diff, encoding="utf-8")

    apply_error = ""
    if proposal.applicable:
        try:
            apply_patch(repo_root, proposal.patch_diff)
        except GitError as exc:
            apply_error = str(exc)
    else:
        apply_error = proposal.rejection_reason

    clear_strategy_import(repo_root)
    trades_after, metrics_after = run_and_write(
        strategy_name=CURRENT_STRATEGY,
        data_path=data_path,
        metrics_path=round_dir / "metrics_after.json",
        trades_path=round_dir / "trades_after.csv",
        report_path=round_dir / "report_after.md",
    )

    decision = evaluate_policy(metrics_before, metrics_after, policy_rules)
    if apply_error:
        decision["accepted"] = False
        decision["reasons"] = [apply_error, *decision["reasons"]]  # type: ignore[index]
    write_json(round_dir / "decision.json", decision)

    return {
        "round_id": round_id,
        "run_id": run_id,
        "accepted": decision["accepted"],
        "reasons": decision["reasons"],
        "proposal_applicable": proposal.applicable,
        "before_trade_count": len(trades_before),
        "after_trade_count": len(trades_after),
    }


def clear_strategy_import(repo_root: Path) -> None:
    """Force Python to load the current strategy from disk after patches."""
    sys.modules.pop(CURRENT_STRATEGY, None)
    for pyc_path in (repo_root / "strategies" / "__pycache__").glob(
        "current_strategy*.pyc"
    ):
        pyc_path.unlink(missing_ok=True)
    importlib.invalidate_caches()


@contextmanager
def repo_context(repo_root: Path) -> Iterator[None]:
    """Temporarily run with repo_root as cwd and first import path."""
    previous_cwd = Path.cwd()
    repo_root_str = str(repo_root)
    added_path = False
    if not sys.path or sys.path[0] != repo_root_str:
        sys.path.insert(0, repo_root_str)
        added_path = True
    os.chdir(repo_root)
    try:
        yield
    finally:
        os.chdir(previous_cwd)
        if added_path:
            try:
                sys.path.remove(repo_root_str)
            except ValueError:
                pass


def make_run_id() -> str:
    """Create a sortable run id."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def main() -> None:
    """CLI entrypoint for `python -m orchestrator.iteration_loop`."""
    manifest = run_iteration_loop()
    print(f"Run id: {manifest['run_id']}")
    print(f"Status: {manifest['status']}")
    print(f"Completed rounds: {manifest['completed_rounds']}")
    print(f"Accepted round: {manifest['accepted_round']}")
    print(f"Final strategy commit: {manifest['final_strategy_commit']}")


if __name__ == "__main__":
    main()
