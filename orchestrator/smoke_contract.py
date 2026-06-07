"""Validate that required smoke commands stay documented and CI-covered."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from orchestrator.schema_validation import load_schema, validate_json_payload


TASK_PATH = Path("TASK.md")
DEFAULT_DOC_PATHS = (
    Path("README.md"),
    Path("docs/artifact_reference.md"),
)
DEFAULT_CI_PATH = Path(".github/workflows/ci.yml")
SMOKE_CONTRACT_SCHEMA_PATH = Path("schemas/smoke_contract.schema.json")
CI_COMMAND_OVERRIDES = {
    "pytest": "python -m pytest",
    "python -m orchestrator.iteration_loop": (
        "python -m orchestrator.iteration_loop --run-id ci-default"
    ),
}


def validate_smoke_contract(*, repo_root: Path = Path(".")) -> dict[str, object]:
    """Return a read-only report for required smoke command coverage."""
    repo_root = repo_root.resolve()
    source = required_smoke_commands_from_task(repo_root=repo_root)
    required_doc_commands = tuple(source["commands"])
    required_ci_commands = tuple(
        CI_COMMAND_OVERRIDES.get(command, command) for command in required_doc_commands
    )
    docs = [
        _path_command_report(
            path=repo_root / relative_path,
            relative_path=relative_path,
            required_commands=required_doc_commands,
        )
        for relative_path in DEFAULT_DOC_PATHS
    ]
    ci = _path_command_report(
        path=repo_root / DEFAULT_CI_PATH,
        relative_path=DEFAULT_CI_PATH,
        required_commands=required_ci_commands,
    )
    missing_count = sum(len(row["missing_commands"]) for row in docs)
    missing_count += len(ci["missing_commands"])
    if not source["ok"]:
        missing_count += 1
    return {
        "schema_version": "smoke_contract_v1",
        "ok": missing_count == 0,
        "repo_root": str(repo_root),
        "source": source,
        "required_doc_commands": list(required_doc_commands),
        "required_ci_commands": list(required_ci_commands),
        "docs": docs,
        "ci": ci,
        "summary": {
            "doc_path_count": len(docs),
            "required_doc_command_count": len(required_doc_commands),
            "required_ci_command_count": len(required_ci_commands),
            "missing_count": missing_count,
        },
        "policy": {
            "inspection_only": True,
            "does_not_run_tests": True,
            "does_not_run_backtests": True,
            "does_not_create_experiments": True,
            "does_not_change_acceptance": True,
        },
    }


def required_smoke_commands_from_task(
    *,
    repo_root: Path = Path("."),
) -> dict[str, object]:
    """Read the required smoke commands from TASK.md."""
    task_path = repo_root.resolve() / TASK_PATH
    if not task_path.exists():
        return {
            "path": str(TASK_PATH),
            "ok": False,
            "commands": [],
            "errors": ["task_file_missing"],
        }
    text = task_path.read_text(encoding="utf-8")
    marker = "## Required smoke checks"
    marker_index = text.find(marker)
    if marker_index < 0:
        return {
            "path": str(TASK_PATH),
            "ok": False,
            "commands": [],
            "errors": ["required_smoke_section_missing"],
        }
    block_start = text.find("```", marker_index)
    if block_start < 0:
        return {
            "path": str(TASK_PATH),
            "ok": False,
            "commands": [],
            "errors": ["required_smoke_code_block_missing"],
        }
    first_line_end = text.find("\n", block_start)
    block_end = text.find("```", first_line_end)
    if first_line_end < 0 or block_end < 0:
        return {
            "path": str(TASK_PATH),
            "ok": False,
            "commands": [],
            "errors": ["required_smoke_code_block_unclosed"],
        }
    commands = [
        line.strip()
        for line in text[first_line_end:block_end].splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return {
        "path": str(TASK_PATH),
        "ok": bool(commands),
        "commands": commands,
        "errors": [] if commands else ["required_smoke_commands_empty"],
    }


def validate_smoke_contract_payload(
    payload: dict[str, object],
    *,
    repo_root: Path = Path("."),
) -> tuple[str, ...]:
    """Validate a smoke-contract payload against its local schema."""
    schema_path = repo_root.resolve() / SMOKE_CONTRACT_SCHEMA_PATH
    schema = load_schema(schema_path)
    return validate_json_payload(
        payload=payload,
        schema=schema,
        schema_dir=schema_path.parent,
    )


def _path_command_report(
    *,
    path: Path,
    relative_path: Path,
    required_commands: tuple[str, ...],
) -> dict[str, object]:
    """Return command coverage for one text file."""
    if not path.exists():
        return {
            "path": str(relative_path),
            "exists": False,
            "present_commands": [],
            "missing_commands": list(required_commands),
        }
    text = path.read_text(encoding="utf-8")
    present_commands = [command for command in required_commands if command in text]
    missing_commands = [command for command in required_commands if command not in text]
    return {
        "path": str(relative_path),
        "exists": True,
        "present_commands": present_commands,
        "missing_commands": missing_commands,
    }


def main() -> None:
    """CLI entrypoint for `python -m orchestrator.smoke_contract`."""
    args = parse_args()
    payload = validate_smoke_contract(repo_root=args.repo_root)
    schema_errors = validate_smoke_contract_payload(payload, repo_root=args.repo_root)
    if schema_errors:
        payload = {
            **payload,
            "ok": False,
            "schema_errors": list(schema_errors),
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for smoke contract validation."""
    parser = argparse.ArgumentParser(
        description="Validate required smoke command coverage in docs and CI.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root to inspect.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
