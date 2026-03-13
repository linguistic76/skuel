"""
SKUEL Modal Components (MonsterUI)
====================================

Modal wrappers using MonsterUI's modal system.
Keeps SKUEL's API (Modal, ModalBox, ModalAction, ModalBackdrop).

Note: MonsterUI modals use UIkit's modal system. Opening mechanism changes from
dialog.showModal() to UIkit.modal('#id').show() or data-uk-toggle="target: #id".
"""

from typing import Any

from fasthtml.common import Div
from monsterui.franken import Button as MButton
from monsterui.franken import ButtonT as MButtonT
from monsterui.franken import ModalBody as MModalBody
from monsterui.franken import ModalCloseButton as MModalCloseButton
from monsterui.franken import ModalContainer as MModalContainer
from monsterui.franken import ModalDialog as MModalDialog
from monsterui.franken import ModalFooter as MModalFooter
from monsterui.franken import ModalHeader as MModalHeader
from monsterui.franken import ModalTitle as MModalTitle

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
    Modal wrapper using MonsterUI's UIkit modal system.

    Args:
        id: Modal ID (required for opening/closing)
        *c: Modal content (should include ModalBox)
        cls: Additional CSS classes
        open_on_load: If True, modal opens when page loads
        title_id: ID of the modal title element for aria-labelledby
        **kwargs: Additional HTML attributes

    To open: UIkit.modal('#my-modal').show() or use data-uk-toggle="target: #id"
    To close: UIkit.modal('#my-modal').hide() or use ModalCloseButton
    """
    attrs: dict[str, Any] = {"id": id}

    if title_id:
        attrs["aria_labelledby"] = title_id

    if cls:
        attrs["cls"] = cls

    if open_on_load:
        attrs["uk_open"] = True

    return MModalContainer(*c, **attrs, **kwargs)


def ModalBox(*c: Any, cls: str = "", role: str = "document", **kwargs: Any) -> Any:
    """
    Modal dialog content wrapper using MonsterUI.

    Args:
        *c: Modal box content
        cls: Additional CSS classes
        role: ARIA role (default: "document" for screen readers)
        **kwargs: Additional HTML attributes
    """
    return MModalDialog(*c, cls=cls or None, **kwargs)


def ModalAction(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    Modal action wrapper (for buttons in footer).

    Args:
        *c: Action buttons
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    return MModalFooter(*c, cls=cls or None, **kwargs)


def ModalBackdrop(**kwargs: Any) -> Any:
    """
    Modal close button — replaces DaisyUI backdrop close pattern.

    In MonsterUI, use ModalCloseButton or clicking outside the dialog.
    """
    return MModalCloseButton("Close", cls=MButtonT.default, **kwargs)


def ModalHeader(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """Modal header wrapper using MonsterUI."""
    return MModalHeader(*c, cls=cls or None, **kwargs)


def ModalBody(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """Modal body wrapper using MonsterUI."""
    return MModalBody(*c, cls=cls or None, **kwargs)


def ModalTitle(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """Modal title wrapper using MonsterUI."""
    return MModalTitle(*c, cls=cls or None, **kwargs)


def ModalCloseButton(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """Modal close button using MonsterUI."""
    return MModalCloseButton(*c, cls=cls or None, **kwargs)
