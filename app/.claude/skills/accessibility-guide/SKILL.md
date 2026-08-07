---
name: accessibility-guide
description: Expert guide for building accessible web applications following WCAG standards. Use when implementing keyboard navigation, screen reader support, ARIA labels, focus management, semantic HTML, or when the user mentions accessibility, a11y, WCAG, screen readers, or inclusive design.
allowed-tools: Read, Grep, Glob
related_skills:
- ui-browser
- skuel-ui
- ui-css
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

**SKUEL Semantic Color Tokens** (defined in `static/css/input.css` — Tailwind v4 CSS-first config):
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

**SKUEL components:** All interactive `ui.components` (Button, Input, Select, etc.) ship with built-in focus styles.

### 6. Touch Target Size (WCAG 2.5.5)

**All interactive elements must have a minimum touch target of 44x44 CSS pixels:**

| Element | Tailwind Class | Size |
|---------|---------------|------|
| Navbar buttons (search, notifications, avatar, menu, logout) | `size-11` | 44px |
| Sidebar nav items | `min-h-[44px]` | 44px minimum height |
| Form inputs | Default Tailwind | 44px+ (built-in) |

**SKUEL Convention:** Outer interactive element gets `size-11` (44px); inner decorative element (e.g., avatar circle) stays `size-8` (32px). The touch target is the outer element.

```python
# Navbar icon link pattern
A(
    Div(icon, cls="size-8 rounded-full ..."),  # Visual: 32px
    href="/path",
    cls="inline-flex items-center justify-center size-11 rounded-full hover:bg-accent",  # Touch: 44px
)
```

## Implementation Patterns & Real-World Examples

For the full, copy-paste implementation patterns — accessible button vs link, form labels & descriptions, modal dialog focus trapping, skip links, live-region announcements, accessible dropdown menus, progress indicators, and tab panels — plus the two real-world SKUEL examples (sidebar navigation, task form) — see **[reference.md](reference.md)**.

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

# ✅ GOOD: LabelInput handles label association automatically
from ui.forms import LabelInput
LabelInput("Email Address", type="email", name="email")
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

# ✅ GOOD: SKUEL semantic color tokens (guaranteed contrast)
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

- `ui-browser` - For semantic HTML, HTMX, and interactive components
- `skuel-ui` - For navigation and form patterns
- `ui-css` - For accessible component styling
