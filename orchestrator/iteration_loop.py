"""Multi-round self-iteration loop skeleton."""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from agents.modifier_adapter import StrategyModifier
from agents.registry import get_strategy_modifier
from orchestrator.agent_context import write_agent_context
from orchestrator.config import ProjectConfig, load_project_config
from orchestrator.experiment_index import append_experiment_index
from orchestrator.git_manager import (
    GitError,
    apply_patch,
    assert_strategy_clean,
    check_patch,
    commit_strategy,
    current_commit,
    ensure_git_repo,
    rollback_strategy,
)
from orchestrator.outcome_memory import (
    append_outcome_memory,
    build_outcome_record,
    memory_filter_rejection_reason,
)
from orchestrator.policy_gate import evaluate_policy
from orchestrator.preflight import run_preflight
from orchestrator.proposal import StrategyProposal, annotate_proposal_quality
from orchestrator.run_loop import run_and_write, write_json
from orchestrator.run_summary import write_iteration_summary


MAX_ROUNDS = 5


def run_iteration_loop(
    *,
    run_id: str | None = None,
    max_rounds: int | None = None,
    repo_root: Path = Path("."),
    experiments_dir: Path | None = None,
    data_path: Path | None = None,
    policy_rules: dict[str, float | int] | None = None,
    config_path: Path | None = None,
    config: ProjectConfig | None = None,
    stop_on_repeated_proposal: bool | None = None,
) -> dict[str, object]:
    """Run the V0.5 self-iteration skeleton until accepted or max rounds."""
    repo_root = repo_root.resolve()
    preflight = run_preflight(repo_root=repo_root, config_path=config_path)
    if config is None and not preflight.ok:
        raise ValueError("Preflight failed: " + "; ".join(preflight.errors))
    active_config = config or load_project_config(repo_root, config_path)
    active_run_id = run_id or os.environ.get("SUAN_RUN_ID") or make_run_id()
    active_experiments_dir = (
        active_config.resolve_path(repo_root, active_config.experiments_dir)
        if experiments_dir is None
        else experiments_dir
    )
    active_max_rounds = max_rounds if max_rounds is not None else active_config.max_rounds
    train_data_path = active_config.dataset_path(repo_root, "train")
    validation_data_path = (
        active_config.dataset_path(repo_root, "validation") if data_path is None else data_path
    )
    holdout_data_path = active_config.dataset_path(repo_root, "holdout")
    active_policy_rules = policy_rules or active_config.policy
    active_stop_on_repeated_proposal = (
        active_config.stop_on_repeated_proposal
        if stop_on_repeated_proposal is None
        else stop_on_repeated_proposal
    )
    modifier = get_strategy_modifier(
        active_config.strategy_modifier,
        active_config.modifier_settings,
    )
    fallback_modifiers = tuple(
        get_strategy_modifier(fallback_name, active_config.modifier_settings)
        for fallback_name in active_config.memory_fallback_modifiers
    )
    strategy_path = Path(active_config.strategy_path)
    strategy_file_path = active_config.resolve_path(repo_root, active_config.strategy_path)
    strategy_module = active_config.current_strategy_module
    run_dir = active_experiments_dir / active_run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    manifest: dict[str, object] = {
        "run_id": active_run_id,
        "status": "failed",
        "max_rounds": active_max_rounds,
        "datasets": {
            "train": str(train_data_path),
            "validation": str(validation_data_path),
            "holdout": str(holdout_data_path),
        },
        "completed_rounds": 0,
        "accepted_round": None,
        "final_strategy_commit": None,
        "stop_on_repeated_proposal": active_stop_on_repeated_proposal,
        "memory_fallback_modifiers": list(active_config.memory_fallback_modifiers),
        "stop_reason": None,
        "rounds": [],
    }

    try:
        ensure_git_repo(repo_root)
        assert_strategy_clean(repo_root, strategy_path)

        with repo_context(repo_root):
            for round_index in range(1, active_max_rounds + 1):
                round_id = f"round_{round_index:03d}"
                round_dir = run_dir / round_id
                round_dir.mkdir(parents=True, exist_ok=False)

                round_summary = run_round(
                    repo_root=repo_root,
                    run_id=active_run_id,
                    round_id=round_id,
                    round_index=round_index,
                    round_dir=round_dir,
                    train_data_path=train_data_path,
                    validation_data_path=validation_data_path,
                    holdout_data_path=holdout_data_path,
                    policy_rules=active_policy_rules,
                    stub_old_threshold=active_config.stub_old_threshold,
                    stub_new_threshold=active_config.stub_new_threshold,
                    strategy_module=strategy_module,
                    strategy_file_path=strategy_file_path,
                    modifier=modifier,
                    fallback_modifiers=fallback_modifiers,
                    memory_failed_patch_threshold=active_config.memory_failed_patch_threshold,
                )
                manifest["completed_rounds"] = round_index
                manifest["rounds"].append(round_summary)  # type: ignore[union-attr]
                write_json(run_dir / "manifest.json", manifest)

                if round_summary["accepted"]:
                    manifest["status"] = "accepted"
                    manifest["accepted_round"] = round_id
                    manifest["final_strategy_commit"] = commit_strategy(
                        repo_root,
                        run_id=active_run_id,
                        round_id=round_id,
                        strategy_path=strategy_path,
                    )
                    write_json(run_dir / "manifest.json", manifest)
                    write_iteration_summary(run_dir=run_dir, manifest=manifest)
                    append_experiment_index(
                        experiments_dir=active_experiments_dir,
                        record=index_record(manifest),
                    )
                    return manifest

                rollback_strategy(repo_root, strategy_path)
                clear_strategy_import(repo_root, strategy_module)

                if (
                    active_stop_on_repeated_proposal
                    and round_summary["proposal_is_repeat"]
                ):
                    manifest["status"] = "stopped_repeated_proposal"
                    manifest["stop_reason"] = (
                        f"{round_id} repeated patch from "
                        f"{round_summary['proposal_repeat_of_round']}"
                    )
                    manifest["final_strategy_commit"] = current_commit(repo_root)
                    write_json(run_dir / "manifest.json", manifest)
                    write_iteration_summary(run_dir=run_dir, manifest=manifest)
                    append_experiment_index(
                        experiments_dir=active_experiments_dir,
                        record=index_record(manifest),
                    )
                    return manifest

        manifest["status"] = "stopped_max_rounds"
        manifest["stop_reason"] = "max_rounds reached"
        manifest["final_strategy_commit"] = current_commit(repo_root)
        write_json(run_dir / "manifest.json", manifest)
        write_iteration_summary(run_dir=run_dir, manifest=manifest)
        append_experiment_index(
            experiments_dir=active_experiments_dir,
            record=index_record(manifest),
        )
        return manifest
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        write_json(run_dir / "manifest.json", manifest)
        write_iteration_summary(run_dir=run_dir, manifest=manifest)
        append_experiment_index(
            experiments_dir=active_experiments_dir,
            record=index_record(manifest),
        )
        raise


def run_round(
    *,
    repo_root: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    round_dir: Path,
    train_data_path: Path,
    validation_data_path: Path,
    holdout_data_path: Path,
    policy_rules: dict[str, float | int] | None,
    stub_old_threshold: str,
    stub_new_threshold: str,
    strategy_module: str,
    strategy_file_path: Path,
    modifier: StrategyModifier,
    fallback_modifiers: tuple[StrategyModifier, ...],
    memory_failed_patch_threshold: int,
) -> dict[str, object]:
    """Run one proposal/apply/evaluate round."""
    clear_strategy_import(repo_root, strategy_module)
    train_trades_before, train_metrics_before = run_and_write(
        strategy_name=strategy_module,
        data_path=train_data_path,
        metrics_path=round_dir / "train_metrics_before.json",
        trades_path=round_dir / "train_trades_before.csv",
        report_path=round_dir / "train_report_before.md",
    )
    trades_before, metrics_before = run_and_write(
        strategy_name=strategy_module,
        data_path=validation_data_path,
        metrics_path=round_dir / "metrics_before.json",
        trades_path=round_dir / "trades_before.csv",
        report_path=round_dir / "report_before.md",
    )
    holdout_trades_before, holdout_metrics_before = run_and_write(
        strategy_name=strategy_module,
        data_path=holdout_data_path,
        metrics_path=round_dir / "holdout_metrics_before.json",
        trades_path=round_dir / "holdout_trades_before.csv",
        report_path=round_dir / "holdout_report_before.md",
    )

    context_path = write_agent_context(
        run_dir=round_dir.parent,
        current_round_id=round_id,
        output_path=round_dir / "agent_context.md",
        memory_path=round_dir.parent.parent / "memory.jsonl",
    )
    (
        proposal,
        memory_filter_reason,
        proposal_attempts,
        selected_attempt,
        primary_memory_filter_reason,
    ) = select_proposal_candidate(
        modifier=modifier,
        fallback_modifiers=fallback_modifiers,
        report_path=round_dir / "train_report_before.md",
        target_file=strategy_file_path,
        round_index=round_index,
        repo_root=repo_root,
        old_threshold=stub_old_threshold,
        new_threshold=stub_new_threshold,
        context_path=context_path,
        run_dir=round_dir.parent,
        current_round_id=round_id,
        experiments_dir=round_dir.parent.parent,
        memory_failed_patch_threshold=memory_failed_patch_threshold,
        run_id=run_id,
    )
    proposal_fallback_used = selected_attempt["role"] != "primary"
    proposal_fallback_reason = (
        str(selected_attempt["selection_reason"]) if proposal_fallback_used else ""
    )

    write_json(round_dir / "proposal_attempts.json", proposal_attempts)
    write_json(round_dir / "proposal.json", proposal.to_dict())
    (round_dir / "agent_response.txt").write_text(
        proposal.raw_response + "\n", encoding="utf-8"
    )
    (round_dir / "patch.diff").write_text(proposal.patch_diff, encoding="utf-8")

    apply_error = ""
    if memory_filter_reason:
        apply_error = memory_filter_reason
    elif proposal.applicable:
        try:
            apply_patch(repo_root, proposal.patch_diff)
        except GitError as exc:
            apply_error = str(exc)
    else:
        apply_error = proposal.rejection_reason

    clear_strategy_import(repo_root, strategy_module)
    train_trades_after, train_metrics_after = run_and_write(
        strategy_name=strategy_module,
        data_path=train_data_path,
        metrics_path=round_dir / "train_metrics_after.json",
        trades_path=round_dir / "train_trades_after.csv",
        report_path=round_dir / "train_report_after.md",
    )
    trades_after, metrics_after = run_and_write(
        strategy_name=strategy_module,
        data_path=validation_data_path,
        metrics_path=round_dir / "metrics_after.json",
        trades_path=round_dir / "trades_after.csv",
        report_path=round_dir / "report_after.md",
    )
    holdout_trades_after, holdout_metrics_after = run_and_write(
        strategy_name=strategy_module,
        data_path=holdout_data_path,
        metrics_path=round_dir / "holdout_metrics_after.json",
        trades_path=round_dir / "holdout_trades_after.csv",
        report_path=round_dir / "holdout_report_after.md",
    )

    decision = evaluate_policy(metrics_before, metrics_after, policy_rules)
    if apply_error:
        decision["accepted"] = False
        decision["reasons"] = [apply_error, *decision["reasons"]]  # type: ignore[index]
    write_json(round_dir / "decision.json", decision)
    append_outcome_memory(
        experiments_dir=round_dir.parent.parent,
        record=build_outcome_record(
            run_id=run_id,
            round_id=round_id,
            proposal=proposal,
            decision=decision,
            train_metrics_before=train_metrics_before,
            train_metrics_after=train_metrics_after,
            validation_metrics_before=metrics_before,
            validation_metrics_after=metrics_after,
            holdout_metrics_before=holdout_metrics_before,
            holdout_metrics_after=holdout_metrics_after,
        ),
    )

    return {
        "round_id": round_id,
        "run_id": run_id,
        "accepted": decision["accepted"],
        "reasons": decision["reasons"],
        "proposal_applicable": proposal.applicable,
        "proposal_patch_sha256": proposal.patch_sha256,
        "proposal_is_repeat": proposal.is_repeat_patch,
        "proposal_repeat_of_round": proposal.repeat_of_round,
        "proposal_memory_rejected": bool(memory_filter_reason),
        "proposal_memory_filter_reason": memory_filter_reason,
        "primary_proposal_memory_rejected": bool(primary_memory_filter_reason),
        "primary_proposal_memory_filter_reason": primary_memory_filter_reason,
        "proposal_fallback_used": proposal_fallback_used,
        "proposal_fallback_reason": proposal_fallback_reason,
        "before_trade_count": len(trades_before),
        "after_trade_count": len(trades_after),
        "train_before_trade_count": len(train_trades_before),
        "train_after_trade_count": len(train_trades_after),
        "holdout_before_trade_count": len(holdout_trades_before),
        "holdout_after_trade_count": len(holdout_trades_after),
        "train_ev_before": train_metrics_before["ev"],
        "train_ev_after": train_metrics_after["ev"],
        "validation_ev_before": metrics_before["ev"],
        "validation_ev_after": metrics_after["ev"],
        "holdout_ev_before": holdout_metrics_before["ev"],
        "holdout_ev_after": holdout_metrics_after["ev"],
    }


def index_record(manifest: dict[str, object]) -> dict[str, object]:
    """Build a compact JSONL index record for an iteration run."""
    return {
        "kind": "iteration_loop",
        "run_id": manifest["run_id"],
        "status": manifest["status"],
        "completed_rounds": manifest["completed_rounds"],
        "accepted_round": manifest["accepted_round"],
        "final_strategy_commit": manifest["final_strategy_commit"],
        "stop_reason": manifest.get("stop_reason"),
    }


def proposal_attempt_record(
    *,
    role: str,
    proposal: StrategyProposal,
    memory_filter_reason: str,
    patch_check_error: str,
    status: str,
) -> dict[str, object]:
    """Build an auditable proposal attempt record."""
    payload = proposal.to_dict()
    return {
        "role": role,
        "agent_name": payload.get("agent_name", ""),
        "summary": payload.get("summary", ""),
        "patch_sha256": payload.get("patch_sha256", ""),
        "status": status,
        "selected": False,
        "selection_reason": "",
        "memory_filter_rejected": bool(memory_filter_reason),
        "memory_filter_reason": memory_filter_reason,
        "patch_check_error": patch_check_error,
        "proposal": payload,
    }


def select_proposal_candidate(
    *,
    modifier: StrategyModifier,
    fallback_modifiers: tuple[StrategyModifier, ...],
    report_path: Path,
    target_file: Path,
    round_index: int,
    repo_root: Path,
    old_threshold: str,
    new_threshold: str,
    context_path: Path,
    run_dir: Path,
    current_round_id: str,
    experiments_dir: Path,
    memory_failed_patch_threshold: int,
    run_id: str,
) -> tuple[StrategyProposal, str, list[dict[str, object]], dict[str, object], str]:
    """Return the first proposal candidate that passes cheap deterministic filters."""
    candidate_modifiers = [("primary", modifier)]
    candidate_modifiers.extend(
        (f"fallback_{index:02d}", fallback_modifier)
        for index, fallback_modifier in enumerate(fallback_modifiers, start=1)
    )
    attempts: list[dict[str, object]] = []
    selected_index: int | None = None
    selected_proposal: StrategyProposal | None = None
    selected_memory_reason = ""
    primary_memory_reason = ""

    for role, candidate_modifier in candidate_modifiers:
        proposal = candidate_modifier.propose_strategy_change(
            report_path=report_path,
            target_file=target_file,
            round_index=round_index,
            repo_root=repo_root,
            old_threshold=old_threshold,
            new_threshold=new_threshold,
            context_path=context_path,
        )
        proposal = annotate_proposal_quality(
            proposal=proposal,
            run_dir=run_dir,
            current_round_id=current_round_id,
        )
        memory_reason = memory_filter_rejection_reason(
            experiments_dir=experiments_dir,
            patch_sha256=proposal.patch_sha256,
            threshold=memory_failed_patch_threshold,
            exclude_run_id=run_id,
        )
        if role == "primary":
            primary_memory_reason = memory_reason
        patch_check_error = ""
        if not memory_reason and proposal.applicable:
            try:
                check_patch(repo_root, proposal.patch_diff)
            except GitError as exc:
                patch_check_error = str(exc)
        status = proposal_candidate_status(
            proposal=proposal,
            memory_filter_reason=memory_reason,
            patch_check_error=patch_check_error,
        )
        attempts.append(
            proposal_attempt_record(
                role=role,
                proposal=proposal,
                memory_filter_reason=memory_reason,
                patch_check_error=patch_check_error,
                status=status,
            )
        )
        selected_proposal = proposal
        selected_memory_reason = memory_reason
        if status == "selectable":
            selected_index = len(attempts) - 1
            break

    if selected_proposal is None:
        raise ValueError("No proposal candidates were generated")
    if selected_index is None:
        selected_index = len(attempts) - 1
        selection_reason = "no selectable proposal candidates; using final rejection"
    else:
        selection_reason = "selected primary proposal"
        if attempts[selected_index]["role"] != "primary":
            rejected_reasons = [
                attempt_rejection_summary(attempt)
                for attempt in attempts[:selected_index]
            ]
            selection_reason = (
                f"selected {attempts[selected_index]['role']} after "
                + "; ".join(rejected_reasons)
            )
    attempts[selected_index]["selected"] = True
    attempts[selected_index]["selection_reason"] = selection_reason
    return (
        selected_proposal,
        selected_memory_reason,
        attempts,
        attempts[selected_index],
        primary_memory_reason,
    )


def proposal_candidate_status(
    *,
    proposal: StrategyProposal,
    memory_filter_reason: str,
    patch_check_error: str,
) -> str:
    """Return the cheap deterministic prefilter status for a proposal."""
    if memory_filter_reason:
        return "memory_rejected"
    if not proposal.applicable:
        return "not_applicable"
    if patch_check_error:
        return "patch_check_failed"
    return "selectable"


def attempt_rejection_summary(attempt: dict[str, object]) -> str:
    """Return a compact reason why a candidate was skipped."""
    role = str(attempt.get("role", "candidate"))
    reason = str(attempt.get("memory_filter_reason", ""))
    if reason:
        return f"{role} memory rejected: {reason}"
    patch_check_error = str(attempt.get("patch_check_error", ""))
    if patch_check_error:
        return f"{role} patch check failed: {patch_check_error}"
    return f"{role} status: {attempt.get('status', 'unknown')}"


def clear_strategy_import(repo_root: Path, strategy_module: str) -> None:
    """Force Python to load the current strategy from disk after patches."""
    sys.modules.pop(strategy_module, None)
    if strategy_module.startswith("strategies."):
        module_name = strategy_module.rsplit(".", maxsplit=1)[-1]
        for pyc_path in (repo_root / "strategies" / "__pycache__").glob(
            f"{module_name}*.pyc"
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
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def main() -> None:
    """CLI entrypoint for `python -m orchestrator.iteration_loop`."""
    args = parse_args()
    manifest = run_iteration_loop(
        run_id=args.run_id,
        max_rounds=args.max_rounds,
        experiments_dir=args.experiments_dir,
        data_path=args.validation_data,
        config_path=args.config,
        stop_on_repeated_proposal=False if args.allow_repeated_proposals else None,
    )
    print(f"Run id: {manifest['run_id']}")
    print(f"Status: {manifest['status']}")
    print(f"Completed rounds: {manifest['completed_rounds']}")
    print(f"Accepted round: {manifest['accepted_round']}")
    print(f"Stop reason: {manifest['stop_reason']}")
    print(f"Final strategy commit: {manifest['final_strategy_commit']}")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the iteration loop."""
    parser = argparse.ArgumentParser(description="Run the V0.5 self-iteration loop.")
    parser.add_argument("--config", type=Path, default=None, help="Path to config JSON.")
    parser.add_argument("--run-id", default=None, help="Experiment run id.")
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=None,
        help="Override configured max rounds.",
    )
    parser.add_argument(
        "--experiments-dir",
        type=Path,
        default=None,
        help="Override configured experiment directory.",
    )
    parser.add_argument(
        "--validation-data",
        type=Path,
        default=None,
        help="Override configured validation data path.",
    )
    parser.add_argument(
        "--allow-repeated-proposals",
        action="store_true",
        help="Continue until max rounds even if an agent repeats a failed patch.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
