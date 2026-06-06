"""Shared runner for file-contract agent subprocesses."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from orchestrator.workspace_manager import workspace_mutation_errors, workspace_snapshot


AGENT_CONTRACT_RUNNER_NAME = "agent_contract_runner_v1"
CODEX_CLI_GUARDED_RUNNER_NAME = "codex_cli_guarded_adapter"
AGENT_EXECUTION_SCHEMA_VERSION = "agent_execution_v1"
AGENT_EXECUTION_INTAKE_BINDING_SCHEMA_VERSION = "agent_execution_intake_binding_v1"
AUDIT_PREVIEW_CHARS = 500


@dataclass(frozen=True)
class AgentCommandResult:
    """Captured result from an external agent subprocess."""

    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False


@dataclass(frozen=True)
class AgentContractRunResult:
    """Normalized result from running one file-contract agent."""

    status: str
    execution_enabled: bool
    command: tuple[str, ...]
    cwd: Path
    workspace_path: Path
    agent_input_path: Path
    workspace_output_path: Path
    round_output_path: Path
    timeout_seconds: int
    raw_response: str
    mutation_errors: tuple[str, ...]
    allowed_mutation_paths: tuple[str, ...]
    result: AgentCommandResult | None = None


def run_agent_contract(
    *,
    output_path: Path,
    agent_name: str,
    profile_name: str,
    adapter_name: str,
    command: list[str],
    cwd: Path,
    workspace_path: Path,
    agent_input_path: Path,
    workspace_output_path: Path,
    round_output_path: Path,
    timeout_seconds: int,
    execute: bool,
    allowed_mutation_paths: tuple[str, ...],
    disabled_response: str = "agent contract execution disabled",
) -> AgentContractRunResult:
    """Run or skip one external file-contract agent and write execution audit."""
    if not execute:
        contract_result = AgentContractRunResult(
            status="disabled",
            execution_enabled=False,
            command=tuple(command),
            cwd=cwd,
            workspace_path=workspace_path,
            agent_input_path=agent_input_path,
            workspace_output_path=workspace_output_path,
            round_output_path=round_output_path,
            timeout_seconds=timeout_seconds,
            raw_response=disabled_response,
            mutation_errors=(),
            allowed_mutation_paths=allowed_mutation_paths,
            result=None,
        )
        write_agent_execution(
            output_path=output_path,
            agent_name=agent_name,
            profile_name=profile_name,
            adapter_name=adapter_name,
            contract_result=contract_result,
        )
        return contract_result

    before = workspace_snapshot(workspace_path)
    command_result = run_agent_command(
        command=command,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
    )
    raw_response = response_text(result=command_result, output_path=workspace_output_path)
    copy_agent_output_back(
        workspace_output_path=workspace_output_path,
        round_output_path=round_output_path,
    )
    after = workspace_snapshot(workspace_path)
    mutation_errors = workspace_mutation_errors(
        before=before,
        after=after,
        allowed_paths=set(allowed_mutation_paths),
    )
    status = execution_status(
        result=command_result,
        mutation_errors=mutation_errors,
    )
    contract_result = AgentContractRunResult(
        status=status,
        execution_enabled=True,
        command=tuple(command),
        cwd=cwd,
        workspace_path=workspace_path,
        agent_input_path=agent_input_path,
        workspace_output_path=workspace_output_path,
        round_output_path=round_output_path,
        timeout_seconds=timeout_seconds,
        raw_response=raw_response,
        mutation_errors=mutation_errors,
        allowed_mutation_paths=allowed_mutation_paths,
        result=command_result,
    )
    write_agent_execution(
        output_path=output_path,
        agent_name=agent_name,
        profile_name=profile_name,
        adapter_name=adapter_name,
        contract_result=contract_result,
    )
    return contract_result


def execution_status(
    *,
    result: AgentCommandResult,
    mutation_errors: tuple[str, ...],
) -> str:
    """Return the normalized execution status for an agent command."""
    if result.timed_out:
        return "timeout"
    if result.returncode != 0:
        return "command_failed"
    if mutation_errors:
        return "workspace_violation"
    return "completed"


def run_agent_command(
    *,
    command: list[str],
    cwd: Path,
    timeout_seconds: int,
) -> AgentCommandResult:
    """Run an external agent command."""
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
        timeout_message = f"agent command timed out after {timeout_seconds} seconds"
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


def copy_agent_output_back(
    *,
    workspace_output_path: Path,
    round_output_path: Path,
) -> None:
    """Copy external agent output from workspace to real round artifacts."""
    if workspace_output_path.exists():
        shutil.copy2(workspace_output_path, round_output_path)


def write_agent_execution(
    *,
    output_path: Path,
    agent_name: str,
    profile_name: str,
    adapter_name: str,
    contract_result: AgentContractRunResult,
    runner_name: str = AGENT_CONTRACT_RUNNER_NAME,
    stdin_text: str = "",
) -> None:
    """Write a deterministic audit record for one external agent execution."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = contract_result.result
    payload = {
        "schema_version": AGENT_EXECUTION_SCHEMA_VERSION,
        "runner_name": runner_name,
        "agent_name": agent_name,
        "profile_name": profile_name,
        "adapter_name": adapter_name,
        "status": contract_result.status,
        "execution_enabled": contract_result.execution_enabled,
        "command": list(contract_result.command),
        "command_sha256": stable_json_digest(list(contract_result.command)),
        "cwd": str(contract_result.cwd),
        "workspace_path": str(contract_result.workspace_path),
        "agent_input_path": str(contract_result.agent_input_path),
        "workspace_output_path": str(contract_result.workspace_output_path),
        "round_output_path": str(contract_result.round_output_path),
        "timeout_seconds": contract_result.timeout_seconds,
        "returncode": result.returncode if result is not None else None,
        "stdout": stream_summary(result.stdout if result is not None else ""),
        "stderr": stream_summary(result.stderr if result is not None else ""),
        "stdin": stream_summary(stdin_text),
        "raw_response": stream_summary(contract_result.raw_response),
        "output_file": file_summary(contract_result.workspace_output_path),
        "round_output_file": file_summary(contract_result.round_output_path),
        "allowed_mutation_paths": list(contract_result.allowed_mutation_paths),
        "mutation_errors": list(contract_result.mutation_errors),
        "mutation_guard": {
            "allowed_paths": list(contract_result.allowed_mutation_paths),
            "mutation_errors": list(contract_result.mutation_errors),
            "passed": not contract_result.mutation_errors,
        },
        "intake_binding": unbound_intake_binding(),
        "preflight_binding": unbound_preflight_binding(),
    }
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def bind_agent_execution_to_preflight(
    *,
    audit_path: Path,
    run_dir: Path,
    repo_root: Path,
) -> dict[str, object]:
    """Bind one Codex execution audit to startup preflight evidence."""
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    preflight_path = run_dir / "codex_cli_execution_preflight.json"
    preflight = (
        json.loads(preflight_path.read_text(encoding="utf-8"))
        if preflight_path.exists()
        else {}
    )
    binding = build_preflight_binding(
        audit=payload,
        preflight_path=preflight_path,
        preflight=preflight,
        repo_root=repo_root,
        run_id=run_dir.name,
    )
    payload["preflight_binding"] = binding
    audit_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return binding


def build_preflight_binding(
    *,
    audit: dict[str, object],
    preflight_path: Path,
    preflight: dict[str, object],
    repo_root: Path,
    run_id: str,
) -> dict[str, object]:
    """Return deterministic checks tying a Codex audit to startup preflight."""
    profiles = preflight.get("profiles", [])
    profile_name = str(audit.get("profile_name", ""))
    profile = {}
    if isinstance(profiles, list):
        for row in profiles:
            if (
                isinstance(row, dict)
                and str(row.get("profile_name", "")) == profile_name
                and str(row.get("adapter_name", "")) == "codex_cli"
            ):
                profile = row
                break
    expected_execution = object_or_empty(profile.get("expected_execution", {}))
    expected_command = list_or_empty(expected_execution.get("command", []))
    command = list_or_empty(audit.get("command", []))
    expected_workspace_prefix = str(expected_execution.get("workspace_prefix", ""))
    workspace_path = str(audit.get("workspace_path", ""))
    allowed_paths = list_or_empty(audit.get("allowed_mutation_paths", []))
    guard = object_or_empty(audit.get("mutation_guard", {}))
    guard_allowed_paths = list_or_empty(guard.get("allowed_paths", []))
    execution_enabled = bool(audit.get("execution_enabled", False))
    operator_unlock_ready = bool(profile.get("operator_unlock_ready", False))
    canary_exempt = bool(profile.get("canary_exempt", False))
    preflight_run_id = str(preflight.get("run_id", ""))
    preflight_ok = bool(preflight.get("ok", False))
    checks = {
        "preflight_present": preflight_path.exists(),
        "preflight_run_id_matches": preflight_run_id == run_id,
        "preflight_ok": preflight_ok,
        "profile_present": bool(profile),
        "adapter_is_codex_cli": str(audit.get("adapter_name", "")) == "codex_cli",
        "command_matches_preflight": command == expected_command,
        "command_sha256_matches_preflight": (
            str(audit.get("command_sha256", ""))
            == str(expected_execution.get("command_sha256", ""))
        ),
        "workspace_path_under_preflight_prefix": (
            bool(expected_workspace_prefix)
            and path_under_workspace_prefix(
                path_text=workspace_path,
                prefix_text=expected_workspace_prefix,
                repo_root=repo_root,
            )
        ),
        "allowed_mutation_paths_strategy_only": allowed_paths
        == ["strategies/current_strategy.py"],
        "mutation_guard_paths_strategy_only": guard_allowed_paths
        == ["strategies/current_strategy.py"],
        "execution_allowed_by_startup_preflight": (
            not execution_enabled or operator_unlock_ready or canary_exempt
        ),
    }
    bound = all(checks.values())
    return {
        "schema_version": "agent_execution_preflight_binding_v1",
        "status": "bound" if bound else "mismatch",
        "bound": bound,
        "preflight_path": str(preflight_path),
        "preflight_file": file_summary(preflight_path),
        "run_id": run_id,
        "preflight_run_id": preflight_run_id,
        "preflight_ok": preflight_ok,
        "profile_name": profile_name,
        "operator_unlock_ready": operator_unlock_ready,
        "canary_exempt": canary_exempt,
        "expected_command_sha256": str(expected_execution.get("command_sha256", "")),
        "expected_workspace_prefix": expected_workspace_prefix,
        "checks": checks,
        "blocking_reasons": [
            f"preflight_binding:{name}"
            for name, passed in checks.items()
            if not passed
        ],
    }


def bind_agent_execution_to_intake(
    *,
    audit_path: Path,
    agent_validation_path: Path,
    proposal_path: Path,
    raw_agent_output_path: Path,
) -> dict[str, object]:
    """Bind one execution audit to the shared proposal intake artifacts."""
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    validation = json.loads(agent_validation_path.read_text(encoding="utf-8"))
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    raw_output = raw_agent_output_path.read_text(encoding="utf-8")
    binding = build_intake_binding(
        audit=payload,
        agent_validation_path=agent_validation_path,
        validation=validation,
        proposal_path=proposal_path,
        proposal=proposal,
        raw_agent_output_path=raw_agent_output_path,
        raw_agent_output=raw_output,
    )
    payload["intake_binding"] = binding
    audit_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return binding


def build_intake_binding(
    *,
    audit: dict[str, object],
    agent_validation_path: Path,
    validation: dict[str, object],
    proposal_path: Path,
    proposal: dict[str, object],
    raw_agent_output_path: Path,
    raw_agent_output: str,
) -> dict[str, object]:
    """Return deterministic checks tying execution audit to proposal intake."""
    validation_proposal = object_or_empty(validation.get("proposal", {}))
    command = list_or_empty(audit.get("command", []))
    proposal_command = list_or_empty(proposal.get("command", []))
    audit_raw_sha = str(object_or_empty(audit.get("raw_response", {})).get("sha256", ""))
    audit_stdin_sha = str(object_or_empty(audit.get("stdin", {})).get("sha256", ""))
    audit_stdin_chars = int(object_or_empty(audit.get("stdin", {})).get("chars", 0) or 0)
    raw_without_trailing_newline = raw_agent_output.rstrip("\n")
    checks = {
        "agent_validation_present": agent_validation_path.exists(),
        "proposal_present": proposal_path.exists(),
        "raw_agent_output_present": raw_agent_output_path.exists(),
        "validation_embeds_proposal": bool(validation_proposal),
        "validation_proposal_matches_saved_proposal": validation_proposal == proposal,
        "audit_raw_response_matches_proposal": (
            audit_raw_sha == sha256_text(str(proposal.get("raw_response", "")))
        ),
        "raw_agent_output_matches_proposal": (
            raw_without_trailing_newline.rstrip("\n")
            == str(proposal.get("raw_response", "")).rstrip("\n")
        ),
        "audit_command_matches_proposal": command == proposal_command,
        "audit_command_sha256_matches_proposal": (
            str(audit.get("command_sha256", ""))
            == stable_json_digest(proposal_command)
        ),
        "audit_stdin_matches_proposal_prompt": (
            audit_stdin_chars == 0
            or audit_stdin_sha == sha256_text(str(proposal.get("prompt", "")))
        ),
        "validation_patch_hash_matches_proposal": (
            str(validation.get("proposal_patch_sha256", ""))
            == str(proposal.get("patch_sha256", ""))
        ),
        "validation_target_matches_proposal": (
            str(validation.get("proposal_target_file", ""))
            == str(proposal.get("target_file", ""))
        ),
        "validation_applicable_matches_proposal": (
            bool(validation.get("proposal_applicable", False))
            == bool(proposal.get("applicable", False))
        ),
        "validation_agent_input_matches_audit": (
            str(validation.get("agent_input_path", ""))
            == str(audit.get("agent_input_path", ""))
            or str(proposal.get("prompt", "")) == str(audit.get("agent_input_path", ""))
        ),
        "validation_agent_output_matches_raw_path": (
            str(validation.get("agent_output_path", ""))
            == str(raw_agent_output_path)
        ),
    }
    bound = all(checks.values())
    return {
        "schema_version": AGENT_EXECUTION_INTAKE_BINDING_SCHEMA_VERSION,
        "status": "bound" if bound else "mismatch",
        "bound": bound,
        "agent_validation_path": str(agent_validation_path),
        "proposal_path": str(proposal_path),
        "raw_agent_output_path": str(raw_agent_output_path),
        "agent_validation_ok": bool(validation.get("ok", False)),
        "proposal_patch_sha256": str(proposal.get("patch_sha256", "")),
        "proposal_applicable": bool(proposal.get("applicable", False)),
        "checks": checks,
        "blocking_reasons": [
            f"intake_binding:{name}"
            for name, passed in checks.items()
            if not passed
        ],
    }


def unbound_intake_binding() -> dict[str, object]:
    """Return the initial unbound intake-binding block for execution audits."""
    return {
        "schema_version": AGENT_EXECUTION_INTAKE_BINDING_SCHEMA_VERSION,
        "status": "unbound",
        "bound": False,
        "agent_validation_path": "",
        "proposal_path": "",
        "raw_agent_output_path": "",
        "agent_validation_ok": False,
        "proposal_patch_sha256": "",
        "proposal_applicable": False,
        "checks": {
            "agent_validation_present": False,
            "proposal_present": False,
            "raw_agent_output_present": False,
            "validation_embeds_proposal": False,
            "validation_proposal_matches_saved_proposal": False,
            "audit_raw_response_matches_proposal": False,
            "raw_agent_output_matches_proposal": False,
            "audit_command_matches_proposal": False,
            "audit_command_sha256_matches_proposal": False,
            "audit_stdin_matches_proposal_prompt": False,
            "validation_patch_hash_matches_proposal": False,
            "validation_target_matches_proposal": False,
            "validation_applicable_matches_proposal": False,
            "validation_agent_input_matches_audit": False,
            "validation_agent_output_matches_raw_path": False,
        },
        "blocking_reasons": ["intake_binding:not_bound"],
    }


def unbound_preflight_binding() -> dict[str, object]:
    """Return the initial unbound startup-preflight binding block."""
    return {
        "schema_version": "agent_execution_preflight_binding_v1",
        "status": "unbound",
        "bound": False,
        "preflight_path": "",
        "preflight_file": {
            "exists": False,
            "path": "",
            "bytes": 0,
            "sha256": "",
        },
        "profile_name": "",
        "run_id": "",
        "preflight_run_id": "",
        "preflight_ok": False,
        "operator_unlock_ready": False,
        "canary_exempt": False,
        "expected_command_sha256": "",
        "expected_workspace_prefix": "",
        "checks": {
            "preflight_present": False,
            "preflight_run_id_matches": False,
            "preflight_ok": False,
            "profile_present": False,
            "adapter_is_codex_cli": False,
            "command_matches_preflight": False,
            "command_sha256_matches_preflight": False,
            "workspace_path_under_preflight_prefix": False,
            "allowed_mutation_paths_strategy_only": False,
            "mutation_guard_paths_strategy_only": False,
            "execution_allowed_by_startup_preflight": False,
        },
        "blocking_reasons": ["preflight_binding:not_bound"],
    }


def path_under_workspace_prefix(
    *,
    path_text: str,
    prefix_text: str,
    repo_root: Path,
) -> bool:
    """Return whether a path is inside a repo-relative or absolute prefix."""
    if not path_text or not prefix_text:
        return False
    path = Path(path_text)
    prefix = Path(prefix_text)
    if not path.is_absolute():
        path = repo_root / path
    if not prefix.is_absolute():
        prefix = repo_root / prefix
    try:
        path.resolve(strict=False).relative_to(prefix.resolve(strict=False))
    except ValueError:
        return False
    return True


def response_text(
    *,
    result: AgentCommandResult,
    output_path: Path,
) -> str:
    """Return output-file text plus optional stdout and stderr."""
    chunks: list[str] = []
    if output_path.exists():
        output_text = output_path.read_text(encoding="utf-8")
        if output_text.strip():
            chunks.append(output_text)
    if result.stdout.strip():
        chunks.append(result.stdout)
    if result.stderr.strip():
        chunks.append("[stderr]\n" + result.stderr)
    return "\n".join(chunks) or "agent command produced no output"


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


def stable_json_digest(payload: object) -> str:
    """Return a stable digest for one JSON-compatible payload."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256_text(encoded)


def object_or_empty(value: object) -> dict[str, object]:
    """Return a JSON object or an empty mapping."""
    return value if isinstance(value, dict) else {}


def list_or_empty(value: object) -> list[object]:
    """Return a JSON list or an empty list."""
    return value if isinstance(value, list) else []


def text_or_empty(value: str | bytes | None) -> str:
    """Return timeout output as text."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
