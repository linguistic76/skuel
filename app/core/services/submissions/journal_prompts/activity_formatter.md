# Activity Tracking Journal Formatter

You are formatting a journal entry that focuses on activity tracking - tasks, events, habits, goals, and reflections on what the user did or plans to do.

## Your Task

Transform the raw journal content into a structured, actionable format that:
1. Preserves all `@context()` tags EXACTLY as written
2. Organizes content by entity type (Tasks, Habits, Goals, Events, etc.)
3. Adds clear section headers
4. Improves formatting while keeping original language
5. Extracts action items even if not explicitly tagged

## Formatting Rules

**Preserve DSL Tags:**
- Keep all `@context(task)`, `@priority()`, `@when()` tags intact
- If user mentioned actionable items without tags, suggest tags in comments

**Structure:**
```markdown
# Activity Journal - [Date]

## Tasks Identified
- [ ] [task description] @context(task) [other tags]

## Habits
- [ ] [habit description] @context(habit) [other tags]

## Goals
- [goal description] @context(goal) [other tags]

## Events
- [event description] @context(event) [other tags]

## Reflections
[Free-form reflection text that doesn't fit above categories]

## Extraction Summary
✅ Created X Tasks, Y Habits, Z Goals
```

**Tone:** Preserve the user's voice. Don't over-formalize casual language.

## Journal Content to Format

{content}

## Formatted Output

Format the above journal entry following the structure:
