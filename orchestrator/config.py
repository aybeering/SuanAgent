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
    stub_old_threshold: str
    stub_new_threshold: str

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
    return ProjectConfig(
        baseline_strategy_module=str(raw["baseline_strategy_module"]),
        current_strategy_module=str(raw["current_strategy_module"]),
        experiments_dir=str(raw["experiments_dir"]),
        max_rounds=int(raw["max_rounds"]),
        datasets={str(key): str(value) for key, value in raw["datasets"].items()},
        policy={str(key): value for key, value in raw["policy"].items()},
        strategy_path=str(raw["strategy_path"]),
        stub_old_threshold=str(stub["old_threshold"]),
        stub_new_threshold=str(stub["new_threshold"]),
    )
