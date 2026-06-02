"""Round-level agent routing decision artifact."""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.agent_attempts import ATTEMPTS_DIRNAME, attempt_trace_id


AGENT_ROUTING_SCHEMA_VERSION = "agent_routing_policy_v1"


def write_agent_routing_policy(
    *,
    output_path: Path,
    repo_root: Path,
    round_dir: Path,
    run_id: str,
    round_id: str,
    attempts: list[dict[str, object]],
    candidate_selection: dict[str, float | int],
) -> Path:
    """Write a compact routing decision artifact for one round."""
    payload = agent_routing_policy_payload(
        repo_root=repo_root,
        round_dir=round_dir,
        run_id=run_id,
        round_id=round_id,
        attempts=attempts,
        candidate_selection=candidate_selection,
    )
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def agent_routing_policy_payload(
    *,
    repo_root: Path,
    round_dir: Path,
    run_id: str,
    round_id: str,
    attempts: list[dict[str, object]],
    candidate_selection: dict[str, float | int],
) -> dict[str, object]:
    """Return the JSON payload explaining agent routing for one round."""
    candidates = routing_candidates(
        attempts=attempts,
        repo_root=repo_root,
        round_dir=round_dir,
    )
    selected = next((row for row in candidates if row["selected"] is True), {})
    return {
        "schema_version": AGENT_ROUTING_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "selected_attempt_id": str(selected.get("attempt_id", "")),
        "selected_profile_name": str(selected.get("profile_name", "")),
        "selected_adapter_name": str(selected.get("adapter_name", "")),
        "selected_agent_role": str(selected.get("agent_role", "")),
        "selected_runner_name": str(selected.get("runner_name", "")),
        "selection_reason": str(selected.get("selection_reason", "")),
        "routing_policy": {
            "mode": "deterministic_score_then_policy_gate",
            "eligible_status": "selectable",
            "rank_order": [
                "eligible_candidates",
                "candidate_score_desc",
                "attempt_index_asc",
            ],
            "candidate_selection": normalized_candidate_selection(candidate_selection),
            "final_acceptance": "policy_gate_after_backtest",
        },
        "candidates": candidates,
    }


def routing_candidates(
    *,
    attempts: list[dict[str, object]],
    repo_root: Path,
    round_dir: Path,
) -> list[dict[str, object]]:
    """Return candidate routing rows sorted by attempt order."""
    selected_index = selected_attempt_index(attempts)
    rows: list[dict[str, object]] = []
    for index, attempt in enumerate(attempts, start=1):
        attempt_id = str(
            attempt.get("attempt_id")
            or attempt_trace_id(index=index, role=str(attempt.get("role", "")))
        )
        selected = bool(attempt.get("selected", False))
        status = str(attempt.get("status", ""))
        blocking_reasons = attempt_blocking_reasons(attempt)
        rows.append(
            {
                "attempt_id": attempt_id,
                "attempt_index": int(attempt.get("attempt_index", index)),
                "role": str(attempt.get("role", "")),
                "agent_role": str(attempt.get("agent_role", "")),
                "profile_name": str(attempt.get("profile_name", "")),
                "adapter_name": str(attempt.get("adapter_name", "")),
                "supported_directions": list_or_empty(
                    attempt.get("supported_directions", [])
                ),
                "direction_capability": dict_or_empty(
                    attempt.get("direction_capability", {})
                ),
                "direction_intent_alignment": dict_or_empty(
                    attempt.get("direction_intent_alignment", {})
                ),
                "runner_name": str(attempt.get("runner_name", "")),
                "runner": dict_or_empty(attempt.get("runner", {})),
                "agent_name": str(attempt.get("agent_name", "")),
                "direction_tag": str(attempt.get("direction_tag", "")),
                "status": status,
                "eligible": status == "selectable",
                "selected": selected,
                "rank": attempt_rank(attempts=attempts, attempt_index=index - 1),
                "candidate_score": attempt.get("candidate_score", 0),
                "quality_breakdown": dict_or_empty(
                    attempt.get("quality_breakdown", {})
                ),
                "score_reasons": list_or_empty(attempt.get("score_reasons", [])),
                "blocking_reasons": blocking_reasons,
                "selection_reason": str(attempt.get("selection_reason", "")),
                "skip_reason": attempt_skip_reason(
                    attempt=attempt,
                    selected=selected,
                    selected_index=selected_index,
                    blocking_reasons=blocking_reasons,
                ),
                "failure_stage": str(attempt.get("failure_stage", "none")),
                "failure_code": str(attempt.get("failure_code", "none")),
                "failure_message": str(attempt.get("failure_message", "")),
                "patch_sha256": str(attempt.get("patch_sha256", "")),
                "probe_ev_delta": attempt.get("probe_ev_delta", 0.0),
                "validation_ev_delta": attempt.get("validation_ev_delta", None),
                "holdout_ev_delta": attempt.get("holdout_ev_delta", None),
                "validation_status": str(attempt.get("validation_status", "")),
                "routing_prior": dict_or_empty(attempt.get("routing_prior", {})),
                "exploration_bonus": dict_or_empty(
                    attempt.get("exploration_bonus", {})
                ),
                "champion_gap": dict_or_empty(attempt.get("champion_gap", {})),
                "artifacts": candidate_artifacts(
                    attempt_id=attempt_id,
                    repo_root=repo_root,
                    round_dir=round_dir,
                ),
            }
        )
    return rows


def candidate_artifacts(
    *,
    attempt_id: str,
    repo_root: Path,
    round_dir: Path,
) -> dict[str, str]:
    """Return stable artifact paths for one routed candidate."""
    attempt_dir = round_dir / ATTEMPTS_DIRNAME / attempt_id
    return {
        "attempt_dir": relative_path(attempt_dir, repo_root),
        "attempt_output": relative_path(attempt_dir / "attempt_output.json", repo_root),
        "agent_input": relative_path(attempt_dir / "agent_input.json", repo_root),
        "selection": relative_path(attempt_dir / "selection.json", repo_root),
        "proposal": relative_path(attempt_dir / "proposal.json", repo_root),
    }


def normalized_candidate_selection(
    candidate_selection: dict[str, float | int],
) -> dict[str, float | int]:
    """Return stable candidate-selection weights for routing audit."""
    return {str(key): candidate_selection[key] for key in sorted(candidate_selection)}


def selected_attempt_index(attempts: list[dict[str, object]]) -> int | None:
    """Return selected attempt list index."""
    for index, attempt in enumerate(attempts):
        if bool(attempt.get("selected", False)):
            return index
    return None


def attempt_rank(
    *,
    attempts: list[dict[str, object]],
    attempt_index: int,
) -> int:
    """Return rank over selected/selectable candidate attempts."""
    ordered_indexes = sorted(
        range(len(attempts)),
        key=lambda index: (
            bool(attempts[index].get("selected", False)),
            int(attempts[index].get("candidate_score", 0)),
            -index,
        ),
        reverse=True,
    )
    return ordered_indexes.index(attempt_index) + 1


def attempt_blocking_reasons(attempt: dict[str, object]) -> list[str]:
    """Return deterministic reasons why a candidate was not routable."""
    reasons: list[str] = []
    for field in (
        "contract_errors",
        "memory_filter_reason",
        "patch_memory_filter_reason",
        "direction_filter_reason",
        "direction_capability_reason",
        "patch_check_error",
        "probe_error",
    ):
        value = attempt.get(field)
        if isinstance(value, list | tuple):
            reasons.extend(str(item) for item in value if str(item))
        elif value:
            reasons.append(str(value))
    status = str(attempt.get("status", ""))
    if status and status != "selectable" and not reasons:
        reasons.append(f"status={status}")
    return reasons


def attempt_skip_reason(
    *,
    attempt: dict[str, object],
    selected: bool,
    selected_index: int | None,
    blocking_reasons: list[str],
) -> str:
    """Return a stable routing skip reason."""
    if selected:
        return ""
    if blocking_reasons:
        return "; ".join(blocking_reasons)
    if selected_index is None:
        return "no selected attempt"
    return (
        "selectable but not highest ranked"
        if str(attempt.get("status", "")) == "selectable"
        else f"status={attempt.get('status', 'unknown')}"
    )


def dict_or_empty(value: object) -> dict[str, object]:
    """Return JSON-object metadata without leaking non-dict values."""
    if not isinstance(value, dict):
        return {}
    return {str(key): entry for key, entry in value.items()}


def list_or_empty(value: object) -> list[object]:
    """Return JSON-list metadata without leaking tuple values."""
    return list(value) if isinstance(value, list | tuple) else []


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
