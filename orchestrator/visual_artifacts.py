"""Round-level visual artifact manifest generation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


VISUAL_ARTIFACTS_SCHEMA_VERSION = "visual_artifacts_manifest_v1"


def write_visual_artifacts_manifest(
    *,
    output_path: Path,
    repo_root: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    round_dir: Path,
    chart_path: Path,
    timeline_path: Path,
) -> Path:
    """Write a deterministic manifest for visual-review input artifacts."""
    payload = visual_artifacts_manifest_payload(
        repo_root=repo_root,
        run_id=run_id,
        round_id=round_id,
        round_index=round_index,
        round_dir=round_dir,
        chart_path=chart_path,
        timeline_path=timeline_path,
    )
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def visual_artifacts_manifest_payload(
    *,
    repo_root: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    round_dir: Path,
    chart_path: Path,
    timeline_path: Path,
) -> dict[str, object]:
    """Return the JSON payload for visual artifact indexing."""
    return {
        "schema_version": VISUAL_ARTIFACTS_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "round_index": round_index,
        "round_dir": relative_path(round_dir, repo_root),
        "execution_mode": "deterministic_static_artifacts",
        "visual_agent_enabled": False,
        "artifacts": [
            artifact_record(
                repo_root=repo_root,
                path=chart_path,
                artifact_id="chart_html",
                artifact_type="chart",
                schema_marker='name="suan-chart-schema" content="round_chart_v1"',
                description="Cumulative PnL chart and metrics table.",
                source_files=(
                    round_dir / "train_metrics_before.json",
                    round_dir / "metrics_before.json",
                    round_dir / "holdout_metrics_before.json",
                    round_dir / "train_trades_before.csv",
                    round_dir / "trades_before.csv",
                    round_dir / "holdout_trades_before.csv",
                ),
            ),
            artifact_record(
                repo_root=repo_root,
                path=timeline_path,
                artifact_id="trade_timeline_html",
                artifact_type="timeline",
                schema_marker=(
                    'name="suan-timeline-schema" content="trade_timeline_v1"'
                ),
                description="Time-ordered before-trade table with PnL and slippage.",
                source_files=(
                    round_dir / "train_trades_before.csv",
                    round_dir / "trades_before.csv",
                    round_dir / "holdout_trades_before.csv",
                ),
            ),
        ],
        "supporting_artifacts": {
            "analysis_notes": relative_path(round_dir / "analysis_notes.json", repo_root),
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
        "policy": {
            "external_network_assets_allowed": False,
            "visual_agent_can_change_acceptance": False,
            "visual_agent_can_change_routing": False,
        },
    }


def artifact_record(
    *,
    repo_root: Path,
    path: Path,
    artifact_id: str,
    artifact_type: str,
    schema_marker: str,
    description: str,
    source_files: tuple[Path, ...],
) -> dict[str, object]:
    """Return a stable manifest record for one visual artifact."""
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "path": relative_path(path, repo_root),
        "format": "html",
        "schema_marker": schema_marker,
        "description": description,
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() else 0,
        "sha256": file_sha256(path) if path.exists() else "",
        "external_dependencies": False,
        "source_files": [
            relative_path(source_path, repo_root)
            for source_path in source_files
        ],
    }


def file_sha256(path: Path) -> str:
    """Return a SHA-256 digest for a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
