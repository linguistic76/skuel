# LearningStep Domain Models

**Purpose**: Individual steps within a learning path, tracking progress and mastery.

---

## YAML Structure

### Required Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `version` | Float | YAML version | `1.0` |
| `type` | String | Entity type (must be exact) | `LearningStep` |
| `uid` | String | Unique identifier | `ls:study-skills-101:step-1` |
| `title` | String | Step title (1-200 chars) | `"One 25-Minute Block Today"` |
| `intent` | String | Learning objective (min 1 char) | `"Pick one topic, run a single 25-minute block..."` |
| `knowledge_uid` | String | Reference to KnowledgeUnit | `ku:note-taking-basics` |
| `sequence` | Integer | Order in path (0-based) | `1` |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mastery_threshold` | Float | `0.7` | Required mastery level (0.0-1.0) |
| `estimated_hours` | Float | `1.0` | Expected time to complete |
| `current_mastery` | Float | `0.0` | Current mastery level (auto-managed) |
| `completed` | Boolean | `false` | Whether completed (auto-managed) |
| `completed_at` | Datetime | `null` | Completion timestamp (auto-managed) |
| `notes` | String | `null` | Additional notes/guidance |
| `prerequisites` | List[String] | `[]` | Other LearningStep UIDs needed first |

### Auto-Populated Fields (DO NOT SET)

- `current_mastery`: Updated by learning system
- `completed`: Set when mastery_threshold reached
- `completed_at`: Timestamp when completed
- `created_at`: Timestamp when created
- `updated_at`: Timestamp when last modified

---

## UID Pattern

LearningStep UIDs follow the pattern: `ls:path-name:step-number`

**Examples**:
- `ls:study-skills-101:step-1`
- `ls:mindfulness-101:step-2`
- `ls:python-basics:step-3`

**Components**:
- `ls:` - Prefix indicating LearningStep
- `path-name` - The learning path this belongs to
- `step-number` - The step number (typically starts at 1)

---

## Example YAML

```yaml
version: 1.0
type: LearningStep
uid: ls:study-skills-101:step-1
title: One 25-Minute Block Today
intent: Pick one topic, run a single 25-minute block, and log it
knowledge_uid: ku:note-taking-basics
sequence: 1
mastery_threshold: 0.7
estimated_hours: 1.0
current_mastery: 0.0
completed: false
notes: |
  First step: Learn basic note-taking structure and run one 25-minute
  focused study block.

  Supporting knowledge: ku:distraction-handling helps create the
  environment for focus.
prerequisites: []
```

---

## Common Mistakes

### ❌ Wrong: Missing title or intent
```yaml
uid: ls:example:step-1
knowledge_uid: ku:example
sequence: 1
# FAILS - missing required 'title' and 'intent' fields
```

### ✅ Correct: Include title and intent
```yaml
uid: ls:example:step-1
title: Example Step Title       # Required
intent: What to accomplish      # Required
knowledge_uid: ku:example
sequence: 1
```

### ❌ Wrong: Invalid UID pattern
```yaml
uid: step-1  # FAILS - missing path context
```

### ✅ Correct: Full UID with path
```yaml
uid: ls:study-skills-101:step-1  # Includes path context
```

---

## Model Files

- **Pure Domain Model**: `ls.py` - Tier 3 (frozen dataclass)
- **DTO**: `ls_dto.py` - Tier 2 (mutable transfer)
- **Request Models**: `ls_request.py` - Tier 1 (Pydantic validation)

---

## Template Reference

Full template with all fields documented:
- [/yaml_templates/_schemas/learning_step_template.yaml](../../../yaml_templates/_schemas/learning_step_template.yaml)

---

## Prerequisites and Dependencies

LearningSteps can have prerequisites to enforce learning order:

```yaml
# Step 1 - Foundation
uid: ls:example:step-1
title: Learn Basics
sequence: 1
prerequisites: []  # No prerequisites

---

# Step 2 - Builds on Step 1
uid: ls:example:step-2
title: Apply Basics
sequence: 2
prerequisites:
  - ls:example:step-1  # Must complete step 1 first
```

---

## Mastery Tracking

### Mastery Threshold
The minimum mastery level (0.0-1.0) required to complete the step.

```yaml
mastery_threshold: 0.7  # Requires 70% mastery
```

### Current Mastery
Auto-updated by the learning system as the learner progresses.

```yaml
current_mastery: 0.0  # Starts at 0, updated by system
```

### Completion
Step is marked `completed: true` when `current_mastery >= mastery_threshold`.

---

## Integration with LearningPath

LearningSteps are typically referenced in LearningPath YAML:

```yaml
# In learning path YAML:
type: LearningPath
uid: lp:study-skills-101
steps:
  - ls:study-skills-101:step-1
  - ls:study-skills-101:step-2
```

Or embedded directly:

```yaml
type: LearningPath
uid: lp:study-skills-101
steps:
  - uid: ls:study-skills-101:step-1
    title: One 25-Minute Block
    intent: Complete one focused block
    knowledge_uid: ku:note-taking-basics
    sequence: 1
```

---

## Title vs Intent

### Title
Short, descriptive name for the step (like a headline).

```yaml
title: One 25-Minute Block Today
```

### Intent
The learning objective - what the learner should accomplish.

```yaml
intent: Pick one topic, run a single 25-minute block, and log it
```

**Both are required** by the Pydantic validation.

---

## Notes Field

Use `notes` for:
- Implementation guidance
- Tips for success
- Context about the step
- Links to resources

```yaml
notes: |
  This step builds on previous knowledge of time management.

  Tips:
  - Start with an easy topic
  - Use a timer app
  - Log your progress immediately after

  Common pitfalls:
  - Picking a topic that's too complex
  - Getting distracted mid-session
```

---

## Sequence Numbers

Sequence determines the order of steps in the learning path.

**Best Practice**: Start at 1 and increment:

```yaml
# Step 1
sequence: 1

# Step 2
sequence: 2

# Step 3
sequence: 3
```

Sequence is used for:
- Display order in UI
- Determining what's "next"
- Progress calculation

---

## Notes

1. **title and intent are BOTH required**: LearningStepCreateRequest validates both
2. **UID includes path name**: Pattern is `ls:path-name:step-number`
3. **Progress fields are auto-managed**: Don't set current_mastery, completed, completed_at
4. **Prerequisites create dependencies**: Learning system enforces order
5. **Mastery threshold is customizable**: Adjust based on step difficulty
6. **Steps reference knowledge**: Each step has exactly one knowledge_uid
7. **Notes support markdown**: Use multi-line YAML for formatted notes
