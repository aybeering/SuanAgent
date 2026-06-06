"""Build a deterministic health report for planned agent execution slots."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from orchestrator.schema_validation import validate_json_file


AGENT_SLOT_HEALTH_SCHEMA_VERSION = "agent_slot_health_v1"
SCHEMA_PATH = Path("schemas/agent_slot_health.schema.json")


def build_agent_slot_health(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Return a run-level health report for planned agent slots."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    preflight = load_json_object(run_dir / "agent_activation_preflight.json")
    preflight_profiles = profiles_by_name(preflight)
    slots: list[dict[str, Any]] = []
    for round_dir in round_dirs(run_dir):
        slots.extend(
            round_slot_rows(
                run_dir=run_dir,
                round_dir=round_dir,
                repo_root=repo_root,
                preflight_profiles=preflight_profiles,
            )
        )
    status_counts = Counter(str(slot["health_status"]) for slot in slots)
    return {
        "schema_version": AGENT_SLOT_HEALTH_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "source_artifacts": {
            "agent_activation_preflight": str(
                run_dir / "agent_activation_preflight.json"
            ),
            "rounds": [
                str(path / "agent_execution_plan.json") for path in round_dirs(run_dir)
            ],
        },
        "totals": {
            "slot_count": len(slots),
            "healthy_count": status_counts.get("healthy", 0),
            "needs_replay_count": status_counts.get("needs_replay", 0),
            "blocked_count": len(slots)
            - status_counts.get("healthy", 0)
            - status_counts.get("needs_replay", 0),
            "workspace_required_count": sum(
                1 for slot in slots if bool(slot["workspace_required"])
            ),
            "execution_audit_required_count": sum(
                1 for slot in slots if bool(slot["execution_audit_required"])
            ),
            "replay_present_count": sum(
                1 for slot in slots if bool(slot["replay_present"])
            ),
        },
        "status_counts": dict(sorted(status_counts.items())),
        "slots": slots,
        "policy": {
            "inspection_only": True,
            "does_not_execute_agents": True,
            "does_not_select_candidate": True,
            "does_not_change_acceptance": True,
        },
    }


def write_agent_slot_health(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    """Write JSON and markdown agent-slot health reports for one run."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_agent_slot_health(run_dir=run_dir, repo_root=repo_root)
    destination = output_path or run_dir / "agent_slot_health.json"
    write_json(destination, payload)
    markdown_destination = markdown_path or run_dir / "agent_slot_health.md"
    markdown_destination.write_text(
        agent_slot_health_markdown(payload),
        encoding="utf-8",
    )
    return payload


def validate_agent_slot_health_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
    schema_path: Path | None = None,
    require_current_evidence: bool = True,
) -> tuple[str, ...]:
    """Validate a saved agent-slot health report against schema and evidence."""
    repo_root = repo_root.resolve()
    schema_errors = tuple(
        validate_json_file(
            payload_path=payload_path,
            schema_path=schema_path or repo_root / SCHEMA_PATH,
        )
    )
    if schema_errors or not require_current_evidence:
        return schema_errors
    payload = load_json_object(payload_path)
    run_dir_value = str(payload.get("run_dir", ""))
    if not run_dir_value:
        return schema_errors + ("agent_slot_health run_dir required",)
    expected = build_agent_slot_health(
        run_dir=resolve_path(Path(run_dir_value), repo_root),
        repo_root=repo_root,
    )
    if payload != expected:
        return schema_errors + ("agent_slot_health current evidence mismatch",)
    return schema_errors


def round_slot_rows(
    *,
    run_dir: Path,
    round_dir: Path,
    repo_root: Path,
    preflight_profiles: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return health rows for every planned attempt in one round."""
    plan = load_json_object(round_dir / "agent_execution_plan.json")
    manifest = load_json_object(round_dir / "agent_attempts_manifest.json")
    replay = load_json_object(round_dir / "round_replay.json")
    manifest_attempts = attempts_by_id(manifest.get("attempts", []))
    replay_attempts = attempts_by_id(replay.get("attempts", []))
    rows: list[dict[str, Any]] = []
    for planned in object_rows(plan.get("attempts", [])):
        attempt_id = str(planned.get("attempt_id", ""))
        manifest_row = manifest_attempts.get(attempt_id, {})
        replay_row = replay_attempts.get(attempt_id, {})
        rows.append(
            slot_health_row(
                run_dir=run_dir,
                round_dir=round_dir,
                repo_root=repo_root,
                planned=planned,
                manifest_row=manifest_row,
                replay_row=replay_row,
                preflight_profile=preflight_profiles.get(
                    str(planned.get("profile_name", "")),
                    {},
                ),
            )
        )
    return rows


def slot_health_row(
    *,
    run_dir: Path,
    round_dir: Path,
    repo_root: Path,
    planned: dict[str, Any],
    manifest_row: dict[str, Any],
    replay_row: dict[str, Any],
    preflight_profile: dict[str, Any],
) -> dict[str, Any]:
    """Return one planned slot health row."""
    del run_dir
    attempt_id = str(planned.get("attempt_id", ""))
    runner = object_value(planned.get("runner", {}))
    workspace = object_value(planned.get("workspace", {}))
    output_contract = object_value(planned.get("output_contract", {}))
    planned_artifacts = object_value(planned.get("planned_artifacts", {}))
    attempt_dir = resolve_path(
        Path(str(planned_artifacts.get("attempt_dir", ""))),
        repo_root,
    )
    workspace_manifest_path = first_existing_path(
        repo_root,
        [
            str(planned_artifacts.get("workspace_manifest", "")),
            str(attempt_dir / "workspace_manifest.json"),
            str(round_dir / "workspace_manifest.json"),
        ],
    )
    agent_execution_path = first_existing_path(
        repo_root,
        [
            str(planned_artifacts.get("agent_execution", "")),
            str(attempt_dir / "agent_execution.json"),
            str(round_dir / "agent_execution.json"),
        ],
    )
    agent_execution = load_json_object(agent_execution_path) if agent_execution_path else {}
    workspace_required = bool(workspace.get("workspace_required", False))
    execution_enabled = bool(runner.get("execution_enabled", False))
    execution_audit_required = execution_enabled and (
        bool(output_contract.get("file_contract_required", False))
        or bool(output_contract.get("stdout_patch_allowed", False))
    )
    attempt_saved = bool(manifest_row)
    replay_present = bool(replay_row)
    plan_matches_manifest = (
        bool(replay_row.get("plan_matches_manifest", False))
        if replay_present
        else planned_matches_manifest(planned=planned, manifest_row=manifest_row)
    )
    replay_ok = bool(replay_row.get("ok", False)) if replay_present else False
    activation_status = str(preflight_profile.get("activation_status", "missing"))
    issues = slot_issues(
        activation_status=activation_status,
        execution_enabled=execution_enabled,
        attempt_saved=attempt_saved,
        plan_matches_manifest=plan_matches_manifest,
        workspace_required=workspace_required,
        workspace_manifest_present=bool(workspace_manifest_path),
        execution_audit_required=execution_audit_required,
        agent_execution_present=bool(agent_execution_path),
        replay_present=replay_present,
        replay_ok=replay_ok,
    )
    return {
        "slot_id": f"{round_dir.name}:{attempt_id}",
        "run_id": round_dir.parent.name,
        "round_id": round_dir.name,
        "attempt_id": attempt_id,
        "attempt_index": int(planned.get("attempt_index", 0)),
        "queue_role": str(planned.get("queue_role", "")),
        "profile_name": str(planned.get("profile_name", "")),
        "agent_role": str(planned.get("agent_role", "")),
        "adapter_name": str(planned.get("adapter_name", "")),
        "runner_name": str(runner.get("runner_name", "")),
        "execution_enabled": execution_enabled,
        "activation_status": activation_status,
        "health_status": health_status(issues),
        "health_ok": not issues,
        "issues": issues,
        "attempt_saved": attempt_saved,
        "selected": bool(manifest_row.get("selected", False)),
        "candidate_status": str(manifest_row.get("status", "")),
        "candidate_failure_code": str(manifest_row.get("failure_code", "")),
        "workspace_required": workspace_required,
        "workspace_manifest_present": bool(workspace_manifest_path),
        "workspace_manifest_path": str(workspace_manifest_path) if workspace_manifest_path else "",
        "execution_audit_required": execution_audit_required,
        "agent_execution_present": bool(agent_execution_path),
        "agent_execution_path": str(agent_execution_path) if agent_execution_path else "",
        "agent_execution_status": str(agent_execution.get("status", "")),
        "replay_present": replay_present,
        "replay_ok": replay_ok,
        "plan_matches_manifest": plan_matches_manifest,
        "replay_path": str(replay_row.get("replay_path", "")),
    }


def slot_issues(
    *,
    activation_status: str,
    execution_enabled: bool,
    attempt_saved: bool,
    plan_matches_manifest: bool,
    workspace_required: bool,
    workspace_manifest_present: bool,
    execution_audit_required: bool,
    agent_execution_present: bool,
    replay_present: bool,
    replay_ok: bool,
) -> list[str]:
    """Return stable issue codes for one slot."""
    issues: list[str] = []
    if execution_enabled and activation_status not in {"ready", "missing"}:
        issues.append("activation_blocked")
    if not attempt_saved:
        issues.append("attempt_missing")
    if attempt_saved and not plan_matches_manifest:
        issues.append("plan_manifest_mismatch")
    if workspace_required and not workspace_manifest_present:
        issues.append("workspace_audit_missing")
    if execution_audit_required and not agent_execution_present:
        issues.append("execution_audit_missing")
    if replay_present and not replay_ok:
        issues.append("replay_failed")
    if not replay_present:
        issues.append("needs_replay")
    return issues


def health_status(issues: list[str]) -> str:
    """Return the primary health status from issue codes."""
    if not issues:
        return "healthy"
    order = (
        "activation_blocked",
        "attempt_missing",
        "plan_manifest_mismatch",
        "workspace_audit_missing",
        "execution_audit_missing",
        "replay_failed",
        "needs_replay",
    )
    for code in order:
        if code in issues:
            return code
    return issues[0]


def planned_matches_manifest(
    *,
    planned: dict[str, Any],
    manifest_row: dict[str, Any],
) -> bool:
    """Return whether saved manifest metadata matches the pre-execution plan."""
    if not manifest_row:
        return False
    keys = ("profile_name", "adapter_name", "agent_role")
    for key in keys:
        if str(planned.get(key, "")) != str(manifest_row.get(key, "")):
            return False
    runner = object_value(planned.get("runner", {}))
    return str(runner.get("runner_name", "")) == str(manifest_row.get("runner_name", ""))


def profiles_by_name(preflight: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return preflight profile rows keyed by profile name."""
    return {
        str(profile.get("profile_name", "")): profile
        for profile in object_rows(preflight.get("profiles", []))
        if str(profile.get("profile_name", ""))
    }


def attempts_by_id(value: object) -> dict[str, dict[str, Any]]:
    """Return attempt rows keyed by attempt id."""
    return {
        str(row.get("attempt_id", "")): row
        for row in object_rows(value)
        if str(row.get("attempt_id", ""))
    }


def round_dirs(run_dir: Path) -> list[Path]:
    """Return sorted round directories for one iteration run."""
    return [path for path in sorted(run_dir.glob("round_*")) if path.is_dir()]


def object_rows(value: object) -> list[dict[str, Any]]:
    """Return object rows from a JSON array value."""
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def object_value(value: object) -> dict[str, Any]:
    """Return a JSON object or an empty object."""
    return value if isinstance(value, dict) else {}


def first_existing_path(repo_root: Path, values: list[str]) -> Path | None:
    """Return the first path from values that exists."""
    for value in values:
        if not value:
            continue
        path = resolve_path(Path(value), repo_root)
        if path.exists():
            return path
    return None


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root when needed."""
    return path if path.is_absolute() else repo_root / path


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object, returning empty dict for missing or invalid content."""
    if not path or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: object) -> None:
    """Write deterministic JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def agent_slot_health_markdown(payload: dict[str, Any]) -> str:
    """Return a compact markdown slot health table."""
    lines = [
        "# Agent Slot Health",
        "",
        f"- Schema: `{payload['schema_version']}`",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Slots: `{payload.get('totals', {}).get('slot_count', 0)}`",
        f"- Healthy: `{payload.get('totals', {}).get('healthy_count', 0)}`",
        "",
        "| Round | Attempt | Profile | Adapter | Runner | Status | Issues |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for slot in object_rows(payload.get("slots", [])):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(slot.get("round_id", "")),
                    str(slot.get("attempt_id", "")),
                    str(slot.get("profile_name", "")),
                    str(slot.get("adapter_name", "")),
                    str(slot.get("runner_name", "")),
                    str(slot.get("health_status", "")),
                    ", ".join(str(item) for item in slot.get("issues", []))
                    if isinstance(slot.get("issues", []), list)
                    else "",
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    """CLI entrypoint for agent slot health reports."""
    args = parse_args()
    payload = write_agent_slot_health(
        run_dir=args.run_dir,
        repo_root=args.repo_root,
        output_path=args.output,
        markdown_path=args.markdown,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if int(payload["totals"]["blocked_count"]) > 0:  # type: ignore[index]
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for agent slot health."""
    parser = argparse.ArgumentParser(
        description="Inspect planned agent slots across one iteration run.",
    )
    parser.add_argument("run_dir", type=Path, help="Path to experiments/<run_id>.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root used to resolve artifact paths.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write agent_slot_health.json.",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=None,
        help="Optional path to write agent_slot_health.md.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
