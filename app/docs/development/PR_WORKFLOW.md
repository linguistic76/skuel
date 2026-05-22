# PR-Based Development Workflow

**Purpose:** Explain *why* every change to `main` now goes through a pull request, what happens to a change along the way, and which checks actually gate a merge.

> **Operational reference:** how the workflows and reviewers are wired (and the exact `gh` commands to re-apply them) lives in [`.github/workflows/README.md`](../../../.github/workflows/README.md). This document is the *why* and the *lifecycle*; that one is the *how*. Read [GitHub Fundamentals](../guides/GITHUB_FUNDAMENTALS.md) first if branches/PRs/remotes are unfamiliar.

---

## Why we use PRs now

Until **2026-05-21**, changes landed on `main` directly — commit, push, done. That was fast, and for a small early codebase it was fine. It is no longer how SKUEL works.

The reason is structural, not bureaucratic:

- **SKUEL is built by a non-technical founder working with AI.** The code is largely AI-authored, and there is **no second human engineer** doing code review. The usual safety net — "another person reads it before it ships" — does not exist here.
- As the codebase grew (25 EntityTypes, strict type-safety invariants, a generic backend serving every domain), so did the cost of a silent regression slipping onto `main`.
- A pull request inserts a **mandatory gate before code reaches `main`**: mechanical checks plus two AI reviewers stand in for the human reviewer SKUEL doesn't have.

So yes — **the PR exists to allow review.** But more precisely: the PR is the place where the *substitute* for a human reviewer runs. Direct-to-`main` skipped that substitute entirely. The PR makes it unskippable (for everything except a deliberate admin override — see [The gate is self-discipline for the admin](#the-gate-is-self-discipline-for-the-admin)).

### Before vs. after

| | Old (direct) | New (PR-gated, since 2026-05-21) |
|---|---|---|
| Path to `main` | `git push` straight to `main` | branch → PR → checks + review → merge |
| Review | none | CI Gate (mechanical) + Kody (gating) + Codex (advisory) |
| Speed | instant | minutes (wait for CI + reviewers) |
| Safety net | none | regressions caught before they reach `main` |
| Audit trail | commit message only | PR thread: diff, review comments, check history |

The trade is deliberate: a few minutes of latency per change buys a reviewer SKUEL otherwise lacks.

---

## The lifecycle of a change

1. **Branch off `main`.** `git checkout -b kind/short-description` (e.g. `docs/pr-workflow`, `fix/ownership-404`). `main` is protected — you cannot push to it directly.
2. **Commit and push the branch.** `git push -u origin <branch>`.
3. **Open the PR** against `main`: `gh pr create`. Write a real description — Kody *concatenates* its summary onto yours rather than replacing it, so a meaningful description survives.
4. **CI runs automatically.** `ci.yml` runs path-guarded jobs (MyPy when Python changed, doc validation when docs/skills changed) and aggregates them into the **CI Gate** check.
5. **The AI reviewers run.** Kody reviews on open and re-reviews each pushed commit. `codex-review.yml` auto-posts `@codex review`, which triggers Codex ~40s later.
6. **Address feedback.** Push fixes to the same branch — CI and Kody re-run on the new commit; comment `@codex review` to re-request Codex on demand.
7. **Merge** once CI Gate is green and no reviewer is blocking. Delete the branch.

---

## Who reviews — and which one is the gate

Three participants run on a PR. They do **not** carry equal authority, and conflating them is the most common point of confusion.

| Participant | What it checks | Posts | Blocks merge? |
|---|---|---|---|
| **CI Gate** (`ci.yml`) | Mechanical invariants: 0 MyPy errors, valid doc cross-references | A required status check | **Yes** — the single required check |
| **Kody** (`kody-ai[bot]`, Kodus) | Full-spectrum review (security, error handling, business logic, …) per `kodus-config.yml` | A check **and** a real PR review | **Yes** — `CHANGES_REQUESTED` holds the merge until resolved/dismissed |
| **Codex** (`chatgpt-codex-connector[bot]`) | Full-spectrum review against `AGENTS.md` invariants | **PR reviews/comments only — never a status check** | **No** — advisory |

**The trust model:**
- **CI Gate is the floor.** It is binary and mechanical. If it's red, something is objectively broken.
- **Kody is the gate.** Its `CHANGES_REQUESTED` review (configured via `isRequestChangesActive: true`) actually holds the merge. Treat its blocking findings as must-address.
- **Codex is the second opinion.** It is *advisory* and **invisible to `gh pr checks`** — easy to miss, because it isn't a check at all. Its verdict can land as a *review* or as an *issue comment*, so to see it you must scan both:

  ```bash
  gh pr view <PR#> --json reviews,comments \
    -q '(.reviews[], .comments[]) | select(.author.login|test("codex|kody";"i")) | "\(.author.login)\t\(.state // "comment")"'
  ```

Why two AI reviewers? Defense-in-depth from independent models (Kodus + OpenAI Codex) catches more than either alone. Kody gates because a single gating reviewer is enough to hold the line; Codex stays advisory so a flaky external service can never deadlock a merge.

---

## What the gate enforces — and what it doesn't

### The gate is self-discipline for the admin

Branch protection on `main` is: **require a PR + a green CI Gate, 0 human approvals required, `enforce_admins=false`.** That last setting means the **admin (the founder) can bypass the gate** — merge despite a red check, or push directly in an emergency.

This is intentional for a solo project (no second person exists to unblock you), but be honest about what it means: **for the admin, the gate is advisory; its value depends on choosing to honor it.** For everything that runs *as* automation (CI, agents, bots), the gate is binding. The discipline the workflow buys is only as real as the founder's willingness to wait for green.

### Drafts and on-demand review

- Open a PR as a **draft** to iterate without triggering Codex (`codex-review.yml` skips drafts). Marking it *ready for review* triggers the full review.
- Comment **`@codex review`** any time to re-request Codex manually; **`@kody start-review`** re-runs Kody.

---

## Observations & possible improvements

*Noticed while documenting the setup (2026-05-22). None are blocking; listed for a future pass.*

1. **No PR template.** A `.github/pull_request_template.md` would standardize descriptions — valuable precisely because Kody concatenates its summary onto the human description, so an empty description yields a thin PR record. Low effort, clear win.
2. ~~**`develop` branch is referenced but doesn't exist.**~~ *(Resolved 2026-05-22)* — `develop` was dead config in `ci.yml` and `kodus-config.yml`; removed, since only `main` exists. Re-add it to both if a staging flow is ever introduced.
3. **`codex-review.yml` uses `pull_request`, not `pull_request_target`.** Fine today because every PR comes from a same-repo branch (the token has write access). A PR from an external fork would get a read-only token and the comment-post would silently no-op. Only matters if SKUEL ever accepts outside contributions.
4. **Codex's verdict is invisible to `gh pr checks`.** This is by design (it's not a check), but it's a real footgun — a "merge when checks pass" reflex skips Codex entirely. The scan command above is the mitigation; consider it part of the merge ritual.

---

## See also

- [`.github/workflows/README.md`](../../../.github/workflows/README.md) — operational reference: the four CI participants, `ci.yml` job graph, branch-protection `gh` command, dashboard-only steps
- [`AGENTS.md`](../../../AGENTS.md) — the invariants Codex (and other agents) review against
- [GitHub Fundamentals](../guides/GITHUB_FUNDAMENTALS.md) — local → remote git/GitHub workflow basics
- [Git Hooks](GIT_HOOKS.md) — local automation that runs outside CI
