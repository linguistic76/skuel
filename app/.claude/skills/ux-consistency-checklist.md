# UX Consistency Checklist

**Purpose:** Cross-skill consistency enforcement for all UI code

**Use:** Review this checklist before committing any UI changes (HTML, CSS, components, routes)

---

## Before Committing Any UI Code

### 1. Colors (MonsterUI)

**Check:**
- [ ] Using semantic colors (`bg-base-100`, `text-base-content`, `btn-primary`)?
- [ ] No hardcoded hex/rgb except brand colors or data visualization?
- [ ] No raw Tailwind colors (`bg-blue-600`, `text-gray-900`, `bg-white`)?
- [ ] All interactive elements use semantic colors (not hardcoded)?

**Quick Test:**
```bash
# Find hardcoded colors
grep -r "bg-white\|text-gray-\|bg-gray-" adapters/inbound/ ui/
```

**Fix:**
```python
# BAD
Div(cls="bg-white text-gray-900")

# GOOD
Div(cls="bg-base-100 text-base-content")
```

**See:** [ui-css/SKILL.md](ui-css/SKILL.md#critical-avoid-hardcoded-colors)

---

### 2. Theme (MonsterUI)

**Check:**
- [ ] Dark mode uses `dark` class on `<html>` element (MonsterUI class-based dark mode)?
- [ ] Theme script runs before CSS loads (FOUC prevention)?
- [ ] Theme preference saved to localStorage (`skuel-theme` key)?

**Quick Test:**
```bash
# Check dark mode toggle works
grep -r "classList.*dark" ui/theme.py
```

**Fix:**
```html
<!-- BAD (old DaisyUI pattern) -->
<html data-theme="dark">

<!-- GOOD (MonsterUI class-based dark mode) -->
<html class="dark">
```

**See:** [ui-css/SKILL.md](ui-css/SKILL.md)

---

### 3. Spacing (SKUEL Tokens + Tailwind)

**Check:**
- [ ] Using SKUEL tokens (`Spacing.PAGE`, `Spacing.SECTION`, `Spacing.CONTENT`)?
- [ ] Standard gaps (4, 6, 8) not random (5, 7, 9)?
- [ ] Form fields use `Spacing.FORM` (space-y-6)?
- [ ] One-off spacing uses Tailwind directly (gap-2, gap-3)?

**Quick Test:**
```bash
# Find non-standard spacing
grep -r "space-y-[135579]\|gap-[135579]" adapters/inbound/ ui/
```

**Fix:**
```python
# BAD - Random spacing
Div(*sections, cls="space-y-5")

# GOOD - Standard token
from ui.tokens import Spacing
Div(*sections, cls=Spacing.SECTION)  # space-y-8
```

**See:** [tailwind-css/design-consistency-guide.md](tailwind-css/design-consistency-guide.md#spacing-scale)

---

### 4. Container Widths (SKUEL Tokens)

**Check:**
- [ ] Using `Container.STANDARD` for most pages?
- [ ] Using `Container.NARROW` for forms/articles?
- [ ] Using `Container.WIDE` for tables/dashboards?
- [ ] Not using custom `max-w-*` values without reason?
- [ ] Container includes responsive padding (`px-6 lg:px-8`)?

**Quick Test:**
```bash
# Find custom max-width values
grep -r "max-w-[0-9xl]\+" adapters/inbound/ | grep -v "Container\."
```

**Fix:**
```python
# BAD - Custom width
Div(content, cls="max-w-5xl mx-auto px-4")

# GOOD - Standard token
from ui.tokens import Container
Div(content, cls=Container.STANDARD)  # max-w-6xl mx-auto px-6 lg:px-8
```

**See:** [tailwind-css/design-consistency-guide.md](tailwind-css/design-consistency-guide.md#container-widths)

---

### 5. Typography (SKUEL Tokens)

**Check:**
- [ ] Using `Typography.H1`, `Typography.H2`, `Typography.H3` for headings?
- [ ] Body text uses `Typography.BODY` or default semantic classes?
- [ ] Consistent font weights (bold for headings, normal for body)?
- [ ] Text color uses `text-base-content` or semantic colors?

**Fix:**
```python
# BAD - Manual typography
H1("Title", cls="text-4xl font-bold text-gray-900")

# GOOD - Typography token
from ui.tokens import Typography
H1("Title", cls=Typography.H1)  # Includes size, weight, color
```

**See:** [tailwind-css/design-consistency-guide.md](tailwind-css/design-consistency-guide.md#typography-scale)

---

### 6. Cards (SKUEL Tokens)

**Check:**
- [ ] Using `Card.STANDARD`, `Card.HOVER`, or `Card.INTERACTIVE`?
- [ ] Not mixing card styles inconsistently across pages?
- [ ] Cards have consistent padding (p-6 standard, p-4 compact)?
- [ ] Card backgrounds use `bg-base-100` or `bg-base-200`?

**Fix:**
```python
# BAD - Manual card styling
Div(content, cls="bg-white p-6 rounded shadow")

# GOOD - Card token
from ui.tokens import Card
Div(content, cls=Card.STANDARD)
```

**See:** [tailwind-css/design-consistency-guide.md](tailwind-css/design-consistency-guide.md#card-styles)

---

### 7. Semantic HTML (HTML Best Practices)

**Check:**
- [ ] Using semantic elements (`<article>`, `<section>`, `<nav>`, `<header>`)?
- [ ] Not using `<div>` for everything?
- [ ] Lists use `<ul>` or `<ol>` (not divs)?
- [ ] Forms use `<form>`, `<label>`, `<input>` properly?

**Fix:**
```html
<!-- BAD - Divs for everything -->
<div>
  <div>Title</div>
  <div>Content</div>
</div>

<!-- GOOD - Semantic HTML -->
<article>
  <h1>Title</h1>
  <p>Content</p>
</article>
```

**See:** [html-htmx/SKILL.md](html-htmx/SKILL.md)

---

### 8. Accessibility (A11y)

**Check:**
- [ ] All images have `alt` attributes?
- [ ] Form inputs have associated `<label>` elements?
- [ ] Buttons have descriptive text (not just icons)?
- [ ] Color contrast meets WCAG AA (4.5:1 for text)?
- [ ] Interactive elements are keyboard accessible?
- [ ] ARIA attributes used where semantic HTML insufficient?

**Quick Test:**
```bash
# Find images without alt
grep -r "<img" adapters/inbound/ ui/ | grep -v "alt="
```

**Fix:**
```python
# BAD - No alt text
Img(src="/logo.png")

# GOOD - Descriptive alt
Img(src="/logo.png", alt="SKUEL logo")
```

---

### 9. Responsive Design (Mobile-First)

**Check:**
- [ ] Mobile-first approach (base styles, then `md:`, `lg:`)?
- [ ] Tested on mobile (375px), tablet (768px), desktop (1024px+)?
- [ ] No horizontal scroll on small screens?
- [ ] Touch targets at least 44x44px on mobile?
- [ ] Text readable without zooming (min 16px base)?

**Fix:**
```html
<!-- BAD - Desktop-first -->
<div class="text-lg sm:text-base">

<!-- GOOD - Mobile-first -->
<div class="text-base lg:text-lg">
```

---

### 10. HTMX Updates (Hypermedia)

**Check:**
- [ ] HTMX updates use proper `hx-target` and `hx-swap`?
- [ ] Loading states indicated (spinner, disabled button)?
- [ ] Error states handled gracefully?
- [ ] Progressive enhancement (works without JS)?

**Fix:**
```python
# GOOD - Proper HTMX pattern
Button(
    "Save",
    hx_post="/api/save",
    hx_target="#result",
    hx_swap="outerHTML",
    hx_indicator="#spinner",
    variant=ButtonT.primary
)
```

**See:** [html-htmx/SKILL.md](html-htmx/SKILL.md)

---

## Automated Checks

Run these before committing:

### Find All Violations

```bash
# Hardcoded colors
echo "=== Hardcoded Colors ==="
grep -r "bg-white\|text-gray-\|bg-gray-\|bg-blue-\|bg-red-" adapters/inbound/ ui/ | grep -v chart

# Custom container widths
echo "=== Custom Containers ==="
grep -r "max-w-[0-9xl]\+" adapters/inbound/ ui/ | grep -v "Container\."

# Non-standard spacing
echo "=== Non-Standard Spacing ==="
grep -r "space-y-[135579]\|gap-[135579]" adapters/inbound/ ui/

# Missing alt attributes
echo "=== Missing Alt Text ==="
grep -r "<img" adapters/inbound/ ui/ | grep -v "alt="

# Theme on wrong element
echo "=== Theme on Body (should be HTML) ==="
grep -r "Body.*data-theme" adapters/inbound/
```

### Full Check Script

```bash
#!/bin/bash
# Save as .claude/scripts/ux-check.sh

echo "Running UX Consistency Checks..."
echo

errors=0

# Check 1: Hardcoded colors
if grep -rq "bg-white\|text-gray-[0-9]\|bg-gray-[0-9]" adapters/inbound/ ui/ 2>/dev/null; then
    echo "❌ Found hardcoded colors (use MonsterUI semantic colors)"
    grep -rn "bg-white\|text-gray-[0-9]\|bg-gray-[0-9]" adapters/inbound/ ui/ | head -5
    errors=$((errors+1))
else
    echo "✅ No hardcoded colors"
fi

# Check 2: Custom containers
if grep -rq "max-w-[0-9]" adapters/inbound/ ui/ 2>/dev/null | grep -vq "Container\."; then
    echo "❌ Found custom container widths (use Container tokens)"
    grep -rn "max-w-[0-9]" adapters/inbound/ ui/ | grep -v "Container\." | head -5
    errors=$((errors+1))
else
    echo "✅ Using Container tokens"
fi

# Check 3: Non-standard spacing
if grep -rq "space-y-[135579]\|gap-[135579]" adapters/inbound/ ui/ 2>/dev/null; then
    echo "❌ Found non-standard spacing (use 4, 6, 8)"
    grep -rn "space-y-[135579]\|gap-[135579]" adapters/inbound/ ui/ | head -5
    errors=$((errors+1))
else
    echo "✅ Using standard spacing"
fi

echo
if [ $errors -eq 0 ]; then
    echo "✅ All UX consistency checks passed!"
    exit 0
else
    echo "❌ Found $errors issue(s). Review output above."
    exit 1
fi
```

**Usage:**
```bash
chmod +x .claude/scripts/ux-check.sh
./.claude/scripts/ux-check.sh
```

---

## Quick Reference

### Decision Matrix

| Need | Use This | Not This |
|------|----------|----------|
| Button | `Button(variant=ButtonT.primary)` | `bg-blue-600` |
| Background | `bg-base-100` | `bg-white` |
| Text | `text-base-content` | `text-gray-900` |
| Container | `Container.STANDARD` | `max-w-6xl` |
| Section spacing | `Spacing.SECTION` | `space-y-8` |
| Page padding | `Spacing.PAGE` | `p-6` |
| Card | `Card.STANDARD` | `bg-white p-6 rounded` |
| Heading | `Typography.H2` | `text-3xl font-bold` |

### Import Statement

```python
# At top of route/component file
from ui.tokens import Spacing, Container, Card, Typography
```

---

## Priority Levels

When fixing violations, address in this order:

1. **CRITICAL (Fix Immediately):**
   - Hardcoded colors → Semantic colors
   - Theme on `<body>` → Theme on `<html>`
   - Missing accessibility features

2. **HIGH (Fix Before Merge):**
   - Custom containers → Container tokens
   - Inconsistent spacing → Spacing tokens
   - Non-semantic HTML → Semantic elements

3. **MEDIUM (Fix When Refactoring):**
   - Manual cards → Card tokens
   - Manual typography → Typography tokens
   - Missing responsive breakpoints

4. **LOW (Optional Optimization):**
   - One-off spacing tweaks
   - Minor layout improvements

---

## Related Guides

### By Skill
- [ui-css/SKILL.md](ui-css/SKILL.md) - MonsterUI components and semantic colors
- [ui-css/SKILL.md](ui-css/SKILL.md) - CSS variables and OKLCH
- [ui-css/SKILL.md](ui-css/SKILL.md) - Theme patterns
- [tailwind-css/SKILL.md](tailwind-css/SKILL.md) - Tailwind utilities
- [tailwind-css/design-consistency-guide.md](tailwind-css/design-consistency-guide.md) - SKUEL tokens
- [html-htmx/SKILL.md](html-htmx/SKILL.md) - Semantic HTML and HTMX

### By Topic
- **Colors:** [ui-css/SKILL.md#critical-avoid-hardcoded-colors](ui-css/SKILL.md)
- **Theme:** [ui-css/SKILL.md](ui-css/SKILL.md)
- **Spacing:** [tailwind-css/design-consistency-guide.md#spacing-scale](tailwind-css/design-consistency-guide.md)
- **Containers:** [tailwind-css/design-consistency-guide.md#container-widths](tailwind-css/design-consistency-guide.md)
- **Tokens:** [tailwind-css/design-consistency-guide.md#skuel-design-token-system](tailwind-css/design-consistency-guide.md)
