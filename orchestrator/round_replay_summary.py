"""Shared manifest summary helpers for saved round replay reports."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def manifest_round_replay_summary(
    *,
    round_id: str,
    replay_report: dict[str, Any],
    json_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, object]:
    """Return the compact replay row stored in manifest.rounds."""
    return {
        "path": f"{round_id}/round_replay.json",
        "markdown_path": f"{round_id}/round_replay.md",
        **file_digest_fields(prefix="json", path=json_path),
        **file_digest_fields(prefix="markdown", path=markdown_path),
        "ok": bool(replay_report.get("ok", False)),
        "run_probe": bool(replay_report.get("run_probe", False)),
        "replayed_attempt_count": int(
            replay_report.get("replayed_attempt_count", 0) or 0
        ),
        "failure_stage": str(replay_report.get("failure_stage", "none")),
        "failure_code": str(replay_report.get("failure_code", "none")),
        "failure_message": str(replay_report.get("failure_message", "")),
    }


def file_digest_fields(*, prefix: str, path: Path | None) -> dict[str, object]:
    """Return stable byte and SHA-256 fields for an optional artifact path."""
    if path is None or not path.exists():
        return {f"{prefix}_bytes": 0, f"{prefix}_sha256": ""}
    data = path.read_bytes()
    return {
        f"{prefix}_bytes": len(data),
        f"{prefix}_sha256": hashlib.sha256(data).hexdigest(),
    }
