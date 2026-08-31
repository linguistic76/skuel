# GitHub Actions Workflows & PR Reviewers

This directory holds SKUEL's CI. It also documents the **two AI reviewers**
(Kodus and Codex) that run on PRs but are configured outside these YAMLs.

## Who runs on a PR

| Participant | What it is | Where configured | Posts | Trigger |
|---|---|---|---|---|
| **CI Gate** | Aggregator job in `ci.yml` | This repo | ✅ status check (**required**) | Every PR/push to `main` |
| **Type Check (MyPy + Pyright)** | Job in `ci.yml` | This repo | ✅ status check + PR comment on MyPy failure | When `app/**/*.py`, `pyproject.toml`, or `uv.lock` change — both zero-error baselines |
| **Lint** | Job in `ci.yml` | This repo | ✅ status check | When `app/**/*.py`, `pyproject.toml`, or `uv.lock` change — Ruff format + check, SKUEL architecture linter (strict), Cypher linter (errors), route-security audit, raw-headers audit, dead-code gate (`detect_bloat.py --check`), ShellCheck |
| **Dependency CVE Audit** | Job in `ci.yml` | This repo | ✅ status check | When `app/**/*.py`, `pyproject.toml`, either lockfile, or the audit tooling itself (`audit_dependencies.sh`, `osv-scanner.toml`) change — osv-scanner over BOTH locked ecosystems (`uv.lock` + `package-lock.json`, all severities; `scripts/audit_dependencies.sh`, same as `./dev audit-deps`); accepted findings documented in `app/osv-scanner.toml` with `ignoreUntil` expiries |
| **Integration Tests** | Job in `ci.yml` | This repo | ✅ status check | When `app/**/*.py`, `pyproject.toml`, or `uv.lock` change — `tests/integration/` against a Neo4j testcontainer (the runner's Docker daemon); the only tier that executes real Cypher |
| **Render Smoke Test** | Job in `ci.yml` | This repo | ✅ status check | When `app/static/**`, `app/ui/**`, `app/**/*.py`, or deps change — renders unauthenticated pages in headless Chrome and fails if any never reaches idle (infinite JS loop / render hang) |
| **Validate Documentation** | Job in `ci.yml` | This repo | ✅ status check + PR comment | When `app/docs/**`, `app/.claude/skills/**`, or the docs scripts change |
| **JS Tests** | Job in `ci.yml` | This repo | ✅ status check | When `app/static/js/**`, `app/tests/js/**`, `package*.json`, or `vitest.config.js` change — vitest (jsdom) over `static/js/`, same as `./dev test-js` locally |
| **Generate Metrics** | Job in `ci.yml` | This repo | ✅ status check (skipped on PRs) | Push to `main` only |
| **Kody** (`kody-ai[bot]`) | Kodus AI code review | **`kodus-config.yml`** (repo root) + app.kodus.io | ✅ "Code Review Skipped" check when not summoned; "Code Review Completed" check (conclusion `success`) **+ a PR review only on findings** (CHANGES_REQUESTED) when summoned — a clean run posts NO review object; the check-run success is its verdict signal | **On-demand only** — `@kody start-review` (auto-review toggle OFF, 2026-05-25). The dashboard toggle is the real switch; repo `automatedReviewActive: false` alone neither enables nor stops it. |
| **Codex Auto-Review** | Job in `codex-review.yml` | This repo | Posts the `@codex review` comment (no status check) | ⏸️ **DISABLED** — comment-bot trigger off (cosmetic-only: a bot-posted `@codex review` draws only the "create a Codex account" prompt; see below) |
| **Codex** (`chatgpt-codex-connector[bot]`) | OpenAI Codex AI review | **`AGENTS.md`** (repo root) + dashboard | ⚠️ **PR reviews only — NOT a status check** | **On-demand only** — manual `@codex review` from a human account (auto-review OFF, 2026-05-25: dashboard "Personal auto review preferences" off + repo "Follow personal preferences") |
| **Codex Review Gate** | `codex-gate.yml` (commit status) | This repo | ✅ status check (**required**) | **Two-tier:** (1) **Python files changed** → RED until `codex-considered` label applied, regardless of whether `@codex review` was posted; (2) **docs/tooling only** → RED only when a human posted `@codex review` and it isn't yet considered. Cleared on new commits. See below. |
| **Strip Codex Footer** | `strip-codex-footer.yml` | This repo | Nothing — edits Codex's own summary comments in place (no status check) | Every PR comment authored by `chatgpt-codex-connector[bot]` — removes the boilerplate "About Codex in GitHub" `<details>` footer. See below. |

### ⚠️ Codex does not appear in `gh pr checks`

This is by design — the Codex connector posts **PR reviews/comments**, never a
status check. Its verdict may land as a *review* or as an **issue comment**
depending on how it was invoked, so a verdict check must scan **both**. Open the
PR's **Files changed / Conversation** tabs, or run:

```bash
gh pr view <PR#> --json reviews,comments \
  -q '(.reviews[], .comments[]) | select(.author.login|test("codex|kody";"i")) | "\(.author.login)\t\(.state // "comment")\t\(.submittedAt // .createdAt)"'
```

To confirm which GitHub App owns each *check*:

```bash
SHA=$(gh pr view <PR#> --json headRefOid -q .headRefOid)
gh api repos/linguistic76/skuel/commits/$SHA/check-runs -q '.check_runs[] | "\(.name)\tapp=\(.app.slug)"'
```

## `ci.yml`

One workflow, path-guarded jobs, one always-on gate.

```
changes ──┬─▶ mypy (if app py changed) ─────────────┐
          ├─▶ lint (if app py changed) ──────────────┤
          ├─▶ dep_audit (if py or audit changed) ────┤
          ├─▶ unit_tests (if app py changed) ────────┤
          ├─▶ integration_tests (if app py changed) ─┤
          ├─▶ smoke (if py OR ui/static changed) ────┤
          └─▶ validate_documentation (if docs) ──────┤
                                                      ▼
documentation_metrics (push to main only)         gate ── "CI Gate" (required)
```

- **`changes`** uses `dorny/paths-filter` to decide what ran.
- **`mypy` / `lint` / `dep_audit` / `unit_tests` / `integration_tests` / `smoke` /
  `validate_documentation` / `js_tests`** run only
  when their paths changed, so they're skipped (not failed) on unrelated PRs.
- **`lint`** runs the mechanical rule set `./dev quality` runs locally, minus
  the type checkers (their own job) and checks owned by other jobs:
  `ruff format --check`, `ruff check`, `lint_skuel.py --strict`,
  `cypher_linter.py --errors-only --strict`, `audit_route_security.py`,
  `audit_raw_headers.py`, `detect_bloat.py --check`, and
  `shellcheck_tracked.py`. Steps keep running after one fails so a single CI
  run surfaces every violation category.
  `app/tests/unit/scripts/test_quality_ci_parity.py` fails when a
  `./dev quality` check has no CI home — extend both sides together.
- **`dep_audit`** audits BOTH locked ecosystems (`uv.lock` all groups +
  `package-lock.json`, all severities) against the OSV database via
  `scripts/audit_dependencies.sh` (osv-scanner; binary pin + checksum in
  `.github/actions/install-osv-scanner`) — the same path as `./dev audit-deps`
  and `./dev quality` check 8. Accepted findings live in `app/osv-scanner.toml`,
  each with a documented reason and an `ignoreUntil` expiry (ADR-067 § 6e).
- **`integration_tests`** runs `tests/integration/` — testcontainers boots the
  pinned Neo4j image on the runner's Docker daemon, same as `./dev test-integration`
  locally. This is the only tier that executes real Cypher (unit tests mock the
  driver), so it gates persistence regressions that `unit_tests` cannot see.
- **`smoke`** renders the unauthenticated pages and loads them in headless Chrome,
  failing if any never reaches idle (catches client-side render hangs / infinite
  JS loops that unit tests can't see). No server or Neo4j needed.
- **`js_tests`** runs the vitest suite over `static/js/` (`npm run test:js`,
  same as `./dev test-js`). Path-filtered like `cypher`: a JS-only PR skips
  every py-gated job but must still exercise the JS under test.
- **`gate` ("CI Gate")** always runs and passes only when every required job's
  result is `success` or `skipped`; any other value fails, naming the job and
  the literal result. An allow-list, deliberately: the old deny-list over
  `failure`/`cancelled` admitted the undocumented result `abandoned` during the
  2026-08-06 Actions outage and greenlighted a PR with every test job skipped
  (PR #967). Exercised by `app/tests/unit/test_ci_gate_result_allowlist.py`,
  which runs the shipped step under substituted results. **It is the single
  required status check** — required checks must report on every PR, and a
  path-filtered job alone would deadlock a PR it doesn't run on.

### Run the checks locally

```bash
cd app
uv run mypy .                                  # MyPy check
./dev lint                                     # Ruff + SKUEL linter (the CI Lint job's core)
./dev audit-deps                               # Dependency CVE audit (the CI dep_audit job)
uv run python scripts/docs_freshness.py --critical-only
uv run python scripts/skills_validator.py
./dev quality                                  # full suite — every check here also has a CI home (parity-tested)
```

## Scheduled workflows (no PR trigger, not status checks)

Three workflows run on a clock instead of on a diff. None feeds the `gate` job, so none can
block a merge — all are advisory, and all **file an issue** on failure, because a red scheduled
run that lands nowhere is indistinguishable from no check at all.

| Workflow | Cadence | What it does | On failure |
|---|---|---|---|
| `mypy-suppressions.yml` | Mondays 06:00 UTC | Finds mypy suppressions that suppress nothing (`scripts/health/mypy_suppressions.py`, `./dev health-mypy`) | Opens/comments on a marker-keyed issue; fails the run |
| `weekly-janitor.yml` | Mondays 06:30 UTC | Runs the `./dev health` checks (dead modules, dead doc links, stale names, duplicate headings, cross-references) plus the full advisory bloat report (`detect_bloat.py`, no `--check`) with its PLANNED-tier aging summary | Fails the job on health-check findings or an aborted bloat run (bloat *findings* never fail it — the WARNING tier already gates PRs via `--check`), and maintains **one always-open status issue** (same `file-audit-issue` action as the dependency audit). Issues are written only on default-branch runs |
| `dependency-audit.yml` | Daily 07:00 UTC | Runs the consolidated CVE audit — osv-scanner over `app/uv.lock` + `app/package-lock.json` via `scripts/audit_dependencies.sh` (same script as the required `dep_audit` job) | Fails the job, and maintains **one always-open status issue** whose body is the current state (clean, findings, or could-not-measure — the script's three-state exit contract). Comments only when the reported content **changes**, so an unchanged result is silent. Issues are written only on default-branch runs |

**Why a schedule rather than a PR check.** Both watch for things that change without a diff. An
advisory is published against a lockfile nobody touched; a suppression goes dead when *source* is
fixed, with the config untouched. Path-filtered PR jobs cannot see either. `undici` 7.28.0 sat in
`app/package-lock.json` accruing five high advisories with zero file changes and surfaced only
because a developer ran `./dev quality` by hand (PR #929).

**Why `dependency-audit.yml` is not a required check.** A cron run has no PR to gate — this
workflow is the diff-independent backstop for advisories published against untouched lockfiles.
The PR-side gate is `dep_audit` in `ci.yml` (required, same script). The historical blocker —
`npm audit` having no per-advisory accept mechanism — was retired with npm audit itself:
`app/osv-scanner.toml` accepts findings for both ecosystems with reasons + `ignoreUntil` expiries
(ADR-067 § 6e).

Run any of them locally: `./dev health-mypy`, `./dev health` + `./dev bloat`, and `./dev audit-deps`.

## `codex-review.yml`

> ⏸️ **This comment-bot stays DISABLED, and Codex cloud auto-review is also OFF
> (2026-05-25) — so Codex reviews only on a human `@codex review`.** Two separate
> things: (1) **This comment-bot trigger** is off: when `@codex review` is posted by
> `github-actions[bot]`, Codex replies with only the cosmetic "create a Codex
> account" line and no real review (a bot-posted comment isn't attributed to the
> connected account), so its `pull_request:` trigger is commented out. (2) Codex
> **cloud auto-review** (the dashboard feature) is **OFF**: at
> `chatgpt.com/codex/cloud/settings/code-review` "Personal auto review preferences"
> is off and `linguistic76/skuel`'s "Auto code review" = **"Follow personal
> preferences"** (→ off). (It was briefly auto-ON on a paid plan earlier on
> 2026-05-25, then turned off to consolidate both reviewers to on-demand.) **To turn
> Codex auto-review back on,** enable the personal toggle or set the repo's "Auto code
> review" to "Review my PRs".

Historical note (why this workflow exists): across PRs #1–#10 Codex's cloud
auto-review fired on only **3**, and **6 merged with no Codex review at all** — so
this workflow was added to post `@codex review` automatically. That turned out
**not** to yield real reviews: a comment posted by `github-actions[bot]` only
draws Codex's cosmetic "create a Codex account" reply, not a substantive review
(confirmed across PRs #12–#15). Hence the trigger is now commented out. Kept for
re-enablement only.

The bullets below describe the workflow **as it would behave if re-enabled** — the
`pull_request:` trigger is commented out, so none of it runs today:

- Would trigger on `opened` / `reopened` / `ready_for_review` / `synchronize`.
- A `sleep 30` + per-PR `concurrency: cancel-in-progress` debounces bursts — a
  flurry of pushes collapses to one trigger.
- Job guard `if: github.event_name == 'pull_request' && …draft == false` — runs
  only on real PR events (skips drafts) and **no-ops on the manual
  `workflow_dispatch`**, which has no PR/issue context.
- Uses the built-in `GITHUB_TOKEN` with `pull-requests: write` — enough to
  **post** the comment (the `issues.createComment` call worked on PR #11), but
  not enough to **get a review** (next bullet). So "no PAT needed" is true only
  of posting; a re-enable that actually produces reviews does need one.
- A bot-authored `@codex review` (this workflow's `GITHUB_TOKEN` →
  `github-actions[bot]`) yields ONLY Codex's cosmetic "create a Codex account"
  line and **no real review** — a bot comment isn't attributed to the connected
  account. That's why the trigger stays disabled; a *human*-authored
  `@codex review` is the working path (see next section).

## Manually requesting a Codex review (the reliable recipe)

Codex auto-review is **off**, so a manual `@codex review` is now the **only** way to
get a Codex review (and the way to re-review after pushing more commits). What makes
the manual call reliable is **who authors the comment**: a bot (`github-actions[bot]`) draws only
the cosmetic "create a Codex account" reply, while the **connected human account**
(`linguistic76`) gets a real review. The `gh` CLI posts as your authenticated
account, so the dependable trigger — equivalent to posting it in the web UI — is:

```bash
gh pr comment <PR#> --body "@codex review"   # authored as linguistic76 (a User) → real review
```

Verified on **PR #43** (2026-05-25): Codex replied with a substantive verdict
plus the connected-account "About Codex" footer (not the cosmetic prompt).
**Reading the result:** a substantive verdict — findings, or "Didn't find any
major issues" — means it worked; a "create a Codex account / connect to github"
reply with no verdict means it's off, disconnected, or weekly-usage-limited.
(Codex also appends an "About Codex in GitHub" footer to every summary, but
`strip-codex-footer.yml` removes it moments after posting — so don't read the
footer's *absence* as the cosmetic-reply failure mode; the verdict is the signal.
The original footer stays visible in the comment's edit history.)

> ⚠️ **That footer is not a statement of this repo's configuration.** It lists
> "Open a pull request for review" among the triggers on *every* Codex summary —
> identical boilerplate whatever the account's auto-review setting is (which is
> why `strip-codex-footer.yml` deletes it). Read it as "Codex supports these
> triggers", not "these triggers are enabled here". The repo's own behaviour is
> the authority, and it says otherwise: across #949,
> #957, #959, #960, #961 and #962, **no Codex review has ever appeared on PR
> open** — every one followed a human `@codex review` by 2–5 minutes. #962 is a
> clean control: opened with all checks running, it drew nothing until summoned.
> Mistaking a capability list for a configuration is how the `codex-review.yml`
> header went stale for ~2.5 months.

Optional — confirm the trigger comment was authored by a **User**, not a bot
(the whole reliability hinge):

```bash
gh pr view <PR#> --json comments \
  -q '[.comments[]|select(.body|test("@codex review"))]|last|.author.login'
# want: linguistic76 (a User account) — NOT github-actions[bot] (cosmetic-only)
```

## Codex Review Gate (`codex-gate.yml`) — mandatory on Python PRs, on-request for docs/tooling

Codex posts reviews/comments but **never a status check**, so it can't itself be
required in branch protection. `codex-gate.yml` bridges that with the required
status **`Codex Review Gate`**, operating in **two tiers**:

**Tier 1 — Python files changed (app code):**
- Gate is 🔴 **RED** immediately when the PR opens, regardless of whether `@codex review`
  was posted.
- Clears to 🟢 **GREEN** only when the **`codex-considered`** label is applied.
- Run `app/scripts/request_codex_review.sh <PR#>` to summon Codex and wait for its verdict.

**Tier 2 — Docs/tooling only (no `.py` files):**
- A PR with **no `@codex review` request** → 🟢 **GREEN automatically** (no friction).
- Once a **human posts `@codex review`** → 🔴 **RED** until `codex-considered` is applied.

**Both tiers:** A **new commit (`synchronize`) auto-removes the label**, so changed
code must be re-considered.

> ⚠️ **Label race:** workflow runs are queued, not instant — a gate run still in
> flight from the **last push** strips the label even when the label was applied
> *after* that push (observed live on #584). Apply the label with
> **`app/scripts/apply_codex_considered.sh <PR#>`**, which waits for in-flight gate
> runs on the head SHA to drain, applies the label, and polls the `Codex Review
> Gate` commit status until it actually reports green (re-adding once if
> stripped). If labeling by hand, re-check the label + gate status immediately
> before merging.

(Codex auto-review is off, so there are no ambient auto-reviews. If you ever re-enable
dashboard auto-review, those auto-reviews stay advisory and **do not gate** — only an
explicit `@codex review` does.)

**Codex is advisory** — the gate requires the requested review was *considered*,
never that it was *agreed with*. Claude (the LLM) arbitrates what's actually true.
To gate a PR on Codex and clear it:

1. `gh pr comment <PR#> --body "@codex review"` (as your account → a real review).
2. Read the review; post a short **"Codex consideration"** comment — what you
   accept / reject and why.
3. Apply the label race-safely: `app/scripts/apply_codex_considered.sh <PR#>`
   (waits out in-flight gate runs and confirms the gate goes green; plain
   `gh pr edit <PR#> --add-label codex-considered` can be silently race-stripped
   by a gate run queued from the last push).

The label is the auditable record that steps 1–2 happened. **Implementation note:**
the gate is a **commit status** (not a job check-run) so the `issue_comment`
trigger can update it on the PR head SHA — an issue_comment check-run wouldn't
attach to the PR commit, but a posted status does. **Caveat:** `main` keeps
admin-bypass (`enforce_admins=false`), so a RED gate is a strong, visible signal +
audit trail, not an unbreakable lock — fitting "truth rests with Claude, who clears
it." Set `enforce_admins=true` for a hard lock (also blocks legitimate bypasses,
e.g. a Kody billing failure).

## `strip-codex-footer.yml` — de-boilerplate Codex summaries

Every Codex review summary ends with the same collapsed `<details>` block
("Your team has set up Codex to review pull requests in this repo… Reviews are
triggered when you …") — byte-identical on every summary regardless of the
account's settings, with no OpenAI toggle to disable it. Collapsed for humans,
but ~700 chars of repeated noise for every agent reading PR conversations via
the API. This workflow fires on each PR comment authored by
`chatgpt-codex-connector[bot]` and edits the comment in place, removing just
that block.

What it deliberately leaves alone: the verdict line (the clean-signature grep
in `request_codex_review.sh` reads it), the `**Reviewed commit:**` line, and
inline review comments (their one-line "Useful? React with 👍 / 👎." footer).
It cannot loop: it triggers on `created` only, and a stripped comment no longer
contains the marker. It cannot affect the Codex Review Gate: `codex-gate.yml`
scans only *human*-authored comments for `@codex review` (bot comments are
excluded there precisely because this footer contains that literal string).
The pre-edit body remains in the comment's edit-history dropdown.

## Verifying / re-enabling a reviewer

To confirm a reviewer actually runs — after re-enabling Codex, changing config,
or any "is it working?" doubt — open a throwaway PR, read what the reviewer posts,
then close it. A verdict can be a *review* or an *issue comment*, so scan both.

```bash
# 1. Throwaway PR with a trivial diff
git checkout -b test/reviewer-check main
echo "scratch" > SCRATCH_REVIEW_TEST.md && git add SCRATCH_REVIEW_TEST.md
git commit -m "test: reviewer connectivity check (throwaway)"
git push -u origin test/reviewer-check
gh pr create --base main --head test/reviewer-check \
  --title "test: reviewer connectivity (throwaway — will be closed)" \
  --body "Throwaway. Will be closed; do not merge."

# 2. After ~1-2 min, read what Kody / Codex posted (reviews AND comments)
gh pr view <PR#> --json reviews,comments \
  -q '(.reviews[], .comments[]) | select((.author.login//"")|test("codex|kody|kodus";"i")) | "[\(.author.login)] \(.state // "comment"): \(.body | split("\n")[0])"'

# 3. Clean up — the PR never merges
gh pr close <PR#> --delete-branch
```

Reading the result: a Codex "create a Codex account / connect to github" reply
with **no substantive review following** means it's off, usage-limited, or
disconnected — not live. A real review (or Kody's "Code Review Complete") means
it's working.

## Branch protection (`main`)

Classic protection: **require a PR + two green checks ("CI Gate" and "Codex
Review Gate"); no human approval required; admins can bypass.** As of 2026-05-25
**neither AI reviewer auto-runs** — both are on-demand (`@codex review` /
`@kody start-review`), and **CI Gate is the only automatic gate**. Codex posts no
status check of its own; the required **`Codex Review Gate`** (see above) passes
automatically unless someone posts `@codex review`, in which case it stays red until
that review is considered (`codex-considered` label). Kody runs in request-changes
mode, so a Kody `CHANGES_REQUESTED` holds the merge when summoned.

```bash
gh api -X PUT repos/linguistic76/skuel/branches/main/protection \
  -f 'required_status_checks[strict]=true' \
  -f 'required_status_checks[contexts][]=CI Gate' \
  -f 'required_status_checks[contexts][]=Codex Review Gate' \
  -f 'required_pull_request_reviews[required_approving_review_count]=0' \
  -F 'enforce_admins=false' \
  -F 'restrictions=null'
```

## One-time dashboard steps (cannot live in the repo)

- **Codex:** auto-review is **OFF** (2026-05-25). At
  `chatgpt.com/codex/cloud/settings/code-review`: the "Personal auto review preferences"
  toggle is **off**, and `linguistic76/skuel`'s "Auto code review" = **"Follow personal
  preferences"** (→ off). (The "Personal Review Trigger Preference" dropdown only picks
  *when* auto-review fires — On PR open / On every push / Smart Trigger — it has **no
  "off" option**, so it is *not* the switch; the personal toggle + per-repo setting are.)
  Codex therefore reviews **only** on a manual `@codex review` (from a human account).
  The in-repo comment-bot (`codex-review.yml`) stays disabled — a bot-posted
  `@codex review` is cosmetic-only. To turn auto-review back on, enable the personal
  toggle or set the repo's "Auto code review" to "Review my PRs". (It was briefly
  auto-ON on a paid plan earlier on 2026-05-25.)
- **Kodus:** two dashboard steps at `app.kodus.io`:
  1. ensure a **BYOK** LLM key is configured (Kody can't review without it);
  2. **auto-review is OFF** (2026-05-25) via the **"enable automatic code review"**
     toggle in the Code Review settings (Mike-controlled — flip it back on to restore
     auto-review; off = **on-demand only**, `@kody start-review`). ⚠️ The dashboard
     toggle is the real switch: the repo `kodus-config.yml`'s `automatedReviewActive:
     false` did **not** stop auto-review on its own (verified 2026-05-24) —
     dashboard-only, exactly like Codex. When OFF, pushes show a "Code Review Skipped"
     check.
  `kodus-config.yml` still governs the rest (review lenses, severity, summary,
  request-changes mode).
