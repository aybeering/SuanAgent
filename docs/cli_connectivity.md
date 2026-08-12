# Codex CLI, Lark CLI, and GitHub CLI integration

The project now has a configuration entry point for the three command-line
tools that form its development base:

- Codex CLI is the project construction and execution entry point.
- GitHub CLI (`gh`) is the repository development-management entry point.
- Lark CLI is the documentation, experience-retention, and task-coordination
  entry point.

`config/cli_integrations.json` registers all three executables.
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
gh --version
gh --help
```

It does not run `auth login`, `auth status --verify`, `whoami`, `doctor`, a
model prompt, a GitHub write command, or a Lark API request. Therefore a
passing result means “the CLI is installed and starts locally,” not “the
account is authorized,” “a GitHub write is permitted,” or “the remote service
is reachable.”

For GitHub, the local probe is intentionally separate from repository access:
the Docker image contains `gh`, but it does not inherit the host's GitHub
profile. API and write checks require an explicit authorization step:

```bash
docker compose exec dev gh auth status
```

Before authorization, this command is expected to report that no account is
configured. After an operator explicitly authorizes the container, API reads
and branch, pull request, issue, or review operations can be tested separately.
An authenticated host-side Git or connector workflow remains an alternative.

Run it with:

```bash
python -m orchestrator.cli_connectivity \
  --config config/cli_integrations.json
```

Use `--strict` when the command should fail if any executable is missing or one
of the three local probes fails:

```bash
python -m orchestrator.cli_connectivity \
  --config config/cli_integrations.json --strict
```

No API key, app secret, access token, OAuth code, or account profile is stored
in this repository. Authorization and write-capability checks are intentionally
a separate explicit step.
