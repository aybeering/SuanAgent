"""Guarded external agent adapter using agent I/O JSON fixtures."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from agents.codex_dry_run_adapter import (
    extract_proposal_metadata,
    metadata_expected_metric_change,
    metadata_hypotheses,
    metadata_patch_diff,
)
from orchestrator.patch_parser import PatchParseError, extract_unified_diff, validate_patch_targets
from orchestrator.proposal import StrategyProposal


PROTECTED_PATHS = (
    "AGENTS.md",
    "README.md",
    "TASK.md",
    "pyproject.toml",
    ".gitignore",
    "agents",
    "backtester",
    "config",
    "docs",
    "orchestrator",
    "reports",
    "strategies",
    "tests",
)


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
    ) -> None:
        self.executable = executable
        self.args = args
        self.execute = execute
        self.timeout_seconds = timeout_seconds
        self.output_filename = output_filename

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
        agent_input_path = round_dir / "agent_input.json"
        output_path = round_dir / self.output_filename
        command = [
            self.executable,
            *self.args,
            str(agent_input_path),
            str(output_path),
        ]

        if not self.execute:
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
                workspace_path=str(repo_root),
            )

        before = protected_source_snapshot(repo_root)
        result = run_file_protocol_command(
            command=command,
            cwd=round_dir,
            timeout_seconds=self.timeout_seconds,
        )
        raw_response = response_text(result=result, output_path=output_path)
        if result.returncode != 0:
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
                workspace_path=str(repo_root),
            )

        mutation_errors = protected_source_mutation_errors(
            before=before,
            after=protected_source_snapshot(repo_root),
        )
        if mutation_errors:
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
                workspace_path=str(repo_root),
                contract_errors=mutation_errors,
            )

        return proposal_from_file_protocol_output(
            raw_output=raw_response,
            target_file=target_file,
            round_index=round_index,
            repo_root=repo_root,
            command=command,
            agent_input_path=agent_input_path,
        )


def run_file_protocol_command(
    *,
    command: list[str],
    cwd: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    """Run an external file-protocol agent command."""
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )


def proposal_from_file_protocol_output(
    *,
    raw_output: str,
    target_file: Path,
    round_index: int,
    repo_root: Path,
    command: list[str],
    agent_input_path: Path,
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
            workspace_path=str(repo_root),
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
        workspace_path=str(repo_root),
    )


def response_text(
    *,
    result: subprocess.CompletedProcess[str],
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


def protected_source_snapshot(repo_root: Path) -> dict[str, str]:
    """Return hashes for source files an external agent must not mutate."""
    snapshot: dict[str, str] = {}
    for protected_path in PROTECTED_PATHS:
        path = repo_root / protected_path
        if path.is_file():
            snapshot[path.relative_to(repo_root).as_posix()] = file_sha256(path)
        elif path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and not ignored_path(child):
                    snapshot[child.relative_to(repo_root).as_posix()] = file_sha256(child)
    return snapshot


def protected_source_mutation_errors(
    *,
    before: dict[str, str],
    after: dict[str, str],
) -> tuple[str, ...]:
    """Return source mutations made by an external file-protocol agent."""
    errors: list[str] = []
    for path in sorted(set(before) | set(after)):
        if before.get(path) == after.get(path):
            continue
        if path not in before:
            errors.append(f"file protocol added protected file: {path}")
        elif path not in after:
            errors.append(f"file protocol deleted protected file: {path}")
        else:
            errors.append(f"file protocol modified protected file: {path}")
    return tuple(errors)


def ignored_path(path: Path) -> bool:
    """Return whether a source snapshot path should be ignored."""
    parts = set(path.parts)
    return "__pycache__" in parts or ".pytest_cache" in parts


def file_sha256(path: Path) -> str:
    """Return a file SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
