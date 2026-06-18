---
title: Linter Guide
updated: 2026-03-29
category: guides
related_skills:
- python
related_docs:
- docs/patterns/linter_rules.md
- docs/guides/UV_GUIDE.md
---

# Linter Guide

SKUEL enforces code quality through three linting layers, all run via `uv run` underneath. The `./dev` script is the primary interface.

## Quick Start

```bash
./dev format        # Auto-format with Ruff
./dev lint          # Run Ruff + SKUEL pattern linter
./dev lint-fix      # Auto-fix Ruff issues
./dev quality       # Run ALL checks (format + Ruff + SKUEL + Cypher + MyPy)
./dev quality-fix   # Run all checks with auto-fix
```

**Never use `poetry run`.** SKUEL uses uv. See [UV Guide](UV_GUIDE.md).

## Three Linting Layers

| Layer | Tool | Scope | Config |
|-------|------|-------|--------|
| **Standard Python** | Ruff | 33 rule families (F, E, W, I, N, UP, B, SIM, RET, PERF, etc.) | `pyproject.toml` `[tool.ruff]` |
| **SKUEL Patterns** | `scripts/lint_skuel.py` | 19 architectural rules (SKUEL001-SKUEL019) | Inline in script |
| **Cypher Queries** | `scripts/cypher_linter.py` | 10 Neo4j query rules (CYP001-CYP010) | Inline in script |

Additional type checkers run during `./dev quality`:
- **MyPy** — static type checking (0 errors enforced)
- **Pyright** — additional strict type checking for VS Code

## How `./dev quality` Works

`./dev quality` calls `scripts/run_quality_checks.py`, which orchestrates nine checks in order:

1. **Ruff format check** — `uv run ruff format --check`
2. **Ruff lint** — `uv run ruff check`
3. **SKUEL pattern lint** — `uv run python scripts/lint_skuel.py`
4. **Cypher lint** — `uv run python scripts/cypher_linter.py --errors-only --strict`
5. **Route security audit** — `uv run python scripts/audit_route_security.py`
6. **Skills validation** — `uv run python scripts/skills_validator.py`
7. **Dead-code gate** — `uv run python scripts/detect_bloat.py --check` (PLANNED tier is the escape hatch)
8. **npm audit** — `npm audit --audit-level=moderate` (JS dependency vulnerabilities)
9. **Type checks** — MyPy + Pyright (optional, skip with `--fast`)

`./dev quality-fix` passes `--fix` to auto-fixable steps.

## Ruff Configuration

Configured in `pyproject.toml` under `[tool.ruff]`:

- **Target:** Python 3.12
- **Line length:** 100
- **All rules auto-fixable:** `fixable = ["ALL"]`
- **Per-file ignores:** Extensive config for tests, UI, routes, scripts (see `[tool.ruff.lint.per-file-ignores]`)

## SKUEL Pattern Rules (SKUEL001-SKUEL019)

These enforce SKUEL-specific architectural patterns that Ruff cannot catch.

### CRITICAL (blocks CI)

| Rule | Pattern | Description |
|------|---------|-------------|
| **SKUEL001** | APOC in services | Use CypherGenerator, not APOC in domain services |

### ERROR (blocks CI)

| Rule | Pattern | Description |
|------|---------|-------------|
| **SKUEL002** | Magic semantic strings | Use `SemanticRelationshipType` enum |
| **SKUEL003** | `.is_err` usage | Use `.is_error` instead [auto-fix] |
| **SKUEL019** | Catalog credential read via env | Use `get_credential()` — ERROR for catalog keys, WARNING for credential-shape names |

### WARNING

| Rule | Pattern | Description |
|------|---------|-------------|
| **SKUEL004** | Missing confidence threshold | Semantic queries need confidence filters |
| **SKUEL005** | Non-Result return types | Service methods should return `Result[T]` |
| **SKUEL007** | String `Result.fail()` | Use `Errors` factory |
| **SKUEL008** | Backend wrapper classes | Use `UniversalNeo4jBackend` directly |
| **SKUEL009** | Tuple defaults | Single-element tuple bug [auto-fix] |
| **SKUEL010** | Nested tuples | Neo4j can't store nested collections [auto-fix] |
| **SKUEL011** | `hasattr()` usage | Use Protocol/isinstance |
| **SKUEL012** | Lambda expressions | Use named functions |
| **SKUEL013** | RelationshipName strings | Use `RelationshipName` enum |
| **SKUEL014** | EntityType/NonKuDomain strings | Use `EntityType` or `NonKuDomain` enum |
| **SKUEL015** | Print in production code | Use `logger.*()` instead |
| **SKUEL016** | Stale Poetry references | SKUEL uses uv, not Poetry |
| **SKUEL017** | Bare `except Exception` | Use specific types from `exception_types.py` |
| **SKUEL018** | Direct read of `RichUserContext` rich-only fields | Use `get_X()` / `X_or_empty()` accessors |

### INFO

| Rule | Pattern | Description |
|------|---------|-------------|
| **SKUEL006** | TODO/FIXME tracking | Categorizes and tracks TODO/FIXME comments |

**Detailed examples and rationale:** See [Linter Rules](../patterns/linter_rules.md).

## Cypher Query Rules (CYP001-CYP010)

Static analysis for Neo4j Cypher queries embedded in Python code.

| Rule | Severity | Description |
|------|----------|-------------|
| **CYP001** | ERROR | Nested aggregate functions |
| **CYP002** | ERROR | DELETE without DETACH |
| **CYP003** | WARNING | String interpolation instead of parameters |
| **CYP004** | WARNING | Unbounded relationship traversal |
| **CYP005** | WARNING | Missing depth limit on multi-hop |
| **CYP006** | INFO | Large result set without LIMIT |
| **CYP007** | ERROR | Duplicate variable names (disabled) |
| **CYP008** | WARNING | WITH clause without DISTINCT (disabled) |
| **CYP009** | WARNING | Query complexity too high |
| **CYP010** | INFO | Missing index hint |

## Inline Suppression

When a rule needs to be suppressed for a legitimate reason:

```python
# Line-level
route_count = len(app.routes) if hasattr(app, "routes") else 0  # skuel-lint: disable=SKUEL011 -- FastHTML app attribute check

# File-level (top of file, before docstring)
# skuel-lint: disable-file=SKUEL005 -- Cache service, raw values not Result[T]
```

**Supported rules:** SKUEL005, SKUEL011, SKUEL012, SKUEL015, SKUEL017, SKUEL018, SKUEL019.

**SKUEL017 additional markers:**
```python
except Exception as e:  # intentional-broad: event handler must not propagate
except Exception as e:  # safety-net: catch unexpected errors at API boundary
```

Always include a reason after `--` to document why.

## SKUEL Linter CLI

```bash
# Basic usage
uv run python scripts/lint_skuel.py                    # Report violations
uv run python scripts/lint_skuel.py --fix              # Auto-fix (SKUEL003, SKUEL009, SKUEL010)
uv run python scripts/lint_skuel.py --check            # Exit 1 if violations (CI mode)

# Filtering
uv run python scripts/lint_skuel.py --file core/services/   # Lint specific path
uv run python scripts/lint_skuel.py --rule SKUEL011          # Run specific rule(s)

# Documentation
uv run python scripts/lint_skuel.py --explain SKUEL011  # Show rule documentation
uv run python scripts/lint_skuel.py --list-rules        # List all rules

# Output options
uv run python scripts/lint_skuel.py --context   # Show code around violations
uv run python scripts/lint_skuel.py --quiet     # Minimal output (CI)
uv run python scripts/lint_skuel.py --json      # Machine-readable output
uv run python scripts/lint_skuel.py --strict    # Treat warnings as errors
```

## Adding a New SKUEL Rule

1. **Choose a rule ID** — next available `SKUELXXX` number (last allocated: SKUEL019)
2. **Add a check method** in `scripts/lint_skuel.py` — follow the pattern of existing `_check_skuelXXX()` methods
3. **Register the rule** in the `RULE_DOCS` dict with severity, description, and good/bad examples (used by `--explain`)
4. **Wire it into `_lint_file`** with the correct context gate (e.g. `not is_test`, `is_service`)
5. **Add unit tests** in `tests/unit/scripts/test_lint_skuel.py`
6. **Document the rule** in `docs/patterns/linter_rules.md` with good/bad examples and rationale
7. **Update both lists in `CLAUDE.md`** — the "Key SKUEL Linter Rules" line *and* the supported inline-suppression list
8. **Update this guide** — both the WARNING/ERROR table and the "next available" hint above

## Unit Tests

Both custom linters have comprehensive test coverage:

- `tests/unit/scripts/test_lint_skuel.py` — 141 tests covering all 19 SKUEL rules
- `tests/unit/scripts/test_cypher_linter.py` — 35 tests covering Cypher rules

## Key Files

| File | Purpose |
|------|---------|
| `dev` | CLI wrapper — `./dev lint`, `./dev quality`, etc. |
| `pyproject.toml` | Ruff, MyPy, Pyright configuration |
| `scripts/lint_skuel.py` | SKUEL pattern linter (19 rules) |
| `scripts/cypher_linter.py` | Cypher query linter (10 rules) |
| `scripts/run_quality_checks.py` | Quality check orchestrator |
| `docs/patterns/linter_rules.md` | Detailed rule documentation |

---

**See:** [Linter Rules](../patterns/linter_rules.md) for detailed patterns and examples, [UV Guide](UV_GUIDE.md) for package manager commands
