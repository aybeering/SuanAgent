# Self Iterating Strategy Agent V0.5

![CI](https://github.com/aybeering/SuanAgent/actions/workflows/ci.yml/badge.svg)

A small, deterministic prototype for evaluating and iterating strategy changes.

V0 runs a fixed validation dataset through a baseline strategy and the current
candidate strategy, writes metrics and markdown reports, and accepts or rejects
the candidate with a deterministic policy gate.

V0.5 adds a minimal self-iteration skeleton: a fixed strategy modifier stub
or guarded adapter proposes a patch, the loop validates it, applies it, reruns
train/validation/holdout evaluation, and then accepts or rolls back the change
through Git based on deterministic gates.

Default run settings live in `config/default.json`. The iteration loop uses
train data for the agent report, validation data for the main policy gate, and
holdout data for a conservative risk gate. By default, the iteration loop stops
early when an agent repeats a previously rejected patch.

GitHub Actions runs the deterministic smoke suite on every push and pull
request. The workflow uses `python -m pytest`, preflight validation, the
single-run loop, one dry-run iteration loop pass, and one adaptive-stub pass.

## Documentation

- `TASK.md` defines the current V0.5 target and smoke checks.
- `AGENTS.md` defines repository rules for coding agents.
- `docs/architecture.md` explains the loop, roles, workspaces, executor, memory,
  and champion registry.
- `docs/artifact_reference.md` indexes commands, generated artifacts, replay
  tools, and validators.
- `docs/codex_cli_readiness.md` explains the guarded Codex CLI evidence chain.
- `docs/contract_roadmap.md` tracks the detailed V0.5 contract roadmap.
- `docs/strategy_interface.md` documents what strategy code may change.
- `schemas/` contains the machine-readable JSON contracts.

## Commands

```bash
pytest
python -m orchestrator.preflight
python -m orchestrator.run_loop
python -m orchestrator.iteration_loop
```

Useful mode switches:

```bash
python -m orchestrator.iteration_loop --config config/codex_dry_run.json --run-id dry-run-demo
python -m orchestrator.iteration_loop --config config/adaptive_stub.json --run-id adaptive-demo
python -m orchestrator.iteration_loop --config config/codex_cli_guarded.json --run-id guarded-demo --max-rounds 1
python -m orchestrator.iteration_loop --config config/file_protocol_guarded.json --run-id file-protocol-demo --max-rounds 1
python -m orchestrator.iteration_loop --config config/file_protocol_demo.json --run-id file-protocol-local-demo --max-rounds 1
```

Useful inspection:

```bash
python -m orchestrator.experiments review <run_id> --markdown
python -m orchestrator.experiments action-plan <run_id> --markdown
python -m orchestrator.experiments action-approval <run_id> --markdown
python -m orchestrator.experiments action-execution <run_id> --markdown
python -m orchestrator.experiments action-audit <run_id> --markdown
python -m orchestrator.experiments action-dashboard <run_id> --markdown
python -m orchestrator.experiments action-guide <run_id> --markdown
python -m orchestrator.experiments config-runbook <run_id> --markdown
python -m orchestrator.experiments unlock-checklist <run_id> --markdown
python -m orchestrator.experiments unlock-runbook <run_id> --markdown
python -m orchestrator.experiments execution-readiness-diff <run_id> --markdown
python -m orchestrator.experiments cockpit <run_id> --markdown
python -m orchestrator.experiments home <run_id> --markdown
python -m orchestrator.experiments home --latest --markdown
```

`iteration_loop` writes the config operator runbook, final action dashboard,
operator unlock checklist, Codex CLI execution readiness diff, and cockpit
during closeout; the inspection commands can also refresh or render those
read-only views after later operator artifacts are written. The standalone
operator unlock checklist and cockpit
include Codex CLI startup preflight evidence as read-only views so evidence gaps
are visible without executing Codex. The checklist also includes blocking
navigation with related artifact paths and explicit command hints for the
operator to run manually. The config operator runbook turns the config
candidate, review, dry-run, guarded apply, rollback preview, guarded restore,
and lineage chain into an ordered read-only guide without executing commands or
writing config. The cockpit inspection command also reports whether
the saved cockpit source hashes are stale, so operators can refresh the cockpit
after updating readiness artifacts. `python -m orchestrator.experiments
refresh-operator-views <run_id>` refreshes the read-only operator dashboard,
Codex CLI preflight, unlock checklist, readiness diff, and cockpit in
dependency order without executing agents or changing acceptance. Its
terminal-only receipt records both pre-refresh stale source evidence and the
post-refresh cockpit freshness summary, including the primary current blocker
when one remains, a compact refresh-effect status, before/after blocker delta
counts, whether operator review is still required, primary review reason codes,
the action execution-readiness status, action path-closure status and step
counts, the digest headline, reason, and boundary classification for the first
recommended command, and a compact safety-policy summary. The terminal receipt
is schema-validated before printing, but it does not create another artifact
family. `action-guide <run_id>` is the terminal-only guided path
for the same operator action chain: it tells the operator whether approval,
guarded read-only execution, audit refresh, or dashboard review is next, while
remaining a hint-only view. It also includes a four-step guided checklist for
audit refresh, approval, guarded execution, and dashboard review.
`home <run_id>` is the terminal-only operator landing page: it combines run
outcome, cockpit review priority, the action guide checklist, Codex CLI
preflight/readiness-diff/intake-binding status, next-command hint, blockers,
and compact command-center rows without recording approval, executing commands,
running agents, running backtests, writing config, promoting champions,
applying patches, routing agents, or changing acceptance.
If no run id is provided, `home` resolves the latest indexed iteration run; use
`--latest` to make that selection explicit.
If a real Codex execute=true startup preflight is blocked, the failed run still writes
the checklist, execution readiness diff, and summary navigation. The Codex CLI
unlock runbook turns the same evidence chain into an ordered read-only operator
guide; it lists the required artifacts and command hints but does not execute
commands or unlock Codex. The execution
readiness diff compares the current config-derived command, workspace, mutation
boundary, dry-run plan, and operator-reviewed request so missing evidence or
drift is visible in both the diff and cockpit before any real Codex execution is
considered.

More commands and artifact details live in `docs/artifact_reference.md`.

The V0.5 prototype does not call exchanges, wallets, or external APIs.
