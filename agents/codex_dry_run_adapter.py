"""Dry-run Codex CLI adapter.

This adapter preserves the future isolated Codex CLI boundary without invoking
Codex. It builds the prompt and command that a real adapter would use, then
returns a non-applicable proposal so the deterministic loop can exercise the
control flow safely.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.proposal import StrategyProposal


class CodexDryRunModifier:
    """A dry-run stand-in for a future isolated Codex CLI process."""

    agent_name = "codex_cli_dry_run"

    def __init__(
        self,
        *,
        executable: str = "codex",
        model: str = "default",
        sandbox: str = "workspace-write",
    ) -> None:
        self.executable = executable
        self.model = model
        self.sandbox = sandbox

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
        """Return a no-op proposal with the would-be Codex prompt and command."""
        report_text = report_path.read_text(encoding="utf-8")
        target_relative = target_file.relative_to(repo_root)
        prompt = build_codex_prompt(
            report_text=report_text,
            target_file=str(target_relative),
            round_index=round_index,
        )
        command = build_codex_command(
            executable=self.executable,
            model=self.model,
            sandbox=self.sandbox,
            target_file=str(target_relative),
        )
        return StrategyProposal(
            agent_name=self.agent_name,
            round_index=round_index,
            target_file=str(target_relative),
            summary="Dry-run Codex CLI adapter built a command but did not run it.",
            risk_notes="No patch was generated; this adapter is for CLI boundary tests.",
            expected_metric_change={},
            raw_response=(
                "codex cli dry-run response: "
                f"built command for report with {len(report_text)} characters"
            ),
            patch_diff="",
            applicable=False,
            rejection_reason="Codex CLI dry-run adapter does not emit patches.",
            prompt=prompt,
            command=tuple(command),
        )


def build_codex_prompt(
    *,
    report_text: str,
    target_file: str,
    round_index: int,
) -> str:
    """Build the prompt that would be sent to an isolated Codex CLI process."""
    return "\n".join(
        [
            "You are modifying a strategy for SuanAgent V0.5.",
            f"Round: {round_index}",
            f"Only modify: {target_file}",
            "Do not modify data, backtester, reports, orchestrator, or tests.",
            "Return a unified diff patch only.",
            "",
            "Report:",
            report_text,
        ]
    )


def build_codex_command(
    *,
    executable: str,
    model: str,
    sandbox: str,
    target_file: str,
) -> list[str]:
    """Build the future Codex CLI command without executing it."""
    return [
        executable,
        "exec",
        "--model",
        model,
        "--sandbox",
        sandbox,
        "--",
        f"Modify only {target_file} and return a patch.",
    ]
