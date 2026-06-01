"""Run provenance metadata for reproducible experiments."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from orchestrator.config import DEFAULT_CONFIG_PATH, ProjectConfig


RUN_METADATA_SCHEMA_VERSION = "run_metadata_v1"


def write_run_metadata(
    *,
    output_path: Path,
    run_id: str,
    kind: str,
    repo_root: Path,
    experiments_dir: Path,
    config: ProjectConfig,
    config_path: Path | None,
    overrides: dict[str, object] | None = None,
) -> Path:
    """Write a stable provenance snapshot for one run."""
    payload = build_run_metadata(
        run_id=run_id,
        kind=kind,
        repo_root=repo_root,
        experiments_dir=experiments_dir,
        config=config,
        config_path=config_path,
        overrides=overrides or {},
    )
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def build_run_metadata(
    *,
    run_id: str,
    kind: str,
    repo_root: Path,
    experiments_dir: Path,
    config: ProjectConfig,
    config_path: Path | None,
    overrides: dict[str, object],
) -> dict[str, object]:
    """Return a JSON-friendly run provenance payload."""
    repo_root = repo_root.resolve()
    active_config_path = resolved_config_path(repo_root, config_path)
    config_snapshot = normalize_for_json(asdict(config))
    return {
        "schema_version": RUN_METADATA_SCHEMA_VERSION,
        "run_id": run_id,
        "kind": kind,
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(repo_root),
        "experiments_dir": str(resolve_path(experiments_dir, repo_root)),
        "config_path": str(active_config_path),
        "config_path_exists": active_config_path.exists(),
        "config_snapshot": config_snapshot,
        "resolved_datasets": resolved_datasets(config=config, repo_root=repo_root),
        "dataset_fingerprints": dataset_fingerprints(
            config=config,
            repo_root=repo_root,
        ),
        "strategy_path": str(config.resolve_path(repo_root, config.strategy_path)),
        "strategy_modifier": config.strategy_modifier,
        "modifier_settings": normalize_for_json(config.modifier_settings),
        "overrides": normalize_for_json(overrides),
        "git": git_metadata(repo_root),
    }


def resolved_config_path(repo_root: Path, config_path: Path | None) -> Path:
    """Return the effective config path for metadata."""
    active_path = config_path or repo_root / DEFAULT_CONFIG_PATH
    return active_path if active_path.is_absolute() else repo_root / active_path


def resolved_datasets(*, config: ProjectConfig, repo_root: Path) -> dict[str, str]:
    """Return configured datasets resolved relative to the repository root."""
    datasets: dict[str, str] = {}
    for split in sorted(config.datasets):
        datasets[split] = str(config.dataset_path(repo_root, split))
    return datasets


def dataset_fingerprints(
    *,
    config: ProjectConfig,
    repo_root: Path,
) -> dict[str, dict[str, object]]:
    """Return content fingerprints for configured dataset files."""
    fingerprints: dict[str, dict[str, object]] = {}
    for split in sorted(config.datasets):
        path = config.dataset_path(repo_root, split)
        fingerprints[split] = file_fingerprint(path)
    return fingerprints


def file_fingerprint(path: Path) -> dict[str, object]:
    """Return a stable fingerprint for one file path."""
    if not path.exists() or not path.is_file():
        return {
            "path": str(path),
            "exists": False,
            "bytes": 0,
            "sha256": "",
        }
    data = path.read_bytes()
    return {
        "path": str(path),
        "exists": True,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def git_metadata(repo_root: Path) -> dict[str, object]:
    """Return best-effort Git provenance metadata."""
    commit = run_git(repo_root, "rev-parse", "HEAD")
    branch = run_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    status = run_git(repo_root, "status", "--short")
    return {
        "available": bool(commit),
        "commit": commit,
        "branch": branch,
        "dirty": bool(status.strip()),
        "status_short": status.splitlines() if status else [],
    }


def run_git(repo_root: Path, *args: str) -> str:
    """Run a read-only Git command and return stdout, or empty string."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root."""
    return path if path.is_absolute() else repo_root / path


def normalize_for_json(value: Any) -> object:
    """Convert tuples and Paths to stable JSON-friendly values."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [normalize_for_json(item) for item in value]
    if isinstance(value, list):
        return [normalize_for_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize_for_json(item) for key, item in value.items()}
    return value
