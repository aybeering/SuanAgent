"""Deterministic quarantine gate for selected agent output before patch apply."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


AGENT_OUTPUT_QUARANTINE_SCHEMA_VERSION = "agent_output_quarantine_v1"
EXTERNAL_ADAPTERS = {
    "codex_cli",
    "codex_dry_run",
    "codex_cli_dry_run",
    "file_protocol",
}


def write_agent_output_quarantine(
    *,
    output_path: Path,
    markdown_path: Path,
    repo_root: Path,
    round_dir: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    proposal: Any,
    selected_attempt: dict[str, object],
    agent_validation: dict[str, object],
    raw_agent_output_path: Path,
    patch_path: Path,
) -> dict[str, object]:
    """Write the selected output quarantine report and return its payload."""
    payload = agent_output_quarantine_payload(
        repo_root=repo_root,
        round_dir=round_dir,
        run_id=run_id,
        round_id=round_id,
        round_index=round_index,
        proposal=proposal,
        selected_attempt=selected_attempt,
        agent_validation=agent_validation,
        raw_agent_output_path=raw_agent_output_path,
        patch_path=patch_path,
    )
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(agent_output_quarantine_markdown(payload), encoding="utf-8")
    return payload


def agent_output_quarantine_payload(
    *,
    repo_root: Path,
    round_dir: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    proposal: Any,
    selected_attempt: dict[str, object],
    agent_validation: dict[str, object],
    raw_agent_output_path: Path,
    patch_path: Path,
) -> dict[str, object]:
    """Return a JSON-friendly quarantine payload for one selected output."""
    adapter_name = str(selected_attempt.get("adapter_name", ""))
    runner = dict_or_empty(selected_attempt.get("runner", {}))
    proposal_applicable = bool(getattr(proposal, "applicable", False))
    validation_ok = bool(agent_validation.get("ok", False))
    checks = dict_or_empty(agent_validation.get("checks", {}))
    agent_output = load_json_object(round_dir / "agent_output.json")
    proposal_intent_summary = dict_or_empty(
        agent_output.get("proposal_intent_summary", {})
    )
    selected_attempt_payload = {
        "attempt_id": str(selected_attempt.get("attempt_id", "")),
        "role": str(selected_attempt.get("role", "")),
        "profile_name": str(selected_attempt.get("profile_name", "")),
        "adapter_name": adapter_name,
        "agent_role": str(selected_attempt.get("agent_role", "")),
        "runner_name": str(selected_attempt.get("runner_name", "")),
        "execution_enabled": bool(runner.get("execution_enabled", False)),
        "external_adapter": adapter_name in EXTERNAL_ADAPTERS,
        "candidate_status": str(selected_attempt.get("status", "")),
        "selected": bool(selected_attempt.get("selected", False)),
    }
    proposal_payload = {
        "agent_name": str(getattr(proposal, "agent_name", "")),
        "target_file": str(getattr(proposal, "target_file", "")),
        "applicable": proposal_applicable,
        "direction_tag": str(getattr(proposal, "direction_tag", "")),
        "patch_sha256": str(getattr(proposal, "patch_sha256", "")),
        "contract_errors": list(getattr(proposal, "contract_errors", ())),
        "rejection_reason": str(getattr(proposal, "rejection_reason", "")),
    }
    agent_validation_payload = {
        "path": relative_path(round_dir / "agent_validation.json", repo_root),
        "ok": validation_ok,
        "failure_stage": str(agent_validation.get("failure_stage", "")),
        "failure_code": str(agent_validation.get("failure_code", "")),
        "checks": checks,
        "errors": string_list(agent_validation.get("errors", [])),
    }
    artifacts = {
        "agent_input": file_record(round_dir / "agent_input.json", repo_root),
        "raw_agent_output": file_record(raw_agent_output_path, repo_root),
        "patch": file_record(patch_path, repo_root),
        "proposal": file_record(round_dir / "proposal.json", repo_root),
        "agent_output": file_record(round_dir / "agent_output.json", repo_root),
        "agent_validation": file_record(
            round_dir / "agent_validation.json",
            repo_root,
        ),
    }
    blocking_reasons = quarantine_blocking_reasons(
        proposal_applicable=proposal_applicable,
        validation_ok=validation_ok,
        raw_agent_output_path=raw_agent_output_path,
        patch_path=patch_path,
        checks=checks,
    )
    release_to_apply = proposal_applicable and not blocking_reasons
    status = quarantine_status(
        proposal_applicable=proposal_applicable,
        release_to_apply=release_to_apply,
    )
    consistency_checks = quarantine_consistency_checks(
        repo_root=repo_root,
        round_dir=round_dir,
        round_index=round_index,
        proposal_intent_summary=proposal_intent_summary,
        quarantine_status=status,
        release_to_apply=release_to_apply,
        blocking_reasons=blocking_reasons,
        selected_attempt=selected_attempt_payload,
        proposal=proposal_payload,
        agent_validation=agent_validation_payload,
        artifacts=artifacts,
    )
    return {
        "schema_version": AGENT_OUTPUT_QUARANTINE_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "round_index": round_index,
        "round_dir": relative_path(round_dir, repo_root),
        "proposal_intent_summary": proposal_intent_summary,
        "quarantine_status": status,
        "release_to_apply": release_to_apply,
        "blocking_reasons": blocking_reasons,
        "selected_attempt": selected_attempt_payload,
        "proposal": proposal_payload,
        "agent_validation": agent_validation_payload,
        "artifacts": artifacts,
        "consistency_checks": consistency_checks,
        "policy": {
            "quarantine_before_git_apply": True,
            "does_not_execute_agents": True,
            "does_not_apply_patch": True,
            "release_requires_agent_validation_ok": True,
            "release_requires_applicable_patch": True,
            "release_requires_git_apply_check_passed": True,
            "deterministic_policy_gate_keeps_acceptance_authority": True,
        },
    }


def quarantine_blocking_reasons(
    *,
    proposal_applicable: bool,
    validation_ok: bool,
    raw_agent_output_path: Path,
    patch_path: Path,
    checks: dict[str, object],
) -> list[str]:
    """Return stable quarantine blocker codes."""
    blockers: list[str] = []
    if not proposal_applicable:
        blockers.append("proposal_not_applicable")
    if not validation_ok:
        blockers.append("agent_validation_failed")
    if not raw_agent_output_path.exists():
        blockers.append("raw_agent_output_missing")
    if proposal_applicable and not patch_path.exists():
        blockers.append("patch_file_missing")
    elif proposal_applicable and not patch_path.read_text(encoding="utf-8").strip():
        blockers.append("patch_file_empty")
    if proposal_applicable and checks.get("contract_valid") is not True:
        blockers.append("contract_not_valid")
    if proposal_applicable and checks.get("git_apply_check") != "passed":
        blockers.append("git_apply_check_not_passed")
    if proposal_applicable and checks.get("strategy_only_patch") is not True:
        blockers.append("strategy_only_patch_not_confirmed")
    return blockers


def quarantine_consistency_checks(
    *,
    repo_root: Path,
    round_dir: Path,
    round_index: int,
    proposal_intent_summary: dict[str, object],
    quarantine_status: str,
    release_to_apply: bool,
    blocking_reasons: list[str],
    selected_attempt: dict[str, object],
    proposal: dict[str, object],
    agent_validation: dict[str, object],
    artifacts: dict[str, dict[str, object]],
) -> dict[str, object]:
    """Return deterministic consistency checks for quarantine source binding."""
    agent_input = load_json_object(round_dir / "agent_input.json")
    agent_output = load_json_object(round_dir / "agent_output.json")
    validation = load_json_object(round_dir / "agent_validation.json")
    proposal_file = load_json_object(round_dir / "proposal.json")
    patch_record = dict_or_empty(artifacts.get("patch", {}))
    agent_validation_record = dict_or_empty(artifacts.get("agent_validation", {}))
    patch_sha256 = str(proposal.get("patch_sha256", ""))
    selected_attempt_id = str(selected_attempt.get("attempt_id", ""))
    expected_status = quarantine_status_from_saved_state(
        proposal_applicable=bool(proposal.get("applicable", False)),
        release_to_apply=release_to_apply,
    )
    checks = {
        "release_status_matches_blockers": (
            release_to_apply == (not blocking_reasons and bool(proposal.get("applicable", False)))
        ),
        "quarantine_status_matches_release": quarantine_status == expected_status,
        "proposal_intent_matches_agent_input": (
            agent_input.get("proposal_intent_summary", {}) == proposal_intent_summary
        ),
        "proposal_intent_matches_agent_output": (
            agent_output.get("proposal_intent_summary", {}) == proposal_intent_summary
        ),
        "proposal_intent_matches_agent_validation": (
            validation.get("proposal_intent_summary", {}) == proposal_intent_summary
        ),
        "selected_attempt_matches_agent_output": any(
            str(row.get("attempt_id", "")) == selected_attempt_id
            and str(row.get("patch_sha256", "")) == patch_sha256
            for row in list_of_dicts(agent_output.get("attempts", []))
        ),
        "round_index_matches_agent_input": (
            int(agent_input.get("round_index", -1)) == round_index
        ),
        "proposal_hash_matches_agent_output": (
            string_from_path(agent_output, ("selected_proposal", "patch_sha256"))
            == patch_sha256
        ),
        "proposal_hash_matches_agent_validation": (
            str(validation.get("proposal_patch_sha256", "")) == patch_sha256
        ),
        "proposal_hash_matches_proposal_file": (
            str(proposal_file.get("patch_sha256", "")) == patch_sha256
        ),
        "patch_artifact_hash_matches_proposal": (
            (
                not patch_sha256
                and (
                    not bool(patch_record.get("exists", False))
                    or int(patch_record.get("bytes", 0) or 0) == 0
                )
            )
            or str(patch_record.get("sha256", "")) == patch_sha256
        ),
        "agent_validation_path_matches_artifact": (
            str(agent_validation.get("path", ""))
            == str(agent_validation_record.get("path", ""))
        ),
        "agent_validation_ok_matches_source": (
            bool(validation.get("ok", False)) == bool(agent_validation.get("ok", False))
        ),
        "contract_valid_matches_validation": (
            dict_or_empty(validation.get("checks", {})).get("contract_valid")
            == dict_or_empty(agent_validation.get("checks", {})).get("contract_valid")
        ),
        "git_apply_check_matches_validation": (
            dict_or_empty(validation.get("checks", {})).get("git_apply_check")
            == dict_or_empty(agent_validation.get("checks", {})).get("git_apply_check")
        ),
    }
    blocking = [
        f"quarantine_consistency:{name}"
        for name, passed in checks.items()
        if not passed
    ]
    return {
        "expected_status": expected_status,
        "selected_attempt_id": selected_attempt_id,
        "proposal_patch_sha256": patch_sha256,
        "artifact_paths": {
            key: str(record.get("path", ""))
            for key, record in artifacts.items()
        },
        "checks": checks,
        "blocking_reasons": blocking,
    }


def quarantine_status_from_saved_state(
    *,
    proposal_applicable: bool,
    release_to_apply: bool,
) -> str:
    """Return expected status from persisted quarantine booleans."""
    return quarantine_status(
        proposal_applicable=proposal_applicable,
        release_to_apply=release_to_apply,
    )


def quarantine_status(*, proposal_applicable: bool, release_to_apply: bool) -> str:
    """Return a stable quarantine status."""
    if release_to_apply:
        return "released"
    if proposal_applicable:
        return "blocked"
    return "not_applicable"


def file_record(path: Path, repo_root: Path) -> dict[str, object]:
    """Return deterministic metadata for a file artifact."""
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


def load_json_object(path: Path) -> dict[str, object]:
    """Load an optional JSON object artifact."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def agent_output_quarantine_markdown(payload: dict[str, object]) -> str:
    """Return a compact markdown quarantine report."""
    selected = dict_or_empty(payload.get("selected_attempt", {}))
    proposal = dict_or_empty(payload.get("proposal", {}))
    blockers = string_list(payload.get("blocking_reasons", []))
    return "\n".join(
        [
            "# Agent Output Quarantine",
            "",
            f"- Schema: `{payload['schema_version']}`",
            f"- Run: `{payload.get('run_id', '')}`",
            f"- Round: `{payload.get('round_id', '')}`",
            f"- Status: `{payload.get('quarantine_status', '')}`",
            f"- Release to apply: `{payload.get('release_to_apply', False)}`",
            f"- Adapter: `{selected.get('adapter_name', '')}`",
            f"- Agent: `{proposal.get('agent_name', '')}`",
            f"- Patch SHA-256: `{proposal.get('patch_sha256', '')}`",
            "",
            "## Blocking Reasons",
            *(f"- {reason}" for reason in blockers),
            "" if blockers else "- none",
            "",
            "Final acceptance remains controlled by deterministic policy gates.",
            "",
        ]
    )


def dict_or_empty(value: object) -> dict[str, object]:
    """Return a dict or an empty dict."""
    return value if isinstance(value, dict) else {}


def string_list(value: object) -> list[str]:
    """Return a deterministic list of strings."""
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list | tuple):
        return [str(item) for item in value if str(item)]
    return []


def list_of_dicts(value: object) -> list[dict[str, object]]:
    """Return object rows from a JSON list-like value."""
    if not isinstance(value, list | tuple):
        return []
    return [row for row in value if isinstance(row, dict)]


def string_from_path(payload: dict[str, object], keys: tuple[str, ...]) -> str:
    """Return a nested string from a JSON object."""
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key, "")
    return current if isinstance(current, str) else ""


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
