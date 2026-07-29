"""CLI and runner for the isolated stub visual-marks workspace."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from orchestrator.schema_validation import validate_json_file
from orchestrator.visual_marks_workspace import (
    AGENT_ENTRY_REL,
    ALLOWED_OUTPUT_PATHS,
    INPUT_RUN_REQUEST,
    assert_workspace_mutations_allowed,
    create_visual_marks_workspace,
    file_sha256,
    load_workspace_manifest,
    verify_input_digests,
    write_json,
)
from orchestrator.workspace_manager import workspace_snapshot


RUN_RECEIPT_SCHEMA_VERSION = "visual_marks_run_receipt_v1"

COLLECTED_POINTS_JSON = "output/collected_points.json"
MARK_POINTS_JSON = "output/mark_points.json"
MARK_POINTS_CSV = "output/mark_points.csv"
AGENT_TRACE_JSON = "output/agent_trace.json"
RUN_RECEIPT_JSON = "output/run_receipt.json"


def main(argv: list[str] | None = None) -> int:
    """Create and run an isolated stub visual-marks workspace."""
    parser = argparse.ArgumentParser(
        description=(
            "Create a visual_marks workspace from n HTML pages, run the stub "
            "visual agent, and write empty mark_points when vision finds nothing."
        ),
    )
    parser.add_argument("--run-id", default="visual-marks-demo")
    parser.add_argument("--workspace-id", default="visual-stub")
    parser.add_argument(
        "--html",
        action="append",
        default=[],
        help="HTML page path (repeatable). At least one required.",
    )
    parser.add_argument(
        "--workspace-root",
        default="workspaces",
        help="Root directory for isolated workspaces.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    html_args = list(args.html)
    if not html_args:
        html_args = default_demo_html_paths(repo_root)

    html_sources = []
    for item in html_args:
        path = Path(item)
        if not path.is_absolute():
            path = (repo_root / path).resolve()
        html_sources.append(path)

    workspace_root = Path(args.workspace_root)
    if not workspace_root.is_absolute():
        workspace_root = repo_root / workspace_root

    result = run_visual_marks(
        repo_root=repo_root,
        workspace_root=workspace_root,
        run_id=args.run_id,
        workspace_id=args.workspace_id,
        html_sources=html_sources,
    )
    print(json.dumps(result["receipt"], indent=2, sort_keys=True))
    return 0 if result["receipt"]["status"] == "accepted" else 1


def default_demo_html_paths(repo_root: Path) -> list[str]:
    """Return demo HTML paths, creating a tiny second page if needed."""
    primary = (
        repo_root
        / "workspaces/fake-marks-review/strategy_marks/fake-demo/output/marks_view.html"
    )
    secondary = repo_root / "demos/visual_stub_page_b.html"
    if not secondary.exists():
        secondary.parent.mkdir(parents=True, exist_ok=True)
        secondary.write_text(
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Visual Stub Page B</title></head>"
            "<body><h1>Visual Stub Fixture B</h1>"
            "<p>Placeholder HTML for n-page visual_marks packing.</p>"
            "</body></html>\n",
            encoding="utf-8",
        )
    paths = []
    if primary.exists():
        paths.append(str(primary.relative_to(repo_root)))
    else:
        # Fall back to a generated primary page when fake demo is absent.
        primary_fallback = repo_root / "demos/visual_stub_page_a.html"
        if not primary_fallback.exists():
            primary_fallback.parent.mkdir(parents=True, exist_ok=True)
            primary_fallback.write_text(
                "<!doctype html><html><head><meta charset='utf-8'>"
                "<title>Visual Stub Page A</title></head>"
                "<body><h1>Visual Stub Fixture A</h1></body></html>\n",
                encoding="utf-8",
            )
        paths.append(str(primary_fallback.relative_to(repo_root)))
    paths.append(str(secondary.relative_to(repo_root)))
    return paths


def run_visual_marks(
    *,
    repo_root: Path,
    workspace_root: Path,
    run_id: str,
    workspace_id: str,
    html_sources: list[Path],
) -> dict[str, Any]:
    """Create a workspace, run the stub agent, and write a receipt."""
    workspace_path = create_visual_marks_workspace(
        repo_root=repo_root,
        workspace_root=workspace_root,
        run_id=run_id,
        workspace_id=workspace_id,
        html_sources=html_sources,
    )
    before_snapshot = workspace_snapshot(workspace_path)
    manifest = load_workspace_manifest(workspace_path)
    run_request = json.loads(
        (workspace_path / INPUT_RUN_REQUEST).read_text(encoding="utf-8")
    )
    html_files = list(run_request.get("html_files", []))
    input_ok, input_errors = verify_input_digests(
        workspace_path=workspace_path,
        expected=manifest["input_digests"],
        html_files=html_files,
    )

    agent_exit = 1
    failure_reason = ""
    html_accepted = False
    script_exit_code = 1
    mark_count = 0

    try:
        if not input_ok:
            raise RuntimeError("; ".join(input_errors))
        request_errors = validate_json_file(
            payload_path=workspace_path / INPUT_RUN_REQUEST,
            schema_path=repo_root / "schemas/visual_marks_run_request.schema.json",
        )
        if request_errors:
            raise RuntimeError("; ".join(request_errors))
        manifest_errors = validate_json_file(
            payload_path=workspace_path / "workspace_manifest.json",
            schema_path=repo_root
            / "schemas/visual_marks_workspace_manifest.schema.json",
        )
        if manifest_errors:
            raise RuntimeError("; ".join(manifest_errors))

        completed = subprocess.run(
            [sys.executable, AGENT_ENTRY_REL],
            cwd=workspace_path,
            check=False,
            capture_output=True,
            text=True,
        )
        agent_exit = int(completed.returncode)
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)

        trace = optional_json(workspace_path / AGENT_TRACE_JSON)
        html_accepted = bool(trace.get("html_accepted", False))
        script_exit_code = int(trace.get("script_exit_code", agent_exit))
        mark_payload = optional_json(workspace_path / MARK_POINTS_JSON)
        mark_count = int(mark_payload.get("mark_count", 0))

        if agent_exit != 0:
            raise RuntimeError(
                f"stub visual agent failed with exit {agent_exit}: "
                f"{trace.get('notes', '')}"
            )

        for relative, schema_name in (
            (COLLECTED_POINTS_JSON, "collected_points.schema.json"),
            (MARK_POINTS_JSON, "visual_mark_points.schema.json"),
            (AGENT_TRACE_JSON, "visual_agent_trace.schema.json"),
        ):
            errors = validate_json_file(
                payload_path=workspace_path / relative,
                schema_path=repo_root / "schemas" / schema_name,
            )
            if errors:
                raise RuntimeError("; ".join(errors))
    except Exception as exc:  # noqa: BLE001 - receipt must capture runner failures
        failure_reason = str(exc)

    mutation_errors = assert_workspace_mutations_allowed(
        workspace_path=workspace_path,
        before_snapshot=before_snapshot,
    )
    # Receipt is written by the orchestrator after the agent finishes; allow it.
    status = "accepted"
    if (
        failure_reason
        or mutation_errors
        or not input_ok
        or not html_accepted
        or script_exit_code != 0
        or agent_exit != 0
    ):
        status = "rejected"
        if not failure_reason and mutation_errors:
            failure_reason = "; ".join(mutation_errors)
        elif not failure_reason and not input_ok:
            failure_reason = "; ".join(input_errors)

    # Stub success contract: accepted path must be zero-signal.
    if status == "accepted" and mark_count != 0:
        status = "rejected"
        failure_reason = (
            f"visual stub expected mark_count=0, got {mark_count}"
        )

    receipt = build_run_receipt(
        run_id=run_id,
        workspace_id=workspace_id,
        workspace_path=workspace_path,
        status=status,
        html_accepted=html_accepted,
        script_exit_code=script_exit_code,
        input_digest_ok=input_ok,
        mutation_errors=mutation_errors,
        mark_count=mark_count,
        failure_reason=failure_reason,
    )
    write_json(workspace_path / RUN_RECEIPT_JSON, receipt)
    receipt_errors = validate_json_file(
        payload_path=workspace_path / RUN_RECEIPT_JSON,
        schema_path=repo_root / "schemas/visual_marks_run_receipt.schema.json",
    )
    if receipt_errors:
        receipt["status"] = "rejected"
        receipt["failure_reason"] = "; ".join(receipt_errors)
        write_json(workspace_path / RUN_RECEIPT_JSON, receipt)

    return {
        "workspace_path": workspace_path,
        "receipt": receipt,
        "allowed_output_paths": list(ALLOWED_OUTPUT_PATHS),
    }


def build_run_receipt(
    *,
    run_id: str,
    workspace_id: str,
    workspace_path: Path,
    status: str,
    html_accepted: bool,
    script_exit_code: int,
    input_digest_ok: bool,
    mutation_errors: tuple[str, ...],
    mark_count: int,
    failure_reason: str,
) -> dict[str, Any]:
    """Build the visual marks run receipt."""
    receipt: dict[str, Any] = {
        "schema_version": RUN_RECEIPT_SCHEMA_VERSION,
        "run_id": run_id,
        "workspace_id": workspace_id,
        "status": status,
        "workspace_path": str(workspace_path.resolve()),
        "html_accepted": html_accepted,
        "script_exit_code": script_exit_code,
        "input_digest_ok": input_digest_ok,
        "mutation_errors": list(mutation_errors),
        "artifact_sha256": {
            "mark_points_json": optional_file_sha256(workspace_path / MARK_POINTS_JSON),
            "mark_points_csv": optional_file_sha256(workspace_path / MARK_POINTS_CSV),
            "collected_points_json": optional_file_sha256(
                workspace_path / COLLECTED_POINTS_JSON
            ),
            "agent_trace_json": optional_file_sha256(workspace_path / AGENT_TRACE_JSON),
        },
        "mark_count": mark_count,
    }
    if failure_reason:
        receipt["failure_reason"] = failure_reason
    return receipt


def optional_file_sha256(path: Path) -> str:
    """Return a file digest or empty string when missing."""
    if not path.exists():
        return ""
    return file_sha256(path)


def optional_json(path: Path) -> dict[str, Any]:
    """Load a JSON object or return an empty dict."""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    return {}


if __name__ == "__main__":
    raise SystemExit(main())
