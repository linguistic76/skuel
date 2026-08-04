---
title: One Dependency Scanner — Retire pip-audit for osv-scanner
updated: 2026-08-03
category: roadmap
tags: [roadmap, dependencies, security, tooling, uv, npm, maintenance]
---
# One Dependency Scanner — Retire pip-audit for osv-scanner

**Created:** 2026-08-03
**Status:** Proposed, not scheduled. Cheap to do, safe to defer — nothing is broken today.
**Authority:** `/docs/decisions/ADR-067-dependency-upgrade-policy.md` (§ 5 signals, § 6e the JS gap)
**Related:** `/docs/roadmap/js-dependency-surface.md` (the open decision this would close),
`/docs/roadmap/security-hardening-deferred.md` item 5 (where `.pip-audit-ignore` was agreed),
`scripts/audit_dependencies.sh`, `../.github/workflows/dependency-audit.yml` (the scheduled
audit, merged as **#931**)

The question that produced this doc was "uv replaced pip, so why is pip-audit here?" The
answer is that `pip-audit` is a **scanner**, not an installer, so uv does not obsolete it —
`uv 0.10.9` has no audit subcommand at all. But the instinct was right for a different
reason, and chasing it turned up something better than tidiness.

---

## 1. What is true today (verified 2026-08-03)

| | Python | JavaScript |
|---|---|---|
| Scanner | `pip-audit --strict --disable-pip --vulnerability-service osv` | `npm audit --audit-level=moderate` |
| Input | `uv export --locked` → a requirements.txt **derived** from `uv.lock` | `package-lock.json` directly |
| Advisory source | **OSV** (selected explicitly) | GitHub Advisory DB (npm registry) |
| Accept mechanism | `.pip-audit-ignore` — 9 IDs, suppressing 17 findings | ❌ **none** |

Two details matter for what follows:

- **`pip` is installed in `.venv` even though nothing uses it.** `pip` is not declared in
  `pyproject.toml`; it arrives transitively via `pip-audit` → `pip-api`. The audit itself
  passes `--disable-pip`, so pip never resolves anything. It is present and inert.
- **The Python audit scans a derived artifact**, not the lockfile. `uv export` converts
  `uv.lock` to requirements.txt (with hashes) and pip-audit reads that. One conversion step
  that has to stay faithful.

---

## 2. Why consolidating is genuinely better — not just tidier

`osv-scanner` reads **`uv.lock` and `package-lock.json` natively** (both are on Google's
supported-lockfiles list, verified). Adopting it would mean one scanner for both ecosystems.
Four consequences, in ascending order of importance:

1. **The pip chain leaves the tree.** `pip-audit`, `pip-api`, `pip-requirements-parser` and
   therefore `pip` all disappear from the lock. The venv stops carrying an installer it never
   uses.
2. **No derived artifact.** The lockfile is scanned directly, so the `uv export` conversion
   stops being a thing that can drift.
3. **One tool, one config, one output shape** for both ecosystems — which collapses the
   two-job split in `dependency-audit.yml` and removes the awkward asymmetry documented in
   its header (the JS job can prove it measured; the Python job cannot).
4. **It gives JavaScript an accept mechanism — and that is the real prize.**

### On (4): this closes the blocker, not just a nicety

`osv-scanner.toml` supports:

```toml
[[IgnoredVulns]]
id = "GHSA-xxxx-xxxx-xxxx"
ignoreUntil = 2026-11-09     # optional expiry
reason = "no fixed release published upstream"
```

plus `PackageOverrides` for per-package scoping.

**ADR-067 § 6e records that `npm audit` has no per-advisory accept mechanism, and that this
is precisely why the scheduled audit is advisory rather than a required check** — an
advisory with no upstream fix would otherwise wedge every merge. `osv-scanner.toml` supplies
that mechanism for both ecosystems at once. It is the thing standing between the dependency
audit and being a gate.

It is also **better than what Python has now**. `.pip-audit-ignore` carries reasons as free
prose comments and has no expiry — its header states a re-check convention, and nothing
enforces it. An entry like *"diskcache 5.6.3 — no fixed release published at all
(2026-07-24)"* is exactly the kind of decision that should expire and be re-examined.
`ignoreUntil` makes that structural instead of aspirational.

---

## 3. What it costs, honestly

- **A new class of tool.** `osv-scanner` is a Go binary. Every other dev tool here is either
  uv-managed Python or npm. CI has an official action; local use needs the binary on PATH,
  so `./dev audit-deps` changes shape and `SETUP.md` grows a line.
- **9 accepted findings to port**, each with its documented reason preserved. The port is an
  opportunity — assign every entry an `ignoreUntil` while migrating — but it is careful work,
  not a mechanical translation.
- **Two advisory sources become one.** Today the JS side reads the GitHub Advisory DB via
  `npm audit`; osv-scanner reads OSV. OSV aggregates GHSA, so coverage should be a superset —
  but *should* is not *measured*. See § 4.

---

## 4. The risk that must be measured, not assumed

**`pip-audit --strict` fails on dependencies it cannot audit rather than warning.** Whether
`osv-scanner` has an equivalent — and what it does with a package it cannot match — is
**not established**; the supported-lockfiles docs do not say, and this doc deliberately does
not guess.

This is the whole risk of the migration, and it is the dangerous shape: a scanner that
silently skips what it cannot resolve produces a clean result that looks identical to a
genuinely clean tree. Swapping tools on the assumption of parity could quietly reduce
coverage while every dashboard stays green.

**So the migration is gated on a differential measurement, not on reading documentation.**

### The second unknown: severity thresholds, and an asymmetry nobody wrote down

The two ecosystems do **not** apply the same severity policy today (verified 2026-08-03):

| | threshold | where |
|---|---|---|
| Python | **none — every severity is reported** | `pip-audit` takes no audit-level; `audit_dependencies.sh` sets only `--strict` |
| JavaScript | **moderate-or-higher** | `npm audit --audit-level=moderate` (`run_quality_checks.py:173`) and the `SEV` filter in `dependency-audit.yml` |

That asymmetry is undocumented and consolidation forces a decision about it. Whether
`osv-scanner` can express a minimum severity at all is **not established** — its usage docs
describe `--config` and `PackageOverrides`, neither of which is a severity threshold.

Two consequences to design for rather than discover:

- If osv-scanner has no threshold, preserving the JS policy means post-filtering its output,
  which is more work than "point it at both lockfiles".
- Low-severity JS findings must **not** be parked in `[[IgnoredVulns]]`. That entry means
  *"we have accepted this specific vulnerability"*; using it to enforce a global severity
  floor conflates policy with case-by-case acceptance, and the resulting file stops being
  reviewable — every reader would have to know which entries are real decisions and which
  are threshold noise.

**Decide the policy explicitly before migrating**: keep moderate-or-higher for JS and
all-severities for Python, or unify. Either is defensible; drifting into one by accident is
not. Whatever is chosen belongs in ADR-067 alongside the tooling change (step 7).

### The contract `audit_dependencies.sh` provides today

Four review rounds on this doc each found a different guarantee the migration would have
dropped. The pattern is the giveaway: a list of *steps* invites omissions, so here is the
list of *properties* instead, read off all 39 lines of the script. Replacing it means
preserving each one or dropping it deliberately — and this table is short enough to check
against the file.

| Guarantee | How it is provided today | On osv-scanner |
|---|---|---|
| **The lock matches the manifest** | `uv export --locked` refuses a `uv.lock` behind `pyproject.toml` | **Lost** — scanning `uv.lock` directly happily audits a stale resolution and reports clean for dependencies that are not the ones that would be installed. Re-add with `uv lock --check` before scanning (verified present in uv 0.10.9) |
| **Dev groups are audited** | `--all-groups`; dev deps run on developer machines and CI, so they count | Confirm osv-scanner reads all groups from `uv.lock`, not just the default group |
| **The LOCK is audited, not the live venv** | exports from `uv.lock`, never from the installed environment | Native — it reads the lockfile |
| **Unauditable deps fail, not warn** | `--strict` | Unknown (§ 4) |
| **OSV, not the PyPI feed** | `--vulnerability-service osv`, chosen deliberately | Native |
| **Accepted findings, with reasons** | `.pip-audit-ignore` | `[[IgnoredVulns]]`, and better — it has `ignoreUntil` |
| **Severity threshold** | none for Python; moderate+ for JS elsewhere | Unknown (above) |

The first row is the one with teeth, and it is the same defect class as the `uv sync`
finding in #931: an audit that measures a resolution which is not the real one produces a
clean result that means nothing.

---

## 5. Migration sketch

Do these in order. Step 1 is the decision point — if it does not come out clean, stop.

1. **Prove parity before changing anything.** Run both scanners over the same commit with
   ignores disabled, and diff the finding sets:
   - `bash scripts/audit_dependencies.sh` with `.pip-audit-ignore` temporarily empty
   - `osv-scanner --lockfile=uv.lock` with no config
   Any ID pip-audit reports that osv-scanner does not is a coverage regression and must be
   explained before proceeding. Do the same for `package-lock.json` against `npm audit`,
   using the pre-#929 lockfile (`git show 4041a0025:app/package-lock.json`) as a **positive
   control** — it carries 5 known undici advisories, so a scanner that reports nothing there
   is broken, not clean.

   **Diff at matching severity thresholds** (§ 4), or the JS comparison is meaningless:
   `npm audit` is filtered to moderate-or-higher and osv-scanner may not be, so every
   low-severity finding would show up as a spurious "new" result and drown the real signal.
2. **Establish the unauditable-package behaviour AND whether a minimum severity can be
   expressed** (§ 4), each with a deliberately constructed case. If there is no `--strict`
   equivalent, or no way to hold the JS threshold at moderate, those are findings worth
   recording here — either may be a reason not to migrate.
3. Port `.pip-audit-ignore` → `osv-scanner.toml`, giving every entry a `reason` and an
   `ignoreUntil`.
4. Rewrite `scripts/audit_dependencies.sh` to invoke osv-scanner over both lockfiles; keep
   the script as the ONE path so CI and `./dev audit-deps` cannot diverge. **Walk the
   contract table in § 4 line by line** and preserve or consciously drop each row — the
   lock-freshness assertion (`uv lock --check`) is the one that silently produces a
   meaningless clean result if forgotten.

   **Every call site must move together.** Two review rounds on this doc each found a
   consumer the sketch had missed, so here is the full list rather than a third guess —
   re-derive it before starting, because it will have drifted:

   ```bash
   grep -rn "npm.*audit\|audit_dependencies\.sh" \
     app/dev app/scripts/ .github/workflows/ --include="*.py" --include="*.sh" --include="*.yml"
   ```

   | Call site | Invokes | Note |
   |---|---|---|
   | `app/dev:83` (`./dev audit-deps`) | the script | |
   | `.github/workflows/ci.yml:310` (`pip_audit`) | the script | **required check** — see step 5 |
   | `.github/workflows/dependency-audit.yml:155` (`python_audit`) | the script | |
   | `.github/workflows/dependency-audit.yml:289,294` (`js_audit`) | `npm audit` **directly** | must move to the script |
   | `app/scripts/run_quality_checks.py:173` (`./dev quality` check 8) | `npm audit` **directly** | must move to the script |

   The last two matter most: they bypass the shared script today, so leaving them alone
   would mean an advisory accepted in `osv-scanner.toml` still fails `./dev quality` and
   the scheduled JS audit — defeating both the accept mechanism that motivates this
   migration (§ 2.4) and the single-path property that makes findings agree everywhere.
5. **Migrate the REQUIRED CI job in the same change — this is the step that bites.**
   `ci.yml`'s `pip_audit` job runs that same script, so step 4 changes it too. Verified
   2026-08-03, it needs three edits or it breaks:
   - **Install the binary.** The job sets up only Python + uv, so the moment the script
     needs `osv-scanner` it fails on *every* matching PR — and it is a **required** check
     feeding the `gate` job, so that blocks all merges.
   - **Widen the path filters.** The job triggers on `py || audit`; neither filter mentions
     `app/package-lock.json` (checked). Once one script scans both lockfiles, a JS-only
     lock change would silently skip the consolidated check — the same diff-gating blind
     spot that produced `dependency-audit.yml` in the first place. Add `package-lock.json`,
     `package.json` and `osv-scanner.toml` to the `audit` filter.
   - **Rename it.** "Dependency CVE Audit" is fine; the job id `pip_audit` and the
     `.pip-audit-ignore` reference in `.github/workflows/README.md` are not.
6. Collapse `dependency-audit.yml` to a single job, and update its header — the
   asymmetry it documents (JS can prove it measured, Python cannot) stops being true.
7. Update ADR-067 § 5 and § 6e, and close the accept-mechanism decision in
   `js-dependency-surface.md`.

   **Then sweep every remaining reference — do not work from this list, re-derive it.**
   The tool names appear in help text, workflow docs and contributor guidance, not just
   policy docs. Run from the **repository root** (80 hits today):

   ```bash
   grep -rn "pip-audit\|pip_audit\|npm audit" \
     app/dev app/scripts app/CLAUDE.md app/docs/guides app/docs/decisions \
     app/docs/development .github \
     --include="*.md" --include="*.yml" --include="*.py" --include="*.sh" --include="dev"
   ```

   `.github` is in that list deliberately: `.github/workflows/README.md` alone carries 10
   descriptions of the old paths, and an earlier draft of this sweep omitted it — the sweep
   is itself a thing that can be silently incomplete. A whole-repo `grep -rn` instead
   returns ~567 hits, mostly historical prose in roadmap and arc docs, which is why the
   scope is the surfaces that *instruct* rather than every mention.

   Four checks that the sweep is working: `.github/workflows/README.md` (10),
   `app/dev:82,281` describing `./dev audit-deps` as pip-audit in user-facing help,
   `app/CLAUDE.md:613`, and `docs/guides/LINTER_GUIDE.md:53` — the last two both state that
   quality check 8 runs `npm audit --audit-level=moderate`. Leaving these pointed at removed
   paths sends contributors to scanners and semantics that no longer exist, which is the
   same documentation-drift failure ADR-067 § 5 had to be corrected for.
8. Drop `pip-audit` from `pyproject.toml`; confirm `pip` has left the lock.

---

## 6. When to do it

No urgency — nothing is broken, and pip-audit is PyPA-official and working. The natural
triggers:

- **Wanting the dependency audit to be a required check.** This is the unblocker; do this
  first or that conversation stalls on § 6e.
- Any further work on `dependency-audit.yml` that would deepen the two-job split.
- A JS advisory landing with no upstream fix — at which point the missing accept mechanism
  stops being theoretical and blocks `./dev quality` outright.

**Non-goal:** this is deliberately not folded into the PR that introduced
`dependency-audit.yml` (#931). That PR builds the scheduled audit on the tools we have;
this one changes what those tools are.
