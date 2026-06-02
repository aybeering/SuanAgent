"""Read-only config change candidates for the next iteration run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.memory_scope_recommendation import build_memory_scope_recommendation
from orchestrator.schema_validation import validate_json_file


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
    json_path = run_dir / "config_change_candidate.json"
    md_path = run_dir / "config_change_candidate.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_config_change_candidate_markdown(payload), encoding="utf-8")
    errors = validate_config_change_candidate_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(
            "config change candidate failed schema validation: " + "; ".join(errors)
        )
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
    changes = memory_scope_changes(memory_scope=memory_scope)
    summary = summary_payload(changes=changes)
    return {
        "schema_version": CONFIG_CHANGE_CANDIDATE_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": relative_path(run_dir, repo_root),
        "sources": [
            {
                "artifact_name": "memory_scope_recommendation",
                "from_artifact": memory_scope_from_artifact,
                "file": file_record(memory_scope_path, repo_root),
            }
        ],
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
