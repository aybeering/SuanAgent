"""Controlled Codex CLI adapter.

This adapter is the real execution boundary for future Codex integration. It is
safe by default: unless `execute=True`, it records the prompt and command but
does not invoke any subprocess.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from agents.codex_dry_run_adapter import (
    build_codex_command,
    build_codex_prompt,
    proposal_from_codex_output,
    workspace_ids_from_report,
)
from orchestrator.proposal import StrategyProposal
from orchestrator.workspace_manager import create_isolated_workspace


class CodexCliModifier:
    """A guarded adapter for invoking Codex CLI."""

    agent_name = "codex_cli"

    def __init__(
        self,
        *,
        executable: str = "codex",
        model: str = "default",
        sandbox: str = "workspace-write",
        workspace_root: str = "workspaces",
        execute: bool = False,
        timeout_seconds: int = 120,
    ) -> None:
        self.executable = executable
        self.model = model
        self.sandbox = sandbox
        self.workspace_root = Path(workspace_root)
        self.execute = execute
        self.timeout_seconds = timeout_seconds

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
        """Build the Codex request and optionally execute it."""
        report_text = report_path.read_text(encoding="utf-8")
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
        )
        command = build_codex_command(
            executable=self.executable,
            model=self.model,
            sandbox=self.sandbox,
            target_file=str(target_relative),
        )

        if not self.execute:
            return StrategyProposal(
                agent_name=self.agent_name,
                round_index=round_index,
                target_file=str(target_relative),
                summary="Codex CLI execution is disabled by config.",
                risk_notes="No subprocess was invoked; set execute=true to run Codex.",
                expected_metric_change={},
                raw_response="codex cli execution disabled",
                patch_diff="",
                applicable=False,
                hypotheses=(
                    "A future enabled Codex CLI run should return a strategy-only patch.",
                ),
                rejection_reason="Codex CLI execution disabled.",
                prompt=prompt,
                command=tuple(command),
                workspace_path=str(workspace_path),
            )

        result = run_codex_command(
            command=command,
            prompt=prompt,
            cwd=workspace_path,
            timeout_seconds=self.timeout_seconds,
        )
        raw_output = result.stdout
        if result.stderr:
            raw_output = raw_output + "\n[stderr]\n" + result.stderr
        if result.returncode != 0:
            return StrategyProposal(
                agent_name=self.agent_name,
                round_index=round_index,
                target_file=str(target_relative),
                summary="Codex CLI execution failed.",
                risk_notes="No patch was accepted because the subprocess failed.",
                expected_metric_change={},
                raw_response=raw_output,
                patch_diff="",
                applicable=False,
                hypotheses=(
                    "A successful Codex CLI subprocess is required before patch parsing.",
                ),
                rejection_reason=f"Codex CLI exited with {result.returncode}.",
                prompt=prompt,
                command=tuple(command),
                workspace_path=str(workspace_path),
            )

        return proposal_from_codex_output(
            raw_output=raw_output,
            report_path=report_path,
            target_file=target_file,
            round_index=round_index,
            repo_root=repo_root,
            prompt=prompt,
            command=command,
            workspace_path=workspace_path,
        )


def run_codex_command(
    *,
    command: list[str],
    prompt: str,
    cwd: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    """Run Codex CLI with prompt on stdin."""
    return subprocess.run(
        command,
        input=prompt,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
