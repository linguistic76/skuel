"""The fields that are ``Input`` / ``Select`` keep their wiring and take the component's size.

Each site renders through its real function; the pin reads the one visible
field it names and checks the component heights (``md:h-10``, or ``md:h-8`` for
the compact chat chrome) and the HTMX / Alpine / ARIA attributes the site wires
— the components pass them through ``**kwargs``.
"""

import re
from datetime import date
from unittest.mock import MagicMock

import pytest
from fasthtml.common import to_xml

from ui.askesis import chat as askesis_chat
from ui.explore.cards import render_explore_search_panel, render_explore_subtopic_inner
from ui.finance.invoice_views import InvoiceViews
from ui.journals import ModelControl
from ui.journals.chat_page import DiscussionRow
from ui.today.page import _quick_add
from ui.user_entry.forms import render_upload_form


def _field(xml: str, marker: str) -> str:
    """The one ``<input>`` / ``<select>`` open tag carrying ``marker``."""
    tags = [tag for tag in re.findall(r"<(?:input|select)\b[^>]*>", xml) if marker in tag]
    assert len(tags) == 1, tags
    return tags[0]


def _classes(tag: str) -> list[str]:
    found = re.search(r'class="([^"]*)"', tag)
    assert found
    return found.group(1).split()


_SITES = [
    (
        "askesis model",
        lambda: askesis_chat._model_select([("m", "Model M")]),
        'aria-label="Model"',
        "md:h-8",
        ['x-model="selectedModel"', "w-auto"],
    ),
    (
        "askesis topic",
        lambda: askesis_chat._nous_scope_select(["focus"]),
        'aria-label="Scope answer to a NOUS topic"',
        "md:h-8",
        ['x-model="selectedNous"', "max-w-[160px]"],
    ),
    (
        "askesis sub-topic",
        lambda: askesis_chat._nous_subtopic_scope_select({"focus": ["breath"]}),
        'aria-label="Scope answer to a NOUS sub-topic"',
        "md:h-8",
        ['x-model="selectedNousSubtopic"', ':disabled="!selectedNous"'],
    ),
    (
        "askesis search",
        askesis_chat._sb_search_field,
        'type="search"',
        "md:h-8",
        ['aria-label="Search chats"', "pl-9"],
    ),
    (
        "journals model",
        lambda: ModelControl("m", [("m", "Model M")]),
        'name="model"',
        "md:h-8",
        ['aria-label="Model"', "w-auto"],
    ),
    (
        "journals rename",
        lambda: DiscussionRow(MagicMock(session_id="s1", title="Old title")),
        'name="title"',
        "md:h-8",
        ['x-ref="titleInput"', '@keydown.escape="editing = false"', 'value="Old title"'],
    ),
    (
        "explore search",
        lambda: render_explore_search_panel([]),
        'name="q"',
        "md:h-10",
        [
            'x-model="query"',
            'hx-get="/api/explore/search"',
            'hx-trigger="input delay:250ms"',
            "pl-9",
        ],
    ),
    (
        "explore type",
        lambda: render_explore_search_panel([]),
        'name="type"',
        "md:h-10",
        ['hx-get="/api/explore/search"', 'hx-target="#explore-grid"', "w-auto"],
    ),
    (
        "explore nous",
        lambda: render_explore_search_panel([], nous_topics=["focus"]),
        'name="nous"',
        "md:h-10",
        ["hx-include=\"[name='q'], [name='type'], [name='sort']", "w-auto"],
    ),
    (
        "explore sub-topic",
        lambda: render_explore_subtopic_inner(["breath"]),
        'name="nous_subtopic"',
        "md:h-10",
        ['hx-include="closest form"', "w-auto"],
    ),
    (
        "invoice status filter",
        InvoiceViews._render_filter_bar,
        'name="status"',
        "md:h-10",
        ['hx-get="/finance/invoices"', "hx-include=\"[name='type']\"", "mt-1"],
    ),
    (
        "invoice due date",
        InvoiceViews._render_create_form,
        'name="due_date"',
        "md:h-10",
        ['type="date"'],
    ),
    (
        "invoice line quantity",
        lambda: InvoiceViews._render_line_item_row(0),
        'name="items[0][quantity]"',
        "md:h-10",
        ['type="number"', 'step="0.01"', "required"],
    ),
    (
        "submit title",
        render_upload_form,
        'name="title"',
        "md:h-10",
        ['aria-label="Title"', 'maxlength="200"'],
    ),
    (
        "submit class",
        lambda: render_upload_form(teacher_groups=[("g1", "Class A"), ("g2", "Class B")]),
        'name="teacher_group"',
        "md:h-10",
        ['x-model="teacherGroup"', 'aria-label="Which class?"'],
    ),
    (
        "today quick-add",
        lambda: _quick_add(date(2026, 10, 17)),
        'name="title"',
        "md:h-10",
        ['aria-label="New task title"', "flex-1", "min-w-0"],
    ),
]


@pytest.mark.parametrize(
    ("render", "marker", "md_height", "carried"),
    [site[1:] for site in _SITES],
    ids=[site[0] for site in _SITES],
)
def test_a_field_has_the_component_size_and_keeps_its_wiring(
    render: object, marker: str, md_height: str, carried: list[str]
) -> None:
    assert callable(render)
    tag = _field(to_xml(render()), marker)
    classes = _classes(tag)
    assert "h-11" in classes and md_height in classes
    for expected in carried:
        assert expected in classes or expected in tag, expected


def test_an_added_invoice_line_item_is_the_component_row() -> None:
    """The "+ Add Line Item" button clones a template of the component row from a live script."""
    xml = to_xml(InvoiceViews._render_create_form())
    assert "&lt;script" not in xml
    assert re.search(r"<script>\s*let lineItemCount", xml)
    template = re.search(r'<template id="line-item-template">(.*?)</template>', xml, re.DOTALL)
    assert template
    fields = re.findall(r"<input\b[^>]*>", template.group(1))
    assert len(fields) == 3
    for tag in fields:
        assert "items[__INDEX__]" in tag
        assert {"h-11", "md:h-10"} <= set(_classes(tag))
    assert 'aria-label="Remove line item"' in template.group(1)
