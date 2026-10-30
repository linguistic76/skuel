"""The page shell owns the gutter: a body handed to a padded shell pads none of its own.

``SidebarPage`` pads its content column (``px-4 sm:px-6 lg:px-8 py-4 lg:py-6``) and
``BasePage(STANDARD)`` pads its own (``Spacing.PAGE``). A body that pads its sides
as well doubles the gutter — at 375px two ``px-4`` put 32px before the first card, a
quarter of the width gone to margin — and one that pads its top or bottom again, or
puts a margin there, pushes the page down. Spacing between siblings belongs to their
parent, which adds none at its own edges. ``BasePage(page_type=CUSTOM)`` pads
nothing, so a body there pads itself.

The census (``_gutter_census.py``) finds every body handed to a padded shell, through
wrappers, helpers and HTMX fragments, by reading the source; nothing here names the
pages it checks, and nothing is exempt. The census states its own holes, and their
count is pinned: a new hole is a body nobody has checked.
"""

from __future__ import annotations

import io
import re
import tokenize
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fasthtml.common import fast_app, to_xml
from starlette.testclient import TestClient

from adapters.inbound.system_ui import create_system_ui_routes
from core.models.enums.entity_enums import EntityStatus
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry import UserEntry, periodic_note_uid
from tests.unit.ui import _gutter_census as census
from ui.journals.chat_page import PeriodicNotePage
from ui.lifepath.dashboard import render_dashboard_content

# Every hole the census leaves, read by hand: the refusal renderers ``refuse`` is
# handed (an error banner) and a refusal that is a bare 404 ``Response``; the
# Activity and exchange cards (each draws its own box); a field's help text; a
# section label's text; the Insights hub cards (their URL comes from a method);
# an out-of-band HTMX swap; Today's date label. A new hole is a body nobody has read.
UNRESOLVED = 10


@pytest.fixture(scope="module")
def taken() -> census.Census:
    return census.take()


def _where(element: census.Element) -> str:
    return f"{element.where} [{','.join(sorted(element.modes))}] {' '.join(element.classes)}"


def test_no_shelled_body_pads_its_own_sides(taken: census.Census) -> None:
    assert [_where(e) for e in taken.side] == []


def test_no_shelled_body_pads_its_own_top_or_bottom(taken: census.Census) -> None:
    assert [_where(e) for e in taken.vertical] == []


def test_no_shelled_body_spaces_its_own_top_or_bottom_with_a_margin(taken: census.Census) -> None:
    """A margin at the body's top or bottom edge sits inside the shell's padding, so it
    doubles the shell's space as padding there does. Spacing between siblings belongs
    to their parent (``space-y-*`` / ``gap-*``), which puts none at its own edges."""
    assert [f"{_where(e)} via {min(e.chains)}" for e in taken.margins] == []


def test_the_census_holes_are_the_ones_read_by_hand(taken: census.Census) -> None:
    holes = "\n".join(f"{where} {what}" for where, what in sorted(taken.unresolved))

    assert len(taken.unresolved) == UNRESOLVED, holes


# ----------------------------------------------------------------- controls


def _shell_calls(text: str, names: set[str]) -> Iterator[str]:
    """Each shell or wrapper name the tokenizer sees called — never one in a string or comment."""
    code = [
        t
        for t in tokenize.generate_tokens(io.StringIO(text).readline)
        if t.type in (tokenize.NAME, tokenize.OP)
    ]
    for before, name, paren in zip(code, code[1:], code[2:], strict=False):
        if name.string in names and paren.string == "(" and before.string != "def":
            yield name.string


def test_the_census_reads_every_module_and_every_shell_call(taken: census.Census) -> None:
    """The walked-files control: the roots hold every module, and every module that
    calls a shell is an entry — except a wrapper's own definition, which passes its
    parameter straight through."""
    sources = census.source_files()
    expected = {
        rel
        for root in census.ROOTS
        for rel in (str(p.relative_to(census.APP)) for p in (census.APP / root).rglob("*.py"))
    }
    names = set(census.SHELLS) | set(taken.wrappers)
    calling = {rel for rel, text in sources.items() if any(_shell_calls(text, names))}
    defining = {
        rel
        for rel, text in sources.items()
        for name in taken.wrappers
        if re.search(rf"^\s*def {re.escape(name)}\(", text, re.MULTILINE)
    }

    assert set(taken.files) == expected
    assert len(taken.wrappers) >= 10
    assert sorted(calling - taken.entry_files - defining) == []
    assert taken.entries >= 130


def _one(body: str, *, shell: str = "SidebarPage(content, items=[])") -> census.Census:
    """The census over one synthetic module whose page returns ``shell`` around ``body``."""
    return census.take(
        {
            "ui/sample.py": f"def page(request):\n    content = {body}\n    return {shell}\n",
        }
    )


def test_control_a_padded_body_is_a_finding() -> None:
    found = _one('Div(P("hi"), cls="max-w-3xl mx-auto px-4")')

    assert [(e.function, e.modes) for e in found.side] == [("page", {"sidebar"})]


def test_control_a_body_under_custom_pads_itself() -> None:
    found = _one('Div(P("hi"), cls="px-4")', shell="BasePage(content, page_type=PageType.CUSTOM)")

    assert found.side == []
    assert [e.function for e in found.custom_side] == ["page"]


def test_control_a_box_owns_what_pads_inside_it() -> None:
    boxed = _one('Div(Div(P("hi"), cls="px-4"), cls="border rounded-lg")')
    styled = _one('Div(Div(P("hi"), cls="px-4"), style="background: red")')

    assert boxed.side == styled.side == []


def test_control_padding_passed_through_a_mapping_is_a_finding() -> None:
    found = _one('Div(P("hi"), **{"cls": "px-2 pt-2"})')

    assert len(found.side) == len(found.vertical) == 1


def test_control_a_body_from_a_wrapper_a_helper_and_an_htmx_route() -> None:
    found = census.take(
        {
            "ui/sample.py": (
                "def wrap(content, request):\n"
                "    return SidebarPage(content, items=[])\n"
                "def body(url):\n"
                '    return Div(Div(hx_get=url, hx_trigger="load", hx_swap="outerHTML"))\n'
                "def page(request):\n"
                '    return wrap(body("/frag"), request)\n'
                '@rt("/frag")\n'
                "def frag(request):\n"
                '    return Div(P("hi"), cls="py-8 px-6")\n'
            ),
        }
    )

    assert found.wrappers == {"wrap": "sidebar"}
    assert [(e.function, e.chains) for e in found.side] == [
        ("frag", {"body() > Div > HTMX /frag (outerHTML)"})
    ]


def test_control_a_renderer_bound_by_partial_and_a_url_from_the_caller() -> None:
    found = census.take(
        {
            "ui/sample.py": (
                "def shell(request, url):\n"
                "    return SidebarPage(Div(hx_get=url, hx_trigger='load'), items=[])\n"
                "def page(request):\n"
                "    return shell(request, '/frag')\n"
                "def slot(name, message):\n"
                "    return Div(P(message), id=name, cls='px-4')\n"
                "def refuse(render):\n"
                "    return render('gone')\n"
                "@rt('/frag')\n"
                "def frag(request):\n"
                "    return refuse(partial(slot, 'x'))\n"
            ),
        }
    )

    assert [e.function for e in found.side] == ["slot"]


def test_control_only_the_edges_carry_vertical_padding() -> None:
    top = _one('Div(Div(P("a"), cls="py-8"), P("b"))')
    bottom = _one('Div(P("a"), Div(P("b"), cls="pb-8"))')
    middle = _one('Div(P("a"), Div(P("b"), cls="py-8"), P("c"))')
    after_an_optional_child = _one('Div(None, P("a") if x else None, Div(P("b"), cls="pt-8"))')

    assert len(top.vertical) == len(bottom.vertical) == len(after_an_optional_child.vertical) == 1
    assert middle.vertical == []


def test_control_a_margin_at_an_edge_is_a_finding() -> None:
    top = _one('Div(Div(P("a"), cls="mt-8"), P("b"))')
    bottom = _one('Div(P("a"), Div(P("b"), cls="sm:mb-8"))')
    both = _one('Div(P("a"), cls="my-4")')
    middle = _one('Div(P("a"), Div(P("b"), cls="my-8"), P("c"))')
    aligned = _one('Div(Div(P("a"), cls="mt-auto mb-auto mb-0 -mb-2 mx-4"))')

    assert [e.classes for e in top.margins] == [("mt-8",)]
    assert [e.classes for e in bottom.margins] == [("sm:mb-8",)]
    assert [e.edges for e in both.margins] == [{"top", "bottom"}]
    assert middle.margins == aligned.margins == []


def test_control_a_box_and_a_control_at_an_edge_are_spaced_by_their_margin() -> None:
    """A margin sits outside the element's own box, so a card's, a link's or a
    paragraph's counts where its padding does not."""
    card = _one('Div(P("a"), Div(P("b"), cls="border rounded-lg p-4 mb-4"))')
    link = _one('Div(P("a"), A("b", href="/x", cls="block mb-2"))')
    text = _one('Div(Div(P("a")), P("b", cls="mb-3"))')

    assert [e.tag for e in card.margins + link.margins + text.margins] == ["Div", "A", "P"]
    assert card.vertical == []


def test_control_a_first_or_last_reset_cancels_the_margin_at_that_edge() -> None:
    """``_HUB_BLOCK_CLS`` (ui/patterns/hub.py): each block spaces the next and the
    last one takes its own margin back."""
    reset = _one('Div(P("a"), Div(P("b"), cls="border-b mb-5 last:mb-0 pb-5 last:pb-0"))')
    first = _one('Div(Div(P("a"), cls="mt-4 first:mt-0"), P("b"))')
    wrong_edge = _one('Div(Div(P("a"), cls="mt-4 last:mt-0"), P("b"))')

    assert reset.margins == reset.vertical == first.margins == []
    assert len(wrong_edge.margins) == 1


def test_control_text_at_an_edge_pads_it() -> None:
    """``P("No learning paths available yet.", cls="... py-8")`` at the bottom of the
    pathways browse body doubles the shell's bottom padding, as a block would."""
    found = _one('Div(Div(P("a")), P("none yet", cls="text-center py-8"))')

    assert [(e.tag, e.classes) for e in found.vertical] == [("P", ("py-8",))]


def test_control_a_mapping_built_up_passes_its_classes() -> None:
    """``CardGenerator.from_dataclass`` builds ``attrs = {}``, updates it from its
    ``card_attrs`` parameter and spreads it into ``Card``, whose ``cls`` it binds."""
    found = census.take(
        {
            "ui/sample.py": (
                "def card(*c, cls='', **kw):\n"
                "    return Div(*c, cls=f'border {cls}', **kw)\n"
                "def make(card_attrs=None, extra=''):\n"
                "    attrs = {}\n"
                "    if card_attrs:\n"
                "        attrs.update(card_attrs)\n"
                "    return card(P('x'), **attrs)\n"
                "def keyed(pad):\n"
                "    attrs = {'id': 'k'}\n"
                "    attrs['cls'] = pad\n"
                "    return Div(P('y'), **attrs)\n"
                "def page(request):\n"
                "    body = Div(keyed('px-4'), P('m'), make(card_attrs={'cls': 'mb-2'}))\n"
                "    return SidebarPage(body, items=[])\n"
            ),
        }
    )

    assert [(e.function, e.classes) for e in found.margins] == [("card", ("mb-2",))]
    assert [e.function for e in found.side] == ["keyed"]


def test_control_a_list_built_by_appending_is_walked_in_order() -> None:
    """EmptyState appends its icon first and its action last: the icon's margin is
    always followed, the action's always follows."""

    def built(lines: str) -> census.Census:
        return census.take(
            {
                "ui/sample.py": (
                    "def page(request):\n"
                    "    items = [P('first')]\n"
                    f"{lines}"
                    "    return SidebarPage(Div(*items), items=[])\n"
                ),
            }
        )

    followed = built("    items.append(Div(P('a'), cls='mb-4'))\n    items.append(P('b'))\n")
    last = built("    items.append(P('b'))\n    items.append(Div(P('a'), cls='mb-4'))\n")
    then_maybe = built(
        "    items.append(Div(P('a'), cls='mb-4'))\n    if x:\n        items.append(P('b'))\n"
    )
    in_front = built("    items.insert(0, Div(P('a'), cls='mt-4'))\n")

    assert followed.margins == []
    assert len(last.margins) == len(then_maybe.margins) == len(in_front.margins) == 1


def test_control_a_child_that_may_render_nothing_does_not_hold_the_edge() -> None:
    """The GradeBook's last two groups each return ``None`` when they are empty, so
    the exchange section above them can be the last thing on the page."""

    def page(after: str) -> census.Census:
        return census.take(
            {
                "ui/sample.py": (
                    "def group(rows):\n"
                    "    if not rows:\n"
                    "        return None\n"
                    "    return Div(P('g'))\n"
                    "def always(rows):\n"
                    "    return Div(P('g'))\n"
                    "def page(request):\n"
                    "    more = None\n"
                    f"    body = Div(Div(P('a'), cls='mb-8'), {after})\n"
                    "    return SidebarPage(body, items=[])\n"
                ),
            }
        )

    assert len(page("group(rows)").margins) == len(page("more").margins) == 1
    assert len(page("always(rows) if x else group(rows)").margins) == 1
    assert page("always(rows)").margins == []


def test_control_a_spread_that_is_never_empty_holds_the_edge() -> None:
    """The Obsidian sync page spreads a tuple that holds a panel on either branch."""
    found = census.take(
        {
            "ui/sample.py": (
                "def page(request):\n"
                "    if x:\n"
                "        area = (P('a'), Div(id='r'))\n"
                "    else:\n"
                "        area = (Div(P('b')),)\n"
                "    return SidebarPage(Div(Div(P('h'), cls='mb-6'), *area), items=[])\n"
                "def other(request):\n"
                "    rows = [P(r) for r in rs]\n"
                "    return SidebarPage(Div(Div(P('h'), cls='mb-4'), *rows), items=[])\n"
            ),
        }
    )

    assert [e.classes for e in found.margins] == [("mb-4",)]


def test_control_a_shared_component_is_recorded_once_per_spacing_handed_to_it() -> None:
    """``Card`` writes no margin; its callers hand it one through ``cls``. Each spacing
    is its own record, and the record's chains name the caller."""
    found = census.take(
        {
            "ui/sample.py": (
                "def card(*c, cls=''):\n"
                "    return Div(*c, cls=f'border {cls}')\n"
                "def first(request):\n"
                "    return SidebarPage(Div(P('a'), card(P('b'), cls='mb-2')), items=[])\n"
                "def second(request):\n"
                "    return SidebarPage(Div(P('a'), card(P('b'), cls='mb-8')), items=[])\n"
            ),
        }
    )

    assert sorted(e.classes for e in found.margins) == [("mb-2",), ("mb-8",)]
    assert all(e.chains == {"Div > card()"} for e in found.margins)


def test_control_an_imported_name_is_the_function_its_import_names() -> None:
    """Two modules define ``render_queue_item``; the teaching queue imports one.
    An alias (``from ui.components import Alert as _SKUELAlert``, in a module that
    defines its own ``Alert``) is the imported function, never the local one, and a
    package re-export is followed to the module that defines it."""
    found = census.take(
        {
            "ui/a/cards.py": "def row(x):\n    return Div(P(x), cls='border mb-3')\n",
            "ui/b/cards.py": "def row(x):\n    return Div(P(x), cls='border mb-2')\n",
            "ui/b/__init__.py": "from .cards import row\n",
            "ui/wrap.py": ("from ui.b import row as _inner\ndef row(x):\n    return _inner(x)\n"),
            "ui/page.py": (
                "from ui.wrap import row\n"
                "def page(request):\n"
                "    return SidebarPage(Div(P('h'), row('r')), items=[])\n"
            ),
        }
    )

    assert [(e.rel, e.classes) for e in found.margins] == [("ui/b/cards.py", ("mb-2",))]


def test_control_a_sibling_that_can_be_hidden_leaves_the_edge_to_its_neighbour() -> None:
    """The teaching student page shows one of four ``x-show`` panels at a time, so
    each is at both edges of the body; a ``hidden`` class takes an element out too."""
    tabs = _one('Div(Div(P("one", cls="py-8"), x_show="a"), Div(P("two"), **{"x-show": "b"}))')
    hidden = _one('Div(Div(P("a"), cls="mb-4"), Div(P("b"), cls="hidden lg:block"))')
    shown = _one('Div(Div(P("a"), cls="mb-4"), Div(P("b"), cls="block"))')

    assert [e.edges for e in tabs.vertical] == [{"top", "bottom"}]
    assert len(hidden.margins) == 1
    assert shown.margins == []


def test_control_a_branch_a_constant_rules_out_adds_nothing() -> None:
    """``ExploreGraphView`` insets itself only when it is not standalone; its own
    page calls it with the default ``standalone=True``."""

    def page(call: str) -> census.Census:
        return census.take(
            {
                "ui/sample.py": (
                    "def graph(standalone=True):\n"
                    "    attrs = {}\n"
                    "    if standalone:\n"
                    "        attrs['x_data'] = 'g'\n"
                    "    else:\n"
                    "        attrs['cls'] = 'px-2 pt-2'\n"
                    "    return Div(P('g'), **attrs)\n"
                    "def page(request):\n"
                    f"    return BasePage(Div({call}), request=request)\n"
                ),
            }
        )

    assert page("graph()").side == page("graph(standalone=True)").side == []
    assert len(page("graph(standalone=False)").side) == 1
    assert len(page("graph(not_known)").side) == 1


def test_control_a_bulleted_list_and_text_keep_their_own_padding() -> None:
    bullets = _one('Ul(Li("a"), cls="list-disc pl-6")')
    plain = _one('Ul(Li("a"), cls="pl-6")')
    inside_text = _one('P(Span("a", cls="px-2"))')

    assert bullets.side == inside_text.side == []
    assert len(plain.side) == 1


def test_control_a_hand_written_css_class_that_paints_is_a_box() -> None:
    """``.panel-surface`` (search.css) sets a background and a shadow."""
    assert "panel-surface" in census.CSS_BOXES
    assert _one('Div(Div(P("hi"), cls="px-4"), cls="panel-surface")').side == []


def test_control_a_css_rule_that_applies_a_box_class_is_a_box() -> None:
    """``.tree-container`` (hierarchy.css) paints through ``@apply bg-background border``;
    a rule that applies only padding, or a box only in a state, paints nothing."""
    sheet = (
        ".card { @apply bg-card rounded-lg p-4; }\n"
        ".edged { @apply border border-border; }\n"
        ".raised {\n  @apply shadow-md;\n}\n"
        ".inset { @apply p-4; }\n"
        ".lit { @apply hover:bg-muted focus:ring-2; }\n"
    )

    assert census.css_boxes([sheet]) == {"card", "edged", "raised"}
    assert {"tree-container", "indented-list"} <= census.CSS_BOXES


def test_search_paints_no_backdrop_of_its_own() -> None:
    """Search's body sits in the STANDARD shell like any page: its container neither
    tints a panel behind the page nor pushes it down below the navbar."""
    rules = re.findall(r"\.search-container\s*\{([^{}]*)\}", census.css_sheets()["search.css"])

    assert "search-container" not in census.CSS_BOXES
    assert not [r for r in rules if re.search(r"margin|min-height", r)]


def test_control_what_cannot_be_resolved_is_a_hole() -> None:
    found = _one("make_body()")

    assert found.side == []
    assert found.unresolved == {("ui/sample.py:2", "call make_body")}


# ------------------------------------------------------------- page layout


def test_the_dashboard_actions_wrap_rather_than_squeeze() -> None:
    """At 375px the two action links do not fit on one line; the row wraps them.

    Without ``flex-wrap`` the row shrinks both links until their labels break onto a
    second line, and a margin on one link (beside the row's ``gap``) widens the squeeze.
    """
    xml = to_xml(render_dashboard_content({"has_vision": True}, UserUID("user_learner")))
    row = re.search(r'<div class="([^"]*)">\s*<a [^>]*href="/lifepath/alignment"', xml)
    assert row, "the dashboard's action row was not found"
    assert {"flex", "flex-wrap"} <= set(row.group(1).split())
    links = re.findall(r'<a [^>]*href="/lifepath/(?:alignment|vision)"[^>]*>', xml)
    assert len(links) == 2
    for link in links:
        classes = re.search(r'class="([^"]*)"', link)
        assert classes and not [
            c for c in classes.group(1).split() if re.match(r"^(?:[a-z0-9]+:)*-?m[trblxyse]?-", c)
        ]


def test_the_periodic_note_editor_takes_the_full_width_below_lg() -> None:
    """Stacked (below ``lg``) the editor and navigator stretch across the column;
    side by side they align to the top. A stacked column that aligns its children
    to the start sizes the editor to its content rather than to the column."""
    created = datetime(2026, 10, 25, 8, 0, tzinfo=UTC)
    entry = UserEntry(
        uid=periodic_note_uid("daily", "user_learner", "2026-10-25"),
        user_uid="user_learner",
        title="Daily Note",
        content="",
        status=EntityStatus.ACTIVE,
        created_at=created,
        updated_at=created,
        metadata={"entry_kind": "daily", "period_key": "2026-10-25"},
    )
    row = PeriodicNotePage(entry=entry, initial_workspace="editor")
    classes = str(row.attrs["class"]).split()

    assert {"flex-col", "lg:flex-row", "items-stretch", "lg:items-start"} <= set(classes)
    assert "items-start" not in classes


def test_the_not_found_page_goes_through_the_shell() -> None:
    app, rt = fast_app(pico=False, default_hdrs=False)
    create_system_ui_routes(app, rt, None)

    page = TestClient(app).get("/404")

    assert page.status_code == 200
    assert 'id="live-region"' in page.text  # BasePage's chrome
    assert "Page Not Found" in page.text
    assert 'class="navbar' not in page.text  # no hand-built navbar
