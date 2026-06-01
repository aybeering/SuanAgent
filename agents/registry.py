"""Modifier adapter registry."""

from __future__ import annotations

from agents.codex_dry_run_adapter import CodexDryRunModifier
from agents.modifier_adapter import StrategyModifier
from agents.strategy_modifier_stub import FixedPatchModifier


def get_strategy_modifier(name: str) -> StrategyModifier:
    """Return a strategy modifier adapter by configured name."""
    if name == "fixed_patch_stub":
        return FixedPatchModifier()
    if name == "codex_dry_run":
        return CodexDryRunModifier()
    raise ValueError(f"Unknown strategy modifier adapter: {name}")
