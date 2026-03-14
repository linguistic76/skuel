"""
SKUEL Form Components (MonsterUI)
==================================

Form component wrappers using MonsterUI internals.
Standalone inputs (Input, Select, Textarea) for cases without labels.
LabelInput/LabelTextArea/LabelSelect for label+input combos with ARIA accessibility.
"""

from typing import Any

from fasthtml.common import Div
from monsterui.franken import CheckboxX as MCheckbox
from monsterui.franken import FormLabel as MFormLabel
from monsterui.franken import Input as MInput
from monsterui.franken import LabelInput as MLabelInput
from monsterui.franken import LabelSelect as MLabelSelect
from monsterui.franken import LabelTextArea as MLabelTextArea
from monsterui.franken import Radio as MRadio
from monsterui.franken import Range as MRange
from monsterui.franken import Select as MSelect
from monsterui.franken import Switch as MSwitch
from monsterui.franken import TextArea as MTextArea

from ui.buttons import ButtonT
from ui.layout import Size

__all__ = [
    "Input",
    "Select",
    "Textarea",
    "Label",
    "LabelInput",
    "LabelTextArea",
    "LabelSelect",
    "LabelCheckbox",
    "Checkbox",
    "Radio",
    "Toggle",
    "Range",
]


def _aria_attrs(
    name: str,
    help_text: str | None,
    error_text: str | None,
) -> tuple[dict[str, str], list[Any]]:
    """Build ARIA attributes and help/error elements for accessible forms.

    Returns (extra_kwargs, trailing_elements).
    """
    help_id = f"{name}-help"
    error_id = f"{name}-error"
    extra: dict[str, str] = {}
    elements: list[Any] = []
    describedby_ids: list[str] = []

    if help_text:
        describedby_ids.append(help_id)
        elements.append(Div(help_text, id=help_id, cls="mt-1 text-sm text-muted-foreground"))
    if error_text:
        describedby_ids.append(error_id)
        extra["aria_invalid"] = "true"
        elements.append(
            Div(error_text, id=error_id, role="alert", cls="mt-1 text-sm text-destructive")
        )
    if describedby_ids:
        extra["aria_describedby"] = " ".join(describedby_ids)

    return extra, elements


def Input(
    cls: str = "",
    size: Size | None = None,
    full_width: bool = True,
    help_text: str | None = None,
    error_text: str | None = None,
    **kwargs: Any,
) -> Any:
    """Standalone input (no label). Use LabelInput when a label is needed."""
    cls_parts = []
    if full_width:
        cls_parts.append("w-full")
    if error_text:
        cls_parts.append("border-destructive")
    if cls:
        cls_parts.append(cls)

    input_name = kwargs.get("name", kwargs.get("id", "input"))
    aria_extra, trailing = _aria_attrs(input_name, help_text, error_text)
    kwargs.update(aria_extra)

    input_element = MInput(cls=" ".join(cls_parts) if cls_parts else None, **kwargs)

    if not trailing:
        return input_element

    return Div(input_element, *trailing, cls="w-full" if full_width else "")


def Select(
    *options: Any,
    cls: str = "",
    size: Size | None = None,
    full_width: bool = True,
    help_text: str | None = None,
    error_text: str | None = None,
    **kwargs: Any,
) -> Any:
    """Standalone select (no label). Use LabelSelect when a label is needed."""
    cls_parts = []
    if full_width:
        cls_parts.append("w-full")
    if error_text:
        cls_parts.append("border-destructive")
    if cls:
        cls_parts.append(cls)

    select_name = kwargs.get("name", kwargs.get("id", "select"))
    aria_extra, trailing = _aria_attrs(select_name, help_text, error_text)
    kwargs.update(aria_extra)

    select_element = MSelect(*options, cls=" ".join(cls_parts) if cls_parts else None, **kwargs)

    if not trailing:
        return select_element

    return Div(select_element, *trailing, cls="w-full" if full_width else "")


def Textarea(
    *c: Any,
    cls: str = "",
    size: Size | None = None,
    full_width: bool = True,
    help_text: str | None = None,
    error_text: str | None = None,
    **kwargs: Any,
) -> Any:
    """Standalone textarea (no label). Use LabelTextArea when a label is needed."""
    cls_parts = []
    if full_width:
        cls_parts.append("w-full")
    if error_text:
        cls_parts.append("border-destructive")
    if cls:
        cls_parts.append(cls)

    textarea_name = kwargs.get("name", kwargs.get("id", "textarea"))
    aria_extra, trailing = _aria_attrs(textarea_name, help_text, error_text)
    kwargs.update(aria_extra)

    textarea_element = MTextArea(*c, cls=" ".join(cls_parts) if cls_parts else None, **kwargs)

    if not trailing:
        return textarea_element

    return Div(textarea_element, *trailing, cls="w-full" if full_width else "")


def LabelInput(
    label: str,
    *,
    help_text: str | None = None,
    error_text: str | None = None,
    lbl_cls: str = "",
    cls: str = "space-y-2",
    **kwargs: Any,
) -> Any:
    """MonsterUI LabelInput + SKUEL accessibility (ARIA, help/error text)."""
    input_name = kwargs.get("name", kwargs.get("id", "input"))
    aria_extra, trailing = _aria_attrs(input_name, help_text, error_text)
    if error_text:
        input_cls = kwargs.pop("input_cls", "") + " border-destructive"
    else:
        input_cls = kwargs.pop("input_cls", "")
    kwargs.update(aria_extra)

    base = MLabelInput(label, lbl_cls=lbl_cls, input_cls=input_cls.strip(), cls=cls, **kwargs)

    if not trailing:
        return base

    return Div(base, *trailing)


def LabelTextArea(
    label: str,
    *,
    help_text: str | None = None,
    error_text: str | None = None,
    lbl_cls: str = "",
    cls: str = "space-y-2",
    **kwargs: Any,
) -> Any:
    """MonsterUI LabelTextArea + SKUEL accessibility (ARIA, help/error text)."""
    textarea_name = kwargs.get("name", kwargs.get("id", "textarea"))
    aria_extra, trailing = _aria_attrs(textarea_name, help_text, error_text)
    if error_text:
        input_cls = kwargs.pop("input_cls", "") + " border-destructive"
    else:
        input_cls = kwargs.pop("input_cls", "")
    kwargs.update(aria_extra)

    base = MLabelTextArea(label, lbl_cls=lbl_cls, input_cls=input_cls.strip(), cls=cls, **kwargs)

    if not trailing:
        return base

    return Div(base, *trailing)


def LabelSelect(
    *options: Any,
    label: str,
    help_text: str | None = None,
    error_text: str | None = None,
    lbl_cls: str = "",
    cls: str = "space-y-2",
    **kwargs: Any,
) -> Any:
    """MonsterUI LabelSelect + SKUEL accessibility (ARIA, help/error text)."""
    select_name = kwargs.get("name", kwargs.get("id", "select"))
    aria_extra, trailing = _aria_attrs(select_name, help_text, error_text)
    kwargs.update(aria_extra)

    base = MLabelSelect(*options, label=label, lbl_cls=lbl_cls, cls=cls, **kwargs)

    if not trailing:
        return base

    return Div(base, *trailing)


def LabelCheckbox(
    label: str,
    *,
    cls: str = "space-y-2",
    **kwargs: Any,
) -> Any:
    """Label + Checkbox combo using MonsterUI FormLabel + CheckboxX."""
    return Div(
        Div(
            MCheckbox(**kwargs),
            MFormLabel(label, cls="ml-2"),
            cls="flex items-center",
        ),
        cls=cls,
    )


def Label(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """Form label wrapper using MonsterUI FormLabel."""
    return MFormLabel(*c, cls=cls or None, **kwargs)


def Checkbox(
    cls: str = "",
    variant: ButtonT = ButtonT.primary,
    size: Size | None = None,
    **kwargs: Any,
) -> Any:
    """Checkbox wrapper using MonsterUI."""
    return MCheckbox(cls=cls or None, **kwargs)


def Radio(
    cls: str = "",
    variant: ButtonT = ButtonT.primary,
    size: Size | None = None,
    **kwargs: Any,
) -> Any:
    """Radio button wrapper using MonsterUI."""
    return MRadio(cls=cls or None, **kwargs)


def Toggle(
    cls: str = "",
    variant: ButtonT = ButtonT.primary,
    size: Size | None = None,
    **kwargs: Any,
) -> Any:
    """Toggle/Switch wrapper using MonsterUI's Switch component."""
    return MSwitch(cls=cls or None, **kwargs)


def Range(
    cls: str = "",
    variant: ButtonT = ButtonT.primary,
    size: Size | None = None,
    **kwargs: Any,
) -> Any:
    """Range slider wrapper using MonsterUI."""
    return MRange(cls=cls or None, **kwargs)
