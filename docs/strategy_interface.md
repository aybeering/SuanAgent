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
`agent_input.json` includes an advisory `strategy_search_space` block with
direction tags, direction order, modifier hints, and a fallback direction; this
block guides proposal generation only and cannot route agents or decide
acceptance.
`proposal_intent.json` includes a `direction_decision_trace` that explains the
planner's candidate order, selected direction, and avoid-source codes. Future
agents may use it as context, but it cannot score candidates, route profiles,
apply patches, or decide acceptance.
For convenience, `agent_input.json` also includes `proposal_intent_summary`, a
compact copy of the recommended direction, trace selection code, candidate
order, avoid-source summary, and advisory-only policy. Workspace and
attempt-scoped agent inputs preserve the same summary.
`agent_execution_plan.json` binds that same summary into each planned attempt's
input contract so the pre-execution queue and later agent inputs can be checked
for drift.
Each saved attempt's `attempt_output.json` also records the same summary, so
audit replay can detect input/output drift without changing candidate replay,
patch application, or acceptance.
The round-level `agent_output.json` records the same summary as well, binding
the selected-output contract back to the planner context in `agent_input.json`.
`agent_validation.json` records the same summary while checking contract shape,
patch target, and git-apply viability.
`agent_output_quarantine.json` preserves the same summary before patch
application, so pre-apply audits can detect context drift without changing the
quarantine release rules.
Agent profiles may separately declare `supported_directions`. The executor uses
that declaration only as a deterministic contract check after a proposal is
normalized: a candidate whose `direction_tag` is outside its own declared
capability is skipped and audited as `direction_not_supported`. This does not
let the planner choose an agent and does not bypass the policy gate.
Candidate artifacts also include `direction_intent_alignment`, which compares
the proposal intent's recommended direction, the profile capability, and the
actual proposal direction. It records whether a proposal matched or deviated
from the recommendation and whether that deviation was allowed, but it is
audit-only.
Candidate artifacts also carry `candidate_score`, `score_reasons`, and
`quality_breakdown` across executor, attempt, selection, routing, selected
output, and leaderboard views. These fields explain deterministic candidate
ranking and are validated for score consistency. The artifact validator also
binds each row by `attempt_id` back to `proposal_attempts.json`, but final
strategy acceptance still comes only from the policy gate and holdout gate.
The corresponding JSON Schema files are:

```text
schemas/agent_input.schema.json
schemas/agent_output.schema.json
schemas/agent_execution.schema.json
```

The `file_protocol` modifier is a guarded bridge for this contract: when
`execute=true`, it runs a configured command with `agent_input.json` and an
output path as arguments, then parses the command's JSON or diff output into the
same `StrategyProposal` contract. The command runs in an isolated workspace;
mutating workspace files other than the configured output file is rejected.
Every file-protocol round also writes `agent_execution.json`, which records the
command, working directory, return code, output-file hashes, stdout/stderr
summaries, and mutation-guard errors.
Its execution `status` is deterministic: `disabled`, `completed`,
`command_failed`, `timeout`, or `workspace_violation`. A completed command can
still yield a rejected proposal when output is malformed or the patch touches a
file other than `strategies/current_strategy.py`.

`agents.file_protocol_demo_agent` is the deterministic reference command for
this protocol. It can be run through `config/file_protocol_demo.json` to prove
that an external process can consume `agent_input.json`, emit proposal JSON, and
then let the loop apply all normal deterministic gates.
