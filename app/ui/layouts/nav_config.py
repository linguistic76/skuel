"""
Navigation Configuration
========================

The global chrome's one spec. ``ICON_NAV_ITEMS`` renders as the desktop
centre links (sm+) AND the phone bottom-nav tabs (<sm); ``MAIN_NAV_ITEMS``
renders as the role-gated centre links (lg+) AND the ``lg:hidden`` rows on
/settings (<lg). One item per SECTION, lit for the whole section by a
section key — the section's own pages are the sidebar's rows, lit by slug.

Usage:
    from ui.layouts.nav_config import ICON_NAV_ITEMS, MAIN_NAV_ITEMS
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class NavItem:
    """A role-gated text link: a centre link at lg+, a /settings row below.

    Attributes:
        label: Display text for the link
        href: The section's landing
        page_key: Section key the link is lit for (matches ``active_page``)
        requires_admin: Visible to admins only
        requires_teacher: Visible to teachers and admins
    """

    label: str
    href: str
    page_key: str
    requires_admin: bool = False
    requires_teacher: bool = False

    def visible_to(self, *, is_admin: bool, is_teacher: bool) -> bool:
        """Whether the viewer's role clears this link's gate."""
        if self.requires_admin and not is_admin:
            return False
        return not (self.requires_teacher and not (is_teacher or is_admin))


# Role-gated section doors — order determines display order
MAIN_NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem("Teaching", "/teaching/students", "teaching", requires_teacher=True),
    NavItem("Admin", "/admin", "admin", requires_admin=True),
)


@dataclass(frozen=True)
class IconNavItem:
    """A section door rendered twice from one spec: a desktop centre text
    link and a phone bottom-nav icon tab.

    Attributes:
        label: Display text (the tab's accessible name)
        href: The section's landing — also the section nav's first page,
            the one sanctioned overlap between the chrome and a sidebar
        page_keys: Every section key this door is lit for. One key per
            section; the Library door carries two because its landing
            (``/explore/library``) lights ``explore`` while ``/library/*``
            lights ``library``
        icon: Icon name (ui/components/icon.py) for the bottom-nav tab
        requires_auth: False → visible to anonymous visitors too
            (ContentScope.SHARED pages)
    """

    label: str
    href: str
    page_keys: frozenset[str]
    icon: str
    requires_auth: bool = True

    def lights(self, active_page: str) -> bool:
        """Whether the page's ``active_page`` key lies in this door's section."""
        return active_page in self.page_keys


# Section doors — one per section, identical for every authenticated role
ICON_NAV_ITEMS: tuple[IconNavItem, ...] = (
    # Tasks+: every page under the activity sidebar passes "activity"
    IconNavItem("Tasks+", "/today", frozenset({"activity"}), icon="activity"),
    IconNavItem(
        "Library",
        "/explore/library",
        frozenset({"explore", "library"}),
        icon="globe",
        requires_auth=False,
    ),
    IconNavItem(
        "PathSteps", "/path-steps", frozenset({"path-steps"}), icon="map", requires_auth=False
    ),
    IconNavItem("Submissions", "/submissions", frozenset({"submissions"}), icon="upload"),
)


__all__ = [
    "ICON_NAV_ITEMS",
    "IconNavItem",
    "MAIN_NAV_ITEMS",
    "NavItem",
]
