---
title: "TaskUpdateRequest Future completion_date — Create/Update Asymmetry"
updated: 2026-09-07
status: "ruled and shipped"
registered: 2026-08-24
ruled: 2026-09-07
---

# `TaskUpdateRequest` Future `completion_date` — Create/Update Asymmetry

*Closed 2026-09-07. Kept as the record of the ruling and of what the investigation
found that the open case file did not.*

## The ruling (Mike, 2026-09-07)

**Refuse a future `completion_date` on update too — symmetry with create.** The
2026-08-23 future-completion ruling was about HABITS and does not transfer: a future
habit *occurrence* is a real scheduled thing, while a task claiming it was *completed*
next year is not.

Shipped as `_refuse_future_completion_date` in `core/models/task/task_request.py`,
shared by both doors so neither can tighten or loosen alone.

## What the open case file recorded

`TaskCreateRequest` refused a future `completion_date`; `TaskUpdateRequest.to_intent()`
passed one straight through as a patch. Both claims verified on the live models before
the ruling.

## What the investigation added

1. **The create door enforces two rules, not one.** R1: no future date. R2: the stamp
   is non-null exactly when the task is completed. The update door enforced *neither*.
   R2's breach was a live bug rather than an unruled preference, and was fixed in the
   same change — see [Stranded Completion Stamp on First Ingest](stranded-completion-stamp-vault-first-ingest.md)
   for the one site that fix does not reach.

2. **The vector was reachable from the ordinary edit form**, not only the API:
   `completion_date` renders as "Completed on", a plain date input in the same
   Scheduling section as `status` (`ui/activities/tasks_form.py`).

3. **`TaskStatusUpdateRequest` has zero callers** — a dead model carrying its own
   `completion_date` defaulting validator. Not touched here; noted for a bloat sweep.

4. **The monotone-max reader was never at risk.** The case file worried about readers
   generally; `ProductivityAnalytics.last_completion_at` advances to the LATEST
   completion moment and never comes back, but the update chokepoint publishes
   `TaskCompleted` with the default `occurred_at=now`, not the stamp. Only the create
   and vault doors forward `completion_date`, and both were already bounded.

5. **The two windowed readers stay bounded on their own account.** Their upper bound
   is what a trailing window means, and it still contains any row stamped before the
   doors agreed — so the bound was not removed when the writers were fixed, only its
   rationale corrected (`core/constants.py`, `cross_domain_backend.py`).

## The R2 fix, and why it is not in the shared front half

`_refuse_stranded_stamp` lives in `core/services/completion_stamp.py` and is called by
`status_transition_guard` **only**. It was first written into `_stamp_target`, the half
shared with `validate_status_target` — which broke the vault door: a file carrying a
stale `completion_date:` beside an open status must be ingested and CLEANED, never
refused. Pinned by
`test_it_does_not_carry_the_stranded_stamp_refusal`.
