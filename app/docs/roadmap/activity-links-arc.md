---
title: "Activity Links Arc — Rulings & Contract"
updated: 2026-10-04
status: "active — ruled 2026-10-04 (four rounds); PR 0 (this document + ADR-090) in review; O4 (where a page's view is declared) waits on the founder before PR 1b"
registered: 2026-10-02
ruled: 2026-10-04
---

# Activity Links Arc — Rulings & Contract

**Status:** ACTIVE — ruled 2026-10-04 (founder rulings R1–R9, four rounds). Every PR runs in a
**fresh local session**, one row of the [PR ledger](#pr-ledger) each. This document is the single
source of truth for the arc, and the ledger's **Status** column is its progress record.
**Decision record:** [ADR-090 — One Link per Fact, a View per Domain](../decisions/ADR-090-one-link-per-fact-a-view-per-domain.md).
**Grew out of:** PE-1, a skills-review follow-up registered 2026-10-02 when NB-2b removed
`PrincipleLinkRequest.bidirectional`. No principle registry definition read a principle link made on
the goal or the choice; the principle's page showed the choice-side link (`INFORMED_BY_PRINCIPLE`)
but not the goal-side one (`GUIDED_BY_PRINCIPLE`).
**Related:** [ADR-026](../decisions/ADR-026-unified-relationship-registry.md) (the registry that
declares each domain's view of its links); [ADR-087](../decisions/ADR-087-status-guarded-conditional-writes.md)
(a goal's tally is recomputed under its lock); [Goal Tally Membership Changes Don't Recompute](goal-tally-membership-changes.md)
and [Mixed Goals Get No Event-Driven Progress](mixed-goal-event-progress.md) (both touch the
tally PR 4 widens); [Relationships Architecture](../architecture/RELATIONSHIPS_ARCHITECTURE.md).

---

## Intent

The six Activity domains link to each other through edges each domain declares for itself. The
links grew one domain at a time, so the same kind of link is stored in four different ways
(ADR-090 § Context), and whether a page shows a link depends on which page made it. Most links show
on neither page: a detail page reads its own hand-written list of edge types, one direction per
domain, which misses most of the links its domain writes (§ What each layer shows today).

After this arc, a link between two Activities is one stored fact that both pages show, each in its
own words. The goal tally counts every task and event that contributes to a goal (which goals'
progress the tally feeds: O1).

## Founder rulings (2026-10-04 — do not re-litigate)

| # | Ruling |
|---|--------|
| R1 | **A link between two Activities is ONE stored fact.** A link made on either page shows on both. The founder's "yes" to the test: a support added on the goal page appears on the principle page. |
| R2 | **Each domain names the link from its own perspective.** The principle page says "goals this principle supports"; the goal page says "principles that support this goal". The perspective lives in the page, not in the stored link: there is no provenance property. The founder's framing: separation of concerns, "thinking in terms of one Activity domain at a time". |
| R3 | **Two links between a pair only when the two directions say different things:** principle inspires habit ≠ habit embodies principle; goal inspired by choice ≠ choice affects goal; habit informs choice ≠ choice impacts habit. |
| R4 | **The same verb across domains where the meaning is the same:** habits and principles both *support* goals, with the importance level habits carry; habits and principles both *inform* choices. |
| R5 | **Task → goal is "contributes"** (`CONTRIBUTES_TO_GOAL`, shared with events); `FULFILLS_GOAL` retires. A task may serve SEVERAL goals and counts toward each goal's progress. |
| R6 | **A contributing event counts toward the goal's progress.** How a cancelled contribution counts is settled in PR 4's kickoff (O1). |
| R7 | **"Practiced at an event" is the event's link, read from the other side.** An event demonstrating a principle and the principle being practiced at the event are one fact ("the same, yet different perspectives"). So are an event reinforcing a habit and the habit being practiced at the event. `PRACTICED_AT_EVENT` retires. |
| R8 | **Scope: storage and visibility only.** "Link from this page" controls are the NEXT arc. Same-type pairs are a later pass. |
| R9 | **Vault files: the PR session edits them.** The content vault (`/home/mike/0bsidian/0vault/`) and the personal vault (`/home/mike/0bsidian/skuel/`) are outside the repo. Before the PR, census every retired frontmatter field in both; edit them in the same session, re-sync, then verify the live edges. |

Not ruled: creating the links nothing writes today (`IMPLEMENTS_CHOICE`, `INFORMS_CHOICE` from a
habit, `TRIGGERS_CHOICE`, `SCHEDULES_EVENT` from a choice, `DEMONSTRATES_PRINCIPLE`) is neither
storage nor visibility, so it falls outside this arc under R8; which later arc takes it was not put
to the founder.

## Target, pair by pair

| Pair | Stored today | Target | Ruling |
|------|--------------|--------|--------|
| Principle → Goal | `GUIDES_GOAL` (written at the principle) and `GUIDED_BY_PRINCIPLE` (written at the goal) | ONE edge `SUPPORTS_GOAL`, with the importance level habits carry; both old types retire | R1, R2, R4 |
| Principle → Choice | `GUIDES_CHOICE` (at the principle) and `INFORMED_BY_PRINCIPLE` (at the choice) | ONE edge `INFORMS_CHOICE`; both old types retire | R1, R2, R4 |
| Principle ↔ Habit | `INSPIRES_HABIT` and `EMBODIES_PRINCIPLE` | unchanged — two facts, each shown on both pages | R3 |
| Task → Goal | `FULFILLS_GOAL` (one goal per task at the app doors and in `fulfills_goal_uid`, but the vault door writes one edge per `connections.fulfills_goal` target, O3; each edge counted toward its goal's progress) and `CONTRIBUTES_TO_GOAL` (the task "link goal" door; never counted) | ONE edge `CONTRIBUTES_TO_GOAL`; a task may serve several goals and counts toward each; `FULFILLS_GOAL` retires | R5 |
| Event → Goal | `CONTRIBUTES_TO_GOAL` and `CELEBRATES_GOAL` | the goal page shows celebrating events and, separately, contributing events; a contributing event counts toward progress | R6 |
| Choice → Goal | `AFFECTS_GOAL` and `INSPIRED_BY_CHOICE` | keep both; the goal page gains "choices that affect this goal" | R3 |
| Task → Principle | `ALIGNED_WITH_PRINCIPLE` | unchanged ("aligned with" stays), shown on both pages | ruled round 3 |
| Event ↔ Principle | `DEMONSTRATES_PRINCIPLE` and `PRACTICED_AT_EVENT` (declared principle → event; the event reads it as `practiced_habits`) | ONE edge `DEMONSTRATES_PRINCIPLE`: the event says "principles this event demonstrates", the principle "events where this principle is practiced"; `PRACTICED_AT_EVENT` retires | R7 |
| Event → Habit | `REINFORCES_HABIT` | ONE fact; the habit page names it "events where this habit is practiced"; the event's `practiced_habits` retires with `PRACTICED_AT_EVENT` | R7 |
| Task → Habit, Event → Task, Task → Choice, Habit ↔ Choice, Event ↔ Choice | `REINFORCES_HABIT`, `EXECUTES_TASK`, `IMPLEMENTS_CHOICE`, `INFORMS_CHOICE` / `IMPACTS_HABIT`, `TRIGGERS_CHOICE` / `SCHEDULES_EVENT` | storage unchanged; each shown on both pages | R1 (creating the unwritten ones: outside this arc, R8) |

Same-type pairs — task dependencies (`DEPENDS_ON`, `ENABLES_TASK`, `BLOCKS` / `BLOCKED_BY`),
principle ↔ principle (`SUPPORTS_PRINCIPLE`, `CONFLICTS_WITH_PRINCIPLE`), habit prerequisites
(`REQUIRES_PREREQUISITE_HABIT`, `ENABLES_HABIT`) — are a later pass (R8). Only `BLOCKS` /
`BLOCKED_BY` of these is a lateral type; the rest are domain edges, and habit and principle facts
are split today between a lateral edge and a domain edge. That pass starts from a census the arc
already holds: task create writes a prerequisite as `BLOCKED_BY` with no `BLOCKS` partner, and the
dependency readers disagree (the planner and the user context read `DEPENDS_ON`, readiness reads
`BLOCKED_BY`, the blocking chain reads `BLOCKS`).

## Open items (not ruled)

Each is settled in prose before the first edit of the PR named.

- **O1 — How a cancelled contribution counts (PR 4).** Today the goal tally counts every linked task
  whose `completion_updates_goal` is not false: COMPLETED is done, and every other status, CANCELLED
  and FAILED included, is not done. A cancelled task therefore holds a goal's progress down.
  Cancelling an open task triggers no recompute (under today's rule nothing changes, but option (b)
  would need that trigger); cancelling a completed task is a reopen, and the `TaskReopened` it
  publishes recomputes the goal. An event's statuses are SCHEDULED, ACTIVE, COMPLETED and
  CANCELLED. Three ways to count an event: (a) exactly as a task, a cancelled event counted as not
  done; (b) the tally leaves CANCELLED out for tasks and events alike, and decides FAILED, a task-only
  status; (c) a rule per kind. Recommendation, not yet put to the founder: (b) — a cancelled
  contribution is no longer part of the goal's plan, so it should not count against it, and one rule
  for every contribution keeps the tally one statement. The kickoff also decides which goals' tally a
  contribution feeds (today only task-based goals are recomputed from it), and that an event's
  completion triggers the recompute as a task's does.
- **O2 — The PathStep's `GUIDED_BY_PRINCIPLE` (PR 2).** The type also has a curriculum source: a
  PathStep's guiding principles (`principle_uids` frontmatter; one live edge), read by the PathStep
  intelligence. The rulings cover links between Activities only. Retiring the goal's use of the type
  leaves two choices for the PathStep: keep the type for that one source, or move it. A question for
  the founder.
- **O3 — The shape of `Task.fulfills_goal_uid` (PR 4).** The field is single-valued and dual-written
  with the edge, but the two have already diverged. A vault task writes one `FULFILLS_GOAL` edge per
  `connections.fulfills_goal` target and stores only the first in the field. A task spawned from a
  PathStep template gets the field with no edge. Several goals per task make it a plural field or
  drop it for the edges alone (a GRAPH-NATIVE read). Settle it from its readers' census.
- **O4 — Where a page's view is declared (PR 1b).** A domain's view of its links is declared twice
  today. The registry definitions (`core/models/relationship_registry.py`) feed the context API and
  the services' relationship reads. The detail page's Connections section reads a second,
  hand-written list per domain (`core/utils/connection_configs.py`), with one direction per domain
  and raw strings. That second list has drifted: it names five edge types that do not exist
  (`REINFORCES_GOAL`, `INFORMED_BY_GOAL`, `REINFORCED_BY_PRINCIPLE`, `INFORMS_GOAL_STRATEGY`,
  `EXPRESSES_PRINCIPLE`). SKUEL030 cannot see them: they reach the query as a parameter, not as
  Cypher text. Recommendation, not yet put to the founder: one
  declaration. Each registry definition the page shows carries the domain's name for the link (R2),
  and the page renders its domain's definitions in both directions. `connection_configs.py` then
  retires. The alternative is to keep the hand lists and fix them in each PR, which leaves two
  declarations free to drift again.

## Verified ground truth (2026-10-04 — `main` `cb9741960`)

Verified by a read of the registry, the page lists, the doors and both vaults, and one read-only
graph probe. File names are hints for each PR's own census, not a census of record: re-verify every
claim before the first edit.

### What each layer shows today

"Registry" is the domain's relationship-registry definition, which the context API and the
services' relationship reads use. "Page" is the detail page's Connections section (and the list
card, which reads the same list). ✓ = that end reads the link; ✗ = it does not.

| Edge (from → to) | Registry: from / to | Page: from / to | Writers |
|------------------|---------------------|-----------------|---------|
| `GUIDES_GOAL` (Principle → Goal) | ✓ / ✓ | ✗ / ✗ | `POST /api/principles/link` (`link_type=goal`); principle frontmatter `connections.guides_goal` |
| `GUIDED_BY_PRINCIPLE` (Goal → Principle) | ✓ / ✗ | ✗ / ✗ | `POST /api/goals/link-principle`; goal create (`guiding_principle_uids`); goal frontmatter `connections.aligned_with_principle`; the DSL's `@context(goal) @link(principle:…)` |
| `GUIDES_CHOICE` (Principle → Choice) | ✓ / ✓ | ✗ / ✗ | `POST /api/principles/link` (`link_type=choice`); no frontmatter field |
| `INFORMED_BY_PRINCIPLE` (Choice → Principle) | ✓ / ✗ | ✗ / ✓ | `POST /api/choices/link-principle`; choice frontmatter `connections.guided_by_principle` |
| `INSPIRES_HABIT` (Principle → Habit) | ✓ / ✓ | ✗ / ✗ | `POST /api/principles/link` (`link_type=habit`); principle frontmatter `connections.inspires_habit` |
| `EMBODIES_PRINCIPLE` (Habit → Principle) | ✓ / ✓ | ✗ / ✓ | `POST /api/habits/link-principle`; habit create (`linked_principle_uids`); the DSL; habit frontmatter `connections.embodies_principle` |
| `SUPPORTS_GOAL` (Habit → Goal) | ✓ / ✓ | ✗ / ✓ | habit create (`linked_goal_uids`) and goal create (`supporting_habit_uids`), both `essentiality: "supporting"`; the DSL's `@context(habit) @link(goal:…)` (through habit create); habit `connections.supports_goal` and goal `connections.supporting_habits` frontmatter (no properties) |
| `FULFILLS_GOAL` (Task → Goal) | ✓ / ✓ | ✓ / ✓ | task create and update (`fulfills_goal_uid`, the form's goal picker); task frontmatter `connections.fulfills_goal`; the DSL's `@context(task) @link(goal:…)`; the goal task generator |
| `CONTRIBUTES_TO_GOAL` (Task → Goal) | ✓ / ✗ | ✗ / ✓ ¹ | `POST /api/tasks/link-goal` |
| `CONTRIBUTES_TO_GOAL` (Event → Goal) | ✓ / ✗ | ✗ / ✓ ¹ | `POST /api/events/link-goal`; event create (`contributes_to_goal_uids`, API only); the habit event scheduler; event frontmatter `connections.contributes_to_goal` |
| `CELEBRATES_GOAL` (Event → Goal) | ✓ / ✗ | ✓ / ✗ | the event form's "Milestone for goal" picker (create and edit); the PathStep engagement spawn |
| `AFFECTS_GOAL` (Choice → Goal) | ✓ / ✗ | ✗ / ✗ | `POST /api/choices/link-goal`; choice frontmatter `connections.affects_goal` |
| `INSPIRED_BY_CHOICE` (Goal → Choice) | ✓ / ✓ | ✗ / ✗ | the PathStep engagement spawn |
| `ALIGNED_WITH_PRINCIPLE` (Task → Principle) | ✓ / ✓ | ✗ ² / ✓ | task create only ³ |
| `DEMONSTRATES_PRINCIPLE` (Event → Principle) | ✓ / ✓ | ✓ / ✓ | none |
| `PRACTICED_AT_EVENT` (Principle → Event) | ✓ / ✓ ⁴ | ✗ / ✗ | none |
| `REINFORCES_HABIT` (Task or Event → Habit) | ✓ / ✓ | ✓ / ✗ | task create, update and frontmatter; event create and update (the event form's habit picker), the habit event scheduler and event frontmatter; the PathStep engagement spawn |
| `EXECUTES_TASK` (Event → Task) | ✓ / ✓ | ✗ / ✗ | event frontmatter `connections.executes_task` |
| `IMPLEMENTS_CHOICE` (Task → Choice) | ✓ / ✓ | ✗ / ✗ | none |
| `INFORMS_CHOICE` (Habit → Choice) | ✓ / ✓ | ✓ ⁵ / ✗ | none from a habit |
| `IMPACTS_HABIT` (Choice → Habit) | ✓ / ✓ | ✗ / ✓ ⁵ | choice frontmatter `connections.impacts_habit` (the door-less `ChoicesService.link_choice_to_habit` is registered PLANNED) |
| `TRIGGERS_CHOICE` (Event → Choice) | ✓ / ✓ | ✗ / ✗ | none |
| `SCHEDULES_EVENT` (Choice → Event) | ✓ / ✓ | ✗ / ✗ | none from a choice |

A content-vault Edge file can author any of these types as well.

1. The goal page lists a contributing task under "Tasks fulfilling this goal", so a task with both
   edges is listed twice, and lists a contributing event under "Events contributing" with a link to
   `#`.
2. The task page's list names `INFORMED_BY_PRINCIPLE`, a type no task writes, instead of
   `ALIGNED_WITH_PRINCIPLE`.
3. A task update stores `aligned_principle_uids` as a node property instead of writing edges.
4. Declared principle → event on the principle and as incoming `practiced_habits` on the event;
   the user-context statement reads it as habit → event.
5. Through the habit page's choices fragment, not its Connections section.

A few readers union a link's two names by hand: `cross_domain_backend.py`'s alignment-evidence query
and its goals-for-tasks batch query (`CONTRIBUTES_TO_GOAL|FULFILLS_GOAL`); `GoalCrossContext` and
`ChoiceCrossContext` (both principle directions), `TaskCrossContext` (contributing goals ∪ the
fulfilled goal) and `EventCrossContext` (reinforced ∪ practiced habits); and the choice-alignment
metric. This list is a hint, not a census: the PR that collapses a link greps for both its names.

### The live graph (AuraDB, read-only)

Every edge between two Activity nodes (fourteen), and the PathStep edges onto an Activity whose type
an Activity view also reads:

| Source → target | Edge | Count |
|-----------------|------|-------|
| Goal → Principle | `GUIDED_BY_PRINCIPLE` | 2 |
| Principle → Goal | `GUIDES_GOAL` | 2 |
| Principle → Habit | `INSPIRES_HABIT` | 3 |
| Habit → Principle | `EMBODIES_PRINCIPLE` | 2 |
| Habit → Goal | `SUPPORTS_GOAL` | 2 |
| Task → Goal | `FULFILLS_GOAL` | 2 |
| Task → Habit | `REINFORCES_HABIT` | 1 |
| PathStep → Principle | `GUIDED_BY_PRINCIPLE` | 1 |
| PathStep → Event | `SCHEDULES_EVENT` | 1 |

No `CONTRIBUTES_TO_GOAL`, `CELEBRATES_GOAL`, `AFFECTS_GOAL`, `PRACTICED_AT_EVENT` or choice edge
exists. The two goal ↔ principle links are authored on both sides, so two facts are held as four
edges — the case the arc collapses.

### The vaults

- **Content vault:** six files author a retiring type through frontmatter. `FULFILLS_GOAL`
  (`connections.fulfills_goal`): two task files. `GUIDED_BY_PRINCIPLE`: one goal file
  (`connections.aligned_with_principle`) and one PathStep file (`principle_uids`). `GUIDES_GOAL`
  (`connections.guides_goal`): two principle files. No Edge file uses a retiring type.
- **Personal vault:** no file authors a retiring type. Two userguides show
  `@context(goal) @link(principle:…)`, which writes `GUIDED_BY_PRINCIPLE` through the DSL.

### Readers that share an edge type

A definition whose far end is `Entity` lists every source of its edge type, and the curriculum
already writes several of these types:

- The goal's unfiltered `SUPPORTS_GOAL` view (`supporting_habits`) also lists PathSteps
  (`goal_uids`). The essential / critical / optional views filter on `essentiality`, which a
  PathStep's edge never carries (§ The importance level). Principles join in PR 2, with the
  importance level.
- The choice's `informing_habits` (`INFORMS_CHOICE`) also lists PathSteps (`choice_uids`).
  Principles join in PR 3.
- The principle's `embodying_habits` (`EMBODIES_PRINCIPLE`) also lists learning paths
  (`connections.embodied_principles`).
- The event's `scheduled_by_choices` (`SCHEDULES_EVENT`) lists PathSteps (`event_uids`), the only
  writer of that type; the live graph holds one.
- From PR 4, any goal-side `CONTRIBUTES_TO_GOAL` view, written by tasks and events.

**A definition's `target_label` is not a filter on its own:** neither per-key reader passes it.
`get_related_uids` passes the edge type, the direction and the definition's edge-property filter.
`get_related_with_metadata` passes the edge type and the direction, plus the edge properties to
return and an ordering, but no edge-property filter, so a tiered definition read through it returns
every edge of its type. A view that splits by source label, or by tier, needs that filter in the
read.

### The importance level

`SUPPORTS_GOAL` carries `essentiality` (`HabitEssentiality`: essential, critical, supporting,
optional) beside `weight`. Both create doors store `supporting`, and vault edges carry no property.
The registry's three tiered views (essential, critical, optional) are therefore empty today; the
unfiltered view lists everything.

### Retiring a type: what it touches

- 145 tracked files name one of the six types (`git grep -w`; tests 43, docs and skills 54).
  Every docs mention outside records is swept by the PR that retires the type.
- Hand-written Cypher names the types directly, so no registry edit reaches it: the user-context
  statements (`user_context_queries.py`: `FULFILLS_GOAL`, `PRACTICED_AT_EVENT`, `GUIDES_GOAL`,
  `GUIDES_CHOICE`, `INFORMED_BY_PRINCIPLE`), the goal tally (`goal_tally_queries.py`,
  `activity_backends.py`, `cross_domain_backend.py`), and `activity_backends.py`'s achievement
  context and choice-influence stats.
- Ingestion writes edges from the registry (`yaml_field_path`), so a type's edges leave ingestion
  with its registry definition. The task's goal field is the exception:
  `preparer._reconcile_task_goal_link` stamps `fulfills_goal_uid` from `connections.fulfills_goal`
  and turns a bare `fulfills_goal_uid` into that field, and `vault_policy`'s `_TASK_GOAL_FIELD` /
  `_TASK_GOAL_COLUMN` realign the column when a goal target is refused. Both name the field and the
  column, not the type, so `git grep -w FULFILLS_GOAL` misses them; PR 4 settles both with O3. Two
  field names disagree with the edge they write today: goal
  `connections.aligned_with_principle` writes `GUIDED_BY_PRINCIPLE`, and choice
  `connections.guided_by_principle` writes `INFORMED_BY_PRINCIPLE`
  (pinned by `tests/unit/test_ingestion_relationship_config.py`).
- **Migrate before the enum member goes.** A content-vault Edge file naming a deleted type becomes a
  validation error, and an `authored_edges` tracker row naming one is skipped, so the edge it
  recorded would never be retracted. Convert or delete the stored edges in the same PR.
- `GRAPH_CONTRACT.yaml` is generated (`uv run python scripts/generate_graph_contract.py`) and
  drift-tested.

### Defects found by the census

Each is fixed by the PR named, or registered there if it falls outside the arc:

- The page lists' five nonexistent edge names; the task page's `INFORMED_BY_PRINCIPLE`; the habit
  page's `APPLIES_KNOWLEDGE` (habits write `REINFORCES_KNOWLEDGE`); the choice page's
  `APPLIES_KNOWLEDGE` (choices write `INFORMED_BY_KNOWLEDGE` and `REQUIRES_KNOWLEDGE_FOR_DECISION`)
  and `ENABLES_HABIT` (a habit-prerequisite edge no choice writes); the goal page's incoming
  `APPLIES_KNOWLEDGE` (no definition or writer points that edge at a goal), its `#` links and its
  double-listed task — **PR 1b**.
- `cross_domain_backend.py`'s alignment-evidence query tests `(goal)-[:EMBODIES_PRINCIPLE]->`, a
  shape nothing writes — **PR 2**.
- `cross_domain_backend.py`'s choice-adherence query reads `(choice)-[:ALIGNED_WITH_PRINCIPLE]->`,
  but choices write `INFORMED_BY_PRINCIPLE` — **PR 3**.
- Search enrichment ignores the choice's shared-neighbour `related_choices` definition and matches its
  placeholder type directly, so `related_choices` holds principles, not choices — **PR 3**.
- `PrinciplesSearchService.get_for_habit` reads `(habit)-[:ALIGNED_WITH_PRINCIPLE]->`, but habits
  write `EMBODIES_PRINCIPLE` (its facade has no caller outside tests) — **PR 5**.
- A task update stores `aligned_principle_uids` as a node property instead of edges — **PR 5**.
- The user-context statement reads a habit's `FULFILLS_GOAL`, which nothing writes — **PR 4**.
- `Task.fulfills_goal_uid` and its edge diverge at the vault door and the PathStep spawn (O3) —
  **PR 4**.

## PR ledger

Rows run in order. PR 1 needs PR 0. PR 1b needs PR 1 and O4. PRs 2–5 each need PR 1b, and each
shrinks PR 1's known-gaps list. PRs 2 and 3 are independent of each other. PR 4 rewrites the goal
tally, so it runs after PR 2 to keep the goal page's changes apart. PR 5 runs last.

| PR | Scope | Acceptance | Status |
|----|-------|------------|--------|
| 0 | This document, ADR-090, the INDEX rows and the skill back-link; the cells of ADR-057's diagonals table and of the Sibling Signal and Shared Signal patterns that named edges nothing carries (docs only; summon Codex explicitly) | Merged; `./dev docs-links`, the dead-link scan and the skills validator clean | in review |
| 1 | The invariant as a test, derived from the registry: every edge type joining two different Activity domains is read at BOTH ends (same-type edges are the later pass, R8), and a view over an edge type with several kinds of source filters by source label in the read. Lands with a known-gaps list | Passes with the list; removing any entry turns it red; a one-sided definition added turns it red | — |
| 1b | The pages show both ends, by the route O4 settles (recommended: the page renders the registry's labelled definitions in both directions and `connection_configs.py` retires); the page-list defects (§ Defects found by the census) | Every link in § What each layer shows today that the registry reads at both ends shows on both detail pages; the five nonexistent names are gone | waits on O4 |
| 2 | Principle → goal: `SUPPORTS_GOAL` with the importance level; label-split goal views; retire `GUIDES_GOAL`, and `GUIDED_BY_PRINCIPLE` between Activities (its enum member goes only if O2 moves the PathStep's use; O2 first) | A link made at any door shows on both pages; the live pairs migrated (four edges become two) and shown from both ends; the gaps list shrinks | — |
| 3 | Principle → choice: `INFORMS_CHOICE`; label-split choice views; retire `GUIDES_CHOICE` / `INFORMED_BY_PRINCIPLE` | As PR 2, for choices | — |
| 4 | "Contributes": tasks serve several goals through `CONTRIBUTES_TO_GOAL`; retire `FULFILLS_GOAL` and settle `Task.fulfills_goal_uid` (O3); the task form's goal picker; the goal's progress counts contributing tasks AND events (O1 first) | A task linked to two goals counts toward both; a completed contributing event moves the goal's progress; the gaps list shrinks | — |
| 5 | The remaining views: the goal sees choices (affects) and events (celebrates, contributes) apart; event ↔ principle is one link (retire `PRACTICED_AT_EVENT` and the event's `practiced_habits`); the habit names `REINFORCES_HABIT` from events "events where this habit is practiced"; the views still sharing an edge type split by source label (the habit's `REINFORCES_HABIT` views, the principle's `embodying_habits`, the event's `scheduled_by_choices`); a task update writes `ALIGNED_WITH_PRINCIPLE` edges instead of a node property | PR 1's known-gaps list is empty | — |
| close | ADR-090 marked implemented; this document to `done/` (docs only) | Every retired type reads 0 in the live graph and in live code (`GUIDED_BY_PRINCIPLE`: between Activities, or wholly if O2 moved the PathStep's use) | — |

## Choices — per PR

Each section stands alone for a fresh context: census before the first edit, re-verify every
symbol, and update the ledger row as the PR's last commit.

### PR 0 — Arc record (docs only)

This document; ADR-090 and its skill back-link (`activity-domains` lists it); the INDEX rows. The
census found two "graph edge today" cells in ADR-057's diagonals table, mirrored in
`docs/patterns/SIBLING_SIGNAL_PATTERN.md`, that named edges nothing carries: a task's
`GUIDED_BY_PRINCIPLE` (a task's principle edge is `ALIGNED_WITH_PRINCIPLE`) and `ADVANCES_GOAL` (an
event's goal edge is `CONTRIBUTES_TO_GOAL`); the pattern's mapping table also named
`(Event)-[:OCCURS_AT]->(TimeSlot)`, and its companion `docs/patterns/SHARED_SIGNAL_PATTERN.md` named
the same, plus `MASTERED_AT` (the edge is `MASTERED`) and `OWNED_BY` (ownership is `OWNS`).
Corrected here.

**Acceptance:** merged; `./dev docs-links`, the dead-link scan and the skills validator are clean.

### PR 1 — The invariant, as a test

A unit test derived from the registry, not from a hand list. For every edge type joining two
different Activity domains, both domain configs carry a definition that reaches the other end.
Same-type edges (task ↔ task, habit ↔ habit, principle ↔ principle, …) are the later pass (R8) and
outside the test: several are read at one end only today, and no PR in this arc removes them. Every
definition over an edge type with more than one kind of source filters by source label, in the read
and not only in `target_label` (§ Readers that share an edge type). Key on the definition's
`method_key`: a definition's context name and method key can differ (the task's
`implements_choices` has the context name `implemented_choices`). The gaps found on the day are
the known-gaps list, each entry naming the PR that removes it.

**Acceptance:** the test passes with its list; removing any entry turns it red; a one-sided
definition added turns it red.

### PR 1b — The pages show both ends

O4 is settled first. On the recommended route, a registry definition that the page shows carries the
domain's name for the link. The detail page and the list card render the domain's definitions in both
directions, grouped by link rather than by the far end's type, so that celebrating and contributing
events are listed apart. `core/utils/connection_configs.py` and its consumers' wiring retire. PR 1's
invariant then covers the pages. The page-list defects go with it.

**Acceptance:** every link that the registry reads at both ends shows on both detail pages, under
each domain's name for it; a real-graph route test per pair, red on the old source.

### PR 2 — Principle → goal

`SUPPORTS_GOAL` from principles, with the importance level (`essentiality`) habits carry; the doors
store the same default habits' doors do. The goal's views split by source label: supporting habits,
supporting principles. Retire `GUIDES_GOAL` and `GUIDED_BY_PRINCIPLE`: the enum members, registry
definitions, `GRAPH_CONTRACT.yaml`, the frontmatter fields, the doors (`/api/principles/link`'s goal
type, goal `link-principle`, goal create, the DSL's goal → principle link), the migration of the
stored edges, the vault files (R9) and the docs that name the types. `GUIDED_BY_PRINCIPLE`'s enum
member, PathStep definition and contract rows go only if O2 moves the PathStep's use; O2 is settled
first. Add the retired names to `scripts/health/stale_names.py`. The scanner has no directory
exclusion and reads only backtick spans and fences, so every mention left in a record needs its own
line-anchored `ALLOWED_OCCURRENCES` entry: ADR-090, this document, `docs/INDEX.md`'s ADR-090 row and
the older ADRs that keep the names (today ADR-015 and ADR-057). Run it with `--verbose` after adding
the names and take the anchors from its output.

**Acceptance:** real-graph tests — a link made at either door is returned by both entities' views,
under one key each; unlinking at either door removes it for both; the migration leaves the live
pairs as one edge each, shown from both ends; red on the old source.

### PR 3 — Principle → choice

As PR 2, with `INFORMS_CHOICE` and the choice's views, retiring `GUIDES_CHOICE` and
`INFORMED_BY_PRINCIPLE`. The choice-alignment metric, `ChoiceCrossContext` and the
choice-adherence query read the one edge.

**Acceptance:** as PR 2.

### PR 4 — "Contributes"

Tasks link to any number of goals through `CONTRIBUTES_TO_GOAL`. `FULFILLS_GOAL` retires, with
`Task.fulfills_goal_uid` reshaped (O3), the task form's goal picker, the vault field, the DSL's
task → goal link, the goal task generator and the readers in § Retiring a type. The goal's tally
counts contributing tasks and events under O1's rule, and an event's completion triggers the
recompute. Two readers need more than the type's deletion: the goal-cancel guard counts open tasks
over `FULFILLS_GOAL` only (`cross_domain_backend.py`) and must count open contributions (the kickoff
decides whether an open contributing event blocks a cancel), and `GOALS_CONFIG`'s shared-neighbour
`related_goals` definition names `FULFILLS_GOAL` as its placeholder type and as an intermediate edge
(search enrichment turns the placeholder into a goal ↔ goal arm). Both name the enum member, so
missing either breaks the import. The readers that fail silently name the type as a raw string: the
user-context statements, `cross_domain_backend.py`'s `_INTENT_EDGE_SETS["goal_achievement"]`, and
`connection_configs.py` if PR 1b has not retired it. The field's column-only readers (the goal Gantt, the relevance scorer) go
with O3. Update the [goal-tally case file](goal-tally-membership-changes.md), whose check names
`FULFILLS_GOAL`.

**Acceptance:** a task linked to two goals counts toward both; a completed contributing event
moves the goal's progress; the tally's statement and the user-context statements read the one edge;
red on the old source.

### PR 5 — The remaining views

The goal page reads `AFFECTS_GOAL`, and `CELEBRATES_GOAL` and `CONTRIBUTES_TO_GOAL` from events, as
separate lists. Event ↔ principle is `DEMONSTRATES_PRINCIPLE` alone: `PRACTICED_AT_EVENT` and the
event's `practiced_habits` retire, and the principle names the edge "events where this principle is
practiced". The habit names `REINFORCES_HABIT` from events "events where this habit is practiced".
The views PRs 2–4 leave sharing an edge type filter by source label in the read: the habit's
`REINFORCES_HABIT` views (tasks and events apart; the unfiltered `reinforcing_habits` is split or
retired), the principle's `embodying_habits` (habits, not learning paths) and the event's
`scheduled_by_choices` (choices, not PathSteps). A task update writes its `ALIGNED_WITH_PRINCIPLE`
edges, as task create does, instead of storing `aligned_principle_uids` as a node property; both
pages already show the link from PR 1b.

**Acceptance:** PR 1's known-gaps list is empty.

## Non-goals (this arc)

- Page controls for making a link from either side — the next arc.
- Creating the links nothing writes today (`IMPLEMENTS_CHOICE`, `INFORMS_CHOICE` from a habit,
  `TRIGGERS_CHOICE`, `SCHEDULES_EVENT` from a choice, `DEMONSTRATES_PRINCIPLE`) — outside this arc
  (R8); which later arc takes it is not ruled.
- Same-type pairs — a later pass.

## Standing conventions that bind every PR here

- One fresh local session per row; branch from `origin/main`.
- Prove each new test red on the old source before the summon.
- A retired type leaves nothing behind: enum, registry, `GRAPH_CONTRACT.yaml`, frontmatter fields,
  doors, stored edges, vault files, docs. `git grep -w <TYPE>` then finds it only in records (ADRs,
  `done/`, this document, ADR-090's row in `docs/INDEX.md`), in `scripts/health/stale_names.py` (its
  table entry and allowances), and in the stored-edge migration and its test.
- Vault edits (R9) are made in the same session, re-synced, and the live edges checked after.
- The ledger row is the PR's last commit.
