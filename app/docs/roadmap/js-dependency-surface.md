---
title: JS/Node Dependency Surface — Audit Triage, Coverage Gaps, and the Node 20 Runway
updated: 2026-08-03
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

| | Python | JavaScript |
|---|---|---|
| Audit tool | `pip-audit --strict` (`scripts/audit_dependencies.sh`) | `npm audit --audit-level=moderate` |
| Runs in CI | ✅ `pip_audit` job (`../.github/workflows/ci.yml:279`) | ❌ **no** — `js_tests` runs `npm ci` + vitest only |
| Runs locally | `./dev audit-deps` | `./dev quality` check 8 |
| Accept/ignore mechanism | ✅ `.pip-audit-ignore`, one ID per line with a documented reason | ❌ none |
| Renovate coverage | ⚠ `pep621` manager — **on paper only; Renovate has never run** | ❌ npm not even in `enabledManagers` |
| Written policy | ADR-067 §§ 1–5 | ✅ ADR-067 § 6 (added 2026-08-03) |

Three consequences worth naming:

- **The JS audit is local-only.** Nothing on the CI gate would have caught this. It surfaced
  because someone ran `./dev quality` by hand. A contributor who never runs the full local
  gate can merge a JS advisory without any signal.
- **There is no escape hatch.** Python can accept a finding in `.pip-audit-ignore` with a
  recorded reason. `npm audit` has no per-advisory accept mechanism, so an advisory with no
  upstream fix hard-blocks check 8 — and therefore all of `./dev quality` — until upstream
  ships or the dependency is dropped. We were one unfixable advisory away from that.
- **Renovate does not cover npm.** `renovate.json` sets
  `"enabledManagers": ["pep621", "github-actions", "dockerfile"]`, and per the Renovate docs
  that list *"allow[s] only certain package managers and implicitly disable[s] all others."*
  `app/package.json` and `app/package-lock.json` are never extracted, so the
  `lockFileMaintenance` Monday run never touches them either.

### The larger finding: Renovate has never run

ADR-067 §5 *used to* record "Automation: Renovate opens PRs, never auto-merges." That automation
is **not operating on this repository**, and §5 has since been corrected to say so — it now reads
"Renovate is CONFIGURED but has never run" and carries the evidence below. Evidence (2026-08-03):

- **0** PRs authored by `renovate`/`dependabot` across **920** PRs sampled (full history).
- **0** issues by either, across 200 sampled.
- **No "Dependency Dashboard" issue exists** — decisive, because `renovate.json` extends
  `:dependencyDashboard`, which opens that issue on the first run.

So `renovate.json` is configuration for an app that has never been installed or enabled. This
is worth confirming before any work in §4 is planned around it — enabling Renovate would
change the answer to most of the open decisions below.

---

## 3. The Node 20 runway

**Node 20 reached end-of-life on 2026-04-30** (verified against `nodejs/Release`
`schedule.json`). The repo is past it. Node 22 is in maintenance until 2027-04-30; Node 24
until 2028-04-30.

The only recorded Node version anywhere in the repo is `node-version: '20'` in
`../.github/workflows/ci.yml:661`. There is **no** `engines` field in `app/package.json`, no
`.nvmrc`, no `.node-version`, and no Node in either Dockerfile. Local dev Node is therefore
unpinned and unverified — it happens to work.

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

1. **Is Renovate meant to be running at all?** Still open — installing a GitHub App is a
   founder action. ADR-067 §5 no longer *claims* it runs (corrected 2026-08-03), so the doc is
   at least honest; the choice is between installing it and deleting `renovate.json` rather
   than leaving decorative config. Until then, dependency freshness is manual.
2. **Add `npm` to `enabledManagers`?** Only meaningful after (1). If Renovate is enabled,
   adding `npm` is what prevents the next silent lockfile rot.
3. **Should `npm audit` run in CI?** Adding a step to the existing `js_tests` job is a
   two-line change and closes the local-only gap. The counter-argument is (2): an advisory
   with no accept mechanism can block CI with no way to proceed deliberately — so this pairs
   naturally with deciding what our npm equivalent of `.pip-audit-ignore` is.
4. **Pin Node.** An `engines` field or `.nvmrc` costs nothing and makes the §3 ceiling
   explicit instead of folklore.
5. ~~**Extend ADR-067 to the JS surface, or write a sibling ADR?**~~ **RESOLVED 2026-08-03** —
   amended in place. ADR-067's filename was already scope-neutral and its Context always
   intended all dependencies, so § 6 was *added* (never renumbering, since `pyproject.toml`,
   `CLAUDE.md`, and `tests/integration/test_apoc_canary.py` cite its sections by number) and the
   title dropped "& Python". A sibling ADR was rejected: § 5's false claim had to be corrected
   where it lived, and a second doc cannot do that.
