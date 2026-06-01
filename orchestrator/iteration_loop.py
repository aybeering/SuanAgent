"""Multi-round self-iteration loop skeleton."""

from __future__ import annotations

import argparse
import csv
import importlib
import json
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
    direction_prior,
    direction_filter_rejection_reason,
    memory_filter_rejection_reason,
)
from orchestrator.policy_gate import apply_holdout_gate, evaluate_policy
from orchestrator.preflight import run_preflight
from orchestrator.proposal import (
    StrategyProposal,
    annotate_proposal_quality,
    enforce_proposal_contract,
)
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
        "memory_filter_policy": {
            "failed_patch_threshold": active_config.memory_failed_patch_threshold,
            "failed_direction_threshold": active_config.memory_failed_direction_threshold,
        },
        "exploration_policy": {
            "stop_after_no_improvement_rounds": (
                active_config.stop_after_no_improvement_rounds
            ),
            "min_probe_ev_delta": active_config.min_probe_ev_delta,
            "min_validation_ev_delta": active_config.min_validation_ev_delta,
            "explore_after_no_improvement_rounds": (
                active_config.explore_after_no_improvement_rounds
            ),
            "explore_low_sample_threshold": active_config.explore_low_sample_threshold,
            "explore_bonus": active_config.explore_bonus,
        },
        "candidate_selection": active_config.candidate_selection,
        "holdout_policy": active_config.holdout_policy,
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
                    holdout_policy_rules=active_config.holdout_policy,
                    stub_old_threshold=active_config.stub_old_threshold,
                    stub_new_threshold=active_config.stub_new_threshold,
                    strategy_module=strategy_module,
                    strategy_file_path=strategy_file_path,
                    modifier=modifier,
                    fallback_modifiers=fallback_modifiers,
                    memory_failed_patch_threshold=active_config.memory_failed_patch_threshold,
                    memory_failed_direction_threshold=(
                        active_config.memory_failed_direction_threshold
                    ),
                    explore_after_no_improvement_rounds=(
                        active_config.explore_after_no_improvement_rounds
                    ),
                    explore_low_sample_threshold=(
                        active_config.explore_low_sample_threshold
                    ),
                    explore_bonus=active_config.explore_bonus,
                    min_probe_ev_delta=active_config.min_probe_ev_delta,
                    min_validation_ev_delta=active_config.min_validation_ev_delta,
                    candidate_selection=active_config.candidate_selection,
                )
                manifest["completed_rounds"] = round_index
                manifest["rounds"].append(round_summary)  # type: ignore[union-attr]
                write_json(run_dir / "manifest.json", manifest)
                write_candidate_leaderboard(run_dir)

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
                    write_candidate_leaderboard(run_dir)
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
                    write_candidate_leaderboard(run_dir)
                    write_iteration_summary(run_dir=run_dir, manifest=manifest)
                    append_experiment_index(
                        experiments_dir=active_experiments_dir,
                        record=index_record(manifest),
                    )
                    return manifest

                no_improvement_reason = no_improvement_stop_reason(
                    rounds=manifest["rounds"],  # type: ignore[arg-type]
                    stop_after_rounds=active_config.stop_after_no_improvement_rounds,
                    min_probe_ev_delta=active_config.min_probe_ev_delta,
                    min_validation_ev_delta=active_config.min_validation_ev_delta,
                )
                if no_improvement_reason:
                    manifest["status"] = "stopped_no_improvement"
                    manifest["stop_reason"] = no_improvement_reason
                    manifest["final_strategy_commit"] = current_commit(repo_root)
                    write_json(run_dir / "manifest.json", manifest)
                    write_candidate_leaderboard(run_dir)
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
        write_candidate_leaderboard(run_dir)
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
        write_candidate_leaderboard(run_dir)
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
    holdout_policy_rules: dict[str, float | int | bool] | None,
    stub_old_threshold: str,
    stub_new_threshold: str,
    strategy_module: str,
    strategy_file_path: Path,
    modifier: StrategyModifier,
    fallback_modifiers: tuple[StrategyModifier, ...],
    memory_failed_patch_threshold: int,
    memory_failed_direction_threshold: int,
    explore_after_no_improvement_rounds: int,
    explore_low_sample_threshold: int,
    explore_bonus: int,
    min_probe_ev_delta: float,
    min_validation_ev_delta: float,
    candidate_selection: dict[str, float | int],
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
    probe_data_path = round_dir / "probe_data.csv"
    create_probe_dataset(
        source_path=train_data_path,
        output_path=probe_data_path,
        max_rows=10,
    )
    probe_trades_before, probe_metrics_before = run_and_write(
        strategy_name=strategy_module,
        data_path=probe_data_path,
        metrics_path=round_dir / "probe_metrics_before.json",
        trades_path=round_dir / "probe_trades_before.csv",
        report_path=round_dir / "probe_report_before.md",
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
        memory_failed_direction_threshold=memory_failed_direction_threshold,
        explore_after_no_improvement_rounds=explore_after_no_improvement_rounds,
        explore_low_sample_threshold=explore_low_sample_threshold,
        explore_bonus=explore_bonus,
        min_probe_ev_delta=min_probe_ev_delta,
        min_validation_ev_delta=min_validation_ev_delta,
        candidate_selection=candidate_selection,
        run_id=run_id,
        strategy_module=strategy_module,
        probe_data_path=probe_data_path,
        probe_metrics_before=probe_metrics_before,
        round_dir=round_dir,
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

    decision = apply_holdout_gate(
        evaluate_policy(metrics_before, metrics_after, policy_rules),
        before=holdout_metrics_before,
        after=holdout_metrics_after,
        rules=holdout_policy_rules,
    )
    if apply_error:
        decision["accepted"] = False
        decision["reasons"] = [apply_error, *decision["reasons"]]  # type: ignore[index]
    write_json(round_dir / "decision.json", decision)
    proposal_attempts = attach_validation_result_to_attempts(
        attempts=proposal_attempts,
        selected_patch_sha256=proposal.patch_sha256,
        decision=decision,
        metrics_before=metrics_before,
        metrics_after=metrics_after,
    )
    write_json(round_dir / "proposal_attempts.json", proposal_attempts)
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
        "proposal_contract_valid": not proposal.contract_errors,
        "proposal_contract_errors": list(proposal.contract_errors),
        "proposal_patch_sha256": proposal.patch_sha256,
        "proposal_direction_tag": proposal.direction_tag,
        "proposal_is_repeat": proposal.is_repeat_patch,
        "proposal_repeat_of_round": proposal.repeat_of_round,
        "proposal_memory_rejected": bool(memory_filter_reason),
        "proposal_memory_filter_reason": memory_filter_reason,
        "proposal_direction_memory_rejected": bool(
            selected_attempt.get("direction_filter_reason", "")
        ),
        "proposal_direction_filter_reason": selected_attempt.get(
            "direction_filter_reason",
            "",
        ),
        "primary_proposal_memory_rejected": bool(primary_memory_filter_reason),
        "primary_proposal_memory_filter_reason": primary_memory_filter_reason,
        "proposal_fallback_used": proposal_fallback_used,
        "proposal_fallback_reason": proposal_fallback_reason,
        "proposal_selected_role": selected_attempt["role"],
        "proposal_candidate_score": selected_attempt["candidate_score"],
        "proposal_candidate_status": selected_attempt["status"],
        "proposal_probe_ev_delta": selected_attempt.get("probe_ev_delta", 0.0),
        "before_trade_count": len(trades_before),
        "after_trade_count": len(trades_after),
        "train_before_trade_count": len(train_trades_before),
        "train_after_trade_count": len(train_trades_after),
        "holdout_before_trade_count": len(holdout_trades_before),
        "holdout_after_trade_count": len(holdout_trades_after),
        "probe_before_trade_count": len(probe_trades_before),
        "train_ev_before": train_metrics_before["ev"],
        "train_ev_after": train_metrics_after["ev"],
        "validation_ev_before": metrics_before["ev"],
        "validation_ev_after": metrics_after["ev"],
        "holdout_ev_before": holdout_metrics_before["ev"],
        "holdout_ev_after": holdout_metrics_after["ev"],
    }


def attach_validation_result_to_attempts(
    *,
    attempts: list[dict[str, object]],
    selected_patch_sha256: str,
    decision: dict[str, object],
    metrics_before: dict[str, float | int],
    metrics_after: dict[str, float | int],
) -> list[dict[str, object]]:
    """Attach final validation outcome to the selected candidate attempt."""
    for attempt in attempts:
        is_selected = bool(attempt.get("selected", False))
        if not is_selected:
            attempt["validation_status"] = "not_evaluated"
            continue
        attempt["validation_status"] = "evaluated"
        attempt["validation_accepted"] = bool(decision.get("accepted", False))
        attempt["validation_reasons"] = decision.get("reasons", [])
        attempt["validation_metrics_before"] = metrics_before
        attempt["validation_metrics_after"] = metrics_after
        attempt["validation_ev_delta"] = metric_delta(
            metrics_before,
            metrics_after,
            "ev",
        )
        attempt["validation_trade_count_delta"] = metric_delta(
            metrics_before,
            metrics_after,
            "trade_count",
        )
        attempt["selected_patch_sha256"] = selected_patch_sha256
    return attempts


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


def no_improvement_stop_reason(
    *,
    rounds: list[dict[str, object]],
    stop_after_rounds: int,
    min_probe_ev_delta: float,
    min_validation_ev_delta: float,
) -> str:
    """Return a stop reason when recent rounds show no meaningful improvement."""
    if stop_after_rounds <= 0 or len(rounds) < stop_after_rounds:
        return ""
    recent_rounds = rounds[-stop_after_rounds:]
    improved_rounds = [
        round_payload
        for round_payload in recent_rounds
        if round_improved(
            round_payload=round_payload,
            min_probe_ev_delta=min_probe_ev_delta,
            min_validation_ev_delta=min_validation_ev_delta,
        )
    ]
    if improved_rounds:
        return ""
    round_ids = ", ".join(str(payload.get("round_id", "")) for payload in recent_rounds)
    return (
        f"no probe or validation EV improvement above thresholds for "
        f"{stop_after_rounds} rounds: {round_ids}"
    )


def round_improved(
    *,
    round_payload: dict[str, object],
    min_probe_ev_delta: float,
    min_validation_ev_delta: float,
) -> bool:
    """Return whether a round exceeded either configured improvement threshold."""
    probe_delta = float(round_payload.get("proposal_probe_ev_delta", 0.0))
    validation_delta = float(round_payload.get("validation_ev_after", 0.0)) - float(
        round_payload.get("validation_ev_before", 0.0)
    )
    return probe_delta > min_probe_ev_delta or validation_delta > min_validation_ev_delta


def write_candidate_leaderboard(run_dir: Path) -> list[dict[str, object]]:
    """Write a run-level candidate leaderboard from round attempts."""
    rows = candidate_leaderboard_rows(run_dir)
    write_json(run_dir / "candidate_leaderboard.json", rows)
    return rows


def candidate_leaderboard_rows(run_dir: Path) -> list[dict[str, object]]:
    """Return candidate attempt rows ranked by selection and observed outcomes."""
    rows: list[dict[str, object]] = []
    for round_dir in sorted(run_dir.glob("round_*")):
        attempts_path = round_dir / "proposal_attempts.json"
        if not attempts_path.exists():
            continue
        attempts_payload = json_load_list(attempts_path)
        for attempt_index, attempt in enumerate(attempts_payload, start=1):
            if not isinstance(attempt, dict):
                continue
            proposal = attempt.get("proposal", {})
            proposal_payload = proposal if isinstance(proposal, dict) else {}
            rows.append(
                {
                    "run_id": run_dir.name,
                    "round_id": round_dir.name,
                    "attempt_index": attempt_index,
                    "role": attempt.get("role", ""),
                    "agent_name": attempt.get("agent_name", ""),
                    "direction_tag": attempt.get("direction_tag", ""),
                    "selected": bool(attempt.get("selected", False)),
                    "status": attempt.get("status", ""),
                    "candidate_score": attempt.get("candidate_score", 0),
                    "probe_ev_delta": attempt.get("probe_ev_delta", 0.0),
                    "probe_trade_count_delta": attempt.get(
                        "probe_trade_count_delta",
                        0.0,
                    ),
                    "validation_status": attempt.get("validation_status", ""),
                    "validation_accepted": attempt.get("validation_accepted", None),
                    "validation_ev_delta": attempt.get("validation_ev_delta", None),
                    "validation_trade_count_delta": attempt.get(
                        "validation_trade_count_delta",
                        None,
                    ),
                    "patch_sha256": attempt.get("patch_sha256", ""),
                    "summary": attempt.get("summary", ""),
                    "target_file": proposal_payload.get("target_file", ""),
                    "selection_reason": attempt.get("selection_reason", ""),
                    "score_reasons": attempt.get("score_reasons", []),
                    "contract_errors": attempt.get("contract_errors", []),
                    "memory_filter_reason": attempt.get("memory_filter_reason", ""),
                    "patch_memory_filter_reason": attempt.get(
                        "patch_memory_filter_reason",
                        "",
                    ),
                    "direction_filter_reason": attempt.get(
                        "direction_filter_reason",
                        "",
                    ),
                    "direction_prior": attempt.get("direction_prior", {}),
                    "exploration_bonus": attempt.get("exploration_bonus", {}),
                    "patch_check_error": attempt.get("patch_check_error", ""),
                    "probe_error": attempt.get("probe_error", ""),
                    "probe_artifacts": attempt.get("probe_artifacts", {}),
                }
            )
    rows.sort(key=candidate_leaderboard_sort_key, reverse=True)
    return rows


def candidate_leaderboard_sort_key(row: dict[str, object]) -> tuple[object, ...]:
    """Sort selected and high-performing candidate rows first."""
    validation_ev_delta = row.get("validation_ev_delta")
    validation_value = (
        float(validation_ev_delta)
        if isinstance(validation_ev_delta, int | float)
        else float("-inf")
    )
    return (
        bool(row.get("selected", False)),
        validation_value,
        float(row.get("probe_ev_delta", 0.0)),
        int(row.get("candidate_score", 0)),
        str(row.get("round_id", "")),
        -int(row.get("attempt_index", 0)),
    )


def json_load_list(path: Path) -> list[object]:
    """Load a JSON list from disk."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def proposal_attempt_record(
    *,
    role: str,
    proposal: StrategyProposal,
    memory_filter_reason: str,
    patch_memory_filter_reason: str,
    direction_filter_reason: str,
    direction_prior_payload: dict[str, object],
    exploration_bonus_payload: dict[str, object],
    patch_check_error: str,
    status: str,
    candidate_score: int,
    score_reasons: list[str],
    probe_metrics_before: dict[str, float | int],
    probe_metrics_after: dict[str, float | int],
    probe_error: str,
    probe_artifacts: dict[str, str],
    candidate_selection: dict[str, float | int],
) -> dict[str, object]:
    """Build an auditable proposal attempt record."""
    payload = proposal.to_dict()
    return {
        "role": role,
        "agent_name": payload.get("agent_name", ""),
        "direction_tag": payload.get("direction_tag", ""),
        "summary": payload.get("summary", ""),
        "patch_sha256": payload.get("patch_sha256", ""),
        "status": status,
        "selected": False,
        "selection_reason": "",
        "candidate_score": candidate_score,
        "score_reasons": score_reasons,
        "candidate_selection": candidate_selection,
        "contract_errors": payload.get("contract_errors", ()),
        "probe_metrics_before": probe_metrics_before,
        "probe_metrics_after": probe_metrics_after,
        "probe_ev_delta": metric_delta(probe_metrics_before, probe_metrics_after, "ev"),
        "probe_trade_count_delta": metric_delta(
            probe_metrics_before,
            probe_metrics_after,
            "trade_count",
        ),
        "probe_error": probe_error,
        "probe_artifacts": probe_artifacts,
        "memory_filter_rejected": bool(memory_filter_reason),
        "memory_filter_reason": memory_filter_reason,
        "patch_memory_filter_rejected": bool(patch_memory_filter_reason),
        "patch_memory_filter_reason": patch_memory_filter_reason,
        "direction_memory_filter_rejected": bool(direction_filter_reason),
        "direction_filter_reason": direction_filter_reason,
        "direction_prior": direction_prior_payload,
        "exploration_bonus": exploration_bonus_payload,
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
    memory_failed_direction_threshold: int,
    explore_after_no_improvement_rounds: int,
    explore_low_sample_threshold: int,
    explore_bonus: int,
    min_probe_ev_delta: float,
    min_validation_ev_delta: float,
    candidate_selection: dict[str, float | int],
    run_id: str,
    strategy_module: str,
    probe_data_path: Path,
    probe_metrics_before: dict[str, float | int],
    round_dir: Path,
) -> tuple[StrategyProposal, str, list[dict[str, object]], dict[str, object], str]:
    """Return the highest-scored proposal that passes cheap deterministic filters."""
    candidate_modifiers = [("primary", modifier)]
    candidate_modifiers.extend(
        (f"fallback_{index:02d}", fallback_modifier)
        for index, fallback_modifier in enumerate(fallback_modifiers, start=1)
    )
    attempts: list[dict[str, object]] = []
    selected_proposal: StrategyProposal | None = None
    selected_memory_reason = ""
    primary_memory_reason = ""
    seen_patch_hashes: set[str] = set()

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
        proposal = enforce_proposal_contract(
            proposal=proposal,
            expected_target_file=target_file.relative_to(repo_root),
            expected_round_index=round_index,
        )
        proposal = annotate_proposal_quality(
            proposal=proposal,
            run_dir=run_dir,
            current_round_id=current_round_id,
        )
        patch_memory_reason = memory_filter_rejection_reason(
            experiments_dir=experiments_dir,
            patch_sha256=proposal.patch_sha256,
            threshold=memory_failed_patch_threshold,
            exclude_run_id=run_id,
        )
        direction_memory_reason = direction_filter_rejection_reason(
            experiments_dir=experiments_dir,
            direction_tag=proposal.direction_tag,
            threshold=memory_failed_direction_threshold,
            exclude_run_id=run_id,
        )
        memory_reason = combined_filter_reason(
            patch_memory_reason,
            direction_memory_reason,
        )
        direction_prior_payload = direction_prior(
            experiments_dir=experiments_dir,
            direction_tag=proposal.direction_tag,
            exclude_run_id=run_id,
        )
        exploration_bonus_payload = exploration_bonus_payload_for_candidate(
            run_dir=run_dir,
            current_round_id=current_round_id,
            direction_prior_payload=direction_prior_payload,
            explore_after_no_improvement_rounds=explore_after_no_improvement_rounds,
            explore_low_sample_threshold=explore_low_sample_threshold,
            explore_bonus=explore_bonus,
            min_probe_ev_delta=min_probe_ev_delta,
            min_validation_ev_delta=min_validation_ev_delta,
        )
        if role == "primary":
            primary_memory_reason = memory_reason
        duplicate_patch = bool(proposal.patch_sha256 in seen_patch_hashes)
        if proposal.patch_sha256:
            seen_patch_hashes.add(proposal.patch_sha256)
        patch_check_error = ""
        if not memory_reason and proposal.applicable and not duplicate_patch:
            try:
                check_patch(repo_root, proposal.patch_diff)
            except GitError as exc:
                patch_check_error = str(exc)
        status = proposal_candidate_status(
            proposal=proposal,
            memory_filter_reason=memory_reason,
            patch_check_error=patch_check_error,
            duplicate_patch=duplicate_patch,
        )
        probe_metrics_after: dict[str, float | int] = {}
        probe_error = ""
        probe_artifacts: dict[str, str] = {}
        if status == "selectable":
            probe_metrics_after, probe_error, probe_artifacts = run_probe_candidate(
                repo_root=repo_root,
                proposal=proposal,
                role=role,
                strategy_module=strategy_module,
                probe_data_path=probe_data_path,
                round_dir=round_dir,
            )
            if probe_error:
                status = "probe_failed"
        score_payload = score_proposal_candidate(
            proposal=proposal,
            role=role,
            status=status,
            memory_filter_reason=memory_reason,
            patch_check_error=patch_check_error,
            duplicate_patch=duplicate_patch,
            probe_metrics_before=probe_metrics_before,
            probe_metrics_after=probe_metrics_after,
            probe_error=probe_error,
            direction_prior_payload=direction_prior_payload,
            exploration_bonus_payload=exploration_bonus_payload,
            candidate_selection=candidate_selection,
        )
        attempts.append(
            proposal_attempt_record(
                role=role,
                proposal=proposal,
                memory_filter_reason=memory_reason,
                patch_memory_filter_reason=patch_memory_reason,
                direction_filter_reason=direction_memory_reason,
                direction_prior_payload=direction_prior_payload,
                exploration_bonus_payload=exploration_bonus_payload,
                patch_check_error=patch_check_error,
                status=status,
                candidate_score=int(score_payload["score"]),
                score_reasons=list(score_payload["reasons"]),
                probe_metrics_before=probe_metrics_before,
                probe_metrics_after=probe_metrics_after,
                probe_error=probe_error,
                probe_artifacts=probe_artifacts,
                candidate_selection=candidate_selection,
            )
        )

    selected_index = selected_candidate_index(attempts)
    if selected_index is not None:
        selected_payload = attempts[selected_index]["proposal"]
        selected_proposal = StrategyProposal(**selected_payload)  # type: ignore[arg-type]
        selected_memory_reason = str(attempts[selected_index]["memory_filter_reason"])
    elif attempts:
        selected_index = len(attempts) - 1
        selected_payload = attempts[selected_index]["proposal"]
        selected_proposal = StrategyProposal(**selected_payload)  # type: ignore[arg-type]
        selected_memory_reason = str(attempts[selected_index]["memory_filter_reason"])
    if selected_proposal is None:
        raise ValueError("No proposal candidates were generated")

    if attempts[selected_index]["status"] != "selectable":
        selection_reason = "no selectable proposal candidates; using final rejection"
    else:
        selection_reason = (
            f"selected {attempts[selected_index]['role']} with score "
            f"{attempts[selected_index]['candidate_score']}"
        )
        if attempts[selected_index]["role"] != "primary":
            rejected_reasons = skipped_attempt_summaries(attempts, selected_index)
            selection_reason = (
                f"selected {attempts[selected_index]['role']} with score "
                f"{attempts[selected_index]['candidate_score']} after "
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
    duplicate_patch: bool,
) -> str:
    """Return the cheap deterministic prefilter status for a proposal."""
    if proposal.contract_errors:
        return "contract_invalid"
    if memory_filter_reason:
        return "memory_rejected"
    if not proposal.applicable:
        return "not_applicable"
    if duplicate_patch:
        return "duplicate_candidate"
    if patch_check_error:
        return "patch_check_failed"
    return "selectable"


def combined_filter_reason(*reasons: str) -> str:
    """Return one stable rejection reason from patch and direction memory."""
    return "; ".join(reason for reason in reasons if reason)


def selected_candidate_index(attempts: list[dict[str, object]]) -> int | None:
    """Return the highest-scored selectable candidate index."""
    selectable_indexes = [
        index
        for index, attempt in enumerate(attempts)
        if attempt.get("status") == "selectable"
    ]
    if not selectable_indexes:
        return None
    return max(
        selectable_indexes,
        key=lambda index: (int(attempts[index].get("candidate_score", 0)), -index),
    )


def score_proposal_candidate(
    *,
    proposal: StrategyProposal,
    role: str,
    status: str,
    memory_filter_reason: str,
    patch_check_error: str,
    duplicate_patch: bool,
    probe_metrics_before: dict[str, float | int],
    probe_metrics_after: dict[str, float | int],
    probe_error: str,
    direction_prior_payload: dict[str, object],
    exploration_bonus_payload: dict[str, object],
    candidate_selection: dict[str, float | int],
) -> dict[str, object]:
    """Score a candidate deterministically before running expensive evaluation."""
    if status != "selectable":
        reasons = [f"status={status}"]
        if memory_filter_reason:
            reasons.append("blocked by outcome memory")
        if patch_check_error:
            reasons.append("patch check failed")
        if duplicate_patch:
            reasons.append("duplicate patch hash")
        if probe_error:
            reasons.append("probe evaluation failed")
        return {"score": 0, "reasons": reasons}

    score = score_setting(candidate_selection, "base_selectable_score")
    reasons = [f"base selectable score {format_score_delta(score)}"]
    expected = proposal.expected_metric_change
    for metric, value in sorted(expected.items()):
        delta, reason = expected_metric_score(metric, value, candidate_selection)
        if delta:
            score += delta
            reasons.append(reason)
    risk_delta, risk_reason = risk_score(proposal.risk_notes, candidate_selection)
    if risk_delta:
        score += risk_delta
        reasons.append(risk_reason)
    if role == "primary":
        primary_bonus = score_setting(candidate_selection, "primary_modifier_bonus")
        score += primary_bonus
        reasons.append(f"primary modifier stability {format_score_delta(primary_bonus)}")
    prior_delta, prior_reason = direction_prior_score(
        direction_prior_payload,
        candidate_selection,
    )
    if prior_delta:
        score += prior_delta
        reasons.append(prior_reason)
    exploration_delta, exploration_reason = exploration_bonus_score(
        exploration_bonus_payload,
        candidate_selection,
    )
    if exploration_delta:
        score += exploration_delta
        reasons.append(exploration_reason)
    probe_delta, probe_reason = probe_score(
        metrics_before=probe_metrics_before,
        metrics_after=probe_metrics_after,
        candidate_selection=candidate_selection,
    )
    if probe_delta:
        score += probe_delta
        reasons.append(probe_reason)
    return {"score": score, "reasons": reasons}


def exploration_bonus_payload_for_candidate(
    *,
    run_dir: Path,
    current_round_id: str,
    direction_prior_payload: dict[str, object],
    explore_after_no_improvement_rounds: int,
    explore_low_sample_threshold: int,
    explore_bonus: int,
    min_probe_ev_delta: float,
    min_validation_ev_delta: float,
) -> dict[str, object]:
    """Return deterministic exploration-bonus metadata for one candidate."""
    base_payload: dict[str, object] = {
        "active": False,
        "score_delta": 0,
        "reason": "",
        "recent_rounds": [],
        "recent_selected_directions": [],
        "explore_after_no_improvement_rounds": explore_after_no_improvement_rounds,
        "explore_low_sample_threshold": explore_low_sample_threshold,
        "direction_tag": direction_prior_payload.get("direction_tag", ""),
        "direction_sample_count": int(direction_prior_payload.get("sample_count", 0)),
    }
    if explore_after_no_improvement_rounds <= 0 or explore_bonus <= 0:
        return base_payload

    prior_rounds = prior_manifest_rounds(run_dir, current_round_id)
    if len(prior_rounds) < explore_after_no_improvement_rounds:
        return base_payload
    recent_rounds = prior_rounds[-explore_after_no_improvement_rounds:]
    base_payload["recent_rounds"] = [
        str(round_payload.get("round_id", "")) for round_payload in recent_rounds
    ]
    recent_selected_directions = [
        str(round_payload.get("proposal_direction_tag", ""))
        for round_payload in recent_rounds
        if round_payload.get("proposal_direction_tag", "")
    ]
    base_payload["recent_selected_directions"] = recent_selected_directions
    if any(
        round_improved(
            round_payload=round_payload,
            min_probe_ev_delta=min_probe_ev_delta,
            min_validation_ev_delta=min_validation_ev_delta,
        )
        for round_payload in recent_rounds
    ):
        return base_payload
    sample_count = int(direction_prior_payload.get("sample_count", 0))
    if sample_count > explore_low_sample_threshold:
        return base_payload
    direction_tag = str(direction_prior_payload.get("direction_tag", ""))
    if direction_tag in recent_selected_directions:
        return base_payload

    recent_text = ", ".join(str(round_id) for round_id in base_payload["recent_rounds"])
    return {
        **base_payload,
        "active": True,
        "score_delta": explore_bonus,
        "reason": (
            f"exploration bonus after {explore_after_no_improvement_rounds} "
            f"no-improvement rounds ({recent_text}) for low-sample direction "
            f"{direction_tag} n={sample_count}"
        ),
    }


def prior_manifest_rounds(
    run_dir: Path,
    current_round_id: str,
) -> list[dict[str, object]]:
    """Return completed prior round payloads from the active manifest."""
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    rounds = payload.get("rounds", [])
    if not isinstance(rounds, list):
        return []
    return [
        round_payload
        for round_payload in rounds
        if isinstance(round_payload, dict)
        and str(round_payload.get("round_id", "")) < current_round_id
    ]


def exploration_bonus_score(
    payload: dict[str, object],
    candidate_selection: dict[str, float | int],
) -> tuple[int, str]:
    """Return score contribution and reason text from exploration metadata."""
    raw_delta = int(payload.get("score_delta", 0))
    score_delta = weighted_score(
        raw_delta,
        candidate_selection,
        "exploration_bonus_weight",
    )
    if score_delta <= 0:
        return 0, ""
    return score_delta, weighted_reason(
        str(payload.get("reason", "exploration bonus")),
        raw_delta,
        score_delta,
        score_weight(candidate_selection, "exploration_bonus_weight"),
    )


def direction_prior_score(
    prior_payload: dict[str, object],
    candidate_selection: dict[str, float | int],
) -> tuple[int, str]:
    """Return score contribution and reason text from direction history."""
    raw_delta = int(prior_payload.get("score_delta", 0))
    score_delta = weighted_score(
        raw_delta,
        candidate_selection,
        "direction_prior_weight",
    )
    if score_delta == 0:
        return 0, ""
    sample_count = int(prior_payload.get("sample_count", 0))
    accept_rate = float(prior_payload.get("accept_rate", 0.0))
    avg_ev_delta = float(prior_payload.get("avg_validation_ev_delta", 0.0))
    sign = "+" if raw_delta > 0 else ""
    reason = (
        "direction prior "
        f"n={sample_count} accept_rate={accept_rate:.3f} "
        f"avg_validation_ev_delta={avg_ev_delta:.6f} {sign}{raw_delta}"
    )
    return (
        score_delta,
        weighted_reason(
            reason,
            raw_delta,
            score_delta,
            score_weight(candidate_selection, "direction_prior_weight"),
        ),
    )


def expected_metric_score(
    metric: str,
    value: str,
    candidate_selection: dict[str, float | int],
) -> tuple[int, str]:
    """Return a deterministic score contribution for expected metric metadata."""
    normalized = value.lower()
    raw_delta = 0
    reason = ""
    if metric == "ev":
        if "increase" in normalized or "improve" in normalized:
            raw_delta, reason = 20, "expected ev improvement +20"
        elif "uncertain" in normalized:
            raw_delta, reason = 5, "explicit ev uncertainty +5"
    elif metric == "total_pnl":
        if "increase" in normalized or "improve" in normalized:
            raw_delta, reason = 10, "expected pnl improvement +10"
        elif "uncertain" in normalized:
            raw_delta, reason = 2, "explicit pnl uncertainty +2"
    elif metric == "trade_count":
        if "same_or_increase" in normalized:
            raw_delta, reason = 6, "trade count stable/increase +6"
        elif "increase" in normalized:
            raw_delta, reason = 8, "trade count increase +8"
        elif "decrease" in normalized:
            raw_delta, reason = -2, "trade count decrease -2"
    elif metric == "avg_slippage":
        if "decrease" in normalized:
            raw_delta, reason = 4, "expected slippage decrease +4"
        elif "increase" in normalized:
            raw_delta, reason = -4, "expected slippage increase -4"
    elif metric == "max_drawdown" and "decrease" in normalized:
        raw_delta, reason = 6, "expected drawdown decrease +6"
    return weighted_metric_score(
        raw_delta,
        reason,
        candidate_selection,
        "expected_metric_weight",
    )


def risk_score(
    risk_notes: str,
    candidate_selection: dict[str, float | int],
) -> tuple[int, str]:
    """Return a small deterministic risk contribution from risk notes."""
    normalized = risk_notes.lower()
    if "increas" in normalized:
        return weighted_metric_score(
            -3,
            "risk note includes increase -3",
            candidate_selection,
            "risk_weight",
        )
    if "reduce" in normalized or "decrease" in normalized:
        return weighted_metric_score(
            3,
            "risk note suggests reduction +3",
            candidate_selection,
            "risk_weight",
        )
    return 0, ""


def probe_score(
    *,
    metrics_before: dict[str, float | int],
    metrics_after: dict[str, float | int],
    candidate_selection: dict[str, float | int],
) -> tuple[int, str]:
    """Return a deterministic score contribution from probe metrics."""
    if not metrics_before or not metrics_after:
        return 0, ""
    ev_delta = metric_delta(metrics_before, metrics_after, "ev")
    trade_delta = metric_delta(metrics_before, metrics_after, "trade_count")
    score = 0
    reasons: list[str] = []
    ev_multiplier = float(candidate_selection.get("probe_ev_multiplier", 1000))
    ev_cap = score_setting(candidate_selection, "probe_ev_cap")
    trade_cap = score_setting(candidate_selection, "probe_trade_count_cap")
    if ev_delta > 0:
        score += min(ev_cap, int(round(ev_delta * ev_multiplier)))
        reasons.append(f"probe ev delta {ev_delta:.6f}")
    elif ev_delta < 0:
        score -= min(ev_cap, int(round(abs(ev_delta) * ev_multiplier)))
        reasons.append(f"probe ev delta {ev_delta:.6f}")
    if trade_delta > 0:
        score += min(trade_cap, int(trade_delta))
        reasons.append(f"probe trade count delta +{int(trade_delta)}")
    elif trade_delta < 0:
        score -= min(trade_cap, abs(int(trade_delta)))
        reasons.append(f"probe trade count delta {int(trade_delta)}")
    if not reasons:
        return 0, ""
    raw_score = score
    score = weighted_score(raw_score, candidate_selection, "probe_weight")
    return score, weighted_reason(
        "; ".join(reasons),
        raw_score,
        score,
        score_weight(candidate_selection, "probe_weight"),
    )


def weighted_metric_score(
    raw_delta: int,
    reason: str,
    candidate_selection: dict[str, float | int],
    weight_key: str,
) -> tuple[int, str]:
    """Apply a configured weight to a deterministic score contribution."""
    if raw_delta == 0:
        return 0, ""
    weight = score_weight(candidate_selection, weight_key)
    delta = weighted_score(raw_delta, candidate_selection, weight_key)
    if delta == 0:
        return 0, ""
    return delta, weighted_reason(reason, raw_delta, delta, weight)


def weighted_score(
    raw_delta: int,
    candidate_selection: dict[str, float | int],
    weight_key: str,
) -> int:
    """Return a rounded weighted score delta."""
    return int(round(raw_delta * score_weight(candidate_selection, weight_key)))


def score_setting(
    candidate_selection: dict[str, float | int],
    key: str,
) -> int:
    """Return an integer score setting."""
    return int(round(float(candidate_selection.get(key, 0))))


def score_weight(
    candidate_selection: dict[str, float | int],
    key: str,
) -> float:
    """Return a floating score weight."""
    return float(candidate_selection.get(key, 1.0))


def weighted_reason(reason: str, raw_delta: int, delta: int, weight: float) -> str:
    """Return an auditable reason for a weighted score contribution."""
    if weight == 1.0 or raw_delta == delta:
        return reason if reason.endswith(str(raw_delta)) else (
            f"{reason} {format_score_delta(delta)}"
        )
    return (
        f"{reason} -> {format_score_delta(delta)} "
        f"(raw {format_score_delta(raw_delta)} x {weight:g})"
    )


def format_score_delta(delta: int) -> str:
    """Format a signed score contribution."""
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta}"


def metric_delta(
    before: dict[str, float | int],
    after: dict[str, float | int],
    key: str,
) -> float:
    """Return a metric delta when both metric payloads are present."""
    if key not in before or key not in after:
        return 0.0
    return float(after[key]) - float(before[key])


def skipped_attempt_summaries(
    attempts: list[dict[str, object]],
    selected_index: int,
) -> list[str]:
    """Summarize attempts that were not selected before the winning candidate."""
    return [
        attempt_rejection_summary(attempt)
        for attempt in attempts[:selected_index]
        if attempt.get("status") != "selectable"
    ]


def attempt_rejection_summary(attempt: dict[str, object]) -> str:
    """Return a compact reason why a candidate was skipped."""
    role = str(attempt.get("role", "candidate"))
    contract_errors = attempt.get("contract_errors", [])
    if isinstance(contract_errors, list | tuple) and contract_errors:
        return f"{role} contract invalid: {contract_errors[0]}"
    reason = str(attempt.get("memory_filter_reason", ""))
    if reason:
        return f"{role} memory rejected: {reason}"
    patch_check_error = str(attempt.get("patch_check_error", ""))
    if patch_check_error:
        return f"{role} patch check failed: {patch_check_error}"
    return f"{role} status: {attempt.get('status', 'unknown')}"


def run_probe_candidate(
    *,
    repo_root: Path,
    proposal: StrategyProposal,
    role: str,
    strategy_module: str,
    probe_data_path: Path,
    round_dir: Path,
) -> tuple[dict[str, float | int], str, dict[str, str]]:
    """Apply a candidate temporarily, run probe data, and rollback."""
    safe_role = role.replace("/", "_")
    metrics_path = round_dir / f"probe_{safe_role}_metrics.json"
    trades_path = round_dir / f"probe_{safe_role}_trades.csv"
    report_path = round_dir / f"probe_{safe_role}_report.md"
    artifacts = {
        "metrics": metrics_path.name,
        "trades": trades_path.name,
        "report": report_path.name,
    }
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
        return metrics, "", artifacts
    except Exception as exc:
        return {}, str(exc), artifacts
    finally:
        rollback_strategy(repo_root)
        clear_strategy_import(repo_root, strategy_module)


def create_probe_dataset(
    *,
    source_path: Path,
    output_path: Path,
    max_rows: int,
) -> None:
    """Copy a deterministic prefix of a source CSV into a probe dataset."""
    with source_path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {source_path}")
        with output_path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=reader.fieldnames)
            writer.writeheader()
            for index, row in enumerate(reader):
                if index >= max_rows:
                    break
                writer.writerow(row)


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
