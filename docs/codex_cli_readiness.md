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
change acceptance. Pipeline step, generated-artifact, and final-summary file
hashes must be empty or 64 lowercase hexadecimal SHA-256 strings.

`codex_cli_readiness_summary.json` records a schema-validated
`consistency_checks` section. These checks bind the expected readiness stage
order, missing-stage list, blocked-stage list, aggregate blocking reasons, final
stage ready flag, and human-facing readiness status to the same saved evidence.
The summary remains read-only and cannot unlock Codex, apply patches, or change
acceptance. Each stage artifact hash in the summary must be empty or a 64
lowercase hexadecimal SHA-256 string.

Manual approval evidence is also digest-bound: confirmation phrase digests must
be 64 lowercase hexadecimal SHA-256 strings, while recorded enablement-gate and
candidate-config artifact hashes must be empty or 64 lowercase hexadecimal
SHA-256 strings.

## Canonical Source Binding

Codex readiness artifacts are validated as a source chain, not as isolated JSON
files. The artifact validator checks that key source records point to canonical
files inside the same run directory and that the recorded hashes still match.

Important canonical bindings include:

- `codex_cli_execution_unlock_snapshot.json` must source the canonical
  `codex_cli_execution_unlock_gate.json` and must retain the complete frozen
  evidence set from the unlock gate: candidate config, replay gate, enablement
  gate, manual approval, canary gate, real preflight, and dry-invocation guard.
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
Each guarded Codex audit also records `agent_execution.preflight_binding`,
which recomputes the active startup preflight match for the saved audit. The
binding must show the reviewed command digest, current run workspace prefix,
current run identity, startup preflight run identity, startup preflight ok
state, strategy-only mutation allowlist, strategy-only mutation guard, and
startup execution permission all matched before artifact validation treats the
audit as preflight-bound.

If any of these change, execution remains blocked:

- command
- startup preflight run id
- startup preflight ok state
- workspace prefix
- strategy-only mutation allowlist
- strategy-only mutation guard
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
read-only and schema-constrains request phrase, snapshot, planned command, and
source-file digests before any startup preflight may consume it. It also
includes policy checks proving that the request itself does not:

- Execute Codex CLI.
- Send a strategy prompt.
- Create a workspace.
- Apply patches.
- Select a candidate.
- Change final acceptance.
- Modify config.

The request must include the expected confirmation phrase hash and operator id.
It also records canonical source records for the readiness pipeline, execution
unlock snapshot, execution candidate, and real-execution dry run. Startup
preflight and artifact validation re-check those source hashes before treating
the request as ready.
It may still be `operator_request_ready=false` when upstream readiness evidence
is blocked; this is valid audit output, not execution permission.

## Startup Preflight

`codex_cli_execution_preflight.json` blocks real Codex CLI execution unless a
ready canonical operator request already exists in the current run directory and
still matches the active profile command, workspace prefix, run identity, source
hashes, and planned execution identity. The saved operator-request file hash and
expected command digest are schema-constrained before the startup gate can trust
them.

The iteration loop allows an existing run directory only for this narrow
canonical operator-request startup case. Ordinary pre-existing run directories
remain blocked to avoid accidental artifact overwrite.

## Useful Commands

Run a guarded audit iteration:

```bash
python -m orchestrator.iteration_loop --config config/codex_cli_guarded.json --run-id guarded-demo --max-rounds 1
```

With `execute=false`, this command does not invoke Codex. It writes a guarded
`agent_execution.json` audit and binds the selected audit to `proposal.json`,
`raw_agent_output.txt`, and `agent_validation.json` through
`agent_execution.intake_binding`, proving the disabled Codex boundary still uses
the shared proposal-intake path. When startup preflight evidence is present,
the audit also includes `agent_execution.preflight_binding`, proving the
attempt stayed under the preflight command, workspace-prefix, and strategy-only
mutation boundary.

Run a local canary iteration:

```bash
python -m orchestrator.iteration_loop --config config/codex_cli_canary.json --run-id canary-demo --max-rounds 1
python -m orchestrator.codex_cli_canary_gate experiments/canary-demo --config config/codex_cli_canary.json
```

The canary gate requires each selected canary execution audit to have bound,
blocker-free `agent_execution.intake_binding` and
`agent_execution.preflight_binding`. The final execution unlock gate exposes
both `canary_intake_binding_ready` and `canary_preflight_binding_ready`, so a
future real Codex enablement cannot rely on canary subprocess evidence unless
that output was normalized through the shared proposal-intake path and stayed
inside the startup preflight command, workspace, and mutation boundary.
Artifact validation re-derives the canary gate from the current run artifacts,
so a stale or manually edited `codex_cli_canary_gate.json` cannot keep reporting
ready after the underlying execution audit drifts. Direct canary gate file
validation reports the same condition as a current-evidence mismatch.
The final execution unlock gate is also re-derived from the current replay,
enablement, manual approval, canary, real-preflight, and dry-invocation
artifacts, so stale unlock evidence cannot survive upstream readiness drift.
Direct unlock gate file validation reports the same stale aggregate evidence
as a current-evidence mismatch while preserving detailed upstream mismatch
errors in the full artifact validator.
Direct unlock snapshot file validation rechecks the canonical source unlock
gate and frozen evidence file records, so stale snapshot evidence is also
reported as a current-evidence mismatch.
Direct execution candidate file validation re-derives the future command,
workspace path, mutation boundary, and candidate config binding from the
canonical unlock snapshot, so stale candidate plans are reported as
current-evidence mismatches before any real execution can be considered.
Direct real-execution dry-run file validation rechecks the canonical execution
candidate, planned command, planned workspace path, and workspace-not-created
state, so stale dry-run boundaries are reported before any real execution can
be considered.
Direct real-preflight file validation also re-runs only the local `--version`
probe against the current candidate config and reports stale executable or
config evidence as a current-evidence mismatch.
Direct dry-invocation guard file validation stays read-only: it replays current
config, prompt, execution-audit, and workspace evidence without invoking Codex
again, and reports stale dry-run evidence as a current-evidence mismatch.
Operator-facing views now surface the same condition as a shared
`codex_intake_readiness` block in the unlock checklist, unlock runbook,
execution readiness diff, cockpit, and terminal-only operator home. It is
read-only display evidence: `blocked` points to missing or dirty
selected-attempt intake or preflight binding, while `not_available` means no
canary or unlock evidence exists for that run yet.

Run the read-only readiness pipeline:

```bash
python -m orchestrator.codex_cli_readiness_pipeline experiments/guarded-demo --config config/codex_cli_enable_candidate.json --canary-run-dir experiments/canary-demo --approved --approved-by local-review --confirmation-phrase "I approve this Codex CLI candidate for manual enablement"
```

The pipeline writes the readiness chain in dependency order and records a
`consistency_checks` section that binds expected step order, generated artifact
records, the final readiness summary file, and the pipeline-level status fields.
Those checks are schema-validated and read-only; they do not execute Codex,
create workspaces, apply patches, or change acceptance.

Review or refresh the read-only unlock runbook:

```bash
python -m orchestrator.codex_cli_unlock_runbook experiments/guarded-demo
python -m orchestrator.experiments unlock-runbook guarded-demo --markdown
```

The iteration loop writes the runbook during closeout and no-round real-Codex
startup failures. The explicit command refreshes that read-only guide after
later evidence changes. The runbook orders the required readiness, candidate,
dry-run, and operator request artifacts into a manual review guide with
SHA-256 bindings for each command hint and artifact write command. The runbook
schema requires those digests to be 64 lowercase hexadecimal characters. It
only reads saved artifacts and prints command hints; it does not execute Codex,
record approval, create workspaces, apply patches, or change acceptance.

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
returning the deterministic startup error. The operator cockpit includes
read-only unlock-runbook and readiness-diff panels so missing ordered evidence,
blocked runbook steps, or drift are visible from the main operator page. The
terminal-only operator home mirrors the runbook status and command hint in its
Codex CLI section.

Refresh operator-facing views after writing later readiness evidence:

```bash
python -m orchestrator.experiments refresh-operator-views guarded-demo
```

The refresh command rewrites the read-only operator action dashboard, Codex CLI
execution preflight, unlock checklist, unlock runbook, readiness diff, and
cockpit in dependency order. It uses the run's recorded config path unless
`--config` is provided and
returns a terminal-only receipt with the config source, path, existence flag,
SHA-256 digest, pre-refresh cockpit stale-source evidence, post-refresh
freshness, operator-home navigation status, Codex unlock-runbook status and
command hint, Codex readiness-diff status, Codex intake readiness status, and
per-artifact JSON/Markdown output hashes; it does not execute
Codex, record approval, create workspaces, modify config, apply patches, or
change acceptance.
Use `--markdown` for the same terminal-only receipt as a short operator summary
when reviewing the stale sources that were fixed plus the refreshed paths and
hash prefixes by eye. The summary also surfaces the refreshed cockpit status,
primary focus, blocker count, primary blocker, blocker preview, refresh-effect
status, operator-review-required flag, primary review reason codes,
before/after blocker delta counts, and the review-priority recommended next
command with its source marker and reason, plus a compact safety-policy
summary. The terminal receipt is checked with schema validation plus
deterministic consistency checks for the copied next-command and review-reason
summary fields before anything is printed.

Record operator review intent:

```bash
python -m orchestrator.codex_cli_operator_unlock_request experiments/guarded-demo --requested --requested-by local-review --confirmation-phrase "I request operator review for real Codex CLI execution"
```

Validate artifacts:

```bash
python -m orchestrator.artifact_validator guarded-demo
```
