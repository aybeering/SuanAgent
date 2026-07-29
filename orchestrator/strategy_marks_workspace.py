"""Isolated strategy-marks workspace helpers for the dead-strategy endpoint."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from orchestrator.workspace_manager import (
    safe_workspace_segment,
    should_ignore_snapshot_path,
    workspace_mutation_errors,
    workspace_snapshot,
    workspace_snapshot_digest,
)


STRATEGY_MARKS_WORKSPACE_KIND = "strategy_marks_v1"
STRATEGY_MARKS_MANIFEST_SCHEMA_VERSION = "strategy_marks_workspace_manifest_v1"
RUN_REQUEST_SCHEMA_VERSION = "strategy_marks_run_request_v1"

INCLUDE_DIRS = ("backtester", "strategies")
INCLUDE_FILES = ("strategies/__init__.py",)

ALLOWED_OUTPUT_PATHS = (
    "output/mark_points.json",
    "output/mark_points.csv",
    "output/marks_view.html",
    "output/run_receipt.json",
)

READONLY_PREFIXES = (
    "input/",
    "backtester/",
    "strategies/",
)

INPUT_RUN_REQUEST = "input/run_request.json"
INPUT_MARKET_CSV = "input/market.csv"


def strategy_marks_workspace_path(
    *,
    workspace_root: Path,
    run_id: str,
    workspace_id: str,
) -> Path:
    """Return the deterministic path for one strategy-marks workspace."""
    return (
        workspace_root
        / safe_workspace_segment(run_id)
        / "strategy_marks"
        / safe_workspace_segment(workspace_id)
    )


def create_strategy_marks_workspace(
    *,
    repo_root: Path,
    workspace_root: Path,
    run_id: str,
    workspace_id: str,
    split: str,
    market_csv_source: Path,
    strategy_module: str = "strategies/current_strategy.py",
) -> Path:
    """Create a narrow isolated workspace with read-only input packed in."""
    workspace_path = strategy_marks_workspace_path(
        workspace_root=workspace_root,
        run_id=run_id,
        workspace_id=workspace_id,
    )
    if workspace_path.exists():
        raise FileExistsError(f"Workspace already exists: {workspace_path}")
    workspace_path.mkdir(parents=True)

    for directory in INCLUDE_DIRS:
        source = repo_root / directory
        if not source.exists():
            raise FileNotFoundError(f"Missing include directory: {source}")
        shutil.copytree(
            source,
            workspace_path / directory,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

    (workspace_path / "input").mkdir(parents=True, exist_ok=True)
    (workspace_path / "output").mkdir(parents=True, exist_ok=True)

    if not market_csv_source.exists():
        raise FileNotFoundError(f"Missing market CSV: {market_csv_source}")
    shutil.copy2(market_csv_source, workspace_path / INPUT_MARKET_CSV)

    run_request = {
        "schema_version": RUN_REQUEST_SCHEMA_VERSION,
        "run_id": run_id,
        "workspace_id": workspace_id,
        "split": split,
        "market_csv": INPUT_MARKET_CSV,
        "strategy_module": strategy_module,
    }
    write_json(workspace_path / INPUT_RUN_REQUEST, run_request)

    snapshot = workspace_snapshot(workspace_path)
    payload = strategy_marks_manifest_payload(
        repo_root=repo_root,
        workspace_path=workspace_path,
        run_id=run_id,
        workspace_id=workspace_id,
        snapshot=snapshot,
        input_digests=compute_input_digests(workspace_path),
    )
    write_json(workspace_path / "workspace_manifest.json", payload)
    return workspace_path


def strategy_marks_manifest_payload(
    *,
    repo_root: Path,
    workspace_path: Path,
    run_id: str,
    workspace_id: str,
    snapshot: dict[str, str],
    input_digests: dict[str, str],
) -> dict[str, Any]:
    """Return a JSON-friendly strategy-marks workspace manifest."""
    return {
        "schema_version": STRATEGY_MARKS_MANIFEST_SCHEMA_VERSION,
        "workspace_kind": STRATEGY_MARKS_WORKSPACE_KIND,
        "run_id": run_id,
        "workspace_id": workspace_id,
        "source_repo_root": str(repo_root.resolve()),
        "workspace_path": str(workspace_path.resolve()),
        "include_dirs": list(INCLUDE_DIRS),
        "include_files": list(INCLUDE_FILES),
        "input_digests": input_digests,
        "initial_snapshot": {
            "file_count": len(snapshot),
            "sha256": workspace_snapshot_digest(snapshot),
        },
        "mutation_policy": {
            "allowed_paths": list(ALLOWED_OUTPUT_PATHS),
            "reject_unlisted_changes": True,
            "readonly_prefixes": list(READONLY_PREFIXES),
        },
    }


def compute_input_digests(workspace_path: Path) -> dict[str, str]:
    """Return sha256 digests for the packed input files."""
    return {
        "run_request_json": file_sha256(workspace_path / INPUT_RUN_REQUEST),
        "market_csv": file_sha256(workspace_path / INPUT_MARKET_CSV),
    }


def verify_input_digests(
    *,
    workspace_path: Path,
    expected: dict[str, str],
) -> tuple[bool, tuple[str, ...]]:
    """Return whether packed inputs still match the manifest digests."""
    current = compute_input_digests(workspace_path)
    errors: list[str] = []
    for key, digest in expected.items():
        if current.get(key) != digest:
            errors.append(f"input digest mismatch: {key}")
    return (not errors, tuple(errors))


def load_workspace_manifest(workspace_path: Path) -> dict[str, Any]:
    """Load the strategy-marks workspace manifest."""
    path = workspace_path / "workspace_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("workspace_manifest.json must be an object")
    return payload


def assert_workspace_mutations_allowed(
    *,
    workspace_path: Path,
    before_snapshot: dict[str, str],
) -> tuple[str, ...]:
    """Return mutation errors against the strategy-marks allowlist."""
    after = workspace_snapshot(workspace_path)
    return workspace_mutation_errors(
        before=before_snapshot,
        after=after,
        allowed_paths=set(ALLOWED_OUTPUT_PATHS),
    )


def file_sha256(path: Path) -> str:
    """Return the sha256 hex digest for one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    """Write deterministic pretty JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def ignored_snapshot_path(relative_path: str) -> bool:
    """Expose snapshot ignore helper for tests."""
    return should_ignore_snapshot_path(relative_path)
