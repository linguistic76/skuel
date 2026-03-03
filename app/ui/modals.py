"""
SKUEL DaisyUI Modal Components
================================

Modal, ModalBox, ModalAction, ModalBackdrop wrappers.
"""

from typing import Any

from fasthtml.common import Button as FTButton
from fasthtml.common import Dialog, Div

__all__ = ["Modal", "ModalBox", "ModalAction", "ModalBackdrop"]


def Modal(
    id: str,
    *c: Any,
    cls: str = "",
    open_on_load: bool = False,
    title_id: str | None = None,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Modal wrapper using dialog element with WCAG 2.1 Level AA compliance.

    Args:
        id: Modal ID (required for opening/closing)
        *c: Modal content (should include ModalBox)
        cls: Additional CSS classes
        open_on_load: If True, modal opens when page loads
        title_id: ID of the modal title element for aria-labelledby (recommended)
        **kwargs: Additional HTML attributes

    Example:
        Modal("my-modal",
            ModalBox(
                H2("Modal Title", id="modal-title"),
                P("Modal content here"),
                ModalAction(
                    Button("Close", onclick="my-modal.close()")
                )
            ),
            title_id="modal-title"
        )

    ARIA Attributes:
        - role="dialog" (implicit from <dialog> element)
        - aria-modal="true" (automatically added)
        - aria-labelledby (if title_id provided)

    To open: document.getElementById('my-modal').showModal()
    To close: document.getElementById('my-modal').close()
    """
    classes = ["modal"]
    if cls:
        classes.append(cls)

    attrs = {
        "id": id,
        "cls": " ".join(classes),
        "aria_modal": "true",  # WCAG 2.1 Level AA requirement
    }

    # Add aria-labelledby if title ID provided
    if title_id:
        attrs["aria_labelledby"] = title_id

    if open_on_load:
        attrs["open"] = True

    return Dialog(*c, **attrs, **kwargs)


def ModalBox(*c: Any, cls: str = "", role: str = "document", **kwargs: Any) -> Any:
    """
    DaisyUI Modal box wrapper (the content container) with accessibility support.

    Args:
        *c: Modal box content
        cls: Additional CSS classes
        role: ARIA role (default: "document" for screen readers)
        **kwargs: Additional HTML attributes

    Note:
        The role="document" tells screen readers this is the main modal content,
        allowing proper navigation within the dialog.
    """
    classes = ["modal-box"]
    if cls:
        classes.append(cls)

    # Add role for accessibility
    attrs = {"cls": " ".join(classes)}
    if role:
        attrs["role"] = role

    return Div(*c, **attrs, **kwargs)


def ModalAction(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    DaisyUI Modal action wrapper (for buttons).

    Args:
        *c: Action buttons
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = ["modal-action"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def ModalBackdrop(**kwargs: Any) -> Any:
    """
    DaisyUI Modal backdrop (closes modal on click).

    Add as child of Modal after ModalBox to enable click-outside-to-close.
    """
    from fasthtml.common import Form

    return Form(method="dialog", cls="modal-backdrop")(FTButton("close", **kwargs))
