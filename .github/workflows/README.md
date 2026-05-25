# GitHub Actions Workflows & PR Reviewers

This directory holds SKUEL's CI. It also documents the **two AI reviewers**
(Kodus and Codex) that run on PRs but are configured outside these YAMLs.

## Who runs on a PR

| Participant | What it is | Where configured | Posts | Trigger |
|---|---|---|---|---|
| **CI Gate** | Aggregator job in `ci.yml` | This repo | ✅ status check (**required**) | Every PR/push to `main` |
| **MyPy Type Check** | Job in `ci.yml` | This repo | ✅ status check + PR comment on failure | When `app/**/*.py`, `pyproject.toml`, or `uv.lock` change |
| **Validate Documentation** | Job in `ci.yml` | This repo | ✅ status check + PR comment | When `app/docs/**`, `app/.claude/skills/**`, or the docs scripts change |
| **Generate Metrics** | Job in `ci.yml` | This repo | ✅ status check (skipped on PRs) | Push to `main` only |
| **Kody** (`kody-ai[bot]`) | Kodus AI code review | **`kodus-config.yml`** (repo root) + app.kodus.io | ✅ "Code Review Completed" check **+ PR reviews** (CHANGES_REQUESTED on findings) | **Auto-review ON** (app.kodus.io dashboard toggle — Mike-controlled) **+** `@kody start-review`. The dashboard toggle is the real switch; repo `automatedReviewActive: false` alone does not stop it. |
| **Codex Auto-Review** | Job in `codex-review.yml` | This repo | Posts the `@codex review` comment (no status check) | ⏸️ **DISABLED** — comment-bot trigger off (cosmetic-only; now also redundant — dashboard auto-review covers it; see below) |
| **Codex** (`chatgpt-codex-connector[bot]`) | OpenAI Codex AI review | **`AGENTS.md`** (repo root) + dashboard | ⚠️ **PR reviews only — NOT a status check** | **Auto-reviews PRs you open** (dashboard 2026-05-25: "On PR open" + repo "Review my PRs"; needs a paid ChatGPT plan) **+** manual `@codex review` (re-review after pushes) |
| **Codex Review Gate** | `codex-gate.yml` (commit status) | This repo | ✅ status check (**required**) | **Scoped to on-request:** RED only when a human posted `@codex review` and it isn't yet considered (`codex-considered` label); PRs with no request pass automatically. Cleared on new commits. See below. |

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
          └─▶ validate_documentation (if docs) ─────┤
                                                     ▼
documentation_metrics (push to main only)         gate ── "CI Gate" (required)
```

- **`changes`** uses `dorny/paths-filter` to decide what ran.
- **`mypy` / `validate_documentation`** run only when their paths changed, so
  they're skipped (not failed) on unrelated PRs.
- **`gate` ("CI Gate")** always runs and passes when required jobs succeeded or
  were skipped; fails only on a real failure/cancellation. **It is the single
  required status check** — required checks must report on every PR, and a
  path-filtered job alone would deadlock a PR it doesn't run on.

### Run the checks locally

```bash
cd app
uv run mypy .                                  # MyPy check
uv run python scripts/docs_freshness.py --critical-only
uv run python scripts/skills_validator.py
./dev quality                                  # full suite (ruff + SKUEL linter + cypher + mypy)
```

## `codex-review.yml`

> ⏸️ **This comment-bot stays DISABLED — but Codex cloud auto-review is now ON
> via the dashboard (2026-05-25), so this bot is redundant.** Two separate things:
> (1) **This comment-bot trigger** is off: when `@codex review` is posted by
> `github-actions[bot]`, Codex replies with only the cosmetic "create a Codex
> account" line and no real review (a bot-posted comment isn't attributed to the
> connected account), so its `pull_request:` trigger is commented out. (2) Codex
> **cloud auto-review** (the dashboard feature) is now **ON**: at
> `chatgpt.com/codex/cloud/settings/code-review` the "Personal Review Trigger
> Preference" = **"On PR open"** and `linguistic76/skuel`'s "Auto code review" =
> **"Review my PRs"**, so Codex auto-reviews every PR you open. (A paid ChatGPT
> plan unlocked this — it was unreliable/off on the free tier.) Kody + CI Gate
> remain the gate; Codex is advisory. **To stop Codex auto-review,** change the
> dashboard trigger preference back / set the repo to a non-auto option.

Historical note (why this workflow exists): across PRs #1–#10 Codex's cloud
auto-review fired on only **3**, and **6 merged with no Codex review at all** — so
this workflow was added to post `@codex review` automatically. That turned out
**not** to yield real reviews: a comment posted by `github-actions[bot]` only
draws Codex's cosmetic "create a Codex account" reply, not a substantive review
(confirmed across PRs #12–#15). Hence the trigger is now commented out. Kept for
re-enablement only.

- Triggers on `opened` / `reopened` / `ready_for_review` / `synchronize`.
- A `sleep 30` + per-PR `concurrency: cancel-in-progress` debounces bursts — a
  flurry of pushes collapses to one trigger.
- Job guard `if: github.event_name == 'pull_request' && …draft == false` — runs
  only on real PR events (skips drafts) and **no-ops on the manual
  `workflow_dispatch`**, which has no PR/issue context.
- Uses the built-in `GITHUB_TOKEN` with `pull-requests: write` (sufficient for
  the `issues.createComment` call — proven on PR #11; no PAT needed).
- A bot-authored `@codex review` (this workflow's `GITHUB_TOKEN` →
  `github-actions[bot]`) yields ONLY Codex's cosmetic "create a Codex account"
  line and **no real review** — a bot comment isn't attributed to the connected
  account. That's why the trigger stays disabled; a *human*-authored
  `@codex review` is the working path (see next section).

## Manually requesting a Codex review (the reliable recipe)

Codex **auto-reviews PRs you open** (dashboard, see below), and you can also
request a review **manually anytime** with `@codex review` — the path for a
**re-review after you push more commits** (the dashboard trigger is "On PR open",
not per-push) or if the auto-review didn't fire. What makes the manual call
reliable is **who authors the comment**: a bot (`github-actions[bot]`) draws only
the cosmetic "create a Codex account" reply, while the **connected human account**
(`linguistic76`) gets a real review. The `gh` CLI posts as your authenticated
account, so the dependable trigger — equivalent to posting it in the web UI — is:

```bash
gh pr comment <PR#> --body "@codex review"   # authored as linguistic76 (a User) → real review
```

Verified on **PR #43** (2026-05-25): Codex replied with a substantive verdict
plus the connected-account "About Codex" footer (not the cosmetic prompt).
**Reading the result:** a verdict + the "Your team has set up Codex to review…"
footer means it worked; a "create a Codex account / connect to github" reply with
no verdict means it's off, disconnected, or weekly-usage-limited.

Optional — confirm the trigger comment was authored by a **User**, not a bot
(the whole reliability hinge):

```bash
gh pr view <PR#> --json comments \
  -q '[.comments[]|select(.body|test("@codex review"))]|last|.author.login'
# want: linguistic76 (a User account) — NOT github-actions[bot] (cosmetic-only)
```

## Codex Review Gate (`codex-gate.yml`) — making "consider Codex" enforceable, on request

Codex posts reviews/comments but **never a status check**, so it can't itself be
required in branch protection. `codex-gate.yml` bridges that with the required
status **`Codex Review Gate`**, **scoped to explicit requests**:

- A PR with **no `@codex review` request** → 🟢 **GREEN automatically** (gate not
  applicable; no friction on routine PRs).
- Once a **human posts `@codex review`** → 🔴 **RED** until the PR carries the
  **`codex-considered`** label → 🟢 **GREEN** when it does.
- A **new commit (`synchronize`) auto-removes the label**, so changed code must be
  re-considered.

(Codex may still **auto-review** every PR via the dashboard "On PR open" setting;
those auto-reviews are advisory FYI and **do not gate** — only an explicit
`@codex review` does. Turn the dashboard trigger off if you don't want the ambient
auto-reviews.)

**Codex is advisory** — the gate requires the requested review was *considered*,
never that it was *agreed with*. Claude (the LLM) arbitrates what's actually true.
To gate a PR on Codex and clear it:

1. `gh pr comment <PR#> --body "@codex review"` (as your account → a real review).
2. Read the review; post a short **"Codex consideration"** comment — what you
   accept / reject and why.
3. Apply the label: `gh pr edit <PR#> --add-label codex-considered`.

The label is the auditable record that steps 1–2 happened. **Implementation note:**
the gate is a **commit status** (not a job check-run) so the `issue_comment`
trigger can update it on the PR head SHA — an issue_comment check-run wouldn't
attach to the PR commit, but a posted status does. **Caveat:** `main` keeps
admin-bypass (`enforce_admins=false`), so a RED gate is a strong, visible signal +
audit trail, not an unbreakable lock — fitting "truth rests with Claude, who clears
it." Set `enforce_admins=true` for a hard lock (also blocks legitimate bypasses,
e.g. a Kody billing failure).

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
**both AI reviewers auto-run** on PRs you open (Codex via its dashboard "On PR
open"; Kody via its app.kodus.io toggle), and both are also summonable by comment
(`@codex review` / `@kody start-review`). Codex posts no status check of its own;
the required **`Codex Review Gate`** (see above) passes automatically unless someone
posts `@codex review`, in which case it stays red until that review is considered
(`codex-considered` label). Kody runs in request-changes mode, so a Kody
`CHANGES_REQUESTED` holds the merge too.

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

- **Codex:** auto-review is **ON** (2026-05-25, on a paid ChatGPT plan — it was
  unreliable/off on the free tier). At `chatgpt.com/codex/cloud/settings/code-review`:
  "Personal Review Trigger Preference" = **"On PR open"**, and `linguistic76/skuel`'s
  "Auto code review" = **"Review my PRs"** (runs on PRs you open). Exhaustive review
  and credits-use are off. Codex auto-reviews on PR open **and** responds to a manual
  `@codex review` (the re-review path, since the trigger is "On PR open", not
  per-push). The in-repo comment-bot (`codex-review.yml`) stays disabled — redundant
  with auto-review, and a bot-posted `@codex review` is cosmetic-only. To turn
  auto-review off, change the trigger preference / set the repo to a non-auto option.
- **Kodus:** two dashboard steps at `app.kodus.io`:
  1. ensure a **BYOK** LLM key is configured (Kody can't review without it);
  2. **auto-review is currently ON** via the **"enable automatic code review"**
     toggle in the Code Review settings (Mike-controlled — flip it off to make Kody
     **on-demand only**, `@kody start-review`). ⚠️ The dashboard toggle is the real
     switch: the repo `kodus-config.yml`'s `automatedReviewActive: false` did **not**
     stop auto-review on its own (verified 2026-05-24) — dashboard-only, exactly like
     Codex. When OFF, pushes show a "Code Review Skipped" check.
  `kodus-config.yml` still governs the rest (review lenses, severity, summary,
  request-changes mode).
