"""The owner unnames knowledge by deleting its ``@ku`` from the entry's text.

A link the owner named (an ``APPLIES_KNOWLEDGE`` edge with no inference stamp) lives
as long as the text names it: when the extraction re-reads the entry and the
reference is gone, the link is retracted and recorded as removed
(``grounding_rejected_ku_uids``), the record the owner's remove door writes. So:

- an unnamed link is gone, and a link the text still names stays;
- a link the grounding pass inferred is not the text's to retract;
- a reference the text still makes keeps its link even when its line no longer
  parses, or the Ku became a draft and can no longer be linked;
- naming it again relinks it without a second substance credit;
- the grounding pass never re-makes a removed pair, even one whose caller read
  the entry before the removal.

Everything from the extractor outward is the real code over real Neo4j; entity
creation goes through the pipeline suite's graph-writing task stub.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from adapters.persistence.neo4j.entry_grounding_backend import EntryGroundingBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry_request import UserEntryUpdateRequest
from tests.integration.user_entry.test_entry_knowledge_credit_once import (
    _edges,
    _entry,
    _process,
)
from tests.integration.user_entry.test_extract_activities_pipeline import _seed_ku

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.models.user_entry.user_entry import UserEntry
    from core.services.user_entry.user_entry_service import UserEntryService


async def _rewrite(
    user_entry_service: UserEntryService, entry: UserEntry, content: str
) -> UserEntry:
    updated = await user_entry_service.update_entry(
        uid=entry.uid,
        user_uid=UserUID(entry.user_uid),
        request=UserEntryUpdateRequest(content=content),
    )
    assert updated.is_ok, updated
    reread = await user_entry_service.get_entry(entry.uid, UserUID(entry.user_uid))
    assert reread.is_ok and reread.value is not None, reread
    return reread.value


async def _rejected(neo4j_driver: AsyncDriver, entry_uid: str) -> list[str] | None:
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (e:UserEntry {uid: $uid}) RETURN e.grounding_rejected_ku_uids AS rejected",
            uid=entry_uid,
        )
        record = await result.single()
        assert record is not None
        return record["rejected"]


_NAMED = {"inferred": None, "confidence": None, "grounded_at": None}


@pytest.fixture
def grounding(neo4j_driver: AsyncDriver) -> EntryGroundingBackend:
    return EntryGroundingBackend(Neo4jQueryExecutor(neo4j_driver))


@pytest.mark.integration
class TestUnnamedKnowledgeRetracted:
    @pytest.mark.asyncio
    async def test_a_reference_deleted_from_the_text_unlinks_and_is_recorded(
        self, neo4j_driver, user_entry_service, seed_user
    ):
        user_uid = await seed_user(f"user_unname_{uuid4().hex[:6]}")
        dropped = await _seed_ku(neo4j_driver, f"ku.it.dropped-{uuid4().hex[:6]}")
        kept = await _seed_ku(neo4j_driver, f"ku.it.kept-{uuid4().hex[:6]}")
        entry = await _entry(
            user_entry_service,
            user_uid,
            f"- [ ] Read on it @context(task) @ku({dropped})\n"
            f"- [ ] Read on more @context(task) @ku({kept})\n",
        )
        assert sorted(await _process(neo4j_driver, user_entry_service, entry)) == sorted(
            [dropped, kept]
        )

        entry = await _rewrite(
            user_entry_service,
            entry,
            f"- [ ] Read on it @context(task)\n- [ ] Read on more @context(task) @ku({kept})\n",
        )
        assert await _process(neo4j_driver, user_entry_service, entry) == []

        assert await _edges(neo4j_driver, entry.uid, dropped) == []
        assert await _rejected(neo4j_driver, entry.uid) == [dropped]
        # Control: the reference the text still makes keeps its link.
        assert await _edges(neo4j_driver, entry.uid, kept) == [_NAMED]

    @pytest.mark.asyncio
    async def test_an_inferred_link_the_text_never_named_stays(
        self, neo4j_driver, user_entry_service, seed_user, grounding
    ):
        user_uid = await seed_user(f"user_unname_{uuid4().hex[:6]}")
        inferred = await _seed_ku(neo4j_driver, f"ku.it.inferred-{uuid4().hex[:6]}")
        entry = await _entry(user_entry_service, user_uid, "- [ ] Read @context(task)\n")
        assert (await grounding.write_applies_knowledge(entry.uid, inferred, 0.74)).value is True

        await _process(neo4j_driver, user_entry_service, entry)

        edges = await _edges(neo4j_driver, entry.uid, inferred)
        assert [e["inferred"] for e in edges] == [True]
        assert await _rejected(neo4j_driver, entry.uid) is None

    @pytest.mark.asyncio
    async def test_a_reference_still_in_the_text_keeps_its_link_when_it_cannot_be_relinked(
        self, neo4j_driver, user_entry_service, seed_user
    ):
        user_uid = await seed_user(f"user_unname_{uuid4().hex[:6]}")
        named = await _seed_ku(neo4j_driver, f"ku.it.drafted-{uuid4().hex[:6]}")
        entry = await _entry(
            user_entry_service, user_uid, f"- [ ] Read on it @context(task) @ku({named})\n"
        )
        assert await _process(neo4j_driver, user_entry_service, entry) == [named]
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (k:Ku {uid: $uid}) SET k.publication_state = 'draft'", uid=named
            )

        await _process(neo4j_driver, user_entry_service, entry)

        assert await _edges(neo4j_driver, entry.uid, named) == [_NAMED]
        assert await _rejected(neo4j_driver, entry.uid) is None

    @pytest.mark.asyncio
    async def test_naming_it_again_relinks_without_a_second_credit(
        self, neo4j_driver, user_entry_service, seed_user
    ):
        user_uid = await seed_user(f"user_unname_{uuid4().hex[:6]}")
        named = await _seed_ku(neo4j_driver, f"ku.it.renamed-{uuid4().hex[:6]}")
        fresh = await _seed_ku(neo4j_driver, f"ku.it.fresh-{uuid4().hex[:6]}")
        line = f"- [ ] Read on it @context(task) @ku({named})\n"
        entry = await _entry(user_entry_service, user_uid, line)
        assert await _process(neo4j_driver, user_entry_service, entry) == [named]
        entry = await _rewrite(user_entry_service, entry, "- [ ] Read on it @context(task)\n")
        await _process(neo4j_driver, user_entry_service, entry)
        assert await _edges(neo4j_driver, entry.uid, named) == []

        entry = await _rewrite(
            user_entry_service,
            entry,
            line + f"- [ ] Read on more @context(task) @ku({fresh})\n",
        )
        credited = await _process(neo4j_driver, user_entry_service, entry)

        # Control: the reference never linked before is credited, once.
        assert credited == [fresh]
        assert await _edges(neo4j_driver, entry.uid, named) == [_NAMED]

    @pytest.mark.asyncio
    async def test_the_grounding_pass_never_remakes_a_removed_pair(
        self, neo4j_driver, user_entry_service, seed_user, grounding
    ):
        user_uid = await seed_user(f"user_unname_{uuid4().hex[:6]}")
        removed = await _seed_ku(neo4j_driver, f"ku.it.removed-{uuid4().hex[:6]}")
        other = await _seed_ku(neo4j_driver, f"ku.it.other-{uuid4().hex[:6]}")
        entry = await _entry(user_entry_service, user_uid, "- [ ] Read @context(task)\n")
        assert (await grounding.write_applies_knowledge(entry.uid, removed, 0.74)).value is True
        removal = await grounding.remove_grounded_edge(entry.uid, removed, UserUID(user_uid))
        assert removal.is_ok and removal.value is not None

        # A pass whose read came before the removal still holds the candidate.
        rewritten = await grounding.write_applies_knowledge(entry.uid, removed, 0.74)

        assert rewritten.is_ok and rewritten.value is False
        assert await _edges(neo4j_driver, entry.uid, removed) == []
        # Control: a pair the owner never removed is still written.
        assert (await grounding.write_applies_knowledge(entry.uid, other, 0.74)).value is True

    @pytest.mark.asyncio
    async def test_a_line_that_no_longer_parses_still_names_its_knowledge(
        self, neo4j_driver, user_entry_service, seed_user
    ):
        user_uid = await seed_user(f"user_unname_{uuid4().hex[:6]}")
        named = await _seed_ku(neo4j_driver, f"ku.it.broken-{uuid4().hex[:6]}")
        dropped = await _seed_ku(neo4j_driver, f"ku.it.dropped-{uuid4().hex[:6]}")
        entry = await _entry(
            user_entry_service,
            user_uid,
            f"- [ ] Read on it @context(task) @ku({named})\n"
            f"- [ ] Read on more @context(task) @ku({dropped})\n",
        )
        await _process(neo4j_driver, user_entry_service, entry)

        entry = await _rewrite(
            user_entry_service,
            entry,
            f"- [ ] Read on it @context(bogus) @ku({named})\n- [ ] Read on more @context(task)\n",
        )
        await _process(neo4j_driver, user_entry_service, entry)

        assert await _edges(neo4j_driver, entry.uid, named) == [_NAMED]
        # Control: the reference deleted in the same edit is retracted.
        assert await _edges(neo4j_driver, entry.uid, dropped) == []
        assert await _rejected(neo4j_driver, entry.uid) == [dropped]
