"""The fields that are ``Input`` / ``Select`` keep their wiring and take the component's size.

Each site renders through its real function; the pin reads the one visible
field it names and checks the component heights (``md:h-10``, or ``md:h-8`` for
the compact chat chrome) and the HTMX / Alpine / ARIA attributes the site wires
— the components pass them through ``**kwargs``.
"""

import re
from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest
from fasthtml.common import FT, to_xml

from core.models.enums.pipeline import ReportSource
from core.models.report.activity_report import ActivityReport
from ui.askesis import chat as askesis_chat
from ui.components import COMPOSER_FOCUS_RING, Button
from ui.components.button import _BTN_BASE, _BTN_SIZES
from ui.components.form import _TEXTAREA_BASE
from ui.explore.cards import render_explore_search_panel, render_explore_subtopic_inner
from ui.explore.ku_mastery import render_ku_mastery_section
from ui.finance.invoice_views import InvoiceViews
from ui.journals import ModelControl, PeriodicNoteFragment, _Composer, _ReviewGate
from ui.journals.chat_page import DiscussionRow, _landing_text_form
from ui.learning_loop.report import render_activity_report_detail
from ui.search import components as search_components
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


# ---------------------------------------------------------------------------
# Buttons beside fields take ``Button(size="field")``.
# ---------------------------------------------------------------------------

# Height, padding and text-size utilities — the geometry a size owns.
_GEOMETRY = re.compile(
    r"^(md:|lg:)?(h|min-h|p|px|py|pt|pb|pl|pr)-|^(md:|lg:)?text-(xs|sm|base|lg|\d)"
)


def _button(xml: str, marker: str) -> str:
    """The one ``<button>`` open tag carrying ``marker``."""
    tags = [tag for tag in re.findall(r"<button\b[^>]*>", xml) if marker in tag]
    assert len(tags) == 1, tags
    return tags[0]


_BUTTON_SITES = [
    (
        "explore more filters",
        lambda: render_explore_search_panel([]),
        'x-on:click="moreFilters = !moreFilters"',
    ),
    (
        "search more filters",
        lambda: search_components._render_filter_panel([], {}, []),
        'x-on:click="moreFilters = !moreFilters"',
    ),
    ("today quick-add", lambda: _quick_add(date(2026, 10, 17)), 'type="submit"'),
]


def test_the_field_size_is_the_field_heights() -> None:
    assert {"h-11", "md:h-10"} <= set(_BTN_SIZES["field"].split())
    assert set(_BTN_SIZES["field"].split()) <= set(_classes(to_xml(Button("x", size="field"))))


@pytest.mark.parametrize(
    ("render", "marker"), [site[1:] for site in _BUTTON_SITES], ids=[s[0] for s in _BUTTON_SITES]
)
def test_a_button_beside_fields_has_the_field_size_and_no_second_geometry(
    render: object, marker: str
) -> None:
    """The component's base and ``field`` size lead the class list; ``cls`` adds no geometry."""
    assert callable(render)
    classes = _classes(_button(to_xml(render()), marker))
    sized = [*_BTN_BASE.split(), *_BTN_SIZES["field"].split()]
    assert classes[: len(sized)] == sized
    assert not [c for c in classes[len(sized) :] if _GEOMETRY.match(c)]


# ---------------------------------------------------------------------------
# Plain textareas are ``TextArea``; the chat composers stay raw with a ring.
# ---------------------------------------------------------------------------

# Height, padding, text size, border and background — the look ``TextArea`` owns.
_TEXTAREA_LOOK = re.compile(
    r"^(md:|lg:)?(h|min-h|p|px|py|pt|pb|pl|pr)-|^(md:|lg:)?text-(xs|sm|base|lg|\d)"
    r"|^(border|bg|rounded)(-|$)"
)


def _textarea(xml: str, marker: str) -> str:
    tags = [tag for tag in re.findall(r"<textarea\b[^>]*>", xml) if marker in tag]
    assert len(tags) == 1, tags
    return tags[0]


def _report() -> ActivityReport:
    at = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
    return ActivityReport(
        uid="ar_notes",
        title="Activity Report",
        user_uid="user_reports",
        subject_uid="user_reports",
        processor_type=ReportSource.AUTOMATIC,
        time_period="7d",
        period_start=at,
        period_end=at,
        processed_content="# Progress Report",
        created_at=at,
    )


_TEXTAREA_SITES = [
    ("invoice notes", InvoiceViews._render_create_form, 'name="notes"', ['rows="2"']),
    (
        "periodic note",
        lambda: PeriodicNoteFragment("ue_note", "Note", "draft"),
        'name="content"',
        ['rows="18"', "resize-y"],
    ),
    (
        "review gate notes",
        lambda: _ReviewGate(2, {"k": "v"}, "/journals/stage", "Next", "Your notes"),
        'name="review_notes"',
        ['rows="4"', "mt-1", "resize-y"],
    ),
    (
        "report notes",
        lambda: render_activity_report_detail(_report()),
        'name="annotation_text"',
        ['rows="4"'],
    ),
    (
        "ku mastery reflection",
        lambda: render_ku_mastery_section("ku.demo.breath", []),
        'name="reflection"',
        ['x-model="note"', 'rows="2"', "resize-none"],
    ),
]


@pytest.mark.parametrize(
    ("render", "marker", "carried"),
    [site[1:] for site in _TEXTAREA_SITES],
    ids=[site[0] for site in _TEXTAREA_SITES],
)
def test_a_plain_textarea_is_the_component_and_keeps_its_wiring(
    render: object, marker: str, carried: list[str]
) -> None:
    assert callable(render)
    tag = _textarea(to_xml(render()), marker)
    classes = _classes(tag)
    base = _TEXTAREA_BASE.split()
    assert classes[: len(base)] == base
    assert not [c for c in classes[len(base) :] if _TEXTAREA_LOOK.match(c)]
    for expected in carried:
        assert expected in classes or expected in tag, expected


def _parent_of_textarea(node: object) -> FT | None:
    """The element whose own children include the one ``<textarea>``."""
    if not isinstance(node, FT):
        return None
    if any(isinstance(child, FT) and child.tag == "textarea" for child in node.children):
        return node
    for child in node.children:
        found = _parent_of_textarea(child)
        if found is not None:
            return found
    return None


_COMPOSERS = [
    ("askesis", lambda: askesis_chat._composer_form([], {})),
    ("journal follow-up", lambda: _Composer("Title", "scribe")),
    ("journal landing", lambda: _landing_text_form([], False)),
]


@pytest.mark.parametrize("render", [c[1] for c in _COMPOSERS], ids=[c[0] for c in _COMPOSERS])
def test_a_composer_box_shows_the_focus_ring_for_its_raw_textarea(render: object) -> None:
    assert callable(render)
    box = _parent_of_textarea(render())
    assert box is not None
    textarea = next(c for c in box.children if isinstance(c, FT) and c.tag == "textarea")
    assert "min-h-[80px]" not in str(textarea.attrs.get("class", ""))  # raw, borderless
    assert textarea.attrs.get("aria-label")
    assert set(COMPOSER_FOCUS_RING.split()) <= set(str(box.attrs["class"]).split())
