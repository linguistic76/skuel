# DaisyUI 5 CSS Variables Guide

**Purpose:** Prevent CSS variable naming errors and OKLCH color format confusion

**Version:** DaisyUI 5.x (SKUEL uses DaisyUI 5)

---

## DaisyUI 5 vs DaisyUI 4 Variable Naming

**CRITICAL:** DaisyUI 5 changed ALL CSS variable names from short codes to descriptive names.

| DaisyUI 4 (OLD) | DaisyUI 5 (NEW) | Usage |
|-----------------|-----------------|-------|
| `--p` | `--color-primary` | Primary action color (buttons, links) |
| `--pc` | `--color-primary-content` | Text/icons on primary background |
| `--s` | `--color-secondary` | Secondary action color |
| `--sc` | `--color-secondary-content` | Text/icons on secondary background |
| `--a` | `--color-accent` | Accent/highlight color |
| `--ac` | `--color-accent-content` | Text/icons on accent background |
| `--n` | `--color-neutral` | Neutral UI elements |
| `--nc` | `--color-neutral-content` | Text/icons on neutral background |
| `--b1` | `--color-base-100` | Page background (lightest) |
| `--b2` | `--color-base-200` | Component background (cards, panels) |
| `--b3` | `--color-base-300` | Component background (deeper) |
| `--bc` | `--color-base-content` | Text on base colors |
| `--in` | `--color-info` | Info state color |
| `--inc` | `--color-info-content` | Text/icons on info background |
| `--su` | `--color-success` | Success state color |
| `--suc` | `--color-success-content` | Text/icons on success background |
| `--wa` | `--color-warning` | Warning state color |
| `--wac` | `--color-warning-content` | Text/icons on warning background |
| `--er` | `--color-error` | Error state color |
| `--erc` | `--color-error-content` | Text/icons on error background |

**Migration Rule:** If you see `--p`, `--b1`, `--bc` in old code, update to `--color-primary`, `--color-base-100`, `--color-base-content`.

---

## OKLCH Color Format

**Format:** `oklch(L% C H [/ alpha])`

DaisyUI 5 stores colors as OKLCH values (not hex, rgb, or hsl).

### OKLCH Components

| Component | Range | Description | Example |
|-----------|-------|-------------|---------|
| **L** (Lightness) | 0-100% | Perceived brightness | `50%` = medium brightness |
| **C** (Chroma) | 0-0.4 | Color intensity/saturation | `0.2` = vibrant, `0.05` = muted |
| **H** (Hue) | 0-360° | Color angle on color wheel | `240°` = blue, `120°` = green |
| **alpha** | 0-1 | Opacity (optional) | `0.5` = 50% transparent |

### Color Wheel Reference

```
  0° = Red
 30° = Orange
 60° = Yellow
120° = Green
180° = Cyan
240° = Blue
300° = Magenta
360° = Red (full circle)
```

### Example OKLCH Values

```css
/* Bright blue */
oklch(60% 0.25 240)

/* Dark muted green */
oklch(30% 0.1 120)

/* Light gray (achromatic - no hue) */
oklch(90% 0 0)

/* Semi-transparent red */
oklch(50% 0.3 0 / 0.5)
```

---

## Using CSS Variables in Custom CSS

### Basic Usage

```css
.custom-card {
  background: oklch(var(--color-base-100));
  border: 1px solid oklch(var(--color-base-300));
  color: oklch(var(--color-base-content));
}
```

**Critical:** DaisyUI variables store ONLY the OKLCH values (e.g., `60% 0.25 240`). You MUST wrap them in `oklch()` to use them.

### With Opacity

```css
.semi-transparent-overlay {
  /* Add opacity with slash notation */
  background: oklch(var(--color-primary) / 0.5); /* 50% opacity */
}

.ghost-button {
  background: oklch(var(--color-primary) / 0.1); /* 10% opacity */
  color: oklch(var(--color-primary));
}
```

### Using @apply with DaisyUI Classes

```css
.custom-button {
  /* Use DaisyUI utility classes - they handle oklch() wrapping */
  @apply bg-primary text-primary-content;
  @apply hover:bg-primary-focus;
}
```

**Why this works:** DaisyUI utilities (`bg-primary`, `text-primary-content`) already wrap variables in `oklch()`.

### Inline Styles (FastHTML/HTML)

```python
# FastHTML
Div(
    content,
    style="background: oklch(var(--color-base-200)); padding: 1rem;"
)

# HTML
<div style="background: oklch(var(--color-base-200)); padding: 1rem;">
  Content
</div>
```

---

## Complete DaisyUI 5 Variable Reference

### Color Variables

#### Semantic Colors
- `--color-primary` - Primary brand color
- `--color-primary-content` - Text on primary
- `--color-secondary` - Secondary brand color
- `--color-secondary-content` - Text on secondary
- `--color-accent` - Accent/highlight color
- `--color-accent-content` - Text on accent
- `--color-neutral` - Neutral UI elements
- `--color-neutral-content` - Text on neutral

#### Base Colors (Backgrounds)
- `--color-base-100` - Page background (lightest)
- `--color-base-200` - Card/panel background (medium)
- `--color-base-300` - Deeper background (darkest base)
- `--color-base-content` - Text on any base color

#### State Colors
- `--color-info` / `--color-info-content` - Info messages
- `--color-success` / `--color-success-content` - Success messages
- `--color-warning` / `--color-warning-content` - Warning messages
- `--color-error` / `--color-error-content` - Error messages

### Non-Color Variables

#### Border Radius
- `--rounded-box` - Card/container radius (e.g., `1rem`)
- `--rounded-btn` - Button radius (e.g., `0.5rem`)
- `--rounded-badge` - Badge radius (e.g., `1.9rem`)

#### Animation
- `--animation-btn` - Button click animation duration
- `--animation-input` - Input focus animation duration

#### Other
- `--btn-focus-scale` - Button scale on focus (e.g., `0.95`)
- `--border-btn` - Button border width (e.g., `1px`)
- `--tab-border` - Tab border width
- `--tab-radius` - Tab border radius

---

## Common Pitfalls

### ❌ Using Old DaisyUI 4 Variable Names

```css
/* WRONG - DaisyUI 4 syntax */
.card {
  background: oklch(var(--b1));
  color: oklch(var(--bc));
}
```

```css
/* CORRECT - DaisyUI 5 syntax */
.card {
  background: oklch(var(--color-base-100));
  color: oklch(var(--color-base-content));
}
```

### ❌ Forgetting oklch() Wrapper

```css
/* WRONG - Variable stores ONLY "60% 0.25 240" */
.card {
  background: var(--color-base-100);
}
```

```css
/* CORRECT - Wrap in oklch() */
.card {
  background: oklch(var(--color-base-100));
}
```

### ❌ Using Hex/RGB Instead of Variables

```css
/* WRONG - Hardcoded color, doesn't support themes */
.card {
  background: #ffffff;
  color: #1a1a1a;
}
```

```css
/* CORRECT - Uses theme variables */
.card {
  background: oklch(var(--color-base-100));
  color: oklch(var(--color-base-content));
}
```

### ❌ Incorrect Opacity Syntax

```css
/* WRONG - Can't use rgba() with oklch */
.overlay {
  background: rgba(var(--color-primary), 0.5);
}
```

```css
/* CORRECT - Use slash notation */
.overlay {
  background: oklch(var(--color-primary) / 0.5);
}
```

---

## Quick Reference: When to Use What

| Need | Use This | Example |
|------|----------|---------|
| Page background | `bg-base-100` utility | `class="bg-base-100"` |
| Card background | `bg-base-200` utility | `class="bg-base-200"` |
| Custom CSS background | Variable + oklch() | `background: oklch(var(--color-base-100));` |
| Semi-transparent overlay | Variable + opacity | `background: oklch(var(--color-primary) / 0.5);` |
| Button color | DaisyUI component | `class="btn btn-primary"` |
| Text color | `text-base-content` utility | `class="text-base-content"` |

---

## Debugging Theme Colors

### View All Active Variables

```javascript
// In browser console
const styles = getComputedStyle(document.documentElement);
console.log('Primary:', styles.getPropertyValue('--color-primary'));
console.log('Base-100:', styles.getPropertyValue('--color-base-100'));
```

### Test OKLCH Values

```html
<!-- Add to page temporarily -->
<div style="background: oklch(60% 0.25 240); padding: 2rem; color: white;">
  Test OKLCH: oklch(60% 0.25 240)
</div>
```

---

## Related Guides

- [theme-application-guide.md](theme-application-guide.md) - Where to place data-theme, cascading rules
- [../ux-consistency-checklist.md](../ux-consistency-checklist.md) - Pre-commit UX verification
- [SKILL.md](SKILL.md) - Complete DaisyUI component reference
