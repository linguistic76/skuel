---
name: html-navigation
description: Expert guide for building navigation components. Use when creating navbars, sidebars, mobile menus, breadcrumbs, or responsive navigation that combines HTML structure, HTMX server communication, and Alpine.js client state.
allowed-tools: Read, Grep, Glob
---

# HTML Navigation: Structure + State + Communication

## Core Philosophy

> "Navigation is the skeleton of user experience - semantic HTML provides accessibility, Alpine.js manages UI state, HTMX handles server communication."

Navigation components require three distinct concerns working in harmony:

| Layer | Technology | Responsibility |
|-------|------------|----------------|
| **Structure** | Semantic HTML | Accessibility, SEO, keyboard navigation |
| **State** | Alpine.js | Menu toggles, dropdowns, mobile menu visibility |
| **Communication** | HTMX | Content loading, URL updates, partial page updates |

**The Rule:** HTML provides the skeleton, Alpine.js animates it, HTMX connects it to the server.

## Quick Start: Minimal Navbar

```html
<!-- Complete navbar with mobile toggle and profile dropdown -->
<nav x-data="{ mobileOpen: false, profileOpen: false }"
     class="navbar bg-white border-b border-gray-200 sticky top-0 z-50"
     aria-label="Main navigation">

    <!-- Mobile menu button -->
    <button @click="mobileOpen = !mobileOpen"
            class="btn btn-ghost sm:hidden"
            aria-label="Toggle menu">
        <span x-show="!mobileOpen">☰</span>
        <span x-show="mobileOpen" x-cloak>✕</span>
    </button>

    <!-- Logo -->
    <a href="/" class="text-xl font-bold">SKUEL</a>

    <!-- Desktop navigation -->
    <div class="hidden sm:flex space-x-2">
        <a href="/dashboard" class="btn btn-ghost">Dashboard</a>
        <a href="/search" class="btn btn-ghost">Search</a>
        <a href="/calendar" class="btn btn-ghost">Calendar</a>
    </div>

    <!-- Profile dropdown -->
    <div class="relative" @click.outside="profileOpen = false">
        <button @click="profileOpen = !profileOpen" class="btn btn-circle">
            <span class="sr-only">Open user menu</span>
            U
        </button>
        <div x-show="profileOpen" x-transition x-cloak
             class="absolute right-0 mt-2 w-48 bg-base-100 rounded-lg shadow-lg">
            <a href="/profile" class="block px-4 py-2">Profile</a>
            <a href="/settings" class="block px-4 py-2">Settings</a>
            <a href="/logout" class="block px-4 py-2">Sign out</a>
        </div>
    </div>

    <!-- Mobile menu -->
    <div x-show="mobileOpen" x-transition x-cloak class="sm:hidden">
        <a href="/dashboard" class="block px-3 py-2">Dashboard</a>
        <a href="/search" class="block px-3 py-2">Search</a>
        <a href="/calendar" class="block px-3 py-2">Calendar</a>
    </div>
</nav>
```

## Navigation Item Configuration

### Type-Safe NavItem Pattern

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class NavItem:
    """Immutable navigation item configuration."""
    label: str           # Display text
    href: str            # URL path
    page_key: str        # Key for active state matching
    requires_auth: bool = True
    requires_admin: bool = False

# Main navigation items - order determines display order
MAIN_NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem("Profile Hub", "/profile/hub", "profile/hub"),
    NavItem("Search", "/search", "search"),
    NavItem("Calendar", "/calendar", "calendar"),
)

# Admin-only item - prepended when user is admin
ADMIN_NAV_ITEM = NavItem(
    label="Admin Dashboard",
    href="/admin",
    page_key="admin",
    requires_admin=True,
)
```

### Rendering Navigation Links

```python
def _nav_link(item: NavItem, active_page: str, mobile: bool = False) -> A:
    """Create a navigation link with active state styling."""
    is_active = item.page_key == active_page

    if mobile:
        base_cls = "block rounded-md px-3 py-2 text-base font-medium"
    else:
        base_cls = "rounded-md px-3 py-2 text-sm font-medium"

    active_cls = "bg-base-300 text-base-content"
    inactive_cls = "text-base-content/70 hover:bg-base-300"

    cls = f"{base_cls} {active_cls if is_active else inactive_cls}"
    return A(item.label, href=item.href, cls=cls)
```

## Alpine.js Navbar Component

### Component Definition (in skuel.js)

```javascript
document.addEventListener('alpine:init', () => {
    Alpine.data('navbar', function() {
        return {
            mobileMenuOpen: false,
            profileMenuOpen: false,

            toggleMobile() {
                this.mobileMenuOpen = !this.mobileMenuOpen;
            },

            toggleProfile() {
                this.profileMenuOpen = !this.profileMenuOpen;
            },

            closeProfile() {
                this.profileMenuOpen = false;
            },

            init() {
                // Close profile menu when clicking outside
                document.addEventListener('click', (e) => {
                    const profileButton = e.target.closest('[data-profile-trigger]');
                    const profileMenu = document.getElementById('profile-dropdown');

                    if (!profileButton && profileMenu && !profileMenu.contains(e.target)) {
                        this.profileMenuOpen = false;
                    }
                });
            }
        };
    });
});
```

### FastHTML Usage

```python
from fasthtml.common import Nav, Div, Button, A

def create_navbar(current_user: str | None, active_page: str = "") -> Nav:
    return Nav(
        # Desktop links
        Div(
            *[_nav_link(item, active_page) for item in MAIN_NAV_ITEMS],
            cls="hidden sm:flex sm:space-x-1",
        ),
        # Mobile menu button
        Button(
            Span("☰", **{"x-show": "!mobileMenuOpen"}),
            Span("✕", **{"x-show": "mobileMenuOpen", "x-cloak": ""}),
            type="button",
            cls="btn btn-ghost sm:hidden",
            **{"@click": "toggleMobile()"},
        ),
        # Alpine.js state management
        **{"x-data": "navbar()"},
        cls="navbar bg-white border-b border-gray-200 sticky top-0 z-50",
    )
```

## HTMX Integration for Navigation

### SPA-Like Navigation

Use HTMX to update only the main content area without full page reload:

```html
<nav aria-label="Main navigation">
    <a href="/"
       hx-get="/"
       hx-target="main"
       hx-push-url="true"
       hx-swap="innerHTML">
        Home
    </a>
    <a href="/about"
       hx-get="/about"
       hx-target="main"
       hx-push-url="true"
       hx-swap="innerHTML">
        About
    </a>
</nav>

<main id="main">
    <!-- Content updated by HTMX -->
</main>
```

### When to Use HTMX vs Standard Links

| Scenario | Approach | Why |
|----------|----------|-----|
| Main content swap | HTMX | Preserves navbar/footer, feels like SPA |
| Full page transition | Standard link | Different layout, authentication change |
| External links | Standard link | Different domain |
| File downloads | Standard link | Browser handles download |

### HTMX Navigation with Active State

```python
def nav_link_htmx(item: NavItem, active_page: str, target: str = "main") -> A:
    """Navigation link using HTMX for partial updates."""
    is_active = item.page_key == active_page
    cls = "btn btn-ghost" + (" btn-active" if is_active else "")

    return A(
        item.label,
        href=item.href,
        cls=cls,
        hx_get=item.href,
        hx_target=f"#{target}",
        hx_push_url="true",
        hx_swap="innerHTML",
    )
```

### HTMX Boost Considerations

HTMX boost (`hx-boost="true"`) automatically converts links to AJAX requests. However, for navigation:

```python
# SKUEL Pattern: HTMX boost disabled at bootstrap level
# Navbar uses standard HTML navigation for simplicity

# If you enable boost, exclude specific links:
# <a href="/logout" hx-boost="false">Sign out</a>
```

## Profile Dropdown Pattern

### Structure

```python
def _profile_dropdown(current_user: str) -> Div:
    """Profile dropdown using Alpine.js state."""
    user_initial = current_user[0].upper() if current_user else "U"

    return Div(
        # Trigger button
        Button(
            Span("Open user menu", cls="sr-only"),
            Div(
                user_initial,
                cls="size-8 rounded-full bg-primary flex items-center justify-center",
            ),
            type="button",
            cls="btn btn-ghost btn-circle",
            **{"@click": "toggleProfile()", "data-profile-trigger": "true"},
        ),
        # Dropdown menu
        Div(
            A("Your profile", href="/profile", cls="block px-4 py-2"),
            A("Settings", href="/settings", cls="block px-4 py-2"),
            A("Sign out", href="/logout", cls="block px-4 py-2"),
            id="profile-dropdown",
            cls="absolute right-0 z-50 mt-2 w-48 rounded-lg bg-base-100 shadow-lg",
            **{"x-show": "profileMenuOpen", "x-transition": "", "x-cloak": ""},
        ),
        cls="relative",
    )
```

### Click-Outside Handling

```javascript
// In Alpine.js init()
document.addEventListener('click', (e) => {
    const trigger = e.target.closest('[data-profile-trigger]');
    const menu = document.getElementById('profile-dropdown');

    // Close if click is outside both trigger and menu
    if (!trigger && menu && !menu.contains(e.target)) {
        this.profileMenuOpen = false;
    }
});
```

**Alternative: Alpine x-on:click.outside**

```html
<div x-data="{ open: false }" @click.outside="open = false" class="relative">
    <button @click="open = !open">Menu</button>
    <div x-show="open" x-transition>
        <!-- Dropdown content -->
    </div>
</div>
```

## Mobile Navigation Patterns

### Hamburger/Close Toggle

```python
def _mobile_menu_button() -> Button:
    """Hamburger/close toggle button for mobile."""
    return Button(
        Span("Open menu", cls="sr-only"),
        # Show hamburger when closed
        Span(_hamburger_icon(), **{"x-show": "!mobileMenuOpen"}),
        # Show X when open
        Span(_close_icon(), **{"x-show": "mobileMenuOpen", "x-cloak": ""}),
        type="button",
        cls="btn btn-ghost btn-square sm:hidden",
        **{"@click": "toggleMobile()"},
    )
```

### Mobile Menu Panel

```python
def _mobile_menu(nav_items: list[NavItem], active_page: str) -> Div:
    """Collapsible mobile menu panel."""
    return Div(
        Div(
            *[_nav_link(item, active_page, mobile=True) for item in nav_items],
            cls="space-y-1 px-2 pt-2 pb-3",
        ),
        cls="sm:hidden",
        **{"x-show": "mobileMenuOpen", "x-transition": "", "x-cloak": ""},
    )
```

### Responsive Breakpoints

| Class | Behavior |
|-------|----------|
| `sm:hidden` | Hidden on sm+ (shows mobile menu button) |
| `hidden sm:flex` | Hidden on mobile, flex on sm+ (desktop links) |
| `lg:drawer-open` | DaisyUI drawer always open on lg+ |

## Sidebar/Drawer Navigation

### DaisyUI Drawer Pattern

```html
<div class="drawer lg:drawer-open">
    <!-- Hidden checkbox toggle -->
    <input id="sidebar" type="checkbox" class="drawer-toggle" />

    <!-- Main content -->
    <div class="drawer-content">
        <!-- Mobile navbar with hamburger -->
        <div class="navbar lg:hidden">
            <label for="sidebar" class="btn btn-ghost drawer-button">
                ☰
            </label>
        </div>
        <!-- Page content -->
        <main class="p-6">...</main>
    </div>

    <!-- Sidebar -->
    <div class="drawer-side">
        <label for="sidebar" class="drawer-overlay"></label>
        <ul class="menu w-80 min-h-full bg-base-200">
            <li><a href="/overview">Overview</a></li>
            <li><a href="/settings">Settings</a></li>
        </ul>
    </div>
</div>
```

### MenuItem Configuration

```python
@dataclass
class MenuItem:
    """Menu item for drawer sidebar."""
    title: str
    href: str
    slug: str
    description: str = ""
    icon: str = ""
```

**See:** [sidebar-patterns.md](sidebar-patterns.md) for complete DrawerLayout implementation.

## Accessibility Checklist

### Required Attributes

| Element | Attribute | Purpose |
|---------|-----------|---------|
| `<nav>` | `aria-label` | Identifies navigation region |
| Icon buttons | `<span class="sr-only">` | Screen reader text |
| Toggle buttons | `aria-expanded` | Indicates menu state |
| Dropdown | `aria-haspopup` | Indicates popup behavior |

### Example

```html
<nav aria-label="Main navigation">
    <button aria-expanded="false"
            aria-haspopup="true"
            aria-label="Open user menu">
        <span class="sr-only">Open user menu</span>
        <svg>...</svg>
    </button>
</nav>
```

### Keyboard Navigation

- Tab: Move between links
- Enter/Space: Activate link or toggle
- Escape: Close dropdown/menu
- Arrow keys: Navigate within dropdown

## Anti-Patterns

### Don't Use Div Soup

```html
<!-- WRONG: No semantic meaning -->
<div class="nav">
    <div onclick="navigate()">Home</div>
</div>

<!-- RIGHT: Semantic elements -->
<nav aria-label="Main navigation">
    <a href="/">Home</a>
</nav>
```

### Don't Mix HTMX and Alpine for Same Concern

```html
<!-- WRONG: Both controlling visibility -->
<div x-show="visible" hx-get="/content">

<!-- RIGHT: Clear responsibility -->
<div x-data="{ loading: false }">
    <span x-show="loading">Loading...</span>
    <div hx-get="/content" hx-trigger="load">
        <!-- HTMX loads, Alpine shows loading state -->
    </div>
</div>
```

### Don't Nest x-data Unnecessarily

```html
<!-- WRONG: Redundant nesting -->
<nav x-data="{ navOpen: false }">
    <div x-data="{ dropdownOpen: false }">
        <!-- Can't easily access navOpen -->
    </div>
</nav>

<!-- RIGHT: Single state container -->
<nav x-data="{ navOpen: false, dropdownOpen: false }">
    <!-- Access all state -->
</nav>
```

## Additional Resources

- [navbar-patterns.md](navbar-patterns.md) - Complete navbar implementation walkthrough
- [sidebar-patterns.md](sidebar-patterns.md) - DaisyUI drawer patterns
- [responsive-patterns.md](responsive-patterns.md) - Mobile-responsive navigation

## Related Skills

- **[daisyui](../daisyui/SKILL.md)** - DaisyUI navbar/drawer components
- **[tailwind-css](../tailwind-css/SKILL.md)** - Responsive utility classes
- **[fasthtml](../fasthtml/SKILL.md)** - FastHTML route patterns

## Foundation

- **[html-htmx](../html-htmx/SKILL.md)** - HTMX fundamentals for server communication
- **[js-alpine](../js-alpine/SKILL.md)** - Alpine.js for client-side state

## See Also

- `/ui/layouts/navbar.py` - SKUEL navbar implementation
- `/ui/layouts/nav_config.py` - NavItem configuration
- `/components/drawer_layout.py` - DaisyUI drawer pattern
- `/static/js/skuel.js` - Alpine.data('navbar') component
