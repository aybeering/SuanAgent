"""Freeze Codex CLI execution unlock evidence as a deterministic snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.codex_cli_dry_invocation_guard import (
    file_record,
    load_json_object,
    object_value,
    relative_path,
    resolve_path,
    sha256_text,
    string_list,
    write_json,
)


CODEX_CLI_EXECUTION_UNLOCK_SNAPSHOT_SCHEMA_VERSION = (
    "codex_cli_execution_unlock_snapshot_v1"
)


def build_codex_cli_execution_unlock_snapshot(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Return a read-only evidence snapshot for the latest execution unlock gate."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    unlock_gate_path = run_dir / "codex_cli_execution_unlock_gate.json"
    unlock_gate = load_json_object(unlock_gate_path)
    artifacts = object_value(unlock_gate.get("artifacts", {}))
    evidence_artifacts = {
        key: normalize_file_record(record)
        for key, record in artifacts.items()
        if isinstance(record, dict)
    }
    snapshot_core = {
        "source_gate": file_record(unlock_gate_path, repo_root),
        "real_codex_execution_unlocked": bool(
            unlock_gate.get("real_codex_execution_unlocked", False)
        ),
        "blocking_reasons": string_list(unlock_gate.get("blocking_reasons", [])),
        "checks": object_value(unlock_gate.get("checks", {})),
        "gate_status": object_value(unlock_gate.get("gate_status", {})),
        "config_binding": object_value(unlock_gate.get("config_binding", {})),
        "evidence_artifacts": evidence_artifacts,
    }
    snapshot_digest = stable_digest(snapshot_core)
    return {
        "schema_version": CODEX_CLI_EXECUTION_UNLOCK_SNAPSHOT_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "ok": bool(unlock_gate),
        "source_gate_path": relative_path(unlock_gate_path, repo_root),
        "snapshot_digest": snapshot_digest,
        **snapshot_core,
        "policy": {
            "snapshot_only": True,
            "read_only": True,
            "does_not_execute_codex_cli": True,
            "does_not_send_strategy_prompt": True,
            "does_not_modify_config": True,
            "does_not_select_candidate": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
            "freezes_unlock_gate_sha256": True,
            "freezes_evidence_artifact_sha256": True,
            "deterministic_code_keeps_acceptance_authority": True,
        },
    }


def write_codex_cli_execution_unlock_snapshot(
    *,
    run_dir: Path,
    repo_root: Path = Path("."),
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    """Write JSON and markdown execution unlock snapshot artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_codex_cli_execution_unlock_snapshot(
        run_dir=run_dir,
        repo_root=repo_root,
    )
    destination = output_path or run_dir / "codex_cli_execution_unlock_snapshot.json"
    write_json(destination, payload)
    markdown_destination = markdown_path or (
        run_dir / "codex_cli_execution_unlock_snapshot.md"
    )
    markdown_destination.write_text(
        codex_cli_execution_unlock_snapshot_markdown(payload),
        encoding="utf-8",
    )
    return payload


def normalize_file_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return only stable file-record fields for snapshot evidence."""
    byte_count = record.get("bytes", 0)
    return {
        "exists": bool(record.get("exists", False)),
        "path": str(record.get("path", "")),
        "bytes": byte_count if isinstance(byte_count, int) else 0,
        "sha256": str(record.get("sha256", "")),
    }


def stable_digest(payload: object) -> str:
    """Return a stable digest for one JSON-compatible payload."""
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_text(encoded)


def codex_cli_execution_unlock_snapshot_markdown(payload: dict[str, Any]) -> str:
    """Return compact markdown for the execution unlock evidence snapshot."""
    blockers = string_list(payload.get("blocking_reasons", []))
    lines = [
        "# Codex CLI Execution Unlock Snapshot",
        "",
        f"- Schema: `{payload.get('schema_version', '')}`",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Report OK: `{payload.get('ok', False)}`",
        f"- Real Codex execution unlocked: `{payload.get('real_codex_execution_unlocked', False)}`",
        f"- Snapshot digest: `{payload.get('snapshot_digest', '')}`",
        f"- Source gate: `{payload.get('source_gate_path', '')}`",
        "",
        "## Blocking Reasons",
    ]
    lines.extend(f"- {reason}" for reason in blockers)
    if not blockers:
        lines.append("- none")
    lines.extend(
        [
            "",
            "This snapshot freezes unlock evidence hashes. It is read-only and does not execute Codex CLI, apply patches, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    """CLI entrypoint for Codex CLI execution unlock snapshots."""
    args = parse_args()
    payload = write_codex_cli_execution_unlock_snapshot(
        run_dir=args.run_dir,
        repo_root=args.repo_root,
        output_path=args.output,
        markdown_path=args.markdown_output,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for execution unlock snapshots."""
    parser = argparse.ArgumentParser(
        description="Freeze read-only Codex CLI execution unlock evidence.",
    )
    parser.add_argument("run_dir", type=Path, help="Path to a guarded run directory.")
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
        help="Optional path for codex_cli_execution_unlock_snapshot.json.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_execution_unlock_snapshot.md.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
