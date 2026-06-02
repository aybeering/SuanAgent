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
python -m orchestrator.experiments unlock-checklist <run_id> --markdown
python -m orchestrator.experiments cockpit <run_id> --markdown
```

`iteration_loop` writes the final action dashboard and cockpit during closeout;
the inspection commands can also refresh or render those read-only views after
later operator artifacts are written. The standalone operator unlock checklist
and cockpit include Codex CLI startup preflight evidence as read-only views so
evidence gaps are visible without executing Codex. The checklist also includes
blocking navigation with related artifact paths and explicit command hints for
the operator to run manually. If a real Codex execute=true startup preflight is
blocked, the failed run still writes the checklist and summary navigation.

More commands and artifact details live in `docs/artifact_reference.md`.

The V0.5 prototype does not call exchanges, wallets, or external APIs.
