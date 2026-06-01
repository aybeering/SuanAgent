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
    workspace_manifest_output_path,
    workspace_ids_from_report,
)
from orchestrator.agent_contract_runner import (
    AgentCommandResult,
    AgentContractRunResult,
    CODEX_CLI_GUARDED_RUNNER_NAME,
    write_agent_execution,
)
from orchestrator.proposal import StrategyProposal
from orchestrator.workspace_manager import (
    create_isolated_workspace,
    write_workspace_manifest,
    workspace_mutation_errors,
    workspace_snapshot,
)


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
        context_path: Path | None = None,
        attempt_id: str = "",
        profile_name: str = "",
        adapter_name: str = "",
        agent_role: str = "",
    ) -> StrategyProposal:
        """Build the Codex request and optionally execute it."""
        del agent_role
        report_text = report_path.read_text(encoding="utf-8")
        context_text = context_path.read_text(encoding="utf-8") if context_path else ""
        target_relative = target_file.relative_to(repo_root)
        run_id, round_id = workspace_ids_from_report(report_path)
        workspace_path = create_isolated_workspace(
            repo_root=repo_root,
            workspace_root=repo_root / self.workspace_root,
            run_id=run_id,
            round_id=round_id,
            attempt_id=attempt_id,
            profile_name=profile_name,
        )
        write_workspace_manifest(
            output_path=workspace_manifest_output_path(
                round_dir=report_path.parent,
                attempt_id=attempt_id,
            ),
            repo_root=repo_root,
            workspace_path=workspace_path,
            run_id=run_id,
            round_id=round_id,
            agent_name=self.agent_name,
            execution_enabled=self.execute,
            allowed_mutation_paths=(str(target_relative),),
            attempt_id=attempt_id,
            profile_name=profile_name,
            adapter_name=adapter_name,
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
        execution_output_path = codex_execution_output_path(
            round_dir=report_path.parent,
            attempt_id=attempt_id,
        )
        agent_input_path = report_path.parent / "agent_input.json"
        round_output_path = report_path.parent / "codex_stdout.txt"
        workspace_output_path = workspace_path / "codex_stdout.txt"

        if not self.execute:
            write_codex_execution_audit(
                output_path=execution_output_path,
                profile_name=profile_name,
                adapter_name=adapter_name,
                command=command,
                workspace_path=workspace_path,
                agent_input_path=agent_input_path,
                workspace_output_path=workspace_output_path,
                round_output_path=round_output_path,
                timeout_seconds=self.timeout_seconds,
                execution_enabled=False,
                raw_response="codex cli execution disabled",
                stdin_text=prompt,
                allowed_mutation_paths=(str(target_relative),),
            )
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
                direction_tag="codex_cli_disabled",
                hypotheses=(
                    "A future enabled Codex CLI run should return a strategy-only patch.",
                ),
                rejection_reason="Codex CLI execution disabled.",
                prompt=prompt,
                command=tuple(command),
                workspace_path=str(workspace_path),
            )

        workspace_before = workspace_snapshot(workspace_path)
        result = run_codex_command(
            command=command,
            prompt=prompt,
            cwd=workspace_path,
            timeout_seconds=self.timeout_seconds,
        )
        raw_output = result.stdout
        if result.stderr:
            raw_output = raw_output + "\n[stderr]\n" + result.stderr
        if result.timed_out:
            write_codex_execution_audit(
                output_path=execution_output_path,
                profile_name=profile_name,
                adapter_name=adapter_name,
                command=command,
                workspace_path=workspace_path,
                agent_input_path=agent_input_path,
                workspace_output_path=workspace_output_path,
                round_output_path=round_output_path,
                timeout_seconds=self.timeout_seconds,
                execution_enabled=True,
                raw_response=raw_output,
                stdin_text=prompt,
                allowed_mutation_paths=(str(target_relative),),
                result=result,
                status="timeout",
            )
            return StrategyProposal(
                agent_name=self.agent_name,
                round_index=round_index,
                target_file=str(target_relative),
                summary="Codex CLI execution timed out.",
                risk_notes="No patch was accepted because the subprocess timed out.",
                expected_metric_change={},
                raw_response=raw_output,
                patch_diff="",
                applicable=False,
                direction_tag="codex_cli_timeout",
                hypotheses=("Codex CLI subprocesses must finish before timeout.",),
                rejection_reason=(
                    f"Codex CLI timed out after {self.timeout_seconds} seconds."
                ),
                prompt=prompt,
                command=tuple(command),
                workspace_path=str(workspace_path),
            )
        if result.returncode != 0:
            write_codex_execution_audit(
                output_path=execution_output_path,
                profile_name=profile_name,
                adapter_name=adapter_name,
                command=command,
                workspace_path=workspace_path,
                agent_input_path=agent_input_path,
                workspace_output_path=workspace_output_path,
                round_output_path=round_output_path,
                timeout_seconds=self.timeout_seconds,
                execution_enabled=True,
                raw_response=raw_output,
                stdin_text=prompt,
                allowed_mutation_paths=(str(target_relative),),
                result=result,
                status="command_failed",
            )
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
                direction_tag="codex_cli_failed",
                hypotheses=(
                    "A successful Codex CLI subprocess is required before patch parsing.",
                ),
                rejection_reason=f"Codex CLI exited with {result.returncode}.",
                prompt=prompt,
                command=tuple(command),
                workspace_path=str(workspace_path),
            )

        mutation_errors = workspace_mutation_errors(
            before=workspace_before,
            after=workspace_snapshot(workspace_path),
            allowed_paths={str(target_relative)},
        )
        if mutation_errors:
            write_codex_execution_audit(
                output_path=execution_output_path,
                profile_name=profile_name,
                adapter_name=adapter_name,
                command=command,
                workspace_path=workspace_path,
                agent_input_path=agent_input_path,
                workspace_output_path=workspace_output_path,
                round_output_path=round_output_path,
                timeout_seconds=self.timeout_seconds,
                execution_enabled=True,
                raw_response=raw_output,
                stdin_text=prompt,
                allowed_mutation_paths=(str(target_relative),),
                result=result,
                mutation_errors=mutation_errors,
                status="workspace_violation",
            )
            return StrategyProposal(
                agent_name=self.agent_name,
                round_index=round_index,
                target_file=str(target_relative),
                summary="Codex CLI modified disallowed workspace files.",
                risk_notes="Workspace mutation guard rejected the subprocess output.",
                expected_metric_change={},
                raw_response=raw_output,
                patch_diff="",
                applicable=False,
                direction_tag="codex_cli_workspace_violation",
                hypotheses=(
                    "Codex CLI subprocesses must modify only the strategy file.",
                ),
                rejection_reason=(
                    "proposal contract invalid: " + "; ".join(mutation_errors)
                ),
                prompt=prompt,
                command=tuple(command),
                workspace_path=str(workspace_path),
                contract_errors=mutation_errors,
            )

        write_codex_execution_audit(
            output_path=execution_output_path,
            profile_name=profile_name,
            adapter_name=adapter_name,
            command=command,
            workspace_path=workspace_path,
            agent_input_path=agent_input_path,
            workspace_output_path=workspace_output_path,
            round_output_path=round_output_path,
            timeout_seconds=self.timeout_seconds,
            execution_enabled=True,
            raw_response=raw_output,
            stdin_text=prompt,
            allowed_mutation_paths=(str(target_relative),),
            result=result,
            status="completed",
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


def codex_execution_output_path(*, round_dir: Path, attempt_id: str) -> Path:
    """Return where to store Codex execution audit before attempt selection."""
    if not attempt_id:
        return round_dir / "agent_execution.json"
    return round_dir / "agent_executions" / f"{attempt_id}.json"


def write_codex_execution_audit(
    *,
    output_path: Path,
    profile_name: str,
    adapter_name: str,
    command: list[str],
    workspace_path: Path,
    agent_input_path: Path,
    workspace_output_path: Path,
    round_output_path: Path,
    timeout_seconds: int,
    execution_enabled: bool,
    raw_response: str,
    stdin_text: str,
    allowed_mutation_paths: tuple[str, ...],
    result: AgentCommandResult | None = None,
    mutation_errors: tuple[str, ...] = (),
    status: str = "disabled",
) -> None:
    """Write the unified guarded-Codex execution audit."""
    write_agent_execution(
        output_path=output_path,
        agent_name=CodexCliModifier.agent_name,
        profile_name=profile_name,
        adapter_name=adapter_name,
        runner_name=CODEX_CLI_GUARDED_RUNNER_NAME,
        stdin_text=stdin_text,
        contract_result=AgentContractRunResult(
            status=status,
            execution_enabled=execution_enabled,
            command=tuple(command),
            cwd=workspace_path,
            workspace_path=workspace_path,
            agent_input_path=agent_input_path,
            workspace_output_path=workspace_output_path,
            round_output_path=round_output_path,
            timeout_seconds=timeout_seconds,
            raw_response=raw_response,
            mutation_errors=mutation_errors,
            allowed_mutation_paths=allowed_mutation_paths,
            result=result,
        ),
    )


def run_codex_command(
    *,
    command: list[str],
    prompt: str,
    cwd: Path,
    timeout_seconds: int,
) -> AgentCommandResult:
    """Run Codex CLI with prompt on stdin."""
    try:
        result = subprocess.run(
            command,
            input=prompt,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = text_or_empty(exc.stderr)
        timeout_message = f"codex cli timed out after {timeout_seconds} seconds"
        return AgentCommandResult(
            returncode=None,
            stdout=text_or_empty(exc.stdout),
            stderr="\n".join(part for part in (stderr, timeout_message) if part),
            timed_out=True,
        )
    return AgentCommandResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def text_or_empty(value: str | bytes | None) -> str:
    """Return subprocess output as text."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
