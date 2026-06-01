"""Modifier adapter registry."""

from __future__ import annotations

from agents.codex_cli_adapter import CodexCliModifier
from agents.codex_dry_run_adapter import CodexDryRunModifier
from agents.modifier_adapter import StrategyModifier
from agents.strategy_modifier_conservative_stub import ConservativePatchModifier
from agents.strategy_modifier_adaptive_stub import AdaptivePatchModifier
from agents.strategy_modifier_stub import FixedPatchModifier


SUPPORTED_MODIFIERS = {
    "fixed_patch_stub",
    "adaptive_stub",
    "conservative_stub",
    "codex_dry_run",
    "codex_cli_dry_run",
    "codex_cli",
}


def get_strategy_modifier(
    name: str,
    settings: dict[str, object] | None = None,
) -> StrategyModifier:
    """Return a strategy modifier adapter by configured name."""
    active_settings = settings or {}
    if name == "fixed_patch_stub":
        return FixedPatchModifier()
    if name == "adaptive_stub":
        return AdaptivePatchModifier()
    if name == "conservative_stub":
        return ConservativePatchModifier()
    if name in {"codex_dry_run", "codex_cli_dry_run"}:
        return CodexDryRunModifier(
            executable=str(active_settings.get("executable", "codex")),
            model=str(active_settings.get("model", "default")),
            sandbox=str(active_settings.get("sandbox", "workspace-write")),
            workspace_root=str(active_settings.get("workspace_root", "workspaces")),
        )
    if name == "codex_cli":
        return CodexCliModifier(
            executable=str(active_settings.get("executable", "codex")),
            model=str(active_settings.get("model", "default")),
            sandbox=str(active_settings.get("sandbox", "workspace-write")),
            workspace_root=str(active_settings.get("workspace_root", "workspaces")),
            execute=bool(active_settings.get("execute", False)),
            timeout_seconds=int(active_settings.get("timeout_seconds", 120)),
        )
    raise ValueError(f"Unknown strategy modifier adapter: {name}")
