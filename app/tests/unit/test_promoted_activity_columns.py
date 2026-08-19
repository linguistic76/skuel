"""
Unit Tests: two promoted Activity columns — Principle.why_important, Choice.decision_context
=============================================================================================

Both fields were named in a live surface before they were fields. ``why_important``
was collected by the Principle create/edit form and spliced into ``description``
behind a marker constant; ``decision_context`` was named by ``MODEL_ARCHITECTURE.md``
and by the CHOICE embedding field map, and existed nowhere else. Promoting both to
real columns is what these tests pin — specifically the three seams a
string-splice or a phantom would have hidden in:

  1. the frozen dataclass carries the value (nothing to unpack from a sibling field)
  2. the request → typed update intent (ADR-066) carries it, and only when SET
  3. the DTO round-trips it through the persistence shape

See: docs/architecture/MODEL_ARCHITECTURE.md, ADR-066.
"""

from __future__ import annotations

from core.models.choice.choice import Choice
from core.models.choice.choice_dto import ChoiceDTO
from core.models.choice.choice_request import ChoiceUpdateRequest
from core.models.principle.principle import Principle
from core.models.principle.principle_dto import PrincipleDTO
from core.models.principle.principle_request import PrincipleUpdateRequest
from core.models.sentinels import UNSET


class TestPrincipleWhyImportantIsARealColumn:
    def test_model_carries_it_alongside_description(self) -> None:
        """The splice is gone: two fields, two values, neither derived from the other."""
        principle = Principle(
            uid="principle_x",
            user_uid="u",
            title="Observe first",
            description="Understanding comes before change.",
            why_important="Plans built on shallow understanding do not stick.",
        )

        assert principle.why_important == "Plans built on shallow understanding do not stick."
        assert principle.description == "Understanding comes before change."

    def test_update_request_carries_it_into_the_intent(self) -> None:
        intent = PrincipleUpdateRequest(why_important="It is what makes the rest work").to_intent()

        assert intent.why_important == "It is what makes the rest work"
        # Untouched fields stay UNSET — a partial patch, not a full overwrite.
        assert intent.description is UNSET

    def test_an_unset_why_important_is_not_written(self) -> None:
        """Absent ≠ cleared: only explicitly-set fields reach ``to_changes()``."""
        intent = PrincipleUpdateRequest(title="Observe first").to_intent()

        assert intent.why_important is UNSET
        assert "why_important" not in intent.to_changes()

    def test_an_explicit_none_clears_it(self) -> None:
        intent = PrincipleUpdateRequest(why_important=None).to_intent()

        assert intent.to_changes()["why_important"] is None

    def test_dto_round_trip(self) -> None:
        """The persistence shape carries it, so a vault-authored value is finally read.

        Vault principles already carried a real ``why_important`` node property —
        ingestion writes frontmatter keys verbatim — which the model could not see.
        """
        dto = PrincipleDTO.from_dict(
            {
                "uid": "principle_x",
                "user_uid": "u",
                "title": "Observe first",
                "entity_type": "principle",
                "why_important": "Plans built on shallow understanding do not stick.",
            }
        )

        assert dto.why_important == "Plans built on shallow understanding do not stick."
        assert dto.to_dict()["why_important"] == (
            "Plans built on shallow understanding do not stick."
        )
        assert (
            Principle.from_dto(dto).why_important
            == "Plans built on shallow understanding do not stick."
        )

    def test_dto_update_from_accepts_it(self) -> None:
        """It is on the DTO's allowed_fields, so an update patch is not silently dropped."""
        dto = PrincipleDTO.create_principle(user_uid="u", title="Observe first")
        dto.update_from({"why_important": "Because the plans keep failing"})

        assert dto.why_important == "Because the plans keep failing"


class TestChoiceDecisionContextIsARealColumn:
    def test_it_is_distinct_from_decision_rationale(self) -> None:
        """Circumstance vs reasoning — the distinction the field was added to carry.

        ``decision_context`` is what forces the choice and is authored up front;
        ``decision_rationale`` justifies the option finally selected and is written
        by ``make_decision``. Collapsing them would lose the un-chosen alternatives'
        context the moment a decision is recorded.
        """
        choice = Choice(
            uid="choice_x",
            user_uid="u",
            title="Pick a graph host",
            decision_context="The sandbox instance keeps pausing between sessions.",
            decision_rationale="Aura Free covers the corpus and costs nothing.",
        )

        assert choice.decision_context == "The sandbox instance keeps pausing between sessions."
        assert choice.decision_rationale == "Aura Free covers the corpus and costs nothing."

    def test_update_request_carries_it_into_the_intent(self) -> None:
        intent = ChoiceUpdateRequest(decision_context="The deadline moved up").to_intent()

        assert intent.decision_context == "The deadline moved up"
        assert intent.title is UNSET

    def test_an_unset_decision_context_is_not_written(self) -> None:
        intent = ChoiceUpdateRequest(title="Pick a graph host").to_intent()

        assert intent.decision_context is UNSET
        assert "decision_context" not in intent.to_changes()

    def test_dto_round_trip(self) -> None:
        dto = ChoiceDTO.from_dict(
            {
                "uid": "choice_x",
                "user_uid": "u",
                "title": "Pick a graph host",
                "entity_type": "choice",
                "decision_context": "The sandbox instance keeps pausing.",
            }
        )

        assert dto.decision_context == "The sandbox instance keeps pausing."
        assert dto.to_dict()["decision_context"] == "The sandbox instance keeps pausing."
        assert Choice.from_dto(dto).decision_context == "The sandbox instance keeps pausing."

    def test_dto_update_from_accepts_it(self) -> None:
        dto = ChoiceDTO.create_choice(user_uid="u", title="Pick a graph host")
        dto.update_from({"decision_context": "The sandbox keeps pausing"})

        assert dto.decision_context == "The sandbox keeps pausing"
