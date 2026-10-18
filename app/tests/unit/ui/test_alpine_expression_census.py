"""Every value interpolated into an Alpine or htmx expression attribute.

An Alpine directive holds JavaScript; ``hx-vals``/``hx-headers`` hold JSON, and
``hx-vars``, ``hx-on`` and an ``hx-trigger`` filter hold JavaScript. A value
hand-quoted into one (``f"toggle('{uid}')"``) ends its string at the first
quote it carries, and the rest runs as code. Data goes in through
``ui.alpine.js_literal`` / ``alpine_call`` (or ``json.dumps``); this census
holds every other interpolation, each with the reason it cannot carry a quote.

**What is matched.** Tracked ``.py`` files under ``ui/`` and ``adapters/``. An
expression attribute is one of ``x-data``, ``x-init``, ``x-show``, ``x-text``,
``x-html``, ``x-effect``, ``x-if``, ``x-for``, ``x-model…``, ``x-on:…``,
``x-bind:…``, ``@…``, ``:…``, ``hx-vals``, ``hx-vars``, ``hx-headers``,
``hx-trigger``, ``hx-on…`` or a native ``on<event>`` handler, named by a string
key in a dict literal, by a keyword argument (``x_data=``; ``_`` reads as
``-``), or by a string subscript assignment (``attrs["x-data"] = …``). Its
value is split into holes: each ``{…}`` of an f-string, each non-literal
operand of a ``+`` chain, or the whole value when it is any other expression.
A hole passes when it is a call to ``js_literal``, ``alpine_call`` or
``json.dumps``, or a literal, or a conditional choosing between two literals.

**What is not seen.** JavaScript built somewhere else and handed in under
another name: a helper's parameter (``SelectableOptionRow(selected_expr=…)``)
or a variable the attribute names. The census lists that variable or
parameter as a hole, so whoever adds one says where its text comes from; the
text itself is checked where it is written only if it is written into an
expression attribute. A computed attribute key is not seen either.

The census counts each (file, attribute, hole) so a second copy of a listed
hole is new, and an entry whose hole is gone fails as stale.
"""

import ast
import re
import subprocess
from collections import Counter
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[3]

_EXPRESSION_ATTRIBUTE = re.compile(
    r"^(x-(data|init|show|text|html|effect|if|for|model[\w.:-]*|on:[\w.:-]+|bind:[\w.:-]+)"
    r"|@[\w.:-]+|:[\w.:-]+|hx-(vals|vars|headers|trigger|on[\w.:-]*)|on[a-z]+)$"
)
_ENCODERS = frozenset({"js_literal", "alpine_call", "json.dumps", "_json.dumps"})

ENUM = "an enum value, a module constant, or a literal every caller passes"
IDENTIFIER = "a Python identifier — a Pydantic model's field name"
CODE = "JavaScript written in the code — every caller passes constant text"
ENCODED = "built upstream with every value through json.dumps or js_literal"
NUMBER = "a number, a boolean or an ISO date"
ALLOWED = "checked against a fixed set of tokens before it gets here"
URL_QUOTED = "percent-encoded with urllib.parse.quote(safe='')"

# (file, attribute as written, hole source) -> (count, reason)
CENSUS: dict[tuple[str, str, str], tuple[int, str]] = {
    ("adapters/inbound/calendar_ui.py", "hx_vals", "on_date.isoformat()"): (1, NUMBER),
    ("adapters/inbound/calendar_ui.py", "x-on:click", "close_expr"): (1, CODE),
    ("adapters/inbound/teaching_ui.py", "hx-on::after-request", "after_request"): (1, CODE),
    ("ui/activities/_shared.py", "hx_vals", "level.value"): (1, ENUM),
    ("ui/activities/choices_views.py", "hx_vals", "new_status"): (1, ENUM),
    ("ui/activities/events_views.py", "hx_vals", "new_status"): (1, ENUM),
    ("ui/activities/habits_views.py", "hx_vals", "new_status"): (1, ENUM),
    ("ui/activities/principles_views.py", "hx_vals", "new_status"): (1, ENUM),
    ("ui/activities/tasks_views.py", "hx_vals", "new_status"): (1, ENUM),
    ("ui/admin/prereq_views.py", "x-show", "f.choice.value"): (1, ENUM),
    ("ui/admin/prereq_views.py", "x_data", "alpine_data"): (1, ENCODED),
    ("ui/askesis/chat.py", ":class", "value"): (2, ENUM),
    ("ui/askesis/chat.py", "@click", "value"): (2, ENUM),
    ("ui/askesis/chat.py", "x-show", "value"): (1, ENUM),
    ("ui/calendar/components.py", ":aria-pressed", "item_type.value"): (1, ENUM),
    ("ui/calendar/components.py", ":class", "item_type.value"): (1, ENUM),
    ("ui/calendar/components.py", "@click", "item_type.value"): (1, ENUM),
    ("ui/calendar/components.py", "@mouseenter", "item_type.value"): (1, ENUM),
    ("ui/calendar/components.py", "hx_vals", "occurrence_day.isoformat()"): (1, NUMBER),
    ("ui/calendar/components.py", "onclick", "day.isoformat()"): (1, NUMBER),
    ("ui/calendar/components.py", "onclick", "day_lens_href"): (1, NUMBER),
    ("ui/calendar/components.py", "x-on:click", "close_expr"): (2, CODE),
    ("ui/components/accordion.py", "x-data", "open_str"): (1, NUMBER),
    (
        "ui/exercises/inline_form.py",
        "@submit.prevent",
        "_submit_handler(exercise_uid, field_names)",
    ): (1, ENCODED),
    ("ui/explore/cards.py", "x-text", "len(overflow_tags)"): (1, NUMBER),
    ("ui/explore/graph.py", ":class", "filter_id"): (1, ENUM),
    ("ui/explore/graph.py", "@click", "filter_id"): (1, ENUM),
    ("ui/explore/ku_detail.py", ":aria-checked", "val"): (1, ENUM),
    ("ui/explore/ku_detail.py", ":class", "val"): (1, ENUM),
    ("ui/explore/ku_detail.py", "@click", "val"): (1, ENUM),
    ("ui/explore/ku_detail.py", "x-data", "seed_json"): (1, ENCODED),
    ("ui/explore/ku_mastery.py", ":aria-checked", "level_id"): (1, ENUM),
    ("ui/explore/ku_mastery.py", ":class", "level_id"): (1, ENUM),
    ("ui/explore/ku_mastery.py", "@click", "level_id"): (1, ENUM),
    ("ui/explore/nav.py", "x_show", "filter_name"): (1, ENUM),
    ("ui/explore/ps_detail.py", "x-data", "seed_json"): (1, ENCODED),
    ("ui/explore/reading_plan.py", "x-data", "seed_json"): (1, ENCODED),
    (
        "ui/forms/inline_form_template.py",
        "@submit.prevent",
        "_submit_handler(form_template_uid, form_schema)",
    ): (1, ENCODED),
    ("ui/groups/hub.py", ":aria-selected", "cond"): (1, ENCODED),
    ("ui/groups/hub.py", ":style", "_ACTIVE_STYLE"): (1, ENUM),
    ("ui/groups/hub.py", ":style", "_INACTIVE_STYLE"): (1, ENUM),
    ("ui/groups/hub.py", ":style", "cond"): (1, ENCODED),
    ("ui/groups/hub.py", ":tabindex", "cond"): (1, ENCODED),
    ("ui/groups/hub.py", "@keydown.arrow-left.prevent", "_FOCUS_ACTIVE_TAB"): (1, ENUM),
    ("ui/groups/hub.py", "@keydown.arrow-right.prevent", "_FOCUS_ACTIVE_TAB"): (1, ENUM),
    ("ui/groups/hub.py", "@keydown.end.prevent", "_FOCUS_ACTIVE_TAB"): (1, ENUM),
    ("ui/groups/hub.py", "@keydown.home.prevent", "_FOCUS_ACTIVE_TAB"): (1, ENUM),
    ("ui/ingestion/dashboard.py", "onclick", "onclick"): (1, CODE),
    ("ui/journals/__init__.py", "@click", "safe_href"): (1, URL_QUOTED),
    ("ui/journals/__init__.py", "x-data", "alpine_data"): (3, ENCODED),
    ("ui/journals/components.py", "x-data", "component_name"): (1, ENUM),
    ("ui/journals/forms.py", ":aria-pressed", "value"): (2, ENUM),
    ("ui/journals/forms.py", ":class", "mode_key.value"): (2, ENUM),
    ("ui/journals/forms.py", ":class", "value"): (2, ENUM),
    ("ui/journals/forms.py", ":disabled", "supported"): (1, CODE),
    ("ui/journals/forms.py", "@click", "mode_key.value"): (2, ENUM),
    ("ui/journals/forms.py", "@click", "value"): (2, ENUM),
    ("ui/journals/forms.py", "x-data", "alpine_data"): (2, ENCODED),
    ("ui/journals/forms.py", "x-show", "mode_key.value"): (4, ENUM),
    ("ui/journals/forms.py", "x-show", "supported"): (1, CODE),
    ("ui/patterns/form_generator.py", "@input", "field_name"): (1, IDENTIFIER),
    ("ui/patterns/hub.py", "hx_trigger", "trigger"): (1, ENUM),
    ("ui/patterns/modal.py", "x-on:click", "close"): (1, CODE),
    ("ui/patterns/modal.py", "x-on:keydown.escape.stop", "close"): (1, CODE),
    ("ui/patterns/modal.py", "x_effect", "show"): (1, CODE),
    ("ui/patterns/modal.py", "x_show", "show"): (1, CODE),
    ("ui/patterns/relationships/add_modal.py", "x-data", "RelationshipName.BLOCKS.value"): (
        1,
        ENUM,
    ),
    ("ui/patterns/relationships/add_modal.py", "x-show", "rel_value"): (1, ENUM),
    ("ui/patterns/relationships/blocking_chain.py", "x-init", "chain_data['chain_depth']"): (
        1,
        NUMBER,
    ),
    ("ui/patterns/sidebar.py", ":aria-selected", "item.slug"): (2, ENUM),
    ("ui/patterns/sidebar.py", ":aria-selected", "state_var"): (2, CODE),
    ("ui/patterns/sidebar.py", ":class", "collapse_translate"): (1, ENUM),
    ("ui/patterns/sidebar.py", ":class", "item.slug"): (2, ENUM),
    ("ui/patterns/sidebar.py", ":class", "state_var"): (2, CODE),
    ("ui/patterns/sidebar.py", "@click", "item.slug"): (2, ENUM),
    ("ui/patterns/sidebar.py", "@click", "state_var"): (2, CODE),
    ("ui/patterns/sidebar.py", "x-data", "alpine_state"): (1, ENCODED),
    ("ui/patterns/sidebar.py", "x-data", "collapsed_default"): (1, NUMBER),
    ("ui/patterns/sidebar.py", "x-data", "storage_key"): (2, ENUM),
    ("ui/patterns/sidebar.py", "x-data", "str(default_collapsed).lower()"): (1, NUMBER),
    ("ui/primitives.py", ":class", "active_expr"): (1, CODE),
    ("ui/primitives.py", ":class", "selected_expr"): (1, CODE),
    ("ui/primitives.py", "@click", "click_handler"): (2, CODE),
    ("ui/primitives.py", "@click", "remove_handler"): (1, CODE),
    ("ui/primitives.py", "@click", "replace_handler"): (1, CODE),
    ("ui/primitives.py", "@dragleave", "dragleave_handler"): (1, CODE),
    ("ui/primitives.py", "@dragover", "dragover_handler"): (1, CODE),
    ("ui/primitives.py", "@drop", "drop_handler"): (1, CODE),
    ("ui/primitives.py", "x-show", "selected_expr"): (1, CODE),
    ("ui/primitives.py", "x-show", "show_expr"): (2, CODE),
    ("ui/primitives.py", "x-text", "file_name_expr"): (1, CODE),
    ("ui/primitives.py", "x-text", "meta_expr"): (1, CODE),
    ("ui/search/components.py", "x-bind:disabled", "_TYPE_SELECTED"): (1, ENUM),
    ("ui/search/components.py", "x-bind:disabled", "name"): (1, ENUM),
    (
        "ui/search/components.py",
        "x-bind:title",
        "_hint_when('isKnowledgeMode', _TYPE_DISABLED_HINT)",
    ): (1, ENCODED),
    (
        "ui/search/components.py",
        "x-bind:title",
        "_hint_when(_TYPE_SELECTED, _NOUS_DISABLED_HINT)",
    ): (1, ENCODED),
    ("ui/search/components.py", "x-on:click", "fc.facet_value"): (1, ALLOWED),
    ("ui/search/components.py", "x_show", "name"): (1, ENUM),
    ("ui/settings/preferences.py", "onclick", "TIMEZONE_NOTE_ID"): (1, ENUM),
    ("ui/settings/preferences.py", "onclick", "TIMEZONE_SELECT_ID"): (1, ENUM),
    ("ui/user_entry/forms.py", "x-data", "FEEDBACK_TEACHER"): (1, ENUM),
    ("ui/user_entry/forms.py", "x-data", "str(not has_exercise).lower()"): (1, NUMBER),
    ("ui/user_entry/forms.py", "x-show", "FEEDBACK_TEACHER"): (1, ENUM),
}


def _attribute_name(raw: str) -> str:
    return raw if raw.startswith(("@", ":")) else raw.replace("_", "-")


def _is_literal(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.IfExp):
        return _is_literal(node.body) and _is_literal(node.orelse)
    return False


def _holes(value: ast.expr) -> list[ast.expr]:
    if isinstance(value, ast.JoinedStr):
        return [part.value for part in value.values if isinstance(part, ast.FormattedValue)]
    if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
        return _holes(value.left) + _holes(value.right)
    return [value]


def _passes(hole: ast.expr) -> bool:
    if _is_literal(hole):
        return True
    return isinstance(hole, ast.Call) and ast.unparse(hole.func) in _ENCODERS


def _attribute_values(tree: ast.AST) -> list[tuple[str, ast.expr]]:
    found: list[tuple[str, ast.expr]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg:
            found.append((node.arg, node.value))
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    found.append((key.value, value))
        elif isinstance(node, ast.Assign):
            found.extend(
                (target.slice.value, node.value)
                for target in node.targets
                if isinstance(target, ast.Subscript)
                and isinstance(target.slice, ast.Constant)
                and isinstance(target.slice.value, str)
            )
    return [(raw, v) for raw, v in found if _EXPRESSION_ATTRIBUTE.match(_attribute_name(raw))]


def _tracked_sources() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "ui", "adapters"],
        cwd=APP_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [path for path in out.split() if path.endswith(".py")]


def scan(sources: dict[str, str]) -> Counter[tuple[str, str, str]]:
    """Every hole that is neither encoded nor literal, counted by (file, attribute, source)."""
    holes: Counter[tuple[str, str, str]] = Counter()
    for path, text in sources.items():
        for raw, value in _attribute_values(ast.parse(text)):
            for hole in _holes(value):
                if not _passes(hole):
                    holes[(path, raw, ast.unparse(hole))] += 1
    return holes


def test_every_interpolated_expression_value_is_encoded_or_listed() -> None:
    sources = {path: (APP_ROOT / path).read_text() for path in _tracked_sources()}
    found = scan(sources)
    listed = {key: count for key, (count, _reason) in CENSUS.items()}

    new = {key: count for key, count in found.items() if listed.get(key) != count}
    stale = {key: count for key, count in listed.items() if found.get(key) != count}
    assert not new and not stale, (
        "A value interpolated into an Alpine/htmx expression attribute must be written with "
        "ui.alpine.js_literal / alpine_call, or listed in CENSUS with why it cannot carry a "
        f"quote.\n  found, not listed (or a different count): {new}\n"
        f"  listed, not found (or a different count): {stale}"
    )


def test_the_scan_sees_each_spelling() -> None:
    """The control: every way the matching model names a hole is found."""
    source = """
Div(x_data=f"c('{uid}')")
Div(**{"@click": f"go('{uid}')", ":class": "a" + uid, "x-show": shown})
attrs["hx-vals"] = f'{{"u": "{uid}"}}'
Div(onclick=f"location.href='{href}'", hx_trigger=f"expand-{uid}")
"""
    assert scan({"probe.py": source}) == Counter(
        {
            ("probe.py", "x_data", "uid"): 1,
            ("probe.py", "@click", "uid"): 1,
            ("probe.py", ":class", "uid"): 1,
            ("probe.py", "x-show", "shown"): 1,
            ("probe.py", "hx-vals", "uid"): 1,
            ("probe.py", "onclick", "href"): 1,
            ("probe.py", "hx_trigger", "uid"): 1,
        }
    )


def test_the_scan_passes_encoded_and_literal_values() -> None:
    source = """
Div(x_data=alpine_call("c", uid), hx_vals=json.dumps({"u": uid}))
Div(**{"@click": f"go({js_literal(uid)})", "x-show": "open", ":class": "a" if b else "c"})
Div(x_init="a" + js_literal(uid), id=f"row-{uid}", hx_get=f"/x/{uid}", x_ref=name)
"""
    assert scan({"probe.py": source}) == Counter()
