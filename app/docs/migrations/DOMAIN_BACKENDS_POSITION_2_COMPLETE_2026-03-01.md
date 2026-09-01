---
title: Domain Backends Position 2 — Complete
updated: 2026-04-11
category: migrations
related_docs:
- /docs/patterns/BACKEND_OPERATIONS_ISP.md
- /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
---

# Domain Backends Position 2 — Complete

*Date: March 1, 2026*

## Summary

Extended the domain backend pattern from Activity Domains (6) to all remaining domains
with relationship-specific Cypher. Four new backend classes added to
`adapters/persistence/neo4j/domain_backends.py`.

**Result:** 4-layer consistency across all domains:
```
*Operations protocol → *Backend subclass → *Service facade → sub-services
```

## Motivation

Activity Domain backends (`HabitsBackend`, `GoalsBackend`, etc.) were created in
February 2026 to fix `__getattr__` bridge failures. They accidentally landed on a
correct architectural insight: **domain-specific persistence operations belong at
the persistence layer, not scattered through service methods.**

Three domains still had raw Cypher in services:
- `ku_organization_service.py` — direct `execute_query()` calls for ORGANIZES graph ops
- `submissions_sharing_service.py` — bypassed the backend entirely, wired to `QueryExecutor`
- `lp_progress_service.py` — raw executor calls for mastery progress queries
- `exercise_service.py` — inline Cypher for curriculum relationship management

## What Moved

### Phase 1: KuBackend

7 ORGANIZES relationship methods moved from `ku_organization_service.py`:

| Method | Purpose |
|--------|---------|
| `organize(parent_uid, child_uid, order)` | Create ORGANIZES relationship |
| `unorganize(parent_uid, child_uid)` | Delete ORGANIZES relationship |
| `reorder(parent_uid, child_uid, new_order)` | Update order property |
| `get_organized_children(parent_uid)` | List children with order |
| `find_organizers(ku_uid)` | List parent organizers |
| `list_root_organizers(limit)` | All top-level organizers |
| `is_organizer(ku_uid)` | Boolean check for MOC identity |

`ku_organization_service.py` methods are now thin delegations.

### Phase 2: SubmissionsBackend

8 SHARES_WITH relationship methods moved from `submissions_sharing_service.py`.
The sharing service previously bypassed the backend entirely, wiring directly to
`executor: QueryExecutor`. Now uses `backend: SubmissionOperations`.

| Method | Purpose |
|--------|---------|
| `share_submission(entity_uid, recipient_uid, role)` | Create SHARES_WITH |
| `unshare_submission(entity_uid, recipient_uid)` | Delete SHARES_WITH |
| `get_shared_with_users(entity_uid)` | List recipients |
| `get_submissions_shared_with_me(user_uid, limit)` | Inbox query |
| `set_visibility(entity_uid, owner_uid, visibility)` | Update visibility property |
| `check_access(entity_uid, user_uid)` | Owner OR shared access check |
| `verify_shareable(entity_uid)` | Must be COMPLETED to share |
| `verify_ownership(entity_uid, owner_uid)` | Inherited from base |

### Phase 3: LpBackend

2 mastery progress queries moved from `lp_progress_service.py`:

| Method | Purpose |
|--------|---------|
| `get_paths_containing_ku(ku_uid)` | Find all LPs that include a KU |
| `get_ku_mastery_progress(lp_uid, user_uid)` | KU completion state for LP |

`lp_progress_service.py` switched from `executor: QueryExecutor | None` to
`backend: LpBackend | None`.

### Phase 5: LpBackend CRUD expansion (April 2026)

11 raw `execute_query` calls moved from `lp_core_service.py` to typed LpBackend methods. Fixes a Cypher injection risk in `list_all_paths` (f-string `ORDER BY` interpolation without `_ALLOWED_ORDER_BY` validation).

| Method | Purpose |
|--------|---------|
| `get_path_with_steps(uid)` | Single LP + HAS_STEP steps |
| `get_paths_batch_with_steps(uids)` | Batch LP fetch (GraphQL DataLoader) |
| `get_path_with_graph_context(uid)` | LP + 7 graph neighborhoods |
| `list_user_paths_with_steps(user_uid, limit)` | User's LPs with steps |
| `list_all_paths_with_steps(limit, offset, order_by, order_desc)` | All LPs with `_ALLOWED_ORDER_BY` |
| `update_path_properties(set_clauses, params)` | Dynamic SET update |
| `delete_path_cascade(uid)` | Cascade delete LP + step nodes |
| `persist_path_with_steps(user_uid, path_params, steps_params)` | Create LP + steps atomically |
| `entity_exists(uid)` | Simple existence check |

Dead code removed: `_build_prerequisite_query()` in `lp_core_service.py` (duplicate of the copy in `lp_intelligence_service.py`).

### Phase 6: LpBackend Intelligence expansion (April 2026)

7 raw `execute_query` calls moved from `lp_intelligence_service.py` to typed LpBackend methods. Fixes 6 broken `graph_intel.execute_query()` calls (`GraphIntelligenceService` has no `execute_query` method — would raise `AttributeError` at runtime). Also removes `executor` parameter from `LpIntelligenceService` and `LpService`.

**Follow-up fix (April 2026):** 4 of the 7 service-layer consumers were calling `.get()` on `result.value` (a `list[dict]`) instead of extracting records first. `execute_query` returns `Result[list[dict]]` — a list of Neo4j records, not a single dict. The correct pattern:
```python
# Single-record queries (identify_path_blockers, get_optimal_path_recommendations, get_path_with_context):
records = result.value or []
record = records[0] if records else None
analysis = record["blocker_analysis"]

# Multi-record queries (validate_path_prerequisites):
records = result.value or []
validations = [r["validation"] for r in records]
```

| Method | Purpose |
|--------|---------|
| `validate_path_prerequisites(path_uid)` | Prerequisite ordering validation |
| `identify_path_blockers(path_uid, user_uid)` | Find blockers for a user |
| `get_optimal_path_recommendations(user_uid, goal_domain)` | Best path recommendations |
| `find_learning_sequence(start_uid, goal_uid)` | Shortest path graph traversal |
| `get_next_adaptive_step(current_step_uid, user_uid)` | Adaptive next step |
| `get_recommended_path_steps(user_uid, max_difficulty, limit)` | Recommended steps by progress |
| `get_path_with_context(path_uid, user_uid, depth)` | Path + full graph context |

Helper `_build_prerequisite_subquery()` (static method) builds Cypher prerequisite fragments using `SemanticRelationshipType`.

### Phase 4: ExerciseBackend

3 curriculum linking methods moved from `exercise_service.py`:

| Method | Purpose |
|--------|---------|
| `link_to_curriculum(exercise_uid, curriculum_uid)` | Create REQUIRES relationship |
| `unlink_from_curriculum(exercise_uid, curriculum_uid)` | Delete REQUIRES relationship |
| `get_required_knowledge(exercise_uid)` | List required KUs |

## What Did NOT Move

Cross-domain aggregation stays in services — not raw persistence:

| Service | Why it stays |
|---------|-------------|
| `progress_feedback_generator.py` | Reads Tasks/Goals/Habits for cross-domain aggregation |
| `activity_review_service.py` | Cross-domain snapshot queries |
| `feedback_service.py` `_persist_feedback_entity()` | Atomic entity+relationship transaction |

## Files Modified

| File | Change |
|------|--------|
| `adapters/persistence/neo4j/domain_backends.py` | +4 backend classes (KuBackend, SubmissionsBackend, LpBackend, ExerciseBackend) |
| `adapters/persistence/neo4j/universal_backend.py` | Updated BACKENDS IN USE docstring registry |
| `core/ports/submission_protocols.py` | Added 7 sharing method signatures to `SubmissionOperations` |
| `core/services/ku/ku_organization_service.py` | 7 methods → thin backend delegations |
| `core/services/submissions/submissions_sharing_service.py` | `executor: QueryExecutor` → `backend: SubmissionOperations` |
| `core/services/lp/lp_progress_service.py` | `executor` → `backend: LpBackend` |
| `core/services/exercises/exercise_service.py` | 3 methods → thin backend delegations |
| `services_bootstrap.py` | 4 backend class upgrades + sharing service wiring |

## Complete Backend Registry (Post-Migration)

**Activity Domains (6) — all extend `_HierarchyMixin` (March 24, 2026):**
- `TasksBackend` — hierarchy + `get_stats_for_user` + `auto_complete_parent_if_ready` + `calculate_parent_progress`
- `GoalsBackend` — hierarchy + `get_stats_for_user`
- `HabitsBackend` — hierarchy + `get_stats_for_user` + badge/achievement ops (4 methods)
- `EventsBackend` — hierarchy + `get_stats_for_user`
- `PrinciplesBackend` — hierarchy + `get_stats_for_user`
- `ChoicesBackend` — hierarchy + `get_stats_for_user` + behavioral signals (5 methods: principle adherence, conflicts, life path contribution, satisfaction correlation, conflict count)

**Curriculum Domains (5):**
- `KuBackend` — ORGANIZES graph + usage summary + namespace/alias search + relationship queries (13 methods: +7 for related/broader/narrower/learning-path/task/event/habit UIDs)
- `LessonBackend` — 59 methods across 5 mixins: `_OrganizesMixin` (12), `_LearningStateMixin` (13), `_SemanticMixin` (11), `_KnowledgeContextMixin` (13), `_AdaptiveMixin` (10)
- `PsBackend` — CONTAINS_KNOWLEDGE CRUD (4 methods) + lesson progress tracking
- `LpBackend` — HAS_STEP management (5 methods) + mastery progress queries (2 methods) + CRUD (9 methods, April 2026) + intelligence queries (7 methods + 1 helper, April 2026)
- `ExerciseBackend` — curriculum links + OWNS/FOR_GROUP + student exercise queries (6 methods)

**Submissions/Reports (1):**
- `SubmissionsBackend` — SHARES_WITH access control + exercise submission processing + temporal/thematic relationships + assessment ops + report relationship queries (20 methods: +6 for pending submissions, unsubmitted exercises, report summary, learning loop chain, submission chain, supported goals)

**Exercises (1):**
- `RevisedExerciseBackend` — teacher authority verification + auto-share + student listing (4 methods)

**Forms (2):**
- `FormTemplateBackend` — submission count for deletion guard
- `FormSubmissionBackend` — admin user lookup for auto-sharing

**Groups/Notifications (2, new March 24, 2026):**
- `GroupBackend` — OWNS/MEMBER_OF CRUD (6 methods)
- `NotificationBackend` — HAS_NOTIFICATION CRUD (5 methods)

**Supporting (uses UniversalNeo4jBackend[T] directly):**
- `SharingBackend`, `HabitCompletion`, `Transcription`, `PrincipleReflection`, `UserProgress`, `Askesis`, `ActivityReport`, `ExpensePure`, `InvoicePure`

## Commits

| Commit | Phase |
|--------|-------|
| `c726434` | Phase 1: KuBackend |
| `0acb7c1` | Phase 2: SubmissionsBackend |
| `5a31b5e` | Phases 3+4: LpBackend + ExerciseBackend + docstring |
| `ad0a5dcb` | Phase 0-1: _HierarchyMixin + Tasks hierarchy |
| `a9470fa2` | Phases 2-4: Remaining hierarchy + curriculum CRUD |
| `35ad08e9` | Phase 5: Remaining 12 services + GroupBackend + NotificationBackend |
| `e7be457b` | Phases 1-3: Inline Cypher migration (Goals, FormSubmission, Ku, PS) |
| `17d0b1c5` | Phase 4: ActivityReport, TeacherReview, ExerciseBackend, GroupBackend |
| `a1c264af` | Phase 5: LateralRelationshipBackend (14 methods) |
| `84b2b9db` | Phase 6: Fail-fast sweep — eliminate optional-dep fallback patterns |
| `a918c7d2` | Phase 7: Lesson domain (8 services, 31 LessonBackend methods) |
| `053bbaa9` | Phase 8: Harden 3 methods + migrate 17 queries from Choices/Report/KU/Submissions |
