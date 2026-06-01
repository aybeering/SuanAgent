# Self Iterating Strategy Agent V0

A small, deterministic prototype for evaluating strategy changes.

V0 runs a fixed validation dataset through a baseline strategy and the current
candidate strategy, writes metrics and markdown reports, and accepts or rejects
the candidate with a deterministic policy gate.

## Commands

```bash
pytest
python -m orchestrator.run_loop
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
