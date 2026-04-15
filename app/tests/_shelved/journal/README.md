# Shelved — ADR-054 Commit 6a

These tests target the legacy `core/services/journal/` package, which is
being retired in favor of the unified `core/services/user_entry/` hub
(ADR-054).

## Contents

- `test_option_a_journals_processing.py` — integration tests for the
  "Option A" journal processing flow (`JournalInputService` →
  `JournalOutputService`). The new pipeline routes journal audio/text
  through `UserEntryProcessingService` + `UserEntryService`.

## Reshelving convention

Per the user's standing instruction
(`memory/feedback_shelve_not_delete.md`): code and tests are moved to
`_shelved/` with a short README instead of being deleted outright.
