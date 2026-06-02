# Artifact Reference

This document is the human-facing index for generated files and inspection
commands. Machine-readable contracts live under `schemas/`.

## Core Commands

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
python -m orchestrator.iteration_loop --allow-repeated-proposals --run-id max-round-demo
python -m orchestrator.run_loop --config config/default.json --run-id single-run-demo
python -m orchestrator.preflight --config config/codex_cli_guarded.json
```

Experiment inspection:

```bash
python -m orchestrator.experiments list --limit 5
python -m orchestrator.experiments show <run_id>
python -m orchestrator.experiments summary
python -m orchestrator.experiments leaderboard --limit 5
python -m orchestrator.experiments memory --limit 5
python -m orchestrator.experiments memory-diagnostics
python -m orchestrator.experiments diagnose <run_id>
python -m orchestrator.experiments agents <run_id>
python -m orchestrator.experiments slots <run_id>
python -m orchestrator.experiments compare <base_run_id> <candidate_run_id>
python -m orchestrator.experiments champion
python -m orchestrator.experiments promote <base_run_id> <candidate_run_id>
```

Replay and validation:

```bash
python -m orchestrator.artifact_validator <run_id>
python -m orchestrator.agent_replay experiments/<run_id>/round_001/agent_input.json
python -m orchestrator.agent_replay experiments/<run_id>/round_001/agent_input.json --validate
python -m orchestrator.attempt_replay experiments/<run_id>/round_001/agent_attempts/attempt_001_primary
python -m orchestrator.round_replay experiments/<run_id>/round_001
python -m orchestrator.agent_slot_health experiments/<run_id>
python -m orchestrator.agent_output_intake experiments/<run_id>/round_001/agent_input.json experiments/<run_id>/round_001/demo_agent_output.json --output experiments/<run_id>/round_001/agent_validation.json
python -m orchestrator.run_artifact_health --limit 10 --strict
python -m orchestrator.run_artifact_health --all --record-history
python -m orchestrator.run_artifact_health --all --created-at-from 2026-06-02T00:00:00Z --strict
python -m orchestrator.run_artifact_health --history-summary
python -m orchestrator.run_artifact_health --history-summary --created-at-from 2026-06-02T00:00:00Z
python -m orchestrator.experiments validate --limit 10 --strict
python -m orchestrator.experiments health-history
python -m orchestrator.memory_diagnostics --strict
python -m orchestrator.memory_diagnostics --created-at-from 2026-06-02T00:00:00Z --strict
python -m orchestrator.experiment_scope_health --created-at-from 2026-06-02T00:00:00Z --strict
python -m orchestrator.experiments scope-health --created-at-from 2026-06-02T00:00:00Z --strict
python -m orchestrator.artifact_validator_coverage --output artifact_validator_coverage.json --markdown artifact_validator_coverage.md
python -m orchestrator.artifact_validator_coverage --strict
python -m orchestrator.experiments coverage
```

## Single-Run Artifacts

The V0 single-run loop writes:

```text
experiments/<run_id>/
  metrics_before.json
  metrics_after.json
  report_before.md
  report_after.md
  summary.md
  diagnosis.json
  run_metadata.json
  decision.json
  patch.diff
  trades_before.csv
  trades_after.csv
```

## Multi-Round Run Artifacts

The V0.5 iteration loop writes run-level files:

```text
experiments/<run_id>/
  manifest.json
  summary.md
  diagnosis.json
  run_metadata.json
  agent_activation_preflight.json
  agent_activation_preflight.md
  candidate_leaderboard.json
  agent_result_stats.json
  research_brief.json
  research_brief.md
  experiment_scope_health.json
  run_closeout.json
  run_closeout.md
```

It also updates append-only experiment indexes:

```text
experiments/index.jsonl
experiments/memory.jsonl
experiments/run_artifact_health_history.jsonl
experiments/champion_history.jsonl
```

`champion_history.jsonl` exists after champion promotion.

`champion_comparison.json` exists inside a completed iteration run when a
champion registry is already present.

## Round Artifacts

Each completed round writes:

```text
round_001/
  train_metrics_before.json
  train_report_before.md
  train_trades_before.csv
  metrics_before.json
  report_before.md
  trades_before.csv
  holdout_metrics_before.json
  holdout_report_before.md
  holdout_trades_before.csv
  agent_context.md
  agent_context.json
  proposal_intent.json
  proposal_intent.md
  agent_role_contracts.json
  analysis_notes.json
  analysis_notes.md
  visual_artifacts_manifest.json
  chart.html
  trade_timeline.html
  visual_review.json
  visual_review.md
  agent_execution_plan.json
  agent_execution_plan.md
  agent_input.json
  agent_bundle_manifest.json
  agent_input_bundle/
  agent_output_bundle/
  agent_attempts/
  agent_attempts_manifest.json
  agent_selection_report.json
  agent_executor_report.json
  agent_routing_policy.json
  raw_agent_output.txt
  agent_output.json
  agent_validation.json
  agent_output_quarantine.json
  proposal.json
  agent_response.txt
  patch.diff
  train_metrics_after.json
  train_report_after.md
  train_trades_after.csv
  metrics_after.json
  report_after.md
  trades_after.csv
  holdout_metrics_after.json
  holdout_report_after.md
  holdout_trades_after.csv
  decision.json
  overfit_validation.json
  overfit_validation.md
  agent_role_readiness.json
  agent_role_readiness.md
```

Optional or adapter-specific artifacts include:

```text
  probe_data.csv
  probe_<role>_metrics.json
  round_replay.json
  round_replay.md
  workspace_manifest.json
  workspace_manifests/
  agent_execution.json
  agent_executions/
```

## Artifact Meanings

Proposal and intake artifacts:

- `raw_agent_output.txt` preserves the exact modifier output.
- `agent_output.json` stores normalized selected proposal data.
- `agent_validation.json` records contract, patch-target, and `git apply`
  checks.
- `agent_output_quarantine.json` records whether selected output is held or
  released before git apply.
- `proposal.json` is the auditable proposal used by the loop.
- `patch.diff` is the validated strategy patch.

Context and planning artifacts:

- `agent_context.md` and `agent_context.json` summarize prior rounds, outcome
  memory, candidate traces, champion context, and recent research briefs.
- `proposal_intent.json` and `proposal_intent.md` convert context into
  deterministic planner guidance.
- `agent_execution_plan.json` records the planned candidate queue before any
  modifier runs.
- `agent_routing_policy.json` explains deterministic candidate ranking.

Role and readiness artifacts:

- `agent_role_contracts.json` declares active and future role responsibilities.
- `analysis_notes.json` is read-only analysis context.
- `visual_artifacts_manifest.json`, `chart.html`, `trade_timeline.html`, and
  `visual_review.json` provide deterministic visual inspection artifacts with
  no routing authority.
- `overfit_validation.json` records advisory validation risk flags with no veto
  authority in V0.5.
- `agent_role_readiness.json` reports future role readiness.
- `agent_activation_preflight.json` validates startup role/profile wiring.

Replay artifacts:

- `attempt_replay.json` validates one saved candidate attempt without changing
  final acceptance.
- `attempt_output.json` links one saved attempt's input, proposal, raw output,
  patch, selection explanation, validation status, and optional execution audit.
- `round_replay.json` validates all saved planned attempts for a round.
- `agent_slot_health.json` summarizes slot readiness, audits, and replay state.
- `run_artifact_health.json` batch-validates saved experiment run artifacts
  and reports per-run artifact health without rerunning simulations.
  `--created-at-from` scopes indexed runs to a current contract era without
  deleting older experiment directories.
- `run_artifact_health_history.jsonl` appends compact health snapshots when
  explicitly requested or when the iteration loop completes, and
  `run_artifact_health_history_v1` summaries show repeated failing runs and
  artifact filenames. Automatic iteration records use the run's startup
  timestamp as the scope boundary. The same `--created-at-from` scope can
  exclude legacy failed runs from the summary without rewriting history.
- `memory_diagnostics.json` cross-references proposal outcome memory with
  artifact-health history by run id, agent, profile, direction, and patch hash.
  `--created-at-from` applies the same current-contract scope to outcome memory
  and indexed health runs. It is inspection-only and cannot execute agents, run
  backtests, route agents, apply patches, or change acceptance.
- `experiment_scope_health.json` combines current artifact health,
  artifact-health history, and memory diagnostics for one `--created-at-from`
  scope. It is a read-only status page and marks the scope unhealthy if any
  component has read errors, current artifact failures, historical scoped
  failure observations, or memory-linked failed health runs. The iteration loop
  writes it automatically at run completion using the run's startup timestamp
  as the current-contract scope boundary.
- `run_closeout.json` and `run_closeout.md` summarize the completed iteration
  run for operator review. They read saved artifacts only, record deterministic
  acceptance authority, selected candidates, health status, and recommended
  next actions, and cannot execute agents, run backtests, apply patches, route
  agents, or change acceptance.
- `artifact_validator_coverage.json` reports schema, validator, documentation,
  test, and inspection/replay coverage for repository artifact contracts.

## Validation

Use `python -m orchestrator.artifact_validator <run_id>` after a run. The
validator checks required files, schema validity, artifact hashes, source-path
bindings, role authority invariants, visual artifact locality, workspace audit
records, and Codex readiness evidence when present.
