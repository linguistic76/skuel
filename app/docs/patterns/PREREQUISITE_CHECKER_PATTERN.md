---
title: PrerequisiteChecker & the Learning-Requirements Lens
updated: 2026-08-07
category: patterns
related_docs:
  - /docs/intelligence/GOALS_INTELLIGENCE.md
  - /docs/intelligence/TASKS_INTELLIGENCE.md
  - /docs/patterns/CONTEXT_FIRST_RELATIONSHIP_PATTERN.md
---

# PrerequisiteChecker & the Learning-Requirements Lens

**Core Principle:** "One mastery split, surfaced two ways — readiness and the rich payload come from the same source."

`PrerequisiteChecker` (`core/services/infrastructure/prerequisite_checker.py`) is the single
source of mastery-gap truth. It answers "is the user ready?" (a score + blocking reasons) and
feeds the richer "what does the user still need to learn?" display payload. Both are computed
from the same `check_prerequisites` split, so they never disagree (PR #254, #255).

## `check_prerequisites` → `PrerequisiteResult`

```python
result = PrerequisiteChecker.check_prerequisites(
    required_knowledge_uids=["ku.python"],
    required_task_uids=["task.setup"],
    context=user_context,
    mastery_threshold=0.7,   # DEFAULT_MASTERY_THRESHOLD
)
```

`PrerequisiteResult` is a frozen dataclass:

| Field | Type | Meaning |
|-------|------|---------|
| `score` | `float` | 0.0–1.0 — fraction of prerequisites met |
| `is_ready` | `bool` | `score >= mastery_threshold` (default 0.7) |
| `missing_knowledge` | `tuple[str, ...]` | KU UIDs not yet mastered |
| `missing_tasks` | `tuple[str, ...]` | task UIDs not yet completed |
| `blocking_reasons` | `tuple[str, ...]` | human-readable, capped (default 3) |

There is deliberately no Result-returning wrapper: `validate_prerequisites(...)` was
deleted 2026-08-06 with its one caller (the learning bridge's create half — see
`/docs/roadmap/learning-aligned-create-verb.md`). Creation-time prerequisite gates
live in the context doors (`create_task_with_context` and siblings), which check
UserContext sets directly and then create through the domain's core primitive.

## `build_learning_requirements` → `LearningRequirements`

The rich display payload, shared by the two domains that carry a `REQUIRES_KNOWLEDGE` edge
(**Tasks** and **Goals**):

```python
from core.services.infrastructure.prerequisite_checker import build_learning_requirements

reqs = build_learning_requirements(
    required_knowledge_uids=[...],   # KU UIDs the entity requires
    learning_path_uids=[...],        # LPs that cover them
    context=user_context,            # or None when mastery is unknown
)
```

The mastery split is delegated to `check_prerequisites` (same 0.7 threshold), so `knowledge_gaps`
and `ready_to_start` reflect the user's actual `knowledge_mastery`, not a stub. When `context is
None` (no user in scope) every requirement is treated as an open gap — reproducing the pre-mastery
behaviour exactly, so context-free callers are unchanged.

`LearningRequirements` is a `TypedDict` with three JSON-safe blocks:

- **`knowledge_requirements`** (`KnowledgeRequirementsBlock`): `required_knowledge`,
  `mastered_knowledge`, `knowledge_gaps` (each `list[dict[str, str]]`), `total_required`,
  `total_mastered`, `mastery_percentage`.
- **`learning_paths`** (`LearningPathsBlock`): `available_paths`, `recommended_path`,
  `estimated_learning_time` (hours — `LEARNING_HOURS_PER_KNOWLEDGE_AREA = 2` per unmet area).
- **`learning_analysis`** (`LearningAnalysisBlock`): `ready_to_start`, `has_prerequisites`,
  `learning_in_progress`, `knowledge_complete` (booleans).

## Where it surfaces

- `ContextualGoal` / `ContextualTask` (`core/models/context_types.py`) carry a
  `learning_requirements: LearningRequirements | None` field, built from `build_learning_requirements`.
  Their `blocking_reasons` / `learning_gaps` come from the same `check_prerequisites` call (this
  replaced the inline `_compute_readiness` / `_compute_blocking_reasons` helpers, now deleted).
  `can_start` tracks the **effective** readiness (`readiness >= 0.7`, honouring a
  `readiness_override`) — not `check.is_ready`.
- `GoalsIntelligenceService.get_goal_learning_requirements(uid, ..., user_context=None)` returns the
  three blocks for a single goal.
- **UI note:** the former profile-overview renderer (`_goal_focus_section` in
  `ui/profile/overview.py`) was removed 2026-07-05 with the dead overview surface — the
  `learning_requirements` payload currently has no UI renderer; it reaches consumers via
  `to_dict` / programmatic access. **Goals only** by design — actionable tasks are pre-filtered
  to ready in the planning service, so a task line would be inert. The Task field is still
  populated (for non-prefiltered consumers + `to_dict`).

**See:** [GOALS_INTELLIGENCE.md](/docs/intelligence/GOALS_INTELLIGENCE.md),
[TASKS_INTELLIGENCE.md](/docs/intelligence/TASKS_INTELLIGENCE.md),
[CONTEXT_FIRST_RELATIONSHIP_PATTERN.md](/docs/patterns/CONTEXT_FIRST_RELATIONSHIP_PATTERN.md).
