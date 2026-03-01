"""
FormGenerator - Dynamic Form Generation from Pydantic Models
=============================================================

Generates DaisyUI forms automatically from Pydantic model introspection.

Following the 100% dynamic architecture vision:
- Models define structure → UI auto-generates
- Add field to Pydantic model → Form auto-updates
- No manual form composition needed

Usage:
    from core.models.task.task_request import TaskCreateRequest
    from ui.patterns.form_generator import FormGenerator

    # Auto-generate form from model
    form = FormGenerator.from_model(
        TaskCreateRequest,
        action="/api/tasks",
        method="POST"
    )

Version: 2.0.0 (January 2026) - DaisyUI Migration
"""

from datetime import date, datetime
from enum import Enum
from typing import Any, get_args, get_origin

from fasthtml.common import Div, Form, Label, Option
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
from ui.daisy_components import Button, ButtonT, Input, InputT, Select, Textarea

logger = get_logger("skuel.components.form_generator")


class FieldWidgetMapper:
    """
    Maps Pydantic field types to DaisyUI components.

    Uses introspection to determine the appropriate UI component
    based on field type, constraints, and metadata.
    """

    @staticmethod
    def get_widget_type(field_name: str, field_info: FieldInfo, annotation: type) -> str:
        """
        Determine widget type from field introspection.

        Priority:
        1. Explicit metadata hint (metadata={'ui_widget': 'textarea'})
        2. Field type inference (str → input, int → number, etc.)
        3. Field constraints (max_length > 100 → textarea)
        """
        # Check for explicit UI widget metadata
        if isinstance(field_info, PydanticFieldInfo):
            for meta in field_info.metadata:
                if isinstance(meta, dict) and "ui_widget" in meta:
                    return str(meta["ui_widget"])

        # Get origin type (handles Optional, List, etc.)
        origin = get_origin(annotation)
        if origin is not None and (origin is type(None) or str(origin) == "typing.Union"):
            # Handle Optional[T] → extract T
            args = get_args(annotation)
            if args:
                annotation = (
                    args[0] if args[0] is not type(None) else (args[1] if len(args) > 1 else str)
                )

        # Enum → select dropdown
        if isinstance(annotation, type) and issubclass(annotation, Enum):
            return "select"

        # List → multi-select or tags (use textarea for now)
        if origin is list:
            return "textarea"  # Can be enhanced to tags widget

        # Date/DateTime → date/datetime input
        if annotation is date:
            return "date"
        if annotation is datetime:
            return "datetime-local"

        # Boolean → checkbox
        if annotation is bool:
            return "checkbox"

        # Integer/Float → number input
        if annotation in (int, float):
            return "number"

        # String with constraints
        if annotation is str:
            # Long text → textarea
            max_length = getattr(field_info, "max_length", None)
            if max_length and max_length > 100:
                return "textarea"

            # Check field name hints
            if any(
                keyword in field_name.lower()
                for keyword in ["description", "notes", "content", "body"]
            ):
                return "textarea"

            # Check metadata for email, url, etc.
            if isinstance(field_info, PydanticFieldInfo):
                for meta in field_info.metadata:
                    if isinstance(meta, dict):
                        if meta.get("format") == "email":
                            return "email"
                        if meta.get("format") == "url":
                            return "url"

            # Default string → text input
            return "text"

        # Fallback
        return "text"

    @staticmethod
    def extract_constraints(field_info: FieldInfo) -> dict[str, Any]:
        """
        Extract validation constraints from field info.

        Returns dict of HTML input attributes like:
        - min, max (for numbers)
        - minlength, maxlength (for strings)
        - pattern (for regex)
        - required (for non-optional fields)
        """
        constraints = {}

        # Pydantic v2 stores constraints in metadata
        # Check metadata list for constraint objects using Protocols
        if isinstance(field_info, PydanticFieldInfo) and field_info.metadata:
            for constraint in field_info.metadata:
                # MinLen constraint
                if isinstance(constraint, MinLenConstraint):
                    constraints["minlength"] = constraint.min_length
                # MaxLen constraint
                if isinstance(constraint, MaxLenConstraint):
                    constraints["maxlength"] = constraint.max_length
                # Ge (greater than or equal)
                if isinstance(constraint, GeConstraint):
                    constraints["min"] = constraint.ge
                # Le (less than or equal)
                if isinstance(constraint, LeConstraint):
                    constraints["max"] = constraint.le
                # Gt (greater than)
                if isinstance(constraint, GtConstraint):
                    constraints["min"] = constraint.gt + 0.01
                # Lt (less than)
                if isinstance(constraint, LtConstraint):
                    constraints["max"] = constraint.lt - 0.01

        return constraints

    @staticmethod
    def get_field_label(field_name: str, field_info: FieldInfo) -> str:
        """
        Generate user-friendly label from field name.

        Priority:
        1. Explicit metadata label (metadata={'ui_label': 'Task Title'})
        2. Field description from Pydantic
        3. Auto-generated from field_name (task_title → Task Title)
        """
        # Check for explicit label in metadata
        if isinstance(field_info, PydanticFieldInfo):
            for meta in field_info.metadata:
                if isinstance(meta, dict) and "ui_label" in meta:
                    return str(meta["ui_label"])

        # Use description if available
        if field_info.description:
            return field_info.description

        # Auto-generate from field name
        # task_title → Task Title
        return " ".join(word.capitalize() for word in field_name.split("_"))

    @staticmethod
    def get_placeholder(field_name: str, field_info: FieldInfo) -> str | None:
        """
        Generate placeholder text.

        Priority:
        1. Explicit metadata (metadata={'ui_placeholder': 'Enter title...'})
        2. Auto-generated from label
        """
        # Check for explicit placeholder
        if isinstance(field_info, PydanticFieldInfo):
            for meta in field_info.metadata:
                if isinstance(meta, dict) and "ui_placeholder" in meta:
                    return str(meta["ui_placeholder"])

        # Auto-generate
        label = FieldWidgetMapper.get_field_label(field_name, field_info)
        return f"Enter {label.lower()}..."


class FormGenerator:
    """
    Dynamic form generator using Pydantic model introspection.

    Follows 100% dynamic architecture:
    - Introspects model fields via model.__fields__
    - Determines widget types via type annotations
    - Applies constraints from Pydantic validators
    - Generates DaisyUI components with type-safe enums
    """

    @staticmethod
    def from_model(
        model_class: type[BaseModel],
        action: str,
        method: str = "POST",
        submit_label: str = "Submit",
        include_fields: list[str] | None = None,
        exclude_fields: list[str] | None = None,
        field_order: list[str] | None = None,
        custom_widgets: dict[str, Any] | None = None,
        form_attrs: dict[str, Any] | None = None,
    ) -> Form:
        """
        Generate form from Pydantic model introspection.

        Args:
            model_class: Pydantic model class to introspect,
            action: Form action URL,
            method: HTTP method (POST, PATCH, etc.),
            submit_label: Label for submit button,
            include_fields: Only include these fields (None = all),
            exclude_fields: Exclude these fields (None = exclude none),
            field_order: Custom field ordering (None = model order),
            custom_widgets: Override widgets for specific fields,
            form_attrs: Additional form attributes (hx_*, cls, etc.)

        Returns:
            DaisyUI Form component

        Example:
            form = FormGenerator.from_model(
                TaskCreateRequest,
                action="/api/tasks",
                method="POST",
                exclude_fields=['uid', 'created_at'],
                custom_widgets={
                    'description': Textarea(rows=5)
                }
            )
        """
        logger.info(f"Generating form from {model_class.__name__}")

        # Get model fields via introspection
        model_fields = model_class.model_fields

        # Determine which fields to include
        field_names = list(model_fields.keys())

        if include_fields:
            field_names = [f for f in field_names if f in include_fields]

        if exclude_fields:
            field_names = [f for f in field_names if f not in exclude_fields]

        # Apply custom ordering
        if field_order:
            ordered_fields = [f for f in field_order if f in field_names]
            remaining_fields = [f for f in field_names if f not in field_order]
            field_names = ordered_fields + remaining_fields

        # Generate form fields
        form_fields = []
        custom_widgets = custom_widgets or {}

        for field_name in field_names:
            field_info = model_fields[field_name]

            # Use custom widget if provided
            if field_name in custom_widgets:
                form_fields.append(custom_widgets[field_name])
                continue

            # Generate field component via introspection
            field_component = FormGenerator._generate_field(
                field_name, field_info, model_class.__annotations__[field_name]
            )

            form_fields.append(field_component)

        # Add submit button
        form_fields.append(Button(submit_label, type="submit", variant=ButtonT.primary, cls="mt-4"))

        # Build form attributes
        attrs = {
            "action": action,
            "method": method.upper(),
            "cls": "space-y-4",
            # Add Alpine.js form validation
            "x-data": "formValidator",
            "@submit": "validate($event)",
        }

        # Merge custom attributes
        if form_attrs:
            attrs.update(form_attrs)

        # Return generated form
        form = Form(*form_fields, **attrs)

        logger.info(f"✅ Generated form with {len(form_fields) - 1} fields (validation enabled)")
        return form

    @staticmethod
    def _generate_field(field_name: str, field_info: FieldInfo, annotation: type) -> Div:
        """
        Generate a single form field with label and input.

        Uses introspection to determine:
        - Widget type (text, number, select, etc.)
        - Label text
        - Placeholder
        - Validation constraints
        - Required status
        """
        # Determine widget type via introspection
        widget_type = FieldWidgetMapper.get_widget_type(field_name, field_info, annotation)

        # Extract metadata
        label_text = FieldWidgetMapper.get_field_label(field_name, field_info)
        placeholder = FieldWidgetMapper.get_placeholder(field_name, field_info)
        constraints = FieldWidgetMapper.extract_constraints(field_info)

        # Determine if required
        is_required = field_info.is_required()

        # Build widget based on type
        widget = FormGenerator._build_widget(
            field_name, widget_type, annotation, placeholder, constraints, is_required
        )

        # Wrap in form control div with error display
        return Div(
            Label(label_text, **({"required": True} if is_required else {}), cls="label"),
            widget,
            # Error message div (hidden by default, shown by formValidator)
            Div(
                id=f"{field_name}-error",
                role="alert",
                cls="text-sm text-error mt-1",
                style="display:none;",
            ),
            cls="form-control",
        )

    @staticmethod
    def _build_widget(
        field_name: str,
        widget_type: str,
        annotation: type,
        placeholder: str | None,
        constraints: dict[str, Any],
        is_required: bool,
    ) -> Any:
        """
        Build the actual input widget.

        Supports:
        - text, email, url, number, date, datetime-local
        - textarea
        - select (for enums)
        - checkbox
        """
        base_attrs = {
            "name": field_name,
            "cls": "input" if widget_type != "textarea" else "textarea",
            **constraints,
            # Add Alpine.js error clearing on input
            "@input": f"clearError('{field_name}')",
        }

        if is_required:
            base_attrs["required"] = True

        if placeholder and widget_type not in ["checkbox", "select"]:
            base_attrs["placeholder"] = placeholder

        # Textarea
        if widget_type == "textarea":
            base_attrs["cls"] = "textarea"
            base_attrs["rows"] = 4
            return Textarea(**base_attrs)

        # Select (for enums)
        if widget_type == "select":
            # Extract enum values via introspection
            origin = get_origin(annotation)
            if origin is not None:
                args = get_args(annotation)
                if args:
                    annotation = (
                        args[0]
                        if args[0] is not type(None)
                        else (args[1] if len(args) > 1 else annotation)
                    )

            if isinstance(annotation, type) and issubclass(annotation, Enum):
                # Type is known to be Enum, use .value directly (per CLAUDE.md Oct 5 update)
                options = [Option(str(member.value), value=member.value) for member in annotation]

                # Add empty option if not required
                if not is_required:
                    options.insert(0, Option("-- Select --", value=""))

                base_attrs["cls"] = "select"
                return Select(*options, **base_attrs)

        # Checkbox
        if widget_type == "checkbox":
            base_attrs["type"] = "checkbox"
            base_attrs["cls"] = "checkbox"
            return Input(**base_attrs)

        # Standard inputs (text, number, date, etc.)
        base_attrs["type"] = widget_type
        return Input(**base_attrs)


class FormGeneratorExamples:
    """
    Example usage patterns for FormGenerator.

    Demonstrates various use cases and customization options.
    """

    @staticmethod
    def basic_form_example() -> Any:
        """Most basic usage - just pass the model"""
        from core.models.task.task_request import TaskCreateRequest

        return FormGenerator.from_model(TaskCreateRequest, action="/api/tasks", method="POST")

    @staticmethod
    def custom_fields_example() -> Any:
        """Selective field inclusion and ordering"""
        from core.models.task.task_request import TaskCreateRequest

        return FormGenerator.from_model(
            TaskCreateRequest,
            action="/api/tasks",
            method="POST",
            include_fields=["title", "description", "due_date", "priority"],
            field_order=["title", "priority", "due_date", "description"],
        )

    @staticmethod
    def custom_widgets_example() -> Any:
        """Override specific field widgets"""
        from core.models.task.task_request import TaskCreateRequest

        return FormGenerator.from_model(
            TaskCreateRequest,
            action="/api/tasks",
            method="POST",
            custom_widgets={
                "description": Textarea(
                    name="description",
                    rows=8,
                    placeholder="Detailed task description...",
                    variant=InputT.bordered,
                )
            },
        )

    @staticmethod
    def htmx_form_example() -> Any:
        """HTMX-enhanced form"""
        from core.models.task.task_request import TaskCreateRequest

        return FormGenerator.from_model(
            TaskCreateRequest,
            action="/api/tasks",
            method="POST",
            form_attrs={
                "hx_post": "/api/tasks",
                "hx_target": "#task-list",
                "hx_swap": "beforeend",
                "cls": "space-y-4 p-4 bg-base-100 rounded shadow",
            },
        )


# Export main classes
__all__ = ["FieldWidgetMapper", "FormGenerator", "FormGeneratorExamples"]
