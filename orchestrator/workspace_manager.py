"""Isolated workspace helpers for future agent execution."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


WORKSPACE_MANIFEST_SCHEMA_VERSION = "workspace_manifest_v1"

DEFAULT_INCLUDE_DIRS = (
    "agents",
    "backtester",
    "config",
    "data",
    "docs",
    "orchestrator",
    "reports",
    "strategies",
)

DEFAULT_INCLUDE_FILES = (
    ".gitignore",
    "AGENTS.md",
    "README.md",
    "TASK.md",
    "pyproject.toml",
)


def create_isolated_workspace(
    *,
    repo_root: Path,
    workspace_root: Path,
    run_id: str,
    round_id: str,
) -> Path:
    """Copy the minimal project into an isolated round workspace."""
    workspace_path = workspace_root / run_id / round_id / "strategy_workspace"
    if workspace_path.exists():
        raise FileExistsError(f"Workspace already exists: {workspace_path}")
    workspace_path.mkdir(parents=True)

    for directory in DEFAULT_INCLUDE_DIRS:
        source = repo_root / directory
        if source.exists():
            shutil.copytree(
                source,
                workspace_path / directory,
                ignore=shutil.ignore_patterns("__pycache__"),
            )

    for filename in DEFAULT_INCLUDE_FILES:
        source = repo_root / filename
        if source.exists():
            shutil.copy2(source, workspace_path / filename)

    (workspace_path / "experiments").mkdir(exist_ok=True)
    (workspace_path / "experiments" / ".gitkeep").write_text("", encoding="utf-8")
    return workspace_path


def write_workspace_manifest(
    *,
    output_path: Path,
    repo_root: Path,
    workspace_path: Path,
    run_id: str,
    round_id: str,
    agent_name: str,
    execution_enabled: bool,
    allowed_mutation_paths: tuple[str, ...],
) -> Path:
    """Write a deterministic manifest for one isolated agent workspace."""
    snapshot = workspace_snapshot(workspace_path)
    payload = workspace_manifest_payload(
        repo_root=repo_root,
        workspace_path=workspace_path,
        run_id=run_id,
        round_id=round_id,
        agent_name=agent_name,
        execution_enabled=execution_enabled,
        allowed_mutation_paths=allowed_mutation_paths,
        snapshot=snapshot,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def workspace_manifest_payload(
    *,
    repo_root: Path,
    workspace_path: Path,
    run_id: str,
    round_id: str,
    agent_name: str,
    execution_enabled: bool,
    allowed_mutation_paths: tuple[str, ...],
    snapshot: dict[str, str],
) -> dict[str, Any]:
    """Return a JSON-friendly isolated workspace manifest."""
    return {
        "schema_version": WORKSPACE_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "agent_name": agent_name,
        "execution_enabled": execution_enabled,
        "source_repo_root": str(repo_root.resolve()),
        "workspace_path": str(workspace_path.resolve()),
        "include_dirs": list(DEFAULT_INCLUDE_DIRS),
        "include_files": list(DEFAULT_INCLUDE_FILES),
        "initial_snapshot": {
            "file_count": len(snapshot),
            "sha256": workspace_snapshot_digest(snapshot),
        },
        "mutation_policy": {
            "allowed_paths": list(allowed_mutation_paths),
            "reject_unlisted_changes": True,
        },
    }


def workspace_snapshot_digest(snapshot: dict[str, str]) -> str:
    """Return a deterministic digest for a workspace snapshot mapping."""
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def workspace_snapshot(workspace_path: Path) -> dict[str, str]:
    """Return deterministic file hashes for an isolated workspace."""
    snapshot: dict[str, str] = {}
    for path in sorted(workspace_path.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(workspace_path).as_posix()
        if should_ignore_snapshot_path(relative):
            continue
        snapshot[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def workspace_mutation_errors(
    *,
    before: dict[str, str],
    after: dict[str, str],
    allowed_paths: set[str],
) -> tuple[str, ...]:
    """Return disallowed workspace mutations between two snapshots."""
    errors: list[str] = []
    all_paths = sorted(set(before) | set(after))
    for path in all_paths:
        if before.get(path) == after.get(path):
            continue
        if path in allowed_paths:
            continue
        if path not in before:
            errors.append(f"workspace added disallowed file: {path}")
        elif path not in after:
            errors.append(f"workspace deleted disallowed file: {path}")
        else:
            errors.append(f"workspace modified disallowed file: {path}")
    return tuple(errors)


def should_ignore_snapshot_path(relative_path: str) -> bool:
    """Return whether a generated workspace path should be ignored."""
    parts = set(Path(relative_path).parts)
    return (
        "__pycache__" in parts
        or ".pytest_cache" in parts
        or Path(relative_path).name == "workspace_manifest.json"
    )
