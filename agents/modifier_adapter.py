"""Strategy modifier adapter interface."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from orchestrator.proposal import StrategyProposal


class StrategyModifier(Protocol):
    """Common interface for stub, dry-run, and future Codex adapters."""

    def propose_strategy_change(
        self,
        *,
        report_path: Path,
        target_file: Path,
        round_index: int,
        repo_root: Path,
        old_threshold: str,
        new_threshold: str,
    ) -> StrategyProposal:
        """Return a proposed strategy patch."""
