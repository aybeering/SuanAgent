"""Deterministic read-only analysis role stub."""

from __future__ import annotations

import json
from pathlib import Path


ANALYSIS_NOTES_SCHEMA_VERSION = "analysis_notes_v1"


def write_analysis_notes(
    *,
    output_path: Path,
    markdown_path: Path,
    repo_root: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    round_dir: Path,
    train_metrics_before: dict[str, float | int],
    validation_metrics_before: dict[str, float | int],
    holdout_metrics_before: dict[str, float | int],
    train_report_path: Path,
    validation_report_path: Path,
    holdout_report_path: Path,
    agent_role_contracts_path: Path,
    proposal_intent_path: Path,
) -> Path:
    """Write a deterministic, read-only analysis-role stub artifact."""
    payload = analysis_notes_payload(
        repo_root=repo_root,
        run_id=run_id,
        round_id=round_id,
        round_index=round_index,
        round_dir=round_dir,
        train_metrics_before=train_metrics_before,
        validation_metrics_before=validation_metrics_before,
        holdout_metrics_before=holdout_metrics_before,
        train_report_path=train_report_path,
        validation_report_path=validation_report_path,
        holdout_report_path=holdout_report_path,
        agent_role_contracts_path=agent_role_contracts_path,
        proposal_intent_path=proposal_intent_path,
    )
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(analysis_notes_markdown(payload), encoding="utf-8")
    return output_path


def analysis_notes_payload(
    *,
    repo_root: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    round_dir: Path,
    train_metrics_before: dict[str, float | int],
    validation_metrics_before: dict[str, float | int],
    holdout_metrics_before: dict[str, float | int],
    train_report_path: Path,
    validation_report_path: Path,
    holdout_report_path: Path,
    agent_role_contracts_path: Path,
    proposal_intent_path: Path,
) -> dict[str, object]:
    """Return the JSON payload for the read-only analysis stub."""
    metrics = {
        "train": compact_metrics(train_metrics_before),
        "validation": compact_metrics(validation_metrics_before),
        "holdout": compact_metrics(holdout_metrics_before),
    }
    return {
        "schema_version": ANALYSIS_NOTES_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "round_index": round_index,
        "agent_role": "analysis",
        "execution_mode": "stub_contract",
        "implemented": False,
        "round_dir": relative_path(round_dir, repo_root),
        "consumed_artifacts": {
            "agent_role_contracts": relative_path(agent_role_contracts_path, repo_root),
            "proposal_intent": relative_path(proposal_intent_path, repo_root),
            "train_report_before": relative_path(train_report_path, repo_root),
            "validation_report_before": relative_path(validation_report_path, repo_root),
            "holdout_report_before": relative_path(holdout_report_path, repo_root),
        },
        "metrics_before": metrics,
        "observations": observations(metrics),
        "constraints": [
            "analysis stub is read-only",
            "analysis stub cannot accept or reject patches",
            "deterministic policy gates keep final acceptance authority",
        ],
        "recommendation": {
            "action": "continue_to_strategy_modifier",
            "reason": "V0.5 analysis role is a contract-only stub.",
            "can_change_routing": False,
            "can_change_acceptance": False,
        },
        "produced_artifacts": {
            "analysis_notes_json": relative_path(round_dir / "analysis_notes.json", repo_root),
            "analysis_notes_markdown": relative_path(round_dir / "analysis_notes.md", repo_root),
        },
    }


def compact_metrics(metrics: dict[str, float | int]) -> dict[str, float | int]:
    """Return the fields the analysis stub is allowed to inspect."""
    keys = (
        "ev",
        "total_pnl",
        "max_drawdown",
        "trade_count",
        "fill_rate",
        "avg_slippage",
    )
    return {key: metrics[key] for key in keys if key in metrics}


def observations(metrics: dict[str, object]) -> list[str]:
    """Return deterministic analysis observations from before metrics."""
    validation = metrics.get("validation", {})
    holdout = metrics.get("holdout", {})
    validation_trade_count = metric_number(validation, "trade_count")
    holdout_trade_count = metric_number(holdout, "trade_count")
    validation_ev = metric_number(validation, "ev")
    holdout_ev = metric_number(holdout, "ev")
    return [
        f"validation_trade_count={validation_trade_count:g}",
        f"holdout_trade_count={holdout_trade_count:g}",
        f"validation_ev={validation_ev:.6f}",
        f"holdout_ev={holdout_ev:.6f}",
    ]


def metric_number(metrics: object, key: str) -> float:
    """Return a metric value as a float for stable observation text."""
    if not isinstance(metrics, dict):
        return 0.0
    value = metrics.get(key, 0.0)
    return float(value) if isinstance(value, int | float) else 0.0


def analysis_notes_markdown(payload: dict[str, object]) -> str:
    """Return a human-readable render of the analysis stub output."""
    observations_text = "\n".join(
        f"- {item}" for item in payload.get("observations", [])
    )
    return "\n".join(
        [
            "# Analysis Notes",
            "",
            f"Run: {payload['run_id']}",
            f"Round: {payload['round_id']}",
            "Role: analysis",
            "Mode: stub_contract",
            "",
            "## Observations",
            observations_text,
            "",
            "## Recommendation",
            "continue_to_strategy_modifier",
            "",
        ]
    )


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
