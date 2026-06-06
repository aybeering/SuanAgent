"""Read-only operator approval record for action-plan command candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.operator_action_plan import (
    OPERATOR_ACTION_PLAN_SCHEMA_VERSION,
    build_operator_action_plan,
)
from orchestrator.schema_validation import (
    load_schema,
    validate_json_file,
    validate_json_payload,
)


OPERATOR_ACTION_APPROVAL_SCHEMA_VERSION = "operator_action_approval_v1"
SCHEMA_PATH = Path("schemas/operator_action_approval.schema.json")
DEFAULT_OPERATOR_ID = "unassigned"
REQUIRED_CONFIRMATION_PHRASE = "APPROVE OPERATOR ACTION"


def write_operator_action_approval(
    *,
    run_dir: Path,
    repo_root: Path,
    experiments_dir: Path | None = None,
    operator_id: str = DEFAULT_OPERATOR_ID,
    action_id: str = "",
    command_label: str = "",
    explicit_approval: bool = False,
    confirmation_phrase: str = "",
) -> tuple[Path, Path, dict[str, object]]:
    """Write machine-readable and markdown operator action approval artifacts."""
    payload = build_operator_action_approval(
        run_dir=run_dir,
        repo_root=repo_root,
        experiments_dir=experiments_dir,
        operator_id=operator_id,
        action_id=action_id,
        command_label=command_label,
        explicit_approval=explicit_approval,
        confirmation_phrase=confirmation_phrase,
    )
    resolved_repo_root = repo_root.resolve()
    resolved_run_dir = resolve_path(run_dir, resolved_repo_root)
    errors = validate_operator_action_approval_payload(
        payload,
        run_dir=resolved_run_dir,
        repo_root=resolved_repo_root,
        experiments_dir=experiments_dir,
        operator_id=operator_id,
        action_id=action_id,
        command_label=command_label,
        explicit_approval=explicit_approval,
        confirmation_phrase=confirmation_phrase,
        require_current_evidence=True,
    )
    if errors:
        raise ValueError(
            "operator action approval failed schema validation: " + "; ".join(errors)
        )
    json_path = resolved_run_dir / "operator_action_approval.json"
    md_path = resolved_run_dir / "operator_action_approval.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(
        render_operator_action_approval_markdown(payload),
        encoding="utf-8",
    )
    errors = validate_operator_action_approval_file(
        payload_path=json_path,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError(
            "operator action approval failed schema validation: " + "; ".join(errors)
        )
    return json_path, md_path, payload


def build_operator_action_approval(
    *,
    run_dir: Path,
    repo_root: Path,
    experiments_dir: Path | None = None,
    operator_id: str = DEFAULT_OPERATOR_ID,
    action_id: str = "",
    command_label: str = "",
    explicit_approval: bool = False,
    confirmation_phrase: str = "",
) -> dict[str, object]:
    """Return a deterministic approval record for one action-plan command."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    experiments_root = (
        resolve_path(experiments_dir, repo_root)
        if experiments_dir is not None
        else run_dir.parent
    )
    plan_path = run_dir / "operator_action_plan.json"
    if plan_path.exists():
        action_plan = load_json_object(plan_path)
        plan_from_artifact = True
    else:
        action_plan = build_operator_action_plan(
            run_dir=run_dir,
            experiments_dir=experiments_root,
            repo_root=repo_root,
        )
        plan_from_artifact = False
    selected_action = find_action(
        action_plan=action_plan,
        action_id=action_id,
    )
    selected_command = find_command(
        action=selected_action,
        command_label=command_label,
    )
    phrase_hash = sha256_text(confirmation_phrase) if confirmation_phrase else ""
    required_phrase_hash = sha256_text(REQUIRED_CONFIRMATION_PHRASE)
    phrase_matches = confirmation_phrase == REQUIRED_CONFIRMATION_PHRASE
    eligible = approval_eligible(
        action_plan=action_plan,
        selected_action=selected_action,
        selected_command=selected_command,
        action_id=action_id,
        command_label=command_label,
    )
    approval_recorded = bool(explicit_approval and phrase_matches and eligible)
    blockers = approval_blockers(
        action_plan=action_plan,
        selected_action=selected_action,
        selected_command=selected_command,
        action_id=action_id,
        command_label=command_label,
        explicit_approval=explicit_approval,
        phrase_matches=phrase_matches,
        eligible=eligible,
    )
    payload: dict[str, object] = {
        "schema_version": OPERATOR_ACTION_APPROVAL_SCHEMA_VERSION,
        "run_id": str(action_plan.get("run_id", run_dir.name)),
        "run_dir": str(run_dir),
        "status": approval_status(
            action_plan=action_plan,
            eligible=eligible,
            approval_recorded=approval_recorded,
            explicit_approval=explicit_approval,
        ),
        "ok": bool(action_plan),
        "source_action_plan": {
            "artifact_name": "operator_action_plan",
            "from_artifact": plan_from_artifact,
            "file": file_record(plan_path),
        },
        "operator_intent": {
            "approval_recorded": approval_recorded,
            "explicit_approval": bool(explicit_approval),
            "operator_id": str(operator_id),
            "target_action_id": str(action_id),
            "target_command_label": str(command_label),
            "required_confirmation_phrase_hash": required_phrase_hash,
            "provided_confirmation_phrase_hash": phrase_hash,
            "confirmation_phrase_matches": phrase_matches,
        },
        "selected_action": selected_action_record(selected_action),
        "selected_command": selected_command_record(selected_command),
        "approval_gate": {
            "eligible_for_approval": eligible,
            "approval_blockers": blockers,
            "requires_action_plan": True,
            "requires_known_action_id": True,
            "requires_known_command_label": True,
            "requires_explicit_approval_flag": True,
            "requires_matching_confirmation_phrase": True,
            "approval_does_not_execute_command": True,
        },
        "recommended_next_actions": recommended_next_actions(
            approval_recorded=approval_recorded,
            eligible=eligible,
            blockers=blockers,
        ),
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
            "approval_does_not_execute_command": True,
            "command_still_requires_explicit_execution": True,
        },
    }
    return payload


def find_action(
    *,
    action_plan: dict[str, object],
    action_id: str,
) -> dict[str, Any]:
    """Return the selected action row, or an empty dict."""
    if not action_id:
        return {}
    for row in list_of_dicts(action_plan.get("actions", [])):
        if str(row.get("action_id", "")) == action_id:
            return row
    return {}


def find_command(
    *,
    action: dict[str, Any],
    command_label: str,
) -> dict[str, Any]:
    """Return the selected command row, or an empty dict."""
    if not command_label:
        return {}
    for row in list_of_dicts(action.get("command_candidates", [])):
        if str(row.get("label", "")) == command_label:
            return row
    return {}


def approval_eligible(
    *,
    action_plan: dict[str, object],
    selected_action: dict[str, Any],
    selected_command: dict[str, Any],
    action_id: str,
    command_label: str,
) -> bool:
    """Return whether the selected command can be approved."""
    return bool(
        action_plan
        and action_plan.get("schema_version") == OPERATOR_ACTION_PLAN_SCHEMA_VERSION
        and action_id
        and command_label
        and selected_action
        and selected_command
    )


def approval_blockers(
    *,
    action_plan: dict[str, object],
    selected_action: dict[str, Any],
    selected_command: dict[str, Any],
    action_id: str,
    command_label: str,
    explicit_approval: bool,
    phrase_matches: bool,
    eligible: bool,
) -> list[str]:
    """Return deterministic approval blockers."""
    blockers: list[str] = []
    if not action_plan:
        blockers.append("missing_operator_action_plan")
    if action_plan.get("schema_version") != OPERATOR_ACTION_PLAN_SCHEMA_VERSION:
        blockers.append("operator_action_plan_schema_invalid")
    if not action_id:
        blockers.append("target_action_id_missing")
    elif not selected_action:
        blockers.append("target_action_id_not_found")
    if not command_label:
        blockers.append("target_command_label_missing")
    elif selected_action and not selected_command:
        blockers.append("target_command_label_not_found")
    if not explicit_approval:
        blockers.append("operator_approval_not_recorded")
    if explicit_approval and not phrase_matches:
        blockers.append("confirmation_phrase_mismatch")
    if not eligible:
        blockers.append("not_eligible_for_approval")
    return unique_strings(blockers)


def approval_status(
    *,
    action_plan: dict[str, object],
    eligible: bool,
    approval_recorded: bool,
    explicit_approval: bool,
) -> str:
    """Return compact approval status."""
    if not action_plan:
        return "needs_action_plan"
    if approval_recorded:
        return "approval_recorded"
    if eligible and not explicit_approval:
        return "ready_for_operator_approval"
    return "approval_blocked"


def selected_action_record(action: dict[str, Any]) -> dict[str, object]:
    """Return selected action audit fields."""
    return {
        "action_id": str(action.get("action_id", "")),
        "action_type": str(action.get("action_type", "")),
        "status": str(action.get("status", "")),
        "source_text": str(action.get("source_text", "")),
    }


def selected_command_record(command: dict[str, Any]) -> dict[str, object]:
    """Return selected command audit fields."""
    command_text = str(command.get("command", ""))
    recorded_sha = str(command.get("command_sha256", ""))
    return {
        "label": str(command.get("label", "")),
        "command": command_text,
        "command_sha256": recorded_sha,
        "computed_command_sha256": sha256_text(command_text) if command_text else "",
        "command_sha256_matches": bool(
            command_text and recorded_sha == sha256_text(command_text)
        ),
        "expected_artifact": str(command.get("expected_artifact", "")),
        "writes_repository": bool(command.get("writes_repository", False)),
        "promotes_champion": bool(command.get("promotes_champion", False)),
        "runs_backtests": bool(command.get("runs_backtests", False)),
        "requires_explicit_operator_invocation": bool(
            command.get("requires_explicit_operator_invocation", False)
        ),
        "executed_by_approval": False,
    }


def recommended_next_actions(
    *,
    approval_recorded: bool,
    eligible: bool,
    blockers: list[str],
) -> list[str]:
    """Return next actions for operator review."""
    if approval_recorded:
        return [
            "Review the approved command digest before invoking the command explicitly."
        ]
    if eligible:
        return ["Record explicit approval with the required confirmation phrase."]
    if "target_action_id_missing" in blockers or "target_command_label_missing" in blockers:
        return ["Select an action id and command label from operator_action_plan.json."]
    return ["Resolve approval blockers before executing any command candidate."]


def render_operator_action_approval_markdown(payload: dict[str, object]) -> str:
    """Render operator action approval as markdown."""
    intent = object_field(payload, "operator_intent")
    gate = object_field(payload, "approval_gate")
    action = object_field(payload, "selected_action")
    command = object_field(payload, "selected_command")
    lines = [
        "# Operator Action Approval",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- OK: `{payload.get('ok', False)}`",
        f"- Approval recorded: `{intent.get('approval_recorded', False)}`",
        f"- Operator id: `{intent.get('operator_id', '')}`",
        f"- Target action: `{intent.get('target_action_id', '')}`",
        f"- Target command: `{intent.get('target_command_label', '')}`",
        "",
        "## Selected Command",
        "",
        f"- Action type: `{action.get('action_type', '')}`",
        f"- Command label: `{command.get('label', '')}`",
        f"- Command SHA-256: `{command.get('command_sha256', '')}`",
        f"- Writes repository: `{command.get('writes_repository', False)}`",
        f"- Promotes champion: `{command.get('promotes_champion', False)}`",
        f"- Runs backtests: `{command.get('runs_backtests', False)}`",
        "",
        "```bash",
        str(command.get("command", "")),
        "```",
        "",
        "## Approval Blockers",
        "",
    ]
    blockers = string_list(gate.get("approval_blockers", []))
    lines.extend([f"- `{blocker}`" for blocker in blockers] or ["- none"])
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- This artifact is inspection-only and reads saved artifacts only.",
            "- It records approval intent but does not execute commands, execute agents, run backtests, write config, promote champions, apply patches, route agents, or change acceptance.",
            "- The approved command still requires explicit operator execution.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_operator_action_approval_file(
    *,
    payload_path: Path,
    repo_root: Path,
) -> tuple[str, ...]:
    """Validate a saved operator action approval artifact."""
    errors = list(
        validate_json_file(
            payload_path=payload_path,
            schema_path=repo_root / SCHEMA_PATH,
        )
    )
    if payload_path.exists():
        errors.extend(
            validate_operator_action_approval_consistency(
                load_json_object(payload_path),
                run_dir=payload_path.parent,
                repo_root=repo_root,
            )
        )
    return tuple(errors)


def validate_operator_action_approval_payload(
    payload: dict[str, object],
    *,
    run_dir: Path,
    repo_root: Path,
    experiments_dir: Path | None = None,
    operator_id: str = DEFAULT_OPERATOR_ID,
    action_id: str = "",
    command_label: str = "",
    explicit_approval: bool = False,
    confirmation_phrase: str = "",
    require_current_evidence: bool = False,
) -> tuple[str, ...]:
    """Validate an in-memory operator action approval payload."""
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    comparable_payload = strip_terminal_metadata(payload)
    schema = load_schema(repo_root / SCHEMA_PATH)
    errors = list(
        validate_json_payload(
            payload=comparable_payload,
            schema=schema,
            schema_dir=(repo_root / SCHEMA_PATH).parent,
        )
    )
    errors.extend(
        validate_operator_action_approval_consistency(
            comparable_payload,
            run_dir=run_dir,
            repo_root=repo_root,
        )
    )
    if require_current_evidence:
        expected = build_operator_action_approval(
            run_dir=run_dir,
            repo_root=repo_root,
            experiments_dir=experiments_dir,
            operator_id=operator_id,
            action_id=action_id,
            command_label=command_label,
            explicit_approval=explicit_approval,
            confirmation_phrase=confirmation_phrase,
        )
        if comparable_payload != expected:
            errors.append("operator_action_approval current evidence mismatch")
    return tuple(errors)


def validate_operator_action_approval_consistency(
    payload: dict[str, object],
    *,
    run_dir: Path,
    repo_root: Path,
) -> tuple[str, ...]:
    """Validate approval status, selected command, hashes, and policy fields."""
    errors: list[str] = []
    repo_root = repo_root.resolve()
    run_dir = resolve_path(run_dir, repo_root)
    source = object_field(payload, "source_action_plan")
    source_file = object_field(source, "file")
    plan_path = resolve_path(Path(str(source_file.get("path", ""))), repo_root)
    action_plan = load_json_object(plan_path)
    intent = object_field(payload, "operator_intent")
    selected_action = object_field(payload, "selected_action")
    selected_command = object_field(payload, "selected_command")
    gate = object_field(payload, "approval_gate")
    policy = object_field(payload, "policy")

    if str(payload.get("run_id", "")) != run_dir.name:
        errors.append("operator_action_approval run_id mismatch")
    if str(payload.get("run_dir", "")) != str(run_dir):
        errors.append("operator_action_approval run_dir mismatch")
    if source.get("artifact_name") != "operator_action_plan":
        errors.append("operator_action_approval source artifact mismatch")
    if str(source_file.get("sha256", "")) != file_sha256(plan_path):
        errors.append("operator_action_approval source digest mismatch")

    action_id = str(intent.get("target_action_id", ""))
    command_label = str(intent.get("target_command_label", ""))
    plan_action = find_action(action_plan=action_plan, action_id=action_id)
    plan_command = find_command(action=plan_action, command_label=command_label)
    expected_selected_action = selected_action_record(plan_action)
    expected_selected_command = selected_command_record(plan_command)
    append_field_mismatches(
        errors,
        prefix="operator_action_approval selected_action",
        payload=selected_action,
        expected=expected_selected_action,
        field_names=("action_id", "action_type", "status", "source_text"),
    )
    append_field_mismatches(
        errors,
        prefix="operator_action_approval selected_command",
        payload=selected_command,
        expected=expected_selected_command,
        field_names=(
            "label",
            "command",
            "command_sha256",
            "computed_command_sha256",
            "command_sha256_matches",
            "expected_artifact",
            "writes_repository",
            "promotes_champion",
            "runs_backtests",
            "requires_explicit_operator_invocation",
            "executed_by_approval",
        ),
    )
    if selected_action != expected_selected_action:
        errors.append("operator_action_approval selected action mismatch")
    if selected_command != expected_selected_command:
        errors.append("operator_action_approval selected command mismatch")

    required_hash = sha256_text(REQUIRED_CONFIRMATION_PHRASE)
    provided_hash = str(intent.get("provided_confirmation_phrase_hash", ""))
    if intent.get("required_confirmation_phrase_hash") != required_hash:
        errors.append("operator_action_approval required phrase hash mismatch")
    if bool(intent.get("confirmation_phrase_matches", False)) != (
        provided_hash == required_hash and bool(provided_hash)
    ):
        errors.append("operator_action_approval confirmation phrase mismatch")

    command_text = str(selected_command.get("command", ""))
    command_sha = str(selected_command.get("command_sha256", ""))
    if str(selected_command.get("computed_command_sha256", "")) != (
        sha256_text(command_text) if command_text else ""
    ):
        errors.append("operator_action_approval computed command digest mismatch")
    if bool(selected_command.get("command_sha256_matches", False)) != (
        bool(command_text) and command_sha == sha256_text(command_text)
    ):
        errors.append("operator_action_approval command digest flag mismatch")
    if selected_command.get("executed_by_approval") is not False:
        errors.append("operator_action_approval execution flag mismatch")

    explicit_approval = bool(intent.get("explicit_approval", False))
    phrase_matches = bool(intent.get("confirmation_phrase_matches", False))
    eligible = approval_eligible(
        action_plan=action_plan,
        selected_action=plan_action,
        selected_command=plan_command,
        action_id=action_id,
        command_label=command_label,
    )
    approval_recorded = bool(explicit_approval and phrase_matches and eligible)
    expected_blockers = approval_blockers(
        action_plan=action_plan,
        selected_action=plan_action,
        selected_command=plan_command,
        action_id=action_id,
        command_label=command_label,
        explicit_approval=explicit_approval,
        phrase_matches=phrase_matches,
        eligible=eligible,
    )
    expected_status = approval_status(
        action_plan=action_plan,
        eligible=eligible,
        approval_recorded=approval_recorded,
        explicit_approval=explicit_approval,
    )
    expected_intent = {
        "approval_recorded": approval_recorded,
        "explicit_approval": explicit_approval,
        "target_action_id": action_id,
        "target_command_label": command_label,
        "required_confirmation_phrase_hash": required_hash,
        "provided_confirmation_phrase_hash": provided_hash,
        "confirmation_phrase_matches": bool(
            provided_hash == required_hash and bool(provided_hash)
        ),
    }
    append_field_mismatches(
        errors,
        prefix="operator_action_approval operator_intent",
        payload=intent,
        expected=expected_intent,
        field_names=tuple(expected_intent),
    )
    if bool(payload.get("ok", False)) != bool(action_plan):
        errors.append("operator_action_approval ok mismatch")
    if str(payload.get("status", "")) != expected_status:
        errors.append("operator_action_approval status mismatch")
    if intent.get("approval_recorded") is not approval_recorded:
        errors.append("operator_action_approval recorded mismatch")
    expected_gate = {
        "eligible_for_approval": eligible,
        "approval_blockers": expected_blockers,
        "requires_action_plan": True,
        "requires_known_action_id": True,
        "requires_known_command_label": True,
        "requires_explicit_approval_flag": True,
        "requires_matching_confirmation_phrase": True,
        "approval_does_not_execute_command": True,
    }
    append_field_mismatches(
        errors,
        prefix="operator_action_approval approval_gate",
        payload=gate,
        expected=expected_gate,
        field_names=tuple(expected_gate),
    )
    if gate.get("eligible_for_approval") is not eligible:
        errors.append("operator_action_approval eligibility mismatch")
    if string_list(gate.get("approval_blockers", [])) != expected_blockers:
        errors.append("operator_action_approval blockers mismatch")
    if string_list(payload.get("recommended_next_actions", [])) != (
        recommended_next_actions(
            approval_recorded=approval_recorded,
            eligible=eligible,
            blockers=expected_blockers,
        )
    ):
        errors.append("operator_action_approval next actions mismatch")

    expected_policy = {
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
        "approval_does_not_execute_command": True,
        "command_still_requires_explicit_execution": True,
    }
    append_field_mismatches(
        errors,
        prefix="operator_action_approval policy",
        payload=policy,
        expected=expected_policy,
        field_names=tuple(expected_policy),
    )
    if policy != expected_policy:
        errors.append("operator_action_approval policy mismatch")
    return tuple(errors)


def strip_terminal_metadata(payload: dict[str, object]) -> dict[str, object]:
    """Return payload without CLI-only annotation fields."""
    stripped = dict(payload)
    stripped.pop("from_artifact", None)
    return stripped


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


def append_field_mismatches(
    errors: list[str],
    *,
    prefix: str,
    payload: dict[str, Any],
    expected: dict[str, object],
    field_names: tuple[str, ...],
) -> None:
    """Append field-specific mismatch messages for comparable objects."""
    for field_name in field_names:
        if payload.get(field_name) != expected.get(field_name):
            errors.append(f"{prefix} {field_name} mismatch")


def unique_strings(values: list[str]) -> list[str]:
    """Return values in stable first-seen order."""
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def resolve_path(path: Path, repo_root: Path) -> Path:
    """Resolve a path relative to the repository root."""
    return path if path.is_absolute() else repo_root / path


def main() -> None:
    """CLI entrypoint for operator action approval."""
    parser = argparse.ArgumentParser(
        description="Record read-only operator approval for one action-plan command."
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--experiments-dir", type=Path)
    parser.add_argument("--operator-id", default=DEFAULT_OPERATOR_ID)
    parser.add_argument("--action-id", default="")
    parser.add_argument("--command-label", default="")
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--confirmation-phrase", default="")
    args = parser.parse_args()
    _, _, payload = write_operator_action_approval(
        run_dir=args.run_dir,
        repo_root=args.repo_root,
        experiments_dir=args.experiments_dir,
        operator_id=args.operator_id,
        action_id=args.action_id,
        command_label=args.command_label,
        explicit_approval=args.approve,
        confirmation_phrase=args.confirmation_phrase,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
