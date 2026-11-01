"""Every prompt the eight domain AI services send is a committed template.

``BaseAIService._generate_insight`` takes a template id (``AIPromptId``), never a
prompt string, so mypy refuses an inline prompt at the family's one door. This
file holds what the type cannot see, read statically from the eight service
modules, so a typo fails without a run:

- each id a builder passes is a committed template whose placeholder set is
  exactly the ``fields`` keys the call gives (``str.format`` raises on a missing
  key, but drops an extra one silently);
- each id is used by one builder, and ``AIPromptId`` lists exactly those ids;
- each routed builder's id is its route's ``AIRouteSpec`` name;
- every ``{domain}_ai_*`` template is either rendered by a builder or one of
  ``explain_step``'s level fragments.

The service modules are found through ``AI_SERVICE_CLASSES``, the registry the
AI routes resolve against.
"""

from __future__ import annotations

import ast
import inspect
import string
import typing
from pathlib import Path

import pytest

from adapters.inbound.ai_routes import AI_ROUTE_SPECS, AI_SERVICE_CLASSES
from core.services.base_ai_service import AIPromptId
from core.services.ps.ps_ai_service import EXPLAIN_LEVEL_TEMPLATES

TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "core" / "prompts" / "templates"

#: The builders with no route, and the template each renders.
UNROUTED = {
    "PsAIService.suggest_step_applications": "ps_ai_applications",
    "PsAIService.suggest_learning_sequence": "ps_ai_learning_sequence",
}


def _placeholders(template_id: str) -> set[str]:
    content = (TEMPLATES_DIR / f"{template_id}.md").read_text(encoding="utf-8")
    return {name for _, name, _, _ in string.Formatter().parse(content) if name is not None}


def _builder_calls() -> tuple[dict[str, tuple[str, set[str]]], list[str]]:
    """Every ``_generate_insight`` call, as ``{Class.method: (template id, fields keys)}``.

    A call this file cannot read (an id or ``fields`` that is not a literal) is
    returned as a problem rather than raised, so it fails one test instead of
    the collection of the whole session.
    """
    calls: dict[str, tuple[str, set[str]]] = {}
    problems: list[str] = []
    for domain, service_class in AI_SERVICE_CLASSES.items():
        source = Path(inspect.getfile(service_class)).read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            for call in ast.walk(node):
                if not (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "_generate_insight"
                ):
                    continue
                key = f"{service_class.__name__}.{node.name}"
                first = call.args[0] if call.args else None
                if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                    problems.append(f"{key}: the template id is not a string literal")
                    continue
                fields: set[str] = set()
                for keyword in call.keywords:
                    if keyword.arg != "fields":
                        continue
                    keys = keyword.value.keys if isinstance(keyword.value, ast.Dict) else [None]
                    literal = [k.value for k in keys if isinstance(k, ast.Constant)]
                    if len(literal) != len(keys):
                        problems.append(f"{key}: `fields` is not a dict literal with literal keys")
                    fields = {str(name) for name in literal}
                if not first.value.startswith(f"{domain}_ai_"):
                    problems.append(f"{key}: {first.value!r} is not named {domain}_ai_*")
                if key in calls:
                    problems.append(f"{key}: calls _generate_insight twice")
                calls[key] = (first.value, fields)
    return calls, problems


BUILDER_CALLS, SCAN_PROBLEMS = _builder_calls()


def test_every_call_names_a_literal_template_and_literal_fields() -> None:
    assert SCAN_PROBLEMS == []


def test_the_scan_finds_every_builder() -> None:
    """28 prompt methods across the eight services — an empty scan would pass everything."""
    assert len(BUILDER_CALLS) == 28
    assert {key.split(".")[0] for key in BUILDER_CALLS} == {
        service_class.__name__ for service_class in AI_SERVICE_CLASSES.values()
    }


@pytest.mark.parametrize("builder", sorted(BUILDER_CALLS))
def test_each_template_is_committed_with_exactly_the_fields_given(builder: str) -> None:
    template_id, fields = BUILDER_CALLS[builder]

    assert (TEMPLATES_DIR / f"{template_id}.md").is_file(), f"no template {template_id!r}"
    assert _placeholders(template_id) == fields


def test_each_template_has_one_builder_and_the_id_type_lists_exactly_them() -> None:
    ids = [template_id for template_id, _ in BUILDER_CALLS.values()]

    assert len(ids) == len(set(ids))
    assert set(ids) == set(typing.get_args(AIPromptId))


def test_a_routed_builders_template_is_named_for_its_route() -> None:
    routes = {
        f"{AI_SERVICE_CLASSES[spec.domain_attr].__name__}.{spec.method_name}": spec.func_name
        for spec in AI_ROUTE_SPECS
    }
    expected = {builder: routes.get(builder, UNROUTED.get(builder)) for builder in BUILDER_CALLS}

    assert {builder: template_id for builder, (template_id, _) in BUILDER_CALLS.items()} == (
        expected
    )
    assert set(UNROUTED) <= set(BUILDER_CALLS)
    assert not set(UNROUTED) & set(routes), "a route now serves an UNROUTED builder"


def test_the_explain_level_fragments_are_committed_and_take_no_fields() -> None:
    for template_id in EXPLAIN_LEVEL_TEMPLATES.values():
        assert (TEMPLATES_DIR / f"{template_id}.md").is_file(), f"no template {template_id!r}"
        assert _placeholders(template_id) == set()
    assert "guidance" in _placeholders("ps_ai_explain")


def test_every_domain_ai_template_is_rendered() -> None:
    prefixes = tuple(f"{domain}_ai_" for domain in AI_SERVICE_CLASSES)
    committed = {path.stem for path in TEMPLATES_DIR.glob("*.md") if path.stem.startswith(prefixes)}

    rendered = set(typing.get_args(AIPromptId)) | set(EXPLAIN_LEVEL_TEMPLATES.values())

    assert committed == rendered
