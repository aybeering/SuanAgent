"""Replay every saved candidate attempt for one round."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.attempt_replay import (
    DEFAULT_STRATEGY_MODULE,
    replay_attempt,
)
from orchestrator.failure_taxonomy import attach_failure_metadata, reason_code
from orchestrator.round_replay_summary import manifest_round_replay_summary


ROUND_REPLAY_SCHEMA_VERSION = "round_replay_v1"


def replay_round(
    *,
    round_dir: Path,
    repo_root: Path = Path("."),
    output_path: Path | None = None,
    markdown_path: Path | None = None,
    strategy_module: str = DEFAULT_STRATEGY_MODULE,
    run_probe: bool = True,
) -> dict[str, Any]:
    """Replay all saved attempts for one round and write a round-level report."""
    repo_root = repo_root.resolve()
    round_dir = resolve_path(round_dir, repo_root)
    plan_path = round_dir / "agent_execution_plan.json"
    manifest_path = round_dir / "agent_attempts_manifest.json"
    plan = load_json_object(plan_path)
    manifest = load_json_object(manifest_path)
    planned_attempts = planned_attempt_rows(plan)
    manifest_attempts = manifest_attempt_rows(manifest)
    attempts: list[dict[str, Any]] = []
    reason_codes = consistency_reason_codes(
        plan=plan,
        planned_attempts=planned_attempts,
        manifest_attempts=manifest_attempts,
    )
    for planned in planned_attempts:
        attempt_id = str(planned.get("attempt_id", ""))
        manifest_row = manifest_attempts.get(attempt_id)
        attempts.append(
            replay_attempt_row(
                planned=planned,
                manifest_row=manifest_row,
                repo_root=repo_root,
                strategy_module=strategy_module,
                run_probe=run_probe,
            )
        )
    for attempt_id, manifest_row in manifest_attempts.items():
        if attempt_id in {str(row.get("attempt_id", "")) for row in planned_attempts}:
            continue
        attempts.append(
            replay_attempt_row(
                planned={"attempt_id": attempt_id},
                manifest_row=manifest_row,
                repo_root=repo_root,
                strategy_module=strategy_module,
                run_probe=run_probe,
            )
        )
    for row in attempts:
        if not bool(row.get("ok", False)):
            reason_codes.append(
                reason_code(
                    stage="replay",
                    code="attempt_replay_failed",
                    message=f"{row.get('attempt_id', '')}: {row.get('failure_code', '')}",
                )
            )
    report = attach_failure_metadata(
        {
            "schema_version": ROUND_REPLAY_SCHEMA_VERSION,
            "ok": not reason_codes,
            "round_dir": str(round_dir),
            "run_id": str(plan.get("run_id", "")),
            "round_id": str(plan.get("round_id", round_dir.name)),
            "strategy_module": strategy_module,
            "run_probe": run_probe,
            "plan_path": str(plan_path),
            "attempts_manifest_path": str(manifest_path),
            "planned_attempt_count": len(planned_attempts),
            "manifest_attempt_count": len(manifest_attempts),
            "replayed_attempt_count": len(attempts),
            "selected_attempt_id": str(manifest.get("selected_attempt_id", "")),
            "attempts": attempts,
            "policy": {
                "does_not_execute_agents": True,
                "does_not_select_candidate": True,
                "does_not_apply_final_patch": True,
                "reuses_attempt_replay_contract": True,
            },
        },
        reason_codes,
    )
    destination = output_path or round_dir / "round_replay.json"
    write_json(destination, report)
    markdown_destination = markdown_path or round_dir / "round_replay.md"
    markdown_destination.write_text(round_replay_markdown(report), encoding="utf-8")
    refresh_parent_manifest_round_replay_summary(
        round_dir=round_dir,
        json_path=destination,
        markdown_path=markdown_destination,
        replay_report=report,
    )
    return report


def replay_attempt_row(
    *,
    planned: dict[str, Any],
    manifest_row: dict[str, Any] | None,
    repo_root: Path,
    strategy_module: str,
    run_probe: bool,
) -> dict[str, Any]:
    """Replay one planned attempt and return a compact round-level row."""
    attempt_id = str(planned.get("attempt_id", ""))
    if manifest_row is None:
        return {
            "attempt_id": attempt_id,
            "planned": True,
            "manifest_present": False,
            "ok": False,
            "failure_stage": "replay",
            "failure_code": "attempt_missing_from_manifest",
            "failure_message": f"{attempt_id} is absent from agent_attempts_manifest.json",
            "replay_path": "",
            "profile_name": str(planned.get("profile_name", "")),
            "adapter_name": str(planned.get("adapter_name", "")),
            "runner_name": planned_runner_name(planned),
            "selected": False,
            "plan_matches_manifest": False,
        }
    attempt_dir = resolve_path(Path(str(manifest_row.get("attempt_dir", ""))), repo_root)
    replay_path = attempt_dir / "attempt_replay.json"
    report = replay_attempt(
        attempt_dir=attempt_dir,
        repo_root=repo_root,
        output_path=replay_path,
        strategy_module=strategy_module,
        run_probe=run_probe,
    )
    plan_matches = attempt_plan_matches_manifest(planned=planned, manifest_row=manifest_row)
    return {
        "attempt_id": attempt_id or str(manifest_row.get("attempt_id", "")),
        "planned": bool(attempt_id),
        "manifest_present": True,
        "ok": bool(report.get("ok", False)) and plan_matches,
        "failure_stage": str(report.get("failure_stage", "none"))
        if plan_matches
        else "replay",
        "failure_code": str(report.get("failure_code", "none"))
        if plan_matches
        else "plan_manifest_mismatch",
        "failure_message": str(report.get("failure_message", ""))
        if plan_matches
        else "planned profile, adapter, or runner does not match manifest",
        "replay_path": str(replay_path),
        "profile_name": str(manifest_row.get("profile_name", planned.get("profile_name", ""))),
        "adapter_name": str(manifest_row.get("adapter_name", planned.get("adapter_name", ""))),
        "runner_name": str(manifest_row.get("runner_name", planned_runner_name(planned))),
        "selected": bool(manifest_row.get("selected", False)),
        "plan_matches_manifest": plan_matches,
        "probe": report.get("probe", {}),
        "validation_ok": bool(
            isinstance(report.get("validation", {}), dict)
            and report.get("validation", {}).get("ok", False)  # type: ignore[union-attr]
        ),
    }


def consistency_reason_codes(
    *,
    plan: dict[str, Any],
    planned_attempts: list[dict[str, Any]],
    manifest_attempts: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    """Return round-level consistency failures before per-attempt replay."""
    reasons: list[dict[str, str]] = []
    queue_count = plan.get("queue_count")
    if queue_count != len(planned_attempts):
        reasons.append(
            reason_code(
                stage="replay",
                code="plan_queue_count_mismatch",
                message=f"queue_count={queue_count} planned={len(planned_attempts)}",
            )
        )
    planned_ids = {str(row.get("attempt_id", "")) for row in planned_attempts}
    manifest_ids = set(manifest_attempts)
    missing = sorted(planned_ids - manifest_ids)
    extra = sorted(manifest_ids - planned_ids)
    if missing:
        reasons.append(
            reason_code(
                stage="replay",
                code="planned_attempt_missing",
                message=", ".join(missing),
            )
        )
    if extra:
        reasons.append(
            reason_code(
                stage="replay",
                code="manifest_attempt_not_planned",
                message=", ".join(extra),
            )
        )
    return reasons


def attempt_plan_matches_manifest(
    *,
    planned: dict[str, Any],
    manifest_row: dict[str, Any],
) -> bool:
    """Return whether stable plan metadata matches the saved manifest row."""
    checks = (
        ("profile_name", "profile_name"),
        ("adapter_name", "adapter_name"),
        ("agent_role", "agent_role"),
    )
    for plan_key, manifest_key in checks:
        if str(planned.get(plan_key, "")) != str(manifest_row.get(manifest_key, "")):
            return False
    if planned_runner_name(planned) != str(manifest_row.get("runner_name", "")):
        return False
    return True


def planned_runner_name(planned: dict[str, Any]) -> str:
    """Return the planned runner name from a plan attempt row."""
    runner = planned.get("runner", {})
    if isinstance(runner, dict):
        return str(runner.get("runner_name", ""))
    return ""


def planned_attempt_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Return planned attempt rows from agent_execution_plan.json."""
    attempts = plan.get("attempts", [])
    if not isinstance(attempts, list):
        return []
    return [row for row in attempts if isinstance(row, dict)]


def manifest_attempt_rows(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return manifest attempts keyed by attempt id."""
    attempts = manifest.get("attempts", [])
    if not isinstance(attempts, list):
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in attempts:
        if not isinstance(row, dict):
            continue
        attempt_id = str(row.get("attempt_id", ""))
        if attempt_id:
            rows[attempt_id] = row
    return rows


def round_replay_markdown(report: dict[str, Any]) -> str:
    """Return a compact markdown summary for a round replay report."""
    lines = [
        "# Round Replay",
        "",
        f"- Schema: `{report['schema_version']}`",
        f"- Run: `{report.get('run_id', '')}`",
        f"- Round: `{report.get('round_id', '')}`",
        f"- OK: `{str(report.get('ok', False)).lower()}`",
        f"- Attempts: `{report.get('replayed_attempt_count', 0)}`",
        f"- Failure: `{report.get('failure_code', 'none')}`",
        "",
        "| Attempt | Adapter | Runner | Selected | OK | Failure |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    attempts = report.get("attempts", [])
    if isinstance(attempts, list):
        for row in attempts:
            if not isinstance(row, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("attempt_id", "")),
                        str(row.get("adapter_name", "")),
                        str(row.get("runner_name", "")),
                        str(row.get("selected", False)).lower(),
                        str(row.get("ok", False)).lower(),
                        str(row.get("failure_code", "")),
                    ]
                )
                + " |"
            )
    lines.append("")
    return "\n".join(lines)


def refresh_parent_manifest_round_replay_summary(
    *,
    round_dir: Path,
    json_path: Path,
    markdown_path: Path,
    replay_report: dict[str, Any],
) -> None:
    """Refresh the parent run manifest when replay writes the standard artifacts."""
    standard_json_path = round_dir / "round_replay.json"
    standard_markdown_path = round_dir / "round_replay.md"
    if json_path.resolve() != standard_json_path.resolve():
        return
    if markdown_path.resolve() != standard_markdown_path.resolve():
        return
    run_dir = round_dir.parent
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return
    manifest = load_json_object(manifest_path)
    rounds = manifest.get("rounds", [])
    if not isinstance(rounds, list):
        return
    round_id = str(replay_report.get("round_id", round_dir.name))
    refreshed = False
    for row in rounds:
        if not isinstance(row, dict):
            continue
        if str(row.get("round_id", "")) != round_id:
            continue
        row["round_replay"] = manifest_round_replay_summary(
            round_id=round_id,
            replay_report=replay_report,
        )
        refreshed = True
        break
    if not refreshed:
        return
    write_json(manifest_path, manifest)
    from orchestrator.run_summary import write_iteration_summary

    write_iteration_summary(run_dir=run_dir, manifest=manifest)


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root when needed."""
    return path if path.is_absolute() else repo_root / path


def write_json(path: Path, payload: object) -> None:
    """Write deterministic JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    """CLI entrypoint for round replay."""
    args = parse_args()
    report = replay_round(
        round_dir=args.round_dir,
        repo_root=args.repo_root,
        output_path=args.output,
        markdown_path=args.markdown,
        strategy_module=args.strategy_module,
        run_probe=not args.skip_probe,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for round replay."""
    parser = argparse.ArgumentParser(
        description="Replay every saved candidate attempt for one round.",
    )
    parser.add_argument("round_dir", type=Path, help="Path to experiments/<run>/round_xxx.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root used for patch checks and probe replay.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write round_replay.json.",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=None,
        help="Optional path to write round_replay.md.",
    )
    parser.add_argument(
        "--strategy-module",
        default=DEFAULT_STRATEGY_MODULE,
        help="Import path for the candidate strategy module.",
    )
    parser.add_argument(
        "--skip-probe",
        action="store_true",
        help="Only replay contract and patch validation for each attempt.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
