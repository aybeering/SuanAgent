"""Deterministic readiness gate for future isolated agent slots."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from orchestrator.schema_validation import validate_json_file


AGENT_SLOT_READINESS_GATE_SCHEMA_VERSION = "agent_slot_readiness_gate_v1"
SCHEMA_PATH = Path("schemas/agent_slot_readiness_gate.schema.json")


def build_agent_slot_readiness_gate(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
    require_replay: bool = True,
) -> dict[str, Any]:
    """Return a deterministic readiness report for planned agent slots."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    preflight = load_json_object(run_dir / "agent_activation_preflight.json")
    profiles = profiles_by_name(preflight)
    slots: list[dict[str, Any]] = []
    for round_dir in round_dirs(run_dir):
        slots.extend(
            round_readiness_rows(
                run_dir=run_dir,
                round_dir=round_dir,
                repo_root=repo_root,
                profiles=profiles,
                require_replay=require_replay,
            )
        )
    status_counts = Counter(str(slot["readiness_status"]) for slot in slots)
    blocked_count = status_counts.get("blocked", 0)
    return {
        "schema_version": AGENT_SLOT_READINESS_GATE_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "ok": blocked_count == 0,
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
            "ready_count": status_counts.get("ready", 0),
            "blocked_count": blocked_count,
            "contract_only_count": status_counts.get("contract_only", 0),
            "external_slot_count": sum(
                1 for slot in slots if bool(slot["external_slot"])
            ),
            "replay_required_count": sum(
                1 for slot in slots if bool(slot["requirements"]["replay_required"])
            ),
        },
        "status_counts": dict(sorted(status_counts.items())),
        "slots": slots,
        "policy": {
            "readiness_gate_only": True,
            "does_not_execute_agents": True,
            "does_not_select_candidate": True,
            "does_not_change_acceptance": True,
            "requires_replay": require_replay,
            "deterministic_code_keeps_acceptance_authority": True,
        },
    }


def write_agent_slot_readiness_gate(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
    output_path: Path | None = None,
    markdown_path: Path | None = None,
    require_replay: bool = True,
) -> dict[str, Any]:
    """Write JSON and markdown readiness-gate artifacts for one run."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_agent_slot_readiness_gate(
        run_dir=run_dir,
        repo_root=repo_root,
        require_replay=require_replay,
    )
    destination = output_path or run_dir / "agent_slot_readiness_gate.json"
    write_json(destination, payload)
    markdown_destination = markdown_path or run_dir / "agent_slot_readiness_gate.md"
    markdown_destination.write_text(
        agent_slot_readiness_gate_markdown(payload),
        encoding="utf-8",
    )
    return payload


def validate_agent_slot_readiness_gate_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
    schema_path: Path | None = None,
    require_current_evidence: bool = True,
) -> tuple[str, ...]:
    """Validate a saved readiness gate against schema and current evidence."""
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
        return schema_errors + ("agent_slot_readiness_gate run_dir required",)
    policy = object_value(payload.get("policy", {}))
    expected = build_agent_slot_readiness_gate(
        run_dir=resolve_path(Path(run_dir_value), repo_root),
        repo_root=repo_root,
        require_replay=bool(policy.get("requires_replay", True)),
    )
    if payload != expected:
        return schema_errors + (
            "agent_slot_readiness_gate current evidence mismatch",
        )
    return schema_errors


def round_readiness_rows(
    *,
    run_dir: Path,
    round_dir: Path,
    repo_root: Path,
    profiles: dict[str, dict[str, Any]],
    require_replay: bool,
) -> list[dict[str, Any]]:
    """Return readiness rows for every planned attempt in one round."""
    plan = load_json_object(round_dir / "agent_execution_plan.json")
    manifest = load_json_object(round_dir / "agent_attempts_manifest.json")
    replay = load_json_object(round_dir / "round_replay.json")
    manifest_attempts = rows_by_id(manifest.get("attempts", []))
    replay_attempts = rows_by_id(replay.get("attempts", []))
    rows: list[dict[str, Any]] = []
    for planned in object_rows(plan.get("attempts", [])):
        profile_name = str(planned.get("profile_name", ""))
        attempt_id = str(planned.get("attempt_id", ""))
        rows.append(
            slot_readiness_row(
                run_dir=run_dir,
                round_dir=round_dir,
                repo_root=repo_root,
                planned=planned,
                manifest_row=manifest_attempts.get(attempt_id, {}),
                replay_row=replay_attempts.get(attempt_id, {}),
                preflight_profile=profiles.get(profile_name, {}),
                require_replay=require_replay,
            )
        )
    return rows


def slot_readiness_row(
    *,
    run_dir: Path,
    round_dir: Path,
    repo_root: Path,
    planned: dict[str, Any],
    manifest_row: dict[str, Any],
    replay_row: dict[str, Any],
    preflight_profile: dict[str, Any],
    require_replay: bool,
) -> dict[str, Any]:
    """Return one planned slot readiness row."""
    del run_dir
    attempt_id = str(planned.get("attempt_id", ""))
    runner = object_value(planned.get("runner", {}))
    workspace = object_value(planned.get("workspace", {}))
    input_contract = object_value(planned.get("input_contract", {}))
    output_contract = object_value(planned.get("output_contract", {}))
    planned_artifacts = object_value(planned.get("planned_artifacts", {}))

    round_input_path = existing_path(
        repo_root,
        str(input_contract.get("round_agent_input", "")),
    )
    attempt_input_path = existing_path(
        repo_root,
        str(input_contract.get("attempt_agent_input", "")),
    )
    input_bundle_path = existing_path(
        repo_root,
        str(input_contract.get("input_bundle_dir", "")),
    )
    workspace_manifest_path = first_existing_path(
        repo_root,
        [
            str(planned_artifacts.get("workspace_manifest", "")),
            str(round_dir / "workspace_manifests" / f"{attempt_id}.json"),
            str(round_dir / "agent_attempts" / attempt_id / "workspace_manifest.json"),
            str(round_dir / "workspace_manifest.json"),
        ],
    )
    agent_execution_path = first_existing_path(
        repo_root,
        [
            str(planned_artifacts.get("agent_execution", "")),
            str(round_dir / "agent_executions" / f"{attempt_id}.json"),
            str(round_dir / "agent_attempts" / attempt_id / "agent_execution.json"),
            str(round_dir / "agent_execution.json"),
        ],
    )
    attempt_saved = bool(manifest_row)
    plan_matches_manifest = (
        bool(replay_row.get("plan_matches_manifest", False))
        if replay_row
        else planned_matches_manifest(planned=planned, manifest_row=manifest_row)
    )
    workspace_required = bool(workspace.get("workspace_required", False))
    mutation_guard_required = bool(workspace.get("mutation_guard_required", False))
    file_contract_required = bool(output_contract.get("file_contract_required", False))
    stdout_patch_allowed = bool(output_contract.get("stdout_patch_allowed", False))
    execution_enabled = bool(runner.get("execution_enabled", False))
    external_slot = workspace_required or file_contract_required or stdout_patch_allowed
    execution_audit_required = external_slot and (
        execution_enabled or file_contract_required or stdout_patch_allowed
    )
    replay_required = require_replay and bool(attempt_id)
    replay_present = bool(replay_row)
    replay_ok = bool(replay_row.get("ok", False)) if replay_present else False
    activation_status = str(preflight_profile.get("activation_status", "missing"))
    requirements = {
        "activation_ready": activation_status in {"ready", "missing"},
        "attempt_saved": attempt_saved,
        "plan_matches_manifest": plan_matches_manifest,
        "round_agent_input_present": bool(round_input_path),
        "attempt_agent_input_present": bool(attempt_input_path),
        "input_bundle_present": bool(input_bundle_path),
        "output_contract_declared": output_contract_declared(output_contract),
        "workspace_required": workspace_required,
        "workspace_manifest_required": workspace_required,
        "workspace_manifest_present": bool(workspace_manifest_path),
        "mutation_guard_required": mutation_guard_required,
        "mutation_guard_declared": (not workspace_required) or mutation_guard_required,
        "execution_audit_required": execution_audit_required,
        "execution_audit_present": bool(agent_execution_path),
        "replay_required": replay_required,
        "replay_present": replay_present,
        "replay_ok": replay_ok,
    }
    blocking_issues, advisory_issues = readiness_issues(
        requirements=requirements,
        external_slot=external_slot,
    )
    status = readiness_status(
        blocking_issues=blocking_issues,
        external_slot=external_slot,
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
        "external_slot": external_slot,
        "activation_status": activation_status,
        "readiness_status": status,
        "readiness_ok": not blocking_issues,
        "blocking_issues": blocking_issues,
        "advisory_issues": advisory_issues,
        "requirements": requirements,
        "paths": {
            "round_agent_input": str(round_input_path) if round_input_path else "",
            "attempt_agent_input": str(attempt_input_path) if attempt_input_path else "",
            "input_bundle": str(input_bundle_path) if input_bundle_path else "",
            "workspace_manifest": (
                str(workspace_manifest_path) if workspace_manifest_path else ""
            ),
            "agent_execution": str(agent_execution_path) if agent_execution_path else "",
            "round_replay": str(round_dir / "round_replay.json")
            if replay_present
            else "",
        },
    }


def readiness_issues(
    *,
    requirements: dict[str, bool],
    external_slot: bool,
) -> tuple[list[str], list[str]]:
    """Return blocking and advisory readiness issue codes."""
    blocking: list[str] = []
    advisory: list[str] = []
    required_true = (
        ("activation_ready", "activation_not_ready"),
        ("attempt_saved", "attempt_missing"),
        ("plan_matches_manifest", "plan_manifest_mismatch"),
        ("round_agent_input_present", "round_agent_input_missing"),
        ("attempt_agent_input_present", "attempt_agent_input_missing"),
        ("input_bundle_present", "input_bundle_missing"),
        ("output_contract_declared", "output_contract_missing"),
        ("mutation_guard_declared", "mutation_guard_missing"),
    )
    for key, code in required_true:
        if not requirements.get(key, False):
            blocking.append(code)
    if external_slot and requirements.get("workspace_manifest_required", False):
        if not requirements.get("workspace_manifest_present", False):
            blocking.append("workspace_manifest_missing")
    if external_slot and requirements.get("execution_audit_required", False):
        if not requirements.get("execution_audit_present", False):
            blocking.append("execution_audit_missing")
    if requirements.get("replay_required", False):
        if not requirements.get("replay_present", False):
            blocking.append("replay_missing")
        elif not requirements.get("replay_ok", False):
            blocking.append("replay_failed")
    if not external_slot:
        advisory.append("in_process_slot_no_external_workspace")
    return blocking, advisory


def readiness_status(*, blocking_issues: list[str], external_slot: bool) -> str:
    """Return the stable readiness status for one slot."""
    if blocking_issues:
        return "blocked"
    return "ready" if external_slot else "contract_only"


def output_contract_declared(output_contract: dict[str, Any]) -> bool:
    """Return whether a planned attempt declares a valid output mode."""
    output_mode = str(output_contract.get("output_mode", ""))
    if output_mode not in {"none", "file_contract", "stdout_patch"}:
        return False
    if output_mode == "file_contract":
        files = output_contract.get("allowed_output_files", [])
        return isinstance(files, list) and bool(files)
    return True


def profiles_by_name(preflight: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return preflight profile rows keyed by name."""
    return {
        str(profile.get("profile_name", "")): profile
        for profile in object_rows(preflight.get("profiles", []))
        if str(profile.get("profile_name", ""))
    }


def rows_by_id(value: object) -> dict[str, dict[str, Any]]:
    """Return object rows keyed by attempt id."""
    return {
        str(row.get("attempt_id", "")): row
        for row in object_rows(value)
        if str(row.get("attempt_id", ""))
    }


def planned_matches_manifest(
    *,
    planned: dict[str, Any],
    manifest_row: dict[str, Any],
) -> bool:
    """Return whether saved attempt metadata matches the execution plan."""
    if not manifest_row:
        return False
    for key in ("profile_name", "adapter_name", "agent_role"):
        if str(planned.get(key, "")) != str(manifest_row.get(key, "")):
            return False
    runner = object_value(planned.get("runner", {}))
    return str(runner.get("runner_name", "")) == str(manifest_row.get("runner_name", ""))


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
    """Return the first existing path from path text values."""
    for value in values:
        path = existing_path(repo_root, value)
        if path is not None:
            return path
    return None


def existing_path(repo_root: Path, value: str) -> Path | None:
    """Return a resolved path only when it exists."""
    if not value:
        return None
    path = resolve_path(Path(value), repo_root)
    return path if path.exists() else None


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root."""
    return path if path.is_absolute() else repo_root / path


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object, returning an empty object for missing or invalid files."""
    if not path.exists():
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


def agent_slot_readiness_gate_markdown(payload: dict[str, Any]) -> str:
    """Return a compact markdown readiness report."""
    lines = [
        "# Agent Slot Readiness Gate",
        "",
        f"- Schema: `{payload['schema_version']}`",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Slots: `{payload.get('totals', {}).get('slot_count', 0)}`",
        f"- Blocked: `{payload.get('totals', {}).get('blocked_count', 0)}`",
        "",
        "| Round | Attempt | Profile | Adapter | Runner | Status | Blocking issues |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for slot in object_rows(payload.get("slots", [])):
        issues = slot.get("blocking_issues", [])
        lines.append(
            "| "
            + " | ".join(
                [
                    str(slot.get("round_id", "")),
                    str(slot.get("attempt_id", "")),
                    str(slot.get("profile_name", "")),
                    str(slot.get("adapter_name", "")),
                    str(slot.get("runner_name", "")),
                    str(slot.get("readiness_status", "")),
                    ", ".join(str(item) for item in issues)
                    if isinstance(issues, list)
                    else "",
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    """CLI entrypoint for agent slot readiness reports."""
    args = parse_args()
    payload = write_agent_slot_readiness_gate(
        run_dir=args.run_dir,
        repo_root=args.repo_root,
        output_path=args.output,
        markdown_path=args.markdown,
        require_replay=not args.skip_replay_requirement,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not bool(payload["ok"]):
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Gate planned agent slots before enabling external execution.",
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
        help="Optional path for agent_slot_readiness_gate.json.",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=None,
        help="Optional path for agent_slot_readiness_gate.md.",
    )
    parser.add_argument(
        "--skip-replay-requirement",
        action="store_true",
        help="Do not block when round_replay.json is missing.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
