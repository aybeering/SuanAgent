"""Deterministic stdout fixture for the guarded Codex CLI contract."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.agent_contract_runner import CODEX_CLI_GUARDED_RUNNER_NAME
from orchestrator.agent_output_intake import verify_agent_output
from orchestrator.failure_taxonomy import attach_failure_metadata, reason_code


CODEX_CLI_CONTRACT_FIXTURE_SCHEMA_VERSION = "codex_cli_contract_fixture_v1"
OLD_THRESHOLD = "MIN_EDGE = 0.05"
NEW_THRESHOLD = "MIN_EDGE = 0.04"


def write_codex_cli_contract_fixture(
    *,
    round_dir: Path,
    repo_root: Path = Path("."),
    attempt_id: str = "selected",
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    """Write a deterministic Codex CLI stdin/stdout contract fixture report."""
    repo_root = repo_root.resolve()
    round_dir = resolve_path(round_dir, repo_root)
    payload = build_codex_cli_contract_fixture(
        round_dir=round_dir,
        repo_root=repo_root,
        attempt_id=attempt_id,
    )
    destination = output_path or round_dir / "codex_cli_contract_fixture.json"
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_destination = markdown_path or round_dir / "codex_cli_contract_fixture.md"
    markdown_destination.write_text(
        codex_cli_contract_fixture_markdown(payload),
        encoding="utf-8",
    )
    return payload


def build_codex_cli_contract_fixture(
    *,
    round_dir: Path,
    repo_root: Path,
    attempt_id: str = "selected",
) -> dict[str, Any]:
    """Return a deterministic contract fixture for one saved Codex CLI attempt."""
    reason_codes: list[dict[str, str]] = []
    manifest_path = round_dir / "agent_attempts_manifest.json"
    manifest = load_json_object(manifest_path)
    selected_attempt_id = str(manifest.get("selected_attempt_id", ""))
    resolved_attempt_id = selected_attempt_id if attempt_id == "selected" else attempt_id
    attempts = attempt_rows_by_id(manifest.get("attempts", []))
    manifest_row = attempts.get(resolved_attempt_id, {})
    if not manifest_row:
        reason_codes.append(
            reason_code(
                stage="codex_fixture",
                code="attempt_missing",
                message=f"attempt_id={resolved_attempt_id}",
            )
        )
    attempt_dir = resolve_path(
        Path(str(manifest_row.get("attempt_dir", ""))) if manifest_row else Path(),
        repo_root,
    )
    attempt_input_path = attempt_dir / "agent_input.json"
    saved_proposal_path = attempt_dir / "proposal.json"
    execution_path = first_existing_path(
        (
            attempt_dir / "agent_execution.json",
            round_dir / "agent_executions" / f"{resolved_attempt_id}.json",
            round_dir / "agent_execution.json",
        )
    )
    fixture_stdout_path = attempt_dir / "codex_cli_fixture_stdout.json"
    fixture_validation_path = attempt_dir / "codex_cli_fixture_validation.json"
    fixture_proposal_path = attempt_dir / "codex_cli_fixture_proposal.json"
    intake_binding: dict[str, object] = {}
    intake_binding_blockers: list[str] = []

    for name, path in (
        ("attempt_input", attempt_input_path),
        ("saved_proposal", saved_proposal_path),
        ("agent_execution", execution_path),
    ):
        if not path.exists() or not path.is_file():
            reason_codes.append(
                reason_code(
                    stage="codex_fixture",
                    code=f"{name}_missing",
                    message=str(path),
                )
            )

    proposal: dict[str, Any] = {}
    execution: dict[str, Any] = {}
    validation: dict[str, Any] = {}
    prompt_sha = ""
    audit_stdin_sha = ""
    fixture_patch_sha = ""
    fixture_direction = ""
    if not reason_codes:
        proposal = load_json_object(saved_proposal_path)
        execution = load_json_object(execution_path)
        if str(execution.get("runner_name", "")) != CODEX_CLI_GUARDED_RUNNER_NAME:
            reason_codes.append(
                reason_code(
                    stage="codex_fixture",
                    code="runner_not_codex_cli_guarded",
                    message=str(execution.get("runner_name", "")),
                )
            )
        if str(execution.get("adapter_name", "")) != "codex_cli":
            reason_codes.append(
                reason_code(
                    stage="codex_fixture",
                    code="adapter_not_codex_cli",
                    message=str(execution.get("adapter_name", "")),
                )
            )
        intake_binding = dict_or_empty(execution.get("intake_binding", {}))
        intake_binding_blockers = string_list(
            intake_binding.get("blocking_reasons", [])
        )
        if not bool(intake_binding.get("bound", False)):
            reason_codes.append(
                reason_code(
                    stage="codex_fixture",
                    code="intake_binding_not_bound",
                    message=str(execution_path),
                )
            )
        if intake_binding_blockers:
            reason_codes.append(
                reason_code(
                    stage="codex_fixture",
                    code="intake_binding_blocked",
                    message="; ".join(intake_binding_blockers),
                )
            )
        prompt = str(proposal.get("prompt", ""))
        prompt_sha = sha256_text(prompt) if prompt else ""
        stdin_summary = dict_or_empty(execution.get("stdin", {}))
        audit_stdin_sha = str(stdin_summary.get("sha256", ""))
        if not prompt_sha or prompt_sha != audit_stdin_sha:
            reason_codes.append(
                reason_code(
                    stage="codex_fixture",
                    code="stdin_prompt_sha_mismatch",
                    message=f"proposal={prompt_sha} audit={audit_stdin_sha}",
                )
            )

    if not reason_codes:
        agent_input = load_json_object(attempt_input_path)
        fixture_payload = codex_fixture_stdout(agent_input=agent_input)
        fixture_stdout_path.write_text(
            json.dumps(fixture_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        validation = verify_agent_output(
            agent_input_path=attempt_input_path,
            agent_output_path=fixture_stdout_path,
            repo_root=repo_root,
            output_path=fixture_validation_path,
            proposal_output_path=fixture_proposal_path,
            agent_name="codex_cli_contract_fixture",
        )
        fixture_patch_sha = str(validation.get("proposal_patch_sha256", ""))
        validation_proposal = validation.get("proposal", {})
        validation_proposal_map = (
            validation_proposal if isinstance(validation_proposal, dict) else {}
        )
        fixture_direction = str(validation_proposal_map.get("direction_tag", ""))
        if not bool(validation.get("ok", False)):
            reason_codes.append(
                reason_code(
                    stage="codex_fixture",
                    code="fixture_stdout_validation_failed",
                    message=str(validation.get("failure_message", "")),
                )
            )
        if not fixture_patch_sha:
            reason_codes.append(
                reason_code(
                    stage="codex_fixture",
                    code="fixture_patch_missing",
                    message="fixture stdout did not produce a patch hash",
                )
            )

    report = {
        "schema_version": CODEX_CLI_CONTRACT_FIXTURE_SCHEMA_VERSION,
        "ok": not reason_codes,
        "run_id": str(manifest.get("run_id", "")),
        "round_id": str(manifest.get("round_id", round_dir.name)),
        "round_dir": relative_path(round_dir, repo_root),
        "requested_attempt_id": attempt_id,
        "attempt_id": resolved_attempt_id,
        "selected_attempt_id": selected_attempt_id,
        "checks": {
            "attempt_present": bool(manifest_row),
            "adapter_is_codex_cli": str(execution.get("adapter_name", "")) == "codex_cli",
            "runner_is_guarded_codex_cli": (
                str(execution.get("runner_name", "")) == CODEX_CLI_GUARDED_RUNNER_NAME
            ),
            "intake_binding_bound": bool(intake_binding.get("bound", False)),
            "intake_binding_clean": not intake_binding_blockers,
            "stdin_prompt_sha_matches_audit": (
                bool(prompt_sha) and prompt_sha == audit_stdin_sha
            ),
            "fixture_stdout_validation_ok": bool(validation.get("ok", False)),
            "fixture_patch_present": bool(fixture_patch_sha),
            "does_not_execute_codex": True,
        },
        "artifacts": {
            "attempt_input": file_record(attempt_input_path, repo_root),
            "saved_proposal": file_record(saved_proposal_path, repo_root),
            "agent_execution": file_record(execution_path, repo_root),
            "fixture_stdout": file_record(fixture_stdout_path, repo_root),
            "fixture_validation": file_record(fixture_validation_path, repo_root),
            "fixture_proposal": file_record(fixture_proposal_path, repo_root),
        },
        "contract": {
            "command": list(execution.get("command", []))
            if isinstance(execution.get("command", []), list)
            else [],
            "execution_status": str(execution.get("status", "")),
            "execution_enabled": bool(execution.get("execution_enabled", False)),
            "prompt_sha256": prompt_sha,
            "audit_stdin_sha256": audit_stdin_sha,
            "intake_binding_status": str(intake_binding.get("status", "")),
            "intake_binding_blocking_reasons": intake_binding_blockers,
            "fixture_stdout_sha256": file_sha256(fixture_stdout_path),
            "fixture_patch_sha256": fixture_patch_sha,
            "fixture_direction_tag": fixture_direction,
        },
        "policy": {
            "does_not_execute_codex_cli": True,
            "does_not_select_candidate": True,
            "does_not_apply_final_patch": True,
            "does_not_change_acceptance": True,
            "freezes_stdin_stdout_contract": True,
            "requires_guarded_codex_runner": True,
            "requires_intake_binding": True,
            "requires_prompt_hash_match": True,
            "requires_fixture_stdout_validation": True,
        },
    }
    return attach_failure_metadata(report, reason_codes)


def codex_fixture_stdout(*, agent_input: dict[str, Any]) -> dict[str, object]:
    """Return a stable structured stdout payload shaped like Codex CLI output."""
    target_file = str(agent_input["target_file"])
    before = str(agent_input["target_file_content"])
    after = before.replace(OLD_THRESHOLD, NEW_THRESHOLD, 1)
    patch_diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{target_file}",
            tofile=f"b/{target_file}",
        )
    )
    return {
        "agent_name": "codex_cli",
        "round_index": int(agent_input["round_index"]),
        "target_file": target_file,
        "summary": "Fixture Codex CLI stdout lowers MIN_EDGE.",
        "risk_notes": "May increase trade count, slippage, and drawdown.",
        "direction_tag": "codex_cli_fixture_lower_min_edge",
        "expected_metric_change": {
            "trade_count": "increase",
            "ev": "uncertain",
            "avg_slippage": "increase",
        },
        "hypotheses": [
            "A guarded Codex CLI response should be parseable from structured JSON.",
            "The deterministic policy gate remains the only acceptance authority.",
        ],
        "patch_diff": patch_diff,
        "rejection_reason": "" if patch_diff.strip() else (
            f"fixture did not find {OLD_THRESHOLD}"
        ),
    }


def codex_cli_contract_fixture_markdown(payload: dict[str, Any]) -> str:
    """Return a compact markdown report for the Codex CLI contract fixture."""
    checks = dict_or_empty(payload.get("checks", {}))
    contract = dict_or_empty(payload.get("contract", {}))
    return "\n".join(
        [
            "# Codex CLI Contract Fixture",
            "",
            f"- Schema: `{payload.get('schema_version', '')}`",
            f"- Run: `{payload.get('run_id', '')}`",
            f"- Round: `{payload.get('round_id', '')}`",
            f"- Attempt: `{payload.get('attempt_id', '')}`",
            f"- OK: `{payload.get('ok', False)}`",
            f"- Failure code: `{payload.get('failure_code', '')}`",
            f"- Execution status: `{contract.get('execution_status', '')}`",
            f"- Fixture patch SHA-256: `{contract.get('fixture_patch_sha256', '')}`",
            "",
            "## Checks",
            *(f"- {key}: `{value}`" for key, value in sorted(checks.items())),
            "",
            "This fixture validates the guarded Codex CLI stdin/stdout contract without executing Codex or changing acceptance.",
            "",
        ]
    )


def attempt_rows_by_id(value: object) -> dict[str, dict[str, Any]]:
    """Return manifest attempt rows keyed by attempt id."""
    if not isinstance(value, list):
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        attempt_id = str(item.get("attempt_id", ""))
        if attempt_id:
            rows[attempt_id] = item
    return rows


def first_existing_path(paths: tuple[Path, ...]) -> Path:
    """Return the first existing path, or the first candidate."""
    for path in paths:
        if path.exists():
            return path
    return paths[0]


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


def file_sha256(path: Path) -> str:
    """Return a file hash or an empty string when the file is absent."""
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def sha256_text(text: str) -> str:
    """Return the SHA-256 digest for text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root when needed."""
    return path if path.is_absolute() else repo_root / path


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def dict_or_empty(value: object) -> dict[str, object]:
    """Return a dict or an empty dict."""
    return value if isinstance(value, dict) else {}


def string_list(value: object) -> list[str]:
    """Return non-empty strings from a JSON value."""
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, list | tuple):
        return []
    return [str(item) for item in value if str(item)]


def main() -> None:
    """CLI entrypoint for Codex CLI contract fixture generation."""
    args = parse_args()
    payload = write_codex_cli_contract_fixture(
        round_dir=args.round_dir,
        repo_root=args.repo_root,
        attempt_id=args.attempt_id,
        output_path=args.output,
        markdown_path=args.markdown_output,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for Codex CLI contract fixture generation."""
    parser = argparse.ArgumentParser(
        description="Create a deterministic fixture for a guarded Codex CLI attempt.",
    )
    parser.add_argument("round_dir", type=Path, help="Path to a round_XXX directory.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root used for contract validation.",
    )
    parser.add_argument(
        "--attempt-id",
        default="selected",
        help="Attempt id to inspect, or 'selected' for the manifest-selected attempt.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_contract_fixture.json.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional path for codex_cli_contract_fixture.md.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
