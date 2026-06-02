"""Read-only operator action plan derived from run closeout artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.run_closeout import build_run_closeout
from orchestrator.schema_validation import validate_json_file


OPERATOR_ACTION_PLAN_SCHEMA_VERSION = "operator_action_plan_v1"
SCHEMA_PATH = Path("schemas/operator_action_plan.schema.json")


def write_operator_action_plan(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown operator action plan artifacts."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    payload = build_operator_action_plan(
        run_dir=run_dir,
        experiments_dir=experiments_dir,
        repo_root=repo_root,
    )
    json_path = run_dir / "operator_action_plan.json"
    md_path = run_dir / "operator_action_plan.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_operator_action_plan_markdown(payload), encoding="utf-8")
    errors = validate_operator_action_plan_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(
            "operator action plan failed schema validation: " + "; ".join(errors)
        )
    return json_path, md_path, payload


def build_operator_action_plan(
    *,
    run_dir: Path,
    experiments_dir: Path = Path("experiments"),
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Return a deterministic operator action plan from saved closeout data."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_dir = resolve_path(experiments_dir, repo_root)
    closeout_path = run_dir / "run_closeout.json"
    if closeout_path.exists():
        closeout = load_json_object(closeout_path)
        from_artifact = True
    else:
        closeout = build_run_closeout(
            run_dir=run_dir,
            experiments_dir=experiments_dir,
            repo_root=repo_root,
        )
        from_artifact = False
    dashboard = object_field(closeout, "operator_dashboard")
    raw_actions = string_list(dashboard.get("operator_action_items", []))
    if not raw_actions:
        raw_actions = string_list(closeout.get("recommended_next_actions", []))
    actions = [
        action_row(
            run_id=run_dir.name,
            index=index,
            source_text=source_text,
            closeout=closeout,
        )
        for index, source_text in enumerate(raw_actions, start=1)
    ]
    summary = action_summary(actions=actions)
    payload: dict[str, object] = {
        "schema_version": OPERATOR_ACTION_PLAN_SCHEMA_VERSION,
        "run_id": str(closeout.get("run_id", run_dir.name)),
        "run_dir": str(run_dir),
        "status": action_plan_status(summary=summary, closeout=closeout),
        "ok": bool(closeout),
        "source_closeout": {
            "artifact_name": "run_closeout",
            "from_artifact": from_artifact,
            "file": file_record(closeout_path),
        },
        "summary": summary,
        "actions": actions,
        "policy": {
            "inspection_only": True,
            "reads_saved_artifacts_only": True,
            "does_not_execute_commands": True,
            "does_not_execute_agents": True,
            "does_not_run_backtests": True,
            "does_not_write_config": True,
            "does_not_promote_champion": True,
            "does_not_apply_patches": True,
            "does_not_route_agents": True,
            "does_not_change_acceptance": True,
            "commands_require_explicit_operator_invocation": True,
        },
    }
    return payload


def action_row(
    *,
    run_id: str,
    index: int,
    source_text: str,
    closeout: dict[str, object],
) -> dict[str, object]:
    """Return one stable operator action row."""
    action_type = classify_action(source_text)
    commands = command_candidates(
        run_id=run_id,
        action_type=action_type,
        closeout=closeout,
    )
    status = action_status(action_type=action_type, commands=commands)
    return {
        "action_id": f"action_{index:03d}_{action_type}",
        "action_type": action_type,
        "source_text": source_text,
        "status": status,
        "reason_codes": action_reason_codes(action_type=action_type, status=status),
        "command_candidates": commands,
        "authority": {
            "plan_can_execute": False,
            "plan_can_write_config": False,
            "plan_can_promote_champion": False,
            "final_acceptance_authority": "deterministic_code",
        },
    }


def classify_action(source_text: str) -> str:
    """Classify a closeout action into a stable action type."""
    normalized = source_text.lower()
    if "artifact health" in normalized:
        return "repair_artifact_health"
    if "config_lineage" in normalized or "config lineage" in normalized:
        return "inspect_config_lineage"
    if "promotion approval" in normalized or "promoting" in normalized:
        return "review_champion_promotion"
    if "different deterministic modifier" in normalized or "different profile" in normalized:
        return "switch_modifier_profile"
    if "research brief" in normalized or "selected candidate" in normalized:
        return "inspect_research_context"
    return "inspect_run_context"


def command_candidates(
    *,
    run_id: str,
    action_type: str,
    closeout: dict[str, object],
) -> list[dict[str, object]]:
    """Return read-only command candidates for a classified action."""
    if action_type == "repair_artifact_health":
        return [
            command_row(
                label="validate_run_artifacts",
                command=f"python -m orchestrator.artifact_validator {run_id}",
                expected_artifact="run_artifact_health.json",
            ),
            command_row(
                label="inspect_scope_health",
                command="python -m orchestrator.experiments scope-health --strict",
                expected_artifact="experiment_scope_health.json",
            ),
        ]
    if action_type == "inspect_config_lineage":
        return [
            command_row(
                label="inspect_config_lineage",
                command=f"python -m orchestrator.experiments config-lineage {run_id}",
                expected_artifact="config_lineage.json",
            ),
            command_row(
                label="inspect_config_candidate",
                command=(
                    f"python -m orchestrator.experiments "
                    f"config-change-candidate {run_id}"
                ),
                expected_artifact="config_change_candidate.json",
            ),
        ]
    if action_type == "review_champion_promotion":
        promotion_command = reviewed_promotion_command(closeout)
        commands = [
            command_row(
                label="inspect_promotion_approval",
                command=(
                    f"python -m orchestrator.champion_promotion_approval "
                    f"experiments/{run_id}"
                ),
                expected_artifact="champion_promotion_approval.json",
            )
        ]
        if promotion_command:
            commands.append(
                command_row(
                    label="promote_from_approval",
                    command=promotion_command,
                    expected_artifact="champion_promotion_receipt.json",
                    writes_repo=True,
                    promotes_champion=True,
                )
            )
        return commands
    if action_type == "switch_modifier_profile":
        return [
            command_row(
                label="inspect_candidates",
                command=f"python -m orchestrator.experiments candidates {run_id}",
                expected_artifact="candidate_leaderboard.json",
            ),
            command_row(
                label="inspect_quality_trace",
                command=f"python -m orchestrator.experiments quality-trace {run_id}",
                expected_artifact="candidate_quality_trace.json",
            ),
            command_row(
                label="start_next_iteration",
                command="python -m orchestrator.iteration_loop",
                expected_artifact="manifest.json",
                runs_backtests=True,
            ),
        ]
    return [
        command_row(
            label="review_run_dashboard",
            command=f"python -m orchestrator.experiments review {run_id} --markdown",
            expected_artifact="run_closeout.md",
        ),
        command_row(
            label="inspect_research_brief",
            command=f"python -m orchestrator.experiments show {run_id}",
            expected_artifact="research_brief.json",
        ),
    ]


def command_row(
    *,
    label: str,
    command: str,
    expected_artifact: str,
    writes_repo: bool = False,
    promotes_champion: bool = False,
    runs_backtests: bool = False,
) -> dict[str, object]:
    """Return one candidate command row without executing it."""
    return {
        "label": label,
        "command": command,
        "command_sha256": sha256_text(command),
        "expected_artifact": expected_artifact,
        "writes_repository": writes_repo,
        "promotes_champion": promotes_champion,
        "runs_backtests": runs_backtests,
        "requires_explicit_operator_invocation": True,
        "executed_by_plan": False,
    }


def reviewed_promotion_command(closeout: dict[str, object]) -> str:
    """Return the promotion command from closeout sources when present."""
    for row in list_of_dicts(closeout.get("artifacts", [])):
        if row.get("label") == "champion_promotion_approval":
            path = Path(str(row.get("path", "")))
            payload = load_json_object(path)
            command = object_field(payload, "reviewed_command")
            return str(command.get("command", ""))
    return ""


def action_status(*, action_type: str, commands: list[dict[str, object]]) -> str:
    """Return compact action status."""
    if not commands:
        return "blocked"
    if action_type in {"switch_modifier_profile", "inspect_research_context", "inspect_run_context"}:
        return "ready_for_review"
    if any(bool(command.get("writes_repository", False)) for command in commands):
        return "requires_operator_approval"
    return "ready_for_review"


def action_reason_codes(*, action_type: str, status: str) -> list[str]:
    """Return deterministic reason codes for an action row."""
    codes = [f"source_action_type:{action_type}", f"status:{status}"]
    if status == "requires_operator_approval":
        codes.append("guarded_command_candidate_present")
    return codes


def action_summary(*, actions: list[dict[str, object]]) -> dict[str, object]:
    """Return compact action plan summary."""
    command_count = sum(len(list_of_dicts(action.get("command_candidates", []))) for action in actions)
    guarded_count = sum(
        1
        for action in actions
        for command in list_of_dicts(action.get("command_candidates", []))
        if bool(command.get("writes_repository", False))
        or bool(command.get("promotes_champion", False))
        or bool(command.get("runs_backtests", False))
    )
    return {
        "action_count": len(actions),
        "command_candidate_count": command_count,
        "guarded_command_candidate_count": guarded_count,
        "ready_action_count": sum(
            1 for action in actions if str(action.get("status", "")) == "ready_for_review"
        ),
        "approval_required_action_count": sum(
            1
            for action in actions
            if str(action.get("status", "")) == "requires_operator_approval"
        ),
    }


def action_plan_status(
    *,
    summary: dict[str, object],
    closeout: dict[str, object],
) -> str:
    """Return plan-level status."""
    if not closeout:
        return "missing_closeout"
    if int(summary.get("action_count", 0) or 0) == 0:
        return "no_actions"
    if int(summary.get("approval_required_action_count", 0) or 0) > 0:
        return "operator_approval_required"
    return "ready_for_review"


def render_operator_action_plan_markdown(payload: dict[str, object]) -> str:
    """Render an operator action plan payload as markdown."""
    summary = object_field(payload, "summary")
    lines = [
        "# Operator Action Plan",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Actions: `{summary.get('action_count', 0)}`",
        f"- Command candidates: `{summary.get('command_candidate_count', 0)}`",
        f"- Guarded command candidates: `{summary.get('guarded_command_candidate_count', 0)}`",
        "",
        "## Actions",
        "",
    ]
    actions = list_of_dicts(payload.get("actions", []))
    if not actions:
        lines.append("No operator actions were derived from the closeout dashboard.")
    for action in actions:
        lines.extend(
            [
                f"### {action.get('action_id', '')}",
                "",
                f"- Type: `{action.get('action_type', '')}`",
                f"- Status: `{action.get('status', '')}`",
                f"- Source: {action.get('source_text', '')}",
                "",
                "| Label | Command | Writes Repo | Promotes Champion | Runs Backtests |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for command in list_of_dicts(action.get("command_candidates", [])):
            lines.append(
                "| "
                f"{command.get('label', '')} | "
                f"`{command.get('command', '')}` | "
                f"{command.get('writes_repository', False)} | "
                f"{command.get('promotes_champion', False)} | "
                f"{command.get('runs_backtests', False)} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Policy",
            "",
            "- This artifact is inspection-only and reads saved artifacts only.",
            "- It does not execute commands, execute agents, run backtests, write config, promote champions, apply patches, route agents, or change acceptance.",
            "- Every command candidate requires explicit operator invocation.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_operator_action_plan_file(
    *,
    payload_path: Path,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a saved operator action plan artifact."""
    return validate_json_file(
        payload_path=payload_path,
        schema_path=repo_root / SCHEMA_PATH,
    )


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
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    """Return SHA-256 for text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object or return an empty object."""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def object_field(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a nested object field."""
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def list_of_dicts(value: object) -> list[dict[str, Any]]:
    """Return object rows from a possible list."""
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def string_list(value: object) -> list[str]:
    """Return string rows from a possible list."""
    return [str(item) for item in value] if isinstance(value, list) else []


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root."""
    return path if path.is_absolute() else repo_root / path


def main() -> None:
    """CLI entrypoint for operator action plan generation."""
    parser = argparse.ArgumentParser(description="Write a read-only operator action plan.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--experiments-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    _, _, payload = write_operator_action_plan(
        run_dir=args.run_dir,
        experiments_dir=args.experiments_dir,
        repo_root=args.repo_root,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
