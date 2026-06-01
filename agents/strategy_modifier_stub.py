"""Deterministic strategy modifier stub.

This module is a placeholder for a future isolated Codex CLI process. For now
it reads the report path, returns a fixed patch, and never makes acceptance
decisions.
"""

from __future__ import annotations

import difflib
from pathlib import Path

from orchestrator.proposal import StrategyProposal


AGENT_NAME = "strategy_modifier_stub"
OLD_THRESHOLD = "MIN_EDGE = 0.05"
NEW_THRESHOLD = "MIN_EDGE = 0.04"


def propose_strategy_change(
    *,
    report_path: Path,
    target_file: Path,
    round_index: int,
    repo_root: Path = Path("."),
) -> StrategyProposal:
    """Return a fixed proposal that lowers the candidate strategy threshold."""
    report_text = report_path.read_text(encoding="utf-8")
    target_text = target_file.read_text(encoding="utf-8")
    target_relative = target_file.relative_to(repo_root)

    if OLD_THRESHOLD not in target_text:
        return StrategyProposal(
            agent_name=AGENT_NAME,
            round_index=round_index,
            target_file=str(target_relative),
            summary="No patch generated because the expected threshold was absent.",
            raw_response=f"Read report with {len(report_text)} characters.",
            patch_diff="",
            applicable=False,
            rejection_reason=f"Expected `{OLD_THRESHOLD}` in {target_relative}.",
        )

    updated_text = target_text.replace(OLD_THRESHOLD, NEW_THRESHOLD, 1)
    patch_diff = "".join(
        difflib.unified_diff(
            target_text.splitlines(keepends=True),
            updated_text.splitlines(keepends=True),
            fromfile=f"a/{target_relative}",
            tofile=f"b/{target_relative}",
        )
    )

    return StrategyProposal(
        agent_name=AGENT_NAME,
        round_index=round_index,
        target_file=str(target_relative),
        summary="Lower MIN_EDGE from 0.05 to 0.04 for the candidate strategy.",
        raw_response=f"stub response: read report with {len(report_text)} characters",
        patch_diff=patch_diff,
        applicable=True,
        rejection_reason="",
    )
