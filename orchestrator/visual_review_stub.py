"""Deterministic visual-review role stub."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


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
    chart_path: Path,
    timeline_path: Path,
    visual_artifacts_manifest_path: Path,
) -> Path:
    """Write a deterministic, read-only visual-review stub artifact."""
    payload = visual_review_payload(
        repo_root=repo_root,
        run_id=run_id,
        round_id=round_id,
        round_index=round_index,
        round_dir=round_dir,
        analysis_notes_path=analysis_notes_path,
        chart_path=chart_path,
        timeline_path=timeline_path,
        visual_artifacts_manifest_path=visual_artifacts_manifest_path,
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
    chart_path: Path,
    timeline_path: Path,
    visual_artifacts_manifest_path: Path,
) -> dict[str, object]:
    """Return the JSON payload for the contract-only visual-review stub."""
    trade_rows = {
        "train": csv_data_row_count(round_dir / "train_trades_before.csv"),
        "validation": csv_data_row_count(round_dir / "trades_before.csv"),
        "holdout": csv_data_row_count(round_dir / "holdout_trades_before.csv"),
    }
    manifest = load_json_object(visual_artifacts_manifest_path)
    artifact_summaries = visual_artifact_summaries(manifest)
    visual_policy = visual_policy_summary(manifest)
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
            "visual_artifacts_manifest": relative_path(
                visual_artifacts_manifest_path,
                repo_root,
            ),
            "chart_html": relative_path(chart_path, repo_root),
            "trade_timeline_html": relative_path(timeline_path, repo_root),
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
        "expected_future_artifacts": [],
        "chart_artifacts": {
            "chart_html": relative_path(chart_path, repo_root),
            "rendering_mode": "deterministic_static_html",
            "external_dependencies": False,
        },
        "timeline_artifacts": {
            "trade_timeline_html": relative_path(timeline_path, repo_root),
            "rendering_mode": "deterministic_static_html",
            "external_dependencies": False,
        },
        "visual_artifacts_summary": {
            "manifest_path": relative_path(visual_artifacts_manifest_path, repo_root),
            "manifest_loaded": bool(manifest),
            "artifact_count": len(artifact_summaries),
            "artifacts": artifact_summaries,
            "policy": visual_policy,
        },
        "trade_row_counts": trade_rows,
        "checks": {
            "chart_rendering_enabled": True,
            "visual_agent_enabled": False,
            "trade_files_present": trade_files_present(round_dir),
            "chart_file_present": chart_path.exists(),
            "timeline_file_present": timeline_path.exists(),
            "can_change_acceptance": False,
            "can_change_routing": False,
        },
        "observations": [
            f"train_trades_before_rows={trade_rows['train']}",
            f"validation_trades_before_rows={trade_rows['validation']}",
            f"holdout_trades_before_rows={trade_rows['holdout']}",
            "chart_html_generated",
            "trade_timeline_html_generated",
            "visual_agent_disabled",
            "visual_artifacts_manifest_generated",
            f"visual_artifact_count={len(artifact_summaries)}",
            *artifact_observations(artifact_summaries),
            *policy_observations(visual_policy),
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


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk, returning an empty dict on parse failure."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def visual_artifact_summaries(manifest: dict[str, Any]) -> list[dict[str, object]]:
    """Return compact deterministic summaries from the visual artifact manifest."""
    artifacts = manifest.get("artifacts", [])
    if not isinstance(artifacts, list):
        return []
    summaries: list[dict[str, object]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        source_files = artifact.get("source_files", [])
        source_count = len(source_files) if isinstance(source_files, list) else 0
        sha256 = str(artifact.get("sha256", ""))
        summaries.append(
            {
                "artifact_id": str(artifact.get("artifact_id", "")),
                "artifact_type": str(artifact.get("artifact_type", "")),
                "path": str(artifact.get("path", "")),
                "bytes": int_or_zero(artifact.get("bytes", 0)),
                "sha256_prefix": sha256[:12],
                "source_file_count": source_count,
                "external_dependencies": bool(
                    artifact.get("external_dependencies", True)
                ),
                "schema_marker": str(artifact.get("schema_marker", "")),
            }
        )
    return sorted(summaries, key=lambda row: str(row["artifact_id"]))


def visual_policy_summary(manifest: dict[str, Any]) -> dict[str, bool]:
    """Return the visual input policy from the manifest."""
    policy = manifest.get("policy", {})
    if not isinstance(policy, dict):
        return {
            "external_network_assets_allowed": True,
            "visual_agent_can_change_acceptance": True,
            "visual_agent_can_change_routing": True,
        }
    return {
        "external_network_assets_allowed": bool(
            policy.get("external_network_assets_allowed", True)
        ),
        "visual_agent_can_change_acceptance": bool(
            policy.get("visual_agent_can_change_acceptance", True)
        ),
        "visual_agent_can_change_routing": bool(
            policy.get("visual_agent_can_change_routing", True)
        ),
    }


def artifact_observations(artifact_summaries: list[dict[str, object]]) -> list[str]:
    """Return stable observation strings for visual artifacts."""
    return [
        "visual_artifact="
        f"{artifact['artifact_id']}:"
        f"bytes={artifact['bytes']}:"
        f"sources={artifact['source_file_count']}:"
        f"sha256_prefix={artifact['sha256_prefix']}"
        for artifact in artifact_summaries
    ]


def policy_observations(policy: dict[str, bool]) -> list[str]:
    """Return stable observation strings for visual policy fields."""
    return [
        f"visual_policy_external_assets_allowed={str(policy['external_network_assets_allowed']).lower()}",
        f"visual_policy_can_change_acceptance={str(policy['visual_agent_can_change_acceptance']).lower()}",
        f"visual_policy_can_change_routing={str(policy['visual_agent_can_change_routing']).lower()}",
    ]


def int_or_zero(value: object) -> int:
    """Return an integer value or zero."""
    return value if isinstance(value, int) else 0


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
