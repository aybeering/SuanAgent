# AGENTS.md

## Project name

Self Iterating Strategy Agent V0.5

## Project goal

This repository is a deterministic, auditable prototype for strategy self-iteration.

V0 implemented the single-run evaluation loop:

1. Run strategy code on fixed backtest data.
2. Generate metrics and a markdown report.
3. Compare before/after metrics with hard-coded policy rules.
4. Accept or reject with deterministic code.

V0.5 builds on that by adding a minimal self-iteration skeleton:

1. Run the current strategy on fixed validation data.
2. Generate before metrics and report.
3. Call a strategy modifier stub.
4. Apply the stub proposal as a patch.
5. Run the modified strategy.
6. Generate after metrics and report.
7. Compare old and new metrics with the policy gate.
8. Accept and commit the patch only if policy passes.
9. Reject and roll back the patch if policy fails.
10. Repeat until accepted or the max-round limit is reached.

V0.5 is not the full multi-agent system. It is the smallest deterministic loop
that proves the self-iteration control flow works.

## Core principle

The system must be evaluation driven.

Agent-generated suggestions are allowed, but final acceptance must be decided by
deterministic code. Do not allow natural language judgment to decide whether a
strategy is accepted.

## Current scope

Build V0.5 only.

Allowed components:

1. A simple strategy interface.
2. A deterministic backtester.
3. Metrics generation.
4. Markdown report generation.
5. A deterministic policy gate.
6. A single-run V0 pipeline.
7. A multi-round V0.5 iteration loop.
8. A fixed strategy modifier stub.
9. A proposal schema for agent output.
10. Git apply, accept commit, and reject rollback helpers.
11. Round-based experiment outputs.
12. Clear tests and smoke checks.

Still out of scope:

1. Real Codex CLI integration.
2. Full multi-agent architecture.
3. Visual agents.
4. HTML chart rendering agents.
5. Overfitting agents.
6. Live trading.
7. Real exchange, Polymarket, Binance, wallet, or network APIs.

## Domain context

The long-term target domain is prediction market strategy research.

The strategy may later be used for Polymarket-style orderbook strategies. The
research problem is that a strategy can fail when a signal appears but liquidity
disappears quickly due to maker cancellations or taker competition. V0.5 should
not solve this trading problem directly. V0.5 should only create the
infrastructure that can repeatedly test and gate strategy changes.

## Repository design target

Use Python.

Prefer simple modules over complex frameworks.

Current structure:

```text
.
├── AGENTS.md
├── README.md
├── TASK.md
├── pyproject.toml
├── agents/
│   └── strategy_modifier_stub.py
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
│   ├── iteration_loop.py
│   ├── policy_gate.py
│   ├── proposal.py
│   ├── git_manager.py
│   └── git_utils.py
├── experiments/
│   └── .gitkeep
└── tests/
    ├── test_smoke.py
    └── test_iteration_loop.py
```

The exact structure may be adjusted if needed, but keep the system small and
understandable.

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

The single-run V0 pipeline writes:

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

The multi-round V0.5 loop writes:

```text
manifest.json
round_001/
  metrics_before.json
  report_before.md
  trades_before.csv
  proposal.json
  agent_response.txt
  patch.diff
  metrics_after.json
  report_after.md
  trades_after.csv
  decision.json
```

Additional rounds use the same `round_NNN/` structure.

## Strategy policy

For strategy improvement rounds, only this file should be modified by the agent
or stub proposal:

```text
strategies/current_strategy.py
```

Infrastructure tasks may modify:

```text
agents/
backtester/
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

unless the current task explicitly asks for infrastructure or policy changes.

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

## Acceptance policy

The policy gate should compare before and after metrics.

A patch should be accepted only if all required rules pass.

Default V0.5 rules:

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

Prefer plain Python, pytest, and standard library tools.

Avoid heavy dependencies.

Avoid hidden global state.

Use clear function boundaries.

Write docstrings for public functions.

Make every command runnable from the repository root.

Do not add real credentials, private keys, API keys, or wallet logic.

Do not add network calls in V0.5.

## Testing

Add smoke tests that verify:

1. The backtester can run on sample data.
2. Metrics are generated.
3. The report is generated.
4. The policy gate returns a valid decision.
5. The full V0 run loop completes.
6. The V0.5 iteration loop creates round artifacts.
7. The strategy modifier stub generates a fixed patch.
8. Reject rolls back the strategy file.
9. Accept can stop the loop under relaxed test rules.
10. The max-round guard stops repeated rejections.

The project is complete only when these checks pass:

```bash
pytest
python -m orchestrator.run_loop
python -m orchestrator.iteration_loop
```

## Expected behavior

When the V0.5 loop runs, it should:

1. Create a new run directory under `experiments/`.
2. Create per-round directories under that run.
3. Run the current strategy before modification.
4. Save before metrics, trades, and report.
5. Call the fixed strategy modifier stub.
6. Save `proposal.json`, `agent_response.txt`, and `patch.diff`.
7. Apply the patch with Git.
8. Run the modified strategy.
9. Save after metrics, trades, and report.
10. Run the policy gate.
11. Save `decision.json`.
12. Accept and commit if policy passes.
13. Reject and roll back if policy fails.
14. Save `manifest.json`.
15. Print a short final summary.

## Important constraint

Do not overbuild.

V0.5 should be boring, deterministic, testable, and easy to debug.
