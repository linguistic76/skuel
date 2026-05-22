# GitHub Actions Workflows & PR Reviewers

This directory holds SKUEL's CI. It also documents the **two AI reviewers**
(Kodus and Codex) that run on PRs but are configured outside these YAMLs.

## Who runs on a PR

| Participant | What it is | Where configured | Posts | Trigger |
|---|---|---|---|---|
| **CI Gate** | Aggregator job in `ci.yml` | This repo | ✅ status check (the one required check) | Every PR/push to `main`/`develop` |
| **MyPy Type Check** | Job in `ci.yml` | This repo | ✅ status check + PR comment on failure | When `app/**/*.py`, `pyproject.toml`, or `uv.lock` change |
| **Validate Documentation** | Job in `ci.yml` | This repo | ✅ status check + PR comment | When `app/docs/**`, `app/.claude/skills/**`, or the docs scripts change |
| **Generate Metrics** | Job in `ci.yml` | This repo | ✅ status check (skipped on PRs) | Push to `main` only |
| **Kody** (`kody-ai[bot]`) | Kodus AI code review | **`kodus-config.yml`** (repo root) + app.kodus.io | ✅ "Code Review Completed" check **+ PR reviews** (CHANGES_REQUESTED on findings) | On PR open + re-reviews each pushed commit; `@kody start-review` |
| **Codex Auto-Review** | Job in `codex-review.yml` | This repo | Posts the `@codex review` comment (no status check) | Every non-draft PR: open / reopen / ready-for-review / push (debounced) |
| **Codex** (`chatgpt-codex-connector[bot]`) | OpenAI Codex AI review | **`AGENTS.md`** (repo root) + `codex-review.yml` | ⚠️ **PR reviews only — NOT a status check** | The auto-posted `@codex review` comment (cloud auto-review is **OFF**) |

### ⚠️ Codex does not appear in `gh pr checks`

This is by design — the Codex connector posts **PR reviews/comments**, never a
status check. Its verdict may land as a *review* (cloud auto-review used to) **or
as an issue comment** (the `@codex review` comment trigger does), so a verdict
check must scan **both**. Open the PR's **Files changed / Conversation** tabs, or
run:

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

Codex's cloud auto-review proved unreliable — across PRs #1–#10 it fired on only
**3**, and **6 merged with no Codex review at all**. The `@codex review` *comment*
worked every time. This workflow posts that comment automatically, so every
non-draft PR gets a deterministic review. (Verified on PR #11: a comment posted
by `github-actions[bot]` does trigger Codex.)

- Triggers on `opened` / `reopened` / `ready_for_review` / `synchronize`.
- A `sleep 30` + per-PR `concurrency: cancel-in-progress` debounces bursts — a
  flurry of pushes collapses to one trigger.
- Skips drafts (`if: github.event.pull_request.draft == false`).
- Uses the built-in `GITHUB_TOKEN` with `pull-requests: write` (sufficient for
  the `issues.createComment` call — proven on PR #11; no PAT needed).
- Codex prepends a cosmetic "create a Codex account / connect to github" line
  because the trigger comes from a bot account; the actual review still follows.

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

- **Codex:** keep **Automatic reviews OFF** at
  `chatgpt.com/codex/settings/code-review` (turned off 2026-05-22).
  `codex-review.yml` auto-posts `@codex review` as the deterministic path;
  leaving cloud auto-review on would double-review the PRs where it fires.
- **Kodus:** ensure a **BYOK** LLM key is configured at `app.kodus.io`
  (Kody can't review without it). `kodus-config.yml` overrides the rest.
