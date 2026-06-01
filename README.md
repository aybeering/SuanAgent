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
train data for the agent report, validation data for the policy gate, and
holdout data for observation-only reports. By default, the iteration loop stops
early when an agent repeats a previously rejected patch.

The strategy interface contract is documented in
`docs/strategy_interface.md`. The current modifier backend is selected with
`strategy_modifier` in config; available values are `fixed_patch_stub`,
`adaptive_stub`, `codex_dry_run`, `codex_cli_dry_run`, and `codex_cli`. The
`codex_cli` adapter only invokes a subprocess when `codex_cli.execute` is
explicitly set to `true`. Example configs live in `config/adaptive_stub.json`,
`config/codex_dry_run.json`, and `config/codex_cli_guarded.json`.

Codex-facing adapters use ignored `workspaces/<run_id>/<round_id>/` directories
for isolated project copies. Returned text is parsed as a unified diff and must
touch only `strategies/current_strategy.py`.

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
```

Useful mode switches:

```bash
python -m orchestrator.iteration_loop --config config/codex_dry_run.json --run-id dry-run-demo
python -m orchestrator.iteration_loop --config config/adaptive_stub.json --run-id adaptive-demo
python -m orchestrator.iteration_loop --config config/codex_cli_guarded.json --run-id guarded-demo --max-rounds 1
python -m orchestrator.iteration_loop --allow-repeated-proposals --run-id max-round-demo
python -m orchestrator.run_loop --config config/default.json --run-id single-run-demo
python -m orchestrator.preflight --config config/codex_cli_guarded.json
python -m orchestrator.experiments show dry-run-demo
```

## Outputs

Each run writes artifacts to `experiments/<run_id>/`:

- `metrics_before.json`
- `metrics_after.json`
- `report_before.md`
- `report_after.md`
- `summary.md`
- `decision.json`
- `patch.diff`
- `trades_before.csv`
- `trades_after.csv`

The multi-round loop also writes per-round train and holdout artifacts, a
human-readable `summary.md`, and an append-only `experiments/index.jsonl`.
Iteration summaries include proposal direction tags, hypotheses, expected
metric changes, risk notes, patch fingerprints, and repeat-patch detection.
Iteration status is one of `accepted`, `stopped_repeated_proposal`,
`stopped_max_rounds`, or `failed`.
Each round also writes `agent_context.md`, a deterministic summary of prior
failed proposals and metric deltas that future agent backends can read before
creating the next patch.
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
and outcome-memory status before the loop spends a validation backtest on one
proposal.
The scorer also writes a tiny per-round `probe_data.csv` copied from the train
split and runs selectable candidates against it before final selection, storing
`probe_<role>_metrics.json`, trades, and reports under the round directory.
Iteration runs also write `candidate_leaderboard.json`, a run-level search trace
that ranks all candidate attempts by selection status, direction tag, probe
deltas, validation deltas, and deterministic candidate score.
Later rounds include prior rows from that leaderboard in `agent_context.md`, so
modifier backends can avoid weak search directions and reuse promising ones.
The optional `exploration.stop_after_no_improvement_rounds` policy can stop a
run when recent selected candidates fail to clear configured probe or validation
EV improvement thresholds.

Use `python -m orchestrator.experiments list` and
`python -m orchestrator.experiments show <run_id>` to inspect local experiment
history. Use `summary` and `leaderboard` to aggregate runs by status and rank
them by validation EV improvement. Use `memory` to inspect recent proposal
outcome records. Use `candidates <run_id>` to inspect one iteration run's
candidate leaderboard.

The V0.5 prototype does not call exchanges, wallets, or external APIs.
