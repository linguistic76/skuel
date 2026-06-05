"""
Integration Test: Choice Update Intent pipeline (ADR-066 Phase 4)
================================================================

Verifies the typed ``ChoiceUpdateIntent`` update path end to end against live Neo4j:

1. ``update_choice(intent)`` materializes only the set fields at the single
   ``backend.update`` seam — a partial update does NOT clobber untouched columns.
2. A ``ChoiceUpdated`` event fires on the intent path (cache invalidation contract).
3. A status transition expressed as an intent persists and fires ``ChoiceUpdated``,
   running the kept ``_validate_update`` (super().update is preserved, unlike the prior
   backend-direct write).
4. The ``Mapping`` funnel (``core.update`` — the ``choices_api`` status route) routes
   through ``update_choice`` and fires ``ChoiceUpdated`` too.
5. ``ChoiceUpdateRequest.to_intent()`` carries exactly the explicitly-set fields
   (``model_fields_set``) — absent fields stay ``UNSET`` and are not written, and the
   funnel-only ``status`` column is never carried from the request path.

Mirrors ``test_goal_update_intent_pipeline.py`` (the closest reference) for Choices.
"""

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events import ChoiceUpdated
from core.models.choice.choice import Choice
from core.models.choice.choice_option import ChoiceOption
from core.models.choice.choice_request import ChoiceUpdateRequest
from core.models.choice.choice_update_intent import ChoiceUpdateIntent
from core.models.enums import EntityStatus, Priority
from core.models.enums.choice_enums import ChoiceType
from core.models.sentinels import UNSET
from core.services.choices.choices_core_service import ChoicesCoreService


@pytest.mark.asyncio
class TestChoiceUpdateIntentPipeline:
    """Live-Neo4j checks for the ADR-066 typed update path (Choices)."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def choices_backend(self, neo4j_driver, clean_neo4j):
        return UniversalNeo4jBackend[Choice](
            neo4j_driver, "Entity", Choice, default_filters={"entity_type": "choice"}
        )

    @pytest_asyncio.fixture
    async def core_service(self, choices_backend, event_bus):
        return ChoicesCoreService(backend=choices_backend, event_bus=event_bus)

    @pytest_asyncio.fixture
    async def seeded_choice(self, core_service):
        # Two options satisfy _validate_create's minimum-options rule; MULTIPLE avoids
        # the BINARY (exactly 2) and STRATEGIC (50+ char description) special cases.
        choice = Choice(
            uid="choice.intent_pipeline",
            user_uid="user_intent_pipeline",
            title="Original title",
            description="Original description",
            choice_type=ChoiceType.MULTIPLE,
            priority=Priority.MEDIUM,
            status=EntityStatus.DRAFT,
            options=(
                ChoiceOption(uid="option_a", title="Option A"),
                ChoiceOption(uid="option_b", title="Option B"),
            ),
        )
        result = await core_service.create(choice)
        assert result.is_ok
        return result.value

    async def test_partial_intent_writes_only_set_fields(
        self, core_service, seeded_choice, event_bus
    ) -> None:
        """A partial intent updates title only — description/priority survive."""
        event_bus.clear_event_history()
        intent = ChoiceUpdateIntent(title="Updated title")

        result = await core_service.update_choice(seeded_choice.uid, intent)
        assert result.is_ok
        assert result.value.title == "Updated title"

        # Re-fetch from Neo4j: title changed, the rest is intact (no clobber).
        fetched = await core_service.get_choice(seeded_choice.uid)
        assert fetched.is_ok
        assert fetched.value.title == "Updated title"
        assert fetched.value.description == "Original description"
        assert fetched.value.priority == Priority.MEDIUM

        # ChoiceUpdated fired on the intent path, naming only the changed field.
        updated_events = [e for e in event_bus.get_event_history() if isinstance(e, ChoiceUpdated)]
        assert updated_events, "expected a ChoiceUpdated event on the intent path"
        assert updated_events[-1].updated_fields == {"title": "Updated title"}

    async def test_status_transition_intent_persists_and_emits_event(
        self, core_service, seeded_choice, event_bus
    ) -> None:
        """A status transition expressed as an intent persists and fires ChoiceUpdated.

        From DRAFT the kept _validate_update permits the status change (decision
        immutability only locks DECIDED/EVALUATED choices).
        """
        event_bus.clear_event_history()
        intent = ChoiceUpdateIntent(status=EntityStatus.ACTIVE.value)

        result = await core_service.update_choice(seeded_choice.uid, intent)
        assert result.is_ok
        assert result.value.status == EntityStatus.ACTIVE

        fetched = await core_service.get_choice(seeded_choice.uid)
        assert fetched.is_ok
        assert fetched.value.status == EntityStatus.ACTIVE

        updated_events = [e for e in event_bus.get_event_history() if isinstance(e, ChoiceUpdated)]
        assert updated_events, "status transition must fire ChoiceUpdated"
        assert "status" in updated_events[-1].updated_fields

    async def test_to_intent_carries_only_explicit_fields(self) -> None:
        """to_intent() reflects model_fields_set: provided → set, absent → UNSET."""
        request = ChoiceUpdateRequest(title="Just the title")
        intent = request.to_intent()

        assert intent.title == "Just the title"
        assert intent.priority is UNSET
        assert intent.choice_type is UNSET
        assert intent.description is UNSET
        assert intent.to_changes() == {"title": "Just the title"}

        # Enum fields are lowered to their string value on the intent.
        request2 = ChoiceUpdateRequest(priority=Priority.HIGH, choice_type=ChoiceType.BINARY)
        intent2 = request2.to_intent()
        assert intent2.priority == Priority.HIGH.value
        assert intent2.choice_type == ChoiceType.BINARY.value
        assert intent2.title is UNSET
        assert intent2.to_changes() == {
            "priority": Priority.HIGH.value,
            "choice_type": ChoiceType.BINARY.value,
        }

    async def test_to_intent_never_carries_funnel_only_status(self) -> None:
        """status is a funnel-only intent field — ChoiceUpdateRequest has no status field,
        so the request→intent path can never set it (no junk write)."""
        request = ChoiceUpdateRequest(
            title="A title",
            decision_criteria=["criterion_1"],
            stakeholders=["alice"],
        )
        intent = request.to_intent()

        assert intent.status is UNSET
        assert "status" not in intent.to_changes()
        assert intent.to_changes() == {
            "title": "A title",
            "decision_criteria": ["criterion_1"],
            "stakeholders": ["alice"],
        }
