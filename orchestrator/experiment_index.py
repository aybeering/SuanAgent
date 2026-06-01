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
