"""Gate a controlled local Codex CLI canary execution."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


CODEX_CLI_CANARY_GATE_SCHEMA_VERSION = "codex_cli_canary_gate_v1"
EXPECTED_CANARY_EXECUTABLE = "agents/codex_cli_canary.py"
EXPECTED_DIRECTION_TAG = "codex_cli_canary_lower_min_edge"
OLD_THRESHOLD = "MIN_EDGE = 0.05"


def build_codex_cli_canary_gate(
    *,
    run_dir: Path,
    config_path: Path,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Return a deterministic gate report for a local Codex CLI canary run."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    config_path = resolve_path(config_path, repo_root)
    config = load_json_object(config_path)
    manifest = load_json_object(run_dir / "manifest.json")
    canary_config = object_value(config.get("codex_cli_canary", {}))
    codex_cli = object_value(config.get("codex_cli", {}))
    round_ids = round_ids_from_manifest(manifest)
    slots = [
        canary_slot(
            run_dir=run_dir,
            round_id=round_id,
            repo_root=repo_root,
            expected_executable=str(
                canary_config.get("expected_executable", EXPECTED_CANARY_EXECUTABLE)
            ),
            expected_direction_tag=str(
                canary_config.get("expected_direction_tag", EXPECTED_DIRECTION_TAG)
            ),
        )
        for round_id in round_ids
    ]
    strategy_path = repo_root / str(config.get("strategy_path", ""))
    checks = {
        "config_exists": config_path.exists() and config_path.is_file(),
        "strategy_modifier_is_codex_cli": str(config.get("strategy_modifier", ""))
        == "codex_cli",
        "canary_enabled": bool(canary_config.get("enabled", False)),
        "local_fixture_only": bool(canary_config.get("local_fixture_only", False)),
        "real_codex_cli_false": canary_config.get("real_codex_cli", None) is False,
        "execute_true": bool(codex_cli.get("execute", False)),
        "executable_is_canary": str(codex_cli.get("executable", ""))
        == str(canary_config.get("expected_executable", EXPECTED_CANARY_EXECUTABLE)),
        "manifest_present": bool(manifest),
        "rounds_present": bool(round_ids),
        "all_slots_ready": bool(slots) and all(slot["ready"] for slot in slots),
        "strategy_rolled_back": strategy_path.exists()
        and OLD_THRESHOLD in strategy_path.read_text(encoding="utf-8"),
    }
    blocking_reasons = canary_blockers(checks)
    ok = not blocking_reasons
    return {
        "schema_version": CODEX_CLI_CANARY_GATE_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "config_path": relative_path(config_path, repo_root),
        "ok": ok,
        "controlled_execution_ready": ok,
        "blocking_reasons": blocking_reasons,
        "checks": checks,
        "config": {
            "strategy_modifier": str(config.get("strategy_modifier", "")),
            "codex_cli": {
                "executable": str(codex_cli.get("executable", "")),
                "model": str(codex_cli.get("model", "")),
                "sandbox": str(codex_cli.get("sandbox", "")),
                "workspace_root": str(codex_cli.get("workspace_root", "")),
                "execute": bool(codex_cli.get("execute", False)),
                "timeout_seconds": int_value(codex_cli.get("timeout_seconds", 0)),
            },
            "canary": {
                "enabled": bool(canary_config.get("enabled", False)),
                "local_fixture_only": bool(
                    canary_config.get("local_fixture_only", False)
                ),
                "real_codex_cli": bool(canary_config.get("real_codex_cli", True)),
                "expected_executable": str(
                    canary_config.get(
                        "expected_executable",
                        EXPECTED_CANARY_EXECUTABLE,
                    )
                ),
                "expected_direction_tag": str(
                    canary_config.get(
                        "expected_direction_tag",
                        EXPECTED_DIRECTION_TAG,
                    )
                ),
                "expected_final_decision": str(
                    canary_config.get("expected_final_decision", "")
                ),
                "requires_quarantine_release": bool(
                    canary_config.get("requires_quarantine_release", False)
                ),
                "requires_strategy_rollback": bool(
                    canary_config.get("requires_strategy_rollback", False)
                ),
            },
        },
        "totals": {
            "round_count": len(slots),
            "ready_count": sum(1 for slot in slots if slot["ready"]),
            "blocked_count": sum(1 for slot in slots if not slot["ready"]),
        },
        "slots": slots,
        "artifacts": {
            "manifest": file_record(run_dir / "manifest.json", repo_root),
            "candidate_config": file_record(config_path, repo_root),
            "strategy_file": file_record(strategy_path, repo_root),
        },
        "policy": {
            "gate_only": True,
            "executes_only_checked_in_canary": True,
            "does_not_execute_real_codex_cli": True,
            "does_not_modify_config": True,
            "does_not_select_candidate": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
            "requires_guarded_execution_audit": True,
            "requires_intake_binding": True,
            "requires_quarantine_release": True,
            "requires_deterministic_reject_and_rollback": True,
            "deterministic_code_keeps_acceptance_authority": True,
        },
    }


def write_codex_cli_canary_gate(
    *,
    run_dir: Path,
    config_path: Path,
    repo_root: Path = Path("."),
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    """Write JSON and markdown Codex CLI canary gate artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_codex_cli_canary_gate(
        run_dir=run_dir,
        config_path=config_path,
        repo_root=repo_root,
    )
    destination = output_path or run_dir / "codex_cli_canary_gate.json"
    write_json(destination, payload)
    markdown_destination = markdown_path or run_dir / "codex_cli_canary_gate.md"
    markdown_destination.write_text(
        codex_cli_canary_gate_markdown(payload),
        encoding="utf-8",
    )
    return payload


def canary_slot(
    *,
    run_dir: Path,
    round_id: str,
    repo_root: Path,
    expected_executable: str,
    expected_direction_tag: str,
) -> dict[str, Any]:
    """Return one round-level canary slot audit."""
    round_dir = run_dir / round_id
    execution_path = round_dir / "agent_executions/attempt_001_primary.json"
    execution = load_json_object(execution_path)
    quarantine_path = round_dir / "agent_output_quarantine.json"
    quarantine = load_json_object(quarantine_path)
    proposal_path = round_dir / "proposal.json"
    proposal = load_json_object(proposal_path)
    validation_path = round_dir / "agent_validation.json"
    validation = load_json_object(validation_path)
    decision_path = round_dir / "decision.json"
    decision = load_json_object(decision_path)
    command = string_list(execution.get("command", []))
    mutation_guard = object_value(execution.get("mutation_guard", {}))
    intake_binding = object_value(execution.get("intake_binding", {}))
    intake_binding_blockers = string_list(intake_binding.get("blocking_reasons", []))
    requirements = {
        "execution_audit_present": bool(execution),
        "runner_is_guarded_codex_cli": str(execution.get("runner_name", ""))
        == "codex_cli_guarded_adapter",
        "adapter_is_codex_cli": str(execution.get("adapter_name", "")) == "codex_cli",
        "execution_enabled": bool(execution.get("execution_enabled", False)),
        "execution_completed": str(execution.get("status", "")) == "completed",
        "returncode_zero": execution.get("returncode") == 0,
        "command_is_canary": bool(command) and command[0] == expected_executable,
        "stdout_recorded": int_value(object_value(execution.get("stdout", {})).get("chars", 0))
        > 0,
        "stdin_recorded": int_value(object_value(execution.get("stdin", {})).get("chars", 0))
        > 0,
        "mutation_guard_passed": bool(mutation_guard.get("passed", False)),
        "intake_binding_bound": bool(intake_binding.get("bound", False)),
        "intake_binding_clean": not intake_binding_blockers,
        "proposal_applicable": bool(proposal.get("applicable", False)),
        "proposal_direction_matches": str(proposal.get("direction_tag", ""))
        == expected_direction_tag,
        "agent_validation_ok": bool(validation.get("ok", False)),
        "quarantine_released": bool(quarantine.get("release_to_apply", False)),
        "decision_present": bool(decision),
        "decision_rejected": bool(decision) and not bool(decision.get("accepted", True)),
    }
    blocking_issues = [
        code
        for key, code in (
            ("execution_audit_present", "execution_audit_missing"),
            ("runner_is_guarded_codex_cli", "runner_not_guarded_codex_cli"),
            ("adapter_is_codex_cli", "adapter_not_codex_cli"),
            ("execution_enabled", "execution_not_enabled"),
            ("execution_completed", "execution_not_completed"),
            ("returncode_zero", "returncode_not_zero"),
            ("command_is_canary", "command_not_canary"),
            ("stdout_recorded", "stdout_missing"),
            ("stdin_recorded", "stdin_missing"),
            ("mutation_guard_passed", "mutation_guard_failed"),
            ("intake_binding_bound", "intake_binding_not_bound"),
            ("intake_binding_clean", "intake_binding_has_blockers"),
            ("proposal_applicable", "proposal_not_applicable"),
            ("proposal_direction_matches", "proposal_direction_mismatch"),
            ("agent_validation_ok", "agent_validation_failed"),
            ("quarantine_released", "quarantine_not_released"),
            ("decision_present", "decision_missing"),
            ("decision_rejected", "decision_not_rejected"),
        )
        if not requirements.get(key, False)
    ]
    ready = not blocking_issues
    return {
        "slot_id": f"{round_id}:attempt_001_primary",
        "round_id": round_id,
        "attempt_id": "attempt_001_primary",
        "ready": ready,
        "gate_status": "ready" if ready else "blocked",
        "blocking_issues": blocking_issues,
        "requirements": requirements,
        "evidence": {
            "execution_status": str(execution.get("status", "")),
            "execution_enabled": bool(execution.get("execution_enabled", False)),
            "returncode": execution.get("returncode"),
            "command": command,
            "stdout_sha256": str(object_value(execution.get("stdout", {})).get("sha256", "")),
            "stdin_sha256": str(object_value(execution.get("stdin", {})).get("sha256", "")),
            "mutation_errors": string_list(execution.get("mutation_errors", [])),
            "intake_binding_status": str(intake_binding.get("status", "")),
            "intake_binding_bound": bool(intake_binding.get("bound", False)),
            "intake_binding_blocking_reasons": intake_binding_blockers,
            "quarantine_status": str(quarantine.get("quarantine_status", "")),
            "release_to_apply": bool(quarantine.get("release_to_apply", False)),
            "proposal_direction_tag": str(proposal.get("direction_tag", "")),
            "decision_accepted": bool(decision.get("accepted", False)),
        },
        "artifacts": {
            "agent_execution": relative_path(execution_path, repo_root),
            "agent_output_quarantine": relative_path(quarantine_path, repo_root),
            "proposal": relative_path(proposal_path, repo_root),
            "agent_validation": relative_path(validation_path, repo_root),
            "decision": relative_path(decision_path, repo_root),
        },
    }


def canary_blockers(checks: dict[str, bool]) -> list[str]:
    """Return stable blocker codes for canary checks."""
    blockers: list[str] = []
    for key, code in (
        ("config_exists", "config_missing"),
        ("strategy_modifier_is_codex_cli", "strategy_modifier_not_codex_cli"),
        ("canary_enabled", "canary_not_enabled"),
        ("local_fixture_only", "local_fixture_only_not_declared"),
        ("real_codex_cli_false", "real_codex_cli_not_false"),
        ("execute_true", "execute_not_true"),
        ("executable_is_canary", "executable_not_canary"),
        ("manifest_present", "manifest_missing"),
        ("rounds_present", "rounds_missing"),
        ("all_slots_ready", "slot_not_ready"),
        ("strategy_rolled_back", "strategy_not_rolled_back"),
    ):
        if not checks.get(key, False):
            blockers.append(code)
    return blockers


def codex_cli_canary_gate_markdown(payload: dict[str, Any]) -> str:
    """Return compact markdown for the canary gate."""
    blockers = string_list(payload.get("blocking_reasons", []))
    totals = object_value(payload.get("totals", {}))
    lines = [
        "# Codex CLI Canary Gate",
        "",
        f"- Schema: `{payload.get('schema_version', '')}`",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Controlled execution ready: `{payload.get('controlled_execution_ready', False)}`",
        f"- Ready slots: `{totals.get('ready_count', 0)}/{totals.get('round_count', 0)}`",
        f"- Config: `{payload.get('config_path', '')}`",
        "",
        "## Blocking Reasons",
    ]
    lines.extend(f"- {reason}" for reason in blockers)
    if not blockers:
        lines.append("- none")
    lines.extend(
        [
            "",
            "This gate validates a checked-in local canary executable only; it does not execute real Codex or alter acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def round_ids_from_manifest(manifest: dict[str, Any]) -> list[str]:
    """Return stable round ids from an iteration manifest."""
    rounds = manifest.get("rounds", [])
    if not isinstance(rounds, list):
        return []
    result: list[str] = []
    for item in rounds:
        if isinstance(item, str) and item:
            result.append(item)
        elif isinstance(item, dict) and str(item.get("round_id", "")):
            result.append(str(item["round_id"]))
    return result


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object, returning an empty object when missing."""
    if not path.exists() or not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def file_record(path: Path, repo_root: Path) -> dict[str, object]:
    """Return deterministic metadata for a file artifact."""
    if not path.exists() or not path.is_file():
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


def write_json(path: Path, payload: object) -> None:
    """Write deterministic JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def object_value(value: object) -> dict[str, Any]:
    """Return a dict value or an empty dict."""
    return value if isinstance(value, dict) else {}


def string_list(value: object) -> list[str]:
    """Return non-empty strings from a JSON value."""
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, list | tuple):
        return []
    return [str(item) for item in value if str(item)]


def int_value(value: object) -> int:
    """Return an integer value or zero."""
    return value if isinstance(value, int) else 0


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root when needed."""
    return path if path.is_absolute() else repo_root / path


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> None:
    """CLI entrypoint for Codex CLI canary gate."""
    args = parse_args()
    payload = write_codex_cli_canary_gate(
        run_dir=args.run_dir,
        config_path=args.config,
        repo_root=args.repo_root,
        output_path=args.output,
        markdown_path=args.markdown_output,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for Codex CLI canary gate."""
    parser = argparse.ArgumentParser(
        description="Gate a controlled local Codex CLI canary execution.",
    )
    parser.add_argument("run_dir", type=Path, help="Path to an iteration run directory.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/codex_cli_canary.json"),
        help="Canary config with codex_cli.execute=true and a local fixture executable.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root used to resolve paths.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_canary_gate.json.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_canary_gate.md.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
