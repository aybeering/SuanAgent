#!/usr/bin/env python3
"""Hardcoded stub visual agent for isolated visual_marks workspaces.

Pipeline:
1. Accept packed HTML pages from run_request.
2. Vision stub (no model): emit empty collected points.
3. Call tools/write_mark_points.py.
4. Write agent_trace.json.

Expected V0 stub outcome: HTML accepted, script succeeds, zero signals.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


TRACE_SCHEMA_VERSION = "visual_agent_trace_v1"
COLLECTED_SCHEMA_VERSION = "collected_points_v1"
RUN_REQUEST_PATH = Path("input/run_request.json")
COLLECTED_POINTS_PATH = Path("output/collected_points.json")
AGENT_TRACE_PATH = Path("output/agent_trace.json")
MARKING_SCRIPT = Path("tools/write_mark_points.py")


def main() -> int:
    """Run the stub visual agent from the workspace root."""
    workspace_root = Path.cwd()
    html_accepted = False
    html_count = 0
    script_command: list[str] = []
    script_exit_code = 1
    signal_count = 0
    notes = "stub vision emits no trade points"

    try:
        run_request = load_json_object(workspace_root / RUN_REQUEST_PATH)
        html_files = list(run_request.get("html_files", []))
        if not html_files:
            raise ValueError("run_request.html_files is empty")
        for relative in html_files:
            path = workspace_root / relative
            if not path.is_file():
                raise FileNotFoundError(f"Missing HTML page: {relative}")
            # Touch-read to prove acceptance without parsing visuals.
            _ = path.read_text(encoding="utf-8")
        html_accepted = True
        html_count = len(html_files)

        collected = {
            "schema_version": COLLECTED_SCHEMA_VERSION,
            "points": [],
        }
        write_json(workspace_root / COLLECTED_POINTS_PATH, collected)
        signal_count = 0

        script_command = [
            sys.executable,
            str(MARKING_SCRIPT),
            "--run-request",
            str(RUN_REQUEST_PATH),
            "--points",
            str(COLLECTED_POINTS_PATH),
            "--output-dir",
            "output",
        ]
        completed = subprocess.run(
            script_command,
            cwd=workspace_root,
            check=False,
            capture_output=True,
            text=True,
        )
        script_exit_code = int(completed.returncode)
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        if script_exit_code != 0:
            notes = f"marking script failed with exit {script_exit_code}"
    except Exception as exc:  # noqa: BLE001 - trace must capture stub failures
        notes = str(exc)
        script_exit_code = 1 if script_exit_code == 0 else script_exit_code
        html_accepted = html_accepted
    finally:
        run_id = ""
        workspace_id = ""
        try:
            request = load_json_object(workspace_root / RUN_REQUEST_PATH)
            run_id = str(request.get("run_id", ""))
            workspace_id = str(request.get("workspace_id", ""))
        except Exception:  # noqa: BLE001
            pass
        trace = {
            "schema_version": TRACE_SCHEMA_VERSION,
            "run_id": run_id or "unknown",
            "workspace_id": workspace_id or "unknown",
            "html_accepted": html_accepted,
            "html_count": html_count,
            "vision_mode": "stub_empty",
            "script_command": script_command
            or [
                sys.executable,
                str(MARKING_SCRIPT),
                "--run-request",
                str(RUN_REQUEST_PATH),
                "--points",
                str(COLLECTED_POINTS_PATH),
                "--output-dir",
                "output",
            ],
            "script_exit_code": script_exit_code,
            "signal_count": signal_count,
            "notes": notes,
        }
        write_json(workspace_root / AGENT_TRACE_PATH, trace)

    return 0 if html_accepted and script_exit_code == 0 else 1


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write deterministic pretty JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
