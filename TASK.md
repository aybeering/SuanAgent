# TASK

Build only V0.5 of the self-iterating strategy improvement system.

The implementation should stay deterministic, auditable, and small. V0.5 is a
control-flow prototype, not the full multi-agent system.

## Current target

1. Run the current strategy on fixed train, validation, and holdout data.
2. Generate before metrics, trades, and markdown reports.
3. Build deterministic agent context, proposal intent, and role-readiness
   artifacts for future agent slots.
4. Call one active strategy modifier backend. The default is a deterministic
   stub; external adapters must remain guarded and config-driven.
5. Normalize the modifier output into the shared proposal contract.
6. Validate that the proposal patch only targets `strategies/current_strategy.py`.
7. Apply the patch only after deterministic contract and patch checks pass.
8. Re-run train, validation, and holdout evaluation.
9. Accept only when the validation policy gate passes and the holdout risk gate
   does not veto.
10. Commit accepted strategy changes; reject and roll back failed changes.
11. Stop on acceptance, repeated failed proposal, deterministic no-improvement
   stop, or the configured max-round limit.
12. Write git-friendly experiment artifacts under `experiments/<run_id>/`.

## Required smoke checks

```bash
pytest
python -m orchestrator.run_loop
python -m orchestrator.iteration_loop
python -m orchestrator.preflight --config config/default.json
```

Use `docs/contract_roadmap.md` for the detailed V0.5 contract and readiness
roadmap.

## Out of scope

- Real Codex CLI strategy execution.
- Full multi-agent architecture.
- Concurrent or distributed agent execution.
- Visual agents with routing authority.
- Overfitting agents with veto authority.
- Live trading.
- Real exchange, Polymarket, Binance, wallet, or network integrations.
