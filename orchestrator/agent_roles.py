"""Round-level agent role contract artifacts."""

from __future__ import annotations

import json
from pathlib import Path


AGENT_ROLE_CONTRACTS_SCHEMA_VERSION = "agent_role_contracts_v1"


def write_agent_role_contracts(
    *,
    output_path: Path,
    repo_root: Path,
    round_dir: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    agent_roles: tuple[dict[str, object], ...],
) -> Path:
    """Write the deterministic role contract map for one round."""
    payload = agent_role_contracts_payload(
        repo_root=repo_root,
        round_dir=round_dir,
        run_id=run_id,
        round_id=round_id,
        round_index=round_index,
        agent_roles=agent_roles,
    )
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def agent_role_contracts_payload(
    *,
    repo_root: Path,
    round_dir: Path,
    run_id: str,
    round_id: str,
    round_index: int,
    agent_roles: tuple[dict[str, object], ...],
) -> dict[str, object]:
    """Return a JSON-friendly role contract map for one round."""
    roles = compact_agent_roles(agent_roles)
    return {
        "schema_version": AGENT_ROLE_CONTRACTS_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "round_index": round_index,
        "round_dir": relative_path(round_dir, repo_root),
        "active_roles": [
            role["role_name"]
            for role in roles
            if role["enabled"] and role["execution_mode"] == "active"
        ],
        "implemented_roles": [
            role["role_name"]
            for role in roles
            if role["implemented"]
        ],
        "stub_roles": [
            role["role_name"]
            for role in roles
            if role["execution_mode"] == "stub_contract"
        ],
        "roles": roles,
        "role_topology": default_role_topology(roles),
        "execution_policy": {
            "only_strategy_modifier_executes_in_v0_5": True,
            "deterministic_gates_keep_acceptance_authority": True,
            "non_implemented_roles_are_contract_only": True,
        },
    }


def compact_agent_roles(
    agent_roles: tuple[dict[str, object], ...],
) -> list[dict[str, object]]:
    """Return stable role metadata safe for external agent input."""
    return [
        {
            "role_name": str(role.get("role_name", "")),
            "stage": str(role.get("stage", "")),
            "enabled": bool(role.get("enabled", False)),
            "execution_mode": str(role.get("execution_mode", "")),
            "required": bool(role.get("required", False)),
            "implemented": bool(role.get("implemented", False)),
            "description": str(role.get("description", "")),
            "allowed_adapters": string_list(role.get("allowed_adapters", [])),
            "consumes": string_list(role.get("consumes", [])),
            "produces": string_list(role.get("produces", [])),
            "decision_authority": str(role.get("decision_authority", "")),
        }
        for role in agent_roles
    ]


def default_role_topology(roles: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return the planned role edges that are present in the configured roles."""
    role_names = {str(role.get("role_name", "")) for role in roles}
    planned_edges = (
        {
            "from": "strategy_modifier",
            "to": "analysis",
            "artifact": "proposal.json",
            "enabled": False,
        },
        {
            "from": "analysis",
            "to": "visual_review",
            "artifact": "analysis_notes.json",
            "enabled": False,
        },
        {
            "from": "analysis",
            "to": "overfit_validator",
            "artifact": "decision.json",
            "enabled": False,
        },
        {
            "from": "overfit_validator",
            "to": "strategy_modifier",
            "artifact": "overfit_validation.json",
            "enabled": False,
        },
    )
    return [
        edge
        for edge in planned_edges
        if edge["from"] in role_names and edge["to"] in role_names
    ]


def string_list(value: object) -> list[str]:
    """Return a deterministic list of strings."""
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list | tuple):
        return [str(item) for item in value if str(item)]
    return []


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
