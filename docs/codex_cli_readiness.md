# Codex CLI Readiness

Real Codex CLI strategy execution is still out of scope for V0.5. The repository
currently builds deterministic evidence so a future operator can review the
command, workspace, mutation boundary, and source artifacts before any real
execution is considered.

## Boundary

Allowed in V0.5:

- Guarded dry-run adapters.
- Local canary execution through the guarded path.
- Read-only readiness gates.
- Operator intent artifacts.
- Startup preflight checks.
- Artifact validation of source hashes, canonical paths, command digests, run
  identity, workspace identity, and planned execution identity.

Not allowed in V0.5:

- Sending a real strategy prompt to Codex CLI.
- Applying a real Codex-produced patch.
- Letting a Codex response decide acceptance.
- Mutating config or data through the readiness pipeline.
- Reusing an operator request across unrelated runs.

## Readiness Chain

The read-only chain is:

1. `codex_cli_replay_gate.json`
2. `codex_cli_enablement_gate.json`
3. `codex_cli_manual_approval.json`
4. `codex_cli_canary_gate.json`
5. `codex_cli_real_preflight.json`
6. `codex_cli_dry_invocation_guard.json`
7. `codex_cli_execution_unlock_gate.json`
8. `codex_cli_execution_unlock_snapshot.json`
9. `codex_cli_execution_candidate.json`
10. `codex_cli_real_execution_dry_run.json`
11. `codex_cli_readiness_summary.json`
12. `codex_cli_readiness_pipeline.json`
13. `codex_cli_operator_unlock_request.json`
14. `codex_cli_execution_preflight.json`

The pipeline can summarize these artifacts, but it must not execute Codex,
create a real execution workspace, send a strategy prompt, apply patches, or
change acceptance.

## Canonical Source Binding

Codex readiness artifacts are validated as a source chain, not as isolated JSON
files. The artifact validator checks that key source records point to canonical
files inside the same run directory and that the recorded hashes still match.

Important canonical bindings include:

- `codex_cli_execution_unlock_snapshot.json` must source the canonical
  `codex_cli_execution_unlock_gate.json`.
- `codex_cli_execution_candidate.json` must source the canonical
  `codex_cli_execution_unlock_snapshot.json`.
- `codex_cli_real_execution_dry_run.json` must source the canonical
  `codex_cli_execution_candidate.json`.
- `codex_cli_operator_unlock_request.json` must be stored as the canonical
  artifact in the current run directory and must source the canonical
  readiness pipeline and real-execution dry-run artifacts.

This prevents a run from substituting an alias file with the same content hash
but a different reviewed artifact path.

## Command Digest Binding

Guarded Codex CLI attempts record a stable `command_sha256`. Startup preflight
and artifact validation bind that digest to the operator-reviewed command for
the same profile, attempt id, round id, workspace path, and run id.

If any of these change, execution remains blocked:

- command
- candidate config hash
- run id
- run directory
- profile name
- agent name
- round id
- attempt id
- reviewed workspace path
- source evidence hashes
- source evidence paths
- operator intent fields

## Operator Request

`codex_cli_operator_unlock_request.json` records explicit operator intent. It is
read-only and includes policy checks proving that the request itself does not:

- Execute Codex CLI.
- Send a strategy prompt.
- Create a workspace.
- Apply patches.
- Select a candidate.
- Change final acceptance.
- Modify config.

The request must include the expected confirmation phrase hash and operator id.
It may still be `operator_request_ready=false` when upstream readiness evidence
is blocked; this is valid audit output, not execution permission.

## Startup Preflight

`codex_cli_execution_preflight.json` blocks real Codex CLI execution unless a
ready canonical operator request already exists in the current run directory and
still matches the active profile command, workspace prefix, run identity, source
hashes, and planned execution identity.

The iteration loop allows an existing run directory only for this narrow
canonical operator-request startup case. Ordinary pre-existing run directories
remain blocked to avoid accidental artifact overwrite.

## Useful Commands

Run a guarded audit iteration:

```bash
python -m orchestrator.iteration_loop --config config/codex_cli_guarded.json --run-id guarded-demo --max-rounds 1
```

Run a local canary iteration:

```bash
python -m orchestrator.iteration_loop --config config/codex_cli_canary.json --run-id canary-demo --max-rounds 1
python -m orchestrator.codex_cli_canary_gate experiments/canary-demo --config config/codex_cli_canary.json
```

Run the read-only readiness pipeline:

```bash
python -m orchestrator.codex_cli_readiness_pipeline experiments/guarded-demo --config config/codex_cli_enable_candidate.json --canary-run-dir experiments/canary-demo --approved --approved-by local-review --confirmation-phrase "I approve this Codex CLI candidate for manual enablement"
```

Generate the read-only unlock runbook:

```bash
python -m orchestrator.codex_cli_unlock_runbook experiments/guarded-demo
python -m orchestrator.experiments unlock-runbook guarded-demo --markdown
```

The runbook orders the required readiness, candidate, dry-run, and operator
request artifacts into a manual review guide. It only reads saved artifacts and
prints command hints; it does not execute Codex, record approval, create
workspaces, apply patches, or change acceptance.

Generate the read-only execution readiness drift audit:

```bash
python -m orchestrator.codex_cli_execution_readiness_diff experiments/guarded-demo --config config/codex_cli_enable_candidate.json
python -m orchestrator.experiments execution-readiness-diff guarded-demo --markdown
```

The diff compares the current config-derived command, command digest, workspace
path, mutation boundary, startup preflight expectation, execution candidate,
real-execution dry-run, and operator request. It reports `matched`, `missing`,
or `drift` rows only; it does not execute commands, execute Codex, record
approval, create workspaces, modify config, apply patches, or change
acceptance. Completed iteration runs now write this diff automatically during
closeout, and failed execute=true startup preflight runs write it before
returning the deterministic startup error. The operator cockpit includes a
read-only readiness diff panel so missing evidence or drift is visible from the
main operator page.

Refresh operator-facing views after writing later readiness evidence:

```bash
python -m orchestrator.experiments refresh-operator-views guarded-demo
```

The refresh command rewrites the read-only operator action dashboard, Codex CLI
execution preflight, unlock checklist, readiness diff, and cockpit in dependency
order. It uses the run's recorded config path unless `--config` is provided and
returns a terminal-only receipt; it does not execute Codex, record approval,
create workspaces, modify config, apply patches, or change acceptance.

Record operator review intent:

```bash
python -m orchestrator.codex_cli_operator_unlock_request experiments/guarded-demo --requested --requested-by local-review --confirmation-phrase "I request operator review for real Codex CLI execution"
```

Validate artifacts:

```bash
python -m orchestrator.artifact_validator guarded-demo
```
