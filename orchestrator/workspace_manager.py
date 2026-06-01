"""Isolated workspace helpers for future agent execution."""

from __future__ import annotations

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
