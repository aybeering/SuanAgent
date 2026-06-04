"""Terminal-only operator home view for one iteration run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.operator_action_audit import (
    file_record,
    object_field,
    resolve_path,
    string_list,
)
from orchestrator.operator_action_guide import (
    build_operator_action_guide,
    validate_operator_action_guide_payload,
)
from orchestrator.operator_cockpit import (
    build_operator_cockpit,
    validate_operator_cockpit_payload,
)
from orchestrator.schema_validation import load_schema, validate_json_payload


OPERATOR_HOME_SCHEMA_VERSION = "operator_home_v1"
SCHEMA_PATH = Path("schemas/operator_home.schema.json")


def build_operator_home(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return a read-only operator home view derived from current run evidence."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    cockpit = load_or_build_cockpit(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    guide = build_operator_action_guide(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    summary = object_field(cockpit, "summary")
    digest = object_field(cockpit, "operator_digest")
    priority = object_field(cockpit, "review_priority")
    guided_path = object_field(guide, "guided_path")
    next_command = object_field(guide, "next_command")
    next_command_boundary = object_field(next_command, "boundary")
    blockers = string_list(cockpit.get("blockers", []))
    command_state = next_command_state(
        guided_path=guided_path,
        next_command=next_command,
        blockers=blockers,
    )
    codex_home = codex_home_summary(cockpit)
    status = home_status(cockpit=cockpit, guide=guide, blockers=blockers)
    return {
        "schema_version": OPERATOR_HOME_SCHEMA_VERSION,
        "run_id": str(cockpit.get("run_id", run_dir.name)),
        "run_dir": str(run_dir),
        "status": status,
        "ok": status not in {"blocked"},
        "headline": home_headline(
            status=status,
            cockpit=cockpit,
            guide=guide,
            digest=digest,
        ),
        "primary_focus": str(cockpit.get("primary_focus", "")),
        "run_summary": {
            "run_status": str(summary.get("run_status", "")),
            "outcome_category": str(summary.get("run_outcome_category", "")),
            "primary_code": str(summary.get("run_outcome_primary_code", "")),
            "artifact_health_ok": bool(summary.get("artifact_health_ok", False)),
            "scope_health_ok": bool(summary.get("scope_health_ok", False)),
            "candidate_quality_selected_count": int(
                summary.get("candidate_quality_selected_count", 0) or 0
            ),
            "candidate_quality_top_failure_code": str(
                summary.get("candidate_quality_top_failure_code", "")
            ),
        },
        "action_home": {
            "guide_status": str(guide.get("status", "")),
            "current_step": str(guide.get("current_step", "")),
            "active_step_id": str(guided_path.get("active_step_id", "")),
            "completed_step_count": int(
                guided_path.get("completed_step_count", 0) or 0
            ),
            "step_count": int(guided_path.get("step_count", 0) or 0),
            "next_command_label": str(next_command.get("label", "")),
            "next_command_status": str(command_state.get("status", "")),
            "next_command_blocked": bool(command_state.get("blocked", False)),
            "next_command_blocker_count": int(
                command_state.get("blocker_count", 0) or 0
            ),
            "next_command_operator_hint": str(
                command_state.get("operator_hint", "")
            ),
            "next_command_boundary": str(
                next_command_boundary.get("boundary_type", "")
            ),
            "next_command_writes_artifact": str(
                next_command.get("writes_artifact", "")
            ),
            "next_command_requires_explicit_operator_invocation": bool(
                next_command.get("requires_explicit_operator_invocation", False)
            ),
            "next_command_requires_operator_approval": bool(
                next_command.get("requires_operator_approval", False)
            ),
            "next_command_records_operator_approval": bool(
                next_command.get("records_operator_approval", False)
            ),
            "next_command_uses_guarded_executor": bool(
                next_command.get("uses_guarded_executor", False)
            ),
            "next_command_is_hint_only": bool(
                next_command.get("command_is_hint_only", False)
            ),
            "can_invoke_guarded_executor_now": bool(
                object_field(guide, "guidance").get(
                    "can_invoke_guarded_executor_now", False
                )
            ),
        },
        "codex_home": codex_home,
        "guided_path": guided_path,
        "next_command": next_command,
        "review_priority": {
            "priority": str(priority.get("priority", "")),
            "target_panel": str(priority.get("target_panel", "")),
            "target_panel_title": str(priority.get("target_panel_title", "")),
            "command_label": str(object_field(priority, "command").get("label", "")),
            "command": str(object_field(priority, "command").get("command", "")),
        },
        "command_center": command_center_rows(cockpit=cockpit, guide=guide),
        "blockers": blockers[:8],
        "source_views": source_views(run_dir=run_dir, repo_root=repo_root),
        "authority": {
            "home_can_record_approval": False,
            "home_can_execute_commands": False,
            "home_can_write_config": False,
            "home_can_promote_champion": False,
            "home_can_change_acceptance": False,
            "approval_must_use_operator_action_approval": True,
            "execution_must_use_guarded_executor": True,
        },
        "policy": {
            "inspection_only": True,
            "terminal_only": True,
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


def load_or_build_cockpit(
    *,
    run_dir: Path,
    experiments_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    """Load the saved cockpit when present, otherwise derive it."""
    cockpit_path = run_dir / "operator_cockpit.json"
    if cockpit_path.exists():
        payload = json.loads(cockpit_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    return build_operator_cockpit(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )


def home_status(
    *,
    cockpit: dict[str, Any],
    guide: dict[str, Any],
    blockers: list[str],
) -> str:
    """Return a stable operator home status."""
    if cockpit.get("ok") is not True or guide.get("ok") is not True:
        return "blocked"
    if blockers:
        return "needs_operator_review"
    if guide.get("status") == "ready_for_guarded_execution":
        return "ready_for_guarded_execution"
    if guide.get("status") == "awaiting_operator_approval":
        return "awaiting_operator_approval"
    if guide.get("status") == "path_closed":
        return "review_ready"
    return "review_required"


def home_headline(
    *,
    status: str,
    cockpit: dict[str, Any],
    guide: dict[str, Any],
    digest: dict[str, Any],
) -> str:
    """Return the first-screen home headline."""
    if status == "blocked":
        return "Inspect blockers before continuing."
    if status == "needs_operator_review":
        return "Review surfaced operator items, then continue the action path."
    if status == "ready_for_guarded_execution":
        return "Guarded read-only execution is ready."
    if status == "awaiting_operator_approval":
        return "Record approval for the selected read-only operator action."
    if status == "review_ready":
        return "Review the completed operator action path and run outcome."
    return str(
        digest.get(
            "headline",
            object_field(guide, "guidance").get("headline", cockpit.get("status", "")),
        )
    )


def command_center_rows(
    *, cockpit: dict[str, Any], guide: dict[str, Any]
) -> list[dict[str, object]]:
    """Return compact command hints from guide and cockpit priority."""
    rows: list[dict[str, object]] = []
    guide_command = object_field(guide, "next_command")
    if guide_command:
        rows.append(command_row("action_next", guide_command))
    priority_command = object_field(object_field(cockpit, "review_priority"), "command")
    if priority_command and priority_command.get("label") != guide_command.get("label"):
        rows.append(command_row("review_priority", priority_command))
    for command in list_of_dicts(cockpit.get("recommended_commands", [])):
        if len(rows) >= 4:
            break
        label = str(command.get("label", ""))
        if any(row.get("label") == label for row in rows):
            continue
        rows.append(command_row("cockpit", command))
    return rows


def next_command_state(
    *,
    guided_path: dict[str, Any],
    next_command: dict[str, Any],
    blockers: list[str],
) -> dict[str, object]:
    """Return whether the home next-command hint is currently actionable."""
    label = str(next_command.get("label", ""))
    command = str(next_command.get("command", ""))
    active_step_id = str(guided_path.get("active_step_id", ""))
    active_step = guided_path_step_by_id(
        list_of_dicts(guided_path.get("steps", [])),
        active_step_id,
    )
    active_status = str(active_step.get("status", ""))
    if not label or not command:
        return {
            "status": "unavailable",
            "blocked": True,
            "blocker_count": len(blockers),
            "operator_hint": "No next command is available; inspect the guided path.",
        }
    if blockers:
        return {
            "status": "blocked_by_home_blockers",
            "blocked": True,
            "blocker_count": len(blockers),
            "operator_hint": "Review home blockers before invoking the next command hint.",
        }
    if active_status in {"active", "available"}:
        return {
            "status": "ready_for_operator",
            "blocked": False,
            "blocker_count": 0,
            "operator_hint": "The next command is a hint and still requires explicit operator invocation.",
        }
    if active_status == "waiting":
        return {
            "status": "waiting_for_prior_step",
            "blocked": True,
            "blocker_count": 0,
            "operator_hint": "Complete the earlier guided-path step before invoking this command.",
        }
    if active_status == "complete":
        return {
            "status": "already_complete",
            "blocked": False,
            "blocker_count": 0,
            "operator_hint": "The active guided-path step is already complete; review the dashboard.",
        }
    return {
        "status": "review_required",
        "blocked": False,
        "blocker_count": 0,
        "operator_hint": "Review the guided path before invoking the next command hint.",
    }


def guided_path_step_by_id(
    steps: list[dict[str, Any]],
    step_id: str,
) -> dict[str, Any]:
    """Return one guided-path step by id."""
    for step in steps:
        if str(step.get("step_id", "")) == step_id:
            return step
    return {}


def codex_home_summary(cockpit: dict[str, Any]) -> dict[str, object]:
    """Return the Codex CLI readiness summary shown on the home page."""
    summary = object_field(cockpit, "summary")
    intake = object_field(cockpit, "codex_intake_readiness")
    command = command_for_label(
        list_of_dicts(cockpit.get("recommended_commands", [])),
        "review_codex_cli_readiness_diff",
    )
    runbook_command = command_for_label(
        list_of_dicts(cockpit.get("recommended_commands", [])),
        "review_codex_cli_unlock_runbook",
    )
    return {
        "preflight_status": str(summary.get("codex_preflight_status", "")),
        "unlock_runbook_status": str(
            summary.get("codex_unlock_runbook_status", "")
        ),
        "unlock_runbook_ready": bool(
            summary.get("codex_unlock_runbook_ready", False)
        ),
        "unlock_runbook_blocked_step_count": int(
            summary.get("codex_unlock_runbook_blocked_step_count", 0) or 0
        ),
        "readiness_diff_status": str(
            summary.get("codex_readiness_diff_status", "")
        ),
        "readiness_diff_ready": bool(
            summary.get("codex_readiness_diff_ready", False)
        ),
        "intake_readiness_status": str(
            summary.get("codex_intake_readiness_status", "")
        ),
        "intake_ready": bool(summary.get("codex_intake_ready", False)),
        "intake_blocker_count": int(
            summary.get("codex_intake_blocker_count", 0) or 0
        ),
        "intake_source": str(intake.get("source", "none")),
        "bound_slot_count": int(intake.get("bound_slot_count", 0) or 0),
        "blocked_slot_count": int(intake.get("blocked_slot_count", 0) or 0),
        "next_step": str(
            intake.get("next_step", "review Codex CLI readiness evidence")
        ),
        "review_command_label": str(command.get("label", "")),
        "review_command": str(command.get("command", "")),
        "runbook_command_label": str(runbook_command.get("label", "")),
        "runbook_command": str(runbook_command.get("command", "")),
    }


def command_for_label(
    commands: list[dict[str, Any]],
    label: str,
) -> dict[str, Any]:
    """Return a command hint with the requested label."""
    for command in commands:
        if str(command.get("label", "")) == label:
            return command
    return {}


def command_row(source: str, command: dict[str, Any]) -> dict[str, object]:
    """Return one command-center row."""
    boundary = object_field(command, "boundary")
    return {
        "source": source,
        "label": str(command.get("label", "")),
        "command": str(command.get("command", "")),
        "reason": str(command.get("reason", "")),
        "boundary_type": str(boundary.get("boundary_type", "")),
        "command_is_hint_only": True,
    }


def source_views(*, run_dir: Path, repo_root: Path) -> dict[str, object]:
    """Return source view file records used by the home page."""
    return {
        "operator_cockpit": file_record(run_dir / "operator_cockpit.json", repo_root),
        "operator_action_dashboard": file_record(
            run_dir / "operator_action_dashboard.json", repo_root
        ),
        "operator_action_plan": file_record(
            run_dir / "operator_action_plan.json", repo_root
        ),
        "run_closeout": file_record(run_dir / "run_closeout.json", repo_root),
        "operator_unlock_checklist": file_record(
            run_dir / "operator_unlock_checklist.json", repo_root
        ),
        "codex_cli_unlock_runbook": file_record(
            run_dir / "codex_cli_unlock_runbook.json", repo_root
        ),
        "codex_cli_execution_readiness_diff": file_record(
            run_dir / "codex_cli_execution_readiness_diff.json", repo_root
        ),
    }


def render_operator_home_markdown(payload: dict[str, object]) -> str:
    """Render the operator home view as markdown."""
    run_summary = object_field(payload, "run_summary")
    action_home = object_field(payload, "action_home")
    codex_home = object_field(payload, "codex_home")
    lines = [
        "# Operator Home",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Headline: {payload.get('headline', '')}",
        f"- Primary focus: `{payload.get('primary_focus', '')}`",
        f"- Run outcome: `{run_summary.get('outcome_category', '')}` / "
        f"`{run_summary.get('primary_code', '')}`",
        f"- Action step: `{action_home.get('active_step_id', '')}`",
        f"- Guided path: `{action_home.get('completed_step_count', 0)}` / "
        f"`{action_home.get('step_count', 0)}`",
        f"- Next command: `{action_home.get('next_command_label', '')}` "
        f"(`{action_home.get('next_command_boundary', '')}`)",
        f"- Next command status: `{action_home.get('next_command_status', '')}`",
        f"- Next command blocked: `{action_home.get('next_command_blocked', False)}`",
        f"- Next command blockers: `{action_home.get('next_command_blocker_count', 0)}`",
        f"- Next command operator hint: {action_home.get('next_command_operator_hint', '')}",
        f"- Next command writes: `{action_home.get('next_command_writes_artifact', '')}`",
        f"- Next command hint-only: `{action_home.get('next_command_is_hint_only', False)}`",
        f"- Next command needs explicit invocation: "
        f"`{action_home.get('next_command_requires_explicit_operator_invocation', False)}`",
        f"- Next command needs approval: "
        f"`{action_home.get('next_command_requires_operator_approval', False)}`",
        f"- Next command records approval: "
        f"`{action_home.get('next_command_records_operator_approval', False)}`",
        f"- Next command uses guarded executor: "
        f"`{action_home.get('next_command_uses_guarded_executor', False)}`",
        f"- Codex intake: `{codex_home.get('intake_readiness_status', '')}`",
        f"- Codex intake ready: `{codex_home.get('intake_ready', False)}`",
        "",
        "## Codex CLI",
        "",
        f"- Preflight: `{codex_home.get('preflight_status', '')}`",
        f"- Unlock runbook: `{codex_home.get('unlock_runbook_status', '')}`",
        f"- Unlock runbook ready: `{codex_home.get('unlock_runbook_ready', False)}`",
        f"- Unlock runbook blocked steps: `{codex_home.get('unlock_runbook_blocked_step_count', 0)}`",
        f"- Readiness diff: `{codex_home.get('readiness_diff_status', '')}`",
        f"- Readiness diff ready: `{codex_home.get('readiness_diff_ready', False)}`",
        f"- Intake binding: `{codex_home.get('intake_readiness_status', '')}`",
        f"- Intake ready: `{codex_home.get('intake_ready', False)}`",
        f"- Intake blockers: `{codex_home.get('intake_blocker_count', 0)}`",
        f"- Bound slots: `{codex_home.get('bound_slot_count', 0)}`",
        f"- Next step: {codex_home.get('next_step', '')}",
        f"- Runbook command: `{codex_home.get('runbook_command_label', '')}`",
        f"- Review command: `{codex_home.get('review_command_label', '')}`",
        "",
        "## Guided Path",
        "",
    ]
    for step in list_of_dicts(object_field(payload, "guided_path").get("steps", [])):
        lines.append(
            f"- `{step.get('step_id', '')}` `{step.get('status', '')}` -> "
            f"`{step.get('command_label', '')}`"
        )
    lines.extend(["", "## Next Command", ""])
    next_command = object_field(payload, "next_command")
    lines.extend(
        [
            f"- Label: `{next_command.get('label', '')}`",
            f"- Boundary: `{object_field(next_command, 'boundary').get('boundary_type', '')}`",
            "```bash",
            str(next_command.get("command", "")),
            "```",
            "",
            "## Command Center",
            "",
        ]
    )
    for row in list_of_dicts(payload.get("command_center", [])):
        lines.append(
            f"- `{row.get('source', '')}` `{row.get('label', '')}` "
            f"(`{row.get('boundary_type', '')}`)"
        )
    lines.extend(["", "## Blockers", ""])
    blockers = string_list(payload.get("blockers", []))
    lines.extend([f"- `{blocker}`" for blocker in blockers] or ["- none"])
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This home view is terminal-only and hint-only.",
            "- It does not record approval, execute commands, run agents, run backtests, write config, promote champions, apply patches, route agents, or change acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_operator_home_payload(
    payload: dict[str, object],
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an operator home payload."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    schema = load_schema(repo_root / SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=payload,
            schema=schema,
            schema_dir=(repo_root / SCHEMA_PATH).parent,
        )
    )
    errors.extend(
        validate_operator_home_consistency(
            payload,
            run_dir=run_dir,
            experiments_dir=experiments_dir,
            repo_root=repo_root,
        )
    )
    if require_current_evidence:
        expected = build_operator_home(
            run_dir=run_dir,
            experiments_dir=experiments_dir,
            repo_root=repo_root,
        )
        if "from_artifact" in payload:
            expected = {**expected, "from_artifact": payload.get("from_artifact")}
        if payload != expected:
            errors.append("operator_home current evidence mismatch")
    return tuple(errors)


def validate_operator_home_consistency(
    payload: dict[str, object],
    *,
    run_dir: Path,
    experiments_dir: Path,
    repo_root: Path,
) -> tuple[str, ...]:
    """Validate home fields against current cockpit and action guide evidence."""
    errors: list[str] = []
    cockpit = load_or_build_cockpit(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    guide = build_operator_action_guide(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    cockpit_errors = validate_operator_cockpit_payload(
        cockpit,
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    guide_errors = validate_operator_action_guide_payload(
        guide,
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        require_current_evidence=True,
    )
    if cockpit_errors:
        errors.append("operator_home cockpit validation failed")
    if guide_errors:
        errors.append("operator_home guide validation failed")
    summary = object_field(cockpit, "summary")
    codex_home = object_field(payload, "codex_home")
    if codex_home:
        if str(codex_home.get("intake_readiness_status", "")) != str(
            summary.get("codex_intake_readiness_status", "")
        ):
            errors.append("operator_home codex intake status mismatch")
        if bool(codex_home.get("intake_ready", False)) != bool(
            summary.get("codex_intake_ready", False)
        ):
            errors.append("operator_home codex intake ready mismatch")
        if int(codex_home.get("intake_blocker_count", -1)) != int(
            summary.get("codex_intake_blocker_count", -2)
        ):
            errors.append("operator_home codex intake blocker count mismatch")
    expected = build_operator_home(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    payload_for_compare = dict(payload)
    payload_for_compare.pop("from_artifact", None)
    if payload_for_compare != expected:
        errors.append("operator_home derived fields mismatch")
    return tuple(errors)


def list_of_dicts(value: object) -> list[dict[str, Any]]:
    """Return dict rows from a possible list."""
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def main() -> None:
    """CLI entrypoint for the terminal-only operator home."""
    parser = argparse.ArgumentParser(
        description="Show a terminal-only operator home for one run."
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    payload = build_operator_home(
        run_dir=args.run_dir,
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
    )
    errors = validate_operator_home_payload(
        payload,
        run_dir=args.run_dir,
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
        require_current_evidence=True,
    )
    if errors:
        raise SystemExit("; ".join(errors))
    if args.markdown:
        print(render_operator_home_markdown(payload), end="")
        return
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
