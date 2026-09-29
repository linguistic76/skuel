# accessibility-guide Reference: Implementation Patterns

> On-demand reference for the [`accessibility-guide`](SKILL.md) skill. SKILL.md holds the WCAG philosophy, the core concepts (semantic HTML, ARIA, keyboard navigation, color contrast, focus, touch targets), the anti-patterns, and the testing checklist; this file holds the eight detailed implementation patterns and the real-world SKUEL examples.

## Implementation Patterns

### Pattern 1: Accessible Button vs Link

**Purpose:** Use correct element for semantic meaning and keyboard behavior

**Implementation:**

```python
from ui.activities._shared import safe_id
from ui.components import Button, ButtonT
from ui.primitives import ButtonLink

# ✅ Button for actions (same page) — renders <button>
Button(
    "Delete Task",
    cls=ButtonT.destructive,
    type="button",                               # not a form submit
    hx_post=f"/api/tasks/delete?uid={task.uid}",
    hx_confirm="Delete this task?",
    hx_target=f"#task-{safe_id(task.uid)}",      # the TaskCard's id
    hx_swap="delete",                            # the door answers JSON; remove the card instead
    aria_label=f"Delete task: {task.title}",     # include context
)

# ✅ Link for navigation (new page/route) — renders <a href>, styled as a button
ButtonLink("View Task Details", href=f"/tasks/detail?uid={task.uid}", cls=ButtonT.ghost, size="sm")

# ❌ BAD: Div as button (no keyboard support, no role)
Div("Delete Task", onclick="confirmDelete()", cls="text-destructive cursor-pointer")

# ⚠️ Only when a native <button> is impossible: role + tabindex + both key handlers
Div(
    "Delete Task",
    role="button",
    tabindex="0",
    onclick="confirmDelete()",
    onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); confirmDelete(); }",
    aria_label="Delete task",
)
```

**Key Principles:**
- **Button:** Actions that affect current page (submit, delete, toggle)
- **Link:** Navigation to different page/route
- **ARIA button:** Only when semantic `<button>` impossible (rare)

### Pattern 2: Form Labels and Descriptions

**Purpose:** Associate labels with inputs, provide help text

SKUEL uses `LabelInput`, `LabelTextArea`, and `LabelSelect` wrappers that have **built-in ARIA support**. These wrappers wire `for=`/`id=`, `aria-describedby`, `aria-invalid`, and help/error text themselves; no manual wiring needed.

**Implementation:**

```python
from fasthtml.common import Option

from ui.forms import Input, LabelInput, LabelSelect, LabelTextArea

# ✅ Basic label association (built into LabelInput)
LabelInput("Email Address", type="email", name="email")

# ✅ With help text (auto aria-describedby + help div)
LabelInput(
    "Password",
    type="password",
    name="password",
    help_text="Must be at least 8 characters with one uppercase letter.",
)

# ✅ With error message (auto aria-invalid="true" + aria-describedby + role="alert" error div)
LabelInput(
    "Username",
    type="text",
    name="username",
    error_text="This username is unavailable.",
)

# ✅ Required field indicator
LabelInput("Full Name", type="text", name="name", required=True)

# ✅ Textarea with help text
LabelTextArea("Description", name="description", help_text="Describe what needs to be done in detail.")

# ✅ Select with label (options positional, label keyword-only)
LabelSelect(
    Option("Low", value="low"),
    Option("Medium", value="medium", selected=True),
    Option("High", value="high"),
    label="Priority",
    name="priority",
)

# Standalone input (no visible label, e.g. a search box) — give it an accessible name
Input(type="search", name="q", placeholder="Search...", aria_label="Search")
```

**Built-in ARIA of LabelInput/LabelTextArea/LabelSelect** (rendered output, not intent):
- **Label association:** `<label for="{id}">` beside the control, whose `id` defaults to `name`
- **help_text=:** a `{id}-help` div, listed in the control's `aria-describedby`
- **error_text=:** a `role="alert"` `{id}-error` div, listed in `aria-describedby`, plus `aria-invalid="true"` and the destructive border
- **required=True:** the HTML `required` attribute

### Pattern 3: Modal Dialog Accessibility

**Purpose:** Announce the dialog, handle Escape, move focus in and back out

`AlpineModal` gives the overlay: backdrop, click-outside-to-close, `x-cloak`, transition.
The dialog semantics, Escape and focus handling are the caller's. See SKILL.md
Mistake 5 for the measured pattern:

```python
Div(
    Button("Delete", x_ref="trigger", **{"@click": "open = true; $nextTick(() => $refs.cancel.focus())"}),
    AlpineModal(
        Div(
            H2("Delete this task?", id="del-title"),
            P("This cannot be undone.", id="del-body"),
            Div(
                Button("Cancel", x_ref="cancel", cls=ButtonT.ghost,
                       **{"@click": "open = false; $refs.trigger.focus()"}),
                Button("Delete", cls=ButtonT.destructive, hx_post=delete_url),
                cls="flex gap-2 justify-end mt-4",
            ),
            role="dialog",
            aria_labelledby="del-title",
            aria_describedby="del-body",
        ),
        show="open",
        close="open = false; $refs.trigger.focus()",
    ),
    x_data="{ open: false }",
    **{"@keydown.escape.window": "if (open) { open = false; $refs.trigger.focus() }"},
)
```

**What it gives:**
- **role="dialog" + aria-labelledby/describedby:** announced as a named dialog
- **Escape** closes it, and only while it is open (the window listener is guarded by `open`)
- **Focus** moves to Cancel on open and back to the trigger on close

**What it does not give:** a focus trap. Tab can still reach the page behind the backdrop,
which is why the pattern leaves out `aria-modal="true"`: that attribute promises an inert
background. SKUEL vendors no Alpine focus plugin, so a real modal means writing the
Tab/Shift+Tab containment (or marking the background `inert`) and then adding `aria-modal`.

### Pattern 4: Skip Links for Keyboard Users

**Purpose:** Allow keyboard users to skip repetitive navigation

`BasePage` already renders one, first in `<body>`: `A("Skip to main content",
href="#main-content", cls="skip-link")`. The `<main>` it targets carries
`id="main-content"`, and `.skip-link` (`static/css/main.css`) keeps it off-screen until it
takes focus. A page built on `BasePage` needs nothing more; don't add a second skip link.

**Key Features:**
- **Hidden by default:** Positioned off-screen
- **Visible on focus:** Appears when keyboard user tabs to it
- **Direct jump:** Links to main content ID

### Pattern 5: Live Region Announcements

**Purpose:** Announce dynamic content changes to screen readers

SKUEL has one live region, `#live-region`, rendered by `BasePage`. For HTMX traffic,
`skuel.js` announces into it for you (SKILL.md section 7). For anything else, call the same
function:

```javascript
window.SKUEL.announce('Filters cleared');               // polite
window.SKUEL.announce('Could not save', 'assertive');   // interrupts
```

It sets the region's `aria-live` to the priority, writes the text, and clears it three
seconds later.

For errors shown in the page, use the real banner. `render_error_banner(message)`
(`ui/patterns/error_banner.py`) renders `role="alert"`, so it is announced when it is
inserted; don't hand-roll another.

**ARIA Live Regions:**

| Type | aria-live | When to Use |
|------|-----------|-------------|
| **Polite** | `polite` | Non-critical updates (success messages, status changes) |
| **Assertive** | `assertive` | Critical errors, time-sensitive alerts |
| **Off** | `off` | Default (no announcement) |

**Additional Attributes:**
- **aria-atomic="true":** Announce entire region (not just changes)
- **role="status":** Polite live region (implicit aria-live="polite")
- **role="alert":** Assertive live region (implicit aria-live="assertive")
- A live region must already be in the DOM when its text changes; one inserted together with its text is often not announced. That is why SKUEL keeps a single persistent region.

### Pattern 6: Accessible Dropdown (Disclosure)

**Purpose:** Keyboard-operable disclosure with the right ARIA state

```python
Div(
    Button(
        "Options",
        Icon("chevron-down", size=16),
        x_ref="trig",
        aria_controls="options-menu",
        cls=ButtonT.ghost,
        **{":aria-expanded": "open", "@click": "open = !open"},
    ),
    Ul(
        Li(A("Settings", href="/settings")),
        id="options-menu",
        cls="absolute right-0 mt-2 w-48 bg-background border border-border rounded-lg shadow-lg z-50",
        **{"x-show": "open", "x-transition": ""},
    ),
    x_data="{ open: false }",
    cls="relative",
    **{"@click.outside": "open = false", "@keydown.escape": "open = false; $refs.trig.focus()"},
)
```

Measured with the vendored Alpine 3.14.8: `aria-expanded` reads `"false"` → `"true"` →
`"false"` (Alpine keeps a false `aria-expanded` rather than dropping it), and Escape from
inside the menu returns focus to the trigger. `dropdown_menu()` in `ui/primitives.py` is the
styled shell; it carries no ARIA, so the attributes above are still the caller's.

**Key Features:**
- **aria-controls:** the trigger names what it opens. No `aria-haspopup`: that announces a
  menu, and this is a disclosure of plain links
- **:aria-expanded:** tracks open/closed state
- **Escape:** closes the menu and returns focus to the trigger
- Links inside stay plain links. A `role="menu"` widget (which *does* take `aria-haspopup`)
  additionally needs menu roles and arrow-key roving focus

### Pattern 7: Progress Indicators

**Purpose:** Announce progress to screen readers

```python
from ui.feedback import Loading, Progress
from ui.layout import Size

# Determinate progress — Progress renders role="progressbar" with aria-valuenow/min/max
Div(
    P("Upload progress", id="upload-label", cls="text-sm mb-2"),
    Progress(value=40, aria_labelledby="upload-label"),
)

# Indeterminate progress — Loading() renders role="status" with aria-label="Loading";
# a caller's aria_label replaces the default
Loading(size=Size.md, aria_label="Loading tasks")
```

**ARIA Progressbar Attributes:**
- **role="progressbar":** Announces as progress indicator
- **aria-valuenow:** Current value
- **aria-valuemin/max:** Range (typically 0-100)
- **aria-label or aria-labelledby:** Description of what's loading

### Pattern 8: Tab Panel Component

**Purpose:** Accessible tabbed interface with keyboard navigation

The live reference is `GroupsHub` in `ui/groups/hub.py`, a WAI-ARIA tabs widget in Alpine
with roving tabindex:

```python
def _tab_button(group: Group) -> FT:
    cond = f"activeTab === '{group.uid}'"
    return Button(
        group.name,
        role="tab",
        id=f"groups-tab-{group.uid}",
        type="button",
        aria_controls=f"groups-panel-{group.uid}",
        **{
            ":aria-selected": cond,
            ":tabindex": f"{cond} ? 0 : -1",      # only the active tab is in the tab order
            "@click": f"activeTab = '{group.uid}'",
        },
    )

def _tab_panel(group: Group) -> FT:
    return Div(
        ...,
        role="tabpanel",
        id=f"groups-panel-{group.uid}",
        aria_labelledby=f"groups-tab-{group.uid}",
        tabindex="0",
        **{"x-show": f"activeTab === '{group.uid}'"},
    )

# The tablist moves activation AND focus with the arrow keys, Home and End
Div(
    *[_tab_button(g) for g in groups],
    role="tablist",
    **{
        "aria-label": "Your groups",
        "@keydown.arrow-right.prevent": "activeTab = tabs[(tabs.indexOf(activeTab) + 1) % tabs.length]; "
        "$nextTick(() => document.getElementById('groups-tab-' + activeTab).focus())",
        # arrow-left, home and end follow the same shape
    },
)
```

**Key Features:**
- **role="tablist" / "tab" / "tabpanel":** the three roles, each tab `aria-controls` its panel
- **:aria-selected:** bound to the active tab
- **Roving tabindex:** the active tab is `0`, the rest `-1`, so Tab enters the list once
- **Arrow / Home / End keys:** move between tabs

Use tabs only for same-page panels. Links between pages belong in the sidebar's section
nav (`<nav>` + `aria-current`), never `role="tab"`.

## Real-World Examples

### Example 1: SKUEL Sidebar Navigation (Accessible Navigation)

**File:** `/ui/patterns/sidebar.py` — the one `SidebarPage` every sidebar section uses. It renders the same `SidebarItem` list twice: a fixed desktop sidebar at `lg+` and, below `lg`, the **section nav** — a horizontally scrolling row above the content.

**The section nav (below `lg`):**

```python
Nav(
    Ul(
        *[
            Li(
                A(
                    Icon(item.icon, size=16, cls="shrink-0"),   # Icon() sets aria-hidden itself
                    Span(item.label),
                    href=item.href,
                    **({"aria_current": "page"} if item.slug == active else {}),
                ),
                cls="shrink-0",                                  # the ROW overflows, never the page
            )
            for item in items
        ],
        role="list",                                             # restores list semantics under list-none
        cls="flex overflow-x-auto gap-1 border-b border-border list-none m-0 p-0",
    ),
    aria_label=title,                                            # "Tasks+", "Library", …
)
```

A parse-time inline `<script>` after the nav sets the row's `scrollLeft` so the `[aria-current="page"]` link is centred before first paint (never `scrollIntoView`, which scrolls ancestors), and stamps `data-overflow`/`data-at-end` for a CSS right-edge fade. With JS off the row is a plain scrolling list.

**Why accessible:**
- **`<nav>` + `<ul role="list">` + `<a aria-current="page">`:** the links navigate between PAGES, so they are links in a navigation landmark — never `role="tab"`/`aria-selected`, which describe same-page panels. (The teaching student page's same-page switcher IS a tabs widget and renders `<div role="tablist">` instead; the two are never mixed — a nav list owning `role="tab"` children is an invalid tabs hierarchy.)
- **`aria-label` on the `<nav>`:** names the landmark after the section, so a screen-reader user can tell the Tasks+ row from the Library row
- **`role="list"`:** `list-none` strips list semantics in VoiceOver; the explicit role restores "list, 11 items"
- **Decorative icons hidden:** `Icon()` owns `aria-hidden="true"` (`kwargs.setdefault`), so no call site has to remember it
- **Native scrolling, siblings visible:** no drawer or hamburger — every sibling stays reachable by keyboard and touch, and the current link is on screen when the page loads
- **44px targets:** every link is `min-h-[44px]`; the desktop rows carry `aria-current="page"` the same way

### Example 2: Task Form with Validation

**Where:** `TaskCreateForm` (`ui/activities/tasks_form.py`) calls `render_activity_form`
(`ui/patterns/activity_form_helper.py`), a thin wrapper over `FormGenerator`, which renders
the same labelled-control shape. By hand it looks like:

```python
from ui.forms import LabelInput

LabelInput(
    "Title",
    type="text",
    name="title",
    placeholder="What needs to be done?",
    required=True,
    maxlength=200,
    autofocus=True,
    help_text="Enter a clear, actionable task title (max 200 characters).",
)
```

**Why accessible:**
- **LabelInput:** Automatically associates label with input (no manual `for_=`/`id=` wiring)
- **required=True:** Adds HTML `required` attribute
- **help_text=:** Automatically adds `aria-describedby` linking to the help text div
- **autofocus:** Keyboard users start typing immediately
- **maxlength:** Prevents over-length input client-side
