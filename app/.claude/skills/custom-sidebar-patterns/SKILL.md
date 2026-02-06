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

> "BasePage handles standard layouts - custom sidebars provide domain-specific navigation with fine-grained control over collapse behavior, state persistence, and responsive patterns."

SKUEL uses **BasePage** for most layouts, but complex navigation requirements (like Profile Hub's multi-domain navigation) benefit from custom sidebar implementations that provide:

- **State persistence** via localStorage (survives page reloads)
- **Responsive transforms** (desktop collapse vs mobile drawer)
- **Domain-specific structure** (curriculum sections, account actions, insights)
- **Smooth animations** with pure CSS transitions

## When to Use This Skill

Choose custom sidebar patterns when:

- ✅ Navigation requires **multi-level sections** (Curriculum, Account, etc.)
- ✅ Sidebar state must **persist across sessions** (localStorage)
- ✅ Need **fine-grained control** over collapse behavior (desktop vs mobile)
- ✅ Domain items have **dynamic badges/indicators** (counts, status, insights)
- ✅ Sidebar has **complex interactions** (drag-to-resize, nested menus)

Use **BasePage HUB** instead when:

- ⚠️ Simple left sidebar with static menu items
- ⚠️ No state persistence needed
- ⚠️ Standard responsive drawer pattern sufficient

**Decision Tree:**

```
Does sidebar need multi-section structure (Curriculum + Account)?
├─ YES → Custom Sidebar Pattern ✓
└─ NO → Does sidebar state need localStorage persistence?
    ├─ YES → Custom Sidebar Pattern ✓
    └─ NO → Does sidebar have dynamic badges/counts?
        ├─ YES → Custom Sidebar Pattern ✓
        └─ NO → BasePage HUB is sufficient
```

## Core Concepts

### 1. Three-Layer Architecture

Custom sidebars use a **three-layer stack**:

| Layer | Technology | Responsibility |
|-------|------------|----------------|
| **HTML Structure** | Python (FastHTML) | Sidebar menu, toggle button, overlay |
| **CSS Animations** | Pure CSS | Smooth transitions, responsive breakpoints |
| **State Management** | Vanilla JS | Toggle function, localStorage persistence |

**Key Principle:** Keep it simple. No Alpine.js for basic toggle - vanilla JS is lighter and more maintainable for this pattern.

### 2. Profile Hub Pattern (Reference Implementation)

The **Profile Hub** (`/ui/profile/layout.py`) is SKUEL's canonical custom sidebar implementation:

**Key Features:**
- Fixed sidebar (256px) collapses to 48px edge on desktop
- Full-width drawer with overlay on mobile
- localStorage persists collapsed state
- Multi-section navigation (Overview, Shared With Me, Curriculum, Account)
- Dynamic badges (count, status, insights) for curriculum domains

**Files:**
- `/ui/profile/layout.py` - `build_profile_sidebar()`, `create_profile_page()`
- `/static/css/profile_sidebar.css` - Animations and responsive behavior
- `/static/js/profile_sidebar.js` - Toggle function with persistence

### 3. Responsive Transform Pattern

```
Desktop (>1024px):
┌────────┬──────────────┐
│        │              │
│ Sidebar│   Content    │  ← Sidebar collapses to 48px edge
│ (256px)│              │
└────────┴──────────────┘

Mobile (≤1024px):
┌──────────────────────┐
│      Content         │  ← Sidebar slides in as overlay
└──────────────────────┘
     ↓ (tap menu)
┌────────┬─────────────┐
│ Sidebar│  Overlay    │  ← Full-width drawer
│ (85%)  │  (dimmed)   │
└────────┴─────────────┘
```

**Implementation:**
- Desktop: `transform: translateX(-208px)` (leaves 48px edge visible)
- Mobile: `transform: translateX(-100%)` (completely off-screen)
- Overlay: `display: none` (desktop) → `display: block` (mobile)

### 4. State Persistence Pattern

```javascript
// Save state on toggle
localStorage.setItem('profile-sidebar-collapsed', profileSidebarCollapsed);

// Restore on page load
const savedState = localStorage.getItem('profile-sidebar-collapsed');
if (savedState === 'true') {
    toggleProfileSidebar();  // Apply collapsed state
}
```

**Key:** Desktop restores saved state, mobile always starts collapsed.

### 5. Domain Item Configuration

Use dataclasses for type-safe sidebar items:

```python
@dataclass
class ProfileDomainItem:
    """Sidebar item for a domain."""
    name: str           # "Tasks", "Habits"
    slug: str           # "tasks", "habits"
    icon: str           # Emoji icon
    count: int          # Total items
    active_count: int   # Active/pending items
    status: str         # "healthy", "warning", "critical"
    href: str           # "/profile/tasks"
    insight_count: int = 0  # Active insights badge
```

## Implementation Patterns

### Pattern 1: Build Sidebar Function

**Purpose:** Construct sidebar HTML with sections, badges, toggle button

**Implementation:**

```python
from fasthtml.common import Anchor, Button, Div, Li, P, Span, Ul, NotStr

def build_profile_sidebar(
    domains: list[ProfileDomainItem],
    active_domain: str = "",
    user_display_name: str = "",
    curriculum_domains: list[ProfileDomainItem] | None = None,
) -> "FT":
    """Build the profile sidebar navigation using /nous-style pattern.

    Args:
        domains: Activity domain items for sidebar navigation
        active_domain: Currently active domain slug (empty = overview)
        user_display_name: User's display name for header
        curriculum_domains: Optional curriculum domain items

    Returns:
        Sidebar component with toggle button and navigation
    """
    display_name = user_display_name or "Your Profile"
    is_overview_active = active_domain == ""

    # Build activity domain items
    activity_items = [_domain_menu_item(d, d.slug == active_domain) for d in domains]

    # Build curriculum section if provided
    curriculum_section = []
    if curriculum_domains:
        curriculum_section = [
            # Section header
            Li(
                Span("Curriculum", cls="text-xs font-semibold uppercase tracking-wider opacity-60"),
                cls="menu-title",
            ),
            # Navigation items
            *[_domain_menu_item(d, d.slug == active_domain) for d in curriculum_domains],
        ]

    # Chevron icon for toggle button
    chevron_svg = NotStr(
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
        '<path d="M15 18l-6-6 6-6"></path>'
        '</svg>'
    )

    # Build sidebar menu content
    sidebar_menu = Ul(
        # Profile header
        Li(
            Anchor(
                display_name,
                href="/profile",
                cls="text-xl font-bold text-primary hover:text-primary-focus",
                **{"hx-boost": "false"},
            ),
            P("Profile", cls="text-xs opacity-60 mt-1"),
            cls="px-4 py-4 sidebar-header-text",
        ),
        # Divider
        Li(cls="divider my-0"),
        # Overview link
        Li(
            Anchor(
                Span("📊", cls="text-lg"),
                "Overview",
                href="/profile",
                cls=f"flex items-center gap-2 {'menu-active' if is_overview_active else ''}",
                **{"hx-boost": "false"},
            )
        ),
        # Activity Domains section
        Li(
            Span("Activity Domains", cls="text-xs font-semibold uppercase tracking-wider opacity-60"),
            cls="menu-title",
        ),
        *activity_items,
        # Curriculum section (if provided)
        *curriculum_section,
        cls="menu bg-white min-h-full w-full p-4 sidebar-nav",
    )

    return Div(
        Div(
            # Toggle button (chevron icon, right side)
            Button(
                chevron_svg,
                onclick="toggleProfileSidebar()",
                cls="sidebar-toggle",
                title="Toggle Sidebar",
                type="button",
            ),
            # Sidebar navigation
            sidebar_menu,
            cls="sidebar-inner",
        ),
        cls="profile-sidebar",
        id="profile-sidebar",
    )
```

**Key Details:**
- **Sections:** Use `Li(cls="menu-title")` for section headers
- **Active state:** Apply `menu-active` class to current domain
- **SVG icons:** Use `NotStr()` for inline SVG (chevron, etc.)
- **hx-boost: false:** Disable HTMX boost for standard navigation

### Pattern 2: Domain Menu Item with Badges

**Purpose:** Single navigation item with count, status, insight badges

**Implementation:**

```python
def _domain_menu_item(domain: ProfileDomainItem, is_active: bool) -> "FT":
    """Single domain navigation item with badges."""
    active_cls = "menu-active" if is_active else ""

    # Build badges - include insight badge if available
    badges = [
        _count_badge(domain.count, domain.active_count),
        _status_badge(domain.status),
    ]

    # Add insight badge if there are insights
    insight_badge = _insight_badge(domain.insight_count)
    if insight_badge:
        badges.append(insight_badge)

    return Li(
        Anchor(
            Span(domain.icon, cls="text-lg"),
            Span(domain.name, cls="flex-1"),
            Div(
                *badges,
                cls="flex items-center gap-2",
            ),
            href=domain.href,
            cls=f"flex items-center gap-2 {active_cls}",
            x_on_click="closeOnMobile()",  # Close drawer on mobile after click
            **{"hx-boost": "false"},
        )
    )

def _status_badge(status: str) -> "FT":
    """Status indicator dot."""
    color_map = {
        "healthy": "bg-success",
        "warning": "bg-warning",
        "critical": "bg-error",
    }
    color = color_map.get(status, "bg-base-content/50")
    return Span(cls=f"w-2 h-2 rounded-full {color}", title=f"Status: {status}")

def _count_badge(count: int, active: int | None = None) -> "FT":
    """Count badge showing total (optionally with active subset)."""
    text = f"{active}/{count}" if active is not None and active > 0 else str(count)
    return Span(text, cls="badge badge-sm badge-ghost")

def _insight_badge(insight_count: int) -> Optional["FT"]:
    """Insight count badge (bell icon + count)."""
    if insight_count <= 0:
        return None

    bell_svg = NotStr(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3">'
        '<path d="M10 2a6 6 0 00-6 6v3.586l-.707.707A1 1 0 004 14h12a1 1 0 00.707-1.707L16 11.586V8a6 6 0 00-6-6zM10 18a3 3 0 01-3-3h6a3 3 0 01-3 3z"/>'
        '</svg>'
    )

    return Span(
        bell_svg,
        Span(str(insight_count), cls="text-xs font-bold"),
        cls="badge badge-xs badge-warning gap-1",
        title=f"{insight_count} active insight{'s' if insight_count != 1 else ''}",
    )
```

**Badge Types:**
- **Count:** `active/total` or just `total`
- **Status:** Color-coded dot (green/yellow/red)
- **Insights:** Bell icon with number

### Pattern 3: CSS Animations (Desktop Collapse)

**Purpose:** Smooth sidebar collapse with visible edge, content margin shift

**Implementation (`profile_sidebar.css`):**

```css
/* Container */
.profile-container {
    display: flex;
    min-height: 100vh;
    position: relative;
}

/* Sidebar - Fixed position */
.profile-sidebar {
    width: 256px;
    background-color: oklch(var(--color-base-200));
    border-right: 1px solid oklch(var(--color-base-300));
    transition: transform 0.3s ease;
    position: fixed;
    top: 64px;  /* Below navbar */
    left: 0;
    bottom: 0;
    z-index: 40;
    transform: translateX(0);
    overflow-y: auto;
}

/* Collapsed state (desktop) */
.profile-sidebar.collapsed {
    transform: translateX(-208px);  /* Leaves 48px edge visible */
}

/* Content area - Margin adjusts with sidebar */
.profile-content {
    flex: 1;
    margin-left: 256px;
    transition: margin-left 0.3s ease;
    min-height: calc(100vh - 64px);
    margin-top: 64px;
}

.profile-content.expanded {
    margin-left: 48px;  /* When sidebar collapsed */
}

/* Toggle button - Positioned on sidebar */
.sidebar-toggle {
    position: absolute;
    right: 8px;
    top: 16px;
    background: oklch(var(--color-base-100));
    border: 1px solid oklch(var(--color-base-300));
    cursor: pointer;
    padding: 8px;
    border-radius: 6px;
    transition: background 0.2s, transform 0.3s;
    z-index: 5;
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.sidebar-toggle:hover {
    background: oklch(var(--color-base-200));
}

/* Rotate chevron when collapsed */
.sidebar-toggle svg {
    transition: transform 0.3s ease;
}

.profile-sidebar.collapsed .sidebar-toggle svg {
    transform: rotate(180deg);
}

/* Hide text when collapsed */
.profile-sidebar.collapsed .sidebar-nav,
.profile-sidebar.collapsed .sidebar-header-text {
    opacity: 0;
    visibility: hidden;
}
```

**Key Principles:**
- **Fixed positioning:** Sidebar stays put, content scrolls
- **Transform transitions:** Smooth 300ms ease for collapse
- **Visibility toggle:** Fade out text (opacity + visibility) when collapsed
- **Chevron rotation:** Visual feedback of collapse state

### Pattern 4: Mobile Drawer Responsiveness

**Purpose:** Full-width overlay drawer on mobile, standard collapse on desktop

**Implementation (`profile_sidebar.css`):**

```css
/* Mobile overlay */
.profile-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 35;
    display: none;
}

.profile-overlay.active {
    display: block;
}

/* Mobile responsiveness */
@media (max-width: 1024px) {
    .profile-sidebar {
        width: 85%;
        max-width: 320px;
        top: 0;  /* Full height on mobile */
        transform: translateX(-100%);  /* Completely off-screen */
    }

    .profile-sidebar:not(.collapsed) {
        transform: translateX(0);  /* Slide in when open */
    }

    .profile-content {
        margin-left: 0;  /* Full width on mobile */
        margin-top: 64px;
    }

    .profile-content.expanded {
        margin-left: 0;
    }

    .sidebar-toggle {
        display: none;  /* Hide desktop toggle on mobile */
    }

    .mobile-menu-button {
        display: flex !important;
    }

    .profile-overlay {
        top: 0;
    }
}

@media (min-width: 1025px) {
    .mobile-menu-button {
        display: none !important;
    }
}
```

**Mobile Menu Button (in content area):**

```python
mobile_menu = Div(
    Span("☰", cls="text-xl"),
    Span("Menu", cls="ml-2"),
    cls="btn btn-ghost mobile-menu-button mb-4",
    onclick="toggleProfileSidebar()",
)
```

### Pattern 5: JavaScript Toggle with Persistence

**Purpose:** Toggle sidebar state, save to localStorage, handle responsive behavior

**Implementation (`profile_sidebar.js`):**

```javascript
let profileSidebarCollapsed = false;

function toggleProfileSidebar() {
    const sidebar = document.getElementById('profile-sidebar');
    const content = document.getElementById('profile-content');
    const overlay = document.getElementById('profile-overlay');

    if (!sidebar || !content || !overlay) {
        console.warn('Profile sidebar elements not found');
        return;
    }

    profileSidebarCollapsed = !profileSidebarCollapsed;

    if (profileSidebarCollapsed) {
        sidebar.classList.add('collapsed');
        content.classList.add('expanded');
        overlay.classList.remove('active');
    } else {
        sidebar.classList.remove('collapsed');
        content.classList.remove('expanded');

        // Show overlay on mobile
        if (window.innerWidth <= 1024) {
            overlay.classList.add('active');
        }
    }

    // Save state to localStorage
    localStorage.setItem('profile-sidebar-collapsed', profileSidebarCollapsed);
}

// Restore saved state on load
document.addEventListener('DOMContentLoaded', function() {
    const savedState = localStorage.getItem('profile-sidebar-collapsed');

    // Desktop: restore saved state
    if (window.innerWidth > 1024 && savedState === 'true') {
        toggleProfileSidebar();
    }

    // Mobile: always start collapsed
    if (window.innerWidth <= 1024) {
        profileSidebarCollapsed = false;
        toggleProfileSidebar();
    }
});

// Handle window resize
window.addEventListener('resize', function() {
    const overlay = document.getElementById('profile-overlay');
    if (overlay && window.innerWidth > 1024) {
        overlay.classList.remove('active');
    }
});
```

**Key Logic:**
- **Toggle:** Flip collapsed state, apply classes
- **Overlay:** Show on mobile when open, hide on desktop
- **Persistence:** Save to localStorage after toggle
- **Restore:** Apply saved state on page load (desktop only)
- **Resize:** Hide overlay when switching to desktop

### Pattern 6: Create Page Function (Integration with BasePage)

**Purpose:** Wrap sidebar + content using BasePage for consistency

**Implementation:**

```python
def create_profile_page(
    content: Any,
    domains: list[ProfileDomainItem],
    active_domain: str = "",
    user_display_name: str = "",
    title: str = "Profile",
    curriculum_domains: list[ProfileDomainItem] | None = None,
    request: "Request | None" = None,
) -> "FT":
    """Create profile page using BasePage with /nous-style sidebar.

    Args:
        content: Main content HTML
        domains: List of ProfileDomainItem for sidebar (Activity Domains)
        active_domain: Currently active domain slug (empty = overview)
        user_display_name: User's display name for header
        title: Page title
        curriculum_domains: List of ProfileDomainItem for curriculum section
        request: Starlette request (enables BasePage auto-detection of auth/admin)

    Returns:
        Complete HTML page using BasePage with custom sidebar layout
    """
    # Build sidebar navigation
    sidebar = build_profile_sidebar(
        domains=domains,
        active_domain=active_domain,
        user_display_name=user_display_name,
        curriculum_domains=curriculum_domains,
    )

    # Build mobile overlay
    overlay = Div(
        cls="profile-overlay",
        id="profile-overlay",
        onclick="toggleProfileSidebar()",
    )

    # Mobile menu button
    mobile_menu = Div(
        Span("☰", cls="text-xl"),
        Span("Menu", cls="ml-2"),
        cls="btn btn-ghost mobile-menu-button mb-4",
        onclick="toggleProfileSidebar()",
    )

    # Wrap content with sidebar + overlay
    wrapped_content = Div(
        overlay,
        sidebar,
        Div(
            mobile_menu,
            Main(
                Div(content, cls="max-w-6xl mx-auto"),
                cls="p-6 lg:p-8",
            ),
            cls="profile-content",
            id="profile-content",
        ),
        cls="profile-container",
    )

    # Use BasePage with STANDARD type (we handle layout ourselves)
    return BasePage(
        content=wrapped_content,
        title=title,
        page_type=PageType.STANDARD,
        request=request,
        active_page="profile/hub",
        extra_css=["/static/css/profile_sidebar.css"],
        user_display_name=user_display_name,
    )
```

**Integration Points:**
- **BasePage:** Provides navbar, auth detection, consistent page structure
- **PageType.STANDARD:** No BasePage sidebar - we manage our own layout
- **extra_css:** Load custom sidebar CSS
- **Wrapped content:** Three layers (overlay, sidebar, content)

### Pattern 7: Mobile Auto-Close on Navigation

**Purpose:** Close drawer automatically after user clicks a link on mobile

**Implementation:**

```python
# In _domain_menu_item function
return Li(
    Anchor(
        # ... content ...
        href=domain.href,
        x_on_click="closeOnMobile()",  # Alpine.js directive
        **{"hx-boost": "false"},
    )
)
```

**JavaScript helper:**

```javascript
// In skuel.js or profile_sidebar.js
function closeOnMobile() {
    if (window.innerWidth <= 1024 && !profileSidebarCollapsed) {
        toggleProfileSidebar();  // Close drawer on mobile
    }
}
```

**Why:** Improves mobile UX - user doesn't have to manually close drawer after navigation.

### Pattern 8: Multi-Section Navigation

**Purpose:** Group domains into logical sections (Activity, Curriculum, Admin)

**Implementation:**

```python
# Define section headers
ACTIVITY_DOMAINS = ["tasks", "events", "goals", "habits", "principles", "choices"]
CURRICULUM_DOMAINS = ["learning"]

# Build sections
activity_section = [
    Li(Span("Activity Domains", cls="text-xs font-semibold uppercase tracking-wider opacity-60"), cls="menu-title"),
    *[_domain_menu_item(d, d.slug == active_domain) for d in activity_domains],
]

curriculum_section = [
    Li(Span("Curriculum", cls="text-xs font-semibold uppercase tracking-wider opacity-60"), cls="menu-title"),
    *[_domain_menu_item(d, d.slug == active_domain) for d in curriculum_domains],
]

# Combine in sidebar
sidebar_menu = Ul(
    # Header
    Li(...),
    # Overview
    Li(...),
    # Activity section
    *activity_section,
    # Curriculum section
    *curriculum_section,
    cls="menu bg-white min-h-full w-full p-4 sidebar-nav",
)
```

**DaisyUI Menu Title Pattern:**
```html
<li class="menu-title">
  <span class="text-xs font-semibold uppercase tracking-wider opacity-60">Section Name</span>
</li>
```

## Real-World Examples

### Example 1: Profile Hub Implementation

**File:** `/home/mike/skuel/app/ui/profile/layout.py`

**Usage in route:**

```python
from ui.profile.layout import create_profile_page, ProfileDomainItem

@rt("/profile")
async def profile_hub(request):
    user_uid = require_authenticated_user(request)

    # Build domain items
    domains = [
        ProfileDomainItem(
            name="Tasks",
            slug="tasks",
            icon="✅",
            count=42,
            active_count=10,
            status="healthy",
            href="/profile/tasks",
            insight_count=2,
        ),
        ProfileDomainItem(
            name="Goals",
            slug="goals",
            icon="🎯",
            count=8,
            active_count=3,
            status="warning",
            href="/profile/goals",
            insight_count=0,
        ),
        # ... more domains
    ]

    # Create page with custom sidebar
    return create_profile_page(
        content=main_content,
        domains=domains,
        active_domain="",  # Overview active
        user_display_name="John Doe",
        title="Profile Hub",
        request=request,
    )
```

### Example 2: Admin Dashboard Sidebar

**Alternative pattern using BasePage HUB:**

```python
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType

def create_admin_sidebar():
    """Simple admin menu - no custom collapse needed."""
    return Ul(
        Li(Anchor("Dashboard", href="/admin")),
        Li(Anchor("Users", href="/admin/users")),
        Li(Anchor("Settings", href="/admin/settings")),
        cls="menu bg-white w-64 min-h-full",
    )

return BasePage(
    content,
    page_type=PageType.HUB,
    sidebar=create_admin_sidebar(),
    title="Admin Dashboard",
    request=request,
)
```

**When to use BasePage HUB vs Custom:**
- **HUB:** Simple static menu, no persistence, standard drawer
- **Custom:** Multi-section, badges, persistence, fine-grained control

### Example 3: SEL Pages (Profile Sidebar on a Non-Profile Domain)

**File:** `/home/mike/skuel/app/adapters/inbound/sel_ui.py`

SEL is the second domain to adopt the profile sidebar pattern. It reuses `profile_sidebar.css` and `profile_sidebar.js` directly — no new CSS or JS files needed.

**Key differences from Profile Hub:**
- Sidebar content is static (6 fixed menu items, no badges or domain stats)
- `_sel_sidebar()` and `_sel_page_layout()` are module-level helpers, not imported from a shared layout module
- `extra_css=["/static/css/profile_sidebar.css"]` is passed explicitly on each `BasePage` call

**Usage in route:**

```python
from fasthtml.common import A as Anchor, Button, Li, Main, NotStr, P, Span, Ul

SEL_MENU_ITEMS = [
    ("Overview", "/sel", "overview", "Introduction to SEL"),
    ("Self Awareness", "/sel/self-awareness", "self-awareness", "..."),
    # ... 4 more items
]

def _sel_sidebar(active_slug: str):
    """Sidebar Div — same IDs profile_sidebar.js expects."""
    menu_items = [
        Li(Anchor(title, href=href,
                  cls=f"{'menu-active' if slug == active_slug else ''}",
                  **{"hx-boost": "false",
                     "onclick": "if(window.innerWidth<=1024)toggleProfileSidebar()"}))
        for title, href, slug, _desc in SEL_MENU_ITEMS
    ]
    return Div(
        Div(
            Button(..., cls="sidebar-toggle", onclick="toggleProfileSidebar()"),
            Ul(...menu_items, cls="menu bg-white min-h-full w-full p-4 sidebar-nav",
               id="sel-sidebar-nav"),
            cls="sidebar-inner",
        ),
        id="profile-sidebar", cls="profile-sidebar", role="dialog",
    )

def _sel_page_layout(active_slug: str, content: Any):
    """Profile-container shell — identical structure to create_profile_page()."""
    return Div(
        Div(id="profile-overlay", cls="profile-overlay", onclick="toggleProfileSidebar()"),
        _sel_sidebar(active_slug),
        Div(id="sidebar-sr-announcements", role="status", aria_live="polite", cls="sr-only"),
        Div(
            Div(Span("☰"), Span("Menu"),
                cls="btn btn-ghost mobile-menu-button mb-4",
                onclick="toggleProfileSidebar()", role="button", tabindex="0",
                aria_label="Open SEL navigation", aria_controls="profile-sidebar"),
            Main(Div(content, cls="max-w-6xl mx-auto"), cls="p-6 lg:p-8"),
            id="profile-content", cls="profile-content",
        ),
        cls="profile-container",
    )

# Route handler
@rt("/sel")
async def sel_main(request: Request) -> Any:
    content = Div(...)
    page_layout = _sel_page_layout("overview", content)
    return await BasePage(
        page_layout,
        title="SEL - Social Emotional Learning",
        page_type=PageType.STANDARD,
        request=request,
        active_page="sel",
        extra_css=["/static/css/profile_sidebar.css"],   # ← the only addition vs Profile Hub
    )
```

**Required element IDs (enforced by `profile_sidebar.js`):**

| ID | Element | Role |
|----|---------|------|
| `profile-sidebar` | Outer sidebar Div | Toggle target; receives `collapsed` class |
| `profile-content` | Content wrapper Div | Receives `expanded` class |
| `profile-overlay` | Mobile overlay Div | Receives `active` class |
| `sidebar-sr-announcements` | Live region Div | Screen-reader drawer state announcements |

## Common Mistakes & Anti-Patterns

### Mistake 1: Using Alpine.js for Simple Toggle

```python
# ❌ BAD: Overcomplicated with Alpine.js
Div(
    x_data="{ sidebarOpen: $persist(false) }",
    x_on_click="sidebarOpen = !sidebarOpen",
    # ... complex Alpine logic
)

# ✅ GOOD: Simple vanilla JS
Div(
    onclick="toggleProfileSidebar()",
    id="profile-sidebar",
)
```

**Why:** Vanilla JS is lighter, easier to debug, and sufficient for basic toggle.

### Mistake 2: Forgetting Mobile Overlay Click Handler

```python
# ❌ BAD: Overlay doesn't close sidebar
overlay = Div(cls="profile-overlay", id="profile-overlay")

# ✅ GOOD: Clicking overlay closes sidebar
overlay = Div(
    cls="profile-overlay",
    id="profile-overlay",
    onclick="toggleProfileSidebar()",
)
```

### Mistake 3: Not Hiding Desktop Toggle on Mobile

```css
/* ❌ BAD: Desktop toggle visible on mobile (confusing) */
.sidebar-toggle {
    display: flex;
}

/* ✅ GOOD: Hide desktop toggle on mobile */
@media (max-width: 1024px) {
    .sidebar-toggle {
        display: none;
    }
}
```

### Mistake 4: Hardcoding Sidebar Width Without Container Adjustment

```css
/* ❌ BAD: Content doesn't adjust when sidebar collapses */
.profile-content {
    margin-left: 256px;
    /* No transition */
}

/* ✅ GOOD: Content margin transitions with sidebar */
.profile-content {
    margin-left: 256px;
    transition: margin-left 0.3s ease;
}

.profile-content.expanded {
    margin-left: 48px;
}
```

### Mistake 5: Not Differentiating Mobile/Desktop Restore Logic

```javascript
// ❌ BAD: Mobile starts with last saved state (confusing)
document.addEventListener('DOMContentLoaded', function() {
    const savedState = localStorage.getItem('profile-sidebar-collapsed');
    if (savedState === 'true') {
        toggleProfileSidebar();  // Applied on mobile too!
    }
});

// ✅ GOOD: Only restore on desktop
document.addEventListener('DOMContentLoaded', function() {
    const savedState = localStorage.getItem('profile-sidebar-collapsed');

    // Desktop: restore saved state
    if (window.innerWidth > 1024 && savedState === 'true') {
        toggleProfileSidebar();
    }

    // Mobile: always start collapsed
    if (window.innerWidth <= 1024) {
        profileSidebarCollapsed = false;
        toggleProfileSidebar();
    }
});
```

## Testing & Verification Checklist

When implementing custom sidebars, verify:

### Functional Tests

- [ ] **Desktop collapse:** Sidebar collapses to 48px edge, chevron rotates
- [ ] **Desktop expand:** Sidebar expands to full width, text visible
- [ ] **Mobile drawer:** Sidebar slides in from left, overlay dims background
- [ ] **Mobile close:** Clicking overlay closes drawer
- [ ] **Auto-close:** Clicking navigation link closes mobile drawer
- [ ] **State persistence:** Reload page, sidebar state preserved (desktop only)
- [ ] **Resize handling:** Switch from desktop to mobile, overlay hides

### Visual Tests

- [ ] **Smooth transitions:** 300ms ease, no jank
- [ ] **Badge alignment:** Count, status, insights align properly
- [ ] **Section headers:** Uppercase, reduced opacity, proper spacing
- [ ] **Active state:** Current domain highlighted
- [ ] **Hover states:** Links, buttons show hover feedback
- [ ] **Text fade:** Sidebar text fades out when collapsed (not instant hide)

### Accessibility Tests

- [ ] **Keyboard navigation:** Tab through menu items
- [ ] **Screen reader:** Menu structure announced correctly
- [ ] **Focus management:** Focus visible, trapped in drawer on mobile
- [ ] **ARIA labels:** Toggle button has aria-label

### Responsive Tests

- [ ] **Breakpoint 1024px:** Transitions properly between desktop/mobile
- [ ] **Small mobile (320px):** Sidebar 85% width, readable
- [ ] **Large desktop (1920px):** Sidebar proportions correct

## Related Documentation

### SKUEL Documentation

- `/docs/patterns/UI_COMPONENT_PATTERNS.md` - Lines 77-130 (Profile Hub Custom Sidebar Pattern)
- `/ui/profile/layout.py` - Reference implementation
- `/static/css/profile_sidebar.css` - Complete CSS
- `/static/js/profile_sidebar.js` - Toggle logic

### Related Patterns

- **BasePage Architecture:** For standard page layouts
- **HTML Navigation:** For navbar and top-level navigation
- **Alpine.js:** For complex UI state (when vanilla JS insufficient)
- **Tailwind CSS:** For utility classes and responsive breakpoints

## See Also

- `base-page-architecture` - When to use BasePage HUB vs custom sidebar
- `html-navigation` - For navbar and top-level navigation patterns
- `js-alpine` - For complex sidebar interactions (nested menus, drag-to-resize)
- `tailwind-css` - For responsive breakpoints and utility classes
- `daisyui` - For menu, divider, badge components
