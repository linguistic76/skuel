# Learning Loop Cross-Domain Search (Level 3)

*Created: 2026-03-07*

## Status: Roadmap

Level 1+2 (registry wiring, search config) are complete. This doc covers Level 3: cross-loop graph traversal search.

## Cross-Loop Graph Traversal

Given an Article UID, traverse the full learning loop chain to find related entities:

```
Article -[:FULFILLS_EXERCISE]-> Exercise
Exercise -[:FEEDBACK_FOR]-> SubmissionFeedback
SubmissionFeedback -[:RESPONDS_TO_FEEDBACK]-> RevisedExercise
RevisedExercise -[:REVISES_EXERCISE]-> Exercise (back to loop)
```

### Use Cases

1. **Teacher view:** "Show me everything related to the photosynthesis article" -- returns the article, all exercises, student submissions, feedback, and revised exercises
2. **Student view:** "What revised exercises exist for content I've submitted?" -- traverses from Submission back through feedback to RevisedExercise
3. **Curriculum audit:** "Which articles have no exercises yet?" -- find Articles with no incoming FULFILLS_EXERCISE

### Implementation Approach

Add a `search_learning_chain(article_uid)` method to SearchRouter that:
1. Starts from the Article node
2. Traverses FULFILLS_EXERCISE, FEEDBACK_FOR, RESPONDS_TO_FEEDBACK, REVISES_EXERCISE
3. Returns grouped results by entity type

### Future: SubmissionFeedback and ActivityReport Search

These entities currently lack BaseService-based search:
- **SubmissionFeedback**: `FeedbackService` is an LLM generator, not a BaseService. Would need a `SubmissionFeedbackSearchService` extending BaseService.
- **ActivityReport**: `ActivityReportService` is standalone. Would need search methods or a BaseService wrapper.

Both are lower priority since teachers primarily search by Exercise or Submission, then navigate to feedback via relationships.
