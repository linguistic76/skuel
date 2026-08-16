"""The fulltext half of hybrid search, against a real Neo4j.

Covers what mocks structurally cannot: that the index name the QUERY side
derives resolves to the index the SCHEMA side created, that Lucene ranks a term
case-insensitively where the live ``CONTAINS`` path would miss it, that the
publication gate withholds drafts on this second door (Codex #1006 shipped
through the vector door; ``query_fulltext_index`` was ungated until this arc),
and that Lucene syntax in user input searches rather than throws.

``tests/integration/conftest.py`` never runs the schema manager and
``clean_neo4j`` wipes non-User nodes, so the fixture syncs the fulltext indexes
itself — the same call the composition root makes at boot.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.neo4j_schema_manager import Neo4jSchemaManager
from adapters.persistence.neo4j.vector_search_backend import VectorSearchBackend
from core.config.unified_config import VectorSearchConfig
from core.models.enums.neo_labels import NeoLabel
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService

PUBLISHED_UID = "ps.fulltext-probe.published"
DRAFT_UID = "ps.fulltext-probe.draft"
SPECIALS_UID = "ps.fulltext-probe.specials"

# "Photosynthesis" is seeded capitalized and searched lowercase: the live text
# path is case-SENSITIVE CONTAINS, so this term is exactly what it misses.
SEED = """
CREATE (:Entity:PathStep {uid: $published, entity_type: 'path_step',
                          title: 'Photosynthesis in deep shade',
                          intent: 'Understand chloroplast behaviour',
                          description: 'A published step about photosynthesis.',
                          created_at: '2026-01-01'})
CREATE (:Entity:PathStep {uid: $draft, entity_type: 'path_step',
                          title: 'Photosynthesis draft notes',
                          intent: 'Draft intent about photosynthesis',
                          description: 'A draft step about photosynthesis.',
                          created_at: '2026-01-02',
                          publication_state: 'draft'})
CREATE (:Entity:PathStep {uid: $specials, entity_type: 'path_step',
                          title: 'C++ (advanced) topics',
                          intent: 'Syntax that Lucene would parse',
                          description: 'Title carries Lucene special characters.',
                          created_at: '2026-01-03'})
"""

CLEANUP = "MATCH (n) WHERE n.uid STARTS WITH 'ps.fulltext-probe.' DETACH DELETE n"

SEED_PARAMS = {"published": PUBLISHED_UID, "draft": DRAFT_UID, "specials": SPECIALS_UID}


@pytest_asyncio.fixture
async def fulltext_graph(neo4j_driver: AsyncDriver) -> AsyncGenerator[AsyncDriver]:
    """Seed the probe corpus behind real, boot-identical fulltext indexes."""
    sync_result = await Neo4jSchemaManager(neo4j_driver).sync_fulltext_indexes()
    assert sync_result.is_ok, f"fulltext index sync failed: {sync_result}"
    assert not sync_result.value["failed"], f"indexes failed: {sync_result.value['failed']}"

    async with neo4j_driver.session() as session:
        await session.run(CLEANUP)
        await session.run(SEED, SEED_PARAMS)
        # Fulltext indexes are eventually consistent — without this the seeded
        # rows may not be searchable yet and every assertion below passes vacuously.
        await session.run("CALL db.awaitIndexes(120)")

    yield neo4j_driver

    async with neo4j_driver.session() as session:
        await session.run(CLEANUP)


@pytest.fixture
def search_service(fulltext_graph: AsyncDriver) -> Neo4jVectorSearchService:
    """The real service over the real backend — no embeddings (fulltext half only)."""
    backend = VectorSearchBackend(Neo4jQueryExecutor(fulltext_graph))
    return Neo4jVectorSearchService(backend=backend, config=VectorSearchConfig())


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pathstep_fulltext_index_exists_under_the_derived_name(
    fulltext_graph: AsyncDriver,
) -> None:
    """The multi-word label's index resolves — `pathstep_fulltext_idx` never did."""
    expected = NeoLabel.fulltext_index_name(NeoLabel.PATH_STEP)
    assert expected == "path_step_fulltext_idx"

    async with fulltext_graph.session() as session:
        result = await session.run(
            "SHOW INDEXES YIELD name, type, labelsOrTypes "
            "WHERE name = $name RETURN name, type, labelsOrTypes",
            {"name": expected},
        )
        indexes = await result.data()

    assert len(indexes) == 1, f"{expected} not found — the query side would match nothing"
    assert indexes[0]["type"] == "FULLTEXT"
    assert "PathStep" in indexes[0]["labelsOrTypes"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fulltext_matches_case_insensitively(
    search_service: Neo4jVectorSearchService,
) -> None:
    """Lucene finds 'Photosynthesis' from 'photosynthesis' — CONTAINS does not."""
    result = await search_service._fulltext_search(
        label=NeoLabel.PATH_STEP.value, query_text="photosynthesis", limit=10
    )

    assert result.is_ok, f"fulltext search failed: {result}"
    uids = [item["node"]["uid"] for item in result.value]
    assert PUBLISHED_UID in uids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_case_sensitive_contains_would_miss_it(fulltext_graph: AsyncDriver) -> None:
    """The negative control: without it, the test above proves nothing about ranking."""
    async with fulltext_graph.session() as session:
        result = await session.run(
            "MATCH (n:PathStep) WHERE n.title CONTAINS $q RETURN n.uid AS uid",
            {"q": "photosynthesis"},
        )
        rows = await result.data()

    assert rows == [], "CONTAINS matched case-insensitively — the premise no longer holds"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_draft_is_withheld(search_service: Neo4jVectorSearchService) -> None:
    """The publication gate on the second door (Codex #1006 class)."""
    result = await search_service._fulltext_search(
        label=NeoLabel.PATH_STEP.value, query_text="photosynthesis", limit=10
    )

    assert result.is_ok
    uids = [item["node"]["uid"] for item in result.value]
    assert DRAFT_UID not in uids, "draft PathStep leaked through the fulltext door"
    assert PUBLISHED_UID in uids, "gate withheld everything — exclusion proves nothing"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ungated_query_would_leak_the_draft(fulltext_graph: AsyncDriver) -> None:
    """Positive control: the same query without the gate returns the draft.

    Without this, a fixture that simply returns no rows would pass the
    exclusion assertion above with a gate of zero measured effect.
    """
    async with fulltext_graph.session() as session:
        result = await session.run(
            "CALL db.index.fulltext.queryNodes($index_name, $q) YIELD node, score "
            "RETURN node.uid AS uid",
            {"index_name": NeoLabel.fulltext_index_name(NeoLabel.PATH_STEP), "q": "photosynthesis"},
        )
        rows = await result.data()

    uids = [row["uid"] for row in rows]
    assert DRAFT_UID in uids, "the draft is unreachable even ungated — the gate is unproven"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lucene_specials_do_not_raise(search_service: Neo4jVectorSearchService) -> None:
    """Unescaped, `C++ (advanced)` is a Lucene parse error, not a search."""
    result = await search_service._fulltext_search(
        label=NeoLabel.PATH_STEP.value, query_text="C++ (advanced)", limit=10
    )

    assert result.is_ok, f"Lucene specials broke the query: {result}"
    uids = [item["node"]["uid"] for item in result.value]
    assert SPECIALS_UID in uids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unbalanced_quote_does_not_raise(search_service: Neo4jVectorSearchService) -> None:
    """The commonest accidental parse error in a search box."""
    result = await search_service._fulltext_search(
        label=NeoLabel.PATH_STEP.value, query_text='say "hello', limit=10
    )

    assert result.is_ok, f"unbalanced quote broke the query: {result}"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["AND", "OR", "NOT"])
async def test_bare_boolean_keyword_does_not_raise(
    search_service: Neo4jVectorSearchService, query: str
) -> None:
    """Escaping characters alone left this door open — a bare uppercase
    operator raised Lucene's ParseException (Codex, PR #1074)."""
    result = await search_service._fulltext_search(
        label=NeoLabel.PATH_STEP.value, query_text=query, limit=10
    )

    assert result.is_ok, f"bare {query!r} broke the query: {result}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_boolean_keywords_are_literal_not_operators(
    search_service: Neo4jVectorSearchService,
) -> None:
    """`photosynthesis NOT shade` must not EXCLUDE the shade step.

    Unquoted, Lucene reads `NOT` as negation and withholds the published step —
    silently answering a question the user never asked.
    """
    result = await search_service._fulltext_search(
        label=NeoLabel.PATH_STEP.value, query_text="photosynthesis NOT shade", limit=10
    )

    assert result.is_ok, f"boolean query broke: {result}"
    uids = [item["node"]["uid"] for item in result.value]
    assert PUBLISHED_UID in uids, "NOT was parsed as negation — the term is meant to be literal"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hybrid_search_degrades_to_fulltext_without_embeddings(
    search_service: Neo4jVectorSearchService,
) -> None:
    """The wired entry end to end: no embeddings service → fulltext-only, still gated."""
    result, metrics = await search_service.hybrid_search_with_metrics(
        label=NeoLabel.PATH_STEP.value, query_text="photosynthesis", limit=10
    )

    assert result.is_ok, f"hybrid search failed: {result}"
    assert metrics is not None
    uids = [item["node"]["uid"] for item in result.value]
    assert PUBLISHED_UID in uids
    assert DRAFT_UID not in uids
