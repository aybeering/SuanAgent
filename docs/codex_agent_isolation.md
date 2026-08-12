# Codex CLI agent isolation

`config/codex_agents.json` is the registry for independent Codex CLI agents.
It is separate from `config/default.json`, so adding an agent does not change
the V0.5 strategy acceptance loop.

The machine-readable contracts are `schemas/codex_agent_registry.schema.json`
and `schemas/codex_agent_handoff.schema.json`.

## What the registry controls

Each registered agent has an explicit identity, source files copied into its
private workspace, paths it may modify, allowed skill and tool names, memory
persistence, network setting, and directed handoff edges.

The runtime creates the following private layout for a run:

```text
workspaces/codex_agents/<run_id>/<agent_id>/       # only this agent's files
experiments/codex_agents/<run_id>/agents/<id>/
  codex_home/                                      # only this agent's Codex state
  inbox/<handoff_id>/                              # only explicit incoming work
  agent_manifest.json
```

The handoff path is one-way and explicit:

```text
analysis_agent --handoff--> strategy_bot --handoff--> verification_agent
       ^                                                     |
       +---------------------- declared route ---------------+
```

The sender cannot deliver an undeclared edge or an undeclared artifact. The
recipient receives a copy of the artifact and a `handoff.json` file in its own
inbox. It does not receive the sender's workspace or Codex home.

## Commands

Validate the registry without creating anything:

```bash
python -m orchestrator.codex_agent_runtime \
  --repo-root . --registry config/codex_agents.json validate
```

Provision all registered agents for one run:

```bash
python -m orchestrator.codex_agent_runtime \
  --repo-root . --registry config/codex_agents.json \
  provision --run-id strategy-bot-dev
```

Create a directed handoff after the sender has written an allowed artifact:

```bash
python -m orchestrator.codex_agent_runtime \
  --repo-root . --registry config/codex_agents.json \
  handoff --run-id strategy-bot-dev \
  --from analysis_agent --to strategy_bot \
  --task "根据分析结果提出策略候选修改" \
  --message "只检查 inbox 中的交接内容，并把候选结果写入 output/" \
  --artifact output/analysis.json \
  --handoff-id analysis-to-strategy-001
```

Build the command and receipt without starting Codex:

```bash
python -m orchestrator.codex_agent_runtime \
  --repo-root . --registry config/codex_agents.json \
  execute --run-id strategy-bot-dev --agent strategy_bot \
  --prompt "读取 inbox 中的交接，修改策略候选并把说明写入 output/"
```

The actual subprocess requires the explicit `--execute` switch. It runs with a
private `CODEX_HOME`, `codex exec --cd <private workspace>`, `--ephemeral`, and
the registered sandbox mode. The process output is checked after it exits; a
write outside the registered paths produces a rejected execution receipt.

## Boundary and limitation

This implementation isolates repository-visible state, Codex configuration,
custom skills, MCP configuration, workspaces, and handoff data at the
orchestrator level. The default registry has no custom skills, no MCP servers,
no network access, and no persistent memory. The `skills` and `tools` fields
are auditable allowlists; custom skills are copied only when explicitly listed,
and this version enables no extra MCP tools. Codex's built-in shell capability
is controlled by its sandbox and is not dynamically switchable by tool name in
this registry.

It does not create a separate operating-system user, container, or virtual
machine. Therefore it is not an absolute OS-level read barrier against a
malicious process that deliberately escapes the Codex sandbox. If that threat
model is required, each agent must run under a separate OS/container boundary;
the registry and handoff contract can remain the control-plane layer.
