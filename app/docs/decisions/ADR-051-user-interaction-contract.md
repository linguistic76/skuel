---
adr: 051
title: User Interaction Contract — EntityType.INTERACTION (22nd Entity Type)
status: Accepted
date: 2026-04-02
deciders: Mike
tags:
  - entity-types
  - learning-loop
  - submissions
  - zpd
related:
  - ADR-047-entity-types-replace-domain-categories
  - ADR-043-intelligence-tier-toggle
---

# ADR-051: User Interaction Contract

## Status

Accepted — implemented in commit `686d7b69` (entity + service) and `cb4af2c5` (UserContext wiring).

---

## Context

`ExerciseSubmission` records *what* a student submitted against an Exercise, but it
carries no information about *where in the curriculum* the student was studying when
they submitted.

This gap matters for:
- **ZPD (Zone of Proximal Development):** To assess learning readiness, ZPD needs to
  know not just which exercises a student has completed but which PathSteps and
  LearningPaths those completions occurred within.
- **Askesis (Socratic companion):** Personalized guidance requires knowing the student's
  active curriculum position, not just their submission history.
- **Learning trajectory analysis:** "Student X submitted three exercises while studying
  PathStep Y" is a different signal than three submissions across unrelated contexts.

Adding `context_path_step_uid` and `context_learning_path_uid` directly to
`ExerciseSubmission` would work but embeds curriculum-position data inside a submission
artifact, mixing two concerns. It would also prevent querying context as a first-class
dimension (e.g. "all submissions that happened during PathStep Y").

---

## Decision

Add `EntityType.INTERACTION` as SKUEL's 22nd entity type.

An Interaction is a **situated learning-loop audit record** — a first-class Neo4j node
capturing who did what, to which target, in which curriculum context, and with what
result.

**Key design choices:**

1. **Separate node, not fields on ExerciseSubmission.** Interaction is queryable as a
   graph node. Traversals like
   `MATCH (i:Interaction)-[:INTERACTION_DURING]->(ps:PathStep)` are natural Cypher.
   Embedding context fields in ExerciseSubmission would require filtering within a single
   node's properties rather than traversing relationships.

2. **Auto-created by SubmissionsService, not user-initiated.** Users don't create
   Interactions directly. `SubmissionsService._create_interaction_record()` fires after a
   successful ExerciseSubmission. Failure is logged but never propagates to the user.

3. **UI-driven deterministic context capture (updated 2026-04-02).** PathStep context
   flows from explicit UI navigation: PathStep detail → Exercise card → Submit form, via
   a `from_ps={ps_uid}` query parameter. The submit form embeds it as a hidden field;
   `_get_learning_context(explicit_ps_uid=...)` in route handlers uses it directly rather
   than falling back to the nondeterministic `next(iter(ctx.current_ps_uids))` heuristic.
   LearningPath UID still comes from `UserContext.current_learning_path_uid`. `from_ps`
   is absent on standalone submissions (no PathStep navigation), in which case the
   UserContext heuristic applies as a best-effort fallback.

4. **YAML-ingestible (Phase 1).** Despite being auto-generated in production, Interaction
   has a full `EntityIngestionConfig` so test fixtures and content authors can create
   them via YAML if needed.

5. **`InteractionResult` tracks pipeline progression.** The `result_status` field starts
   as `PENDING` and is intended to transition as the submission pipeline completes
   (`REPORT_GENERATED`, `SHARED_WITH_TEACHER`, `COMPLETED`). Phase 2 will wire this
   lifecycle to the report generation pipeline.

---

## Implementation

**New files:**
- `core/models/enums/interaction_enums.py` — `InteractionType` + `InteractionResult`
- `core/models/interaction/interaction.py` — `Interaction(UserOwnedEntity)`, 6 fields
- `core/models/interaction/interaction_dto.py` — `InteractionDTO(UserOwnedDTO)`
- `core/services/interaction/interaction_service.py` — `create_interaction()` + `list_interactions_for_user()`

**Modified files (key):**
- `entity_enums.py` — `INTERACTION = "interaction"` added (22nd value)
- `submissions_service.py` — `_create_interaction_record()` called after submission creation
- `submissions_api.py` / `submissions_ui.py` — `user_service` wired in; `_get_learning_context(explicit_ps_uid=...)` helper prefers explicit `from_ps` param over UserContext heuristic
- `path_steps_ui.py` — exercises section added; links carry `?from_ps={ps_uid}` context
- `exercises_ui.py` — "Submit →" button forwards `from_ps` query param
- `ui/submissions/forms.py` — `render_upload_form(from_ps=...)` embeds PathStep context as hidden field
- `adapters/persistence/neo4j/_knowledge_context_mixin.py` — `get_exercises_for_path_step()` added
- `core/services/ps_service.py` — `get_exercises_for_path_step()` facade method added

**New relationships:**
- `RECORDS` — `(Interaction)-[:RECORDS]->(ExerciseSubmission | ...)`
- `INTERACTION_DURING` — `(Interaction)-[:INTERACTION_DURING]->(PathStep)`
- `INTERACTION_WITHIN` — `(Interaction)-[:INTERACTION_WITHIN]->(LearningPath)`

---

## Consequences

**Phase 1 (shipped, UI enhanced 2026-04-02):**
- Every ExerciseSubmission creates an Interaction node capturing the user's curriculum
  position at submission time.
- Interaction nodes are queryable via `InteractionService.list_interactions_for_user()`.
- PathStep context is now captured **deterministically** via `from_ps` UI navigation:
  PathStep detail page → exercise card → submit form → hidden field → upload handler.
  Before 2026-04-02, context used `next(iter(UserContext.current_ps_uids))`, which was
  ambiguous when a student had multiple IN_PROGRESS PathSteps simultaneously.
- The "By Student" teaching admin view now shows **all** student submissions (not just
  those auto-shared via the ASSIGNED exercise pipeline), closing the gap where
  personal/standalone submissions were permanently invisible to the teacher.

**Phase 2 (deferred):**
- ZPD will query `(u:User)-[:OWNS]->(i:Interaction)-[:INTERACTION_DURING]->(ps:PathStep)`
  to build situated learning evidence.
- Askesis will use Interaction history to contextualise its Socratic responses.
- `result_status` will be updated by the report generation pipeline when a report is
  created (currently remains PENDING).
- `InteractionType.KU_VIEW`, `PATH_STEP_COMPLETION`, and `FORM_SUBMISSION` are reserved
  enum values for future interaction capture points.

---

## Alternatives Considered

**A. Add `context_path_step_uid` + `context_learning_path_uid` directly to `ExerciseSubmission`.**
Simple, no new entity type. Rejected because: (1) mixes submission artifact with
curriculum position context; (2) cannot query context as a graph dimension; (3) signals
that context is second-class metadata rather than a first-class event.

**B. Add a `SUBMITTED_DURING` relationship from ExerciseSubmission to PathStep.**
Cleaner than field embedding but still couples the submission artifact to curriculum
context without a queryable intermediate node. Interaction as a node enables richer
analytics (interaction counts per PathStep, result distribution per LearningPath, etc.).
