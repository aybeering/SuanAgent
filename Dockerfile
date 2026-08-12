FROM python:3.11-slim-bookworm

ARG CODEX_CLI_VERSION=0.147.0-alpha.6.5
ARG LARK_CLI_VERSION=1.0.85

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace \
    HOME=/home/suanagent \
    CODEX_HOME=/home/suanagent/.codex \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    NPM_CONFIG_FUND=false

WORKDIR /workspace

# The image owns the Python and CLI runtimes. Nothing is copied from the
# developer's host installation. Versions are build arguments so an operator
# can deliberately upgrade them instead of silently inheriting host binaries.
RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl git nodejs npm \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global --no-update-notifier \
        "@openai/codex@${CODEX_CLI_VERSION}" \
        "@larksuite/cli@${LARK_CLI_VERSION}" \
    && npm cache clean --force

RUN groupadd --gid 10001 suanagent \
    && useradd --uid 10001 --gid 10001 --create-home --shell /bin/sh suanagent

# pytest is a development tool for this repository; runtime dependencies remain
# empty in pyproject.toml by design.
RUN python -m pip install --no-cache-dir --disable-pip-version-check "pytest>=8,<10"

COPY . /workspace

RUN mkdir -p /workspace/experiments /workspace/workspaces /home/suanagent/.codex \
    && chown -R suanagent:suanagent /workspace /home/suanagent

USER suanagent

CMD ["python", "-m", "orchestrator.cli_connectivity", "--config", "config/cli_integrations.json", "--strict"]
