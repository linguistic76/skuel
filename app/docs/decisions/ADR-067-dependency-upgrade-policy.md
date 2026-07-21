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
- CI runs **unit tests only** (not integration tests), so a careless bump can pass CI and break only
  at runtime against a real database. Upgrades need a *local* verification ritual, written down.

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
| **Lint/format syntax target** | `[tool.ruff]` / `[tool.black]` `target-version` | ruff: **`py314`** (TC002/TC003/UP037 suppressed — see Deferred); black: **`py312`** (still intentionally lags) |

### 3. Intentional pins (exempt from routine upgrades)

Two dependencies are **deliberately capped**. They are NOT stale floors and must not be bumped in a
routine upgrade pass:

- **`neo4j==5.26.0`** — pinned conservatively (ADR-044: Neo4j is a committed architectural choice,
  not a swappable adapter). The driver's version does **not** track the server's: the server runs the
  calendar line (see § 3a) while the driver stays on the last 5.x driver, which the Bolt protocol
  keeps forward-compatible with 2026.x servers (verified live). Bumping the driver is a normal
  latest-stable upgrade under § 4 (test it against the pinned server); moving to the 6.x driver is a
  deliberate migration with its own ADR. Not a silent `uv lock --upgrade`.
- **`deepgram-sdk>=4.8.1,<5.0.0`** — 5.x+ is a breaking SDK rewrite. Stay on 4.x until a deliberate
  migration.

### 3a. Neo4j **server** version policy — latest calendar monthly, hotfix-tracked

The server (Docker image, testcontainers, k8s, all environments) tracks Neo4j's **calendar-versioned
line** (`YYYY.MM.patch`), pinned to the **latest monthly release** — today **`neo4j:2026.06.0`**.

- **Track the latest monthly, don't soak.** Neo4j hotfixes each monthly release **only until the next
  monthly ships** — e.g. `2026.04.0` stopped receiving fixes the moment `2026.05` released. So on this
  line "wait until it's proven stable for a cycle" is self-defeating: by the time a monthly has soaked,
  it is already EOL for hotfixes. The supported posture is to run the **current** monthly and take its
  `.1`/`.2` hotfixes as they land. (Reversing this trade — trading newest features for a long, no-
  treadmill support window — is what the 5.26 **LTS** is for; adopting it would be a separate ADR and a
  store *downgrade*.)
- **"Latest monthly" = latest with a published Docker image.** We pin Docker *images*, and the
  official `library/neo4j` image lags Neo4j's release notes / deployment center by days. A monthly that
  is announced but whose `neo4j:<tag>` image is not yet on Docker Hub is **not** pinnable — pinning it
  would break `docker compose pull` and CI testcontainers. So "current monthly" means the newest one
  whose image is actually pullable; bump when the image lands, not when the release notes drop.
- **Bump cadence ≈ monthly, always deliberate.** When a new monthly's image publishes, bump to it (it
  supersedes the prior line's hotfix support). Pin **exactly** — never a floating `latest`/major/minor
  tag — so every environment is reproducible; the bump is a conscious PR, not an auto-pull.
- **Upgrades are forward and in-place.** Neo4j auto-migrates the store forward, so `2026.06.0` → a
  later monthly is: back up → swap the tag everywhere it is pinned → restart → run integration.
- **Downgrades are not supported** — a store written by a newer server will not open on an older one.
  Rolling back means restoring the pre-upgrade backup, not just re-pinning the old tag.
- **Where the tag lives:** primary source `infrastructure/docker-compose.yml`; mirrors in
  `k8s-manifests.yml`, `docker-compose.production.yml` (template), and the integration testcontainer
  in `tests/integration/conftest.py`. Bump them together; the `test_apoc_canary` version canary fails
  loudly when they drift from the running server.
- **Driver ↔ server:** kept decoupled on purpose (see § 3). The `5.26.0` driver is Bolt-forward-
  compatible with the `2026.x` server; they need not share a version.

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

Steps 5–7 are mandatory because **CI runs unit tests only** (not integration tests): a unit-only
pass proves nothing about a real driver/runtime bump. Verify against local Docker Neo4j.

### 5. Automation: Renovate opens PRs, never auto-merges

`renovate.json` is configured to **open update PRs for human review only** (no auto-merge). Given CI
covers only unit tests (not integration), an unattended merge could ship a runtime break against the
real database. Renovate groups minor/patch updates, and is explicitly told to **leave the intentional
pins alone**.

---

## Consequences

**Positive**

- "Latest stable" is now a checkable state, not an aspiration: `./dev deps` answers it in one line.
- The two pins are explained once, in code comments *and* here — no more archaeology.
- The upgrade ritual encodes the "CI covers unit tests only" reality so bumps are verified where it matters (integration layer).

**Negative / trade-offs**

- Raising floors on every upgrade means more `pyproject.toml` churn — accepted; the floors are
  documentation of reality.
- Renovate adds PR noise. Mitigated by grouping and PR-only (no auto-merge) mode.

### Deferred: TC/UP037 annotation-modernization sweep

Ruff `target-version` was bumped to `py314` in PR #340 (June 2026), but three rules are explicitly
suppressed in `pyproject.toml` to isolate their sweeps:

- **`TC002` / `TC003`** — move third-party / stdlib imports into `TYPE_CHECKING` blocks. **Runtime-risky:**
  Pydantic and FastHTML resolve annotations at runtime (`get_type_hints`), so hiding a referenced type
  behind `if TYPE_CHECKING:` can break model construction or route param extraction. Must be reviewed
  case-by-case before enabling.
- **`UP037`** — remove quotes from type annotations (~890 sites). Own deliberate change; not urgent.

mypy/pyright already type-check against 3.14 — the suppressed rules are a cosmetic backlog, not a
correctness gap.
