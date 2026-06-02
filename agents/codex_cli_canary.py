#!/usr/bin/env python3
"""Local Codex CLI canary executable.

This script intentionally mimics a Codex CLI subprocess for CI and local safety
checks. It reads the prompt from stdin, ignores Codex-style CLI arguments, and
prints a deterministic structured proposal with a strategy-only patch.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path
import sys


OLD_THRESHOLD = "MIN_EDGE = 0.05"
NEW_THRESHOLD = "MIN_EDGE = 0.04"
TARGET_FILE = Path("strategies/current_strategy.py")


def main() -> None:
    """Emit a fixed strategy-only patch as structured Codex-like output."""
    prompt = sys.stdin.read()
    before = TARGET_FILE.read_text(encoding="utf-8")
    after = before.replace(OLD_THRESHOLD, NEW_THRESHOLD, 1)
    patch = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{TARGET_FILE.as_posix()}",
            tofile=f"b/{TARGET_FILE.as_posix()}",
        )
    )
    payload = {
        "summary": "Canary Codex CLI fixture lowered MIN_EDGE.",
        "risk_notes": "This is a local canary patch; deterministic gates still decide.",
        "direction_tag": "codex_cli_canary_lower_min_edge",
        "expected_metric_change": {
            "trade_count": "increase",
            "ev": "uncertain",
        },
        "hypotheses": [
            "A controlled executable can traverse the guarded Codex CLI path.",
            "The deterministic policy gate can reject and roll back the canary patch.",
        ],
        "patch_diff": patch,
        "canary": {
            "kind": "local_codex_cli_canary",
            "prompt_chars": len(prompt),
            "argv": sys.argv[1:],
        },
    }
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
