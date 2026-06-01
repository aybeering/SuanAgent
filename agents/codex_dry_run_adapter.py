"""Dry-run Codex CLI adapter.

This adapter preserves the future isolated Codex CLI boundary without invoking
Codex. It builds the prompt and command that a real adapter would use, then
returns a non-applicable proposal so the deterministic loop can exercise the
control flow safely.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.patch_parser import (
    PatchParseError,
    extract_unified_diff,
    validate_patch_targets,
)
from orchestrator.proposal import StrategyProposal
from orchestrator.workspace_manager import create_isolated_workspace


class CodexDryRunModifier:
    """A dry-run stand-in for a future isolated Codex CLI process."""

    agent_name = "codex_cli_dry_run"

    def __init__(
        self,
        *,
        executable: str = "codex",
        model: str = "default",
        sandbox: str = "workspace-write",
        workspace_root: str = "workspaces",
    ) -> None:
        self.executable = executable
        self.model = model
        self.sandbox = sandbox
        self.workspace_root = Path(workspace_root)

    def propose_strategy_change(
        self,
        *,
        report_path: Path,
        target_file: Path,
        round_index: int,
        repo_root: Path,
        old_threshold: str,
        new_threshold: str,
        context_path: Path | None = None,
    ) -> StrategyProposal:
        """Return a no-op proposal with the would-be Codex prompt and command."""
        report_text = report_path.read_text(encoding="utf-8")
        context_text = context_path.read_text(encoding="utf-8") if context_path else ""
        target_relative = target_file.relative_to(repo_root)
        run_id, round_id = workspace_ids_from_report(report_path)
        workspace_path = create_isolated_workspace(
            repo_root=repo_root,
            workspace_root=repo_root / self.workspace_root,
            run_id=run_id,
            round_id=round_id,
        )
        prompt = build_codex_prompt(
            report_text=report_text,
            target_file=str(target_relative),
            round_index=round_index,
            context_text=context_text,
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
            hypotheses=(
                "A future Codex CLI call should inspect the train report before editing.",
            ),
            rejection_reason="Codex CLI dry-run adapter does not emit patches.",
            prompt=prompt,
            command=tuple(command),
            workspace_path=str(workspace_path),
        )


def build_codex_prompt(
    *,
    report_text: str,
    target_file: str,
    round_index: int,
    context_text: str = "",
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
            "Prior proposal context:",
            context_text or "No prior proposal context was provided.",
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


def proposal_from_codex_output(
    *,
    raw_output: str,
    report_path: Path,
    target_file: Path,
    round_index: int,
    repo_root: Path,
    prompt: str,
    command: list[str],
    workspace_path: Path,
) -> StrategyProposal:
    """Convert future Codex CLI output into a StrategyProposal."""
    target_relative = target_file.relative_to(repo_root)
    try:
        patch_diff = extract_unified_diff(raw_output)
        validate_patch_targets(patch_diff, target_relative)
    except PatchParseError as exc:
        return StrategyProposal(
            agent_name="codex_cli",
            round_index=round_index,
            target_file=str(target_relative),
            summary="Codex output did not contain an applicable strategy patch.",
            risk_notes="Patch parser rejected the output before git apply.",
            expected_metric_change={},
            raw_response=raw_output,
            patch_diff="",
            applicable=False,
            hypotheses=(
                "The Codex response must contain a unified diff for the strategy file.",
            ),
            rejection_reason=str(exc),
            prompt=prompt,
            command=tuple(command),
            workspace_path=str(workspace_path),
        )

    return StrategyProposal(
        agent_name="codex_cli",
        round_index=round_index,
        target_file=str(target_relative),
        summary="Codex output produced a strategy patch.",
        risk_notes="Patch targets were validated before git apply.",
        expected_metric_change={},
        raw_response=raw_output,
        patch_diff=patch_diff,
        applicable=True,
        hypotheses=(
            "The parsed patch is intended to improve validation metrics after simulation.",
        ),
        rejection_reason="",
        prompt=prompt,
        command=tuple(command),
        workspace_path=str(workspace_path),
    )


def workspace_ids_from_report(report_path: Path) -> tuple[str, str]:
    """Derive stable workspace ids from an experiment report path."""
    round_id = report_path.parent.name or "round_unknown"
    run_id = report_path.parent.parent.name or "run_unknown"
    return run_id, round_id
