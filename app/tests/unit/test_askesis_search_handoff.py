"""Search → Askesis "Ask" handoff (PR3 of the merged Find/Ask arc).

The /search "Ask" button navigates to /askesis?question=&nous=. On that page the
composer must be prefilled, the scope seeded INLINE into x-data (never from a
window global — the settle-phase race would drop it), and the first turn must
auto-run via HTMX's native ``load`` trigger. These are pure-render assertions;
the live Alpine/HTMX behavior is covered by the runtime smoke.
"""

from __future__ import annotations

from fasthtml.common import to_xml

from ui.askesis.chat import render_askesis_shell
from ui.search.components import _render_search_input


def test_handoff_seeds_scope_prefills_question_and_auto_runs() -> None:
    xml = to_xml(
        render_askesis_shell(
            initial_question="what is breath awareness",
            initial_nous="self-awareness",
        )
    )

    # Scope seeded inline into x-data (not from a window global).
    assert '"self-awareness"' in xml
    assert 'selectedNous: "self-awareness"' in xml
    # Question prefilled into the composer textarea.
    assert "what is breath awareness" in xml
    # Hidden nous field carries a server-side value so the first (load) submit
    # is scoped even if HTMX fires before Alpine applies :value.
    assert 'name="nous"' in xml
    assert 'value="self-awareness"' in xml
    # Native HTMX auto-run: load fires once, submit preserved for later messages.
    assert "load, submit" in xml


def test_no_handoff_is_the_plain_composer() -> None:
    xml = to_xml(render_askesis_shell())

    # Empty scope, no auto-run trigger, no server-side nous value.
    assert 'selectedNous: ""' in xml
    assert "load, submit" not in xml


def test_ask_button_gated_to_full_tier() -> None:
    enabled = _render_search_input(ask_enabled=True)
    assert "askHref()" in enabled
    assert ">Ask<" in enabled or "<span>Ask</span>" in enabled

    disabled = _render_search_input(ask_enabled=False)
    assert "askHref()" not in disabled
