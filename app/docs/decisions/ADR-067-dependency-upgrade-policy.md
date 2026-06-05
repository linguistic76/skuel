---
title: "ADR-067: Dependency & Python upgrade policy (latest-stable default, documented pins)"
updated: 2026-06-05
status: current
category: decisions
tags: [adr, decisions, dependencies, uv, python, tooling, maintenance]
related: [ADR-044, ADR-049, ADR-063]
---

# ADR-067: Dependency & Python upgrade policy (latest-stable default, documented pins)

**Status:** Accepted

**Date:** 2026-06-05

**Decision Type:** ✅ Pattern/Practice

**Related ADRs:**
- Related to: ADR-044 (Neo4j is a committed choice — explains the neo4j driver pin rationale),
  ADR-049 (HuggingFace embeddings), ADR-063 (LLM/embedding SDK ports).

---

## Context

SKUEL's core philosophy is **"One Path Forward — latest stable"** (see `CLAUDE.md`). That
principle was stated but never *operationalized* for dependencies:

- There was no recorded policy for which Python branch we target or how/when we bump packages.
- There was no single command to see what is outdated — checking meant remembering the raw `uv`
  invocation.
- The only versioning rule that existed was an inline comment pinning the neo4j driver. The
  rationale for the deepgram cap lived nowhere.
- CI runs **no pytest** (memory: "CI runs NO pytest"), so a careless bump can land green in CI and
  break only at runtime. Upgrades need a *local* verification ritual, written down.

This ADR records the policy and the structure that enforces it.

---

## Decision

### 1. Latest-stable is the default

- **Python:** target the **latest stable CPython branch** (currently **3.14**). One back is
  acceptable only as a deliberate, recorded fallback. Alpha/beta/freethreaded builds are never the
  target. The interpreter is pinned in `.python-version` so `uv` and contributors converge on it.
- **Packages:** the `>=` floors in `pyproject.toml` reflect the **currently-locked latest stable**,
  not a historical minimum. Floors are raised to match reality whenever we upgrade — a stale floor
  is a lie about what we actually run and test against.

### 2. The version target lives in one place per concern

| Concern | Where | Value |
|---|---|---|
| Runtime floor | `pyproject.toml` `requires-python` | `>=3.14,<4.0` |
| Type checking | `[tool.mypy]` `python_version`, `[tool.pyright]` `pythonVersion` | `3.14` |
| Interpreter pin | `.python-version` | `3.14` |
| Container base | `Dockerfile`, `Dockerfile.production` | `python:3.14-slim` |
| **Lint/format syntax target** | `[tool.ruff]`/`[tool.black]` `target-version` | **`py312` (intentionally lags — see Deferred)** |

### 3. Intentional pins (exempt from routine upgrades)

Two dependencies are **deliberately capped**. They are NOT stale floors and must not be bumped in a
routine upgrade pass:

- **`neo4j==5.26.0`** — the driver major must match the server/APOC line (ADR-044: Neo4j is a
  committed architectural choice, not a swappable adapter). Moving to the 6.x driver is a deliberate
  server migration with its own ADR + version-matrix update, not a `uv lock --upgrade`.
- **`deepgram-sdk>=4.8.1,<5.0.0`** — 5.x+ is a breaking SDK rewrite. Stay on 4.x until a deliberate
  migration.

Each pin carries an inline `# INTENTIONAL PIN/CAP` comment in `pyproject.toml` pointing here. The
test for "is this a pin or a stale floor?" is: a pin says **why** and references this ADR.

### 4. The upgrade workflow (the ritual CI cannot do for us)

```
1. ./dev deps                 # see what's outdated; note the pins it reminds you of
2. uv lock --upgrade          # re-resolve to latest allowed (pins/caps hold automatically)
3. raise the >= floors in pyproject.toml to match the new lock (step 1's "latest" column)
4. uv sync                    # install onto the pinned interpreter
5. uv run python -c "import main"   # boot smoke test (import the app)
6. ./dev quality              # ruff + SKUEL lint + mypy + pyright + cypher + skills
7. ./dev test-integration     # LOCAL Docker Neo4j — the layer CI does not cover
```

Steps 5–7 are mandatory because **CI runs no pytest**: a mock-only pass proves nothing about a
real driver/runtime bump. Verify against local Docker Neo4j.

### 5. Automation: Renovate opens PRs, never auto-merges

`renovate.json` is configured to **open update PRs for human review only** (no auto-merge). Given CI
has no pytest gate, an unattended merge could ship a runtime break. Renovate groups minor/patch
updates, and is explicitly told to **leave the intentional pins alone**.

---

## Consequences

**Positive**

- "Latest stable" is now a checkable state, not an aspiration: `./dev deps` answers it in one line.
- The two pins are explained once, in code comments *and* here — no more archaeology.
- The upgrade ritual encodes the "CI runs no pytest" reality so bumps are verified where it matters.

**Negative / trade-offs**

- Raising floors on every upgrade means more `pyproject.toml` churn — accepted; the floors are
  documentation of reality.
- Renovate adds PR noise. Mitigated by grouping and PR-only (no auto-merge) mode.

### Deferred: the py314 lint-modernization sweep

Bumping `[tool.ruff]`/`[tool.black]` `target-version` to `py314` surfaces a **codebase-wide
modernization** (~1024 lints: 890 `UP037` quoted-annotation removals + 134 `TC002`/`TC003`
move-import-into-`TYPE_CHECKING`). The `TC` rules are **runtime-risky** here: Pydantic and FastHTML
resolve annotations at runtime (`get_type_hints`), so hiding a referenced type behind
`if TYPE_CHECKING:` can break model construction / route param extraction. Therefore the lint/format
target **intentionally lags** the runtime target (3.14). Modernizing to `py314` lint rules is its own
deliberate change that must review the `TC` moves case-by-case (likely ignoring `TC002`/`TC003`
project-wide). Until then, mypy/pyright already type-check against 3.14 — the lag is cosmetic, not a
correctness gap.
