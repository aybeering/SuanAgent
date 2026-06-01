"""Deterministic conservative strategy modifier stub."""

from __future__ import annotations

import difflib
from pathlib import Path

from orchestrator.proposal import StrategyProposal


AGENT_NAME = "strategy_modifier_conservative_stub"
OLD_THRESHOLD = "MIN_EDGE = 0.05"
NEW_THRESHOLD = "MIN_EDGE = 0.06"


class ConservativePatchModifier:
    """Adapter class for a deterministic conservative threshold proposal."""

    agent_name = AGENT_NAME

    def propose_strategy_change(
        self,
        *,
        report_path: Path,
        target_file: Path,
        round_index: int,
        repo_root: Path = Path("."),
        old_threshold: str = OLD_THRESHOLD,
        new_threshold: str = NEW_THRESHOLD,
        context_path: Path | None = None,
    ) -> StrategyProposal:
        """Return the conservative threshold-change proposal."""
        return propose_strategy_change(
            report_path=report_path,
            target_file=target_file,
            round_index=round_index,
            repo_root=repo_root,
            old_threshold=OLD_THRESHOLD,
            new_threshold=NEW_THRESHOLD,
            context_path=context_path,
        )


def propose_strategy_change(
    *,
    report_path: Path,
    target_file: Path,
    round_index: int,
    repo_root: Path = Path("."),
    old_threshold: str = OLD_THRESHOLD,
    new_threshold: str = NEW_THRESHOLD,
    context_path: Path | None = None,
) -> StrategyProposal:
    """Return a fixed proposal that raises the candidate strategy threshold."""
    report_text = report_path.read_text(encoding="utf-8")
    context_text = context_path.read_text(encoding="utf-8") if context_path else ""
    target_text = target_file.read_text(encoding="utf-8")
    target_relative = target_file.relative_to(repo_root)

    if old_threshold not in target_text:
        return StrategyProposal(
            agent_name=AGENT_NAME,
            round_index=round_index,
            target_file=str(target_relative),
            summary="No patch generated because the expected threshold was absent.",
            risk_notes="No file change was proposed.",
            expected_metric_change={},
            raw_response=response_text(report_text, context_text),
            patch_diff="",
            applicable=False,
            hypotheses=(
                "The current strategy file must contain the configured threshold.",
            ),
            rejection_reason=f"Expected `{old_threshold}` in {target_relative}.",
        )

    updated_text = target_text.replace(old_threshold, new_threshold, 1)
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
        summary=f"Replace `{old_threshold}` with `{new_threshold}`.",
        risk_notes="May reduce trade count while increasing average required edge.",
        expected_metric_change={
            "trade_count": "decrease",
            "ev": "uncertain",
            "avg_slippage": "decrease",
        },
        raw_response=response_text(report_text, context_text),
        patch_diff=patch_diff,
        applicable=True,
        hypotheses=(
            "Raising MIN_EDGE should filter out weaker candidate trades.",
            "This explores a conservative direction after lower-threshold patches fail.",
        ),
        rejection_reason="",
    )


def response_text(report_text: str, context_text: str) -> str:
    """Return deterministic stub response metadata."""
    return (
        "conservative stub response: "
        f"read report with {len(report_text)} characters and "
        f"context with {len(context_text)} characters"
    )
