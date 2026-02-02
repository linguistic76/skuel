---
name: skuel-form-patterns
description: Expert guide for building accessible, validated forms in SKUEL. Use when creating forms with validation, error handling, dynamic fields, or when the user mentions forms, input validation, error messages, or form submission.
allowed-tools: Read, Grep, Glob
related_skills:
- daisyui
- html-htmx
- ui-error-handling
- accessibility-guide
- tailwind-css
---

# SKUEL Form Patterns

## Core Philosophy

> "Validate early, fail fast, communicate clearly - forms should guide users to success, not punish mistakes."

SKUEL forms follow a **layered validation approach**:

1. **Client-side hints** (HTML5 attributes) - Immediate feedback
2. **Early validation** (pure Python functions) - Clear error messages before Pydantic
3. **Pydantic validation** (request models) - Type safety and schema enforcement
4. **Service-level checks** (business logic) - Domain rules and constraints

## When to Use This Skill

Use this skill when:

- ✅ Building **create/edit forms** for Activity Domains (Tasks, Goals, Habits, etc.)
- ✅ Implementing **form validation** with user-friendly error messages
- ✅ Creating **dynamic forms** with conditional fields or autocomplete
- ✅ Handling **date/time inputs** with proper formatting and constraints
- ✅ Building **multi-step forms** or modal forms with HTMX
- ✅ Implementing **quick-add patterns** (minimal fields, rapid entry)

## Core Concepts

### 1. Three-Tier Validation Strategy

SKUEL validates form data at **three distinct layers**:

| Layer | Technology | Purpose | Error Format |
|-------|------------|---------|--------------|
| **Client** | HTML5 attributes | Immediate feedback | Browser native |
| **Early Validation** | Pure Python functions | User-friendly messages | `Result[None]` with clear error |
| **Schema Validation** | Pydantic models | Type safety | 422 Unprocessable Entity |

**Decision Tree:**

```
Is this a simple field constraint (required, min/max length)?
├─ YES → HTML5 attributes (required, maxlength)
└─ NO → Does it need custom error message?
    ├─ YES → Early validation function
    └─ NO → Pydantic model validation
```

### 2. Early Validation Pattern

**Purpose:** Catch validation errors before Pydantic, return clear messages to UI

**Pattern:**

```python
def validate_task_form_data(form_data: dict[str, Any]) -> Result[None]:
    """
    Validate task form data early.

    Pure function: returns clear error messages for UI.
    """
    # Required fields
    title = form_data.get("title", "").strip()
    if not title:
        return Errors.validation("Task title is required")

    if len(title) > 200:
        return Errors.validation("Task title must be 200 characters or less")

    # Date validation
    scheduled_date_str = form_data.get("scheduled_date", "")
    due_date_str = form_data.get("due_date", "")

    if scheduled_date_str and due_date_str:
        try:
            scheduled = date.fromisoformat(scheduled_date_str)
            due = date.fromisoformat(due_date_str)
            if due < scheduled:
                return Errors.validation("Due date cannot be before scheduled date")
        except ValueError:
            return Errors.validation("Invalid date format")

    return Result.ok(None)
```

**Key Features:**
- **Pure function:** No I/O, testable without mocks
- **Clear messages:** User-facing error text
- **Early exit:** Return first error found
- **Result[None]:** Consistent error handling pattern

### 3. DaisyUI Form Component Pattern

SKUEL uses **DaisyUI form components** with semantic structure:

```
Form
├── FormControl (wraps label + input)
│   ├── Label
│   │   └── LabelText (visible label)
│   └── Input/Select/Textarea (form control)
└── Button (submit)
```

**Key Principle:** Always wrap inputs in `FormControl` + `Label` for accessibility.

### 4. HTMX Form Submission Pattern

Forms submit via **HTMX POST** to API endpoints, return fragments or full pages:

```python
Form(
    # ... form controls ...
    Button("Create Task", variant=ButtonT.primary, type="submit"),
    hx_post="/tasks/quick-add",
    hx_target="#task-list",  # Replace target with new content
    hx_swap="beforeend",     # Or: outerHTML, innerHTML
)
```

**Response types:**
- **Fragment:** Return new task card to append/replace
- **Full page:** Return updated dashboard (common for modals)
- **Error banner:** Return error component for HTMX swap

### 5. Modal Form Pattern

**Purpose:** Create/edit forms in modal dialogs (common in SKUEL)

**Pattern:**

```python
# Route returns modal HTML
@rt("/tasks/create-modal")
async def task_create_modal(request):
    """Return modal with create form."""
    return Modal(
        "task-create-modal",
        ModalBox(
            H3("Create Task"),
            Form(
                # ... form controls ...
                ModalAction(
                    Button("Cancel", variant=ButtonT.ghost, onclick="closeModal()"),
                    Button("Create", variant=ButtonT.primary, type="submit"),
                ),
                hx_post="/tasks/quick-add",
                hx_target="body",  # Replace entire page
            ),
        ),
    )

# Open modal via HTMX
Button(
    "New Task",
    variant=ButtonT.primary,
    hx_get="/tasks/create-modal",
    hx_target="#modal",  # Global modal container
)
```

## Implementation Patterns

### Pattern 1: Basic Form with Validation

**Purpose:** Create form with required fields, client-side hints, server validation

**Implementation:**

```python
from fasthtml.common import Form, Option
from core.ui.daisy_components import (
    Button, ButtonT,
    FormControl, Label, LabelText,
    Input, Select, Textarea,
)

def create_task_form(
    action_url: str = "/tasks/quick-add",
    initial_data: dict[str, Any] | None = None,
) -> Any:
    """Render task creation form."""
    initial_data = initial_data or {}

    return Form(
        # Title (required)
        FormControl(
            Label(LabelText("Title *")),
            Input(
                type="text",
                name="title",
                placeholder="Enter task title",
                value=initial_data.get("title", ""),
                required=True,
                maxlength=200,
                cls="input input-bordered w-full",
            ),
        ),
        # Description (optional)
        FormControl(
            Label(LabelText("Description")),
            Textarea(
                name="description",
                placeholder="Add details...",
                rows=4,
                cls="textarea textarea-bordered w-full",
            ),
        ),
        # Priority (select)
        FormControl(
            Label(LabelText("Priority")),
            Select(
                Option("Select priority...", value="", selected=True),
                Option("Critical", value="critical"),
                Option("High", value="high"),
                Option("Medium", value="medium"),
                Option("Low", value="low"),
                name="priority",
                cls="select select-bordered w-full",
            ),
        ),
        # Due date
        FormControl(
            Label(LabelText("Due Date")),
            Input(
                type="date",
                name="due_date",
                value=initial_data.get("due_date", ""),
                cls="input input-bordered w-full",
            ),
        ),
        # Submit button
        FormControl(
            Button(
                "Create Task",
                variant=ButtonT.primary,
                type="submit",
                cls="w-full mt-4",
            ),
        ),
        hx_post=action_url,
        hx_target="#task-list",
        hx_swap="beforeend",
        cls="space-y-4",
    )
```

**Key Details:**
- **Required fields:** Use `required=True` + asterisk in label
- **Maxlength:** Prevent client-side over-length input
- **Placeholder text:** Guide user on expected format
- **Full width:** `w-full` for consistent form layout
- **Spacing:** `space-y-4` for vertical rhythm

### Pattern 2: Early Validation in Route Handler

**Purpose:** Validate form data before processing, return error banner on failure

**Implementation:**

```python
from core.utils.result_simplified import Errors, Result

@rt("/tasks/quick-add", methods=["POST"])
async def create_task_from_form(request):
    """Create task with early validation."""
    user_uid = require_authenticated_user(request)

    # Parse form data
    form_data = await request.form()
    form_dict = dict(form_data)

    # VALIDATE EARLY
    validation_result = validate_task_form_data(form_dict)
    if validation_result.is_error:
        # Return error banner for HTMX swap
        return render_error_banner(f"Validation error: {validation_result.error}")

    # Continue with task creation
    result = await create_task_from_form(form_dict, user_uid)
    if result.is_error:
        return render_error_banner(f"Failed to create task: {result.error}")

    # Success - return new task card
    task = result.value
    return TaskCard(task)


def validate_task_form_data(form_data: dict[str, Any]) -> Result[None]:
    """Validate task form data (pure function)."""
    # Title validation
    title = form_data.get("title", "").strip()
    if not title:
        return Errors.validation("Task title is required")
    if len(title) > 200:
        return Errors.validation("Task title must be 200 characters or less")

    # Date validation
    scheduled_date_str = form_data.get("scheduled_date", "")
    due_date_str = form_data.get("due_date", "")

    if scheduled_date_str and due_date_str:
        try:
            scheduled = date.fromisoformat(scheduled_date_str)
            due = date.fromisoformat(due_date_str)
            if due < scheduled:
                return Errors.validation("Due date cannot be before scheduled date")
        except ValueError:
            return Errors.validation("Invalid date format")

    return Result.ok(None)


def render_error_banner(message: str) -> Any:
    """Render error banner for UI failures."""
    from fasthtml.common import Div, P
    return Div(
        Div(
            P("⚠️ Error", cls="font-bold text-error"),
            P(message, cls="text-sm"),
            cls="alert alert-error",
        ),
        cls="mb-4",
    )
```

**Flow:**
1. Parse form data to dict
2. Run early validation (pure function)
3. Check `is_error`, return banner if failed
4. Continue with service call if valid
5. Return error banner or success content

### Pattern 3: Date/Time Input with Constraints

**Purpose:** Date and time inputs with proper formatting and validation

**Implementation:**

```python
from datetime import date, time

# Date input (with min/max)
FormControl(
    Label(LabelText("Due Date")),
    Input(
        type="date",
        name="due_date",
        min=str(date.today()),  # Can't select past dates
        value=str(date.today() + timedelta(days=7)),  # Default: 7 days from now
        cls="input input-bordered w-full",
    ),
)

# Time input
FormControl(
    Label(LabelText("Start Time")),
    Input(
        type="time",
        name="start_time",
        value="09:00",  # Default: 9 AM
        step="900",  # 15-minute increments (900 seconds)
        cls="input input-bordered w-full",
    ),
)

# Datetime-local (combined)
FormControl(
    Label(LabelText("Event Start")),
    Input(
        type="datetime-local",
        name="event_start",
        value=datetime.now().strftime("%Y-%m-%dT%H:%M"),
        cls="input input-bordered w-full",
    ),
)
```

**Validation:**

```python
# In early validation function
def validate_event_form_data(form_data: dict[str, Any]) -> Result[None]:
    """Validate event form with datetime."""
    start_str = form_data.get("event_start", "")
    end_str = form_data.get("event_end", "")

    if not start_str:
        return Errors.validation("Event start time is required")

    try:
        start = datetime.fromisoformat(start_str)
        if end_str:
            end = datetime.fromisoformat(end_str)
            if end <= start:
                return Errors.validation("Event end must be after start")
    except ValueError:
        return Errors.validation("Invalid date/time format")

    return Result.ok(None)
```

### Pattern 4: Checkbox and Toggle Inputs

**Purpose:** Boolean fields with proper styling

**Implementation:**

```python
from core.ui.daisy_components import Checkbox, Toggle

# Checkbox (DaisyUI)
FormControl(
    Label(
        Checkbox(name="is_recurring", variant=ButtonT.primary),
        LabelText("Recurring task", cls="ml-2"),
        cls="flex items-center cursor-pointer",
    ),
)

# Toggle switch
FormControl(
    Label(
        LabelText("Enable notifications", cls="mr-2"),
        Toggle(name="notifications_enabled", variant=ButtonT.primary),
        cls="flex items-center justify-between cursor-pointer",
    ),
)

# Radio buttons (mutually exclusive)
from core.ui.daisy_components import Radio

FormControl(
    Label(LabelText("Task Type")),
    Div(
        Label(
            Radio(name="task_type", value="action", checked=True),
            Span("Action", cls="ml-2"),
            cls="flex items-center",
        ),
        Label(
            Radio(name="task_type", value="project"),
            Span("Project", cls="ml-2"),
            cls="flex items-center",
        ),
        cls="space-y-2",
    ),
)
```

**Parsing in route:**

```python
# Checkbox/toggle values
is_recurring = form_data.get("is_recurring") == "on"  # HTML checkbox sends "on" when checked
notifications = form_data.get("notifications_enabled") == "on"

# Radio button
task_type = form_data.get("task_type", "action")  # Default to "action" if not set
```

### Pattern 5: Autocomplete/Typeahead Pattern

**Purpose:** Dynamic suggestions for project names, tags, assignees

**Implementation:**

```python
# Route providing autocomplete data
@rt("/tasks/autocomplete/projects")
async def autocomplete_projects(request):
    """Return project suggestions as JSON."""
    query = request.query_params.get("q", "")
    user_uid = require_authenticated_user(request)

    # Get unique project names
    projects = await tasks_service.get_user_projects(user_uid)
    filtered = [p for p in projects if query.lower() in p.lower()]

    return JSONResponse(filtered[:10])  # Top 10 matches


# Form with autocomplete input (using datalist)
def create_task_form():
    return Form(
        # ... other fields ...

        # Project input with autocomplete
        FormControl(
            Label(LabelText("Project")),
            Input(
                type="text",
                name="project",
                list="project-suggestions",
                placeholder="Start typing project name...",
                cls="input input-bordered w-full",
                hx_get="/tasks/autocomplete/projects",
                hx_trigger="keyup changed delay:300ms",
                hx_target="#project-suggestions",
                hx_include="[name='project']",
            ),
            Datalist(
                id="project-suggestions",
                # Populated via HTMX
            ),
        ),
        # ... submit button ...
    )
```

**Alternative (Alpine.js dropdown):**

```python
# Using Alpine.js for richer autocomplete
Div(
    Label(LabelText("Assignee")),
    Div(
        Input(
            type="text",
            name="assignee",
            placeholder="Search users...",
            x_model="query",
            **{"@input": "search()"},
            cls="input input-bordered w-full",
        ),
        Div(
            Ul(
                Template(
                    Li(
                        Span(x_text="user.name"),
                        **{"@click": "select(user)"},
                        cls="p-2 hover:bg-base-200 cursor-pointer",
                    ),
                    x_for="user in filteredUsers",
                ),
                cls="menu bg-base-100 rounded-lg shadow-lg",
            ),
            x_show="query.length > 0 && filteredUsers.length > 0",
            cls="absolute top-full left-0 right-0 mt-1 z-10",
        ),
        x_data="autocompleteData()",
        cls="relative",
    ),
)
```

### Pattern 6: Quick-Add Pattern (Minimal Form)

**Purpose:** Rapid entry with minimal fields (title only), defaults for rest

**Implementation:**

```python
from core.infrastructure.routes import QuickAddConfig, QuickAddRouteFactory

# Quick-add configuration
QUICK_ADD_CONFIG = QuickAddConfig(
    title_field="title",
    title_placeholder="Add a new task...",
    button_text="Add Task",
    button_icon="✅",
    target_id="task-list",
    api_endpoint="/tasks/quick-add",
    additional_fields=[],  # None - just title
)

# Register quick-add route
QuickAddRouteFactory.create_quick_add_route(
    app=app,
    rt=rt,
    config=QUICK_ADD_CONFIG,
    route_path="/tasks/quick-add-form",
)

# Quick-add form (rendered at top of task list)
def render_quick_add_form():
    return Form(
        Div(
            Input(
                type="text",
                name="title",
                placeholder="Add a new task...",
                required=True,
                cls="input input-bordered flex-1",
            ),
            Button(
                "✅ Add",
                variant=ButtonT.primary,
                type="submit",
            ),
            cls="flex gap-2",
        ),
        hx_post="/tasks/quick-add",
        hx_target="#task-list",
        hx_swap="beforeend",
        hx_on="htmx:afterRequest: this.reset()",  # Clear form after submit
    )
```

**Key Features:**
- **Single field:** Title only for speed
- **Auto-clear:** Reset form after successful submit
- **Inline layout:** Horizontal flex for compact UI
- **Defaults:** Service applies default priority, status, etc.

### Pattern 7: Multi-Step Form with HTMX

**Purpose:** Break complex forms into steps, navigate via HTMX

**Implementation:**

```python
# Step 1: Basic info
@rt("/goals/create/step1")
async def goal_create_step1(request):
    return Div(
        H3("Step 1: Basic Information"),
        Form(
            FormControl(
                Label(LabelText("Goal Title *")),
                Input(type="text", name="title", required=True, cls="input input-bordered w-full"),
            ),
            FormControl(
                Label(LabelText("Category")),
                Select(
                    Option("Personal", value="personal"),
                    Option("Career", value="career"),
                    name="category",
                    cls="select select-bordered w-full",
                ),
            ),
            Button("Next →", variant=ButtonT.primary, type="submit", cls="w-full"),
            hx_post="/goals/create/step2",
            hx_target="#form-container",
        ),
        id="step1",
    )


# Step 2: Timeline
@rt("/goals/create/step2", methods=["POST"])
async def goal_create_step2(request):
    # Store step 1 data in session/hidden fields
    form_data = await request.form()

    return Div(
        H3("Step 2: Timeline"),
        Form(
            # Hidden fields from step 1
            Input(type="hidden", name="title", value=form_data.get("title")),
            Input(type="hidden", name="category", value=form_data.get("category")),

            # Step 2 fields
            FormControl(
                Label(LabelText("Target Date")),
                Input(type="date", name="target_date", cls="input input-bordered w-full"),
            ),

            Div(
                Button("← Back", variant=ButtonT.ghost, hx_get="/goals/create/step1", hx_target="#form-container"),
                Button("Create Goal", variant=ButtonT.primary, type="submit"),
                cls="flex gap-2",
            ),
            hx_post="/goals/create/submit",
            hx_target="#goal-list",
        ),
        id="step2",
    )
```

**Alternative (client-side steps with Alpine.js):**

```python
Div(
    # Step 1
    Div(
        H3("Step 1: Basic Information"),
        # ... step 1 fields ...
        Button("Next →", **{"@click": "step = 2"}, variant=ButtonT.primary),
        x_show="step === 1",
    ),

    # Step 2
    Div(
        H3("Step 2: Timeline"),
        # ... step 2 fields ...
        Button("← Back", **{"@click": "step = 1"}, variant=ButtonT.ghost),
        Button("Submit", type="submit", variant=ButtonT.primary),
        x_show="step === 2",
    ),

    x_data="{ step: 1 }",
)
```

### Pattern 8: Conditional Fields (Show/Hide Based on Selection)

**Purpose:** Display fields conditionally based on other field values

**Implementation (Alpine.js):**

```python
Form(
    # Task type selection
    FormControl(
        Label(LabelText("Task Type")),
        Select(
            Option("One-time", value="once"),
            Option("Recurring", value="recurring"),
            name="task_type",
            x_model="taskType",
            cls="select select-bordered w-full",
        ),
    ),

    # Show only for recurring tasks
    Div(
        FormControl(
            Label(LabelText("Recurrence Pattern")),
            Select(
                Option("Daily", value="daily"),
                Option("Weekly", value="weekly"),
                Option("Monthly", value="monthly"),
                name="recurrence_pattern",
                cls="select select-bordered w-full",
            ),
        ),
        x_show="taskType === 'recurring'",
        x_transition=True,
    ),

    # Submit
    Button("Create Task", variant=ButtonT.primary, type="submit"),

    x_data="{ taskType: 'once' }",
    hx_post="/tasks/quick-add",
)
```

**Key Features:**
- **x-model:** Two-way binding for select value
- **x-show:** Conditional visibility
- **x-transition:** Smooth fade in/out

## Real-World Examples

### Example 1: Task Creation Form (Complete)

**File:** `/home/mike/skuel/app/adapters/inbound/tasks_ui.py`

**Full form implementation:**

```python
def render_task_create_form():
    """Complete task creation form with all fields."""
    return Form(
        # Title (required)
        FormControl(
            Label(LabelText("Title *")),
            Input(
                type="text",
                name="title",
                placeholder="What needs to be done?",
                required=True,
                maxlength=200,
                autofocus=True,
                cls="input input-bordered w-full",
            ),
        ),

        # Description
        FormControl(
            Label(LabelText("Description")),
            Textarea(
                name="description",
                placeholder="Add details, notes, or context...",
                rows=4,
                cls="textarea textarea-bordered w-full",
            ),
        ),

        # Priority
        FormControl(
            Label(LabelText("Priority")),
            Select(
                Option("Select priority...", value="", selected=True),
                Option("🔴 Critical", value="critical"),
                Option("🟠 High", value="high"),
                Option("🟡 Medium", value="medium"),
                Option("🟢 Low", value="low"),
                name="priority",
                cls="select select-bordered w-full",
            ),
        ),

        # Project (autocomplete)
        FormControl(
            Label(LabelText("Project")),
            Input(
                type="text",
                name="project",
                list="project-list",
                placeholder="Start typing...",
                cls="input input-bordered w-full",
            ),
            Datalist(id="project-list"),  # Populated via HTMX
        ),

        # Dates (two columns)
        Div(
            FormControl(
                Label(LabelText("Scheduled Date")),
                Input(type="date", name="scheduled_date", cls="input input-bordered w-full"),
            ),
            FormControl(
                Label(LabelText("Due Date")),
                Input(type="date", name="due_date", min=str(date.today()), cls="input input-bordered w-full"),
            ),
            cls="grid grid-cols-2 gap-4",
        ),

        # Submit
        FormControl(
            Button("Create Task", variant=ButtonT.primary, type="submit", cls="w-full mt-4"),
        ),

        hx_post="/tasks/quick-add",
        hx_target="body",  # Replace entire page
        cls="space-y-4",
    )
```

### Example 2: Goal Progress Update Form (Modal)

**File:** `/home/mike/skuel/app/adapters/inbound/goals_ui.py`

**Specialized form for updating progress:**

```python
@rt("/goals/{uid}/progress-form")
async def goal_progress_form(uid: str, request):
    """Return modal with progress update form."""
    user_uid = require_authenticated_user(request)

    # Get current goal
    goal_result = await goals_service.get_for_user(uid, user_uid)
    if goal_result.is_error:
        return render_error_banner("Goal not found")

    goal = goal_result.value

    return Modal(
        "progress-modal",
        ModalBox(
            H3(f"Update Progress: {goal.title}"),
            P(f"Current: {goal.progress}%", cls="text-sm text-base-content/70 mb-4"),

            Form(
                # Progress slider
                FormControl(
                    Label(LabelText("New Progress (%)")),
                    Input(
                        type="range",
                        name="progress",
                        min="0",
                        max="100",
                        value=str(goal.progress),
                        step="5",
                        x_model="progress",
                        cls="range range-primary",
                    ),
                    P(
                        Span(x_text="progress", cls="font-bold"),
                        "%",
                        cls="text-sm text-center mt-2",
                    ),
                ),

                # Reflection notes
                FormControl(
                    Label(LabelText("Reflection (optional)")),
                    Textarea(
                        name="notes",
                        placeholder="What did you accomplish? What's next?",
                        rows=3,
                        cls="textarea textarea-bordered w-full",
                    ),
                ),

                ModalAction(
                    Button("Cancel", variant=ButtonT.ghost, onclick="closeModal('progress-modal')"),
                    Button("Update", variant=ButtonT.success, type="submit"),
                ),

                hx_post=f"/api/goals/{uid}/progress",
                hx_target="body",
                x_data=f"{{ progress: {goal.progress} }}",
            ),
        ),
    )
```

**Key Features:**
- **Range input:** Visual slider for progress percentage
- **Alpine.js binding:** Show current value dynamically
- **Optional field:** Reflection notes for context
- **Modal actions:** Cancel and submit buttons

## Common Mistakes & Anti-Patterns

### Mistake 1: Skipping Early Validation

```python
# ❌ BAD: No validation until Pydantic layer (generic errors)
@rt("/tasks/quick-add", methods=["POST"])
async def create_task(request):
    form_data = await request.form()
    # Directly create Pydantic model - generic 422 error if fails
    task_request = TaskCreateRequest(**form_data)
    # ...

# ✅ GOOD: Early validation with clear messages
@rt("/tasks/quick-add", methods=["POST"])
async def create_task(request):
    form_data = await request.form()
    form_dict = dict(form_data)

    # Validate early
    validation_result = validate_task_form_data(form_dict)
    if validation_result.is_error:
        return render_error_banner(f"Validation error: {validation_result.error}")

    # Continue...
```

### Mistake 2: Not Using FormControl Wrapper

```python
# ❌ BAD: Label and input not associated (accessibility issue)
Label("Email")
Input(type="email", name="email")

# ✅ GOOD: Wrapped in FormControl
FormControl(
    Label(LabelText("Email")),
    Input(type="email", name="email", cls="input input-bordered w-full"),
)
```

### Mistake 3: Forgetting to Reset Form After HTMX Submit

```python
# ❌ BAD: Form retains old values after submit
Form(
    # ... fields ...
    hx_post="/tasks/quick-add",
)

# ✅ GOOD: Auto-reset after successful submit
Form(
    # ... fields ...
    hx_post="/tasks/quick-add",
    hx_on="htmx:afterRequest: this.reset()",
)
```

### Mistake 4: Using GET for Form Submission

```python
# ❌ BAD: Form modifies data but uses GET
Form(
    # ... fields ...
    hx_get="/tasks/create",  # Wrong HTTP method
)

# ✅ GOOD: POST for mutations
Form(
    # ... fields ...
    hx_post="/tasks/quick-add",
)
```

### Mistake 5: Missing Required Attribute for Mandatory Fields

```python
# ❌ BAD: No client-side validation for required field
FormControl(
    Label(LabelText("Title *")),  # Asterisk suggests required
    Input(type="text", name="title"),  # But not marked required
)

# ✅ GOOD: required=True for immediate feedback
FormControl(
    Label(LabelText("Title *")),
    Input(type="text", name="title", required=True),
)
```

### Mistake 6: Not Providing Default Values in Edit Forms

```python
# ❌ BAD: Edit form shows empty fields
def edit_task_form(task_uid: str):
    return Form(
        Input(type="text", name="title"),  # Empty!
        # ...
    )

# ✅ GOOD: Pre-populate with current values
def edit_task_form(task: Task):
    return Form(
        Input(type="text", name="title", value=task.title),
        Textarea(name="description", value=task.description or ""),
        # ...
    )
```

## Testing & Verification Checklist

When implementing forms, verify:

### Functional Tests

- [ ] **Required fields:** Client-side validation (HTML5) prevents empty submit
- [ ] **Early validation:** Custom validation returns clear error messages
- [ ] **Pydantic validation:** Type errors caught (422 response)
- [ ] **HTMX submit:** Form submits via POST, target updated correctly
- [ ] **Error handling:** Errors display in UI (banner or inline)
- [ ] **Success handling:** Form clears or redirects after success
- [ ] **Date constraints:** Min/max dates enforced, invalid dates rejected

### Accessibility Tests

- [ ] **Labels:** All inputs have associated labels (FormControl + Label)
- [ ] **Tab order:** Keyboard navigation flows logically
- [ ] **Focus management:** First field focused on form load (autofocus)
- [ ] **Error announcements:** Screen reader announces validation errors
- [ ] **Required indicators:** Asterisks or aria-required for mandatory fields

### UX Tests

- [ ] **Placeholder text:** Helpful hints in all text inputs
- [ ] **Button states:** Submit button disabled during processing
- [ ] **Loading indicators:** Spinner or text while submitting
- [ ] **Autocomplete:** Suggestions appear with 300ms debounce
- [ ] **Conditional fields:** Show/hide smoothly with transitions
- [ ] **Mobile layout:** Form usable on small screens (320px+)

### Data Tests

- [ ] **Empty strings:** Handled as None or default values
- [ ] **Whitespace:** Trimmed before validation
- [ ] **Special characters:** Properly escaped/sanitized
- [ ] **Date formats:** ISO format (YYYY-MM-DD) consistently used
- [ ] **Checkbox values:** "on" parsed to boolean correctly

## Related Documentation

### SKUEL Documentation

- `/docs/patterns/UI_COMPONENT_PATTERNS.md` - Lines 1079-1145 (Form patterns)
- `/docs/patterns/API_VALIDATION_PATTERNS.md` - Query param and JSON validation
- `/adapters/inbound/tasks_ui.py` - Lines 1079-1145 (Early validation pattern)
- `/adapters/inbound/goals_ui.py` - Progress form example

### Related Patterns

- **UI Error Handling:** For error banner components and Result[T] pattern
- **DaisyUI:** For form component styling
- **HTMX:** For form submission without full page reload
- **Accessibility Guide:** For ARIA labels and keyboard navigation

## Deep Dive Resources

**Patterns:**
- [UI_COMPONENT_PATTERNS.md](/docs/patterns/UI_COMPONENT_PATTERNS.md) - Lines 1079-1145 (Form patterns)
- [API_VALIDATION_PATTERNS.md](/docs/patterns/API_VALIDATION_PATTERNS.md) - Query param and JSON validation
- [ERROR_HANDLING.md](/docs/patterns/ERROR_HANDLING.md) - Safe form parsing pattern (lines 692-820)

**Implementation Examples:**
- `/adapters/inbound/tasks_ui.py` - Early validation pattern (lines 1079-1145)
- `/adapters/inbound/goals_ui.py` - Progress form with validation
- `/adapters/inbound/user_profile_ui.py` - Safe form parsing with safe_int/safe_bool

---

## See Also

- `daisyui` - For FormControl, Label, Input, Select, Textarea components
- `html-htmx` - For form submission patterns with HTMX
- `ui-error-handling` - For error banner rendering and Result[T]
- `accessibility-guide` - For ARIA labels, focus management, screen readers
- `js-alpine` - For dynamic form fields and conditional visibility
