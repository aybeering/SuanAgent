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
    "champion_gap_weight": 1.0,
    "probe_ev_multiplier": 1000,
    "probe_ev_cap": 25,
    "probe_trade_count_cap": 5,
    "champion_gap_multiplier": 1000,
    "champion_gap_cap": 15,
}


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
    fallback_names = fallback_modifier_names(memory_filter)
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
