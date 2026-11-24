---
title: "Enrollment Progress Counts Prerequisite Kus"
updated: 2026-11-24
status: "open — registered, not ruled"
registered: "2026-11-24 (bootstrap typing residuals, row 2i-b-vi)"
trigger: "a ruling on what an enrollment's completion counts"
check: "grep -n 'REQUIRES_KNOWLEDGE' adapters/persistence/neo4j/_lp_progress_mixin.py — a hit inside record_enrollment_progress means the recount still counts the path's prerequisite Kus"
---

# Enrollment Progress Counts Prerequisite Kus

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## What it counts

`_LpProgressMixin.record_enrollment_progress` recounts a learner's progress in a path and writes
it on the `ENROLLED_IN` edge: `r.progress` is the learner's mastered Kus over the path's Kus, and
`r.status` becomes `completed` when it reaches 1.0. The path's Kus are two sets:

- the Kus the path's steps teach (`HAS_STEP` → `USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU`);
- the path's own prerequisite Kus (`(lp)-[:REQUIRES_KNOWLEDGE]->(ku)`).

## Why it is a question

A prerequisite is what the learner masters before the thing that requires it may be undertaken
(Mike, 2026-11-24, for prerequisite steps). By that meaning a path's prerequisite Kus come before
the path, not inside it, yet the recount counts them toward the path's progress and its completion.

No page shows `r.progress`; a path's progress on the LP pages, on Insights and in the user context is
its mastered steps over its steps ([path-step-completion-read.md](done/path-step-completion-read.md)).
`r.status` is read: the learning-velocity `paths_completed` count and the completed-path lists. So
two meanings of a completed path stand side by side: every step mastered (Insights'
`completed_learning_paths`), and every Ku mastered, prerequisites included (`paths_completed`). They
also part on a step that teaches no Ku (never derived as mastered) and on draft steps (their Kus are
counted; a draft step is never derived).

## Open when this is picked up

- Whether an enrollment's completion counts the path's prerequisite Kus.
- Whether a completed enrollment and a path with every step mastered should be one rule.
