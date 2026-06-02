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
25. Saved attempt replay for contract and probe checks without a full loop rerun.
26. Stable failure taxonomy fields for decisions, attempts, validation, and replay.
27. A deterministic agent executor queue that assigns stable attempt ids before candidate selection.
28. Optional config-level agent profiles that name future isolated agent slots while still using deterministic adapters.
29. Profile-aware workspace and execution audit metadata for workspace-backed adapters.
30. Profile-aware agent input contracts for external CLI or SDK-backed agents.
31. Attempt-scoped agent input artifacts for candidate-level replay.
32. Role-level agent contracts that declare future blue-node responsibilities while only the strategy modifier executes.
33. Deterministic local `chart.html` and `trade_timeline.html` artifacts for round inspection, generated without visual agents or network calls.
34. A deterministic `visual_artifacts_manifest.json` that indexes visual inputs, source files, hashes, and visual authority policy.
35. A deterministic `agent_role_readiness.json` audit that reports which future agent roles are executable, blocked, or contract-only.
36. A deterministic `agent_activation_preflight.json` startup gate that verifies role/profile activation before iteration begins.
37. A deterministic `agent_execution_plan.json` round plan that records the candidate queue before any modifier is invoked.
38. A deterministic `round_replay.json` audit command that replays every saved planned attempt without rerunning the full loop.
39. Agent inspection output that summarizes round replay status for each saved round.
40. A deterministic `agent_slot_health.json` report that summarizes planned slot readiness, audits, and replay status.
41. A deterministic `agent_slot_readiness_gate.json` report that blocks future external agent slots until input, output, workspace, audit, and replay artifacts are present.
42. A deterministic `external_agent_sandbox_drill.json` report that audits external slot command, workspace, input, output, subprocess, and mutation-guard evidence without executing agents.
43. A unified `agent_execution.json` contract for guarded Codex CLI attempts, including disabled, completed, failed, timed-out, and mutation-guard outcomes.
44. A deterministic `agent_output_quarantine.json` report that quarantines selected agent output before git apply and releases only validated strategy patches.

Still out of scope:

1. Real Codex CLI integration.
2. Full multi-agent architecture.
3. Concurrent or distributed agent execution.
4. Visual agents.
5. HTML chart rendering agents.
6. Overfitting agents.
7. Live trading.
8. Real exchange, Polymarket, Binance, wallet, or network APIs.

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
├── schemas/
│   ├── agent_input.schema.json
│   ├── agent_bundle.schema.json
│   ├── agent_attempts.schema.json
│   ├── agent_selection.schema.json
│   ├── agent_executor.schema.json
│   ├── agent_output.schema.json
│   ├── agent_validation.schema.json
│   ├── agent_output_quarantine.schema.json
│   ├── agent_execution.schema.json
│   ├── agent_activation_preflight.schema.json
│   ├── agent_execution_plan.schema.json
│   ├── round_replay.schema.json
│   ├── agent_slot_health.schema.json
│   ├── agent_slot_readiness_gate.schema.json
│   ├── external_agent_sandbox_drill.schema.json
│   ├── agent_role_contracts.schema.json
│   ├── agent_role_readiness.schema.json
│   ├── analysis_notes.schema.json
│   ├── visual_artifacts_manifest.schema.json
│   ├── visual_review.schema.json
│   ├── overfit_validation.schema.json
│   ├── attempt_replay.schema.json
│   ├── agent_result_stats.schema.json
│   ├── workspace_manifest.schema.json
│   ├── champion.schema.json
│   ├── champion_comparison.schema.json
│   ├── proposal_intent.schema.json
│   ├── run_metadata.schema.json
│   └── research_brief.schema.json
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
│   ├── generate_report.py
│   ├── generate_chart.py
│   └── generate_timeline.py
├── orchestrator/
│   ├── run_loop.py
│   ├── iteration_loop.py
│   ├── agent_attempts.py
│   ├── agent_bundle.py
│   ├── agent_context.py
│   ├── agent_executor.py
│   ├── agent_output_intake.py
│   ├── agent_output_quarantine.py
│   ├── outcome_memory.py
│   ├── policy_gate.py
│   ├── proposal.py
│   ├── proposal_intent.py
│   ├── research_brief.py
│   ├── run_summary.py
│   ├── patch_parser.py
│   ├── workspace_manager.py
│   ├── agent_slot_readiness_gate.py
│   ├── external_agent_sandbox_drill.py
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
diagnosis.json
run_metadata.json
patch.diff
summary.md
trades_before.csv
trades_after.csv
```

The multi-round V0.5 loop writes:

```text
manifest.json
summary.md
diagnosis.json
run_metadata.json
agent_activation_preflight.json
agent_activation_preflight.md
agent_slot_health.json  # optional slot health audit
agent_slot_health.md    # optional slot health audit
research_brief.json
research_brief.md
champion_comparison.json  # when a champion registry exists
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
  proposal_intent.json
  proposal_intent.md
  agent_role_contracts.json
  analysis_notes.json
  analysis_notes.md
  visual_artifacts_manifest.json
  chart.html
  trade_timeline.html
  visual_review.json
  visual_review.md
  agent_execution_plan.json
  agent_execution_plan.md
  overfit_validation.json
  overfit_validation.md
  agent_role_readiness.json
  agent_role_readiness.md
  agent_input.json
  agent_bundle_manifest.json
  agent_input_bundle/
  agent_output_bundle/
  agent_output.json
  agent_validation.json
  agent_executor_report.json
  agent_attempts_manifest.json
  agent_selection_report.json
  round_replay.json   # optional replay audit
  round_replay.md     # optional replay audit
  agent_attempts/
  workspace_manifests/ # attempt-scoped workspace manifests
  agent_executions/    # attempt-scoped file-protocol audits
  workspace_manifest.json  # workspace-backed agents only
  proposal.json
  raw_agent_output.txt
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

Each completed iteration run should write `research_brief.json` and
`research_brief.md`. The JSON artifact should use schema version
`research_brief_v1` and compact the run diagnosis, selected candidates, top
candidate leaderboard rows, champion comparison summary, deterministic
observations, and next research questions.

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
outcome memory, current champion context when available, previous champion
comparison context when available, recent research brief summaries from
completed runs, target file, and policy notes for SDK-backed agents.
Each round should then write `proposal_intent.json` and `proposal_intent.md`
before calling the modifier. The JSON artifact should use schema version
`proposal_intent_v1` and summarize the recommended direction, directions to
avoid, evidence, source context artifacts, and hard constraints. It is planner
guidance only; it must not decide acceptance.
Each round should also write `agent_role_contracts.json`, `analysis_notes.json`,
`analysis_notes.md`, `visual_artifacts_manifest.json`, `chart.html`,
`trade_timeline.html`, `visual_review.json`, `visual_review.md`,
`agent_execution_plan.json`, `agent_execution_plan.md`,
`overfit_validation.json`, `overfit_validation.md`,
`agent_role_readiness.json`, `agent_role_readiness.md`,
`agent_input.json`, `agent_bundle_manifest.json`, `agent_input_bundle/`,
`agent_output_bundle/`, `raw_agent_output.txt`, `agent_output.json`,
`agent_validation.json`, `agent_executor_report.json`, `agent_routing_policy.json`,
`agent_attempts_manifest.json`, and `agent_attempts/`.
`agent_role_contracts.json` should use schema version
`agent_role_contracts_v1` and declare the planned agent responsibilities,
active roles, stub-only roles, disabled role topology, and the rule that
deterministic gates keep final acceptance authority. In V0.5, only
`strategy_modifier` should be active and implemented; `analysis`,
`visual_review`, and `overfit_validator` should remain disabled stub contracts.
`analysis_notes.json` should use schema version `analysis_notes_v1` and record
the read-only analysis stub's consumed reports, before metrics, observations,
and recommendation. It may advise continuing to the strategy modifier, but it
must not change routing or final acceptance.
`chart.html` should be a deterministic static HTML artifact generated by local
Python from before-trade files and before-metrics. It must not include external
scripts, external assets, or network calls.
`trade_timeline.html` should be a deterministic static HTML artifact generated
by local Python from before-trade files. It must not include external scripts,
external assets, or network calls.
`visual_artifacts_manifest.json` should use schema version
`visual_artifacts_manifest_v1` and index every visual artifact with its path,
format, schema marker, source files, byte count, SHA-256 digest, and the policy
that visual inputs cannot change routing or final acceptance.
`visual_review.json` should use schema version `visual_review_v1` and record
the read-only visual review stub's consumed `visual_artifacts_manifest.json`,
consumed `chart.html`, consumed `trade_timeline.html`, consumed before-trade
files, consumed before-reports, trade row counts, manifest-derived artifact
summaries, observations, and recommendation. The manifest-derived summaries
should include artifact ids, bytes, SHA-256 prefixes, source-file counts, and
visual authority policy. In V0.5 visual-agent execution must remain disabled,
and the artifact must not change routing or final acceptance.
`overfit_validation.json` should use schema version `overfit_validation_v1` and
record the overfit validator stub's consumed proposal, decision, metric deltas,
prior rejected round count, and advisory risk flags. In V0.5 it must not veto,
change routing, or change final acceptance.
`agent_activation_preflight.json` should use schema version
`agent_activation_preflight_v1` and be written at the iteration run root before
round execution. It validates effective roles, effective profiles, runner
capabilities, workspace contracts, and output contracts. In V0.5, startup must
fail if any enabled profile points at a non-`strategy_modifier` role or if the
runner/workspace/output contract does not match its adapter.
`agent_role_readiness.json` should use schema version
`agent_role_readiness_v1` and record each configured agent role's execution
mode, executable status, activation blockers, consumed artifacts, produced
artifacts, and authority flags. In V0.5, only `strategy_modifier` may be
executable; `analysis`, `visual_review`, and `overfit_validator` must remain
non-executable contract stubs with no routing, veto, or final acceptance
authority.
`agent_input.json` should use schema version `agent_io_input_v1` and describe
the reports, context, proposal intent, before metrics, policy config,
candidate-selection config, modifier list, configured agent roles, configured
agent profiles, and an `active_agent` task envelope. Round-level inputs should
keep `active_agent` empty as a template. Workspace-backed adapters should
rewrite the workspace copy of `agent_input.json` and its bundled copy with the
current attempt id, role, profile name, adapter name, agent name, expected
output filename, and workspace output path before invoking any external
process.
Each configured agent profile should include a normalized `runner` capability
block. In-process deterministic modifiers should use `runner_name` =
`in_process_modifier`; file-contract subprocesses should use `runner_name` =
`agent_contract_runner_v1`; the current guarded Codex CLI adapter should use
`runner_name` = `codex_cli_guarded_adapter`; Codex dry runs should use
`runner_name` = `workspace_dry_run`. The block should also record isolation
mode, execution flag, timeout, workspace root, output mode, and allowed output
filenames where relevant. Runner metadata should be copied into
`manifest.json`, `agent_input.json`, `agent_executor_report.json`,
`agent_execution_plan.json`, `agent_routing_policy.json`, `agent_output.json`,
`agent_attempts_manifest.json`,
`agent_selection_report.json`, and attempt-scoped `attempt_output.json`.
`agent_input_bundle/` should be created before calling the modifier and contain
the read-only files an external agent may inspect, including
`agent_role_contracts.json` and `analysis_notes.json`. `agent_output_bundle/`
should contain the output artifacts the orchestrator will inspect after the
modifier returns.
`agent_bundle_manifest.json` should use schema version
`agent_bundle_v1` and record both bundle directories plus file hashes.
`raw_agent_output.txt` should preserve the exact raw response text that will be
normalized into a proposal. For local stubs this can be the deterministic stub
response; for external agents it should be the subprocess output or configured
proposal output content.
`agent_output.json` should use schema
version `agent_io_output_v1` and record the selected proposal, compact attempt
rows, and output artifact paths, including `raw_agent_output.txt`.
`agent_validation.json` should use schema version `agent_validation_v1` and
record deterministic intake checks for the selected proposal, including
contract validity, strategy-only patch targeting, and `git apply --check`.
`agent_execution_plan.json` should use schema version `agent_execution_plan_v1`
and record the planned executor queue before any candidate modifier is invoked.
It should include attempt ids, queue roles, profile names, adapter names, agent
roles, runner capability blocks, expected workspace paths, allowed mutation
paths, input contracts, output contracts, and planned attempt artifacts. It is
plan-only: it must not execute agents, select candidates, or change final
acceptance.
`agent_executor_report.json` should use schema version `agent_executor_v1` and
record the deterministic execution queue, selected attempt id, per-attempt
modifier names, proposal metadata, runtime artifact paths, and normalized
executor config.
`agent_routing_policy.json` should use schema version
`agent_routing_policy_v1` and record the selected profile, adapter, runner,
deterministic rank policy, candidate-selection weights, candidate scores,
score reasons, skip reasons, routing priors, and links to attempt-level audit
files. It explains routing only; it must not override deterministic proposal
validation or the policy gate.
External command based adapters should use the shared
`agent_contract_runner_v1` path for subprocess execution, output copy-back,
workspace mutation checks, and `agent_execution.json` audit writing. Adapters
should prepare their workspace/input contract and translate the runner result
into a proposal, not reimplement command/audit logic independently.
`agent_attempts/` should contain one subdirectory per candidate attempt, each
with its own attempt payload, attempt-scoped `agent_input.json`,
`attempt_output.json`, proposal, raw output, patch, and any attempt-level
workspace or execution audit. Workspace backed attempts should preserve the
exact workspace-local `agent_input.json`; other attempts should synthesize the
same contract from the round input and attempt metadata. `attempt_output.json`
should use schema version `attempt_output_v1` and provide a compact audit
entry linking the attempt input, proposal, raw output, patch, selection
explanation, validation status, and optional workspace execution audit. The
`agent_attempts_manifest.json` artifact should use schema version
`agent_attempts_v1` and identify the selected attempt.
`agent_selection_report.json` should use schema version `agent_selection_v1`
and explain each attempt's eligibility, rank, score reasons, blocking reasons,
selection reason, or skip reason.
`round_replay.json` should use schema version `round_replay_v1` when the
optional replay command is run. It should compare `agent_execution_plan.json`
with `agent_attempts_manifest.json`, replay every saved attempt through the
existing deterministic attempt replay contract, and write a round-level summary
without executing agents, selecting candidates, or applying a final strategy
patch.
`agent_slot_health.json` should use schema version `agent_slot_health_v1` when
the optional slot health command is run. It should summarize preflight status,
planned attempts, saved attempt manifests, workspace/execution audits, and
round replay status without calling agents or changing acceptance.
The machine-readable contracts for these files live in `schemas/`. Run-level
metadata should write `run_metadata.json`, include resolved dataset paths and
dataset SHA-256 fingerprints, use schema version `run_metadata_v1`, and match
`schemas/run_metadata.schema.json`. Workspace-backed agent attempts should write
attempt-scoped manifests under `workspace_manifests/`, publish the selected
attempt as `workspace_manifest.json`, use schema version `workspace_manifest_v1`,
and record the profile name, adapter name, attempt id, isolated workspace path,
copied project surface, initial snapshot digest, and allowed mutation paths.
Workspace paths should include both profile and attempt segments:
`workspaces/<run_id>/<round_id>/<profile>/<attempt_id>/strategy_workspace/`.
File-protocol attempts
should write attempt-scoped execution audits under `agent_executions/`, publish
the selected attempt as `agent_execution.json`, include profile and adapter
metadata, use schema version `agent_execution_v1`, and match
`schemas/agent_execution.schema.json`.
File-protocol execution status should be one of `disabled`, `completed`,
`command_failed`, `timeout`, or `workspace_violation`. Timeouts, command
failures, malformed output, disallowed patch targets, and workspace side effects
must be auditable deterministic rejections.
Each iteration round should append a compact proposal outcome to
`experiments/memory.jsonl` so later runs and different modifier backends can
reuse prior proposal outcomes.
Before applying a patch, the loop should reject patch hashes that have already
failed at least `memory_filter.failed_patch_threshold` times in outcome memory.
It should also reject direction tags that have already failed at least
`memory_filter.failed_direction_threshold` times in outcome memory.
When `memory_filter.fallback_modifiers` is set, the loop may route through
multiple fallback candidates in the same round. Candidate invocation should go
through the deterministic agent executor queue, which assigns stable attempt ids
before adapter execution. Record each primary/fallback attempt in
`proposal_attempts.json` and select only a candidate that is applicable, not
rejected by outcome memory, and highest scored among candidates by cheap
pre-backtest metadata.
Configs may alternatively define an explicit `agents` list. Each enabled profile
should have a unique `name`, an adapter name, a `primary` or `fallback` role, and
optional adapter settings. Exactly one enabled profile must be primary. Disabled
profiles should remain visible in run manifests but must not enter the execution
queue. If no explicit `agents` list is present, derive audit profiles from
`strategy_modifier` and `memory_filter.fallback_modifiers`.
Configs may also define `agent_roles`; when omitted, use the default role
contracts. Roles describe architectural responsibilities, while profiles
describe concrete execution slots. Do not execute analysis, visual review, or
overfit validation roles in V0.5.
Each configured profile may include `agent_role`. Enabled profiles must point at
the active implemented role, currently `strategy_modifier`; disabled profiles
may point at future stub roles for manifest visibility. Attempt, executor,
selection, routing, and output artifacts should preserve both the queue `role`
(`primary`, `fallback_01`, etc.) and the architectural `agent_role`.
Executor calls should pass profile metadata to modifiers so workspace-backed
adapters can isolate future blue agent slots even when they share the same
underlying adapter.
The `executor` config block should remain deterministic. In V0.5, `mode` must
be `sequential`; `max_candidates` may cap the queue; `per_agent_timeout_seconds`
is audit metadata for future adapters; and `allow_disabled_adapters` records
whether guarded disabled adapters are allowed to participate.
Candidate attempts should include deterministic pre-backtest score metadata so
the selected proposal can be audited without relying on natural language
judgment.
Candidate scoring weights should come from the `candidate_selection` config
block and be written into both `manifest.json` and `proposal_attempts.json`.
Executor settings should be written into `manifest.json` and
`agent_executor_report.json`.
Candidate scoring may include a bounded direction-history prior from
`experiments/memory.jsonl`. The prior should use only prior runs for the same
`direction_tag`, record its sample counts and score delta, and only affect
candidate ranking. It must not decide final acceptance.
Candidate scoring may include a conservative routing prior from prior
`agent_result_stats.json` artifacts. The prior should match on `agent_name` and
`direction_tag`, record prefer/downweight counts and score delta, and only
affect candidate ranking. It must not decide final acceptance.
Candidate scoring may also include a deterministic exploration bonus after a
configured no-improvement window. The bonus should apply only to low-sample
directions that were not selected in the recent no-improvement window, record
its trigger metadata, and only affect candidate ranking. It must not decide
final acceptance.
Candidate scoring may also include a capped champion-gap feature when
`experiments/champion.json` exists. This feature compares the candidate's probe
EV delta with the current champion's validation EV delta, records the gap in
`proposal_attempts.json` and `candidate_leaderboard.json`, and only affects
candidate ranking. It must not decide final acceptance.
For selectable candidates, the loop may run a tiny probe evaluation copied from
the train split. Probe data must be written under the round directory, not under
`data/`, and each candidate's probe artifacts should be linked from
`proposal_attempts.json`.
Iteration runs should also maintain a run-level `candidate_leaderboard.json`
that aggregates candidate attempts, selected status, direction tags, direction
priors, exploration bonuses, probe deltas, and final validation deltas for
later agent context and search analysis.
Iteration runs should also maintain `agent_result_stats.json`, aggregating the
candidate leaderboard by agent name, direction tag, and patch hash family. This
artifact should preserve top failure codes and conservative routing hints for
future multi-agent downweighting or preference logic.
`agent_context.md` should include prior rows from `candidate_leaderboard.json`
so future modifier backends can see selected candidates, scores, direction
priors, exploration bonuses, probe deltas, and validation deltas before
proposing the next patch.
New runs should also include recent `research_brief.json` summaries in
`agent_context.md` and `agent_context.json`, limited to a small deterministic
window, so future SDK-backed agents can use recent observations and next
questions without scanning every experiment artifact.
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
16. Isolated workspaces copy the minimal project without `.git`, are scoped per attempt id, and publish the selected `workspace_manifest.json`.
17. Proposal contract validation rejects malformed or disallowed agent output before apply.
18. Direction-history priors can influence candidate ranking without deciding acceptance.
19. Exploration bonuses can push low-sample directions after deterministic stalls.
20. Agent context is written as both markdown and `agent_context_v1` JSON.
21. Codex output can be parsed from structured proposal JSON or plain diff text.
22. Enabled Codex CLI subprocesses are rejected if they mutate files outside `strategies/current_strategy.py`.
23. Candidate-selection weights are configurable and recorded with attempts.
24. Agent I/O fixtures are written as `agent_io_input_v1` and `agent_io_output_v1` JSON.
25. Agent role readiness is written as `agent_role_readiness_v1` JSON and keeps non-strategy roles non-executable in V0.5.
26. Agent activation preflight is written as `agent_activation_preflight_v1` JSON and blocks invalid enabled role/profile wiring before iteration starts.
27. Agent execution planning is written as `agent_execution_plan_v1` JSON before candidate modifiers run.
28. Round replay can replay every saved planned attempt and validate the resulting `round_replay_v1` artifact.
29. Experiment agent inspection reports round replay presence, counts, and per-attempt plan/manifest alignment.
30. Agent slot health reports identify healthy, unreplayed, blocked, and audit-missing agent slots.

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
python -m orchestrator.artifact_validator <run_id>
python -m orchestrator.experiments diagnose <run_id>
python -m orchestrator.experiments agents <run_id>
python -m orchestrator.experiments slots <run_id>
python -m orchestrator.experiments compare <base_run_id> <candidate_run_id>
python -m orchestrator.experiments champion
python -m orchestrator.experiments promote <base_run_id> <candidate_run_id>
python -m orchestrator.agent_replay experiments/<run_id>/round_001/agent_input.json
python -m orchestrator.agent_replay experiments/<run_id>/round_001/agent_input.json --validate
python -m orchestrator.attempt_replay experiments/<run_id>/round_001/agent_attempts/attempt_001_primary
python -m orchestrator.round_replay experiments/<run_id>/round_001
python -m orchestrator.agent_slot_health experiments/<run_id>
python -m orchestrator.agent_output_intake experiments/<run_id>/round_001/agent_input.json experiments/<run_id>/round_001/demo_agent_output.json --output experiments/<run_id>/round_001/agent_validation.json
```

## Expected behavior

When the V0.5 loop runs, it should:

1. Create a new run directory under `experiments/`.
2. Create per-round directories under that run.
3. Save `agent_activation_preflight.json` and stop before round execution if enabled agent wiring is invalid.
4. Run the current strategy before modification on all configured data splits.
5. Save train, validation, and holdout before metrics, trades, and reports.
6. Call the fixed strategy modifier stub using the train report.
7. Save `agent_context.md`, `agent_context.json`, `proposal_intent.json`, `proposal_intent.md`, `agent_input.json`, `agent_execution_plan.json`, `agent_execution_plan.md`, `raw_agent_output.txt`, `agent_output.json`, `agent_validation.json`, `agent_executor_report.json`, `proposal.json`, `agent_response.txt`, and `patch.diff`.
8. Apply the patch with Git only after deterministic agent-output validation passes.
9. Run the modified strategy on all configured data splits.
10. Save train, validation, and holdout after metrics, trades, and reports.
11. Run the main policy gate on validation metrics.
12. Run the configured holdout risk gate as a deterministic veto.
13. Save `decision.json`.
14. Save `overfit_validation.json`, `overfit_validation.md`, `agent_role_readiness.json`, and `agent_role_readiness.md`.
15. Append proposal outcome memory to `experiments/memory.jsonl`.
16. Accept and commit if both gates pass.
17. Reject and roll back if either gate fails.
18. Stop with `stopped_repeated_proposal` if the rejected patch repeats a prior round.
19. Stop with `stopped_max_rounds` if max rounds is reached.
20. Save `manifest.json`.
21. Save `summary.md`, `diagnosis.json`, and the research brief artifacts.
22. Print a short final summary.

The configured modifier may also be `codex_dry_run`, `codex_cli_dry_run`,
`codex_cli`, or `file_protocol`. The `adaptive_stub` modifier is still
deterministic, but it should read `agent_context.md` / `agent_context.json` and
choose a different fixed patch after prior failures or recent research briefs
that flag a weak direction. Dry-run Codex prompts and file-protocol demo agents
should consume `proposal_intent.json` so future CLI or SDK agents receive one
compact planner handoff. The `codex_cli` and `file_protocol` adapters must
default to `execute=false`; only an explicit config change may invoke a
subprocess. Workspace-backed agents must write attempt-scoped workspace
manifests before proposal application so the copied files, initial snapshot
digest, attempt id, and mutation policy are auditable. Enabled `file_protocol`
commands must run in an isolated attempt workspace and only bring back the
configured proposal output file. Subprocess fixtures should be able to return
either plain diffs or structured proposal JSON so the external-process boundary
remains testable without real Codex.

CLI entrypoints must support `--config` and `--run-id` so experiments can switch
between modes without editing `config/default.json`.

Run preflight before experiment execution. It must fail fast on missing data
paths, unsupported modifiers, invalid policy config, or enabled Codex execution
without an available executable.

Experiment inspection commands should read `experiments/index.jsonl` and local
run artifacts without mutating strategy code. Leaderboards should rank by
validation EV improvement, not natural-language judgment. The agent inspection
command should include aggregate candidate stats and any available round replay
status so planned, saved, and replayed attempt traces can be inspected from one
entrypoint. The slot inspection command should report whether each planned
agent slot is activation-ready, saved, workspace-audited, execution-audited,
and replayed.
Agent replay commands should read saved `agent_input.json` and
`proposal_intent.json` artifacts, emit deterministic proposal JSON, and must
not apply patches, run backtests, or mutate strategy files. A validate mode may
check replayed output against the `proposal_v1` contract and patch-target rules
without applying the patch.
Agent output intake commands should accept a saved `agent_input.json` plus a
raw agent output file, normalize it into a proposal, run the same deterministic
contract and `git apply --check` validation, and write `agent_validation.json`.
Attempt replay commands should accept one saved `agent_attempts/attempt_xxx`
directory, rerun deterministic contract validation, optionally evaluate the
patch on saved probe data, write `attempt_replay.json`, and leave
`strategies/current_strategy.py` rolled back to HEAD.
Round replay commands should accept one saved round directory, compare the
execution plan with the attempt manifest, replay every saved attempt through
the attempt replay path, write `round_replay.json` and `round_replay.md`, and
leave `strategies/current_strategy.py` rolled back to HEAD. They must not call
agents, rerun candidate selection, or change acceptance decisions.
Agent slot health commands should accept one saved run directory, inspect
preflight, plan, attempt, workspace, execution, and replay artifacts, write
`agent_slot_health.json` and `agent_slot_health.md`, and remain inspection-only.
Failure classification should remain machine-readable and stable. Preserve the
human-readable `reasons` text, but add or maintain `reason_codes`,
`failure_stage`, `failure_code`, and `failure_message` for contract, memory,
patch, probe, policy-gate, holdout-gate, and selection failures.
Codex CLI output conversion should use the shared intake normalization path for
both structured proposal JSON and plain unified diff output; do not add a second
Codex-only parser for patch extraction or proposal metadata.
Run comparison should use deterministic metrics and dataset fingerprints. A
candidate should only receive a promotion recommendation when artifacts are
valid, compared dataset fingerprints match, validation EV delta improves beyond
the configured threshold, and the candidate run was accepted by its own policy
gate.
Champion promotion should write `experiments/champion.json` using schema
version `champion_v1` and append `experiments/champion_history.jsonl`. Promotion
must only happen when deterministic comparison recommends `promote_candidate`;
failed or inconclusive comparisons should not mutate the champion registry.
When a champion registry exists, completed iteration runs should write
`champion_comparison.json` in the run directory using schema version
`champion_comparison_v1`.
Completed iteration runs should then write `research_brief.json` and
`research_brief.md` so the candidate search trace is easy to inspect before the
next run.

Future Codex output must be normalized through agent output intake and rejected
before git apply if it touches anything except `strategies/current_strategy.py`.

## Important constraint

Do not overbuild.

V0.5 should be boring, deterministic, testable, and easy to debug.
