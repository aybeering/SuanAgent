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
ATTEMPT_OUTPUT_SCHEMA_VERSION = "attempt_output_v1"
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
        write_attempt_agent_input(
            round_dir=round_dir,
            attempt_dir=attempt_dir,
            attempt=attempt,
            attempt_id=attempt_id,
        )
        attempt_output_path = write_attempt_output(
            round_dir=round_dir,
            repo_root=repo_root,
            attempt_dir=attempt_dir,
            attempt=attempt,
            attempts=attempts,
            attempt_id=attempt_id,
            attempt_index=index,
        )
        rows.append(
            {
                "attempt_id": attempt_id,
                "attempt_index": index,
                "role": attempt.get("role", ""),
                "agent_role": attempt.get("agent_role", ""),
                "profile_name": attempt.get("profile_name", ""),
                "adapter_name": attempt.get("adapter_name", ""),
                "supported_directions": attempt.get("supported_directions", []),
                "direction_capability": attempt.get("direction_capability", {}),
                "direction_intent_alignment": attempt.get(
                    "direction_intent_alignment", {}
                ),
                "runner_name": attempt.get("runner_name", ""),
                "runner": attempt.get("runner", {}),
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
                "agent_input": relative_path(attempt_dir / "agent_input.json", repo_root),
                "attempt_output": relative_path(attempt_output_path, repo_root),
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
                "agent_role": attempt.get("agent_role", ""),
                "profile_name": attempt.get("profile_name", ""),
                "adapter_name": attempt.get("adapter_name", ""),
                "supported_directions": attempt.get("supported_directions", []),
                "direction_capability": attempt.get("direction_capability", {}),
                "direction_intent_alignment": attempt.get(
                    "direction_intent_alignment", {}
                ),
                "runner_name": attempt.get("runner_name", ""),
                "runner": attempt.get("runner", {}),
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
                "quality_breakdown": attempt.get("quality_breakdown", {}),
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
                "probe_trade_count_delta": attempt.get(
                    "probe_trade_count_delta",
                    0.0,
                ),
                "validation_status": attempt.get("validation_status", ""),
                "validation_accepted": attempt.get("validation_accepted", None),
                "validation_ev_delta": attempt.get("validation_ev_delta", None),
                "validation_trade_count_delta": attempt.get(
                    "validation_trade_count_delta",
                    None,
                ),
                "holdout_ev_delta": attempt.get("holdout_ev_delta", None),
                "holdout_trade_count_delta": attempt.get(
                    "holdout_trade_count_delta",
                    None,
                ),
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


def write_attempt_output(
    *,
    round_dir: Path,
    repo_root: Path,
    attempt_dir: Path,
    attempt: dict[str, object],
    attempts: list[dict[str, object]],
    attempt_id: str,
    attempt_index: int,
) -> Path:
    """Write a compact, attempt-scoped output/audit summary."""
    payload = attempt_output_payload(
        round_dir=round_dir,
        repo_root=repo_root,
        attempt_dir=attempt_dir,
        attempt=attempt,
        attempts=attempts,
        attempt_id=attempt_id,
        attempt_index=attempt_index,
    )
    output_path = attempt_dir / "attempt_output.json"
    write_json(output_path, payload)
    return output_path


def attempt_output_payload(
    *,
    round_dir: Path,
    repo_root: Path,
    attempt_dir: Path,
    attempt: dict[str, object],
    attempts: list[dict[str, object]],
    attempt_id: str,
    attempt_index: int,
) -> dict[str, object]:
    """Return the self-contained audit summary for one candidate attempt."""
    selected_index = selected_attempt_index(attempts)
    selected = bool(attempt.get("selected", False))
    status = str(attempt.get("status", ""))
    blocking_reasons = attempt_blocking_reasons(attempt)
    reason_codes = attempt.get("reason_codes", [])
    if not reason_codes:
        reason_codes = selection_skip_reason_codes(
            selected=selected,
            status=status,
            blocking_reasons=blocking_reasons,
            selected_index=selected_index,
        )
    failure = primary_failure(reason_codes)
    return {
        "schema_version": ATTEMPT_OUTPUT_SCHEMA_VERSION,
        "attempt_id": attempt_id,
        "attempt_index": attempt_index,
        "round_id": round_dir.name,
        "role": attempt.get("role", ""),
        "agent_role": attempt.get("agent_role", ""),
        "profile_name": attempt.get("profile_name", ""),
        "adapter_name": attempt.get("adapter_name", ""),
        "supported_directions": attempt.get("supported_directions", []),
        "direction_capability": attempt.get("direction_capability", {}),
        "direction_intent_alignment": attempt.get("direction_intent_alignment", {}),
        "runner_name": attempt.get("runner_name", ""),
        "runner": attempt.get("runner", {}),
        "agent_name": attempt.get("agent_name", ""),
        "direction_tag": attempt.get("direction_tag", ""),
        "status": status,
        "selected": selected,
        "eligible": status == "selectable",
        "rank": attempt_rank(attempts=attempts, attempt_index=attempt_index - 1),
        "candidate_score": attempt.get("candidate_score", 0),
        "failure_stage": failure["stage"],
        "failure_code": failure["code"],
        "failure_message": failure["message"],
        "reason_codes": reason_codes,
        "proposal": proposal_payload(attempt),
        "selection": {
            "selected": selected,
            "selection_reason": attempt.get("selection_reason", ""),
            "skip_reason": attempt_skip_reason(
                attempt=attempt,
                attempt_index=attempt_index - 1,
                selected_index=selected_index,
                blocking_reasons=blocking_reasons,
            ),
            "score_reasons": attempt.get("score_reasons", []),
            "quality_breakdown": attempt.get("quality_breakdown", {}),
            "blocking_reasons": blocking_reasons,
        },
        "validation": {
            "status": attempt.get("validation_status", ""),
            "accepted": attempt.get("validation_accepted", None),
            "ev_delta": attempt.get("validation_ev_delta", None),
            "trade_count_delta": attempt.get("validation_trade_count_delta", None),
            "probe_ev_delta": attempt.get("probe_ev_delta", 0.0),
            "probe_trade_count_delta": attempt.get("probe_trade_count_delta", 0.0),
            "holdout_ev_delta": attempt.get("holdout_ev_delta", None),
            "holdout_trade_count_delta": attempt.get(
                "holdout_trade_count_delta",
                None,
            ),
        },
        "artifacts": attempt_output_artifacts(
            round_dir=round_dir,
            repo_root=repo_root,
            attempt_dir=attempt_dir,
        ),
    }


def attempt_output_artifacts(
    *,
    round_dir: Path,
    repo_root: Path,
    attempt_dir: Path,
) -> dict[str, str]:
    """Return stable artifact paths referenced by attempt_output.json."""
    return {
        "attempt": relative_path(attempt_dir / "attempt.json", repo_root),
        "agent_input": relative_path(attempt_dir / "agent_input.json", repo_root),
        "proposal": relative_path(attempt_dir / "proposal.json", repo_root),
        "raw_agent_output": relative_path(
            attempt_dir / "raw_agent_output.txt",
            repo_root,
        ),
        "patch": relative_path(attempt_dir / "patch.diff", repo_root),
        "selection": relative_path(attempt_dir / "selection.json", repo_root),
        "workspace_manifest": relative_path(
            attempt_dir / "workspace_manifest.json",
            repo_root,
        )
        if (attempt_dir / "workspace_manifest.json").exists()
        else "",
        "agent_execution": relative_path(
            attempt_dir / "agent_execution.json",
            repo_root,
        )
        if (attempt_dir / "agent_execution.json").exists()
        else "",
        "round_agent_input": relative_path(round_dir / "agent_input.json", repo_root),
        "round_agent_output": relative_path(round_dir / "agent_output.json", repo_root),
        "round_agent_validation": relative_path(
            round_dir / "agent_validation.json",
            repo_root,
        ),
    }


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


def write_attempt_agent_input(
    *,
    round_dir: Path,
    attempt_dir: Path,
    attempt: dict[str, object],
    attempt_id: str,
) -> None:
    """Write the exact or synthesized input contract for one attempt."""
    workspace_input = workspace_agent_input_path(round_dir=round_dir, attempt_id=attempt_id)
    destination = attempt_dir / "agent_input.json"
    if workspace_input is not None and workspace_input.exists():
        shutil.copy2(workspace_input, destination)
        return

    source = round_dir / "agent_input.json"
    if not source.exists():
        return
    payload = load_json_object(source)
    payload["active_agent"] = {
        "attempt_id": attempt_id,
        "role": str(attempt.get("role", "")),
        "agent_role": str(attempt.get("agent_role", "")),
        "profile_name": str(attempt.get("profile_name", "")),
        "adapter_name": str(attempt.get("adapter_name", "")),
        "agent_name": str(attempt.get("agent_name", "")),
        "output_filename": "",
        "supported_directions": list_or_empty(
            attempt.get("supported_directions", [])
        ),
    }
    output_contract = payload.get("output_contract", {})
    if isinstance(output_contract, dict):
        output_contract["workspace_output_path"] = ""
        output_contract["expected_command_output_filename"] = ""
    write_json(destination, payload)


def workspace_agent_input_path(*, round_dir: Path, attempt_id: str) -> Path | None:
    """Return workspace-local agent input path from execution audit when present."""
    execution_path = round_dir / "agent_executions" / f"{attempt_id}.json"
    if not execution_path.exists():
        return None
    payload = load_json_object(execution_path)
    agent_input_path = str(payload.get("agent_input_path", ""))
    return Path(agent_input_path) if agent_input_path else None


def load_json_object(path: Path) -> dict[str, object]:
    """Load a JSON object from disk."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def list_or_empty(value: object) -> list[object]:
    """Return JSON-list metadata without leaking tuple values."""
    return list(value) if isinstance(value, list | tuple) else []


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
        "direction_capability_reason",
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
