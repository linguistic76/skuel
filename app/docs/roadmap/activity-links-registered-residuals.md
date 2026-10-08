---
title: "Activity Links Arc — Registered Residuals"
updated: 2026-10-08
status: "registered"
registered: "2026-10-04 to 2026-10-08 (the censuses of Activity Links arc PRs 1c–5)"
trigger: "the next touch of the subsystem an item names (each item carries its file and line), or the quarterly review walk"
check: "re-read each item at its cited line; an item whose code no longer matches its description moves to done/ or is struck"
---

# Activity Links Arc — Registered Residuals

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

The defects the [Activity Links arc](done/activity-links-arc.md) found outside its own scope and
registered rather than fixed (arc doc § Defects found by the census, the bullets ending "outside
the arc; registered by PR N's census"). Every one was re-verified live on `main` `322d133fd` at
the arc's close (2026-10-08): all 27 still hold. Each item keeps the census's number; the file and
line are where the defect is, not where the fix goes. Items whose nearest home is another live
case file say so.

Two kinds recur. **A reader of a key nothing writes** (items 6, 10, 12, 13, 14, 16, 26, 27): a
bucket, context field or projection name that no statement emits, so the reader is dead and its
feature silently returns nothing — the shape the arc fixed for the goal page, `/self-checkin` and
`EventCrossContext`. **A door that drops what it was given** (items 5, 7, 18, 25): a request field
or DSL link parsed and discarded, answering 200 and writing no edge.

## 1. Link doors and the DSL

5. `GoalUpdateRequest` accepts `required_knowledge_uids`, `supporting_habit_uids` and
   `supporting_principle_uids`, and `to_intent()` carries none of them: an update that sends one
   answers 200 and changes no edge — `core/models/goal/goal_request.py:182` (`to_intent()`
   at 222–252). Registered by PR 2.
7. `@context(principle) @link(goal:…)` is parsed and discarded: the DSL's principle converter
   builds a `PrincipleCreateRequest`, which has no link field —
   `core/services/dsl/activity_domain_converters.py:351`. Registered by PR 2.
18. `@context(choice) @link(principle:…)` is parsed and dropped, and choice create has no
   principle field (no `informing_principle_uids`), so the choice side has two fewer doors than
   the goal side — `core/services/dsl/activity_domain_converters.py:413`. Founder, 2026-10-05:
   left unwired. Registered by PR 3. Which arc wires it is the question in
   [follow-ons § 2](activity-links-follow-ons.md).
25. The DSL's task converter (`activity_to_task_request`) drops `@link(principle:…)`, while the
   habit and goal converters keep theirs — `core/services/dsl/activity_domain_converters.py:137`.
   Registered by PR 5.
15. `GET /api/choices/aligned-with-principle` (`ChoicesService.find_choices_aligned_with_principle`)
   reads a semantic-relationship filter, not the principle ↔ choice link, so a choice a principle
   informs is not returned unless a semantic edge also says so —
   `core/services/choices_service.py:563`. Registered by PR 3.

## 2. Readers of keys nothing projects or writes

6. `get_principle_conflict_analysis` reads the bucket `"goals"` from each principle's cross-domain
   context; the buckets are keyed by the registry's context names (`supported_goals`), so the key
   is never present and no conflict is ever detected —
   `core/services/principles/_influence_mixin.py:112-113`. Registered by PR 2.
10. `GoalsProgressService._get_relationships_from_rich_context` reads a goal's rich-context keys
   `supporting_habits`, `aligned_paths` and `guiding_principles`, none of which the user context's
   goals statement emits (it projects `contributing_tasks`, `sub_goals`, `required_knowledge`),
   so the relationships it builds hold no habit, path or principle; its two callers
   (`calculate_goal_progress_with_context`, `update_goal_from_habit_progress`) are reached only
   through facade delegators nothing calls — `core/services/goals/goals_progress_service.py:456`,
   `adapters/persistence/neo4j/user_context_queries.py:351-355`. `PrinciplesPlanningService` reads
   `aligned_principles` from the same goal context, equally absent —
   `core/services/principles/principles_planning_service.py:136`. Registered by PR 2.
12. `UserContext.decisions_aligned_with_principles` and `decisions_against_principles` have no
   writer: the principles stats card always reads 0 / 0, and life-path intelligence reads them
   too — `core/services/user/unified_user_context.py:372`;
   reader `core/services/user/intelligence/life_path_intelligence.py:239`. Registered by PR 3.
13. `ContextualChoice.aligned_principles` is never passed when the daily plan builds its choices,
   so the core-principle relevance boost never fires in the plan's choice step —
   `core/services/choices_service.py:313`. Registered by PR 3.
14. `ContextualPrinciple.guided_choices` is never written — `core/models/context_types.py:995`.
   Registered by PR 3.
16. The principle's dual-track assessment describes "recent choices" it does not read (the code
   reads `supported_goals` and `inspired_habits`), and the adherence trends read the nonexistent
   buckets `choices` and `habits` — `core/services/principles/_alignment_intelligence_mixin.py:204`
   and ~385. Registered by PR 3.
26. `PrinciplesPlanningService._extract_principles_for_activities` reads a task's and an event's
   `graph_context["guiding_principles"]`, a key neither user-context statement projects, so
   `get_contextual_principles_for_user` and `get_principle_practice_opportunities_for_user` never
   see a task or an event linked to a principle, though the task's `ALIGNED_WITH_PRINCIPLE` is
   writable on create and update. Reading it there is a new read — a new registry statement under
   the MEGA-QUERY rule — `adapters/persistence/neo4j/user_context_queries.py:297-302` (task) and
   499–504 (event); `core/services/principles/principles_planning_service.py:112,124`. Registered
   by PR 5. (`docs/domains/principles.md` records the same under the planning service.)
27. `assess_principle_alignment` hard-codes no recent tasks and a task count of 0 ("Principles
   don't directly relate to tasks") and ignores the `aligned_tasks` bucket `PRINCIPLES_CONFIG`
   emits — `core/services/principles/_alignment_intelligence_mixin.py:98`. Registered by PR 5.
2. `PRINCIPLE_REFLECTION_CONFIG` declares the method key `"trigger"` four times, and
   `get_relationship_by_method` returns the first, so a keyed read of it would see only goals. No
   service is built from that config — latent — `core/models/relationship_registry.py:1565,1572,1579,1586`
   (lookup at 415). Registered by PR 1c.
11. `principle_integration_score` can exceed 1.0: `user_context_populator.py` divides the choices
   any principle informs (read through the principles statement, unwindowed) by the choices in the
   user-context window, and life-path alignment weights the score 30%. PR 3 raised the numerator
   for everyone, since a link made at the choice's door now counts —
   `core/services/user/user_context_populator.py:820`. Registered by PR 3.

## 3. Readers of edges nothing writes

17. `cross_domain_backend.py`'s `_CHOICE_CONFLICT_COUNT_QUERY` counts
   `(choice)-[:CONFLICTS_WITH_PRINCIPLE]->(principle)`, an edge no choice writes (the registry
   defines the type principle → principle only), so the conflict count is always 0 —
   `adapters/persistence/neo4j/cross_domain_backend.py:368`. Registered by PR 3.

## 4. Goal progress and cancel

19. The goal-cancel guard sits on one door only: `GoalsService.cancel_goal`, reached through
   `POST /api/goals/{uid}/status`. `GoalUpdateRequest` carries `status`, so
   `POST /api/goals/update` and the goal edit form (`POST /goals/edit`) reach
   `GoalsCoreService.update_goal` with CANCELLED and skip it (`update_goal` runs only
   `status_transition_guard`) — `core/services/goals/goals_core_service.py:864`. Registered by PR 4.
21. Changing a goal's `measurement_type` recomputes nothing: a goal turned TASK_BASED keeps its
   stored figure until its next contribution change or `./dev reconcile-goal-tallies` (the update
   publishes only `GoalUpdated`) — `core/services/goals/goals_core_service.py:886`. Registered by
   PR 4.
22. `GoalProgressUpdated` documents `old_progress` / `new_progress` as 0.0–1.0, but the recomputes
   publish percentages (0–100), and `GoalEventHandlerService.handle_goal_progress_updated` reads
   them on the 0–1 scale: its stall check's `< 0.01` delta and `:.0%` formatting are a hundredfold
   off — `core/services/goals/goal_event_handler_service.py:299`; publishers
   `core/services/goals/goals_progress_service.py:1098,1466`; `core/events/goal_events.py:138`.
   Registered by PR 4.
20. The vault deletion sweep (`VaultReconciler`) classifies each retired task as open from the
   status its listing read, then writes CANCELLED through `update_task`, whose guard refuses no
   prior (a prior of COMPLETED is accepted); a task completed between the read and the write is
   cancelled from COMPLETED — `core/services/vault/vault_reconciler.py:1200`;
   the guard it reaches, `core/services/completion_stamp.py:428` (`status_transition_guard`), has no
   terminal-prior refusal. Registered by PR 4.

## 5. Ingestion

8. Two vault files can author one edge: a principle file's `connections.supports_goal` and a goal
   file's `connections.supporting_principles` (as a habit file's `connections.supports_goal` and a
   goal file's `connections.supporting_habits` already could). Each file's tracker row fingerprints
   the edge under its own key, so dropping the line from one file retracts the edge while the other
   file still declares it; the unchanged file is skipped on the next sync and does not write it
   back until it is edited or forced — the retract has no check for another declaring file —
   `adapters/persistence/neo4j/ingestion_write_backend.py:328` (caller
   `core/services/ingestion/batch.py:1562`). Registered by PR 2.
9. An unregistered `connections.*` frontmatter key is not refused: the preparer flattens every
   `connections` entry and only a registered field is turned into edges and kept off the node, so
   a retired or misspelt key writes no edge and gives no warning —
   `core/services/ingestion/preparer.py:380`. Registered by PR 2.

## 6. Task update fields and the dependency edges

23. `TaskUpdateIntent.prerequisite_knowledge_uids` and `prerequisite_task_uids` are stored as node
   properties on update (the update's edge split resets only habit, knowledge, goal and principle;
   the mapper's skip set does not list them), while task create writes them as
   `REQUIRES_KNOWLEDGE` and `BLOCKED_BY` edges — the shape PR 5 fixed for `aligned_principle_uids`
   — `core/services/tasks_service.py:481-486`; `adapters/persistence/neo4j/neo4j_mapper.py:50`.
   Registered by PR 5.
24. `TaskRelationships.prerequisite_task_uids` reads the key `prerequisite_tasks`, which is
   `DEPENDS_ON`, while the create field of the same name writes `BLOCKED_BY`, so a prerequisite
   set at create never reaches that reader — `core/services/tasks/task_relationships.py:25`;
   registry `:588`; `core/services/tasks/tasks_core_service.py:592`. Registered by PR 5. Its home is
   the same-type pass, [follow-ons § 3](activity-links-follow-ons.md).
1. The task and event "replace" paths (`TasksService._delete_edges_of_kind`,
   `EventsService._replace_edge`) find the edges to delete through `get_related_uids`, which the
   far-node wall scopes: an `APPLIES_KNOWLEDGE` edge to a Ku since reverted to draft is withheld,
   so it is not deleted when the set is replaced, and comes back beside the new set on republish.
   The delete needs an untied read (`include_withheld`), which the keyed reader does not expose —
   `core/services/tasks_service.py:506`; `core/services/events_service.py:406`. Registered by PR 1c.

## 7. Search enrichment

3. Search enrichment (`_search_raw_mixin.py`'s graph-enrichment matches, built from each registry
   definition's type, far label and direction) composes no far-node wall, so a search result's
   `_graph_context` would list the node at the far end of an edge whoever owns it and whether or
   not it is published, and it carries no edge-property filter, so a goal's `essential_habits` /
   `critical_habits` / `optional_habits` enrichment would list every supporting habit — latent, see
   item 4 — `adapters/persistence/neo4j/_search_raw_mixin.py:497`. Registered by PR 2.
4. `DomainConfig.graph_enrichment_patterns` is computed from the registry
   (`generate_graph_enrichment`) for every Activity and curriculum config, and nothing reads it:
   the faceted search reads the service's own `_graph_enrichment_patterns`, which defaults to `()`
   and which no Activity search service sets, so an Activity search result carries no
   `_graph_context` from the registry. **Wire it or delete it** —
   `core/services/mixins/search_operations_mixin.py:623`; `core/services/base_service.py:603`;
   `core/services/domain_config.py:156,254`. Registered by PR 3. (`docs/architecture/SEARCH_ARCHITECTURE.md`
   and `docs/reference/SEARCH_SERVICE_METHODS.md` record the same beside their pattern tables.)
