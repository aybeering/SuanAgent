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
8. Run the configured holdout risk gate as a deterministic veto.
9. Accept and commit the patch only if both gates pass.
10. Reject and roll back the patch if either gate fails.
11. Repeat until accepted, a failed patch repeats, or the max-round limit is reached.

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
10. A proposal schema and deterministic contract validator for agent output.
11. A guarded Codex CLI adapter that only executes when config explicitly enables it.
12. Isolated workspace creation for future Codex execution.
13. Workspace mutation checks that reject hidden Codex CLI side effects outside the strategy file.
14. Unified diff extraction and target-file validation.
15. Git apply, accept commit, and reject rollback helpers.
16. Round-based experiment outputs.
17. Config-driven dataset, validation policy, holdout policy, and modifier settings.
18. Proposal quality metadata and repeated-patch detection.
19. Repeated-proposal stop control.
20. Clear tests and smoke checks.
21. A guarded file-protocol adapter for future CLI or SDK-backed agents.
22. A local deterministic file-protocol demo agent for end-to-end external-agent smoke tests.
23. File-protocol execution audit logs with command, output hashes, and mutation-guard results.
24. GitHub Actions CI for deterministic smoke validation.

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
│   ├── file_protocol_demo_agent.py
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
  agent_context.json
  agent_input.json
  agent_output.json
  proposal.json
  agent_execution.json   # file_protocol runs only
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
agent summary, protocol version, direction tag, hypotheses, expected metric
changes, risk notes, patch hash, quality checks, contract errors, and whether
the patch repeats a prior round in the same run.
Every proposal must pass the `proposal_v1` contract before patch checks, probe
evaluation, or application. Contract-invalid proposals must be marked
non-applicable, recorded with `contract_errors`, and rejected by deterministic
code.
Codex-style adapters may parse either a plain unified diff or a structured JSON
proposal object. Structured JSON should include `summary`, `risk_notes`,
`direction_tag`, `expected_metric_change`, `hypotheses`, and `patch_diff`; the
parsed proposal must still pass the same deterministic contract validator.
Each round should write both `agent_context.md` and `agent_context.json` from
the same context payload. The markdown file should summarize prior rounds for
human inspection. The JSON file should use schema version `agent_context_v1`
and include prior rounds, failed patch hashes, candidate search trace, global
outcome memory, target file, and policy notes for SDK-backed agents.
Each round should also write `agent_input.json` and `agent_output.json`.
`agent_input.json` should use schema version `agent_io_input_v1` and describe
the reports, context, before metrics, policy config, candidate-selection config,
and modifier list available to the agent. `agent_output.json` should use schema
version `agent_io_output_v1` and record the selected proposal, compact attempt
rows, and output artifact paths.
Each iteration round should append a compact proposal outcome to
`experiments/memory.jsonl` so later runs and different modifier backends can
reuse prior proposal outcomes.
Before applying a patch, the loop should reject patch hashes that have already
failed at least `memory_filter.failed_patch_threshold` times in outcome memory.
It should also reject direction tags that have already failed at least
`memory_filter.failed_direction_threshold` times in outcome memory.
When `memory_filter.fallback_modifiers` is set, the loop may route through
multiple fallback candidates in the same round. Record each primary/fallback
attempt in `proposal_attempts.json` and select only a candidate that is
applicable, not rejected by outcome memory, and highest scored among candidates
by cheap pre-backtest metadata.
Candidate attempts should include deterministic pre-backtest score metadata so
the selected proposal can be audited without relying on natural language
judgment.
Candidate scoring weights should come from the `candidate_selection` config
block and be written into both `manifest.json` and `proposal_attempts.json`.
Candidate scoring may include a bounded direction-history prior from
`experiments/memory.jsonl`. The prior should use only prior runs for the same
`direction_tag`, record its sample counts and score delta, and only affect
candidate ranking. It must not decide final acceptance.
Candidate scoring may also include a deterministic exploration bonus after a
configured no-improvement window. The bonus should apply only to low-sample
directions that were not selected in the recent no-improvement window, record
its trigger metadata, and only affect candidate ranking. It must not decide
final acceptance.
For selectable candidates, the loop may run a tiny probe evaluation copied from
the train split. Probe data must be written under the round directory, not under
`data/`, and each candidate's probe artifacts should be linked from
`proposal_attempts.json`.
Iteration runs should also maintain a run-level `candidate_leaderboard.json`
that aggregates candidate attempts, selected status, direction tags, direction
priors, exploration bonuses, probe deltas, and final validation deltas for
later agent context and search analysis.
`agent_context.md` should include prior rows from `candidate_leaderboard.json`
so future modifier backends can see selected candidates, scores, direction
priors, exploration bonuses, probe deltas, and validation deltas before
proposing the next patch.
The loop may stop with `stopped_no_improvement` when the configured exploration
window shows no selected candidate with sufficient probe or validation EV
improvement.

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

The policy gate should compare before and after validation metrics.

A patch should be accepted only if all required validation rules pass and the
configured holdout risk gate does not veto it.

Default V0.5 rules:

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

Iteration decisions may also include a `holdout_policy` object with the holdout
gate result, metrics, and active rules.

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
17. Proposal contract validation rejects malformed or disallowed agent output before apply.
18. Direction-history priors can influence candidate ranking without deciding acceptance.
19. Exploration bonuses can push low-sample directions after deterministic stalls.
20. Agent context is written as both markdown and `agent_context_v1` JSON.
21. Codex output can be parsed from structured proposal JSON or plain diff text.
22. Enabled Codex CLI subprocesses are rejected if they mutate files outside `strategies/current_strategy.py`.
23. Candidate-selection weights are configurable and recorded with attempts.
24. Agent I/O fixtures are written as `agent_io_input_v1` and `agent_io_output_v1` JSON.

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
6. Save `agent_context.md`, `agent_context.json`, `agent_input.json`, `agent_output.json`, `proposal.json`, `agent_response.txt`, and `patch.diff`.
7. Apply the patch with Git.
8. Run the modified strategy on all configured data splits.
9. Save train, validation, and holdout after metrics, trades, and reports.
10. Run the main policy gate on validation metrics.
11. Run the configured holdout risk gate as a deterministic veto.
12. Save `decision.json`.
13. Append proposal outcome memory to `experiments/memory.jsonl`.
14. Accept and commit if both gates pass.
15. Reject and roll back if either gate fails.
16. Stop with `stopped_repeated_proposal` if the rejected patch repeats a prior round.
17. Stop with `stopped_max_rounds` if max rounds is reached.
18. Save `manifest.json`.
19. Print a short final summary.

The configured modifier may also be `codex_dry_run`, `codex_cli_dry_run`,
`codex_cli`, or `file_protocol`. The `adaptive_stub` modifier is still
deterministic, but it should read `agent_context.md` and choose a different
fixed patch after prior failures. The `codex_cli` and `file_protocol` adapters
must default to `execute=false`; only an explicit config change may invoke a
subprocess. Enabled `file_protocol` commands must run in an isolated workspace
and only bring back the configured proposal output file. Subprocess fixtures
should be able to return either plain diffs or structured proposal JSON so the
external-process boundary remains testable without real Codex.

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
