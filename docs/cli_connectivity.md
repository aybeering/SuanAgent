# Codex CLI and Lark CLI integration

The project now has a configuration entry point for both command-line tools:

- `config/cli_integrations.json` registers the Codex CLI executable and the
  `lark-cli` executable.
- `orchestrator/cli_connectivity.py` checks whether each executable can start
  locally.
- `schemas/cli_integrations.schema.json` validates the configuration.

## Current test boundary

The connectivity test runs only these local commands:

```text
codex --version
codex --help
lark-cli --version
lark-cli --help
```

It does not run `auth login`, `auth status --verify`, `whoami`, `doctor`, a
model prompt, or a Lark API request. Therefore a passing result means “the CLI
is installed and starts locally,” not “the account is authorized” or “the
remote service is reachable.”

Run it with:

```bash
python -m orchestrator.cli_connectivity \
  --config config/cli_integrations.json
```

Use `--strict` when the command should fail if either executable is missing or
one of the two local probes fails:

```bash
python -m orchestrator.cli_connectivity \
  --config config/cli_integrations.json --strict
```

No API key, app secret, access token, OAuth code, or account profile is stored
in this repository. Authorization and remote API checks are intentionally a
separate future step.
