"""The /settings page shell — the account page every avatar tap opens.

Below the desktop widths it is also the chrome's overflow: the sign-out row
(``sm:hidden`` — the top bar carries the icon from sm), the Insights row
(``sm`` to ``md`` only — the band where the top bar has no room for its icon)
and the role-gated section doors Admin and Teaching (``lg:hidden`` — the
centre links carry them from lg; the bottom nav never does) render here as
rows. Those rows come first and sit outside any HTMX fragment or ``x-cloak`` —
they must not wait for the preferences fragment or for Alpine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fasthtml.common import A, Div

from core.utils.auth_context import current_auth_state
from ui.layouts.base_page import BasePage, HtmlDocument
from ui.layouts.navbar import insights_row, role_nav_rows, signout_row
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader
from ui.settings.account import render_account_card

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import Request


def render_settings_page(request: Request) -> HtmlDocument:
    """The settings page: phone chrome rows, the Account card, then the
    preferences editor loaded from ``/settings/content``.

    Role flags come from the middleware-set auth context, as the navbar's do
    — the rows are chrome, filtered by the same predicate as the centre links.
    The Account card's name is that context's too: the graph's value on this
    request.
    """
    auth = current_auth_state()
    content = Div(
        signout_row(),
        insights_row(),
        *role_nav_rows(is_admin=auth.is_admin, is_teacher=auth.is_teacher),
        PageHeader("Settings", subtitle="Manage your preferences"),
        render_account_card(auth.display_name),
        Div(
            A(
                "Devices — vault-agent enrollment →",
                href="/settings/devices",
                cls="link text-sm",
            ),
            cls="mb-4",
        ),
        content_loading_placeholder("/settings/content", "settings-content"),
    )
    return BasePage(
        content=content,
        title="Settings",
        request=request,
        active_page="settings",
    )


__all__ = ["render_settings_page"]
