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
4. **CI runs automatically.** `ci.yml` runs path-guarded jobs (MyPy + unit tests when Python changed, a headless render smoke test when UI/static/Python changed, doc validation when docs/skills changed) and aggregates them into the **CI Gate** check. The **Codex Review Gate** (`codex-gate.yml`) also fires: for PRs touching `.py` files it is RED until `codex-considered` is applied — Codex review is mandatory on app-code PRs; for docs/tooling-only PRs it passes unless `@codex review` was posted and not yet considered.
5. **Summon a reviewer when ready.** Neither AI reviewer runs automatically (since 2026-05-24). Comment **`@kody start-review`** for Kody's gating review. For any PR touching Python files, also run **`scripts/request_codex_review.sh <PR#>`** — the Codex Review Gate is RED until you do. Do this once a PR is substantive, not on every intermediate commit.
6. **Address feedback.** Push fixes to the same branch — CI re-runs automatically on the new commit; re-comment `@kody start-review` / re-run the script to re-review the updated diff.
7. **Run `./dev pre-merge <PR#>`** to confirm all gates are green before merging. Then: `gh pr merge <PR#> --squash --delete-branch`. (No `--admin` — that flag merges past unmet requirements, including a blocking Kody review; the admin bypass is reserved for genuine emergencies, per [The gate is self-discipline for the admin](#the-gate-is-self-discipline-for-the-admin).)

### Merge policy: gates green + a considered review means merge (standing, 2026-07-25)

An autonomous merge (including by an AI agent running the workflow) requires BOTH:

1. **CI Gate and Codex Review Gate green**, and
2. **at least one AI review verdict on the final substantive content — Codex
   (`scripts/request_codex_review.sh`) or Kody (`@kody start-review`) — obtained, read, and
   considered.** A clean Kody run posts **no review object** — its verdict is the Kody
   check-run concluding `success` on the head, which `./dev pre-merge` (check 3) accepts.
   For Python-touching PRs the Codex Review Gate enforces this (it only turns
   green via `scripts/apply_codex_considered.sh` after a verdict exists). For docs/tooling-only
   PRs the gate **auto-passes with no verdict**, so condition 2 does not come for free: summon
   a reviewer explicitly before merging autonomously.

No additional per-merge human sign-off is required or expected. Kody, when summoned, holds the
merge through its own `CHANGES_REQUESTED` review. Earlier ad-hoc practice ("wait for the
founder's word at merge time") is superseded; the founder's controls are the gates, this
review-before-autonomous-merge requirement, and summoning Kody for anything non-trivial.

**Stacked-PR caveat:** merging a base PR with `--delete-branch` auto-**closes** any open PR
stacked on that branch — GitHub does not retarget it, and a closed PR cannot be reopened after
its head was force-pushed (observed on #806, which required successor #807). Rebase the child
onto `main` and retarget it **before** deleting the base branch, or merge without
`--delete-branch` and delete the branch after the child is safe.

---

## Who reviews — and which one is the gate

Three reviewers can run on a PR, gated by **two required status checks** (CI Gate + Codex Review Gate). Only the mechanical checks run automatically; both AI reviewers are summoned by comment (since 2026-05-24). They do **not** carry equal authority, and conflating them is the most common point of confusion.

| Participant | What it checks | Posts | Trigger | Blocks merge? |
|---|---|---|---|---|
| **CI Gate** (`ci.yml`) | Mechanical invariants: 0 MyPy errors, valid doc cross-references | A required status check | **Automatic** — every PR/push | **Yes** — required check |
| **Codex Review Gate** (`codex-gate.yml`) | That Codex review was **considered** — not Codex's verdict | A required status check | **Automatic** — two tiers: (1) **Python files changed** → RED until `codex-considered` label applied, regardless of whether `@codex review` was posted; (2) **docs/tooling only** → RED only once `@codex review` was posted and not yet considered; passes automatically with no request | **Yes** — required check; cleared by applying the `codex-considered` label (auto-dropped on every new commit, so changed code is re-considered) |
| **Kody** (`kody-ai[bot]`, Kodus) | Full-spectrum review (security, error handling, business logic, …) per `kodus-config.yml` | A check-run always; a real PR review **only when it has findings** — a clean run posts no review object, so its check-run concluding `success` IS the verdict signal (`./dev pre-merge` check 3 reads it) | **On demand** — `@kody start-review` (auto-review turned off in the Kodus dashboard, not via the repo file) | **Yes, when summoned** — `CHANGES_REQUESTED` holds the merge until resolved/dismissed |
| **Codex** (`chatgpt-codex-connector[bot]`) | Full-spectrum review against `AGENTS.md` invariants | **PR reviews/comments only — never itself a status check** (the *Codex Review Gate* above is the check) | **On demand** — `@codex review` | **No** — its *verdict* is advisory; the *gate* enforces only that you considered it |

> ℹ️ **Both AI reviewers are on-demand as of 2026-05-25.** Codex auto-review is off (Codex dashboard "Personal auto review preferences" toggle off + `linguistic76/skuel` set to "Follow personal preferences", which resolves to off — the personal toggle / per-repo setting is the switch, not the "Personal Review Trigger Preference" dropdown, which only picks *when*). The repo's comment-bot (`codex-review.yml`) is disabled too, because a bot-posted `@codex review` only returns the cosmetic "create a Codex account" prompt. Kody auto-review is off via its app.kodus.io "enable automatic code review" toggle. So both review **only** when summoned (`@codex review` / `@kody start-review`), and **CI Gate is the only dependable *automatic* gate**; Kody is the gating review you summon, Codex an optional second opinion. (Both briefly auto-ran earlier on 2026-05-25 before being consolidated back to on-demand.) Details: [`.github/workflows/README.md`](../../../.github/workflows/README.md).

**The trust model:**
- **CI Gate is the floor.** It is binary and mechanical. If it's red, something is objectively broken. It runs without being asked on every PR/push. (The **Codex Review Gate** also runs automatically but blocks on *process*, not findings — it stays green unless you requested a Codex review and haven't yet marked it considered.)
- **Kody is the gate you summon.** It no longer runs on its own; comment **`@kody start-review`** to invoke it. *When* it runs, its `CHANGES_REQUESTED` review (configured via `isRequestChangesActive: true`) actually holds the merge, so treat its blocking findings as must-address. The catch: a review you never summon never runs — so summoning Kody before merging anything non-trivial is now part of the ritual, not something the system does for you.
- **Codex is the second opinion you summon.** Comment **`@codex review`** to invoke it. Its *verdict* is *advisory* and **invisible to `gh pr checks`** — what shows up in checks is the separate **Codex Review Gate** (above), which only enforces that you *considered* the review. The verdict can land on any of **three** surfaces, so scan all three (the first command below misses inline review-comments — the surface Codex often uses for a specific finding):

  ```bash
  # issue-comments + review-objects
  gh pr view <PR#> --json reviews,comments \
    -q '(.reviews[], .comments[]) | select(.author.login|test("codex|kody";"i")) | "\(.author.login)\t\(.state // "comment")"'
  # inline review-comments (easy to miss — anchored to a file/line)
  gh api repos/linguistic76/skuel/pulls/<PR#>/comments \
    -q '.[] | select(.user.login|test("codex";"i")) | "\(.commit_id[0:8]) \(.path):\(.line) \(.body[0:80])"'
  ```

  > ⚠️ **Match the login by substring, never by exact string — it varies by surface.** Codex posts as `chatgpt-codex-connector` on the issue-comment surface (`gh pr view --json comments`) but as `chatgpt-codex-connector[bot]` on the review and inline-comment APIs. A filter like `select(.author.login == "chatgpt-codex-connector[bot]")` therefore silently returns *nothing* on the issue-comment surface — making a posted review look like no review at all. Always use the substring/regex form above (`test("codex";"i")`).

  **Three failure modes to rule out before you apply `codex-considered`:**
  1. **"Nothing found" is not proof of "no review" — it is a STOP.** An empty result usually means your filter or surface was wrong (the login-suffix trap above, a not-yet-posted review, or a surface you didn't scan), not that Codex stayed silent. Never clear the gate on the assumption "no news is good news." If you cannot **positively locate the verdict and read its actual text**, do not clear the gate — re-query the other surfaces, wait, or re-summon. The gate exists so a human/agent consciously reads what Codex said; clearing it on an unread or merely-presumed verdict defeats its entire purpose.
  2. **A located review may be stale-at-head.** `commit_id == head` is necessary but **not sufficient** — Codex can re-emit a prior finding verbatim while re-anchoring it to a new commit. Also confirm the finding's **premise still exists in the code** (e.g. if it cites a function/branch you already changed, `grep` for it). A finding whose premise is gone is refuted; document that disposition in a PR comment, then apply `codex-considered`.
  3. **The label can be race-stripped by an in-flight gate run.** The gate removes `codex-considered` when it processes a `synchronize` event — and a gate run still **queued from the last push** does that *after* you apply the label (observed live on #584: the label silently vanished and the gate read RED at merge time). Apply the label with **`scripts/apply_codex_considered.sh <PR#>`**, which waits for in-flight gate runs on the head SHA to finish, applies the label, and polls until the gate status actually reports green (re-adding once if stripped). If labeling by hand instead, wait until no gate runs are in flight and **re-check the label + gate status immediately before merging**.

Why two AI reviewers, both on demand? Defense-in-depth from a second, independent model (OpenAI Codex alongside Kodus) catches more than one alone. They differ in authority: when summoned, **Kody posts a real blocking review** (a `CHANGES_REQUESTED` that holds the merge), while **Codex only ever comments** — so Kody is the reviewer you reach for when you want a verdict that gates, Codex when you want a second pair of eyes. Both are on-demand as of 2026-05-25 for the same reason: auto-review on every intermediate commit produced noise, and a flaky, usage-capped external service should never be able to deadlock a merge — so the only thing that runs automatically is the mechanical CI Gate. The cost of that choice is honest: **review coverage is no longer automatic.** A PR merged without anyone commenting `@kody start-review` gets *no* AI review at all. That is acceptable only because the founder owns the discipline of summoning review before merging anything that matters.

---

## What the gate enforces — and what it doesn't

### The gate is self-discipline for the admin

Branch protection on `main` is: **require a PR + a green CI Gate, 0 human approvals required, `enforce_admins=false`.** That last setting means the **admin (the founder) can bypass the gate** — merge despite a red check, or push directly in an emergency.

This is intentional for a solo project (no second person exists to unblock you), but be honest about what it means: **for the admin, the gate is advisory; its value depends on choosing to honor it.** For everything that runs *as* automation (CI, agents, bots), the gate is binding. The discipline the workflow buys is only as real as the founder's willingness to wait for green.

### Drafts and on-demand review

- Open a PR as a **draft** to iterate before inviting review; mark it *ready for review* when it's done. (No AI reviewer auto-fires regardless, so a draft is purely a signal to humans.)
- Both AI reviewers are **on demand** — neither runs on its own. Comment **`@kody start-review`** to run Kody (the gating reviewer) and run `scripts/request_codex_review.sh <PR#>` for Codex. Re-comment / re-run after pushing fixes to re-review the updated diff.

### Never commit directly to `main`

All work goes through a branch + PR — no exceptions except a genuine production emergency. Direct pushes to `main` skip every gate (CI, Codex, Kody) and leave no review audit trail. The `enforce_admins=false` setting makes direct pushes technically possible for the admin, but they are not part of the normal workflow.

### The decommission check (consumer-death rule)

When a PR **deletes or reroutes a consumer** — removes a service, swaps a call site to a new mechanism, deletes an adapter — name in the PR description what upstream machinery just lost its **last invoker**. What happens to that machinery follows the existing staged-vs-abandoned line (CLAUDE.md § One Path Forward): if it is genuinely staged work with a concrete integration intent, register it deliberately (a `PLANNED_*` tier in `scripts/detect_bloat.py`, or a debt-register row with a trigger); otherwise **delete it in the same PR** — a PLANNED entry is a completion backlog, not an escape hatch for abandoned paths. Silence is the failure mode: the orphan stays wired and later reads as alive.

Corollary for liveness audits: **construction is not liveness.** A class built in the composition root, injected on every boot, and annotated "REQUIRED" can still have zero production invocations — audit *invocation reachability from production entry points* (routes, background workers, event subscriptions, one-shot `./dev` scripts), never construction alone. Both failure modes shipped together in the `query_builders/` stack: it lost its last invoker as a side effect of feature PRs (2026-02-09, 2026-05-12) with no decommission step, and a deliberate audit then certified the corpse as live because it was constructed at boot (#58/#66; corrected 2026-08-16). No gate can catch this mechanically — invocation reachability is flow analysis, which SKUEL's linters deliberately refuse — so, like the rest of this section, it is self-discipline.

### Closing orphaned PRs after a cherry-pick

When commits are cherry-picked to `main` directly (e.g. because the branch diverged after a prior session landed commits on `main`), the PR remains open on GitHub with `mergedAt: null` — a confusing audit trail. After cherry-picking, **close the PR with a note** citing the SHAs that landed:

```bash
gh pr close <PR#> --comment "Work landed via cherry-pick: <sha1>, <sha2>, <sha3>. Branch had conflicts due to prior direct commits on main."
```

This closes the record cleanly so the PR history accurately reflects what shipped.

---

## Observations & possible improvements

*Noticed while documenting the setup (2026-05-22). None are blocking; listed for a future pass.*

1. ~~**No PR template.**~~ *(Resolved 2026-05-22)* — `.github/pull_request_template.md` now exists, so descriptions are standardized — valuable precisely because Kody concatenates its summary onto the human description, so an empty description would otherwise yield a thin PR record.
2. ~~**`develop` branch is referenced but doesn't exist.**~~ *(Resolved 2026-05-22)* — `develop` was dead config in `ci.yml` and `kodus-config.yml`; removed, since only `main` exists. Re-add it to both if a staging flow is ever introduced.
3. **`codex-review.yml` uses `pull_request`, not `pull_request_target`.** Fine today because every PR comes from a same-repo branch (the token has write access). A PR from an external fork would get a read-only token and the comment-post would silently no-op. Only matters if SKUEL ever accepts outside contributions.
4. **Codex's verdict is invisible to `gh pr checks`.** By design — Codex's *review* is not a check (the **Codex Review Gate** is, but it only tracks whether you *considered* the review, not what Codex said). So "merge when checks pass" can clear the gate without anyone reading the verdict. The three-surface scan above is the mitigation; reading the verdict before applying `codex-considered` is part of the merge ritual.

---

## See also

- [`.github/workflows/README.md`](../../../.github/workflows/README.md) — operational reference: the four CI participants, `ci.yml` job graph, branch-protection `gh` command, dashboard-only steps
- [`AGENTS.md`](../../../AGENTS.md) — the invariants Codex (and other agents) review against
- [GitHub Fundamentals](../guides/GITHUB_FUNDAMENTALS.md) — local → remote git/GitHub workflow basics
- [Git Hooks](GIT_HOOKS.md) — local automation that runs outside CI
