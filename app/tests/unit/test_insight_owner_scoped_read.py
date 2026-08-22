"""Insight by-UID read is owner-scoped end to end (ADR-085 G6).

``InsightStore.get_insight_by_uid`` used to take no ``user_uid`` — the route
fetched any user's insight and compared owners afterwards (an ad-hoc audience
check, ADR-085 §4). The scoping now lives in the store/backend, matching the
sibling ``get_insights_for_entity`` shape: the MATCH itself carries the owner
predicate, so not-found and not-yours are indistinguishable.

Two pins, one per layer:
- the store forwards (uid, user_uid) to the backend (the CALLER assertion);
- the backend's Cypher matches on BOTH ``uid`` and ``user_uid`` — the exact
  properties the writer (``create_insight``) persists, both plain strings.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.persistence.neo4j.insight_backend import InsightBackend
from core.services.insight.insight_store import InsightStore
from core.utils.result_simplified import Result


class TestStoreForwardsTheRequestingUser:
    @pytest.mark.anyio
    async def test_get_insight_by_uid_passes_user_to_backend(self) -> None:
        backend = MagicMock()
        # Empty rows → NotFound; the pin is the call shape, not the payload.
        backend.get = AsyncMock(return_value=Result.ok([]))
        store = InsightStore(backend=backend)

        result = await store.get_insight_by_uid("insight_1", "user_owner")

        assert result.is_error  # zero rows → NotFound (not-yours looks identical)
        backend.get.assert_awaited_once_with("insight_1", "user_owner")


class TestBackendMatchIsOwnerScoped:
    @pytest.mark.anyio
    async def test_get_cypher_matches_uid_and_owner(self) -> None:
        executor = MagicMock()
        executor.execute_query = AsyncMock(return_value=Result.ok([]))
        backend = InsightBackend(executor=executor)

        await backend.get("insight_1", "user_owner")

        query, params = executor.execute_query.await_args.args
        # The owner predicate rides in the MATCH — the get_insights_for_entity
        # sibling shape — so a foreign uid matches zero rows.
        assert "{uid: $uid, user_uid: $user_uid}" in query
        assert params == {"uid": "insight_1", "user_uid": "user_owner"}
