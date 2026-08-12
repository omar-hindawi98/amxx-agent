# Contributing

## Getting started

```sh
git clone https://github.com/omar-hindawi98/amxmodx-genai.git
cd amxmodx-genai
cd sidecar && uv sync --dev
```

## Development workflow

```sh
cd sidecar
uv run ruff check .          # lint
uv run ruff format --check . # format check
uv run ruff format .         # auto-format
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
  genai_core.sma      - AMXMODX core plugin (registers natives, manages TCP queue)
  genai_example.sma   - Example plugin demonstrating the API
  include/
    genai.inc         - Public API header for plugin authors
sidecar/
  genai_sidecar.py    - Python TCP server bridging to the Anthropic API
  pyproject.toml      - uv project config and ruff settings
```
