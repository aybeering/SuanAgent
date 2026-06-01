"""Guarded external agent adapter using agent I/O JSON fixtures."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agents.codex_dry_run_adapter import (
    extract_proposal_metadata,
    metadata_expected_metric_change,
    metadata_hypotheses,
    metadata_patch_diff,
    workspace_ids_from_report,
)
from orchestrator.patch_parser import (
    PatchParseError,
    extract_unified_diff,
    validate_patch_targets,
)
from orchestrator.proposal import StrategyProposal
from orchestrator.workspace_manager import (
    create_isolated_workspace,
    workspace_mutation_errors,
    workspace_snapshot,
)


AGENT_EXECUTION_SCHEMA_VERSION = "agent_execution_v1"
AUDIT_PREVIEW_CHARS = 500


@dataclass(frozen=True)
class FileProtocolCommandResult:
    """Captured result from a file-protocol subprocess."""

    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False


class FileProtocolModifier:
    """Run an external command that consumes agent_input.json and emits proposal JSON."""

    agent_name = "file_protocol_agent"

    def __init__(
        self,
        *,
        executable: str,
        args: tuple[str, ...] = (),
        execute: bool = False,
        timeout_seconds: int = 120,
        output_filename: str = "agent_command_output.json",
        workspace_root: str = "workspaces",
    ) -> None:
        self.executable = executable
        self.args = args
        self.execute = execute
        self.timeout_seconds = timeout_seconds
        self.output_filename = output_filename
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
        """Invoke the configured file-protocol command when enabled."""
        del old_threshold, new_threshold, context_path
        target_relative = target_file.relative_to(repo_root)
        round_dir = report_path.parent
        run_id, round_id = workspace_ids_from_report(report_path)
        workspace_path = create_isolated_workspace(
            repo_root=repo_root,
            workspace_root=repo_root / self.workspace_root,
            run_id=f"{run_id}-file-protocol",
            round_id=round_id,
        )
        workspace_round_dir = workspace_path / "experiments" / run_id / round_id
        copy_agent_round_inputs(
            source_round_dir=round_dir,
            workspace_round_dir=workspace_round_dir,
        )
        agent_input_path = workspace_round_dir / "agent_input.json"
        output_path = workspace_round_dir / self.output_filename
        command = [
            self.executable,
            *self.args,
            str(agent_input_path),
            str(output_path),
        ]

        if not self.execute:
            write_agent_execution(
                output_path=round_dir / "agent_execution.json",
                status="disabled",
                execution_enabled=False,
                command=command,
                cwd=workspace_path,
                workspace_path=workspace_path,
                agent_input_path=agent_input_path,
                workspace_output_path=output_path,
                round_output_path=round_dir / self.output_filename,
                timeout_seconds=self.timeout_seconds,
                result=None,
                raw_response="file protocol execution disabled",
                mutation_errors=(),
                allowed_mutation_paths=(output_path.relative_to(workspace_path).as_posix(),),
            )
            return StrategyProposal(
                agent_name=self.agent_name,
                round_index=round_index,
                target_file=str(target_relative),
                summary="File-protocol agent execution is disabled by config.",
                risk_notes="No subprocess was invoked; set execute=true to run it.",
                expected_metric_change={},
                raw_response="file protocol execution disabled",
                patch_diff="",
                applicable=False,
                direction_tag="file_protocol_disabled",
                hypotheses=(
                    "A future enabled file-protocol agent should return proposal JSON.",
                ),
                rejection_reason="File-protocol execution disabled.",
                prompt=str(agent_input_path),
                command=tuple(command),
                workspace_path=str(workspace_path),
            )

        before = workspace_snapshot(workspace_path)
        result = run_file_protocol_command(
            command=command,
            cwd=workspace_path,
            timeout_seconds=self.timeout_seconds,
        )
        raw_response = response_text(result=result, output_path=output_path)
        copy_agent_output_back(
            workspace_output_path=output_path,
            round_output_path=round_dir / self.output_filename,
        )
        after = workspace_snapshot(workspace_path)
        mutation_errors = workspace_mutation_errors(
            before=before,
            after=after,
            allowed_paths={output_path.relative_to(workspace_path).as_posix()},
        )
        if result.timed_out:
            write_agent_execution(
                output_path=round_dir / "agent_execution.json",
                status="timeout",
                execution_enabled=True,
                command=command,
                cwd=workspace_path,
                workspace_path=workspace_path,
                agent_input_path=agent_input_path,
                workspace_output_path=output_path,
                round_output_path=round_dir / self.output_filename,
                timeout_seconds=self.timeout_seconds,
                result=result,
                raw_response=raw_response,
                mutation_errors=mutation_errors,
                allowed_mutation_paths=(
                    output_path.relative_to(workspace_path).as_posix(),
                ),
            )
            return StrategyProposal(
                agent_name=self.agent_name,
                round_index=round_index,
                target_file=str(target_relative),
                summary="File-protocol agent execution timed out.",
                risk_notes="No patch was accepted because the subprocess timed out.",
                expected_metric_change={},
                raw_response=raw_response,
                patch_diff="",
                applicable=False,
                direction_tag="file_protocol_timeout",
                hypotheses=("External agent commands must finish before timeout.",),
                rejection_reason=(
                    f"File-protocol agent timed out after {self.timeout_seconds} seconds."
                ),
                prompt=str(agent_input_path),
                command=tuple(command),
                workspace_path=str(workspace_path),
            )
        if result.returncode != 0:
            write_agent_execution(
                output_path=round_dir / "agent_execution.json",
                status="command_failed",
                execution_enabled=True,
                command=command,
                cwd=workspace_path,
                workspace_path=workspace_path,
                agent_input_path=agent_input_path,
                workspace_output_path=output_path,
                round_output_path=round_dir / self.output_filename,
                timeout_seconds=self.timeout_seconds,
                result=result,
                raw_response=raw_response,
                mutation_errors=mutation_errors,
                allowed_mutation_paths=(
                    output_path.relative_to(workspace_path).as_posix(),
                ),
            )
            return StrategyProposal(
                agent_name=self.agent_name,
                round_index=round_index,
                target_file=str(target_relative),
                summary="File-protocol agent execution failed.",
                risk_notes="No patch was accepted because the subprocess failed.",
                expected_metric_change={},
                raw_response=raw_response,
                patch_diff="",
                applicable=False,
                direction_tag="file_protocol_failed",
                hypotheses=("The external agent command must exit successfully.",),
                rejection_reason=f"File-protocol agent exited with {result.returncode}.",
                prompt=str(agent_input_path),
                command=tuple(command),
                workspace_path=str(workspace_path),
            )

        if mutation_errors:
            write_agent_execution(
                output_path=round_dir / "agent_execution.json",
                status="workspace_violation",
                execution_enabled=True,
                command=command,
                cwd=workspace_path,
                workspace_path=workspace_path,
                agent_input_path=agent_input_path,
                workspace_output_path=output_path,
                round_output_path=round_dir / self.output_filename,
                timeout_seconds=self.timeout_seconds,
                result=result,
                raw_response=raw_response,
                mutation_errors=mutation_errors,
                allowed_mutation_paths=(
                    output_path.relative_to(workspace_path).as_posix(),
                ),
            )
            return StrategyProposal(
                agent_name=self.agent_name,
                round_index=round_index,
                target_file=str(target_relative),
                summary="File-protocol agent mutated protected source files.",
                risk_notes="Source mutation guard rejected the subprocess output.",
                expected_metric_change={},
                raw_response=raw_response,
                patch_diff="",
                applicable=False,
                direction_tag="file_protocol_source_violation",
                hypotheses=(
                    "External file-protocol agents must only emit proposal JSON.",
                ),
                rejection_reason=(
                    "proposal contract invalid: " + "; ".join(mutation_errors)
                ),
                prompt=str(agent_input_path),
                command=tuple(command),
                workspace_path=str(workspace_path),
                contract_errors=mutation_errors,
            )

        write_agent_execution(
            output_path=round_dir / "agent_execution.json",
            status="completed",
            execution_enabled=True,
            command=command,
            cwd=workspace_path,
            workspace_path=workspace_path,
            agent_input_path=agent_input_path,
            workspace_output_path=output_path,
            round_output_path=round_dir / self.output_filename,
            timeout_seconds=self.timeout_seconds,
            result=result,
            raw_response=raw_response,
            mutation_errors=(),
            allowed_mutation_paths=(output_path.relative_to(workspace_path).as_posix(),),
        )
        return proposal_from_file_protocol_output(
            raw_output=raw_response,
            target_file=target_file,
            round_index=round_index,
            repo_root=repo_root,
            command=command,
            agent_input_path=agent_input_path,
            workspace_path=workspace_path,
        )


def run_file_protocol_command(
    *,
    command: list[str],
    cwd: Path,
    timeout_seconds: int,
) -> FileProtocolCommandResult:
    """Run an external file-protocol agent command."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = text_or_empty(exc.stderr)
        timeout_message = f"file protocol command timed out after {timeout_seconds} seconds"
        return FileProtocolCommandResult(
            returncode=None,
            stdout=text_or_empty(exc.stdout),
            stderr="\n".join(part for part in (stderr, timeout_message) if part),
            timed_out=True,
        )
    return FileProtocolCommandResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def proposal_from_file_protocol_output(
    *,
    raw_output: str,
    target_file: Path,
    round_index: int,
    repo_root: Path,
    command: list[str],
    agent_input_path: Path,
    workspace_path: Path,
) -> StrategyProposal:
    """Convert file-protocol output text into a StrategyProposal."""
    target_relative = target_file.relative_to(repo_root)
    metadata = extract_proposal_metadata(raw_output)
    try:
        patch_diff = metadata_patch_diff(metadata) or extract_unified_diff(raw_output)
        validate_patch_targets(patch_diff, target_relative)
    except PatchParseError as exc:
        return StrategyProposal(
            agent_name="file_protocol_agent",
            round_index=round_index,
            target_file=str(target_relative),
            summary=str(
                metadata.get(
                    "summary",
                    "File-protocol output did not contain an applicable patch.",
                )
            ),
            risk_notes=str(
                metadata.get(
                    "risk_notes",
                    "Patch parser rejected the external agent output.",
                )
            ),
            expected_metric_change=metadata_expected_metric_change(metadata),
            raw_response=raw_output,
            patch_diff="",
            applicable=False,
            direction_tag=str(metadata.get("direction_tag", "file_protocol_unknown")),
            hypotheses=metadata_hypotheses(
                metadata,
                ("The external agent output must include a strategy-file patch.",),
            ),
            rejection_reason=str(exc),
            prompt=str(agent_input_path),
            command=tuple(command),
            workspace_path=str(workspace_path),
        )

    return StrategyProposal(
        agent_name="file_protocol_agent",
        round_index=round_index,
        target_file=str(target_relative),
        summary=str(
            metadata.get("summary", "File-protocol agent produced a strategy patch.")
        ),
        risk_notes=str(
            metadata.get("risk_notes", "Patch targets were validated before git apply.")
        ),
        expected_metric_change=metadata_expected_metric_change(metadata),
        raw_response=raw_output,
        patch_diff=patch_diff,
        applicable=True,
        direction_tag=str(metadata.get("direction_tag", "file_protocol_unknown")),
        hypotheses=metadata_hypotheses(
            metadata,
            ("The parsed patch is intended to improve validation metrics.",),
        ),
        rejection_reason="",
        prompt=str(agent_input_path),
        command=tuple(command),
        workspace_path=str(workspace_path),
    )


def copy_agent_round_inputs(*, source_round_dir: Path, workspace_round_dir: Path) -> None:
    """Copy stable agent input artifacts into the isolated workspace."""
    workspace_round_dir.mkdir(parents=True, exist_ok=True)
    for filename in (
        "agent_input.json",
        "agent_context.md",
        "agent_context.json",
        "proposal_intent.json",
        "proposal_intent.md",
        "train_report_before.md",
        "report_before.md",
        "holdout_report_before.md",
    ):
        source = source_round_dir / filename
        if source.exists():
            shutil.copy2(source, workspace_round_dir / filename)


def copy_agent_output_back(
    *,
    workspace_output_path: Path,
    round_output_path: Path,
) -> None:
    """Copy external agent output from workspace to the real round artifacts."""
    if workspace_output_path.exists():
        shutil.copy2(workspace_output_path, round_output_path)


def write_agent_execution(
    *,
    output_path: Path,
    status: str,
    execution_enabled: bool,
    command: list[str],
    cwd: Path,
    workspace_path: Path,
    agent_input_path: Path,
    workspace_output_path: Path,
    round_output_path: Path,
    timeout_seconds: int,
    result: FileProtocolCommandResult | None,
    raw_response: str,
    mutation_errors: tuple[str, ...],
    allowed_mutation_paths: tuple[str, ...],
) -> None:
    """Write a deterministic audit record for one external agent execution."""
    payload = {
        "schema_version": AGENT_EXECUTION_SCHEMA_VERSION,
        "agent_name": FileProtocolModifier.agent_name,
        "status": status,
        "execution_enabled": execution_enabled,
        "command": command,
        "cwd": str(cwd),
        "workspace_path": str(workspace_path),
        "agent_input_path": str(agent_input_path),
        "workspace_output_path": str(workspace_output_path),
        "round_output_path": str(round_output_path),
        "timeout_seconds": timeout_seconds,
        "returncode": result.returncode if result is not None else None,
        "stdout": stream_summary(result.stdout if result is not None else ""),
        "stderr": stream_summary(result.stderr if result is not None else ""),
        "raw_response": stream_summary(raw_response),
        "output_file": file_summary(workspace_output_path),
        "round_output_file": file_summary(round_output_path),
        "allowed_mutation_paths": list(allowed_mutation_paths),
        "mutation_errors": list(mutation_errors),
        "mutation_guard": {
            "allowed_paths": list(allowed_mutation_paths),
            "mutation_errors": list(mutation_errors),
            "passed": not mutation_errors,
        },
    }
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def stream_summary(text: str) -> dict[str, object]:
    """Return a compact deterministic summary for command output text."""
    return {
        "chars": len(text),
        "sha256": sha256_text(text) if text else "",
        "preview": text[:AUDIT_PREVIEW_CHARS],
    }


def file_summary(path: Path) -> dict[str, object]:
    """Return deterministic metadata for an optional file."""
    if not path.exists():
        return {
            "exists": False,
            "path": str(path),
            "bytes": 0,
            "sha256": "",
        }
    return {
        "exists": True,
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def sha256_text(text: str) -> str:
    """Return a text SHA-256 digest."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def response_text(
    *,
    result: FileProtocolCommandResult,
    output_path: Path,
) -> str:
    """Return stdout plus optional file output and stderr."""
    chunks: list[str] = []
    if output_path.exists():
        output_text = output_path.read_text(encoding="utf-8")
        if output_text.strip():
            chunks.append(output_text)
    if result.stdout.strip():
        chunks.append(result.stdout)
    if result.stderr.strip():
        chunks.append("[stderr]\n" + result.stderr)
    return "\n".join(chunks) or "file protocol command produced no output"


def text_or_empty(value: str | bytes | None) -> str:
    """Return timeout output as text."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
