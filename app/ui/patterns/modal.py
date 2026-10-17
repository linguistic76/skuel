"""Alpine.js Modal Pattern
=========================

Standardized modal dialog for SKUEL's Alpine.js-controlled modals.

AlpineModal is a pure Alpine.js modal — no UIkit dependency. The caller's own
Alpine scope owns the open state (``show`` / ``close``); the wrapper adds the
backdrop, the transition and the dialog behaviour, through the shared
``alpineModal`` component in ``static/js/skuel.js``:

- the content box is ``role="dialog"`` with ``aria-modal="true"``, named by the
  caller's heading (``title_id``);
- opening moves focus to the first focusable element in the dialog, Tab and
  Shift+Tab cycle inside it, Escape and a backdrop click close it, and closing
  returns focus to the element that had it when the dialog opened.

Usage::

    # Simple modal controlled by Alpine.js boolean
    AlpineModal(
        H3("Edit Item", id="edit-item-title"),
        some_form,
        show="isOpen",
        close="isOpen = false",
        title_id="edit-item-title",
    )

    # Modal with custom width and id
    AlpineModal(
        H3("Share", id="share-title"),
        *modal_content,
        show="shareModal",
        close="shareModal = false",
        title_id="share-title",
        max_width="max-w-lg",
        id="share-modal",
    )

    # Modal controlled by Alpine component methods
    AlpineModal(
        H3(title, id=f"detail-{uid}-title"),
        *detail_content,
        show="isOpen",
        close="close()",
        title_id=f"detail-{uid}-title",
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
    title_id: str,
    max_width: str = "max-w-md",
    scrollable: bool = False,
    id: str | None = None,
) -> Div:
    """Alpine.js-controlled modal dialog with backdrop, transitions and focus handling.

    Args:
        content: Modal body content (header, form, buttons, etc.)
        show: Alpine.js expression for visibility (e.g., ``"isOpen"``, ``"shareModal"``)
        close: Alpine.js expression to close (e.g., ``"close()"``, ``"shareModal = false"``)
        title_id: DOM id of the heading inside ``content`` that names the dialog
            (``aria-labelledby``) — unique on the page
        max_width: Tailwind max-width class for the content box
        scrollable: Whether content should scroll when exceeding viewport height
        id: Optional DOM id for the modal container

    Returns:
        Div with backdrop overlay and centered dialog box
    """
    content_cls = f"bg-background rounded-lg shadow-lg w-full {max_width} p-6 relative"
    if scrollable:
        content_cls += " max-h-[80vh] overflow-y-auto"

    wrapper_attrs: dict[str, Any] = {
        "x_show": show,
        "x_cloak": True,
        "x_data": "alpineModal",
        "x_effect": f"modalToggled(!!({show}))",
    }
    if id:
        wrapper_attrs["id"] = id

    return Div(
        # Backdrop overlay
        Div(
            # Dialog box — stop clicks from closing via backdrop. tabindex=-1
            # lets a click on its text keep focus inside, so Escape still lands.
            Div(
                *content,
                cls=content_cls,
                role="dialog",
                tabindex="-1",
                **{
                    "aria-modal": "true",
                    "aria-labelledby": title_id,
                    "@click.stop": "",
                    "x-on:keydown.escape.stop": close,
                    "x-on:keydown.tab": "modalTrapTab($event)",
                },
            ),
            cls="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4",
            x_transition="",
            **{"x-on:click": close},
        ),
        **wrapper_attrs,
    )


__all__ = ["AlpineModal"]
