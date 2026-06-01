# Strategy Interface Contract

V0.5 strategy-improvement agents may only modify:

```text
strategies/current_strategy.py
```

The strategy module must expose:

```python
def generate_orders(snapshot: MarketSnapshot) -> list[StrategyOrder]:
    ...
```

## Input

`snapshot` is a frozen `MarketSnapshot` from `backtester.schema`:

```python
MarketSnapshot(
    timestamp: str,
    market_id: str,
    yes_price: float,
    fair_value: float,
    outcome: int,
    liquidity: float,
    next_yes_price: float,
)
```

Strategies must treat snapshots as read-only.

## Output

The function must return a plain list of `StrategyOrder` objects. Each order must:

- use the same `market_id` as the snapshot
- use `side="YES"`
- have `0.0 < limit_price < 1.0`
- have `stake > 0.0`
- use finite numeric values
- be deterministic for the same input snapshot

Invalid outputs fail before simulation and are not scored.

## Boundaries

Strategy code must not:

- read or write files
- make network calls
- access credentials, wallets, exchanges, or external APIs
- mutate global state in a way that changes later decisions
- modify anything under `data/`, `backtester/`, or `orchestrator/`

The deterministic policy gate, not the strategy or agent, decides whether a
patch is accepted.
