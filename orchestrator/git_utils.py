"""Small git helpers for experiment audit artifacts."""

from __future__ import annotations

import subprocess
from pathlib import Path


def strategy_diff(strategy_path: Path = Path("strategies/current_strategy.py")) -> str:
    """Return the git diff for the candidate strategy, or a V0 placeholder."""
    command = ["git", "diff", "--", str(strategy_path)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return "No git diff available; repository is not initialized for git.\n"
    return result.stdout or "No strategy changes detected by git diff.\n"
