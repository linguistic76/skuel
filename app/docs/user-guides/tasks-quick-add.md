# Tasks Quick-Add Guide

*Last updated: 2025-12-08*

## Overview

The Tasks page (`/tasks`) provides a Todoist-inspired task manager with a quick-add form for zero-friction task capture.

## Quick-Add Form

The form has two rows of fields:

### Row 1: Essential Fields
| Field | Description | Required |
|-------|-------------|----------|
| **Title** | Task name (e.g., "Review pull request") | Yes |
| **Project** | Free-text field with autocomplete - type any project name (e.g., "Work", "Home", "Q4 Planning") | No |
| **Priority** | P1-P4 flag (P1=Critical/Red, P2=High/Orange, P3=Medium/Blue, P4=Low/Gray) | No (default: P3) |
| **Add Task** | Submit button | - |

**Note:** The Project field lets you type ANY project name. As you create tasks with projects, those project names will appear as autocomplete suggestions for future tasks.

### Row 2: Additional Metadata
| Field | Description | Required |
|-------|-------------|----------|
| **Assignee** | Person responsible (free text) | No |
| **Start** | Scheduled start date (date picker) | No |
| **Due** | Due date (date picker) - shows red when overdue | No |

### Row 3: Description
| Field | Description | Required |
|-------|-------------|----------|
| **Description** | Detailed task description (multiline textarea) | No |

The description appears as a subtitle below the task title in the list view (truncated to one line).

### Row 4: Subtasks & Recurrence
| Field | Description | Required |
|-------|-------------|----------|
| **Subtask of** | Select a parent task to make this a subtask (autocomplete from existing tasks) | No |
| **Repeat** | Recurrence pattern (Daily, Weekdays, Weekly, Monthly, etc.) | No |
| **Until** | End date for recurring tasks | No |

**Recurrence Options:**
- No repeat (default)
- Daily
- Weekdays (Mon-Fri)
- Weekends (Sat-Sun)
- Weekly
- Biweekly
- Monthly
- Quarterly
- Yearly

## Priority Levels (Todoist-Style)

| Priority | Label | Color | Use For |
|----------|-------|-------|---------|
| P1 | Critical | Red | Urgent, must do today |
| P2 | High | Orange | Important, this week |
| P3 | Medium | Blue | Normal priority (default) |
| P4 | Low | Gray | Someday/maybe |

## Example Workflow

1. **Quick capture**: Just type title + click "Add Task" (fastest)
2. **With context**: Title + select Project + set Priority + Add
3. **Full details**: Fill all fields including Assignee and dates

## Filtering Tasks

After adding tasks, use the filter bar to:
- **Project**: Show only tasks from a specific project
- **Assignee**: Filter by who's responsible
- **Due**: Today / Tomorrow / This Week / Overdue / All
- **Status**: Active / Completed / All
- **Sort**: Due Date / Priority / Recently Added

## Task Actions

- **Toggle complete**: Click the checkbox to mark done/undone
- **View details**: Click task title (opens detail view)

## Tips

1. **Projects as categories**: Use projects to group related tasks (e.g., "Q4 Planning", "Home Renovation")
2. **P1 sparingly**: Reserve P1 for true emergencies - too many P1s defeats the purpose
3. **Due dates matter**: Tasks with due dates appear in Calendar view and trigger overdue styling
4. **Start dates for scheduling**: Use start date for "don't start until" scenarios

## Alternative: Journal DSL Entry

You can also create tasks via the Activity DSL in journals:

```
@context(task) @priority(high) @when(2025-12-15)
Review quarterly report and prepare summary
```

This creates a task with:
- Context: task
- Priority: high (P2)
- Due date: December 15, 2025
- Title: "Review quarterly report and prepare summary"

See `/docs/dsl/DSL_USAGE_GUIDE.md` for full DSL syntax.
