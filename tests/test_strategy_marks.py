"""Tests for the isolated dead-strategy marks workspace."""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.schema_validation import validate_json_file
from orchestrator.strategy_marks_run import main, run_strategy_marks
from orchestrator.strategy_marks_workspace import (
    ALLOWED_OUTPUT_PATHS,
    INPUT_MARKET_CSV,
    assert_workspace_mutations_allowed,
    create_strategy_marks_workspace,
    load_workspace_manifest,
    verify_input_digests,
)
from orchestrator.workspace_manager import workspace_snapshot


REPO_ROOT = Path(__file__).resolve().parents[1]
MARKET_CSV = REPO_ROOT / "data/validation/sample_markets.csv"


def test_create_strategy_marks_workspace_is_narrow(tmp_path: Path) -> None:
    workspace = create_strategy_marks_workspace(
        repo_root=REPO_ROOT,
        workspace_root=tmp_path / "workspaces",
        run_id="marks-narrow",
        workspace_id="validation-dead",
        split="validation",
        market_csv_source=MARKET_CSV,
    )

    assert (workspace / "strategies/current_strategy.py").exists()
    assert (workspace / "backtester/simulate.py").exists()
    assert (workspace / INPUT_MARKET_CSV).exists()
    assert (workspace / "input/run_request.json").exists()
    assert not (workspace / "orchestrator").exists()
    assert not (workspace / "agents").exists()
    assert not (workspace / "docs").exists()

    manifest = load_workspace_manifest(workspace)
    assert manifest["workspace_kind"] == "strategy_marks_v1"
    assert set(manifest["mutation_policy"]["allowed_paths"]) == set(ALLOWED_OUTPUT_PATHS)
    assert validate_json_file(
        payload_path=workspace / "workspace_manifest.json",
        schema_path=REPO_ROOT / "schemas/strategy_marks_workspace_manifest.schema.json",
    ) == ()
    assert validate_json_file(
        payload_path=workspace / "input/run_request.json",
        schema_path=REPO_ROOT / "schemas/strategy_marks_run_request.schema.json",
    ) == ()


def test_input_digest_detects_tampering(tmp_path: Path) -> None:
    workspace = create_strategy_marks_workspace(
        repo_root=REPO_ROOT,
        workspace_root=tmp_path / "workspaces",
        run_id="marks-tamper",
        workspace_id="validation-dead",
        split="validation",
        market_csv_source=MARKET_CSV,
    )
    manifest = load_workspace_manifest(workspace)
    ok, errors = verify_input_digests(
        workspace_path=workspace,
        expected=manifest["input_digests"],
    )
    assert ok
    assert errors == ()

    market_path = workspace / INPUT_MARKET_CSV
    market_path.write_text(market_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    ok, errors = verify_input_digests(
        workspace_path=workspace,
        expected=manifest["input_digests"],
    )
    assert not ok
    assert errors == ("input digest mismatch: market_csv",)


def test_disallowed_mutation_is_detected(tmp_path: Path) -> None:
    workspace = create_strategy_marks_workspace(
        repo_root=REPO_ROOT,
        workspace_root=tmp_path / "workspaces",
        run_id="marks-mutation",
        workspace_id="validation-dead",
        split="validation",
        market_csv_source=MARKET_CSV,
    )
    before = workspace_snapshot(workspace)
    (workspace / "strategies/current_strategy.py").write_text(
        "# tampered\n",
        encoding="utf-8",
    )
    errors = assert_workspace_mutations_allowed(
        workspace_path=workspace,
        before_snapshot=before,
    )
    assert errors
    assert any("strategies/current_strategy.py" in item for item in errors)


def test_run_strategy_marks_writes_contracts_and_html(tmp_path: Path) -> None:
    result = run_strategy_marks(
        repo_root=REPO_ROOT,
        workspace_root=tmp_path / "workspaces",
        run_id="marks-run",
        workspace_id="validation-dead",
        split="validation",
        market_csv_source=MARKET_CSV,
    )
    receipt = result["receipt"]
    workspace = Path(result["workspace_path"])

    assert receipt["status"] == "accepted"
    assert receipt["input_digest_ok"] is True
    assert receipt["mutation_errors"] == []
    assert receipt["mark_count"] > 0

    mark_points_path = workspace / "output/mark_points.json"
    assert validate_json_file(
        payload_path=mark_points_path,
        schema_path=REPO_ROOT / "schemas/strategy_mark_points.schema.json",
    ) == ()
    assert validate_json_file(
        payload_path=workspace / "output/run_receipt.json",
        schema_path=REPO_ROOT / "schemas/strategy_marks_run_receipt.schema.json",
    ) == ()

    payload = json.loads(mark_points_path.read_text(encoding="utf-8"))
    kinds = {mark["kind"] for mark in payload["marks"]}
    assert "signal" in kinds
    assert "fill" in kinds

    html = (workspace / "output/marks_view.html").read_text(encoding="utf-8")
    assert "marks_view_v1" in html
    assert "Strategy Marks View" in html
    assert "yes_price" in html
    assert payload["marks"][0]["mark_id"] in html


def test_run_strategy_marks_is_deterministic(tmp_path: Path) -> None:
    first = run_strategy_marks(
        repo_root=REPO_ROOT,
        workspace_root=tmp_path / "workspaces-a",
        run_id="marks-det",
        workspace_id="validation-dead",
        split="validation",
        market_csv_source=MARKET_CSV,
    )
    second = run_strategy_marks(
        repo_root=REPO_ROOT,
        workspace_root=tmp_path / "workspaces-b",
        run_id="marks-det",
        workspace_id="validation-dead",
        split="validation",
        market_csv_source=MARKET_CSV,
    )
    first_marks = json.loads(
        (Path(first["workspace_path"]) / "output/mark_points.json").read_text(
            encoding="utf-8"
        )
    )
    second_marks = json.loads(
        (Path(second["workspace_path"]) / "output/mark_points.json").read_text(
            encoding="utf-8"
        )
    )
    assert first_marks["marks"] == second_marks["marks"]
    assert first_marks["input_digest"] == second_marks["input_digest"]
    assert first_marks["strategy_sha256"] == second_marks["strategy_sha256"]
    assert first["receipt"]["artifact_sha256"]["mark_points_json"] == second[
        "receipt"
    ]["artifact_sha256"]["mark_points_json"]


def test_cli_main_accepts_validation_split(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(REPO_ROOT)
    code = main(
        [
            "--run-id",
            "marks-cli",
            "--workspace-id",
            "cli-dead",
            "--split",
            "validation",
            "--workspace-root",
            str(tmp_path / "workspaces"),
        ]
    )
    assert code == 0
    workspace = (
        tmp_path / "workspaces" / "marks-cli" / "strategy_marks" / "cli-dead"
    )
    assert (workspace / "output/marks_view.html").exists()
