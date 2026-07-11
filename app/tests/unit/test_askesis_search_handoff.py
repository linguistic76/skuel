"""Search → Askesis "Ask" handoff (PR3 of the merged Find/Ask arc).

The /search "Ask" button navigates to /askesis?question=&nous=. On that page the
composer must be prefilled and the scope seeded INLINE into x-data (never from a
window global — the settle-phase race would drop it). It PREFILLS ONLY — it must
NOT auto-submit, so a crafted GET can't run a prompt in the session (Kody #545).
These are pure-render assertions; live Alpine behavior is covered by runtime smoke.
"""

from __future__ import annotations

from fasthtml.common import to_xml

from ui.askesis.chat import render_askesis_shell
from ui.search.components import _render_search_input


def test_handoff_seeds_scope_and_prefills_question_without_auto_submit() -> None:
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
    # Hidden nous field is Alpine-bound to selectedNous (the single source of
    # truth). NO server-side `value` that reset() could later restore stale and
    # silently re-scope a message after the chip is cleared (Codex #545 P2).
    assert 'name="nous"' in xml
    assert ':value="selectedNous"' in xml
    assert 'value="self-awareness"' not in xml
    # SECURITY (Kody #545): prefill only — NO load trigger, so a crafted GET
    # /askesis?question=... can never auto-submit a prompt in the session.
    assert "load, submit" not in xml
    assert "load" not in _hx_trigger_values(xml)


def test_no_handoff_is_the_plain_composer() -> None:
    xml = to_xml(render_askesis_shell())

    # Empty scope, no auto-run trigger, no server-side nous value.
    assert 'selectedNous: ""' in xml
    assert "load, submit" not in xml


def _hx_trigger_values(xml: str) -> str:
    """Concatenate any hx-trigger attribute values found in the rendered XML."""
    import re

    return " ".join(re.findall(r'hx-trigger="([^"]*)"', xml))


def test_ask_button_gated_to_full_tier() -> None:
    enabled = to_xml(_render_search_input(ask_enabled=True))
    assert "askHref()" in enabled
    assert ">Ask<" in enabled or "<span>Ask</span>" in enabled

    disabled = to_xml(_render_search_input(ask_enabled=False))
    assert "askHref()" not in disabled
