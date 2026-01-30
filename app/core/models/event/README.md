# Event Domain Model

The Event domain represents calendar events in SKUEL - time-based activities and occurrences.

## Overview

Events handle:
- Calendar scheduling and time management
- Recurring activities (daily study blocks, weekly reviews)
- Learning activities (study sessions, practice blocks)
- Habit reinforcement through scheduled time
- Task execution within time blocks
- Milestone celebrations

**Key Features**: Full datetime support, recurrence patterns (RRULE), online/in-person distinction, learning integration.

## YAML Structure

### Required Fields

| Field | Type | Pattern | Description |
|-------|------|---------|-------------|
| `version` | String | `1.0` | YAML schema version |
| `type` | String | `Event` | Entity type identifier |
| `uid` | String | `event:name` | Unique identifier (e.g., `event:study-block-25min`) |
| `title` | String | 1-200 chars | Display title |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `description` | String | `null` | Detailed description |
| `event_type` | String | `PERSONAL` | Type of event |
| `status` | Enum | `scheduled` | Current event status |
| `priority` | Enum | `medium` | Event priority |
| `visibility` | Enum | `private` | Who can see this event |
| `event_date` | Date | `null` | Date of event (YYYY-MM-DD) |
| `start_time` | Time | `null` | Start time (HH:MM:SS or HH:MM) |
| `end_time` | Time | `null` | End time (HH:MM:SS or HH:MM) |
| `location` | String | `null` | Physical location |
| `is_online` | Boolean | `false` | Is this virtual/online? |
| `meeting_url` | String | `null` | URL for online events |
| `tags` | List[str] | `[]` | Categorization tags |
| `attendee_emails` | List[str] | `[]` | Attendee email addresses |
| `max_attendees` | Integer | `null` | Maximum attendee count |
| `recurrence_pattern` | Enum | `null` | Recurrence pattern |
| `recurrence_end_date` | Date | `null` | End date for recurrence |
| `reminder_minutes` | Integer | `null` | Reminder time before event (0-10080) |

### Learning Integration Fields (Optional)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `reinforces_habit_uid` | String | `null` | **Single** Habit UID this event reinforces |
| `practices_knowledge_uids` | List[str] | `[]` | Knowledge practiced (multiple) |
| `milestone_celebration_for_goal` | String | `null` | Goal milestone being celebrated |
| `executes_tasks` | List[str] | `[]` | Tasks to execute during event |
| `habit_completion_quality` | Integer | `null` | Quality of habit completion (1-5) |
| `knowledge_retention_check` | Boolean | `false` | Is this a retention check? |

### Metadata Fields (Auto-Populated)

| Field | Type | Description |
|-------|------|-------------|
| `created_at` | DateTime | When event was created |
| `updated_at` | DateTime | When event was last modified |

✅ Event has BOTH `created_at` AND `updated_at` (like Task, Habit, Goal).

## Enum Values

### event_type (String - not a true enum)
- `PERSONAL` - Personal activities (default)
- `WORK` - Work-related events
- `MEETING` - Meetings and calls
- `LEARNING` - Study sessions, workshops
- `HEALTH` - Health and wellness activities
- `SOCIAL` - Social gatherings
- `DEADLINE` - Time-bound deadlines
- `REMINDER` - Reminder events
- `CONFERENCE` - Conferences and seminars
- `WORKSHOP` - Workshops and training

### status (ActivityStatus - from shared_enums)
- `scheduled` - Planned, not yet started (default)
- `in_progress` - Currently happening
- `completed` - Finished
- `cancelled` - No longer happening

### priority (Priority - from shared_enums)
- `low` - Nice to attend
- `medium` - Should attend (default)
- `high` - Important to attend
- `critical` - Must attend

### visibility (Visibility - from shared_enums)
- `private` - Only you can see (default)
- `public` - Anyone can see
- `shared` - Shared with specific people

### recurrence_pattern (RecurrencePattern - from shared_enums)
- `daily` - Every day
- `weekly` - Every week
- `monthly` - Every month
- `custom` - Custom RRULE pattern

## RRULE Format

For `recurrence_rule` field in more advanced use cases, SKUEL supports RRULE format:

```yaml
# Daily event
recurrence_rule: "FREQ=DAILY;INTERVAL=1"

# Weekly event (every Monday)
recurrence_rule: "FREQ=WEEKLY;BYDAY=MO"

# Monthly event (1st of each month)
recurrence_rule: "FREQ=MONTHLY;BYMONTHDAY=1"

# Workday event (Monday-Friday)
recurrence_rule: "FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR"
```

## Example YAML

```yaml
version: 1.0
type: Event
uid: event:study-block-25min
title: Study Block — 25 min

description: |
  A focused 25-minute study session using the Pomodoro technique.

  During this block:
  - Eliminate all distractions
  - Focus on one topic
  - Take notes as you learn
  - Log what you accomplished

event_type: LEARNING
status: scheduled
priority: high
visibility: private

# Timing (example - flexible timing in practice)
event_date: null                     # Flexible scheduling
start_time: null                     # User schedules when ready
end_time: null                       # 25 minutes from start

# For recurring events
recurrence_pattern: daily
recurrence_end_date: 2025-12-31

# Location
location: Quiet study space
is_online: false

# Learning Integration
reinforces_habit_uid: habit:daily-review
practices_knowledge_uids:
  - ku:spaced-repetition-basics
  - ku:note-taking-basics

knowledge_retention_check: true

# Organization
tags:
  - study
  - focus
  - pomodoro
```

## Common Mistakes

### ❌ CRITICAL: End time before start time
```yaml
start_time: "14:00:00"
end_time: "13:00:00"                 # FAILS - end before start!
```

### ✅ Correct: End time after start time
```yaml
start_time: "14:00:00"
end_time: "15:00:00"                 # ✅ Valid - 1 hour event
```

---

### ❌ Wrong: Missing meeting_url for online event
```yaml
is_online: true
meeting_url: null                    # FAILS - URL required for online events!
```

### ✅ Correct: Include meeting_url for online events
```yaml
is_online: true
meeting_url: https://zoom.us/j/123456789  # ✅ Valid
```

---

### ❌ Wrong: Recurrence end before event date
```yaml
event_date: 2025-10-15
recurrence_end_date: 2025-10-10      # FAILS - end before start!
```

### ✅ Correct: Recurrence end after event date
```yaml
event_date: 2025-10-15
recurrence_end_date: 2025-12-31      # ✅ Valid
```

---

### ❌ Wrong: Invalid reminder time
```yaml
reminder_minutes: 20000              # FAILS - max is 10080 (1 week)
reminder_minutes: -5                 # FAILS - must be >= 0
```

### ✅ Correct: Valid reminder time
```yaml
reminder_minutes: 15                 # ✅ Valid - 15 minutes before
reminder_minutes: 1440               # ✅ Valid - 1 day before
```

---

### ❌ Wrong: Invalid habit completion quality
```yaml
habit_completion_quality: 6          # FAILS - must be 1-5
habit_completion_quality: 0          # FAILS - must be 1-5
```

### ✅ Correct: Valid quality score
```yaml
habit_completion_quality: 4          # ✅ Valid - 4 out of 5
```

---

### ❌ Wrong: Using 'name' instead of 'title'
```yaml
type: Event
uid: event:example
name: My Event                       # FAILS - Event uses 'title' not 'name'!
```

### ✅ Correct: Use 'title'
```yaml
type: Event
uid: event:example
title: My Event                      # ✅ Correct field name
```

## Field Differences from Other Models

| Feature | Event | Task | Habit | Choice | Goal |
|---------|-------|------|-------|--------|------|
| **Display Name** | `title` | `title` | `name` ⚠️ | `title` | `title` |
| **User Ownership** | NO `user_uid` | NO `user_uid` | NO `user_uid` | YES `user_uid` ⚠️ | NO `user_uid` |
| **Timestamps** | Both | Both | Both | `created_at` only ⚠️ | Both |
| **Time Fields** | `event_date`, `start_time`, `end_time` | `due_date`, `scheduled_date` | No date fields | `decision_deadline` | `target_date`, `deadline` |
| **Recurrence** | Full RRULE support | RecurrencePattern enum | RecurrencePattern enum | No recurrence | No recurrence |
| **Location** | YES (`location`, `is_online`, `meeting_url`) | NO | NO | NO | NO |
| **Attendees** | YES (`attendee_emails`, `max_attendees`) | NO | NO | NO | NO |

## Business Logic Methods

The Event domain model (Tier 3) includes extensive business logic:

### Timing & Scheduling
- `duration_minutes()` - Calculate event duration
- `start_datetime()` - Combined start date + time
- `end_datetime()` - Combined end date + time
- `is_past()` - Check if event already happened
- `is_ongoing()` - Check if event is happening now
- `is_upcoming()` - Check if event is in the future
- `is_today()` - Check if event is today
- `is_tomorrow()` - Check if event is tomorrow
- `is_this_week()` - Check if event is this week
- `minutes_until_start()` - Minutes until event starts
- `hours_until_start()` - Hours until event starts

### Status Checks
- `is_scheduled()` - Check if event is scheduled
- `is_completed()` - Check if event is completed
- `is_cancelled()` - Check if event is cancelled

### Recurrence
- `is_recurring()` - Check if event recurs
- `next_recurrence_date()` - Next occurrence date

### Learning Integration
- `is_learning_event()` - Check if practices knowledge
- `is_habit_event()` - Check if reinforces habit
- `is_milestone_event()` - Check if celebrates goal
- `reinforcement_score()` - Learning reinforcement score

### Conflicts & Validation
- `conflicts_with_event(other)` - Check time overlap
- `can_accommodate_attendee()` - Check if space available
- `needs_reminder()` - Check if reminder should be sent

### Graph Intelligence (Phase 1-4 Integration)
- `build_scheduling_query(depth)` - APOC query for scheduling context
- `build_habit_reinforcement_query()` - APOC query for habit connections
- `build_knowledge_practice_query(depth)` - APOC query for knowledge practice
- `get_suggested_query_intent()` - Recommended QueryIntent for event analysis

## Model File Locations

```
/core/models/event/
├── event.py                     # Tier 3: Frozen domain model (Event)
├── event_dto.py                 # Tier 2: Mutable DTO for data transfer
├── event_request.py             # Tier 1: Pydantic validation models
└── event_converters.py          # Conversion between tiers
```

## Template Reference

Full YAML template with all fields and documentation:
`/home/mike/skuel/app/yaml_templates/_schemas/event_template.yaml`

## Validation Rules

**From Pydantic Request Models** (`event_request.py`):

- `title`: 1-200 characters (required)
- `description`: No length limit
- `end_time`: Must be after `start_time`
- `meeting_url`: Required if `is_online` is true
- `recurrence_end_date`: Must be after `event_date`
- `reminder_minutes`: 0-10080 (max 1 week)
- `max_attendees`: Must be >= 1 if provided
- `habit_completion_quality`: 1-5 range if provided

## Best Practices

1. **Set specific times for scheduled events** - Use `event_date`, `start_time`, `end_time` for calendar events
2. **Use null for flexible timing** - Set times to null for events without fixed schedules
3. **Link to habits for recurring activities** - Use `reinforces_habit_uid` for daily/weekly practices
4. **Practice knowledge during events** - Use `practices_knowledge_uids` for study sessions
5. **Celebrate milestones** - Use `milestone_celebration_for_goal` for achievements
6. **Execute tasks during events** - Use `executes_tasks` to link tasks to time blocks
7. **Track habit quality** - Use `habit_completion_quality` to monitor consistency
8. **Set reminders** - Use `reminder_minutes` for important events
9. **Specify location clearly** - Use `location` for physical spaces, `is_online`+`meeting_url` for virtual
10. **Use recurrence for regular activities** - Set `recurrence_pattern` for daily/weekly/monthly events

## Learning Integration Pattern

Events are the time-based execution layer:

```yaml
# Knowledge → Event → Habit → Goal flow
practices_knowledge_uids:            # What I'm learning
  - ku:spaced-repetition-basics

reinforces_habit_uid: habit:daily-review  # What habit I'm building

milestone_celebration_for_goal: goal:master-study-skills  # What I'm achieving

knowledge_retention_check: true      # This event validates learning
```

## Online vs In-Person Pattern

```yaml
# In-person event
location: Conference Room A
is_online: false
meeting_url: null                    # Not needed

# Online event
location: null                       # Optional description
is_online: true
meeting_url: https://zoom.us/j/123  # Required!

# Hybrid event
location: Conference Room A (or join online)
is_online: true
meeting_url: https://zoom.us/j/123
```

## Recurrence Patterns

```yaml
# Daily study block
recurrence_pattern: daily
recurrence_end_date: 2025-12-31

# Weekly review (every Monday)
recurrence_pattern: weekly
# Use recurrence_rule for specific day:
recurrence_rule: "FREQ=WEEKLY;BYDAY=MO"

# Monthly reflection
recurrence_pattern: monthly
recurrence_end_date: 2025-12-31
```

## Notes

- Event domain focuses on calendar scheduling and time management
- Full datetime support with timezone awareness (in implementation)
- Recurrence patterns support both simple (daily/weekly/monthly) and RRULE format
- Learning integration connects events to Knowledge, Habits, and Goals
- Quality tracking (`habit_completion_quality`) enables habit improvement
- Graph intelligence methods (Phase 1-4) provide scheduling and learning context
- Conflict detection helps prevent double-booking
- Reminder system ensures events aren't missed
- Visibility control allows private, shared, or public events
- Attendee management supports group events and capacity limits
