"""UI Layouts - Page-level layout components."""

from ui.layouts.base_page import BasePage
from ui.layouts.dashboard import DashboardLayout
from ui.layouts.navbar import create_navbar
from ui.layouts.page_types import CONTAINER_WIDTH, PAGE_CONFIG, PageType

__all__ = [
    "BasePage",
    "CONTAINER_WIDTH",
    "DashboardLayout",
    "PAGE_CONFIG",
    "PageType",
    "create_navbar",
]
