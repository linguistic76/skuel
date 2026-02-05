# Responsive Navigation Patterns

Complete reference for mobile-responsive navigation patterns.

## Tailwind Breakpoint System

| Breakpoint | Min-width | Common Use |
|------------|-----------|------------|
| `sm` | 640px | Small tablets |
| `md` | 768px | Tablets |
| `lg` | 1024px | Laptops |
| `xl` | 1280px | Desktops |
| `2xl` | 1536px | Large desktops |

### Mobile-First Approach

Default styles apply to mobile, then add breakpoint modifiers for larger screens:

```html
<!-- Mobile: hidden, sm+: flex -->
<div class="hidden sm:flex">Desktop navigation</div>

<!-- Mobile: visible, sm+: hidden -->
<button class="sm:hidden">Mobile menu button</button>
```

## Mobile Menu Button Pattern

### Hamburger/Close Toggle

```python
def _mobile_menu_button() -> Button:
    """Hamburger/close toggle button for mobile."""
    return Button(
        # Screen reader text
        Span("Open menu", cls="sr-only"),
        # Hamburger icon (shown when closed)
        Span(_hamburger_icon(), **{"x-show": "!mobileMenuOpen"}),
        # Close icon (shown when open)
        Span(_close_icon(), **{"x-show": "mobileMenuOpen", "x-cloak": ""}),
        type="button",
        cls="btn btn-ghost btn-square sm:hidden",
        **{"@click": "toggleMobile()"},
    )
```

### SVG Icons

```python
def _hamburger_icon() -> NotStr:
    """Three horizontal lines."""
    return NotStr(
        '<svg xmlns="http://www.w3.org/2000/svg" fill="none" '
        'viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6">'
        '<path stroke-linecap="round" stroke-linejoin="round" '
        'd="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"/>'
        '</svg>'
    )

def _close_icon() -> NotStr:
    """X icon."""
    return NotStr(
        '<svg xmlns="http://www.w3.org/2000/svg" fill="none" '
        'viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6">'
        '<path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/>'
        '</svg>'
    )
```

### Key Attributes

| Attribute | Purpose |
|-----------|---------|
| `sm:hidden` | Hide on sm+ screens (desktop) |
| `x-show="!mobileMenuOpen"` | Show hamburger when menu closed |
| `x-show="mobileMenuOpen"` | Show X when menu open |
| `x-cloak` | Prevent flash before Alpine init |
| `@click="toggleMobile()"` | Alpine click handler |

## Mobile Menu Panel

### Collapsible Panel

```python
def _mobile_menu(nav_items: list[NavItem], active_page: str) -> Div:
    """Mobile navigation panel."""
    return Div(
        Div(
            *[_nav_link(item, active_page, mobile=True) for item in nav_items],
            cls="space-y-1 px-2 pt-2 pb-3",
        ),
        cls="sm:hidden",
        **{"x-show": "mobileMenuOpen", "x-transition": "", "x-cloak": ""},
    )
```

### Transition Effects

```html
<!-- Basic transition -->
<div x-show="mobileMenuOpen" x-transition>

<!-- Custom transition -->
<div x-show="mobileMenuOpen"
     x-transition:enter="transition ease-out duration-200"
     x-transition:enter-start="opacity-0 -translate-y-2"
     x-transition:enter-end="opacity-100 translate-y-0"
     x-transition:leave="transition ease-in duration-150"
     x-transition:leave-start="opacity-100"
     x-transition:leave-end="opacity-0">
```

## Desktop vs Mobile Links

### Responsive Link Styling

```python
def _nav_link(item: NavItem, active_page: str, mobile: bool = False) -> A:
    is_active = item.page_key == active_page

    if mobile:
        # Larger touch targets for mobile
        base_cls = "block rounded-md px-3 py-2 text-base font-medium"
    else:
        # Compact styling for desktop
        base_cls = "rounded-md px-3 py-2 text-sm font-medium"

    active_cls = "bg-base-300 text-base-content"
    inactive_cls = "text-base-content/70 hover:bg-base-300 hover:text-base-content"

    cls = f"{base_cls} {active_cls if is_active else inactive_cls}"
    return A(item.label, href=item.href, cls=cls)
```

### Touch Target Guidelines

| Platform | Minimum Target Size |
|----------|---------------------|
| iOS | 44x44 px |
| Android | 48x48 dp |
| Web (recommended) | 44x44 px |

Mobile navigation should use:
- `py-2` or `py-3` for vertical padding
- `text-base` for readable font size
- `block` for full-width clickable area

## Responsive Visibility Classes

### Common Patterns

```html
<!-- Desktop only -->
<div class="hidden sm:flex">Desktop navigation</div>

<!-- Mobile only -->
<div class="sm:hidden">Mobile navigation</div>

<!-- Tablet and up -->
<div class="hidden md:block">Tablet+ content</div>

<!-- Desktop and up -->
<div class="hidden lg:block">Desktop+ content</div>
```

### Navbar Example

```html
<nav class="navbar">
    <!-- Mobile menu button - hidden on sm+ -->
    <button class="sm:hidden">☰</button>

    <!-- Logo - always visible -->
    <a href="/" class="text-xl font-bold">SKUEL</a>

    <!-- Desktop links - hidden on mobile -->
    <div class="hidden sm:flex sm:flex-1 sm:justify-center">
        <a href="/dashboard">Dashboard</a>
        <a href="/search">Search</a>
    </div>

    <!-- Profile - always visible -->
    <div class="relative">
        <button>Profile</button>
    </div>
</nav>
```

## Drawer Responsive Behavior

### lg:drawer-open Pattern

```html
<div class="drawer lg:drawer-open">
    <!-- Mobile: toggleable sidebar -->
    <!-- lg+: always visible sidebar -->
</div>
```

| Screen | Sidebar State |
|--------|---------------|
| < lg | Hidden by default, overlay when open |
| lg+ | Always visible, inline with content |

### Mobile Drawer Navbar

```html
<div class="drawer-content">
    <!-- Mobile navbar - hidden on lg+ -->
    <div class="navbar bg-white border-b border-gray-200 lg:hidden">
        <label for="drawer-id" class="btn btn-ghost drawer-button">
            <svg><!-- Hamburger icon --></svg>
        </label>
        <span class="text-xl font-bold">Page Title</span>
    </div>

    <!-- Main content -->
    <main>...</main>
</div>
```

## x-cloak Pattern

### Problem: Flash of Unstyled Content

Without `x-cloak`, Alpine.js elements may briefly show before initialization:

```html
<!-- BAD: May flash briefly -->
<div x-show="false">Hidden content</div>
```

### Solution: x-cloak

```css
/* In your CSS */
[x-cloak] { display: none !important; }
```

```html
<!-- GOOD: Hidden until Alpine initializes -->
<div x-show="false" x-cloak>Hidden content</div>
```

### When to Use

| Scenario | Use x-cloak? |
|----------|--------------|
| Content hidden by default | Yes |
| Toggle icons (hamburger/close) | Yes for the initially hidden one |
| Dropdown menus | Yes |
| Modal overlays | Yes |
| Content shown by default | No |

## Complete Responsive Navbar

```python
def create_responsive_navbar(
    nav_items: list[NavItem],
    current_user: str | None,
    active_page: str,
    is_authenticated: bool,
) -> Nav:
    """Complete responsive navbar with mobile menu."""

    return Nav(
        Div(
            Div(
                # Mobile menu button (hidden sm+)
                Button(
                    Span("Menu", cls="sr-only"),
                    Span("☰", **{"x-show": "!mobileMenuOpen"}),
                    Span("✕", **{"x-show": "mobileMenuOpen", "x-cloak": ""}),
                    cls="btn btn-ghost sm:hidden",
                    **{"@click": "mobileMenuOpen = !mobileMenuOpen"},
                ),

                # Logo (always visible)
                A("SKUEL", href="/", cls="text-xl font-bold text-primary ml-2 sm:ml-0"),

                # Desktop navigation (hidden on mobile)
                Div(
                    *[_desktop_link(item, active_page) for item in nav_items],
                    cls="hidden sm:flex sm:flex-1 sm:justify-center sm:space-x-1",
                ),

                # Profile section (always visible)
                Div(
                    _profile_dropdown(current_user) if is_authenticated
                    else _auth_buttons(),
                    cls="flex items-center",
                ),
                cls="flex items-center justify-between h-16",
            ),
            cls="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8",
        ),

        # Mobile menu panel (hidden sm+)
        Div(
            *[_mobile_link(item, active_page) for item in nav_items],
            cls="sm:hidden space-y-1 px-2 py-3",
            **{"x-show": "mobileMenuOpen", "x-transition": "", "x-cloak": ""},
        ),

        # Alpine.js state
        **{"x-data": "{ mobileMenuOpen: false, profileMenuOpen: false }"},
        cls="navbar bg-white border-b border-gray-200 sticky top-0 z-50",
    )
```

## Testing Responsive Navigation

### Browser DevTools

1. Open DevTools (F12)
2. Toggle device toolbar (Ctrl+Shift+M)
3. Select device or enter custom dimensions
4. Test hamburger toggle, dropdowns, transitions

### Key Breakpoints to Test

| Device | Width | Test Focus |
|--------|-------|------------|
| iPhone SE | 375px | Mobile menu, touch targets |
| iPhone 12 | 390px | Mobile menu |
| iPad Mini | 768px | Tablet layout |
| iPad | 810px | Tablet/desktop threshold |
| Laptop | 1024px | Desktop navigation |
| Desktop | 1440px | Full layout |

### Checklist

- [ ] Mobile menu button appears on small screens
- [ ] Mobile menu toggles correctly
- [ ] Desktop navigation appears on sm+ screens
- [ ] Profile dropdown works on all sizes
- [ ] Touch targets are adequate (44px+)
- [ ] Transitions are smooth
- [ ] No flash of unstyled content (x-cloak)
- [ ] Active states display correctly
