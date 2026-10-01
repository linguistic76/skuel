---
title: "Zero-Ku PathStep Mastery — a step that teaches no Ku is a content defect"
updated: 2026-10-01
status: "done — ruled 2026-10-01; the knowledge-health gauge names every Ku-less step"
registered: 2026-10-01
ruled: 2026-10-01
---

# Zero-Ku PathStep Mastery — a step that teaches no Ku is a content defect

*Closed case file (opened as a `deferred-work.md` entry the same day). Nothing in it remains open.*

## The ruling (Mike, 2026-10-01)

> A zero-Ku step cannot be mastered — that sounds right. But more than that, there should be
> **no** zero-Ku step. Every learning step requires Kus if it is legitimate. A Ku-less step is a
> content defect.

So there is no manual "mark step complete" door, and the derivation stays the one writer of a
step's mastery. The remedy is authoring guidance: the knowledge-health gauge
(`KnowledgeHealthService`, `/docs/tools/KNOWLEDGE_HEALTH.md`) counts and lists every PathStep with
no `USES_KU` / `CONTAINS_KNOWLEDGE` / `TRAINS_KU` edge onto a Ku (`ku_less_step_count`,
`ku_less_steps`) and flags any count at all — no threshold, a defect is a defect — on
`./dev knowledge-health`, `/admin/knowledge-health` and the report JSON. Fix each one in the vault
(compose Kus into the step) and re-sync.

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

## What the gap meant for a learner

Such a step could be viewed, started (`IN_PROGRESS`), read and bookmarked, but never mastered: nothing a
learner did reached a `MASTERED` edge, its enrollment never retired, and a learning path containing it could
never reach 100 % through the step chain. The ruling makes that the author's problem, surfaced by the gauge,
not a learner door.
