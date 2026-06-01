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

    strategy_path = config.resolve_path(repo_root, config.strategy_path)
    if not strategy_path.exists():
        errors.append(f"strategy file does not exist: {strategy_path}")

    validate_importable_module(config.baseline_strategy_module, errors)
    validate_importable_module(config.current_strategy_module, errors)

    if config.strategy_modifier not in SUPPORTED_MODIFIERS:
        errors.append(f"unsupported strategy_modifier: {config.strategy_modifier}")

    if config.strategy_modifier == "codex_cli":
        validate_codex_cli_settings(config, errors, warnings)


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
