# Self Iterating Strategy Agent V0

A small, deterministic prototype for evaluating and iterating strategy changes.

V0 runs a fixed validation dataset through a baseline strategy and the current
candidate strategy, writes metrics and markdown reports, and accepts or rejects
the candidate with a deterministic policy gate.

V0.5 adds a minimal self-iteration skeleton: a fixed strategy modifier stub
proposes a patch, the loop applies it, reruns validation, and then accepts or
rolls back the change through Git based on the same deterministic policy gate.

## Commands

```bash
pytest
python -m orchestrator.run_loop
python -m orchestrator.iteration_loop
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

The V0 prototype does not call exchanges, wallets, or external APIs.
