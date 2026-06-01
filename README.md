# Self Iterating Strategy Agent V0.5

A small, deterministic prototype for evaluating and iterating strategy changes.

V0 runs a fixed validation dataset through a baseline strategy and the current
candidate strategy, writes metrics and markdown reports, and accepts or rejects
the candidate with a deterministic policy gate.

V0.5 adds a minimal self-iteration skeleton: a fixed strategy modifier stub
proposes a patch, the loop applies it, reruns validation, and then accepts or
rolls back the change through Git based on the same deterministic policy gate.

Default run settings live in `config/default.json`. The iteration loop uses
train data for the agent report, validation data for the policy gate, and
holdout data for observation-only reports.

The strategy interface contract is documented in
`docs/strategy_interface.md`. The current modifier backend is selected with
`strategy_modifier` in config; available values are `fixed_patch_stub`,
`codex_dry_run`, `codex_cli_dry_run`, and `codex_cli`. The `codex_cli` adapter
only invokes a subprocess when `codex_cli.execute` is explicitly set to `true`.
Example configs live in `config/codex_dry_run.json` and
`config/codex_cli_guarded.json`.

Codex-facing adapters use ignored `workspaces/<run_id>/<round_id>/` directories
for isolated project copies. Returned text is parsed as a unified diff and must
touch only `strategies/current_strategy.py`.

## Commands

```bash
pytest
python -m orchestrator.run_loop
python -m orchestrator.iteration_loop
```

Useful mode switches:

```bash
python -m orchestrator.iteration_loop --config config/codex_dry_run.json --run-id dry-run-demo
python -m orchestrator.iteration_loop --config config/codex_cli_guarded.json --run-id guarded-demo --max-rounds 1
python -m orchestrator.run_loop --config config/default.json --run-id single-run-demo
```

## Outputs

Each run writes artifacts to `experiments/<run_id>/`:

- `metrics_before.json`
- `metrics_after.json`
- `report_before.md`
- `report_after.md`
- `decision.json`
- `patch.diff`
- `trades_before.csv`
- `trades_after.csv`

The multi-round loop also writes per-round train and holdout artifacts plus an
append-only `experiments/index.jsonl`.

The V0.5 prototype does not call exchanges, wallets, or external APIs.
