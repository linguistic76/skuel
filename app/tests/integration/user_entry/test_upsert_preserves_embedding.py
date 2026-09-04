"""
Living-upsert re-sync preserves the embedding triple
=====================================================

The vault door re-syncs a note through ``UserEntryService.create_entry`` with
the same deterministic uid, which lands on ``UserEntryBackend.upsert``
(MERGE-on-uid, ``ON MATCH SET n += props``). The embedding triple
(``embedding`` / ``embedding_model`` / ``embedding_updated_at``) has ONE
writer — ``EmbeddingsService.store_embedding_with_metadata`` — and an entity
re-sync must not touch it: under ``+=`` a ``null`` REMOVES the property, so a
payload carrying the model's ``None`` defaults wiped the vector on every
re-sync and the worker re-embedded identical text (ADR-074 §8 broken for
exactly this door).

Fixtures mirror the writers' shapes: the vault door's request (deterministic
uid, ``pipeline: knowledge``) and the embeddings writer's full store
(vector + version + model + updated_at + text_hash), not a hand-set
``embedding`` alone.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from adapters.persistence.neo4j.embeddings_backend import EmbeddingsBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.constants import EmbeddingGeometry
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.services.embeddings_service import EmbeddingsService
from core.utils.embedding_text_builder import build_embedding_text

_UID = "ue_resync01"  # the tracker's path-keyed prior uid shape for a uid-less note
_MODEL = "text-embedding-3-small"


def _embeddings_service(neo4j_driver) -> EmbeddingsService:
    """The one embedding writer over a REAL backend; the inference client is inert."""
    client = MagicMock()
    client.model = _MODEL
    client.dimension = EmbeddingGeometry.DIMENSION
    client.max_input_chars = 20000
    return EmbeddingsService(
        EmbeddingsBackend(Neo4jQueryExecutor(neo4j_driver)), embedding_client=client
    )


def _note_request(content: str) -> UserEntryCreateRequest:
    return UserEntryCreateRequest(
        uid=_UID,
        title="Decisions 0",
        content=content,
        pipeline=Pipeline.KNOWLEDGE,
    )


async def _node_props(neo4j_driver, uid: str) -> dict:
    async with neo4j_driver.session() as session:
        record = await (
            await session.run("MATCH (n:UserEntry {uid: $uid}) RETURN n", uid=uid)
        ).single()
    assert record is not None, f"{uid} missing"
    return dict(record["n"])


async def _embed_as_the_writer(embeddings: EmbeddingsService, props: dict) -> str:
    """Store through the writer's own path and return the text it hashed."""
    text = build_embedding_text(EntityType.USER_ENTRY, props)
    stored = await embeddings.store_embedding_with_metadata(
        uid=props["uid"],
        label=NeoLabel.USER_ENTRY.value,
        embedding=[0.1] * EmbeddingGeometry.DIMENSION,
        text=text,
    )
    assert stored.is_ok, stored.expect_error()
    return text


@pytest.mark.asyncio
async def test_identical_resync_keeps_vector_and_stays_hash_fresh(
    clean_neo4j, user_entry_service, neo4j_driver, seed_user
) -> None:
    owner = await seed_user("user_resync_owner")
    content = "A decision is when you have power to choose."

    first = await user_entry_service.create_entry(request=_note_request(content), user_uid=owner)
    assert first.is_ok, first.expect_error()
    assert first.value[0].uid == _UID

    embeddings = _embeddings_service(neo4j_driver)
    text = await _embed_as_the_writer(embeddings, await _node_props(neo4j_driver, _UID))
    before = await _node_props(neo4j_driver, _UID)
    assert before.get("embedding") is not None

    # The re-sync: same uid, byte-identical content — the vault door's shape.
    second = await user_entry_service.create_entry(request=_note_request(content), user_uid=owner)
    assert second.is_ok, second.expect_error()

    after = await _node_props(neo4j_driver, _UID)
    assert after.get("embedding") is not None, "re-sync removed the vector"
    assert after.get("embedding_model") == _MODEL
    assert after.get("embedding_updated_at") == before["embedding_updated_at"], (
        "re-sync must not touch the embedding writer's timestamp"
    )
    assert after.get("embedding_version") == before["embedding_version"]
    assert after.get("embedding_text_hash") == before["embedding_text_hash"]

    fresh = await embeddings.verify_fresh_embeddings({_UID: text})
    assert fresh.is_ok, fresh.expect_error()
    assert fresh.value == {_UID}, "identical text must skip re-embedding (ADR-074 §8)"


@pytest.mark.asyncio
async def test_edited_resync_refreshes_content_but_keeps_vector_until_the_worker(
    clean_neo4j, user_entry_service, neo4j_driver, seed_user
) -> None:
    """The entity writer refreshes what the FILE authors; the vector stays the
    embedding writer's to replace (hash mismatch → not fresh → worker re-embeds)."""
    owner = await seed_user("user_resync_owner")

    first = await user_entry_service.create_entry(
        request=_note_request("first draft"), user_uid=owner
    )
    assert first.is_ok, first.expect_error()
    embeddings = _embeddings_service(neo4j_driver)
    old_text = await _embed_as_the_writer(embeddings, await _node_props(neo4j_driver, _UID))

    second = await user_entry_service.create_entry(
        request=_note_request("second draft"), user_uid=owner
    )
    assert second.is_ok, second.expect_error()

    after = await _node_props(neo4j_driver, _UID)
    assert after["content"] == "second draft", "re-sync must refresh authored fields"
    assert after.get("embedding") is not None, "an edit must not blank retrievability"

    new_text = build_embedding_text(EntityType.USER_ENTRY, after)
    assert new_text != old_text
    fresh = await embeddings.verify_fresh_embeddings({_UID: new_text})
    assert fresh.is_ok, fresh.expect_error()
    assert fresh.value == set(), "changed text must re-embed"
