"""System UI components — landing and error pages."""

from ui.system.error_pages import render_404_page
from ui.system.landing import render_login_landing_page

__all__ = ["render_404_page", "render_login_landing_page"]
