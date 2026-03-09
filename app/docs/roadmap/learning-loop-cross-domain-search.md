# Learning Loop Cross-Domain Search

*Created: 2026-03-07*

## Status

| Level | Description | Status |
|-------|-------------|--------|
| 1 | Registry wiring (EntityType, NeoLabel, RelationshipName) | Complete |
| 2 | Search config (SearchRouter domain dispatch, `_simple_domain_search`) | Complete |
| 3a | Graph-aware search for Exercise, RevisedExercise, Submission | Complete |
| 3b | Learning loop chain traversal on ReportRelationshipService | Complete |

## Level 3a: Graph-Aware Search

Exercise, RevisedExercise, and Submission now use `graph_aware_faceted_search` via SearchRouter instead of falling through to `_simple_domain_search`.

**Changes:**
- Added `_graph_enrichment_patterns` ClassVar to `ExerciseService`, `RevisedExerciseService`, `SubmissionsSearchService`
- Modified `SearchRouter._graph_aware_domain_search` to check if the service itself implements `SupportsGraphAwareSearch` (not just `.search` sub-service)
- Added `_DOMAIN_ATTR_ALIASES` for `submissions → submissions_search` mapping
- Expanded `_GRAPH_AWARE_DOMAINS` from 9 to 12

**Graph enrichment per domain:**

| Domain | Enrichment Patterns |
|--------|-------------------|
| Exercise | `REQUIRES_KNOWLEDGE` (outgoing), `FOR_GROUP` (outgoing), `FULFILLS_EXERCISE` (incoming) |
| RevisedExercise | `RESPONDS_TO_FEEDBACK` (outgoing), `REVISES_EXERCISE` (outgoing), `FULFILLS_EXERCISE` (incoming) |
| Submission | `FULFILLS_EXERCISE` (outgoing), `FEEDBACK_FOR` (incoming) |

## Level 3b: Learning Loop Chain Traversal

Two methods on `ReportRelationshipService` for multi-hop graph traversal:

### `get_learning_loop_chain(exercise_uid)`

Teacher/admin view: "show me everything related to this exercise."

```
(Submission)-[:FULFILLS_EXERCISE]->(Exercise)
(SubmissionReport)-[:FEEDBACK_FOR]->(Submission)
(RevisedExercise)-[:RESPONDS_TO_FEEDBACK]->(SubmissionReport)
```

Returns: `{exercise, submissions, feedback, revised_exercises}`

### `get_submission_chain(submission_uid)`

Student view: "what happened after I submitted?"

```
(Submission)-[:FULFILLS_EXERCISE]->(Exercise)
(SubmissionReport)-[:FEEDBACK_FOR]->(Submission)
(RevisedExercise)-[:RESPONDS_TO_FEEDBACK]->(SubmissionReport)
```

Returns: `{submission, exercise, feedback, revised_exercises}`

### Protocol

`ReportRelationshipOperations` in `core/ports/report_protocols.py` covers all 5 methods (3 existing + 2 new).

## Future: SubmissionFeedback and ActivityReport Search

These entities currently lack BaseService-based search:
- **SubmissionReport**: `SubmissionReportService` is an LLM generator, not a BaseService. Would need a `SubmissionReportSearchService` extending BaseService.
- **ActivityReport**: `ActivityReportService` is standalone. Would need search methods or a BaseService wrapper.

Both are lower priority since teachers primarily search by Exercise or Submission, then navigate to feedback via relationships.
