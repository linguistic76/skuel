"""
Every user-context statement is served from the server's plan cache.

A rich-context statement executes in tens of milliseconds, but a statement
past the size the server will cache is re-planned on every execution —
hundreds of milliseconds self-hosted, about a second on AuraDB Free — and the
edge is cumulative: one more section over it and the whole statement pays,
silently. The edge is also server-version dependent, so a line or ``OPTIONAL
MATCH`` count is the wrong guard. The driver summary's ``result_available_after``
(server-side time to the first record) measures the real thing: a cached plan
answers in single-digit milliseconds, a re-plan in hundreds.

Three back-to-back executions of each statement; the third must be cached.
The parametrization is DERIVED from ``RICH_CONTEXT_STATEMENTS`` — a statement
registered there is guarded by construction — plus the reads that run beside
the registry and the standard-context statement, and
``test_every_statement_constant_is_guarded`` fails if a ``*_QUERY`` constant
exists in the module that this parametrization does not run.
"""

import pytest
from neo4j import AsyncDriver

from adapters.persistence.neo4j import user_context_queries
from adapters.persistence.neo4j.user_context_queries import (
    CONSOLIDATED_QUERY,
    ENTRY_KNOWLEDGE_APPLIED_QUERY,
    RICH_CONTEXT_STATEMENTS,
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

_RICH_PARAMS = build_mega_query_params(_USER_UID)

_STATEMENTS = [
    *(pytest.param(query, _RICH_PARAMS, id=name) for name, query in RICH_CONTEXT_STATEMENTS),
    pytest.param(
        SUBMISSION_STATS_QUERY,
        {"user_uid": _USER_UID, "window_start": _RICH_PARAMS["window_start"]},
        id="SUBMISSION_STATS_QUERY",
    ),
    pytest.param(
        ENTRY_KNOWLEDGE_APPLIED_QUERY,
        {"user_uid": _USER_UID, "min_confidence": 0.7},
        id="ENTRY_KNOWLEDGE_APPLIED_QUERY",
    ),
    pytest.param(
        CONSOLIDATED_QUERY,
        {"user_uid": _USER_UID, "today": _RICH_PARAMS["today"], **STATUS_PARAMS},
        id="CONSOLIDATED_QUERY",
    ),
]


def test_every_statement_constant_is_guarded() -> None:
    """A ``*_QUERY`` constant the module defines is one this file runs.

    The registry covers itself by derivation; this covers the statements that
    are NOT registry entries (their own executor methods, their own result
    contracts), so a new one cannot be added to the module and left out here.
    """
    guarded = {param.values[0] for param in _STATEMENTS}
    constants = {
        name: value
        for name, value in vars(user_context_queries).items()
        if name.endswith("_QUERY") and isinstance(value, str)
    }
    unguarded = sorted(name for name, text in constants.items() if text not in guarded)

    assert constants, "the module defines its statements as *_QUERY constants"
    assert unguarded == [], (
        f"{unguarded} are statements this module executes but this guard never runs — add "
        "each to _STATEMENTS with the parameters its executor method passes"
    )


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
        f"cumulative: give the newest read a statement of its own (a new "
        f"RICH_CONTEXT_STATEMENTS entry) instead of growing this one."
    )
