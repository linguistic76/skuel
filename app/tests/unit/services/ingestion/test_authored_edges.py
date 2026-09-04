"""
Unit: the authored-edge fingerprint and its tracker plumbing.

The fingerprint is a pure function over the prepared entity dict and the entity
type's registered relationship fields; the tracker stores it on the file's row,
carries it across a move, and hands it back keyed by the caller's own paths.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.ingestion.ingestion_types import AuthoredEdge, RelationshipConfig
from core.models.relationship_names import RelationshipName
from core.services.ingestion.authored_edges import (
    authored_edge_fingerprint,
    parse_authored_edge,
    retracted_edges,
)
from core.services.ingestion.config import ENTITY_CONFIGS
from core.services.ingestion.ingestion_tracker import IngestionTracker
from core.services.ingestion.move_detection import MoveCandidate, NewFileCandidate
from core.utils.result_simplified import Result

_CONFIG: dict[str, RelationshipConfig] = {
    "uses_kus": {"rel_type": "USES_KU", "target_label": "Ku", "direction": "outgoing"},
    "learning_path_uids": {
        "rel_type": "HAS_STEP",
        "target_label": "Entity",
        "direction": "incoming",
    },
    "connections.related": {
        "rel_type": "RELATED_TO",
        "target_label": "Entity",
        "direction": "both",
    },
    "organizes": {
        "rel_type": "ORGANIZES",
        "target_label": "Entity",
        "direction": "outgoing",
        "order_property": "order",
    },
}


class TestAuthoredEdgeFingerprint:
    def test_registered_fields_only_sorted_and_deduplicated(self) -> None:
        entity = {
            "uid": "ps.t.x",
            "uses_kus": ["ku.t.b", "ku.t.a", "ku.t.a"],
            "resource_uids": ["resource.t.unregistered-here"],
            "title": "not a field",
        }
        assert authored_edge_fingerprint(entity, _CONFIG) == [
            "USES_KU|outgoing|ku.t.a",
            "USES_KU|outgoing|ku.t.b",
        ]

    def test_direction_incoming_kept_both_collapses_to_outgoing(self) -> None:
        entity = {"learning_path_uids": ["lp.t.p"], "connections.related": ["ps.t.y"]}
        assert authored_edge_fingerprint(entity, _CONFIG) == [
            "HAS_STEP|incoming|lp.t.p",
            "RELATED_TO|outgoing|ps.t.y",
        ]

    def test_string_value_is_one_target(self) -> None:
        assert authored_edge_fingerprint({"uses_kus": "ku.t.solo"}, _CONFIG) == [
            "USES_KU|outgoing|ku.t.solo"
        ]

    def test_non_string_elements_and_empty_strings_author_nothing(self) -> None:
        entity = {"uses_kus": ["", 5, None, {"uid": "ku.t.a"}], "organizes": None}
        assert authored_edge_fingerprint(entity, _CONFIG) == []

    def test_ordered_field_keys_carry_no_position(self) -> None:
        # Position lives on the edge (``order``), refreshed by MERGE; a reorder
        # alone is not a retraction.
        first = authored_edge_fingerprint({"organizes": ["ku.t.a", "ku.t.b"]}, _CONFIG)
        second = authored_edge_fingerprint({"organizes": ["ku.t.b", "ku.t.a"]}, _CONFIG)
        assert first == second

    def test_no_config_no_fingerprint(self) -> None:
        assert authored_edge_fingerprint({"uses_kus": ["ku.t.a"]}, None) == []
        assert authored_edge_fingerprint({"uses_kus": ["ku.t.a"]}, {}) == []

    def test_every_registered_field_config_is_entity_labelled(self) -> None:
        """The retraction primitive matches the source as ``:Entity`` — the
        precondition that makes that exact is that relationship fields are
        registered only on ``:Entity``-based ingestion configs."""
        for entity_type, config in ENTITY_CONFIGS.items():
            if config.relationship_config:
                assert config.base_label == "Entity", (
                    f"{entity_type}: relationship fields on a non-Entity config would "
                    "escape the retraction MATCH"
                )


class TestParseAndDiff:
    def test_parse_round_trips_a_key(self) -> None:
        assert parse_authored_edge("USES_KU|outgoing|ku.t.a") == AuthoredEdge(
            RelationshipName.USES_KU, "outgoing", "ku.t.a"
        )
        assert parse_authored_edge("HAS_STEP|incoming|lp.t.p") == AuthoredEdge(
            RelationshipName.HAS_STEP, "incoming", "lp.t.p"
        )

    @pytest.mark.parametrize(
        "key",
        [
            "NOT_A_TYPE|outgoing|ku.t.a",
            "USES_KU|sideways|ku.t.a",
            "USES_KU|outgoing",
            "USES_KU||ku.t.a",
            "",
        ],
    )
    def test_parse_rejects_keys_naming_no_writable_edge(self, key: str) -> None:
        assert parse_authored_edge(key) is None

    def test_retracted_is_prior_minus_current_decoded_in_key_order(self) -> None:
        prior = ["USES_KU|outgoing|ku.t.b", "USES_KU|outgoing|ku.t.a", "HAS_STEP|incoming|lp.t.p"]
        current = ["USES_KU|outgoing|ku.t.a", "USES_KU|outgoing|ku.t.new"]
        assert retracted_edges(prior, current) == [
            AuthoredEdge(RelationshipName.HAS_STEP, "incoming", "lp.t.p"),
            AuthoredEdge(RelationshipName.USES_KU, "outgoing", "ku.t.b"),
        ]

    def test_unchanged_declaration_is_an_empty_diff(self) -> None:
        keys = ["USES_KU|outgoing|ku.t.a", "USES_KU|outgoing|ku.t.b"]
        assert retracted_edges(keys, list(reversed(keys))) == []

    def test_undecodable_prior_key_is_skipped_not_fatal(self) -> None:
        assert retracted_edges(["GONE_TYPE|outgoing|ku.t.a", "USES_KU|outgoing|ku.t.b"], []) == [
            AuthoredEdge(RelationshipName.USES_KU, "outgoing", "ku.t.b")
        ]


def _backend_with_rows(rows: list[dict]) -> MagicMock:
    backend = MagicMock()
    by_path = {row["file_path"]: row for row in rows}

    async def _metadata_for(paths: list[str]) -> Result[list[dict]]:
        return Result.ok([by_path[p] for p in paths if p in by_path])

    backend.get_ingestion_metadata = AsyncMock(side_effect=_metadata_for)
    backend.update_ingestion_metadata = AsyncMock(return_value=Result.ok([]))
    backend.update_ingestion_metadata_batch = AsyncMock(return_value=Result.ok([{"updated": 1}]))
    backend.delete_ingestion_metadata = AsyncMock(return_value=Result.ok([{"deleted": 1}]))
    return backend


class TestTrackerFingerprintPlumbing:
    @pytest.mark.asyncio
    async def test_get_authored_edges_keyed_by_caller_path(self, tmp_path: Path) -> None:
        stamped = tmp_path / "x.md"
        legacy = tmp_path / "old.md"
        untracked = tmp_path / "new.md"
        backend = _backend_with_rows(
            [
                {
                    "file_path": str(stamped.resolve()),
                    "content_hash": "h",
                    "file_mtime": 0.0,
                    "last_ingested_at": None,
                    "entity_uid": "ps.t.x",
                    "authored_edges": ["USES_KU|outgoing|ku.t.a"],
                },
                # A row stamped without a fingerprint reads back as null.
                {
                    "file_path": str(legacy.resolve()),
                    "content_hash": "h",
                    "file_mtime": 0.0,
                    "last_ingested_at": None,
                    "entity_uid": "ps.t.old",
                    "authored_edges": None,
                },
            ]
        )
        tracker = IngestionTracker(backend)

        result = await tracker.get_authored_edges([stamped, legacy, untracked])

        assert result.is_ok
        assert result.value == {
            str(stamped): ["USES_KU|outgoing|ku.t.a"],
            str(legacy): [],
            str(untracked): [],
        }

    @pytest.mark.asyncio
    async def test_single_stamp_carries_fingerprint(self, tmp_path: Path) -> None:
        target = tmp_path / "x.md"
        target.write_text("x")
        backend = _backend_with_rows([])
        tracker = IngestionTracker(backend)

        result = await tracker.update_ingestion_metadata(
            target, "ps.t.x", "hash", ("USES_KU|outgoing|ku.t.a",)
        )

        assert result.is_ok
        payload = backend.update_ingestion_metadata.await_args.args[0]
        assert payload["authored_edges"] == ["USES_KU|outgoing|ku.t.a"]

    @pytest.mark.asyncio
    async def test_batch_stamp_carries_fingerprint_per_file(self, tmp_path: Path) -> None:
        x = tmp_path / "x.md"
        edge = tmp_path / "edge.md"
        x.write_text("x")
        edge.write_text("e")
        backend = _backend_with_rows([])
        tracker = IngestionTracker(backend)

        result = await tracker.update_ingestion_metadata_batch(
            [
                (x, "ps.t.x", "hx", ["USES_KU|outgoing|ku.t.a"]),
                (edge, "edge:ku.t.a|ENABLES_KNOWLEDGE|ku.t.b", "he", []),
            ]
        )

        assert result.is_ok
        items = backend.update_ingestion_metadata_batch.await_args.args[0]
        assert [item["authored_edges"] for item in items] == [["USES_KU|outgoing|ku.t.a"], []]

    @pytest.mark.asyncio
    async def test_move_rewrite_carries_the_fingerprint_to_the_new_row(
        self, tmp_path: Path
    ) -> None:
        backend = _backend_with_rows([])
        tracker = IngestionTracker(backend)
        row = MoveCandidate(
            file_path=str(tmp_path / "old.md"),
            entity_uid="ps.t.x",
            content_hash="h1",
            authored_edges=("USES_KU|outgoing|ku.t.a", "USES_KU|outgoing|ku.t.b"),
        )
        new_file = NewFileCandidate(file_path=str(tmp_path / "new.md"), content_hash="h1")

        result = await tracker._rewrite_move_row(row, new_file, tmp_path, similarity=None)

        assert result.is_ok
        payload = backend.update_ingestion_metadata.await_args.args[0]
        assert payload["file_path"] == str(tmp_path / "new.md")
        assert payload["entity_uid"] == "ps.t.x"
        assert payload["authored_edges"] == [
            "USES_KU|outgoing|ku.t.a",
            "USES_KU|outgoing|ku.t.b",
        ]
