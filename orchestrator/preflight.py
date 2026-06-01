"""Preflight validation for experiment configuration."""

from __future__ import annotations

import importlib.util
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from agents.registry import SUPPORTED_MODIFIERS
from orchestrator.config import ProjectConfig, load_project_config


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
        )

    validate_config(config, repo_root, errors, warnings)
    return PreflightResult(ok=not errors, errors=errors, warnings=warnings)


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
    validate_executor(config, errors)
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
    for index, profile in enumerate(config.agent_profiles, start=1):
        name = str(profile.get("name", ""))
        adapter = str(profile.get("adapter", ""))
        role = str(profile.get("role", ""))
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
        if enabled and role == "primary":
            enabled_primary_count += 1
    if config.agent_profiles and enabled_primary_count != 1:
        errors.append("agents must contain exactly one enabled primary profile")


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
