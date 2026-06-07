"""Terminal-only operator home view for one iteration run."""

from __future__ import annotations

import argparse
import hashlib
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
from orchestrator.run_artifact_health import (
    DEFAULT_HISTORY_FILENAME,
    build_run_artifact_health_history,
)
from orchestrator.schema_validation import load_schema, validate_json_payload


OPERATOR_HOME_SCHEMA_VERSION = "operator_home_v1"
OPERATOR_NEXT_COMMAND_SCHEMA_VERSION = "operator_next_command_v1"
SCHEMA_PATH = Path("schemas/operator_home.schema.json")
NEXT_COMMAND_SCHEMA_PATH = Path("schemas/operator_next_command.schema.json")


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
    guide_next_command = object_field(guide, "next_command")
    artifact_health_history = artifact_health_history_home_summary(
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    next_command = select_home_next_command(
        guide=guide,
        guide_next_command=guide_next_command,
        cockpit=cockpit,
        artifact_health_history=artifact_health_history,
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    next_command_boundary = object_field(next_command, "boundary")
    blockers = string_list(cockpit.get("blockers", []))
    command_state = next_command_state(
        guided_path=guided_path,
        next_command=next_command,
        blockers=blockers,
    )
    codex_home = codex_home_summary(cockpit)
    status = home_status(cockpit=cockpit, guide=guide, blockers=blockers)
    next_command_first_blocker = blockers[0] if blockers else ""
    review_priority_command = str(priority.get("recommended_command", ""))
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
            artifact_health_history=artifact_health_history,
        ),
        "primary_focus": home_primary_focus(
            cockpit=cockpit,
            artifact_health_history=artifact_health_history,
        ),
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
            "next_command_first_blocker": next_command_first_blocker,
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
        "artifact_health_history": artifact_health_history,
        "guided_path": guided_path,
        "next_command": next_command,
        "review_priority": {
            "priority": str(priority.get("priority", "")),
            "target_panel": str(priority.get("target_panel", "")),
            "target_panel_title": str(priority.get("target_panel_title", "")),
            "command_label": str(priority.get("recommended_command_label", "")),
            "command": review_priority_command,
            "command_sha256": sha256_text(review_priority_command),
        },
        "command_center": command_center_rows(
            cockpit=cockpit,
            guide=guide,
            selected_next=next_command,
        ),
        "blockers": blockers[:8],
        "source_views": source_views(
            run_dir=run_dir,
            experiments_dir=experiments_dir,
            repo_root=repo_root,
        ),
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


def build_operator_next_command(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return the single next-command hint from the operator home view."""
    home = build_operator_home(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    action_home = object_field(home, "action_home")
    codex_home = object_field(home, "codex_home")
    next_command = object_field(home, "next_command")
    boundary = object_field(next_command, "boundary")
    status = str(action_home.get("next_command_status", "unavailable"))
    blocked = bool(action_home.get("next_command_blocked", True))
    command = str(next_command.get("command", ""))
    blockers = string_list(home.get("blockers", []))
    operator_hint = str(action_home.get("next_command_operator_hint", ""))
    home_command = (
        "python -m orchestrator.experiments "
        f"home {home.get('run_id', run_dir.name)} --markdown"
    )
    return {
        "schema_version": OPERATOR_NEXT_COMMAND_SCHEMA_VERSION,
        "run_id": str(home.get("run_id", run_dir.name)),
        "run_dir": str(home.get("run_dir", run_dir)),
        "status": status,
        "ok": bool(home.get("ok", False)) and not blocked and bool(command),
        "home_status": str(home.get("status", "")),
        "primary_focus": str(home.get("primary_focus", "")),
        "selection_source": "operator_home.next_command",
        "label": str(next_command.get("label", "")),
        "command": command,
        "command_sha256": sha256_text(command),
        "reason": str(next_command.get("reason", "")),
        "boundary_type": str(boundary.get("boundary_type", "")),
        "writes_artifact": str(next_command.get("writes_artifact", "")),
        "blocked": blocked,
        "blocker_count": int(action_home.get("next_command_blocker_count", 0) or 0),
        "operator_hint": operator_hint,
        "navigation": next_command_navigation(
            status=status,
            blocked=blocked,
            command=command,
            reason=str(next_command.get("reason", "")),
            operator_hint=operator_hint,
            blockers=blockers,
            codex_next_step=str(codex_home.get("next_step", "")),
        ),
        "action_step": str(action_home.get("active_step_id", "")),
        "action_guide_status": str(action_home.get("guide_status", "")),
        "codex_unlock_runbook_status": str(
            codex_home.get("unlock_runbook_status", "")
        ),
        "codex_preflight_next_step": str(codex_home.get("preflight_next_step", "")),
        "codex_intake_readiness_status": str(
            codex_home.get("intake_readiness_status", "")
        ),
        "safety": {
            "command_is_hint_only": bool(
                next_command.get("command_is_hint_only", False)
            ),
            "requires_explicit_operator_invocation": bool(
                next_command.get("requires_explicit_operator_invocation", False)
            ),
            "requires_operator_approval": bool(
                next_command.get("requires_operator_approval", False)
            ),
            "records_operator_approval": bool(
                next_command.get("records_operator_approval", False)
            ),
            "uses_guarded_executor": bool(
                next_command.get("uses_guarded_executor", False)
            ),
        },
        "source_home": {
            "schema_version": str(home.get("schema_version", "")),
            "terminal_only": True,
            "artifact_created": False,
            "command_is_hint_only": True,
            "command_label": "review_operator_home",
            "command": home_command,
            "command_sha256": sha256_text(home_command),
            "boundary_type": "read_only_inspection",
        },
        "authority": {
            "selector_can_record_approval": False,
            "selector_can_execute_commands": False,
            "selector_can_write_config": False,
            "selector_can_promote_champion": False,
            "selector_can_change_acceptance": False,
            "approval_must_use_operator_action_approval": True,
            "execution_must_use_guarded_executor": True,
        },
        "policy": {
            "inspection_only": True,
            "terminal_only": True,
            "does_not_create_artifacts": True,
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


def next_command_navigation(
    *,
    status: str,
    blocked: bool,
    command: str,
    reason: str,
    operator_hint: str,
    blockers: list[str],
    codex_next_step: str,
) -> dict[str, object]:
    """Return a compact operator navigation summary for one command hint."""
    first_blocker = blockers[0] if blockers else ""
    can_invoke = bool(command) and not blocked
    if not command:
        summary = "No selected command is available."
        next_step = "Open the operator home and inspect the guided path."
    elif blocked and first_blocker:
        summary = f"Blocked by {len(blockers)} home blocker(s)."
        next_step = f"Review blocker: {first_blocker}"
    elif blocked:
        summary = f"Command is blocked with status {status}."
        next_step = operator_hint or "Review the selected command status."
    else:
        summary = "Selected command is ready for explicit operator invocation."
        next_step = operator_hint or reason
    return {
        "can_invoke_selected_command": can_invoke,
        "summary": summary,
        "first_blocker": first_blocker,
        "next_step": next_step,
        "codex_next_step": codex_next_step,
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
    if cockpit.get("status") == "promotion_pending_approval":
        return "needs_operator_review"
    if promotion_ready_for_guarded_execution(cockpit):
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
    artifact_health_history: dict[str, Any],
) -> str:
    """Return the first-screen home headline."""
    artifact_status = str(artifact_health_history.get("status", ""))
    if artifact_status == "read_errors":
        return "Review artifact-health history read errors before continuing."
    if artifact_status == "replay_manifest_drift_observed":
        return "Review replay manifest drift before continuing."
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


def home_primary_focus(
    *,
    cockpit: dict[str, Any],
    artifact_health_history: dict[str, Any],
) -> str:
    """Return the operator home's primary focus label."""
    artifact_status = str(artifact_health_history.get("status", ""))
    if artifact_status == "read_errors":
        return "artifact_health_history_read_errors"
    if artifact_status == "replay_manifest_drift_observed":
        return "artifact_health_history_replay_manifest_drift"
    return str(cockpit.get("primary_focus", ""))


def command_center_rows(
    *,
    cockpit: dict[str, Any],
    guide: dict[str, Any],
    selected_next: dict[str, Any],
) -> list[dict[str, object]]:
    """Return compact command hints from guide and cockpit priority."""
    rows: list[dict[str, object]] = []
    guide_command = object_field(guide, "next_command")
    if guide_command:
        rows.append(command_row("action_next", guide_command))
    selected_label = str(selected_next.get("label", ""))
    if selected_label and not any(row.get("label") == selected_label for row in rows):
        rows.append(command_row("selected_next", selected_next))
    priority_command = command_from_review_priority(
        object_field(cockpit, "review_priority")
    )
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


def select_home_next_command(
    *,
    guide: dict[str, Any],
    guide_next_command: dict[str, Any],
    cockpit: dict[str, Any],
    artifact_health_history: dict[str, Any],
    run_dir: Path,
    experiments_dir: Path,
    repo_root: Path,
) -> dict[str, object]:
    """Return the command hint that should be surfaced as the home next step."""
    guide_command = command_with_source(guide_next_command, "action_next")
    artifact_command = artifact_health_history_command(artifact_health_history)
    if artifact_command:
        return artifact_command
    priority = object_field(cockpit, "review_priority")
    if guide.get("status") == "path_closed":
        followup = promotion_followup_command(
            cockpit=cockpit,
            priority=priority,
            run_dir=run_dir,
            experiments_dir=experiments_dir,
            repo_root=repo_root,
        )
        if followup:
            return followup
    return guide_command


def artifact_health_history_command(
    artifact_health_history: dict[str, Any],
) -> dict[str, object]:
    """Return the read-only artifact-health history review command when needed."""
    status = str(artifact_health_history.get("status", ""))
    if status not in {"read_errors", "replay_manifest_drift_observed"}:
        return {}
    command = str(artifact_health_history.get("review_command", ""))
    if not command:
        return {}
    if status == "read_errors":
        reason = "Review artifact-health history read errors before continuing."
    else:
        reason = "Review replay manifest drift before continuing."
    return {
        "label": "review_artifact_health_history",
        "command": command,
        "reason": reason,
        "writes_artifact": "",
        "boundary": read_only_inspection_boundary(),
        "source": "artifact_health_history",
        "command_is_hint_only": True,
        "requires_explicit_operator_invocation": True,
        "requires_operator_approval": False,
        "records_operator_approval": False,
        "uses_guarded_executor": False,
    }


def promotion_followup_command(
    *,
    cockpit: dict[str, Any],
    priority: dict[str, Any],
    run_dir: Path,
    experiments_dir: Path,
    repo_root: Path,
) -> dict[str, object]:
    """Return the promotion-chain command that should follow a closed action path."""
    summary = object_field(cockpit, "summary")
    would_promote = summary.get("promotion_would_promote") is True
    approval_recorded = summary.get("promotion_approval_recorded") is True
    receipt_promoted = summary.get("promotion_receipt_promoted") is True
    if not would_promote:
        return {}
    if receipt_promoted:
        if champion_lineage_is_current(
            experiments_dir=experiments_dir,
            repo_root=repo_root,
        ):
            return champion_status_command()
        return champion_lineage_command()
    if approval_recorded:
        return promote_approved_candidate_command(
            run_id=str(cockpit.get("run_id", run_dir.name)),
            run_dir=run_dir,
        )
    if priority.get("primary_reason") == "promotion_pending_approval":
        return command_from_review_priority(priority)
    return {}


def promotion_ready_for_guarded_execution(cockpit: dict[str, Any]) -> bool:
    """Return whether promotion approval is recorded but no receipt has promoted."""
    summary = object_field(cockpit, "summary")
    return (
        summary.get("promotion_would_promote") is True
        and summary.get("promotion_approval_recorded") is True
        and summary.get("promotion_receipt_promoted") is not True
    )


def promote_approved_candidate_command(
    *,
    run_id: str,
    run_dir: Path,
) -> dict[str, object]:
    """Return a guarded champion-promotion command hint after approval is recorded."""
    approval_path = run_dir / "champion_promotion_approval.json"
    command = (
        "python -m orchestrator.experiments promote-approved "
        f"{run_id} --approval-path {approval_path}"
    )
    boundary = guarded_champion_promotion_boundary()
    return {
        "label": "promote_approved_candidate",
        "command": command,
        "reason": "Run the guarded promotion command only after approval evidence is recorded.",
        "writes_artifact": "champion_promotion_receipt.json",
        "boundary": boundary,
        "source": "promotion_receipt",
        "command_is_hint_only": True,
        "requires_explicit_operator_invocation": True,
        "requires_operator_approval": True,
        "records_operator_approval": False,
        "uses_guarded_executor": True,
    }


def champion_lineage_command() -> dict[str, object]:
    """Return the lineage refresh command after a promotion receipt exists."""
    boundary = read_only_artifact_refresh_boundary()
    return {
        "label": "review_champion_lineage",
        "command": "python -m orchestrator.experiments lineage --markdown",
        "reason": "Refresh and inspect champion lineage after the promotion receipt.",
        "writes_artifact": "champion_lineage.json",
        "boundary": boundary,
        "source": "champion_lineage",
        "command_is_hint_only": True,
        "requires_explicit_operator_invocation": True,
        "requires_operator_approval": False,
        "records_operator_approval": False,
        "uses_guarded_executor": False,
    }


def champion_status_command() -> dict[str, object]:
    """Return the champion status inspection command after lineage is current."""
    boundary = read_only_inspection_boundary()
    return {
        "label": "review_champion_status",
        "command": "python -m orchestrator.experiments champion --markdown",
        "reason": "Inspect champion status after lineage is current.",
        "writes_artifact": "",
        "boundary": boundary,
        "source": "champion_status",
        "command_is_hint_only": True,
        "requires_explicit_operator_invocation": True,
        "requires_operator_approval": False,
        "records_operator_approval": False,
        "uses_guarded_executor": False,
    }


def champion_lineage_is_current(
    *,
    experiments_dir: Path,
    repo_root: Path,
) -> bool:
    """Return whether the saved global champion lineage matches current evidence."""
    lineage_path = experiments_dir / "champion_lineage.json"
    if not lineage_path.exists():
        return False
    try:
        saved = json.loads(lineage_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(saved, dict):
        return False
    try:
        from orchestrator.champion_lineage import build_champion_lineage

        expected = build_champion_lineage(
            experiments_dir=experiments_dir,
            repo_root=repo_root,
        )
    except Exception:
        return False
    return saved == expected


def guarded_champion_promotion_boundary() -> dict[str, object]:
    """Return the boundary metadata for a guarded champion promotion hint."""
    return {
        "boundary_type": "guarded_champion_promotion",
        "requires_explicit_operator_invocation": True,
        "requires_operator_approval": True,
        "records_operator_approval": False,
        "uses_guarded_executor": True,
        "writes_artifact": True,
        "executes_agents": False,
        "runs_backtests": False,
        "applies_patches": False,
        "changes_acceptance": False,
    }


def read_only_artifact_refresh_boundary() -> dict[str, object]:
    """Return the boundary metadata for a read-only lineage refresh hint."""
    return {
        "boundary_type": "read_only_artifact_refresh",
        "requires_explicit_operator_invocation": True,
        "requires_operator_approval": False,
        "records_operator_approval": False,
        "uses_guarded_executor": False,
        "writes_artifact": True,
        "executes_agents": False,
        "runs_backtests": False,
        "applies_patches": False,
        "changes_acceptance": False,
    }


def read_only_inspection_boundary() -> dict[str, object]:
    """Return the boundary metadata for a read-only inspection hint."""
    return {
        "boundary_type": "read_only_inspection",
        "requires_explicit_operator_invocation": True,
        "requires_operator_approval": False,
        "records_operator_approval": False,
        "uses_guarded_executor": False,
        "writes_artifact": False,
        "executes_agents": False,
        "runs_backtests": False,
        "applies_patches": False,
        "changes_acceptance": False,
    }


def command_from_review_priority(priority: dict[str, Any]) -> dict[str, object]:
    """Return a command object from cockpit review-priority fields."""
    label = str(priority.get("recommended_command_label", ""))
    command = str(priority.get("recommended_command", ""))
    if not label or not command:
        return {}
    boundary = object_field(priority, "recommended_command_boundary")
    return {
        "label": label,
        "command": command,
        "reason": str(priority.get("recommended_command_reason", ""))
        or str(priority.get("next_step", "")),
        "writes_artifact": str(priority.get("recommended_command_writes_artifact", "")),
        "boundary": boundary,
        "source": "review_priority",
        "command_is_hint_only": True,
        "requires_explicit_operator_invocation": bool(
            boundary.get("requires_explicit_operator_invocation", False)
        ),
        "requires_operator_approval": bool(
            boundary.get("requires_operator_approval", False)
        ),
        "records_operator_approval": bool(
            boundary.get("records_operator_approval", False)
        ),
        "uses_guarded_executor": bool(boundary.get("uses_guarded_executor", False)),
    }


def command_with_source(command: dict[str, Any], source: str) -> dict[str, object]:
    """Return a command hint with a stable source marker."""
    if not command:
        return {}
    return {**command, "source": str(command.get("source", source))}


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
    if str(next_command.get("source", "")) == "artifact_health_history":
        return {
            "status": "ready_for_operator",
            "blocked": False,
            "blocker_count": 0,
            "operator_hint": str(
                next_command.get(
                    "reason",
                    "Review artifact-health history before invoking other commands.",
                )
            ),
        }
    if blockers:
        return {
            "status": "blocked_by_home_blockers",
            "blocked": True,
            "blocker_count": len(blockers),
            "operator_hint": "Review home blockers before invoking the next command hint.",
        }
    if str(next_command.get("source", "action_next")) != "action_next":
        return {
            "status": "ready_for_operator",
            "blocked": False,
            "blocker_count": 0,
            "operator_hint": "The next command is a cockpit-priority hint and still requires explicit operator invocation.",
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


def panel_by_id(
    panels: list[dict[str, Any]],
    panel_id: str,
) -> dict[str, Any]:
    """Return one cockpit panel by id."""
    for panel_row in panels:
        if str(panel_row.get("panel_id", "")) == panel_id:
            return panel_row
    return {}


def codex_home_summary(cockpit: dict[str, Any]) -> dict[str, object]:
    """Return the Codex CLI readiness summary shown on the home page."""
    summary = object_field(cockpit, "summary")
    intake = object_field(cockpit, "codex_intake_readiness")
    unlock_panel = panel_by_id(
        list_of_dicts(cockpit.get("panels", [])),
        "codex_cli_unlock",
    )
    command = command_for_label(
        list_of_dicts(cockpit.get("recommended_commands", [])),
        "review_codex_cli_readiness_diff",
    )
    runbook_command = command_for_label(
        list_of_dicts(cockpit.get("recommended_commands", [])),
        "review_codex_cli_unlock_runbook",
    )
    review_command = str(command.get("command", ""))
    runbook_command_text = str(runbook_command.get("command", ""))
    return {
        "preflight_status": str(summary.get("codex_preflight_status", "")),
        "preflight_next_step": str(unlock_panel.get("next_step", "")),
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
        "review_command": review_command,
        "review_command_sha256": sha256_text(review_command),
        "runbook_command_label": str(runbook_command.get("label", "")),
        "runbook_command": runbook_command_text,
        "runbook_command_sha256": sha256_text(runbook_command_text),
    }


def artifact_health_history_home_summary(
    *,
    experiments_dir: Path,
    repo_root: Path,
) -> dict[str, object]:
    """Return the artifact-health history summary shown on the home page."""
    history_path = experiments_dir / DEFAULT_HISTORY_FILENAME
    history = build_run_artifact_health_history(
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        history_path=history_path,
        limit=1,
    )
    totals = object_field(history, "totals")
    recent_records = list_of_dicts(history.get("recent_records", []))
    latest = recent_records[-1] if recent_records else {}
    command = "python -m orchestrator.run_artifact_health --history-summary --markdown"
    record_count = int(totals.get("record_count", 0) or 0)
    read_error_count = int(totals.get("read_error_count", 0) or 0)
    return {
        "status": artifact_health_history_status(
            record_count=record_count,
            read_error_count=read_error_count,
            drift_count=int(
                totals.get("round_replay_manifest_drift_observation_count", 0) or 0
            ),
        ),
        "ok": bool(history.get("ok", False)) and read_error_count == 0,
        "history_path": str(history_path),
        "record_count": record_count,
        "records_with_failures": int(totals.get("records_with_failures", 0) or 0),
        "failed_run_observation_count": int(
            totals.get("failed_run_observation_count", 0) or 0
        ),
        "artifact_failure_count": int(totals.get("artifact_failure_count", 0) or 0),
        "round_replay_manifest_drift_observation_count": int(
            totals.get("round_replay_manifest_drift_observation_count", 0) or 0
        ),
        "read_error_count": read_error_count,
        "latest_recorded_at": str(latest.get("recorded_at", "")),
        "latest_failed_count": int(latest.get("failed_count", 0) or 0),
        "latest_round_replay_manifest_drift_count": int(
            latest.get("round_replay_manifest_drift_count", 0) or 0
        ),
        "latest_failed_run_ids": string_list(latest.get("failed_run_ids", [])),
        "review_command_label": "review_artifact_health_history",
        "review_command": command,
        "review_command_sha256": sha256_text(command),
    }


def artifact_health_history_status(
    *,
    record_count: int,
    read_error_count: int,
    drift_count: int,
) -> str:
    """Return a compact artifact-health history status for operator home."""
    if read_error_count > 0:
        return "read_errors"
    if drift_count > 0:
        return "replay_manifest_drift_observed"
    if record_count > 0:
        return "available"
    return "empty"


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
    command_text = str(command.get("command", ""))
    return {
        "source": source,
        "label": str(command.get("label", "")),
        "command": command_text,
        "command_sha256": sha256_text(command_text),
        "reason": str(command.get("reason", "")),
        "boundary_type": str(boundary.get("boundary_type", "")),
        "command_is_hint_only": True,
    }


def source_views(
    *,
    run_dir: Path,
    experiments_dir: Path,
    repo_root: Path,
) -> dict[str, object]:
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
        "run_artifact_health_history": file_record(
            experiments_dir / DEFAULT_HISTORY_FILENAME,
            repo_root,
        ),
        "operator_unlock_checklist": file_record(
            run_dir / "operator_unlock_checklist.json", repo_root
        ),
        "codex_cli_unlock_runbook": file_record(
            run_dir / "codex_cli_unlock_runbook.json", repo_root
        ),
        "codex_cli_execution_readiness_diff": file_record(
            run_dir / "codex_cli_execution_readiness_diff.json", repo_root
        ),
        "champion_promotion_approval": file_record(
            run_dir / "champion_promotion_approval.json", repo_root
        ),
        "champion_promotion_receipt": file_record(
            run_dir / "champion_promotion_receipt.json", repo_root
        ),
        "champion_lineage": file_record(
            experiments_dir / "champion_lineage.json", repo_root
        ),
        "champion_registry": file_record(
            experiments_dir / "champion.json", repo_root
        ),
        "champion_history": file_record(
            experiments_dir / "champion_history.jsonl", repo_root
        ),
    }


def render_operator_home_markdown(payload: dict[str, object]) -> str:
    """Render the operator home view as markdown."""
    run_summary = object_field(payload, "run_summary")
    action_home = object_field(payload, "action_home")
    codex_home = object_field(payload, "codex_home")
    artifact_history = object_field(payload, "artifact_health_history")
    review_priority = object_field(payload, "review_priority")
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
        f"- Next command first blocker: `{action_home.get('next_command_first_blocker', '')}`",
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
        f"- Review priority command label: `{review_priority.get('command_label', '')}`",
        f"- Review priority command SHA-256: `{review_priority.get('command_sha256', '')}`",
        f"- Codex intake: `{codex_home.get('intake_readiness_status', '')}`",
        f"- Codex intake ready: `{codex_home.get('intake_ready', False)}`",
        f"- Artifact-health history: `{artifact_history.get('status', '')}`",
        "- Artifact-health replay drift observations: "
        f"`{artifact_history.get('round_replay_manifest_drift_observation_count', 0)}`",
        "",
        "## Codex CLI",
        "",
        f"- Preflight: `{codex_home.get('preflight_status', '')}`",
        f"- Preflight next step: {codex_home.get('preflight_next_step', '')}",
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
        f"- Runbook command SHA-256: `{codex_home.get('runbook_command_sha256', '')}`",
        f"- Review command: `{codex_home.get('review_command_label', '')}`",
        f"- Review command SHA-256: `{codex_home.get('review_command_sha256', '')}`",
        "",
        "## Artifact Health History",
        "",
        f"- Status: `{artifact_history.get('status', '')}`",
        f"- OK: `{artifact_history.get('ok', False)}`",
        f"- History path: `{artifact_history.get('history_path', '')}`",
        f"- Records: `{artifact_history.get('record_count', 0)}`",
        f"- Records with failures: `{artifact_history.get('records_with_failures', 0)}`",
        "- Failed run observations: "
        f"`{artifact_history.get('failed_run_observation_count', 0)}`",
        f"- Artifact failures: `{artifact_history.get('artifact_failure_count', 0)}`",
        "- Round replay manifest drift observations: "
        f"`{artifact_history.get('round_replay_manifest_drift_observation_count', 0)}`",
        f"- Latest record: `{artifact_history.get('latest_recorded_at', '')}`",
        "- Latest replay drift: "
        f"`{artifact_history.get('latest_round_replay_manifest_drift_count', 0)}`",
        f"- Review command: `{artifact_history.get('review_command_label', '')}`",
        "- Review command SHA-256: "
        f"`{artifact_history.get('review_command_sha256', '')}`",
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
            f"(`{row.get('boundary_type', '')}`) "
            f"`{str(row.get('command_sha256', ''))[:12]}`"
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


def render_operator_next_command_markdown(payload: dict[str, object]) -> str:
    """Render the operator next-command selector as markdown."""
    navigation = object_field(payload, "navigation")
    safety = object_field(payload, "safety")
    source_home = object_field(payload, "source_home")
    lines = [
        "# Operator Next Command",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Home status: `{payload.get('home_status', '')}`",
        f"- Primary focus: `{payload.get('primary_focus', '')}`",
        f"- Label: `{payload.get('label', '')}`",
        f"- Boundary: `{payload.get('boundary_type', '')}`",
        f"- Blocked: `{payload.get('blocked', False)}`",
        f"- Blockers: `{payload.get('blocker_count', 0)}`",
        f"- Operator hint: {payload.get('operator_hint', '')}",
        "- Can invoke selected command: "
        f"`{navigation.get('can_invoke_selected_command', False)}`",
        f"- Navigation summary: {navigation.get('summary', '')}",
        f"- First blocker: `{navigation.get('first_blocker', '')}`",
        f"- Next step: {navigation.get('next_step', '')}",
        f"- Codex next step: {navigation.get('codex_next_step', '')}",
        f"- Writes artifact: `{payload.get('writes_artifact', '')}`",
        f"- Codex unlock runbook: `{payload.get('codex_unlock_runbook_status', '')}`",
        f"- Codex preflight next step: {payload.get('codex_preflight_next_step', '')}",
        f"- Codex intake: `{payload.get('codex_intake_readiness_status', '')}`",
        f"- Selection source: `{payload.get('selection_source', '')}`",
        "",
        "## Command",
        "",
        "```bash",
        str(payload.get("command", "")),
        "```",
        "",
        f"- Command SHA-256: `{payload.get('command_sha256', '')}`",
        "",
        "## Safety",
        "",
        f"- Hint-only: `{safety.get('command_is_hint_only', False)}`",
        "- Requires explicit operator invocation: "
        f"`{safety.get('requires_explicit_operator_invocation', False)}`",
        f"- Requires approval: `{safety.get('requires_operator_approval', False)}`",
        f"- Records approval: `{safety.get('records_operator_approval', False)}`",
        f"- Uses guarded executor: `{safety.get('uses_guarded_executor', False)}`",
        "",
        "## Source",
        "",
        f"- Home command: `{source_home.get('command', '')}`",
        f"- Home command SHA-256: `{source_home.get('command_sha256', '')}`",
        f"- Source boundary: `{source_home.get('boundary_type', '')}`",
        f"- Source terminal-only: `{source_home.get('terminal_only', False)}`",
        f"- Source creates artifact: `{source_home.get('artifact_created', True)}`",
        f"- Source hint-only: `{source_home.get('command_is_hint_only', False)}`",
        "",
        "## Policy",
        "",
        "- This selector is terminal-only and hint-only.",
        "- It does not record approval, execute commands, run agents, run backtests, write config, promote champions, apply patches, route agents, or change acceptance.",
        "",
    ]
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


def validate_operator_next_command_payload(
    payload: dict[str, object],
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an operator next-command selector payload."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    schema = load_schema(repo_root / NEXT_COMMAND_SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=payload,
            schema=schema,
            schema_dir=(repo_root / NEXT_COMMAND_SCHEMA_PATH).parent,
        )
    )
    errors.extend(
        validate_operator_next_command_consistency(
            payload,
            run_dir=run_dir,
            experiments_dir=experiments_dir,
            repo_root=repo_root,
        )
    )
    if require_current_evidence:
        expected = build_operator_next_command(
            run_dir=run_dir,
            experiments_dir=experiments_dir,
            repo_root=repo_root,
        )
        if "from_artifact" in payload:
            expected = {**expected, "from_artifact": payload.get("from_artifact")}
        if payload != expected:
            errors.append("operator_next_command current evidence mismatch")
    return tuple(errors)


def validate_operator_next_command_consistency(
    payload: dict[str, object],
    *,
    run_dir: Path,
    experiments_dir: Path,
    repo_root: Path,
) -> tuple[str, ...]:
    """Validate next-command selector fields against the operator home."""
    errors: list[str] = []
    home = build_operator_home(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    home_errors = validate_operator_home_payload(
        home,
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
        require_current_evidence=True,
    )
    if home_errors:
        errors.append("operator_next_command home validation failed")
    command = str(payload.get("command", ""))
    if str(payload.get("command_sha256", "")) != sha256_text(command):
        errors.append("operator_next_command command sha256 mismatch")
    source_home = object_field(payload, "source_home")
    source_command = str(source_home.get("command", ""))
    if str(source_home.get("command_sha256", "")) != sha256_text(source_command):
        errors.append("operator_next_command source command sha256 mismatch")
    expected = build_operator_next_command(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    expected_source = object_field(expected, "source_home")
    expected_safety = object_field(expected, "safety")
    expected_authority = object_field(expected, "authority")
    expected_policy = object_field(expected, "policy")
    safety = object_field(payload, "safety")
    navigation = object_field(payload, "navigation")
    authority = object_field(payload, "authority")
    policy = object_field(payload, "policy")
    for field_name in (
        "run_id",
        "run_dir",
        "status",
        "ok",
        "home_status",
        "primary_focus",
        "selection_source",
        "label",
        "command",
        "command_sha256",
        "reason",
        "boundary_type",
        "writes_artifact",
        "blocked",
        "blocker_count",
        "operator_hint",
        "action_step",
        "action_guide_status",
        "codex_unlock_runbook_status",
        "codex_preflight_next_step",
        "codex_intake_readiness_status",
    ):
        if payload.get(field_name) != expected.get(field_name):
            errors.append(f"operator_next_command {field_name} mismatch")
    expected_navigation = object_field(expected, "navigation")
    for field_name in (
        "can_invoke_selected_command",
        "summary",
        "first_blocker",
        "next_step",
        "codex_next_step",
    ):
        if navigation.get(field_name) != expected_navigation.get(field_name):
            errors.append(f"operator_next_command navigation {field_name} mismatch")
    for field_name in (
        "schema_version",
        "terminal_only",
        "artifact_created",
        "command_is_hint_only",
        "command_label",
        "command",
        "command_sha256",
        "boundary_type",
    ):
        if source_home.get(field_name) != expected_source.get(field_name):
            errors.append(f"operator_next_command source_home {field_name} mismatch")
    for field_name in (
        "command_is_hint_only",
        "requires_explicit_operator_invocation",
        "requires_operator_approval",
        "records_operator_approval",
        "uses_guarded_executor",
    ):
        if safety.get(field_name) != expected_safety.get(field_name):
            errors.append(f"operator_next_command safety {field_name} mismatch")
    for field_name in (
        "selector_can_record_approval",
        "selector_can_execute_commands",
        "selector_can_write_config",
        "selector_can_promote_champion",
        "selector_can_change_acceptance",
        "approval_must_use_operator_action_approval",
        "execution_must_use_guarded_executor",
    ):
        if authority.get(field_name) != expected_authority.get(field_name):
            errors.append(f"operator_next_command authority {field_name} mismatch")
    for field_name in (
        "inspection_only",
        "terminal_only",
        "does_not_create_artifacts",
        "does_not_record_approval",
        "does_not_execute_commands",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_write_config",
        "does_not_promote_champion",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_change_acceptance",
    ):
        if policy.get(field_name) != expected_policy.get(field_name):
            errors.append(f"operator_next_command policy {field_name} mismatch")
    payload_for_compare = dict(payload)
    payload_for_compare.pop("from_artifact", None)
    if payload_for_compare != expected:
        errors.append("operator_next_command derived fields mismatch")
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
    expected_action_home = object_field(expected, "action_home")
    expected_codex_home = object_field(expected, "codex_home")
    expected_artifact_history = object_field(expected, "artifact_health_history")
    expected_command_center = command_center_by_marker(
        list_of_dicts(expected.get("command_center", []))
    )
    expected_command_center_counts = command_center_marker_counts(
        list_of_dicts(expected.get("command_center", []))
    )
    expected_source_views = object_field(expected, "source_views")
    expected_authority = object_field(expected, "authority")
    expected_policy = object_field(expected, "policy")
    action_home = object_field(payload, "action_home")
    review_priority = object_field(payload, "review_priority")
    expected_review_priority = object_field(expected, "review_priority")
    command_center_payload = command_center_by_marker(
        list_of_dicts(payload.get("command_center", []))
    )
    command_center_payload_counts = command_center_marker_counts(
        list_of_dicts(payload.get("command_center", []))
    )
    source_views_payload = object_field(payload, "source_views")
    artifact_history = object_field(payload, "artifact_health_history")
    authority = object_field(payload, "authority")
    policy = object_field(payload, "policy")
    for field_name in (
        "run_id",
        "run_dir",
        "status",
        "ok",
        "headline",
        "primary_focus",
    ):
        if payload.get(field_name) != expected.get(field_name):
            errors.append(f"operator_home {field_name} mismatch")
    for field_name in (
        "guide_status",
        "current_step",
        "active_step_id",
        "completed_step_count",
        "step_count",
        "next_command_label",
        "next_command_status",
        "next_command_blocked",
        "next_command_blocker_count",
        "next_command_first_blocker",
        "next_command_operator_hint",
        "next_command_boundary",
        "next_command_writes_artifact",
        "next_command_requires_explicit_operator_invocation",
        "next_command_requires_operator_approval",
        "next_command_records_operator_approval",
        "next_command_uses_guarded_executor",
        "next_command_is_hint_only",
        "can_invoke_guarded_executor_now",
    ):
        if action_home.get(field_name) != expected_action_home.get(field_name):
            errors.append(f"operator_home action_home {field_name} mismatch")
    for field_name in (
        "preflight_status",
        "preflight_next_step",
        "unlock_runbook_status",
        "unlock_runbook_ready",
        "readiness_diff_status",
        "readiness_diff_ready",
        "intake_readiness_status",
        "intake_ready",
        "intake_blocker_count",
        "startup_preflight_ok",
        "review_command_label",
        "review_command",
        "review_command_sha256",
        "runbook_command_label",
        "runbook_command",
        "runbook_command_sha256",
    ):
        if codex_home.get(field_name) != expected_codex_home.get(field_name):
            errors.append(f"operator_home codex_home {field_name} mismatch")
    for field_name in (
        "status",
        "ok",
        "history_path",
        "record_count",
        "records_with_failures",
        "failed_run_observation_count",
        "artifact_failure_count",
        "round_replay_manifest_drift_observation_count",
        "read_error_count",
        "latest_recorded_at",
        "latest_failed_count",
        "latest_round_replay_manifest_drift_count",
        "latest_failed_run_ids",
        "review_command_label",
        "review_command",
        "review_command_sha256",
    ):
        if artifact_history.get(field_name) != expected_artifact_history.get(field_name):
            errors.append(
                f"operator_home artifact_health_history {field_name} mismatch"
            )
    if str(artifact_history.get("review_command_sha256", "")) != sha256_text(
        str(artifact_history.get("review_command", ""))
    ):
        errors.append(
            "operator_home artifact_health_history review_command_sha256 mismatch"
        )
    for field_name in ("review_command", "runbook_command"):
        digest_field = f"{field_name}_sha256"
        if str(codex_home.get(digest_field, "")) != sha256_text(
            str(codex_home.get(field_name, ""))
        ):
            errors.append(f"operator_home codex_home {digest_field} mismatch")
    for field_name in (
        "priority",
        "target_panel",
        "target_panel_title",
        "command_label",
        "command",
        "command_sha256",
    ):
        if review_priority.get(field_name) != expected_review_priority.get(field_name):
            errors.append(f"operator_home review_priority {field_name} mismatch")
    if str(review_priority.get("command_sha256", "")) != sha256_text(
        str(review_priority.get("command", ""))
    ):
        errors.append("operator_home review_priority command_sha256 mismatch")
    for source_name, expected_record in expected_source_views.items():
        if source_views_payload.get(source_name) != expected_record:
            errors.append(f"operator_home source_views {source_name} mismatch")
    for marker, expected_record in expected_command_center.items():
        if command_center_payload.get(marker) != expected_record:
            errors.append(f"operator_home command_center {marker} mismatch")
    unexpected_markers = sorted(
        set(command_center_payload) - set(expected_command_center)
    )
    for marker in unexpected_markers:
        errors.append(f"operator_home command_center {marker} unexpected")
    for marker, marker_count in command_center_payload_counts.items():
        if marker_count > 1:
            errors.append(f"operator_home command_center {marker} duplicate")
    missing_markers = sorted(
        set(expected_command_center) - set(command_center_payload)
    )
    for marker in missing_markers:
        errors.append(f"operator_home command_center {marker} missing")
    for marker, expected_count in expected_command_center_counts.items():
        if command_center_payload_counts.get(marker, 0) != expected_count:
            errors.append(f"operator_home command_center {marker} count mismatch")
    for field_name in (
        "home_can_record_approval",
        "home_can_execute_commands",
        "home_can_write_config",
        "home_can_promote_champion",
        "home_can_change_acceptance",
        "approval_must_use_operator_action_approval",
        "execution_must_use_guarded_executor",
    ):
        if authority.get(field_name) != expected_authority.get(field_name):
            errors.append(f"operator_home authority {field_name} mismatch")
    for field_name in (
        "inspection_only",
        "terminal_only",
        "does_not_record_approval",
        "does_not_execute_commands",
        "does_not_execute_agents",
        "does_not_run_backtests",
        "does_not_write_config",
        "does_not_promote_champion",
        "does_not_apply_patches",
        "does_not_route_agents",
        "does_not_change_acceptance",
    ):
        if policy.get(field_name) != expected_policy.get(field_name):
            errors.append(f"operator_home policy {field_name} mismatch")
    payload_for_compare = dict(payload)
    payload_for_compare.pop("from_artifact", None)
    if payload_for_compare != expected:
        errors.append("operator_home derived fields mismatch")
    return tuple(errors)


def command_center_by_marker(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return command-center rows keyed by their stable command marker."""
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        indexed.setdefault(command_center_marker(row), row)
    return indexed


def command_center_marker_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Return command-center row counts keyed by their stable command marker."""
    counts: dict[str, int] = {}
    for row in rows:
        marker = command_center_marker(row)
        counts[marker] = counts.get(marker, 0) + 1
    return counts


def command_center_marker(row: dict[str, Any]) -> str:
    """Return the stable source/label marker for one command-center row."""
    return f"{row.get('source', '')}:{row.get('label', '')}"


def list_of_dicts(value: object) -> list[dict[str, Any]]:
    """Return dict rows from a possible list."""
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def sha256_text(value: str) -> str:
    """Return a stable SHA-256 digest for text command bindings."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> None:
    """CLI entrypoint for the terminal-only operator home."""
    parser = argparse.ArgumentParser(
        description="Show a terminal-only operator home for one run."
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--next-command", action="store_true")
    args = parser.parse_args()
    if args.next_command:
        payload = build_operator_next_command(
            run_dir=args.run_dir,
            experiments_dir=args.experiments_dir,
            repo_root=args.repo_root,
        )
        errors = validate_operator_next_command_payload(
            payload,
            run_dir=args.run_dir,
            experiments_dir=args.experiments_dir,
            repo_root=args.repo_root,
            require_current_evidence=True,
        )
        if errors:
            raise SystemExit("; ".join(errors))
        if args.markdown:
            print(render_operator_next_command_markdown(payload), end="")
            return
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
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
