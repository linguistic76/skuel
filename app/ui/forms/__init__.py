"""
Forms UI package.

Re-exports all form components from ui.forms.components (formerly ui/forms.py)
plus the inline form template renderer.
"""

from ui.forms.components import (
    Checkbox,
    Input,
    Label,
    LabelCheckbox,
    LabelInput,
    LabelSelect,
    LabelTextArea,
    Radio,
    Range,
    Select,
    Textarea,
    Toggle,
)
from ui.forms.inline_form_template import render_inline_form_template

__all__ = [
    "Checkbox",
    "Input",
    "Label",
    "LabelCheckbox",
    "LabelInput",
    "LabelSelect",
    "LabelTextArea",
    "Radio",
    "Range",
    "Select",
    "Textarea",
    "Toggle",
    "render_inline_form_template",
]
