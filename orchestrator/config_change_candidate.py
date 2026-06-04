"""Read-only config change candidates for the next iteration run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.agent_activation_preflight import effective_agent_profiles
from orchestrator.config import (
    DEFAULT_CONFIG_PATH,
    ProjectConfig,
    adapter_supported_directions,
    load_project_config,
)
from orchestrator.memory_scope_recommendation import build_memory_scope_recommendation
from orchestrator.modifier_profile_recommendation import (
    build_modifier_profile_recommendation,
)
from orchestrator.schema_validation import (
    load_schema,
    validate_json_file,
    validate_json_payload,
)


CONFIG_CHANGE_CANDIDATE_SCHEMA_VERSION = "config_change_candidate_v1"
SCHEMA_PATH = Path("schemas/config_change_candidate.schema.json")


def write_config_change_candidate(
    *,
    run_dir: Path,
    repo_root: Path,
    experiments_dir: Path | None = None,
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown config change candidate artifacts."""
    payload = build_config_change_candidate(
        run_dir=run_dir,
        repo_root=repo_root,
        experiments_dir=experiments_dir,
    )
    errors = validate_config_change_candidate_payload(
        payload,
        run_dir=run_dir,
        repo_root=repo_root,
        experiments_dir=experiments_dir,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "config change candidate failed schema validation: " + "; ".join(errors)
        )
    json_path = run_dir / "config_change_candidate.json"
    md_path = run_dir / "config_change_candidate.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_config_change_candidate_markdown(payload), encoding="utf-8")
    return json_path, md_path, payload


def build_config_change_candidate(
    *,
    run_dir: Path,
    repo_root: Path,
    experiments_dir: Path | None = None,
) -> dict[str, object]:
    """Return deterministic candidate config changes from saved recommendations."""
    repo_root = repo_root.resolve()
    run_dir = run_dir.resolve()
    config_path = repo_root / DEFAULT_CONFIG_PATH
    config_payload = load_json_object(config_path)
    active_config = load_project_config(repo_root=repo_root, config_path=config_path)
    memory_scope_path = run_dir / "memory_scope_recommendation.json"
    if memory_scope_path.exists():
        memory_scope = load_json_object(memory_scope_path)
        memory_scope_from_artifact = True
    else:
        memory_scope = build_memory_scope_recommendation(
            run_dir=run_dir,
            repo_root=repo_root,
            experiments_dir=experiments_dir,
        )
        memory_scope_from_artifact = False
    profile_recommendation_path = run_dir / "modifier_profile_recommendation.json"
    if profile_recommendation_path.exists():
        profile_recommendation = load_json_object(profile_recommendation_path)
        profile_recommendation_from_artifact = True
    else:
        profile_recommendation = build_modifier_profile_recommendation(
            run_dir=run_dir,
            repo_root=repo_root,
            config_path=config_path,
            config=active_config,
        )
        profile_recommendation_from_artifact = False
    changes = [
        *memory_scope_changes(memory_scope=memory_scope),
        *modifier_profile_changes(
            profile_recommendation=profile_recommendation,
            config_payload=config_payload,
            active_config=active_config,
        ),
    ]
    summary = summary_payload(changes=changes)
    sources = [
        {
            "artifact_name": "memory_scope_recommendation",
            "from_artifact": memory_scope_from_artifact,
            "file": file_record(memory_scope_path, repo_root),
        },
        {
            "artifact_name": "config",
            "from_artifact": True,
            "file": file_record(config_path, repo_root),
        },
    ]
    if profile_recommendation_path.exists():
        sources.insert(
            1,
            {
                "artifact_name": "modifier_profile_recommendation",
                "from_artifact": profile_recommendation_from_artifact,
                "file": file_record(profile_recommendation_path, repo_root),
            },
        )
    return {
        "schema_version": CONFIG_CHANGE_CANDIDATE_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": relative_path(run_dir, repo_root),
        "sources": sources,
        "summary": summary,
        "changes": changes,
        "operator_review": {
            "required": bool(changes),
            "status": "pending_review" if changes else "no_candidate_changes",
            "instruction": (
                "Review candidates before manually editing config; this artifact "
                "does not modify repository files."
            ),
        },
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "does_not_write_config": True,
            "does_not_delete_memory": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_route_candidates": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
            "operator_must_apply_changes_manually": True,
        },
    }


def memory_scope_changes(*, memory_scope: dict[str, object]) -> list[dict[str, object]]:
    """Return candidate config changes derived from memory scope recommendation."""
    recommendation = object_value(memory_scope.get("recommendation", {}))
    current_scope = object_value(memory_scope.get("current_scope", {}))
    action = str(recommendation.get("action", ""))
    changes: list[dict[str, object]] = []
    if action == "set_recent_record_limit":
        proposed_limit = int(recommendation.get("recommended_recent_record_limit", 0) or 0)
        current_limit = int(current_scope.get("recent_record_limit", 0) or 0)
        if proposed_limit > 0 and proposed_limit != current_limit:
            changes.append(
                {
                    "candidate_id": "memory_filter_recent_record_limit",
                    "config_path": "memory_filter.recent_record_limit",
                    "operation": "set",
                    "current_value": current_limit,
                    "proposed_value": proposed_limit,
                    "source_artifact": "memory_scope_recommendation.json",
                    "source_action": action,
                    "priority": "medium",
                    "reason_codes": string_list(
                        recommendation.get("reason_codes", [])
                    ),
                    "rationale": str(recommendation.get("message", "")),
                    "risk_notes": [
                        "May ignore older failed proposals in future runs.",
                        "Should be reviewed with memory_hygiene before manual config edits.",
                    ],
                    "applied": False,
                    "requires_operator_review": True,
                }
            )
    return changes


def modifier_profile_changes(
    *,
    profile_recommendation: dict[str, object],
    config_payload: dict[str, object],
    active_config: ProjectConfig,
) -> list[dict[str, object]]:
    """Return candidate config changes derived from profile recommendations."""
    summary = object_value(profile_recommendation.get("summary", {}))
    if str(summary.get("status", "")) != "no_available_profile":
        return []
    suggested_directions = string_list(summary.get("suggested_directions", []))
    suggested_direction = (
        suggested_directions[0]
        if suggested_directions
        else str(active_config.strategy_search_space.get("fallback_direction", ""))
    )
    if not suggested_direction:
        return []
    current_agents = config_value_at_path(config_payload, "agents")
    proposed_agents = proposed_agents_with_guarded_profile(
        current_agents=current_agents,
        active_config=active_config,
        supported_direction=suggested_direction,
    )
    if current_agents == proposed_agents:
        return []
    reason_codes = [
        "modifier_profile_recommendation:no_available_profile",
        f"suggested_direction:{suggested_direction}",
        "add_guarded_codex_cli_dry_run_profile",
    ]
    top_failure_code = str(summary.get("top_failure_code", ""))
    if top_failure_code:
        reason_codes.append(f"top_failure:{top_failure_code}")
    return [
        {
            "candidate_id": f"modifier_profile_add_{safe_id(suggested_direction)}",
            "config_path": "agents",
            "operation": "set",
            "current_value": current_agents,
            "proposed_value": proposed_agents,
            "source_artifact": "modifier_profile_recommendation.json",
            "source_action": "add_guarded_modifier_profile",
            "priority": "high",
            "reason_codes": reason_codes,
            "rationale": (
                "The saved modifier profile recommendation found no enabled "
                f"profile for suggested direction `{suggested_direction}`. "
                "Add a guarded dry-run fallback profile so a future run can "
                "exercise the external-agent boundary without enabling real "
                "Codex CLI execution."
            ),
            "risk_notes": [
                "This replaces implicit legacy modifier settings with an explicit agents list.",
                "The proposed codex_cli_dry_run profile does not execute real Codex CLI.",
                "Operator review should confirm the fallback profile belongs in the next run.",
            ],
            "applied": False,
            "requires_operator_review": True,
        }
    ]


def proposed_agents_with_guarded_profile(
    *,
    current_agents: object,
    active_config: ProjectConfig,
    supported_direction: str,
) -> list[dict[str, object]]:
    """Return an explicit agent list with a guarded dry-run fallback profile."""
    if isinstance(current_agents, list):
        agents = [
            normalize_agent_config_row(row)
            for row in current_agents
            if isinstance(row, dict)
        ]
    else:
        agents = implicit_agent_config_rows(active_config)
    if any(profile_covers_direction(row, supported_direction) for row in agents):
        return agents
    new_profile_name = unique_profile_name(
        existing_names=[
            str(row.get("name", ""))
            for row in agents
            if str(row.get("name", ""))
        ],
        base_name=f"fallback_{safe_id(supported_direction)}",
    )
    agents.append(
        {
            "name": new_profile_name,
            "adapter": "codex_cli_dry_run",
            "role": "fallback",
            "agent_role": "strategy_modifier",
            "enabled": True,
            "supported_directions": ["*"],
            "settings": {
                "execute": False,
            },
        }
    )
    return agents


def implicit_agent_config_rows(active_config: ProjectConfig) -> list[dict[str, object]]:
    """Return explicit config rows equivalent to the current implicit profiles."""
    rows: list[dict[str, object]] = []
    for profile in effective_agent_profiles(active_config):
        rows.append(
            {
                "name": str(profile.get("name", "")),
                "adapter": str(profile.get("adapter", "")),
                "role": str(profile.get("role", "")),
                "agent_role": str(profile.get("agent_role", "strategy_modifier")),
                "enabled": bool(profile.get("enabled", True)),
                "supported_directions": string_list(
                    profile.get("supported_directions", [])
                )
                or list(
                    adapter_supported_directions(
                        adapter_name=str(profile.get("adapter", "")),
                        strategy_search_space=active_config.strategy_search_space,
                    )
                ),
            }
        )
    return rows


def normalize_agent_config_row(row: dict[str, object]) -> dict[str, object]:
    """Return a stable agent config row preserving optional settings."""
    normalized: dict[str, object] = {
        "name": str(row.get("name", "")),
        "adapter": str(row.get("adapter", "")),
        "role": str(row.get("role", "")),
        "agent_role": str(row.get("agent_role", "strategy_modifier")),
        "enabled": bool(row.get("enabled", True)),
        "supported_directions": string_list(row.get("supported_directions", [])),
    }
    settings = row.get("settings", {})
    if isinstance(settings, dict) and settings:
        normalized["settings"] = {str(key): value for key, value in settings.items()}
    return normalized


def profile_covers_direction(row: dict[str, object], direction: str) -> bool:
    """Return whether a profile is enabled and can cover one direction."""
    if not bool(row.get("enabled", True)):
        return False
    supported = string_list(row.get("supported_directions", []))
    return "*" in supported or direction in supported


def unique_profile_name(*, existing_names: list[str], base_name: str) -> str:
    """Return a unique profile name for a proposed config row."""
    if base_name not in existing_names:
        return base_name
    index = 2
    while f"{base_name}_{index}" in existing_names:
        index += 1
    return f"{base_name}_{index}"


def safe_id(value: str) -> str:
    """Return a stable identifier fragment."""
    return "".join(char if char.isalnum() else "_" for char in value).strip("_") or "profile"


def summary_payload(*, changes: list[dict[str, object]]) -> dict[str, object]:
    """Return compact config candidate summary."""
    priorities = [str(change.get("priority", "")) for change in changes]
    return {
        "candidate_count": len(changes),
        "recommended_change_count": len(changes),
        "status": "changes_recommended" if changes else "no_changes_recommended",
        "highest_priority": highest_priority(priorities),
        "config_paths": sorted(
            str(change.get("config_path", ""))
            for change in changes
            if str(change.get("config_path", ""))
        ),
    }


def highest_priority(priorities: list[str]) -> str:
    """Return highest priority from deterministic ordering."""
    order = {"high": 3, "medium": 2, "low": 1}
    if not priorities:
        return "none"
    return sorted(priorities, key=lambda item: (-order.get(item, 0), item))[0]


def render_config_change_candidate_markdown(payload: dict[str, object]) -> str:
    """Render config change candidates as markdown."""
    summary = object_value(payload.get("summary", {}))
    lines = [
        "# Config Change Candidate",
        "",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Status: `{summary.get('status', '')}`",
        f"- Candidate count: `{summary.get('candidate_count', 0)}`",
        f"- Highest priority: `{summary.get('highest_priority', 'none')}`",
        "",
        "## Changes",
        "",
    ]
    changes = list_of_objects(payload.get("changes", []))
    if not changes:
        lines.append("No config changes are recommended for the next run.")
    else:
        lines.extend(
            [
                "| Config Path | Operation | Current | Proposed | Priority |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for change in changes:
            lines.append(
                "| "
                f"{change.get('config_path', '')} | "
                f"{change.get('operation', '')} | "
                f"{json.dumps(change.get('current_value', ''), sort_keys=True)} | "
                f"{json.dumps(change.get('proposed_value', ''), sort_keys=True)} | "
                f"{change.get('priority', '')} |"
            )
    lines.extend(
        [
            "",
            "This artifact is advisory only and does not write config, execute agents, run backtests, route candidates, apply patches, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_config_change_candidate_file(
    *,
    payload_path: Path,
    repo_root: Path,
) -> tuple[str, ...]:
    """Validate a saved config change candidate report."""
    schema_path = repo_root / SCHEMA_PATH
    return tuple(validate_json_file(payload_path=payload_path, schema_path=schema_path))


def validate_config_change_candidate_payload(
    payload: dict[str, object],
    *,
    run_dir: Path,
    repo_root: Path,
    experiments_dir: Path | None = None,
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an in-memory config change candidate payload."""
    repo_root = repo_root.resolve()
    run_dir = run_dir.resolve()
    normalized = dict(payload)
    normalized.pop("from_artifact", None)
    schema = load_schema(repo_root / SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=normalized,
            schema=schema,
            schema_dir=(repo_root / SCHEMA_PATH).parent,
        )
    )
    errors.extend(
        validate_config_change_candidate_consistency(
            normalized,
            run_dir=run_dir,
            repo_root=repo_root,
        )
    )
    if require_current_evidence:
        expected = build_config_change_candidate(
            run_dir=run_dir,
            repo_root=repo_root,
            experiments_dir=experiments_dir,
        )
        if normalized != expected:
            errors.append("config_change_candidate current evidence mismatch")
    return tuple(errors)


def validate_config_change_candidate_consistency(
    payload: dict[str, object],
    *,
    run_dir: Path,
    repo_root: Path,
) -> tuple[str, ...]:
    """Return stable internal consistency errors for config candidates."""
    errors: list[str] = []
    changes = list_of_objects(payload.get("changes", []))
    summary = object_value(payload.get("summary", {}))
    operator_review = object_value(payload.get("operator_review", {}))
    if str(payload.get("run_id", "")) != run_dir.name:
        errors.append("config_change_candidate run_id mismatch")
    if str(payload.get("run_dir", "")) != relative_path(run_dir, repo_root):
        errors.append("config_change_candidate run_dir mismatch")
    if summary != summary_payload(changes=changes):
        errors.append("config_change_candidate summary mismatch")
    expected_operator_review = {
        "required": bool(changes),
        "status": "pending_review" if changes else "no_candidate_changes",
        "instruction": (
            "Review candidates before manually editing config; this artifact "
            "does not modify repository files."
        ),
    }
    if operator_review != expected_operator_review:
        errors.append("config_change_candidate operator_review mismatch")
    seen_ids: set[str] = set()
    for change in changes:
        candidate_id = str(change.get("candidate_id", ""))
        if not candidate_id:
            errors.append("config_change_candidate empty candidate_id")
        elif candidate_id in seen_ids:
            errors.append("config_change_candidate duplicate candidate_id")
        seen_ids.add(candidate_id)
        if bool(change.get("applied", True)):
            errors.append("config_change_candidate applied flag must be false")
        if not bool(change.get("requires_operator_review", False)):
            errors.append("config_change_candidate requires_operator_review false")
    return tuple(errors)


def load_json_object(path: Path) -> dict[str, object]:
    """Load a JSON object, returning an empty object if unavailable."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def object_value(value: object) -> dict[str, object]:
    """Return a JSON object value or an empty object."""
    return value if isinstance(value, dict) else {}


def list_of_objects(value: object) -> list[dict[str, object]]:
    """Return JSON object rows from a list-like value."""
    if not isinstance(value, list | tuple):
        return []
    return [row for row in value if isinstance(row, dict)]


def string_list(value: object) -> list[str]:
    """Return a deterministic string list."""
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list | tuple):
        return [str(item) for item in value if str(item)]
    return []


def config_value_at_path(payload: dict[str, object], dotted_path: str) -> object:
    """Return a nested config value, using None for missing paths."""
    value: object = payload
    for part in dotted_path.split("."):
        if not part:
            return None
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def file_record(path: Path, repo_root: Path) -> dict[str, object]:
    """Return deterministic metadata for one source file."""
    if not path.exists():
        return {
            "exists": False,
            "path": relative_path(path, repo_root),
            "bytes": 0,
            "sha256": "",
        }
    data = path.read_bytes()
    return {
        "exists": True,
        "path": relative_path(path, repo_root),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> None:
    """CLI entrypoint for config change candidate reports."""
    parser = argparse.ArgumentParser(description="Write a config change candidate report.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--experiments-dir", type=Path)
    args = parser.parse_args()
    _, _, payload = write_config_change_candidate(
        run_dir=args.run_dir,
        repo_root=args.repo_root,
        experiments_dir=args.experiments_dir,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
