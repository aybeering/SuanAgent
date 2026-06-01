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


def build_proposal(agent_input: dict[str, Any]) -> dict[str, object]:
    """Return a deterministic proposal from file-protocol input JSON."""
    target_file = str(agent_input["target_file"])
    before = str(agent_input["target_file_content"])
    after = before.replace(OLD_THRESHOLD, NEW_THRESHOLD, 1)
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
            "risk_notes": "The expected MIN_EDGE threshold was not present.",
            "direction_tag": "file_protocol_demo_noop",
            "expected_metric_change": {},
            "hypotheses": [
                "The demo agent only proposes the fixed MIN_EDGE threshold edit.",
            ],
            "patch_diff": "",
        }

    return {
        "summary": "Demo file-protocol agent lowers MIN_EDGE.",
        "risk_notes": "May increase trade count, slippage, and drawdown.",
        "direction_tag": "file_protocol_demo_lower_min_edge",
        "expected_metric_change": {
            "trade_count": "increase",
            "ev": "uncertain",
            "avg_slippage": "increase",
        },
        "hypotheses": [
            "Lowering MIN_EDGE can expose more candidate trades for validation.",
            "The deterministic policy gate should reject the patch if metrics do not improve.",
        ],
        "patch_diff": patch_diff,
    }


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
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(build_proposal(agent_input), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
