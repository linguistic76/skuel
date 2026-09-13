"""
Every rich-context statement is served from the server's plan cache.

``MEGA_QUERY`` executes in tens of milliseconds, but a statement past the size
the server will cache is re-planned on every execution — hundreds of
milliseconds self-hosted, about a second on AuraDB Free — and the edge is
cumulative: one more section over it and the whole statement pays, silently.
The edge is also server-version dependent, so a line or ``OPTIONAL MATCH``
count is the wrong guard. The driver summary's ``result_available_after``
(server-side time to the first record) measures the real thing: a cached plan
answers in single-digit milliseconds, a re-plan in hundreds.

Three back-to-back executions of each statement; the third must be cached.
A new section belongs in a statement of its own — add it to this list, never
to ``MEGA_QUERY``.
"""

import pytest
from neo4j import AsyncDriver

from adapters.persistence.neo4j.user_context_queries import (
    CONSOLIDATED_QUERY,
    ENTRY_KNOWLEDGE_APPLIED_QUERY,
    MEGA_QUERY,
    STATUS_PARAMS,
    SUBMISSION_STATS_QUERY,
    build_mega_query_params,
)
from core.models.type_hints import UserUID

_USER_UID = UserUID("user_test")

# Well under a re-plan (hundreds of ms on the pinned image, measured 460-660 ms
# for the statement one block over the edge) and well over a cached execution
# (2-5 ms here; a slow CI runner still answers in tens).
_CACHED_PLAN_CEILING_MS = 100

_MEGA_PARAMS = build_mega_query_params(_USER_UID)

_STATEMENTS = [
    pytest.param(MEGA_QUERY, _MEGA_PARAMS, id="MEGA_QUERY"),
    pytest.param(
        SUBMISSION_STATS_QUERY,
        {"user_uid": _USER_UID, "window_start": _MEGA_PARAMS["window_start"]},
        id="SUBMISSION_STATS_QUERY",
    ),
    pytest.param(
        ENTRY_KNOWLEDGE_APPLIED_QUERY,
        {"user_uid": _USER_UID, "min_confidence": 0.7},
        id="ENTRY_KNOWLEDGE_APPLIED_QUERY",
    ),
    pytest.param(
        CONSOLIDATED_QUERY,
        {"user_uid": _USER_UID, "today": _MEGA_PARAMS["today"], **STATUS_PARAMS},
        id="CONSOLIDATED_QUERY",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("query", "params"), _STATEMENTS)
async def test_third_execution_is_served_from_the_plan_cache(
    neo4j_driver: AsyncDriver, ensure_test_users, query: str, params: dict
) -> None:
    """The third back-to-back run answers in cached-plan time, not planner time."""
    available_after: list[int] = []
    async with neo4j_driver.session() as session:
        for _ in range(3):
            result = await session.run(query, params)
            summary = await result.consume()
            available_after.append(summary.result_available_after or 0)

    assert available_after[2] < _CACHED_PLAN_CEILING_MS, (
        f"result_available_after across three runs: {available_after} ms — the third is "
        f"planner time, so the server is not caching this statement's plan. The edge is "
        f"cumulative: lift the newest section into a statement of its own "
        f"(see ENTRY_KNOWLEDGE_APPLIED_QUERY) instead of growing this one."
    )
