# Contributing

## Getting started

```sh
git clone https://github.com/omar-hindawi98/amxx-agent.git
cd amxx-agent
uv sync --dev
```

## Development workflow

```sh
uv run ruff check .          # lint
uv run ruff format --check . # format check
uv run ruff format .         # auto-format
uv run pytest tests/unit     # unit tests (no API key, no network)
uv run pytest tests/         # unit + integration (Ollama-dependent tests auto-skip when Ollama is unreachable)
```

Integration tests use a real Ollama instance when reachable at `AGENT_MODEL_ENDPOINT`
(default `http://localhost:11434`). Tests marked with `@requires_ollama` are skipped
automatically when Ollama is not available, so no API key or network access is needed for
the rest of the suite.

### Live integration tests

Run the live sidecar tests against a real API key:

```sh
AGENT_MODEL_API_KEY=sk-ant-... uv run pytest tests/integration/test_live_sidecar.py
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
- For sidecar changes: `ruff check` and `ruff format --check` must pass
- For plugin changes: the `.sma` must compile without warnings (CI runs the compiler)
- For new example plugins: add the `.sma` under `examples/<name>/` - CI compiles all examples automatically
- Fill in the PR template (What / Why / How to test)

## Project structure

```
plugins/
  amxx_agent/
    core.sma                 - AMX Mod X core plugin (natives, TCP queue, poll loop)
    include/
      constants.inc          - Shared #define limits
      json.inc               - Minimal flat-JSON parser
      queue.inc              - Queue and tool/skill registry globals
      core_tools.inc         - Built-in tool definitions
      core_skills.inc        - Built-in skill registration
      skills/                - Bundled skill directories (e.g. amxmodx-reference)
  include/
    amxx_agent.inc        - Public native declarations for third-party plugins
examples/
  weapon_advisor/            - agent_register_skill + custom tool + per-player memory
    skills/                  - Skill directory shipped with this plugin
  admin_assistant/           - All main API functions: tools, skill, cancel, clear_longterm
    skills/                  - Skill directory shipped with this plugin
  testable/                  - All plugin API natives; observable for integration testing
    skills/                  - Skill directory shipped with this plugin
src/amxx_agent/
  server.py                  - asyncio TCP listener entry point
  config.py                  - Pydantic settings (AGENT_* env vars)
  logger.py                  - Logging configuration (level from AGENT_LOG_LEVEL)
  SYSTEM_PROMPT.md           - Immutable base agent persona
  core/
    handler.py               - Per-connection coroutine: agent loop, memory, framing
    memory.py                - SQLite two-tier memory (short-term turns + long-term summary)
    model.py                 - Model factory: multi-backend LLM provider (Bedrock, Ollama, LiteLLM, OpenAI-compatible)
    protocol.py              - JSON framing helpers
    summarize.py             - Long-term memory summarization
    messages.py              - Message type definitions
  tools/
    plugin.py                - Dynamic tool factory for AMX Mod X-registered tools
    native.py                - Built-in sidecar tools (e.g. current_datetime)
  skills/
    loader.py                - Loads AgentSkills from disk
tests/
  unit/                      - Pure Python unit tests (no API key, no network)
  integration/               - TCP handler + tool roundtrip tests; Ollama tests skip when unreachable
                               test_live_sidecar.py requires a real API key
                               test_example_testable.py exercises the testable/ example plugin
docker/                      - HLDS container config for plugin e2e tests
```
