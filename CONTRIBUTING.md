# Contributing to Lumon AI

Thank you for being here.

Lumon AI is built on top of nanobot, but this fork is maintained with a simpler goal: ship faster, keep history understandable, and make outside contribution less painful.

This guide explains how to contribute to the fork without breaking compatibility where the runtime still uses `nanobot` package, CLI, and path names.

## Branching Strategy

We use a single-branch workflow.

### Which Branch Should I Target?

Target `main` for all pull requests:

- New features or functionality
- Bug fixes
- Documentation improvements
- Refactoring
- Changes to APIs or configuration

### Quick Summary

| Your Change | Target Branch |
|-------------|---------------|
| New feature | `main` |
| Bug fix | `main` |
| Documentation | `main` |
| Refactoring | `main` |
| Unsure | `main` |

## Development Setup

Keep setup boring and reliable. The goal is to get you into the code quickly:

```bash
# Clone the repository
git clone https://github.com/EvanNotFound/lumon.git
cd lumon

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint code
ruff check nanobot/

# Format code
ruff format nanobot/
```

## Code Style

We care about more than passing lint. We want Lumon AI to stay small, calm, and readable.

When contributing, please aim for code that feels:

- Simple: prefer the smallest change that solves the real problem
- Clear: optimize for the next reader, not for cleverness
- Decoupled: keep boundaries clean and avoid unnecessary new abstractions
- Honest: do not hide complexity, but do not create extra complexity either
- Durable: choose solutions that are easy to maintain, test, and extend

In practice:

- Line length: 100 characters (`ruff`)
- Target: Python 3.11+
- Linting: `ruff` with rules E, F, I, N, W (E501 ignored)
- Async: uses `asyncio` throughout; pytest with `asyncio_mode = "auto"`
- Prefer readable code over magical code
- Prefer focused patches over broad rewrites
- If a new abstraction is introduced, it should clearly reduce complexity rather than move it around
- Keep operational identifiers such as `nanobot`, `nanobot-ai`, and `~/.nanobot` intact unless the task explicitly changes them

## Questions?

If you have questions, ideas, or half-formed insights, you are warmly welcome here.

Please open an issue or pull request in this repository:

- Issues: https://github.com/EvanNotFound/lumon/issues
- Pull requests: https://github.com/EvanNotFound/lumon/pulls

Thank you for spending your time and care on Lumon AI. Contributions of all sizes are welcome.
