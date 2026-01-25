# SKUEL UX Migration Plan: FrankenUI → DaisyUI + Tailwind
*Last updated: 2026-01-22*

## Executive Summary

Migrate SKUEL's UI from **FrankenUI component DSL** to **semantic HTML + DaisyUI + Tailwind CSS**, following the successful pattern established in `/docs/` and `/components/drawer_layout.py`.

**Status:** MIGRATION COMPLETE (January 2026)
**Current State:** All 5 phases complete. SKUEL uses DaisyUI 5 + Tailwind CSS via Python wrappers.
**Architecture:** `core/ui/daisy_components.py` provides type-safe wrappers, `core/ui/theme.py` provides `daisy_headers()`

### Phase 1 Status: COMPLETE

New DaisyUI components created (parallel to existing FrankenUI versions):
- `components/daisyui_design_system.py` - Core design system with NavItem, DaisyUIComponents, page layouts
- `components/shared_ui_components_daisy.py` - Dashboard components (stats, entity lists, quick actions)
- `components/form_generator_daisy.py` - Pydantic model to form HTML generation
- `components/auth_components_daisy.py` - Login/registration pages
- `static/css/main.css` - Core stylesheet with typography, animations, HTMX loading states

---

## Why Migrate?

### FrankenUI Limitations
1. **Component DSL overhead** - `Card()`, `Button()` add abstraction layer
2. **Limited customization** - Harder to tweak individual styles
3. **Bundle size** - Includes UIkit JS we don't need
4. **Learning curve** - Custom API on top of standard HTML

### DaisyUI Advantages
1. **Semantic HTML** - Works naturally with FastHTML's philosophy
2. **CSS-only components** - Drawer toggles, modals via pure CSS
3. **Tailwind foundation** - Utility-first, highly composable
4. **Smaller footprint** - No JavaScript for basic components
5. **Better accessibility** - Semantic structure built-in
6. **Theme system** - Easy light/dark mode, custom themes

### Proven Pattern
The `/docs/` section already demonstrates the target architecture:
- `docs_layout.py` - DaisyUI drawer, responsive, CSS-only
- `drawer_layout.py` - Reusable drawer component
- `docs.css` - Minimal custom CSS (~310 lines)

---

## Architecture Comparison

### Before (FrankenUI)
```python
from monsterui.franken import Card, Button, Div, H1, P

def render_task_card(task):
    return Card(
        H1(task.title, cls="text-xl"),
        P(task.description),
        Button("Complete", cls="btn-primary"),
        cls="p-4 shadow-md"
    )
```

### After (DaisyUI + Semantic HTML)
```python
from fasthtml.common import Div, H1, P, Button, NotStr

def render_task_card(task):
    return Div(
        H1(task.title, cls="text-xl font-bold"),
        P(task.description, cls="text-base-content/70"),
        Button("Complete", cls="btn btn-primary btn-sm"),
        cls="card bg-base-100 shadow-md p-4"
    )
```

**Key Differences:**
- Same Python syntax, different CSS classes
- DaisyUI classes (`card`, `btn`, `bg-base-100`) replace FrankenUI components
- No import from `monsterui.franken`
- Use `fasthtml.common` elements directly

---

## Component Mapping: FrankenUI → DaisyUI

| FrankenUI | DaisyUI Class | Notes |
|-----------|---------------|-------|
| `Card()` | `div.card` | Add `bg-base-100 shadow-xl` |
| `Button()` | `button.btn` | Add variant: `btn-primary`, `btn-ghost`, etc. |
| `Input()` | `input.input` | Add `input-bordered` for border |
| `Select()` | `select.select` | Add `select-bordered` |
| `Textarea()` | `textarea.textarea` | Add `textarea-bordered` |
| `Table()` | `table.table` | Add `table-zebra` for stripes |
| `Modal()` | `dialog.modal` | CSS-only with `<dialog>` element |
| `Navbar()` | `div.navbar` | Use `bg-base-100` |
| `Drawer()` | `div.drawer` | CSS-only toggle via checkbox |
| `Badge()` | `span.badge` | Add variant: `badge-primary`, etc. |
| `Alert()` | `div.alert` | Add `alert-info`, `alert-error`, etc. |
| `Progress()` | `progress.progress` | Native `<progress>` element |
| `Tabs()` | `div.tabs` | `role="tablist"` + `tab` class |

---

## Migration Phases

### Phase 0: Foundation (Complete)
- [x] DaisyUI drawer pattern established (`drawer_layout.py`)
- [x] Docs layout working (`docs_layout.py`)
- [x] CSS foundation (`docs.css`)
- [x] CDN setup in headers

### Phase 1: Shared Components (Week 1)
Priority: Migrate reusable components that cascade to all domains.

| File | Lines | Priority | Complexity |
|------|-------|----------|------------|
| `shared_ui_components.py` | ~400 | HIGH | Medium |
| `franken_design_system.py` | ~300 | HIGH | Medium |
| `form_generator.py` | ~200 | HIGH | Low |
| `auth_components.py` | ~150 | MEDIUM | Low |

**Deliverables:**
- `BaseLayout` - Standard page wrapper with navbar/footer
- `EntityCard` - Generic card for all entity types
- `StatsGrid` - Statistics display component
- `ActionButtons` - HTMX-enabled action button group
- `FormBuilder` - DaisyUI form field generator

### Phase 2: Activity Domains (Weeks 2-3)
Core user-facing dashboards.

| File | Lines | Priority | Complexity |
|------|-------|----------|------------|
| `tasks_ui.py` | ~390 | HIGH | Medium |
| `goals_ui.py` | ~400 | HIGH | Medium |
| `habits_ui.py` | ~350 | HIGH | Medium |
| `events_ui.py` | ~300 | HIGH | Medium |
| `principles_ui.py` | ~200 | MEDIUM | Low |
| `choice_ui.py` | ~200 | MEDIUM | Low |
| `finance_ui.py` | ~250 | MEDIUM | Low |

### Phase 3: Knowledge/Curriculum (Week 4)
Learning-focused interfaces.

| File | Lines | Priority | Complexity |
|------|-------|----------|------------|
| `knowledge_ui.py` | ~300 | MEDIUM | Medium |
| `learning_ui.py` | ~350 | MEDIUM | Medium |
| `moc_ui.py` | ~200 | MEDIUM | Low |

### Phase 4 Status: COMPLETE

Supporting UIs migrated to DaisyUI semantic colors (January 2026):

| File | Changes | Notes |
|------|---------|-------|
| `search_routes.py` | Already DaisyUI | Was migrated in earlier phase |
| `calendar_routes.py` | 83 color → DaisyUI | + import change to `fasthtml.common` |
| `calendar_components.py` | 38 color → DaisyUI | Buttons, modals, day cells |
| `reports_ui.py` | 27 color → DaisyUI | + Card → Div with card class |
| `assignments_ui.py` | 60 UIKit → DaisyUI | Full rewrite from `uk-*` classes |

**Key Migration Patterns Applied:**
- Fixed Tailwind colors → DaisyUI semantic (`text-gray-600` → `text-base-content/60`)
- Button classes → `btn btn-{variant}`
- Card component → `Div` with `card bg-base-100 shadow-sm` classes
- Alert styling → `alert alert-{type}`
- Badge styling → `badge badge-{type}`
- Form controls → `input input-bordered`, `select select-bordered`

### Phase 5 Status: COMPLETE

**Completed: January 2026**

Phase 5 finalized the MonsterUI → DaisyUI migration:

| Action | Result |
|--------|--------|
| Remove `monsterui` from pyproject.toml | Done |
| Create SKUEL DaisyUI wrappers | `/core/ui/daisy_components.py` |
| Create theme configuration | `/core/ui/theme.py` with `daisy_headers()` |
| Migrate 35+ files from MonsterUI | All imports updated |
| Convert 213 uk-* FrankenUI classes | Replaced with DaisyUI |
| Delete MonsterUI skill folder | Removed `/.claude/skills/monsterui/` |
| Delete MonsterUI data/docs/examples | All removed |
| Update UI_COMPONENT_PATTERNS.md | Rewritten for SKUEL/DaisyUI |

**Key Migration Patterns:**
- `from monsterui.all import *` → `from core.ui.daisy_components import *`
- `Theme.blue.headers()` → `daisy_headers()` from `core.ui.theme`
- Type-safe enums: `ButtonT`, `AlertT`, `BadgeT`, `ProgressT`, `Size`

**One Path Forward:** MonsterUI is fully removed. SKUEL uses DaisyUI directly via type-safe Python wrappers

---

## DaisyUI Component Patterns

### 1. Page Layout with Drawer

```python
def create_page_layout(title: str, nav_items: list, content: str) -> NotStr:
    """Standard page layout with responsive sidebar."""
    return NotStr(f"""
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - SKUEL</title>
    <link href="https://cdn.jsdelivr.net/npm/daisyui@5" rel="stylesheet" />
    <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
    <script src="https://unpkg.com/htmx.org@1.9.6"></script>
</head>
<body class="bg-base-100 min-h-screen">
    <div class="drawer lg:drawer-open">
        <input id="main-drawer" type="checkbox" class="drawer-toggle" />

        <div class="drawer-content">
            <!-- Mobile navbar -->
            <div class="navbar bg-base-200 lg:hidden sticky top-0 z-10">
                <label for="main-drawer" class="btn btn-square btn-ghost">
                    <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
                    </svg>
                </label>
                <span class="text-xl font-bold">{title}</span>
            </div>

            <!-- Main content -->
            <main class="p-4 lg:p-8">
                {content}
            </main>
        </div>

        <!-- Sidebar -->
        <div class="drawer-side z-20">
            <label for="main-drawer" class="drawer-overlay"></label>
            <aside class="bg-base-200 min-h-full w-72 p-4">
                <h2 class="text-2xl font-bold text-primary mb-6">SKUEL</h2>
                <ul class="menu menu-md w-full">
                    {build_nav_items(nav_items)}
                </ul>
            </aside>
        </div>
    </div>
</body>
</html>
""")
```

### 2. Entity Card Pattern

```python
def render_entity_card(
    title: str,
    description: str,
    status: str,
    priority: str,
    actions: list[dict],
) -> str:
    """Generic entity card with DaisyUI styling."""
    priority_colors = {
        "high": "border-error",
        "medium": "border-warning",
        "low": "border-success",
    }
    status_badges = {
        "todo": "badge-neutral",
        "in_progress": "badge-info",
        "done": "badge-success",
    }

    border = priority_colors.get(priority, "border-base-300")
    badge = status_badges.get(status, "badge-ghost")

    action_html = "".join([
        f'<button class="btn btn-sm {a.get("cls", "btn-ghost")}" '
        f'hx-{a.get("method", "get")}="{a["url"]}" '
        f'hx-target="{a.get("target", "#content")}">{a["label"]}</button>'
        for a in actions
    ])

    return f"""
    <div class="card bg-base-100 shadow-md border-l-4 {border}">
        <div class="card-body p-4">
            <div class="flex justify-between items-start">
                <h3 class="card-title text-base">{title}</h3>
                <span class="badge {badge}">{status}</span>
            </div>
            <p class="text-sm text-base-content/70">{description}</p>
            <div class="card-actions justify-end mt-2">
                {action_html}
            </div>
        </div>
    </div>
    """
```

### 3. Stats Grid Pattern

```python
def render_stats_grid(stats: list[dict]) -> str:
    """Grid of stat cards."""
    cards = []
    for stat in stats:
        color = stat.get("color", "primary")
        cards.append(f"""
        <div class="stat bg-base-100 rounded-box shadow">
            <div class="stat-figure text-{color}">
                <span class="text-3xl">{stat.get("icon", "📊")}</span>
            </div>
            <div class="stat-title">{stat["label"]}</div>
            <div class="stat-value text-{color}">{stat["value"]}</div>
            <div class="stat-desc">{stat.get("desc", "")}</div>
        </div>
        """)

    return f"""
    <div class="stats stats-vertical lg:stats-horizontal shadow w-full mb-6">
        {"".join(cards)}
    </div>
    """
```

### 4. Form Pattern

```python
def render_form_field(
    name: str,
    label: str,
    field_type: str = "text",
    required: bool = False,
    options: list | None = None,
) -> str:
    """DaisyUI form field."""
    req = "required" if required else ""

    if field_type == "select" and options:
        opts = "".join([f'<option value="{o["value"]}">{o["label"]}</option>' for o in options])
        input_html = f'<select name="{name}" class="select select-bordered w-full" {req}>{opts}</select>'
    elif field_type == "textarea":
        input_html = f'<textarea name="{name}" class="textarea textarea-bordered w-full" {req}></textarea>'
    else:
        input_html = f'<input type="{field_type}" name="{name}" class="input input-bordered w-full" {req} />'

    return f"""
    <div class="form-control w-full">
        <label class="label">
            <span class="label-text">{label}</span>
        </label>
        {input_html}
    </div>
    """
```

### 5. Modal Pattern (CSS-Only)

```python
def render_modal(modal_id: str, title: str, content: str, actions: str = "") -> str:
    """DaisyUI modal using HTML dialog element."""
    return f"""
    <dialog id="{modal_id}" class="modal">
        <div class="modal-box">
            <h3 class="text-lg font-bold">{title}</h3>
            <div class="py-4">{content}</div>
            <div class="modal-action">
                {actions}
                <form method="dialog">
                    <button class="btn">Close</button>
                </form>
            </div>
        </div>
        <form method="dialog" class="modal-backdrop">
            <button>close</button>
        </form>
    </dialog>
    """
```

---

## CSS Strategy

### Consolidated CSS File Structure

```
/static/css/
├── main.css          # Core styles (typography, layout)
├── components.css    # Custom component styles (minimal)
└── themes.css        # Theme customizations (optional)
```

### Core CSS (main.css)

```css
/* Typography */
.prose { line-height: 1.75; }
.prose h1 { @apply text-3xl font-bold mb-4; }
.prose h2 { @apply text-2xl font-semibold mt-8 mb-3; }
.prose h3 { @apply text-xl font-semibold mt-6 mb-2; }

/* Code blocks */
.prose code {
    @apply bg-base-200 px-1.5 py-0.5 rounded text-sm font-mono;
}
.prose pre {
    @apply bg-neutral text-neutral-content p-4 rounded-lg overflow-x-auto;
}

/* Tables */
.prose table { @apply w-full my-4; }
.prose th { @apply text-left p-3 bg-base-200 font-semibold; }
.prose td { @apply p-3 border-b border-base-200; }

/* Print styles */
@media print {
    .drawer-side, .navbar { display: none !important; }
    .drawer-content { margin-left: 0 !important; }
}
```

### Theme Configuration

```html
<!-- In head, allow theme switching -->
<html data-theme="light">

<!-- Theme toggle button -->
<label class="swap swap-rotate">
    <input type="checkbox" class="theme-controller" value="dark" />
    <span class="swap-on">🌙</span>
    <span class="swap-off">☀️</span>
</label>
```

---

## Migration Checklist per File

For each route/component file:

1. **Replace imports:**
   ```python
   # Before
   from monsterui.franken import Card, Button, Div, H1, P

   # After
   from fasthtml.common import Div, H1, P, Button, NotStr
   ```

2. **Update component calls:**
   ```python
   # Before
   Card(..., cls="uk-card uk-card-default")

   # After
   Div(..., cls="card bg-base-100 shadow-md")
   ```

3. **Convert buttons:**
   ```python
   # Before
   Button("Click", cls="uk-button uk-button-primary")

   # After
   Button("Click", cls="btn btn-primary")
   ```

4. **Update forms:**
   ```python
   # Before
   Input(cls="uk-input")

   # After
   Input(cls="input input-bordered w-full")
   ```

5. **Test HTMX interactions** - Ensure `hx-*` attributes still work

6. **Verify responsive behavior** - Check mobile drawer, grid layouts

---

## File-by-File Migration Guide

### shared_ui_components.py

**Current (FrankenUI):**
```python
from monsterui.franken import H1, H2, Card, Div, Button, ...

class SharedUIComponents:
    @staticmethod
    def render_entity_dashboard(...):
        return Div(
            navbar,
            H1(title, cls="text-3xl font-bold mb-6"),
            SharedUIComponents.render_stats_cards(stats),
            ...
        )
```

**Target (DaisyUI):**
```python
from fasthtml.common import Div, H1, H2, P, Button, NotStr

class SharedUIComponents:
    @staticmethod
    def render_entity_dashboard(...) -> NotStr:
        return NotStr(f"""
        <div class="container mx-auto p-6">
            {navbar}
            <h1 class="text-3xl font-bold mb-6">{title}</h1>
            {SharedUIComponents.render_stats_cards(stats)}
            ...
        </div>
        """)
```

### tasks_ui.py

**Current:**
```python
from monsterui.franken import H1, H4, Button, Card, Div, Li, P, Span, Ul

class TaskUIComponents:
    @staticmethod
    def render_task_item(task) -> Any:
        return Li(
            Card(
                Div(H4(title), render_status_badge(status), cls="flex..."),
                ...
            )
        )
```

**Target:**
```python
from fasthtml.common import Li, Div, H4, P, Span, Button

class TaskUIComponents:
    @staticmethod
    def render_task_item(task) -> str:
        return f"""
        <li class="mb-2">
            <div class="card bg-base-100 shadow-sm border-l-4 {border_color} p-4">
                <div class="flex justify-between items-start mb-2">
                    <h4 class="text-base font-semibold">{title}</h4>
                    <span class="badge {status_badge}">{status}</span>
                </div>
                <p class="text-sm text-base-content/70 mb-2">{description}</p>
                <div class="flex gap-2">
                    <span class="badge {priority_badge}">{priority}</span>
                    {f'<span class="text-xs text-base-content/50">📅 {due_date}</span>' if due_date else ''}
                </div>
                <div class="flex gap-2 mt-3">
                    <button class="btn btn-sm btn-outline" hx-get="/tasks/{uid}/edit" hx-target="#modal">Edit</button>
                    <button class="btn btn-sm btn-success" hx-post="/api/tasks/{uid}/complete" hx-target="#task-list">Complete</button>
                </div>
            </div>
        </li>
        """
```

---

## Testing Strategy

### Visual Regression Testing
1. Screenshot current UI (FrankenUI)
2. Migrate component
3. Compare screenshots
4. Verify responsive breakpoints

### Functional Testing
1. Verify all HTMX interactions work
2. Test form submissions
3. Check modal open/close
4. Verify drawer toggle on mobile

### Accessibility Testing
1. Run Lighthouse audit
2. Check keyboard navigation
3. Verify screen reader compatibility

---

## Dependencies

### Current (FrankenUI)
```toml
[tool.poetry.dependencies]
monsterui = "*"
python-fasthtml = "^0.12.21"
```

### Target (DaisyUI via CDN)
```toml
[tool.poetry.dependencies]
python-fasthtml = "^0.12.21"
# monsterui removed
```

**CDN in HTML head:**
```html
<link href="https://cdn.jsdelivr.net/npm/daisyui@5" rel="stylesheet" />
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
```

---

## Success Metrics

| Metric | Before | Target |
|--------|--------|--------|
| JS bundle size | ~150KB (UIkit) | ~0KB (CSS-only) |
| CSS dependencies | FrankenUI + UIkit | DaisyUI + Tailwind |
| Custom CSS lines | ~800 | ~400 |
| Component imports | 24 files with `monsterui.franken` | 0 |
| Lighthouse Performance | ~70 | ~90 |

---

## Rollback Plan

If issues arise during migration:
1. Keep `monsterui` in dependencies until Phase 5
2. Files can coexist (some FrankenUI, some DaisyUI)
3. Theme headers already load both frameworks
4. Individual routes can be reverted independently

---

## Related Documentation

- `/docs/Daisyui_llms.txt` - Complete DaisyUI reference
- `/docs/fasthtml-llms.txt` - FastHTML patterns
- `/components/drawer_layout.py` - Working DaisyUI drawer
- `/components/docs_layout.py` - Working DaisyUI page layout
- `/static/css/docs.css` - Reference CSS implementation
