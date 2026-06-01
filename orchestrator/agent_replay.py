"""Offline replay helpers for deterministic agent input fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agents.file_protocol_demo_agent import build_proposal, load_proposal_intent


SUPPORTED_AGENT = "file_protocol_demo"


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


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def main() -> None:
    """CLI entrypoint for offline agent replay."""
    args = parse_args()
    payload = replay_agent_input(
        agent_input_path=args.agent_input,
        output_path=args.output,
        agent=args.agent,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


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
    return parser.parse_args()


if __name__ == "__main__":
    main()
