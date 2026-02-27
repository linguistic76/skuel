---
name: custom-sidebar-patterns
description: Expert guide for building custom sidebar navigation patterns. Use when creating collapsible sidebars, drawer navigation, multi-section menus, or persistent navigation state that goes beyond standard BasePage HUB layout.
allowed-tools: Read, Grep, Glob
related_skills:
- base-page-architecture
- html-navigation
- js-alpine
- tailwind-css
- daisyui
---

# Custom Sidebar Patterns

## Core Philosophy

> "One sidebar component for all pages — Tailwind for styling, Alpine.js for state."

SKUEL uses a **unified sidebar component** (`ui/patterns/sidebar.py`) for all pages that need collapsible navigation. Desktop gets a collapsible fixed sidebar. Mobile gets horizontal DaisyUI tabs (no drawer/overlay).

**Stack:**

| Layer | Technology | Responsibility |
|-------|------------|----------------|
| **HTML Structure** | Python/FastHTML | `SidebarItem`, `SidebarNav`, `SidebarPage` |
| **Styling** | Tailwind utility classes | Layout, transitions, responsive hiding |
| **State Management** | Alpine.js `collapsibleSidebar` | Toggle, localStorage, screen reader announcements |

**Key Design Decisions:**
- **Alpine.js manages state** — `Alpine.store()` shares collapsed state between sidebar and content area
- **No custom CSS files** — Tailwind utilities replace `profile_sidebar.css`
- **No mobile drawer** — horizontal tabs replace the overlay/hamburger pattern
- **`PageType.CUSTOM`** — sidebar pages use BasePage CUSTOM (no container padding conflict)

## When to Use This Skill

Choose `SidebarPage()` when:

- ✅ Navigation requires **multi-item sidebar** (3+ navigation sections)
- ✅ Sidebar state must **persist across sessions** (localStorage)
- ✅ Need **collapsible sidebar** on desktop with smooth transitions
- ✅ Domain items have **dynamic badges/indicators**
- ✅ Need **extra sidebar sections** (curriculum, HTMX-loaded content)

Use **BasePage HUB** instead when:

- ⚠️ Simple left sidebar with static menu items (Admin Dashboard)
- ⚠️ No collapse behavior needed
- ⚠️ Standard responsive drawer pattern sufficient

**Decision Tree:**

```
Does page need collapsible sidebar with persistence?
├─ YES → SidebarPage() ✓
└─ NO → Does page need any sidebar?
    ├─ YES → BasePage HUB ✓
    └─ NO → BasePage STANDARD ✓
```

## Core Component: `ui/patterns/sidebar.py`

### SidebarItem Dataclass

```python
from ui.patterns.sidebar import SidebarItem

item = SidebarItem(
    label="Submit",        # Display text
    href="/submissions/submit", # Navigation URL
    slug="submit",         # For active state matching
    icon="📤",             # Optional emoji
    description="",        # Optional subtitle (renders two-line item)
    badge_text="",         # Optional badge (e.g., count)
    badge_cls="badge badge-sm badge-ghost",  # Badge styling
    hx_attrs={},           # Optional HTMX attributes
)
```

### SidebarNav Function

Builds desktop sidebar + mobile tabs. Does NOT wrap in BasePage — use `SidebarPage()` for that.

```python
from ui.patterns.sidebar import SidebarNav

nav = SidebarNav(
    items=items,
    active="submit",              # Currently active slug
    title="Reports",              # Sidebar heading
    subtitle="",                  # Optional subtitle
    storage_key="reports-sidebar", # localStorage key for collapse state
    extra_sidebar_sections=None,  # Additional content after nav items
    extra_mobile_sections=None,   # Additional content below mobile tabs
    item_renderer=None,           # Custom render function
    title_href="",                # Optional link on title
)
```

### SidebarPage Function (Primary API)

Creates a full page with collapsible sidebar. This is THE function to call.

```python
from ui.patterns.sidebar import SidebarItem, SidebarPage

items = [
    SidebarItem("Submit", "/submissions/submit", "submit", icon="📤"),
    SidebarItem("Browse", "/submissions/browse", "browse", icon="📂"),
    SidebarItem("Projects", "/submissions/projects", "projects", icon="📋"),
]

return await SidebarPage(
    content=my_content,
    items=items,
    active="submit",
    title="Reports",
    storage_key="reports-sidebar",
    request=request,
    active_page="reports",
)
```

**Parameters:**

| Parameter | Type | Purpose |
|-----------|------|---------|
| `content` | Any | Main page content |
| `items` | list[SidebarItem] | Navigation items |
| `active` | str | Active item slug |
| `title` | str | Sidebar heading |
| `subtitle` | str | Optional subtitle |
| `storage_key` | str | localStorage key for collapse persistence |
| `extra_sidebar_sections` | list[Any] | Extra content appended to desktop sidebar |
| `extra_mobile_sections` | list[Any] | Extra content below mobile tabs |
| `page_title` | str | Browser title (defaults to `title`) |
| `request` | Request | Starlette request (auth detection) |
| `active_page` | str | Navbar active page indicator |
| `item_renderer` | Callable | Custom item rendering function |
| `title_href` | str | Optional link on sidebar title |

## Alpine.js Component: `collapsibleSidebar`

**Location:** `/static/js/skuel.js` (lines 917-953)

```javascript
Alpine.data('collapsibleSidebar', function(storageKey) {
    return {
        get collapsed() {
            var store = Alpine.store(storageKey);
            return store ? store.collapsed : false;
        },
        init: function() {
            if (!Alpine.store(storageKey)) {
                var initial = false;
                if (window.innerWidth >= 1024) {
                    initial = localStorage.getItem(storageKey + '-collapsed') === 'true';
                }
                Alpine.store(storageKey, { collapsed: initial });
            }
        },
        toggle: function() {
            var store = Alpine.store(storageKey);
            store.collapsed = !store.collapsed;
            localStorage.setItem(storageKey + '-collapsed', store.collapsed.toString());
            if (window.SKUEL && window.SKUEL.announce) {
                window.SKUEL.announce('Sidebar ' + (store.collapsed ? 'collapsed' : 'expanded'));
            }
        }
    };
});
```

**Why `Alpine.store()`:** Both the sidebar element and the content area need to read `collapsed` state. Without a shared store, two separate `x-data` instances would have independent state — the bug fixed in commit `5856a7e`.

**State flow:**
```
Alpine.store(storageKey) ← shared reactive state
├── Sidebar reads: `:class="collapsed ? '-translate-x-52' : 'translate-x-0'"`
├── Content reads: `:class="collapsed ? 'lg:ml-12' : 'lg:ml-64'"`
└── localStorage persists: `{storageKey}-collapsed`
```

## Layout Architecture

### Desktop (lg: and above)

```
┌──────────┬────────────────────────────┐
│ Sidebar  │  Content                   │
│ w-64     │  flex-1                    │
│ fixed    │  ml-64 (or ml-12 collapsed)│
│ toggle ← │                            │
└──────────┴────────────────────────────┘
```

**Sidebar:** `fixed top-16 left-0 bottom-0 w-64 transition-transform duration-300`
**Collapsed:** `-translate-x-52` (leaves 48px visible for toggle button)
**Content:** `lg:ml-64 lg:transition-[margin-left] lg:duration-300`
**Collapsed content:** `lg:ml-12`

### Mobile (below lg:)

```
┌────────────────────────────────────────┐
│ [Tab1] [Tab2] [Tab3]  ← horizontal    │
├────────────────────────────────────────┤
│ Content                                │
└────────────────────────────────────────┘
```

**Tabs:** DaisyUI `tabs tabs-bordered overflow-x-auto flex-nowrap`
**Sidebar:** `hidden lg:block` (completely hidden on mobile)
**No drawer, no overlay, no hamburger** — tabs provide all navigation.

## Implementation Patterns

### Pattern 1: Basic Sidebar (Reports)

Simplest case — flat list of items, no extra sections.

```python
# adapters/inbound/reports_ui.py
from ui.patterns.sidebar import SidebarItem, SidebarPage

REPORTS_ITEMS = [
    SidebarItem("Submit", "/submissions/submit", "submit", icon="📤"),
    SidebarItem("Browse", "/submissions/browse", "browse", icon="📂"),
    SidebarItem("Projects", "/submissions/projects", "projects", icon="📋"),
]

async def _reports_page(content, active_slug, request):
    return await SidebarPage(
        content=content,
        items=REPORTS_ITEMS,
        active=active_slug,
        title="Reports",
        storage_key="reports-sidebar",
        request=request,
        active_page="reports",
    )
```

### Pattern 2: Extra Sections (KU)

Add content below the main nav items using `extra_sidebar_sections`.

```python
# adapters/inbound/ku_ui.py
from ui.patterns.sidebar import SidebarItem, SidebarPage

KU_ITEMS = [
    SidebarItem("Self Awareness", "/ku/sel/self-awareness", "self-awareness", icon="🧠"),
    SidebarItem("Self Management", "/ku/sel/self-management", "self-management", icon="🎯"),
    # ... more SEL categories
]

# HTMX-loaded MOC section
moc_section = Div(
    H4("Maps of Content", cls="text-sm font-semibold uppercase tracking-wider opacity-60 px-3 mt-2"),
    Div(
        id="moc-list",
        hx_get="/api/ku/moc-list",
        hx_trigger="load",
        hx_swap="innerHTML",
    ),
)

return await SidebarPage(
    content=content,
    items=KU_ITEMS,
    active=active_slug,
    title="Knowledge",
    storage_key="ku-sidebar",
    extra_sidebar_sections=[moc_section],
    request=request,
    active_page="ku",
)
```

### Pattern 3: Custom Item Renderer (Profile)

Override the default item rendering for complex items with badges.

```python
# ui/profile/layout.py
from ui.patterns.sidebar import SidebarItem, SidebarPage

def _profile_item_renderer(item: SidebarItem, is_active: bool) -> "FT":
    """Custom renderer with status dot and count badge."""
    active_cls = "bg-base-200 font-semibold" if is_active else ""
    return Li(
        A(
            Span(item.icon, cls="text-lg"),
            Span(item.label, cls="flex-1"),
            # Custom badge area
            Span(item.badge_text, cls=item.badge_cls) if item.badge_text else "",
            href=item.href,
            cls=f"flex items-center gap-2 rounded-lg px-3 py-2.5 min-h-[44px] transition-colors hover:bg-base-200 {active_cls}",
            **{"hx-boost": "false"},
        )
    )

return await SidebarPage(
    content=content,
    items=profile_items,
    active=active_slug,
    title=user_display_name or "Your Profile",
    subtitle="Profile",
    storage_key="profile-sidebar",
    item_renderer=_profile_item_renderer,
    title_href="/profile",
    request=request,
    active_page="profile/hub",
)
```

### Pattern 4: Description Items (Askesis)

Items with subtitles use the built-in `description` field — no custom renderer needed.

```python
# adapters/inbound/askesis_ui.py
from ui.patterns.sidebar import SidebarItem, SidebarPage

ASKESIS_ITEMS = [
    SidebarItem(
        "Overview", "/askesis", "overview",
        icon="🏠", description="Your life context dashboard",
    ),
    SidebarItem(
        "Daily Planning", "/askesis/daily", "daily",
        icon="📅", description="AI-powered day planning",
    ),
    SidebarItem(
        "Life Path", "/askesis/life-path", "life-path",
        icon="🧭", description="Alignment & direction",
    ),
]

return await SidebarPage(
    content=content,
    items=ASKESIS_ITEMS,
    active=active_slug,
    title="Askesis",
    subtitle="Life Intelligence",
    storage_key="askesis-sidebar",
    request=request,
    active_page="askesis",
)
```

When `description` is set, the default renderer produces a two-line layout:
```
🏠 Overview
   Your life context dashboard
```

## Common Mistakes & Anti-Patterns

### Mistake 1: Duplicate `x-data` Without `Alpine.store()`

```python
# ❌ BAD: Two independent x-data instances = out-of-sync state
sidebar = Div(x_data="{ collapsed: false }", ...)
content = Div(x_data="{ collapsed: false }", ...)  # Different instance!

# ✅ GOOD: Shared store (what SidebarPage does automatically)
sidebar = Div(**{"x-data": "collapsibleSidebar('my-key')"}, ...)
content = Div(**{"x-data": "collapsibleSidebar('my-key')"}, ...)
# Both read from Alpine.store('my-key')
```

**This was the bug in commit `5856a7e`.** When sidebar collapsed, content margin didn't adjust because each element had its own state.

### Mistake 2: Using DaisyUI Drawer for Sidebar Pages

```python
# ❌ BAD: DaisyUI drawer conflicts with BasePage container padding
Div(cls="drawer lg:drawer-open", ...)

# ✅ GOOD: SidebarPage with Tailwind + Alpine
await SidebarPage(content=..., items=..., ...)
```

**Why:** DaisyUI drawer requires negative margins to negate BasePage `p-6 lg:p-8` padding, doesn't support desktop collapse (only show/hide), needs two toggle mechanisms (checkbox for mobile, JS for desktop), and conflicts with the sticky 64px navbar offset.

### Mistake 3: Custom CSS for Sidebar Behavior

```css
/* ❌ BAD: Custom CSS duplicates what Tailwind already provides */
.profile-sidebar {
    width: 256px;
    position: fixed;
    top: 64px;
    transition: transform 0.3s ease;
}

/* ✅ GOOD: Tailwind utility classes (inline in Python) */
/* fixed top-16 left-0 bottom-0 w-64 transition-transform duration-300 */
```

### Mistake 4: Mobile Overlay/Hamburger Pattern

```python
# ❌ BAD: Mobile drawer with overlay (requires FocusTrap, overlay click handler, etc.)
overlay = Div(cls="profile-overlay", onclick="toggleProfileSidebar()")
mobile_btn = Div(Span("☰"), onclick="toggleProfileSidebar()")

# ✅ GOOD: Horizontal tabs (zero JavaScript, built-in accessibility)
# SidebarPage automatically generates DaisyUI tabs for mobile
```

### Mistake 5: Forgetting `hx-boost="false"` on Nav Links

```python
# ❌ BAD: HTMX boost intercepts navigation, causes partial page load
A("Submit", href="/submissions/submit")

# ✅ GOOD: Disable boost for full page navigation
A("Submit", href="/submissions/submit", **{"hx-boost": "false"})
```

**Note:** `SidebarItem.hx_attrs` and the default renderer handle this automatically.

## Testing & Verification

### Functional Tests

- [ ] **Desktop collapse:** Sidebar collapses to 48px edge, chevron rotates 180°
- [ ] **Desktop expand:** Sidebar expands to full width, text visible
- [ ] **Mobile tabs:** Horizontal DaisyUI tabs shown, sidebar hidden
- [ ] **State persistence:** Reload page, sidebar state preserved (desktop only)
- [ ] **Shared state:** Collapse sidebar → content margin adjusts simultaneously

### Visual Tests

- [ ] **Smooth transitions:** 300ms duration, no layout shift
- [ ] **Active state:** Current item highlighted with `bg-base-200 font-semibold`
- [ ] **Text fade:** Sidebar text `opacity-0 invisible` when collapsed
- [ ] **Mobile tab overflow:** Horizontal scroll when many items

### Accessibility Tests

- [ ] **Screen reader:** `window.SKUEL.announce('Sidebar collapsed/expanded')` fires on toggle
- [ ] **ARIA:** Toggle button has `aria-label="Toggle sidebar"` and `:aria-expanded="!collapsed"`
- [ ] **Navigation landmark:** Sidebar has `role="navigation"` and `aria-label`
- [ ] **Tab role:** Mobile tabs have `role="tablist"` and individual `role="tab"`

### Import Test

```bash
poetry run python -c "from ui.patterns.sidebar import SidebarItem, SidebarNav, SidebarPage; print('OK')"
```

## Current Adopters (5 Pages)

| Page | Items | Extra Features | Storage Key |
|------|-------|----------------|-------------|
| Profile | 4-6 | Custom renderer (badges), title link | `profile-sidebar` |
| KU List | 5-6 | HTMX MOC section via extra_sidebar_sections | `ku-sidebar` |
| Reports | 3 | Basic (simplest case) | `reports-sidebar` |
| Journals | 2 | Admin-only | `journals-sidebar` |
| Askesis | 3-5 | Description items (two-line layout) | `askesis-sidebar` |

## Key Files

| File | Purpose |
|------|---------|
| `/ui/patterns/sidebar.py` | `SidebarItem`, `SidebarNav`, `SidebarPage` (~300 lines) |
| `/static/js/skuel.js` (lines 917-953) | `collapsibleSidebar` Alpine component (~37 lines) |
| `/ui/layouts/base_page.py` | `BasePage` with `PageType.CUSTOM` |
| `/ui/layouts/page_types.py` | `PageType` enum |

## Related Documentation

- `/docs/patterns/UI_COMPONENT_PATTERNS.md` - Unified Sidebar Pattern section
- `@base-page-architecture` - When to use BasePage HUB vs SidebarPage
- `@html-navigation` - For navbar and top-level navigation patterns
- `@js-alpine` - Alpine.js store pattern and reactive state
- `@tailwind-css` - Responsive breakpoints and utility classes
- `@daisyui` - Tabs, menu, badge components used in sidebar

## Historical Context

**Before (2026-02-08):** Three implementations (~590 lines custom CSS/JS):
- 4 sidebars (Profile, KU, Reports, Journals) shared `profile_sidebar.css` (172 lines) + `profile_sidebar.js` (121 lines)
- 1 sidebar (Askesis) had inline CSS/JS (~300 lines) with different breakpoints

**After (commit `949f201`, 2026-02-09):** One component (~300 lines Python + ~37 lines Alpine):
- Single `SidebarPage()` function for all 5 pages
- `profile_sidebar.css` and `profile_sidebar.js` deleted
- Consistent breakpoints (lg: 1024px) across all pages
- Shared state via `Alpine.store()` prevents the duplicate-state bug
