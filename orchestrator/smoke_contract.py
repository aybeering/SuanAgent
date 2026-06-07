"""Validate that required smoke commands stay documented and CI-covered."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_DOC_COMMANDS = (
    "pytest",
    "python -m orchestrator.run_loop",
    "python -m orchestrator.iteration_loop",
    "python -m orchestrator.preflight --config config/default.json",
)

REQUIRED_CI_COMMANDS = (
    "python -m pytest",
    "python -m orchestrator.run_loop",
    "python -m orchestrator.iteration_loop --run-id ci-default",
    "python -m orchestrator.preflight --config config/default.json",
)

DEFAULT_DOC_PATHS = (
    Path("README.md"),
    Path("docs/artifact_reference.md"),
)
DEFAULT_CI_PATH = Path(".github/workflows/ci.yml")


def validate_smoke_contract(*, repo_root: Path = Path(".")) -> dict[str, object]:
    """Return a read-only report for required smoke command coverage."""
    repo_root = repo_root.resolve()
    docs = [
        _path_command_report(
            path=repo_root / relative_path,
            relative_path=relative_path,
            required_commands=REQUIRED_DOC_COMMANDS,
        )
        for relative_path in DEFAULT_DOC_PATHS
    ]
    ci = _path_command_report(
        path=repo_root / DEFAULT_CI_PATH,
        relative_path=DEFAULT_CI_PATH,
        required_commands=REQUIRED_CI_COMMANDS,
    )
    missing_count = sum(len(row["missing_commands"]) for row in docs)
    missing_count += len(ci["missing_commands"])
    return {
        "schema_version": "smoke_contract_v1",
        "ok": missing_count == 0,
        "repo_root": str(repo_root),
        "required_doc_commands": list(REQUIRED_DOC_COMMANDS),
        "required_ci_commands": list(REQUIRED_CI_COMMANDS),
        "docs": docs,
        "ci": ci,
        "summary": {
            "doc_path_count": len(docs),
            "required_doc_command_count": len(REQUIRED_DOC_COMMANDS),
            "required_ci_command_count": len(REQUIRED_CI_COMMANDS),
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
