"""
Entity writers never carry the embedding writer's properties
=============================================================

``EmbeddingsBackend.store_embedding_metadata`` is the ONE writer of the
embedding triple (+ version / text hash). ``Entity`` carries the triple as
model fields defaulting to ``None``, and the mapper serialises ``None`` as an
explicit null — which under ``SET n += $props`` REMOVES the property. So every
entity writer that applies a full-model payload to an EXISTING node drops
those keys first, through one helper (``without_embedding_props``).

These tests pin the helper's exact key set and assert the two callers whose
write is ``MERGE … ON MATCH SET n +=``: ``UserEntryBackend.upsert`` (the
vault's living-note door) and ``prepare_batch_items`` (the bulk-ingest
door). Asserting the caller, not just the helper: a helper nobody calls
fixes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import Mock

import pytest

from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from adapters.persistence.neo4j.batch_preparer import prepare_batch_items
from adapters.persistence.neo4j.neo4j_mapper import (
    EMBEDDING_OWNED_PROPERTIES,
    to_neo4j_node,
    without_embedding_props,
)
from core.models.user_entry.user_entry import UserEntry

_OWNED = {
    "embedding",
    "embedding_model",
    "embedding_updated_at",
    "embedding_version",
    "embedding_text_hash",
}


class TestWithoutEmbeddingProps:
    def test_owned_set_is_exactly_the_writers_five_properties(self) -> None:
        assert frozenset(_OWNED) == EMBEDDING_OWNED_PROPERTIES

    def test_strips_exactly_the_owned_keys_and_nothing_else(self) -> None:
        payload = {
            "uid": "ue_x",
            "title": "t",
            "embedding": None,
            "embedding_model": None,
            "embedding_updated_at": None,
            "embedding_version": "v3",
            "embedding_text_hash": "abc",
        }
        out = without_embedding_props(payload)
        assert set(payload) - set(out) == _OWNED
        assert out == {"uid": "ue_x", "title": "t"}

    def test_other_explicit_nulls_pass_through(self) -> None:
        """Null-under-``+=`` is the retraction channel for cleared fields — keep it."""
        out = without_embedding_props({"uid": "ue_x", "fulfills_exercise_uid": None})
        assert out == {"uid": "ue_x", "fulfills_exercise_uid": None}

    def test_returns_a_new_dict_and_leaves_the_input_alone(self) -> None:
        payload = {"uid": "ue_x", "embedding": [0.1]}
        out = without_embedding_props(payload)
        assert out is not payload
        assert payload == {"uid": "ue_x", "embedding": [0.1]}

    def test_a_full_model_payload_carries_the_triple_as_nulls(self) -> None:
        """The premise: the mapper emits the model's None triple as explicit nulls."""
        props = to_neo4j_node(UserEntry(uid="ue_x", title="t", user_uid="user_x"))
        assert {k: props[k] for k in ("embedding", "embedding_model", "embedding_updated_at")} == {
            "embedding": None,
            "embedding_model": None,
            "embedding_updated_at": None,
        }


class TestUserEntryUpsertCaller:
    @pytest.mark.asyncio
    async def test_neither_create_nor_match_payload_carries_an_owned_key(self) -> None:
        driver = Mock()
        driver._closed = False
        backend = UserEntryBackend(driver)
        captured: dict[str, Any] = {}

        async def _run_single(query: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            captured["query"] = query
            captured["params"] = params or {}
            return {"n": dict(captured["params"]["props"]), "owned": True}

        backend._run_single = _run_single  # type: ignore[method-assign]

        entry = UserEntry(uid="ue_resync01", title="Decisions 0", user_uid="user_x", content="c")
        result = await backend.upsert(entry)
        assert result.is_ok, result.expect_error()

        params = captured["params"]
        assert not _OWNED & set(params["props"])
        assert not _OWNED & set(params["on_match_props"])
        # Existing contracts stay: created_at is CREATE-only, the living channel's
        # explicit null still rides ON MATCH, and the ownership gate is unchanged.
        assert "created_at" in params["props"]
        assert "created_at" not in params["on_match_props"]
        assert params["on_match_props"]["fulfills_exercise_uid"] is None
        assert "n.user_uid = $owner" in captured["query"]


@dataclass(frozen=True)
class _DataclassEntity:
    """A dataclass entity with the embedding triple, as a model would carry it."""

    uid: str
    title: str
    embedding: tuple[float, ...] | None = None
    embedding_model: str | None = None
    embedding_updated_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TestPrepareBatchItemsCaller:
    def test_dataclass_entity_carries_no_owned_key(self) -> None:
        [item] = prepare_batch_items([_DataclassEntity(uid="ku.x", title="t")], rel_config=None)
        assert not _OWNED & set(item)
        assert item["uid"] == "ku.x"

    def test_dict_entity_and_its_node_props_carry_no_owned_key(self) -> None:
        rel_config = {
            "connections.requires": {
                "rel_type": "PREREQUISITE",
                "target_label": "Entity",
                "direction": "incoming",
            }
        }
        [item] = prepare_batch_items(
            [{"uid": "ku.x", "title": "t", "embedding": None, "embedding_version": "v3"}],
            rel_config=rel_config,
        )
        assert not _OWNED & set(item)
        assert not _OWNED & set(item["_node_props"])
        assert item["_node_props"]["title"] == "t"
