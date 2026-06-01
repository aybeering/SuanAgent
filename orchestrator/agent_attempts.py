"""Per-candidate attempt trace artifacts for modifier selection."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from orchestrator.failure_taxonomy import primary_failure, selection_skip_reason_codes


AGENT_ATTEMPTS_SCHEMA_VERSION = "agent_attempts_v1"
AGENT_SELECTION_SCHEMA_VERSION = "agent_selection_v1"
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
        copy_attempt_runtime_artifacts(
            round_dir=round_dir,
            attempt_dir=attempt_dir,
            attempt_id=attempt_id,
        )
        rows.append(
            {
                "attempt_id": attempt_id,
                "attempt_index": index,
                "role": attempt.get("role", ""),
                "profile_name": attempt.get("profile_name", ""),
                "adapter_name": attempt.get("adapter_name", ""),
                "agent_name": attempt.get("agent_name", ""),
                "direction_tag": attempt.get("direction_tag", ""),
                "status": attempt.get("status", ""),
                "selected": bool(attempt.get("selected", False)),
                "candidate_score": attempt.get("candidate_score", 0),
                "failure_stage": attempt.get("failure_stage", "none"),
                "failure_code": attempt.get("failure_code", "none"),
                "failure_message": attempt.get("failure_message", ""),
                "reason_codes": attempt.get("reason_codes", []),
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


def write_agent_selection_report(
    *,
    round_dir: Path,
    repo_root: Path,
    run_id: str,
    round_id: str,
    attempts: list[dict[str, object]],
) -> Path:
    """Write a deterministic explanation of candidate selection."""
    rows = selection_rows(attempts=attempts, repo_root=repo_root, round_dir=round_dir)
    selected_rows = [row for row in rows if row["selected"] is True]
    selected_attempt_id = (
        str(selected_rows[0]["attempt_id"]) if selected_rows else ""
    )
    report = {
        "schema_version": AGENT_SELECTION_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "selected_attempt_id": selected_attempt_id,
        "selection_policy": {
            "eligible_status": "selectable",
            "rank_order": [
                "selected",
                "candidate_score_desc",
                "attempt_index_asc",
            ],
            "final_acceptance": "deterministic policy gate after backtest",
        },
        "attempts": rows,
    }
    output_path = round_dir / "agent_selection_report.json"
    write_json(output_path, report)
    write_attempt_selection_files(round_dir=round_dir, rows=rows)
    return output_path


def selection_rows(
    *,
    attempts: list[dict[str, object]],
    repo_root: Path,
    round_dir: Path,
) -> list[dict[str, object]]:
    """Return per-attempt selection explanation rows."""
    selected_index = selected_attempt_index(attempts)
    rows: list[dict[str, object]] = []
    for index, attempt in enumerate(attempts, start=1):
        attempt_id = attempt_trace_id(index=index, role=str(attempt.get("role", "")))
        selected = bool(attempt.get("selected", False))
        status = str(attempt.get("status", ""))
        eligible = status == "selectable"
        blocking_reasons = attempt_blocking_reasons(attempt)
        skip_reason_codes = selection_skip_reason_codes(
            selected=selected,
            status=status,
            blocking_reasons=blocking_reasons,
            selected_index=selected_index,
        )
        attempt_reason_codes = attempt.get("reason_codes", [])
        row_reason_codes = attempt_reason_codes or skip_reason_codes
        failure = primary_failure(row_reason_codes)
        rows.append(
            {
                "attempt_id": attempt_id,
                "attempt_index": index,
                "role": attempt.get("role", ""),
                "profile_name": attempt.get("profile_name", ""),
                "adapter_name": attempt.get("adapter_name", ""),
                "agent_name": attempt.get("agent_name", ""),
                "direction_tag": attempt.get("direction_tag", ""),
                "status": status,
                "eligible": eligible,
                "selected": selected,
                "rank": attempt_rank(
                    attempts=attempts,
                    attempt_index=index - 1,
                ),
                "candidate_score": attempt.get("candidate_score", 0),
                "failure_stage": failure["stage"],
                "failure_code": failure["code"],
                "failure_message": failure["message"],
                "reason_codes": row_reason_codes,
                "score_reasons": attempt.get("score_reasons", []),
                "blocking_reasons": blocking_reasons,
                "selection_reason": attempt.get("selection_reason", ""),
                "skip_reason": attempt_skip_reason(
                    attempt=attempt,
                    attempt_index=index - 1,
                    selected_index=selected_index,
                    blocking_reasons=blocking_reasons,
                ),
                "patch_sha256": attempt.get("patch_sha256", ""),
                "probe_ev_delta": attempt.get("probe_ev_delta", 0.0),
                "validation_status": attempt.get("validation_status", ""),
                "validation_accepted": attempt.get("validation_accepted", None),
                "validation_ev_delta": attempt.get("validation_ev_delta", None),
                "attempt_dir": relative_path(
                    round_dir / ATTEMPTS_DIRNAME / attempt_id,
                    repo_root,
                ),
            }
        )
    return rows


def write_attempt_selection_files(
    *,
    round_dir: Path,
    rows: list[dict[str, object]],
) -> None:
    """Write per-attempt selection report files into trace dirs."""
    for row in rows:
        attempt_dir = round_dir / ATTEMPTS_DIRNAME / str(row["attempt_id"])
        attempt_dir.mkdir(parents=True, exist_ok=True)
        write_json(attempt_dir / "selection.json", row)


def copy_attempt_runtime_artifacts(
    *,
    round_dir: Path,
    attempt_dir: Path,
    attempt_id: str,
) -> None:
    """Copy attempt-scoped workspace/execution audits into the attempt trace."""
    for source_dirname, destination_name in (
        ("workspace_manifests", "workspace_manifest.json"),
        ("agent_executions", "agent_execution.json"),
    ):
        source = round_dir / source_dirname / f"{attempt_id}.json"
        if source.exists():
            shutil.copy2(source, attempt_dir / destination_name)


def selected_attempt_index(attempts: list[dict[str, object]]) -> int | None:
    """Return the selected attempt list index."""
    for index, attempt in enumerate(attempts):
        if bool(attempt.get("selected", False)):
            return index
    return None


def attempt_rank(
    *,
    attempts: list[dict[str, object]],
    attempt_index: int,
) -> int:
    """Return a stable rank over selected/selectable candidate attempts."""
    ordered_indexes = sorted(
        range(len(attempts)),
        key=lambda index: (
            bool(attempts[index].get("selected", False)),
            int(attempts[index].get("candidate_score", 0)),
            -index,
        ),
        reverse=True,
    )
    return ordered_indexes.index(attempt_index) + 1


def attempt_blocking_reasons(attempt: dict[str, object]) -> list[str]:
    """Return deterministic reasons why an attempt was not eligible."""
    reasons: list[str] = []
    for field in (
        "contract_errors",
        "memory_filter_reason",
        "patch_memory_filter_reason",
        "direction_filter_reason",
        "patch_check_error",
        "probe_error",
    ):
        value = attempt.get(field)
        if isinstance(value, list | tuple):
            reasons.extend(str(item) for item in value if str(item))
        elif value:
            reasons.append(str(value))
    status = str(attempt.get("status", ""))
    if status and status != "selectable" and not reasons:
        reasons.append(f"status={status}")
    return reasons


def attempt_skip_reason(
    *,
    attempt: dict[str, object],
    attempt_index: int,
    selected_index: int | None,
    blocking_reasons: list[str],
) -> str:
    """Return the stable skip reason for an unselected attempt."""
    if bool(attempt.get("selected", False)):
        return ""
    if blocking_reasons:
        return "; ".join(blocking_reasons)
    if selected_index is None:
        return "no selected attempt"
    return (
        "selectable but not highest ranked"
        if str(attempt.get("status", "")) == "selectable"
        else f"status={attempt.get('status', 'unknown')}"
    )


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
