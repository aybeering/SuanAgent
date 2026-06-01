"""Local demo agent for the file-protocol adapter.

This module intentionally behaves like a tiny external coding agent while
remaining deterministic and network-free. It reads the stable agent input JSON
and writes a structured proposal JSON to the output path supplied by the
file-protocol adapter.
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path
from typing import Any


OLD_THRESHOLD = "MIN_EDGE = 0.05"
NEW_THRESHOLD = "MIN_EDGE = 0.04"
STAKE_OLD = "STAKE = 10.0"
STAKE_NEW = "STAKE = 8.0"


def build_proposal(
    agent_input: dict[str, Any],
    *,
    proposal_intent: dict[str, Any] | None = None,
) -> dict[str, object]:
    """Return a deterministic proposal from file-protocol input JSON."""
    intent = proposal_intent or {}
    if intent.get("recommended_direction") == "reduce_stake":
        return build_replacement_proposal(
            agent_input=agent_input,
            old_text=STAKE_OLD,
            new_text=STAKE_NEW,
            direction_tag="file_protocol_demo_reduce_stake",
            summary="Demo file-protocol agent follows proposal intent to reduce STAKE.",
            risk_notes="May lower exposure while preserving signal threshold.",
            expected_metric_change={
                "trade_count": "same_or_decrease",
                "ev": "uncertain",
                "max_drawdown": "decrease",
            },
            hypotheses=[
                "Proposal intent recommended reduce_stake after weak threshold probes.",
                "Lower stake can reduce downside while keeping the strategy active.",
            ],
        )
    return build_replacement_proposal(
        agent_input=agent_input,
        old_text=OLD_THRESHOLD,
        new_text=NEW_THRESHOLD,
        direction_tag="file_protocol_demo_lower_min_edge",
        summary="Demo file-protocol agent lowers MIN_EDGE.",
        risk_notes="May increase trade count, slippage, and drawdown.",
        expected_metric_change={
            "trade_count": "increase",
            "ev": "uncertain",
            "avg_slippage": "increase",
        },
        hypotheses=[
            "Lowering MIN_EDGE can expose more candidate trades for validation.",
            "The deterministic policy gate should reject the patch if metrics do not improve.",
        ],
    )


def build_replacement_proposal(
    *,
    agent_input: dict[str, Any],
    old_text: str,
    new_text: str,
    direction_tag: str,
    summary: str,
    risk_notes: str,
    expected_metric_change: dict[str, str],
    hypotheses: list[str],
) -> dict[str, object]:
    """Return a structured proposal replacing one exact text snippet."""
    target_file = str(agent_input["target_file"])
    before = str(agent_input["target_file_content"])
    after = before.replace(old_text, new_text, 1)
    patch_diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{target_file}",
            tofile=f"b/{target_file}",
        )
    )

    if before == after:
        return {
            "summary": "Demo file-protocol agent found no supported edit.",
            "risk_notes": f"The expected snippet `{old_text}` was not present.",
            "direction_tag": "file_protocol_demo_noop",
            "expected_metric_change": {},
            "hypotheses": [
                "The demo agent only proposes fixed intent-driven edits.",
            ],
            "patch_diff": "",
        }

    return {
        "summary": summary,
        "risk_notes": risk_notes,
        "direction_tag": direction_tag,
        "expected_metric_change": expected_metric_change,
        "hypotheses": hypotheses,
        "patch_diff": patch_diff,
    }


def load_proposal_intent(
    *,
    agent_input: dict[str, Any],
    input_path: Path,
) -> dict[str, Any]:
    """Load proposal intent from the copied round artifacts when available."""
    artifacts = agent_input.get("artifacts", {})
    artifact_payload = artifacts if isinstance(artifacts, dict) else {}
    intent_ref = str(artifact_payload.get("proposal_intent_json", ""))
    candidates = [input_path.parent / "proposal_intent.json"]
    if intent_ref:
        candidates.extend(
            [
                Path(intent_ref),
                input_path.parent / Path(intent_ref).name,
            ]
        )
    for path in candidates:
        if not path.exists() or not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def main(argv: list[str] | None = None) -> int:
    """Run the demo file-protocol agent."""
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        print(
            "usage: python -m agents.file_protocol_demo_agent "
            "<agent_input.json> <agent_output.json>",
            file=sys.stderr,
        )
        return 2

    input_path = Path(args[0])
    output_path = Path(args[1])
    agent_input = json.loads(input_path.read_text(encoding="utf-8"))
    proposal_intent = load_proposal_intent(
        agent_input=agent_input,
        input_path=input_path,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            build_proposal(agent_input, proposal_intent=proposal_intent),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
