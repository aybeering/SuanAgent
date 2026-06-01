"""Guarded external agent adapter using agent I/O JSON fixtures."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from agents.codex_dry_run_adapter import (
    extract_proposal_metadata,
    metadata_expected_metric_change,
    metadata_hypotheses,
    metadata_patch_diff,
    workspace_manifest_output_path,
    workspace_ids_from_report,
)
from orchestrator.patch_parser import (
    PatchParseError,
    extract_unified_diff,
    validate_patch_targets,
)
from orchestrator.proposal import StrategyProposal
from orchestrator.agent_contract_runner import (
    AGENT_EXECUTION_SCHEMA_VERSION,
    run_agent_contract,
)
from orchestrator.workspace_manager import (
    create_isolated_workspace,
    write_workspace_manifest,
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
        attempt_id: str = "",
        profile_name: str = "",
        adapter_name: str = "",
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
            attempt_id=attempt_id,
            profile_name=profile_name,
        )
        workspace_round_dir = workspace_path / "experiments" / run_id / round_id
        copy_agent_round_inputs(
            source_round_dir=round_dir,
            workspace_round_dir=workspace_round_dir,
        )
        agent_input_path = workspace_round_dir / "agent_input.json"
        output_path = workspace_round_dir / self.output_filename
        allowed_output_path = output_path.relative_to(workspace_path).as_posix()
        write_active_agent_input(
            agent_input_path=agent_input_path,
            attempt_id=attempt_id,
            profile_name=profile_name,
            adapter_name=adapter_name,
            agent_name=self.agent_name,
            output_filename=self.output_filename,
            workspace_output_path=allowed_output_path,
        )
        write_workspace_manifest(
            output_path=workspace_manifest_output_path(
                round_dir=round_dir,
                attempt_id=attempt_id,
            ),
            repo_root=repo_root,
            workspace_path=workspace_path,
            run_id=f"{run_id}-file-protocol",
            round_id=round_id,
            agent_name=self.agent_name,
            execution_enabled=self.execute,
            allowed_mutation_paths=(allowed_output_path,),
            attempt_id=attempt_id,
            profile_name=profile_name,
            adapter_name=adapter_name,
        )
        command = [
            self.executable,
            *self.args,
            str(agent_input_path),
            str(output_path),
        ]

        contract_result = run_agent_contract(
            output_path=agent_execution_output_path(
                round_dir=round_dir,
                attempt_id=attempt_id,
            ),
            agent_name=self.agent_name,
            profile_name=profile_name,
            adapter_name=adapter_name,
            command=command,
            cwd=workspace_path,
            workspace_path=workspace_path,
            agent_input_path=agent_input_path,
            workspace_output_path=output_path,
            round_output_path=round_dir / self.output_filename,
            timeout_seconds=self.timeout_seconds,
            execute=self.execute,
            allowed_mutation_paths=(allowed_output_path,),
            disabled_response="file protocol execution disabled",
        )

        if contract_result.status == "disabled":
            return StrategyProposal(
                agent_name=self.agent_name,
                round_index=round_index,
                target_file=str(target_relative),
                summary="File-protocol agent execution is disabled by config.",
                risk_notes="No subprocess was invoked; set execute=true to run it.",
                expected_metric_change={},
                raw_response=contract_result.raw_response,
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

        if contract_result.status == "timeout":
            return StrategyProposal(
                agent_name=self.agent_name,
                round_index=round_index,
                target_file=str(target_relative),
                summary="File-protocol agent execution timed out.",
                risk_notes="No patch was accepted because the subprocess timed out.",
                expected_metric_change={},
                raw_response=contract_result.raw_response,
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
        if contract_result.status == "command_failed":
            returncode = (
                contract_result.result.returncode
                if contract_result.result is not None
                else None
            )
            return StrategyProposal(
                agent_name=self.agent_name,
                round_index=round_index,
                target_file=str(target_relative),
                summary="File-protocol agent execution failed.",
                risk_notes="No patch was accepted because the subprocess failed.",
                expected_metric_change={},
                raw_response=contract_result.raw_response,
                patch_diff="",
                applicable=False,
                direction_tag="file_protocol_failed",
                hypotheses=("The external agent command must exit successfully.",),
                rejection_reason=f"File-protocol agent exited with {returncode}.",
                prompt=str(agent_input_path),
                command=tuple(command),
                workspace_path=str(workspace_path),
            )

        if contract_result.status == "workspace_violation":
            return StrategyProposal(
                agent_name=self.agent_name,
                round_index=round_index,
                target_file=str(target_relative),
                summary="File-protocol agent mutated protected source files.",
                risk_notes="Source mutation guard rejected the subprocess output.",
                expected_metric_change={},
                raw_response=contract_result.raw_response,
                patch_diff="",
                applicable=False,
                direction_tag="file_protocol_source_violation",
                hypotheses=(
                    "External file-protocol agents must only emit proposal JSON.",
                ),
                rejection_reason=(
                    "proposal contract invalid: "
                    + "; ".join(contract_result.mutation_errors)
                ),
                prompt=str(agent_input_path),
                command=tuple(command),
                workspace_path=str(workspace_path),
                contract_errors=contract_result.mutation_errors,
            )

        return proposal_from_file_protocol_output(
            raw_output=contract_result.raw_response,
            target_file=target_file,
            round_index=round_index,
            repo_root=repo_root,
            command=command,
            agent_input_path=agent_input_path,
            workspace_path=workspace_path,
        )


def agent_execution_output_path(*, round_dir: Path, attempt_id: str) -> Path:
    """Return where to store execution audit before attempt selection."""
    if not attempt_id:
        return round_dir / "agent_execution.json"
    return round_dir / "agent_executions" / f"{attempt_id}.json"


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
    source_bundle = source_round_dir / "agent_input_bundle"
    if source_bundle.exists():
        shutil.copytree(
            source_bundle,
            workspace_round_dir / "agent_input_bundle",
            dirs_exist_ok=True,
        )


def write_active_agent_input(
    *,
    agent_input_path: Path,
    attempt_id: str,
    profile_name: str,
    adapter_name: str,
    agent_name: str,
    output_filename: str,
    workspace_output_path: str,
) -> None:
    """Add current attempt metadata to the workspace-local agent input."""
    if not agent_input_path.exists():
        return
    payload = json.loads(agent_input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return
    payload["active_agent"] = {
        "attempt_id": attempt_id,
        "role": role_from_attempt_id(attempt_id),
        "profile_name": profile_name,
        "adapter_name": adapter_name,
        "agent_name": agent_name,
        "output_filename": output_filename,
    }
    output_contract = payload.get("output_contract", {})
    if isinstance(output_contract, dict):
        output_contract["workspace_output_path"] = workspace_output_path
        output_contract["expected_command_output_filename"] = output_filename
    agent_input_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    bundle_copy = agent_input_path.parent / "agent_input_bundle" / "agent_input.json"
    if bundle_copy.exists():
        shutil.copy2(agent_input_path, bundle_copy)


def role_from_attempt_id(attempt_id: str) -> str:
    """Return queue role embedded in a stable attempt id."""
    if not attempt_id:
        return ""
    parts = attempt_id.split("_", maxsplit=2)
    return parts[2] if len(parts) == 3 else ""
