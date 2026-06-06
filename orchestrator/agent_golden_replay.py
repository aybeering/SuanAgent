"""Golden replay report for a saved deterministic agent input/output pair."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.agent_output_intake import verify_agent_output
from orchestrator.agent_replay import SUPPORTED_AGENT, replay_agent_input
from orchestrator.failure_taxonomy import attach_failure_metadata, reason_code


AGENT_GOLDEN_REPLAY_SCHEMA_VERSION = "agent_golden_replay_v1"


def write_agent_golden_replay(
    *,
    round_dir: Path,
    repo_root: Path = Path("."),
    attempt_id: str = "selected",
    output_path: Path | None = None,
    markdown_path: Path | None = None,
    agent: str = SUPPORTED_AGENT,
) -> dict[str, Any]:
    """Replay one saved attempt as a stable protocol golden sample."""
    repo_root = repo_root.resolve()
    round_dir = resolve_path(round_dir, repo_root)
    payload = build_agent_golden_replay(
        round_dir=round_dir,
        repo_root=repo_root,
        attempt_id=attempt_id,
        agent=agent,
    )
    destination = output_path or round_dir / "agent_golden_replay.json"
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_destination = markdown_path or round_dir / "agent_golden_replay.md"
    markdown_destination.write_text(agent_golden_replay_markdown(payload), encoding="utf-8")
    return payload


def build_agent_golden_replay(
    *,
    round_dir: Path,
    repo_root: Path,
    attempt_id: str = "selected",
    agent: str = SUPPORTED_AGENT,
) -> dict[str, Any]:
    """Return the golden replay report payload without changing loop decisions."""
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
                stage="golden_replay",
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
    saved_raw_output_path = attempt_dir / "raw_agent_output.txt"
    golden_output_path = attempt_dir / "golden_agent_output.json"
    golden_validation_path = attempt_dir / "golden_agent_validation.json"
    golden_proposal_path = attempt_dir / "golden_proposal.json"

    for name, path in (
        ("attempt_input", attempt_input_path),
        ("saved_proposal", saved_proposal_path),
        ("saved_raw_output", saved_raw_output_path),
    ):
        if not path.exists() or not path.is_file():
            reason_codes.append(
                reason_code(
                    stage="golden_replay",
                    code=f"{name}_missing",
                    message=str(path),
                )
            )

    replay_validation: dict[str, Any] = {}
    replayed_patch_sha = ""
    saved_patch_sha = ""
    saved_raw_output_sha = ""
    replayed_raw_output_sha = ""
    saved_direction_tag = ""
    replayed_direction_tag = ""
    if not reason_codes:
        replay_agent_input(
            agent_input_path=attempt_input_path,
            output_path=golden_output_path,
            agent=agent,
        )
        replay_validation = verify_agent_output(
            agent_input_path=attempt_input_path,
            agent_output_path=golden_output_path,
            repo_root=repo_root,
            output_path=golden_validation_path,
            proposal_output_path=golden_proposal_path,
            agent_name="agent_golden_replay",
        )
        saved_proposal = load_json_object(saved_proposal_path)
        replayed_proposal = replay_validation.get("proposal", {})
        replayed_proposal_map = (
            replayed_proposal if isinstance(replayed_proposal, dict) else {}
        )
        saved_patch_sha = str(saved_proposal.get("patch_sha256", ""))
        replayed_patch_sha = str(replay_validation.get("proposal_patch_sha256", ""))
        saved_raw_output_sha = file_sha256(saved_raw_output_path)
        replayed_raw_output_sha = file_sha256(golden_output_path)
        saved_direction_tag = str(saved_proposal.get("direction_tag", ""))
        replayed_direction_tag = str(replayed_proposal_map.get("direction_tag", ""))
        if not bool(replay_validation.get("ok", False)):
            reason_codes.append(
                reason_code(
                    stage="golden_replay",
                    code="replayed_output_validation_failed",
                    message=str(replay_validation.get("failure_message", "")),
                )
            )
        if saved_patch_sha != replayed_patch_sha:
            reason_codes.append(
                reason_code(
                    stage="golden_replay",
                    code="patch_sha_mismatch",
                    message=f"saved={saved_patch_sha} replayed={replayed_patch_sha}",
                )
            )
        if saved_raw_output_sha != replayed_raw_output_sha:
            reason_codes.append(
                reason_code(
                    stage="golden_replay",
                    code="raw_output_sha_mismatch",
                    message=(
                        "saved="
                        f"{saved_raw_output_sha} replayed={replayed_raw_output_sha}"
                    ),
                )
            )
        if saved_direction_tag != replayed_direction_tag:
            reason_codes.append(
                reason_code(
                    stage="golden_replay",
                    code="direction_tag_mismatch",
                    message=(
                        f"saved={saved_direction_tag} replayed={replayed_direction_tag}"
                    ),
                )
            )

    report = {
        "schema_version": AGENT_GOLDEN_REPLAY_SCHEMA_VERSION,
        "ok": not reason_codes,
        "run_id": str(manifest.get("run_id", "")),
        "round_id": str(manifest.get("round_id", round_dir.name)),
        "round_dir": relative_path(round_dir, repo_root),
        "requested_attempt_id": attempt_id,
        "attempt_id": resolved_attempt_id,
        "selected_attempt_id": selected_attempt_id,
        "agent": agent,
        "checks": {
            "attempt_present": bool(manifest_row),
            "replayed_output_validation_ok": bool(replay_validation.get("ok", False)),
            "patch_sha_matches_saved_proposal": (
                bool(saved_patch_sha) and saved_patch_sha == replayed_patch_sha
            ),
            "raw_output_sha_matches_saved_output": (
                bool(saved_raw_output_sha)
                and saved_raw_output_sha == replayed_raw_output_sha
            ),
            "direction_tag_matches_saved_proposal": (
                bool(saved_direction_tag)
                and saved_direction_tag == replayed_direction_tag
            ),
        },
        "artifacts": {
            "attempt_input": file_record(attempt_input_path, repo_root),
            "saved_raw_output": file_record(saved_raw_output_path, repo_root),
            "saved_proposal": file_record(saved_proposal_path, repo_root),
            "golden_output": file_record(golden_output_path, repo_root),
            "golden_validation": file_record(golden_validation_path, repo_root),
            "golden_proposal": file_record(golden_proposal_path, repo_root),
        },
        "comparison": {
            "saved_patch_sha256": saved_patch_sha,
            "replayed_patch_sha256": replayed_patch_sha,
            "saved_raw_output_sha256": saved_raw_output_sha,
            "replayed_raw_output_sha256": replayed_raw_output_sha,
            "saved_direction_tag": saved_direction_tag,
            "replayed_direction_tag": replayed_direction_tag,
        },
        "policy": {
            "does_not_execute_external_agents": True,
            "does_not_select_candidate": True,
            "does_not_apply_final_patch": True,
            "does_not_change_acceptance": True,
            "replays_saved_agent_input_contract": True,
            "requires_replayed_output_validation": True,
            "requires_patch_hash_match": True,
            "requires_raw_output_hash_match": True,
        },
    }
    return attach_failure_metadata(report, reason_codes)


def agent_golden_replay_markdown(payload: dict[str, Any]) -> str:
    """Return a compact markdown report for a golden replay."""
    checks = dict_or_empty(payload.get("checks", {}))
    return "\n".join(
        [
            "# Agent Golden Replay",
            "",
            f"- Schema: `{payload.get('schema_version', '')}`",
            f"- Run: `{payload.get('run_id', '')}`",
            f"- Round: `{payload.get('round_id', '')}`",
            f"- Attempt: `{payload.get('attempt_id', '')}`",
            f"- OK: `{payload.get('ok', False)}`",
            f"- Failure code: `{payload.get('failure_code', '')}`",
            "",
            "## Checks",
            *(
                f"- {key}: `{value}`"
                for key, value in sorted(checks.items())
            ),
            "",
            "This replay validates a saved agent protocol fixture without executing external agents or changing acceptance.",
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
    """Return a file sha256 digest, or empty string when missing."""
    if not path.exists() or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def main() -> None:
    """CLI entrypoint for golden agent replay."""
    args = parse_args()
    payload = write_agent_golden_replay(
        round_dir=args.round_dir,
        repo_root=args.repo_root,
        attempt_id=args.attempt_id,
        output_path=args.output,
        markdown_path=args.markdown_output,
        agent=args.agent,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for golden replay."""
    parser = argparse.ArgumentParser(
        description="Create a golden replay report for a saved agent attempt.",
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
        help="Attempt id to replay, or 'selected' for the manifest-selected attempt.",
    )
    parser.add_argument(
        "--agent",
        default=SUPPORTED_AGENT,
        choices=[SUPPORTED_AGENT],
        help="Deterministic replay agent implementation to use.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for agent_golden_replay.json.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional path for agent_golden_replay.md.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
