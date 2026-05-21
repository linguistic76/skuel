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
| **Codex** (`chatgpt-codex-connector[bot]`) | OpenAI Codex AI review | **`AGENTS.md`** (repo root) + chatgpt.com/codex/settings/code-review | ⚠️ **PR reviews only — NOT a status check** | Auto-review (cloud setting) + `@codex review` |

### ⚠️ Codex does not appear in `gh pr checks`

This is by design — the Codex connector posts **PR reviews/comments**, never a
status check. To see its verdict, open the PR's **Files changed / Conversation**
tabs, or run:

```bash
gh pr view <PR#> --json reviews \
  -q '.reviews[] | select(.author.login|test("codex|kody")) | "\(.author.login)\t\(.state)\t\(.submittedAt)"'
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

- **Codex:** turn on **Automatic reviews** at
  `chatgpt.com/codex/settings/code-review` for deterministic per-PR review.
- **Kodus:** ensure a **BYOK** LLM key is configured at `app.kodus.io`
  (Kody can't review without it). `kodus-config.yml` overrides the rest.
