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
44. A deterministic `agent_output_quarantine.json` report that quarantines selected agent output before git apply and releases only validated strategy patches, with schema-validated consistency checks that bind release status, selected attempt id, patch hash, validation status, and source artifact hashes.
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
57. A deterministic `codex_cli_readiness_summary.json` report that summarizes the full Codex CLI readiness chain into one read-only status page, with schema-validated consistency checks that bind expected stage order, missing and blocked stage lists, aggregate blockers, final-stage readiness, and readiness status.
58. A deterministic `codex_cli_readiness_pipeline.json` report that runs the read-only Codex CLI readiness chain from enablement through summary as one auditable command, with schema-validated consistency checks that bind expected step order, generated artifact records, final summary file hashes, and pipeline-level readiness status.
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
81. A deterministic `candidate_challenger_report.json` and `candidate_challenger_report.md` report pair that compares saved candidate rows with the current champion registry, including validation gap and holdout stability flags, with writer and terminal-output consistency validation for `ok` and status derivation, checks summaries, selected/top candidate counts and rows, top-candidate summary fields, per-candidate gap/status/stability derivations, recommended next actions, read-only policy flags, terminal-only metadata stripping, and optional current-evidence drift checks, without promoting champions, routing agents, running backtests, applying patches, or changing acceptance.
82. A deterministic `champion_promotion_dry_run.json` and `champion_promotion_dry_run.md` report pair that previews whether a completed run would satisfy the existing deterministic champion promotion comparison, with writer and artifact-validator consistency checks for `ok`, status, blocking reasons, promotion command, would-promote decision, recommended next actions, and read-only policy flags, without writing `champion.json`, appending champion history, running agents, running backtests, routing agents, applying patches, or changing acceptance.
83. A deterministic `champion_promotion_approval.json` and `champion_promotion_approval.md` report pair that records operator review intent, required confirmation phrase hashes, reviewed promote command digests, and source evidence hashes, with writer and artifact-validator consistency checks for dry-run summary binding, command and source digest binding, approval eligibility, blockers, next actions, evidence file hashes, and non-promoting policy flags, without executing promotion, writing champion registry files, appending champion history, running agents, running backtests, routing agents, applying patches, or changing acceptance.
84. A deterministic `champion_promotion_receipt.json` and `champion_promotion_receipt.md` report pair for the guarded promote-approved command, which writes `champion.json` and appends `champion_history.jsonl` only when approval evidence, command digest, dry-run digest, current champion identity, and current comparison recommendation still match, with writer consistency checks for receipt status/promoted consistency, approval and dry-run digests, expected/reviewed commands, pre-promotion champion identity, promotion comparison/result fields, and guarded-write policy flags, plus artifact-validator non-source consistency checks that do not mark older blocked receipts unhealthy after later approval artifact refreshes.
85. A deterministic global `champion_lineage.json` and `champion_lineage.md` report pair that connects the current champion registry, champion history, promotion receipts, approval artifacts, dry-run hashes, and comparison metric deltas into a read-only champion evolution chain, with writer and terminal-output consistency validation for history event and parse-error counts, row indexes, current-champion to last-history matching, `checks` summaries, receipt-derived promotion source labels, read-only policy flags, terminal-only metadata stripping, and optional current-evidence drift checks, without promoting champions or changing acceptance.
86. Deterministic profile direction-capability contracts that let each modifier profile declare supported proposal directions, record those declarations in agent input, execution plan, selection, routing, executor, and attempt artifacts, and skip mismatched candidates, with artifact-validator recomputation of candidate-row capability fields, without giving planner guidance final routing or acceptance authority.
87. Deterministic `direction_intent_alignment` fields that compare proposal intent, profile direction capability, and actual proposal direction across candidate artifacts, including recommendation coverage, recommendation match/deviation, avoid-direction checks, audit-only deviation allowance, and artifact-validator recomputation of saved alignment booleans and reason text, without changing routing, scoring, patch application, or acceptance.
88. Deterministic `direction_decision_trace` metadata inside `proposal_intent.json` that records planner candidate order, avoid-source codes, selected direction, fallback exhaustion, and advisory-only authority policy without changing routing, scoring, patch application, or acceptance.
89. Deterministic `proposal_intent_summary` metadata inside round-level, bundle-level, workspace-backed, and attempt-scoped `agent_input.json` contracts so future external agents can consume planner direction guidance from the input contract while the summary remains advisory-only and cannot change routing, scoring, patch application, or acceptance.
90. Deterministic `proposal_intent_summary` binding inside `agent_execution_plan.json` and each planned attempt's input contract, proving the pre-execution queue was planned against the same advisory planner context that later appears in agent input artifacts without changing queue order, scoring, patch application, or acceptance.
91. Deterministic `proposal_intent_summary` binding inside `attempt_output.json`, proving each saved candidate attempt's output audit matches the planner context in its attempt-scoped `agent_input.json` without changing replay, scoring, patch application, or acceptance.
92. Deterministic `proposal_intent_summary` binding inside round-level `agent_output.json`, proving the selected-output contract matches the planner context in round-level `agent_input.json` without changing routing, scoring, patch application, or acceptance.
93. Deterministic `proposal_intent_summary` binding inside `agent_output_quarantine.json`, proving the pre-apply quarantine report matches both `agent_output.json` and `agent_input.json` planner context without changing quarantine release rules, patch application, or acceptance.
94. Deterministic `proposal_intent_summary` binding inside `agent_validation.json`, proving raw-output contract validation ran against the same planner context in `agent_input.json` without changing validation pass/fail rules, git apply checks, quarantine release rules, patch application, or acceptance.
95. Deterministic candidate quality breakdown bindings inside executor, attempt manifest, attempt output, selection, routing, agent output, leaderboard, brief, and closeout artifacts, proving candidate score explanations remain auditable across the saved candidate trace without changing queue order, scoring rules, patch application, or acceptance.
96. Deterministic cross-artifact candidate quality and direction-metadata consistency checks that bind each `attempt_id` in executor, attempt manifest, attempt output, selection, routing, agent output, and leaderboard artifacts back to `proposal_attempts.json`, without executing agents, rerunning backtests, applying patches, or changing acceptance.
97. A deterministic `candidate_quality_trace.json` and `candidate_quality_trace.md` report pair that summarizes saved candidate score components, probe/validation/holdout signals, selected attempts, patch families, and failure codes from `candidate_leaderboard.json`, with writer, artifact-validator, and terminal-output recomputation of saved source metadata, summary, round rows, candidate rows, policy flags, terminal-only metadata stripping, and optional current-evidence drift checks, without executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
97a. A deterministic `modifier_profile_recommendation.json` and `modifier_profile_recommendation.md` report pair that maps saved `candidate_quality_trace.json`, `research_brief.json`, and current config search-space/profile capability evidence into an advisory next modifier profile and direction for operator review, exposed through `python -m orchestrator.experiments profile-recommendation <run_id>` and action-plan command hints, with writer, artifact-validator, and terminal-output recomputation of source metadata, profile rows, recommendations, summary, and policy flags, without writing config, executing agents, rerunning backtests, routing agents, applying patches, or changing acceptance.
98. Configurable deterministic outcome-memory scope fields, `memory_filter.created_at_from` and `memory_filter.recent_record_limit`, that constrain patch rejection, direction rejection, and direction history priors while preserving full-history behavior by default.
99. A deterministic `memory_hygiene.json` and `memory_hygiene.md` report pair that summarizes active versus ignored outcome memory records, patch and direction block groups, and read-only hygiene recommendations, with artifact-validator internal consistency checks for saved scope, totals, visible rows, and recommendation derivation that do not bind old reports to future append-only memory records, without deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
100. A deterministic `memory_scope_recommendation.json` and `memory_scope_recommendation.md` report pair that reads saved memory hygiene artifacts and recommends whether future runs should keep full-history outcome memory or set a recent-record scope, without writing config, deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
101. A deterministic `config_change_candidate.json` and `config_change_candidate.md` report pair that translates saved read-only recommendations into operator-reviewed config field candidates for a future run, including memory-scope changes and guarded modifier-profile additions from `modifier_profile_recommendation.json` when no profile is available for the fallback direction, with current values, proposed values, rationale, reason codes, and risk notes, without writing config, deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
102. A deterministic `operator_config_review.json` and `operator_config_review.md` report pair that records operator approve or reject intent for saved config change candidates, including confirmation phrase hashes for approval and reviewed candidate rows, without writing config, deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
103. A deterministic `config_application_dry_run.json` and `config_application_dry_run.md` report pair that previews whether approved config change candidates still match the current config value and are ready for a later manual edit, including whether the target config path currently exists, without writing config, deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
104. A guarded `config_application_receipt.json` and `config_application_receipt.md` report pair for the explicit apply-config-approved command, which writes config only when ready dry-run evidence, operator-review evidence, and current config digests still match, and records whether each previous config path existed so restore can distinguish missing paths from JSON null values, without deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
105. A read-only `config_application_rollback_preview.json` and `config_application_rollback_preview.md` report pair that derives manual restore rows and next-run impact from a saved config application receipt and current config, including whether restore should write a previous value or remove a newly-added path, without writing config, deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
106. A guarded `config_application_restore_receipt.json` and `config_application_restore_receipt.md` report pair for the explicit restore-config-approved command, which restores config only when rollback-preview evidence, source receipt evidence, and current config digests still match, deleting newly-added config paths when receipt evidence says the previous path did not exist, without deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
107. A read-only `config_operator_runbook.json` and `config_operator_runbook.md` report pair, written during iteration-loop closeout after the final config lineage artifact, that orders the config candidate, operator review, dry-run, guarded apply, rollback preview, guarded restore, and lineage commands into an explicit operator walkthrough, marking commands that would write config if invoked while the runbook itself never records review, writes config, executes commands, runs agents, reruns backtests, routes candidates, applies patches, or changes acceptance.
108. A read-only `config_lineage.json` and `config_lineage.md` report pair that connects config candidates, operator reviews, dry-runs, application receipts, rollback previews, and restore receipts into one digest-checked run-level audit chain, without writing config, deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
109. A deterministic `operator_dashboard` section inside `run_closeout.json` and `run_closeout.md`, exposed through `python -m orchestrator.experiments review <run_id>`, that summarizes run status, artifact health, config lineage, candidate quality trace status, champion review, promotion review, watchlist status, operator action items, and deterministic authority in one read-only operator view, including selectable counts, selected directions, top failure code, and trace source path without writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
109. A deterministic `operator_action_plan.json` and `operator_action_plan.md` report pair, exposed through `python -m orchestrator.experiments action-plan <run_id>`, that derives explicit command candidates from the saved closeout dashboard, binds to `run_closeout.json` by SHA-256, marks guarded commands, and requires explicit operator invocation while artifact validation checks command labels, expected artifacts, command digests, command prefixes, and shell-control-token safety, without executing commands, writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
110. A deterministic `operator_action_approval.json` and `operator_action_approval.md` report pair, exposed through `python -m orchestrator.experiments action-approval <run_id>` and written by `python -m orchestrator.operator_action_approval`, that records explicit operator approval for one action-plan command candidate, binds to `operator_action_plan.json` and the selected command digest, requires a confirmation phrase, and is artifact-validated against the saved action-plan selected action and command without executing commands, writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
111. A guarded `operator_action_execution_receipt.json` and `operator_action_execution_receipt.md` report pair, written by `python -m orchestrator.operator_action_executor` and exposed through `python -m orchestrator.experiments action-execution <run_id>`, that executes only approval-backed allowlisted read-only inspection commands, binds to `operator_action_approval.json` and the selected command digest, artifact-validates selected action, selected command, execution command, argv, and evidence hashes against the saved approval, records stdout/stderr hashes and tracked workspace mutation evidence, and blocks commands that write repository state, promote champions, execute agents, rerun backtests, route candidates, apply patches, or change acceptance.
112. A read-only `operator_action_audit.json` and `operator_action_audit.md` report pair, written by `python -m orchestrator.operator_action_audit` and exposed through `python -m orchestrator.experiments action-audit <run_id>`, that connects the saved operator action plan, approval, and execution receipt into one digest-checked chain, reports source schema errors, selected-command consistency, chain status, stable stage/code failure reasons, and next operator steps, while writer and terminal-output validation reject stale source file records, status, summary, selected action, selected command, execution record, chain-check, next-action, or policy drift before returning payloads, without executing commands, writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
113. A read-only `operator_action_dashboard.json` and `operator_action_dashboard.md` report pair, written by `python -m orchestrator.operator_action_dashboard` and exposed through `python -m orchestrator.experiments action-dashboard <run_id>`, that summarizes the operator action plan, approval, execution receipt, and audit state into one compact next-step view with timeline rows, selected command state, safe command counts, audit failure reasons, blockers derived from reason codes, command hints with explicit boundary classification (`read_only_inspection`, `read_only_artifact_refresh`, `operator_approval_receipt`, or `guarded_read_only_execution`), an `execution_readiness` checkpoint binding current status, first recommended command boundary, required dependency artifacts, missing artifacts, blockers, selected-command digest status, and guarded-executor readiness, plus a `path_closure` checkpoint proving whether action plan, approval, guarded execution receipt, audit, and dashboard evidence have closed; the shared operator command-hint validator checks known labels, expected write targets, boundary derivation, current-step coverage, execution-readiness command binding, path-closure completion rules, and shell-control-token safety; the dashboard writer also validates status-derived fields plus action, command, failure-reason, blocker count summaries, command-boundary derivation, execution-readiness derivation, and path-closure derivation before returning, without recording approval, executing commands, writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
114. A read-only `operator_unlock_checklist.json` and `operator_unlock_checklist.md` report pair, written by `python -m orchestrator.operator_unlock_checklist` and exposed through `python -m orchestrator.experiments unlock-checklist <run_id>`, that promotes the Codex CLI startup-preflight unlock evidence checklist into a standalone operator artifact with grouped request, intent, source-evidence, execution-identity, command-review, workspace-boundary, mutation-boundary, and non-executing-request items plus deterministic blocker navigation for expected artifacts, related artifact paths, reason codes, and manual command hints that the shared operator command-hint validator checks for known labels, artifact ids, write flags, command prefixes, and shell-control-token safety, while writer and terminal-output consistency validation check top-level item counts, item failed-check and blocker-code mappings, navigation blocking counts, primary blocker, expected artifact ordering, command-hint coverage, current-evidence drift for derived payloads, and terminal-only metadata stripping before schema checks, without recording approval, executing Codex, creating workspaces, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
115. A read-only `operator_cockpit.json` and `operator_cockpit.md` report pair, written by `python -m orchestrator.operator_cockpit` and exposed through `python -m orchestrator.experiments cockpit <run_id>`, that aggregates run closeout, config lineage, operator action dashboard, Codex CLI execution preflight, standalone operator unlock checklist, Codex CLI unlock runbook, Codex CLI execution readiness diff, candidate quality trace state, challenger comparison, champion-promotion dry-run, promotion approval, and scope-health state into one operator page with a first-screen operator digest, panel rows, surfaced action failure reasons, `operator_action:<code>` blockers, primary focus, action execution-readiness status, action path-closure status, unlock-runbook status, readiness diff status, candidate quality score/rejection navigation, a deterministic review-priority object that picks the first panel and existing command hint to inspect, command hints that the shared operator command-hint validator checks for known labels, expected write targets, command-boundary derivation, first-command ordering, and shell-control-token safety, plus writer and terminal-output consistency validation for operator-digest derivation, status-derived OK/focus fields, action failure summaries, Codex unlock checklist counts, review-priority panel/command/boundary references, and terminal-only metadata stripping before schema checks, without recording approval, executing commands, writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
116. Deterministic iteration-loop closeout generation for `config_operator_runbook.json`, `config_operator_runbook.md`, `operator_action_dashboard.json`, `operator_action_dashboard.md`, `operator_unlock_checklist.json`, `operator_unlock_checklist.md`, `codex_cli_unlock_runbook.json`, `codex_cli_unlock_runbook.md`, `codex_cli_execution_readiness_diff.json`, `codex_cli_execution_readiness_diff.md`, `operator_cockpit.json`, and `operator_cockpit.md`, written after their source artifacts so source-file hashes bind to the final operator-facing artifacts by default; explicit config-runbook, dashboard, unlock-checklist, unlock-runbook, readiness-diff, and cockpit commands remain available for later refresh after operator approval, execution, audit, or config-lineage artifacts are rewritten, without executing commands, writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
117. Deterministic startup-failure operator unlock checklist, Codex CLI unlock runbook, and Codex CLI execution readiness diff generation for real Codex execute=true preflight blocks, so failed no-round runs still write `operator_unlock_checklist.json`, `operator_unlock_checklist.md`, `codex_cli_unlock_runbook.json`, `codex_cli_unlock_runbook.md`, `codex_cli_execution_readiness_diff.json`, `codex_cli_execution_readiness_diff.md`, and manifest/summary navigation fields for blocker count, primary blocker, command-hint count, ordered unlock steps, intake-readiness status, missing evidence, and drift status, without executing Codex, creating workspaces, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
    Run-level agent-intake summary fields in `manifest.json`, `summary.md`,
    and `diagnosis.json` group per-round raw agent-output validation status,
    primary stable reason codes, retryability, and blocker counts without
    routing candidates, applying patches, rerunning backtests, changing
    policy-gate decisions, or changing acceptance.
    Run-level outcome summary fields in `manifest.json`, `summary.md`, and
    `diagnosis.json` classify accepted runs, policy rejections, holdout vetoes,
    repeated proposals, no-improvement stops, max-round stops, agent-intake
    blocks, artifact-invalid diagnoses, and runtime failures as read-only
    operator navigation without routing candidates, applying patches, rerunning
    backtests, changing deterministic gates, or changing acceptance.
    Experiment summary dashboards and operator cockpit summaries surface the
    same outcome category, primary stage, and primary code as read-only
    navigation so recent run history and per-run review show why the loop
    stopped without changing gates or acceptance.
118. A read-only `codex_cli_unlock_runbook.json` and `codex_cli_unlock_runbook.md` report pair, written by `python -m orchestrator.codex_cli_unlock_runbook` and exposed through `python -m orchestrator.experiments unlock-runbook <run_id>`, that orders the real Codex CLI unlock evidence chain into startup-preflight, readiness-pipeline, execution-candidate, real-execution-dry-run, and operator-unlock-request steps with artifact hashes, readiness fields, step statuses, blockers, shared `codex_intake_readiness` status/ready/blocker summaries, and command hints that the shared operator command-hint validator checks for known labels, write flags, command prefixes, and shell-control-token safety, while writer and terminal-output consistency validation check step order, summary counters and step lists, status and readiness fields, source checklist summaries, shared Codex intake-readiness summaries, operator-command bindings, authority flags, read-only policy flags, current-evidence drift for derived payloads, and terminal-only metadata stripping before schema checks, without recording approval, executing commands, executing Codex, creating workspaces, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
119. A read-only `codex_cli_execution_readiness_diff.json` and `codex_cli_execution_readiness_diff.md` report pair, written by `python -m orchestrator.codex_cli_execution_readiness_diff` and exposed through `python -m orchestrator.experiments execution-readiness-diff <run_id>`, that compares current config-derived real Codex command, command digest, workspace path, target file, mutation allowlist, startup preflight expected execution, execution candidate, real-execution dry-run, and operator-reviewed request evidence as matched, missing, or drift rows before any real Codex execution can be considered, with writer and terminal-output consistency validation for status-derived readiness, comparison summary counters, missing-artifact lists, drift/missing comparison ids, missing-side markers, blocking-reason coverage, current-evidence drift for derived payloads, shared `codex_intake_readiness` blocker surfacing, and terminal-only metadata stripping before schema checks, without recording approval, executing commands, executing Codex, creating workspaces, writing config, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
120. Deterministic operator-cockpit binding for the saved Codex CLI unlock runbook and execution readiness diff, including source-file hash validation, runbook status counters, readiness-diff summary counters, a dedicated `codex_cli_unlock_runbook` panel, a dedicated `codex_cli_readiness_diff` panel, a `codex_cli_intake` panel for selected-attempt intake-binding status, and read-only command hints for reviewing the runbook and diff, without recording approval, executing commands, executing Codex, creating workspaces, writing config, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
121. Transient operator-cockpit snapshot freshness metadata in `python -m orchestrator.experiments cockpit <run_id>` output, which compares saved cockpit source hashes with current source files and reports stale sources plus the explicit cockpit refresh command, without changing the saved `operator_cockpit.json` contract, recording approval, executing commands, executing Codex, creating workspaces, writing config, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
122. A deterministic `python -m orchestrator.experiments refresh-operator-views <run_id>` convenience command that rewrites existing read-only operator action dashboard, Codex CLI execution preflight, operator unlock checklist, Codex CLI unlock runbook, Codex CLI execution readiness diff, and operator cockpit artifacts in dependency order, using the run's recorded config path unless explicitly overridden, and returns a terminal-only `operator_view_refresh_v1` receipt with pre-refresh cockpit stale-source evidence, refreshed file hashes, post-refresh cockpit freshness, refresh-effect status, operator-review-required flag, deterministic review reason codes, refreshed-cockpit operator-digest headline/priority/target-panel state, refreshed-cockpit action execution-readiness and path-closure status, refreshed-cockpit blocker preview, refreshed operator-home navigation status including next-command text, status, blocked state, blocker count, operator hint, boundary, write target, explicit-invocation flag, approval flags, guarded-executor flag, and hint-only flag, Codex unlock-runbook status and command hint, readiness-diff status, and intake readiness, before/after blocker delta counts, digest-backed next-command summary including command source, reason, and boundary classification, and compact safety-policy summary, with optional `--markdown` compact operator rendering, without creating a new artifact family, recording approval, executing commands, executing Codex, creating workspaces, writing config, executing agents, rerunning backtests, routing candidates, applying patches, promoting champions, or changing acceptance.
123. Strict local schema validation for the terminal-only `operator_view_refresh_v1` receipt through `schemas/operator_view_refresh.schema.json`, plus deterministic consistency validation for refreshed artifact counts and order, file-path bindings, blocker-delta counters, policy-summary derivation, refresh-effect derivation, operator-digest command reason and boundary binding, home-command hint-only binding, and copied home and review-summary next-command text, safety, reason, and boundary metadata, applied before printing JSON or markdown output, so refresh receipt fields, nested reason summaries, blocker deltas, policy summaries, home navigation fields, and refreshed artifact file records cannot drift without tests or schema updates, while still not creating a new artifact family, recording approval, executing commands, executing Codex, creating workspaces, writing config, executing agents, rerunning backtests, routing candidates, applying patches, promoting champions, or changing acceptance.
124. Strict local consistency validation for the terminal-only `operator_run_review_v1` payload exposed by `python -m orchestrator.experiments review <run_id>`, including embedded dashboard fixed gate order, gate-to-summary status bindings, selected-candidate and watchlist counts, read-only dashboard authority, and policy flag equality between the review wrapper and dashboard, applied before JSON or markdown output is printed, without writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
125. Strict local consistency validation for the terminal-only `experiment_summary_dashboard_v1` payload exposed by `python -m orchestrator.experiments summary`, including latest-run to recent-tail binding, accepted-row and completed-round invariants, latest-run operator-home availability, run, command, boundary, terminal-only, artifact-created, and hint-only bindings, champion-gap active/status/gap consistency, watchlist alert identity, alert summary counters, and outer/watchlist policy flags, applied before JSON or markdown output is printed, without writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
126. Strict local schema and consistency validation for the terminal-only `champion_status_v1` payload exposed by `python -m orchestrator.experiments champion`, including current champion existence, registry schema version, champion-run binding to the embedded lineage summary, latest history champion and validation EV checks, lineage event counters, and read-only status/lineage policy flags, applied before JSON output is printed, without writing champion registry files, appending champion history, promoting champions, rerunning backtests, routing candidates, applying patches, or changing acceptance.
127. Strict local schema and consistency validation for the terminal-only `experiment_leaderboard` payload exposed by `python -m orchestrator.experiments leaderboard`, including bounded row count, unique run IDs, descending validation EV-delta and creation-time ordering, single-run EV delta arithmetic, and non-negative iteration completed-round counts, applied before JSON output is printed without executing agents, rerunning backtests, promoting champions, applying patches, or changing acceptance.
128. Strict local schema and consistency validation for the terminal-only `candidate_leaderboard` payload exposed by `python -m orchestrator.experiments candidates <run_id>`, including bounded row count, run-id binding, unique round/attempt identity, stable candidate ranking order, positive attempt indexes, quality-score binding, and selected-row validation/holdout signal checks, applied before JSON output is printed without executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
129. Strict local schema and consistency validation for the terminal-only `agent_result_stats_v1` payload exposed by `python -m orchestrator.experiments agents <run_id>`, including run-id and source-path binding, totals recomputation, agent/direction/patch-family aggregate recomputation, routing hint recomputation, optional artifact-source flag checks, and round replay summary normalization, applied before JSON output is printed without executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
129a. A terminal-only `operator_action_guide_v1` payload exposed by `python -m orchestrator.experiments action-guide <run_id>` and `python -m orchestrator.operator_action_guide experiments/<run_id>`, backed by `schemas/operator_action_guide.schema.json`, that reads the saved or derived operator action dashboard and turns its current step, recommended command, execution-readiness checkpoint, path-closure checkpoint, blockers, command sequence, and `operator_action_guided_path_v1` checklist into a guided next-step view. The checklist normalizes action-audit refresh, operator approval, guarded read-only execution, and dashboard review into active/available/waiting/complete rows. The guide validates source-dashboard binding, status derivation, next-command hints, guided-path rows, blocker previews, authority flags, and read-only policy before printing JSON or markdown, without creating run artifacts, recording approval, executing commands, writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
129b. A terminal-only `operator_home_v1` payload exposed by `python -m orchestrator.experiments home <run_id>`, `python -m orchestrator.experiments home --latest`, and `python -m orchestrator.operator_home experiments/<run_id>`, backed by `schemas/operator_home.schema.json`, that derives from the current cockpit and action guide to combine run outcome, primary focus, guided action path, next command, next-command status and blocker summary, next-command safety flags for hint-only behavior, explicit operator invocation, approval requirements, approval-receipt writing, guarded-executor usage, and target artifact, cockpit review priority, Codex CLI preflight/unlock-runbook/readiness-diff/intake-binding status, command-center hints, blockers, source view records, authority flags, and read-only policy into one operator landing page, with schema and current-evidence validation before printing JSON or markdown, latest-run resolution through the append-only experiment index, closeout `manifest.json` and `summary.md` navigation rows that expose the read-only home command, terminal-only flag, home status, action step, next-command text, label/status/blocked state/boundary/blocker count/operator hint/safety flags, unlock-runbook status, and intake-readiness status without creating an `operator_home.json` artifact, and no run artifacts created, without recording approval, executing commands, writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
129c. A read-only `python -m orchestrator.experiments list --limit N` enhancement that returns recent append-only index rows with a derived `operator_home` hint per row: iteration-loop rows expose the terminal-only home markdown command, status, read-only boundary, hint-only flags, next-command text, label, status, blocked flag, blocker count, operator hint, boundary, write target, explicit-invocation flag, approval flags, guarded-executor flag, and hint-only flag, while single-run rows mark the hint and next-command state unavailable, without rewriting `index.jsonl`, creating artifacts, executing commands, writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
129d. A read-only `python -m orchestrator.experiments show <run_id>` enhancement that returns the same derived `operator_home` hint in the compact run payload: iteration-loop runs expose the terminal-only home markdown command, status, read-only boundary, hint-only flags, next-command text, label, status, blocked flag, blocker count, operator hint, boundary, write target, explicit-invocation flag, approval flags, guarded-executor flag, and hint-only flag, while single-run payloads mark the hint and next-command state unavailable, without rewriting `index.jsonl`, creating artifacts, executing commands, writing config, promoting champions, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
130. Strict local schema and consistency validation for the terminal-only `proposal_outcome_memory` payload exposed by `python -m orchestrator.experiments memory --limit N`, including bounded recent-window binding to `experiments/memory.jsonl`, proposal-outcome identity, run and round identity, accepted boolean checks, and optional validation EV type checks, applied before JSON output is printed without executing agents, rerunning backtests, routing candidates, applying patches, deleting memory, or changing acceptance.
131. Strict local schema and current-evidence validation for terminal-only `memory_diagnostics_v1` payloads exposed by `python -m orchestrator.memory_diagnostics` and `python -m orchestrator.experiments memory-diagnostics`, including binding to the selected experiments directory, outcome memory, artifact-health history path, recent link limit, created-at scope, grouped diagnostics, and totals before JSON output is printed, without executing agents, rerunning backtests, routing candidates, applying patches, deleting memory, or changing acceptance.
132. Strict local schema, internal consistency, and current-evidence validation for dynamic terminal-only `memory_hygiene_v1` payloads exposed by `python -m orchestrator.memory_hygiene`, plus schema and internal consistency validation for saved-artifact terminal output exposed by `python -m orchestrator.experiments memory-hygiene <run_id>`, preserving append-only memory behavior without binding old saved reports to future memory records, without deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
133. Strict local schema, deterministic recommendation, candidate-scope, and optional current-evidence validation for terminal-only `memory_scope_recommendation_v1` payloads exposed by `python -m orchestrator.memory_scope_recommendation` and `python -m orchestrator.experiments memory-scope-recommendation <run_id>`, including saved hygiene source binding and advisory-only policy checks before JSON output is printed, without writing config, deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
134. Strict local schema, run binding, internal consistency, and optional current-evidence validation for terminal-only config advisory payloads exposed by `python -m orchestrator.experiments config-change-candidate <run_id>`, `operator-config-review <run_id>`, and `config-application-dry-run <run_id>`, including candidate summaries, review gates, reviewed-row decisions, application gate counts, planned-row readiness, status, and next-action derivation before JSON output is printed, without writing config, deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.
135. Strict local schema, run binding, internal consistency, and optional current-evidence validation for terminal-only config rollback and lineage payloads exposed by `python -m orchestrator.experiments config-application-rollback-preview <run_id>` and `config-lineage <run_id>`, including rollback gate counts, row restore readiness, next-run impact, stage order, stage counts, action flags, current-config summary, status derivation, and source-artifact evidence checks before JSON output is printed, without writing config, deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, restoring config, or changing acceptance.
136. Strict local schema, run binding, internal consistency, and optional current-evidence validation for saved and terminal-only config runbook payloads written during closeout, written by `python -m orchestrator.config_operator_runbook`, and exposed through `python -m orchestrator.experiments config-runbook <run_id>`, including artifact file records, step statuses, blockers, command hints, shell-control-token safety, explicit operator invocation, write-config marking, summary-count consistency, authority flags, and read-only policy before JSON or markdown output is printed, without recording approval, executing commands, writing config, restoring config, deleting memory, executing agents, rerunning backtests, routing candidates, applying patches, or changing acceptance.

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
- Config operator runbook: `schemas/config_operator_runbook.schema.json`
- Config lineage: `schemas/config_lineage.schema.json`
- Experiment scope health: `schemas/experiment_scope_health.schema.json`
- Run closeout: `schemas/run_closeout.schema.json`
- Operator action plan: `schemas/operator_action_plan.schema.json`
- Operator action approval: `schemas/operator_action_approval.schema.json`
- Operator action execution receipt:
  `schemas/operator_action_execution_receipt.schema.json`
- Operator action audit: `schemas/operator_action_audit.schema.json`
- Operator action dashboard: `schemas/operator_action_dashboard.schema.json`
- Operator action guide: `schemas/operator_action_guide.schema.json`
- Operator home: `schemas/operator_home.schema.json`
- Operator cockpit: `schemas/operator_cockpit.schema.json`
- Candidate quality trace: `schemas/candidate_quality_trace.schema.json`
- Candidate challenger report: `schemas/candidate_challenger_report.schema.json`
- Champion promotion dry-run: `schemas/champion_promotion_dry_run.schema.json`
- Champion promotion approval: `schemas/champion_promotion_approval.schema.json`
- Champion promotion receipt: `schemas/champion_promotion_receipt.schema.json`
- Champion lineage: `schemas/champion_lineage.schema.json`
- Proposal outcome memory terminal view:
  `schemas/proposal_outcome_memory.schema.json`

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
- Execution readiness diff:
  `schemas/codex_cli_execution_readiness_diff.schema.json`

## Safety Invariants

1. Deterministic gates keep final acceptance authority.
2. Agent text can propose patches but cannot accept strategies.
3. Strategy-improvement patches may only modify `strategies/current_strategy.py`.
4. Data under `data/` is immutable experiment input.
5. Codex CLI canary and unlock readiness require a bound, blocker-free selected
   `agent_execution.intake_binding`; subprocess evidence alone is not enough to
   unlock future real execution.
6. V0.5 must not call real exchange, wallet, Polymarket, Binance, or network APIs.
7. Real Codex CLI strategy execution remains out of scope until the full
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
    candidates, apply patches, or change strategy acceptance. The terminal-only
    `operator_run_review_v1` payload exposed by
    `python -m orchestrator.experiments review <run_id>` is validated against
    `schemas/operator_run_review.schema.json` before JSON or markdown output is
    printed, with deterministic consistency checks for copied top-level status,
    round, stop-reason, and config-lineage summary fields.
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
23. Proposal intent summaries and consistency checks in
    `agent_output_quarantine.json` bind pre-apply quarantine reports to the same
    context, selected attempt, patch hash, validation result, and source
    artifacts recorded in selected output and round-level agent input. They can
    prove quarantine/output/input consistency, but they cannot change
    quarantine release rules, apply patches, or change acceptance.
24. Proposal intent summaries and consistency checks in `agent_validation.json`
    bind raw-output validation reports to the same context recorded in
    round-level agent input, the normalized proposal, patch hash, and validation
    result. `agent_output.json` and `agent_validation.json` both reuse
    `schemas/strategy_proposal.schema.json` for the shared strategy proposal
    field shape. `agent_validation.json` also records `semantic_checks`, a
    structured deterministic breakdown of protocol, expected round, target,
    metadata, and patch-target contract rules. It also records
    `intake_diagnosis`, a compact stable-code summary for blocked external
    adapter outputs such as invalid patch targets, workspace mutation, missing
    patch data, malformed JSON, oversized raw output, oversized normalized
    patch diffs, invalid proposal metadata types, or git-apply failures. These
    checks can prove
    raw-output/proposal/input consistency and explain contract pass/fail, but
    they cannot change git apply checks, quarantine release rules, patch
    application, policy-gate results, holdout vetoes, or acceptance.
    Selected external execution audits also carry
    `agent_execution.intake_binding`, which binds command, prompt/stdin where
    applicable, raw response, saved proposal, and validation artifacts back to
    the same shared intake path. This binding is audit evidence only and cannot
    route candidates, release quarantine, apply patches, or change acceptance.
    Codex CLI contract fixtures, canary gates, and final unlock gates require
    the selected binding to be present and clean before reporting readiness.
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
    lineage command writes lineage artifacts. The terminal-only
    `champion_status_v1` payload exposed by the `champion` inspection command
    is validated against `schemas/champion_status.schema.json` before JSON
    output is printed, with deterministic consistency checks for current
    registry-to-lineage binding, latest-history champion identity, validation
    EV equality, lineage event counters, and read-only policy flags.
32. Experiment summary dashboards are read-only inspection payloads embedded in
    `python -m orchestrator.experiments summary`. They can summarize latest
    indexed runs, recent diagnosis rows, recent failure-code counts, and
    best-run-to-champion gaps, and they may include a deterministic operator
    watchlist for repeated proposals, artifact-health failures, and champion
    gap alerts. They cannot execute agents, run backtests, route candidates,
    apply patches, promote champions, write artifacts, or change strategy
    acceptance. The optional `summary --markdown` mode renders the same payload
    for terminal inspection without writing artifacts.
    The embedded `experiment_summary_dashboard_v1` payload is validated against
    `schemas/experiment_summary_dashboard.schema.json` before JSON or markdown
    output is printed, with deterministic consistency checks for recent
    failure/outcome counters, top recent summary fields, latest accepted or
    rejected status rows, and watchlist alert summaries.
    The validator also checks latest-run to recent-tail binding, accepted-row
    flags, non-negative completed round counts, champion-gap active/status/gap
    invariants, watchlist alert codes, and outer/watchlist policy flags before
    terminal JSON or markdown is emitted.
    Experiment leaderboard terminal output is also schema-validated before JSON
    is emitted. Its validator checks row bounds, run identity uniqueness,
    ranking order, single-run EV delta arithmetic, and iteration round-count
    sanity without executing agents, rerunning backtests, applying patches, or
    changing acceptance.
    Candidate leaderboard terminal output is also schema-validated before JSON
    is emitted. Its validator checks run-id binding, row bounds, round/attempt
    uniqueness, ranking order, candidate score to quality-score binding, and
    selected validation/holdout signal presence without executing agents,
    rerunning backtests, routing candidates, applying patches, or changing
    acceptance.
    Agent result stats terminal output is schema-validated before JSON is
    emitted. Its validator recomputes totals, agent/direction/patch-family
    aggregates, routing hints, source-path binding, and replay summaries from
    saved run artifacts without executing agents, rerunning backtests, routing
    candidates, applying patches, or changing acceptance.
33. Operator cockpit panels include Codex CLI execution preflight state as a
    read-only unlock visibility layer. They may summarize real-execution
    profile counts, operator-unlock-ready counts, and startup blockers, but
    they cannot record unlock approval, execute Codex, run agents, create
    workspaces, apply patches, route candidates, or change strategy acceptance.
34. Operator cockpit unlock visibility also includes a grouped
    `codex_unlock_checklist` derived from startup preflight checks. It may
    classify operator request, intent, source evidence, execution identity,
    command digest, workspace boundary, mutation boundary, and non-executing
    request evidence as passed or failed, but it remains read-only and cannot
    unlock Codex or execute anything.
35. Operator unlock checklist artifacts are the standalone source of the same
    grouped Codex CLI unlock evidence. They may be embedded or summarized by
    cockpit views, and may include command hints for missing evidence artifacts,
    but they cannot record approval, execute those commands, execute Codex,
    create workspaces, apply patches, route candidates, or change strategy
    acceptance.
36. Operator action plan and operator action dashboard terminal outputs are
    schema-validated before JSON or markdown is emitted. Their validators check
    summary counts, status-derived fields, command digests, authority flags,
    read-only policy flags, and current-evidence equality for derived payloads
    without recording approval, executing commands, writing config, promoting
    champions, running agents, rerunning backtests, routing candidates,
    applying patches, or changing acceptance.
37. Operator action approval and operator action execution receipt terminal
    outputs are schema-validated before JSON or markdown is emitted. Their
    validators replay source action-plan or approval bindings, selected command
    hashes, confirmation phrase evidence, approval gates, execution command
    argv, evidence-check rows, mutation guard status, and read-only policy flags
    without executing new commands from terminal inspection, writing config,
    promoting champions, running agents, rerunning backtests, routing
    candidates, applying patches, or changing acceptance.

## Near-Term Development Order

1. Keep `TASK.md` aligned with the current V0.5 boundary.
2. Keep `AGENTS.md` focused on rules that affect code changes.
3. Put expanding artifact and readiness detail in this roadmap or narrower docs.
4. Prefer artifact validators and replay commands over undocumented assumptions.
5. Add a schema or fixture before adding a new generated artifact family.
