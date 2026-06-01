# AGENTS.md

## Project name

Self Iterating Strategy Agent V0

## Project goal

This repository is the V0 prototype of a self iterating strategy improvement system.

The goal of V0 is to build a deterministic, auditable, rollback friendly loop:

1. Run a baseline strategy on fixed backtest data.
2. Generate metrics and a markdown report.
3. Ask a coding agent to modify only the strategy file.
4. Run the modified strategy on validation data.
5. Compare old and new metrics with hard coded rules.
6. Accept the patch only if it passes the policy gate.
7. Reject and rollback the patch if it fails.

V0 is not intended to build a full multi agent system. It should only create the minimal working loop.

## Core principle

The system must be evaluation driven.

LLM generated suggestions are allowed, but final acceptance must be decided by deterministic code. Do not allow natural language judgment to decide whether a strategy is accepted.

## Current scope

Build V0 only.

Required components:

1. A simple strategy interface.
2. A deterministic backtester.
3. Metrics generation.
4. Markdown report generation.
5. A policy gate.
6. A run loop that executes the full V0 pipeline.
7. Git friendly experiment outputs.
8. Clear tests or smoke checks.

Do not implement the full multi agent architecture yet.

Do not implement visual agents yet.

Do not implement overfitting agents yet.

Do not implement live trading.

Do not connect to real exchanges.

Do not call real Polymarket, Binance, or wallet APIs.

## Domain context

The long term target domain is prediction market strategy research.

The strategy may later be used for Polymarket style orderbook based strategies. The main research problem is that a strategy can fail when a signal appears but liquidity disappears quickly due to maker cancellations or taker competition. V0 should not solve this trading problem directly. V0 should only create the infrastructure that can repeatedly test strategy changes.

## Repository design target

Use Python.

Prefer simple modules over complex frameworks.

Suggested structure:

```text
.
├── AGENTS.md
├── README.md
├── TASK.md
├── pyproject.toml
├── data/
│   ├── train/
│   ├── validation/
│   └── holdout/
├── strategies/
│   ├── baseline_strategy.py
│   └── current_strategy.py
├── backtester/
│   ├── simulate.py
│   ├── metrics.py
│   └── schema.py
├── reports/
│   └── generate_report.py
├── orchestrator/
│   ├── run_loop.py
│   ├── policy_gate.py
│   └── git_utils.py
├── experiments/
│   └── .gitkeep
└── tests/
    └── test_smoke.py
```

The exact structure may be adjusted if needed, but keep the system small and understandable.

## Data policy

Data files are treated as immutable experiment inputs.

Do not modify files under:

```text
data/
```

Generated experiment outputs should go under:

```text
experiments/<run_id>/
```

Each run directory should contain:

```text
metrics_before.json
metrics_after.json
report_before.md
report_after.md
decision.json
patch.diff
trades_before.csv
trades_after.csv
```

If some files are not available in the first implementation, create the pipeline so they can be added later.

## Strategy policy

For V0, only this file should be modified by the strategy improvement step:

```text
strategies/current_strategy.py
```

Do not modify:

```text
data/
backtester/
orchestrator/policy_gate.py
```

unless the current task explicitly asks for infrastructure changes.

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

The exact formulas can be simple in V0, but they must be deterministic and documented.

## Acceptance policy

The policy gate should compare baseline metrics and modified strategy metrics.

A patch should be accepted only if all required rules pass.

Default V0 rules:

```json
{
  "min_trade_count": 20,
  "min_ev_improvement": 0.01,
  "max_drawdown_worsening": 0.01,
  "max_slippage_worsening": 0.005
}
```

The policy gate must output:

```json
{
  "accepted": true,
  "reasons": [],
  "before": {},
  "after": {}
}
```

or:

```json
{
  "accepted": false,
  "reasons": ["..."],
  "before": {},
  "after": {}
}
```

## Engineering rules

Keep the code deterministic.

Use fixed random seeds where randomness is needed.

Prefer plain Python, pandas, pydantic, pytest, and standard library tools.

Avoid heavy dependencies.

Avoid hidden global state.

Use clear function boundaries.

Write docstrings for public functions.

Make every command runnable from the repository root.

Do not add real credentials, private keys, API keys, or wallet logic.

Do not add network calls in V0.

## Testing

Add smoke tests that verify:

1. The backtester can run on sample data.
2. Metrics are generated.
3. The report is generated.
4. The policy gate returns a valid decision.
5. The full V0 run loop completes.

The project is complete only when these checks pass:

```bash
pytest
python -m orchestrator.run_loop
```

## Expected behavior

When the V0 loop runs, it should:

1. Create a new run directory under `experiments/`.
2. Run the current strategy.
3. Save before metrics.
4. Generate a report.
5. Stop and instruct the user to run Codex for strategy modification, or optionally support a placeholder strategy modification step.
6. Run the modified strategy.
7. Save after metrics.
8. Run the policy gate.
9. Save `decision.json`.
10. Print a short final summary.

## Important constraint

Do not overbuild.

V0 should be boring, testable, and easy to debug.