# Navbar Patterns

Complete reference for horizontal navigation bar patterns in SKUEL.

## Architecture Overview

SKUEL's navbar follows a three-file pattern:

| File | Purpose |
|------|---------|
| `ui/layouts/nav_config.py` | Type-safe NavItem configuration |
| `ui/layouts/navbar.py` | FastHTML navbar rendering |
| `static/js/skuel.js` | Alpine.js `navbar()` component |

## NavItem Configuration

### Dataclass Definition

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class NavItem:
    """
    Immutable navigation item configuration.

    Attributes:
        label: Display text for the link
        href: URL path to navigate to
        page_key: Key for active state matching (matches active_page param)
        requires_auth: Whether link requires authentication (default True)
        requires_admin: Whether link requires admin role (default False)
    """
    label: str
    href: str
    page_key: str
    requires_auth: bool = True
    requires_admin: bool = False
```

### Configuration Tuples

```python
# Main navigation items - order determines display order
MAIN_NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem("Profile Hub", "/profile/hub", "profile/hub"),
    NavItem("Search", "/search", "search"),
    NavItem("Askesis", "/askesis", "askesis"),
    NavItem("Calendar", "/calendar", "calendar"),
    NavItem("Nous", "/nous", "nous"),
)

# Admin-only navigation item - prepended to nav when user is admin
ADMIN_NAV_ITEM = NavItem(
    label="Admin Dashboard",
    href="/admin",
    page_key="admin",
    requires_admin=True,
)

# Profile dropdown menu items
PROFILE_MENU_ITEMS: tuple[NavItem, ...] = (
    NavItem("Your profile", "/profile", "profile"),
    NavItem("Settings", "/settings", "settings"),
    NavItem("Sign out", "/logout", "logout"),
)
```

### Why Frozen Dataclass?

- **Immutable**: Config can't be accidentally modified
- **Hashable**: Can be used in sets/dict keys
- **Type-safe**: MyPy verifies field types

## Navbar Component Structure

### Complete Navbar Function

```python
from fasthtml.common import A, Button, Div, Nav, NotStr, Span

def create_navbar(
    current_user: str | None = None,
    is_authenticated: bool = False,
    active_page: str = "",
    is_admin: bool = False,
) -> Nav:
    """
    Create the navigation bar.

    Args:
        current_user: Current user's display name or UID
        is_authenticated: Whether user is logged in
        active_page: Current page slug for highlighting
        is_admin: Whether user has admin role
    """
    # Build navigation items list
    nav_items = list(MAIN_NAV_ITEMS)
    if is_admin:
        nav_items.insert(0, ADMIN_NAV_ITEM)

    # Desktop navigation links
    desktop_links = Div(
        *[_nav_link(item, active_page) for item in nav_items],
        cls="hidden sm:flex sm:space-x-1",
    )

    # Mobile navigation links
    mobile_links = Div(
        Div(
            *[_nav_link(item, active_page, mobile=True) for item in nav_items],
            cls="space-y-1 px-2 pt-2 pb-3",
        ),
        cls="sm:hidden",
        **{"x-show": "mobileMenuOpen", "x-transition": "", "x-cloak": ""},
    )

    # Profile section
    if is_authenticated and current_user:
        profile_section = Div(
            _notification_button(),
            _profile_dropdown(current_user),
            cls="flex items-center gap-2",
        )
    else:
        profile_section = _auth_buttons()

    return Nav(
        Div(
            Div(
                _mobile_menu_button(),
                Div(
                    A("SKUEL", href="/", cls="text-xl font-bold text-primary"),
                    cls="flex-shrink-0 ml-2 sm:ml-0",
                ),
                Div(desktop_links, cls="hidden sm:flex sm:flex-1 sm:justify-center"),
                Div(profile_section, cls="flex items-center"),
                cls="flex items-center justify-between h-16",
            ),
            cls="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8",
        ),
        mobile_links,
        **{"x-data": "navbar()"},
        cls="navbar bg-white border-b border-gray-200 sticky top-0 z-50",
    )
```

### Request-Aware Factory

```python
def create_navbar_for_request(request: Request, active_page: str = "") -> Nav:
    """
    Create navbar with automatic user/admin detection from session.

    This is the recommended way to create navbars in routes.
    """
    from core.auth import get_current_user, get_is_admin, is_authenticated

    return create_navbar(
        current_user=get_current_user(request),
        is_authenticated=is_authenticated(request),
        active_page=active_page,
        is_admin=get_is_admin(request),
    )
```

## Navigation Link Rendering

### Active State Logic

```python
def _nav_link(item: NavItem, active_page: str, mobile: bool = False) -> A:
    """Create a navigation link with active state styling."""
    is_active = item.page_key == active_page

    if mobile:
        base_cls = "block rounded-md px-3 py-2 text-base font-medium"
        active_cls = "bg-base-300 text-base-content"
        inactive_cls = "text-base-content/70 hover:bg-base-300 hover:text-base-content"
    else:
        base_cls = "rounded-md px-3 py-2 text-sm font-medium"
        active_cls = "bg-base-300 text-base-content"
        inactive_cls = "text-base-content/70 hover:bg-base-300 hover:text-base-content"

    cls = f"{base_cls} {active_cls if is_active else inactive_cls}"
    return A(item.label, href=item.href, cls=cls)
```

### CSS Classes Breakdown

| Class | Purpose |
|-------|---------|
| `rounded-md` | Rounded corners |
| `px-3 py-2` | Horizontal/vertical padding |
| `text-sm font-medium` | Desktop text styling |
| `text-base font-medium` | Mobile text styling (larger) |
| `bg-base-300` | Active background |
| `text-base-content` | Primary text color |
| `text-base-content/70` | Dimmed text (70% opacity) |
| `hover:bg-base-300` | Hover background |

## Profile Dropdown

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
                cls="size-8 rounded-full bg-primary flex items-center justify-center text-primary-content font-medium text-sm",
            ),
            type="button",
            cls="btn btn-ghost btn-circle",
            **{"@click": "toggleProfile()", "data-profile-trigger": "true"},
        ),
        # Dropdown menu
        Div(
            *[
                A(
                    item.label,
                    href=item.href,
                    cls="block px-4 py-2 text-sm text-base-content hover:bg-base-200 first:rounded-t-lg last:rounded-b-lg",
                )
                for item in PROFILE_MENU_ITEMS
            ],
            id="profile-dropdown",
            cls="absolute right-0 z-50 mt-2 w-48 origin-top-right rounded-lg bg-base-100 shadow-lg ring-1 ring-black/5",
            **{"x-show": "profileMenuOpen", "x-transition": "", "x-cloak": ""},
        ),
        cls="relative",
    )
```

### Key Attributes

| Attribute | Purpose |
|-----------|---------|
| `data-profile-trigger` | Marker for click-outside detection |
| `x-show="profileMenuOpen"` | Alpine.js visibility binding |
| `x-transition` | Smooth enter/leave animation |
| `x-cloak` | Prevent flash before Alpine initializes |

## Mobile Menu Button

### Hamburger/Close Toggle

```python
def _mobile_menu_button() -> Button:
    """Create hamburger/close toggle button for mobile."""
    return Button(
        Span("Open menu", cls="sr-only"),
        Span(_hamburger_icon(), **{"x-show": "!mobileMenuOpen"}),
        Span(_close_icon(), **{"x-show": "mobileMenuOpen", "x-cloak": ""}),
        type="button",
        cls="btn btn-ghost btn-square sm:hidden",
        **{"@click": "toggleMobile()"},
    )
```

### SVG Icons

```python
def _hamburger_icon() -> NotStr:
    """Hamburger menu SVG icon."""
    return NotStr(
        '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" '
        'stroke-width="1.5" stroke="currentColor" class="size-6">'
        '<path stroke-linecap="round" stroke-linejoin="round" '
        'd="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"/>'
        '</svg>'
    )

def _close_icon() -> NotStr:
    """Close X SVG icon."""
    return NotStr(
        '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" '
        'stroke-width="1.5" stroke="currentColor" class="size-6">'
        '<path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/>'
        '</svg>'
    )
```

## Authentication States

### Authenticated User

```python
profile_section = Div(
    _notification_button(),
    _profile_dropdown(current_user),
    cls="flex items-center gap-2",
)
```

### Unauthenticated User

```python
def _auth_buttons() -> Div:
    """Login/signup buttons for unauthenticated users."""
    return Div(
        A("Login", href="/login", cls="btn btn-ghost btn-sm"),
        A("Sign Up", href="/register", cls="btn btn-primary btn-sm"),
        cls="flex items-center gap-2",
    )
```

## Alpine.js Component

### Full navbar() Definition

```javascript
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
```

### State Variables

| State | Type | Purpose |
|-------|------|---------|
| `mobileMenuOpen` | boolean | Mobile menu visibility |
| `profileMenuOpen` | boolean | Profile dropdown visibility |

### Methods

| Method | Purpose |
|--------|---------|
| `toggleMobile()` | Toggle mobile menu |
| `toggleProfile()` | Toggle profile dropdown |
| `closeProfile()` | Force close profile dropdown |
| `init()` | Setup click-outside listener |

## Usage in Routes

```python
from ui.layouts.navbar import create_navbar_for_request

@rt("/calendar")
async def calendar_page(request):
    return Titled(
        "Calendar",
        create_navbar_for_request(request, active_page="calendar"),
        Main(
            # Calendar content...
            id="main-content",
        ),
    )
```
