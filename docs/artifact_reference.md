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
python -m orchestrator.experiments review <run_id>
python -m orchestrator.experiments review <run_id> --markdown
python -m orchestrator.experiments action-plan <run_id>
python -m orchestrator.experiments action-plan <run_id> --markdown
python -m orchestrator.experiments action-approval <run_id>
python -m orchestrator.experiments action-approval <run_id> --markdown
python -m orchestrator.experiments summary
python -m orchestrator.experiments summary --markdown
python -m orchestrator.experiments leaderboard --limit 5
python -m orchestrator.experiments memory --limit 5
python -m orchestrator.experiments memory-diagnostics
python -m orchestrator.experiments diagnose <run_id>
python -m orchestrator.experiments agents <run_id>
python -m orchestrator.experiments slots <run_id>
python -m orchestrator.experiments compare <base_run_id> <candidate_run_id>
python -m orchestrator.experiments champion
python -m orchestrator.experiments lineage
python -m orchestrator.experiments apply-config-approved <run_id> --dry-run-path experiments/<run_id>/config_application_dry_run.json
python -m orchestrator.experiments config-application-rollback-preview <run_id> --receipt-path experiments/<run_id>/config_application_receipt.json
python -m orchestrator.experiments restore-config-approved <run_id> --preview-path experiments/<run_id>/config_application_rollback_preview.json
python -m orchestrator.experiments config-lineage <run_id>
python -m orchestrator.experiments promote-approved <candidate_run_id> --approval-path experiments/<run_id>/champion_promotion_approval.json
python -m orchestrator.operator_action_approval experiments/<run_id> --action-id <action_id> --command-label <label> --approve --operator-id <operator> --confirmation-phrase "APPROVE OPERATOR ACTION"
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
  candidate_quality_trace.json
  candidate_quality_trace.md
  memory_hygiene.json
  memory_hygiene.md
  memory_scope_recommendation.json
  memory_scope_recommendation.md
  config_change_candidate.json
  config_change_candidate.md
  operator_config_review.json
  operator_config_review.md
  config_application_dry_run.json
  config_application_dry_run.md
  config_application_receipt.json  # after guarded config application
  config_application_receipt.md    # after guarded config application
  config_application_rollback_preview.json  # after rollback preview command
  config_application_rollback_preview.md    # after rollback preview command
  config_application_restore_receipt.json  # after guarded restore command
  config_application_restore_receipt.md    # after guarded restore command
  config_lineage.json
  config_lineage.md
  agent_result_stats.json
  candidate_challenger_report.json
  candidate_challenger_report.md
  champion_promotion_dry_run.json
  champion_promotion_dry_run.md
  champion_promotion_approval.json
  champion_promotion_approval.md
  champion_promotion_receipt.json  # after guarded champion promotion
  champion_promotion_receipt.md    # after guarded champion promotion
  research_brief.json
  research_brief.md
  experiment_scope_health.json
  run_closeout.json
  run_closeout.md
  operator_action_plan.json
  operator_action_plan.md
  operator_action_approval.json  # after explicit operator approval command
  operator_action_approval.md    # after explicit operator approval command
```

It also updates append-only experiment indexes:

```text
experiments/index.jsonl
experiments/memory.jsonl
experiments/run_artifact_health_history.jsonl
experiments/champion_history.jsonl
experiments/champion_lineage.json
experiments/champion_lineage.md
```

`champion_history.jsonl` exists after guarded champion promotion.
`champion_lineage.json` and `champion_lineage.md` are written by the lineage
inspection command and summarize champion history, current champion identity,
promotion receipts, approval hashes, dry-run hashes, and metric deltas.
`python -m orchestrator.experiments summary` and
`python -m orchestrator.experiments champion` also include a compact read-only
lineage summary without writing lineage artifacts.
`python -m orchestrator.experiments summary` additionally embeds a compact
dashboard with the latest indexed run, latest accepted and rejected runs, recent
diagnosis rows, recent failure-code counts, a best-run-to-champion gap, and an
operator watchlist for repeated proposals, artifact-health failures, and
champion-gap alerts. It is inspection-only and does not execute agents, run
backtests, apply patches, promote champions, or change acceptance.
`python -m orchestrator.experiments summary --markdown` renders the same
summary payload, including the watchlist, as a compact terminal-friendly
Markdown report without writing artifacts.
`python -m orchestrator.experiments review <run_id>` returns the saved
`run_closeout.json` operator dashboard directly. `review --markdown` renders
the same dashboard for terminal inspection. The command is read-only: it does
not write config, promote champions, execute agents, run backtests, route
candidates, apply patches, or change acceptance.
`operator_action_plan.json` and `operator_action_plan.md` translate the saved
closeout dashboard action items into explicit command candidates for human
review. `python -m orchestrator.experiments action-plan <run_id>` and
`action-plan --markdown` expose the same plan without executing any command.
The plan records command digests, guarded-command flags, and deterministic
authority fields, but it cannot write config, promote champions, execute
agents, run backtests, route candidates, apply patches, or change acceptance.
`operator_action_approval.json` and `operator_action_approval.md` can then
record explicit operator approval for one action-plan command candidate. The
approval binds to `operator_action_plan.json`, records the selected action id,
command label, command digest, operator id, and confirmation phrase hashes, but
still does not execute the approved command. The approved command must be
invoked separately by the operator.

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
- `agent_output.json` stores normalized selected proposal data and the
  proposal intent summary used by the round-level agent input.
- `agent_validation.json` records contract, patch-target, `git apply` checks,
  and the proposal intent summary used by the validated agent input.
- `agent_output_quarantine.json` records whether selected output is held or
  released before git apply, including the same proposal intent summary used by
  `agent_output.json`.
- `proposal.json` is the auditable proposal used by the loop.
- `patch.diff` is the validated strategy patch.

Context and planning artifacts:

- `agent_context.md` and `agent_context.json` summarize prior rounds, outcome
  memory, candidate traces, champion context, recent research briefs, and the
  configured strategy search space.
- `proposal_intent.json` and `proposal_intent.md` convert context into
  deterministic planner guidance using the configured strategy search-space
  direction order and fallback direction. They also include a
  `direction_decision_trace` that records candidate order, selected direction,
  avoid-source codes, and advisory-only authority policy.
- `agent_input.json` carries a compact `proposal_intent_summary` copied from
  that planner trace so external agents can consume the selected direction,
  candidate order, avoid-source summary, and advisory-only policy from one
  input contract.
- `agent_execution_plan.json` records the planned candidate queue and each
  profile's declared direction capability before any modifier runs. It also
  binds the same `proposal_intent_summary` into each attempt input contract so
  planned candidates can be audited against the planner context they will see.
- `agent_routing_policy.json` explains deterministic candidate ranking,
  including whether each proposal direction matched the profile's declared
  capability and whether it matched or auditably deviated from
  `proposal_intent.json`.
- `agent_executor_report.json`, `agent_attempts_manifest.json`,
  `attempt_output.json`, `agent_selection_report.json`, `agent_routing_policy.json`,
  `agent_output.json`, and `candidate_leaderboard.json` all carry the candidate
  score and `quality_breakdown` so the saved trace can prove why a candidate was
  selected without giving those artifacts final acceptance authority.
  Artifact validation binds those rows by `attempt_id` back to
  `proposal_attempts.json`, including `candidate_score`, `score_reasons`, and
  `quality_breakdown`.

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
  patch, selection explanation, validation status, proposal intent summary, and
  optional execution audit.
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
- `memory_hygiene.json` and `memory_hygiene.md` summarize the active outcome
  memory scope used by memory filters. They report total versus active records,
  ignored records from `created_at_from` or `recent_record_limit`, patch and
  direction groups that would trigger deterministic rejection, and advisory
  hygiene recommendations. They never delete memory, run backtests, route
  agents, apply patches, or change acceptance.
- `memory_scope_recommendation.json` and `memory_scope_recommendation.md`
  summarize whether the current outcome-memory scope should remain full-history
  or be narrowed for future runs with a recent-record limit. They read saved
  hygiene artifacts only, never write config, never delete memory, never route
  candidates, never apply patches, and never change acceptance.
- `config_change_candidate.json` and `config_change_candidate.md` convert
  saved recommendations into operator-reviewed config field candidates, such as
  `memory_filter.recent_record_limit`. They include current value, proposed
  value, rationale, reason codes, and risk notes, but they never write config,
  route candidates, apply patches, run backtests, or change acceptance.
- `operator_config_review.json` and `operator_config_review.md` record
  operator approve or reject intent for saved config candidates. Approval
  requires the configured confirmation phrase, rejection can be recorded without
  applying anything, and both paths remain audit-only: they never edit config,
  route candidates, apply patches, run backtests, or change acceptance.
- `config_application_dry_run.json` and `config_application_dry_run.md` preview
  whether approved config candidates still match the current config value and
  are ready for a later manual edit. They remain dry-run only and never edit
  config, route candidates, apply patches, run backtests, or change acceptance.
- `config_application_receipt.json` and `config_application_receipt.md` record
  the result of the guarded apply-config-approved command. The command writes
  config only when the saved dry-run is ready, the operator-review digest still
  matches, and the current config digest still matches the reviewed dry-run.
  Blocked attempts write a receipt but leave config unchanged.
- `config_application_rollback_preview.json` and
  `config_application_rollback_preview.md` read a saved application receipt and
  current config to preview manual restore rows and next-run impact. They are
  read-only and never restore config automatically.
- `config_application_restore_receipt.json` and
  `config_application_restore_receipt.md` record the result of the guarded
  restore-config-approved command. The command writes config only when the
  saved rollback preview is ready and all preview, receipt, and current config
  digests still match. Blocked attempts write a receipt but leave config
  unchanged.
- `config_lineage.json` and `config_lineage.md` connect config candidates,
  operator review, dry-run, apply receipt, rollback preview, and restore
  receipt artifacts into one read-only digest chain for the run.
- `experiment_scope_health.json` combines current artifact health,
  artifact-health history, and memory diagnostics for one `--created-at-from`
  scope. It is a read-only status page and marks the scope unhealthy if any
  component has read errors, current artifact failures, historical scoped
  failure observations, or memory-linked failed health runs. The iteration loop
  writes it automatically at run completion using the run's startup timestamp
  as the current-contract scope boundary.
- `research_brief.json` and `research_brief.md` summarize the completed
  iteration run, selected candidates, champion comparison context, deterministic
  observations, next questions, a run-local watchlist, and a recommended
  experiment focus. The focus uses the saved `strategy_search_space` direction
  order and fallback direction to suggest or avoid proposal directions for the
  next deterministic loop, but it is advisory only and cannot route agents or
  change acceptance.
- `run_closeout.json` and `run_closeout.md` summarize the completed iteration
  run for operator review. They read saved artifacts only, record deterministic
  acceptance authority, selected candidates, health status, research watchlist
  status, config-lineage status, champion/promotion review status, an
  operator-facing dashboard, and recommended next actions, and cannot execute
  agents, run backtests, write config, promote champions, apply patches, route
  agents, or change acceptance.
- `operator_action_plan.json` and `operator_action_plan.md` derive explicit
  command candidates from the saved closeout dashboard. They bind to
  `run_closeout.json` by SHA-256, mark commands that would write repository
  state, promote champions, or run backtests, and require explicit operator
  invocation for every candidate. They do not execute commands, execute agents,
  run backtests, write config, promote champions, route agents, apply patches,
  or change acceptance.
- `operator_action_approval.json` and `operator_action_approval.md` record
  operator approval for one action-plan command candidate. They bind to
  `operator_action_plan.json` by SHA-256 and require the exact confirmation
  phrase `APPROVE OPERATOR ACTION` for approval, but approval still does not
  execute commands, write config, promote champions, run agents, rerun
  backtests, route candidates, apply patches, or change acceptance.
- `candidate_leaderboard.json` records every proposal attempt with stable
  quality metadata. `quality_breakdown` decomposes the pre-backtest candidate
  score into named components, selected rows also record validation and
  holdout EV deltas, and artifact validation checks that each saved
  `quality_breakdown.total_score` matches the candidate score and that each
  leaderboard row matches the round-local `proposal_attempts.json` row for the
  same `attempt_id`. These fields explain candidate routing only; final
  acceptance remains controlled by deterministic policy and holdout gates.
- `candidate_quality_trace.json` and `candidate_quality_trace.md` summarize
  the saved leaderboard into an inspection-only trace of score components,
  probe/validation/holdout signals, selected attempts, patch families, and
  failure codes. They read `candidate_leaderboard.json` only, keep
  `proposal_attempts.json` as the round source of truth, and cannot route
  candidates, execute agents, run backtests, apply patches, or change
  acceptance.
- `candidate_challenger_report.json` and `candidate_challenger_report.md`
  compare saved candidate rows with the current champion registry when one
  exists. They expose validation gap, holdout stability flags, and top
  candidates for operator inspection only; they cannot promote champions,
  route agents, run backtests, apply patches, or change acceptance.
- `champion_promotion_dry_run.json` and `champion_promotion_dry_run.md`
  preview whether the completed run would satisfy the deterministic champion
  promotion comparison against the current champion. They never write
  `champion.json`, append `champion_history.jsonl`, execute agents, run
  backtests, apply patches, route agents, or change acceptance. Actual
  guarded promotion uses the explicit `experiments promote-approved` command.
- `champion_promotion_approval.json` and `champion_promotion_approval.md`
  record operator review intent, required confirmation phrase hashes, reviewed
  promote command digests, and source evidence hashes. They do not execute the
  promote command, write `champion.json`, append `champion_history.jsonl`, run
  agents, run backtests, apply patches, route agents, or change acceptance.
- `champion_promotion_receipt.json` and `champion_promotion_receipt.md` record
  the result of the guarded promote-approved command. The command writes
  `champion.json` and appends `champion_history.jsonl` only when the approval
  artifact, reviewed command digest, dry-run digest, current champion identity,
  and current deterministic comparison still match.
- `champion_lineage.json` and `champion_lineage.md` are read-only global
  experiment reports that connect `champion.json`, `champion_history.jsonl`,
  promotion receipts, approval artifacts, dry-run reports, and comparison
  metric deltas into one inspectable champion evolution chain. The experiment
  `summary` and `champion` inspection commands expose the same chain as compact
  embedded JSON fields for quick status checks, but only the `lineage` command
  writes `champion_lineage.json` and `champion_lineage.md`.
- `python -m orchestrator.experiments promote <base_run_id> <candidate_run_id>`
  remains available as a legacy deterministic helper for tests and fixtures,
  but operator-facing promotion should use `promote-approved` with a recorded
  approval artifact.
- `artifact_validator_coverage.json` reports schema, validator, documentation,
  test, and inspection/replay coverage for repository artifact contracts.

## Validation

Use `python -m orchestrator.artifact_validator <run_id>` after a run. The
validator checks required files, schema validity, artifact hashes, source-path
bindings, role authority invariants, visual artifact locality, workspace audit
records, and Codex readiness evidence when present.
