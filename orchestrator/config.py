"""Configuration loading for V0.5 experiment loops."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_CONFIG_PATH = Path("config/default.json")
DEFAULT_CANDIDATE_SELECTION = {
    "base_selectable_score": 100,
    "primary_modifier_bonus": 2,
    "expected_metric_weight": 1.0,
    "risk_weight": 1.0,
    "direction_prior_weight": 1.0,
    "exploration_bonus_weight": 1.0,
    "probe_weight": 1.0,
    "routing_prior_weight": 1.0,
    "routing_prefer_bonus": 8,
    "routing_downweight_penalty": 12,
    "champion_gap_weight": 1.0,
    "probe_ev_multiplier": 1000,
    "probe_ev_cap": 25,
    "probe_trade_count_cap": 5,
    "champion_gap_multiplier": 1000,
    "champion_gap_cap": 15,
}
DEFAULT_EXECUTOR = {
    "mode": "sequential",
    "max_candidates": 0,
    "per_agent_timeout_seconds": 120,
    "allow_disabled_adapters": True,
}
AGENT_CONTRACT_RUNNER_NAME = "agent_contract_runner_v1"
CODEX_CLI_GUARDED_RUNNER_NAME = "codex_cli_guarded_adapter"
IN_PROCESS_RUNNER_NAME = "in_process_modifier"
WORKSPACE_DRY_RUNNER_NAME = "workspace_dry_run"
CONTRACT_RUNNER_ADAPTERS = {"file_protocol"}
WORKSPACE_ADAPTERS = {"file_protocol", "codex_cli", "codex_dry_run"}


@dataclass(frozen=True)
class ProjectConfig:
    """Runtime configuration for deterministic strategy experiments."""

    baseline_strategy_module: str
    current_strategy_module: str
    experiments_dir: str
    max_rounds: int
    datasets: dict[str, str]
    policy: dict[str, float | int]
    holdout_policy: dict[str, float | int | bool]
    strategy_path: str
    strategy_modifier: str
    modifier_settings: dict[str, object]
    stub_old_threshold: str
    stub_new_threshold: str
    stop_on_repeated_proposal: bool
    memory_failed_patch_threshold: int = 2
    memory_failed_direction_threshold: int = 3
    memory_fallback_modifier: str = ""
    memory_fallback_modifiers: tuple[str, ...] = ()
    stop_after_no_improvement_rounds: int = 0
    min_probe_ev_delta: float = 0.0
    min_validation_ev_delta: float = 0.0
    explore_after_no_improvement_rounds: int = 0
    explore_low_sample_threshold: int = 1
    explore_bonus: int = 0
    candidate_selection: dict[str, float | int] = field(default_factory=dict)
    executor: dict[str, object] = field(default_factory=dict)
    agent_profiles: tuple[dict[str, object], ...] = ()

    def resolve_path(self, repo_root: Path, path_text: str) -> Path:
        """Resolve config paths relative to the repository root."""
        path = Path(path_text)
        return path if path.is_absolute() else repo_root / path

    def dataset_path(self, repo_root: Path, split: str) -> Path:
        """Return the configured path for a dataset split."""
        try:
            return self.resolve_path(repo_root, self.datasets[split])
        except KeyError as exc:
            raise KeyError(f"Missing dataset split in config: {split}") from exc


def load_project_config(
    repo_root: Path = Path("."),
    config_path: Path | None = None,
) -> ProjectConfig:
    """Load project configuration from JSON."""
    repo_root = repo_root.resolve()
    active_path = config_path or repo_root / DEFAULT_CONFIG_PATH
    if not active_path.is_absolute():
        active_path = repo_root / active_path

    raw = json.loads(active_path.read_text(encoding="utf-8"))
    stub = raw.get("stub", {})
    modifier_name = str(raw["strategy_modifier"])
    modifier_settings = modifier_settings_for(raw, modifier_name)
    memory_filter = raw.get("memory_filter", {})
    exploration = raw.get("exploration", {})
    candidate_selection = DEFAULT_CANDIDATE_SELECTION | raw.get(
        "candidate_selection",
        {},
    )
    executor = DEFAULT_EXECUTOR | raw.get("executor", {})
    fallback_names = fallback_modifier_names(memory_filter)
    agent_profiles = normalize_agent_profiles(raw=raw)
    return ProjectConfig(
        baseline_strategy_module=str(raw["baseline_strategy_module"]),
        current_strategy_module=str(raw["current_strategy_module"]),
        experiments_dir=str(raw["experiments_dir"]),
        max_rounds=int(raw["max_rounds"]),
        datasets={str(key): str(value) for key, value in raw["datasets"].items()},
        policy={str(key): value for key, value in raw["policy"].items()},
        holdout_policy={
            str(key): value for key, value in raw.get("holdout_policy", {}).items()
        },
        strategy_path=str(raw["strategy_path"]),
        strategy_modifier=modifier_name,
        modifier_settings={
            str(key): value for key, value in modifier_settings.items()
        },
        stub_old_threshold=str(stub["old_threshold"]),
        stub_new_threshold=str(stub["new_threshold"]),
        stop_on_repeated_proposal=bool(raw.get("stop_on_repeated_proposal", True)),
        memory_failed_patch_threshold=int(
            memory_filter.get("failed_patch_threshold", 2)
        ),
        memory_failed_direction_threshold=int(
            memory_filter.get("failed_direction_threshold", 3)
        ),
        memory_fallback_modifier=fallback_names[0] if fallback_names else "",
        memory_fallback_modifiers=fallback_names,
        stop_after_no_improvement_rounds=int(
            exploration.get("stop_after_no_improvement_rounds", 0)
        ),
        min_probe_ev_delta=float(exploration.get("min_probe_ev_delta", 0.0)),
        min_validation_ev_delta=float(
            exploration.get("min_validation_ev_delta", 0.0)
        ),
        explore_after_no_improvement_rounds=int(
            exploration.get("explore_after_no_improvement_rounds", 0)
        ),
        explore_low_sample_threshold=int(
            exploration.get("explore_low_sample_threshold", 1)
        ),
        explore_bonus=int(exploration.get("explore_bonus", 0)),
        candidate_selection={
            str(key): value for key, value in candidate_selection.items()
        },
        executor={str(key): value for key, value in executor.items()},
        agent_profiles=agent_profiles,
    )


def fallback_modifier_names(memory_filter: object) -> tuple[str, ...]:
    """Return configured fallback modifier names without duplicates."""
    if not isinstance(memory_filter, dict):
        return ()
    raw_names: list[object] = []
    legacy_name = memory_filter.get("fallback_modifier")
    if legacy_name:
        raw_names.append(legacy_name)
    configured_names = memory_filter.get("fallback_modifiers", [])
    if isinstance(configured_names, str):
        raw_names.append(configured_names)
    elif isinstance(configured_names, list):
        raw_names.extend(configured_names)

    names: list[str] = []
    for raw_name in raw_names:
        name = str(raw_name)
        if name and name not in names:
            names.append(name)
    return tuple(names)


def modifier_settings_for(raw: dict[str, object], modifier_name: str) -> dict[str, object]:
    """Return modifier-specific settings from raw config."""
    if modifier_name.startswith("codex"):
        settings = raw.get("codex_cli", {})
    elif modifier_name == "file_protocol":
        settings = raw.get("file_protocol", {})
    else:
        settings = {}
    return settings if isinstance(settings, dict) else {}


def normalize_agent_profiles(
    *,
    raw: dict[str, object],
) -> tuple[dict[str, object], ...]:
    """Return explicit agent profiles from config."""
    raw_profiles = raw.get("agents", [])
    if isinstance(raw_profiles, list) and raw_profiles:
        return tuple(
            normalize_agent_profile(raw_profile, index)
            for index, raw_profile in enumerate(raw_profiles, start=1)
            if isinstance(raw_profile, dict)
        )
    return ()


def normalize_agent_profile(
    raw_profile: dict[str, object],
    index: int,
) -> dict[str, object]:
    """Return a normalized explicit agent profile."""
    settings = raw_profile.get("settings", {})
    adapter = str(raw_profile.get("adapter", ""))
    normalized_settings = settings if isinstance(settings, dict) else {}
    return {
        "name": str(raw_profile.get("name", f"agent_{index:02d}")),
        "adapter": adapter,
        "role": str(raw_profile.get("role", "fallback")),
        "enabled": bool(raw_profile.get("enabled", True)),
        "settings": normalized_settings,
        "runner": normalize_runner_capability(
            adapter_name=adapter,
            settings=normalized_settings,
            raw_runner=raw_profile.get("runner", {}),
        ),
    }


def normalize_runner_capability(
    *,
    adapter_name: str,
    settings: dict[str, object],
    raw_runner: object = None,
) -> dict[str, object]:
    """Return normalized runner capability metadata for one agent profile."""
    overrides = raw_runner if isinstance(raw_runner, dict) else {}
    default_runner = default_runner_name(adapter_name)
    output_filename = str(
        settings.get(
            "output_filename",
            "agent_command_output.json" if adapter_name == "file_protocol" else "",
        )
    )
    return {
        "runner_name": str(overrides.get("runner_name", default_runner)),
        "isolation": str(
            overrides.get(
                "isolation",
                "workspace" if adapter_name in WORKSPACE_ADAPTERS else "none",
            )
        ),
        "execution_enabled": bool(
            overrides.get(
                "execution_enabled",
                settings.get("execute", adapter_name not in WORKSPACE_ADAPTERS),
            )
        ),
        "timeout_seconds": int(
            overrides.get("timeout_seconds", settings.get("timeout_seconds", 0))
        ),
        "workspace_root": str(
            overrides.get(
                "workspace_root",
                settings.get("workspace_root", "workspaces")
                if adapter_name in WORKSPACE_ADAPTERS
                else "",
            )
        ),
        "output_mode": str(
            overrides.get(
                "output_mode",
                "file_contract"
                if adapter_name == "file_protocol"
                else "stdout_patch"
                if adapter_name == "codex_cli"
                else "none",
            )
        ),
        "allowed_output_files": string_list(
            overrides.get(
                "allowed_output_files",
                (output_filename,) if output_filename else (),
            )
        ),
    }


def default_runner_name(adapter_name: str) -> str:
    """Return the default runner label for an adapter."""
    if adapter_name in CONTRACT_RUNNER_ADAPTERS:
        return AGENT_CONTRACT_RUNNER_NAME
    if adapter_name == "codex_cli":
        return CODEX_CLI_GUARDED_RUNNER_NAME
    if adapter_name == "codex_dry_run":
        return WORKSPACE_DRY_RUNNER_NAME
    return IN_PROCESS_RUNNER_NAME


def string_list(value: object) -> list[str]:
    """Return a deterministic list of strings from config values."""
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list | tuple):
        return [str(item) for item in value if str(item)]
    return []
