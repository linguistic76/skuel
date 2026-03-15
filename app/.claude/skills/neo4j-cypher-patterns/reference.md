# Neo4j Relationship Reference

Complete catalog of all relationship types in SKUEL's graph database.

**Source of Truth:** `/core/models/relationship_names.py`

## Relationship Categories

### Knowledge Relationships

Relationships involving Knowledge Units (`Curriculum` nodes).

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `PREREQUISITE` | Curriculum | Curriculum | Direct prerequisite dependency |
| `REQUIRES_PREREQUISITE` | Curriculum | Curriculum | Requires as prerequisite |
| `ENABLES` | Curriculum | Curriculum | This knowledge enables learning another |
| `RELATED_TO` | Curriculum | Curriculum | General semantic relationship |
| `HAS_NARROWER` | Curriculum | Curriculum | Parent → child concept hierarchy |
| `HAS_BROADER` | Curriculum | Curriculum | Child → parent concept hierarchy |
| `REQUIRES_KNOWLEDGE` | Goal/Task | Curriculum | Entity requires this knowledge |
| `APPLIES_KNOWLEDGE` | Task/Event | Curriculum | Entity applies this knowledge |
| `REINFORCES_KNOWLEDGE` | Habit | Curriculum | Habit reinforces this knowledge |
| `PRACTICES_KNOWLEDGE` | Event | Curriculum | Event practices this knowledge |
| `GROUNDED_IN_KNOWLEDGE` | Principle | Curriculum | Principle grounded in knowledge |
| `GROUNDS_PRINCIPLE` | Curriculum | Principle | Knowledge grounds this principle |
| `ENABLES_KNOWLEDGE` | Curriculum | Curriculum | Enables learning this knowledge |
| `ENABLES_GOAL` | Curriculum | Goal | Knowledge enables goal achievement |
| `ENABLES_TASK` | Curriculum | Task | Knowledge enables task completion |
| `INFORMS_CHOICE` | Curriculum | Choice | Knowledge informs this choice |
| `SUPPORTS_HABIT` | Curriculum | Habit | Knowledge supports habit formation |
| `COMPLETES_KNOWLEDGE` | Task | Curriculum | Task completion demonstrates mastery |
| `INFERRED_KNOWLEDGE` | * | Curriculum | Inferred (not explicit) knowledge link |
| `GUIDED_BY_KNOWLEDGE` | Goal | Curriculum | Goal guided by knowledge |
| `REINFORCED_BY_KNOWLEDGE` | Habit | Curriculum | Habit reinforced by knowledge |
| `BLOCKED_BY_KNOWLEDGE` | Task | Curriculum | Task blocked by lack of knowledge |

### Task Relationships

Task dependencies, contributions, and cross-domain links.

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `DEPENDS_ON` | Task | Task | Task dependency (blocking) |
| `BLOCKS` | Task | Task | This task blocks another |
| `BLOCKED_BY` | Task | Task | This task is blocked by another |
| `CONTRIBUTES_TO_GOAL` | Task | Goal | Task contributes to goal progress |
| `FULFILLS_GOAL` | Task | Goal | Task directly fulfills goal |
| `GENERATES_TASK` | * | Task | Something generates this task |
| `EXECUTES_TASK` | Event | Task | Event executes this task |
| `REQUIRES_TASK` | * | Task | Requires this task |
| `FUNDS_TASK` | Expense | Task | Expense funds this task |
| `TRIGGERS_ON_COMPLETION` | Task | Task | Completing triggers another |
| `UNLOCKS_KNOWLEDGE` | Task | Curriculum | Completing unlocks knowledge |
| `COMPLETED_TASK` | User | Task | User completed this task |
| `ASSIGNED_TO` | Task | User | Task assigned to user |

### Goal Relationships

Goal hierarchy, dependencies, and guidance.

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `SUBGOAL_OF` | Goal | Goal | This is a subgoal of parent |
| `HAS_SUBGOAL` | Goal | Goal | This goal has a subgoal |
| `HAS_CHILD` | Goal | Goal | Parent-child relationship |
| `DEPENDS_ON_GOAL` | Goal | Goal | Goal depends on another |
| `GUIDED_BY_PRINCIPLE` | Goal | Principle | Goal guided by principle |
| `SUPPORTS_GOAL` | Habit | Goal | Habit supports goal |
| `CONFLICTS_WITH_GOAL` | Goal | Goal | Goals conflict |
| `INSPIRES_GOAL` | * | Goal | Something inspires this goal |
| `CELEBRATED_BY_EVENT` | Goal | Event | Goal celebrated by event |
| `HAS_MILESTONE` | Goal | Milestone | Goal has milestone |
| `MILESTONE_OF` | Milestone | Goal | Milestone belongs to goal |
| `ALIGNED_WITH_PATH` | Goal | LifePath | Goal aligned with life path |
| `MOTIVATED_BY_GOAL` | * | Goal | Motivated by this goal |

### Habit Relationships

Habit chains, prerequisites, and reinforcement.

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `REQUIRES_PREREQUISITE_HABIT` | Habit | Habit | Habit requires another first |
| `ENABLES_HABIT` | Habit | Habit | This habit enables another |
| `REQUIRES_HABIT` | * | Habit | Requires this habit |
| `REINFORCES_HABIT` | * | Habit | Reinforces this habit |
| `INSPIRES_HABIT` | * | Habit | Inspires this habit |
| `REINFORCES_STEP` | Habit | LearningStep | Habit reinforces learning step |
| `EMBODIES_PRINCIPLE` | Habit | Principle | Habit embodies principle |
| `PRACTICED_AT_EVENT` | Habit | Event | Habit practiced at event |

### Event Relationships

Event conflicts, execution, and practice.

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `CONFLICTS_WITH` | Event | Event | Events conflict in schedule |
| `FUNDS_EVENT` | Expense | Event | Expense funds event |
| `ATTENDS` | User | Event | User attends event |

### Principle Relationships

Principle support, conflicts, and guidance.

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `SUPPORTS_PRINCIPLE` | * | Principle | Supports this principle |
| `CONFLICTS_WITH_PRINCIPLE` | * | Principle | Conflicts with principle |
| `GUIDES_GOAL` | Principle | Goal | Principle guides goal |
| `GUIDES_CHOICE` | Principle | Choice | Principle guides choice |
| `ALIGNED_WITH_PRINCIPLE` | Choice | Principle | Choice aligned with principle |

### Choice Relationships

Choice influences and outcomes.

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `INFORMED_BY_PRINCIPLE` | Choice | Principle | Choice informed by principle |
| `INFORMED_BY_KNOWLEDGE` | Choice | Curriculum | Choice informed by knowledge |
| `INSPIRED_BY_CHOICE` | * | Choice | Inspired by this choice |
| `IMPLEMENTS_CHOICE` | Task | Choice | Task implements choice |
| `REQUIRES_KNOWLEDGE_FOR_DECISION` | Choice | Curriculum | Choice requires knowledge |
| `OPENS_LEARNING_PATH` | Choice | Lp | Choice opens learning path |
| `AFFECTS_GOAL` | Choice | Goal | Choice affects goal |

### User/Ownership Relationships

User-to-entity ownership and progress.

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `HAS_TASK` | User | Task | User owns task |
| `HAS_EVENT` | User | Event | User owns event |
| `HAS_HABIT` | User | Habit | User owns habit |
| `HAS_GOAL` | User | Goal | User owns goal |
| `HAS_PRINCIPLE` | User | Principle | User has principle |
| `HAS_CHOICE` | User | Choice | User made choice |

### User Learning Progress Relationships

Track user interaction with knowledge units (pedagogical tracking).

State progression: `NONE` → `VIEWED` → `IN_PROGRESS` → `MASTERED`

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `VIEWED` | User | Curriculum | User has seen/read this content |
| `IN_PROGRESS` | User | Curriculum | User is actively learning |
| `MASTERED` | User | Curriculum | User has acquired this knowledge |
| `LEARNING` | User | Curriculum | Legacy - use IN_PROGRESS |

### Finance Relationships

Expense and budget connections.

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `PART_OF_PROJECT` | Expense | Project | Expense part of project |

### Learning Path Relationships

Learning path dependencies and completion.

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `REQUIRES_PATH_COMPLETION` | Lp | Lp | Path requires another path first |

### Evidence Relationships

Observable connections between knowledge units.

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `EXACERBATED_BY` | Entity | Entity | Subject exacerbated by target |
| `REDUCED_BY` | Entity | Entity | Subject reduced/mitigated by target |
| `CORRELATED_WITH` | Entity | Entity | Statistical correlation |
| `CAUSES` | Entity | Entity | Direct causal relationship |
| `PRECEDES` | Entity | Entity | Temporal precedence |

Evidence edges carry properties: `confidence` (0.0–1.0), `polarity` (-1/0/1), `temporality` (minutes/hours/days/chronic), `source` (self_observation/research/teacher/clinical), `evidence` (text), `observed_at`.

### Resource Relationships

Curriculum-to-Resource citations — connects teaching content to reference material.

| Relationship | From | To | Properties | Purpose |
|--------------|------|-----|------------|---------|
| `CITES_RESOURCE` | Lesson / Ku | Resource | `context` | Curriculum cites reference material (books, talks, films) |

```cypher
-- Find all Resources cited by Lessons in a Learning Step
MATCH (ls:LearningStep)-[:HAS_STEP]-(lp:LearningPath)
MATCH (ls)-[:CONTAINS_KNOWLEDGE]->(a:Lesson)-[:CITES_RESOURCE]->(r:Resource)
RETURN a.title AS article, r.title AS resource, r.author, r.media_type
```

### Content/Processing Relationships

Transcription, journal processing, and content linking.

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `TRANSCRIBED_FOR` | Transcription | Journal | Transcription created for journal |

### Authentication Relationships

Graph-native session and auth event tracking.

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `HAS_SESSION` | User | Session | User has active session |
| `HAD_AUTH_EVENT` | User | AuthEvent | User had auth event (audit) |
| `HAS_RESET_TOKEN` | User | ResetToken | User has password reset token |

## Helper Methods (RelationshipName Enum)

The `RelationshipName` enum provides helper methods:

```python
from core.models.relationship_names import RelationshipName

# Convert string to enum (returns None if invalid)
rel = RelationshipName.from_string("REQUIRES_KNOWLEDGE")

# Check if valid
is_valid = RelationshipName.is_valid("REQUIRES_KNOWLEDGE")  # True

# Category checks
rel = RelationshipName.REQUIRES_KNOWLEDGE
rel.is_knowledge_relationship()  # True
rel.is_blocking_relationship()   # False
rel.is_ownership_relationship()  # False
rel.is_learning_progress_relationship()  # False
```

## Edge Properties

Some relationships carry metadata on the edge:

### Confidence Score
```cypher
// Relationship with confidence
(task)-[:APPLIES_KNOWLEDGE {confidence: 0.85}]->(ku)

// Filter by confidence
MATCH (t:Task)-[r:APPLIES_KNOWLEDGE]->(ku:Curriculum)
WHERE r.confidence >= 0.8
```

### Mastery Score (Learning Progress)
```cypher
// User mastery with score
(user)-[:MASTERED {mastery_score: 0.95, mastered_at: datetime()}]->(ku)
```

### Timestamps
```cypher
// Relationship with timestamp
(user)-[:VIEWED {viewed_at: datetime()}]->(ku)
```
