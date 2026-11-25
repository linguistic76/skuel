---
title: "Path Step Prerequisite Gate"
updated: 2026-11-25
status: "done — every door that starts a step admits it only once the learner has mastered every published prerequisite in its chain"
registered: "2026-11-24 (bootstrap typing residuals, row 2i-b-vi)"
ruled: "2026-11-24 — a prerequisite step is one the learner masters before the step that requires it may be undertaken; the gate is its own PR. 2026-11-25 — the gate follows the chain; it governs starting, not holding; Review again and the mastered-step write folded in; engage rolls back on its own failure; a draft step is refused at engage; the Ku-progress door needs the step started"
---

# Path Step Prerequisite Gate

*Closed case file. It was the [deferred-work.md](../deferred-work.md) entry of the same name.*

## The rule

A learner starts a step only once every published prerequisite in its chain is mastered. The
chain is what the step requires through `REQUIRES_STEP` or `REQUIRES_KNOWLEDGE`, directly or
through another prerequisite, up to `PREREQUISITE_GATE_DEPTH` (10) hops. Met is the learner's
`MASTERED` edge ([path-step-completion-read.md](path-step-completion-read.md)); marking a
prerequisite as read does not meet it. A draft is withheld, and so is a prerequisite reached only
through one: nobody can master what no reader names, so it never blocks.

Direct prerequisites alone would not do: a step can be mastered without being started (its Kus
mastered through another step), so a step's own prerequisites can all be mastered while one of
theirs is not (Mike, 2026-11-25: the gate follows the chain).

## One read, three readers

`PsIntelligenceBackend.fetch_prerequisite_statuses` reads the chain with the learner's mastery on
each row, through `build_prerequisite_chain_query` (the same builder as the step stats' count).
It is behind:

- the PathStep page's Blocking dependencies: the whole chain, nearest-first, a row two or more
  hops away marked *Earlier prerequisite*; Start learning is disabled, counting what is left,
  while any row is Blocked;
- the chain door, `GET /api/path-steps/prerequisites`, whose default depth is the gate's, so an
  `unmet_count` of 0 is a step every door admits;
- `PsPrerequisiteGate` (`core/services/ps/ps_prerequisite_gate.py`).

## The doors

`PsMasteryService.mark_in_progress` is the one writer that starts a step. Its refusals, in order:
a uid that is not a published step (`not_found`, as for a uid naming nothing); an unmet
prerequisite (`ps_prerequisites_unmet`, naming what to master first); a step already mastered
(`ps_already_mastered`, decided again by the write); the enrollment cap of two
(`ps_enrollment_cap`), which moved here from the two routes that held it. It serves
`POST /explore/ps/{uid}/progress` (`state=learning`) and `POST /api/path-steps/{uid}/start`.

`PsEngagementService.engage_pathstep` asks the same gate before anything else, so a draft step is
refused as missing and a step with an unmet prerequisite opens no edge and spawns nothing
(`POST /api/ps/{uid}/engage`, `POST /explore/ps/{uid}/engage`). On the step page, a step with task
templates is started first and engaged only once the start lands; an engagement that then fails
leaves the step Learning and says so in a toast.

The doors that start nothing act only on a step the learner holds in progress, so none is a way
round the gate:

- Mark as read (`state=read`, `POST /api/path-steps/{uid}/mark-read`);
- Review again (`state=learning&review=true`), which now only takes back a mark as read: on a
  mastered step it is refused and its button is gone, where it used to write `IN_PROGRESS` beside
  `MASTERED` and take an enrollment slot;
- `POST /api/pathways/progress`, the self-report of a step's Kus (`PsMasteryService.require_held`).

## Held steps

The gate governs the act of starting. A step a learner already holds stays held when a
prerequisite is added to it later, or when it was started before the gate existed; nothing
sweeps it (Mike, 2026-11-25). On the live graph at the time, the one held step whose prerequisites
were unmet had only draft prerequisites, which do not block.

## Left for other rows

- `/api/path-steps/{uid}/start` has no caller and the `/explore/ps/{uid}/engage` button group is
  rendered by nothing; retiring them is 2i-b-x's (engaging a step and starting it become one act).
- The Ku-progress door reads a step's Kus off `CONTAINS_KNOWLEDGE` only (`LpService.get_step`),
  where mastery derivation reads `USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU`.
