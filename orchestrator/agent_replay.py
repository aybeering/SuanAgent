"""Offline replay helpers for deterministic agent input fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agents.file_protocol_demo_agent import build_proposal, load_proposal_intent
from orchestrator.agent_output_intake import proposal_from_raw_agent_output
from orchestrator.proposal import StrategyProposal, validate_proposal_contract


SUPPORTED_AGENT = "file_protocol_demo"
REPLAY_AGENT_NAME = "agent_replay_file_protocol_demo"


def replay_agent_input(
    *,
    agent_input_path: Path,
    output_path: Path | None = None,
    agent: str = SUPPORTED_AGENT,
) -> dict[str, object]:
    """Replay a deterministic demo agent from an existing agent_input.json."""
    if agent != SUPPORTED_AGENT:
        raise ValueError(f"Unsupported replay agent: {agent}")
    agent_input = load_json_object(agent_input_path)
    proposal_intent = load_proposal_intent(
        agent_input=agent_input,
        input_path=agent_input_path,
    )
    payload = build_proposal(agent_input, proposal_intent=proposal_intent)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return payload


def validate_replayed_proposal(
    *,
    agent_input_path: Path,
    proposal_payload: dict[str, object],
    agent: str = SUPPORTED_AGENT,
) -> dict[str, object]:
    """Validate a replayed proposal without applying its patch."""
    if agent != SUPPORTED_AGENT:
        raise ValueError(f"Unsupported replay agent: {agent}")
    agent_input = load_json_object(agent_input_path)
    proposal = replay_payload_to_strategy_proposal(
        agent_input=agent_input,
        proposal_payload=proposal_payload,
    )
    errors = validate_proposal_contract(
        proposal=proposal,
        expected_target_file=Path(str(agent_input["target_file"])),
        expected_round_index=int(agent_input["round_index"]),
    )
    return {
        "ok": not errors,
        "errors": list(errors),
        "protocol_version": proposal.protocol_version,
        "target_file": proposal.target_file,
        "round_index": proposal.round_index,
        "direction_tag": proposal.direction_tag,
        "applicable": proposal.applicable,
    }


def replay_payload_to_strategy_proposal(
    *,
    agent_input: dict[str, Any],
    proposal_payload: dict[str, object],
) -> StrategyProposal:
    """Convert replay JSON into the StrategyProposal contract shape."""
    raw_response = json.dumps(proposal_payload, indent=2, sort_keys=True)
    return proposal_from_raw_agent_output(
        raw_output=raw_response,
        agent_input=agent_input,
        agent_name=REPLAY_AGENT_NAME,
        default_summary="Replayed proposal output.",
        default_risk_notes="Replay validation uses the shared proposal intake path.",
        default_direction_tag="agent_replay_unknown",
        default_hypotheses=(
            "The replayed agent output must satisfy the shared proposal contract.",
        ),
    )


def replay_report(
    *,
    agent_input_path: Path,
    output_path: Path | None = None,
    agent: str = SUPPORTED_AGENT,
    validate: bool = False,
) -> dict[str, object]:
    """Replay an agent input and optionally include validation metadata."""
    proposal = replay_agent_input(
        agent_input_path=agent_input_path,
        output_path=output_path,
        agent=agent,
    )
    if not validate:
        return proposal
    return {
        "proposal": proposal,
        "validation": validate_replayed_proposal(
            agent_input_path=agent_input_path,
            proposal_payload=proposal,
            agent=agent,
        ),
    }


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def main() -> None:
    """CLI entrypoint for offline agent replay."""
    args = parse_args()
    payload = replay_report(
        agent_input_path=args.agent_input,
        output_path=args.output,
        agent=args.agent,
        validate=args.validate,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.validate:
        validation = payload.get("validation", {})
        if isinstance(validation, dict) and not validation.get("ok", False):
            raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for offline agent replay."""
    parser = argparse.ArgumentParser(
        description="Replay a deterministic agent from an existing agent_input.json.",
    )
    parser.add_argument("agent_input", type=Path, help="Path to agent_input.json.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write replayed proposal JSON.",
    )
    parser.add_argument(
        "--agent",
        default=SUPPORTED_AGENT,
        choices=[SUPPORTED_AGENT],
        help="Replay agent implementation to use.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate the replayed proposal contract without applying the patch.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
