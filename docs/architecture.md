# Architecture

SuanAgent is a deterministic V0.5 control-flow prototype for strategy
self-iteration. It is intentionally small: the system can propose, test, accept,
reject, roll back, and audit strategy changes without giving natural-language
agents final decision authority.

## Runtime Flow

The single-run V0 loop lives in `orchestrator/run_loop.py`:

1. Run the baseline strategy and current strategy on fixed validation data.
2. Write trades, metrics, markdown reports, diagnosis, metadata, and decision
   artifacts under `experiments/<run_id>/`.
3. Compare metrics through deterministic policy rules.

The multi-round V0.5 loop lives in `orchestrator/iteration_loop.py`:

1. Create `experiments/<run_id>/`.
2. Run startup preflight and write activation artifacts.
3. For each round, evaluate the current strategy on train, validation, and
   holdout data.
4. Build agent context, proposal intent, role-readiness, visual, analysis, and
   execution-plan artifacts.
5. Invoke the selected deterministic modifier backend.
6. Normalize output into the shared proposal contract.
7. Validate patch target, proposal contract, outcome-memory filters, and
   `git apply --check`.
8. Apply the patch, rerun train/validation/holdout evaluation, then run the
   validation policy gate plus holdout veto.
9. Commit accepted strategy changes or roll rejected patches back.
10. Stop on acceptance, repeated failed proposal, no-improvement policy, max
    rounds, or a deterministic failure.

## Authority Model

Final acceptance belongs to deterministic code.

Agent or stub output may:

- Propose a patch.
- Attach direction tags, hypotheses, risk notes, and expected metric changes.
- Produce raw text or structured proposal JSON.

Agent or stub output may not:

- Accept a strategy.
- Override the validation policy gate.
- Override the holdout risk gate.
- Modify files outside `strategies/current_strategy.py` during a strategy
  improvement round.
- Route, veto, or promote a candidate through natural-language judgment.

## Strategy Modifier Backends

The active modifier is selected by config. Supported values include:

- `fixed_patch_stub`
- `adaptive_stub`
- `codex_dry_run`
- `codex_cli_dry_run`
- `codex_cli`
- `file_protocol`

The default stub is deterministic. The adaptive stub is also deterministic, but
can change its fixed patch direction from saved context such as same-run
failures and recent research briefs.

External adapters are guarded. `codex_cli` and `file_protocol` only invoke a
subprocess when their config explicitly sets `execute=true`.

## Agent Slots and Roles

V0.5 models future blue-node agent slots without running the full multi-agent
system.

The only executable role is:

- `strategy_modifier`

Contract-only roles remain disabled and advisory:

- `analysis`
- `visual_review`
- `overfit_validator`

These roles may write deterministic inspection artifacts, but they cannot route,
veto, or decide final acceptance in V0.5.

Configs may define explicit `agents` profiles with profile names, adapters,
queue roles, architectural roles, enabled flags, and adapter settings. When no
explicit profile list exists, the loop derives audit profiles from
`strategy_modifier` and `memory_filter.fallback_modifiers`.

## Executor and Candidate Selection

Candidate modifiers run through a deterministic executor queue:

- The primary modifier receives `attempt_001_primary`.
- Fallback modifiers receive stable `attempt_00N_fallback_NN` ids.
- Each attempt writes compact input/output, proposal, raw output, patch,
  validation, and optional workspace/execution audit artifacts.

Candidate ranking can use deterministic metadata such as expected metric
changes, risk notes, duplicate patch hashes, outcome-memory filters, direction
history priors, routing priors, exploration bonuses, probe metrics, and
champion gap. These ranking features only choose which candidate to backtest.
They do not decide final acceptance.

## Workspaces

Workspace-backed adapters use isolated profile-attempt paths:

```text
workspaces/<run_id>/<round_id>/<profile>/<attempt_id>/strategy_workspace/
```

Workspace manifests record the copied project surface, initial snapshot digest,
profile, adapter, attempt id, and allowed mutation paths. Hidden mutation checks
reject side effects outside the configured strategy file boundary.

## Outcome Memory

Iteration runs append compact proposal outcomes to `experiments/memory.jsonl`.
The loop can reject patch hashes or direction tags that have failed too many
times, and future context builders can use recent outcomes and research briefs
to avoid repeating weak search directions.

`memory_filter.created_at_from` and `memory_filter.recent_record_limit` can
scope the records used by patch rejection, direction rejection, and direction
history priors. Empty scope values preserve full-history behavior.
Each iteration run writes `memory_hygiene.json` and `memory_hygiene.md` to show
which records were active, which were ignored by scope, and which patch or
direction groups would be blocked. These reports are read-only and do not
delete memory or change acceptance.
The run also writes `memory_scope_recommendation.json` and
`memory_scope_recommendation.md`, an advisory-only report that suggests whether
future runs should keep full-history memory or set a recent-record scope. It
does not edit config, delete memory, route candidates, or change acceptance.
`config_change_candidate.json` and `config_change_candidate.md` lift those
recommendations into operator-reviewed config fields for a future run. The loop
does not apply the candidate changes; it only records the field, current value,
proposed value, rationale, and risk notes.
`operator_config_review.json` and `operator_config_review.md` can then record
whether an operator approved or rejected the candidate. This creates an audit
trail for human intent, but it still does not edit config files or change
iteration behavior automatically.
`config_application_dry_run.json` and `config_application_dry_run.md` preview
whether an approved candidate still matches the current config value and is
ready for a later manual edit. The dry run is intentionally read-only and does
not apply config changes.
`config_application_receipt.json` and `config_application_receipt.md` are only
created by the explicit guarded apply command. That command binds the current
config digest, the approved dry-run digest, and the operator-review digest
before writing config, and it still does not run agents or change acceptance.
`config_application_rollback_preview.json` and
`config_application_rollback_preview.md` then provide a read-only manual
restore plan and next-run impact summary from the receipt and current config.
They never restore config automatically.
`config_application_restore_receipt.json` and
`config_application_restore_receipt.md` are only created by the explicit
guarded restore command. That command restores config only when the rollback
preview is ready and the preview, receipt, and current config digests still
match; it does not run agents or change acceptance.
`config_lineage.json` and `config_lineage.md` connect the run's config
candidate, review, dry-run, application receipt, rollback preview, and restore
receipt artifacts into one read-only digest chain. They do not write config.

`run_closeout.json` and `run_closeout.md` include an `operator_dashboard`
summary that rolls up artifact health, config lineage, champion review,
promotion review, watchlist status, action items, and deterministic authority.
`python -m orchestrator.experiments review <run_id>` renders the same dashboard
without requiring the operator to inspect the full closeout file. It is an
inspection view only; it cannot write config, promote champions, route
candidates, run backtests, apply patches, execute agents, or change acceptance.
`operator_action_plan.json` and `operator_action_plan.md` sit immediately after
closeout and turn dashboard action items into reviewed command candidates. They
bind to `run_closeout.json`, mark guarded candidates, and require explicit
operator invocation; they do not execute commands or change repository state.
`operator_action_approval.json` and `operator_action_approval.md` record
explicit approval for one action-plan command candidate. They bind to the saved
action plan and command digest, but approval is still not execution; the
operator must invoke the selected command separately.
`operator_action_execution_receipt.json` and
`operator_action_execution_receipt.md` record the guarded execution of one
approved read-only inspection command. They bind to the saved approval and
command digest, execute without a shell, record stdout/stderr hashes, and check
tracked git status before and after execution. Commands that write repository
state, promote champions, run backtests, execute agents, apply patches, route
agents, or change acceptance are blocked.
`operator_action_audit.json` and `operator_action_audit.md` then provide a
read-only chain view across the saved plan, approval, and execution receipt.
They expose source artifact hashes, schema errors, selected-command
consistency, execution status, and the next operator step without executing
commands or changing repository state.
`operator_action_dashboard.json` and `operator_action_dashboard.md` summarize
that chain for the operator. They show the current step, timeline, selected
command, safe command counts, blockers, and suggested guarded commands while
remaining read-only: they do not record approval, execute commands, write
config, promote champions, run agents, run backtests, route agents, apply
patches, or change acceptance.

## Champion Registry

Experiment comparison and promotion commands are deterministic. A candidate can
be promoted through the guarded `promote-approved` path only when comparison
rules recommend `promote_candidate`, operator approval is recorded, reviewed
command and source dry-run digests still match, and the current champion has
not drifted. Successful promotion writes `experiments/champion.json` and
appends `experiments/champion_history.jsonl`.
