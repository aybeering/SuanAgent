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
python -m orchestrator.experiments list --limit 5 --markdown
python -m orchestrator.experiments show <run_id>
python -m orchestrator.experiments show <run_id> --markdown
python -m orchestrator.experiments review <run_id>
python -m orchestrator.experiments review <run_id> --markdown
python -m orchestrator.experiments action-plan <run_id>
python -m orchestrator.experiments action-plan <run_id> --markdown
python -m orchestrator.experiments action-plan --latest --markdown
python -m orchestrator.experiments action-approval <run_id>
python -m orchestrator.experiments action-approval <run_id> --markdown
python -m orchestrator.experiments action-approval --latest --markdown
python -m orchestrator.experiments summary
python -m orchestrator.experiments summary --markdown
python -m orchestrator.experiments leaderboard --limit 5
python -m orchestrator.experiments leaderboard --limit 5 --markdown
python -m orchestrator.experiments memory --limit 5
python -m orchestrator.experiments memory --limit 5 --markdown
python -m orchestrator.experiments memory-diagnostics
python -m orchestrator.experiments memory-hygiene <run_id>
python -m orchestrator.experiments memory-hygiene <run_id> --markdown
python -m orchestrator.experiments memory-scope-recommendation <run_id>
python -m orchestrator.experiments memory-scope-recommendation <run_id> --markdown
python -m orchestrator.experiments diagnose <run_id>
python -m orchestrator.experiments diagnose <run_id> --markdown
python -m orchestrator.experiments candidates <run_id> --limit 5
python -m orchestrator.experiments candidates <run_id> --limit 5 --markdown
python -m orchestrator.experiments agents <run_id>
python -m orchestrator.experiments agents <run_id> --markdown
python -m orchestrator.experiments quality-trace <run_id>
python -m orchestrator.experiments quality-trace <run_id> --markdown
python -m orchestrator.experiments slots <run_id>
python -m orchestrator.experiments compare <base_run_id> <candidate_run_id>
python -m orchestrator.experiments champion
python -m orchestrator.experiments champion --markdown
python -m orchestrator.champion_lineage
python -m orchestrator.champion_lineage --markdown
python -m orchestrator.experiments lineage
python -m orchestrator.experiments lineage --markdown
python -m orchestrator.champion_promotion_dry_run experiments/<run_id>
python -m orchestrator.champion_promotion_dry_run experiments/<run_id> --markdown
python -m orchestrator.experiments promotion-dry-run <run_id>
python -m orchestrator.experiments promotion-dry-run <run_id> --markdown
python -m orchestrator.champion_promotion_approval experiments/<run_id>
python -m orchestrator.champion_promotion_approval experiments/<run_id> --markdown
python -m orchestrator.experiments promotion-approval <run_id>
python -m orchestrator.experiments promotion-approval <run_id> --markdown
python -m orchestrator.champion_promotion_executor <candidate_run_id> --approval-path experiments/<run_id>/champion_promotion_approval.json
python -m orchestrator.champion_promotion_executor <candidate_run_id> --approval-path experiments/<run_id>/champion_promotion_approval.json --markdown
python -m orchestrator.experiments apply-config-approved <run_id> --dry-run-path experiments/<run_id>/config_application_dry_run.json
python -m orchestrator.experiments config-application-rollback-preview <run_id> --receipt-path experiments/<run_id>/config_application_receipt.json
python -m orchestrator.experiments restore-config-approved <run_id> --preview-path experiments/<run_id>/config_application_rollback_preview.json
python -m orchestrator.config_operator_runbook experiments/<run_id>
python -m orchestrator.experiments config-runbook <run_id>
python -m orchestrator.experiments config-runbook <run_id> --markdown
python -m orchestrator.experiments config-lineage <run_id>
python -m orchestrator.experiments config-lineage <run_id> --markdown
python -m orchestrator.experiments promote-approved <candidate_run_id> --approval-path experiments/<run_id>/champion_promotion_approval.json
python -m orchestrator.operator_action_approval experiments/<run_id> --action-id <action_id> --command-label <label> --approve --operator-id <operator> --confirmation-phrase "APPROVE OPERATOR ACTION"
python -m orchestrator.operator_action_executor <run_id> --approval-path experiments/<run_id>/operator_action_approval.json
python -m orchestrator.experiments action-execution <run_id>
python -m orchestrator.experiments action-execution <run_id> --markdown
python -m orchestrator.experiments action-execution --latest --markdown
python -m orchestrator.operator_action_audit experiments/<run_id>
python -m orchestrator.experiments action-audit <run_id>
python -m orchestrator.experiments action-audit <run_id> --markdown
python -m orchestrator.experiments action-audit --latest --markdown
python -m orchestrator.operator_action_dashboard experiments/<run_id>
python -m orchestrator.experiments action-dashboard <run_id>
python -m orchestrator.experiments action-dashboard <run_id> --markdown
python -m orchestrator.experiments action-dashboard --latest --markdown
python -m orchestrator.operator_action_guide experiments/<run_id>
python -m orchestrator.experiments action-guide <run_id>
python -m orchestrator.experiments action-guide <run_id> --markdown
python -m orchestrator.experiments action-guide --latest --markdown
python -m orchestrator.operator_home experiments/<run_id>
python -m orchestrator.experiments home <run_id>
python -m orchestrator.experiments home <run_id> --markdown
python -m orchestrator.experiments home --latest --markdown
python -m orchestrator.operator_home experiments/<run_id> --next-command
python -m orchestrator.experiments next-command <run_id>
python -m orchestrator.experiments next-command --latest --markdown
python -m orchestrator.operator_unlock_checklist experiments/<run_id>
python -m orchestrator.experiments unlock-checklist <run_id>
python -m orchestrator.experiments unlock-checklist <run_id> --markdown
python -m orchestrator.experiments unlock-checklist --latest --markdown
python -m orchestrator.codex_cli_readiness_summary experiments/<run_id>
python -m orchestrator.codex_cli_unlock_runbook experiments/<run_id>
python -m orchestrator.experiments unlock-runbook <run_id>
python -m orchestrator.experiments unlock-runbook <run_id> --markdown
python -m orchestrator.experiments unlock-runbook --latest --markdown
python -m orchestrator.codex_cli_execution_readiness_diff experiments/<run_id>
python -m orchestrator.experiments execution-readiness-diff <run_id>
python -m orchestrator.experiments execution-readiness-diff <run_id> --markdown
python -m orchestrator.experiments execution-readiness-diff --latest --markdown
python -m orchestrator.operator_cockpit experiments/<run_id>
python -m orchestrator.experiments cockpit <run_id>
python -m orchestrator.experiments cockpit <run_id> --markdown
python -m orchestrator.experiments cockpit --latest --markdown
python -m orchestrator.experiments refresh-operator-views <run_id>
python -m orchestrator.experiments refresh-operator-views --latest --markdown
```

`python -m orchestrator.experiments list --limit N` returns recent append-only
index rows with derived `operator_home` and `operator_next_command` hints on
each row. Iteration-loop rows include the terminal-only `home <run_id>
--markdown` command, the narrower `next-command <run_id> --markdown`
selector, status, boundary, hint-only policy flags, next-command text, blocker
summary, command SHA-256 bindings, and next-command safety flags; single-run
rows mark both hints and next-command state unavailable. `list --markdown`
renders the recent-run table plus per-run `show <run_id> --markdown`, home, and
next-command navigation with the same command SHA-256 bindings and Codex
preflight next-step hint. The command does not rewrite `index.jsonl`, create
artifacts, execute commands, run agents, run backtests, apply patches, promote
champions, or change acceptance.

`python -m orchestrator.experiments show <run_id>` includes the same derived
`operator_home` and `operator_next_command` hints in the compact run payload.
Iteration-loop runs expose the terminal-only home markdown command, the
next-command selector command, and the selected command label, status, blocked
flag, blocker count, operator hint, command text, boundary, write target,
command SHA-256 bindings, approval flags, guarded-executor flag, and
hint-only flag, plus the Codex preflight next-step hint; single-run payloads
explicitly mark the home hint, selector hint, and next-command state
unavailable. `show <run_id> --markdown` renders the compact run record, round
table, and operator navigation as a terminal-only human view with the same
command digest bindings, Codex preflight next-step hint, and safety flags. These are
read-only convenience fields and do not rewrite index rows or create
`operator_home.json` or `operator_next_command.json` artifacts.

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
python -m orchestrator.run_artifact_health --limit 10 --strict --markdown
python -m orchestrator.run_artifact_health --all --record-history
python -m orchestrator.run_artifact_health --all --created-at-from 2026-06-02T00:00:00Z --strict
python -m orchestrator.run_artifact_health --history-summary
python -m orchestrator.run_artifact_health --history-summary --markdown
python -m orchestrator.run_artifact_health --history-summary --created-at-from 2026-06-02T00:00:00Z
python -m orchestrator.experiments validate --limit 10 --strict
python -m orchestrator.experiments validate --limit 10 --strict --markdown
python -m orchestrator.experiments health-history
python -m orchestrator.experiments health-history --markdown
python -m orchestrator.memory_diagnostics --strict
python -m orchestrator.memory_diagnostics --strict --markdown
python -m orchestrator.memory_diagnostics --created-at-from 2026-06-02T00:00:00Z --strict
python -m orchestrator.experiment_scope_health --created-at-from 2026-06-02T00:00:00Z --strict
python -m orchestrator.experiment_scope_health --created-at-from 2026-06-02T00:00:00Z --strict --markdown
python -m orchestrator.experiments scope-health --created-at-from 2026-06-02T00:00:00Z --strict
python -m orchestrator.experiments scope-health --created-at-from 2026-06-02T00:00:00Z --strict --markdown
python -m orchestrator.artifact_validator_coverage --output artifact_validator_coverage.json --markdown artifact_validator_coverage.md
python -m orchestrator.artifact_validator_coverage --strict
python -m orchestrator.experiments coverage
python -m orchestrator.experiments coverage --markdown
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
  config_operator_runbook.json
  config_operator_runbook.md
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
  codex_cli_unlock_runbook.json
  codex_cli_unlock_runbook.md
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
The artifact validator checks that the top-level run fields printed in
`summary.md` continue to mirror the same `manifest.json` values, including run
id, status, completed rounds, accepted round, stop reason, and final strategy
commit. It also checks the `summary.md` dataset, run-outcome, agent-intake,
Codex CLI execution preflight, health, codex-cli-unlock-runbook, config-lineage,
config-operator-runbook, config-application-dry-run, candidate-challenger,
champion-promotion-dry-run, champion-promotion-approval, run-closeout,
operator-action-plan, operator-action-dashboard, operator-cockpit,
operator-home, operator-next-command, operator-unlock-checklist, round-table,
best-validation-delta, proposal-quality, and candidate-leaderboard sections
against the corresponding
manifest records and round artifacts, so operator-facing data split, outcome,
health, navigation, per-round, proposal-quality, candidate-ranking, and
agent-output diagnosis fields stay tied to the machine-readable record.
`diagnosis.json` is a compact machine-readable review artifact built from the
saved run artifacts and validated against
`schemas/run_diagnosis.schema.json` before the file is written or terminal JSON
is printed. The saved-file validator also rebuilds the diagnosis from current
run-local artifacts and reports current-evidence drift when the saved diagnosis
no longer matches those sources; the run artifact validator surfaces the same
drift as a whole-run health warning because later operator artifacts may
legitimately advance after an earlier diagnosis snapshot. For iteration runs,
it includes per-round policy results, selected candidates, the best validation
round, and the same agent-intake summary and run-outcome summary so
adapter/proposal and gate failures can be grouped without changing acceptance.
It also includes an
`operator_navigation` block. Single-run diagnoses mark this navigation
unavailable. Iteration diagnoses copy the terminal-only operator-home command
and the narrower next-command selector from `manifest.json`, including the
source home command, selected command, blocked state, blocker count, first
blocker, Codex preflight next step, boundary, write target, command SHA-256
bindings, and safety flags.
The schema allows unavailable command digest fields to stay empty, but any
present diagnosis navigation command digest must use 64 lowercase hexadecimal
characters. Per-round patch SHA-256 fields must likewise be empty or
64-lowercase-hex strings.
The `--markdown` flag renders the same diagnosis navigation as a terminal-only
human review view with the same command digest bindings. These fields are
diagnosis hints only; they do not
create artifacts, record approval, execute commands, write config, promote
champions, run agents, run backtests, apply patches, route agents, or change
acceptance.
`python -m orchestrator.artifact_validator <run_id>` validates this block when
present, checking the diagnosis navigation against the saved
`manifest.operator_home` row and requiring all diagnosis navigation policy flags
to stay read-only. It also validates the saved diagnosis file against the local
schema. For iteration diagnoses, it binds the diagnosis run status,
completed-round count, accepted round, stop reason, final strategy commit, and
agent-intake summary back to `manifest.json`, and binds selected candidate rows
back to `candidate_leaderboard.json`. The saved diagnosis `best_round` must
match the best validation EV delta from `manifest.rounds` and the corresponding
diagnosis round row.

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
or markdown is printed. `champion --markdown` renders the same validated
status as a terminal-only champion, lineage, artifact, command, and read-only
policy view. It does not write champion registry files, append champion
history, promote champions, rerun backtests, route candidates, apply patches,
or change acceptance.
`python -m orchestrator.experiments memory --limit N` returns the recent
append-only proposal outcome memory records as a terminal-only
`proposal_outcome_memory` payload validated against
`schemas/proposal_outcome_memory.schema.json` before JSON is printed. Its
consistency checks bind the output to the bounded tail of
`experiments/memory.jsonl`, require proposal-outcome identity fields and a
boolean acceptance result, and keep the command read-only: it does not execute
agents, rerun backtests, route candidates, apply patches, delete memory, or
change acceptance. `memory --markdown` renders the same validated bounded tail
as a terminal-only outcome table with run/round, agent, direction,
acceptance, EV deltas, repeat-patch status, patch family, rejection reason,
and per-row diagnose/candidate command SHA-256 bindings without creating
artifacts or changing loop state.
`python -m orchestrator.experiments summary` additionally embeds a compact
dashboard with the latest indexed run, latest accepted and rejected runs, recent
diagnosis rows, recent failure-code counts, recent outcome-category counts, a
best-run-to-champion gap, a latest-run operator-home entry, a latest-run
operator-next-command entry, and an operator watchlist for repeated proposals,
artifact-health failures, and champion-gap alerts. Recent rows include the
saved `run_outcome_summary` category, primary stage, and primary code when the
run has an iteration diagnosis. The operator-home entry is available only when
the latest indexed run is an iteration loop; it surfaces the read-only `home
<run_id> --markdown` command, terminal-only flag, source, status, action step,
and Codex readiness snippets without creating an artifact. The
operator-next-command entry mirrors the home-selected next command and exposes
the read-only `next-command <run_id> --markdown` selector, selected command,
status, blocker summary, boundary, write target, source home command, and
command SHA-256 bindings without creating an artifact. The dashboard is
inspection-only and does not execute agents, run
backtests, apply patches, promote champions, or change acceptance.
The embedded dashboard is validated in memory against
`schemas/experiment_summary_dashboard.schema.json` before JSON or markdown is
printed, with deterministic consistency checks for recent failure/outcome
counts, top recent code/category fields, latest accepted/rejected status
summaries, latest-run to recent-tail binding, accepted-row flags,
operator-home run/command/boundary binding, operator-next-command selector,
source-home, and selected-command binding, champion-gap status and delta
invariants, watchlist alert counts, severity counts, status, alert codes, and
read-only policy flags.
`python -m orchestrator.experiments summary --markdown` renders the same
summary payload, including the latest-run operator-home entry,
operator-next-command entry, and watchlist, as a compact terminal-friendly
Markdown report without writing artifacts.
`python -m orchestrator.experiments leaderboard --limit N` returns the same
ranked run list shape as before, but validates the terminal-only
`experiment_leaderboard` payload against
`schemas/experiment_leaderboard.schema.json` before printing. The consistency
checks enforce the requested limit, descending EV-delta and creation-time
ordering, unique run IDs, single-run EV delta arithmetic, and non-negative
iteration completed-round counts. `leaderboard --markdown` renders the same
ranked rows as a terminal-only table with per-run
`show <run_id> --markdown` commands and command SHA-256 bindings, without
creating artifacts, rerunning backtests, promoting champions, or changing
acceptance.
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
`python -m orchestrator.experiments challenger <run_id>` writes or refreshes
`candidate_challenger_report.json` and `candidate_challenger_report.md` for the
selected run, then prints the same payload. `challenger --markdown` renders the
report for terminal inspection. The command is inspection-only: it does not
promote champions, route agents, execute agents, run backtests, apply patches,
or change acceptance.
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
`python -m orchestrator.experiments action-plan --latest` expose the same plan
without executing any command; add `--markdown` to render the terminal view as
markdown.
The plan records command digests, guarded-command flags, and deterministic
authority fields. The schema requires command candidate digests to use 64
lowercase hexadecimal characters. The writer and terminal view validate the
payload against `schemas/operator_action_plan.schema.json` and check summary
counts, action ids, action statuses, reason codes, command digests, policy
flags, and authority fields before returning. Artifact validation checks
command candidates through the shared operator command-hint validator for known
labels, expected artifacts, command prefixes, simple shell-control-token
guards, and matching command digests. The plan cannot write config, promote
champions, execute agents, run backtests, route candidates, apply patches, or
change acceptance.
`operator_action_approval.json` and `operator_action_approval.md` can then
record explicit operator approval for one action-plan command candidate. The
approval binds to `operator_action_plan.json`, records the selected action id,
command label, command digest, operator id, and confirmation phrase hashes.
The schema allows preview-state command and phrase digest fields to remain
empty, but any present approval command or confirmation digest must use 64
lowercase hexadecimal characters.
Artifact validation replays the selected action and command lookup from the
saved action plan so the approval cannot drift to a different command while
keeping a valid source digest. The writer and terminal view also validate the
payload against `schemas/operator_action_approval.schema.json` and check the
selected action, selected command, confirmation phrase hashes, approval gate,
status, recommended next actions, and read-only policy before returning.
Approval consistency validation reports field-specific drift for selected
action, selected command, operator intent, approval gate, and read-only policy
fields before the aggregate mismatch messages.
`python -m orchestrator.experiments action-approval --latest` resolves the
latest indexed iteration run while preserving optional `--action-id` and
`--command-label` filters.
Approval still does not execute the approved command. The approved command must
be invoked separately by the operator.
`operator_action_execution_receipt.json` and
`operator_action_execution_receipt.md` can then record the guarded execution of
an approved read-only inspection command. The receipt requires a saved approval
artifact, validates the selected command digest, verifies that the receipt's
selected action, selected command, execution command, argv, and evidence hashes
still match the saved approval, blocks commands that write repository state,
promote champions, run backtests, execute agents, route agents, apply patches,
or change acceptance, records schema-constrained command/source evidence hashes
and stdout/stderr output hashes, and checks tracked workspace mutation before
writing the receipt. The writer and terminal view
validate the payload against
`schemas/operator_action_execution_receipt.schema.json` and check source
approval binding, selected action and command equality, execution command and
argv, evidence fields, mutation guard, status, and policy before returning.
Execution receipt consistency validation reports field-specific drift for
source approval, selected action, selected command, evidence checks, command
execution, mutation guard, and read-only policy fields before aggregate
messages.
`python -m orchestrator.experiments action-execution --latest` resolves the
latest indexed iteration run and still only reads a saved execution receipt.
The allowlist includes `python -m orchestrator.experiments quality-trace
<run_id>`, so a repeated-proposal closeout can be followed by an approved
read-only inspection of `candidate_quality_trace.json` before choosing the next
deterministic modifier profile.
`operator_action_audit.json` and `operator_action_audit.md` connect the saved
action plan, approval, and execution receipt into one digest-checked read-only
chain. The audit records stable failure reasons with stage, code, severity, and
detail fields so operator views can report exactly which link broke. Command,
output, source-file, and chain digests are schema-constrained to empty or
64-lowercase-hex strings before consistency checks run. The writer and terminal
view validate the payload against
`schemas/operator_action_audit.schema.json` and check source artifact file
records, status, summary, selected action, selected command, execution record,
chain checks, next actions, and policy against the current digest chain before
returning.
The audit consistency validator reports field-specific drift for summary,
selected action, selected command, approval record, execution record, chain
check, and read-only policy fields before falling back to the full block
comparison.
`python -m orchestrator.experiments action-audit <run_id>`,
`python -m orchestrator.experiments action-audit --latest`, and `action-audit
--markdown` expose the saved or derived audit without executing commands,
writing config, promoting champions, running agents, running backtests,
applying patches, routing agents, or changing acceptance.
`operator_action_dashboard.json` and `operator_action_dashboard.md` summarize
the same chain into a compact next-step view. The iteration loop writes the
final dashboard during closeout after `operator_action_plan.json`; `python -m
orchestrator.experiments action-dashboard <run_id>`, `python -m
orchestrator.experiments action-dashboard --latest`, and `action-dashboard
--markdown` show or derive the current step, timeline, selected command, safe
command counts, audit failure reasons, blockers derived from those reason
codes, and suggested read-only/guarded commands with explicit boundary
classification (`read_only_inspection`, `read_only_artifact_refresh`,
`operator_approval_receipt`, or `guarded_read_only_execution`) plus SHA-256
bindings for each recommended command. The dashboard schema requires action-row
and recommended-command digests to use 64 lowercase hexadecimal characters and
source-file digests to be empty or 64-lowercase-hex strings, without recording
approval, executing commands, writing config, promoting champions, running
agents, running backtests, applying patches, routing agents, or changing
acceptance.
It also includes an `execution_readiness` summary that binds the current
action-chain status, first recommended command boundary, required dependency
artifacts, missing artifacts, blockers, selected-command digest status, and
guarded-executor readiness into one pre-execution checkpoint for the operator.
The companion `path_closure` summary records whether the operator action path
has closed across action plan, approval, guarded execution receipt, audit, and
dashboard evidence, with completed/required step counts and the same read-only
policy boundary.
The dashboard writer and terminal view validate the saved or derived payload
against
`schemas/operator_action_dashboard.schema.json` and checks that status-derived
fields plus action, command, failure-reason, and blocker counts still match the
embedded rows, including the execution-readiness and path-closure summaries.
Execution-readiness and path-closure validation also reports field-specific
drift for command boundary, readiness, closure, dependency, step, blocker, and
read-only policy fields before falling back to the full summary comparison.
Artifact validation checks dashboard command hints through the shared operator
command-hint validator for known labels, expected write targets, boundary
classification, current-step coverage, execution-readiness command binding,
path-closure completion rules, command SHA-256 bindings, and simple
shell-control-token guards.
`python -m orchestrator.experiments action-guide <run_id>`, `python -m
orchestrator.experiments action-guide --latest`, and `python -m
orchestrator.operator_action_guide experiments/<run_id>` expose a
terminal-only `operator_action_guide_v1` payload validated by
`schemas/operator_action_guide.schema.json`. The guide reads the saved or
derived action dashboard, reports the current step, first recommended command
with a SHA-256 digest, execution-readiness state, path-closure state, blockers,
a compact operator instruction, and a `guided_path` checklist covering
action-audit refresh, operator approval, guarded read-only execution, and
dashboard review. Each guided-path step and command sequence row includes
command text plus a SHA-256 digest for terminal review, and the schema requires
the next-command, command-sequence, and guided-path command digests to use 64
lowercase hexadecimal characters, while the source-dashboard file digest must
be empty or 64-lowercase-hex. It never records approval, executes commands,
writes config, promotes champions, runs agents, runs backtests, applies
patches, routes agents, or changes acceptance; all commands remain hints that
require the dedicated approval, guarded executor, audit, or dashboard commands.
The guide consistency validator reports field-specific drift for action state,
next-command safety, guidance, guided-path status, authority, and read-only
policy before falling back to the broader derived-block comparisons.
`python -m orchestrator.experiments home <run_id>` and `python -m
orchestrator.operator_home experiments/<run_id>` expose a terminal-only
`operator_home_v1` payload validated by `schemas/operator_home.schema.json`.
The home view derives from the current cockpit and action guide, then combines
run outcome, primary focus, guided action path, next command, next-command
safety flags, cockpit review priority, compact Codex CLI
preflight status and next step, unlock-runbook/readiness/intake-binding status, compact
command-center rows, blockers, and source view records into one operator
landing page. The safety flags surface whether the next command is hint-only,
requires explicit operator invocation, needs prior approval, records an
approval receipt, uses the guarded executor, and which artifact it would write
when invoked through the dedicated command. The home action summary also
reports whether the next command is currently blocked by home-level blockers,
how many blockers apply, the first blocker identity, and the operator hint to
review before invoking it.
The command center always includes the selected next command when it differs
from the action-guide command, so dynamic promotion follow-ups remain visible
next to the regular cockpit and guide command rows. Each command-center row
also carries a SHA-256 digest of its command text for terminal review. The
operator-home schema requires Codex review/runbook command digests, review
priority command digests, and command-center digests to use 64 lowercase
hexadecimal characters, and source-view file digests to be empty or
64-lowercase-hex strings.
The home consistency validator reports field-specific drift for the selected
action step, next-command safety flags, Codex readiness summary, authority
flags, and read-only policy before falling back to the full derived-payload
comparison.
When the guided operator action path is closed and the cockpit has a
deterministic champion-promotion approval pending, the home next-command hint
surfaces the cockpit promotion-approval command instead of leaving the operator
on the already-closed action receipt review. After that approval is recorded,
the home next-command hint advances to the guarded `promote-approved` command
that can write `champion_promotion_receipt.json`; after a successful promotion
receipt, it advances again to the read-only `lineage --markdown` refresh. Once
the saved global lineage matches current champion evidence, it stops repeating
the refresh hint and surfaces the read-only champion status view instead. These
commands are still only hints: approval, promotion, lineage refresh, and status
inspection remain explicit dedicated commands.
Its source records include the saved unlock checklist, unlock runbook,
readiness diff, promotion approval, promotion receipt, global champion lineage,
champion registry, and champion history so the first screen can point directly
at the evidence behind Codex readiness and promotion follow-up decisions
without becoming an unlock or promotion authority. It does not create run
artifacts, record approval, execute commands, write config, promote champions,
run agents, run backtests, apply patches, route agents, or change acceptance.
Completed iteration runs also record an `operator_home` manifest row and
`summary.md` section with the read-only markdown command, terminal-only flag,
current home status, action step, next-command label/status/blocked state,
next-command command text, boundary, blocker count, operator hint, write
target, explicit-invocation flag, approval flags, guarded-executor flag,
hint-only flag, selected-command SHA-256, home-command SHA-256, Codex
preflight next step, unlock-runbook status, and intake readiness status. These fields are
navigation hints only; they do not create an `operator_home.json` artifact or
grant execution authority.
The artifact validator checks that the saved `summary.md` operator-home section
continues to mirror the `manifest.operator_home` row, so operator-facing
markdown cannot silently drift from the machine-readable navigation record.
The saved `summary.md` also includes an `Operator Next Command` selector section
derived from the same manifest row. The validator binds its
`operator_home.next_command` source marker, selected command, status, blocker
state, boundary, write target, selected-command digest, and safety flags back
to `manifest.operator_home`, so the landing page and the narrow next-command
selector cannot drift apart. Those safety flags include whether the hint is
terminal-only, requires explicit operator invocation, requires approval,
records operator approval, or uses the guarded executor.
Before later operator action approval, execution, audit, or Codex readiness
artifacts advance the source evidence, the validator also rebuilds the
terminal-only next-command selector from current run evidence and checks the
compact `manifest.operator_home` next-command row against it, including command
text and digest, status, blocker state, boundary, write target,
digest-backed review priority, Codex preflight next step, readiness statuses,
Codex review and unlock-runbook command digests, source-home command and digest,
and hint-only safety flags. After
those later artifacts exist, the manifest row remains a closeout-time snapshot;
the validator still checks its static read-only and hint-only safety fields and
saved command digest bindings while terminal-only views derive the current next
step from the newer evidence.
When no run id is supplied, `home` resolves the latest indexed iteration-loop
run with a saved `manifest.json`; `--latest` makes the same selection explicit.
`python -m orchestrator.experiments next-command <run_id>`, `python -m
orchestrator.experiments next-command --latest`, and `python -m
orchestrator.operator_home experiments/<run_id> --next-command` expose a
terminal-only `operator_next_command_v1` narrow view validated by
`schemas/operator_next_command.schema.json`. It is derived from the same
operator home payload and returns only the selected command, status, blocker
count, boundary, write target, a structured navigation summary with the first
blocker and explicit-invocation readiness, safety flags, source-home command,
Codex readiness summary fields including the preflight next step, authority
flags, command SHA-256 bindings, and
read-only policy. Its markdown view also displays the selector source marker,
navigation summary, selected-command digest, source-home command digest, and
source-home terminal-only, artifact-free, hint-only boundary. It creates no artifact and
remains a hint; it does not record approval, execute commands, write config,
promote champions, run agents, run backtests, apply patches, route agents, or
change acceptance.
The selector consistency validator reports field-specific drift for the
selected command, source-home binding, safety flags, authority flags, and
read-only policy before falling back to the full derived-payload comparison.
The same selector command is also surfaced as a derived hint in
`experiments list`, `experiments show`, and the `experiment_summary_dashboard`
payload, so an operator can discover the narrow next-step view from recent run
history, per-run inspection, or the summary dashboard without creating any run
artifacts. These surfaces validate and display that the home and selector
remain terminal-only, artifact-free hints and that the selector's copied
selected-command status, boundary, write target, blocked state, blocker count,
compact navigation readiness, navigation summary, first blocker, next-step
hint, source marker, and safety flags still match the source operator-home row.
`operator_unlock_checklist.json` and `operator_unlock_checklist.md` expose the
Codex CLI operator-unlock evidence chain as a standalone read-only checklist.
The iteration loop writes it during closeout before the final cockpit so cockpit
source hashes bind to it. `python -m orchestrator.experiments unlock-checklist
<run_id>`, `python -m orchestrator.experiments unlock-checklist --latest`, and
`unlock-checklist --markdown` show the saved or derived checklist without
recording approval, executing Codex, executing agents, creating workspaces,
applying patches, routing agents, or changing acceptance. The
`navigation` section lists expected evidence artifacts, failed evidence groups,
blocking reason codes, related artifact paths, and command hints that still
require explicit operator invocation. Those command hints include SHA-256
bindings for the displayed command text, and each navigation artifact row binds
its manual write command with `write_command_sha256`. Artifact validation checks
those navigation command hints through the shared operator command-hint
validator for known labels, artifact ids, write flags, command SHA-256
bindings, command prefixes, and shell-control token safety, then checks artifact
write-command SHA-256 drift directly. The checklist writer and terminal view
validate saved or derived payloads against the schema and deterministic
consistency checks before
returning them, stripping terminal-only metadata before schema checks.
Those checks include top-level item counts, item-level failed-check and
blocker-code mappings, navigation blocking counts, primary blocker, expected
artifact ordering, command-hint coverage, artifact write-command digest binding,
and command digest bindings. The schema requires command and artifact write
command digests to use 64 lowercase hexadecimal characters. The
saved-file validator also rebuilds the checklist from current run evidence and
surfaces a
current-evidence mismatch when the saved checklist drifts. If real Codex
execute=true startup preflight is blocked before any round starts, the failed
run still writes this checklist and
the run summary points at the primary blocker. The checklist also includes a
read-only `codex_intake_readiness` block so an operator can distinguish
`not_available` intake evidence from blocked or ready selected-attempt binding
evidence.
`codex_cli_readiness_pipeline.json` records a read-only dependency-order
readiness run and includes `consistency_checks` that bind expected step order,
generated artifact file records, the final summary artifact hash, and
pipeline-level readiness fields. These checks are schema-validated audit
evidence only; they cannot execute Codex, create workspaces, route agents,
apply patches, or change acceptance. Step, generated-artifact, and final-summary
file SHA-256 fields are schema-constrained to empty-or-64-lowercase-hex strings.
`codex_cli_readiness_summary.json` stage artifact SHA-256 fields are
schema-constrained to empty-or-64-lowercase-hex strings.
`codex_cli_operator_unlock_request.json` records explicit operator intent plus
canonical file records for the readiness pipeline, execution unlock snapshot,
execution candidate, and real-execution dry-run artifacts. Artifact validation
and startup preflight re-check those recorded hashes so reviewed source
evidence cannot drift after the request is written. Request phrase, snapshot,
planned command, and source-file digests are schema-constrained to 64-lowercase
hex strings or empty-or-64-lowercase-hex strings where source evidence may be
absent.
`codex_cli_unlock_runbook.json` and `codex_cli_unlock_runbook.md` convert the
same Codex CLI unlock chain into an ordered operator guide. The iteration loop
writes it during closeout and no-round real-Codex startup failures after the
operator unlock checklist, while `python -m
orchestrator.codex_cli_unlock_runbook experiments/<run_id>` can refresh the
artifacts explicitly. `python -m orchestrator.experiments unlock-runbook
<run_id>`, `python -m orchestrator.experiments unlock-runbook --latest`, or
`unlock-runbook --markdown` shows the saved or derived guide. The runbook lists
the required evidence artifacts, readiness fields, status, and digest-backed
command hints, and artifact validation checks those operator commands through
the shared operator command-hint validator for known labels, write flags,
command SHA-256 bindings, command prefixes, and simple shell-control-token
guards. It also embeds the shared read-only
`codex_intake_readiness` block and binds its status, ready flag, and blocker
count into the runbook summary so selected-attempt intake binding is visible
from the ordered unlock guide. The runbook writer and terminal view
validate saved or derived payloads against the schema and deterministic
consistency checks before returning them, stripping terminal-only metadata
before schema checks. Those checks include step order, summary counters and
step lists, status and readiness fields, source checklist summaries, shared
Codex intake-readiness summaries, operator-command and artifact write-command
digest bindings, authority flags, read-only policy flags, and current-evidence
drift for derived payloads. Every
command still requires explicit operator invocation. It cannot record approval,
execute commands, execute Codex, create workspaces, route agents, apply
patches, or change acceptance.
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
current-evidence drift for derived payloads, and a shared
`codex_intake_readiness` summary. When saved canary or unlock evidence shows
unbound or blocked selected-attempt intake, the diff reports `blocked` with an
`intake_binding:*` blocker.
It is read-only and cannot record approval, execute commands, execute Codex,
create workspaces, modify config, route agents, apply patches, or change
acceptance. The iteration loop writes it automatically during closeout,
including no-round startup failures caused by blocked real Codex execute=true
preflight checks; explicit commands can refresh it after later operator
evidence artifacts are written. `python -m orchestrator.experiments
execution-readiness-diff <run_id>` and `python -m orchestrator.experiments
execution-readiness-diff --latest` expose the same read-only diff without
recording approval, executing Codex, creating workspaces, applying patches, or
changing acceptance.
`manifest.json` and `summary.md` also expose compact Codex CLI execution
preflight status and counts for total profiles, real-execution profiles,
operator-unlock ready profiles, canary-exempt profiles, and startup blockers;
artifact validation binds those fields back to the saved
`codex_cli_execution_preflight.json` summary, and requires the manifest status
to fall back to `missing` if that required startup artifact is absent. The
iteration writer and artifact validator use the same compact-row helper so the
operator-facing manifest view cannot drift from the validator expectation.
That helper only reports `operator_unlock_ready` when every real-execution
profile is operator-unlock ready; a real-execution profile with no blocker and
no matching ready count is surfaced as `operator_unlock_incomplete`. The
operator cockpit reuses the same startup-preflight status helper for its Codex
unlock panel and points incomplete unlock evidence back to operator review.
`operator_cockpit.json` and `operator_cockpit.md` collect the run closeout,
config lineage, operator action dashboard, Codex CLI execution preflight,
standalone operator unlock checklist, Codex CLI unlock runbook, Codex CLI execution readiness diff,
candidate challenger report, champion-promotion dry-run, promotion approval,
and scope-health status into a single read-only operator page. The Codex CLI
panels expose startup preflight status and next step, real-execution profile counts,
operator-unlock readiness counts, preflight blockers, grouped checklist status,
ordered runbook status, readiness diff missing/drift counts, and the shared Codex intake-binding
status, but they do not unlock or execute
Codex. The operator-action panel surfaces dashboard failure reasons as cockpit
action failure reasons and `operator_action:<code>` blockers so action-chain
breaks are visible from the top page. The iteration loop writes the final
cockpit after the dashboard, standalone checklist, unlock runbook, and readiness
diff so source hashes bind to the final closeout artifacts;
`python -m orchestrator.experiments cockpit <run_id>`, `python -m
orchestrator.experiments cockpit --latest`, and `cockpit --markdown` expose
panel rows, blockers, primary focus, a deterministic `review_priority`
navigation object, a first-screen `operator_digest`, and command hints with
SHA-256 bindings. Source-file digests are schema-constrained to empty or
64-lowercase-hex strings. The cockpit records this without recording approval,
executing commands, writing config, promoting champions, running agents,
running backtests, applying patches, routing agents, or changing acceptance.
The `review_priority` object
chooses the first panel and existing saved command hint to inspect from blocker,
config lineage, action, Codex readiness, challenger, promotion, scope-health,
and run-outcome state; the digest mirrors that priority plus the recommended
command boundary and command SHA-256 binding, action execution-readiness status,
outcome, blocker, config, action,
candidate-quality, Codex, and promotion status as a compact read-only header.
Artifact validation checks cockpit command hints through the shared operator
command-hint validator for known labels, expected write targets, the required
`review_cockpit` first command, command SHA-256 bindings, boundary
classification, and simple shell-control-token guards. It also cross-checks the
`review_priority` navigation object against the saved panel row, saved command
hint, command digest, and command boundary so the priority target cannot drift
from the cockpit payload it summarizes. The cockpit writer itself also
validates the operator digest,
status-derived OK and focus fields, action failure-reason
summaries,
`operator_action:<code>` blocker coverage, Codex unlock checklist counts, and
review-priority panel and command references before returning.
The `cockpit` terminal view validates saved or derived payloads through the
same schema and consistency checks before adding terminal-only metadata.
When the inspection command reads a saved
cockpit artifact, it adds a transient `snapshot_freshness` section that compares
recorded source hashes with the current source files and names stale sources
that require an explicit cockpit refresh. The refresh command hint includes a
SHA-256 binding. This freshness section is read-only inspection metadata and is
not stored in `operator_cockpit.json`.
`python -m orchestrator.experiments refresh-operator-views <run_id>` and
`python -m orchestrator.experiments refresh-operator-views --latest` are
explicit convenience commands that rewrite the existing read-only operator
action dashboard, Codex CLI execution preflight, operator unlock checklist,
Codex CLI unlock runbook, Codex CLI execution readiness diff, and operator
cockpit in dependency order.
It uses the run's recorded config path unless `--config` is provided, returns a
terminal-only `operator_view_refresh_v1` receipt with config source, path,
existence, SHA-256 fields, pre-refresh cockpit stale-source evidence,
post-refresh cockpit freshness, refresh-command SHA-256 bindings,
refresh-effect status, operator-review-required
flag, deterministic review reason codes, refreshed-cockpit operator digest
headline/priority/target-panel state, digest-backed next-command boundary,
action execution-readiness status, operator-home navigation status,
operator-home next-command text and SHA-256, first blocker, and safety flags, Codex
unlock-runbook status and command hint, Codex readiness-diff status, Codex
intake readiness status, blocker delta counts, and per-artifact JSON/Markdown
output hashes, and still
does not execute commands, execute Codex, run agents, run backtests, write
config, promote champions, apply patches, route agents, or change acceptance.
The receipt is validated in memory against
`schemas/operator_view_refresh.schema.json` before it is printed, with an
additional deterministic consistency check for refreshed artifact count and
order, per-artifact file-path bindings, blocker-delta counters, policy-summary
derivation, refresh-effect derivation, operator-digest command reason binding,
operator-digest command boundary binding, home-command hint-only binding,
home-command SHA-256 binding, snapshot-refresh command SHA-256 binding,
next-command SHA-256 binding, and copied home and review-summary next command,
safety, reason, boundary, first-blocker, and post-refresh blocker fields, even
though it is not written as a new artifact family.
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

`agent_bundle_manifest.json` records the bundled input and output files with
schema-constrained 64-lowercase-hex SHA-256 file digests.

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
- `agent_execution.json`, when present, records guarded external-adapter
  execution. Its `intake_binding` section starts as `unbound` at execution time
  and is updated for the selected attempt after `agent_validation.json` is
  written, binding command, prompt/stdin, raw response, saved proposal, and
  validation evidence. Execution audit command, stream, file, proposal-patch,
  and preflight command digests are schema-constrained to
  empty-or-64-lowercase-hex strings. This proves selected external output went
  through the shared intake path before quarantine or patch application.
  Codex-specific contract fixtures, local canary gates, and final execution
  unlock gates also require this selected execution binding to be present and
  blocker-free before they can report readiness. Guarded Codex CLI audits also
  carry `preflight_binding`, which binds the saved command digest, run identity,
  startup preflight run identity and ok state, workspace prefix, strategy-only
  mutation allowlist, and mutation guard back to the startup
  `codex_cli_execution_preflight.json` profile. Startup preflight operator-request
  file hashes and expected command digests are schema-constrained to
  empty-or-64-lowercase-hex and 64-lowercase-hex strings. Local canary and final
  unlock readiness also require that preflight binding to be blocker-free, and
  artifact validation re-derives canary gate rows from the current source
  artifacts to detect stale saved readiness. Canary gate file validation now
  also exposes stale rows as a current-evidence mismatch. Final unlock gate
  validation is also re-derived from current replay, enablement, manual
  approval, canary, real-preflight, and dry-invocation evidence. Direct unlock
  gate file validation reports stale aggregate evidence as a current-evidence
  mismatch while the full artifact validator keeps detailed upstream mismatch
  errors. Direct unlock snapshot file validation rechecks the canonical unlock
  gate and frozen evidence file records before surfacing stale snapshots as
  current-evidence mismatches. Direct execution candidate file validation
  re-derives the future command, workspace path, strategy-only mutation
  boundary, and candidate config binding from the canonical unlock snapshot
  before surfacing stale candidate plans as current-evidence mismatches.
  Direct real-execution dry-run file validation rechecks the canonical
  candidate, planned command, planned workspace path, and
  workspace-not-created state before surfacing stale dry-run boundaries as
  current-evidence mismatches. Real preflight file validation re-runs the
  harmless version probe against the current candidate config, so stale
  executable or config evidence is surfaced before execution can be unlocked.
  Dry-invocation guard file validation stays read-only while replaying current
  config, prompt, execution-audit, and workspace evidence, so stale dry-run
  evidence surfaces without invoking Codex again. Manual approval validation
  also replays its saved approval intent against the current enablement gate
  and candidate config, so stale approval snapshots surface as current-evidence
  mismatches while keeping the approval artifact non-executing.
- `agent_output.json` stores normalized selected proposal data and the
  proposal intent summary used by the round-level agent input. Its selected
  proposal uses `schemas/strategy_proposal.schema.json`, including an
  empty-or-64-lowercase-hex `patch_sha256` binding when a patch is present.
  Attempt rows and selection-report rows schema-constrain their patch SHA-256
  fields the same way.
- `agent_validation.json` records contract, patch-target, `git apply` checks,
  and the proposal intent summary used by the validated agent input. It also
  records schema-validated consistency checks that bind the raw output,
  normalized proposal fields, empty-or-64-lowercase-hex patch hash, semantic
  checks, and validation result. Its embedded proposal uses the same shared
  strategy proposal schema;
  the `semantic_checks` object records deterministic protocol, target, metadata,
  and patch-target rule results that control contract pass/fail before `git
  apply` can run. The `intake_diagnosis` object summarizes the primary stable
  failure code, all blocking codes, retryability, and git-apply status so
  external-adapter failures can be grouped without parsing free-form text. It
  also records raw output byte counts and rejects oversized output before JSON
  or diff parsing with the stable `raw_output_too_large` code. The semantic
  checks also bound normalized `patch_diff` size and reject oversized patches
  with `patch_diff_too_large` before `git apply` can run.
- `agent_output_quarantine.json` records whether selected output is held or
  released before git apply, including the same proposal intent summary used by
  `agent_output.json`. It also records schema-validated consistency checks that
  bind release status, selected attempt id, patch hash, validation status, and
  source artifact hashes before any patch can be applied. Its proposal patch
  hash, consistency-check patch hash, and artifact file SHA-256 digests are
  schema-constrained before release.
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
  input contract. Its `target_file_sha256` field schema-constrains the target
  strategy snapshot binding to a 64-lowercase-hex SHA-256 digest.
- `agent_execution_plan.json` records the planned candidate queue and each
  profile's declared direction capability before any modifier runs. It also
  binds the same `proposal_intent_summary` into each attempt input contract so
  planned candidates can be audited against the planner context they will see.
- `agent_routing_policy.json` explains deterministic candidate ranking,
  including whether each proposal direction matched the profile's declared
  capability and whether it matched or auditably deviated from
  `proposal_intent.json`. Artifact validation recomputes the capability and
  alignment booleans from each saved candidate row so schema-valid drift in
  those audit fields is reported. Candidate patch hashes are schema-constrained
  to empty-or-64-lowercase-hex strings.
- `agent_executor_report.json`, `agent_attempts_manifest.json`,
  `attempt_output.json`, `agent_selection_report.json`, `agent_routing_policy.json`,
  `agent_output.json`, and `candidate_leaderboard.json` all carry the candidate
  score and `quality_breakdown` so the saved trace can prove why a candidate was
  selected without giving those artifacts final acceptance authority. The
  executor, routing, selection, and attempts manifests schema-constrain proposal
  or attempt patch hashes, while the attempts manifest also constrains saved
  file hashes to empty-or-64-lowercase-hex strings.
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
- `agent_golden_replay.json` freezes one saved agent input/output pair as a
  replayable protocol fixture. Its saved and replayed patch/raw-output
  SHA-256 comparison fields are schema-constrained to
  empty-or-64-lowercase-hex strings.
- `attempt_output.json` links one saved attempt's input, proposal, raw output,
  patch, selection explanation, validation status, proposal intent summary, and
  optional execution audit.
- `round_replay.json` validates all saved planned attempts for a round.
- `agent_slot_health.json` summarizes slot readiness, audits, and replay state.
  Saved slot-health reports are strict snapshots: validators recompute them
  from current run-local plan, attempt manifest, replay, workspace, and
  execution-audit evidence and fail when the saved report no longer matches.
- `agent_slot_readiness_gate.json` blocks future external agent slots until
  input, output, workspace, execution-audit, and replay evidence is present.
  Saved readiness-gate reports are also strict snapshots and fail validation
  when the current run-local evidence no longer matches the saved gate.
- `external_agent_sandbox_drill.json` audits external-slot command, workspace,
  input, output, subprocess, and mutation-guard evidence without executing
  agents. Each source execution-plan and executor-report artifact, declared
  command, workspace manifest, and execution-audit artifact carries a SHA-256
  binding. The round and attempt agent inputs, input bundle, and declared round
  output files carry SHA-256 bindings as well, so operator review can compare
  the exact source evidence, external command, isolation policy, saved
  execution evidence, delivered input context, and produced output artifacts
  without invoking it.
  The paired markdown report includes compact source-artifact hash summaries
  plus output-file presence and hash columns for terminal review.
  Saved sandbox-drill reports are strict snapshots and fail validation when
  current run-local boundary evidence no longer matches the saved drill. The
  paired markdown report must also exist and match the JSON report's
  deterministic render.
- `codex_cli_contract_fixture.json` freezes guarded Codex CLI stdin/stdout
  expectations without executing Codex. Its prompt, audit-stdin, fixture-stdout,
  and fixture-patch SHA-256 fields are schema-constrained to
  empty-or-64-lowercase-hex strings.
- `codex_cli_replay_gate.json` gates future Codex CLI enablement using saved
  guarded-execution audit, contract fixture, quarantine, and round-replay
  evidence. Saved replay-gate reports are strict snapshots and fail validation
  when current run-local Codex readiness evidence no longer matches the gate.
  Per-slot artifact record SHA-256 fields are schema-constrained to
  empty-or-64-lowercase-hex strings.
- `codex_cli_enablement_gate.json` gates an explicit execute-true candidate
  config against the saved replay gate before any guarded Codex CLI enablement.
  Saved enablement-gate reports are strict snapshots and fail validation when
  current candidate-config or replay-gate evidence no longer matches the gate.
  Its replay-gate and candidate-config artifact SHA-256 fields are
  schema-constrained to empty-or-64-lowercase-hex strings.
- `codex_cli_manual_approval.json` records explicit operator approval for a
  passing enablement gate without executing Codex. Its approval phrase digests
  must be 64-lowercase-hex strings, and its enablement-gate and
  candidate-config artifact SHA-256 fields are schema-constrained to
  empty-or-64-lowercase-hex strings.
- `run_artifact_health.json` batch-validates saved experiment run artifacts
  and reports per-run artifact health without rerunning simulations.
  `--created-at-from` scopes indexed runs to a current contract era without
  deleting older experiment directories. The direct `--markdown` mode and
  `python -m orchestrator.experiments validate --markdown` render the same
  bounded read-only run rows for terminal review without executing agents,
  rerunning backtests, applying patches, or changing acceptance.
- `run_artifact_health_history.jsonl` appends compact health snapshots when
  explicitly requested or when the iteration loop completes, and
  `run_artifact_health_history_v1` summaries show repeated failing runs and
  artifact filenames. Automatic iteration records use the run's startup
  timestamp as the scope boundary. The same `--created-at-from` scope can
  exclude legacy failed runs from the summary without rewriting history.
  `python -m orchestrator.run_artifact_health --history-summary --markdown` and
  `python -m orchestrator.experiments health-history --markdown` render the same
  bounded read-only summary for terminal review without executing agents,
  rerunning backtests, applying patches, or changing acceptance.
- `memory_diagnostics.json` cross-references proposal outcome memory with
  artifact-health history by run id, agent, profile, direction, and patch hash.
  `--created-at-from` applies the same current-contract scope to outcome memory
  and indexed health runs. It is inspection-only and cannot execute agents, run
  backtests, route agents, apply patches, or change acceptance.
  `python -m orchestrator.memory_diagnostics` and
  `python -m orchestrator.experiments memory-diagnostics` validate the terminal
  payload against `schemas/memory_diagnostics.schema.json` and the current
  source artifacts before printing JSON or markdown. The `--markdown` view
  summarizes totals, matched and unmatched failed health runs, top groups, and
  recent outcome-health links with bounded lists for terminal review.
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
  artifacts for schema and internal consistency before printing JSON or
  markdown with terminal metadata.
- `memory_scope_recommendation.json` and `memory_scope_recommendation.md`
  summarize whether the current outcome-memory scope should remain full-history
  or be narrowed for future runs with a recent-record limit. They read saved
  hygiene artifacts only, never write config, never delete memory, never route
  candidates, never apply patches, and never change acceptance.
  `python -m orchestrator.memory_scope_recommendation` and
  `python -m orchestrator.experiments memory-scope-recommendation <run_id>`
  validate the terminal payload against the schema and deterministic
  recommendation derivation before printing JSON or markdown.
  The saved-file validator reports field-specific drift for source evidence,
  scope, observed totals, recommendation fields, candidate scopes, and read-only
  policy fields.
- `config_change_candidate.json` and `config_change_candidate.md` convert
  saved recommendations into operator-reviewed config field candidates, such as
  `memory_filter.recent_record_limit` or a guarded `agents` fallback profile
  when `modifier_profile_recommendation.json` reports `no_available_profile`.
  They include current value, proposed value, rationale, reason codes, and risk
  notes, but they never write config, route candidates, apply patches, run
  backtests, or change acceptance.
  `python -m orchestrator.experiments config-change-candidate <run_id>` and
  `python -m orchestrator.experiments config-change-candidate <run_id> --markdown`
  validate schema, run binding, candidate summary, and operator-review status
  before printing JSON or markdown. The saved-file validator reports
  field-specific drift for source file records, summary fields, candidate
  change rows, operator-review status, and read-only policy fields.
- `operator_config_review.json` and `operator_config_review.md` record
  operator approve or reject intent for saved config candidates. Approval
  requires the configured confirmation phrase, rejection can be recorded without
  applying anything, and both paths remain audit-only: they never edit config,
  route candidates, apply patches, run backtests, or change acceptance.
  `python -m orchestrator.experiments operator-config-review <run_id>` and
  `python -m orchestrator.experiments operator-config-review <run_id> --markdown`
  validate schema, candidate summary, review gate, reviewed-row decisions, and
  next actions before printing JSON or markdown.
  The consistency validator reports field-specific drift for candidate summary,
  operator intent, review gate, reviewed changes, and read-only policy fields.
  The saved-file validator also checks current source candidate evidence and
  reports source-file, summary, intent, gate, row, and policy drift before
  surfacing a current-evidence mismatch.
- `config_application_dry_run.json` and `config_application_dry_run.md` preview
  whether approved config candidates still match the current config value and
  are ready for a later manual edit. They remain dry-run only and never edit
  config, route candidates, apply patches, run backtests, or change acceptance.
  `python -m orchestrator.experiments config-application-dry-run <run_id>` and
  `python -m orchestrator.experiments config-application-dry-run <run_id> --markdown`
  validate schema, application gate counts, planned-row readiness, status, and
  next actions before printing JSON or markdown.
  The consistency validator reports field-specific drift for source files,
  operator intent, application gate, planned changes, and read-only policy
  fields.
  The saved-file validator also rebuilds the dry run from current operator
  review and config evidence, then reports source, intent, gate, row, and policy
  drift before surfacing a current-evidence mismatch.
- `config_application_receipt.json` and `config_application_receipt.md` record
  the result of the guarded apply-config-approved command. The command writes
  config only when the saved dry-run is ready, the operator-review digest still
  matches, and the current config digest still matches the reviewed dry-run.
  Receipts preserve whether each reviewed config path existed before the
  application, so restore can delete newly-added fields instead of writing
  `null`. Blocked attempts write a receipt but leave config unchanged.
  `python -m orchestrator.experiments apply-config-approved <run_id>` and
  `python -m orchestrator.experiments apply-config-approved <run_id> --markdown`
  write the guarded receipt and print JSON or markdown, preserving blocked
  attempts as non-zero exits. The receipt validator reports field-specific
  drift for source dry-run and operator-review hashes, evidence-check fields,
  applied-change rows, and guarded write policy fields while treating a later
  restore receipt as historical closeout evidence.
- `config_application_rollback_preview.json` and
  `config_application_rollback_preview.md` read a saved application receipt and
  current config to preview manual restore rows and next-run impact. They are
  read-only and never restore config automatically.
  `python -m orchestrator.experiments config-application-rollback-preview <run_id>`
  and `python -m orchestrator.experiments config-application-rollback-preview <run_id> --markdown`
  validate schema, rollback gate counts, row restore readiness, next-run
  impact, and optional current receipt/config evidence before printing JSON or
  markdown.
  The consistency validator reports field-specific drift for source receipt
  and config hashes, rollback gate fields, rollback-plan rows, next-run impact,
  and read-only policy fields.
  The saved-file validator also rechecks current receipt/config evidence and
  surfaces a current-evidence mismatch when the saved preview no longer matches
  the deterministic rebuild.
- `config_application_restore_receipt.json` and
  `config_application_restore_receipt.md` record the result of the guarded
  restore-config-approved command. The command writes config only when the
  saved rollback preview is ready and all preview, receipt, and current config
  digests still match. If an applied candidate added a previously missing
  config path, restore removes that path. Blocked attempts write a receipt but
  leave config unchanged. `python -m orchestrator.experiments
  restore-config-approved <run_id>` and `python -m orchestrator.experiments
  restore-config-approved <run_id> --markdown` write the guarded receipt and
  print JSON or markdown while preserving blocked attempts as non-zero exits.
  The receipt validator reports field-specific drift for source preview and
  receipt hashes, restore gate fields, restored-change rows, and guarded write
  policy fields, then surfaces a current-evidence mismatch when those saved
  receipt fields no longer match the current preview/config evidence.
- `config_operator_runbook.json` and `config_operator_runbook.md` summarize the
  config candidate, operator review, application dry-run, guarded apply,
  rollback preview, guarded restore, and lineage chain into one ordered
  operator guide. The iteration loop writes it during closeout after the final
  config lineage artifact. The runbook lists digest-backed command hints, marks
  which commands would write config if explicitly invoked, and remains
  read-only: it never records approval, executes commands, writes config,
  restores config, runs agents, or changes acceptance. `python -m
  orchestrator.experiments config-runbook <run_id>` validates schema, step
  ordering, command SHA-256 bindings, command safety, summary counters,
  authority flags, current artifact evidence, and read-only policy before
  printing JSON or markdown. The saved-file validator reports field-specific
  drift for source fields, summary counters, step rows, command hints, and
  read-only policy fields.
- `config_lineage.json` and `config_lineage.md` connect config candidates,
  operator review, dry-run, apply receipt, rollback preview, and restore
  receipt artifacts into one read-only digest chain for the run.
  `python -m orchestrator.experiments config-lineage <run_id>` validates schema,
  stage order, stage counts, action flags, current-config summary, status, and
  current artifact evidence before printing JSON or markdown. The saved-file
  validator reports field-specific drift for current-config fields, stage rows,
  lineage checks, and read-only policy fields.
- `experiment_scope_health.json` combines current artifact health,
  artifact-health history, and memory diagnostics for one `--created-at-from`
  scope. It is a read-only status page and marks the scope unhealthy if any
  component has read errors, current artifact failures, historical scoped
  failure observations, or memory-linked failed health runs. The iteration loop
  writes it automatically at run completion using the run's startup timestamp
  as the current-contract scope boundary. The direct
  `python -m orchestrator.experiment_scope_health --markdown` command and
  `python -m orchestrator.experiments scope-health --markdown` render the same
  terminal-only health summary without writing config, running agents,
  rerunning backtests, routing candidates, applying patches, or changing
  acceptance.
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
  recommended next actions. The saved-file validator rebuilds the closeout from
  the current run-local source artifacts and reports current-evidence drift
  when the saved closeout no longer matches those sources; the run artifact
  validator surfaces the same drift as a whole-run health warning because later
  operator artifacts may legitimately advance after an earlier closeout
  snapshot. The dashboard includes a read-only candidate quality review with
  selectable counts, selected directions, top failure code, and source path. It
  cannot execute agents, run backtests, write config,
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
  after a repeated-proposal stop and the `promotion-approval` experiment view
  for refreshing the non-promoting champion approval inspection artifact.
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
  artifact mismatches, write-flag mismatches, artifact write-command SHA-256
  drift, malformed command digest strings, unsafe shell control tokens, and
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
  a first-screen operator digest, panels, blockers, primary focus, surfaced
  action failure reasons, candidate score/rejection navigation, Codex unlock
  checklist visibility, failed evidence groups, and command hints while
  preserving deterministic acceptance authority. Artifact validation rejects
  unknown cockpit command labels,
  unexpected write targets, unsafe shell control tokens, and a missing first
  `review_cockpit` command. The writer and terminal view validate status,
  focus, operator-digest derivation, action failure summaries, unlock counts,
  review-priority references, and policy before returning payloads.
- `candidate_leaderboard.json` records every proposal attempt with stable
  quality metadata. `quality_breakdown` decomposes the pre-backtest candidate
  score into named components, selected rows also record validation and
  holdout EV deltas, and artifact validation checks that each saved
  `quality_breakdown.total_score` matches the candidate score and that each
  leaderboard row matches the round-local `proposal_attempts.json` row for the
  same `attempt_id`. Leaderboard patch hashes are schema-constrained to
  empty-or-64-lowercase-hex strings. These fields explain candidate routing
  only; final acceptance remains controlled by deterministic policy and holdout
  gates.
  `python -m orchestrator.experiments candidates <run_id> --limit N` reads the
  saved leaderboard as a terminal-only inspection view and validates the
  returned `candidate_leaderboard` payload against
  `schemas/candidate_leaderboard.schema.json` before printing. Its consistency
  checks enforce the requested limit, run identity, unique round/attempt pairs,
  stable candidate sort order, positive attempt indexes, quality-score binding,
  and selected-row validation/holdout signal presence without executing agents,
  rerunning backtests, routing candidates, applying patches, or changing
  acceptance. `candidates <run_id> --markdown` renders the same validated rows
  as a terminal-only table with selected status, candidate score,
  validation/holdout deltas, failure navigation, read-only policy flags, and
  per-run show/diagnose command SHA-256 bindings, without creating artifacts or
  changing the loop state.
- `agent_result_stats.json` aggregates the saved candidate leaderboard by
  agent, direction, and patch family, plus deterministic routing hints for
  future review. `python -m orchestrator.experiments agents <run_id>` returns
  the same read-only view with transient round replay status and validates the
  terminal payload against `schemas/agent_result_stats.schema.json` before
  printing. Its consistency checks recompute totals, grouped rows, patch-family
  rows, routing hints, source path binding, and replay summaries from saved
  run artifacts without executing agents, rerunning backtests, routing
  candidates, applying patches, or changing acceptance. `agents <run_id>
  --markdown` renders the same validated payload as compact agent, direction,
  patch-family, routing-hint, and round-replay tables with candidate
  leaderboard and diagnosis command SHA-256 bindings. It remains terminal-only
  and does not create artifacts or change loop state.
- `proposal_outcome_memory` is the terminal-only payload returned by
  `python -m orchestrator.experiments memory --limit N`. It reads
  `experiments/memory.jsonl`, returns only the bounded recent tail, validates
  against `schemas/proposal_outcome_memory.schema.json`, and checks core
  proposal outcome identity before printing JSON or markdown. It is an
  inspection view only and cannot create artifacts, execute agents, rerun
  backtests, route candidates, apply patches, delete memory, or change
  acceptance.
- `candidate_quality_trace.json` and `candidate_quality_trace.md` summarize
  the saved leaderboard into an inspection-only trace of score components,
  probe/validation/holdout signals, selected attempts, patch families, and
  failure codes. They read `candidate_leaderboard.json` only, keep
  `proposal_attempts.json` as the round source of truth, and artifact
  validation recomputes the saved source metadata, summary, round rows, and
  candidate rows from the leaderboard. The same payload validator checks writer
  and terminal output after stripping transient fields such as `from_artifact`,
  and can rebuild from current run evidence to catch drift before returning.
  `python -m orchestrator.experiments quality-trace <run_id>` prints the
  validated terminal payload as JSON or markdown for operator inspection.
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
  change acceptance. The direct module `--markdown` mode and
  `python -m orchestrator.experiments challenger <run_id> --markdown` render
  the report as terminal markdown.
- `champion_promotion_dry_run.json` and `champion_promotion_dry_run.md`
  preview whether the completed run would satisfy the deterministic champion
  promotion comparison against the current champion. The writer and artifact
  validator check derived `ok`, status, blocking reasons, promotion command,
  would-promote decision, recommended next actions, and read-only policy flags.
  They never write `champion.json`, append `champion_history.jsonl`, execute
  agents, run backtests, apply patches, route agents, or change acceptance.
  The direct module `--markdown` mode and
  `python -m orchestrator.experiments promotion-dry-run <run_id> --markdown`
  render the same preview as terminal markdown. Actual guarded promotion uses
  the explicit `experiments promote-approved` command.
- `champion_promotion_approval.json` and `champion_promotion_approval.md`
  record operator review intent, required confirmation phrase hashes, reviewed
  promote command digests, and source evidence hashes. The writer and artifact
  validator check dry-run summary binding, command and source digest binding,
  approval eligibility, blockers, next actions, evidence file hashes, and
  non-promoting policy flags. They do not execute the promote command, write
  `champion.json`, append `champion_history.jsonl`, run agents, run backtests,
  apply patches, route agents, or change acceptance. The direct module
  `--markdown` mode and
  `python -m orchestrator.experiments promotion-approval <run_id> --markdown`
  render the same non-promoting approval artifact as terminal markdown. The
  `promotion-approval` experiment view is also eligible for guarded read-only
  operator action execution because it writes only the approval inspection
  artifact and cannot promote a champion.
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
  The direct executor module can also print the same receipt as markdown.
  `python -m orchestrator.experiments promote-approved <candidate_run_id>` and
  `python -m orchestrator.experiments promote-approved <candidate_run_id> --markdown`
  write the guarded receipt and print JSON or markdown, preserving blocked
  attempts as non-zero exits.
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
  as compact embedded JSON fields for quick status checks. The direct module
  `--markdown` mode and `python -m orchestrator.experiments lineage --markdown`
  write `champion_lineage.json` and `champion_lineage.md`, then print the same
  validated payload as a terminal-friendly markdown view.
- `python -m orchestrator.experiments promote <base_run_id> <candidate_run_id>`
  remains available as a legacy deterministic helper for tests and fixtures,
  but operator-facing promotion should use `promote-approved` with a recorded
  approval artifact.
- `artifact_validator_coverage.json` reports schema, validator, documentation,
  test, inspection/replay, and local schema-keyword support coverage for
  repository artifact contracts.
  `python -m orchestrator.experiments coverage --markdown` renders the same
  bounded read-only coverage summary for terminal review without validating run
  artifacts, executing agents, rerunning backtests, applying patches, or
  changing acceptance.

## Validation

Use `python -m orchestrator.artifact_validator <run_id>` after a run. The
validator checks required files, schema validity, artifact hashes, source-path
bindings, role authority invariants, visual artifact locality, workspace audit
records, and Codex readiness evidence when present.
