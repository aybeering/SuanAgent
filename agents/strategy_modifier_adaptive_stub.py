"""Deterministic adaptive strategy modifier stub.

This stub is a testable bridge toward history-aware agents. It still uses fixed
patches, but it reads `agent_context.md` and switches to a different patch after
seeing prior failed patches in the same run.
"""

from __future__ import annotations

import difflib
from pathlib import Path

from orchestrator.proposal import StrategyProposal


AGENT_NAME = "strategy_modifier_adaptive_stub"
MIN_EDGE_OLD = "MIN_EDGE = 0.05"
MIN_EDGE_NEW = "MIN_EDGE = 0.04"
STAKE_OLD = "STAKE = 10.0"
STAKE_NEW = "STAKE = 8.0"


class AdaptivePatchModifier:
    """Deterministic modifier that changes patch direction after failures."""

    agent_name = AGENT_NAME

    def propose_strategy_change(
        self,
        *,
        report_path: Path,
        target_file: Path,
        round_index: int,
        repo_root: Path = Path("."),
        old_threshold: str = MIN_EDGE_OLD,
        new_threshold: str = MIN_EDGE_NEW,
        context_path: Path | None = None,
    ) -> StrategyProposal:
        """Return a history-aware fixed proposal."""
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
    old_threshold: str = MIN_EDGE_OLD,
    new_threshold: str = MIN_EDGE_NEW,
    context_path: Path | None = None,
) -> StrategyProposal:
    """Return a fixed patch that changes direction after prior failures."""
    report_text = report_path.read_text(encoding="utf-8")
    context_text = context_path.read_text(encoding="utf-8") if context_path else ""
    target_text = target_file.read_text(encoding="utf-8")
    target_relative = target_file.relative_to(repo_root)

    if has_prior_failed_patch(context_text):
        return build_replacement_proposal(
            target_text=target_text,
            target_relative=target_relative,
            report_text=report_text,
            context_text=context_text,
            round_index=round_index,
            old_text=STAKE_OLD,
            new_text=STAKE_NEW,
            summary=f"Replace `{STAKE_OLD}` with `{STAKE_NEW}` after prior failure.",
            risk_notes="May increase fill affordability while changing position sizing.",
            expected_metric_change={
                "trade_count": "same_or_increase",
                "total_pnl": "uncertain",
                "max_drawdown": "decrease",
            },
            hypotheses=(
                "Prior failed patch hashes indicate lowering MIN_EDGE was not enough.",
                "Changing stake size tests a different strategy dimension from signal threshold.",
            ),
        )

    return build_replacement_proposal(
        target_text=target_text,
        target_relative=target_relative,
        report_text=report_text,
        context_text=context_text,
        round_index=round_index,
        old_text=old_threshold,
        new_text=new_threshold,
        summary=f"Replace `{old_threshold}` with `{new_threshold}`.",
        risk_notes="May increase trade count while lowering average edge per trade.",
        expected_metric_change={
            "trade_count": "increase",
            "ev": "uncertain",
            "avg_slippage": "slight_increase",
        },
        hypotheses=(
            "First try lowers MIN_EDGE to explore more candidate trades.",
            "The policy gate will reject the change if validation EV does not improve.",
        ),
    )


def build_replacement_proposal(
    *,
    target_text: str,
    target_relative: Path,
    report_text: str,
    context_text: str,
    round_index: int,
    old_text: str,
    new_text: str,
    summary: str,
    risk_notes: str,
    expected_metric_change: dict[str, str],
    hypotheses: tuple[str, ...],
) -> StrategyProposal:
    """Build a proposal replacing one exact text snippet."""
    if old_text not in target_text:
        return StrategyProposal(
            agent_name=AGENT_NAME,
            round_index=round_index,
            target_file=str(target_relative),
            summary=f"No patch generated because `{old_text}` was absent.",
            risk_notes="No file change was proposed.",
            expected_metric_change={},
            raw_response=response_text(report_text, context_text),
            patch_diff="",
            applicable=False,
            hypotheses=hypotheses,
            rejection_reason=f"Expected `{old_text}` in {target_relative}.",
        )

    updated_text = target_text.replace(old_text, new_text, 1)
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
        summary=summary,
        risk_notes=risk_notes,
        expected_metric_change=expected_metric_change,
        raw_response=response_text(report_text, context_text),
        patch_diff=patch_diff,
        applicable=True,
        hypotheses=hypotheses,
        rejection_reason="",
    )


def has_prior_failed_patch(context_text: str) -> bool:
    """Return whether context includes at least one failed patch hash."""
    return "## Failed Patch Hashes" in context_text and "- `" in context_text


def response_text(report_text: str, context_text: str) -> str:
    """Return deterministic stub response metadata."""
    return (
        "adaptive stub response: "
        f"read report with {len(report_text)} characters and "
        f"context with {len(context_text)} characters"
    )
