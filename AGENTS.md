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

1. Run the current strategy on fixed train, validation, and holdout data.
2. Generate before metrics and reports.
3. Call a strategy modifier stub.
4. Apply the stub proposal as a patch.
5. Run the modified strategy on train, validation, and holdout data.
6. Generate after metrics and reports.
7. Compare old and new validation metrics with the policy gate.
8. Accept and commit the patch only if policy passes.
9. Reject and roll back the patch if policy fails.
10. Repeat until accepted, a failed patch repeats, or the max-round limit is reached.

V0.5 is not the full multi-agent system. It is the smallest deterministic loop
that proves the self-iteration control flow works.

The loop should stop early when a rejected patch is repeated, unless repeated
proposals are explicitly allowed for max-round smoke testing.

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
9. A deterministic adaptive stub that changes fixed patch direction from context.
10. A proposal schema for agent output.
11. A guarded Codex CLI adapter that only executes when config explicitly enables it.
12. Isolated workspace creation for future Codex execution.
13. Unified diff extraction and target-file validation.
14. Git apply, accept commit, and reject rollback helpers.
15. Round-based experiment outputs.
16. Config-driven dataset, policy, and modifier settings.
17. Proposal quality metadata and repeated-patch detection.
18. Repeated-proposal stop control.
19. Clear tests and smoke checks.
20. GitHub Actions CI for deterministic smoke validation.

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
├── config/
│   └── default.json
├── .github/
│   └── workflows/
│       └── ci.yml
├── docs/
│   └── strategy_interface.md
├── agents/
│   ├── strategy_modifier_adaptive_stub.py
│   ├── codex_dry_run_adapter.py
│   ├── registry.py
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
│   ├── agent_context.py
│   ├── outcome_memory.py
│   ├── policy_gate.py
│   ├── proposal.py
│   ├── run_summary.py
│   ├── patch_parser.py
│   ├── workspace_manager.py
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
summary.md
trades_before.csv
trades_after.csv
```

The multi-round V0.5 loop writes:

```text
manifest.json
summary.md
index.jsonl
memory.jsonl
round_001/
  train_metrics_before.json
  train_report_before.md
  train_trades_before.csv
  metrics_before.json
  report_before.md
  trades_before.csv
  holdout_metrics_before.json
  holdout_report_before.md
  holdout_trades_before.csv
  agent_context.md
  proposal.json
  agent_response.txt
  patch.diff
  train_metrics_after.json
  train_report_after.md
  train_trades_after.csv
  metrics_after.json
  report_after.md
  trades_after.csv
  holdout_metrics_after.json
  holdout_report_after.md
  holdout_trades_after.csv
  decision.json
```

Additional rounds use the same `round_NNN/` structure.

Each `proposal.json` should keep agent output auditable. It records the patch,
agent summary, hypotheses, expected metric changes, risk notes, patch hash,
quality checks, and whether the patch repeats a prior round in the same run.
Each `agent_context.md` should summarize prior rounds for the next modifier
call, including failed patch hashes, validation/holdout deltas, repeat status,
and deterministic rejection reasons.
Each iteration round should append a compact proposal outcome to
`experiments/memory.jsonl` so later runs and different modifier backends can
reuse prior proposal outcomes.

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
config/
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
10. The repeated-proposal guard stops duplicate failed patches.
11. The max-round guard still works when repeated proposals are explicitly allowed.
12. Config loading exposes train, validation, and holdout splits.
13. Invalid strategy orders are rejected before simulation.
14. The dry-run Codex adapter records a non-applicable proposal without changing files.
15. Patch parsing rejects changes outside `strategies/current_strategy.py`.
16. Isolated workspaces copy the minimal project without `.git`.

The project is complete only when these checks pass:

```bash
pytest
python -m orchestrator.run_loop
python -m orchestrator.iteration_loop
python -m orchestrator.preflight --config config/default.json
python -m orchestrator.iteration_loop --config config/codex_dry_run.json --run-id smoke-dry --max-rounds 1
python -m orchestrator.experiments list --limit 5
python -m orchestrator.experiments summary
python -m orchestrator.experiments leaderboard --limit 5
python -m orchestrator.experiments memory --limit 5
```

## Expected behavior

When the V0.5 loop runs, it should:

1. Create a new run directory under `experiments/`.
2. Create per-round directories under that run.
3. Run the current strategy before modification on all configured data splits.
4. Save train, validation, and holdout before metrics, trades, and reports.
5. Call the fixed strategy modifier stub using the train report.
6. Save `agent_context.md`, `proposal.json`, `agent_response.txt`, and `patch.diff`.
7. Apply the patch with Git.
8. Run the modified strategy on all configured data splits.
9. Save train, validation, and holdout after metrics, trades, and reports.
10. Run the policy gate on validation metrics only.
11. Save `decision.json`.
12. Append proposal outcome memory to `experiments/memory.jsonl`.
13. Accept and commit if policy passes.
14. Reject and roll back if policy fails.
15. Stop with `stopped_repeated_proposal` if the rejected patch repeats a prior round.
16. Stop with `stopped_max_rounds` if max rounds is reached.
17. Save `manifest.json`.
18. Print a short final summary.

The configured modifier may also be `codex_dry_run`, `codex_cli_dry_run`, or
`codex_cli`. The `adaptive_stub` modifier is still deterministic, but it should
read `agent_context.md` and choose a different fixed patch after prior failures.
The `codex_cli` adapter must default to `execute=false`; only an explicit
config change may invoke a subprocess.

CLI entrypoints must support `--config` and `--run-id` so experiments can switch
between modes without editing `config/default.json`.

Run preflight before experiment execution. It must fail fast on missing data
paths, unsupported modifiers, invalid policy config, or enabled Codex execution
without an available executable.

Experiment inspection commands should read `experiments/index.jsonl` and local
run artifacts without mutating strategy code. Leaderboards should rank by
validation EV improvement, not natural-language judgment.

Future Codex output must be parsed as a unified diff and rejected before git
apply if it touches anything except `strategies/current_strategy.py`.

## Important constraint

Do not overbuild.

V0.5 should be boring, deterministic, testable, and easy to debug.
