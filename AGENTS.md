# AGENTS.md

## Project Name

Self Iterating Strategy Agent V0.5

## Project Goal

This repository is a deterministic, auditable prototype for strategy
self-iteration.

V0 implemented the single-run evaluation loop:

1. Run strategy code on fixed backtest data.
2. Generate metrics and a markdown report.
3. Compare before/after metrics with hard-coded policy rules.
4. Accept or reject with deterministic code.

V0.5 adds a minimal self-iteration skeleton:

1. Run the current strategy on fixed train, validation, and holdout data.
2. Generate before metrics and reports.
3. Call one active strategy modifier backend.
4. Normalize the modifier output into the shared proposal contract.
5. Apply the proposal patch only after deterministic validation passes.
6. Run the modified strategy on train, validation, and holdout data.
7. Compare old and new validation metrics with the policy gate.
8. Run the configured holdout risk gate as a deterministic veto.
9. Accept and commit the patch only if both gates pass.
10. Reject and roll back the patch if either gate fails.
11. Stop on acceptance, repeated failed proposal, deterministic no-improvement
    stop, or the configured max-round limit.

V0.5 is not the full multi-agent system. It is the smallest deterministic loop
that proves the self-iteration control flow works.

## Core Principle

The system must be evaluation driven.

Agent-generated suggestions are allowed, but final acceptance must be decided by
deterministic code. Do not allow natural-language judgment to decide whether a
strategy is accepted.

## Current Scope

Build V0.5 only.

Allowed implementation work includes the deterministic evaluation loop, strategy
modifier stubs, guarded external-adapter slots, proposal contracts, artifact
validation, replay commands, read-only outcome-memory hygiene and scope
recommendation artifacts, read-only config change candidate and operator review
artifacts, read-only config application dry-run artifacts, guarded config
application receipt artifacts, read-only config rollback preview artifacts, and
guarded config restore receipt artifacts, read-only config lineage artifacts,
read-only run closeout operator dashboard summaries, read-only operator action
plans, read-only operator action approval receipts, guarded read-only operator
action execution receipts, read-only operator action audit artifacts, read-only
operator action dashboard artifacts, read-only operator unlock checklist
artifacts, read-only Codex CLI unlock runbook artifacts, read-only operator
cockpit artifacts, read-only Codex CLI execution readiness diff artifacts, and
Codex CLI readiness evidence, plus schema-validated terminal-only operator view
refresh receipts and experiment summary dashboards.

Still out of scope:

1. Real Codex CLI strategy execution.
2. Full multi-agent architecture.
3. Concurrent or distributed agent execution.
4. Visual agents with routing authority.
5. Overfitting agents with veto authority.
6. Live trading.
7. Real exchange, Polymarket, Binance, wallet, or network integrations.

## Documentation Map

Use these files instead of expanding this instruction file with long reference
lists:

- `TASK.md` defines the current V0.5 target and required smoke checks.
- `README.md` is the short project entrypoint.
- `docs/architecture.md` explains runtime architecture, authority, roles,
  workspaces, executor behavior, memory, and champion registry.
- `docs/artifact_reference.md` indexes generated artifacts, commands, replay
  tools, and validators.
- `docs/codex_cli_readiness.md` explains guarded Codex CLI readiness evidence.
- `docs/contract_roadmap.md` tracks the detailed V0.5 contract roadmap.
- `docs/strategy_interface.md` documents the strategy modification boundary.
- `schemas/` contains machine-readable JSON contracts.

When adding a new artifact family, readiness stage, or agent contract, update
the relevant `docs/` file, schema, tests, and validators. Keep `AGENTS.md`
focused on rules that affect day-to-day code changes.

## Domain Context

The long-term target domain is prediction market strategy research.

The strategy may later be used for Polymarket-style orderbook strategies. The
research problem is that a strategy can fail when a signal appears but liquidity
disappears quickly due to maker cancellations or taker competition. V0.5 should
not solve this trading problem directly. V0.5 should only create the
infrastructure that can repeatedly test and gate strategy changes.

## Repository Design Target

Use Python.

Prefer simple modules over complex frameworks.

Keep the system small, deterministic, and understandable.

Top-level structure:

```text
.
├── AGENTS.md
├── README.md
├── TASK.md
├── pyproject.toml
├── agents/
├── backtester/
├── config/
├── data/
├── docs/
├── experiments/
├── orchestrator/
├── reports/
├── schemas/
├── strategies/
└── tests/
```

## Data Policy

Data files are immutable experiment inputs.

Do not modify files under:

```text
data/
```

Generated experiment outputs should go under:

```text
experiments/<run_id>/
```

Artifact details live in `docs/artifact_reference.md`.
Outcome-memory hygiene and scope recommendation artifacts are advisory only:
they may suggest future config changes, but they must not edit config, delete
memory, route candidates, apply patches, or change acceptance.
Config change candidate artifacts are also advisory only. They may record fields
an operator could edit later, but the loop must not apply those changes by
itself.
Operator config review artifacts may record approve or reject intent for those
candidates. Approval still must not apply config automatically.
Config application dry-run artifacts may preview whether approved config
candidates are still safe for a later manual edit. They still must not apply
config automatically.
Config application receipts may be written only by an explicit guarded command
after approved dry-run evidence still matches current config. Receipts may
write config only through that command and must not run agents or change
iteration acceptance.
Config application rollback previews may inspect receipts and current config to
describe manual restore plans and next-run impact. They must remain read-only
and must not restore config automatically.
Config application restore receipts may be written only by an explicit guarded
restore command after rollback preview evidence still matches current config.
Receipts may write config only through that command and must not run agents or
change iteration acceptance.
Config lineage artifacts may connect config candidates, reviews, dry-runs,
apply receipts, rollback previews, and restore receipts for audit. They must be
read-only and must not write config.
Operator action plans may translate run closeout dashboard items into explicit
command candidates for review. They must be read-only and must not execute
commands, write config, promote champions, run agents, apply patches, or change
acceptance.
Operator action approval receipts may record explicit approval for one
action-plan command candidate. They must bind to the action plan and selected
command digest, but must still not execute commands or change repository state.
Operator action execution receipts may execute only an approved, allowlisted,
read-only inspection command from the action plan. They must block commands
that write repository state, promote champions, run backtests, execute agents,
apply patches, route agents, or change acceptance, and they must record output
hashes plus tracked workspace mutation evidence.
Operator action audit artifacts may connect the saved action plan, approval,
and execution receipt into one digest-checked chain. They must remain read-only
and must not execute commands, write config, promote champions, run agents,
run backtests, apply patches, route agents, or change acceptance.
Operator action dashboard artifacts may summarize that action chain into a
human-facing next-step view. They must remain read-only and must not record
approval, execute commands, write config, promote champions, run agents, run
backtests, apply patches, route agents, or change acceptance.
Operator unlock checklist artifacts may summarize Codex CLI startup preflight
evidence as standalone grouped request, intent, source, command, workspace, and
mutation-boundary checks. They may include expected artifact paths, blocker
reason codes, and command hints for manual operator action. They must remain
read-only and must not record unlock approval, execute those commands, execute
Codex, create workspaces, run agents, apply patches, route agents, or change
acceptance.
If a real Codex execute=true startup preflight fails before any round starts,
the iteration loop should still write the standalone operator unlock checklist
and surface its navigation summary in `manifest.json` and `summary.md`.
Operator cockpit artifacts may summarize run review, config lineage, operator
action, Codex CLI execution preflight, standalone operator unlock checklist,
challenger, champion promotion, and scope-health state into one human-facing
page. The Codex CLI preflight panel may expose unlock blockers, readiness
counts, and grouped checklist status, but it must not unlock Codex or execute
agents. Cockpit artifacts must remain read-only and must not record approval,
execute commands, write config, promote champions, run agents, run backtests,
apply patches, route agents, or change acceptance.
Codex CLI execution readiness diff artifacts may compare the current candidate
config, startup preflight expected execution, execution candidate, real dry-run,
and operator request evidence for drift. They must remain read-only and must
not record approval, execute commands, execute Codex, create workspaces, modify
config, run agents, apply patches, route agents, or change acceptance.
The iteration loop should write this diff during closeout and during failed
real Codex execute=true startup preflight runs. Operator cockpit artifacts may
include a dedicated readiness-diff panel and summary counters, but still must
not unlock or execute Codex.
The iteration loop writes the final operator action dashboard and cockpit
during closeout, along with the standalone operator unlock checklist and Codex
CLI execution readiness diff. Explicit commands may refresh them after later
operator artifacts are written.

## Strategy Policy

For strategy improvement rounds, only this file should be modified by the agent
or stub proposal:

```text
strategies/current_strategy.py
```

Infrastructure tasks may modify:

```text
agents/
backtester/
config/
docs/
orchestrator/
reports/
tests/
README.md
TASK.md
AGENTS.md
pyproject.toml
```

Do not modify:

```text
data/
orchestrator/policy_gate.py
```

unless the current task explicitly asks for infrastructure, data, or policy
changes.

## Metrics

The metrics should include at least:

```json
{
  "ev": 0.0,
  "total_pnl": 0.0,
  "max_drawdown": 0.0,
  "trade_count": 0,
  "fill_rate": 0.0,
  "avg_slippage": 0.0
}
```

The formulas can be simple in V0.5, but they must be deterministic and
documented.

## Acceptance Policy

The policy gate should compare before and after validation metrics.

A patch should be accepted only if all required validation rules pass and the
configured holdout risk gate does not veto it.

Default V0.5 validation rules:

```json
{
  "min_trade_count": 20,
  "min_ev_improvement": 0.01,
  "max_drawdown_worsening": 0.01,
  "max_slippage_worsening": 0.005
}
```

The default holdout gate is conservative and can only reject a candidate:

```json
{
  "enabled": true,
  "min_trade_count": 1,
  "min_ev_delta": -0.01,
  "max_drawdown_worsening": 0.02,
  "max_slippage_worsening": 0.005
}
```

Iteration decisions may also include a `holdout_policy` object with the holdout
gate result, metrics, and active rules.

## Engineering Rules

Keep the code deterministic.

Use fixed random seeds where randomness is needed.

Prefer plain Python, pytest, and standard library tools.

Avoid heavy dependencies.

Avoid hidden global state.

Use clear function boundaries.

Write docstrings for public functions.

Make every command runnable from the repository root.

Do not add real credentials, private keys, API keys, or wallet logic.

Do not add network calls in V0.5.

Do not add a second Codex-only output parser. Future Codex output must be
normalized through the shared agent-output intake path and rejected before
`git apply` if it touches anything except `strategies/current_strategy.py`.

## Testing

At minimum, the current target must keep these checks green:

```bash
pytest
python -m orchestrator.run_loop
python -m orchestrator.iteration_loop
python -m orchestrator.preflight --config config/default.json
```

For broader artifact, replay, and inspection coverage, use the command list in
`docs/artifact_reference.md` and the CI workflow in `.github/workflows/ci.yml`.

## Expected Behavior

When the V0.5 loop runs, it should:

1. Create a new run directory under `experiments/`.
2. Write startup preflight artifacts.
3. Evaluate the current strategy on train, validation, and holdout data.
4. Build deterministic context, proposal intent, role-readiness, planning,
   visual, analysis, and agent I/O artifacts.
5. Invoke the configured deterministic modifier backend.
6. Validate the selected proposal contract and strategy-only patch target.
7. Apply the patch only after deterministic checks pass.
8. Re-run evaluation on all configured data splits.
9. Run validation and holdout gates.
10. Accept and commit, or reject and roll back.
11. Write manifest, summary, diagnosis, research brief, and replayable round
    artifacts.
12. Print a short final summary.

Detailed runtime behavior lives in `docs/architecture.md`; detailed artifacts
live in `docs/artifact_reference.md`.

## Important Constraint

Do not overbuild.

V0.5 should be boring, deterministic, testable, and easy to debug.
