---
related_skills:
- daisyui
- fasthtml
- html-htmx
- html-navigation
- tailwind-css
---

# SKUEL Page Architecture

*Last updated: 2026-02-05*

**When to use this skill:** When building new pages, choosing page layouts, implementing consistent UX patterns, or understanding how SKUEL structures HTML pages.

---

## Overview

SKUEL uses **BasePage** for consistency across all pages. This unified page wrapper provides:

- Consistent HTML structure and head includes
- Automatic navbar integration with auth detection
- Three layout types (STANDARD, HUB, CUSTOM)
- Design tokens for spacing and containers
- Accessibility features (ARIA live regions, semantic HTML)

**Core Principle:** "BasePage for consistency, custom layouts for special cases"

Every page in SKUEL should use `BasePage` unless there's a compelling reason for a completely custom HTML structure (extremely rare).

---

## Core Concepts

### 1. BasePage is THE Foundation

`BasePage` is the single source of truth for HTML structure. It automatically includes:
- HTMX 1.9.10 (for hypermedia interactions)
- Alpine.js 3.14.8 (for client-side state)
- DaisyUI 4.4.19 + Tailwind CSS (for styling)
- Vis.js Network 9.1.9 (for graph visualizations)
- SKUEL's custom CSS and JavaScript
- Modal container, toast notifications, ARIA live regions

### 2. Three Page Types

| Type | Use Case | Sidebar | Container | Examples |
|------|----------|---------|-----------|----------|
| **STANDARD** | Most pages | None | `max-w-6xl` centered | Tasks, Goals, Habits, Search |
| **HUB** | Dashboards | Fixed left (w-64) | Flexible | Admin Dashboard |
| **CUSTOM** | Special layouts | Custom implementation | Flexible | Profile Hub (/nous-style sidebar) |

### 3. Auto-Detection via Request

Pass the `request` parameter to automatically detect:
- User authentication state
- Admin role
- Current user name

This is ALWAYS preferred over manual parameters.

### 4. Design Tokens for Consistency

Use design tokens from `/ui/tokens.py` for spacing and containers:
- `Container.STANDARD` - `max-w-6xl mx-auto`
- `Spacing.PAGE` - `p-6 lg:p-8`
- `Card.BASE` - Standard card styling

### 5. Unified White Background

All layout surfaces use `bg-white`. Sections are separated by **borders**, not color contrast:
- Navbar: `bg-white border-b border-gray-200`
- HUB sidebar: `bg-white border-r border-gray-200`
- Sidebar pages (Profile, KU, Reports, Journals, Askesis): `bg-white border-r border-base-300` via Tailwind in `SidebarPage()`
- Body / content area: `bg-white`

Only interactive states (active nav links, hover tints) use non-white backgrounds.

### 6. Custom Layouts are Rare

Only create custom layouts when:
- You need sidebar behavior DIFFERENT from PageType.HUB (e.g., collapsible with state persistence)
- The page has unique structure that doesn't fit STANDARD or HUB
- You're building documentation or specialized tools

For Profile Hub, we built a custom sidebar because we wanted `/nous`-style collapsible behavior with localStorage persistence, which PageType.HUB doesn't provide.

---

## Decision Trees

### Choosing a Page Type

```
Need to build a page?
├─ Is it a standard content page (forms, lists, details)?
│  └─ Use PageType.STANDARD ✅
│
├─ Is it a dashboard with FIXED sidebar navigation?
│  └─ Use PageType.HUB ✅
│
└─ Does it need custom sidebar behavior (collapsible, state persistence)?
   ├─ Can you achieve this with PageType.HUB?
   │  └─ Use PageType.HUB ✅
   └─ No, need full control
      └─ Use PageType.STANDARD + custom sidebar implementation ⚠️
```

### When to Use Each Type

**STANDARD (90% of pages):**
- Activity domain pages (Tasks, Goals, Habits, Events, Choices, Principles)
- Search results
- Forms (create/edit)
- Detail pages
- Reports
- Static content

**HUB (5% of pages):**
- Admin Dashboard (user management, system stats)
- Multi-domain navigation with fixed sidebar

**CUSTOM (5% of pages):**
- Profile Hub (collapsible sidebar with state persistence)
- Documentation pages (if needing special navigation)
- Specialized tools with unique layouts

---

## Implementation Patterns

### Pattern 1: Standard Page (Most Common)

**Use when:** Building activity domain pages, forms, search results, static content

**Example:**
```python
from ui.layouts.base_page import BasePage

@rt("/tasks")
async def get_tasks(request: Request):
    # ... fetch tasks ...

    content = Div(
        PageHeader("Tasks", subtitle="Manage your daily work"),
        # ... task list ...
    )

    return BasePage(
        content,
        title="Tasks",
        request=request,  # Auto-detects auth/admin
        active_page="tasks",  # Highlights navbar item
    )
```

**Key Features:**
- Centered container (`max-w-6xl`)
- Standard padding (`p-6 lg:p-8`)
- No sidebar
- Auto navbar with active highlighting

---

### Pattern 2: Hub Page with Fixed Sidebar

**Use when:** Building dashboards with multi-section navigation

**Example:**
```python
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType

@rt("/admin")
async def get_admin_dashboard(request: Request):
    # Build sidebar menu
    sidebar = Div(
        Ul(
            Li(A("Users", href="/admin/users", cls="menu-item")),
            Li(A("System", href="/admin/system", cls="menu-item")),
            Li(A("Metrics", href="/admin/metrics", cls="menu-item")),
            cls="menu",
        ),
        cls="p-4",
    )

    # Main content
    content = Div(
        H1("Admin Dashboard"),
        # ... dashboard widgets ...
    )

    return BasePage(
        content,
        page_type=PageType.HUB,  # Enable sidebar layout
        sidebar=sidebar,  # Provide sidebar content
        title="Admin Dashboard",
        request=request,
        active_page="admin",
    )
```

**Key Features:**
- Fixed left sidebar (256px wide on desktop)
- Sidebar hidden on mobile (can be toggled)
- Flexible content area
- Sidebar sticky on scroll

---

### Pattern 3: Sidebar Page (SidebarPage)

**Use when:** You need collapsible sidebar with state persistence, multi-item navigation, or extra sections

**Example:**
```python
from ui.patterns.sidebar import SidebarItem, SidebarPage

@rt("/submissions")
async def reports_hub(request: Request):
    items = [
        SidebarItem("Submit", "/submissions/submit", "submit", icon="📤"),
        SidebarItem("Browse", "/submissions/browse", "browse", icon="📂"),
        SidebarItem("Projects", "/submissions/projects", "projects", icon="📋"),
    ]

    content = Div(
        H1("Submit Report"),
        # ... form content ...
    )

    return await SidebarPage(
        content=content,
        items=items,
        active="submit",
        title="Reports",
        storage_key="reports-sidebar",
        request=request,
        active_page="reports",
    )
```

**Key Features:**
- Collapsible sidebar (256px → 48px edge on desktop)
- Alpine.js `collapsibleSidebar` + `Alpine.store()` for shared state
- localStorage persistence (sidebar state saved)
- Mobile: Horizontal DaisyUI tabs (no drawer/overlay)
- Chevron toggle button with screen reader announcements
- Extension: `extra_sidebar_sections`, `item_renderer`, `description` items

**Files:**
- `/ui/patterns/sidebar.py` - `SidebarItem`, `SidebarNav`, `SidebarPage`
- `/static/js/skuel.js` (lines 917-953) - `collapsibleSidebar` Alpine component

**Current Adopters:** Profile, KU, Reports, Journals, Askesis (all 5 sidebar pages)

**See:** `@custom-sidebar-patterns` for complete implementation guide

---

### Pattern 4: Using Design Tokens

**Use when:** Building custom content that needs consistent spacing

**Example:**
```python
from ui.tokens import Container, Spacing, Card

# Custom content with design tokens
content = Div(
    # Section with standard spacing
    Div(
        H2("Recent Activity"),
        Div(
            # Cards with consistent styling
            Div(
                P("Task completed"),
                cls=f"{Card.BASE} {Card.PADDING}",
            ),
            cls=Spacing.CONTENT,  # space-y-4
        ),
        cls=Spacing.SECTION,  # space-y-8
    ),
    cls=Container.STANDARD,  # max-w-6xl mx-auto
)
```

**Available Tokens:**

**Containers:**
- `Container.STANDARD` - `max-w-6xl mx-auto` (1152px, default)
- `Container.NARROW` - `max-w-4xl mx-auto` (896px)
- `Container.WIDE` - `max-w-7xl mx-auto` (1280px)

**Spacing:**
- `Spacing.PAGE` - `p-6 lg:p-8` (page-level padding)
- `Spacing.SECTION` - `space-y-8` (between sections)
- `Spacing.CONTENT` - `space-y-4` (between items)

**Cards:**
- `Card.BASE` - `bg-base-100 border border-base-200 rounded-lg`
- `Card.INTERACTIVE` - BASE + hover shadow
- `Card.PADDING` - `p-6`

---

### Pattern 5: Extra CSS/JS for Specific Pages

**Use when:** A page needs additional CSS or JavaScript files

**Example:**
```python
return BasePage(
    content,
    title="Advanced Visualization",
    request=request,
    extra_css=[
        "/static/css/custom_graphs.css",
        "/static/css/advanced_layout.css",
    ],
)
```

**Note:** BasePage already includes:
- HTMX, Alpine.js, DaisyUI, Tailwind, Vis.js
- SKUEL's main.css, output.css, hierarchy.css
- SKUEL's skuel.js (Alpine components)

Only add extra CSS/JS for page-specific needs.

---

### Pattern 6: Page Header & Section Header

**Use when:** Building consistent page and section titles

**Example:**
```python
from ui.patterns import PageHeader, SectionHeader
from fasthtml.common import A, Button

# Page header with subtitle
content = Div(
    PageHeader(
        "Tasks",
        subtitle="Manage your daily work",
        actions=Button("Create Task", cls="btn btn-primary"),
    ),

    # Section header with action link
    SectionHeader(
        "Recent Tasks",
        action=A("View All", href="/tasks/all", cls="link link-primary"),
    ),

    # ... content ...
)
```

**PageHeader:**
- Large title with optional subtitle
- Optional action buttons (top-right)
- Consistent spacing (mb-8)

**SectionHeader:**
- Medium title for sections
- Optional action link (right-aligned)
- Consistent spacing (mb-4)

---

## Real-World Examples

### Example 1: Tasks Page (STANDARD)
**File:** `/adapters/inbound/tasks_ui.py:24`

```python
@rt("/tasks")
async def get_tasks(request: Request):
    user_uid = require_authenticated_user(request)

    tasks_result = await tasks_service.list_for_user(user_uid)
    if tasks_result.is_error:
        return render_error_banner(tasks_result.error)

    content = Div(
        PageHeader("Tasks"),
        TasksList(tasks_result.value),
    )

    return BasePage(
        content,
        title="Tasks",
        request=request,
        active_page="tasks",
    )
```

**Pattern:** STANDARD page with auto auth detection

---

### Example 2: Admin Dashboard (HUB)
**File:** `/ui/admin/layout.py:15`

```python
@rt("/admin")
async def get_admin_dashboard(request: Request):
    # Build sidebar
    sidebar = Div(
        Ul(
            Li(A("Users", href="/admin/users")),
            Li(A("System", href="/admin/system")),
            cls="menu",
        ),
    )

    return BasePage(
        content=dashboard_widgets,
        page_type=PageType.HUB,
        sidebar=sidebar,
        title="Admin Dashboard",
        request=request,
    )
```

**Pattern:** HUB page with fixed sidebar

---

### Example 3: Profile Hub (CUSTOM)
**File:** `/ui/profile/layout.py:180`

```python
from ui.patterns.sidebar import SidebarItem, SidebarPage

items = [
    SidebarItem("Overview", "/profile", "overview", icon="📊"),
    SidebarItem("Shared", "/profile/shared", "shared", icon="📬"),
]

return await SidebarPage(
    content=content,
    items=items,
    active="overview",
    title="Profile",
    storage_key="profile-sidebar",
    request=request,
    active_page="profile/hub",
)
```

**Pattern:** CUSTOM sidebar with collapse behavior via `SidebarPage()`

---

## Common Mistakes & Anti-Patterns

### Mistake 1: Creating Custom HTML Structure

**Why it's wrong:**
- Breaks consistency across pages
- Misses navbar, modal container, ARIA regions
- Different library versions (HTMX, Alpine.js)
- No auto auth detection

**Example of mistake:**
```python
# ❌ DON'T DO THIS
return Html(
    Head(Title("My Page")),
    Body(
        Div("Custom navbar"),
        Div(content),
    ),
)
```

**Correct approach:**
```python
# ✅ DO THIS
return BasePage(
    content,
    title="My Page",
    request=request,
)
```

---

### Mistake 2: Using PageType.HUB for Collapsible Sidebar

**Why it's wrong:**
PageType.HUB creates a FIXED sidebar that's always visible on desktop. It doesn't collapse or persist state.

**When you need:**
- Collapsible sidebar with chevron toggle
- Sidebar state persistence (localStorage)
- Mobile drawer with overlay

**Correct approach:**
Use PageType.STANDARD + custom sidebar implementation (like Profile Hub pattern)

---

### Mistake 3: Manual Auth Parameters Instead of Request

**Why it's wrong:**
```python
# ❌ DON'T DO THIS
return BasePage(
    content,
    user_display_name="John",
    is_authenticated=True,
    is_admin=False,
)
```

**Correct approach:**
```python
# ✅ DO THIS
return BasePage(
    content,
    request=request,  # Auto-detects everything
)
```

Passing `request` automatically extracts auth state, user name, and admin role.

---

### Mistake 4: Inconsistent Container Widths

**Why it's wrong:**
```python
# ❌ DON'T DO THIS
content = Div(
    Div("Section 1", cls="max-w-4xl mx-auto"),
    Div("Section 2", cls="max-w-5xl mx-auto"),
    Div("Section 3", cls="max-w-7xl mx-auto"),
)
```

**Correct approach:**
```python
# ✅ DO THIS - Use design tokens
from ui.tokens import Container

content = Div(
    Div("All sections", cls=Container.STANDARD),
)
```

SKUEL uses `max-w-6xl` (1152px) as the standard container width. Use design tokens for consistency.

---

### Mistake 5: Not Including Active Page

**Why it's wrong:**
```python
# ❌ DON'T DO THIS
return BasePage(
    content,
    title="Tasks",
    request=request,
    # Missing active_page parameter
)
```

**Correct approach:**
```python
# ✅ DO THIS
return BasePage(
    content,
    title="Tasks",
    request=request,
    active_page="tasks",  # Highlights navbar item
)
```

The `active_page` parameter highlights the current page in the navbar, improving UX.

---

### Mistake 6: Forgetting Extra CSS for Custom Components

**Why it's wrong:**
Custom components (like Profile Hub sidebar) need their CSS files included.

**Example of mistake:**
```python
# ❌ DON'T DO THIS
return create_profile_page(
    content,
    domains=domains,
    request=request,
    # Missing extra_css for sidebar styles
)
```

**Correct approach:**
```python
# ✅ DO THIS — use SidebarPage for sidebar pages
from ui.patterns.sidebar import SidebarItem, SidebarPage

return await SidebarPage(
    content=content,
    items=items,
    active="overview",
    title="Profile",
    storage_key="profile-sidebar",
    request=request,
)
```

**Note:** `SidebarPage()` handles all layout, BasePage wrapping, and Alpine.js state automatically.

---

## Testing & Verification

### Checklist for New Pages

When building a new page, verify:

- [ ] Uses `BasePage` (not custom HTML structure)
- [ ] Passes `request` parameter (auto auth detection)
- [ ] Includes `active_page` parameter (navbar highlighting)
- [ ] Uses correct `page_type` (STANDARD for most pages)
- [ ] Uses design tokens for containers and spacing
- [ ] Includes `extra_css` if needed for custom styles
- [ ] Page title is descriptive ("Tasks" not "Page")
- [ ] Works on mobile (responsive design)
- [ ] Navbar appears and highlights correctly
- [ ] Modal container works (if using modals)
- [ ] ARIA live regions present (screen reader support)

### Visual Verification

1. **Desktop (1920x1080):**
   - Content centered with `max-w-6xl` (STANDARD)
   - Sidebar visible and functional (HUB)
   - Navbar appears at top
   - Padding consistent (`p-6 lg:p-8`)

2. **Mobile (375x667):**
   - Content takes full width with padding
   - Navbar collapses to mobile menu
   - Sidebar hidden (HUB) or drawer (CUSTOM)
   - No horizontal scroll

3. **Accessibility:**
   - Keyboard navigation works
   - Screen reader announces page changes (ARIA live region)
   - Focus indicators visible
   - Color contrast meets WCAG AA

---

## Related Documentation

### Core Files
- `/ui/layouts/base_page.py` - BasePage implementation
- `/ui/layouts/page_types.py` - PageType enum and PAGE_CONFIG
- `/ui/tokens.py` - Design tokens (Container, Spacing, Card)
- `/ui/patterns/` - PageHeader, SectionHeader components

### Sidebar Pages
- `/ui/patterns/sidebar.py` - Unified sidebar component (`SidebarItem`, `SidebarNav`, `SidebarPage`)
- `/static/js/skuel.js` (lines 917-953) - `collapsibleSidebar` Alpine component

### Documentation
- `/docs/patterns/UI_COMPONENT_PATTERNS.md` - Complete UI patterns guide
- `/docs/migrations/PROFILE_HUB_MODERNIZATION_2026-02-01.md` - Profile Hub migration
- `/CLAUDE.md` - UI Component Pattern section (lines 632-669)

### Related Skills
- **daisyui** - DaisyUI component library (buttons, cards, forms)
- **fasthtml** - FastHTML framework (FT components, routes)
- **html-htmx** - HTMX patterns (hypermedia interactions)
- **html-navigation** - Navbar, sidebar, mobile menu patterns
- **tailwind-css** - Tailwind CSS utility classes

---

## Deep Dive Resources

**Patterns:**
- [UI_COMPONENT_PATTERNS.md](/docs/patterns/UI_COMPONENT_PATTERNS.md) - Complete UI component architecture

**Migration:**
- [PROFILE_HUB_MODERNIZATION_2026-02-01.md](/docs/migrations/PROFILE_HUB_MODERNIZATION_2026-02-01.md) - Profile Hub migration to BasePage with custom sidebar

**Implementation:**
- `/ui/patterns/sidebar.py` - Unified sidebar component (`SidebarItem`, `SidebarNav`, `SidebarPage`)
- `/ui/layouts/base_page.py` - BasePage implementation
- `/ui/layouts/page_types.py` - PageType enum and config

---

## See Also

### Decision Making
- **When to use STANDARD:** Most pages (activity domains, forms, lists)
- **When to use HUB:** Dashboards with fixed sidebar (Admin Dashboard)
- **When to use CUSTOM:** Special sidebar behavior (Profile Hub collapsible)

### Advanced Patterns
- **custom-sidebar-patterns** skill - Building custom sidebars like Profile Hub
- **ui-error-handling** skill - Handling Result[T] at UI boundaries
- **skuel-form-patterns** skill - Form validation and submission

### Philosophy
SKUEL's "One Path Forward" principle means:
- Use `BasePage` for ALL pages (no exceptions without strong justification)
- Use design tokens for consistency (no magic numbers)
- Pass `request` for auto-detection (no manual auth parameters)
- Choose page type based on content, not aesthetics

**Key Insight:** BasePage isn't a constraint - it's a foundation that handles all the boilerplate (HTML head, navbar, auth, ARIA, modals) so you can focus on domain logic.
