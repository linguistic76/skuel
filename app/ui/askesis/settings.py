"""Askesis settings form."""

from typing import Any

from fasthtml.common import Div, Form, Option

from ui.buttons import Button, ButtonT
from ui.cards import Card
from ui.forms import LabelSelect
from ui.patterns.page_header import PageHeader


def render_settings_form() -> Any:
    """Build the Askesis settings page content."""
    return Div(
        PageHeader("Settings", subtitle="Configure your AI assistant preferences."),
        Div(
            Card(
                Form(
                    LabelSelect(
                        Option("Sonnet 4.5", value="sonnet-4.5", selected=True),
                        Option("Opus 3", value="opus-3"),
                        Option("Haiku 3", value="haiku-3"),
                        label="Default Model",
                        name="default_model",
                        cls="space-y-2 mb-4",
                    ),
                    LabelSelect(
                        Option("Concise", value="concise"),
                        Option("Balanced", value="balanced", selected=True),
                        Option("Detailed", value="detailed"),
                        label="Response Length",
                        name="response_length",
                        cls="space-y-2 mb-4",
                    ),
                    Button("Save Settings", variant=ButtonT.primary, type="submit"),
                    cls="space-y-4",
                ),
                cls="bg-muted p-6",
            ),
            cls="max-w-2xl mx-auto",
        ),
    )
