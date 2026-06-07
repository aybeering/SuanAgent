"""Shared manifest summary helpers for saved round replay reports."""

from __future__ import annotations

from typing import Any


def manifest_round_replay_summary(
    *,
    round_id: str,
    replay_report: dict[str, Any],
) -> dict[str, object]:
    """Return the compact replay row stored in manifest.rounds."""
    return {
        "path": f"{round_id}/round_replay.json",
        "markdown_path": f"{round_id}/round_replay.md",
        "ok": bool(replay_report.get("ok", False)),
        "run_probe": bool(replay_report.get("run_probe", False)),
        "replayed_attempt_count": int(
            replay_report.get("replayed_attempt_count", 0) or 0
        ),
        "failure_stage": str(replay_report.get("failure_stage", "none")),
        "failure_code": str(replay_report.get("failure_code", "none")),
        "failure_message": str(replay_report.get("failure_message", "")),
    }
