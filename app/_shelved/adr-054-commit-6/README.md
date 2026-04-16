# ADR-054 Commit 6b — Shelved Legacy Services, Events, Protocols, Models

Shelved during ADR-054 Commit 6b. Parent commit: `503bbdfc` (Commit 6b-prep — clear dangling legacy imports).

These files are the pre-ADR-054 service, event, protocol, and model layer for `Submission`, `ExerciseSubmission`, `JeInput`, and `JeOutput`. Load-bearing logic was ported to `core/services/user_entry/` in Commit 6a; the packages shelved here contain only internal self-references and dead code.

## Contents

### `core/services/submissions/`
- `submissions_service.py` — Facade for the legacy submissions domain.
- `submissions_core_service.py` — CRUD + `process_exercise_submission` (ported to `core/services/user_entry/exercise_linker.py`).
- `submissions_processing_service.py` — Pipeline orchestration (replaced by `UserEntryProcessor`).
- `submissions_search_service.py` — Search (replaced by `UserEntrySearchService`).
- `submissions_relationship_service.py` — Relationship creation (ported to `core/services/user_entry/relationship_service.py`).
- `learning_loop_event_handler_service.py` — Iteration tracking + mastery velocity (ported to `core/services/user_entry/learning_loop_handler.py`).
- `learning_loop_query_service.py` — Learning-loop Cypher queries (ported to `core/services/user_entry/learning_loop_query.py`).

### `core/services/journal/`
- `journal_input_service.py` — JeInput CRUD + file upload (replaced by `UserEntryService`).
- `journal_output_service.py` — JeOutput LLM processing (replaced by `UserEntryProcessor`).

### `core/events/`
- `submission_events.py` — Legacy submission events. The four learning-loop events were relocated and renamed in Commit 6a: `ReportSubmitted`, `RevisedExerciseCreated` (kept names) and `SubmissionApproved` -> `UserEntryApproved`, `SubmissionRevisionRequested` -> `UserEntryRevisionRequested` — now in `core/events/learning_loop_events.py`.
- `journal_events.py` — Legacy journal events (superseded by `UserEntry` events in `core/events/user_entry_events.py`).

### `core/ports/`
- `journal_protocols.py` — Journal service protocols (superseded by `core/ports/user_entry_protocols.py`).

### `core/models/submissions/`
- `submission.py`, `submission_dto.py` — Base `Submission` model + DTO (replaced by `UserEntry`).
- `exercise_submission.py`, `exercise_submission_dto.py` — Leaf model + DTO (replaced by `UserEntry`).
- `submission_requests.py` — Pydantic request models.

### `core/models/journal/`
- `je_input.py`, `je_input_dto.py` — JeInput model + DTO (replaced by `UserEntry`).
- `je_output.py`, `je_output_dto.py` — JeOutput model + DTO (replaced by `UserEntry`).
- `journal_insight.py` — Journal insight model.

### `adapters/persistence/neo4j/backends/`
- `journal_backends.py` — `JournalInputBackend`, `JournalOutputBackend` (replaced by `UserEntryBackend`).

## New homes for ported logic

| Legacy location | New location |
|---|---|
| `SubmissionsRelationshipService` | `core/services/user_entry/relationship_service.py` |
| `LearningLoopEventHandlerService` | `core/services/user_entry/learning_loop_handler.py` |
| `LearningLoopQueryService` | `core/services/user_entry/learning_loop_query.py` |
| `ProcessingOutcome` + `process_exercise_submission` | `core/services/user_entry/exercise_linker.py` |
| `SubmissionProcessingContext` / `SubmissionAIInsights` | `core/services/content_enrichment/types.py` as `EnrichmentContext` / `EnrichmentInsights` |
| `ReportSubmitted` / `RevisedExerciseCreated` | `core/events/learning_loop_events.py` (names kept) |
| `SubmissionApproved` / `SubmissionRevisionRequested` | `core/events/learning_loop_events.py` as `UserEntryApproved` / `UserEntryRevisionRequested` |

## Not shelved

- `SubmissionsBackend` (`adapters/persistence/neo4j/backends/submissions_backend.py`) — still wired; deferred to Commit 7.
- `assessment_service.py`, `report_schedule.py` — moved earlier per Commit 2.
- `submission_processing_types.py` — moved to `core/services/content_enrichment/types.py` in Commit 6a.
- `submission_protocols.py` (`core/ports/`) — already removed prior to 6b.
