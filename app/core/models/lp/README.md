# Learning Domain Model (LearningPath & LearningStep)

The Learning domain represents structured learning paths and steps in SKUEL - guided sequences for knowledge acquisition.

## Overview

Learning paths provide:
- Structured sequences for learning knowledge
- Step-by-step progression with prerequisites
- Mastery tracking for each step
- Multiple path types (structured, adaptive, exploratory)
- Integration with Knowledge domain
- Progress calculation and next-step recommendation

**Key Features**: Sequential steps with prerequisites, mastery thresholds, embedded or referenced steps, learning outcomes.

## YAML Structure - LearningPath

### Required Fields

| Field | Type | Pattern | Description |
|-------|------|---------|-------------|
| `version` | String | `1.0` | YAML schema version |
| `type` | String | `LearningPath` | Entity type identifier |
| `uid` | String | `lp:path-name` | Unique identifier (e.g., `lp:study-skills-101`) |
| `name` | String | 1-200 chars | Display name for the path |
| `goal` | String | Text | What the learner will achieve |
| `domain` | Enum | Domain | Knowledge domain classification |

### Optional Fields - LearningPath

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `path_type` | Enum | `structured` | Type of learning path structure |
| `difficulty` | String | `intermediate` | Overall difficulty level |
| `steps` | List | `[]` | Learning step UIDs OR embedded step objects |
| `prerequisites` | List[str] | `[]` | Knowledge UIDs required before starting |
| `outcomes` | List[str] | `[]` | Learning outcomes upon completion |
| `estimated_hours` | Float | `0.0` | Total time to complete (auto-calculated if steps provided) |
| `created_by` | String | `null` | Creator UID (e.g., "system", "user:mike") |

### Metadata Fields - LearningPath (Auto-Populated)

| Field | Type | Description |
|-------|------|-------------|
| `created_at` | DateTime | When path was created |
| `updated_at` | DateTime | When path was last modified |

## YAML Structure - LearningStep

### Required Fields - LearningStep

| Field | Type | Pattern | Description |
|-------|------|---------|-------------|
| `uid` | String | `ls:path-name:step-number` | Unique identifier (e.g., `ls:study-skills-101:step-1`) |
| `title` | String | 1-200 chars | Step title |
| `intent` | String | Text | What to accomplish in this step |
| `knowledge_uid` | String | UID | KnowledgeUnit this step teaches |
| `sequence` | Integer | 1+ | Order in the path |

### Optional Fields - LearningStep

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mastery_threshold` | Float | `0.7` | Required mastery level (0.0-1.0) |
| `estimated_hours` | Float | `1.0` | Time to complete this step |
| `prerequisites` | List[str] | `[]` | Other step UIDs that must complete first |
| `notes` | String | `null` | Additional notes or guidance |

## Enum Values

### path_type (LearningPathType)
- `structured` - Pre-defined sequence (default) - most common
- `adaptive` - Adjusts based on progress
- `exploratory` - Open-ended discovery
- `remedial` - Address knowledge gaps
- `accelerated` - Fast track

### difficulty
- `beginner` - Introductory level
- `intermediate` - Moderate level (default)
- `advanced` - Advanced level
- `expert` - Expert level

### domain (Domain - from shared_enums)
- `personal` - Personal development
- `professional` - Career/work
- `technical` - Technical skills
- `health` - Health and wellness
- `financial` - Financial goals
- `social` - Relationships and community
- `knowledge` - Learning and education

## Example YAML - Referenced Steps

```yaml
version: 1.0
type: LearningPath
uid: lp:study-skills-101
name: Study Skills 101 — Simple & Steady

goal: Build foundational study skills through focused blocks and spaced repetition

domain: personal
path_type: structured
difficulty: beginner

# Reference separate LearningStep YAML files
steps:
  - ls:study-skills-101:step-1
  - ls:study-skills-101:step-2
  - ls:study-skills-101:step-3

prerequisites:
  - ku:basic-learning-concepts

outcomes:
  - Execute focused 25-minute study blocks
  - Create effective notes using headers and bullets
  - Apply spaced repetition for durable memory
  - Manage distractions during study sessions

estimated_hours: 1.5
created_by: system
```

## Example YAML - Embedded Steps

```yaml
version: 1.0
type: LearningPath
uid: lp:study-skills-101
name: Study Skills 101 — Simple & Steady

goal: Build foundational study skills through focused blocks and spaced repetition

domain: personal
path_type: structured
difficulty: beginner

# Embed full LearningStep definitions inline
steps:
  - uid: ls:study-skills-101:step-1
    title: Learn Spaced Repetition Basics
    intent: Understand why short reviews beat cramming
    knowledge_uid: ku:spaced-repetition-basics
    sequence: 1
    mastery_threshold: 0.7
    estimated_hours: 0.25

  - uid: ls:study-skills-101:step-2
    title: Practice Effective Note-Taking
    intent: Create simple, readable notes
    knowledge_uid: ku:note-taking-basics
    sequence: 2
    mastery_threshold: 0.7
    estimated_hours: 0.5
    prerequisites:
      - ls:study-skills-101:step-1

  - uid: ls:study-skills-101:step-3
    title: Handle Distractions
    intent: Learn to keep focus clean
    knowledge_uid: ku:distraction-handling
    sequence: 3
    mastery_threshold: 0.7
    estimated_hours: 0.75
    prerequisites:
      - ls:study-skills-101:step-1

prerequisites:
  - ku:basic-learning-concepts

outcomes:
  - Execute focused 25-minute study blocks
  - Create effective notes using headers and bullets
  - Apply spaced repetition for durable memory
  - Manage distractions during study sessions

estimated_hours: 1.5  # Auto-calculated from steps if omitted
created_by: system
```

## Example YAML - LearningStep (Separate File)

```yaml
version: 1.0
type: LearningStep
uid: ls:study-skills-101:step-1
title: Learn Spaced Repetition Basics
intent: Understand why short reviews beat cramming

knowledge_uid: ku:spaced-repetition-basics
sequence: 1

mastery_threshold: 0.7
estimated_hours: 0.25

prerequisites: []
notes: |
  This is the foundational step. Focus on understanding the concept
  before moving to application.
```

## Common Mistakes

### ❌ CRITICAL: Missing title and intent in LearningStep
```yaml
type: LearningStep
uid: ls:example:step-1
knowledge_uid: ku:example
sequence: 1
# FAILS - missing required 'title' and 'intent' fields!
```

### ✅ Correct: Include title and intent
```yaml
type: LearningStep
uid: ls:example:step-1
title: Example Step Title       # ✅ Required
intent: What to accomplish      # ✅ Required
knowledge_uid: ku:example
sequence: 1
```

---

### ❌ Wrong: Invalid UID pattern for LearningStep
```yaml
uid: step-1                      # FAILS - missing prefix
uid: ku:example                  # FAILS - wrong prefix (ku: is for Knowledge)
```

### ✅ Correct: Use proper LearningStep UID pattern
```yaml
uid: ls:study-skills-101:step-1  # ✅ Correct: ls:path-name:step-number
```

---

### ❌ Wrong: Mastery threshold out of range
```yaml
mastery_threshold: 1.5           # FAILS - must be 0.0-1.0
mastery_threshold: -0.2          # FAILS - must be 0.0-1.0
```

### ✅ Correct: Valid mastery threshold
```yaml
mastery_threshold: 0.7           # ✅ Valid - 70% mastery required
mastery_threshold: 0.85          # ✅ Valid - 85% mastery required
```

---

### ❌ Wrong: Sequence number starts at 0
```yaml
sequence: 0                      # FAILS - sequences start at 1
```

### ✅ Correct: Sequence starts at 1
```yaml
sequence: 1                      # ✅ Valid - first step
sequence: 2                      # ✅ Valid - second step
```

---

### ❌ Wrong: Missing 'goal' field in LearningPath
```yaml
type: LearningPath
uid: lp:example
name: Example Path
domain: personal
# FAILS - missing required 'goal' field!
```

### ✅ Correct: Include goal field
```yaml
type: LearningPath
uid: lp:example
name: Example Path
goal: What learner will achieve  # ✅ Required
domain: personal
```

---

### ❌ Wrong: Using 'title' instead of 'name' for LearningPath
```yaml
type: LearningPath
uid: lp:example
title: Example Path              # FAILS - LearningPath uses 'name' not 'title'!
```

### ✅ Correct: Use 'name' for LearningPath
```yaml
type: LearningPath
uid: lp:example
name: Example Path               # ✅ Correct field name
```

## Field Differences - LearningPath vs Other Models

| Feature | LearningPath | KnowledgeUnit | Task | Goal |
|---------|--------------|---------------|------|------|
| **Display Name** | `name` ⚠️ | `title` | `title` | `title` |
| **Purpose Field** | `goal` (what to achieve) | N/A | N/A | `description` |
| **Steps/Sequence** | YES (`steps` list) | NO | YES (subtasks) | YES (sub-goals) |
| **Prerequisites** | Knowledge UIDs | Knowledge UIDs | Task/Knowledge UIDs | Knowledge UIDs |
| **Outcomes** | YES (learning outcomes) | NO | NO | NO |
| **Difficulty** | YES (`difficulty` field) | YES (`complexity` field) | NO | NO |
| **Timestamps** | Both | Both | Both | Both |

## Field Differences - LearningStep vs Other Models

| Feature | LearningStep | KnowledgeUnit | Task |
|---------|--------------|---------------|------|
| **Display Name** | `title` | `title` | `title` |
| **Purpose** | `intent` ⚠️ | `summary` | `description` |
| **Sequence** | YES (explicit order) | NO | NO |
| **Mastery** | YES (`mastery_threshold`, `current_mastery`) | NO | NO |
| **Prerequisites** | Step UIDs | Knowledge UIDs | Task/Knowledge UIDs |

## Business Logic Methods - LearningPath

The LearningPath domain model (Tier 3) includes:

### Progress & Navigation
- `get_next_step(completed_step_uids)` - Get next available step
- `calculate_progress()` - Overall path progress (0.0-1.0)
- `calculate_mastery()` - Average mastery across steps
- `is_completed(completed_step_uids)` - Check if path complete
- `get_completed_steps()` - List of completed steps
- `get_remaining_steps(completed_step_uids)` - List of remaining steps

### Prerequisites & Requirements
- `has_prerequisites()` - Check if prerequisites exist
- `is_ready_for_user(user_knowledge)` - Check if user meets prerequisites

### Time Estimation
- `estimated_completion_time(current_mastery)` - Estimate remaining time
- `total_estimated_hours()` - Sum of all step hours

### Graph Intelligence (Phase 1-4 Integration)
- `build_path_traversal_query()` - APOC query for step sequence
- `build_knowledge_coverage_query()` - APOC query for knowledge connections
- `get_suggested_query_intent()` - Recommended QueryIntent for path analysis

## Business Logic Methods - LearningStep

The LearningStep domain model (Tier 3) includes:

### Status & Readiness
- `is_ready(completed_steps)` - Check if prerequisites met
- `is_mastered()` - Check if mastery threshold met
- `progress_percentage()` - Progress as percentage (0-100)

## Steps: Referenced vs Embedded

### Referenced Steps (Recommended for larger paths)
```yaml
# In LearningPath file
steps:
  - ls:study-skills-101:step-1
  - ls:study-skills-101:step-2

# In separate step-1.yaml file
type: LearningStep
uid: ls:study-skills-101:step-1
title: Learn Spaced Repetition
# ... rest of step definition
```

**Pros**: Easier to maintain, clearer file organization, reusable steps
**Cons**: More files to manage

### Embedded Steps (Good for small paths)
```yaml
# In LearningPath file
steps:
  - uid: ls:study-skills-101:step-1
    title: Learn Spaced Repetition
    # ... complete step definition

  - uid: ls:study-skills-101:step-2
    title: Practice Note-Taking
    # ... complete step definition
```

**Pros**: Single file, easier for small paths
**Cons**: Harder to maintain for large paths, can't reuse steps

## Model File Locations

```
/core/models/learning/
├── learning.py                  # Tier 3: Frozen domain models (LearningPath, LearningStep)
├── learning_dto.py              # Tier 2: Mutable DTOs for data transfer
├── learning_request.py          # Tier 1: Pydantic validation models
└── learning_converters.py       # Conversion between tiers
```

## Template Reference

Full YAML template with all fields and documentation:
`/home/mike/skuel/app/yaml_templates/_schemas/learning_path_template.yaml`

See also:
`/home/mike/skuel/app/yaml_templates/_schemas/learning_step_template.yaml`

## Validation Rules

**From Pydantic Request Models** (`learning_request.py`):

- `name`: 1-200 characters (required for LearningPath)
- `goal`: Required for LearningPath
- `title`: 1-200 characters (required for LearningStep)
- `intent`: Required for LearningStep
- `mastery_threshold`: 0.0-1.0 range
- `estimated_hours`: Must be > 0
- `sequence`: Must be >= 1

## Best Practices

1. **Use referenced steps for large paths** - Easier to maintain and organize
2. **Use embedded steps for small paths** - Simpler for 2-4 step paths
3. **Set appropriate mastery thresholds** - 0.7 (70%) is a good default
4. **Define clear learning outcomes** - What will learners be able to do?
5. **Establish prerequisites** - What should learners know before starting?
6. **Use sequential UIDs** - `ls:path-name:step-1`, `ls:path-name:step-2`, etc.
7. **Include intent for each step** - Clarify the purpose of each step
8. **Estimate time realistically** - Help learners plan their learning
9. **Use structured path_type** - Most common for linear learning sequences
10. **Link to knowledge properly** - Each step should reference a KnowledgeUnit

## Learning Path Types

### Structured (Most Common)
```yaml
path_type: structured
# Linear sequence: Step 1 → Step 2 → Step 3
# Each step builds on the previous
```

### Adaptive
```yaml
path_type: adaptive
# Adjusts based on learner performance
# May skip/add steps based on mastery
```

### Exploratory
```yaml
path_type: exploratory
# Learner-directed
# Multiple valid paths through content
```

### Remedial
```yaml
path_type: remedial
# Address specific knowledge gaps
# Targeted learning for missing foundations
```

### Accelerated
```yaml
path_type: accelerated
# Fast-paced for experienced learners
# Higher mastery thresholds, less time per step
```

## Integration with Knowledge Domain

```yaml
# LearningPath connects multiple KnowledgeUnits
prerequisites:
  - ku:basic-concepts           # Must know before starting

steps:
  - uid: ls:example:step-1
    knowledge_uid: ku:topic-1   # Learn this in step 1

  - uid: ls:example:step-2
    knowledge_uid: ku:topic-2   # Learn this in step 2
    prerequisites:
      - ls:example:step-1       # After mastering step 1

outcomes:
  - Apply topic 1 and topic 2 together
  - Create projects using learned knowledge
```

## Notes

- LearningPath uses `name` field (not `title`) - different from most other models
- LearningPath requires `goal` field to clarify what learners will achieve
- LearningStep uses `intent` field to clarify step purpose
- LearningStep UID pattern: `ls:path-name:step-number`
- Mastery threshold of 0.7 (70%) is a reasonable default
- Sequence numbers start at 1, not 0
- Steps can be referenced (separate files) or embedded (inline)
- Prerequisites create step dependencies
- estimated_hours auto-calculates from steps if not provided
- Graph intelligence methods (Phase 1-4) support path visualization and traversal
- Multiple path types support different learning styles
- Integration with Knowledge domain enables structured learning progression
