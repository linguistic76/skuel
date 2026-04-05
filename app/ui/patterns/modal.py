"""Alpine.js Modal Pattern
=========================

Standardized modal wrapper for SKUEL's Alpine.js-controlled modals.

MonsterUI provides Modal components based on UIKit's ``data-uk-toggle`` mechanism,
which is incompatible with SKUEL's Alpine.js state management pattern. This wrapper
standardizes the Alpine.js modal pattern (backdrop, transitions, accessibility)
while preserving full Alpine.js control.

Usage::

    # Simple modal controlled by Alpine.js boolean
    AlpineModal(
        H3("Edit Item"),
        some_form,
        show="isOpen",
        close="isOpen = false",
    )

    # Modal with custom width and id
    AlpineModal(
        *modal_content,
        show="shareModal",
        close="shareModal = false",
        max_width="max-w-lg",
        id="share-modal",
    )

    # Modal controlled by Alpine component methods
    AlpineModal(
        *detail_content,
        show="isOpen",
        close="close()",
        max_width="max-w-2xl",
        scrollable=True,
    )
"""

from typing import Any

from fasthtml.common import Div


def AlpineModal(
    *content: Any,
    show: str,
    close: str,
    max_width: str = "max-w-md",
    scrollable: bool = False,
    id: str | None = None,
) -> Div:
    """Alpine.js-controlled modal with backdrop and transitions.

    Args:
        content: Modal body content (header, form, buttons, etc.)
        show: Alpine.js expression for visibility (e.g., ``"isOpen"``, ``"shareModal"``)
        close: Alpine.js expression to close (e.g., ``"close()"``, ``"shareModal = false"``)
        max_width: Tailwind max-width class for the content box
        scrollable: Whether content should scroll when exceeding viewport height
        id: Optional DOM id for the modal container

    Returns:
        Div with backdrop overlay and centered content box
    """
    content_cls = f"bg-background rounded-lg shadow-lg w-full {max_width} p-6 relative"
    if scrollable:
        content_cls += " max-h-[80vh] overflow-y-auto"

    wrapper_attrs: dict[str, Any] = {
        "x_show": show,
        "x_cloak": True,
    }
    if id:
        wrapper_attrs["id"] = id

    return Div(
        # Backdrop overlay
        Div(
            # Content box — stop clicks from closing via backdrop
            Div(
                *content,
                cls=content_cls,
                **{"@click.stop": ""},
            ),
            cls="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4",
            x_transition="",
            **{"x-on:click": close},
        ),
        **wrapper_attrs,
    )


__all__ = ["AlpineModal"]
