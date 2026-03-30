---
title: Learning Progress Event Chain
updated: 2026-03-15
status: current
category: architecture
related:
- FOUR_PHASED_LEARNING_LOOP.md
- CURRICULUM_GROUPING_PATTERNS.md
- ../patterns/event_driven_architecture.md
---

# Learning Progress Event Chain

> "KU mastery ripples upward through the curriculum hierarchy automatically."

When a user masters a KU, progress propagates upward through the curriculum
hierarchy via event-driven subscriptions: KU → Lesson → PS → LP. Each level
is decoupled — services react to events, not direct calls. All handlers are
best-effort: failures are logged but never block the triggering action.

---

## The Chain

```
mark_mastered(ku_uid, user_uid)
    │
    ├─ Creates (User)-[:MASTERED]->(Ku) in Neo4j
    │
    └─ Publishes KnowledgeMastered
           │
           ├─► LpProgressService.handle_knowledge_mastered
           │       Find LPs containing this KU → recalculate LP progress
           │       → publish LearningPathProgressUpdated
           │       → if 100%: publish LearningPathCompleted
           │
           └─► LessonMasteryService.handle_knowledge_mastered
                   For each Lesson using this KU (via USES_KU):
                     Check if ALL KUs in that Lesson are mastered
                     → if yes: publish LessonCompleted
                                   │
                                   └─► PsProgressService.handle_lesson_completed
                                           Find LSs containing this Lesson (via HAS_LESSON)
                                           → recalculate PS progress (completed/total lessons)
                                           → publish PathStepProgressUpdated
                                           → if 100%: publish PathStepCompleted
                                                           │
                                                           └─► LpProgressService.handle_step_completed
                                                                   Find LPs containing this PS (via HAS_STEP)
                                                                   → recalculate LP progress
                                                                   → publish LearningPathProgressUpdated
```

---

## Events

| Event | Published By | Subscribers | Event Type String |
|-------|-------------|-------------|-------------------|
| `KnowledgeMastered` | `LessonMasteryService.mark_mastered()` | `LpProgressService`, `LessonMasteryService` | `knowledge.mastered` |
| `LessonCompleted` | `LessonMasteryService.handle_knowledge_mastered()` | `PsProgressService` | `lesson.completed` |
| `PathStepProgressUpdated` | `PsProgressService._update_ls_from_lesson_completion()` | Dashboard, Notifications | `path_step.progress_updated` |
| `PathStepCompleted` | `PsProgressService._update_ls_from_lesson_completion()` | `LpProgressService` | `path_step.completed` |
| `LearningPathProgressUpdated` | `LpProgressService._update_lp_from_ku_mastery()` | Dashboard, Notifications | `learning_path.progress_updated` |
| `LearningPathCompleted` | `LpProgressService._update_lp_from_ku_mastery()` | Achievements, Analytics | `learning_path.completed` |

---

## Graph Relationships

The chain relies on three graph relationships to propagate progress:

| Relationship | Pattern | Purpose |
|-------------|---------|---------|
| `USES_KU` | `(Lesson)-[:USES_KU]->(Ku)` | Lesson completion detection — are ALL KUs mastered? |
| `HAS_LESSON` | `(PS)-[:HAS_LESSON]->(Lesson)` | PS progress calculation — how many Lessons completed? |
| `HAS_STEP` | `(LP)-[:HAS_STEP]->(PS)` | LP progress recalculation on PS completion |

`HAS_LESSON` is derived from shared KU references: an PS and a Lesson are linked
when they share KUs via `CONTAINS_KNOWLEDGE`/`TRAINS_KU` and `USES_KU`.
Migration script: `scripts/migrations/add_has_lesson_relationship_2026_03.cypher`.

---

## Services

| Service | File | Role |
|---------|------|------|
| `LessonMasteryService` | `core/services/lesson/lesson_mastery_service.py` | Publishes `KnowledgeMastered` on `mark_mastered()`, detects Lesson completion |
| `PsProgressService` | `core/services/ls/ps_progress_service.py` | Tracks PS progress from Lesson completion |
| `LpProgressService` | `core/services/lp/lp_progress_service.py` | Tracks LP progress from KU mastery and PS completion |

### Backend Support

| Backend | File | Methods |
|---------|------|---------|
| `PsBackend` | `adapters/persistence/neo4j/domain_backends.py` | `get_steps_containing_lesson()`, `get_lesson_completion_progress()` |
| `LpBackend` | `adapters/persistence/neo4j/domain_backends.py` | `get_paths_containing_ku()`, `get_ku_mastery_progress()` |

---

## Bootstrap Wiring

All subscriptions are wired in `services_bootstrap/_event_wiring.py`:

```python
# KU mastery → LP progress (direct KU-level tracking)
event_bus.subscribe(KnowledgeMastered, lp_service.progress.handle_knowledge_mastered)

# KU mastery → Lesson completion detection
event_bus.subscribe(KnowledgeMastered, lesson_service.mastery.handle_knowledge_mastered)

# Lesson completion → PS progress
event_bus.subscribe(LessonCompleted, ps_service.progress.handle_lesson_completed)

# PS completion → LP progress (chain: PS→LP)
event_bus.subscribe(PathStepCompleted, lp_service.progress.handle_step_completed)
```

---

## Dual LP Progress Paths

`LpProgressService` receives progress signals through two independent paths:

1. **Direct KU mastery** (`handle_knowledge_mastered`) — recalculates LP progress
   whenever any KU in the LP is mastered. This is the fine-grained path.
2. **PS completion** (`handle_step_completed`) — recalculates LP progress when an
   entire PS is completed. This is the coarse-grained path.

Both paths converge on the same `_update_lp_from_ku_mastery()` method, which
recalculates progress from the current graph state. The numbers converge because
PS completion implies underlying KU mastery.

---

## Error Handling

Every handler in the chain follows the best-effort pattern:

```python
async def handle_knowledge_mastered(self, event: KnowledgeMastered) -> None:
    try:
        # ... progress logic ...
    except Exception as e:
        self.logger.error(f"Error handling knowledge_mastered event: {e}")
        # Never raises — KU mastery must not fail because progress tracking fails
```

If any handler fails:
- The triggering action (`mark_mastered()`) still succeeds
- Other subscribers still receive the event
- The error is logged for investigation
- Progress will self-correct on the next KU mastery event (recalculated fresh)

---

## Two Callers of mark_mastered()

| Caller | Score Source | Method | Context |
|--------|-------------|--------|---------|
| `TeacherReviewService.approve_report()` | `MasteryImpact.get_teacher_score()` (0.6–0.95) | `"ku_approval"` | Teacher approves a submission report — highest confidence |
| `ExerciseReportService._update_mastery_for_linked_ku()` | `MasteryImpact.get_ai_score()` (0.4–0.8) | `"activity_report"` | PERSONAL scope exercises with no teacher step |

Scores are determined by the Exercise's `mastery_impact` field (`MasteryImpact` enum):
MINOR (AI=0.4/Teacher=0.6), MODERATE (0.6/0.8, default), MAJOR (0.7/0.85),
CERTIFICATION (0.8/0.95). Both trigger the full event chain. Higher scores always
win (Cypher uses `CASE WHEN new > existing`), so teacher approval upgrades an
earlier AI score.

---

## See Also

| Document | What It Covers |
|----------|---------------|
| [FOUR_PHASED_LEARNING_LOOP.md](/docs/architecture/FOUR_PHASED_LEARNING_LOOP.md) | The five-phase loop this chain supports |
| [CURRICULUM_GROUPING_PATTERNS.md](/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md) | KU / PS / LP hierarchy and relationships |
| [event_driven_architecture.md](/docs/patterns/event_driven_architecture.md) | Event bus infrastructure and patterns |
| [adaptive-learning-loop-roadmap.md](/docs/roadmap/adaptive-learning-loop-roadmap.md) | Roadmap for closing remaining feedback loops |
