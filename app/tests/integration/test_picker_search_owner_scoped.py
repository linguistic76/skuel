"""
Integration Test: Entity-picker search for Event / Choice / Principle
=====================================================================

The "does it actually work" bar for extending the entity picker to the
Event, Choice, and Principle targets. Drives the REAL
``GET /api/picker/search`` handler (registered against the real activity
facades) against a live Neo4j testcontainer.

Verifies for each new target type:
1. Empty ``q`` → ``list_recent_for_user`` (OWNS-edge traversal) returns the
   user's seeded entity as a selectable ``<li>`` option.
2. Non-empty ``q`` → ``search_for_user`` (user_uid-property scope) returns
   the matching seeded entity.
3. Owner scoping: an entity owned by a DIFFERENT user never leaks into the
   requesting user's picker results.

Seeding goes through each domain's backend ``create()`` (auto-creates the
``(User)-[:OWNS]->(entity)`` edge), so both picker paths — edge traversal and
property scope — are exercised end to end.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fasthtml.common import to_xml

from core.models.choice.choice import Choice
from core.models.enums import EntityStatus
from core.models.enums.principle_enums import PrincipleCategory
from core.models.event.event import Event
from core.models.principle.principle import Principle

# The picker route always speaks to the authenticated owner; use a user that
# ``ensure_test_users`` (via the clean_neo4j fixture) creates and preserves so
# the auto-created OWNS edge has a User node to attach to.
OWNER = "user_test"
OTHER = "user_test_123"


def _make_request(user_uid: str) -> Any:
    """Minimal request-like object the auth helper accepts (mirrors unit test)."""
    return SimpleNamespace(
        session={"user_uid": user_uid},
        url=SimpleNamespace(path="/api/picker/search"),
        query_params={},
    )


def _register_handler(services: Any) -> Any:
    """Register the real picker route and return the handler callable."""
    from adapters.inbound.picker_routes import create_picker_routes

    registered: dict[str, Any] = {}

    def rt_collector(path: str, *_a: Any, **_kw: Any) -> Any:
        def decorator(fn: Any) -> Any:
            registered[path] = fn
            return fn

        return decorator

    create_picker_routes(MagicMock(), rt_collector, services)
    return registered["/api/picker/search"]


def _picker_services(services: Any) -> Any:
    """Expose the six activity facades the picker routes over.

    The integration ``services`` fixture supplies real Event/Choice/Principle
    facades but no ``habits`` attribute; ``_resolve_search_service`` builds its
    lookup dict eagerly, so ``habits`` must merely be accessible (never read for
    these three types). ``None`` is a valid, unused placeholder.
    """
    return SimpleNamespace(
        tasks=services.tasks,
        goals=services.goals,
        habits=None,
        events=services.events,
        choices=services.choices,
        principles=services.principles,
    )


@pytest.fixture
def handler(services: Any) -> Any:
    return _register_handler(_picker_services(services))


@pytest.mark.asyncio
class TestPickerSearchEventChoicePrinciple:
    """Owner-scoped picker search over the three newly-supported targets."""

    async def test_event_picker_lists_and_searches(
        self, handler: Any, services: Any, clean_neo4j: Any
    ) -> None:
        owned = Event(
            uid="event.picker_seed",
            user_uid=OWNER,
            title="Quarterly Planning Summit",
            description="Owned by the requesting user",
            event_date=date.today(),
            status=EntityStatus.SCHEDULED,
        )
        foreign = Event(
            uid="event.picker_foreign",
            user_uid=OTHER,
            title="Quarterly Someone Else Summit",
            description="Owned by a different user",
            event_date=date.today(),
            status=EntityStatus.SCHEDULED,
        )
        assert (await services.events.backend.create(owned)).is_ok
        assert (await services.events.backend.create(foreign)).is_ok

        # Empty q → list_recent_for_user (OWNS-edge traversal).
        recent = to_xml(await handler(_make_request(OWNER), type="event", q=""))
        assert 'data-uid="event.picker_seed"' in recent
        assert "Quarterly Planning Summit" in recent
        assert "event.picker_foreign" not in recent  # owner scoping

        # Non-empty q → search_for_user (user_uid-property scope).
        found = to_xml(await handler(_make_request(OWNER), type="event", q="Planning Summit"))
        assert 'data-uid="event.picker_seed"' in found
        assert "event.picker_foreign" not in found

    async def test_choice_picker_lists_and_searches(
        self, handler: Any, services: Any, clean_neo4j: Any
    ) -> None:
        owned = Choice(
            uid="choice.picker_seed",
            user_uid=OWNER,
            title="Pick a Framework",
            description="Owned by the requesting user",
            status=EntityStatus.DRAFT,
        )
        foreign = Choice(
            uid="choice.picker_foreign",
            user_uid=OTHER,
            title="Pick a Framework Elsewhere",
            description="Owned by a different user",
            status=EntityStatus.DRAFT,
        )
        assert (await services.choices.backend.create(owned)).is_ok
        assert (await services.choices.backend.create(foreign)).is_ok

        recent = to_xml(await handler(_make_request(OWNER), type="choice", q=""))
        assert 'data-uid="choice.picker_seed"' in recent
        assert "Pick a Framework" in recent
        assert "choice.picker_foreign" not in recent

        found = to_xml(await handler(_make_request(OWNER), type="choice", q="Pick a Framework"))
        assert 'data-uid="choice.picker_seed"' in found
        assert "choice.picker_foreign" not in found

    async def test_principle_picker_lists_and_searches(
        self, handler: Any, services: Any, clean_neo4j: Any
    ) -> None:
        owned = Principle(
            uid="principle.picker_seed",
            user_uid=OWNER,
            title="Bias Toward Action",
            statement="Prefer shipping over deliberating",
            description="Owned by the requesting user",
            principle_category=PrincipleCategory.PERSONAL,
        )
        foreign = Principle(
            uid="principle.picker_foreign",
            user_uid=OTHER,
            title="Bias Toward Action Elsewhere",
            statement="Owned by a different user",
            description="Owned by a different user",
            principle_category=PrincipleCategory.PERSONAL,
        )
        assert (await services.principles.backend.create(owned)).is_ok
        assert (await services.principles.backend.create(foreign)).is_ok

        recent = to_xml(await handler(_make_request(OWNER), type="principle", q=""))
        assert 'data-uid="principle.picker_seed"' in recent
        assert "Bias Toward Action" in recent  # title is the displayed label
        assert "principle.picker_foreign" not in recent

        # PrinciplesSearchService searches statement/description/why_important
        # (not title), so query a word that lives in the owned principle's
        # statement; the option still renders the title as its label.
        found = to_xml(await handler(_make_request(OWNER), type="principle", q="shipping"))
        assert 'data-uid="principle.picker_seed"' in found
        assert "Bias Toward Action" in found
        assert "principle.picker_foreign" not in found
