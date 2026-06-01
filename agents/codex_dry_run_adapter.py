"""Dry-run Codex adapter.

This adapter preserves the future Codex CLI boundary without invoking Codex. It
returns a fixed non-applicable proposal so the orchestration layer can exercise
the adapter path safely.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.proposal import StrategyProposal


class CodexDryRunModifier:
    """A no-op stand-in for a future isolated Codex CLI process."""

    agent_name = "codex_cli_dry_run"

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
        """Return a fixed no-op proposal without touching files."""
        report_text = report_path.read_text(encoding="utf-8")
        target_relative = target_file.relative_to(repo_root)
        return StrategyProposal(
            agent_name=self.agent_name,
            round_index=round_index,
            target_file=str(target_relative),
            summary="Dry-run Codex adapter did not request a file change.",
            risk_notes="No patch was generated; this adapter is for control-flow tests.",
            expected_metric_change={},
            raw_response=(
                "codex dry-run response: "
                f"read report with {len(report_text)} characters"
            ),
            patch_diff="",
            applicable=False,
            rejection_reason="Codex dry-run adapter does not emit patches.",
        )
