"""Deterministic overfit-validator role stub."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


OVERFIT_VALIDATION_SCHEMA_VERSION = "overfit_validation_v1"
EV_LAG_WARNING_THRESHOLD = 0.01


def write_overfit_validation(
    *,
    output_path: Path,
    markdown_path: Path,
    repo_root: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    round_dir: Path,
    train_metrics_before: dict[str, float | int],
    train_metrics_after: dict[str, float | int],
    validation_metrics_before: dict[str, float | int],
    validation_metrics_after: dict[str, float | int],
    holdout_metrics_before: dict[str, float | int],
    holdout_metrics_after: dict[str, float | int],
    decision: dict[str, object],
    proposal_path: Path,
    decision_path: Path,
    analysis_notes_path: Path,
    agent_role_contracts_path: Path,
) -> Path:
    """Write the deterministic overfit-validator stub artifact."""
    payload = overfit_validation_payload(
        repo_root=repo_root,
        run_id=run_id,
        round_id=round_id,
        round_index=round_index,
        round_dir=round_dir,
        train_metrics_before=train_metrics_before,
        train_metrics_after=train_metrics_after,
        validation_metrics_before=validation_metrics_before,
        validation_metrics_after=validation_metrics_after,
        holdout_metrics_before=holdout_metrics_before,
        holdout_metrics_after=holdout_metrics_after,
        decision=decision,
        proposal_path=proposal_path,
        decision_path=decision_path,
        analysis_notes_path=analysis_notes_path,
        agent_role_contracts_path=agent_role_contracts_path,
    )
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(overfit_validation_markdown(payload), encoding="utf-8")
    return output_path


def overfit_validation_payload(
    *,
    repo_root: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    round_dir: Path,
    train_metrics_before: dict[str, float | int],
    train_metrics_after: dict[str, float | int],
    validation_metrics_before: dict[str, float | int],
    validation_metrics_after: dict[str, float | int],
    holdout_metrics_before: dict[str, float | int],
    holdout_metrics_after: dict[str, float | int],
    decision: dict[str, object],
    proposal_path: Path,
    decision_path: Path,
    analysis_notes_path: Path,
    agent_role_contracts_path: Path,
) -> dict[str, object]:
    """Return the JSON payload for the overfit-validator stub."""
    deltas = {
        "train": metric_deltas(train_metrics_before, train_metrics_after),
        "validation": metric_deltas(validation_metrics_before, validation_metrics_after),
        "holdout": metric_deltas(holdout_metrics_before, holdout_metrics_after),
    }
    flags = risk_flags(
        deltas=deltas,
        decision=decision,
        previous_rejected_rounds=previous_rejected_rounds(round_dir.parent, round_id),
    )
    return {
        "schema_version": OVERFIT_VALIDATION_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "round_index": round_index,
        "agent_role": "overfit_validator",
        "execution_mode": "stub_contract",
        "implemented": False,
        "round_dir": relative_path(round_dir, repo_root),
        "consumed_artifacts": {
            "agent_role_contracts": relative_path(agent_role_contracts_path, repo_root),
            "analysis_notes": relative_path(analysis_notes_path, repo_root),
            "proposal": relative_path(proposal_path, repo_root),
            "decision": relative_path(decision_path, repo_root),
            "train_metrics_before": relative_path(
                round_dir / "train_metrics_before.json",
                repo_root,
            ),
            "train_metrics_after": relative_path(
                round_dir / "train_metrics_after.json",
                repo_root,
            ),
            "validation_metrics_before": relative_path(
                round_dir / "metrics_before.json",
                repo_root,
            ),
            "validation_metrics_after": relative_path(
                round_dir / "metrics_after.json",
                repo_root,
            ),
            "holdout_metrics_before": relative_path(
                round_dir / "holdout_metrics_before.json",
                repo_root,
            ),
            "holdout_metrics_after": relative_path(
                round_dir / "holdout_metrics_after.json",
                repo_root,
            ),
        },
        "metric_deltas": deltas,
        "checks": {
            "previous_rejected_rounds": previous_rejected_rounds(
                round_dir.parent,
                round_id,
            ),
            "validation_holdout_ev_delta_gap": (
                metric_number(deltas["validation"], "ev")
                - metric_number(deltas["holdout"], "ev")
            ),
            "decision_accepted": bool(decision.get("accepted", False)),
            "deterministic_gate_active": False,
        },
        "risk_flags": flags,
        "recommendation": {
            "action": "keep_existing_decision",
            "reason": "V0.5 overfit validator is a contract-only stub.",
            "can_veto": False,
            "can_change_acceptance": False,
            "can_change_routing": False,
        },
        "produced_artifacts": {
            "overfit_validation_json": relative_path(
                round_dir / "overfit_validation.json",
                repo_root,
            ),
            "overfit_validation_markdown": relative_path(
                round_dir / "overfit_validation.md",
                repo_root,
            ),
        },
    }


def metric_deltas(
    before: dict[str, float | int],
    after: dict[str, float | int],
) -> dict[str, float]:
    """Return deterministic metric deltas used by the overfit stub."""
    keys = (
        "ev",
        "total_pnl",
        "max_drawdown",
        "trade_count",
        "fill_rate",
        "avg_slippage",
    )
    return {
        key: metric_number(after, key) - metric_number(before, key)
        for key in keys
        if key in before or key in after
    }


def risk_flags(
    *,
    deltas: dict[str, dict[str, float]],
    decision: dict[str, object],
    previous_rejected_rounds: int,
) -> list[str]:
    """Return deterministic advisory risk flags."""
    flags: list[str] = []
    validation_ev_delta = metric_number(deltas.get("validation", {}), "ev")
    holdout_ev_delta = metric_number(deltas.get("holdout", {}), "ev")
    if validation_ev_delta - holdout_ev_delta > EV_LAG_WARNING_THRESHOLD:
        flags.append("holdout_ev_lags_validation")
    if bool(decision.get("accepted", False)) and holdout_ev_delta < 0.0:
        flags.append("accepted_candidate_loses_holdout_ev")
    if previous_rejected_rounds >= 3:
        flags.append("many_recent_rejections")
    return flags


def previous_rejected_rounds(run_dir: Path, current_round_id: str) -> int:
    """Count prior round decisions that were rejected before this round."""
    count = 0
    for round_dir in sorted(run_dir.glob("round_*")):
        if round_dir.name >= current_round_id:
            continue
        decision_path = round_dir / "decision.json"
        if not decision_path.exists():
            continue
        try:
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(decision, dict) and not bool(decision.get("accepted", False)):
            count += 1
    return count


def overfit_validation_markdown(payload: dict[str, object]) -> str:
    """Return a human-readable render of the overfit stub output."""
    flags = payload.get("risk_flags", [])
    flag_text = "\n".join(f"- {flag}" for flag in flags) if flags else "- none"
    return "\n".join(
        [
            "# Overfit Validation",
            "",
            f"Run: {payload['run_id']}",
            f"Round: {payload['round_id']}",
            "Role: overfit_validator",
            "Mode: stub_contract",
            "",
            "## Risk Flags",
            flag_text,
            "",
            "## Recommendation",
            "keep_existing_decision",
            "",
        ]
    )


def metric_number(metrics: object, key: str) -> float:
    """Return a metric value as a float."""
    if not isinstance(metrics, dict):
        return 0.0
    value = metrics.get(key, 0.0)
    return float(value) if isinstance(value, int | float) else 0.0


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
