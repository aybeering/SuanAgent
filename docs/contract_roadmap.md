# Contract Roadmap

This document keeps the detailed V0.5 contract roadmap outside `AGENTS.md` so
the agent instructions can stay readable. It describes the current deterministic
prototype boundary and the guarded evidence chain for future agent activation.

V0.5 remains a deterministic control-flow prototype. It may create contracts,
fixtures, manifests, readiness checks, and replay artifacts for future agents,
but final acceptance still belongs to deterministic code.

## Active V0.5 Scope

Implemented or allowed V0.5 components:

1. A simple strategy interface.
2. A deterministic backtester.
3. Metrics generation.
4. Markdown report generation.
5. A deterministic policy gate.
6. A single-run V0 pipeline.
7. A multi-round V0.5 iteration loop.
8. A fixed strategy modifier stub.
9. A deterministic adaptive stub that changes fixed patch direction from context.
10. A proposal schema and deterministic contract validator for agent output.
11. A guarded Codex CLI adapter that only executes when config explicitly enables it.
12. Isolated workspace creation for future Codex execution.
13. Workspace mutation checks that reject hidden Codex CLI side effects outside the strategy file.
14. Unified diff extraction and target-file validation.
15. Git apply, accept commit, and reject rollback helpers.
16. Round-based experiment outputs.
17. Config-driven dataset, validation policy, holdout policy, and modifier settings.
18. Proposal quality metadata and repeated-patch detection.
19. Repeated-proposal stop control.
20. Clear tests and smoke checks.
21. A guarded file-protocol adapter for future CLI or SDK-backed agents.
22. A local deterministic file-protocol demo agent for end-to-end external-agent smoke tests.
23. File-protocol execution audit logs with command, output hashes, and mutation-guard results.
24. GitHub Actions CI for deterministic smoke validation.
25. Saved attempt replay for contract and probe checks without a full loop rerun.
26. Stable failure taxonomy fields for decisions, attempts, validation, and replay.
27. A deterministic agent executor queue that assigns stable attempt ids before candidate selection.
28. Optional config-level agent profiles that name future isolated agent slots while still using deterministic adapters.
29. Profile-aware workspace and execution audit metadata for workspace-backed adapters.
30. Profile-aware agent input contracts for external CLI or SDK-backed agents.
31. Attempt-scoped agent input artifacts for candidate-level replay.
32. Role-level agent contracts that declare future blue-node responsibilities while only the strategy modifier executes.
33. Deterministic local `chart.html` and `trade_timeline.html` artifacts for round inspection, generated without visual agents or network calls.
34. A deterministic `visual_artifacts_manifest.json` that indexes visual inputs, source files, hashes, and visual authority policy.
35. A deterministic `agent_role_readiness.json` audit that reports which future agent roles are executable, blocked, or contract-only.
36. A deterministic `agent_activation_preflight.json` startup gate that verifies role/profile activation before iteration begins.
37. A deterministic `agent_execution_plan.json` round plan that records the candidate queue before any modifier is invoked.
38. A deterministic `round_replay.json` audit command that replays every saved planned attempt without rerunning the full loop.
39. Agent inspection output that summarizes round replay status for each saved round.
40. A deterministic `agent_slot_health.json` report that summarizes planned slot readiness, audits, and replay status.
41. A deterministic `agent_slot_readiness_gate.json` report that blocks future external agent slots until input, output, workspace, audit, and replay artifacts are present.
42. A deterministic `external_agent_sandbox_drill.json` report that audits external slot command, workspace, input, output, subprocess, and mutation-guard evidence without executing agents.
43. A unified `agent_execution.json` contract for guarded Codex CLI attempts, including disabled, completed, failed, timed-out, and mutation-guard outcomes.
44. A deterministic `agent_output_quarantine.json` report that quarantines selected agent output before git apply and releases only validated strategy patches.
45. A deterministic `agent_golden_replay.json` report that freezes one saved agent input/output pair as a replayable protocol fixture.
46. A deterministic `codex_cli_contract_fixture.json` report that freezes guarded Codex CLI stdin/stdout expectations without executing Codex.
47. A deterministic `codex_cli_replay_gate.json` report that gates Codex CLI enablement using saved execution, fixture, quarantine, and replay artifacts.
48. A deterministic `codex_cli_enablement_gate.json` report that checks an explicit execute=true candidate config without executing Codex or modifying config files.
49. A deterministic `codex_cli_manual_approval.json` report that records explicit approval for a passing enablement gate without executing Codex.
50. A deterministic `codex_cli_canary_gate.json` report that validates a checked-in local Codex CLI canary executable through the guarded execution path without running real Codex.
51. A deterministic `codex_cli_real_preflight.json` report that probes real Codex CLI availability with `--version` only, without sending strategy prompts or modifying files.
52. A deterministic `codex_cli_dry_invocation_guard.json` report that can optionally run a harmless Codex CLI prompt in an isolated workspace with an empty mutation allowlist.
53. A deterministic `codex_cli_execution_unlock_gate.json` report that aggregates replay, enablement, manual approval, canary, real preflight, and dry-invocation evidence, including candidate config sha256 binding, before real Codex execution can be considered unlocked.
54. A deterministic `codex_cli_execution_unlock_snapshot.json` report that freezes the unlock gate, candidate config binding, and evidence artifact hashes so later drift or tampering can be detected.
55. A deterministic `codex_cli_execution_candidate.json` report that freezes the future real Codex command, planned workspace path, allowed mutation boundary, and unlock snapshot evidence without executing Codex.
56. A deterministic `codex_cli_real_execution_dry_run.json` report that performs the final real-execution boundary dry run without invoking Codex, creating a workspace, applying patches, or changing acceptance.
57. A deterministic `codex_cli_readiness_summary.json` report that summarizes the full Codex CLI readiness chain into one read-only status page.
58. A deterministic `codex_cli_readiness_pipeline.json` report that runs the read-only Codex CLI readiness chain from enablement through summary as one auditable command.
59. A deterministic `codex_cli_operator_unlock_request.json` report that records explicit operator intent and the reviewed Codex command digest for future real Codex CLI execution review without executing Codex.
60. A deterministic `codex_cli_execution_preflight.json` startup gate that blocks real Codex CLI execution unless a ready operator unlock request is already recorded and still matches the current profile command, current run workspace prefix, and recorded readiness evidence hashes.
61. Deterministic `agent_execution.json` command digest binding that lets artifact validation prove guarded Codex CLI attempts used the command reviewed by startup preflight.
62. Strict local JSON schema validation, including repository-local `$defs` references, for Codex CLI execution preflight evidence contracts.
63. Strict `codex_cli_operator_unlock_request.json` evidence contracts that type-check operator intent, canonical source artifact checks, source file records, planned command review, and read-only safety policy.
64. Startup preflight binding for operator unlock intent fields, including request scope, explicit request flag, operator id, and required confirmation phrase hashes.
65. Startup preflight contract validation for the full operator unlock request file before real Codex CLI execution can be unlocked.
66. Operator request generation, startup preflight, and artifact validation path binding for canonical operator unlock source evidence files, so reviewed readiness evidence paths cannot drift independently from their recorded file hashes.
67. Startup preflight and artifact validation binding for operator unlock run identity, including `run_id` and `run_dir`, so reviewed requests cannot be reused across iteration runs.
68. Startup preflight and artifact validation binding for operator unlock planned execution identity, including agent name, profile name, round id, and attempt id.
69. Startup preflight and artifact validation binding for the exact operator-reviewed real Codex workspace path, so reviewed requests cannot drift to another attempt workspace inside the same run.
70. Startup preflight and artifact validation binding between an operator unlock request's reviewed execution plan and its recorded source real-execution dry-run plan.
71. Operator request generation, startup preflight, and artifact validation binding that requires real Codex operator unlock requests to be written and stored as the canonical `codex_cli_operator_unlock_request.json` artifact inside the current run directory.
72. A narrow iteration-loop startup exception that permits an existing run directory only when it contains the configured canonical real Codex operator unlock request artifact; ordinary or non-canonical existing run directories remain blocked.
73. A deterministic `artifact_validator_coverage.json` report that audits whether each repository-local artifact schema has validator coverage, documentation references, tests, and inspection or replay support.
74. A deterministic `run_artifact_health.json` report that batch-validates saved experiment run artifacts without rerunning backtests or calling agents.
75. A deterministic `run_artifact_health_history.jsonl` memory layer and `run_artifact_health_history_v1` summary that track repeated artifact-health failures across saved inspection runs. The iteration loop automatically appends one scoped artifact-health record at run completion.
76. A deterministic `memory_diagnostics.json` report that cross-references proposal outcome memory with artifact-health history by run id, agent, profile, direction, and patch hash without routing agents or changing acceptance.
77. A deterministic current-contract scope filter for artifact health, artifact-health history, and memory diagnostics, keyed by indexed `created_at`, so legacy experiment directories can remain on disk without polluting current V0.5 validation.
78. A deterministic `experiment_scope_health.json` report that combines scoped artifact health, health-history, and memory diagnostics into one read-only status page without running agents, running backtests, routing agents, applying patches, or changing acceptance. The iteration loop writes this report automatically at run completion using the run's startup timestamp as the scope boundary.
79. A deterministic `run_closeout.json` and `run_closeout.md` report pair that summarizes completed iteration status, health, selected candidates, deterministic acceptance authority, and recommended next actions without running agents, running backtests, applying patches, routing agents, or changing acceptance.
80. Deterministic candidate quality breakdown fields that decompose proposal prefilter scores into named components and carry selected validation and holdout signals across leaderboard, routing, selection, brief, and closeout artifacts without changing final acceptance authority.
81. A deterministic `candidate_challenger_report.json` and `candidate_challenger_report.md` report pair that compares saved candidate rows with the current champion registry, including validation gap and holdout stability flags, without promoting champions, routing agents, running backtests, applying patches, or changing acceptance.
82. A deterministic `champion_promotion_dry_run.json` and `champion_promotion_dry_run.md` report pair that previews whether a completed run would satisfy the existing deterministic champion promotion comparison, without writing `champion.json`, appending champion history, running agents, running backtests, routing agents, applying patches, or changing acceptance.
83. A deterministic `champion_promotion_approval.json` and `champion_promotion_approval.md` report pair that records operator review intent, required confirmation phrase hashes, reviewed promote command digests, and source evidence hashes without executing promotion, writing champion registry files, appending champion history, running agents, running backtests, routing agents, applying patches, or changing acceptance.
84. A deterministic `champion_promotion_receipt.json` and `champion_promotion_receipt.md` report pair for the guarded promote-approved command, which writes `champion.json` and appends `champion_history.jsonl` only when approval evidence, command digest, dry-run digest, current champion identity, and current comparison recommendation still match.
85. A deterministic global `champion_lineage.json` and `champion_lineage.md` report pair that connects the current champion registry, champion history, promotion receipts, approval artifacts, dry-run hashes, and comparison metric deltas into a read-only champion evolution chain without promoting champions or changing acceptance.
86. Deterministic profile direction-capability contracts that let each modifier profile declare supported proposal directions, record those declarations in agent input, execution plan, selection, routing, executor, and attempt artifacts, and skip mismatched candidates without giving planner guidance final routing or acceptance authority.
87. Deterministic `direction_intent_alignment` fields that compare proposal intent, profile direction capability, and actual proposal direction across candidate artifacts, including recommendation coverage, recommendation match/deviation, avoid-direction checks, and audit-only deviation allowance without changing routing, scoring, patch application, or acceptance.
88. Deterministic `direction_decision_trace` metadata inside `proposal_intent.json` that records planner candidate order, avoid-source codes, selected direction, fallback exhaustion, and advisory-only authority policy without changing routing, scoring, patch application, or acceptance.
89. Deterministic `proposal_intent_summary` metadata inside round-level, bundle-level, workspace-backed, and attempt-scoped `agent_input.json` contracts so future external agents can consume planner direction guidance from the input contract while the summary remains advisory-only and cannot change routing, scoring, patch application, or acceptance.
90. Deterministic `proposal_intent_summary` binding inside `agent_execution_plan.json` and each planned attempt's input contract, proving the pre-execution queue was planned against the same advisory planner context that later appears in agent input artifacts without changing queue order, scoring, patch application, or acceptance.
91. Deterministic `proposal_intent_summary` binding inside `attempt_output.json`, proving each saved candidate attempt's output audit matches the planner context in its attempt-scoped `agent_input.json` without changing replay, scoring, patch application, or acceptance.
92. Deterministic `proposal_intent_summary` binding inside round-level `agent_output.json`, proving the selected-output contract matches the planner context in round-level `agent_input.json` without changing routing, scoring, patch application, or acceptance.
93. Deterministic `proposal_intent_summary` binding inside `agent_output_quarantine.json`, proving the pre-apply quarantine report matches both `agent_output.json` and `agent_input.json` planner context without changing quarantine release rules, patch application, or acceptance.
94. Deterministic `proposal_intent_summary` binding inside `agent_validation.json`, proving raw-output contract validation ran against the same planner context in `agent_input.json` without changing validation pass/fail rules, git apply checks, quarantine release rules, patch application, or acceptance.
95. Deterministic candidate quality breakdown bindings inside executor, attempt manifest, attempt output, selection, routing, agent output, leaderboard, brief, and closeout artifacts, proving candidate score explanations remain auditable across the saved candidate trace without changing queue order, scoring rules, patch application, or acceptance.
96. Deterministic cross-artifact candidate quality consistency checks that bind each `attempt_id` in executor, attempt manifest, attempt output, selection, routing, agent output, and leaderboard artifacts back to `proposal_attempts.json`, without executing agents, rerunning backtests, applying patches, or changing acceptance.
97. A deterministic `candidate_quality_trace.json` and `candidate_quality_trace.md` report pair that summarizes saved candidate score components, probe/validation/holdout signals, selected attempts, patch families, and failure codes from `candidate_leaderboard.json` without executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
98. Configurable deterministic outcome-memory scope fields, `memory_filter.created_at_from` and `memory_filter.recent_record_limit`, that constrain patch rejection, direction rejection, and direction history priors while preserving full-history behavior by default.
99. A deterministic `memory_hygiene.json` and `memory_hygiene.md` report pair that summarizes active versus ignored outcome memory records, patch and direction block groups, and read-only hygiene recommendations without deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
100. A deterministic `memory_scope_recommendation.json` and `memory_scope_recommendation.md` report pair that reads saved memory hygiene artifacts and recommends whether future runs should keep full-history outcome memory or set a recent-record scope, without writing config, deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
101. A deterministic `config_change_candidate.json` and `config_change_candidate.md` report pair that translates saved read-only recommendations into operator-reviewed config field candidates for a future run, including current values, proposed values, rationale, reason codes, and risk notes, without writing config, deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
102. A deterministic `operator_config_review.json` and `operator_config_review.md` report pair that records operator approve or reject intent for saved config change candidates, including confirmation phrase hashes for approval and reviewed candidate rows, without writing config, deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
103. A deterministic `config_application_dry_run.json` and `config_application_dry_run.md` report pair that previews whether approved config change candidates still match the current config value and are ready for a later manual edit, without writing config, deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
104. A guarded `config_application_receipt.json` and `config_application_receipt.md` report pair for the explicit apply-config-approved command, which writes config only when ready dry-run evidence, operator-review evidence, and current config digests still match, without deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
105. A read-only `config_application_rollback_preview.json` and `config_application_rollback_preview.md` report pair that derives manual restore rows and next-run impact from a saved config application receipt and current config, without writing config, deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
106. A guarded `config_application_restore_receipt.json` and `config_application_restore_receipt.md` report pair for the explicit restore-config-approved command, which restores config only when rollback-preview evidence, source receipt evidence, and current config digests still match, without deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
107. A read-only `config_lineage.json` and `config_lineage.md` report pair that connects config candidates, operator reviews, dry-runs, application receipts, rollback previews, and restore receipts into one digest-checked run-level audit chain, without writing config, deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
108. A deterministic `operator_dashboard` section inside `run_closeout.json` and `run_closeout.md`, exposed through `python -m orchestrator.experiments review <run_id>`, that summarizes run status, artifact health, config lineage, champion review, promotion review, watchlist status, operator action items, and deterministic authority in one read-only operator view, without writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
109. A deterministic `operator_action_plan.json` and `operator_action_plan.md` report pair, exposed through `python -m orchestrator.experiments action-plan <run_id>`, that derives explicit command candidates from the saved closeout dashboard, binds to `run_closeout.json` by SHA-256, marks guarded commands, and requires explicit operator invocation without executing commands, writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
110. A deterministic `operator_action_approval.json` and `operator_action_approval.md` report pair, exposed through `python -m orchestrator.experiments action-approval <run_id>` and written by `python -m orchestrator.operator_action_approval`, that records explicit operator approval for one action-plan command candidate, binds to `operator_action_plan.json` and the selected command digest, and requires a confirmation phrase without executing commands, writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
111. A guarded `operator_action_execution_receipt.json` and `operator_action_execution_receipt.md` report pair, written by `python -m orchestrator.operator_action_executor` and exposed through `python -m orchestrator.experiments action-execution <run_id>`, that executes only approval-backed allowlisted read-only inspection commands, binds to `operator_action_approval.json` and the selected command digest, records stdout/stderr hashes and tracked workspace mutation evidence, and blocks commands that write repository state, promote champions, execute agents, rerun backtests, route candidates, apply patches, or change acceptance.
112. A read-only `operator_action_audit.json` and `operator_action_audit.md` report pair, written by `python -m orchestrator.operator_action_audit` and exposed through `python -m orchestrator.experiments action-audit <run_id>`, that connects the saved operator action plan, approval, and execution receipt into one digest-checked chain, reports source schema errors, selected-command consistency, chain status, and next operator steps, without executing commands, writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
113. A read-only `operator_action_dashboard.json` and `operator_action_dashboard.md` report pair, written by `python -m orchestrator.operator_action_dashboard` and exposed through `python -m orchestrator.experiments action-dashboard <run_id>`, that summarizes the operator action plan, approval, execution receipt, and audit state into one compact next-step view with timeline rows, selected command state, safe command counts, blockers, and command hints, without recording approval, executing commands, writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
114. A read-only `operator_cockpit.json` and `operator_cockpit.md` report pair, written by `python -m orchestrator.operator_cockpit` and exposed through `python -m orchestrator.experiments cockpit <run_id>`, that aggregates run closeout, config lineage, operator action dashboard, challenger comparison, champion-promotion dry-run, promotion approval, and scope-health state into one operator page with panel rows, blockers, primary focus, and command hints, without recording approval, executing commands, writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.

## Contract Families

Documentation map:

- `README.md` is the short project entrypoint.
- `TASK.md` defines the current V0.5 target and smoke checks.
- `AGENTS.md` defines repository rules for coding agents.
- `docs/architecture.md` explains the runtime architecture.
- `docs/artifact_reference.md` indexes commands and generated artifacts.
- `docs/codex_cli_readiness.md` explains the guarded Codex CLI evidence chain.
- `docs/strategy_interface.md` documents the strategy modification boundary.

Core evaluation contracts:

- Strategy interface: `docs/strategy_interface.md`
- Proposal normalization and validation: `orchestrator/proposal.py`
- Policy acceptance: `orchestrator/policy_gate.py`
- Experiment metadata and diagnosis: `orchestrator/run_metadata.py`,
  `orchestrator/run_diagnosis.py`, and `orchestrator/research_brief.py`

Agent-slot contracts:

- Role contracts: `schemas/agent_role_contracts.schema.json`
- Activation preflight: `schemas/agent_activation_preflight.schema.json`
- Execution plan: `schemas/agent_execution_plan.schema.json`
- Agent input/output: `schemas/agent_input.schema.json` and
  `schemas/agent_output.schema.json`
- Attempt replay: `schemas/attempt_replay.schema.json`
- Round replay: `schemas/round_replay.schema.json`
- Slot health/readiness: `schemas/agent_slot_health.schema.json` and
  `schemas/agent_slot_readiness_gate.schema.json`
- Artifact contract coverage:
  `schemas/artifact_validator_coverage.schema.json`
- Batch run artifact health: `schemas/run_artifact_health.schema.json` and
  `schemas/run_artifact_health_history.schema.json`
- Memory diagnostics: `schemas/memory_diagnostics.schema.json`
- Memory hygiene: `schemas/memory_hygiene.schema.json`
- Memory scope recommendation:
  `schemas/memory_scope_recommendation.schema.json`
- Config change candidate: `schemas/config_change_candidate.schema.json`
- Operator config review: `schemas/operator_config_review.schema.json`
- Config application dry run:
  `schemas/config_application_dry_run.schema.json`
- Config application receipt:
  `schemas/config_application_receipt.schema.json`
- Config application rollback preview:
  `schemas/config_application_rollback_preview.schema.json`
- Config application restore receipt:
  `schemas/config_application_restore_receipt.schema.json`
- Config lineage: `schemas/config_lineage.schema.json`
- Experiment scope health: `schemas/experiment_scope_health.schema.json`
- Run closeout: `schemas/run_closeout.schema.json`
- Operator action plan: `schemas/operator_action_plan.schema.json`
- Operator action approval: `schemas/operator_action_approval.schema.json`
- Operator action execution receipt:
  `schemas/operator_action_execution_receipt.schema.json`
- Operator action audit: `schemas/operator_action_audit.schema.json`
- Operator action dashboard: `schemas/operator_action_dashboard.schema.json`
- Operator cockpit: `schemas/operator_cockpit.schema.json`
- Candidate quality trace: `schemas/candidate_quality_trace.schema.json`
- Candidate challenger report: `schemas/candidate_challenger_report.schema.json`
- Champion promotion dry-run: `schemas/champion_promotion_dry_run.schema.json`
- Champion promotion approval: `schemas/champion_promotion_approval.schema.json`
- Champion promotion receipt: `schemas/champion_promotion_receipt.schema.json`
- Champion lineage: `schemas/champion_lineage.schema.json`

Codex CLI readiness contracts:

- Replay gate: `schemas/codex_cli_replay_gate.schema.json`
- Enablement gate: `schemas/codex_cli_enablement_gate.schema.json`
- Manual approval: `schemas/codex_cli_manual_approval.schema.json`
- Canary gate: `schemas/codex_cli_canary_gate.schema.json`
- Real preflight: `schemas/codex_cli_real_preflight.schema.json`
- Dry invocation guard: `schemas/codex_cli_dry_invocation_guard.schema.json`
- Unlock gate and snapshot:
  `schemas/codex_cli_execution_unlock_gate.schema.json` and
  `schemas/codex_cli_execution_unlock_snapshot.schema.json`
- Execution candidate and final dry run:
  `schemas/codex_cli_execution_candidate.schema.json` and
  `schemas/codex_cli_real_execution_dry_run.schema.json`
- Operator unlock request:
  `schemas/codex_cli_operator_unlock_request.schema.json`
- Startup execution preflight:
  `schemas/codex_cli_execution_preflight.schema.json`

## Safety Invariants

1. Deterministic gates keep final acceptance authority.
2. Agent text can propose patches but cannot accept strategies.
3. Strategy-improvement patches may only modify `strategies/current_strategy.py`.
4. Data under `data/` is immutable experiment input.
5. V0.5 must not call real exchange, wallet, Polymarket, Binance, or network APIs.
6. Real Codex CLI strategy execution remains out of scope until the full
   readiness chain, operator request, startup preflight, and artifact validator
   all agree on the same command, workspace, run identity, and source hashes.
7. Visual and overfit roles may write deterministic read-only artifacts, but in
   V0.5 they cannot route, veto, or change final acceptance.
8. Artifact coverage reports are inspection-only. They can identify missing
   validators, docs, tests, and inspection commands, but they do not validate
   run artifacts or change strategy acceptance.
9. Batch run artifact health reports inspect saved run artifacts only. They do
   not rerun simulations, invoke agents, apply patches, or change acceptance.
10. Artifact health history is append-only local memory. It can guide future
    maintenance priorities, but it cannot route agents or decide acceptance.
11. Memory diagnostics are read-only. They may reveal recurring proposal,
    direction, profile, or patch correlations with artifact-health failures,
    but they cannot execute agents, run backtests, route candidates, apply
    patches, or change acceptance.
12. Current-contract scope filters only change which saved records are inspected.
    They cannot delete legacy experiments, repair artifacts, hide explicit
    run-id checks, or affect strategy acceptance.
13. Experiment scope health is a read-only rollup of existing diagnostics. It
    can mark a scope healthy or unhealthy for operator inspection, but it cannot
    execute agents, run backtests, route candidates, apply patches, repair
    artifacts, or change strategy acceptance.
14. Run closeout reports, their operator dashboards, and research-brief focus
    hints are read-only operator summaries. They can surface watchlist alerts,
    config-lineage status, champion/promotion review status, recommended next
    inspection steps, suggested directions, and directions to avoid, but they
    cannot write config, promote champions, execute agents, run backtests, route
    candidates, apply patches, or change strategy acceptance.
15. Strategy search-space config is an advisory planning contract. It can name
    candidate direction tags, direction order, modifier hints, and a fallback
    direction for operator review and future agent input, but it cannot execute
    agents, route candidates, apply patches, or change strategy acceptance.
16. Profile direction-capability checks are contract enforcement only. They can
    reject a candidate whose proposal direction is outside the profile's own
    declared capability, but they cannot accept a strategy, override validation,
    or let planner guidance route candidates.
17. Direction intent alignment is audit-only. It can report whether a candidate
    covered, matched, or deviated from the proposal intent recommendation, but
    it cannot score candidates, route agents, apply patches, or change
    acceptance.
18. Direction decision traces are planner explanation only. They can expose why
    `proposal_intent.json` recommended a direction and which directions were
    avoided, but they cannot score candidates, route agents, apply patches, or
    change acceptance.
19. Proposal intent summaries in `agent_input.json` are compact context only.
    They can make planner trace metadata easier for external agents to consume,
    but they cannot score candidates, route agents, apply patches, or change
    acceptance.
20. Proposal intent summaries in `agent_execution_plan.json` bind planned
    attempts to the context they will receive. They can prove plan/input
    consistency, but they cannot change queue order, score candidates, apply
    patches, or change acceptance.
21. Proposal intent summaries in `attempt_output.json` bind saved attempt
    audits to the same context recorded in attempt-scoped agent input. They can
    prove audit/input consistency, but they cannot change replay, score
    candidates, apply patches, or change acceptance.
22. Proposal intent summaries in `agent_output.json` bind selected-output
    contracts to the same context recorded in round-level agent input. They can
    prove output/input consistency, but they cannot route agents, score
    candidates, apply patches, or change acceptance.
23. Proposal intent summaries in `agent_output_quarantine.json` bind pre-apply
    quarantine reports to the same context recorded in selected output and
    round-level agent input. They can prove quarantine/output/input
    consistency, but they cannot change quarantine release rules, apply patches,
    or change acceptance.
24. Proposal intent summaries in `agent_validation.json` bind raw-output
    validation reports to the same context recorded in round-level agent input.
    They can prove validation/input consistency, but they cannot change
    validation pass/fail rules, git apply checks, quarantine release rules,
    patch application, or acceptance.
25. Candidate quality breakdowns explain proposal ranking only. They bind the
    same score total and component metadata across executor, attempt, selection,
    routing, output, leaderboard, brief, and closeout artifacts, but they cannot
    change queue order, override the deterministic policy gate, or bypass the
    holdout veto.
26. Cross-artifact candidate quality checks use `proposal_attempts.json` as the
    round-local source of truth for `candidate_score`, `score_reasons`, and
    `quality_breakdown` per `attempt_id`. They can reject inconsistent saved
    artifacts during inspection, but they cannot execute agents, rerun
    backtests, apply patches, or change acceptance.
27. Candidate challenger reports are read-only comparison summaries. They can
    highlight validation gaps and holdout stability against the current
    champion, but they cannot promote champions, route candidates, apply
    patches, run backtests, or change strategy acceptance.
28. Champion promotion dry-runs are read-only promotion previews. They can
    expose the deterministic promote command that would be appropriate after
    operator review, but they cannot write champion registry files, append
    champion history, route candidates, apply patches, run backtests, or change
    strategy acceptance.
29. Champion promotion approval artifacts record operator intent and reviewed
    command digests only. They cannot execute promotion, write champion
    registry files, append champion history, route candidates, apply patches,
    run backtests, or change strategy acceptance.
30. Guarded champion promotion receipts are the only V0.5 artifact family that
    records champion registry writes. They require approval evidence, command
    digest binding, source dry-run digest binding, unchanged champion identity,
    and a current deterministic promote recommendation before writing
    `champion.json` or appending `champion_history.jsonl`.
31. Champion lineage reports are read-only global experiment inspections. They
    can summarize champion history, receipts, approvals, dry-runs, and metric
    deltas, but they cannot promote champions, route candidates, run backtests,
    apply patches, write champion registry files, append champion history, or
    change strategy acceptance. Compact lineage summaries may appear in
    experiment summary and champion inspection output, but only the explicit
    lineage command writes lineage artifacts.
32. Experiment summary dashboards are read-only inspection payloads embedded in
    `python -m orchestrator.experiments summary`. They can summarize latest
    indexed runs, recent diagnosis rows, recent failure-code counts, and
    best-run-to-champion gaps, and they may include a deterministic operator
    watchlist for repeated proposals, artifact-health failures, and champion
    gap alerts. They cannot execute agents, run backtests, route candidates,
    apply patches, promote champions, write artifacts, or change strategy
    acceptance. The optional `summary --markdown` mode renders the same payload
    for terminal inspection without writing artifacts.

## Near-Term Development Order

1. Keep `TASK.md` aligned with the current V0.5 boundary.
2. Keep `AGENTS.md` focused on rules that affect code changes.
3. Put expanding artifact and readiness detail in this roadmap or narrower docs.
4. Prefer artifact validators and replay commands over undocumented assumptions.
5. Add a schema or fixture before adding a new generated artifact family.
