---
title: "Path Step Prerequisite Gate"
updated: 2026-11-24
status: "ruled, not built — its own PR"
registered: "2026-11-24 (bootstrap typing residuals, row 2i-b-vi)"
ruled: "2026-11-24 — a prerequisite step is one the learner masters before the step that requires it may be undertaken; the gate on the doors is its own PR"
trigger: "the row is taken up"
check: "git grep -nE 'prerequisite' -- core/services/ps/ps_mastery_service.py core/services/ps_engagement/ps_engagement_service.py — no hit means no door checks a step's prerequisites before undertaking it"
---

# Path Step Prerequisite Gate

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## The rule

A prerequisite step is one the learner masters before the step that requires it may be undertaken.
Met is the learner's `MASTERED` edge to the prerequisite, the one completion edge
([path-step-completion-read.md](done/path-step-completion-read.md)). The PathStep page's Blocking
dependencies accordion shows each prerequisite as Completed or Blocked by that edge, and the chain
door (`GET /api/path-steps/prerequisites`) counts `unmet_count` by it.

## What nothing enforces

Every door that undertakes a step does so whatever its prerequisites:

- `POST /explore/ps/{uid}/progress` with `state=learning` (`PsMasteryService.mark_in_progress`), and
  with `review=true` (`mark_as_learning`, Review again);
- `POST /api/path-steps/{uid}/start` (`mark_in_progress`);
- `POST /api/ps/{ps_uid}/engage` (`PsEngagementService.engage_pathstep`, which spawns the step's
  templates).

The only refusal on the first two is the two-step enrollment cap.

## Open when this is picked up

- Census every writer of `IN_PROGRESS` and `ENGAGED_WITH` onto a `PathStep`, not only the routes above.
- Which prerequisites gate: `REQUIRES_STEP` alone, or `REQUIRES_KNOWLEDGE` too (the accordion and
  the chain door read both). A draft prerequisite is withheld from both, so it neither shows nor
  blocks.
- What a step undertaken before its prerequisites were mastered becomes: one started before the gate,
  or one whose prerequisite was added later.
- Whether Review again, on a step the learner already undertook, passes the gate.
