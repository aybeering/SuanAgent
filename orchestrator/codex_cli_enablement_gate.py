"""Gate a candidate config that would enable guarded Codex CLI execution."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.schema_validation import validate_json_file


CODEX_CLI_ENABLEMENT_GATE_SCHEMA_VERSION = "codex_cli_enablement_gate_v1"
SCHEMA_PATH = Path("schemas/codex_cli_enablement_gate.schema.json")


def build_codex_cli_enablement_gate(
    *,
    run_dir: Path,
    config_path: Path,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Return a deterministic gate report for a Codex execute=true config."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    config_path = resolve_path(config_path, repo_root)
    replay_gate_path = run_dir / "codex_cli_replay_gate.json"
    replay_gate = load_json_object(replay_gate_path)
    config = load_json_object(config_path)
    codex_cli = object_value(config.get("codex_cli", {}))
    enablement = object_value(config.get("codex_cli_enablement", {}))
    checks = {
        "config_exists": config_path.exists() and config_path.is_file(),
        "strategy_modifier_is_codex_cli": str(config.get("strategy_modifier", "")) == "codex_cli",
        "execute_true": bool(codex_cli.get("execute", False)),
        "sandbox_workspace_write": str(codex_cli.get("sandbox", "")) == "workspace-write",
        "workspace_root_declared": bool(str(codex_cli.get("workspace_root", ""))),
        "timeout_positive": int_value(codex_cli.get("timeout_seconds", 0)) > 0,
        "candidate_only_declared": bool(enablement.get("candidate_only", False)),
        "manual_confirmation_required": bool(
            enablement.get("manual_confirmation_required", False)
        ),
        "requires_replay_gate_declared": bool(
            enablement.get("requires_codex_cli_replay_gate", False)
        ),
        "replay_gate_present": bool(replay_gate),
        "replay_gate_ready": bool(replay_gate.get("ready_to_enable_codex_cli", False)),
        "replay_gate_ok": bool(replay_gate.get("ok", False)),
        "source_artifact_hashes_recorded": (
            bool(file_record(replay_gate_path, repo_root).get("sha256", ""))
            and bool(file_record(config_path, repo_root).get("sha256", ""))
        ),
    }
    blocking_reasons = enablement_blockers(checks)
    permitted = not blocking_reasons
    return {
        "schema_version": CODEX_CLI_ENABLEMENT_GATE_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "config_path": relative_path(config_path, repo_root),
        "ok": permitted,
        "permitted_to_enable": permitted,
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
            "enablement": {
                "candidate_only": bool(enablement.get("candidate_only", False)),
                "requires_codex_cli_replay_gate": bool(
                    enablement.get("requires_codex_cli_replay_gate", False)
                ),
                "manual_confirmation_required": bool(
                    enablement.get("manual_confirmation_required", False)
                ),
                "does_not_run_in_ci": bool(enablement.get("does_not_run_in_ci", False)),
            },
        },
        "artifacts": {
            "codex_cli_replay_gate": file_record(replay_gate_path, repo_root),
            "candidate_config": file_record(config_path, repo_root),
        },
        "replay_gate": {
            "schema_version": str(replay_gate.get("schema_version", "")),
            "ok": bool(replay_gate.get("ok", False)),
            "ready_to_enable_codex_cli": bool(
                replay_gate.get("ready_to_enable_codex_cli", False)
            ),
            "blocked_count": int_value(
                object_value(replay_gate.get("totals", {})).get("blocked_count", 0)
            ),
            "slot_count": int_value(
                object_value(replay_gate.get("totals", {})).get("slot_count", 0)
            ),
        },
        "policy": {
            "gate_only": True,
            "does_not_execute_codex_cli": True,
            "does_not_modify_config": True,
            "does_not_select_candidate": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
            "requires_replay_gate_ready": True,
            "requires_manual_confirmation": True,
            "requires_source_artifact_hash_match": True,
            "deterministic_code_keeps_acceptance_authority": True,
        },
    }


def write_codex_cli_enablement_gate(
    *,
    run_dir: Path,
    config_path: Path,
    repo_root: Path = Path("."),
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    """Write JSON and markdown Codex CLI enablement gate artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_codex_cli_enablement_gate(
        run_dir=run_dir,
        config_path=config_path,
        repo_root=repo_root,
    )
    destination = output_path or run_dir / "codex_cli_enablement_gate.json"
    write_json(destination, payload)
    markdown_destination = markdown_path or run_dir / "codex_cli_enablement_gate.md"
    markdown_destination.write_text(
        codex_cli_enablement_gate_markdown(payload),
        encoding="utf-8",
    )
    return payload


def validate_codex_cli_enablement_gate_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
    schema_path: Path | None = None,
    require_current_evidence: bool = True,
) -> tuple[str, ...]:
    """Validate a saved Codex CLI enablement gate against schema and evidence."""
    repo_root = repo_root.resolve()
    schema_errors = tuple(
        validate_json_file(
            payload_path=payload_path,
            schema_path=schema_path or repo_root / SCHEMA_PATH,
        )
    )
    if schema_errors or not require_current_evidence:
        return schema_errors
    payload = load_json_object(payload_path)
    run_dir_value = str(payload.get("run_dir", ""))
    config_path_value = str(payload.get("config_path", ""))
    if not run_dir_value:
        return schema_errors + ("codex_cli_enablement_gate run_dir required",)
    if not config_path_value:
        return schema_errors + ("codex_cli_enablement_gate config_path required",)
    expected = build_codex_cli_enablement_gate(
        run_dir=resolve_path(Path(run_dir_value), repo_root),
        config_path=resolve_path(Path(config_path_value), repo_root),
        repo_root=repo_root,
    )
    if payload != expected:
        return schema_errors + ("codex_cli_enablement_gate current evidence mismatch",)
    return schema_errors


def enablement_blockers(checks: dict[str, bool]) -> list[str]:
    """Return stable blocker codes for enablement checks."""
    blockers: list[str] = []
    for key, code in (
        ("config_exists", "config_missing"),
        ("strategy_modifier_is_codex_cli", "strategy_modifier_not_codex_cli"),
        ("execute_true", "execute_not_true"),
        ("sandbox_workspace_write", "sandbox_not_workspace_write"),
        ("workspace_root_declared", "workspace_root_missing"),
        ("timeout_positive", "timeout_not_positive"),
        ("candidate_only_declared", "candidate_only_not_declared"),
        ("manual_confirmation_required", "manual_confirmation_not_required"),
        ("requires_replay_gate_declared", "replay_gate_requirement_not_declared"),
        ("replay_gate_present", "replay_gate_missing"),
        ("replay_gate_ready", "replay_gate_not_ready"),
        ("replay_gate_ok", "replay_gate_not_ok"),
        ("source_artifact_hashes_recorded", "source_artifact_hash_missing"),
    ):
        if not checks.get(key, False):
            blockers.append(code)
    return blockers


def codex_cli_enablement_gate_markdown(payload: dict[str, Any]) -> str:
    """Return compact markdown for the enablement gate."""
    blockers = string_list(payload.get("blocking_reasons", []))
    config = object_value(payload.get("config", {}))
    codex = object_value(config.get("codex_cli", {}))
    lines = [
        "# Codex CLI Enablement Gate",
        "",
        f"- Schema: `{payload.get('schema_version', '')}`",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Permitted to enable: `{payload.get('permitted_to_enable', False)}`",
        f"- Config: `{payload.get('config_path', '')}`",
        f"- Execute: `{codex.get('execute', False)}`",
        "",
        "## Blocking Reasons",
    ]
    lines.extend(f"- {reason}" for reason in blockers)
    if not blockers:
        lines.append("- none")
    lines.extend(
        [
            "",
            "This gate only checks saved artifacts and a candidate config; it does not execute Codex or modify configuration.",
            "",
        ]
    )
    return "\n".join(lines)


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
    """CLI entrypoint for Codex CLI enablement gate."""
    args = parse_args()
    payload = write_codex_cli_enablement_gate(
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
    """Parse CLI args for Codex CLI enablement gate."""
    parser = argparse.ArgumentParser(
        description="Gate a candidate config before enabling guarded Codex CLI.",
    )
    parser.add_argument("run_dir", type=Path, help="Path to an iteration run directory.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/codex_cli_enable_candidate.json"),
        help="Candidate config that explicitly sets codex_cli.execute=true.",
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
        help="Optional path for codex_cli_enablement_gate.json.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_enablement_gate.md.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
