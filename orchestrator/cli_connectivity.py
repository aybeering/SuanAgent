"""Unauthenticated local availability checks for project CLI integrations.

The checks intentionally run only ``<cli> --version`` and ``<cli> --help``.
They prove that a configured executable can start locally; they do not prove
login state, API access, model access, Lark permissions, or network reachability.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from orchestrator.schema_validation import validate_json_payload


SCHEMA_VERSION = "cli_integrations_v1"
SCHEMA_FILENAME = "cli_integrations.schema.json"
PROBES = (("version", ("--version",)), ("help", ("--help",)))


class CliConnectivityError(ValueError):
    """Raised when the local CLI integration configuration is invalid."""


def load_cli_config(config_path: Path) -> dict[str, Any]:
    """Load and validate the no-auth CLI integration configuration."""
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    schema_path = config_path.parent.parent / "schemas" / SCHEMA_FILENAME
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = validate_json_payload(
        payload=payload,
        schema=schema,
        schema_dir=schema_path.parent,
    )
    if errors:
        raise CliConnectivityError("CLI integration config errors: " + "; ".join(errors))
    return payload


def probe_cli(*, integration: str, executable: str, purpose: str, timeout_seconds: int) -> dict[str, Any]:
    """Probe one executable without authentication or network requests."""
    resolved = _resolve_executable(executable)
    result: dict[str, Any] = {
        "integration": integration,
        "purpose": purpose,
        "configured_executable": executable,
        "resolved_executable": str(resolved) if resolved else "",
        "authentication": {"attempted": False, "status": "not_run"},
        "network": {"attempted": False, "status": "not_run"},
        "probes": {},
        "status": "missing",
    }
    if resolved is None:
        return result

    probe_results: dict[str, Any] = {}
    for probe_name, args in PROBES:
        probe_results[probe_name] = _run_probe(
            executable=str(resolved),
            args=args,
            timeout_seconds=timeout_seconds,
        )
    result["probes"] = probe_results
    version_probe = probe_results["version"]
    help_probe = probe_results["help"]
    result["version"] = version_probe["first_line"]
    result["available"] = bool(version_probe["ok"] and help_probe["ok"])
    result["status"] = "available_local_only" if result["available"] else "probe_failed"
    return result


def run_connectivity_test(*, config_path: Path) -> dict[str, Any]:
    """Return local availability for every configured CLI integration."""
    payload = load_cli_config(config_path)
    timeout_seconds = int(payload["connectivity_test"]["timeout_seconds"])
    results = [
        probe_cli(
            integration=name,
            executable=str(settings["executable"]),
            purpose=str(settings["purpose"]),
            timeout_seconds=timeout_seconds,
        )
        for name, settings in payload["integrations"].items()
    ]
    return {
        "schema_version": "cli_connectivity_v1",
        "config_path": str(config_path),
        "scope": {
            "local_executable_probe": True,
            "authentication_probe": False,
            "network_probe": False,
            "business_api_probe": False,
        },
        "results": results,
        "summary": {
            "integration_count": len(results),
            "available_local_count": sum(item["status"] == "available_local_only" for item in results),
            "missing_or_failed_count": sum(item["status"] != "available_local_only" for item in results),
        },
    }


def _resolve_executable(executable: str) -> Path | None:
    candidate = Path(executable)
    if candidate.is_absolute() or os.sep in executable:
        return candidate if candidate.is_file() and os.access(candidate, os.X_OK) else None
    resolved = shutil.which(executable)
    return Path(resolved) if resolved else None


def _run_probe(*, executable: str, args: tuple[str, ...], timeout_seconds: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [executable, *args],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "args": list(args),
            "ok": False,
            "returncode": None,
            "timed_out": True,
            "first_line": "",
        }
    first_line = _first_line(completed.stdout) or _first_line(completed.stderr)
    return {
        "args": list(args),
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "timed_out": False,
        "first_line": first_line,
    }


def _first_line(value: str) -> str:
    return next((line.strip() for line in value.splitlines() if line.strip()), "")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check local Codex, Lark, and GitHub CLI availability without auth.")
    parser.add_argument("--config", type=Path, default=Path("config/cli_integrations.json"))
    parser.add_argument("--strict", action="store_true", help="exit 1 if either CLI is unavailable or probe fails")
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = run_connectivity_test(config_path=args.config)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if args.strict and report["summary"]["missing_or_failed_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
