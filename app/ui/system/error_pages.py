"""Error page UI components (404, etc.)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fasthtml.common import Div

from ui.components import ButtonT
from ui.layouts.base_page import BasePage
from ui.patterns.page_header import PageHeader
from ui.primitives import ButtonLink

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import Request


def render_404_page(request: Request) -> FT:
    """The not-found page, in the page shell."""
    return BasePage(
        Div(
            PageHeader(
                "Page Not Found", subtitle="Sorry, the page you're looking for doesn't exist."
            ),
            Div(
                ButtonLink("Go Home", href="/", cls=ButtonT.primary),
                ButtonLink("Search", href="/search", cls=ButtonT.secondary),
                cls="flex flex-wrap gap-2",
            ),
        ),
        title="Page Not Found",
        request=request,
    )
