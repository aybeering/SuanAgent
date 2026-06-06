"""Aggregate Codex CLI safety gates before real strategy execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.codex_cli_dry_invocation_guard import (
    file_record,
    int_value,
    load_json_object,
    object_value,
    relative_path,
    resolve_path,
    string_list,
    write_json,
)


CODEX_CLI_EXECUTION_UNLOCK_GATE_SCHEMA_VERSION = "codex_cli_execution_unlock_gate_v1"


def build_codex_cli_execution_unlock_gate(
    *,
    run_dir: Path,
    config_path: Path,
    repo_root: Path = Path("."),
    canary_run_dir: Path | None = None,
) -> dict[str, Any]:
    """Return the final read-only gate for real Codex CLI strategy execution."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    canary_run_dir = (
        resolve_path(canary_run_dir, repo_root) if canary_run_dir is not None else run_dir
    )
    config_path = resolve_path(config_path, repo_root)
    config = load_json_object(config_path)
    codex_cli = object_value(config.get("codex_cli", {}))
    artifacts = {
        "candidate_config": file_record(config_path, repo_root),
        "codex_cli_replay_gate": file_record(
            run_dir / "codex_cli_replay_gate.json",
            repo_root,
        ),
        "codex_cli_enablement_gate": file_record(
            run_dir / "codex_cli_enablement_gate.json",
            repo_root,
        ),
        "codex_cli_manual_approval": file_record(
            run_dir / "codex_cli_manual_approval.json",
            repo_root,
        ),
        "codex_cli_canary_gate": file_record(
            canary_run_dir / "codex_cli_canary_gate.json",
            repo_root,
        ),
        "codex_cli_real_preflight": file_record(
            run_dir / "codex_cli_real_preflight.json",
            repo_root,
        ),
        "codex_cli_dry_invocation_guard": file_record(
            run_dir / "codex_cli_dry_invocation_guard.json",
            repo_root,
        ),
    }
    replay_gate = load_json_object(run_dir / "codex_cli_replay_gate.json")
    enablement_gate = load_json_object(run_dir / "codex_cli_enablement_gate.json")
    manual_approval = load_json_object(run_dir / "codex_cli_manual_approval.json")
    canary_gate = load_json_object(canary_run_dir / "codex_cli_canary_gate.json")
    real_preflight = load_json_object(run_dir / "codex_cli_real_preflight.json")
    dry_invocation_guard = load_json_object(
        run_dir / "codex_cli_dry_invocation_guard.json"
    )
    canary_intake_binding_ready = canary_gate_intake_binding_ready(canary_gate)
    canary_preflight_binding_ready = canary_gate_preflight_binding_ready(canary_gate)
    config_binding = candidate_config_binding(
        expected_record=artifacts["candidate_config"],
        gate_payloads={
            "codex_cli_enablement_gate": enablement_gate,
            "codex_cli_manual_approval": manual_approval,
            "codex_cli_real_preflight": real_preflight,
            "codex_cli_dry_invocation_guard": dry_invocation_guard,
        },
    )
    checks = {
        "config_exists": config_path.exists() and config_path.is_file(),
        "candidate_config_sha256_present": bool(
            artifacts["candidate_config"].get("sha256", "")
        ),
        "strategy_modifier_is_codex_cli": str(config.get("strategy_modifier", ""))
        == "codex_cli",
        "execute_true_candidate": bool(codex_cli.get("execute", False)),
        "replay_gate_exists": bool(artifacts["codex_cli_replay_gate"]["exists"]),
        "replay_gate_ok": bool(replay_gate.get("ok", False)),
        "replay_gate_ready": bool(replay_gate.get("ready_to_enable_codex_cli", False)),
        "enablement_gate_exists": bool(
            artifacts["codex_cli_enablement_gate"]["exists"]
        ),
        "enablement_gate_ok": bool(enablement_gate.get("ok", False)),
        "enablement_permitted": bool(enablement_gate.get("permitted_to_enable", False)),
        "enablement_candidate_config_matches": gate_binding_matches(
            config_binding,
            "codex_cli_enablement_gate",
        ),
        "manual_approval_exists": bool(
            artifacts["codex_cli_manual_approval"]["exists"]
        ),
        "manual_approval_ok": bool(manual_approval.get("ok", False)),
        "manual_approval_granted": bool(
            manual_approval.get("manual_approval_granted", False)
        ),
        "manual_approval_ready": bool(
            manual_approval.get("ready_for_controlled_codex_cli_execution", False)
        ),
        "manual_approval_candidate_config_matches": gate_binding_matches(
            config_binding,
            "codex_cli_manual_approval",
        ),
        "canary_gate_exists": bool(artifacts["codex_cli_canary_gate"]["exists"]),
        "canary_gate_ok": bool(canary_gate.get("ok", False)),
        "canary_controlled_execution_ready": bool(
            canary_gate.get("controlled_execution_ready", False)
        ),
        "canary_intake_binding_ready": canary_intake_binding_ready,
        "canary_preflight_binding_ready": canary_preflight_binding_ready,
        "real_preflight_exists": bool(artifacts["codex_cli_real_preflight"]["exists"]),
        "real_preflight_ok": bool(real_preflight.get("ok", False)),
        "real_codex_cli_ready": bool(real_preflight.get("real_codex_cli_ready", False)),
        "real_preflight_candidate_config_matches": gate_binding_matches(
            config_binding,
            "codex_cli_real_preflight",
        ),
        "dry_invocation_guard_exists": bool(
            artifacts["codex_cli_dry_invocation_guard"]["exists"]
        ),
        "dry_invocation_guard_ok": bool(dry_invocation_guard.get("ok", False)),
        "dry_invocation_ready": bool(
            dry_invocation_guard.get("dry_invocation_ready", False)
        ),
        "dry_invocation_executed": bool(
            dry_invocation_guard.get("execution_requested", False)
        ),
        "dry_invocation_candidate_config_matches": gate_binding_matches(
            config_binding,
            "codex_cli_dry_invocation_guard",
        ),
        "candidate_config_binding_consistent": bool(config_binding["all_matched"]),
        "does_not_execute_codex_cli": True,
        "does_not_apply_patches": True,
        "does_not_change_acceptance": True,
        "deterministic_code_keeps_acceptance_authority": True,
    }
    blocking_reasons = unlock_blockers(checks)
    unlocked = not blocking_reasons
    return {
        "schema_version": CODEX_CLI_EXECUTION_UNLOCK_GATE_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "canary_run_dir": str(canary_run_dir),
        "config_path": relative_path(config_path, repo_root),
        "ok": True,
        "real_codex_execution_unlocked": unlocked,
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
        },
        "gate_status": {
            "codex_cli_replay_gate": gate_summary(
                replay_gate,
                "ready_to_enable_codex_cli",
            ),
            "codex_cli_enablement_gate": gate_summary(
                enablement_gate,
                "permitted_to_enable",
            ),
            "codex_cli_manual_approval": gate_summary(
                manual_approval,
                "ready_for_controlled_codex_cli_execution",
            ),
            "codex_cli_canary_gate": gate_summary(
                canary_gate,
                "controlled_execution_ready",
            ),
            "codex_cli_real_preflight": gate_summary(
                real_preflight,
                "real_codex_cli_ready",
            ),
            "codex_cli_dry_invocation_guard": gate_summary(
                dry_invocation_guard,
                "dry_invocation_ready",
            ),
        },
        "config_binding": config_binding,
        "artifacts": artifacts,
        "policy": {
            "unlock_gate_only": True,
            "read_only": True,
            "does_not_execute_codex_cli": True,
            "does_not_send_strategy_prompt": True,
            "does_not_modify_config": True,
            "does_not_select_candidate": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
            "requires_replay_gate": True,
            "requires_enablement_gate": True,
            "requires_manual_approval": True,
            "requires_controlled_canary": True,
            "requires_canary_intake_binding": True,
            "requires_canary_preflight_binding": True,
            "requires_real_preflight": True,
            "requires_successful_dry_invocation": True,
            "requires_candidate_config_hash_binding": True,
            "deterministic_code_keeps_acceptance_authority": True,
        },
    }


def write_codex_cli_execution_unlock_gate(
    *,
    run_dir: Path,
    config_path: Path,
    repo_root: Path = Path("."),
    canary_run_dir: Path | None = None,
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    """Write JSON and markdown Codex CLI execution unlock artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_codex_cli_execution_unlock_gate(
        run_dir=run_dir,
        config_path=config_path,
        repo_root=repo_root,
        canary_run_dir=canary_run_dir,
    )
    destination = output_path or run_dir / "codex_cli_execution_unlock_gate.json"
    write_json(destination, payload)
    markdown_destination = markdown_path or run_dir / "codex_cli_execution_unlock_gate.md"
    markdown_destination.write_text(
        codex_cli_execution_unlock_gate_markdown(payload),
        encoding="utf-8",
    )
    return payload


def gate_summary(payload: dict[str, Any], ready_key: str) -> dict[str, Any]:
    """Return compact state for one upstream gate."""
    return {
        "schema_version": str(payload.get("schema_version", "")),
        "ok": bool(payload.get("ok", False)),
        "ready": bool(payload.get(ready_key, False)),
        "blocking_reasons": string_list(payload.get("blocking_reasons", [])),
    }


def candidate_config_binding(
    *,
    expected_record: dict[str, object],
    gate_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return sha256 binding evidence for candidate-config-bearing gates."""
    expected_path = str(expected_record.get("path", ""))
    expected_sha256 = str(expected_record.get("sha256", ""))
    gates: dict[str, dict[str, Any]] = {}
    for gate_name, payload in gate_payloads.items():
        artifacts = object_value(payload.get("artifacts", {}))
        record = object_value(artifacts.get("candidate_config", {}))
        path = str(record.get("path", ""))
        sha256 = str(record.get("sha256", ""))
        exists = bool(record.get("exists", False))
        gates[gate_name] = {
            "exists": exists,
            "path": path,
            "sha256": sha256,
            "matches_expected_path": exists and path == expected_path,
            "matches_expected_sha256": exists
            and bool(expected_sha256)
            and sha256 == expected_sha256,
            "matches_expected": exists
            and path == expected_path
            and bool(expected_sha256)
            and sha256 == expected_sha256,
        }
    matched = [name for name, gate in gates.items() if gate["matches_expected"]]
    missing = [name for name, gate in gates.items() if not gate["exists"]]
    mismatched = [
        name
        for name, gate in gates.items()
        if gate["exists"] and not gate["matches_expected"]
    ]
    return {
        "expected_config_path": expected_path,
        "expected_config_sha256": expected_sha256,
        "gates": gates,
        "matched_gate_names": matched,
        "missing_gate_names": missing,
        "mismatched_gate_names": mismatched,
        "all_matched": bool(expected_sha256) and not missing and not mismatched,
    }


def gate_binding_matches(binding: dict[str, Any], gate_name: str) -> bool:
    """Return whether one upstream gate is bound to the expected candidate config."""
    gate = object_value(object_value(binding.get("gates", {})).get(gate_name, {}))
    return bool(gate.get("matches_expected", False))


def canary_gate_intake_binding_ready(canary_gate: dict[str, Any]) -> bool:
    """Return whether every canary slot proves selected output-intake binding."""
    slots = canary_gate.get("slots", [])
    if not isinstance(slots, list) or not slots:
        return False
    for slot in slots:
        if not isinstance(slot, dict):
            return False
        requirements = object_value(slot.get("requirements", {}))
        if not bool(requirements.get("intake_binding_bound", False)):
            return False
        if not bool(requirements.get("intake_binding_clean", False)):
            return False
    return True


def canary_gate_preflight_binding_ready(canary_gate: dict[str, Any]) -> bool:
    """Return whether every canary slot proves startup-preflight binding."""
    slots = canary_gate.get("slots", [])
    if not isinstance(slots, list) or not slots:
        return False
    for slot in slots:
        if not isinstance(slot, dict):
            return False
        requirements = object_value(slot.get("requirements", {}))
        if not bool(requirements.get("preflight_binding_bound", False)):
            return False
        if not bool(requirements.get("preflight_binding_clean", False)):
            return False
    return True


def unlock_blockers(checks: dict[str, bool]) -> list[str]:
    """Return stable blocker codes for real Codex CLI execution unlock."""
    blockers: list[str] = []
    for key, code in (
        ("config_exists", "config_missing"),
        ("candidate_config_sha256_present", "candidate_config_sha256_missing"),
        ("strategy_modifier_is_codex_cli", "strategy_modifier_not_codex_cli"),
        ("execute_true_candidate", "execute_not_true_candidate"),
        ("replay_gate_exists", "replay_gate_missing"),
        ("replay_gate_ok", "replay_gate_not_ok"),
        ("replay_gate_ready", "replay_gate_not_ready"),
        ("enablement_gate_exists", "enablement_gate_missing"),
        ("enablement_gate_ok", "enablement_gate_not_ok"),
        ("enablement_permitted", "enablement_not_permitted"),
        (
            "enablement_candidate_config_matches",
            "enablement_candidate_config_mismatch",
        ),
        ("manual_approval_exists", "manual_approval_missing"),
        ("manual_approval_ok", "manual_approval_not_ok"),
        ("manual_approval_granted", "manual_approval_not_granted"),
        ("manual_approval_ready", "manual_approval_not_ready"),
        (
            "manual_approval_candidate_config_matches",
            "manual_approval_candidate_config_mismatch",
        ),
        ("canary_gate_exists", "canary_gate_missing"),
        ("canary_gate_ok", "canary_gate_not_ok"),
        (
            "canary_controlled_execution_ready",
            "canary_controlled_execution_not_ready",
        ),
        ("canary_intake_binding_ready", "canary_intake_binding_not_ready"),
        ("canary_preflight_binding_ready", "canary_preflight_binding_not_ready"),
        ("real_preflight_exists", "real_preflight_missing"),
        ("real_preflight_ok", "real_preflight_not_ok"),
        ("real_codex_cli_ready", "real_codex_cli_not_ready"),
        (
            "real_preflight_candidate_config_matches",
            "real_preflight_candidate_config_mismatch",
        ),
        ("dry_invocation_guard_exists", "dry_invocation_guard_missing"),
        ("dry_invocation_guard_ok", "dry_invocation_guard_not_ok"),
        ("dry_invocation_ready", "dry_invocation_not_ready"),
        ("dry_invocation_executed", "dry_invocation_not_executed"),
        (
            "dry_invocation_candidate_config_matches",
            "dry_invocation_candidate_config_mismatch",
        ),
        ("candidate_config_binding_consistent", "candidate_config_binding_mismatch"),
        ("does_not_execute_codex_cli", "unlock_gate_executed_codex_cli"),
        ("does_not_apply_patches", "unlock_gate_applied_patch"),
        ("does_not_change_acceptance", "unlock_gate_changed_acceptance"),
        (
            "deterministic_code_keeps_acceptance_authority",
            "deterministic_authority_missing",
        ),
    ):
        if not checks.get(key, False):
            blockers.append(code)
    return blockers


def codex_cli_execution_unlock_gate_markdown(payload: dict[str, Any]) -> str:
    """Return compact markdown for the final execution unlock gate."""
    blockers = string_list(payload.get("blocking_reasons", []))
    lines = [
        "# Codex CLI Execution Unlock Gate",
        "",
        f"- Schema: `{payload.get('schema_version', '')}`",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Report OK: `{payload.get('ok', False)}`",
        f"- Real Codex execution unlocked: `{payload.get('real_codex_execution_unlocked', False)}`",
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
            "This gate is read-only. It aggregates existing safety evidence and does not execute Codex CLI, send a strategy prompt, apply patches, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    """CLI entrypoint for Codex CLI execution unlock gate."""
    args = parse_args()
    payload = write_codex_cli_execution_unlock_gate(
        run_dir=args.run_dir,
        config_path=args.config,
        repo_root=args.repo_root,
        canary_run_dir=args.canary_run_dir,
        output_path=args.output,
        markdown_path=args.markdown_output,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for the final execution unlock gate."""
    parser = argparse.ArgumentParser(
        description="Aggregate read-only Codex CLI gates before real execution.",
    )
    parser.add_argument("run_dir", type=Path, help="Path to a guarded run directory.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/codex_cli_enable_candidate.json"),
        help="Candidate config that declares the real Codex CLI executable.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root used to resolve paths.",
    )
    parser.add_argument(
        "--canary-run-dir",
        type=Path,
        default=None,
        help="Optional separate run directory that contains codex_cli_canary_gate.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_execution_unlock_gate.json.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_execution_unlock_gate.md.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
