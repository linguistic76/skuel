<!--
No AI reviewer runs automatically — comment `@kody start-review` (gating review) or
`@codex review` (advisory) to summon one. Kody generates no PR summary, so this
description is the PR's only account of the change — write a real one. See
app/docs/development/PR_WORKFLOW.md for who reviews this PR and which checks gate
the merge.
-->

## What & why

<!-- What does this change do, and why does it need to exist? -->

## Type of change

- [ ] Feature
- [ ] Fix
- [ ] Refactor (no behavior change)
- [ ] Docs / skills
- [ ] CI / tooling

## How it was verified

- [ ] `./dev quality` passes (ruff + SKUEL linter + cypher checks + 0 MyPy errors)
- [ ] Tests added/updated where behavior changed
<!-- Note anything you ran manually (e.g. launched the app, hit the route). -->

## Reviewer notes

<!--
Anything the reviewers should focus on. CI Gate is the required check (automatic).
AI reviewers are on demand: `@kody start-review` gates (CHANGES_REQUESTED holds the
merge); `@codex review` is advisory (comments only — not a status check). Invariants
are in /AGENTS.md. One Path Forward: no back-compat shims — the old path should be
deleted, not preserved.
-->
