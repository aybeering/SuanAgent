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
- Experiment scope health: `schemas/experiment_scope_health.schema.json`

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

## Near-Term Development Order

1. Keep `TASK.md` aligned with the current V0.5 boundary.
2. Keep `AGENTS.md` focused on rules that affect code changes.
3. Put expanding artifact and readiness detail in this roadmap or narrower docs.
4. Prefer artifact validators and replay commands over undocumented assumptions.
5. Add a schema or fixture before adding a new generated artifact family.
