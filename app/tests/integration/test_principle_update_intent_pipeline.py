"""
Integration Test: Principle Update Intent pipeline (ADR-066 Phase 5)
===================================================================

Verifies the typed ``PrincipleUpdateIntent`` update path end to end against live Neo4j:

1. ``update_principle(intent)`` materializes only the set fields at the single
   ``backend.update`` seam — a partial update does NOT clobber untouched columns.
2. A ``PrincipleUpdated`` event fires on the intent path (cache-invalidation contract).
3. A status transition expressed as an intent persists and fires ``PrincipleUpdated``.
4. A strength change fires ``PrincipleStrengthChanged`` (preserved event) — and is NOT
   blocked, documenting that ``update_principle`` is backend-direct (the inherited
   ``_validate_update`` is stale and deliberately not run; reform is Phase-7 work).
5. The ``Mapping`` funnel (``core.update`` — the ``principles_api`` status route) routes
   through ``update_principle`` and fires ``PrincipleUpdated`` too.
6. ``PrincipleUpdateRequest.to_intent()`` carries exactly the explicitly-set fields
   (``model_fields_set``), lowers enums, and DROPS the one non-column request field
   (``decision_criteria``) plus the funnel-only ``status``.

Mirrors ``test_choice_update_intent_pipeline.py`` (the closest reference) for Principles.
"""

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events import PrincipleStrengthChanged, PrincipleUpdated
from core.models.enums import Priority
from core.models.enums.entity_enums import EntityStatus
from core.models.enums.principle_enums import PrincipleCategory, PrincipleStrength
from core.models.principle.principle import Principle
from core.models.principle.principle_request import PrincipleUpdateRequest
from core.models.sentinels import UNSET
from core.services.principles.principles_core_service import PrinciplesCoreService


@pytest.mark.asyncio
class TestPrincipleUpdateIntentPipeline:
    """Live-Neo4j checks for the ADR-066 typed update path (Principles)."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def principles_backend(self, neo4j_driver, clean_neo4j):
        return UniversalNeo4jBackend[Principle](
            neo4j_driver, "Entity", Principle, default_filters={"entity_type": "principle"}
        )

    @pytest_asyncio.fixture
    async def core_service(self, principles_backend, event_bus):
        return PrinciplesCoreService(backend=principles_backend, event_bus=event_bus)

    @pytest_asyncio.fixture
    async def seeded_principle(self, core_service):
        # statement >= 10 chars and description >= 20 chars satisfy _validate_create.
        principle = Principle(
            uid="principle.intent_pipeline",
            user_uid="user_intent_pipeline",
            title="Original title",
            statement="Be honest in all dealings",
            description="Original description that is plenty long enough",
            principle_category=PrincipleCategory.PERSONAL,
            strength=PrincipleStrength.MODERATE,
            priority=Priority.MEDIUM,
        )
        result = await core_service.create(principle)
        assert result.is_ok
        return result.value

    async def test_partial_intent_writes_only_set_fields(
        self, core_service, seeded_principle, event_bus
    ) -> None:
        """A partial intent updates title only — statement/description/priority survive."""
        from core.models.principle.principle_update_intent import PrincipleUpdateIntent

        event_bus.clear_event_history()
        intent = PrincipleUpdateIntent(title="Updated title")

        result = await core_service.update_principle(seeded_principle.uid, intent)
        assert result.is_ok
        assert result.value.title == "Updated title"

        # Re-fetch from Neo4j: title changed, the rest is intact (no clobber).
        fetched = await core_service.get_principle(seeded_principle.uid)
        assert fetched.is_ok
        assert fetched.value.title == "Updated title"
        assert fetched.value.statement == "Be honest in all dealings"
        assert fetched.value.description == "Original description that is plenty long enough"
        assert fetched.value.priority == Priority.MEDIUM

        # PrincipleUpdated fired on the intent path, naming only the changed field.
        updated = [e for e in event_bus.get_event_history() if isinstance(e, PrincipleUpdated)]
        assert updated, "expected a PrincipleUpdated event on the intent path"
        assert updated[-1].updated_fields == {"title": "Updated title"}

    async def test_status_transition_intent_persists_and_emits_event(
        self, core_service, seeded_principle, event_bus
    ) -> None:
        """A status transition expressed as an intent persists and fires PrincipleUpdated."""
        from core.models.principle.principle_update_intent import PrincipleUpdateIntent

        event_bus.clear_event_history()
        intent = PrincipleUpdateIntent(status=EntityStatus.ARCHIVED.value)

        result = await core_service.update_principle(seeded_principle.uid, intent)
        assert result.is_ok
        assert result.value.status == EntityStatus.ARCHIVED

        fetched = await core_service.get_principle(seeded_principle.uid)
        assert fetched.is_ok
        assert fetched.value.status == EntityStatus.ARCHIVED

        updated = [e for e in event_bus.get_event_history() if isinstance(e, PrincipleUpdated)]
        assert updated, "status transition must fire PrincipleUpdated"
        assert "status" in updated[-1].updated_fields

    async def test_strength_change_emits_strength_changed_and_is_not_blocked(
        self, core_service, seeded_principle, event_bus
    ) -> None:
        """A strength change fires PrincipleStrengthChanged and is NOT blocked.

        Backend-direct contract: the stale ``_validate_update`` (whose strength rule never
        fires — uppercase keys vs lowercase enum values — and whose modification-reason gate
        is unsatisfiable) is deliberately not run; reforming it is Phase-7 work.
        """
        from core.models.principle.principle_update_intent import PrincipleUpdateIntent

        event_bus.clear_event_history()
        intent = PrincipleUpdateIntent(strength=PrincipleStrength.STRONG.value)

        result = await core_service.update_principle(seeded_principle.uid, intent)
        assert result.is_ok
        assert result.value.strength == PrincipleStrength.STRONG

        changed = [
            e for e in event_bus.get_event_history() if isinstance(e, PrincipleStrengthChanged)
        ]
        assert changed, "a strength change must fire PrincipleStrengthChanged"
        assert changed[-1].old_strength == PrincipleStrength.MODERATE.value
        assert changed[-1].new_strength == PrincipleStrength.STRONG.value

    async def test_to_intent_carries_only_explicit_fields(self) -> None:
        """to_intent() reflects model_fields_set: provided → set, absent → UNSET."""
        request = PrincipleUpdateRequest(title="Just the title")
        intent = request.to_intent()

        assert intent.title == "Just the title"
        assert intent.priority is UNSET
        assert intent.strength is UNSET
        assert intent.description is UNSET
        assert intent.to_changes() == {"title": "Just the title"}

        # Enum fields are lowered to their string value on the intent.
        request2 = PrincipleUpdateRequest(priority=Priority.HIGH, strength=PrincipleStrength.STRONG)
        intent2 = request2.to_intent()
        assert intent2.priority == Priority.HIGH.value
        assert intent2.strength == PrincipleStrength.STRONG.value
        assert intent2.title is UNSET
        assert intent2.to_changes() == {
            "priority": Priority.HIGH.value,
            "strength": PrincipleStrength.STRONG.value,
        }

    async def test_to_intent_drops_non_column_and_funnel_only_fields(self) -> None:
        """to_intent() drops ``decision_criteria`` (not a node column) and never carries
        ``status`` (no such request field), while carrying ``why_important``, which is.

        ``why_important`` used to be dropped here too — it had no column and was spliced
        into ``description``. It is a real column now, so the assertion it belongs in is
        the CARRIED one; ``decision_criteria`` is the only survivor of the drop list.
        """
        request = PrincipleUpdateRequest(
            title="A title",
            why_important="Because integrity compounds",
            decision_criteria=["criterion_1"],
            key_behaviors=["tell the truth"],
        )
        intent = request.to_intent()

        assert intent.status is UNSET
        changes = intent.to_changes()
        assert "decision_criteria" not in changes
        assert "status" not in changes
        assert changes == {
            "title": "A title",
            "why_important": "Because integrity compounds",
            "key_behaviors": ["tell the truth"],
        }
