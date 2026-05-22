# GitHub Actions Workflows & PR Reviewers

This directory holds SKUEL's CI. It also documents the **two AI reviewers**
(Kodus and Codex) that run on PRs but are configured outside these YAMLs.

## Who runs on a PR

| Participant | What it is | Where configured | Posts | Trigger |
|---|---|---|---|---|
| **CI Gate** | Aggregator job in `ci.yml` | This repo | ✅ status check (the one required check) | Every PR/push to `main` |
| **MyPy Type Check** | Job in `ci.yml` | This repo | ✅ status check + PR comment on failure | When `app/**/*.py`, `pyproject.toml`, or `uv.lock` change |
| **Validate Documentation** | Job in `ci.yml` | This repo | ✅ status check + PR comment | When `app/docs/**`, `app/.claude/skills/**`, or the docs scripts change |
| **Generate Metrics** | Job in `ci.yml` | This repo | ✅ status check (skipped on PRs) | Push to `main` only |
| **Kody** (`kody-ai[bot]`) | Kodus AI code review | **`kodus-config.yml`** (repo root) + app.kodus.io | ✅ "Code Review Completed" check **+ PR reviews** (CHANGES_REQUESTED on findings) | On PR open + re-reviews each pushed commit; `@kody start-review` |
| **Codex Auto-Review** | Job in `codex-review.yml` | This repo | Posts the `@codex review` comment (no status check) | ⏸️ **DISABLED 2026-05-22** — comment-bot trigger off (cosmetic-only; see below) |
| **Codex** (`chatgpt-codex-connector[bot]`) | OpenAI Codex AI review | **`AGENTS.md`** (repo root) + dashboard | ⚠️ **PR reviews only — NOT a status check** | **Auto-review intentionally OFF** (dashboard); reviews only on a manual `@codex review`; comment-bot also disabled |

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

> ⏸️ **DISABLED 2026-05-22 — two things are off, for two reasons.** (1) This
> comment-bot trigger: when `@codex review` is posted by `github-actions[bot]`,
> Codex replies with only the cosmetic "create a Codex account" line and no real
> review (a bot-posted comment isn't attributed to the connected account), so it
> added noise without producing reviews — its `pull_request:` trigger is commented
> out. (2) Codex **cloud auto-review** (the dashboard feature) is **intentionally
> OFF**: at `chatgpt.com/codex/cloud/settings/code-review` the "Personal auto
> review preferences" toggle is off and `linguistic76/skuel` is set to "Follow
> personal preferences" (resolves to off); there's no per-repo hard-off, so the
> personal toggle is the switch. Codex now reviews **only** on a manual
> `@codex review`. **Why off:** cloud auto-review was always best-effort — it fired
> on ~1 of 4 PRs and draws from a weekly shared usage limit. Kody stays the gating
> reviewer and CI Gate is the required check, so Codex was never part of the gate.
> **Re-enable** Codex auto-review by flipping the dashboard toggle ON (or setting
> the repo to "Review all PRs"); re-enable this comment-bot by uncommenting its
> trigger in `codex-review.yml`. Verify either with the throwaway-PR test below.

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
- Skips drafts (`if: github.event.pull_request.draft == false`).
- Uses the built-in `GITHUB_TOKEN` with `pull-requests: write` (sufficient for
  the `issues.createComment` call — proven on PR #11; no PAT needed).
- Codex prepends a cosmetic "create a Codex account / connect to github" line
  because the trigger comes from a bot account; the actual review still follows.

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

Classic protection: **require a PR + a green "CI Gate"; no human approval
required; admins can bypass.** With Kody in request-changes mode, a Kody
`CHANGES_REQUESTED` holds the merge until resolved or dismissed.

```bash
gh api -X PUT repos/linguistic76/skuel/branches/main/protection \
  -f 'required_status_checks[strict]=true' \
  -f 'required_status_checks[contexts][]=CI Gate' \
  -f 'required_pull_request_reviews[required_approving_review_count]=0' \
  -F 'enforce_admins=false' \
  -F 'restrictions=null'
```

## One-time dashboard steps (cannot live in the repo)

- **Codex:** auto-review is **intentionally OFF** (2026-05-22). At
  `chatgpt.com/codex/cloud/settings/code-review` the "Personal auto review
  preferences" toggle is **off** and `linguistic76/skuel` is set to "Follow
  personal preferences" (which resolves to off) — there is no per-repo hard-off,
  so the personal toggle is the switch. Codex reviews only on a manual
  `@codex review`. The comment-bot (`codex-review.yml`) is disabled too (a
  bot-posted `@codex review` yields only the cosmetic prompt). To turn auto-review
  **on**, flip that toggle (or set the repo to "Review all PRs"); it's best-effort
  and draws from a weekly usage limit (Analytics → Usage).
- **Kodus:** ensure a **BYOK** LLM key is configured at `app.kodus.io`
  (Kody can't review without it). `kodus-config.yml` overrides the rest.
