"""Inspect experiment history and artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from orchestrator.agent_result_stats import build_agent_result_stats
from orchestrator.agent_slot_readiness_gate import build_agent_slot_readiness_gate
from orchestrator.agent_slot_health import build_agent_slot_health
from orchestrator.artifact_validator_coverage import build_artifact_validator_coverage
from orchestrator.experiment_index import read_experiment_index, recent_experiments
from orchestrator.external_agent_sandbox_drill import (
    build_external_agent_sandbox_drill,
)
from orchestrator.outcome_memory import recent_outcomes
from orchestrator.run_diagnosis import diagnose_run


CHAMPION_SCHEMA_VERSION = "champion_v1"


def list_experiments(
    *,
    experiments_dir: Path = Path("experiments"),
    limit: int = 10,
) -> list[dict[str, object]]:
    """Return recent experiment records."""
    return recent_experiments(experiments_dir=experiments_dir, limit=limit)


def show_experiment(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return a compact summary for a run directory."""
    run_dir = experiments_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")

    manifest_path = run_dir / "manifest.json"
    decision_path = run_dir / "decision.json"
    if manifest_path.exists():
        manifest = load_json(manifest_path)
        return {
            "kind": "iteration_loop",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "summary_path": str(run_dir / "summary.md"),
            "candidate_leaderboard_path": str(run_dir / "candidate_leaderboard.json"),
            "manifest": manifest,
        }
    if decision_path.exists():
        decision = load_json(decision_path)
        return {
            "kind": "single_run",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "summary_path": str(run_dir / "summary.md"),
            "decision": decision,
        }
    raise FileNotFoundError(f"No manifest.json or decision.json for run: {run_id}")


def summarize_experiments(
    *,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return aggregate counts for local experiment history."""
    records = read_experiment_index(experiments_dir)
    by_kind: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for record in records:
        kind = str(record.get("kind", "unknown"))
        status = str(record.get("status", "unknown"))
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1

    leaderboard = experiment_leaderboard(experiments_dir=experiments_dir, limit=1)
    return {
        "total_runs": len(records),
        "by_kind": by_kind,
        "by_status": by_status,
        "best_run": leaderboard[0] if leaderboard else None,
    }


def experiment_leaderboard(
    *,
    experiments_dir: Path = Path("experiments"),
    limit: int = 10,
) -> list[dict[str, object]]:
    """Rank experiments by validation EV improvement."""
    rows = [
        experiment_score(record=record, experiments_dir=experiments_dir)
        for record in read_experiment_index(experiments_dir)
    ]
    rows.sort(
        key=lambda row: (
            float(row.get("ev_delta", 0.0)),
            str(row.get("created_at", "")),
        ),
        reverse=True,
    )
    return rows[: max(limit, 0)]


def candidate_leaderboard(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    limit: int = 20,
) -> list[dict[str, object]]:
    """Return ranked candidate attempts for an iteration run."""
    run_dir = experiments_dir / run_id
    path = run_dir / "candidate_leaderboard.json"
    if not path.exists():
        raise FileNotFoundError(f"Candidate leaderboard not found for run: {run_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Candidate leaderboard is not a list: {path}")
    rows = [row for row in payload if isinstance(row, dict)]
    return rows[: max(limit, 0)]


def agent_result_stats(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return agent/direction/patch-family aggregate stats for one run."""
    run_dir = experiments_dir / run_id
    path = run_dir / "agent_result_stats.json"
    if path.exists():
        payload = load_json(path)
        payload["from_artifact"] = True
        payload["round_replays"] = round_replay_summary(run_dir=run_dir)
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_agent_result_stats(run_dir=run_dir)
    payload["from_artifact"] = False
    payload["round_replays"] = round_replay_summary(run_dir=run_dir)
    return payload


def agent_slot_health_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return agent slot health, loading a saved report when present."""
    run_dir = experiments_dir / run_id
    path = run_dir / "agent_slot_health.json"
    if path.exists():
        payload = load_json(path)
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_agent_slot_health(run_dir=run_dir, repo_root=experiments_dir.parent)
    payload["from_artifact"] = False
    return payload


def agent_slot_readiness_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return agent slot readiness, loading a saved report when present."""
    run_dir = experiments_dir / run_id
    path = run_dir / "agent_slot_readiness_gate.json"
    if path.exists():
        payload = load_json(path)
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_agent_slot_readiness_gate(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
    )
    payload["from_artifact"] = False
    return payload


def external_agent_sandbox_report(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return external agent sandbox drill details for one run."""
    run_dir = experiments_dir / run_id
    path = run_dir / "external_agent_sandbox_drill.json"
    if path.exists():
        payload = load_json(path)
        payload["from_artifact"] = True
        return payload
    if not run_dir.exists():
        raise FileNotFoundError(f"Experiment run not found: {run_id}")
    payload = build_external_agent_sandbox_drill(
        run_dir=run_dir,
        repo_root=experiments_dir.parent,
    )
    payload["from_artifact"] = False
    return payload


def round_replay_summary(*, run_dir: Path) -> dict[str, object]:
    """Return compact round replay status for experiment inspection."""
    round_dirs = [
        path
        for path in sorted(run_dir.glob("round_*"))
        if path.is_dir()
    ]
    rounds = [round_replay_row(round_dir=round_dir) for round_dir in round_dirs]
    replayed_count = sum(1 for row in rounds if bool(row["exists"]))
    ok_count = sum(1 for row in rounds if bool(row["ok"]))
    return {
        "round_count": len(rounds),
        "replayed_round_count": replayed_count,
        "missing_round_count": len(rounds) - replayed_count,
        "ok_count": ok_count,
        "failure_count": replayed_count - ok_count,
        "rounds": rounds,
    }


def round_replay_row(*, round_dir: Path) -> dict[str, object]:
    """Return one compact round replay inspection row."""
    path = round_dir / "round_replay.json"
    markdown_path = round_dir / "round_replay.md"
    if not path.exists():
        return {
            "round_id": round_dir.name,
            "exists": False,
            "ok": False,
            "failure_code": "missing_round_replay",
            "failure_stage": "replay",
            "path": str(path),
            "markdown_path": str(markdown_path),
            "planned_attempt_count": 0,
            "manifest_attempt_count": 0,
            "replayed_attempt_count": 0,
            "selected_attempt_id": "",
            "attempts": [],
        }
    payload = load_json(path)
    attempts = payload.get("attempts", [])
    return {
        "round_id": str(payload.get("round_id", round_dir.name)),
        "exists": True,
        "ok": bool(payload.get("ok", False)),
        "failure_code": str(payload.get("failure_code", "")),
        "failure_stage": str(payload.get("failure_stage", "")),
        "path": str(path),
        "markdown_path": str(markdown_path),
        "planned_attempt_count": int(payload.get("planned_attempt_count", 0)),
        "manifest_attempt_count": int(payload.get("manifest_attempt_count", 0)),
        "replayed_attempt_count": int(payload.get("replayed_attempt_count", 0)),
        "selected_attempt_id": str(payload.get("selected_attempt_id", "")),
        "attempts": compact_round_replay_attempts(attempts),
    }


def compact_round_replay_attempts(attempts: object) -> list[dict[str, object]]:
    """Return compact attempt rows from a round replay payload."""
    if not isinstance(attempts, list):
        return []
    rows: list[dict[str, object]] = []
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        rows.append(
            {
                "attempt_id": str(attempt.get("attempt_id", "")),
                "profile_name": str(attempt.get("profile_name", "")),
                "adapter_name": str(attempt.get("adapter_name", "")),
                "runner_name": str(attempt.get("runner_name", "")),
                "selected": bool(attempt.get("selected", False)),
                "ok": bool(attempt.get("ok", False)),
                "failure_code": str(attempt.get("failure_code", "")),
                "plan_matches_manifest": bool(
                    attempt.get("plan_matches_manifest", False)
                ),
                "replay_path": str(attempt.get("replay_path", "")),
            }
        )
    return rows


def compare_experiments(
    *,
    base_run_id: str,
    candidate_run_id: str,
    experiments_dir: Path = Path("experiments"),
    min_ev_delta: float = 0.0,
) -> dict[str, object]:
    """Compare two runs and return a deterministic promotion recommendation."""
    base = diagnose_run(run_id=base_run_id, experiments_dir=experiments_dir)
    candidate = diagnose_run(run_id=candidate_run_id, experiments_dir=experiments_dir)
    base_perf = comparable_performance(base)
    candidate_perf = comparable_performance(candidate)
    dataset_comparison = compare_dataset_hashes(base, candidate)
    ev_delta = round(
        float(candidate_perf["validation_ev_delta"])
        - float(base_perf["validation_ev_delta"]),
        6,
    )
    trade_count_delta = int(candidate_perf["trade_count_delta"]) - int(
        base_perf["trade_count_delta"]
    )
    winner = comparison_winner(ev_delta=ev_delta, min_ev_delta=min_ev_delta)
    recommendation, reasons = comparison_recommendation(
        winner=winner,
        ev_delta=ev_delta,
        min_ev_delta=min_ev_delta,
        base_perf=base_perf,
        candidate_perf=candidate_perf,
        dataset_comparison=dataset_comparison,
    )
    return {
        "base_run_id": base_run_id,
        "candidate_run_id": candidate_run_id,
        "base": base_perf,
        "candidate": candidate_perf,
        "metric_deltas": {
            "validation_ev_delta": ev_delta,
            "trade_count_delta": trade_count_delta,
        },
        "dataset_comparison": dataset_comparison,
        "winner": winner,
        "recommendation": recommendation,
        "reasons": reasons,
        "min_ev_delta": min_ev_delta,
        "summary": comparison_summary(
            base_run_id=base_run_id,
            candidate_run_id=candidate_run_id,
            winner=winner,
            recommendation=recommendation,
            ev_delta=ev_delta,
        ),
    }


def show_champion(
    *,
    experiments_dir: Path = Path("experiments"),
) -> dict[str, object]:
    """Return the current champion registry, or an empty status."""
    path = champion_path(experiments_dir)
    if not path.exists():
        return {
            "exists": False,
            "schema_version": CHAMPION_SCHEMA_VERSION,
            "champion_path": str(path),
        }
    payload = load_json(path)
    return {
        "exists": True,
        "champion_path": str(path),
        "champion": payload,
    }


def promote_champion(
    *,
    base_run_id: str,
    candidate_run_id: str,
    experiments_dir: Path = Path("experiments"),
    min_ev_delta: float = 0.0,
) -> dict[str, object]:
    """Promote a candidate run to champion when deterministic comparison allows."""
    comparison = compare_experiments(
        base_run_id=base_run_id,
        candidate_run_id=candidate_run_id,
        experiments_dir=experiments_dir,
        min_ev_delta=min_ev_delta,
    )
    if comparison["recommendation"] != "promote_candidate":
        return {
            "promoted": False,
            "champion_path": str(champion_path(experiments_dir)),
            "history_path": str(champion_history_path(experiments_dir)),
            "comparison": comparison,
            "reason": "comparison did not recommend promotion",
            "current_champion": show_champion(experiments_dir=experiments_dir),
        }

    candidate = diagnose_run(
        run_id=candidate_run_id,
        experiments_dir=experiments_dir,
    )
    payload = champion_payload(
        base_run_id=base_run_id,
        candidate_run_id=candidate_run_id,
        experiments_dir=experiments_dir,
        comparison=comparison,
        candidate_diagnosis=candidate,
    )
    path = champion_path(experiments_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    history_path = append_champion_history(
        experiments_dir=experiments_dir,
        payload=payload,
    )
    return {
        "promoted": True,
        "champion_path": str(path),
        "history_path": str(history_path),
        "champion": payload,
        "comparison": comparison,
    }


def write_champion_comparison(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    min_ev_delta: float = 0.0,
) -> Path | None:
    """Write a run-local comparison against the current champion when available."""
    champion = show_champion(experiments_dir=experiments_dir)
    if not champion.get("exists", False):
        return None
    champion_payload_raw = champion.get("champion", {})
    champion_payload_data = (
        champion_payload_raw if isinstance(champion_payload_raw, dict) else {}
    )
    champion_run_id = str(champion_payload_data.get("champion_run_id", ""))
    if not champion_run_id or champion_run_id == run_id:
        return None

    comparison = compare_experiments(
        base_run_id=champion_run_id,
        candidate_run_id=run_id,
        experiments_dir=experiments_dir,
        min_ev_delta=min_ev_delta,
    )
    payload = {
        "schema_version": "champion_comparison_v1",
        "run_id": run_id,
        "champion_run_id": champion_run_id,
        "created_at": utc_timestamp(),
        "comparison": comparison,
    }
    output_path = experiments_dir / run_id / "champion_comparison.json"
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def champion_payload(
    *,
    base_run_id: str,
    candidate_run_id: str,
    experiments_dir: Path,
    comparison: dict[str, object],
    candidate_diagnosis: dict[str, object],
) -> dict[str, object]:
    """Build the champion registry payload."""
    metadata_payload = candidate_diagnosis.get("metadata", {})
    metadata = metadata_payload if isinstance(metadata_payload, dict) else {}
    candidate_payload = comparison.get("candidate", {})
    candidate = candidate_payload if isinstance(candidate_payload, dict) else {}
    return {
        "schema_version": CHAMPION_SCHEMA_VERSION,
        "champion_run_id": candidate_run_id,
        "promoted_from_run_id": base_run_id,
        "promoted_at": utc_timestamp(),
        "experiments_dir": str(experiments_dir),
        "source_kind": candidate.get("kind", "unknown"),
        "source_status": candidate.get("status", "unknown"),
        "source_best_round": candidate.get("best_round"),
        "strategy_commit": champion_strategy_commit(candidate_diagnosis, metadata),
        "strategy_modifier": str(metadata.get("strategy_modifier", "")),
        "dataset_sha256": metadata.get("dataset_sha256", {}),
        "validation_ev_delta": candidate.get("validation_ev_delta", 0.0),
        "trade_count_delta": candidate.get("trade_count_delta", 0),
        "comparison_summary": comparison["summary"],
        "promotion_reasons": comparison["reasons"],
        "comparison": comparison,
    }


def champion_strategy_commit(
    diagnosis: dict[str, object],
    metadata: dict[str, object],
) -> str:
    """Return the best available commit for the champion strategy."""
    final_commit = diagnosis.get("final_strategy_commit")
    if isinstance(final_commit, str) and final_commit:
        return final_commit
    commit = metadata.get("git_commit")
    return str(commit) if commit else ""


def append_champion_history(
    *,
    experiments_dir: Path,
    payload: dict[str, object],
) -> Path:
    """Append one champion promotion event to history."""
    path = champion_history_path(experiments_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return path


def champion_path(experiments_dir: Path) -> Path:
    """Return the current champion registry path."""
    return experiments_dir / "champion.json"


def champion_history_path(experiments_dir: Path) -> Path:
    """Return the champion promotion history path."""
    return experiments_dir / "champion_history.jsonl"


def utc_timestamp() -> str:
    """Return a deterministic-format UTC timestamp."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def comparable_performance(diagnosis: dict[str, object]) -> dict[str, object]:
    """Return the comparable performance row for one diagnosis payload."""
    kind = str(diagnosis.get("kind", "unknown"))
    status = str(diagnosis.get("status", "unknown"))
    if kind == "iteration_loop":
        best_round = diagnosis.get("best_round")
        best = best_round if isinstance(best_round, dict) else {}
        return {
            "run_id": diagnosis.get("run_id", ""),
            "kind": kind,
            "status": status,
            "accepted": status == "accepted",
            "artifact_ok": bool(diagnosis.get("artifact_ok", False)),
            "validation_ev_delta": float(best.get("validation_ev_delta", 0.0)),
            "trade_count_delta": int(best.get("trade_count_delta", 0)),
            "best_round": best.get("round_id"),
            "summary": diagnosis.get("summary", ""),
        }
    return {
        "run_id": diagnosis.get("run_id", ""),
        "kind": kind,
        "status": status,
        "accepted": bool(diagnosis.get("accepted", False)),
        "artifact_ok": bool(diagnosis.get("artifact_ok", False)),
        "validation_ev_delta": float(diagnosis.get("validation_ev_delta", 0.0)),
        "trade_count_delta": int(diagnosis.get("trade_count_delta", 0)),
        "best_round": None,
        "summary": diagnosis.get("summary", ""),
    }


def compare_dataset_hashes(
    base: dict[str, object],
    candidate: dict[str, object],
) -> dict[str, object]:
    """Compare compact dataset hashes from two diagnosis payloads."""
    base_hashes = dataset_hashes_from_diagnosis(base)
    candidate_hashes = dataset_hashes_from_diagnosis(candidate)
    compared_splits = sorted(set(base_hashes) | set(candidate_hashes))
    missing_fingerprints = []
    if not base_hashes:
        missing_fingerprints.append("base")
    if not candidate_hashes:
        missing_fingerprints.append("candidate")
    mismatched = [
        split
        for split in compared_splits
        if base_hashes.get(split, "") != candidate_hashes.get(split, "")
    ]
    return {
        "match": not missing_fingerprints and not mismatched,
        "compared_splits": compared_splits,
        "mismatched_splits": mismatched,
        "missing_fingerprints": missing_fingerprints,
        "base_sha256": base_hashes,
        "candidate_sha256": candidate_hashes,
    }


def dataset_hashes_from_diagnosis(diagnosis: dict[str, object]) -> dict[str, str]:
    """Return dataset hashes from a diagnosis payload."""
    metadata_payload = diagnosis.get("metadata", {})
    metadata = metadata_payload if isinstance(metadata_payload, dict) else {}
    hashes_payload = metadata.get("dataset_sha256", {})
    if not isinstance(hashes_payload, dict):
        return {}
    return {str(key): str(value) for key, value in hashes_payload.items()}


def comparison_winner(*, ev_delta: float, min_ev_delta: float) -> str:
    """Return the metric winner label."""
    if ev_delta > min_ev_delta:
        return "candidate"
    if ev_delta < -min_ev_delta:
        return "base"
    return "tie"


def comparison_recommendation(
    *,
    winner: str,
    ev_delta: float,
    min_ev_delta: float,
    base_perf: dict[str, object],
    candidate_perf: dict[str, object],
    dataset_comparison: dict[str, object],
) -> tuple[str, list[str]]:
    """Return a deterministic baseline-promotion recommendation."""
    reasons: list[str] = []
    if not bool(base_perf.get("artifact_ok", False)):
        reasons.append("base artifacts are invalid")
    if not bool(candidate_perf.get("artifact_ok", False)):
        reasons.append("candidate artifacts are invalid")
        return "keep_base", reasons
    missing = dataset_comparison.get("missing_fingerprints", [])
    if missing:
        reasons.append(f"dataset fingerprints missing for {', '.join(missing)}")
        return "inconclusive_missing_dataset_fingerprints", reasons
    if not bool(dataset_comparison.get("match", False)):
        reasons.append("dataset fingerprints differ")
        return "inconclusive_dataset_mismatch", reasons
    if winner == "candidate":
        reasons.append(
            f"candidate validation EV delta beats base by {ev_delta:.6f}"
        )
        if bool(candidate_perf.get("accepted", False)):
            return "promote_candidate", reasons
        reasons.append("candidate run was not accepted by its policy gate")
        return "review_candidate_not_accepted", reasons
    if winner == "base":
        reasons.append(
            f"candidate validation EV delta trails base by {abs(ev_delta):.6f}"
        )
        return "keep_base", reasons
    reasons.append(
        f"validation EV delta difference is within threshold {min_ev_delta:.6f}"
    )
    return "keep_base", reasons


def comparison_summary(
    *,
    base_run_id: str,
    candidate_run_id: str,
    winner: str,
    recommendation: str,
    ev_delta: float,
) -> str:
    """Return a one-line comparison summary."""
    return (
        f"Compared {candidate_run_id} against {base_run_id}: winner={winner}; "
        f"recommendation={recommendation}; validation EV delta difference "
        f"{ev_delta:.6f}."
    )


def experiment_score(
    *,
    record: dict[str, object],
    experiments_dir: Path,
) -> dict[str, object]:
    """Build one leaderboard row from index and artifact data."""
    kind = str(record.get("kind", "unknown"))
    if kind == "single_run":
        ev_before = float(record.get("ev_before", 0.0))
        ev_after = float(record.get("ev_after", 0.0))
        return {
            "run_id": record.get("run_id"),
            "kind": kind,
            "status": record.get("status"),
            "created_at": record.get("created_at"),
            "ev_before": ev_before,
            "ev_after": ev_after,
            "ev_delta": round(ev_after - ev_before, 6),
            "trade_count_before": record.get("trade_count_before"),
            "trade_count_after": record.get("trade_count_after"),
        }

    if kind == "iteration_loop":
        run_id = str(record.get("run_id", ""))
        manifest_path = experiments_dir / run_id / "manifest.json"
        best_round: dict[str, object] | None = None
        best_delta = 0.0
        if manifest_path.exists():
            manifest = load_json(manifest_path)
            for round_payload in manifest.get("rounds", []):
                if not isinstance(round_payload, dict):
                    continue
                before = float(round_payload.get("validation_ev_before", 0.0))
                after = float(round_payload.get("validation_ev_after", 0.0))
                delta = round(after - before, 6)
                if best_round is None or delta > best_delta:
                    best_round = round_payload
                    best_delta = delta
        return {
            "run_id": record.get("run_id"),
            "kind": kind,
            "status": record.get("status"),
            "created_at": record.get("created_at"),
            "completed_rounds": record.get("completed_rounds"),
            "accepted_round": record.get("accepted_round"),
            "ev_delta": best_delta,
            "best_round": best_round.get("round_id") if best_round else None,
        }

    return {
        "run_id": record.get("run_id"),
        "kind": kind,
        "status": record.get("status"),
        "created_at": record.get("created_at"),
        "ev_delta": 0.0,
    }


def load_json(path: Path) -> dict[str, object]:
    """Load a JSON object from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    """CLI entrypoint for experiment inspection."""
    parser = argparse.ArgumentParser(description="Inspect SuanAgent experiments.")
    parser.add_argument(
        "--experiments-dir",
        type=Path,
        default=Path("experiments"),
        help="Directory containing experiment artifacts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List recent experiments.")
    list_parser.add_argument("--limit", type=int, default=10)

    show_parser = subparsers.add_parser("show", help="Show one experiment.")
    show_parser.add_argument("run_id")

    leaderboard_parser = subparsers.add_parser(
        "leaderboard",
        help="Rank experiments by validation EV improvement.",
    )
    leaderboard_parser.add_argument("--limit", type=int, default=10)

    memory_parser = subparsers.add_parser(
        "memory",
        help="List recent proposal outcome memory records.",
    )
    memory_parser.add_argument("--limit", type=int, default=10)

    candidates_parser = subparsers.add_parser(
        "candidates",
        help="Show candidate leaderboard for one iteration run.",
    )
    candidates_parser.add_argument("run_id")
    candidates_parser.add_argument("--limit", type=int, default=20)

    agents_parser = subparsers.add_parser(
        "agents",
        help="Show aggregate agent, direction, and patch-family result stats.",
    )
    agents_parser.add_argument("run_id")

    slots_parser = subparsers.add_parser(
        "slots",
        help="Show agent slot health across one iteration run.",
    )
    slots_parser.add_argument("run_id")

    readiness_parser = subparsers.add_parser(
        "readiness",
        help="Show the external-agent slot readiness gate for one iteration run.",
    )
    readiness_parser.add_argument("run_id")

    sandbox_parser = subparsers.add_parser(
        "sandbox",
        help="Show external-agent sandbox drill details for one iteration run.",
    )
    sandbox_parser.add_argument("run_id")

    subparsers.add_parser(
        "coverage",
        help="Report schema, validator, docs, and replay coverage.",
    )

    subparsers.add_parser("champion", help="Show the current champion registry.")

    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare two runs and recommend whether to promote the candidate.",
    )
    compare_parser.add_argument("base_run_id")
    compare_parser.add_argument("candidate_run_id")
    compare_parser.add_argument("--min-ev-delta", type=float, default=0.0)

    promote_parser = subparsers.add_parser(
        "promote",
        help="Promote a candidate run to champion when comparison allows.",
    )
    promote_parser.add_argument("base_run_id")
    promote_parser.add_argument("candidate_run_id")
    promote_parser.add_argument("--min-ev-delta", type=float, default=0.0)

    diagnose_parser = subparsers.add_parser(
        "diagnose",
        help="Diagnose one run with artifact health and round outcomes.",
    )
    diagnose_parser.add_argument("run_id")

    subparsers.add_parser("summary", help="Summarize experiment history.")

    args = parser.parse_args()
    if args.command == "list":
        payload = list_experiments(
            experiments_dir=args.experiments_dir,
            limit=args.limit,
        )
    elif args.command == "show":
        payload = show_experiment(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
    elif args.command == "leaderboard":
        payload = experiment_leaderboard(
            experiments_dir=args.experiments_dir,
            limit=args.limit,
        )
    elif args.command == "memory":
        payload = recent_outcomes(
            experiments_dir=args.experiments_dir,
            limit=args.limit,
        )
    elif args.command == "candidates":
        payload = candidate_leaderboard(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
            limit=args.limit,
        )
    elif args.command == "agents":
        payload = agent_result_stats(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
    elif args.command == "slots":
        payload = agent_slot_health_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
    elif args.command == "readiness":
        payload = agent_slot_readiness_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
    elif args.command == "sandbox":
        payload = external_agent_sandbox_report(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
    elif args.command == "coverage":
        payload = build_artifact_validator_coverage(repo_root=args.experiments_dir.parent)
    elif args.command == "champion":
        payload = show_champion(experiments_dir=args.experiments_dir)
    elif args.command == "compare":
        payload = compare_experiments(
            experiments_dir=args.experiments_dir,
            base_run_id=args.base_run_id,
            candidate_run_id=args.candidate_run_id,
            min_ev_delta=args.min_ev_delta,
        )
    elif args.command == "promote":
        payload = promote_champion(
            experiments_dir=args.experiments_dir,
            base_run_id=args.base_run_id,
            candidate_run_id=args.candidate_run_id,
            min_ev_delta=args.min_ev_delta,
        )
    elif args.command == "diagnose":
        payload = diagnose_run(
            experiments_dir=args.experiments_dir,
            run_id=args.run_id,
        )
    else:
        payload = summarize_experiments(experiments_dir=args.experiments_dir)
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
