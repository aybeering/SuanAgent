"""Per-candidate attempt trace artifacts for modifier selection."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


AGENT_ATTEMPTS_SCHEMA_VERSION = "agent_attempts_v1"
ATTEMPTS_DIRNAME = "agent_attempts"


def write_agent_attempts_manifest(
    *,
    round_dir: Path,
    repo_root: Path,
    run_id: str,
    round_id: str,
    attempts: list[dict[str, object]],
) -> Path:
    """Write one trace directory per candidate attempt and a manifest."""
    attempts_dir = round_dir / ATTEMPTS_DIRNAME
    attempts_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    selected_attempt_id = ""
    for index, attempt in enumerate(attempts, start=1):
        attempt_id = attempt_trace_id(index=index, role=str(attempt.get("role", "")))
        if bool(attempt.get("selected", False)):
            selected_attempt_id = attempt_id
        attempt_dir = attempts_dir / attempt_id
        attempt_dir.mkdir(parents=True, exist_ok=True)
        proposal = proposal_payload(attempt)
        write_json(attempt_dir / "attempt.json", attempt)
        write_json(attempt_dir / "proposal.json", proposal)
        write_text(attempt_dir / "raw_agent_output.txt", str(proposal.get("raw_response", "")))
        write_text(attempt_dir / "patch.diff", str(proposal.get("patch_diff", "")))
        rows.append(
            {
                "attempt_id": attempt_id,
                "attempt_index": index,
                "role": attempt.get("role", ""),
                "agent_name": attempt.get("agent_name", ""),
                "direction_tag": attempt.get("direction_tag", ""),
                "status": attempt.get("status", ""),
                "selected": bool(attempt.get("selected", False)),
                "candidate_score": attempt.get("candidate_score", 0),
                "patch_sha256": attempt.get("patch_sha256", ""),
                "attempt_dir": relative_path(attempt_dir, repo_root),
                "files": file_records(attempt_dir, repo_root),
            }
        )
    manifest = {
        "schema_version": AGENT_ATTEMPTS_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "attempt_count": len(attempts),
        "selected_attempt_id": selected_attempt_id,
        "attempts_dir": relative_path(attempts_dir, repo_root),
        "attempts": rows,
    }
    output_path = round_dir / "agent_attempts_manifest.json"
    write_json(output_path, manifest)
    return output_path


def attempt_trace_id(*, index: int, role: str) -> str:
    """Return a stable trace id for one candidate attempt."""
    safe_role = re.sub(r"[^a-zA-Z0-9_]+", "_", role).strip("_").lower()
    return f"attempt_{index:03d}_{safe_role or 'candidate'}"


def proposal_payload(attempt: dict[str, object]) -> dict[str, Any]:
    """Return the proposal payload stored inside an attempt record."""
    proposal = attempt.get("proposal", {})
    return proposal if isinstance(proposal, dict) else {}


def file_records(directory: Path, repo_root: Path) -> list[dict[str, object]]:
    """Return stable file metadata for one attempt directory."""
    records: list[dict[str, object]] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        records.append(
            {
                "path": relative_path(path, repo_root),
                "name": path.name,
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    return records


def write_json(path: Path, payload: object) -> None:
    """Write deterministic JSON."""
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    """Write text with a trailing newline."""
    path.write_text(text.rstrip("\n") + "\n", encoding="utf-8")


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def file_sha256(path: Path) -> str:
    """Return a file SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
