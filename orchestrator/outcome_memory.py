"""Append-only proposal outcome memory."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from orchestrator.proposal import StrategyProposal


MEMORY_FILENAME = "memory.jsonl"


def append_outcome_memory(
    *,
    experiments_dir: Path,
    record: dict[str, object],
) -> Path:
    """Append one proposal outcome record to experiment memory."""
    experiments_dir.mkdir(parents=True, exist_ok=True)
    memory_path = experiments_dir / MEMORY_FILENAME
    payload = {
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **record,
    }
    with memory_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return memory_path


def read_outcome_memory(
    experiments_dir: Path = Path("experiments"),
) -> list[dict[str, object]]:
    """Read proposal outcome memory records from JSONL."""
    memory_path = experiments_dir / MEMORY_FILENAME
    if not memory_path.exists():
        return []

    records: list[dict[str, object]] = []
    with memory_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {memory_path}:{line_number}") from exc
            records.append(payload)
    return records


def recent_outcomes(
    *,
    experiments_dir: Path = Path("experiments"),
    limit: int = 10,
) -> list[dict[str, object]]:
    """Return recent proposal outcome memory records."""
    if limit <= 0:
        return []
    return read_outcome_memory(experiments_dir)[-limit:]


def build_outcome_record(
    *,
    run_id: str,
    round_id: str,
    proposal: StrategyProposal,
    decision: dict[str, object],
    train_metrics_before: dict[str, float | int],
    train_metrics_after: dict[str, float | int],
    validation_metrics_before: dict[str, float | int],
    validation_metrics_after: dict[str, float | int],
    holdout_metrics_before: dict[str, float | int],
    holdout_metrics_after: dict[str, float | int],
) -> dict[str, object]:
    """Build a compact, queryable memory record for one proposal outcome."""
    return {
        "kind": "proposal_outcome",
        "run_id": run_id,
        "round_id": round_id,
        "agent_name": proposal.agent_name,
        "target_file": proposal.target_file,
        "summary": proposal.summary,
        "accepted": bool(decision.get("accepted", False)),
        "reasons": decision.get("reasons", []),
        "applicable": proposal.applicable,
        "patch_sha256": proposal.patch_sha256,
        "is_repeat_patch": proposal.is_repeat_patch,
        "repeat_of_round": proposal.repeat_of_round,
        "hypotheses": list(proposal.hypotheses),
        "expected_metric_change": proposal.expected_metric_change,
        "quality_checks": proposal.quality_checks or {},
        "train_ev_delta": metric_delta(train_metrics_before, train_metrics_after, "ev"),
        "validation_ev_delta": metric_delta(
            validation_metrics_before,
            validation_metrics_after,
            "ev",
        ),
        "holdout_ev_delta": metric_delta(
            holdout_metrics_before,
            holdout_metrics_after,
            "ev",
        ),
        "validation_trade_count_before": validation_metrics_before.get("trade_count", 0),
        "validation_trade_count_after": validation_metrics_after.get("trade_count", 0),
    }


def metric_delta(
    before: dict[str, float | int],
    after: dict[str, float | int],
    key: str,
) -> float:
    """Return a rounded metric delta."""
    return round(float(after.get(key, 0.0)) - float(before.get(key, 0.0)), 6)
