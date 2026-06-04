"""Read-only recommendation for the next deterministic modifier profile."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.config import (
    ProjectConfig,
    adapter_supported_directions,
    load_project_config,
)
from orchestrator.schema_validation import (
    load_schema,
    validate_json_file,
    validate_json_payload,
)


MODIFIER_PROFILE_RECOMMENDATION_SCHEMA_VERSION = "modifier_profile_recommendation_v1"
SCHEMA_PATH = Path("schemas/modifier_profile_recommendation.schema.json")


def write_modifier_profile_recommendation(
    *,
    run_dir: Path,
    repo_root: Path,
    config_path: Path = Path("config/default.json"),
    config: ProjectConfig | None = None,
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown modifier profile recommendation artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    config_path = resolve_path(config_path, repo_root)
    payload = build_modifier_profile_recommendation(
        run_dir=run_dir,
        repo_root=repo_root,
        config_path=config_path,
        config=config,
    )
    errors = validate_modifier_profile_recommendation_payload(
        payload,
        run_dir=run_dir,
        repo_root=repo_root,
        config_path=config_path,
        config=config,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "modifier profile recommendation failed schema validation: "
            + "; ".join(errors)
        )
    json_path = run_dir / "modifier_profile_recommendation.json"
    md_path = run_dir / "modifier_profile_recommendation.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(
        render_modifier_profile_recommendation_markdown(payload),
        encoding="utf-8",
    )
    errors = validate_modifier_profile_recommendation_file(
        payload_path=json_path,
        repo_root=repo_root,
        config_path=config_path,
        config=config,
    )
    if errors:
        raise ValueError(
            "modifier profile recommendation failed schema validation: "
            + "; ".join(errors)
        )
    return json_path, md_path, payload


def build_modifier_profile_recommendation(
    *,
    run_dir: Path,
    repo_root: Path,
    config_path: Path = Path("config/default.json"),
    config: ProjectConfig | None = None,
) -> dict[str, object]:
    """Return a deterministic, advisory-only next-profile recommendation."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    config_path = resolve_path(config_path, repo_root)
    active_config = config or load_project_config(repo_root=repo_root, config_path=config_path)
    quality_path = run_dir / "candidate_quality_trace.json"
    brief_path = run_dir / "research_brief.json"
    quality_trace = load_json_object(quality_path)
    research_brief = load_json_object(brief_path)
    search_space = dict_value(active_config.strategy_search_space)
    focus = dict_value(research_brief.get("recommended_experiment_focus", {}))
    quality_summary = dict_value(quality_trace.get("summary", {}))
    selected_directions = string_list(quality_summary.get("selected_directions", []))
    avoid_directions = unique_strings(
        string_list(focus.get("avoid_directions", [])) or selected_directions
    )
    suggested_directions = unique_strings(
        string_list(focus.get("suggested_directions", []))
        or alternative_directions(
            avoid_directions=avoid_directions,
            search_space=search_space,
        )
    )
    profiles = available_profiles(config=active_config, search_space=search_space)
    direction_rows = direction_rows_by_tag(search_space)
    recommendations = recommendation_rows(
        suggested_directions=suggested_directions,
        avoid_directions=avoid_directions,
        direction_rows=direction_rows,
        profiles=profiles,
    )
    selected = recommendations[0] if recommendations else {}
    status = recommendation_status(
        quality_trace=quality_trace,
        research_brief=research_brief,
        recommendations=recommendations,
    )
    return {
        "schema_version": MODIFIER_PROFILE_RECOMMENDATION_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": relative_path(run_dir, repo_root),
        "sources": {
            "candidate_quality_trace": file_record(quality_path, repo_root),
            "research_brief": file_record(brief_path, repo_root),
            "config": file_record(config_path, repo_root),
        },
        "summary": {
            "status": status,
            "primary_focus": str(focus.get("primary_focus", "")),
            "top_failure_code": str(quality_summary.get("top_failure_code", "")),
            "selected_directions": selected_directions,
            "avoid_directions": avoid_directions,
            "suggested_directions": suggested_directions,
            "available_profile_count": len(profiles),
            "recommendation_count": len(recommendations),
            "recommended_direction_tag": str(selected.get("direction_tag", "")),
            "recommended_profile_name": str(selected.get("profile_name", "")),
            "recommended_adapter_name": str(selected.get("adapter_name", "")),
            "recommendation_reason_code": recommendation_reason_code(
                status=status,
                focus=focus,
                selected=selected,
            ),
        },
        "available_profiles": profiles,
        "recommendations": recommendations,
        "operator_notes": operator_notes(
            status=status,
            selected=selected,
            avoid_directions=avoid_directions,
            suggested_directions=suggested_directions,
        ),
        "policy": {
            "advisory_only": True,
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_write_config": True,
            "does_not_route_agents": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
        },
    }


def available_profiles(
    *,
    config: ProjectConfig,
    search_space: dict[str, object],
) -> list[dict[str, object]]:
    """Return normalized profiles available for operator review."""
    if config.agent_profiles:
        rows = [
            {
                "profile_name": str(profile.get("name", "")),
                "role": str(profile.get("role", "")),
                "adapter_name": str(profile.get("adapter", "")),
                "agent_role": str(profile.get("agent_role", "strategy_modifier")),
                "enabled": bool(profile.get("enabled", True)),
                "supported_directions": string_list(
                    profile.get("supported_directions", [])
                ),
            }
            for profile in config.agent_profiles
        ]
    else:
        modifiers = [("primary", config.strategy_modifier)]
        modifiers.extend(
            (f"fallback_{index:02d}", modifier_name)
            for index, modifier_name in enumerate(config.memory_fallback_modifiers, start=1)
        )
        rows = [
            {
                "profile_name": profile_name,
                "role": "primary" if profile_name == "primary" else "fallback",
                "adapter_name": modifier_name,
                "agent_role": "strategy_modifier",
                "enabled": True,
                "supported_directions": list(
                    adapter_supported_directions(
                        adapter_name=modifier_name,
                        strategy_search_space=search_space,
                    )
                ),
            }
            for profile_name, modifier_name in modifiers
        ]
    rows.sort(key=profile_sort_key)
    return rows


def recommendation_rows(
    *,
    suggested_directions: list[str],
    avoid_directions: list[str],
    direction_rows: dict[str, dict[str, object]],
    profiles: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return ranked profile recommendations for suggested directions."""
    rows: list[dict[str, object]] = []
    ranked_directions = unique_strings(
        suggested_directions
        + [
            direction
            for direction in direction_rows
            if direction not in suggested_directions and direction not in avoid_directions
        ]
    )
    for direction_index, direction in enumerate(ranked_directions, start=1):
        direction_payload = direction_rows.get(direction, {})
        for profile in profiles:
            if not bool(profile.get("enabled", False)):
                continue
            supported = string_list(profile.get("supported_directions", []))
            if "*" not in supported and direction not in supported:
                continue
            rows.append(
                {
                    "rank": len(rows) + 1,
                    "direction_rank": direction_index,
                    "direction_tag": direction,
                    "profile_name": str(profile.get("profile_name", "")),
                    "adapter_name": str(profile.get("adapter_name", "")),
                    "role": str(profile.get("role", "")),
                    "modifier_hint": str(direction_payload.get("modifier_hint", "")),
                    "description": str(direction_payload.get("description", "")),
                    "reason_codes": recommendation_reason_codes(
                        direction=direction,
                        suggested_directions=suggested_directions,
                        avoid_directions=avoid_directions,
                        profile=profile,
                        direction_payload=direction_payload,
                    ),
                }
            )
    return rows


def profile_sort_key(row: dict[str, object]) -> tuple[object, ...]:
    """Sort primary profile before fallback profiles."""
    role = str(row.get("role", ""))
    role_rank = 0 if role == "primary" else 1 if role == "fallback" else 2
    return (role_rank, str(row.get("profile_name", "")))


def recommendation_reason_codes(
    *,
    direction: str,
    suggested_directions: list[str],
    avoid_directions: list[str],
    profile: dict[str, object],
    direction_payload: dict[str, object],
) -> list[str]:
    """Return stable reason codes for one recommendation row."""
    codes = [f"profile:{profile.get('profile_name', '')}"]
    if direction in suggested_directions:
        codes.append("direction_suggested_by_research_focus")
    if direction in avoid_directions:
        codes.append("direction_in_avoid_list")
    if str(profile.get("adapter_name", "")) == str(
        direction_payload.get("modifier_hint", "")
    ):
        codes.append("adapter_matches_modifier_hint")
    return codes


def recommendation_status(
    *,
    quality_trace: dict[str, object],
    research_brief: dict[str, object],
    recommendations: list[dict[str, object]],
) -> str:
    """Return compact recommendation status."""
    if not quality_trace:
        return "missing_quality_trace"
    if not research_brief:
        return "missing_research_brief"
    if not recommendations:
        return "no_available_profile"
    return "ready_for_operator_review"


def recommendation_reason_code(
    *,
    status: str,
    focus: dict[str, object],
    selected: dict[str, object],
) -> str:
    """Return one summary reason code."""
    if status != "ready_for_operator_review":
        return status
    primary_focus = str(focus.get("primary_focus", ""))
    direction = str(selected.get("direction_tag", ""))
    if primary_focus == "switch_modifier_direction":
        return f"switch_modifier_direction:{direction}"
    return f"{primary_focus or 'review_next_profile'}:{direction}"


def operator_notes(
    *,
    status: str,
    selected: dict[str, object],
    avoid_directions: list[str],
    suggested_directions: list[str],
) -> list[str]:
    """Return short human-facing next-step notes."""
    if status == "no_available_profile":
        return [
            (
                "No enabled profile covers the suggested direction; review "
                "config_change_candidate.json for a guarded modifier-profile "
                "candidate."
            )
        ]
    if status != "ready_for_operator_review":
        return ["Inspect missing source artifacts before changing modifier settings."]
    return [
        (
            "Review the recommended profile before editing config or starting a new "
            "iteration."
        ),
        (
            f"Recommended `{selected.get('profile_name', '')}` for "
            f"`{selected.get('direction_tag', '')}`; avoid "
            f"`{', '.join(avoid_directions) or 'none'}`."
        ),
        (
            f"Suggested direction order was "
            f"`{', '.join(suggested_directions) or 'none'}`."
        ),
    ]


def render_modifier_profile_recommendation_markdown(
    payload: dict[str, object],
) -> str:
    """Render modifier profile recommendation payload as markdown."""
    summary = dict_value(payload.get("summary", {}))
    lines = [
        "# Modifier Profile Recommendation",
        "",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Status: `{summary.get('status', '')}`",
        f"- Primary focus: `{summary.get('primary_focus', '')}`",
        f"- Top failure: `{summary.get('top_failure_code', '') or 'none'}`",
        f"- Recommended direction: `{summary.get('recommended_direction_tag', '') or 'none'}`",
        f"- Recommended profile: `{summary.get('recommended_profile_name', '') or 'none'}`",
        f"- Recommended adapter: `{summary.get('recommended_adapter_name', '') or 'none'}`",
        "",
        "## Recommendations",
        "",
        "| Rank | Direction | Profile | Adapter | Reason |",
        "| ---: | --- | --- | --- | --- |",
    ]
    recommendations = list_of_dicts(payload.get("recommendations", []))
    if recommendations:
        for row in recommendations:
            lines.append(
                "| "
                f"{row.get('rank', 0)} | "
                f"`{row.get('direction_tag', '')}` | "
                f"`{row.get('profile_name', '')}` | "
                f"`{row.get('adapter_name', '')}` | "
                f"{', '.join(string_list(row.get('reason_codes', []))) or 'none'} |"
            )
    else:
        lines.append("| 0 | none | none | none | no available profile |")
    lines.extend(["", "## Operator Notes", ""])
    lines.extend(f"- {note}" for note in string_list(payload.get("operator_notes", [])))
    lines.extend(
        [
            "",
            "This artifact is advisory only and cannot route agents, write config, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_modifier_profile_recommendation_file(
    *,
    payload_path: Path,
    repo_root: Path,
    config_path: Path = Path("config/default.json"),
    config: ProjectConfig | None = None,
) -> tuple[str, ...]:
    """Validate a saved modifier profile recommendation artifact."""
    schema_errors = tuple(
        validate_json_file(
            payload_path=payload_path,
            schema_path=repo_root / SCHEMA_PATH,
        )
    )
    if schema_errors:
        return schema_errors
    payload = load_json_object(payload_path)
    return schema_errors + validate_modifier_profile_recommendation_payload(
        payload,
        run_dir=payload_path.parent,
        repo_root=repo_root,
        config_path=config_path,
        config=config,
        require_current_evidence=True,
    )


def validate_modifier_profile_recommendation_payload(
    payload: dict[str, object],
    *,
    run_dir: Path | None = None,
    repo_root: Path,
    config_path: Path = Path("config/default.json"),
    config: ProjectConfig | None = None,
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an in-memory modifier profile recommendation artifact."""
    repo_root = repo_root.resolve()
    comparable_payload = strip_terminal_metadata(payload)
    schema = load_schema(repo_root / SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=comparable_payload,
            schema=schema,
            schema_dir=(repo_root / SCHEMA_PATH).parent,
        )
    )
    if require_current_evidence:
        resolved_run_dir = recommendation_run_dir(
            payload=comparable_payload,
            run_dir=run_dir,
            repo_root=repo_root,
        )
        if resolved_run_dir is None:
            errors.append("modifier_profile_recommendation run_dir required")
        else:
            errors.extend(
                validate_modifier_profile_recommendation_consistency(
                    payload=comparable_payload,
                    run_dir=resolved_run_dir,
                    repo_root=repo_root,
                    config_path=config_path,
                    config=config,
                )
            )
    return tuple(errors)


def validate_modifier_profile_recommendation_consistency(
    *,
    payload: dict[str, object],
    run_dir: Path,
    repo_root: Path,
    config_path: Path = Path("config/default.json"),
    config: ProjectConfig | None = None,
) -> tuple[str, ...]:
    """Return consistency errors after recomputing the recommendation."""
    expected = build_modifier_profile_recommendation(
        run_dir=run_dir,
        repo_root=repo_root,
        config_path=config_path,
        config=config,
    )
    errors: list[str] = []
    for key in (
        "schema_version",
        "run_id",
        "run_dir",
        "sources",
        "summary",
        "available_profiles",
        "recommendations",
        "operator_notes",
        "policy",
    ):
        if payload.get(key) != expected.get(key):
            errors.append(f"modifier_profile_recommendation recompute mismatch: {key}")
    return tuple(errors)


def recommendation_run_dir(
    *,
    payload: dict[str, object],
    run_dir: Path | None,
    repo_root: Path,
) -> Path | None:
    """Return the run directory used for current-evidence validation."""
    if run_dir is not None:
        return resolve_path(run_dir, repo_root)
    raw_path = str(payload.get("run_dir", ""))
    return resolve_path(Path(raw_path), repo_root) if raw_path else None


def direction_rows_by_tag(search_space: dict[str, object]) -> dict[str, dict[str, object]]:
    """Return configured direction rows keyed by direction tag."""
    directions = list_of_dicts(search_space.get("directions", []))
    return {str(row.get("direction_tag", "")): row for row in directions}


def alternative_directions(
    *,
    avoid_directions: list[str],
    search_space: dict[str, object],
) -> list[str]:
    """Return direction order excluding avoided directions."""
    order = string_list(search_space.get("direction_order", []))
    if not order:
        order = [
            str(row.get("direction_tag", ""))
            for row in list_of_dicts(search_space.get("directions", []))
        ]
    return [direction for direction in order if direction and direction not in avoid_directions]


def load_json_object(path: Path) -> dict[str, object]:
    """Load a JSON object or return an empty mapping."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def dict_value(value: object) -> dict[str, object]:
    """Return a dict value or an empty mapping."""
    return value if isinstance(value, dict) else {}


def list_of_dicts(value: object) -> list[dict[str, object]]:
    """Return dict rows from a list-like value."""
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


def unique_strings(values: list[str]) -> list[str]:
    """Return values in stable first-seen order."""
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            rows.append(value)
    return rows


def strip_terminal_metadata(payload: dict[str, object]) -> dict[str, object]:
    """Return payload without terminal-only annotation fields."""
    stripped = dict(payload)
    stripped.pop("from_artifact", None)
    return stripped


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


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root."""
    return path if path.is_absolute() else repo_root / path


def main() -> None:
    """CLI entrypoint for modifier profile recommendations."""
    parser = argparse.ArgumentParser(
        description="Write a read-only modifier profile recommendation.",
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--config", type=Path, default=Path("config/default.json"))
    args = parser.parse_args()
    _, _, payload = write_modifier_profile_recommendation(
        run_dir=args.run_dir,
        repo_root=Path(".").resolve(),
        config_path=args.config,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
