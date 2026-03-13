# FormGenerator User Guide

**Location:** `ui/patterns/form_generator.py`
**Import:** `from ui.patterns.form_generator import FormGenerator`

FormGenerator creates MonsterUI-styled forms automatically from Pydantic request models. Point it at a model, and it introspects fields, types, constraints, and enums to produce a complete, styled form.

---

## Quick Start

```python
from core.models.task.task_request import TaskCreateRequest
from ui.patterns.form_generator import FormGenerator

# Minimal usage — all fields from the model
form = FormGenerator.from_model(TaskCreateRequest, action="/api/tasks")
```

This generates a `<form>` with:
- One input per model field (type-appropriate: text, number, select, etc.)
- MonsterUI styling (`input-bordered`, `select-bordered`, etc.)
- Labels from `Field(description=...)` or auto-generated from field names
- Pydantic constraint attributes (`min`, `max`, `minlength`, `maxlength`)
- Alpine.js `formValidator` for client-side validation
- A submit button

---

## API Reference

### `FormGenerator.from_model()`

The primary method. All parameters except `model_class` are optional.

```python
FormGenerator.from_model(
    model_class,          # Required: Pydantic BaseModel class
    action="/api/tasks",  # Form action URL
    method="POST",        # HTTP method
    submit_label="Submit",# Submit button text
    include_fields=None,  # Only these fields (list[str])
    exclude_fields=None,  # Skip these fields (list[str])
    field_order=None,     # Custom ordering (list[str])
    sections=None,        # Grouped fields (dict[str, list[str]])
    custom_widgets=None,  # Override widgets (dict[str, FT])
    help_texts=None,      # Per-field help (dict[str, str])
    hidden_fields=None,   # Hidden inputs (dict[str, str])
    form_attrs=None,      # Extra form attributes (dict[str, Any])
    values=None,          # Pre-fill values (dict[str, Any])
    as_fragment=False,    # True = Div with fields only, no <form>
)
```

### `FormGenerator.from_instance()`

Convenience for edit forms. Extracts values from a dataclass or dict.

```python
FormGenerator.from_instance(
    TaskUpdateRequest,
    existing_task,           # Frozen dataclass or dict
    action=f"/tasks/edit-save?uid={task.uid}",
    submit_label="Save Changes",
    include_fields=["title", "description", "priority"],
)
```

---

## Field Selection

### include_fields / exclude_fields

```python
# Only show these 3 fields
FormGenerator.from_model(
    TaskCreateRequest,
    action="/api/tasks",
    include_fields=["title", "description", "priority"],
)

# Show all fields except internal ones
FormGenerator.from_model(
    TaskCreateRequest,
    action="/api/tasks",
    exclude_fields=["created_at", "updated_at", "uid"],
)
```

### field_order

Reorder fields without filtering:

```python
FormGenerator.from_model(
    TaskCreateRequest,
    action="/api/tasks",
    include_fields=["title", "priority", "due_date", "description"],
    field_order=["title", "priority", "due_date", "description"],
)
```

---

## Sections

Group fields into labeled sections with visual dividers. When `sections` is provided, `include_fields` and `field_order` are ignored.

```python
FormGenerator.from_model(
    GoalCreateRequest,
    action="/api/goals",
    sections={
        "Basic Information": ["title", "description", "why_important"],
        "Classification": ["goal_type", "domain", "timeframe", "priority"],
        "Timeline": ["start_date", "target_date"],
    },
)
```

Each section renders as:
- An H3 heading with the section title
- The fields in order
- A bottom border divider (except the last section)

`exclude_fields` still applies within sections. Fields listed in sections that don't exist on the model are silently skipped.

### Consistency across Activity Domains

All 6 Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles) should use the same section pattern for their create forms:

```python
sections={
    "Basic Information": ["title", "description", ...domain-specific...],
    "Classification": ["priority", "domain", ...domain-specific...],
    "Timeline": ["start_date", "target_date", ...],
}
```

---

## Help Text

Add per-field help text that appears below the input:

```python
FormGenerator.from_model(
    GoalCreateRequest,
    action="/api/goals",
    include_fields=["title", "why_important"],
    help_texts={
        "title": "A clear, actionable goal title",
        "why_important": "What makes this goal meaningful to you?",
    },
)
```

Help text renders as a `<p>` with `text-sm text-muted-foreground` styling, between the input and the error display.

---

## Pre-filling (Edit Forms)

### Via values dict

```python
FormGenerator.from_model(
    TaskUpdateRequest,
    action="/tasks/edit-save?uid=task_123",
    values={"title": "Fix bug", "priority": Priority.HIGH},
)
```

### Via from_instance

```python
task = await service.get("task_123")
FormGenerator.from_instance(
    TaskUpdateRequest,
    task,  # Frozen dataclass — fields matched by name
    action=f"/tasks/edit-save?uid={task.uid}",
    submit_label="Save Changes",
)
```

Value handling by type:
- **Text/Number:** sets `value="..."` attribute
- **Textarea:** sets content between tags
- **Select (enum):** sets `selected` on matching option
- **Checkbox:** sets `checked` attribute
- **Date:** calls `.isoformat()` on date/datetime objects

---

## Hidden Fields

Add hidden inputs for entity UIDs, versions, or other non-visible data:

```python
FormGenerator.from_model(
    TaskUpdateRequest,
    action="/tasks/edit-save",
    include_fields=["title", "description"],
    hidden_fields={"uid": "task_abc123", "version": "3"},
)
```

---

## Custom Widgets

Override the auto-generated widget for any field. Custom widgets are still wrapped with the field's label and error display:

```python
from ui.forms import Textarea, Input

FormGenerator.from_model(
    TaskCreateRequest,
    action="/api/tasks",
    include_fields=["title", "description"],
    custom_widgets={
        "description": Textarea(
            name="description",
            rows=8,
            placeholder="Detailed description...",
        ),
    },
)
```

---

## HTMX Integration

Use `form_attrs` to add HTMX attributes:

```python
FormGenerator.from_model(
    TaskCreateRequest,
    action="/api/tasks",
    form_attrs={
        "hx_post": "/api/tasks",
        "hx_target": "#task-list",
        "hx_swap": "beforeend",
    },
)
```

---

## Alpine.js

By default, every form gets `x-data="formValidator"` and `@submit="validate($event)"`. Override or disable via `form_attrs`:

```python
# Use a different Alpine component
FormGenerator.from_model(
    ...,
    form_attrs={"x-data": "exerciseForm"},
)

# Disable Alpine entirely
FormGenerator.from_model(
    ...,
    form_attrs={"x-data": None, "@submit": None},
)
```

---

## Fragment Mode: Embedding Forms in Articles

`as_fragment=True` returns a `<div>` with fields only — no `<form>` tag, no submit button. Use this to embed interactive form fields within article content.

### Use case: Interactive exercise within an article

```python
from fasthtml.common import Div, Form, H2, P
from ui.buttons import Button, ButtonT

# Article content with embedded exercise form
def render_article_with_exercise(article, exercise):
    exercise_fields = FormGenerator.from_model(
        ExerciseSubmissionRequest,
        include_fields=["response", "confidence_level"],
        values={"confidence_level": 0.5},
        help_texts={
            "response": "Write your answer to the exercise above",
            "confidence_level": "How confident are you? (0.0 = guessing, 1.0 = certain)",
        },
        as_fragment=True,
    )

    return Div(
        # Article content
        H2(article.title),
        Div(article.rendered_content, cls="prose"),

        # Embedded exercise form
        Form(
            H2("Exercise", cls="text-lg font-semibold"),
            P(exercise.instructions, cls="mb-4"),
            exercise_fields,  # Fragment slots in here
            Button("Submit Answer", type="submit", variant=ButtonT.primary),
            action=f"/api/submissions?exercise_uid={exercise.uid}",
            method="POST",
            hx_post=f"/api/submissions?exercise_uid={exercise.uid}",
            hx_target="#feedback-area",
        ),

        # Feedback area (populated by HTMX after submission)
        Div(id="feedback-area"),
    )
```

### Composing multiple fragments

```python
# Combine fields from different models into one form
basic_fields = FormGenerator.from_model(
    BasicInfoRequest,
    include_fields=["title", "description"],
    as_fragment=True,
)
settings_fields = FormGenerator.from_model(
    SettingsRequest,
    include_fields=["priority", "visibility"],
    as_fragment=True,
)

form = Form(
    basic_fields,
    settings_fields,
    Button("Create", type="submit", variant=ButtonT.primary),
    action="/api/create",
    method="POST",
)
```

---

## Type Mapping Reference

| Python Type | Widget | MonsterUI Class |
|-------------|--------|-----------------|
| `str` | `<input type="text">` | `input input-bordered` |
| `str` (name contains "description", "notes", "content", "body") | `<textarea>` | `textarea textarea-bordered` |
| `str` (max_length > 100) | `<textarea>` | `textarea textarea-bordered` |
| `int`, `float` | `<input type="number">` | `input input-bordered` |
| `bool` | `<input type="checkbox">` | `checkbox checkbox-primary` |
| `date` | `<input type="date">` | `input input-bordered` |
| `datetime` | `<input type="datetime-local">` | `input input-bordered` |
| `Enum` subclass | `<select>` | `select select-bordered` |
| `list[str]` | `<textarea>` | `textarea textarea-bordered` |

### Pydantic metadata overrides

```python
# Force a specific widget type
title: str = Field(..., json_schema_extra={"ui_widget": "textarea"})

# Custom label (overrides description)
title: str = Field(..., metadata=[{"ui_label": "Goal Title"}])

# Custom placeholder
title: str = Field(..., metadata=[{"ui_placeholder": "e.g., Learn Spanish"}])
```

---

## Complete Example: Activity Domain Create Form

```python
# adapters/inbound/tasks_ui.py
from core.models.task.task_request import TaskCreateRequest
from ui.patterns.form_generator import FormGenerator
from ui.cards import Card
from fasthtml.common import H2

class TaskUIComponents:
    @staticmethod
    def render_create_task_form():
        return Card(
            H2("Create New Task", cls="text-xl font-bold mb-4"),
            FormGenerator.from_model(
                TaskCreateRequest,
                action="/api/tasks",
                submit_label="Create Task",
                sections={
                    "Basic Information": ["title", "description"],
                    "Classification": ["priority", "domain", "tags"],
                    "Timeline": ["due_date", "estimated_minutes"],
                },
                help_texts={
                    "description": "What needs to be done?",
                    "tags": "Comma-separated tags for categorization",
                },
                form_attrs={
                    "hx_post": "/api/tasks",
                    "hx_target": "#task-list",
                    "hx_swap": "beforeend",
                },
            ),
            cls="p-6 max-w-2xl mx-auto",
        )
```
