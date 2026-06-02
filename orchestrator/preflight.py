"""Preflight validation for experiment configuration."""

from __future__ import annotations

import importlib.util
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from agents.registry import SUPPORTED_MODIFIERS
from orchestrator.agent_activation_preflight import (
    agent_activation_preflight_payload,
)
from orchestrator.config import (
    AGENT_CONTRACT_RUNNER_NAME,
    AGENT_ROLE_DECISION_AUTHORITIES,
    AGENT_ROLE_EXECUTION_MODES,
    AGENT_ROLE_STAGES,
    CODEX_CLI_GUARDED_RUNNER_NAME,
    IN_PROCESS_RUNNER_NAME,
    WORKSPACE_DRY_RUNNER_NAME,
    ProjectConfig,
    load_project_config,
    strategy_direction_order,
)


REQUIRED_DATASETS = ("train", "validation", "holdout")
REQUIRED_POLICY_KEYS = (
    "min_trade_count",
    "min_ev_improvement",
    "max_drawdown_worsening",
    "max_slippage_worsening",
)
REQUIRED_HOLDOUT_POLICY_KEYS = (
    "enabled",
    "min_trade_count",
    "min_ev_delta",
    "max_drawdown_worsening",
    "max_slippage_worsening",
)


@dataclass(frozen=True)
class PreflightResult:
    """Structured preflight result."""

    ok: bool
    errors: list[str]
    warnings: list[str]
    agent_activation: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly payload."""
        return asdict(self)


def run_preflight(
    *,
    repo_root: Path = Path("."),
    config_path: Path | None = None,
) -> PreflightResult:
    """Validate config, paths, and guarded execution settings."""
    repo_root = repo_root.resolve()
    errors: list[str] = []
    warnings: list[str] = []

    try:
        config = load_project_config(repo_root, config_path)
    except Exception as exc:
        return PreflightResult(
            ok=False,
            errors=[f"Could not load config: {exc}"],
            warnings=[],
            agent_activation={},
        )

    validate_config(config, repo_root, errors, warnings)
    agent_activation = agent_activation_preflight_payload(
        repo_root=repo_root,
        run_id="preflight",
        config=config,
    )
    append_unique(errors, string_list(agent_activation.get("blocking_errors", [])))
    append_unique(warnings, string_list(agent_activation.get("warnings", [])))
    return PreflightResult(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        agent_activation=agent_activation,
    )


def append_unique(target: list[str], values: list[str]) -> None:
    """Append strings to a list without duplicating existing entries."""
    for value in values:
        if value not in target:
            target.append(value)


def validate_config(
    config: ProjectConfig,
    repo_root: Path,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Populate preflight errors and warnings for a loaded config."""
    if config.max_rounds <= 0:
        errors.append("max_rounds must be positive")
    if config.memory_failed_patch_threshold < 0:
        errors.append("memory_filter.failed_patch_threshold must be non-negative")
    if config.memory_failed_direction_threshold < 0:
        errors.append("memory_filter.failed_direction_threshold must be non-negative")
    if config.stop_after_no_improvement_rounds < 0:
        errors.append(
            "exploration.stop_after_no_improvement_rounds must be non-negative"
        )
    if config.explore_after_no_improvement_rounds < 0:
        errors.append(
            "exploration.explore_after_no_improvement_rounds must be non-negative"
        )
    if config.explore_low_sample_threshold < 0:
        errors.append("exploration.explore_low_sample_threshold must be non-negative")
    if config.explore_bonus < 0:
        errors.append("exploration.explore_bonus must be non-negative")
    validate_candidate_selection(config, errors)
    validate_strategy_search_space(config, errors)
    validate_executor(config, errors)
    validate_agent_roles(config, errors)
    validate_agent_profiles(config, errors)
    for fallback_modifier in config.memory_fallback_modifiers:
        if fallback_modifier not in SUPPORTED_MODIFIERS:
            errors.append(
                f"unsupported memory_filter.fallback_modifiers: {fallback_modifier}"
            )

    for split in REQUIRED_DATASETS:
        if split not in config.datasets:
            errors.append(f"missing dataset split: {split}")
            continue
        path = config.dataset_path(repo_root, split)
        if not path.exists():
            errors.append(f"dataset path does not exist: {path}")

    for key in REQUIRED_POLICY_KEYS:
        if key not in config.policy:
            errors.append(f"missing policy key: {key}")
    for key in REQUIRED_HOLDOUT_POLICY_KEYS:
        if key not in config.holdout_policy:
            errors.append(f"missing holdout_policy key: {key}")
    validate_holdout_policy(config, errors)

    strategy_path = config.resolve_path(repo_root, config.strategy_path)
    if not strategy_path.exists():
        errors.append(f"strategy file does not exist: {strategy_path}")

    validate_importable_module(config.baseline_strategy_module, errors)
    validate_importable_module(config.current_strategy_module, errors)

    if config.strategy_modifier not in SUPPORTED_MODIFIERS:
        errors.append(f"unsupported strategy_modifier: {config.strategy_modifier}")

    if config.strategy_modifier == "codex_cli":
        validate_codex_cli_settings(config, errors, warnings)
    if config.strategy_modifier == "file_protocol":
        validate_file_protocol_settings(config, errors, warnings)


def validate_holdout_policy(config: ProjectConfig, errors: list[str]) -> None:
    """Validate optional holdout gate settings."""
    if not config.holdout_policy:
        return
    if int(config.holdout_policy.get("min_trade_count", 0)) < 0:
        errors.append("holdout_policy.min_trade_count must be non-negative")
    if float(config.holdout_policy.get("max_drawdown_worsening", 0.0)) < 0.0:
        errors.append("holdout_policy.max_drawdown_worsening must be non-negative")
    if float(config.holdout_policy.get("max_slippage_worsening", 0.0)) < 0.0:
        errors.append("holdout_policy.max_slippage_worsening must be non-negative")


def validate_candidate_selection(config: ProjectConfig, errors: list[str]) -> None:
    """Validate candidate scoring settings."""
    non_negative_keys = (
        "base_selectable_score",
        "probe_ev_multiplier",
        "probe_ev_cap",
        "probe_trade_count_cap",
        "routing_prefer_bonus",
        "routing_downweight_penalty",
        "champion_gap_multiplier",
        "champion_gap_cap",
    )
    for key in non_negative_keys:
        if float(config.candidate_selection.get(key, 0.0)) < 0.0:
            errors.append(f"candidate_selection.{key} must be non-negative")


def validate_strategy_search_space(config: ProjectConfig, errors: list[str]) -> None:
    """Validate advisory strategy search-space config."""
    search_space = config.strategy_search_space
    if search_space.get("schema_version") != "strategy_search_space_v1":
        errors.append("strategy_search_space.schema_version must be strategy_search_space_v1")
    directions = search_space.get("directions", [])
    if not isinstance(directions, list) or not directions:
        errors.append("strategy_search_space.directions must be non-empty")
        return
    seen: set[str] = set()
    for index, direction in enumerate(directions, start=1):
        if not isinstance(direction, dict):
            errors.append(f"strategy_search_space.directions[{index}] must be object")
            continue
        direction_tag = str(direction.get("direction_tag", ""))
        if not direction_tag:
            errors.append(
                f"strategy_search_space.directions[{index}].direction_tag must be non-empty"
            )
        if direction_tag in seen:
            errors.append(
                f"strategy_search_space.directions[{index}].direction_tag must be unique: {direction_tag}"
            )
        seen.add(direction_tag)
    fallback = str(search_space.get("fallback_direction", ""))
    if not fallback:
        errors.append("strategy_search_space.fallback_direction must be non-empty")
    policy = search_space.get("policy", {})
    if not isinstance(policy, dict):
        errors.append("strategy_search_space.policy must be object")
        return
    for key in (
        "advisory_only",
        "does_not_route_agents",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            errors.append(f"strategy_search_space.policy.{key} must be true")


def validate_executor(config: ProjectConfig, errors: list[str]) -> None:
    """Validate deterministic executor settings."""
    mode = str(config.executor.get("mode", "sequential"))
    if mode != "sequential":
        errors.append("executor.mode must be sequential")
    if int(config.executor.get("max_candidates", 0)) < 0:
        errors.append("executor.max_candidates must be non-negative")
    if int(config.executor.get("per_agent_timeout_seconds", 1)) <= 0:
        errors.append("executor.per_agent_timeout_seconds must be positive")
    if not isinstance(config.executor.get("allow_disabled_adapters", True), bool):
        errors.append("executor.allow_disabled_adapters must be boolean")


def validate_agent_profiles(config: ProjectConfig, errors: list[str]) -> None:
    """Validate configured agent profiles."""
    enabled_primary_count = 0
    seen_names: set[str] = set()
    known_agent_roles = {
        str(role.get("role_name", ""))
        for role in config.agent_roles
        if str(role.get("role_name", ""))
    }
    active_role_names = {
        str(role.get("role_name", ""))
        for role in config.agent_roles
        if bool(role.get("enabled", False))
        and bool(role.get("implemented", False))
        and str(role.get("execution_mode", "")) == "active"
    }
    for index, profile in enumerate(config.agent_profiles, start=1):
        name = str(profile.get("name", ""))
        adapter = str(profile.get("adapter", ""))
        role = str(profile.get("role", ""))
        agent_role = str(profile.get("agent_role", ""))
        enabled = bool(profile.get("enabled", True))
        if not name:
            errors.append(f"agents[{index}].name must be non-empty")
        if name in seen_names:
            errors.append(f"agents[{index}].name must be unique: {name}")
        seen_names.add(name)
        if adapter not in SUPPORTED_MODIFIERS:
            errors.append(f"agents[{index}].adapter is unsupported: {adapter}")
        if role not in {"primary", "fallback"}:
            errors.append(f"agents[{index}].role must be primary or fallback")
        if agent_role not in known_agent_roles:
            errors.append(f"agents[{index}].agent_role is unknown: {agent_role}")
        if enabled and agent_role not in active_role_names:
            errors.append(
                f"agents[{index}].agent_role is not active in V0.5: {agent_role}"
            )
        validate_agent_profile_runner(
            profile=profile,
            profile_index=index,
            errors=errors,
        )
        validate_agent_profile_direction_capability(
            profile=profile,
            profile_index=index,
            config=config,
            errors=errors,
        )
        if enabled and role == "primary":
            enabled_primary_count += 1
    if config.agent_profiles and enabled_primary_count != 1:
        errors.append("agents must contain exactly one enabled primary profile")


def validate_agent_profile_direction_capability(
    *,
    profile: dict[str, object],
    profile_index: int,
    config: ProjectConfig,
    errors: list[str],
) -> None:
    """Validate one profile's declared strategy-direction capability."""
    supported = profile.get("supported_directions", [])
    if not isinstance(supported, list | tuple):
        errors.append(f"agents[{profile_index}].supported_directions must be an array")
        return
    if not supported:
        errors.append(f"agents[{profile_index}].supported_directions must be non-empty")
        return
    normalized = [str(direction) for direction in supported if str(direction)]
    if len(normalized) != len(set(normalized)):
        errors.append(f"agents[{profile_index}].supported_directions must be unique")
    if "*" in normalized:
        if len(normalized) != 1:
            errors.append(
                f"agents[{profile_index}].supported_directions wildcard must stand alone"
            )
        return
    allowed_directions = set(strategy_direction_order(config.strategy_search_space))
    for direction in normalized:
        if direction not in allowed_directions:
            errors.append(
                "agents"
                f"[{profile_index}].supported_directions contains unknown direction: "
                f"{direction}"
            )


def validate_agent_roles(config: ProjectConfig, errors: list[str]) -> None:
    """Validate configured role contracts."""
    seen_names: set[str] = set()
    active_implemented_roles = 0
    for index, role in enumerate(config.agent_roles, start=1):
        name = str(role.get("role_name", ""))
        stage = str(role.get("stage", ""))
        execution_mode = str(role.get("execution_mode", ""))
        decision_authority = str(role.get("decision_authority", ""))
        enabled = bool(role.get("enabled", False))
        implemented = bool(role.get("implemented", False))
        if not name:
            errors.append(f"agent_roles[{index}].role_name must be non-empty")
        if name in seen_names:
            errors.append(f"agent_roles[{index}].role_name must be unique: {name}")
        seen_names.add(name)
        if stage not in AGENT_ROLE_STAGES:
            errors.append(f"agent_roles[{index}].stage is unsupported: {stage}")
        if execution_mode not in AGENT_ROLE_EXECUTION_MODES:
            errors.append(
                f"agent_roles[{index}].execution_mode is unsupported: {execution_mode}"
            )
        if decision_authority not in AGENT_ROLE_DECISION_AUTHORITIES:
            errors.append(
                "agent_roles"
                f"[{index}].decision_authority is unsupported: {decision_authority}"
            )
        if execution_mode == "active" and not enabled:
            errors.append(f"agent_roles[{index}].active role must be enabled")
        if enabled and execution_mode == "active" and implemented:
            active_implemented_roles += 1
        if enabled and not implemented and execution_mode == "active":
            errors.append(f"agent_roles[{index}].active role must be implemented")
    if not config.agent_roles:
        errors.append("agent_roles must contain at least one role")
    if active_implemented_roles != 1:
        errors.append(
            "agent_roles must contain exactly one active implemented role in V0.5"
        )


def validate_agent_profile_runner(
    *,
    profile: dict[str, object],
    profile_index: int,
    errors: list[str],
) -> None:
    """Validate one agent profile runner capability block."""
    runner = profile.get("runner", {})
    if not isinstance(runner, dict):
        errors.append(f"agents[{profile_index}].runner must be an object")
        return
    runner_name = str(runner.get("runner_name", ""))
    if runner_name not in {
        AGENT_CONTRACT_RUNNER_NAME,
        CODEX_CLI_GUARDED_RUNNER_NAME,
        IN_PROCESS_RUNNER_NAME,
        WORKSPACE_DRY_RUNNER_NAME,
    }:
        errors.append(f"agents[{profile_index}].runner.runner_name is unsupported: {runner_name}")
    timeout = int(runner.get("timeout_seconds", 0))
    if timeout < 0:
        errors.append(f"agents[{profile_index}].runner.timeout_seconds must be non-negative")
    if runner_name == AGENT_CONTRACT_RUNNER_NAME and timeout <= 0:
        errors.append(f"agents[{profile_index}].runner.timeout_seconds must be positive")
    output_mode = str(runner.get("output_mode", ""))
    allowed_output_files = runner.get("allowed_output_files", [])
    if output_mode == "file_contract" and not allowed_output_files:
        errors.append(f"agents[{profile_index}].runner.allowed_output_files must be non-empty")


def validate_importable_module(module_name: str, errors: list[str]) -> None:
    """Check that a configured module can be resolved."""
    if importlib.util.find_spec(module_name) is None:
        errors.append(f"module is not importable: {module_name}")


def validate_codex_cli_settings(
    config: ProjectConfig,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate guarded Codex CLI settings."""
    executable = str(config.modifier_settings.get("executable", "codex"))
    execute = bool(config.modifier_settings.get("execute", False))
    timeout = int(config.modifier_settings.get("timeout_seconds", 120))
    if timeout <= 0:
        errors.append("codex_cli.timeout_seconds must be positive")
    if execute and shutil.which(executable) is None:
        errors.append(f"codex_cli executable not found on PATH: {executable}")
    if not execute:
        warnings.append("codex_cli execution is disabled")


def validate_file_protocol_settings(
    config: ProjectConfig,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate guarded file-protocol agent settings."""
    executable = str(config.modifier_settings.get("executable", "agent-command"))
    execute = bool(config.modifier_settings.get("execute", False))
    timeout = int(config.modifier_settings.get("timeout_seconds", 120))
    if timeout <= 0:
        errors.append("file_protocol.timeout_seconds must be positive")
    if execute and shutil.which(executable) is None:
        errors.append(f"file_protocol executable not found on PATH: {executable}")
    if not execute:
        warnings.append("file_protocol execution is disabled")


def string_list(value: object) -> list[str]:
    """Return a deterministic list of strings."""
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list | tuple):
        return [str(item) for item in value if str(item)]
    return []


def main() -> None:
    """CLI entrypoint for preflight checks."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate SuanAgent configuration.")
    parser.add_argument("--config", type=Path, default=None, help="Path to config JSON.")
    args = parser.parse_args()

    result = run_preflight(config_path=args.config)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if not result.ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
