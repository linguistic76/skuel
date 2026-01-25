# DaisyUI Themes Guide

## Available Themes

DaisyUI includes 32 built-in themes:

| Theme | Style |
|-------|-------|
| `light` | Default light theme |
| `dark` | Default dark theme |
| `cupcake` | Soft pastel colors |
| `bumblebee` | Yellow accent |
| `emerald` | Green accent |
| `corporate` | Professional blue |
| `synthwave` | 80s neon |
| `retro` | Vintage colors |
| `cyberpunk` | Futuristic yellow/pink |
| `valentine` | Pink romantic |
| `halloween` | Orange/purple spooky |
| `garden` | Natural green |
| `forest` | Dark green |
| `aqua` | Blue aquatic |
| `lofi` | Muted minimal |
| `pastel` | Soft colors |
| `fantasy` | Purple magical |
| `wireframe` | Sketch style |
| `black` | Pure black |
| `luxury` | Gold/black |
| `dracula` | Dark purple |
| `cmyk` | Print colors |
| `autumn` | Warm orange |
| `business` | Professional gray |
| `acid` | Bright lime |
| `lemonade` | Yellow fresh |
| `night` | Deep blue dark |
| `coffee` | Brown warm |
| `winter` | Cool blue |
| `dim` | Dimmed dark |
| `nord` | Nordic colors |
| `sunset` | Orange/purple gradient |

## Configuration

### Enable Specific Themes

```javascript
// tailwind.config.js
module.exports = {
  plugins: [require("daisyui")],
  daisyui: {
    themes: ["light", "dark", "cupcake", "corporate"],
  },
}
```

### Enable All Themes

```javascript
// tailwind.config.js
module.exports = {
  plugins: [require("daisyui")],
  daisyui: {
    themes: true, // All 32 themes
  },
}
```

### Disable All Themes (Only Base)

```javascript
// tailwind.config.js
module.exports = {
  plugins: [require("daisyui")],
  daisyui: {
    themes: false,
  },
}
```

## Applying Themes

### HTML Attribute

```html
<!-- On html element (recommended) -->
<html data-theme="dark">

<!-- On any element (scoped) -->
<div data-theme="cupcake">
  This section uses cupcake theme
</div>
```

### Theme Switcher

```html
<select id="theme-select" class="select select-bordered">
  <option value="light">Light</option>
  <option value="dark">Dark</option>
  <option value="cupcake">Cupcake</option>
</select>

<script>
  document.getElementById('theme-select').addEventListener('change', (e) => {
    document.documentElement.setAttribute('data-theme', e.target.value);
    localStorage.setItem('theme', e.target.value);
  });

  // Load saved theme
  const savedTheme = localStorage.getItem('theme') || 'light';
  document.documentElement.setAttribute('data-theme', savedTheme);
</script>
```

### System Preference Detection

```javascript
// Use dark theme if user prefers dark mode
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light');

// Listen for changes
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
  document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
});
```

## Custom Themes

### Create a Custom Theme

```javascript
// tailwind.config.js
module.exports = {
  plugins: [require("daisyui")],
  daisyui: {
    themes: [
      "light",
      "dark",
      {
        mytheme: {
          "primary": "#570df8",
          "secondary": "#f000b8",
          "accent": "#37cdbe",
          "neutral": "#3d4451",
          "base-100": "#ffffff",
          "info": "#3abff8",
          "success": "#36d399",
          "warning": "#fbbd23",
          "error": "#f87272",
        },
      },
    ],
  },
}
```

### Extend Existing Theme

```javascript
// tailwind.config.js
module.exports = {
  plugins: [require("daisyui")],
  daisyui: {
    themes: [
      {
        mylight: {
          ...require("daisyui/src/theming/themes")["light"],
          "primary": "#570df8",
          "secondary": "#f000b8",
        },
      },
    ],
  },
}
```

## Theme CSS Variables

Each theme sets these CSS variables:

### Color Variables

| Variable | Purpose |
|----------|---------|
| `--p` | Primary color |
| `--pf` | Primary focus |
| `--pc` | Primary content (text on primary) |
| `--s` | Secondary color |
| `--sf` | Secondary focus |
| `--sc` | Secondary content |
| `--a` | Accent color |
| `--af` | Accent focus |
| `--ac` | Accent content |
| `--n` | Neutral color |
| `--nf` | Neutral focus |
| `--nc` | Neutral content |
| `--b1` | Base 100 (background) |
| `--b2` | Base 200 (slightly darker) |
| `--b3` | Base 300 (darker) |
| `--bc` | Base content (text) |
| `--in` | Info color |
| `--inc` | Info content |
| `--su` | Success color |
| `--suc` | Success content |
| `--wa` | Warning color |
| `--wac` | Warning content |
| `--er` | Error color |
| `--erc` | Error content |

### Using CSS Variables

```css
/* In custom CSS */
.my-element {
  background-color: hsl(var(--p));  /* Primary color */
  color: hsl(var(--pc));            /* Primary content */
}
```

## Theme-Aware Tailwind Classes

DaisyUI provides these semantic color classes:

### Backgrounds
- `bg-primary`, `bg-secondary`, `bg-accent`
- `bg-neutral`, `bg-base-100`, `bg-base-200`, `bg-base-300`
- `bg-info`, `bg-success`, `bg-warning`, `bg-error`

### Text
- `text-primary`, `text-secondary`, `text-accent`
- `text-neutral`, `text-base-content`
- `text-info`, `text-success`, `text-warning`, `text-error`
- `text-primary-content` (text on primary bg)

### Borders
- `border-primary`, `border-secondary`, `border-accent`
- `border-neutral`, `border-base-200`, `border-base-300`

## Best Practices

### 1. Use Semantic Colors

```html
<!-- GOOD: Theme-aware -->
<button class="bg-primary text-primary-content">Button</button>
<p class="text-base-content">Body text</p>

<!-- AVOID: Fixed colors -->
<button class="bg-blue-600 text-white">Button</button>
<p class="text-gray-900">Body text</p>
```

### 2. Test Multiple Themes

Always test your UI with at least light and dark themes to ensure readability.

### 3. Respect Content Colors

Use `-content` suffixes for text on colored backgrounds:
- `text-primary-content` on `bg-primary`
- `text-base-content` on `bg-base-100`

### 4. Default Theme

Set a default theme in your HTML to prevent flash of unstyled content:

```html
<html data-theme="light">
```

### 5. Persist User Preference

```javascript
// Save to localStorage
localStorage.setItem('theme', selectedTheme);

// Load on page init
const theme = localStorage.getItem('theme') || 'light';
document.documentElement.setAttribute('data-theme', theme);
```

## Theme Color Reference

### Light Theme Colors

| Color | Hex | Usage |
|-------|-----|-------|
| Primary | #570df8 | Buttons, links |
| Secondary | #f000b8 | Secondary actions |
| Accent | #37cdbe | Highlights |
| Neutral | #3d4451 | Neutral elements |
| Base-100 | #ffffff | Background |
| Info | #3abff8 | Info messages |
| Success | #36d399 | Success states |
| Warning | #fbbd23 | Warnings |
| Error | #f87272 | Errors |

### Dark Theme Colors

| Color | Hex | Usage |
|-------|-----|-------|
| Primary | #661ae6 | Buttons, links |
| Secondary | #d926aa | Secondary actions |
| Accent | #1fb2a5 | Highlights |
| Neutral | #2a323c | Neutral elements |
| Base-100 | #1d232a | Background |
| Info | #3abff8 | Info messages |
| Success | #36d399 | Success states |
| Warning | #fbbd23 | Warnings |
| Error | #f87272 | Errors |
