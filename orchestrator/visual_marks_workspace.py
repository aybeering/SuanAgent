"""Isolated visual-marks workspace helpers for the stub visual agent."""

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


VISUAL_MARKS_WORKSPACE_KIND = "visual_marks_v1"
VISUAL_MARKS_MANIFEST_SCHEMA_VERSION = "visual_marks_workspace_manifest_v1"
RUN_REQUEST_SCHEMA_VERSION = "visual_marks_run_request_v1"

MARKING_SCRIPT_REL = "tools/write_mark_points.py"
AGENT_ENTRY_REL = "agent/stub_visual_agent.py"
TOOLS_README_REL = "tools/README.md"

ALLOWED_OUTPUT_PATHS = (
    "output/collected_points.json",
    "output/mark_points.json",
    "output/mark_points.csv",
    "output/agent_trace.json",
    "output/run_receipt.json",
)

READONLY_PREFIXES = (
    "input/",
    "tools/",
    "agent/",
)

INPUT_RUN_REQUEST = "input/run_request.json"
INPUT_PAGES_DIR = "input/pages"

REPO_MARKING_SCRIPT = "tools/visual_write_mark_points.py"
REPO_STUB_AGENT = "tools/stub_visual_agent.py"
REPO_TOOLS_README = "tools/visual_marks_tools_README.md"


def visual_marks_workspace_path(
    *,
    workspace_root: Path,
    run_id: str,
    workspace_id: str,
) -> Path:
    """Return the deterministic path for one visual-marks workspace."""
    return (
        workspace_root
        / safe_workspace_segment(run_id)
        / "visual_marks"
        / safe_workspace_segment(workspace_id)
    )


def create_visual_marks_workspace(
    *,
    repo_root: Path,
    workspace_root: Path,
    run_id: str,
    workspace_id: str,
    html_sources: list[Path],
) -> Path:
    """Create a narrow workspace packed with n HTML pages and marking tools."""
    if not html_sources:
        raise ValueError("At least one HTML source is required")

    workspace_path = visual_marks_workspace_path(
        workspace_root=workspace_root,
        run_id=run_id,
        workspace_id=workspace_id,
    )
    if workspace_path.exists():
        raise FileExistsError(f"Workspace already exists: {workspace_path}")
    workspace_path.mkdir(parents=True)

    pages_dir = workspace_path / INPUT_PAGES_DIR
    pages_dir.mkdir(parents=True, exist_ok=True)
    (workspace_path / "output").mkdir(parents=True, exist_ok=True)
    (workspace_path / "tools").mkdir(parents=True, exist_ok=True)
    (workspace_path / "agent").mkdir(parents=True, exist_ok=True)

    html_files: list[str] = []
    for index, source in enumerate(html_sources, start=1):
        if not source.exists():
            raise FileNotFoundError(f"Missing HTML source: {source}")
        relative = f"{INPUT_PAGES_DIR}/page_{index:03d}.html"
        shutil.copy2(source, workspace_path / relative)
        html_files.append(relative)

    marking_src = repo_root / REPO_MARKING_SCRIPT
    agent_src = repo_root / REPO_STUB_AGENT
    readme_src = repo_root / REPO_TOOLS_README
    if not marking_src.exists():
        raise FileNotFoundError(f"Missing marking script: {marking_src}")
    if not agent_src.exists():
        raise FileNotFoundError(f"Missing stub agent: {agent_src}")
    shutil.copy2(marking_src, workspace_path / MARKING_SCRIPT_REL)
    shutil.copy2(agent_src, workspace_path / AGENT_ENTRY_REL)
    if readme_src.exists():
        shutil.copy2(readme_src, workspace_path / TOOLS_README_REL)
    else:
        (workspace_path / TOOLS_README_REL).write_text(
            "# Visual marking tools\n\n"
            "Call `python tools/write_mark_points.py` from the workspace root.\n",
            encoding="utf-8",
        )

    run_request = {
        "schema_version": RUN_REQUEST_SCHEMA_VERSION,
        "run_id": run_id,
        "workspace_id": workspace_id,
        "html_files": html_files,
        "marking_script": MARKING_SCRIPT_REL,
        "agent_entry": AGENT_ENTRY_REL,
    }
    write_json(workspace_path / INPUT_RUN_REQUEST, run_request)

    html_digests = {
        relative: file_sha256(workspace_path / relative) for relative in html_files
    }
    input_digests = compute_input_digests(
        workspace_path=workspace_path,
        html_files=html_files,
    )
    snapshot = workspace_snapshot(workspace_path)
    payload = visual_marks_manifest_payload(
        repo_root=repo_root,
        workspace_path=workspace_path,
        run_id=run_id,
        workspace_id=workspace_id,
        snapshot=snapshot,
        input_digests=input_digests,
        html_digests=html_digests,
    )
    write_json(workspace_path / "workspace_manifest.json", payload)
    return workspace_path


def visual_marks_manifest_payload(
    *,
    repo_root: Path,
    workspace_path: Path,
    run_id: str,
    workspace_id: str,
    snapshot: dict[str, str],
    input_digests: dict[str, str],
    html_digests: dict[str, str],
) -> dict[str, Any]:
    """Return a JSON-friendly visual-marks workspace manifest."""
    return {
        "schema_version": VISUAL_MARKS_MANIFEST_SCHEMA_VERSION,
        "workspace_kind": VISUAL_MARKS_WORKSPACE_KIND,
        "run_id": run_id,
        "workspace_id": workspace_id,
        "source_repo_root": str(repo_root.resolve()),
        "workspace_path": str(workspace_path.resolve()),
        "include_dirs": ["input", "tools", "agent", "output"],
        "include_files": [
            MARKING_SCRIPT_REL,
            AGENT_ENTRY_REL,
            TOOLS_README_REL,
            INPUT_RUN_REQUEST,
        ],
        "input_digests": input_digests,
        "html_digests": html_digests,
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


def compute_input_digests(
    *,
    workspace_path: Path,
    html_files: list[str],
) -> dict[str, str]:
    """Return sha256 digests for packed input request and HTML pages."""
    digests = {
        "run_request_json": file_sha256(workspace_path / INPUT_RUN_REQUEST),
    }
    for relative in html_files:
        key = relative.replace("/", "__")
        digests[key] = file_sha256(workspace_path / relative)
    return digests


def verify_input_digests(
    *,
    workspace_path: Path,
    expected: dict[str, str],
    html_files: list[str],
) -> tuple[bool, tuple[str, ...]]:
    """Return whether packed inputs still match the manifest digests."""
    current = compute_input_digests(
        workspace_path=workspace_path,
        html_files=html_files,
    )
    errors: list[str] = []
    for key, digest in expected.items():
        if current.get(key) != digest:
            errors.append(f"input digest mismatch: {key}")
    return (not errors, tuple(errors))


def load_workspace_manifest(workspace_path: Path) -> dict[str, Any]:
    """Load the visual-marks workspace manifest."""
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
    """Return mutation errors against the visual-marks allowlist."""
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
