# Goal Domain Model

The Goal domain represents desired outcomes and aspirations in SKUEL - the "why" behind learning and habits.

## Overview

Goals provide:
- Direction and motivation for learning
- Connection between knowledge and desired outcomes
- Progress tracking with multiple measurement types
- Hierarchical structure (parent/sub-goals)
- Integration with habits and principles
- Milestone-based achievement tracking

**Key Features**: Multiple measurement types, goal hierarchies, learning integration, vision alignment.

## YAML Structure

### Required Fields

| Field | Type | Pattern | Description |
|-------|------|---------|-------------|
| `version` | String | `1.0` | YAML schema version |
| `type` | String | `Goal` | Entity type identifier |
| `uid` | String | `goal:name` | Unique identifier (e.g., `goal:study-sprint-beginner`) |
| `title` | String | 1-200 chars | Display title |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `description` | String | `null` | Detailed description |
| `goal_type` | Enum | `outcome` | Type of goal |
| `domain` | Enum | `personal` | Knowledge domain |
| `timeframe` | Enum | `quarterly` | Time horizon |
| `measurement_type` | Enum | `percentage` | How progress is measured |
| `target_value` | Float | `null` | Target metric value |
| `current_value` | Float | `0.0` | Current progress value |
| `unit_of_measurement` | String | `null` | Unit for the metric (e.g., "study blocks") |
| `start_date` | Date | `null` | When work begins (YYYY-MM-DD) |
| `target_date` | Date | `null` | When goal should be achieved |
| `status` | Enum | `planned` | Current goal status |
| `priority` | Enum | `medium` | Goal priority |
| `tags` | List[str] | `[]` | Categorization tags |
| `vision_statement` | String | `null` | Long-term vision this supports |
| `parent_goal_uid` | String | `null` | Parent goal UID |
| `sub_goal_uids` | List[str] | `[]` | Child goal UIDs |
| `progress_percentage` | Float | `0.0` | Overall progress (0-100) |
| `why_important` | String | `null` | Personal importance statement |
| `success_criteria` | String | `null` | Clear definition of success |
| `potential_obstacles` | List[str] | `[]` | Anticipated challenges |
| `strategies` | List[str] | `[]` | Strategies to achieve |

### Learning Integration Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `required_knowledge_uids` | List[str] | `[]` | Knowledge needed to achieve |
| `supporting_habit_uids` | List[str] | `[]` | Habits that support this goal |
| `guiding_principle_uids` | List[str] | `[]` | Principles that guide pursuit |

### Metadata Fields (Auto-Populated)

| Field | Type | Description |
|-------|------|-------------|
| `created_at` | DateTime | When goal was created |
| `updated_at` | DateTime | When goal was last modified |
| `achieved_date` | DateTime | When goal was achieved (set when status becomes 'achieved') |
| `last_progress_update` | DateTime | Last time progress was updated |

✅ Goal has BOTH `created_at` AND `updated_at` (like Task, Event, Habit).

## Enum Values

### goal_type
⚠️ **IMPORTANT**: Use `process` NOT `habit` (common mistake from Study Skills 101 examples!)

- `outcome` - Result-focused (achieve X) - default
- `process` - Activity-focused (do Y consistently) ⚠️ **Use this, not "habit"!**
- `learning` - Knowledge/skill acquisition
- `project` - Complete a specific project
- `milestone` - Reach a specific milestone
- `mastery` - Master a domain/skill

### domain (Domain - from shared_enums)
- `personal` - Personal development (default)
- `professional` - Career/work
- `technical` - Technical skills
- `health` - Health and wellness
- `financial` - Financial goals
- `social` - Relationships and community
- `knowledge` - Learning and education

### timeframe
- `daily` - Micro-goals (today)
- `weekly` - Short-term (this week)
- `monthly` - Near-term (this month)
- `quarterly` - Medium-term (3 months) - default
- `yearly` - Long-term (this year)
- `multi_year` - Strategic (multiple years)

### measurement_type
- `binary` - Done/Not Done
- `percentage` - 0-100% complete (default)
- `numeric` - Specific number (e.g., 5 sessions)
- `milestone` - Checkpoints achieved
- `habit_based` - Based on habit consistency
- `knowledge_based` - Based on knowledge mastery

### status
- `planned` - Not yet started (default)
- `active` - Currently pursuing
- `paused` - Temporarily on hold
- `achieved` - Successfully completed
- `revised` - Modified/updated
- `abandoned` - No longer pursuing

### priority (Priority - from shared_enums)
- `low` - Nice to achieve
- `medium` - Should achieve (default)
- `high` - Important to achieve
- `critical` - Must achieve

## Example YAML

```yaml
version: 1.0
type: Goal
uid: goal:study-sprint-beginner
title: Complete beginner study sprint

description: |
  Complete your first structured study sprint demonstrating consistent
  practice and basic knowledge retention.

  Success means:
  - Logging first three study blocks
  - Creating initial flashcards
  - Doing first review session
  - Completing entry survey

goal_type: process               # ✅ Use 'process' not 'habit'!
domain: personal
timeframe: weekly
priority: high

# Measurement
measurement_type: numeric
target_value: 3.0
current_value: 0.0
unit_of_measurement: study blocks

# Timeline
start_date: 2025-10-04
target_date: 2025-10-11

# Learning Integration
required_knowledge_uids:
  - ku:spaced-repetition-basics
  - ku:note-taking-basics
  - ku:distraction-handling

supporting_habit_uids:
  - habit:daily-review

guiding_principle_uids:
  - pr:small-wins

# Motivation
why_important: |
  Building foundational study habits will enable all future learning.
  This sprint proves I can stick with a structured approach.

success_criteria: |
  - Three 25-minute focused study blocks logged
  - Five flashcards created with good formatting
  - One review session completed
  - Entry survey submitted

potential_obstacles:
  - Finding consistent study time
  - Dealing with distractions
  - Maintaining motivation

strategies:
  - Start with just 25 minutes
  - Use Pomodoro technique
  - Track progress visibly
  - Celebrate small wins

status: active
tags:
  - beginner
  - sprint
  - foundation
```

## Common Mistakes

### ❌ CRITICAL: Using 'habit' instead of 'process'
```yaml
goal_type: habit                 # FAILS - 'habit' is NOT a valid goal_type!
```

### ✅ Correct: Use 'process' for activity-focused goals
```yaml
goal_type: process               # ✅ Valid - for consistent activities
```

---

### ❌ Wrong: Using 'name' instead of 'title'
```yaml
type: Goal
uid: goal:example
name: My Goal                    # FAILS - Goal uses 'title' not 'name'!
```

### ✅ Correct: Use 'title'
```yaml
type: Goal
uid: goal:example
title: My Goal                   # ✅ Correct field name
```

---

### ❌ Wrong: Setting user_uid
```yaml
type: Goal
uid: goal:example
title: My Goal
user_uid: user:mike              # FAILS - Goal has NO user_uid field!
```

### ✅ Correct: Omit user_uid
```yaml
type: Goal
uid: goal:example
title: My Goal
# No user_uid field - Goal doesn't have this
```

---

### ❌ Wrong: Missing target_value for numeric measurement
```yaml
measurement_type: numeric
unit_of_measurement: sessions
# FAILS - numeric goals need target_value!
```

### ✅ Correct: Include target_value for numeric goals
```yaml
measurement_type: numeric
target_value: 5.0
unit_of_measurement: sessions    # ✅ Clear what we're measuring
```

---

### ❌ Wrong: Invalid timeframe value
```yaml
timeframe: short_term            # FAILS - not a valid enum value
timeframe: 2_weeks               # FAILS - use 'weekly' or 'monthly'
```

### ✅ Correct: Use valid timeframe values
```yaml
timeframe: weekly                # ✅ Valid - 1 week horizon
timeframe: monthly               # ✅ Valid - 1 month horizon
```

---

### ❌ Wrong: Progress percentage out of range
```yaml
progress_percentage: 150.0       # FAILS - must be 0-100
progress_percentage: -5.0        # FAILS - must be 0-100
```

### ✅ Correct: Progress in valid range
```yaml
progress_percentage: 75.0        # ✅ Valid - 75% complete
progress_percentage: 0.0         # ✅ Valid - just starting
```

## Field Differences from Other Models

| Feature | Goal | Task | Habit | Event | Choice |
|---------|------|------|-------|-------|--------|
| **Display Name** | `title` | `title` | `name` ⚠️ | `title` | `title` |
| **User Ownership** | NO `user_uid` | NO `user_uid` | NO `user_uid` | NO `user_uid` | YES `user_uid` ⚠️ |
| **Timestamps** | Both + `achieved_date` | Both | Both | Both | `created_at` only ⚠️ |
| **Measurement** | Multiple types (binary, numeric, milestone, etc.) | Duration-based | Streak/completion | Time-based | Decision-based |
| **Hierarchy** | YES (`parent_goal_uid`, `sub_goal_uids`) | YES (parent/subtask) | NO | NO | NO |
| **Learning Links** | Required knowledge, supporting habits, principles | Applies knowledge, fulfills goal | No knowledge link | Practices knowledge | No learning link |
| **Milestones** | YES (embedded Milestone objects) | NO | NO | NO | NO |

## Measurement Type Patterns

### Binary (Done/Not Done)
```yaml
measurement_type: binary
# No target_value needed - just done or not
progress_percentage: 0.0         # 0% = not done, 100% = done
```

### Percentage (0-100%)
```yaml
measurement_type: percentage
target_value: 100.0
current_value: 35.0
progress_percentage: 35.0        # Automatically calculated
```

### Numeric (Count-based)
```yaml
measurement_type: numeric
target_value: 10.0
current_value: 3.0
unit_of_measurement: study blocks
progress_percentage: 30.0        # 3 out of 10 = 30%
```

### Habit-Based (Consistency)
```yaml
measurement_type: habit_based
supporting_habit_uids:
  - habit:daily-review
# Progress based on habit streak and completion rate
```

### Knowledge-Based (Mastery)
```yaml
measurement_type: knowledge_based
required_knowledge_uids:
  - ku:algebra-basics
  - ku:calculus-intro
# Progress based on knowledge mastery levels
```

## Goal Hierarchy Pattern

```yaml
# Parent goal
uid: goal:master-study-skills
title: Master Study Skills
goal_type: mastery
timeframe: yearly

sub_goal_uids:
  - goal:study-sprint-beginner
  - goal:advanced-review-techniques
  - goal:speed-reading-foundations

---

# Child goal
uid: goal:study-sprint-beginner
title: Complete beginner study sprint
goal_type: process
timeframe: weekly

parent_goal_uid: goal:master-study-skills  # Links back to parent
```

## Business Logic Methods

The Goal domain model (Tier 3) includes extensive business logic:

### Status Checks
- `is_active()` - Check if goal is actively being pursued
- `is_achieved()` - Check if goal is achieved
- `is_overdue()` - Check if past target date without achievement
- `is_on_track()` - Check if progress is on pace
- `is_stalled()` - Check if no recent progress

### Progress Calculation
- `calculate_progress_percentage()` - Calculate progress based on measurement type
- `calculate_velocity()` - Progress rate over time
- `estimate_completion_date()` - Predict when goal will be achieved
- `days_remaining()` - Days until target date
- `days_since_start()` - Days since start date

### Hierarchy & Structure
- `is_parent_goal()` - Check if has sub-goals
- `is_sub_goal()` - Check if is a child goal
- `has_milestones()` - Check if has milestones defined
- `get_next_milestone()` - Get upcoming milestone

### Learning Integration
- `requires_knowledge()` - Check if has knowledge prerequisites
- `is_learning_goal()` - Check if this is a learning-focused goal
- `knowledge_readiness_score()` - Readiness based on knowledge mastery
- `get_all_learning_connections()` - All knowledge + habit + principle connections

### Milestone Tracking
- `get_completed_milestones()` - List of achieved milestones
- `get_pending_milestones()` - List of upcoming milestones
- `milestone_completion_rate()` - Percentage of milestones achieved

### Graph Intelligence (Phase 1-4 Integration)
- `build_supporting_activities_query(depth)` - APOC query for tasks/habits/events
- `build_knowledge_requirements_query(depth)` - APOC query for knowledge needs
- `build_goal_hierarchy_query(depth)` - APOC query for parent/child goals
- `get_suggested_query_intent()` - Recommended QueryIntent for goal analysis

## Model File Locations

```
/core/models/goal/
├── goal.py                      # Tier 3: Frozen domain model (Goal, Milestone)
├── goal_dto.py                  # Tier 2: Mutable DTO for data transfer
├── goal_request.py              # Tier 1: Pydantic validation models
└── goal_converters.py           # Conversion between tiers
```

## Template Reference

Full YAML template with all fields and documentation:
`/home/mike/skuel/app/yaml_templates/_schemas/goal_template.yaml`

## Validation Rules

**From Pydantic Request Models** (`goal_request.py`):

- `title`: 1-200 characters (required)
- `description`: No length limit
- `target_value`: Must be > 0 if provided
- `current_value`: Must be >= 0
- `progress_percentage`: 0.0-100.0 range
- `target_date`: Cannot be before start_date
- `measurement_type`: Required for numeric goals
- `unit_of_measurement`: Recommended for numeric goals

## Best Practices

1. **Use 'process' not 'habit' for goal_type** - Common mistake from examples
2. **Set clear success criteria** - Define what "done" looks like
3. **Choose appropriate measurement_type** - Numeric for countable, percentage for completion
4. **Link to required knowledge** - Use `required_knowledge_uids` to show what you need to learn
5. **Connect supporting habits** - Use `supporting_habit_uids` for daily practices
6. **Ground in principles** - Use `guiding_principle_uids` for value alignment
7. **Break down large goals** - Use parent/sub-goal hierarchy for complex goals
8. **Add meaningful milestones** - Break journey into checkpoints
9. **Explain 'why'** - Use `why_important` for motivation
10. **Anticipate obstacles** - Use `potential_obstacles` to plan ahead
11. **Define strategies** - Use `strategies` to clarify approach
12. **Set realistic timeframes** - Match timeframe to goal scope
13. **Update progress regularly** - Keep `current_value` and `progress_percentage` current
14. **Celebrate achievements** - Mark `status: achieved` and set `achieved_date`

## Learning Integration Pattern

Goals connect the entire learning ecosystem:

```yaml
# Knowledge → Habits → Tasks → Goals → Principles flow
required_knowledge_uids:             # What I need to learn
  - ku:spaced-repetition-basics
  - ku:note-taking-basics

supporting_habit_uids:               # Daily practices that help
  - habit:daily-review
  - habit:morning-study

guiding_principle_uids:              # Why this matters
  - pr:small-wins
  - pr:consistency-over-intensity

# Tasks fulfill this goal (defined in Task domain)
# Events celebrate milestones for this goal (defined in Event domain)
```

## Milestone Pattern

```yaml
milestones:
  - uid: milestone:first-3-blocks
    title: Complete first three study blocks
    target_date: 2025-10-07
    target_value: 3.0
    required_knowledge_uids:
      - ku:spaced-repetition-basics

  - uid: milestone:first-5-cards
    title: Create first five flashcards
    target_date: 2025-10-09
    target_value: 5.0
    required_knowledge_uids:
      - ku:note-taking-basics

  - uid: milestone:first-review
    title: Complete first review session
    target_date: 2025-10-11
    required_knowledge_uids:
      - ku:spaced-repetition-basics
    unlocked_knowledge_uids:
      - ku:advanced-review-techniques
```

## Notes

- Goal domain provides the "why" for learning and habit formation
- Multiple measurement types support different goal types
- Milestone system breaks large goals into achievable checkpoints
- Goal hierarchies support breaking down complex aspirations
- Learning integration connects goals to knowledge, habits, and principles
- Progress tracking with multiple calculation methods
- Vision alignment helps maintain long-term motivation
- Graph intelligence methods (Phase 1-4) provide context and supporting activity analysis
- Status lifecycle supports entire goal journey from planning to achievement
- Obstacle and strategy tracking helps with goal achievement planning
