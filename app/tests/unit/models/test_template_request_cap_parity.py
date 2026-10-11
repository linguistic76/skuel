"""An Activity template holds no text its spawned instance's request model would refuse.

A PathStep engagement spawns each Activity from its template by copying every
same-named field verbatim (``_spawn_orchestrator._copy_through``), past the
instance's request model. A template text longer than the instance's cap makes
the spawned Task, Goal or Habit unsaveable through the edit form, which re-sends
the field. So each template request model caps a copied text field at the
instance's cap.

The pairs are derived from the models: a new text field on either side is
checked on the day it is written.
"""

from __future__ import annotations

import importlib

import pytest
from pydantic import BaseModel, ValidationError

DOMAINS = ("task", "goal", "habit", "event", "choice", "principle")
_TEXT = {"<class 'str'>", "str | None"}


def _models(domain: str) -> tuple[type[BaseModel], type[BaseModel], type[BaseModel]]:
    """(instance create request, template create request, template update request)."""
    name = domain.capitalize()
    instance = importlib.import_module(f"core.models.{domain}.{domain}_request")
    template = importlib.import_module(f"core.models.templates.{domain}_template_request")
    return (
        getattr(instance, f"{name}CreateRequest"),
        getattr(template, f"{name}TemplateCreateRequest"),
        getattr(template, f"{name}TemplateUpdateRequest"),
    )


def _cap(model: type[BaseModel], field_name: str) -> int | None:
    for constraint in model.model_fields[field_name].metadata:
        limit = getattr(constraint, "max_length", None)
        if limit is not None:
            return int(limit)
    return None


def _capped_copied_fields(domain: str) -> list[tuple[str, int]]:
    """Every text field the template and instance share, with the instance's cap."""
    instance, template_create, template_update = _models(domain)
    template_fields = set(template_create.model_fields) | set(template_update.model_fields)
    pairs = []
    for name, field in instance.model_fields.items():
        cap = _cap(instance, name)
        if name in template_fields and str(field.annotation) in _TEXT and cap is not None:
            pairs.append((name, cap))
    return pairs


CASES = [
    pytest.param(domain, name, cap, id=f"{domain}.{name}")
    for domain in DOMAINS
    for name, cap in _capped_copied_fields(domain)
]


def test_the_derivation_finds_the_fields_it_guards() -> None:
    """An empty derivation would pass every case below."""
    guarded = {(case.values[0], case.values[1]) for case in CASES}
    assert ("task", "description") in guarded
    assert ("task", "project") in guarded
    assert ("event", "meeting_url") in guarded
    assert ("principle", "title") in guarded


@pytest.mark.parametrize(("domain", "field_name", "instance_cap"), CASES)
def test_template_caps_a_copied_field_at_the_instance_cap(
    domain: str, field_name: str, instance_cap: int
) -> None:
    _, template_create, template_update = _models(domain)
    for model in (template_create, template_update):
        if field_name in model.model_fields:
            assert _cap(model, field_name) == instance_cap, model.__name__


@pytest.mark.parametrize("domain", DOMAINS)
def test_an_over_length_template_description_is_refused(domain: str) -> None:
    """The 4xx at the model: one character past the instance's cap is a ValidationError."""
    instance, template_create, template_update = _models(domain)
    cap = _cap(instance, "description")
    assert cap is not None

    template_create(title="A template", description="x" * cap)
    template_update(description="x" * cap)
    with pytest.raises(ValidationError, match="description"):
        template_create(title="A template", description="x" * (cap + 1))
    with pytest.raises(ValidationError, match="description"):
        template_update(description="x" * (cap + 1))
