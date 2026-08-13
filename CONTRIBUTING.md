# Contributing

## Getting started

```sh
git clone https://github.com/omar-hindawi98/amxmodx-genai.git
cd amxmodx-genai
uv sync --dev
```

## Development workflow

```sh
uv run ruff check .          # lint
uv run ruff format --check . # format check
uv run ruff format .         # auto-format
uv run pytest                # unit + e2e (mocked agent, no API key needed)
```

### Live e2e tests

Run the full e2e suite against a real sidecar:

```sh
GENAI_SIDECAR_HOST=127.0.0.1 uv run pytest tests/e2e/
```

### Docker e2e

Run the full AMX e2e suite (compiles plugins, starts game server + sidecar):

```sh
docker compose up
```

Run live loop tests against Ollama:

```sh
docker compose --profile live up --abort-on-container-exit live_test
```

## Commits

This project follows [Conventional Commits](https://www.conventionalcommits.org). Your commit message must match the format:

```
<type>(<scope>): <description>

feat(sidecar): add streaming support
fix(core): handle queue full edge case
docs: update install steps
```

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

## Pull requests

- Keep PRs focused - one concern per PR
- For sidecar changes, make sure `ruff check` and `ruff format --check` pass
- For plugin changes, confirm the `.sma` compiles without warnings
- Fill in the PR template (What / Why / How to test)

## Project structure

```
plugins/
  amxmodx_genai/
    core.sma                 - AMXMODX core plugin (natives, TCP queue, poll loop)
    include/
      constants.inc          - Shared #define limits
      json.inc               - Minimal flat-JSON parser
      queue.inc              - Queue and tool/skill registry globals
      core_tools.inc         - Built-in tool definitions
      core_skills.inc        - Built-in skill registration
      skills/                - Bundled skill directories (e.g. amxmodx-reference)
  include/
    amxmodx_genai.inc        - Public native declarations for third-party plugins
src/amxmodx_genai/
  server.py                  - asyncio TCP listener entry point
  config.py                  - Pydantic settings (GENAI_* env vars)
  SYSTEM_PROMPT.md           - Immutable base agent persona
  core/
    handler.py               - Per-connection coroutine: agent loop, memory, framing
    memory.py                - SQLite two-tier memory (short-term turns + long-term summary)
    model.py                 - Model factory: Anthropic or Ollama
    protocol.py              - JSON framing helpers
    summarize.py             - Long-term memory summarization
    messages.py              - Message type definitions
  tools/
    plugin.py                - Dynamic tool factory for AMXMODX-registered tools
    native.py                - Built-in sidecar tools (e.g. current_datetime)
  skills/
    loader.py                - Loads AgentSkills from disk
tests/
  unit/                      - Pure Python tests (no API key, no sidecar)
  e2e/                       - TCP handler tests with mocked Strands Agent (no API key)
docker/                      - HLDS container config for plugin e2e tests
```
