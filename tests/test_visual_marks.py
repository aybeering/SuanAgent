"""Tests for the isolated stub visual-marks workspace."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from orchestrator.schema_validation import validate_json_file
from orchestrator.visual_marks_run import main, run_visual_marks
from orchestrator.visual_marks_workspace import (
    ALLOWED_OUTPUT_PATHS,
    INPUT_PAGES_DIR,
    assert_workspace_mutations_allowed,
    create_visual_marks_workspace,
    load_workspace_manifest,
    verify_input_digests,
)
from orchestrator.workspace_manager import workspace_snapshot


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_html(path: Path, title: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{title}</title></head><body><h1>{title}</h1></body></html>\n"
        ),
        encoding="utf-8",
    )
    return path


def test_create_visual_marks_workspace_packs_html_and_tools(tmp_path: Path) -> None:
    html_a = _write_html(tmp_path / "a.html", "A")
    html_b = _write_html(tmp_path / "b.html", "B")
    workspace = create_visual_marks_workspace(
        repo_root=REPO_ROOT,
        workspace_root=tmp_path / "workspaces",
        run_id="visual-narrow",
        workspace_id="stub",
        html_sources=[html_a, html_b],
    )

    assert (workspace / "tools/write_mark_points.py").exists()
    assert (workspace / "agent/stub_visual_agent.py").exists()
    assert (workspace / f"{INPUT_PAGES_DIR}/page_001.html").exists()
    assert (workspace / f"{INPUT_PAGES_DIR}/page_002.html").exists()
    assert not (workspace / "strategies").exists()
    assert not (workspace / "orchestrator").exists()

    manifest = load_workspace_manifest(workspace)
    assert manifest["workspace_kind"] == "visual_marks_v1"
    assert set(manifest["mutation_policy"]["allowed_paths"]) == set(ALLOWED_OUTPUT_PATHS)
    assert validate_json_file(
        payload_path=workspace / "workspace_manifest.json",
        schema_path=REPO_ROOT / "schemas/visual_marks_workspace_manifest.schema.json",
    ) == ()
    assert validate_json_file(
        payload_path=workspace / "input/run_request.json",
        schema_path=REPO_ROOT / "schemas/visual_marks_run_request.schema.json",
    ) == ()


def test_input_and_tools_mutations_are_rejected(tmp_path: Path) -> None:
    html_a = _write_html(tmp_path / "a.html", "A")
    workspace = create_visual_marks_workspace(
        repo_root=REPO_ROOT,
        workspace_root=tmp_path / "workspaces",
        run_id="visual-mut",
        workspace_id="stub",
        html_sources=[html_a],
    )
    before = workspace_snapshot(workspace)
    page = workspace / f"{INPUT_PAGES_DIR}/page_001.html"
    page.write_text(page.read_text(encoding="utf-8") + "<!-- tamper -->\n", encoding="utf-8")
    (workspace / "tools/write_mark_points.py").write_text("# tamper\n", encoding="utf-8")
    errors = assert_workspace_mutations_allowed(
        workspace_path=workspace,
        before_snapshot=before,
    )
    assert any("input/pages/page_001.html" in item for item in errors)
    assert any("tools/write_mark_points.py" in item for item in errors)

    manifest = load_workspace_manifest(workspace)
    run_request = json.loads(
        (workspace / "input/run_request.json").read_text(encoding="utf-8")
    )
    ok, digest_errors = verify_input_digests(
        workspace_path=workspace,
        expected=manifest["input_digests"],
        html_files=list(run_request["html_files"]),
    )
    assert not ok
    assert digest_errors


def test_marking_script_accepts_empty_points(tmp_path: Path) -> None:
    html_a = _write_html(tmp_path / "a.html", "A")
    workspace = create_visual_marks_workspace(
        repo_root=REPO_ROOT,
        workspace_root=tmp_path / "workspaces",
        run_id="visual-script",
        workspace_id="stub",
        html_sources=[html_a],
    )
    points_path = workspace / "output/collected_points.json"
    points_path.write_text(
        json.dumps({"schema_version": "collected_points_v1", "points": []}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "tools/write_mark_points.py",
            "--run-request",
            "input/run_request.json",
            "--points",
            "output/collected_points.json",
            "--output-dir",
            "output",
        ],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads((workspace / "output/mark_points.json").read_text(encoding="utf-8"))
    assert payload["mark_count"] == 0
    assert payload["marks"] == []
    assert payload["source"] == "visual_agent_stub"
    assert validate_json_file(
        payload_path=workspace / "output/mark_points.json",
        schema_path=REPO_ROOT / "schemas/visual_mark_points.schema.json",
    ) == ()


def test_run_visual_marks_stub_zero_signal_end_to_end(tmp_path: Path) -> None:
    html_a = _write_html(tmp_path / "a.html", "Page A")
    html_b = _write_html(tmp_path / "b.html", "Page B")
    result = run_visual_marks(
        repo_root=REPO_ROOT,
        workspace_root=tmp_path / "workspaces",
        run_id="visual-e2e",
        workspace_id="stub",
        html_sources=[html_a, html_b],
    )
    receipt = result["receipt"]
    workspace = Path(result["workspace_path"])

    assert receipt["status"] == "accepted"
    assert receipt["html_accepted"] is True
    assert receipt["script_exit_code"] == 0
    assert receipt["mark_count"] == 0
    assert receipt["mutation_errors"] == []

    marks = json.loads((workspace / "output/mark_points.json").read_text(encoding="utf-8"))
    assert marks["marks"] == []
    trace = json.loads((workspace / "output/agent_trace.json").read_text(encoding="utf-8"))
    assert trace["html_accepted"] is True
    assert trace["html_count"] == 2
    assert trace["vision_mode"] == "stub_empty"
    assert trace["signal_count"] == 0
    assert validate_json_file(
        payload_path=workspace / "output/agent_trace.json",
        schema_path=REPO_ROOT / "schemas/visual_agent_trace.schema.json",
    ) == ()
    assert validate_json_file(
        payload_path=workspace / "output/run_receipt.json",
        schema_path=REPO_ROOT / "schemas/visual_marks_run_receipt.schema.json",
    ) == ()


def test_missing_html_source_fails_workspace_create(tmp_path: Path) -> None:
    missing = tmp_path / "missing.html"
    try:
        create_visual_marks_workspace(
            repo_root=REPO_ROOT,
            workspace_root=tmp_path / "workspaces",
            run_id="visual-missing",
            workspace_id="stub",
            html_sources=[missing],
        )
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass


def test_cli_main_accepts_html_flags(tmp_path: Path, monkeypatch) -> None:
    html_a = _write_html(tmp_path / "cli_a.html", "CLI A")
    html_b = _write_html(tmp_path / "cli_b.html", "CLI B")
    monkeypatch.chdir(REPO_ROOT)
    code = main(
        [
            "--run-id",
            "visual-cli",
            "--workspace-id",
            "cli-stub",
            "--html",
            str(html_a),
            "--html",
            str(html_b),
            "--workspace-root",
            str(tmp_path / "workspaces"),
        ]
    )
    assert code == 0
    workspace = tmp_path / "workspaces" / "visual-cli" / "visual_marks" / "cli-stub"
    receipt = json.loads((workspace / "output/run_receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "accepted"
    assert receipt["mark_count"] == 0
