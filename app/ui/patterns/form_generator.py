"""
FormGenerator - Dynamic Form Generation from Pydantic Models
=============================================================

Generates forms from Pydantic model introspection. Supports
sections, help text, pre-fill, hidden fields, and fragment mode for
embedding forms within curriculum content.

For Activity Domain forms (Tasks, Goals, Habits, Events, Choices, Principles),
prefer :func:`ui.patterns.activity_form_helper.render_activity_form` — it
encodes the action URL / submit label / form id conventions on top of this.

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
from core.utils.csrf_token_context import CSRF_FORM_FIELD, current_csrf_token
from core.utils.logging import get_logger
from ui.components import Button, ButtonT, Icon
from ui.forms import Checkbox, Input, Label, Select, Textarea

logger = get_logger("skuel.components.form_generator")

# Section accent palette — rotated when callers don't specify an accent.
# Tailwind tokens used: border-l-{color}-500, text-{color}-600, bg-{color}-500/10.
# Tailwind here is loaded via Play CDN (no purge), so dynamic class names work.
_ACCENT_ROTATION: tuple[str, ...] = ("blue", "amber", "emerald", "violet", "rose", "cyan")


def _accent_classes(accent: str) -> tuple[str, str, str]:
    """Return (card_stripe, icon_color, icon_bg) class strings for an accent."""
    return (
        f"border-l-4 border-l-{accent}-500",
        f"text-{accent}-600 dark:text-{accent}-400",
        f"bg-{accent}-500/10",
    )


def _is_union_type(origin: type | None) -> bool:
    """Check if origin is a Union type (handles both typing.Union and PEP 604 X | Y)."""
    return origin is Union or origin is types.UnionType  # type: ignore[comparison-overlap]


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
    """Maps Pydantic field types to widget types via introspection."""

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

        # Handle Optional[T] / T | None — recompute origin so checks below
        # see the unwrapped inner type (e.g. Optional[list[str]] -> list).
        origin = get_origin(annotation)
        if origin is not None and _is_union_type(origin):
            annotation = _unwrap_optional(annotation)
            origin = get_origin(annotation)

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

    Generates SKUEL-component forms with proper variant classes, ARIA support,
    and Alpine.js validation. Supports sections, help text, pre-fill, hidden
    fields, and fragment mode for embedding in curriculum content.

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
        sections: dict[str, list[str]] | dict[str, dict[str, Any]] | None = None,
        custom_widgets: dict[str, Any] | None = None,
        help_texts: dict[str, str] | None = None,
        labels: dict[str, str] | None = None,
        placeholders: dict[str, str] | None = None,
        hidden_fields: dict[str, str] | None = None,
        form_attrs: dict[str, Any] | None = None,
        values: dict[str, Any] | None = None,
        as_fragment: bool = False,
    ) -> Any:
        """
        Generate a form from Pydantic model introspection.

        Args:
            model_class: Pydantic model to introspect
            action: Form action URL (ignored when as_fragment=True)
            method: HTTP method
            submit_label: Submit button label (ignored when as_fragment=True)
            include_fields: Only these fields (ignored when sections is set)
            exclude_fields: Skip these fields (always applied)
            field_order: Custom ordering (ignored when sections is set)
            sections: Grouped fields. Either a flat mapping
                ``{"Section": ["field1", "field2"]}`` (accent auto-rotated, no icon),
                or a config mapping
                ``{"Section": {"fields": [...], "icon": "calendar", "accent": "amber"}}``.
                Accent values are Tailwind color names (blue, amber, emerald, violet,
                rose, cyan). Icon values are Lucide icon names rendered via Icon.
            custom_widgets: Override specific field widgets (still wrapped with label)
            help_texts: Per-field help: {"field": "Helpful text"}
            labels: Override per-field label text (priority over Pydantic description).
            placeholders: Override per-field placeholder text.
            hidden_fields: Hidden inputs: {"uid": "task_123"}
            form_attrs: Extra form/wrapper attributes (hx_post, cls, x-data override, etc.)
            values: Pre-fill values: {"field": value}
            as_fragment: True = Div with fields only (no form tag, no submit).
                         Use for embedding in path step content or composing forms.
        """
        logger.debug("Generating form from %s", model_class.__name__)

        model_fields = model_class.model_fields
        custom_widgets = custom_widgets or {}
        help_texts = help_texts or {}
        labels = labels or {}
        placeholders = placeholders or {}
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
                labels,
                placeholders,
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
                    labels.get(name),
                    placeholders.get(name),
                )
                for name in field_names
            ]

        # Hidden fields
        for hf_name, hf_value in hidden_fields.items():
            form_fields.append(FTInput(type="hidden", name=hf_name, value=str(hf_value)))

        # Auto-inject CSRF token for mutating forms. Fragments are composed
        # into a parent form that already carries the token, so skip there.
        if not as_fragment and method.upper() != "GET" and CSRF_FORM_FIELD not in hidden_fields:
            token = current_csrf_token()
            if token:
                form_fields.append(FTInput(type="hidden", name=CSRF_FORM_FIELD, value=token))

        # Fragment mode: Div with fields only (for embedding in path steps)
        if as_fragment:
            wrapper_attrs: dict[str, Any] = {"cls": "space-y-4"}
            if form_attrs:
                wrapper_attrs.update(form_attrs)
            return Div(*form_fields, **wrapper_attrs)

        # Full form mode — submit button sits in a sticky-feeling footer bar so
        # it's clearly separated from the section cards above.
        form_fields.append(
            Div(
                Button(submit_label, type="submit", cls=ButtonT.primary),
                cls="flex justify-end pt-2",
            )
        )

        attrs: dict[str, Any] = {
            "action": action,
            "method": method.upper(),
            "cls": "space-y-4 max-w-3xl",
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
            _missing = object()
            values = {
                field_name: val
                for field_name in model_class.model_fields
                if (val := getattr(instance, field_name, _missing)) is not _missing
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
        sections: dict[str, list[str]] | dict[str, dict[str, Any]],
        exclude_fields: list[str],
        custom_widgets: dict[str, Any],
        help_texts: dict[str, str],
        labels: dict[str, str],
        placeholders: dict[str, str],
        values: dict[str, Any],
    ) -> list[Any]:
        """Build form fields grouped into labeled section cards with icon + accent stripe."""
        section_divs: list[Any] = []

        for index, (section_title, raw_config) in enumerate(sections.items()):
            # Normalize: list[str] -> {"fields": list[str]}
            icon_name: str | None
            accent: str | None
            if isinstance(raw_config, dict):
                field_names = raw_config.get("fields", [])
                icon_name = raw_config.get("icon")
                accent = raw_config.get("accent")
            else:
                field_names = list(raw_config)
                icon_name = None
                accent = None

            accent = accent or _ACCENT_ROTATION[index % len(_ACCENT_ROTATION)]
            stripe_cls, icon_text_cls, icon_bg_cls = _accent_classes(accent)

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
                        labels.get(name),
                        placeholders.get(name),
                    )
                )
            if not fields:
                continue

            header_children: list[Any] = []
            if icon_name:
                header_children.append(
                    Div(
                        Icon(icon_name, size=18, cls=icon_text_cls),
                        cls=(
                            f"size-9 rounded-md flex items-center justify-center "
                            f"shrink-0 {icon_bg_cls}"
                        ),
                    )
                )
            header_children.append(H3(section_title, cls="text-base font-semibold"))

            section_divs.append(
                Div(
                    Div(
                        *header_children,
                        cls="flex items-center gap-3 mb-4 pb-3 border-b border-border",
                    ),
                    Div(*fields, cls="space-y-4"),
                    cls=(
                        "rounded-lg border border-border bg-card "
                        f"text-card-foreground shadow-xs p-6 {stripe_cls}"
                    ),
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
        label_override: str | None = None,
        placeholder_override: str | None = None,
    ) -> Div:
        """Generate a single form field with label, widget, help text, and error display."""
        label_text = label_override or FieldWidgetMapper.get_field_label(field_name, field_info)
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
        placeholder = placeholder_override or FieldWidgetMapper.get_placeholder(
            field_name, field_info
        )
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
            Label(label_text, required=is_required),
            widget,
        ]
        if help_text:
            children.append(P(help_text, cls="text-sm text-muted-foreground mt-1"))
        # Alpine.js error display (hidden by default, shown by formValidator)
        children.append(
            Div(
                id=f"{field_name}-error",
                role="alert",
                cls="text-sm text-error mt-1",
                style="display:none;",
            )
        )
        return Div(*children, cls="space-y-2")

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
        Build a SKUEL-component input widget.

        Uses ui/forms.py wrappers (Input, Select, Textarea, Checkbox) for
        consistent variant classes, ARIA support, and full-width defaults.
        """
        # Normalize: extract .value from Enum, format dates for HTML inputs
        normalized_value = value.value if isinstance(value, Enum) else value
        if (
            normalized_value is not None
            and widget_type in ("date", "datetime-local")
            and isinstance(normalized_value, (date, datetime))
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
            if isinstance(normalized_value, (list, tuple)):
                text_value = "\n".join(str(item) for item in normalized_value)
            elif normalized_value:
                text_value = str(normalized_value)
            else:
                text_value = ""
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

        # Checkbox — paired with a hidden companion so the control posts on EVERY submit.
        # An unchecked box is not a successful control: the browser omits it entirely, which
        # reads downstream as "field absent" — UNSET on an update intent — so a box that is
        # already checked can never be UNchecked from an edit form. The hidden input carries
        # "false" and renders first; a checked box appends "true" after it, and Starlette's
        # FormData resolves a repeated key to its LAST value, so checked still wins.
        if widget_type == "checkbox":
            attrs["value"] = "true"
            if normalized_value:
                attrs["checked"] = True
            return (
                FTInput(type="hidden", name=field_name, value="false"),
                Checkbox(**attrs),
            )

        # Standard inputs (text, number, date, datetime-local, email, url)
        attrs["type"] = widget_type
        if normalized_value is not None:
            attrs["value"] = str(normalized_value)
        return Input(**attrs)


# Export main classes
__all__ = ["FieldWidgetMapper", "FormGenerator"]
