"""Askesis page wrapper — renders the chat shell inside BasePage(CUSTOM)."""

from typing import TYPE_CHECKING, Any

from ui.askesis.chat import render_askesis_shell
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import Request


async def render_askesis_page(
    request: "Request",
    *,
    username: str = "User",
    learning_scope_label: str = "Your learning",
) -> Any:
    """Render the Askesis chat surface within the SKUEL BasePage shell."""
    return await BasePage(
        content=render_askesis_shell(
            username=username,
            learning_scope_label=learning_scope_label,
        ),
        title="Askesis",
        page_type=PageType.CUSTOM,
        request=request,
        active_page="askesis",
    )
