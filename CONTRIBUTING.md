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
uv run pytest                # unit + integration (mocked agent, no API key needed)
```

### Live integration tests

Run the live sidecar tests against a real API key:

```sh
GENAI_MODEL_API_KEY=sk-ant-... uv run pytest tests/integration/test_live_sidecar.py
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
    core.sma                 - AMX Mod X core plugin (natives, TCP queue, poll loop)
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
  logger.py                  - Logging configuration (level from GENAI_LOG_LEVEL)
  SYSTEM_PROMPT.md           - Immutable base agent persona
  core/
    handler.py               - Per-connection coroutine: agent loop, memory, framing
    memory.py                - SQLite two-tier memory (short-term turns + long-term summary)
    model.py                 - Model factory: Anthropic, Bedrock, Ollama, LiteLLM, OpenAI
    protocol.py              - JSON framing helpers
    summarize.py             - Long-term memory summarization
    messages.py              - Message type definitions
  tools/
    plugin.py                - Dynamic tool factory for AMX Mod X-registered tools
    native.py                - Built-in sidecar tools (e.g. current_datetime)
  skills/
    loader.py                - Loads AgentSkills from disk
tests/
  unit/                      - Pure Python unit tests (no API key, no sidecar)
  integration/               - TCP handler tests with mocked Strands Agent (no API key)
                               test_live_sidecar.py requires a real API key
docker/                      - HLDS container config for plugin e2e tests
```
