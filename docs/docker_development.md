# Docker development boundary

This repository is developed and executed inside the `dev` container defined
by `docker-compose.yml`. The host only supplies the source tree and runs Docker
commands.

## What is inside the image

The image contains:

- Python 3.11 and the repository's test/runtime files;
- pytest for development checks;
- the Codex CLI, `lark-cli`, and GitHub CLI (`gh`);
- a container-owned `HOME`, `CODEX_HOME`, `/tmp`, experiment volume, and
  workspace volume.

The image does not copy the host's Python installation, virtual environment,
`PATH`, `HOME`, `CODEX_HOME`, Codex sessions, Lark profile, API keys, OAuth
tokens, or app secrets.

## Start the development container

```bash
docker compose build
docker compose up -d dev
```

Compose marks the service healthy only after the container-local Codex CLI,
Lark CLI, and GitHub CLI `--version`/`--help` probes pass. This healthcheck
still performs no authentication or business API request.

Run repository commands through the container:

```bash
docker compose exec dev python -m pytest
docker compose exec dev python -m orchestrator.preflight --config config/default.json
docker compose exec dev python -m orchestrator.smoke_contract
docker compose exec dev python -m orchestrator.cli_connectivity \
  --config config/cli_integrations.json --strict
docker compose exec dev gh auth status
```

The source tree is mounted at `/workspace`; generated experiments and agent
workspaces are Docker-managed volumes. This means paths recorded by the
program are container paths such as `/workspace`, never the host's absolute
project path.

## Codex and Lark authorization boundary

The image contains the three CLI executables, but it contains no account
authorization. Do not mount the host's `~/.codex`, Lark profile directory,
GitHub CLI profile, or any credential file into the container. Authorization is
a later explicit step, and should use a deliberately scoped container volume
or environment secret rather than a source-tree file.

The default image command runs only unauthenticated local CLI probes. It does
not call `codex exec`, `lark-cli auth`, `lark-cli doctor`, `gh auth`, `gh api`,
`whoami`, or a business API.

## Stop and inspect

```bash
docker compose down
docker compose ps
docker volume ls --filter name=suanagent
```

`docker compose down` stops the container but keeps the named volumes. The
volumes can be removed explicitly later when the developer chooses to discard
container-generated state.
