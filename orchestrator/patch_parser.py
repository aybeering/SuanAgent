"""Parse and validate unified diffs returned by strategy modifier agents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PatchParseError(ValueError):
    """Raised when agent output does not contain an acceptable patch."""


def extract_unified_diff(text: str) -> str:
    """Extract a unified diff from plain text or a fenced diff block."""
    fenced = extract_fenced_diff(text)
    if fenced:
        return fenced

    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith("--- "):
            candidate = "".join(lines[index:]).strip()
            if candidate:
                return candidate + "\n"
    raise PatchParseError("No unified diff found in agent output")


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract a JSON object from plain text or a fenced json block."""
    fenced = extract_fenced_json(text)
    if fenced:
        return parse_json_object(fenced)

    stripped = text.strip()
    if stripped.startswith("{"):
        return parse_json_object(stripped)

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return parse_json_object(text[start : end + 1])
    raise PatchParseError("No JSON object found in agent output")


def extract_fenced_json(text: str) -> str:
    """Return the first fenced json block, or an empty string."""
    lines = text.splitlines(keepends=True)
    in_block = False
    block: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not in_block and stripped in {"```json", "```JSON"}:
            in_block = True
            continue
        if in_block and stripped == "```":
            return "".join(block).strip()
        if in_block:
            block.append(line)
    return ""


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse text as a JSON object."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PatchParseError(f"Invalid JSON object in agent output: {exc}") from exc
    if not isinstance(payload, dict):
        raise PatchParseError("Agent JSON output must be an object")
    return payload


def extract_fenced_diff(text: str) -> str:
    """Return the first fenced diff block, or an empty string."""
    lines = text.splitlines(keepends=True)
    in_block = False
    block: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not in_block and stripped in {"```diff", "```patch"}:
            in_block = True
            continue
        if in_block and stripped == "```":
            return "".join(block).strip() + "\n"
        if in_block:
            block.append(line)
    return ""


def changed_paths_from_diff(patch_diff: str) -> set[str]:
    """Return file paths changed by a unified diff."""
    paths: set[str] = set()
    for line in patch_diff.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            path = normalize_diff_path(line[4:].strip())
            if path != "/dev/null":
                paths.add(path)
    return paths


def normalize_diff_path(path_text: str) -> str:
    """Normalize a diff path by removing a/ and b/ prefixes."""
    path_text = path_text.split("\t", maxsplit=1)[0]
    if path_text.startswith("a/") or path_text.startswith("b/"):
        return path_text[2:]
    return path_text


def validate_patch_targets(patch_diff: str, allowed_path: Path) -> None:
    """Ensure a patch only touches the allowed strategy file."""
    allowed = str(allowed_path)
    changed_paths = changed_paths_from_diff(patch_diff)
    if not changed_paths:
        raise PatchParseError("Patch does not contain changed file paths")
    disallowed = sorted(path for path in changed_paths if path != allowed)
    if disallowed:
        raise PatchParseError(
            "Patch touches disallowed files: " + ", ".join(disallowed)
        )
