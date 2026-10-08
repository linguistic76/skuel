---
title: "Activity Links Follow-ons — Link Doors, Unwritten Links, Same-Type Pairs"
updated: 2026-10-08
status: "deferred"
registered: "2026-10-04 (Activity Links arc, ruling R8)"
ruled: "2026-10-04 — R8: storage and visibility were the arc; page controls are the arc after; same-type pairs a later pass; which arc creates the unwritten links was not put to the founder"
trigger: "the founder schedules the next links arc (the page controls first — four service-level unlink methods wait on it in the PLANNED tier)"
check: "`./dev bloat` lists the four unlink methods under their link-doors entries; `tests/unit/test_activity_link_invariant.py` still excludes same-type edges (R8); the dependency readers named under § 3 still disagree"
---

# Activity Links Follow-ons — Link Doors, Unwritten Links, Same-Type Pairs

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

What the [Activity Links arc](done/activity-links-arc.md) (closed 2026-10-08) left outside itself
by ruling. R8 (arc doc § Founder rulings): "Scope: storage and visibility only. 'Link from this
page' controls are the NEXT arc. Same-type pairs are a later pass." Three items, each a section;
each is settled in prose with the founder before its first edit. The arc's contract they build on
is [ADR-090](../decisions/ADR-090-one-link-per-fact-a-view-per-domain.md): a link between two
Activities is one stored fact, shown on both pages, each in its own words.

## 1. "Link from this page" — the link and unlink page controls (the arc after)

Every link between two Activities now shows on both detail pages (R10: the page renders the
registry's headed views in both directions), but a link is still made only through the API link
doors, the create forms' pickers, the DSL and the vault, and unlinked only at the service or by a
dropped frontmatter line. No detail page has a control to add or remove a link.

What exists for it:

- **Link doors (HTTP):** `POST /api/principles/link` (`link_type` goal / choice / habit),
  `POST /api/goals/link-principle`, `POST /api/choices/link-principle`, `POST /api/habits/link-principle`,
  `POST /api/tasks/link-goal`, `POST /api/events/link-goal`, `POST /api/choices/link-goal`; the
  create forms' pickers (task → one goal; event → "Milestone for goal", habits; goal →
  supporting habits / principles).
- **Unlink at the service only, registered PLANNED** (`scripts/detect_bloat.py`, `blocked_by`
  this file's MOC entry): `GoalsService.unlink_goal_from_principle`,
  `ChoicesService.unlink_choice_from_principle`, `TasksService.unlink_task_from_goal`,
  `EventsService.unlink_event_from_goal` (via `_orchestration_mixin`). Each carries the far
  end's kind, so it removes only its own kind's edge (arc doc § Readers that share an edge type —
  "A keyed delete reads the definition whole"). The task update's `contributes_to_goal_uids` and
  `aligned_principle_uids` are full replaces (`[]` clears) — a replace, not an unlink door.
- **Older staged link surfaces** in the same PLANNED tier: `GoalsService.unlink_goal_from_habit`
  and `create_semantic_goal_relationship` (the goals "gravity" entry), `ChoicesService.link_choice_to_habit`.
- **A rule the controls inherit:** a page shows its links from the registry (R10), so a control
  belongs beside the headed view it edits, and writes the one edge whichever page it sits on (R1).

## 2. The links nothing writes

Five link types have a registry definition at both ends, show on both pages, and have no writer —
no door, no form field, no DSL sink, no vault field (a content-vault Edge file can author any
type, which is the only way one exists today):

| Edge | Pages | Registry views |
|------|-------|----------------|
| `IMPLEMENTS_CHOICE` (Task → Choice) | task, choice | the task's `implements_choices`, the choice's view |
| `INFORMS_CHOICE` from a Habit (Habit → Choice) | habit, choice | the habit's `informed_choices`, the choice's `informing_habits` (principles write the type; habits do not) |
| `TRIGGERS_CHOICE` (Event → Choice) | event, choice | both |
| `SCHEDULES_EVENT` from a Choice (Choice → Event) | choice, event | the event's `scheduled_by_choices` names `Choice`; PathSteps write the type through `event_uids` |
| `DEMONSTRATES_PRINCIPLE` (Event → Principle) | event, principle | the one event ↔ principle link since PR 5 (the principle-side type retired with it); "events where this principle is practiced" |

Creating them is neither storage nor visibility, so R8 put it outside the arc; **which later arc
takes it was not put to the founder.** The natural home is § 1 (a control that makes a link is a
writer), but that is a reading, not a ruling. Two related doors the arc registered as residuals
belong with this decision: choice create has no principle field and the DSL drops
`@context(choice) @link(principle:…)`, and the DSL drops `@context(principle) @link(goal:…)` and
the task converter's `@link(principle:…)` ([registered residuals](activity-links-registered-residuals.md) § 1).

## 3. Same-type pairs — a later pass

Links between two entities of the same kind were outside the arc and are outside its invariant
test (`tests/unit/test_activity_link_invariant.py` keys on edges joining two *different* Activity
domains). The pairs:

- **Task dependencies:** `DEPENDS_ON`, `ENABLES_TASK`, `BLOCKS` / `BLOCKED_BY`. Only
  `BLOCKS` / `BLOCKED_BY` is a lateral type (with `auto_inverse`); the rest are domain edges.
- **Principle ↔ principle:** `SUPPORTS_PRINCIPLE`, `CONFLICTS_WITH_PRINCIPLE`.
- **Habit prerequisites:** `REQUIRES_PREREQUISITE_HABIT`, `ENABLES_HABIT`.

Habit and principle facts are split today between a lateral edge and a domain edge. The census the
arc already holds, to start from (arc doc § Target, § Defects found by the census):

- Task create writes a prerequisite as `BLOCKED_BY` with no `BLOCKS` partner
  (`core/services/tasks/tasks_core_service.py`).
- The dependency readers disagree: the planner and the user context read `DEPENDS_ON`, readiness
  reads `BLOCKED_BY`, the blocking chain reads `BLOCKS`.
- `TaskRelationships.prerequisite_task_uids` (`core/services/tasks/task_relationships.py`) reads the
  key `prerequisite_tasks`, whose definition is `DEPENDS_ON`, while the create field of the same
  name writes `BLOCKED_BY` — so a prerequisite set at create never reaches that reader
  ([registered residuals](activity-links-registered-residuals.md) § 6, item 24).
- The task registry's `subtasks` view names `HAS_CHILD`, but every task writer writes
  `HAS_SUBTASK`, which the task page's Sub-tasks section reads through the hierarchy backend.
- Several same-type edges are read at one end only; no arc PR removed them.

The pass applies ADR-090's rule to a pair of the same kind: one stored fact per link, both pages
show it, two edges only where the two directions say different things (R3). The task page's
Sub-tasks and Dependencies sections, and the Relationships section that draws laterals, are the
surfaces it reconciles (arc doc § PR 1b: "Not shown: laterals … same-type links (R8)").
