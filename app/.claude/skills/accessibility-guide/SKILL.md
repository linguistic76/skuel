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
- `text-foreground` / `text-muted-foreground` on `bg-background` — the theme-aware body pair, redefined for `.dark`
- `text-error` / `text-success` / `text-warning` / `text-info` — fixed hex (red-600, green-600, amber-600, blue-600) that doesn't change in dark mode. On white, measured: `text-error` 4.83:1 and `text-info` 5.17:1 pass AA for body text; `text-success` 3.30:1 and `text-warning` 3.19:1 pass only the 3:1 large-text / UI-component threshold. Use those two for icons, borders, and bold 14pt+ labels, not body text
- A status color on its own fill (`text-error` on `bg-error`) has no contrast at all; pair a status text color with a tint (`bg-error/10`) or with white

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
    outline: 2px solid hsl(var(--ring));
    outline-offset: 2px;
}
```

In FT, the Tailwind utilities are `focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2`, the ones `Button` and `Input` render.

**SKUEL components:** `Button`, `Input` and the other `ui.components` form controls ship with those focus-visible ring classes.

### 6. Touch Target Size (WCAG 2.5.5)

**SKUEL's convention is a 44x44 CSS-pixel minimum touch target** (WCAG 2.1 SC 2.5.5, a Level AAA criterion, which SKUEL adopts):

| Element | Tailwind Class | Size |
|---------|---------------|------|
| Navbar icon buttons (Askesis, Shared, notifications, avatar, sign out) | `size-11` | 44px |
| Sidebar nav items (desktop rows and the section nav) | `min-h-[44px]` | 44px minimum height |
| Form inputs (`Input`, `Select`) | `h-10` | **40px tall** (full width), below the 44px convention; add `min-h-11` where a form is used on touch |

**SKUEL Convention:** Outer interactive element gets `size-11` (44px); inner decorative element (e.g., avatar circle) stays `size-8` (32px). The touch target is the outer element.

```python
# Navbar icon link pattern
A(
    Div(icon, cls="size-8 rounded-full ..."),  # Visual: 32px
    href="/path",
    cls="inline-flex items-center justify-center size-11 rounded-full hover:bg-accent",  # Touch: 44px
)
```

### 7. HTMX Announcements Are Built In

`BasePage` renders one live region, `#live-region` (`role="status"`, `aria-live="polite"`,
`aria-atomic="true"`), and `static/js/skuel.js` announces HTMX traffic into it through
`window.SKUEL.announce(message, priority)`. A route or component rarely needs its own live
region:

- **Mutations announce themselves.** For a non-GET request, the path is matched against
  `ANNOUNCE_ROUTES` (`/create`, `/update`·`/edit`·`/save`, `/delete`·`/remove`, `/complete`,
  `/upload`, `/track`, `/enroll`, `/status`): "Creating..." while in flight, then "Created
  successfully" after the swap. An unmatched mutation says "Loading..." and nothing after.
  GET fragment loads are silent.
- **Override the words** with `data-announce` (success) and `data-announce-loading` on the
  triggering element, or put `data-announce` inside the swapped content.
- **Errors are assertive:** 404 "Item not found", 403 "Permission denied", 400 "Invalid
  request", 5xx "Server error. Please try again later.", a network failure "Network error.
  Please check your connection."
- **`aria-busy`** is set on the request's target while it is in flight.
- **Refusals don't read as success.** A rendered ownership refusal (`X-SKUEL-Refusal:
  rendered`) swaps in, but the success announcement is skipped because
  `event.detail.successful` is false. The banner itself is `role="alert"`
  (`render_error_banner`).

**See:** `/docs/patterns/HTMX_ACCESSIBILITY_PATTERNS.md`

## Implementation Patterns & Real-World Examples

For the full, copy-paste implementation patterns — accessible button vs link, form labels & descriptions, modal dialog focus trapping, skip links, live-region announcements, accessible dropdown menus, progress indicators, and tab panels — plus the two real-world SKUEL examples (sidebar navigation, task form) — see **[reference.md](reference.md)**.

## Common Mistakes & Anti-Patterns

### Mistake 1: Div/Span as Button Without ARIA

```python
# ❌ BAD: No keyboard support, no semantic meaning
Div(
    "Delete",
    onclick="deleteTask()",
    cls="text-destructive cursor-pointer",
)

# ✅ GOOD: Semantic button element (ui.components.Button renders <button>)
Button(
    "Delete",
    cls=ButtonT.destructive,
    type="button",
    hx_post=f"/api/tasks/delete?uid={task.uid}",
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
# ❌ BAD: Screen reader announces "wastebasket" (confusing)
Button(
    "🗑️ Delete",
    cls=ButtonT.destructive,
)

# ✅ GOOD: Icon() is decorative by default (it sets aria-hidden="true" itself)
Button(
    Icon("trash-2", size=16),
    " Delete",
    cls=ButtonT.destructive,
)
```

### Mistake 4: Poor Color Contrast

```python
# ❌ BAD: Light gray on white (fails WCAG)
P("Secondary text", cls="text-gray-300")

# ✅ GOOD: SKUEL's theme-aware secondary-text token
P("Secondary text", cls="text-muted-foreground")
```

### Mistake 5: Assuming AlpineModal Makes a Dialog

`AlpineModal` (`ui/patterns/modal.py`) renders the backdrop, click-outside-to-close,
`x-cloak` and a transition, and nothing else. It sets no `role="dialog"` or `aria-modal`,
doesn't close on Escape, and doesn't move, trap or restore focus. SKUEL doesn't vendor
Alpine's focus plugin, so `x-trap` isn't available either. The caller adds the rest:

```python
Div(
    Button("Delete", x_ref="trigger", **{"@click": "open = true; $nextTick(() => $refs.cancel.focus())"}),
    AlpineModal(
        Div(
            H2("Delete this task?", id="del-title"),
            Button("Cancel", x_ref="cancel", **{"@click": "open = false; $refs.trigger.focus()"}),
            role="dialog", aria_labelledby="del-title",
        ),
        show="open",
        close="open = false; $refs.trigger.focus()",
    ),
    x_data="{ open: false }",
    # guarded: a window listener fires on every Escape, open or not
    **{"@keydown.escape.window": "if (open) { open = false; $refs.trigger.focus() }"},
)
```

Measured with the vendored Alpine 3.14.8: opening focuses Cancel; Escape closes the dialog
and returns focus to the trigger; with the dialog closed, Escape leaves focus where it was.
Tab can still leave the dialog, so the pattern **omits `aria-modal="true"`**. That attribute
tells assistive technology the rest of the page is inert, and here it isn't. Add
`aria-modal` together with a real focus trap or an `inert` background, never before.

### Mistake 6: Hand-Rolling a Live Region SKUEL Already Has

```python
# ❌ BAD: a second live region per fragment — it competes with #live-region, and a
#    region inserted together with its text is often not announced at all
Div(TaskCard(task), Div(f"Task '{task.title}' added.", role="status", aria_live="polite", cls="sr-only"))

# ✅ GOOD: let the built-in announcer say it (section 7): a POST to a /create path
#    announces "Created successfully" by itself. To choose the words, put them on the element
#    that ISSUES the request: for a form submit that is the Form, not its submit button
Form(..., hx_post=create_url, **{"data-announce": "Task added", "data-announce-loading": "Adding task"})
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

- `/docs/patterns/HTMX_ACCESSIBILITY_PATTERNS.md` - The HTMX announcer (`#live-region`, `data-announce`)
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
