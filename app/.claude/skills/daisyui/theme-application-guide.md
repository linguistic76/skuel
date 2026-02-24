# DaisyUI Theme Application Guide

**Purpose:** Prevent theme cascading bugs, FOUC (Flash of Unstyled Content), and theme-related issues

**Version:** DaisyUI 5.x (SKUEL uses DaisyUI 5)

---

## Where to Place data-theme

### Global Theme (Recommended)

**Location:** `<html>` element

```html
<html lang="en" data-theme="light">
  <head>...</head>
  <body>
    <!-- Entire app uses "light" theme -->
    <div class="bg-base-100 text-base-content">
      All content automatically styled with light theme
    </div>
  </body>
</html>
```

**Pros:**
- Single source of truth
- No cascading complexity
- Semantic classes work everywhere
- Best performance (one theme scope)

**Cons:**
- Cannot have mixed themes on same page

**When to use:** 99% of cases (including SKUEL)

---

### Nested Themes (Advanced)

**Use case:** Different theme for sidebar, modal, or embedded widget

```html
<html lang="en" data-theme="light">
  <body>
    <!-- Main content uses light theme -->
    <div class="bg-base-100 text-base-content p-6">
      Light content here
    </div>

    <!-- Sidebar uses dark theme -->
    <aside data-theme="dark" class="bg-base-100 text-base-content p-4">
      Dark sidebar here
    </aside>
  </body>
</html>
```

**CRITICAL:** When nesting themes, you MUST reapply semantic classes (`bg-base-100`, `text-base-content`) inside the nested theme container.

#### Why Reapply Classes?

DaisyUI semantic classes (`bg-base-100`) compile to CSS variables at build time:

```css
.bg-base-100 {
  background-color: oklch(var(--color-base-100));
}
```

When you change `data-theme`, the VARIABLE values change, but the classes don't automatically reapply. You must add the class to the themed container.

#### Nested Theme Pattern

```html
<html data-theme="light">
  <!-- Main area - light theme -->
  <main class="bg-base-100">
    <h1 class="text-base-content">Light content</h1>
  </main>

  <!-- Nested area - dark theme -->
  <aside data-theme="dark" class="bg-base-100 text-base-content">
    <!-- MUST reapply bg-base-100 and text-base-content -->
    <h2>Dark sidebar</h2>
    <div class="bg-base-200 p-4">Card in dark theme</div>
  </aside>
</html>
```

---

### ❌ Common Mistake: Theme on <body>

```html
<!-- WRONG - Theme on body instead of html -->
<html lang="en">
  <body data-theme="light">
    <div class="bg-base-100">Content</div>
  </body>
</html>
```

**Why this is wrong:**
- Some CSS frameworks scope to `:root` (html element)
- DaisyUI expects `data-theme` on `<html>`
- Can cause inconsistent styling

**Correct:**

```html
<!-- CORRECT - Theme on html -->
<html lang="en" data-theme="light">
  <body>
    <div class="bg-base-100">Content</div>
  </body>
</html>
```

---

## Theme Cascading Rules

### How Cascading Works

1. DaisyUI looks for nearest ancestor with `data-theme`
2. Applies that theme's CSS variables
3. All semantic classes use those variables

```html
<html data-theme="light">
  <!-- Uses light theme -->
  <div class="bg-base-100">Light background</div>

  <section data-theme="dark" class="bg-base-100">
    <!-- Uses dark theme (overrides light) -->
    Dark background

    <div data-theme="light" class="bg-base-100">
      <!-- Uses light theme (overrides dark) -->
      Nested light background
    </div>
  </section>
</html>
```

### Inheritance Rules

| Element | Inherits From | Result |
|---------|---------------|--------|
| No `data-theme` | Nearest ancestor with `data-theme` | Uses ancestor theme |
| Has `data-theme` | Itself | Uses own theme, ignores ancestors |
| `<html>` has `data-theme` | Nothing | Global theme |

---

## Preventing FOUC (Flash of Unstyled Content)

### The Problem

If theme is set via JavaScript AFTER page loads, users see a flash of default theme:

```html
<!-- BAD - Theme set after page renders -->
<html lang="en">
  <head>
    <link rel="stylesheet" href="styles.css">
  </head>
  <body>
    <div class="bg-base-100">Content</div>

    <script>
      // Runs AFTER content renders - FOUC!
      document.documentElement.setAttribute('data-theme', 'dark');
    </script>
  </body>
</html>
```

**Result:** User sees light theme for split second, then dark theme appears.

---

### The Solution: Inline Blocking Script

**Pattern:** Run theme script in `<head>` BEFORE CSS loads

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My App</title>

    <!-- CRITICAL: Set theme BEFORE CSS loads -->
    <script>
      (function() {
        // Get saved theme or use system preference
        const savedTheme = localStorage.getItem('theme');
        const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches
          ? 'dark'
          : 'light';
        const theme = savedTheme || systemTheme;

        // Set immediately (BEFORE page renders)
        document.documentElement.setAttribute('data-theme', theme);
      })();
    </script>

    <!-- CSS loads AFTER theme is set -->
    <link rel="stylesheet" href="styles.css">
  </head>
  <body>
    <!-- Content renders with correct theme -->
    <div class="bg-base-100 text-base-content">
      No FOUC!
    </div>
  </body>
</html>
```

**Why this works:**
1. Script runs synchronously in `<head>`
2. Sets `data-theme` BEFORE browser parses CSS
3. CSS variables applied correctly on first render
4. No theme flash

---

## Programmatic Theme Switching

### Basic Theme Toggle

```javascript
// Toggle between light and dark
function toggleTheme() {
  const html = document.documentElement;
  const currentTheme = html.getAttribute('data-theme');
  const newTheme = currentTheme === 'light' ? 'dark' : 'light';

  html.setAttribute('data-theme', newTheme);
  localStorage.setItem('theme', newTheme);
}

// Usage
document.getElementById('theme-toggle').addEventListener('click', toggleTheme);
```

### Multi-Theme Selector

```javascript
function setTheme(themeName) {
  document.documentElement.setAttribute('data-theme', themeName);
  localStorage.setItem('theme', themeName);
}

// Usage
setTheme('cupcake');  // DaisyUI has 30+ built-in themes
setTheme('dracula');
setTheme('light');
```

### System Preference Detection

```javascript
function getSystemTheme() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light';
}

// Auto-switch when system preference changes
window.matchMedia('(prefers-color-scheme: dark)')
  .addEventListener('change', (e) => {
    const newTheme = e.matches ? 'dark' : 'light';
    setTheme(newTheme);
  });
```

### Complete Theme Management

```javascript
// Initialize theme on page load
(function initTheme() {
  const savedTheme = localStorage.getItem('theme');
  const systemTheme = getSystemTheme();
  const theme = savedTheme || systemTheme;

  document.documentElement.setAttribute('data-theme', theme);
})();

// Toggle function
function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const newTheme = current === 'light' ? 'dark' : 'light';
  setTheme(newTheme);
}

// Setter
function setTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('theme', theme);
}

// System preference helper
function getSystemTheme() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light';
}
```

---

## SKUEL-Specific Patterns

### FastHTML Base Template

```python
# /ui/layouts/base_page.py (or similar)

def theme_script():
    """Inline blocking script to prevent FOUC"""
    return Script("""
        (function() {
            const theme = localStorage.getItem('theme') || 'light';
            document.documentElement.setAttribute('data-theme', theme);
        })();
    """)

def base_html(*content):
    return Html(
        Head(
            Meta(charset="UTF-8"),
            Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
            Title("SKUEL"),
            theme_script(),  # BEFORE CSS
            Link(rel="stylesheet", href="/static/css/styles.css"),
        ),
        Body(*content),
        lang="en",
        # data-theme set by JavaScript, not server-side
    )
```

### Theme Toggle Component

```python
# /ui/layouts/base_page.py

def ThemeToggle():
    return Button(
        "Toggle Theme",
        cls="btn btn-ghost",
        onclick="toggleTheme()",
    )
```

### Global Theme Script

```javascript
// /static/js/theme.js

window.toggleTheme = function() {
  const html = document.documentElement;
  const current = html.getAttribute('data-theme');
  const newTheme = current === 'light' ? 'dark' : 'light';

  html.setAttribute('data-theme', newTheme);
  localStorage.setItem('theme', newTheme);
};
```

---

## Common Pitfalls

### ❌ Setting Theme After CSS Loads

```html
<!-- WRONG - FOUC will occur -->
<head>
  <link rel="stylesheet" href="styles.css">
  <script>
    document.documentElement.setAttribute('data-theme', 'dark');
  </script>
</head>
```

```html
<!-- CORRECT - Theme set first -->
<head>
  <script>
    document.documentElement.setAttribute('data-theme', 'dark');
  </script>
  <link rel="stylesheet" href="styles.css">
</head>
```

### ❌ Forgetting to Reapply Classes on Nested Themes

```html
<!-- WRONG - bg-base-100 not reapplied -->
<html data-theme="light">
  <aside data-theme="dark">
    <!-- Uses LIGHT theme base-100, not dark! -->
    Content here
  </aside>
</html>
```

```html
<!-- CORRECT - Semantic classes reapplied -->
<html data-theme="light">
  <aside data-theme="dark" class="bg-base-100 text-base-content">
    <!-- Uses DARK theme base-100 -->
    Content here
  </aside>
</html>
```

### ❌ Theme on Wrong Element

```html
<!-- WRONG - Theme on body or child element -->
<html>
  <body data-theme="light">...</body>
</html>
```

```html
<!-- CORRECT - Theme on html -->
<html data-theme="light">
  <body>...</body>
</html>
```

### ❌ Not Saving Theme Preference

```javascript
// WRONG - Theme resets on page reload
function toggleTheme() {
  const newTheme = current === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', newTheme);
  // Missing: localStorage.setItem('theme', newTheme);
}
```

```javascript
// CORRECT - Theme persists across reloads
function toggleTheme() {
  const newTheme = current === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', newTheme);
  localStorage.setItem('theme', newTheme); // Persists
}
```

---

## Testing Themes

### Manual Testing Checklist

- [ ] Page loads with correct theme (no FOUC)
- [ ] Theme toggle switches immediately
- [ ] Theme persists after page reload
- [ ] All semantic colors update (base, primary, accent, etc.)
- [ ] Nested themes apply correctly (if used)
- [ ] System preference detection works
- [ ] Theme switch animates smoothly (if transition added)

### Browser DevTools Testing

```javascript
// In console - test theme switching
document.documentElement.setAttribute('data-theme', 'dark');
document.documentElement.setAttribute('data-theme', 'light');
document.documentElement.setAttribute('data-theme', 'cupcake');

// Check localStorage
localStorage.getItem('theme');
localStorage.setItem('theme', 'dark');

// Check CSS variables
getComputedStyle(document.documentElement).getPropertyValue('--color-base-100');
```

---

## Quick Reference

| Task | Implementation |
|------|----------------|
| Global theme | `<html data-theme="light">` |
| Prevent FOUC | Inline script in `<head>` before CSS |
| Toggle theme | `html.setAttribute('data-theme', newTheme)` |
| Save preference | `localStorage.setItem('theme', theme)` |
| Nested theme | Add `data-theme` + reapply semantic classes |
| System preference | `window.matchMedia('(prefers-color-scheme: dark)')` |

---

## Related Guides

- [css-variables-guide.md](css-variables-guide.md) - CSS variable naming, OKLCH format
- [../ux-consistency-checklist.md](../ux-consistency-checklist.md) - Pre-commit UX verification
- [SKILL.md](SKILL.md) - Complete DaisyUI component reference
