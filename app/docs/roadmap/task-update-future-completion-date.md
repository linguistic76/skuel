---
title: "TaskUpdateRequest Future completion_date — Create/Update Asymmetry"
updated: 2026-09-05
status: "ruling needed"
registered: 2026-08-24
trigger: "next touch of task_request.py's validators — take it to Mike, do not rule in passing"
check: "ruling: refuse future on update too, or allow on both and bound the readers"
---

# `TaskUpdateRequest` Future `completion_date` — Create/Update Asymmetry

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

`TaskCreateRequest` refuses a future `completion_date` ("semantically impossible and would pin
itself atop completion-date-ordered reads" — `core/models/task/task_request.py`,
`default_completion_date_when_completed`); `TaskUpdateRequest.to_intent()` passes one straight
through as a patch. The 2026-08-23 future-completion ruling was about HABITS — future habit
occurrences are legitimate — and does not extend to Tasks; the create-vs-update asymmetry inside
Tasks is UNRULED. The decision (Mike's): refuse future on update too (symmetry with create), or
allow on both and bound the readers (the habits precedent). The two windowed readers are already
bounded either way (#1139/#1142).

**Trigger:** ruling — take it to Mike on the next touch of `task_request.py`'s validators; do
not rule it in passing.
**Named cost:** until ruled, an update can plant the future-dated stamp the create door exists
to refuse, pinning itself atop completion-date-ordered reads.
