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
python -m orchestrator.operator_action_executor <run_id> --approval-path experiments/<run_id>/operator_action_approval.json
python -m orchestrator.experiments action-execution <run_id>
python -m orchestrator.experiments action-execution <run_id> --markdown
python -m orchestrator.operator_action_audit experiments/<run_id>
python -m orchestrator.experiments action-audit <run_id>
python -m orchestrator.experiments action-audit <run_id> --markdown
python -m orchestrator.operator_action_dashboard experiments/<run_id>
python -m orchestrator.experiments action-dashboard <run_id>
python -m orchestrator.experiments action-dashboard <run_id> --markdown
python -m orchestrator.operator_unlock_checklist experiments/<run_id>
python -m orchestrator.experiments unlock-checklist <run_id>
python -m orchestrator.experiments unlock-checklist <run_id> --markdown
python -m orchestrator.codex_cli_readiness_summary experiments/<run_id>
python -m orchestrator.codex_cli_unlock_runbook experiments/<run_id>
python -m orchestrator.experiments unlock-runbook <run_id>
python -m orchestrator.experiments unlock-runbook <run_id> --markdown
python -m orchestrator.codex_cli_execution_readiness_diff experiments/<run_id>
python -m orchestrator.experiments execution-readiness-diff <run_id>
python -m orchestrator.experiments execution-readiness-diff <run_id> --markdown
python -m orchestrator.operator_cockpit experiments/<run_id>
python -m orchestrator.experiments cockpit <run_id>
python -m orchestrator.experiments cockpit <run_id> --markdown
python -m orchestrator.experiments refresh-operator-views <run_id>
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
  modifier_profile_recommendation.json
  modifier_profile_recommendation.md
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
  operator_action_execution_receipt.json  # after guarded read-only action execution
  operator_action_execution_receipt.md    # after guarded read-only action execution
  operator_action_audit.json  # after optional operator action audit command
  operator_action_audit.md    # after optional operator action audit command
  operator_action_dashboard.json
  operator_action_dashboard.md
  operator_unlock_checklist.json
  operator_unlock_checklist.md
  codex_cli_readiness_summary.json  # after optional readiness summary command
  codex_cli_readiness_summary.md    # after optional readiness summary command
  codex_cli_unlock_runbook.json  # after optional unlock runbook command
  codex_cli_unlock_runbook.md    # after optional unlock runbook command
  codex_cli_execution_readiness_diff.json
  codex_cli_execution_readiness_diff.md
  operator_cockpit.json
  operator_cockpit.md
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

`manifest.json` records the run status, stop reason, completed rounds, linked
run-level artifact paths, and `agent_intake_summary`, a compact aggregation of
per-round agent-output intake status, blocking reason codes, retryable counts,
and the primary blocked-code navigation hint. It also records
`run_outcome_summary`, a deterministic read-only classification of the saved
run outcome such as policy rejection, holdout veto, repeated proposal, no
improvement, max-round stop, agent-intake block, artifact invalid, or accepted.
`diagnosis.json` is a compact machine-readable review artifact built from the
saved run artifacts. For iteration runs, it includes per-round policy results,
selected candidates, the best validation round, and the same agent-intake
summary and run-outcome summary so adapter/proposal and gate failures can be
grouped without changing acceptance.

`champion_history.jsonl` exists after guarded champion promotion.
`champion_lineage.json` and `champion_lineage.md` are written by the lineage
inspection command and summarize champion history, current champion identity,
promotion receipts, approval hashes, dry-run hashes, and metric deltas.
`python -m orchestrator.experiments summary` and
`python -m orchestrator.experiments champion` also include a compact read-only
lineage summary without writing lineage artifacts.
The `champion` terminal output is a `champion_status_v1` payload validated
against `schemas/champion_status.schema.json`, with deterministic consistency
checks that bind the current registry champion to the embedded lineage summary,
latest history row, validation EV delta, and read-only policy flags before JSON
is printed.
`python -m orchestrator.experiments memory --limit N` returns the recent
append-only proposal outcome memory records as a terminal-only
`proposal_outcome_memory` payload validated against
`schemas/proposal_outcome_memory.schema.json` before JSON is printed. Its
consistency checks bind the output to the bounded tail of
`experiments/memory.jsonl`, require proposal-outcome identity fields and a
boolean acceptance result, and keep the command read-only: it does not execute
agents, rerun backtests, route candidates, apply patches, delete memory, or
change acceptance.
`python -m orchestrator.experiments summary` additionally embeds a compact
dashboard with the latest indexed run, latest accepted and rejected runs, recent
diagnosis rows, recent failure-code counts, recent outcome-category counts, a
best-run-to-champion gap, and an operator watchlist for repeated proposals,
artifact-health failures, and champion-gap alerts. Recent rows include the
saved `run_outcome_summary` category, primary stage, and primary code when the
run has an iteration diagnosis. It is inspection-only and does not execute
agents, run backtests, apply patches, promote champions, or change acceptance.
The embedded dashboard is validated in memory against
`schemas/experiment_summary_dashboard.schema.json` before JSON or markdown is
printed, with deterministic consistency checks for recent failure/outcome
counts, top recent code/category fields, latest accepted/rejected status
summaries, latest-run to recent-tail binding, accepted-row flags, champion-gap
status and delta invariants, watchlist alert counts, severity counts, status,
alert codes, and read-only policy flags.
`python -m orchestrator.experiments summary --markdown` renders the same
summary payload, including the watchlist, as a compact terminal-friendly
Markdown report without writing artifacts.
`python -m orchestrator.experiments leaderboard --limit N` returns the same
ranked run list shape as before, but validates the terminal-only
`experiment_leaderboard` payload against
`schemas/experiment_leaderboard.schema.json` before printing. The consistency
checks enforce the requested limit, descending EV-delta and creation-time
ordering, unique run IDs, single-run EV delta arithmetic, and non-negative
iteration completed-round counts.
`python -m orchestrator.experiments review <run_id>` returns the saved
`run_closeout.json` operator dashboard directly. `review --markdown` renders
the same dashboard for terminal inspection. The terminal review payload is
validated in memory against `schemas/operator_run_review.schema.json` before it
is printed, with deterministic consistency checks that the copied top-level
run status, closeout status, completed rounds, accepted round, stop reason, and
config-lineage summary still match the embedded dashboard. It also checks the
dashboard's fixed gate order, gate-to-summary bindings, read-only authority,
policy flags, selected-candidate count, and watchlist alert count. The command
is read-only: it does not write config, promote champions, execute agents, run
backtests, route candidates, apply patches, or change acceptance.
`python -m orchestrator.experiments profile-recommendation <run_id>` returns
the saved or recomputed `modifier_profile_recommendation.json`. The payload
reads `candidate_quality_trace.json`, `research_brief.json`, and the active
config, then maps suggested directions to available deterministic modifier
profiles for operator review. `profile-recommendation --markdown` renders the
same recommendation. It is read-only: it does not write config, route agents,
execute agents, run backtests, apply patches, or change acceptance.
`operator_action_plan.json` and `operator_action_plan.md` translate the saved
closeout dashboard action items into explicit command candidates for human
review. `python -m orchestrator.experiments action-plan <run_id>` and
`action-plan --markdown` expose the same plan without executing any command.
The plan records command digests, guarded-command flags, and deterministic
authority fields. The writer and terminal view validate the payload against
`schemas/operator_action_plan.schema.json` and check summary counts, action
ids, action statuses, reason codes, command digests, policy flags, and
authority fields before returning. Artifact validation checks command
candidates through the shared operator command-hint validator for known labels,
expected artifacts, command prefixes, simple shell-control-token guards, and
matching command digests. The plan cannot write config, promote champions,
execute agents, run backtests, route candidates, apply patches, or change
acceptance.
`operator_action_approval.json` and `operator_action_approval.md` can then
record explicit operator approval for one action-plan command candidate. The
approval binds to `operator_action_plan.json`, records the selected action id,
command label, command digest, operator id, and confirmation phrase hashes.
Artifact validation replays the selected action and command lookup from the
saved action plan so the approval cannot drift to a different command while
keeping a valid source digest. The writer and terminal view also validate the
payload against `schemas/operator_action_approval.schema.json` and check the
selected action, selected command, confirmation phrase hashes, approval gate,
status, recommended next actions, and read-only policy before returning.
Approval still does not execute the approved command. The approved command must
be invoked separately by the operator.
`operator_action_execution_receipt.json` and
`operator_action_execution_receipt.md` can then record the guarded execution of
an approved read-only inspection command. The receipt requires a saved approval
artifact, validates the selected command digest, verifies that the receipt's
selected action, selected command, execution command, argv, and evidence hashes
still match the saved approval, blocks commands that write repository state,
promote champions, run backtests, execute agents, route agents, apply patches,
or change acceptance, records stdout/stderr hashes, and checks tracked
workspace mutation before writing the receipt. The writer and terminal view
validate the payload against
`schemas/operator_action_execution_receipt.schema.json` and check source
approval binding, selected action and command equality, execution command and
argv, evidence fields, mutation guard, status, and policy before returning.
The allowlist includes `python -m orchestrator.experiments quality-trace
<run_id>`, so a repeated-proposal closeout can be followed by an approved
read-only inspection of `candidate_quality_trace.json` before choosing the next
deterministic modifier profile.
`operator_action_audit.json` and `operator_action_audit.md` connect the saved
action plan, approval, and execution receipt into one digest-checked read-only
chain. The audit records stable failure reasons with stage, code, severity, and
detail fields so operator views can report exactly which link broke. The writer
and terminal view validate the payload against
`schemas/operator_action_audit.schema.json` and check source artifact file
records, status, summary, selected action, selected command, execution record,
chain checks, next actions, and policy against the current digest chain before
returning.
`python -m orchestrator.experiments action-audit <run_id>` and `action-audit
--markdown` expose the saved or derived audit without executing commands,
writing config, promoting champions, running agents, running backtests,
applying patches, routing agents, or changing acceptance.
`operator_action_dashboard.json` and `operator_action_dashboard.md` summarize
the same chain into a compact next-step view. The iteration loop writes the
final dashboard during closeout after `operator_action_plan.json`; `python -m
orchestrator.experiments action-dashboard <run_id>` and `action-dashboard
--markdown` show or derive the current step, timeline, selected command, safe
command counts, audit failure reasons, blockers derived from those reason
codes, and suggested read-only/guarded commands without recording approval,
executing commands, writing config, promoting champions, running agents,
running backtests, applying patches, routing agents, or changing acceptance.
The dashboard writer and terminal view validate the saved or derived payload
against
`schemas/operator_action_dashboard.schema.json` and checks that status-derived
fields plus action, command, failure-reason, and blocker counts still match the
embedded rows.
Artifact validation checks dashboard command hints through the shared operator
command-hint validator for known labels, expected write
targets, current-step coverage, and simple shell-control-token guards.
`operator_unlock_checklist.json` and `operator_unlock_checklist.md` expose the
Codex CLI operator-unlock evidence chain as a standalone read-only checklist.
The iteration loop writes it during closeout before the final cockpit so cockpit
source hashes bind to it. `python -m orchestrator.experiments unlock-checklist
<run_id>` and `unlock-checklist --markdown` show the saved or derived checklist
without recording approval, executing Codex, executing agents, creating
workspaces, applying patches, routing agents, or changing acceptance. The
`navigation` section lists expected evidence artifacts, failed evidence groups,
blocking reason codes, related artifact paths, and command hints that still
require explicit operator invocation. Artifact validation checks those
navigation command hints through the shared operator command-hint validator for
known labels, artifact ids, write flags, command prefixes, and shell-control
token safety. The checklist writer and terminal view validate saved or derived
payloads against the schema and deterministic consistency checks before
returning them, stripping terminal-only metadata before schema checks.
Those checks include top-level item counts, item-level failed-check and
blocker-code mappings, navigation blocking counts, primary blocker, expected
artifact ordering, and command-hint coverage. If real Codex execute=true
startup preflight is blocked before any round starts, the failed run still
writes this checklist and
the run summary points at the primary blocker.
`codex_cli_readiness_pipeline.json` records a read-only dependency-order
readiness run and includes `consistency_checks` that bind expected step order,
generated artifact file records, the final summary artifact hash, and
pipeline-level readiness fields. These checks are schema-validated audit
evidence only; they cannot execute Codex, create workspaces, route agents,
apply patches, or change acceptance.
`codex_cli_unlock_runbook.json` and `codex_cli_unlock_runbook.md` convert the
same Codex CLI unlock chain into an ordered operator guide. `python -m
orchestrator.codex_cli_unlock_runbook experiments/<run_id>` writes the
artifacts, and `python -m orchestrator.experiments unlock-runbook <run_id>` or
`unlock-runbook --markdown` shows the saved or derived guide. The runbook lists
the required evidence artifacts, readiness fields, status, and command hints,
and artifact validation checks those operator commands through the shared
operator command-hint validator for known labels, write flags, command prefixes,
and simple shell-control-token guards. The runbook writer and terminal view
validate saved or derived payloads against the schema and deterministic
consistency checks before returning them, stripping terminal-only metadata
before schema checks. Those checks include step order, summary counters and
step lists, status and readiness fields, source checklist summaries,
operator-command bindings, authority flags, read-only policy flags, and
current-evidence drift for derived payloads. Every command still requires
explicit operator invocation. It cannot record approval, execute commands,
execute Codex, create workspaces, route agents, apply patches, or change
acceptance.
`codex_cli_execution_readiness_diff.json` and
`codex_cli_execution_readiness_diff.md` compare the current config-derived real
Codex command, command digest, workspace path, target file, mutation allowlist,
startup preflight expectation, execution candidate, real-execution dry-run, and
operator request evidence. The report marks each comparison as `matched`,
`missing`, or `drift` and summarizes whether evidence is missing or has drifted.
The writer and terminal view validate saved or derived payloads against the
schema and deterministic consistency checks before returning them, stripping
terminal-only metadata before schema checks. Those checks include
status-derived readiness, comparison summary counters, missing-artifact lists,
drift/missing comparison ids, missing-side markers, blocking-reason coverage,
and current-evidence drift for derived payloads.
It is read-only and cannot record approval, execute commands, execute Codex,
create workspaces, modify config, route agents, apply patches, or change
acceptance. The iteration loop writes it automatically during closeout,
including no-round startup failures caused by blocked real Codex execute=true
preflight checks; explicit commands can refresh it after later operator
evidence artifacts are written.
`operator_cockpit.json` and `operator_cockpit.md` collect the run closeout,
config lineage, operator action dashboard, Codex CLI execution preflight,
standalone operator unlock checklist, Codex CLI execution readiness diff,
candidate challenger report, champion-promotion dry-run, promotion approval,
and scope-health status into a single read-only operator page. The Codex CLI
panels expose startup preflight status, real-execution profile counts,
operator-unlock readiness counts, preflight blockers, grouped checklist status,
and readiness diff missing/drift counts, but they do not unlock or execute
Codex. The operator-action panel surfaces dashboard failure reasons as cockpit
action failure reasons and `operator_action:<code>` blockers so action-chain
breaks are visible from the top page. The iteration loop writes the final
cockpit after the dashboard, standalone checklist, and readiness diff so source
hashes bind to the final closeout artifacts;
`python -m orchestrator.experiments cockpit <run_id>` and `cockpit --markdown`
expose panel rows, blockers, primary focus, a deterministic `review_priority`
navigation object, and command hints without recording approval, executing
commands, writing config, promoting champions, running agents, running
backtests, applying patches, routing agents, or changing acceptance. The
`review_priority` object chooses the first panel and existing saved command
hint to inspect from blocker, config lineage, action, Codex readiness,
challenger, promotion, scope-health, and run-outcome state; it is a read-only
ordering hint and cannot execute the command or change acceptance.
Artifact validation checks cockpit command hints through the shared operator
command-hint validator for known labels, expected write targets, the required
`review_cockpit` first command, and simple shell-control-token guards. It also
cross-checks the `review_priority` navigation object against the saved panel
row and saved command hint so the priority target cannot drift from the
cockpit payload it summarizes. The cockpit writer itself also validates
status-derived OK and focus fields, action failure-reason summaries,
`operator_action:<code>` blocker coverage, Codex unlock checklist counts, and
review-priority panel and command references before returning.
The `cockpit` terminal view validates saved or derived payloads through the
same schema and consistency checks before adding terminal-only metadata.
When the inspection command reads a saved
cockpit artifact, it adds a transient `snapshot_freshness` section that compares
recorded source hashes with the current source files and names stale sources
that require an explicit cockpit refresh. This freshness section is read-only
inspection metadata and is
not stored in `operator_cockpit.json`.
`python -m orchestrator.experiments refresh-operator-views <run_id>` is an
explicit convenience command that rewrites the existing read-only operator
action dashboard, Codex CLI execution preflight, operator unlock checklist,
Codex CLI execution readiness diff, and operator cockpit in dependency order.
It uses the run's recorded config path unless `--config` is provided, returns a
terminal-only `operator_view_refresh_v1` receipt with config source, path,
existence, SHA-256 fields, pre-refresh cockpit stale-source evidence,
post-refresh cockpit freshness, refresh-effect status, operator-review-required
flag, deterministic review reason codes, blocker delta counts, and
per-artifact JSON/Markdown output hashes, and still does not execute commands,
execute Codex, run agents, run backtests, write config, promote champions,
apply patches, route agents, or change acceptance.
The receipt is validated in memory against
`schemas/operator_view_refresh.schema.json` before it is printed, with an
additional deterministic consistency check for refreshed artifact count and
order, per-artifact file-path bindings, blocker-delta counters, policy-summary
derivation, refresh-effect derivation, and copied review-summary next command,
reason, and post-refresh blocker fields, even though it is not written as a new
artifact family.
Add `--markdown` to render the same terminal-only receipt as a compact operator
summary with refreshed artifact paths, hash prefixes, config provenance,
pre-refresh stale sources, and post-refresh snapshot freshness. The receipt
also includes a derived operator summary from the refreshed cockpit: cockpit
status, primary focus, blocker count, primary blocker, a short blocker preview,
refresh-effect details including whether operator review is still required,
primary review reason codes, before/after blocker delta details, the
review-priority recommended next command with an explicit source marker and
reason, and a compact safety-policy summary.

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
  proposal intent summary used by the round-level agent input. Its selected
  proposal uses `schemas/strategy_proposal.schema.json`.
- `agent_validation.json` records contract, patch-target, `git apply` checks,
  and the proposal intent summary used by the validated agent input. It also
  records schema-validated consistency checks that bind the raw output,
  normalized proposal fields, patch hash, semantic checks, and validation
  result. Its embedded proposal uses the same shared strategy proposal schema;
  the `semantic_checks` object records deterministic protocol, target, metadata,
  and patch-target rule results that control contract pass/fail before `git
  apply` can run. The `intake_diagnosis` object summarizes the primary stable
  failure code, all blocking codes, retryability, and git-apply status so
  external-adapter failures can be grouped without parsing free-form text.
- `agent_output_quarantine.json` records whether selected output is held or
  released before git apply, including the same proposal intent summary used by
  `agent_output.json`. It also records schema-validated consistency checks that
  bind release status, selected attempt id, patch hash, validation status, and
  source artifact hashes before any patch can be applied.
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
  `proposal_intent.json`. Artifact validation recomputes the capability and
  alignment booleans from each saved candidate row so schema-valid drift in
  those audit fields is reported.
- `agent_executor_report.json`, `agent_attempts_manifest.json`,
  `attempt_output.json`, `agent_selection_report.json`, `agent_routing_policy.json`,
  `agent_output.json`, and `candidate_leaderboard.json` all carry the candidate
  score and `quality_breakdown` so the saved trace can prove why a candidate was
  selected without giving those artifacts final acceptance authority.
  Artifact validation binds those rows by `attempt_id` back to
  `proposal_attempts.json`, including `candidate_score`, `score_reasons`,
  `quality_breakdown`, and saved direction metadata where that artifact carries
  it.

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
  `python -m orchestrator.memory_diagnostics` and
  `python -m orchestrator.experiments memory-diagnostics` validate the terminal
  payload against `schemas/memory_diagnostics.schema.json` and the current
  source artifacts before printing JSON.
- `memory_hygiene.json` and `memory_hygiene.md` summarize the active outcome
  memory scope used by memory filters. They report total versus active records,
  ignored records from `created_at_from` or `recent_record_limit`, patch and
  direction groups that would trigger deterministic rejection, and advisory
  hygiene recommendations. Artifact validation checks saved scope, totals,
  visible rows, and recommendations for internal consistency without binding
  old reports to future append-only memory records. They never delete memory,
  run backtests, route agents, apply patches, or change acceptance.
  `python -m orchestrator.memory_hygiene` validates dynamic terminal output
  against current outcome memory before printing JSON, while
  `python -m orchestrator.experiments memory-hygiene <run_id>` validates saved
  artifacts for schema and internal consistency before adding terminal metadata.
- `memory_scope_recommendation.json` and `memory_scope_recommendation.md`
  summarize whether the current outcome-memory scope should remain full-history
  or be narrowed for future runs with a recent-record limit. They read saved
  hygiene artifacts only, never write config, never delete memory, never route
  candidates, never apply patches, and never change acceptance.
  `python -m orchestrator.memory_scope_recommendation` and
  `python -m orchestrator.experiments memory-scope-recommendation <run_id>`
  validate the terminal payload against the schema and deterministic
  recommendation derivation before printing JSON.
- `config_change_candidate.json` and `config_change_candidate.md` convert
  saved recommendations into operator-reviewed config field candidates, such as
  `memory_filter.recent_record_limit`. They include current value, proposed
  value, rationale, reason codes, and risk notes, but they never write config,
  route candidates, apply patches, run backtests, or change acceptance.
  `python -m orchestrator.experiments config-change-candidate <run_id>` validates
  schema, run binding, candidate summary, and operator-review status before
  printing JSON.
- `operator_config_review.json` and `operator_config_review.md` record
  operator approve or reject intent for saved config candidates. Approval
  requires the configured confirmation phrase, rejection can be recorded without
  applying anything, and both paths remain audit-only: they never edit config,
  route candidates, apply patches, run backtests, or change acceptance.
  `python -m orchestrator.experiments operator-config-review <run_id>` validates
  schema, candidate summary, review gate, reviewed-row decisions, and next
  actions before printing JSON.
- `config_application_dry_run.json` and `config_application_dry_run.md` preview
  whether approved config candidates still match the current config value and
  are ready for a later manual edit. They remain dry-run only and never edit
  config, route candidates, apply patches, run backtests, or change acceptance.
  `python -m orchestrator.experiments config-application-dry-run <run_id>`
  validates schema, application gate counts, planned-row readiness, status, and
  next actions before printing JSON.
- `config_application_receipt.json` and `config_application_receipt.md` record
  the result of the guarded apply-config-approved command. The command writes
  config only when the saved dry-run is ready, the operator-review digest still
  matches, and the current config digest still matches the reviewed dry-run.
  Blocked attempts write a receipt but leave config unchanged.
- `config_application_rollback_preview.json` and
  `config_application_rollback_preview.md` read a saved application receipt and
  current config to preview manual restore rows and next-run impact. They are
  read-only and never restore config automatically.
  `python -m orchestrator.experiments config-application-rollback-preview <run_id>`
  validates schema, rollback gate counts, row restore readiness, next-run
  impact, and optional current receipt/config evidence before printing JSON.
- `config_application_restore_receipt.json` and
  `config_application_restore_receipt.md` record the result of the guarded
  restore-config-approved command. The command writes config only when the
  saved rollback preview is ready and all preview, receipt, and current config
  digests still match. Blocked attempts write a receipt but leave config
  unchanged.
- `config_lineage.json` and `config_lineage.md` connect config candidates,
  operator review, dry-run, apply receipt, rollback preview, and restore
  receipt artifacts into one read-only digest chain for the run.
  `python -m orchestrator.experiments config-lineage <run_id>` validates schema,
  stage order, stage counts, action flags, current-config summary, status, and
  optional current artifact evidence before printing JSON.
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
  status, config-lineage status, candidate quality trace status,
  champion/promotion review status, an operator-facing dashboard, and
  recommended next actions. The dashboard includes a read-only candidate
  quality review with selectable counts, selected directions, top failure code,
  and source path. It cannot execute agents, run backtests, write config,
  promote champions, apply patches, route agents, or change acceptance.
- `operator_action_plan.json` and `operator_action_plan.md` derive explicit
  command candidates from the saved closeout dashboard. They bind to
  `run_closeout.json` by SHA-256, mark commands that would write repository
  state, promote champions, or run backtests, and require explicit operator
  invocation for every candidate. Artifact validation rejects unknown command
  labels, expected-artifact mismatches, unsafe shell control tokens, invalid
  command prefixes, and command digest mismatches. They do not execute
  commands, execute agents, run backtests, write config, promote champions,
  route agents, apply patches, or change acceptance.
- `operator_action_approval.json` and `operator_action_approval.md` record
  operator approval for one action-plan command candidate. They bind to
  `operator_action_plan.json` by SHA-256 and require the exact confirmation
  phrase `APPROVE OPERATOR ACTION` for approval. Artifact validation replays
  the selected action and command lookup from the saved action plan and rejects
  selected-command drift, but approval still does not execute commands, write
  config, promote champions, run agents, rerun backtests, route candidates,
  apply patches, or change acceptance.
- `operator_action_execution_receipt.json` and
  `operator_action_execution_receipt.md` record guarded execution of one
  approved action-plan command. They execute only allowlisted read-only
  inspection commands, bind to `operator_action_approval.json` by SHA-256,
  verify selected action, selected command, execution command, argv, and
  evidence hashes against the saved approval, record stdout/stderr hashes, and
  check tracked workspace mutation. They block commands that write repository
  state, promote champions, run backtests, execute agents, apply patches, route
  agents, or change acceptance. The read-only allowlist includes the
  `quality-trace` experiment view for inspecting candidate quality failures
  after a repeated-proposal stop.
- `operator_action_audit.json` and `operator_action_audit.md` summarize the
  action plan, approval, and execution receipt chain. They validate source
  artifact schema state, source file hashes, selected command consistency, and
  next recommended operator step while also recording stable failure reasons
  with stage, code, severity, and detail fields. Their writer and terminal view
  reject stale or internally inconsistent payloads before returning them. They
  remain read-only.
- `operator_action_dashboard.json` and `operator_action_dashboard.md` turn the
  action plan, approval, execution receipt, and audit state into a compact
  operator next-step view. The iteration loop writes them during run closeout,
  and the explicit command can refresh them after later operator action
  artifacts. They list the timeline, selected command, safe command counts,
  audit failure reasons, blockers, and command hints, but cannot approve or
  execute anything. Artifact validation rejects unknown dashboard command
  labels, unexpected write targets, unsafe shell control tokens, and missing
  current-step/review commands.
- `operator_unlock_checklist.json` and `operator_unlock_checklist.md` expose
  Codex CLI operator-unlock evidence as a standalone read-only checklist. They
  classify saved preflight evidence groups and source hashes, then provide
  `navigation.expected_artifacts`, `navigation.blocking_items`, and
  `navigation.commands` so an operator can see the next artifact to inspect or
  generate. Artifact validation rejects unknown navigation command labels,
  artifact mismatches, write-flag mismatches, unsafe shell control tokens, and
  invalid command prefixes. The writer and terminal view validate saved or
  derived payloads against the schema and deterministic consistency checks
  before returning them, stripping terminal-only metadata before schema checks.
  Command rows are hints only; the checklist cannot record approval, execute
  Codex, create workspaces, apply patches, route
  agents, or change acceptance. Startup preflight failures for real Codex
  execute=true profiles still write the checklist before the loop exits, so
  no-round failed runs keep a deterministic blocker trail.
- `operator_cockpit.json` and `operator_cockpit.md` aggregate run review,
  config lineage, operator action, Codex CLI execution preflight, challenger
  comparison, candidate quality trace state, promotion review, promotion
  approval, and scope-health state into one read-only cockpit. The iteration
  loop writes them after the action dashboard, and the explicit command can
  refresh source hashes after later operator inspection artifacts. They list
  panels, blockers, primary focus, surfaced action failure reasons, candidate
  score/rejection navigation, Codex unlock checklist visibility, failed
  evidence groups, and command hints while preserving deterministic acceptance
  authority. Artifact validation rejects unknown cockpit command labels,
  unexpected write targets, unsafe shell control tokens, and a missing first
  `review_cockpit` command. The writer and terminal view validate status,
  focus, action failure summaries, unlock counts, review-priority references,
  and policy before returning payloads.
- `candidate_leaderboard.json` records every proposal attempt with stable
  quality metadata. `quality_breakdown` decomposes the pre-backtest candidate
  score into named components, selected rows also record validation and
  holdout EV deltas, and artifact validation checks that each saved
  `quality_breakdown.total_score` matches the candidate score and that each
  leaderboard row matches the round-local `proposal_attempts.json` row for the
  same `attempt_id`. These fields explain candidate routing only; final
  acceptance remains controlled by deterministic policy and holdout gates.
  `python -m orchestrator.experiments candidates <run_id> --limit N` reads the
  saved leaderboard as a terminal-only inspection view and validates the
  returned `candidate_leaderboard` payload against
  `schemas/candidate_leaderboard.schema.json` before printing. Its consistency
  checks enforce the requested limit, run identity, unique round/attempt pairs,
  stable candidate sort order, positive attempt indexes, quality-score binding,
  and selected-row validation/holdout signal presence without executing agents,
  rerunning backtests, routing candidates, applying patches, or changing
  acceptance.
- `agent_result_stats.json` aggregates the saved candidate leaderboard by
  agent, direction, and patch family, plus deterministic routing hints for
  future review. `python -m orchestrator.experiments agents <run_id>` returns
  the same read-only view with transient round replay status and validates the
  terminal payload against `schemas/agent_result_stats.schema.json` before
  printing. Its consistency checks recompute totals, grouped rows, patch-family
  rows, routing hints, source path binding, and replay summaries from saved
  run artifacts without executing agents, rerunning backtests, routing
  candidates, applying patches, or changing acceptance.
- `proposal_outcome_memory` is the terminal-only payload returned by
  `python -m orchestrator.experiments memory --limit N`. It reads
  `experiments/memory.jsonl`, returns only the bounded recent tail, validates
  against `schemas/proposal_outcome_memory.schema.json`, and checks core
  proposal outcome identity before printing JSON. It is an inspection view
  only and cannot execute agents, rerun backtests, route candidates, apply
  patches, delete memory, or change acceptance.
- `candidate_quality_trace.json` and `candidate_quality_trace.md` summarize
  the saved leaderboard into an inspection-only trace of score components,
  probe/validation/holdout signals, selected attempts, patch families, and
  failure codes. They read `candidate_leaderboard.json` only, keep
  `proposal_attempts.json` as the round source of truth, and artifact
  validation recomputes the saved source metadata, summary, round rows, and
  candidate rows from the leaderboard. The same payload validator checks writer
  and terminal output after stripping transient fields such as `from_artifact`,
  and can rebuild from current run evidence to catch drift before returning.
  They cannot route candidates, execute agents, run backtests, apply patches,
  or change acceptance.
- `modifier_profile_recommendation.json` and
  `modifier_profile_recommendation.md` translate saved candidate-quality and
  research-focus evidence into an advisory next modifier profile and direction
  for operator review. They bind to `candidate_quality_trace.json`,
  `research_brief.json`, and `config/default.json`, list available deterministic
  profiles, and rank matching profile/direction pairs. Artifact validation
  recomputes source metadata, profile rows, recommendations, summary, and
  policy from current evidence. They cannot write config, route agents,
  execute agents, run backtests, apply patches, or change acceptance.
- `candidate_challenger_report.json` and `candidate_challenger_report.md`
  compare saved candidate rows with the current champion registry when one
  exists. They expose validation gap, holdout stability flags, and top
  candidates for operator inspection only. The writer validates `ok` and
  status derivation, checks summaries, selected/top candidate counts and rows,
  top-candidate summary fields, per-candidate gap/status/stability derivations,
  recommended next actions, and read-only policy flags before returning. The
  same payload validator can check terminal output after stripping transient
  fields such as `from_artifact`, and can optionally rebuild the report from
  the current run evidence to catch drift before printing or writing. They
  cannot promote champions, route agents, run backtests, apply patches, or
  change acceptance.
- `champion_promotion_dry_run.json` and `champion_promotion_dry_run.md`
  preview whether the completed run would satisfy the deterministic champion
  promotion comparison against the current champion. The writer and artifact
  validator check derived `ok`, status, blocking reasons, promotion command,
  would-promote decision, recommended next actions, and read-only policy flags.
  They never write `champion.json`, append `champion_history.jsonl`, execute
  agents, run backtests, apply patches, route agents, or change acceptance.
  Actual guarded promotion uses the explicit `experiments promote-approved`
  command.
- `champion_promotion_approval.json` and `champion_promotion_approval.md`
  record operator review intent, required confirmation phrase hashes, reviewed
  promote command digests, and source evidence hashes. The writer and artifact
  validator check dry-run summary binding, command and source digest binding,
  approval eligibility, blockers, next actions, evidence file hashes, and
  non-promoting policy flags. They do not execute the promote command, write
  `champion.json`, append `champion_history.jsonl`, run agents, run backtests,
  apply patches, route agents, or change acceptance.
- `champion_promotion_receipt.json` and `champion_promotion_receipt.md` record
  the result of the guarded promote-approved command. The command writes
  `champion.json` and appends `champion_history.jsonl` only when the approval
  artifact, reviewed command digest, dry-run digest, current champion identity,
  and current deterministic comparison still match. The writer checks receipt
  status/promoted consistency, approval and dry-run digests, expected/reviewed
  commands, pre-promotion champion identity, promotion comparison/result fields,
  and guarded-write policy flags. The artifact validator reuses the non-source
  consistency checks without treating older blocked receipts as unhealthy after
  a later approval artifact refresh.
- `champion_lineage.json` and `champion_lineage.md` are read-only global
  experiment reports that connect `champion.json`, `champion_history.jsonl`,
  promotion receipts, approval artifacts, dry-run reports, and comparison
  metric deltas into one inspectable champion evolution chain. The writer
  validates history event and parse-error counts, row indexes, current-champion
  to last-history matching, `checks` summaries, receipt-derived promotion
  source labels, and read-only policy flags before returning. The same payload
  validator can check terminal output after stripping transient fields such as
  `from_artifact`, and can optionally rebuild the lineage from current
  champion/history evidence to catch drift before printing or writing. The
  experiment `summary` and `champion` inspection commands expose the same chain
  as compact embedded JSON fields for quick status checks, but only the
  `lineage` command writes `champion_lineage.json` and `champion_lineage.md`.
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
