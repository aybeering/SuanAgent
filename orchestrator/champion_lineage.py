"""Read-only champion lineage report from saved promotion artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.experiments import (
    CHAMPION_SCHEMA_VERSION,
    champion_history_path,
    champion_path,
)
from orchestrator.schema_validation import (
    load_schema,
    validate_json_file,
    validate_json_payload,
)


CHAMPION_LINEAGE_SCHEMA_VERSION = "champion_lineage_v1"
SCHEMA_PATH = Path("schemas/champion_lineage.schema.json")


def write_champion_lineage(
    *,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown champion lineage artifacts."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    payload = build_champion_lineage(
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    errors = validate_champion_lineage_payload(
        payload,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "champion lineage failed schema validation: " + "; ".join(errors)
        )
    json_path = experiments_dir / "champion_lineage.json"
    md_path = experiments_dir / "champion_lineage.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_champion_lineage_markdown(payload), encoding="utf-8")
    file_errors = validate_champion_lineage_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if file_errors:
        raise ValueError(
            "champion lineage failed schema validation: " + "; ".join(file_errors)
        )
    return json_path, md_path, payload


def build_champion_lineage(
    *,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Build a deterministic lineage report from saved champion artifacts."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    champion_file = champion_path(experiments_dir)
    history_file = champion_history_path(experiments_dir)
    champion_payload = load_json_object(champion_file)
    history_rows, parse_errors = read_history(path=history_file)
    lineage = [
        lineage_row(
            index=index,
            event=event,
            experiments_dir=experiments_dir,
        )
        for index, event in enumerate(history_rows, start=1)
    ]
    current = current_champion_summary(
        champion_path=champion_file,
        champion=champion_payload,
    )
    checks = lineage_checks(
        current=current,
        lineage=lineage,
        parse_errors=parse_errors,
    )
    return {
        "schema_version": CHAMPION_LINEAGE_SCHEMA_VERSION,
        "experiments_dir": str(experiments_dir),
        "current_champion": current,
        "history": {
            "path": str(history_file),
            "exists": history_file.exists(),
            "sha256": file_sha256(history_file),
            "event_count": len(history_rows),
            "parse_error_count": len(parse_errors),
            "parse_errors": parse_errors,
        },
        "lineage": lineage,
        "checks": checks,
        "ok": bool(checks["ok"]),
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_apply_patches": True,
            "does_not_route_agents": True,
            "does_not_change_acceptance": True,
            "does_not_write_champion_registry": True,
            "does_not_append_champion_history": True,
            "does_not_promote_champion": True,
        },
    }


def current_champion_summary(
    *,
    champion_path: Path,
    champion: dict[str, Any],
) -> dict[str, object]:
    """Return compact current champion registry context."""
    exists = bool(champion)
    return {
        "exists": exists,
        "path": str(champion_path),
        "sha256": file_sha256(champion_path),
        "schema_version": str(champion.get("schema_version", CHAMPION_SCHEMA_VERSION)),
        "champion_run_id": str(champion.get("champion_run_id", "")),
        "promoted_from_run_id": str(champion.get("promoted_from_run_id", "")),
        "promoted_at": str(champion.get("promoted_at", "")),
        "source_kind": str(champion.get("source_kind", "")),
        "source_status": str(champion.get("source_status", "")),
        "strategy_commit": str(champion.get("strategy_commit", "")),
        "validation_ev_delta": optional_float(champion.get("validation_ev_delta")),
        "trade_count_delta": optional_int(champion.get("trade_count_delta")),
    }


def read_history(*, path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Read append-only champion history rows."""
    if not path.exists():
        return [], []
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: {exc.msg}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"line {line_number}: expected object")
            continue
        rows.append(payload)
    return rows, errors


def lineage_row(
    *,
    index: int,
    event: dict[str, Any],
    experiments_dir: Path,
) -> dict[str, object]:
    """Return one compact lineage event with evidence file hashes."""
    run_id = str(event.get("champion_run_id", ""))
    promoted_from = str(event.get("promoted_from_run_id", ""))
    run_dir = experiments_dir / run_id
    approval_path = run_dir / "champion_promotion_approval.json"
    dry_run_path = run_dir / "champion_promotion_dry_run.json"
    receipt_path = run_dir / "champion_promotion_receipt.json"
    receipt = load_json_object(receipt_path)
    comparison = object_field(event, "comparison")
    metric_deltas = object_field(comparison, "metric_deltas")
    promotion_source = "approved_receipt" if bool(receipt.get("promoted", False)) else "legacy_direct"
    return {
        "index": index,
        "champion_run_id": run_id,
        "promoted_from_run_id": promoted_from,
        "promoted_at": str(event.get("promoted_at", "")),
        "promotion_source": promotion_source,
        "source_kind": str(event.get("source_kind", "")),
        "source_status": str(event.get("source_status", "")),
        "source_best_round": event.get("source_best_round"),
        "strategy_commit": str(event.get("strategy_commit", "")),
        "validation_ev_delta": optional_float(event.get("validation_ev_delta")),
        "trade_count_delta": optional_int(event.get("trade_count_delta")),
        "comparison_summary": str(event.get("comparison_summary", "")),
        "promotion_reasons": string_list(event.get("promotion_reasons", [])),
        "comparison_metric_deltas": {
            "validation_ev_delta": optional_float(metric_deltas.get("validation_ev_delta")),
            "trade_count_delta": optional_int(metric_deltas.get("trade_count_delta")),
        },
        "evidence": {
            "run_dir": str(run_dir),
            "approval": file_record(approval_path),
            "dry_run": file_record(dry_run_path),
            "receipt": file_record(receipt_path),
            "receipt_promoted": bool(receipt.get("promoted", False)),
        },
    }


def lineage_checks(
    *,
    current: dict[str, object],
    lineage: list[dict[str, object]],
    parse_errors: list[str],
) -> dict[str, object]:
    """Return deterministic lineage consistency checks."""
    current_exists = bool(current.get("exists", False))
    last = lineage[-1] if lineage else {}
    current_run_id = str(current.get("champion_run_id", ""))
    last_run_id = str(last.get("champion_run_id", ""))
    current_matches_last = (
        not current_exists or bool(lineage) and current_run_id == last_run_id
    )
    return {
        "ok": not parse_errors and current_matches_last,
        "current_champion_matches_last_history": current_matches_last,
        "history_parse_error_count": len(parse_errors),
        "lineage_event_count": len(lineage),
        "current_champion_run_id": current_run_id,
        "last_history_champion_run_id": last_run_id,
    }


def render_champion_lineage_markdown(payload: dict[str, object]) -> str:
    """Render champion lineage as markdown."""
    current = object_field(payload, "current_champion")
    history = object_field(payload, "history")
    checks = object_field(payload, "checks")
    lineage_raw = payload.get("lineage", [])
    lineage = lineage_raw if isinstance(lineage_raw, list) else []
    lines = [
        "# Champion Lineage",
        "",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Current champion: `{current.get('champion_run_id', '') or 'none'}`",
        f"- Current champion SHA-256: `{current.get('sha256', '')}`",
        f"- History events: `{history.get('event_count', 0)}`",
        f"- Parse errors: `{history.get('parse_error_count', 0)}`",
        f"- Current matches last history: `{checks.get('current_champion_matches_last_history', False)}`",
        "",
        "## Events",
        "",
    ]
    if not lineage:
        lines.append("No champion promotion events have been recorded.")
    else:
        lines.extend(
            [
                "| # | Champion | From | Source | EV Delta | Receipt |",
                "| --- | --- | --- | --- | ---: | --- |",
            ]
        )
        for row_raw in lineage:
            row = row_raw if isinstance(row_raw, dict) else {}
            evidence = object_field(row, "evidence")
            receipt = object_field(evidence, "receipt")
            lines.append(
                "| "
                f"{row.get('index', '')} | "
                f"`{row.get('champion_run_id', '')}` | "
                f"`{row.get('promoted_from_run_id', '')}` | "
                f"`{row.get('promotion_source', '')}` | "
                f"{number_text(row.get('validation_ev_delta'))} | "
                f"`{receipt.get('sha256', '')}` |"
            )
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This report is read-only and uses saved champion artifacts only.",
            "- It does not execute agents, run backtests, apply patches, route agents, promote champions, write champion registry files, append champion history, or change acceptance.",
        ]
    )
    return "\n".join(lines) + "\n"


def validate_champion_lineage_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved champion lineage report."""
    schema_errors = validate_json_file(
        payload_path=payload_path,
        schema_path=repo_root / SCHEMA_PATH,
    )
    if schema_errors:
        return schema_errors
    return schema_errors + validate_champion_lineage_consistency(
        load_json_object(payload_path)
    )


def validate_champion_lineage_payload(
    payload: dict[str, object],
    *,
    experiments_dir: Path | None = None,
    repo_root: Path = Path("."),
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an in-memory champion lineage payload."""
    repo_root = repo_root.resolve()
    comparable_payload = strip_terminal_metadata(payload)
    schema = load_schema(repo_root / SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=comparable_payload,
            schema=schema,
            schema_dir=(repo_root / SCHEMA_PATH).parent,
        )
    )
    errors.extend(validate_champion_lineage_consistency(comparable_payload))
    if require_current_evidence:
        resolved_experiments_dir = lineage_experiments_dir(
            payload=comparable_payload,
            experiments_dir=experiments_dir,
            repo_root=repo_root,
        )
        if resolved_experiments_dir is None:
            errors.append("champion_lineage experiments_dir required")
        else:
            expected = build_champion_lineage(
                experiments_dir=resolved_experiments_dir,
                repo_root=repo_root,
            )
            if comparable_payload != expected:
                errors.append("champion_lineage current evidence mismatch")
    return tuple(errors)


def strip_terminal_metadata(payload: dict[str, object]) -> dict[str, object]:
    """Return payload without terminal-only annotation fields."""
    stripped = dict(payload)
    stripped.pop("from_artifact", None)
    return stripped


def lineage_experiments_dir(
    *,
    payload: dict[str, object],
    experiments_dir: Path | None,
    repo_root: Path,
) -> Path | None:
    """Return the experiments directory used for current-evidence validation."""
    if experiments_dir is not None:
        return resolve_path(experiments_dir, repo_root)
    raw_path = str(payload.get("experiments_dir", ""))
    return resolve_path(Path(raw_path), repo_root) if raw_path else None


def validate_champion_lineage_consistency(
    payload: dict[str, object],
) -> tuple[str, ...]:
    """Validate derived champion lineage fields against the payload."""
    errors: list[str] = []
    current = object_field(payload, "current_champion")
    history = object_field(payload, "history")
    checks = object_field(payload, "checks")
    lineage = list_of_dicts(payload.get("lineage", []))
    parse_errors = string_list(history.get("parse_errors", []))

    if int(history.get("event_count", -1)) != len(lineage):
        errors.append("champion_lineage history event_count mismatch")
    if int(history.get("parse_error_count", -1)) != len(parse_errors):
        errors.append("champion_lineage history parse_error_count mismatch")

    expected_indexes = list(range(1, len(lineage) + 1))
    observed_indexes = [int(row.get("index", 0) or 0) for row in lineage]
    if observed_indexes != expected_indexes:
        errors.append("champion_lineage row index mismatch")

    current_exists = bool(current.get("exists", False))
    current_run_id = str(current.get("champion_run_id", ""))
    last_run_id = str(lineage[-1].get("champion_run_id", "")) if lineage else ""
    current_matches_last = (
        not current_exists or bool(lineage) and current_run_id == last_run_id
    )
    expected_ok = not parse_errors and current_matches_last

    if bool(checks.get("current_champion_matches_last_history", False)) != (
        current_matches_last
    ):
        errors.append("champion_lineage current match mismatch")
    if int(checks.get("history_parse_error_count", -1)) != len(parse_errors):
        errors.append("champion_lineage check parse_error_count mismatch")
    if int(checks.get("lineage_event_count", -1)) != len(lineage):
        errors.append("champion_lineage check event_count mismatch")
    if str(checks.get("current_champion_run_id", "")) != current_run_id:
        errors.append("champion_lineage check current run mismatch")
    if str(checks.get("last_history_champion_run_id", "")) != last_run_id:
        errors.append("champion_lineage check last run mismatch")
    if bool(checks.get("ok", False)) != expected_ok:
        errors.append("champion_lineage check ok mismatch")
    if bool(payload.get("ok", False)) != expected_ok:
        errors.append("champion_lineage ok mismatch")

    errors.extend(validate_champion_lineage_rows(lineage))
    errors.extend(validate_champion_lineage_policy(payload))
    return tuple(errors)


def validate_champion_lineage_rows(
    lineage: list[dict[str, Any]],
) -> tuple[str, ...]:
    """Validate row-level champion lineage derivations."""
    errors: list[str] = []
    for row in lineage:
        evidence = object_field(row, "evidence")
        receipt = object_field(evidence, "receipt")
        receipt_exists = bool(receipt.get("exists", False))
        expected_source = (
            "approved_receipt"
            if bool(evidence.get("receipt_promoted", False))
            else "legacy_direct"
        )
        if str(row.get("promotion_source", "")) != expected_source:
            errors.append("champion_lineage promotion_source mismatch")
        if bool(evidence.get("receipt_promoted", False)) and not receipt_exists:
            errors.append("champion_lineage receipt promoted without receipt")
    return tuple(errors)


def validate_champion_lineage_policy(payload: dict[str, object]) -> tuple[str, ...]:
    """Validate champion lineage policy flags preserve read-only behavior."""
    errors: list[str] = []
    policy = object_field(payload, "policy")
    for key in (
        "inspection_only",
        "reads_saved_artifacts_only",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_change_acceptance",
        "does_not_write_champion_registry",
        "does_not_append_champion_history",
        "does_not_promote_champion",
    ):
        if policy.get(key) is not True:
            errors.append(f"champion_lineage policy false: {key}")
    return tuple(errors)


def file_record(path: Path) -> dict[str, object]:
    """Return a deterministic file record."""
    return {
        "path": str(path),
        "exists": path.exists(),
        "sha256": file_sha256(path),
        "byte_count": path.stat().st_size if path.exists() else 0,
    }


def file_sha256(path: Path) -> str:
    """Return SHA-256 for a file or an empty string when missing."""
    if not path.exists() or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object or return an empty mapping."""
    if not path.exists() or not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def object_field(payload: dict[str, Any] | dict[str, object], key: str) -> dict[str, Any]:
    """Return a nested object field."""
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def list_of_dicts(value: object) -> list[dict[str, Any]]:
    """Return dictionaries from a JSON list value."""
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def string_list(value: object) -> list[str]:
    """Return string rows from a list-like value."""
    return [str(item) for item in value] if isinstance(value, list) else []


def optional_float(value: object) -> float | None:
    """Return a float when possible."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def optional_int(value: object) -> int | None:
    """Return an integer when possible."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def number_text(value: object) -> str:
    """Return compact numeric display text."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):.6f}"
    return ""


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root."""
    return path if path.is_absolute() else repo_root / path


def main() -> None:
    """CLI entrypoint for champion lineage reports."""
    parser = argparse.ArgumentParser(description="Write a read-only champion lineage report.")
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    _, _, payload = write_champion_lineage(
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
