---
title: Linter Guide
updated: 2026-08-30
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
| **SKUEL Patterns** | `scripts/lint_skuel.py` | 33 architectural rules (SKUEL001–SKUEL034; SKUEL004 deleted, IDs not renumbered) | Inline in script |
| **Cypher Queries** | `scripts/cypher_linter.py` | Neo4j query rules CYP001–CYP012 (CYP007/CYP008/CYP010 disabled — see the script docstring) | Inline in script |

Additional type checkers run during `./dev quality`:
- **MyPy** — static type checking (0 errors enforced)
- **Pyright** — additional strict type checking for VS Code

## How `./dev quality` Works

`./dev quality` calls `scripts/run_quality_checks.py`, which orchestrates the following checks in order (the script is the source of truth for the exact set — `tests/unit/scripts/test_quality_ci_parity.py` pins it against CI):

1. **Ruff format check** — `uv run ruff format --check`
2. **Ruff lint** — `uv run ruff check`
3. **SKUEL pattern lint** — `uv run python scripts/lint_skuel.py --strict` (warnings block — the tier is at zero)
4. **Cypher lint** — `uv run python scripts/cypher_linter.py --errors-only --strict`
5. **Route security audit** — `uv run python scripts/audit_route_security.py`
6. **Raw headers audit** — `uv run python scripts/audit_raw_headers.py` (advisory: H1/H2 outside approved files; `Html(Head())` outside `base_page.py` is blocking)
7. **Skills validation** — `uv run python scripts/skills_validator.py`
8. **Content-boundary guard** — `uv run python scripts/audit_content_boundary.py` (no proprietary vault content tracked in this PUBLIC repo; also enforced by `tests/unit/test_content_boundary.py` on the CI gate)
9. **Dead-code gate** — `uv run python scripts/detect_bloat.py --check` (PLANNED tier is the escape hatch)
10. **Dependency CVE audit** — `bash scripts/audit_dependencies.sh` (osv-scanner over `uv.lock` + `package-lock.json`, all severities; accepted findings in `osv-scanner.toml` — ADR-067 § 6e)
11. **ShellCheck** — `uv run python scripts/shellcheck_tracked.py` (tracked `*.sh` + shebang-detected scripts; discovery shared with the CI lint job)
12. **Type checks** — MyPy + Pyright (optional, skip with `--fast`)

`./dev quality-fix` passes `--fix` to auto-fixable steps.

## Ruff Configuration

Configured in `pyproject.toml` under `[tool.ruff]`:

- **Target:** latest stable CPython (`target-version` in `pyproject.toml`, currently `py314` — tracks `.python-version` per ADR-067)
- **Line length:** 100
- **All rules auto-fixable:** `fixable = ["ALL"]`
- **Per-file ignores:** Extensive config for tests, UI, routes, scripts (see `[tool.ruff.lint.per-file-ignores]`)

## SKUEL Pattern Rules (SKUEL001–SKUEL034)

These enforce SKUEL-specific architectural patterns that Ruff cannot catch.

### CRITICAL (blocks CI)

| Rule | Pattern | Description |
|------|---------|-------------|
| **SKUEL001** | APOC in services | Move the query onto the domain backend and call a named backend method — services author neither APOC nor Cypher |

### ERROR (blocks CI)

| Rule | Pattern | Description |
|------|---------|-------------|
| **SKUEL002** | Magic semantic strings | Use `SemanticRelationshipType` enum |
| **SKUEL003** | `.is_err` usage | Use `.is_error` instead [auto-fix] |
| **SKUEL019** | Catalog credential read via env | Use `get_credential()` — ERROR for catalog keys, WARNING for credential-shape names |
| **SKUEL020** | `request: Any` on `@rt` handlers | Annotate `request: Request` (AST rule) |
| **SKUEL021** | Raw Cypher in `core/` | Relocate below the boundary (ADR-044) |
| **SKUEL022** | `adapters/` imports in `core/` | Depend on a `core/ports` protocol (ADR-044) |
| **SKUEL023** | a `core/` class's `backend` — assigned, only declared, or merely inherited from a `Base*[Any, ...]` / bare `Base*` parameterisation — typed against an adapter class, `Any`, or nothing at all | Type against the `core/ports` protocol (ADR-044). For the inherited form, parameterise the base — annotating `__init__` does not narrow it |
| **SKUEL024** | `cls=` + `**kwargs` collision in FT helpers | Add explicit `cls: str = ""` and merge |
| **SKUEL025** | Deleted Activity `*UpdatePayload` names | Use `*UpdateIntent` / `*UpdateRequest.to_intent()` (ADR-066) |
| **SKUEL027** | Runtime `adapters/` imports in `ui/` | Move shared code inward or pass values in from the route (SKUEL022's ui/ sibling) |
| **SKUEL032** | Runtime `ui/` imports in `core/` | Return a `core/ports/query_types` row; build the display type in `ui/` (ADR-058; SKUEL022's presentation-side twin) |
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
| **SKUEL030** | Unregistered label / edge name in `adapters/persistence/` Cypher | Must be a `NeoLabel` / `RelationshipName` member — Neo4j matches zero rows silently on an unknown name (`.cypher` half is CYP011) |
| **SKUEL031** | Stale pip references | uv is the one path (`uv add` / `uv sync`) — SKUEL016's pip sibling |
| **SKUEL033** | Cypher-shaped docstrings in `core/services`, `core/orchestrator`, `core/ports`, `core/models` | State intent + the guarantee; the query belongs in the backend docstring (see SERVICE_DOCSTRING_STYLE.md) |
| **SKUEL034** | Substring test against a *singular* uid (`"tech" in knowledge_uid.lower()`) | Read the field that carries the fact — `entity_type`, the label, `sel_category`, or the edge (ADR-013 never-sniff; bare collections / `startswith` / `split` out of scope, but `str(uids)`-style serialization is flagged) |

### INFO

| Rule | Pattern | Description |
|------|---------|-------------|
| **SKUEL006** | TODO/FIXME tracking | Categorizes and tracks TODO/FIXME comments |

**Detailed examples and rationale:** See [Linter Rules](../patterns/linter_rules.md).

## Cypher Query Rules (CYP001-CYP012)

Static analysis for Neo4j Cypher queries — both embedded in Python string
literals and in standalone `.cypher` files.

| Rule | Severity | Description |
|------|----------|-------------|
| **CYP001** | ERROR | Nested aggregate functions |
| **CYP002** | ERROR | DELETE without DETACH on a **node** |
| **CYP003** | ERROR | Interpolated VALUE instead of parameter (`'{var}'`, `= {var}`, `IN {var}`) |
| **CYP004** | WARNING | Unbounded relationship traversal |
| **CYP005** | WARNING | Missing depth limit on multi-hop |
| **CYP006** | INFO | Large result set without LIMIT |
| **CYP007** | ERROR | Duplicate variable names (disabled) |
| **CYP008** | WARNING | WITH clause without DISTINCT (disabled) |
| **CYP009** | WARNING | Query complexity too high |
| **CYP010** | INFO | Missing index hint |
| **CYP011** | ERROR | Label / relationship type not registered in `NeoLabel` / `RelationshipName` (`.cypher` files only; the `.py` half is SKUEL030) |
| **CYP012** | WARNING | DETACH on a **relationship** delete — a no-op |

**CYP002 and CYP012 are the two directions of one question**, over one shared
classifier (`_relationship_vars`, the set of variables a pattern binds to an
edge). CYP002 asks whether a DETACH is *missing* and therefore skips edge
deletes entirely; CYP012 asks whether a DETACH can do *anything* and therefore
looks only at them. That asymmetry is why four sites emitted `DETACH DELETE r`
on an edge unreported for as long as CYP002 shipped alone — the mechanism to
classify the variable was already there, the second question was simply never
asked. A relationship has no relationships to detach, so `DETACH DELETE r` and
`DELETE r` leave identical graphs (verified against a live server, not read off
the docs). CYP012 fires only when **every** target is an edge: `DETACH DELETE r, n`
is correct and is not flagged, because the DETACH is there for `n`. A target also
bound as a **node** anywhere in the query, or rebound by an `AS` alias, is skipped.

**Only CYP012 reads those subtractions, and that asymmetry is deliberate.** The
node/alias classifiers are lexical and query-wide, so they are sometimes wrong.
Every way they can be wrong makes CYP012 *quieter*, which is free — it only ever
removes a redundant keyword. Pointing the same subtractions at CYP002 makes them
point the other way, and #868 measured the result: `count (r)` — valid Cypher,
whitespace before the paren — reads as a node pattern, drops `r` from the edge
set, and makes an **ERROR-severity, CI-gating rule fail a correct relationship
deletion**. CYP002 therefore keeps the raw classifier. A gate must not fail closed
because a regex was wrong.

**Known limits of CYP012 (all misses, never false alarms):** a name reused across
scopes (`CALL { MATCH ()-[r:OWNS]->() DELETE r } MATCH (r:Entity) DETACH DELETE r`);
a whitespace-separated aggregate (`count (r)`), where telling a function name from
a clause keyword is a parser's job; and any name a `WITH … AS r` rebinds. Four
review rounds landed on this surface in #868. That progression is a regex growing
toward a parser — a tail this repo already paid 19 rounds for once (#831) — so the
mechanism stopped and the rule's *claim* narrowed instead: **CYP012 speaks only
when a name is bound by a relationship pattern, never by a node pattern, and never
by an alias.**

**Known limit of CYP002 (pre-existing, left as found):** the same cross-scope
reuse makes CYP002 *skip* a node delete that genuinely needs DETACH. This predates
#868; a round of that PR "fixed" it via the subtractions above and had to be
reverted when the fix proved worse than the bug. Closing it properly needs scope
resolution. Both limits are asserted by tests, so a real fix will announce itself
by turning those assertions red.

**Coverage boundary (closed 2026-07-29):** CYP012 once guarded **three** of the
four sites repaired when it was added. `relationship_builders.py` (the adapter-level
fluent builder, **deleted 2026-08-20**) interpolated
every structural position (`(from {from_pattern})`, `-[r:{self._relationship_type}]`),
so the extractor's local heuristic saw no node pattern, rel pattern, property map
or `$param` and never yielded the query at all — a blind spot upstream of *every*
CYP rule, not CYP012's. Measured tree-wide, **113 queries** were rejected on that
basis while leading with a Cypher clause. The heuristic was replaced by the shared
`looks_like_cypher` gate (see *Discovery scope*), and the test that pinned the gap
now pins the query travelling extractor-to-rule end to end.

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
directly), and `tests/integration/` — both `**/*.py` and `**/*.cypher` in each
tree (`find_lintable_files`). In Python files, queries are extracted from
triple-quoted strings, admitted by **`cypher_vocabulary.looks_like_cypher`** —
the same three-anchor gate SKUEL030 applies to the same kind of text. Two
conditions travel with that gate:

- **Docstrings are skipped**, by AST position. This is a stated precondition of
  the gate's head anchor, not a nicety: SKUEL033's intent-only docstrings open
  with the clause the method performs ("MERGE VIEWED relationship with timestamp
  and count tracking"), so the anchor reads them as Cypher. 19 such docstrings
  were admitted without the exemption, and one made CYP002 — ERROR severity,
  CI-gating — report a node named `the`.
- **Cypher comments are masked** before the rules run, the same treatment the
  `.cypher` path has had since #710. Prose in a comment is not Cypher: `// The
  stale-owner DELETE enforces the single-owner invariant` made CYP002 report a
  node named `enforces` inside a query that is entirely correct.
- **Python `#` comments are masked too**, via `tokenize`, so commented-out code
  is never read as a live query. On `main` this hole was open and gating:
  `# query = """MATCH (n:Entity) DELETE n"""` produced a CI-blocking CYP002 on a
  line Python never executes. `tokenize` rather than a `#`-matching regex,
  because a `#` inside a string literal is not a comment.

The gate replaced a local heuristic (`_is_actual_cypher`) that scored raw text for
four structural shapes and so was blind to fully-interpolated queries. Deleting it
cost nothing measurable: the shared gate admits 1047 of the 1049 literals it
admitted, and the 2 it declines are prose docstrings.

**Known cost of the head anchor:** prose that opens with an uppercase clause and an
operand (`MATCH the user to the correct task`, `prompt = """DELETE the paragraph."""`)
is admitted outside a docstring, and CYP002 will report an ERROR on it. That is the
anchor working as designed — it is what admits `RETURN 1 as ping` and `SHOW INDEXES`,
statement families with no paren to anchor on — and the docstring exemption is what
keeps it tolerable.

This is not a `cypher_linter` quirk: **SKUEL021 runs the same anchor at the same
ERROR severity over `core/services` and flags that exact prose today.** Re-filtering
it in the extractor would fork the anchor's semantics between two rules that are
meant to agree. If the trade needs revisiting, the place is a fourth condition on the
shared anchor in `cypher_vocabulary` — one change, both rules — never a second prose
heuristic in `cypher_linter.py`. A test pins the current behaviour so a future
tightening announces itself.

Single-line
f-string concatenation (`cypher += f"..."`) is below its resolution —
parameterize those by convention.

**Standalone `.cypher` files (PR #710, 2026-07):** indexes, migrations, and
bulk-upsert templates are Cypher by declaration — no heuristics. The file is
split into semicolon-terminated statements and each statement is linted as its
own query (so a `LIMIT` in one audit query can't exempt another, and CYP009
complexity isn't summed across a whole migration). Comments — `//` line and
`/* */` block — are masked before rules run, so comment prose ("DELETE the
stale edges") can't trip prose-shaped rules and a `;` or quote inside a
comment never splits a statement. Masking started here and now applies to both
source shapes; only the statement splitting is specific to this one. The one
exception to masking: `noqa:`-carrying `//`
comments are kept, and the natural placement works —
`DELETE n; // noqa: CYP002 - reason` suppresses the statement its semicolon
closes. Block comments are always masked, so noqa must be `//`-style.

**Scanner diagnostics:** `scripts/cypher_scan_diagnostics.py` replays SKUEL030's
and CYP011's real scan paths with recording switched on and reports every span
the shared vocabulary scanner admitted but could not read (dropped items,
unreadable pattern bodies, truncated mutation regions). A diagnostic, not a rule
— not wired into `./dev quality`, and most drops are correct; it exists so a
reviewer measures the scanner's blind spots instead of imagining them (#831's
19-round tail). See its module docstring for usage.

## Inline Suppression

When a rule needs to be suppressed for a legitimate reason:

```python
# Line-level
route_count = len(app.routes) if hasattr(app, "routes") else 0  # skuel-lint: disable=SKUEL011 -- FastHTML app attribute check

# File-level (top of file, before docstring)
# skuel-lint: disable-file=SKUEL005 -- Cache service, raw values not Result[T]
```

**Supported rules:** SKUEL005, SKUEL011–SKUEL015, SKUEL017–SKUEL025, SKUEL027–SKUEL030, SKUEL032 (the `SUPPRESSIBLE_RULES` set in `lint_skuel.py`, drift-guarded by `TestSuppressibleRulesDrift`). Every run audits suppressions and flags unused ones as SKUEL026.

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

1. **Choose a rule ID** — next available `SKUELXXX` number (last allocated: **SKUEL034**; SKUEL004 was deleted 2026-07 and must NOT be reused)
2. **Add a check method** in `scripts/lint_skuel.py` — follow the pattern of existing `_check_skuelXXX()` methods
3. **Register the rule** in the `RULE_DOCS` dict with severity, description, and good/bad examples (used by `--explain`)
4. **Wire it into `_lint_file`** with the correct context gate (e.g. `not is_test`, `is_service`), AND add the id to `AST_RULE_IDS` if the rule reads the shared tree — omitting it leaves `tree` as `None`, so `--rule SKUELXXX` silently reports zero while a full sweep works
5. **Add unit tests** in `tests/unit/scripts/test_lint_skuel.py` — and mirror the `_lint_file` gate in that file's `lint_content()` harness, or every new test passes vacuously. Suppressible rules must also be added to `SUPPRESSIBLE_RULES` (`TestSuppressibleRulesDrift` enforces it by scanning for a **quoted literal** rule id at the suppression call site — which is why the three import-direction checkers are separate functions over one shared scan)
6. **Document the rule** in `docs/patterns/linter_rules.md` with good/bad examples and rationale
7. **Update both lists in `CLAUDE.md`** — the "Key SKUEL Linter Rules" line *and* the supported inline-suppression list
8. **Update this guide** — both the WARNING/ERROR table and the "next available" hint above

## Unit Tests

Both custom linters have comprehensive test coverage:

- `tests/unit/scripts/test_lint_skuel.py` — covers all active SKUEL rules, LintResult, suppression + the SKUEL026 audit
- `tests/unit/scripts/test_cypher_linter.py` — covers the active Cypher rules, Python query extraction, and `.cypher` statement extraction

## Key Files

| File | Purpose |
|------|---------|
| `dev` | CLI wrapper — `./dev lint`, `./dev quality`, etc. |
| `pyproject.toml` | Ruff, MyPy, Pyright configuration |
| `scripts/lint_skuel.py` | SKUEL pattern linter (33 rules; SKUEL004 deleted 2026-07, IDs not renumbered) |
| `scripts/cypher_linter.py` | Cypher query linter (CYP001–CYP012; CYP007/CYP008/CYP010 disabled) |
| `scripts/cypher_vocabulary.py` | Shared registry reader + name scanner for SKUEL030/CYP011 and the `looks_like_cypher` admission gate — one anchor, both linters |
| `scripts/cypher_scan_diagnostics.py` | Diagnostic (not a rule): replays both rules' real scan paths and reports every span the scanner admitted but could not read |
| `scripts/quality_discovery.py` | Shared file-discovery exclusion vocabulary (lint_skuel + audit_raw_headers); ruff-exclude overlap pinned by `tests/unit/scripts/test_quality_discovery.py` |
| `scripts/run_quality_checks.py` | Quality check orchestrator |
| `docs/patterns/linter_rules.md` | Detailed rule documentation |

---

**See:** [Linter Rules](../patterns/linter_rules.md) for detailed patterns and examples, [UV Guide](UV_GUIDE.md) for package manager commands
