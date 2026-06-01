"""Compact run diagnosis for experiment review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.artifact_validator import validate_run_artifacts


def diagnose_run(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return a compact diagnosis for one experiment run."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    run_dir = experiments_dir / run_id
    artifact_report = validate_run_artifacts(
        run_id=run_id,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
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
        "selected_candidates": compact_candidates(selected_candidates),
        "summary": iteration_summary(manifest, round_diagnostics, best_round),
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
        "agent_name": proposal.get("agent_name", ""),
        "direction_tag": proposal.get("direction_tag", ""),
        "proposal_applicable": bool(proposal.get("applicable", False)),
        "contract_errors": proposal.get("contract_errors", []),
        "agent_validation_ok": agent_validation.get("ok"),
        "agent_validation_errors": agent_validation.get("errors", []),
        "patch_sha256": proposal.get("patch_sha256", ""),
        "selected_role": selected_attempt.get("role", ""),
        "candidate_score": selected_attempt.get("candidate_score", 0),
        "candidate_status": selected_attempt.get("status", ""),
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
