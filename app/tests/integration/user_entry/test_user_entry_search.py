"""
UserEntry Search Integration — SearchRouter composition
========================================================

Proves the ``user_entry`` search wiring end to end against a real Neo4j
container:

    SearchRouter.search(EntityType.USER_ENTRY, ..., user_uid=...)
        → UserEntryService.search → backend.text_search_raw (user_uid scope)
    SearchRouter.faceted_search(entity_types=[USER_ENTRY], user_uid)
        → _graph_aware_domain_search("user_entry")
        → UserEntryService.graph_aware_faceted_search (OWNS-edge scope)

The cross-user negative controls are the point: journal periodic notes live
in this store, so owner-only scoping is the privacy line.
"""

from __future__ import annotations

import pytest

from core.models.enums.entity_enums import EntityType
from core.models.enums.pipeline import Pipeline
from core.models.search_request import SearchRequest
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.orchestrator.search_router import SearchRouter

OWNER_UID = "user_ue_search_owner"
OTHER_UID = "user_ue_search_other"


@pytest.fixture
def search_router(user_entry_service) -> SearchRouter:
    """SearchRouter wired with only the user_entry domain."""
    return SearchRouter(user_entry=user_entry_service)


async def _seed_entries(user_entry_service, seed_user) -> dict[str, str]:
    """Create two owner entries (knowledge + journal pipeline) and one
    entry for the other user, all through the real create path."""
    await seed_user(OWNER_UID, name="Search Owner")
    await seed_user(OTHER_UID, name="Search Other")

    created: dict[str, str] = {}
    specs = [
        # key, owner, title, content, pipeline
        (
            "tasks_list",
            OWNER_UID,
            "My Tasks List",
            "A living list of tasks I keep as an exercise entry.",
            Pipeline.KNOWLEDGE,
        ),
        (
            "journal_note",
            OWNER_UID,
            "Morning reflection",
            "Private journal text mentioning zettelkasten workflow.",
            Pipeline.JOURNAL,
        ),
        (
            "other_users",
            OTHER_UID,
            "Other Tasks List",
            "The other user's tasks note — must never cross over.",
            Pipeline.KNOWLEDGE,
        ),
    ]
    for key, owner, title, content, pipeline in specs:
        result = await user_entry_service.create_entry(
            request=UserEntryCreateRequest(title=title, content=content, pipeline=pipeline),
            user_uid=owner,
        )
        assert result.is_ok, result.expect_error()
        entry, _ = result.value
        created[key] = entry.uid
    return created


@pytest.mark.asyncio
async def test_owner_search_finds_entry_by_title_and_content(
    clean_neo4j, user_entry_service, seed_user, search_router
) -> None:
    created = await _seed_entries(user_entry_service, seed_user)

    # By title
    by_title = await search_router.search(EntityType.USER_ENTRY, "Tasks List", user_uid=OWNER_UID)
    assert by_title.is_ok, by_title.expect_error()
    assert {e.uid for e in by_title.value} == {created["tasks_list"]}

    # By content-field text (content is a configured search field)
    by_content = await search_router.search(
        EntityType.USER_ENTRY, "zettelkasten", user_uid=OWNER_UID
    )
    assert by_content.is_ok, by_content.expect_error()
    assert {e.uid for e in by_content.value} == {created["journal_note"]}


@pytest.mark.asyncio
async def test_cross_user_negative_control(
    clean_neo4j, user_entry_service, seed_user, search_router
) -> None:
    """User B never sees user A's entries — through either search path."""
    created = await _seed_entries(user_entry_service, seed_user)

    # Single-domain path: OTHER searching sees only their own entry
    result = await search_router.search(EntityType.USER_ENTRY, "Tasks", user_uid=OTHER_UID)
    assert result.is_ok, result.expect_error()
    assert {e.uid for e in result.value} == {created["other_users"]}

    # OTHER searching for OWNER's private journal text: nothing
    journal_probe = await search_router.search(
        EntityType.USER_ENTRY, "zettelkasten", user_uid=OTHER_UID
    )
    assert journal_probe.is_ok
    assert journal_probe.value == []

    # Faceted path (the /search dropdown route): same isolation
    request = SearchRequest(query_text="Tasks", entity_types=[EntityType.USER_ENTRY])
    faceted = await search_router.faceted_search(request, user_uid=OTHER_UID)
    assert faceted.is_ok, faceted.expect_error()
    uids = {r.get("uid") for r in faceted.value.results}
    assert created["tasks_list"] not in uids
    assert created["journal_note"] not in uids


@pytest.mark.asyncio
async def test_unscoped_search_is_refused(
    clean_neo4j, user_entry_service, seed_user, search_router
) -> None:
    """No user scope → refusal, not a cross-user result set."""
    await _seed_entries(user_entry_service, seed_user)

    result = await search_router.search(EntityType.USER_ENTRY, "Tasks")
    assert result.is_error

    # Faceted single-type path refuses loudly too (not an empty success)
    request = SearchRequest(query_text="Tasks", entity_types=[EntityType.USER_ENTRY])
    faceted = await search_router.faceted_search(request, user_uid=None)
    assert faceted.is_error


@pytest.mark.asyncio
async def test_multi_type_filter_returns_scoped_entries(
    clean_neo4j, user_entry_service, seed_user, search_router
) -> None:
    """[USER_ENTRY, TASK] narrows the sweep and still surfaces the caller's
    own entries (Kody finding on PR #512) — owner-scoped, never cross-user."""
    created = await _seed_entries(user_entry_service, seed_user)

    request = SearchRequest(
        query_text="Tasks", entity_types=[EntityType.USER_ENTRY, EntityType.TASK]
    )
    result = await search_router.faceted_search(request, user_uid=OWNER_UID)
    assert result.is_ok, result.expect_error()
    uids = {r.get("uid") for r in result.value.results}
    assert created["tasks_list"] in uids
    assert created["other_users"] not in uids


@pytest.mark.asyncio
async def test_faceted_search_owner_scope_and_pipeline_facet(
    clean_neo4j, user_entry_service, seed_user, search_router
) -> None:
    created = await _seed_entries(user_entry_service, seed_user)

    # Owner faceted search finds their entry through the graph-aware path
    request = SearchRequest(query_text="Tasks", entity_types=[EntityType.USER_ENTRY])
    faceted = await search_router.faceted_search(request, user_uid=OWNER_UID)
    assert faceted.is_ok, faceted.expect_error()
    assert faceted.value.domain == "user_entry"
    uids = {r.get("uid") for r in faceted.value.results}
    assert uids == {created["tasks_list"]}

    # Pipeline facet (category_field="pipeline"): journal-only slice
    journal_request = SearchRequest(
        query_text=None,
        entity_types=[EntityType.USER_ENTRY],
        extended_facets={"pipeline": Pipeline.JOURNAL.value},
    )
    journal_faceted = await search_router.faceted_search(journal_request, user_uid=OWNER_UID)
    assert journal_faceted.is_ok, journal_faceted.expect_error()
    journal_uids = {r.get("uid") for r in journal_faceted.value.results}
    assert journal_uids == {created["journal_note"]}
