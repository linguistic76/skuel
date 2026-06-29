"""
SKUEL Form Components
=====================

Public form component API. Thin delegation layer — all rendering via ui.components.form (pure Tailwind).
Standalone inputs (Input, Select, Textarea) for cases without labels.
LabelInput/LabelTextArea/LabelSelect for label+input combos with ARIA accessibility.
"""

from ui.components.form import (
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
    Switch,
    TextArea,
)

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

# Public-API aliases — callers use these names; internal modules export TextArea/Switch.
Textarea = TextArea
Toggle = Switch
