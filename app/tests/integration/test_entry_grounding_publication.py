"""Vector grounding links an entry to published Kus only.

``EntryGroundingBackend.write_applies_knowledge`` is the second writer of an entry's
``APPLIES_KNOWLEDGE`` edge (the first is the ``@ku()`` reference,
``UserEntryService.link_applied_knowledge``). A Ku marked ``publication_state: draft``
is unfinished curriculum no learner is shown, so it is no entry's knowledge: the write
matches nothing, returns False, and the caller publishes no substance event.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.entry_grounding_backend import EntryGroundingBackend
from tests.helpers.production_backends import build_production_backends

ENTRY = "ue.grounding-publication"
KU_PUBLISHED = "ku.grounding.published"
KU_LEGACY = "ku.grounding.no-state"  # authored before publication_state existed
KU_DRAFT = "ku.grounding.draft"


@pytest_asyncio.fixture
async def backend(neo4j_driver, clean_neo4j) -> EntryGroundingBackend:
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (:Entity:UserEntry {uid: $entry, entity_type: 'user_entry',
                                       pipeline: 'knowledge', title: 'entry'})
            CREATE (:Entity:Ku {uid: $published, entity_type: 'ku', title: 'published',
                                publication_state: 'published'})
            CREATE (:Entity:Ku {uid: $legacy, entity_type: 'ku', title: 'legacy'})
            CREATE (:Entity:Ku {uid: $draft, entity_type: 'ku', title: 'draft',
                                publication_state: 'draft'})
            """,
            entry=ENTRY,
            published=KU_PUBLISHED,
            legacy=KU_LEGACY,
            draft=KU_DRAFT,
        )
    return build_production_backends(neo4j_driver)["entry_grounding_backend"]


async def _linked(neo4j_driver, ku_uid: str) -> bool:
    async with neo4j_driver.session() as session:
        record = await (
            await session.run(
                """
                MATCH (e:UserEntry {uid: $entry})
                RETURN EXISTS { (e)-[:APPLIES_KNOWLEDGE]->(:Ku {uid: $ku}) } AS linked
                """,
                entry=ENTRY,
                ku=ku_uid,
            )
        ).single()
    assert record is not None
    return bool(record["linked"])


@pytest.mark.asyncio
@pytest.mark.parametrize("ku_uid", [KU_PUBLISHED, KU_LEGACY], ids=["published", "no-state"])
async def test_a_published_ku_is_grounded(backend, neo4j_driver, ku_uid: str) -> None:
    written = await backend.write_applies_knowledge(ENTRY, ku_uid, 0.91)

    assert written.is_ok and written.value is True
    assert await _linked(neo4j_driver, ku_uid)


@pytest.mark.asyncio
async def test_a_draft_ku_is_not_grounded(backend, neo4j_driver) -> None:
    written = await backend.write_applies_knowledge(ENTRY, KU_DRAFT, 0.91)

    assert written.is_ok and written.value is False
    assert not await _linked(neo4j_driver, KU_DRAFT)
