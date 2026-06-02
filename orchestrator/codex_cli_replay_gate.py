"""Readiness gate for enabling guarded Codex CLI execution."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from orchestrator.agent_contract_runner import CODEX_CLI_GUARDED_RUNNER_NAME


CODEX_CLI_REPLAY_GATE_SCHEMA_VERSION = "codex_cli_replay_gate_v1"


def build_codex_cli_replay_gate(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Return a deterministic readiness gate for guarded Codex CLI slots."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    slots: list[dict[str, Any]] = []
    for round_dir in round_dirs(run_dir):
        slots.extend(codex_round_slots(round_dir=round_dir, repo_root=repo_root))
    status_counts = Counter(str(slot["gate_status"]) for slot in slots)
    blocked_count = status_counts.get("blocked", 0)
    return {
        "schema_version": CODEX_CLI_REPLAY_GATE_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "ok": bool(slots) and blocked_count == 0,
        "ready_to_enable_codex_cli": bool(slots) and blocked_count == 0,
        "source_artifacts": {
            "rounds": [
                str(path / "agent_execution_plan.json") for path in round_dirs(run_dir)
            ],
            "codex_cli_contract_fixtures": [
                str(path / "codex_cli_contract_fixture.json")
                for path in round_dirs(run_dir)
                if (path / "codex_cli_contract_fixture.json").exists()
            ],
            "round_replays": [
                str(path / "round_replay.json")
                for path in round_dirs(run_dir)
                if (path / "round_replay.json").exists()
            ],
        },
        "totals": {
            "slot_count": len(slots),
            "ready_count": status_counts.get("ready", 0),
            "blocked_count": blocked_count,
            "codex_cli_slot_count": len(slots),
        },
        "status_counts": dict(sorted(status_counts.items())),
        "slots": slots,
        "policy": {
            "gate_only": True,
            "does_not_execute_codex_cli": True,
            "does_not_select_candidate": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
            "requires_guarded_execution_audit": True,
            "requires_contract_fixture": True,
            "requires_quarantine": True,
            "requires_round_replay": True,
            "deterministic_code_keeps_acceptance_authority": True,
        },
    }


def write_codex_cli_replay_gate(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    """Write JSON and markdown Codex CLI replay-gate artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_codex_cli_replay_gate(run_dir=run_dir, repo_root=repo_root)
    destination = output_path or run_dir / "codex_cli_replay_gate.json"
    write_json(destination, payload)
    markdown_destination = markdown_path or run_dir / "codex_cli_replay_gate.md"
    markdown_destination.write_text(
        codex_cli_replay_gate_markdown(payload),
        encoding="utf-8",
    )
    return payload


def codex_round_slots(*, round_dir: Path, repo_root: Path) -> list[dict[str, Any]]:
    """Return replay-gate rows for planned Codex CLI slots in one round."""
    plan = load_json_object(round_dir / "agent_execution_plan.json")
    manifest = load_json_object(round_dir / "agent_attempts_manifest.json")
    replay = load_json_object(round_dir / "round_replay.json")
    replay_attempts = rows_by_id(replay.get("attempts", []))
    manifest_attempts = rows_by_id(manifest.get("attempts", []))
    rows: list[dict[str, Any]] = []
    for planned in object_rows(plan.get("attempts", [])):
        if str(planned.get("adapter_name", "")) != "codex_cli":
            continue
        rows.append(
            codex_slot_row(
                round_dir=round_dir,
                repo_root=repo_root,
                planned=planned,
                manifest_row=manifest_attempts.get(str(planned.get("attempt_id", "")), {}),
                replay_row=replay_attempts.get(str(planned.get("attempt_id", "")), {}),
            )
        )
    return rows


def codex_slot_row(
    *,
    round_dir: Path,
    repo_root: Path,
    planned: dict[str, Any],
    manifest_row: dict[str, Any],
    replay_row: dict[str, Any],
) -> dict[str, Any]:
    """Return one guarded Codex CLI replay-gate row."""
    attempt_id = str(planned.get("attempt_id", ""))
    runner = object_value(planned.get("runner", {}))
    planned_artifacts = object_value(planned.get("planned_artifacts", {}))
    execution_path = first_existing_path(
        repo_root,
        [
            str(planned_artifacts.get("agent_execution", "")),
            str(round_dir / "agent_executions" / f"{attempt_id}.json"),
            str(round_dir / "agent_attempts" / attempt_id / "agent_execution.json"),
            str(round_dir / "agent_execution.json"),
        ],
    )
    execution = load_json_object(execution_path) if execution_path else {}
    fixture_path = round_dir / "codex_cli_contract_fixture.json"
    fixture = load_json_object(fixture_path) if fixture_path.exists() else {}
    quarantine_path = round_dir / "agent_output_quarantine.json"
    quarantine = load_json_object(quarantine_path) if quarantine_path.exists() else {}
    fixture_checks = object_value(fixture.get("checks", {}))
    quarantine_policy = object_value(quarantine.get("policy", {}))
    mutation_guard = object_value(execution.get("mutation_guard", {}))
    stdin_summary = object_value(execution.get("stdin", {}))
    replay_present = bool(replay_row)
    replay_ok = bool(replay_row.get("ok", False)) if replay_present else False
    quarantine_present = bool(quarantine)
    fixture_present = bool(fixture)
    requirements = {
        "attempt_saved": bool(manifest_row),
        "adapter_is_codex_cli": str(planned.get("adapter_name", "")) == "codex_cli",
        "runner_is_guarded_codex_cli": (
            str(runner.get("runner_name", "")) == CODEX_CLI_GUARDED_RUNNER_NAME
            and str(execution.get("runner_name", "")) == CODEX_CLI_GUARDED_RUNNER_NAME
        ),
        "agent_execution_present": bool(execution_path),
        "agent_execution_not_enabled_yet": not bool(execution.get("execution_enabled", True)),
        "stdin_recorded": (
            int_value(stdin_summary.get("chars", 0)) > 0
            and bool(str(stdin_summary.get("sha256", "")))
        ),
        "mutation_guard_passed": bool(mutation_guard.get("passed", False)),
        "contract_fixture_present": fixture_present,
        "contract_fixture_ok": bool(fixture.get("ok", False)),
        "contract_fixture_prompt_hash_ok": bool(
            fixture_checks.get("stdin_prompt_sha_matches_audit", False)
        ),
        "contract_fixture_stdout_valid": bool(
            fixture_checks.get("fixture_stdout_validation_ok", False)
        ),
        "quarantine_present": quarantine_present,
        "quarantine_policy_ok": bool(
            quarantine_policy.get(
                "deterministic_policy_gate_keeps_acceptance_authority",
                False,
            )
        ),
        "quarantine_not_released_for_disabled_codex": (
            quarantine_present
            and bool(quarantine.get("release_to_apply", False)) is False
            and str(quarantine.get("quarantine_status", "")) == "not_applicable"
        ),
        "round_replay_present": replay_present,
        "round_replay_ok": replay_ok,
        "round_replay_plan_matches_manifest": bool(
            replay_row.get("plan_matches_manifest", False)
        )
        if replay_present
        else False,
    }
    blocking_issues = codex_replay_blockers(requirements)
    return {
        "slot_id": f"{round_dir.name}:{attempt_id}",
        "run_id": round_dir.parent.name,
        "round_id": round_dir.name,
        "attempt_id": attempt_id,
        "attempt_index": int(planned.get("attempt_index", 0)),
        "profile_name": str(planned.get("profile_name", "")),
        "agent_role": str(planned.get("agent_role", "")),
        "adapter_name": str(planned.get("adapter_name", "")),
        "runner_name": str(runner.get("runner_name", "")),
        "execution_enabled": bool(runner.get("execution_enabled", False)),
        "gate_status": "blocked" if blocking_issues else "ready",
        "ready_to_enable": not blocking_issues,
        "blocking_issues": blocking_issues,
        "requirements": requirements,
        "artifacts": {
            "agent_execution": str(execution_path) if execution_path else "",
            "codex_cli_contract_fixture": str(fixture_path) if fixture_present else "",
            "agent_output_quarantine": str(quarantine_path) if quarantine_present else "",
            "round_replay": str(round_dir / "round_replay.json") if replay_present else "",
        },
        "evidence": {
            "execution_status": str(execution.get("status", "")),
            "fixture_failure_code": str(fixture.get("failure_code", "")),
            "quarantine_status": str(quarantine.get("quarantine_status", "")),
            "quarantine_release_to_apply": bool(
                quarantine.get("release_to_apply", False)
            )
            if quarantine_present
            else False,
            "round_replay_failure_code": str(replay_row.get("failure_code", "")),
            "stdin_sha256": str(stdin_summary.get("sha256", "")),
            "fixture_patch_sha256": str(
                object_value(fixture.get("contract", {})).get(
                    "fixture_patch_sha256",
                    "",
                )
            ),
        },
    }


def codex_replay_blockers(requirements: dict[str, bool]) -> list[str]:
    """Return stable blocker codes for a guarded Codex CLI replay gate row."""
    blockers: list[str] = []
    for key, code in (
        ("attempt_saved", "attempt_missing"),
        ("adapter_is_codex_cli", "adapter_not_codex_cli"),
        ("runner_is_guarded_codex_cli", "runner_not_guarded_codex_cli"),
        ("agent_execution_present", "agent_execution_missing"),
        ("agent_execution_not_enabled_yet", "codex_execution_already_enabled"),
        ("stdin_recorded", "stdin_not_recorded"),
        ("mutation_guard_passed", "mutation_guard_failed"),
        ("contract_fixture_present", "contract_fixture_missing"),
        ("contract_fixture_ok", "contract_fixture_failed"),
        ("contract_fixture_prompt_hash_ok", "contract_fixture_prompt_hash_mismatch"),
        ("contract_fixture_stdout_valid", "contract_fixture_stdout_invalid"),
        ("quarantine_present", "quarantine_missing"),
        ("quarantine_policy_ok", "quarantine_policy_invalid"),
        (
            "quarantine_not_released_for_disabled_codex",
            "quarantine_unexpected_release",
        ),
        ("round_replay_present", "round_replay_missing"),
        ("round_replay_ok", "round_replay_failed"),
        ("round_replay_plan_matches_manifest", "round_replay_plan_mismatch"),
    ):
        if not requirements.get(key, False):
            blockers.append(code)
    return blockers


def codex_cli_replay_gate_markdown(payload: dict[str, Any]) -> str:
    """Return a compact markdown Codex CLI replay-gate report."""
    slots = object_rows(payload.get("slots", []))
    lines = [
        "# Codex CLI Replay Gate",
        "",
        f"- Schema: `{payload.get('schema_version', '')}`",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Ready to enable Codex CLI: `{payload.get('ready_to_enable_codex_cli', False)}`",
        f"- Slot count: `{object_value(payload.get('totals', {})).get('slot_count', 0)}`",
        "",
        "## Slots",
    ]
    if not slots:
        lines.append("- none")
    for slot in slots:
        blockers = string_list(slot.get("blocking_issues", []))
        lines.append(
            "- "
            + f"`{slot.get('slot_id', '')}` "
            + f"status=`{slot.get('gate_status', '')}` "
            + f"blockers=`{', '.join(blockers) if blockers else 'none'}`"
        )
    lines.extend(
        [
            "",
            "This gate only reads saved artifacts and does not execute Codex, apply patches, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def round_dirs(run_dir: Path) -> list[Path]:
    """Return round directories in stable order."""
    return sorted(path for path in run_dir.glob("round_*") if path.is_dir())


def object_rows(value: object) -> list[dict[str, Any]]:
    """Return object rows from an arbitrary JSON value."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def rows_by_id(value: object) -> dict[str, dict[str, Any]]:
    """Return rows keyed by attempt id."""
    rows: dict[str, dict[str, Any]] = {}
    for row in object_rows(value):
        attempt_id = str(row.get("attempt_id", ""))
        if attempt_id:
            rows[attempt_id] = row
    return rows


def first_existing_path(repo_root: Path, candidates: list[str]) -> Path | None:
    """Return the first existing candidate path resolved from repo root."""
    for candidate in candidates:
        if not candidate:
            continue
        path = resolve_path(Path(candidate), repo_root)
        if path.exists():
            return path
    return None


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root when needed."""
    return path if path.is_absolute() else repo_root / path


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk, returning an empty object when absent."""
    if not path.exists() or not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: object) -> None:
    """Write deterministic JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def object_value(value: object) -> dict[str, Any]:
    """Return a dict value or an empty dict."""
    return value if isinstance(value, dict) else {}


def string_list(value: object) -> list[str]:
    """Return non-empty string values from a JSON value."""
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, list | tuple):
        return []
    return [str(item) for item in value if str(item)]


def int_value(value: object) -> int:
    """Return an integer value or zero."""
    return value if isinstance(value, int) else 0


def main() -> None:
    """CLI entrypoint for the Codex CLI replay gate."""
    args = parse_args()
    payload = write_codex_cli_replay_gate(
        run_dir=args.run_dir,
        repo_root=args.repo_root,
        output_path=args.output,
        markdown_path=args.markdown_output,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for the Codex CLI replay gate."""
    parser = argparse.ArgumentParser(
        description="Gate guarded Codex CLI enablement using saved replay artifacts.",
    )
    parser.add_argument("run_dir", type=Path, help="Path to an iteration run directory.")
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
        help="Optional path for codex_cli_replay_gate.json.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_replay_gate.md.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
