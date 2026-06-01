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


def failed_patch_outcomes(
    *,
    experiments_dir: Path,
    patch_sha256: str,
    exclude_run_id: str = "",
) -> list[dict[str, object]]:
    """Return failed memory records for a patch hash."""
    if not patch_sha256:
        return []
    return [
        record
        for record in read_outcome_memory(experiments_dir)
        if record.get("patch_sha256") == patch_sha256
        and record.get("accepted") is False
        and str(record.get("run_id", "")) != exclude_run_id
    ]


def failed_direction_outcomes(
    *,
    experiments_dir: Path,
    direction_tag: str,
    exclude_run_id: str = "",
) -> list[dict[str, object]]:
    """Return failed memory records for a proposal direction tag."""
    if not direction_tag:
        return []
    return [
        record
        for record in read_outcome_memory(experiments_dir)
        if record.get("direction_tag") == direction_tag
        and record.get("accepted") is False
        and str(record.get("run_id", "")) != exclude_run_id
    ]


def memory_filter_rejection_reason(
    *,
    experiments_dir: Path,
    patch_sha256: str,
    threshold: int,
    exclude_run_id: str = "",
) -> str:
    """Return a rejection reason when a patch has failed too often."""
    if threshold <= 0 or not patch_sha256:
        return ""
    failures = failed_patch_outcomes(
        experiments_dir=experiments_dir,
        patch_sha256=patch_sha256,
        exclude_run_id=exclude_run_id,
    )
    if len(failures) < threshold:
        return ""
    short_hash = patch_sha256[:12]
    return (
        f"memory filter rejected patch {short_hash}: "
        f"{len(failures)} prior failed outcomes >= threshold {threshold}"
    )


def direction_filter_rejection_reason(
    *,
    experiments_dir: Path,
    direction_tag: str,
    threshold: int,
    exclude_run_id: str = "",
) -> str:
    """Return a rejection reason when a direction has failed too often."""
    if threshold <= 0 or not direction_tag:
        return ""
    failures = failed_direction_outcomes(
        experiments_dir=experiments_dir,
        direction_tag=direction_tag,
        exclude_run_id=exclude_run_id,
    )
    if len(failures) < threshold:
        return ""
    return (
        f"memory filter rejected direction {direction_tag}: "
        f"{len(failures)} prior failed outcomes >= threshold {threshold}"
    )


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
        "protocol_version": proposal.protocol_version,
        "agent_name": proposal.agent_name,
        "direction_tag": proposal.direction_tag,
        "target_file": proposal.target_file,
        "summary": proposal.summary,
        "accepted": bool(decision.get("accepted", False)),
        "reasons": decision.get("reasons", []),
        "applicable": proposal.applicable,
        "contract_errors": list(proposal.contract_errors),
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
