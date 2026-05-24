# PR-Based Development Workflow

**Purpose:** Explain *why* every change to `main` now goes through a pull request, what happens to a change along the way, and which checks actually gate a merge.

> **Operational reference:** how the workflows and reviewers are wired (and the exact `gh` commands to re-apply them) lives in [`.github/workflows/README.md`](../../../.github/workflows/README.md). This document is the *why* and the *lifecycle*; that one is the *how*. Read [GitHub Fundamentals](../guides/GITHUB_FUNDAMENTALS.md) first if branches/PRs/remotes are unfamiliar.

---

## Why we use PRs now

Until **2026-05-21**, changes landed on `main` directly — commit, push, done. That was fast, and for a small early codebase it was fine. It is no longer how SKUEL works.

The reason is structural, not bureaucratic:

- **SKUEL is built by a non-technical founder working with AI.** The code is largely AI-authored, and there is **no second human engineer** doing code review. The usual safety net — "another person reads it before it ships" — does not exist here.
- As the codebase grew (25 EntityTypes, strict type-safety invariants, a generic backend serving every domain), so did the cost of a silent regression slipping onto `main`.
- A pull request inserts a **mandatory mechanical gate before code reaches `main`** (the CI Gate check), plus the place from which to summon two AI reviewers that stand in for the human reviewer SKUEL doesn't have.

So yes — **the PR exists to allow review.** More precisely: the PR is the place where the *substitute* for a human reviewer runs. Direct-to-`main` skipped that substitute entirely. Two halves run on a PR, and **since 2026-05-24 they behave differently**:

- The **mechanical half** (CI Gate) is **automatic and unskippable** — except by a deliberate admin override (see [The gate is self-discipline for the admin](#the-gate-is-self-discipline-for-the-admin)).
- The **AI-reviewer half** (Kody, Codex) is **summoned on demand** — `@kody start-review` / `@codex review` — when a PR is ready for it, rather than firing on every intermediate commit. Neither AI reviewer runs by itself anymore.

The discipline therefore has two parts: never bypass the mechanical gate, and **actually remember to summon AI review** before merging anything non-trivial. The substitute reviewer is now opt-in; its value depends on the founder choosing to invoke it.

### Before vs. after

| | Old (direct) | New (PR-gated, since 2026-05-21) |
|---|---|---|
| Path to `main` | `git push` straight to `main` | branch → PR → checks + review → merge |
| Review | none | CI Gate (mechanical, automatic); AI reviewers on demand — Kody (gating, `@kody start-review`) + Codex (advisory, `@codex review`) |
| Speed | instant | minutes (wait for CI + reviewers) |
| Safety net | none | regressions caught before they reach `main` |
| Audit trail | commit message only | PR thread: diff, review comments, check history |

The trade is deliberate: a few minutes of latency per change buys a reviewer SKUEL otherwise lacks.

---

## The lifecycle of a change

1. **Branch off `main`.** `git checkout -b kind/short-description` (e.g. `docs/pr-workflow`, `fix/ownership-404`). `main` is protected — you cannot push to it directly.
2. **Commit and push the branch.** `git push -u origin <branch>`.
3. **Open the PR** against `main`: `gh pr create`. Write a real description — when Kody is later summoned it *concatenates* its summary onto yours rather than replacing it, so a meaningful description survives.
4. **CI runs automatically.** `ci.yml` runs path-guarded jobs (MyPy when Python changed, doc validation when docs/skills changed) and aggregates them into the **CI Gate** check. This is the only thing that runs on its own.
5. **Summon a reviewer when ready.** Neither AI reviewer runs automatically (since 2026-05-24). Comment **`@kody start-review`** for Kody's gating review, and/or **`@codex review`** for a Codex second opinion. Do this once a PR is substantive, not on every intermediate commit.
6. **Address feedback.** Push fixes to the same branch — CI re-runs automatically on the new commit; re-comment `@kody start-review` / `@codex review` to re-review the updated diff.
7. **Merge** once CI Gate is green and no summoned reviewer is blocking. Delete the branch.

---

## Who reviews — and which one is the gate

Three participants can run on a PR. Only **CI Gate runs automatically**; both AI reviewers are summoned by comment (since 2026-05-24). They do **not** carry equal authority, and conflating them is the most common point of confusion.

| Participant | What it checks | Posts | Trigger | Blocks merge? |
|---|---|---|---|---|
| **CI Gate** (`ci.yml`) | Mechanical invariants: 0 MyPy errors, valid doc cross-references | A required status check | **Automatic** — every PR/push | **Yes** — the single required check |
| **Kody** (`kody-ai[bot]`, Kodus) | Full-spectrum review (security, error handling, business logic, …) per `kodus-config.yml` | A check **and** a real PR review | **On demand** — `@kody start-review` (`automatedReviewActive: false`) | **Yes, when summoned** — `CHANGES_REQUESTED` holds the merge until resolved/dismissed |
| **Codex** (`chatgpt-codex-connector[bot]`) | Full-spectrum review against `AGENTS.md` invariants | **PR reviews/comments only — never a status check** | **On demand** — `@codex review` | **No** — advisory comments only |

> ℹ️ **Codex auto-review is intentionally off (2026-05-22).** In the Codex dashboard the "Personal auto review preferences" toggle is off and `linguistic76/skuel` is set to "Follow personal preferences" (which resolves to off) — there's no per-repo hard-off, so the personal toggle is the switch. The repo's comment-bot (`codex-review.yml`) is disabled too, because a bot-posted `@codex review` only returns the cosmetic "create a Codex account" prompt. So Codex reviews **only** on a manual `@codex review`. **As of 2026-05-24 Kody is on-demand too** (`@kody start-review`), so **CI Gate is the only dependable *automatic* gate**; Kody is the gating review you summon, and Codex an optional second opinion you summon. Details: [`.github/workflows/README.md`](../../../.github/workflows/README.md).

**The trust model:**
- **CI Gate is the floor — and the only automatic gate.** It is binary and mechanical. If it's red, something is objectively broken. It is the one thing that runs without being asked.
- **Kody is the gate you summon.** It no longer runs on its own; comment **`@kody start-review`** to invoke it. *When* it runs, its `CHANGES_REQUESTED` review (configured via `isRequestChangesActive: true`) actually holds the merge, so treat its blocking findings as must-address. The catch: a review you never summon never runs — so summoning Kody before merging anything non-trivial is now part of the ritual, not something the system does for you.
- **Codex is the second opinion you summon.** Comment **`@codex review`** to invoke it. It is *advisory* and **invisible to `gh pr checks`** — easy to miss, because it isn't a check at all. Its verdict can land as a *review* or as an *issue comment*, so to see it you must scan both:

  ```bash
  gh pr view <PR#> --json reviews,comments \
    -q '(.reviews[], .comments[]) | select(.author.login|test("codex|kody";"i")) | "\(.author.login)\t\(.state // "comment")"'
  ```

Why two AI reviewers, both on demand? Defense-in-depth from a second, independent model (OpenAI Codex alongside Kodus) catches more than one alone. They differ in authority: when summoned, **Kody posts a real blocking review** (a `CHANGES_REQUESTED` that holds the merge), while **Codex only ever comments** — so Kody is the reviewer you reach for when you want a verdict that gates, Codex when you want a second pair of eyes. Both were moved to on-demand (Codex 2026-05-22, Kody 2026-05-24) for the same reason: auto-review on every intermediate commit produced noise, and a flaky, usage-capped external service should never be able to deadlock a merge — so the only thing that runs automatically is the mechanical CI Gate. The cost of that choice is honest: **review coverage is no longer automatic.** A PR merged without anyone commenting `@kody start-review` gets *no* AI review at all. That is acceptable only because the founder owns the discipline of summoning review before merging anything that matters.

---

## What the gate enforces — and what it doesn't

### The gate is self-discipline for the admin

Branch protection on `main` is: **require a PR + a green CI Gate, 0 human approvals required, `enforce_admins=false`.** That last setting means the **admin (the founder) can bypass the gate** — merge despite a red check, or push directly in an emergency.

This is intentional for a solo project (no second person exists to unblock you), but be honest about what it means: **for the admin, the gate is advisory; its value depends on choosing to honor it.** For everything that runs *as* automation (CI, agents, bots), the gate is binding. The discipline the workflow buys is only as real as the founder's willingness to wait for green.

### Drafts and on-demand review

- Open a PR as a **draft** to iterate before inviting review; mark it *ready for review* when it's done. (No AI reviewer auto-fires regardless, so a draft is purely a signal to humans.)
- Both AI reviewers are **on demand** — neither runs on its own. Comment **`@kody start-review`** to run Kody (the gating reviewer) and **`@codex review`** for a Codex second opinion. Re-comment after pushing fixes to re-review the updated diff.

---

## Observations & possible improvements

*Noticed while documenting the setup (2026-05-22). None are blocking; listed for a future pass.*

1. ~~**No PR template.**~~ *(Resolved 2026-05-22)* — `.github/pull_request_template.md` now exists, so descriptions are standardized — valuable precisely because Kody concatenates its summary onto the human description, so an empty description would otherwise yield a thin PR record.
2. ~~**`develop` branch is referenced but doesn't exist.**~~ *(Resolved 2026-05-22)* — `develop` was dead config in `ci.yml` and `kodus-config.yml`; removed, since only `main` exists. Re-add it to both if a staging flow is ever introduced.
3. **`codex-review.yml` uses `pull_request`, not `pull_request_target`.** Fine today because every PR comes from a same-repo branch (the token has write access). A PR from an external fork would get a read-only token and the comment-post would silently no-op. Only matters if SKUEL ever accepts outside contributions.
4. **Codex's verdict is invisible to `gh pr checks`.** This is by design (it's not a check), but it's a real footgun — a "merge when checks pass" reflex skips Codex entirely. The scan command above is the mitigation; consider it part of the merge ritual.

---

## See also

- [`.github/workflows/README.md`](../../../.github/workflows/README.md) — operational reference: the four CI participants, `ci.yml` job graph, branch-protection `gh` command, dashboard-only steps
- [`AGENTS.md`](../../../AGENTS.md) — the invariants Codex (and other agents) review against
- [GitHub Fundamentals](../guides/GITHUB_FUNDAMENTALS.md) — local → remote git/GitHub workflow basics
- [Git Hooks](GIT_HOOKS.md) — local automation that runs outside CI
