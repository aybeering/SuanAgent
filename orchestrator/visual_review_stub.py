"""Deterministic visual-review role stub."""

from __future__ import annotations

import csv
import json
from pathlib import Path


VISUAL_REVIEW_SCHEMA_VERSION = "visual_review_v1"


def write_visual_review(
    *,
    output_path: Path,
    markdown_path: Path,
    repo_root: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    round_dir: Path,
    analysis_notes_path: Path,
) -> Path:
    """Write a deterministic, read-only visual-review stub artifact."""
    payload = visual_review_payload(
        repo_root=repo_root,
        run_id=run_id,
        round_id=round_id,
        round_index=round_index,
        round_dir=round_dir,
        analysis_notes_path=analysis_notes_path,
    )
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(visual_review_markdown(payload), encoding="utf-8")
    return output_path


def visual_review_payload(
    *,
    repo_root: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    round_dir: Path,
    analysis_notes_path: Path,
) -> dict[str, object]:
    """Return the JSON payload for the contract-only visual-review stub."""
    trade_rows = {
        "train": csv_data_row_count(round_dir / "train_trades_before.csv"),
        "validation": csv_data_row_count(round_dir / "trades_before.csv"),
        "holdout": csv_data_row_count(round_dir / "holdout_trades_before.csv"),
    }
    return {
        "schema_version": VISUAL_REVIEW_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "round_index": round_index,
        "agent_role": "visual_review",
        "execution_mode": "stub_contract",
        "implemented": False,
        "round_dir": relative_path(round_dir, repo_root),
        "consumed_artifacts": {
            "analysis_notes": relative_path(analysis_notes_path, repo_root),
            "train_trades_before": relative_path(
                round_dir / "train_trades_before.csv",
                repo_root,
            ),
            "validation_trades_before": relative_path(
                round_dir / "trades_before.csv",
                repo_root,
            ),
            "holdout_trades_before": relative_path(
                round_dir / "holdout_trades_before.csv",
                repo_root,
            ),
            "train_report_before": relative_path(
                round_dir / "train_report_before.md",
                repo_root,
            ),
            "validation_report_before": relative_path(
                round_dir / "report_before.md",
                repo_root,
            ),
            "holdout_report_before": relative_path(
                round_dir / "holdout_report_before.md",
                repo_root,
            ),
        },
        "expected_future_artifacts": [
            "chart.html",
            "trade_timeline.html",
        ],
        "trade_row_counts": trade_rows,
        "checks": {
            "chart_rendering_enabled": False,
            "visual_agent_enabled": False,
            "trade_files_present": trade_files_present(round_dir),
            "can_change_acceptance": False,
            "can_change_routing": False,
        },
        "observations": [
            f"train_trades_before_rows={trade_rows['train']}",
            f"validation_trades_before_rows={trade_rows['validation']}",
            f"holdout_trades_before_rows={trade_rows['holdout']}",
            "chart_rendering_disabled",
        ],
        "recommendation": {
            "action": "continue_without_visual_gate",
            "reason": "V0.5 visual review role is a contract-only stub.",
            "can_change_acceptance": False,
            "can_change_routing": False,
        },
        "produced_artifacts": {
            "visual_review_json": relative_path(
                round_dir / "visual_review.json",
                repo_root,
            ),
            "visual_review_markdown": relative_path(
                round_dir / "visual_review.md",
                repo_root,
            ),
        },
    }


def csv_data_row_count(path: Path) -> int:
    """Return the number of data rows in a CSV file, excluding the header."""
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        rows = list(reader)
    return max(len(rows) - 1, 0)


def trade_files_present(round_dir: Path) -> bool:
    """Return whether all before-trade files needed by the stub exist."""
    return all(
        (round_dir / filename).exists()
        for filename in (
            "train_trades_before.csv",
            "trades_before.csv",
            "holdout_trades_before.csv",
        )
    )


def visual_review_markdown(payload: dict[str, object]) -> str:
    """Return a human-readable render of the visual-review stub output."""
    observations_text = "\n".join(
        f"- {item}" for item in payload.get("observations", [])
    )
    return "\n".join(
        [
            "# Visual Review",
            "",
            f"Run: {payload['run_id']}",
            f"Round: {payload['round_id']}",
            "Role: visual_review",
            "Mode: stub_contract",
            "",
            "## Observations",
            observations_text,
            "",
            "## Recommendation",
            "continue_without_visual_gate",
            "",
        ]
    )


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
