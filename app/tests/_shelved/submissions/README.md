# Shelved — ADR-054 Commit 6a

These tests target the legacy `core/services/submissions/` package, which is
being retired in favor of the unified `core/services/user_entry/` hub
(ADR-054). They are moved here instead of deleted so that the test logic
can inform the post-6b rewrite when the legacy backend is removed.

## Contents

- `test_submissions_core_service.py` — original `SubmissionsCoreService` unit
  tests. The `process_exercise_submission` slice was retargeted to
  `tests/unit/services/user_entry/test_exercise_linker.py`; the rest
  (get/update/archive/categorize/tags/bulk/delete/export) is shelved.
- `test_submissions_search_service.py` — `SubmissionsSearchService` tests;
  search surface will be reworked on top of `UserEntry` post-6b.
- `test_processing_events.py` — event-emission tests for the old
  `SubmissionsProcessingService`; the new wiring publishes
  `UserEntryCreated` from `UserEntryService.create_entry()` and is covered
  by `tests/unit/services/test_user_entry_service.py`.

## Reshelving convention

Per the user's standing instruction
(`memory/feedback_shelve_not_delete.md`): code and tests are moved to
`_shelved/` with a short README instead of being deleted outright.
