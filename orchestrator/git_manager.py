"""Git helpers for the self-iteration loop."""

from __future__ import annotations

import subprocess
from pathlib import Path


STRATEGY_PATH = Path("strategies/current_strategy.py")


class GitError(RuntimeError):
    """Raised when a required git operation fails."""


def ensure_git_repo(repo_root: Path) -> None:
    """Initialize git and create a baseline commit when needed."""
    repo_root = repo_root.resolve()
    ensure_gitignore(repo_root)
    if not (repo_root / ".git").exists():
        run_git(repo_root, "init")
        run_git(repo_root, "config", "user.name", "SuanAgent V0")
        run_git(repo_root, "config", "user.email", "suanagent-v0@example.local")
        run_git(repo_root, "add", ".")
        commit(repo_root, "baseline: initialize self-iteration workspace")
    else:
        ensure_git_identity(repo_root)


def ensure_gitignore(repo_root: Path) -> None:
    """Create the expected gitignore if it is missing."""
    gitignore = repo_root / ".gitignore"
    if gitignore.exists():
        return
    gitignore.write_text(
        "\n".join(
            [
                "__pycache__/",
                "*.py[cod]",
                ".pytest_cache/",
                "experiments/*",
                "!experiments/.gitkeep",
                "",
            ]
        ),
        encoding="utf-8",
    )


def ensure_git_identity(repo_root: Path) -> None:
    """Set local commit identity only when the repo lacks one."""
    name = run_git(repo_root, "config", "--get", "user.name", check=False)
    email = run_git(repo_root, "config", "--get", "user.email", check=False)
    if not name.stdout.strip():
        run_git(repo_root, "config", "user.name", "SuanAgent V0")
    if not email.stdout.strip():
        run_git(repo_root, "config", "user.email", "suanagent-v0@example.local")


def assert_strategy_clean(repo_root: Path) -> None:
    """Stop before iteration if the candidate strategy has pending changes."""
    result = run_git(
        repo_root,
        "status",
        "--porcelain",
        "--",
        str(STRATEGY_PATH),
        check=True,
    )
    if result.stdout.strip():
        raise GitError(f"{STRATEGY_PATH} has uncommitted changes")


def apply_patch(repo_root: Path, patch_diff: str) -> None:
    """Apply a git patch after checking that it is valid."""
    if not patch_diff.strip():
        raise GitError("empty patch")
    run_git(repo_root, "apply", "--check", input_text=patch_diff)
    run_git(repo_root, "apply", input_text=patch_diff)


def rollback_strategy(repo_root: Path) -> None:
    """Restore the candidate strategy to HEAD."""
    run_git(repo_root, "checkout", "--", str(STRATEGY_PATH))


def commit_strategy(repo_root: Path, *, run_id: str, round_id: str) -> str:
    """Commit the accepted strategy and return the commit hash."""
    run_git(repo_root, "add", str(STRATEGY_PATH))
    status = run_git(repo_root, "status", "--porcelain", "--", str(STRATEGY_PATH))
    if status.stdout.strip():
        commit(repo_root, f"accept strategy update {run_id} {round_id}")
    return current_commit(repo_root)


def current_commit(repo_root: Path) -> str:
    """Return the current HEAD commit hash."""
    result = run_git(repo_root, "rev-parse", "HEAD")
    return result.stdout.strip()


def commit(repo_root: Path, message: str) -> None:
    """Create a git commit."""
    run_git(repo_root, "commit", "-m", message)


def run_git(
    repo_root: Path,
    *args: str,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command in the repository root."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip()
        raise GitError(f"git {' '.join(args)} failed: {details}")
    return result
