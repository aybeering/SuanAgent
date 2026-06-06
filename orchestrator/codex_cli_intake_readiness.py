"""Read-only Codex CLI intake-binding readiness summary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.operator_action_audit import file_record, resolve_path


CODEX_CLI_INTAKE_READINESS_SCHEMA_VERSION = "codex_cli_intake_readiness_v1"


def build_codex_cli_intake_readiness(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return operator-facing intake-binding readiness from saved gate evidence."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    unlock_gate_path = run_dir / "codex_cli_execution_unlock_gate.json"
    canary_gate_path = run_dir / "codex_cli_canary_gate.json"
    unlock_gate = load_json_object(unlock_gate_path)
    if unlock_gate:
        canary_run_dir = resolve_optional_path(
            str(unlock_gate.get("canary_run_dir", "")),
            repo_root=repo_root,
        )
        canary_gate_path = canary_run_dir / "codex_cli_canary_gate.json"
        canary_gate = load_json_object(canary_gate_path)
        return readiness_from_unlock_gate(
            unlock_gate=unlock_gate,
            canary_gate=canary_gate,
            unlock_gate_path=unlock_gate_path,
            canary_gate_path=canary_gate_path,
            repo_root=repo_root,
        )
    canary_gate = load_json_object(canary_gate_path)
    if canary_gate:
        return readiness_from_canary_gate(
            canary_gate=canary_gate,
            canary_gate_path=canary_gate_path,
            repo_root=repo_root,
        )
    return base_readiness(
        status="not_available",
        ready=False,
        applicable=False,
        source="none",
        source_artifacts={
            "codex_cli_execution_unlock_gate": file_record(unlock_gate_path, repo_root),
            "codex_cli_canary_gate": file_record(canary_gate_path, repo_root),
        },
        canary_intake_binding_ready=False,
        requires_intake_binding=False,
        slot_count=0,
        bound_slot_count=0,
        blocked_slot_count=0,
        blocking_reasons=[],
        next_step="generate Codex CLI canary or unlock evidence before reviewing intake binding readiness",
    )


def readiness_from_unlock_gate(
    *,
    unlock_gate: dict[str, Any],
    canary_gate: dict[str, Any],
    unlock_gate_path: Path,
    canary_gate_path: Path,
    repo_root: Path,
) -> dict[str, object]:
    """Summarize intake readiness from the final execution unlock gate."""
    checks = object_value(unlock_gate.get("checks", {}))
    policy = object_value(unlock_gate.get("policy", {}))
    gate_ready = bool(checks.get("canary_intake_binding_ready", False))
    blockers = [
        reason
        for reason in string_list(unlock_gate.get("blocking_reasons", []))
        if "intake_binding" in reason
    ]
    slot_summary = canary_slot_summary(canary_gate)
    if not blockers and not gate_ready:
        blockers.append("canary_intake_binding_not_ready")
    combined_blockers = blockers + slot_summary["blocking_reasons"]
    status = "ready" if gate_ready and not combined_blockers else "blocked"
    return base_readiness(
        status=status,
        ready=status == "ready",
        applicable=True,
        source="codex_cli_execution_unlock_gate",
        source_artifacts={
            "codex_cli_execution_unlock_gate": file_record(unlock_gate_path, repo_root),
            "codex_cli_canary_gate": file_record(canary_gate_path, repo_root),
        },
        canary_intake_binding_ready=gate_ready,
        requires_intake_binding=bool(
            policy.get("requires_canary_intake_binding", False)
        ),
        slot_count=slot_summary["slot_count"],
        bound_slot_count=slot_summary["bound_slot_count"],
        blocked_slot_count=slot_summary["blocked_slot_count"],
        blocking_reasons=combined_blockers,
        next_step=(
            "intake binding evidence is ready for operator review"
            if status == "ready"
            else "regenerate canary evidence until selected executions have bound, blocker-free intake and preflight records"
        ),
    )


def readiness_from_canary_gate(
    *,
    canary_gate: dict[str, Any],
    canary_gate_path: Path,
    repo_root: Path,
) -> dict[str, object]:
    """Summarize intake readiness from a local canary gate."""
    policy = object_value(canary_gate.get("policy", {}))
    slot_summary = canary_slot_summary(canary_gate)
    blockers = [
        reason
        for reason in string_list(canary_gate.get("blocking_reasons", []))
        if "intake_binding" in reason
    ]
    blockers.extend(slot_summary["blocking_reasons"])
    ready = bool(canary_gate.get("controlled_execution_ready", False)) and not blockers
    status = "ready" if ready else "blocked"
    return base_readiness(
        status=status,
        ready=ready,
        applicable=True,
        source="codex_cli_canary_gate",
        source_artifacts={
            "codex_cli_canary_gate": file_record(canary_gate_path, repo_root),
        },
        canary_intake_binding_ready=ready,
        requires_intake_binding=bool(policy.get("requires_intake_binding", False)),
        slot_count=slot_summary["slot_count"],
        bound_slot_count=slot_summary["bound_slot_count"],
        blocked_slot_count=slot_summary["blocked_slot_count"],
        blocking_reasons=blockers,
        next_step=(
            "intake binding evidence is ready for operator review"
            if ready
            else "inspect canary gate intake/preflight-binding slot blockers"
        ),
    )


def canary_slot_summary(canary_gate: dict[str, Any]) -> dict[str, Any]:
    """Return intake-binding counts and blockers from canary slot rows."""
    slots = list_of_dicts(canary_gate.get("slots", []))
    blockers: list[str] = []
    bound_count = 0
    blocked_count = 0
    for slot in slots:
        requirements = object_value(slot.get("requirements", {}))
        intake_bound = bool(requirements.get("intake_binding_bound", False))
        intake_clean = bool(requirements.get("intake_binding_clean", False))
        preflight_bound = bool(requirements.get("preflight_binding_bound", False))
        preflight_clean = bool(requirements.get("preflight_binding_clean", False))
        if intake_bound and intake_clean and preflight_bound and preflight_clean:
            bound_count += 1
        else:
            blocked_count += 1
            slot_id = str(slot.get("slot_id", ""))
            if not intake_bound:
                blockers.append(f"{slot_id}:intake_binding_not_bound")
            if not intake_clean:
                blockers.append(f"{slot_id}:intake_binding_has_blockers")
            if not preflight_bound:
                blockers.append(f"{slot_id}:preflight_binding_not_bound")
            if not preflight_clean:
                blockers.append(f"{slot_id}:preflight_binding_has_blockers")
        for issue in string_list(slot.get("blocking_issues", [])):
            if "intake_binding" in issue or "preflight_binding" in issue:
                blockers.append(f"{slot.get('slot_id', '')}:{issue}")
        evidence = object_value(slot.get("evidence", {}))
        for reason in string_list(evidence.get("intake_binding_blocking_reasons", [])):
            blockers.append(f"{slot.get('slot_id', '')}:{reason}")
        for reason in string_list(
            evidence.get("preflight_binding_blocking_reasons", [])
        ):
            blockers.append(f"{slot.get('slot_id', '')}:{reason}")
    return {
        "slot_count": len(slots),
        "bound_slot_count": bound_count,
        "blocked_slot_count": blocked_count,
        "blocking_reasons": unique_strings(blockers),
    }


def base_readiness(
    *,
    status: str,
    ready: bool,
    applicable: bool,
    source: str,
    source_artifacts: dict[str, object],
    canary_intake_binding_ready: bool,
    requires_intake_binding: bool,
    slot_count: int,
    bound_slot_count: int,
    blocked_slot_count: int,
    blocking_reasons: list[str],
    next_step: str,
) -> dict[str, object]:
    """Return the stable shared intake-readiness payload."""
    blockers = unique_strings(blocking_reasons)
    return {
        "schema_version": CODEX_CLI_INTAKE_READINESS_SCHEMA_VERSION,
        "status": status,
        "ready": ready,
        "applicable": applicable,
        "source": source,
        "source_artifacts": source_artifacts,
        "canary_intake_binding_ready": canary_intake_binding_ready,
        "requires_intake_binding": requires_intake_binding,
        "slot_count": slot_count,
        "bound_slot_count": bound_slot_count,
        "blocked_slot_count": blocked_slot_count,
        "blocking_reason_count": len(blockers),
        "blocking_reasons": blockers,
        "next_step": next_step,
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "does_not_execute_codex_cli": True,
            "does_not_record_operator_approval": True,
            "does_not_create_workspace": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
        },
    }


def validate_codex_cli_intake_readiness(payload: dict[str, object]) -> tuple[str, ...]:
    """Validate the shared intake-readiness summary derivations."""
    errors: list[str] = []
    status = str(payload.get("status", ""))
    ready = bool(payload.get("ready", False))
    blockers = string_list(payload.get("blocking_reasons", []))
    if status == "ready" and not ready:
        errors.append("codex_cli_intake_readiness ready status mismatch")
    if status in {"blocked", "not_available"} and ready:
        errors.append("codex_cli_intake_readiness blocked ready mismatch")
    if status == "blocked" and not blockers:
        errors.append("codex_cli_intake_readiness blocked without reasons")
    if status == "ready" and blockers:
        errors.append("codex_cli_intake_readiness ready with blockers")
    if int(payload.get("blocking_reason_count", -1)) != len(blockers):
        errors.append("codex_cli_intake_readiness blocker count mismatch")
    slot_count = int(payload.get("slot_count", 0) or 0)
    bound_count = int(payload.get("bound_slot_count", 0) or 0)
    blocked_count = int(payload.get("blocked_slot_count", 0) or 0)
    if bound_count + blocked_count != slot_count:
        errors.append("codex_cli_intake_readiness slot count mismatch")
    return tuple(errors)


def resolve_optional_path(path_text: str, *, repo_root: Path) -> Path:
    """Resolve a saved optional path, defaulting to the repository root."""
    if not path_text:
        return repo_root
    return resolve_path(Path(path_text), repo_root)


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object, returning empty when absent or malformed."""
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def object_value(value: object) -> dict[str, Any]:
    """Return a dict value or an empty dict."""
    return value if isinstance(value, dict) else {}


def list_of_dicts(value: object) -> list[dict[str, Any]]:
    """Return object rows from a possible list."""
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def string_list(value: object) -> list[str]:
    """Return string rows from a possible list."""
    return [str(row) for row in value if str(row)] if isinstance(value, list) else []


def unique_strings(values: list[str]) -> list[str]:
    """Return unique strings while preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
