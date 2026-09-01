---
updated: 2026-04-14
---

# ADR-053: Groups First-Class + Unified Sharing

> **2026-04-14 — Extended by [ADR-054](ADR-054-user-entry-unified-submissions.md).** This ADR unified the teacher → student direction of sharing on `SHARED_WITH_GROUP`. ADR-054 makes the student → teacher direction symmetric by collapsing `Submission`/`ExerciseSubmission`/`JeInput`/`JeOutput` into a single `UserEntry` type that is shared via `UnifiedSharingService` at submit time.

**Status:** Accepted
**Date:** 2026-04-14
**Supersedes:** The `FOR_GROUP` portion of [ADR-040](ADR-040-teacher-exercise-workflow.md).
**Related:** [ADR-038 Content Sharing Model](ADR-038-content-sharing-model.md), [ADR-040 Teacher Exercise Workflow](ADR-040-teacher-exercise-workflow.md)

## Context

`Group` was complete at the model / service / backend layer but invisible and
under-wired in the broader system:

1. **Two competing sharing mechanisms.** `Exercise` connected to groups via
   a bare `FOR_GROUP` edge (no metadata, no lifecycle, entity-type hardcoded
   in Cypher). `UnifiedSharingService` already had a fully-featured
   `SHARED_WITH_GROUP` edge with `shared_at` and `share_version` properties,
   access verification, and an entity-agnostic backend. But `PathStep` and
   `LearningPath` had **neither** — there was no teacher→group curriculum
   path for them at all.
2. **`Group` was absent from `UserContext`.** ~250 fields, zero about the
   groups a user belongs to or owns. Intelligence services could not reason
   about class membership.
3. **No ingestion path for Group.** Teachers could not create groups via
   YAML. `ENTITY_CONFIGS` had no entry for Group.
4. **Dead UI code.** A stub `/groups` page reachable only from a broken
   empty-state link.

## Decision

Raise `Group` to a first-class, observable, ingestion-creatable domain, and
unify Exercise / PathStep / LearningPath → Group connections under a single
mechanism.

### 1. Retire `FOR_GROUP`. Unify on `SHARED_WITH_GROUP`.

`SHARED_WITH_GROUP` becomes **the** teacher→group curriculum mechanism for
all entity types. It is entity-agnostic in the backend, carries `shared_at`
and `share_version` metadata, and goes through `UnifiedSharingService`
ownership + shareable validation.

- `RelationshipName.FOR_GROUP` is removed from the enum.
- `UnifiedSharingService._check_shareable` admits a new curriculum set
  (`exercise`, `path_step`, `learning_path`) and allows sharing at any
  non-archived status — curriculum is shared at assignment time, well
  before it reaches a "completed" state.
- `ExerciseService` creates an ASSIGNED exercise by calling
  `sharing_service.share_with_group(...)` instead of a bare Cypher MERGE.
- All student-facing discovery queries (`get_student_exercises`,
  `user_context_queries.py` MEGA-QUERY, `report_relationship_service`) read
  from `SHARED_WITH_GROUP`.

A one-shot Cypher migration (`scripts/migrations/unify_group_sharing_2026_04.cypher`)
backfills existing `FOR_GROUP` edges into `SHARED_WITH_GROUP` with
`share_version='original'` and `migrated_from='FOR_GROUP'`.

### 2. `Group` is ingestion-creatable (teachers only).

`UserUploadService` accepts `type: Group` YAML files when the uploader has
`UserRole.TEACHER` or higher. The upload flow injects the uploader's UID as
`owner_uid`, and the ingestion service creates the `OWNS` edge from the
uploader to the new `:Group` node.

Group members are added via the existing edge ingestion path
(`type: Edge`, `relationship: MEMBER_OF`) — no new mechanism.

### 3. `Group` is visible in `UserContext`.

`UserContext` now carries:

- `user_groups` — groups the user is a `MEMBER_OF` (student role)
- `teacher_groups` — groups the user `OWNS` (with member counts)
- `group_assigned_exercise_uids` / `group_assigned_path_step_uids` /
  `group_assigned_learning_path_uids` — curriculum shared to any of the
  user's groups via `SHARED_WITH_GROUP`.

Populated via a dedicated `fetch_user_groups` query rather than threading
through the MEGA-QUERY — the group surface is narrow enough that a
separate query is simpler and keeps the MEGA-QUERY change minimal.

## Consequences

**Positive:**
- One mechanism, not two. Exercise, PathStep, and LearningPath share the
  same teacher→group path.
- `UnifiedSharingService` is the single enforcement point for sharing
  ownership, shareable-status, and metadata.
- Teachers can bulk-create groups and enrollments via YAML, same as the
  rest of the curriculum content.
- Intelligence services can finally see a user's class membership.

**Negative / Care required:**
- The data migration must run before any traffic hits the new code. The
  migration is idempotent (`MERGE` on the new edge), and there is a
  bootstrap assertion that rejects any residual `FOR_GROUP` edges.
- The `ExerciseService` now has a post-hoc wired `sharing_service` (the
  same pattern as `FormSubmissionService`) because of construction order
  in `services_bootstrap/compose.py`. A fully DI'd rewrite is a follow-up.

## Migration

```
scripts/migrations/unify_group_sharing_2026_04.cypher
```

The acceptance gate is the final `MATCH ()-[r:FOR_GROUP]->() RETURN
count(r)` query — it must return 0 after the migration.
