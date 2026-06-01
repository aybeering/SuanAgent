"""Startup checks for agent role/profile activation boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.registry import SUPPORTED_MODIFIERS
from orchestrator.config import (
    AGENT_CONTRACT_RUNNER_NAME,
    CODEX_CLI_GUARDED_RUNNER_NAME,
    DEFAULT_AGENT_ROLES,
    IN_PROCESS_RUNNER_NAME,
    WORKSPACE_DRY_RUNNER_NAME,
    ProjectConfig,
    default_runner_name,
    normalize_runner_capability,
)


AGENT_ACTIVATION_PREFLIGHT_SCHEMA_VERSION = "agent_activation_preflight_v1"
WORKSPACE_ADAPTERS = {"codex_cli", "codex_dry_run", "codex_cli_dry_run", "file_protocol"}
CONTRACT_ADAPTERS = {"file_protocol"}


def write_agent_activation_preflight(
    *,
    output_path: Path,
    markdown_path: Path,
    repo_root: Path,
    run_id: str,
    config: ProjectConfig,
    agent_profiles: tuple[dict[str, object], ...] | None = None,
    agent_roles: tuple[dict[str, object], ...] | None = None,
    allow_unregistered_adapters: bool = False,
) -> Path:
    """Write the run-level activation preflight artifact."""
    payload = agent_activation_preflight_payload(
        repo_root=repo_root,
        run_id=run_id,
        config=config,
        agent_profiles=agent_profiles,
        agent_roles=agent_roles,
        allow_unregistered_adapters=allow_unregistered_adapters,
    )
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        agent_activation_preflight_markdown(payload),
        encoding="utf-8",
    )
    return output_path


def agent_activation_preflight_payload(
    *,
    repo_root: Path,
    run_id: str,
    config: ProjectConfig,
    agent_profiles: tuple[dict[str, object], ...] | None = None,
    agent_roles: tuple[dict[str, object], ...] | None = None,
    allow_unregistered_adapters: bool = False,
) -> dict[str, object]:
    """Return the deterministic agent activation preflight payload."""
    roles = effective_agent_roles(config) if agent_roles is None else agent_roles
    profiles = (
        effective_agent_profiles(config)
        if agent_profiles is None
        else agent_profiles
    )
    role_rows = role_rows_for(roles)
    profile_rows = profile_rows_for(
        profiles=profiles,
        roles=roles,
        allow_unregistered_adapters=allow_unregistered_adapters,
    )
    errors = [
        *role_blocking_errors(role_rows),
        *profile_blocking_errors(profile_rows),
    ]
    warnings = profile_warnings(profile_rows)
    return {
        "schema_version": AGENT_ACTIVATION_PREFLIGHT_SCHEMA_VERSION,
        "run_id": run_id,
        "repo_root": str(repo_root.resolve()),
        "ok": not errors,
        "blocking_errors": errors,
        "warnings": warnings,
        "roles": role_rows,
        "profiles": profile_rows,
        "summary": {
            "role_count": len(role_rows),
            "profile_count": len(profile_rows),
            "enabled_profile_count": sum(
                1 for profile in profile_rows if bool(profile["enabled"])
            ),
            "enabled_primary_count": sum(
                1
                for profile in profile_rows
                if bool(profile["enabled"]) and profile["queue_role"] == "primary"
            ),
            "ready_enabled_profiles": [
                profile["profile_name"]
                for profile in profile_rows
                if profile["activation_status"] == "ready"
            ],
            "blocked_enabled_profiles": [
                profile["profile_name"]
                for profile in profile_rows
                if profile["activation_status"] == "blocked"
            ],
            "disabled_visible_profiles": [
                profile["profile_name"]
                for profile in profile_rows
                if profile["activation_status"] == "disabled_visible"
            ],
        },
        "policy": {
            "only_strategy_modifier_executes_in_v0_5": True,
            "disabled_future_roles_are_manifest_only": True,
            "programmatic_unregistered_adapters_allowed": allow_unregistered_adapters,
            "activation_preflight_can_change_acceptance": False,
            "activation_preflight_can_change_routing": False,
            "deterministic_gates_keep_acceptance_authority": True,
        },
    }


def effective_agent_roles(config: ProjectConfig) -> tuple[dict[str, object], ...]:
    """Return configured roles, falling back to repository defaults."""
    return config.agent_roles or tuple(dict(role) for role in DEFAULT_AGENT_ROLES)


def effective_agent_profiles(config: ProjectConfig) -> tuple[dict[str, object], ...]:
    """Return explicit profiles or legacy profiles derived from modifier config."""
    if config.agent_profiles:
        return config.agent_profiles
    profiles: list[dict[str, object]] = [
        {
            "name": "primary",
            "adapter": config.strategy_modifier,
            "role": "primary",
            "agent_role": "strategy_modifier",
            "enabled": True,
            "settings": config.modifier_settings,
            "runner": normalize_runner_capability(
                adapter_name=config.strategy_modifier,
                settings=config.modifier_settings,
            ),
        }
    ]
    profiles.extend(
        {
            "name": f"fallback_{index:02d}",
            "adapter": fallback_modifier,
            "role": "fallback",
            "agent_role": "strategy_modifier",
            "enabled": True,
            "settings": config.modifier_settings,
            "runner": normalize_runner_capability(
                adapter_name=fallback_modifier,
                settings=config.modifier_settings,
            ),
        }
        for index, fallback_modifier in enumerate(
            config.memory_fallback_modifiers,
            start=1,
        )
    )
    return tuple(profiles)


def role_rows_for(
    roles: tuple[dict[str, object], ...],
) -> list[dict[str, object]]:
    """Return activation rows for configured role contracts."""
    rows: list[dict[str, object]] = []
    active_implemented_roles = active_role_names(roles)
    for role in roles:
        role_name = str(role.get("role_name", ""))
        enabled = bool(role.get("enabled", False))
        implemented = bool(role.get("implemented", False))
        execution_mode = str(role.get("execution_mode", ""))
        can_execute = (
            role_name == "strategy_modifier"
            and role_name in active_implemented_roles
        )
        blockers: list[str] = []
        if not role_name:
            blockers.append("role_name_empty")
        if enabled and execution_mode == "active" and not implemented:
            blockers.append("active_role_not_implemented")
        if role_name != "strategy_modifier" and enabled and execution_mode == "active":
            blockers.append("non_strategy_role_active_in_v0_5")
        if role_name == "strategy_modifier" and not can_execute:
            blockers.append("strategy_modifier_not_active")
        rows.append(
            {
                "role_name": role_name,
                "stage": str(role.get("stage", "")),
                "enabled": enabled,
                "implemented": implemented,
                "execution_mode": execution_mode,
                "decision_authority": str(role.get("decision_authority", "")),
                "allowed_adapters": string_list(role.get("allowed_adapters", [])),
                "can_execute_in_v0_5": can_execute,
                "activation_blockers": blockers,
            }
        )
    return rows


def profile_rows_for(
    *,
    profiles: tuple[dict[str, object], ...],
    roles: tuple[dict[str, object], ...],
    allow_unregistered_adapters: bool = False,
) -> list[dict[str, object]]:
    """Return activation rows for configured agent profiles."""
    role_map = {str(role.get("role_name", "")): role for role in roles}
    active_roles = active_role_names(roles)
    seen_names: set[str] = set()
    rows: list[dict[str, object]] = []
    for index, profile in enumerate(profiles, start=1):
        profile_name = str(profile.get("name", ""))
        adapter_name = str(profile.get("adapter", ""))
        agent_role = str(profile.get("agent_role", "strategy_modifier"))
        queue_role = str(profile.get("role", ""))
        enabled = bool(profile.get("enabled", True))
        runner = dict_or_empty(profile.get("runner", {}))
        role = role_map.get(agent_role, {})
        blockers = profile_blockers(
            index=index,
            profile_name=profile_name,
            seen_names=seen_names,
            adapter_name=adapter_name,
            queue_role=queue_role,
            agent_role=agent_role,
            enabled=enabled,
            runner=runner,
            role=role,
            active_roles=active_roles,
            allow_unregistered_adapters=allow_unregistered_adapters,
        )
        warnings = profile_row_warnings(
            adapter_name=adapter_name,
            enabled=enabled,
            runner=runner,
            adapter_registered=adapter_name in SUPPORTED_MODIFIERS,
            allow_unregistered_adapters=allow_unregistered_adapters,
        )
        seen_names.add(profile_name)
        rows.append(
            {
                "profile_index": index,
                "profile_name": profile_name,
                "enabled": enabled,
                "queue_role": queue_role,
                "agent_role": agent_role,
                "adapter_name": adapter_name,
                "activation_status": activation_status(
                    enabled=enabled,
                    blockers=blockers,
                ),
                "activation_blockers": blockers,
                "warnings": warnings,
                "role_contract": {
                    "known": bool(role),
                    "active": agent_role in active_roles,
                    "allowed_adapters": string_list(role.get("allowed_adapters", [])),
                },
                "runner": runner,
                "workspace_contract": workspace_contract(
                    adapter_name=adapter_name,
                    runner=runner,
                ),
                "output_contract": output_contract(
                    adapter_name=adapter_name,
                    runner=runner,
                ),
            }
        )
    return rows


def profile_blockers(
    *,
    index: int,
    profile_name: str,
    seen_names: set[str],
    adapter_name: str,
    queue_role: str,
    agent_role: str,
    enabled: bool,
    runner: dict[str, object],
    role: dict[str, object],
    active_roles: set[str],
    allow_unregistered_adapters: bool,
) -> list[str]:
    """Return deterministic activation blockers for one profile."""
    blockers: list[str] = []
    if not profile_name:
        blockers.append(f"agents[{index}].name_empty")
    if profile_name in seen_names:
        blockers.append(f"agents[{index}].name_duplicate")
    adapter_registered = adapter_name in SUPPORTED_MODIFIERS
    if not adapter_registered and not allow_unregistered_adapters:
        blockers.append(f"agents[{index}].adapter_unsupported")
    if queue_role not in {"primary", "fallback"}:
        blockers.append(f"agents[{index}].queue_role_invalid")
    if not role:
        blockers.append(f"agents[{index}].agent_role_unknown")
    elif (
        adapter_name not in string_list(role.get("allowed_adapters", []))
        and (adapter_registered or not allow_unregistered_adapters)
    ):
        blockers.append(f"agents[{index}].adapter_not_allowed_for_role")
    if enabled and agent_role != "strategy_modifier":
        blockers.append(f"agents[{index}].non_strategy_role_enabled")
    if enabled and agent_role not in active_roles:
        blockers.append(f"agents[{index}].agent_role_not_active")
    blockers.extend(runner_blockers(index=index, adapter_name=adapter_name, runner=runner))
    return blockers


def runner_blockers(
    *,
    index: int,
    adapter_name: str,
    runner: dict[str, object],
) -> list[str]:
    """Return blockers for runner capability metadata."""
    blockers: list[str] = []
    runner_name = str(runner.get("runner_name", ""))
    expected_runner = default_runner_name(adapter_name)
    if runner_name not in {
        AGENT_CONTRACT_RUNNER_NAME,
        CODEX_CLI_GUARDED_RUNNER_NAME,
        IN_PROCESS_RUNNER_NAME,
        WORKSPACE_DRY_RUNNER_NAME,
    }:
        blockers.append(f"agents[{index}].runner_name_unsupported")
    elif runner_name != expected_runner:
        blockers.append(f"agents[{index}].runner_name_adapter_mismatch")
    timeout = int_value(runner.get("timeout_seconds", 0))
    if timeout < 0:
        blockers.append(f"agents[{index}].runner_timeout_negative")
    if runner_name == AGENT_CONTRACT_RUNNER_NAME and timeout <= 0:
        blockers.append(f"agents[{index}].runner_timeout_non_positive")
    isolation = str(runner.get("isolation", ""))
    if adapter_name in WORKSPACE_ADAPTERS and isolation != "workspace":
        blockers.append(f"agents[{index}].workspace_isolation_required")
    if adapter_name not in WORKSPACE_ADAPTERS and isolation not in {"none", ""}:
        blockers.append(f"agents[{index}].workspace_isolation_unexpected")
    workspace_root = str(runner.get("workspace_root", ""))
    if adapter_name in WORKSPACE_ADAPTERS and not workspace_root:
        blockers.append(f"agents[{index}].workspace_root_required")
    output_mode = str(runner.get("output_mode", ""))
    allowed_output_files = string_list(runner.get("allowed_output_files", []))
    if adapter_name in CONTRACT_ADAPTERS and output_mode != "file_contract":
        blockers.append(f"agents[{index}].file_contract_output_mode_required")
    if output_mode == "file_contract" and not allowed_output_files:
        blockers.append(f"agents[{index}].allowed_output_files_required")
    for filename in allowed_output_files:
        if "/" in filename or "\\" in filename or filename in {"", ".", ".."}:
            blockers.append(f"agents[{index}].allowed_output_file_must_be_basename")
            break
    return blockers


def profile_row_warnings(
    *,
    adapter_name: str,
    enabled: bool,
    runner: dict[str, object],
    adapter_registered: bool = True,
    allow_unregistered_adapters: bool = False,
) -> list[str]:
    """Return advisory activation warnings for one profile."""
    warnings: list[str] = []
    execution_enabled = bool(runner.get("execution_enabled", False))
    if adapter_name in WORKSPACE_ADAPTERS and not execution_enabled:
        warnings.append("external_execution_disabled")
    if not enabled:
        warnings.append("profile_disabled_manifest_only")
    if not adapter_registered and allow_unregistered_adapters:
        warnings.append("programmatic_unregistered_adapter")
    return warnings


def workspace_contract(
    *,
    adapter_name: str,
    runner: dict[str, object],
) -> dict[str, object]:
    """Return expected workspace contract metadata for one profile."""
    workspace_required = adapter_name in WORKSPACE_ADAPTERS
    return {
        "workspace_required": workspace_required,
        "isolation": str(runner.get("isolation", "")),
        "workspace_root": str(runner.get("workspace_root", "")),
        "path_pattern": (
            "<workspace_root>/<run_id>/<round_id>/<profile>/<attempt_id>/strategy_workspace"
            if workspace_required
            else ""
        ),
        "mutation_guard_required": workspace_required,
    }


def output_contract(
    *,
    adapter_name: str,
    runner: dict[str, object],
) -> dict[str, object]:
    """Return expected output contract metadata for one profile."""
    return {
        "output_mode": str(runner.get("output_mode", "")),
        "allowed_output_files": string_list(runner.get("allowed_output_files", [])),
        "file_contract_required": adapter_name in CONTRACT_ADAPTERS,
        "stdout_patch_allowed": adapter_name == "codex_cli",
    }


def role_blocking_errors(role_rows: list[dict[str, object]]) -> list[str]:
    """Return top-level role activation errors."""
    errors: list[str] = []
    executable = [
        str(role["role_name"])
        for role in role_rows
        if bool(role.get("can_execute_in_v0_5", False))
    ]
    if executable != ["strategy_modifier"]:
        errors.append("agent_activation: only strategy_modifier may execute in V0.5")
    for role in role_rows:
        for blocker in role.get("activation_blockers", []):
            errors.append(
                f"agent_activation: role {role.get('role_name', '')} blocked by {blocker}"
            )
    return errors


def profile_blocking_errors(profile_rows: list[dict[str, object]]) -> list[str]:
    """Return top-level profile activation errors."""
    errors: list[str] = []
    enabled_primary_count = sum(
        1
        for profile in profile_rows
        if bool(profile.get("enabled", False)) and profile.get("queue_role") == "primary"
    )
    if enabled_primary_count != 1:
        errors.append("agent_activation: exactly one enabled primary profile is required")
    for profile in profile_rows:
        if not bool(profile.get("enabled", False)):
            continue
        for blocker in profile.get("activation_blockers", []):
            errors.append(
                "agent_activation: profile "
                f"{profile.get('profile_name', '')} blocked by {blocker}"
            )
    return errors


def profile_warnings(profile_rows: list[dict[str, object]]) -> list[str]:
    """Return top-level profile activation warnings."""
    warnings: list[str] = []
    for profile in profile_rows:
        for warning in profile.get("warnings", []):
            warnings.append(
                f"agent_activation: profile {profile.get('profile_name', '')}: {warning}"
            )
    return warnings


def activation_status(*, enabled: bool, blockers: list[str]) -> str:
    """Return the activation status for a profile row."""
    if not enabled:
        return "disabled_visible"
    return "blocked" if blockers else "ready"


def active_role_names(roles: tuple[dict[str, object], ...]) -> set[str]:
    """Return active implemented role names."""
    return {
        str(role.get("role_name", ""))
        for role in roles
        if bool(role.get("enabled", False))
        and bool(role.get("implemented", False))
        and str(role.get("execution_mode", "")) == "active"
    }


def agent_activation_preflight_markdown(payload: dict[str, object]) -> str:
    """Return a human-readable activation preflight report."""
    profile_lines = []
    for profile in payload.get("profiles", []):
        if not isinstance(profile, dict):
            continue
        blockers = profile.get("activation_blockers", [])
        blocker_text = ", ".join(str(item) for item in blockers) if blockers else "none"
        profile_lines.append(
            "| {name} | {enabled} | {role} | {adapter} | {status} | {blockers} |".format(
                name=profile.get("profile_name", ""),
                enabled=profile.get("enabled", False),
                role=profile.get("agent_role", ""),
                adapter=profile.get("adapter_name", ""),
                status=profile.get("activation_status", ""),
                blockers=blocker_text,
            )
        )
    error_lines = [
        f"- {error}" for error in payload.get("blocking_errors", [])
    ] or ["- none"]
    return "\n".join(
        [
            "# Agent Activation Preflight",
            "",
            f"Run: {payload['run_id']}",
            f"OK: {payload['ok']}",
            "",
            "## Profiles",
            "| Profile | Enabled | Agent role | Adapter | Status | Blockers |",
            "| --- | --- | --- | --- | --- | --- |",
            *profile_lines,
            "",
            "## Blocking Errors",
            *error_lines,
            "",
            "Final acceptance remains controlled by deterministic gates.",
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


def int_value(value: object) -> int:
    """Return an int from simple config values."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except ValueError:
        return 0
