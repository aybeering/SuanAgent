"""Deterministic proposal intent planner for strategy modifier agents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROPOSAL_INTENT_SCHEMA_VERSION = "proposal_intent_v1"
DEFAULT_DIRECTION = "lower_min_edge"
ALTERNATIVE_DIRECTION = "reduce_stake"
DEFAULT_DIRECTION_CANDIDATES = (DEFAULT_DIRECTION, ALTERNATIVE_DIRECTION, "raise_min_edge")


def write_proposal_intent(
    *,
    context_path: Path,
    output_path: Path,
) -> Path:
    """Write a deterministic strategy proposal intent artifact."""
    payload = build_proposal_intent(context_path=context_path)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_path.with_suffix(".md").write_text(
        render_proposal_intent_markdown(payload),
        encoding="utf-8",
    )
    return output_path


def build_proposal_intent(*, context_path: Path) -> dict[str, object]:
    """Return a compact proposal intent from one agent context artifact."""
    context = load_json(context_path.with_suffix(".json"))
    run_id = str(context.get("run_id", ""))
    round_id = str(context.get("current_round_id", ""))
    target_file = str(context.get("target_file", "strategies/current_strategy.py"))
    prior_rounds = list_of_dicts(context.get("prior_rounds", []))
    recent_briefs = list_of_dicts(context.get("recent_research_briefs", []))
    memory_records = list_of_dicts(context.get("global_outcome_memory", []))
    champion = dict_payload(context.get("champion", {}))
    search_space = dict_payload(context.get("strategy_search_space", {}))
    direction_candidates = search_space_directions(search_space)

    avoid_directions = sorted(
        {
            str(row.get("direction_tag", ""))
            for row in [*prior_rounds, *memory_records]
            if str(row.get("direction_tag", "")) and not bool(row.get("accepted", False))
        }
        | {
            str(row.get("top_direction_tag", "") or row.get("selected_direction_tag", ""))
            for row in recent_briefs
            if recent_brief_failed(row)
        }
        | {
            direction
            for row in recent_briefs
            for direction in string_list(row.get("recommended_avoid_directions", []))
            if recent_brief_failed(row)
        }
    )
    avoid_directions = [direction for direction in avoid_directions if direction]

    recommended_direction = DEFAULT_DIRECTION
    reason = "No prior weak direction was found; start with the default threshold probe."
    evidence = []
    if DEFAULT_DIRECTION in avoid_directions:
        recommended_direction = choose_recommended_direction(
            avoid_directions=avoid_directions,
            direction_candidates=direction_candidates,
            fallback_direction=search_space_fallback(search_space),
        )
        reason = (
            "Recent context shows lower_min_edge was weak; probe a different "
            "strategy dimension."
        )
        evidence.append("lower_min_edge appears in failed prior context")
    elif any(
        str(row.get("recommended_primary_focus", "")) == "switch_modifier_direction"
        for row in recent_briefs
    ):
        recommended_direction = choose_recommended_direction(
            avoid_directions=avoid_directions,
            direction_candidates=direction_candidates,
            fallback_direction=search_space_fallback(search_space),
        )
        reason = "Recent research brief recommends switching modifier direction."
        evidence.append("recent research focus recommends switching direction")
    elif prior_rounds:
        recommended_direction = choose_recommended_direction(
            avoid_directions=avoid_directions,
            direction_candidates=direction_candidates,
            fallback_direction=search_space_fallback(search_space),
        )
        reason = "Same-run history exists; avoid repeating the first probe dimension."
        evidence.append("same-run prior rounds exist")

    champion_gap = 0.0
    if champion.get("exists"):
        champion_gap = float(champion.get("validation_ev_delta", 0.0))
        evidence.append(
            "current champion validation EV delta "
            f"{champion_gap:.6f}"
        )

    payload: dict[str, object] = {
        "schema_version": PROPOSAL_INTENT_SCHEMA_VERSION,
        "run_id": run_id,
        "round_id": round_id,
        "target_file": target_file,
        "recommended_direction": recommended_direction,
        "avoid_directions": avoid_directions,
        "reason": reason,
        "evidence": evidence,
        "constraints": [
            "modify only strategies/current_strategy.py",
            "acceptance is decided only by deterministic policy gates",
            "return a proposal_v1-compatible patch",
        ],
        "source_artifacts": {
            "agent_context_json": str(context_path.with_suffix(".json")),
            "agent_context_markdown": str(context_path),
        },
        "strategy_search_space": {
            "schema_version": search_space.get("schema_version", ""),
            "direction_order": direction_candidates,
            "fallback_direction": search_space_fallback(search_space),
            "policy": search_space.get("policy", {}),
        },
        "champion_gap": {
            "active": bool(champion.get("exists", False)),
            "champion_run_id": champion.get("champion_run_id", ""),
            "validation_ev_delta": champion_gap,
        },
    }
    return payload


def render_proposal_intent_markdown(payload: dict[str, object]) -> str:
    """Render a proposal intent payload as markdown."""
    evidence = [str(item) for item in payload.get("evidence", [])]
    constraints = [str(item) for item in payload.get("constraints", [])]
    avoid = [str(item) for item in payload.get("avoid_directions", [])]
    search_space = dict_payload(payload.get("strategy_search_space", {}))
    lines = [
        "# Proposal Intent",
        "",
        f"- Run id: `{payload.get('run_id', '')}`",
        f"- Round id: `{payload.get('round_id', '')}`",
        f"- Target file: `{payload.get('target_file', '')}`",
        f"- Recommended direction: `{payload.get('recommended_direction', '')}`",
        f"- Avoid directions: `{', '.join(avoid) if avoid else 'none'}`",
        f"- Reason: {payload.get('reason', '')}",
        "",
        "## Evidence",
        "",
    ]
    lines.extend(f"- {item}" for item in evidence or ["No prior evidence."])
    lines.extend(
        [
            "",
            "## Strategy Search Space",
            "",
            "- Direction order: "
            f"`{', '.join(string_list(search_space.get('direction_order', []))) or 'none'}`",
            f"- Fallback direction: `{search_space.get('fallback_direction', 'none')}`",
        ]
    )
    lines.extend(["", "## Constraints", ""])
    lines.extend(f"- {item}" for item in constraints)
    return "\n".join(lines).rstrip() + "\n"


def recent_brief_failed(payload: dict[str, Any]) -> bool:
    """Return whether a compact research brief describes a failed direction."""
    if payload.get("accepted_round"):
        return False
    status = str(payload.get("status", ""))
    return status.startswith("stopped") or status == "failed"


def choose_recommended_direction(
    *,
    avoid_directions: list[str],
    direction_candidates: list[str],
    fallback_direction: str,
) -> str:
    """Return the first known direction not already marked for avoidance."""
    for direction in direction_candidates:
        if direction not in avoid_directions:
            return direction
    return fallback_direction


def search_space_directions(search_space: dict[str, Any]) -> list[str]:
    """Return configured direction order from agent context."""
    direction_order = string_list(search_space.get("direction_order", []))
    if direction_order:
        return direction_order
    rows = list_of_dicts(search_space.get("directions", []))
    row_order = [
        str(row.get("direction_tag", ""))
        for row in rows
        if str(row.get("direction_tag", ""))
    ]
    return row_order or list(DEFAULT_DIRECTION_CANDIDATES)


def search_space_fallback(search_space: dict[str, Any]) -> str:
    """Return configured fallback direction for exhausted search space."""
    fallback = str(search_space.get("fallback_direction", ""))
    return fallback or "new_modifier_profile"


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object if present."""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def list_of_dicts(value: object) -> list[dict[str, Any]]:
    """Return dict items from a list-like payload."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    """Return stringified items from a list-like payload."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def dict_payload(value: object) -> dict[str, Any]:
    """Return a dict payload or an empty mapping."""
    return value if isinstance(value, dict) else {}
