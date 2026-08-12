"""Provision and run isolated Codex CLI agent workspaces.

This module is deliberately separate from the V0.5 iteration loop.  The
registry is the authority for which files an agent receives, where its private
Codex state is stored, which local capabilities it may use, and which agents
may exchange handoffs.  A handoff is copied into the recipient's inbox by the
orchestrator; agents never read another agent's workspace directly.

The runtime provides a strong repository-level boundary: private CODEX_HOME,
an allowlisted workspace, no inherited MCP configuration, and a post-run
mutation check.  Absolute OS-level read isolation still requires a container
or a separate operating-system account; this module does not claim to create
that boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from orchestrator.schema_validation import validate_json_file, validate_json_payload
from orchestrator.workspace_manager import workspace_snapshot


REGISTRY_SCHEMA_VERSION = "codex_agent_registry_v1"
HANDOFF_SCHEMA_VERSION = "codex_agent_handoff_v1"
REGISTRY_SCHEMA_FILENAME = "codex_agent_registry.schema.json"
HANDOFF_SCHEMA_FILENAME = "codex_agent_handoff.schema.json"


class CodexAgentRegistryError(ValueError):
    """Raised when a registry or its filesystem boundaries are invalid."""


@dataclass(frozen=True)
class AgentDefinition:
    """Concrete permissions and routing rules for one Codex agent."""

    agent_id: str
    description: str
    workspace_sources: tuple[str, ...]
    write_paths: tuple[str, ...]
    handoff_export_paths: tuple[str, ...]
    skills: tuple[str, ...]
    tools: tuple[str, ...]
    handoff_to: tuple[str, ...]
    can_receive_from: tuple[str, ...]
    instructions: str
    sandbox: str
    model: str
    persist_memory: bool
    network_access: bool


@dataclass(frozen=True)
class AgentRuntime:
    """Filesystem locations created for one registered agent."""

    run_id: str
    definition: AgentDefinition
    workspace: Path
    codex_home: Path
    inbox: Path
    manifest: Path


def load_registry(registry_path: Path) -> dict[str, Any]:
    """Load and semantically validate a Codex agent registry."""
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    schema_path = registry_path.parent.parent / "schemas" / REGISTRY_SCHEMA_FILENAME
    errors = validate_json_payload(
        payload=payload,
        schema=json.loads(schema_path.read_text(encoding="utf-8")),
        schema_dir=schema_path.parent,
    )
    if errors:
        raise CodexAgentRegistryError("registry schema errors: " + "; ".join(errors))
    validate_registry_semantics(payload)
    return payload


def validate_registry_file(*, registry_path: Path, schema_path: Path) -> tuple[str, ...]:
    """Return schema errors for a registry file without applying it."""
    return validate_json_file(payload_path=registry_path, schema_path=schema_path)


def validate_registry_semantics(payload: dict[str, Any]) -> None:
    """Reject duplicate identities, invalid paths, and undeclared handoffs."""
    agents = payload.get("agents", [])
    defaults = payload["defaults"]
    agent_ids = [str(agent["id"]) for agent in agents]
    if len(agent_ids) != len(set(agent_ids)):
        raise CodexAgentRegistryError("agent ids must be unique")
    agent_id_set = set(agent_ids)
    for agent in agents:
        agent_id = str(agent["id"])
        for field in ("workspace_sources", "write_paths", "handoff_export_paths", "skills"):
            for value in agent.get(field, []):
                _validate_relative_path(str(value), f"{agent_id}.{field}")
        for field in ("handoff_to", "can_receive_from"):
            unknown = sorted(set(agent.get(field, [])) - agent_id_set)
            if unknown:
                raise CodexAgentRegistryError(
                    f"{agent_id}.{field} references unknown agents: {', '.join(unknown)}"
                )
        if not set(agent.get("handoff_export_paths", [])).issubset(
            set(agent.get("write_paths", []))
        ):
            raise CodexAgentRegistryError(
                f"{agent_id}.handoff_export_paths must be inside write_paths"
            )
        if not bool(agent.get("network_access", defaults["network_access"])) and str(
            agent.get("sandbox", defaults["sandbox"])
        ) == "danger-full-access":
            raise CodexAgentRegistryError(
                f"{agent_id} cannot disable network access while using danger-full-access"
            )
    for agent in agents:
        sender = str(agent["id"])
        for recipient in agent.get("handoff_to", []):
            recipient_config = next(item for item in agents if item["id"] == recipient)
            if sender not in recipient_config.get("can_receive_from", []):
                raise CodexAgentRegistryError(
                    f"handoff edge {sender}->{recipient} is not declared by the recipient"
                )


def agent_definitions(payload: dict[str, Any]) -> dict[str, AgentDefinition]:
    """Return normalized agent definitions keyed by their registered id."""
    defaults = payload["defaults"]
    return {
        str(raw["id"]): AgentDefinition(
            agent_id=str(raw["id"]),
            description=str(raw["description"]),
            workspace_sources=tuple(raw.get("workspace_sources", [])),
            write_paths=tuple(raw.get("write_paths", [])),
            handoff_export_paths=tuple(raw.get("handoff_export_paths", [])),
            skills=tuple(raw.get("skills", [])),
            tools=tuple(raw.get("tools", [])),
            handoff_to=tuple(raw.get("handoff_to", [])),
            can_receive_from=tuple(raw.get("can_receive_from", [])),
            instructions=str(raw.get("instructions", "")),
            sandbox=str(raw.get("sandbox", defaults["sandbox"])),
            model=str(raw.get("model", defaults["model"])),
            persist_memory=bool(raw.get("persist_memory", defaults["persist_memory"])),
            network_access=bool(raw.get("network_access", defaults["network_access"])),
        )
        for raw in payload["agents"]
    }


def provision_agents(
    *,
    repo_root: Path,
    registry_path: Path,
    run_id: str,
    agent_ids: Iterable[str] | None = None,
) -> tuple[AgentRuntime, ...]:
    """Create private workspaces, homes, inboxes, and manifests for agents."""
    payload = load_registry(registry_path)
    definitions = agent_definitions(payload)
    selected = tuple(agent_ids) if agent_ids is not None else tuple(definitions)
    unknown = sorted(set(selected) - set(definitions))
    if unknown:
        raise CodexAgentRegistryError(f"unknown agent ids: {', '.join(unknown)}")
    workspace_root = _rooted_path(repo_root, payload["workspace_root"])
    runtime_root = _rooted_path(repo_root, payload["runtime_root"])
    runtimes: list[AgentRuntime] = []
    for agent_id in selected:
        definition = definitions[agent_id]
        workspace = workspace_root / run_id / agent_id
        codex_home = runtime_root / run_id / "agents" / agent_id / "codex_home"
        inbox = runtime_root / run_id / "agents" / agent_id / "inbox"
        if workspace.exists() or codex_home.exists() or inbox.exists():
            raise FileExistsError(f"agent runtime already exists: {agent_id} / {run_id}")
        workspace.mkdir(parents=True)
        _copy_allowlisted_sources(repo_root, workspace, definition.workspace_sources)
        _prepare_workspace(workspace, definition)
        codex_home.mkdir(parents=True)
        inbox.mkdir(parents=True)
        _write_codex_home(codex_home, definition, repo_root)
        manifest = runtime_root / run_id / "agents" / agent_id / "agent_manifest.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(
                _manifest_payload(
                    repo_root=repo_root,
                    run_id=run_id,
                    definition=definition,
                    workspace=workspace,
                    codex_home=codex_home,
                    inbox=inbox,
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        runtimes.append(
            AgentRuntime(
                run_id=run_id,
                definition=definition,
                workspace=workspace,
                codex_home=codex_home,
                inbox=inbox,
                manifest=manifest,
            )
        )
    return tuple(runtimes)


def create_handoff(
    *,
    repo_root: Path,
    registry_path: Path,
    run_id: str,
    from_agent: str,
    to_agent: str,
    task: str,
    message: str,
    artifact_paths: Iterable[str] = (),
    handoff_id: str = "",
) -> Path:
    """Deliver a directed handoff into the recipient's private inbox."""
    payload = load_registry(registry_path)
    definitions = agent_definitions(payload)
    if from_agent not in definitions or to_agent not in definitions:
        raise CodexAgentRegistryError("handoff sender and recipient must be registered")
    sender = definitions[from_agent]
    if to_agent not in sender.handoff_to or from_agent not in definitions[to_agent].can_receive_from:
        raise CodexAgentRegistryError(f"handoff edge is not registered: {from_agent}->{to_agent}")
    if not task.strip() or not message.strip():
        raise CodexAgentRegistryError("handoff task and message must not be empty")
    handoff_id = handoff_id or f"handoff_{uuid4().hex[:12]}"
    source_workspace = _rooted_path(repo_root, payload["workspace_root"]) / run_id / from_agent
    recipient_inbox = (
        _rooted_path(repo_root, payload["runtime_root"])
        / run_id
        / "agents"
        / to_agent
        / "inbox"
        / handoff_id
    )
    if not source_workspace.is_dir() or not recipient_inbox.parent.is_dir():
        raise CodexAgentRegistryError("provision both agents before creating a handoff")
    if recipient_inbox.exists():
        raise FileExistsError(f"handoff already exists: {handoff_id}")
    validated_artifacts: list[tuple[str, Path]] = []
    for raw_path in artifact_paths:
        relative = _validate_relative_path(str(raw_path), "handoff artifact")
        if not _is_allowed_path(relative, sender.handoff_export_paths):
            raise CodexAgentRegistryError(
                f"{from_agent} may export only {sender.handoff_export_paths}; got {relative}"
            )
        source = source_workspace / relative
        if not source.is_file() or source.is_symlink():
            raise CodexAgentRegistryError(f"handoff artifact is not a regular file: {relative}")
        validated_artifacts.append((relative, source))
    recipient_inbox.mkdir()
    artifacts: list[dict[str, str]] = []
    for relative, source in validated_artifacts:
        target = recipient_inbox / "artifacts" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        artifacts.append(
            {
                "path": relative,
                "sha256": _sha256(source),
            }
        )
    handoff = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "handoff_id": handoff_id,
        "run_id": run_id,
        "from_agent": from_agent,
        "to_agent": to_agent,
        "created_at": datetime.now(UTC).isoformat(),
        "task": task,
        "message": message,
        "artifacts": artifacts,
        "recipient_permissions": {
            "read_only_inbox": True,
            "can_write_paths": list(definitions[to_agent].write_paths),
            "can_send_to": list(definitions[to_agent].handoff_to),
        },
    }
    handoff_path = recipient_inbox / "handoff.json"
    schema_path = registry_path.parent.parent / "schemas" / HANDOFF_SCHEMA_FILENAME
    schema_errors = validate_json_payload(
        payload=handoff,
        schema=json.loads(schema_path.read_text(encoding="utf-8")),
        schema_dir=schema_path.parent,
    )
    if schema_errors:
        raise CodexAgentRegistryError("handoff schema errors: " + "; ".join(schema_errors))
    handoff_path.write_text(json.dumps(handoff, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return handoff_path


def build_codex_command(
    *,
    registry_payload: dict[str, Any],
    definition: AgentDefinition,
    workspace: Path,
    prompt: str,
) -> list[str]:
    """Build the explicit Codex CLI command for one isolated agent."""
    defaults = registry_payload["defaults"]
    command = [
        str(defaults["codex_executable"]),
        "exec",
        "--cd",
        str(workspace.resolve()),
        "--model",
        definition.model,
        "--sandbox",
        definition.sandbox,
        "--skip-git-repo-check",
    ]
    if not definition.persist_memory:
        command.append("--ephemeral")
    command.extend(["--", prompt])
    return command


def execute_agent(
    *,
    repo_root: Path,
    registry_path: Path,
    run_id: str,
    agent_id: str,
    prompt: str,
    execute: bool = False,
) -> dict[str, Any]:
    """Dry-run or execute one registered Codex process and record its receipt."""
    payload = load_registry(registry_path)
    definitions = agent_definitions(payload)
    if agent_id not in definitions:
        raise CodexAgentRegistryError(f"unknown agent id: {agent_id}")
    definition = definitions[agent_id]
    expected_workspace = _rooted_path(repo_root, payload["workspace_root"]) / run_id / agent_id
    if expected_workspace.exists():
        runtime = _existing_runtime(
            payload=payload,
            definition=definition,
            repo_root=repo_root,
            run_id=run_id,
        )
    else:
        runtime = provision_agents(
            repo_root=repo_root,
            registry_path=registry_path,
            run_id=run_id,
            agent_ids=(agent_id,),
        )[0]
    command = build_codex_command(
        registry_payload=payload,
        definition=definition,
        workspace=runtime.workspace,
        prompt=prompt,
    )
    receipt: dict[str, Any] = {
        "schema_version": "codex_agent_execution_receipt_v1",
        "run_id": run_id,
        "agent_id": agent_id,
        "command": command,
        "workspace": str(runtime.workspace.resolve()),
        "codex_home": str(runtime.codex_home.resolve()),
        "execute": execute,
        "network_access": definition.network_access,
        "status": "planned",
    }
    if execute:
        before = workspace_snapshot(runtime.workspace)
        environment = os.environ.copy()
        environment["CODEX_HOME"] = str(runtime.codex_home.resolve())
        result = subprocess.run(
            command,
            cwd=runtime.workspace,
            env=environment,
            capture_output=True,
            text=True,
            timeout=int(payload["defaults"]["timeout_seconds"]),
            check=False,
        )
        after = workspace_snapshot(runtime.workspace)
        allowed = set(definition.write_paths)
        mutations = tuple(
            path
            for path in sorted(set(before) | set(after))
            if before.get(path) != after.get(path)
            and not _is_allowed_path(path, allowed)
        )
        receipt.update(
            {
                "status": "completed" if result.returncode == 0 and not mutations else "rejected",
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "disallowed_mutations": list(mutations),
            }
        )
    receipt_path = runtime.manifest.parent / "execution_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt["receipt_path"] = str(receipt_path)
    return receipt


def _copy_allowlisted_sources(repo_root: Path, workspace: Path, sources: Iterable[str]) -> None:
    for raw_source in sources:
        relative = _validate_relative_path(str(raw_source), "workspace source")
        source = repo_root / relative
        if not source.exists() or source.is_symlink():
            raise CodexAgentRegistryError(f"workspace source is missing or symlinked: {relative}")
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        else:
            shutil.copy2(source, target)


def _prepare_workspace(workspace: Path, definition: AgentDefinition) -> None:
    (workspace / "output").mkdir(exist_ok=True)
    (workspace / "inbox").mkdir(exist_ok=True)
    instructions = "\n".join(
        [
            f"# Private workspace: {definition.agent_id}",
            "",
            definition.description,
            "",
            "Only use the files present in this workspace.",
            "Do not look for sibling agent workspaces, shared Codex homes, or global project memory.",
            "Read incoming handoffs from inbox/ and write results only to the registered write paths.",
            definition.instructions,
            "",
        ]
    )
    (workspace / "AGENTS.md").write_text(instructions, encoding="utf-8")


def _write_codex_home(
    codex_home: Path,
    definition: AgentDefinition,
    repo_root: Path,
) -> None:
    persistence = "save-all" if definition.persist_memory else "none"
    config = "\n".join(
        [
            'approval_policy = "never"',
            f'sandbox_mode = "{definition.sandbox}"',
            "",
            "[history]",
            f'persistence = "{persistence}"',
            "",
            "[features]",
            "multi_agent = false",
            "",
            "[mcp_servers]",
            "",
        ]
    )
    (codex_home / "config.toml").write_text(config, encoding="utf-8")
    skills_root = codex_home / "skills"
    skills_root.mkdir()
    for skill in definition.skills:
        source = repo_root / _validate_relative_path(skill, "skill source")
        if not source.is_dir() or source.is_symlink():
            raise CodexAgentRegistryError(f"skill source is missing or symlinked: {skill}")
        shutil.copytree(source, skills_root / source.name)


def _existing_runtime(
    *,
    payload: dict[str, Any],
    definition: AgentDefinition,
    repo_root: Path,
    run_id: str,
) -> AgentRuntime:
    """Load paths for a previously provisioned agent without changing it."""
    workspace = _rooted_path(repo_root, payload["workspace_root"]) / run_id / definition.agent_id
    agent_root = _rooted_path(repo_root, payload["runtime_root"]) / run_id / "agents" / definition.agent_id
    codex_home = agent_root / "codex_home"
    inbox = agent_root / "inbox"
    manifest = agent_root / "agent_manifest.json"
    if not all(path.exists() for path in (workspace, codex_home, inbox, manifest)):
        raise CodexAgentRegistryError(
            f"agent runtime is incomplete; provision {definition.agent_id} again with a new run id"
        )
    return AgentRuntime(
        run_id=run_id,
        definition=definition,
        workspace=workspace,
        codex_home=codex_home,
        inbox=inbox,
        manifest=manifest,
    )


def _manifest_payload(
    *,
    repo_root: Path,
    run_id: str,
    definition: AgentDefinition,
    workspace: Path,
    codex_home: Path,
    inbox: Path,
) -> dict[str, Any]:
    return {
        "schema_version": "codex_agent_manifest_v1",
        "run_id": run_id,
        "agent_id": definition.agent_id,
        "description": definition.description,
        "source_repo_root": str(repo_root.resolve()),
        "workspace": str(workspace.resolve()),
        "codex_home": str(codex_home.resolve()),
        "inbox": str(inbox.resolve()),
        "permissions": {
            "read_sources": list(definition.workspace_sources),
            "write_paths": list(definition.write_paths),
            "handoff_export_paths": list(definition.handoff_export_paths),
            "skills": list(definition.skills),
            "tools": list(definition.tools),
            "network_access": definition.network_access,
            "persistent_memory": definition.persist_memory,
        },
        "handoff": {
            "send_to": list(definition.handoff_to),
            "receive_from": list(definition.can_receive_from),
        },
    }


def _rooted_path(repo_root: Path, value: str) -> Path:
    relative = _validate_relative_path(value, "registry root")
    return repo_root / relative


def _validate_relative_path(value: str, label: str) -> str:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts or value in {".", ".."}:
        raise CodexAgentRegistryError(f"{label} must be a relative path without '..': {value!r}")
    return path.as_posix()


def _is_allowed_path(relative: str, allowed_paths: Iterable[str]) -> bool:
    normalized = Path(relative).as_posix()
    return any(normalized == allowed or normalized.startswith(allowed.rstrip("/") + "/") for allowed in allowed_paths)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provision isolated Codex CLI agents.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--registry", type=Path, default=Path("config/codex_agents.json"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.set_defaults(handler=_cli_validate)

    provision = subparsers.add_parser("provision")
    provision.add_argument("--run-id", required=True)
    provision.add_argument("--agent", action="append", dest="agents")
    provision.set_defaults(handler=_cli_provision)

    handoff = subparsers.add_parser("handoff")
    handoff.add_argument("--run-id", required=True)
    handoff.add_argument("--from", dest="from_agent", required=True)
    handoff.add_argument("--to", dest="to_agent", required=True)
    handoff.add_argument("--task", required=True)
    handoff.add_argument("--message", required=True)
    handoff.add_argument("--artifact", action="append", default=[])
    handoff.add_argument("--handoff-id", default="")
    handoff.set_defaults(handler=_cli_handoff)

    execute = subparsers.add_parser("execute")
    execute.add_argument("--run-id", required=True)
    execute.add_argument("--agent", required=True)
    execute.add_argument("--prompt", required=True)
    execute.add_argument("--execute", action="store_true")
    execute.set_defaults(handler=_cli_execute)
    return parser


def _cli_validate(args: argparse.Namespace) -> int:
    payload = load_registry(args.registry)
    print(json.dumps({"valid": True, "agents": [agent["id"] for agent in payload["agents"]]}, indent=2))
    return 0


def _cli_provision(args: argparse.Namespace) -> int:
    runtimes = provision_agents(
        repo_root=args.repo_root,
        registry_path=args.registry,
        run_id=args.run_id,
        agent_ids=args.agents,
    )
    print(json.dumps({"run_id": args.run_id, "agents": [runtime.definition.agent_id for runtime in runtimes]}, indent=2))
    return 0


def _cli_handoff(args: argparse.Namespace) -> int:
    path = create_handoff(
        repo_root=args.repo_root,
        registry_path=args.registry,
        run_id=args.run_id,
        from_agent=args.from_agent,
        to_agent=args.to_agent,
        task=args.task,
        message=args.message,
        artifact_paths=args.artifact,
        handoff_id=args.handoff_id,
    )
    print(path)
    return 0


def _cli_execute(args: argparse.Namespace) -> int:
    receipt = execute_agent(
        repo_root=args.repo_root,
        registry_path=args.registry,
        run_id=args.run_id,
        agent_id=args.agent,
        prompt=args.prompt,
        execute=args.execute,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] in {"planned", "completed"} else 1


if __name__ == "__main__":
    parsed_args = _parser().parse_args()
    raise SystemExit(parsed_args.handler(parsed_args))
