"""Dry-run Codex CLI adapter.

This adapter preserves the future isolated Codex CLI boundary without invoking
Codex. It builds the prompt and command that a real adapter would use, then
returns a non-applicable proposal so the deterministic loop can exercise the
control flow safely.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.patch_parser import (
    PatchParseError,
    extract_json_object,
    extract_unified_diff,
    validate_patch_targets,
)
from orchestrator.proposal import StrategyProposal
from orchestrator.workspace_manager import create_isolated_workspace


class CodexDryRunModifier:
    """A dry-run stand-in for a future isolated Codex CLI process."""

    agent_name = "codex_cli_dry_run"

    def __init__(
        self,
        *,
        executable: str = "codex",
        model: str = "default",
        sandbox: str = "workspace-write",
        workspace_root: str = "workspaces",
    ) -> None:
        self.executable = executable
        self.model = model
        self.sandbox = sandbox
        self.workspace_root = Path(workspace_root)

    def propose_strategy_change(
        self,
        *,
        report_path: Path,
        target_file: Path,
        round_index: int,
        repo_root: Path,
        old_threshold: str,
        new_threshold: str,
        context_path: Path | None = None,
    ) -> StrategyProposal:
        """Return a no-op proposal with the would-be Codex prompt and command."""
        report_text = report_path.read_text(encoding="utf-8")
        context_text = context_path.read_text(encoding="utf-8") if context_path else ""
        intent_text = proposal_intent_text(context_path)
        target_relative = target_file.relative_to(repo_root)
        run_id, round_id = workspace_ids_from_report(report_path)
        workspace_path = create_isolated_workspace(
            repo_root=repo_root,
            workspace_root=repo_root / self.workspace_root,
            run_id=run_id,
            round_id=round_id,
        )
        prompt = build_codex_prompt(
            report_text=report_text,
            target_file=str(target_relative),
            round_index=round_index,
            context_text=context_text,
            intent_text=intent_text,
        )
        command = build_codex_command(
            executable=self.executable,
            model=self.model,
            sandbox=self.sandbox,
            target_file=str(target_relative),
        )
        return StrategyProposal(
            agent_name=self.agent_name,
            round_index=round_index,
            target_file=str(target_relative),
            summary="Dry-run Codex CLI adapter built a command but did not run it.",
            risk_notes="No patch was generated; this adapter is for CLI boundary tests.",
            expected_metric_change={},
            raw_response=(
                "codex cli dry-run response: "
                f"built command for report with {len(report_text)} characters"
            ),
            patch_diff="",
            applicable=False,
            direction_tag="codex_dry_run",
            hypotheses=(
                "A future Codex CLI call should inspect the train report before editing.",
            ),
            rejection_reason="Codex CLI dry-run adapter does not emit patches.",
            prompt=prompt,
            command=tuple(command),
            workspace_path=str(workspace_path),
        )


def build_codex_prompt(
    *,
    report_text: str,
    target_file: str,
    round_index: int,
    context_text: str = "",
    intent_text: str = "",
) -> str:
    """Build the prompt that would be sent to an isolated Codex CLI process."""
    return "\n".join(
        [
            "You are modifying a strategy for SuanAgent V0.5.",
            f"Round: {round_index}",
            f"Only modify: {target_file}",
            "Do not modify data, backtester, reports, orchestrator, or tests.",
            "Return either a unified diff patch or a JSON object with fields: "
            "summary, risk_notes, direction_tag, expected_metric_change, "
            "hypotheses, patch_diff.",
            "",
            "Prior proposal context:",
            "If a sibling agent_context.json artifact exists, treat it as the "
            "machine-readable version of this context.",
            context_text or "No prior proposal context was provided.",
            "",
            "Proposal intent:",
            "If proposal_intent.json exists, treat it as the compact planner "
            "instruction derived from the context.",
            intent_text or "No proposal intent was provided.",
            "",
            "Report:",
            report_text,
        ]
    )


def proposal_intent_text(context_path: Path | None) -> str:
    """Return pretty proposal intent JSON located next to agent context."""
    if context_path is None:
        return ""
    intent_path = context_path.with_name("proposal_intent.json")
    if not intent_path.exists():
        return ""
    payload = load_json(intent_path)
    if not payload:
        return intent_path.read_text(encoding="utf-8")
    return json.dumps(payload, indent=2, sort_keys=True)


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object if present."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_codex_command(
    *,
    executable: str,
    model: str,
    sandbox: str,
    target_file: str,
) -> list[str]:
    """Build the future Codex CLI command without executing it."""
    return [
        executable,
        "exec",
        "--model",
        model,
        "--sandbox",
        sandbox,
        "--",
        f"Modify only {target_file} and return a patch.",
    ]


def proposal_from_codex_output(
    *,
    raw_output: str,
    report_path: Path,
    target_file: Path,
    round_index: int,
    repo_root: Path,
    prompt: str,
    command: list[str],
    workspace_path: Path,
) -> StrategyProposal:
    """Convert future Codex CLI output into a StrategyProposal."""
    target_relative = target_file.relative_to(repo_root)
    metadata = extract_proposal_metadata(raw_output)
    try:
        patch_diff = metadata_patch_diff(metadata) or extract_unified_diff(raw_output)
        validate_patch_targets(patch_diff, target_relative)
    except PatchParseError as exc:
        return StrategyProposal(
            agent_name="codex_cli",
            round_index=round_index,
            target_file=str(target_relative),
            summary=str(
                metadata.get(
                    "summary",
                    "Codex output did not contain an applicable strategy patch.",
                )
            ),
            risk_notes=str(
                metadata.get(
                    "risk_notes",
                    "Patch parser rejected the output before git apply.",
                )
            ),
            expected_metric_change=metadata_expected_metric_change(metadata),
            raw_response=raw_output,
            patch_diff="",
            applicable=False,
            direction_tag=str(metadata.get("direction_tag", "codex_cli_unknown")),
            hypotheses=metadata_hypotheses(
                metadata,
                (
                    "The Codex response must contain a unified diff for the strategy file.",
                ),
            ),
            rejection_reason=str(exc),
            prompt=prompt,
            command=tuple(command),
            workspace_path=str(workspace_path),
        )

    return StrategyProposal(
        agent_name="codex_cli",
        round_index=round_index,
        target_file=str(target_relative),
        summary=str(metadata.get("summary", "Codex output produced a strategy patch.")),
        risk_notes=str(
            metadata.get("risk_notes", "Patch targets were validated before git apply.")
        ),
        expected_metric_change=metadata_expected_metric_change(metadata),
        raw_response=raw_output,
        patch_diff=patch_diff,
        applicable=True,
        direction_tag=str(metadata.get("direction_tag", "codex_cli_unknown")),
        hypotheses=metadata_hypotheses(
            metadata,
            (
                "The parsed patch is intended to improve validation metrics after simulation.",
            ),
        ),
        rejection_reason="",
        prompt=prompt,
        command=tuple(command),
        workspace_path=str(workspace_path),
    )


def extract_proposal_metadata(raw_output: str) -> dict[str, object]:
    """Return optional structured proposal metadata from Codex output."""
    try:
        payload = extract_json_object(raw_output)
    except PatchParseError:
        return {}
    proposal_payload = payload.get("proposal", payload)
    return proposal_payload if isinstance(proposal_payload, dict) else {}


def metadata_patch_diff(metadata: dict[str, object]) -> str:
    """Return patch_diff from metadata with a trailing newline, if present."""
    patch_diff = str(metadata.get("patch_diff", ""))
    if not patch_diff.strip():
        return ""
    return patch_diff if patch_diff.endswith("\n") else patch_diff + "\n"


def metadata_expected_metric_change(metadata: dict[str, object]) -> dict[str, str]:
    """Return expected metric metadata from parsed proposal JSON."""
    raw_value = metadata.get("expected_metric_change", {})
    if not isinstance(raw_value, dict):
        return {}
    return {str(key): str(value) for key, value in raw_value.items()}


def metadata_hypotheses(
    metadata: dict[str, object],
    default: tuple[str, ...],
) -> tuple[str, ...]:
    """Return hypotheses from parsed proposal JSON."""
    raw_value = metadata.get("hypotheses", ())
    if isinstance(raw_value, str) and raw_value.strip():
        return (raw_value,)
    if isinstance(raw_value, list | tuple):
        hypotheses = tuple(str(item) for item in raw_value if str(item).strip())
        if hypotheses:
            return hypotheses
    return default


def workspace_ids_from_report(report_path: Path) -> tuple[str, str]:
    """Derive stable workspace ids from an experiment report path."""
    round_id = report_path.parent.name or "round_unknown"
    run_id = report_path.parent.parent.name or "run_unknown"
    return run_id, round_id
