---
title: "ADR-090: One Link per Fact, a View per Domain"
updated: 2026-10-04
status: accepted
category: decisions
tags: [adr, decisions, relationships, activity-domains, graph-schema, registry, goals, principles]
related: [ADR-026, ADR-057, ADR-087]
related_skills: [activity-domains]
---

# ADR-090: One Link per Fact, a View per Domain

**Status:** Accepted — founder-ratified 2026-10-04 (four rounds). **Implementation pending:** the
Activity Links arc builds it; the Status column of its [PR ledger](../roadmap/activity-links-arc.md#pr-ledger)
is the ledger.
**Date:** 2026-10-04
**Deciders:** MCF
**Decision Type:** ☑ Graph Schema  ☑ Pattern/Practice
**Arc:** [Activity Links — rulings & contract](../roadmap/activity-links-arc.md) (rulings R1–R11).
**Related ADRs:**
- [ADR-026](ADR-026-unified-relationship-registry.md) — the registry where each domain declares
  its view of a link (one `UnifiedRelationshipDefinition` per side). This ADR decides what those
  declarations may say about one link; where they live is unchanged.
- [ADR-057](ADR-057-activity-domain-sibling-signals.md) — its diagonals table names a retiring
  edge type; amended by the PR that retires it (§ Records this ADR amends).
- [ADR-087](ADR-087-status-guarded-conditional-writes.md) — a goal's progress is recomputed from
  its linked-task tally under the goal's lock. §5 changes what the tally counts, not how the write
  is guarded.

## Related Skills

For implementation guidance, see:
- [@activity-domains](../../.claude/skills/activity-domains/SKILL.md)

---

## Context

The six Activity domains (Task, Goal, Habit, Event, Choice, Principle) link to each other through
edges. Each domain declares its view of those links twice. Its relationship-registry definitions
(`core/models/relationship_registry.py`) feed the context API and the services' relationship reads.
Its detail page's Connections section reads a separate hand-written list of edge types
(`core/utils/connection_configs.py`), with one direction per domain.

The links were added one domain at a time. A census of the registry (2026-10-04) found four
patterns where there should be one:

- **One edge, read at both ends.** `SUPPORTS_GOAL` (habit → goal) is the habit's supported goals and
  the goal's supporting habits.
- **Two edges for two different statements.** A principle *inspires* a habit; a habit *embodies* a
  principle. These are different claims, and the registry reads both at both ends.
- **One statement stored under two names, one per side.** "This principle guides this goal" is
  `GUIDES_GOAL` when written at the principle and `GUIDED_BY_PRINCIPLE` when written at the goal.
  Principle and choice repeat the shape with `GUIDES_CHOICE` / `INFORMED_BY_PRINCIPLE`. No principle
  definition reads the goal-side or choice-side edge. The goal and the choice each hold the one fact
  under two keys, and a reader that asks one key sees half.
- **One edge, read at one end only.** The task "link goal" door writes `CONTRIBUTES_TO_GOAL`, while
  the goal's registry views, its progress tally and the user-context statements read
  `FULFILLS_GOAL` only. An event's `CONTRIBUTES_TO_GOAL` and `CELEBRATES_GOAL`, and a choice's
  `AFFECTS_GOAL`, have no definition on the goal's side.

`PRACTICED_AT_EVENT` fits none of the four: both ends read it, with two meanings. The principle
declares it principle → event (`practice_events`); the event reads it as incoming
`practiced_habits`, and the user-context statement matches it as habit → event.

The detail pages are further off. Their lists name five edge types that do not exist, and about half
the links show on neither page — 11 of the 23 edges in the arc document's census, and 7 of the 14
live edges: a principle ↔ goal link made at either end (`GUIDES_GOAL`, `GUIDED_BY_PRINCIPLE`), a
principle → choice or principle → habit link made at the principle (`GUIDES_CHOICE`,
`INSPIRES_HABIT`), a choice ↔ goal link of either kind (`AFFECTS_GOAL`, `INSPIRED_BY_CHOICE`),
`PRACTICED_AT_EVENT`, `EXECUTES_TASK`, `IMPLEMENTS_CHOICE`, and the event ↔ choice pair
(`TRIGGERS_CHOICE`, `SCHEDULES_EVENT`). Only `FULFILLS_GOAL` and `DEMONSTRATES_PRINCIPLE` are shown
on both pages. The pair-by-pair census is in the arc document.

What a person sees therefore depends on which page made a link and which reader asks. A few readers
union the two names by hand; the rest see half.

The question was put to the founder pair by pair (PE-1, a skills-review follow-up, registered
2026-10-02). The live graph holds fourteen edges between Activities, all authored in vault files:
twelve links, because each of the two goal ↔ principle links is stored once from each side. Moving
them costs almost nothing, so the design is chosen on its merits.

## Decision

### 1. A link between two Activities is one stored fact (R1)

A link is one edge. A link made on either page shows on both: a support added on the goal page
appears on the principle page. Every door that makes the link writes that same edge: the link
routes on both domains, both create paths, and ingestion from either file's frontmatter. Unlinking
from either side removes it for both.

The stored link does not record which page made it. There is no provenance property.

### 2. Each domain names the link from its own perspective (R2)

The perspective belongs to the domain's view of the link (its registry definition and its page),
not to the stored edge. The principle page says "goals this principle supports"; the goal page says
"principles that support this goal". The founder's framing: this is separation of concerns —
thinking about one Activity domain at a time.

One consequence is a reader rule. When an edge type has sources of more than one kind, a view that
lists one kind filters by the source's label, in the read itself. Once principles support goals, a
goal's "supporting habits" lists habits only, and its "supporting principles" lists principles only.

The rule binds every declaration of a view, and a domain declares its views once (R10): the page
reads the registry. Each registry definition the page shows carries that domain's name for the link
(`page_heading`), and the detail page and the list card render the domain's definitions in both
directions, grouped by that name. Two definitions share a name only when they are one link stored
under two names, and the page lists each far end once under it. The invariant test holds the page to
it: every end that reads a link between two Activities shows it, and no edge is listed twice.

### 3. Two links between a pair only when the two directions say different things (R3)

Four pairs keep a link in each direction, because each direction states something the other does
not. The founder named the first three; Event ↔ Choice stands on the same ground, with its storage
unchanged (§6):

| Pair | Link one | Link two |
|------|----------|----------|
| Principle ↔ Habit | principle *inspires* habit (`INSPIRES_HABIT`) | habit *embodies* principle (`EMBODIES_PRINCIPLE`) |
| Goal ↔ Choice | goal *inspired by* choice (`INSPIRED_BY_CHOICE`) | choice *affects* goal (`AFFECTS_GOAL`) |
| Habit ↔ Choice | habit *informs* choice (`INFORMS_CHOICE`) | choice *impacts* habit (`IMPACTS_HABIT`) |
| Event ↔ Choice | event *triggers* choice (`TRIGGERS_CHOICE`) | choice *schedules* event (`SCHEDULES_EVENT`) |

Each of these links is still one stored fact under §1, and both pages read it. An event's
`CONTRIBUTES_TO_GOAL` and `CELEBRATES_GOAL` are two links in the same direction: two different
statements, not one fact under two names (§6).

### 4. The same verb across domains where the meaning is the same (R4)

- Habits and principles both **support** goals: `SUPPORTS_GOAL`. The link carries the importance
  level habits' links carry (`essentiality`) whichever kind of entity supports the goal.
- Habits and principles both **inform** choices: `INFORMS_CHOICE`.
- Tasks and events both **contribute** to goals: `CONTRIBUTES_TO_GOAL` (R5). A task may contribute
  to several goals.

### 5. A goal's progress counts every contribution (R5, R6, R11)

The goal tally counts the tasks that contribute to a goal and the events that contribute to it, and
a task linked to several goals counts toward each. The tally is what a goal's progress is computed
from; today only task-based goals are recomputed from it, and which goals' progress the widened
tally feeds is settled with the count (arc document, O1).

A completed contribution is done and an open one is not yet done. A cancelled contribution, task or
event, is left out of the count (R11): it is no longer part of the goal's plan, so it does not hold
the goal's progress down. Today the tally counts a cancelled task as not done, so this changes the
rule for tasks as well as setting it for events. How a failed task counts is settled in the kickoff
of the PR that builds the count (arc document, O1).

### 6. Per-pair rulings

| Pair | Stored as (target) | First page reads it as | Second page reads it as |
|------|--------------------|------------------------|-------------------------|
| Principle → Goal | `SUPPORTS_GOAL`, with importance | principle: goals this principle supports | goal: principles that support this goal |
| Principle → Choice | `INFORMS_CHOICE` | principle: choices this principle informs | choice: principles that inform this choice |
| Principle ↔ Habit | `INSPIRES_HABIT` and `EMBODIES_PRINCIPLE` (two facts, §3) | both pages read both | — |
| Task → Goal | `CONTRIBUTES_TO_GOAL`, several goals per task, counted | task: goals this task contributes to | goal: contributing tasks |
| Event → Goal | `CONTRIBUTES_TO_GOAL` (counted) and `CELEBRATES_GOAL` | event: its goals | goal: contributing events, and separately celebrating events |
| Choice → Goal | `AFFECTS_GOAL` and `INSPIRED_BY_CHOICE` (two facts, §3) | choice: goals it affects | goal: choices that affect this goal, and the choices that inspired it |
| Task → Principle | `ALIGNED_WITH_PRINCIPLE` (unchanged; "aligned with" stays) | both pages | — |
| Event → Principle | `DEMONSTRATES_PRINCIPLE`, one link | event: principles this event demonstrates | principle: events where this principle is practiced |
| Event → Habit | `REINFORCES_HABIT`, one link | event: habits it reinforces | habit: events where this habit is practiced |
| Task → Habit, Event → Task, Task → Choice, Habit ↔ Choice, Event ↔ Choice | unchanged | each page shows its end | — |

"A principle practiced at an event" and "an event demonstrates a principle" are one fact, and so
are "a habit practiced at an event" and "an event reinforces a habit".

### 7. What retires (One Path Forward)

Six edge types leave the links between Activities: `GUIDES_GOAL`, `GUIDED_BY_PRINCIPLE`,
`GUIDES_CHOICE`, `INFORMED_BY_PRINCIPLE`, `FULFILLS_GOAL` and `PRACTICED_AT_EVENT`. With them go the
single-valued `Task.fulfills_goal_uid`, which becomes plural or is dropped for edges only (a choice
for the PR that retires `FULFILLS_GOAL`), and the event's `practiced_habits` view (its registry
definition and the readers built on it; no event page shows it).

Retiring a type removes all of it in the PR that replaces it: the enum member, its registry
definitions, its `GRAPH_CONTRACT.yaml` rows, the frontmatter fields that author it, its doors, the
stored edges (migrated), and the vault files that declare it. No alias remains.

Five of the six retire outright. `GUIDED_BY_PRINCIPLE` also has a source outside the Activities: a
PathStep's guiding principles. The rulings cover links between Activities only, so whether that
curriculum link keeps the type or moves is open (arc document, O2), deferred by the founder. Until
it is settled, `GUIDED_BY_PRINCIPLE` stays in the enum with that one source and the goal's use
retires alone; if the PathStep's use later moves, all six types go.

### 8. Scope (R8)

This decision covers storage and visibility. Page controls for making a link from either side
are the next arc. Creating the links nothing writes today (a task implements a choice, a habit
informs a choice, an event triggers a choice, a choice schedules an event, an event demonstrates a
principle) is neither storage nor visibility, so it is outside this decision; which later arc takes
it was not ruled. Links between two entities of the same kind (task dependencies, principle ↔
principle, habit prerequisites) are a later pass.

## Alternatives Considered

### Alternative 1: Two declarations, one per side
**Description:** keep each side's edge as its own statement, and give the principle readers for
the goal-side and choice-side edges so each declaration shows on both pages.
**Pros:** no migration; each edge records which side declared it.
**Cons:** one link reads under two names on the same page, and every reader must know to union
them.
**Why rejected:** R1 and R2. The founder answered "yes" to the test (a support added on the goal page
appears on the principle page), so a link is one fact, not two declarations. Recording which side
declared it, this alternative's one advantage, is the provenance R2 rules out; the two statements are
the two pages' perspectives on that one link (§1, §2).

### Alternative 2: Always write both edges
**Description:** every door writes the pair and every unlink deletes the pair, as the lateral
system's `auto_inverse` does for `BLOCKS` / `BLOCKED_BY`.
**Pros:** every existing reader keeps working.
**Cons:** two edges per fact forever, and every writer must keep them in step, including hand-authored
vault files. The content vault already authors each of its two goal ↔ principle links in both files,
four edges for two facts.
**Why rejected:** it stores the same fact twice.

### Alternative 3: Leave storage; readers take the union
**Description:** every reader of a two-name link matches both names.
**Pros:** the smallest change.
**Cons:** every new reader has to know which links need a union. Today a few readers union by hand,
every other reads one name, and the choice-adherence query reads a third name that choices never
write.
**Why rejected:** it leaves the defect in place for the next reader.

### Alternative 4: A provenance property on the one edge
**Description:** one edge, marked with the page that made it.
**Pros:** keeps the "where was it entered" information.
**Cons:** nothing reads it, and it brings back two kinds of the same link.
**Why rejected:** R2 — the perspective lives in the page.

### Alternative 5: A per-request `bidirectional` flag
**Description:** the caller chooses whether a link is written to both sides (the removed
`PrincipleLinkRequest.bidirectional`).
**Pros:** none over Alternative 2.
**Cons:** whether a link shows on both pages becomes each caller's choice, so no reader can trust
either side alone, and unlinking becomes ambiguous.
**Why rejected:** a fact's shape cannot depend on the door that wrote it.

## Consequences

- **Positive:** each link lives in one place and every page shows it. The goal tally counts every
  task and event that contributes to a goal. Five or six edge types fewer (six unless O2 keeps
  `GUIDED_BY_PRINCIPLE` for a PathStep's guiding principles), and a property of the registry that can
  be tested: every link between Activities has a view on both ends.
- **Negative:** a migration of stored edges (six of the fourteen today: the four principle ↔ goal
  edges become two, and two task → goal edges change type) and a change to vault authoring:
  the retired frontmatter fields stop working, and the vault files that use them are edited in the
  same PR. A view over a shared edge type must filter by source label, and a new reader can forget
  to. The arc's invariant test checks the registry's definitions, and through them the pages once
  they read the registry (R10); a reader written in hand Cypher is outside it. `Task.fulfills_goal_uid`
  changes shape.
- **Neutral:** every other pair keeps its edge type and gains views, not a migration: the pairs that
  keep two links (§3) and the task → principle, event → goal, event → principle, event → habit,
  task → habit, event → task and task → choice pairs (§6). `GUIDES_CHOICE`, `INFORMED_BY_PRINCIPLE`
  and `PRACTICED_AT_EVENT` hold no stored edges today, so retiring them moves nothing.

## Records this ADR amends

Each record below gets its note in the PR whose code makes the change true. (The PR that added this
ADR corrected cells of ADR-057's diagonals table and of the Sibling Signal and Shared Signal
patterns that named edges nothing carries — a task's `GUIDED_BY_PRINCIPLE`, `ADVANCES_GOAL`,
`OCCURS_AT`, `MASTERED_AT`, `OWNED_BY`. That was a correction of fact, not an amendment.)

- [ADR-057](ADR-057-activity-domain-sibling-signals.md) § Diagonals — the "Values anchor
  direction" row (Principles → Goals) names `GUIDED_BY_PRINCIPLE`, which becomes `SUPPORTS_GOAL`
  (PR 2); its Context paragraph lists `GUIDED_BY_PRINCIPLE` and `INFORMED_BY_PRINCIPLE` among the
  edges that connect the Activity domains (PR 2, PR 3).
- [ADR-015](ADR-015-mega-query-rich-queries-completion.md) § Decision (the Principles, Choices and
  Events rich queries) and its Domain Relationship Mappings — the user-context traversals it records
  include `GUIDES_GOAL` (`guided_goals`, PR 2), `GUIDES_CHOICE` (`guided_choices`) and
  `INFORMED_BY_PRINCIPLE` (`guiding_principles`, PR 3), and `PRACTICED_AT_EVENT` (the event's
  `practiced_habits`, PR 5).

## Implementation Details

The arc document carries the rulings, the verified census, the open items and the per-PR scope and
acceptance. This ADR is marked implemented when the arc closes.

## Changelog

- 2026-10-04 — Accepted (Activity Links arc PR 0, #1498).
- 2026-10-04 — Round 5: the page reads the registry (R10, §2) and a cancelled contribution is left
  out of the count (R11, §5); the PathStep's `GUIDED_BY_PRINCIPLE` (O2) is deferred (§7).
- 2026-10-04 — §2 implemented for the pages (Activity Links arc PR 1b): `page_heading` on the
  registry definition; the hand-written page lists are deleted.
