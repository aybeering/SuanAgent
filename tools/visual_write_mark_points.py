#!/usr/bin/env python3
"""Agent-friendly visual mark-points writer for isolated visual_marks workspaces.

Designed to be copied into a workspace as ``tools/write_mark_points.py``.
Call from the workspace root:

    python tools/write_mark_points.py \\
      --run-request input/run_request.json \\
      --points output/collected_points.json \\
      --output-dir output
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


MARK_POINTS_SCHEMA_VERSION = "visual_mark_points_v1"
COLLECTED_SCHEMA_VERSION = "collected_points_v1"
MARK_SOURCE = "visual_agent_stub"

MARK_CSV_FIELDS = (
    "mark_id",
    "timestamp",
    "market_id",
    "side",
    "action",
    "price",
    "kind",
    "stake",
    "quantity",
    "reason",
    "source",
)


def main(argv: list[str] | None = None) -> int:
    """Write visual mark_points artifacts from collected points."""
    parser = argparse.ArgumentParser(
        description="Write visual mark_points.json/csv from collected points.",
    )
    parser.add_argument("--run-request", required=True)
    parser.add_argument("--points", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    workspace_root = Path.cwd()
    run_request_path = Path(args.run_request)
    points_path = Path(args.points)
    output_dir = Path(args.output_dir)
    if not run_request_path.is_absolute():
        run_request_path = workspace_root / run_request_path
    if not points_path.is_absolute():
        points_path = workspace_root / points_path
    if not output_dir.is_absolute():
        output_dir = workspace_root / output_dir

    try:
        run_request = load_json_object(run_request_path)
        collected = load_json_object(points_path)
        validate_collected(collected)
        html_files = list(run_request.get("html_files", []))
        if not html_files:
            raise ValueError("run_request.html_files must be a non-empty list")
        html_digests = {
            relative: file_sha256(workspace_root / relative) for relative in html_files
        }
        marks = marks_from_collected(collected.get("points", []))
        payload = {
            "schema_version": MARK_POINTS_SCHEMA_VERSION,
            "run_id": str(run_request["run_id"]),
            "workspace_id": str(run_request["workspace_id"]),
            "source": MARK_SOURCE,
            "html_digests": html_digests,
            "mark_count": len(marks),
            "marks": marks,
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        write_json(output_dir / "mark_points.json", payload)
        write_mark_points_csv(output_dir / "mark_points.csv", marks)
    except Exception as exc:  # noqa: BLE001 - CLI must return non-zero on failure
        print(f"write_mark_points failed: {exc}", file=sys.stderr)
        return 1
    return 0


def validate_collected(collected: dict[str, Any]) -> None:
    """Validate the collected_points payload shape used by the stub agent."""
    if collected.get("schema_version") != COLLECTED_SCHEMA_VERSION:
        raise ValueError(
            f"collected_points schema_version must be {COLLECTED_SCHEMA_VERSION}"
        )
    points = collected.get("points")
    if not isinstance(points, list):
        raise ValueError("collected_points.points must be an array")
    for index, point in enumerate(points):
        if not isinstance(point, dict):
            raise ValueError(f"points[{index}] must be an object")
        for key in ("timestamp", "market_id", "side", "action", "price", "kind"):
            if key not in point:
                raise ValueError(f"points[{index}] missing required field: {key}")


def marks_from_collected(points: list[Any]) -> list[dict[str, Any]]:
    """Normalize collected points into visual mark_points rows."""
    marks: list[dict[str, Any]] = []
    for index, point in enumerate(points):
        if not isinstance(point, dict):
            continue
        marks.append(
            {
                "mark_id": f"visual-{index:05d}",
                "timestamp": str(point["timestamp"]),
                "market_id": str(point["market_id"]),
                "side": str(point["side"]),
                "action": str(point["action"]),
                "price": float(point["price"]),
                "kind": str(point.get("kind", "signal")),
                "stake": float(point.get("stake", 0.0) or 0.0),
                "quantity": float(point.get("quantity", 0.0) or 0.0),
                "reason": str(point.get("reason", "")),
                "source": MARK_SOURCE,
            }
        )
    return marks


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write deterministic pretty JSON."""
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_mark_points_csv(path: Path, marks: list[dict[str, Any]]) -> None:
    """Write a flat CSV mirror of mark points."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(MARK_CSV_FIELDS))
        writer.writeheader()
        for mark in marks:
            writer.writerow({field: mark.get(field, "") for field in MARK_CSV_FIELDS})


def file_sha256(path: Path) -> str:
    """Return the sha256 hex digest for one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
