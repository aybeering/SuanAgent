"""Round-local input/output bundle protocol for modifier agents."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


AGENT_BUNDLE_SCHEMA_VERSION = "agent_bundle_v1"
INPUT_BUNDLE_DIRNAME = "agent_input_bundle"
OUTPUT_BUNDLE_DIRNAME = "agent_output_bundle"

INPUT_BUNDLE_FILES = (
    "agent_role_contracts.json",
    "analysis_notes.json",
    "analysis_notes.md",
    "visual_review.json",
    "visual_review.md",
    "agent_input.json",
    "agent_context.md",
    "agent_context.json",
    "proposal_intent.json",
    "proposal_intent.md",
    "train_report_before.md",
    "report_before.md",
    "holdout_report_before.md",
)

OUTPUT_BUNDLE_FILES = (
    "raw_agent_output.txt",
    "proposal.json",
    "patch.diff",
    "agent_validation.json",
)


def write_agent_bundle_manifest(
    *,
    round_dir: Path,
    repo_root: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    agent_name: str,
) -> Path:
    """Create input/output bundle dirs and write their manifest."""
    input_dir = round_dir / INPUT_BUNDLE_DIRNAME
    output_dir = round_dir / OUTPUT_BUNDLE_DIRNAME
    sync_bundle_dir(
        round_dir=round_dir,
        bundle_dir=input_dir,
        filenames=INPUT_BUNDLE_FILES,
    )
    sync_bundle_dir(
        round_dir=round_dir,
        bundle_dir=output_dir,
        filenames=OUTPUT_BUNDLE_FILES,
    )
    manifest = build_agent_bundle_manifest(
        round_dir=round_dir,
        repo_root=repo_root,
        run_id=run_id,
        round_id=round_id,
        round_index=round_index,
        agent_name=agent_name,
        input_dir=input_dir,
        output_dir=output_dir,
    )
    output_path = round_dir / "agent_bundle_manifest.json"
    output_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def write_agent_input_bundle(*, round_dir: Path) -> Path:
    """Create the read-only input bundle before an external agent is invoked."""
    input_dir = round_dir / INPUT_BUNDLE_DIRNAME
    sync_bundle_dir(
        round_dir=round_dir,
        bundle_dir=input_dir,
        filenames=INPUT_BUNDLE_FILES,
    )
    return input_dir


def sync_bundle_dir(
    *,
    round_dir: Path,
    bundle_dir: Path,
    filenames: tuple[str, ...],
) -> None:
    """Copy selected round artifacts into one bundle directory."""
    bundle_dir.mkdir(parents=True, exist_ok=True)
    for filename in filenames:
        source = round_dir / filename
        if source.exists():
            shutil.copy2(source, bundle_dir / filename)


def build_agent_bundle_manifest(
    *,
    round_dir: Path,
    repo_root: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    agent_name: str,
    input_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Return a JSON-friendly bundle manifest."""
    return {
        "schema_version": AGENT_BUNDLE_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "round_index": round_index,
        "agent_name": agent_name,
        "input_bundle_dir": relative_path(input_dir, repo_root),
        "output_bundle_dir": relative_path(output_dir, repo_root),
        "input_files": bundle_file_records(input_dir, repo_root),
        "output_files": bundle_file_records(output_dir, repo_root),
        "policy": {
            "input_bundle_read_only": True,
            "output_bundle_write_only_for_external_agents": True,
            "strategy_changes_must_be_patch_only": True,
        },
        "source_round_dir": relative_path(round_dir, repo_root),
    }


def bundle_file_records(bundle_dir: Path, repo_root: Path) -> list[dict[str, object]]:
    """Return stable file records for a bundle directory."""
    records: list[dict[str, object]] = []
    for path in sorted(bundle_dir.iterdir()):
        if not path.is_file():
            continue
        records.append(
            {
                "path": relative_path(path, repo_root),
                "name": path.name,
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    return records


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def file_sha256(path: Path) -> str:
    """Return a file SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
