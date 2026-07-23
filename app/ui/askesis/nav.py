"""Askesis page wrapper — renders the chat shell inside BasePage(CUSTOM)."""

from typing import TYPE_CHECKING, Any

from ui.askesis.chat import render_askesis_shell
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import Request


def render_askesis_page(
    request: "Request",
    *,
    username: str = "User",
    learning_scope_label: str = "Your learning",
    nous_topics: list[str] | None = None,
    nous_subtopic_map: dict[str, list[str]] | None = None,
    initial_question: str = "",
    initial_nous: str = "",
    initial_nous_subtopic: str = "",
    model_options: list[tuple[str, str]] | None = None,
) -> Any:
    """Render the Askesis chat surface within the SKUEL BasePage shell.

    ``initial_question`` / ``initial_nous`` / ``initial_nous_subtopic`` carry the
    /search "Ask" handoff — they prefill the composer and seed the scope (chip
    shown); the user clicks Send (no auto-submit — a crafted GET must not run a
    prompt in the session). ``model_options`` are the ``(value, label)`` models
    the wired caller can serve — the top-bar switcher's options (empty → no picker).
    """
    return BasePage(
        content=render_askesis_shell(
            username=username,
            learning_scope_label=learning_scope_label,
            nous_topics=nous_topics,
            nous_subtopic_map=nous_subtopic_map,
            initial_question=initial_question,
            initial_nous=initial_nous,
            initial_nous_subtopic=initial_nous_subtopic,
            model_options=model_options,
        ),
        title="Askesis",
        page_type=PageType.CUSTOM,
        request=request,
        active_page="askesis",
    )
