---
title: Context DSL Cheat-Sheet
updated: 2026-07-10
status: current
category: user-guide
tags: [dsl, cheatsheet, activities, quick-reference]
related: [tasks-quick-add.md]
---

# Context DSL Cheat-Sheet

Turn a plain markdown line into a real SKUEL entity by adding `@context()`.
Write these lines in a Periodic Note or another synced folder — the next vault
sync extracts them. Vault sync only reads the allowlisted folders
(`periodic_notes/`, `personal_notes/`, `activity_notes/`, `knowledge/` by
default); loose captures belong in `activity_notes/`.

## The shape

```markdown
- [ ] What you want to do @context(type) @when(date) @priority(1-5)
```

Only `@context()` is required. `- [ ]` starts it as a draft; `- [x]` records it
as already done.

## Context types

| Write | Creates | Example |
|-------|---------|---------|
| `@context(task)` | Task | `- [ ] Call hosting provider @context(task) @priority(2)` |
| `@context(habit)` | Habit | `- [ ] Morning pages @context(habit) @repeat(daily) @duration(20m)` |
| `@context(goal)` | Goal | `- [ ] Reach 20 members @context(goal) @when(2026-09-01)` |
| `@context(event)` | Event | `- [ ] Workshop @context(event) @when(2026-07-15T14:00) @duration(2h)` |
| `@context(principle)` | Principle | `- [ ] Discernment before action @context(principle)` |
| `@context(choice)` | Choice | `- [ ] Pick course platform @context(choice) @when(2026-08-01)` |

Combine when an activity spans domains: `@context(task,goal)`. Add `learning`
as a modifier for educational activities: `@context(task,learning)`.

Other valid vocabulary: `ku` (creates a Knowledge Unit; teacher/admin only)
and `path_step`/`ps`, `learning_path`/`lp`, `calendar`, `life_path`, `finance`
— these parse but create nothing yet (no create surface wired; the sync warns
you whenever such a context is skipped). Anything else inside `@context()` is an error.
See `/docs/dsl/DSL_SPECIFICATION.md` for the full vocabulary.

A typo in `@context()` fails the whole line (you'll see it in the sync
warnings) — that's deliberate, so a misspelled context never half-creates
something.

## Optional tags

| Tag | Values | Example |
|-----|--------|---------|
| `@when()` | ISO date or datetime | `@when(2026-07-14)` · `@when(2026-07-14T09:30)` |
| `@priority()` | 1 (highest) – 5 (lowest) | `@priority(1)` |
| `@duration()` | minutes/hours | `@duration(45m)` · `@duration(1h30m)` |
| `@repeat()` | daily, weekly:…, monthly:…, every:Nd | `@repeat(weekly:Mon,Wed,Fri)` |
| `@energy()` | focus, light, social, physical, creative, rest, spiritual, emotion | `@energy(focus,creative)` |
| `@ku()` | primary knowledge link | `@ku(ku.sel/mindfulness)` |
| `@link()` | goal:, principle:, ku:, … | `@link(goal:health, principle:awareness-first)` |

`@when()` needs a real ISO date — `@when(Friday)` or `@when(07:00)` keeps the
line but drops the schedule (the sync warnings tell you which values were
dropped; same for invalid `@priority`/`@duration`/`@repeat` values).

## Full example

```markdown
- [ ] Draft Teens.yoga lesson on focus @context(task,learning) @when(2026-07-14T09:00) @priority(1) @duration(90m) @energy(focus,creative) @ku(ku.teens-yoga/focus-lesson) @link(goal:teens-yoga/20-members)
```

**Full reference:** `/docs/dsl/DSL_USAGE_GUIDE.md` (patterns) and
`/docs/dsl/DSL_SPECIFICATION.md` (grammar).
