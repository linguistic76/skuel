"""The exercise editor renders the stored exercise and posts to the registered doors.

The Domain select is the sharp edge: ``Entity.domain`` always holds a value, so the
select never offers a blank (a blank would clear the stored property on save); the
default ``Domain.KNOWLEDGE`` is an option like any other, and a stored domain the list
does not offer is still selectable, or a save that touches unrelated fields would
change it.
"""

from __future__ import annotations

import re

from fasthtml.common import to_xml

from core.models.enums import EntityType
from core.models.enums.entity_enums import Domain
from core.models.enums.user_entry_enums import ExerciseScope
from core.models.exercises.exercise import Exercise
from ui.exercises.editor import EDITOR_DOMAINS, EDITOR_MODELS, render_exercise_editor


def _exercise(domain: Domain, model: str = "claude-sonnet-4-6") -> Exercise:
    return Exercise(
        uid="ex_abc",
        title="Daily Reflection",
        entity_type=EntityType.EXERCISE,
        instructions="Ask me one clarifying question.",
        scope=ExerciseScope.PERSONAL,
        owner_uid="user_x",
        domain=domain,
        model=model,
    )


def _select_options(html: str, name: str) -> list[tuple[str, bool]]:
    """``(value, selected)`` per option of the named select."""
    select = re.search(rf'<select name="{name}".*?</select>', html, re.DOTALL)
    assert select is not None
    return [
        (value, "selected" in attrs)
        for value, attrs in re.findall(r'<option value="([^"]*)"([^>]*)>', select.group(0))
    ]


def _domain_options(html: str) -> list[tuple[str, bool]]:
    return _select_options(html, "domain")


def test_create_form_posts_to_the_create_door() -> None:
    html = to_xml(render_exercise_editor(mode="create"))
    assert 'hx-post="/api/exercises/create"' in html
    assert 'hx-swap="none"' in html


def test_edit_form_posts_to_the_update_door_with_the_uid() -> None:
    html = to_xml(render_exercise_editor(exercise=_exercise(Domain.HEALTH), mode="edit"))
    assert 'hx-post="/api/exercises/update?uid=ex_abc"' in html


def test_the_select_never_offers_a_blank() -> None:
    for html in (
        to_xml(render_exercise_editor(mode="create")),
        to_xml(render_exercise_editor(exercise=_exercise(Domain.KNOWLEDGE), mode="edit")),
    ):
        options = _domain_options(html)
        assert "" not in [v for v, _ in options]
        assert [v for v, selected in options if selected] == [Domain.KNOWLEDGE.value]
        assert [v for v, _ in options] == [d.value for _label, d in EDITOR_DOMAINS]


def test_an_offered_domain_is_preselected() -> None:
    options = _domain_options(
        to_xml(render_exercise_editor(exercise=_exercise(Domain.HEALTH), mode="edit"))
    )
    assert [v for v, selected in options if selected] == ["health"]


def test_a_stored_domain_the_list_does_not_offer_is_kept_and_selected() -> None:
    options = _domain_options(
        to_xml(render_exercise_editor(exercise=_exercise(Domain.TECH), mode="edit"))
    )
    assert [v for v, selected in options if selected] == ["tech"]
    assert options[-1] == ("tech", True)


def test_every_offered_domain_is_a_domain_member() -> None:
    """The request model rejects anything else — the list can never offer a 400."""
    assert all(isinstance(d, Domain) for _label, d in EDITOR_DOMAINS)


def test_a_stored_model_the_list_does_not_offer_is_kept_and_selected() -> None:
    html = to_xml(
        render_exercise_editor(exercise=_exercise(Domain.HEALTH, "gpt-4-turbo"), mode="edit")
    )
    options = _select_options(html, "model")
    assert [v for v, selected in options if selected] == ["gpt-4-turbo"]
    assert options[-1] == ("gpt-4-turbo", True)


def test_the_create_form_preselects_the_first_model() -> None:
    options = _select_options(to_xml(render_exercise_editor(mode="create")), "model")
    assert [v for v, selected in options if selected] == [EDITOR_MODELS[0][1]]
