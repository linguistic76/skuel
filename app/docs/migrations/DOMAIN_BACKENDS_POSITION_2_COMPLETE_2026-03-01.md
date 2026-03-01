---
title: Domain Backends Position 2 — Complete
updated: 2026-03-01
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

**Activity Domains (6):**
- `TasksBackend`, `EventsBackend`, `GoalsBackend`, `HabitsBackend`, `ChoicesBackend`, `PrinciplesBackend`

**Curriculum Domains (4):**
- `KuBackend` — ORGANIZES graph
- `LsBackend` — excluded (only `execute_exists()` analytics calls, no raw persistence)
- `LpBackend` — mastery progress queries
- `ExerciseBackend` — curriculum link methods

**Content/Submissions (1):**
- `SubmissionsBackend` — SHARES_WITH access control

**Supporting (uses UniversalNeo4jBackend[T] directly):**
- `HabitCompletion`, `Transcription`, `PrincipleReflection`, `UserProgress`, `Askesis`, `ActivityReport`, `ExpensePure`, `InvoicePure`

## Commits

| Commit | Phase |
|--------|-------|
| `c726434` | Phase 1: KuBackend |
| `0acb7c1` | Phase 2: SubmissionsBackend |
| `5a31b5e` | Phases 3+4: LpBackend + ExerciseBackend + docstring |
