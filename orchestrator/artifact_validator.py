"""Validate experiment artifacts and agent contract files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.schema_validation import validate_json_file


SINGLE_RUN_REQUIRED_FILES = (
    "metrics_before.json",
    "metrics_after.json",
    "report_before.md",
    "report_after.md",
    "summary.md",
    "decision.json",
    "patch.diff",
    "trades_before.csv",
    "trades_after.csv",
)

ITERATION_RUN_REQUIRED_FILES = (
    "manifest.json",
    "summary.md",
    "candidate_leaderboard.json",
)

ROUND_REQUIRED_FILES = (
    "train_metrics_before.json",
    "train_report_before.md",
    "train_trades_before.csv",
    "metrics_before.json",
    "report_before.md",
    "trades_before.csv",
    "holdout_metrics_before.json",
    "holdout_report_before.md",
    "holdout_trades_before.csv",
    "probe_data.csv",
    "probe_metrics_before.json",
    "probe_report_before.md",
    "probe_trades_before.csv",
    "agent_context.md",
    "agent_context.json",
    "proposal_intent.json",
    "proposal_intent.md",
    "agent_input.json",
    "agent_bundle_manifest.json",
    "agent_output.json",
    "agent_validation.json",
    "agent_executor_report.json",
    "agent_routing_policy.json",
    "agent_attempts_manifest.json",
    "agent_selection_report.json",
    "proposal_attempts.json",
    "proposal.json",
    "raw_agent_output.txt",
    "agent_response.txt",
    "patch.diff",
    "train_metrics_after.json",
    "train_report_after.md",
    "train_trades_after.csv",
    "metrics_after.json",
    "report_after.md",
    "trades_after.csv",
    "holdout_metrics_after.json",
    "holdout_report_after.md",
    "holdout_trades_after.csv",
    "decision.json",
)


def validate_run_artifacts(
    *,
    run_id: str,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return a deterministic validation report for one experiment run."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    run_dir = experiments_dir / run_id
    report: dict[str, object] = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "kind": "unknown",
        "ok": False,
        "errors": [],
        "warnings": [],
        "checked_files": [],
        "rounds_checked": 0,
    }

    if not run_dir.exists():
        add_error(report, f"run directory does not exist: {run_dir}")
        return report

    if (run_dir / "manifest.json").exists():
        report["kind"] = "iteration_loop"
        validate_iteration_run(run_dir=run_dir, repo_root=repo_root, report=report)
    elif (run_dir / "decision.json").exists():
        report["kind"] = "single_run"
        validate_required_files(
            base_dir=run_dir,
            filenames=SINGLE_RUN_REQUIRED_FILES,
            report=report,
        )
        validate_json_object(path=run_dir / "decision.json", report=report)
    else:
        add_error(report, "run has neither manifest.json nor decision.json")

    validate_optional_diagnosis(run_dir=run_dir, report=report)
    validate_optional_metadata(run_dir=run_dir, repo_root=repo_root, report=report)
    validate_optional_champion_comparison(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    validate_optional_research_brief(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    report["ok"] = not report["errors"]
    return report


def validate_iteration_run(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate an iteration-loop run directory."""
    validate_required_files(
        base_dir=run_dir,
        filenames=ITERATION_RUN_REQUIRED_FILES,
        report=report,
    )
    manifest = load_json_object(run_dir / "manifest.json", report)
    if manifest is None:
        return

    validate_json_list(path=run_dir / "candidate_leaderboard.json", report=report)
    validate_optional_agent_result_stats(
        run_dir=run_dir,
        repo_root=repo_root,
        report=report,
    )
    round_ids = round_ids_from_manifest(manifest)
    if not round_ids:
        add_error(report, "manifest.rounds is empty or invalid")
        return

    for round_id in round_ids:
        round_dir = run_dir / round_id
        validate_round_dir(round_dir=round_dir, repo_root=repo_root, report=report)
    report["rounds_checked"] = len(round_ids)


def validate_round_dir(
    *,
    round_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate one iteration round directory."""
    if not round_dir.exists():
        add_error(report, f"round directory does not exist: {round_dir}")
        return

    validate_required_files(
        base_dir=round_dir,
        filenames=ROUND_REQUIRED_FILES,
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "proposal_intent.json",
        schema_path=repo_root / "schemas/proposal_intent.schema.json",
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_input.json",
        schema_path=repo_root / "schemas/agent_input.schema.json",
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_bundle_manifest.json",
        schema_path=repo_root / "schemas/agent_bundle.schema.json",
        report=report,
    )
    validate_agent_bundle_manifest(
        path=round_dir / "agent_bundle_manifest.json",
        repo_root=repo_root,
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_output.json",
        schema_path=repo_root / "schemas/agent_output.schema.json",
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_validation.json",
        schema_path=repo_root / "schemas/agent_validation.schema.json",
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_executor_report.json",
        schema_path=repo_root / "schemas/agent_executor.schema.json",
        report=report,
    )
    validate_agent_executor_report(
        path=round_dir / "agent_executor_report.json",
        repo_root=repo_root,
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_routing_policy.json",
        schema_path=repo_root / "schemas/agent_routing_policy.schema.json",
        report=report,
    )
    validate_agent_routing_policy(
        path=round_dir / "agent_routing_policy.json",
        repo_root=repo_root,
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_attempts_manifest.json",
        schema_path=repo_root / "schemas/agent_attempts.schema.json",
        report=report,
    )
    validate_contract_file(
        payload_path=round_dir / "agent_selection_report.json",
        schema_path=repo_root / "schemas/agent_selection.schema.json",
        report=report,
    )
    validate_agent_attempts_manifest(
        path=round_dir / "agent_attempts_manifest.json",
        repo_root=repo_root,
        report=report,
    )
    validate_agent_selection_report(
        path=round_dir / "agent_selection_report.json",
        repo_root=repo_root,
        report=report,
    )

    proposal = load_json_object(round_dir / "proposal.json", report)
    if proposal and proposal.get("agent_name") == "file_protocol_agent":
        validate_required_files(
            base_dir=round_dir,
            filenames=("agent_execution.json",),
            report=report,
        )
        validate_contract_file(
            payload_path=round_dir / "agent_execution.json",
            schema_path=repo_root / "schemas/agent_execution.schema.json",
            report=report,
        )
    elif (round_dir / "agent_execution.json").exists():
        add_warning(report, f"unexpected agent_execution.json in {round_dir}")
        validate_contract_file(
            payload_path=round_dir / "agent_execution.json",
            schema_path=repo_root / "schemas/agent_execution.schema.json",
            report=report,
        )

    validate_json_object(path=round_dir / "decision.json", report=report)
    validate_json_list(path=round_dir / "proposal_attempts.json", report=report)
    validate_optional_workspace_manifest(
        round_dir=round_dir,
        repo_root=repo_root,
        proposal=proposal,
        report=report,
    )


def validate_optional_workspace_manifest(
    *,
    round_dir: Path,
    repo_root: Path,
    proposal: dict[str, Any] | None,
    report: dict[str, object],
) -> None:
    """Validate workspace_manifest.json for workspace-backed agent rounds."""
    path = round_dir / "workspace_manifest.json"
    has_workspace = bool(proposal and proposal.get("workspace_path"))
    if not path.exists():
        if has_workspace:
            add_error(report, f"missing required workspace manifest: {path}")
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/workspace_manifest.schema.json",
        report=report,
    )


def validate_agent_bundle_manifest(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate bundle dirs and listed files exist."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    for key in ("input_bundle_dir", "output_bundle_dir"):
        bundle_dir = resolve_path(Path(str(payload.get(key, ""))), repo_root)
        if not bundle_dir.exists() or not bundle_dir.is_dir():
            add_error(report, f"{key} does not exist: {bundle_dir}")
    for key in ("input_files", "output_files"):
        rows = payload.get(key, [])
        if not isinstance(rows, list) or not rows:
            add_error(report, f"agent_bundle_manifest.json {key} is empty or invalid")
            continue
        for row in rows:
            if not isinstance(row, dict):
                add_error(report, f"agent_bundle_manifest.json {key} contains non-object")
                continue
            file_path = resolve_path(Path(str(row.get("path", ""))), repo_root)
            if not file_path.exists() or not file_path.is_file():
                add_error(report, f"bundle file does not exist: {file_path}")


def validate_agent_attempts_manifest(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate per-attempt trace dirs and listed files exist."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    attempts_dir = resolve_path(Path(str(payload.get("attempts_dir", ""))), repo_root)
    if not attempts_dir.exists() or not attempts_dir.is_dir():
        add_error(report, f"attempts_dir does not exist: {attempts_dir}")
    rows = payload.get("attempts", [])
    if not isinstance(rows, list) or not rows:
        add_error(report, "agent_attempts_manifest.json attempts is empty or invalid")
        return
    for row in rows:
        if not isinstance(row, dict):
            add_error(report, "agent_attempts_manifest.json attempts contains non-object")
            continue
        attempt_dir = resolve_path(Path(str(row.get("attempt_dir", ""))), repo_root)
        if not attempt_dir.exists() or not attempt_dir.is_dir():
            add_error(report, f"attempt_dir does not exist: {attempt_dir}")
        else:
            attempt_input = attempt_dir / "agent_input.json"
            if attempt_input.exists():
                checked_files(report).append(str(attempt_input))
                validate_contract_file(
                    payload_path=attempt_input,
                    schema_path=repo_root / "schemas/agent_input.schema.json",
                    report=report,
                )
            else:
                add_error(report, f"attempt agent_input.json does not exist: {attempt_input}")
            attempt_output = attempt_dir / "attempt_output.json"
            if attempt_output.exists():
                checked_files(report).append(str(attempt_output))
                validate_contract_file(
                    payload_path=attempt_output,
                    schema_path=repo_root / "schemas/attempt_output.schema.json",
                    report=report,
                )
                validate_attempt_output_artifacts(
                    path=attempt_output,
                    repo_root=repo_root,
                    report=report,
                )
            else:
                add_error(report, f"attempt_output.json does not exist: {attempt_output}")
            replay_path = attempt_dir / "attempt_replay.json"
            if replay_path.exists():
                checked_files(report).append(str(replay_path))
                validate_contract_file(
                    payload_path=replay_path,
                    schema_path=repo_root / "schemas/attempt_replay.schema.json",
                    report=report,
                )
        file_rows = row.get("files", [])
        if not isinstance(file_rows, list) or not file_rows:
            add_error(report, f"attempt has no file records: {row.get('attempt_id', '')}")
            continue
        for file_row in file_rows:
            if not isinstance(file_row, dict):
                add_error(report, "attempt file record is non-object")
                continue
            file_path = resolve_path(Path(str(file_row.get("path", ""))), repo_root)
            if not file_path.exists() or not file_path.is_file():
                add_error(report, f"attempt file does not exist: {file_path}")


def validate_attempt_output_artifacts(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate attempt_output.json points at existing audit files."""
    payload = load_json_object(path, report)
    if payload is None:
        return
    artifacts = payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        add_error(report, f"attempt_output.json artifacts is invalid: {path}")
        return
    required = (
        "attempt",
        "agent_input",
        "proposal",
        "raw_agent_output",
        "patch",
        "selection",
        "round_agent_input",
        "round_agent_output",
        "round_agent_validation",
    )
    optional = ("workspace_manifest", "agent_execution")
    for key in required:
        artifact_path = resolve_path(Path(str(artifacts.get(key, ""))), repo_root)
        if not artifact_path.exists() or not artifact_path.is_file():
            add_error(report, f"attempt_output artifact does not exist: {key}={artifact_path}")
    for key in optional:
        value = str(artifacts.get(key, ""))
        if not value:
            continue
        artifact_path = resolve_path(Path(value), repo_root)
        if not artifact_path.exists() or not artifact_path.is_file():
            add_error(report, f"attempt_output artifact does not exist: {key}={artifact_path}")


def validate_agent_executor_report(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate executor rows point at existing attempt/runtime artifacts."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    rows = payload.get("attempts", [])
    if not isinstance(rows, list) or not rows:
        add_error(report, "agent_executor_report.json attempts is empty or invalid")
        return
    selected_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            add_error(report, "agent_executor_report.json attempts contains non-object")
            continue
        if bool(row.get("selected", False)):
            selected_rows += 1
        artifacts = row.get("artifacts", {})
        if not isinstance(artifacts, dict):
            add_error(report, "agent_executor_report.json artifacts is non-object")
            continue
        for key in ("attempt_dir", "workspace_manifest", "agent_execution"):
            value = str(artifacts.get(key, ""))
            if not value:
                continue
            artifact_path = resolve_path(Path(value), repo_root)
            if key == "attempt_dir":
                if not artifact_path.exists() or not artifact_path.is_dir():
                    add_error(
                        report,
                        f"executor attempt_dir does not exist: {artifact_path}",
                    )
            elif not artifact_path.exists() or not artifact_path.is_file():
                add_error(report, f"executor artifact does not exist: {artifact_path}")
    if selected_rows != 1:
        add_error(
            report,
            f"agent_executor_report.json must have exactly one selected row, got {selected_rows}",
        )


def validate_agent_routing_policy(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate routing policy rows and referenced attempt artifacts."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    rows = payload.get("candidates", [])
    if not isinstance(rows, list) or not rows:
        add_error(report, "agent_routing_policy.json candidates is empty or invalid")
        return
    selected_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            add_error(report, "agent_routing_policy.json candidates contains non-object")
            continue
        if bool(row.get("selected", False)):
            selected_rows += 1
        artifacts = row.get("artifacts", {})
        if not isinstance(artifacts, dict):
            add_error(report, "agent_routing_policy.json artifacts is non-object")
            continue
        attempt_dir = resolve_path(
            Path(str(artifacts.get("attempt_dir", ""))),
            repo_root,
        )
        if not attempt_dir.exists() or not attempt_dir.is_dir():
            add_error(report, f"routing attempt_dir does not exist: {attempt_dir}")
        for key in ("attempt_output", "agent_input", "selection", "proposal"):
            artifact_path = resolve_path(Path(str(artifacts.get(key, ""))), repo_root)
            if not artifact_path.exists() or not artifact_path.is_file():
                add_error(
                    report,
                    f"routing artifact does not exist: {key}={artifact_path}",
                )
    if selected_rows != 1:
        add_error(
            report,
            f"agent_routing_policy.json must have exactly one selected row, got {selected_rows}",
        )
    selected_attempt_id = str(payload.get("selected_attempt_id", ""))
    if selected_attempt_id and not any(
        isinstance(row, dict)
        and bool(row.get("selected", False))
        and str(row.get("attempt_id", "")) == selected_attempt_id
        for row in rows
    ):
        add_error(
            report,
            "agent_routing_policy.json selected_attempt_id does not match selected row",
        )


def validate_agent_selection_report(
    *,
    path: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate selection report rows point at real attempt dirs."""
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    rows = payload.get("attempts", [])
    if not isinstance(rows, list) or not rows:
        add_error(report, "agent_selection_report.json attempts is empty or invalid")
        return
    selected_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            add_error(report, "agent_selection_report.json attempts contains non-object")
            continue
        if bool(row.get("selected", False)):
            selected_rows += 1
        attempt_dir = resolve_path(Path(str(row.get("attempt_dir", ""))), repo_root)
        if not attempt_dir.exists() or not attempt_dir.is_dir():
            add_error(report, f"selection attempt_dir does not exist: {attempt_dir}")
        selection_file = attempt_dir / "selection.json"
        if not selection_file.exists():
            add_error(report, f"missing per-attempt selection file: {selection_file}")
    if selected_rows != 1:
        add_error(
            report,
            f"agent_selection_report.json must have exactly one selected row, got {selected_rows}",
        )


def validate_required_files(
    *,
    base_dir: Path,
    filenames: tuple[str, ...],
    report: dict[str, object],
) -> None:
    """Check required files exist and record present files."""
    for filename in filenames:
        path = base_dir / filename
        if not path.exists():
            add_error(report, f"missing required artifact: {path}")
            continue
        checked_files(report).append(str(path))


def validate_optional_diagnosis(
    *,
    run_dir: Path,
    report: dict[str, object],
) -> None:
    """Validate diagnosis.json when a run has one."""
    path = run_dir / "diagnosis.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_json_object(path=path, report=report)


def validate_optional_metadata(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate run_metadata.json when a run has one."""
    path = run_dir / "run_metadata.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/run_metadata.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, f"run_metadata.json run_id does not match report: {path}")


def validate_optional_champion_comparison(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate champion_comparison.json when a run has one."""
    path = run_dir / "champion_comparison.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/champion_comparison.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(
            report,
            f"champion_comparison.json run_id does not match report: {path}",
        )


def validate_optional_research_brief(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate research_brief.json/md when a run has one."""
    path = run_dir / "research_brief.json"
    md_path = run_dir / "research_brief.md"
    if not path.exists() and not md_path.exists():
        return
    if not path.exists():
        add_error(report, f"missing research brief JSON artifact: {path}")
        return
    if not md_path.exists():
        add_error(report, f"missing research brief markdown artifact: {md_path}")
    checked_files(report).append(str(path))
    if md_path.exists():
        checked_files(report).append(str(md_path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/research_brief.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, f"research_brief.json run_id does not match report: {path}")


def validate_optional_agent_result_stats(
    *,
    run_dir: Path,
    repo_root: Path,
    report: dict[str, object],
) -> None:
    """Validate agent_result_stats.json when a run has one."""
    path = run_dir / "agent_result_stats.json"
    if not path.exists():
        return
    checked_files(report).append(str(path))
    validate_contract_file(
        payload_path=path,
        schema_path=repo_root / "schemas/agent_result_stats.schema.json",
        report=report,
    )
    payload = validate_json_object(path=path, report=report)
    if payload is None:
        return
    if payload.get("run_id") != report.get("run_id"):
        add_error(report, f"agent_result_stats.json run_id does not match report: {path}")


def validate_contract_file(
    *,
    payload_path: Path,
    schema_path: Path,
    report: dict[str, object],
) -> None:
    """Validate a JSON artifact against a schema."""
    if not payload_path.exists():
        return
    if not schema_path.exists():
        add_error(report, f"schema file does not exist: {schema_path}")
        return
    try:
        errors = validate_json_file(payload_path=payload_path, schema_path=schema_path)
    except Exception as exc:
        add_error(report, f"could not validate {payload_path}: {exc}")
        return
    for error in errors:
        add_error(report, f"{payload_path}: {error}")


def validate_json_object(*, path: Path, report: dict[str, object]) -> dict[str, Any] | None:
    """Load a JSON object artifact."""
    payload = load_json_object(path, report)
    return payload


def validate_json_list(*, path: Path, report: dict[str, object]) -> list[Any] | None:
    """Load a JSON list artifact."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        add_error(report, f"could not read JSON artifact {path}: {exc}")
        return None
    if not isinstance(payload, list):
        add_error(report, f"JSON artifact must be a list: {path}")
        return None
    return payload


def load_json_object(path: Path, report: dict[str, object]) -> dict[str, Any] | None:
    """Load a JSON object artifact."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        add_error(report, f"could not read JSON artifact {path}: {exc}")
        return None
    if not isinstance(payload, dict):
        add_error(report, f"JSON artifact must be an object: {path}")
        return None
    return payload


def round_ids_from_manifest(manifest: dict[str, Any]) -> list[str]:
    """Return round ids from an iteration manifest."""
    raw_rounds = manifest.get("rounds", [])
    if not isinstance(raw_rounds, list):
        return []
    round_ids: list[str] = []
    for row in raw_rounds:
        if isinstance(row, dict) and isinstance(row.get("round_id"), str):
            round_ids.append(str(row["round_id"]))
    return round_ids


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve paths relative to the repository root."""
    return path if path.is_absolute() else repo_root / path


def checked_files(report: dict[str, object]) -> list[str]:
    """Return the mutable checked_files list from a report."""
    return report["checked_files"]  # type: ignore[return-value]


def add_error(report: dict[str, object], message: str) -> None:
    """Append an error to a validation report."""
    errors = report["errors"]  # type: ignore[assignment]
    errors.append(message)


def add_warning(report: dict[str, object], message: str) -> None:
    """Append a warning to a validation report."""
    warnings = report["warnings"]  # type: ignore[assignment]
    warnings.append(message)


def main() -> None:
    """CLI entrypoint for artifact validation."""
    parser = argparse.ArgumentParser(description="Validate SuanAgent run artifacts.")
    parser.add_argument("run_id", help="Experiment run id under experiments/.")
    parser.add_argument(
        "--experiments-dir",
        type=Path,
        default=Path("experiments"),
        help="Directory containing experiment artifacts.",
    )
    args = parser.parse_args()

    payload = validate_run_artifacts(
        run_id=args.run_id,
        experiments_dir=args.experiments_dir,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
