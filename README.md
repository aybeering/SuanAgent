# Self Iterating Strategy Agent V0.5

![CI](https://github.com/aybeering/SuanAgent/actions/workflows/ci.yml/badge.svg)

A small, deterministic prototype for evaluating and iterating strategy changes.

V0 runs a fixed validation dataset through a baseline strategy and the current
candidate strategy, writes metrics and markdown reports, and accepts or rejects
the candidate with a deterministic policy gate.

V0.5 adds a minimal self-iteration skeleton: a fixed strategy modifier stub
proposes a patch, the loop applies it, reruns validation, and then accepts or
rolls back the change through Git based on the same deterministic policy gate.

Default run settings live in `config/default.json`. The iteration loop uses
train data for the agent report, validation data for the main policy gate, and
holdout data for a conservative risk gate. By default, the iteration loop stops
early when an agent repeats a previously rejected patch.

The strategy interface contract is documented in
`docs/strategy_interface.md`. Machine-readable agent contracts live in
`schemas/agent_input.schema.json`, `schemas/agent_output.schema.json`,
`schemas/agent_validation.schema.json`, and `schemas/agent_execution.schema.json`;
planner intent, run provenance, and run-level research notes are described by
`schemas/proposal_intent.schema.json`, `schemas/run_metadata.schema.json`, and
`schemas/research_brief.schema.json`.
The current modifier backend is selected with `strategy_modifier` in config;
available values are `fixed_patch_stub`, `adaptive_stub`, `codex_dry_run`,
`codex_cli_dry_run`, `codex_cli`, and `file_protocol`. The `codex_cli` and
`file_protocol` adapters only invoke a subprocess when their `execute` flag is
explicitly set to `true`. Example configs live in `config/adaptive_stub.json`,
`config/codex_dry_run.json`, `config/codex_cli_guarded.json`,
`config/file_protocol_guarded.json`, and `config/file_protocol_demo.json`.
The `adaptive_stub` remains deterministic but now reads both same-run failures
and recent `research_brief` rows from `agent_context.json`; if recent research
shows failed `lower_min_edge` attempts, it shifts to a fixed `reduce_stake`
proposal. Dry-run Codex prompts and the demo file-protocol agent also consume
`proposal_intent.json`, so local stand-ins exercise the same planner handoff
that future SDK or CLI agents will use.
Enabled `file_protocol` commands run inside an isolated workspace and may only
bring back the configured proposal output file. Each file-protocol round writes
`agent_execution.json` with the command, workspace path, return code, output
hashes, stdout/stderr summaries, and mutation-guard result.
The demo file-protocol config executes `agents.file_protocol_demo_agent`, a
local deterministic command that exercises the same JSON contract without
calling Codex or any network service.

Codex-facing adapters use ignored `workspaces/<run_id>/<round_id>/` directories
for isolated project copies. Returned text can be a unified diff or structured
proposal JSON, and the extracted patch must touch only
`strategies/current_strategy.py`. When execution is enabled, the adapter also
hashes the isolated workspace before and after the subprocess and rejects the
proposal if any file outside `strategies/current_strategy.py` is added,
modified, or deleted.

GitHub Actions runs the deterministic smoke suite on every push and pull
request. The workflow uses `python -m pytest`, preflight validation, the
single-run loop, one dry-run iteration loop pass, and one adaptive-stub pass.

## Commands

```bash
pytest
python -m orchestrator.preflight
python -m orchestrator.run_loop
python -m orchestrator.iteration_loop
python -m orchestrator.experiments list --limit 5
python -m orchestrator.experiments summary
python -m orchestrator.experiments leaderboard --limit 5
python -m orchestrator.experiments memory --limit 5
python -m orchestrator.artifact_validator <run_id>
python -m orchestrator.experiments diagnose <run_id>
python -m orchestrator.experiments compare <base_run_id> <candidate_run_id>
python -m orchestrator.experiments champion
python -m orchestrator.experiments promote <base_run_id> <candidate_run_id>
python -m orchestrator.agent_replay experiments/<run_id>/round_001/agent_input.json
python -m orchestrator.agent_replay experiments/<run_id>/round_001/agent_input.json --validate
python -m orchestrator.agent_output_intake experiments/<run_id>/round_001/agent_input.json experiments/<run_id>/round_001/demo_agent_output.json --output experiments/<run_id>/round_001/agent_validation.json
```

Useful mode switches:

```bash
python -m orchestrator.iteration_loop --config config/codex_dry_run.json --run-id dry-run-demo
python -m orchestrator.iteration_loop --config config/adaptive_stub.json --run-id adaptive-demo
python -m orchestrator.iteration_loop --config config/codex_cli_guarded.json --run-id guarded-demo --max-rounds 1
python -m orchestrator.iteration_loop --config config/file_protocol_guarded.json --run-id file-protocol-demo --max-rounds 1
python -m orchestrator.iteration_loop --config config/file_protocol_demo.json --run-id file-protocol-local-demo --max-rounds 1
python -m orchestrator.iteration_loop --allow-repeated-proposals --run-id max-round-demo
python -m orchestrator.run_loop --config config/default.json --run-id single-run-demo
python -m orchestrator.preflight --config config/codex_cli_guarded.json
python -m orchestrator.experiments show dry-run-demo
python -m orchestrator.artifact_validator file-protocol-local-demo
python -m orchestrator.experiments diagnose file-protocol-local-demo
python -m orchestrator.experiments compare dry-run-demo adaptive-demo
python -m orchestrator.experiments promote dry-run-demo adaptive-demo
```

## Outputs

Each run writes artifacts to `experiments/<run_id>/`:

- `metrics_before.json`
- `metrics_after.json`
- `report_before.md`
- `report_after.md`
- `summary.md`
- `diagnosis.json`
- `run_metadata.json`
- `decision.json`
- `patch.diff`
- `trades_before.csv`
- `trades_after.csv`

The multi-round loop also writes per-round train and holdout artifacts, a
human-readable `summary.md`, a machine-readable `diagnosis.json`, and an
immutable `run_metadata.json` provenance snapshot, plus `research_brief.json`
and `research_brief.md` for deterministic run-level research notes. It also
updates append-only `experiments/index.jsonl`.
When a champion registry exists, completed iteration runs also write
`champion_comparison.json`.
Iteration summaries include proposal direction tags, hypotheses, expected
metric changes, risk notes, patch fingerprints, and repeat-patch detection.
Every candidate proposal must pass the deterministic `proposal_v1` contract
before patch checks or probe evaluation. Contract failures are recorded as
non-applicable proposals with `contract_errors`, so malformed agent output is
auditable but never applied.
Codex-style adapters can consume either a plain unified diff or a structured
JSON proposal containing `summary`, `risk_notes`, `direction_tag`,
`expected_metric_change`, `hypotheses`, and `patch_diff`; both forms flow
through the same deterministic contract validator.
Enabled Codex CLI subprocesses are also checked for hidden workspace side
effects: only `strategies/current_strategy.py` may change inside the isolated
workspace, and violations are recorded as contract errors.
Enabled file-protocol subprocesses are stricter: they may only write the
configured proposal output file inside the isolated workspace. Each run records
an `agent_execution.json` audit log so command execution and guard decisions can
be inspected without replaying the agent.
Timeouts, non-zero exits, malformed output, disallowed patch targets, and hidden
workspace mutations are all deterministic rejections; the strategy file remains
rolled back unless the policy gates accept a valid patch.
`agents.file_protocol_demo_agent` is the reference local command for this path:
it reads `agent_input.json` plus `proposal_intent.json`, writes structured
proposal JSON, and lets the loop perform the same patch parsing, validation,
backtest, policy gate, and rollback used for future SDK or CLI-backed agents.
Use `python -m orchestrator.agent_replay <agent_input.json>` to replay that
same demo agent offline from a saved round input. Replay writes only the
requested proposal JSON output and does not run backtests, apply patches, or
mutate strategy files. Add `--validate` to wrap the replayed proposal with
deterministic `proposal_v1` contract validation, including strategy-only patch
target checks, while still avoiding patch application.
Use `python -m orchestrator.agent_output_intake <agent_input.json> <agent_output>`
to validate any saved raw agent output before it can become a candidate patch.
The intake command normalizes JSON proposal output or plain unified diffs into
the `proposal_v1` shape, checks that only `strategies/current_strategy.py` is
targeted, runs `git apply --check`, and can write `agent_validation.json`.
Iteration status is one of `accepted`, `stopped_repeated_proposal`,
`stopped_max_rounds`, or `failed`.
The validation policy remains the primary acceptance rule, while the optional
`holdout_policy` can only veto a candidate when holdout EV, drawdown, slippage,
or trade count crosses configured risk limits.
Each round also writes `agent_context.md` and `agent_context.json`, two renders
of the same deterministic context payload. The markdown file is easy to inspect,
while the JSON file gives future Codex CLI or SDK-backed agents a stable
machine-readable view of prior rounds, candidate traces, outcome memory, and
the current champion when a champion registry exists. It also includes compact
`recent_research_briefs` rows from the latest completed iteration runs, so a
modifier backend can see recent observations and next questions without
re-parsing every artifact directory.
Each round also writes `proposal_intent.json` and `proposal_intent.md`, a thin
deterministic planner output that turns the context into a recommended
direction, directions to avoid, evidence, and hard constraints for the modifier.
Each round also writes `agent_input.json`, `agent_output.json`, and
`agent_validation.json`, stable fixtures that record what a modifier backend
was given, which proposal candidate was selected, and whether deterministic
intake checks passed before patch application.
Tests validate these artifacts against the JSON schemas under `schemas/`; the
proposal intent, agent validation report, and file-protocol execution audit are
validated against `schemas/proposal_intent.schema.json`,
`schemas/agent_validation.schema.json`, and `schemas/agent_execution.schema.json`;
run provenance is validated against `schemas/run_metadata.schema.json`.
Use `python -m orchestrator.artifact_validator <run_id>` to check that a run
directory has required files and that agent contract artifacts match their
schemas.
Use `python -m orchestrator.experiments diagnose <run_id>` for a compact JSON
diagnosis of artifact health, selected candidates, per-round EV deltas,
rejection reasons, and file-protocol execution status.
Each completed run writes the same diagnosis payload to `diagnosis.json` inside
the run directory.
Each run also writes `run_metadata.json` with the effective config snapshot,
resolved dataset paths, dataset SHA-256 fingerprints, strategy modifier
settings, and best-effort Git commit metadata for reproducibility.
Iteration runs append proposal outcomes to `experiments/memory.jsonl`, which is
used as cross-run context for later agent calls.
Before applying a patch, the loop checks outcome memory and rejects patch hashes
that have already failed at least `memory_filter.failed_patch_threshold` times.
It also rejects proposal directions that have failed at least
`memory_filter.failed_direction_threshold` times, so the prototype can avoid a
weak idea family even when the exact patch text changes.
If `memory_filter.fallback_modifiers` is configured, the same round can route
through a deterministic candidate list and select a proposal that is applicable,
not rejected by outcome memory, and highest scored among candidates by cheap
pre-backtest metadata.
Selectable candidates are scored with deterministic metadata from
`expected_metric_change`, risk notes, patch validity, duplicate patch hashes,
outcome-memory status, and a bounded direction-history prior before the loop
spends a validation backtest on one proposal. The direction prior uses prior
accepted counts and average validation EV deltas for the same `direction_tag`;
it only affects candidate ranking and never overrides the policy gate.
The `candidate_selection` config block controls the deterministic scoring
weights for expected metrics, risk notes, direction priors, exploration bonuses,
probe EV, probe trade count, and primary-modifier stability; the active weights
are written to `manifest.json` and each `proposal_attempts.json` row.
When `exploration.explore_after_no_improvement_rounds` is enabled, recent
no-improvement rounds can add a deterministic exploration bonus to low-sample
directions that were not selected in that recent window. This is an
explore/exploit ranking rule only; final acceptance still belongs to the policy
gate.
The scorer also writes a tiny per-round `probe_data.csv` copied from the train
split and runs selectable candidates against it before final selection, storing
`probe_<role>_metrics.json`, trades, and reports under the round directory.
Iteration runs also write `candidate_leaderboard.json`, a run-level search trace
that ranks all candidate attempts by selection status, direction tag, direction
prior, exploration bonus, probe deltas, validation deltas, and deterministic
candidate score. When a champion registry exists, candidate scoring also records
a capped champion-gap feature comparing each candidate's probe EV delta with the
current champion's validation EV delta.
Completed iteration runs also write `research_brief.json` and
`research_brief.md`, which compact the diagnosis, top candidates, selected
candidates, champion comparison, deterministic observations, and next research
questions into one auditable run summary.
Later rounds include prior rows from that leaderboard in `agent_context.md`, and
new runs include recent research brief rows, so modifier backends can avoid weak
search directions and reuse promising ones.
The optional `exploration.stop_after_no_improvement_rounds` policy can stop a
run when recent selected candidates fail to clear configured probe or validation
EV improvement thresholds.

Use `python -m orchestrator.experiments list` and
`python -m orchestrator.experiments show <run_id>` to inspect local experiment
history. Use `summary` and `leaderboard` to aggregate runs by status and rank
them by validation EV improvement. Use `compare <base_run_id>
<candidate_run_id>` to compare two runs, check dataset fingerprints, and emit a
deterministic promotion recommendation. Use `memory` to inspect recent proposal
outcome records. Use `candidates <run_id>` to inspect one iteration run's
candidate leaderboard. Use `promote <base_run_id> <candidate_run_id>` to write
`experiments/champion.json` and append `experiments/champion_history.jsonl`
only when compare recommends `promote_candidate`; use `champion` to inspect the
current registry. Once a champion exists, completed iteration runs also write
`champion_comparison.json` inside their run directory, comparing that run
against the current champion.

The V0.5 prototype does not call exchanges, wallets, or external APIs.
