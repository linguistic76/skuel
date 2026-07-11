"""SKUEL component layer — pure Tailwind + Alpine.js (ADR-071).

All components follow the FT protocol:

    Component(*c, cls="", **kwargs) -> Any

``cls`` accepts str, tuple, or list. ``**kwargs`` passes through to the
underlying HTML element, so HTMX (hx_*) and Alpine (x_*, @*, :*) attributes
all work without special handling.
"""

from ui.components.accordion import Accordion, AccordionItem
from ui.components.button import Button, ButtonT
from ui.components.card import Card, CardBody, CardFooter, CardHeader, CardTitle
from ui.components.divider import Divider, DividerLine, DividerSplit, DividerT
from ui.components.feedback import Alert, AlertT, Loading, Progress
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
from ui.components.icon import Icon
from ui.components.layout import Center, DivCentered, DivFullySpaced
from ui.components.nav import TabContainer
from ui.components.table import (
    Table,
    TableFromDicts,
    TableFromLists,
    TableT,
    Tbody,
    Td,
    Th,
    Thead,
    Tr,
)

__all__ = [
    # Accordion
    "Accordion",
    "AccordionItem",
    # Button
    "Button",
    "ButtonT",
    # Card
    "Card",
    "CardBody",
    "CardFooter",
    "CardHeader",
    "CardTitle",
    # Divider
    "Divider",
    "DividerLine",
    "DividerSplit",
    "DividerT",
    # Feedback
    "Alert",
    "AlertT",
    "Loading",
    "Progress",
    # Form
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
    "Switch",
    "TextArea",
    # Icon
    "Icon",
    # Layout
    "Center",
    "DivCentered",
    "DivFullySpaced",
    # Nav
    "TabContainer",
    # Table
    "Table",
    "TableFromDicts",
    "TableFromLists",
    "TableT",
    "Tbody",
    "Td",
    "Th",
    "Thead",
    "Tr",
]
