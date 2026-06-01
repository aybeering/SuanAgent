"""Configuration loading for V0.5 experiment loops."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG_PATH = Path("config/default.json")


@dataclass(frozen=True)
class ProjectConfig:
    """Runtime configuration for deterministic strategy experiments."""

    baseline_strategy_module: str
    current_strategy_module: str
    experiments_dir: str
    max_rounds: int
    datasets: dict[str, str]
    policy: dict[str, float | int]
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
    modifier_settings = raw.get("codex_cli", {}) if modifier_name.startswith("codex") else {}
    memory_filter = raw.get("memory_filter", {})
    exploration = raw.get("exploration", {})
    fallback_names = fallback_modifier_names(memory_filter)
    return ProjectConfig(
        baseline_strategy_module=str(raw["baseline_strategy_module"]),
        current_strategy_module=str(raw["current_strategy_module"]),
        experiments_dir=str(raw["experiments_dir"]),
        max_rounds=int(raw["max_rounds"]),
        datasets={str(key): str(value) for key, value in raw["datasets"].items()},
        policy={str(key): value for key, value in raw["policy"].items()},
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
