"""
FormGenerator - Dynamic Form Generation from Pydantic Models
=============================================================

Generates DaisyUI forms from Pydantic model introspection. Supports
sections, help text, pre-fill, hidden fields, and fragment mode for
embedding forms within article content.

See: /docs/patterns/FORM_GENERATOR_GUIDE.md
"""

import types
from datetime import date, datetime
from enum import Enum
from typing import Any, Union, get_args, get_origin

from fasthtml.common import H3, Div, Form, Option, P
from fasthtml.common import Input as FTInput
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from core.ports import (
    GeConstraint,
    GtConstraint,
    LeConstraint,
    LtConstraint,
    MaxLenConstraint,
    MinLenConstraint,
    PydanticFieldInfo,
)
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonT
from ui.forms import Checkbox, Input, Label, Select, Textarea

logger = get_logger("skuel.components.form_generator")


def _is_union_type(origin: type | None) -> bool:
    """Check if origin is a Union type (handles both typing.Union and PEP 604 X | Y)."""
    return origin is Union or origin is types.UnionType


def _unwrap_optional(annotation: type) -> type:
    """Extract T from Optional[T] or T | None. Returns annotation unchanged if not optional."""
    origin = get_origin(annotation)
    if origin is not None and _is_union_type(origin):
        args = get_args(annotation)
        if args:
            non_none = [a for a in args if a is not type(None)]
            return non_none[0] if non_none else str
    return annotation


class FieldWidgetMapper:
    """Maps Pydantic field types to DaisyUI widget types via introspection."""

    @staticmethod
    def get_widget_type(field_name: str, field_info: FieldInfo, annotation: type) -> str:
        """
        Determine widget type from field introspection.

        Priority: explicit ui_widget metadata > type inference > name heuristics.
        """
        # Check for explicit UI widget metadata
        if isinstance(field_info, PydanticFieldInfo):
            for meta in field_info.metadata:
                if isinstance(meta, dict) and "ui_widget" in meta:
                    return str(meta["ui_widget"])

        # Handle Optional[T] / T | None
        origin = get_origin(annotation)
        if origin is not None and _is_union_type(origin):
            annotation = _unwrap_optional(annotation)

        # Enum -> select dropdown
        if isinstance(annotation, type) and issubclass(annotation, Enum):
            return "select"

        # List -> textarea (comma/newline separated)
        if origin is list:
            return "textarea"

        # Date/DateTime
        if annotation is date:
            return "date"
        if annotation is datetime:
            return "datetime-local"

        # Boolean -> checkbox
        if annotation is bool:
            return "checkbox"

        # Numeric
        if annotation in (int, float):
            return "number"

        # String with heuristics
        if annotation is str:
            max_length = getattr(field_info, "max_length", None)
            if max_length and max_length > 100:
                return "textarea"

            if any(
                keyword in field_name.lower()
                for keyword in ["description", "notes", "content", "body"]
            ):
                return "textarea"

            if isinstance(field_info, PydanticFieldInfo):
                for meta in field_info.metadata:
                    if isinstance(meta, dict):
                        if meta.get("format") == "email":
                            return "email"
                        if meta.get("format") == "url":
                            return "url"

            return "text"

        return "text"

    @staticmethod
    def extract_constraints(field_info: FieldInfo) -> dict[str, Any]:
        """Extract HTML input constraints (min, max, minlength, maxlength) from Pydantic metadata."""
        constraints: dict[str, Any] = {}

        if isinstance(field_info, PydanticFieldInfo) and field_info.metadata:
            for constraint in field_info.metadata:
                if isinstance(constraint, MinLenConstraint):
                    constraints["minlength"] = constraint.min_length
                if isinstance(constraint, MaxLenConstraint):
                    constraints["maxlength"] = constraint.max_length
                if isinstance(constraint, GeConstraint):
                    constraints["min"] = constraint.ge
                if isinstance(constraint, LeConstraint):
                    constraints["max"] = constraint.le
                if isinstance(constraint, GtConstraint):
                    constraints["min"] = constraint.gt + 0.01
                if isinstance(constraint, LtConstraint):
                    constraints["max"] = constraint.lt - 0.01

        return constraints

    @staticmethod
    def get_field_label(field_name: str, field_info: FieldInfo) -> str:
        """
        Generate label from field info.

        Priority: explicit ui_label metadata > Pydantic description > auto-generated from name.
        """
        if isinstance(field_info, PydanticFieldInfo):
            for meta in field_info.metadata:
                if isinstance(meta, dict) and "ui_label" in meta:
                    return str(meta["ui_label"])

        if field_info.description:
            return field_info.description

        return " ".join(word.capitalize() for word in field_name.split("_"))

    @staticmethod
    def get_placeholder(field_name: str, field_info: FieldInfo) -> str | None:
        """Generate placeholder: explicit ui_placeholder metadata or auto-generated from label."""
        if isinstance(field_info, PydanticFieldInfo):
            for meta in field_info.metadata:
                if isinstance(meta, dict) and "ui_placeholder" in meta:
                    return str(meta["ui_placeholder"])

        label = FieldWidgetMapper.get_field_label(field_name, field_info)
        return f"Enter {label.lower()}..."


class FormGenerator:
    """
    Dynamic form generator using Pydantic model introspection.

    Generates DaisyUI-styled forms with proper variant classes, ARIA support,
    and Alpine.js validation. Supports sections, help text, pre-fill, hidden
    fields, and fragment mode for embedding in article content.

    See: /docs/patterns/FORM_GENERATOR_GUIDE.md
    """

    @staticmethod
    def from_model(
        model_class: type[BaseModel],
        action: str = "",
        method: str = "POST",
        submit_label: str = "Submit",
        include_fields: list[str] | None = None,
        exclude_fields: list[str] | None = None,
        field_order: list[str] | None = None,
        sections: dict[str, list[str]] | None = None,
        custom_widgets: dict[str, Any] | None = None,
        help_texts: dict[str, str] | None = None,
        hidden_fields: dict[str, str] | None = None,
        form_attrs: dict[str, Any] | None = None,
        values: dict[str, Any] | None = None,
        as_fragment: bool = False,
    ) -> Any:
        """
        Generate a DaisyUI form from Pydantic model introspection.

        Args:
            model_class: Pydantic model to introspect
            action: Form action URL (ignored when as_fragment=True)
            method: HTTP method
            submit_label: Submit button label (ignored when as_fragment=True)
            include_fields: Only these fields (ignored when sections is set)
            exclude_fields: Skip these fields (always applied)
            field_order: Custom ordering (ignored when sections is set)
            sections: Grouped fields: {"Section Title": ["field1", "field2"]}
            custom_widgets: Override specific field widgets (still wrapped with label)
            help_texts: Per-field help: {"field": "Helpful text"}
            hidden_fields: Hidden inputs: {"uid": "task_123"}
            form_attrs: Extra form/wrapper attributes (hx_post, cls, x-data override, etc.)
            values: Pre-fill values: {"field": value}
            as_fragment: True = Div with fields only (no form tag, no submit).
                         Use for embedding in article content or composing forms.
        """
        logger.debug("Generating form from %s", model_class.__name__)

        model_fields = model_class.model_fields
        custom_widgets = custom_widgets or {}
        help_texts = help_texts or {}
        hidden_fields = hidden_fields or {}
        values = values or {}
        exclude_fields = exclude_fields or []

        # Build form content — sectioned or flat
        if sections:
            form_fields = FormGenerator._build_sectioned_fields(
                model_class,
                model_fields,
                sections,
                exclude_fields,
                custom_widgets,
                help_texts,
                values,
            )
        else:
            field_names = FormGenerator._resolve_field_names(
                model_fields,
                include_fields,
                exclude_fields,
                field_order,
            )
            form_fields = [
                FormGenerator._generate_field(
                    name,
                    model_fields[name],
                    model_class.__annotations__[name],
                    values.get(name),
                    custom_widgets.get(name),
                    help_texts.get(name),
                )
                for name in field_names
            ]

        # Hidden fields
        for hf_name, hf_value in hidden_fields.items():
            form_fields.append(FTInput(type="hidden", name=hf_name, value=str(hf_value)))

        # Fragment mode: Div with fields only (for embedding in articles)
        if as_fragment:
            wrapper_attrs: dict[str, Any] = {"cls": "space-y-4"}
            if form_attrs:
                wrapper_attrs.update(form_attrs)
            return Div(*form_fields, **wrapper_attrs)

        # Full form mode
        form_fields.append(Button(submit_label, type="submit", variant=ButtonT.primary, cls="mt-4"))

        attrs: dict[str, Any] = {
            "action": action,
            "method": method.upper(),
            "cls": "space-y-4",
            "x-data": "formValidator",
            "@submit": "validate($event)",
        }
        if form_attrs:
            attrs.update(form_attrs)

        return Form(*form_fields, **attrs)

    @staticmethod
    def from_instance(
        model_class: type[BaseModel],
        instance: Any,
        action: str,
        method: str = "POST",
        submit_label: str = "Save",
        **kwargs: Any,
    ) -> Any:
        """
        Generate pre-filled form from an existing entity instance.

        Extracts values from a frozen dataclass or dict, then delegates to from_model().
        """
        if isinstance(instance, dict):
            values = instance
        else:
            values = {
                field_name: getattr(instance, field_name, None)
                for field_name in model_class.model_fields
                if hasattr(instance, field_name)
            }
        return FormGenerator.from_model(
            model_class, action, method, submit_label, values=values, **kwargs
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_field_names(
        model_fields: dict[str, FieldInfo],
        include_fields: list[str] | None,
        exclude_fields: list[str],
        field_order: list[str] | None,
    ) -> list[str]:
        """Resolve which fields to render and in what order."""
        field_names = list(model_fields.keys())

        if include_fields:
            field_names = [f for f in field_names if f in include_fields]

        field_names = [f for f in field_names if f not in exclude_fields]

        if field_order:
            ordered = [f for f in field_order if f in field_names]
            remaining = [f for f in field_names if f not in field_order]
            field_names = ordered + remaining

        return field_names

    @staticmethod
    def _build_sectioned_fields(
        model_class: type[BaseModel],
        model_fields: dict[str, FieldInfo],
        sections: dict[str, list[str]],
        exclude_fields: list[str],
        custom_widgets: dict[str, Any],
        help_texts: dict[str, str],
        values: dict[str, Any],
    ) -> list[Any]:
        """Build form fields grouped into labeled sections with dividers."""
        section_divs: list[Any] = []
        section_items = list(sections.items())
        total_sections = len(section_items)

        for i, (section_title, field_names) in enumerate(section_items):
            fields: list[Any] = []
            for name in field_names:
                if name in exclude_fields or name not in model_fields:
                    continue
                fields.append(
                    FormGenerator._generate_field(
                        name,
                        model_fields[name],
                        model_class.__annotations__[name],
                        values.get(name),
                        custom_widgets.get(name),
                        help_texts.get(name),
                    )
                )
            if fields:
                is_last = i == total_sections - 1
                section_cls = "mb-6" if is_last else "mb-6 pb-6 border-b border-base-200"
                section_divs.append(
                    Div(
                        H3(section_title, cls="text-lg font-semibold mb-3 text-base-content/70"),
                        *fields,
                        cls=section_cls,
                    )
                )

        return section_divs

    @staticmethod
    def _generate_field(
        field_name: str,
        field_info: FieldInfo,
        annotation: type,
        value: Any = None,
        custom_widget: Any = None,
        help_text: str | None = None,
    ) -> Div:
        """Generate a single form field with label, widget, help text, and error display."""
        label_text = FieldWidgetMapper.get_field_label(field_name, field_info)
        is_required = field_info.is_required()

        # Custom widgets still get wrapped with label and error display
        if custom_widget is not None:
            return FormGenerator._wrap_field(
                field_name,
                label_text,
                custom_widget,
                is_required,
                help_text,
            )

        widget_type = FieldWidgetMapper.get_widget_type(field_name, field_info, annotation)
        placeholder = FieldWidgetMapper.get_placeholder(field_name, field_info)
        constraints = FieldWidgetMapper.extract_constraints(field_info)

        widget = FormGenerator._build_widget(
            field_name,
            widget_type,
            annotation,
            placeholder,
            constraints,
            is_required,
            value,
        )

        return FormGenerator._wrap_field(
            field_name,
            label_text,
            widget,
            is_required,
            help_text,
        )

    @staticmethod
    def _wrap_field(
        field_name: str,
        label_text: str,
        widget: Any,
        is_required: bool,
        help_text: str | None,
    ) -> Div:
        """Wrap a widget in form-control with label, optional help text, and error display."""
        children: list[Any] = [
            Label(label_text, **({"required": True} if is_required else {})),
            widget,
        ]
        if help_text:
            children.append(P(help_text, cls="text-sm text-base-content/70 mt-1"))
        # Alpine.js error display (hidden by default, shown by formValidator)
        children.append(
            Div(
                id=f"{field_name}-error",
                role="alert",
                cls="text-sm text-error mt-1",
                style="display:none;",
            )
        )
        return Div(*children, cls="form-control")

    @staticmethod
    def _build_widget(
        field_name: str,
        widget_type: str,
        annotation: type,
        placeholder: str | None,
        constraints: dict[str, Any],
        is_required: bool,
        value: Any = None,
    ) -> Any:
        """
        Build a DaisyUI-styled input widget.

        Uses ui/forms.py wrappers (Input, Select, Textarea, Checkbox) for
        consistent variant classes, ARIA support, and full-width defaults.
        """
        # Normalize: extract .value from Enum, format dates for HTML inputs
        normalized_value = value.value if isinstance(value, Enum) else value
        if (
            normalized_value is not None
            and widget_type in ("date", "datetime-local")
            and hasattr(normalized_value, "isoformat")
        ):
            normalized_value = normalized_value.isoformat()

        # Shared attributes for all widgets
        attrs: dict[str, Any] = {
            "name": field_name,
            "@input": f"clearError('{field_name}')",
            **constraints,
        }
        if is_required:
            attrs["required"] = True
        if placeholder and widget_type not in ("checkbox", "select"):
            attrs["placeholder"] = placeholder

        # Textarea
        if widget_type == "textarea":
            attrs["rows"] = 4
            text_value = str(normalized_value) if normalized_value else ""
            if text_value:
                return Textarea(text_value, **attrs)
            return Textarea(**attrs)

        # Select (enum)
        if widget_type == "select":
            annotation = _unwrap_optional(annotation)
            if isinstance(annotation, type) and issubclass(annotation, Enum):
                options = [
                    Option(
                        str(member.value),
                        value=member.value,
                        selected=(
                            normalized_value is not None and member.value == normalized_value
                        ),
                    )
                    for member in annotation
                ]
                if not is_required:
                    options.insert(
                        0, Option("-- Select --", value="", selected=(normalized_value is None))
                    )
                return Select(*options, **attrs)

        # Checkbox
        if widget_type == "checkbox":
            if normalized_value:
                attrs["checked"] = True
            return Checkbox(**attrs)

        # Standard inputs (text, number, date, datetime-local, email, url)
        attrs["type"] = widget_type
        if normalized_value is not None:
            attrs["value"] = str(normalized_value)
        return Input(**attrs)


# Export main classes
__all__ = ["FieldWidgetMapper", "FormGenerator"]
