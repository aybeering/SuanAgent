"""Read-only operator cockpit across run, config, action, and champion state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.operator_action_audit import (
    file_record,
    load_json_object,
    object_field,
    resolve_path,
    schema_errors,
)
from orchestrator.operator_action_dashboard import build_operator_action_dashboard
from orchestrator.schema_validation import validate_json_file


OPERATOR_COCKPIT_SCHEMA_VERSION = "operator_cockpit_v1"
SCHEMA_PATH = Path("schemas/operator_cockpit.schema.json")


def write_operator_cockpit(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown operator cockpit artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    payload = build_operator_cockpit(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    json_path = run_dir / "operator_cockpit.json"
    md_path = run_dir / "operator_cockpit.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_operator_cockpit_markdown(payload), encoding="utf-8")
    errors = validate_operator_cockpit_file(payload_path=json_path, repo_root=repo_root)
    if errors:
        raise ValueError(
            "operator cockpit failed schema validation: " + "; ".join(errors)
        )
    return json_path, md_path, payload


def build_operator_cockpit(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return a compact read-only operator cockpit for a completed run."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    run_id = run_dir.name

    closeout = load_json_object(run_dir / "run_closeout.json")
    config_lineage = load_json_object(run_dir / "config_lineage.json")
    challenger = load_json_object(run_dir / "candidate_challenger_report.json")
    promotion = load_json_object(run_dir / "champion_promotion_dry_run.json")
    approval = load_json_object(run_dir / "champion_promotion_approval.json")
    codex_preflight = load_json_object(run_dir / "codex_cli_execution_preflight.json")
    action_dashboard = load_or_build_action_dashboard(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    scope_health = load_json_object(run_dir / "experiment_scope_health.json")
    summary = cockpit_summary(
        closeout=closeout,
        config_lineage=config_lineage,
        challenger=challenger,
        promotion=promotion,
        approval=approval,
        codex_preflight=codex_preflight,
        action_dashboard=action_dashboard,
        scope_health=scope_health,
    )
    panels = cockpit_panels(
        run_dir=run_dir,
        closeout=closeout,
        config_lineage=config_lineage,
        challenger=challenger,
        promotion=promotion,
        approval=approval,
        codex_preflight=codex_preflight,
        action_dashboard=action_dashboard,
        scope_health=scope_health,
    )
    blockers = cockpit_blockers(
        config_lineage=config_lineage,
        action_dashboard=action_dashboard,
        codex_preflight=codex_preflight,
        promotion=promotion,
        approval=approval,
        scope_health=scope_health,
    )
    status = cockpit_status(summary=summary, blockers=blockers)
    return {
        "schema_version": OPERATOR_COCKPIT_SCHEMA_VERSION,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "status": status,
        "ok": status not in {"needs_repair", "missing_closeout"},
        "primary_focus": primary_focus(status=status, summary=summary),
        "source_artifacts": source_artifacts(run_dir=run_dir, repo_root=repo_root),
        "summary": summary,
        "panels": panels,
        "blockers": blockers,
        "recommended_commands": recommended_commands(
            run_id=run_id,
            run_dir=run_dir,
            repo_root=repo_root,
            summary=summary,
            status=status,
        ),
        "authority": {
            "final_acceptance_authority": "deterministic_policy_gate",
            "cockpit_can_record_approval": False,
            "cockpit_can_execute_commands": False,
            "cockpit_can_write_config": False,
            "cockpit_can_promote_champion": False,
            "cockpit_can_change_acceptance": False,
        },
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "does_not_record_approval": True,
            "does_not_execute_commands": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_write_config": True,
            "does_not_promote_champion": True,
            "does_not_apply_patches": True,
            "does_not_route_agents": True,
            "does_not_change_acceptance": True,
        },
    }


def load_or_build_action_dashboard(
    *,
    run_dir: Path,
    experiments_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    """Load saved action dashboard or derive the same read-only view."""
    path = run_dir / "operator_action_dashboard.json"
    if path.exists():
        return load_json_object(path)
    return build_operator_action_dashboard(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )


def cockpit_summary(
    *,
    closeout: dict[str, Any],
    config_lineage: dict[str, Any],
    challenger: dict[str, Any],
    promotion: dict[str, Any],
    approval: dict[str, Any],
    codex_preflight: dict[str, Any],
    action_dashboard: dict[str, Any],
    scope_health: dict[str, Any],
) -> dict[str, object]:
    """Return compact cockpit summary fields."""
    closeout_summary = object_field(closeout, "summary")
    action_summary = object_field(action_dashboard, "summary")
    codex_summary = object_field(codex_preflight, "summary")
    codex_blockers = string_rows(codex_preflight.get("blocking_errors", []))
    return {
        "run_status": str(closeout.get("status", "unknown")),
        "artifact_health_ok": bool(
            closeout.get("ok", False)
            or closeout_summary.get("artifact_health_history_ok", False)
        ),
        "scope_health_ok": bool(scope_health.get("ok", False)),
        "config_lineage_status": str(config_lineage.get("status", "missing")),
        "config_lineage_ok": bool(config_lineage.get("ok", False)),
        "action_status": str(action_dashboard.get("status", "missing")),
        "action_current_step": str(action_dashboard.get("current_step", "")),
        "action_safe_command_count": int(
            action_summary.get("safe_command_count", 0) or 0
        ),
        "challenger_status": str(challenger.get("status", "missing")),
        "promotion_status": str(promotion.get("status", "missing")),
        "promotion_would_promote": bool(
            object_field(promotion, "dry_run_decision").get("would_promote", False)
        ),
        "promotion_approval_status": str(approval.get("status", "missing")),
        "promotion_approval_recorded": bool(
            object_field(approval, "operator_intent").get("approval_recorded", False)
        ),
        "codex_preflight_status": codex_preflight_status(
            preflight=codex_preflight,
            blockers=codex_blockers,
        ),
        "codex_preflight_ok": bool(codex_preflight.get("ok", False)),
        "codex_real_execute_profile_count": int(
            codex_summary.get("real_codex_execute_profile_count", 0) or 0
        ),
        "codex_operator_unlock_ready_count": int(
            codex_summary.get("operator_unlock_ready_count", 0) or 0
        ),
        "codex_preflight_blocker_count": len(codex_blockers),
    }


def cockpit_status(*, summary: dict[str, object], blockers: list[str]) -> str:
    """Return a stable cockpit status."""
    if summary.get("run_status") == "unknown":
        return "missing_closeout"
    if blockers:
        return "needs_operator_review"
    if summary.get("action_status") in {"pending_approval", "ready_for_execution"}:
        return "action_pending"
    if summary.get("promotion_would_promote") is True and not summary.get(
        "promotion_approval_recorded"
    ):
        return "promotion_pending_approval"
    return "ready_for_review"


def primary_focus(*, status: str, summary: dict[str, object]) -> str:
    """Return one human-facing focus string."""
    if status == "action_pending":
        return str(summary.get("action_current_step", "review_action_dashboard"))
    if status == "promotion_pending_approval":
        return "review_champion_promotion"
    if status == "needs_operator_review":
        return "inspect_blockers"
    if status == "missing_closeout":
        return "write_run_closeout"
    return "review_research_outcome"


def cockpit_panels(
    *,
    run_dir: Path,
    closeout: dict[str, Any],
    config_lineage: dict[str, Any],
    challenger: dict[str, Any],
    promotion: dict[str, Any],
    approval: dict[str, Any],
    codex_preflight: dict[str, Any],
    action_dashboard: dict[str, Any],
    scope_health: dict[str, Any],
) -> list[dict[str, object]]:
    """Return the cockpit panel rows."""
    preflight_blockers = string_rows(codex_preflight.get("blocking_errors", []))
    return [
        panel(
            panel_id="run_review",
            title="Run Review",
            status=str(closeout.get("closeout_status", "missing")),
            ok=bool(closeout.get("ok", False)),
            artifact_path=run_dir / "run_closeout.json",
            next_step="review run closeout dashboard",
        ),
        panel(
            panel_id="config_lineage",
            title="Config Lineage",
            status=str(config_lineage.get("status", "missing")),
            ok=bool(config_lineage.get("ok", False)),
            artifact_path=run_dir / "config_lineage.json",
            next_step="inspect config lineage before changing config",
        ),
        panel(
            panel_id="operator_action",
            title="Operator Action",
            status=str(action_dashboard.get("status", "missing")),
            ok=bool(action_dashboard.get("ok", False)),
            artifact_path=run_dir / "operator_action_dashboard.json",
            next_step=str(action_dashboard.get("current_step", "review action dashboard")),
        ),
        panel(
            panel_id="codex_cli_unlock",
            title="Codex CLI Unlock",
            status=codex_preflight_status(
                preflight=codex_preflight,
                blockers=preflight_blockers,
            ),
            ok=bool(codex_preflight.get("ok", False)),
            artifact_path=run_dir / "codex_cli_execution_preflight.json",
            next_step=codex_preflight_next_step(
                preflight=codex_preflight,
                blockers=preflight_blockers,
            ),
        ),
        panel(
            panel_id="champion_review",
            title="Champion Review",
            status=str(challenger.get("status", "missing")),
            ok=bool(challenger.get("ok", False)),
            artifact_path=run_dir / "candidate_challenger_report.json",
            next_step="review candidate challenger gap",
        ),
        panel(
            panel_id="promotion",
            title="Promotion",
            status=str(promotion.get("status", "missing")),
            ok=bool(promotion.get("ok", False)),
            artifact_path=run_dir / "champion_promotion_dry_run.json",
            next_step="record promotion approval only if dry run recommends it",
        ),
        panel(
            panel_id="promotion_approval",
            title="Promotion Approval",
            status=str(approval.get("status", "missing")),
            ok=bool(object_field(approval, "operator_intent").get("approval_recorded", False)),
            artifact_path=run_dir / "champion_promotion_approval.json",
            next_step="approval does not promote automatically",
        ),
        panel(
            panel_id="scope_health",
            title="Scope Health",
            status="ok" if scope_health.get("ok") is True else "needs_review",
            ok=bool(scope_health.get("ok", False)),
            artifact_path=run_dir / "experiment_scope_health.json",
            next_step="inspect artifact health failures before reuse",
        ),
    ]


def panel(
    *,
    panel_id: str,
    title: str,
    status: str,
    ok: bool,
    artifact_path: Path,
    next_step: str,
) -> dict[str, object]:
    """Return one cockpit panel row."""
    return {
        "panel_id": panel_id,
        "title": title,
        "status": status,
        "ok": ok,
        "artifact_path": artifact_path.as_posix(),
        "artifact_exists": artifact_path.exists(),
        "next_step": next_step,
    }


def cockpit_blockers(
    *,
    config_lineage: dict[str, Any],
    action_dashboard: dict[str, Any],
    codex_preflight: dict[str, Any],
    promotion: dict[str, Any],
    approval: dict[str, Any],
    scope_health: dict[str, Any],
) -> list[str]:
    """Return compact blocker codes from the cockpit source artifacts."""
    blockers: list[str] = []
    if config_lineage and config_lineage.get("ok") is not True:
        blockers.append("config_lineage_not_ok")
    blockers.extend(string_rows(action_dashboard.get("blockers", [])))
    blockers.extend(
        f"codex_cli_preflight:{blocker}"
        for blocker in string_rows(codex_preflight.get("blocking_errors", []))
    )
    blockers.extend(
        string_rows(object_field(promotion, "promotion_gate").get("blockers", []))
    )
    blockers.extend(
        string_rows(object_field(approval, "approval_gate").get("approval_blockers", []))
    )
    if scope_health and scope_health.get("ok") is not True:
        blockers.append("scope_health_not_ok")
    return unique_strings(blockers)


def source_artifacts(*, run_dir: Path, repo_root: Path) -> dict[str, object]:
    """Return cockpit source artifact records."""
    specs = {
        "run_closeout": (
            run_dir / "run_closeout.json",
            "schemas/run_closeout.schema.json",
        ),
        "config_lineage": (
            run_dir / "config_lineage.json",
            "schemas/config_lineage.schema.json",
        ),
        "operator_action_dashboard": (
            run_dir / "operator_action_dashboard.json",
            "schemas/operator_action_dashboard.schema.json",
        ),
        "codex_cli_execution_preflight": (
            run_dir / "codex_cli_execution_preflight.json",
            "schemas/codex_cli_execution_preflight.schema.json",
        ),
        "candidate_challenger_report": (
            run_dir / "candidate_challenger_report.json",
            "schemas/candidate_challenger_report.schema.json",
        ),
        "champion_promotion_dry_run": (
            run_dir / "champion_promotion_dry_run.json",
            "schemas/champion_promotion_dry_run.schema.json",
        ),
        "champion_promotion_approval": (
            run_dir / "champion_promotion_approval.json",
            "schemas/champion_promotion_approval.schema.json",
        ),
        "experiment_scope_health": (
            run_dir / "experiment_scope_health.json",
            "schemas/experiment_scope_health.schema.json",
        ),
    }
    return {
        name: source_artifact(
            path=path,
            schema_path=repo_root / schema_path,
            artifact_name=name,
            repo_root=repo_root,
        )
        for name, (path, schema_path) in specs.items()
    }


def source_artifact(
    *,
    path: Path,
    schema_path: Path,
    artifact_name: str,
    repo_root: Path,
) -> dict[str, object]:
    """Return one source artifact row."""
    return {
        "artifact_name": artifact_name,
        "file": file_record(path, repo_root),
        "schema_errors": list(schema_errors(path=path, schema_path=schema_path)),
    }


def recommended_commands(
    *,
    run_id: str,
    run_dir: Path,
    repo_root: Path,
    summary: dict[str, object],
    status: str,
) -> list[dict[str, object]]:
    """Return read-only command hints for the next operator step."""
    commands = [
        command_hint(
            label="review_cockpit",
            command=f"python -m orchestrator.experiments cockpit {run_id} --markdown",
            reason="Review this read-only cockpit.",
            writes_artifact="",
        ),
        command_hint(
            label="review_run_dashboard",
            command=f"python -m orchestrator.experiments review {run_id} --markdown",
            reason="Inspect the saved run closeout dashboard.",
            writes_artifact="",
        ),
        command_hint(
            label="review_action_dashboard",
            command=f"python -m orchestrator.experiments action-dashboard {run_id} --markdown",
            reason="Inspect operator action state and guarded next commands.",
            writes_artifact="",
        ),
        command_hint(
            label="review_codex_cli_preflight",
            command=(
                "python -m orchestrator.codex_cli_execution_preflight "
                f"{relative_path(run_dir, repo_root)}"
            ),
            reason="Inspect startup blockers before any real Codex CLI execution.",
            writes_artifact="codex_cli_execution_preflight.json",
        ),
    ]
    if not (run_dir / "operator_action_dashboard.json").exists():
        commands.append(
            command_hint(
                label="write_action_dashboard",
                command=(
                    "python -m orchestrator.operator_action_dashboard "
                    f"{relative_path(run_dir, repo_root)}"
                ),
                reason="Persist the read-only action dashboard.",
                writes_artifact="operator_action_dashboard.json",
            )
        )
    if status == "action_pending":
        commands.append(
            command_hint(
                label="continue_operator_action",
                command=f"python -m orchestrator.experiments action-dashboard {run_id} --markdown",
                reason=str(summary.get("action_current_step", "Continue operator action review.")),
                writes_artifact="",
            )
        )
    if status == "promotion_pending_approval":
        commands.append(
            command_hint(
                label="review_promotion_approval",
                command=(
                    "python -m orchestrator.champion_promotion_approval "
                    f"{relative_path(run_dir, repo_root)}"
                ),
                reason="Preview the explicit promotion approval artifact.",
                writes_artifact="champion_promotion_approval.json",
            )
        )
    return commands


def command_hint(
    *,
    label: str,
    command: str,
    reason: str,
    writes_artifact: str,
) -> dict[str, object]:
    """Return one command hint row."""
    return {
        "label": label,
        "command": command,
        "reason": reason,
        "writes_artifact": writes_artifact,
    }


def codex_preflight_status(
    *,
    preflight: dict[str, Any],
    blockers: list[str],
) -> str:
    """Return a compact Codex CLI startup preflight status."""
    if not preflight:
        return "missing"
    if blockers:
        return "blocked"
    summary = object_field(preflight, "summary")
    if int(summary.get("real_codex_execute_profile_count", 0) or 0) == 0:
        return "no_real_execution_profiles"
    return "operator_unlock_ready"


def codex_preflight_next_step(
    *,
    preflight: dict[str, Any],
    blockers: list[str],
) -> str:
    """Return the next operator-facing step for Codex CLI startup preflight."""
    if not preflight:
        return "run iteration preflight before reviewing Codex CLI unlock"
    if blockers:
        return "inspect Codex CLI preflight blockers before real execution"
    summary = object_field(preflight, "summary")
    if int(summary.get("real_codex_execute_profile_count", 0) or 0) == 0:
        return "keep real Codex execution disabled unless explicitly reviewed"
    return "review operator unlock evidence before any real Codex execution"


def render_operator_cockpit_markdown(payload: dict[str, object]) -> str:
    """Render an operator cockpit as markdown."""
    summary = object_field(payload, "summary")
    lines = [
        "# Operator Cockpit",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Primary focus: `{payload.get('primary_focus', '')}`",
        f"- Run status: `{summary.get('run_status', '')}`",
        f"- Config lineage: `{summary.get('config_lineage_status', '')}`",
        f"- Action: `{summary.get('action_status', '')}`",
        f"- Codex CLI preflight: `{summary.get('codex_preflight_status', '')}`",
        f"- Promotion: `{summary.get('promotion_status', '')}`",
        "",
        "## Panels",
        "",
        "| Panel | Status | OK | Next Step |",
        "| --- | --- | --- | --- |",
    ]
    for row in list_of_dicts(payload.get("panels", [])):
        lines.append(
            "| "
            f"{row.get('title', '')} | "
            f"`{row.get('status', '')}` | "
            f"`{row.get('ok', False)}` | "
            f"{row.get('next_step', '')} |"
        )
    lines.extend(["", "## Blockers", ""])
    blockers = string_rows(payload.get("blockers", []))
    lines.extend([f"- `{blocker}`" for blocker in blockers] or ["- none"])
    lines.extend(["", "## Recommended Commands", ""])
    for command in list_of_dicts(payload.get("recommended_commands", [])):
        lines.append(f"- `{command.get('label', '')}`: `{command.get('command', '')}`")
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This cockpit is read-only and does not record approvals or execute commands.",
            "- It does not execute agents, run backtests, write config, promote champions, apply patches, route agents, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_operator_cockpit_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved operator cockpit artifact."""
    return tuple(
        validate_json_file(
            payload_path=payload_path,
            schema_path=repo_root / SCHEMA_PATH,
        )
    )


def list_of_dicts(value: object) -> list[dict[str, Any]]:
    """Return object rows from a possible list."""
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def string_rows(value: object) -> list[str]:
    """Return string rows from a possible list."""
    return [str(row) for row in value] if isinstance(value, list) else []


def unique_strings(values: list[str]) -> list[str]:
    """Return values in stable first-seen order."""
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        if value and value not in seen:
            rows.append(value)
            seen.add(value)
    return rows


def relative_path(path: Path, repo_root: Path) -> str:
    """Return a stable repository-relative path when possible."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def main() -> None:
    """CLI entrypoint for operator cockpit generation."""
    parser = argparse.ArgumentParser(
        description="Write a read-only operator cockpit for one iteration run."
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    _, _, payload = write_operator_cockpit(
        run_dir=args.run_dir,
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
