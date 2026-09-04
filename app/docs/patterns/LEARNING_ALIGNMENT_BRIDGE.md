---
title: LearningAlignmentBridge - Unified Learning Integration Pattern
updated: '2026-09-04'
category: patterns
related_skills: []
related_docs:
  - roadmap/learning-aligned-create-verb.md
---
# LearningAlignmentBridge - Unified Learning Integration Pattern

**Location:** `/core/services/infrastructure/learning_alignment_bridge.py`

**Status:** ✅ Read/assess operations only — the create half was deleted 2026-08-06 (see below)

---

## Overview

The **LearningAlignmentBridge** is a generic infrastructure service that eliminates
duplication across Activity Domain learning services by providing unified
implementations of the learning-alignment READ patterns. Before the helper, every
domain had near-identical copies of:

- `get_learning_supporting_X()` (~57 lines each)
- `suggest_learning_aligned_X()` (~72 lines each)
- `assess_X_learning_alignment()` (~55 lines each)

One generic implementation now serves them all, parameterized as
`LearningAlignmentBridge[T]` and customized per domain through
optional hooks.

### Architecture Position

```
Layer 4: Domain Learning Services (Tasks, Goals, Habits, Choices, Principles)
    ↓ uses
Layer 3: LearningAlignmentBridge (Infrastructure)
    ↓ uses
Layer 2: BaseService (DTO conversion helpers)
    ↓ uses
Layer 1: UniversalNeo4jBackend[T] (Persistence — reads only)
```

---

## The create half was DELETED (2026-08-06)

The bridge once carried `create_with_learning_alignment()` and
`create_batch_with_learning_alignment()`, wired to dict-based
`backend.create_{domain}` doors. Three facts sank them together:

1. **The doors never existed.** `backend.create_task` / `create_goal` / … resolve
   through `UniversalNeo4jBackend.__getattr__` to `create(entity)`, which expects a
   DOMAIN MODEL. The bridge handed it `request.model_dump()` — a dict with no
   `uid` and no `user_uid` — so every real call persisted a corrupt uid-less,
   ownerless node and then raised converting it back. Only mock-based unit tests
   kept the paths green.
2. **Nothing reached them.** All seven wrapper methods (Tasks 1, Goals 2, Habits 2,
   Events 2) were facade-exposed with zero callers above the facades and zero
   integration coverage.
3. **The create-time "alignment" was a log line.** Nothing was persisted from the
   assessment, so a wired wrapper would have been functionally the domain's core
   create primitive plus a log statement.

Creation belongs to each domain's core primitive (`TasksCoreService.create_task`,
`GoalsCoreService.create_goal`, …), which publishes the domain event, requests the
ADR-074 embedding, and writes the request's link edges through the admission guard
(`keep_permitted_link_edges`) — every domain whose create request carries link uids;
Principles' carries none. The
orchestrator context doors (`create_goal_with_context`,
`create_habit_with_context`) keep their gates and now create through those
primitives. The two genuinely valuable create-verb ideas the bridge half carried
("act on a learning recommendation", "LP → calendar schedule") are recorded in
`/docs/roadmap/learning-aligned-create-verb.md` with the build surface to use
when either becomes a lived need.

---

## Capabilities

| Capability | Method | Description |
|------------|--------|-------------|
| **Support Filtering** | `get_learning_supporting_entities()` | User's entities that support learning, filtered (score > 0.3) and sorted |
| **Suggestion Generation** | `suggest_learning_aligned_entities()` | Suggestion dicts from active paths: current step mastery, path completion, outcomes |
| **Alignment Assessment** | `assess_learning_alignment()` | Structured assessment for one existing entity (support score, milestones, recommendations) |
| **Scoring** | `calculate_learning_score()` | Default algorithm: domain match +0.4, knowledge match +0.5, text match +0.3 |

---

## Construction

```python
# In {Domain}LearningService.__init__
self.learning_helper = LearningAlignmentBridge[Goal](
    service=self,                                  # provides _to_domain_model(s), dto/model classes via _config
    backend_get=self.backend.get_goal,             # single-entity read
    backend_get_user=self.backend.get_user_goals,  # per-user read
    domain=Domain.GOALS,
    entity_name="goal",                            # for log lines
)
```

`dto_class` / `model_class` are derived from the service's `_config` — a service
without them fails fast at construction.

Bridges live today in: `tasks_learning` (suggest), `goals_learning`
(assess/suggest/get), `habits_learning` (suggest/get/assess), `choices_learning`
(suggest), `principles_learning` (assess). A learning service that only needs one
operation still constructs the one bridge — the unused methods cost nothing.

---

## Custom Hooks

Three optional hooks customize behavior without touching the helper:

| Hook | Signature | Replaces / extends | Used by |
|------|-----------|--------------------|---------|
| `alignment_scorer` | `(entity, LpPosition) -> float` | Replaces the default scoring algorithm in `calculate_learning_score()` | Principles |
| `suggestion_filter` | `(suggestion_dict, filter_param) -> bool` | Filters generated suggestions (True = keep) | (available) |
| `embodiment_scorer` | `(entity, LpPosition) -> dict` | Merged into the assessment dict after the base assessment | Principles |

All three are synchronous functions. Execution points:

```
calculate_learning_score():        alignment_scorer  ← instead of default algorithm
suggest_learning_aligned_entities(): generate → merge custom_suggestions → suggestion_filter
assess_learning_alignment():       base assessment → embodiment_scorer merged in
```

---

## Usage Pattern

Every domain wrapper is a thin delegation:

```python
async def assess_goal_learning_alignment(
    self, goal_uid: str, learning_position: LpPosition
) -> Result[dict[str, Any]]:
    return await self.learning_helper.assess_learning_alignment(
        entity_uid=EntityUID(goal_uid), learning_position=learning_position
    )
```

---

## Migration History

- **January 2026 (Phase 6):** introduced; all 6 Activity Domains integrated,
  ~723 LOC of duplication collapsed.
- **2026-08-06:** create half deleted (see above). The `backend_create`,
  `prerequisite_validator`, and `custom_fields` plumbing left with it; the three
  read/assess operations and their hooks are the whole surface. The
  scheduling-service bridges (Tasks/Goals/Habits) and the Events learning bridge,
  which existed only to create, were removed with their wrappers.
- **2026-09-03:** the class is `LearningAlignmentBridge[T]`. The `DTO` and
  `Request` type parameters, which nothing in the read surface consumes, left
  the signature.
