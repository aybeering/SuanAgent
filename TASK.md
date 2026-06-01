# TASK

Build only V0 of the self iterating strategy improvement system.

The implementation should be deterministic, testable, and small:

1. Run a baseline strategy on fixed validation data.
2. Run the current candidate strategy on the same validation data.
3. Generate trades, metrics, and markdown reports.
4. Compare metrics with a deterministic policy gate.
5. Write git-friendly experiment artifacts under `experiments/<run_id>/`.
6. Provide smoke tests for the backtester, reports, policy gate, and full loop.

Out of scope for V0:

- Multi-agent orchestration.
- Visual agents.
- Overfitting agents.
- Live trading.
- Real exchange, Polymarket, Binance, wallet, or network integrations.
