"""Guarded champion promotion execution from approved dry-run evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.champion_promotion_approval import (
    CHAMPION_PROMOTION_APPROVAL_SCHEMA_VERSION,
)
from orchestrator.champion_promotion_dry_run import (
    CHAMPION_PROMOTION_DRY_RUN_SCHEMA_VERSION,
    approved_promotion_command,
)
from orchestrator.experiments import (
    compare_experiments,
    promote_champion,
    show_champion,
)
from orchestrator.schema_validation import (
    load_schema,
    validate_json_file,
    validate_json_payload,
)


CHAMPION_PROMOTION_RECEIPT_SCHEMA_VERSION = "champion_promotion_receipt_v1"
SCHEMA_PATH = Path("schemas/champion_promotion_receipt.schema.json")


def promote_champion_with_approval(
    *,
    candidate_run_id: str,
    approval_path: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    min_ev_delta: float = 0.0,
) -> dict[str, object]:
    """Promote a candidate only when saved approval evidence still matches."""
    repo_root = repo_root.resolve()
    experiments_dir = resolve_path(experiments_dir, repo_root)
    approval_path = resolve_path(approval_path, repo_root)
    run_dir = experiments_dir / candidate_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    approval = load_json_object(approval_path)
    dry_run_path = resolve_path(
        Path(str(object_field(approval, "reviewed_command").get("source_dry_run_path", ""))),
        repo_root,
    )
    dry_run = load_json_object(dry_run_path)
    checks = promotion_evidence_checks(
        candidate_run_id=candidate_run_id,
        approval_path=approval_path,
        approval=approval,
        dry_run_path=dry_run_path,
        dry_run=dry_run,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        min_ev_delta=min_ev_delta,
    )
    promoted = False
    promotion_result: dict[str, object] = {}
    if checks["ok"]:
        decision = object_field(dry_run, "dry_run_decision")
        base_run_id = str(decision.get("base_run_id", ""))
        promotion_result = promote_champion(
            base_run_id=base_run_id,
            candidate_run_id=candidate_run_id,
            experiments_dir=experiments_dir,
            min_ev_delta=min_ev_delta,
        )
        promoted = bool(promotion_result.get("promoted", False))
        if not promoted:
            checks["ok"] = False
            checks["blockers"].append("promote_function_declined")

    receipt = build_receipt_payload(
        candidate_run_id=candidate_run_id,
        experiments_dir=experiments_dir,
        approval_path=approval_path,
        dry_run_path=dry_run_path,
        checks=checks,
        promoted=promoted,
        promotion_result=promotion_result,
    )
    write_receipt(run_dir=run_dir, payload=receipt, repo_root=repo_root)
    return receipt


def promotion_evidence_checks(
    *,
    candidate_run_id: str,
    approval_path: Path,
    approval: dict[str, Any],
    dry_run_path: Path,
    dry_run: dict[str, Any],
    experiments_dir: Path,
    repo_root: Path,
    min_ev_delta: float,
) -> dict[str, Any]:
    """Return deterministic blockers for guarded champion promotion."""
    blockers: list[str] = []
    approval_errors = (
        validate_json_file(
            payload_path=approval_path,
            schema_path=repo_root / "schemas/champion_promotion_approval.schema.json",
        )
        if approval_path.exists() and approval_path.is_file()
        else ("missing_approval_file",)
    )
    if approval_errors:
        blockers.append("approval_schema_invalid")
    if approval.get("schema_version") != CHAMPION_PROMOTION_APPROVAL_SCHEMA_VERSION:
        blockers.append("approval_schema_version_invalid")
    if approval.get("ok") is not True:
        blockers.append("approval_not_ok")
    if approval.get("status") != "approval_recorded":
        blockers.append("approval_not_recorded")

    intent = object_field(approval, "operator_intent")
    if intent.get("approval_recorded") is not True:
        blockers.append("operator_approval_not_recorded")
    if intent.get("explicit_approval") is not True:
        blockers.append("explicit_approval_missing")
    if intent.get("confirmation_phrase_matches") is not True:
        blockers.append("confirmation_phrase_mismatch")

    if str(approval.get("run_id", "")) != candidate_run_id:
        blockers.append("approval_run_id_mismatch")

    reviewed = object_field(approval, "reviewed_command")
    reviewed_command = str(reviewed.get("command", ""))
    expected_command = approved_promotion_command(
        candidate_run_id=candidate_run_id,
        approval_path=approval_path,
    )
    if reviewed_command != expected_command:
        blockers.append("reviewed_command_mismatch")
    if str(reviewed.get("command_sha256", "")) != sha256_text(reviewed_command):
        blockers.append("reviewed_command_digest_mismatch")

    recorded_dry_sha = str(reviewed.get("source_dry_run_sha256", ""))
    if not dry_run_path.exists():
        blockers.append("source_dry_run_missing")
    elif recorded_dry_sha != file_sha256(dry_run_path):
        blockers.append("source_dry_run_digest_mismatch")

    dry_errors = (
        validate_json_file(
            payload_path=dry_run_path,
            schema_path=repo_root / "schemas/champion_promotion_dry_run.schema.json",
        )
        if dry_run_path.exists() and dry_run_path.is_file()
        else ("missing_dry_run_file",)
    )
    if dry_errors:
        blockers.append("dry_run_schema_invalid")
    if dry_run.get("schema_version") != CHAMPION_PROMOTION_DRY_RUN_SCHEMA_VERSION:
        blockers.append("dry_run_schema_version_invalid")
    if dry_run.get("ok") is not True:
        blockers.append("dry_run_not_ok")
    if str(dry_run.get("run_id", "")) != candidate_run_id:
        blockers.append("dry_run_run_id_mismatch")

    decision = object_field(dry_run, "dry_run_decision")
    if decision.get("would_promote") is not True:
        blockers.append("dry_run_does_not_recommend_promotion")

    base_run_id = str(decision.get("base_run_id", ""))
    if not base_run_id:
        blockers.append("base_run_id_missing")

    champion = show_champion(experiments_dir=experiments_dir)
    champion_payload = object_field(champion, "champion")
    current_champion_run_id = str(champion_payload.get("champion_run_id", ""))
    if current_champion_run_id != base_run_id:
        blockers.append("current_champion_drift")

    comparison: dict[str, object] = {}
    if base_run_id:
        comparison = compare_experiments(
            base_run_id=base_run_id,
            candidate_run_id=candidate_run_id,
            experiments_dir=experiments_dir,
            min_ev_delta=min_ev_delta,
        )
        if comparison.get("recommendation") != "promote_candidate":
            blockers.append("comparison_no_longer_recommends_promotion")

    return {
        "ok": not blockers,
        "blockers": unique_strings(blockers),
        "approval_schema_errors": list(approval_errors),
        "dry_run_schema_errors": list(dry_errors),
        "expected_command": expected_command,
        "reviewed_command": reviewed_command,
        "base_run_id": base_run_id,
        "current_champion_run_id": current_champion_run_id,
        "comparison": comparison,
    }


def build_receipt_payload(
    *,
    candidate_run_id: str,
    experiments_dir: Path,
    approval_path: Path,
    dry_run_path: Path,
    checks: dict[str, Any],
    promoted: bool,
    promotion_result: dict[str, object],
) -> dict[str, object]:
    """Build the saved promotion execution receipt."""
    status = "promoted" if promoted else "blocked"
    return {
        "schema_version": CHAMPION_PROMOTION_RECEIPT_SCHEMA_VERSION,
        "candidate_run_id": candidate_run_id,
        "base_run_id": str(checks.get("base_run_id", "")),
        "experiments_dir": str(experiments_dir),
        "status": status,
        "ok": True,
        "promoted": promoted,
        "approval_path": str(approval_path),
        "approval_sha256": file_sha256(approval_path),
        "source_dry_run_path": str(dry_run_path),
        "source_dry_run_sha256": file_sha256(dry_run_path),
        "evidence_checks": {
            "ok": bool(checks.get("ok", False)),
            "blockers": string_list(checks.get("blockers", [])),
            "approval_schema_errors": string_list(
                checks.get("approval_schema_errors", [])
            ),
            "dry_run_schema_errors": string_list(checks.get("dry_run_schema_errors", [])),
            "expected_command": str(checks.get("expected_command", "")),
            "reviewed_command": str(checks.get("reviewed_command", "")),
            "current_champion_run_id": str(checks.get("current_champion_run_id", "")),
        },
        "comparison": object_field(checks, "comparison"),
        "promotion_result": promotion_result,
        "policy": {
            "requires_approval_artifact": True,
            "requires_approval_recorded": True,
            "requires_command_digest_match": True,
            "requires_source_dry_run_digest_match": True,
            "requires_current_champion_match": True,
            "requires_current_comparison_recommendation": True,
            "writes_only_champion_registry_and_history": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_apply_patches": True,
            "does_not_route_agents": True,
            "does_not_change_acceptance": True,
        },
    }


def write_receipt(
    *,
    run_dir: Path,
    payload: dict[str, object],
    repo_root: Path,
) -> tuple[Path, Path]:
    """Write machine-readable and markdown promotion execution receipts."""
    json_path = run_dir / "champion_promotion_receipt.json"
    md_path = run_dir / "champion_promotion_receipt.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_receipt_markdown(payload), encoding="utf-8")
    errors = validate_champion_promotion_receipt_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(f"champion promotion receipt failed schema validation: {errors}")
    return json_path, md_path


def render_receipt_markdown(payload: dict[str, object]) -> str:
    """Render a promotion receipt as markdown."""
    checks = object_field(payload, "evidence_checks")
    lines = [
        "# Champion Promotion Receipt",
        "",
        f"- Candidate run: `{payload.get('candidate_run_id', '')}`",
        f"- Base run: `{payload.get('base_run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- Promoted: `{payload.get('promoted', False)}`",
        f"- Evidence OK: `{checks.get('ok', False)}`",
        f"- Approval SHA-256: `{payload.get('approval_sha256', '')}`",
        f"- Source dry-run SHA-256: `{payload.get('source_dry_run_sha256', '')}`",
        "",
        "## Blockers",
        "",
    ]
    blockers = string_list(checks.get("blockers", []))
    lines.extend([f"- `{blocker}`" for blocker in blockers] or ["- none"])
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- Promotion requires a recorded approval artifact, matching command digest, matching source dry-run digest, unchanged champion identity, and a current promote recommendation.",
            "- This command does not execute agents, run backtests, apply patches, route agents, or change iteration acceptance.",
        ]
    )
    return "\n".join(lines) + "\n"


def validate_champion_promotion_receipt_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved champion promotion execution receipt."""
    schema_errors = validate_json_file(
        payload_path=payload_path,
        schema_path=repo_root / SCHEMA_PATH,
    )
    if schema_errors:
        return schema_errors
    return validate_champion_promotion_receipt_consistency(load_json_object(payload_path))


def validate_champion_promotion_receipt_payload(
    payload: dict[str, object],
    *,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate an in-memory champion promotion execution receipt."""
    schema = load_schema(repo_root / SCHEMA_PATH)
    schema_errors = validate_json_payload(
        payload=payload,
        schema=schema,
        schema_dir=(repo_root / SCHEMA_PATH).parent,
    )
    if schema_errors:
        return schema_errors
    return validate_champion_promotion_receipt_consistency(payload)


def validate_champion_promotion_receipt_consistency(
    payload: dict[str, object],
    *,
    verify_source_digests: bool = True,
) -> tuple[str, ...]:
    """Validate derived champion promotion receipt fields."""
    errors: list[str] = []
    checks = object_field(payload, "evidence_checks")
    comparison = object_field(payload, "comparison")
    promotion_result = object_field(payload, "promotion_result")
    promotion_comparison = object_field(promotion_result, "comparison")
    approval_path = Path(str(payload.get("approval_path", "")))
    dry_run_path = Path(str(payload.get("source_dry_run_path", "")))
    approval = load_json_object(approval_path)
    reviewed = object_field(approval, "reviewed_command")

    promoted = bool(payload.get("promoted", False))
    expected_status = "promoted" if promoted else "blocked"
    expected_command = approved_promotion_command(
        candidate_run_id=str(payload.get("candidate_run_id", "")),
        approval_path=approval_path,
    )

    if payload.get("ok") is not True:
        errors.append("champion_promotion_receipt ok false")
    if str(payload.get("status", "")) != expected_status:
        errors.append("champion_promotion_receipt status mismatch")
    if promoted and checks.get("ok") is not True:
        errors.append("champion_promotion_receipt promoted without evidence ok")
    if promoted and string_list(checks.get("blockers", [])):
        errors.append("champion_promotion_receipt promoted with blockers")
    if not promoted and str(payload.get("status", "")) != "blocked":
        errors.append("champion_promotion_receipt blocked status mismatch")
    if verify_source_digests and str(payload.get("approval_sha256", "")) != file_sha256(
        approval_path
    ):
        errors.append("champion_promotion_receipt approval digest mismatch")
    if verify_source_digests and str(payload.get("source_dry_run_sha256", "")) != file_sha256(
        dry_run_path
    ):
        errors.append("champion_promotion_receipt dry-run digest mismatch")
    if str(checks.get("expected_command", "")) != expected_command:
        errors.append("champion_promotion_receipt expected command mismatch")
    if approval and str(checks.get("reviewed_command", "")) != str(
        reviewed.get("command", "")
    ):
        errors.append("champion_promotion_receipt reviewed command mismatch")
    if str(payload.get("base_run_id", "")) != str(checks.get("current_champion_run_id", "")):
        errors.append("champion_promotion_receipt base champion mismatch")
    if promoted and str(comparison.get("recommendation", "")) != "promote_candidate":
        errors.append("champion_promotion_receipt comparison recommendation mismatch")
    if promoted and promotion_result.get("promoted") is not True:
        errors.append("champion_promotion_receipt promotion result mismatch")
    if promoted and str(promotion_comparison.get("candidate_run_id", "")) != str(
        payload.get("candidate_run_id", "")
    ):
        errors.append("champion_promotion_receipt promotion candidate mismatch")
    if promoted and str(promotion_comparison.get("base_run_id", "")) != str(
        payload.get("base_run_id", "")
    ):
        errors.append("champion_promotion_receipt promotion base mismatch")
    errors.extend(validate_champion_promotion_receipt_policy(payload))
    return tuple(errors)


def validate_champion_promotion_receipt_policy(
    payload: dict[str, object],
) -> tuple[str, ...]:
    """Validate promotion receipt policy flags."""
    errors: list[str] = []
    policy = object_field(payload, "policy")
    for key in (
        "requires_approval_artifact",
        "requires_approval_recorded",
        "requires_command_digest_match",
        "requires_source_dry_run_digest_match",
        "requires_current_champion_match",
        "requires_current_comparison_recommendation",
        "writes_only_champion_registry_and_history",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_change_acceptance",
    ):
        if policy.get(key) is not True:
            errors.append(f"champion_promotion_receipt policy false: {key}")
    return tuple(errors)


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object or return an empty object."""
    if not path.exists() or not path.is_file() or not str(path):
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def object_field(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a nested object field."""
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def string_list(value: object) -> list[str]:
    """Return string rows from a list-like value."""
    return [str(item) for item in value] if isinstance(value, list) else []


def unique_strings(values: list[str]) -> list[str]:
    """Return stable unique strings."""
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a possibly relative path from the repository root."""
    return path if path.is_absolute() else repo_root / path


def file_sha256(path: Path) -> str:
    """Return SHA-256 for a file or an empty string when missing."""
    if not path.exists() or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    """Return SHA-256 for text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> None:
    """CLI entrypoint for guarded champion promotion."""
    parser = argparse.ArgumentParser(description="Promote a champion from approval evidence.")
    parser.add_argument("candidate_run_id")
    parser.add_argument("--approval-path", type=Path, required=True)
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--min-ev-delta", type=float, default=0.0)
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Print the champion promotion receipt as markdown.",
    )
    args = parser.parse_args()
    payload = promote_champion_with_approval(
        candidate_run_id=args.candidate_run_id,
        approval_path=args.approval_path,
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
        min_ev_delta=args.min_ev_delta,
    )
    if args.markdown:
        print(render_receipt_markdown(payload), end="")
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload.get("promoted", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
