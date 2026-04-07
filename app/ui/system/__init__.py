"""System UI components — landing, admin hub, error pages."""

from ui.system.admin_hub import render_admin_hub_content
from ui.system.error_pages import render_404_page
from ui.system.landing import render_login_landing_page

__all__ = ["render_admin_hub_content", "render_404_page", "render_login_landing_page"]
