---
title: JS/Node Dependency Surface — Audit Triage, Coverage Gaps, and the Node 20 Runway
updated: 2026-08-05
category: roadmap
tags: [roadmap, dependencies, security, javascript, node, npm, maintenance]
---
# JS/Node Dependency Surface — Audit Triage, Coverage Gaps, and the Node 20 Runway

**Created:** 2026-08-03
**Trigger:** `./dev quality` check 8 (npm Audit) went red on `main` at 4041a0025 — 5 high
GHSAs against `undici` 7.28.0, pulled in transitively by `jsdom`.
**Authority:** `/docs/decisions/ADR-067-dependency-upgrade-policy.md` — §§ 1–5 Python,
**§ 6 JavaScript / Node** (added 2026-08-03; this doc supplied its raw material)
**Related:** `/docs/roadmap/security-hardening-deferred.md` (item 5A is the pip-audit
counterpart), `scripts/run_quality_checks.py` (check 8), `scripts/audit_dependencies.sh`

The incident itself was a three-line lockfile bump. What it exposed is that the JS
dependency surface was governed by **nothing written down** — at the time, ADR-067 contained no
mention of `npm`, `node`, `package.json`, or `audit`, and the automation it described had never
run.

> **Update 2026-08-03:** the policy half is now closed. ADR-067 gained **§ 6 (JavaScript / Node
> dependencies)** — triage order, the `overrides`-is-a-pin rule, and the runtime ceiling — and
> **§ 5 was corrected** to state that Renovate has never run. Open decision 5 below is therefore
> resolved; the rest stand.
>
> **Update 2026-08-05:** Renovate is now **live** — the Mend-hosted App was installed and un-silenced,
> `npm` was added to `enabledManagers` (#941), and the first run opened PRs #942–#946 plus a Dependency
> Dashboard (#947). Open decisions **1 and 2 are resolved**; §§ 2–3 and decisions 4 & 6 stand.

---

## 1. Triage order for a transitive `npm audit` failure

Do these in order. Most of the time you stop at step 2.

1. **Find the parent.** `npm ls <pkg>` in `app/`. A transitive dep is a symptom; the parent
   is what you actually control.
2. **Check for a patched release inside the range already declared.** Read the parent's
   declared range (`npm view <parent>@<version> dependencies.<pkg>`) and list what the
   registry actually has (`npm view <pkg> versions --json`, `npm view <pkg> dist-tags`).
   **A major line that upstream has moved off is still maintained for a while** — the fix is
   often a patch release you can already accept.
3. **Read npm's own hint.** When the report ends with *"fix available via `npm audit fix`"*,
   a semver-compatible fix exists. If it instead says the fix requires `--force` or is a
   *breaking change*, the in-range option is gone and you are in step 4.
4. **Only then** consider a parent major bump or an `overrides` entry — and check the
   runtime ceiling (§3) before either.

**Worked example (2026-08-03).** `jsdom@29.1.1` declares `undici: ^7.25.0`; the lockfile held
7.28.0; the advisory range was `7.0.0 - 7.28.0`. undici **7.29.0** existed — the patched 7.x
release, already inside `^7.25.0`. `npm audit fix` moved one lockfile entry; `package.json`
was untouched. The tempting wrong moves were both available and both worse: `npm audit fix
--force` would have pulled jsdom 30 (which **cannot run on Node 20** — see §3), and an
`overrides` entry would have pinned a transitive dep in perpetuity to route around a problem
that did not exist.

**The rule to carry forward:** *check whether the fix is already inside the range you
declare, before reaching for a bump or an override.* An `overrides` entry is a standing
commitment — it silently outlives the advisory that motivated it, and nothing revisits it.

### Verifying the fix

- **`npm ci` FIRST.** Without it the rest can pass vacuously: `npm audit` reads the lockfile,
  but `npm run test:js` executes whatever is already in `node_modules` and `./dev quality`
  never installs. On a lockfile-only diff — a colleague's branch, a revert — the tests would
  green-light a resolution they never loaded. `npm ci` reinstalls exactly the lockfile, which
  is what the `js_tests` CI job does.
- `npm audit --audit-level=moderate` in `app/` — must exit 0 (this is exactly what check 8
  runs).
- `npm run test:js` — vitest runs in the **jsdom** environment, so with the reviewed tree
  installed the jsdom/undici chain is genuinely exercised rather than merely resolved.
- `./dev quality` — full gate.

---

## 2. Coverage gap: the JS surface has no owner

Verified 2026-08-03. The asymmetry is not "Python is gated and JS is not" — both have an
audit tool. The gap is in *where each one runs* and *what happens when it fires*.

> **Update 2026-08-03:** the CI half is closed. `dependency-audit.yml` runs **both** audits on
> a daily cron, diff-independent, and files an issue on findings. Decision 3 below is resolved
> — though not the way it was originally framed. The accept-mechanism gap (decision 3's
> counter-argument) is still open, and is exactly why the new job is advisory rather than a
> required check.

| | Python | JavaScript |
|---|---|---|
| Audit tool | `pip-audit --strict` (`scripts/audit_dependencies.sh`) | `npm audit --audit-level=moderate` |
| Runs on PRs | ✅ `pip_audit` job (`../.github/workflows/ci.yml:279`) — **diff-gated** | ❌ **no** — `js_tests` runs `npm ci` + vitest only |
| Runs on a schedule | ✅ `dependency-audit.yml` daily | ✅ `dependency-audit.yml` daily *(added 2026-08-03)* |
| Runs locally | `./dev audit-deps` | `./dev quality` check 8 |
| Accept/ignore mechanism | ✅ `.pip-audit-ignore`, one ID per line with a documented reason | ❌ none |
| Renovate coverage | ✅ `pep621` manager — **live since 2026-08-05** | ✅ `npm` added to `enabledManagers` (2026-08-05, #941) |
| Written policy | ADR-067 §§ 1–5 | ✅ ADR-067 § 6 (added 2026-08-03) |

Three consequences worth naming:

- ~~**The JS audit is local-only.**~~ **CLOSED 2026-08-03** by the daily
  `dependency-audit.yml`. As written, nothing on the CI gate would have caught this — it
  surfaced only because someone ran `./dev quality` by hand. Note what did *not* fix it:
  adding a step to `js_tests` would still have missed this incident, because that job is
  gated on the `js` path filter and **no file changed at all** (see decision 3).
- **There is no escape hatch.** Python can accept a finding in `.pip-audit-ignore` with a
  recorded reason. `npm audit` has no per-advisory accept mechanism, so an advisory with no
  upstream fix hard-blocks check 8 — and therefore all of `./dev quality` — until upstream
  ships or the dependency is dropped. We were one unfixable advisory away from that.
- ~~**Renovate does not cover npm.**~~ **RESOLVED 2026-08-05.** `renovate.json` now sets
  `"enabledManagers": ["pep621", "npm", "github-actions", "dockerfile"]` (#941), so
  `app/package.json` / `app/package-lock.json` are extracted and the `lockFileMaintenance` Monday
  run covers them. As originally written the list omitted `npm`, and per the Renovate docs the
  allowlist *"allow[s] only certain package managers and implicitly disable[s] all others"* — which
  is why the first js-minor/patch PR (#943) only appeared once `npm` was added.

### The larger finding: Renovate was never running — now it is (resolved 2026-08-05)

For most of this repo's history Renovate was configured but **never ran**. The 2026-08-03 evidence
that established this:

- **0** PRs authored by `renovate`/`dependabot` across **920** PRs sampled (full history).
- **0** issues by either, across 200 sampled.
- **No "Dependency Dashboard" issue existed** — decisive, because `renovate.json` extends
  `:dependencyDashboard`, which opens that issue on the first run.

**Resolved 2026-08-05.** The Mend-hosted Renovate App was installed. It first ran in Mend **Silent
mode** (a portal setting, not in `renovate.json`) — which computes updates but pushes nothing to
GitHub, so the repo-side signals above briefly still read "never ran." Turning Silent off produced
the missing artifacts immediately: the **Dependency Dashboard** issue (#947) and grouped PRs
(#942–#946). Enabling Renovate resolved decisions 1 and 2 below.

---

## 3. The Node 20 runway

**Node 20 reached end-of-life on 2026-04-30** (verified against `nodejs/Release`
`schedule.json`). The repo is past it. Node 22 is in maintenance until 2027-04-30; Node 24
until 2028-04-30.

Node is recorded **only in two `setup-node` steps, which must be bumped together**:
`../.github/workflows/ci.yml` (`js_tests`) and `../.github/workflows/dependency-audit.yml`
(`js_audit`, added 2026-08-03). There is **no** `engines` field in `app/package.json`, no
`.nvmrc`, no `.node-version`, and no Node in either Dockerfile. Local dev Node is therefore
unpinned and unverified — it happens to work. Bumping one workflow and not the other would leave
the scheduled security audit on a different toolchain than the tests, which is decision 4 below.

Staying on Node 20 imposes a ceiling that is invisible until an advisory lands:

```
Node 20  →  jsdom ^29  →  undici 7.x
Node 22+ →  jsdom 30   →  undici 8.x   (jsdom 30 engines: ^22.22.2 || ^24.15.0 || >=26.0.0)
```

undici's `latest` is **8.10.0**; the 7.x line survives under the `seven` dist-tag at 7.29.0.
Today's fix works precisely because 7.x is still receiving backports. **The next 7.x advisory
may not get one** — and at that point the only fix is jsdom 30, which requires bumping Node
in CI first. That is a migration, not a lockfile bump, and it should not be discovered while
the gate is red.

**Trigger to act:** any of —
- an `undici` advisory with no fix inside the 7.x line, or
- undici 7.x dropping out of maintenance (watch the `seven` dist-tag), or
- a routine decision to leave EOL Node, which is independently overdue.

**Migration sketch (small, once Node moves):** bump `node-version` in `ci.yml` to `22`; add
an `engines` field and/or `.nvmrc` so local and CI agree; `npm install jsdom@^30`; run
`npm run test:js`. The jsdom-30 API surface change that matters to us is bounded — the vitest
`environment: 'jsdom'` harness in `vitest.config.js` and `tests/js/helpers/load-skuel.js` are
the only consumers.

---

## 4. Open decisions

These need a founder ruling; none is urgent, all are cheap.

1. ~~**Is Renovate meant to be running at all?**~~ **RESOLVED 2026-08-05 — yes.** The Mend-hosted
   Renovate App was installed and un-silenced; `renovate.json` is no longer decorative config.
   Dependency freshness is now automated as reviewable PRs (no auto-merge).
2. ~~**Add `npm` to `enabledManagers`?**~~ **RESOLVED 2026-08-05 (#941).** `npm` is in the manager
   list, so the JS lockfile is now watched — closing the silent-rot gap this doc was written around.
3. ~~**Should `npm audit` run in CI?**~~ **RESOLVED 2026-08-03 — but the proposal above was
   wrong, and worth recording as such.** It suggested adding a step to `js_tests`. That job is
   gated on the `js` path filter (`static/js/**`, `tests/js/**`, `package*.json`,
   `vitest.config.js`), and **this incident changed none of those files** — the lockfile sat
   still while the advisories were published around it. That placement would have added the
   *appearance* of coverage while staying blind to the exact failure mode. Diff-gating is the
   wrong trigger for a check whose input changes on someone else's clock. Shipped instead as
   `dependency-audit.yml`: a daily cron running **both** audits, diff-independent, filing an
   issue on findings. The same latent hole existed on the Python side — `pip_audit` is
   diff-gated too, merely masked because its `py` filter matches nearly every PR — so the
   scheduled job covers both.
4. **Pin Node.** An `engines` field or `.nvmrc` costs nothing and makes the §3 ceiling
   explicit instead of folklore. **Still open** — deliberately not folded into the
   scheduled-audit PR, since it changes what every contributor's toolchain must satisfy.
5. ~~**Extend ADR-067 to the JS surface, or write a sibling ADR?**~~ **RESOLVED 2026-08-03** —
   amended in place. ADR-067's filename was already scope-neutral and its Context always
   intended all dependencies, so § 6 was *added* (never renumbering, since `pyproject.toml`,
   `CLAUDE.md`, and `tests/integration/test_apoc_canary.py` cite its sections by number) and the
   title dropped "& Python". A sibling ADR was rejected: § 5's false claim had to be corrected
   where it lived, and a second doc cannot do that.
6. **What is our npm equivalent of `.pip-audit-ignore`?** *(New, split out of decision 3.)*
   Unresolved, and it is the blocker on ever making a dependency audit a **required** check.
   `npm audit` has no per-advisory accept mechanism, so an advisory with no upstream fix would
   wedge every merge. Until this exists, `dependency-audit.yml` stays advisory — it files an
   issue and goes red on its own schedule, and the cost is that a red scheduled run is easier
   to ignore than a red PR check. Plausible shapes: an allowlist file consumed by a wrapper
   around `npm audit --json`, or `npm audit --audit-level=high` plus a documented review of
   what that silently drops.

   **A third shape would close this for free:** `osv-scanner.toml` supports
   `[[IgnoredVulns]]` with `id`, `reason` and `ignoreUntil`, for *both* ecosystems — so
   consolidating on one scanner would supply the missing mechanism rather than build it.
   See [`/docs/roadmap/dependency-scanner-consolidation.md`](dependency-scanner-consolidation.md),
   which treats this decision as its headline motivation.
