# Strategy Interface Contract

V0.5 strategy-improvement agents may only modify:

```text
strategies/current_strategy.py
```

The strategy module must expose:

```python
def generate_orders(snapshot: MarketSnapshot) -> list[StrategyOrder]:
    ...
```

## Input

`snapshot` is a frozen `MarketSnapshot` from `backtester.schema`:

```python
MarketSnapshot(
    timestamp: str,
    market_id: str,
    yes_price: float,
    fair_value: float,
    outcome: int,
    liquidity: float,
    next_yes_price: float,
)
```

Strategies must treat snapshots as read-only.

## Output

The function must return a plain list of `StrategyOrder` objects. Each order must:

- use the same `market_id` as the snapshot
- use `side="YES"`
- have `0.0 < limit_price < 1.0`
- have `stake > 0.0`
- use finite numeric values
- be deterministic for the same input snapshot

Invalid outputs fail before simulation and are not scored.

## Boundaries

Strategy code must not:

- read or write files
- make network calls
- access credentials, wallets, exchanges, or external APIs
- mutate global state in a way that changes later decisions
- modify anything under `data/`, `backtester/`, or `orchestrator/`

The deterministic policy gate, not the strategy or agent, decides whether a
patch is accepted.

## Agent Adapter Boundary

Strategy modifier adapters must return a `StrategyProposal`.

The dry-run Codex CLI adapter is allowed to build and record a prompt and command,
but it must not invoke Codex or edit files. The guarded `codex_cli` adapter may
invoke a subprocess only when config explicitly sets `execute=true`; it must keep
the same proposal shape and still only target `strategies/current_strategy.py`.

Codex-facing adapters should run against an isolated copy under:

```text
workspaces/<run_id>/<round_id>/strategy_workspace/
```

Any returned text must be parsed as a unified diff. Patches that touch files
other than `strategies/current_strategy.py` must be rejected before `git apply`.

Each iteration round writes stable JSON fixtures for agent integration:

```text
agent_input.json   # schema_version: agent_io_input_v1
agent_output.json  # schema_version: agent_io_output_v1
```

Future CLI or SDK-backed agents should treat `agent_input.json` as the structured
input contract and `agent_output.json` as the audited selected-output contract.
The `file_protocol` modifier is a guarded bridge for this contract: when
`execute=true`, it runs a configured command with `agent_input.json` and an
output path as arguments, then parses the command's JSON or diff output into the
same `StrategyProposal` contract. The command runs in an isolated workspace;
mutating workspace files other than the configured output file is rejected.
Every file-protocol round also writes `agent_execution.json`, which records the
command, working directory, return code, output-file hashes, stdout/stderr
summaries, and mutation-guard errors.
