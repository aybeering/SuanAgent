"""Tests for unauthenticated local CLI connectivity checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from orchestrator.cli_connectivity import probe_cli, run_connectivity_test
from orchestrator.schema_validation import validate_json_file


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repository_cli_integration_config_is_schema_valid() -> None:
    assert validate_json_file(
        payload_path=REPO_ROOT / "config/cli_integrations.json",
        schema_path=REPO_ROOT / "schemas/cli_integrations.schema.json",
    ) == ()


def test_repository_registers_github_cli() -> None:
    payload = json.loads(
        (REPO_ROOT / "config/cli_integrations.json").read_text(encoding="utf-8")
    )

    assert payload["integrations"]["github_cli"] == {
        "executable": "gh",
        "purpose": "管理 GitHub 仓库、分支、Issue、Pull Request 和协作流程",
    }


def test_probe_checks_only_local_version_and_help(tmp_path: Path) -> None:
    config_path = tmp_path / "repo/config/cli_integrations.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "cli_integrations_v1",
                "connectivity_test": {
                    "timeout_seconds": 5,
                    "authentication_probe": "not_run",
                    "network_probe": "not_run",
                },
                "integrations": {
                    "codex_cli": {
                        "executable": sys.executable,
                        "purpose": "test codex",
                    },
                    "lark_cli": {
                        "executable": sys.executable,
                        "purpose": "test lark",
                    },
                    "github_cli": {
                        "executable": sys.executable,
                        "purpose": "test github",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "repo/schemas").mkdir()
    (tmp_path / "repo/schemas/cli_integrations.schema.json").write_text(
        (REPO_ROOT / "schemas/cli_integrations.schema.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    report = run_connectivity_test(config_path=config_path)

    assert report["scope"]["authentication_probe"] is False
    assert report["scope"]["network_probe"] is False
    assert report["summary"]["available_local_count"] == 3
    for item in report["results"]:
        assert item["status"] == "available_local_only"
        assert item["authentication"] == {"attempted": False, "status": "not_run"}
        assert item["network"] == {"attempted": False, "status": "not_run"}
        assert set(item["probes"]) == {"version", "help"}


def test_missing_executable_does_not_attempt_auth_or_network() -> None:
    result = probe_cli(
        integration="lark_cli",
        executable="definitely-not-installed-suanagent-cli",
        purpose="test",
        timeout_seconds=1,
    )

    assert result["status"] == "missing"
    assert result["authentication"]["attempted"] is False
    assert result["network"]["attempted"] is False
