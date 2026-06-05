"""Compact run diagnosis for experiment review."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from orchestrator.artifact_validator import validate_run_artifacts
from orchestrator.run_outcome import build_run_outcome_summary


def diagnose_run(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    ignored_iteration_required_files: tuple[str, ...] = (),
) -> dict[str, object]:
    """Return a compact diagnosis for one experiment run."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    run_dir = experiments_dir / run_id
    artifact_report = validate_run_artifacts(
        run_id=run_id,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        ignored_iteration_required_files=ignored_iteration_required_files,
        validate_diagnosis=False,
    )
    base: dict[str, object] = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "artifact_ok": bool(artifact_report.get("ok", False)),
        "artifact_errors": artifact_report.get("errors", []),
        "artifact_warnings": artifact_report.get("warnings", []),
        "metadata": compact_metadata(load_json_object(run_dir / "run_metadata.json")),
    }

    manifest = load_json_object(run_dir / "manifest.json")
    if manifest is not None:
        return diagnose_iteration_run(
            run_dir=run_dir,
            manifest=manifest,
            base=base,
        )

    decision = load_json_object(run_dir / "decision.json")
    if decision is not None:
        return diagnose_single_run(run_dir=run_dir, decision=decision, base=base)

    return {
        **base,
        "kind": "unknown",
        "status": "missing",
        "summary": "Run is missing manifest.json and decision.json.",
    }


def write_run_diagnosis(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> Path:
    """Write diagnosis.json for one experiment run."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    output_path = experiments_dir / run_id / "diagnosis.json"
    payload = diagnose_run(
        run_id=run_id,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def diagnose_single_run(
    *,
    run_dir: Path,
    decision: dict[str, Any],
    base: dict[str, object],
) -> dict[str, object]:
    """Return diagnosis for a single evaluation run."""
    before = load_json_object(run_dir / "metrics_before.json") or {}
    after = load_json_object(run_dir / "metrics_after.json") or {}
    accepted = bool(decision.get("accepted", False))
    return {
        **base,
        "kind": "single_run",
        "status": "accepted" if accepted else "rejected",
        "accepted": accepted,
        "reasons": decision.get("reasons", []),
        "validation_ev_delta": metric_delta(before, after, "ev"),
        "trade_count_delta": metric_delta(before, after, "trade_count"),
        "operator_navigation": operator_navigation_unavailable(
            run_id=str(base.get("run_id", "")),
            run_kind="single_run",
            reason="not_iteration_run",
        ),
        "summary": single_run_summary(accepted, before, after, decision),
    }


def diagnose_iteration_run(
    *,
    run_dir: Path,
    manifest: dict[str, Any],
    base: dict[str, object],
) -> dict[str, object]:
    """Return diagnosis for a multi-round iteration run."""
    rounds = [
        row
        for row in manifest.get("rounds", [])
        if isinstance(row, dict) and isinstance(row.get("round_id"), str)
    ]
    round_diagnostics = [
        diagnose_round(run_dir=run_dir, round_payload=row) for row in rounds
    ]
    best_round = best_validation_round(round_diagnostics)
    selected_candidates = [
        row
        for row in load_json_list(run_dir / "candidate_leaderboard.json")
        if isinstance(row, dict) and row.get("selected") is True
    ]
    return {
        **base,
        "kind": "iteration_loop",
        "status": manifest.get("status", "unknown"),
        "completed_rounds": manifest.get("completed_rounds", 0),
        "accepted_round": manifest.get("accepted_round"),
        "stop_reason": manifest.get("stop_reason"),
        "final_strategy_commit": manifest.get("final_strategy_commit"),
        "best_round": best_round,
        "rounds": round_diagnostics,
        "agent_intake_summary": agent_intake_summary(round_diagnostics),
        "run_outcome_summary": build_run_outcome_summary(
            manifest=manifest,
            artifact_ok=bool(base.get("artifact_ok", False)),
            artifact_error_count=len(base.get("artifact_errors", []))
            if isinstance(base.get("artifact_errors", []), list)
            else 0,
        ),
        "operator_navigation": operator_navigation_from_manifest(
            run_id=str(base.get("run_id", "")),
            manifest=manifest,
        ),
        "selected_candidates": compact_candidates(selected_candidates),
        "summary": iteration_summary(manifest, round_diagnostics, best_round),
    }


def operator_navigation_from_manifest(
    *,
    run_id: str,
    manifest: dict[str, Any],
) -> dict[str, object]:
    """Return read-only operator navigation copied from manifest home hints."""
    operator_home = manifest.get("operator_home", {})
    if not isinstance(operator_home, dict):
        return operator_navigation_unavailable(
            run_id=run_id,
            run_kind="iteration_loop",
            reason="operator_home_missing",
        )
    home_available = bool(operator_home.get("command", ""))
    if not home_available:
        return operator_navigation_unavailable(
            run_id=run_id,
            run_kind="iteration_loop",
            reason="operator_home_unavailable",
        )
    next_command = str(operator_home.get("next_command", ""))
    home_command = str(operator_home.get("command", ""))
    selector_command = (
        f"python -m orchestrator.experiments next-command {run_id} --markdown"
    )
    return {
        "schema_version": "run_diagnosis_operator_navigation_v1",
        "available": True,
        "reason": "iteration_run",
        "run_id": run_id,
        "run_kind": "iteration_loop",
        "home": {
            "available": True,
            "command_label": str(operator_home.get("command_label", "")),
            "command": home_command,
            "command_sha256": str(
                operator_home.get("command_sha256", sha256_text(home_command))
            ),
            "status": str(operator_home.get("status", "unknown")),
            "primary_focus": str(operator_home.get("primary_focus", "")),
            "action_step": str(operator_home.get("action_step", "")),
            "terminal_only": bool(operator_home.get("terminal_only", True)),
            "artifact_created": bool(operator_home.get("artifact_created", False)),
            "command_boundary": str(operator_home.get("command_boundary", "")),
            "command_is_hint_only": bool(
                operator_home.get("command_is_hint_only", True)
            ),
        },
        "next_command": {
            "available": bool(next_command),
            "selection_source": "operator_home.next_command",
            "selector_command_label": "review_operator_next_command",
            "selector_command": selector_command,
            "selector_command_sha256": sha256_text(selector_command),
            "selector_boundary": "read_only_inspection",
            "selected_command_label": str(
                operator_home.get("next_command_label", "")
            ),
            "selected_command": next_command,
            "selected_command_sha256": str(
                operator_home.get(
                    "next_command_sha256",
                    sha256_text(next_command) if next_command else "",
                )
            ),
            "status": str(operator_home.get("next_command_status", "unavailable")),
            "blocked": bool(operator_home.get("next_command_blocked", False)),
            "blocker_count": int(
                operator_home.get("next_command_blocker_count", 0) or 0
            ),
            "operator_hint": str(
                operator_home.get("next_command_operator_hint", "")
            ),
            "boundary": str(operator_home.get("next_command_boundary", "")),
            "writes_artifact": str(
                operator_home.get("next_command_writes_artifact", "")
            ),
            "requires_explicit_operator_invocation": bool(
                operator_home.get(
                    "next_command_requires_explicit_operator_invocation",
                    False,
                )
            ),
            "requires_operator_approval": bool(
                operator_home.get("next_command_requires_operator_approval", False)
            ),
            "records_operator_approval": bool(
                operator_home.get("next_command_records_operator_approval", False)
            ),
            "uses_guarded_executor": bool(
                operator_home.get("next_command_uses_guarded_executor", False)
            ),
            "command_is_hint_only": bool(
                operator_home.get("next_command_is_hint_only", True)
            ),
        },
        "policy": operator_navigation_policy(),
    }


def operator_navigation_unavailable(
    *,
    run_id: str,
    run_kind: str,
    reason: str,
) -> dict[str, object]:
    """Return a stable unavailable operator-navigation block."""
    return {
        "schema_version": "run_diagnosis_operator_navigation_v1",
        "available": False,
        "reason": reason,
        "run_id": run_id,
        "run_kind": run_kind,
        "home": {
            "available": False,
            "command_label": "",
            "command": "",
            "command_sha256": "",
            "status": "unavailable",
            "primary_focus": "",
            "action_step": "",
            "terminal_only": True,
            "artifact_created": False,
            "command_boundary": "",
            "command_is_hint_only": True,
        },
        "next_command": {
            "available": False,
            "selection_source": "operator_home.next_command",
            "selector_command_label": "",
            "selector_command": "",
            "selector_command_sha256": "",
            "selector_boundary": "",
            "selected_command_label": "",
            "selected_command": "",
            "selected_command_sha256": "",
            "status": "unavailable",
            "blocked": False,
            "blocker_count": 0,
            "operator_hint": "",
            "boundary": "",
            "writes_artifact": "",
            "requires_explicit_operator_invocation": False,
            "requires_operator_approval": False,
            "records_operator_approval": False,
            "uses_guarded_executor": False,
            "command_is_hint_only": True,
        },
        "policy": operator_navigation_policy(),
    }


def sha256_text(value: str) -> str:
    """Return a SHA-256 digest for a text command."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def operator_navigation_policy() -> dict[str, bool]:
    """Return read-only policy flags for diagnosis navigation hints."""
    return {
        "inspection_only": True,
        "does_not_create_artifacts": True,
        "does_not_record_approval": True,
        "does_not_execute_commands": True,
        "does_not_execute_agents": True,
        "does_not_run_backtests": True,
        "does_not_write_config": True,
        "does_not_promote_champion": True,
        "does_not_apply_patches": True,
        "does_not_route_agents": True,
        "does_not_change_acceptance": True,
    }


def diagnose_round(
    *,
    run_dir: Path,
    round_payload: dict[str, Any],
) -> dict[str, object]:
    """Return compact diagnosis for one iteration round."""
    round_id = str(round_payload["round_id"])
    round_dir = run_dir / round_id
    proposal = load_json_object(round_dir / "proposal.json") or {}
    decision = load_json_object(round_dir / "decision.json") or {}
    agent_validation = load_json_object(round_dir / "agent_validation.json") or {}
    intake_diagnosis = compact_agent_intake_diagnosis(
        agent_validation.get("intake_diagnosis", {})
    )
    agent_bundle = load_json_object(round_dir / "agent_bundle_manifest.json") or {}
    agent_attempts = load_json_object(round_dir / "agent_attempts_manifest.json") or {}
    agent_selection = load_json_object(round_dir / "agent_selection_report.json") or {}
    workspace_manifest = load_json_object(round_dir / "workspace_manifest.json") or {}
    selected_attempt = selected_attempt_from_file(round_dir / "proposal_attempts.json")
    execution = load_json_object(round_dir / "agent_execution.json") or {}

    validation_delta = metric_pair_delta(
        round_payload,
        "validation_ev_before",
        "validation_ev_after",
    )
    trade_delta = metric_pair_delta(
        round_payload,
        "before_trade_count",
        "after_trade_count",
    )
    return {
        "round_id": round_id,
        "accepted": bool(round_payload.get("accepted", False)),
        "reasons": decision.get("reasons", round_payload.get("reasons", [])),
        "failure_stage": decision.get(
            "failure_stage",
            round_payload.get("failure_stage", "none"),
        ),
        "failure_code": decision.get(
            "failure_code",
            round_payload.get("failure_code", "none"),
        ),
        "reason_codes": decision.get("reason_codes", round_payload.get("reason_codes", [])),
        "agent_name": proposal.get("agent_name", ""),
        "direction_tag": proposal.get("direction_tag", ""),
        "proposal_applicable": bool(proposal.get("applicable", False)),
        "contract_errors": proposal.get("contract_errors", []),
        "agent_validation_ok": agent_validation.get("ok"),
        "agent_validation_errors": agent_validation.get("errors", []),
        "agent_intake_diagnosis": intake_diagnosis,
        "agent_intake_status": intake_diagnosis["status"],
        "agent_intake_primary_code": intake_diagnosis["primary_code"],
        "agent_bundle_present": bool(agent_bundle),
        "agent_bundle_input_file_count": len(agent_bundle.get("input_files", []))
        if isinstance(agent_bundle.get("input_files", []), list)
        else 0,
        "agent_bundle_output_file_count": len(agent_bundle.get("output_files", []))
        if isinstance(agent_bundle.get("output_files", []), list)
        else 0,
        "agent_attempt_trace_present": bool(agent_attempts),
        "agent_attempt_count": agent_attempts.get("attempt_count", 0),
        "selected_attempt_id": agent_attempts.get("selected_attempt_id", ""),
        "agent_selection_present": bool(agent_selection),
        "selection_rank_order": (
            agent_selection.get("selection_policy", {}).get("rank_order", [])
            if isinstance(agent_selection.get("selection_policy", {}), dict)
            else []
        ),
        "workspace_manifest_present": bool(workspace_manifest),
        "workspace_initial_file_count": (
            workspace_manifest.get("initial_snapshot", {}).get("file_count", 0)
            if isinstance(workspace_manifest.get("initial_snapshot", {}), dict)
            else 0
        ),
        "patch_sha256": proposal.get("patch_sha256", ""),
        "selected_role": selected_attempt.get("role", ""),
        "candidate_score": selected_attempt.get("candidate_score", 0),
        "candidate_status": selected_attempt.get("status", ""),
        "candidate_failure_code": selected_attempt.get("failure_code", "none"),
        "selection_reason": selected_attempt.get("selection_reason", ""),
        "probe_ev_delta": selected_attempt.get("probe_ev_delta", 0.0),
        "validation_ev_delta": validation_delta,
        "trade_count_delta": trade_delta,
        "file_protocol_status": execution.get("status", ""),
        "file_protocol_returncode": execution.get("returncode"),
        "summary": round_summary(
            round_id=round_id,
            direction_tag=str(proposal.get("direction_tag", "")),
            accepted=bool(round_payload.get("accepted", False)),
            validation_delta=validation_delta,
            reasons=decision.get("reasons", round_payload.get("reasons", [])),
        ),
    }


def selected_attempt_from_file(path: Path) -> dict[str, Any]:
    """Return selected proposal attempt from an attempts file."""
    for row in load_json_list(path):
        if isinstance(row, dict) and row.get("selected") is True:
            return row
    return {}


def compact_candidates(rows: list[dict[str, Any]]) -> list[dict[str, object]]:
    """Return compact selected candidate rows."""
    compact: list[dict[str, object]] = []
    for row in rows:
        compact.append(
            {
                "round_id": row.get("round_id", ""),
                "role": row.get("role", ""),
                "agent_name": row.get("agent_name", ""),
                "direction_tag": row.get("direction_tag", ""),
                "candidate_score": row.get("candidate_score", 0),
                "champion_gap": row.get("champion_gap", {}),
                "validation_ev_delta": row.get("validation_ev_delta"),
                "status": row.get("status", ""),
            }
        )
    return compact


def compact_agent_intake_diagnosis(value: object) -> dict[str, object]:
    """Return stable diagnosis fields from an agent_validation intake payload."""
    diagnosis = value if isinstance(value, dict) else {}
    blocking_raw = diagnosis.get("blocking_codes", [])
    blocking_codes = (
        [str(code) for code in blocking_raw] if isinstance(blocking_raw, list) else []
    )
    return {
        "schema_version": str(
            diagnosis.get("schema_version", "agent_intake_diagnosis_v1")
        ),
        "status": str(diagnosis.get("status", "unknown")),
        "primary_stage": str(diagnosis.get("primary_stage", "none")),
        "primary_code": str(diagnosis.get("primary_code", "none")),
        "primary_message": str(diagnosis.get("primary_message", "")),
        "blocking_codes": blocking_codes,
        "blocking_count": int(diagnosis.get("blocking_count", len(blocking_codes)) or 0),
        "retryable": bool(diagnosis.get("retryable", False)),
        "git_apply_status": str(diagnosis.get("git_apply_status", "not_checked")),
    }


def agent_intake_summary(rounds: list[dict[str, object]]) -> dict[str, object]:
    """Return run-level counts for agent output intake diagnoses."""
    code_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    blocked_round_count = 0
    retryable_round_count = 0
    primary_stage = "none"
    primary_code = "none"
    primary_message = ""
    round_rows: list[dict[str, object]] = []
    for row in rounds:
        diagnosis = compact_agent_intake_diagnosis(row.get("agent_intake_diagnosis", {}))
        status = str(diagnosis.get("status", "unknown"))
        code = str(diagnosis.get("primary_code", "none"))
        status_counts[status] = status_counts.get(status, 0) + 1
        if code and code != "none":
            code_counts[code] = code_counts.get(code, 0) + 1
        if status == "blocked":
            blocked_round_count += 1
            if primary_code == "none":
                primary_stage = str(diagnosis.get("primary_stage", "none"))
                primary_code = code
                primary_message = str(diagnosis.get("primary_message", ""))
        if bool(diagnosis.get("retryable", False)):
            retryable_round_count += 1
        round_rows.append({
            "round_id": str(row.get("round_id", "")),
            "status": status,
            "primary_stage": str(diagnosis.get("primary_stage", "none")),
            "primary_code": code,
            "blocking_codes": diagnosis.get("blocking_codes", []),
            "retryable": bool(diagnosis.get("retryable", False)),
        })
    return {
        "schema_version": "agent_intake_summary_v1",
        "round_count": len(round_rows),
        "blocked_round_count": blocked_round_count,
        "passed_round_count": int(status_counts.get("passed", 0)),
        "retryable_round_count": retryable_round_count,
        "primary_stage": primary_stage,
        "primary_code": primary_code,
        "primary_message": primary_message,
        "top_blocking_code": top_count_key(code_counts),
        "code_counts": code_counts,
        "status_counts": status_counts,
        "rounds": round_rows,
    }


def top_count_key(counts: dict[str, int]) -> str:
    """Return the highest-count key using stable lexical tie-breaking."""
    if not counts:
        return "none"
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def compact_metadata(metadata: dict[str, Any] | None) -> dict[str, object]:
    """Return compact run metadata for diagnosis."""
    if not metadata:
        return {}
    git_payload = metadata.get("git", {})
    git = git_payload if isinstance(git_payload, dict) else {}
    return {
        "schema_version": metadata.get("schema_version", ""),
        "config_path": metadata.get("config_path", ""),
        "strategy_modifier": metadata.get("strategy_modifier", ""),
        "dataset_sha256": compact_dataset_hashes(metadata),
        "git_commit": git.get("commit", ""),
        "git_dirty": bool(git.get("dirty", False)),
    }


def compact_dataset_hashes(metadata: dict[str, Any]) -> dict[str, str]:
    """Return dataset SHA-256 fingerprints keyed by split."""
    fingerprints = metadata.get("dataset_fingerprints", {})
    if not isinstance(fingerprints, dict):
        return {}
    hashes: dict[str, str] = {}
    for split, payload in sorted(fingerprints.items()):
        if isinstance(payload, dict):
            hashes[str(split)] = str(payload.get("sha256", ""))
    return hashes


def best_validation_round(rounds: list[dict[str, object]]) -> dict[str, object] | None:
    """Return the round with the best validation EV delta."""
    if not rounds:
        return None
    return max(rounds, key=lambda row: float(row.get("validation_ev_delta", 0.0)))


def single_run_summary(
    accepted: bool,
    before: dict[str, Any],
    after: dict[str, Any],
    decision: dict[str, Any],
) -> str:
    """Return a one-line single-run summary."""
    status = "accepted" if accepted else "rejected"
    reason = first_reason(decision.get("reasons", []))
    return (
        f"Single run {status}; validation EV delta "
        f"{metric_delta(before, after, 'ev'):.6f}; {reason}"
    )


def iteration_summary(
    manifest: dict[str, Any],
    rounds: list[dict[str, object]],
    best_round: dict[str, object] | None,
) -> str:
    """Return a one-line iteration-run summary."""
    status = str(manifest.get("status", "unknown"))
    completed = manifest.get("completed_rounds", len(rounds))
    stop_reason = manifest.get("stop_reason") or "none"
    if best_round is None:
        return f"Iteration run {status}; no completed rounds; stop reason: {stop_reason}"
    return (
        f"Iteration run {status}; completed {completed} rounds; best "
        f"{best_round.get('round_id')} validation EV delta "
        f"{float(best_round.get('validation_ev_delta', 0.0)):.6f}; "
        f"stop reason: {stop_reason}"
    )


def round_summary(
    *,
    round_id: str,
    direction_tag: str,
    accepted: bool,
    validation_delta: float,
    reasons: object,
) -> str:
    """Return one-line round diagnosis."""
    status = "accepted" if accepted else "rejected"
    return (
        f"{round_id} {status}; direction {direction_tag or 'none'}; "
        f"validation EV delta {validation_delta:.6f}; {first_reason(reasons)}"
    )


def first_reason(reasons: object) -> str:
    """Return compact first rejection reason text."""
    if isinstance(reasons, list) and reasons:
        return str(reasons[0])
    return "no rejection reason"


def metric_delta(
    before: dict[str, Any],
    after: dict[str, Any],
    key: str,
) -> float:
    """Return a numeric metric delta."""
    return round(float(after.get(key, 0.0)) - float(before.get(key, 0.0)), 6)


def metric_pair_delta(payload: dict[str, Any], before_key: str, after_key: str) -> float:
    """Return a numeric delta from two keys in one payload."""
    return round(float(payload.get(after_key, 0.0)) - float(payload.get(before_key, 0.0)), 6)


def load_json_object(path: Path) -> dict[str, Any] | None:
    """Load a JSON object if present."""
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def load_json_list(path: Path) -> list[Any]:
    """Load a JSON list if present."""
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root."""
    return path if path.is_absolute() else repo_root / path
