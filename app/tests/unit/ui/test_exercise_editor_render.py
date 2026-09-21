"""The exercise editor renders the stored exercise and posts to the registered doors.

The Domain select is the sharp edge: a blank domain IS the default
(``Domain.KNOWLEDGE`` on create, cleared back to it on update), so the default reads
as "None"; any other stored domain the list does not offer must still be selectable,
or a save that touches unrelated fields would erase it.
"""

from __future__ import annotations

import re

from fasthtml.common import to_xml

from core.models.enums import EntityType
from core.models.enums.entity_enums import Domain
from core.models.enums.user_entry_enums import ExerciseScope
from core.models.exercises.exercise import Exercise
from ui.exercises.editor import EDITOR_DOMAINS, render_exercise_editor


def _exercise(domain: Domain) -> Exercise:
    return Exercise(
        uid="ex_abc",
        title="Daily Reflection",
        entity_type=EntityType.EXERCISE,
        instructions="Ask me one clarifying question.",
        scope=ExerciseScope.PERSONAL,
        owner_uid="user_x",
        domain=domain,
    )


def _domain_options(html: str) -> list[tuple[str, bool]]:
    """``(value, selected)`` per option of the domain select."""
    select = re.search(r'<select name="domain".*?</select>', html, re.DOTALL)
    assert select is not None
    return [
        (value, "selected" in attrs)
        for value, attrs in re.findall(r'<option value="([^"]*)"([^>]*)>', select.group(0))
    ]


def test_create_form_posts_to_the_create_door() -> None:
    html = to_xml(render_exercise_editor(mode="create"))
    assert 'hx-post="/api/exercises/create"' in html
    assert 'hx-swap="none"' in html


def test_edit_form_posts_to_the_update_door_with_the_uid() -> None:
    html = to_xml(render_exercise_editor(exercise=_exercise(Domain.HEALTH), mode="edit"))
    assert 'hx-post="/api/exercises/update?uid=ex_abc"' in html


def test_the_default_domain_reads_as_none() -> None:
    options = _domain_options(
        to_xml(render_exercise_editor(exercise=_exercise(Domain.KNOWLEDGE), mode="edit"))
    )
    assert options[0] == ("", True)
    assert [v for v, _ in options[1:]] == [d.value for _label, d in EDITOR_DOMAINS]


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
