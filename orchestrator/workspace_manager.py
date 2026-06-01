"""Isolated workspace helpers for future agent execution."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


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
    return "__pycache__" in parts or ".pytest_cache" in parts
