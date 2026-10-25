"""A note that opts out of grounding loses the links the grounding pass inferred.

A note on a grounded pipeline (``Pipeline.grounds_knowledge`` — knowledge notes
and activity notes) is embedded and linked to Kus by the grounding pass. The
re-sync that turns it ``private: true``, or moves it to a pipeline that is not
grounded, lands on ``UserEntryBackend.upsert`` and takes those links back:

- every ``inferred`` ``APPLIES_KNOWLEDGE`` edge is deleted, and its Ku recorded
  in ``grounding_rejected_ku_uids`` — so a note that opts back in is never
  re-linked, or re-credited, to it;
- ``grounded_text_hash`` is cleared — so the note that opts back in is pending
  again once its vector is stored, even when its text is unchanged;
- a link the owner named (``@ku``) stays: it is the text's.

A re-sync that stays grounded keeps every link, a move between two grounded
pipelines included; a re-sync that takes no write (another owner's uid)
retracts nothing.

The entry is written through the vault door's request (a deterministic uid);
the links through their two real writers; the vector through the embeddings
writer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from adapters.persistence.neo4j.entry_grounding_backend import EntryGroundingBackend
from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid
from tests.integration.user_entry.test_entry_grounding_pending import _embed
from tests.integration.user_entry.test_extract_activities_pipeline import _seed_ku

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.services.user_entry.user_entry_service import UserEntryService

_CONTENT = "Kept the morning walk; noticed the urge to skip it and went anyway."


async def _sync(
    service: UserEntryService,
    owner: str,
    uid: str,
    pipeline: Pipeline,
    private: bool = False,
) -> None:
    result = await service.create_entry(
        request=UserEntryCreateRequest(
            uid=uid, title="Daily", content=_CONTENT, pipeline=pipeline, private=private
        ),
        user_uid=owner,
    )
    assert result.is_ok, result.expect_error()


async def _entry(neo4j_driver: AsyncDriver, uid: str) -> dict[str, object]:
    async with neo4j_driver.session() as session:
        record = await (
            await session.run("MATCH (e:UserEntry {uid: $uid}) RETURN e", uid=uid)
        ).single()
    assert record is not None, uid
    return dict(record["e"])


async def _links(neo4j_driver: AsyncDriver, uid: str) -> dict[str, bool]:
    """The entry's knowledge links: far-end uid → inferred."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (:UserEntry {uid: $uid})-[r:APPLIES_KNOWLEDGE]->(k)"
            " RETURN k.uid AS ku, coalesce(r.inferred, false) AS inferred",
            uid=uid,
        )
        return {record["ku"]: record["inferred"] async for record in result}


@pytest.fixture
def grounding(neo4j_driver: AsyncDriver) -> EntryGroundingBackend:
    return build_production_backends(neo4j_driver)["entry_grounding_backend"]


async def _grounded_note(
    neo4j_driver: AsyncDriver,
    service: UserEntryService,
    grounding: EntryGroundingBackend,
    owner: str,
    pipeline: Pipeline,
) -> tuple[str, str, str]:
    """A grounded note holding one inferred and one named link; returns (uid, inferred, named)."""
    tag = uuid4().hex[:6]
    uid = f"ue.optout-{tag}"
    inferred = await _seed_ku(neo4j_driver, f"ku.it.inferred-{tag}")
    named = await _seed_ku(neo4j_driver, f"ku.it.named-{tag}")
    await _sync(service, owner, uid, pipeline)
    await _embed(neo4j_driver, uid)

    wrote = await grounding.write_applies_knowledge(uid, inferred, 0.8)
    assert wrote.is_ok and wrote.value is True
    linked = await service.backend.write_applied_knowledge(uid, named)
    assert linked.is_ok and linked.value is not None and linked.value["created"]
    text_hash = str((await _entry(neo4j_driver, uid))["embedding_text_hash"])
    stamped = await grounding.stamp_grounded(uid, text_hash, 1)
    assert stamped.is_ok

    assert await _links(neo4j_driver, uid) == {inferred: True, named: False}
    return uid, inferred, named


@pytest.mark.integration
class TestOptingOutRetractsInferredLinks:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("before", "after", "private"),
        [
            (Pipeline.KNOWLEDGE, Pipeline.KNOWLEDGE, True),
            (Pipeline.EXTRACT_ACTIVITIES, Pipeline.EXTRACT_ACTIVITIES, True),
            (Pipeline.KNOWLEDGE, Pipeline.NONE, False),
            (Pipeline.EXTRACT_ACTIVITIES, Pipeline.LLM_SUMMARY, False),
        ],
        ids=[
            "knowledge-turns-private",
            "activity-note-turns-private",
            "knowledge-leaves-to-none",
            "activity-note-leaves-to-summary",
        ],
    )
    async def test_the_opting_out_resync_takes_the_inferred_links_and_keeps_the_named(
        self,
        clean_neo4j,
        neo4j_driver,
        user_entry_service,
        seed_user,
        grounding,
        before: Pipeline,
        after: Pipeline,
        private: bool,
    ):
        owner = await seed_user(seed_user_uid(f"optout_{uuid4().hex[:6]}"))
        uid, inferred, named = await _grounded_note(
            neo4j_driver, user_entry_service, grounding, owner, before
        )

        await _sync(user_entry_service, owner, uid, after, private)

        assert await _links(neo4j_driver, uid) == {named: False}
        props = await _entry(neo4j_driver, uid)
        assert props.get("grounding_rejected_ku_uids") == [inferred]
        assert "grounded_text_hash" not in props

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("before", "after"),
        [
            (Pipeline.KNOWLEDGE, Pipeline.KNOWLEDGE),
            (Pipeline.EXTRACT_ACTIVITIES, Pipeline.EXTRACT_ACTIVITIES),
            (Pipeline.KNOWLEDGE, Pipeline.EXTRACT_ACTIVITIES),
            (Pipeline.EXTRACT_ACTIVITIES, Pipeline.KNOWLEDGE),
        ],
        ids=[
            "knowledge-stays",
            "activity-note-stays",
            "knowledge-to-activity-note",
            "activity-note-to-knowledge",
        ],
    )
    async def test_a_resync_that_stays_grounded_keeps_every_link(
        self,
        clean_neo4j,
        neo4j_driver,
        user_entry_service,
        seed_user,
        grounding,
        before: Pipeline,
        after: Pipeline,
    ):
        owner = await seed_user(seed_user_uid(f"optout_{uuid4().hex[:6]}"))
        uid, inferred, named = await _grounded_note(
            neo4j_driver, user_entry_service, grounding, owner, before
        )

        await _sync(user_entry_service, owner, uid, after)

        assert await _links(neo4j_driver, uid) == {inferred: True, named: False}
        props = await _entry(neo4j_driver, uid)
        assert props.get("grounding_rejected_ku_uids") is None
        assert props.get("grounded_text_hash") is not None

    @pytest.mark.asyncio
    async def test_a_note_that_opts_back_in_is_pending_but_never_relinked_to_the_retracted_ku(
        self, clean_neo4j, neo4j_driver, user_entry_service, seed_user, grounding
    ):
        owner = await seed_user(seed_user_uid(f"optout_{uuid4().hex[:6]}"))
        uid, inferred, _named = await _grounded_note(
            neo4j_driver, user_entry_service, grounding, owner, Pipeline.EXTRACT_ACTIVITIES
        )
        await _sync(user_entry_service, owner, uid, Pipeline.EXTRACT_ACTIVITIES, private=True)

        # Opts back in with the same text: the worker stores the same vector.
        await _sync(user_entry_service, owner, uid, Pipeline.EXTRACT_ACTIVITIES)
        await _embed(neo4j_driver, uid)

        pending = await grounding.get_pending_entries(user_uid=owner)
        assert pending.is_ok, pending.expect_error()
        rows = {row["uid"]: row for row in pending.value}
        assert uid in rows, "an unchanged note that opted back in must be grounded afresh"
        assert inferred in rows[uid]["rejected_ku_uids"]

        rewrote = await grounding.write_applies_knowledge(uid, inferred, 0.8)
        assert rewrote.is_ok and rewrote.value is False, "credit-once: the pair is not re-made"
        assert inferred not in await _links(neo4j_driver, uid)

    @pytest.mark.asyncio
    async def test_a_resync_that_takes_no_write_retracts_nothing(
        self, clean_neo4j, neo4j_driver, user_entry_service, seed_user, grounding
    ):
        owner = await seed_user(seed_user_uid(f"optout_{uuid4().hex[:6]}"))
        other = await seed_user(seed_user_uid(f"optout_other_{uuid4().hex[:6]}"))
        uid, inferred, named = await _grounded_note(
            neo4j_driver, user_entry_service, grounding, owner, Pipeline.KNOWLEDGE
        )

        refused = await user_entry_service.create_entry(
            request=UserEntryCreateRequest(
                uid=uid, title="Daily", content=_CONTENT, pipeline=Pipeline.NONE, private=True
            ),
            user_uid=other,
        )
        assert refused.is_error

        assert await _links(neo4j_driver, uid) == {inferred: True, named: False}
        props = await _entry(neo4j_driver, uid)
        assert props.get("grounding_rejected_ku_uids") is None
        assert props.get("grounded_text_hash") is not None


@pytest.mark.integration
class TestAPassThatReadTheNoteBeforeItOptedOut:
    """A grounding pass reads its rows up front; the note may opt out before the pass
    writes. Its writes re-check, under the entry's lock, the state they were read for."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("opts_out", [True, False], ids=["opted-out", "control-still-grounded"])
    async def test_its_links_and_stamp_land_only_on_a_note_that_still_grounds(
        self, clean_neo4j, neo4j_driver, user_entry_service, seed_user, grounding, opts_out: bool
    ):
        owner = await seed_user(seed_user_uid(f"optout_{uuid4().hex[:6]}"))
        uid, _inferred, _named = await _grounded_note(
            neo4j_driver, user_entry_service, grounding, owner, Pipeline.KNOWLEDGE
        )
        late = await _seed_ku(neo4j_driver, f"ku.it.late-{uuid4().hex[:6]}")
        read_hash = str((await _entry(neo4j_driver, uid))["embedding_text_hash"])

        if opts_out:
            await _sync(user_entry_service, owner, uid, Pipeline.KNOWLEDGE, private=True)

        wrote = await grounding.write_applies_knowledge(uid, late, 0.8)
        stamped = await grounding.stamp_grounded(uid, read_hash, 2)
        assert wrote.is_ok and stamped.is_ok

        props = await _entry(neo4j_driver, uid)
        if opts_out:
            assert wrote.value is False
            assert late not in await _links(neo4j_driver, uid)
            assert "grounded_text_hash" not in props
        else:
            assert wrote.value is True
            assert (await _links(neo4j_driver, uid))[late] is True
            assert props.get("grounded_text_hash") == read_hash
            assert props.get("grounding_version") == 2

    @pytest.mark.asyncio
    async def test_its_stamp_after_the_note_opts_back_in_leaves_it_pending(
        self, clean_neo4j, neo4j_driver, user_entry_service, seed_user, grounding
    ):
        """Out and back in before the pass stamps: the note grounds again, but its
        vector is gone until the worker stores it, so the old pass's stamp is not
        for the text it holds."""
        owner = await seed_user(seed_user_uid(f"optout_{uuid4().hex[:6]}"))
        uid, _inferred, _named = await _grounded_note(
            neo4j_driver, user_entry_service, grounding, owner, Pipeline.EXTRACT_ACTIVITIES
        )
        read_hash = str((await _entry(neo4j_driver, uid))["embedding_text_hash"])
        await _sync(user_entry_service, owner, uid, Pipeline.EXTRACT_ACTIVITIES, private=True)
        await _sync(user_entry_service, owner, uid, Pipeline.EXTRACT_ACTIVITIES)

        stamped = await grounding.stamp_grounded(uid, read_hash, 2)
        assert stamped.is_ok
        assert "grounded_text_hash" not in await _entry(neo4j_driver, uid)

        await _embed(neo4j_driver, uid)
        pending = await grounding.get_pending_entries(user_uid=owner)
        assert pending.is_ok, pending.expect_error()
        assert uid in {row["uid"] for row in pending.value}
