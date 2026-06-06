"""Record a deterministic manual approval for guarded Codex CLI enablement."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


CODEX_CLI_MANUAL_APPROVAL_SCHEMA_VERSION = "codex_cli_manual_approval_v1"
REQUIRED_CONFIRMATION_PHRASE = (
    "I approve this Codex CLI candidate for manual enablement"
)


def build_codex_cli_manual_approval(
    *,
    run_dir: Path,
    config_path: Path,
    approved: bool = False,
    approved_by: str = "",
    confirmation_phrase: str = "",
    approval_scope: str = "manual_enablement_candidate",
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Return a deterministic manual approval gate report."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    config_path = resolve_path(config_path, repo_root)
    enablement_gate_path = run_dir / "codex_cli_enablement_gate.json"
    enablement_gate = load_json_object(enablement_gate_path)
    enablement_config = object_value(enablement_gate.get("config", {}))
    enablement_section = object_value(enablement_config.get("enablement", {}))
    codex_cli = object_value(enablement_config.get("codex_cli", {}))
    candidate_config_path = str(enablement_gate.get("config_path", ""))
    expected_config_path = relative_path(config_path, repo_root)
    checks = {
        "config_exists": config_path.exists() and config_path.is_file(),
        "enablement_gate_present": bool(enablement_gate),
        "enablement_gate_ok": bool(enablement_gate.get("ok", False)),
        "enablement_gate_permitted": bool(
            enablement_gate.get("permitted_to_enable", False)
        ),
        "gate_config_matches_candidate": candidate_config_path == expected_config_path,
        "candidate_execute_true": bool(codex_cli.get("execute", False)),
        "candidate_only_declared": bool(enablement_section.get("candidate_only", False)),
        "manual_confirmation_required": bool(
            enablement_section.get("manual_confirmation_required", False)
        ),
        "explicit_approval": bool(approved),
        "approved_by_present": bool(approved_by.strip()),
        "confirmation_phrase_matches": confirmation_phrase
        == REQUIRED_CONFIRMATION_PHRASE,
        "source_artifact_hashes_recorded": (
            bool(file_record(enablement_gate_path, repo_root).get("sha256", ""))
            and bool(file_record(config_path, repo_root).get("sha256", ""))
        ),
    }
    blocking_reasons = manual_approval_blockers(checks)
    granted = not blocking_reasons
    return {
        "schema_version": CODEX_CLI_MANUAL_APPROVAL_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "config_path": expected_config_path,
        "ok": granted,
        "manual_approval_granted": granted,
        "ready_for_controlled_codex_cli_execution": granted,
        "blocking_reasons": blocking_reasons,
        "checks": checks,
        "approval": {
            "approved": bool(approved),
            "approved_by": approved_by.strip(),
            "approval_scope": approval_scope,
            "required_confirmation_phrase_sha256": sha256_text(
                REQUIRED_CONFIRMATION_PHRASE
            ),
            "provided_confirmation_phrase_sha256": sha256_text(confirmation_phrase),
            "confirmation_phrase_matches": checks["confirmation_phrase_matches"],
        },
        "artifacts": {
            "codex_cli_enablement_gate": file_record(enablement_gate_path, repo_root),
            "candidate_config": file_record(config_path, repo_root),
        },
        "enablement_gate": {
            "schema_version": str(enablement_gate.get("schema_version", "")),
            "ok": bool(enablement_gate.get("ok", False)),
            "permitted_to_enable": bool(
                enablement_gate.get("permitted_to_enable", False)
            ),
            "config_path": candidate_config_path,
        },
        "policy": {
            "approval_only": True,
            "does_not_execute_codex_cli": True,
            "does_not_modify_config": True,
            "does_not_select_candidate": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
            "requires_enablement_gate": True,
            "requires_explicit_approval_flag": True,
            "requires_exact_confirmation_phrase": True,
            "requires_source_artifact_hash_match": True,
            "deterministic_code_keeps_acceptance_authority": True,
        },
    }


def write_codex_cli_manual_approval(
    *,
    run_dir: Path,
    config_path: Path,
    approved: bool = False,
    approved_by: str = "",
    confirmation_phrase: str = "",
    approval_scope: str = "manual_enablement_candidate",
    repo_root: Path = Path("."),
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    """Write JSON and markdown manual approval artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    payload = build_codex_cli_manual_approval(
        run_dir=run_dir,
        config_path=config_path,
        approved=approved,
        approved_by=approved_by,
        confirmation_phrase=confirmation_phrase,
        approval_scope=approval_scope,
        repo_root=repo_root,
    )
    destination = output_path or run_dir / "codex_cli_manual_approval.json"
    write_json(destination, payload)
    markdown_destination = markdown_path or run_dir / "codex_cli_manual_approval.md"
    markdown_destination.write_text(
        codex_cli_manual_approval_markdown(payload),
        encoding="utf-8",
    )
    return payload


def manual_approval_blockers(checks: dict[str, bool]) -> list[str]:
    """Return stable blocker codes for manual approval checks."""
    blockers: list[str] = []
    for key, code in (
        ("config_exists", "config_missing"),
        ("enablement_gate_present", "enablement_gate_missing"),
        ("enablement_gate_ok", "enablement_gate_not_ok"),
        ("enablement_gate_permitted", "enablement_gate_not_permitted"),
        ("gate_config_matches_candidate", "candidate_config_mismatch"),
        ("candidate_execute_true", "candidate_execute_not_true"),
        ("candidate_only_declared", "candidate_only_not_declared"),
        ("manual_confirmation_required", "manual_confirmation_not_required"),
        ("explicit_approval", "explicit_approval_missing"),
        ("approved_by_present", "approved_by_missing"),
        ("confirmation_phrase_matches", "confirmation_phrase_mismatch"),
        ("source_artifact_hashes_recorded", "source_artifact_hash_missing"),
    ):
        if not checks.get(key, False):
            blockers.append(code)
    return blockers


def codex_cli_manual_approval_markdown(payload: dict[str, Any]) -> str:
    """Return compact markdown for manual approval."""
    blockers = string_list(payload.get("blocking_reasons", []))
    approval = object_value(payload.get("approval", {}))
    lines = [
        "# Codex CLI Manual Approval",
        "",
        f"- Schema: `{payload.get('schema_version', '')}`",
        f"- Run: `{payload.get('run_id', '')}`",
        f"- Manual approval granted: `{payload.get('manual_approval_granted', False)}`",
        f"- Ready for controlled execution: `{payload.get('ready_for_controlled_codex_cli_execution', False)}`",
        f"- Approved by: `{approval.get('approved_by', '')}`",
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
            "This artifact records explicit human approval only; it does not execute Codex, apply patches, or change acceptance.",
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


def sha256_text(value: str) -> str:
    """Return the SHA-256 hash for text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
    """CLI entrypoint for Codex CLI manual approval."""
    args = parse_args()
    payload = write_codex_cli_manual_approval(
        run_dir=args.run_dir,
        config_path=args.config,
        approved=args.approved,
        approved_by=args.approved_by,
        confirmation_phrase=args.confirmation_phrase,
        approval_scope=args.approval_scope,
        repo_root=args.repo_root,
        output_path=args.output,
        markdown_path=args.markdown_output,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for Codex CLI manual approval."""
    parser = argparse.ArgumentParser(
        description="Record manual approval after Codex CLI enablement gate.",
    )
    parser.add_argument("run_dir", type=Path, help="Path to an iteration run directory.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/codex_cli_enable_candidate.json"),
        help="Candidate config that explicitly sets codex_cli.execute=true.",
    )
    parser.add_argument(
        "--approved",
        action="store_true",
        help="Explicit approval flag required for a passing artifact.",
    )
    parser.add_argument(
        "--approved-by",
        default="",
        help="Human or fixture identity granting approval.",
    )
    parser.add_argument(
        "--confirmation-phrase",
        default="",
        help="Must exactly match the required confirmation phrase.",
    )
    parser.add_argument(
        "--approval-scope",
        default="manual_enablement_candidate",
        help="Stable scope label for the approval artifact.",
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
        help="Optional path for codex_cli_manual_approval.json.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_manual_approval.md.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
