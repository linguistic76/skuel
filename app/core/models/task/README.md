# Task Domain Model

The Task domain represents actionable work items in SKUEL - things that need to be done.

## Overview

Tasks are the core execution unit for:
- Getting things done (GTD-style workflow)
- Applying knowledge in practice
- Fulfilling goals through concrete actions
- Reinforcing habits through consistent execution
- Tracking progress with status lifecycle

**Critical Differences**: Task does NOT have `user_uid` field, and supports full status lifecycle with prerequisites and dependencies.

## YAML Structure

### Required Fields

| Field | Type | Pattern | Description |
|-------|------|---------|-------------|
| `version` | String | `1.0` | YAML schema version |
| `type` | String | `Task` | Entity type identifier |
| `uid` | String | `task:name` | Unique identifier (e.g., `task:log-first-3-blocks`) |
| `title` | String | 1-200 chars | Display title |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `description` | String | `null` | Detailed description (multiline supported) |
| `duration_minutes` | Integer | `30` | Estimated time (5-480 minutes) |
| `priority` | Enum | `medium` | Task priority level |
| `status` | Enum | `draft` | Current task status |
| `due_date` | Date | `null` | When task should be completed |
| `scheduled_date` | Date | `null` | When task is scheduled |
| `project` | String | `null` | Associated project name |
| `tags` | List[str] | `[]` | Categorization tags |
| `parent_uid` | String | `null` | Parent task UID (for subtasks) |
| `recurrence_pattern` | Enum | `null` | Recurrence pattern if recurring |
| `recurrence_end_date` | Date | `null` | End date for recurrence |

### Learning Integration Fields (Optional)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `fulfills_goal_uid` | String | `null` | **Single** Goal UID this task fulfills ⚠️ |
| `reinforces_habit_uid` | String | `null` | **Single** Habit UID this task reinforces ⚠️ |
| `applies_knowledge_uids` | List[str] | `[]` | Knowledge being applied (multiple) |
| `aligned_principle_uids` | List[str] | `[]` | Aligned principles (multiple) |
| `prerequisite_knowledge_uids` | List[str] | `[]` | Required knowledge |
| `prerequisite_task_uids` | List[str] | `[]` | Required tasks |
| `goal_progress_contribution` | Float | `0.0` | Goal progress (0.0-1.0) |
| `knowledge_mastery_check` | Boolean | `false` | Is this a knowledge validation task? |
| `habit_streak_maintainer` | Boolean | `false` | Does this maintain habit streak? |

### Metadata Fields (Auto-Populated)

| Field | Type | Description |
|-------|------|-------------|
| `created_at` | DateTime | When task was created |
| `updated_at` | DateTime | When task was last modified |

⚠️ **IMPORTANT**: Task has BOTH `created_at` AND `updated_at` (different from Choice which only has `created_at`)!

## Enum Values

### status (ActivityStatus)
- `draft` - Planning stage, not yet ready (default)
- `ready` - Ready to start (actionable)
- `in_progress` - Currently working on
- `blocked` - Waiting on something/someone
- `completed` - Finished
- `cancelled` - No longer needed
- `scheduled` - Scheduled for specific time

### priority (Priority - from shared_enums)
- `low` - Nice to have
- `medium` - Should do (default)
- `high` - Important
- `critical` - Urgent and important

### recurrence_pattern (RecurrencePattern - from shared_enums)
- `daily` - Every day
- `weekly` - Every week
- `monthly` - Every month
- `custom` - Custom RRULE pattern

## Example YAML

```yaml
version: 1.0
type: Task
uid: task:log-first-3-blocks
title: Log your first three 25-minute study blocks

description: |
  Complete three focused study sessions using the Pomodoro technique.

  Steps:
  1. Choose a topic from your study plan
  2. Set a timer for 25 minutes
  3. Focus entirely on the topic (no distractions)
  4. Log the session when timer ends
  5. Take a 5-minute break
  6. Repeat two more times

duration_minutes: 75                   # 3x 25min sessions

priority: high                         # Important for building momentum
status: ready                          # Ready to start

# Learning Integration
applies_knowledge_uids:
  - ku:spaced-repetition-basics
  - ku:distraction-handling

fulfills_goal_uid: goal:study-skills-foundation
reinforces_habit_uid: habit:daily-review

# Organization
tags:
  - logging
  - beginner
  - habit-building

due_date: 2025-10-15
```

## Common Mistakes

### ❌ CRITICAL: Using 'name' instead of 'title'
```yaml
type: Task
uid: task:example
name: My Task                        # FAILS - Task uses 'title' not 'name'!
```

### ✅ Correct: Use 'title'
```yaml
type: Task
uid: task:example
title: My Task                       # ✅ Correct field name
```

---

### ❌ Wrong: Setting user_uid
```yaml
type: Task
uid: task:example
title: My Task
user_uid: user:mike                 # FAILS - Task has NO user_uid field!
```

### ✅ Correct: Omit user_uid
```yaml
type: Task
uid: task:example
title: My Task
# No user_uid field - Task doesn't have this
```

---

### ❌ Wrong: Multiple goals/habits as lists
```yaml
fulfills_goal_uid:                   # FAILS - this is a SINGLE UID, not a list!
  - goal:goal-1
  - goal:goal-2

reinforces_habit_uid:                # FAILS - this is a SINGLE UID, not a list!
  - habit:habit-1
  - habit:habit-2
```

### ✅ Correct: Single goal/habit UIDs
```yaml
fulfills_goal_uid: goal:goal-1       # ✅ Single UID string
reinforces_habit_uid: habit:habit-1  # ✅ Single UID string

# For multiple knowledge connections, use applies_knowledge_uids:
applies_knowledge_uids:              # ✅ This CAN be a list
  - ku:knowledge-1
  - ku:knowledge-2
```

---

### ❌ Wrong: Invalid status value
```yaml
status: todo                         # FAILS - 'todo' not valid, use 'ready'
status: done                         # FAILS - use 'completed'
status: working                      # FAILS - use 'in_progress'
```

### ✅ Correct: Use valid status values
```yaml
status: ready                        # ✅ Valid - ready to start
status: in_progress                  # ✅ Valid - currently working
status: completed                    # ✅ Valid - finished
```

---

### ❌ Wrong: Duration out of range
```yaml
duration_minutes: 3                  # FAILS - minimum is 5 minutes
duration_minutes: 500                # FAILS - maximum is 480 minutes (8 hours)
```

### ✅ Correct: Duration within valid range
```yaml
duration_minutes: 30                 # ✅ Valid - 5 to 480 minutes
duration_minutes: 120                # ✅ Valid - 2 hours
```

---

### ❌ Wrong: Date in the past
```yaml
due_date: 2024-01-01                 # FAILS - date cannot be in the past
```

### ✅ Correct: Future or current date
```yaml
due_date: 2025-10-15                 # ✅ Valid future date
due_date: null                       # ✅ Valid - no due date
```

## Field Differences from Other Models

| Feature | Task | Event | Habit | Choice | Goal |
|---------|------|-------|-------|--------|------|
| **Display Name** | `title` | `title` | `name` ⚠️ | `title` | `title` |
| **User Ownership** | NO `user_uid` | NO `user_uid` | NO `user_uid` | YES `user_uid` ⚠️ | NO `user_uid` |
| **Timestamps** | `created_at`, `updated_at` | `created_at`, `updated_at` | `created_at`, `updated_at` | `created_at` only ⚠️ | `created_at`, `updated_at` |
| **Status** | Full lifecycle | Event-specific | Habit-specific | Choice-specific | Goal-specific |
| **Goal Link** | **Single** `fulfills_goal_uid` | No goal link | No goal link | No goal link | N/A (is goal) |
| **Habit Link** | **Single** `reinforces_habit_uid` | No habit link | N/A (is habit) | No habit link | No habit link |

## Status Lifecycle

Tasks follow this typical lifecycle:

```
draft → ready → in_progress → completed
                       ↓
                    blocked → in_progress
                       ↓
                   cancelled
```

- **draft**: Planning, not yet ready to start
- **ready**: Actionable, can be started anytime
- **in_progress**: Currently working on
- **blocked**: Waiting on prerequisite or dependency
- **completed**: Successfully finished
- **cancelled**: No longer needed or abandoned

## Business Logic Methods

The Task domain model (Tier 3) includes extensive business logic:

### Status Checks
- `is_completed()` - Check if task is completed
- `is_cancelled()` - Check if task is cancelled
- `is_blocked()` - Check if task is blocked
- `is_in_progress()` - Check if task is in progress
- `is_scheduled()` - Check if task is scheduled
- `is_draft()` - Check if task is in draft status
- `is_active()` - Check if task is active (not completed/cancelled)

### Time & Scheduling
- `is_overdue()` - Check if past due date
- `is_due_today()` - Check if due today
- `is_due_this_week()` - Check if due this week
- `is_scheduled_for_today()` - Check if scheduled for today
- `days_until_due()` - Days until due (None if no due date)
- `progress_percentage()` - Progress as percentage (0-100)

### Hierarchy & Recurrence
- `is_recurring()` - Check if task recurs
- `is_parent()` - Check if has subtasks
- `is_subtask()` - Check if is a subtask
- `next_recurrence_date()` - Next occurrence date

### Learning Integration
- `is_learning_task()` - Check if connected to knowledge
- `is_habit_task()` - Check if reinforces habit
- `is_milestone_task()` - Check if fulfills goal
- `has_prerequisites()` - Check if has prerequisites
- `learning_alignment_score()` - Learning alignment (0-1)
- `impact_score()` - Overall impact score

### Knowledge Intelligence (Enhanced)
- `get_all_knowledge_connections()` - All knowledge connections (explicit + inferred)
- `get_knowledge_enhancement_summary()` - Comprehensive knowledge metrics
- `calculate_knowledge_complexity()` - Knowledge-based complexity score

### Graph Intelligence (Phase 1-4 Integration)
- `build_dependency_query(depth)` - APOC query for task dependencies
- `build_impact_analysis_query()` - APOC query for task impact
- `build_knowledge_requirements_query(depth)` - APOC query for knowledge needs
- `get_suggested_query_intent()` - Recommended QueryIntent for task analysis

## Model File Locations

```
/core/models/task/
├── task.py                      # Tier 3: Frozen domain model (Task)
├── task_dto.py                  # Tier 2: Mutable DTO for data transfer
├── task_request.py              # Tier 1: Pydantic validation models
└── task_converters.py           # Conversion between tiers
```

## Template Reference

Full YAML template with all fields and documentation:
`/home/mike/skuel0/yaml_templates/_schemas/task_template.yaml`

## Validation Rules

**From Pydantic Request Models** (`task_request.py`):

- `title`: 1-200 characters (required)
- `description`: No length limit, supports multiline
- `duration_minutes`: 5-480 minutes (default: 30)
- `due_date`: Cannot be in the past
- `scheduled_date`: Cannot be in the past
- `recurrence_end_date`: Must be after due_date
- `goal_progress_contribution`: 0.0-1.0 range
- `actual_minutes`: Must be >= 0 if provided

## Best Practices

1. **Use status lifecycle properly** - Move tasks through draft → ready → in_progress → completed
2. **Set realistic duration_minutes** - Helps with scheduling and time management
3. **Link to goals** - Use `fulfills_goal_uid` to show how tasks advance goals
4. **Apply knowledge** - Use `applies_knowledge_uids` to practice what you learn
5. **Track habit reinforcement** - Use `reinforces_habit_uid` for habit-building tasks
6. **Use prerequisites** - Define `prerequisite_task_uids` for proper task ordering
7. **Tag effectively** - Use tags for filtering and organization
8. **Set priorities** - Use priority levels to guide task selection
9. **Break down big tasks** - Use parent/subtask relationships for complex work
10. **Update status promptly** - Keep task status current for accurate progress tracking

## Learning Integration Pattern

Tasks are the execution layer for learning:

```yaml
# Knowledge → Task → Goal → Principle flow
applies_knowledge_uids:              # What I'm learning
  - ku:spaced-repetition-basics

fulfills_goal_uid: goal:master-study-skills  # What I'm achieving

aligned_principle_uids:              # Why I'm doing it
  - pr:small-wins

knowledge_mastery_check: true        # This task validates learning
```

## Notes

- Task is the most feature-rich domain model
- Supports full GTD-style workflow with status lifecycle
- Integrates tightly with Knowledge, Goals, and Habits
- Graph intelligence methods (Phase 1-4) provide context and impact analysis
- Learning alignment score helps prioritize learning-focused tasks
- Impact score combines goal contribution, habit reinforcement, and knowledge application
