---
title: Learning Progress Event Chain
updated: 2026-08-28
status: current
category: architecture
related:
- LEARNING_LOOP_ARCHITECTURE.md
- CURRICULUM_GROUPING_PATTERNS.md
- ../patterns/event_driven_architecture.md
---

# Learning Progress Event Chain

> "KU mastery ripples upward through the curriculum hierarchy automatically."

When a user masters a KU, progress propagates upward through the curriculum
hierarchy via event-driven subscriptions: **KU → PathStep → LearningPath**. Each
level is decoupled — services react to events, not direct calls. All handlers
are best-effort: failures are logged but never block the triggering action.

The former `Lesson` layer was merged into `PathStep` in April 2026, so the
chain now has two propagation steps instead of three.

---

## The Chain

This traces the **progress-propagation** path only — the handlers that recompute PathStep and
LearningPath progress. It is *not* the complete subscriber set; user-context invalidation,
analytics and the FULL-tier ZPD hub also consume these events.

To find every consumer, read both wiring modules — `services_bootstrap/_event_wiring.py` and
`services_bootstrap/_intelligence_hub.py` (FULL tier). Grepping an event's class name is **not
sufficient**: some subscriptions are registered by looping over a list of event types
(`for event_type in learning_context_events`), some import the class under an alias, and some
`.subscribe(` calls in the tree are examples inside docstrings rather than live wiring.

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
           ├─► PsProgressService.handle_knowledge_mastered
           │       Find PathSteps using this KU (via USES_KU) → recalculate
           │       PS progress (kus_mastered / kus_total)
           │       → publish PathStepProgressUpdated
           │
           └─► PsMasteryService.handle_knowledge_mastered
                   For each PathStep using this KU:
                     Check if ALL KUs in that PathStep are mastered
                     → if yes: publish PathStepCompleted
                                   │
                                   └─► LpProgressService.handle_step_completed
                                           Find LPs containing this PS (via HAS_STEP)
                                           → recalculate LP progress
                                           → publish LearningPathProgressUpdated
```

---

## Events

| Event | Published By | Event Type String |
|-------|-------------|-------------------|
| `KnowledgeMastered` | `PsMasteryService.mark_mastered()` | `knowledge.mastered` |
| `PathStepProgressUpdated` | `PsProgressService.handle_knowledge_mastered()` | `path_step.progress_updated` |
| `PathStepCompleted` | `PsMasteryService.handle_knowledge_mastered()` | `path_step.completed` |
| `LearningPathProgressUpdated` | `LpProgressService._update_lp_from_ku_mastery()` | `learning_path.progress_updated` |
| `LearningPathCompleted` | `LpProgressService._update_lp_from_ku_mastery()` | `learning_path.completed` |

There is deliberately no *Subscribers* column. The one that used to be here named
"Dashboard, Notifications" as consumers of the two progress events — neither of which has a
handler by that name anywhere in the tree.

Of the two columns that remain, only the event-type string is definition-local: it is the
`ClassVar` in the event's own file. **`Published By` is a copied fact and can drift** — a
publisher may move, or a second one may appear, and nothing here will fail. Re-derive it with
`git grep '<EventClass>(' -- core/services/`, which is reliable in a way the equivalent
subscriber search is not: a constructor call puts the class name and its opening parenthesis
together, whereas subscriptions are registered through loop variables and aliases.

For consumers, read the two wiring modules named below.

---

## Graph Relationships

The chain relies on two graph relationships to propagate progress:

| Relationship | Pattern | Purpose |
|-------------|---------|---------|
| `USES_KU` | `(PathStep)-[:USES_KU]->(Ku)` | PS completion detection — are ALL KUs in this PathStep mastered? |
| `HAS_STEP` | `(LearningPath)-[:HAS_STEP]->(PathStep)` | LP progress recalculation on PS completion |

There is no intermediate `HAS_LESSON` edge. PathStep composes atomic Kus directly
via `USES_KU`, and LearningPaths compose PathSteps directly via `HAS_STEP`.

---

## Services

| Service | File | Role |
|---------|------|------|
| `PsMasteryService` | `core/services/ps/ps_mastery_service.py` | Publishes `KnowledgeMastered` on `mark_mastered()`, detects PathStep completion |
| `PsProgressService` | `core/services/ps/ps_progress_service.py` | Recalculates PS progress from KU mastery |
| `LpProgressService` | `core/services/lp/lp_progress_service.py` | Tracks LP progress from KU mastery and PS completion |

### Backend Support

| Backend | File | Methods |
|---------|------|---------|
| `PsBackend` | `adapters/persistence/neo4j/backends/curriculum_backends.py` | PathStep ↔ Ku traversal, mastery rollup queries |
| `LpBackend` | `adapters/persistence/neo4j/backends/curriculum_backends.py` | `get_paths_containing_ku()`, `get_ku_mastery_progress()` |

---

## Bootstrap Wiring

The progress-chain subscriptions are wired in `services_bootstrap/_event_wiring.py`. This is
**not** every subscription to these events: `services_bootstrap/_intelligence_hub.py` registers
FULL-tier ZPD handlers for `KnowledgeMastered`, `PathStepCompleted` and
`LearningPathProgressUpdated` (under aliased import names), and the context-invalidation loop
in `_event_wiring.py` subscribes them again as part of a list.

```python
# KU mastery → LP progress (direct KU-level tracking)
event_bus.subscribe(KnowledgeMastered, lp_service.progress.handle_knowledge_mastered)

# KU mastery → PS progress (fine-grained recalculation)
event_bus.subscribe(KnowledgeMastered, ps_service.progress.handle_knowledge_mastered)

# KU mastery → PS completion detection
event_bus.subscribe(KnowledgeMastered, ps_service.mastery.handle_knowledge_mastered)

# PS completion → LP progress (chain: PS→LP)
event_bus.subscribe(PathStepCompleted, lp_service.progress.handle_step_completed)
```

---

## Dual LP Progress Paths

`LpProgressService` receives progress signals through two independent paths:

1. **Direct KU mastery** (`handle_knowledge_mastered`) — recalculates LP progress
   whenever any KU in the LP is mastered. This is the fine-grained path.
2. **PathStep completion** (`handle_step_completed`) — recalculates LP progress
   when an entire PathStep is completed. This is the coarse-grained path.

Both paths converge on the same recalculation method, which reads the current
graph state. The numbers converge because PS completion implies underlying KU
mastery.

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
| `EntryReportService._update_mastery_for_linked_ku()` | `MasteryImpact.get_ai_score()` (0.4–0.8) | `"activity_report"` | PERSONAL scope exercises with no teacher step |

Scores are determined by the Exercise's `mastery_impact` field (`MasteryImpact` enum):
MINOR (AI=0.4/Teacher=0.6), MODERATE (0.6/0.8, default), MAJOR (0.7/0.85),
CERTIFICATION (0.8/0.95). Both trigger the full event chain. Higher scores always
win (Cypher uses `CASE WHEN new > existing`), so teacher approval upgrades an
earlier AI score.

---

## See Also

| Document | What It Covers |
|----------|---------------|
| [LEARNING_LOOP_ARCHITECTURE.md](/docs/architecture/LEARNING_LOOP_ARCHITECTURE.md) | The four-phase loop this chain supports |
| [CURRICULUM_GROUPING_PATTERNS.md](/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md) | KU / PS / LP hierarchy and relationships |
| [event_driven_architecture.md](/docs/patterns/event_driven_architecture.md) | Event bus infrastructure and patterns |
