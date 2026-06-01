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


class FixedPatchModifier:
    """Adapter class for the deterministic fixed-patch modifier."""

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
        attempt_id: str = "",
        profile_name: str = "",
        adapter_name: str = "",
        agent_role: str = "",
    ) -> StrategyProposal:
        """Return the fixed threshold-change proposal."""
        del attempt_id, profile_name, adapter_name, agent_role
        return propose_strategy_change(
            report_path=report_path,
            target_file=target_file,
            round_index=round_index,
            repo_root=repo_root,
            old_threshold=old_threshold,
            new_threshold=new_threshold,
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
    """Return a fixed proposal that lowers the candidate strategy threshold."""
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
            raw_response=(
                f"Read report with {len(report_text)} characters and "
                f"context with {len(context_text)} characters."
            ),
            patch_diff="",
            applicable=False,
            direction_tag="lower_min_edge",
            hypotheses=(
                "The current strategy file must contain the configured old threshold.",
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
        risk_notes="May increase trade count while lowering average edge per trade.",
        expected_metric_change={
            "trade_count": "increase",
            "ev": "uncertain",
            "avg_slippage": "slight_increase",
        },
        raw_response=(
            f"stub response: read report with {len(report_text)} characters and "
            f"context with {len(context_text)} characters"
        ),
        patch_diff=patch_diff,
        applicable=True,
        direction_tag="lower_min_edge",
        hypotheses=(
            "Lowering MIN_EDGE should allow more candidate trades to pass the filter.",
            "The extra trades may improve total opportunity capture if edge estimates are reliable.",
        ),
        rejection_reason="",
    )
