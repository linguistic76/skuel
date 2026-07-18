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
| **SKUEL Patterns** | `scripts/lint_skuel.py` | 28 architectural rules (SKUEL001-SKUEL029; SKUEL004 deleted, IDs not renumbered) | Inline in script |
| **Cypher Queries** | `scripts/cypher_linter.py` | 10 Neo4j query rules (CYP001-CYP010) | Inline in script |

Additional type checkers run during `./dev quality`:
- **MyPy** — static type checking (0 errors enforced)
- **Pyright** — additional strict type checking for VS Code

## How `./dev quality` Works

`./dev quality` calls `scripts/run_quality_checks.py`, which orchestrates eleven checks in order:

1. **Ruff format check** — `uv run ruff format --check`
2. **Ruff lint** — `uv run ruff check`
3. **SKUEL pattern lint** — `uv run python scripts/lint_skuel.py --strict` (warnings block — the tier is at zero)
4. **Cypher lint** — `uv run python scripts/cypher_linter.py --errors-only --strict`
5. **Route security audit** — `uv run python scripts/audit_route_security.py`
6. **Raw headers audit** — `uv run python scripts/audit_raw_headers.py` (advisory: H1/H2 outside approved files; `Html(Head())` outside `base_page.py` is blocking)
7. **Skills validation** — `uv run python scripts/skills_validator.py`
8. **Content-boundary guard** — `uv run python scripts/audit_content_boundary.py` (no proprietary vault content tracked in this PUBLIC repo; also enforced by `tests/unit/test_content_boundary.py` on the CI gate)
9. **Dead-code gate** — `uv run python scripts/detect_bloat.py --check` (PLANNED tier is the escape hatch)
10. **npm audit** — `npm audit --audit-level=moderate` (JS dependency vulnerabilities)
11. **Type checks** — MyPy + Pyright (optional, skip with `--fast`)

`./dev quality-fix` passes `--fix` to auto-fixable steps.

## Ruff Configuration

Configured in `pyproject.toml` under `[tool.ruff]`:

- **Target:** Python 3.12
- **Line length:** 100
- **All rules auto-fixable:** `fixable = ["ALL"]`
- **Per-file ignores:** Extensive config for tests, UI, routes, scripts (see `[tool.ruff.lint.per-file-ignores]`)

## SKUEL Pattern Rules (SKUEL001-SKUEL029)

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
| **SKUEL020** | `request: Any` on `@rt` handlers | Annotate `request: Request` (AST rule) |
| **SKUEL021** | Raw Cypher in `core/` | Relocate below the boundary (ADR-044) |
| **SKUEL022** | `adapters/` imports in `core/` | Depend on a `core/ports` protocol (ADR-044) |
| **SKUEL023** | `self.backend` typed against adapter class in `core/` | Type against the `core/ports` protocol (ADR-044) |
| **SKUEL024** | `cls=` + `**kwargs` collision in FT helpers | Add explicit `cls: str = ""` and merge |
| **SKUEL025** | Deleted Activity `*UpdatePayload` names | Use `*UpdateIntent` / `*UpdateRequest.to_intent()` (ADR-066) |
| **SKUEL027** | Runtime `adapters/` imports in `ui/` | Move shared code inward or pass values in from the route (SKUEL022's ui/ sibling) |
| **SKUEL028** | `Result.fail(...expect_error())` | Propagate with `Result.fail(result)`; `.expect_error()` is for reading only |
| **SKUEL029** | `async def` without `await` | Sync body in async signature — convert to `def`, or suppress where a protocol/lifecycle contract requires async (promoted from opt-in 2026-07-18 after the 215→0 reduction arc) |

### WARNING

Warnings fail the gate commands (`./dev lint` / `./dev quality` pass `--strict`)
now that the tier is at zero codebase-wide; a plain `lint_skuel.py` run reports
them without failing.

| Rule | Pattern | Description |
|------|---------|-------------|
| **SKUEL005** | Non-Result return types | Async service methods return `Result[T]` (AST — catches multi-line signatures) |
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
| **SKUEL017** | Bare `except Exception` | Use specific types from `exception_types.py` (AST — catches wrapped clauses) |
| **SKUEL018** | Direct read of `RichUserContext` rich-only fields | Use `get_X()` / `X_or_empty()` accessors |
| **SKUEL026** | Suppression comment that suppresses nothing | Delete the rotted comment (per-run audit; see linter_rules.md) |

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
| **CYP003** | ERROR | Interpolated VALUE instead of parameter (`'{var}'`, `= {var}`, `IN {var}`) |
| **CYP004** | WARNING | Unbounded relationship traversal |
| **CYP005** | WARNING | Missing depth limit on multi-hop |
| **CYP006** | INFO | Large result set without LIMIT |
| **CYP007** | ERROR | Duplicate variable names (disabled) |
| **CYP008** | WARNING | WITH clause without DISTINCT (disabled) |
| **CYP009** | WARNING | Query complexity too high |
| **CYP010** | INFO | Missing index hint |

**CYP003 (promoted WARNING → ERROR 2026-07, now CI-gated):** flags only
value-position interpolation — quoted literals (`'{var}'`, including map values
like `{{uid: '{source_uid}'}}`) and operator operands (`= {var}`, `<= {depth}`,
`IN {var}`). Structural composition stays legal: clause fragments
(`{where_clause}`), validated identifiers (`(n:{label})`, `[r:{rel_type}]` —
labels/reltypes cannot be driver parameters), and variable-length bounds
(`*1..{depth}`, likewise unparameterizable). The pre-promotion rule flagged all
structural composition (157 false positives) while missing quoted map values.
Suppress a boundary-shaped hit with a Cypher comment on the flagged line:
`// noqa: CYP003 - <reason>` (`// noqa: CYP002 - <reason>` works the same way).

**Discovery scope:** `core/services/`, `adapters/persistence/neo4j/`,
`scripts/` (added 2026-07 — migrations and maintenance scripts run raw Cypher
directly), and `tests/integration/`. Queries are extracted from triple-quoted
strings that pass the `_is_actual_cypher` heuristic; single-line f-string
concatenation (`cypher += f"..."`) is below its resolution — parameterize those
by convention.

## Inline Suppression

When a rule needs to be suppressed for a legitimate reason:

```python
# Line-level
route_count = len(app.routes) if hasattr(app, "routes") else 0  # skuel-lint: disable=SKUEL011 -- FastHTML app attribute check

# File-level (top of file, before docstring)
# skuel-lint: disable-file=SKUEL005 -- Cache service, raw values not Result[T]
```

**Supported rules:** SKUEL005, SKUEL011–SKUEL015, SKUEL017–SKUEL025, SKUEL027–SKUEL029 (the `SUPPRESSIBLE_RULES` set in `lint_skuel.py`). Every run audits suppressions and flags unused ones as SKUEL026.

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
| `scripts/lint_skuel.py` | SKUEL pattern linter (25 rules; SKUEL004 deleted 2026-07, IDs not renumbered) |
| `scripts/cypher_linter.py` | Cypher query linter (10 rules) |
| `scripts/run_quality_checks.py` | Quality check orchestrator |
| `docs/patterns/linter_rules.md` | Detailed rule documentation |

---

**See:** [Linter Rules](../patterns/linter_rules.md) for detailed patterns and examples, [UV Guide](UV_GUIDE.md) for package manager commands
