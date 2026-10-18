"""Values written into an Alpine or htmx expression attribute.

An Alpine directive (``x-data``, ``@click``, ``:class`` …) holds JavaScript, and
Alpine evaluates it as statements. FastHTML escapes an attribute for HTML, which
does nothing for a quote inside a JavaScript string: a value hand-quoted into the
expression (``f"toggle('{uid}')"``) ends its string at the first quote in the
value, and the rest runs as code. Every value that is data — a uid, a query
parameter, stored text — goes in as a literal built here instead.

``js_literal`` writes a value as JSON, which is a JavaScript literal for every
string, number, boolean, ``None``, list and dict; ``alpine_call`` spells a call
whose arguments are such literals. FastHTML then escapes the JSON's double quotes
for the attribute, and the browser hands Alpine the literal unchanged.

``tests/unit/ui/test_alpine_expression_census.py`` lists every other value
written straight into an expression attribute under ``ui/`` and ``adapters/``,
with the reason it cannot carry a quote.
"""

import json
from collections.abc import Mapping, Sequence

type JsValue = str | int | float | bool | Sequence[JsValue] | Mapping[str, JsValue] | None


def js_literal(value: JsValue) -> str:
    """The JavaScript literal for ``value`` — a string's quotes, backslashes,
    newlines and line separators all escaped."""
    return json.dumps(value)


def alpine_call(name: str, *args: JsValue) -> str:
    """``name(arg, …)`` with each argument written as a JavaScript literal.

    ``name`` is code — a component or method the page defines — so it must be
    an identifier; a value never goes there.
    """
    if not name.isidentifier():
        raise ValueError(f"alpine_call name must be an identifier, got {name!r}")
    return f"{name}({', '.join(js_literal(arg) for arg in args)})"
