"""Tests for the private Codex agent registry and handoff boundary."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from orchestrator.codex_agent_runtime import (
    CodexAgentRegistryError,
    build_codex_command,
    create_handoff,
    load_registry,
    provision_agents,
)
from orchestrator.schema_validation import validate_json_file


REPO_ROOT = Path(__file__).resolve().parents[1]


def _test_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    config_dir = repo_root / "config"
    schema_dir = repo_root / "schemas"
    (repo_root / "strategies").mkdir(parents=True)
    (repo_root / "backtester").mkdir()
    (repo_root / "data").mkdir()
    (repo_root / "docs").mkdir()
    (repo_root / "strategies/current_strategy.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo_root / "backtester/simulate.py").write_text("# test\n", encoding="utf-8")
    (repo_root / "data/input.csv").write_text("x\n", encoding="utf-8")
    (repo_root / "docs/strategy_interface.md").write_text("# interface\n", encoding="utf-8")
    config_dir.mkdir()
    schema_dir.mkdir()
    shutil.copy2(REPO_ROOT / "schemas/codex_agent_registry.schema.json", schema_dir)
    shutil.copy2(REPO_ROOT / "schemas/codex_agent_handoff.schema.json", schema_dir)
    registry_path = config_dir / "codex_agents.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": "codex_agent_registry_v1",
                "runtime_root": "experiments/codex_agents",
                "workspace_root": "workspaces/codex_agents",
                "defaults": {
                    "codex_executable": "codex",
                    "model": "default",
                    "sandbox": "workspace-write",
                    "persist_memory": False,
                    "network_access": False,
                    "timeout_seconds": 10,
                },
                "agents": [
                    {
                        "id": "a",
                        "description": "analysis",
                        "workspace_sources": ["strategies", "backtester"],
                        "write_paths": ["output"],
                        "handoff_export_paths": ["output"],
                        "skills": [],
                        "tools": ["shell"],
                        "handoff_to": ["b"],
                        "can_receive_from": [],
                        "instructions": "write analysis",
                    },
                    {
                        "id": "b",
                        "description": "strategy",
                        "workspace_sources": ["strategies", "data"],
                        "write_paths": ["strategies/current_strategy.py", "output"],
                        "handoff_export_paths": ["output"],
                        "skills": [],
                        "tools": ["shell"],
                        "handoff_to": [],
                        "can_receive_from": ["a"],
                        "instructions": "write strategy",
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return repo_root, registry_path


def test_registry_is_schema_valid_and_provisions_private_state(tmp_path: Path) -> None:
    repo_root, registry_path = _test_repo(tmp_path)

    payload = load_registry(registry_path)
    assert [agent["id"] for agent in payload["agents"]] == ["a", "b"]
    runtimes = provision_agents(
        repo_root=repo_root,
        registry_path=registry_path,
        run_id="run-1",
    )

    first, second = runtimes
    assert (first.workspace / "strategies/current_strategy.py").exists()
    assert (second.workspace / "strategies/current_strategy.py").exists()
    assert not (first.workspace / "data").exists()
    assert not (first.workspace / "../b").resolve().is_relative_to(first.workspace.resolve())
    assert first.codex_home != second.codex_home
    assert "multi_agent = false" in (first.codex_home / "config.toml").read_text(encoding="utf-8")
    assert validate_json_file(
        payload_path=registry_path,
        schema_path=REPO_ROOT / "schemas/codex_agent_registry.schema.json",
    ) == ()


def test_handoff_is_copied_only_into_declared_recipient_inbox(tmp_path: Path) -> None:
    repo_root, registry_path = _test_repo(tmp_path)
    provision_agents(repo_root=repo_root, registry_path=registry_path, run_id="run-2")
    sender_output = repo_root / "workspaces/codex_agents/run-2/a/output/result.json"
    sender_output.parent.mkdir(exist_ok=True)
    sender_output.write_text('{"finding":"useful"}\n', encoding="utf-8")

    handoff_path = create_handoff(
        repo_root=repo_root,
        registry_path=registry_path,
        run_id="run-2",
        from_agent="a",
        to_agent="b",
        task="Review the finding",
        message="Use this result when evaluating the strategy.",
        artifact_paths=("output/result.json",),
        handoff_id="handoff-1",
    )

    assert handoff_path == repo_root / "experiments/codex_agents/run-2/agents/b/inbox/handoff-1/handoff.json"
    assert (handoff_path.parent / "artifacts/output/result.json").exists()
    assert not (repo_root / "workspaces/codex_agents/run-2/a/inbox/handoff-1").exists()
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert handoff["from_agent"] == "a"
    assert handoff["to_agent"] == "b"
    assert handoff["artifacts"][0]["path"] == "output/result.json"
    assert validate_json_file(
        payload_path=handoff_path,
        schema_path=REPO_ROOT / "schemas/codex_agent_handoff.schema.json",
    ) == ()


def test_handoff_rejects_an_undeclared_edge_or_artifact(tmp_path: Path) -> None:
    repo_root, registry_path = _test_repo(tmp_path)
    provision_agents(repo_root=repo_root, registry_path=registry_path, run_id="run-3")
    with pytest.raises(CodexAgentRegistryError, match="handoff edge"):
        create_handoff(
            repo_root=repo_root,
            registry_path=registry_path,
            run_id="run-3",
            from_agent="b",
            to_agent="a",
            task="No",
            message="This route is not registered.",
        )


def test_command_uses_private_workspace_and_ephemeral_cli_state(tmp_path: Path) -> None:
    repo_root, registry_path = _test_repo(tmp_path)
    runtime = provision_agents(
        repo_root=repo_root,
        registry_path=registry_path,
        run_id="run-4",
        agent_ids=("b",),
    )[0]
    payload = load_registry(registry_path)
    definition = next(item for item in payload["agents"] if item["id"] == "b")
    from orchestrator.codex_agent_runtime import agent_definitions

    command = build_codex_command(
        registry_payload=payload,
        definition=agent_definitions(payload)["b"],
        workspace=runtime.workspace,
        prompt="Inspect the handoff and propose a strategy change.",
    )
    assert command[:2] == ["codex", "exec"]
    assert "--cd" in command
    assert str(runtime.workspace.resolve()) in command
    assert "--ephemeral" in command
    assert "--skip-git-repo-check" in command
