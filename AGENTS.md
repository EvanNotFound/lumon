# Repository Guide For Coding Agents

This repo is `nanobot-ai`: an async Python 3.11+ codebase with a small
TypeScript WhatsApp bridge in `bridge/`.

## Scope
- Main package: `nanobot/`
- Tests: `tests/`
- Packaging/config: `pyproject.toml`
- CI: `.github/workflows/ci.yml`
- Contributor guidance: `CONTRIBUTING.md`
- Workspace templates: `nanobot/templates/AGENTS.md`, `nanobot/templates/TOOLS.md`

## Rule Files Checked
- No repo-level `AGENTS.md` existed before this file.
- No `.cursorrules` file exists.
- No `.cursor/rules/` directory exists.
- No `.github/copilot-instructions.md` file exists.
- `nanobot/templates/AGENTS.md` is a generated-workspace template, not the repo guide.

## Tooling Snapshot
- Preferred Python workflow: `uv`
- CI Python versions: 3.11, 3.12, 3.13
- Build backend: `hatchling`
- Python lint/format: `ruff`
- Test runner: `pytest`
- Async test mode: `pytest-asyncio` with `asyncio_mode = auto`
- Bridge runtime: Node >= 20
- Bridge build: `tsc` with `strict: true`

## Setup
Preferred:
```bash
uv sync --all-extras
```

Fallback editable install:
```bash
pip install -e ".[dev]"
```

## Build, Lint, And Test Commands
Python:
```bash
uv run pytest tests/
uv run pytest tests/cli/test_commands.py::test_onboard_fresh_install
uv run pytest tests/ -k onboard
uv run pytest --cov=nanobot --cov-report=term-missing
uv run ruff check nanobot tests
uv run ruff format nanobot tests
uv build
```

Notes:
- CI runs `uv sync --all-extras` then `uv run pytest tests/`.
- `ruff` is the only configured Python linter/formatter.
- `uv build` is the easiest way to build the wheel/sdist from the Hatch backend.

Bridge commands from `bridge/`:
```bash
npm install
npm run build
npm run dev
npm start
```

## Single-Test Recipes
Exact test node:
```bash
uv run pytest tests/path/to/test_file.py::test_name
```

Examples:
```bash
uv run pytest tests/cli/test_commands.py::test_onboard_fresh_install
```

Name filtering:
```bash
uv run pytest tests/ -k restart
```

Useful flags:
```bash
uv run pytest tests/cli/test_commands.py::test_onboard_fresh_install -q
uv run pytest tests/cli/test_commands.py::test_onboard_fresh_install -vv
```

## High-Level Expectations
- Keep patches focused, readable, and low-risk.
- Prefer the smallest change that solves the real problem.
- Favor clear control flow over clever abstractions.
- Do not casually rename `nanobot`, `nanobot-ai`, or `~/.nanobot`.

## Python Formatting And Imports
- Use 4-space indentation.
- Respect Ruff's `line-length = 100`.
- Use double quotes consistently in Python.
- Let Ruff manage import ordering.
- Group imports as standard library, third-party, then local package imports.
- Use `TYPE_CHECKING` imports for typing-only or optional heavy imports.
- In optional-dependency modules, gate runtime imports with availability checks.

## Typing And Naming
- Target Python 3.11+ typing syntax.
- Prefer built-in generics like `list[str]`, `dict[str, Any]`, `set[str]`.
- Prefer PEP 604 unions like `str | None` over `Optional[str]`.
- Use `Literal[...]` for constrained string config values.
- Use `Any` sparingly at dynamic boundaries.
- Add explicit return types on public functions and async methods.
- Use `from __future__ import annotations` in larger or forward-ref-heavy modules when helpful.
- Modules/functions use `snake_case`; classes use `PascalCase`; constants use `UPPER_SNAKE_CASE`.
- Test files and functions start with `test_`.

## Pydantic And Config Patterns
- Config models usually subclass `Base` from `nanobot.config.schema`.
- That base accepts both camelCase and snake_case via alias generation.
- Prefer typed fields and explicit defaults.
- Use `Field(default_factory=...)` for mutable defaults.
- Keep config additions serializable through `model_dump(by_alias=True)`.
- Preserve config/path compatibility unless the task explicitly changes it.

## Async And Concurrency Patterns
- The codebase is async-first.
- Prefer `async def` for IO-heavy paths.
- Wrap blocking filesystem or client work with `asyncio.to_thread(...)`.
- Avoid blocking the main async loop.
- Keep async code cancellation-friendly.
- Async tests commonly use `@pytest.mark.asyncio`.

## Error Handling And Logging
- Use guard clauses for invalid config and unsupported states.
- For recoverable issues, log clearly and return safely.
- Raise only when the caller should actually handle the failure.
- Keep user-facing errors specific and actionable.
- Prefer Loguru placeholder style like `logger.warning("... {}", value)`.
- Avoid noisy stack traces for expected config problems.
- Preserve local-only and auth-sensitive behavior around the bridge and external services.

## Comments, Docstrings, And Tests
- Most modules start with a short module docstring; follow that pattern.
- Add docstrings to public classes and non-trivial functions.
- Keep comments for intent, invariants, or tricky edge cases.
- Avoid comments that merely restate the code.
- Tests use plain `pytest` asserts.
- CLI tests often use `typer.testing.CliRunner`.
- Prefer focused unit tests over oversized integration setups.
- Update tests when changing CLI behavior, config parsing, tools, providers, or channels.

## TypeScript Bridge Conventions
- Bridge code is ESM TypeScript with `strict` mode.
- Existing files use single quotes and semicolons.
- Prefer explicit `interface` and union types for message payloads.
- Keep localhost-only binding and token-based bridge security intact.
- No repo-local ESLint or Prettier config exists; match existing style and make `npm run build` pass.

## Security And Change Strategy
- Never hardcode secrets, tokens, or private endpoints into committed files.
- Be careful with auth headers, config files, and outbound network behavior.
- Read nearby code before editing; local conventions matter.
- Avoid broad rewrites unless the task explicitly asks for one.
- Update docs when commands, config shape, or user-visible workflows change.

## First Verification Steps After Changes
- Run the narrowest relevant pytest selection first.
- Run `uv run ruff check nanobot tests` after Python edits.
- Run `uv run ruff format nanobot tests` if formatting changed.
- Run `npm run build` in `bridge/` after TypeScript edits.
- Run `uv build` if packaging or install behavior changed.
