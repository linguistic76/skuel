---
title: "Zero-Ku PathStep Mastery — a step that teaches no Ku cannot be mastered by derivation"
updated: 2026-10-01
status: "deferred — waits on a product decision"
registered: 2026-10-01
trigger: "A learner needs to complete a PathStep that teaches no Ku (a reflective or practice-only step), or the content vault starts authoring such steps on purpose"
check: "MATCH (ps:Entity:PathStep) WHERE NOT EXISTS { (ps)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(:Entity) } RETURN count(ps) — the live count of steps no learner can master (1 of 25 on AuraDB at registration)"
---

# Zero-Ku PathStep Mastery — a step that teaches no Ku cannot be mastered by derivation

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## What is live

A PathStep's `(User)-[:MASTERED]->(PathStep)` edge is **derived**: `PsMasteryService.handle_knowledge_mastered`
(`core/services/ps/ps_mastery_service.py`) runs `detect_path_step_completion` on every `KnowledgeMastered`
event, and for each step whose Kus — over `USES_KU`, `CONTAINS_KNOWLEDGE` and `TRAINS_KU` — are now all
mastered it writes the edge through `mark_mastered` (the Ku edge's writer and shape: `mastered_at`,
`mastery_score` 1.0, `confidence`, `method = 'derived'`), retires the step's `IN_PROGRESS` enrollment, and
only then publishes `PathStepCompleted`. There is no other writer of a step's mastery.

## The gap

`detect_path_step_completion` anchors on the mastered Ku, so a step with **no** Ku edge is never a candidate,
and `get_ku_completion_progress` reports `total_kus == 0` for it — `PsProgressService` logs and returns.
Such a step can be viewed, started (`IN_PROGRESS`), read and bookmarked, but never mastered: nothing a
learner does reaches a `MASTERED` edge, its enrollment never retires, and a learning path containing it can
never reach 100 % through the step chain.

## What it waits on

A product decision, not code: whether a Ku-less step is a content defect (the knowledge-health gauge could
flag it as an authoring warning — `KnowledgeHealthService`, `/docs/tools/KNOWLEDGE_HEALTH.md`) or a legitimate
shape (a reflection or practice step) that needs a **manual** "mark step complete" door — a learner-facing
action on `/explore/ps/{uid}` that calls `mark_mastered` on the step with a `method` naming the learner
(`self_report` is the vocabulary the Ku side already uses) and publishes `PathStepCompleted` itself.

Either way the writer stays one: `mark_mastered`. A manual door must not grow a second edge shape.
