# Habit Domain Models

**Purpose**: Recurring behaviors to build or break, with progress tracking and learning integration.

---

## YAML Structure

### Required Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `version` | Float | YAML version | `1.0` |
| `type` | String | Entity type (must be exact) | `Habit` |
| `uid` | String | Unique identifier | `habit:daily-25min-focus` |
| `name` | String | Habit name ⚠️ Use `name` NOT `title`! | `"Daily 25-Minute Focus Block"` |

### Optional Fields

| Field | Type | Default | Valid Values | Description |
|-------|------|---------|--------------|-------------|
| `description` | String | `null` | Any string | Detailed description |
| `polarity` | Enum | `build` | `build`, `break` | Whether to establish or eliminate |
| `category` | Enum | `other` | See below | Type of habit |
| `difficulty` | Enum | `moderate` | See below | How challenging |
| `recurrence_pattern` | Enum | `daily` | `daily`, `weekly`, `monthly`, `custom` | How often it occurs |
| `target_days_per_week` | Integer | `7` | `1` to `7` | Days per week to perform |
| `preferred_time` | String | `null` | `morning`, `afternoon`, `evening`, `null` | When to do it |
| `duration_minutes` | Integer | `15` | `1` to `480` | Expected time per occurrence |
| `current_streak` | Integer | `0` | Auto-managed | Current consecutive completions |
| `best_streak` | Integer | `0` | Auto-managed | Longest streak |
| `cue` | String | `null` | Any string | Environmental/time trigger |
| `routine` | String | `null` | Any string | The habit action |
| `reward` | String | `null` | Any string | Benefit from completion |
| `tags` | List[String] | `[]` | Any strings | Tags for organization |

### Learning Integration Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `linked_knowledge_uids` | List[String] | `[]` | KnowledgeUnit UIDs this habit reinforces |
| `linked_goal_uids` | List[String] | `[]` | Goal UIDs this habit supports |
| `linked_principle_uids` | List[String] | `[]` | Principle UIDs this habit embodies |
| `prerequisite_habit_uids` | List[String] | `[]` | Habit UIDs to establish first |

### Auto-Populated Fields (DO NOT SET)

- `created_at`: Timestamp when created
- `updated_at`: Timestamp when last modified
- `total_completions`: Total times completed
- `total_attempts`: Total times attempted
- `success_rate`: Completion rate (auto-calculated)
- `last_completed`: Last completion timestamp

---

## Enum Values

### Category
- `health` - Physical/mental health habits
- `learning` - Study and education habits
- `productivity` - Work efficiency habits
- `social` - Relationship and communication habits
- `creative` - Creative practice habits
- `mindfulness` - Meditation and awareness habits
- `financial` - Money management habits
- `other` - Miscellaneous habits

### Difficulty
- `trivial` - Takes almost no effort
- `easy` - Simple to maintain
- `moderate` - Requires some discipline
- `challenging` - Requires significant effort
- `heroic` - Extremely demanding

### Polarity
- `build` - Positive habit to establish
- `break` - Negative habit to eliminate

---

## Example YAML

```yaml
version: 1.0
type: Habit
uid: habit:daily-25min-focus
name: Daily 25-Minute Focus Block
description: One focused study session per day, 25 minutes, single topic
polarity: build
category: learning
difficulty: easy
recurrence_pattern: daily
target_days_per_week: 5
preferred_time: morning
duration_minutes: 25
current_streak: 0
best_streak: 0
cue: After breakfast, before checking phone
routine: Set timer for 25 minutes, study one topic, log completion
reward: Check off day, see streak grow
tags:
  - focus
  - study
  - pomodoro
```

---

## Common Mistakes

### ❌ CRITICAL: Wrong field name
```yaml
type: Habit
title: My Habit  # FAILS - Habit uses 'name' not 'title'!
```

### ✅ Correct: Use 'name'
```yaml
type: Habit
name: My Habit  # ✅ Correct field name
```

### ❌ Wrong: Old field names
```yaml
habit_type: daily    # FAILS - old field name
frequency: daily     # FAILS - old field name
```

### ✅ Correct: Current field names
```yaml
recurrence_pattern: daily       # ✅ Current field
target_days_per_week: 7        # ✅ Related field
```

### ❌ Wrong: Including user_uid
```yaml
user_uid: system  # FAILS - Habit model doesn't have this field
```

### ✅ Correct: No user_uid
```yaml
# Just omit user_uid - Habit model doesn't use it
name: My Habit
description: ...
```

---

## Model Files

- **Pure Domain Model**: `habit.py` - Tier 3 (frozen dataclass)
- **DTO**: `habit_dto.py` - Tier 2 (mutable transfer)
- **Request Models**: `habit_request.py` - Tier 1 (Pydantic validation)

---

## Template Reference

Full template with all fields documented:
- [/yaml_templates/_schemas/habit_template.yaml](../../../yaml_templates/_schemas/habit_template.yaml)

---

## Cue-Routine-Reward Pattern

The classic habit loop from behavioral science:

### Cue (Trigger)
What reminds you to do the habit?
```yaml
cue: After breakfast, before checking phone
```

### Routine (Behavior)
What you actually do:
```yaml
routine: Set timer for 25 minutes, study one topic, log completion
```

### Reward (Benefit)
What you get from doing it:
```yaml
reward: Check off day, see streak grow
```

---

## Field Differences from Other Models

⚠️ **Habit is DIFFERENT** from Task/Event/Goal/Choice:

| Feature | Habit | Task/Event/Goal | Choice |
|---------|-------|-----------------|--------|
| **Display Name Field** | `name` | `title` | `title` |
| **User Ownership** | NO `user_uid` | NO `user_uid` | YES `user_uid` |
| **Recurrence** | `recurrence_pattern` | N/A | N/A |
| **Old Fields** | NO `habit_type`/`frequency` | N/A | N/A |

---

## Progress Tracking

These fields are AUTO-MANAGED by the system:

- `current_streak` - Updated when habit is completed
- `best_streak` - Updated when current exceeds best
- `total_completions` - Incremented on each completion
- `total_attempts` - Incremented on each attempt
- `success_rate` - Calculated: completions / attempts
- `last_completed` - Timestamp of last completion

**Do NOT set these manually in YAML** - they're managed by the completion tracking system.

---

## Best Practices

### 1. Start Small (Use Difficulty Levels)
```yaml
# ✅ Better for beginners
difficulty: easy
duration_minutes: 15
target_days_per_week: 3
```

### 2. Clear Cues
```yaml
# ✅ Specific trigger
cue: After breakfast, before checking phone

# ❌ Vague trigger
cue: In the morning
```

### 3. Concrete Routines
```yaml
# ✅ Specific actions
routine: Set timer for 25 minutes, study one topic, log completion

# ❌ Vague actions
routine: Study
```

### 4. Immediate Rewards
```yaml
# ✅ Immediate satisfaction
reward: Check off day, see streak grow

# ❌ Delayed/vague reward
reward: Feel accomplished eventually
```

---

## Habit Progression

Use `prerequisite_habit_uids` to build progressions:

```yaml
# Simple habit first
uid: habit:daily-5min-reading
name: Daily 5-Minute Reading
difficulty: easy
duration_minutes: 5

---

# Build on the simple habit
uid: habit:daily-30min-deep-reading
name: Daily 30-Minute Deep Reading
difficulty: moderate
duration_minutes: 30
prerequisite_habit_uids:
  - habit:daily-5min-reading  # Master simple before complex
```

---

## Notes

1. **Use `name` not `title`**: This is the most common mistake with Habit YAML
2. **No `user_uid` field**: Unlike Choice, Habit doesn't track user ownership
3. **Progress fields are auto-managed**: Don't set streak/completion fields manually
4. **recurrence_pattern replaces old fields**: Use this instead of habit_type/frequency
5. **Cue-routine-reward is powerful**: Use all three for stronger habit formation
6. **Link to learning ecosystem**: Connect habits to knowledge, goals, principles
