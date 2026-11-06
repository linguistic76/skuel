---
title: "LP Mastery and Next Step"
updated: 2026-11-06
status: "staged — kept by ruling; no implementation, no caller"
registered: 2026-11-06
ruled: "2026-11-06 — Mike keeps these two when the other never-built LpOperations declarations were deleted"
trigger: "a learning-path surface wants a learner's mastery across a path, or the next step for that learner"
check: "git grep -nE 'def (calculate_mastery|get_next_step)\\b' -- core adapters"
---

# LP Mastery and Next Step

Two capabilities `LpOperations` declared and no backend ever implemented. The declarations were removed with the rest (a protocol member with no implementation now fails `tests/unit/adapters/test_backend_protocol_conformance.py`), and the two are kept here because Mike wants them.

| As declared | What it answers |
|---|---|
| `calculate_mastery(uid, user_uid) -> Result[float]` | The learner's average mastery across every step of the path, 0.0-1.0 |
| `get_next_step(uid, completed_step_uids) -> Result[PathStep \| None]` | The next step to complete in the path, or None when it is complete |

Both belong on a service, `LpService` and the sub-service behind it, not on the backend port: each composes reads.

## What is already nearby

- **Next step.** `core/models/pathways/lp_position.py` has a private `_get_next_step(path, completed_step_uids)` that `LpPosition` reads; nothing outside its own module builds an `LpPosition`. `LpService.get_current_step` returns the first step not completed, but reads the step's own status, so it is not per learner. `LpService.get_next_adaptive_step` ranks by edge metadata from a current step and answers a different question.
- **Completed.** Mike's ruling of 2026-11-06 for the PathStep page: marked as read or mastered. `PsIntelligenceBackend.fetch_prerequisite_statuses` reads those two edges, and a next step should agree with it.
- **Mastery.** A step's mastery is the `MASTERED` edge `PsMasteryService` writes. The learner's map is `UserContext.knowledge_mastery`.

## Open when this is picked up

Whether a path's mastery averages steps or the Kus under them; and what a draft step does to the average. A draft step is withheld from learners, and `fetch_prerequisite_statuses` neither shows nor counts one.
