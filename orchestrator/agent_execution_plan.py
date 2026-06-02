"""Pre-execution plan for the deterministic agent queue."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.agent_executor import AgentCandidate, executor_policy_payload
from orchestrator.workspace_manager import safe_workspace_segment


AGENT_EXECUTION_PLAN_SCHEMA_VERSION = "agent_execution_plan_v1"


def write_agent_execution_plan(
    *,
    output_path: Path,
    markdown_path: Path,
    repo_root: Path,
    round_dir: Path,
    run_id: str,
    round_id: str,
    queue: tuple[AgentCandidate, ...],
    executor_config: dict[str, object],
) -> Path:
    """Write the queue plan before any candidate agent is invoked."""
    payload = agent_execution_plan_payload(
        repo_root=repo_root,
        round_dir=round_dir,
        run_id=run_id,
        round_id=round_id,
        queue=queue,
        executor_config=executor_config,
    )
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(agent_execution_plan_markdown(payload), encoding="utf-8")
    return output_path


def agent_execution_plan_payload(
    *,
    repo_root: Path,
    round_dir: Path,
    run_id: str,
    round_id: str,
    queue: tuple[AgentCandidate, ...],
    executor_config: dict[str, object],
) -> dict[str, object]:
    """Return a deterministic pre-execution plan for one round."""
    attempts = [
        candidate_plan_row(
            candidate=candidate,
            repo_root=repo_root,
            round_dir=round_dir,
            run_id=run_id,
            round_id=round_id,
        )
        for candidate in queue
    ]
    return {
        "schema_version": AGENT_EXECUTION_PLAN_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "round_dir": relative_path(round_dir, repo_root),
        "queue_count": len(attempts),
        "execution_policy": executor_policy_payload(executor_config),
        "attempts": attempts,
        "policy": {
            "plan_only": True,
            "does_not_execute_agents": True,
            "does_not_select_candidate": True,
            "acceptance_still_requires_policy_gate": True,
            "only_strategy_modifier_profiles_may_execute": True,
        },
    }


def candidate_plan_row(
    *,
    candidate: AgentCandidate,
    repo_root: Path,
    round_dir: Path,
    run_id: str,
    round_id: str,
) -> dict[str, object]:
    """Return one planned candidate attempt row."""
    runner = dict_or_empty(candidate.runner_capability)
    workspace = workspace_plan(
        runner=runner,
        adapter_name=candidate.adapter_name,
        run_id=run_id,
        round_id=round_id,
        profile_name=candidate.profile_name,
        attempt_id=candidate.attempt_id,
        repo_root=repo_root,
    )
    return {
        "attempt_id": candidate.attempt_id,
        "attempt_index": candidate.attempt_index,
        "queue_role": candidate.role,
        "profile_name": candidate.profile_name,
        "adapter_name": candidate.adapter_name,
        "agent_role": candidate.agent_role,
        "modifier_name": candidate.modifier_name,
        "direction_capability": {
            "schema_version": "direction_capability_v1",
            "supported_directions": list(candidate.supported_directions),
            "wildcard": "*" in candidate.supported_directions,
            "source": "agent_profile_or_adapter_default",
            "enforced_after_proposal_contract": True,
        },
        "runner": runner,
        "workspace": workspace,
        "input_contract": {
            "round_agent_input": relative_path(round_dir / "agent_input.json", repo_root),
            "attempt_agent_input": relative_path(
                round_dir / "agent_attempts" / candidate.attempt_id / "agent_input.json",
                repo_root,
            ),
            "input_bundle_dir": relative_path(
                round_dir / "agent_input_bundle",
                repo_root,
            ),
        },
        "output_contract": output_contract(
            runner=runner,
            adapter_name=candidate.adapter_name,
            round_dir=round_dir,
            attempt_id=candidate.attempt_id,
            repo_root=repo_root,
        ),
        "planned_artifacts": {
            "attempt_dir": relative_path(
                round_dir / "agent_attempts" / candidate.attempt_id,
                repo_root,
            ),
            "proposal": relative_path(
                round_dir / "agent_attempts" / candidate.attempt_id / "proposal.json",
                repo_root,
            ),
            "raw_output": relative_path(
                round_dir / "agent_attempts" / candidate.attempt_id / "raw_agent_output.txt",
                repo_root,
            ),
            "attempt_output": relative_path(
                round_dir / "agent_attempts" / candidate.attempt_id / "attempt_output.json",
                repo_root,
            ),
            "workspace_manifest": relative_path(
                round_dir / "workspace_manifests" / f"{candidate.attempt_id}.json",
                repo_root,
            ),
            "agent_execution": relative_path(
                round_dir / "agent_executions" / f"{candidate.attempt_id}.json",
                repo_root,
            ),
        },
    }


def workspace_plan(
    *,
    runner: dict[str, object],
    adapter_name: str,
    run_id: str,
    round_id: str,
    profile_name: str,
    attempt_id: str,
    repo_root: Path,
) -> dict[str, object]:
    """Return expected workspace path and mutation policy metadata."""
    isolation = str(runner.get("isolation", ""))
    workspace_required = isolation == "workspace"
    workspace_root_text = str(runner.get("workspace_root", ""))
    workspace_root = Path(workspace_root_text) if workspace_root_text else Path("")
    effective_run_id = f"{run_id}-file-protocol" if adapter_name == "file_protocol" else run_id
    workspace_path = Path("")
    if workspace_required and workspace_root_text:
        workspace_path = (
            resolve_path(workspace_root, repo_root)
            / effective_run_id
            / round_id
            / safe_workspace_segment(profile_name)
            / attempt_id
            / "strategy_workspace"
        )
    allowed_mutations = (
        allowed_file_protocol_mutations(runner)
        if adapter_name == "file_protocol"
        else ["strategies/current_strategy.py"]
        if workspace_required
        else []
    )
    return {
        "workspace_required": workspace_required,
        "isolation": isolation,
        "workspace_root": workspace_root_text,
        "effective_workspace_run_id": effective_run_id if workspace_required else "",
        "expected_workspace_path": (
            relative_path(workspace_path, repo_root) if workspace_path else ""
        ),
        "mutation_guard_required": workspace_required,
        "allowed_mutation_paths": allowed_mutations,
    }


def output_contract(
    *,
    runner: dict[str, object],
    adapter_name: str,
    round_dir: Path,
    attempt_id: str,
    repo_root: Path,
) -> dict[str, object]:
    """Return planned output metadata for one attempt."""
    allowed_output_files = string_list(runner.get("allowed_output_files", []))
    return {
        "output_mode": str(runner.get("output_mode", "")),
        "allowed_output_files": allowed_output_files,
        "round_output_files": [
            relative_path(round_dir / filename, repo_root)
            for filename in allowed_output_files
        ],
        "attempt_output_bundle": relative_path(
            round_dir / "agent_output_bundle",
            repo_root,
        ),
        "file_contract_required": adapter_name == "file_protocol",
        "stdout_patch_allowed": adapter_name == "codex_cli",
        "agent_execution_audit": relative_path(
            round_dir / "agent_executions" / f"{attempt_id}.json",
            repo_root,
        ),
    }


def allowed_file_protocol_mutations(runner: dict[str, object]) -> list[str]:
    """Return workspace-local files a file-protocol command may write."""
    return [
        f"experiments/<run_id>/<round_id>/{filename}"
        for filename in string_list(runner.get("allowed_output_files", []))
    ]


def agent_execution_plan_markdown(payload: dict[str, object]) -> str:
    """Return a human-readable queue plan."""
    lines = []
    for attempt in payload.get("attempts", []):
        if not isinstance(attempt, dict):
            continue
        workspace = attempt.get("workspace", {})
        workspace_path = (
            workspace.get("expected_workspace_path", "")
            if isinstance(workspace, dict)
            else ""
        )
        lines.append(
            "| {attempt_id} | {queue_role} | {profile} | {adapter} | {agent_role} | {workspace} |".format(
                attempt_id=attempt.get("attempt_id", ""),
                queue_role=attempt.get("queue_role", ""),
                profile=attempt.get("profile_name", ""),
                adapter=attempt.get("adapter_name", ""),
                agent_role=attempt.get("agent_role", ""),
                workspace=workspace_path or "none",
            )
        )
    return "\n".join(
        [
            "# Agent Execution Plan",
            "",
            f"Run: {payload['run_id']}",
            f"Round: {payload['round_id']}",
            "",
            "| Attempt | Queue role | Profile | Adapter | Agent role | Workspace |",
            "| --- | --- | --- | --- | --- | --- |",
            *lines,
            "",
            "This is a plan-only artifact; final acceptance remains deterministic.",
            "",
        ]
    )


def dict_or_empty(value: object) -> dict[str, object]:
    """Return a string-keyed dict or empty dict."""
    if not isinstance(value, dict):
        return {}
    return {str(key): entry for key, entry in value.items()}


def string_list(value: object) -> list[str]:
    """Return a deterministic list of strings."""
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list | tuple):
        return [str(item) for item in value if str(item)]
    return []


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root."""
    return path if path.is_absolute() else repo_root / path


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
