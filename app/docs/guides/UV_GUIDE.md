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
| `./dev health` | `uv run python scripts/health/dead_modules.py` and the other health scripts |

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

### Freezing the lock in CI

**A bare `uv sync` locks before syncing.** If `uv.lock` has fallen behind
`pyproject.toml`, uv silently re-resolves and rewrites it in the runner
workspace — CI then measures a resolution nobody reviewed.

**`uv run` does the same thing.** This is the part that's easy to miss: pinning
only the install step leaves the hole open one step later, because `uv run`
locks and syncs before it runs your command. `uv run --frozen` is "Run without
updating the `uv.lock` file."

So `ci.yml` sets **`UV_FROZEN: "1"` at the job level** rather than flagging each
invocation — one setting covers `sync`, `run`, and any uv command a future step
adds. A hand-maintained list of flags goes stale the first time someone adds a
step.

**The one exception: `UV_FROZEN` conflicts with an explicit `--locked`.**

```
error: the argument `--locked` cannot be used with `UV_FROZEN` (environment variable)
```

uv exits 2 — it is a hard conflict, not a precedence rule.

**And the quieter trap: `UV_FROZEN` silently downgrades `uv lock --check`.** No
conflict, no error — uv reports the lockfile was "only checked for validity,
not whether it is up-to-date" and exits 0 (measured, uv 0.10.9). A freshness
gate under that env var passes vacuously. This is why the `dep_audit` CI job
deliberately does *not* set `UV_FROZEN`: `scripts/audit_dependencies.sh` uses
`uv lock --check` as the single staleness detector guarding the CVE gate, and
the script itself refuses to run if `UV_FROZEN`/`UV_LOCKED` is set.

Rule of thumb: **`--frozen` installs the committed lock as-is; `--locked`
asserts the lock is already current and *fails* if it isn't.** Reach for
`--locked` only where that failure is the signal you want. The Docker build uses
`--frozen` for the same reason — see `.claude/skills/docker/SKILL.md`.

**This is enforced, not remembered.** `tests/unit/test_workflow_uv_lock_pinning.py`
parses every job in `../.github/workflows/` and fails on any of four shapes: a
uv-using job with no `UV_FROZEN`; a `--locked` job that sets it anyway (exit 2);
a `--locked` job whose own uv commands lack `--frozen` (the original defect); and
`UV_FROZEN` left on a job that no longer runs uv. It keys on **whether the job
passes `--locked`**, not on job names, and follows the shell scripts a job runs —
so both `--locked` jobs are recognised through `audit_dependencies.sh` and the
guard survives that script being renamed or replaced.

Two things follow from that, if you are editing a workflow:

- **`UV_FROZEN` belongs in the job's `env:` block and nowhere else.** A step-level
  `env:`, a command prefix (`UV_FROZEN=0 uv sync`), an `export`, or a write to
  `$GITHUB_ENV` all override it in a scope the job cannot see, and all four are
  rejected. uv reads the **value**, so `UV_FROZEN=0` disables the pin — it is not
  merely redundant.
- **uv must be plainly visible.** The guard parses bash properly
  (`tree-sitter-bash`) but refuses what parsing cannot settle: uv behind a wrapper
  whose options it cannot skip, a `--locked` it cannot attribute to uv rather than
  to the child (`uv run --with requests --locked …` — write `--opt=value`), a
  script that does not resolve, and any command verb it does not recognise. If it
  refuses your step, the message names the shape and the fix.

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
