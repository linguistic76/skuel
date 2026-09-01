---
updated: 2026-08-08
---

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
| RevisedExercise | `RESPONDS_TO_REPORT` (outgoing), `REVISES_EXERCISE` (outgoing), `FULFILLS_REVISED_EXERCISE` (incoming) |
| Submission | `FULFILLS_EXERCISE` (outgoing, → root Exercise), `FULFILLS_REVISED_EXERCISE` (outgoing, revision-cycle only), `REPORT_FOR` (incoming) |

## Level 3b: Learning Loop Chain Traversal

Two methods on `ReportRelationshipService` for multi-hop graph traversal:

### `get_learning_loop_chain(exercise_uid)`

Teacher/admin view: "show me everything related to this exercise."

```
(UserEntry)-[:FULFILLS_EXERCISE]->(Exercise)
(EntryReport)-[:REPORT_FOR]->(UserEntry)
(RevisedExercise)-[:RESPONDS_TO_REPORT]->(EntryReport)
```

Returns: `{exercise, submissions, feedback, revised_exercises}`

### `get_submission_chain(submission_uid)`

Student view: "what happened after I submitted?"

```
(UserEntry)-[:FULFILLS_EXERCISE]->(Exercise)
(EntryReport)-[:REPORT_FOR]->(UserEntry)
(RevisedExercise)-[:RESPONDS_TO_REPORT]->(EntryReport)
```

Returns: `{submission, exercise, feedback, revised_exercises}`

### Protocol

`ReportRelationshipOperations` in `core/ports/report_protocols.py` covers all 5 methods (3 existing + 2 new).

## Future: EntryReport and ActivityReport Search

> Tracked live in `../deferred-work.md` § EntryReport / ActivityReport Search (extracted
> when this doc moved to `done/` — the section below is the record; the register is the
> tracker).

These entities currently lack BaseService-based search:
- **EntryReport**: `EntryReportService` is an LLM generator, not a BaseService. Would need a `EntryReportSearchService` extending BaseService.
- **ActivityReport**: `ActivityReportService` is standalone. Would need search methods or a BaseService wrapper.

Both are lower priority since teachers primarily search by Exercise or Submission, then navigate to feedback via relationships.
