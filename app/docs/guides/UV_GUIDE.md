---
title: UV Package Manager Guide
updated: 2026-03-29
category: guides
related_skills:
- python
related_docs:
- docs/design-principles/ONE_PATH_FORWARD.md
- docs/development/DEVELOPMENT_SETUP.md
- docs/guides/LINTER_GUIDE.md
---

# UV Package Manager Guide

SKUEL uses [uv](https://docs.astral.sh/uv/) for Python package management. Poetry was fully replaced per [One Path Forward](../design-principles/ONE_PATH_FORWARD.md) — there is no alternative path.

## Key Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Package metadata, dependencies, tool config (PEP 621 `[project]` format) |
| `uv.lock` | Locked dependency versions for reproducible builds |
| `.python-version` | Python version pin |

Dependencies are declared in `pyproject.toml` under `[project.dependencies]`. Dev dependencies use `[dependency-groups]`:

```toml
[project]
dependencies = ["fasthtml>=0.12.0", "neo4j>=5.0", ...]

[dependency-groups]
dev = ["pytest>=8.0", "mypy>=1.0", "ruff>=0.8", ...]
```

Build system is hatchling (`[build-system]` section).

## Common Commands

| Command | Purpose |
|---------|---------|
| `uv sync` | Install all dependencies (dev + production) from lock file |
| `uv sync --no-dev` | Install production dependencies only |
| `uv run <command>` | Run a command in the project's virtual environment |
| `uv add <package>` | Add a dependency and update lock file |
| `uv add --dev <package>` | Add a dev dependency |
| `uv remove <package>` | Remove a dependency |
| `uv lock` | Regenerate lock file without installing |
| `uv pip list` | List installed packages |

## The `./dev` Script

The `./dev` script is the primary interface for development commands. Every command runs `uv run` underneath:

| `./dev` Command | Underlying `uv run` Command |
|-----------------|----------------------------|
| `./dev serve` | `uv run python main.py` |
| `./dev format` | `uv run ruff format` |
| `./dev lint` | `uv run ruff check` + `uv run python scripts/lint_skuel.py --strict` |
| `./dev lint-fix` | `uv run ruff check --fix` |
| `./dev quality` | `uv run python scripts/run_quality_checks.py` |
| `./dev test` | `uv run python scripts/run_tests.py comprehensive` |
| `./dev test-quick` | `uv run python scripts/run_tests.py quick` |
| `./dev health` | `uv run python scripts/health/dead_modules.py` + 3 more |

**Prefer `./dev` commands** — they handle error formatting and provide consistent output. Use raw `uv run` when you need options the wrapper doesn't expose.

See [Linter Guide](LINTER_GUIDE.md) for the full linting command reference.

## Docker Integration

Both Dockerfiles use the official uv image for fast installs:

```dockerfile
# Copy uv binary from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Production: install without dev dependencies
RUN uv sync --no-dev --no-root

# Development: install everything
RUN uv sync
```

The `.venv` is created inside the container. No system-wide Python packages.

## CI Integration

GitHub Actions use the official uv setup action:

```yaml
- uses: astral-sh/setup-uv@v6
  with:
    enable-cache: true
    cache-dependency-glob: "app/uv.lock"

- run: uv sync --frozen
  working-directory: app

- run: uv run pytest
  working-directory: app
```

Cache key is based on `uv.lock` for reproducible CI builds.

**`--frozen` in CI is not optional.** A bare `uv sync` locks before syncing, so a
`uv.lock` that has fallen behind `pyproject.toml` is silently re-resolved and
rewritten in the runner workspace — CI then measures a resolution nobody
reviewed. `--frozen` installs the committed lock as-is. (`--locked` also refuses
to rewrite, but *fails* the install step; pick it only where that failure is the
signal you want. `ci.yml` uses `--frozen` everywhere and lets the dependency
audit's `uv export --locked` be the one staleness detector.) The Docker build
uses `--frozen` for the same reason — see `.claude/skills/docker/SKILL.md`.

## Enforcement: SKUEL016

The SKUEL linter rule **SKUEL016** catches stale Poetry references anywhere in the codebase:

| Caught Pattern | Replacement |
|---------------|-------------|
| `poetry install` | `uv sync` |
| `poetry add` | `uv add` |
| `poetry run` | `uv run` |
| `poetry.lock` | `uv.lock` |
| `poetry remove` | `uv remove` |

This is One Path Forward in action — automated enforcement ensures no parallel path survives.

## Why uv

uv replaced Poetry as part of SKUEL's [Leverage Maintained Software](../design-principles/LEVERAGE_MAINTAINED_SOFTWARE.md) principle:

- **Fast:** 10-100x faster than Poetry for installs and resolution
- **Standards-compliant:** PEP 621 `[project]` format (not Poetry's custom `[tool.poetry]`)
- **Maintained:** Active development by Astral (also maintains Ruff)
- **Simple:** Single binary, no plugin system, deterministic lock file

---

**See:** [One Path Forward](../design-principles/ONE_PATH_FORWARD.md), [Development Setup](../development/DEVELOPMENT_SETUP.md), [Linter Guide](LINTER_GUIDE.md)
