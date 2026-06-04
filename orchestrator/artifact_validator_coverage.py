"""Report schema, validator, documentation, and replay coverage for artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.schema_validation import validate_json_file


SCHEMA_VERSION = "artifact_validator_coverage_v1"
COVERAGE_SCHEMA_PATH = Path("schemas/artifact_validator_coverage.schema.json")

DOC_PATHS = (
    Path("README.md"),
    Path("TASK.md"),
    Path("AGENTS.md"),
    Path("docs"),
)

TEST_PATHS = (
    Path("tests"),
)

SUPPORT_PATHS = (
    Path("orchestrator"),
)

KNOWN_ARTIFACT_NAMES = {
    "agent_bundle": ("agent_bundle_manifest.json",),
    "agent_attempts": ("agent_attempts_manifest.json",),
    "agent_selection": ("agent_selection_report.json",),
    "agent_executor": ("agent_executor_report.json",),
    "agent_routing_policy": ("agent_routing_policy.json",),
    "workspace_manifest": ("workspace_manifest.json",),
    "attempt_output": ("attempt_output.json",),
    "run_artifact_health_history": ("run_artifact_health_history.jsonl",),
    "memory_diagnostics": ("memory_diagnostics.json",),
    "memory_hygiene": ("memory_hygiene.json", "memory_hygiene.md"),
    "memory_scope_recommendation": (
        "memory_scope_recommendation.json",
        "memory_scope_recommendation.md",
    ),
    "config_change_candidate": (
        "config_change_candidate.json",
        "config_change_candidate.md",
    ),
    "operator_config_review": (
        "operator_config_review.json",
        "operator_config_review.md",
    ),
    "operator_action_plan": (
        "operator_action_plan.json",
        "operator_action_plan.md",
    ),
    "operator_action_approval": (
        "operator_action_approval.json",
        "operator_action_approval.md",
    ),
    "operator_action_execution_receipt": (
        "operator_action_execution_receipt.json",
        "operator_action_execution_receipt.md",
    ),
    "operator_action_audit": (
        "operator_action_audit.json",
        "operator_action_audit.md",
    ),
    "operator_action_dashboard": (
        "operator_action_dashboard.json",
        "operator_action_dashboard.md",
    ),
    "operator_unlock_checklist": (
        "operator_unlock_checklist.json",
        "operator_unlock_checklist.md",
    ),
    "codex_cli_unlock_runbook": (
        "codex_cli_unlock_runbook.json",
        "codex_cli_unlock_runbook.md",
    ),
    "codex_cli_execution_readiness_diff": (
        "codex_cli_execution_readiness_diff.json",
        "codex_cli_execution_readiness_diff.md",
    ),
    "operator_cockpit": (
        "operator_cockpit.json",
        "operator_cockpit.md",
    ),
    "config_application_dry_run": (
        "config_application_dry_run.json",
        "config_application_dry_run.md",
    ),
    "config_application_receipt": (
        "config_application_receipt.json",
        "config_application_receipt.md",
    ),
    "config_application_rollback_preview": (
        "config_application_rollback_preview.json",
        "config_application_rollback_preview.md",
    ),
    "config_application_restore_receipt": (
        "config_application_restore_receipt.json",
        "config_application_restore_receipt.md",
    ),
    "config_operator_runbook": (
        "config_operator_runbook.json",
        "config_operator_runbook.md",
    ),
    "config_lineage": ("config_lineage.json", "config_lineage.md"),
    "experiment_scope_health": ("experiment_scope_health.json",),
    "run_closeout": ("run_closeout.json", "run_closeout.md"),
    "candidate_challenger_report": (
        "candidate_challenger_report.json",
        "candidate_challenger_report.md",
    ),
    "candidate_quality_trace": (
        "candidate_quality_trace.json",
        "candidate_quality_trace.md",
    ),
    "modifier_profile_recommendation": (
        "modifier_profile_recommendation.json",
        "modifier_profile_recommendation.md",
    ),
    "champion_promotion_dry_run": (
        "champion_promotion_dry_run.json",
        "champion_promotion_dry_run.md",
    ),
    "champion_promotion_approval": (
        "champion_promotion_approval.json",
        "champion_promotion_approval.md",
    ),
    "champion_promotion_receipt": (
        "champion_promotion_receipt.json",
        "champion_promotion_receipt.md",
    ),
    "champion_lineage": (
        "champion_lineage.json",
        "champion_lineage.md",
    ),
}

INSPECTION_COMMANDS = {
    "agent_slot_health": ("python -m orchestrator.agent_slot_health",),
    "agent_slot_readiness_gate": ("python -m orchestrator.experiments readiness",),
    "external_agent_sandbox_drill": (
        "python -m orchestrator.external_agent_sandbox_drill",
        "python -m orchestrator.experiments sandbox",
    ),
    "attempt_replay": ("python -m orchestrator.attempt_replay",),
    "round_replay": ("python -m orchestrator.round_replay",),
    "agent_validation": ("python -m orchestrator.agent_output_intake",),
    "strategy_proposal": ("module reference: orchestrator.proposal StrategyProposal",),
    "agent_result_stats": ("python -m orchestrator.experiments agents",),
    "candidate_leaderboard": ("python -m orchestrator.experiments candidates",),
    "proposal_outcome_memory": ("python -m orchestrator.experiments memory",),
    "run_artifact_health": (
        "python -m orchestrator.run_artifact_health",
        "python -m orchestrator.experiments validate",
    ),
    "run_artifact_health_history": (
        "python -m orchestrator.run_artifact_health --history-summary",
        "python -m orchestrator.experiments health-history",
    ),
    "memory_diagnostics": (
        "python -m orchestrator.memory_diagnostics",
        "python -m orchestrator.experiments memory-diagnostics",
    ),
    "memory_hygiene": (
        "python -m orchestrator.memory_hygiene",
        "python -m orchestrator.experiments memory-hygiene",
    ),
    "memory_scope_recommendation": (
        "python -m orchestrator.memory_scope_recommendation",
        "python -m orchestrator.experiments memory-scope-recommendation",
    ),
    "config_change_candidate": (
        "python -m orchestrator.config_change_candidate",
        "python -m orchestrator.experiments config-change-candidate",
    ),
    "operator_config_review": (
        "python -m orchestrator.operator_config_review",
        "python -m orchestrator.experiments operator-config-review",
    ),
    "operator_action_plan": (
        "python -m orchestrator.operator_action_plan",
        "python -m orchestrator.experiments action-plan",
    ),
    "operator_action_approval": (
        "python -m orchestrator.operator_action_approval",
        "python -m orchestrator.experiments action-approval",
    ),
    "operator_action_execution_receipt": (
        "python -m orchestrator.operator_action_executor",
        "python -m orchestrator.experiments action-execution",
    ),
    "operator_action_audit": (
        "python -m orchestrator.operator_action_audit",
        "python -m orchestrator.experiments action-audit",
    ),
    "operator_action_dashboard": (
        "python -m orchestrator.operator_action_dashboard",
        "python -m orchestrator.experiments action-dashboard",
    ),
    "operator_unlock_checklist": (
        "python -m orchestrator.operator_unlock_checklist",
        "python -m orchestrator.experiments unlock-checklist",
    ),
    "operator_cockpit": (
        "python -m orchestrator.operator_cockpit",
        "python -m orchestrator.experiments cockpit",
    ),
    "operator_view_refresh": (
        "python -m orchestrator.experiments refresh-operator-views",
    ),
    "experiment_summary_dashboard": (
        "python -m orchestrator.experiments summary",
        "python -m orchestrator.experiments summary --markdown",
    ),
    "experiment_leaderboard": ("python -m orchestrator.experiments leaderboard",),
    "champion_status": ("python -m orchestrator.experiments champion",),
    "operator_run_review": (
        "python -m orchestrator.experiments review",
        "python -m orchestrator.experiments review --markdown",
    ),
    "config_application_dry_run": (
        "python -m orchestrator.config_application_dry_run",
        "python -m orchestrator.experiments config-application-dry-run",
    ),
    "config_application_receipt": (
        "python -m orchestrator.config_application_executor",
        "python -m orchestrator.experiments apply-config-approved",
    ),
    "config_application_rollback_preview": (
        "python -m orchestrator.config_application_rollback_preview",
        "python -m orchestrator.experiments config-application-rollback-preview",
    ),
    "config_application_restore_receipt": (
        "python -m orchestrator.config_application_restore_executor",
        "python -m orchestrator.experiments restore-config-approved",
    ),
    "config_operator_runbook": (
        "python -m orchestrator.config_operator_runbook",
        "python -m orchestrator.experiments config-runbook",
    ),
    "config_lineage": (
        "python -m orchestrator.config_lineage",
        "python -m orchestrator.experiments config-lineage",
    ),
    "experiment_scope_health": (
        "python -m orchestrator.experiment_scope_health",
        "python -m orchestrator.experiments scope-health",
    ),
    "run_closeout": (
        "python -m orchestrator.run_closeout",
        "python -m orchestrator.experiments review",
    ),
    "candidate_challenger_report": (
        "python -m orchestrator.candidate_challenger_report",
    ),
    "candidate_quality_trace": (
        "python -m orchestrator.candidate_quality_trace",
        "python -m orchestrator.experiments quality-trace",
    ),
    "modifier_profile_recommendation": (
        "python -m orchestrator.modifier_profile_recommendation",
        "python -m orchestrator.experiments profile-recommendation",
    ),
    "champion_promotion_dry_run": (
        "python -m orchestrator.champion_promotion_dry_run",
    ),
    "champion_promotion_approval": (
        "python -m orchestrator.champion_promotion_approval",
    ),
    "champion_promotion_receipt": (
        "python -m orchestrator.experiments promote-approved",
        "python -m orchestrator.champion_promotion_executor",
    ),
    "champion": ("python -m orchestrator.experiments champion",),
    "champion_lineage": (
        "python -m orchestrator.champion_lineage",
        "python -m orchestrator.experiments lineage",
    ),
    "champion_comparison": ("python -m orchestrator.experiments compare",),
    "codex_cli_replay_gate": ("python -m orchestrator.codex_cli_replay_gate",),
    "codex_cli_enablement_gate": ("python -m orchestrator.codex_cli_enablement_gate",),
    "codex_cli_manual_approval": ("python -m orchestrator.codex_cli_manual_approval",),
    "codex_cli_canary_gate": ("python -m orchestrator.codex_cli_canary_gate",),
    "codex_cli_real_preflight": ("python -m orchestrator.codex_cli_real_preflight",),
    "codex_cli_dry_invocation_guard": (
        "python -m orchestrator.codex_cli_dry_invocation_guard",
    ),
    "codex_cli_execution_unlock_gate": (
        "python -m orchestrator.codex_cli_execution_unlock_gate",
    ),
    "codex_cli_execution_unlock_snapshot": (
        "python -m orchestrator.codex_cli_execution_unlock_snapshot",
    ),
    "codex_cli_execution_candidate": (
        "python -m orchestrator.codex_cli_execution_candidate",
    ),
    "codex_cli_real_execution_dry_run": (
        "python -m orchestrator.codex_cli_real_execution_dry_run",
    ),
    "codex_cli_readiness_summary": (
        "python -m orchestrator.codex_cli_readiness_summary",
    ),
    "codex_cli_readiness_pipeline": (
        "python -m orchestrator.codex_cli_readiness_pipeline",
    ),
    "codex_cli_operator_unlock_request": (
        "python -m orchestrator.codex_cli_operator_unlock_request",
    ),
    "codex_cli_unlock_runbook": (
        "python -m orchestrator.codex_cli_unlock_runbook",
        "python -m orchestrator.experiments unlock-runbook",
    ),
    "codex_cli_execution_readiness_diff": (
        "python -m orchestrator.codex_cli_execution_readiness_diff",
        "python -m orchestrator.experiments execution-readiness-diff",
    ),
    "codex_cli_execution_preflight": (
        "python -m orchestrator.codex_cli_execution_preflight",
    ),
}

CONTRACT_SCHEMA_NAMES = {
    "strategy_proposal",
}


def build_artifact_validator_coverage(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    """Return a deterministic artifact coverage report for the repository."""
    repo_root = repo_root.resolve()
    schema_paths = sorted((repo_root / "schemas").glob("*.schema.json"))
    validator_text = "\n".join(
        (
            read_text(repo_root / "orchestrator/artifact_validator.py"),
            read_text(repo_root / "orchestrator/artifact_validator_coverage.py"),
            read_text(repo_root / "orchestrator/run_artifact_health.py"),
            read_text(repo_root / "orchestrator/memory_diagnostics.py"),
            read_text(repo_root / "orchestrator/experiment_scope_health.py"),
            read_text(repo_root / "orchestrator/run_closeout.py"),
            read_text(repo_root / "orchestrator/experiments.py"),
        )
    )
    docs_text = read_paths(paths=DOC_PATHS, repo_root=repo_root)
    tests_text = read_paths(paths=TEST_PATHS, repo_root=repo_root)
    support_text = read_paths(paths=SUPPORT_PATHS, repo_root=repo_root)

    rows = [
        coverage_row(
            schema_path=schema_path,
            repo_root=repo_root,
            validator_text=validator_text,
            docs_text=docs_text,
            tests_text=tests_text,
            support_text=support_text,
        )
        for schema_path in schema_paths
    ]
    rows.sort(key=lambda row: str(row["schema_name"]))
    totals = coverage_totals(rows)
    gaps = [
        {
            "schema_name": row["schema_name"],
            "gap_codes": row["gap_codes"],
            "recommended_action": row["recommended_action"],
        }
        for row in rows
        if row["gap_codes"]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "repo_root": str(repo_root),
        "ok": totals["schema_with_gap_count"] == 0,
        "totals": totals,
        "schemas": rows,
        "gaps": gaps,
        "policy": {
            "inspection_only": True,
            "does_not_validate_run_artifacts": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_apply_patches": True,
            "does_not_change_acceptance": True,
            "strict_mode_required_for_nonzero_exit": True,
        },
    }


def coverage_row(
    *,
    schema_path: Path,
    repo_root: Path,
    validator_text: str,
    docs_text: str,
    tests_text: str,
    support_text: str,
) -> dict[str, Any]:
    """Return one schema coverage row."""
    schema_file = schema_path.name
    schema_name = schema_file.removesuffix(".schema.json")
    artifact_names = artifact_names_for_schema(schema_name)
    validator_references = count_any(validator_text, (schema_file,))
    if schema_name in CONTRACT_SCHEMA_NAMES:
        validator_references += 1
    docs_references = count_any(docs_text, (schema_file, *artifact_names))
    tests_references = count_any(tests_text, (schema_file, schema_name, *artifact_names))
    support_commands = support_commands_for_schema(schema_name, support_text)
    gap_codes = gap_codes_for_row(
        validator_references=validator_references,
        docs_references=docs_references,
        tests_references=tests_references,
        support_commands=support_commands,
    )
    return {
        "schema_name": schema_name,
        "schema_path": stable_path(schema_path, repo_root),
        "artifact_names": list(artifact_names),
        "validator_covered": validator_references > 0,
        "validator_reference_count": validator_references,
        "docs_covered": docs_references > 0,
        "docs_reference_count": docs_references,
        "tests_covered": tests_references > 0,
        "tests_reference_count": tests_references,
        "inspection_or_replay_supported": bool(support_commands),
        "support_commands": list(support_commands),
        "gap_codes": gap_codes,
        "recommended_action": recommended_action(gap_codes),
    }


def artifact_names_for_schema(schema_name: str) -> tuple[str, ...]:
    """Return known artifact filenames for one schema name."""
    names = [f"{schema_name}.json"]
    names.extend(KNOWN_ARTIFACT_NAMES.get(schema_name, ()))
    return tuple(dict.fromkeys(names))


def support_commands_for_schema(schema_name: str, support_text: str) -> tuple[str, ...]:
    """Return known support commands or module-level support for a schema."""
    commands = list(INSPECTION_COMMANDS.get(schema_name, ()))
    module_token = schema_name
    if module_token in support_text and not commands:
        commands.append(f"module reference: {module_token}")
    return tuple(commands)


def gap_codes_for_row(
    *,
    validator_references: int,
    docs_references: int,
    tests_references: int,
    support_commands: tuple[str, ...],
) -> list[str]:
    """Return stable coverage gap codes."""
    gaps: list[str] = []
    if validator_references == 0:
        gaps.append("validator_missing")
    if docs_references == 0:
        gaps.append("docs_missing")
    if tests_references == 0:
        gaps.append("tests_missing")
    if not support_commands:
        gaps.append("inspection_or_replay_support_missing")
    return gaps


def recommended_action(gap_codes: list[str]) -> str:
    """Return compact guidance for one schema row."""
    if not gap_codes:
        return "covered"
    actions = {
        "validator_missing": "add artifact_validator schema validation",
        "docs_missing": "document artifact or command in docs",
        "tests_missing": "add schema/validator test coverage",
        "inspection_or_replay_support_missing": "add or document inspection/replay support",
    }
    return "; ".join(actions[code] for code in gap_codes)


def coverage_totals(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Return aggregate coverage counts."""
    schema_count = len(rows)
    return {
        "schema_count": schema_count,
        "validator_covered_count": sum(1 for row in rows if row["validator_covered"]),
        "docs_covered_count": sum(1 for row in rows if row["docs_covered"]),
        "tests_covered_count": sum(1 for row in rows if row["tests_covered"]),
        "inspection_or_replay_supported_count": sum(
            1 for row in rows if row["inspection_or_replay_supported"]
        ),
        "schema_with_gap_count": sum(1 for row in rows if row["gap_codes"]),
    }


def coverage_markdown(payload: dict[str, Any]) -> str:
    """Return a compact markdown coverage report."""
    totals = dict(payload.get("totals", {}))
    lines = [
        "# Artifact Validator Coverage",
        "",
        f"- Schema: `{payload.get('schema_version', '')}`",
        f"- Repository: `{payload.get('repo_root', '')}`",
        f"- Schemas: `{totals.get('schema_count', 0)}`",
        f"- Validator covered: `{totals.get('validator_covered_count', 0)}`",
        f"- Docs covered: `{totals.get('docs_covered_count', 0)}`",
        f"- Tests covered: `{totals.get('tests_covered_count', 0)}`",
        "- Inspection/replay supported: "
        f"`{totals.get('inspection_or_replay_supported_count', 0)}`",
        f"- Schemas with gaps: `{totals.get('schema_with_gap_count', 0)}`",
        "",
        "## Gaps",
        "",
    ]
    gaps = payload.get("gaps", [])
    if isinstance(gaps, list) and gaps:
        lines.extend(
            [
                "| Schema | Gap Codes | Recommended Action |",
                "| --- | --- | --- |",
            ]
        )
        for row in gaps:
            if not isinstance(row, dict):
                continue
            gap_codes = ", ".join(str(code) for code in row.get("gap_codes", []))
            lines.append(
                "| "
                f"{row.get('schema_name', '')} | "
                f"{gap_codes} | "
                f"{row.get('recommended_action', '')} |"
            )
    else:
        lines.append("No coverage gaps detected.")
    lines.append("")
    lines.append("This report is inspection-only and does not validate run artifacts.")
    return "\n".join(lines) + "\n"


def write_coverage_report(
    *,
    output_path: Path,
    repo_root: Path = Path("."),
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    """Write coverage JSON and optionally markdown."""
    payload = build_artifact_validator_coverage(repo_root=repo_root)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    errors = validate_coverage_payload_file(
        payload_path=output_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(f"coverage report failed schema validation: {errors}")
    if markdown_path is not None:
        markdown_path.write_text(coverage_markdown(payload), encoding="utf-8")
    return payload


def validate_coverage_payload_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved artifact validator coverage report."""
    schema_path = repo_root.resolve() / COVERAGE_SCHEMA_PATH
    return validate_json_file(payload_path=payload_path, schema_path=schema_path)


def count_any(text: str, needles: tuple[str, ...]) -> int:
    """Return total occurrence count for a set of text needles."""
    return sum(text.count(needle) for needle in needles)


def read_paths(*, paths: tuple[Path, ...], repo_root: Path) -> str:
    """Return concatenated text for files under the requested paths."""
    chunks: list[str] = []
    for relative in paths:
        path = repo_root / relative
        if path.is_file():
            chunks.append(read_text(path))
        elif path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix in {".md", ".py", ".json", ".yml"}:
                    chunks.append(read_text(child))
    return "\n".join(chunks)


def read_text(path: Path) -> str:
    """Read text, returning an empty string for missing files."""
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def stable_path(path: Path, repo_root: Path) -> str:
    """Return a stable repository-relative path."""
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> None:
    """CLI entrypoint for artifact validator coverage."""
    args = parse_args()
    payload = build_artifact_validator_coverage(repo_root=args.repo_root)
    if args.output is not None:
        args.output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.markdown is not None:
        args.markdown.write_text(coverage_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.strict and not payload["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Report artifact schema, validator, docs, and replay coverage.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root to inspect.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write JSON coverage report.",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=None,
        help="Optional path to write markdown coverage report.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero when coverage gaps are present.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
