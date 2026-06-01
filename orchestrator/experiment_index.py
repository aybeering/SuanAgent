"""Append-only experiment index helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def append_experiment_index(
    *,
    experiments_dir: Path,
    record: dict[str, object],
) -> Path:
    """Append one JSONL record to the experiment index."""
    experiments_dir.mkdir(parents=True, exist_ok=True)
    index_path = experiments_dir / "index.jsonl"
    payload = {
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **record,
    }
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return index_path


def read_experiment_index(experiments_dir: Path = Path("experiments")) -> list[dict[str, object]]:
    """Read experiment index records from JSONL."""
    index_path = experiments_dir / "index.jsonl"
    if not index_path.exists():
        return []

    records: list[dict[str, object]] = []
    with index_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {index_path}:{line_number}") from exc
            records.append(payload)
    return records


def recent_experiments(
    *,
    experiments_dir: Path = Path("experiments"),
    limit: int = 10,
) -> list[dict[str, object]]:
    """Return the most recent experiment records."""
    if limit <= 0:
        return []
    return read_experiment_index(experiments_dir)[-limit:]
