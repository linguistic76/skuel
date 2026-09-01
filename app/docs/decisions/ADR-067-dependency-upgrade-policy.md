---
title: "ADR-067: Dependency upgrade policy (latest-stable default, documented pins)"
updated: 2026-08-29
status: current
category: decisions
tags: [adr, decisions, dependencies, uv, python, javascript, npm, node, tooling, maintenance]
related: [ADR-044, ADR-049, ADR-063]
---

# ADR-067: Dependency upgrade policy (latest-stable default, documented pins)

**Status:** Accepted

**Date:** 2026-06-05 (amended 2026-08-05 — Renovate now live, § 5 + drawbacks updated, § 4 CI-coverage corrected: CI runs integration tests since #701; 2026-08-03 — § 6 added, § 5 corrected)

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
- CI ran **unit tests only** at the time (the integration tier was added later — 2026-07-18, #701), so
  a careless bump could pass CI and break only at runtime against a real database. That is why upgrades
  need a *local* verification ritual, written down (§ 4).

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
| **Lint/format syntax target** | `[tool.ruff]` / `[tool.black]` `target-version` | ruff: **`py314`** (TC002/TC003 permanently ignored, UP037 one scheduled sweep — see Deferred); black: **`py312`** (still intentionally lags) |
| **Node runtime** | **Two** `setup-node` pins that must move together — `../.github/workflows/ci.yml` (`js_tests`) and `../.github/workflows/dependency-audit.yml` (`js_audit`) — plus `app/package.json` `engines.node`, `app/.nvmrc`, and `app/.npmrc` (`engine-strict=true`) for local dev | `^24.15.0` (Node 24 LTS Krypton, at jsdom-30's floor; `.nvmrc` = `24`, enforced by engine-strict) — keeps jsdom on 30 / undici on 8.x (§ 6c) |

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
line** (`YYYY.MM.patch`), pinned to the **latest monthly release** — today **`neo4j:2026.07.1`**
(bumped 2026-08-28; the line went `2026.06.0` → `2026.07.1` — no `2026.07.0` image was ever published).

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
- **Bump cadence ≈ monthly, always deliberate — and since 2026-08-28, PROPOSED by Renovate.** The
  `docker-compose` manager is enabled for `infrastructure/docker-compose.yml` only (§ 5 — scoped by a
  package rule that disables `app/**`, because `managerFilePatterns` is additive to the manager's
  defaults and cannot exclude a file), so when a new
  monthly's image publishes Renovate opens the bump PR; a human merges it after CI's integration job has
  run the proposed image. Pin **exactly** — never a floating `latest`/major/minor tag — so every
  environment is reproducible; the bump is a reviewed PR, not an auto-pull. The treadmill lapsed for a
  month before this (pinned `2026.06.0` while `2026.07.1` had been published since 2026-08-25) because
  nothing watched it — a prose obligation is not a trigger. Manual check, when you want one:

  ```bash
  curl -s "https://hub.docker.com/v2/repositories/library/neo4j/tags?name=2026.&page_size=100" \
    | uv run python -c "import sys,json; print(sorted(t['name'] for t in json.load(sys.stdin)['results'] if t['name'].replace('.','').isdigit()))"
  grep -n 'image: neo4j:' infrastructure/docker-compose.yml   # must equal the newest tag printed
  ```
- **Upgrades are forward and in-place.** Neo4j auto-migrates the store forward, so `2026.06.0` → a
  later monthly is: back up → swap the tag everywhere it is pinned → restart → run integration.
- **Downgrades are not supported** — a store written by a newer server will not open on an older one.
  Rolling back means restoring the pre-upgrade backup, not just re-pinning the old tag.
- **Where the tag lives — ONE place:** `infrastructure/docker-compose.yml`. The integration
  testcontainers no longer mirror it: `tests/integration/_neo4j_pin.py` YAML-parses the compose pin
  (the one reader — `conftest.py` and the APOC-lockdown suite both start that image) and the
  `test_apoc_canary` version canary asserts the running server reports exactly that version (production runs no Neo4j service — it
  talks to AuraDB). A floating tag fails the pin reader loudly, so "exact tag" is enforced, not
  requested. Before the 2026-08-28 bump the mirror had drifted with the primary for a month.
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
5. uv run python -c "import asyncio; from scripts.dev.bootstrap import bootstrap_skuel; asyncio.run(bootstrap_skuel())"
                              # boot smoke test — COMPOSES the app (services + every @rt handler);
                              # `import main` alone registers nothing (main() is __main__-guarded)
6. ./dev quality              # ruff + SKUEL lint + mypy + pyright + cypher + skills
7. ./dev test-integration     # LOCAL Docker Neo4j — same suite CI's integration_tests job runs
```

Run steps 5–7 locally before opening the PR — they are the fast pre-push check for an upgrade you are
making by hand. **CI also runs the integration tier** (since 2026-07-18, #701): the `integration_tests`
job runs `pytest tests/integration/` against a testcontainer Neo4j on any `py`/`cypher` change — a
lockfile bump counts — using the same command as step 7. So CI backstops you, but a real driver/runtime
bump is exactly what you want to see green locally first.

### 5. Automation: Renovate is LIVE — it opens update PRs; scheduled audits cover vulnerabilities

> **Updated 2026-08-05.** Renovate is now running. History: this section once asserted Renovate
> opened PRs; a **2026-08-03** correction found the automation had never actually run (`renovate.json`
> was config for an app nobody had installed); on **2026-08-05** the Mend-hosted Renovate GitHub App
> was installed and un-silenced, and it now opens PRs. Dependency freshness is no longer a purely
> manual responsibility.

`renovate.json` describes PR-only updates for human review (no auto-merge), grouped minor/patch, with
the intentional pins excluded. As of **2026-08-05** that intent is operating:

- The **Mend-hosted Renovate App** is installed (plan: Community/Free, Renovate v44.12.0). Run logs
  live at the Mend developer portal (`developer.mend.io/github/linguistic76/skuel`), not in the repo.
- It first defaulted to **Silent mode** — a *Mend-portal* setting, **not** in `renovate.json`, that
  computes updates but pushes nothing to GitHub, staging them in the portal for manual "Create/Rebase."
  That is why a first repo-side check still saw 0 PRs and no Dependency Dashboard. Silent was turned
  **off** the same day.
- With Silent off, the first run opened grouped PRs (**#942–#946**) and the **Dependency Dashboard**
  issue (**#947**) — the `:dependencyDashboard` artifact whose earlier absence had been the decisive
  proof the app had never run.

So Renovate now watches for stale dependencies and proposes bumps as reviewable PRs. It sits alongside
a **vulnerability** layer, which reports *published CVEs* rather than staleness:

| Signal | Covers | Automated? | Trigger |
|---|---|---|---|
| Renovate PRs | **both** ecosystems — **freshness** | ✅ yes | Mend App schedule; PR-only, no auto-merge — **live 2026-08-05** |
| Renovate PRs — Neo4j **server** image | the calendar-monthly treadmill (§ 3a) | ✅ yes | `docker-compose` manager, scoped to `infrastructure/docker-compose.yml` by a package rule disabling `app/**` — **since 2026-08-28**; the pypi-only `neo4j` driver pin rule deliberately does not catch the docker `neo4j` image |
| `dependency-audit.yml` | **both** ecosystems — CVEs | ✅ yes | **daily cron**, independent of any diff — added 2026-08-03 |
| `dep_audit` CI job (required) | **both** ecosystems — CVEs | ✅ yes | **diff-triggered** — the `py`/`audit` path filters (the `audit` filter carries the JS lockfile) |
| `./dev quality` check 8 / `./dev audit-deps` | **both** ecosystems — CVEs | local | the same script as both jobs above — one path |

All three CVE rows run **one script** — `scripts/audit_dependencies.sh`, osv-scanner over `uv.lock`
and `package-lock.json` (consolidated 2026-08-07; pip-audit and the direct `npm audit` call retired —
see § 6e and `/docs/roadmap/done/dependency-scanner-consolidation.md` for the measured migration). The
scheduled audit still earns its place: it catches what Renovate does not — a CVE published against a
lockfile nobody touched. The `dep_audit` job is diff-gated, so no diff means it never fires. That is
exactly how `undici` 7.28.0 sat vulnerable until a manual `./dev quality` caught it (PR #929). The
scheduled job is **advisory** — a cron run has no PR to gate; the PR-side gate is `dep_audit`.

`npm` is in `enabledManagers` as of **2026-08-05** (#941), so `package.json` / `package-lock.json` are
now extracted; without it the Renovate docs' allowlist semantics (only the listed managers run) would
have left the JS tree unmanaged. (Was open decision 2 in
[`/docs/roadmap/done/js-dependency-surface.md`](../roadmap/done/js-dependency-surface.md); now resolved.)

### 6. JavaScript / Node dependencies

Everything above §5 was written for the Python surface. `app/package.json`, `app/package-lock.json`
and the Node toolchain are governed by the same **latest-stable-by-default** principle, with the
rules below. Added 2026-08-03 (PR #929 exposed the omission).

**6a. Triage order for a transitive JS advisory** (reported by the audit script). Most of the time
you stop at step 2.

1. `npm ls <pkg>` — find the parent. A transitive dep is a symptom; the parent is what you control.
2. **Check for a patched release inside the range already declared.** Compare the parent's declared
   range (`npm view <parent>@<ver> dependencies.<pkg>`) against what the registry has
   (`npm view <pkg> versions --json`, `npm view <pkg> dist-tags`). A major line upstream has moved
   off is often still receiving backports — the fix may already be inside the range you accept.
3. Read npm's own hint (run `npm audit` by hand — it remains useful interactively even though no
   gate invokes it): *"fix available via `npm audit fix`"* means a semver-compatible fix exists.
   *"requires --force"* or *breaking change* means the in-range option is gone.
4. Only then consider a parent major bump or an `overrides` entry — and check § 6c first.

**6b. `overrides` is a pin, and carries a pin's obligations.** An `overrides` entry in
`package.json` forces a transitive version for every consumer and **silently outlives the advisory
that motivated it** — nothing revisits it. Same rule as § 3: it must say *why* and reference this
ADR. Prefer an in-range fix (§ 6a step 2) or a parent bump; reach for `overrides` only when neither
exists.

**6c. Check the runtime ceiling before any parent major bump.** The Node version caps the
dependency tree, and the cap is invisible until an advisory lands:

```
Node 20  →  jsdom ^29  →  undici 7.x   (EOL 2026-04-30 — migrated away 2026-08-05)
Node 24  →  jsdom 30   →  undici 8.x   (jsdom 30 engines: ^22.22.2 || ^24.15.0 || >=26.0.0)
```

**The repo runs Node 24 (LTS Krypton) as of 2026-08-05**, having migrated off end-of-life Node 20.
The version is pinned in **three places that must move together**: the `setup-node` step in
`../.github/workflows/ci.yml` (`js_tests`, `node-version: '^24.15.0'`), plus `app/package.json`
`engines.node` (the same `^24.15.0` — the Node 24 LTS line at jsdom-30's floor; the caret excludes
non-LTS 25.x, which jsdom 30 does not support) and `app/.nvmrc` (`24`) for local dev. (A fourth pin,
`dependency-audit.yml`'s `js_audit` setup-node step, left with the osv-scanner consolidation — the
scheduled audit no longer runs Node at all.) The `setup-node` step uses the range rather than a bare
`'24'` on purpose: with the default `check-latest: false`, `'24'` can select an older cached
`24.0–24.14` below jsdom's floor, so the CI pin mirrors `engines.node` exactly.

`.nvmrc` names the line, not a floor — nvm has no caret syntax, and `nvm use` can resolve a bare `24`
to an already-installed `24.0–24.14`. So `app/.npmrc` sets **`engine-strict=true`**, which hard-fails
`npm ci` / `npm install` on any Node below `engines.node` instead of silently installing and testing
under an engine-mismatched runtime. That makes the `^24.15.0` floor authoritative for **every** local
path, not just nvm, and is the real backstop behind the pins above. Bumping the workflows without the
local-dev pins (or vice versa) leaves contributors on a different toolchain than CI. The Node 24 floor is what unlocked jsdom 30 and moved undici onto the
8.x line. Before any future parent major bump, re-check this ceiling — a dependency that needs a
newer Node forces a runtime migration, so plan it before the gate is red, not during.

**6d. Verification for any JS dependency change.** `npm ci` first — **without it this recipe can
pass vacuously.** `npm audit` reads the lockfile, but `npm run test:js` executes whatever is in
`node_modules`, and `./dev quality` never installs. In a checkout whose `node_modules` predates the
change (a colleague's branch, a lockfile-only diff, a revert), the tests would green-light a
resolution they never loaded. `npm ci` deletes and reinstalls exactly the lockfile — the same step
the `js_tests` CI job runs.

```
npm ci                             # install the REVIEWED resolution — never skip on a lockfile diff
./dev audit-deps                   # osv-scanner over both lockfiles (same script as CI + check 8)
npm run test:js                    # vitest's jsdom environment now exercises the installed tree
./dev quality                      # full gate
```

**6e. The accept mechanism, and the all-severities policy (closed 2026-08-07).** Historically this
section recorded a gap: `npm audit` had no per-advisory accept mechanism, so an advisory with no
upstream fix would have hard-blocked `./dev quality` with no documented way to proceed — the reason
the scheduled audit stayed advisory and no dependency audit could be a required check.

The osv-scanner consolidation closed it. **`app/osv-scanner.toml` is the ONE dispositions file for
both ecosystems**: each accepted advisory carries an `id`, a `reason` naming why it is unfixable
today and what unblocks it, and an **`ignoreUntil` expiry** — the scanner re-raises the finding the
day it lapses, so acceptance is a dated decision the tooling re-examines, not a permanent exemption.
Delete the entry the moment an upgrade path exists (One Path Forward). With the escape hatch in
place, the PR-side audit (`dep_audit`) is a **required** check.

**Severity policy — ruled 2026-08-07: ALL severities, both ecosystems, everything dispositioned.**
The former JS `--audit-level=moderate` floor was a *workaround* for the missing accept mechanism —
the only available valve against unfixable low-severity noise — and was deleted together with that
gap. A severity floor is a structured silent drop: nobody ever sees what falls below it, and a
finding with no severity metadata has no honest place under one. Now every advisory in either
lockfile is reported and either fixed or accepted with a reason. If low-severity churn ever becomes
a real cost, the JSON output carries per-finding severity + CVSS, so a post-filter is a small,
*informed* change — the reverse order (filter first, learn never) was rejected deliberately.
Measured at the ruling: the JS surface had zero findings at any severity, so the unification cost
nothing on day one.

---

## Consequences

**Positive**

- "Latest stable" is now a checkable state, not an aspiration: `./dev deps` answers it in one line.
- The two pins are explained once, in code comments *and* here — no more archaeology.
- The upgrade ritual verifies bumps at the integration layer locally, where driver/runtime breaks surface — a fast pre-push check ahead of the `integration_tests` CI job (added 2026-07-18) that also gates them.

**Negative / trade-offs**

- Raising floors on every upgrade means more `pyproject.toml` churn — accepted; the floors are
  documentation of reality.
- Renovate adds PR noise — mitigated by grouping (minor/patch batched) and PR-only, no-auto-merge
  mode. **Live again as of 2026-08-05** (§ 5): after a stretch where Renovate never ran — during which
  the real trade-off was the opposite, that freshness was entirely manual — the Mend App is installed
  and opens grouped PRs. Expect a burst on each run (up to `prConcurrentLimit: 5`), and each bump still
  needs a local verification pass before merge (§ 4).
- The scheduled audit files an issue rather than blocking a merge. That is deliberate (§ 6e), and
  the cost is real: a red scheduled run is easy to ignore in a way a red PR check is not.

### Deferred: TC/UP037 annotation-modernization sweep — ruled 2026-08-28, two dispositions

Ruff `target-version` was bumped to `py314` in PR #340 (June 2026) with three rules suppressed in
`pyproject.toml`. **These counts live here and nowhere else** — `CLAUDE.md`, `pyproject.toml` and
`deferred-work.md` name the command instead of a number, because a copied count decays in both
directions: the UP037 figure below was stale within a day, and TC003 was written as `161` into two
files on a tree that measured `162`. Baseline at `fd08f3bd7`
(`uv run ruff check --select TC002,TC003,UP037 --statistics .`): UP037 **1222** (all marked
safe-fixable), TC003 **162**, TC002 **91**. They are two kinds of work:

- **`TC002` / `TC003` — permanent ignore, never a sweep.** Moving an import under `TYPE_CHECKING` is
  only safe where nothing evaluates the annotation at runtime. `[tool.ruff.lint.flake8-type-checking]
  runtime-evaluated-base-classes` already exempts `pydantic.BaseModel` and `fasthtml.common.ft`
  subclasses, so what the counts contain is exactly the residue ruff cannot see: FastHTML route
  handlers, whose signatures the *local* `@rt` decorator introspects at registration (not expressible
  as a `runtime-evaluated-decorators` entry — those take dotted paths), plus every
  `get_type_hints`-style consumer. A bulk move turns a lint pass into a bootstrap-time `NameError`.
  Enable either rule only per file, after checking no annotation in it is evaluated; the pyproject
  comment now says *permanent*, not *deferred*.
- **`UP037` — one mechanical PR whenever convenient.** Under 3.14's deferred evaluation the quotes are
  redundant and ruff marks every fix safe. The one hazard is the mirror image of the TC one: a
  quoted name imported only under `TYPE_CHECKING` is inert as a string but, unquoted, becomes a
  deferred reference that raises `NameError` the moment something introspects that signature — the
  FastHTML bootstrap gotcha. So the sweep is `uv run ruff check --select UP037 --fix .`, then a
  check that actually COMPOSES the app — `uv run python -c "import asyncio; from scripts.dev.bootstrap import bootstrap_skuel; asyncio.run(bootstrap_skuel())"`
  against a reachable Neo4j (it is what `main()` runs; `bootstrap_skuel()` builds the services and
  registers every `@rt` handler, which is the moment FastHTML evaluates the signatures) — or
  `./dev test-integration`, whose `tests/conftest.py` app fixture calls the same function. A bare
  `import main` registers nothing (`main()` is `__main__`-guarded) and `./dev smoke` renders static
  fixtures without a server, so neither can see the failure. A `NameError` at bootstrap names the
  site, which keeps its quotes (or gains a runtime import). Churn across most of the tree → its
  own PR in a merge lull.

**Trigger + check** live in `deferred-work.md` § "py314 Annotation Sweeps" (UP037: Mike picks the
window; TC002/TC003: never). mypy/pyright already type-check against 3.14 — the backlog is cosmetic,
not a correctness gap.
