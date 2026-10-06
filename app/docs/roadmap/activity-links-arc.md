---
title: "Activity Links Arc — Rulings & Contract"
updated: 2026-10-06
status: "active — ruled 2026-10-04 (five rounds); PR 0 merged #1498; PR 1 merged #1500; PR 1b merged #1501; PR 1c merged #1503; PR 2 merged #1504; PR 3 merged #1505; PR 4 merged #1507; O1, O3 and O4 ruled (R10, R11, § PR 4); O2 deferred; PR 5 next"
registered: 2026-10-02
ruled: 2026-10-04
---

# Activity Links Arc — Rulings & Contract

**Status:** ACTIVE — ruled 2026-10-04 (founder rulings R1–R11, five rounds). Every PR runs in a
**fresh local session**, one row of the [PR ledger](#pr-ledger) each. This document is the single
source of truth for the arc, and the ledger's **Status** column is its progress record.
**Decision record:** [ADR-090 — One Link per Fact, a View per Domain](../decisions/ADR-090-one-link-per-fact-a-view-per-domain.md).
**Grew out of:** PE-1, a skills-review follow-up registered 2026-10-02 when NB-2b removed
`PrincipleLinkRequest.bidirectional`. No principle registry definition read a principle link made on
the goal or the choice; the principle's page showed the choice-side link (`INFORMED_BY_PRINCIPLE`)
but not the goal-side one (`GUIDED_BY_PRINCIPLE`).
**Related:** [ADR-026](../decisions/ADR-026-unified-relationship-registry.md) (the registry that
declares each domain's view of its links); [ADR-087](../decisions/ADR-087-status-guarded-conditional-writes.md)
(a goal's tally is recomputed under its lock); [Goal Tally Membership Changes Don't Recompute](done/goal-tally-membership-changes.md)
(closed by PR 4) and [Mixed Goals Get No Event-Driven Progress](mixed-goal-event-progress.md) (both
touch the tally PR 4 widens); [Relationships Architecture](../architecture/RELATIONSHIPS_ARCHITECTURE.md).

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
| R6 | **A contributing event counts toward the goal's progress.** A cancelled contribution is left out of the count (R11). |
| R7 | **"Practiced at an event" is the event's link, read from the other side.** An event demonstrating a principle and the principle being practiced at the event are one fact ("the same, yet different perspectives"). So are an event reinforcing a habit and the habit being practiced at the event. `PRACTICED_AT_EVENT` retires. |
| R8 | **Scope: storage and visibility only.** "Link from this page" controls are the NEXT arc. Same-type pairs are a later pass. |
| R9 | **Vault files: the PR session edits them.** The content vault (`/home/mike/0bsidian/0vault/`) and the personal vault (`/home/mike/0bsidian/skuel/`) are outside the repo. Before the PR, census every retired frontmatter field in both; edit them in the same session, re-sync, then verify the live edges. |
| R10 | **A page shows its links from the registry** (round 5, answering O4). Each registry definition the page shows carries that domain's name for the link (R2), the page renders its domain's definitions in both directions, and the hand-written lists in `core/utils/connection_configs.py` are deleted. |
| R11 | **A cancelled contribution, task or event, is left out of the goal's count** (round 5, answering O1). It is no longer part of the goal's plan, so it does not hold the goal's progress down. |

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
`BLOCKED_BY`, the blocking chain reads `BLOCKS`). PR 1b's census adds one: the task registry's
`subtasks` view names `HAS_CHILD`, but every task writer writes `HAS_SUBTASK`, which the task page's
Sub-tasks section reads through the hierarchy backend.

## Open items (not ruled)

Each is settled in prose before the first edit of the PR named. O1 and O4 were answered in round 5
(R10, R11) and O1's remainder and O3 before PR 4's first edit; O2 is deferred.

- **O1 — How a contribution counts (PR 4). RULED — cancelled left out for tasks and events alike
  (R11); the rest settled before PR 4's first edit (§ PR 4, settled list items 5 and 6).** What
  the rulings answered: today the goal tally counts every linked task
  whose `completion_updates_goal` is not false: COMPLETED is done, and every other status, CANCELLED
  and FAILED included, is not done. A cancelled task therefore holds a goal's progress down.
  Cancelling an open task triggers no recompute (under today's rule nothing changes, but option (b)
  would need that trigger); cancelling a completed task is a reopen, and the `TaskReopened` it
  publishes recomputes the goal. An event's statuses are SCHEDULED, ACTIVE, COMPLETED and
  CANCELLED. Three ways to count an event: (a) exactly as a task, a cancelled event counted as not
  done; (b) the tally leaves CANCELLED out for tasks and events alike, and decides FAILED, a task-only
  status; (c) a rule per kind. The founder chose (b). **Still open for PR 4's kickoff:** how a
  FAILED task counts (today: not done); which goals' tally a contribution feeds (today only task-based
  goals are recomputed from it); and the recompute triggers the rule now needs — any status write
  that moves a task or event between the tally's classes (done, not done, out). Today an open
  task's cancellation recomputes nothing, and events publish no reopen event: an event leaving
  COMPLETED, by the API or the vault, publishes only `CalendarEventUpdated`.
- **O2 — The PathStep's `GUIDED_BY_PRINCIPLE` (PR 2).** The type also has a curriculum source: a
  PathStep's guiding principles (`principle_uids` frontmatter; one live edge), read by the PathStep
  intelligence. The rulings cover links between Activities only. Retiring the goal's use of the type
  leaves two choices for the PathStep: keep the type for that one source, or move it. **Deferred by
  the founder (2026-10-04: "look at that closer later").** Until it is settled, the type stays in
  the enum with its one PathStep source; PR 2 retires only the goal's use and does not wait on it.
- **O3 — The shape of `Task.fulfills_goal_uid` (PR 4). RULED — dropped for the edges alone (§ PR 4,
  settled list item 2).** The field is single-valued and dual-written
  with the edge, but the two have already diverged. A vault task writes one `FULFILLS_GOAL` edge per
  `connections.fulfills_goal` target and stores only the first in the field. A task spawned from a
  PathStep template gets the field with no edge. Several goals per task make it a plural field or
  drop it for the edges alone (a GRAPH-NATIVE read). Settle it from its readers' census.
- **O4 — Where a page's view is declared (PR 1b). RULED (R10) — the page reads the registry.** What
  the ruling answered: a domain's view of its links is declared twice
  today. The registry definitions (`core/models/relationship_registry.py`) feed the context API and
  the services' relationship reads. The detail page's Connections section reads a second,
  hand-written list per domain (`core/utils/connection_configs.py`), with one direction per domain
  and raw strings. That second list has drifted: it names five edge types that do not exist
  (`REINFORCES_GOAL`, `INFORMED_BY_GOAL`, `REINFORCED_BY_PRINCIPLE`, `INFORMS_GOAL_STRATEGY`,
  `EXPRESSES_PRINCIPLE`). SKUEL030 cannot see them: they reach the query as a parameter, not as
  Cypher text. The founder chose one declaration over keeping the hand lists and fixing them in each
  PR, which would have left two declarations free to drift again.

## Verified ground truth (2026-10-04 — `main` `cb9741960`)

Verified by a read of the registry, the page lists, the doors and both vaults, and one read-only
graph probe. File names are hints for each PR's own census, not a census of record: re-verify every
claim before the first edit.

### What each layer shows today

The Page column records the hand-written lists PR 1b deleted. From PR 1b the page shows exactly the
registry's headed views, so the Page column equals the Registry column for every link between two
Activities. A link the registry reads at one end only (PR 1's `MISSING_ENDS`) shows at that end until its PR
adds the other: at the goal, `CELEBRATES_GOAL` and `AFFECTS_GOAL` (PR 5). From
PR 2 a principle ↔ goal link is one `SUPPORTS_GOAL` edge that both pages show, whichever door made
it; the live graph's four edges for its two links (§ The live graph) became two when PR 2's
stored-edge migration ran (2026-10-05). From PR 3 a principle ↔ choice link is one `INFORMS_CHOICE`
edge that both pages show, whichever door made it; the principle's one-ended entry left
`MISSING_ENDS` with the type it named. From PR 4 a task's or an event's contribution to a goal is
one `CONTRIBUTES_TO_GOAL` edge that both pages show, whichever door made it: the goal lists
contributing tasks and contributing events apart, and the event's goal-side entry left
`MISSING_ENDS`. A task spawned from a PathStep gets the edge from its template
(`contributes_to_goal_template_uid`), so it shows its goal like any other task.

"Registry" is the domain's relationship-registry definition, which the context API and the
services' relationship reads use. "Page" is the detail page's Connections section (and the list
card, which reads the same list). ✓ = that end reads the link; ✗ = it does not.

| Edge (from → to) | Registry: from / to | Page: from / to | Writers |
|------------------|---------------------|-----------------|---------|
| `SUPPORTS_GOAL` (Principle → Goal; from PR 2) | ✓ / ✓ | ✓ / ✓ | `POST /api/principles/link` (`link_type=goal`), `POST /api/goals/link-principle` and goal create (`supporting_principle_uids`), each `weight: 1.0`, `essentiality: "supporting"`; the DSL's `@context(goal) @link(principle:…)` (through goal create); principle `connections.supports_goal` and goal `connections.supporting_principles` frontmatter (no properties). On 2026-10-04 the link was two edges: `GUIDES_GOAL` from the principle's door and `connections.guides_goal`, read at both ends by the registry and by neither page; `GUIDED_BY_PRINCIPLE` from the goal's doors and `connections.aligned_with_principle`, read at the goal only |
| `INFORMS_CHOICE` (Principle → Choice; from PR 3) | ✓ / ✓ | ✓ / ✓ | `POST /api/principles/link` (`link_type=choice`) and `POST /api/choices/link-principle`, no properties; principle `connections.informs_choice` and choice `connections.informing_principles` frontmatter. On 2026-10-04 the link was two edges: `GUIDES_CHOICE` from the principle's door (no frontmatter field), read at both ends by the registry and by neither page; `INFORMED_BY_PRINCIPLE` from the choice's door (with `alignment_score`) and `connections.guided_by_principle`, read by the registry at the choice only |
| `INSPIRES_HABIT` (Principle → Habit) | ✓ / ✓ | ✗ / ✗ | `POST /api/principles/link` (`link_type=habit`); principle frontmatter `connections.inspires_habit` |
| `EMBODIES_PRINCIPLE` (Habit → Principle) | ✓ / ✓ | ✗ / ✓ | `POST /api/habits/link-principle`; habit create (`linked_principle_uids`); the DSL; habit frontmatter `connections.embodies_principle` |
| `SUPPORTS_GOAL` (Habit → Goal) | ✓ / ✓ | ✗ / ✓ | habit create (`linked_goal_uids`) and goal create (`supporting_habit_uids`), both `essentiality: "supporting"`; the DSL's `@context(habit) @link(goal:…)` (through habit create); habit `connections.supports_goal` and goal `connections.supporting_habits` frontmatter (no properties) |
| `CONTRIBUTES_TO_GOAL` (Task → Goal; from PR 4) | ✓ / ✓ | ✓ / ✓ | task create (`contributes_to_goal_uids`; the create form's goal picker), the task update's `contributes_to_goal_uids` (a full replace), `POST /api/tasks/link-goal`, task frontmatter `connections.contributes_to_goal`, the DSL's `@context(task) @link(goal:…)` (every goal the line names), the goal task generator, the PathStep engagement spawn (`contributes_to_goal_template_uid`); no properties. On 2026-10-04 the link was two edges: `FULFILLS_GOAL` from create and update (`fulfills_goal_uid`), the vault (`connections.fulfills_goal`), the DSL and the generator, read at both ends and counted; and `CONTRIBUTES_TO_GOAL` from the link door alone, read at the task only and never counted |
| `CONTRIBUTES_TO_GOAL` (Event → Goal) | ✓ / ✓ | ✓ / ✓ | `POST /api/events/link-goal` (no properties from PR 4); event create (`contributes_to_goal_uids`, API only); the DSL's `@context(event) @link(goal:…)` (from PR 4); the habit event scheduler; event frontmatter `connections.contributes_to_goal`. Read at the event only until PR 4 |
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

1. On 2026-10-04 the goal page listed a contributing task under "Tasks fulfilling this goal", so a
   task with both edges was listed twice, and a contributing event under "Events contributing" with
   a link to `#` (PR 1b removed both; PR 4 added the registry's two goal views).
2. The task page's list names `INFORMED_BY_PRINCIPLE`, a type no task writes, instead of
   `ALIGNED_WITH_PRINCIPLE`.
3. A task update stores `aligned_principle_uids` as a node property instead of writing edges.
4. Declared principle → event on the principle and as incoming `practiced_habits` on the event;
   the user-context statement reads it as habit → event.
5. Through the habit page's choices fragment, not its Connections section.

One reader still unions a link's two names by hand: `EventCrossContext` (reinforced ∪ practiced
habits, PR 5). PR 2 took two readers off this list: the alignment-evidence query and
`GoalCrossContext` each read the one principle → goal edge. PR 3 took two more:
`ChoiceCrossContext` and the choice-alignment metric each read the one principle → choice edge.
PR 4 took two more: `cross_domain_backend.py`'s goals-for-tasks batch query and `TaskCrossContext`
each read the one task → goal edge. This list is a hint, not a census: the PR that collapses a link greps for both its
names.

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

PR 2's migration ran on 2026-10-05: the four edges are two `SUPPORTS_GOAL` edges from the
principles, and its census afterwards found no old edge and no tracker key naming one. PR 3's census
(2026-10-05) found no principle ↔ choice edge of either retired type and no tracker row naming one,
so its migration has nothing to move.

PR 4's census (2026-10-06) found two `FULFILLS_GOAL` edges, `task.three-moments-values` and
`task.track-one-pattern` → `goal.self-reflection-beginner` (both tasks draft, no edge
properties); the same two tasks' `fulfills_goal_uid` columns, each naming its edge's goal; one
TaskTemplate (`tt.mindfulness-101.log-first-five`) holding `fulfills_goal_template_uid`; two
tracker rows keyed `FULFILLS_GOAL|outgoing|goal.self-reflection-beginner`; no Edge-file row, no
`CONTRIBUTES_TO_GOAL` edge, and no TASK_BASED goal (the three goals are percentage-measured). Its
migration (`scripts/migrations/task_contributes_to_goal_2026_10.py`) re-types the edges, removes the
task columns, renames the template property and rewrites the tracker keys; `./dev
reconcile-goal-tallies` then recomputes the stored tallies.

### The vaults

- **Content vault:** six files author a retiring type through frontmatter. `FULFILLS_GOAL`
  (`connections.fulfills_goal`): two task files. `GUIDED_BY_PRINCIPLE`: one goal file
  (`connections.aligned_with_principle`) and one PathStep file (`principle_uids`). `GUIDES_GOAL`
  (`connections.guides_goal`): two principle files. No Edge file uses a retiring type.
- **Personal vault:** no file authors a retiring type. Two userguides show
  `@context(goal) @link(principle:…)`, which writes `GUIDED_BY_PRINCIPLE` through the DSL.
- **PR 3 (2026-10-05):** neither vault authors the choice's retired field or either retired
  principle ↔ choice type, so PR 3 edits no vault file.
- **PR 4 (2026-10-06):** the content vault authors the retiring field in three files: two task
  files' `connections.fulfills_goal` (`Task/task_three-moments-values.md`,
  `Task/task_track-one-pattern.md`, one target each), which become
  `connections.contributes_to_goal`, and one task template's `fulfills_goal_template_uid`
  (`Tmpl/log-first-five_tmpl.md`), which becomes `contributes_to_goal_template_uid`. No Edge file
  names either type; the personal vault authors neither.

### Readers that share an edge type

A definition whose far end is `Entity` lists every source of its edge type, and the curriculum
already writes several of these types:

- `SUPPORTS_GOAL` has three kinds of source: habits, principles (from PR 2) and PathSteps
  (`goal_uids`). Every goal view of it names its kind: `supporting_habits` and the essential /
  critical / optional views name `Habit`, `supporting_principles` names `Principle`. A PathStep's
  edge is on no goal view; the PathStep reads it as `practice_goals`.
- `INFORMS_CHOICE` has three kinds of source: principles (from PR 3), habits and PathSteps
  (`choice_uids`). Every choice view of it names its kind: `informing_principles` names
  `Principle`, `informing_habits` names `Habit`. A PathStep's edge is on no choice view; the
  PathStep reads it as `informed_choices`. The principle's and the habit's `informed_choices` name
  `Choice`.
- The principle's `embodying_habits` (`EMBODIES_PRINCIPLE`) also lists learning paths
  (`connections.embodied_principles`).
- The event's `scheduled_by_choices` (`SCHEDULES_EVENT`) lists PathSteps (`event_uids`), the only
  writer of that type; the live graph holds one.
- `CONTRIBUTES_TO_GOAL` has two kinds of source, tasks and events, and from PR 4 the goal's tally
  counts both. Each goal view of it names its kind: `contributing_tasks` names `Task`,
  `contributing_events` names `Event`. The task's `contributing_goals` and the event's
  `supported_goals` name `Goal`.

**A keyed reader reads the definition whole (PR 1c):** the three keyed readers on
`UnifiedRelationshipService` (`get_related_uids`, `has_relationship`, `batch_get_related_uids`)
resolve the key through `resolve_keyed_read` and carry the definition's `target_label` (unless it
is `Entity`) and its edge-property filter to the backend, which labels the far node and filters the
edge in the statement. A view that splits by source label, or by tier, therefore reads only its
kind and tier once its definition names them. The five keyed readers with no caller and no PLANNED
ruling (`count_related`, `get_ordered_related_uids`, `get_related_with_metadata`,
`batch_has_relationship`, `batch_count_related`) were deleted, with the backend methods behind four
of them. A shared-neighbour definition is refused by a keyed read.

**A keyed delete reads the definition whole too (PR 2):** `delete_relationship(key, …)` passes the
far end's label to the backend when the definition names one, so a key removes only its own kind's
edge. The goal's `supporting_habits` cannot delete a principle's `SUPPORTS_GOAL` edge into the same
goal, and `supporting_principles` cannot delete a habit's.

**The cross-domain context places a node by both ends of its incident edge (PR 2):** a related node
lands in a mapping's bucket only if the edge touching it has the mapping's type and orientation and
its other end is of the centre's kind. A goal reached habit → principle → goal (`EMBODIES_PRINCIPLE`,
then the principle's `SUPPORTS_GOAL`) is not one of the habit's `supported_goals`, and a goal reached
principle → habit → goal is not one of the principle's. A shared-neighbour view (`related_goals`,
`related_principles_shared`) is exempt: its node is a peer reached through the shared neighbour.

### The importance level

`SUPPORTS_GOAL` carries `essentiality` (`HabitEssentiality`: essential, critical, supporting,
optional) beside `weight`. The habit's create doors and, from PR 2, every principle door store
`weight: 1.0` and `essentiality: "supporting"`; vault edges carry no property. The registry's three
tiered views (essential, critical, optional) are habit-only and therefore empty today;
`supporting_habits` lists every habit. A principle's edge stores the level and has no tier view.

### Retiring a type: what it touches

- 145 tracked files name one of the six types (`git grep -w`; tests 43, docs and skills 54).
  Every docs mention outside records is swept by the PR that retires the type.
- Hand-written Cypher names the types directly, so no registry edit reaches it: the user-context
  statements (`user_context_queries.py`: `PRACTICED_AT_EVENT`; `FULFILLS_GOAL` until PR 4 re-pointed
  the task and goal rows to `CONTRIBUTES_TO_GOAL` and deleted the habit's arm; `GUIDES_GOAL` until
  PR 2 deleted that projection; both principle ↔ choice halves read `INFORMS_CHOICE` from PR 3, under
  their old projection names `guided_choices` and `guiding_principles`), the goal tally
  (`goal_tally_queries.py`, `activity_backends.py`, `cross_domain_backend.py`), and
  `activity_backends.py`'s achievement context (its choice-influence stats read `INFORMS_CHOICE`
  from PR 3).
- Ingestion writes edges from the registry (`yaml_field_path`), so a type's edges leave ingestion
  with its registry definition. The task's goal field is the exception:
  `preparer._reconcile_task_goal_link` stamps `fulfills_goal_uid` from `connections.fulfills_goal`
  and turns a bare `fulfills_goal_uid` into that field, and `vault_policy`'s `_TASK_GOAL_FIELD` /
  `_TASK_GOAL_COLUMN` realign the column when a goal target is refused. Both name the field and the
  column, not the type, so `git grep -w FULFILLS_GOAL` misses them; PR 4 deleted both with the
  column (O3), and a task file's `connections.contributes_to_goal` writes its edges from the
  registry like any other field. The
  two fields whose names disagreed with the edge they wrote have retired: the goal's
  `connections.aligned_with_principle` (`GUIDED_BY_PRINCIPLE`) in PR 2, and the choice's
  `connections.guided_by_principle` in PR 3, replaced by `connections.informing_principles`, which
  writes `INFORMS_CHOICE` into the choice.
- **Migrate before the enum member goes.** A content-vault Edge file naming a deleted type becomes a
  validation error, and an `authored_edges` tracker key naming one cannot be decoded: it is skipped
  with a warning (the warning is PR 2's), so the edge it recorded would never be retracted. Convert
  or delete the stored edges, and rewrite the tracker keys, in the same PR.
- `GRAPH_CONTRACT.yaml` is generated (`uv run python scripts/generate_graph_contract.py`) and
  drift-tested.

### Defects found by the census

Each is fixed by the PR named, or registered there if it falls outside the arc:

- The page lists' five nonexistent edge names; the task page's `INFORMED_BY_PRINCIPLE`; the habit
  page's `APPLIES_KNOWLEDGE` (habits write `REINFORCES_KNOWLEDGE`); the choice page's
  `APPLIES_KNOWLEDGE` (choices write `INFORMED_BY_KNOWLEDGE` and `REQUIRES_KNOWLEDGE_FOR_DECISION`)
  and `ENABLES_HABIT` (a habit-prerequisite edge no choice writes); the goal page's incoming
  `APPLIES_KNOWLEDGE` (no definition or writer points that edge at a goal), its `#` links and its
  double-listed task — **PR 1b** (fixed: the pages read the registry; the task's goal fallback,
  which rendered a raw goal uid as its title, went with them).
- `cross_domain_backend.py`'s alignment-evidence query tests `(goal)-[:EMBODIES_PRINCIPLE]->`, a
  shape nothing writes — **PR 2** (fixed: the goal arm reads `(principle)-[:SUPPORTS_GOAL]->(goal)`
  alone).
- `cross_domain_backend.py`'s choice-adherence query reads `(choice)-[:ALIGNED_WITH_PRINCIPLE]->`,
  but choices write `INFORMED_BY_PRINCIPLE` — **PR 3** (fixed: it reads
  `(principle)-[:INFORMS_CHOICE]->(choice)`).
- `generate_graph_enrichment` turned the choice's shared-neighbour `related_choices` definition into
  a one-hop match on its placeholder type, so the patterns it computed put principles under
  `related_choices` — **PR 3** (fixed: it leaves out every shared-neighbour definition;
  `related_choices` is now the choices that affect the same goal, through `AFFECTS_GOAL`). PR 3's
  census found the leak latent: no Activity search service reads those patterns (see the next
  registered item), so no search result ever carried it.
- `PrinciplesBackend.get_choice_influence_stats` (`GET /api/principles/choice-effectiveness`) and
  both principle ↔ choice halves of the user-context statement read one of the link's two
  names each — **PR 3** (fixed: each reads the one edge; the choice half keeps its `Principle` far
  label).
- `PrinciplesSearchService.get_for_habit` reads `(habit)-[:ALIGNED_WITH_PRINCIPLE]->`, but habits
  write `EMBODIES_PRINCIPLE` (its facade has no caller outside tests) — **PR 5**.
- A task update stores `aligned_principle_uids` as a node property instead of edges — **PR 5**.
- The user-context statement reads a habit's `FULFILLS_GOAL`, which nothing writes — **PR 4**
  (fixed: the habit arm reads `SUPPORTS_GOAL` alone; the task row carries every goal a task
  contributes to, one row per task, where a task with two goals had been two rows).
- `Task.fulfills_goal_uid` and its edge diverge at the vault door and the PathStep spawn (O3) —
  **PR 4** (fixed: the column is gone; every door writes `CONTRIBUTES_TO_GOAL` edges, the PathStep
  spawn included, and the readers that held the column — the goal Gantt's `get_tasks_for_goal`
  and the relevance scorer — read the edge).
- A goal's `supporting_habits` and tier views name `Entity`, so they also return the PathSteps whose
  `practice_goals` write `SUPPORTS_GOAL`; a published one passes the far-node wall, and
  `_predictive_mixin.py` then fetches its title with a bare `habits_service.get` — **PR 2** (fixed:
  the four views name `Habit`).
- The cross-domain context bucketed a node by its incident edge alone, so a goal two hops from a
  habit through a principle's `SUPPORTS_GOAL` counted as a goal the habit supports — **PR 2** (fixed:
  § Readers that share an edge type).
- `GET /api/principles/goal` (`PrinciplesSearchService.get_for_goal`) and the goal-achieved handler
  read one of the link's two names each — **PR 2** (fixed: both read the one edge, principles only).
- The task and event "replace" paths (`TasksService._delete_edges_of_kind`,
  `EventsService._replace_edge`) find the edges to delete through `get_related_uids`, which the
  far-node wall scopes: an `APPLIES_KNOWLEDGE` edge to a Ku since reverted to draft is withheld, so
  it is not deleted when the set is replaced, and comes back beside the new set on republish —
  outside the arc; registered here by PR 1c's census (the delete needs an untied read,
  `include_withheld`, which the keyed reader does not expose).
- `PRINCIPLE_REFLECTION_CONFIG` declares the method key `"trigger"` four times, and
  `get_relationship_by_method` returns the first, so a keyed read of it would see only goals. No
  service is built from that config — outside the arc, latent.
- Search enrichment (`_search_raw_mixin.py`'s graph-enrichment matches, built from each registry
  definition's type, far label and direction) composes no far-node wall, so a search result's
  `_graph_context` lists the node at the far end of an edge whoever owns it and whether or not it
  is published, and it carries no edge-property filter, so a goal's `essential_habits` / `critical_habits` / `optional_habits`
  enrichment lists every supporting habit — outside the arc; registered by PR 2's census. Latent:
  PR 3's census found the enrichment never runs for an Activity domain (below).
- `DomainConfig.graph_enrichment_patterns` is computed from the registry
  (`generate_graph_enrichment`) for every Activity and curriculum config, and nothing reads it: the
  faceted search reads the service's own `_graph_enrichment_patterns`, which no Activity search
  service sets, so an Activity search result carries no `_graph_context` from the registry. Wire it
  or delete it — outside the arc; registered by PR 3's census (the six "configured via
  `_graph_enrichment_patterns`" comments that claimed otherwise were corrected).
- `GoalUpdateRequest` accepts `required_knowledge_uids`, `supporting_habit_uids` and
  `supporting_principle_uids`, and `to_intent()` carries none of them: an update that sends one
  answers 200 and changes no edge — outside the arc; registered by PR 2's census.
- `EventsSearchService.get_for_goal` reads `(Event)-[:SUPPORTS_GOAL]->(Goal)`, an edge no event
  door writes (an event's goal edges are `CONTRIBUTES_TO_GOAL` and `CELEBRATES_GOAL`), so it
  returns nothing — registered by PR 2's census; fixed by **PR 4** (deleted: it had no route and
  no caller, and the goal's `contributing_events` view reads the event's link).
- `get_principle_conflict_analysis` reads the bucket `"goals"` from each principle's cross-domain
  context. The buckets are keyed by the registry's context names (`supported_goals`), so the key is
  never present and no conflict is ever detected — outside the arc; registered by PR 2's census.
- `@context(principle) @link(goal:…)` is parsed and discarded: the DSL's principle converter builds
  a `PrincipleCreateRequest`, which has no link field — outside the arc; registered by PR 2's census.
- Two vault files can author one edge: a principle file's `connections.supports_goal` and a goal
  file's `connections.supporting_principles` (as a habit file's `connections.supports_goal` and a
  goal file's `connections.supporting_habits` already could). Each file's tracker row fingerprints
  the edge under its own key, so dropping the line from one file retracts the edge while the other
  file still declares it; the unchanged file is skipped on the next sync and does not write it
  back until it is edited or forced — outside the arc; registered by PR 2's census.
- An unregistered `connections.*` frontmatter key is not refused: the preparer flattens every
  `connections` entry and only a registered field is turned into edges and kept off the node, so a
  retired or misspelt key writes no edge and gives no warning — outside the arc; registered by PR
  2's census.
- `GoalsProgressService._get_relationships_from_rich_context` reads a goal's rich-context keys
  `supporting_habits`, `aligned_paths` and `guiding_principles`, none of which the user context's
  goals statement emits, so the relationships it builds hold no habit, path or principle and the
  graph read behind it is never reached; its two callers
  (`calculate_goal_progress_with_context`, `update_goal_from_habit_progress`) have no caller of
  their own. `PrinciplesPlanningService` reads `aligned_principles` from the same goal context,
  equally absent — outside the arc; registered by PR 2's census.
- `principle_integration_score` can exceed 1.0: `user_context_populator.py` divides the choices any
  principle informs (read through the principles statement, unwindowed) by the choices in the
  user-context window, and life-path alignment weights the score 30%. PR 3 raises the numerator for
  everyone, since a link made at the choice's door now counts — outside the arc; registered by
  PR 3's census.
- `UserContext.decisions_aligned_with_principles` and `decisions_against_principles` have no
  writer: the principles stats card always reads 0 / 0, and life-path intelligence reads them too —
  outside the arc; registered by PR 3's census.
- `ContextualChoice.aligned_principles` is never passed when the daily plan builds its choices
  (`choices_service.py`), so the core-principle relevance boost never fires in the plan's choice
  step — outside the arc; registered by PR 3's census.
- `ContextualPrinciple.guided_choices` is never written — outside the arc; registered by PR 3's
  census.
- `GET /api/choices/aligned-with-principle` (`find_choices_aligned_with_principle`) reads a
  semantic-relationship filter, not the principle ↔ choice link, so a choice a principle informs is
  not returned unless a semantic edge also says so — outside the arc; registered by PR 3's census.
- The principle's dual-track assessment and adherence trends describe choice reads they do not
  make — outside the arc; registered by PR 3's census.
- `cross_domain_backend.py`'s `_CHOICE_CONFLICT_COUNT_QUERY` counts
  `(choice)-[:CONFLICTS_WITH_PRINCIPLE]->(principle)`, an edge no choice writes, so the conflict
  count is always 0 — outside the arc; registered by PR 3's census.
- `@context(choice) @link(principle:…)` is parsed and dropped, and choice create has no principle
  field (no `informing_principle_uids`), so the choice side has two fewer doors than the goal side
  (founder, 2026-10-05: left unwired) — outside the arc; registered by PR 3's census.
- The goal's shared-neighbour `related_goals` walks `FULFILLS_GOAL` and `SUPPORTS_GOAL` out of the
  goal, but both edges point into it, so the view finds nothing — **PR 4** (fixed: the definition is
  deleted; the task's shared-neighbour `related_tasks` walks `CONTRIBUTES_TO_GOAL`).
- The event's behavioural signals (`/self-checkin`'s engagement score) read the event's goal links
  under the bucket `"goals"`, but the bucket is named by the registry's context name
  (`supported_goals`), so the score's goal share never moved — found by PR 4's census; fixed by
  **PR 4** (it reads `supported_goals`).
- The goal-cancel guard counted open tasks over `FULFILLS_GOAL` only, and its open set left out
  DRAFT and POSTPONED — **PR 4** (fixed: it counts the open tasks that contribute to the goal, open
  being anything but COMPLETED, CANCELLED and FAILED; a contributing event does not block).
- The guard sits on one door only: `GoalsService.cancel_goal`, reached through
  `POST /api/goals/{uid}/status`. `GoalUpdateRequest` carries `status`, so `POST /api/goals/update`
  and the goal edit form (`POST /goals/edit`) reach `GoalsCoreService.update_goal` with CANCELLED
  and skip it — outside the arc; registered by PR 4's census.
- The vault deletion sweep (`VaultReconciler`, `core/services/vault/vault_reconciler.py`) classifies
  each retired task as open from the status its listing read, then writes CANCELLED through
  `update_task`, whose guard refuses no prior; a task completed between the read and the write is
  cancelled from COMPLETED — outside the arc; registered by PR 4's census.
- Changing a goal's `measurement_type` recomputes nothing: a goal turned TASK_BASED keeps its stored
  figure until its next contribution change or `./dev reconcile-goal-tallies` — outside the arc;
  registered by PR 4's census.
- `GoalProgressUpdated` documents `old_progress` / `new_progress` as 0.0–1.0, but the recomputes
  publish percentages (0–100), and `GoalEventHandlerService.handle_goal_progress_updated` reads them
  on the 0–1 scale: its stall check's `< 0.01` delta and `:.0%` formatting are a hundredfold off —
  outside the arc; registered by PR 4's census.
- The cross-domain context still lists a node two hops away when the hop between is of the
  centre's own kind: a goal supported by a principle that a second principle supports
  (`SUPPORTS_PRINCIPLE`) is among the second principle's `supported_goals`, at distance 2. That is
  the transitive context `depth` asks for, and each item carries its distance — stated here, not a
  defect.

## PR ledger

Rows run in order. PR 1 needs PR 0. PR 1b needs PR 1. PR 1c needs PR 1b. PRs 2–5 each need PR 1c, and each
shrinks PR 1's known-gaps list. PRs 2 and 3 are independent of each other. PR 4 rewrites the goal
tally, so it runs after PR 2 to keep the goal page's changes apart. PR 5 runs last.

| PR | Scope | Acceptance | Status |
|----|-------|------------|--------|
| 0 | This document, ADR-090, the INDEX rows and the skill back-link; the cells of ADR-057's diagonals table and of the Sibling Signal and Shared Signal patterns that named edges nothing carries (docs only; summon Codex explicitly) | Merged; `./dev docs-links`, the dead-link scan and the skills validator clean | merged #1498, 2026-10-04 |
| 1 | The invariant as a test, derived from the registry: every edge type joining two different Activity domains is read at BOTH ends (same-type edges are the later pass, R8), and a view over an edge type with several kinds of source filters by source label in the read. Lands with a known-gaps list | Passes with the list; removing any entry turns it red; a one-sided definition added turns it red | merged #1500, 2026-10-04 |
| 1b | The pages show both ends (R10): the page renders the registry's labelled definitions in both directions and `connection_configs.py` is deleted; the page-list defects (§ Defects found by the census) | Every link in § What each layer shows today that the registry reads at both ends shows on both detail pages and both list cards; the five nonexistent names are gone | merged #1501, 2026-10-04 |
| 1c | The keyed readers carry `target_label` and the tier filter: the eight `READERS_IGNORING_TARGET_LABEL` entries (re-owned from 1b, which keeps the pages on the walled batched reader), the readers and the backend methods behind them | `READERS_IGNORING_TARGET_LABEL` is empty; real-graph tests: a label-split view returns only its kind and a tier view only its tier, through each reader; red on the old source | merged #1503, 2026-10-04 |
| 2 | Principle → goal: `SUPPORTS_GOAL` with the importance level; label-split goal views; retire `GUIDES_GOAL`, and `GUIDED_BY_PRINCIPLE` between Activities (its enum member stays with the PathStep's use while O2 is deferred) | A link made at any door shows on both pages; the live pairs migrated (four edges become two) and shown from both ends; the gaps list shrinks | merged #1504, 2026-10-05; the stored-edge migration and the vault edits (R9) ran 2026-10-05 (four edges became two) |
| 3 | Principle → choice: `INFORMS_CHOICE`; label-split choice views; retire `GUIDES_CHOICE` / `INFORMED_BY_PRINCIPLE` | As PR 2, for choices | merged #1505, 2026-10-05; the stored-edge migration ran 2026-10-05 on the founder's go (nothing to re-type) |
| 4 | "Contributes": tasks serve several goals through `CONTRIBUTES_TO_GOAL`; retire `FULFILLS_GOAL` and settle `Task.fulfills_goal_uid` (O3); the task form's goal picker; the goal's progress counts contributing tasks AND events, cancelled ones left out (R11; the rest of O1 first) | A task linked to two goals counts toward both; a completed contributing event moves the goal's progress; cancelling a completed event, or a goal's last contribution, updates the stored tally (to 0/0 for the last); every membership change recomputes (closes the goal-tally case file); the gaps list shrinks | merged #1507, 2026-10-06; the stored-edge migration and the vault edits (R9) ran 2026-10-06 on the founder's go (two edges re-typed, two columns and one template field moved, two tracker rows rewritten) |
| 5 | The remaining views: the goal sees choices (affects) and events (celebrates, contributes) apart; event ↔ principle is one link (retire `PRACTICED_AT_EVENT` and the event's `practiced_habits`); the habit names `REINFORCES_HABIT` from events "events where this habit is practiced"; the views still sharing an edge type split by source label (the habit's `REINFORCES_HABIT` views, the principle's `embodying_habits`, the event's `scheduled_by_choices`); a task update writes `ALIGNED_WITH_PRINCIPLE` edges instead of a node property | PR 1's known-gaps list is empty | — |
| close | ADR-090 marked implemented; this document to `done/` (docs only) | Every retired type reads 0 in the live graph and in live code (`GUIDED_BY_PRINCIPLE`: between Activities; wholly only if O2, deferred, moves the PathStep's use) | — |

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

R10 settles the route: a registry definition that the page shows carries the domain's name for the
link. The detail page and the list card render the domain's definitions in both directions, grouped by link rather than by the far end's type, so that celebrating and contributing
events are listed apart. `core/utils/connection_configs.py` and its consumers' wiring are deleted. PR 1's
invariant then covers the pages. The page-list defects go with it.

**Acceptance:** every link that the registry reads at both ends shows on both detail pages and on
both list cards, under each domain's name for it; a real-graph route test per pair for the detail
route and the list route, red on the old source.

**Settled in prose before the first edit (founder, 2026-10-04):**
- The name lives on the definition, `page_heading`; a definition with one is shown, one without is
  not. Two definitions share a heading only when they are one link stored under two names (goal ↔
  principle and choice ↔ principle until PRs 2–3, the task's fulfills / contributes until PR 4, the
  event's demonstrates / practiced until PR 5); the page lists each far end once. The headings use
  the ruled verbs (R2 "support", R4 "inform", R7 "practiced").
- Shown: every cross-Activity view at both ends, and the knowledge and learning-path views each
  domain declares. Not shown: laterals (the Relationships section draws them), same-type links (R8;
  the task has its own Sub-tasks and Dependencies sections) and `SERVES_LIFE_PATH`.
- The tier views (`essential_habits` / `critical_habits` / `optional_habits`) get no heading. A mixed
  view lists whatever its edge holds, each item with its kind's icon, until its PR splits it; the
  habit's mixed `reinforcing_habits` gets none, since its task and event views cover both sources.
- One card for all six domains, one line per heading. The Today page and the card re-render after a
  status or priority change read through the same walled reader.
- PR 1's eight keyed-reader entries move to a row of their own (1c).
- The habit page's separate "Choices" section (`/habits/choices-fragment`, footnote 5 of § What
  each layer shows today), which repeated `INFORMS_CHOICE` and `IMPACTS_HABIT` beside the
  Connections section through an unwalled keyed reader, is deleted (founder, 2026-10-04).
- The invariant gains two rules: every end that reads a link between two Activities shows it, and no
  edge is listed twice on a page.

### PR 1c — The keyed readers carry the label and the tier

PR 1's test lists eight keyed readers on `UnifiedRelationshipService` that do not carry a
definition's `target_label` to the backend (`READERS_IGNORING_TARGET_LABEL`), and five of them drop
the tier filter too (§ Readers that share an edge type). PR 1b kept the pages on
`ConnectionFetchBackend`'s walled batched statement, which places each row by its far end's label
itself, so the pages never reach those readers; the entries moved here from 1b (founder, 2026-10-04).
The label-split views of PRs 2, 3 and 5 are read through these readers, so this row runs first.
Census each reader's callers and its backend method before the first edit; none of the keyed
readers carries the far-node wall (`build_far_node_clause`), which is not this row's scope but is
worth stating in its kickoff.

**Acceptance:** `READERS_IGNORING_TARGET_LABEL` is empty; per reader, a real-graph test shows a
label-split view returning only its kind and a tier view only its tier; red on the old source.

**Settled in prose before the first edit (founder, 2026-10-04):**
- The census found two keyed readers with production callers (`get_related_uids`,
  `batch_get_related_uids`) and one PLANNED (`has_relationship`, ruled 2026-06-13). Those three are
  fixed; the five with no caller and no ruling are deleted, with the backend methods only they
  reached. `READERS_IGNORING_TARGET_LABEL` is deleted with them, and the invariant checks label and
  tier with no gap list.
- The label is a backend parameter (`target_label: NeoLabel | None = None`, so the direct backend
  callers are unchanged); the service passes it unless the definition names `Entity`, which names
  no kind and would drop the non-Entity far nodes. The batch reader gains the tier filter.
- `batch_get_related_uids` was walled only on paper: the service passed `config.entity_label`
  (`Entity` for every Activity config), so the far-node wall never applied on the service path.
  The backend now anchors on its own label and keys the wall on it, as `get_related_uids` does
  (ADR-085 G12 corrected).
- A keyed read of a shared-neighbour definition is refused (its one-hop read returns the shared
  neighbours); `related_events` leaves the event's fetch specs with its readerless field.
- The goal planner's read of `"habits"` (no such key on `GOALS_CONFIG`) and the blockers it fed,
  computed and never returned, are deleted.

### PR 2 — Principle → goal

`SUPPORTS_GOAL` from principles, with the importance level (`essentiality`) habits carry; the doors
store the same default habits' doors do. The goal's views split by source label: supporting habits,
supporting principles.

The doors stay and write the one edge: `/api/principles/link`'s goal type, goal `link-principle`,
goal create (its list field is `supporting_principle_uids`) and the DSL's goal → principle link.
What retires is the edge type, not the way to make the link.

Retire `GUIDES_GOAL` whole: its enum member, registry definitions, `GRAPH_CONTRACT.yaml` rows,
frontmatter field (`connections.guides_goal`), stored edges (migrated), vault files (R9) and the
docs that name it. Retire the goal's use of `GUIDED_BY_PRINCIPLE`: the goal's definition, its
frontmatter field (`connections.aligned_with_principle`), the goal → principle edges (migrated) and
the goal file's field in the vault. O2 is deferred, so the type itself stays — its enum member, the
PathStep's definition and its contract rows — with that one source.

Add `GUIDES_GOAL` to `scripts/health/stale_names.py` (not `GUIDED_BY_PRINCIPLE`, which stays live for
the PathStep). The scanner has no directory exclusion and reads only backtick spans and fences, so
every mention left in a record needs its own line-anchored `ALLOWED_OCCURRENCES` entry: ADR-090, this
document, `docs/INDEX.md`'s ADR-090 row and the older ADRs that keep the name (today ADR-015). Run it
with `--verbose` after adding the name and take the anchors from its output.

**Acceptance:** real-graph tests — a link made at either door is returned by both entities' views,
under one key each; unlinking at either door removes it for both; the migration leaves the live
pairs as one edge each, shown from both ends; red on the old source.

**Settled in prose before the first edit (founder, 2026-10-05):**
- **Views.** The goal page lists "Habits that support this goal" (habits only) and "Principles that
  support this goal" (one list); the principle page lists "Goals this principle supports". The goal's
  key and context name are `supporting_principles`, the principle's `supported_goals`. A PathStep
  supporter leaves the goal page, and no PathStep list is added in this arc. The three tier views
  become habit-only; a principle's edge stores `essentiality` and gets no tier view.
- **The doors stay, repointed.** `POST /api/principles/link` (goal type),
  `POST /api/goals/link-principle`, goal create and `@context(goal) @link(principle:…)` all write
  `(Principle)-[:SUPPORTS_GOAL {weight: 1.0, essentiality: "supporting"}]->(Goal)`. The goal door's
  `alignment_strength` goes: nothing read it. `@context(principle) @link(goal:…)` stays discarded
  and is registered (§ Defects found by the census). Frontmatter: a principle file authors
  `connections.supports_goal`, a goal file `connections.supporting_principles`;
  `connections.guides_goal` and `connections.aligned_with_principle` retire. A vault edge carries no
  property, as a habit's does. The personal-vault userguides need no edit.
- **Unlinking.** No HTTP unlink door is added. "Unlinking at either door" is proven at the service
  (`GoalsService.unlink_goal_from_principle`) and at the vault door (a dropped frontmatter line).
  The goal's "unlink habit" checks the far end's kind, so it cannot remove a principle's link.
- **Vault files.** Converted in place: the two principle files take `supports_goal`, the goal file
  takes `supporting_principles`. Two files now author one edge; the hazard that one file dropping the
  line deletes an edge the other still declares is registered, not fixed.
- **The transitive miscount is fixed in the cross-domain categoriser:** a node is bucketed only if
  the other end of its incident edge is of the kind the mapping implies. Its real-graph test: a habit
  embodies a principle, the principle supports a goal, the habit has no goal link.
- **Migration.** One Python script (`scripts/migrations/principle_supports_goal_2026_10.py`): a
  census by default, writes under `--confirm` on the founder's go. Per pair holding either old edge
  it MERGEs the principle → goal `SUPPORTS_GOAL`, fills the default importance only where the edge
  has none (an existing `SUPPORTS_GOAL` keeps its values), deletes both old edges and drops
  `alignment_strength`. `GUIDED_BY_PRINCIPLE` is matched only where the source is a Goal. The
  tracker rows (`IngestionMetadata.authored_edges`, keys `TYPE|direction|uid`) are rewritten with
  the edges, and an undecodable tracker key logs a warning. Order: merge, stop the app, edit the
  three vault files, census, `--confirm`, `./dev vault-sync --vault content`, verify.
- **Defects.** Fixed: the alignment-evidence query, `GET /api/principles/goal`, the goal-achieved
  principle readers and the stale docstrings. Deleted: the caller-less
  `build_principle_with_context` and the user context's `guided_goals` projection, which nothing
  read. Registered: the residuals in § Defects found by the census marked "registered by PR 2's
  census".
- **Acceptance.** Real-graph tests, red on the old source: each door returns the link
  from both views under one key each; a goal with a habit, a principle and a PathStep supporter
  shows each where it belongs and no habit reader counts the principle; the transitive case; the
  migration's states (either old edge alone, both, `SUPPORTS_GOAL` already present, a re-run, a
  PathStep's edge untouched, the tracker rows).

### PR 3 — Principle → choice

As PR 2, with `INFORMS_CHOICE` and the choice's views, retiring `GUIDES_CHOICE` and
`INFORMED_BY_PRINCIPLE`. The choice-alignment metric, `ChoiceCrossContext` and the
choice-adherence query read the one edge.

**Acceptance:** as PR 2.

**Settled in prose before the first edit (founder, 2026-10-05):**
- **Views.** The choice page lists "Principles that inform this choice" (one list; key and context
  name `informing_principles`, far end `Principle`) and "Habits that inform this choice"
  (`informing_habits`, far end `Habit`, habits only). The principle page lists "Choices this
  principle informs" (`informed_choices`, far end `Choice`). The habit page is unchanged; its
  `informed_choices` names `Choice`. A PathStep's `choice_uids` edge leaves the choice page. The
  user-context and report names stay: `guided_choices`, `guiding_principles`,
  `principle_guided_choice_counts`.
- **The doors stay, repointed.** `POST /api/principles/link` (`link_type=choice`) and
  `POST /api/choices/link-principle` write `(Principle)-[:INFORMS_CHOICE]->(Choice)` with no
  properties; `alignment_score` goes, from the request and from the service. Frontmatter: a choice
  file authors `connections.informing_principles` (replacing `connections.guided_by_principle`), a
  principle file `connections.informs_choice` (new). Choice create and the DSL's
  `@context(choice) @link(principle:…)` stay unwired; both are registered (§ Defects found by the
  census).
- **Unlinking.** No HTTP door is added. `ChoicesService.unlink_choice_from_principle` is added and
  registered PLANNED, like the goal's; the keyed delete carries the `Principle` kind, so it leaves a
  habit's informing link alone. The vault door retracts a dropped frontmatter line.
- **Vault files.** None authors a retiring field or type; no edits.
- **Transitive.** A choice reached habit → principle → choice (`EMBODIES_PRINCIPLE`, then the
  principle's `INFORMS_CHOICE`) is not one of the habit's informed choices, and one reached
  principle → habit → choice is not one of the principle's. PR 2's categoriser gate already blocks
  both; real-graph tests prove it.
- **`related_choices`.** Kept, as "choices that affect the same goal": its placeholder type is
  `AFFECTS_GOAL` (whose real definition precedes it), walked through `AFFECTS_GOAL` only, far end
  `Choice`. `generate_graph_enrichment` leaves out every shared-neighbour definition, which ends the
  leak of the shared neighbour into the choice's, habit's and goal's search enrichment patterns
  (a latent leak: nothing reads those patterns, § Defects found by the census).
- **Migration.** One script (`scripts/migrations/principle_informs_choice_2026_10.py`): a census by
  default, writes under `--confirm` on the founder's go, run before any sync on the new code. Both
  types retire whole: an edge of either type that is not principle ↔ choice stops the run (exit 2),
  and so does an Edge-file tracker row naming either type (its Edge YAML is rewritten by hand, then one sync). Tracker
  keys are rewritten by four mappings, of which only the choice file's outgoing key to a principle
  becomes `INFORMS_CHOICE|incoming|…` in practice. `alignment_score` is dropped.
- **Defects.** Fixed: the choice-adherence query, the choice-effectiveness stats, both
  user-context halves (the choice half keeps its `Principle` pin), the alignment metric's hand
  union, the `ChoiceCrossContext` union and the stale docstrings. Deleted: the caller-less
  `build_choice_with_context` and its re-exports; dropped: the choice-side arm of
  `_TraversalMixin.get_batch_cross_domain_context` and the retired type's string in
  `build_impact_chain_query`. Registered: the residuals in § Defects found by the census marked
  "registered by PR 3's census".
- **Acceptance.** Real-graph tests, red on the old source: each of the four doors read from both
  ends under one key each; a choice with a habit, a principle and a PathStep informer through every
  reader; the transitive cases; unlink by kind; the migration's states, Edge-file rows included; the
  far-end door test gains the choice door; a placement unit test.

### PR 4 — "Contributes"

Tasks link to any number of goals through `CONTRIBUTES_TO_GOAL`. `FULFILLS_GOAL` retires, with
`Task.fulfills_goal_uid` reshaped (O3), the task form's goal picker, the vault field, the DSL's
task → goal link, the goal task generator and the readers in § Retiring a type. The goal's tally
counts contributing tasks and events, cancelled ones left out (R11), with the rest of O1 settled in
the kickoff. The recompute's status trigger is the tally's own classes, not a list of transitions:
any status write that moves a task or an event between done, not done and out (COMPLETED; the open
statuses; CANCELLED; FAILED in whichever class the kickoff settles) recomputes the goals it
contributes to. The door set is not a list: every status write goes through
`update_with_status_guard` (ADR-087), so the PR censuses that primitive's task and event callers —
the API, the vault, and raw writers such as the missed-habit-event writer, which cancels an event
directly — or puts the trigger where they converge. Events need this most: they publish no reopen event, so an
event leaving COMPLETED, or a completed event's cancellation, publishes only `CalendarEventUpdated`
today. When the last contribution leaves the count the recompute still writes:
today `_plan_task_progress` writes nothing for a 0/0 tally, which would leave the stored progress
describing the removed contribution. This PR changes how goal progress is triggered, which is the
trigger of [Goal Tally Membership Changes Don't Recompute](done/goal-tally-membership-changes.md), so it
closes that case file too: linking or unlinking a task or event, creating or deleting one with a goal
link, and changing a task's `completion_updates_goal` all recompute the goals they touch, for both
kinds of contribution. The case file moves to `done/` with this PR. Two readers need more than the type's deletion: the goal-cancel guard counts open tasks
over `FULFILLS_GOAL` only (`cross_domain_backend.py`) and must count open contributions (the kickoff
decides whether an open contributing event blocks a cancel), and `GOALS_CONFIG`'s shared-neighbour
`related_goals` definition names `FULFILLS_GOAL` as its placeholder type and as an intermediate edge.
Both name the enum member, so
missing either breaks the import. The readers that fail silently name the type as a raw string: the
user-context statements and `cross_domain_backend.py`'s `_INTENT_EDGE_SETS["goal_achievement"]`.
The field's column-only readers (the goal Gantt, the relevance scorer) go with O3. Update the [goal-tally case file](done/goal-tally-membership-changes.md), whose check names
`FULFILLS_GOAL`.

**Acceptance:** a task linked to two goals counts toward both; a completed contributing event
moves the goal's progress; every status write that changes a contribution's class moves the stored
tally, for tasks and events, through each caller of `update_with_status_guard` the census finds
(a completed event set back to scheduled, a completed event cancelled, an open task cancelled, a
habit event marked missed), and cancelling a goal's last contribution leaves
it 0/0; every door that changes a goal's membership moves the
stored tally with no status transition (linking a scheduled event to a 1/1 goal makes it 1/2). The
doors come from the PR's own census of writers, not a hand list: every writer of a task's or an
event's goal link (create, update, link door, vault field, DSL, generator, scheduler), every unlink
and delete door for tasks and events, and a `completion_updates_goal` change — one real-graph test
per door; the tally's statement and the user-context statements read
the one edge; red on the old source.

**Settled in prose before the first edit (founder, 2026-10-06):**
- **Views.** The task page lists "Goals this task contributes to" (several; key
  `contributes_to_goal`, far end `Goal`). The goal page lists "Tasks that contribute to this goal"
  (key and context name `contributing_tasks`, which `GoalCrossContext.tasks` reads) and, apart,
  "Events that contribute to this goal" (`contributing_events`, far end `Event`), which takes PR 5's
  Event → Goal `MISSING_ENDS` entry. A cancelled contribution is still listed, its status shown,
  and not counted. The event page is unchanged.
- **O3: `Task.fulfills_goal_uid` is dropped**, on the Task only — `Goal.fulfills_goal_uid` is the
  parent goal and stays. `get_tasks_for_goal` (`/api/tasks/goal`, the goal Gantt) reads the edge;
  the relevance scorer reads the task → goal edge map as events do. Task create takes
  `contributes_to_goal_uids` (a list).
- **Form.** The create form keeps its goal picker (one goal, one contribution); the edit form loses
  it. The task update API takes `contributes_to_goal_uids` as a full replace (`[]` clears it, absent
  leaves it). No event update field.
- **The doors stay and write `(Task)-[:CONTRIBUTES_TO_GOAL]->(Goal)` with no properties:** task
  create, task update, `POST /api/tasks/link-goal`, vault `connections.contributes_to_goal`
  (`connections.fulfills_goal` retires), the DSL's task `@link(goal:…)` (every goal the line names),
  the goal task generator, and the PathStep template spawn (the template field is renamed
  `contributes_to_goal_template_uid` and the spawn writes the edge). The link doors'
  `contribution_percentage` / `milestone_uid` (task) and `contribution_weight` (event) go. The
  DSL's event `@link(goal:…)` is wired.
- **Counting.** Only TASK_BASED goals have a tally (MIXED stays in its case file). Done is
  COMPLETED, out is CANCELLED, and everything else, FAILED included, is not done — the same for
  events. Habit-scheduled events count. When the last contribution leaves, the recompute writes
  0 / 0 and 0%, and a goal at 100% is un-achieved (back to ACTIVE). A recompute never achieves or
  un-achieves a CANCELLED, ARCHIVED or FAILED goal. The cancel guard: an open contributing TASK
  blocks a cancel (open = not COMPLETED, CANCELLED or FAILED); events do not block.
- **One trigger:** a new event, `GoalContributionsChanged` (goal uids and contributor uids), with
  goal progress its one subscriber, replacing the goal progress subscriptions to `TaskCompleted`
  and `TaskReopened`. It is published on a status class move (`update_task`, `update_event`, the
  vault's status classifier); on create with goals, the link doors, the task update's list,
  unlink, delete (the goal uids captured before; the HTTP delete included), a vault field added or
  retracted, a vault file deleted, and a `completion_updates_goal` change. `./dev
  reconcile-goal-tallies` recomputes every TASK_BASED goal under its lock — the backstop, and the
  migration's tally step.
- **Unlink:** through the task update's list; `unlink_task_from_goal` / `unlink_event_from_goal`
  service methods, keyed by kind, registered PLANNED.
- **`related_goals`** is deleted. `related_tasks`' intermediate edge becomes `CONTRIBUTES_TO_GOAL`.
- **Vault and migration:** the two task files take `connections.contributes_to_goal`, the template
  takes `contributes_to_goal_template_uid`. The script is PR 3's state machine plus: remove
  `fulfills_goal_uid` from `:Task` nodes only, turn a column with no edge into an edge, rename the
  template property, then reconcile the tallies. Order: edit the files, census, `--confirm`,
  preview the sync (shown to the founder), sync. The live run waits on the founder's go.
- **Defects.** Fixed: the user context's habit `FULFILLS_GOAL` arm (deleted) and its task row (one
  row per task, with every goal); `/self-checkin`'s `"goals"` bucket (now `supported_goals`);
  `EventsSearchService.get_for_goal` and the dead helpers that named `FULFILLS_GOAL` (deleted).
  `miss_habit_event` is registered PLANNED with its trigger and a service test. Registered: the
  goal-cancel guard bypass (the update request and the edit form) and the vault deletion sweep's
  prior-read race (§ Defects found by the census).
- **Acceptance:** this section, the door list from the census, one real-graph test per door, red on
  the old source; `miss_habit_event` proven at the service.

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
  stored edges, vault files, docs. A door that made the link stays when the link does, and writes
  the replacing edge (PR 2). `git grep -w <TYPE>` then finds it only in records (ADRs,
  `done/`, this document, ADR-090's row in `docs/INDEX.md`), in `scripts/health/stale_names.py` (its
  table entry and allowances), and in the stored-edge migration and its test.
- Vault edits (R9) are made in the same session, re-synced, and the live edges checked after.
- The ledger row is the PR's last commit.
