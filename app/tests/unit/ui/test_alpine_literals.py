"""``ui.alpine`` writes data into an Alpine expression as a JavaScript literal."""

import html
import json
import re

import pytest
from fasthtml.common import Div, to_xml

from ui.alpine import alpine_call, js_literal

HOSTILE = [
    "x'});window.__pwned=1;({a:'",
    "\\'",
    'a"b',
    "</script>",
    "line1\nline2",
    "a\u2028b",
    "`${x}`",
]


@pytest.mark.parametrize("value", HOSTILE)
def test_a_string_round_trips_and_leaves_no_raw_quote_or_line_break(value: str) -> None:
    literal = js_literal(value)
    assert json.loads(literal) == value
    assert literal[0] == literal[-1] == '"'
    assert re.search(r'(?<!\\)"', literal[1:-1]) is None, "an unescaped quote ends the string"
    assert "\n" not in literal
    assert "\u2028" not in literal


def test_a_mapping_is_a_js_object_literal() -> None:
    assert js_literal({"search": "it's", "status": "all"}) == '{"search": "it\'s", "status": "all"}'


def test_none_numbers_and_booleans_are_js_literals() -> None:
    assert [js_literal(v) for v in (None, 2, 1.5, True, False)] == [
        "null",
        "2",
        "1.5",
        "true",
        "false",
    ]


def test_alpine_call_writes_each_argument_as_a_literal() -> None:
    assert alpine_call("relationshipGraph", "task.a'b", "tasks", 2) == (
        'relationshipGraph("task.a\'b", "tasks", 2)'
    )
    assert alpine_call("init") == "init()"


@pytest.mark.parametrize("name", ["", "a b", "f(1); g", "x'"])
def test_alpine_call_refuses_a_name_that_is_not_an_identifier(name: str) -> None:
    with pytest.raises(ValueError, match="identifier"):
        alpine_call(name)


def test_the_attribute_keeps_the_literal_after_html_escaping() -> None:
    """FastHTML escapes the attribute; the browser decodes it back to the literal."""
    rendered = to_xml(Div(x_data=alpine_call("f", {"q": "a'\"<&"})))
    match = re.search(r"x-data=(['\"])(.*?)\1", rendered)
    assert match is not None
    assert html.unescape(match.group(2)) == 'f({"q": "a\'\\"<&"})'
