---
name: accessibility-guide
description: Expert guide for building accessible web applications following WCAG standards. Use when implementing keyboard navigation, screen reader support, ARIA labels, focus management, semantic HTML, or when the user mentions accessibility, a11y, WCAG, screen readers, or inclusive design.
allowed-tools: Read, Grep, Glob
related_skills:
- html-htmx
- html-navigation
- ui-css
- skuel-form-patterns
- js-alpine
---

# Accessibility Guide for SKUEL

## Core Philosophy

> "Accessibility is not a feature - it's a baseline requirement. Every user deserves equal access to functionality, regardless of how they interact with the application."

SKUEL follows **WCAG 2.1 Level AA** standards, ensuring:

- **Perceivable:** Content visible to all senses (visual, auditory, touch)
- **Operable:** Functional via keyboard, mouse, touch, voice
- **Understandable:** Clear labels, predictable behavior, error guidance
- **Robust:** Compatible with assistive technologies (screen readers, voice control)

## When to Use This Skill

Use this guide when:

- ✅ Building **interactive components** (modals, dropdowns, forms)
- ✅ Implementing **keyboard navigation** (tab order, shortcuts, focus traps)
- ✅ Adding **dynamic content** (live regions, ARIA announcements)
- ✅ Creating **custom controls** (toggle buttons, range sliders, autocomplete)
- ✅ Ensuring **color contrast** and visual accessibility
- ✅ Testing with **screen readers** (NVDA, JAWS, VoiceOver)

## Core Concepts

### 1. Semantic HTML First

**Always use the correct HTML element for the job:**

| Purpose | Semantic Element | Why |
|---------|------------------|-----|
| Navigation | `<nav>` | Announces navigation region to screen readers |
| Main content | `<main>` | Identifies primary content area |
| Section with header | `<section>` | Groups related content logically |
| Form field | `<label>` + `<input>` | Associates label with control |
| Button action | `<button>` | Native keyboard support, role=button |
| Link navigation | `<a href>` | Indicates navigation intent |
| List | `<ul>` / `<ol>` | Structure announced to screen readers |

**Decision Tree:**

```
Does this element perform an action (same page)?
├─ YES → <button>
└─ NO → Does it navigate to a new page?
    ├─ YES → <a href>
    └─ NO → Does it display data?
        ├─ YES → Semantic HTML (table, list, section)
        └─ NO → Generic <div> with ARIA
```

### 2. ARIA Roles and Attributes

**ARIA (Accessible Rich Internet Applications)** enhances HTML semantics when native elements insufficient:

| ARIA Attribute | Purpose | Example |
|----------------|---------|---------|
| `role` | Define element purpose | `role="dialog"`, `role="button"` |
| `aria-label` | Provide text label | `aria-label="Close modal"` |
| `aria-labelledby` | Reference label element | `aria-labelledby="heading-id"` |
| `aria-describedby` | Reference description | `aria-describedby="help-text"` |
| `aria-hidden` | Hide from screen readers | `aria-hidden="true"` (decorative icons) |
| `aria-live` | Announce dynamic changes | `aria-live="polite"` (notifications) |
| `aria-expanded` | Indicate toggle state | `aria-expanded="true"` (accordion open) |
| `aria-current` | Mark active item | `aria-current="page"` (current nav link) |

**ARIA Rules:**
1. **First Rule:** Don't use ARIA - use semantic HTML
2. **Second Rule:** Don't change native semantics (e.g., don't put role="button" on `<a>`)
3. **Third Rule:** All interactive ARIA controls must be keyboard operable
4. **Fourth Rule:** Don't use `role="presentation"` or `aria-hidden="true"` on focusable elements
5. **Fifth Rule:** All interactive elements must have an accessible name

### 3. Keyboard Navigation Standards

**All interactive elements must be keyboard accessible:**

| Key | Action | Elements |
|-----|--------|----------|
| **Tab** | Move focus forward | All focusable elements |
| **Shift+Tab** | Move focus backward | All focusable elements |
| **Enter** | Activate | Links, buttons |
| **Space** | Activate | Buttons, checkboxes, toggles |
| **Escape** | Close/Cancel | Modals, dropdowns, menus |
| **Arrow Keys** | Navigate within | Menus, tabs, radio groups |
| **Home/End** | First/last item | Lists, menus |

**Focus Management Principles:**
- **Visible focus:** Always show focus indicator (outline, ring)
- **Logical order:** Tab order matches visual order
- **Focus trapping:** Trap focus in modals (can't tab outside)
- **Focus restoration:** Return focus after modal closes

### 4. Color Contrast Requirements

**WCAG 2.1 Level AA contrast ratios:**

| Content Type | Contrast Ratio | Example |
|--------------|----------------|---------|
| Normal text (< 18pt) | 4.5:1 | Body text on background |
| Large text (≥ 18pt or 14pt bold) | 3:1 | Headings, callouts |
| UI components | 3:1 | Buttons, form borders, icons |
| Graphics (meaningful) | 3:1 | Chart elements, diagrams |

**SKUEL MonsterUI Color System:**
- `text-base-content` on `bg-base-100` - Always passes (designed for contrast)
- `text-primary` on `bg-base-100` - Checked in theme
- `text-error` on `bg-error` - High contrast for alerts

**Testing:** Use browser DevTools (Lighthouse Accessibility audit) or WebAIM Contrast Checker.

### 5. Focus Indicator Standards

**Always provide visible focus:**

```css
/* ❌ BAD: Removing focus outline */
*:focus {
    outline: none;
}

/* ✅ GOOD: Custom focus ring that's always visible */
*:focus-visible {
    outline: 2px solid oklch(var(--color-primary));
    outline-offset: 2px;
}

/* Tailwind equivalent */
.focus-visible:ring-2 .ring-primary .ring-offset-2
```

**MonsterUI default:** All interactive components have built-in focus styles.

## Implementation Patterns

### Pattern 1: Accessible Button vs Link

**Purpose:** Use correct element for semantic meaning and keyboard behavior

**Implementation:**

```python
from fasthtml.common import A, Button

# ✅ Button for actions (same page)
Button(
    "Delete Task",
    variant=ButtonT.error,
    onclick="confirmDelete('task-123')",
    type="button",  # Prevent form submission
    aria_label="Delete task: Buy groceries",  # Include context
)

# ✅ Link for navigation (new page/route)
A(
    "View Task Details",
    href="/tasks/task-123",
    cls="btn btn-ghost",  # Styled as button, but semantically a link
)

# ❌ BAD: Div as button (no keyboard support)
Div(
    "Delete Task",
    onclick="confirmDelete('task-123')",
    cls="btn btn-error",  # Looks like button, but not accessible
)

# ✅ GOOD: Div with ARIA and keyboard support
Div(
    "Delete Task",
    role="button",
    tabindex="0",
    onclick="confirmDelete('task-123')",
    onkeydown="if(event.key === 'Enter' || event.key === ' ') confirmDelete('task-123')",
    aria_label="Delete task: Buy groceries",
    cls="btn btn-error",
)
```

**Key Principles:**
- **Button:** Actions that affect current page (submit, delete, toggle)
- **Link:** Navigation to different page/route
- **ARIA button:** Only when semantic `<button>` impossible (rare)

### Pattern 2: Form Labels and Descriptions

**Purpose:** Associate labels with inputs, provide help text

**Implementation:**

```python
from ui.forms import FormControl, Input, Label, LabelText

# ✅ Basic label association (implicit via FormControl)
FormControl(
    Label(LabelText("Email Address")),
    Input(
        type="email",
        name="email",
        id="email-input",
        aria_required="true",
        cls="input input-bordered w-full",
    ),
)

# ✅ With help text (aria-describedby)
FormControl(
    Label(LabelText("Password"), for_="password-input"),
    Input(
        type="password",
        name="password",
        id="password-input",
        aria_describedby="password-help",
        aria_required="true",
        cls="input input-bordered w-full",
    ),
    P(
        "Must be at least 8 characters with one uppercase letter.",
        id="password-help",
        cls="text-sm text-base-content/70 mt-1",
    ),
)

# ✅ With error message (aria-invalid + aria-describedby)
FormControl(
    Label(LabelText("Username"), for_="username-input"),
    Input(
        type="text",
        name="username",
        id="username-input",
        aria_invalid="true",
        aria_describedby="username-error",
        cls="input input-bordered input-error w-full",
    ),
    P(
        "This username is unavailable.",
        id="username-error",
        role="alert",
        cls="text-sm text-error mt-1",
    ),
)

# ✅ Required field indicator
FormControl(
    Label(
        LabelText("Full Name "),
        Span("*", cls="text-error", aria_label="required"),
        for_="name-input",
    ),
    Input(
        type="text",
        name="name",
        id="name-input",
        required=True,
        aria_required="true",
        cls="input input-bordered w-full",
    ),
)
```

**Key ARIA Attributes:**
- **aria-required:** Indicates required field (in addition to HTML `required`)
- **aria-invalid:** Marks field with validation error
- **aria-describedby:** Links help text or error message to input
- **role="alert":** Screen reader announces error immediately

### Pattern 3: Modal Dialog Accessibility

**Purpose:** Trap focus, announce to screen readers, handle keyboard events

**Implementation:**

```python
from ui.buttons import Button, ButtonT
from ui.modals import Modal, ModalAction, ModalBox

def create_accessible_modal(modal_id: str, title: str, content: Any) -> Any:
    """Create fully accessible modal dialog."""
    return Div(
        # Modal backdrop
        Div(
            cls="modal-backdrop",
            onclick=f"closeModal('{modal_id}')",
            aria_hidden="true",  # Decorative
        ),

        # Modal dialog
        Div(
            # Modal content
            Div(
                # Close button (top-right)
                Button(
                    "✕",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                    onclick=f"closeModal('{modal_id}')",
                    aria_label="Close modal",
                    cls="absolute top-2 right-2",
                ),

                # Modal header
                H2(
                    title,
                    id=f"{modal_id}-title",
                    cls="text-xl font-bold mb-4",
                ),

                # Modal body
                Div(content, id=f"{modal_id}-body"),

                # Modal actions
                ModalAction(
                    Button("Cancel", variant=ButtonT.ghost, onclick=f"closeModal('{modal_id}')"),
                    Button("Confirm", variant=ButtonT.primary, onclick=f"confirmAction('{modal_id}')"),
                ),

                role="dialog",
                aria_modal="true",
                aria_labelledby=f"{modal_id}-title",
                aria_describedby=f"{modal_id}-body",
                tabindex="-1",  # Programmatically focusable
                cls="modal-box",
            ),

            id=modal_id,
            cls="modal",
            **{"data-modal": "true"},  # For JS focus trap
        ),
    )


# JavaScript for focus trap and keyboard handling
"""
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.classList.add('modal-open');

    // Store last focused element
    modal.dataset.lastFocus = document.activeElement.id;

    // Focus first interactive element in modal
    const firstFocusable = modal.querySelector('button, input, select, textarea, a[href]');
    if (firstFocusable) firstFocusable.focus();

    // Trap focus within modal
    modal.addEventListener('keydown', trapFocus);

    // Close on Escape
    modal.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal(modalId);
    });
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.classList.remove('modal-open');

    // Restore focus to triggering element
    const lastFocusId = modal.dataset.lastFocus;
    if (lastFocusId) {
        const lastFocus = document.getElementById(lastFocusId);
        if (lastFocus) lastFocus.focus();
    }

    // Remove focus trap
    modal.removeEventListener('keydown', trapFocus);
}

function trapFocus(e) {
    if (e.key !== 'Tab') return;

    const modal = e.currentTarget;
    const focusableElements = modal.querySelectorAll(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href]'
    );

    const firstFocusable = focusableElements[0];
    const lastFocusable = focusableElements[focusableElements.length - 1];

    if (e.shiftKey && document.activeElement === firstFocusable) {
        lastFocusable.focus();
        e.preventDefault();
    } else if (!e.shiftKey && document.activeElement === lastFocusable) {
        firstFocusable.focus();
        e.preventDefault();
    }
}
"""
```

**Key Features:**
- **role="dialog":** Announces as modal dialog
- **aria-modal="true":** Indicates background inert
- **aria-labelledby:** Links to modal title
- **Focus trap:** Tab cycles within modal only
- **Escape key:** Closes modal
- **Focus restoration:** Returns to trigger element

### Pattern 4: Skip Links for Keyboard Users

**Purpose:** Allow keyboard users to skip repetitive navigation

**Implementation:**

```python
def render_skip_links() -> Any:
    """Skip navigation links (hidden until focused)."""
    return Div(
        A(
            "Skip to main content",
            href="#main-content",
            cls="skip-link",
        ),
        A(
            "Skip to navigation",
            href="#main-navigation",
            cls="skip-link",
        ),
    )


# CSS for skip links
"""
.skip-link {
    position: absolute;
    top: -40px;
    left: 0;
    background: oklch(var(--color-primary));
    color: white;
    padding: 8px 16px;
    text-decoration: none;
    z-index: 9999;
}

.skip-link:focus {
    top: 0;
}
"""

# Usage in BasePage
def BasePage(content, **kwargs):
    return Html(
        Head(...),
        Body(
            render_skip_links(),  # First element in body
            Navbar(..., id="main-navigation"),
            Main(content, id="main-content"),
        ),
    )
```

**Key Features:**
- **Hidden by default:** Positioned off-screen
- **Visible on focus:** Appears when keyboard user tabs to it
- **Direct jump:** Links to main content ID

### Pattern 5: Live Region Announcements

**Purpose:** Announce dynamic content changes to screen readers

**Implementation:**

```python
# Success notification (polite announcement)
def render_success_toast(message: str) -> Any:
    """Success toast with screen reader announcement."""
    return Div(
        Div(
            Span("✓", cls="text-success text-xl", aria_hidden="true"),
            Span(message, cls="ml-2"),
            cls="alert alert-success",
        ),
        role="status",
        aria_live="polite",
        aria_atomic="true",
        cls="toast toast-top toast-end",
    )


# Error notification (assertive announcement)
def render_error_banner(message: str) -> Any:
    """Error banner with immediate screen reader announcement."""
    return Div(
        Div(
            P("⚠️ Error", cls="font-bold text-error"),
            P(message, cls="text-sm"),
            cls="alert alert-error",
        ),
        role="alert",
        aria_live="assertive",
        aria_atomic="true",
        cls="mb-4",
    )


# Loading state announcement
def render_loading_state() -> Any:
    """Loading indicator with screen reader announcement."""
    return Div(
        Div(
            Loading(size=Size.md),
            Span("Loading tasks...", cls="ml-2"),
            cls="flex items-center gap-2",
        ),
        role="status",
        aria_live="polite",
        aria_busy="true",
    )
```

**ARIA Live Regions:**

| Type | aria-live | When to Use |
|------|-----------|-------------|
| **Polite** | `polite` | Non-critical updates (success messages, status changes) |
| **Assertive** | `assertive` | Critical errors, time-sensitive alerts |
| **Off** | `off` | Default (no announcement) |

**Additional Attributes:**
- **aria-atomic="true":** Announce entire region (not just changes)
- **role="status":** Polite live region (same as aria-live="polite")
- **role="alert":** Assertive live region (same as aria-live="assertive")

### Pattern 6: Accessible Dropdown Menu

**Purpose:** Keyboard navigable dropdown with ARIA

**Implementation:**

```python
def render_accessible_dropdown(
    trigger_text: str,
    items: list[dict],
    dropdown_id: str = "dropdown-1",
) -> Any:
    """Accessible dropdown menu with keyboard navigation."""
    return Div(
        # Trigger button
        Button(
            trigger_text,
            Span("▼", cls="ml-2", aria_hidden="true"),
            id=f"{dropdown_id}-trigger",
            variant=ButtonT.ghost,
            aria_haspopup="true",
            aria_expanded="false",
            aria_controls=dropdown_id,
            onclick=f"toggleDropdown('{dropdown_id}')",
        ),

        # Dropdown menu
        Ul(
            *[
                Li(
                    A(
                        item["label"],
                        href=item["href"],
                        role="menuitem",
                        tabindex="-1",  # Managed by JS
                    )
                )
                for item in items
            ],
            id=dropdown_id,
            role="menu",
            aria_labelledby=f"{dropdown_id}-trigger",
            cls="menu dropdown-content bg-base-100 rounded-box shadow hidden",
            style="display: none;",
        ),

        x_data="{ open: false }",
        **{"@click.outside": "open = false"},
        cls="dropdown relative",
    )


# JavaScript for keyboard navigation
"""
function toggleDropdown(dropdownId) {
    const dropdown = document.getElementById(dropdownId);
    const trigger = document.getElementById(dropdownId + '-trigger');
    const isOpen = trigger.getAttribute('aria-expanded') === 'true';

    if (isOpen) {
        dropdown.style.display = 'none';
        trigger.setAttribute('aria-expanded', 'false');
    } else {
        dropdown.style.display = 'block';
        trigger.setAttribute('aria-expanded', 'true');

        // Focus first menu item
        const firstItem = dropdown.querySelector('[role="menuitem"]');
        if (firstItem) firstItem.focus();
    }
}

// Arrow key navigation within menu
dropdown.addEventListener('keydown', (e) => {
    const items = Array.from(dropdown.querySelectorAll('[role="menuitem"]'));
    const currentIndex = items.indexOf(document.activeElement);

    if (e.key === 'ArrowDown') {
        e.preventDefault();
        const nextIndex = (currentIndex + 1) % items.length;
        items[nextIndex].focus();
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        const prevIndex = (currentIndex - 1 + items.length) % items.length;
        items[prevIndex].focus();
    } else if (e.key === 'Escape') {
        toggleDropdown(dropdownId);
        trigger.focus();
    }
});
"""
```

**Key Features:**
- **aria-haspopup="true":** Indicates trigger opens menu
- **aria-expanded:** Tracks open/closed state
- **aria-controls:** Links trigger to menu
- **role="menu":** Announces as menu to screen readers
- **Arrow keys:** Navigate menu items
- **Escape:** Closes menu, returns focus to trigger

### Pattern 7: Progress Indicators

**Purpose:** Announce progress to screen readers

**Implementation:**

```python
# Determinate progress (known duration)
def render_progress_bar(value: int, max_value: int = 100, label: str = "") -> Any:
    """Progress bar with ARIA attributes."""
    return Div(
        P(label, id="progress-label", cls="text-sm mb-2") if label else None,
        Div(
            Div(
                cls="h-2 bg-primary rounded-full transition-all",
                style=f"width: {value}%",
            ),
            role="progressbar",
            aria_valuenow=str(value),
            aria_valuemin="0",
            aria_valuemax=str(max_value),
            aria_labelledby="progress-label" if label else None,
            cls="w-full bg-base-300 rounded-full h-2",
        ),
        Span(f"{value}%", cls="text-xs text-base-content/70 mt-1"),
    )


# Indeterminate progress (unknown duration)
def render_loading_spinner(label: str = "Loading...") -> Any:
    """Loading spinner with screen reader announcement."""
    return Div(
        Loading(size=Size.md, aria_hidden="true"),  # Decorative
        Span(label, cls="sr-only"),  # Screen reader only
        role="status",
        aria_live="polite",
        cls="flex items-center gap-2",
    )
```

**ARIA Progressbar Attributes:**
- **role="progressbar":** Announces as progress indicator
- **aria-valuenow:** Current value
- **aria-valuemin/max:** Range (typically 0-100)
- **aria-label or aria-labelledby:** Description of what's loading

### Pattern 8: Tab Panel Component

**Purpose:** Accessible tabbed interface with keyboard navigation

**Implementation:**

```python
def render_tab_panel(
    tabs: list[dict],
    active_tab: str,
    panel_id: str = "tab-panel-1",
) -> Any:
    """Accessible tab panel with ARIA."""
    return Div(
        # Tab list
        Div(
            *[
                Button(
                    tab["label"],
                    id=f"{panel_id}-tab-{tab['id']}",
                    role="tab",
                    aria_selected="true" if tab["id"] == active_tab else "false",
                    aria_controls=f"{panel_id}-panel-{tab['id']}",
                    tabindex="0" if tab["id"] == active_tab else "-1",
                    cls=f"tab {'tab-active' if tab['id'] == active_tab else ''}",
                    onclick=f"switchTab('{panel_id}', '{tab['id']}')",
                )
                for tab in tabs
            ],
            role="tablist",
            aria_label="Task views",
            cls="tabs tabs-boxed",
        ),

        # Tab panels
        *[
            Div(
                tab["content"],
                id=f"{panel_id}-panel-{tab['id']}",
                role="tabpanel",
                aria_labelledby=f"{panel_id}-tab-{tab['id']}",
                tabindex="0",
                cls="mt-4",
                style="display: block;" if tab["id"] == active_tab else "display: none;",
            )
            for tab in tabs
        ],
    )


# JavaScript for tab switching
"""
function switchTab(panelId, tabId) {
    // Update aria-selected on tabs
    const tabs = document.querySelectorAll(`[id^="${panelId}-tab-"]`);
    tabs.forEach(tab => {
        const isActive = tab.id === `${panelId}-tab-${tabId}`;
        tab.setAttribute('aria-selected', isActive);
        tab.setAttribute('tabindex', isActive ? '0' : '-1');
        tab.classList.toggle('tab-active', isActive);
    });

    // Show/hide panels
    const panels = document.querySelectorAll(`[id^="${panelId}-panel-"]`);
    panels.forEach(panel => {
        const isActive = panel.id === `${panelId}-panel-${tabId}`;
        panel.style.display = isActive ? 'block' : 'none';
    });
}

// Arrow key navigation
tablist.addEventListener('keydown', (e) => {
    const tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));
    const currentIndex = tabs.indexOf(document.activeElement);

    if (e.key === 'ArrowRight') {
        e.preventDefault();
        const nextIndex = (currentIndex + 1) % tabs.length;
        tabs[nextIndex].click();
        tabs[nextIndex].focus();
    } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        const prevIndex = (currentIndex - 1 + tabs.length) % tabs.length;
        tabs[prevIndex].click();
        tabs[prevIndex].focus();
    }
});
"""
```

**Key Features:**
- **role="tablist":** Container for tabs
- **role="tab":** Individual tab button
- **role="tabpanel":** Content panel
- **aria-selected:** Indicates active tab
- **aria-controls:** Links tab to panel
- **Arrow keys:** Navigate between tabs

## Real-World Examples

### Example 1: SKUEL Sidebar Navigation (Accessible Navigation)

**File:** `/home/mike/skuel/app/ui/patterns/sidebar.py` (unified sidebar), `/home/mike/skuel/app/ui/activities/sidebar.py` (Activities), `/home/mike/skuel/app/ui/study/sidebar.py` (Study)

**Accessible features:**

```python
def _domain_menu_item(domain: ProfileDomainItem, is_active: bool) -> "FT":
    """Accessible domain navigation item."""
    active_cls = "menu-active" if is_active else ""

    return Li(
        Anchor(
            Span(domain.icon, cls="text-lg", aria_hidden="true"),  # Decorative emoji
            Span(domain.name, cls="flex-1"),  # Screen reader reads name
            Div(
                _count_badge(domain.count, domain.active_count),
                _status_badge(domain.status),
                cls="flex items-center gap-2",
                aria_hidden="true",  # Badges are visual only
            ),
            href=domain.href,
            cls=f"flex items-center gap-2 {active_cls}",
            aria_current="page" if is_active else None,  # Marks active page
        )
    )
```

**Why accessible:**
- **aria-hidden on decorative content:** Emojis and badges not announced
- **aria-current="page":** Screen reader announces "current page"
- **Semantic `<a>` for links:** Native keyboard support
- **Focus visible:** MonsterUI menu items have built-in focus styles

### Example 2: Task Form with Validation

**File:** `/home/mike/skuel/app/adapters/inbound/tasks_ui.py`

**Accessible form:**

```python
FormControl(
    Label(
        LabelText("Title "),
        Span("*", cls="text-error", aria_label="required"),
        for_="task-title-input",
    ),
    Input(
        type="text",
        name="title",
        id="task-title-input",
        placeholder="What needs to be done?",
        required=True,
        aria_required="true",
        aria_describedby="title-help",
        maxlength=200,
        autofocus=True,
        cls="input input-bordered w-full",
    ),
    P(
        "Enter a clear, actionable task title (max 200 characters).",
        id="title-help",
        cls="text-sm text-base-content/70 mt-1",
    ),
)
```

**Why accessible:**
- **for attribute:** Links label to input
- **aria-required:** Announces required field
- **aria-describedby:** Links help text to input
- **autofocus:** Keyboard users start typing immediately
- **maxlength:** Prevents over-length input client-side

## Common Mistakes & Anti-Patterns

### Mistake 1: Div/Span as Button Without ARIA

```python
# ❌ BAD: No keyboard support, no semantic meaning
Div(
    "Delete",
    onclick="deleteTask()",
    cls="btn btn-error",
)

# ✅ GOOD: Semantic button element
Button(
    "Delete",
    variant=ButtonT.error,
    onclick="deleteTask()",
    type="button",
)
```

### Mistake 2: Missing Label for Input

```python
# ❌ BAD: Input without label (screen reader doesn't know purpose)
Input(type="text", name="email", placeholder="Email")

# ✅ GOOD: Proper label association
FormControl(
    Label(LabelText("Email Address"), for_="email-input"),
    Input(type="email", name="email", id="email-input"),
)
```

### Mistake 3: Decorative Icons Without aria-hidden

```python
# ❌ BAD: Screen reader announces "trash can emoji" (confusing)
Button(
    "🗑️ Delete",
    variant=ButtonT.error,
)

# ✅ GOOD: Icon hidden from screen readers
Button(
    Span("🗑️", aria_hidden="true"),
    " Delete",
    variant=ButtonT.error,
)
```

### Mistake 4: Poor Color Contrast

```python
# ❌ BAD: Light gray on white (fails WCAG)
P("Secondary text", cls="text-gray-300")

# ✅ GOOD: MonsterUI semantic colors (guaranteed contrast)
P("Secondary text", cls="text-base-content/70")
```

### Mistake 5: No Focus Trap in Modal

```javascript
// ❌ BAD: Can tab outside modal to background
function openModal(modalId) {
    document.getElementById(modalId).classList.add('modal-open');
}

// ✅ GOOD: Focus trapped within modal
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.classList.add('modal-open');
    trapFocus(modal);  // Prevent tabbing outside
}
```

### Mistake 6: Missing Live Region for Dynamic Content

```python
# ❌ BAD: Task added, but screen reader not notified
def add_task_to_list(task):
    return Div(
        TaskCard(task),
        id="task-list",
    )

# ✅ GOOD: Announce task added
def add_task_to_list(task):
    return Div(
        TaskCard(task),
        # Live region announcement
        Div(
            f"Task '{task.title}' added to list.",
            role="status",
            aria_live="polite",
            cls="sr-only",  # Screen reader only
        ),
        id="task-list",
    )
```

## Testing & Verification Checklist

### Keyboard Navigation Tests

- [ ] **Tab order:** Logical flow (left-to-right, top-to-bottom)
- [ ] **Focus visible:** All interactive elements show focus indicator
- [ ] **Enter/Space:** Activate buttons and links
- [ ] **Escape:** Closes modals, dropdowns, menus
- [ ] **Arrow keys:** Navigate within menus, tabs, radio groups
- [ ] **Skip links:** Functional and visible on focus

### Screen Reader Tests

Test with at least one screen reader:
- **NVDA** (Windows, free)
- **JAWS** (Windows, commercial)
- **VoiceOver** (macOS/iOS, built-in)
- **TalkBack** (Android, built-in)

- [ ] **Headings:** Proper hierarchy (H1 → H2 → H3, no skips)
- [ ] **Landmarks:** nav, main, section, footer announced
- [ ] **Form labels:** All inputs have associated labels
- [ ] **Button text:** Descriptive (not "Click here" or "Submit")
- [ ] **Alt text:** Images have descriptive alt (decorative: aria-hidden)
- [ ] **Live regions:** Dynamic content announced
- [ ] **ARIA states:** Expanded/collapsed, selected, current page

### Visual Tests

- [ ] **Color contrast:** All text passes 4.5:1 (3:1 for large text)
- [ ] **Text resize:** Readable at 200% zoom (no text cutoff)
- [ ] **Focus indicators:** Visible at all times (not removed by CSS)
- [ ] **Color alone:** Not sole means of conveying information

### Automated Tests

Run Lighthouse Accessibility audit:

```bash
# Chrome DevTools → Lighthouse → Accessibility
# Target: 100 score (or 95+ with documented exceptions)
```

Use axe DevTools extension:
- Install: https://www.deque.com/axe/devtools/
- Run audit on each page type
- Fix all critical and serious issues

## Related Documentation

### SKUEL Documentation

- `/docs/patterns/UI_COMPONENT_PATTERNS.md` - Semantic component patterns
- `/ui/layouts/base_page.py` - Accessible page structure
- `/ui/patterns/sidebar.py` - Accessible sidebar navigation (unified component)

### External Resources

- **WCAG 2.1 Guidelines:** https://www.w3.org/WAI/WCAG21/quickref/
- **ARIA Practices:** https://www.w3.org/WAI/ARIA/apg/
- **WebAIM Contrast Checker:** https://webaim.org/resources/contrastchecker/
- **Screen Reader Testing:** https://www.nvaccess.org/ (NVDA)

## See Also

- `html-htmx` - For semantic HTML structure
- `html-navigation` - For accessible navigation patterns
- `daisyui` - For accessible component styling
- `skuel-form-patterns` - For accessible form patterns
- `js-alpine` - For accessible interactive components
